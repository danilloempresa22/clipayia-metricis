"""Modo ROTINA (vlog de rotina do Ale): cortes, relogio falso no canto superior direito que pula o horario a cada
corte, headline no comeco, velocidade 1,13x em cada segmento (sem clipe composto), filtro Aprimorar e musica com
abaixamento na fala. Sem IA em decisao criativa: headline, onde a atividade muda e o tamanho de cada salto do
relogio sao do usuario; o app so aplica e mostra a lista pra corrigir.
Especificacao: docs/design/rotina-especificacao.md."""
import copy, json, re
import numpy as np
from pathlib import Path
from . import audio, capcut, composto, legenda, reels, ipad

VELOCIDADE = 1.13
FILTRO_ID = "7289393505166692866"           # Aprimorar
FILTRO_INTENSIDADE = 60
SALTO_PADRAO = 2                            # min, "mesma cena" (o usuario edita de 1 a 3)
SALTO_MAX = 720                             # min: passo maior que isso entre dois trechos = horario voltou
MARGEM = 0.04                               # do relogio ate a borda de cima e a da direita (fracao da tela)
SEGURANCA = 1.3                             # fator na largura do texto (fonte real mais larga que a estimativa)
ESC_RELOGIO = 0.5
ESC_HEADLINE = ipad.ESC_HEADLINE            # fonte Classic, mesma escala do Cortes + Headline
HEADLINE_S = 5.0
VOLUME = {"silencio": 1.0, "fala": 0.21, "rampa": 0.5}      # rampa de 0,4 a 0,8 s
JUNTA_FALA = 0.6                            # pausa menor que isso entre falas: a musica nao sobe no meio

# fontes do catalogo do CapCut (baixam pelo id); ids ja usados em projetos reais desta maquina
FONTES_RELOGIO = {
    "kanit":   {"id": "7341281166273548801", "nome": "Kanit Black"},
    "public":  {"id": "7242301789909815863", "nome": "Public Sans"},
    "classic": {"id": "7545362071773367568", "nome": "Classic"},
}
FONTE_PADRAO = "kanit"

MOLDE = json.loads((Path(__file__).resolve().parent / "assets" / "moldes" / "rotina.json").read_text(encoding="utf-8"))
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


# ---------------- cortes ----------------
def cortes(palavras, dur, silencio_ms=250, minimo_s=0.0):
    """regua do corte por palavra (a mesma da Legenda Complexa: 250 ms, folga 60 ms / 150-200 ms em palavra curta,
    sem gaguejada nem muleta isolada). Trecho mais curto que minimo_s e' juntado ao vizinho mais perto (pausa curta),
    nunca apagado: fala nao some."""
    keep, _ = legenda.cortes(palavras, dur, corte_min=silencio_ms / 1000.0)
    return junta_curtos(keep, minimo_s)


def cortes_takes(takes, silencio_ms=250, minimo_s=0.0):
    """varios takes em ordem -> [[take, a, b]]. Take sem fala (so imagem) entra inteiro."""
    out = []
    for i, tk in enumerate(takes):
        dur = tk["info"]["duracao"]
        k = cortes(tk["palavras"], dur, silencio_ms, minimo_s) if tk["palavras"] else []
        out += [[i, a, b] for a, b in (k or [[0.0, float(np.floor(dur * audio.FPS) / audio.FPS)]])]
    return out


def mascara_fala(e, v):
    porta = audio.porta_de(e, v)
    return audio.tom_sustentado(e, v, porta) | (e > porta + 8.0)


def junta_curtos(keep, minimo, pausa_max=1.0):
    k = [list(x) for x in keep]
    if minimo <= 0:
        return k
    mudou = True
    while mudou and len(k) > 1:
        mudou = False
        for i, (a, b) in enumerate(k):
            if b - a >= minimo: continue
            ant = a - k[i - 1][1] if i > 0 else 1e9
            dep = k[i + 1][0] - b if i + 1 < len(k) else 1e9
            if min(ant, dep) > pausa_max: continue
            j = i - 1 if ant <= dep else i + 1
            lo, hi = min(i, j), max(i, j)
            k[lo] = [k[lo][0], k[hi][1]]; del k[hi]
            mudou = True; break
    return k


