# Legenda Complexa — Especificação técnica

Regras extraídas e calibradas nas edições reais feitas manualmente antes do Clipay.ia existir, adaptadas aqui pra um produto multi-usuário (removendo o que era específico da máquina/marca pessoal do Danillo).

## Corte por palavra (adaptar a régua já usada no motor de cortes+headline)

- Juntar todas as palavras (de todos os blocos de transcrição) numa lista única, ordenada por tempo.
- Cortar onde o intervalo entre palavras ultrapassa `CORTE_MIN = 250_000` µs (250ms).
- Padding assimétrico dependendo da duração do trecho de fala:
  - trecho ≤ 800ms (palavra curta isolada): `PAD_PRE = 150_000`, `PAD_POST = 200_000` µs
  - trecho > 800ms (frase): `PAD_PRE = 60_000`, `PAD_POST = 60_000` µs
- Remover gaguejada: palavra repetida colada com gap < 400ms (mantém a segunda ocorrência).
- Remover muleta: palavra isolada entre dois silêncios que seja uma destas: "é", "tá", "e", "né", "ó", "tipo".
- **Corte por palavra, nunca por bloco de legenda inteiro.** Cortar por bloco desalinha o tempo da legenda quando dois blocos se encostam: o timestamp da legenda fica negativo e ela renderiza sobreposta à anterior. Esse bug já foi visto (34 casos) e só aparece agrupando segmentos de texto por altura Y — não pela checagem normal por trilha.

## Marcadores de ênfase (o usuário escreve isso direto no texto da legenda)

| marcador | efeito |
|---|---|
| `[palavra]` | ênfase forte ("soco"), a mais usada |
| `*palavra*` | ênfase leve |
| `palavra?` | pergunta retórica |
| edição manual da palavra (ex. `por**grafia`) | censura |

## Texto condensado — decisão manual, sem IA

O app **não** tenta reescrever/condensar a transcrição sozinho. Mostra a transcrição bruta já cortada numa caixa de texto editável; o usuário edita à vontade (apaga palavras, adiciona os marcadores acima, corrige erro de transcrição) — tudo no mesmo lugar, no mesmo texto que vira a legenda final. Primeira palavra da legenda entra com maiúscula.

## Corte da abertura (gancho) — decisão manual

Mostrar a transcrição com marcação de tempo; usuário clica na palavra onde o vídeo deve realmente começar (equivalente a um parâmetro `--inicio`). Não tentar adivinhar automaticamente onde está o gancho.

## Legenda acumulada — posicionamento

```
X_LINHA   = -0.58        # canto superior esquerdo
DEGRAU    = 0.050        # cada linha entra mais pra direita
Y0        = 0.38         # linhas em 0.38 / 0.265 / 0.15
ALT_LINHA = 0.115
LARG_LINHA = 0.55
MAX_PAL_LINHA = 2
MARGEM = 0.04
ESC_BASE = 0.45273892468443844
```

- Máximo 2 linhas "normais" acumulando palavra por palavra; a palavra em ênfase ganha linha própria (máx. 3 linhas no total).
- **Um estilo de texto por linha.** Nunca posicionar palavra por palavra manualmente — a largura real do texto na fonte não bate com a estimativa e as palavras colam (`pra`**`mostrar`**`que`). Cada linha é um objeto de texto único; o espaçamento interno é o próprio CapCut que resolve.
- Clamp de margem: `x = max(x, -1.0 + meia_largura * 1.3 + MARGEM)`.
- Cada linha cresce palavra a palavra: o "estado" i vale do início da palavra i até o início da palavra i+1; o último estado permanece até o fim do grupo.
- O grupo de legenda anterior só sai da tela depois que o próximo grupo começa.

## Ênfase — escala por largura, nunca fixa

```
LARG_ALVO_ENFASE = 0.45   # unidades de tela; tela inteira = 2.0
escala = LARG_ALVO_ENFASE * ESC_BASE / (largura_do_texto_na_fonte * 0.000705)
# na prática cai entre ~0.49 e ~0.95
```

- **Nunca** deixar a ênfase num tamanho fixo — sempre calcular pela largura real do texto renderizado na fonte usada.
- Estouro gigante (escala 1.17–1.33) só quando o enquadramento está aberto (zoom desligado ou fraco) — com zoom apertado a palavra grande tampa o rosto da pessoa. Regra: zoom desligado → pode estouro grande; zoom ligado → limitar a 0.5–0.95.
- Posição da ênfase: livre, `y` entre 0.06 e 0.29, `x` entre -0.58 e -0.41, abaixo das linhas normais. Duas ênfases podem coexistir na tela em alturas diferentes.

## Fontes

- Preferir fontes do catálogo de efeitos do próprio CapCut (baixam sozinhas quando referenciadas por ID de recurso — é assim que a fonte "Classic" do modo cortes+headline já funciona). Isso evita depender de fonte instalada manualmente no Windows do cliente.
- As fontes usadas na régua original de referência (CreatoDisplay Black/Bold/BoldItalic, Coolvetica) **não** são do catálogo do CapCut — são arquivos instalados manualmente numa máquina específica. Pra funcionar em qualquer instalação do Clipay.ia: **empacotar essas fontes junto com o instalador** e registrá-las (ou usar equivalentes do catálogo do CapCut). Decisão tomada agora: se uma fonte não puder ser aplicada, avisar claramente na tela — nunca falhar silenciosamente ou trocar por outra sem avisar.
- Estilo base do texto: `border_width 0.08`, `has_shadow false`, `alignment 1`, `line_spacing 0.02`, `letter_spacing 0`, `font_size 15`.

