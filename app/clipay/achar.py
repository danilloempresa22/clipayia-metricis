"""Cortes Fase 3: achar TODOS os assuntos completos de um podcast com IA (so o texto da transcricao) e gerar um
projeto do CapCut por corte. A IA so devolve ids, categorias e forca; todo o resto e' conferido aqui, contra a
transcricao real: ids, ordem, sobreposicao, minimo, teto (vira 'longo', nunca corta), frase de transicao no fim,
filtro por tipo e limites puxados pro audio (longo.ajusta_limite).
BETA: a IA roda no proprio computador pelo Ollama (gratis, sem chave, nada sai do PC). A versao paga troca so
`chama_ia` pela Edge Function; a configuracao fica em assets/cortes/achar.json."""
import hashlib, json, re, unicodedata, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from . import audio, capcut, cortes, longo, transcricao

CFG_PATH = Path(__file__).resolve().parent / "assets" / "cortes" / "achar.json"
TIPOS = ("historia", "polemico", "emocional", "engracado", "conselho")
NOME_TIPO = {"historia": "Historia", "polemico": "Polemico", "emocional": "Emocional", "engracado": "Engracado",
             "conselho": "Conselho"}
# fim de assunto que na verdade ja e' a ponte pro proximo: sai do corte
TRANSICAO = re.compile(r"^\W*(e\s+)?(mudando de assunto|mudando um pouco|voltando (ao|pro|para o|pra)|falando nisso|"
                       r"agora (vamos|vou|deixa)|deixa eu te perguntar|pr[oó]xima pergunta|outra coisa|"
                       r"bora pr[ao]|vamos (falar|pra|para)|e sobre|e quanto a|aproveitando)", re.I)
# frase que e' so resposta curta ("Com certeza.", "Nossa, demais.", "entendeu?"): nao abre corte (depende do que veio antes)
MULETA = re.compile(r"^\W*((e|ah|ai|aí|pô|po|cara|nossa|sim|não|nao|é|e aí|exato|exatamente|isso|tá|ta|beleza|show|"
                    r"legal|massa|demais|com certeza|claro|pois é|verdade|entendeu|entende|né|fechou|perfeito|top|uhum|"
                    r"aham)[\s,.!?…]*)+$", re.I)
MSG_MANUAL = ("Você pode digitar o início e o fim de cada corte (modo manual) e o Clipay monta do mesmo jeito.")


class SemIA(Exception):
    """sem a IA (desligada, fora do ar, sem internet ou sem cota): a tela mostra a mensagem e o modo manual"""


def config():
    return json.loads(CFG_PATH.read_text(encoding="utf-8"))


# ---------------- o pedido ----------------
REGRAS = """Você recebe um trecho da transcrição de um podcast em português do Brasil, uma frase por linha:
id | tempo | texto

Sua tarefa: achar TODOS os ASSUNTOS completos que dão um corte bom para redes sociais.

Regras obrigatórias:
1. A unidade é um ASSUNTO INTEIRO. O corte começa na frase que introduz o assunto e termina na ÚLTIMA frase que ainda pertence a ele, quando o assunto muda.
2. Histórias vão ATÉ O DESFECHO. Nunca termine uma história logo depois do começo ("um dia eu levei um tiro" e parar ali é ERRADO: continue até o fim do que aconteceu).
3. A frase de transição para o próximo assunto ("mudando de assunto", "voltando ao episódio", "e sobre…", uma nova pergunta do apresentador) NÃO entra.
4. Se o começo natural for uma pergunta curta do apresentador (até uns 15 segundos) sem a qual o corte não se entende, comece nela. Evite começar em frase que depende do que veio antes ("então", "mas", "isso", "ele" sem dizer quem).
5. Categorias (uma ou duas, a primeira é a principal): historia (começo, meio e fim), polemico, emocional (triste, perda, virada), engracado, conselho (ordem ou promessa clara).
6. Força de 0 a 100, pesando: gancho nos primeiros 5 segundos, a ideia fechar sozinha sem contexto, emoção ou conflito, e o desfecho.
7. Assunto com menos de 30 segundos não serve. Não existe duração máxima: se o assunto for longo, devolva ele INTEIRO.
8. Entregue TODOS os assuntos bons, não só os melhores. Assuntos não se sobrepõem.
8b. Um podcast muda de assunto MUITAS vezes: num trecho de 10 minutos costuma haver de 3 a 8 assuntos. Cada pergunta do apresentador com a resposta completa do convidado costuma ser um assunto. NUNCA junte assuntos diferentes num só nem devolva o trecho inteiro como um assunto.
8c. A primeira frase do corte tem que fazer sentido para quem nunca viu o podcast. Não comece em "com certeza", "entendeu?", "nossa", "sim", "é" ou no meio de uma resposta.
8d. A abertura do episódio (apresentação do convidado) e a despedida (agradecimentos, "tamo junto") não são cortes.
9. Use SÓ ids que existem nas linhas abaixo. Não escreva o texto das frases.
10. Se um assunto já começou antes da primeira linha ou continua depois da última, use o primeiro ou o último id do trecho.

Responda só o JSON: {"assuntos": [{"ini_id": 412, "fim_id": 468, "categorias": ["historia", "emocional"], "forca": 92, "titulo": "título curto", "motivo": "por que é bom, curto"}]}"""

