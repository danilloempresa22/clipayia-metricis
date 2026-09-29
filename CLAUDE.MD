# Clipay.ia

MicroSaaS que automatiza o fluxo de edição "cortes + headline" no CapCut: usuário importa um vídeo bruto, o produto corta silêncio/respiração, aplica zoom punch-in, e entrega um projeto novo pronto no CapCut. A parte de "julgamento" (headline, cortes de conteúdo por sentido) fica manual, decidida pelo usuário numa tela de revisão — sem chamada de IA por vídeo.

Design completo validado em `docs/plans/2026-09-29-clipay-ia-design.md`. Este arquivo é o resumo operacional para trabalhar no código; consulte o design doc para o "porquê" das decisões.

**Nome do produto: Clipay.ia — não CortesApp.** Este arquivo hoje mora dentro da pasta/repositório antigo `CortesApp` (é de lá que o motor reaproveitado vem), mas isso é legado, não o nome definitivo. **Primeira tarefa de implementação:** renomear a pasta/repositório e o pacote Python interno (`cortesapp/` → algo como `clipay/`) para refletir o nome Clipay.ia, ajustando os imports e o `cortesapp.spec` (nome do executável gerado, ícone) de acordo. Depois disso, tratar todo o restante deste documento como aplicável ao projeto já renomeado.

## O que este projeto NÃO é

Não é o CortesApp (app avulso vendido separadamente) — é um produto novo e paralelo. Mas o motor de edição do CortesApp já existe, já está validado contra edições reais aprovadas, e deve ser reaproveitado como base (ver seção "Reaproveitamento" abaixo). Não escrever esse motor do zero.

## Arquitetura

Duas metades, propositalmente simples:

1. **App local (o motor)** — um único executável Windows (PyInstaller `--onefile`, sem instalador, sem assinatura de código). Ao abrir, sobe um servidor local (Flask/FastAPI) e abre o navegador padrão em `localhost`. Faz todo o processamento: lê áudio direto do vídeo (ffmpeg), transcreve com Whisper offline (onnxruntime), detecta silêncio, corta, aplica zoom, escreve o `draft_content.json`/`draft_meta_info.json` novo direto na pasta do CapCut.
2. **Backend Supabase** — só a camada de conta: login, status ativo/inativo, contador de uso. Não processa nem armazena vídeo. Ver `supabase/migrations/0001_init.sql` para o schema.
3. **Painel web** — cadastro (username + e-mail + senha), status da conta, botão de download do app.

**Por que não tudo na nuvem:** CapCut não tem API pública; a automação só existe rodando na máquina do usuário. Uma tentativa anterior (`Claude outputs/ARCHITECTURE.md`, backend FastAPI + Docker) exigia o usuário exportar manualmente MP3 + `draft_content.json` e reimportar na mão — descartada por ser o oposto de "importa e sai pronto".

**Por que sem IA na headline:** já foi tentado (`cortesapp/headline.py`, Claude API) e funcionava, mas gera custo por vídeo processado. Decisão atual: fica manual. O código continua disponível caso vire feature paga no futuro — não apagar, só desativar do fluxo padrão.

## Reaproveitamento do CortesApp

Código-fonte de referência em `CortesApp/cortesapp/` (motor já testado e validado contra edições reais — ver `LEIA-ME.md` e `MUDANCAS.md` desse projeto para histórico).

| Arquivo | Reaproveitar como está | Mudança necessária |
|---|---|---|
| `audio.py` | Sim | — |
| `reels.py` | Sim (lógica de corte + zoom do modo "cortes + headline") | — |
| `capcut.py` | Sim (acha pasta do CapCut, lê/grava projeto, registra em `root_meta_info.json`) | Confirmar/completar a criação de projeto **novo do zero** a partir de vídeo bruto (v2 já tinha começado isso) |
| `transcricao.py` | Sim (Whisper offline) | — |
| `headline.py` | Não usar no fluxo padrão | Deixar desativado; não remover o arquivo |
| `servidor.py` | Parcial | Novos endpoints: login (Supabase), upload de vídeo cru, tela de revisão (transcrição + headline manual + cortes extra) |
| `assets/index.html` | Parcial | Redesenhar fluxo: login → importar vídeo → revisão → processar |
| `cortesapp.spec` | Sim | Ajustar nome/ícone para Clipay.ia |

