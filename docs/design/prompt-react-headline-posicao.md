Preciso de 2 alterações no modelo **React** que você já construiu: a pessoa **escolhe o modelo da headline** e **ajusta a posição do vídeo de react** (hoje só dá para ajustar o vídeo de cima). **Adapte o que existe, não refaça o modelo.**

A referência visual **aprovada** é `docs/design/react-novo-fluxo.html`: abra no navegador, vá até o passo Enquadrar e teste as 3 abas, depois veja o passo Ajustes e o Gerar. A referência do modelo novo de headline está em `docs/design/referencia-headline/citacao/draft_content.json`, copiado do meu projeto "headline teste". Use **só a parte da headline** desse projeto. O resto (vídeos, escalas, máscara, CTA) continua vindo da referência do React (`docs/design/referencia-react/`).

Descubra e me diga:
- onde o motor do React monta a headline hoje;
- onde fica a posição do react na montagem;
- onde fica guardado o react salvo.

Depois me diga o plano em poucas linhas, **o que já existe que você vai reaproveitar**, e espere eu dizer "pode seguir".

## 1. Abas no passo Enquadrar

- O painel de controles ganha 3 abas no topo: **Vídeo de cima**, **React** e **Headline**.
- **Vídeo de cima:** tudo o que já existe (posição, zoom, área do react, aplicar a todos, voltar ao padrão), sem mudança.
- O celular da prévia destaca o que está sendo ajustado. Na aba React, a faixa de baixo ganha um contorno lime e a etiqueta "← React →". Na aba Headline, a caixa da headline ganha um contorno lime. Na aba do vídeo de cima, fica como hoje.
- O título do passo passa a ser "Confira o visual", com o texto do protótipo. O nome do passo na barra de progresso continua "Enquadrar".
- Tudo funciona por teclado: setas entre as abas, setas entre os modelos de headline e foco lime visível.

## 2. Posição do react

- **React horizontal** (o caso de hoje): ele é ampliado para preencher a altura da faixa. Por isso ele **só se move para os lados**, porque subir ou descer abriria uma faixa vazia.
  - A barra vai de −100 (encostado na borda esquerda da sobra) a +100 (borda direita). 0 é o centro e é o padrão.
  - A saída mostra "No centro" ou "N% para a esquerda/direita".
  - Pela conta da referência, o react 16:9 com escala 1.2172 fica com ~1315 px de largura numa tela de 1080. Isso deixa ~117 px de sobra de cada lado, ou seja, um transform x máximo de ~±0,217 (a unidade é meia tela, 1 = 540 px).
  - **Calcule o limite real a partir das dimensões do arquivo** e nunca deixe aparecer fundo vazio.
- **React vertical:** ele se move **para cima e para baixo**, com a mesma lógica de limite. A tela troca o rótulo e a etiqueta ("Vertical" em vez de "Horizontal"). Me diga como ficou.
- **A máscara "Dividir" tem que continuar no mesmo lugar da tela**, esmaecendo o topo do react sobre o vídeo de cima. A máscara é relativa ao trecho:
  - no movimento para os lados, a linha horizontal não muda;
  - no movimento vertical, **compense o centro da máscara** para o degradê continuar na emenda.

  Confirme abrindo o resultado e me diga o que fez.
- A posição vale para **todos os vídeos do lote**, porque o react é o mesmo. Ela se aplica a todos os trechos do react, inclusive ao trecho retomado depois do CTA. **O vídeo do CTA não muda** e continua como hoje.
- Com "Usar sempre este react" ligado, a posição fica **salva junto com o react salvo** e volta preenchida nas próximas vezes. "Esquecer este react" apaga a posição também.
- **O play do Enquadrar continua leve:** a posição do react muda só com transformação de CSS no vídeo leve do react, ao vivo, sem refazer nada.
- O botão "Voltar ao centro" zera a posição.

## 3. Modelo da headline

