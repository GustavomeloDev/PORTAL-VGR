# DataTables — toolkit padrão do Portal (`PortalDt*`)

Toolkit neutro em `core` para padronizar:

1. **Toolbar** — Limpar Filtros / Atualizar / Colunas / Texto  
2. **Visual** — cabeçalho `#343a40` em cápsula, zebra, ColumnControl invisível, Select2 bootstrap-5  
3. **Contrato ColumnControl** — `searchList` (não `searchText`)

Alinhado ao PRODESP **sem** copiar classes `prodesp-*`.

**Consumidores atuais**

| Módulo | O que usa |
|--------|-----------|
| `login` | CSS + 4 JS no `base.html`; toolbar via `registrarAjusteColunasDataTable` / `loginAdminDtOpts` |
| PRODESP admin (Links / Equipamentos) | CSS + toolbar PortalDt; `AdminInv.ccSearchList` → `PortalDt` |
| PRODESP fila / dashboard | `portal_dt_defaults.js` no `base_prodesp.html`; `prodespDtCc*` / `prodespGestaoDt*` → `PortalDt` (toolbar ainda própria do módulo) |

---

## Assets e ordem de carga

| Arquivo | Global | Papel |
|---------|--------|--------|
| `portal_datatable.css` | — | Visual DT + Select2 bootstrap-5 + Ações |
| `portal_dt_font_size.js` | `PortalDtFontSize` | Tamanho do texto (`localStorage`: `portal_dt_font_size`) |
| `portal_dt_columns.js` | `PortalDtColumns` | Menu Colunas (`portal_dt_cols_v1_{tableId}`) |
| `portal_dt_toolbar.js` | `PortalDtToolbar` | Monta a barra e liga font/columns |
| `portal_dt_defaults.js` | `PortalDt` | `ccSearchList`, `ccOrderOnly`, `languagePtBr`, … |

**Ordem dos scripts** (após jQuery + DataTables + ColumnControl):

```html
<link rel="stylesheet" href="/core/static/css/datatable/portal_datatable.css?v=dt-visual-11">
…
<script src="…/columnControl.dataTables.js"></script>
<script src="/core/static/js/datatable/portal_dt_font_size.js?v=dt-visual-11"></script>
<script src="/core/static/js/datatable/portal_dt_columns.js?v=dt-visual-11"></script>
<script src="/core/static/js/datatable/portal_dt_toolbar.js?v=dt-visual-11"></script>
<script src="/core/static/js/datatable/portal_dt_defaults.js?v=dt-visual-11"></script>
<!-- scripts de página -->
```

- **Login:** tudo no `login/templates/base.html` (antes do `{% block scripts %}`).  
- **PRODESP:** `portal_dt_defaults.js` no `base_prodesp.html`; CSS + toolbar JS nas páginas admin (ou incluir o CSS no snippet comum quando migrar a fila).  
- Sempre alterar `?v=…` ao mudar CSS/JS (Waitress não faz cache-bust automático).

---

## API `PortalDt` (defaults ColumnControl)

```js
PortalDt.ccSearchList()                    // searchList + spacer + order* (ajaxOnly:false)
PortalDt.ccSearchList({ ajaxOnly: true }) // só opções de ajax.json().columnControl
PortalDt.ccOrderOnly()                     // só ordenação (tempos / sem checklist)
PortalDt.languagePtBr()                    // i18n pt-BR inline + textos do ColumnControl
PortalDt.languageColumnControl()           // só o bloco language.columnControl
PortalDt.orderingSilent()                  // { indicators: false, handler: false }
PortalDt.columnDefsSearchList([0, 1, 2]) // atalho columnDefs
PortalDt.columnDefsSearchList([0, 1], { orderable: false })
```

### Regras do contrato

1. Coluna filtrável → `searchList` (nunca `searchText`; sem `{ extend: "dropdown" }` aninhado).  
2. Client-side com dataset completo → `ajaxOnly: false` (opções no 1º draw; abertura imediata).  
3. JSON `columnControl` só se **completo** ou lista fixa; parcial + `ajaxOnly: true` esconde colunas sem chave.  
4. Ações → sem `columnControl` (ou `[]`). Tempos → `ccOrderOnly()`.  
5. Lista fixa de status (ex. fila): manter `options` no objeto `searchList` (não usar só o helper genérico).

