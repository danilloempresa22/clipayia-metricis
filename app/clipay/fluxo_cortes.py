"""Tela Cortes (Fase 4): o trabalho de verdade das Fases 1 a 3, em segundo plano, com o estado que a tela le.
Etapas: transcrever (longo) -> vozes -> a pessoa confirma o apresentador -> achar os cortes (IA) -> pronto.
Cada etapa grava o proprio cache (longo/vozes/achar): fechar o app no meio e voltar continua de onde parou.
Gerar e' um trabalho separado: um projeto do CapCut por corte, com o estado de cada linha."""
import hashlib, json, threading, time, traceback
from pathlib import Path
from . import achar, audio, cortes, longo, previa, transcricao, vozes

ANALISE = {"job": None}
GERACAO = {"job": None}


class Erro(Exception):
    pass


def _tempo(job, fase, t0):
    job["tempos"][fase] = round(time.perf_counter() - t0, 1)


def info_cache(caminho, modelo="preciso"):
    """o que ja foi feito deste video neste computador (sem processar nada)"""
    try:
        e = longo.estado_cache(caminho, modelo)
    except (OSError, RuntimeError) as x:
        raise Erro(str(x))
    pasta = longo.pasta_cache(caminho, modelo)
    ok_vozes = e["completo"] and all(vozes.le_vozes(pasta, k) is not None for k in range(e["prontas"]))
    return {"transcrito": e["completo"], "janelas_prontas": e["prontas"], "vozes": ok_vozes,
            "ja_processado": e["completo"] or e["prontas"] > 0}


