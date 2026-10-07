"""Modo REELS: corte seco sem respiracao, zoom punch-in pro lado do rosto e headline fixa no topo
(estilo medido no "0925 - corte" e no "0925 (3) - corte")."""
import copy, json, re
from pathlib import Path
import numpy as np
from .audio import SR, H, FPS, analisa, runs, porta_de, tira
from . import capcut
from .vlog import eh_broll, takes_broll, duplicados

K, SOFT_REL, MAXEXT, G, P0, P1, R, ISO, CURTO, GAP_PICOTADO = 8.0, -1.0, 0.30, 0.10, 0.04, 0.02, 0.25, 0.5, 0.6, 0.5
INICIO_FOLGA = 0.01                  # s antes da fala em que o trecho comeca (Cortes + Headline). Medido no "edit ale 1":
                                     # a pessoa puxou o comeco 2 quadros pra frente em 15 de 25 trechos; com 10 ms a regra
                                     # tira o mesmo ~1 s e fica no maximo 1 quadro mais justa que a escolha dela
VELOCIDADE = 1.13                    # a mesma do Cortes de podcast, do iPad e da Rotina


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


def fala_estrita(e, v):
    """quadro a quadro: onde ha voz de verdade (sem a extensao suave da regua)"""
    porta = porta_de(e, v)
    tom = (v > 0.42) & (e > porta)
    sust = tom.copy()
    for k in (1, 2): sust[:-k] &= tom[k:]
    return sust | (e > porta + K)


def aperta_inicios(e, v, keep, folga=INICIO_FOLGA):
    """o comeco de cada trecho vai pra perto de onde a voz comeca (folga s antes, na grade de quadros).
    So puxa pra frente (nunca come fala) e nao mexe em trecho onde a voz demora a aparecer."""
    fala = fala_estrita(e, v); out = []
    for p in keep:
        a, b = p[0], p[1]
        i = int(a / H)
        while i < len(fala) and i * H < b and not fala[i]: i += 1
        alvo = float(np.floor((i * H - folga) * FPS + 1e-6) / FPS)
        out.append([max(a, alvo) if a < alvo < b - 0.1 else a, b] + list(p[2:]))
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
            keep = aperta_inicios(e, v, divide_longos(e, v, regua(e, v, dur)))
        keep = [[round(src0 + p[0], 4), round(src0 + min(p[1], dur), 4), p[2]] for p in keep]
        if i == 0 and inicio is not None: keep = tira(keep, [[0, inicio]])
        if i == len(itens) - 1 and fim is not None: keep = tira(keep, [[fim, 1e9]])
        out.append({"clip": nm, "tipo": tipo, "dur": dur, "keep": keep})
        if progresso: progresso(i + 1, len(itens))
    return out


# ---------------- zoom ----------------
ESTATICO = [1.190, 1.226, 1.251, 1.226, 1.228, 1.150]      # so a escala: o unico deslocamento e' o da pessoa
EMPURRAO = [1.203, 1.251, 1.264]
INTERVALO = [3, 2, 4, 4, 3, 3, 4]
FOLGA_BORDA = 0.02                   # nunca encosta no limite (borda preta)


def x_centro(s, posicao):
    """deslocamento que traz a pessoa (posicao -1..1 no quadro) pro meio da tela num zoom de escala s.
    Unidade do CapCut: 1 = meia largura da tela. Na escala s a pessoa aparece em s*posicao, entao x = -s*posicao
    (pessoa a direita -> x negativo). Limitado a +-(s-1-folga): o video nunca descobre a borda."""
    lim = max(0.0, (s - 1) - FOLGA_BORDA)
    return round(max(-lim, min(lim, -posicao * s)), 6)


