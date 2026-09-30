"""Modo APRESENTADOR + iPAD: junta a camera (pessoa falando) e a gravacao de tela do iPad num projeto 1080x1920,
iPad em cima (recortado) e pessoa embaixo, sincronizados pelo usuario, zoom so na pessoa e headline no inicio.
Os dois videos vao juntos num CLIPE COMPOSTO sincronizado, e os cortes sao feitos no composto (na raiz): assim o
iPad e a pessoa nunca desalinham e os cortes podem ser ajustados no CapCut puxando as bordas.
Especificacao: docs/design/apresentador-ipad-especificacao.md."""
import copy, json, subprocess, re
import numpy as np
from pathlib import Path
from . import audio, capcut, reels, composto

# ---------------- medidas calibradas na referencia (resultado final ipad.mp4) e nas capas do CapCut ----------------
PROPORCAO_IPAD = 0.347               # altura padrao da faixa do iPad (fracao da tela)
PX_POR_EM = 94.2                     # 1080x1920, font_size 15: pixels por (em x escala), medido em 3 capas do CapCut
ESC_HEADLINE = 0.623                 # fonte Classic (molde da headline do Cortes + Headline)
Y_HEADLINE = 0.408                   # centro a 29,6% da altura (y do CapCut: 1 = topo, -1 = base)
HEADLINE_S = 7.0
SEGURANCA = 1.3
QUADRO = 1 / 30                      # passo de "avancar 1 quadro" na tela de sincronia (as previas sao 30 fps)

_ASSETS = Path(__file__).resolve().parent / "assets"
_LARG = {n: json.loads((_ASSETS / f"larguras_{n}.json").read_text(encoding="utf-8")) for n in ("classic",)}


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


# ---------------- cortes (regua propria: quem explica desenhando pausa pra desenhar) ----------------
# A regua seca do Cortes + Headline cortava silaba e jogava fora o desenho feito em silencio (medido no bruto "1.MOV":
# 6 palavras cortadas no meio e 18 coladas na borda do corte). Aqui: so corta pausa de verdade, com folga antes e
# depois da fala, e a transcricao protege as palavras (medido: 0 palavras cortadas, 0 coladas, nas 3 intensidades).
INTENSIDADES = {                     # pausa minima pra virar corte, folga antes, folga depois (s)
    "leve": (0.8, 0.15, 0.25),
    "media": (0.5, 0.15, 0.25),
    "forte": (0.35, 0.12, 0.20),
}


def cortes(x, palavras=(), intensidade="media"):
    """trechos mantidos [[a, b, False]] em s relativos ao inicio da janela. Fala = audio com voz OU palavra transcrita."""
    pausa, pre, pos = INTENSIDADES.get(intensidade, INTENSIDADES["media"])
    dur = len(x) / audio.SR
    e, v = audio.analisa(x)
    porta = audio.porta_de(e, v)
    fala = audio.tom_sustentado(e, v, porta) | (e > porta + 8.0)
    for p in palavras:                                    # a palavra transcrita nunca fica fora
        fala[max(0, int(p["a"] / audio.H)):int(p["b"] / audio.H) + 1] = True
    out = []
    for a, b in audio.runs(fala):
        a, b = max(0.0, a * audio.H - pre), min(dur, b * audio.H + pos)
        if out and a - out[-1][1] < pausa:
            out[-1][1] = b
        else:
            out.append([a, b])
    out = [list(audio.na_grade(a, b)) for a, b in out if b - a > 0.15]
    out = [[a, min(b, np.floor(dur * audio.FPS) / audio.FPS), False] for a, b in out]
    return out or [[0.0, float(np.floor(dur * audio.FPS) / audio.FPS), False]]


# ---------------- montagem: clipe composto "iPad + pessoa" sincronizado, cortado por fora ----------------
def crop_material(c):
    x0, y0, x1, y1 = c
    return {"upper_left_x": x0, "upper_left_y": y0, "upper_right_x": x1, "upper_right_y": y0,
            "lower_left_x": x0, "lower_left_y": y1, "lower_right_x": x1, "lower_right_y": y1}