- A aba Headline mostra uma **lista de modelos prontos** (sem importar modelo da pessoa por enquanto). Cada modelo tem uma imagem de prévia, o nome, uma frase e um selo ("Atual" ou "Novo"). A escolha é um grupo de rádio.
- Começa com 2 modelos:
  - **Notícia**: o que existe hoje ("Title EN Simple News", da referência do React). É o padrão e não muda nada no resultado.
  - **Citação**: o novo, do "headline teste". É o modelo de texto "Title EN Caption Simple Username" (effect_id `7641057540280798472`), com a caixa branca arredondada, o texto preto em CreatoDisplay-Bold, negrito e **sem itálico**, a **barra ao lado** (o shape em `non_text_info_resources`), as duas animações de entrada (texto e barra), o espaçamento entre linhas e a posição e o tamanho do JSON (transform x ≈ −0,474, y ≈ −0,244, escala ≈ 0,358). **Confirme tudo lendo o JSON, não confie só neste resumo.** Copie a estrutura do CapCut e troque só ids, tempos e o texto.
- **O texto sai sempre como `SUA HEADLINE AQUI`**, em qualquer modelo. O texto de exemplo do projeto ("Você precisa começar…", com aspas) **não entra**. A headline dura o vídeo inteiro, como hoje, já contando o CTA.
- **Os modelos vivem numa configuração**, não espalhados no código. Cada um é uma entrada com id, nome, descrição, selo, imagem de prévia e o bloco de referência do CapCut. Um terceiro modelo no futuro tem que ser só **um arquivo de referência + uma entrada**, sem mexer no motor. Me mostre como ficou.
- **Prévias:** vou colocar as imagens reais em `docs/design/assets/headline-noticia.png` e `headline-citacao.png`. Copie para a pasta de assets do app, com as mesmas regras das imagens do Início. Enquanto não existirem, mostre a prévia simples do protótipo, sem quebrar.
- Vale para **todos os vídeos do lote**. O app **lembra o último modelo usado**, no mesmo lugar do "último modelo usado" da Edição.
- **Passo Ajustes:** a linha "Headline" mostra "Modelo <nome>. O texto você troca no CapCut." e o botão **"Mudar"**, que volta para o Enquadrar já na aba Headline.
- **Passo Gerar:** o quadro estático de cada cartão mostra o modelo escolhido.
- **Risco em outro PC:** a fonte da Citação aponta para `C:/Users/USUARIO/AppData/Local/Microsoft/Windows/Fonts/CreatoDisplay-Bold.otf` (instalada só no meu usuário), e o modelo usa a Gotham-Bold do cache do CapCut. Veja como o app já trata isso na Notícia e me diga o que acontece num computador sem essas fontes. Não resolva agora, só me diga.

## Como verificar

- Compare o Enquadrar (as 3 abas), o Ajustes e o Gerar com `react-novo-fluxo.html`, lado a lado, em **1440×900 e 700×800**, e me mostre as capturas (diga onde salvou).
- **Teste de ouro:**
  - o React com **Notícia** e o react no centro tem que continuar **idêntico** ao teste de ouro atual;
  - teste novo: React com **Citação**, comparando o bloco da headline com `referencia-headline/citacao/draft_content.json` (só ids, tempos e texto podem mudar);
  - teste novo: react deslocado para a esquerda e para a direita no limite, conferindo que o transform x não passa do limite e a máscara não muda.
- Testes automáticos para: react vertical (move na vertical, máscara compensada), posição salva com o react salvo, esquecer o react salvo, modelo lembrado entre aberturas, imagem de prévia faltando, CTA no meio e no final com o react deslocado (o CTA não se move).
- **Rodada real, só pela interface:**
  - gere 3 projetos: Citação com o react à esquerda, Notícia com o react à direita e Citação com CTA no meio;
  - feche e reabra o app e confirme que o modelo e a posição voltam;
  - **eu abro os projetos no CapCut para conferir.**
- Rode os testes que já existem. A Edição, o Início, o login e o resto do React não podem mudar.

## Não fazer agora

- Nenhum modelo além dos 2, nenhuma importação de modelo da pessoa, nenhuma troca automática do texto da headline.
- Nada de zoom ou altura da faixa do react: **só a posição**.
- Não mexa no vídeo do CTA, na máscara (além da compensação vertical), na Edição, no Início, em Cortes nem na barra lateral.
- Pare no fim e espere eu validar.