Delegação nos módulos (com fallback local se o script do core não carregar):

- Login: `loginAdminDtOpts`  
- Admin inventário: `AdminInv.ccSearchList` / `dtLanguagePtBr`  
- Fila: `prodespDtCcSearchList` / `prodespDtCcOrderOnly` / `prodespAtendimentosDataTableLanguage`  
- Dashboard: `prodespGestaoDtCcSearchList` / `prodespGestaoDtLanguage`

---

## Exemplos de uso

### 1) HTML mínimo da tabela

```html
<div class="table-wrap">
  <table id="tblExemplo" class="table table-sm table-striped table-hover mb-0" style="width:100%">
    <thead>
      <tr>
        <th class="cc">ID</th>
        <th class="cc">Nome</th>
        <th class="no-filter col-acoes">Ações</th>
      </tr>
    </thead>
  </table>
</div>
```

- `id` estável — obrigatório para prefs de Colunas / toolbar.  
- `table-striped table-hover` — recomendado; o CSS do portal também aplica zebra.  
- `col-acoes` no `<th>`; célula de ações com classes `col-acoes portal-dt-acoes`.  
- Largura padrão da coluna Ações: **180px** (`--portal-dt-acoes-width`); sobrescreva no wrapper se precisar de mais/menos ícones.  
- Evitar `thead.table-dark` — o fundo escuro já vem do CSS do portal (permite cantos arredondados).

### 2) DataTable “do zero” (só core)

```js
const api = $("#tblExemplo").DataTable({
  language: PortalDt.languagePtBr(),
  ordering: PortalDt.orderingSilent(),
  columns: [
    { data: "id" },
    { data: "nome" },
    {
      data: "id",
      orderable: false,
      searchable: false,
      className: "col-acoes portal-dt-acoes",
      render: (id) =>
        `<span class="portal-dt-acoes-inner">
           <button type="button" class="btn-icon" title="Ver"><i class="fas fa-eye"></i></button>
         </span>`,
    },
  ],
  columnDefs: [
    { targets: [0, 1], columnControl: PortalDt.ccSearchList() },
    { targets: [-1], columnControl: [] },
  ],
});

PortalDtToolbar.mount(null, {
  api: api,
  onRefresh: function (dt) {
    dt.ajax.reload(null, false);
  },
});
```

`PortalDtToolbar.mount(hostElOrSelector, options)`:

| Opção | Uso |
|-------|-----|
| `api` | Instância DataTables (obrigatória na prática) |
| `onRefresh` | Callback do botão Atualizar (se houver ajax, o botão aparece mesmo sem callback) |
| `onClearExtra` | Extra após limpar filtros CC / search |
| `showRefresh` | Força mostrar/esconder a barra Atualizar |
| `columnsMeta` | Metadados opcionais do menu Colunas |

Host: passe `null` para inserir a toolbar automaticamente acima do wrapper da tabela.

### 3) Login — atalho admin

```js
const opts = loginAdminDtOpts([0, 1, 2, 3], {
  ajax: { url: "/login/api/…", dataSrc: "data" },
  columns: [ /* … */ ],
  loginDtToolbar: {
    onRefresh: function (api) {
      api.ajax.reload(null, false);
    },
  },
});
$("#tblSaudeDigests").DataTable(opts);
// loginAdminDtOpts já chama registrarAjusteColunasDataTable no initComplete
```

Ou, após criar a tabela manualmente:

```js
registrarAjusteColunasDataTable(api, {
  onRefresh: function () { carregarSegLoginEventos(); },
  onClearExtra: function () { /* limpar filtros externos */ },
});
```

### 4) PRODESP admin inventário

```js
columnDefs: [
  { targets: [0, 1, 2, /* … */], columnControl: AI.ccSearchList() },
  { targets: [-1], columnControl: [] },
],
language: AI.dtLanguagePtBr(),
initComplete: function () {
  AI.bindPortalDtColumnControl(this.api());
},
// Toolbar:
PortalDtToolbar.mount(null, { api: api, onRefresh: … });
```

