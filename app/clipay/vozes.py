"""Quem fala (Cortes): separa as vozes no proprio computador, sem enviar audio, e diz qual e' o apresentador.
1) por janela da Fase 2 (mesmos limites, mesmo cache, retomavel): o audio e' relido (a transcricao NAO e' refeita),
   cada trecho de fala entre pausas vira pedacos de ate 3 s e cada pedaco ganha uma "impressao da voz" (embedding
   CAM++ do 3D-Speaker, via sherpa-onnx, 192 numeros). Grava por janela: so os tempos e as impressoes (~10 KB/min).
2) no fim, UM agrupamento com as impressoes do video inteiro: os rotulos (A, B...) sao os mesmos do comeco ao fim
   (agrupar janela por janela trocaria o A de uma janela pelo B da outra).
3) cada frase fica com a voz que mais fala dentro dela; o apresentador e' a voz que mais pergunta e tem as falas
   mais curtas (palpite com confianca; trocavel por parametro)."""
import io, math, os, threading, time, urllib.request
import numpy as np
from . import audio, longo, transcricao

VERSAO = 1
URL_MODELO = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
              "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx")
PEDACO_MAX = 3.0                     # s por impressao (fala corrida e' de uma pessoa so, quase sempre)
PEDACO_MIN = 0.5                     # trecho mais curto que isso nao da impressao confiavel (rotulado pelos vizinhos)
MESMA_VOZ = 0.55                     # semelhanca (cosseno) a partir da qual dois grupos sao a mesma pessoa
VOZ_MIN = 0.03                       # voz com menos de 3% da fala e' ruido/risada: vai pro grupo mais parecido
LETRAS = "ABCDEFGHIJ"


# ---------------- modelo ----------------
def arq_modelo():
    return transcricao.pasta_dados() / "modelos" / "voz" / "campplus.onnx"


def baixa_modelo(progresso=None):
    f = arq_modelo()
    if f.exists(): return f
    f.parent.mkdir(parents=True, exist_ok=True); tmp = f.with_suffix(".part")
    with urllib.request.urlopen(URL_MODELO) as r, open(tmp, "wb") as o:
        total = int(r.headers.get("Content-Length", 0)); feito = 0
        while bloco := r.read(1 << 20):
            o.write(bloco); feito += len(bloco)
            if progresso and total: progresso(feito, total)
    tmp.replace(f)
    return f


class Impressao:
    """embedding de voz (sherpa-onnx). Uma instancia por processo; compute e' sequencial."""
    def __init__(self, threads=None):
        import sherpa_onnx
        cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(baixa_modelo()),
                                                          num_threads=threads or transcricao.nucleos_fisicos())
        self.ext = sherpa_onnx.SpeakerEmbeddingExtractor(cfg); self.dim = self.ext.dim
        self.trava = threading.Lock()

    def __call__(self, x):
        with self.trava:
            s = self.ext.create_stream()
            s.accept_waveform(audio.SR, np.ascontiguousarray(x, np.float32)); s.input_finished()
            return np.asarray(self.ext.compute(s), np.float32)


# ---------------- por janela (cache) ----------------
def _arq(pasta, k):
    return pasta / f"vozes_v{VERSAO}_{k:04d}.npz"


def le_vozes(pasta, k):
    f = _arq(pasta, k)
    try:
        if not f.exists(): return None
        z = np.load(f)
        return {"seg": z["seg"], "emb": z["emb"].astype(np.float32)}
    except (OSError, ValueError, KeyError):
        return None


def grava_vozes(pasta, k, seg, emb):
    f = _arq(pasta, k); tmp = f.with_name(f.name + ".tmp")
    b = io.BytesIO(); np.savez_compressed(b, seg=np.asarray(seg, np.float32).reshape(-1, 2),
                                          emb=np.asarray(emb, np.float16).reshape(len(seg), -1))
    tmp.write_bytes(b.getvalue()); tmp.replace(f)


def falas(jan):
    """trechos de fala da janela = o que nao e' pausa (as pausas ja estao no cache da Fase 2)"""
    out, c = [], jan["ini"]
    for a, b in sorted(jan["pausas"]):
        if a > c + 1e-3: out.append([c, a])
        c = max(c, b)
    if jan["fim"] > c + 1e-3: out.append([c, jan["fim"]])
    return out


def pedacos(trechos):
    out = []
    for a, b in trechos:
        if b - a < PEDACO_MIN: continue
        n = max(1, math.ceil((b - a) / PEDACO_MAX)); d = (b - a) / n
        out += [[a + i * d, a + (i + 1) * d] for i in range(n)]
    return out


