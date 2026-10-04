"""Cortes Fase 2: transcricao de video longo por janelas (emenda na pausa, cache, retomada, cancelar, ajuste de limite).
Video sintetico de 10 s (fala 0-3, 4,5-7,5 e 9-10 s) com janelas pequenas; o Whisper e' falso (conta as chamadas)."""
import pytest
from clipay import audio, longo, transcricao


class WhisperFalso:
    def __init__(self):
        self.chamadas = 0

    def segmentos(self, x):
        self.chamadas += 1
        return [(0.0, len(x) / audio.SR, f"fala {self.chamadas}")]


@pytest.fixture
def janelas_pequenas(tmp_path, monkeypatch):
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: tmp_path)
    monkeypatch.setattr(longo, "JANELA", 4.5)
    monkeypatch.setattr(longo, "BUSCA", 1.0)
    monkeypatch.setattr(longo, "MARGEM", 0.5)
    return tmp_path


def test_emendas_caem_nas_pausas_sem_fala_repetida(video_horizontal, janelas_pequenas):
    w = WhisperFalso()
    r = longo.transcreve(video_horizontal, w, paralelo=1)
    assert len(r["janelas"]) == 3
    for (_, fim), (ini, _) in zip(r["janelas"], r["janelas"][1:]):
        assert fim == ini                                              # colados, sem sobreposicao
    assert 3.0 < r["janelas"][0][1] < 4.5 and 7.5 < r["janelas"][1][1] < 9.0   # emendas no silencio
    fs = r["frases"]
    assert [f["id"] for f in fs] == [1, 2, 3] and w.chamadas == 3
    for f, (a, b) in zip(fs, [(0, 3), (4.5, 7.5), (9, 10)]):
        assert f["ini"] == pytest.approx(a, abs=0.15) and f["fim"] == pytest.approx(b, abs=0.15)
    for p, q in zip(fs, fs[1:]):
        assert p["fim"] <= q["ini"]
    # pausas: o silencio do meio de cada emenda vira uma pausa so
    assert any(a < 3.3 and b > 4.3 for a, b in r["pausas"]) and any(a < 7.8 and b > 8.8 for a, b in r["pausas"])


def test_cache_retoma_e_responde_na_hora(video_horizontal, janelas_pequenas):
    w = WhisperFalso(); r1 = longo.transcreve(video_horizontal, w, paralelo=1)
    w2 = WhisperFalso(); visto = []
    r2 = longo.transcreve(video_horizontal, w2, paralelo=1, progresso=visto.append)
    assert w2.chamadas == 0 and visto[-1]["do_cache"] == 3                # nada refeito
    assert [f["texto"] for f in r2["frases"]] == [f["texto"] for f in r1["frases"]]
    assert longo.resultado(video_horizontal)["frases"] == r1["frases"]


def test_cancelar_deixa_o_cache_consistente(video_horizontal, janelas_pequenas):
    w = WhisperFalso(); estados = []

    def cancela():
        return len(estados) >= 1                                          # cancela depois da 1a janela pronta
    with pytest.raises(longo.Cancelado):
        longo.transcreve(video_horizontal, w, paralelo=1, cancelado=cancela,
                         progresso=lambda e: estados.append(e) if e["janelas_prontas"] >= 1 else None)
    assert longo.resultado(video_horizontal) is None
    est = longo.estado_cache(video_horizontal)
    assert est["prontas"] == 1 and not est["completo"]
    w2 = WhisperFalso(); r = longo.transcreve(video_horizontal, w2, paralelo=1)
    assert w2.chamadas == 2 and len(r["frases"]) == 3                     # so as 2 janelas que faltavam


def test_ajusta_limite_cai_na_pausa():
    pausas = [[0.0, 0.4], [3.0, 4.5], [7.5, 7.8], [9.6, 10.0]]
    assert longo.ajusta_limite(4.6, "inicio", pausas) == pytest.approx(4.45)     # logo antes da 1a palavra
    assert longo.ajusta_limite(2.9, "fim", pausas) == pytest.approx(3.3)         # fim da fala + 0,3 s
    assert longo.ajusta_limite(7.4, "fim", pausas) == pytest.approx(7.75)        # pausa curta: nao invade a fala
    assert longo.ajusta_limite(0.5, "inicio", pausas) == pytest.approx(0.35)         # pausa logo antes
    assert longo.ajusta_limite(2.0, "inicio", pausas) == 2.0                        # sem pausa a 0,5 s: o tempo do Whisper
    assert longo.ajusta_limite(5.8, "fim", pausas) == 5.8                           # nunca pula pra pausa longe
    assert longo.ajusta_limite(3.1, "fim", pausas) == pytest.approx(3.3)             # Whisper atrasado: a pausa de verdade
    # fala baixa no meio de uma "pausa" longa (o detector nao ouviu): o corte parte do t, nao come a frase
    longa = [[10.0, 14.0]]
    assert longo.ajusta_limite(12.0, "inicio", longa) == pytest.approx(11.95)
    assert longo.ajusta_limite(12.0, "fim", longa) == pytest.approx(12.3)
    with pytest.raises(ValueError):
        longo.ajusta_limite(1.0, "meio", pausas)


def test_emenda_sem_pausa_usa_o_fim_nominal():
    assert longo.emenda([[0.0, 700.0]], 0.0, 600.0) == 600.0
    assert longo.emenda([[0.0, 570.0], [571.0, 590.0], [592.0, 700.0]], 0.0, 600.0) == pytest.approx(591.0)


def test_costura_junta_frase_partida_sem_pausa():
    fs = [[131.7, 138.44, "mas naquele momento você"], [138.44, 142.84, "ainda não tinha isso."],
          [143.43, 146.94, "Foi algo que você mudou,"], [147.5, 150.0, "outra frase"]]
    assert longo.costura(fs) == [[131.7, 142.84, "mas naquele momento você ainda não tinha isso."],
                                 [143.43, 146.94, "Foi algo que você mudou,"], [147.5, 150.0, "outra frase"]]
