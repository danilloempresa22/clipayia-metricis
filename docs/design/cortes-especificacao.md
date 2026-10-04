# Seção Cortes do Clipay.ia: especificação

Nova seção da barra lateral (Início, Edição, **Cortes**, Projetos, Tutorial). É um plano separado da Edição: é o **plano Basic**. A pessoa envia um vídeo longo (podcast de 1 a 3 horas), diz que **tipos** de corte quer (história, polêmico, emocional, engraçado, conselho), e o Clipay.ia transcreve, acha os melhores momentos e entrega **todos** como cortes completos, já editados, cada um em um projeto do CapCut. **A pessoa não escolhe cortes um por um no Clipay.ia**: ela escolhe o que postar depois, direto na lista do CapCut.

Referência visual interativa: `docs/design/cortes-novo-fluxo.html`.
Referência da edição: o projeto `docs/design/referencia-cortes/` (cópia do projeto "cortes ale pod cast") e os dois quadros ao lado dele.

## 1. A regra mais importante: o corte é completo

A unidade do corte é **um assunto**, não uma duração. O corte começa onde o assunto (ou a história) começa e **só termina quando o assunto muda**. Exemplo que já deu errado antes: o corte pegava "um dia, cara, eu levei um tiro" e acabava ali. Isso é um corte inútil. O certo é pegar ele contando a história inteira, até o desfecho, e parar quando passa para outro assunto.

Consequências para o projeto:

- Não existe duração fixa. O resultado varia. Alvo comum: de 1 a 4 minutos. Mínimo: 30 segundos. Teto padrão: 4 minutos, ajustável na tela Ajustes (a decidir, ver seção 10).
- **Nunca truncar** um assunto para caber no teto. Se o assunto inteiro passa do teto, o corte aparece marcado como "Longo" e o usuário decide (aceitar, ou ajustar o fim para uma frase anterior que ainda feche uma ideia). A IA pode sugerir um sub-trecho que também seja completo, mas nunca um que termine no meio.
- O corte **não inclui a frase de transição** ("mudando de assunto…", "voltando ao episódio…"). Termina na última frase que pertence ao assunto.
- O começo é a frase que introduz o assunto. Em podcast a história muitas vezes nasce de uma pergunta do apresentador ("e como foi isso?"). Se a pergunta é curta (até uns 15 s) e sem ela o corte não se entende, ela entra.
- Um começo ruim é o que depende do que veio antes: abre com "então", "mas", "e aí", "isso", "ele" sem dizer quem. A IA deve escolher o começo onde dá para entender sem contexto.

## 2. O que é um "melhor momento"

Os tipos (cada um é uma opção na tela Tipos): **História** (com começo, meio e fim), **Polêmico**, **Emocional** (triste, perda, virada), **Engraçado** e **Conselho** (uma ordem ou promessa clara). Cada momento recebe:

- uma ou duas categorias das acima (a primeira é a principal; o filtro da tela Tipos casa com qualquer uma delas),
- força de 0 a 100,
- uma frase dizendo por que é bom (aparece só como apoio, o usuário não precisa ler),
- primeira e última frases reais, tiradas da transcrição (nunca escritas pelo modelo).

A força serve para descartar o que é fraco, não para o usuário escolher: ela pesa gancho nos primeiros 5 segundos, a ideia fechar sozinha, a presença de emoção ou conflito, e o desfecho. Eu não tenho os critérios finais dele. Os acima são um ponto de partida para ele corrigir com exemplos reais (seção 10).

## 3. Como o app acha os momentos (pipeline)

### 3.1 Transcrição (local, no computador dele)

Reaproveita o Whisper local e o plano de `prompt-transcricao-rapida.md` (janelas cheias, cache, segundo plano). Para 2 ou 3 horas ficam exigências novas:

- `audio.pcm()` hoje carrega o áudio inteiro na memória. Em 3 horas a 16 kHz isso passa de 340 MB (int16) ou 690 MB (float32). Ler e processar **por janelas** (por exemplo 10 minutos) ou gravar um WAV temporário e usar `numpy.memmap`.
- A transcrição precisa **sobreviver ao app fechar**: gravar o resultado por janela em disco (cache por caminho, tamanho e data do arquivo) e retomar de onde parou.
- Barra de progresso real e botão cancelar. A pessoa pode usar o resto do app enquanto roda.
- Frases com **início e fim em segundos** (nível de frase, não só pedaços de 6 a 15 s como `transcricao.frases` faz hoje). A IA trabalha com frases numeradas.
- Os limites do corte são **ajustados no áudio**: a frase escolhida como começo ou fim é puxada para a pausa mais próxima (≥ 250 ms) usando a régua de silêncio que já existe, para nunca cortar no meio de uma palavra. Folga de 0,3 s depois do fim.

