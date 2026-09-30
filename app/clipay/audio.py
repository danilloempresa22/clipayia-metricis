"""Leitura e analise de audio. So numpy + ffmpeg (binario embutido no app)."""
import os, re, sys, shutil, subprocess
from pathlib import Path
import numpy as np

SR, H, WIN, FPS = 16000, 0.010, 0.032, 30.0


def ffmpeg_bin():
    """ffmpeg embutido no app (PyInstaller) > variavel CLIPAY_FFMPEG > ffmpeg do sistema."""
    env = os.environ.get("CLIPAY_FFMPEG")
    if env and Path(env).exists():
        return env
    nome = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    for c in (base / "bin" / nome, base / nome):
        if c.exists():
            return str(c)
    achado = shutil.which("ffmpeg")
    if achado:
        return achado
    raise RuntimeError("ffmpeg nao encontrado")


def _sem_janela():
    """no Windows, nao abrir janela de terminal a cada chamada do ffmpeg"""
    if sys.platform == "win32":
        return {"creationflags": 0x08000000}
    return {}


def pcm(path, inicio=None, duracao=None):
    """audio mono 16 kHz em float32. inicio/duracao em segundos (opcional)."""
    cmd = [ffmpeg_bin(), "-v", "error"]
    if inicio:
        cmd += ["-ss", f"{inicio:.3f}"]
    cmd += ["-i", str(path)]
    if duracao is not None:
        cmd += ["-t", f"{duracao:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    r = subprocess.run(cmd, capture_output=True, **_sem_janela())
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou em {path}: {r.stderr.decode(errors='ignore')[-300:]}")
    x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    if duracao is not None:                       # garante o tamanho exato (arquivo sem audio / fim curto)
        n = int(round(duracao * SR))
        x = x[:n] if len(x) >= n else np.concatenate([x, np.zeros(n - len(x), np.float32)])
    return x


def quadro_us(t, fps=FPS):
    """segundos -> microssegundos em cima de um quadro exato. O CapCut arredonda a duracao de cada trecho da timeline
    pra quadros inteiros; se o source nao estiver na grade, ele compensa mudando a velocidade (visto: 0,9987)."""
    return int(round(round(t * fps) * 1e6 / fps))


def na_grade(a, b, fps=FPS):
    """intervalo [a, b] em s alargado pra grade de quadros (nunca encolhe a fala)"""
    return float(np.floor(a * fps + 1e-6) / fps), float(np.ceil(b * fps - 1e-6) / fps)


def probe_video(path):
    """largura/altura (ja com a rotacao do celular aplicada), duracao, fps e se tem audio.
    Le a saida de 'ffmpeg -i' — nao depende do ffprobe."""
    r = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", str(path)], capture_output=True, **_sem_janela())
    t = r.stderr.decode("utf-8", errors="ignore")
    d = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", t)
    v = next((l for l in t.splitlines() if "Video:" in l and "Stream" in l), None)
    if not d or not v:
        raise RuntimeError(f"Não consegui ler o vídeo: {path}")
    dur = int(d[1]) * 3600 + int(d[2]) * 60 + float(d[3])
    wh = re.search(r"\b(\d{2,5})x(\d{2,5})\b", v.split("Video:")[1])
    w, h = int(wh[1]), int(wh[2])
    rot = re.search(r"rotation of (-?\d+(?:\.\d+)?) degrees", t)
    if rot and round(abs(float(rot[1]))) % 180 == 90:      # video de celular gravado em pe
        w, h = h, w
    fps = re.search(r"(\d+(?:\.\d+)?) fps", v)
    return {"largura": w, "altura": h, "duracao": dur, "fps": float(fps[1]) if fps else FPS,
            "tem_audio": any("Audio:" in l and "Stream" in l for l in t.splitlines())}


def duracao(path):
    """duracao em s de qualquer midia (musica inclusive, que nao tem trilha de video)"""
    r = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", str(path)], capture_output=True, **_sem_janela())
    t = r.stderr.decode("utf-8", errors="ignore")
    d = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", t)
    if not d or "Audio:" not in t:
        raise RuntimeError(f"Não consegui ler o áudio: {Path(path).name}")
    return int(d[1]) * 3600 + int(d[2]) * 60 + float(d[3])


def capa(path, destino, segundo=0.5):
    """primeiro quadro do video como JPEG (capa do projeto no CapCut)"""
    r = subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-ss", f"{segundo:.2f}", "-i", str(path),
                        "-frames:v", "1", "-vf", "scale=-2:360", str(destino)], capture_output=True, **_sem_janela())
    return r.returncode == 0 and Path(destino).exists()


