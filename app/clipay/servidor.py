"""Servidor local (so 127.0.0.1) que serve a tela do app e roda as edicoes em segundo plano.
Toda chamada /api exige o token da sessao (so quem abriu a tela do app o conhece) e o Host local:
assim nenhuma pagina qualquer da internet consegue mandar o app processar coisas."""
import json, os, re, secrets, subprocess, threading, uuid, traceback, webbrowser, socket, sys, shutil, time
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from . import capcut, transcricao, processa, conta, audio, ipad, rotina, composto, pacote, __version__

ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "clipay" / "assets"
if not ASSETS.exists():
    ASSETS = Path(__file__).resolve().parent / "assets"

TOKEN = secrets.token_urlsafe(24)
GOOGLE_ESTADOS = {}                                  # codigo de uso unico de cada login com Google em andamento -> hora
RETORNO_GOOGLE = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Clipay.ia</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0e0e0e;color:#fbfbfb;
font:15px/1.5 "Segoe UI",system-ui,sans-serif}div{text-align:center;max-width:420px;padding:24px}p{color:#999}</style></head>
<body><div><h2 id="t">Conectando…</h2><p id="s"></p></div><script>
const h = new URLSearchParams(location.hash.slice(1)), q = new URLSearchParams(location.search);
const fim = (t, s) => { document.getElementById("t").textContent = t; document.getElementById("s").textContent = s; };
const erro = h.get("error_description") || q.get("error_description");
if (erro) fim("Não deu certo", erro.replace(/\\+/g, " ") + ". Volte ao Clipay.ia e tente de novo.");
else if (!h.get("access_token")) fim("Não deu certo", "O Google não devolveu o login. Volte ao Clipay.ia e tente de novo.");
else fetch("/api/google-tokens", {method: "POST", headers: {"X-Clipay-Token": "__TOKEN__", "Content-Type": "application/json"},
  body: JSON.stringify({estado: q.get("estado"), access_token: h.get("access_token"), refresh_token: h.get("refresh_token"),
  expires_in: h.get("expires_in")})}).then(r => r.json()).then(d => {
  history.replaceState(null, "", location.pathname);
  d.erro ? fim("Não deu certo", d.erro) : fim("Pronto!", "Você entrou no Clipay.ia. Pode fechar esta aba e voltar ao app.");
}).catch(() => fim("Não deu certo", "O Clipay.ia não respondeu. Ele ainda está aberto?"));
</script></body></html>"""
JOBS = {}
IPAD = {}                                            # sessao do Apresentador + iPad -> {"ipad": {...}, "pessoa": {...}}
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


# ---------------- historico local (so neste computador; alimenta "ultimos projetos" e "silencio removido") ----------------
def historico_path():
    return transcricao.pasta_dados() / "historico.json"


def le_historico():
    try: return json.loads(historico_path().read_text(encoding="utf-8"))
    except (OSError, ValueError): return []


def anota_historico(r):
    h = [{"data": datetime.now(timezone.utc).isoformat(timespec="seconds"), "nome": r["nome"],
          "antes": round(r["antes"], 1), "depois": round(r["depois"], 1), "pedacos": r["pedacos"],
          "zooms": r.get("zooms", 0), "headline": (r.get("headline") or "").replace("\n", " ")}] + le_historico()
    historico_path().write_text(json.dumps(h[:100], ensure_ascii=False, indent=1), encoding="utf-8")


def semanas(datas, n=8):
    """conta de videos nas ultimas n semanas (segunda a domingo), da mais antiga pra mais nova"""
    hoje = datetime.now().astimezone().date()
    seg = hoje - timedelta(days=hoje.weekday())
    inicios = [seg - timedelta(weeks=k) for k in range(n - 1, -1, -1)]
    cont = {i: 0 for i in inicios}
    for d in datas:
        try: dia = datetime.fromisoformat(d.replace("Z", "+00:00")).astimezone().date()
        except ValueError: continue
        ini = dia - timedelta(days=dia.weekday())
        if ini in cont: cont[ini] += 1
    return [{"inicio": i.isoformat(), "videos": cont[i]} for i in inicios]


def painel():
    """numeros do dashboard. Contador e grafico vem do Supabase (todos os computadores da conta);
    sem internet, cai no historico local e avisa."""
    hist = le_historico()
    try:
        datas, fonte = conta.processamentos(), "conta"
    except conta.ErroConta:
        datas, fonte = [x["data"] for x in hist], "local"
    return {"videos": len(datas), "fonte": fonte, "semanas": semanas(datas),
            "silencio_removido": round(sum(max(0.0, x["antes"] - x["depois"]) for x in hist)),
            "recentes": hist[:5]}


def roda_job(jid, fn):
    """roda fn(avisa) em segundo plano, uma edicao por vez (CPU e root_meta_info do CapCut)"""
    def avisa(etapa, fr):
        JOBS[jid].update({"etapa": etapa, "fracao": round(fr, 3)})

    def linha(ini, texto):                       # trecho transcrito, pra tela mostrar enquanto sai (so as ultimas)
        ls = JOBS[jid].setdefault("linhas", []); ls.append([round(float(ini), 2), texto]); del ls[:-12]
    avisa.linha = linha
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


EXT_AUDIO = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")
ESTATICOS = {("/assets/img", ".png"): "image/png",          # (pasta, extensao) -> tipo. Fonte embutida: o app
             ("/assets/fonts", ".woff2"): "font/woff2",     # funciona sem internet (nada de CDN)
             ("/assets", ".css"): "text/css; charset=utf-8",
             ("/assets/previews", ".mp4"): "video/mp4",     # previa de cada modelo na tela de escolher (o usuario entrega)
             ("/assets/previews", ".jpg"): "image/jpeg"}


def escolhe_arquivo(tipo="video"):
    """janela nativa do Windows pra escolher o arquivo (caminho direto: nao copia arquivo de GBs)"""
    import tkinter as tk
    from tkinter import filedialog
    r = tk.Tk(); r.withdraw(); r.attributes("-topmost", True)
    titulo, rot, ext = (("Escolha a música de fundo", "Áudio", EXT_AUDIO) if tipo == "musica"
                        else ("Escolha os takes (pode selecionar vários)", "Vídeos", EXT_VIDEO) if tipo == "videos"
                        else ("Escolha o vídeo bruto", "Vídeos", EXT_VIDEO))
    try:
        if tipo == "videos":                     # rotina: varios takes de uma vez
            return list(filedialog.askopenfilenames(title=titulo, parent=r, filetypes=[(rot, " ".join("*" + e for e in ext)), ("Todos", "*.*")]))
        return filedialog.askopenfilename(title=titulo, parent=r, filetypes=[(rot, " ".join("*" + e for e in ext)), ("Todos", "*.*")])
    finally:
        r.destroy()


def abre_capcut():
    for base in (os.environ.get("LOCALAPPDATA", ""),):
        exe = Path(base) / "CapCut" / "Apps" / "CapCut.exe"
        if exe.exists():
            subprocess.Popen([str(exe)], close_fds=True)
            return True
    return False


RT_BG = {"job": None}                # Rotina: transcricao em segundo plano dos takes escolhidos


def rotina_em_segundo_plano(caminhos, modelo="preciso"):
    """comeca a transcrever os takes assim que o usuario escolhe, enquanto ele organiza. Mudar so a ordem nao refaz
    nada; takes novos entram numa fila depois do trabalho atual (o que ja foi feito vem do cache, pacote.py)."""
    ant = RT_BG["job"]
    if ant and set(ant["caminhos"]) == set(caminhos) and not ant["erro"]:
        return ant
    job = {"caminhos": list(caminhos), "cancelar": threading.Event(), "feitas": 0, "total": 0, "etapa": "Na fila",
           "res": None, "erro": None, "fim": False}

    def roda():
        try:
            if ant and ant.get("thread"):
                ant["thread"].join()
            if job["cancelar"].is_set():
                raise pacote.Cancelado()
            job["res"] = pacote.transcreve_takes(
                lambda threads=None, paralelo=1: processa._whisper(modelo, lambda e, f=None: job.update(etapa=e), 0, 0, threads, paralelo),
                job["caminhos"], modelo,
                ao_ler=lambda k, n: job.update(etapa=f"Lendo o áudio dos takes ({k} de {n})"),
                progresso=lambda k, n: job.update(feitas=k, total=n, etapa=f"Transcrevendo (trecho {k} de {n})"),
                cancelado=job["cancelar"].is_set)
            job["etapa"] = "Transcrição pronta"
        except pacote.Cancelado:
            job["erro"] = "cancelado"; job["etapa"] = "Cancelado"
        except Exception as e:                       # noqa: BLE001 — aparece na tela; a analise refaz sem o segundo plano
            job["erro"] = str(e); job["etapa"] = "Erro na transcrição"
        finally:
            job["fim"] = True
    job["thread"] = threading.Thread(target=roda, daemon=True)
    RT_BG["job"] = job
    job["thread"].start()
    return job


def estado_rotina():
    j = RT_BG["job"]
    if not j:
        return {"ativo": False}
    return {"ativo": True, "etapa": j["etapa"], "feitas": j["feitas"], "total": j["total"], "fim": j["fim"],
            "erro": j["erro"], "takes": len(j["caminhos"])}


def trabalho_analisa(caminho, modelo, modo="cortes"):
    def fn(avisa):
        conta.exige_ativa()
        raiz = raiz_atual()
        if not raiz:
            raise capcut.ErroProjeto("Não achei a pasta de projetos do CapCut. Informe o caminho nas configurações.")
        if modo == "rotina":
            job = RT_BG["job"]; pronto = None
            if job and set(job["caminhos"]) == {str(Path(c)) for c in caminho}:
                while not job["fim"]:                    # aproveita a transcricao que ja comecou em segundo plano
                    fr = job["feitas"] / job["total"] if job["total"] else 0.0
                    avisa(job["etapa"], 0.02 + 0.9 * fr); time.sleep(0.3)
                if job["erro"] == "cancelado":
                    raise capcut.ErroProjeto("Transcrição cancelada.")
                pronto = job["res"]
            cancela = job["cancelar"] if job else threading.Event()
            try:
                an = processa.analisa_rotina(raiz, caminho, {"modelo": modelo}, avisa, cancelado=cancela.is_set, pronto=pronto)
            except pacote.Cancelado:
                raise capcut.ErroProjeto("Transcrição cancelada.")
            aid = uuid.uuid4().hex[:10]
            ANALISES[aid] = an
            cache = capcut.cache_efeitos(raiz)
            return {"analise": aid, "modo": "rotina", "nome": an["video"].name,
                    "duracao": sum(t["info"]["duracao"] for t in an["takes"]),
                    "takes": [{"nome": t["video"].name, "duracao": t["info"]["duracao"], "fala": bool(t["palavras"])} for t in an["takes"]],
                    "trechos": [[t, round(a, 3), round(b, 3)] for t, a, b in an["keep"]],
                    "fontes": [{"chave": k, "nome": f["nome"], "baixada": bool(composto.caminho_no_cache(f["id"], cache))}
                               for k, f in rotina.FONTES_RELOGIO.items()],
                    "padrao": {"fonte": rotina.FONTE_PADRAO, "escala": rotina.ESC_RELOGIO, "salto": rotina.SALTO_PADRAO,
                               "headline_s": rotina.HEADLINE_S, "volume": rotina.VOLUME}}
        if modo == "legenda":
            an = processa.analisa_legenda(raiz, caminho, {"modelo": modelo}, avisa)
            aid = uuid.uuid4().hex[:10]
            ANALISES[aid] = an
            return {"analise": aid, "modo": "legenda", "nome": an["video"].name, "duracao": an["info"]["duracao"],
                    "depois": sum(b - a for a, b in an["keep"]), "pedacos": len(an["keep"]),
                    "palavras": [[round(p["a"], 2), round(p["b"], 2), p["t"]] for p in an["mantidas"]],
                    "largura": an["info"]["largura"], "altura": an["info"]["altura"]}
        an = processa.analisa_video(raiz, caminho, {"transcrever": True, "modelo": modelo}, avisa)
        aid = uuid.uuid4().hex[:10]
        ANALISES[aid] = an
        keep = an["pl"][0]["keep"]
        return {"analise": aid, "nome": an["video"].name, "duracao": an["pl"][0]["dur"],
                "depois": sum(k[1] - k[0] for k in keep), "pedacos": len(keep),
                "frases": [[round(a, 2), round(b, 2), t] for a, b, t in an["frases"].get(0, [])],
                "largura": an["info"]["largura"], "altura": an["info"]["altura"]}
    return fn


def trabalho_gera(c):
    def fn(avisa):
        conta.exige_ativa()
        an = ANALISES.get(c.get("analise"))
        if not an:
            raise capcut.ErroProjeto("Essa análise expirou. Importe o vídeo de novo.")
        raiz = raiz_atual()
        if an.get("modo") == "rotina":
            def num(v, lo, hi, pad):
                return min(hi, max(lo, float(v))) if v not in (None, "") else pad
            durs = [t["info"]["duracao"] for t in an["takes"]]
            trechos = []
            for tk, a, b in (c.get("trechos") or []):
                tk = int(tk)
                if not 0 <= tk < len(durs):
                    raise capcut.ErroProjeto("Um trecho aponta para um vídeo que não está na lista.")
                trechos.append([tk, num(a, 0, durs[tk], 0), num(b, 0, durs[tk], 0)])
            trechos.sort()
            if any(b - a < 0.1 for _, a, b in trechos) or any(p[0] == q[0] and q[1] < p[2] - 1e-3 for p, q in zip(trechos, trechos[1:])):
                raise capcut.ErroProjeto("Há trechos com fim antes do início ou um em cima do outro. Ajuste na tela de cortes.")
            musica = (c.get("musica") or "").strip()
            if musica and (not Path(musica).is_file() or Path(musica).suffix.lower() not in EXT_AUDIO):
                raise capcut.ErroProjeto("Não achei o arquivo da música. Escolha de novo.")
            vol = c.get("volume") or {}
            op = {"trechos": trechos, "inicio": str(c.get("inicio") or "07:30"),
                  "saltos": [int(num(s, 1, rotina.SALTO_MAX, rotina.SALTO_PADRAO)) for s in (c.get("saltos") or [])],
                  "headline": (c.get("headline") or "").strip()[:120], "headline_s": num(c.get("headline_s"), 1, 60, rotina.HEADLINE_S),
                  "headline_ini": num(c.get("headline_ini"), 0, 1e5, 0.0),
                  "fonte": c.get("fonte") if c.get("fonte") in rotina.FONTES_RELOGIO else rotina.FONTE_PADRAO,
                  "escala": num(c.get("escala"), 0.2, 1.5, rotina.ESC_RELOGIO), "musica": musica or None,
                  "volume": {"silencio": num(vol.get("silencio"), 0, 2, 1.0), "fala": num(vol.get("fala"), 0, 2, 0.21),
                             "rampa": num(vol.get("rampa"), 0.4, 0.8, 0.5)},
                  "nome": (c.get("nome") or "").strip() or None}
            r = processa.monta_rotina(raiz, an, op, avisa)
            _conta_uso(r)
            return r
        if "janela" in an:                               # Apresentador + iPad
            def num(v, lo, hi, pad):
                return min(hi, max(lo, float(v))) if v not in (None, "") else pad
            pes = c.get("pessoa") or {}
            crop = [num(v, 0.0, 1.0, 0.0) for v in (c.get("crop_ipad") or [0, 0, 1, 1])][:4]
            if len(crop) != 4 or crop[2] - crop[0] < 0.05 or crop[3] - crop[1] < 0.05:
                raise capcut.ErroProjeto("O recorte do iPad ficou pequeno demais. Ajuste na tela de enquadrar.")
            musica = (c.get("musica") or "").strip()
            if musica and (not Path(musica).is_file() or Path(musica).suffix.lower() not in EXT_AUDIO):
                raise capcut.ErroProjeto("Não achei o arquivo da música. Escolha de novo.")
            op = {"legenda": False,                               # legenda desligada a pedido do usuario
                  "velocidade": bool(c.get("velocidade")), "musica": musica or None, "headline": (c.get("headline") or "").strip()[:120],
                  "headline_s": num(c.get("headline_s"), 1, 60, ipad.HEADLINE_S),
                  "cortes": c.get("cortes") if c.get("cortes") in ipad.CORTES else "seco",
                  "zoom": bool(c.get("zoom", True)), "intensidade": num(c.get("intensidade"), 0.2, 2.0, 1.0),
                  "pessoa": {"escala": num(pes.get("escala"), 0.5, 4.0, 1.0), "x": num(pes.get("x"), -3, 3, 0.0),
                             "y": num(pes.get("y"), -3, 3, 0.0)},
                  "crop_ipad": crop, "nome": (c.get("nome") or "").strip() or None}
            r = processa.monta_ipad(raiz, an, op, avisa)
            _conta_uso(r)
            return r
        if "mantidas" in an:                             # Legenda Complexa
            num = lambda k, lo, hi, pad: min(hi, max(lo, float(c[k]))) if c.get(k) not in (None, "") else pad
            musica = (c.get("musica") or "").strip()
            if musica and (not Path(musica).is_file() or Path(musica).suffix.lower() not in EXT_AUDIO):
                raise capcut.ErroProjeto("Não achei o arquivo da música. Escolha de novo.")
            op = {"texto": c.get("texto") or "", "inicio": num("inicio", 0, 1e6, None),
                  "zoom": num("zoom", 1.0, 1.6, None), "velocidade": num("velocidade", 1.0, 2.0, 1.15),
                  "musica": musica or None, "volume": num("volume", 0.0, 1.0, 0.068),
                  "nome": (c.get("nome") or "").strip() or None}
            r = processa.monta_legenda(raiz, an, op, avisa)
            _conta_uso(r)
            return r
        op = {"headline": (c.get("headline") or "").strip(), "nome": (c.get("nome") or "").strip() or None}
        r = processa.monta_video(raiz, an, op, avisa)
        _conta_uso(r)
        return r
    return fn


def previa_de(video, com_audio, avisa):
    """previa leve em cache: o mesmo arquivo (caminho + tamanho + data) nao e' convertido de novo"""
    import hashlib
    st = Path(video).stat()
    chave = hashlib.sha1(f"{Path(video).resolve()}|{st.st_size}|{st.st_mtime_ns}|{com_audio}".encode()).hexdigest()[:16]
    pasta = pasta_temp() / "previas"
    pasta.mkdir(parents=True, exist_ok=True)
    info = audio.probe_video(video)
    return ipad.gera_previa(video, pasta / f"{chave}.mp4", com_audio=com_audio, avisa=avisa, dur=info["duracao"]), info


def resumo_ipad(sid, invertido=False):
    ses = IPAD[sid]

    def r(q):
        return {"nome": Path(ses[q]["video"]).name, "largura": ses[q]["info"]["largura"],
                "altura": ses[q]["info"]["altura"], "duracao": ses[q]["info"]["duracao"]}
    return {"sessao": sid, "ipad": r("ipad"), "pessoa": r("pessoa"), "quadro": ipad.QUADRO,
            "proporcao_ipad": ipad.PROPORCAO_IPAD, "invertido": invertido}


def trabalho_prepara_ipad(v_ipad, v_pessoa):
    def fn(avisa):
        conta.exige_ativa()
        out = {}
        passos = (("ipad", v_ipad, "do iPad"), ("pessoa", v_pessoa, "da câmera"))
        for i, (qual, video, rot) in enumerate(passos):
            aviso = lambda f, i=i, rot=rot: avisa(f"Preparando a prévia {rot}", 0.02 + 0.47 * (i + f))
            try:
                previa, info = previa_de(video, True, aviso)       # as duas com audio: da pra inverter sem refazer
            except RuntimeError as e:
                raise capcut.ErroProjeto(str(e))
            out[qual] = {"video": video, "info": info, "previa": str(previa)}
        avisa("Conferindo qual vídeo tem a fala", 0.96)
        for q in out:
            out[q]["voz"] = ipad.fracao_de_voz(out[q]["video"], out[q]["info"])
        invertido = out["pessoa"]["voz"] < ipad.VOZ_MIN <= out["ipad"]["voz"]
        if invertido:                                             # escolhidos trocados: a camera e' a que tem fala
            out["ipad"], out["pessoa"] = out["pessoa"], out["ipad"]
        if out["pessoa"]["voz"] < ipad.VOZ_MIN:
            raise capcut.ErroProjeto("Não encontrei fala em nenhum dos dois vídeos. O vídeo da câmera precisa ter a voz da pessoa.")
        sid = uuid.uuid4().hex[:10]
        IPAD[sid] = out
        transcreve_em_segundo_plano(sid)
        return resumo_ipad(sid, invertido)
    return fn


def transcreve_em_segundo_plano(sid):
    """comeca a legenda enquanto o usuario enquadra e sincroniza (a parte que mais demora deixa de ser espera)"""
    ses = IPAD[sid]
    ses["legenda"] = {"fracao": 0.0, "pronto": False, "erro": None, "palavras": None, "video": ses["pessoa"]["video"]}
    est = ses["legenda"]

    def roda():
        try:
            est["palavras"] = processa.transcreve_pessoa(est["video"], lambda e, f: est.update(fracao=round(f, 3)))
        except Exception as e:                                   # a analise tenta de novo do jeito normal
            traceback.print_exc(); est["erro"] = str(e)
        est["pronto"] = True
    threading.Thread(target=roda, daemon=True).start()


def trabalho_analisa_ipad(sid, offset):
    def fn(avisa):
        conta.exige_ativa()
        ses = IPAD.get(sid)
        if not ses:
            raise capcut.ErroProjeto("Essa sessão expirou. Escolha os vídeos de novo.")
        raiz = raiz_atual()
        if not raiz:
            raise capcut.ErroProjeto("Não achei a pasta de projetos do CapCut. Informe o caminho nas configurações.")
        est = ses.get("legenda")
        if est and est["video"] != ses["pessoa"]["video"]:          # videos invertidos depois: a transcricao era do outro
            transcreve_em_segundo_plano(sid); est = ses["legenda"]
        while est and not est["pronto"]:                          # termina a legenda que ja estava sendo feita
            avisa("Terminando a transcrição da fala (protege as palavras nos cortes)", 0.1 + 0.85 * est["fracao"])
            time.sleep(0.5)
        pal = est["palavras"] if est and not est["erro"] else None
        an = processa.analisa_ipad(raiz, ses, offset, {}, avisa, palavras_prontas=pal)
        aid = uuid.uuid4().hex[:10]
        ANALISES[aid] = an
        return {"analise": aid, "modo": "ipad", "offset": an["offset"], "antes": an["janela"][2],
                "cortes": {k: {"depois": round(sum(b - a for a, b, *_ in kp), 1), "trechos": len(kp)} for k, kp in an["keeps"].items()}}
    return fn


def _conta_uso(r):
    try:
        anota_historico(r)
    except OSError:
        traceback.print_exc()
    try:
        conta.registra_processamento()                   # so contagem: nenhum video sai da maquina
    except conta.ErroConta:
        traceback.print_exc()                            # falha de contagem nao invalida o projeto ja gravado


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

    def _protegido(self, fn):
        """qualquer erro inesperado vira resposta JSON (com o motivo), nunca conexao derrubada:
        pro usuario, conexao derrubada aparece como 'Failed to fetch' e nao diz nada"""
        try:
            fn()
        except (BrokenPipeError, ConnectionResetError):
            pass                                          # o navegador desistiu da conexao
        except Exception as e:
            traceback.print_exc()
            try: self._json({"erro": f"Erro inesperado no app: {e}"}, 500)
            except OSError: pass

    def do_GET(self):
        self._protegido(self._get)

    def do_POST(self):
        self._protegido(self._post)

    def _get(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("127.0.0.1", "localhost"):
                self.send_response(403); self.end_headers(); return
            b = (ASSETS / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN).encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if u.path.startswith("/assets/"):                # estaticos: so estes tipos, cada um na sua pasta (sem subir pasta)
            pasta, nome = Path(u.path).parent.as_posix(), Path(u.path).name
            tipo = ESTATICOS.get((pasta, Path(nome).suffix.lower()))
            p = ASSETS / pasta.removeprefix("/assets").strip("/") / nome
            if tipo and p.is_file():
                b = p.read_bytes()
                self.send_response(200); self.send_header("Content-Type", tipo)
                self.send_header("Cache-Control", "max-age=3600")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
            self.send_response(404); self.end_headers(); return
        if u.path == "/auth/retorno":                    # volta do login com Google (aberto no navegador padrao)
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("127.0.0.1", "localhost"):
                self.send_response(403); self.end_headers(); return
            b = RETORNO_GOOGLE.replace("__TOKEN__", TOKEN).encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if not u.path.startswith("/api/"):
            self.send_response(404); self.end_headers(); return
        if u.path == "/api/video":                       # previa da revisao: <video> nao manda cabecalho, token vai na URL
            return self._video(q)
        if not self._autorizado(): return
        try:
            if u.path == "/api/sessao":
                return self._json(conta.estado())
            if u.path == "/api/painel":
                return self._json(painel())
            if u.path == "/api/estado":
                raiz = raiz_atual()
                return self._json({"versao": __version__, "raiz": str(raiz) if raiz else None,
                                   "modelo": transcricao.pronto("preciso"), "site": conta.SITE_URL, "google": conta.google_disponivel()})
            if u.path == "/api/rotina/estado":
                return self._json(estado_rotina())
            if u.path == "/api/ipad/legenda":             # andamento da transcricao em segundo plano
                ses = IPAD.get(q.get("sessao", [""])[0]) or {}
                est = ses.get("legenda") or {}
                return self._json({"fracao": est.get("fracao", 0), "pronto": bool(est.get("pronto")), "erro": est.get("erro")})
            if u.path == "/api/job":
                return self._json(JOBS.get(q.get("id", [""])[0]) or {"erro": "job não existe", "fim": True})
        except conta.ErroConta as e:
            return self._json({"erro": str(e)}, 400)
        self.send_response(404); self.end_headers()

    def _video(self, q):
        """so o video de uma analise (ou a previa leve de uma sessao do iPad), so com o token; com Range
        (o <video> precisa pra arrastar e pular no tempo)"""
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost") or not secrets.compare_digest(q.get("t", [""])[0], TOKEN):
            self.send_response(403); self.end_headers(); return
        an = ANALISES.get(q.get("analise", [""])[0])
        ses = IPAD.get(q.get("sessao", [""])[0])
        qual = q.get("q", [""])[0]
        if an and an.get("video"):
            p = Path(an["video"])
        elif ses and qual in ("ipad", "pessoa"):
            p = Path(ses[qual]["previa"])
        else:
            self.send_response(403); self.end_headers(); return
        tam = p.stat().st_size
        a, b = 0, tam - 1
        rg = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if rg:
            if rg[1]: a = int(rg[1])
            if rg[2]: b = min(int(rg[2]), tam - 1)
            elif not rg[1]: a = max(0, tam - int(rg[2] or 0))
            b = min(b, a + (8 << 20) - 1)                # blocos de ate 8 MB
        self.send_response(206 if rg else 200)
        self.send_header("Content-Type", "video/quicktime" if p.suffix.lower() == ".mov" else "video/mp4")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(b - a + 1))
        if rg: self.send_header("Content-Range", f"bytes {a}-{b}/{tam}")
        self.end_headers()
        with open(p, "rb") as f:
            f.seek(a); falta = b - a + 1
            while falta > 0:
                bl = f.read(min(1 << 20, falta))
                if not bl: break
                self.wfile.write(bl); falta -= len(bl)

    def _post(self):
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
            if u.path == "/api/abrir-site":              # navegador padrao (a janela do app nao abre abas)
                caminho = c.get("caminho", "/")
                if caminho not in ("/", "/cadastro", "/conta", "/entrar"):
                    return self._json({"erro": "pedido inválido"}, 400)
                webbrowser.open(conta.SITE_URL + caminho)
                return self._json({"ok": True})
            if u.path == "/api/recuperar":
                conta.recupera_senha(c.get("email", ""))
                return self._json({"ok": True})
            if u.path == "/api/google":
                estado = secrets.token_urlsafe(16)
                GOOGLE_ESTADOS[estado] = time.time()
                volta = f"http://127.0.0.1:{self.server.server_address[1]}/auth/retorno?estado={estado}"
                webbrowser.open(conta.url_google(volta))
                return self._json({"ok": True})
            if u.path == "/api/google-tokens":
                t0 = GOOGLE_ESTADOS.pop(c.get("estado", ""), None)       # uso unico: evita login forjado por outra pagina
                if t0 is None or time.time() - t0 > 600:
                    return self._json({"erro": "Esse link de login expirou. Tente de novo pelo Clipay.ia."}, 400)
                conta.entra_com_tokens(c.get("access_token", ""), c.get("refresh_token", ""), int(c.get("expires_in") or 3600))
                return self._json(conta.estado())
            if u.path == "/api/logout":
                conta.logout(); return self._json({"ok": True})
            if u.path == "/api/raiz":
                p = Path(c.get("raiz", "")).expanduser()
                if not p.is_dir(): return self._json({"erro": "Essa pasta não existe."}, 400)
                cfg = le_cfg(); cfg["raiz"] = str(p); grava_cfg(cfg)
                return self._json({"ok": True})
            if u.path == "/api/arquivo-info":            # cartao do arquivo escolhido: nome, tamanho e duracao (so leitura)
                p = Path(c.get("caminho", ""))
                if not p.is_file() or p.suffix.lower() not in EXT_VIDEO:
                    return self._json({"erro": "Arquivo de vídeo não encontrado."}, 400)
                try:
                    dur = audio.probe_video(p)["duracao"]
                except RuntimeError:
                    dur = None
                return self._json({"nome": p.name, "tamanho": p.stat().st_size, "duracao": dur})
            if u.path == "/api/escolher-arquivo":
                return self._json({"caminho": escolhe_arquivo(c.get("tipo", "video")) or ""})
            if u.path == "/api/ipad/preparar":
                vs = {}
                for q, rot in (("ipad", "do iPad"), ("pessoa", "da pessoa")):
                    p = Path(c.get(q, ""))
                    if not p.is_file() or p.suffix.lower() not in EXT_VIDEO:
                        return self._json({"erro": f"Escolha o vídeo {rot}."}, 400)
                    vs[q] = str(p)
                if Path(vs["ipad"]).resolve() == Path(vs["pessoa"]).resolve():
                    return self._json({"erro": "Os dois vídeos são o mesmo arquivo."}, 400)
                conta.exige_ativa()
                return self._json({"id": novo_job(trabalho_prepara_ipad(vs["ipad"], vs["pessoa"]))})
            if u.path == "/api/ipad/trocar":                # botao "Inverter os videos" na tela de enquadrar
                ses = IPAD.get(c.get("sessao", ""))
                if not ses:
                    return self._json({"erro": "Essa sessão expirou. Escolha os vídeos de novo."}, 400)
                if ses["ipad"].get("voz", 0) < ipad.VOZ_MIN:
                    return self._json({"erro": "O outro vídeo não tem fala, então ele não pode ser o da câmera."}, 400)
                ses["ipad"], ses["pessoa"] = ses["pessoa"], ses["ipad"]
                transcreve_em_segundo_plano(c["sessao"])              # a legenda agora e' do outro video
                return self._json(resumo_ipad(c["sessao"]))
            if u.path == "/api/ipad/analisar":
                conta.exige_ativa()
                return self._json({"id": novo_job(trabalho_analisa_ipad(c.get("sessao", ""), float(c.get("offset", 0))))})
            if u.path == "/api/analisar" and c.get("modo") == "rotina":     # varios takes, em ordem
                ps = [Path(x) for x in (c.get("caminhos") or [])]
                if not ps or any(not p.is_file() or p.suffix.lower() not in EXT_VIDEO for p in ps):
                    return self._json({"erro": "Algum vídeo da lista não foi encontrado. Escolha de novo."}, 400)
                conta.exige_ativa()
                rotina_em_segundo_plano([str(p) for p in ps], c.get("modelo", "preciso"))   # ja rodando: reaproveita
                return self._json({"id": novo_job(trabalho_analisa([str(p) for p in ps], c.get("modelo", "preciso"), "rotina"))})
            if u.path == "/api/analisar":
                p = Path(c.get("caminho", ""))
                if not p.is_file() or p.suffix.lower() not in EXT_VIDEO:
                    return self._json({"erro": "Arquivo de vídeo não encontrado."}, 400)
                modo = c.get("modo", "cortes") if c.get("modo") in ("cortes", "legenda", "rotina") else "cortes"
                conta.exige_ativa()                       # falha logo, antes de gastar CPU
                return self._json({"id": novo_job(trabalho_analisa(str(p), c.get("modelo", "preciso"), modo))})
            if u.path == "/api/rotina/transcrever":      # takes escolhidos: comeca a transcrever ja, em segundo plano
                ps = [Path(x) for x in (c.get("caminhos") or [])]
                if not ps or any(not p.is_file() or p.suffix.lower() not in EXT_VIDEO for p in ps):
                    return self._json({"erro": "Algum vídeo da lista não foi encontrado."}, 400)
                conta.exige_ativa()
                rotina_em_segundo_plano([str(p) for p in ps], c.get("modelo", "preciso"))
                return self._json(estado_rotina())
            if u.path == "/api/rotina/cancelar":
                j = RT_BG["job"]
                if j: j["cancelar"].set()
                return self._json(estado_rotina())
            if u.path == "/api/rotina/cortes":            # controles "silencio minimo" e "duracao minima": refaz a lista
                an = ANALISES.get(c.get("analise"))
                if not an or an.get("modo") != "rotina":
                    return self._json({"erro": "Essa análise expirou. Importe o vídeo de novo."}, 400)
                sil = min(2000, max(50, float(c.get("silencio_ms", 250))))
                mn = min(10.0, max(0.0, float(c.get("minimo_s", 0))))
                keep = rotina.cortes_takes(an["takes"], sil, mn)
                return self._json({"trechos": [[t, round(a, 3), round(b, 3)] for t, a, b in keep]})
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
    threading.Thread(target=transcricao.nucleos_fisicos, daemon=True).start()   # descobre ja na abertura (leva uns segundos)
    srv = ThreadingHTTPServer(("127.0.0.1", porta), H)
    url = f"http://127.0.0.1:{porta}/"
    print(f"Clipay.ia rodando em {url}  (feche esta janela para sair)")
    if abrir:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
