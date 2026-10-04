As Fases 1, 2 e 3 da seção **Cortes** foram validadas (montador de um corte, transcrição de vídeo longo com quem fala, e achar os cortes). Agora é a **Fase 4: a tela Cortes**, que liga tudo isso ao app. É a primeira vez que a pessoa vai usar a seção de verdade.

Leia antes de mexer: `docs/design/cortes-especificacao.md` (seção 6 e o resto para o contexto), `docs/design/cortes-novo-fluxo.html` (a referência visual interativa: abra no navegador e clique pelo fluxo; é o alvo), `docs/design/prompt-edicao-passo-a-passo.md` (o wizard da Edição, que Cortes segue no mesmo molde) e `docs/design/prompt-visual-dashboard.md` (os tokens do visual). Descubra e me diga **onde está o arquivo da interface real do app** (o `index.html` de `cortesapp/assets` pode ser uma versão antiga). Se o novo visual do Dashboard e da Edição já está no app, **reaproveite os mesmos componentes e o mesmo CSS**; se ainda não, use os tokens do `prompt-visual-dashboard.md` (fundo `#0a0a0b`, cartões `#131315`, lime `#b3f706`, fonte Inter empacotada localmente) e me avise. Depois me diga o plano em poucas linhas e espere eu dizer "pode seguir".

**Tudo que a tela mostra vem do backend real que já existe. Nada simulado:** o progresso, as vozes, os cortes e a geração são os das Fases 1, 2 e 3.

## A barra lateral

Adicione o item **Cortes** (ícone de tela vertical, como no protótipo) logo depois de Edição, sem mexer no resto da barra. O acesso por plano vem da configuração criada na Fase 3 (quais planos têm Cortes). Quem não tem acesso vê o item com cadeado e, ao clicar, uma tela curta explicando e levando para Plano e cobrança. **Não decida sozinho quais planos têm o quê:** leia da configuração e me diga qual é o valor atual.

## O fluxo

Barra segmentada no topo, mesmo molde da Edição: **Modelo, Vídeo, Tipos, Transcrição, Ajustes, Gerar**. Rodapé fixo em todas as telas: "Voltar", o aviso de privacidade no centro, botão principal à direita (pílula lime, desabilitado até o passo estar completo). "Voltar" mantém o que foi escolhido.

**1. Modelo.** Lista com "Corte básico" (pré-selecionado, radio de verdade, setas do teclado) e um cartão "Mais modelos de corte, em breve" (não clicável). À direita, o painel de prévia com um quadro de celular 9:16. Use um vídeo real em `cortesapp/assets/previews/cortes-basico.mp4` (curto, em loop, sem som, 9:16, H.264, menos de 1,5 MB) com `poster`; **eu entrego o arquivo**, então deixe a pasta, o nome e um `README` de uma linha prontos e mostre só o poster se o arquivo não existir. Respeite `prefers-reduced-motion`. Textos como no protótipo.

**2. Vídeo.** Uma área de arrastar e soltar e o botão "Escolher vídeo" (não copia o arquivo). Depois de escolhido, vira o cartão do arquivo com nome, tamanho, duração real, check e botão de remover. Mostre também, em letra pequena, **quantas análises restam no mês** (da cota da Fase 3). Se já houver transcrição ou análise em cache deste arquivo, diga isso ("já processado neste computador") e deixe as próximas etapas passarem na hora.

**3. Tipos.** Cinco cartões marcáveis (**História, Polêmico, Emocional, Engraçado, Insight**), todos marcados de saída, com "Limpar seleção" e contador. Precisa de pelo menos um para continuar. É a única escolha sobre os cortes: **não existe tela de escolher corte por corte.**

**4. Transcrição.** A tela mais complexa. Fases, mostradas como no protótipo, cada uma com percentual grande, barra lime e o estado real:
1. **Transcrever** no computador (progresso real das janelas, cancelar, retomável, em segundo plano; a pessoa pode sair da tela e voltar).
2. **Identificar as vozes**, também no computador.
3. **Confirmar o apresentador.** Ao fim da identificação, a tela mostra as vozes encontradas, cada uma com uma frase de exemplo e quanto tempo falou, e deixa **a que o app acha que é o apresentador já selecionada**, com um botão "Confirmar e achar os cortes". Isso existe porque o apresentador entra no pedido à IA; trocar depois obrigaria a pagar uma nova análise. **Decisão minha, me avise se quiser tirar.**
4. **Achar os cortes** (IA, só o texto da transcrição). Nesta fase o aviso do rodapé muda para: "O vídeo e o áudio não saem do seu computador. Só o texto." e a tela diz que isso gasta 1 análise do plano.
No fim: "Encontramos N cortes completos", já considerando os tipos marcados. **Sem internet, sem cota ou função fora do ar:** mensagem clara e o **modo manual** (abaixo), sem travar.

**Modo manual.** Uma lista simples onde a pessoa adiciona cortes digitando início e fim (`h:mm:ss`) e, se quiser, o tipo; com validação (fim depois do início, dentro da duração do vídeo) e botão de remover. Usa o mesmo caminho do montador da Fase 1. Só aparece quando a IA não está disponível ou se a pessoa escolher "Digitar cortes à mão".

**5. Ajustes.** Só o acabamento, num cartão: velocidade 1,13x, efeito de tremor e música (com "Trocar", que abre o seletor de arquivo e o app **lembra a escolha**). **Sem volume da fala e sem headline** (a headline é trocada depois no CapCut). O botão principal diz "Gerar N cortes".

