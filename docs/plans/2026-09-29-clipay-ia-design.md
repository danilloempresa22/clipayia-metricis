# Clipay.ia — Design do MVP

**Data:** 29/09/2026
**Status:** Design validado, pronto para implementação

## 1. Visão do produto

Clipay.ia é um microSaaS que automatiza o fluxo de edição "cortes + headline" (hoje feito manualmente por Danillo no CapCut, ou via skill do Claude) para qualquer criador de conteúdo ou editor de vídeo. O usuário importa um vídeo bruto, e o produto entrega um projeto novo do CapCut já cortado (corte seco sem respiração, zoom punch-in) e pronto pra revisão da headline — sem precisar saber nada de automação, script ou CapCut avançado.

**Não é este projeto:** não substitui o CortesApp (app avulso vendido separadamente) — é um produto novo e paralelo, construído reaproveitando o motor de edição já validado do CortesApp, mas com conta de usuário, login e uma esteira de venda como SaaS de verdade.

## 2. Por que essa arquitetura

CapCut roda localmente na máquina de cada usuário e não tem API pública. Isso significa que a automação (abrir o CapCut, criar o projeto lá) só é tecnicamente possível com algo rodando na máquina do cliente — não existe jeito de um servidor remoto fazer isso sozinho.

Duas arquiteturas alternativas já foram tentadas e descartadas (ver pasta `capcut-kit-main/Claude outputs`):
- **Backend FastAPI + Docker na nuvem**, onde o usuário precisava exportar manualmente o MP3 e o `draft_content.json` do CapCut, subir num site, e reimportar o resultado na mão. Funcionava, mas é o oposto de "importa e já sai pronto" — muita fricção manual.
- **Geração de headline via Claude API** (`headline.py` do CortesApp v2): funcionava, mas gera custo de API por vídeo processado, o que não é desejado agora.

A arquitetura escolhida evita as duas coisas.

## 3. Arquitetura de alto nível

**App local (o motor) — executável único, sem instalador**
Um único arquivo `.exe` (Windows, MVP), sem instalador, sem assinatura de código, sem PowerShell. Usuário baixa, dá duplo-clique, e o app abre no navegador padrão em `localhost` (servidor local Flask/FastAPI, como o `servidor.py` do CortesApp já faz). É ele que faz todo o trabalho pesado: lê o áudio direto do vídeo (sem precisar exportar nada), transcreve com Whisper offline, detecta silêncio/respiração, corta, aplica zoom, e escreve o projeto novo direto na pasta do CapCut.

Trade-off aceito: sem assinatura de código, Windows mostra o aviso "O Windows protegeu o seu computador" (SmartScreen) na primeira execução — resolve com um clique ("Mais informações" → "Executar assim mesmo"). Evita o custo de um certificado de assinatura de código no MVP; a página de download explica o aviso.

**Backend (Supabase) — só a camada de "empresa"**
Cuida de cadastro, login e status da conta. Não processa vídeo, não armazena vídeo, não participa da automação do CapCut.

**Painel web**
Landing page + cadastro + área logada simples (status da conta + botão de download do app).

Os dois se conectam por login: o app local pede login (mesma conta do site) na primeira abertura, valida contra o Supabase se a conta está ativa, e libera ou bloqueia o processamento.

## 4. Reaproveitamento do CortesApp

O motor de edição já existe e está testado (pasta `capcut-kit-main/CortesApp/cortesapp/`), batendo com as edições aprovadas de Danillo (ex.: "Advisor Ale 1 - corte v2": 49,3 → 42,9 min, 902 pedaços; casos de reels com números idênticos aos das edições entregues). Reaproveitar como base do Clipay.ia:

| Arquivo | Função | O que muda para o Clipay.ia |
|---|---|---|
| `audio.py` | Lê áudio direto do vídeo via ffmpeg, analisa voz/silêncio | Nenhuma mudança |
| `reels.py` | Modo "cortes + headline": corte seco + zoom punch-in + headline | Nenhuma mudança na lógica de corte/zoom |
| `capcut.py` | Acha a pasta do CapCut (Win/Mac), lê/grava projeto, registra no `root_meta_info.json` | Nenhuma mudança |
| `transcricao.py` | Whisper offline (onnxruntime) | Nenhuma mudança |
| `headline.py` | Gerava headline via Claude API | **Removido** — headline vira decisão manual do usuário na tela (ver seção 6) |
| `servidor.py` | Servidor local + endpoints | Adaptar endpoints para o novo fluxo (login, upload direto de vídeo cru) |
| `assets/index.html` | Tela do app | Redesenhar: tela de login + fluxo de importar vídeo → revisar transcrição/headline → processar |
| `cortesapp.spec` | Receita do PyInstaller | Reaproveitar, ajustando nome/ícone do Clipay.ia |

Diferença de escopo em relação à skill/CortesApp atual: hoje o motor edita um projeto que **já existe** no CapCut. O Clipay.ia precisa **criar um projeto novo do zero** a partir do vídeo bruto importado (o CortesApp v2 já tinha começado isso — "cria draft CapCut minimalista automaticamente" — vale conferir o estado dessa parte e completá-la se necessário).

## 5. Fluxo do usuário

