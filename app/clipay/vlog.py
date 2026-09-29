"""Modo VLOG / aula: so corte. Regua SECA (aprovada no "Advisor Ale 1 - corte v2") com zonas soltas
perto de fala fraca, b-roll em takes curtos e clipe duplicado fora."""
import copy
import numpy as np
from .audio import (SR, H, FPS, analisa, runs, porta_de, nivel_voz, tom_sustentado, dil, mudo,
                    uniao, inter, fora_de, tira)
from . import capcut

SECA = dict(NEAR=0.12, SOFT_REL=0.0, MAXEXT=0.08, GAP_PICOTADO=0.8)
SOLTA = dict(NEAR=None, SOFT_ABS=10.0, MAXEXT=0.30, GAP_PICOTADO=1.5)


def regua_ev(e, v, dur, NEAR=None, SOFT_REL=None, SOFT_ABS=None, MAXEXT=0.30, K=4.0, G=0.20, P0=0.04,
             P1=0.06, R=0.25, ISO=1.0, CURTO=0.6, GAP_PICOTADO=1.5):
    n = len(e); porta = porta_de(e, v)
    sust = tom_sustentado(e, v, porta)
    energia = e > porta + K
    if NEAR is not None:
        energia &= dil(sust, int(NEAR / H))       # energia sem tom longe da voz = respiracao / sala
    fala = sust | energia
    soft = e > (porta + SOFT_REL if SOFT_REL is not None else min(SOFT_ABS, porta))
    mx = int(MAXEXT / H); ext = fala.copy()
    for a, b in runs(fala):
        i = a
        while i > 0 and a - i < mx and soft[i - 1]: i -= 1
        j = b
        while j < n and j - b < mx and soft[j]: j += 1
        ext[i:j] = True
    rs = [[a * H, b * H] for a, b in runs(ext)]
    if not rs: return [[0.0, dur]]
    lim = []
    for k, (a, b) in enumerate(rs):
        ant = a - rs[k - 1][1] if k else 9; dep = rs[k + 1][0] - b if k + 1 < len(rs) else 9
        if b - a < R and ant > ISO and dep > ISO: continue
        lim.append([a, b])
    if not lim: return [[0.0, dur]]
    g = [lim[0][:]]
    for a, b in lim[1:]:
        if a - g[-1][1] < G: g[-1][1] = b
        else: g.append([a, b])
    out = []
    for a, b in g:
        a, b = max(0.0, a - P0), min(dur, b + P1)
        a, b = float(np.floor(a * FPS) / FPS), float(min(dur, np.ceil(b * FPS) / FPS))
        if out and a <= out[-1][1] + 1e-6: out[-1][1] = max(out[-1][1], b)
        else: out.append([a, b])
    mud = True
    while mud:
        mud = False
        for k in range(len(out) - 1):
            (a, b), (c, d) = out[k], out[k + 1]
            if c - b < GAP_PICOTADO and (b - a < CURTO or d - c < CURTO):
                out[k] = [a, d]; del out[k + 1]; mud = True; break
    return out


def zonas_soltas(e, v, margem=1.5, rel=-6.0):
    porta = porta_de(e, v); nivel = nivel_voz(e, v)
    fala = tom_sustentado(e, v, porta) | (e > porta + 4.0)
    U = runs(fala)
    if not U: return []
    M = [list(U[0])]
    for a, b in U[1:]:
        if a - M[-1][1] < 15: M[-1][1] = b
        else: M.append([a, b])
    return uniao([a * H - margem, b * H + margem] for a, b in M
                 if b - a >= 20 and np.percentile(e[a:b], 75) < nivel + rel)


def cortes_respiro(e, v, keep, zonas, MIN=0.40, POS=0.10, PRE=0.06):
    n = len(e); sust = tom_sustentado(e, v, porta_de(e, v))
    kept = np.zeros(n, bool)
    for a, b in keep: kept[int(round(a / H)):min(n, int(round(b / H)))] = True
    rem = []
    for a, b in runs(kept & ~sust):
        if a == 0 or b >= n or not kept[a - 1] or not kept[b]: continue
        if (b - a) * H < MIN: continue
        r0, r1 = a * H + POS, b * H - PRE
        if any(r0 < z1 and z0 < r1 for z0, z1 in zonas): continue
        r0, r1 = float(np.ceil(r0 * FPS) / FPS), float(np.floor(r1 * FPS) / FPS)
        if r1 - r0 >= 0.15: rem.append([r0, r1])
    return rem


