"""Apresentador + iPad: sincronia, cortes que nunca cortam palavra, clipe composto cortado por fora, headline e verificacao."""
import copy, json, os
from pathlib import Path
import pytest
from clipay import audio, capcut, composto, ipad, palavras, processa, transcricao


def test_janela_da_sincronia_positiva_negativa_e_sem_cruzamento():
    assert ipad.janela(9.1, 204.7, 209.6) == (0.0, 9.1, pytest.approx(200.5))     # projeto 0930: iPad comecou 9,1 s antes
    sp, si, comum = ipad.janela(-1.5, 60, 60)                                        # a pessoa comecou antes
    assert (sp, si, comum) == (1.5, 0.0, 58.5)
    with pytest.raises(capcut.ErroProjeto, match="quase não se cruzam"):
        ipad.janela(59.5, 60, 60)


def test_passo_de_um_quadro_alcanca_o_ajuste_do_0930():
    quadros = round(9.1 / ipad.QUADRO)
    assert abs(quadros * ipad.QUADRO - 9.1) < 1 / 60                                  # margem de 1 quadro do original (60 fps)


def test_cortes_nunca_cortam_palavra_e_respeitam_a_intensidade(video_vertical):
    x = audio.pcm(video_vertical)                        # tom em 0-3 s, 4,5-7,5 s e 9-10 s (pausas de 1,5 s)
    # palavra "sussurrada" no meio da pausa: o audio nao ve, a transcricao ve -> nao pode sumir
    pal = [{"t": "baixinho", "a": 3.5, "b": 3.9}]
    for k in ipad.INTENSIDADES:
        keep = ipad.cortes(x, pal, k)
        assert any(a <= 3.5 and 3.9 <= b for a, b, _ in keep), k
    leve, forte = ipad.cortes(x, [], "leve"), ipad.cortes(x, [], "forte")
    assert sum(b - a for a, b, _ in leve) >= sum(b - a for a, b, _ in forte)
    assert len(forte) >= 2                                                           # pausas de 1,5 s viram corte
    pausa, pre, pos = ipad.INTENSIDADES["media"]
    k = ipad.cortes(x, [], "media")
    assert k[0][1] >= 3.0 + pos - 0.02                                                # folga depois da fala


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
    base = {"headline": "Como levar um CEO para 10 mil seguidores", "cortes": "forte", "zoom": True, "intensidade": 1.0,
            "pessoa": {"escala": 1.0, "x": 0.0, "y": -0.169}, "crop_ipad": [0.0, 0.11, 1.0, 0.93], "nome": "iPad teste"}
    return processa.monta_ipad(raiz, a, dict(base, **op))


def abre(raiz, nome):
    p = Path(raiz) / nome
    return json.loads((p / "draft_content.json").read_text(encoding="utf-8")), p


def test_composto_sincronizado_cortado_por_fora(raiz_capcut, an):
    a = an(1.2)                                                                       # iPad comecou 1,2 s antes
    r = gera(raiz_capcut, a)
    d, pasta = abre(raiz_capcut, r["nome"])
    assert (d["canvas_config"]["width"], d["canvas_config"]["height"]) == (1080, 1920)
    ents = d["materials"]["drafts"]
    assert len(ents) == 1                                                             # um composto, na raiz
    c = ents[0]["draft"]
    assert c["materials"].get("drafts", []) == [] and (pasta / "subdraft" / c["id"] / "draft_content.json").exists()
    # dentro do composto: pessoa embaixo e iPad por cima, os dois INTEIROS e sincronizados
    pessoa, ip = [t for t in c["tracks"] if t["type"] == "video"]
    assert pessoa["flag"] == 0 and ip["flag"] == 2 and c["tracks"].index(ip) > c["tracks"].index(pessoa)
    assert len(ip["segments"]) == 1 and ip["segments"][0]["source_timerange"]["start"] == 1_200_000
    assert pessoa["segments"][0]["source_timerange"]["start"] == 0
    fim = lambda t: t["segments"][-1]["target_timerange"]["start"] + t["segments"][-1]["target_timerange"]["duration"]
    assert fim(pessoa) == fim(ip) == c["duration"]
    assert ip["segments"][0]["common_keyframes"] == [] and ip["segments"][0]["clip"]["scale"]["x"] == 1.0   # iPad sem zoom
    assert any(s["clip"]["scale"]["x"] > 1.0 for s in pessoa["segments"])             # zoom so na pessoa
    # raiz: os cortes sao segmentos do MESMO composto, cada um com material proprio
    raizv = d["tracks"][0]["segments"]
    assert len(raizv) >= 2 and len({s["material_id"] for s in raizv}) == len(raizv)
    assert all(s["extra_material_refs"][0] == ents[0]["id"] for s in raizv)
    assert r["depois"] < r["antes"]
    assert ipad.verifica(d, pasta) == []


