"""Cortes Fase 1: um corte montado a partir do template (projeto feito a mao). Video sintetico, pasta do CapCut falsa."""
import json
import pytest
from clipay import cortes, rosto

INFO_169 = {"largura": 2560, "altura": 1440}


def test_limites_batem_com_a_referencia():
    """no projeto de referencia o empurrao do pedaco 1 termina em y = -0,2156 com s = 2,161: exatamente o limite"""
    W, H = cortes.cobertura(INFO_169, (1920, 1920))
    assert (W, H) == (1.0, 0.5625)
    x, y = cortes.enquadra(2.1610776942355883, 0.0, 1.0, W, H)
    assert y == pytest.approx(-0.2156062030075181, abs=1e-6)
    assert cortes.enquadra(1.8, 0.0, 0.0, W, H) == (0.0, 0.0)
    x, y = cortes.enquadra(2.0, -0.1, 0.0, W, H)
    assert x == pytest.approx(0.2)                                       # pessoa a esquerda -> x positivo


def test_plano_base_e_zoom_sem_borda():
    mod = cortes.modelo()
    pcs = [[i * 3.0, i * 3.0 + 2.5, False] for i in range(12)]
    zs, base, (W, H) = cortes.plano(pcs, INFO_169, (1920, 1920), mod, px=0.6, py=0.8)
    assert base == pytest.approx(1 / 0.5625 * 1.025, abs=1e-5)           # 1,822 (referencia: 1,823)
    assert any(z[0] != z[3] for z in zs) and any(z[0] == z[3] != base for z in zs)   # tem empurrao e fixo
    for z in zs:
        for s, x, y in (z[:3], z[3:]):
            assert abs(x) <= s * W - 1 and abs(y) <= s * H - 1


def test_vertical_recalcula_a_base():
    W, H = cortes.cobertura({"largura": 1080, "altura": 1920}, (1920, 1920))
    assert (W, H) == (pytest.approx(0.5625), 1.0)


def test_template_ids_novos_e_consistentes():
    a, b = cortes.carrega_template(), cortes.carrega_template()
    ea, eb = a["draft"]["materials"]["drafts"][0], b["draft"]["materials"]["drafts"][0]
    assert ea["draft"]["id"] != eb["draft"]["id"]
    assert ea["draft"]["id"] in ea["draft_file_path"] and cortes.GUID_TOKEN in ea["draft_file_path"]
    assert ea["draft"]["id"] == a["cfg"]["id"]
    tipo18 = [g for g in a["meta"]["draft_materials"] if g["type"] == 18][0]["value"][0]
    assert ea["draft"]["id"] in tipo18["file_Path"]


@pytest.fixture
def corte(video_horizontal, monkeypatch):
    monkeypatch.setattr(rosto, "posicao_2d", lambda v, a, b: (0.0, 0.0, False))
    return cortes.monta(video_horizontal, 0.5, 9.5, cache=None,
                        musica={"path": video_horizontal, "nome": "musica", "dur": 10.0})


def test_monta_corte(corte):
    d = corte["draft"]; c = d["materials"]["drafts"][0]["draft"]
    segs = c["tracks"][0]["segments"]
    assert len(segs) >= 2                                                # o silencio do meio saiu
    for p, q in zip(segs, segs[1:]):
        assert p["target_timerange"]["start"] + p["target_timerange"]["duration"] == q["target_timerange"]["start"]
        assert q["source_timerange"]["start"] >= p["source_timerange"]["start"] + p["source_timerange"]["duration"]
    assert all(500_000 - 1 <= s["source_timerange"]["start"] for s in segs)
    sc = d["tracks"][0]["segments"][0]
    assert sc["speed"] == pytest.approx(1.13, abs=0.01) and sc["volume"] == 1.0
    assert sc["clip"]["transform"]["y"] == pytest.approx(-0.128, abs=1e-3)
    assert d["duration"] == sc["target_timerange"]["duration"]
    txt = json.loads(d["materials"]["texts"][0]["content"])
    assert txt["text"] == "SUA HEADLINE AQUI\nSOBRE O SEU CORTE"
    aud = [t for t in d["tracks"] if t["type"] == "audio"][0]["segments"][0]
    assert aud["volume"] == pytest.approx(0.053, abs=1e-3)
    assert cortes.verifica(corte) == []


def test_sem_musica_tira_a_trilha(video_horizontal, monkeypatch):
    monkeypatch.setattr(rosto, "posicao_2d", lambda v, a, b: (0.0, 0.0, False))
    r = cortes.monta(video_horizontal, 0.5, 9.5)
    assert not any(t["type"] == "audio" for t in r["draft"]["tracks"])
    assert not r["draft"]["materials"]["audios"]
    assert cortes.verifica(r) == []


def test_intervalo_fora_do_video(video_horizontal):
    with pytest.raises(Exception):
        cortes.monta(video_horizontal, 5, 50)


def test_grava_em_pasta_nova_com_subdraft_igual(corte, raiz_capcut):
    nome = cortes.grava(raiz_capcut, "corte teste", corte)
    p = raiz_capcut / nome
    raiz = json.loads((p / "draft_content.json").read_text(encoding="utf-8"))
    e = raiz["materials"]["drafts"][0]; fid = e["draft"]["id"]
    sub = json.loads((p / "subdraft" / fid / "draft_content.json").read_text(encoding="utf-8"))
    assert sub["materials"]["drafts"][0]["draft"] == e["draft"]           # os dois rascunhos identicos
    assert str(p).replace("\\", "/") in sub["materials"]["drafts"][0]["draft_file_path"]
    assert (p / "subdraft" / fid / "sub_draft_config.json").exists()
    assert cortes.verifica(corte, p) == []
    assert cortes.grava(raiz_capcut, "corte teste", corte) != nome       # nunca sobrescreve


def test_sem_efeito_e_sem_velocidade(video_horizontal, monkeypatch):
    monkeypatch.setattr(rosto, "posicao_2d", lambda v, a, b: (0.0, 0.0, False))
    mod = cortes.modelo(); mod["composto"]["velocidade"] = 1.0
    r = cortes.monta(video_horizontal, 0.5, 9.5, mod=mod, efeito=False)
    d = r["draft"]; sc = d["tracks"][0]["segments"][0]
    assert not d["materials"]["video_effects"] and sc["speed"] == pytest.approx(1.0, abs=0.01)
    assert cortes.verifica(r) == []