# ---------------- relogio ----------------
def minutos(hhmm):
    m = _HHMM.match((hhmm or "").strip())
    if not m:
        raise capcut.ErroProjeto("Horário inicial inválido. Use o formato HH:MM (ex.: 07:30).")
    return int(m[1]) * 60 + int(m[2])


def hhmm(m):
    m = int(m) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def horarios(inicio, saltos):
    """inicio 'HH:MM'; saltos[i] = minutos somados ANTES do trecho i (saltos[0] e' ignorado: o 1o mostra o inicio).
    Devolve os horarios 'HH:MM' (vira a hora e a meia-noite)."""
    m = minutos(inicio); out = []
    for i, s in enumerate(saltos):
        if i:
            s = int(s)
            if not 1 <= s <= SALTO_MAX:
                raise capcut.ErroProjeto(f"O salto do trecho {i + 1} precisa ser de 1 a {SALTO_MAX} minutos.")
            m += s
        out.append(hhmm(m))
    return out


# ---------------- tempo na timeline (velocidade exata) ----------------
def linha_do_tempo(keep, vel=VELOCIDADE):
    """[(src_inicio, src_dur, tl_inicio, tl_dur)] em us. A timeline fica em quadros inteiros e src = tl x vel:
    todos os segmentos com a MESMA velocidade e o CapCut nao mexe (fora da grade ele reajusta a velocidade)."""
    out, q = [], 0
    for a, b in keep:
        n = max(1, int(np.floor((b - a) * audio.FPS / vel + 1e-6)))     # para baixo: o source nunca passa do trecho
        T0, T1 = audio.quadro_us(q / audio.FPS), audio.quadro_us((q + n) / audio.FPS)
        S0 = audio.quadro_us(a)
        out.append((S0, int(round((T1 - T0) * vel)), T0, T1 - T0)); q += n
    return out


def falas_na_timeline(mascaras, trechos, tl, vel=VELOCIDADE):
    """intervalos de fala (s) na timeline final, pela mesma deteccao de audio dos cortes.
    mascaras[take] = fala quadro a quadro do audio daquele take; trechos = [[take, a, b]]"""
    out = []
    for (tk, a, b), (S0, Sd, T0, _) in zip(trechos, tl):
        fala = mascaras[tk]
        for i, j in audio.runs(fala[int(a / audio.H):int(b / audio.H) + 1]):
            x0 = a + i * audio.H; x1 = min(b, a + j * audio.H)
            t0 = T0 / 1e6 + (x0 - a) / vel; t1 = T0 / 1e6 + (x1 - a) / vel
            if out and t0 - out[-1][1] < JUNTA_FALA: out[-1][1] = t1
            elif t1 > t0: out.append([t0, t1])
    return out


def volume_keyframes(falas, total_s, silencio, fala, rampa):
    """(tempo us, volume) — a musica desce pra 'fala' durante a fala e volta pra 'silencio' nas pausas"""
    pts = [(0.0, silencio)]
    for a, b in falas:
        d0, s1 = a - rampa, min(total_s, b + rampa)
        if d0 <= 0 and len(pts) == 1:                      # fala logo no comeco: a musica ja entra baixa
            pts = [(0.0, fala)]
        elif len(pts) > 1 and pts[-1][0] >= d0:            # a subida da fala anterior encosta na descida desta: fica baixo
            pts.pop()
        else:
            pts.append((d0, silencio))
        pts += [(a, fala), (b, fala), (s1, silencio)]
    pts = [(t, v) for t, v in pts if t <= total_s]
    limpo = []
    for t, v in pts:                                       # tempos estritamente crescentes
        if limpo and t <= limpo[-1][0] + 1e-4:
            limpo[-1] = (limpo[-1][0], v)
        else:
            limpo.append((t, v))
    limpo = [p for i, p in enumerate(limpo)                # ponto no meio de um trecho de volume constante nao muda nada
             if i in (0, len(limpo) - 1) or not (limpo[i - 1][1] == p[1] == limpo[i + 1][1])]
    return [(int(round(t * 1e6)), float(v)) for t, v in limpo]


