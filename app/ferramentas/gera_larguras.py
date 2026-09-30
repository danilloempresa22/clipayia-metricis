"""Gera as tabelas de largura por caractere (em 'em') usadas pra dimensionar e conferir textos sem precisar da fonte.
- larguras_arial.json: Arial = Liberation Sans (a regua da enfase da Legenda Complexa mede nela, tamanho 100)
- larguras_proximanova_bold.json / larguras_classic.json: fontes do catalogo do CapCut usadas no Apresentador + iPad
Guardamos so os numeros (avanco por caractere), nao a fonte.
Uso (no computador de desenvolvimento, com as fontes do catalogo ja baixadas pelo CapCut): python ferramentas/gera_larguras.py"""
import json, os
from pathlib import Path
from fontTools.ttLib import TTFont

ASSETS = Path(__file__).resolve().parent.parent / "clipay" / "assets"
CACHE = Path(os.path.expandvars(r"%LOCALAPPDATA%\CapCut\User Data\Cache\effect"))
FONTES = {
    "larguras_arial.json": Path(r"C:\Windows\Fonts\arial.ttf"),
    "larguras_proximanova_bold.json": next(iter(sorted(CACHE.glob("7098268696795156993/*/*.ttf"))), None),
    "larguras_classic.json": next(iter(sorted(CACHE.glob("7545362071773367568/*/*.ttf"))), None),
}
chars = [chr(c) for c in range(32, 0x250)] + list("“”‘’–—…•ªº")
for nome, arq in FONTES.items():
    if not arq or not arq.exists():
        print("fonte nao encontrada, pulando:", nome); continue
    f = TTFont(arq, fontNumber=0)
    cmap, hm, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    tab = {c: round(hm[cmap[ord(c)]][0] / upm, 5) for c in chars if ord(c) in cmap}
    cap = round(getattr(f["OS/2"], "sCapHeight", 0) / upm, 4) if "OS/2" in f else 0
    (ASSETS / nome).write_text(json.dumps({"_origem": f"{arq.name}: avanco por caractere em em", "padrao": round(sum(tab.values()) / len(tab), 5),
                                           "altura_maiuscula": cap, "chars": tab}, ensure_ascii=False), encoding="utf-8")
    print(len(tab), "caracteres ->", nome)
