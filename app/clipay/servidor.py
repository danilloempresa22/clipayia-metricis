"""Servidor local (so 127.0.0.1) que serve a tela do app e roda as edicoes em segundo plano.
Toda chamada /api exige o token da sessao (so quem abriu a tela do app o conhece) e o Host local:
assim nenhuma pagina qualquer da internet consegue mandar o app processar coisas."""
import json, os, secrets, subprocess, threading, uuid, traceback, webbrowser, socket, sys, shutil
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from . import capcut, transcricao, processa, conta, __version__

ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "clipay" / "assets"
if not ASSETS.exists():
    ASSETS = Path(__file__).resolve().parent / "assets"

TOKEN = secrets.token_urlsafe(24)
JOBS = {}
ANALISES = {}                                        # id -> resultado de processa.analisa_video
TRAVA = threading.Lock()
EXT_VIDEO = (".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm")


def pasta_temp():
    p = transcricao.pasta_dados() / "temp"
    p.mkdir(parents=True, exist_ok=True)
    return p


def cfg_path():
    return transcricao.pasta_dados() / "config.json"


def le_cfg():
    try: return json.loads(cfg_path().read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}


def grava_cfg(c):
    cfg_path().write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")


def raiz_atual():
    return capcut.acha_raiz(le_cfg().get("raiz"))


def roda_job(jid, fn):
    """roda fn(avisa) em segundo plano, uma edicao por vez (CPU e root_meta_info do CapCut)"""
    def avisa(etapa, fr):
        JOBS[jid].update({"etapa": etapa, "fracao": round(fr, 3)})
    try:
        with TRAVA:
            JOBS[jid]["etapa"] = "Começando"
            r = fn(avisa)
        JOBS[jid].update({"fim": True, "resultado": r, "fracao": 1.0, "etapa": "Pronto"})
    except (capcut.ErroProjeto, conta.ErroConta) as e:
        JOBS[jid].update({"fim": True, "erro": str(e)})
    except Exception as e:
        traceback.print_exc()
        JOBS[jid].update({"fim": True, "erro": f"Erro inesperado: {e}"})


def novo_job(fn):
    jid = uuid.uuid4().hex[:10]
    JOBS[jid] = {"id": jid, "etapa": "Na fila", "fracao": 0.0, "fim": False}
    threading.Thread(target=roda_job, args=(jid, fn), daemon=True).start()
    return jid


def escolhe_arquivo():
    """janela nativa do Windows pra escolher o video (caminho direto: nao copia arquivo de GBs)"""
    import tkinter as tk
    from tkinter import filedialog
    r = tk.Tk(); r.withdraw(); r.attributes("-topmost", True)
    try:
        return filedialog.askopenfilename(title="Escolha o vídeo bruto", parent=r,
                                          filetypes=[("Vídeos", " ".join("*" + e for e in EXT_VIDEO)), ("Todos", "*.*")])
    finally:
        r.destroy()


def abre_capcut():
    for base in (os.environ.get("LOCALAPPDATA", ""),):
        exe = Path(base) / "CapCut" / "Apps" / "CapCut.exe"
        if exe.exists():
            subprocess.Popen([str(exe)], close_fds=True)
            return True
    return False


def trabalho_analisa(caminho, modelo):
    def fn(avisa):
        conta.exige_ativa()
        raiz = raiz_atual()
        if not raiz:
            raise capcut.ErroProjeto("Não achei a pasta de projetos do CapCut. Informe o caminho nas configurações.")
        an = processa.analisa_video(raiz, caminho, {"transcrever": True, "modelo": modelo}, avisa)
        aid = uuid.uuid4().hex[:10]
        ANALISES[aid] = an
        keep = an["pl"][0]["keep"]
        return {"analise": aid, "nome": an["video"].name, "duracao": an["pl"][0]["dur"],
                "depois": sum(k[1] - k[0] for k in keep), "pedacos": len(keep),
                "frases": [[round(a, 2), round(b, 2), t] for a, b, t in an["frases"].get(0, [])],
                "largura": an["info"]["largura"], "altura": an["info"]["altura"],
                "rosto": an.get("rosto", "centro"), "rosto_confiavel": an.get("rosto_confiavel", False)}
    return fn