def filtra_picotado(keep, rem, CURTO=0.6):
    ok = []
    for r in sorted(rem):
        cur = tira(keep, ok); teste = tira(keep, ok + [r])
        if len(teste) == len(cur) + 1 and sum(b - a < CURTO for a, b in teste) <= sum(b - a < CURTO for a, b in cur):
            ok.append(r)
    return ok


def regua(x, dur):
    e, v = analisa(x)
    Z = zonas_soltas(e, v)
    Zc = [[max(0.0, a), min(dur, b)] for a, b in Z]
    keep = uniao(inter(regua_ev(e, v, dur, **SECA), fora_de(Z, dur)) + inter(regua_ev(e, v, dur, **SOLTA), Zc))
    return tira(keep, filtra_picotado(keep, cortes_respiro(e, v, keep, Z)))


def eh_broll(x):
    if sum(b - a for a, b in mudo(x)) > 0.9 * len(x) / SR: return True
    e, v = analisa(x)
    cand = (v > 0.42) & (e > 8.0)
    nivel = float(np.median(e[cand])) if cand.any() else 0.0
    voz = float(((v > 0.42) & (e > porta_de(e, v))).mean())
    return voz < 0.05 or (voz < 0.13 and nivel < 15.0)


def takes_broll(dur, frac=0.25, take=2.5):
    n = int(min(8, max(1, round(dur * frac / take))))
    if dur <= take + 0.5: return [[0.0, round(min(dur, take), 4)]]
    passo = (dur - take) / max(1, n - 1) if n > 1 else 0
    return [[round(k * passo, 4), round(k * passo + take, 4)] for k in range(n)]


def duplicados(clips):
    """clips: [(nome, dur_us, x)] -> nomes repetidos (mesmo take importado 2x)"""
    fora = set()
    for i in range(len(clips)):
        for j in range(i + 1, len(clips)):
            (ni, di, xi), (nj, dj, xj) = clips[i], clips[j]
            if ni in fora or nj in fora or abs(di - dj) > 40_000: continue
            m = min(len(xi), len(xj))
            if m > SR and np.std(xi[:m]) > 0 and np.std(xj[:m]) > 0 and np.corrcoef(xi[:m], xj[:m])[0, 1] > 0.7:
                fora.add(nj)
    return fora


def plano(itens, progresso=None):
    """itens: [(segmento, material, audio)] -> [{clip, tipo, dur, keep}] com keep em s da ORIGEM"""
    nomes = [(m.get("material_name", ""), s["target_timerange"]["duration"], x) for s, m, x in itens]
    dup = duplicados(nomes) if len(nomes) > 1 else set()
    out = []
    for i, ((s, m, x), (nm, d_us, _)) in enumerate(zip(itens, nomes)):
        dur = d_us / 1e6; src0 = s["source_timerange"]["start"] / 1e6
        if nm in dup and i > 0: tipo, keep = "duplicado", []
        elif eh_broll(x): tipo, keep = "broll", takes_broll(dur)
        else:
            tipo = "fala"
            keep = regua(x, dur)
            mz = mudo(x)
            if mz:
                for a, b in mz:
                    if b - a <= 4.0: keep.append([float(np.floor(a * FPS) / FPS), float(np.ceil(b * FPS) / FPS)])
                    else: keep += [[a + p, a + q] for p, q in takes_broll(b - a)]
                keep = uniao(keep)
        keep = [[round(src0 + a, 4), round(src0 + min(b, dur), 4)] for a, b in keep if min(b, dur) - a > 0.05]
        out.append({"clip": nm, "tipo": tipo, "dur": dur, "keep": keep})
        if progresso: progresso(i + 1, len(itens))
    return out


def montar(draft, pl):
    novo = copy.deepcopy(draft); mats = novo["materials"]
    idx = capcut.indice_materiais(mats)
    vt = capcut.trilha_principal(novo)
    segs = sorted(vt["segments"], key=lambda s: s["target_timerange"]["start"])
    assert len(segs) == len(pl)
    novos, cur = [], 0
    for s, p in zip(segs, pl):
        for a, b in p["keep"]:
            ns = capcut.clona_segmento(s, idx, mats)
            A, B = int(round(a * 1e6)), int(round(b * 1e6))
            ns["source_timerange"] = {"start": A, "duration": B - A}
            ns["target_timerange"] = {"start": cur, "duration": B - A}
            novos.append(ns); cur += B - A
    vt["segments"] = novos; novo["duration"] = cur
    for t in novo["tracks"]:
        if t is not vt: t["segments"] = [x for x in t["segments"] if x["target_timerange"]["start"] < cur]
    capcut.poda(novo)
    return novo, capcut.verifica(novo)
