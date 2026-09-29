"""Legenda Complexa: regua de corte, marcadores, matematica da legenda, checklist e estrutura de composto aninhado."""
import copy, json, os
from pathlib import Path
import pytest
from clipay import audio, capcut, composto, legenda, palavras, processa, transcricao


def P(t, a, b):
    return {"t": t, "a": a, "b": b}


# ---------------- regua de corte por palavra ----------------
def test_corte_por_palavra_folgas_gaguejada_e_muleta():
    pal = [P("eu", 1.0, 1.2), P("eu", 1.3, 1.5),                     # gaguejada (gap 0.1 < 0.4): fica a segunda
           P("acho", 1.55, 1.8), P("que", 1.85, 2.0),                 # mesma frase (gaps <= 250 ms)
           P("né", 3.0, 3.2),                                         # muleta isolada entre silencios: sai
           P("isso", 5.0, 5.3),                                       # palavra curta isolada (<= 800 ms)
           P("funciona", 7.0, 7.6), P("muito", 7.65, 7.9), P("bem", 7.95, 8.2)]
    keep, mant = legenda.cortes(pal, 10.0)
    assert [p["t"] for p in mant] == ["eu", "acho", "que", "isso", "funciona", "muito", "bem"]
    assert keep[0] == [pytest.approx(1.3 - 0.150), pytest.approx(2.0 + 0.200)]                # trecho de 0,7 s: curto, 150/200 ms
    assert keep[1] == [pytest.approx(5.0 - 0.150), pytest.approx(5.3 + 0.200)]                # palavra isolada: 150/200 ms
    assert keep[2] == [pytest.approx(7.0 - 0.060), pytest.approx(8.2 + 0.060)]                # frase (1,2 s): 60/60 ms
    assert len(keep) == 3 and not any(a < 3.2 < b for a, b in keep)                            # "né" cortado


def test_inicio_no_gancho_e_mapa_de_tempo():
    keep, mant = legenda.cortes([P("então", 0.5, 0.9), P("vou", 1.0, 1.2), P("começar", 2.0, 2.6)], 5)
    k2, m2 = legenda.a_partir_de(keep, mant, 1.94)
    assert k2[0][0] == pytest.approx(1.94) and [p["t"] for p in m2] == ["começar"]
    f, total = legenda.mapa_tempo([[1.0, 2.0], [3.0, 4.0]])
    assert total == 2.0 and f(1.5) == 0.5 and f(3.5) == 1.5 and f(2.5) == 1.0               # buraco vai pro proximo pedaco


# ---------------- marcadores e texto ----------------
def test_marcadores_maiuscula_e_alinhamento():
    tk = legenda.tokens("se você [nunca] tentou *isso* porque?")
    assert [(t["txt"], t["tipo"]) for t in tk] == [("Se", "normal"), ("você", "normal"), ("[nunca]", "soco"),
                                                  ("tentou", "normal"), ("*isso*", "leve"), ("porque?", "pergunta")]
    pal = [P("se", 1, 1.2), P("voce", 1.3, 1.6), P("nunca", 1.7, 2.0), P("tentou", 2.1, 2.5), P("isso", 2.6, 2.9), P("porque", 3.0, 3.3)]
    al = legenda.alinha(tk, pal)
    assert [round(t["t0"], 2) for t in al] == [1.0, 1.3, 1.7, 2.1, 2.6, 3.0]                  # acento/marcadores nao atrapalham
    al = legenda.alinha(legenda.tokens("se você realmente tentou"), pal)                        # palavra digitada que nao esta no audio
    assert 1.3 < al[2]["t0"] < 2.1


# ---------------- enfase: escala por largura ----------------
def test_escala_da_enfase_segue_as_edicoes_aprovadas():
    reais = {"recaída": .943, "[droga]": .769, "promessas": .750, "[foda-se]": .740, "[MENTIROSO]": .530, "[VERGONHA]": .494}
    for txt, esc in reais.items():
        calc = legenda.escala_enfase(txt, zoom=True)
        assert abs(calc - esc) / esc < 0.35, (txt, calc, esc)       # ajuste a olho do editor varia ~13% em media
    assert legenda.escala_enfase("a", zoom=True) == 0.95                                        # zoom: teto 0.95
    assert legenda.escala_enfase("a", zoom=False) > 0.95                                        # aberto: pode estourar
    assert legenda.escala_enfase("[palavramuitomuitolonga]", zoom=True) == 0.50


