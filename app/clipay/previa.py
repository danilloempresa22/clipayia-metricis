"""Preview de cada corte (tela Cortes, passo Gerar): um video pequeno (270x480, H.264) feito a partir do video
ORIGINAL com a MESMA edicao do projeto do CapCut (cortes.edicao: pedacos do corte seco, enquadramento na pessoa,
zoom de cada pedaco), a velocidade e a headline de exemplo por cima. E' uma aproximacao (sem o efeito de tremor e
fora do motor do CapCut), nao o render do CapCut.
Como desenha sem pesar: o ffmpeg le SO o trecho (-ss antes do -i) ja reduzido a 640 px de largura e entrega um
quadro por vez; aqui cada quadro e' recortado no quadrado do zoom e posto no quadro 9:16; outro ffmpeg codifica.
Nunca ha mais de um quadro na memoria. Cache em <dados do app>/cache_previa (apagar a pasta limpa tudo)."""
import hashlib, json, os, shutil, subprocess, threading
from pathlib import Path
import cv2
import numpy as np
from . import audio, capcut, cortes, transcricao

VERSAO = 1                           # muda quando o desenho do preview mudar (refaz o cache)
LARG, ALT = 270, 480                 # quadro 9:16 do preview (1/4 do 1080x1920 do projeto)
DEC_LARG = 640                       # o ffmpeg ja entrega o original reduzido a essa largura
CURTO_S = 12.0                       # a grade toca so os primeiros ~12 s de cada corte
BITRATE = "260k"
PLACA = True                         # decodifica o original na placa de video (-hwaccel auto); sem placa, o ffmpeg usa a CPU


class SemQuadro(RuntimeError):
    pass


class Cancelado(Exception):
    pass


def pasta():
    p = transcricao.pasta_dados() / "cache_previa"; p.mkdir(parents=True, exist_ok=True)
    return p


def _assinatura_edicao(mod):
    return hashlib.sha1(json.dumps({k: mod[k] for k in ("zoom", "composto", "headline", "canvas_externo", "canvas_interno")},
                                   sort_keys=True).encode()).hexdigest()[:12]


def chave(video, ini, fim, mod, *extra):
    p = Path(video).resolve(); st = p.stat()
    base = f"{p}|{st.st_size}|{st.st_mtime_ns}|{ini:.3f}|{fim:.3f}|v{VERSAO}|{_assinatura_edicao(mod)}|" + "|".join(map(str, extra))
    return hashlib.sha1(base.encode()).hexdigest()


# ---------------- a edicao (a mesma do projeto), guardada pra nao recalcular ----------------
_TRAVAS = {}
_TRAVA = threading.Lock()


def edicao(video, ini, fim, mod=None):
    """cortes.edicao com cache em disco: o preview e o projeto do mesmo corte usam o mesmo resultado"""
    mod = mod or cortes.modelo()
    k = chave(video, ini, fim, mod, "edicao")
    with _TRAVA:
        trava = _TRAVAS.setdefault(k, threading.Lock())
    with trava:
        f = pasta() / f"ed_{k}.json"
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        ed = cortes.edicao(video, ini, fim, mod)
        ed = json.loads(json.dumps(ed))                     # tuplas -> listas (igual ao que volta do cache)
        tmp = f.with_suffix(".tmp"); tmp.write_text(json.dumps(ed), encoding="utf-8"); tmp.replace(f)
        return ed


def duracao_final(ed, velocidade):
    return sum(b - a for a, b, *_ in ed["pcs"]) / velocidade


# ---------------- desenho ----------------
def fonte_headline(mod, cache_capcut=None):
    """a fonte da headline do CapCut (cache desta maquina) copiada pra pasta do cache; senao Arial Negrito"""
    dest = pasta() / "fonte_headline.ttf"
    if dest.exists():
        return dest.name
    achada = cortes.composto.caminho_no_cache(mod["headline"]["fonte_id"], Path(cache_capcut) / "effect") if cache_capcut else ""
    for c in (achada, capcut.fonte_instalada("arialbd.ttf", "Arial Bold.ttf", "arial.ttf", "Arial.ttf")):
        if c and Path(c).is_file() and Path(c).suffix.lower() in (".ttf", ".otf"):
            shutil.copy(c, dest); return dest.name
    return None


