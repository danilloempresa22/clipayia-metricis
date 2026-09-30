"""Servidor local + conta. Supabase e Whisper sao simulados; o resto (ffmpeg, cortes, CapCut falso) e' real."""
import json, threading, time, urllib.request, urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
import pytest
from clipay import conta, servidor, transcricao


@pytest.fixture
def app(monkeypatch, raiz_capcut, tmp_path):
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: tmp_path)
    monkeypatch.setattr(servidor, "raiz_atual", lambda: raiz_capcut)
    monkeypatch.setattr(transcricao, "modelo_pronto", lambda q="preciso": True)
    monkeypatch.setattr(transcricao, "Whisper", lambda q: None)
    monkeypatch.setattr(transcricao, "frases", lambda w, x, p=None: [[0.0, 3.0, "primeira fala"], [4.5, 7.5, "segunda fala"], [9.0, 10.0, "final"]])
    estado = {"status": "ativo", "usos": 0}
    monkeypatch.setattr(conta, "estado", lambda: {"logado": True, "email": "a@b.c", "username": "a", "status": estado["status"]})
    monkeypatch.setattr(conta, "registra_processamento", lambda: estado.update(usos=estado["usos"] + 1))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), servidor.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def chama(caminho, corpo=None, token=servidor.TOKEN, host=None):
        h = {"X-Clipay-Token": token, "Content-Type": "application/json"}
        if host: h["Host"] = host
        req = urllib.request.Request(base + caminho, headers=h, method="GET" if corpo is None else "POST",
                                     data=None if corpo is None else json.dumps(corpo).encode())
        try:
            with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def espera(jid):
        for _ in range(200):
            _, j = chama(f"/api/job?id={jid}")
            if j.get("fim"): return j
            time.sleep(0.1)
        raise AssertionError("job nao terminou")

    yield chama, espera, estado, base
    srv.shutdown()


def test_index_leva_token_e_api_exige_token(app):
    chama, _, _, base = app
    html = urllib.request.urlopen(base + "/").read().decode()
    assert servidor.TOKEN in html and "__TOKEN__" not in html
    assert chama("/api/estado", token="errado")[0] == 403
    assert chama("/api/estado", token="")[0] == 403
    assert chama("/api/estado")[0] == 200


def test_erro_inesperado_vira_json_e_nao_conexao_caida(app, monkeypatch):
    chama, *_ = app
    def quebra(*a): raise RuntimeError("tk quebrou")
    monkeypatch.setattr(servidor, "escolhe_arquivo", quebra)
    c, r = chama("/api/escolher-arquivo", {})
    assert c == 500 and "tk quebrou" in r["erro"]


def test_host_estranho_e_barrado(app):
    chama, *_ = app
    assert chama("/api/estado", host="evil.example.com")[0] == 403


def test_fluxo_completo_analisa_revisa_gera(app, video_vertical, raiz_capcut):
    chama, espera, estado, _ = app
    c, r = chama("/api/analisar", {"caminho": str(video_vertical)})
    assert c == 200
    j = espera(r["id"]); assert "erro" not in j, j
    a = j["resultado"]
    assert a["rosto"] == "centro" and a["rosto_confiavel"] is False               # video sintetico: sem rosto
    assert a["frases"][0][2] == "primeira fala" and a["depois"] < a["duracao"] and (a["largura"], a["altura"]) == (540, 960)

    # gera removendo a 2a frase (4,5-7,5 s) e escolhendo o lado
    c, r = chama("/api/gerar", {"analise": a["analise"], "headline": "TESTE DE HEADLINE BEM GRANDE AQUI", "rosto": "direita",
                                "remover": [a["frases"][1][:2]], "nome": "Projeto do teste"})
    assert c == 200
    j = espera(r["id"]); assert "erro" not in j, j
    res = j["resultado"]
    assert res["nome"] == "Projeto do teste" and res["depois"] < a["depois"]      # removeu a fala a mais
    d = json.loads((Path(raiz_capcut) / "Projeto do teste" / "draft_content.json").read_text(encoding="utf-8"))
    assert any(t["type"] == "text" for t in d["tracks"])
    assert estado["usos"] == 1                                                    # contou 1 processamento


def test_conta_inativa_bloqueia_antes_de_processar(app, video_vertical, monkeypatch):
    chama, _, estado, _ = app
    monkeypatch.setattr(conta, "estado", lambda: {"logado": True, "email": "a@b.c", "username": "a", "status": "inativo"})
    c, r = chama("/api/analisar", {"caminho": str(video_vertical)})
    assert c == 400 and "não está ativa" in r["erro"]
    c, r = chama("/api/gerar", {"analise": "x"})
    assert c == 400 and estado["usos"] == 0


def test_analise_inexistente_e_arquivo_invalido(app):
    chama, espera, *_ = app
    assert chama("/api/analisar", {"caminho": "C:/nao/existe.mp4"})[0] == 400
    assert chama("/api/analisar", {"caminho": __file__})[0] == 400                 # nao e' video
    c, r = chama("/api/gerar", {"analise": "fantasma"})
    assert "expirou" in espera(r["id"])["erro"]