### 3.2 Achar os assuntos e escolher (IA, só texto)

Mesma arquitetura da headline (ver `prompt-ajustes-headline-cortes.md`): uma Edge Function do Supabase (`achar-cortes`) recebe a sessão e a transcrição, confere plano e cota, chama o modelo e devolve JSON. A chave nunca fica no executável.

1. **Passo 1: segmentar por assunto.** A transcrição vai em janelas de cerca de 15 minutos com 2 minutos de sobreposição, cada frase com id e tempo (`412 | 1:12:40 | Cara, um dia eu levei um tiro…`). O modelo devolve a lista de assuntos: id da primeira frase, id da última, título curto, categoria. As janelas são costuradas no código (assunto que cruza a borda vira um só).
2. **Passo 2: dar nota.** Para cada assunto, o modelo dá força e motivo. Pode ser na mesma chamada do passo 1, se o modelo escolhido aguentar.
3. **Entrega tudo, sem top-N.** A ferramenta gera o **máximo de cortes que conseguir**: todo assunto completo que passar de um piso de força (padrão 50 de 100, configurável, só para não gerar lixo) e do mínimo de duração. Não existe limite de quantidade escolhido pelo usuário. O filtro por tipo é aplicado **no código**, depois, sobre a lista completa.
4. **Validação no código, sem confiar no modelo:** ids existem e estão em ordem; sem sobreposição (se dois cortes se cruzam, fica o de maior força); duração mínima e teto; o começo e o fim exibidos vêm da transcrição real; o fim não é uma frase de transição.
5. **Cache:** por (usuário, hash da transcrição, versão das regras). Mudar o teto de duração ou os tipos reaproveita os assuntos já achados e só refaz a seleção, sem nova cobrança.

Custo: 3 horas ficam em torno de 30 a 35 mil palavras, algo como 50 mil tokens de entrada. Com um modelo pequeno isso é centavos por vídeo, mas o Claude Code **deve me dizer o modelo escolhido e o custo estimado por vídeo antes de contratar qualquer provedor**.

### 3.3 O que muda nas regras do produto

Até aqui o Clipay.ia só usava IA para headline. Agora a **escolha dos momentos** também usa. Cortes secos, zoom e montagem continuam sem IA. Isto precisa ficar claro nos Termos e na política de privacidade: o vídeo e o áudio nunca saem do computador, **só o texto da transcrição vai para a IA**, uma vez por vídeo. Aqui vai mais texto do que na headline (a conversa toda), então o aviso na tela de análise tem que dizer isso com todas as letras (já está no protótipo).

Sem internet ou sem cota: não existe alternativa boa sem IA para achar assuntos. A tela mostra isso claramente e oferece o modo manual (a pessoa digita início e fim de cada corte).

## 4. A edição de cada corte (medida no projeto de referência)

Medido em `referencia-cortes/draft_content.json` e no clipe composto em `subdraft/`. É o corte "mais básico": o ponto de partida do modelo **Corte básico**.

**Estrutura.** O projeto tem um clipe composto. Dentro dele (canvas 1:1, 1920×1920) estão os pedaços do vídeo original (2560×1440, 70 minutos na amostra). Por fora (canvas 9:16, 1080×1920, 30 fps, fundo preto) estão o composto, a headline e a música.

**Corte seco (dentro do composto).** A amostra tem 13 pedaços, de 1,33 a 4,63 s, de um trecho do original de 900,5 s a 943,4 s (43 s). Os intervalos removidos entre pedaços foram de 0,33 a 0,87 s. É a mesma ideia do modo Reels (`reels.regua` + `divide_longos`): reaproveitar. Os pedaços ficam colados no tempo, sem espaço entre eles.

**Zoom por pedaço.** A base é escala **1,823** (um quadrado centrado na pessoa recortado do 16:9, com 2,5% de folga). Mais ou menos a cada 3 pedaços há um zoom: **empurrão** (keyframes lineares de posição e escala do início ao último quadro do pedaço) ou **fixo**. Na amostra: pedaço 1 empurra de 1,823 para 2,161; pedaço 4 empurra de 1,823 para 2,111; pedaço 7 fica fixo em 2,199. Em relação à base são fatores de 1,16 a 1,21, o mesmo intervalo das tabelas `ESTATICO` e `EMPURRAO` de `reels.py`. **Reaproveitar as tabelas e o `plano_zoom`, aplicando os fatores sobre a base 1,823.** Detalhes que a amostra mostra e precisam estar no código:

