# Apresentador + iPad — Especificação técnica

Terceiro modo de edição do Clipay.ia (depois de Cortes + Headline e Legenda Complexa). Referência visual do resultado final: `resultado final ipad.mp4` (Downloads do Danillo; não versionado).

## O que o usuário tem e o que recebe

**Entrada:** dois vídeos gravados separados — a câmera com a pessoa falando (vertical) e a gravação de tela do iPad. Eles não começam no mesmo instante.

**Saída:** um projeto novo do CapCut, 1080x1920, com o iPad em cima (só a área escura do canvas, recortada) e a pessoa embaixo, sincronizados, cortados juntos, com zooms só na pessoa, legenda automática e headline no início.

## Decisão de produto: a sincronia é manual

Tentamos detectar o ponto de sincronia automaticamente por movimento e não deu certo: o apresentador repete os mesmos gestos, a tela do iPad aparece pequena e com reflexo na câmera, e as tentativas erraram em testes reais. Portanto **quem decide onde os vídeos batem é o usuário**, olhando os dois. O app faz o resto. Não tentar detectar nem "sugerir" o ponto de sincronia.

## Fluxo

1. **Selecionar os dois vídeos** (iPad e pessoa).
2. **Enquadrar (tela de layout):** prévia 1080x1920 com o iPad em cima e a pessoa embaixo.
   - Pessoa: escala e posição ajustáveis (arrastar/zoom) pra o rosto ficar onde o usuário quer. É esse enquadramento que os zooms depois usam como base.
   - iPad: recorte livre em volta da área escura do desenho (retângulo arrastável). O que fica fora do recorte é descartado.
3. **Sincronizar (tela de sincronia):** os dois vídeos lado a lado, cada um com controle de tempo. O usuário arrasta um deles (ou usa avançar/voltar 1 frame) até o mesmo momento bater, e tem um botão "tocar os dois juntos" pra conferir. Só depois de clicar "Está sincronizado" o app grava o ajuste. Tem também um botão "conferir o final": mostra os dois vídeos perto do fim, pra o usuário ver se não desalinhou.
4. **Legenda:** transcrição automática local, com tela de revisão pra o usuário corrigir o texto antes de gerar (sem IA reescrevendo).
5. **Headline:** o usuário digita o texto. Sem IA escrevendo.
6. **Gerar:** o app corta, aplica zooms, legenda e headline, roda a verificação e grava o projeto novo no CapCut.

## Cálculo da sincronia

O usuário marca o instante `t_ipad` no vídeo do iPad e `t_pessoa` no vídeo da pessoa, que mostram o mesmo momento. Então `offset = t_ipad - t_pessoa`.

- `offset >= 0`: o iPad começou a gravar antes. O clipe do iPad usa `source.start = offset` e a pessoa usa `source.start = 0`.
- `offset < 0`: a pessoa começou antes. A pessoa usa `source.start = -offset` e o iPad usa `0`.

Em CapCut tudo em microssegundos. Alinhar sempre no início da timeline (`target.start = 0`).

Validação: no projeto CapCut "0930" do Danillo (pasta `com.lveditor.draft`), o clipe do iPad tem `source.start = 9100000` e o vídeo "1.MOV" tem `source.start = 0`. Reproduzir esse resultado, com margem de 1 frame, usando os arquivos brutos completos, é um teste de aceitação.

## Cortes

- Calculados sobre o áudio da pessoa, com a mesma régua de silêncio do Cortes + Headline (`audio.py`/`reels.py`).
- Cada corte vale para os dois vídeos: a lista de trechos é a mesma, cada um com o `source.start` ajustado pelo offset da sincronia.
- **MVP sem clipe composto**: o app escreve direto os dois trilhos (iPad e pessoa) com a mesma lista de trechos. O composto fica como v2 opcional (ver `legenda-complexa-especificacao.md`, "Estrutura de clipe composto").

Ordem das faixas: pessoa embaixo (trilho principal), iPad em cima (trilho de sobreposição). Um zoom da pessoa que passa da borda de cima fica escondido atrás do iPad.

