# PyInstaller: gera o app do Clipay.ia (Windows).
# rodar de dentro de app/:  pyinstaller clipay.spec --noconfirm
import sys
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

datas = [("clipay/assets", "clipay/assets"), ("clipay/config_publica.json", "clipay")]
binaries = collect_dynamic_libs("onnxruntime")
binaries += [("bin/ffmpeg.exe", "bin")]
try:
    datas += collect_data_files("webview")
except Exception:
    pass

a = Analysis(["app.py"], pathex=["."], binaries=binaries, datas=datas,
             hiddenimports=["onnxruntime", "webview"], excludes=["matplotlib", "PyQt5", "PySide6"])
pyz = PYZ(a.pure)
# Fase 5 decide onefile vs pasta; por ora pasta (COLLECT) como o CortesApp original.
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Clipay",
          console=False, icon=None)
coll = COLLECT(exe, a.binaries, a.datas, name="Clipay")
