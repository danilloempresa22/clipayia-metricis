"""Uma edicao do comeco ao fim: le o projeto, analisa, monta e grava um projeto NOVO no CapCut."""
import re, tempfile
from pathlib import Path
import numpy as np
from . import capcut, vlog, reels, transcricao, audio, rosto


def agrupa(pl):
    """tabela do resumo: um item por arquivo de clipe"""
    g = {}
    for p in pl:
        c = g.setdefault(p["clip"], {"clip": p["clip"], "tipo": p["tipo"], "antes": 0.0, "depois": 0.0, "pedacos": 0})
        c["antes"] += p["dur"]; c["depois"] += sum(q[1] - q[0] for q in p["keep"]); c["pedacos"] += len(p["keep"])
        if p["tipo"] != c["tipo"]: c["tipo"] = "misto"
    return list(g.values())


def processa(raiz, pasta, modo, opcoes=None, avisa=None):
    """modo: 'vlog' | 'reels'. opcoes: rosto, headline, inicio, fim, transcrever, modelo, mp3, nome.
    avisa(etapa, fracao 0-1). Devolve resumo (dict).

    FLUXO ANTIGO: processa um projeto CapCut existente."""
    op = dict(opcoes or {})
    avisa = avisa or (lambda *a: None)
    pasta = Path(pasta)
    avisa("Lendo o projeto", 0.02)
    draft, meta = capcut.carrega(pasta)
    nome_base = op.get("nome") or re.sub(r" - corte( v\d+)?$", "", pasta.name) + " - corte"
    capa = pasta / "draft_cover.jpg"
    return _executa(raiz, draft, meta, pasta, nome_base, modo, op, avisa, capa if capa.exists() else None)


def _prepara_video(raiz, video_path, avisa):
    video = Path(video_path)
    if not video.is_file():
        raise capcut.ErroProjeto(f"Vídeo não encontrado: {video}")
    avisa("Lendo o vídeo", 0.02)
    try:
        info = audio.probe_video(video)
    except RuntimeError as e:
        raise capcut.ErroProjeto(str(e))
    if not info["tem_audio"]:
        raise capcut.ErroProjeto("Esse vídeo não tem trilha de áudio, então não dá pra achar os cortes de fala.")
    sonda = capcut.sonda_capcut(raiz)              # falha aqui se o CapCut criptografa os projetos
    draft, meta = capcut.cria_draft(video, info, sonda)
    return video, info, draft, meta


def analisa_video(raiz, video_path, opcoes=None, avisa=None):
    """1a metade do fluxo novo: le o video, transcreve e acha os cortes. NAO grava nada no CapCut.
    Devolve 'an' (estado da analise) pra tela de revisao e depois pra monta_video."""
    op = dict(opcoes or {})
    avisa = avisa or (lambda *a: None)
    video, info, draft, meta = _prepara_video(raiz, video_path, avisa)
    an = _analisa(raiz, draft, meta, None, "reels", op, avisa)
    avisa("Vendo de que lado você aparece", 0.95)
    try:
        lado, confiavel = rosto.lado_do_rosto(video, info["duracao"])
    except Exception:                               # detector e' so sugestao: nunca derruba a analise
        lado, confiavel = "centro", False
    an.update({"video": video, "info": info, "rosto": lado, "rosto_confiavel": confiavel})
    return an


def monta_video(raiz, an, opcoes=None, avisa=None):
    """2a metade: aplica headline, cortes extras (op['remover'] = [[ini, fim], ...] em s do video), lado do
    rosto e grava o projeto NOVO no CapCut."""
    op = dict(opcoes or {})
    avisa = avisa or (lambda *a: None)
    with tempfile.TemporaryDirectory() as tmp:
        capa = Path(tmp) / "draft_cover.jpg"
        audio.capa(an["video"], capa)
        return _monta(raiz, an, op.get("nome") or an["video"].stem + " - corte", "reels", op, avisa,
                      capa if capa.exists() else None)


def processa_video(raiz, video_path, modo, opcoes=None, avisa=None):
    """FLUXO NOVO em um passo so (sem tela de revisao): video bruto -> projeto CapCut pronto."""
    op = dict(opcoes or {})
    avisa = avisa or (lambda *a: None)
    video, info, draft, meta = _prepara_video(raiz, video_path, avisa)
    an = _analisa(raiz, draft, meta, None, modo, op, avisa)
    with tempfile.TemporaryDirectory() as tmp:
        capa = Path(tmp) / "draft_cover.jpg"
        audio.capa(video, capa)
        return _monta(raiz, an, op.get("nome") or video.stem + " - corte", modo, op, avisa,
                      capa if capa.exists() else None)


