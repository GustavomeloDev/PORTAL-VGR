/**
 * @file prodesp/static/js/prodesp_datatable_font_size.js
 * @module PRODESP — Preferências de DataTable
 *
 * Finalidade:
 *   Controle de tamanho da fonte das tabelas (sm/md/lg/xl) via CSS variable
 *   --prodesp-dt-font-size e classes no body; ajusta colunas após redraw.
 *
 * Telas:
 *   - atendimentos_prodesp.html, dashboard_atendimentos_prodesp.html
 *
 * Tabelas:
 *   - #tabela-atendimentos, #tabela-gestao-atendimentos
 *
 * Expõe (window):
 *   - ProdespDtFontSize { apply, getSaved, refresh, ... }
 *
 * Storage:
 *   - localStorage["prodesp_datatable_font_size"]
 */
(function () {
  "use strict";

  var STORAGE_KEY = "prodesp_datatable_font_size";
  var TABLE_IDS = ["tabela-atendimentos", "tabela-gestao-atendimentos"];
  var PX = { sm: "12.5px", md: "14px", lg: "16px", xl: "18px" };
  var BODY_CLASS = {
    sm: "prodesp-dt-font-sm",
    md: "prodesp-dt-font-md",
    lg: "prodesp-dt-font-lg",
    xl: "prodesp-dt-font-xl",
  };
  var ALL_BODY_CLASSES = Object.keys(BODY_CLASS).map(function (k) {
    return BODY_CLASS[k];
  });

  function normalizeKey(key) {
    return PX[key] ? key : "md";
  }

  function getSaved() {
    try {
      return normalizeKey(localStorage.getItem(STORAGE_KEY));
    } catch (e) {
      return "md";
    }
  }

  function wrapperEl(tableId) {
    return (
      document.getElementById(tableId + "_wrapper") ||
      document.querySelector("#" + tableId + "_wrapper")
    );
  }

  function syncBodyFontClass(sizeKey) {
    var key = normalizeKey(sizeKey);
    ALL_BODY_CLASSES.forEach(function (c) {
      document.body.classList.remove(c);
    });
    document.body.classList.add(BODY_CLASS[key]);
  }

  function applyToWrapper(tableId, sizeKey) {
    var w = wrapperEl(tableId);
    if (!w) return;
    var px = PX[normalizeKey(sizeKey)];
    w.style.setProperty("--prodesp-dt-font-size", px);
    w.classList.add("prodesp-dt-font-on");
  }

  /** Reaplica preferência salva (wrapper + body) — usado após redraw AJAX da DataTable. */
  function reapplySavedToTable(tableId) {
    var key = getSaved();
    syncBodyFontClass(key);
    applyToWrapper(tableId, key);
  }

  function reapplySavedToAll() {
    var key = getSaved();
    syncBodyFontClass(key);
    TABLE_IDS.forEach(function (id) {
      applyToWrapper(id, key);
    });
  }

  var resizeBound = false;
  var resizeDebounce = null;
  var resizeObservers = {};

  function adjustTableColumns(tableId) {
    if (!window.jQuery || !window.jQuery.fn.dataTable) return;
    var selId = "#" + tableId;
    if (!jQuery.fn.dataTable.isDataTable(selId)) return;
    try {
      jQuery(selId).DataTable().columns.adjust();
    } catch (err) {
      /* ignore */
    }
  }

  function adjustAllTables() {
    TABLE_IDS.forEach(adjustTableColumns);
  }

  function scheduleAdjustColumns() {
    if (resizeDebounce) {
      clearTimeout(resizeDebounce);
    }
    resizeDebounce = setTimeout(adjustAllTables, 120);
  }

  function observeWrapper(tableId) {
    if (!window.ResizeObserver) return;
    var w = wrapperEl(tableId);
    if (!w) return;
    if (resizeObservers[tableId]) {
      resizeObservers[tableId].disconnect();
    }
    var ro = new ResizeObserver(scheduleAdjustColumns);
    ro.observe(w);
    resizeObservers[tableId] = ro;
  }

  function bindResizeHandlers() {
    if (!resizeBound) {
      resizeBound = true;
      window.addEventListener("resize", scheduleAdjustColumns);
    }
    TABLE_IDS.forEach(observeWrapper);
  }

  function apply(sizeKey) {
    var key = normalizeKey(sizeKey);

    try {
      localStorage.setItem(STORAGE_KEY, key);
    } catch (e) { /* ignore */ }

    reapplySavedToAll();

    var sel = document.getElementById("prodespDtFontSize");
    if (sel && sel.value !== key) {
      sel.value = key;
    }

    scheduleAdjustColumns();
  }

  function bindControl() {
    var sel = document.getElementById("prodespDtFontSize");
    if (!sel || sel.dataset.prodespFontBound) return;
    sel.dataset.prodespFontBound = "1";
    sel.value = getSaved();
    sel.addEventListener("change", function () {
      apply(this.value);
    });
  }

  function hookDrawEvents() {
    if (!window.jQuery || !window.jQuery.fn.dataTable) return;
    TABLE_IDS.forEach(function (id) {
      var selId = "#" + id;
      if (!jQuery.fn.dataTable.isDataTable(selId)) return;
      var api = jQuery(selId).DataTable();
      api.off("draw.prodespDtFont draw.prodespDtAdjust");
      api.on("draw.prodespDtFont", function () {
        reapplySavedToTable(id);
      });
      api.on("draw.prodespDtAdjust", function () {
        scheduleAdjustColumns();
      });
    });
    bindResizeHandlers();
  }

  function init() {
    apply(getSaved());
    bindControl();
    hookDrawEvents();
    bindResizeHandlers();
  }

  function refresh() {
    apply(getSaved());
    hookDrawEvents();
    bindResizeHandlers();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.ProdespDtFontSize = {
    apply: apply,
    getSaved: getSaved,
    refresh: refresh,
    reapplySaved: reapplySavedToAll,
    reapplySavedToTable: reapplySavedToTable,
    adjustColumns: adjustAllTables,
    scheduleAdjustColumns: scheduleAdjustColumns,
  };
})();
