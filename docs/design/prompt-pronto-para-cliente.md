Quero testar o Clipay.ia **como um cliente que acabou de pagar**, no Windows e num **MacBook**. O cliente baixa o app por um link, abre e usa. Ele **nunca** abre Terminal, nunca instala Python e nunca mexe em pasta escondida. Hoje isso não existe, principalmente no Mac. Este prompt é para deixar isso pronto. **Adapte o que existe, não refaça o app.**

**Decisão nova:** o Mac entra agora para o beta, só para teste. Atualize o `CLAUDE.md`, que ainda diz "Windows apenas", e me diga o que mais lá ficou desatualizado.

Antes de mexer, leia `CLAUDE.md`, `cortesapp.spec`, `.github/workflows/build.yml`, `cortesapp/capcut.py` e o motor dos modelos (Cortes + headline, iPad + apresentador, React, Rotina). Descubra e me diga:
- se o projeto já está no GitHub e atualizado. Se não estiver, **você faz o envio**; me peça só o que precisar que eu clique (login do GitHub, token);
- quais caminhos fixos do **meu** computador estão no código ou nas referências dos modelos (`C:/Users/USUARIO/...`, fontes, cache de efeitos do CapCut);
- o que o app precisa baixar da internet na primeira vez (modelo de transcrição, etc.);
- o que impede o app de rodar num Mac hoje.

Depois me diga o plano em poucas linhas e **espere eu dizer "pode seguir"**. Faça em **2 partes** e **pare no fim de cada uma** para eu testar.

---

## Parte 1: o app que o cliente baixa e abre

### 1.1 Nome e build
- O app gerado se chama **Clipay.ia** em tudo o que o cliente vê: nome do arquivo, nome do app, título da janela, ícone (`docs/design/logo-clipay-mark.png`) e o identificador do app no Mac. Não precisa renomear as pastas internas do código agora.
- Use o `build.yml` que já existe, que gera Windows e Mac, e corrija o que estiver quebrado.
- Cada versão vira um **Release no GitHub** com os dois arquivos para baixar: `Clipay.ia-Windows.zip` e `Clipay.ia-Mac.zip`. O número da versão aparece dentro do app (no rodapé da Conta, por exemplo).
- Me diga **o link** que eu mando para o cliente. Se o repositório é privado e o cliente não consegue baixar por ele, proponha onde hospedar (por exemplo, o site na Vercel com um botão "Baixar para Windows" e "Baixar para Mac"). **Pergunte antes de decidir.**

### 1.2 Mac
- **Funciona nos Macs com chip da Apple (M1 ou mais novo).** O ffmpeg baixado hoje no build (evermeet.cx) é para Intel. Troque por um que rode nativo no chip da Apple, ou gere uma versão para cada tipo de Mac, e **me diga qual escolheu**. O mesmo vale para o onnxruntime e para a janela do app (pywebview).
- **Achar o CapCut do Mac:** o `capcut.py` já procura em `~/Movies/CapCut/...` e na versão em contêiner. Confirme que isso funciona com o CapCut atual do Mac e me diga a versão que você considerou.
- **Nada de caminho do Windows nos projetos gerados no Mac.** As referências dos modelos têm caminhos como `C:/Users/USUARIO/AppData/Local/Microsoft/Windows/Fonts/CreatoDisplay-Bold.otf` e `C:/Users/USUARIO/AppData/Local/CapCut/User Data/Cache/...`. Em qualquer computador, Windows ou Mac, esses caminhos têm que ser montados **a partir do computador da pessoa** (pasta do CapCut dela, cache de efeitos dela). **Isso vale para o Windows de outro cliente também.**
- **Fonte da headline (CreatoDisplay-Bold):** hoje ela só existe no meu computador. Diga como resolver em qualquer máquina (embutir no app, usar a do cache do CapCut, trocar por outra). **Não embuta nenhuma fonte sem me falar antes**, porque pode ter questão de licença.
- **Formato do projeto do CapCut no Mac:** confira se o CapCut do Mac lê o mesmo formato que o app grava, e se o arquivo vem criptografado em alguma versão. Se não der para gravar, o app avisa com uma frase clara, nunca gera projeto quebrado.
- **Arrastar e soltar:** no Mac, confirme que arrastar um vídeo para o app entrega o caminho do arquivo. Os vídeos **não são copiados**. Se não entregar, o botão "Escolher vídeo" tem que funcionar sempre.
- **Permissões:** quando o Mac pedir acesso às pastas (Filmes, Downloads, Mesa), o texto do pedido vem em português e explica o porquê ("O Clipay.ia precisa ler seus vídeos e criar o projeto no CapCut").