def altura_ipad(info_ipad, crop):
    """fracao da tela ocupada pelo iPad recortado: o CapCut encaixa o recorte na largura toda (1080)"""
    x0, y0, x1, y1 = crop
    return (info_ipad["altura"] * (y1 - y0)) / (info_ipad["largura"] * (x1 - x0)) * 1080 / 1920


def _pedacos(sub, total):
    """divide a timeline do composto: trechos mantidos ja subdivididos pras trocas de zoom (sem tirar nada) e os
    buracos entre eles (cortados por fora). [(a, b, mantido, forca)] cobrindo 0..total"""
    out, cur = [], 0.0
    for a, b, forca in sub:
        if a > cur + 1e-3: out.append((cur, a, False, False))
        out.append((max(a, cur), b, True, forca)); cur = b
    if cur < total - 1e-3: out.append((cur, total, False, False))
    return out


def _zoom(ns, z, clip0):
    """mesmo punch-in do Cortes + Headline (reels.montar), so na pessoa"""
    base_s = clip0["scale"]["x"]; base_x = clip0["transform"]["x"]; base_y = clip0["transform"]["y"]
    clip = copy.deepcopy(clip0); ns["common_keyframes"] = []
    if z:
        tipo, sc, dx = z
        clip["scale"] = {"x": base_s * sc, "y": base_s * sc}; clip["transform"]["x"] = base_x + dx
        if tipo == "empurra":
            A = ns["source_timerange"]["start"]; B = A + ns["source_timerange"]["duration"]
            t0, t1 = A, B - int(1e6 / audio.FPS)
            ns["common_keyframes"] = [reels.kf("KFTypePositionX", t0, t1, base_x, base_x + dx),
                                      reels.kf("KFTypePositionY", t0, t1, base_y, base_y),
                                      reels.kf("KFTypeScaleX", t0, t1, base_s, base_s * sc),
                                      reels.kf("KFTypeRotation", t0, t1, 0.0, 0.0)]
            ns["uniform_scale"] = {"on": True, "value": 1.0}
    ns["clip"] = clip


