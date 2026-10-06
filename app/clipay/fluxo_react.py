"""Tela React (Fase 2): o que a tela pede ao motor (react.py), em segundo plano, com o estado que ela le.
  confere      o arquivo escolhido (react, video de cima ou CTA): mensagens curtas, nada de erro tecnico do Windows
  quadro       um quadro pequeno do video (ffmpeg, em cache) pra montar a previa com os quadros de verdade
  pausas       onde cada video de cima congela (a mesma busca do motor), um por vez, em segundo plano
  gera         um projeto do CapCut por video, ate 3 ao mesmo tempo; a geracao fica gravada em disco: fechar o app no
               meio e pedir de novo continua sem duplicar projeto
Os videos nunca sao copiados nem carregados inteiros: o ffmpeg le direto de onde estao."""
import hashlib, json, shutil, subprocess, threading, time, traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from . import audio, capcut, react, transcricao

EXT_VIDEO = (".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm")
PARALELO = 3                                  # projetos ao mesmo tempo (o computador continua usavel)
SUMIU = "Esse vídeo não está mais nesse lugar. Ele foi movido ou apagado?"
GERACAO = {"job": None}
_TRAVA_GRAVA = threading.Lock()               # o indice do CapCut (root_meta_info) e' um arquivo so: um por vez
_QUADROS = threading.Semaphore(3)             # no maximo 3 ffmpeg tirando quadro ao mesmo tempo
_TRAVA_WHISPER = threading.Lock()             # uma transcricao por vez (a busca da pausa e a geracao usam o mesmo motor)


class Erro(Exception):
    pass