# ---------------- layout (unidades do CapCut: tela inteira = 2.0) ----------------
def _fator(canvas):
    """medidas de texto calibradas em 1080x1920; o texto do CapCut acompanha o lado menor"""
    return min(canvas) / 1080


def caixa_relogio(txt, esc, canvas, seguranca=1.0):
    w = legenda.largura_tela(txt, esc) * _fator(canvas) * 1080 / canvas[0] * seguranca
    h = legenda.ALT_LINHA * esc / legenda.ESC_BASE * _fator(canvas) * 1920 / canvas[1]
    return w, h


def pos_relogio(esc, canvas, txt="00:00"):
    w, h = caixa_relogio(txt, esc, canvas)
    return round(1 - 2 * MARGEM - w / 2, 6), round(1 - 2 * MARGEM - h / 2, 6)


def caixa_headline(txt, esc, canvas, seguranca=1.0):
    linhas = txt.split("\n")
    w = max(ipad.largura_px(l, esc, "classic") for l in linhas) * _fator(canvas) / (canvas[0] / 2) * seguranca
    h = len(linhas) * 1.25 * ipad.PX_POR_EM * esc * _fator(canvas) / (canvas[1] / 2)
    return w, h


def y_headline(txt, canvas, esc_rel, esc_h=ESC_HEADLINE):
    """centralizada, logo abaixo da zona do relogio (folga de 2% da tela)"""
    _, hr = caixa_relogio("00:00", esc_rel, canvas)
    _, hh = caixa_headline(txt, esc_h, canvas)
    return round(1 - 2 * MARGEM - hr - 0.04 - hh / 2, 6)


# ---------------- pecas ----------------
def fonte_no_cache(chave, cache):
    """(id, caminho no cache ou '') da fonte do relogio"""
    f = FONTES_RELOGIO.get(chave) or FONTES_RELOGIO[FONTE_PADRAO]
    return f["id"], composto.caminho_no_cache(f["id"], cache)


def texto_relogio(mats, txt, T0, Td, x, y, esc, fid, caminho):
    seg, m, _ = composto.instancia(composto.MOLDE["texto"], mats)
    c = m["content"]; c = json.loads(c) if isinstance(c, str) else c
    st = copy.deepcopy(c["styles"][0])
    st["range"] = [0, len(txt)]; st["font"] = {"id": fid, "path": caminho}
    st["fill"]["content"]["solid"]["color"] = [1, 1, 1]
    c.update({"text": txt, "styles": [st]})
    m["content"] = json.dumps(c, ensure_ascii=False)
    m.update({"font_path": caminho, "font_resource_id": fid, "font_id": "", "font_name": "", "recognize_text": "",
              "text_color": "#ffffff"})
    if m.get("fonts"):
        m["fonts"] = [dict(m["fonts"][0], id=capcut.uid(), resource_id=fid, path=caminho)]
    if isinstance(m.get("words"), dict):
        m["words"] = {k: [] for k in m["words"]}
    seg["target_timerange"] = {"start": T0, "duration": Td}
    seg["clip"] = dict(seg["clip"], scale={"x": esc, "y": esc}, transform={"x": x, "y": y})
    seg["track_render_index"] = 2; seg["render_index"] = 14002
    seg["common_keyframes"] = []
    return seg


