"""Transcricao offline (Whisper via onnxruntime). Roda no computador do editor, sem internet
depois de baixar o modelo uma vez, sem custo por uso."""
import base64, os, sys, tarfile, urllib.request, shutil, time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
import numpy as np
from .audio import SR

MODELOS = {
    "preciso": ("small", "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-small.tar.bz2"),
    "rapido": ("base", "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-base.tar.bz2"),
}


def pasta_dados():
    if sys.platform == "win32":
        b = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        b = Path.home() / "Library" / "Application Support"
    else:
        b = Path.home() / ".local" / "share"
    p = b / "Clipay"; p.mkdir(parents=True, exist_ok=True)
    return p


def modelo_pronto(qual="preciso"):
    nome, _ = MODELOS[qual]
    d = pasta_dados() / "modelos" / nome
    return all((d / f"{nome}-{f}").exists() for f in ("encoder.int8.onnx", "decoder.int8.onnx", "tokens.txt"))


def baixa_modelo(qual="preciso", progresso=None):
    """baixa uma vez e guarda so o que usa (int8 + tokens)."""
    nome, url = MODELOS[qual]
    destino = pasta_dados() / "modelos" / nome
    if modelo_pronto(qual): return destino
    destino.mkdir(parents=True, exist_ok=True)
    tmp = destino.parent / f"{nome}.tar.bz2.part"
    with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length", 0)); feito = 0
        while True:
            bloco = r.read(1 << 20)
            if not bloco: break
            f.write(bloco); feito += len(bloco)
            if progresso and total: progresso(feito, total)
    quero = {f"{nome}-encoder.int8.onnx", f"{nome}-decoder.int8.onnx", f"{nome}-tokens.txt"}
    with tarfile.open(tmp, "r:bz2") as t:
        for m in t.getmembers():
            if Path(m.name).name in quero:
                src = t.extractfile(m)
                with open(destino / Path(m.name).name, "wb") as out:
                    shutil.copyfileobj(src, out)
    tmp.unlink()
    return destino


# ---------------- log-mel (igual ao Whisper) ----------------
def _hz_mel(f):
    f = np.asanyarray(f, dtype=float); fsp = 200.0 / 3; lo = 1000.0; lm = lo / fsp; ls = np.log(6.4) / 27.0
    return np.where(f >= lo, lm + np.log(np.maximum(f, 1e-10) / lo) / ls, f / fsp)


def _mel_hz(m):
    m = np.asanyarray(m, dtype=float); fsp = 200.0 / 3; lo = 1000.0; lm = lo / fsp; ls = np.log(6.4) / 27.0
    return np.where(m >= lm, lo * np.exp(ls * (m - lm)), fsp * m)