def impressoes_janela(imp, video, jan, cancelado=None):
    x = audio.pcm(video, jan["ini"], jan["fim"] - jan["ini"])
    seg, emb = [], []
    for a, b in pedacos(falas(jan)):
        if cancelado and cancelado(): raise longo.Cancelado()
        y = x[int((a - jan["ini"]) * audio.SR):int((b - jan["ini"]) * audio.SR)]
        if len(y) < PEDACO_MIN * audio.SR * 0.9 or float(np.abs(y).max()) < 1e-3: continue
        seg.append([a, b]); emb.append(imp(y))
    return seg, emb


def identifica(video, modelo="preciso", imp=None, progresso=None, cancelado=None):
    """impressoes de voz do video inteiro, janela por janela da Fase 2 (exige a transcricao pronta), retomando do
    cache. Devolve (seg (n,2), emb (n,d)). progresso(dict) por janela."""
    cancelado = cancelado or (lambda: False)
    pasta = longo.pasta_cache(video, modelo)
    js = []; k = 0
    while (j := longo.le_janela(pasta, k)) is not None:
        js.append(j); k += 1
    dur = audio.duracao(video) if video else None                  # duracao de qualquer midia (o teste usa WAV)
    if not js or (dur and js[-1]["fim"] < dur - 1e-3):
        raise RuntimeError("A transcrição deste vídeo ainda não terminou.")
    t0 = time.perf_counter(); segs, embs = [], []; do_cache = 0
    for k, j in enumerate(js):
        if cancelado(): raise longo.Cancelado()
        v = le_vozes(pasta, k)
        if v is None:
            if imp is None: imp = Impressao()
            s, e = impressoes_janela(imp, video, j, cancelado)
            grava_vozes(pasta, k, s, e); v = le_vozes(pasta, k)
        else:
            do_cache += 1
        segs.append(v["seg"]); embs.append(v["emb"])
        if progresso:
            progresso({"janelas_prontas": k + 1, "janelas_total": len(js), "do_cache": do_cache,
                       "decorrido_s": round(time.perf_counter() - t0, 1)})
    seg = np.concatenate([s for s in segs if len(s)]) if any(len(s) for s in segs) else np.zeros((0, 2), np.float32)
    emb = np.concatenate([e for e in embs if len(e)]) if len(seg) else np.zeros((0, 192), np.float32)
    return seg, emb


# ---------------- agrupamento global ----------------
def _norm(e):
    return e / np.maximum(np.linalg.norm(e, axis=1, keepdims=True), 1e-9)


def agrupa(emb, dur, mesma=MESMA_VOZ, voz_min=VOZ_MIN, iters=15):
    """rotulo (0..k-1) de cada impressao, com o video inteiro de uma vez. Comeca com muitos grupos (k-means com
    sementes espalhadas), junta os grupos parecidos (centro com cosseno >= mesma) e devolve grupos minusculos (< 3%
    da fala) ao mais parecido. Rotulo 0 = quem mais fala."""
    n = len(emb)
    if n == 0: return np.zeros(0, int)
    e = _norm(emb.astype(np.float32)); w = np.asarray(dur, np.float32)
    k = min(8, n); rng = np.random.default_rng(0)
    c = [e[rng.integers(n)]]
    for _ in range(1, k):                                   # k-means++: sementes longe umas das outras
        d = np.clip(1 - np.max(e @ np.array(c).T, axis=1), 0, None)
        c.append(e[rng.choice(n, p=d / d.sum())] if d.sum() > 0 else e[rng.integers(n)])
    c = np.array(c)
    for _ in range(iters):
        lab = np.argmax(e @ c.T, axis=1)
        c = _norm(np.array([(e[lab == i] * w[lab == i, None]).sum(0) if (lab == i).any() else c[i] for i in range(len(c))]))
    while True:                                             # junta os parecidos
        lab = np.argmax(e @ c.T, axis=1)
        vivos = [i for i in range(len(c)) if (lab == i).any()]
        c = c[vivos]; lab = np.argmax(e @ c.T, axis=1)
        if len(c) < 2: break
        s = c @ c.T; np.fill_diagonal(s, -1)
        i, j = np.unravel_index(np.argmax(s), s.shape)
        if s[i, j] < mesma: break
        m = (lab == i) | (lab == j)
        c[i] = _norm((e[m] * w[m, None]).sum(0, keepdims=True))[0]; c = np.delete(c, j, 0)
    while len(c) > 1:                                       # grupos minusculos: ruido, risada, sobreposicao
        lab = np.argmax(e @ c.T, axis=1)
        peso = np.array([w[lab == i].sum() for i in range(len(c))]) / max(w.sum(), 1e-9)
        i = int(np.argmin(peso))
        if peso[i] >= voz_min: break
        c = np.delete(c, i, 0)
    lab = np.argmax(e @ c.T, axis=1)
    ordem = np.argsort([-w[lab == i].sum() for i in range(len(c))])
    novo = np.empty(len(c), int); novo[ordem] = np.arange(len(c))
    return novo[lab]