def monta(raiz, an, op):
    """an: analise (takes [{video, info, palavras, e, v}], draft e meta do 1o take). op: trechos [[take, a, b]]
    (s na origem do take), inicio 'HH:MM', saltos [min por trecho], headline, headline_s, headline_ini, fonte,
    escala, musica {path,nome,dur} ou None, volume {silencio, fala, rampa}, filtro (bool). Devolve (draft, meta, avisos)."""
    takes = an["takes"]
    trechos = [[int(t), float(a), float(b)] for t, a, b in op["trechos"]]
    if any(not 0 <= t < len(takes) for t, _, _ in trechos):
        raise capcut.ErroProjeto("Um trecho aponta para um vídeo que não está na lista. Escolha os vídeos de novo.")
    keep = [[a, b] for _, a, b in trechos]
    if not keep:
        raise capcut.ErroProjeto("Não sobrou nenhum trecho. Volte e mantenha pelo menos um.")
    saltos = list(op.get("saltos") or [SALTO_PADRAO] * len(keep))
    if len(saltos) != len(keep):
        raise capcut.ErroProjeto("A lista do relógio não bate com os trechos. Volte à tela do relógio.")
    horas = horarios(op.get("inicio") or "07:30", saltos)
    cache = capcut.cache_efeitos(raiz)
    avisos = []
    d = copy.deepcopy(an["draft"]); meta = copy.deepcopy(an["meta"])
    canvas = (d["canvas_config"]["width"], d["canvas_config"]["height"])
    mats = d["materials"]; idx = capcut.indice_materiais(mats)
    vt = capcut.trilha_principal(d); orig = vt["segments"][0]
    tl = linha_do_tempo(keep)

    # --- video: um segmento por trecho, todos a 1,13x; cada segmento com o material do seu take
    segs = []
    for (tk, _, _), (S0, Sd, T0, Td) in zip(trechos, tl):
        ns = capcut.clona_segmento(orig, idx, mats)
        if tk:
            v, info = Path(takes[tk]["video"]), takes[tk]["info"]
            m = next(x for x in mats["videos"] if x["id"] == ns["material_id"])
            m.update({"path": str(v.resolve()).replace("\\", "/"), "material_name": v.name, "duration": int(round(info["duracao"] * 1e6)),
                      "width": info["largura"], "height": info["altura"], "has_audio": info["tem_audio"],
                      "local_material_id": "", "unique_id": ""})
        ns["source_timerange"] = {"start": S0, "duration": Sd}
        ns["target_timerange"] = {"start": T0, "duration": Td}
        ns["speed"] = VELOCIDADE; ns["common_keyframes"] = []
        for r in ns["extra_material_refs"]:
            for sp in mats.get("speeds", []):
                if sp["id"] == r: sp["speed"] = VELOCIDADE
        segs.append(ns)
    vt["segments"] = segs
    total = tl[-1][2] + tl[-1][3]
    d["duration"] = total
    d["tracks"] = [vt]

    # --- relogio: um texto por trecho, mesma posicao/fonte/tamanho
    esc = float(op.get("escala") or ESC_RELOGIO)
    fid, caminho = fonte_no_cache(op.get("fonte") or FONTE_PADRAO, cache)
    nome_f = (FONTES_RELOGIO.get(op.get("fonte")) or FONTES_RELOGIO[FONTE_PADRAO])["nome"]
    if (op.get("fonte") or FONTE_PADRAO) not in FONTES_RELOGIO:
        avisos.append(f"A fonte escolhida para o relógio não existe no catálogo: usei {nome_f}.")
    elif not caminho:
        avisos.append(f"A fonte {nome_f} ainda não foi baixada pelo CapCut neste computador: ele baixa ao abrir o "
                      f"projeto. Se não conseguir, o relógio aparece com a fonte padrão — confira.")
    x, y = pos_relogio(esc, canvas)
    rel = [texto_relogio(mats, h, T0, Td, x, y, esc, fid, caminho) for h, (_, _, T0, Td) in zip(horas, tl)]
    d["tracks"].append(composto.trilha("trilha_modelo", rel))

    # --- headline: Classic, no comeco (ajustavel), abaixo do relogio
    texto_h = (op.get("headline") or "").strip()
    if texto_h:
        texto_h = reels.quebra_2_linhas(texto_h)
        th = reels.headline(mats, reels.carrega_tpl(cache), texto_h, total)
        ini = min(audio.quadro_us(float(op.get("headline_ini") or 0.0)), total - audio.quadro_us(1 / audio.FPS))
        dur = min(total - ini, audio.quadro_us(float(op.get("headline_s") or HEADLINE_S)))
        for s in th["segments"]:
            s["target_timerange"] = {"start": ini, "duration": dur}
            s["clip"] = dict(s["clip"], scale={"x": ESC_HEADLINE, "y": ESC_HEADLINE},
                             transform={"x": 0.0, "y": y_headline(texto_h, canvas, esc)})
        d["tracks"].append(th)

    # --- filtro Aprimorar, o video todo
    if op.get("filtro", True):
        f = copy.deepcopy(MOLDE["filtro"]); f["id"] = capcut.uid()
        f["path"] = composto.caminho_no_cache(FILTRO_ID, cache)
        f["value"] = FILTRO_INTENSIDADE / 100
        mats.setdefault("effects", []).append(f)
        sf = copy.deepcopy(MOLDE["segmento_filtro"]); sf["id"] = capcut.uid(); sf["material_id"] = f["id"]
        sf["target_timerange"] = {"start": 0, "duration": total}
        d["tracks"].append(dict(copy.deepcopy(MOLDE["trilha_filtro"]), id=capcut.uid(), segments=[sf]))

    # --- musica com abaixamento na fala (keyframes de volume)
    mus = op.get("musica")
    if mus:
        vol = dict(VOLUME, **{k: float(v) for k, v in (op.get("volume") or {}).items() if v is not None})
        s_m, m_m, _ = composto.instancia(composto.MOLDE["raiz"]["musica"], mats)
        usa = min(total, audio.quadro_us(np.floor(mus["dur"] * audio.FPS) / audio.FPS))
        m_m.update({"path": str(mus["path"]).replace("\\", "/"), "name": mus["nome"], "duration": int(round(mus["dur"] * 1e6))})
        s_m["source_timerange"] = {"start": 0, "duration": usa}
        s_m["target_timerange"] = {"start": 0, "duration": usa}
        s_m["volume"] = s_m["last_nonzero_volume"] = vol["silencio"]
        falas = falas_na_timeline([mascara_fala(tk["e"], tk["v"]) for tk in takes], trechos, tl)
        pts = [(t, v) for t, v in volume_keyframes(falas, usa / 1e6, vol["silencio"], vol["fala"], vol["rampa"]) if t <= usa]
        s_m["common_keyframes"] = [ipad._kf("KFTypeVolume", pts)] if len(pts) > 1 else []
        d["tracks"].append(composto.trilha("trilha_audio_modelo", [s_m]))
        if usa < total - 1000:
            avisos.append("A música é mais curta que o vídeo: ela acaba antes do fim.")
    for tk in takes[1:]:                                   # os outros takes tambem na midia do projeto
        try:
            item = copy.deepcopy(meta["draft_materials"][0]["value"][0]); v = Path(tk["video"])
            item.update({"id": capcut.uid().lower(), "extra_info": v.name, "file_Path": str(v.resolve()).replace("\\", "/"),
                         "duration": int(round(tk["info"]["duracao"] * 1e6)), "width": tk["info"]["largura"],
                         "height": tk["info"]["altura"], "roughcut_time_range": {"duration": int(round(tk["info"]["duracao"] * 1e6)), "start": 0}})
            meta["draft_materials"][0]["value"].append(item)
        except (KeyError, IndexError):
            pass
    capcut.poda(d)
    return d, meta, avisos


