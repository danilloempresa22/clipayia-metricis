Vamos criar um novo modelo de edição chamado **React**: um vídeo em cima (uma receita, por exemplo) e o vídeo de react do apresentador embaixo, com um degradê que junta os dois, uma headline no meio e, opcionalmente, um CTA que entra quando o vídeo de cima congela. A ideia é produzir **muitos vídeos de uma vez**: um react só, vários vídeos em cima, um projeto do CapCut para cada. Esta é a **Fase 1: só o motor** (montar o projeto do CapCut). A tela vem na Fase 2. **Adapte o que existe, não refaça o app.**

Leia antes de mexer:
- `docs/design/referencia-react/draft_content.json` e `draft_meta_info.json`: **o projeto real do CapCut que é o alvo** ("Patricio clipay ia"). É a fonte da verdade da geometria, das máscaras, do filtro, do texto e da estrutura de congelar + CTA. `quadro-resultado-final.jpg` mostra o resultado.
- `docs/design/react-novo-fluxo.html`: o protótipo aprovado da tela (para entender as opções e o que o motor precisa receber).
- O **montador que já existe** (o da Edição e o de Cortes, Fase 1) e a detecção de pausas/transcrição da Fase 2 de Cortes. Descubra e me diga onde estão, o que dá para reaproveitar (criar a pasta do projeto, `draft_meta_info`, capa, caminhos dos materiais) e como a Edição registra um modelo novo.

Depois me diga o plano em poucas linhas e **espere eu dizer "pode seguir"**.

## O que o projeto React tem (confirme lendo o JSON de referência, não confie só neste resumo)

- Tela 9:16, 1080x1920, 30 fps.
- **Trilha de baixo = o vídeo de cima** (a receita), com o áudio dele (volume 1.0). No modelo de referência ele está deslocado para cima em ~24% (transformação y ≈ +0.475; a unidade é meia tela, então 1 = 960 px na vertical), para a parte importante ficar na área visível.
- **Trilha de cima = o react** (o apresentador), **mudo** (volume 0), ocupando uma faixa na parte de baixo da tela: ~38,5% da altura (≈739 px), colada embaixo, ampliada e cortada nas laterais (o original é 3840x2160 horizontal). Escala e posição do JSON de referência.
- Nos trechos do react há a máscara "Dividir" (linha) com borda suave, que **esmaece o topo do react sobre a receita**, e o filtro "Aprimorar". Copie os dois **do JSON de referência** (ids, parâmetros, rotação, suavização).
- **Headline:** um texto no modelo "Title EN Simple News", fonte CreatoDisplay-Bold, negrito, itálico, preto sobre caixa branca, à esquerda, na emenda entre receita e react, com as duas animações de entrada, durante o vídeo inteiro. O texto sai como **`SUA HEADLINE AQUI`**; a pessoa troca depois no CapCut. Copie estilo e posição do JSON.
- Sem música, sem keyframes, velocidades 1.0.
- **Com CTA** (a estrutura de referência): o vídeo de cima corre até o ponto P; ali entra um **material de foto "Congelar"** (quadro do vídeo de cima em P, em PNG) com a duração do CTA; depois o vídeo de cima continua de P. Na trilha do react, no mesmo intervalo, entra o **vídeo do CTA** (com som, volume 1.0, preenchendo a mesma faixa de baixo, **sem** o filtro Aprimorar) e o react **fica pausado**: depois do CTA ele retoma exatamente de onde parou. Duração total = vídeo de cima + duração do CTA.

## O que o motor recebe e faz

Entrada por vídeo: caminho do vídeo de cima, enquadramento (posição e zoom, vindos da tela), o caminho do react (o mesmo para todos), o CTA (opcional) **e onde ele entra (`meio` ou `final`)** e a opção "variar o trecho do react". Saída: um projeto do CapCut chamado **`<nome do vídeo> - react`**, na mesma pasta de projetos que o app já usa.

