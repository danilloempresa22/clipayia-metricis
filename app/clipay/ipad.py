"""Modo APRESENTADOR + iPAD: junta a camera (pessoa falando) e a gravacao de tela do iPad num projeto 1080x1920,
iPad em cima (recortado) e pessoa embaixo, sincronizados pelo usuario, zoom so na pessoa e headline no inicio.
Estrutura (de dentro pra fora):
  "iPad + pessoa"  os dois videos INTEIROS e sincronizados; a pessoa e' UM segmento so, zoom por keyframes
  "Video"          os cortes (segmentos do composto acima) + headline + legenda (opcional)
  RAIZ             o composto "Video" (velocidade 1,13x opcional) + musica a -25 dB (opcional)
O CapCut guarda uma COPIA do "iPad + pessoa" pra cada corte: por isso ele tem que ser leve (2 segmentos; com a
pessoa picada em 124 pedacos o projeto chegou a 46 MB e travava).
Especificacao: docs/design/apresentador-ipad-especificacao.md."""
import copy, json, os, subprocess, re
import numpy as np
from pathlib import Path
from . import audio, capcut, reels, composto, vlog, legenda

# ---------------- medidas calibradas na referencia (resultado final ipad.mp4) e nas capas do CapCut ----------------
PROPORCAO_IPAD = 0.347               # altura padrao da faixa do iPad (fracao da tela)
PX_POR_EM = 94.2                     # 1080x1920, font_size 15: pixels por (em x escala), medido em 3 capas do CapCut
ESC_HEADLINE = 0.623                 # fonte Classic (molde da headline do Cortes + Headline)
Y_HEADLINE = 0.408                   # centro a 29,6% da altura (y do CapCut: 1 = topo, -1 = base)
HEADLINE_S = 7.0
SEGURANCA = 1.3
QUADRO = 1 / 30                      # passo de "avancar 1 quadro" na tela de sincronia (as previas sao 30 fps)
VELOCIDADE = 1.13                    # opcional, no composto final (em cima de tudo, ate da legenda)
MUSICA_DB = -25.0                    # volume da musica de fundo

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
    return _fecha(out, dur, 0.15)


# "seco": a regua SECA do vlog (sem respiracao, sem silencio) + a transcricao devolvendo o SOM das palavras que ela
# comeu (sibilantes: "case.", "somente"). Medido no bruto "1.MOV": 173,7 s (media: 186,5 s), 6 silencios > 0,25 s
# (media: 62), 0 palavras com som cortado (regua do vlog sozinha: 7).
SOM_PALAVRA = 4.0                    # dB acima da porta: o pedaco da palavra que tem som de verdade (nao a folga estimada)
FOLGA_PALAVRA = 0.03
JUNTA_SECO = 0.12                    # buraco menor que isso nao vale o corte (picota)


def seco(x, palavras=()):
    dur = len(x) / audio.SR
    e, v = audio.analisa(x)
    porta, n, H = audio.porta_de(e, v), len(e), audio.H
    m = np.zeros(n, bool)
    for a, b in vlog.regua(x, dur):
        m[int(round(a / H)):int(round(b / H))] = True
    w = np.zeros(n, bool)
    for p in palavras:
        w[max(0, int(p["a"] / H)):int(p["b"] / H) + 1] = True
    m |= audio.dil(w & (e > porta + SOM_PALAVRA), int(FOLGA_PALAVRA / H)) & w
    out = []
    for a, b in audio.runs(m):
        if out and a * H - out[-1][1] < JUNTA_SECO:
            out[-1][1] = b * H
        else:
            out.append([a * H, b * H])
    return _fecha(out, dur, 0.1)


def _fecha(out, dur, minimo):
    """na grade de quadros e dentro do arquivo: [[a, b, False]]"""
    fim = float(np.floor(dur * audio.FPS) / audio.FPS)
    out = [list(audio.na_grade(a, min(b, dur))) for a, b in out if b - a > minimo]
    out = [[a, min(b, fim), False] for a, b in out if min(b, fim) > a]
    return out or [[0.0, fim, False]]


CORTES = ("seco", *INTENSIDADES)     # opcoes da tela; "seco" e' o padrao


