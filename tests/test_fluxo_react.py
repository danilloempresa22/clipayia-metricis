"""Tela React (Fase 2): o que a tela pede ao motor. Mensagens claras, quadro em cache, geracao em segundo plano com
ate 3 ao mesmo tempo, um erro nao derruba os outros, cancelar, e reabrir continua sem duplicar projeto."""
import json, shutil, subprocess, time
from pathlib import Path
import pytest
from clipay import audio, fluxo_react, react, transcricao


def _video(destino, w, h, dur):
    tom = f"aevalsrc='sin(2*PI*150*t)*0.5':s=16000:d={dur}"
    subprocess.run([audio.ffmpeg_bin(), "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s={w}x{h}:r=30:d={dur}",
                    "-f", "lavfi", "-i", tom, "-pix_fmt", "yuv420p", "-c:v", "mpeg4", "-q:v", "5", "-c:a", "aac",
                    "-shortest", str(destino)], check=True, capture_output=True)
    return destino


@pytest.fixture(scope="module")
def midia(tmp_path_factory):
    p = tmp_path_factory.mktemp("rx")
    return {"react": _video(p / "react.mp4", 1920, 1080, 30), "cta": _video(p / "cta.mp4", 1920, 1080, 3),
            "longo": _video(p / "longo demais.mp4", 540, 960, 40)}


@pytest.fixture
def dados(tmp_path, monkeypatch):
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: tmp_path / "dados")
    (tmp_path / "dados").mkdir()
    fluxo_react.GERACAO["job"] = None
    return tmp_path


def _espera(t=60):
    fim = time.time() + t
    while time.time() < fim:
        j = fluxo_react.GERACAO["job"]
        if j and j["parado"]: return fluxo_react.estado_geracao()
        time.sleep(0.1)
    raise TimeoutError


def test_confere_mensagens_claras(video_vertical, video_horizontal, video_mudo, midia, tmp_path):
    ok = fluxo_react.confere(str(video_vertical), "cima")
    assert ok["modo"] == "vertical" and ok["duracao"] == pytest.approx(10, abs=0.1) and ok["largura"] == 540
    assert fluxo_react.confere(str(video_horizontal), "cima")["modo"] == "horizontal"
    r = fluxo_react.confere(str(midia["react"]), "react")
    assert r["faixa"]["escala"] == pytest.approx(1.2172339513890111) and r["duracao"] == pytest.approx(30, abs=0.1)
    assert "não está mais" in fluxo_react.confere(str(tmp_path / "sumiu.mp4"))["erro"]
    txt = tmp_path / "nota.txt"; txt.write_text("oi")
    assert "não é um vídeo" in fluxo_react.confere(str(txt))["erro"]
    falso = tmp_path / "quebrado.mp4"; falso.write_bytes(b"isto nao e video")
    assert "Não consegui ler" in fluxo_react.confere(str(falso))["erro"]
    assert "não tem som" in fluxo_react.confere(str(video_mudo), "cima")["erro"]     # o som do resultado vem de cima
    assert "erro" not in fluxo_react.confere(str(video_mudo), "react")                 # o react e' mudo no projeto


def test_quadro_em_cache(video_vertical, dados):
    a = fluxo_react.quadro(str(video_vertical), 2.0, 120)
    assert a and a.stat().st_size > 0 and a.parent.name == "cache_react_quadros"
    t = a.stat().st_mtime_ns
    assert fluxo_react.quadro(str(video_vertical), 2.0, 120) == a and a.stat().st_mtime_ns == t   # nao refaz
    assert fluxo_react.quadro(str(video_vertical), 999, 120)              # depois do fim: o ultimo quadro, sem erro
    assert fluxo_react.quadro(str(dados / "nada.txt"), 1, 120) is None


def test_constantes_iguais_ao_motor():
    c = fluxo_react.constantes()
    assert c["cobre_ate"] == react.COBRE_ATE and c["corte_padrao"] == pytest.approx(0.2375283446712018)
    assert c["headline"]["texto"] == react.HEADLINE and c["acesso"] is True


def test_gera_varios_um_erro_nao_derruba_e_reabrir_nao_duplica(video_vertical, video_horizontal, midia, dados):
    raiz = dados / "capcut"; raiz.mkdir()
    sumiu = dados / "vai sumir.mp4"; shutil.copy(video_vertical, sumiu)
    itens = [{"video": str(video_vertical), "enquadramento": {"corte": 0.1, "zoom": 1.2, "posicao": 0.5}},
             {"video": str(video_horizontal), "enquadramento": {"corte": None, "zoom": 1, "posicao": 0.2}},
             {"video": str(midia["longo"])}, {"video": str(sumiu)}]
    sumiu.unlink()
    fluxo_react.gera(str(midia["react"]), itens, raiz, variar=True)
    e = _espera()
    est = {l["numero"]: l for l in e["linhas"]}
    assert est[1]["estado"] == est[2]["estado"] == "pronto"
    assert "mais curto" in est[3]["erro"] and "não está mais" in est[4]["erro"]
    assert est[1]["projeto"] == "vertical - react" and est[2]["projeto"] == "horizontal - react"
    assert est[1]["inicio_react"] != est[2]["inicio_react"]                       # variar: cada um num ponto
    d = json.loads((raiz / "horizontal - react" / "draft_content.json").read_text(encoding="utf-8"))
    assert d["tracks"][0]["segments"][0]["clip"]["transform"]["x"] > 0           # posicao 0,2: mais a esquerda
    assert json.loads((dados / "dados" / "geracao_react.json").read_text(encoding="utf-8"))["linhas"][0]["estado"] == "pronto"
    # o app fechou e abriu de novo: a mesma geracao continua so o que falta, sem duplicar
    fluxo_react.GERACAO["job"] = None
    fluxo_react.gera(str(midia["react"]), itens, raiz, variar=True)
    _espera()
    assert sorted(p.name for p in raiz.iterdir() if p.is_dir()) == ["horizontal - react", "vertical - react"]
    # tentar de novo so o que falhou (o video voltou pro lugar)
    shutil.copy(video_vertical, sumiu)
    fluxo_react.gera(str(midia["react"]), itens, raiz, variar=True, so={4})
    e = _espera()
    assert [l["estado"] for l in e["linhas"]] == ["pronto", "pronto", "erro", "pronto"]
    assert (raiz / "vai sumir - react").is_dir()