O algoritmo de corte/zoom em si (detecção de silêncio, régua de timing, padrão de zoom) é o mesmo do `cortes_headline.py` da skill `cortes-headline` — não reinventar essa lógica, ela já foi calibrada e conferida contra edições reais (ver seção 3 e 4 daquele documento se precisar entender o raciocínio por trás dos números).

## Fluxo do usuário (MVP)

1. Cadastro no site: username, e-mail, senha (Supabase Auth).
2. Download do executável único na área logada.
3. Abre o `.exe` → aviso do SmartScreen (aceito, sem assinatura de código no MVP) → abre no navegador em `localhost`.
4. Login no app (mesma conta) → valida `subscriptions.status = 'ativo'` no Supabase.
5. Importa vídeo bruto (drag-and-drop).
6. Processamento automático: transcrição → silêncio/corte → zoom.
7. Tela de revisão: mostra transcrição; usuário escreve/ajusta headline e marca cortes de conteúdo extra opcionais; lado do zoom sugerido por detecção facial simples (OpenCV local), corrigível com um clique.
8. Gera projeto novo do CapCut, abre o CapCut.
9. Registra 1 linha em `processamentos` (sem enviar vídeo nenhum).

## Dados (Supabase)

Ver `supabase/migrations/0001_init.sql`. Resumo:

- `profiles (id, username, created_at)` — 1:1 com `auth.users`, criado via trigger no cadastro.
- `subscriptions (id, user_id, status, created_at, updated_at)` — `status` é `'ativo'` ou `'inativo'`; **sem** cobrança automatizada no MVP, ativação manual. Usuário só tem policy de `select`, nunca de `insert`/`update` — evita autoativação.
- `processamentos (id, user_id, created_at)` — contador de uso, sem vídeo.
- RLS ligado em tudo; toda policy usa `(select auth.uid())` (não `auth.uid()` puro) por performance.

Chave anon do Supabase fica embutida no app local (protegida por RLS). Chave `service_role` nunca vai para o cliente — só usada manualmente (SQL editor) ou num futuro painel admin.

## Riscos conhecidos (não ignorar)

- **CapCut pode criptografar o `draft_content.json`** em algumas versões — já documentado como o maior risco do produto original. Detectar esse caso e avisar claramente ao usuário; nunca falhar silenciosamente ou corromper o projeto.
- **Formato do draft do CapCut não é documentado oficialmente** e pode mudar em atualizações. Escrever sempre em pasta de projeto NOVA — nunca sobrescrever uma pasta que o CapCut já tenha aberto (autosave corrompe).
- **SmartScreen do Windows** vai avisar "publicador desconhecido" no MVP (sem assinatura de código) — é esperado, não é bug.

## Convenções de código

Seguir o estilo já usado no motor existente (`cortes_headline.py`, `audio.py` etc.): Python direto e compacto, nomes e comentários em português, preferência por funções puras sobre classes, sem abstração desnecessária. Não introduzir framework pesado onde um script direto resolve.

## Escopo do MVP — não expandir sem decisão explícita

**Dentro:** Windows apenas · modo "cortes + headline" apenas (sem vlog-youtube) · cadastro simples · conta ativa/inativo manual · executável único sem instalador · transcrição local · headline/cortes manuais na tela · detecção automática (corrigível) do lado do rosto.

**Fora por enquanto:** Mac · modo vlog-youtube · cobrança automatizada · geração de headline via IA · sincronização de configs entre dispositivos · auto-updater.

## Próximos passos técnicos

0. Renomear a pasta/repositório e o pacote `cortesapp/` para o nome definitivo Clipay.ia (ver nota acima) antes de mexer no resto.
1. Confirmar/completar a criação de projeto CapCut do zero a partir de vídeo bruto em `capcut.py`.
2. Rodar `supabase/migrations/0001_init.sql` no projeto Supabase.
3. Adaptar `servidor.py` + `assets/index.html` para login, upload de vídeo cru e tela de revisão.
4. Remover `headline.py`/Claude API do fluxo padrão (manter arquivo, só não chamar).
5. Testar detecção de `draft_content.json` criptografado em pelo menos 2 versões do CapCut.
6. Gerar o `.exe` com `cortesapp.spec` (renomeado) e testar "baixa, abre, usa" numa máquina limpa (sem Python instalado).
7. Painel web simples (cadastro, status da conta, download do app).