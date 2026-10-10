"""Servidor local + conta. Supabase e Whisper sao simulados; o resto (ffmpeg, cortes, CapCut falso) e' real."""
import json, threading, time, urllib.request, urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
import pytest
from clipay import conta, palavras, servidor, transcricao


@pytest.fixture
def app(monkeypatch, raiz_capcut, tmp_path):
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: tmp_path)
    monkeypatch.setattr(servidor, "raiz_atual", lambda: raiz_capcut)
    monkeypatch.setattr(transcricao, "modelo_pronto", lambda q="preciso": True)
    monkeypatch.setattr(transcricao, "Whisper", lambda q: None)
    monkeypatch.setattr(transcricao, "frases", lambda w, x, p=None, **k: [[0.0, 3.0, "primeira fala"], [4.5, 7.5, "segunda fala"], [9.0, 10.0, "final"]])
    # Cortes + Headline: tempo de cada palavra (as frases saem do ponto final)
    monkeypatch.setattr(palavras, "transcreve", lambda w, x, p=None, **k: [
        {"t": "primeira", "a": 0.0, "b": 1.5}, {"t": "fala.", "a": 1.5, "b": 3.0}, {"t": "segunda", "a": 4.5, "b": 6.0},
        {"t": "fala.", "a": 6.0, "b": 7.5}, {"t": "Fechou?", "a": 9.0, "b": 9.5}, {"t": "Boa!", "a": 9.6, "b": 10.0}])
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
    assert "rosto" not in a                                                       # sem escolha de lado: zoom centrado sozinho
    assert a["frases"][0][2] == "primeira fala." and a["depois"] < a["duracao"] and (a["largura"], a["altura"]) == (540, 960)
    assert [x["tipo"] for x in a["sobras"]] == ["final"]                        # "Fechou? Boa!" no fim: sugestao, nada sai sozinho

    # um "remover" antigo no pedido e' ignorado (so "tirar", o que a pessoa confirmou); sem acelerar
    c, r = chama("/api/gerar", {"analise": a["analise"], "headline": "TESTE DE HEADLINE BEM GRANDE AQUI",
                                "remover": [a["frases"][1][:2]], "nome": "Projeto do teste", "velocidade": False})
    assert c == 200
    j = espera(r["id"]); assert "erro" not in j, j
    res = j["resultado"]
    assert res["nome"] == "Projeto do teste" and abs(res["depois"] - a["depois"]) < 0.05    # nada saiu do video
    d = json.loads((Path(raiz_capcut) / "Projeto do teste" / "draft_content.json").read_text(encoding="utf-8"))
    assert any(t["type"] == "text" for t in d["tracks"])
    assert estado["usos"] == 1                                                    # contou 1 processamento

    # tirar a 2a frase (confirmada na revisao) e acelerar 1,13x: tudo num clipe composto acelerado
    c, r = chama("/api/gerar", {"analise": a["analise"], "headline": "OUTRA", "nome": "Projeto acelerado",
                                "tirar": [[4.5, 7.6]], "velocidade": True})
    j = espera(r["id"]); assert "erro" not in j, j
    res2 = j["resultado"]
    pasta = Path(raiz_capcut) / "Projeto acelerado"
    d = json.loads((pasta / "draft_content.json").read_text(encoding="utf-8"))
    dentro = d["materials"]["drafts"][0]["draft"]
    assert res2["velocidade"] == pytest.approx(1.13, abs=0.01) and d["tracks"][0]["segments"][0]["speed"] == pytest.approx(1.13, abs=0.01)
    assert dentro["duration"] == pytest.approx(d["duration"] * res2["velocidade"], abs=1000)
    assert dentro["duration"] / 1e6 < a["depois"] - 2.5                         # a 2a frase saiu
    assert (pasta / "subdraft" / dentro["id"] / "draft_content.json").exists()
    assert {t["type"] for t in dentro["tracks"]} == {"video", "text"}           # cortes, zoom e headline dentro do composto


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
    monkeypatch.setattr(palavras, "transcreve", lambda w, x, p=None, **k: [
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
    assert e == {"logado": True, "email": "e@x", "username": "fulano", "nome": "", "status": "inativo"}
    with pytest.raises(conta.ErroConta, match="não está ativa"): conta.exige_ativa()
    dados["/rest/v1/subscriptions"] = [{"status": "ativo"}]
    assert conta.exige_ativa()["status"] == "ativo"



def test_estado_nome_cache_offline_e_sql_0003(monkeypatch, tmp_path):
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: tmp_path)
    (tmp_path / "sessao.json").write_text(json.dumps({"access_token": _jwt("u"), "refresh_token": "r",
                                                       "expira": time.time() + 999, "email": "e@x", "user_id": "u"}))
    def sem_coluna(m, p, *a, **k):                       # antes do SQL 0003: a coluna nome nao existe
        if "nome" in p: raise conta.ErroConta("column profiles.nome does not exist")
        return [{"status": "ativo"}] if "subscriptions" in p else [{"username": "fulano"}]
    monkeypatch.setattr(conta, "_chama", sem_coluna)
    assert conta.estado()["nome"] == "" and conta.estado()["username"] == "fulano"
    def patch_sem_coluna(m, p, *a, **k):
        raise conta.ErroConta("Could not find the 'nome' column of 'profiles' in the schema cache")
    monkeypatch.setattr(conta, "_chama", patch_sem_coluna)
    with pytest.raises(conta.ErroConta, match="SQL 0003"): conta.salva_nome("Fulano")
    monkeypatch.setattr(conta, "_chama", lambda *a, **k: [])        # RLS recusou (sem policy de update)
    with pytest.raises(conta.ErroConta, match="SQL 0003"): conta.salva_nome("Fulano")
    with pytest.raises(conta.ErroConta, match="Escreva"): conta.salva_nome("   ")
    monkeypatch.setattr(conta, "_chama", lambda *a, **k: [{"nome": "Fulano de Tal"}])
    assert conta.salva_nome("  Fulano   de  Tal ") == "Fulano de Tal"
    def sem_internet(*a, **k): raise conta.ErroConta("Sem internet.")
    monkeypatch.setattr(conta, "_chama", sem_internet)              # offline: os ultimos dados, marcados
    e = conta.estado()
    assert e["offline"] and e["username"] == "fulano" and e["nome"] == "Fulano de Tal" and e["status"] == "ativo"
    with pytest.raises(conta.ErroConta, match="Sem conexão"): conta.salva_nome("Outro")
    conta.logout(); assert not (tmp_path / "conta_cache.json").exists()

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


def test_ipad_videos_escolhidos_trocados_sao_invertidos_pela_fala(app, video_vertical, video_mudo):
    chama, espera, *_ = app
    # a "camera" escolhida nao tem fala e o "iPad" tem: o app inverte e avisa
    c, r = chama("/api/ipad/preparar", {"ipad": str(video_vertical), "pessoa": str(video_mudo)})
    assert c == 200
    j = espera(r["id"]); assert "erro" not in j, j
    s = j["resultado"]
    assert s["invertido"] is True and s["pessoa"]["nome"] == "vertical.mp4" and s["ipad"]["nome"] == "sem_audio.mp4"
    # inverter de novo pelo botao: recusado, porque o outro video nao tem fala
    c, r = chama("/api/ipad/trocar", {"sessao": s["sessao"]})
    assert c == 400 and "não tem fala" in r["erro"]


def test_ipad_sem_fala_em_nenhum_video_avisa(app, video_mudo, tmp_path):
    chama, espera, *_ = app
    import shutil
    outro = tmp_path / "outro_mudo.mp4"; shutil.copy(video_mudo, outro)
    c, r = chama("/api/ipad/preparar", {"ipad": str(video_mudo), "pessoa": str(outro)})
    assert "Não encontrei fala" in espera(r["id"])["erro"]


# ---- Inicio e Conta: edicoes de todos os modelos, plano de exemplo, Cortes "Em breve" ----
def test_edicoes_junta_modelos_e_some_o_que_saiu_do_capcut(monkeypatch, tmp_path):
    from clipay import edicoes
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: tmp_path)
    raiz = tmp_path / "capcut"
    for n in ("velho", "react 1", "corte 1"):
        (raiz / n).mkdir(parents=True); (raiz / n / "draft_content.json").write_text("{}")
    (raiz / "react 1" / "draft_cover.jpg").write_bytes(b"x")
    (tmp_path / "historico.json").write_text(json.dumps([
        {"data": "2026-09-01T10:00:00+00:00", "nome": "velho", "depois": 30},           # antigo: sem modelo
        {"data": "2026-09-02T10:00:00+00:00", "nome": "apagado", "modelo": "ipad", "depois": 20}]))
    (tmp_path / "historico_cortes.json").write_text(json.dumps([{"data": "2026-09-03T10:00:00+00:00", "projeto": "corte 1", "duracao": 50}]))
    edicoes.anota("react 1", "react", 61.04)
    ts = edicoes.todas(raiz)
    assert [(x["projeto"], x["modelo"]) for x in ts] == [("react 1", "React"), ("corte 1", "Cortes de podcast"), ("velho", "Edição")]
    assert ts[0]["capa"] and not ts[1]["capa"] and ts[0]["duracao"] == 61.0
    r = edicoes.resumo(raiz)
    assert r["total"] == 3 and r["ultima"]["projeto"] == "react 1" and r["mes"] >= 1
    assert edicoes.capa(raiz, "react 1") and edicoes.capa(raiz, "../react 1") is None and edicoes.capa(raiz, "corte 1") is None


