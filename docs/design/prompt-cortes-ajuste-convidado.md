Preciso de três ajustes na seção **Cortes**, que mexem na Fase 2 (transcrição) e na Fase 3 (achar os cortes). Se você já fez parte da Fase 3, **adapte o que existe, não refaça**. Leia antes: `docs/design/cortes-especificacao.md` (seções 1.1, 3.1 e 3.2 foram atualizadas) e `docs/design/prompt-cortes-fase3.md` (atualizado). Depois me diga o plano em poucas linhas e espere eu dizer "pode seguir".

## 1. Trocar o tipo "Conselho" por "Insight"

Os tipos passam a ser: **História, Polêmico, Emocional, Engraçado e Insight**. Insight é quando a pessoa **ensina algo: um conhecimento ou uma sacada**. Troque em tudo: o pedido ao modelo, a validação e o filtro por tipo no código, a configuração, o nome do tipo nos projetos (`<vídeo> - corte 03 - Insight`) e os testes. Como as regras mudaram, **aumente a versão das regras** do cache, para análises antigas não serem reaproveitadas.

## 2. O foco é o convidado, não o apresentador (a mudança grande)

Em podcast há o **apresentador** (quem convida e pergunta) e o **convidado**. O corte é feito da fala do convidado. Regras, que vêm de exemplos reais meus:

- **Pergunta do apresentador não vira corte e não abre corte.** Mesmo que o apresentador comece com uma sacada boa antes de perguntar, aquele trecho não serve. O corte abre **na resposta do convidado**.
- O corte **começa na primeira frase do convidado** que abre o assunto e **termina na última frase do convidado** daquele assunto. Falas curtas do apresentador no meio ("hum", "sim", "é verdade", até uns 3 segundos) podem ficar dentro, mas a soma da fala do apresentador num corte tem que ser pequena (limite configurável, começando em 15% da duração). **Uma nova pergunta do apresentador encerra o corte.**
- **Abertura e encerramento do episódio não são corte**, mesmo que tenham uma frase boa: o apresentador cumprimentando, falando para as pessoas assistirem, apresentando o convidado, pedindo para curtir e se inscrever, anunciando patrocínio.
- Todo falante que não é o apresentador conta como convidado.

Isso exige saber **quem está falando**, e hoje a transcrição não sabe. Faça assim:

**Identificação das vozes (diarização local, sem enviar áudio).**
- Verifique se o `sherpa-onnx` que já usamos tem diarização offline (segmentação de falantes e embeddings de voz em onnx) e use isso. Se não der, **me diga e proponha uma alternativa antes de seguir**. Tudo roda no computador da pessoa.
- Cada frase da transcrição ganha um locutor (`A`, `B`…). Os rótulos têm que ser **consistentes no vídeo inteiro** (agrupamento global dos falantes, não janela por janela, senão o "A" de uma janela vira o "B" da outra). Me diga como resolveu.
- Rodar a diarização **não pode refazer a transcrição**: use o áudio e o cache da Fase 2 e grave o resultado no mesmo cache, por janela, retomável. Memória estável em 3 horas, como na Fase 2.
- **Quem é o apresentador:** por padrão, a voz que mais faz perguntas e tem as falas mais curtas. Mostre o palpite com o nível de confiança e deixe um parâmetro para eu trocar. (Na Fase 4 a pessoa poderá trocar na tela; por enquanto é um parâmetro.)
- O resultado de cada frase passa a ser `{id, ini, fim, locutor, papel, texto}`, com `papel` igual a `apresentador` ou `convidado`.

**Pedido ao modelo (Edge Function).** As frases chegam com o papel (`APRESENTADOR` ou `CONVIDADO`). O modelo recebe as regras acima como regras explícitas e continua só devolvendo ids. Para o cabeçalho de cada assunto, peça também o papel de quem abre e de quem fecha, para o código conferir.

