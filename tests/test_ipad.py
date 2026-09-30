"""Apresentador + iPad: sincronia, cortes iguais nos dois trilhos, ordem das faixas, legenda/headline e verificacao."""
import copy, json, os
from pathlib import Path
import pytest
from clipay import audio, capcut, ipad, palavras, processa, transcricao


def test_janela_da_sincronia_positiva_negativa_e_sem_cruzamento():
    assert ipad.janela(9.1, 204.7, 209.6) == (0.0, 9.1, pytest.approx(200.5))     # projeto 0930: iPad comecou 9,1 s antes
    sp, si, comum = ipad.janela(-1.5, 60, 60)                                        # a pessoa comecou antes
    assert (sp, si, comum) == (1.5, 0.0, 58.5)
    with pytest.raises(capcut.ErroProjeto, match="quase não se cruzam"):
        ipad.janela(59.5, 60, 60)


def test_passo_de_um_quadro_alcanca_o_ajuste_do_0930():
    quadros = round(9.1 / ipad.QUADRO)                                              # arrastando/avancando quadro a quadro
    assert abs(quadros * ipad.QUADRO - 9.1) < 1 / 60                                  # margem de 1 quadro do original (60 fps)


def test_grupos_de_2_a_4_palavras_so_do_que_ficou():
    pal = [{"t": t, "a": a, "b": a + 0.3} for t, a in
           (("você", 0.0), ("vai", 0.35), ("ter", 0.7), ("que", 1.05), ("mapear", 1.4), ("isso", 3.0), ("aqui", 3.35))]
    keep = [[0.0, 1.8, False], [2.9, 3.8, False]]
    g = ipad.grupos(pal, keep)
    assert [x["txt"] for x in g] == ["você vai ter que", "mapear", "isso aqui"]      # pausa grande separa; "mapear" isolado
    assert g[1]["fim"] <= g[2]["ini"] and g[2]["ini"] == pytest.approx(1.9, abs=0.01)  # timeline cortada: 1,8 + (3,0 - 2,9)
    assert ipad.maiusculas(" você  vai ") == "VOCÊ VAI"


@pytest.fixture
def an(video_vertical, video_horizontal, raiz_capcut, monkeypatch):
    monkeypatch.setattr(transcricao, "modelo_pronto", lambda q="preciso": True)
    monkeypatch.setattr(transcricao, "Whisper", lambda q: None)
    monkeypatch.setattr(palavras, "transcreve", lambda w, x, p=None: [
        *palavras.espalha("isso aqui muda tudo", [[0.0, 2.0]]), *palavras.espalha("você nunca tentou", [[4.0, 5.0]])])
    vids = {"pessoa": {"video": str(video_vertical), "info": audio.probe_video(video_vertical)},
            "ipad": {"video": str(video_horizontal), "info": audio.probe_video(video_horizontal)}}
    return lambda off: processa.analisa_ipad(raiz_capcut, vids, off)


def gera(raiz, a, **op):
    base = {"headline": "Como levar um CEO para 10 mil seguidores", "grupos": a["grupos"], "zoom": True, "intensidade": 1.0,
            "pessoa": {"escala": 1.0, "x": 0.0, "y": -0.169}, "crop_ipad": [0.0, 0.11, 1.0, 0.93], "nome": "iPad teste"}
    return processa.monta_ipad(raiz, a, dict(base, **op))


def abre(raiz, nome):
    return json.loads((Path(raiz) / nome / "draft_content.json").read_text(encoding="utf-8"))


def test_dois_trilhos_com_os_mesmos_trechos_e_ipad_por_cima(raiz_capcut, an):
    a = an(1.2)                                                                       # iPad comecou 1,2 s antes
    r = gera(raiz_capcut, a)
    d = abre(raiz_capcut, r["nome"])
    assert (d["canvas_config"]["width"], d["canvas_config"]["height"]) == (1080, 1920)
    vids = [t for t in d["tracks"] if t["type"] == "video"]
    pessoa, ip = vids
    assert d["tracks"].index(ip) > d["tracks"].index(pessoa) and ip["flag"] == 2
    alvo = lambda t: [(s["target_timerange"]["start"], s["target_timerange"]["duration"]) for s in t["segments"]]
    assert alvo(pessoa) == alvo(ip) and len(pessoa["segments"]) >= 2               # cortou, e igual nos dois
    for sp_, si_ in zip(pessoa["segments"], ip["segments"]):
        assert si_["source_timerange"]["start"] - sp_["source_timerange"]["start"] == 1_200_000   # sincronia em us
        assert si_["common_keyframes"] == [] and si_["clip"]["scale"]["x"] == 1.0              # iPad nunca tem zoom
    mats = {m["id"]: m for m in d["materials"]["videos"]}
    m_ip = mats[ip["segments"][0]["material_id"]]
    assert m_ip["path"].endswith("horizontal.mp4") and m_ip["crop"]["upper_left_y"] == 0.11
    assert ip["segments"][0]["clip"]["transform"]["y"] == pytest.approx(1 - ipad.altura_ipad(a["ipad"]["info"], [0, 0.11, 1, 0.93]), abs=1e-5)
    assert any(s["clip"]["scale"]["x"] > 1.0 for s in pessoa["segments"])             # zoom so na pessoa
    assert ipad.verifica(d) == []