def _drawtext(mod, fonte):
    """as duas linhas da headline de exemplo, centradas, na altura da headline do projeto"""
    h = mod["headline"]; linhas = h["texto"].split("\n")
    fx, fy = mod["canvas_externo"]
    cy = ALT / 2 - h["y"] * ALT / 2                       # y do CapCut: + pra cima, em meia altura do quadro
    tam = round(15.5 * h["escala"] / 0.6336584, 1)        # medido no quadro da referencia
    out = []
    for i, t in enumerate(linhas):
        y = cy + (i - (len(linhas) - 1) / 2) * tam * 1.22 - tam / 2
        t = t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019")
        out.append(f"drawtext=text='{t}':fontsize={tam}:fontcolor=white:x=(w-text_w)/2:y={y:.1f}"
                   + (f":fontfile={fonte}" if fonte else "") + ":shadowcolor=black@0.5:shadowx=0:shadowy=1")
    return ",".join(out)


def _mapa(ed, velocidade, limite_s=None):
    """por quadro de saida: (indice do pedaco, tempo no original). Corte seco = pedacos colados; velocidade 1,13x."""
    pcs = [(a, b) for a, b, *_ in ed["pcs"]]
    cum = np.concatenate([[0.0], np.cumsum([b - a for a, b in pcs])])
    total = cum[-1] / velocidade
    if limite_s: total = min(total, limite_s)
    n = int(total * audio.FPS)
    out = []
    for j in range(n):
        u = min(j * velocidade / audio.FPS, cum[-1] - 1e-6)
        k = int(np.searchsorted(cum, u, side="right")) - 1
        out.append((k, pcs[k][0] + (u - cum[k])))
    return out, pcs


def _zoom(z, a, b, t):
    """escala e posicao no instante t do pedaco [a, b] (keyframes lineares do 1o ao ultimo quadro, como no projeto)"""
    f = 0.0 if z[:3] == z[3:] else min(1.0, max(0.0, (t - a) / max(b - a - 1 / audio.FPS, 1e-6)))
    return tuple(z[i] + (z[i + 3] - z[i]) * f for i in range(3))


def render(video, ed, destino, mod=None, velocidade=1.13, limite_s=None, som=False, musica=None, cache_capcut=None,
           cancelado=None, progresso=None):
    """desenha o preview em destino (mp4). limite_s: so o comeco (grade). som: a fala dos mesmos pedacos (+ musica).
    Decodifica na placa de video quando da (metade da CPU, medido: 10 previews 69 s -> 46 s); se a placa nao
    entregar quadro nenhum, refaz na CPU."""
    a = (video, ed, destino, mod, velocidade, limite_s, som, musica, cache_capcut, cancelado, progresso)
    if PLACA:
        try:
            return _render(*a, placa=True)
        except SemQuadro:
            pass
    return _render(*a, placa=False)


