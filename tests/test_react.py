"""React (Fase 1, so o motor): o projeto do CapCut sai igual ao real "Patricio clipay ia" trocando so o que varia.
Sem CTA, com CTA (o de cima congela e o react pausa e volta do mesmo ponto), video horizontal em cima, react curto
demais, sem pausa na janela, variar o trecho, nomes com acento — e o teste de ouro contra o projeto de referencia."""
import copy, json, re, shutil, subprocess
from pathlib import Path
import pytest
from clipay import audio, react

REF = Path(__file__).resolve().parent.parent / "docs" / "design" / "referencia-react"
REF_HL = REF.parent / "referencia-headline"


def _video(destino, w, h, dur):
    tom = f"aevalsrc='sin(2*PI*150*t)*0.5':s=16000:d={dur}"
    subprocess.run([audio.ffmpeg_bin(), "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s={w}x{h}:r=30:d={dur}",
                    "-f", "lavfi", "-i", tom, "-pix_fmt", "yuv420p", "-c:v", "mpeg4", "-q:v", "5", "-c:a", "aac",
                    "-shortest", str(destino)], check=True, capture_output=True)
    return destino


@pytest.fixture(scope="module")
def midia(tmp_path_factory):
    p = tmp_path_factory.mktemp("react")
    return {"react": _video(p / "react.mp4", 1920, 1080, 30), "cta": _video(p / "cta.mp4", 1920, 1080, 3),
            "curto": _video(p / "react curto.mp4", 1920, 1080, 6)}


def _segs(r):
    st = lambda s: s.get("source_timerange") or {"start": None, "duration": None}
    return [[(st(s)["start"], st(s)["duration"], s["target_timerange"]["start"], s["target_timerange"]["duration"])
             for s in t["segments"]] for t in r["draft"]["tracks"]]


def test_sem_cta(video_vertical, midia, tmp_path):
    raiz = tmp_path / "capcut"; raiz.mkdir()
    r = react.monta(video_vertical, midia["react"])
    D = react.duracao_us(video_vertical)
    cima, baixo, txt = _segs(r)
    assert cima == [(0, D, 0, D)] and baixo == [(1_400_000, D, 0, D)] and txt[0][2:] == (0, D)
    assert r["draft"]["duration"] == D and r["png"] is None and react.verifica(r) == []
    vols = [s["volume"] for t in r["draft"]["tracks"][:2] for s in t["segments"]]
    assert vols == [1.0, 0.0]                                    # receita com som, react mudo
    assert json.loads(r["draft"]["materials"]["texts"][0]["content"])["text"] == "SUA HEADLINE AQUI"
    nomes = {v["material_name"] for v in r["draft"]["materials"]["videos"]}
    assert nomes == {"vertical.mp4", "react.mp4"}                # sem foto congelada nem CTA sobrando
    assert [g["value"] for g in r["meta"]["draft_materials"] if g["type"] == 6] == [[]]
    nome = react.grava(raiz, r)
    assert nome == "vertical - react" and (raiz / nome / "draft_content.json").exists()
    assert json.loads((raiz / "root_meta_info.json").read_text(encoding="utf-8"))["all_draft_store"][0]["draft_name"] == nome