def test_cobranca_demo_e_o_unico_lugar_dos_exemplos(monkeypatch):
    from datetime import date
    from clipay import cobranca_demo
    d = cobranca_demo.dados("ativo", date(2026, 10, 8))
    assert d["demo"] and d["status"] == "ativo" and d["plano"]["id"] == "premium"
    assert (d["inicio"], d["renova"], d["dias_total"], d["dias_restantes"]) == ("2026-10-01", "2026-11-01", 31, 24)
    assert [h["data"] for h in d["historico"]] == ["2026-10-01", "2026-09-01", "2026-08-01"]
    assert cobranca_demo.dados("ativo", date(2026, 12, 31))["renova"] == "2027-01-01"
    monkeypatch.setattr(cobranca_demo, "DEMO", False)
    assert cobranca_demo.dados("inativo") == {"demo": False, "status": "inativo"}     # sem exemplo: nada inventado


def test_cortes_em_breve_nao_roda_nada(app, monkeypatch):
    chama, _, _, _ = app
    monkeypatch.setattr(servidor, "cortes_liberado", lambda: False)
    c, e = chama("/api/estado")
    assert c == 200 and e["cortes"]["liberado"] is False
    assert chama("/api/cortes/recentes") == (403, {"erro": "Cortes está chegando."})
    assert chama("/api/cortes/analisa", {"caminho": "x"})[0] == 403
    c, d = chama("/api/conta")
    assert c == 200 and d["cobranca"]["status"] == "ativo" and d["foto"] is False and "total" in d["edicoes"]