def test_sincronia_negativa(raiz_capcut, an):
    r = gera(raiz_capcut, an(-1.5))
    d = abre(raiz_capcut, r["nome"])
    pessoa, ip = [t for t in d["tracks"] if t["type"] == "video"]
    for sp_, si_ in zip(pessoa["segments"], ip["segments"]):
        assert sp_["source_timerange"]["start"] - si_["source_timerange"]["start"] == 1_500_000


def test_legenda_e_headline_nas_posicoes_da_referencia(raiz_capcut, an):
    r = gera(raiz_capcut, an(0.0), headline_s=7.0)
    d = abre(raiz_capcut, r["nome"])
    txt = {m["id"]: m for m in d["materials"]["texts"]}
    textos = [(s, txt[s["material_id"]]) for t in d["tracks"] if t["type"] == "text" for s in t["segments"]]
    head = [(s, m) for s, m in textos if m["font_resource_id"] != ipad.FONTE_LEGENDA["id"]]
    leg = [(s, m) for s, m in textos if m["font_resource_id"] == ipad.FONTE_LEGENDA["id"]]
    s, m = head[0]
    assert s["target_timerange"] == {"start": 0, "duration": 7_000_000}
    assert s["clip"]["transform"]["y"] == ipad.Y_HEADLINE and "\n" in json.loads(m["content"])["text"]
    assert leg and all(json.loads(m["content"])["text"].isupper() for _, m in leg)
    assert all(s["clip"]["transform"]["y"] == ipad.Y_LEGENDA for s, _ in leg)
    assert all(m["border_width"] == 0 and m["has_shadow"] for _, m in leg)


def test_zoom_desligado(raiz_capcut, an):
    r = gera(raiz_capcut, an(0.0), zoom=False)
    d = abre(raiz_capcut, r["nome"])
    pessoa = [t for t in d["tracks"] if t["type"] == "video"][0]
    assert all(s["clip"]["scale"]["x"] == 1.0 and not s["common_keyframes"] for s in pessoa["segments"])


def test_verificacao_trava_source_alem_do_arquivo_e_ordem_errada(raiz_capcut, an, monkeypatch):
    a = an(1.2)
    real = processa.ipad.monta
    guardado = {}
    monkeypatch.setattr(processa.ipad, "monta", lambda *x, **k: guardado.setdefault("r", real(*x, **k)))
    gera(raiz_capcut, a)
    d, _ = guardado["r"]
    q = copy.deepcopy(d)
    ip = [t for t in q["tracks"] if t["type"] == "video"][1]
    ip["segments"][-1]["source_timerange"]["start"] += 60_000_000                     # passa do fim do arquivo do iPad
    assert any("passa do fim do arquivo" in e for e in ipad.verifica(q))
    q = copy.deepcopy(d)
    vids = [t for t in q["tracks"] if t["type"] == "video"]
    i, j = q["tracks"].index(vids[0]), q["tracks"].index(vids[1])
    q["tracks"][i], q["tracks"][j] = q["tracks"][j], q["tracks"][i]
    assert any("atrás da pessoa" in e or "mesmos trechos" in e for e in ipad.verifica(q))
    # e a gravacao trava de verdade
    monkeypatch.setattr(processa.ipad, "verifica", lambda d: ["trecho do vídeo do iPad passa do fim do arquivo"])
    antes = set(os.listdir(raiz_capcut))
    with pytest.raises(capcut.ErroProjeto, match="NÃO foi gravado"):
        gera(raiz_capcut, a, nome="nao deve existir")
    assert set(os.listdir(raiz_capcut)) == antes


def test_previa_leve_em_h264_com_o_mesmo_tempo(video_horizontal, tmp_path):
    p = ipad.gera_previa(video_horizontal, tmp_path / "previa.mp4", com_audio=False)
    i = audio.probe_video(p)
    assert abs(i["duracao"] - audio.probe_video(video_horizontal)["duracao"]) < 0.1 and max(i["largura"], i["altura"]) == 854


def test_transcricao_em_segundo_plano_e_recortada_pela_sincronia(an, video_vertical, video_horizontal, raiz_capcut):
    # transcricao feita no video INTEIRO da pessoa (tempos absolutos) antes da sincronia
    prontas = [{"t": "antes", "a": 0.2, "b": 0.5}, {"t": "isso", "a": 1.6, "b": 1.9}, {"t": "aqui", "a": 2.0, "b": 2.3}]
    vids = {"pessoa": {"video": str(video_vertical), "info": audio.probe_video(video_vertical)},
            "ipad": {"video": str(video_horizontal), "info": audio.probe_video(video_horizontal)}}
    a = processa.analisa_ipad(raiz_capcut, vids, -1.5, {}, None, palavras_prontas=prontas)    # pessoa comecou 1,5 s antes
    assert [p["t"] for p in a["palavras"]] == ["isso", "aqui"]                                   # "antes" ficou fora da janela
    assert a["palavras"][0]["a"] == pytest.approx(0.1)                                          # 1,6 - 1,5: relativo a janela