def keep_de(x, palavras, k):
    return seco(x, palavras) if k == "seco" else cortes(x, palavras, k)


# ---------------- montagem: clipe composto "iPad + pessoa" sincronizado, cortado por fora ----------------
def crop_material(c):
    x0, y0, x1, y1 = c
    return {"upper_left_x": x0, "upper_left_y": y0, "upper_right_x": x1, "upper_right_y": y0,
            "lower_left_x": x0, "lower_left_y": y1, "lower_right_x": x1, "lower_right_y": y1}


def altura_ipad(info_ipad, crop):
    """fracao da tela ocupada pelo iPad recortado: o CapCut encaixa o recorte na largura toda (1080)"""
    x0, y0, x1, y1 = crop
    return (info_ipad["altura"] * (y1 - y0)) / (info_ipad["largura"] * (x1 - x0)) * 1080 / 1920


def _kf(prop, pts):
    return {"id": capcut.uid(), "material_id": "", "property_type": prop, "keyframe_list": [
        {"id": capcut.uid(), "curveType": "Line", "time_offset": int(t), "left_control": {"x": 0.0, "y": 0.0},
         "right_control": {"x": 0.0, "y": 0.0}, "values": [float(v)], "string_value": "", "graphID": ""} for t, v in pts]}


def pontos_zoom(sub, zooms, sp_us, comum, clip0, posicao=0.0):
    """zoom da pessoa como keyframes de UM segmento so: [(tempo na origem em us, escala, x)], ja enxuto.
    Mesmo punch-in do Cortes + Headline: 'fixo' segura a escala o trecho todo, 'empurra' vai de 1 ate a escala.
    A troca acontece de um quadro pro outro (keyframe no ultimo quadro do trecho e no primeiro do seguinte).
    time_offset dos keyframes do CapCut = tempo na ORIGEM (conferido num keyframe de volume feito a mao)."""
    base_s, base_x = clip0["scale"]["x"], clip0["transform"]["x"]
    pts = []
    for (a, b, _), z in zip(sub, zooms):
        S = sp_us + audio.quadro_us(a)
        E = sp_us + audio.quadro_us(min(b, comum) - QUADRO)
        v0 = v1 = (base_s, base_x)
        if z:
            tipo, sc, dx = z
            v1 = (base_s * sc, reels.x_centro(base_s * sc, posicao))     # zoom centrado na pessoa (escala total)
            v0 = (base_s, base_x) if tipo == "empurra" else v1
        pts.append((S, *v0))
        if E > S: pts.append((E, *v1))
    enx = [p for i, p in enumerate(pts) if i in (0, len(pts) - 1) or not (pts[i - 1][1:] == p[1:] == pts[i + 1][1:])]
    return enx if any(p[1:] != (base_s, base_x) for p in enx) else []


# ---------------- legenda AUTOMATICA do CapCut (modelo 逐页短句 + Creato Display Black) ----------------
# Nao da pra apertar o "legendas automaticas" do CapCut de fora (o reconhecimento roda no servidor dele). Entao a
# legenda sai EXATAMENTE como ele grava a automatica (molde tirado do projeto do usuario): trilha de legenda,
# cada frase um modelo de legenda com o texto dentro, tempo de cada palavra e o grupo "reconhecido em pt-BR".
# So o texto e os tempos vem da nossa transcricao.
MOLDE_AUTO = json.loads((_ASSETS / "moldes" / "legenda_auto.json").read_text(encoding="utf-8"))
FRASE_MAX = 46                       # letras por frase (na edicao feita a mao: ate 46-54; o CapCut quebra em 2 linhas)
PAUSA_FRASE = 0.25                   # pausa que fecha a frase (s)
COLA = 0.30                          # buraco menor que isso entre frases: a anterior fica ate a proxima entrar
_PONTO = re.compile(r"[.,;:!?…]+[\"'”’)»]*$")
_ENFEITE = re.compile(r"^[-–—\"'“‘(«]+|[\"'”’)»]+$")    # travessao de dialogo e aspas que o Whisper poe
_PENDURADA = {"a", "o", "e", "de", "do", "da", "que", "no", "na", "em", "um", "uma", "os", "as", "pra", "para", "com", "se", "eu"}


