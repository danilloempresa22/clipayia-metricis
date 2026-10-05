Quero redesenhar a seção **Edição** do Clipay.ia. Hoje ela mostra os quatro modelos em cartões e, embaixo, já o upload do vídeo. Eu quero um fluxo por passos, uma pergunta de cada vez, no mesmo visual novo do Dashboard e da barra lateral (mesmos tokens, fonte Inter, lime do logo).

A referência visual interativa está em `docs/design/edicao-novo-fluxo.html` (abra no navegador e clique pelo fluxo). Use como alvo. Os tokens e a barra lateral são os mesmos de `docs/design/dashboard-novo-visual.html` e do prompt `prompt-visual-dashboard.md`.

Esta rodada é só visual e de estrutura de tela. **Não mudar a lógica de processamento** (cortes, zoom, headline, transcrição, gravação no CapCut): só reorganizar quando cada coisa aparece. Os endpoints e as funções que já existem continuam sendo chamados da mesma forma.

## O fluxo

Cada edição é uma sequência de passos, mostrada no topo como uma barra segmentada com o nome de cada passo (o passo atual em destaque, os feitos em lime, os próximos apagados). Os passos mudam conforme o modelo:

- **Cortes + Headline:** Edição, Vídeo, Transcrição, Headline, Gerar
- **Legenda Complexa:** Edição, Vídeo, Transcrição, Revisão, Gerar
- **Apresentador + iPad:** Edição, Vídeos, Enquadrar, Sincronizar, Legenda, Headline, Gerar
- **Rotina:** Edição, Takes, Cortes, Relógio, Headline, Música, Gerar

Rodapé fixo em todas as telas: "Voltar" à esquerda, o aviso "Seu vídeo não sai do seu computador" no centro e o botão principal à direita. No primeiro passo o botão diz "Continuar com <nome do modelo>". O botão fica desabilitado até o passo estar completo.

### Passo 1: escolher o modelo (a tela nova mais importante)

- Título: "Qual edição você vai fazer?" e uma linha: "Escolha o modelo. Você ainda não precisa enviar nada."
- Duas colunas. À esquerda, uma lista de quatro opções (um radio group de verdade: setas do teclado trocam a opção, foco visível). Cada opção tem o nome, a descrição que já existe hoje, e uma etiqueta do que ela pede: "1 vídeo", "1 vídeo", "2 vídeos", "Vários takes". A opção escolhida ganha borda lime e o radio preenchido. Deixar a primeira (Cortes + Headline) pré-selecionada.
- À direita, um painel de prévia que muda quando a opção muda: um quadro de celular 9:16 com a **prévia em vídeo** e, ao lado, o nome do modelo, a descrição, "O que ele faz" (3 itens com check lime), "Você precisa de" (etiqueta) e a nota "Prévia ilustrativa" (tirar essa nota quando for vídeo real).
- **Vídeos de prévia:** o desenho de referência usa animações em CSS só como substitutos. No app, usar vídeos reais, curtos (6 a 10 s), em loop, sem som, em `cortesapp/assets/previews/<modelo>.mp4` (ids: `cortes`, `legenda`, `ipad`, `rotina`), 9:16, H.264 e leves (alvo: menos de 1,5 MB cada). Usar `<video autoplay muted loop playsinline preload="metadata" poster="...">`, com troca suave (fade de 400 ms) entre eles, e pausar o vídeo que não está visível. Se o arquivo de prévia não existir, mostrar um quadro estático (poster) em vez de quebrar. Eu mesmo vou gravar/exportar os 4 vídeos a partir de resultados reais; deixe a pasta e os nomes prontos e um `README` de uma linha dizendo o formato.
- Respeitar `prefers-reduced-motion`: sem autoplay, mostrando só o poster.

### Passo 2: enviar

O título e o texto mudam conforme o modelo:
- **Cortes + Headline e Legenda Complexa:** "Escolha o vídeo". Uma única área de arrastar e soltar com o botão "Escolher vídeo" (mantendo a dica de hoje: "Escolher vídeo" é mais rápido em arquivos grandes porque não copia o arquivo). Depois de escolhido, vira um cartão do arquivo (nome, tamanho, duração, check verde, botão de remover).
- **Apresentador + iPad:** "Escolha os dois vídeos", duas áreas lado a lado: "1. Gravação de tela do iPad" e "2. Vídeo da pessoa". O botão Continuar só habilita com os dois.
- **Rotina:** "Adicione os takes": área de arrastar vários arquivos, depois uma lista numerada na ordem do vlog. Reordenar por **arrastar** e também por botões de subir e descer (acessibilidade e teclado), remover por take, e "Adicionar mais".
Mostrar o aviso de privacidade em todas as telas (ele já está no rodapé).

### Passo 3: transcrição (nos modelos que têm)

Tela própria, com o percentual grande (56 px), uma barra de progresso lime, o estado ("Transcrevendo no seu computador…"), e abaixo, um bloco "Trecho transcrito" que vai mostrando as linhas conforme saem, com o tempo de cada uma. O botão Continuar só habilita no fim. Usar o progresso real que o app já tem (não simular). Dizer "Roda no seu computador, sem internet e sem custo por uso." Se a transcrição for opcional hoje em algum modelo, manter opcional: oferecer "Pular" como botão secundário.

### Passos seguintes

Cada um é uma tela com o mesmo cabeçalho (título + uma linha de ajuda) e o mesmo rodapé. O conteúdo de cada tela vem das especificações que já existem (`rotina-especificacao.md`, `apresentador-ipad-especificacao.md`, `legenda-complexa-especificacao.md`). Nesta rodada, migrar apenas as telas que já existem hoje (Headline, Gerar etc.) para o novo molde; as telas novas desses modelos entram quando o modelo for implementado.

## Visual (mesmos tokens do Dashboard)

- Fundo `#0a0a0b`, cartões `#131315`/`#1b1b1e` com borda `rgba(255,255,255,.08)`, raio 22 px; título da página 34 px/600 com tracking -0.03em; texto `#f5f5f7`, secundário `#a1a1a6`, terciário `#8e8e93`.
- Lime `#b3f706` só no que importa: passo atual, opção escolhida, botão principal e checks.
- Botão principal: pílula lime de 44 px; botão secundário de enviar: pílula clara (`#f5f5f7`, texto escuro).
- Conteúdo centralizado numa coluna de até 1080 px.
- Transições de 160 a 450 ms; nada além disso. Foco visível lime em tudo.
- Responsivo: abaixo de 1100 px a lista e a prévia empilham; abaixo de 720 px o painel de prévia fica embaixo da lista e os nomes dos passos somem, exceto o atual.

## Como verificar

- Rodar o app e comparar, lado a lado com o arquivo de referência, o passo 1 (os 4 modelos), o passo 2 (os 3 tipos de envio) e o passo 3, em 1440×900 e 700×800.
- Fluxo inteiro por teclado: setas escolhem o modelo, Tab chega ao botão, Enter avança, Voltar mantém o que foi escolhido (arquivo, ordem dos takes).
- Trocar o modelo no passo 1 depois de ter enviado arquivos: limpar os arquivos e avisar de forma discreta, sem perder o resto da tela.
- Conferir que o resultado final (projeto no CapCut) é idêntico ao de antes da mudança nos modelos que já existem.
- Contraste de todo texto pequeno acima de 4,5:1.

## Não fazer agora

- Não gravar nem gerar os vídeos de prévia automaticamente. Eu entrego os arquivos.
- Não mexer na barra lateral nem no Dashboard (já têm prompt próprio).
- Não adicionar passos ou opções que eu não pedi.
