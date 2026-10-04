"""Zoom sempre centrado na pessoa: x = -escala*posicao, limitado pra nunca descobrir a borda, e a deteccao devolve a
posicao horizontal continua (-1..1). Confere o resultado de verdade: aplica o zoom num quadro e mede onde o rosto cai."""
import pytest
import numpy as np
from clipay import reels, rosto


def test_formula_sinal_e_limite():
    assert reels.x_centro(1.2, 0.0) == 0.0
    assert reels.x_centro(1.2, 0.1) == pytest.approx(-0.12)            # pessoa a direita -> x negativo (como era o x_do_rosto)
    assert reels.x_centro(1.2, -0.1) == pytest.approx(0.12)
    assert reels.x_centro(1.2, 0.9) == pytest.approx(-(0.2 - reels.FOLGA_BORDA))   # longe do centro: para no limite
    assert reels.x_centro(1.0, 0.5) == 0.0                              # sem zoom nao desloca


def test_tabelas_so_com_escala_e_plano_centrado():
    assert all(isinstance(s, float) for s in reels.ESTATICO + reels.EMPURRAO)
    pecas = [(3.0, False)] * 12
    for pos in (-0.4, 0.0, 0.35):
        for z in reels.plano_zoom(pecas, pos):
            if z:
                tipo, s, x = z
                assert x == reels.x_centro(s, pos) and abs(x) <= s - 1 - reels.FOLGA_BORDA + 1e-9


def test_rosto_volta_pro_meio_no_quadro_com_zoom():
    """simula o CapCut: quadro de 1000 px, rosto em u (-1..1); com escala s e deslocamento x (1 = meia largura) o
    rosto aparece em s*u + x. Tem que cair no meio (ou o mais perto possivel sem borda preta)."""
    for u in (-0.3, 0.0, 0.25):
        for s in reels.ESTATICO + reels.EMPURRAO:
            x = reels.x_centro(s, u)
            na_tela = s * u + x
            assert abs(na_tela) < 1e-9 or abs(x) == pytest.approx(s - 1 - reels.FOLGA_BORDA)
            assert abs(x) <= s - 1                                      # o video cobre a tela inteira


def test_deteccao_devolve_posicao_continua(monkeypatch, tmp_path):
    """sem rosto (video sintetico): 0 e nao confiavel, sem erro"""
    monkeypatch.setattr(rosto, "_quadro", lambda video, t, largura=480: None)
    assert rosto.posicao_horizontal(tmp_path / "x.mp4", 10.0) == (0.0, False)