**Validação no código** (além do que já existe): a primeira e a última frase do corte são do convidado; a fala do apresentador no corte fica abaixo do limite; o corte não começa dentro de uma pergunta do apresentador; abertura, encerramento, chamada para curtir e se inscrever e patrocínio são descartados. O que falhar é corrigido (por exemplo, começar na primeira frase do convidado) ou descartado.

## 3. Duração mínima

Baixe o mínimo de duração de 30 s para **20 s** (configurável). Dois cortes bons meus têm 25 e 26 segundos.

## 4. A régua de acerto: `tests/fixtures/cortes-ouro.json`

Crie o arquivo com os cortes que eu marquei. Por enquanto é um podcast; **vou mandar mais dois**, então a estrutura tem que aceitar vários vídeos e eu vou acrescentar.

O vídeo é o "Momento": `C:\Users\danil\Downloads\Qual foi o momento - Ale EP6.mp4` (confirme com ffprobe que tem a duração esperada e me diga se achar outro arquivo parecido). Tempos no vídeo original, em `h:mm:ss`:

Partes **boas** (o corte vai do começo do assunto até ele mudar):

| início | fim | tipo |
|---|---|---|
| 0:04:54 | 0:06:59 | História e Polêmico |
| 0:17:19 | 0:17:45 | Polêmico |
| 0:30:12 | 0:30:58 | Insight |
| 0:37:18 | 0:37:43 | Insight |
| 0:38:20 | 0:39:31 | Insight |

Partes **ruins** (não podem virar corte):

| início | fim | por quê |
|---|---|---|
| 0:01:05 | 0:01:39 | Abertura do episódio: o apresentador chamando as pessoas para assistir. Tem uma frase boa no começo, mas não é corte. |
| 0:37:43 | 0:38:16 | O apresentador fala uma sacada e depois faz uma pergunta ao convidado. Não pego fala do apresentador nem pergunta; o corte bom é a resposta, logo depois (38:20 a 39:31). |

Os tempos foram anotados à mão e podem estar uns 1 a 2 segundos imprecisos. Por isso a comparação é **por frase**, não por segundo: um corte da IA "acerta" um corte bom quando o começo e o fim caem a no máximo 1 frase de distância dos meus. Mostre sempre os tempos reais lado a lado.

## Como verificar

- **Locutores:** nos trechos acima, mostre quem a diarização diz que fala. Em 0:01:05 a 0:01:39 e 0:37:43 a 0:38:16 tem que ser o apresentador; em 0:38:20 a 0:39:31, o convidado. Me diga se o palpite de "quem é o apresentador" acertou.
- **Corte que já existe:** com o `cortes-ouro.json`, rode a análise (mock para a lógica e, **depois de eu aprovar o custo**, o modelo de verdade) e me mostre, para cada corte bom meu, qual corte da IA casou e a distância em frases do começo e do fim; e, para cada parte ruim, se a IA gerou algo ali com nota acima do piso. Me mostre também os cortes que a IA achou e **não estão** na minha lista, com primeira e última frase, que eu julgo.
- Casos de teste novos com respostas falsas do modelo: corte que abre com pergunta do apresentador, corte de abertura de episódio, corte com muita fala do apresentador. O código tem que corrigir ou descartar.
- **Caso do tiro** continua valendo: assunto inteiro, até o desfecho, sem a frase de transição.
- Mudar os tipos continua sem nova chamada nem cobrança. Duas análises iguais seguidas cobram uma só (com a versão nova das regras).
- Memória estável na diarização do vídeo de 70 minutos e do de 3 horas (repetido 3 vezes, em pasta temporária fora do projeto). Me diga os números.
- Rode os testes que já existem: Edição e Fases 1 e 2 não podem mudar.

## Não fazer agora

- Nada de tela de Cortes (Fase 4). Nada de IA fora de achar os cortes.
- Não mexa na Edição, no Dashboard nem na barra lateral.
- Atualize `docs/design/cortes-novo-fluxo.html` **só se** for preciso; ele já mostra os cinco tipos com Insight.
- Pare no fim e espere eu validar.
