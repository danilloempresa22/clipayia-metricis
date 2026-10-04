Vamos construir a seção **Cortes** do Clipay.ia, a parte mais importante do produto e o plano Basic. A pessoa envia um vídeo longo (podcast de 1 a 3 horas), escolhe os **tipos** de corte que quer, o app transcreve, acha **todos** os melhores momentos e entrega cada um como um corte **completo**, já editado, em um projeto do CapCut. **Não existe tela para escolher corte por corte**: o app gera o máximo que conseguir e a pessoa escolhe o que postar direto no CapCut.

Leia antes de mexer, nesta ordem: `docs/design/cortes-especificacao.md` (é a especificação, com todos os números medidos), a pasta `docs/design/referencia-cortes/` (o projeto de CapCut que eu montei à mão, "cortes ale pod cast", mais dois quadros), `docs/design/cortes-novo-fluxo.html` (as telas), `prompt-transcricao-rapida.md` e `prompt-ajustes-headline-cortes.md` (a transcrição rápida e a arquitetura de IA pela Edge Function, que esta seção reaproveita). Depois me diga o plano em poucas linhas.

**Trabalhe por fases e pare no fim de cada uma para eu validar.** Não passe para a próxima sem eu dizer. Hoje só vale a Fase 1, a menos que eu diga o contrário.

## A regra que não pode quebrar

O corte é um **assunto inteiro**: começa onde o assunto ou a história começa e só termina quando o assunto muda. O erro que já tive: o corte pegava "um dia, cara, eu levei um tiro" e acabava ali. O certo é ele contando a história até o desfecho, e parando quando muda de assunto. Nunca truncar para caber em duração. Nunca incluir a frase de transição ("mudando de assunto…"). Cada decisão de limite abaixo existe por causa disso.

## Fase 1: o montador de um corte, sem IA

Objetivo: dado um vídeo e um intervalo (início e fim, digitados), gerar no CapCut **o mesmo projeto que eu fiz à mão** em `referencia-cortes/`. É aqui que eu valido a edição antes de pagar qualquer IA.

- Crie o módulo `cortesapp/cortes.py` (montagem) e a pasta de modelos `cortesapp/assets/cortes/modelos/basico.json`, com todos os parâmetros da seção 4 da especificação (canvas, escala base, fator e intervalo de zoom, velocidade, volume da música, efeito, headline), em vez de números espalhados no código.
- **Use `referencia-cortes/` como template**, do jeito que `carrega_tpl` usa `headline_tpl.json`: copie `draft_content.json` do projeto, a pasta `subdraft/` e o `draft_meta_info.json` para `cortesapp/assets/cortes/template/`, e troque só o que varia (pedaços e tempos, caminho do vídeo, headline, música, ids novos para tudo, nome, durações). Não escreva o composto do zero.
- O rascunho interno do composto existe em dois lugares (dentro de `materials.drafts[0].draft` e em `subdraft/<id>/draft_content.json`) e eles têm que sair **idênticos**. Registre o composto no `draft_meta_info.json` como a especificação descreve. Esse é o ponto que costuma gerar "Mídia perdida".
- Cortes secos dentro do corte: reaproveite `reels.regua` e `reels.divide_longos` sobre o áudio **só do intervalo** (não do vídeo todo). Pedaços colados no tempo.
- Zoom: reaproveite `plano_zoom` e as tabelas `ESTATICO`/`EMPURRAO`, aplicando os fatores sobre a escala base (1,823 para um original 16:9 em canvas 1:1; calcule a partir da proporção do arquivo, não fixe). Centrar na pessoa pela mesma detecção que já definimos (posição horizontal contínua), agora **também vertical**, e limitar com as fórmulas da seção 4 (`|x| ≤ s−1`, `|y| ≤ 0,5625·s−1` para 16:9). Antes de usar as fórmulas, **confirme o sinal e as unidades** com o projeto de referência: o empurrão do primeiro pedaço termina em `y = −0,2156` com `s = 2,161`, que é exatamente o limite. Se a sua conta não bater com isso, pare e me diga.
- Camada externa: velocidade 1,13x, posição y −0,128, efeito "Estroboscópio de tremor" com os parâmetros da especificação (se o efeito ainda não estiver no cache do CapCut desta máquina, grave só o id, como já fazemos com o filtro da Rotina). Headline pelo modelo que já existe (`reels.headline`), **sempre com o texto de exemplo da referência** (`SUA HEADLINE AQUI` / `SOBRE O SEU CORTE`): eu troco depois no CapCut e o app não gera nem pede headline nos cortes. **Compare** escala e posição dele com 0,634 e (0, 0,511) e use os números da referência se forem diferentes. **Não mexa no volume da fala** (a amostra tinha +10 dB, mas foi só um teste meu: o composto sai com volume 1,0). Música: um MP3 escolhido por mim, volume 0,053, do começo ao fim do corte.
- O vídeo original **não é copiado**: os pedaços apontam para o arquivo com `source_timerange`.
- Para testar eu vou colocar um trecho de uns 10 minutos do podcast em `tests/fixtures/` (não mexa com o arquivo de 4 GB). Se ele ainda não estiver lá quando você chegar nesse ponto, me peça.

