"""Transcricao de video LONGO (Cortes, 1 a 3 horas): frases numeradas com inicio e fim no video inteiro + pausas do audio.
O audio e' lido por janelas de ~10 min (ffmpeg com -ss, direto do arquivo, sem copiar): a memoria nao cresce com a
duracao. A emenda entre janelas cai sempre no meio de uma pausa (>= 250 ms, a mesma regua do corte), escolhida perto
do fim nominal da janela: as janelas nao se sobrepoem na transcricao, entao nenhuma fala sai duas vezes e nenhuma
frase e' partida. Os 2 s de margem dos lados servem so pra medir a energia (piso do audio), nao pra transcrever.
Dentro da janela: os mesmos blocos de ate 25 s de fala de palavras.py, transcritos COM as marcas de tempo do Whisper;
cada segmento do Whisper vira uma frase, com inicio e fim apertados na fala de verdade (limite vem do audio).
Cada janela pronta vai pro cache em disco na hora (pasta de dados do app): fechar ou cancelar e rodar de novo
continua de onde parou, e um video ja pronto responde na hora."""
import hashlib, json, math, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
from . import audio, palavras, transcricao

VERSAO = 1                           # muda quando o metodo mudar (invalida o cache)
JANELA = 600.0                       # s de video por janela (nominal)
BUSCA = 60.0                         # a emenda e' a maior pausa nos ultimos BUSCA s antes do fim nominal
MARGEM = 2.0                         # s lidos a mais dos lados (so pra energia)
PAUSA_MIN = palavras.CORTE_MIN       # 250 ms
FOLGA_FIM = 0.3                      # s de folga depois da fala no fim de um corte
ANTES_FALA = 0.05                    # s antes da primeira palavra no comeco de um corte
PARALELO = 3                         # blocos transcritos ao mesmo tempo (mesmo ganho medido na Rotina)


class Cancelado(Exception):
    pass


# ---------------- cache (uma pasta por video; um arquivo por janela) ----------------
def chave(path, modelo):
    p = Path(path).resolve(); st = p.stat()
    return hashlib.sha1(f"{p}|{st.st_size}|{st.st_mtime_ns}|{modelo}|longo-v{VERSAO}".encode()).hexdigest()


def pasta_cache(path, modelo):
    p = transcricao.pasta_dados() / "cache_longo" / chave(path, modelo); p.mkdir(parents=True, exist_ok=True)
    return p


def _arq_janela(pasta, k):
    return pasta / f"janela_{k:04d}.json"


def le_janela(pasta, k):
    f = _arq_janela(pasta, k)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except (OSError, ValueError):                    # arquivo estragado: refaz so essa janela
        return None


def grava_janela(pasta, k, jan):
    f = _arq_janela(pasta, k); tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(jan, ensure_ascii=False), encoding="utf-8"); tmp.replace(f)


# ---------------- uma janela ----------------
def emenda(trechos, ini, fim_nom):
    """instante da emenda: meio da MAIOR pausa entre falas em [fim_nom - BUSCA, fim_nom] (empate: a mais tarde).
    Sem pausa nenhuma (fala corrida por 1 minuto), o fim nominal."""
    lo = max(ini + 1.0, fim_nom - BUSCA); melhor = None
    bordas = [[lo - 1.0, lo]] + [t for t in trechos if t[1] > lo and t[0] < fim_nom] + [[fim_nom, fim_nom + 1.0]]
    for (_, b0), (a1, _) in zip(bordas, bordas[1:]):
        g0, g1 = max(b0, lo), min(a1, fim_nom)
        if g1 - g0 >= PAUSA_MIN and (melhor is None or g1 - g0 >= melhor[1] - melhor[0]):
            melhor = (g0, g1)
    return fim_nom if melhor is None else round((melhor[0] + melhor[1]) / 2, 3)


def pausas_de(trechos, ini, fim):
    """silencios dentro de [ini, fim] a partir da fala (os da borda entram mesmo curtos: sao limite do mesmo jeito)"""
    out, c = [], ini
    for a, b in trechos:
        if a - c > 1e-3 and (a - c >= PAUSA_MIN or c == ini):
            out.append([round(c, 3), round(a, 3)])
        c = max(c, b)
    if fim - c > 1e-3:
        out.append([round(c, 3), round(fim, 3)])
    return out


def le_janela_audio(video, ini, fim_nom, dur):
    """audio de [ini - MARGEM, fim_nom + MARGEM] e a fala nele, em s do video inteiro"""
    a0 = max(0.0, ini - MARGEM); a1 = min(dur, fim_nom + MARGEM)
    with transcricao.CRONO("ler áudio (ffmpeg)"):
        x = audio.pcm(video, a0, a1 - a0)
    with transcricao.CRONO("achar fala"):
        tr = [[a0 + a, a0 + b] for a, b in palavras.trechos_de_fala(x)] if len(x) and float(np.abs(x).max()) >= 1e-3 else []
    return x, a0, tr


