"""Plano e cobranca: AINDA NAO EXISTEM planos nem pagamentos de verdade. Este e' o UNICO lugar com valores de exemplo
(nada de numero espalhado pelo codigo). Quando a cobranca real existir, troque a fonte em dados() e desligue DEMO.
Real hoje (do Supabase): so o status da conta (ativa/inativa). Todo o resto abaixo e' exemplo.
DEMO = False e sem dado real: a tela esconde o que depende disso (nao inventa nada)."""
from datetime import date, timedelta

DEMO = True

PLANOS = [  # exemplo
    {"id": "basic", "nome": "Clipay Basic", "preco": 67.0, "descricao": "Só cortes de live e similares."},
    {"id": "ascendy", "nome": "Clipay Ascendy", "preco": 197.0, "descricao": "Cortes + headline, iPad + apresentador e edições básicas."},
    {"id": "premium", "nome": "Clipay Premium", "preco": 249.0, "descricao": "Todas as funções liberadas."},
]
PLANO_ATUAL = "premium"            # exemplo
PAGAMENTO = "Cartão final 4242"    # exemplo (o app nunca pede nem guarda dado de cartao)


def _ciclo(hoje):
    """exemplo: o ciclo e' o mes corrente (comeca no dia 1, renova no dia 1 do mes seguinte)"""
    ini = hoje.replace(day=1)
    fim = (ini + timedelta(days=32)).replace(day=1)
    return ini, fim


def dados(status_real=None, hoje=None):
    """o que a aba Plano e cobranca (e o cabecalho da Conta, a pilula do Inicio, o menu da conta) mostram"""
    if not DEMO:
        return {"demo": False, "status": status_real}           # sem dado real de plano: a tela esconde o resto
    hoje = hoje or date.today()
    ini, fim = _ciclo(hoje)
    plano = next(p for p in PLANOS if p["id"] == PLANO_ATUAL)
    hist = []
    d = ini
    for _ in range(3):
        hist.append({"data": d.isoformat(), "descricao": f"{plano['nome']} · mensalidade", "valor": plano["preco"], "status": "Pago"})
        d = (d - timedelta(days=1)).replace(day=1)
    return {"demo": True, "status": status_real, "plano": plano, "planos": PLANOS,
            "inicio": ini.isoformat(), "renova": fim.isoformat(), "dias_total": (fim - ini).days,
            "dias_restantes": max(0, (fim - hoje).days), "proxima": {"valor": plano["preco"], "data": fim.isoformat(), "forma": PAGAMENTO},
            "historico": hist}