def test_com_cta_congela_e_react_volta_de_onde_parou(video_vertical, midia, tmp_path):
    raiz = tmp_path / "capcut"; raiz.mkdir()
    r = react.monta(video_vertical, midia["react"], cta=midia["cta"], congelar=5.0)
    D, C = react.duracao_us(video_vertical), react.duracao_us(midia["cta"])
    P = 5_000_000
    (c1, foto, c3), (k1, kc, k3), (t,) = _segs(r)
    assert c1 == (0, P, 0, P) and foto[2] == P and c3[0] == P and c3[2] == foto[2] + foto[3]
    assert k1 == (1_400_000, P, 0, P) and kc[2] == P and kc[1] == C and k3[0] == 1_400_000 + P   # react pausado
    assert c3[2] + c3[3] == k3[2] + k3[3] == t[3] == D + C == r["draft"]["duration"]
    segs = r["draft"]["tracks"][1]["segments"]
    assert [s["volume"] for s in segs] == [0.0, 1.0, 0.0]        # o CTA tem som
    todos = [s for t in r["draft"]["tracks"] for s in t["segments"]]
    filtros = {x["id"] for x in r["draft"]["materials"].get("effects", [])}
    assert not filtros and not any(set(s["extra_material_refs"]) & filtros for s in todos)   # nenhum filtro em trecho nenhum
    mascaras = {x["id"] for x in r["draft"]["materials"]["common_mask"]}
    assert [bool(set(s["extra_material_refs"]) & mascaras) for s in segs] == [True, True, True]   # a mascara "Dividir" continua
    nome = react.grava(raiz, r)
    png = raiz / nome / r["png"]
    assert png.exists() and png.stat().st_size > 0 and react.verifica(r, raiz / nome) == []
    foto_m = next(v for v in r["draft"]["materials"]["videos"] if v["type"] == "photo")
    assert foto_m["freeze"]["timestamp"] == P and foto_m["path"].endswith("/" + r["png"])


def test_video_horizontal_em_cima(video_horizontal, midia):
    g = react.enquadra_cima(960, 540)
    assert g["modo"] == "horizontal" and g["lateral"]
    lh = 540 * (1080 / 960) * g["escala"]                        # altura na tela
    topo = 960 - g["y"] * 960 - lh / 2
    assert topo <= 1e-6 and topo + lh >= react.COBRE_ATE - 1e-6  # cobre do topo ate a faixa
    esq, dir_ = react.enquadra_cima(960, 540, posicao=0)["x"], react.enquadra_cima(960, 540, posicao=1)["x"]
    assert esq > 0 > dir_ and abs(esq) <= g["escala"] - 1 + 1e-9   # posicao agora e' na horizontal, sem borda
    r = react.monta(video_horizontal, midia["react"], {"posicao": 0.2})
    assert r["enquadramento"]["modo"] == "horizontal" and react.verifica(r) == []


def test_limite_do_corte_em_cima():
    g = react.enquadra_cima(1080, 1920, corte=0.45)
    assert g["limitado"] and abs(g["corte_max"] - (1 - react.COBRE_ATE / 1920)) < 1e-9
    assert abs(react.enquadra_cima(1080, 1920, corte=0.45, zoom=1.5)["corte_max"] - (1 - react.COBRE_ATE / 2880)) < 1e-9
    ok = react.enquadra_cima(1080, 1920, corte=0.2)
    assert not ok["limitado"] and abs(ok["y"] - 0.4) < 1e-9


def test_react_curto_demais(video_vertical, midia, tmp_path):
    with pytest.raises(react.ErroReact, match="vertical.mp4"):
        react.monta(video_vertical, midia["curto"])
    raiz = tmp_path / "capcut"; raiz.mkdir()
    out = react.gera(raiz, [{"video": video_vertical}], midia["curto"])
    assert "mais curto" in out[0]["erro"] and "vertical.mp4" in out[0]["erro"] and not list(raiz.glob("* - react"))


def test_sem_pausa_na_janela(video_vertical):
    D = react.duracao_us(video_vertical) / 1e6                  # tom com pausas em 3-4,5 s e 7,5-9 s: fora de 40-70%
    c = react.ponto_congelar(video_vertical, D)
    assert c == {"t": 0.55 * D, "boa": False, "pausa_curta": False, "motivo": "sem pausa boa"}
    tr = [[0, 4.0], [4.6, 6.0], [6.2, 10]]                      # pausa de 0,6 s em 4,3 s (dentro da janela)
    assert react.ponto_congelar(None, 10, None, tr, x=[0])["t"] == pytest.approx(4.3)
    falas = [{"t": "abre", "a": 3.5, "b": 4.0}, {"t": "a", "a": 4.6, "b": 4.8}]   # sem ponto: meio da frase
    assert react.ponto_congelar(None, 10, falas, tr, x=[0])["boa"] is False