### 5) PRODESP fila / dashboard (só contrato CC)

```js
columnDefs: [
  {
    targets: [0, 1, /* … colunas filtráveis */],
    columnControl: prodespDtCcSearchList(), // → PortalDt.ccSearchList()
  },
  {
    targets: PRODESP_DT_COL_TEMPO_ETAPA,
    columnControl: prodespDtCcOrderOnly(),
  },
  {
    targets: PRODESP_DT_COL_STATUS,
    columnControl: [[
      { extend: "searchList", ajaxOnly: false, options: PRODESP_STATUS_FILTER_OPTIONS },
      "spacer", "orderAsc", "orderDesc", "orderClear",
    ]],
  },
],
language: prodespAtendimentosDataTableLanguage(), // → PortalDt.languagePtBr() + aria
ordering: prodespDtOrderingSilent(),
```

---

## Visual e variáveis CSS

Controláveis em `:root` / override da página:

| Variável | Padrão | Efeito |
|----------|--------|--------|
| `--portal-dt-header-radius` | `0.5rem` | Cantos da cápsula do thead |
| `--portal-dt-stripe-bg` | `#f8f9fa` | Fundo das linhas pares |
| `--portal-dt-th-padding-y` / `-x` | `0.55rem` / `0.5rem` | Padding do `th` |
| `--portal-dt-th-font-size` | `0.8rem` | Fonte do cabeçalho |
| `--portal-dt-cols-z` | `5100` | Menu Colunas acima do CC |
| `--portal-dt-select2-bg` | `#343a40` | Fundo Select2 bootstrap-5 |
| `--dtcc-button_opacity` | `0` | Ícone CC invisível no `th` |

Comportamentos importantes:

- Cabeçalho em **cápsula** (4 cantos) via raio nos `th` extremos + `border-collapse: separate` (não usa `overflow:hidden`, para o título poder quebrar linha).  
- **Zebra** + hover azul suave.  
- ColumnControl: botão cobre o `th`, ícone invisível; checklist nunca no fluxo do `th`.  
- Com `scrollX`: CC e Select2 escondidos no thead espelho do body; `.dt-processing` fantasma oculto.  
- Select2 **bootstrap-5** escuro; filtros KPI do login (`select2--default`) **não** são afetados.

O que **não** entra no core (fica no módulo): larguras `.col-*` PRODESP, badges de tempo, KPIs, typeahead do inventário, padrão legado `#myDataTable` / select “fantasma” no thead.

---

## Checklist ao adotar numa tela nova

1. Carregar CSS + JS na ordem acima (ou só `portal_dt_defaults.js` se a toolbar for outra).  
2. Tabela com `id`; HTML com `table-striped` / `col-acoes` / `portal-dt-acoes` quando couber.  
3. `language: PortalDt.languagePtBr()`, `ordering: PortalDt.orderingSilent()`.  
4. `columnControl: PortalDt.ccSearchList()` nas filtráveis; Ações sem CC; tempos com `ccOrderOnly()`.  
5. Montar toolbar: `PortalDtToolbar.mount` ou `registrarAjusteColunasDataTable` (login).  
6. Smoke:  
   `.\.venv_portal_pessoal\Scripts\python.exe core\tests\test_portal_dt_toolbar_smoke.py`  
7. Hard refresh (Ctrl+F5) após mudar `?v=`.

---

## Segurança

- Preferências só em `localStorage` (fonte / colunas visíveis).  
- Sem rotas/APIs novas no toolkit.  
- Labels do menu Colunas com escape HTML.  
- Preferir `textContent` / escape em células; evitar `innerHTML` com dados crus da API.  
- Auth/autorização das APIs ajax continuam no backend do módulo (não no CSS/JS do core).

---

## Testes

```powershell
.\.venv_portal_pessoal\Scripts\python.exe core\tests\test_portal_dt_toolbar_smoke.py
```

Cobre existência dos assets, exports `PortalDt*`, wiring login/PRODESP, e presença das regras CSS (cápsula, zebra, Select2, `dt-processing`).