def prepara(video, ini, dur):
    """audio da janela que comeca em ini, a fala nele e onde ela termina (a emenda). Barato de CPU: o tempo e' o
    ffmpeg lendo o arquivo, por isso roda adiantado (a proxima janela e' lida enquanto a atual e' transcrita)."""
    fim_nom = ini + JANELA
    ultima = fim_nom + BUSCA >= dur
    x, a0, tr = le_janela_audio(video, ini, dur if ultima else fim_nom, dur)
    fim = dur if ultima else emenda([t for t in tr if t[1] > ini], ini, fim_nom)
    return {"ini": ini, "x": x, "a0": a0, "tr": tr, "fim": fim}


def transcreve_janela(w, video, ini, dur, cancelado=None, passo=None, paralelo=1, prep=None):
    """{ini, fim, frases: [[ini, fim, texto]], pausas: [[a, b]]} em s do video inteiro. passo(i, n) por bloco.
    prep: o resultado de prepara() ja lido (senao le aqui)."""
    cancelado = cancelado or (lambda: False)
    pr = prep or prepara(video, ini, dur)
    x, a0, tr, fim = pr["x"], pr["a0"], pr["tr"], pr["fim"]
    meus = [[max(a, ini), min(b, fim)] for a, b in tr if min(b, fim) - max(a, ini) >= palavras.FALA_MIN]
    bls = palavras.blocos(meus)
    trava = threading.Lock(); feitos = {"n": 0}

    def um(bl):
        if cancelado(): raise Cancelado()
        a, b = max(ini, bl[0][0] - 0.05), min(fim, bl[-1][1] + 0.05)
        segs = w.segmentos(x[int((a - a0) * audio.SR):int((b - a0) * audio.SR)]) if b > a else []
        out = []
        for s0, s1, txt in segs:
            s0, s1 = a + s0, a + min(s1, b - a)
            if s1 <= s0 or not txt.strip(): continue
            r = palavras.recorta(bl, s0, s1)                  # inicio e fim apertados na fala
            out.append([round(r[0][0], 3), round(r[-1][1], 3), txt.strip()])
        with trava:
            feitos["n"] += 1; k = feitos["n"]
        if passo: passo(k, len(bls))
        return out
    if paralelo > 1 and len(bls) > 1:
        with ThreadPoolExecutor(paralelo) as ex:
            res = list(ex.map(um, bls))
    else:
        res = [um(bl) for bl in bls]
    frases = [f for r in res for f in r]
    return {"ini": round(ini, 3), "fim": round(fim, 3), "frases": frases, "pausas": pausas_de(meus, ini, fim)}


# ---------------- o video inteiro ----------------
def estado_cache(video, modelo="preciso"):
    """{"prontas": k, "total_estimado": n, "segundos_prontos": s, "completo": bool} sem transcrever nada"""
    dur = audio.probe_video(video)["duracao"]; pasta = pasta_cache(video, modelo)
    k, ini = 0, 0.0
    while (j := le_janela(pasta, k)) is not None:
        k += 1; ini = j["fim"]
    return {"prontas": k, "total_estimado": max(k, k + math.ceil(max(0.0, dur - ini - BUSCA) / JANELA)),
            "segundos_prontos": ini, "duracao": dur, "completo": ini >= dur - 1e-3}