# ---------------- legenda acumulada ----------------
def monta_de(texto, passo=0.4, fim=None, zoom=True):
    tk = legenda.tokens(texto)
    for i, t in enumerate(tk): t["t0"] = 0.2 + i * passo
    return legenda.monta(tk, fim or 0.2 + len(tk) * passo + 0.5, zoom)


def test_acumula_em_escada_e_grupo_sai_quando_o_proximo_comeca():
    segs = monta_de("isso aqui muda tudo agora mesmo")
    g0 = [s for s in segs if s["linha"][0] == 0]
    assert [s["txt"] for s in g0] == ["Isso", "Isso aqui", "muda", "muda tudo"]
    assert {s["y"] for s in g0} == {0.38, 0.265} and g0[2]["x"] == pytest.approx(-0.58 + 0.05, abs=0.02)
    g1_ini = min(s["ini"] for s in segs if s["linha"][0] == 1)
    assert g0[1]["fim"] == g0[3]["fim"] == g1_ini                                            # sai so quando o proximo comeca
    assert all(s["esc"] == legenda.ESC_BASE for s in segs)
    assert legenda.verifica(segs, 10) == []


def test_enfase_tem_linha_propria_e_no_maximo_3_linhas():
    segs = monta_de("eu sou [MENTIROSO] e [incapaz] mesmo")
    enf = [s for s in segs if s["tipo"] != "normal"]
    assert [s["txt"] for s in enf] == ["[MENTIROSO]", "[incapaz]"]
    for s in enf:
        assert 0.06 <= s["y"] <= 0.29 and -0.58 <= s["x"] <= -0.41 + 1e-9 and 0.5 <= s["esc"] <= 0.95
    for g in {s["linha"][0] for s in segs}:
        assert len({s["linha"][1] for s in segs if s["linha"][0] == g}) <= 3
    assert legenda.verifica(segs, 10) == []


@pytest.mark.parametrize("n", [1, 3, 60])
def test_poucas_e_muitas_palavras(n):
    segs = monta_de(" ".join(["palavra"] * n), passo=0.3)
    assert segs and legenda.verifica(segs, 100) == []
    assert segs[-1]["fim"] == pytest.approx(0.2 + n * 0.3 + 0.5)                              # ultimo grupo vai ate o fim


# ---------------- checklist pega o que esta quebrado ----------------
def test_checklist_pega_sobreposicao_por_altura_y_fora_da_tela_e_duracao():
    segs = monta_de("uma frase normal aqui")
    quebrado = copy.deepcopy(segs)
    quebrado.append(dict(quebrado[0], txt="intrusa", ini=quebrado[0]["ini"] + 0.05, fim=quebrado[0]["fim"] + 0.3,
                         y=quebrado[0]["y"] + 0.01))                                         # outra linha na mesma altura
    assert any("mesma altura" in e for e in legenda.verifica(quebrado, 10))
    assert any("não cabe" in e for e in legenda.verifica([dict(segs[0], x=0.95)], 10))
    assert any("fora da duração" in e for e in legenda.verifica([dict(segs[0], fim=99)], 10))


# ---------------- tempo por palavra ----------------
def test_palavra_curta_isolada_nao_casa_com_ocorrencia_distante():
    pal = [P("eu", 1, 1.2), P("acho", 1.3, 1.6), P("isso", 1.7, 2.0), P("que", 9.0, 9.2), P("fim", 9.3, 9.6)]
    al = legenda.alinha(legenda.tokens("eu acho que isso fim"), pal)       # "que" mudou de lugar no texto editado
    assert al[2]["t0"] < 2.0                                                # nao vai parar em 9 s arrastando "isso"


def test_whisper_com_tempo_prende_cada_frase_no_seu_lugar():
    class W:                                                                # frases do Whisper com tempo (relativo ao bloco)
        def segmentos(self, x): return [(0.0, 1.0, "primeira frase"), (4.4, 7.6, "segunda frase aqui")]
    x = __import__("numpy").zeros(16000 * 10, "float32")
    import clipay.palavras as pw
    orig = pw.trechos_de_fala
    pw.trechos_de_fala = lambda x: [[0.05, 1.0], [4.5, 5.5], [6.0, 7.5]]
    try:
        pal = pw.transcreve(W(), x)
    finally:
        pw.trechos_de_fala = orig
    assert [p["t"] for p in pal] == ["primeira", "frase", "segunda", "frase", "aqui"]
    assert all(p["a"] < 1.0 for p in pal[:2]) and all(p["a"] >= 4.5 for p in pal[2:])