1. **Cadastro no site:** username, e-mail (gmail) e senha → Supabase Auth.
2. **Download:** botão "Baixar o app" na área logada → baixa o `.exe` único.
3. **Abertura:** duplo-clique → aviso do Windows (explicado na página) → abre no navegador em `localhost`.
4. **Login no app:** mesma conta do site; app valida com o Supabase se a conta está ativa.
5. **Importar vídeo:** arrasta o arquivo bruto pro app.
6. **Processamento automático (sem intervenção):** transcrição (Whisper local) → detecção de silêncio/respiração → corte seco → zoom punch-in nos pontos certos, seguindo a régua já validada.
7. **Tela de revisão:** o app mostra a transcrição. Usuário escreve/ajusta a headline e, se quiser, marca trechos extras de conteúdo pra remover (repetição, desvio de assunto). O app sugere automaticamente o lado do zoom (esquerda/centro/direita) via detecção facial simples (OpenCV, local, gratuita), com opção de corrigir num clique.
8. **Montagem final:** gera o projeto novo do CapCut na pasta correta.
9. **Abre o CapCut** já com o projeto carregado.

## 6. Por que sem IA para headline/cortes de conteúdo

A parte de "julgamento" (escrever a headline como promessa/afirmação forte, decidir o que cortar por sentido) hoje é feita por leitura humana (ou por Claude, quando Danillo pede a edição). Replicar isso automaticamente exigiria uma chamada de IA por vídeo — já tentado no CortesApp v2 (`headline.py` com Claude API) — o que gera custo recorrente por uso.

Decisão: por enquanto, essa etapa fica manual — o app mostra a transcrição e o usuário decide. Zero custo de IA, mecanismo mais simples, e o código do `headline.py` fica disponível caso decida reativar essa opção no futuro (ex.: como recurso premium).

## 7. Dados no Supabase (MVP)

- **Auth:** e-mail/senha (username salvo como campo de perfil).
- **Tabela `profiles`:** `user_id`, `username`, `criado_em`.
- **Tabela `subscriptions`:** `user_id`, `status` (`ativo` / `inativo`) — sem tiers ou cobrança automática por enquanto; ativação/desativação manual até definir modelo de cobrança.
- **Tabela `processamentos`** (opcional, leve): `user_id`, `timestamp` — só contagem de uso, nenhum vídeo é enviado à nuvem.
- Row Level Security: cada usuário só enxerga seus próprios dados.

## 8. Riscos conhecidos

- **CapCut criptografando `draft_content.json` em versões mais novas** — já documentado como "o maior risco do produto" na experiência do CortesApp. O app precisa detectar essa situação e avisar claramente ao usuário, em vez de falhar silenciosamente. Vale testar com um grupo pequeno de usuários em versões diferentes do CapCut antes de abrir para todos.
- **Aviso do SmartScreen do Windows** — sem assinatura de código, todo usuário verá o aviso na primeira execução. Mitigar com instruções claras na página de download; considerar comprar um certificado de assinatura de código se isso gerar muita desistência.
- **Formato do projeto do CapCut não é documentado oficialmente** — pode mudar em atualizações futuras do CapCut sem aviso, quebrando a automação. Vale deixar isso explícito nos termos de uso.

## 9. Tratamento de erros

- CapCut não encontrado na pasta padrão → pede pro usuário indicar a pasta manualmente (salva pra próxima vez).
- Vídeo sem fala detectável → avisa em vez de gerar corte quebrado.
- `draft_content.json` criptografado (CapCut não suportado) → mensagem clara, sem tentar editar.
- Conta inativa → bloqueia processamento, mostra link pra reativar no site.
- Projeto sempre criado em pasta NOVA — nunca sobrescreve uma que o CapCut já tenha aberto.
- Qualquer falha no meio do processamento → mensagem clara na tela, sem deixar pasta de projeto pela metade.

## 10. Testes

- Rodar o motor reaproveitado contra os vídeos de referência já validados manualmente (ex.: "0925 - corte"), comparando pedaços/zooms com o que foi feito à mão.
- Testar o fluxo completo (importar → transcrever → revisar → gerar projeto → abrir CapCut) em 3-5 vídeos variados (rosto esquerda/centro/direita, com e sem cortes de conteúdo extra).
- Testar login/conta ativa/inativa isoladamente do processamento.
- Testar em pelo menos duas versões diferentes do CapCut (por causa do risco de criptografia do draft).

## 11. Escopo do MVP (resumo)

**Dentro:**
- Windows apenas.
- Fluxo "cortes + headline" apenas (vlog-youtube fica para uma v2).
- Cadastro simples (username + gmail + senha) via Supabase.
- Conta ativa/inativa manual (sem cobrança automatizada ainda).
- App único executável, sem instalador.
- Transcrição local via Whisper (reaproveitado do CortesApp).
- Headline e cortes de conteúdo extra decididos manualmente pelo usuário na tela.
- Detecção automática (mas corrigível) do lado do rosto para o zoom.

**Fora (v2 ou depois):**
- Mac.
- Modo vlog-youtube.
- Cobrança automatizada (Stripe ou similar).
- Geração de headline/cortes via IA (código já existe em `headline.py`, pode ser reativado como recurso pago).
- Sincronização de configurações entre dispositivos.
- Auto-updater do app.

## 12. Próximos passos sugeridos

1. Confirmar em que estado está a criação de projeto CapCut "do zero" a partir de vídeo bruto no CortesApp v2 (parece iniciada, mas precisa validar se está completa).
2. Configurar o projeto Supabase (Auth + tabelas `profiles`/`subscriptions`).
3. Adaptar `servidor.py` e `assets/index.html` para o novo fluxo (login + upload de vídeo cru + tela de revisão de headline/transcrição).
4. Remover a dependência de `headline.py`/Claude API do fluxo padrão.
5. Testar a detecção de criptografia do `draft_content.json` em pelo menos duas versões do CapCut.
6. Gerar o executável único com PyInstaller (reaproveitando `cortesapp.spec`) e testar a experiência "baixa, abre, usa" do zero numa máquina limpa.
7. Construir o painel web simples (cadastro, status da conta, download).
