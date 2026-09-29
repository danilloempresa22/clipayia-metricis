"""Geração de sugestões de headlines baseadas localmente em palavras-chave e temas."""
import re
from collections import Counter


def limpa_texto(txt):
    """Remove pontuação e converte para minúsculas."""
    return re.sub(r'[^\w\s]', ' ', txt.lower()).split()


def palavras_chave(transcricao, top_n=10):
    """Extrai palavras-chave mais frequentes da transcrição.

    Remove palavras comuns (stopwords) em português.
    Retorna lista de (palavra, frequência)."""

    stopwords = {
        'o', 'a', 'os', 'as', 'um', 'uma', 'uns', 'umas', 'e', 'ou', 'mas',
        'de', 'do', 'da', 'dos', 'das', 'em', 'no', 'na', 'nos', 'nas',
        'por', 'para', 'com', 'sem', 'sob', 'sobre', 'entre', 'até',
        'que', 'qual', 'quais', 'quanto', 'quantos', 'quando', 'onde',
        'como', 'porquê', 'porque', 'pq', 'tb', 'tbm', 'né',
        'é', 'são', 'sou', 'foi', 'fui', 'somos', 'fomos', 'era', 'eram',
        'tenho', 'tem', 'temos', 'tinha', 'tinham', 'tive', 'teve', 'tivemos',
        'vou', 'vai', 'vamos', 'vou', 'ia', 'iam', 'irei', 'irá',
        'este', 'esse', 'aquele', 'esta', 'essa', 'aquela', 'isto', 'isso', 'aquilo',
        'eu', 'tu', 'ele', 'ela', 'nós', 'vós', 'eles', 'elas', 'meu', 'seu', 'nosso',
        'me', 'te', 'se', 'nos', 'vos', 'lhe', 'lhes', 'mim', 'ti', 'si',
        'à', 'ao', 'aos', 'ão', 'ões', 'inha', 'inhas', 'inho', 'inhos',
        'muito', 'pouco', 'mais', 'menos', 'todo', 'nenhum', 'outro', 'mesmo',
        'aí', 'ali', 'aqui', 'acolá', 'lá', 'cá', 'pra', 'pro',
        'vc', 'vcs', 'ó', 'ah', 'ok', 'hm', 'hmm',
    }

    palavras = limpa_texto(transcricao)
    # Filtra: apenas palavras com 3+ caracteres, não stopwords
    palavras_filtradas = [p for p in palavras if len(p) >= 3 and p not in stopwords]

    if not palavras_filtradas:
        return []

    contador = Counter(palavras_filtradas)
    return contador.most_common(top_n)


def tema_central(transcricao):
    """Detecta o tema central baseado na palavra mais frequente e contexto.

    Retorna um dicionário com 'tema', 'freq', e 'palavra_chave'."""
    chaves = palavras_chave(transcricao, top_n=5)

    if not chaves:
        return {"tema": "vida", "freq": 0, "palavra_chave": "vida"}

    palavra_principal, freq = chaves[0]

    # Mapa de temas (pode expandir)
    mapa_temas = {
        "instagram": "instagram",
        "tiktok": "redes sociais",
        "youtube": "youtube",
        "content": "criação de conteúdo",
        "conteúdo": "criação de conteúdo",
        "dinheiro": "ganhar dinheiro",
        "ganhar": "ganhar dinheiro",
        "renda": "renda extra",
        "saúde": "saúde",
        "fitness": "fitness",
        "treino": "treino",
        "emagrecimento": "emagrecimento",
        "corpo": "transformação corporal",
        "beleza": "beleza",
        "make": "maquiagem",
        "produtividade": "produtividade",
        "hábito": "hábitos",
        "sucesso": "sucesso",
        "negócio": "negócio",
        "empreendimento": "empreendimento",
        "vendas": "vendas",
        "marketing": "marketing",
        "técnica": "técnica",
        "hack": "dica",
        "segredo": "segredo",
        "truque": "truque",
    }

    tema = mapa_temas.get(palavra_principal, palavra_principal)

    return {
        "tema": tema,
        "freq": freq,
        "palavra_chave": palavra_principal
    }


def gera_sugestoes(transcricao, num_sugestoes=5):
    """Gera sugestões de headlines baseadas na transcrição.

    Usa:
    1. Palavras-chave mais frequentes
    2. Tema central detectado
    3. Templates de headlines virais

    Retorna lista de strings (headlines)."""

    # Coleta info
    chaves = palavras_chave(transcricao, top_n=8)
    tema_info = tema_central(transcricao)

    if not chaves:
        # Fallback se não encontrar palavras-chave
        return [
            "DESCUBRA COMO COMEÇAR",
            "O SEGREDO QUE NINGUÉM CONTA",
            "VOCÊ NÃO ESTÁ FAZENDO CERTO",
            "MUDE SUA VIDA AGORA",
            "APRENDA ISSO HOJE"
        ]

    # Extrai palavras-chave principais (sem frequência)
    top_palavras = [p[0] for p in chaves[:3]]
    tema = tema_info["tema"]

    # Templates de headlines virais
    templates = [
        f"O SEGREDO DO {top_palavras[0].upper()}",
        f"COMO {top_palavras[0].upper()} EM 30 DIAS",
        f"POR QUE VOCÊ NÃO {top_palavras[0].upper()}",
        f"A VERDADE SOBRE {top_palavras[0].upper()}",
        f"{top_palavras[0].upper()} QUE FUNCIONA",
        f"APRENDA {top_palavras[0].upper()} AGORA",
        f"NUNCA MAIS FAÇA ISSO EM {top_palavras[0].upper()}",
        f"VOCÊ ESTÁ ERRADO SOBRE {top_palavras[0].upper()}",
        f"O TRUQUE DO {top_palavras[0].upper()}",
        f"ISSO VAI MUDAR SEU {top_palavras[0].upper()}",
        f"DESCUBRA O {top_palavras[0].upper()}",
        f"ANTES E DEPOIS: {top_palavras[0].upper()}",
        f"3 DICAS DE {top_palavras[0].upper()}",
        f"A FORMA CERTA DE {top_palavras[0].upper()}",
        f"PARE DE {top_palavras[0].upper()} ERRADO",
    ]

    # Se houver segunda palavra-chave, adiciona variações
    if len(top_palavras) > 1:
        templates.extend([
            f"{top_palavras[0].upper()} + {top_palavras[1].upper()}",
            f"COMO USAR {top_palavras[1].upper()}} EM {top_palavras[0].upper()}",
            f"{top_palavras[1].upper().title()} PARA {top_palavras[0].upper()}",
        ])

    # Se houver terceira palavra-chave, adiciona mais
    if len(top_palavras) > 2:
        templates.extend([
            f"{top_palavras[2].upper()} QUE FUNCIONA",
            f"COMBINE {top_palavras[0].upper()}, {top_palavras[1].upper()} E {top_palavras[2].upper()}",
        ])

    # Seleciona as melhores (primeiras N)
    sugestoes = templates[:num_sugestoes]

    return sugestoes
