"""Cortes + Headline, melhorias medidas no "edit ale 1" (a edicao feita a mao em cima do que o app gerou):
comeco de cada trecho mais justo, sugestoes de sobra (tropeco e conversa no final) e tirar o que a pessoa confirmou."""
import numpy as np
from clipay import reels
from clipay.audio import H, FPS


def _p(*ws):
    """palavras [(texto, a, b)] -> formato do transcritor"""
    return [{"t": t, "a": a, "b": b} for t, a, b in ws]


def test_tropeco_de_quem_se_corrige_e_conversa_no_final():
    pal = _p(("Ao", 5.7, 5.9), ("invés", 5.9, 6.3), ("disso,", 6.3, 6.7), ("seja", 6.8, 7.2), ("efetivo.", 7.2, 8.0),
             ("Dá", 8.08, 8.4), ("substantivo,", 8.4, 9.2), ("não", 9.3, 9.6), ("pode.", 9.6, 10.08),
             ("Adjetivo", 10.39, 11.0), ("para", 11.0, 11.3), ("as", 11.3, 11.4), ("coisas.", 11.4, 12.0),
             ("Então", 52.16, 52.5), ("dessa", 52.5, 52.8), ("forma", 52.8, 53.0), ("que", 53.0, 53.1), ("eu", 53.1, 53.15), ("faria.", 53.15, 53.23),
             ("Fechou?", 53.87, 54.21), ("Fechou.", 54.53, 54.77), ("Boa!", 55.85, 56.13))
    s = reels.sobras(pal)
    assert [x["tipo"] for x in s] == ["tropeco", "final"]
    assert (s[0]["a"], s[0]["b"]) == (8.08, 10.39) and "não pode" in s[0]["texto"]        # ate a fala certa comecar
    assert s[1]["texto"] == "Fechou? Fechou. Boa!" and 53.23 < s[1]["a"] < 53.87 and s[1]["b"] > 56.13


def test_sem_falso_alarme_em_conversa_normal():
    # repeticao de enfase e "nao pode" no meio de uma frase longa: nada
    pal = _p(("Ah", 0.0, 0.1), ("não,", 0.1, 0.3), ("bizarro,", 0.3, 0.7), ("bizarro,", 0.7, 1.1), ("foi", 1.1, 1.3),
             ("muito", 1.3, 1.6), ("louco.", 1.6, 2.0), ("Você", 2.5, 2.7), ("não", 2.7, 2.9), ("pode", 2.9, 3.1),
             ("esquecer", 3.1, 3.5), ("de", 3.5, 3.6), ("conferir", 3.6, 4.0), ("o", 4.0, 4.1), ("contrato.", 4.1, 4.6),
             ("Não", 5.0, 5.2), ("é", 5.2, 5.3), ("um", 5.3, 5.4), ("erro.", 5.4, 5.8), ("É", 5.9, 6.0), ("um", 6.0, 6.1),
             ("erro", 6.1, 6.4), ("burro.", 6.4, 6.9))
    assert reels.sobras(pal) == []


def test_comeco_do_trecho_vai_pra_perto_da_voz():
    n = 400
    e = np.zeros(n); v = np.zeros(n)
    e[100:200] = 30.0; v[100:200] = 0.9                       # voz de 1,00 s a 2,00 s
    e[95:100] = 3.0                                           # respiro antes
    keep = reels.aperta_inicios(e, v, [[0.9, 2.1, False]])
    a = keep[0][0]
    assert 1.0 - 0.01 - 1 / FPS - 1e-6 <= a <= 1.0 and keep[0][1] == 2.1 and keep[0][2] is False
    assert reels.aperta_inicios(e, v, [[1.05, 2.1, True]])[0][0] == 1.05      # ja dentro da voz: nao mexe (nunca come fala)


def test_tirar_o_que_a_pessoa_confirmou_encosta_na_borda_do_trecho():
    pl = [{"clip": "v", "dur": 20.0, "keep": [[1.0, 3.0, False], [3.4, 6.0, False], [6.5, 9.0, True]]}]
    out = reels.tira_trechos(pl, [[3.55, 5.8]])                # a borda caiu a 0,15 s e 0,2 s do trecho: leva ele todo
    assert out[0]["keep"] == [[1.0, 3.0, False], [6.5, 9.0, True]]
    meio = reels.tira_trechos(pl, [[4.2, 5.0]])[0]["keep"]     # no meio do trecho: corta so ali
    assert meio == [[1.0, 3.0, False], [3.4, 4.2, False], [5.0, 6.0, False], [6.5, 9.0, True]]
    assert pl[0]["keep"][1] == [3.4, 6.0, False]               # a analise guardada nao muda