def test_variar_o_trecho(video_vertical, midia, tmp_path):
    raiz = tmp_path / "capcut"; raiz.mkdir()
    itens = []
    for i in range(3):
        v = tmp_path / f"receita {i + 1}.mp4"; shutil.copy(video_vertical, v); itens.append({"video": v})
    out = react.gera(raiz, itens, midia["react"], variar=True)
    assert all("projeto" in o for o in out), out
    ini = [o["inicio_react"] for o in out]
    assert len(set(ini)) == 3 and ini[0] == pytest.approx(1.4)
    R, D = react.duracao_us(midia["react"]), react.duracao_us(video_vertical)
    assert all(round(i * 1e6) + D <= R for i in ini)             # nenhum passa do fim do react
    assert sorted(p.name for p in raiz.glob("* - react")) == ["receita 1 - react", "receita 2 - react", "receita 3 - react"]


def test_nomes_com_acento(video_vertical, midia, tmp_path):
    pasta = tmp_path / "Vídeos café"; pasta.mkdir()
    v = pasta / "Pão de queijo ção.mp4"; shutil.copy(video_vertical, v)
    cta = pasta / "CTA +100 RECEITAS .mp4"; shutil.copy(midia["cta"], cta)
    raiz = tmp_path / "Área de Trabalho" / "capcut"; raiz.mkdir(parents=True)
    out = react.gera(raiz, [{"video": v, "congelar": 5.0}], midia["react"], cta=cta)
    assert out[0].get("projeto") == "Pão de queijo ção - react", out
    d = json.loads((raiz / out[0]["projeto"] / "draft_content.json").read_text(encoding="utf-8"))
    caminhos = {m["path"] for m in d["materials"]["videos"] if m["type"] == "video"}
    assert str(v.resolve()).replace("\\", "/") in caminhos and str(cta.resolve()).replace("\\", "/") in caminhos


def test_molde_sem_dados_da_maquina():
    t = (react.PASTA / "draft_content.json").read_text(encoding="utf-8") + (react.PASTA / "draft_meta_info.json").read_text(encoding="utf-8")
    assert "danil" not in t.lower() and '"device_id": ""' in t


_ID = re.compile(r"^([0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}|[0-9a-f]{32})$")


def _difs(a, b, p="", out=None):
    out = [] if out is None else out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in set(a) | set(b):
            if k not in a or k not in b: out.append(p + "." + k)
            else: _difs(a[k], b[k], p + "." + k, out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b): out.append(p)
        else: [_difs(x, y, f"{p}[{i}]", out) for i, (x, y) in enumerate(zip(a, b))]
    elif isinstance(a, str) and isinstance(b, str) and _ID.match(a) and _ID.match(b): pass
    elif isinstance(a, float) and isinstance(b, (int, float)) and abs(a - b) < 1e-9: pass
    elif a != b: out.append(p)
    return out