def resumo_vozes(r):
    """as vozes pra tela confirmar: letra, quanto falou e uma frase de exemplo (a mais longa ate 12 s, do meio)"""
    out = []
    for l in r["vozes"]:
        d = r["palpite"]["por_voz"].get(l, {})
        fs = [f for f in r["frases"] if f["locutor"] == l]
        boas = [f for f in fs if 4 <= f["fim"] - f["ini"] <= 12 and len(f["texto"]) > 30] or fs
        ex = boas[len(boas) // 2] if boas else None
        out.append({"letra": l, "fala_s": round(d.get("fala_s", 0.0), 1), "parte": d.get("parte_da_fala", 0.0),
                    "exemplo": ex["texto"] if ex else "", "exemplo_ini": ex["ini"] if ex else 0.0})
    return out


def analisa(caminho, modelo="preciso", carrega_whisper=None):
    """comeca (ou continua pelo cache) a analise do video. O mesmo video ja em andamento: devolve o mesmo trabalho."""
    ant = ANALISE["job"]
    if ant and ant["caminho"] == caminho and ant["fase"] not in ("erro", "cancelado"):
        return ant
    if ant and not ant["parado"]:
        ant["cancelar"].set()
    job = {"caminho": caminho, "modelo": modelo, "fase": "transcrever", "progresso": {}, "erro": None,
           "cancelar": threading.Event(), "parado": False, "vozes": None, "palpite": None, "apresentador": None,
           "transc": None, "seg": None, "emb": None, "total": None, "tempos": {}, "sem_ia": False}
    ANALISE["job"] = job

    def roda():
        try:
            info = audio.probe_video(caminho)
            if not info["tem_audio"]:
                raise Erro("Esse vídeo não tem som. Cortes precisa da fala para achar os assuntos.")
            t0 = time.perf_counter()
            longo.transcreve(caminho, carrega_whisper, modelo, cancelado=job["cancelar"].is_set,
                             progresso=lambda e: job.update(progresso=e))
            _tempo(job, "transcrever", t0)
            job.update(fase="vozes", progresso={"fracao": 0.0})
            t0 = time.perf_counter()
            vozes.baixa_modelo(lambda f, t: job.update(progresso={"fracao": 0.0, "baixando": round(f / t, 3)}))
            seg, emb = vozes.identifica(caminho, modelo, cancelado=job["cancelar"].is_set, progresso=lambda e: job.update(
                progresso=dict(e, fracao=round(e["janelas_prontas"] / max(e["janelas_total"], 1), 4))))
            r = vozes.rotula(longo.resultado(caminho, modelo), seg, emb)
            _tempo(job, "vozes", t0)
            job.update(seg=seg, emb=emb, transc=r, vozes=resumo_vozes(r), palpite={"letra": r["palpite"]["letra"],
                       "confianca": r["palpite"]["confianca"]}, fase="apresentador", progresso={"fracao": 1.0})
        except longo.Cancelado:
            job.update(fase="cancelado")
        except Erro as e:
            job.update(fase="erro", erro=str(e))
        except Exception as e:                       # noqa: BLE001 — aparece na tela; o cache guarda o que ja foi feito
            traceback.print_exc(); job.update(fase="erro", erro=f"Erro na análise: {e}")
        finally:
            job["parado"] = True
    job["thread"] = threading.Thread(target=roda, daemon=True); job["thread"].start()
    return job


def confirma(letra, tipos=achar.TIPOS):
    """a pessoa confirmou quem e' o apresentador: rotula e acha os cortes (IA). Sem IA: fase sem_ia + modo manual."""
    job = ANALISE["job"]
    if not job or job["fase"] not in ("apresentador", "pronto", "sem_ia"):
        raise Erro("A análise ainda não chegou na confirmação do apresentador.")
    if letra not in (job["transc"] or {}).get("vozes", []):
        raise Erro("Essa voz não existe neste vídeo.")
    job.update(apresentador=letra, fase="achar", progresso={"fracao": 0.0}, erro=None, sem_ia=False, parado=False)
    job["cancelar"] = threading.Event()

    def roda():
        try:
            t0 = time.perf_counter()
            job["transc"] = vozes.rotula(longo.resultado(job["caminho"], job["modelo"]), job["seg"], job["emb"], letra)
            r = achar.achar_cortes(job["transc"], tipos, cancelado=job["cancelar"].is_set,
                                   progresso=lambda k, n: job.update(progresso={"fracao": round(k / n, 4), "janelas_prontas": k,
                                                                                 "janelas_total": n}))
            _tempo(job, "achar", t0)
            job.update(fase="pronto", total=r["todos"], progresso={"fracao": 1.0})
        except achar.SemIA as e:
            job.update(fase="sem_ia", sem_ia=True, erro=str(e))
        except longo.Cancelado:
            job.update(fase="apresentador")
        except Exception as e:                       # noqa: BLE001
            traceback.print_exc(); job.update(fase="erro", erro=f"Erro ao achar os cortes: {e}")
        finally:
            job["parado"] = True
    job["thread"] = threading.Thread(target=roda, daemon=True); job["thread"].start()
    return job


def lista(tipos):
    """os cortes achados filtrados pelos tipos marcados: so le o cache da IA (mudar os tipos nao chama a IA)"""
    job = ANALISE["job"]
    if not job or job["fase"] != "pronto":
        raise Erro("Os cortes ainda não foram achados.")
    return achar.achar_cortes(job["transc"], tipos)["cortes"]


def cancela():
    j = ANALISE["job"]
    if j: j["cancelar"].set()


def estado():
    j = ANALISE["job"]
    if not j:
        return {"ativo": False}
    return {"ativo": True, "caminho": j["caminho"], "fase": j["fase"], "progresso": j["progresso"], "falha": j["erro"],
            "vozes": j["vozes"], "palpite": j["palpite"], "apresentador": j["apresentador"], "total": j["total"],
            "tempos": j["tempos"], "parado": j["parado"], "sem_ia": j["sem_ia"],
            "duracao": (j["transc"] or {}).get("duracao")}


# ---------------- gerar todos (projetos do CapCut) ----------------
def _arq_geracao():
    return transcricao.pasta_dados() / "geracao_cortes.json"


def _chave_geracao(caminho, lista_cortes, raiz, velocidade, efeito, musica):
    corpo = [str(Path(caminho).resolve()), str(raiz), velocidade, efeito, (musica or {}).get("path"),
             [(c["numero"], round(c["ini"], 3), round(c["fim"], 3), c.get("tipo")) for c in lista_cortes]]
    return hashlib.sha1(json.dumps(corpo).encode()).hexdigest()


def _salva(job):
    try:
        f = _arq_geracao(); tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"chave": job["chave"], "linhas": job["linhas"]}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(f)
    except OSError:
        pass


