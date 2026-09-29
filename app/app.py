"""Ponto de entrada do Clipay.ia (e' este arquivo que vira o .exe / .app).
Abre numa janela propria (pywebview) quando disponivel; senao, no navegador padrao."""
import multiprocessing, sys, threading


def autoteste():
    """confere que tudo que o app precisa veio dentro do executavel (usado no build e em maquina limpa)"""
    import json
    r = {}
    def tenta(nome, fn):
        try: r[nome] = fn() or True
        except Exception as e: r[nome] = f"FALHOU: {e}"
    from clipay import audio, conta, rosto, transcricao, capcut
    tenta("ffmpeg", lambda: audio.ffmpeg_bin())
    tenta("config_supabase", lambda: conta.SUPABASE_URL.startswith("https://") and len(conta.ANON_KEY) > 100)
    tenta("detector_rosto", lambda: rosto._detector(__import__("cv2")) is not None)
    tenta("onnxruntime", lambda: __import__("onnxruntime").__version__)
    tenta("tkinter", lambda: __import__("tkinter.filedialog") is not None)
    tenta("moldes_capcut", lambda: all((capcut.MOLDES / m / "draft_content.json").exists() for m in ("vertical", "horizontal")))
    tenta("pasta_dados", lambda: str(transcricao.pasta_dados()))
    saida = json.dumps(r, ensure_ascii=False, indent=1)
    i = sys.argv.index("--autoteste")
    if len(sys.argv) > i + 1:                       # .exe sem console: a saida vai pra um arquivo
        open(sys.argv[i + 1], "w", encoding="utf-8").write(saida)
    else:
        print(saida)
    sys.exit(0 if all(not str(v).startswith("FALHOU") for v in r.values()) else 1)


def main():
    if "--autoteste" in sys.argv:
        autoteste()
    from clipay import servidor
    porta = servidor.porta_livre()
    url = f"http://127.0.0.1:{porta}/"
    janela = "--navegador" not in sys.argv and "--sem-navegador" not in sys.argv
    if janela:
        try:
            import webview                        # janela nativa: fechar a janela fecha o app
            threading.Thread(target=servidor.inicia, kwargs={"abrir": False, "porta": porta}, daemon=True).start()
            webview.create_window("Clipay.ia", url, width=1280, height=840, min_size=(900, 600))
            webview.start()
            return
        except Exception:
            pass
    servidor.inicia(abrir="--sem-navegador" not in sys.argv, porta=porta)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
