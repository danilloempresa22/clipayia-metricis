"""Modo REACT (Fase 1, so o motor): o video de cima (uma receita) e o react do apresentador embaixo, emendados por
um degrade, com a headline no meio e, opcional, um CTA que entra quando o video de cima congela. Um react serve
varios videos: um projeto do CapCut por video de cima.

O projeto e' o real "Patricio clipay ia" (docs/design/referencia-react, copiado em assets/react com marcadores no
lugar dos caminhos): so muda o que varia (materiais, tempos, enquadramento, ids). Nada de estrutura inventada.
  trilha 1 (video)  o video de cima, com som. Com CTA: [0,P) | quadro congelado em P (foto "Congelar") | [P,fim)
  trilha 2 (video)  o react, mudo, na faixa de baixo, mascara "Dividir" (o degrade). SEM filtro: a referencia tinha
                    "Aprimorar" nos 2 trechos do react (antes e depois do CTA); desde 2026-10 nenhum trecho tem filtro.
                    Com CTA: no mesmo intervalo entra o video do CTA (com som, sem filtro) e o react fica parado:
                    depois do CTA ele volta exatamente de onde parou.
  trilha 3 (texto)  headline no modelo "Title EN Simple News", o video todo (a pessoa troca o texto no CapCut)."""
import copy, hashlib, json, math, re, subprocess, time, uuid
from pathlib import Path
from . import audio, capcut, composto, cortes, palavras

PASTA = Path(__file__).resolve().parent / "assets" / "react"
FPS = 30.0
W, H = 1080, 1920                       # tela 9:16
INICIO_REACT = 1.4                      # s: onde o react comeca (como na referencia)
COBRE_ATE = 1250                        # px: o video de cima tem que chegar ate aqui. Medido no quadro final da
                                        # referencia: o degrade do react vai de ~1185 px (topo da faixa) a ~1240 px
                                        # (opaco); abaixo disso o video de cima fica escondido atras do react
JANELA = (0.40, 0.70)                   # onde procurar a pausa pra congelar (fracao da duracao)
IDEAL = 0.55
PAUSA_MIN = 0.4                         # s
HEADLINE = "Coloque a headline do seu vídeo aqui"
FONTE = "CreatoDisplay-Bold.otf"
_FIM_FRASE = re.compile(r"[.!?…]+[\"'”’)»]*$")
_CACHE_REF = re.compile(r"\{CACHE\}/(effect|artistEffect)/(\d+)/([0-9a-f]+)(/[^\"\\]*)?")


class ErroReact(capcut.ErroProjeto):
    pass


def quadros_us(n):
    """n quadros -> us, truncado como o CapCut grava (1547 quadros -> 51566666, nao ...667)"""
    return int(n) * 1_000_000 // int(FPS)


def us(t):
    """s -> us na grade de quadros da timeline (30 fps)"""
    return quadros_us(round(t * FPS))


# ---------------- duracao como o CapCut mede ----------------
_DUR = {}


def duracao_us(path):
    """duracao do VIDEO (nao do container) arredondada pra cima em quadros de 30 fps, como o CapCut grava no
    material (referencia: 87,4 s -> 87400000; react 154,015 s -> 154033333; CTA 211 quadros -> 7033333).
    Le so os pacotes (sem decodificar): o fim do ultimo quadro."""
    p = Path(path); st = p.stat(); k = (str(p.resolve()), st.st_size, st.st_mtime_ns)
    if k not in _DUR:
        r = subprocess.run([audio.ffmpeg_bin(), "-v", "error", "-i", str(p), "-map", "0:v:0", "-c", "copy", "-f", "framemd5", "-"],
                           capture_output=True, **audio._sem_janela())
        tb, fim = None, 0
        for l in r.stdout.decode("utf-8", "ignore").splitlines():
            if l.startswith("#tb"):
                a, b = l.split(":")[1].strip().split("/"); tb = int(a) / int(b)
            elif l and not l.startswith("#"):
                c = [x.strip() for x in l.split(",")]
                fim = max(fim, int(c[2]) + int(c[3]))
        if tb is None or not fim:
            raise ErroReact(f"Não consegui ler o vídeo: {p.name}")
        s = fim * tb
        _DUR[k] = quadros_us(math.ceil(s * FPS - 1e-3))
    return _DUR[k]