def test_foto_do_perfil_fica_so_no_computador(app, tmp_path):
    import cv2, numpy as np
    chama, _, _, base = app
    ruim = urllib.request.Request(base + "/api/conta/foto", data=b"nao e imagem", method="POST",
                                  headers={"X-Clipay-Token": servidor.TOKEN, "Content-Type": "application/octet-stream"})
    try: urllib.request.urlopen(ruim); assert False
    except urllib.error.HTTPError as e: assert e.code == 400 and "JPG ou PNG" in json.loads(e.read())["erro"]
    ok, png = cv2.imencode(".png", np.full((300, 500, 3), 200, np.uint8))
    boa = urllib.request.Request(base + "/api/conta/foto", data=png.tobytes(), method="POST",
                                 headers={"X-Clipay-Token": servidor.TOKEN, "Content-Type": "application/octet-stream"})
    assert urllib.request.urlopen(boa).status == 200
    im = cv2.imread(str(tmp_path / "foto_perfil.jpg"))
    assert im.shape[:2] == (256, 256)
    r = urllib.request.urlopen(f"{base}/api/foto?t={servidor.TOKEN}")
    assert r.headers["Content-Type"].startswith("image/jpeg")
    try: urllib.request.urlopen(f"{base}/api/foto?t=errado"); assert False
    except urllib.error.HTTPError as e: assert e.code in (401, 403)
    assert chama("/api/conta")[1]["foto"] is True