def plano_zoom(pecas, posicao=0.0, intensidade=1.0):
    """zoom sempre centrado na pessoa (posicao: rosto.posicao_horizontal; 0 = centro ou nao detectado).
    intensidade: 1.0 = tabelas aprovadas; 0 = sem zoom; escala o quanto cada zoom passa de 1.0"""
    if intensidade <= 0: return [None] * len(pecas)
    z = [None] * len(pecas); prox = 0; nz = 0; ie = 0; iv = 0; ult = -9
    for i, (dur, forca) in enumerate(pecas):
        if i - ult == 1: continue
        if not (i >= prox or forca): continue
        if nz == 0 and dur < 1.5: continue
        if (nz % 3 == 0 or forca) and dur >= 1.5:
            s = EMPURRAO[(nz // 3) % len(EMPURRAO)]; tipo = "empurra"
        else:
            s = ESTATICO[ie % len(ESTATICO)]; ie += 1; tipo = "fixo"
        s = 1 + (s - 1) * intensidade
        z[i] = (tipo, s, x_centro(s, posicao))
        nz += 1; ult = i; prox = i + INTERVALO[iv % len(INTERVALO)]; iv += 1
    return z


def kf(prop, t0, t1, v0, v1):
    return {"id": capcut.uid(), "material_id": "", "property_type": prop, "keyframe_list": [
        {"id": capcut.uid(), "curveType": "Line", "time_offset": t, "left_control": {"x": 0.0, "y": 0.0},
         "right_control": {"x": 0.0, "y": 0.0}, "values": [val], "string_value": "", "graphID": ""}
        for t, val in ((t0, v0), (t1, v1))]}


# ---------------- sobras: tropeco (frase recomecada) e conversa no final ----------------
_LIMPA = re.compile(r"[^\wà-ÿ]+", re.I)
CORRIGE = ("quer dizer", "ou melhor", "melhor dizendo", "desculpa", "desculpe", "perdão", "errei", "falar de novo")
CORRIGE_CURTA = ("não pode", "nao pode", "de novo", "pera", "peraí", "calma", "não, não", "nao, nao")   # so em frase curta
CURTA = 5                                                                                         # palavras
FECHO = {"fechou", "boa", "beleza", "valeu", "perfeito", "show", "isso", "entendeu", "tranquilo", "ok", "obrigado",
         "obrigada", "tchau", "falou", "certo", "massa", "top", "demais", "pronto"}


def _norm(t):
    return _LIMPA.sub("", t.lower())


def _fim_de_frase(t):
    return t.strip().rstrip("\"'”’)»").endswith((".", "!", "?", "…"))


def frases_de(pal):
    """as palavras do transcritor viram frases com tempo (fecha no ponto final ou numa pausa longa)"""
    out, cur = [], []
    for i, w in enumerate(pal):
        cur.append(w)
        prox = pal[i + 1] if i + 1 < len(pal) else None
        if prox is None or _fim_de_frase(w["t"]) or prox["a"] - w["b"] >= 0.8 or len(cur) >= 28:
            out.append({"a": cur[0]["a"], "b": cur[-1]["b"], "t": " ".join(x["t"] for x in cur), "i0": i - len(cur) + 1, "i1": i})
            cur = []
    return out


def sobras(pal):
    """trechos que parecem sobrar, pra pessoa CONFIRMAR na revisao (nada sai sozinho):
    tropeco = a pessoa se corrigiu ("Da substantivo, nao pode."): sai a frase do tropeco, ate a fala seguinte comecar
    final   = conversa depois do conteudo: frases curtas de fechamento no fim ("Fechou? Fechou. Boa!")
    Palavra repetida NAO conta: o transcritor junta a repeticao do recomeco ("adjetivo, adjetivo" vira um so) e,
    numa conversa, repetir e' quase sempre enfase ("bizarro, bizarro"; medido no podcast de 10 min: 3 falsos alarmes)."""
    fr = frases_de(pal); out = []
    fim = []
    for f in reversed(fr):
        ws = [_norm(x) for x in f["t"].split()]
        if ws and len(ws) <= 3 and (any(w in FECHO for w in ws) or len(ws) <= 1):
            fim.insert(0, f)
        else:
            break
    if len(fim) == len(fr): fim = []
    for n, f in enumerate(fr[:len(fr) - len(fim)]):
        baixo = f["t"].lower()
        corrige = any(c in baixo for c in CORRIGE) or (len(baixo.split()) <= CURTA and any(c in baixo for c in CORRIGE_CURTA))
        if corrige:                                    # a frase inteira, ate a proxima comecar
            b = fr[n + 1]["a"] if n + 1 < len(fr) else f["b"]
            out.append({"tipo": "tropeco", "a": round(f["a"], 3), "b": round(b, 3), "texto": f["t"]})
    if fim:                                            # comeca logo depois da ultima frase do conteudo (leva o respiro)
        ant = fr[len(fr) - len(fim) - 1]["b"]
        out.append({"tipo": "final", "a": round(max(ant + 0.05, fim[0]["a"] - 1.0), 3), "b": round(fim[-1]["b"] + 0.3, 3),
                    "texto": " ".join(f["t"] for f in fim)})
    return [o for o in out if o["b"] - o["a"] >= 0.3]


def tira_trechos(pl, regioes, encosta=0.3):
    """tira as regioes confirmadas na revisao. A borda que cai a menos de 0,3 s do comeco/fim de um trecho vai ate
    ele (o tempo das palavras e' aproximado: nao sobra um pedacinho de silaba)"""
    out = []
    for p in pl:
        keep = [list(k) for k in p["keep"]]
        rs = []
        for a, b in regioes:
            for k in keep:
                if k[0] < a < k[1] and a - k[0] <= encosta: a = k[0]
                if k[0] < b < k[1] and k[1] - b <= encosta: b = k[1]
                if abs(b - k[0]) <= encosta and b < k[0]: b = k[0]
            rs.append([a, b])
        out.append(dict(p, keep=tira(keep, rs)))
    return out


# ---------------- velocidade: tudo num clipe composto acelerado (como a pessoa fez no "edit ale 1") ----------------
def embrulha(novo, vel, nome="Vídeo"):
    """o projeto inteiro (cortes, zoom e headline) vira um clipe composto e a raiz mostra esse composto acelerado.
    Os zooms ficam dentro do composto, no tempo deles. Devolve (raiz, [entrada do composto])."""
    from . import composto, ipad
    canvas = (novo["canvas_config"]["width"], novo["canvas_config"]["height"])
    dur = novo["duration"]
    ent = composto.composto(nome, novo, canvas, dur)
    dc = ent["draft"]; dc["materials"] = copy.deepcopy(novo["materials"]); dc["tracks"] = copy.deepcopy(novo["tracks"])
    raiz = composto.esqueleto(novo); raiz["id"] = capcut.uid()
    s_v, _, porcat = composto.seg_composto(composto.MOLDE["raiz"]["corpo"], ent, raiz["materials"], dur, canvas)
    s_v["clip"] = dict(s_v["clip"], scale={"x": 1.0, "y": 1.0}, transform={"x": 0.0, "y": 0.0})
    fora = ipad._velocidade(s_v, porcat, dur, vel)
    raiz["tracks"] = [composto.trilha("trilha_video_modelo", [s_v])]
    raiz["duration"] = fora
    raiz["materials"]["drafts"] = [ent]
    return raiz, [ent]


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


def montar(draft, pl, texto, tpl, posicao=0.0, intensidade=1.0):
    novo = copy.deepcopy(draft); mats = novo["materials"]
    idx = capcut.indice_materiais(mats)
    vt = capcut.trilha_principal(novo)
    segs = sorted(vt["segments"], key=lambda s: s["target_timerange"]["start"])
    assert len(segs) == len(pl)
    lista = [(s, p) for s, pp in zip(segs, pl) for p in pp["keep"]]
    zooms = plano_zoom([(p[1] - p[0], p[2]) for _, p in lista], posicao, intensidade)
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