def test_fluxo_legenda_complexa_pela_api(app, video_vertical, raiz_capcut, monkeypatch):
    chama, espera, estado, base = app
    from clipay import palavras
    monkeypatch.setattr(palavras, "transcreve", lambda w, x, p=None: [
        *palavras.espalha("isso aqui muda tudo", [[0.0, 3.0]]), *palavras.espalha("você nunca tentou", [[4.5, 7.5]])])
    c, r = chama("/api/analisar", {"caminho": str(video_vertical), "modo": "legenda"})
    assert c == 200
    j = espera(r["id"]); assert "erro" not in j, j
    a = j["resultado"]
    assert a["modo"] == "legenda" and [p[2] for p in a["palavras"]][:2] == ["isso", "aqui"]
    # previa: sem token = 403; com token e Range = 206 com o pedaco pedido
    assert urllib.request.urlopen(urllib.request.Request(f"{base}/api/video?analise={a['analise']}&t={servidor.TOKEN}",
                                                         headers={"Range": "bytes=0-99"})).status == 206
    try:
        urllib.request.urlopen(f"{base}/api/video?analise={a['analise']}&t=errado"); assert False
    except urllib.error.HTTPError as e:
        assert e.code == 403
    c, r = chama("/api/gerar", {"analise": a["analise"], "texto": "isso aqui muda [tudo] você nunca tentou",
                                "inicio": a["palavras"][1][0], "zoom": 1.3, "velocidade": 1.15, "nome": "Via API"})
    j = espera(r["id"]); assert "erro" not in j, j
    assert j["resultado"]["enfases"] == 1 and (Path(raiz_capcut) / "Via API" / "subdraft").is_dir()
    assert estado["usos"] == 1


def test_painel_conta_videos_e_historico(app, video_vertical, monkeypatch):
    chama, espera, *_ = app
    from datetime import datetime, timedelta, timezone
    agora = datetime.now(timezone.utc)
    datas = [agora.isoformat(), agora.isoformat(), (agora - timedelta(weeks=1)).isoformat(), (agora - timedelta(weeks=20)).isoformat()]
    monkeypatch.setattr(conta, "processamentos", lambda: datas)
    c, p = chama("/api/painel")
    assert c == 200 and p["videos"] == 4 and p["fonte"] == "conta"
    assert len(p["semanas"]) == 8 and p["semanas"][-1]["videos"] == 2 and p["semanas"][-2]["videos"] == 1
    assert sum(s["videos"] for s in p["semanas"]) == 3                      # a de 20 semanas atras fica fora do grafico
    assert p["recentes"] == [] and p["silencio_removido"] == 0

    # gerar um projeto alimenta o historico local
    _, r = chama("/api/analisar", {"caminho": str(video_vertical)})
    a = espera(r["id"])["resultado"]
    _, r = chama("/api/gerar", {"analise": a["analise"], "nome": "Hist"})
    espera(r["id"])
    _, p = chama("/api/painel")
    assert p["recentes"][0]["nome"] == "Hist" and p["silencio_removido"] > 0


def test_painel_sem_internet_usa_historico_local(app, monkeypatch):
    chama, *_ = app
    def offline(): raise conta.ErroConta("Sem conexão com a internet.")
    monkeypatch.setattr(conta, "processamentos", offline)
    servidor.historico_path().write_text(json.dumps([{"data": "2020-01-01T00:00:00+00:00", "nome": "x", "antes": 10, "depois": 7,
                                                      "pedacos": 3, "zooms": 1, "headline": ""}]), encoding="utf-8")
    c, p = chama("/api/painel")
    assert c == 200 and p["fonte"] == "local" and p["videos"] == 1 and p["silencio_removido"] == 3


# ---- conta (Supabase simulado) ----
def _jwt(sub):
    import base64
    p = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).decode().rstrip("=")
    return f"x.{p}.y"


def test_login_guarda_sessao_e_traduz_erros(monkeypatch, tmp_path):
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: tmp_path)
    monkeypatch.setattr(conta, "_chama", lambda m, p, *a, **k: {"access_token": _jwt("uid-1"), "refresh_token": "r",
                                                                  "expires_in": 3600, "user": {"email": "a@b.c"}})
    s = conta.login("a@b.c", "senha")
    assert s["user_id"] == "uid-1" and conta.sessao()["email"] == "a@b.c"
    conta.logout(); assert conta.sessao() is None
    with pytest.raises(conta.ErroConta, match="Preencha"): conta.login("", "")
    assert "incorretos" in conta._traduz({"error_description": "Invalid login credentials"}, 400)
    assert "Confirme" in conta._traduz({"msg": "Email not confirmed"}, 400)


