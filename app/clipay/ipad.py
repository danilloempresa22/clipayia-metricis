"""Modo APRESENTADOR + iPAD: junta a camera (pessoa falando) e a gravacao de tela do iPad num projeto 1080x1920,
iPad em cima (recortado) e pessoa embaixo, sincronizados pelo usuario, cortados juntos, zoom so na pessoa,
legenda automatica e headline no inicio. Especificacao: docs/design/apresentador-ipad-especificacao.md.
Sem clipe composto (MVP): os dois trilhos sao escritos direto com a MESMA lista de trechos."""
import copy, json, subprocess, re
from pathlib import Path
from . import audio, capcut, reels, legenda, composto

# ---------------- medidas calibradas na referencia (resultado final ipad.mp4) e nas capas do CapCut ----------------
PROPORCAO_IPAD = 0.347               # altura padrao da faixa do iPad (fracao da tela)
PX_POR_EM = 94.2                     # 1080x1920, font_size 15: pixels por (em x escala), medido em 3 capas do CapCut
ESC_HEADLINE = 0.623                 # fonte Classic (molde da headline do Cortes + Headline)
Y_HEADLINE = 0.408                   # centro a 29,6% da altura (y do CapCut: 1 = topo, -1 = base)
HEADLINE_S = 7.0
FONTE_LEGENDA = {"id": "7098268696795156993", "nome": "ProximaNova Bold"}     # catalogo do CapCut
ESC_LEGENDA = 0.45                   # pela altura das maiusculas da referencia
Y_LEGENDA = -0.452                   # centro a 72,6% da altura
PAL_MIN, PAL_MAX, PAUSA_GRUPO, PAUSA_FORTE, LETRAS_MAX = 2, 4, 0.35, 0.7, 24
SEGURANCA = 1.3
QUADRO = 1 / 30                      # passo de "avancar 1 quadro" na tela de sincronia (as previas sao 30 fps)

_ASSETS = Path(__file__).resolve().parent / "assets"
_LARG = {n: json.loads((_ASSETS / f"larguras_{n}.json").read_text(encoding="utf-8")) for n in ("proximanova_bold", "classic")}


def largura_px(txt, esc, fonte):
    t = _LARG[fonte]
    return sum(t["chars"].get(c, t["padrao"]) for c in txt) * PX_POR_EM * esc


