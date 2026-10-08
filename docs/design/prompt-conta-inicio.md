Preciso de 6 mudanças no app: ajustes no **Início**, a **Legenda complexa** sai por enquanto, **Cortes** fica bloqueado como "Em breve" e a **conta da pessoa** passa a viver dentro do app (hoje ela está no site da Vercel), incluindo uma tela de **Plano e cobrança**. **Adapte o que existe, não refaça o app.**

A referência visual **aprovada** é `docs/design/conta-inicio-novo.html` (abra no navegador: clique nos 4 modelos do Início, em "Cortes" na barra lateral, no bloco da conta embaixo da barra lateral e nas duas abas da Conta; redimensione a janela). Use também os tokens e componentes que já existem (`docs/design/prompt-visual-dashboard.md`). Descubra e me diga: **onde está o arquivo da interface real**, **como o app guarda a lista de modelos e o que cada plano libera**, **onde hoje a conta é aberta no site da Vercel** (botões, links, menu) e **onde ficam os dados da conta no Supabase**. Depois me diga o plano em poucas linhas e **espere eu dizer "pode seguir"**.

## 1. Tirar "Cortes de podcast" do Início

Some dos botões de modelo do Início. O primeiro modelo vira **Cortes + headline** (pré-selecionado). Se o "último modelo usado" salvo era o Cortes de podcast, volte para o primeiro sem erro. A tela de Cortes e o código dele **não são apagados**. A linha "X de 10 análises neste mês" também sai do Início (era do Cortes).

## 2. "Suas edições recentes" (em vez de "Seus cortes recentes")

A faixa passa a mostrar as **últimas edições feitas neste computador, de qualquer modelo** (Cortes + headline, iPad + apresentador, React, Rotina, e as antigas que existirem): miniatura vertical, duração, **nome do projeto**, o **nome do modelo** embaixo e "Abrir no CapCut". Máximo 12, mais novas primeiro, rolagem lateral. A miniatura vem de um quadro real do projeto (use o cache de prévias que já existe; se não houver, gere um quadro pequeno com o ffmpeg uma vez e guarde em cache; se mesmo assim não der, um cartão neutro). **Sem edições ainda: esconda a seção inteira**, sem mensagem de vazio. "Ver todas" leva para Projetos. Reaproveite o histórico que a seção Projetos já usa; se não houver um registro de modelo por projeto, crie o mínimo necessário e me diga.

## 3. Remover "Legenda complexa" por enquanto

Tire o modelo da lista de modelos da **Edição**, do **Início** e dos tutoriais do Início. **Não apague o código**: desligue por um sinalizador simples na configuração de modelos (por exemplo `enabled: false`), para voltar com uma linha. Projetos já criados com esse modelo continuam abrindo normalmente em Projetos. Me diga o que mais referencia esse modelo (planos, textos, tutoriais).

## 4. Cortes bloqueado ("Em breve")

Na barra lateral, o item **Cortes** continua visível, mas com cadeado e a etiqueta "Em breve" (some a etiqueta abaixo de 720 px, onde a barra vira a do topo). Ao clicar, abre uma tela curta: "Cortes está chegando", uma frase e o botão "Voltar ao início" (texto no protótipo). Nada da seção Cortes carrega nem roda enquanto estiver bloqueada. Controle isso por **um único sinalizador** (por exemplo `cortesEnabled`), para liberar depois sem mexer em mais nada. **Atenção:** o plano Basic é só de cortes. Não mude nada nos planos; me diga como o app trata hoje quem está no Basic, para eu decidir.

## 5. A conta dentro do app (substitui a página da Vercel)

O bloco da conta no rodapé da barra lateral abre um menu com **Minha conta**, **Plano e cobrança** e **Sair**, e as duas primeiras levam à tela **Conta**, com duas abas: **Perfil** e **Plano e cobrança**. Troque todos os pontos onde o app hoje manda a pessoa para a Vercel por esta tela. **Não apague nada do site**; só o app deixa de depender dele para o dia a dia.

**Cabeçalho da Conta:** foto, nome, @username, e-mail, selo "Conta ativa/inativa", selo do plano e o círculo com os dias restantes.

