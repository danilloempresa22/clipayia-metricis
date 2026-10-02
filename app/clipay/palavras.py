"""Tempo por palavra sem modelo de alinhamento dedicado:
1) o audio e' dividido nos trechos de fala (pausas >= 250 ms, a mesma regua do corte — limite exato, vem do audio);
2) os trechos sao agrupados em blocos de ate 25 s e o Whisper transcreve cada bloco COM marcas de tempo (20 ms),
   o que prende cada frase curta (~2 s) no seu lugar;
3) dentro de cada frase, as palavras sao espalhadas so pelo tempo de fala, proporcional ao tamanho de cada palavra.
Medido contra a legenda automatica do CapCut (tempo real por palavra) em 4 videos: erro mediano ~100-140 ms,
2-4% das palavras com erro > 0,5 s (o metodo antigo, sem marcas de tempo, errava > 0,5 s em ate 23%)."""
import numpy as np
from . import audio
from .legenda import CORTE_MIN

BLOCO_MAX = 25.0                     # s por chamada do Whisper (a janela dele e' 30 s)
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


def recorta(trechos, a, b):
    """trechos de fala dentro de [a,b] (a frase que o Whisper marcou); sem fala dentro, a frase inteira"""
    r = [[max(x, a), min(y, b)] for x, y in trechos if min(y, b) - max(x, a) > 0.02]
    return r or [[a, b]]


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


def transcreve(w, x, progresso=None, ao_texto=None):
    """[{"t","a","b"}] em s, em ordem. ao_texto(ini, texto): avisa cada frase assim que sai (so pra mostrar na tela)."""
    from .transcricao import CRONO
    with CRONO("achar fala"):
        bs = blocos(trechos_de_fala(x))
    out = []
    for i, bl in enumerate(bs):
        a, b = max(0.0, bl[0][0] - 0.05), bl[-1][1] + 0.05
        for s0, s1, txt in (w.segmentos(x[int(a * audio.SR):int(b * audio.SR)]) if b > a else []):
            if ao_texto: ao_texto(a + s0, txt)
            with CRONO("mapear"):
                s0, s1 = a + s0, a + min(s1, b - a)
                if s1 > s0:
                    out += espalha(txt, recorta(bl, s0, s1))
        if progresso: progresso(i + 1, len(bs))
    return sorted(out, key=lambda p: p["a"])
