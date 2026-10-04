"""Criacao de projeto CapCut do zero a partir de video bruto (o coracao do produto)."""
import json, os
from pathlib import Path
import pytest
from clipay import audio, capcut, processa


def le(raiz, nome):
    p = Path(raiz) / nome
    return json.loads((p / "draft_content.json").read_text(encoding="utf-8")), p


def test_probe_le_dimensoes_e_audio(video_vertical, video_mudo):
    i = audio.probe_video(video_vertical)
    assert (i["largura"], i["altura"]) == (540, 960)
    assert abs(i["duracao"] - 10) < 0.2 and i["tem_audio"]
    assert not audio.probe_video(video_mudo)["tem_audio"]


def test_cria_draft_vertical_passa_na_verificacao(video_vertical):
    d, meta = capcut.cria_draft(video_vertical, audio.probe_video(video_vertical))
    assert (d["canvas_config"]["width"], d["canvas_config"]["height"]) == (1080, 1920)
    m = d["materials"]["videos"][0]
    assert m["path"].endswith("vertical.mp4") and m["material_name"] == "vertical.mp4"
    assert (m["width"], m["height"]) == (540, 960)
    seg = d["tracks"][0]["segments"][0]
    assert seg["material_id"] == m["id"] and seg["target_timerange"]["duration"] == m["duration"] == d["duration"]
    assert meta["draft_materials"][0]["value"][0]["id"] == m["local_material_id"]
    assert capcut.verifica(d) == []


def test_cria_draft_horizontal_usa_canvas_horizontal(video_horizontal):
    d, _ = capcut.cria_draft(video_horizontal, audio.probe_video(video_horizontal))
    assert (d["canvas_config"]["width"], d["canvas_config"]["height"]) == (1920, 1080)


def test_ids_novos_a_cada_projeto(video_vertical):
    i = audio.probe_video(video_vertical)
    a, _ = capcut.cria_draft(video_vertical, i)
    b, _ = capcut.cria_draft(video_vertical, i)
    assert a["id"] != b["id"] and a["materials"]["videos"][0]["id"] != b["materials"]["videos"][0]["id"]


def test_moldes_nao_vazam_ids_da_maquina_original():
    for nome in ("vertical", "horizontal"):
        d = json.loads((capcut.MOLDES / nome / "draft_content.json").read_text(encoding="utf-8"))
        assert d["platform"]["device_id"] == d["platform"]["mac_address"] == ""


def test_processa_video_reels_ponta_a_ponta(video_vertical, raiz_capcut):
    r = processa.processa_video(raiz_capcut, video_vertical, "reels", {"headline": "VOCE PRECISA VER ISSO ANTES DE POSTAR"})
    assert r["depois"] < r["antes"]                       # cortou os silencios
    assert r["pedacos"] >= 2 and r["headline"].count("\n") == 1
    d, pasta = le(raiz_capcut, r["nome"])
    assert capcut.verifica(d) == []
    assert (pasta / "draft_meta_info.json").exists()
    assert any(t["type"] == "text" for t in d["tracks"])  # headline
    # registrado no indice do CapCut, com o projeto antigo intacto
    idx = json.loads((Path(raiz_capcut) / "root_meta_info.json").read_text(encoding="utf-8"))
    assert r["nome"] in [x["draft_name"] for x in idx["all_draft_store"]]
    assert (Path(raiz_capcut) / "0918 (1)" / "draft_content.json").exists()


def test_nome_ja_existente_nao_sobrescreve(video_vertical, raiz_capcut):
    a = processa.processa_video(raiz_capcut, video_vertical, "reels", {})["nome"]
    b = processa.processa_video(raiz_capcut, video_vertical, "reels", {})["nome"]
    assert a != b and (Path(raiz_capcut) / a).is_dir() and (Path(raiz_capcut) / b).is_dir()


def test_video_sem_audio_avisa_e_nao_grava(video_mudo, raiz_capcut):
    antes = set(os.listdir(raiz_capcut))
    with pytest.raises(capcut.ErroProjeto, match="áudio"):
        processa.processa_video(raiz_capcut, video_mudo, "reels", {})
    assert set(os.listdir(raiz_capcut)) == antes


def test_capcut_criptografado_avisa_e_nao_grava(video_vertical, raiz_capcut):
    (Path(raiz_capcut) / "0918 (1)" / "draft_content.json").write_bytes(os.urandom(4096))
    antes = set(os.listdir(raiz_capcut))
    with pytest.raises(capcut.ErroProjeto, match="criptografado"):
        processa.processa_video(raiz_capcut, video_vertical, "reels", {})
    assert set(os.listdir(raiz_capcut)) == antes


def test_arquivo_vazio_nao_e_acusado_como_criptografia(tmp_path):
    f = tmp_path / "draft_content.json"; f.write_bytes(b"")
    with pytest.raises(capcut.ErroProjeto, match="vazio"):
        capcut.le_draft(f)
    f.write_bytes(b'{"tracks": [')
    with pytest.raises(capcut.ErroProjeto, match="corrompido"):
        capcut.le_draft(f)


def test_falha_no_meio_nao_deixa_pasta_pela_metade(video_vertical, raiz_capcut, monkeypatch):
    def quebra(*a, **k): raise capcut.ErroProjeto("boom")
    monkeypatch.setattr(capcut, "registra", quebra)
    antes = set(os.listdir(raiz_capcut))
    with pytest.raises(capcut.ErroProjeto):
        processa.processa_video(raiz_capcut, video_vertical, "reels", {})
    assert set(os.listdir(raiz_capcut)) == antes
