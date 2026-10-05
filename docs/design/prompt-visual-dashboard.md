Quero renovar o visual do Clipay.ia, começando pela barra lateral e pelo Dashboard. A referência visual está pronta em `docs/design/dashboard-novo-visual.html` (abra no navegador e use como alvo). O logo já recortado está em `docs/design/logo-clipay-mark.png`.

Esta rodada mexe só em visual: **não mudar lógica, endpoints, dados nem textos de função**. Os números, a lista de projetos e o gráfico continuam vindo dos mesmos lugares de hoje.

Observação: o `cortesapp/assets/index.html` que está no repositório é uma versão antiga (CortesApp v2, laranja, sem barra lateral). O Dashboard atual do Clipay.ia (verde, com barra lateral) está em outro arquivo ou build. Ache onde ele realmente mora antes de editar e me diga qual é.

## O que eu quero

1. **Logo.** No topo da barra lateral, mostrar só o logo (`logo-clipay-mark.png`, ~50 px de largura, alinhado à esquerda com os itens do menu). Tirar o texto "Clipay.ia" e o círculo verde. `alt="Clipay.ia"`. Quando a barra lateral ficar estreita (janela menor que 1100 px), centralizar o logo em ~42 px.

2. **Bloco da conta, mais organizado.** Hoje o rodapé mistura rótulo "Conta", avatar, nome, status e menu de três pontos. Trocar por um único cartão compacto:
   - Avatar redondo com a inicial (degradê lime), nome do usuário numa linha (com reticências se for longo) e, embaixo, uma linha pequena com bolinha verde + "Conta ativa" (ou "Plano X · ativo", ver observação abaixo).
   - Ao clicar, abre um menu acima do cartão: cabeçalho com nome e status, "Minha conta", "Plano e cobrança", uma linha divisória e "Sair". Fecha com clique fora e com Esc. Acessível por teclado (`aria-haspopup`, `aria-expanded`, foco visível).
   - Só mostrar o nome do plano (Basic, Ascendy, Premium) se o app já tiver esse dado. Não inventar plano. Se não tiver, mostrar "Conta ativa".

3. **Fonte: Inter, no estilo Apple.** Nada de CDN: o app é portable e precisa funcionar offline.
   - Baixar o Inter variável (arquivo `InterVariable.woff2` do release oficial rsms/inter, licença OFL, tem eixo de peso e de tamanho óptico) e colocar em `cortesapp/assets/fonts/`.
   - Declarar com `@font-face` (`font-weight: 100 900`, `font-display: swap`), e incluir a pasta no empacotamento do executável (`cortesapp.spec`) e garantir que o servidor local serve `.woff2` com o tipo `font/woff2`.
   - Pilha: `"Inter", -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif`. Ativar `font-optical-sizing: auto` e `font-feature-settings: "cv11","ss03"`.
   - Não usar SF Pro como fonte embutida (a licença só permite em plataformas Apple).
   - Números sempre com `font-variant-numeric: tabular-nums`.

4. **Estilo geral.** Menos borda, mais tipografia e espaço. Apple, sem enfeite.
   - Fundo `#0a0a0b`; cartões `#131315` com borda de 1 px `rgba(255,255,255,.08)` e raio 22 px; barra lateral flutuante com raio 24 px e degradê bem sutil.
   - Texto: `#f5f5f7`, secundário `#a1a1a6`, terciário `#8e8e93` (nunca mais escuro que isso: contraste mínimo 4,5:1 em texto pequeno).
   - Cor de destaque única: lime do logo, `#b3f706` (claro `#d7fd22`), texto sobre ela `#0d1103`. Verde de status (`#30d158`) separado do destaque.
   - Escala de tipo: título da página 34 px/600, tracking -0.03em; valores grandes 44 px/600, tracking -0.04em; título de cartão 17 px/600; rótulos 13 px/500; notas 12,5 px.
   - Item ativo do menu: fundo `rgba(255,255,255,.09)` e ícone lime. Hover: `rgba(255,255,255,.05)`.
   - Botão "Nova edição": pílula lime, 42 px de altura, ícone de mais, leve brilho lime embaixo.
   - Animação só de barras do gráfico crescendo ao abrir (0,8 s), e transições de 160 ms nos hovers. Respeitar `prefers-reduced-motion`. Foco visível em tudo (`outline` 2 px lime).
   - Definir tudo como variáveis CSS num arquivo de tokens único, pra as outras telas herdarem depois.

5. **Dashboard (mesmo conteúdo de hoje, melhor apresentado).**
   - Título: saudação ("Bom dia / Boa tarde / Boa noite" pela hora local, com o nome do usuário se o app tiver o nome; se não tiver, sem nome) e, abaixo, uma frase de valor: "Você já tirou **8 min 50 s** de silêncio dos seus vídeos." (usa o mesmo dado do cartão "Silêncio removido").
   - Os três cartões continuam, com o primeiro em destaque (degradê lime suave e borda lime). Em "Silêncio removido", mostrar as unidades menores e mais claras ("8 min 50 s").
   - Gráfico: semanas sem dado viram um traço pequeno e discreto em vez de barra zerada; a semana atual em degradê lime com o valor em cima. Só 3 linhas de grade (0, metade, máximo), rótulos de 12 px.
   - Últimos projetos: manter a lista e acrescentar, à direita de cada linha, o tempo economizado (duração antes menos depois) numa pílula lime, ex.: `−0:50`. Link "Ver todos" no topo do cartão. A altura dos dois cartões de baixo ocupa o espaço que sobra da tela (sem faixa vazia embaixo).
   - Manter a etiqueta "Exemplo" no cartão de visualizações (esse dado ainda não é real).

6. **Responsivo.** Até 1100 px a barra lateral vira só ícones (76 px) e o cartão da conta vira só o avatar. Até 720 px a barra vira uma faixa no topo e tudo empilha em uma coluna. Nada de rolagem horizontal.

## Como verificar

- Rodar o app e tirar capturas em 1440×900, 1000×800 e 700×800. Comparar com `dashboard-novo-visual.html` aberto em tamanhos iguais e me mostrar lado a lado.
- Conferir que o executável portable mostra a fonte Inter sem internet (desligar a rede e abrir).
- Navegar só pelo teclado: Tab chega ao menu da conta, Enter abre, setas/Tab percorrem, Esc fecha.
- Conferir os contrastes dos textos pequenos (mínimo 4,5:1).
- Garantir que nenhum dado nem endpoint mudou (os números do Dashboard continuam iguais aos de antes).

## Não fazer agora

- Não redesenhar as telas de Edição, Tutorial e login nesta rodada. Elas herdam os tokens depois, numa rodada separada.
- Não adicionar funções novas (cartões de modos de edição, créditos, notificações) sem eu pedir.