**Como verificar a Fase 1.** Reproduza o corte da referência (de 900,5 s a 943,4 s do vídeo original; se só tiver o trecho de teste, use o intervalo equivalente nele) e compare com o projeto de referência: número de pedaços parecido, pedaços colados, velocidade, escala e posição dentro dos limites, headline, música, efeito. Rode a verificação do projeto que já existe. Depois **abra no CapCut** e me diga o que viu: sem "Mídia perdida", com som no corte (o cache `Resources/combination/..._audio.aac` do projeto de referência é gerado pelo CapCut; veja se o seu projeto gerado toca o áudio sem ele), com a imagem enquadrada. Se vier mudo, resolva isso antes de qualquer outra coisa. Me mostre os quadros do resultado ao lado dos do original.

## Fase 2: transcrição de 2 a 3 horas

Só começa depois que eu aprovar a Fase 1. Siga `prompt-transcricao-rapida.md` e acrescente o que a especificação (seção 3.1) pede para vídeos longos:

- `audio.pcm()` carrega o áudio todo. Para 3 horas, ler e processar por janelas (ou WAV temporário com `numpy.memmap`). Meça a memória num vídeo de 3 horas e me mostre.
- Cache por janela em disco e **retomada** depois de fechar o app. Progresso real e cancelar.
- Frases com início e fim em segundos, em nível de frase (hoje `transcricao.frases` devolve pedaços de 6 a 15 s). Mantenha o que já funciona para os outros modelos.
- Ajuste dos limites ao áudio: a frase escolhida como começo ou fim é puxada para a pausa mais próxima (≥ 250 ms), com folga de 0,3 s no fim.

## Fase 3: achar os momentos com IA (Edge Function)

Só depois da Fase 2. Siga a arquitetura de `prompt-ajustes-headline-cortes.md` (função no Supabase, chave só nos segredos, modelo configurável, cota por plano ajustável sem build, cache, limite por minuto, não guardar a transcrição). **Antes de contratar qualquer provedor pago, me diga o modelo escolhido e o custo estimado por vídeo de 3 horas.**

A função `achar-cortes` recebe a transcrição numerada (id, tempo, texto) em janelas de cerca de 15 minutos com 2 de sobreposição, e devolve JSON com **todos** os assuntos completos: id da primeira frase, id da última, título curto, uma ou duas categorias (história, polêmico, emocional, engraçado, conselho), força de 0 a 100 e um motivo curto. O código costura as janelas e valida. **Regras que o pedido ao modelo precisa impor** (são as minhas):