def _feitos_antes(chave, raiz):
    """projetos que ja ficaram prontos desta mesma geracao (o app fechou no meio): nao refaz nem duplica"""
    try:
        d = json.loads(_arq_geracao().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if d.get("chave") != chave:
        return {}
    return {l["numero"]: l for l in d["linhas"]
            if l["estado"] == "pronto" and l.get("projeto") and (Path(raiz) / l["projeto"]).exists()}


def gera(caminho, lista_cortes, raiz, cache=None, musica=None, velocidade=True, efeito=True, so=None):
    """um projeto por corte, todos de uma vez, em segundo plano. so: numeros a refazer (os que falharam).
    A mesma geracao pedida de novo (tela reaberta): devolve a que esta rodando, ou continua so o que falta."""
    chave = _chave_geracao(caminho, lista_cortes, raiz, velocidade, efeito, musica)
    ant = GERACAO["job"]
    if ant and not ant["parado"]:
        if ant["chave"] == chave and so is None:
            return ant
        raise Erro("Já estou gerando os cortes. Espere terminar ou cancele.")
    mod = cortes.modelo()
    if not velocidade:
        mod["composto"]["velocidade"] = 1.0
    feitos = dict(_feitos_antes(chave, raiz))
    velhas = {l["numero"]: l for l in ant["linhas"]} if ant and ant["chave"] == chave else {}
    feitos.update({n: l for n, l in velhas.items() if l["estado"] == "pronto"})
    linhas = []
    for c in lista_cortes:
        n = c["numero"]
        if n in feitos and (so is None or n not in so):
            linhas.append(dict(feitos[n])); continue
        if so is not None and n not in so and n in velhas:
            linhas.append(dict(velhas[n])); continue
        linhas.append({"numero": n, "tipo": c.get("tipo"), "duracao": c.get("duracao", c["fim"] - c["ini"]),
                       "nome": achar.nome_corte(caminho, c), "estado": "fila", "fracao": 0.0, "erro": None, "projeto": None})
    job = {"linhas": linhas, "cancelar": threading.Event(), "parado": False, "t0": time.perf_counter(), "tempo": None,
           "chave": chave}
    GERACAO["job"] = job; _salva(job)
    por_num = {c["numero"]: c for c in lista_cortes}

    def roda():
        tmp = transcricao.pasta_dados() / "temp"; tmp.mkdir(parents=True, exist_ok=True)
        try:
            for l in job["linhas"]:
                if l["estado"] == "pronto": continue
                if so is not None and l["numero"] not in so and l["estado"] in ("erro", "cancelado"): continue
                if job["cancelar"].is_set():
                    l["estado"] = "cancelado"; continue
                c = por_num[l["numero"]]
                try:
                    if not Path(caminho).exists():
                        raise Erro("O vídeo não está mais nesse lugar. Ele foi movido ou apagado?")
                    l.update(estado="montando", erro=None)
                    ed = previa.edicao(caminho, c["ini"], c["fim"], mod)        # a mesma edicao do preview
                    r = cortes.monta(caminho, c["ini"], c["fim"], cache=cache, musica=musica, mod=mod, efeito=efeito, ed=ed)
                    l.update(estado="gravando")
                    capa = tmp / f"capa_corte_{l['numero']}.jpg"
                    audio.capa(caminho, capa, c["ini"] + 0.5)
                    l["projeto"] = cortes.grava(raiz, l["nome"], r, capa=capa)
                    l.update(estado="pronto", fracao=1.0)
                    try:                             # o historico do Inicio nunca derruba um projeto ja criado
                        anota_recente(l, c, caminho, (r.get("draft") or {}).get("duration", 0) / 1e6, mod["composto"]["velocidade"])
                    except Exception:                # noqa: BLE001
                        traceback.print_exc()
                except Exception as e:               # noqa: BLE001 — um corte que falha nao derruba os outros
                    traceback.print_exc(); l.update(estado="erro", erro=_motivo(e, caminho), fracao=0.0)
                _salva(job)
        finally:
            job["tempo"] = round(time.perf_counter() - job["t0"], 1); job["parado"] = True; _salva(job)
    job["thread"] = threading.Thread(target=roda, daemon=True); job["thread"].start()
    return job


# ---------------- historico dos projetos de Cortes (faixa "Seus cortes recentes" do Inicio) ----------------
def _arq_recentes():
    return transcricao.pasta_dados() / "historico_cortes.json"


def _le_recentes():
    try:
        return json.loads(_arq_recentes().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def anota_recente(l, c, caminho, duracao, vel):
    """cada projeto de Cortes criado neste computador (so Cortes: a Edicao tem o historico dela)"""
    from datetime import datetime, timezone
    try:
        k = previa.chave(caminho, c["ini"], c["fim"], cortes.modelo(), "curto", vel, "")
    except OSError:
        k = None
    item = {"projeto": l["projeto"], "nome": l["nome"], "numero": l["numero"], "duracao": round(duracao, 1),
            "data": datetime.now(timezone.utc).isoformat(timespec="seconds"), "previa": k}
    with _TRAVA_REC:
        h = [x for x in (_le_recentes() or []) if x.get("projeto") != item["projeto"]]
        h.insert(0, item)
        f = _arq_recentes(); tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(h[:200], ensure_ascii=False), encoding="utf-8"); tmp.replace(f)


_TRAVA_REC = threading.Lock()


def recentes(raiz, n=12):
    """os ultimos projetos de Cortes que ainda existem na pasta do CapCut, mais novos primeiro. Na 1a vez, o
    historico comeca pela ultima geracao gravada (sem a previa: dela nao se sabe o trecho)."""
    from datetime import datetime, timezone
    h = _le_recentes()
    if h is None:
        try:
            g = json.loads(_arq_geracao().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            g = {"linhas": []}
        h = []
        for l in g.get("linhas", []):
            pasta = Path(raiz) / (l.get("projeto") or "")
            if l.get("estado") == "pronto" and l.get("projeto") and pasta.exists():
                h.append({"projeto": l["projeto"], "nome": l["nome"], "numero": l["numero"], "duracao": None,
                          "data": datetime.fromtimestamp(pasta.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
                          "previa": None})
        h.sort(key=lambda x: x["data"], reverse=True)
    out = []
    for x in h:
        if not (Path(raiz) / x["projeto"]).exists():
            continue                                 # apagado no CapCut: sai da faixa
        tem = bool(x.get("previa")) and (previa.pasta() / f"{x['previa']}_curto.mp4").exists()
        out.append(dict(x, tem_previa=tem))
        if len(out) >= n: break
    return out


def arquivo_previa_por_chave(k):
    """o preview curto do cache pela chave (faixa do Inicio). Chave = 40 hex, nada de caminho vindo de fora."""
    import re
    if not re.fullmatch(r"[0-9a-f]{40}", k or ""):
        return None
    f = previa.pasta() / f"{k}_curto.mp4"
    return f if f.exists() else None


def estado_geracao():
    j = GERACAO["job"]
    if not j:
        return {"ativo": False}
    return {"ativo": True, "parado": j["parado"], "tempo": j["tempo"],
            "prontos": sum(l["estado"] == "pronto" for l in j["linhas"]), "total": len(j["linhas"]),
            "linhas": [dict(l) for l in j["linhas"]]}


def cancela_geracao():
    j = GERACAO["job"]
    if j: j["cancelar"].set()
    cancela_previas()


# ---------------- previews (o que a grade mostra): separados dos projetos ----------------
PREVIAS = {"chave": None, "video": None, "cortes": {}, "estado": {}, "fila": [], "fila_inteiro": [], "opcoes": {},
           "cancelar": threading.Event(), "trabalhando": set(), "trabalhando_inteiro": set(), "cancelado": False}
_COND = threading.Condition()
PARALELO_PREVIAS = 2                         # no maximo 2 renders da grade ao mesmo tempo (o computador continua usavel)
# + 1 vaga so pro corte inteiro que a pessoa clicou (nao espera a grade): no maximo 3 renders juntos


SUMIU = "O vídeo não está mais nesse lugar. Ele foi movido ou apagado?"


def _motivo(x, video):
    """o motivo curto pro cartao; o video sumiu no meio (o erro do Windows e' tecnico): a frase clara"""
    return SUMIU if not Path(video).exists() else _curto(x)


def _curto(x):
    m = str(x).strip().splitlines()[0] if str(x).strip() else type(x).__name__
    return m if len(m) <= 140 else m[:137] + "…"


def prepara_previas(caminho, lista_cortes, velocidade=True, musica=None, cache_capcut=None):
    """a lista da grade. A mesma lista de novo (tela reaberta) mantem o que ja foi feito; o cache em disco
    devolve na hora os previews que ja existem."""
    vel = cortes.modelo()["composto"]["velocidade"] if velocidade else 1.0
    chave = (str(Path(caminho).resolve()), tuple((c["numero"], round(c["ini"], 3), round(c["fim"], 3)) for c in lista_cortes),
             vel, (musica or {}).get("path"))
    with _COND:
        if PREVIAS["chave"] != chave:
            PREVIAS.update(chave=chave, video=str(caminho), cortes={c["numero"]: c for c in lista_cortes}, fila=[], fila_inteiro=[], cancelado=False,
                           estado={c["numero"]: {"curto": "nada", "inteiro": "nada", "erro": None, "fracao": 0.0, "dur": None}
                                   for c in lista_cortes},
                           opcoes={"vel": vel, "musica": musica, "cache": cache_capcut})
            for c in lista_cortes:
                for tipo in ("curto", "inteiro"):
                    if _arq_previa(c["numero"], tipo).exists():
                        PREVIAS["estado"][c["numero"]][tipo] = "pronto"
    return estado_previas()


def _arq_previa(numero, tipo):
    c = PREVIAS["cortes"][numero]; o = PREVIAS["opcoes"]
    try:
        k = previa.chave(PREVIAS["video"], c["ini"], c["fim"], cortes.modelo(), tipo, o["vel"],
                         (o["musica"] or {}).get("path") if tipo == "inteiro" else "")
    except OSError:                                  # o video sumiu: nao ha arquivo
        return previa.pasta() / "inexistente.mp4"
    return previa.pasta() / f"{k}_{tipo}.mp4"


def pede_previas(numeros, tipo="curto", de_novo=False):
    """poe na frente da fila (os cartoes que estao na tela agora). de_novo: "Tentar de novo" depois de um erro."""
    fila, quem, vagas = ("fila_inteiro", "trabalhando_inteiro", 1) if tipo == "inteiro" else ("fila", "trabalhando", PARALELO_PREVIAS)
    with _COND:
        if PREVIAS["cancelado"] and not de_novo and tipo == "curto":
            return _estado()                            # cancelou: a grade so volta a pedir com "Tentar de novo"
        if de_novo: PREVIAS["cancelado"] = False
        for n in reversed([n for n in numeros if n in PREVIAS["estado"]]):
            e = PREVIAS["estado"][n]
            if e[tipo] == "erro" and not de_novo: continue
            if e[tipo] in ("pronto", "render"): continue
            if (n, tipo) in PREVIAS[fila]: PREVIAS[fila].remove((n, tipo))
            PREVIAS[fila].insert(0, (n, tipo)); e[tipo] = "fila"
            if de_novo: e["erro"] = None
        PREVIAS["cancelar"].clear()
        while len(PREVIAS[quem]) < min(vagas, len(PREVIAS[fila]) + len(PREVIAS[quem])):
            t = threading.Thread(target=_trabalha, args=(fila, quem), daemon=True); PREVIAS[quem].add(t); t.start()
    return _estado()


def _trabalha(fila="fila", quem="trabalhando"):
    eu = threading.current_thread()
    try:
        while True:
            with _COND:
                if not PREVIAS[fila]:
                    return
                n, tipo = PREVIAS[fila].pop(0)
                if n not in PREVIAS["cortes"]: continue
                c, o, e = PREVIAS["cortes"][n], dict(PREVIAS["opcoes"]), PREVIAS["estado"][n]
                e[tipo] = "render"
                if tipo == "inteiro": e["fracao"] = 0.0
                video, chave = PREVIAS["video"], PREVIAS["chave"]
            try:
                if not Path(video).exists():
                    raise Erro("O vídeo não está mais nesse lugar.")
                mod = cortes.modelo()
                ed = previa.edicao(video, c["ini"], c["fim"], mod)
                e["dur"] = round(previa.duracao_final(ed, o["vel"]), 1)
                destino = _arq_previa(n, tipo)
                if not destino.exists():
                    previa.render(video, ed, destino, mod, o["vel"], limite_s=previa.CURTO_S if tipo == "curto" else None,
                                  som=tipo == "inteiro", musica=o["musica"] if tipo == "inteiro" else None,
                                  cache_capcut=o["cache"], cancelado=PREVIAS["cancelar"].is_set,
                                  progresso=(lambda f: e.update(fracao=round(f, 3))) if tipo == "inteiro" else None)
                with _COND:
                    if PREVIAS["chave"] == chave: e[tipo] = "pronto"
            except (previa.Cancelado, longo.Cancelado):
                with _COND:
                    if PREVIAS["chave"] == chave: e[tipo] = "nada"
            except Exception as x:                   # noqa: BLE001 — o cartao mostra o erro; os outros continuam
                traceback.print_exc()
                with _COND:
                    if PREVIAS["chave"] == chave: e.update({tipo: "erro", "erro": _motivo(x, video)})
    finally:
        with _COND:
            PREVIAS[quem].discard(eu)


def _estado():
    return {"previas": {str(n): dict(e) for n, e in PREVIAS["estado"].items()}, "cancelado": PREVIAS["cancelado"],
            "renderizando": sum(e[t] == "render" for e in PREVIAS["estado"].values() for t in ("curto", "inteiro"))}


def estado_previas():
    with _COND:
        return _estado()


def arquivo_previa(numero, tipo):
    with _COND:
        if numero not in PREVIAS["cortes"] or PREVIAS["estado"][numero][tipo] != "pronto":
            return None
        return _arq_previa(numero, tipo)


def cancela_previas():
    with _COND:
        for n, t in PREVIAS["fila"] + PREVIAS["fila_inteiro"]:
            PREVIAS["estado"][n][t] = "nada"
        PREVIAS["fila"] = []; PREVIAS["fila_inteiro"] = []
        PREVIAS["cancelar"].set(); PREVIAS["cancelado"] = True