def _executa(raiz, draft, meta, pasta, nome_base, modo, op, avisa, capa):
    an = _analisa(raiz, draft, meta, pasta, modo, op, avisa)
    return _monta(raiz, an, nome_base, modo, op, avisa, capa)


def _analisa(raiz, draft, meta, pasta, modo, op, avisa):
    avisa("Lendo o áudio dos clipes", 0.05)
    itens = capcut.audio_dos_clipes(draft, op.get("mp3"),
                                    lambda i, n: avisa("Lendo o áudio dos clipes", 0.05 + 0.15 * i / n), pasta)
    if all(len(x) == 0 or float(np.abs(x).max()) < 1e-3 for _, _, x in itens):
        raise capcut.ErroProjeto("Não encontrei fala nesse vídeo (sem áudio ou totalmente mudo).")

    frases = {}
    if op.get("transcrever"):
        qual = op.get("modelo", "preciso")
        if not transcricao.modelo_pronto(qual):
            transcricao.baixa_modelo(qual, lambda f, t: avisa("Baixando o modelo de transcrição (só na 1ª vez)", 0.2 + 0.1 * f / t))
        w = transcricao.Whisper(qual)
        total = sum(len(x) for _, _, x in itens) or 1; feito = 0
        for k, (s, m, x) in enumerate(itens):
            src0 = s["source_timerange"]["start"] / 1e6
            fr = transcricao.frases(w, x, lambda i, n, f0=feito, lx=len(x):
                                     avisa("Transcrevendo", 0.3 + 0.4 * (f0 + lx * i / n) / total))
            frases[k] = [[a + src0, b + src0, t] for a, b, t in fr]
            feito += len(x)

    avisa("Achando os cortes", 0.72)
    prog = lambda i, n: avisa("Achando os cortes", 0.72 + 0.18 * i / n)
    pl = vlog.plano(itens, prog) if modo == "vlog" else reels.plano(itens, op.get("inicio"), op.get("fim"), prog)
    return {"draft": draft, "meta": meta, "pasta": pasta, "pl": pl, "frases": frases}


def _monta(raiz, an, nome_base, modo, op, avisa, capa):
    draft, meta, pl, frases = an["draft"], an["meta"], an["pl"], an["frases"]
    pl = [dict(p, keep=[list(k) for k in p["keep"]]) for p in pl]          # nao mexe na analise guardada
    if op.get("remover") and pl:
        pl[0]["keep"] = audio.tira(pl[0]["keep"], op["remover"])
    if modo == "vlog":
        novo, erros = vlog.montar(draft, pl); zooms = []
    elif modo == "reels":
        texto = reels.quebra_2_linhas(op["headline"]) if op.get("headline") else "EDITAR\nHEADLINE"
        tpl = reels.carrega_tpl(capcut.cache_efeitos(raiz))
        novo, zooms, erros = reels.montar(draft, pl, texto, tpl, op.get("rosto", "centro"))
    else:
        raise ValueError("modo inválido")
    if erros:
        raise capcut.ErroProjeto("A verificação do projeto falhou: " + ", ".join(sorted(set(erros))[:5]))

    avisa("Gravando no CapCut", 0.92)
    nome = capcut.grava_projeto(raiz, nome_base, novo, meta, capa)

    resumo = {"nome": nome, "modo": modo,
              "antes": sum(p["dur"] for p in pl), "depois": novo["duration"] / 1e6,
              "pedacos": sum(len(p["keep"]) for p in pl),
              "clipes": agrupa(pl)}
    if modo == "reels":
        resumo["zooms"] = sum(1 for z in zooms if z)
        resumo["empurroes"] = sum(1 for z in zooms if z and z[0] == "empurra")
        resumo["headline"] = texto
    if frases:
        leg = transcricao.mapeia(frases, pl)
        destino = Path(raiz) / nome / "legenda_cortes.srt"
        destino.write_text(transcricao.srt(leg), encoding="utf-8")
        txt = "\n".join(t for k in sorted(frases) for _, _, t in frases[k])
        (Path(raiz) / nome / "transcricao.txt").write_text(txt, encoding="utf-8")
        resumo["legenda"] = str(destino)
        resumo["transcricao"] = txt
    avisa("Pronto", 1.0)
    return resumo
