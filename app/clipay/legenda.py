"""Modo LEGENDA COMPLEXA — a parte que nao mexe no formato do CapCut: corte por palavra, marcadores de enfase,
alinhamento do texto editado com o tempo das palavras e a matematica da legenda acumulada em escada.
Numeros calibrados nas edicoes aprovadas (docs/design/legenda-complexa-especificacao.md). Nao inventar valores aqui."""
import difflib, json, re, unicodedata
from pathlib import Path
import numpy as np
from . import audio

# ---------------- corte por palavra (segundos) ----------------
CORTE_MIN = 0.250                     # silencio entre palavras a partir daqui vira corte
TRECHO_CURTO = 0.800                  # trecho de fala ate aqui = palavra curta isolada
PAD_CURTO = (0.150, 0.200)            # (antes, depois) — senao o corte come a palavra
PAD_FRASE = (0.060, 0.060)            # a cauda longa e' so ar
GAGUEJADA = 0.400                     # palavra repetida colada abaixo disso: fica a segunda
MULETAS = {"é", "tá", "e", "né", "ó", "tipo"}

# ---------------- legenda acumulada (unidades de tela do CapCut; tela inteira = 2.0) ----------------
X_LINHA = -0.58
DEGRAU = 0.050
Y0 = 0.38
ALT_LINHA = 0.115
LARG_LINHA = 0.55
MAX_PAL_LINHA = 2
MAX_LINHAS_NORMAIS = 2
MAX_LINHAS = 3
MARGEM = 0.04
ESC_BASE = 0.45273892468443844
SEGURANCA = 1.3                       # fator de seguranca na largura (fonte real mais larga que a estimativa)

# ---------------- enfase: escala pela largura, nunca fixa ----------------
LARG_ALVO_ENFASE = 0.45
K_LARGURA = 0.000705                  # calibrado com getlength em Liberation Sans/Arial tamanho 100
TAM_MEDIDA = 100
ENFASE_Y = (0.06, 0.29)
ENFASE_X = (-0.58, -0.41)
ESC_ENFASE_ZOOM = (0.50, 0.95)        # zoom ligado: palavra grande tampa o rosto
ESC_ENFASE_ABERTO = (0.49, 1.33)      # enquadramento aberto: pode estourar

_LARG = json.loads((Path(__file__).resolve().parent / "assets" / "larguras_arial.json").read_text(encoding="utf-8"))


def getlength(txt, tam=TAM_MEDIDA):
    """= ImageFont.truetype(LiberationSans-Regular, tam).getlength(txt), sem precisar da fonte instalada"""
    c = _LARG["chars"]
    return sum(c.get(ch, _LARG["padrao"]) for ch in txt) * tam


def largura_tela(txt, esc):
    """largura na tela (unidades de 2.0) de um texto na escala esc — mesma calibracao da formula da enfase"""
    return getlength(txt) * K_LARGURA * esc / ESC_BASE


def escala_enfase(txt, zoom):
    esc = LARG_ALVO_ENFASE * ESC_BASE / (max(getlength(txt), 1.0) * K_LARGURA)
    lo, hi = ESC_ENFASE_ZOOM if zoom else ESC_ENFASE_ABERTO
    return max(lo, min(hi, esc))


def norm(p):
    """forma de comparacao de uma palavra: sem acento, sem pontuacao, sem marcadores, minuscula"""
    p = unicodedata.normalize("NFD", p.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(ch for ch in p if unicodedata.category(ch) != "Mn"))


# ---------------- 1. corte ----------------
def cortes(palavras, dur):
    """palavras: [{"t","a","b"}] em s. Devolve (keep [[a,b]], palavras mantidas).
    Por palavra, nunca por bloco: cortar por bloco desloca o tempo da legenda e ela entra por cima da anterior."""
    ps = sorted((dict(p) for p in palavras if p["t"].strip()), key=lambda p: p["a"])
    limpas = []
    for i, p in enumerate(ps):                               # gaguejada: repeticao colada -> fica a segunda
        q = ps[i + 1] if i + 1 < len(ps) else None
        if q and norm(p["t"]) and norm(p["t"]) == norm(q["t"]) and q["a"] - p["b"] < GAGUEJADA:
            continue
        limpas.append(p)
    trechos = []
    for p in limpas:
        if trechos and p["a"] - trechos[-1][-1]["b"] <= CORTE_MIN:
            trechos[-1].append(p)
        else:
            trechos.append([p])
    trechos = [t for t in trechos if not (len(t) == 1 and norm(t[0]["t"]) in {norm(m) for m in MULETAS})]
    keep = []
    for t in trechos:
        a, b = t[0]["a"], t[-1]["b"]
        pre, pos = PAD_CURTO if b - a <= TRECHO_CURTO else PAD_FRASE
        a, b = audio.na_grade(max(0.0, a - pre), min(dur, b + pos))
        b = min(b, float(np.floor(dur * audio.FPS) / audio.FPS))
        if keep and a <= keep[-1][1]:
            keep[-1][1] = max(keep[-1][1], b)
        else:
            keep.append([a, b])
    return [[a, b] for a, b in keep], [p for t in trechos for p in t]