def trabalho_gera(c):
    def fn(avisa):
        conta.exige_ativa()
        an = ANALISES.get(c.get("analise"))
        if not an:
            raise capcut.ErroProjeto("Essa análise expirou. Importe o vídeo de novo.")
        raiz = raiz_atual()
        rem = [[float(a), float(b)] for a, b in (c.get("remover") or []) if float(b) > float(a)]
        op = {"headline": (c.get("headline") or "").strip(), "rosto": c.get("rosto", "centro"),
              "remover": rem, "nome": (c.get("nome") or "").strip() or None}
        if op["rosto"] not in ("esquerda", "centro", "direita"):
            op["rosto"] = "centro"
        r = processa.monta_video(raiz, an, op, avisa)
        try:
            conta.registra_processamento()               # so contagem: nenhum video sai da maquina
        except conta.ErroConta:
            traceback.print_exc()                        # falha de contagem nao invalida o projeto ja gravado
        return r
    return fn


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _corpo(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _autorizado(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            self._json({"erro": "host inválido"}, 403); return False
        if not secrets.compare_digest(self.headers.get("X-Clipay-Token", ""), TOKEN):
            self._json({"erro": "não autorizado"}, 403); return False
        return True

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("127.0.0.1", "localhost"):
                self.send_response(403); self.end_headers(); return
            b = (ASSETS / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN).encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if not u.path.startswith("/api/"):
            self.send_response(404); self.end_headers(); return
        if not self._autorizado(): return
        try:
            if u.path == "/api/sessao":
                return self._json(conta.estado())
            if u.path == "/api/estado":
                raiz = raiz_atual()
                return self._json({"versao": __version__, "raiz": str(raiz) if raiz else None,
                                   "modelo": transcricao.modelo_pronto("preciso"), "site": conta.SITE_URL})
            if u.path == "/api/job":
                return self._json(JOBS.get(q.get("id", [""])[0]) or {"erro": "job não existe", "fim": True})
        except conta.ErroConta as e:
            return self._json({"erro": str(e)}, 400)
        self.send_response(404); self.end_headers()

    def do_POST(self):
        u = urlparse(self.path)
        if not self._autorizado(): return
        try:
            if u.path == "/api/enviar":                  # arrastar-e-soltar no navegador: grava em blocos, sem estourar memoria
                nome = Path(parse_qs(u.query).get("nome", ["video"])[0]).name
                if not nome.lower().endswith(EXT_VIDEO):
                    return self._json({"erro": "Formato não suportado. Use MP4, MOV ou MKV."}, 400)
                destino = pasta_temp() / f"{uuid.uuid4().hex[:8]}_{nome}"
                falta = int(self.headers.get("Content-Length", 0) or 0)
                with open(destino, "wb") as f:
                    while falta > 0:
                        b = self.rfile.read(min(1 << 20, falta))
                        if not b: break
                        f.write(b); falta -= len(b)
                return self._json({"caminho": str(destino)})
            c = self._corpo()
            if u.path == "/api/login":
                conta.login(c.get("email", ""), c.get("senha", ""))
                return self._json(conta.estado())
            if u.path == "/api/logout":
                conta.logout(); return self._json({"ok": True})
            if u.path == "/api/raiz":
                p = Path(c.get("raiz", "")).expanduser()
                if not p.is_dir(): return self._json({"erro": "Essa pasta não existe."}, 400)
                cfg = le_cfg(); cfg["raiz"] = str(p); grava_cfg(cfg)
                return self._json({"ok": True})
            if u.path == "/api/escolher-arquivo":
                return self._json({"caminho": escolhe_arquivo() or ""})
            if u.path == "/api/analisar":
                p = Path(c.get("caminho", ""))
                if not p.is_file() or p.suffix.lower() not in EXT_VIDEO:
                    return self._json({"erro": "Arquivo de vídeo não encontrado."}, 400)
                conta.exige_ativa()                       # falha logo, antes de gastar CPU
                return self._json({"id": novo_job(trabalho_analisa(str(p), c.get("modelo", "preciso")))})
            if u.path == "/api/gerar":
                conta.exige_ativa()
                return self._json({"id": novo_job(trabalho_gera(c))})
            if u.path == "/api/abrir-capcut":
                return self._json({"ok": abre_capcut()})
        except conta.ErroConta as e:
            return self._json({"erro": str(e)}, 400)
        except (ValueError, TypeError):
            return self._json({"erro": "pedido inválido"}, 400)
        self.send_response(404); self.end_headers()


def porta_livre(pref=8765):
    for p in range(pref, pref + 50):
        with socket.socket() as s:
            try: s.bind(("127.0.0.1", p)); return p
            except OSError: continue
    return 0


def inicia(abrir=True, porta=None):
    porta = porta or porta_livre()
    srv = ThreadingHTTPServer(("127.0.0.1", porta), H)
    url = f"http://127.0.0.1:{porta}/"
    print(f"Clipay.ia rodando em {url}  (feche esta janela para sair)")
    if abrir:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
