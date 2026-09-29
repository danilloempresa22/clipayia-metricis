"""Captura os moldes do modo Legenda Complexa a partir de uma edicao REAL aprovada no CapCut (nao inventa estrutura).
Uso (so no computador de desenvolvimento):  python ferramentas/captura_moldes_legenda.py "João 2 - legendado"
Gera app/clipay/assets/moldes/legenda.json com, para cada peca, o segmento e TODOS os materiais que ele referencia."""
import copy, json, os, re, sys
from pathlib import Path

R = Path(os.path.expandvars(r"%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft"))
DESTINO = Path(__file__).resolve().parent.parent / "clipay" / "assets" / "moldes" / "legenda.json"
PUBLICSANS = "7242301789909815863"


def indice(d):
    return {x["id"]: (k, x) for k, v in d.get("materials", {}).items() if isinstance(v, list)
            for x in v if isinstance(x, dict) and "id" in x}


def peca(seg, d, raiz_drafts):
    """segmento + material principal + materiais das refs (na ordem), com a categoria de cada um"""
    idx = indice(d)
    cat, mat = idx[seg["material_id"]]
    refs = []
    for r in seg["extra_material_refs"]:
        if r in raiz_drafts:
            refs.append(["drafts", None])                    # aponta pra entrada da raiz (preenchida na montagem)
        else:
            refs.append(list(idx[r]))
    return {"segmento": seg, "material": [cat, mat], "refs": refs}


def sem_segmentos(t):
    return {k: v for k, v in t.items() if k != "segments"}


def esqueleto(d):
    """draft sem trilhas/materiais (fica so a configuracao de topo)"""
    e = copy.deepcopy(d)
    e["tracks"] = []
    e["materials"] = {k: ([] if isinstance(v, list) else v) for k, v in d["materials"].items()}
    return e


def limpa(txt):
    txt = re.sub(r"C:/Users/[^/\"]+/", "C:/Users/USUARIO/", txt)
    txt = re.sub(r"C:\\\\Users\\\\[^\\\"]+\\\\", r"C:\\\\Users\\\\USUARIO\\\\", txt)
    return txt


def main(nome):
    P = R / nome
    d = json.loads((P / "draft_content.json").read_text(encoding="utf-8"))
    drafts = {x["id"]: x for x in d["materials"]["drafts"]}
    placeholder = lambda dd: {x["id"] for x in dd["materials"].get("videos", []) if x.get("extra_type_option") == 2}

    # raiz: segmento do Corpo (placeholder de composto) e a musica
    vt = [t for t in d["tracks"] if t["type"] == "video"][0]
    corpo_seg = vt["segments"][0]
    corpo_id = [r for r in corpo_seg["extra_material_refs"] if r in drafts][0]
    corpo = drafts[corpo_id]
    musica = next(s for t in d["tracks"] if t["type"] == "audio" for s in t["segments"])

    # dentro do Corpo: segmento que aponta pro composto de cortes (trilha principal) e o da legenda (sobreposicao)
    cd = corpo["draft"]; ph = placeholder(cd)
    cortes_seg = legenda_seg = None
    for t in cd["tracks"]:
        for s in t["segments"]:
            if s["material_id"] not in ph: continue
            alvo = drafts[[r for r in s["extra_material_refs"] if r in drafts][0]]["draft"]
            tem_texto = any(tt["type"] == "text" and len(tt["segments"]) > 3 for tt in alvo["tracks"])
            if tem_texto and legenda_seg is None: legenda_seg, legenda_id = s, [r for r in s["extra_material_refs"] if r in drafts][0]
            if not tem_texto and t.get("flag") == 0 and cortes_seg is None: cortes_seg, cortes_id = s, [r for r in s["extra_material_refs"] if r in drafts][0]
    cortes, legenda = drafts[cortes_id], drafts[legenda_id]

    # um corte de video e um texto normal (PublicSans) com tudo que referenciam
    cv = [t for t in cortes["draft"]["tracks"] if t["type"] == "video"][0]["segments"][0]
    txt_seg = None
    for t in legenda["draft"]["tracks"]:
        for s in t["segments"]:
            k, m = indice(legenda["draft"])[s["material_id"]]
            if PUBLICSANS in json.dumps(m) and txt_seg is None: txt_seg = s
    texto = peca(txt_seg, legenda["draft"], drafts)

    # stub e config de uma pasta subdraft limpa (a do composto de legenda)
    pasta = legenda["draft"]["id"]
    stub = json.loads((P / "subdraft" / pasta / "draft_content.json").read_text(encoding="utf-8"))
    cfg = json.loads((P / "subdraft" / pasta / "sub_draft_config.json").read_text(encoding="utf-8"))
    stub_esq = esqueleto(stub)

    entrada = {k: v for k, v in legenda.items() if k != "draft"}
    out = {
        "_origem": f"capturado de '{nome}' (edicao aprovada) por ferramentas/captura_moldes_legenda.py",
        "raiz": {"corpo": peca(corpo_seg, d, drafts), "musica": peca(musica, d, drafts)},
        "entrada_draft": entrada,
        "composto": {"corpo": esqueleto(corpo["draft"]), "cortes": esqueleto(cortes["draft"]), "legenda": esqueleto(legenda["draft"])},
        "dentro_corpo": {"cortes": peca(cortes_seg, cd, drafts), "legenda": peca(legenda_seg, cd, drafts)},
        "corte_video": peca(cv, cortes["draft"], drafts),
        "texto": texto,
        "trilha_modelo": sem_segmentos([t for t in legenda["draft"]["tracks"] if t["type"] == "text"][0]),
        "trilha_video_modelo": sem_segmentos([t for t in cortes["draft"]["tracks"] if t["type"] == "video"][0]),
        "trilha_audio_modelo": sem_segmentos([t for t in d["tracks"] if t["type"] == "audio"][0]),
        "stub": {"esqueleto": stub_esq, "segmento": peca(stub["tracks"][0]["segments"][0], stub, {stub["materials"]["drafts"][0]["id"]})},
        "sub_draft_config": cfg,
    }
    txt = limpa(json.dumps(out, ensure_ascii=False))
    j = json.loads(txt)
    for dd in (j["composto"]["corpo"], j["composto"]["cortes"], j["composto"]["legenda"], j["stub"]["esqueleto"]):
        for k in ("platform", "last_modified_platform"):
            if isinstance(dd.get(k), dict):
                for c in ("device_id", "hard_disk_id", "mac_address"): dd[k][c] = ""
    DESTINO.write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding="utf-8")
    print("gravado", DESTINO, f"{DESTINO.stat().st_size // 1024} KB")
    print("restos do usuario:", len(re.findall(r"Users/(?!USUARIO)", DESTINO.read_text(encoding="utf-8"))))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "João 2 - legendado")