- A posição horizontal e vertical de cada pedaço **acompanha a pessoa** (x de −0,093 a +0,266 na amostra). Vale a regra já definida: centrar na pessoa, sem escolha de lado.
- Fórmula, com o original 16:9 encaixado na largura do canvas 1:1: o limite horizontal é `|x| ≤ s − 1` e o vertical é `|y| ≤ 0,5625·s − 1`. Conferido na amostra: no empurrão do pedaço 1, `y = −0,2156` é exatamente o limite para `s = 2,161`. Ou seja, o zoom desce o quadro até o limite para mostrar a cabeça, e **nunca passa disso** (sem borda preta). Para outro original (por exemplo vertical, ou 4:3), recalcular com a proporção real.
- Para centrar a pessoa: `x = −px·s` e `y = −py·0,5625·s`, com `px` e `py` a posição do rosto em relação ao centro do quadro (de −1 a 1, y positivo para cima), sempre limitado como acima. Se a detecção falhar, x = 0 e y = 0.

**Camada externa (o clipe composto).** O volume da fala **não é alterado** (a amostra tinha +10 dB, mas foi só um teste dele e não faz parte do modelo; o composto sai com volume 1,0).

| Item | Valor medido |
|---|---|
| Velocidade | 1,13x (34,93 s viram 30,9 s) |
| Escala / posição | 1,0 / x 0, y −0,128 (quadrado um pouco acima do centro) |
| Efeito | "Estroboscópio de tremor", id `7395467839634803974`, no composto inteiro. Parâmetros: intensidade 0,2, animação de fundo 0,5, luminância 0,2, velocidade 0,3 |

**Headline.** Texto em 2 linhas, fonte **Classic** (id `7545362071773367568`), tamanho 15, escala 0,634, posição (0, 0,511), branco, centralizado, durante o corte todo. **O Clipay.ia não escreve a headline dos cortes**: cada projeto sai com o texto de exemplo da referência, `SUA HEADLINE AQUI` / `SOBRE O SEU CORTE`, e ele troca depois no CapCut. É o mesmo modelo de headline do Reels e da Rotina: reaproveitar `headline_tpl.json` e `reels.headline`. **Conferir** se escala e posição do modelo atual batem com estes números e, se não, usar estes.

**Música.** Um MP3 local ("gravitational forces.MP3" na amostra), volume **0,053** (cerca de −25,5 dB) durante o corte inteiro, começando do começo da música, sem fade. O usuário escolhe o arquivo uma vez em Ajustes e o app lembra. Sem ducking (o volume já é baixo).

## 5. Os cortes viram vários projetos

**Todos** os cortes saem de uma vez, cada um em um projeto do CapCut, com o nome `<nome do vídeo> - corte 01 - História`, `corte 02 - Polêmico` e assim por diante, na ordem em que aparecem no podcast. O tipo vai no nome para ele filtrar na lista do CapCut. Sem caracteres especiais no nome. Um podcast de 1 hora pode render dezenas de projetos: gravar em lote e mostrar progresso por corte. O vídeo original **não é copiado**: cada pedaço aponta para o arquivo original com os tempos de início e fim (`source_timerange`), como na amostra. Isso importa: o original pode ter mais de 10 GB.

Como o composto é novo para o app (nenhum código atual cria um), o jeito seguro é **usar o projeto de referência como modelo**, como `carrega_tpl` faz com a headline: o Clipay.ia lê `referencia-cortes/` como template e troca só o que varia (pedaços, tempos, textos, caminhos, música). Pontos que o projeto de referência mostra:

- O composto tem uma pasta própria `subdraft/<id>/` com `draft_content.json`, `sub_draft_config.json` e `draft_cover.jpg`.
- O rascunho interno aparece **duas vezes**: dentro de `materials.drafts[0].draft` do projeto externo e no arquivo da pasta `subdraft`. As duas têm que ser iguais.
- `materials.drafts[0]` tem `draft_file_path`, `draft_cover_path` e `draft_config_path` com o marcador `##_draftpath_placeholder_<GUID>_##`. O `draft_meta_info.json` registra o composto como material do tipo 18 apontando para `./subdraft/<id>/sub_draft_config.json`. Isso é o que costuma causar o aviso de "Mídia perdida" quando erra.
- `Resources/combination/<combination_id>_audio.aac` é **cache** que o CapCut gera sozinho (na amostra nem decodificava inteiro). A hipótese é que ele refaz quando falta. **Testar abrindo o projeto gerado e ouvindo o áudio.** Se vier mudo, tratar isso antes de qualquer outra coisa.
- O vídeo original tem um material por pedaço, todos com o mesmo caminho (`clona_segmento` já faz isso).

## 6. Telas (protótipo: `cortes-novo-fluxo.html`)