def test_estado_e_exige_ativa(monkeypatch, tmp_path):
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: tmp_path)
    (tmp_path / "sessao.json").write_text(json.dumps({"access_token": _jwt("u"), "refresh_token": "r",
                                                       "expira": time.time() + 999, "email": "e@x", "user_id": "u"}))
    dados = {"/rest/v1/subscriptions": [{"status": "inativo"}], "/rest/v1/profiles": [{"username": "fulano"}]}
    monkeypatch.setattr(conta, "_chama", lambda m, p, *a, **k: next(v for k, v in dados.items() if p.startswith(k)))
    e = conta.estado()
    assert e == {"logado": True, "email": "e@x", "username": "fulano", "status": "inativo"}
    with pytest.raises(conta.ErroConta, match="não está ativa"): conta.exige_ativa()
    dados["/rest/v1/subscriptions"] = [{"status": "ativo"}]
    assert conta.exige_ativa()["status"] == "ativo"


# ---- tela de login: senha esquecida, Google, logo ----
def test_login_recusa_email_invalido_antes_de_chamar_o_supabase(monkeypatch, tmp_path):
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: tmp_path)
    monkeypatch.setattr(conta, "_chama", lambda *a, **k: (_ for _ in ()).throw(AssertionError("nao devia chamar")))
    with pytest.raises(conta.ErroConta, match="não parece válido"):
        conta.login("sem-arroba", "12345678")


def test_recuperar_senha_manda_link_pro_site(app, monkeypatch):
    chama, *_ = app
    pedidos = []
    monkeypatch.setattr(conta, "_chama", lambda m, p, corpo=None, **k: pedidos.append((p, corpo)))
    assert chama("/api/recuperar", {"email": "x"})[0] == 400                      # sem e-mail valido: erro na tela
    c, r = chama("/api/recuperar", {"email": "a@b.com"})
    assert c == 200 and pedidos[-1][0].startswith("/auth/v1/recover?redirect_to=")
    from urllib.parse import urlparse, parse_qs
    assert parse_qs(urlparse(pedidos[-1][0]).query)["redirect_to"][0].endswith("/redefinir-senha")   # na URL, nao no corpo
    assert pedidos[-1][1] == {"email": "a@b.com"}


def test_google_indisponivel_avisa_sem_abrir_navegador(app, monkeypatch):
    chama, *_ = app
    abriu = []
    monkeypatch.setattr(servidor.webbrowser, "open", lambda u: abriu.append(u))
    monkeypatch.setattr(conta, "_chama", lambda *a, **k: {"external": {"google": False}})
    c, r = chama("/api/google", {})
    assert c == 400 and "Google ainda não está disponível" in r["erro"] and not abriu


def test_google_volta_com_codigo_de_uso_unico(app, monkeypatch):
    chama, _, _, base = app
    abriu = []
    monkeypatch.setattr(servidor.webbrowser, "open", lambda u: abriu.append(u))
    monkeypatch.setattr(conta, "google_disponivel", lambda: True)
    entrou = []
    monkeypatch.setattr(conta, "entra_com_tokens", lambda a, r, e=3600: entrou.append(a))
    assert chama("/api/google", {})[0] == 200
    from urllib.parse import urlparse, parse_qs
    volta = parse_qs(urlparse(abriu[0]).query)["redirect_to"][0]
    assert volta.startswith("http://127.0.0.1:") and "/auth/retorno?estado=" in volta
    estado = parse_qs(urlparse(volta).query)["estado"][0]
    assert chama("/api/google-tokens", {"estado": "forjado", "access_token": "x"})[0] == 400      # outra pagina nao entra
    c, _ = chama("/api/google-tokens", {"estado": estado, "access_token": "tok", "refresh_token": "r"})
    assert c == 200 and entrou == ["tok"]
    assert chama("/api/google-tokens", {"estado": estado, "access_token": "tok"})[0] == 400       # uso unico
    pagina = urllib.request.urlopen(base + "/auth/retorno?estado=x").read().decode()
    assert servidor.TOKEN in pagina and "__TOKEN__" not in pagina


def test_logo_e_abrir_site(app, monkeypatch):
    chama, _, _, base = app
    r = urllib.request.urlopen(base + "/assets/img/logo-clipay.png")
    assert r.status == 200 and r.headers["Content-Type"] == "image/png"
    try:
        urllib.request.urlopen(base + "/assets/img/..%2F..%2Fconta.py"); assert False
    except urllib.error.HTTPError as e:
        assert e.code == 404
    abriu = []
    monkeypatch.setattr(servidor.webbrowser, "open", lambda u: abriu.append(u))
    assert chama("/api/abrir-site", {"caminho": "/cadastro"})[0] == 200 and abriu[0].endswith("/cadastro")
    assert chama("/api/abrir-site", {"caminho": "https://malicioso.com"})[0] == 400


def test_mensagens_de_limite_de_email_do_supabase():
    assert "60 segundos" in conta._traduz({"msg": "For security purposes, you can only request this after 60 seconds."}, 429)
    assert "mais tarde" in conta._traduz({"msg": "email rate limit exceeded"}, 429)


def test_botao_google_so_aparece_quando_ligado(app, monkeypatch):
    chama, *_ = app
    monkeypatch.setattr(conta, "google_disponivel", lambda: False)
    assert chama("/api/estado")[1]["google"] is False
    monkeypatch.setattr(conta, "google_disponivel", lambda: True)
    assert chama("/api/estado")[1]["google"] is True
