"""Sugere de que lado da tela a pessoa aparece (pro zoom ir pro lado certo). Tudo local, sem custo.
Amostra alguns quadros com o ffmpeg e acha rostos com o detector Haar que ja vem no OpenCV."""
import subprocess
from pathlib import Path
from statistics import median
import numpy as np
from . import audio

AMOSTRAS = 9


def _quadro(video, t, largura=480):
    r = subprocess.run([audio.ffmpeg_bin(), "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={largura}:-2", "-f", "image2pipe", "-c:v", "bmp", "-"],
                       capture_output=True, **audio._sem_janela())
    return r.stdout if r.returncode == 0 and r.stdout else None


def _detector(cv2):
    """O OpenCV no Windows nao abre arquivo em caminho com acento (ex.: 'Área de Trabalho', nome do usuario),
    entao le o XML em Python e entrega pela memoria."""
    xml = (Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml").read_text(encoding="utf-8")
    fs = cv2.FileStorage(xml, cv2.FILE_STORAGE_READ | cv2.FILE_STORAGE_MEMORY)
    det = cv2.CascadeClassifier()
    if not det.read(fs.getFirstTopLevelNode()):
        raise RuntimeError("detector de rosto não carregou")
    return det


def lado_do_rosto(video, duracao):
    """('esquerda'|'centro'|'direita', confiavel). confiavel=False quando nao achou rosto (cai em 'centro')."""
    try:
        import cv2
        det = _detector(cv2)
    except Exception:
        return "centro", False
    xs = []
    for k in range(AMOSTRAS):
        b = _quadro(video, duracao * (k + 1) / (AMOSTRAS + 1))
        if not b:
            continue
        img = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        h, w = img.shape
        faces = det.detectMultiScale(img, scaleFactor=1.1, minNeighbors=6, minSize=(w // 12, w // 12))
        if len(faces):
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])          # o maior rosto do quadro
            xs.append((x + fw / 2) / w)
    if len(xs) < 2:                                                        # 1 achado so pode ser falso positivo
        return "centro", False
    m = median(xs)
    return ("esquerda" if m < 0.40 else "direita" if m > 0.60 else "centro"), True