1. **Gerar a partir do JSON de referência.** Use o draft de referência como modelo e troque só o que muda (materiais, durações, segmentos, ids novos e únicos, textos). Não invente estrutura que o CapCut não escreveu.
2. **Enquadramento do vídeo de cima.** A tela mostra "X% cortado em cima" e zoom. Converta isso nos números do CapCut e **limite o deslocamento para nunca aparecer fundo vazio**: o vídeo de cima tem que cobrir tudo, de cima até a emenda com a faixa do react. Hoje o protótipo deixa a barra ir de 0 a 45%; pela conta da referência o máximo seguro é perto de 38% com zoom 100%. **Calcule o limite real e me diga** (eu ajusto o protótipo).
3. **Vídeo horizontal em cima:** amplie para preencher a área de cima (a região acima do react) e corte as laterais. Nesse caso o controle de posição passa a ser **horizontal**. Me diga como ficou, porque o protótipo só mostra a posição vertical.
4. **O trecho do react de cada vídeo.** O react tem uns 2:34 e serve vários vídeos. Padrão: começa em ~1,4 s, como na referência. Com "variar o trecho" ligado, cada projeto começa num ponto diferente (espalhado, sem passar do fim). **Se o react for mais curto que o vídeo de cima, não gere:** devolva um erro claro com o nome do vídeo (a tela mostra isso).
5. **O ponto de congelar (só com CTA).** Procure uma **pausa de fala entre frases** perto do meio: janela de ~40% a 70% da duração, ponto ideal ~55%, pausa de pelo menos ~0,4 s, **nunca dentro de uma frase**. Reaproveite a detecção de pausas/transcrição que já existe; se não servir, use detecção de silêncio do ffmpeg. Congele no meio da pausa. Se não achar pausa na janela, congele em ~55% e **marque o resultado como "sem pausa boa"** (a tela avisa). Extraia o quadro congelado com o ffmpeg em PNG, dentro da pasta do projeto.
6. **CTA no final** (alternativa ao meio): sem procurar pausa. O vídeo de cima toca inteiro; depois dele entra o material "Congelar" com o **último quadro** do vídeo, com a duração do CTA. Na trilha do react, o CTA entra logo depois do último trecho do react (que não precisa ficar pausado). Duração total = vídeo de cima + CTA, igual ao caso do meio.
7. **Transcrição de todos os vídeos.** Cada vídeo de cima é transcrito (no idioma do vídeo, português por padrão), com o **tempo de cada frase**. Reaproveite o transcritor que o app já tem (Edição/Cortes) e **faça uma passada só**: a mesma transcrição serve para achar a pausa do CTA e para a pessoa. Salve o resultado numa pasta do app (e uma cópia `<nome do projeto> - transcricao.txt` ao lado do projeto, só se o app já grava arquivos ali; se não, só na pasta do app) e exponha para a tela: texto corrido e lista com tempos. **Se a transcrição falhar, o projeto continua sendo criado**; só marca "transcrição indisponível" com o motivo curto. Diga onde fica e quanto tempo leva por minuto de vídeo.
8. **A conta dos tempos tem que fechar:** sem sobreposição nem buraco em nenhuma trilha, e o react pausado durante o CTA retoma no ponto certo. Valide com a referência.
9. Cada projeto tem **capa** (no padrão que o app já usa) e abre no CapCut sem pedir arquivo faltando. Os efeitos da referência (máscara, filtro, modelo de texto) dependem do CapCut da pessoa: **veja como o app já trata isso na Edição** e me diga se há risco.

## Como verificar

- **Teste de ouro:** refaça o projeto "Patricio clipay ia" com as mesmas entradas (vídeo de cima, react, CTA e o enquadramento da referência) e compare com o `draft_content.json` de referência: durações, segmentos, escalas, posições, volumes, máscara, filtro, texto. Diferenças só nos ids. Mostre o resultado do teste (use os arquivos de mídia do caminho que está no JSON, se existirem; senão me diga e eu coloco no lugar).
- Testes automáticos para: sem CTA, com CTA, vídeo horizontal, react curto demais, sem pausa na janela, variar o trecho (3 projetos, 3 inícios diferentes), nomes com acento.
- **Rodada real:** gere 3 projetos com 3 vídeos meus (um com CTA, um sem, um horizontal) e me diga o caminho deles. **Eu abro no CapCut para conferir.** Me diga também o tempo para gerar cada projeto.
- Rode os testes que já existem: Edição, Dashboard e Cortes não podem mudar.

## Não fazer agora

- Nada de tela ainda (Fase 2). Nenhuma IA nova.
- Não mexa na Edição, em Cortes, no Início nem na barra lateral, além de registrar o modelo se for preciso.
- Não troque a headline automaticamente: ela sai como placeholder.
- Não decida sozinho quais planos têm acesso ao React: me pergunte quando chegar nessa parte.
- Pare no fim e espere eu validar no CapCut.
