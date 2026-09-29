"""Conta do usuario no Supabase: login, status ativo/inativo e contador de uso.
So urllib. A chave anon e' publica por desenho (o RLS protege os dados); a service_role NUNCA entra aqui."""
import os, json, time, base64, urllib.request, urllib.error
from pathlib import Path
from . import transcricao

_CFG = json.loads((Path(__file__).resolve().parent / "config_publica.json").read_text(encoding="utf-8"))
SUPABASE_URL = os.environ.get("SUPABASE_URL", _CFG["supabase_url"])
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", _CFG["anon_key"])
SITE_URL = os.environ.get("CLIPAY_SITE", "https://clipayia-metricis.vercel.app")


class ErroConta(Exception):
    pass


def _arq():
    return transcricao.pasta_dados() / "sessao.json"


def _chama(metodo, caminho, corpo=None, token=None, extra=None):
    h = {"apikey": ANON_KEY, "Authorization": f"Bearer {token or ANON_KEY}", "Content-Type": "application/json"}
    h.update(extra or {})
    req = urllib.request.Request(SUPABASE_URL + caminho, method=metodo, headers=h,
                                 data=json.dumps(corpo).encode() if corpo is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            b = r.read()
            return json.loads(b) if b else None
    except urllib.error.HTTPError as e:
        try: d = json.loads(e.read())
        except ValueError: d = {}
        raise ErroConta(_traduz(d, e.code))
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ErroConta("Sem conexão com a internet. O Clipay.ia precisa de internet para validar sua conta.")


def _traduz(d, codigo):
    m = (d.get("error_description") or d.get("msg") or d.get("message") or "").lower()
    if "invalid login" in m or "invalid_grant" in m: return "E-mail ou senha incorretos."
    if "not confirmed" in m: return "Confirme seu e-mail (link enviado no cadastro) antes de entrar."
    if codigo in (401, 403) or "jwt" in m: return "Sessão expirada. Entre de novo."
    return d.get("error_description") or d.get("msg") or d.get("message") or f"Erro do servidor ({codigo})."


def _user_id(token):
    try:
        p = token.split(".")[1]; p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p))["sub"]
    except (IndexError, KeyError, ValueError):
        raise ErroConta("Sessão inválida. Entre de novo.")


def _guarda(d):
    s = {"access_token": d["access_token"], "refresh_token": d["refresh_token"],
         "expira": int(time.time()) + int(d.get("expires_in", 3600)) - 60,
         "email": (d.get("user") or {}).get("email", "")}
    s["user_id"] = _user_id(s["access_token"])
    _arq().write_text(json.dumps(s), encoding="utf-8")
    return s


def login(email, senha):
    if not email or not senha:
        raise ErroConta("Preencha e-mail e senha.")
    return _guarda(_chama("POST", "/auth/v1/token?grant_type=password", {"email": email.strip(), "password": senha}))


def logout():
    try: _arq().unlink()
    except OSError: pass


def sessao():
    """sessao valida (renova o token se venceu) ou None"""
    try: s = json.loads(_arq().read_text(encoding="utf-8"))
    except (OSError, ValueError): return None
    if s.get("expira", 0) > time.time():
        return s
    try:
        return _guarda(_chama("POST", "/auth/v1/token?grant_type=refresh_token", {"refresh_token": s["refresh_token"]}))
    except ErroConta as e:
        if "internet" in str(e): raise                      # sem rede: nao derruba o login
        logout(); return None


def estado():
    """{logado, email, username, status}. status: 'ativo' | 'inativo'."""
    s = sessao()
    if not s:
        return {"logado": False}
    uid = s["user_id"]
    ass = _chama("GET", f"/rest/v1/subscriptions?select=status&user_id=eq.{uid}", token=s["access_token"])
    perf = _chama("GET", f"/rest/v1/profiles?select=username&id=eq.{uid}", token=s["access_token"])
    return {"logado": True, "email": s["email"], "username": perf[0]["username"] if perf else s["email"],
            "status": ass[0]["status"] if ass else "inativo"}


def exige_ativa():
    """barreira de uso: so processa com conta ativa (o banco tambem barra, ver policy processamentos)"""
    e = estado()
    if not e["logado"]:
        raise ErroConta("Entre na sua conta para usar o Clipay.ia.")
    if e["status"] != "ativo":
        raise ErroConta(f"Sua conta ainda não está ativa. Veja o status em {SITE_URL}")
    return e


def processamentos():
    """datas (ISO) de todos os projetos que esta conta ja gerou, em qualquer computador"""
    s = sessao()
    if not s:
        return []
    r = _chama("GET", f"/rest/v1/processamentos?select=created_at&user_id=eq.{s['user_id']}&order=created_at.desc&limit=5000",
               token=s["access_token"])
    return [x["created_at"] for x in r or []]


def registra_processamento():
    s = sessao()
    if s:
        _chama("POST", "/rest/v1/processamentos", {"user_id": s["user_id"]}, token=s["access_token"],
               extra={"Prefer": "return=minimal"})
