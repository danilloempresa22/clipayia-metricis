"""Edicoes feitas neste computador, de qualquer modelo: alimenta "Suas edicoes recentes" no Inicio e os numeros e a
lista "Projetos criados" da Conta. So o que existe de verdade: o historico local (historico.json da Edicao e do React,
historico_cortes.json do Cortes) e a pasta do projeto no CapCut (apagado no CapCut, some daqui).
Entradas antigas nao tinham o modelo: aparecem como "Edição" (desde agora cada projeto anota o modelo)."""
import json, threading
from datetime import datetime, timezone
from pathlib import Path
from . import transcricao

NOMES = {"reels": "Cortes + Headline", "cortes": "Cortes + Headline", "ipad": "Apresentador + iPad", "rotina": "Rotina",
         "legenda": "Legenda Complexa", "react": "React", "cortes-basico": "Cortes de podcast"}
SEM_MODELO = "Edição"
_TRAVA = threading.Lock()


def _arq():
    return transcricao.pasta_dados() / "historico.json"


def _le(f):
    try:
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def anota(nome, modelo, duracao, extra=None):
    """um projeto criado: entra no comeco do historico local (o mesmo arquivo que a Edicao ja usava)"""
    item = {"data": datetime.now(timezone.utc).isoformat(timespec="seconds"), "nome": nome, "modelo": modelo,
            "depois": round(float(duracao or 0), 1)}
    item.update(extra or {})
    with _TRAVA:
        h = [item] + _le(_arq())
        f = _arq(); tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(h[:200], ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(f)


def _data(x):
    try:
        return datetime.fromisoformat(str(x.get("data", "")).replace("Z", "+00:00"))
    except ValueError:
        return None


def todas(raiz):
    """todas as edicoes cujo projeto ainda existe no CapCut, mais novas primeiro (sem repetir o mesmo projeto)"""
    raiz = Path(raiz) if raiz else None
    itens = []
    for x in _le(_arq()):
        itens.append({"projeto": x.get("nome"), "modelo": NOMES.get(x.get("modelo"), x.get("modelo") or SEM_MODELO),
                      "duracao": x.get("depois"), "data": x.get("data")})
    for x in _le(transcricao.pasta_dados() / "historico_cortes.json"):
        itens.append({"projeto": x.get("projeto"), "modelo": NOMES["cortes-basico"], "duracao": x.get("duracao"),
                      "data": x.get("data")})
    vistos, out = set(), []
    for x in sorted((i for i in itens if i["projeto"] and _data(i)), key=_data, reverse=True):
        if x["projeto"] in vistos: continue
        vistos.add(x["projeto"])
        pasta = raiz / x["projeto"] if raiz else None
        if pasta is None or not (pasta / "draft_content.json").exists(): continue
        x["capa"] = (pasta / "draft_cover.jpg").exists()
        out.append(x)
    return out


def resumo(raiz, recentes=12, ultimos=5):
    """o que o Inicio e a Conta mostram: as recentes, os numeros (total, neste mes, ultima) e os 5 ultimos"""
    ts = todas(raiz)
    agora = datetime.now().astimezone()
    mes = [x for x in ts if (_data(x).astimezone().year, _data(x).astimezone().month) == (agora.year, agora.month)]
    return {"recentes": ts[:recentes], "ultimos": ts[:ultimos], "total": len(ts), "mes": len(mes),
            "ultima": ts[0] if ts else None}


def capa(raiz, projeto):
    """a capa do projeto no CapCut (um quadro real dele). So nome de pasta, nada de caminho."""
    if not raiz or not projeto or Path(projeto).name != projeto or projeto in (".", ".."):
        return None
    f = Path(raiz) / projeto / "draft_cover.jpg"
    return f if f.is_file() else None