def fonte_legenda():
    """a fonte da legenda (Creato Display Black) e' uma fonte instalada no sistema (Windows ou Mac), nao do cache do
    CapCut. Vazio = nao instalada."""
    return capcut.fonte_instalada(MOLDE_AUTO["fonte_arquivo"])


def frases(palavras, keep):
    """palavras (s no composto) -> frases na timeline cortada [{txt, ini, fim, palavras}] em quadros inteiros, sem
    se cruzar. palavras = [(falada em minusculas, a, b)] pro tempo de cada palavra da legenda automatica"""
    f, total = legenda.mapa_tempo([k[:2] for k in keep])
    ws = []
    for p in palavras:
        t = _ENFEITE.sub("", _PONTO.sub("", p["t"].strip())).upper()
        a, b = f(p["a"]), f(p["b"])
        if t and b - a > 0.02:                            # palavra que caiu inteira num corte nao entra
            ws.append((t, a, b, bool(_PONTO.search(p["t"].strip()))))
    grupos, cur = [], []
    for w in ws:
        if cur:
            longa = len(" ".join(x[0] for x in cur + [w])) > FRASE_MAX
            if w[1] - cur[-1][2] >= PAUSA_FRASE or cur[-1][3] or longa:
                if longa and len(cur) > 1 and cur[-1][0].lower() in _PENDURADA:
                    grupos.append(cur[:-1]); cur = [cur[-1]]      # "de", "que"... vai pra frase seguinte
                else:
                    grupos.append(cur); cur = []
        cur.append(w)
    if cur:
        grupos.append(cur)
    out = [{"txt": " ".join(w[0] for w in g), "ini": g[0][1], "fim": g[-1][2],
            "palavras": [(w[0].lower(), w[1], w[2]) for w in g]} for g in grupos]
    fps, fim_q, ult = audio.FPS, int(np.floor(total * audio.FPS + 1e-6)), 0
    res = []
    for i, s in enumerate(out):
        prox = out[i + 1]["ini"] if i + 1 < len(out) else total
        fim = prox if prox - s["fim"] < COLA else s["fim"] + 0.1
        I = max(int(round(s["ini"] * fps)), ult)
        F = min(max(int(round(fim * fps)), I + 3), fim_q)
        if F > I:
            res.append({"txt": s["txt"], "ini": I / fps, "fim": F / fps, "palavras": s["palavras"]}); ult = F
    return res