- A unidade é um **assunto**. O corte começa na frase que introduz o assunto e termina na última frase que ainda pertence a ele, quando o assunto muda. **A frase de transição não entra.** Histórias vão **até o desfecho**: nunca terminar antes dele.
- Se o começo natural for uma pergunta curta do apresentador sem a qual o corte não se entende, ela entra. Evitar começar com frase que depende do que veio antes ("então", "mas", "isso", "ele" sem dizer quem).
- Tipos que valem, em ordem: polêmico, triste ou emocional, história com começo, meio e fim, engraçado, conselho (ordem ou promessa clara). Dar força pelo gancho nos primeiros 5 segundos, por a ideia fechar sozinha, por emoção ou conflito e pelo desfecho.
- Duração: mínimo 30 s, teto configurável (padrão 4 minutos, leia da configuração). Se o assunto inteiro passar do teto, **devolver o assunto inteiro marcado como longo**, nunca um pedaço que termina no meio. Pode sugerir à parte um sub-trecho que também seja completo.
- Só pode usar ids que existem na entrada. Nunca inventar frase: o começo e o fim exibidos na tela vêm da transcrição real.

**Entregue tudo, sem top-N:** todo assunto completo acima de um piso de força (padrão 50, configurável) e do mínimo de duração. O filtro pelos tipos que a pessoa marcou é aplicado no código, depois, sobre a lista completa, para mudar os tipos não gastar nova análise.

Validação no código: ids existem e estão em ordem; sem sobreposição (fica o de maior força); mínimo e teto; o fim não é frase de transição; nenhum corte termina no meio de frase. Sem internet ou sem cota: mensagem clara e **modo manual** (digitar início e fim de cada corte), que é a Fase 1.

## Fase 4: a tela Cortes

Só depois da Fase 3. A referência é `cortes-novo-fluxo.html`, no mesmo visual e nos mesmos tokens do Dashboard e da Edição (Inter local, lime do logo, barra lateral flutuante). Adicione o item **Cortes** na barra lateral entre Edição e Projetos, sem mexer no resto da barra. Passos: **Modelo, Vídeo, Tipos, Transcrição, Ajustes, Gerar**.

- **Tipos:** cinco cartões marcáveis (História, Polêmico, Emocional, Engraçado, Conselho), todos marcados de saída, pelo menos um marcado para continuar. É a única escolha sobre os cortes. **Não faça tela de escolher corte por corte nem filtro de lista de cortes.**
- **Ajustes:** só o acabamento (velocidade 1,13x, efeito de tremor, música com "Trocar"). **Sem volume da fala e sem headline** (a headline é trocada depois no CapCut; a função de IA daqui só acha os cortes).
- **Gerar:** grave **todos** os cortes de uma vez, um projeto do CapCut por corte, com o nome `<nome do vídeo> - corte 01 - História` (número na ordem do podcast, tipo no nome, sem caracteres especiais), com progresso por corte. No fim: "N projetos criados no CapCut".
- O aviso do rodapé na fase de análise diz que só o texto da transcrição vai para a IA. O plano Basic dá acesso a Cortes; confira o plano no login como já fazemos para a Edição.

## Testes

- **Caso do tiro:** crie uma transcrição de teste com uma história que começa, é contada inteira e muda de assunto. O corte tem que começar na abertura, terminar no desfecho e não incluir a transição.
- Nenhum corte termina no meio de frase ou de palavra, e nenhum se sobrepõe a outro.
- Sem top-N: um podcast de 1 hora gera todos os assuntos completos acima do piso. Marcar só "Polêmico" gera só os polêmicos, e mudar os tipos não cobra nova análise.
- Vou lhe dar de 5 a 10 cortes bons de podcasts reais (início e fim). O resultado deve ficar a no máximo 1 frase do que marquei e **nunca terminar antes do desfecho**.
- Vídeo de 3 horas: memória estável, transcrição retomável, cancelar funciona.
- Cota esgotada, sem internet, e duas análises iguais seguidas cobrando uma só. A chave não aparece em nenhum arquivo do executável (busque por ela).
- Rodar os testes que já existem: nada do que funciona na Edição pode mudar.

## Não fazer agora

- Não criar outros modelos de corte além do Corte básico (a estrutura em JSON deixa pronto, mas só um existe).
- Não mexer na Edição, no Dashboard nem na barra lateral além do item novo.
- Não adicionar IA em mais nada (zoom, cortes secos e montagem continuam sem IA).
- Não decidir sozinho o que está na seção 10 da especificação (teto de duração, música, piso de força): use o padrão indicado, deixe configurável e me avise qual usou.