def monta(raiz, an, op):
    """an: analise (videos, janela, keeps por intensidade). op: headline, headline_s, cortes (leve|media|forte),
    zoom (bool), intensidade (zoom), pessoa {escala,x,y}, crop_ipad [x0,y0,x1,y1], nome.
    Devolve (raiz_draft, meta, compostos) — compostos pra gravar as pastas subdraft."""
    ip, pe = an["ipad"], an["pessoa"]
    sp, si, comum = an["janela"]
    keep = an["keeps"][op.get("cortes") or "media"]
    comum = float(np.floor(comum * audio.FPS) / audio.FPS)        # composto com numero inteiro de quadros
    total_c = audio.quadro_us(comum)
    us = audio.quadro_us
    sonda = capcut.sonda_capcut(raiz)
    base, meta = capcut.cria_draft(pe["video"], pe["info"], sonda, molde="vertical")
    canvas = (1080, 1920)
    base["canvas_config"] = dict(base["canvas_config"], width=canvas[0], height=canvas[1])

    # --- composto "iPad + pessoa": os dois videos INTEIROS, sincronizados (pessoa embaixo, iPad por cima)
    ent = composto.composto("iPad + pessoa", base, canvas, total_c)
    dc = ent["draft"]; dc["materials"] = copy.deepcopy(base["materials"])
    idx = capcut.indice_materiais(dc["materials"])
    orig = capcut.trilha_principal(base)["segments"][0]
    pes = op.get("pessoa") or {}
    esc_p = float(pes.get("escala", 1.0))
    clip_p = dict(copy.deepcopy(orig["clip"]), scale={"x": esc_p, "y": esc_p},
                  transform={"x": float(pes.get("x", 0.0)), "y": float(pes.get("y", 0.0))})
    sub = (an.get("zooms") or {}).get(op.get("cortes") or "media") or [[a, b, False] for a, b, *_ in keep]
    pedacos = _pedacos(sub, comum)
    intens = float(op.get("intensidade", 1.0)) if op.get("zoom", True) else 0.0
    mantidos = [(b - a, forca) for a, b, m, forca in pedacos if m]
    zooms = iter(reels.plano_zoom(mantidos, "centro", intens))
    segs_p = []
    for a, b, mantido, _ in pedacos:                      # pessoa dividida nos cortes e nas trocas de zoom
        ns = capcut.clona_segmento(orig, idx, dc["materials"])
        A, B = us(a), us(min(b, comum))
        ns["source_timerange"] = {"start": us(sp) + A, "duration": B - A}
        ns["target_timerange"] = {"start": A, "duration": B - A}
        _zoom(ns, next(zooms) if mantido else None, clip_p)
        segs_p.append(ns)
    crop = [float(v) for v in (op.get("crop_ipad") or [0, 0, 1, 1])]
    ns = capcut.clona_segmento(orig, idx, dc["materials"])
    mi = [v for v in dc["materials"]["videos"] if v["id"] == ns["material_id"]][0]
    mi.update({"path": str(Path(ip["video"]).resolve()).replace("\\", "/"), "material_name": Path(ip["video"]).name,
               "duration": int(round(ip["info"]["duracao"] * 1e6)), "width": ip["info"]["largura"], "height": ip["info"]["altura"],
               "has_audio": False, "crop": crop_material(crop), "crop_ratio": "free", "crop_scale": 1.0,
               "local_material_id": "", "unique_id": ""})
    ns["source_timerange"] = {"start": us(si), "duration": total_c}
    ns["target_timerange"] = {"start": 0, "duration": total_c}
    ns["clip"] = dict(copy.deepcopy(orig["clip"]), scale={"x": 1.0, "y": 1.0},
                      transform={"x": 0.0, "y": round(1 - altura_ipad(ip["info"], crop), 6)})
    ns["common_keyframes"] = []; ns["volume"] = 0.0
    ns["render_index"] = 1          # camada de cima (igual ao 0930): com 0 o CapCut desenhou o iPad com fundo preto POR CIMA da pessoa
    trilha = capcut.trilha_principal(base)
    dc["tracks"] = [dict(copy.deepcopy(trilha), id=capcut.uid(), flag=0, segments=segs_p),
                    dict(copy.deepcopy(trilha), id=capcut.uid(), flag=2, segments=[ns])]      # iPad POR CIMA
    capcut.poda(dc)

    # --- raiz: o composto cortado (cada trecho mantido e' um segmento do MESMO composto, com material proprio)
    raiz_d = composto.esqueleto(base); raiz_d["id"] = capcut.uid()
    segs, cur = [], 0
    for a, b, *_ in keep:
        s, _, _ = composto.seg_composto(composto.MOLDE["raiz"]["corpo"], ent, raiz_d["materials"], total_c, canvas)
        A, B = us(a), us(min(b, comum))
        s["source_timerange"] = {"start": A, "duration": B - A}
        s["target_timerange"] = {"start": cur, "duration": B - A}
        s["clip"] = dict(s["clip"], scale={"x": 1.0, "y": 1.0}, transform={"x": 0.0, "y": 0.0})
        segs.append(s); cur += B - A
    raiz_d["tracks"] = [composto.trilha("trilha_video_modelo", segs)]
    raiz_d["duration"] = cur

    # --- headline: so no comeco (padrao 7 s), logo acima do iPad
    if (op.get("headline") or "").strip():
        tpl = reels.carrega_tpl(capcut.cache_efeitos(raiz))
        th = reels.headline(raiz_d["materials"], tpl, reels.quebra_2_linhas(op["headline"].strip()), cur)
        for s in th["segments"]:
            s["target_timerange"] = {"start": 0, "duration": min(cur, int(round(float(op.get("headline_s", HEADLINE_S)) * 1e6)))}
            s["clip"] = dict(s["clip"], scale={"x": ESC_HEADLINE, "y": ESC_HEADLINE}, transform={"x": 0.0, "y": Y_HEADLINE})
        raiz_d["tracks"].append(th)
    raiz_d["materials"]["drafts"] = [ent]                 # entrada do composto na RAIZ (lista plana)

    try:                                                  # registra o iPad tambem na midia do projeto
        item = copy.deepcopy(meta["draft_materials"][0]["value"][0])
        item.update({"id": capcut.uid().lower(), "extra_info": mi["material_name"], "file_Path": mi["path"],
                     "duration": mi["duration"], "width": mi["width"], "height": mi["height"],
                     "roughcut_time_range": {"duration": mi["duration"], "start": 0}})
        meta["draft_materials"][0]["value"].append(item)
    except (KeyError, IndexError):
        pass
    return raiz_d, meta, [ent]


