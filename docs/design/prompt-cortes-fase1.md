Vamos começar a seção **Cortes** do Clipay.ia, a parte mais importante do produto (plano Basic). No fim, a pessoa vai enviar um podcast de 1 a 3 horas, escolher os tipos de corte, e o app vai gerar todos os cortes completos já editados, cada um em um projeto do CapCut. **Hoje é só a Fase 1: o montador de um corte, sem IA.** As outras fases virão em outros prompts, então não construa transcrição longa, IA nem a tela agora.

Leia antes de mexer, nesta ordem: `docs/design/cortes-especificacao.md` (a especificação, com todos os números medidos) e a pasta `docs/design/referencia-cortes/` (o projeto de CapCut que eu montei à mão, "cortes ale pod cast", mais dois quadros). O arquivo `docs/design/prompt-cortes.md` tem o plano completo das 4 fases, só para você saber para onde isso vai. Depois me diga o plano em poucas linhas e espere eu dizer "pode seguir".

## A regra que não pode quebrar (vale para as próximas fases)

O corte é um **assunto inteiro**: começa onde o assunto começa e só termina quando ele muda. Nunca truncar por duração. Aqui, na Fase 1, o início e o fim chegam digitados por mim; a IA que os acha vem depois.

## O que fazer

Dado um vídeo e um intervalo (início e fim, digitados), gerar no CapCut **o mesmo projeto que eu fiz à mão** em `referencia-cortes/`. É aqui que eu valido a edição antes de gastar com qualquer IA.

- Crie o módulo `cortesapp/cortes.py` (montagem) e `cortesapp/assets/cortes/modelos/basico.json`, com todos os parâmetros da seção 4 da especificação (canvas, escala base, fator e intervalo de zoom, velocidade, volume da música, efeito, headline), em vez de números espalhados no código.
- **Use `referencia-cortes/` como template**, do jeito que `carrega_tpl` usa `headline_tpl.json`: copie `draft_content.json`, a pasta `subdraft/` e o `draft_meta_info.json` para `cortesapp/assets/cortes/template/`, e troque só o que varia (pedaços e tempos, caminho do vídeo, música, ids novos para tudo, nome, durações). Não escreva o clipe composto do zero.
- O rascunho interno do composto existe em dois lugares (dentro de `materials.drafts[0].draft` e em `subdraft/<id>/draft_content.json`) e eles têm que sair **idênticos**. Registre o composto no `draft_meta_info.json` como a especificação descreve. É o ponto que costuma gerar "Mídia perdida".
- Cortes secos dentro do corte: reaproveite `reels.regua` e `reels.divide_longos` sobre o áudio **só do intervalo** (não do vídeo todo). Pedaços colados no tempo.
- Zoom: reaproveite `plano_zoom` e as tabelas `ESTATICO` e `EMPURRAO`, aplicando os fatores sobre a escala base (1,823 para um original 16:9 em canvas 1:1; calcule a partir da proporção do arquivo, não fixe). Centrar na pessoa pela detecção que já definimos (posição horizontal contínua), agora **também vertical**, limitando com as fórmulas da seção 4 (`|x| ≤ s−1` e `|y| ≤ 0,5625·s−1` para 16:9). Antes de usar as fórmulas, **confirme sinal e unidades** com o projeto de referência: o empurrão do primeiro pedaço termina em `y = −0,2156` com `s = 2,161`, que é exatamente o limite. Se a sua conta não bater, pare e me diga.
- Camada externa: velocidade 1,13x, posição y −0,128, efeito "Estroboscópio de tremor" com os parâmetros da especificação (se o efeito não estiver no cache do CapCut desta máquina, grave só o id, como já fazemos com o filtro da Rotina).
- Headline pelo modelo que já existe (`reels.headline`), **sempre com o texto de exemplo da referência** (`SUA HEADLINE AQUI` / `SOBRE O SEU CORTE`): eu troco depois no CapCut e o app não gera nem pede headline nos cortes. **Compare** escala e posição dele com 0,634 e (0, 0,511) e use os números da referência se forem diferentes.
- **Não mexa no volume da fala.** A amostra tinha +10 dB, mas foi só um teste meu: o composto sai com volume 1,0.
- Música: um MP3 meu, volume 0,053, do começo ao fim do corte, sem fade.
- O vídeo original **não é copiado**: os pedaços apontam para o arquivo com `source_timerange`.

## Arquivos para o teste

- Vídeo original (70 min, 4 GB, **não copie**): `C:\Users\danil\Downloads\Qual foi o momento - Ale EP6.mp4`. Extraia você um trecho de uns 10 minutos, começando por volta de 14:00, com o ffmpeg do app, e salve em `tests/fixtures/`.
- Música: `C:\Users\danil\Downloads\gravitational forces.MP3`.

## Como verificar

Reproduza o corte da referência (de 900,5 s a 943,4 s do vídeo original; no trecho de teste, use o intervalo equivalente) e compare com o projeto de referência: número de pedaços parecido, pedaços colados, velocidade, escala e posição dentro dos limites, headline de exemplo, música, efeito. Rode a verificação do projeto que já existe. Depois **abra no CapCut** e me diga o que viu: sem "Mídia perdida", com som no corte (o cache `Resources/combination/..._audio.aac` do projeto de referência é gerado pelo CapCut; veja se o seu projeto toca o áudio sem ele), com a imagem enquadrada. Se vier mudo, resolva isso antes de qualquer outra coisa. Me mostre os quadros do resultado ao lado dos da referência.

## Não fazer agora

- Não faça transcrição de vídeo longo, IA, Edge Function nem a tela Cortes: são as fases seguintes.
- Não mexa na Edição, no Dashboard nem na barra lateral.
- Não mude o que já funciona nos outros modos; rode os testes que já existem.
- Pare no fim da Fase 1 e espere eu validar no CapCut.
