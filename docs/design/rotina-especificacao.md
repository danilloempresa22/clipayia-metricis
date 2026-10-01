# Rotina — Especificação técnica

Quarto modo de edição do Clipay.ia (junto de Cortes + Headline, Legenda Complexa e Apresentador + iPad). É o formato de "rotina" / vlog que o Danillo faz pro Ale Ferreira: cortes, relógio falso no canto jogando o tempo pra frente a cada corte, headline no começo, velocidade levemente acelerada, filtro e música de fundo.

## O que o usuário tem e o que recebe

**Entrada:** um vídeo bruto de rotina (ou vários clipes em ordem) e, opcionalmente, uma música da biblioteca dele.

**Saída:** um projeto novo do CapCut com os trechos cortados, relógio no canto superior direito, headline no início, filtro, velocidade final 1,13x e música com abaixamento de volume na fala.

## Regra de produto (vale pra todos os modos)

Sem IA em decisão criativa. O texto da headline, onde a atividade muda e quanto tempo pula no relógio são **do usuário**. O app calcula tempos, aplica os valores e monta o projeto.

## Fluxo

1. **Escolher o vídeo** (e a música, se quiser).
2. **Cortes:** o app calcula os trechos pelo áudio, com a mesma régua de silêncio dos outros modos (ver abaixo). O usuário vê a lista de trechos e pode apagar ou ajustar qualquer um.
3. **Relógio:** o usuário define o horário inicial (ex.: 07:30). Cada trecho começa marcado como "mesma cena". O usuário pode marcar qualquer trecho como "mudou a atividade" e escolher o salto (ver abaixo). O app mostra a lista com o horário que vai aparecer em cada trecho.
4. **Headline:** texto digitado pelo usuário.
5. **Música:** escolher o arquivo e o volume.
6. **Gerar:** monta, verifica e grava o projeto novo no CapCut (pasta nova, nunca sobrescreve).

## Cortes

**Ponto a confirmar com o Danillo: o tamanho dos cortes da rotina.** A única régua que está registrada é a do corte por palavra (silêncio a partir de 250 ms vira corte, folga de 60 ms por lado em frase e 150/200 ms em palavra curta isolada, remover gaguejada e muleta isolada). Não há uma régua específica da rotina salva. Então:

- Padrão do modo: a régua acima.
- Expor na tela dois controles pro usuário ajustar: "silêncio mínimo pra cortar" (ms) e "duração mínima de um trecho" (s).
- Quando o Danillo confirmar o tamanho dos cortes da rotina (por exemplo, trechos de 2 a 4 s), trocar o padrão por esse valor.

## Relógio

- **Posição:** canto superior direito, mesma posição, mesma fonte, mesmo tamanho e mesma cor o vídeo inteiro. Formato `HH:MM`.
- **Um texto por trecho.** Cada trecho mostra o horário daquele momento; ao começar o próximo trecho, o relógio troca. O horário aparece e some junto com o trecho, sem animação de transição.
- **Salto de tempo entre trechos (decisão do usuário):**
  - "Mesma cena" (padrão): salto curto, de 1 a 3 min. O app usa o valor do campo "salto padrão" (padrão 2 min) e o usuário pode editar por trecho.
  - "Mudou a atividade": o usuário digita o salto (de alguns minutos até 40+ min).
  - O horário pode virar a hora (07:58 + 5 min = 08:03) e passar da meia-noite (23:50 + 20 min = 00:10).
- **O app nunca decide o salto sozinho.** O que ele faz é aplicar o padrão e mostrar a lista pra o usuário corrigir.
- **Fonte e tamanho:** o Danillo não passou a fonte nem o tamanho do relógio. Deixar como configuração do modo, com uma fonte do catálogo do CapCut como padrão, e **avisar na tela** se a fonte escolhida não puder ser aplicada (nunca trocar em silêncio). A confirmar com ele.
- **Margem:** o texto fica a 4% da borda superior e da borda direita; com fator de segurança 1,3 na largura, nada sai da tela.

## Headline

- Texto digitado pelo usuário, fonte **Classic** do CapCut, no **começo** do vídeo. (Na skill antiga a headline da rotina ficava no meio do vídeo; ele pediu agora no começo, então o padrão é o início. Deixar o momento ajustável.)
- Posição: topo do quadro, centralizada, **abaixo da zona do relógio** pra os dois não se tocarem. Duração padrão ~5 s, ajustável.
- Referência de conteúdo, só pra ajudar o usuário a escrever (o app não gera nada): a headline é uma promessa ou uma ordem, nunca uma descrição; 3 a 8 palavras, uma linha (duas no máximo), sem dois-pontos.

## Acabamento

- **Velocidade 1,13x.** No MVP, aplicar a velocidade em cada segmento, **sem clipe composto** externo (ele só era necessário pra juntar legenda e cortes; aqui não tem legenda complexa). Os tempos do relógio e da headline são calculados na timeline já com a velocidade aplicada.
- **Filtro Aprimorar** (id `7289393505166692866`) na trilha de filtro, intensidade 60, cobrindo todo o vídeo.
- **Música de fundo:** biblioteca do usuário (pasta que ele prepara); sempre perguntar qual. Volume de música na fala ~0,21 e, no silêncio, 1,0, com rampa de 0,4 a 0,8 s, via keyframes de volume (`common_keyframes`, `property_type: "KFTypeVolume"`). A fala vem da mesma detecção de áudio dos cortes. Ele quer fala audível, então o valor de fala é configurável.
- Sem marca d'água nem fade no MVP; ficam como opção se ele pedir.

## Verificação antes de gravar (travar e avisar, não gravar projeto quebrado)

1. Nenhum `source` passa da duração do arquivo original; nenhum trecho passa da duração do projeto; sem sobreposição no mesmo trilho.
2. O relógio tem exatamente um texto por trecho, sem buraco nem sobreposição no tempo, e todos na mesma posição.
3. Os horários crescem sempre (nunca voltam), contando a virada de hora e de meia-noite.
4. Toda referência de material resolve pra um arquivo que existe no disco (vídeo, música).
5. Nenhum texto sai da tela (fator 1,3), e relógio e headline não se sobrepõem no espaço.
6. A velocidade de todos os segmentos é a mesma e os tempos da timeline foram calculados com ela.

## Fora de escopo por enquanto

- Escolher o salto de tempo ou o momento da headline com IA.
- Escolher música automaticamente.
- Legenda automática na rotina (ele não pediu).
- Clipe composto externo.

## Notas de implementação (2026-10-01)

- **Velocidade exata:** cada trecho tem duração na timeline em quadros inteiros e `source = timeline × 1,13` (µs). Assim todos os segmentos ficam com `speed` exatamente 1,13 e o CapCut não reajusta a velocidade (ele arredonda a timeline pra quadros inteiros; fora disso já mexeu sozinho na velocidade, visto 0,9987).
- **Filtro:** formato copiado do projeto "Advisor Ale 1 - corte v2": trilha `filter`, segmento sem `source`, material em `materials.effects` (`type: "filter"`); a intensidade é `value` (60 → 0,6).
- **Volume da música:** `KFTypeVolume` com valores lineares (como no projeto "Receita normal reels teste"). A música começa em 0 na origem e na timeline, então o tempo do keyframe é o mesmo da timeline.
- **Duração mínima do trecho:** um trecho mais curto que o mínimo é juntado ao vizinho mais próximo (se a pausa entre eles for curta), em vez de apagado: nunca some fala. 0 = desligado (padrão, até o Danillo confirmar).
