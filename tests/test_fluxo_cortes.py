"""Tela Cortes (Fase 4): gerar todos (um corte que falha nao para os outros; refazer so os que falharam; cancelar)
e a confirmacao do apresentador so na hora certa. Montador e gravacao falsos: nada toca o CapCut."""
import threading
import pytest
from clipay import cortes, fluxo_cortes, previa, transcricao


def lista(n=3):
    return [{"numero": i, "tipo": "historia", "ini": 10.0 * i, "fim": 10.0 * i + 30, "duracao": 30.0, "longo": False}
            for i in range(1, n + 1)]


@pytest.fixture
def falsos(tmp_path, monkeypatch, video_horizontal):
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: tmp_path)
    estado = {"falha": {2}, "gravados": []}

    def monta(video, ini, fim, **k):
        if int(ini // 10) in estado["falha"]:
            raise RuntimeError("Não achei fala nesse trecho do vídeo.")
        return {"ini": ini, "efeito": k.get("efeito"), "vel": k["mod"]["composto"]["velocidade"]}
    monkeypatch.setattr(cortes, "monta", monta)
    monkeypatch.setattr(previa, "edicao", lambda video, ini, fim, mod=None: {"ini": ini})
    monkeypatch.setattr(cortes, "grava", lambda raiz, nome, r, capa=None: estado["gravados"].append((nome, r)) or nome)
    fluxo_cortes.GERACAO["job"] = None
    monkeypatch.setattr(fluxo_cortes, "_arq_geracao", lambda: tmp_path / "geracao_cortes.json")
    return estado


def espera(job):
    job["thread"].join(30)
    return fluxo_cortes.estado_geracao()


def test_um_corte_que_falha_nao_para_os_outros_e_refaz_so_ele(falsos, video_horizontal, tmp_path):
    g = espera(fluxo_cortes.gera(str(video_horizontal), lista(), tmp_path, efeito=False, velocidade=False))
    assert [l["estado"] for l in g["linhas"]] == ["pronto", "erro", "pronto"]
    assert "fala" in g["linhas"][1]["erro"] and g["linhas"][0]["nome"] == "horizontal - corte 01 - Historia"
    assert all(r["efeito"] is False and r["vel"] == 1.0 for _, r in falsos["gravados"])     # os Ajustes chegam no montador
    falsos["falha"].clear(); falsos["gravados"].clear()
    g = espera(fluxo_cortes.gera(str(video_horizontal), lista(), tmp_path, efeito=False, velocidade=False, so=[2]))
    assert [l["estado"] for l in g["linhas"]] == ["pronto", "pronto", "pronto"]
    assert [n for n, _ in falsos["gravados"]] == ["horizontal - corte 02 - Historia"]   # so o que tinha falhado


def test_cancelar_para_entre_um_corte_e_outro(falsos, video_horizontal, tmp_path, monkeypatch):
    falsos["falha"].clear(); trava = threading.Event()
    original = cortes.monta

    def lento(video, ini, fim, **k):
        trava.wait(5); return original(video, ini, fim, **k)
    monkeypatch.setattr(cortes, "monta", lento)
    job = fluxo_cortes.gera(str(video_horizontal), lista(), tmp_path)
    for _ in range(500):                                        # o 1o corte ja esta sendo montado
        if job["linhas"][0]["estado"] == "montando": break
        threading.Event().wait(0.01)
    fluxo_cortes.cancela_geracao(); trava.set()
    g = espera(job)
    assert g["linhas"][0]["estado"] == "pronto" and {l["estado"] for l in g["linhas"][1:]} == {"cancelado"}
    with pytest.raises(fluxo_cortes.Erro):                      # nao deixa gerar dois ao mesmo tempo
        fluxo_cortes.GERACAO["job"]["parado"] = False
        fluxo_cortes.gera(str(video_horizontal), lista(2), tmp_path)
    assert fluxo_cortes.gera(str(video_horizontal), lista(), tmp_path) is fluxo_cortes.GERACAO["job"]   # a mesma: devolve a que roda
    fluxo_cortes.GERACAO["job"]["parado"] = True


def test_corte_digitado_a_mao_sem_tipo(falsos, video_horizontal, tmp_path):
    falsos["falha"].clear()
    c = [{"numero": 1, "tipo": None, "ini": 10.0, "fim": 40.0, "longo": False}]
    g = espera(fluxo_cortes.gera(str(video_horizontal), c, tmp_path))
    assert g["linhas"][0]["nome"] == "horizontal - corte 01" and g["linhas"][0]["estado"] == "pronto"


def test_confirmar_o_apresentador_so_depois_das_vozes():
    fluxo_cortes.ANALISE["job"] = None
    with pytest.raises(fluxo_cortes.Erro):
        fluxo_cortes.confirma("B")
    fluxo_cortes.ANALISE["job"] = {"fase": "apresentador", "transc": {"vozes": ["A", "B"]}}
    with pytest.raises(fluxo_cortes.Erro, match="voz"):
        fluxo_cortes.confirma("C")
    fluxo_cortes.ANALISE["job"] = None


def test_app_fechou_no_meio_continua_sem_duplicar(falsos, video_horizontal, tmp_path, monkeypatch):
    def grava(raiz, nome, r, capa=None):
        (raiz / nome).mkdir(parents=True); falsos["gravados"].append((nome, r)); return nome
    monkeypatch.setattr(cortes, "grava", grava)
    espera(fluxo_cortes.gera(str(video_horizontal), lista(), tmp_path))     # 1 e 3 prontos, 2 falhou
    fluxo_cortes.GERACAO["job"] = None                                       # o app fechou e abriu de novo
    falsos["falha"].clear(); falsos["gravados"].clear()
    g = espera(fluxo_cortes.gera(str(video_horizontal), lista(), tmp_path))
    assert [l["estado"] for l in g["linhas"]] == ["pronto"] * 3
    assert [n for n, _ in falsos["gravados"]] == ["horizontal - corte 02 - Historia"]   # so o que faltava
