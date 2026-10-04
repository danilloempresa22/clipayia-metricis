"""Modo CORTES (Fase 1, sem IA): monta UM corte de podcast igual ao projeto feito a mao
(docs/design/referencia-cortes, copiado em assets/cortes/template). Dado o video e o intervalo [ini, fim] em s:
  RAIZ (9:16)  trilha video -> composto 1:1 (velocidade 1,13x, y -0,128, efeito Estroboscopio de tremor)
               trilha texto -> headline de exemplo (a pessoa troca no CapCut)   + trilha da musica (opcional)
  COMPOSTO     os pedacos do corte seco do video original (source_timerange, sem copiar o arquivo), com zoom
O template e' copiado e so muda o que varia (pedacos, tempos, caminhos, musica, ids). O rascunho do composto
sai IDENTICO em materials.drafts[0].draft e em subdraft/<id>/draft_content.json (senao: "Midia perdida").
Numeros do modelo em assets/cortes/modelos/<modelo>.json."""
import copy, json, re, time, uuid
from pathlib import Path
import numpy as np
from . import audio, capcut, composto, reels, rosto

PASTA = Path(__file__).resolve().parent / "assets" / "cortes"
GUID_TOKEN = "0E685133-18CE-45ED-8CB8-2904A212EC80"          # do marcador ##_draftpath_placeholder_..._## (fixo)
KF = ("KFTypePositionX", "KFTypePositionY", "KFTypeScaleX", "KFTypeRotation")


def modelo(nome="basico"):
    return json.loads((PASTA / "modelos" / f"{nome}.json").read_text(encoding="utf-8"))


def _novos_ids(texto):
    """troca TODO uuid por um novo, o mesmo em todos os arquivos (chave sem diferenciar maiuscula)"""
    mapa = {}
    def troca(m):
        s = m.group(0)
        if s.upper() == GUID_TOKEN:
            return s
        k = s.lower()
        if k not in mapa:
            mapa[k] = str(uuid.uuid4())
        return mapa[k] if s == s.lower() else mapa[k].upper()
    return capcut._UUID.sub(troca, texto)


def carrega_template(nome="template"):
    """os 4 arquivos do template com ids novos: {draft, meta, stub, cfg}"""
    T = PASTA / nome
    sub = next(p for p in (T / "subdraft").iterdir() if p.is_dir())
    arqs = {"draft": T / "draft_content.json", "meta": T / "draft_meta_info.json",
            "stub": sub / "draft_content.json", "cfg": sub / "sub_draft_config.json"}
    SEP = "\n␞\n"
    junto = _novos_ids(SEP.join(arqs[k].read_text(encoding="utf-8") for k in arqs))
    return {k: json.loads(t) for k, t in zip(arqs, junto.split(SEP))}


def _troca_textos(o, mapa):
    """substitui os marcadores ({VIDEO}, {CACHE}/..., ...) em toda string do objeto"""
    if isinstance(o, dict):
        return {k: _troca_textos(v, mapa) for k, v in o.items()}
    if isinstance(o, list):
        return [_troca_textos(v, mapa) for v in o]
    if isinstance(o, str) and "{" in o:
        for a, b in mapa.items():
            o = o.replace(a, b)
    return o


# ---------------- corte seco do intervalo ----------------
def pedacos(video, ini, fim):
    """[[a, b, forca]] em s NO VIDEO ORIGINAL: regua + divide_longos sobre o audio SO do intervalo,
    na grade de quadros e colados (sem se sobrepor na origem)."""
    x = audio.pcm(video, ini, fim - ini)
    e, v = audio.analisa(x)
    keep = reels.regua(e, v, len(x) / audio.SR)
    out = []
    for a, b, forca, *_ in reels.divide_longos(e, v, keep):
        a, b = audio.na_grade(ini + a, ini + b)
        if out and a < out[-1][1]:
            a = out[-1][1]
        if b - a >= 1 / audio.FPS - 1e-6:
            out.append([a, b, bool(forca)])
    return out


# ---------------- zoom ----------------
def cobertura(info, canvas):
    """(W, H): fracao da largura/altura do canvas que o video ocupa na escala 1 (o CapCut encaixa o video
    inteiro no canvas). 16:9 num canvas 1:1 -> (1, 0,5625)."""
    va, ca = info["largura"] / info["altura"], canvas[0] / canvas[1]
    return (1.0, ca / va) if va >= ca else (va / ca, 1.0)


