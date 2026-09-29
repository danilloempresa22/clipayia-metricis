"""Fixtures compartilhadas. Nada aqui encosta na pasta real do CapCut: tudo roda em diretorio temporario."""
import shutil, subprocess, sys
from pathlib import Path
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))

from clipay import audio  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _gera_video(destino, largura, altura, com_audio=True):
    """10 s: tom de 150 Hz (parece voz pro detector) em rajadas com silencio no meio."""
    tom = "aevalsrc='sin(2*PI*150*t)*0.5*(lt(t,3)+between(t,4.5,7.5)+gt(t,9))':s=16000:d=10"
    cmd = [audio.ffmpeg_bin(), "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s={largura}x{altura}:r=30:d=10"]
    if com_audio:
        cmd += ["-f", "lavfi", "-i", tom]
    cmd += ["-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast"]
    cmd += (["-c:a", "aac", "-shortest"] if com_audio else ["-an"])
    subprocess.run(cmd + [str(destino)], check=True, capture_output=True)
    return destino


@pytest.fixture(scope="session")
def video_vertical(tmp_path_factory):
    return _gera_video(tmp_path_factory.mktemp("v") / "vertical.mp4", 540, 960)


@pytest.fixture(scope="session")
def video_horizontal(tmp_path_factory):
    return _gera_video(tmp_path_factory.mktemp("v") / "horizontal.mp4", 960, 540)


@pytest.fixture(scope="session")
def video_mudo(tmp_path_factory):
    return _gera_video(tmp_path_factory.mktemp("v") / "sem_audio.mp4", 540, 960, com_audio=False)


@pytest.fixture
def raiz_capcut(tmp_path):
    """pasta de projetos falsa do CapCut, com 1 projeto legivel (o que a sonda precisa)"""
    raiz = tmp_path / "com.lveditor.draft"
    p = raiz / "0918 (1)"
    p.mkdir(parents=True)
    for f in ("draft_content.json", "draft_meta_info.json"):
        shutil.copy(FIXTURES / "vertical_4k" / f, p / f)
    return raiz
