"""Transcricao em pacote: varios takes num audio unico, janelas de ate 28 s, texto de volta pro take certo, cache,
b-roll, duplicado, cancelar."""
import subprocess, wave
from pathlib import Path
import numpy as np
import pytest
from clipay import audio, pacote, palavras, transcricao


def grava_wav(p, dur, falas, freq=220.0):
    """'fala' = tom com vibrato (a deteccao de voz pega tom sustentado), resto = silencio quase total"""
    sr = audio.SR; t = np.arange(int(dur * sr)) / sr
    x = np.random.default_rng(1).normal(0, 1e-4, len(t))
    for a, b in falas:
        m = (t >= a) & (t < b)
        x[m] += 0.3 * np.sin(2 * np.pi * (freq + 8 * np.sin(2 * np.pi * 5 * t[m])) * t[m])
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return p


class WhisperFalso:
    """um segmento cobrindo o bloco inteiro, texto 'falaN' com N = numero da chamada (pra rastrear)"""
    def __init__(self):
        self.chamadas = 0; self.duracoes = []

    def segmentos(self, x):
        self.chamadas += 1; self.duracoes.append(len(x) / audio.SR)
        return [(0.0, len(x) / audio.SR, f"fala{self.chamadas} ok")]


@pytest.fixture(autouse=True)
def cache_isolado(tmp_path, monkeypatch):
    d = tmp_path / "dados"; d.mkdir()
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: d)


@pytest.fixture
def takes(tmp_path):
    return {
        "curto": grava_wav(tmp_path / "curto.wav", 3.0, [[0.5, 2.5]]),
        "mudo": grava_wav(tmp_path / "mudo.wav", 6.0, []),
        "fim": grava_wav(tmp_path / "fim.wav", 8.0, [[1.0, 3.0], [7.1, 7.95]], freq=300),   # fala no ultimo segundo
        "longo": grava_wav(tmp_path / "longo.wav", 20.0, [[0.5, 6.0], [7.0, 13.0], [14.0, 19.5]], freq=180),
    }


def test_cada_texto_no_seu_take_e_take_mudo_pulado(takes):
    w = WhisperFalso(); andamento = []
    ordem = [takes["curto"], takes["mudo"], takes["fim"], takes["longo"]]
    r = pacote.transcreve_takes(w, ordem, usar_cache=False, progresso=lambda k, n: andamento.append((k, n)))
    pal = {Path(k).name: v for k, v in r["palavras"].items()}
    assert r["tipos"][str(takes["mudo"])] == "broll" and pal["mudo.wav"] == []
    assert w.chamadas == r["blocos"] and max(w.duracoes) <= palavras.BLOCO_MAX + 0.2    # take mudo nao chama o Whisper
    assert andamento[-1] == (r["blocos"], r["blocos"]) and [k for k, _ in andamento] == sorted(k for k, _ in andamento)
    for nome, falas in (("curto.wav", [[0.5, 2.5]]), ("fim.wav", [[1.0, 3.0], [7.1, 7.95]]),
                        ("longo.wav", [[0.5, 6.0], [7.0, 13.0], [14.0, 19.5]])):
        assert pal[nome], nome
        for p in pal[nome]:                                    # cada palavra comeca no tempo da ORIGEM, numa fala
            assert any(a - 0.3 <= p["a"] <= b + 0.3 for a, b in falas), (nome, p)
    assert any(p["b"] > 7.5 for p in pal["fim.wav"])          # a fala do ultimo segundo nao some


def test_take_duplicado_reaproveita_o_texto(takes, tmp_path):
    copia = tmp_path / "copia.wav"; copia.write_bytes(Path(takes["fim"]).read_bytes())
    w = WhisperFalso()
    r = pacote.transcreve_takes(w, [takes["fim"], copia], usar_cache=False)
    assert r["tipos"][str(copia)] == "duplicado"
    assert r["palavras"][str(copia)] == r["palavras"][str(takes["fim"])] and w.chamadas == 1


def test_reordenar_usa_o_cache_e_mantem_cada_texto_no_seu_take(takes):
    w = WhisperFalso()
    a = pacote.transcreve_takes(w, [takes["curto"], takes["fim"], takes["longo"]])
    n = w.chamadas
    b = pacote.transcreve_takes(w, [takes["longo"], takes["curto"], takes["fim"]])
    assert w.chamadas == n                                       # nada transcrito de novo
    assert set(b["tipos"].values()) == {"cache"}
    assert all(a["palavras"][k] == b["palavras"][k] for k in a["palavras"])


def test_cancelar_no_meio(takes):
    w = WhisperFalso(); vezes = {"n": 0}
    def cancelado():
        vezes["n"] += 1
        return vezes["n"] > 2                                   # deixa ler 2 arquivos e para
    with pytest.raises(pacote.Cancelado):
        pacote.transcreve_takes(w, [takes["curto"], takes["fim"], takes["longo"]], cancelado=cancelado)
    assert w.chamadas == 0
    vivos = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ffmpeg.exe"], capture_output=True, text=True).stdout
    assert "ffmpeg.exe" not in vivos                            # nao sobra processo


def test_cancelar_entre_dois_blocos(takes):
    w = WhisperFalso()
    def cancelado():
        return w.chamadas >= 1                                    # o 1o bloco roda, o resto para
    with pytest.raises(pacote.Cancelado):
        pacote.transcreve_takes(w, [takes["longo"], takes["fim"]], cancelado=cancelado)
    assert w.chamadas == 1
    assert not list((transcricao.pasta_dados() / "cache_transcricao").glob("*.json"))   # nada pela metade no cache


def test_arquivo_sem_trilha_de_audio(tmp_path):
    v = tmp_path / "sem_audio.mp4"
    subprocess.run([audio.ffmpeg_bin(), "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=320x240:d=2:r=30",
                    "-c:v", "libopenh264", str(v)], check=True, **audio._sem_janela())
    r = pacote.transcreve_takes(WhisperFalso(), [v], usar_cache=False)
    assert r["tipos"][str(v)] == "broll" and r["palavras"][str(v)] == []