def test_ouro_patricio():
    """refaz o "Patricio clipay ia" com as mesmas entradas: so os ids, os dados da maquina (zerados) e o texto da
    headline (sai o exemplo) podem mudar"""
    ref = json.loads((REF / "draft_content.json").read_text(encoding="utf-8"))
    pega = lambda n: next(v["path"] for v in ref["materials"]["videos"] if v["material_name"] == n)
    rec, rct, cta = pega("snaptik_7597584659882724629_v3.mp4"), pega("IMG_7361.MOV"), pega("CTA +100 RECEITAS .mp4")
    novo = Path(rct).parent / "React Patricio.mp4"               # o react da referencia foi renomeado (mesmo 16:9)
    trocou = not Path(rct).exists() and novo.exists()
    if trocou: rct = str(novo)
    if not all(Path(p).exists() for p in (rec, rct, cta)):
        pytest.skip("mídia do projeto de referência não está neste computador")
    cache = ref["materials"]["effects"][0]["path"].split("/effect/")[0]      # o cache do CapCut desta maquina
    r = react.monta(rec, rct, {"corte": ref["tracks"][0]["segments"][0]["clip"]["transform"]["y"] / 2}, cta, None,
                    ref["tracks"][0]["segments"][0]["target_timerange"]["duration"] / 1e6, cache)
    assert react.verifica(r) == []
    sem = copy.deepcopy(ref); react.sem_filtro(sem)                # desde 2026-10 o React sai sem o filtro "Aprimorar"
    assert len(ref["materials"]["effects"]) == 2 and not sem["materials"].get("effects")
    assert not r["draft"]["materials"].get("effects") and len(r["draft"]["materials"]["common_mask"]) == 3
    difs = _difs(r["draft"], sem)
    esperado = [".materials.texts[0].content"] + [f".{k}.{c}" for k in ("platform", "last_modified_platform")
                                                   for c in ("device_id", "hard_disk_id", "mac_address")]
    if trocou:                                                   # so os dados do proprio arquivo do react podem mudar
        ik = {i for i, v in enumerate(sem["materials"]["videos"]) if v["material_name"] == "IMG_7361.MOV"}
        dado = re.compile(r"\.materials\.videos\[(\d+)\]\.(path|material_name|duration|width|height)$")
        difs = [x for x in difs if not (dado.match(x) and int(dado.match(x)[1]) in ik)]
    assert sorted(difs) == sorted(esperado)
    # as pecas do modelo de texto mantem o nome do pacote (texto e barra vermelha): senao o CapCut refaz o modelo
    # do zero, com 3 s e o texto padrao, e a headline some
    nomes = lambda x: (x["materials"]["texts"][0]["name"], x["materials"]["text_templates"][0]["non_text_info_resources"][0]["name"])
    assert nomes(r["draft"]) == nomes(ref)
    a, b = (json.loads(x["materials"]["texts"][0]["content"]) for x in (r["draft"], ref))
    a["text"] = b["text"] = ""; a["styles"][0]["range"] = b["styles"][0]["range"] = None
    assert a == b                                                # estilo da headline identico


def test_cta_no_final(video_vertical, midia, tmp_path):
    """CTA no final: o video toca inteiro, depois o ultimo quadro parado com o CTA embaixo. Sem procurar pausa."""
    raiz = tmp_path / "capcut"; raiz.mkdir()
    r = react.monta(video_vertical, midia["react"], cta=midia["cta"], cta_pos="final")
    D, C = react.duracao_us(video_vertical), react.duracao_us(midia["cta"])
    (c1, foto), (k1, kc), (t,) = _segs(r)
    assert c1 == (0, D, 0, D) and foto == (0, C, D, C)
    assert k1 == (1_400_000, D, 0, D) and kc == (0, C, D, C)            # o CTA logo depois do react
    assert t[3] == D + C == r["draft"]["duration"] and react.verifica(r) == []
    assert r["congelar"]["motivo"] == "no final" and r["congelar"]["us"] == D - react.us(1 / 30)
    assert [s["volume"] for s in r["draft"]["tracks"][1]["segments"]] == [0.0, 1.0]
    nomes = [v["material_name"] for v in r["draft"]["materials"]["videos"]]
    assert sorted(nomes) == sorted(["vertical.mp4", "Congelar", "react.mp4", "cta.mp4"])     # nada do 3o trecho
    nome = react.grava(raiz, r)
    png = raiz / nome / r["png"]
    assert png.exists() and png.stat().st_size > 0 and react.verifica(r, raiz / nome) == []


# ---------------- modelo da headline e posicao do react ----------------
def _bloco_hl(d):
    """o trecho da headline e os materiais dele, por tipo (pra comparar so a headline)"""
    M = d["materials"]; s = next(t for t in d["tracks"] if t["type"] == "text")["segments"][0]
    por_id = {x["id"]: x for v in M.values() if isinstance(v, list) for x in v if isinstance(x, dict) and "id" in x}
    ordem = {i: n for n, i in enumerate(re.findall(r'"([0-9A-Fa-f-]{36})"', json.dumps(s)))}   # na ordem em que o trecho cita
    out = {"segmento": s}
    for k, ids in react.materiais_do_trecho(M, s).items():
        out[k] = [por_id[i] for i in sorted(ids, key=lambda i: ordem.get(i, 99))]
    return out