# ---- React: modelo da headline lembrado, posicao do react guardada com o react salvo ----
def test_react_modelo_lembrado_e_posicao_com_o_react_salvo(app, video_vertical, tmp_path):
    chama, _, _, _ = app
    c, cfg = chama("/api/react/config")
    assert c == 200 and [h["id"] for h in cfg["headlines"]] == ["noticia", "citacao"]
    assert cfg["preferencias"] == {"headline": "noticia"}                       # nunca escolheu: o padrao
    assert all(h["previa"] is None or h["previa"].startswith("/assets/previews/headline/") for h in cfg["headlines"])
    assert chama("/api/react/preferencias", {"headline": "citacao"})[1]["headline"] == "citacao"
    assert chama("/api/react/config")[1]["preferencias"]["headline"] == "citacao"   # reabriu: volta a Citacao
    assert chama("/api/react/preferencias", {"headline": "nao-existe"})[0] == 400
    v = str(video_vertical)
    s = chama("/api/react/salvo", {"caminho": v, "posicao": -40})[1]["salvo"]
    assert s["posicao"] == -40 and s["existe"]
    r = chama("/api/react/preferencias", {"react": v, "posicao": 75})[1]
    assert r["salvo"]["posicao"] == 75 and chama("/api/react/salvo")[1]["salvo"]["posicao"] == 75
    outro = chama("/api/react/preferencias", {"react": str(tmp_path / "outro.mp4"), "posicao": 10})[1]
    assert outro["salvo"]["posicao"] == 75                                       # outro react: nao mexe no salvo
    assert chama("/api/react/preferencias", {"react": v, "posicao": 999})[1]["salvo"]["posicao"] == 100   # limite
    assert chama("/api/react/salvo", {"caminho": ""})[1] == {"salvo": None}      # esquecer: a posicao vai junto
    cfg = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert "react_salvo" not in cfg and cfg["react_headline"] == "citacao"
    assert chama("/api/react/salvo", {"caminho": v})[1]["salvo"]["posicao"] == 0   # salvo de novo: no centro


def test_react_previa_da_headline_so_se_existir(monkeypatch, tmp_path):
    from clipay import fluxo_react
    monkeypatch.setattr(fluxo_react, "PREVIAS_HL", tmp_path)
    assert [h["previa"] for h in fluxo_react.headlines()] == [None, None]          # sem imagem: a tela usa a simples
    (tmp_path / "headline-citacao.webp").write_bytes(b"x")
    assert [h["previa"] for h in fluxo_react.headlines()] == [None, "/assets/previews/headline/headline-citacao.webp"]


# ---- janela do app (Windows e Mac): arquivo arrastado vem com o caminho de verdade, nada e' copiado ----
def test_soltou_na_janela_entrega_o_caminho(monkeypatch, tmp_path):
    v = tmp_path / "Vídeo com acento.mp4"; v.write_bytes(b"x" * 1234)
    monkeypatch.setattr(servidor, "JANELA", object())
    monkeypatch.setattr(servidor, "SOLTOS", [])
    servidor.soltou([str(v), str(tmp_path / "sumiu.mp4")])
    assert servidor.localiza(v.name, 1234) == str(v)                        # o original, sem procurar nem copiar
    assert servidor._do_solto(v.name, 999, espera=0) is None                 # outro tamanho: nao e' o mesmo arquivo


