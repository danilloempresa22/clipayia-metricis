"""Apresentador + iPad: sincronia, cortes que nunca cortam palavra, compostos (iPad + pessoa -> Video -> raiz),
legenda, velocidade, musica, headline e verificacao."""
import copy, json, os
from pathlib import Path
import pytest
from clipay import audio, capcut, composto, ipad, palavras, processa, transcricao


def test_janela_da_sincronia_positiva_negativa_e_sem_cruzamento():
    assert ipad.janela(9.1, 204.7, 209.6) == (0.0, 9.1, pytest.approx(200.5))     # projeto 0930: iPad comecou 9,1 s antes
    sp, si, comum = ipad.janela(-1.5, 60, 60)                                        # a pessoa comecou antes
    assert (sp, si, comum) == (1.5, 0.0, 58.5)
    with pytest.raises(capcut.ErroProjeto, match="quase não se cruzam"):
        ipad.janela(59.5, 60, 60)


def test_passo_de_um_quadro_alcanca_o_ajuste_do_0930():
    quadros = round(9.1 / ipad.QUADRO)
    assert abs(quadros * ipad.QUADRO - 9.1) < 1 / 60                                  # margem de 1 quadro do original (60 fps)


def test_cortes_nunca_cortam_palavra_e_respeitam_a_intensidade(video_vertical):
    x = audio.pcm(video_vertical)                        # tom em 0-3 s, 4,5-7,5 s e 9-10 s (pausas de 1,5 s)
    # palavra "sussurrada" no meio da pausa: o audio nao ve, a transcricao ve -> nao pode sumir
    pal = [{"t": "baixinho", "a": 3.5, "b": 3.9}]
    for k in ipad.INTENSIDADES:
        keep = ipad.cortes(x, pal, k)
        assert any(a <= 3.5 and 3.9 <= b for a, b, _ in keep), k
    leve, forte = ipad.cortes(x, [], "leve"), ipad.cortes(x, [], "forte")
    assert sum(b - a for a, b, _ in leve) >= sum(b - a for a, b, _ in forte)
    assert len(forte) >= 2                                                           # pausas de 1,5 s viram corte
    pausa, pre, pos = ipad.INTENSIDADES["media"]
    k = ipad.cortes(x, [], "media")
    assert k[0][1] >= 3.0 + pos - 0.02                                                # folga depois da fala


@pytest.fixture
def an(video_vertical, video_horizontal, raiz_capcut, monkeypatch):
    monkeypatch.setattr(transcricao, "modelo_pronto", lambda q="preciso": True)
    monkeypatch.setattr(transcricao, "Whisper", lambda q: None)
    monkeypatch.setattr(palavras, "transcreve", lambda w, x, p=None, **k: [
        *palavras.espalha("isso aqui muda tudo", [[0.0, 2.0]]), *palavras.espalha("você nunca tentou", [[4.0, 5.0]])])
    vids = {"pessoa": {"video": str(video_vertical), "info": audio.probe_video(video_vertical)},
            "ipad": {"video": str(video_horizontal), "info": audio.probe_video(video_horizontal)}}
    return lambda off: processa.analisa_ipad(raiz_capcut, vids, off)


def gera(raiz, a, **op):
    base = {"headline": "Como levar um CEO para 10 mil seguidores", "cortes": "forte", "zoom": True, "intensidade": 1.0,
            "pessoa": {"escala": 1.0, "x": 0.0, "y": -0.169}, "crop_ipad": [0.0, 0.11, 1.0, 0.93], "nome": "iPad teste"}
    return processa.monta_ipad(raiz, a, dict(base, **op))


def abre(raiz, nome):
    p = Path(raiz) / nome
    return json.loads((p / "draft_content.json").read_text(encoding="utf-8")), p


def partes(d):
    """(composto Video, composto iPad + pessoa) seguindo as referencias a partir da raiz"""
    ents = {e["id"]: e for e in d["materials"]["drafts"]}
    fin = ents[d["tracks"][0]["segments"][0]["extra_material_refs"][0]]["draft"]
    return fin, ents[fin["tracks"][0]["segments"][0]["extra_material_refs"][0]]["draft"]


