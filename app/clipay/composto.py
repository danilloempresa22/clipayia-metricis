"""Monta o projeto da LEGENDA COMPLEXA no formato do CapCut: clipes compostos aninhados.
Estrutura (igual as edicoes aprovadas, moldes em assets/moldes/legenda.json):
  RAIZ  trilha video -> segmento do composto "Corpo" (velocidade 1.15, fade-in)   + trilha de musica (opcional)
  Corpo trilha video -> segmento do composto "Cortes" (zoom aqui, num controle so)
        trilha video (sobreposicao) -> segmento do composto "Legenda"
  Cortes  os pedacos do video bruto            Legenda  as linhas de texto
REGRA QUE JA DEU "Midia perdida": a entrada de TODO composto mora em materials.drafts da RAIZ (lista plana).
Composto guarda so o placeholder (materials.videos, extra_type_option 2) e o segmento que aponta pro id da raiz."""
import copy, json, shutil, time
from pathlib import Path
from . import capcut, legenda

TOKEN = "##_draftpath_placeholder_0E685133-18CE-45ED-8CB8-2904A212EC80_##"     # macro do CapCut, nao e' id de projeto
MOLDE = json.loads((Path(__file__).resolve().parent / "assets" / "moldes" / "legenda.json").read_text(encoding="utf-8"))
FADE_IN_US = 3_666_666               # fade-in do Corpo nas edicoes aprovadas

# fontes do catalogo do CapCut (baixam sozinhas pelo id); so ids ja usados em projetos reais
FONTES = {
    "normal":   {"id": "7242301789909815863", "nome": "PublicSans Regular", "cor": [1, 1, 1]},
    "soco":     {"id": "7341281166273548801", "nome": "Kanit Black", "cor": [1, 0, 0]},
    "leve":     {"id": "7152810955380888065", "nome": "PublicSans Italic", "cor": [1, 1, 1]},
    "pergunta": {"id": "7152810955380888065", "nome": "PublicSans Italic", "cor": [1, 1, 1]},
}


class ErroMontagem(capcut.ErroProjeto):
    pass


def caminho_no_cache(rid, cache):
    """arquivo do recurso no cache do CapCut desta maquina; vazio = o CapCut baixa pelo id"""
    if cache:
        for f in sorted(Path(cache).glob(f"{rid}/*/*")):
            if f.suffix.lower() in (".ttf", ".otf"):
                return str(f).replace("\\", "/")
        d = sorted(p for p in Path(cache).glob(f"{rid}/*") if p.is_dir())
        if d: return str(d[0]).replace("\\", "/")
    return ""


# ---------------- pecas ----------------
def instancia(p, mats, drafts_id=None, sem=()):
    """copia de um segmento do molde + material principal + materiais das refs, tudo com ids novos"""
    seg = copy.deepcopy(p["segmento"]); seg["id"] = capcut.uid()
    cat, m = p["material"]
    m = copy.deepcopy(m); m["id"] = capcut.uid(); mats.setdefault(cat, []).append(m); seg["material_id"] = m["id"]
    refs, porcat = [], {}
    for cat, mm in p["refs"]:
        if cat in sem: continue
        if cat == "drafts":
            refs.append(drafts_id); continue
        mm = copy.deepcopy(mm); mm["id"] = capcut.uid(); mats.setdefault(cat, []).append(mm)
        refs.append(mm["id"]); porcat[cat] = mm
    seg["extra_material_refs"] = refs
    return seg, m, porcat


def trilha(modelo, segs, flag=0):
    t = copy.deepcopy(MOLDE[modelo]); t["id"] = capcut.uid(); t["flag"] = flag; t["segments"] = segs
    return t


def esqueleto(d):
    e = copy.deepcopy(d); e["tracks"] = []
    e["materials"] = {k: ([] if isinstance(v, list) else v) for k, v in d["materials"].items()}
    return e


