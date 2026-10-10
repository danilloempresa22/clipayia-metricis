"""Tudo que mexe no formato do CapCut: achar a pasta, ler projeto, puxar o audio dos clipes,
gravar projeto NOVO e registrar no root_meta_info.json (sem isso o CapCut nao mostra o projeto)."""
import os, re, sys, json, copy, uuid, time, shutil
from pathlib import Path
from . import audio

POR_SEG = ["speeds", "placeholder_infos", "canvases", "sound_channel_mappings", "material_colors",
           "vocal_separations", "material_animations", "videos"]


def uid():
    return str(uuid.uuid4()).upper()


class ErroProjeto(Exception):
    pass


# ---------------- pasta de projetos ----------------
def pastas_padrao():
    home = Path.home()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return [base / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"]
    if sys.platform == "darwin":
        return [home / "Movies" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft",
                home / "Library" / "Containers" / "com.lemon.lvoverseas" / "Data" / "Movies" / "CapCut"
                / "User Data" / "Projects" / "com.lveditor.draft"]
    return [home / "CapCut" / "com.lveditor.draft"]


def pastas_de_fonte():
    """onde o sistema guarda fontes instaladas (a do usuario primeiro)"""
    home = Path.home()
    if sys.platform == "win32":
        return [Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / "Microsoft" / "Windows" / "Fonts",
                Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"]
    if sys.platform == "darwin":
        return [home / "Library" / "Fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"),
                Path("/System/Library/Fonts")]
    return [home / ".local" / "share" / "fonts", home / ".fonts", Path("/usr/share/fonts")]


def fonte_instalada(*nomes):
    """caminho (com /) da primeira fonte instalada NESTE computador com um desses nomes de arquivo; vazio = nenhuma.
    Nunca devolve caminho de outra maquina: sem a fonte, o projeto fica sem caminho e o CapCut usa a padrao dele."""
    for d in pastas_de_fonte():
        for n in nomes:
            if (d / n).is_file():
                return str(d / n).replace("\\", "/")
    return ""


def caminhos_de_fora(texto):
    """caminhos que nao sao deste computador: o usuario dos moldes (USUARIO), outro usuario do Windows/Mac ou a pasta
    de fontes do Windows escrita a mao. Em qualquer computador (Windows de outro cliente ou Mac) o projeto so pode
    apontar pro que existe nele."""
    eu = Path.home().name.lower()
    ruins = set()
    for m in re.finditer(r"(?:[A-Za-z]:)?[/\\]+Users[/\\]+([^/\\\"]+)", texto):
        if m.group(1).lower() != eu: ruins.add(m.group(0))
    for x in ("USUARIO", "C:/Windows/Fonts", "C:\\\\Windows\\\\Fonts"):
        if x in texto: ruins.add(x)
    return sorted(ruins)


def acha_raiz(config_raiz=None):
    if config_raiz and Path(config_raiz).exists():
        return Path(config_raiz)
    for p in pastas_padrao():
        if p.exists():
            return p
    return None


def cache_efeitos(raiz):
    """pasta Cache/effect do CapCut (fonte da headline mora aqui)"""
    c = Path(raiz).parent.parent / "Cache" / "effect"
    return c if c.exists() else None


# ---------------- listar / ler ----------------
def lista_projetos(raiz):
    raiz = Path(raiz)
    meta_root = raiz / "root_meta_info.json"
    itens = []
    if meta_root.exists():
        try:
            d = json.loads(meta_root.read_text(encoding="utf-8"))
            for x in d.get("all_draft_store", []):
                pasta = Path(x.get("draft_fold_path", ""))
                if not pasta.name:
                    continue
                pasta = raiz / pasta.name            # caminho gravado pode ser de outra maquina
                if not (pasta / "draft_content.json").exists():
                    continue
                itens.append({"nome": x.get("draft_name") or pasta.name, "pasta": str(pasta),
                              "modificado": x.get("tm_draft_modified", 0) / 1e6,
                              "duracao": x.get("tm_duration", 0) / 1e6})
        except (ValueError, OSError):
            itens = []
    if not itens:                                     # sem indice: varre as pastas
        for pasta in raiz.iterdir():
            if (pasta / "draft_content.json").exists():
                itens.append({"nome": pasta.name, "pasta": str(pasta),
                              "modificado": (pasta / "draft_content.json").stat().st_mtime, "duracao": 0})
    itens.sort(key=lambda x: -x["modificado"])
    return itens


MSG_CRIPTO = ("Este projeto está criptografado (versão nova do CapCut). "
              "Ainda não dá pra editar esse formato.")


def le_draft(arq):
    """draft_content.json como dict. Distingue projeto criptografado (bytes que nao sao texto) de arquivo
    vazio/cortado (CapCut ainda gravando), pra nao acusar criptografia por engano."""
    bruto = Path(arq).read_bytes()
    if not bruto.strip():
        raise ErroProjeto("O projeto está vazio ou ainda sendo gravado. Feche o CapCut e tente de novo.")
    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ErroProjeto(MSG_CRIPTO)
    if texto.lstrip()[:1] != "{":                    # texto, mas nao JSON: formato proprio do CapCut
        raise ErroProjeto(MSG_CRIPTO)
    try:
        return json.loads(texto)
    except ValueError:
        raise ErroProjeto("O arquivo do projeto está corrompido ou incompleto. Feche o CapCut e tente de novo.")


def carrega(pasta):
    pasta = Path(pasta)
    draft = le_draft(pasta / "draft_content.json")
    meta_p = pasta / "draft_meta_info.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    vids = [t for t in draft.get("tracks", []) if t.get("type") == "video"]
    if not vids or not vids[0]["segments"]:
        raise ErroProjeto("O projeto não tem clipe de vídeo na trilha principal.")
    return draft, meta


def trilha_principal(draft):
    return [t for t in draft["tracks"] if t["type"] == "video"][0]


def clipes(draft):
    """[(segmento, material_video)] da trilha principal, em ordem"""
    mid = {v["id"]: v for v in draft["materials"]["videos"]}
    segs = sorted(trilha_principal(draft)["segments"], key=lambda s: s["target_timerange"]["start"])
    return [(s, mid[s["material_id"]]) for s in segs]


def audio_dos_clipes(draft, mp3=None, progresso=None, pasta=None):
    """audio de cada clipe da trilha principal. Padrao: le DIRETO do arquivo de video original
    (sem precisar exportar MP3). mp3=audio da timeline exportado do CapCut (fallback, vem ~25 ms atrasado)."""
    cs = clipes(draft)
    T = audio.pcm(mp3)[int(0.025 * audio.SR):] if mp3 else None
    out = []
    for i, (s, m) in enumerate(cs):
        dur = s["target_timerange"]["duration"] / 1e6
        if T is not None:
            t0 = s["target_timerange"]["start"] / 1e6
            x = T[int(t0 * audio.SR):int((t0 + dur) * audio.SR)]
        else:
            bruto = m.get("path", "")
            if "##_draftpath_placeholder" in bruto and pasta:      # midia guardada dentro da pasta do projeto
                bruto = re.sub(r"##_draftpath_placeholder_[^#]*_##", str(pasta).replace("\\", "/"), bruto)
            p = Path(bruto)
            if not p.exists():
                raise ErroProjeto(f"Não achei o arquivo do clipe '{m.get('material_name')}' ({p}). "
                                  "Ele foi movido? Abra o projeto no CapCut e reconecte a mídia.")
            src = s["source_timerange"]["start"] / 1e6
            vel = s.get("speed") or 1.0
            x = audio.pcm(p, src, dur * vel)
            if abs(vel - 1.0) > 1e-3:
                raise ErroProjeto("Clipe com velocidade alterada na trilha principal: deixe em 1x antes de editar.")
        out.append((s, m, x))
        if progresso: progresso(i + 1, len(cs))
    return out


# ---------------- criar projeto do zero a partir de um video ----------------
MOLDES = Path(__file__).resolve().parent / "assets" / "moldes"
_UUID = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")


def sonda_capcut(raiz):
    """Olha o projeto mais recente do usuario: prova que o formato desta versao do CapCut e' legivel
    (senao levanta ErroProjeto de criptografia ANTES de mexer em qualquer coisa) e devolve o bloco
    'platform' real da maquina. Pasta sem projetos: nao da pra sondar, devolve None."""
    for p in lista_projetos(raiz)[:5]:
        d = le_draft(Path(p["pasta"]) / "draft_content.json")
        if d.get("platform"):
            return {"platform": d["platform"], "last_modified_platform": d.get("last_modified_platform") or d["platform"],
                    "new_version": d.get("new_version"), "version": d.get("version")}
    return None


def _novos_ids(texto):
    mapa = {}
    def troca(m):
        s = m.group(0)
        if s not in mapa:
            mapa[s] = uid().lower() if s == s.lower() else uid()
        return mapa[s]
    return _UUID.sub(troca, texto)


def cria_draft(video, info, sonda=None, molde=None):
    """Projeto novo de 1 clipe (o video inteiro), montado a partir de um projeto REAL recem-importado no
    CapCut (assets/moldes) — nada de esqueleto inventado. info = audio.probe_video(video).
    Devolve (draft, meta) prontos pra reels.montar / grava_projeto."""
    video = Path(video)
    molde = MOLDES / (molde or ("vertical" if info["altura"] > info["largura"] else "horizontal"))
    draft = json.loads(_novos_ids((molde / "draft_content.json").read_text(encoding="utf-8")))
    meta = json.loads(_novos_ids((molde / "draft_meta_info.json").read_text(encoding="utf-8")))
    dur = int(round(info["duracao"] * 1e6))
    caminho = str(video.resolve()).replace("\\", "/")
    agora = time.time_ns() // 1000

    m = draft["materials"]["videos"][0]
    m.update({"unique_id": uuid.uuid4().hex, "path": caminho, "material_name": video.name, "duration": dur,
              "width": info["largura"], "height": info["altura"], "has_audio": info["tem_audio"]})
    seg = draft["tracks"][0]["segments"][0]
    seg["source_timerange"] = {"start": 0, "duration": dur}
    seg["target_timerange"] = {"start": 0, "duration": dur}
    draft["duration"] = dur
    draft["name"] = ""
    if sonda:
        for k in ("platform", "last_modified_platform"):
            draft[k] = copy.deepcopy(sonda[k])
        draft["new_version"] = sonda.get("new_version") or draft["new_version"]

    item = meta["draft_materials"][0]["value"][0]
    item.update({"id": m["local_material_id"], "extra_info": video.name, "file_Path": caminho, "duration": dur,
                 "width": info["largura"], "height": info["altura"], "create_time": agora // 10**6,
                 "import_time": agora // 10**6, "import_time_ms": agora,
                 "roughcut_time_range": {"duration": dur, "start": 0}})
    meta["draft_timeline_materials_size_"] = video.stat().st_size
    return draft, meta


# ---------------- montar / gravar ----------------
def indice_materiais(mats):
    return {x["id"]: (k, x) for k, v in mats.items() if isinstance(v, list) for x in v if isinstance(x, dict) and "id" in x}


def clona_segmento(s, idx, mats, pular=("time_marks", "beats")):
    """copia do segmento com material de video e refs PROPRIOS (dois segmentos com o mesmo
    material_id o CapCut nao deixa puxar a borda)."""
    ns = copy.deepcopy(s); ns["id"] = uid()
    c, m = idx[s["material_id"]]
    m2 = copy.deepcopy(m); m2["id"] = uid(); mats[c].append(m2); ns["material_id"] = m2["id"]
    refs = []
    for r in s.get("extra_material_refs", []):
        if r not in idx: continue
        c, m = idx[r]
        if c in pular: continue
        m2 = copy.deepcopy(m); m2["id"] = uid(); mats[c].append(m2); refs.append(m2["id"])
    ns["extra_material_refs"] = refs
    return ns


def poda(novo):
    """apaga material por-segmento que ninguem usa (projeto leve)"""
    mats = novo["materials"]; usados = set()
    for t in novo["tracks"]:
        for x in t["segments"]:
            usados.add(x["material_id"]); usados.update(x.get("extra_material_refs", []))
    for k in POR_SEG + ["texts"]:
        if k in mats and isinstance(mats[k], list):
            mats[k] = [m for m in mats[k] if m["id"] in usados]


def verifica(d):
    mats = d["materials"]; erros = []
    ids = set(indice_materiais(mats))
    vid = {v["id"]: v for v in mats["videos"]}
    for t in d["tracks"]:
        ss = sorted(t["segments"], key=lambda s: s["target_timerange"]["start"])
        for x in ss:
            if x["material_id"] not in ids: erros.append("material solto")
            erros += ["ref solta" for r in x.get("extra_material_refs", []) if r not in ids]
            if t["type"] == "video":
                m = vid[x["material_id"]]
                if x["source_timerange"]["start"] + x["source_timerange"]["duration"] > m["duration"] + 1000:
                    erros.append("passa do fim do clipe " + m.get("material_name", ""))
                cl = x.get("clip") or {}
                sc = cl.get("scale", {}).get("x", 1.0); tx = abs(cl.get("transform", {}).get("x", 0.0))
                if sc >= 1.0 and tx > sc - 1.0 + 1e-6: erros.append("zoom deixa borda preta")
        for p, q in zip(ss, ss[1:]):
            if p["target_timerange"]["start"] + p["target_timerange"]["duration"] > q["target_timerange"]["start"]:
                erros.append("sobreposicao")
    vs = [x["material_id"] for t in d["tracks"] if t["type"] == "video" for x in t["segments"]]
    if len(set(vs)) != len(vs): erros.append("material de video compartilhado")
    for t in d["tracks"]:
        if t["type"] != "text": continue
        for x in t["segments"]:
            m = [m for m in mats.get("texts", []) if m["id"] == x["material_id"]]
            if not m: continue
            c = json.loads(m[0]["content"]) if isinstance(m[0]["content"], str) else m[0]["content"]
            if any(st["range"][1] != len(c["text"]) for st in c.get("styles", [])): erros.append("range do texto errado")
    return erros


def nome_livre(raiz, nome):
    raiz = Path(raiz); n = nome; k = 2
    while (raiz / n).exists():
        n = f"{nome} v{k}"; k += 1
    return n


def grava_projeto(raiz, nome, novo, meta0, capa=None, extras=None):
    """grava SEMPRE em pasta nova (pasta que o CapCut ja abriu e' sobrescrita pelo autosave dele)
    e registra no root_meta_info.json. extras(pasta): grava arquivos a mais (ex.: subdraft/) antes de registrar;
    se falhar, a pasta inteira some. Devolve o nome final."""
    raiz = Path(raiz)
    nome = nome_livre(raiz, nome)
    pasta = raiz / nome
    pasta.mkdir(parents=True)
    try:
        fold = str(pasta).replace("\\", "/")
        rootp = str(raiz).replace("\\", "/")
        novo = copy.deepcopy(novo); novo["id"] = uid()
        (pasta / "draft_content.json").write_text(json.dumps(novo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        now = time.time_ns() // 1000
        meta = copy.deepcopy(meta0)
        meta.update({"draft_id": uid(), "draft_name": nome, "draft_fold_path": fold, "draft_root_path": rootp,
                     "tm_draft_create": now, "tm_draft_modified": now, "tm_duration": novo["duration"]})
        (pasta / "draft_meta_info.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        if capa and Path(capa).exists():
            shutil.copy(capa, pasta / "draft_cover.jpg")
        if extras:
            extras(pasta)
        registra(raiz, meta, fold)
    except BaseException:
        shutil.rmtree(pasta, ignore_errors=True)      # nunca deixa pasta de projeto pela metade
        raise
    return nome


def registra(raiz, meta, fold, tentativas=5):
    """insere o projeto no indice do CapCut. Le de novo na hora (o CapCut mexe nesse arquivo)."""
    rp = Path(raiz) / "root_meta_info.json"
    for _ in range(tentativas):
        if rp.exists():
            antes = rp.stat().st_mtime_ns
            d = json.loads(rp.read_text(encoding="utf-8"))
        else:
            antes = None
            d = {"all_draft_store": [], "draft_ids": 0, "root_path": str(raiz).replace("\\", "/")}
        st = d.setdefault("all_draft_store", [])
        if any(x.get("draft_fold_path") == fold for x in st):
            return
        modelo = copy.deepcopy(st[0]) if st else {}
        modelo.update({"draft_id": meta["draft_id"], "draft_name": meta["draft_name"], "draft_fold_path": fold,
                       "draft_json_file": fold + "/draft_content.json", "draft_cover": fold + "/draft_cover.jpg",
                       "draft_root_path": meta["draft_root_path"],
                       "tm_draft_create": meta["tm_draft_create"], "tm_draft_modified": meta["tm_draft_modified"],
                       "tm_duration": meta["tm_duration"]})
        st.append(modelo)
        melhor = {}
        for x in st:
            k = x.get("draft_fold_path")
            if k not in melhor or x.get("tm_draft_modified", 0) > melhor[k].get("tm_draft_modified", 0): melhor[k] = x
        d["all_draft_store"] = sorted(melhor.values(), key=lambda x: -x.get("tm_draft_modified", 0))
        if isinstance(d.get("draft_ids"), int): d["draft_ids"] = len(d["all_draft_store"])
        if rp.exists() and rp.stat().st_mtime_ns != antes:
            time.sleep(0.5); continue                 # CapCut mexeu no meio: le de novo
        if rp.exists():
            shutil.copy(rp, rp.with_suffix(".json.bak_cortes"))
        tmp = rp.with_suffix(".tmp_cortes")
        tmp.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, rp)
        return
    raise ErroProjeto("Não consegui registrar o projeto no CapCut (arquivo em uso). Feche e abra o CapCut.")