def legenda_auto(d, frs, raiz, fonte):
    """poe as frases em d (draft) como a legenda automatica do CapCut: devolve a trilha de legenda"""
    import time, uuid
    cache = str(Path(raiz).parent.parent / "Cache").replace("\\", "/")
    mol = json.loads(json.dumps(MOLDE_AUTO, ensure_ascii=False).replace("{CACHE}", cache).replace("{FONTE}", fonte))
    tarefa, grupo, nome = f"{uuid.uuid4().hex[:24]}_8_0", f"pt-BR_{int(time.time() * 1000)}", capcut.uid()
    mats = d["materials"]; segs = []
    for i, fr in enumerate(frs):
        A, B = audio.quadro_us(fr["ini"]), audio.quadro_us(fr["fim"])
        an = copy.deepcopy(mol["animacao"]); an["id"] = capcut.uid()
        mats.setdefault("material_animations", []).append(an)
        tx = copy.deepcopy(mol["texto"]); tx["id"] = capcut.uid()
        c = json.loads(tx["content"]); c["text"] = fr["txt"]
        for st in c["styles"]:
            st["range"] = [0, len(fr["txt"])]
        tx["content"] = json.dumps(c, ensure_ascii=False)
        ini, fim, txt = [], [], []                        # tempo de cada palavra em ms desde o inicio da frase
        for j, (w, a, b) in enumerate(fr["palavras"]):
            s0 = max(0, int(round(a * 1000 - A / 1000))); s1 = max(s0, min(int(round(b * 1000 - A / 1000)), (B - A) // 1000))
            ini.append(s0); fim.append(s1); txt.append(w)
            if j + 1 < len(fr["palavras"]):
                ini.append(s1); fim.append(s1); txt.append(" ")
        tx.update({"recognize_task_id": tarefa, "recognize_text": " ".join(w for w, _, _ in fr["palavras"]),
                   "group_id": grupo, "name": nome, "words": {"start_time": ini, "end_time": fim, "text": txt}})
        mats.setdefault("texts", []).append(tx)
        tt = copy.deepcopy(mol["modelo"]); tt["id"] = capcut.uid()
        r = tt["text_info_resources"][0]
        r.update({"id": capcut.uid(), "text_material_id": tx["id"], "extra_material_refs": [an["id"]]})
        r["attach_info"] = dict(r["attach_info"], start_time=0, duration=B - A)
        mats.setdefault("text_templates", []).append(tt)
        sg = copy.deepcopy(mol["segmento"]); sg["id"] = capcut.uid()
        sg.update({"material_id": tt["id"], "extra_material_refs": [an["id"]], "render_index": 14001 + i,
                   "target_timerange": {"start": A, "duration": B - A}})
        segs.append(sg)
    cfg = copy.deepcopy(mol["config"]); cfg["subtitle_taskinfo"][0]["id"] = tarefa
    d["config"] = dict(d.get("config") or {}, **cfg)
    return dict(copy.deepcopy(mol["trilha"]), id=capcut.uid(), segments=segs)


def _velocidade(seg, porcat, dentro_us, vel):
    """segmento de composto acelerado: duracao de fora em quadros inteiros e velocidade EXATA dentro/fora
    (fora da grade o CapCut mexe na velocidade sozinho)"""
    q = 1e6 / audio.FPS
    fora = audio.quadro_us(round(dentro_us / q / vel) / audio.FPS) if vel != 1.0 else dentro_us
    real = dentro_us / fora
    seg["speed"] = real
    seg["source_timerange"] = {"start": 0, "duration": dentro_us}
    seg["target_timerange"] = {"start": 0, "duration": fora}
    if "speeds" in porcat:
        porcat["speeds"]["speed"] = real
    return fora


def monta(raiz, an, op):
    """an: analise (videos, janela, keeps por intensidade). op: headline, headline_s, cortes (seco|leve|media|forte),
    zoom (bool), intensidade (zoom), pessoa {escala,x,y}, crop_ipad [x0,y0,x1,y1], nome.
    Devolve (raiz_draft, meta, compostos) — compostos pra gravar as pastas subdraft."""
    ip, pe = an["ipad"], an["pessoa"]
    sp, si, comum = an["janela"]
    keep = an["keeps"][op.get("cortes") or "seco"]
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
    sub = (an.get("zooms") or {}).get(op.get("cortes") or "seco") or [[a, b, False] for a, b, *_ in keep]
    intens = float(op.get("intensidade", 1.0)) if op.get("zoom", True) else 0.0
    zooms = reels.plano_zoom([(b - a, forca) for a, b, forca in sub], an.get("posicao", 0.0), intens)
    ps = capcut.clona_segmento(orig, idx, dc["materials"])          # a pessoa INTEIRA num segmento so
    ps["source_timerange"] = {"start": us(sp), "duration": total_c}
    ps["target_timerange"] = {"start": 0, "duration": total_c}
    ps["clip"] = copy.deepcopy(clip_p)
    pts = pontos_zoom(sub, zooms, us(sp), comum, clip_p, an.get("posicao", 0.0))
    # os 4 juntos, como o CapCut grava: sem o PositionY ele assume y = 0 e a pessoa subia pra tras do iPad
    ps["common_keyframes"] = ([_kf("KFTypePositionX", [(t, x) for t, _, x in pts]),
                               _kf("KFTypePositionY", [(t, clip_p["transform"]["y"]) for t, _, _ in pts]),
                               _kf("KFTypeScaleX", [(t, s) for t, s, _ in pts]),
                               _kf("KFTypeRotation", [(t, 0.0) for t, _, _ in pts])] if pts else [])
    ps["uniform_scale"] = {"on": True, "value": 1.0}
    ent["_zooms"] = sum(1 for z in zooms if z)
    segs_p = [ps]
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

    # --- composto "Video": o "iPad + pessoa" cortado (cada trecho mantido e' um segmento dele, material proprio)
    #     + headline + legenda. O composto existe sempre: e' nele que vai a velocidade, em cima de tudo.
    comp = [(us(a), us(min(b, comum))) for a, b, *_ in keep]
    total_v = sum(B - A for A, B in comp)
    ent_v = composto.composto("Vídeo", base, canvas, total_v)
    dv = ent_v["draft"]
    segs, cur = [], 0
    for A, B in comp:
        s, _, porcat = composto.seg_composto(composto.MOLDE["raiz"]["corpo"], ent, dv["materials"], total_c, canvas)
        s["source_timerange"] = {"start": A, "duration": B - A}
        s["target_timerange"] = {"start": cur, "duration": B - A}
        s["clip"] = dict(s["clip"], scale={"x": 1.0, "y": 1.0}, transform={"x": 0.0, "y": 0.0})
        if "speeds" in porcat: porcat["speeds"]["speed"] = 1.0
        segs.append(s); cur += B - A
    dv["tracks"] = [composto.trilha("trilha_video_modelo", segs)]
    vel = VELOCIDADE if op.get("velocidade") else 1.0

    # headline: so no comeco, logo acima do iPad. Duracao contada no video FINAL (ja acelerado)
    if (op.get("headline") or "").strip():
        tpl = reels.carrega_tpl(capcut.cache_efeitos(raiz))
        th = reels.headline(dv["materials"], tpl, reels.quebra_2_linhas(op["headline"].strip()), cur)
        dur_h = min(cur, audio.quadro_us(float(op.get("headline_s", HEADLINE_S)) * vel))
        for s in th["segments"]:
            s["target_timerange"] = {"start": 0, "duration": dur_h}
            s["clip"] = dict(s["clip"], scale={"x": ESC_HEADLINE, "y": ESC_HEADLINE}, transform={"x": 0.0, "y": Y_HEADLINE})
        dv["tracks"].append(th)

    # legenda: frases curtas no estilo do molde, na timeline ja cortada
    ent_v["_avisos"], ent_v["_legendas"] = [], 0            # campos "_" nao vao pro disco (limpa_para_gravar)
    if op.get("legenda"):
        fonte = fonte_legenda()
        if not fonte:
            ent_v["_avisos"].append("A fonte Creato Display Black não está instalada neste computador: "
                                    "a legenda vai aparecer com a fonte padrão do CapCut.")
        frs = frases(an.get("palavras") or [], keep)
        if frs:
            dv["tracks"].append(legenda_auto(dv, frs, raiz, fonte))
        ent_v["_legendas"] = len(frs)

    # --- raiz: o "Video" (acelerado ou nao) + musica
    raiz_d = composto.esqueleto(base); raiz_d["id"] = capcut.uid()
    s_v, _, porcat = composto.seg_composto(composto.MOLDE["raiz"]["corpo"], ent_v, raiz_d["materials"], total_v, canvas)
    s_v["clip"] = dict(s_v["clip"], scale={"x": 1.0, "y": 1.0}, transform={"x": 0.0, "y": 0.0})
    fora = _velocidade(s_v, porcat, total_v, vel)
    raiz_d["tracks"] = [composto.trilha("trilha_video_modelo", [s_v])]
    mus = op.get("musica")
    if mus:
        s_m, m_m, _ = composto.instancia(composto.MOLDE["raiz"]["musica"], raiz_d["materials"])
        dur_m = int(round(mus["dur"] * 1e6))
        usa = min(fora, audio.quadro_us(np.floor(mus["dur"] * audio.FPS) / audio.FPS))
        m_m.update({"path": str(mus["path"]).replace("\\", "/"), "name": mus["nome"], "duration": dur_m})
        s_m["source_timerange"] = {"start": 0, "duration": usa}
        s_m["target_timerange"] = {"start": 0, "duration": usa}
        s_m["volume"] = s_m["last_nonzero_volume"] = round(10 ** (MUSICA_DB / 20), 6)
        raiz_d["tracks"].append(composto.trilha("trilha_audio_modelo", [s_m]))
    raiz_d["duration"] = fora
    raiz_d["materials"]["drafts"] = [ent_v, ent]          # entradas de TODOS os compostos na RAIZ (lista plana)

    try:                                                  # registra o iPad tambem na midia do projeto
        item = copy.deepcopy(meta["draft_materials"][0]["value"][0])
        item.update({"id": capcut.uid().lower(), "extra_info": mi["material_name"], "file_Path": mi["path"],
                     "duration": mi["duration"], "width": mi["width"], "height": mi["height"],
                     "roughcut_time_range": {"duration": mi["duration"], "start": 0}})
        meta["draft_materials"][0]["value"].append(item)
    except (KeyError, IndexError):
        pass
    return raiz_d, meta, [ent_v, ent]


# ---------------- verificacao (trava e avisa em vez de gravar projeto quebrado) ----------------
def verifica(raiz, pasta=None):
    erros = list(composto.verifica(raiz, pasta))          # estrutura dos compostos: entradas na raiz, refs, limites, subdraft
    ents = {e["id"]: e for e in raiz["materials"].get("drafts", [])}

    def mostra(d):                                        # compostos que a 1a trilha de video de d mostra
        v = [t for t in d.get("tracks", []) if t["type"] == "video"]
        refs = {s["extra_material_refs"][0] for s in (v[0]["segments"] if v else []) if s.get("extra_material_refs")}
        return [ents[r] for r in refs if r in ents]
    fin = mostra(raiz)
    if len(fin) != 1 or len(raiz["tracks"][0]["segments"]) != 1:
        return erros + ["a raiz precisa ter um único clipe composto (o vídeo final)"]
    dv = fin[0]["draft"]
    dentro = mostra(dv)
    if len(dentro) != 1 or len(ents) != 2:
        return erros + ["os cortes precisam ser todos do clipe composto iPad + pessoa"]
    d = dentro[0]["draft"]
    sv = raiz["tracks"][0]["segments"][0]
    if abs(sv["source_timerange"]["duration"] - dv["duration"]) > 1000 or abs(sv["speed"] * sv["target_timerange"]["duration"] - sv["source_timerange"]["duration"]) > 1000:
        erros.append("a velocidade do vídeo final não bate com a duração dele")
    if len(d["tracks"][0]["segments"]) > 1:
        erros.append("a pessoa ficou picada dentro do composto (deixa o projeto pesado)")
    for t in raiz["tracks"]:
        for s in t["segments"]:
            if t["type"] == "audio":
                m = {x["id"]: x for x in raiz["materials"].get("audios", [])}.get(s["material_id"], {})
                if m.get("path") and not Path(m["path"]).exists():
                    erros.append(f"música não encontrada: {m.get('name')}")
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
    for s in dv["tracks"][0]["segments"]:                 # cortes dentro do composto
        src = s["source_timerange"]
        if src["start"] < 0 or src["start"] + src["duration"] > d["duration"] + 1000:
            erros.append("um corte passa do fim do clipe composto")
    txt = {m["id"]: m for m in dv["materials"].get("texts", [])}
    tpls = {m["id"]: m for m in dv["materials"].get("text_templates", [])}
    for t in dv["tracks"]:
        if t["type"] != "text": continue
        for s in t["segments"]:
            m = txt.get(s["material_id"])
            if not m and s["material_id"] in tpls:        # legenda automatica: modelo -> texto de dentro
                ids = [r.get("text_material_id") for r in tpls[s["material_id"]].get("text_info_resources", [])]
                if not ids or any(i not in txt for i in ids):
                    erros.append("legenda automática aponta pra um texto que não existe"); continue
                m = txt[ids[0]]
            if not m: continue
            c = json.loads(m["content"]) if isinstance(m["content"], str) else m["content"]
            if s["clip"]["transform"]["y"] > 0:           # headline (em cima) dentro da tela
                maior = max(c["text"].split("\n"), key=len)
                if largura_px(maior, s["clip"]["scale"]["x"], "classic") * SEGURANCA > 1080 + 1:
                    erros.append(f"a headline '{maior}' sai da tela: use um texto mais curto")
            elif len(c["text"]) > FRASE_MAX * 1.5:        # legenda (embaixo): no maximo 2 linhas
                erros.append(f"legenda longa demais: '{c['text']}'")
    return sorted(set(erros))