def config():
    try:
        return json.loads((react.PASTA / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def acesso():
    """quem usa o React vem da configuracao (assets/react/config.json, "acesso"). BETA: toda conta ativa"""
    return config().get("acesso", "todas_ativas") == "todas_ativas"


def _ref_clips():
    d = json.loads((react.PASTA / "draft_content.json").read_text(encoding="utf-8"))
    k = d["tracks"][1]["segments"]; t = d["tracks"][2]["segments"][0]["clip"]
    return k[0]["clip"], k[1]["clip"], t


def constantes():
    """o que a tela precisa pra montar a previa com as MESMAS contas do motor"""
    rk, rc, t = _ref_clips()
    return {"largura": react.W, "altura": react.H, "cobre_ate": react.COBRE_ATE, "degrade": [1185, 1240],
            "corte_padrao": react.enquadra_cima(1080, 1920)["corte"], "inicio_react": react.INICIO_REACT,
            "janela": list(react.JANELA), "headline": {"texto": react.HEADLINE, "x": t["transform"]["x"],
                                                       "y": t["transform"]["y"], "escala": t["scale"]["x"]},
            "acesso": acesso()}


# ---------------- conferir o arquivo ----------------
def confere(caminho, papel="cima"):
    """papel: "react" (embaixo, audio nao usado), "cima" (o som do resultado) ou "cta" (embaixo, com som)"""
    p = Path(caminho or "")
    if not caminho or not p.is_file():
        return {"erro": SUMIU}
    if p.suffix.lower() not in EXT_VIDEO:
        return {"erro": "Esse arquivo não é um vídeo. Escolha um MP4, MOV, MKV, M4V, AVI ou WEBM."}
    try:
        i = react.info(p)
    except Exception:                                 # noqa: BLE001 — qualquer falha de leitura vira a frase clara
        return {"erro": "Não consegui ler esse arquivo como vídeo. Ele pode estar incompleto ou corrompido."}
    if papel == "cima" and not i["tem_audio"]:
        return {"erro": "Esse vídeo não tem som. O som do resultado é o som do vídeo de cima."}
    out = {"caminho": str(p), "nome": p.name, "tamanho": p.stat().st_size, "duracao": i["dur_us"] / 1e6,
           "largura": i["largura"], "altura": i["altura"], "tem_audio": i["tem_audio"]}
    if papel == "cima":
        out["modo"] = react.enquadra_cima(i["largura"], i["altura"])["modo"]
    else:
        rk, rc, _ = _ref_clips()
        out["faixa"] = react.enquadra_faixa(i["largura"], i["altura"], rk if papel == "react" else rc)
    return out


# ---------------- quadros pequenos pra previa ----------------
def quadro(caminho, t, largura=360):
    """JPEG de um quadro em t (s), largura px, em cache. O ffmpeg pula direto pro ponto (nao le o video todo)."""
    p = Path(caminho)
    if p.suffix.lower() not in EXT_VIDEO or not p.is_file():
        return None
    largura = max(64, min(int(largura), 720)); t = max(0.0, float(t))
    st = p.stat()
    k = hashlib.sha1(f"{p.resolve()}|{st.st_size}|{st.st_mtime_ns}|{t:.2f}|{largura}|q1".encode()).hexdigest()
    arq = transcricao.pasta_dados() / "cache_react_quadros" / f"{k}.jpg"
    if arq.exists():
        return arq
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(f".{threading.get_ident()}.jpg")
    with _QUADROS:
        if arq.exists():
            return arq
        for tt in (t, max(0.0, t - 0.5), 0.0):          # depois do ultimo quadro o ffmpeg nao devolve nada
            r = subprocess.run([audio.ffmpeg_bin(), "-v", "error", "-y", "-threads", "2",   # 4K HEVC: ~215 MB por ffmpeg (sem isso, ~830)
                                "-ss", f"{tt:.3f}", "-i", str(p), "-frames:v", "1",
                                "-vf", f"scale={largura}:-2", "-q:v", "4", str(tmp)], capture_output=True, **audio._sem_janela())
            if r.returncode == 0 and tmp.exists() and tmp.stat().st_size:
                tmp.replace(arq); return arq
    tmp.unlink(missing_ok=True)
    return None


# ---------------- onde cada video congela (com CTA) ----------------
PAUSAS = {"itens": {}, "fila": [], "thread": None, "whisper": None}
_TRAVA_PAUSAS = threading.Lock()


def pede_pausas(videos, carrega_whisper):
    """poe na fila os videos que ainda nao tem o ponto de congelar; um trabalho so, um video por vez"""
    with _TRAVA_PAUSAS:
        for v in videos:
            v = str(v); it = PAUSAS["itens"].get(v)
            if it and it["estado"] in ("procurando", "pronto", "fila"):
                continue
            PAUSAS["itens"][v] = {"estado": "fila"}; PAUSAS["fila"].append(v)
        th = PAUSAS["thread"]
        if th is None or not th.is_alive():
            PAUSAS["thread"] = threading.Thread(target=_trabalha_pausas, args=(carrega_whisper,), daemon=True)
            PAUSAS["thread"].start()
    return estado_pausas(videos)


def _trabalha_pausas(carrega_whisper):
    while True:
        with _TRAVA_PAUSAS:
            if not PAUSAS["fila"]:
                PAUSAS["thread"] = None; return
            v = PAUSAS["fila"].pop(0); PAUSAS["itens"][v] = {"estado": "procurando"}
        try:
            if not Path(v).is_file():
                raise Erro(SUMIU)
            with _TRAVA_WHISPER:
                if PAUSAS["whisper"] is None:
                    PAUSAS["whisper"] = carrega_whisper() if carrega_whisper else None
            dur = react.duracao_us(v) / 1e6
            with _TRAVA_WHISPER:
                falas = react.transcreve(v, PAUSAS["whisper"]) if PAUSAS["whisper"] else None
            c = react.ponto_congelar(v, dur, falas)
            PAUSAS["itens"][v] = {"estado": "pronto", "t": round(c["t"], 3), "boa": c["boa"],
                                  "pausa_curta": c.get("pausa_curta", False), "motivo": c["motivo"], "duracao": dur}
        except Exception as e:                        # noqa: BLE001 — aparece na linha do video; o motor acha de novo ao gerar
            traceback.print_exc()
            PAUSAS["itens"][v] = {"estado": "erro", "erro": SUMIU if not Path(v).exists() else _curto(e)}


def estado_pausas(videos=None):
    its = PAUSAS["itens"]
    return {"itens": {v: dict(its[v]) for v in (videos or its) if v in its}}


# ---------------- gerar ----------------
def _curto(x):
    m = str(x).strip().splitlines()[0] if str(x).strip() else type(x).__name__
    return m if len(m) <= 140 else m[:137] + "…"


def _arq_geracao():
    return transcricao.pasta_dados() / "geracao_react.json"


def _chave(react_p, itens, cta, variar, raiz):
    """o que define a geracao. O ponto de congelar fica de fora: e' o motor que acha (o mesmo, sempre); se o app fechou
    antes da busca terminar, na volta ele ja vem pronto e a geracao tem que ser reconhecida como a mesma"""
    corpo = [str(Path(react_p).resolve()), str(Path(cta).resolve()) if cta else None, bool(variar), str(raiz),
             [(str(Path(i["video"]).resolve()), json.dumps(i.get("enquadramento") or {}, sort_keys=True)) for i in itens]]
    return hashlib.sha1(json.dumps(corpo).encode()).hexdigest()


_TRAVA_SALVA = threading.Lock()


def _salva(job):
    """grava o andamento (um por vez: 3 projetos terminando juntos nao podem gravar um estado velho por cima)"""
    with _TRAVA_SALVA:
        try:
            f = _arq_geracao(); tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps({"chave": job["chave"], "linhas": [dict(l) for l in job["linhas"]]}, ensure_ascii=False),
                           encoding="utf-8")
            tmp.replace(f)
        except OSError:
            pass


def _registrados(raiz):
    try:
        d = json.loads((Path(raiz) / "root_meta_info.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {Path(x.get("draft_fold_path", "")).name for x in d.get("all_draft_store", [])}


def _feitos_antes(chave, raiz):
    """projetos que ja ficaram prontos desta mesma geracao (o app fechou no meio): nao refaz nem duplica.
    O app pode ter fechado entre gravar o projeto e anotar "pronto": vale o nome previsto, se ele esta na lista do
    CapCut. Pasta pela metade (fechou no meio da gravacao, fora da lista do CapCut) e' nossa: sai, e o projeto e'
    feito de novo com o mesmo nome."""
    try:
        d = json.loads(_arq_geracao().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if d.get("chave") != chave:
        return {}
    feitos, reg = {}, _registrados(raiz)
    for l in d["linhas"]:
        if l["estado"] == "pronto" and l.get("projeto") and (Path(raiz) / l["projeto"]).exists():
            feitos[l["numero"]] = l
        elif l["estado"] == "gravando" and l.get("previsto") and (Path(raiz) / l["previsto"]).is_dir():
            if l["previsto"] in reg:
                feitos[l["numero"]] = dict(l, estado="pronto", projeto=l["previsto"])
            else:
                shutil.rmtree(Path(raiz) / l["previsto"], ignore_errors=True)
    return feitos


def gera(react_p, itens, raiz, cta=None, variar=True, cache=None, carrega_whisper=None, so=None):
    """um projeto por video de cima, em segundo plano, ate PARALELO ao mesmo tempo. itens = [{"video",
    "enquadramento"?, "congelar"?}] (congelar: o ponto que a tela ja mostrou; sem ele, o motor acha). so: numeros a
    refazer (os que falharam). A mesma geracao pedida de novo: devolve a que esta rodando, ou continua o que falta."""
    if not itens:
        raise Erro("Nenhum vídeo para gerar.")
    chave = _chave(react_p, itens, cta, variar, raiz)
    ant = GERACAO["job"]
    if ant and not ant["parado"]:
        if ant["chave"] == chave and so is None:
            return ant
        raise Erro("Já estou criando os projetos. Espere terminar ou cancele.")
    for p, msg in ((react_p, "O vídeo de react não está mais nesse lugar. Ele foi movido ou apagado?"),
                   (cta, "O vídeo do CTA não está mais nesse lugar. Ele foi movido ou apagado?")):
        if p and not Path(p).is_file():
            raise Erro(msg)
    ik = react.info(react_p); ic = react.info(cta) if cta else None
    irs = []
    for it in itens:
        try: irs.append(react.info(it["video"]))
        except Exception as e: irs.append(e)          # noqa: BLE001 — vira o erro do cartao
    inis = react.inicios_react(ik["dur_us"], [i["dur_us"] if isinstance(i, dict) else 0 for i in irs], variar)
    feitos = dict(_feitos_antes(chave, raiz))
    velhas = {l["numero"]: l for l in ant["linhas"]} if ant and ant["chave"] == chave else {}
    feitos.update({n: l for n, l in velhas.items() if l["estado"] == "pronto"})
    linhas = []
    for n, (it, ir, r0) in enumerate(zip(itens, irs, inis), 1):
        if n in feitos and (so is None or n not in so):
            linhas.append(dict(feitos[n])); continue
        if so is not None and n not in so and n in velhas:
            linhas.append(dict(velhas[n])); continue
        v = Path(it["video"])
        dur = (ir["dur_us"] + (ic["dur_us"] if ic else 0)) / 1e6 if isinstance(ir, dict) else None
        linhas.append({"numero": n, "video": str(v), "nome": f"{v.stem} - react", "duracao": dur,
                       "inicio_react": None if r0 is None else r0 / 1e6, "estado": "fila", "erro": None, "projeto": None})
    job = {"linhas": linhas, "cancelar": threading.Event(), "parado": False, "t0": time.perf_counter(), "tempo": None,
           "chave": chave}
    GERACAO["job"] = job; _salva(job)
    infos = {"react": ik, "cta": ic}

    def um(l):
        if l["estado"] == "pronto": return
        if so is not None and l["numero"] not in so and l["estado"] in ("erro", "cancelado"): return
        if job["cancelar"].is_set():
            l["estado"] = "cancelado"; _salva(job); return
        it, ir = itens[l["numero"] - 1], irs[l["numero"] - 1]
        v = Path(it["video"])
        try:
            l.update(estado="montando", erro=None); t0 = time.perf_counter()
            if isinstance(ir, Exception):
                raise ir
            if not v.is_file():
                raise Erro(SUMIU)
            if l["inicio_react"] is None:
                raise Erro(f"O react é mais curto que este vídeo ({ik['dur_us'] / 1e6:.0f} s contra "
                           f"{ir['dur_us'] / 1e6:.0f} s). Use um react mais longo.")
            cong = it.get("congelar")
            falas = None
            if cta and cong is None and carrega_whisper:
                with _TRAVA_WHISPER:
                    if PAUSAS["whisper"] is None: PAUSAS["whisper"] = carrega_whisper()
                    falas = react.transcreve(v, PAUSAS["whisper"])
                if job["cancelar"].is_set():
                    l["estado"] = "cancelado"; _salva(job); return
            r = react.monta(v, react_p, it.get("enquadramento"), cta, react.us(l["inicio_react"]), cong, cache, falas,
                            dict(infos, receita=ir))
            tmp = transcricao.pasta_dados() / "temp"; tmp.mkdir(parents=True, exist_ok=True)
            capa = tmp / f"capa_react_{l['numero']}.jpg"
            if not audio.capa(v, capa): capa = None
            with _TRAVA_GRAVA:
                l.update(estado="gravando", previsto=capcut.nome_livre(raiz, l["nome"])); _salva(job)   # o nome, antes de gravar
                l["projeto"] = react.grava(raiz, r, nome=l["previsto"], capa=capa)
            l.update(estado="pronto", congelar=r["congelar"], avisos=r["avisos"], tempo=round(time.perf_counter() - t0, 2))
        except Exception as e:                       # noqa: BLE001 — um video que falha nao derruba os outros
            traceback.print_exc()
            l.update(estado="erro", erro=SUMIU if not v.exists() else _curto(e))
        _salva(job)

    def roda():
        try:
            with ThreadPoolExecutor(PARALELO) as ex:
                list(ex.map(um, job["linhas"]))
        finally:
            job["tempo"] = round(time.perf_counter() - job["t0"], 1); job["parado"] = True; _salva(job)
    job["thread"] = threading.Thread(target=roda, daemon=True); job["thread"].start()
    return job


def estado_geracao():
    j = GERACAO["job"]
    if not j:
        return {"ativo": False}
    return {"ativo": True, "parado": j["parado"], "tempo": j["tempo"], "cancelado": j["cancelar"].is_set(),
            "prontos": sum(l["estado"] == "pronto" for l in j["linhas"]), "total": len(j["linhas"]),
            "linhas": [dict(l) for l in j["linhas"]]}


def cancela_geracao():
    j = GERACAO["job"]
    if j: j["cancelar"].set()
