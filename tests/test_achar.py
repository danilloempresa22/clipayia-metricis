"""Cortes Fase 3: achar os assuntos (IA falsa, sem custo), costura, validacao, filtro por tipo, cache e gerar todos."""
import json
import pytest
from clipay import achar, rosto, transcricao

CFG = dict(achar.config(), janela_s=200, sobreposicao_s=40, minimo_s=30, teto_s=240, piso_forca=50, paralelo=1)


def podcast():
    """frases de 5 s: 1-10 abertura; 11-30 a historia do tiro (desfecho em 30); 31 transicao; 32-60 outro assunto"""
    tx = {11: "Cara, um dia eu levei um tiro.", 30: "E foi assim que eu sai vivo daquela.",
          31: "Mudando de assunto, me fala do seu negocio.", 32: "Entao, o negocio comecou em 2019."}
    fs = [{"id": i, "ini": (i - 1) * 5.0, "fim": (i - 1) * 5.0 + 4.6, "texto": tx.get(i, f"frase {i}.")} for i in range(1, 61)]
    pausas = [[0.0, 0.0]] + [[f["fim"], f["fim"] + 0.4] for f in fs]
    return {"frases": fs, "pausas": pausas}


class IAFalsa:
    """responde por janela (identificada pelo primeiro id dela) e conta as chamadas"""
    def __init__(self, por_primeiro_id):
        self.r, self.chamadas = por_primeiro_id, 0

    def __call__(self, texto, cfg):
        self.chamadas += 1
        primeiro = int(texto.split(" | ")[0])
        return json.dumps({"assuntos": self.r.get(primeiro, [])}), {"entrada": len(texto) // 4, "saida": 50}


def A(i, j, cats=("historia",), f=80):
    return {"ini_id": i, "fim_id": j, "categorias": list(cats), "forca": f, "titulo": "t", "motivo": "m"}


@pytest.fixture(autouse=True)
def cache_temp(tmp_path, monkeypatch):
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: tmp_path)


def test_janelas_com_sobreposicao():
    js = achar.janelas(podcast()["frases"], 200, 40)
    assert (js[0][0]["id"], js[0][-1]["id"]) == (1, 40) and js[-1][-1]["id"] == 60
    for a, b in zip(js, js[1:]):
        assert b[0]["id"] <= a[-1]["id"]                                  # tem frase em comum


def test_caso_do_tiro_comeca_na_abertura_termina_no_desfecho_sem_transicao():
    js = achar.janelas(podcast()["frases"], 200, 40)
    ia = IAFalsa({js[0][0]["id"]: [A(11, 31, ("historia", "emocional"), 92)]})
    r = achar.achar_cortes(podcast(), cfg=CFG, chamar=ia)
    c = r["cortes"][0]
    assert (c["ini_id"], c["fim_id"]) == (11, 30)                         # transicao (31) saiu
    assert c["primeira"].startswith("Cara, um dia eu levei um tiro") and c["ultima"].startswith("E foi assim")
    assert c["ini"] == pytest.approx(49.95)                              # logo antes da 1a palavra
    assert c["fim"] == pytest.approx(149.6 + 0.3)                         # fim da fala + 0,3 s, dentro da pausa
    assert c["tipo"] == "historia" and c["numero"] == 1 and not c["longo"]


def test_assunto_que_cruza_a_borda_vira_um_so_e_vai_ate_o_desfecho():
    js = achar.janelas(podcast()["frases"], 200, 40)
    ult0 = js[0][-1]["id"]
    ia = IAFalsa({js[0][0]["id"]: [A(11, ult0, f=70)],                    # janela 1 viu so o comeco (encostado na borda)
                  js[1][0]["id"]: [A(js[1][0]["id"], 45, f=85)]})          # janela 2 viu o resto
    c = achar.achar_cortes(podcast(), cfg=CFG, chamar=ia)["cortes"]
    assert len(c) == 1 and (c[0]["ini_id"], c[0]["fim_id"]) == (11, 45) and c[0]["forca"] == 85


def test_respostas_ruins_sao_corrigidas_ou_descartadas():
    js = achar.janelas(podcast()["frases"], 200, 40)
    ia = IAFalsa({js[0][0]["id"]: [A(11, 999), A(500, 520), A(2, 4, f=90),     # id inexistente / curto demais
                                   A(11, 30, f=60), A(20, 36, ("polemico",), f=75),   # se cruzam: fica o mais forte
                                   A(41, 52, ("insight",), f=40)]})                  # abaixo do piso
    c = achar.achar_cortes(podcast(), cfg=CFG, chamar=ia)["cortes"]
    assert [(x["ini_id"], x["fim_id"], x["tipo"]) for x in c] == [(20, 36, "polemico")]
    for x, y in zip(c, c[1:]):
        assert x["fim"] <= y["ini"]


def test_longo_inteiro_e_nunca_cortado():
    ia = IAFalsa({1: [A(1, 60, f=88)]})
    c = achar.achar_cortes(podcast(), cfg=dict(CFG, janela_s=1000), chamar=ia)["cortes"]
    assert c[0]["longo"] and c[0]["fim_id"] == 60 and c[0]["duracao"] > 240


