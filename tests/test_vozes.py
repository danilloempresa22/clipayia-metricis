"""Quem fala: agrupamento global das vozes, locutor por frase, palpite do apresentador e cache por janela
(impressao de voz falsa: o teste nao baixa o modelo)."""
import numpy as np
import pytest
from clipay import longo, transcricao, vozes


def vozes_falsas(n, rng, centro):
    return centro + 0.25 * rng.standard_normal((n, len(centro)))


def test_agrupa_duas_vozes_com_rotulo_igual_no_video_todo():
    rng = np.random.default_rng(1)
    ca, cb = rng.standard_normal(192), rng.standard_normal(192)
    # intercaladas no tempo, como numa conversa: o rotulo depende da voz, nao da posicao
    emb = np.vstack([vozes_falsas(30, rng, ca), vozes_falsas(10, rng, cb), vozes_falsas(30, rng, ca), vozes_falsas(10, rng, cb),
                     vozes_falsas(1, rng, rng.standard_normal(192))])           # 1 ruido (risada): vai pra um dos dois
    lab = vozes.agrupa(emb, np.full(len(emb), 2.0))
    assert len(set(lab)) == 2
    assert set(lab[:30]) == set(lab[40:70]) == {0}                               # quem mais fala = 0 = "A"
    assert set(lab[30:40]) == set(lab[70:80]) == {1}


def test_locutor_da_frase_e_quem_mais_fala_nela():
    seg = np.array([[0, 3], [3, 4], [5, 8], [10, 12]], np.float32); lab = np.array([0, 1, 1, 0])
    fs = [{"ini": 0, "fim": 4}, {"ini": 4.5, "fim": 8}, {"ini": 8.5, "fim": 9}]
    assert vozes.locutor_das_frases(fs, seg, lab) == ["A", "B", "B"]              # a 3a nao tem pedaco: o mais perto


def test_palpite_do_apresentador_por_vez_de_falar():
    fs, locs = [], []
    t = 0.0
    for k in range(10):                                                       # B pergunta e passa a palavra; A responde
        for txt, l, d in (("E como foi isso?", "B", 3), ("Foi assim, cara.", "A", 20), ("Sabe por quê?", "A", 2),
                          ("Porque eu quis.", "A", 20)):
            fs.append({"ini": t, "fim": t + d, "texto": txt}); locs.append(l); t += d
    p = vozes.apresentador(fs, locs)
    assert p["letra"] == "B" and p["confianca"] > 0.5                          # a pergunta retorica do A nao engana
    r = vozes.rotula({"frases": fs[:2]}, np.array([[0, 3], [3, 23]], np.float32),
                     np.vstack([np.ones(192), -np.ones(192)]).astype(np.float32), apresentador_letra="A")
    assert r["apresentador"] == "A" and r["frases"][0]["papel"] == "convidado"   # trocar o palpite por parametro


def test_identifica_por_janela_com_cache_e_retomada(video_horizontal, video_vertical, tmp_path, monkeypatch):
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: tmp_path)
    monkeypatch.setattr(longo, "JANELA", 4.5); monkeypatch.setattr(longo, "BUSCA", 1.0); monkeypatch.setattr(longo, "MARGEM", 0.5)

    class W:
        def segmentos(self, x): return [(0.0, len(x) / 16000, "fala")]
    longo.transcreve(video_horizontal, W(), paralelo=1)

    class Imp:
        n = 0
        def __call__(self, x):
            Imp.n += 1; return np.ones(192, np.float32)
    seg, emb = vozes.identifica(video_horizontal, imp=Imp())
    n1 = Imp.n
    assert n1 > 0 and len(seg) == n1 and emb.shape == (n1, 192)
    assert all(b - a <= vozes.PEDACO_MAX + 1e-3 for a, b in seg)
    seg2, _ = vozes.identifica(video_horizontal, imp=Imp())                     # de novo: tudo do cache
    assert Imp.n == n1 and np.allclose(seg, seg2)
    pasta = longo.pasta_cache(video_horizontal, "preciso")
    vozes._arq(pasta, 1).unlink()                                               # "fechou no meio": falta 1 janela
    vozes.identifica(video_horizontal, imp=Imp())
    assert 0 < Imp.n - n1 < n1                                                  # so a que faltava
    with pytest.raises(RuntimeError, match="transcrição"):
        vozes.identifica(video_vertical, imp=Imp())                             # sem transcricao: nao inventa voz