def analisa(x):
    """energia (dB acima do piso p5) e forca do tom de voz (autocorrelacao 60-300 Hz) a cada 10 ms.
    Em blocos, pra clipe de 40+ min nao estourar a memoria."""
    n, h = int(SR * WIN), int(SR * H)
    if len(x) < n + h:
        x = np.concatenate([x, np.zeros(n + h - len(x), np.float32)])
    m = (len(x) - n) // h + 1
    E, V = [], []
    CH = 20000
    for c0 in range(0, m, CH):
        c1 = min(m, c0 + CH)
        xs = np.ascontiguousarray(x[c0 * h: (c1 - 1) * h + n])
        fr = np.lib.stride_tricks.as_strided(xs, (c1 - c0, n), (xs.strides[0] * h, xs.strides[0])).copy()
        fr -= fr.mean(1, keepdims=True)
        E.append(20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9))
        sp = np.fft.rfft(fr * np.hanning(n), n * 2)
        ac = np.fft.irfft(np.abs(sp) ** 2)[:, :n]
        ac0 = ac[:, :1].copy(); ac0[ac0 <= 0] = 1e-9
        V.append((ac / ac0)[:, int(SR / 300):int(SR / 60)].max(1))
    e = np.concatenate(E); v = np.concatenate(V)
    e -= np.percentile(e, 5)
    return e, v


def runs(mask):
    out, st = [], None
    for j, b in enumerate(list(mask) + [False]):
        if b and st is None: st = j
        elif not b and st is not None: out.append([st, j]); st = None
    return out


def porta_de(e, v):
    cand = (v > 0.42) & (e > 8.0)
    nivel = float(np.median(e[cand])) if cand.any() else 20.0
    return max(8.0, nivel - 16.0)


def nivel_voz(e, v):
    cand = (v > 0.42) & (e > 8.0)
    return float(np.median(e[cand])) if cand.any() else 20.0


def tom_sustentado(e, v, porta):
    tom = (v > 0.42) & (e > porta)
    sust = tom.copy()
    for k in (1, 2): sust[:-k] &= tom[k:]
    return sust


def dil(m, k):
    return np.convolve(m.astype(np.int32), np.ones(2 * k + 1, np.int32), "same") > 0


def mudo(x, min_s=0.5):
    """trechos de silencio digital (clipe sem audio = imagem)"""
    blk = 160; n = len(x) // blk
    z = np.abs(x[:n * blk]).reshape(n, blk).max(1) < 1e-6
    return [[a * blk / SR, b * blk / SR] for a, b in runs(z) if (b - a) * blk / SR >= min_s]


# ---------- intervalos [[a,b],...] em segundos ----------
def uniao(L):
    out = []
    for p in sorted(L):
        a, b = p[0], p[1]
        if out and a <= out[-1][1] + 1e-3: out[-1][1] = max(out[-1][1], b)
        else: out.append([a, b])
    return out


def inter(A, B):
    out = []; i = j = 0
    while i < len(A) and j < len(B):
        a = max(A[i][0], B[j][0]); b = min(A[i][1], B[j][1])
        if b > a: out.append([a, b])
        if A[i][1] < B[j][1]: i += 1
        else: j += 1
    return out


def fora_de(Z, dur):
    out = []; c = 0.0
    for a, b in Z:
        a, b = max(0.0, a), min(dur, b)
        if a > c: out.append([c, a])
        c = max(c, b)
    if c < dur: out.append([c, dur])
    return out


def tira(keep, remover, minimo=0.1):
    """subtrai intervalos; preserva campos extras de cada pedaco (ex.: forca de zoom)"""
    out = [list(p) for p in keep]
    for r0, r1 in remover:
        nv = []
        for p in out:
            a, b = p[0], p[1]
            if b <= r0 or a >= r1: nv.append(p); continue
            if a < r0: nv.append([a, r0] + p[2:])
            if b > r1: nv.append([r1, b] + p[2:])
        out = nv
    return [[round(p[0], 4), round(p[1], 4)] + p[2:] for p in out if p[1] - p[0] > minimo]