def locutor_das_frases(frases, seg, lab):
    """cada frase: a voz com mais tempo de fala dentro dela; sem pedaco dentro (frase curta), o pedaco mais perto"""
    out = []
    if len(seg) == 0:
        return ["A"] * len(frases)
    meio = (seg[:, 0] + seg[:, 1]) / 2
    for f in frases:
        ov = np.minimum(seg[:, 1], f["fim"]) - np.maximum(seg[:, 0], f["ini"])
        m = ov > 0
        if m.any():
            tot = np.bincount(lab[m], weights=ov[m])
            out.append(LETRAS[int(np.argmax(tot))])
        else:
            out.append(LETRAS[int(lab[int(np.argmin(np.abs(meio - (f["ini"] + f["fim"]) / 2)))])])
    return out


def apresentador(frases, locs):
    """palpite: a voz que mais PASSA A PALAVRA com uma pergunta (a vez de falar termina em "?") e tem as vezes mais
    curtas. Por vez, nao por frase: o convidado tambem faz pergunta retorica no meio da resposta (no "Momento", por
    frase a diferenca era 14% x 12%; por vez, 40% x 17%). {letra, confianca 0..1, por_voz}"""
    por = {}
    vezes = []
    for f, l in zip(frases, locs):
        if vezes and vezes[-1][0] == l: vezes[-1][1].append(f)
        else: vezes.append((l, [f]))
    for l, g in vezes:
        d = por.setdefault(l, {"vezes": 0, "terminam_em_pergunta": 0, "fala_s": 0.0, "frases": 0})
        d["vezes"] += 1; d["frases"] += len(g)
        d["terminam_em_pergunta"] += g[-1]["texto"].rstrip().endswith("?")
        d["fala_s"] += sum(f["fim"] - f["ini"] for f in g)
    if len(por) < 2:
        return {"letra": next(iter(por), None), "confianca": 0.0, "por_voz": por}
    tot = sum(d["fala_s"] for d in por.values()) or 1.0
    for d in por.values():
        d["taxa_pergunta_na_vez"] = round(d["terminam_em_pergunta"] / d["vezes"], 3)
        d["vez_media_s"] = round(d["fala_s"] / d["vezes"], 1); d["parte_da_fala"] = round(d["fala_s"] / tot, 3)
    cand = [l for l, d in por.items() if d["parte_da_fala"] >= 0.05] or list(por)
    nota = {l: por[l]["taxa_pergunta_na_vez"] / max(por[l]["vez_media_s"], 1.0) for l in cand}
    o = sorted(cand, key=lambda l: -nota[l])
    conf = 1.0 if len(o) == 1 else (0.0 if nota[o[0]] == 0 else 1 - nota[o[1]] / nota[o[0]])
    return {"letra": o[0], "confianca": round(max(0.0, conf), 2), "por_voz": por}


def rotula(transc, seg, emb, apresentador_letra=None):
    """transcricao da Fase 2 + vozes -> frases com {locutor, papel} e o palpite do apresentador.
    apresentador_letra: None = o palpite; "A", "B"... = escolhido pela pessoa."""
    frases = transc["frases"]
    lab = agrupa(emb, seg[:, 1] - seg[:, 0]) if len(seg) else np.zeros(0, int)
    locs = locutor_das_frases(frases, seg, lab)
    palpite = apresentador(frases, locs)
    ap = apresentador_letra or palpite["letra"]
    novas = [dict(f, locutor=l, papel="apresentador" if l == ap else "convidado") for f, l in zip(frases, locs)]
    return dict(transc, frases=novas, apresentador=ap, palpite=palpite, vozes=sorted(set(locs)))


def resultado(video, modelo="preciso", apresentador_letra=None, progresso=None, cancelado=None):
    """transcricao com quem fala (le o cache; faz so as janelas de voz que faltam)"""
    t = longo.resultado(video, modelo)
    if t is None:
        raise RuntimeError("A transcrição deste vídeo ainda não terminou.")
    seg, emb = identifica(video, modelo, progresso=progresso, cancelado=cancelado)
    return rotula(t, seg, emb, apresentador_letra)