ESQUEMA = {"type": "object", "required": ["assuntos"], "properties": {"assuntos": {"type": "array", "items": {
    "type": "object", "required": ["ini_id", "fim_id", "categorias", "forca", "titulo", "motivo"],
    "properties": {"ini_id": {"type": "integer"}, "fim_id": {"type": "integer"},
                   "categorias": {"type": "array", "items": {"type": "string", "enum": list(TIPOS)}},
                   "forca": {"type": "integer"}, "titulo": {"type": "string"}, "motivo": {"type": "string"}}}}}}


def hms(t):
    t = int(t); return f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}"


def linhas(frases):
    return "\n".join(f"{f['id']} | {hms(f['ini'])} | {f['texto']}" for f in frases)


def janelas(frases, janela_s=900, sobreposicao_s=120):
    """listas de frases de ~15 min, cada uma comecando 2 min antes do fim da anterior"""
    if not frases: return []
    out, ini, fim_total = [], frases[0]["ini"], frases[-1]["fim"]
    while True:
        js = [f for f in frases if ini <= f["ini"] < ini + janela_s]
        if js: out.append(js)
        if ini + janela_s >= fim_total: return out
        ini += janela_s - sobreposicao_s


def chama_ollama(texto, cfg):
    corpo = {"model": cfg["modelo"], "stream": False, "format": ESQUEMA,
             "options": {"temperature": 0, "num_ctx": cfg.get("num_ctx", 16384)},
             "messages": [{"role": "system", "content": REGRAS}, {"role": "user", "content": texto}]}
    req = urllib.request.Request(cfg["url"].rstrip("/") + "/api/chat", data=json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=cfg.get("tempo_limite_s", 600)) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        corpo = e.read().decode(errors="ignore")
        if e.code == 404 and "not found" in corpo:
            raise SemIA(f"A IA local ({cfg['modelo']}) ainda não foi baixada. " + MSG_MANUAL)
        raise SemIA(f"A IA local respondeu com erro ({e.code}). " + MSG_MANUAL)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise SemIA("A IA local (Ollama) não está aberta neste computador. " + MSG_MANUAL)
    return d["message"]["content"], {"entrada": d.get("prompt_eval_count", 0), "saida": d.get("eval_count", 0),
                                     "segundos": round(d.get("total_duration", 0) / 1e9, 1)}


def chama_ia(texto, cfg):
    """(texto da resposta, uso). So o Ollama no BETA; a Edge Function entra aqui na versao paga."""
    if cfg["provedor"] == "ollama":
        return chama_ollama(texto, cfg)
    raise SemIA(f"Provedor de IA desconhecido: {cfg['provedor']}. " + MSG_MANUAL)


def interpreta(resposta):
    """JSON do modelo -> lista de assuntos (tolerante: texto em volta, campos faltando ou com tipo errado)"""
    try:
        d = json.loads(resposta)
    except ValueError:
        m = re.search(r"\{.*\}", resposta or "", re.S)
        try:
            d = json.loads(m[0]) if m else {}
        except ValueError:
            d = {}
    out = []
    for a in (d.get("assuntos") if isinstance(d, dict) else None) or []:
        try:
            cats = [c for c in a.get("categorias") or [] if c in TIPOS][:2]
            out.append({"ini_id": int(a["ini_id"]), "fim_id": int(a["fim_id"]), "categorias": cats,
                        "forca": max(0, min(100, int(a.get("forca", 0)))), "titulo": str(a.get("titulo", ""))[:120],
                        "motivo": str(a.get("motivo", ""))[:300]})
        except (KeyError, TypeError, ValueError):
            continue
    return out


