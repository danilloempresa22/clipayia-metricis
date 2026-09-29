"""Ponto de entrada do Clipay.ia (e' este arquivo que vira o .exe / .app).
Abre numa janela propria (pywebview) quando disponivel; senao, no navegador padrao."""
import multiprocessing, sys, threading


def main():
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
