"""Geração de headlines com Claude API."""
import os
import json
from pathlib import Path


def acha_api_key():
    """Procura por ANTHROPIC_API_KEY em variável de ambiente ou .env"""
    chave = os.environ.get("ANTHROPIC_API_KEY")
    if chave:
        return chave

    # Procura em .env na raiz do projeto
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for linha in f:
                    if "ANTHROPIC_API_KEY" in linha and "=" in linha:
                        _, valor = linha.split("=", 1)
                        return valor.strip().strip('"').strip("'")
        except Exception:
            pass

    return None


def gera_headlines(transcricao, num_sugestoes=3):
    """Gera headlines baseado na transcrição usando Claude API.

    Retorna lista de strings (headlines sugeridos).
    Se falhar, retorna lista vazia."""

    api_key = acha_api_key()
    if not api_key:
        print("AVISO: ANTHROPIC_API_KEY não encontrada. Não será possível gerar headlines com IA.")
        return []

    try:
        from anthropic import Anthropic
    except ImportError:
        print("AVISO: biblioteca 'anthropic' não instalada. Instale com: pip install anthropic")
        return []

    cliente = Anthropic(api_key=api_key)

    prompt = f"""Você é especialista em criar headlines virais para shorts e reels de video.

Baseado na seguinte transcrição de um vídeo, gere {num_sugestoes} headlines curtos, diretos e impactantes.

Headlines devem:
- Ter no máximo 8-10 palavras
- Ser provocadores e chamar atenção
- Ser em português do Brasil
- Ser específicos sobre o conteúdo do vídeo
- Ser colocados em maiúsculas
- Separados por quebras de linha se forem 2 linhas

TRANSCRIÇÃO:
{transcricao[:2000]}

Retorne APENAS os headlines, um por linha, sem numeração nem explicação."""

    try:
        mensagem = cliente.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=300,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        resposta = mensagem.content[0].text.strip()
        headlines = [h.strip() for h in resposta.split("\n") if h.strip()]
        return headlines[:num_sugestoes]

    except Exception as e:
        print(f"Erro ao chamar Claude API: {e}")
        return []
