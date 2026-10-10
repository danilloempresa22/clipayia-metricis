# PyInstaller: gera o Clipay.ia (pasta) no Windows e o Clipay.ia.app no Mac. O CI zipa e publica no Release.
# rodar de dentro de app/:  pyinstaller clipay.spec --noconfirm
# Precisa de app/bin/ffmpeg.exe (Windows) ou app/bin/ffmpeg (Mac): o CI baixa; localmente copie um build.
# Icone: app/icone.png (o PyInstaller converte pra .ico/.icns com o Pillow).
import re, sys
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

WIN, MAC = sys.platform == "win32", sys.platform == "darwin"
VERSAO = re.search(r'"(.+)"', open("clipay/__init__.py", encoding="utf-8").read()).group(1)
NOME = "Clipay.ia"

datas = [("clipay/assets", "clipay/assets"), ("clipay/config_publica.json", "clipay")]
binaries = (collect_dynamic_libs("onnxruntime") + collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("sherpa_onnx")
            + [("bin/ffmpeg.exe" if WIN else "bin/ffmpeg", "bin")])   # sherpa_onnx: impressao de voz (Cortes)
for pacote in ("webview", "cv2", "faster_whisper"):  # cv2: haarcascade do rosto; faster_whisper: assets (VAD)
    try:
        datas += collect_data_files(pacote)
    except Exception:
        pass

a = Analysis(["app.py"], pathex=["."], binaries=binaries, datas=datas,
             hiddenimports=["onnxruntime", "webview", "webview.dom", "cv2", "tkinter", "tkinter.filedialog",
                            "faster_whisper", "ctranslate2", "tokenizers", "av", "sherpa_onnx"],
             excludes=["matplotlib", "PyQt5", "PySide6", "pytest", "PIL"])   # PIL: so converte o icone no build
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NOME, console=False, icon="icone.png", upx=False,
          target_arch="arm64" if MAC else None)
coll = COLLECT(exe, a.binaries, a.datas, name=NOME, upx=False)

if MAC:
    PEDIDO = "O Clipay.ia precisa ler seus vídeos e criar o projeto no CapCut."
    app = BUNDLE(coll, name=NOME + ".app", icon="icone.png", bundle_identifier="ia.clipay.app", version=VERSAO,
                 info_plist={
                     "CFBundleName": NOME, "CFBundleDisplayName": NOME, "CFBundleShortVersionString": VERSAO,
                     "CFBundleVersion": VERSAO, "CFBundleDevelopmentRegion": "pt-BR", "CFBundleLocalizations": ["pt-BR"],
                     "LSMinimumSystemVersion": "12.0", "NSHighResolutionCapable": True,
                     # os pedidos de acesso que o Mac mostra, em portugues
                     "NSDesktopFolderUsageDescription": PEDIDO, "NSDocumentsFolderUsageDescription": PEDIDO,
                     "NSDownloadsFolderUsageDescription": PEDIDO, "NSRemovableVolumesUsageDescription": PEDIDO,
                     "NSNetworkVolumesUsageDescription": PEDIDO,
                 })