def _render(video, ed, destino, mod=None, velocidade=1.13, limite_s=None, som=False, musica=None, cache_capcut=None,
            cancelado=None, progresso=None, placa=False):
    mod = mod or cortes.modelo(); cancelado = cancelado or (lambda: False)
    info = ed["info"]; Ws, Hs = info["largura"], info["altura"]
    W, H = ed["cob"]
    quadros, pcs = _mapa(ed, velocidade, limite_s)
    if not quadros:
        raise RuntimeError("Corte vazio.")
    t0 = max(0.0, pcs[0][0] - 0.05); t1 = max(t for _, t in quadros) + 0.2
    dh = int(round(DEC_LARG * Hs / Ws / 2) * 2); k = DEC_LARG / Ws
    lado = LARG                                           # o composto 1:1 ocupa a largura do 9:16 (escala 1)
    topo = int(round(ALT / 2 - mod["composto"]["y"] * ALT / 2 - lado / 2))   # y do composto: + pra cima
    fonte = fonte_headline(mod, cache_capcut)
    dec = subprocess.Popen([audio.ffmpeg_bin(), "-v", "error"] + (["-hwaccel", "auto"] if placa else []) +
                           ["-threads", "2", "-ss", f"{t0:.3f}", "-i", str(video),
                            "-t", f"{t1 - t0:.3f}", "-an", "-vf", f"fps={audio.FPS},scale={DEC_LARG}:{dh}:flags=fast_bilinear",
                            "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           **audio._sem_janela())
    destino = Path(destino).resolve(); tmp = destino.with_suffix(".parcial.mp4")
    cmd = [audio.ffmpeg_bin(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{LARG}x{ALT}",
           "-r", str(int(audio.FPS)), "-i", "-"]
    filtros = f"[0:v]{_drawtext(mod, fonte)},format=yuv420p[v]"
    mapa = ["-map", "[v]"]
    if som:
        dur = pcs[-1][1] - pcs[0][0]
        cmd += ["-ss", f"{pcs[0][0]:.3f}", "-t", f"{dur + 0.1:.3f}", "-i", str(video)]
        sel = "+".join(f"between(t,{a - pcs[0][0]:.3f},{b - pcs[0][0]:.3f})" for a, b in pcs)
        filtros += f";[1:a]aselect='{sel}',asetpts=N/SR/TB,atempo={velocidade:.4f}[fala]"
        if musica:
            cmd += ["-i", str(musica["path"])]
            filtros += f";[2:a]volume={mod['musica']['volume']}[mus];[fala][mus]amix=inputs=2:duration=first:normalize=0[a]"
        else:
            filtros += ";[fala]anull[a]"
        mapa += ["-map", "[a]", "-c:a", "aac", "-b:a", "96k"]
    cmd += ["-filter_complex", filtros] + mapa + ["-c:v", "libopenh264", "-b:v", BITRATE, "-g", "60",
                                                  "-movflags", "+faststart", "-shortest", str(tmp)]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(pasta()), **audio._sem_janela())
    tam = DEC_LARG * dh * 3; tela = np.zeros((ALT, LARG, 3), np.uint8)
    idx, quadro = -1, None
    try:
        for j, (kp, t) in enumerate(quadros):
            if cancelado(): raise Cancelado()
            alvo = int(round((t - t0) * audio.FPS))
            while idx < alvo:                              # le e descarta ate o quadro desse instante
                b = dec.stdout.read(tam)
                if len(b) < tam: break
                quadro = np.frombuffer(b, np.uint8).reshape(dh, DEC_LARG, 3); idx += 1
            if quadro is None:
                raise (SemQuadro if placa else RuntimeError)("Não consegui ler o vídeo nesse trecho.")
            s, x, y = _zoom(ed["zooms"][kp], *pcs[kp], t)
            L = Ws / (s * W) * k                             # lado do quadrado do composto, em pixels do quadro lido
            cx = (Ws / 2 - x * Ws / (2 * s * W)) * k
            cy = (Hs / 2 + y * Ws / (2 * s * W)) * k
            q = cv2.getRectSubPix(quadro, (max(2, int(round(L))), max(2, int(round(L)))), (cx, cy))
            tela[:] = 0
            tela[topo:topo + lado] = cv2.resize(q, (lado, lado), interpolation=cv2.INTER_AREA)[:max(0, min(lado, ALT - topo))]
            try:
                enc.stdin.write(tela.tobytes())
            except OSError:                                # o codificador parou: a mensagem dele diz por que
                enc.wait(timeout=10)
                raise RuntimeError("O ffmpeg falhou ao gravar a prévia: " + enc.stderr.read().decode(errors="ignore")[-300:])
            if progresso and j % 15 == 0: progresso(j / len(quadros))
        enc.stdin.close()
        if enc.wait(timeout=300) != 0:
            raise RuntimeError("O ffmpeg falhou ao gravar a prévia: " + enc.stderr.read().decode(errors="ignore")[-200:])
        tmp.replace(destino)
    except BaseException:
        for p in (enc, dec):                           # fecha os dois ffmpeg e ESPERA soltarem o arquivo
            try: p.kill(); p.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired): pass
        try:
            tmp.unlink(missing_ok=True)                # a limpeza nunca troca o motivo de verdade (cancelado, erro)
        except OSError:
            pass
        raise
    finally:
        dec.kill(); dec.wait()
    if progresso: progresso(1.0)
    return destino
