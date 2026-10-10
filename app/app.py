"""Ponto de entrada do Clipay.ia (e' este arquivo que vira o .exe / .app).
Abre numa janela propria (pywebview) quando disponivel; senao, no navegador padrao."""
import multiprocessing, os, sys, threading


def certificados():
    """conexao segura (https: login, download do motor de transcricao) com os certificados que vem DENTRO do app.
    No Mac o Python empacotado procura os certificados num caminho da maquina onde o app foi montado, que nao existe
    no computador do cliente: toda conexao era recusada e parecia "sem internet"."""
    if os.environ.get("SSL_CERT_FILE"):
        return os.environ["SSL_CERT_FILE"]
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
        return os.environ["SSL_CERT_FILE"]
    except Exception:                             # sem o pacote: fica o do sistema (Windows usa o dele)
        return ""


def autoteste():
    """confere que tudo que o app precisa veio dentro do executavel (usado no build e em maquina limpa)"""
    import json
    r = {}
    def tenta(nome, fn):
        try: r[nome] = fn() or True
        except Exception as e: r[nome] = f"FALHOU: {e}"
    from clipay import audio, conta, rosto, transcricao, capcut
    def seguro():                                 # os certificados sao os de dentro do app e a conexao segura funciona
        import ssl, urllib.request
        c = os.environ.get("SSL_CERT_FILE", "")
        base = getattr(sys, "_MEIPASS", "")
        if not (c and os.path.isfile(c) and (not base or os.path.abspath(c).startswith(os.path.abspath(base)))):
            raise RuntimeError(f"certificados fora do app: {c or ssl.get_default_verify_paths()}")
        urllib.request.urlopen(urllib.request.Request(transcricao.CT2_URL.format(nome="small", arq="config.json"), method="HEAD"), timeout=30)
        return c
    tenta("conexao_segura", seguro)
    tenta("ffmpeg", lambda: audio.ffmpeg_bin())
    tenta("config_supabase", lambda: conta.SUPABASE_URL.startswith("https://") and len(conta.ANON_KEY) > 100)
    tenta("detector_rosto", lambda: rosto._detector(__import__("cv2")) is not None)
    tenta("onnxruntime", lambda: __import__("onnxruntime").__version__)
    tenta("motor_rapido", lambda: transcricao.motor_rapido_disponivel() and __import__("ctranslate2").__version__
          or (_ for _ in ()).throw(RuntimeError("faster-whisper/ctranslate2 nao carregou")))
    if transcricao.ct2_pronto("preciso"):           # modelo ja baixado: transcreve 1 s de silencio (DLLs do motor ok)
        tenta("motor_rapido_roda", lambda: transcricao.WhisperRapido("preciso").segmentos(__import__("numpy").zeros(16000)) is not None)
    tenta("tkinter", lambda: __import__("tkinter.filedialog") is not None)
    tenta("moldes_capcut", lambda: all((capcut.MOLDES / m / "draft_content.json").exists() for m in ("vertical", "horizontal")))
    tenta("pasta_dados", lambda: str(transcricao.pasta_dados()))
    tenta("janela_pywebview", lambda: __import__("webview") and True)
    if "--gera" in sys.argv:                        # build: gera projetos de verdade numa pasta do CapCut VAZIA
        tenta("projetos", lambda: gera_teste(sys.argv[sys.argv.index("--gera") + 1]))
    saida = json.dumps(r, ensure_ascii=False, indent=1)
    i = sys.argv.index("--autoteste")
    if len(sys.argv) > i + 1:                       # .exe sem console: a saida vai pra um arquivo
        open(sys.argv[i + 1], "w", encoding="utf-8").write(saida)
    else:
        print(saida)
    sys.exit(0 if all(not str(v).startswith("FALHOU") for v in r.values()) else 1)


def _ouve_soltar(w, servidor):
    """arrastar e soltar: a janela entrega o caminho de verdade do arquivo (pywebviewFullPath), sem copiar o video"""
    try:
        from webview.dom import DOMEventHandler

        def soltou(e):
            fs = ((e or {}).get("dataTransfer") or {}).get("files") or []
            servidor.soltou([f.get("pywebviewFullPath") for f in fs if f.get("pywebviewFullPath")])
        w.dom.document.events.drop += DOMEventHandler(soltou, prevent_default=False, stop_propagation=False)
    except Exception:                             # sem isso, a tela procura o arquivo pelo nome (como no navegador)
        pass


def gera_teste(pasta):
    """como um cliente novo: pasta do CapCut vazia (sem nenhum projeto), videos sinteticos, o motor de transcricao
    baixado na hora (a mesma tela "Preparando" usa isso). Gera React e Cortes + Headline e confere que o projeto
    nao aponta pra nada de outro computador."""
    import subprocess
    from pathlib import Path
    from clipay import audio, capcut, processa, react, transcricao
    p = Path(pasta); raiz = p / "CapCut Usuário" / "com.lveditor.draft"; raiz.mkdir(parents=True, exist_ok=True)
    def video(nome, w, h, d):
        f = p / nome
        tom = f"aevalsrc='sin(2*PI*150*t)*0.5*(lt(t,3)+between(t,4.5,7.5)+gt(t,9))':s=16000:d={d}"
        subprocess.run([audio.ffmpeg_bin(), "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s={w}x{h}:r=30:d={d}",
                        "-f", "lavfi", "-i", tom, "-pix_fmt", "yuv420p", "-c:v", "mpeg4", "-q:v", "5", "-c:a", "aac",
                        "-shortest", str(f)], check=True, capture_output=True, **audio._sem_janela())
        return f
    cima, rv = video("vídeo de cima.mp4", 540, 960, 10), video("react.mp4", 1920, 1080, 30)
    out = {}
    r = react.gera(raiz, [{"video": cima}], rv)
    if r[0].get("erro"): raise RuntimeError("React: " + r[0]["erro"])
    out["react"] = r[0]["projeto"]
    transcricao.prepara("preciso")
    an = processa.analisa_video(raiz, cima)
    out["cortes_headline"] = processa.monta_video(raiz, an)["nome"]
    for nome in out.values():
        for f in ("draft_content.json", "draft_meta_info.json"):
            ruins = capcut.caminhos_de_fora((raiz / nome / f).read_text(encoding="utf-8"))
            if ruins: raise RuntimeError(f"{nome}/{f} aponta pra outro computador: {ruins[:3]}")
    return out


def main():
    certificados()
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
            w = webview.create_window("Clipay.ia", url, width=1280, height=840, min_size=(900, 600))
            servidor.JANELA = w                   # janelas "Escolher arquivo" nativas (Windows e Mac)
            w.events.loaded += lambda: _ouve_soltar(w, servidor)
            webview.start()
            return
        except Exception:
            pass
    servidor.inicia(abrir="--sem-navegador" not in sys.argv, porta=porta)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
