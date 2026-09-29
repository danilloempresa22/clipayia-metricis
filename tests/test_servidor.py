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
    def quebra(): raise RuntimeError("tk quebrou")
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