def test_compostos_sincronizados_cortados_e_leves(raiz_capcut, an):
    a = an(1.2)                                                                       # iPad comecou 1,2 s antes
    r = gera(raiz_capcut, a)
    d, pasta = abre(raiz_capcut, r["nome"])
    assert (d["canvas_config"]["width"], d["canvas_config"]["height"]) == (1080, 1920)
    ents = d["materials"]["drafts"]
    assert len(ents) == 2                                                             # Video + iPad + pessoa, na raiz
    assert all(not e["draft"]["materials"].get("drafts") and (pasta / "subdraft" / e["draft"]["id"] / "draft_content.json").exists()
               for e in ents)
    fin, c = partes(d)
    # raiz: UM segmento (o video final) sem velocidade
    assert len(d["tracks"][0]["segments"]) == 1 and d["tracks"][0]["segments"][0]["speed"] == 1.0
    # iPad + pessoa: os dois INTEIROS e sincronizados, a pessoa num segmento so (o CapCut copia o composto por corte)
    pessoa, ip = [t for t in c["tracks"] if t["type"] == "video"]
    assert pessoa["flag"] == 0 and ip["flag"] == 2 and c["tracks"].index(ip) > c["tracks"].index(pessoa)
    assert len(pessoa["segments"]) == 1 and len(ip["segments"]) == 1
    assert ip["segments"][0]["source_timerange"]["start"] == 1_200_000 and pessoa["segments"][0]["source_timerange"]["start"] == 0
    fim = lambda t: t["segments"][-1]["target_timerange"]["start"] + t["segments"][-1]["target_timerange"]["duration"]
    assert fim(pessoa) == fim(ip) == c["duration"]
    assert ip["segments"][0]["common_keyframes"] == [] and ip["segments"][0]["clip"]["scale"]["x"] == 1.0   # iPad sem zoom
    kfs = {k["property_type"]: k["keyframe_list"] for k in pessoa["segments"][0]["common_keyframes"]}
    # os 4 juntos (sem PositionY o CapCut pos a pessoa em y = 0, atras do iPad), y sempre o do enquadramento
    assert set(kfs) == {"KFTypeScaleX", "KFTypePositionX", "KFTypePositionY", "KFTypeRotation"}
    assert max(k["values"][0] for k in kfs["KFTypeScaleX"]) > 1.0
    assert {k["values"][0] for k in kfs["KFTypePositionY"]} == {-0.169}
    assert len({tuple(k["time_offset"] for k in v) for v in kfs.values()}) == 1       # mesmos instantes
    assert len(json.dumps(c)) < 60_000                                               # leve: antes eram ~800 KB por copia
    # Video: os cortes sao segmentos do MESMO composto, cada um com material proprio
    cortes = fin["tracks"][0]["segments"]
    assert len(cortes) >= 2 and len({s["material_id"] for s in cortes}) == len(cortes)
    assert r["depois"] < r["antes"] and r["pedacos"] == len(cortes)
    assert ipad.verifica(d, pasta) == []


def test_zoom_troca_de_um_quadro_pro_outro():
    clip = {"scale": {"x": 1.0}, "transform": {"x": 0.0}}
    sub = [[0.0, 2.0, False], [2.0, 4.0, False], [5.0, 8.0, False]]
    pts = ipad.pontos_zoom(sub, [None, ("fixo", 1.2, 0.1), ("empurra", 1.3, 0.0)], 0, 8.0, clip)
    q = audio.quadro_us(ipad.QUADRO)
    assert (audio.quadro_us(2.0) - q, 1.0, 0.0) in pts and (audio.quadro_us(2.0), 1.2, 0.1) in pts   # 1 quadro de troca
    assert (audio.quadro_us(5.0), 1.0, 0.0) in pts and pts[-1][1] == pytest.approx(1.3)             # empurra: de 1 a 1,3
    assert ipad.pontos_zoom(sub, [None] * 3, 0, 8.0, clip) == []


def test_sincronia_negativa(raiz_capcut, an):
    r = gera(raiz_capcut, an(-1.5))
    d, _ = abre(raiz_capcut, r["nome"])
    pessoa, ip = [t for t in partes(d)[1]["tracks"] if t["type"] == "video"]
    assert pessoa["segments"][0]["source_timerange"]["start"] == 1_500_000 and ip["segments"][0]["source_timerange"]["start"] == 0


