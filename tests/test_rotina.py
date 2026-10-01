"""Rotina: horarios do relogio, velocidade exata, abaixamento da musica, montagem e verificacao."""
import copy, json, math, os, subprocess
from pathlib import Path
import pytest
from clipay import audio, capcut, palavras, processa, rotina, transcricao


# ---------------- relogio ----------------
def test_horario_vira_a_hora_e_a_meia_noite():
    assert rotina.horarios("07:58", [0, 5]) == ["07:58", "08:03"]
    assert rotina.horarios("23:50", [0, 20]) == ["23:50", "00:10"]
    assert rotina.horarios("09:10", [0, 45]) == ["09:10", "09:55"]                  # salto de 40+ min
    # mistura: mesma cena (2 min) e mudou a atividade (30 min e 50 min)
    assert rotina.horarios("07:30", [0, 2, 2, 30, 2, 50]) == ["07:30", "07:32", "07:34", "08:04", "08:06", "08:56"]


def test_horario_invalido_e_salto_fora_da_faixa():
    with pytest.raises(capcut.ErroProjeto, match="HH:MM"):
        rotina.horarios("7h30", [0])
    with pytest.raises(capcut.ErroProjeto, match="salto"):
        rotina.horarios("07:30", [0, 0])


# ---------------- tempo e volume ----------------
def test_velocidade_exata_e_timeline_em_quadros_inteiros():
    tl = rotina.linha_do_tempo([[0.0, 2.0], [3.1, 5.5], [7.0, 7.4]])
    q = 1e6 / 30
    fim = 0
    for (a, b), (S0, Sd, T0, Td) in zip([[0.0, 2.0], [3.1, 5.5], [7.0, 7.4]], tl):
        assert T0 == fim and abs(Td / q - round(Td / q)) < 0.01                     # encostados, quadros inteiros
        assert abs(Sd - Td * rotina.VELOCIDADE) <= 1                               # velocidade exata 1,13
        assert S0 + Sd <= audio.quadro_us(b) + 1                                    # nunca passa do trecho
        fim = T0 + Td


def test_musica_desce_na_fala_e_sobe_no_silencio():
    pts = rotina.volume_keyframes([[2.0, 4.0], [4.6, 6.0], [10.0, 11.0]], 15.0, 1.0, 0.21, 0.5)
    v = dict(pts)
    assert v[0] == 1.0 and v[2_000_000] == 0.21 and v[1_500_000] == 1.0               # rampa de 0,5 s antes da fala
    assert all(val == 0.21 for t, val in pts if 4_000_000 <= t <= 4_600_000)          # pausa curta: fica baixo
    assert v[6_500_000] == 1.0 and v[10_000_000] == 0.21 and v[11_500_000] == 1.0
    assert [t for t, _ in pts] == sorted({t for t, _ in pts})
    assert rotina.volume_keyframes([[0.1, 1.0]], 5.0, 1.0, 0.21, 0.5)[0] == (0, 0.21)   # fala logo no comeco


def test_trecho_curto_junta_com_o_vizinho_sem_perder_fala():
    k = rotina.junta_curtos([[0.0, 2.0], [2.3, 2.6], [5.0, 7.0]], 1.0)
    assert k == [[0.0, 2.6], [5.0, 7.0]]
    assert rotina.junta_curtos([[0.0, 2.0], [4.0, 4.3], [7.0, 9.0]], 1.0) == [[0.0, 2.0], [4.0, 4.3], [7.0, 9.0]]  # longe: fica


# ---------------- montagem ----------------
@pytest.fixture
def an(video_vertical, raiz_capcut, monkeypatch):
    monkeypatch.setattr(transcricao, "modelo_pronto", lambda q="preciso": True)
    monkeypatch.setattr(transcricao, "Whisper", lambda q: None)
    monkeypatch.setattr(palavras, "transcreve", lambda w, x, p=None: [
        *palavras.espalha("bom dia acordei agora", [[0.0, 3.0]]), *palavras.espalha("bora pra academia", [[4.5, 7.5]]),
        *palavras.espalha("treino pago", [[9.0, 10.0]])])
    return processa.analisa_rotina(raiz_capcut, video_vertical)


@pytest.fixture
def musica(tmp_path):
    p = tmp_path / "musica.wav"
    subprocess.run([audio.ffmpeg_bin(), "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=330:duration=30", str(p)],
                   check=True, **audio._sem_janela())
    return str(p)


def gera(raiz, an, **op):
    base = {"trechos": an["keep"], "inicio": "07:58", "saltos": [0] + [5] * (len(an["keep"]) - 1),
            "headline": "Minha rotina de CEO às 5 da manhã", "headline_s": 5.0, "nome": "Rotina teste"}
    return processa.monta_rotina(raiz, an, dict(base, **op))


def abre(raiz, nome):
    return json.loads((Path(raiz) / nome / "draft_content.json").read_text(encoding="utf-8"))


def textos(d):
    txt = {m["id"]: json.loads(m["content"])["text"] for m in d["materials"]["texts"]}
    return [(s, txt[s["material_id"]]) for t in d["tracks"] if t["type"] == "text" for s in t["segments"]]