def _filtros(n_mels=80, n_fft=400):
    ff = np.linspace(0, SR / 2, 1 + n_fft // 2)
    mf = _mel_hz(np.linspace(_hz_mel(0), _hz_mel(SR / 2), n_mels + 2))
    fd = np.diff(mf); rp = mf[:, None] - ff[None, :]
    w = np.zeros((n_mels, len(ff)))
    for i in range(n_mels):
        w[i] = np.maximum(0, np.minimum(-rp[i] / fd[i], rp[i + 2] / fd[i + 1]))
    w *= (2.0 / (mf[2:n_mels + 2] - mf[:n_mels]))[:, None]
    return w.astype(np.float32)


_FB = _filtros()
_WIN = np.hanning(401)[:-1].astype(np.float32)


def logmel(x):
    x = np.pad(x, (200, 200), mode="reflect")
    n = 1 + (len(x) - 400) // 160
    fr = np.lib.stride_tricks.as_strided(x, (n, 400), (x.strides[0] * 160, x.strides[0]))
    spec = (np.abs(np.fft.rfft(fr * _WIN, axis=1)) ** 2)[:-1]
    ls = np.log10(np.maximum(spec @ _FB.T, 1e-10))
    ls = np.maximum(ls, ls.max() - 8.0)
    return ((ls + 4.0) / 4.0).astype(np.float32)


class Cronometro:
    """soma o tempo de cada etapa (s) e quantas vezes ela rodou: crono.t["encoder"], crono.n["encoder"]"""
    def __init__(self):
        self.t, self.n = defaultdict(float), defaultdict(int)

    @contextmanager
    def __call__(self, etapa):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.t[etapa] += time.perf_counter() - t0; self.n[etapa] += 1


CRONO = Cronometro()                 # global do processo: o app e a medicao leem daqui


_NUCLEOS = None


def nucleos_fisicos():
    """nucleos reais do processador. Com hyperthreading o Windows mostra o dobro, e usar os 'virtuais' no Whisper
    deixa tudo ~2x mais lento (medido: 25 s de audio em 71 s com 12 threads x 35 s com 6)."""
    global _NUCLEOS
    if _NUCLEOS is None:
        n = None
        if sys.platform == "win32":
            try:
                import subprocess
                r = subprocess.run(["powershell", "-NoProfile", "-Command",
                                    "(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum"],
                                   capture_output=True, text=True, timeout=10, creationflags=0x08000000)
                n = int(r.stdout.strip() or 0) or None
            except (OSError, ValueError, subprocess.SubprocessError):
                n = None
        _NUCLEOS = max(1, n or (os.cpu_count() or 2) // 2)
    return _NUCLEOS


class Whisper:
    def __init__(self, qual="preciso", threads=None):
        import onnxruntime as ort
        nome, _ = MODELOS[qual]
        d = pasta_dados() / "modelos" / nome
        o = ort.SessionOptions(); o.intra_op_num_threads = threads or nucleos_fisicos()
        o.inter_op_num_threads = 1
        self.enc = ort.InferenceSession(str(d / f"{nome}-encoder.int8.onnx"), o, providers=["CPUExecutionProvider"])
        self.dec = ort.InferenceSession(str(d / f"{nome}-decoder.int8.onnx"), o, providers=["CPUExecutionProvider"])
        m = self.enc.get_modelmeta().custom_metadata_map
        self.L, self.C, self.S = int(m["n_text_layer"]), int(m["n_text_ctx"]), int(m["n_text_state"])
        self.sot, self.eot, self.tr = int(m["sot"]), int(m["eot"]), int(m["translate"])
        self.nots, self.nosp, self.blank = int(m["no_timestamps"]), int(m["no_speech"]), int(m["blank_id"])
        seq = list(map(int, m["sot_sequence"].split(","))); seq.append(self.nots)
        lang = dict(zip(m["all_language_codes"].split(","), map(int, m["all_language_tokens"].split(","))))
        seq[1] = lang["pt"]; self.seq = seq
        self.tok = {}
        for linha in open(d / f"{nome}-tokens.txt", encoding="utf-8"):
            t, i = linha.split(); self.tok[int(i)] = t
        self.nomes = [i.name for i in self.dec.get_inputs()]

    def texto(self, x):
        mel = logmel(x)
        mel = np.pad(mel, ((0, max(0, 3000 - mel.shape[0])), (0, 0)))[:3000]
        ck, cv = self.enc.run(None, {self.enc.get_inputs()[0].name: mel.T[None]})
        kc = np.zeros((self.L, 1, self.C, self.S), np.float32); vc = kc.copy()

        def passo(tk, kc, vc, off):
            lg, kc, vc = self.dec.run(None, dict(zip(self.nomes, [tk, kc, vc, ck, cv, off])))[:3]
            return lg[0, -1], kc, vc
        lg, kc, vc = passo(np.array([self.seq], np.int64), kc, vc, np.zeros(1, np.int64))
        off = np.array([len(self.seq)], np.int64); out = []; primeiro = True
        for _ in range(150):
            for t in (self.nots, self.sot, self.nosp, self.tr): lg[t] = -np.inf
            if primeiro: lg[self.eot] = -np.inf; lg[self.blank] = -np.inf; primeiro = False
            t = int(lg.argmax())
            if t == self.eot: break
            out.append(t)
            if len(out) > 24 and out[-8:] == out[-16:-8]: break      # trava de repeticao
            lg, kc, vc = passo(np.array([[t]], np.int64), kc, vc, off); off = off + 1
        b = b"".join(base64.b64decode(self.tok[t]) for t in out if t in self.tok)
        return b.decode("utf-8", errors="ignore").strip()


    def segmentos(self, x):
        """transcricao COM marcas de tempo do proprio Whisper (resolucao 20 ms): [(ini, fim, texto)] em s do audio x.
        Regras de tempo do Whisper original: comeca com tempo; tempos em pares; tempo nunca volta; se a soma
        das probabilidades de tempo ganha do melhor texto, sai tempo."""
        with CRONO("mel"):
            mel = logmel(x)
            mel = np.pad(mel, ((0, max(0, 3000 - mel.shape[0])), (0, 0)))[:3000]
        with CRONO("encoder"):
            ck, cv = self.enc.run(None, {self.enc.get_inputs()[0].name: mel.T[None]})
        with CRONO("decoder"):
            return self._segmentos_dec(x, ck, cv)

    def _segmentos_dec(self, x, ck, cv):
        kc = np.zeros((self.L, 1, self.C, self.S), np.float32); vc = kc.copy()

        def passo(tk, kc, vc, off):
            lg, kc, vc = self.dec.run(None, dict(zip(self.nomes, [tk, kc, vc, ck, cv, off])))[:3]
            return lg[0, -1].astype(np.float64), kc, vc
        seq = self.seq[:-1]                                  # sem <|notimestamps|>
        tb = self.nots + 1                                   # <|0.00|>
        dur = len(x) / SR
        lim = tb + int(min(30.0, dur + 0.5) / 0.02) + 1
        lg, kc, vc = passo(np.array([seq], np.int64), kc, vc, np.zeros(1, np.int64))
        off = np.array([len(seq)], np.int64); out = []; ult_ts = None
        for _ in range(224):
            lg[[self.nots, self.sot, self.nosp, self.tr]] = -np.inf
            ult = out[-1] if out else None; pen = out[-2] if len(out) > 1 else None
            if ult is None:
                lg[:tb] = -np.inf                            # comeca com tempo
            elif ult >= tb and (pen is None or pen >= tb):
                lg[tb:] = -np.inf                            # par fechado (ou abertura): vem texto
            elif ult >= tb:
                eot = lg[self.eot]; lg[:tb] = -np.inf; lg[self.eot] = eot     # fechou: novo tempo ou fim
            if ult_ts is not None:
                lg[tb:ult_ts] = -np.inf                      # tempo nunca volta
            lg[lim:] = -np.inf
            fin = np.isfinite(lg)
            if fin[tb:].any() and fin[:tb].any():
                p = np.exp(lg - lg[fin].max()); p[~fin] = 0
                if p[tb:].sum() > p[:tb].max():
                    lg[:tb] = -np.inf
            t = int(lg.argmax())
            if t == self.eot: break
            out.append(t)
            if t >= tb: ult_ts = t
            if len(out) > 30 and out[-10:] == out[-20:-10]: break          # trava de repeticao
            lg, kc, vc = passo(np.array([[t]], np.int64), kc, vc, off); off = off + 1
        txt = lambda ks: b"".join(base64.b64decode(self.tok[k]) for k in ks if k in self.tok).decode("utf-8", errors="ignore").strip()
        segs, cur, t0 = [], [], None
        for t in out:
            if t < tb:
                cur.append(t); continue
            if t0 is None:
                t0 = (t - tb) * 0.02
            else:
                if txt(cur): segs.append((t0, (t - tb) * 0.02, txt(cur)))
                cur, t0 = [], None
        if cur and t0 is not None and txt(cur):
            segs.append((t0, dur, txt(cur)))
        return segs


# ---------------- motor rapido: faster-whisper (CTranslate2), gratuito (MIT), offline ----------------
# Medido no PC do usuario (2026-10-02, mesmo modelo small): video de 10,7 min 524 s -> 113 s; 30 takes 239 s -> 101 s;
# ~90% das palavras iguais ao motor ONNX (as diferencas sao de transcricao, sem perda: o ONNX inventava frase
# repetida). O motor ONNX acima fica de reserva: se o rapido nao carregar nesta maquina, o app usa o antigo.
CT2 = {"preciso": "small", "rapido": "base"}
CT2_URL = "https://huggingface.co/Systran/faster-whisper-{nome}/resolve/main/{arq}"
CT2_ARQS = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")


def pasta_ct2(qual):
    return pasta_dados() / "modelos" / f"ct2-{CT2[qual]}"


def ct2_pronto(qual="preciso"):
    d = pasta_ct2(qual)
    return all((d / a).exists() for a in CT2_ARQS)


def baixa_ct2(qual="preciso", progresso=None):
    """baixa uma vez (~460 MB no 'preciso'); arquivo pela metade nunca fica com o nome final"""
    d = pasta_ct2(qual); d.mkdir(parents=True, exist_ok=True)
    tamanhos = {}
    for a in CT2_ARQS:                               # tamanho total pra barra de progresso
        if (d / a).exists(): continue
        req = urllib.request.Request(CT2_URL.format(nome=CT2[qual], arq=a), method="HEAD")
        with urllib.request.urlopen(req) as r:
            tamanhos[a] = int(r.headers.get("Content-Length", 0) or r.headers.get("X-Linked-Size", 0) or 0)
    total = sum(tamanhos.values()) or 1; feito = 0
    for a in tamanhos:
        tmp = d / (a + ".part")
        with urllib.request.urlopen(CT2_URL.format(nome=CT2[qual], arq=a)) as r, open(tmp, "wb") as f:
            while True:
                bloco = r.read(1 << 20)
                if not bloco: break
                f.write(bloco); feito += len(bloco)
                if progresso: progresso(min(feito, total), total)
        tmp.replace(d / a)
    return d


class WhisperRapido:
    """mesma interface do Whisper ONNX (segmentos com marca de tempo do proprio Whisper), configurado igual:
    portugues, greedy (beam 1), sem fallback de temperatura, sem VAD, sem contexto entre chamadas"""
    def __init__(self, qual="preciso", threads=None, paralelo=1):
        from faster_whisper import WhisperModel
        self.m = WhisperModel(str(pasta_ct2(qual)), device="cpu", compute_type="int8",
                              cpu_threads=threads or nucleos_fisicos(), num_workers=max(1, paralelo))

    def segmentos(self, x):
        with CRONO("faster-whisper"):
            segs, _ = self.m.transcribe(np.asarray(x, np.float32), language="pt", beam_size=1, best_of=1,
                                        temperature=0.0, condition_on_previous_text=False, vad_filter=False,
                                        without_timestamps=False, word_timestamps=False)
            return [(float(s.start), float(s.end), s.text.strip()) for s in segs if s.text.strip()]

    def texto(self, x):
        """so o texto (Cortes + Headline: frases da tela de revisao)"""
        return " ".join(t for _, _, t in self.segmentos(x)).strip()


def motor_rapido_disponivel():
    if os.environ.get("CLIPAY_MOTOR") == "onnx":       # forca o motor antigo (testes / diagnostico)
        return False
    try:
        import faster_whisper, ctranslate2  # noqa: F401
        return True
    except Exception:                                # noqa: BLE001 — sem o pacote ou DLL que nao carrega: usa o ONNX
        return False


def pronto(qual="preciso"):
    """o modelo do motor que vai ser usado ja esta baixado?"""
    return ct2_pronto(qual) if motor_rapido_disponivel() else modelo_pronto(qual)


def motor(qual="preciso", threads=None, paralelo=1, avisa=None):
    """o motor de transcricao: o rapido (faster-whisper) se carregar, senao o ONNX. Baixa o modelo na 1a vez.
    avisa(feito, total) durante o download."""
    if motor_rapido_disponivel():
        try:
            if not ct2_pronto(qual):
                baixa_ct2(qual, avisa)
            return WhisperRapido(qual, threads, paralelo)
        except Exception:                            # noqa: BLE001 — qualquer falha do rapido: cai no antigo
            pass
    if not modelo_pronto(qual):
        baixa_modelo(qual, avisa)
    return Whisper(qual, threads=threads) if threads else Whisper(qual)


def frases(w, x, progresso=None, max_s=15.0, min_s=6.0, ao_texto=None):
    """divide o audio em pausas (6-15s) e transcreve cada pedaco -> [[ini, fim, texto]] em s do audio.
    ao_texto(ini, texto): avisa cada trecho assim que sai (so pra mostrar na tela)."""
    h = 160; n = len(x) // h
    if n == 0: return []
    e = 20 * np.log10(np.sqrt((x[:n * h].reshape(n, h) ** 2).mean(1)) + 1e-9)
    es = np.convolve(e, np.ones(10) / 10, "same")
    cortes = [0]
    while n - cortes[-1] > max_s * 100:
        lo, hi = cortes[-1] + int(min_s * 100), cortes[-1] + int(max_s * 100)
        cortes.append(lo + int(np.argmin(es[lo:hi])))
    cortes.append(n)
    out = []
    for i, (a, b) in enumerate(zip(cortes[:-1], cortes[1:])):
        if e[a:b].max() > -45:
            t = w.texto(x[a * h:b * h])
            if t:
                out.append([a / 100, b / 100, t])
                if ao_texto: ao_texto(a / 100, t)
        if progresso: progresso(i + 1, len(cortes) - 1)
    return out


def srt(itens):
    def ts(t):
        ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    return "\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(itens, 1))


def mapeia(frases_por_clipe, pl, palavras_linha=7):
    """frases em s da ORIGEM de cada clipe -> legendas na timeline editada (so o que ficou).
    O tempo de cada palavra e' aproximado (distribuido pelo tempo de fala que sobrou)."""
    out = []; cur = 0.0
    for k, p in enumerate(pl):
        pecas = []
        for piece in p["keep"]:
            a, b = piece[0], piece[1]; pecas.append((a, b, cur)); cur += b - a
        for fa, fb, t in frases_por_clipe.get(k, []):
            trechos = [(cur0 + max(a, fa) - a, cur0 + min(b, fb) - a) for a, b, cur0 in pecas if min(b, fb) - max(a, fa) > 0.05]
            if not trechos: continue
            total = sum(y - x for x, y in trechos)
            pal = t.split(); n = max(1, -(-len(pal) // palavras_linha))
            por = -(-len(pal) // n)
            for j in range(n):
                txt = " ".join(pal[j * por:(j + 1) * por])
                if not txt: continue
                i0, i1 = total * j / n, total * (j + 1) / n
                def pos(q):
                    acc = 0.0
                    for x, y in trechos:
                        if q <= acc + (y - x) + 1e-9: return x + (q - acc)
                        acc += y - x
                    return trechos[-1][1]
                out.append([round(pos(i0), 3), round(pos(i1), 3), txt])
    return out