def info(path):
    i = audio.probe_video(path)
    i["dur_us"] = duracao_us(path)
    return i


# ---------------- geometria ----------------
def _encaixe(w, h):
    """tamanho em px com que o CapCut poe o material na tela antes da escala (cabe inteiro)"""
    f = min(W / w, H / h)
    return w * f, h * f


def enquadra_cima(w, h, corte=None, zoom=1.0, posicao=0.5):
    """video de cima. corte = fracao do video escondida em cima (o "X% cortado em cima" da tela); zoom >= 1;
    posicao = 0 (esquerda) .. 1 (direita), so vale quando sobra largura (video horizontal ou com zoom).
    Ele SEMPRE cobre do topo da tela ate COBRE_ATE: o corte e' limitado (corte_max) pra nunca aparecer fundo vazio.
    Vertical: preenche a largura. Horizontal: amplia ate cobrir a altura de cima e corta as laterais."""
    w0, h0 = _encaixe(w, h)
    zoom = max(1.0, float(zoom or 1.0))
    base = max(W / w0, COBRE_ATE / h0)
    s = base * zoom
    lw, lh = w0 * s, h0 * s
    cmax = max(0.0, 1.0 - COBRE_ATE / lh)
    if corte is None:                               # vertical: como na referencia; horizontal: no meio
        corte = 0.2375283446712018 if W / w0 >= COBRE_ATE / h0 else cmax / 2
    c = min(max(float(corte), 0.0), cmax)
    p = min(max(float(posicao if posicao is not None else 0.5), 0.0), 1.0)
    y = (c * lh - lh / 2 + H / 2) / (H / 2)
    cx = lw / 2 - p * (lw - W)
    x = (cx - W / 2) / (W / 2)
    return {"modo": "vertical" if W / w0 >= COBRE_ATE / h0 else "horizontal", "escala": s, "x": x, "y": y,
            "corte": c, "corte_max": cmax, "limitado": c < float(corte) - 1e-9, "posicao": p,
            "lateral": lw > W + 0.5}


def enquadra_faixa(w, h, ref):
    """react ou CTA na faixa de baixo: o mesmo lugar da referencia (ref = clip do segmento no molde, material 16:9).
    Outro formato: amplia ate cobrir a faixa inteira, centrado nela."""
    if abs(w / h - 16 / 9) < 0.01:
        return {"escala": ref["scale"]["x"], "x": ref["transform"]["x"], "y": ref["transform"]["y"]}
    rw0, rh0 = _encaixe(16, 9)
    fh = rh0 * ref["scale"]["x"]                     # altura da faixa em px
    w0, h0 = _encaixe(w, h)
    return {"escala": max(W / w0, fh / h0), "x": 0.0, "y": ref["transform"]["y"]}


