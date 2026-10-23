/**
 * @file prodesp/static/js/prodesp_datatable_page_length.js
 * @module PRODESP — Preferências de DataTable
 *
 * Finalidade:
 *   Restaura e grava a quantidade de linhas por página nas DataTables PRODESP.
 *
 * Telas:
 *   - atendimentos_prodesp.html (#tabela-atendimentos)
 *   - dashboard_atendimentos_prodesp.html (#tabela-gestao-atendimentos)
 *
 * Depende de:
 *   - DataTables 2 (evento length.dt)
 *
 * Expõe (window):
 *   - ProdespDtPageLength { get, save, dtOptions, bindSave, ... }
 *
 * Storage:
 *   - localStorage["prodesp_datatable_page_length"]
 */
(function () {
  "use strict";

  var STORAGE_KEY = "prodesp_datatable_page_length";
  var DEFAULT = 10;
  var ALLOWED = [5, 10, 25, 50, 100, 150, 200, -1];
  var LENGTH_MENU = [
    [5, 10, 25, 50, 100, 150, 200, -1],
    [5, 10, 25, 50, 100, 150, 200, "Todos"],
  ];

  function isAllowed(n) {
    return ALLOWED.indexOf(n) !== -1;
  }

  function getSaved() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (raw === null || raw === "") return DEFAULT;
      var n = parseInt(raw, 10);
      if (!isAllowed(n)) return DEFAULT;
      return n;
    } catch (e) {
      return DEFAULT;
    }
  }

  function save(len) {
    var n = parseInt(len, 10);
    if (!isAllowed(n)) return;
    try {
      localStorage.setItem(STORAGE_KEY, String(n));
    } catch (e) {
      /* quota / modo privado */
    }
  }

  function dtOptions() {
    return {
      pageLength: getSaved(),
      lengthMenu: LENGTH_MENU,
    };
  }

  function bindSave(api) {
    if (!api || typeof api.on !== "function") return;
    api.on("length.dt", function (e, settings, len) {
      save(len);
    });
  }

  window.ProdespDtPageLength = {
    STORAGE_KEY: STORAGE_KEY,
    DEFAULT: DEFAULT,
    ALLOWED: ALLOWED,
    LENGTH_MENU: LENGTH_MENU,
    get: getSaved,
    save: save,
    dtOptions: dtOptions,
    bindSave: bindSave,
  };
})();
