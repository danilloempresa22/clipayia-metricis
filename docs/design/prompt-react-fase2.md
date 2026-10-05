Agora a **Fase 2 do modelo React: a tela**. O motor (Fase 1) já monta os projetos; aqui a pessoa escolhe os vídeos, confere o enquadramento, decide o CTA e gera. **Adapte o que existe, não refaça a Edição.**

Leia antes de mexer: `docs/design/react-novo-fluxo.html` (a referência visual interativa e **aprovada**: abra no navegador e passe pelos 6 passos, com "Só um" e com "Vários de uma vez", com e sem CTA, e redimensione a janela), `docs/design/prompt-edicao-passo-a-passo.md` e `docs/design/prompt-visual-dashboard.md` (wizard e tokens), e o que você construiu na Fase 1. Me diga **onde está o wizard da Edição** e como ele registra os modelos. Reaproveite CSS, tokens e componentes. Depois me diga o plano em poucas linhas e **espere eu dizer "pode seguir"**.

**Nada simulado:** o protótipo tem 5 receitas de exemplo, nomes, durações e um CTA de exemplo. No app tudo vem dos arquivos reais da pessoa.

## Os 6 passos

**1. Modelo.** "React" entra na lista de modelos da Edição, com selo "Novo", texto e 4 pontos como no protótipo (troque o que for impreciso). A ordem e os nomes vêm da mesma configuração de modelos que a Edição já usa. Acesso por plano: **leia da configuração e me pergunte** qual plano recebe o React; não decida sozinho. Sem imagem do modelo ainda: use o quadro provisório simples (um celular com o nome do modelo).

**2. React.** A pessoa escolhe o vídeo de react (arrastar e soltar ou escolher). Mostre nome, tamanho, duração e resolução reais, com a nota "áudio não usado". Em seguida, a pergunta obrigatória **"Quantos vídeos você vai fazer agora?": "Só um" ou "Vários de uma vez"**; "Continuar" só liga com as duas coisas definidas. Trocar a escolha de "Vários" para "Só um" limpa a lista de vídeos de cima (avise se houver algo importado).

**3. Vídeos.** Um vídeo (modo "Só um") ou vários (arrastar e soltar, "Adicionar mais", remover cada um). Cada linha mostra a miniatura **real** (um quadro tirado com o ffmpeg), nome, duração e se é vertical ou horizontal ("horizontal será ampliado para preencher o topo"). Validações com mensagem curta e clara, sem erro técnico do Windows: arquivo que não é vídeo, que não existe mais, **sem áudio** (o som do resultado é o do vídeo de cima), **maior que o react** (diga qual; esse não é gerado). Mostre a nota "O react tem 2:34 e o maior vídeo tem X. Cabe em todos." só quando for verdade.

**4. Enquadrar.** O passo central. À esquerda, o celular 9:16 com a composição **real**: quadros do vídeo de cima e do react, a faixa de baixo, o degradê e a caixa "SUA HEADLINE AQUI", como o motor vai montar. Uma barra de tempo para passar pelo vídeo (os quadros vêm do ffmpeg, pequenos, em cache, sem travar). Controles: **Posição** (vertical; **horizontal nos vídeos horizontais**) e **Zoom**, com os limites que o motor calculou na Fase 1 (nunca deixar fundo vazio), "Mostrar a área do react" (marca em vermelho o que fica coberto), "Aplicar a todos os vídeos" (ligado por padrão; desligado cada vídeo tem o seu) e "Voltar ao padrão". Com vários vídeos, abas no topo e um check em cada vídeo já conferido. **Pode avançar sem conferir todos**, mas avise uma vez ("Você ainda não conferiu N vídeos").

**5. Ajustes.**
- **Adicionar um CTA** (desligado por padrão). Ligado, a pessoa escolhe o vídeo do CTA (nome, duração, resolução, com som) e, para cada vídeo de cima, a tela mostra uma barra com **o ponto onde ele vai congelar**, calculado de verdade pelo motor (procurando uma pausa entre frases perto do meio). Enquanto procura: "Procurando uma pausa…" por vídeo, em segundo plano. Onde o motor não achou pausa boa, marque com aviso curto ("sem pausa boa, congela no meio"). Texto de ajuda como no protótipo. "Gerar" fica desligado enquanto o CTA está ligado sem arquivo.
- **Variar o trecho do react** (ligado por padrão): cada projeto começa o react num ponto diferente.
- Nota fixa: a headline sai como "SUA HEADLINE AQUI" e a pessoa troca no CapCut.

**6. Gerar.** O botão diz "Gerar N vídeos". Vai direto para a **grade "Seus vídeos"**, como o Gerar de Cortes (mesma grade, mesmos breakpoints, mesma linha de status global): um cartão 9:16 por projeto, com a duração por cima (já somando o CTA) e **embaixo só o nome do projeto** (`<nome do vídeo> - react`, 2 linhas, reticências, nome completo no `title`). Nesta fase o cartão mostra um **quadro estático real** da composição (não renderize vídeo de prévia). Status: "Criando os projetos no CapCut… k de N" com o k real; no fim, check e "N projetos criados no CapCut. Troque a headline lá." Falha em um projeto: cartão de erro com motivo curto e "Tentar de novo" só nele; no fim, "Tentar de novo os que falharam". Cancelar possível. Rodapé: "Seus vídeos não saem do seu computador."

## Regras gerais

- Os vídeos **não são copiados nem enviados**; o app lê de onde estão. Gere até 3 projetos ao mesmo tempo, sem travar o computador, e nunca carregue vídeo inteiro na memória.
- Foco visível lime, fluxo inteiro por teclado, voltar sem perder o que foi feito, `prefers-reduced-motion`.
- Responsivo como o protótipo: abaixo de 1100 px as colunas empilham; abaixo de 720 px a barra lateral vira a do topo.
- Lime só no que importa; mesmos tokens, fonte e raio do resto do app.

## Como verificar

- Compare cada passo com `react-novo-fluxo.html`, lado a lado, em **1440×900 e 700×800**, e me mostre as capturas.
- **Rodada real, só pela interface:** o react `Patricio reagindo` (o que eu uso) e 5 receitas minhas, "Vários de uma vez", com CTA e depois sem. Me diga o tempo de cada passo (carregar quadros, achar as pausas, gerar os 5 projetos) e o uso de memória e CPU. **Eu abro os projetos no CapCut.**
- Cenários: não-vídeo, vídeo sem áudio, vídeo que sumiu do disco, react mais curto que um vídeo, CTA sem arquivo, voltar de "Vários" para "Só um", cancelar no meio, fechar o app no meio da geração.
- Verifique que **nada na tela é simulado**: busque nos arquivos novos por nomes de receita, durações e pausas fixas de exemplo.
- Rode os testes que já existem: Edição, Cortes, Início e a barra lateral não podem mudar.

## Não fazer agora

- Nenhuma IA nova, nenhuma prévia em vídeo, nenhum troca automática de headline.
- Não mexa nos outros modelos da Edição, em Cortes ou na barra lateral. **Não** adicione o React ao Início ainda: isso eu peço depois, com a imagem do modelo.
- Pare no fim e espere eu validar.
