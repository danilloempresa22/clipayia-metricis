"""Tempo por palavra sem modelo de alinhamento: o audio e' dividido nos trechos de fala (pausas >= 250 ms, a mesma
regua do corte), os trechos sao agrupados em blocos curtos pro Whisper, e as palavras de cada bloco sao espalhadas
pelo tempo de fala do bloco proporcionalmente ao tamanho de cada palavra. O limite dos cortes vem do audio (exato);
o instante de cada palavra dentro de um trecho e' aproximado."""
import numpy as np
from . import audio
from .legenda import CORTE_MIN

BLOCO_MAX = 8.0                      # s por chamada do Whisper (curto: tempo mais preciso; nao curto demais: menos alucinacao)
FALA_MIN = 0.08                      # trecho de fala mais curto que isso e' ruido


def trechos_de_fala(x):
    """[[a,b]] em s: onde tem voz. Pausas menores que CORTE_MIN nao separam."""
    e, v = audio.analisa(x)
    porta = audio.porta_de(e, v)
    fala = audio.tom_sustentado(e, v, porta) | (e > porta + 8.0)
    rs = [[a * audio.H, b * audio.H] for a, b in audio.runs(fala)]
    out = []
    for a, b in rs:
        if out and a - out[-1][1] < CORTE_MIN:
            out[-1][1] = b
        else:
            out.append([a, b])
    return [[round(a, 3), round(b, 3)] for a, b in out if b - a >= FALA_MIN]


def blocos(trechos, maximo=BLOCO_MAX):
    out = []
    for t in trechos:
        if out and t[1] - out[-1][0][0] <= maximo:
            out[-1].append(t)
        else:
            out.append([t])
    return out


def espalha(texto, trechos):
    """palavras do texto distribuidas pelos trechos de fala, proporcional ao numero de letras"""
    pal = texto.split()
    if not pal or not trechos:
        return []
    peso = np.array([len(p) + 1 for p in pal], float)
    fim_rel = np.cumsum(peso) / peso.sum()
    ini_rel = np.concatenate([[0.0], fim_rel[:-1]])
    dur = np.array([b - a for a, b in trechos]); acum = np.concatenate([[0.0], np.cumsum(dur)]); total = acum[-1]

    def tempo(f):                    # fracao do tempo de FALA -> instante real (pula as pausas)
        s = f * total
        k = min(int(np.searchsorted(acum, s, side="right")) - 1, len(trechos) - 1)
        return trechos[k][0] + (s - acum[k])

    out = []
    for p, a, b in zip(pal, ini_rel, fim_rel):
        ta, tb = tempo(a + 1e-9), tempo(b - 1e-9)
        out.append({"t": p, "a": round(float(ta), 3), "b": round(float(max(tb, ta + 0.05)), 3)})
    return out


def transcreve(w, x, progresso=None):
    """[{"t","a","b"}] em s, em ordem"""
    bs = blocos(trechos_de_fala(x))
    out = []
    for i, bl in enumerate(bs):
        a, b = bl[0][0], bl[-1][1]
        ia, ib = int(max(0.0, a - 0.05) * audio.SR), int((b + 0.05) * audio.SR)
        txt = w.texto(x[ia:ib]) if ib > ia else ""
        out += espalha(txt, bl)
        if progresso: progresso(i + 1, len(bs))
    return out