def a_partir_de(keep, palavras, inicio):
    """corta a rampa de abertura: tudo antes do inicio (s, na origem) sai"""
    if inicio is None:
        return keep, palavras
    corte = float(np.floor(inicio * audio.FPS + 1e-6) / audio.FPS)     # na grade de quadros, como o resto dos cortes
    out = [[max(a, corte), b] for a, b in keep if b > corte]
    return [k for k in out if k[1] - k[0] > 0.05], [p for p in palavras if p["a"] >= inicio - 1e-6]


def mapa_tempo(keep):
    """tempo na origem (s) -> tempo na timeline cortada (s). Tempo num buraco vai pro inicio do proximo pedaco."""
    acum, pos = [], 0.0
    for a, b in keep:
        acum.append((a, b, pos)); pos += b - a
    def f(t):
        for a, b, p in acum:
            if t < a: return p
            if t <= b: return p + t - a
        return pos
    return f, pos


# ---------------- 2. texto editado ----------------
_TOKEN = re.compile(r"\[[^\]]+\]|\*[^*\s][^*]*\*|\S+")


def tokens(texto):
    """texto do usuario -> [{"txt","tipo"}]. tipo: normal | soco ([..]) | leve (*..*) | pergunta (termina em ?).
    Marcadores ficam visiveis na tela (decisao de produto: igual as edicoes aprovadas)."""
    out = []
    for m in _TOKEN.finditer(texto):
        t = m.group(0)
        if t.startswith("[") and t.endswith("]"): tipo = "soco"
        elif len(t) > 2 and t.startswith("*") and t.endswith("*"): tipo = "leve"
        elif t.endswith("?") and len(t) > 1: tipo = "pergunta"
        else: tipo = "normal"
        out.append({"txt": t, "tipo": tipo})
    if out:
        t = out[0]["txt"]
        i = next((k for k, ch in enumerate(t) if ch.isalpha()), None)
        if i is not None: out[0]["txt"] = t[:i] + t[i].upper() + t[i + 1:]     # primeira palavra com maiuscula
    return out


def alinha(toks, palavras):
    """da tempo (s, origem) a cada token do texto editado, casando com as palavras transcritas.
    Palavra digitada que nao existe no audio herda o tempo entre as vizinhas."""
    a = [norm(t["txt"].split()[0] if t["txt"].split() else "") for t in toks]
    b = [norm(p["t"]) for p in palavras]
    tempo = [None] * len(toks)
    for bl in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        if bl.size == 1 and len(a[bl.a]) < 4:
            continue                         # "que", "e", "é" sozinhos casam com a ocorrencia errada e puxam as vizinhas
        for k in range(bl.size):
            tempo[bl.a + k] = palavras[bl.b + k]["a"]
    # casamento aproximado para quem sobrou (erro de transcricao corrigido a mao): mesma posicao relativa
    conhecidos = [(i, t) for i, t in enumerate(tempo) if t is not None]
    for i in range(len(toks)):
        if tempo[i] is not None: continue
        ant = max((c for c in conhecidos if c[0] < i), default=None, key=lambda c: c[0])
        dep = min((c for c in conhecidos if c[0] > i), default=None, key=lambda c: c[0])
        if ant and dep:
            tempo[i] = ant[1] + (dep[1] - ant[1]) * (i - ant[0]) / (dep[0] - ant[0])
        elif ant:
            tempo[i] = ant[1] + 0.25 * (i - ant[0])
        elif dep:
            tempo[i] = max(0.0, dep[1] - 0.25 * (dep[0] - i))
        else:
            tempo[i] = palavras[0]["a"] + 0.3 * i if palavras else 0.3 * i
    for i in range(1, len(tempo)):                           # nunca volta no tempo
        tempo[i] = max(tempo[i], tempo[i - 1] + 0.01)
    return [dict(t, t0=tempo[i]) for i, t in enumerate(toks)]


# ---------------- 3. legenda acumulada ----------------
def clamp_x(x, txt, esc):
    meia = largura_tela(txt, esc) / 2
    return max(x, -1.0 + meia * SEGURANCA + MARGEM)


