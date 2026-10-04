"""Tela Cortes (Fase 4): o trabalho de verdade das Fases 1 a 3, em segundo plano, com o estado que a tela le.
Etapas: transcrever (longo) -> vozes -> a pessoa confirma o apresentador -> achar os cortes (IA) -> pronto.
Cada etapa grava o proprio cache (longo/vozes/achar): fechar o app no meio e voltar continua de onde parou.
Gerar e' um trabalho separado: um projeto do CapCut por corte, com o estado de cada linha."""
import threading, time, traceback
from pathlib import Path
from . import achar, audio, cortes, longo, transcricao, vozes

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


# ---------------- gerar todos ----------------
def gera(caminho, lista_cortes, raiz, cache=None, musica=None, velocidade=True, efeito=True, so=None):
    """um projeto por corte, todos de uma vez. so: numeros a refazer ("Tentar de novo os que falharam")."""
    ant = GERACAO["job"]
    if ant and not ant["parado"]:
        raise Erro("Já estou gerando os cortes. Espere terminar ou cancele.")
    mod = cortes.modelo()
    if not velocidade:
        mod["composto"]["velocidade"] = 1.0
    linhas = [{"numero": c["numero"], "tipo": c["tipo"], "duracao": c.get("duracao", c["fim"] - c["ini"]),
               "nome": achar.nome_corte(caminho, c), "estado": "fila", "fracao": 0.0, "erro": None, "projeto": None}
              for c in lista_cortes if so is None or c["numero"] in so]
    if so is not None and ant:                     # refazer: as que ja deram certo continuam na tela
        feitas = {l["numero"]: l for l in ant["linhas"] if l["estado"] == "pronto"}
        linhas = sorted(list(feitas.values()) + linhas, key=lambda l: l["numero"])
    job = {"linhas": linhas, "cancelar": threading.Event(), "parado": False, "t0": time.perf_counter(), "tempo": None}
    GERACAO["job"] = job
    por_num = {c["numero"]: c for c in lista_cortes}

    def roda():
        tmp = transcricao.pasta_dados() / "temp"; tmp.mkdir(parents=True, exist_ok=True)
        try:
            for l in job["linhas"]:
                if l["estado"] == "pronto": continue
                if job["cancelar"].is_set():
                    l["estado"] = "cancelado"; continue
                c = por_num[l["numero"]]
                try:
                    if not Path(caminho).exists():
                        raise Erro("O vídeo não está mais nesse lugar. Ele foi movido ou apagado?")
                    l.update(estado="montando", fracao=0.15)
                    r = cortes.monta(caminho, c["ini"], c["fim"], cache=cache, musica=musica, mod=mod, efeito=efeito)
                    l.update(estado="gravando", fracao=0.8)
                    capa = tmp / f"capa_corte_{l['numero']}.jpg"
                    audio.capa(caminho, capa, c["ini"] + 0.5)
                    l["projeto"] = cortes.grava(raiz, l["nome"], r, capa=capa)
                    l.update(estado="pronto", fracao=1.0)
                except Exception as e:               # noqa: BLE001 — um corte que falha nao derruba os outros
                    traceback.print_exc(); l.update(estado="erro", erro=str(e), fracao=0.0)
        finally:
            job["tempo"] = round(time.perf_counter() - job["t0"], 1); job["parado"] = True
    job["thread"] = threading.Thread(target=roda, daemon=True); job["thread"].start()
    return job


def estado_geracao():
    j = GERACAO["job"]
    if not j:
        return {"ativo": False}
    return {"ativo": True, "parado": j["parado"], "tempo": j["tempo"],
            "linhas": [{k: v for k, v in l.items()} for l in j["linhas"]]}


def cancela_geracao():
    j = GERACAO["job"]
    if j: j["cancelar"].set()
