# PyInstaller: gera o Clipay.exe (arquivo unico, Windows).
# rodar de dentro de app/:  pyinstaller clipay.spec --noconfirm
# Precisa de app/bin/ffmpeg.exe (o CI baixa; localmente copie um build LGPL).
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

datas = [("clipay/assets", "clipay/assets"), ("clipay/config_publica.json", "clipay")]
binaries = (collect_dynamic_libs("onnxruntime") + collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("sherpa_onnx")
            + [("bin/ffmpeg.exe", "bin")])                       # sherpa_onnx: impressao de voz (Cortes)
for pacote in ("webview", "cv2", "faster_whisper"):  # cv2: haarcascade do rosto; faster_whisper: assets (VAD)
    try:
        datas += collect_data_files(pacote)
    except Exception:
        pass

a = Analysis(["app.py"], pathex=["."], binaries=binaries, datas=datas,
             hiddenimports=["onnxruntime", "webview", "cv2", "tkinter", "tkinter.filedialog",
                            "faster_whisper", "ctranslate2", "tokenizers", "av", "sherpa_onnx"],
             excludes=["matplotlib", "PyQt5", "PySide6", "pytest"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="Clipay", console=False, icon=None,
          upx=False, runtime_tmpdir=None)