# ---------------- onde congelar ----------------
def ponto_congelar(video, dur_s, falas=None, trechos=None, x=None):
    """onde o video de cima congela: ENTRE frases, perto do meio (janela 40-70% da duracao, a mais perto de 55%).
    1) pausa de fala >= 0,4 s depois de um fim de frase: congela no meio da pausa;
    2) receita narrada rapido com musica quase nunca tem pausa de 0,4 s (2 de 3 receitas de teste: nenhuma).
       Entao vale o fim de frase da transcricao (. ! ?): congela no instante mais quieto logo depois da ultima
       palavra (a referencia congelou assim: logo depois de "...pouquinho.", sem pausa longa). pausa_curta=True;
    3) nada disso na janela: 55% e boa=False (a tela avisa "sem pausa boa").
    falas = palavras do Whisper [{t,a,b}]; sem falas so vale a pausa (1)."""
    if x is None:
        x = audio.pcm(video)
    if trechos is None:
        trechos = palavras.trechos_de_fala(x) if len(x) and float(abs(x).max()) >= 1e-3 else []
    a0, a1, ideal = JANELA[0] * dur_s, JANELA[1] * dur_s, IDEAL * dur_s
    if not trechos:
        return {"t": ideal, "boa": True, "pausa_curta": False, "motivo": "sem fala"}
    fim_frase = lambda p: bool(_FIM_FRASE.search(p["t"].strip()))
    cands = []
    for (_, b), (c, _) in zip(trechos, trechos[1:]):
        meio = (b + c) / 2
        if c - b < PAUSA_MIN or not a0 <= meio <= a1:
            continue
        if falas:
            antes = [p for p in falas if p["b"] <= b + 0.3]
            depois = [p for p in falas if p["a"] >= c - 0.3]
            if antes and depois and not fim_frase(antes[-1]):
                continue                              # pausa no meio de uma frase
        cands.append((abs(meio - ideal), meio, c - b))
    if cands:
        _, meio, dur = min(cands)
        return {"t": meio, "boa": True, "pausa_curta": False, "motivo": f"pausa de {dur:.2f} s"}
    if falas and len(x):
        e, _ = audio.analisa(x)
        fins = []
        for p, q in zip(falas, falas[1:]):
            if not fim_frase(p): continue
            lo, hi = p["b"] - 0.25, min(p["b"] + 0.45, q["b"] - 0.05)   # o tempo da palavra e' aproximado
            i0, i1 = max(0, int(lo / audio.H)), min(len(e), int(hi / audio.H) + 1)
            if i1 <= i0: continue
            t = (i0 + int(e[i0:i1].argmin())) * audio.H + audio.WIN / 2
            if a0 <= t <= a1: fins.append((abs(t - ideal), t, p["t"]))
        if fins:
            _, t, pal = min(fins)
            return {"t": t, "boa": True, "pausa_curta": True, "motivo": f"fim de frase (“{pal}”), pausa curta"}
    return {"t": ideal, "boa": False, "pausa_curta": False, "motivo": "sem pausa boa"}


def arquivo_transcricao(video):
    """onde fica a transcricao do video: %APPDATA%/Clipay/cache_react/<sha1 do caminho, tamanho e data>.json"""
    from . import transcricao
    p = Path(video); st = p.stat()
    k = hashlib.sha1(f"{p.resolve()}|{st.st_size}|{st.st_mtime_ns}|react-v1".encode()).hexdigest()
    return transcricao.pasta_dados() / "cache_react" / f"{k}.json"


def transcreve(video, w):
    """palavras do video de cima, com tempo, em cache por arquivo. Uma passada so: serve pra achar a pausa do CTA
    (onde termina cada frase) e pra transcricao que a pessoa le na tela"""
    arq = arquivo_transcricao(video)
    if arq.exists():
        return json.loads(arq.read_text(encoding="utf-8"))
    x = audio.pcm(video)
    out = palavras.transcreve(w, x) if len(x) and float(abs(x).max()) >= 1e-3 else []
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


