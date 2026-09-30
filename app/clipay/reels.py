"""Modo REELS: corte seco sem respiracao, zoom punch-in pro lado do rosto e headline fixa no topo
(estilo medido no "0925 - corte" e no "0925 (3) - corte")."""
import copy, json, re
from pathlib import Path
import numpy as np
from .audio import SR, H, FPS, analisa, runs, porta_de, tira
from . import capcut
from .vlog import eh_broll, takes_broll, duplicados

K, SOFT_REL, MAXEXT, G, P0, P1, R, ISO, CURTO, GAP_PICOTADO = 8.0, -1.0, 0.30, 0.10, 0.04, 0.02, 0.25, 0.5, 0.6, 0.5


def regua(e, v, dur):
    n = len(e); porta = porta_de(e, v)
    tom = (v > 0.42) & (e > porta)
    sust = tom.copy()
    for k in (1, 2): sust[:-k] &= tom[k:]
    fala = sust | (e > porta + K)
    soft = e > porta + SOFT_REL; mx = int(MAXEXT / H); ext = fala.copy()
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


def divide_longos(e, v, keep, MAX=5.5):
    """pedaco > 5,5s e' partido numa MICROPAUSA do meio (troca de enquadramento). Sem pausa, nao parte."""
    porta = porta_de(e, v); out = []
    for a, b in keep:
        fila = [[a, b, False]]
        while any(q - p > MAX and len(r) == 1 for p, q, *r in fila):
            nv = []
            for p, q, f, *r in fila:
                if r or q - p <= MAX: nv.append([p, q, f, True]); continue
                i0, i1 = int((p + 0.20 * (q - p)) / H), int((p + 0.85 * (q - p)) / H)
                i1 = min(i1, len(e))
                j = i0 + int(np.argmin(e[i0:i1])) if i1 > i0 else None
                if j is None or e[j] >= porta: nv.append([p, q, f, True]); continue
                cut = round(j * H * FPS) / FPS
                nv += [[p, cut, f], [cut, q, True]]
            fila = nv
        out += [[p, q, f] for p, q, f, *_ in fila]
    return out


def plano(itens, inicio=None, fim=None, progresso=None):
    nomes = [(m.get("material_name", ""), s["target_timerange"]["duration"], x) for s, m, x in itens]
    dup = duplicados(nomes) if len(nomes) > 1 else set()
    out = []
    for i, ((s, m, x), (nm, d_us, _)) in enumerate(zip(itens, nomes)):
        dur = d_us / 1e6; src0 = s["source_timerange"]["start"] / 1e6
        if nm in dup and i > 0:
            out.append({"clip": nm, "tipo": "duplicado", "dur": dur, "keep": []}); continue
        if eh_broll(x):
            keep = [[a, b, False] for a, b in takes_broll(dur)]; tipo = "broll"
        else:
            tipo = "fala"
            e, v = analisa(x)
            keep = divide_longos(e, v, regua(e, v, dur))
        keep = [[round(src0 + p[0], 4), round(src0 + min(p[1], dur), 4), p[2]] for p in keep]
        if i == 0 and inicio is not None: keep = tira(keep, [[0, inicio]])
        if i == len(itens) - 1 and fim is not None: keep = tira(keep, [[fim, 1e9]])
        out.append({"clip": nm, "tipo": tipo, "dur": dur, "keep": keep})
        if progresso: progresso(i + 1, len(itens))
    return out


# ---------------- zoom ----------------
ESTATICO = [(1.190, -0.056), (1.226, 0.091), (1.251, 0.0), (1.226, 0.0), (1.228, 0.161), (1.150, 0.131)]
EMPURRAO = [(1.203, 0.0), (1.251, 0.111), (1.264, 0.127)]
INTERVALO = [3, 2, 4, 4, 3, 3, 4]


def x_do_rosto(s, x_ref, rosto):
    if rosto == "esquerda": return (s - 1) - 0.005
    if rosto == "direita": return -((s - 1) - 0.005)
    return max(-(s - 1) + 0.02, min((s - 1) - 0.02, x_ref))