# ---------------- verificacao (trava e avisa em vez de gravar projeto quebrado) ----------------
def verifica(raiz, pasta=None):
    erros = list(composto.verifica(raiz, pasta))          # estrutura do composto: entrada na raiz, refs, limites, subdraft
    ents = raiz["materials"].get("drafts", [])
    if len(ents) != 1:
        return erros + ["o projeto precisa ter exatamente um clipe composto (iPad + pessoa)"]
    d = ents[0]["draft"]
    vids = [t for t in d["tracks"] if t["type"] == "video"]
    pessoa = next((t for t in vids if t.get("flag", 0) == 0), None)
    ipad = next((t for t in vids if t.get("flag", 0) == 2), None)
    if pessoa is None or ipad is None:
        return erros + ["faltou um dos dois vídeos dentro do composto"]
    mats = {v["id"]: v for v in d["materials"]["videos"]}
    fim = lambda t: max(s["target_timerange"]["start"] + s["target_timerange"]["duration"] for s in t["segments"])
    if abs(fim(pessoa) - fim(ipad)) > 1000 or abs(fim(pessoa) - d["duration"]) > 1000:
        erros.append("o iPad e a pessoa não cobrem o mesmo tempo dentro do composto")
    for t, nome in ((pessoa, "da pessoa"), (ipad, "do iPad")):
        for s in t["segments"]:
            m = mats.get(s["material_id"], {})
            src = s["source_timerange"]
            if src["start"] < 0 or src["start"] + src["duration"] > m.get("duration", 0) + 1000:
                erros.append(f"trecho do vídeo {nome} passa do fim do arquivo")
            if m.get("path") and not Path(m["path"]).exists():
                erros.append(f"arquivo não encontrado: {m.get('material_name')}")
    if d["tracks"].index(ipad) < d["tracks"].index(pessoa):
        erros.append("o iPad ficou atrás da pessoa")
    for s in raiz["tracks"][0]["segments"]:               # cortes de fora dentro do composto
        src = s["source_timerange"]
        if src["start"] < 0 or src["start"] + src["duration"] > d["duration"] + 1000:
            erros.append("um corte passa do fim do clipe composto")
    txt = {m["id"]: m for m in raiz["materials"].get("texts", [])}
    for t in raiz["tracks"]:                               # headline dentro da tela
        if t["type"] != "text": continue
        for s in t["segments"]:
            m = txt.get(s["material_id"])
            if not m: continue
            c = json.loads(m["content"]) if isinstance(m["content"], str) else m["content"]
            maior = max(c["text"].split("\n"), key=len)
            if largura_px(maior, s["clip"]["scale"]["x"], "classic") * SEGURANCA > 1080 + 1:
                erros.append(f"a headline '{maior}' sai da tela: use um texto mais curto")
    return sorted(set(erros))
