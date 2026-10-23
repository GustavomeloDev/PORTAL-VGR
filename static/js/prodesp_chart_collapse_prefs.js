/**
 * @file prodesp/static/js/prodesp_chart_collapse_prefs.js
 * @module PRODESP — Preferências de UI (dashboard)
 *
 * Finalidade:
 *   Persiste em localStorage o estado aberto/fechado dos painéis .chart-collapse
 *   (Evolução diária, Agendados, Status/substatus, Tempos, Distribuição).
 *
 * Telas:
 *   - prodesp/templates/dashboard_atendimentos_prodesp.html
 *
 * Depende de:
 *   - jQuery, Bootstrap 5 Collapse
 *
 * Expõe (window):
 *   - ProdespChartCollapsePrefs { STORAGE_KEY, loadAll, saveOne, init }
 *
 * Storage:
 *   - localStorage["prodesp_dashboard_chart_collapses"] — JSON { collapseId: boolean }
 */
(function () {
  "use strict";

  var STORAGE_KEY = "prodesp_dashboard_chart_collapses";

  function loadAll() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return {};
      var obj = JSON.parse(raw);
      return obj && typeof obj === "object" ? obj : {};
    } catch (e) {
      return {};
    }
  }

  function saveOne(id, expanded) {
    if (!id) return;
    try {
      var all = loadAll();
      all[id] = !!expanded;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
    } catch (e) {
      /* quota / modo privado */
    }
  }

  function toggleIcon($collapse, expanded) {
    $collapse
      .parent()
      .find(".card-header button i")
      .removeClass("fa-plus fa-minus")
      .addClass(expanded ? "fa-minus" : "fa-plus");
  }

  function applySavedState($collapse) {
    var id = $collapse.attr("id");
    if (!id) return;

    var prefs = loadAll();
    if (!Object.prototype.hasOwnProperty.call(prefs, id)) return;

    var expanded = !!prefs[id];
    var btn = document.querySelector('[data-bs-target="#' + id + '"]');

    $collapse.toggleClass("show", expanded);
    if (btn) btn.setAttribute("aria-expanded", expanded ? "true" : "false");
    toggleIcon($collapse, expanded);
  }

  function init() {
    var $collapses = $(".chart-collapse");
    if (!$collapses.length) return;

    $collapses.each(function () {
      applySavedState($(this));
    });

    $collapses
      .on("show.bs.collapse", function () {
        saveOne(this.id, true);
        toggleIcon($(this), true);
      })
      .on("hide.bs.collapse", function () {
        saveOne(this.id, false);
        toggleIcon($(this), false);
      });
  }

  if (typeof jQuery !== "undefined") {
    jQuery(init);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.ProdespChartCollapsePrefs = {
    STORAGE_KEY: STORAGE_KEY,
    loadAll: loadAll,
    saveOne: saveOne,
    init: init,
  };
})();