def test_projeto_da_rotina_completo(raiz_capcut, an, musica):
    assert len(an["keep"]) == 3
    r = gera(raiz_capcut, an, musica=musica)
    d = abre(raiz_capcut, r["nome"])
    vids = [t for t in d["tracks"] if t["type"] == "video"]
    assert len(vids) == 1 and len(vids[0]["segments"]) == 3
    assert all(s["speed"] == rotina.VELOCIDADE for s in vids[0]["segments"])
    sp = {x["id"]: x["speed"] for x in d["materials"]["speeds"]}
    assert all(sp[r_] == rotina.VELOCIDADE for s in vids[0]["segments"] for r_ in s["extra_material_refs"] if r_ in sp)
    assert r["depois"] < sum(b - a for a, b in an["keep"])                            # acelerado
    # relogio: um por trecho, mesma posicao, horario pulando 5 min
    rel = sorted([(s, t) for s, t in textos(d) if ":" in t and len(t) == 5], key=lambda x: x[0]["target_timerange"]["start"])
    assert [t for _, t in rel] == ["07:58", "08:03", "08:08"]
    assert [s["target_timerange"] for s, _ in rel] == [s["target_timerange"] for s in vids[0]["segments"]]
    assert len({(s["clip"]["transform"]["x"], s["clip"]["transform"]["y"]) for s, _ in rel}) == 1
    x, y = rel[0][0]["clip"]["transform"]["x"], rel[0][0]["clip"]["transform"]["y"]
    assert x > 0.6 and y > 0.8                                                        # canto superior direito
    # headline no comeco, abaixo do relogio
    hl = [(s, t) for s, t in textos(d) if not (":" in t and len(t) == 5)]
    assert len(hl) == 1 and hl[0][0]["target_timerange"]["start"] == 0 and hl[0][0]["clip"]["transform"]["y"] < y
    assert abs(hl[0][0]["target_timerange"]["duration"] - 5_000_000) <= 1
    # filtro Aprimorar 60 no video todo
    fl = [t for t in d["tracks"] if t["type"] == "filter"]
    assert len(fl) == 1 and fl[0]["segments"][0]["target_timerange"] == {"start": 0, "duration": d["duration"]}
    ef = {m["id"]: m for m in d["materials"]["effects"]}[fl[0]["segments"][0]["material_id"]]
    assert ef["effect_id"] == rotina.FILTRO_ID and ef["value"] == pytest.approx(0.6)
    # musica com keyframes de volume
    au = [t for t in d["tracks"] if t["type"] == "audio"]
    kfs = au[0]["segments"][0]["common_keyframes"]
    assert kfs[0]["property_type"] == "KFTypeVolume"
    vals = {k["values"][0] for k in kfs[0]["keyframe_list"]}
    assert vals == {1.0, 0.21}
    assert rotina.verifica(d) == []


def test_sem_musica_e_sem_headline(raiz_capcut, an):
    r = gera(raiz_capcut, an, headline="")
    d = abre(raiz_capcut, r["nome"])
    assert not [t for t in d["tracks"] if t["type"] == "audio"] and len(textos(d)) == 3
    assert rotina.verifica(d) == []


def test_verificacao_trava_horario_que_volta_e_texto_fora_da_tela(raiz_capcut, an, monkeypatch):
    real = rotina.monta
    guardado = {}
    monkeypatch.setattr(rotina, "monta", lambda *a, **k: guardado.setdefault("r", real(*a, **k)))
    gera(raiz_capcut, an)
    d = guardado["r"][0]
    assert rotina.verifica(d) == []
    q = copy.deepcopy(d)                                                               # horario volta
    txt = {m["id"]: m for m in q["materials"]["texts"]}
    rel = [s for s, t in textos(q) if ":" in t and len(t) == 5]
    rel.sort(key=lambda s: s["target_timerange"]["start"])
    m = txt[rel[2]["material_id"]]; c = json.loads(m["content"]); c["text"] = "07:00"; m["content"] = json.dumps(c)
    assert any("volta" in e for e in rotina.verifica(q))
    q = copy.deepcopy(d)                                                               # headline sai da tela
    hl = [s for s, t in textos(q) if not (":" in t and len(t) == 5)][0]
    hl["clip"]["scale"] = {"x": 3.0, "y": 3.0}
    assert any("sai da tela" in e for e in rotina.verifica(q))
    q = copy.deepcopy(d)                                                               # velocidade diferente
    v = [t for t in q["tracks"] if t["type"] == "video"][0]["segments"][1]
    v["speed"] = 1.0
    assert any("velocidade" in e for e in rotina.verifica(q))
    q = copy.deepcopy(d)                                                               # relogio sem um texto
    tr = [t for t in q["tracks"] if t["type"] == "text" and len(t["segments"]) == 3][0]
    tr["segments"].pop()
    assert any("um por trecho" in e for e in rotina.verifica(q))
    monkeypatch.setattr(rotina, "verifica", lambda d: ["o horário volta"])
    antes = set(os.listdir(raiz_capcut))
    with pytest.raises(capcut.ErroProjeto, match="NÃO foi gravado"):
        gera(raiz_capcut, an, nome="nao deve existir")
    assert set(os.listdir(raiz_capcut)) == antes


def test_controles_de_corte(an):
    poucos = rotina.cortes(an["palavras"], an["info"]["duracao"], silencio_ms=2000)
    assert len(poucos) < len(an["keep"])                                              # silencio maior: menos cortes