def test_headline_no_comeco_e_sem_legenda_quando_desmarcada(raiz_capcut, an):
    r = gera(raiz_capcut, an(0.0), headline_s=7.0, legenda=False)
    d, _ = abre(raiz_capcut, r["nome"])
    fin, c = partes(d)
    textos = [t for t in fin["tracks"] if t["type"] == "text"]
    assert len(textos) == 1 and len(textos[0]["segments"]) == 1                      # so a headline
    s = textos[0]["segments"][0]
    assert s["target_timerange"]["start"] == 0 and s["clip"]["transform"]["y"] == ipad.Y_HEADLINE
    assert abs(s["target_timerange"]["duration"] - 7_000_000) <= 1
    assert not c["materials"].get("texts") and not d["materials"].get("texts")


def test_legenda_automatica_do_capcut(raiz_capcut, an):
    a = an(0.0)
    r = gera(raiz_capcut, a, legenda=True)
    d, pasta = abre(raiz_capcut, r["nome"])
    fin, _ = partes(d)
    mol = ipad.MOLDE_AUTO
    trilhas = [t for t in fin["tracks"] if t["type"] == "text" and t.get("flag") == mol["trilha"]["flag"]]
    assert len(trilhas) == 1                                                          # trilha de LEGENDA (flag 1)
    legs = trilhas[0]["segments"]
    assert legs and r["legendas"] == len(legs)
    tpls = {m["id"]: m for m in fin["materials"]["text_templates"]}
    txt = {m["id"]: m for m in fin["materials"]["texts"]}
    dentro = [txt[tpls[s["material_id"]]["text_info_resources"][0]["text_material_id"]] for s in legs]
    assert all(tpls[s["material_id"]]["effect_id"] == mol["modelo"]["effect_id"] for s in legs)   # modelo 逐页短句
    frases = [json.loads(m["content"])["text"] for m in dentro]
    assert " ".join(frases) == "ISSO AQUI MUDA TUDO VOCÊ NUNCA TENTOU"                 # maiusculas, na ordem
    for k in ("font_size", "letter_spacing", "has_shadow", "shadow_distance", "text_color", "add_type", "language"):
        assert dentro[0][k] == mol["texto"][k], k
    assert len({m["group_id"] for m in dentro}) == 1 and dentro[0]["recognize_task_id"] == fin["config"]["subtitle_taskinfo"][0]["id"]
    w = dentro[0]["words"]
    assert [t for t in w["text"] if t != " "] == dentro[0]["recognize_text"].split() and w["start_time"] == sorted(w["start_time"])
    assert w["end_time"][-1] <= legs[0]["target_timerange"]["duration"] // 1000
    assert legs[0]["clip"] == mol["segmento"]["clip"]
    assert "{CACHE}" not in json.dumps(fin) and "{FONTE}" not in json.dumps(fin)
    ts = sorted((s["target_timerange"]["start"], s["target_timerange"]["duration"]) for s in legs)
    assert all(a + b <= c for (a, b), (c, _) in zip(ts, ts[1:]))                     # uma de cada vez
    assert ipad.verifica(d, pasta) == []


def test_frases_curtas_quebram_na_pausa_e_na_pontuacao():
    pal = [{"t": t, "a": a, "b": a + 0.3} for t, a in
           (("olá,", 0.0), ("tudo", 0.4), ("bem?", 0.8), ("-hoje", 2.0), ("eu", 2.4), ("vou", 2.8), ("falar\".", 3.2))]
    fr = ipad.frases(pal, [[0.0, 4.0, False]])
    assert [f["txt"] for f in fr] == ["OLÁ", "TUDO BEM", "HOJE EU VOU FALAR"]           # sem travessao nem aspas
    assert fr[0]["fim"] == pytest.approx(fr[1]["ini"])                               # pausa curta: cola na proxima
    longa = [{"t": "palavra", "a": i * 0.5, "b": i * 0.5 + 0.4} for i in range(12)]
    assert all(len(f["txt"]) <= ipad.FRASE_MAX for f in ipad.frases(longa, [[0.0, 7.0, False]]))


