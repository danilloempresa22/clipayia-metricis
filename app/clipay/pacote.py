"""Transcricao de VARIOS takes (modo Rotina): cache por arquivo, b-roll e duplicado pulados, progresso e cancelar.
Cada take e' transcrito sozinho com palavras.transcreve (blocos de ate 25 s de fala, mesma qualidade dos outros modos).

Medido em 2026-10-02 (PC do usuario, modelo small, 6 nucleos): o gargalo e' o DECODER (80-93% do tempo; ~115 ms
por token, quase todo em copia de memoria dentro do modelo exportado — ScatterND/Transpose/Split no cache — e
nao muda com mais threads). Juntar a voz de todos os takes num audio unico com janelas cheias de 28 s cortou o
encoder pela metade, mas deixou o total MAIS LENTO (o decoder gera mais tokens por janela cheia: 30 takes 239 s ->
253 s; video de 10,7 min 524 s -> 561 s) e jogou palavras pro take vizinho nas emendas. Por isso nao e' usado.
Cache por (caminho, tamanho, data, modelo): refazer ou reordenar os takes nao transcreve de novo."""
import hashlib, json, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
from . import audio, palavras, transcricao, vlog

VERSAO = 1                           # muda quando o metodo mudar (invalida o cache)
PARALELO = 3                         # takes transcritos ao mesmo tempo (threads do onnxruntime divididas entre eles)


class Cancelado(Exception):
    pass


# ---------------- cache ----------------
def _pasta_cache():
    p = transcricao.pasta_dados() / "cache_transcricao"; p.mkdir(parents=True, exist_ok=True)
    return p


def chave(path, modelo):
    p = Path(path).resolve(); st = p.stat()
    return hashlib.sha1(f"{p}|{st.st_size}|{st.st_mtime_ns}|{modelo}|v{VERSAO}".encode()).hexdigest()


def le_cache(path, modelo):
    f = _pasta_cache() / f"{chave(path, modelo)}.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except (OSError, ValueError):
        return None


def grava_cache(path, modelo, pal):
    f = _pasta_cache() / f"{chave(path, modelo)}.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(pal, ensure_ascii=False), encoding="utf-8"); tmp.replace(f)


def originais(caminhos, audios):
    """{duplicado: original}: mesma duracao (40 ms) e audio correlacionado (> 0,7), o mesmo criterio de
    vlog.duplicados; o original e' o primeiro da lista"""
    out = {}
    for j, c in enumerate(caminhos):
        xj = audios[c]
        for o in caminhos[:j]:
            if o in out: continue
            xi = audios[o]; m = min(len(xi), len(xj))
            if abs(len(xi) - len(xj)) > audio.SR * 0.04 or m <= audio.SR: continue
            if np.std(xi[:m]) > 0 and np.std(xj[:m]) > 0 and np.corrcoef(xi[:m], xj[:m])[0, 1] > 0.7:
                out[c] = o; break
    return out


# ---------------- tudo junto ----------------
def transcreve_takes(w, arquivos, modelo="preciso", usar_cache=True, progresso=None, cancelado=None, audios=None,
                     ao_ler=None, paralelo=PARALELO):
    """arquivos na ordem -> {"palavras": {caminho: [{t,a,b}]}, "duracao": s de audio, "tipos": {caminho: fala|broll|
    duplicado|cache}, "audios": {caminho: x}, "blocos": n}. progresso(feitos, total) por bloco do Whisper;
    cancelado() -> True interrompe (Cancelado). audios: {caminho: x} ja extraidos (nao roda o ffmpeg de novo).
    ao_ler(i, n): andamento da leitura dos arquivos. w pode ser uma funcao w(threads=) que devolve o Whisper (so
    carrega o modelo se houver o que transcrever, ja com as threads divididas pelos takes em paralelo)."""
    crono = transcricao.CRONO
    cancelado = cancelado or (lambda: False)
    caminhos = [str(Path(a)) for a in arquivos]
    res, tipos, dur = {}, {}, 0.0
    audios = dict(audios or {})
    novos = []
    for k, c in enumerate(caminhos):
        if cancelado(): raise Cancelado()
        if c not in audios:
            with crono("extrair áudio (ffmpeg)"):
                try:
                    audios[c] = audio.pcm(c)
                except RuntimeError:                       # arquivo sem trilha de audio: take so de imagem
                    audios[c] = np.zeros(0, np.float32)
        x = audios[c]; dur += len(x) / audio.SR
        if ao_ler: ao_ler(k + 1, len(caminhos))
        if usar_cache:
            with crono("cache"):
                pal = le_cache(c, modelo)
            if pal is not None:
                res[c] = pal; tipos[c] = "cache"; continue
        novos.append(c)
    dup = originais(novos, audios)                         # duplicado -> original (mesmo take importado 2x)
    fila = []
    for c in novos:
        x = audios[c]
        if c in dup:
            tipos[c] = "duplicado"; continue
        with crono("achar fala"):
            broll = len(x) < audio.SR // 2 or float(np.abs(x).max()) < 1e-3 or vlog.eh_broll(x)
            n = 0 if broll else len(palavras.blocos(palavras.trechos_de_fala(x)))
        if not n:
            res[c] = []; tipos[c] = "broll"; continue
        tipos[c] = "fala"; fila.append((c, n))
    total = sum(n for _, n in fila)
    par = max(1, min(paralelo, len(fila)))
    if fila and callable(w) and not hasattr(w, "segmentos"):
        w = w(threads=max(1, transcricao.nucleos_fisicos() // par))
    feitos = {"n": 0}; trava = threading.Lock()

    def um(c):
        def passo(i, _n):
            with trava:
                feitos["n"] += 1; k = feitos["n"]
            if progresso: progresso(k, total)
            if cancelado(): raise Cancelado()          # para entre um bloco e outro
        if cancelado(): raise Cancelado()
        pal = palavras.transcreve(w, audios[c], passo)
        if usar_cache:
            grava_cache(c, modelo, pal)                # so take inteiro vai pro cache
        return c, pal
    # varios takes ao mesmo tempo: o decoder passa ~90% do tempo copiando memoria num nucleo so, entao 3 takes
    # em paralelo (2 threads cada) aproveitam o processador. Medido: 30 takes 239 s -> 189 s, texto identico.
    with ThreadPoolExecutor(par) as ex:
        futs = [ex.submit(um, c) for c, _ in fila]
        erro = None
        for f in futs:
            try:
                c, pal = f.result(); res[c] = pal
            except BaseException as e:                 # noqa: BLE001 — espera os outros pararem e repassa
                erro = erro or e
        if erro:
            raise erro
    for c, orig in dup.items():
        res[c] = [dict(p) for p in res.get(orig, [])]
        if usar_cache:
            grava_cache(c, modelo, res[c])
    return {"palavras": res, "duracao": dur, "tipos": tipos, "audios": audios, "blocos": total}
