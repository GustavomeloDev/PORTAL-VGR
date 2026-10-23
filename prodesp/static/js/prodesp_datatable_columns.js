/**
 * Visibilidade de colunas nas DataTables PRODESP (persistência em localStorage).
 */
(function (global) {
  "use strict";

  const STORAGE_PREFIX = "prodesp_dt_cols_v2_";

  function storageKey(tableId) {
    return STORAGE_PREFIX + tableId;
  }

  function loadPrefs(tableId) {
    try {
      const raw = localStorage.getItem(storageKey(tableId));
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : null;
    } catch (e) {
      return null;
    }
  }

  function savePrefs(tableId, prefs) {
    try {
      localStorage.setItem(storageKey(tableId), JSON.stringify(prefs));
    } catch (e) {
      /* quota */
    }
  }

  /**
   * @param {string} tableId
   * @param {Array<{idx:number, label:string, defaultVisible?:boolean, locked?:boolean}>} meta
   */
  function applySaved(api, tableId, meta) {
    if (!api || !meta || !meta.length) return;
    const saved = loadPrefs(tableId);
    meta.forEach((col) => {
      if (col.locked) return;
      let vis = col.defaultVisible !== false;
      if (saved && Object.prototype.hasOwnProperty.call(saved, String(col.idx))) {
        vis = !!saved[String(col.idx)];
      }
      api.column(col.idx).visible(vis, false);
    });
    api.columns.adjust();
  }

  function persistFromApi(api, tableId, meta) {
    const prefs = {};
    meta.forEach((col) => {
      if (col.locked) return;
      prefs[String(col.idx)] = api.column(col.idx).visible();
    });
    savePrefs(tableId, prefs);
  }

  function showAll(api, tableId, meta) {
    if (!api) return;
    meta.forEach((col) => {
      api.column(col.idx).visible(true, false);
    });
    persistFromApi(api, tableId, meta);
    api.columns.adjust().draw(false);
  }

  function mountUi(tableId, api, meta) {
    const menuId = `prodespDtColsMenu-${tableId}`;
    const btnAllId = `prodespDtColsShowAll-${tableId}`;
    let $menu = global.jQuery ? global.jQuery(`#${menuId}`) : null;
    let $btnAll = global.jQuery ? global.jQuery(`#${btnAllId}`) : null;
    if (!$menu || !$menu.length || !$btnAll || !$btnAll.length) return;

    $menu.empty();
    meta.forEach((col) => {
      if (col.locked) return;
      const checked = api.column(col.idx).visible();
      const $li = global.jQuery("<li></li>");
      const $label = global.jQuery(
        `<label class="dropdown-item d-flex align-items-center gap-2 mb-0" style="cursor:pointer;">
          <input type="checkbox" class="form-check-input m-0 prodesp-dt-col-toggle" data-idx="${col.idx}" ${checked ? "checked" : ""}/>
          <span>${col.label}</span>
        </label>`
      );
      $li.append($label);
      $menu.append($li);
    });

    $menu.off("change.prodespCols").on("change.prodespCols", ".prodesp-dt-col-toggle", function () {
      const idx = parseInt(this.getAttribute("data-idx"), 10);
      if (isNaN(idx)) return;
      api.column(idx).visible(!!this.checked, false);
      persistFromApi(api, tableId, meta);
      api.columns.adjust().draw(false);
    });

    $btnAll.off("click.prodespCols").on("click.prodespCols", function () {
      showAll(api, tableId, meta);
      $menu.find(".prodesp-dt-col-toggle").prop("checked", true);
    });
  }

  const ATENDIMENTOS_META = [
    { idx: 0, label: "ID VGR" },
    { idx: 1, label: "Contratada" },
    { idx: 2, label: "Data Agend." },
    { idx: 3, label: "Hora Agend." },
    { idx: 4, label: "Data Atend." },
    { idx: 5, label: "Secretaria" },
    { idx: 6, label: "Endereço" },
    { idx: 7, label: "Município" },
    { idx: 8, label: "Status" },
    { idx: 9, label: "Substatus" },
    { idx: 10, label: "A. Gestão" },
    { idx: 11, label: "A. Config." },
    { idx: 12, label: "A. MPLS" },
    { idx: 13, label: "A. Caderno" },
    { idx: 14, label: "Tempo Etapa" },
    { idx: 15, label: "Tempo de Vida" },
    { idx: 16, label: "Ações", locked: true },
  ];

  const GESTAO_META = [
    { idx: 0, label: "ID VGR" },
    { idx: 1, label: "Contratada" },
    { idx: 2, label: "Data Agend." },
    { idx: 3, label: "Hora Agend." },
    { idx: 4, label: "Data Atend." },
    { idx: 5, label: "Secretaria" },
    { idx: 6, label: "Endereço" },
    { idx: 7, label: "Município" },
    { idx: 8, label: "Status" },
    { idx: 9, label: "Substatus" },
    { idx: 10, label: "A. Gestão" },
    { idx: 11, label: "A. Config." },
    { idx: 12, label: "A. MPLS" },
    { idx: 13, label: "A. Caderno" },
    { idx: 14, label: "Tempo Etapa" },
    { idx: 15, label: "Tempo de Vida" },
    { idx: 16, label: "Ações", locked: true },
  ];

  /** Índices de coluna para filtros KPI / cards (fonte única com GESTAO_META / ATENDIMENTOS_META). */
  function colIdxFromMeta(meta, label) {
    const row = meta.find((c) => c.label === label);
    return row ? row.idx : -1;
  }

  const GESTAO_COL = {
    STATUS: colIdxFromMeta(GESTAO_META, "Status"),
    SUBSTATUS: colIdxFromMeta(GESTAO_META, "Substatus"),
    TEMPO_ETAPA: colIdxFromMeta(GESTAO_META, "Tempo Etapa"),
    TEMPO_VIDA: colIdxFromMeta(GESTAO_META, "Tempo de Vida"),
    ACOES: colIdxFromMeta(GESTAO_META, "Ações"),
  };

  const ATENDIMENTOS_COL = {
    STATUS: colIdxFromMeta(ATENDIMENTOS_META, "Status"),
    SUBSTATUS: colIdxFromMeta(ATENDIMENTOS_META, "Substatus"),
    TEMPO_ETAPA: colIdxFromMeta(ATENDIMENTOS_META, "Tempo Etapa"),
    TEMPO_VIDA: colIdxFromMeta(ATENDIMENTOS_META, "Tempo de Vida"),
    ACOES: colIdxFromMeta(ATENDIMENTOS_META, "Ações"),
  };

  function initTable(api, tableId) {
    const meta =
      tableId === "tabela-gestao-atendimentos" ? GESTAO_META : ATENDIMENTOS_META;
    applySaved(api, tableId, meta);
    mountUi(tableId, api, meta);
    return meta;
  }

  global.ProdespDtColumns = {
    initTable,
    showAll,
    metaFor: (tableId) =>
      tableId === "tabela-gestao-atendimentos" ? GESTAO_META : ATENDIMENTOS_META,
    col: (tableId) =>
      tableId === "tabela-gestao-atendimentos" ? GESTAO_COL : ATENDIMENTOS_COL,
    GESTAO_COL,
    ATENDIMENTOS_COL,
  };
})(typeof window !== "undefined" ? window : globalThis);