def test_gera_com_cta_usa_o_ponto_da_tela(video_vertical, midia, dados):
    raiz = dados / "capcut"; raiz.mkdir()
    fluxo_react.gera(str(midia["react"]), [{"video": str(video_vertical), "congelar": 4.0}], raiz, cta=str(midia["cta"]))
    e = _espera()
    l = e["linhas"][0]
    assert l["estado"] == "pronto" and l["congelar"]["us"] == 4_000_000
    assert l["duracao"] == pytest.approx(13, abs=0.1)                            # o video + o CTA
    assert list((raiz / l["projeto"]).glob("*-sdr709.png"))


def test_cancelar_para_o_que_falta(video_vertical, midia, dados, monkeypatch):
    raiz = dados / "capcut"; raiz.mkdir()
    lento = react.grava
    monkeypatch.setattr(react, "grava", lambda *a, **k: (time.sleep(0.4), lento(*a, **k))[1])
    monkeypatch.setattr(fluxo_react, "PARALELO", 1)
    itens = []
    for i in range(5):
        v = dados / f"r{i}.mp4"; shutil.copy(video_vertical, v); itens.append({"video": str(v)})
    fluxo_react.gera(str(midia["react"]), itens, raiz)
    time.sleep(0.6); fluxo_react.cancela_geracao()
    e = _espera()
    est = [l["estado"] for l in e["linhas"]]
    assert "cancelado" in est and est.count("pronto") < 5 and e["cancelado"]
    assert len([p for p in raiz.iterdir() if p.is_dir()]) == est.count("pronto")  # nada pela metade


def test_ate_tres_ao_mesmo_tempo(video_vertical, midia, dados, monkeypatch):
    raiz = dados / "capcut"; raiz.mkdir()
    agora, pico = [0], [0]
    monta = react.monta
    def conta(*a, **k):
        agora[0] += 1; pico[0] = max(pico[0], agora[0]); time.sleep(0.3)
        try: return monta(*a, **k)
        finally: agora[0] -= 1
    monkeypatch.setattr(react, "monta", conta)
    itens = []
    for i in range(6):
        v = dados / f"p{i}.mp4"; shutil.copy(video_vertical, v); itens.append({"video": str(v)})
    fluxo_react.gera(str(midia["react"]), itens, raiz)
    e = _espera()
    assert e["prontos"] == 6 and pico[0] == 3


def test_pausas_em_segundo_plano(video_vertical, dados):
    fluxo_react.PAUSAS.update(itens={}, fila=[], thread=None, whisper=None)
    v = str(video_vertical)
    fluxo_react.pede_pausas([v], None)                   # sem motor de transcricao: so a pausa da fala
    fim = time.time() + 30
    while fluxo_react.estado_pausas([v])["itens"][v]["estado"] not in ("pronto", "erro") and time.time() < fim:
        time.sleep(0.1)
    it = fluxo_react.estado_pausas([v])["itens"][v]
    assert it["estado"] == "pronto" and it["boa"] is False and it["t"] == pytest.approx(5.5, abs=0.05)   # sem pausa na janela


def test_fechou_entre_gravar_e_anotar_nao_duplica(video_vertical, midia, dados):
    """o app fechou depois de gravar o projeto e antes de anotar "pronto": o nome previsto ja esta na lista do CapCut,
    entao conta como feito. Pasta pela metade (fora da lista do CapCut) sai e e' refeita com o mesmo nome."""
    raiz = dados / "capcut"; raiz.mkdir()
    vs = []
    for i in range(2):
        v = dados / f"f{i}.mp4"; shutil.copy(video_vertical, v); vs.append(v)
    itens = [{"video": str(v)} for v in vs]
    fluxo_react.gera(str(midia["react"]), itens, raiz); _espera()
    arq = dados / "dados" / "geracao_react.json"
    d = json.loads(arq.read_text(encoding="utf-8"))
    d["linhas"][0].update(estado="gravando", projeto=None, previsto="f0 - react")         # gravou, nao anotou
    shutil.rmtree(raiz / "f1 - react"); (raiz / "f1 - react").mkdir()                   # pela metade, fora da lista
    reg = json.loads((raiz / "root_meta_info.json").read_text(encoding="utf-8"))
    reg["all_draft_store"] = [x for x in reg["all_draft_store"] if not x["draft_fold_path"].endswith("f1 - react")]
    (raiz / "root_meta_info.json").write_text(json.dumps(reg), encoding="utf-8")
    d["linhas"][1].update(estado="gravando", projeto=None, previsto="f1 - react")
    arq.write_text(json.dumps(d), encoding="utf-8")
    fluxo_react.GERACAO["job"] = None
    fluxo_react.gera(str(midia["react"]), itens, raiz); e = _espera()
    assert [l["projeto"] for l in e["linhas"]] == ["f0 - react", "f1 - react"]
    assert sorted(p.name for p in raiz.iterdir() if p.is_dir()) == ["f0 - react", "f1 - react"]
    assert (raiz / "f1 - react" / "draft_content.json").exists()