def composto(nome, base, canvas, dur):
    """entrada da raiz (materials.drafts) com o draft aninhado dentro. id do draft = nome da pasta em subdraft/"""
    d = esqueleto(base); d["id"] = capcut.uid(); d["name"] = ""
    d["canvas_config"] = dict(d["canvas_config"], width=canvas[0], height=canvas[1])
    d["duration"] = dur
    e = copy.deepcopy(MOLDE["entrada_draft"])
    e.update({"id": capcut.uid(), "combination_id": capcut.uid(), "name": ""})
    for c, arq in (("draft_file_path", "draft_content.json"), ("draft_cover_path", "draft_cover.jpg"),
                   ("draft_config_path", "sub_draft_config.json")):
        e[c] = f"{TOKEN}\\subdraft\\{d['id']}\\{arq}"
    e["draft"] = d
    e["_nome"] = nome
    return e


def seg_composto(peca, alvo, mats, dur, canvas, sem=("video_effects", "material_animations")):
    """segmento que mostra o composto 'alvo' dentro de outro draft"""
    seg, ph, porcat = instancia(peca, mats, alvo["id"], sem)
    ph.update({"path": "", "extra_type_option": 2, "material_name": alvo["_nome"], "duration": dur,
               "width": canvas[0], "height": canvas[1]})
    seg["source_timerange"] = {"start": 0, "duration": dur}
    seg["target_timerange"] = {"start": 0, "duration": dur}
    seg["speed"] = 1.0
    seg["common_keyframes"] = []
    return seg, ph, porcat


def texto(mats, s, trilha_idx, cache):
    """um estado de uma linha: objeto de texto unico (o CapCut faz o espacamento entre as palavras)"""
    seg, m, _ = instancia(MOLDE["texto"], mats)
    f = FONTES[s["tipo"]]; caminho = caminho_no_cache(f["id"], cache)
    c = m["content"]; c = json.loads(c) if isinstance(c, str) else c
    st = copy.deepcopy(c["styles"][0])
    st["range"] = [0, len(s["txt"])]
    st["font"] = {"id": f["id"], "path": caminho}
    st["fill"]["content"]["solid"]["color"] = f["cor"]
    c.update({"text": s["txt"], "styles": [st]})
    m["content"] = json.dumps(c, ensure_ascii=False)
    m.update({"font_path": caminho, "font_resource_id": f["id"], "font_id": "", "font_name": "", "recognize_text": "",
              "text_color": "#%02x%02x%02x" % tuple(int(v * 255) for v in f["cor"])})
    if m.get("fonts"):
        m["fonts"] = [dict(m["fonts"][0], id=capcut.uid(), resource_id=f["id"], path=caminho)]
    if isinstance(m.get("words"), dict):
        m["words"] = {k: [] for k in m["words"]}
    ini, fim = int(round(s["ini"] * 1e6)), int(round(s["fim"] * 1e6))
    seg["target_timerange"] = {"start": ini, "duration": fim - ini}
    seg["clip"] = dict(seg["clip"], scale={"x": s["esc"], "y": s["esc"]}, transform={"x": s["x"], "y": s["y"]})
    seg["track_render_index"] = trilha_idx
    seg["render_index"] = 14000 + trilha_idx
    return seg


def empacota(segs):
    """poucas trilhas: cada texto vai na primeira trilha livre no intervalo"""
    trilhas = []
    for s in sorted(segs, key=lambda s: s["target_timerange"]["start"]):
        a = s["target_timerange"]["start"]
        for t in trilhas:
            u = t[-1]["target_timerange"]
            if u["start"] + u["duration"] <= a:
                t.append(s); break
        else:
            trilhas.append([s])
    return trilhas