# ---------------- previa leve (so pras telas de enquadrar e sincronizar) ----------------
def gera_previa(origem, destino, lado=854, com_audio=True, avisa=None, dur=None):
    """H.264 leve, 30 fps constantes, keyframe a cada 0,5 s (pra arrastar a barra de tempo sem travar).
    O tempo da previa e' o mesmo do original (a sincronia vale pros dois). A gravacao final usa o ORIGINAL."""
    destino = Path(destino)
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    tmp = destino.with_suffix(".tmp.mp4")
    esc = f"scale='if(gt(iw,ih),{lado},-2)':'if(gt(iw,ih),-2,{lado})'"
    cmd = [audio.ffmpeg_bin(), "-v", "error", "-y", "-i", str(origem), "-vf", f"fps=30,{esc}", "-c:v", "libopenh264",
           "-b:v", "1500k", "-g", "15", "-pix_fmt", "yuv420p"]
    cmd += (["-c:a", "aac", "-b:a", "96k", "-ac", "1"] if com_audio else ["-an"])
    cmd += ["-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(tmp)]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **audio._sem_janela())
    for linha in p.stdout:
        m = re.match(rb"out_time_us=(\d+)", linha)
        if m and avisa and dur:
            avisa(min(1.0, int(m[1]) / 1e6 / dur))
    erro = p.stderr.read().decode(errors="ignore")
    if p.wait() != 0:
        tmp.unlink(missing_ok=True)
        raise capcut.ErroProjeto(f"Não consegui preparar a prévia de {Path(origem).name}: {erro[-200:]}")
    tmp.replace(destino)
    return destino


VOZ_MIN = 0.05                       # fracao minima de quadros com voz pra dizer que o video tem fala


def fracao_de_voz(video, info):
    """quanto de um trecho do meio do video tem voz. A gravacao de tela do iPad costuma ter trilha de audio MUDA,
    entao 'tem trilha de audio' nao basta pra saber qual video e' a camera."""
    if not info.get("tem_audio"):
        return 0.0
    dur = info["duracao"]; trecho = min(30.0, dur)
    x = audio.pcm(video, max(0.0, dur / 2 - trecho / 2), trecho)
    if len(x) < audio.SR or float(abs(x).max()) < 1e-4:
        return 0.0
    e, v = audio.analisa(x)
    return float(((v > 0.42) & (e > 8.0)).mean())


# ---------------- sincronia ----------------
def janela(offset, dur_pessoa, dur_ipad):
    """offset = t_ipad - t_pessoa (s) no mesmo momento. Devolve (inicio na pessoa, inicio no iPad, duracao em comum)."""
    sp, si = max(0.0, -offset), max(0.0, offset)
    comum = min(dur_pessoa - sp, dur_ipad - si)
    if comum < 1.0:
        raise capcut.ErroProjeto("Com essa sincronia os dois vídeos quase não se cruzam. Confira o ajuste na tela de sincronia.")
    return sp, si, comum


# ---------------- cortes e legenda ----------------
def cortes(x):
    """mesma regua de silencio do Cortes + Headline, no audio da pessoa (s relativos ao inicio da janela)"""
    e, v = audio.analisa(x)
    return reels.divide_longos(e, v, reels.regua(e, v, len(x) / audio.SR))


def grupos(palavras, keep):
    """frases curtas (2-4 palavras) na timeline CORTADA; palavra que caiu num corte nao entra"""
    f, total = legenda.mapa_tempo([k[:2] for k in keep])
    dentro = lambda p: any(a <= (p["a"] + p["b"]) / 2 <= b for a, b, *_ in keep)
    ps = [dict(p, ca=f(p["a"]), cb=f(p["b"])) for p in palavras if dentro(p)]
    out, g = [], []
    for i, p in enumerate(ps):
        if g:
            texto = " ".join(q["t"] for q in g + [p])
            pausa = p["a"] - g[-1]["b"]
            if (len(g) >= PAL_MAX or len(texto) > LETRAS_MAX or pausa > PAUSA_FORTE      # pausa longa fecha sempre
                    or (pausa > PAUSA_GRUPO and len(g) >= PAL_MIN)):
                out.append(g); g = []
        g.append(p)
    if g:
        out.append(g)
    res = []
    for k, g in enumerate(out):
        ini, fim = g[0]["ca"], max(g[-1]["cb"], g[0]["ca"] + 0.25)
        if k + 1 < len(out):
            fim = min(fim, out[k + 1][0]["ca"])
        if fim - ini >= 0.1:
            res.append({"ini": round(ini, 3), "fim": round(min(fim, total), 3), "txt": " ".join(q["t"] for q in g)})
    return res


def maiusculas(txt):
    return " ".join(txt.split()).upper()


# ---------------- montagem ----------------
def crop_material(c):
    x0, y0, x1, y1 = c
    return {"upper_left_x": x0, "upper_left_y": y0, "upper_right_x": x1, "upper_right_y": y0,
            "lower_left_x": x0, "lower_left_y": y1, "lower_right_x": x1, "lower_right_y": y1}


def altura_ipad(info_ipad, crop):
    """fracao da tela ocupada pelo iPad recortado: o CapCut encaixa o recorte na largura toda (1080)"""
    x0, y0, x1, y1 = crop
    return (info_ipad["altura"] * (y1 - y0)) / (info_ipad["largura"] * (x1 - x0)) * 1080 / 1920


def texto_seg(mats, txt, esc, y, fonte_id, caminho, ini, fim, sombra=True):
    seg, m, _ = composto.instancia(composto.MOLDE["texto"], mats)
    c = m["content"]; c = json.loads(c) if isinstance(c, str) else c
    st = copy.deepcopy(c["styles"][0])
    st["range"] = [0, len(txt)]; st["font"] = {"id": fonte_id, "path": caminho}
    st["fill"]["content"]["solid"]["color"] = [1, 1, 1]
    c.update({"text": txt, "styles": [st]})
    m["content"] = json.dumps(c, ensure_ascii=False)
    m.update({"font_path": caminho, "font_resource_id": fonte_id, "font_id": "", "font_name": "", "recognize_text": "",
              "text_color": "#ffffff", "border_width": 0.0, "alignment": 1, "has_shadow": sombra,
              "shadow_color": "#000000", "shadow_alpha": 0.55, "shadow_distance": 4.0, "shadow_smoothing": 0.6})
    if m.get("fonts"):
        m["fonts"] = [dict(m["fonts"][0], id=capcut.uid(), resource_id=fonte_id, path=caminho)]
    if isinstance(m.get("words"), dict):
        m["words"] = {k: [] for k in m["words"]}
    a, b = int(round(ini * 1e6)), int(round(fim * 1e6))
    seg["target_timerange"] = {"start": a, "duration": b - a}
    seg["clip"] = dict(seg["clip"], scale={"x": esc, "y": esc}, transform={"x": 0.0, "y": y})
    return seg


def monta(raiz, an, op):
    """an: analise (videos, infos, janela, keep). op: headline, headline_s, grupos [{ini,fim,txt}], zoom (bool),
    intensidade, pessoa {escala,x,y}, crop_ipad [x0,y0,x1,y1], nome. Devolve (draft, meta)."""
    ip, pe = an["ipad"], an["pessoa"]
    sp, si, comum = an["janela"]
    keep = [[round(sp + a, 4), round(sp + b, 4)] + list(r) for a, b, *r in an["keep"]]
    sonda = capcut.sonda_capcut(raiz)
    draft, meta = capcut.cria_draft(pe["video"], pe["info"], sonda, molde="vertical")
    draft["canvas_config"] = dict(draft["canvas_config"], width=1080, height=1920)

    # enquadramento da pessoa: e' a base dos zooms (o motor multiplica a escala e soma o deslocamento)
    base = capcut.trilha_principal(draft)["segments"][0]
    pes = op.get("pessoa") or {}
    esc_p = float(pes.get("escala", 1.0))
    base["clip"] = dict(base["clip"], scale={"x": esc_p, "y": esc_p},
                        transform={"x": float(pes.get("x", 0.0)), "y": float(pes.get("y", 0.0))})

    # pessoa: cortes + zooms + headline pelo motor do Cortes + Headline
    pl = [{"clip": Path(pe["video"]).name, "tipo": "fala", "dur": pe["info"]["duracao"], "keep": keep}]
    headline = reels.quebra_2_linhas(op["headline"].strip()) if (op.get("headline") or "").strip() else ""
    tpl = reels.carrega_tpl(capcut.cache_efeitos(raiz))
    intens = float(op.get("intensidade", 1.0)) if op.get("zoom", True) else 0.0
    novo, zooms, erros = reels.montar(draft, pl, headline, tpl, "centro", intens)
    erros = [e for e in erros if e != "zoom deixa borda preta"]            # a pessoa pode estar deslocada de proposito
    if erros:
        raise capcut.ErroProjeto("A verificação do projeto falhou: " + ", ".join(sorted(set(erros))[:4]))
    total = novo["duration"]
    mats = novo["materials"]
    idx = capcut.indice_materiais(mats)

    # iPad: MESMOS trechos na timeline, source deslocado pela sincronia; cada trecho com material proprio
    crop = [float(v) for v in (op.get("crop_ipad") or [0, 0, 1, 1])]
    h = altura_ipad(ip["info"], crop)
    caminho_ipad = str(Path(ip["video"]).resolve()).replace("\\", "/")
    vt = capcut.trilha_principal(novo)
    segs_ipad = []
    for s in sorted(vt["segments"], key=lambda s: s["target_timerange"]["start"]):
        ns = capcut.clona_segmento(s, idx, mats)
        mi = [v for v in mats["videos"] if v["id"] == ns["material_id"]][0]
        mi.update({"path": caminho_ipad, "material_name": Path(ip["video"]).name,
                   "duration": int(round(ip["info"]["duracao"] * 1e6)), "width": ip["info"]["largura"],
                   "height": ip["info"]["altura"], "has_audio": False, "crop": crop_material(crop), "crop_ratio": "free",
                   "crop_scale": 1.0, "local_material_id": "", "unique_id": ""})
        ini_rel = s["source_timerange"]["start"] - int(round(sp * 1e6))
        ns["source_timerange"] = {"start": int(round(si * 1e6)) + ini_rel, "duration": s["source_timerange"]["duration"]}
        ns["target_timerange"] = dict(s["target_timerange"])
        ns["clip"] = dict(ns["clip"], scale={"x": 1.0, "y": 1.0}, transform={"x": 0.0, "y": round(1 - h, 6)})
        ns["common_keyframes"] = []
        ns["volume"] = 0.0
        ns.pop("uniform_scale", None)
        segs_ipad.append(ns)
    trilha_ipad = copy.deepcopy(vt); trilha_ipad.update({"id": capcut.uid(), "flag": 2, "segments": segs_ipad})
    novo["tracks"].insert(novo["tracks"].index(vt) + 1, trilha_ipad)   # iPad POR CIMA: zoom que passa da borda fica escondido
    mi = [v for v in mats["videos"] if v["id"] == segs_ipad[0]["material_id"]][0] if segs_ipad else None

    # headline: so no comeco (padrao 7 s), na posicao da referencia
    for t in novo["tracks"]:
        if t["type"] == "text":
            for s in t["segments"]:
                s["target_timerange"] = {"start": 0, "duration": min(total, int(round(float(op.get("headline_s", HEADLINE_S)) * 1e6)))}
                s["clip"] = dict(s["clip"], scale={"x": ESC_HEADLINE, "y": ESC_HEADLINE}, transform={"x": 0.0, "y": Y_HEADLINE})

    # legenda: frases curtas em MAIUSCULAS, uma trilha so
    cache = capcut.cache_efeitos(raiz)
    caminho = composto.caminho_no_cache(FONTE_LEGENDA["id"], cache)
    leg = []
    for g in op.get("grupos") or []:
        txt = maiusculas(g.get("txt", ""))
        if not txt: continue
        esc = ESC_LEGENDA
        if largura_px(txt, esc, "proximanova_bold") * SEGURANCA > 1080:          # frase comprida: diminui ate caber
            esc = 1080 / SEGURANCA / largura_px(txt, 1.0, "proximanova_bold")
        leg.append(texto_seg(mats, txt, round(esc, 4), Y_LEGENDA, FONTE_LEGENDA["id"], caminho,
                             float(g["ini"]), min(float(g["fim"]), total / 1e6)))
    if leg:
        t = copy.deepcopy(composto.MOLDE["trilha_modelo"]); t.update({"id": capcut.uid(), "segments": leg})
        novo["tracks"].append(t)
    capcut.poda(novo)

    # meta: registra o iPad tambem na midia do projeto
    try:
        if mi is None: raise KeyError
        item = copy.deepcopy(meta["draft_materials"][0]["value"][0])
        item.update({"id": capcut.uid().lower(), "extra_info": mi["material_name"], "file_Path": mi["path"],
                     "duration": mi["duration"], "width": mi["width"], "height": mi["height"],
                     "roughcut_time_range": {"duration": mi["duration"], "start": 0}})
        meta["draft_materials"][0]["value"].append(item)
    except (KeyError, IndexError):
        pass
    return novo, meta


# ---------------- verificacao (trava e avisa em vez de gravar projeto quebrado) ----------------
def verifica(d):
    erros = list(capcut.verifica(d))
    vids = [t for t in d["tracks"] if t["type"] == "video"]
    pessoa = next((t for t in vids if t.get("flag", 0) == 0), None)        # trilho principal = pessoa
    ipad = next((t for t in vids if t.get("flag", 0) == 2), None)          # sobreposicao = iPad
    if pessoa is None or ipad is None:
        return erros + ["faltou um dos dois vídeos"]
    mats = {v["id"]: v for v in d["materials"]["videos"]}
    alvo = lambda t: [(s["target_timerange"]["start"], s["target_timerange"]["duration"]) for s in
                      sorted(t["segments"], key=lambda s: s["target_timerange"]["start"])]
    if alvo(pessoa) != alvo(ipad):                                          # 1. mesma lista de trechos
        erros.append("os trilhos do iPad e da pessoa não têm os mesmos trechos")
    for t, nome in ((pessoa, "pessoa"), (ipad, "iPad")):
        for s in t["segments"]:
            m = mats.get(s["material_id"], {})
            src = s["source_timerange"]
            if src["start"] < 0 or src["start"] + src["duration"] > m.get("duration", 0) + 1000:
                erros.append(f"trecho do vídeo da {nome} passa do fim do arquivo")
            if s["target_timerange"]["start"] + s["target_timerange"]["duration"] > d["duration"] + 1000:
                erros.append("trecho passa do fim do projeto")                 # 2. limites
    for m in mats.values():                                                 # 3. arquivos existem
        if m.get("extra_type_option") != 2 and m.get("path") and not Path(m["path"]).exists():
            erros.append(f"arquivo não encontrado: {m.get('material_name')}")
    txt = {m["id"]: m for m in d["materials"].get("texts", [])}
    for t in d["tracks"]:                                                   # 4. texto dentro da tela
        if t["type"] != "text": continue
        for s in t["segments"]:
            m = txt.get(s["material_id"])
            if not m: continue
            c = json.loads(m["content"]) if isinstance(m["content"], str) else m["content"]
            fonte = "proximanova_bold" if m.get("font_resource_id") == FONTE_LEGENDA["id"] else "classic"
            maior = max(c["text"].split("\n"), key=len)
            if largura_px(maior, s["clip"]["scale"]["x"], fonte) * SEGURANCA > 1080 + 1:
                erros.append(f"texto '{maior}' sai da tela")
    if d["tracks"].index(ipad) < d["tracks"].index(pessoa):                 # 5. iPad acima da pessoa
        erros.append("o iPad ficou atrás da pessoa")
    return sorted(set(erros))