def test_palavras_sao_espalhadas_so_no_tempo_de_fala():
    pal = palavras.espalha("um dois três quatro", [[1.0, 2.0], [3.0, 4.0]])
    assert len(pal) == 4 and pal[0]["a"] == pytest.approx(1.0, abs=0.01)
    for p in pal:
        assert not (2.0 + 1e-6 < p["a"] < 3.0 - 1e-6)                                        # ninguem comeca na pausa
    assert pal == sorted(pal, key=lambda p: p["a"])


# ---------------- estrutura de composto aninhado (o maior risco) ----------------
@pytest.fixture
def analise(video_vertical, raiz_capcut, monkeypatch):
    """analise real do video sintetico (ffmpeg + regua), com o Whisper simulado"""
    monkeypatch.setattr(transcricao, "modelo_pronto", lambda q="preciso": True)
    monkeypatch.setattr(transcricao, "Whisper", lambda q: None)
    frases = iter(["isso aqui muda tudo", "você nunca tentou isso", "fim"])
    monkeypatch.setattr(palavras, "transcreve", lambda w, x, p=None: [
        *palavras.espalha("isso aqui muda tudo", [[0.0, 3.0]]),
        *palavras.espalha("você nunca tentou isso", [[4.5, 7.5]]),
        *palavras.espalha("fim", [[9.0, 10.0]])])
    return processa.analisa_legenda(raiz_capcut, video_vertical)


def gera(raiz_capcut, an, **op):
    base = {"texto": "isso aqui muda tudo você [nunca] tentou *isso* fim", "nome": "Teste legenda"}
    return processa.monta_legenda(raiz_capcut, an, dict(base, **op))


def carrega(raiz_capcut, nome):
    p = Path(raiz_capcut) / nome
    return json.loads((p / "draft_content.json").read_text(encoding="utf-8")), p


def test_compostos_ficam_na_raiz_com_pastas_subdraft(raiz_capcut, analise):
    r = gera(raiz_capcut, analise, velocidade=1.15)
    d, pasta = carrega(raiz_capcut, r["nome"])
    drafts = d["materials"]["drafts"]
    assert len(drafts) == 3                                               # Corpo, Cortes, Legenda: lista plana
    for e in drafts:
        assert e["draft"]["materials"].get("drafts", []) == []            # nenhum composto dentro de composto
        assert e["draft_file_path"].startswith(composto.TOKEN)
        sub = pasta / "subdraft" / e["draft"]["id"]
        assert (sub / "draft_content.json").exists() and (sub / "sub_draft_config.json").exists()
        stub = json.loads((sub / "draft_content.json").read_text(encoding="utf-8"))
        assert stub["materials"]["drafts"][0]["id"] == e["id"]            # stub referencia a si mesmo
    assert composto.verifica(d, pasta) == []
    # raiz: 1 segmento (Corpo) acelerado 1.15x
    seg = d["tracks"][0]["segments"][0]
    assert seg["speed"] == 1.15 and seg["extra_material_refs"][0] in {e["id"] for e in drafts}
    corpo = next(e for e in drafts if e["id"] == seg["extra_material_refs"][0])["draft"]
    assert seg["target_timerange"]["duration"] == round(corpo["duration"] / 1.15)
    # placeholders de composto
    for dd in [d] + [e["draft"] for e in drafts]:
        for v in dd["materials"]["videos"]:
            if v.get("extra_type_option") == 2: assert v["path"] == ""
    idx = json.loads((Path(raiz_capcut) / "root_meta_info.json").read_text(encoding="utf-8"))
    assert r["nome"] in [x["draft_name"] for x in idx["all_draft_store"]]
    assert r["enfases"] == 2 and r["pedacos"] >= 3


def test_fontes_do_catalogo_e_enfase_vermelha(raiz_capcut, analise):
    r = gera(raiz_capcut, analise)
    d, _ = carrega(raiz_capcut, r["nome"])
    textos = [m for e in d["materials"]["drafts"] for m in e["draft"]["materials"].get("texts", [])]
    ids = {m["font_resource_id"] for m in textos}
    assert ids <= {f["id"] for f in composto.FONTES.values()}             # nenhuma fonte local/inexistente
    soco = [m for m in textos if "[nunca]" in m["content"]]
    assert soco and json.loads(soco[0]["content"])["styles"][0]["fill"]["content"]["solid"]["color"] == [1, 0, 0]
    assert all("Users/USUARIO" not in m["font_path"] for m in textos)     # nada apontando pra maquina do molde