## Layout (referência: 720x1280, proporcional em 1080x1920)

- Área do iPad: do topo até ~34,7% da altura.
- Pessoa: dos ~34,7% até o fim, cobrindo a largura toda.
- Headline: logo acima da linha de divisão, centralizada (~28% a 31%).
- Legenda: centralizada, na altura do peito, ~72% da altura.

## Zooms (só na pessoa)

- Tabelas de punch-in do Cortes + Headline, aplicadas só ao trilho da pessoa; o iPad nunca recebe zoom.
- Toggle liga/desliga e slider de intensidade. Padrão ligado, intensidade moderada (na referência o zoom vai de 1,0 a ~1,25).

## Legenda automática

- Transcrição local (Whisper offline) com tempo por palavra, sobre o áudio da pessoa.
- Frases curtas de 2 a 4 palavras, MAIÚSCULAS, negrito, branco, sombra leve, sem contorno grosso. Cada grupo aparece enquanto é falado; nada na tela quando a pessoa está calada.
- Posição fixa: centralizada, ~72% da altura. Revisão do texto pelo usuário antes de gerar.
- Fonte do catálogo do CapCut; se não puder ser aplicada, avisar, nunca trocar em silêncio.

## Headline

- Texto digitado pelo usuário, 2 linhas, branco, sem serifa, sem contorno, centralizado logo acima da divisão.
- Duração padrão ~7 s a partir do início; ajustável.

## Prévia — cuidados técnicos

- Brutos enormes em HEVC/MOV: gerar **prévias leves H.264** só pras telas de enquadrar e sincronizar; a gravação final aponta pros originais.
- Servidor local responde `Range`.
- iPad pode vir com rotação nos metadados (1640x2360 gravado, 2360x1640 exibido): usar as dimensões de exibição.
- Taxa de quadros variável: sincronizar por tempo, nunca por número de quadro.

## Verificação antes de gravar (trava e avisa)

1. Os dois trilhos têm a mesma lista de trechos (`target`), e nenhum `source` sai da duração do arquivo.
2. Nenhum trecho ultrapassa a duração do projeto; sem sobreposição no mesmo trilho.
3. Todo material aponta para um arquivo que existe no disco.
4. Nenhum texto sai da tela (fator 1,3 na largura).
5. iPad acima da pessoa.

## Fora de escopo por enquanto

Detecção automática da sincronia · clipe composto · música de fundo, marca d'água, IA escrevendo headline ou texto.

---

## Notas de implementação (Clipay.ia, 2026-09-30)

Código: `app/clipay/ipad.py` (lógica), `processa.analisa_ipad` / `monta_ipad`, telas em `assets/index.html`.

- **Prévias**: `libopenh264` (o ffmpeg empacotado é LGPL, sem x264), 30 fps constantes, keyframe a cada 0,5 s, lado maior 854 px. Nos brutos reais: iPad 209,62 s → prévia 209,63 s (30 s pra gerar); 1.MOV 4K 204,71 s → 204,71 s (151 s). Cache por caminho+tamanho+data em `%APPDATA%\Clipay\temp\previas`.
- **Régua de texto no CapCut vertical** (medida em 3 capas renderizadas pelo próprio CapCut, Creato e Classic): ~94,2 px por (em × escala) com `font_size 15` em 1080x1920.
- **Headline**: molde do Cortes + Headline (fonte Classic), escala **0,623** (medida na referência: as duas linhas deram 0,623 e 0,625), centro a 29,6% → `y = 0,408`.
- **Legenda**: ProximaNova Bold do catálogo (`7098268696795156993`), escala **0,45** pela altura das maiúsculas da referência, centro a 72,6% → `y = -0,452`. Frase longa diminui até caber (1,3).
- **iPad**: `transform.y = 1 - altura_do_recorte_na_tela`; com o recorte do 0930 dá 0,68134 (0930: 0,68165).
- **Aceitação (0930)**: tela de sincronia → iPad em 9,0 s + 3 quadros = +9,100 s; projeto gerado nos brutos reais com todos os 74 trechos em `iPad.source - pessoa.source = 9100000`.
