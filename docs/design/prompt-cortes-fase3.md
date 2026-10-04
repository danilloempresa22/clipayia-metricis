As Fases 1 e 2 da seção **Cortes** foram validadas (montador de um corte e transcrição de vídeo longo). Agora é a **Fase 3: achar os cortes com IA**. Ainda sem tela (a tela é a Fase 4). No fim, quero rodar de ponta a ponta num podcast real: transcrever, achar todos os cortes e montar os projetos.

Leia antes de mexer: `docs/design/cortes-especificacao.md` (a seção 3 é esta fase), `docs/design/prompt-cortes.md` (plano das fases), e o que a Fase 2 deixou pronto (frases com tempo, pausas e `ajusta_limite`). Se já existir no projeto uma chamada autenticada a uma Edge Function do Supabase (a da headline, por exemplo), reaproveite o jeito; se não existir, crie um cliente simples seguindo o login e a sessão que o app já tem. Depois me diga o plano em poucas linhas e espere eu dizer "pode seguir".

## A regra que não pode quebrar

O corte é um **assunto inteiro**: começa onde o assunto ou a história começa e **só termina quando o assunto muda**. O erro que já tive: o corte pegava "um dia, cara, eu levei um tiro" e acabava ali. O certo é ele contando a história até o desfecho e parando quando muda de assunto. Nunca truncar para caber em duração. Nunca incluir a frase de transição ("mudando de assunto…", "voltando ao episódio…"). Tudo abaixo existe por causa disso.

## Antes de gastar dinheiro

**Antes de contratar qualquer provedor pago ou chamar um modelo de verdade, me diga:** qual modelo você escolheu (pequeno, barato, bom em português do Brasil), o nome dele numa configuração (não espalhado no código), e o **custo estimado por vídeo de 3 horas** (conta de tokens de entrada e saída). Espere eu aprovar. Todo teste de lógica (costura, validação, cota, cache) usa um modelo falso (mock), sem custo.

## O que fazer

**1. Edge Function `achar-cortes` (Supabase).** A chamada ao modelo **não** pode ficar no executável: a chave fica só nos segredos da função. A função recebe a sessão do usuário e as frases numeradas (`id`, `ini`, `fim`, `locutor`, `texto`), confere se o plano tem acesso a Cortes e a cota do mês, chama o modelo e devolve JSON. Deixe pronto o código em `supabase/functions/achar-cortes/` e uma migração SQL para as tabelas abaixo. **Não faça deploy nem rode a migração sozinho:** me diga os comandos exatos para eu rodar (ou peça minha confirmação se a CLI já estiver logada).

**2. Como a função trabalha.** Divide as frases em janelas de cerca de 15 minutos com 2 minutos de sobreposição e chama o modelo por janela (poucas chamadas em paralelo, com limite). Costura as janelas: um assunto que cruza a borda vira um só. Responde com **todos** os assuntos completos, não um top-N.

**3. Regras que o pedido ao modelo precisa impor** (são as minhas):

- A unidade é um **assunto**. O corte começa na frase que introduz o assunto e termina na última frase que ainda pertence a ele, quando o assunto muda. **A frase de transição não entra.** Histórias vão **até o desfecho**: nunca terminar antes dele.
- **O foco é o convidado.** O corte começa na primeira frase do convidado que abre o assunto e termina na última frase do convidado daquele assunto. **A pergunta do apresentador não entra e não abre corte** (mesmo que o apresentador comece com uma sacada antes de perguntar). Falas curtas do apresentador no meio (até uns 3 s) podem ficar; a soma da fala do apresentador no corte tem que ser pequena. Uma nova pergunta do apresentador encerra o corte. **Abertura e encerramento do episódio, chamada para curtir e se inscrever e patrocínio não são corte.** Evitar começar com frase que depende do que veio antes ("então", "mas", "isso", "ele" sem dizer quem).
- Tipos: **história** (começo, meio e fim), **polêmico**, **emocional** (triste, perda, virada), **engraçado** e **insight** (a pessoa ensina algo, um conhecimento ou uma sacada). Cada assunto recebe uma ou duas categorias, a primeira é a principal.
- Força de 0 a 100, pesando: gancho nos primeiros 5 segundos, a ideia fechar sozinha sem contexto, emoção ou conflito, e o desfecho.
- Duração: mínimo 20 s; teto configurável (padrão 4 minutos, lido da configuração). Se o assunto inteiro passar do teto, devolver o assunto **inteiro** marcado como `longo`, nunca um pedaço que termina no meio.
- **Só usar ids que existem na entrada.** O modelo nunca escreve o texto das frases: o começo e o fim exibidos vêm da transcrição real.
- **Entregar tudo, sem top-N:** todo assunto completo acima de um piso de força (padrão 50, configurável) e do mínimo de duração. O modelo não deve se conter para "escolher os melhores"; quem filtra por tipo depois é o código.
- Formato da resposta, por assunto: `{ "ini_id": 412, "fim_id": 468, "categorias": ["historia","emocional"], "forca": 92, "longo": false, "titulo": "...", "motivo": "..." }`. O título e o motivo servem para eu avaliar nos testes.