def _nova_linha(g, tk, zoom):
    """posicao da proxima linha do grupo g para o token tk, ou None se nao cabe (entao abre grupo novo)"""
    li = len(g)
    if li >= MAX_LINHAS:
        return None
    if tk["tipo"] == "normal":
        if any(l["tipo"] != "normal" for l in g) or sum(l["tipo"] == "normal" for l in g) >= MAX_LINHAS_NORMAIS:
            return None                                      # linha normal nunca abaixo de uma enfase
        return {"tipo": "normal", "pal": [tk], "esc": ESC_BASE, "alt": ALT_LINHA,
                "y": Y0 - li * ALT_LINHA, "x0": X_LINHA + li * DEGRAU}
    esc = escala_enfase(tk["txt"], zoom)
    alt = ALT_LINHA * esc / ESC_BASE
    if g:                                                    # topo da enfase encosta embaixo da linha anterior
        ant = g[-1]
        y = ant["y"] - (ant["alt"] + alt) / 2
    else:
        y = ENFASE_Y[1]
    y = min(ENFASE_Y[1], y)
    if y < ENFASE_Y[0]:
        return None
    return {"tipo": tk["tipo"], "pal": [tk], "esc": esc, "alt": alt, "y": y,
            "x0": max(ENFASE_X[0], min(ENFASE_X[1], X_LINHA + li * DEGRAU))}


def _cabe_na_linha(l, tk):
    return (l["tipo"] == "normal" and tk["tipo"] == "normal" and len(l["pal"]) < MAX_PAL_LINHA
            and largura_tela(" ".join(p["txt"] for p in l["pal"] + [tk]), ESC_BASE) <= LARG_LINHA)


def monta(toks, fim, zoom):
    """toks com t0 JA na timeline cortada. Devolve segmentos de texto:
    [{"txt","tipo","ini","fim","x","y","esc","linha"}] (s). Cada linha e' UM objeto de texto por estado
    (o espacamento entre palavras e' o CapCut que faz)."""
    grupos = []
    for tk in toks:
        g = grupos[-1] if grupos else None
        if g and _cabe_na_linha(g[-1], tk):
            g[-1]["pal"].append(tk); continue
        l = _nova_linha(g, tk, zoom) if g else None
        if l is None:
            g = []; grupos.append(g)
            l = _nova_linha(g, tk, zoom)
        g.append(l)
    segs = []
    for gi, g in enumerate(grupos):
        g_fim = grupos[gi + 1][0]["pal"][0]["t0"] if gi + 1 < len(grupos) else fim     # sai so quando o proximo comeca
        for li, l in enumerate(g):
            y, esc, x0 = l["y"], l["esc"], l["x0"]
            for k, p in enumerate(l["pal"]):                  # estado k: da palavra k ate a palavra k+1
                txt = " ".join(q["txt"] for q in l["pal"][:k + 1])
                ini = p["t0"]
                fim_k = l["pal"][k + 1]["t0"] if k + 1 < len(l["pal"]) else g_fim
                if fim_k - ini < 0.02: continue
                x = clamp_x(x0, txt, esc)
                segs.append({"txt": txt, "tipo": l["tipo"], "ini": round(ini, 4), "fim": round(fim_k, 4),
                             "x": round(x, 4), "y": round(y, 4), "esc": esc, "linha": (gi, li)})
    return segs


# ---------------- 4. verificacao da legenda (antes de montar o JSON) ----------------
def verifica(segs, dur):
    """itens 1, 4 e 5 da checklist que dependem so da legenda. Devolve lista de problemas (vazia = ok)."""
    erros = []
    # 1. sobreposicao por altura Y (a checagem por trilha NAO pega): duas legendas visiveis ao mesmo tempo
    # cuja faixa vertical se cruza. Faixa = 90% da altura da linha (linhas vizinhas da escada so encostam).
    faixa = lambda s: (s["y"] - 0.45 * ALT_LINHA * s["esc"] / ESC_BASE, s["y"] + 0.45 * ALT_LINHA * s["esc"] / ESC_BASE)
    ordem = sorted(segs, key=lambda s: s["ini"])
    for i, p in enumerate(ordem):
        for q in ordem[i + 1:]:
            if q["ini"] >= p["fim"] - 1e-3: break
            (a0, a1), (b0, b1) = faixa(p), faixa(q)
            if min(a1, b1) - max(a0, b0) > 1e-4:
                erros.append(f"duas legendas na mesma altura ao mesmo tempo em {q['ini']:.2f}s: '{p['txt']}' e '{q['txt']}'")
    for s in segs:
        if s["ini"] < -1e-6 or s["fim"] > dur + 1e-3 or s["fim"] <= s["ini"]:   # 4. limites
            erros.append(f"legenda '{s['txt']}' fora da duração do vídeo ({s['ini']:.2f}–{s['fim']:.2f}s)")
        meia = largura_tela(s["txt"], s["esc"]) / 2 * SEGURANCA
        if s["x"] - meia < -1.0 or s["x"] + meia > 1.0:      # 5. vazando da tela
            erros.append(f"legenda '{s['txt']}' não cabe na tela")
    return erros