def plano_zoom(pecas, rosto="centro", intensidade=1.0):
    """intensidade: 1.0 = tabelas aprovadas; 0 = sem zoom; escala o quanto cada zoom passa de 1.0"""
    if intensidade <= 0: return [None] * len(pecas)
    z = [None] * len(pecas); prox = 0; nz = 0; ie = 0; iv = 0; ult = -9
    for i, (dur, forca) in enumerate(pecas):
        if i - ult == 1: continue
        if not (i >= prox or forca): continue
        if nz == 0 and dur < 1.5: continue
        if (nz % 3 == 0 or forca) and dur >= 1.5:
            s, x = EMPURRAO[(nz // 3) % len(EMPURRAO)]; tipo = "empurra"
        else:
            s, x = ESTATICO[ie % len(ESTATICO)]; ie += 1; tipo = "fixo"
        s, x = 1 + (s - 1) * intensidade, x * intensidade
        z[i] = (tipo, s, x_do_rosto(s, x, rosto))
        nz += 1; ult = i; prox = i + INTERVALO[iv % len(INTERVALO)]; iv += 1
    return z


def kf(prop, t0, t1, v0, v1):
    return {"id": capcut.uid(), "material_id": "", "property_type": prop, "keyframe_list": [
        {"id": capcut.uid(), "curveType": "Line", "time_offset": t, "left_control": {"x": 0.0, "y": 0.0},
         "right_control": {"x": 0.0, "y": 0.0}, "values": [val], "string_value": "", "graphID": ""}
        for t, val in ((t0, v0), (t1, v1))]}


# ---------------- headline ----------------
def quebra_2_linhas(txt):
    if "\n" in txt: return "\n".join(" ".join(l.split()) for l in txt.split("\n"))
    txt = " ".join(txt.split())
    if len(txt) <= 22: return txt
    esp = [m.start() for m in re.finditer(" ", txt)]
    best = min(esp, key=lambda k: (max(k, len(txt) - k - 1), k > len(txt) - k - 1))
    return txt[:best] + "\n" + txt[best + 1:]


def carrega_tpl(cache_efeitos=None):
    """modelo da headline (fonte Classic). O caminho da fonte e' ajustado pro cache do CapCut
    desta maquina; se a fonte ainda nao foi baixada, fica so o id e o CapCut resolve."""
    tpl = json.loads((Path(__file__).parent / "assets" / "headline_tpl.json").read_text(encoding="utf-8"))
    fid = "7545362071773367568"
    caminho = ""
    if cache_efeitos:
        achados = sorted(Path(cache_efeitos).glob(f"{fid}/*/*.ttf"))
        if achados: caminho = str(achados[0]).replace("\\", "/")
    t = tpl["texto"]
    t["font_path"] = caminho
    for f in t.get("fonts", []): f["path"] = caminho
    c = t["content"] if isinstance(t["content"], dict) else json.loads(t["content"])
    for st in c.get("styles", []):
        if "font" in st: st["font"]["path"] = caminho
    t["content"] = c
    return tpl


def headline(mats, tpl, texto, total):
    tm = copy.deepcopy(tpl["texto"]); tm["id"] = capcut.uid()
    c = copy.deepcopy(tm["content"]) if isinstance(tm["content"], dict) else json.loads(tm["content"])
    c["text"] = texto
    for st in c["styles"]: st["range"] = [0, len(texto)]
    tm["content"] = json.dumps(c, ensure_ascii=False)
    mats.setdefault("texts", []).append(tm)
    an = copy.deepcopy(tpl["animacao"]); an["id"] = capcut.uid()
    mats.setdefault("material_animations", []).append(an)
    sg = copy.deepcopy(tpl["segmento"]); sg["id"] = capcut.uid(); sg["material_id"] = tm["id"]
    sg["extra_material_refs"] = [an["id"]]; sg["target_timerange"] = {"start": 0, "duration": total}
    return {"id": capcut.uid(), "type": "text", "segments": [sg], "flag": 0, "attribute": 0, "name": "", "is_default_name": True}


def montar(draft, pl, texto, tpl, rosto="centro", intensidade=1.0):
    novo = copy.deepcopy(draft); mats = novo["materials"]
    idx = capcut.indice_materiais(mats)
    vt = capcut.trilha_principal(novo)
    segs = sorted(vt["segments"], key=lambda s: s["target_timerange"]["start"])
    assert len(segs) == len(pl)
    lista = [(s, p) for s, pp in zip(segs, pl) for p in pp["keep"]]
    zooms = plano_zoom([(p[1] - p[0], p[2]) for _, p in lista], rosto, intensidade)
    novos, cur = [], 0
    for (s, p), z in zip(lista, zooms):
        ns = capcut.clona_segmento(s, idx, mats)
        A, B = int(round(p[0] * 1e6)), int(round(p[1] * 1e6))
        ns["source_timerange"] = {"start": A, "duration": B - A}
        ns["target_timerange"] = {"start": cur, "duration": B - A}
        clip = ns.get("clip") or {"scale": {"x": 1.0, "y": 1.0}, "rotation": 0.0, "transform": {"x": 0.0, "y": 0.0},
                                  "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0}
        base_s = clip["scale"]["x"]; base_x = clip["transform"]["x"]; base_y = clip["transform"]["y"]
        ns["common_keyframes"] = []
        if z:
            tipo, sc, dx = z
            clip["scale"] = {"x": base_s * sc, "y": base_s * sc}; clip["transform"]["x"] = base_x + dx
            if tipo == "empurra":
                t0, t1 = A, B - int(1e6 / FPS)
                ns["common_keyframes"] = [kf("KFTypePositionX", t0, t1, base_x, base_x + dx),
                                          kf("KFTypePositionY", t0, t1, base_y, base_y),
                                          kf("KFTypeScaleX", t0, t1, base_s, base_s * sc),
                                          kf("KFTypeRotation", t0, t1, 0.0, 0.0)]
                ns["uniform_scale"] = {"on": True, "value": 1.0}
        ns["clip"] = clip
        novos.append(ns); cur += B - A
    vt["segments"] = novos; novo["duration"] = cur
    novo["tracks"] = ([t for t in novo["tracks"] if t is vt] +
                      [t for t in novo["tracks"] if t is not vt and t["type"] != "text"])
    for t in novo["tracks"]:
        if t is not vt: t["segments"] = [x for x in t["segments"] if x["target_timerange"]["start"] < cur]
    if texto: novo["tracks"].append(headline(mats, tpl, texto, cur))
    capcut.poda(novo)
    return novo, zooms, capcut.verifica(novo)
