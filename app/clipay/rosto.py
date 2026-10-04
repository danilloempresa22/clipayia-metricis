"""Onde a pessoa esta na horizontal (pro zoom ficar sempre centrado nela). Tudo local, sem custo.
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


MIN_ACHADOS = 3                      # rosto em menos quadros que isso pode ser falso positivo
ESPALHO_MAX = 0.20                   # rostos espalhados demais (mais de uma pessoa, falso positivo): nao confia


def posicao_horizontal(video, duracao):
    """(posicao, confiavel). posicao = centro do rosto em relacao ao centro do quadro, de -1 (borda esquerda) a
    1 (borda direita): mediana dos quadros amostrados. Sem rosto ou pouca confianca: (0.0, False) e segue."""
    try:
        import cv2
        det = _detector(cv2)
    except Exception:
        return 0.0, False
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
            xs.append((x + fw / 2) / w * 2 - 1)                          # 0..w -> -1..1
    if len(xs) < MIN_ACHADOS:
        return 0.0, False
    m = median(xs)
    if median(abs(v - m) for v in xs) > ESPALHO_MAX:
        return 0.0, False
    return round(float(m), 4), True