**Aba Perfil** (tudo **real**):
- Foto: o botão da câmera troca a foto (JPG/PNG, redimensione para ~256 px). Guarde **só neste computador** (pasta do app) e use no cabeçalho e na barra lateral; se a pessoa nunca escolheu, a inicial do nome.
- Dados: Nome (editável, "Salvar" só liga quando muda), username e e-mail (só leitura). Nome salvo no Supabase.
- "Alterar senha": manda o e-mail de redefinição do Supabase e avisa "Enviamos um link para seu e-mail". Nunca peça nem mostre a senha.
- Três números: **projetos criados** (total neste computador), **neste mês** e **última edição**. Vêm do histórico real de projetos. Sem histórico, mostre "0" e "—", sem inventar.
- "Projetos criados": os 5 últimos (nome, modelo, quando) com "Abrir" e "Ver todos" para Projetos. Sem projetos, esconda a lista.
- "Sair da conta": confirmação ("Você volta para a tela de login. Seus projetos e vídeos continuam no seu computador.") e depois sai de verdade, como o app já faz hoje.

**Início:** a pílula "N dias restantes no plano" no canto leva à aba Plano e cobrança. Se a data de renovação real não existir, **não mostre a pílula**.

## 6. Plano e cobrança (valores de exemplo por enquanto)

Ainda não existem planos nem pagamento de verdade, então esta aba mostra **dados de exemplo**, com o aviso fixo no topo: "Prévia com valores de exemplo. Os planos e pagamentos reais chegam em breve." O conteúdo é o do protótipo: cartão do plano com os **dias restantes** e a barra do ciclo (começou em, renova em), "Próxima cobrança" (valor, data, forma de pagamento), "Status da conta" (situação, acesso até, chave "Renovação automática"), os 3 planos (Basic R$ 67, Ascendy R$ 197, Premium R$ 249) com "Mudar para este", "Histórico de pagamentos" (3 linhas, "Recibo") e "Cancelar assinatura" com confirmação.

**Regras para o exemplo não virar mentira:**
- Todos os valores de exemplo vêm de **um único módulo** (por exemplo `billing-demo`) com um sinalizador `DEMO = true`. Nada de números espalhados pelo código. Quando existir cobrança real, é só trocar a fonte.
- **Use dado real quando já existir** (status ativo/inativo, plano, data de validade no Supabase) e complete o resto com o exemplo. Me diga exatamente o que é real e o que é exemplo.
- Nenhum botão faz cobrança, troca de plano ou cancelamento de verdade: "Alterar pagamento", "Mudar para este" e "Recibo" mostram uma mensagem curta ("Em breve…"). Chave de renovação e confirmação de cancelar só mudam a tela, **sem gravar nada**. **Nunca peça número de cartão, nem guarde dado de pagamento.**
- Se `DEMO` for desligado e não houver dado real, **esconda as seções que dependem dele**, sem inventar.

## Visual e comportamento

- Mesmos tokens, fonte e raio do resto do app; lime só no que importa. Conteúdo da Conta numa coluna de até 900 px.
- Foco visível lime, tudo por teclado (setas entre as abas, Esc fecha as confirmações, foco volta ao botão que abriu), contraste de texto pequeno acima de 4,5:1, `prefers-reduced-motion`.
- Responsivo como o protótipo: abaixo de 860 px os cartões empilham; abaixo de 720 px a barra lateral vira a do topo e a tabela de histórico rola de lado.
- Sem internet: a Conta abre com os últimos dados salvos e diz "sem conexão"; salvar o nome e alterar a senha avisam que precisam de internet. Nada quebra.

## Como verificar

- Compare Início, "Cortes em breve", Conta (as duas abas) e as confirmações com `conta-inicio-novo.html`, lado a lado, em **1440×900 e 700×800**, e me mostre as capturas (diga onde salvou).
- **Rodada real, só pela interface:** troque a foto, feche e reabra o app (a foto continua); mude o nome e confirme no Supabase; peça a troca de senha; saia e entre de novo; gere uma edição e veja que ela aparece em "Suas edições recentes", em "Projetos criados" e nos números.
- Confirme: Cortes de podcast sumiu do Início, a Legenda complexa sumiu da Edição e do Início, Cortes não roda, e **nenhum botão do app abre mais a conta na Vercel**.
- Cenários: sem projetos (seções escondidas), conta inativa, sem data de renovação (pílula some), foto inválida, sem internet, plano Basic.
- Verifique que **nada na Conta é simulado fora do módulo de exemplo**: busque nos arquivos novos por números, datas e valores fixos.
- Rode os testes que já existem. A Edição (os wizards), o React e o login não podem mudar.

## Não fazer agora

- Nenhuma cobrança, gateway de pagamento ou integração de pagamento reais, e nenhum plano novo. Não mude o que cada plano libera.
- Não mexa nos wizards da Edição além de tirar a Legenda complexa da lista, nem na tela de Cortes além de bloquear.
- Não apague o site da Vercel nem o código de Cortes e Legenda complexa.
- Pare no fim e espere eu validar.
