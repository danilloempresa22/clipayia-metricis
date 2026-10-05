Preciso redesenhar a tela **Início** do app. Hoje ela é um painel de números (cartões de vídeos feitos, visualizações, silêncio removido, gráfico por semana). Vira um **ponto de partida**: a pessoa escolhe o que fazer, solta o vídeo e começa. **Adapte o que existe, não refaça o app.**

Leia antes de mexer: `docs/design/inicio-novo-v2.html` (a referência visual interativa e **aprovada**: abra no navegador, clique nos modelos, em "Escolher vídeo" e redimensione a janela; é o alvo), `docs/design/prompt-visual-dashboard.md` (os tokens do visual), `docs/design/cortes-especificacao.md` (para o modelo Cortes) e `docs/design/prompt-edicao-passo-a-passo.md` (os wizards). Descubra e me diga **onde está o arquivo da interface real do app** (o `index.html` de `cortesapp/assets` pode ser uma versão antiga) e **onde hoje saem os números do Início**. Reaproveite o CSS, os tokens (fundo `#0a0a0b`, cartões `#131315`, lime `#b3f706`, Inter local) e os componentes que já existem. Depois me diga o plano em poucas linhas e espere eu dizer "pode seguir".

**Nada simulado:** tudo que a tela mostra vem de dados reais do app. O protótipo tem textos e números de exemplo; no app eles são reais ou não aparecem.

## O que a tela mostra, de cima para baixo

**1. Linha de cota (canto superior direito).** "7 de 10 análises neste mês", lido da cota real das análises de Cortes (a da Fase 3). Se o plano não tem Cortes ou a cota ainda não carregou, não mostre a linha (nada de número inventado). O texto de ajuda ao passar o mouse: "Cada vídeo longo analisado em Cortes usa 1 análise".

**2. Saudação.** "Bom dia / Boa tarde / Boa noite, <nome>" (como já existe) e a frase "Escolha o que fazer e solte seu vídeo."

**3. A caixa de enviar vídeo (o centro da tela).**
- Estado vazio: ícone, **título e dica que mudam conforme o modelo escolhido** (os textos estão no `app.js` do protótipo, no array `M`) e o botão lime "Escolher vídeo". Aceita **arrastar e soltar** na caixa inteira (destaque lime enquanto arrasta).
- Com o vídeo escolhido: check, nome do arquivo, tamanho e duração reais (como no passo Vídeo de Cortes), botão de remover e o botão principal **"Continuar"** (no modelo Cortes de podcast o texto é "Achar os cortes").
- O vídeo **não é copiado nem enviado**. Embaixo, em letra pequena: cadeado e "Seu vídeo não é copiado nem enviado".
- **"Continuar" leva ao wizard do modelo escolhido com o vídeo já selecionado**, pulando o passo de escolher modelo e o de enviar o vídeo (Cortes de podcast: abre em Tipos; Edição: abre no passo seguinte ao upload). Se o modelo precisa de mais de um vídeo (iPad + apresentador, Rotina com vários takes), abra no passo de upload com o arquivo já colocado.
- Se o vídeo arrastado não for vídeo, ou não existir, ou não tiver áudio: mensagem curta e clara, sem erro técnico do Windows.
- **Não implemente agora** o link "Experimente com um vídeo de exemplo" do protótipo (precisaria de um vídeo embutido). Não mostre.

**4. Modelos em botões (radio de verdade, setas do teclado).** Cortes de podcast (selo "Novo"), Cortes + headline, iPad + apresentador, Legenda complexa e Rotina. A ordem e os nomes vêm da **mesma configuração de modelos** que já alimenta a Edição e Cortes; se um modelo ainda não existe no app, **não mostre**. Plano sem acesso a um modelo: o botão aparece com cadeado e, ao clicar, a tela curta que explica e leva para Plano e cobrança (como já é no resto do app). **Não decida sozinho quais planos têm o quê:** leia da configuração. O primeiro modelo vem pré-selecionado, e o app **lembra o último modelo usado**.