def test_sincronia_negativa(raiz_capcut, an):
    r = gera(raiz_capcut, an(-1.5))
    d, _ = abre(raiz_capcut, r["nome"])
    c = d["materials"]["drafts"][0]["draft"]
    pessoa, ip = [t for t in c["tracks"] if t["type"] == "video"]
    assert pessoa["segments"][0]["source_timerange"]["start"] == 1_500_000 and ip["segments"][0]["source_timerange"]["start"] == 0


def test_headline_no_comeco_e_sem_legenda(raiz_capcut, an):
    r = gera(raiz_capcut, an(0.0), headline_s=7.0)
    d, _ = abre(raiz_capcut, r["nome"])
    textos = [t for t in d["tracks"] if t["type"] == "text"]
    assert len(textos) == 1 and len(textos[0]["segments"]) == 1                      # so a headline, nenhuma legenda
    s = textos[0]["segments"][0]
    assert s["target_timerange"] == {"start": 0, "duration": 7_000_000} and s["clip"]["transform"]["y"] == ipad.Y_HEADLINE
    c = d["materials"]["drafts"][0]["draft"]
    assert not c["materials"].get("texts")


def test_zoom_desligado(raiz_capcut, an):
    r = gera(raiz_capcut, an(0.0), zoom=False)
    d, _ = abre(raiz_capcut, r["nome"])
    pessoa = d["materials"]["drafts"][0]["draft"]["tracks"][0]
    assert all(s["clip"]["scale"]["x"] == 1.0 and not s["common_keyframes"] for s in pessoa["segments"])


def test_verificacao_trava_source_alem_do_arquivo_e_ordem_errada(raiz_capcut, an, monkeypatch):
    a = an(1.2)
    real = processa.ipad.monta
    guardado = {}
    monkeypatch.setattr(processa.ipad, "monta", lambda *x, **k: guardado.setdefault("r", real(*x, **k)))
    gera(raiz_capcut, a)
    raiz_d = guardado["r"][0]
    q = copy.deepcopy(raiz_d)
    ip = [t for t in q["materials"]["drafts"][0]["draft"]["tracks"] if t["type"] == "video"][1]
    ip["segments"][0]["source_timerange"]["start"] += 60_000_000                    # passa do fim do arquivo do iPad
    assert any("passa do fim do arquivo" in e for e in ipad.verifica(q))
    q = copy.deepcopy(raiz_d)
    ts = q["materials"]["drafts"][0]["draft"]["tracks"]
    ts[0], ts[1] = ts[1], ts[0]
    assert any("atrás da pessoa" in e for e in ipad.verifica(q))
    q = copy.deepcopy(raiz_d)
    q["tracks"][0]["segments"][-1]["source_timerange"]["duration"] += 60_000_000    # corte alem do composto
    assert any("passa do fim do clipe composto" in e for e in ipad.verifica(q))
    monkeypatch.setattr(processa.ipad, "verifica", lambda d, p=None: ["trecho do vídeo do iPad passa do fim do arquivo"])
    antes = set(os.listdir(raiz_capcut))
    with pytest.raises(capcut.ErroProjeto, match="NÃO foi gravado"):
        gera(raiz_capcut, a, nome="nao deve existir")
    assert set(os.listdir(raiz_capcut)) == antes


def test_previa_leve_em_h264_com_o_mesmo_tempo(video_horizontal, tmp_path):
    p = ipad.gera_previa(video_horizontal, tmp_path / "previa.mp4", com_audio=False)
    i = audio.probe_video(p)
    assert abs(i["duracao"] - audio.probe_video(video_horizontal)["duracao"]) < 0.1 and max(i["largura"], i["altura"]) == 854


def test_transcricao_em_segundo_plano_e_recortada_pela_sincronia(video_vertical, video_horizontal, raiz_capcut):
    prontas = [{"t": "antes", "a": 0.2, "b": 0.5}, {"t": "isso", "a": 1.6, "b": 1.9}, {"t": "aqui", "a": 2.0, "b": 2.3}]
    vids = {"pessoa": {"video": str(video_vertical), "info": audio.probe_video(video_vertical)},
            "ipad": {"video": str(video_horizontal), "info": audio.probe_video(video_horizontal)}}
    a = processa.analisa_ipad(raiz_capcut, vids, -1.5, {}, None, palavras_prontas=prontas)    # pessoa comecou 1,5 s antes
    assert [p["t"] for p in a["palavras"]] == ["isso", "aqui"]
    assert a["palavras"][0]["a"] == pytest.approx(0.1)
    assert set(a["keeps"]) == set(ipad.INTENSIDADES)