def test_zoom_no_segmento_do_composto_de_cortes_e_musica(raiz_capcut, analise, tmp_path):
    musica = tmp_path / "trilha.mp3"
    import subprocess
    subprocess.run([audio.ffmpeg_bin(), "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=4", str(musica)], check=True)
    r = gera(raiz_capcut, analise, zoom=1.44, musica=str(musica), volume=0.068)
    d, _ = carrega(raiz_capcut, r["nome"])
    corpo = next(e["draft"] for e in d["materials"]["drafts"] if e["id"] == d["tracks"][0]["segments"][0]["extra_material_refs"][0])
    principal = corpo["tracks"][0]["segments"]
    assert len(principal) == 1 and principal[0]["clip"]["scale"]["x"] == 1.44                # zoom num controle so
    aud = [t for t in d["tracks"] if t["type"] == "audio"][0]["segments"][0]
    assert aud["volume"] == 0.068 and aud["target_timerange"]["duration"] <= 4_000_000 + 1000


def test_checklist_do_projeto_pega_estrutura_quebrada(raiz_capcut, analise, monkeypatch):
    ref = {}
    real = composto.monta
    def espiao(*a, **k):
        ref["r"] = real(*a, **k); return ref["r"]
    monkeypatch.setattr(composto, "monta", espiao)
    gera(raiz_capcut, analise)
    raiz, compostos = ref["r"]
    assert composto.verifica(raiz) == []
    # 1. bug da "Midia perdida": entrada de composto dentro de outro composto
    q = copy.deepcopy(raiz); q["materials"]["drafts"][0]["draft"]["materials"]["drafts"] = [copy.deepcopy(q["materials"]["drafts"][1])]
    assert any("Mídia perdida" in e for e in composto.verifica(q))
    # 2. segmento de composto apontando pra entrada que nao existe na raiz
    q = copy.deepcopy(raiz); q["materials"]["drafts"] = q["materials"]["drafts"][:1]
    assert composto.verifica(q)
    # 3. faixa de estilo menor que o texto
    q = copy.deepcopy(raiz)
    leg = next(e for e in q["materials"]["drafts"] if e["draft"]["materials"].get("texts"))
    m = leg["draft"]["materials"]["texts"][0]; c = json.loads(m["content"]); c["styles"][0]["range"] = [0, 1]; m["content"] = json.dumps(c)
    assert any("sem estilo" in e for e in composto.verifica(q))
    # 4. sobreposicao por altura Y direto no JSON
    q = copy.deepcopy(raiz)
    leg = next(e for e in q["materials"]["drafts"] if e["draft"]["materials"].get("texts"))
    ss = [s for t in leg["draft"]["tracks"] for s in t["segments"]]
    ss[1]["clip"]["transform"]["y"] = ss[0]["clip"]["transform"]["y"]
    ss[1]["target_timerange"]["start"] = ss[0]["target_timerange"]["start"]
    assert any("mesma altura" in e for e in composto.verifica(q))
    # 5. pasta subdraft faltando no disco
    assert any("falta subdraft" in e for e in composto.verifica(raiz, Path(raiz_capcut) / "nao-existe"))


def test_verificacao_falha_nao_grava_nada(raiz_capcut, analise, monkeypatch):
    monkeypatch.setattr(composto, "verifica", lambda raiz, pasta=None: ["problema forçado"])
    antes = set(os.listdir(raiz_capcut))
    with pytest.raises(capcut.ErroProjeto, match="NÃO foi gravado"):
        gera(raiz_capcut, analise)
    assert set(os.listdir(raiz_capcut)) == antes


def test_gancho_tira_a_abertura(raiz_capcut, analise):
    todas = gera(raiz_capcut, analise, nome="a")
    segunda = next(p for p in analise["mantidas"] if p["a"] >= 4.5)
    corta = gera(raiz_capcut, analise, nome="b", inicio=segunda["a"], texto="você [nunca] tentou isso fim")
    assert corta["depois"] < todas["depois"] - 2.0