# ---------------- trecho do react ----------------
def inicios_react(react_us, duracoes_us, variar=False, inicio=INICIO_REACT):
    """onde o react comeca em cada projeto (us). Padrao: 1,4 s. Variar: espalhado do comeco ate o ultimo ponto
    que ainda cabe, um diferente por video. None = o react e' mais curto que aquele video (nao gera)."""
    n, r0 = len(duracoes_us), us(inicio)
    out = []
    for i, d in enumerate(duracoes_us):
        if d > react_us:
            out.append(None); continue
        ult = react_us - d                            # ultimo inicio que nao passa do fim
        ini = min(r0, ult)
        if variar and n > 1:
            ini = ini + (ult - ini) * i / (n - 1)
        out.append(quadros_us(ini * int(FPS) // 1_000_000))      # na grade, sem passar do fim
    return out


# ---------------- montar ----------------
def nomes_do_modelo(d):
    """ids que vem do PACOTE do modelo de texto (content.json dele: o texto e a barra vermelha). Nao podem mudar:
    com outro nome o CapCut nao acha as pecas, refaz o modelo do zero (3 s e o texto padrao) e a headline some."""
    out = {t["name"] for t in d["materials"].get("texts", []) if capcut._UUID.fullmatch(t.get("name") or "")}
    for tt in d["materials"].get("text_templates", []):
        out |= {r["name"] for r in tt.get("non_text_info_resources", []) if capcut._UUID.fullmatch(r.get("name") or "")}
    return {x.upper() for x in out}


def _molde():
    SEP = "\n␞\n"
    t = SEP.join((PASTA / f).read_text(encoding="utf-8") for f in ("draft_content.json", "draft_meta_info.json"))
    fixos = nomes_do_modelo(json.loads(t.split(SEP)[0])) | {cortes.GUID_TOKEN}
    mapa = {}

    def troca(mt):
        s = mt.group(0); k = s.lower()
        if s.upper() in fixos:
            return s
        if k not in mapa:
            mapa[k] = str(uuid.uuid4())
        return mapa[k] if s == s.lower() else mapa[k].upper()
    d, m = (json.loads(x) for x in capcut._UUID.sub(troca, t).split(SEP))
    return d, m


def _cache(o, cache):
    """caminhos de efeito/modelo pro cache do CapCut DESTA maquina; sem o recurso, vazio (o CapCut baixa pelo id)"""
    def troca(mt):
        tipo, rid, h, resto = mt.group(1), mt.group(2), mt.group(3), mt.group(4) or ""
        if not cache:
            return ""
        base = Path(cache) / tipo / rid
        d = base / h if (base / h).is_dir() else next((p for p in sorted(base.glob("*"))
                                                       if p.is_dir() and not p.name.endswith("_tmp")), None)
        if d is None:
            return ""
        if resto and not (d / resto.lstrip("/")).exists():
            f = next(iter(sorted(d.glob("*" + Path(resto).suffix))), None)
            return str(f).replace("\\", "/") if f else str(d).replace("\\", "/")
        return str(d).replace("\\", "/") + resto
    return _troca(o, lambda s: _CACHE_REF.sub(troca, s) if "{CACHE}" in s else s)


def _troca(o, f):
    if isinstance(o, dict):
        return {k: _troca(v, f) for k, v in o.items()}
    if isinstance(o, list):
        return [_troca(v, f) for v in o]
    return f(o) if isinstance(o, str) else o


def fonte_headline():
    """a fonte da headline (Creato Display Bold) mora no Windows, nao no cache do CapCut. Vazio = nao instalada."""
    import os
    for p in (Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts" / FONTE,
              Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / FONTE):
        if p.exists():
            return str(p).replace("\\", "/")
    return ""


def sem_filtro(d):
    """tira todo filtro (materials.effects do tipo filter, ex.: "Aprimorar") de todos os trechos; a mascara fica"""
    M = d["materials"]
    filtros = {x["id"] for x in M.get("effects", []) if x.get("type") == "filter"}
    if not filtros:
        return
    for t in d["tracks"]:
        for s in t["segments"]:
            s["extra_material_refs"] = [r for r in s.get("extra_material_refs", []) if r not in filtros]
    M["effects"] = [x for x in M["effects"] if x["id"] not in filtros]


def nome_congelado(receita, p_us):
    return f"{hashlib.md5(str(receita).encode()).hexdigest()}_{p_us}-sdr709.png"


def monta(receita, react, enq=None, cta=None, inicio_us=None, congelar=None, cache=None, falas=None, infos=None,
          cta_pos="meio"):
    """receita: o video de cima. react: o video do apresentador. enq: {corte, zoom, posicao} da tela.
    cta: caminho do video do CTA ou None. cta_pos: "meio" (congela numa pausa e o video continua depois) ou "final"
    (o video toca inteiro; depois dele, o ultimo quadro parado com o CTA embaixo). inicio_us: onde o react comeca
    (inicios_react). congelar: s, ou None = acha a pausa. cache: pasta 'User Data/Cache' do CapCut."""
    receita, react = Path(receita), Path(react)
    infos = infos or {}
    ir = infos.get("receita") or info(receita)
    ik = infos.get("react") or info(react)
    ic = (infos.get("cta") or info(cta)) if cta else None
    D = ir["dur_us"]
    r0 = us(INICIO_REACT) if inicio_us is None else int(inicio_us)
    if r0 + D > ik["dur_us"]:
        raise ErroReact(f"O react é mais curto que o vídeo “{receita.name}”: o react tem "
                        f"{ik['dur_us'] / 1e6:.0f} s e o vídeo {D / 1e6:.0f} s. Use um react mais longo.")
    avisos = []
    d, meta = _molde()
    M = d["materials"]; ix = capcut.indice_materiais(M)
    cima, baixo, txt = d["tracks"]
    caminho = lambda p: str(Path(p).resolve()).replace("\\", "/")
    fonte = fonte_headline()
    if not fonte:
        avisos.append("A fonte Creato Display Bold não está instalada neste computador: "
                      "a headline vai aparecer com a fonte padrão do CapCut.")
        fonte = "C:/Windows/Fonts/" + FONTE

    # --- tempos (us, grade de 30 fps). Com CTA: o de cima congela em P pelo tempo do CTA
    cong = None
    final = bool(cta) and cta_pos == "final"
    if final:                                         # sem pausa: congela no ultimo quadro, depois do video inteiro
        C = ic["dur_us"]; P = D - us(1 / FPS); total = D + C
        cong = {"t": P / 1e6, "boa": True, "motivo": "no final", "us": P, "final": True}
    elif cta:
        cong = {"t": float(congelar), "boa": True, "motivo": "escolhido"} if congelar is not None else \
            ponto_congelar(receita, D / 1e6, falas)
        P = min(max(us(cong["t"]), us(1 / FPS)), D - us(1 / FPS))
        C = ic["dur_us"]
        T2 = us((P + C) / 1e6)
        total = D + C
        cong.update(us=P)
    else:
        total = D

    def seg(s, src, tgt):
        s["source_timerange"] = {"start": int(src[0]), "duration": int(src[1])}
        s["target_timerange"] = {"start": int(tgt[0]), "duration": int(tgt[1])}

    def clip(s, g):
        s["clip"] = dict(s["clip"], scale={"x": g["escala"], "y": g["escala"]}, transform={"x": g["x"], "y": g["y"]})

    def video(s, path, i, nome=None):
        m = ix[s["material_id"]][1]
        m.update({"path": caminho(path), "material_name": nome or Path(path).name, "duration": i["dur_us"],
                  "width": i["largura"], "height": i["altura"], "has_audio": i["tem_audio"]})
        return m

    g = enquadra_cima(ir["largura"], ir["altura"], *(enq.get(k) for k in ("corte", "zoom", "posicao"))) if enq \
        else enquadra_cima(ir["largura"], ir["altura"])
    if g["limitado"]:
        avisos.append(f"O corte em cima foi limitado a {g['corte'] * 100:.0f}% pra não aparecer fundo vazio.")
    c1, foto, c3 = cima["segments"]
    k1, kcta, k3 = baixo["segments"]
    fk = enquadra_faixa(ik["largura"], ik["altura"], k1["clip"])
    for s in (c1, foto, c3): clip(s, g)
    for s in (k1, k3): clip(s, fk)
    for s in (c1, c3): video(s, receita, ir)
    for s in (k1, k3): video(s, react, ik)
    if final:                                         # [video inteiro | ultimo quadro]  /  [react | CTA]
        seg(c1, (0, D), (0, D)); seg(foto, (0, C), (D, C))
        seg(k1, (r0, D), (0, D)); seg(kcta, (0, C), (D, C))
    elif cta:
        seg(c1, (0, P), (0, P)); seg(foto, (0, C), (P, T2 - P)); seg(c3, (P, D - P), (T2, total - T2))
        seg(k1, (r0, P), (0, P)); seg(kcta, (0, C), (P, T2 - P)); seg(k3, (r0 + P, D - P), (T2, total - T2))
    if cta:
        clip(kcta, enquadra_faixa(ic["largura"], ic["altura"], kcta["clip"]))
        video(kcta, cta, ic)
        png = nome_congelado(caminho(receita), P)
        mf = ix[foto["material_id"]][1]
        mf.update({"path": mf["path"].replace("{CONGELADO}", png), "width": ir["largura"], "height": ir["altura"]})
        mf["freeze"].update({"source_material_id": c1["material_id"], "source_material_path": caminho(receita), "timestamp": P})
    else:
        seg(c1, (0, D), (0, D)); seg(k1, (r0, D), (0, D))
        png = None
    if final or not cta:                              # o que sobra do molde (3o trecho; e, sem CTA, a foto e o CTA)
        sai = (c3, k3) if final else (foto, c3, kcta, k3)
        tira = set()
        for s in sai:
            tira |= {s["material_id"], *s["extra_material_refs"]}
        cima["segments"] = [x for x in cima["segments"] if all(x is not y for y in sai)]
        baixo["segments"] = [x for x in baixo["segments"] if all(x is not y for y in sai)]
        for k, v in M.items():
            if isinstance(v, list):
                M[k] = [x for x in v if not (isinstance(x, dict) and x.get("id") in tira)]

    # --- headline: o texto de exemplo, o video todo
    st = txt["segments"][0]
    seg_t = {"start": 0, "duration": total}
    st["target_timerange"] = seg_t
    tpl = ix[st["material_id"]][1]
    for r in tpl.get("text_info_resources", []) + tpl.get("non_text_info_resources", []):
        r["attach_info"].update(start_time=0, duration=total)
    for tm in M["texts"]:
        cont = json.loads(tm["content"])
        cont["text"] = HEADLINE
        for x in cont.get("styles", []):
            x["range"] = [0, len(HEADLINE)]
            if isinstance(x.get("font"), dict): x["font"]["path"] = fonte
        tm["content"] = json.dumps(cont, ensure_ascii=False, separators=(",", ":"))
        tm["font_path"] = fonte
    d["duration"] = total
    sem_filtro(d)
    d["name"] = ""

    # --- meta: os videos usados (tipo 0) e o quadro congelado (tipo 6)
    tipos = {gr["type"]: gr for gr in meta["draft_materials"]}
    agora = time.time_ns() // 1000
    por_local = {v["local_material_id"]: v for v in M["videos"] if v.get("local_material_id")}
    vivos = []
    for it in tipos[0]["value"]:
        v = por_local.get(it["id"])
        if not v: continue
        dms = v["duration"] // 1000 * 1000
        it.update({"file_Path": v["path"], "extra_info": v["material_name"], "duration": dms,
                   "width": v["width"], "height": v["height"], "roughcut_time_range": {"duration": dms, "start": 0},
                   "create_time": agora // 10**6, "import_time": agora // 10**6, "import_time_ms": agora})
        vivos.append(it)
    tipos[0]["value"] = vivos
    if png:
        it = tipos[6]["value"][0]
        it.update({"file_Path": "./" + png, "import_time": agora // 10**6,
                   "extra_info": json.dumps({"height": ir["altura"], "pts": P, "src": caminho(receita),
                                             "width": ir["largura"]}, separators=(",", ":"))})
    else:
        tipos[6]["value"] = []
    mascaras = {x["id"] for x in M.get("common_mask", [])}
    meta["draft_segment_extra_info"] = [x for x in meta.get("draft_segment_extra_info", []) if x["extra_segmend_id"] in mascaras]
    tam = {Path(p).resolve() for p in (receita, react, cta) if p}
    meta["draft_timeline_materials_size_"] = sum(p.stat().st_size for p in tam)

    nomes = {"{RECEITA}": caminho(receita), "{REACT}": caminho(react), "{CTA}": caminho(cta) if cta else "",
             "{RECEITA_NOME}": receita.name, "{REACT_NOME}": react.name, "{CTA_NOME}": Path(cta).name if cta else "",
             "{FONTE}": fonte}
    def marca(s):
        for a, b in nomes.items():
            if a in s: s = s.replace(a, b)
        return s
    d, meta = _cache(_troca(d, marca), cache), _cache(_troca(meta, marca), cache)
    return {"draft": d, "meta": meta, "receita": str(receita), "congelar": cong, "png": png, "enquadramento": g,
            "faixa": fk, "inicio_react": r0, "total": total, "avisos": avisos}


# ---------------- conferir e gravar ----------------
def verifica(r, pasta=None):
    """o que o CapCut exige (capcut.verifica) + as contas do React: trilhas coladas de 0 ao fim, sem buraco nem
    sobreposicao, o react pausado volta no ponto certo, o de cima cobre ate a faixa, arquivos existem"""
    d = r["draft"]; erros = list(capcut.verifica(d))
    total = d["duration"]
    for t in d["tracks"]:
        fim = 0
        for s in sorted(t["segments"], key=lambda s: s["target_timerange"]["start"]):
            if s["target_timerange"]["start"] != fim: erros.append(f"buraco ou sobreposição na trilha {t['type']}")
            fim = s["target_timerange"]["start"] + s["target_timerange"]["duration"]
        if fim != total: erros.append(f"trilha {t['type']} não termina no fim do vídeo")
    cima, baixo = d["tracks"][0]["segments"], d["tracks"][1]["segments"]
    if len(cima) == 3:
        a, b = baixo[0]["source_timerange"], baixo[2]["source_timerange"]
        if a["start"] + a["duration"] != b["start"]: erros.append("o react não volta de onde parou depois do CTA")
        x, y = cima[0]["source_timerange"], cima[2]["source_timerange"]
        if x["start"] + x["duration"] != y["start"]: erros.append("o vídeo de cima não continua de onde congelou")
    g = r["enquadramento"]
    if g["corte"] > g["corte_max"] + 1e-9: erros.append("o vídeo de cima deixa fundo vazio")
    for v in d["materials"]["videos"]:
        p = v["path"]
        if composto.TOKEN in p:
            if pasta is not None and not (Path(pasta) / p.split("/")[-1]).exists(): erros.append("quadro congelado não gravado")
        elif not Path(p).exists():
            erros.append(f"vídeo não encontrado: {v.get('material_name')}")
    if re.search(r"\{(RECEITA|REACT|CTA|CACHE|FONTE|CONGELADO)[A-Z_]*\}", json.dumps([d, r["meta"]], ensure_ascii=False)):
        erros.append("sobrou marcador do molde no projeto")
    return sorted(set(erros))


def quadro(video, t_us, destino, ultimo=False):
    """o quadro do video em t (PNG, tamanho original) — o "Congelar" do CapCut. ultimo: o ultimo quadro do arquivo
    (le so o ultimo meio segundo, inverte e grava um PNG so: perto do fim o -ss as vezes nao devolve quadro, e gravar
    um PNG por quadro levava 16 s num video de 60 fps)"""
    pos = (["-sseof", "-0.5", "-i", str(video), "-vf", "reverse", "-frames:v", "1"] if ultimo else
           ["-ss", f"{t_us / 1e6:.6f}", "-i", str(video), "-frames:v", "1", "-update", "1"])
    r = subprocess.run([audio.ffmpeg_bin(), "-v", "error", "-y", *pos, str(destino)], capture_output=True, **audio._sem_janela())
    if r.returncode != 0 or not Path(destino).exists():
        raise ErroReact(f"Não consegui tirar o quadro congelado de {Path(video).name}.")


def grava(raiz, r, nome=None, capa=None):
    """pasta NOVA "<nome do video> - react" (capcut.grava_projeto), com o quadro congelado dentro. Trava se a
    checagem falhar; se algo der errado no meio, a pasta some."""
    erros = verifica(r)
    if erros:
        raise ErroReact("Projeto não gravado: " + "; ".join(erros))
    nome = nome or f"{Path(r['receita']).stem} - react"

    def extras(pasta):
        if r["png"]:
            quadro(r["receita"], r["congelar"]["us"], Path(pasta) / r["png"], bool(r["congelar"].get("final")))
        e2 = verifica(r, pasta)
        if e2:
            raise ErroReact("Projeto não gravado: " + "; ".join(e2))

    return capcut.grava_projeto(raiz, nome, r["draft"], r["meta"], capa=capa, extras=extras)


def gera(raiz, itens, react, cta=None, variar=False, cache=None, whisper=None, avisa=None, capas=None):
    """varios videos de cima, um react: um projeto por video. itens = [{"video", "enquadramento"?, "congelar"?}].
    whisper: motor de transcricao (pra pausa entre frases; None = so a pausa). Um erro num video nao para os outros:
    cada um volta com {"video", "projeto"} ou {"video", "erro"}, mais o ponto de congelar e o tempo."""
    avisa = avisa or (lambda *a: None)
    capas = Path(capas) if capas else None
    ik = info(react); ic = info(cta) if cta else None
    irs = []
    for it in itens:
        try: irs.append(info(it["video"]))
        except Exception as e: irs.append(e)
    ini = inicios_react(ik["dur_us"], [i["dur_us"] if isinstance(i, dict) else 0 for i in irs], variar)
    out = []
    for n, (it, ir, r0) in enumerate(zip(itens, irs, ini)):
        t0 = time.perf_counter(); v = Path(it["video"])
        avisa(f"Montando {v.name}", n / len(itens))
        res = {"video": str(v)}
        try:
            if isinstance(ir, Exception): raise ir
            if r0 is None:
                raise ErroReact(f"O react é mais curto que o vídeo “{v.name}”: o react tem {ik['dur_us'] / 1e6:.0f} s "
                                f"e o vídeo {ir['dur_us'] / 1e6:.0f} s. Use um react mais longo.")
            falas = transcreve(v, whisper) if (cta and whisper and it.get("congelar") is None) else None
            r = monta(v, react, it.get("enquadramento"), cta, r0, it.get("congelar"), cache, falas,
                      {"receita": ir, "react": ik, "cta": ic})
            capa = None
            if capas:
                capas.mkdir(parents=True, exist_ok=True); capa = capas / f"react_{n}.jpg"
                if not audio.capa(v, capa): capa = None
            res.update(projeto=grava(raiz, r, capa=capa), congelar=r["congelar"], inicio_react=r0 / 1e6,
                       avisos=r["avisos"], enquadramento=r["enquadramento"])
        except Exception as e:
            res["erro"] = str(e) if isinstance(e, capcut.ErroProjeto) else f"{v.name}: {e}"
        res["tempo_s"] = round(time.perf_counter() - t0, 2)
        out.append(res)
    avisa("Pronto", 1.0)
    return out