# ---------------- costura das janelas ----------------
def costura(por_janela):
    """[(assuntos, primeiro_id, ultimo_id)] -> uma lista. Id fora da janela (o modelo nao viu essa frase) e' inventado:
    o assunto sai. O mesmo assunto visto em duas janelas DIFERENTES (ids se cruzando e um deles encostado na borda da
    sua janela, ou metade ou mais em comum) vira um so: a uniao dos ids (nunca termina antes do desfecho que a outra
    janela viu), a forca e as categorias do mais forte. Dentro da mesma janela nada se junta (a validacao resolve)."""
    tudo = []
    for k, (assuntos, p, u) in enumerate(por_janela):
        for a in assuntos:
            if p <= a["ini_id"] <= u and p <= a["fim_id"] <= u:
                tudo.append(dict(a, borda=a["ini_id"] <= p or a["fim_id"] >= u, jans={k}))
    tudo.sort(key=lambda a: (a["ini_id"], a["fim_id"]))
    out = []
    for a in tudo:
        b = next((b for b in out if not (a["jans"] & b["jans"])
                  and min(a["fim_id"], b["fim_id"]) >= max(a["ini_id"], b["ini_id"])), None)
        if b is not None:
            comum = min(a["fim_id"], b["fim_id"]) - max(a["ini_id"], b["ini_id"]) + 1
            menor = min(a["fim_id"] - a["ini_id"], b["fim_id"] - b["ini_id"]) + 1
            if a["borda"] or b["borda"] or comum * 2 >= menor:
                forte = a if a["forca"] > b["forca"] else b
                b.update({k: forte[k] for k in ("categorias", "forca", "titulo", "motivo")},
                         ini_id=min(a["ini_id"], b["ini_id"]), fim_id=max(a["fim_id"], b["fim_id"]),
                         borda=a["borda"] and b["borda"], jans=a["jans"] | b["jans"])
                continue
        out.append(a)
    return [{k: v for k, v in a.items() if k not in ("borda", "jans")} for a in out]


# ---------------- validacao (nunca confia no modelo) ----------------
def valida(assuntos, frases, cfg):
    """ids existem e em ordem; fim de transicao sai (se sobra o minimo); minimo; 'longo' acima do teto; piso de forca;
    sem sobreposicao (fica o mais forte). Devolve a lista COMPLETA (todos os tipos), na ordem do podcast."""
    idx = {f["id"]: i for i, f in enumerate(frases)}
    ok = []
    for a in assuntos:
        if a["ini_id"] not in idx or a["fim_id"] not in idx or not a["categorias"]:
            continue                                            # id inventado ou sem tipo: descarta
        i, j = sorted((idx[a["ini_id"]], idx[a["fim_id"]]))
        while j > i and TRANSICAO.match(frases[j]["texto"]) and frases[j - 1]["fim"] - frases[i]["ini"] >= cfg["minimo_s"]:
            j -= 1                                              # a ponte pro proximo assunto nao entra
        while i < j and (MULETA.match(frases[i]["texto"]) or TRANSICAO.match(frases[i]["texto"])
                         and frases[i]["fim"] - frases[i]["ini"] < 4) \
                and frases[j]["fim"] - frases[i + 1]["ini"] >= cfg["minimo_s"]:
            i += 1                                              # "Com certeza." / "mudando de assunto," nao abrem corte
        dur = frases[j]["fim"] - frases[i]["ini"]
        if dur < cfg["minimo_s"] or a["forca"] < cfg["piso_forca"]:
            continue
        ok.append(dict(a, i=i, j=j, dur=dur, longo=dur > cfg["teto_s"]))
    ok.sort(key=lambda a: (-a["forca"], a["i"]))
    final = []
    for a in ok:                                                # o mais forte fica; quem cruza com ele sai
        if all(a["j"] < b["i"] or a["i"] > b["j"] for b in final):
            final.append(a)
    return sorted(final, key=lambda a: a["i"])


def finaliza(lista, frases, pausas, tipos=TIPOS):
    """filtro por tipo (principal OU secundario marcado), limites no audio, numero na ordem do podcast"""
    out = []
    for a in lista:
        if not any(c in tipos for c in a["categorias"]):
            continue
        f0, f1 = frases[a["i"]], frases[a["j"]]
        ini = longo.ajusta_limite(f0["ini"], "inicio", pausas)
        fim = longo.ajusta_limite(f1["fim"], "fim", pausas)
        out.append({"numero": len(out) + 1, "tipo": a["categorias"][0], "categorias": a["categorias"],
                    "ini": ini, "fim": fim, "duracao": round(fim - ini, 2), "forca": a["forca"], "longo": a["longo"],
                    "ini_id": f0["id"], "fim_id": f1["id"], "primeira": f0["texto"], "ultima": f1["texto"],
                    "titulo": a["titulo"], "motivo": a["motivo"]})
    return out