**6. Gerar.** Sem barra de progresso por corte: ao clicar em "Gerar N cortes" a tela vai **direto para "Seus cortes"**, uma grade com **todos os cortes numerados (Corte 01, 02…) na ordem do podcast, cerca de 5 por linha** (4, 3 e 2 colunas em telas menores), que a pessoa rola para baixo. Cada cartão é um quadro de celular 9:16 com **o preview de vídeo real daquele corte**, sem som, em loop, e embaixo **só o nome do projeto** (`<nome do vídeo> - corte 01 - História`, em até 2 linhas, com reticências e o nome completo no `title`). **Não mostre mais nada embaixo**: sem etiqueta de tipo, sem minuto de início, sem outro texto. O objetivo da tela é dar a estética de "gerou um monte de corte".

- **Projetos:** um projeto do CapCut por corte, **todos de uma vez**, com nome `<nome do vídeo> - corte 01 - História` (número na ordem do podcast, tipo no nome, sem caracteres especiais; ` - longo` quando for o caso). Isso roda em segundo plano, com o montador da Fase 1.
- **Preview real (o que a pessoa vê na grade):** para cada corte, o app gera com o ffmpeg um vídeo pequeno e leve (cerca de 270x480, H.264, **sem áudio**, bitrate baixo) **a partir do vídeo original da pessoa, com a mesma edição do projeto**: os mesmos trechos e cortes secos, o mesmo enquadramento e zoom, a velocidade e a headline de exemplo por cima (se a fonte do CapCut não puder ser usada, uma fonte parecida; é uma aproximação, não o render do CapCut). A grade toca em loop os **primeiros ~12 segundos** de cada corte. Ao **clicar** num cartão abre um player maior com o **corte inteiro** (gerado na hora e guardado em cache), com som e controles, para a pessoa conferir o começo e o fim antes de abrir no CapCut. Ao fechar volta para a mesma posição da grade.
- **Como renderizar sem travar:** use `-ss` antes do `-i` e preset rápido; gere **primeiro os cartões que aparecem na tela** (os de baixo só ao rolar), com no máximo 2 ou 3 renders ao mesmo tempo, em segundo plano e cancelável. Guarde em uma pasta de cache do app (por arquivo de origem, tempo de início e fim e versão da edição) para não refazer. Enquanto o preview não chega, o cartão mostra o esqueleto cinza piscando com o número; quando chega, aparece (um depois do outro).
- **Uma linha de status no topo**, global: "Criando os projetos no CapCut… k de N", com um check e "N projetos criados no CapCut. Escolha lá quais postar." no fim. O progresso é o real (projetos prontos), nada simulado.
- **Só os cartões visíveis tocam** (os que saíram da tela pausam). `prefers-reduced-motion`: mostre só o primeiro quadro, sem loop.
- **Falhas:** se um projeto ou um preview falhar, o cartão mostra o estado de erro com o motivo curto e "Tentar de novo"; os outros continuam. Um preview que falha não impede o projeto de existir no CapCut (e vice-versa). Não bloqueie a tela: a pessoa pode cancelar.
- **Rodapé:** "Seu vídeo não sai do seu computador."

## Visual e comportamento

- Mesmos tokens, fonte e raio do Dashboard e da Edição; lime só no que importa (passo atual, opção marcada, botão principal, checks). Conteúdo centralizado numa coluna de até 1080 px. Transições de 160 a 450 ms.
- Foco visível lime em tudo, fluxo inteiro por teclado, contraste de texto pequeno acima de 4,5:1.
- Responsivo como a Edição: abaixo de 1100 px a lista e a prévia empilham; abaixo de 720 px os nomes dos passos somem, exceto o atual.
- Trocar o vídeo depois de ter avançado: limpar o que depende dele (transcrição, vozes, cortes) e avisar de forma discreta, sem perder o resto da tela.
- Se a pessoa sair da seção no meio, o trabalho em segundo plano continua e ela retoma de onde parou ao voltar (as Fases 2 e 3 já guardam o progresso).

## Como verificar

- Compare, lado a lado com `cortes-novo-fluxo.html`, os passos Modelo, Tipos, Transcrição, Ajustes e Gerar em **1440×900 e 700×800**. Me mostre as capturas.
- **Rodada real, só pela interface**, com `C:\Users\danil\Downloads\Qual foi o momento - Ale EP6.mp4`: do passo 1 ao 6, com os progressos reais, a confirmação do apresentador e os projetos aparecendo no CapCut (gere em uma pasta de teste e copie **3** para a lista do CapCut para eu abrir; se a rodada de verdade com IA paga ainda precisar da minha aprovação de custo, me peça antes). Me conte o tempo de cada fase.
- Teclado: setas escolhem o modelo, Tab chega ao botão, Enter avança, Voltar mantém as escolhas.
- Cenários de erro, cada um com mensagem clara: sem internet, cota esgotada, função fora do ar (cai no modo manual), vídeo que não existe mais, arquivo sem áudio, cancelar no meio, fechar o app no meio e reabrir (retoma).
- Plano sem acesso mostra o cadeado e a tela explicativa.
- Verifique que **nada na tela é simulado** (busque por timers e números fixos de progresso no código novo).
- Rode os testes que já existem. A Edição, o Dashboard e as Fases 1 a 3 não podem mudar.

## Não fazer agora

- Nenhum outro modelo de corte além do Corte básico (o cartão "em breve" é só visual).
- Nenhuma IA nova (headline, zoom, nada além de achar os cortes).
- Não mexa na Edição nem no Dashboard, e na barra lateral só o item Cortes.
- Não gere o vídeo de prévia do **modelo** (o `cortes-basico.mp4` do passo 1): eu entrego. Os previews dos cortes da tela Gerar são outra coisa e **são gerados pelo app**.
- Pare no fim da Fase 4 e espere eu validar.