# ---------------- verificacao (trava e avisa em vez de gravar projeto quebrado) ----------------
def _texto(m):
    c = m["content"]; c = json.loads(c) if isinstance(c, str) else c
    return c["text"]


def verifica(d):
    erros = list(capcut.verifica(d))                       # refs, sobreposicao no trilho, source alem do arquivo
    canvas = (d["canvas_config"]["width"], d["canvas_config"]["height"])
    vids = [t for t in d["tracks"] if t["type"] == "video"]
    if len(vids) != 1 or not vids[0]["segments"]:
        return sorted(set(erros + ["o projeto precisa ter uma trilha de vídeo com os trechos"]))
    vs = sorted(vids[0]["segments"], key=lambda s: s["target_timerange"]["start"])
    fim = lambda s: s["target_timerange"]["start"] + s["target_timerange"]["duration"]
    # 1. nada passa do projeto
    for t in d["tracks"]:
        for s in t["segments"]:
            if s["target_timerange"]["start"] < 0 or fim(s) > d["duration"] + 1000:
                erros.append("um trecho passa da duração do projeto")
    # 6. mesma velocidade em todos e timeline calculada com ela
    vels = {round(s["speed"], 6) for s in vs}
    if len(vels) != 1:
        erros.append("os trechos estão com velocidades diferentes")
    for s in vs:
        if abs(s["source_timerange"]["duration"] - s["target_timerange"]["duration"] * s["speed"]) > 2:
            erros.append("a duração de um trecho não bate com a velocidade")
    sps = {x["id"]: x for x in d["materials"].get("speeds", [])}
    for s in vs:
        for r in s.get("extra_material_refs", []):
            if r in sps and abs(sps[r]["speed"] - s["speed"]) > 1e-9:
                erros.append("a velocidade do trecho e a do material de velocidade são diferentes")
    # 2/3/5. relogio
    txt = {m["id"]: m for m in d["materials"].get("texts", [])}
    rel, outros = [], []
    for t in d["tracks"]:
        if t["type"] != "text": continue
        for s in t["segments"]:
            if s["material_id"] in txt:
                (rel if _HHMM.match(_texto(txt[s["material_id"]])) else outros).append(s)
    rel.sort(key=lambda s: s["target_timerange"]["start"])
    if len(rel) != len(vs):
        erros.append(f"o relógio tem {len(rel)} textos para {len(vs)} trechos (precisa ser um por trecho)")
    else:
        for r, s in zip(rel, vs):
            if r["target_timerange"] != s["target_timerange"]:
                erros.append("o relógio tem buraco ou sobreposição em relação aos trechos"); break
    if len({json.dumps((s["clip"]["transform"], s["clip"]["scale"]), sort_keys=True) for s in rel}) > 1:
        erros.append("os textos do relógio não estão todos na mesma posição e tamanho")
    hs = [minutos(_texto(txt[s["material_id"]])) for s in rel]
    for i in range(1, len(hs)):
        if not 1 <= (hs[i] - hs[i - 1]) % 1440 <= SALTO_MAX:
            erros.append(f"o horário volta ou não muda no trecho {i + 1} ({hhmm(hs[i - 1])} → {hhmm(hs[i])})")
    caixas = []
    for s in rel[:1]:
        w, h = caixa_relogio(_texto(txt[s["material_id"]]), s["clip"]["scale"]["x"], canvas, SEGURANCA)
        caixas.append(("relógio", s, w, h))
    for s in outros:
        w, h = caixa_headline(_texto(txt[s["material_id"]]), s["clip"]["scale"]["x"], canvas, SEGURANCA)
        caixas.append(("headline", s, w, h))
    box = {}
    for nome, s, w, h in caixas:
        x, y = s["clip"]["transform"]["x"], s["clip"]["transform"]["y"]
        x0, x1, y0, y1 = x - w / 2, x + w / 2, y - h / 2, y + h / 2
        if x0 < -1 or x1 > 1 or y0 < -1 or y1 > 1:
            erros.append(f"o texto do {nome} sai da tela")
        box[nome] = (x0, x1, y0, y1)
    if "relógio" in box and "headline" in box:
        a, b = box["relógio"], box["headline"]
        if min(a[1], b[1]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[2], b[2]):
            erros.append("o relógio e a headline se sobrepõem")
    # 4. arquivos existem
    for v in d["materials"].get("videos", []):
        if v.get("path") and not Path(v["path"]).exists():
            erros.append(f"vídeo não encontrado: {v.get('material_name')}")
    for a in d["materials"].get("audios", []):
        if a.get("path") and not Path(a["path"]).exists():
            erros.append(f"música não encontrada: {a.get('name')}")
    return sorted(set(erros))