# ---------------- tudo junto ----------------
def _chave(frases, cfg):
    h = hashlib.sha1(json.dumps([[f["id"], f["texto"]] for f in frases], ensure_ascii=False).encode()).hexdigest()
    return hashlib.sha1(f"{h}|{cfg['provedor']}|{cfg['modelo']}|regras-v{cfg['versao_regras']}|"
                        f"{cfg['janela_s']}|{cfg['sobreposicao_s']}".encode()).hexdigest()


def _cache(chave):
    p = transcricao.pasta_dados() / "cache_achar"; p.mkdir(parents=True, exist_ok=True)
    return p / f"{chave}.json"


def assuntos(frases, cfg=None, chamar=None, progresso=None, cancelado=None):
    """todos os assuntos achados pela IA (antes da validacao), com cache: a mesma transcricao nunca chama de novo.
    O teto, o piso e os tipos NAO entram na chave (sao aplicados depois): muda-los nao chama a IA."""
    cfg = cfg or config(); chamar = chamar or chama_ia; cancelado = cancelado or (lambda: False)
    arq = _cache(_chave(frases, cfg))
    if arq.exists():
        try:
            return json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    js = janelas(frases, cfg["janela_s"], cfg["sobreposicao_s"])
    feitas = {"n": 0}; uso = []

    def uma(jan):
        if cancelado(): raise longo.Cancelado()
        txt, u = chamar(linhas(jan), cfg)
        feitas["n"] += 1; uso.append(u)
        if progresso: progresso(feitas["n"], len(js))
        return interpreta(txt), jan[0]["id"], jan[-1]["id"]
    with ThreadPoolExecutor(max(1, cfg.get("paralelo", 1))) as ex:
        por_janela = list(ex.map(uma, js))
    r = {"assuntos": costura(por_janela), "uso": uso, "janelas": len(js), "modelo": cfg["modelo"],
         "por_janela": [[a, p, u] for a, p, u in por_janela]}           # so ids/forca/titulo: pra conferir a costura
    tmp = arq.with_suffix(".tmp"); tmp.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8"); tmp.replace(arq)
    return r


def achar_cortes(transcricao_longa, tipos=TIPOS, cfg=None, chamar=None, progresso=None, cancelado=None):
    """transcricao_longa: o resultado de longo.transcreve / longo.resultado (frases + pausas). Devolve
    {"cortes": [...], "todos": n antes do filtro de tipo, "uso": tokens por janela, "modelo"}."""
    cfg = cfg or config()
    tipos = [t for t in tipos if t in TIPOS]
    if not tipos:
        raise ValueError("Marque pelo menos um tipo de corte.")
    frases, pausas = transcricao_longa["frases"], transcricao_longa["pausas"]
    r = assuntos(frases, cfg, chamar, progresso, cancelado)
    lista = valida(r["assuntos"], frases, cfg)
    return {"cortes": finaliza(lista, frases, pausas, tipos), "todos": len(lista), "uso": r["uso"], "modelo": r["modelo"]}


# ---------------- gerar todos ----------------
def nome_corte(video, c):
    base = unicodedata.normalize("NFKD", Path(video).stem).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9 _-]+", " ", base); base = re.sub(r"\s+", " ", base).strip() or "video"
    return f"{base} - corte {c['numero']:02d} - {NOME_TIPO[c['tipo']]}" + (" - longo" if c["longo"] else "")


def gera_todos(video, lista, raiz, cache=None, musica=None, progresso=None, cancelado=None):
    """um projeto do CapCut por corte (montador da Fase 1), com a headline de exemplo. Um corte que falhar nao
    derruba os outros: vai pra lista de erros. Devolve {"criados": [nomes], "erros": [(numero, msg)]}."""
    cancelado = cancelado or (lambda: False)
    criados, erros = [], []
    tmp = transcricao.pasta_dados() / "temp"; tmp.mkdir(parents=True, exist_ok=True)
    for k, c in enumerate(lista):
        if cancelado(): raise longo.Cancelado()
        if progresso: progresso(k, len(lista), c)
        try:
            r = cortes.monta(video, c["ini"], c["fim"], cache=cache, musica=musica)
            capa = tmp / f"capa_corte_{k}.jpg"
            audio.capa(video, capa, c["ini"] + 0.5)
            criados.append(cortes.grava(raiz, nome_corte(video, c), r, capa=capa))
        except (capcut.ErroProjeto, RuntimeError, OSError, ValueError) as e:
            erros.append((c["numero"], str(e)))
    if progresso: progresso(len(lista), len(lista), None)
    return {"criados": criados, "erros": erros}