Passos: **Modelo, Vídeo, Tipos, Transcrição, Ajustes, Gerar.** Mesmo molde do wizard da Edição. **Não existe tela de escolher corte por corte.**

1. **Modelo.** Lista com "Corte básico" (pré-selecionado) e um cartão "Mais modelos de corte, em breve". À direita, prévia 9:16 (quadrado no meio, headline em cima, linha do tempo com os cortes secos). Vídeo real depois.
2. **Vídeo.** Um arquivo longo. "Escolher vídeo" não copia o arquivo.
3. **Tipos.** "Que tipo de corte você quer?": cinco cartões marcáveis (História, Polêmico, Emocional, Engraçado, Conselho), todos marcados de saída, com "Limpar seleção". Pelo menos um tem que ficar marcado. É o único momento em que a pessoa escolhe algo sobre os cortes.
4. **Transcrição.** Duas fases na mesma tela: 1) transcrever no computador, 2) achar os cortes (só o texto vai para a IA). O aviso do rodapé muda na fase 2. No fim: "Encontramos N cortes completos" (N já considera os tipos marcados).
5. **Ajustes.** Só o acabamento: velocidade 1,13x, efeito de tremor e música (com "Trocar"). Sem volume da fala e **sem headline** (ela é trocada depois no CapCut).
6. **Gerar.** Um projeto por corte, com progresso individual, o tipo e a duração, e no fim "N projetos criados no CapCut" com a instrução de escolher lá quais postar.

## 7. Plano e cota

Cortes é o Basic. A cota é por **análise de vídeo** por mês (1 vídeo longo = 1 análise, mesmo com 3 horas), guardada no Supabase e ajustável sem novo build. Não há limite de cortes por vídeo no plano (padrão), mas o campo existe na configuração. A mudança de teto de duração ou de tipos não gasta nova análise (cache). Não guardar a transcrição no servidor, só a contagem.

## 8. Vários modelos de corte (futuro)

O Corte básico é o primeiro. Para os próximos entrarem sem reescrever o app, o modelo é **dados**: um arquivo `cortes/modelos/basico.json` com layout (canvas externo, tamanho e posição do quadrado), tabelas de zoom, velocidade, volume da música, efeito, modelo de headline e a faixa de duração. Um modelo novo é outro JSON e, se mudar a estrutura (por exemplo sem composto), uma variante no montador. Não criar os outros modelos agora.

## 9. Testes

- **Montador sem IA** (primeiro de tudo): dado um vídeo e um intervalo de início e fim digitados, gera o corte. Reproduzir a amostra (de 900,5 s a 943,4 s) e comparar com o projeto de referência: 13 pedaços colados, velocidade, zoom e posições dentro dos limites, headline, música, efeito. Abrir no CapCut: sem "Mídia perdida", com som.
- **Caso do tiro** (corte completo): uma transcrição de teste em que alguém começa uma história, a conta inteira e muda de assunto. O corte tem que começar na abertura, terminar no desfecho e **não incluir** a frase de transição nem pegar só o começo.
- Nenhum corte termina no meio de uma frase nem de uma palavra; nenhum se sobrepõe a outro.
- Sem top-N: num podcast de 1 hora saem todos os assuntos completos acima do piso. Mudar os tipos na tela Tipos filtra a lista sem nova análise.
- Conjunto de teste de verdade: ele marca de 5 a 10 cortes bons em podcasts reais (início e fim). O app deve cair a no máximo 1 frase de distância dos marcados e **nunca terminar antes do desfecho**.
- Vídeo de 3 horas: memória estável (sem carregar o áudio inteiro), transcrição retomável depois de fechar o app, cancelar funciona.
- Cota esgotada e sem internet mostram a mensagem e o modo manual. A chave não aparece em nenhum arquivo do executável. Duas análises iguais seguidas cobram uma só.

## 10. O que eu ainda preciso dele

1. **Teto de duração.** Ele quer cortes com o assunto inteiro. Qual o maior corte aceitável: 3, 4 ou 5 minutos? (Reels e Shorts aceitam 3 minutos hoje; confira a regra atual antes de fixar.)
2. **Exemplos reais:** de 5 a 10 cortes que ele considera perfeitos, com início e fim, de podcasts diferentes. Isso calibra o pedido ao modelo e vira o conjunto de teste.
3. **O vídeo do Ale tem uma câmera só ou alterna entre os dois?** A amostra tem posições de rosto bem diferentes entre pedaços, e isso muda como centrar a pessoa.
4. **Música:** uma fixa, ou uma pasta com várias (uma por corte, sorteada)?
5. **Piso de força** (padrão 50) para não gerar cortes fracos: confirmar depois de ver os primeiros resultados reais.
