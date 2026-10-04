"""Passo Gerar: preview de cada corte (mesma edicao do projeto, render leve) e a fila de previews (os da tela
primeiro, no maximo 2 ao mesmo tempo, erro so do cartao que falhou, cancelar, cache)."""
import threading, time
import pytest
from clipay import audio, cortes, fluxo_cortes, previa, rosto, transcricao


@pytest.fixture
def dados(tmp_path, monkeypatch):
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: tmp_path)
    monkeypatch.setattr(rosto, "posicao_2d", lambda v, a, b: (0.0, 0.2, True))
    return tmp_path


def info_mp4(p):
    import subprocess, re
    t = subprocess.run([audio.ffmpeg_bin(), "-hide_banner", "-i", str(p)], capture_output=True).stderr.decode(errors="ignore")
    d = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", t)
    return int(d[1]) * 3600 + int(d[2]) * 60 + float(d[3]), "Audio:" in t, re.search(r"\b(\d{2,5})x(\d{2,5})\b", t.split("Video:")[1])[0]


def test_preview_usa_a_mesma_edicao_do_projeto(dados, video_horizontal):
    ed = previa.edicao(video_horizontal, 0.5, 9.5)
    r = cortes.monta(video_horizontal, 0.5, 9.5, ed=ed)
    segs = r["draft"]["materials"]["drafts"][0]["draft"]["tracks"][0]["segments"]
    assert [s["source_timerange"]["start"] for s in segs] == [audio.quadro_us(a) for a, *_ in ed["pcs"]]   # mesmos pedacos
    assert previa.edicao(video_horizontal, 0.5, 9.5) == ed                                              # do cache
    curto = previa.render(video_horizontal, ed, dados / "c.mp4", limite_s=3)
    dur, som, tam = info_mp4(curto)
    assert dur == pytest.approx(3.0, abs=0.15) and not som and tam == "270x480"
    inteiro = previa.render(video_horizontal, ed, dados / "i.mp4", som=True)
    dur, som, _ = info_mp4(inteiro)
    assert som and dur == pytest.approx(previa.duracao_final(ed, 1.13), abs=0.2)                      # o corte inteiro, 1,13x
    assert r["draft"]["duration"] / 1e6 == pytest.approx(dur, abs=0.2)                                # = duracao do projeto


def test_cancelar_um_render_nao_deixa_arquivo_pela_metade(dados, video_horizontal):
    ed = previa.edicao(video_horizontal, 0.5, 9.5)
    with pytest.raises(previa.Cancelado):
        previa.render(video_horizontal, ed, dados / "x.mp4", cancelado=lambda: True)
    assert not list(dados.glob("x*.mp4")) and not list(previa.pasta().glob("*.parcial.mp4"))


def lista(n=4):
    return [{"numero": i, "tipo": "historia", "ini": 0.5, "fim": 9.0 + i * 0.1} for i in range(1, n + 1)]


@pytest.fixture
def fila(dados, monkeypatch, video_horizontal):
    feitos, ao_mesmo_tempo, trava = [], {"agora": 0, "max": 0}, threading.Lock()
    falha = set()

    def render(video, ed, destino, *a, **k):
        with trava:
            ao_mesmo_tempo["agora"] += 1; ao_mesmo_tempo["max"] = max(ao_mesmo_tempo["max"], ao_mesmo_tempo["agora"])
        time.sleep(0.15)
        with trava:
            ao_mesmo_tempo["agora"] -= 1
        n = round((k.get("limite_s") and 0) or 0)
        if destino.name in falha:
            raise RuntimeError("Não consegui ler o vídeo nesse trecho.")
        destino.write_bytes(b"mp4"); feitos.append(destino.name)
        return destino
    monkeypatch.setattr(previa, "render", render)
    monkeypatch.setattr(previa, "edicao", lambda v, a, b, mod=None: {"pcs": [[a, b, False]]})
    fluxo_cortes.PREVIAS.update(chave=None)
    fluxo_cortes.prepara_previas(str(video_horizontal), lista())
    return {"feitos": feitos, "max": ao_mesmo_tempo, "falha": falha}


def espera_parar():
    for _ in range(200):
        P = fluxo_cortes.PREVIAS
        if not (P["trabalhando"] or P["fila"] or P["trabalhando_inteiro"] or P["fila_inteiro"]): return
        time.sleep(0.05)


def test_fila_os_da_tela_primeiro_no_maximo_2_e_erro_so_do_cartao(fila):
    fila["falha"].add(fluxo_cortes._arq_previa(3, "curto").name)
    fluxo_cortes.pede_previas([3, 4])                   # o que esta na tela
    fluxo_cortes.pede_previas([1])                     # rolou pro topo: vai pra frente
    espera_parar()
    e = fluxo_cortes.estado_previas()["previas"]
    assert e["1"]["curto"] == e["4"]["curto"] == "pronto" and e["2"]["curto"] == "nada"   # o 2 nunca apareceu: nao renderiza
    assert e["3"]["curto"] == "erro" and "ler o vídeo" in e["3"]["erro"]
    assert fila["max"]["max"] <= fluxo_cortes.PARALELO_PREVIAS
    fila["falha"].clear()
    fluxo_cortes.pede_previas([3])                     # sem "de novo": erro fica
    espera_parar(); assert fluxo_cortes.estado_previas()["previas"]["3"]["curto"] == "erro"
    fluxo_cortes.pede_previas([3], de_novo=True)       # "Tentar de novo" so desse cartao
    espera_parar(); assert fluxo_cortes.estado_previas()["previas"]["3"]["curto"] == "pronto"
    assert fluxo_cortes.arquivo_previa(3, "curto").exists() and fluxo_cortes.arquivo_previa(2, "curto") is None


def test_cache_volta_na_hora_e_cancelar_esvazia_a_fila(fila, video_horizontal):
    fluxo_cortes.pede_previas([1, 2]); espera_parar()
    fluxo_cortes.PREVIAS.update(chave=None)                                   # app reaberto: so o cache em disco
    e = fluxo_cortes.prepara_previas(str(video_horizontal), lista())["previas"]
    assert e["1"]["curto"] == e["2"]["curto"] == "pronto" and e["3"]["curto"] == "nada"
    with fluxo_cortes._COND:                                                   # 2 na fila, ninguem trabalhando ainda
        fluxo_cortes.PREVIAS["fila"] = [(3, "curto"), (4, "curto")]
        for n in (3, 4): fluxo_cortes.PREVIAS["estado"][n]["curto"] = "fila"
    fluxo_cortes.cancela_previas()
    e = fluxo_cortes.estado_previas()["previas"]
    assert e["3"]["curto"] == e["4"]["curto"] == "nada" and not fluxo_cortes.PREVIAS["fila"]


def test_corte_inteiro_tem_vaga_propria(fila):
    fluxo_cortes.pede_previas([1, 2, 3, 4])            # a grade ocupa as 2 vagas
    fluxo_cortes.pede_previas([2], "inteiro")         # clicou: nao espera a grade
    espera_parar()
    e = fluxo_cortes.estado_previas()["previas"]
    assert e["2"]["inteiro"] == "pronto" and all(e[str(n)]["curto"] == "pronto" for n in range(1, 5))
    assert fila["max"]["max"] <= fluxo_cortes.PARALELO_PREVIAS + 1