def test_janela_de_arquivo_nativa_quando_tem_janela(monkeypatch):
    pedidos = []

    class Janela:
        def create_file_dialog(self, tipo, **k):
            pedidos.append((tipo, k)); return ("C:/a.mp4", "C:/b.mp4") if k.get("allow_multiple") else ("C:/a.mp4",)
    monkeypatch.setattr(servidor, "JANELA", Janela())
    assert servidor.escolhe_arquivo("video") == "C:/a.mp4"
    assert servidor.escolhe_arquivo("videos") == ["C:/a.mp4", "C:/b.mp4"]
    assert all("Vídeos (*.mp4" in k["file_types"][0] for _, k in pedidos)


# ---- primeira abertura: o motor de transcricao baixa com barra de verdade e retoma se a internet cair ----
def test_preparar_baixa_retoma_e_avisa_sem_internet(monkeypatch, tmp_path):
    import io, urllib.error
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: tmp_path)
    monkeypatch.setattr(transcricao, "motor_rapido_disponivel", lambda: True)
    conteudo = {a: (a * 50000).encode()[:300000] for a in transcricao.CT2_ARQS}
    pedidos, cai = [], {"vez": 1}

    class Resp(io.BytesIO):
        def __init__(self, dados, status=200, tam=0): super().__init__(dados); self.status = status; self.headers = {"Content-Length": str(tam)}
        def __enter__(self): return self
        def __exit__(self, *a): self.close()

    def abre(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        arq = url.rsplit("/", 1)[1]; dados = conteudo[arq]
        if not isinstance(req, str) and req.get_method() == "HEAD": return Resp(b"", 200, len(dados))
        rng = (req.headers.get("Range") if not isinstance(req, str) else None) or ""
        pedidos.append((arq, rng))
        ini = int(rng[6:-1]) if rng else 0
        if arq == "model.bin" and cai["vez"]:                   # a internet cai no meio do arquivo grande
            cai["vez"] = 0
            class Meia(Resp):
                def read(self, n=-1):
                    b = super().read(n)
                    if not b: raise urllib.error.URLError("conexao perdida")
                    return b
            return Meia(dados[:len(dados) // 2], 200)
        return Resp(dados[ini:], 206 if ini else 200)
    monkeypatch.setattr(transcricao.urllib.request, "urlopen", abre)
    with pytest.raises(OSError):
        transcricao.prepara("preciso")
    d = transcricao.pasta_ct2("preciso")
    assert (d / "model.bin.part").stat().st_size == 150000 and not (d / "model.bin").exists()   # pela metade: nunca com o nome final
    vistos = []
    transcricao.prepara("preciso", lambda f, t: vistos.append((f, t)))
    assert ("model.bin", "bytes=150000-") in pedidos                       # continuou de onde parou
    assert all((d / a).read_bytes() == conteudo[a] for a in transcricao.CT2_ARQS) and transcricao.ct2_pronto()
    assert vistos[-1][0] == vistos[-1][1]                                  # a barra chega a 100%


def test_preparar_sem_internet_frase_clara(monkeypatch, tmp_path):
    import urllib.error
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: tmp_path)
    monkeypatch.setattr(transcricao, "motor_rapido_disponivel", lambda: True)
    monkeypatch.setattr(servidor, "PREP", {"estado": None, "feito": 0, "total": 0, "erro": None})
    def sem_rede(*a, **k): raise urllib.error.URLError("getaddrinfo failed")
    monkeypatch.setattr(transcricao.urllib.request, "urlopen", sem_rede)
    assert servidor.estado_preparar()["estado"] == "falta"
    servidor.preparar()
    for _ in range(50):
        if servidor.PREP["estado"] == "erro": break
        time.sleep(0.05)
    e = servidor.estado_preparar()
    assert e["estado"] == "erro" and "internet" in e["erro"] and "Tentar de novo" in e["erro"]
