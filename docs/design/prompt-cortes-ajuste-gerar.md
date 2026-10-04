Preciso de um ajuste no último passo da tela **Cortes** (o "Gerar"), que você já construiu na Fase 4. **Adapte o que existe, não refaça a tela.** A referência visual atualizada é `docs/design/cortes-novo-fluxo.html` (abra no navegador, vá até o fim do fluxo e clique em "Gerar"). Leia também a seção "6. Gerar" de `docs/design/prompt-cortes-fase4.md` e a seção 6 de `docs/design/cortes-especificacao.md`, que foram atualizadas. Depois me diga o plano em poucas linhas e espere eu dizer "pode seguir".

## O que muda

Hoje o Gerar mostra uma linha por corte com barra de progresso individual. **Tire isso.** Ao clicar em "Gerar N cortes", a tela vai **direto para "Seus cortes"**: uma grade com **todos os cortes numerados na ordem do podcast, cerca de 5 por linha**, que a pessoa rola para baixo. A ideia é dar a estética de "gerou um monte de corte".

**Cada cartão:**

- Quadro de celular 9:16 com o **preview de vídeo real daquele corte**, sem som, em loop.
- Por cima do vídeo, a duração do corte (como no protótipo).
- **Embaixo, só o nome do projeto** (`<nome do vídeo> - corte 01 - História`), em até 2 linhas, com reticências e o nome completo no `title`. **Nada além disso**: sem etiqueta de tipo, sem minuto de início, sem outro texto.

**Grade:** 5 colunas em tela larga, 4 abaixo de 1100 px, 3 abaixo de 860 px, 2 abaixo de 560 px. A grade respeita o mesmo visual (tokens, Inter, lime só no que importa).

**Linha de status no topo, global e real:** "Criando os projetos no CapCut… k de N" com uma barra fina; ao terminar, um check e "N projetos criados no CapCut. Escolha lá quais postar." O k é o número real de projetos prontos. Nada simulado, nada de timer com número fixo.

## Os previews (a parte nova de verdade)

O app gera, para cada corte, um vídeo pequeno e leve **a partir do vídeo original da pessoa, com a mesma edição do projeto**. Use o ffmpeg que o app já tem.

- Formato: cerca de 270x480, H.264, **sem áudio**, bitrate baixo, arquivo de poucas centenas de KB.
- Conteúdo: os mesmos trechos e **cortes secos** do projeto, o mesmo enquadramento e **zoom** (os mesmos números do montador da Fase 1), a velocidade de 1,13x e a headline de exemplo por cima (`SUA HEADLINE AQUI / SOBRE O SEU CORTE`). Se a fonte do CapCut não puder ser usada, use uma parecida: **é uma aproximação, não o render do CapCut**, e isso pode ficar claro num texto pequeno na tela ("prévia aproximada").
- **Na grade**, cada cartão toca em loop só os **primeiros ~12 segundos** do corte.
- **Ao clicar num cartão**, abre um player maior com o **corte inteiro**, com som e controles, para a pessoa conferir começo e fim antes de abrir no CapCut. O corte inteiro é gerado na hora (com um indicador) e fica em cache. Ao fechar, a grade volta para a mesma posição. Foco e Esc funcionam por teclado.
- **Sem travar o computador:** `-ss` antes do `-i`, preset rápido, **no máximo 2 ou 3 renders ao mesmo tempo**, em segundo plano e cancelável. Renderize **primeiro os cartões que aparecem na tela**; os de baixo só quando a pessoa rolar. Nunca carregue o vídeo inteiro na memória (o podcast pode ter 3 horas).
- **Cache:** em uma pasta do app, por (arquivo de origem + tamanho + data de modificação, início, fim, versão da edição). Mudou o corte ou a edição, refaz; senão reaproveita. Diga onde fica e como limpar.
- Enquanto o preview não chega, o cartão mostra o esqueleto cinza piscando com o número; quando chega, aparece (um depois do outro, não todos de uma vez).
- **Só os cartões visíveis tocam** (os que saem da tela pausam). Com `prefers-reduced-motion`, mostre só o primeiro quadro, sem loop.

## Projetos e previews são coisas separadas

Os projetos do CapCut continuam sendo criados em segundo plano pelo montador da Fase 1, todos de uma vez, como já é hoje. **Um preview que falha não impede o projeto de existir, e um projeto que falha não impede o preview de aparecer.**

**Falhas:** se um projeto ou um preview falhar, o cartão mostra o estado de erro com o motivo curto e um botão "Tentar de novo" só para aquele; os outros continuam. No fim, se houve falhas, ofereça "Tentar de novo os que falharam". Cancelar continua possível. Rodapé: "Seu vídeo não sai do seu computador."

## Como verificar

- Compare o Gerar com o `cortes-novo-fluxo.html`, lado a lado, em **1440×900 e 700×800**, e me mostre as capturas.
- **Rodada real, só pela interface**, com `C:\Users\danil\Downloads\Qual foi o momento - Ale EP6.mp4`: do passo 1 ao 6. Me diga: tempo até o primeiro preview aparecer, tempo para todos os previews da tela, tempo do corte inteiro ao clicar, tamanho médio de cada preview e o **uso de memória e de CPU** durante os renders.
- Os previews têm que mostrar o corte certo: abra 3 deles e confirme que começam e terminam onde o projeto do CapCut começa e termina.
- Cenários: vídeo de origem que não existe mais, ffmpeg falhando num corte (cartão de erro e "Tentar de novo"), cancelar no meio, fechar o app no meio e reabrir (retoma e reaproveita o cache), rolar a grade rápido (só os visíveis renderizam), reduzir movimento.
- Verifique que **nada na linha de status é simulado** (busque por timers e números fixos no código novo).
- Rode os testes que já existem: Edição, Dashboard e Fases 1 a 4 (fora o passo Gerar) não podem mudar.

## Não fazer agora

- Não mexa nos outros passos da tela Cortes, na Edição, no Dashboard nem na barra lateral.
- Não mude como os projetos do CapCut são montados; só como o passo Gerar mostra o resultado.
- Nenhuma IA nova.
- Pare no fim e espere eu validar.