### 1.3 Windows
- O `.zip` do Windows abre num PC **sem Python e sem nada instalado**, com dois cliques.
- Teste com uma pasta do CapCut diferente da minha e com o nome de usuário do Windows com acento e espaço.

### 1.4 O que precisa estar dentro do app
- ffmpeg, o transcritor e tudo o que os modelos usam vêm **dentro do app**. Se o modelo de transcrição for grande demais e tiver que ser baixado na primeira vez, mostre uma tela "Preparando o Clipay.ia (só na primeira vez)" com uma barra de progresso real e uma mensagem clara se a internet cair.
- Me diga o **tamanho final** de cada `.zip`.

**Pare aqui** e me mande o link do Release. Eu baixo pelo navegador no Mac e num PC, como cliente.

---

## Parte 2: o cliente não pode ficar travado

### 2.1 Página "Como instalar"
Uma página simples, no site, onde o cliente baixa o app. É ela que eu mando junto com o link. Ela tem o passo a passo **com prints** e sem nenhum termo técnico:

- **Windows:** baixar, extrair o `.zip` e abrir o Clipay.ia. Quando aparecer "O Windows protegeu o computador", clicar em "Mais informações" → "Executar assim mesmo".
- **Mac:** baixar, abrir o `.zip` e arrastar o Clipay.ia para Aplicativos. Quando aparecer "Não foi possível verificar o desenvolvedor", ir em Ajustes do Sistema → Privacidade e Segurança → "Abrir mesmo assim". Confira o texto exato e o caminho na versão atual do macOS.

Isso acontece porque o app não é assinado. Por enquanto vamos sem assinatura. Me diga em 3 linhas o que precisaria para assinar no Mac (conta de desenvolvedor da Apple) e no Windows, e quanto custa, **sem fazer nada disso agora**.

### 2.2 Tela "Verificar minha configuração"
Ela abre sozinha **na primeira vez** e também pela Conta. Mostra uma lista com ✓ verde ou um aviso para cada item, em frase simples:
- CapCut encontrado (e a versão, se der para saber);
- pasta de projetos encontrada, com o botão "Escolher a pasta" se não achar;
- ffmpeg funcionando;
- transcrição funcionando;
- fontes e modelos da headline disponíveis;
- conexão com a conta.

Cada aviso diz **o que a pessoa faz** ("Abra o CapCut uma vez e feche"), nunca um erro técnico. O botão "Verificar de novo" refaz a checagem. **Nada simulado:** tudo é checado de verdade.

### 2.3 Botão "Reportar problema"
- Fica na Conta e em toda mensagem de erro.
- Abre uma janela com um campo "O que aconteceu?" e envia: versão do app, sistema (Windows ou Mac e a versão), versão do CapCut, o modelo que estava usando e as **últimas linhas do log**.
- Guarde no Supabase, numa tabela nova com RLS, em que o usuário só consegue inserir, nunca ler o dos outros. **Nunca envia vídeo, transcrição nem caminho de pasta com o nome da pessoa.** Me mostre o SQL antes de rodar.
- Me diga onde eu vejo os relatos.

### 2.4 Aviso de versão nova
- Ao abrir, o app confere se existe versão mais nova (lida do Release do GitHub ou de um arquivo no site).
- Se existir, mostra uma faixa discreta "Tem uma versão nova do Clipay.ia" com o botão "Baixar", que abre a página de download.
- Não atualiza sozinho. Sem internet, não mostra nada e não trava.

---

## Como verificar

- **Parte 1:** me mande o link do Release e o tamanho dos arquivos. **Eu** testo, como cliente, no MacBook e num PC sem Python:
  - baixar pelo navegador;
  - abrir;
  - fazer login;
  - gerar 1 vídeo de **Cortes + headline**, 1 de **React** e 1 de **iPad + apresentador**;
  - abrir os projetos no CapCut.

  Antes disso, rode você mesmo o que der nos computadores do GitHub (abrir o app, gerar um projeto de teste) e me mostre o resultado.
- **Parte 2:** capturas da página "Como instalar", da tela "Verificar minha configuração" (tudo ok e com problemas), do "Reportar problema" e da faixa de versão nova, em **1440×900 e 700×800**.
- **Cenários:** CapCut não instalado, pasta do CapCut em outro lugar, sem internet na primeira abertura, conta inativa, usuário do Windows com acento, Mac com chip da Apple.
- Rode os testes que já existem. Os modelos e o login não podem mudar no Windows.

## Não fazer agora

- Assinatura do app (Apple e Windows), atualização automática, instalador e cobrança.
- Não mude nada no que os modelos de edição produzem, além de trocar os caminhos fixos pelos do computador da pessoa.
- Não embuta fonte sem me perguntar.
- Pare no fim de cada parte e espere eu validar.