def test_modelos_de_headline_na_configuracao():
    ms = react.headlines()
    assert [m["id"] for m in ms] == ["noticia", "citacao"] and react.headline()["id"] == "noticia"
    for m in ms:
        assert {"id", "nome", "descricao", "selo", "previa", "bloco"} <= set(m)
        if m["bloco"]: assert (react.PASTA / m["bloco"]).is_file()
    with pytest.raises(react.ErroReact, match="desconhecido"): react.headline("nao-existe")
    t = (react.PASTA / "headlines" / "citacao.json").read_text(encoding="utf-8")
    assert "danil" not in t.lower() and "{FONTE}" in t and "{CACHE}" in t      # sem dados da maquina


def test_ouro_citacao(video_vertical, midia):
    """React com Citacao: o bloco da headline igual ao do projeto "headline teste"; so ids, tempos e texto mudam"""
    if not (REF_HL / "citacao" / "draft_content.json").exists():
        pytest.skip("o projeto de referência da Citação não está neste computador")
    ref = json.loads((REF_HL / "citacao" / "draft_content.json").read_text(encoding="utf-8"))
    if not react.fonte_headline():
        pytest.skip("a fonte Creato Display não está instalada neste computador")
    cache = ref["materials"]["text_templates"][0]["path"].split("/artistEffect/")[0]
    r = react.monta(video_vertical, midia["react"], cta=midia["cta"], congelar=5.0, cache=cache, headline_id="citacao")
    d = r["draft"]; total = d["duration"]
    assert react.verifica(r) == [] and r["headline"] == "citacao"
    a, b = _bloco_hl(d), _bloco_hl(ref)
    assert sorted(a) == sorted(b) == ["material_animations", "segmento", "text_templates", "texts"]
    assert a["text_templates"][0]["effect_id"] == "7641057540280798472" and len(d["materials"]["text_templates"]) == 1
    assert a["segmento"]["target_timerange"] == {"start": 0, "duration": total}       # o video todo, contando o CTA
    for x in a["text_templates"][0]["text_info_resources"] + a["text_templates"][0]["non_text_info_resources"]:
        assert x["attach_info"]["start_time"] == 0 and x["attach_info"]["duration"] == total
    ca, cb = (json.loads(x["texts"][0]["content"]) for x in (a, b))
    assert ca["text"] == "SUA HEADLINE AQUI" and ca["styles"][0]["range"] == [0, len("SUA HEADLINE AQUI")]
    ca["text"] = cb["text"] = ""; ca["styles"][0]["range"] = cb["styles"][0]["range"] = None
    assert ca == cb                                               # estilo identico (fonte, tamanho, cor, negrito)
    a["texts"][0]["content"] = b["texts"][0]["content"] = ""
    difs = [x for x in _difs(a, b) if not re.search(r"(target_timerange\.duration|attach_info\.duration)$", x)]
    assert difs == []                                             # o resto da headline: identico
    nomes = lambda x: (x["texts"][0]["name"], x["text_templates"][0]["non_text_info_resources"][0]["name"])
    assert nomes(a) == nomes(b)                                   # nomes do pacote mantidos (a headline nao some)
    tudo = json.dumps(d, ensure_ascii=False)
    assert "praticar" not in tudo and "Simple News" not in tudo and "Bomba de presunto" not in tudo
    ids = [x["id"] for v in d["materials"].values() if isinstance(v, list) for x in v if isinstance(x, dict) and "id" in x]
    assert len(ids) == len(set(ids))                              # nenhum id repetido