def transcreve(video, w=None, modelo="preciso", progresso=None, cancelado=None, paralelo=PARALELO):
    """frases e pausas do video inteiro, janela por janela, retomando do cache. w: o Whisper, ou uma funcao
    w(threads=, paralelo=) que o carrega (so carrega se faltar janela). progresso(dict) a cada bloco:
    janelas prontas, total, fracao, segundos decorridos, estimativa do que falta (s), janelas vindas do cache."""
    cancelado = cancelado or (lambda: False)
    dur = audio.probe_video(video)["duracao"]
    pasta = pasta_cache(video, modelo)
    t0 = time.perf_counter(); janelas = []; ini = 0.0; k = 0; do_cache = 0; feito_agora = 0.0

    def avisa(fr_jan=0.0):
        if not progresso: return
        feito = ini + fr_jan * min(JANELA, dur - ini)
        dec = time.perf_counter() - t0
        rit = dec / feito_agora if feito_agora > 0 else None   # s de relogio por s de video (so o que foi transcrito agora)
        falta = rit * (dur - feito) if rit else None
        total = max(k + 1, k + math.ceil(max(0.0, dur - ini - BUSCA) / JANELA))
        progresso({"janelas_prontas": k, "janelas_total": total, "fracao": round(min(1.0, feito / dur), 4) if dur else 1.0,
                   "decorrido_s": round(dec, 1), "falta_s": round(falta, 1) if falta is not None else None,
                   "do_cache": do_cache, "segundos_video": round(feito, 1), "duracao": round(dur, 1)})
    leitor = ThreadPoolExecutor(1); adiantada = None             # (ini, futuro de prepara) da proxima janela
    try:
        while ini < dur - 1e-3:
            if cancelado(): raise Cancelado()
            j = le_janela(pasta, k)
            if j is None:
                if callable(w) and not hasattr(w, "segmentos"):
                    w = w(threads=max(1, transcricao.nucleos_fisicos() // paralelo), paralelo=paralelo)
                pr = adiantada[1].result() if adiantada and adiantada[0] == ini else prepara(video, ini, dur)
                adiantada = None
                if pr["fim"] < dur - 1e-3 and le_janela(pasta, k + 1) is None:
                    adiantada = (pr["fim"], leitor.submit(prepara, video, pr["fim"], dur))
                j = transcreve_janela(w, video, ini, dur, cancelado, lambda i, n: avisa(i / max(n, 1)), paralelo, pr)
                grava_janela(pasta, k, j)                      # janela pronta vai pro disco na hora
                feito_agora += j["fim"] - j["ini"]
            else:
                do_cache += 1
            janelas.append(j); ini = j["fim"]; k += 1
            avisa()
    finally:
        leitor.shutdown(wait=True, cancel_futures=True)
    return junta(janelas, dur)


def costura(frases, junto=0.05, maximo=30.0):
    """o Whisper as vezes parte uma frase no meio sem pausa ("mas naquele momento voce | ainda nao tinha"): segmento
    sem ponto final colado no seguinte (sem pausa entre eles) vira uma frase so, ate 30 s"""
    out = []
    for a, b, t in frases:
        if out and out[-1][2][-1:] not in ".!?…" and a - out[-1][1] <= junto and b - out[-1][0] <= maximo:
            out[-1] = [out[-1][0], b, out[-1][2] + " " + t]
        else:
            out.append([a, b, t])
    return out


def junta(janelas, dur):
    frases, pausas = [], []
    for j in janelas:
        frases += j["frases"]
        for p in j["pausas"]:
            if pausas and abs(pausas[-1][1] - p[0]) < 1e-3:   # pausa que atravessa a emenda vira uma so
                pausas[-1][1] = p[1]
            else:
                pausas.append(list(p))
    frases.sort(key=lambda f: f[0])
    frases = costura(frases)
    return {"frases": [{"id": i, "ini": a, "fim": b, "texto": t} for i, (a, b, t) in enumerate(frases, 1)],
            "pausas": pausas, "duracao": round(dur, 3), "janelas": [[j["ini"], j["fim"]] for j in janelas]}


def resultado(video, modelo="preciso"):
    """frases e pausas ja prontas no cache (None se ainda falta janela). Para a Fase 3."""
    dur = audio.probe_video(video)["duracao"]; pasta = pasta_cache(video, modelo)
    js, k, ini = [], 0, 0.0
    while (j := le_janela(pasta, k)) is not None:
        js.append(j); ini = j["fim"]; k += 1
    return junta(js, dur) if ini >= dur - 1e-3 else None


# ---------------- limite do corte puxado pro audio ----------------
def ajusta_limite(t, tipo, pausas, perto=0.5, baixa=1.0):
    """instante t (s, comeco ou fim de frase, tempo do Whisper) -> o limite do corte na pausa mais proxima, para
    nunca cortar no meio de palavra. "inicio": logo antes da primeira palavra (fim da pausa - 50 ms). "fim": fim da
    fala + 0,3 s de folga, sem passar da pausa (a proxima palavra nao entra). pausas: as do resultado (cache).
    So vale pausa a ate `perto` s de t (o Whisper erra a borda em ~0,1-0,5 s); sem pausa perto (frase emendada na
    outra sem respiro), fica o tempo do Whisper. Fala baixa que o detector tomou por silencio (o apresentador longe
    do microfone): t cai mais de `baixa` s dentro da pausa, e o limite parte do proprio t (senao comeria a frase)."""
    if tipo not in ("inicio", "fim"):
        raise ValueError("tipo é 'inicio' ou 'fim'")
    if not pausas:
        return round(t, 3)
    i = int(np.searchsorted([p[0] for p in pausas], t, side="right"))
    cand = [pausas[j] for j in (i - 1, i) if 0 <= j < len(pausas)]
    dist = lambda p: 0.0 if p[0] <= t <= p[1] else min(abs(t - p[0]), abs(t - p[1]))
    a, b = min(cand, key=lambda p: (dist(p), -(p[1] - p[0])))
    if dist((a, b)) > perto:
        return round(t, 3)
    if tipo == "inicio":
        if a <= t <= b and b - t > baixa:                     # fala baixa: comeca no t dele
            return round(max(a, t - ANTES_FALA), 3)
        return round(max(a, b - ANTES_FALA), 3)
    if a <= t <= b and t - a > baixa:                         # fala baixa: termina no t dele
        return round(max(t, min(t + FOLGA_FIM, b - ANTES_FALA)), 3)
    return round(min(a + FOLGA_FIM, max(a, b - ANTES_FALA)), 3)