## Zoom — decisão manual, sem IA

- Toggle "Aplicar zoom" + slider de intensidade (escala 1.0 a ~1.47), desligado por padrão. O usuário decide olhando a prévia do vídeo — o app não tenta adivinhar pela imagem.
- Quando ligado: embrulhar **todos** os cortes de vídeo num clipe composto único e aplicar o zoom no segmento desse composto (não corte a corte) — assim o controle fica num lugar só, fácil de ajustar depois.

## Música de fundo

- Usuário sobe o próprio arquivo de áudio (sem biblioteca embutida no MVP desta função).
- Volume: slider ajustável (não fixo) — sugerir um valor baixo por padrão, que não compita com a fala.

## Acabamento

- Embrulhar cortes de vídeo + bloco de legenda num clipe composto único.
- Velocidade final: 1.15x por padrão, ajustável.
- Fade-in no início do corpo do vídeo.
- Sem marca d'água nesta função por enquanto (decisão tomada agora — pode virar configuração por usuário numa v2).

## Estrutura de clipe composto aninhado no CapCut — MAIOR RISCO TÉCNICO desta função

Essa técnica já foi usada e funciona, mas é frágil — testar exaustivamente antes de liberar:

1. Um composto é um draft aninhado completo: tem sua própria estrutura com `tracks` e `canvas_config` (1920x1080).
2. **Toda** entrada em `materials.drafts` — inclusive as de compostos aninhados dentro de outros compostos — precisa morar no `materials` da **RAIZ** do projeto (lista plana), nunca no `materials.drafts` do composto pai. **Bug já documentado**: se a entrada ficar no lugar errado, o CapCut mostra "Mídia perdida / Media Not Found" na faixa.
3. O composto pai só guarda um placeholder em `materials.videos` (`path` vazio, `extra_type_option: 2`) e o segmento que aponta pro id da raiz.
4. O caminho de pasta usa um token literal de macro (`##_draftpath_placeholder_<uuid>_##\subdraft\<FOLDER_ID>\...`) — não é um id de projeto, é um placeholder que o próprio CapCut resolve.
5. Cada composto tem sua própria pasta em disco (`subdraft/<FOLDER_ID>/`) com `draft_content.json`, `sub_draft_config.json` e `draft_cover.jpg` próprios.
6. Ordem dos `extra_material_refs` do segmento importa: `[drafts, speeds, placeholder_infos, video_effects, canvases, sound_channel_mappings, material_colors, vocal_separations]`.

## Verificação obrigatória antes de gravar (travar e avisar em vez de gravar projeto quebrado)

1. **Sobreposição por altura Y**: agrupar segmentos de texto por `transform.y` e garantir que duas legendas nunca ocupam a mesma "linha" na tela ao mesmo tempo. A checagem normal por trilha **não** detecta isso.
2. Toda faixa de estilo de texto cobre o texto inteiro (nenhum `range` fora do tamanho do texto).
3. Toda referência (`material_id`, `extra_material_refs`) resolve pra algo que existe.
4. Nenhum segmento passa da duração do projeto; nenhuma trilha com sobreposição de tempo.
5. Nenhuma linha de texto vazando da tela (fator de segurança de 1.3 na largura).
6. Todo composto aninhado tem entrada correspondente na raiz e pasta correspondente em `subdraft/`.

---

## Notas de implementação (Clipay.ia, 2026-09-29)

Decisões e descobertas feitas ao implementar (código: `app/clipay/legenda.py`, `palavras.py`, `composto.py`):

- **Unidade do `0.000705`**: `largura_do_texto_na_fonte` = `ImageFont.getlength` em **Liberation Sans Regular tamanho 100** (métrica idêntica à Arial). Confirmado contra as 13 escalas reais do João 1/2: mediana do tamanho implícito = 100,4. O app leva só a tabela de larguras (`assets/larguras_arial.json`), não a fonte.
- **Marcadores ficam visíveis na tela** (`[droga]`, `*culpado*`), igual às edições aprovadas. Soco em vermelho `[1,0,0]`.
- **Fontes (catálogo do CapCut, só ids já vistos em projetos reais)**: normal PublicSans Regular `7242301789909815863`; soco Kanit Black `7341281166273548801`; leve e pergunta PublicSans Italic `7152810955380888065`. Ids curtos do cache (ex. Montserrat Black `155387730`) nunca apareceram como `font_resource_id` em projeto real — não usados.
- **Estrutura** copiada do "João 2 - legendado" (`ferramentas/captura_moldes_legenda.py` → `assets/moldes/legenda.json`): RAIZ → Corpo (1.15x, Fade-in `6798320778182922760`) → {Cortes (zoom no segmento), Legenda (sobreposição, `flag 2`)}. Id do draft aninhado = nome da pasta `subdraft/`. O `draft_content.json` da pasta é um stub (canvas 0x0) cujo `materials.drafts[0]` é a própria entrada da raiz com caminhos absolutos.
- **Canvas dos compostos**: 1920x1080 em todas as edições reais (inclusive raiz vertical). No Clipay.ia os compostos seguem a orientação do vídeo — a validar no CapCut com vídeo vertical.
- `Resources/combination/*_video.mp4` é cache que o CapCut renderiza; não precisa existir (o "LOFI NAO - legendas v3" funciona sem).
- **Tempo por palavra**: o Whisper local não dá tempo de palavra. Os cortes vêm do áudio (trechos de fala separados por ≥250 ms — exato); o instante de cada palavra dentro de um trecho é distribuído pelo tamanho da palavra (aproximado).
