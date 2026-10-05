"""Inicio: a caixa confere o video (mensagens claras), acha o arquivo arrastado sem copiar, e a faixa de cortes
recentes mostra so projetos de Cortes que ainda existem, mais novos primeiro (sem nada inventado)."""
import json, shutil
from clipay import fluxo_cortes, previa, servidor, transcricao


def test_video_do_inicio_mensagens_claras(video_horizontal, video_mudo, tmp_path):
    ok = servidor.video_do_inicio(str(video_horizontal))
    assert ok["nome"] == "horizontal.mp4" and ok["duracao"] > 9 and ok["tamanho"] > 0
    assert "não está mais" in servidor.video_do_inicio(str(tmp_path / "sumiu.mp4"))["erro"]
    txt = tmp_path / "nota.txt"; txt.write_text("oi")
    assert "não é um vídeo" in servidor.video_do_inicio(str(txt))["erro"]
    falso = tmp_path / "quebrado.mp4"; falso.write_bytes(b"isto nao e video")
    assert "Não consegui ler" in servidor.video_do_inicio(str(falso))["erro"]
    assert "não tem som" in servidor.video_do_inicio(str(video_mudo))["erro"]
    assert "erro" not in servidor.video_do_inicio(str(video_mudo), precisa_audio=False)   # iPad e Rotina aceitam


def test_localiza_o_original_pelo_nome_e_tamanho(tmp_path, monkeypatch, video_horizontal):
    casa = tmp_path / "casa"; (casa / "Downloads" / "podcasts").mkdir(parents=True)
    alvo = casa / "Downloads" / "podcasts" / "ep6.mp4"; shutil.copy(video_horizontal, alvo)
    monkeypatch.setattr(servidor.Path, "home", classmethod(lambda cls: casa))
    monkeypatch.setenv("OneDrive", str(tmp_path / "sem_onedrive"))
    assert servidor.localiza("ep6.mp4", alvo.stat().st_size) == str(alvo)
    assert servidor.localiza("ep6.mp4", 123) is None                       # outro tamanho: nao e' o mesmo arquivo
    assert servidor.localiza("../ep6.mp4", alvo.stat().st_size) is None    # so nome, nada de caminho


def test_recentes_so_cortes_que_existem_mais_novos_primeiro(tmp_path, monkeypatch, video_horizontal):
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: tmp_path)
    raiz = tmp_path / "capcut"; raiz.mkdir()
    for n in (1, 2, 3):
        nome = f"horizontal - corte {n:02d} - Historia"; (raiz / nome).mkdir()
        fluxo_cortes.anota_recente({"projeto": nome, "nome": nome, "numero": n}, {"ini": 0.5, "fim": 9.0 + n * 0.1},
                                   str(video_horizontal), 20.0 + n, 1.13)
    shutil.rmtree(raiz / "horizontal - corte 02 - Historia")             # apagado no CapCut: some da faixa
    r = fluxo_cortes.recentes(raiz)
    assert [x["numero"] for x in r] == [3, 1] and all(not x["tem_previa"] for x in r)
    k = r[0]["previa"]; (previa.pasta() / f"{k}_curto.mp4").write_bytes(b"mp4")   # o preview do Gerar existe no cache
    assert fluxo_cortes.recentes(raiz)[0]["tem_previa"] and fluxo_cortes.arquivo_previa_por_chave(k)
    assert fluxo_cortes.arquivo_previa_por_chave("../../segredo") is None
    assert len(fluxo_cortes.recentes(raiz, n=1)) == 1


def test_recentes_vazio_e_comeco_pela_ultima_geracao(tmp_path, monkeypatch):
    monkeypatch.setattr(transcricao, "pasta_dados", lambda: tmp_path)
    raiz = tmp_path / "capcut"; raiz.mkdir()
    assert fluxo_cortes.recentes(raiz) == []                              # sem nada: a secao some
    (raiz / "ep - corte 01 - Insight").mkdir()
    (tmp_path / "geracao_cortes.json").write_text(json.dumps({"chave": "x", "linhas": [
        {"numero": 1, "nome": "ep - corte 01 - Insight", "projeto": "ep - corte 01 - Insight", "estado": "pronto"},
        {"numero": 2, "nome": "ep - corte 02 - Insight", "projeto": None, "estado": "erro"}]}), encoding="utf-8")
    r = fluxo_cortes.recentes(raiz)
    assert [x["numero"] for x in r] == [1] and r[0]["previa"] is None and r[0]["duracao"] is None