def test_velocidade_e_musica_no_composto_final(raiz_capcut, an, tmp_path):
    mus = tmp_path / "musica.wav"
    import subprocess
    subprocess.run([audio.ffmpeg_bin(), "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=330:duration=30",
                    str(mus)], check=True, **audio._sem_janela())
    a = an(0.0)
    r = gera(raiz_capcut, a, velocidade=True, musica=str(mus), legenda=True)
    d, pasta = abre(raiz_capcut, r["nome"])
    fin, _ = partes(d)
    sv = d["tracks"][0]["segments"][0]
    assert sv["speed"] == pytest.approx(ipad.VELOCIDADE, abs=0.002)
    assert sv["source_timerange"]["duration"] == fin["duration"]
    assert sv["target_timerange"]["duration"] * sv["speed"] == pytest.approx(fin["duration"], abs=2)
    assert d["duration"] == sv["target_timerange"]["duration"] and r["depois"] < sum(b - q for q, b, _ in a["keeps"]["forte"])
    quadro = 1e6 / 30
    assert abs(d["duration"] / quadro - round(d["duration"] / quadro)) < 0.01
    musica = [t for t in d["tracks"] if t["type"] == "audio"]
    assert len(musica) == 1
    sm = musica[0]["segments"][0]
    assert 20 * __import__("math").log10(sm["volume"]) == pytest.approx(-25.0, abs=0.01)
    assert sm["target_timerange"]["duration"] <= d["duration"]
    h = [s for t in fin["tracks"] if t["type"] == "text" for s in t["segments"] if s["clip"]["transform"]["y"] > 0][0]
    assert h["target_timerange"]["duration"] / sv["speed"] == pytest.approx(7e6, abs=40_000)   # 7 s no video final
    assert ipad.verifica(d, pasta) == []


def test_zoom_desligado(raiz_capcut, an):
    r = gera(raiz_capcut, an(0.0), zoom=False)
    d, _ = abre(raiz_capcut, r["nome"])
    pessoa = partes(d)[1]["tracks"][0]
    assert all(s["clip"]["scale"]["x"] == 1.0 and not s["common_keyframes"] for s in pessoa["segments"])


def test_verificacao_trava_source_alem_do_arquivo_e_ordem_errada(raiz_capcut, an, monkeypatch):
    a = an(1.2)
    real = processa.ipad.monta
    guardado = {}
    monkeypatch.setattr(processa.ipad, "monta", lambda *x, **k: guardado.setdefault("r", real(*x, **k)))
    gera(raiz_capcut, a)
    raiz_d = guardado["r"][0]
    dentro = lambda q: q["materials"]["drafts"][1]["draft"]
    fin = lambda q: q["materials"]["drafts"][0]["draft"]
    q = copy.deepcopy(raiz_d)
    ip = [t for t in dentro(q)["tracks"] if t["type"] == "video"][1]
    ip["segments"][0]["source_timerange"]["start"] += 60_000_000                    # passa do fim do arquivo do iPad
    assert any("passa do fim do arquivo" in e for e in ipad.verifica(q))
    q = copy.deepcopy(raiz_d)
    ts = dentro(q)["tracks"]
    ts[0], ts[1] = ts[1], ts[0]
    assert any("atrás da pessoa" in e for e in ipad.verifica(q))
    q = copy.deepcopy(raiz_d)
    fin(q)["tracks"][0]["segments"][-1]["source_timerange"]["duration"] += 60_000_000   # corte alem do composto
    assert any("passa do fim do clipe composto" in e for e in ipad.verifica(q))
    q = copy.deepcopy(raiz_d)
    q["tracks"][0]["segments"][0]["speed"] = 1.5                                     # velocidade sem bater a duracao
    assert any("velocidade" in e for e in ipad.verifica(q))
    monkeypatch.setattr(processa.ipad, "verifica", lambda d, p=None: ["trecho do vídeo do iPad passa do fim do arquivo"])
    antes = set(os.listdir(raiz_capcut))
    with pytest.raises(capcut.ErroProjeto, match="NÃO foi gravado"):
        gera(raiz_capcut, a, nome="nao deve existir")
    assert set(os.listdir(raiz_capcut)) == antes