def test_react_deslocado_no_limite(video_vertical, midia):
    """react horizontal: so pros lados, no maximo a sobra (nunca fundo vazio); a mascara e o CTA nao mudam"""
    base = react.monta(video_vertical, midia["react"], cta=midia["cta"], congelar=5.0)
    k0 = base["draft"]["tracks"][1]["segments"]
    mk = lambda r, s: next(m for m in r["draft"]["materials"]["common_mask"] if m["id"] in s["extra_material_refs"])["config"]
    lim = (1080 * 1.2172339513890111 - 1080) / 2 / 540
    assert base["faixa"]["eixo"] == "x" and base["faixa"]["lim"] == pytest.approx(lim) and lim == pytest.approx(0.2172, abs=1e-4)
    for pos, x in ((-100, -lim), (100, lim), (-250, -lim), (250, lim), (50, lim / 2)):
        r = react.monta(video_vertical, midia["react"], cta=midia["cta"], congelar=5.0, react_pos=pos)
        k1, kc, k3 = r["draft"]["tracks"][1]["segments"]
        assert k1["clip"]["transform"]["x"] == k3["clip"]["transform"]["x"] == pytest.approx(x)
        assert abs(k1["clip"]["transform"]["x"]) <= lim + 1e-12                 # nunca passa do limite
        assert k1["clip"]["transform"]["y"] == k0[0]["clip"]["transform"]["y"] and k1["clip"]["scale"] == k0[0]["clip"]["scale"]
        assert mk(r, k1) == mk(base, k0[0]) and mk(r, k3) == mk(base, k0[2])      # a mascara nao muda
        assert kc["clip"] == k0[1]["clip"] and mk(r, kc) == mk(base, k0[1])       # o CTA nao se move
        lw = 1080 * k1["clip"]["scale"]["x"]
        esq = 540 + k1["clip"]["transform"]["x"] * 540 - lw / 2
        assert esq <= 1e-6 and esq + lw >= 1080 - 1e-6                           # cobre a largura toda
    r = react.monta(video_vertical, midia["react"], cta=midia["cta"], cta_pos="final", react_pos=-100)
    k1, kc = r["draft"]["tracks"][1]["segments"]
    assert k1["clip"]["transform"]["x"] == pytest.approx(-lim) and kc["clip"]["transform"]["x"] == 0.0 and react.verifica(r) == []


def test_react_vertical_move_na_vertical(video_vertical, midia, tmp_path):
    """react vertical: so pra cima e pra baixo, cobrindo a faixa; a linha da mascara fica no mesmo lugar da tela"""
    rv = _video(tmp_path / "react vertical.mp4", 540, 960, 30)
    ref = react.monta(video_vertical, midia["react"])["draft"]
    k_ref = ref["tracks"][1]["segments"][0]
    cy_ref = next(m for m in ref["materials"]["common_mask"] if m["id"] in k_ref["extra_material_refs"])["config"]["centerY"]
    linha = lambda clip, h, cy: (960 - clip["transform"]["y"] * 960) - cy * h * clip["scale"]["y"] / 2   # px na tela
    h_ref = 1080 * 9 / 16
    alvo = linha(k_ref["clip"], h_ref, cy_ref)
    assert 1180 < alvo < 1250                                     # a emenda medida na referencia (~1215 px)
    topo_faixa = (960 - k_ref["clip"]["transform"]["y"] * 960) - h_ref * k_ref["clip"]["scale"]["y"] / 2   # topo da faixa na tela
    ys = []
    for pos in (-100, 0, 100):
        r = react.monta(video_vertical, rv, cta=midia["cta"], congelar=5.0, react_pos=pos)
        assert react.verifica(r) == [] and r["faixa"]["eixo"] == "y" and r["faixa"]["orientacao"] == "vertical"
        k1, kc, k3 = r["draft"]["tracks"][1]["segments"]
        for s in (k1, k3):
            assert s["clip"]["transform"]["x"] == 0.0
            cy = next(m for m in r["draft"]["materials"]["common_mask"] if m["id"] in s["extra_material_refs"])["config"]["centerY"]
            assert linha(s["clip"], 1920, cy) == pytest.approx(alvo)             # mascara compensada
            c, lh = 960 - s["clip"]["transform"]["y"] * 960, 1920 * s["clip"]["scale"]["y"]
            assert c - lh / 2 <= topo_faixa + 1e-6 and c + lh / 2 >= 1920 - 1e-6   # cobre a faixa, sem fundo vazio
        assert kc["clip"]["transform"]["x"] == 0.0
        ys.append(k1["clip"]["transform"]["y"])
    assert ys[0] > ys[1] > ys[2]                                  # -100 = pra cima (y do CapCut cresce pra cima)