def test_tipos_filtram_sem_nova_chamada_e_repetir_nao_chama_de_novo():
    js = achar.janelas(podcast()["frases"], 200, 40)
    ia = IAFalsa({js[0][0]["id"]: [A(11, 30, ("historia",), 90)], js[1][0]["id"]: [A(33, 50, ("polemico", "insight"), 70)]})
    todos = achar.achar_cortes(podcast(), cfg=CFG, chamar=ia)
    n = ia.chamadas
    so_pol = achar.achar_cortes(podcast(), tipos=["polemico"], cfg=CFG, chamar=ia)
    so_cons = achar.achar_cortes(podcast(), tipos=["insight"], cfg=dict(CFG, teto_s=60, piso_forca=60), chamar=ia)
    assert ia.chamadas == n                                               # tipos, teto e piso: nenhuma chamada nova
    assert len(todos["cortes"]) == 2 and [c["tipo"] for c in so_pol["cortes"]] == ["polemico"]
    assert len(so_cons["cortes"]) == 1 and so_cons["cortes"][0]["longo"]   # 90 s > teto de 60 s
    with pytest.raises(ValueError):
        achar.achar_cortes(podcast(), tipos=[], cfg=CFG, chamar=ia)


def test_sem_ia_mensagem_clara_com_modo_manual():
    with pytest.raises(achar.SemIA, match="modo manual"):
        achar.achar_cortes(podcast(), cfg=dict(CFG, url="http://127.0.0.1:9", tempo_limite_s=2))

    def fora(texto, cfg):
        raise achar.SemIA("A IA está fora do ar. " + achar.MSG_MANUAL)
    with pytest.raises(achar.SemIA, match="modo manual"):
        achar.achar_cortes(podcast(), cfg=CFG, chamar=fora)


def test_interpreta_tolera_lixo():
    assert achar.interpreta("nada") == []
    r = achar.interpreta('ok: {"assuntos": [{"ini_id": "3", "fim_id": 9, "categorias": ["historia", "xx"], "forca": 140}]} fim')
    assert r == [{"ini_id": 3, "fim_id": 9, "categorias": ["historia"], "forca": 100, "titulo": "", "motivo": "",
                  "papel_ini": "", "papel_fim": ""}]


def test_nome_do_corte():
    c = {"numero": 3, "tipo": "historia", "longo": True}
    assert achar.nome_corte("C:/x/Qual foi o momento? - Ale EP6.mp4", c) == "Qual foi o momento - Ale EP6 - corte 03 - Historia - longo"


def test_gera_todos_um_projeto_por_corte(video_horizontal, raiz_capcut, monkeypatch):
    monkeypatch.setattr(rosto, "posicao_2d", lambda v, a, b: (0.0, 0.0, False))
    lista = [{"numero": 1, "tipo": "historia", "longo": False, "ini": 0.5, "fim": 4.0},
             {"numero": 2, "tipo": "insight", "longo": False, "ini": 4.5, "fim": 9.5},
             {"numero": 3, "tipo": "polemico", "longo": False, "ini": 8.0, "fim": 50.0}]    # fora do video: erro so dele
    vistos = []
    r = achar.gera_todos(video_horizontal, lista, raiz_capcut, progresso=lambda k, n, c: vistos.append(k))
    assert r["criados"] == ["horizontal - corte 01 - Historia", "horizontal - corte 02 - Insight"]
    assert [n for n, _ in r["erros"]] == [3] and vistos == [0, 1, 2, 3]
    for nome in r["criados"]:
        assert (raiz_capcut / nome / "draft_content.json").exists()


def test_corte_nao_comeca_em_resposta_curta():
    pc = podcast(); pc["frases"][10]["texto"] = "Com certeza."           # id 11
    pc["frases"][11]["texto"] = "Nossa, demais!"                         # id 12
    js = achar.janelas(pc["frases"], 200, 40)
    c = achar.achar_cortes(pc, cfg=CFG, chamar=IAFalsa({js[0][0]["id"]: [A(11, 30)]}))["cortes"]
    assert c[0]["ini_id"] == 13
    assert not achar.MULETA.match("Com certeza, eu levei um tiro.")


UMA = dict(CFG, janela_s=1000)                                          # uma janela so: ids 1-60


def com_papeis():
    """1-6 apresentador abrindo (com 'se inscrever'); 7-9 boas-vindas do convidado; 10 1a pergunta do apresentador;
    11-30 a historia do convidado (20 = 'Hum.' do apresentador); 31 nova pergunta; 32-45 convidado;
    46-50 apresentador com uma sacada e depois pergunta; 51-60 a resposta do convidado"""
    pc = podcast(); fs = pc["frases"]
    for f in fs: f["papel"] = "convidado"
    for i in list(range(1, 7)) + [10, 20, 31] + list(range(46, 51)):
        fs[i - 1]["papel"] = "apresentador"
    fs[3]["texto"] = "Não deixa de se inscrever e deixar o seu like."
    fs[6]["texto"] = "Valeu pelo convite, meu irmão, o que eu convido você que está assistindo é abrir a cabeça."
    fs[9]["texto"] = "Qual foi o momento mais difícil da sua vida?"
    fs[19].update(texto="Hum.", fim=fs[19]["ini"] + 0.8)                # reacao curta: pode ficar no corte
    fs[30]["texto"] = "E depois disso, como ficou a sua relação com a família?"
    fs[46]["texto"] = "A rede social não é feita para vender, é relacionamento."
    fs[49]["texto"] = "Como o empresário constrói um bom funil de social selling?"
    return pc


