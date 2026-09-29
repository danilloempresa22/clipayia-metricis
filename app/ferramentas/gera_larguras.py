"""Gera a tabela de larguras usada pra dimensionar a enfase (Legenda Complexa).
A regua original mede o texto com PIL getlength em Liberation Sans Regular tamanho 100; Arial tem exatamente
as mesmas larguras de letra. Guardamos so os numeros (avanco por caractere), nao a fonte.
Uso: python ferramentas/gera_larguras.py"""
import json
from pathlib import Path
from fontTools.ttLib import TTFont

f = TTFont(r"C:\Windows\Fonts\arial.ttf")
cmap, hm, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
chars = [chr(c) for c in range(32, 0x250)] + list("“”‘’–—…•ªº")
tab = {c: round(hm[cmap[ord(c)]][0] / upm, 5) for c in chars if ord(c) in cmap}
destino = Path(__file__).resolve().parent.parent / "clipay" / "assets" / "larguras_arial.json"
destino.write_text(json.dumps({"_origem": "Arial/Liberation Sans: avanco por caractere em em (x tamanho = pixels)",
                               "padrao": round(sum(tab.values()) / len(tab), 5), "chars": tab}, ensure_ascii=False), encoding="utf-8")
print(len(tab), "caracteres ->", destino)