def enquadra(s, px, py, W, H, margem=0.0):
    """posicao que centra a pessoa (px, py: -1..1, py pra cima) na escala s, sem nunca mostrar borda preta:
    |x| <= s*W - 1 e |y| <= s*H - 1 (16:9 em 1:1: |x| <= s-1 e |y| <= 0,5625*s - 1)"""
    lx, ly = max(0.0, s * W - 1 - margem), max(0.0, s * H - 1 - margem)
    x, y = -px * s * W, -py * s * H
    return round(max(-lx, min(lx, x)), 6), round(max(-ly, min(ly, y)), 6)


def plano(pcs, info, canvas, mod, px=0.0, py=0.0):
    """por pedaco: (escala_ini, x_ini, y_ini, escala_fim, x_fim, y_fim). Base = menor escala que cobre o canvas
    + folga; os zooms sao as tabelas do Reels (plano_zoom) aplicadas como fatores sobre a base."""
    W, H = cobertura(info, canvas)
    z = mod["zoom"]; m = z.get("margem_borda", 0.0)
    base = round(max(1 / W, 1 / H) * (1 + z["folga_base"]), 6)
    b = (base,) + enquadra(base, px, py, W, H, m)
    out = []
    for p, zz in zip(pcs, reels.plano_zoom([(q[1] - q[0], q[2]) for q in pcs], 0.0, z.get("intensidade", 1.0))):
        if not zz:
            out.append(b + b); continue
        tipo, f, _ = zz
        s = round(base * f, 6); fim = (s,) + enquadra(s, px, py, W, H, m)
        out.append((b if tipo == "empurra" else fim) + fim)
    return out, base, (W, H)


# ---------------- montagem ----------------
def _kfs(modelo_kf, t0, t1, ini, fim):
    """keyframes lineares (t em us NA ORIGEM do pedaco) das 4 propriedades, no formato do template"""
    por = {k["property_type"]: k for k in modelo_kf}
    val = {"KFTypeScaleX": (ini[0], fim[0]), "KFTypePositionX": (ini[1], fim[1]),
           "KFTypePositionY": (ini[2], fim[2]), "KFTypeRotation": (0.0, 0.0)}
    out = []
    for p in KF:
        k = copy.deepcopy(por[p]) if p in por else reels.kf(p, t0, t1, *val[p])
        k["id"] = capcut.uid()
        a, b = copy.deepcopy(k["keyframe_list"][0]), copy.deepcopy(k["keyframe_list"][-1])
        for kk, t, v in ((a, t0, val[p][0]), (b, t1, val[p][1])):
            kk.update({"id": capcut.uid(), "time_offset": t, "values": [v]})
        k["keyframe_list"] = [a, b]
        out.append(k)
    return out