def test_abre_na_resposta_do_convidado_e_a_nova_pergunta_encerra():
    pc = com_papeis()
    c = achar.achar_cortes(pc, cfg=UMA, chamar=IAFalsa({1: [A(10, 36, f=90)]}))["cortes"]
    assert (c[0]["ini_id"], c[0]["fim_id"]) == (11, 30)                  # sem a pergunta (10) e parando antes da 31
    assert c[0]["parte_apresentador"] == pytest.approx(0.8 / (149.6 - 50.0), abs=0.01)   # o "Hum." ficou dentro


def test_abertura_do_episodio_nao_vira_corte():
    pc = com_papeis()
    c = achar.achar_cortes(pc, cfg=dict(UMA, minimo_s=5), chamar=IAFalsa({1: [A(1, 9, f=90), A(7, 9, f=90)]}))["cortes"]
    assert c == []                                                        # cumprimento, like e boas-vindas


def test_sacada_e_pergunta_do_apresentador_ficam_fora():
    pc = com_papeis()
    c = achar.achar_cortes(pc, cfg=UMA, chamar=IAFalsa({1: [A(46, 60, ("insight",), 90)]}))["cortes"]
    assert (c[0]["ini_id"], c[0]["fim_id"]) == (51, 60) and c[0]["tipo"] == "insight"


def test_apresentador_falando_demais_descarta():
    pc = com_papeis()
    for i in (34, 36, 38, 40, 42):                                       # 5 "falas curtas" dele no meio: 5 x 2,5 s
        f = pc["frases"][i - 1]; f.update(papel="apresentador", texto="É verdade.", fim=f["ini"] + 2.5)
    c = achar.achar_cortes(pc, cfg=UMA, chamar=IAFalsa({1: [A(32, 45, f=90)]}))["cortes"]
    assert c == []                                                        # 12,5 s de 69,6 s = 18% > 15%
    c = achar.achar_cortes(pc, cfg=dict(UMA, max_apresentador=0.25), chamar=IAFalsa({1: [A(32, 45, f=90)]}))["cortes"]
    assert len(c) == 1                                                    # o limite e' configuravel


def test_regua_de_acerto_por_frase():
    pc = com_papeis(); fs = pc["frases"]
    ouro = {"bons": [{"inicio": "0:00:51", "fim": "0:02:29", "tipos": ["historia"]},     # frases 11-30
                     {"inicio": "0:04:11", "fim": "0:04:59", "tipos": ["insight"]}],      # frases 51-60
            "ruins": [{"inicio": "0:00:00", "fim": "0:00:44", "motivo": "abertura"}]}
    cortes = [{"numero": 1, "ini_id": 12, "fim_id": 30, "ini": 55.0, "fim": 149.9},        # 1 frase depois: acerta
              {"numero": 2, "ini_id": 51, "fim_id": 55, "ini": 250.0, "fim": 274.6}]       # parou 5 frases antes
    r = achar.compara_ouro(cortes, fs, ouro)
    assert r["bons"][0]["acertou"] and (r["bons"][0]["dist_ini"], r["bons"][0]["dist_fim"]) == (1, 0)
    assert not r["bons"][1]["acertou"] and r["bons"][1]["termina_antes"]
    assert r["acertos"] == 1 and r["ruins"][0]["cortes"] == [] and [c["numero"] for c in r["extras"]] == [2]


def test_pergunta_curta_do_apresentador_tambem_encerra():
    pc = com_papeis(); f = pc["frases"][24]                              # id 25, no meio da historia
    f.update(papel="apresentador", texto="E aí, o que você fez?", fim=f["ini"] + 1.2)
    c = achar.achar_cortes(pc, cfg=UMA, chamar=IAFalsa({1: [A(11, 30, f=90)]}))["cortes"]
    assert (c[0]["ini_id"], c[0]["fim_id"]) == (11, 24)
    assert achar.fim_da_abertura(pc["frases"], UMA) == pc["frases"][9]["ini"]   # abertura ate a 1a pergunta (id 10)


def test_assunto_que_atravessa_a_pergunta_vira_duas_respostas():
    pc = com_papeis()                                                     # pergunta do apresentador no id 31
    c = achar.achar_cortes(pc, cfg=UMA, chamar=IAFalsa({1: [A(11, 45, f=90)]}))["cortes"]
    assert [(x["ini_id"], x["fim_id"]) for x in c] == [(11, 30), (32, 45)]