# ---------------- projeto ----------------
def monta(base, meta, keep, segs_leg, op, cache):
    """base/meta = capcut.cria_draft do video bruto (1 clipe). keep = pedacos mantidos [[a,b]] em s na origem.
    segs_leg = legenda.monta(...). op: zoom (None|escala), velocidade, musica {path,nome,dur,volume}.
    Devolve (raiz, compostos) — compostos = entradas da raiz, pra gravar as pastas subdraft."""
    canvas = (base["canvas_config"]["width"], base["canvas_config"]["height"])
    total = int(round(sum(b - a for a, b in keep) * 1e6))
    if total <= 0:
        raise ErroMontagem("Não sobrou nenhum trecho de fala depois dos cortes.")

    # --- Cortes: os pedacos do video bruto, cada um com material proprio (o CapCut exige)
    e_cortes = composto("Cortes", base, canvas, total)
    dc = e_cortes["draft"]; dc["materials"] = copy.deepcopy(base["materials"])
    idx = capcut.indice_materiais(dc["materials"])
    orig = capcut.trilha_principal(base)["segments"][0]
    novos, cur = [], 0
    for a, b in keep:
        ns = capcut.clona_segmento(orig, idx, dc["materials"])
        A, B = int(round(a * 1e6)), int(round(b * 1e6))
        ns["source_timerange"] = {"start": A, "duration": B - A}
        ns["target_timerange"] = {"start": cur, "duration": B - A}
        ns["common_keyframes"] = []
        novos.append(ns); cur += B - A
    dc["tracks"] = [dict(copy.deepcopy(capcut.trilha_principal(base)), id=capcut.uid(), segments=novos)]
    dc["duration"] = cur
    capcut.poda(dc)
    dc["materials"]["videos"] = [v for v in dc["materials"]["videos"] if v["id"] in {s["material_id"] for s in novos}]

    # --- Legenda: as linhas de texto em poucas trilhas (a 1a trilha de video fica vazia, como no CapCut)
    e_leg = composto("Legenda", MOLDE["composto"]["legenda"], canvas, total)
    dl = e_leg["draft"]
    tsegs = [texto(dl["materials"], s, 0, cache) for s in segs_leg]
    pilhas = empacota(tsegs)
    dl["tracks"] = [trilha("trilha_video_modelo", [])]
    for i, p in enumerate(pilhas):
        for s in p:
            s["track_render_index"] = i + 1; s["render_index"] = 14000 + i + 1
        dl["tracks"].append(trilha("trilha_modelo", p))

    # --- Corpo: Cortes na trilha principal (com o zoom) + Legenda por cima
    e_corpo = composto("Corpo", MOLDE["composto"]["corpo"], canvas, total)
    dco = e_corpo["draft"]
    s_cortes, _, _ = seg_composto(MOLDE["dentro_corpo"]["cortes"], e_cortes, dco["materials"], total, canvas)
    if op.get("zoom"):
        z = float(op["zoom"])
        s_cortes["clip"] = dict(s_cortes["clip"], scale={"x": z, "y": z}, transform={"x": 0.0, "y": 0.0})
    else:
        s_cortes["clip"] = dict(s_cortes["clip"], scale={"x": 1.0, "y": 1.0}, transform={"x": 0.0, "y": 0.0})
    # a legenda leva o efeito das edicoes aprovadas (Estroboscopio de tremor, mesmos parametros do molde)
    s_leg, _, porcat = seg_composto(MOLDE["dentro_corpo"]["legenda"], e_leg, dco["materials"], total, canvas,
                                    sem=("material_animations",))
    s_leg["clip"] = dict(s_leg["clip"], scale={"x": 1.0, "y": 1.0}, transform={"x": 0.0, "y": 0.0})
    if "video_effects" in porcat:
        ef = porcat["video_effects"]
        ef["path"] = caminho_no_cache(ef.get("resource_id") or ef.get("effect_id", ""), cache)
    dco["tracks"] = [trilha("trilha_video_modelo", [s_cortes]), trilha("trilha_video_modelo", [s_leg], flag=2)]

    # --- Raiz: Corpo acelerado + fade-in (+ musica)
    vel = float(op.get("velocidade") or 1.15)
    fora = int(round(total / vel))
    raiz = esqueleto(base)
    raiz["id"] = capcut.uid()
    s_corpo, _, porcat = seg_composto(MOLDE["raiz"]["corpo"], e_corpo, raiz["materials"], total, canvas, sem=("video_effects",))
    s_corpo["speed"] = vel
    s_corpo["target_timerange"] = {"start": 0, "duration": fora}
    if "speeds" in porcat: porcat["speeds"]["speed"] = vel
    if "material_animations" in porcat:
        for an in porcat["material_animations"].get("animations", []):
            an["duration"] = min(FADE_IN_US, total // 3)
            an["path"] = caminho_no_cache(an.get("resource_id", ""), cache)
    raiz["tracks"] = [trilha("trilha_video_modelo", [s_corpo])]
    mus = op.get("musica")
    if mus:
        s_m, m_m, _ = instancia(MOLDE["raiz"]["musica"], raiz["materials"])
        dur_m = int(round(mus["dur"] * 1e6))
        usa = min(fora, dur_m)
        m_m.update({"path": str(mus["path"]).replace("\\", "/"), "name": mus["nome"], "duration": dur_m})
        s_m["source_timerange"] = {"start": 0, "duration": usa}
        s_m["target_timerange"] = {"start": 0, "duration": usa}
        s_m["volume"] = float(mus["volume"])
        raiz["tracks"].append(trilha("trilha_audio_modelo", [s_m]))
    raiz["duration"] = fora
    compostos = [e_corpo, e_cortes, e_leg]
    raiz["materials"]["drafts"] = compostos                  # LISTA PLANA NA RAIZ (bug da "Midia perdida")
    return raiz, compostos


# ---------------- checklist obrigatoria (trava em vez de gravar projeto quebrado) ----------------
def _refs_ok(d, ids_raiz, rot):
    erros = []
    loc = set(capcut.indice_materiais(d["materials"]))
    for t in d["tracks"]:
        segs = sorted(t["segments"], key=lambda s: s["target_timerange"]["start"])
        for s in segs:
            if s["material_id"] not in loc:
                erros.append(f"{rot}: segmento aponta pra material que não existe")
            for r in s.get("extra_material_refs", []):
                if r not in loc and r not in ids_raiz:
                    erros.append(f"{rot}: referência solta")
            tt = s["target_timerange"]
            if tt["start"] < 0 or tt["start"] + tt["duration"] > d["duration"] + 1000:
                erros.append(f"{rot}: segmento passa do fim ({(tt['start'] + tt['duration']) / 1e6:.2f}s > {d['duration'] / 1e6:.2f}s)")
        for p, q in zip(segs, segs[1:]):
            if p["target_timerange"]["start"] + p["target_timerange"]["duration"] > q["target_timerange"]["start"]:
                erros.append(f"{rot}: dois segmentos na mesma trilha ao mesmo tempo")
    return erros


def verifica(raiz, pasta=None):
    """itens da especificacao: 1 Y, 2 estilos, 3 referencias, 4 limites, 5 largura, 6 compostos (+ pasta em disco)"""
    erros = []
    entradas = raiz["materials"].get("drafts", [])
    ids_raiz = {e["id"] for e in entradas}
    erros += _refs_ok(raiz, ids_raiz, "raiz")
    for e in entradas:
        d = e.get("draft") or {}
        rot = f"composto {e.get('_nome') or e['id'][:8]}"
        if d.get("materials", {}).get("drafts"):
            erros.append(f"{rot}: guarda compostos dentro de si (tem que ficar na raiz — causa 'Mídia perdida')")
        if d.get("id", "") not in e.get("draft_file_path", "") or TOKEN not in e.get("draft_file_path", ""):
            erros.append(f"{rot}: caminho da pasta do composto inconsistente")
        erros += _refs_ok(d, ids_raiz, rot)
        if pasta is not None:
            sub = Path(pasta) / "subdraft" / d.get("id", "?")
            for arq in ("draft_content.json", "sub_draft_config.json"):
                if not (sub / arq).exists():
                    erros.append(f"{rot}: falta subdraft/{d.get('id', '?')[:8]}/{arq}")
        # 2. estilos cobrindo o texto inteiro + reconstroi a legenda pra checar 1 e 5 NO JSON FINAL
        txt = {m["id"]: m for m in d.get("materials", {}).get("texts", [])}
        segs = []
        for t in d.get("tracks", []):
            for s in t["segments"]:
                m = txt.get(s["material_id"])
                if not m: continue
                c = json.loads(m["content"]) if isinstance(m["content"], str) else m["content"]
                n = len(c["text"]); cob = set()
                for st in c.get("styles", []):
                    a, b = st["range"]
                    if a < 0 or b > n or a >= b: erros.append(f"{rot}: faixa de estilo fora do texto '{c['text']}'")
                    cob.update(range(max(0, a), min(n, b)))
                if len(cob) != n: erros.append(f"{rot}: parte do texto '{c['text']}' sem estilo")
                tt = s["target_timerange"]
                segs.append({"txt": c["text"], "ini": tt["start"] / 1e6, "fim": (tt["start"] + tt["duration"]) / 1e6,
                             "x": s["clip"]["transform"]["x"], "y": s["clip"]["transform"]["y"], "esc": s["clip"]["scale"]["x"]})
        erros += [f"{rot}: {x}" for x in legenda.verifica(segs, d.get("duration", 0) / 1e6)]
    # 6. todo segmento de composto aponta (1a ref) pra uma entrada da raiz
    todos = [raiz] + [e.get("draft") or {} for e in entradas]
    for d in todos:
        ph = {v["id"] for v in d.get("materials", {}).get("videos", []) if v.get("extra_type_option") == 2}
        for t in d.get("tracks", []):
            for s in t["segments"]:
                if s["material_id"] in ph:
                    r = s.get("extra_material_refs", [])
                    if not r or r[0] not in ids_raiz:
                        erros.append("segmento de composto sem entrada correspondente na raiz")
    return sorted(set(erros))


# ---------------- disco: pastas subdraft ----------------
def grava_subdrafts(pasta, compostos, capa=None):
    """cada composto tem subdraft/<id>/ com draft_content.json (stub que referencia a si mesmo),
    sub_draft_config.json e draft_cover.jpg"""
    agora = time.time()
    for e in compostos:
        d = e["draft"]; fid = d["id"]
        sub = Path(pasta) / "subdraft" / fid
        sub.mkdir(parents=True, exist_ok=True)
        canvas = (d["canvas_config"]["width"], d["canvas_config"]["height"])
        stub = esqueleto(MOLDE["stub"]["esqueleto"]); stub["id"] = capcut.uid()
        seg, _, _ = seg_composto(MOLDE["stub"]["segmento"], e, stub["materials"], d["duration"], canvas, sem=())
        stub["tracks"] = [trilha("trilha_video_modelo", [seg])]
        abs_ = str(Path(pasta)).replace("\\", "/")
        propria = {k: v for k, v in e.items() if not k.startswith("_")}
        for c, arq in (("draft_file_path", "draft_content.json"), ("draft_cover_path", "draft_cover.jpg"),
                       ("draft_config_path", "sub_draft_config.json")):
            propria[c] = f"{abs_}\\subdraft\\{fid}\\{arq}"
        stub["materials"]["drafts"] = [propria]
        (sub / "draft_content.json").write_text(json.dumps(stub, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        cfg = dict(MOLDE["sub_draft_config"], id=fid, project_id=fid, name=e["_nome"], rough_cut_duration=d["duration"],
                   rough_cut_start=0, create_time=int(agora), import_time_ms=int(agora * 1000))
        (sub / "sub_draft_config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        if capa and Path(capa).exists():
            shutil.copy(capa, sub / "draft_cover.jpg")


def limpa_para_gravar(raiz):
    """tira os campos internos (_nome) antes de ir pro disco"""
    r = copy.deepcopy(raiz)
    for e in r["materials"].get("drafts", []):
        for k in [k for k in e if k.startswith("_")]: del e[k]
    return r