def monta(video, ini, fim, cache=None, musica=None, mod=None, pessoa=None):
    """video: caminho do original. ini/fim: s no original. cache: pasta 'User Data/Cache' do CapCut (efeito e fonte).
    musica: {path, nome, dur} ou None. pessoa: (px, py) ou None = detecta. Devolve um dict pra grava()."""
    mod = mod or modelo()
    video = Path(video)
    info = audio.probe_video(video)
    if not 0 <= ini < fim <= info["duracao"] + 0.05:
        raise capcut.ErroProjeto(f"Intervalo fora do vídeo: {ini:.1f}–{fim:.1f} s (o vídeo tem {info['duracao']:.1f} s).")
    t = carrega_template(mod["template"])
    d, meta, stub, cfg = t["draft"], t["meta"], t["stub"], t["cfg"]
    efeitos = (Path(cache) / "effect") if cache else None
    caminho = str(video.resolve()).replace("\\", "/")
    d = _troca_textos(d, {"{VIDEO}": caminho, "{CACHE}": str(Path(cache)).replace("\\", "/") if cache else ""})

    # --- dentro do composto: os pedacos
    entrada = d["materials"]["drafts"][0]; c = entrada["draft"]
    canvas_i = tuple(mod["canvas_interno"])
    c["canvas_config"].update(width=canvas_i[0], height=canvas_i[1])
    segs0 = c["tracks"][0]["segments"]
    vids = {v["id"]: v for v in c["materials"]["videos"]}
    seg0 = next((s for s in segs0 if s.get("common_keyframes") and not vids[s["material_id"]].get("object_locked")), segs0[0])
    idx = capcut.indice_materiais(c["materials"])
    pcs = pedacos(video, ini, fim)
    if not pcs:
        raise capcut.ErroProjeto("Não achei fala nesse trecho do vídeo.")
    if pessoa is None:
        px, py, _ = rosto.posicao_2d(video, ini, fim)
    else:
        px, py = pessoa
    zooms, base, cob = plano(pcs, info, canvas_i, mod, px, py)
    q = 1e6 / audio.FPS
    novos, alvo = [], 0
    for (a, b, _), z in zip(pcs, zooms):
        s = capcut.clona_segmento(seg0, idx, c["materials"])
        m = next(v for v in c["materials"]["videos"] if v["id"] == s["material_id"])
        m.update({"path": caminho, "material_name": video.name, "duration": int(round(info["duracao"] * 1e6)),
                  "width": info["largura"], "height": info["altura"], "has_audio": info["tem_audio"],
                  "unique_id": uuid.uuid4().hex, "object_locked": None})
        a_us, dur = audio.quadro_us(a), audio.quadro_us(b) - audio.quadro_us(a)
        s["source_timerange"] = {"start": a_us, "duration": dur}
        s["target_timerange"] = {"start": alvo, "duration": dur}
        s["speed"] = 1.0
        s["clip"] = dict(s["clip"], scale={"x": z[3], "y": z[3]}, transform={"x": z[4], "y": z[5]}, rotation=0.0)
        empurra = z[:3] != z[3:]
        s["common_keyframes"] = _kfs(seg0.get("common_keyframes") or [], a_us, a_us + dur - int(round(q)),
                                     z[:3], z[3:]) if empurra else []
        s["keyframe_refs"] = []
        novos.append(s); alvo += dur
    c["tracks"][0]["segments"] = novos
    c["duration"] = alvo
    capcut.poda(c)

    # --- raiz: o composto acelerado, efeito, headline, musica
    d["canvas_config"].update(width=mod["canvas_externo"][0], height=mod["canvas_externo"][1])
    M = d["materials"]; ix = capcut.indice_materiais(M)
    trilhas = {tr["type"]: tr for tr in d["tracks"]}
    sc = trilhas["video"]["segments"][0]
    ph = ix[sc["material_id"]][1]
    ph.update({"duration": alvo, "width": canvas_i[0], "height": canvas_i[1]})
    porcat = {ix[r][0]: ix[r][1] for r in sc["extra_material_refs"] if r in ix}
    co = mod["composto"]
    fora = composto_ipad_velocidade(sc, porcat, alvo, co["velocidade"])
    sc["volume"] = sc["last_nonzero_volume"] = float(co["volume_fala"])
    sc["clip"] = dict(sc["clip"], scale={"x": co["escala"], "y": co["escala"]}, transform={"x": co["x"], "y": co["y"]})
    ef = porcat.get("video_effects")
    if ef:
        ef["path"] = composto.caminho_no_cache(mod["efeito"]["id"], efeitos)
        for p in ef.get("adjust_params") or []:
            if p.get("name") in mod["efeito"]["parametros"]:
                p["value"] = float(mod["efeito"]["parametros"][p["name"]])

    h = mod["headline"]
    st = trilhas["text"]["segments"][0]
    st["target_timerange"] = {"start": 0, "duration": fora}
    st["clip"] = dict(st["clip"], scale={"x": h["escala"], "y": h["escala"]}, transform={"x": h["x"], "y": h["y"]})
    tm = ix[st["material_id"]][1]
    fonte = composto.caminho_no_cache(h["fonte_id"], efeitos)
    cont = json.loads(tm["content"]) if isinstance(tm["content"], str) else tm["content"]
    cont["text"] = h["texto"]
    for x in cont.get("styles", []):
        x["range"] = [0, len(h["texto"])]
        if isinstance(x.get("font"), dict): x["font"]["path"] = fonte
    tm["content"] = json.dumps(cont, ensure_ascii=False)
    tm["font_path"] = fonte
    for f in tm.get("fonts") or []: f["path"] = fonte

    sm = trilhas["audio"]["segments"][0]
    mm = ix[sm["material_id"]][1]
    tipos = {g["type"]: g for g in meta["draft_materials"]}
    if musica:
        dur_m = int(round(musica["dur"] * 1e6))
        usa = min(fora, audio.quadro_us(np.floor(musica["dur"] * audio.FPS) / audio.FPS))
        cm = str(Path(musica["path"]).resolve()).replace("\\", "/")
        mm.update({"path": cm, "name": musica["nome"], "duration": dur_m})
        sm["source_timerange"] = {"start": 0, "duration": usa}
        sm["target_timerange"] = {"start": 0, "duration": usa}
        sm["volume"] = sm["last_nonzero_volume"] = float(mod["musica"]["volume"])
        im = tipos[1]["value"][0]
        im.update({"file_Path": cm, "extra_info": Path(musica["path"]).name, "duration": dur_m})
    else:
        tira = {sm["material_id"], *sm["extra_material_refs"]}
        d["tracks"] = [tr for tr in d["tracks"] if tr["type"] != "audio"]
        usados = {r for tr in d["tracks"] for s in tr["segments"] for r in [s["material_id"], *s["extra_material_refs"]]}
        for k, v in M.items():
            if isinstance(v, list) and k != "drafts":
                M[k] = [x for x in v if not (isinstance(x, dict) and x.get("id") in tira - usados)]
        tipos[1]["value"] = []
    d["duration"] = fora
    d["name"] = ""

    # --- meta: video (tipo 0), musica (tipo 1), composto (tipo 18)
    iv = next(x for x in tipos[0]["value"] if x.get("metetype") == "video")
    dv = int(round(info["duracao"] * 1e6))
    agora = time.time_ns() // 1000
    lm = c["materials"]["videos"][0].get("local_material_id") or iv["id"]
    iv.update({"id": lm, "file_Path": caminho, "extra_info": video.name, "duration": dv,
               "width": info["largura"], "height": info["altura"], "roughcut_time_range": {"duration": dv, "start": 0},
               "create_time": agora // 10**6, "import_time": agora // 10**6, "import_time_ms": agora})
    for v in c["materials"]["videos"]: v["local_material_id"] = lm
    ic = tipos[18]["value"][0]
    ic.update({"duration": alvo, "roughcut_time_range": {"duration": alvo, "start": 0},
               "create_time": agora // 10**6, "import_time": agora // 10**6, "import_time_ms": agora // 1000})
    meta["draft_timeline_materials_size_"] = video.stat().st_size
    meta = _troca_textos(meta, {"{VIDEO}": caminho})
    cfg.update({"rough_cut_duration": alvo, "rough_cut_start": 0, "create_time": agora // 10**6,
                "import_time_ms": agora // 1000})

    return {"draft": d, "meta": meta, "stub": stub, "cfg": cfg, "pedacos": pcs, "zooms": zooms, "base": base,
            "cobertura": cob, "pessoa": (px, py), "info": info}


def composto_ipad_velocidade(seg, porcat, dentro_us, vel):
    """mesma regra do iPad: duracao de fora em quadros inteiros e velocidade EXATA (dentro/fora)"""
    from .ipad import _velocidade
    return _velocidade(seg, porcat, dentro_us, vel)


def _stub(r, pasta):
    """subdraft/<id>/draft_content.json: o composto sozinho, com o MESMO rascunho da raiz e caminhos absolutos"""
    stub = copy.deepcopy(r["stub"])
    entrada = r["draft"]["materials"]["drafts"][0]
    alvo = entrada["draft"]["duration"]
    e = copy.deepcopy(entrada)
    raizp = str(Path(pasta)).replace("\\", "/")
    for k in ("draft_file_path", "draft_cover_path", "draft_config_path"):
        e[k] = e[k].replace(composto.TOKEN, raizp)
    stub["materials"]["drafts"] = [e]
    s = stub["tracks"][0]["segments"][0]
    s["source_timerange"] = {"start": 0, "duration": alvo}
    s["target_timerange"] = {"start": 0, "duration": alvo}
    for v in stub["materials"]["videos"]:
        if v["id"] == s["material_id"]: v["duration"] = alvo
    return _troca_textos(stub, {"{PASTA}": raizp})


def verifica(r, pasta=None):
    """checklist antes (e depois) de gravar: estrutura do composto, os dois rascunhos iguais, meta tipo 18,
    pedacos colados, zoom dentro dos limites (sem borda preta), arquivos existem"""
    d = r["draft"]; erros = list(composto.verifica(d, pasta))
    entrada = d["materials"]["drafts"][0]; c = entrada["draft"]; fid = c["id"]
    if fid not in entrada["draft_file_path"]:
        erros.append("caminho do composto não aponta pra pasta subdraft dele")
    tipos = {g["type"]: g["value"] for g in r["meta"]["draft_materials"]}
    if not any(x.get("file_Path") == f"./subdraft/{fid}/sub_draft_config.json" for x in tipos.get(18, [])):
        erros.append("composto não registrado no draft_meta_info (tipo 18)")
    if pasta is not None:
        sub = json.loads((Path(pasta) / "subdraft" / fid / "draft_content.json").read_text(encoding="utf-8"))
        if sub["materials"]["drafts"][0]["draft"] != c:
            erros.append("rascunho do composto diferente entre a raiz e subdraft/")
    W, H = r["cobertura"]
    segs = c["tracks"][0]["segments"]
    for p, q in zip(segs, segs[1:]):
        if p["target_timerange"]["start"] + p["target_timerange"]["duration"] != q["target_timerange"]["start"]:
            erros.append("pedaços não estão colados")
    for s in segs:
        est = [(s["clip"]["scale"]["x"], s["clip"]["transform"]["x"], s["clip"]["transform"]["y"])]
        kf = {k["property_type"]: [x["values"][0] for x in k["keyframe_list"]] for k in s.get("common_keyframes") or []}
        if kf:
            est += list(zip(kf["KFTypeScaleX"], kf["KFTypePositionX"], kf["KFTypePositionY"]))
        for sc, x, y in est:
            if abs(x) > sc * W - 1 + 1e-6 or abs(y) > sc * H - 1 + 1e-6:
                erros.append("zoom deixa borda preta")
        if s["target_timerange"]["duration"] % 1 or s["target_timerange"]["duration"] <= 0:
            erros.append("pedaço com duração inválida")
    for v in c["materials"]["videos"]:
        if not Path(v["path"]).exists(): erros.append(f"vídeo não encontrado: {v.get('material_name')}")
    for a in d["materials"].get("audios", []):
        if a.get("path") and not Path(a["path"]).exists(): erros.append(f"música não encontrada: {a.get('name')}")
    if re.search(r"\{(VIDEO|MUSICA|CACHE|APPS|PASTA)\}", json.dumps(d, ensure_ascii=False)):
        erros.append("sobrou marcador do template no projeto")
    return sorted(set(erros))


def grava(raiz_capcut, nome, r, capa=None):
    """grava em pasta NOVA (capcut.grava_projeto) com a pasta subdraft/ do composto. Trava se a checagem falhar."""
    erros = verifica(r)
    if erros:
        raise composto.ErroMontagem("Projeto não gravado: " + "; ".join(erros))
    fid = r["draft"]["materials"]["drafts"][0]["draft"]["id"]

    def extras(pasta):
        sub = Path(pasta) / "subdraft" / fid
        sub.mkdir(parents=True, exist_ok=True)
        (sub / "draft_content.json").write_text(json.dumps(_stub(r, pasta), ensure_ascii=False, separators=(",", ":")),
                                                encoding="utf-8")
        (sub / "sub_draft_config.json").write_text(json.dumps(r["cfg"], ensure_ascii=False), encoding="utf-8")
        if capa and Path(capa).exists():
            (sub / "draft_cover.jpg").write_bytes(Path(capa).read_bytes())
        e2 = verifica(r, pasta)
        if e2:
            raise composto.ErroMontagem("Projeto não gravado: " + "; ".join(e2))

    return capcut.grava_projeto(raiz_capcut, nome, r["draft"], r["meta"], capa=capa, extras=extras)