def test_previa_leve_em_h264_com_o_mesmo_tempo(video_horizontal, tmp_path):
    p = ipad.gera_previa(video_horizontal, tmp_path / "previa.mp4", com_audio=False)
    i = audio.probe_video(p)
    assert abs(i["duracao"] - audio.probe_video(video_horizontal)["duracao"]) < 0.1 and max(i["largura"], i["altura"]) == 854


def test_transcricao_em_segundo_plano_e_recortada_pela_sincronia(video_vertical, video_horizontal, raiz_capcut):
    prontas = [{"t": "antes", "a": 0.2, "b": 0.5}, {"t": "isso", "a": 1.6, "b": 1.9}, {"t": "aqui", "a": 2.0, "b": 2.3}]
    vids = {"pessoa": {"video": str(video_vertical), "info": audio.probe_video(video_vertical)},
            "ipad": {"video": str(video_horizontal), "info": audio.probe_video(video_horizontal)}}
    a = processa.analisa_ipad(raiz_capcut, vids, -1.5, {}, None, palavras_prontas=prontas)    # pessoa comecou 1,5 s antes
    assert [p["t"] for p in a["palavras"]] == ["isso", "aqui"]
    assert a["palavras"][0]["a"] == pytest.approx(0.1)
    assert set(a["keeps"]) == set(ipad.CORTES)


def test_ipad_na_camada_de_cima_e_cortes_em_quadros_inteiros(raiz_capcut, an):
    r = gera(raiz_capcut, an(1.2))
    d, _ = abre(raiz_capcut, r["nome"])
    fin, c = partes(d)
    pessoa, ip = [t for t in c["tracks"] if t["type"] == "video"]
    # com render_index 0 o CapCut desenhou o iPad (com fundo preto) POR CIMA da pessoa inteira: a pessoa sumia
    assert ip["segments"][0]["render_index"] == 1 and all(s.get("render_index", 0) == 0 for s in pessoa["segments"])
    # o CapCut arredonda cada trecho pra quadros inteiros; fora da grade ele mexe na velocidade (visto: 0,9987)
    quadro = 1e6 / 30
    for s in fin["tracks"][0]["segments"] + pessoa["segments"]:
        for v in (s["source_timerange"]["duration"], s["target_timerange"]["duration"], s["target_timerange"]["start"]):
            assert abs(v / quadro - round(v / quadro)) < 0.01, v


def test_seco_tira_toda_pausa_mas_devolve_o_som_da_palavra(video_vertical, monkeypatch):
    x = audio.pcm(video_vertical)                        # tom em 0-3 s, 4,5-7,5 s e 9-10 s
    k = ipad.seco(x, [])
    assert sum(b - a for a, b, _ in k) < sum(b - a for a, b, _ in ipad.cortes(x, [], "forte"))
    assert all(k[i + 1][0] - k[i][1] >= ipad.JUNTA_SECO for i in range(len(k) - 1))
    # a regua do vlog comeu o fim de uma palavra que tem som (sibilante): a transcricao devolve
    monkeypatch.setattr(ipad.vlog, "regua", lambda x, dur: [[0.0, 2.5], [4.5, 7.5]])
    k = ipad.seco(x, [{"t": "case.", "a": 2.3, "b": 3.0}])
    assert any(a <= 2.3 and b >= 2.95 for a, b, _ in k)
    k = ipad.seco(x, [{"t": "fantasma", "a": 3.5, "b": 4.0}])  # palavra "ouvida" no silencio: nao volta
    assert not any(a < 4.0 and b > 3.5 for a, b, _ in k)
    for a, b, _ in k:                                           # na grade de quadros
        assert abs(a * 30 - round(a * 30)) < 1e-6 and abs(b * 30 - round(b * 30)) < 1e-6


def test_seco_e_o_padrao(raiz_capcut, an):
    a = an(0.0)
    assert set(a["keeps"]) == set(ipad.CORTES) and ipad.CORTES[0] == "seco"
    base = {"headline": "x", "zoom": True, "pessoa": {"escala": 1.0, "x": 0.0, "y": 0.0}, "crop_ipad": [0.0, 0.1, 1.0, 0.9], "nome": "seco"}
    r = processa.monta_ipad(raiz_capcut, a, base)
    assert r["depois"] == pytest.approx(sum(b - q for q, b, _ in a["keeps"]["seco"]), abs=0.05)