**5. O palco "Como fica" (cartão grande abaixo dos botões).**
- À direita: o nome do modelo, o título, o parágrafo e 3 pontos (textos no protótipo; troque se algum for impreciso para o que o app realmente faz). O botão "Ver como funciona" abre a seção Tutorial.
- À esquerda: **uma imagem do modelo**, não os celulares desenhados do protótipo (aqueles são só um quadro provisório). As imagens ficam em `cortesapp/assets/previews/inicio/<id-do-modelo>.png` (ou `.webp`), proporção livre, com `object-fit: contain`, até 440 px de altura. **Eu entrego as imagens.** Já tenho a do iPad: `docs/design/assets/inicio-ipad-apresentador.png`. Copie para `cortesapp/assets/previews/inicio/ipad.png` (use o id de modelo que o app já tem). **Para um modelo sem imagem ainda**, mostre o quadro provisório simples do protótipo (um celular com o nome do modelo), sem quebrar. Deixe a pasta e um `README` de uma linha prontos.
- Troca de modelo anima só o texto (fade de 350 ms). `prefers-reduced-motion`: sem animação.

**6. "Seus cortes recentes".** Uma faixa horizontal (rolagem lateral) com os **últimos projetos de Cortes gerados neste computador**: miniatura vertical (a prévia que já existe do passo Gerar, no cache de prévias; se não houver, um cartão neutro com o número), duração, o **nome do projeto** (`<vídeo> - corte 03 - Insight`, 2 linhas com reticências) e "Abrir no CapCut". Mostre no máximo 12, os mais novos primeiro. **Sem projetos ainda: esconda a seção inteira**, sem mensagem de vazio. Se a pessoa também tem projetos de Edição, **não misture**: esta faixa é só de Cortes. "Ver todos" leva à seção Projetos.

**7. "Aprenda em 1 minuto".** No protótipo são 4 miniaturas de vídeo de exemplo. **Só mostre esta seção se existirem vídeos de tutorial de verdade** na seção Tutorial (use os mesmos). Se não existirem, esconda. "Todos os tutoriais" leva à seção Tutorial.

**8. O que sai.** Saem desta tela o gráfico "Vídeos por semana", os cartões de números e o cartão de "Visualizações geradas" (que era só exemplo). **Não apague o código dos contadores**: só pare de mostrá-los no Início (eles podem voltar em Projetos ou Conta). Me diga onde ficou cada um.

## Visual e comportamento

- Mesmos tokens, fonte e raio do resto do app. Lime só no que importa (modelo escolhido, botão principal, checks, "Abrir no CapCut"). Conteúdo centralizado numa coluna de até 1120 px.
- Foco visível lime em tudo, fluxo inteiro por teclado (setas entre os modelos, Enter no botão principal), contraste de texto pequeno acima de 4,5:1.
- Responsivo como o protótipo: abaixo de 1100 px o palco empilha (imagem em cima, texto embaixo) e os tutoriais passam a 2 colunas; abaixo de 720 px a barra lateral vira a barra do topo, o botão da caixa ocupa a largura toda e a faixa de recentes continua rolando de lado.
- A barra lateral **não muda**: Início, Edição, Cortes, Projetos, Tutorial.

## Como verificar

- Compare o Início do app com `inicio-novo-v2.html`, lado a lado, em **1440×900 e 700×800**, com e sem projetos recentes, com e sem imagem de modelo. Me mostre as capturas (e diga onde as salvou).
- **Rodada real, só pela interface:** solte o `C:\Users\danil\Downloads\Qual foi o momento - Ale EP6.mp4` na caixa, com Cortes de podcast marcado, clique em "Achar os cortes" e confirme que o wizard abre em Tipos **com o vídeo já escolhido**. Repita com um modelo da Edição.
- Teclado: setas trocam o modelo, Tab chega à caixa e ao botão, Enter avança.
- Cenários de erro: arquivo que não é vídeo, vídeo que não existe mais, vídeo sem áudio, plano sem acesso ao modelo (cadeado e tela explicativa), sem internet (a cota some, o resto funciona).
- Verifique que **nada na tela é simulado**: busque nos arquivos novos por números fixos, textos de exemplo de cota, nomes de projeto de exemplo e listas de tutorial falsas.
- Rode os testes que já existem. A Edição, Cortes (Fases 1 a 4 e o Gerar) e a barra lateral não podem mudar.

## Não fazer agora

- Nenhum modelo novo, nenhuma IA nova, nada de integrações com Instagram ou TikTok (as visualizações só voltam quando elas existirem).
- Não mexa nos wizards da Edição e de Cortes além de aceitar o vídeo já escolhido na entrada.
- Não gere imagens nem vídeos de tutorial: eu entrego.
- Pare no fim e espere eu validar.