**4. Tabelas e configuração (ajustáveis sem novo build).** Cota mensal de **análises** por plano (1 vídeo longo = 1 análise, mesmo com 3 horas); quais planos têm acesso a Cortes; nome do modelo; teto de duração; piso de força; limite de pedidos por minuto. Comece com um valor inicial razoável e **me diga qual**. Cache por (usuário, hash da transcrição, versão das regras): repetir a mesma análise **não cobra de novo**, e mudar o teto de duração ou os tipos reaproveita o que já foi achado. **Não guarde a transcrição nem o texto no servidor:** só a contagem de uso e, no cache, os ids, as categorias e a força.

**5. Cliente no app (`cortesapp/achar.py` ou similar).** Função `achar_cortes(frases, tipos, ...)` que chama a função, **valida tudo no código local** contra a transcrição real e devolve a lista final:

- ids existem e estão em ordem; sem sobreposição (se dois assuntos se cruzam, fica o de maior força); mínimo e teto respeitados;
- se a última frase do assunto for de transição, tire-a (desde que ainda sobre o mínimo);
- aplica o filtro pelos tipos marcados **no código**, sobre a lista completa;
- converte os ids em início e fim em segundos e passa pelo `ajusta_limite` da Fase 2 (começo logo antes da primeira palavra, fim com 0,3 s de folga), para nunca cortar no meio de palavra;
- cada item sai com: número (ordem no podcast), categoria principal, início, fim, duração, força, `longo`, e a primeira e a última frase reais.

**6. Sem internet ou sem cota.** Mensagem clara, sem travar, e o **modo manual**: a pessoa digita início e fim de cada corte (é a Fase 1). Não existe alternativa boa sem IA para achar assuntos, então não invente uma.

**7. Gerar todos.** Uma função que pega a lista final e chama o montador da Fase 1 para **cada** corte, um projeto do CapCut por corte, com o nome `<nome do vídeo> - corte 01 - História` (número na ordem do podcast, tipo no nome, sem caracteres especiais; se for `longo`, acrescente ` - longo`). Com progresso por corte. Os projetos saem com a headline de exemplo, como na Fase 1.

## Como verificar

- **Caso do tiro:** crie uma transcrição de teste com uma história que começa, é contada inteira e muda de assunto. O corte tem que começar na abertura, terminar no desfecho e **não incluir** a frase de transição nem pegar só o começo. Teste a validação também com respostas falsas ruins do modelo (id inexistente, corte que termina antes do desfecho, sobreposição): o código tem que corrigir ou descartar.
- Nenhum corte termina no meio de frase ou de palavra, e nenhum se sobrepõe a outro.
- Sem top-N: marcar só "Polêmico" gera só os polêmicos, e **mudar os tipos não faz nova chamada nem nova cobrança**. Duas análises iguais seguidas cobram uma só.
- Cota esgotada, sem internet e função fora do ar mostram a mensagem e o modo manual.
- **A chave não aparece em nenhum arquivo do executável** (busque por ela).
- Se existir `tests/fixtures/cortes-ouro.json` com os cortes bons que eu marquei (início e fim em podcasts reais), compare: o resultado deve ficar a no máximo 1 frase de distância e **nunca terminar antes do desfecho**. Se o arquivo não existir, me peça.
- **Rodada real (depois de eu aprovar o custo):** transcreva o podcast de 70 minutos (`C:\Users\danil\Downloads\Qual foi o momento - Ale EP6.mp4`, somente leitura), ache os cortes e **gere os projetos numa pasta de teste, não na lista do CapCut**; depois copie **3** deles para a lista do CapCut para eu abrir. Me mostre: o modelo e o custo **medidos**, quantos cortes saíram por tipo, e uma tabela com número, tipo, início, fim, duração, força, `longo`, primeira e última frase. Eu confiro se os cortes estão completos.
- Rode os testes que já existem: a Edição e as Fases 1 e 2 não podem mudar.

## Não fazer agora

- Nada de tela de Cortes (Fase 4) nem de geração de headline: a IA daqui só acha os cortes.
- Não adicione IA em mais nada (zoom, cortes secos e montagem continuam sem IA).
- Não mexa na Edição, no Dashboard nem na barra lateral.
- No Termos e na política de privacidade: me avise **onde** precisam dizer que, na análise dos cortes, o vídeo e o áudio nunca saem do computador, só o texto da transcrição vai para a IA, uma vez por vídeo.
- Pare no fim da Fase 3 e espere eu validar os cortes.
