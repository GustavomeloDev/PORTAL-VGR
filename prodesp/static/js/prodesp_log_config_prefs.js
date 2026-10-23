/**
 * @file prodesp/static/js/prodesp_log_config_prefs.js
 * Altura da caixa de Logs Configuração (edição/criação) — redimensionável e persistida.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "prodesp_log_config_text_height";
  var DEFAULT_HEIGHT = 160;
  var MIN_HEIGHT = 72;
  var MAX_HEIGHT = 520;
  var debounceTimer = null;

  function clampHeight(px) {
    return Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, Math.round(px)));
  }

  function getHeight() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      var v = parseInt(raw, 10);
      return clampHeight(Number.isFinite(v) ? v : DEFAULT_HEIGHT);
    } catch (e) {
      return DEFAULT_HEIGHT;
    }
  }

  function saveHeight(px) {
    try {
      localStorage.setItem(STORAGE_KEY, String(clampHeight(px)));
    } catch (e) {
      /* quota / modo privado */
    }
  }

  function applyToWrap(wrap) {
    if (!wrap) return;
    wrap.style.height = getHeight() + "px";
  }

  function bindResize(wrap) {
    if (!wrap || wrap.dataset.prodespLogResizeBound === "1") {
      applyToWrap(wrap);
      return;
    }
    wrap.dataset.prodespLogResizeBound = "1";
    applyToWrap(wrap);

    if (typeof ResizeObserver === "undefined") return;

    var ro = new ResizeObserver(function () {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function () {
        saveHeight(wrap.getBoundingClientRect().height);
      }, 250);
    });
    ro.observe(wrap);
    wrap._prodespLogResizeObserver = ro;
  }

  function resetHeight() {
    saveHeight(DEFAULT_HEIGHT);
    document.querySelectorAll(".incident-log-text-wrap").forEach(applyToWrap);
  }

  function bindResetButtons() {
    document.querySelectorAll("[data-prodesp-log-reset-height]").forEach(function (btn) {
      if (btn.dataset.prodespLogResetBound === "1") return;
      btn.dataset.prodespLogResetBound = "1";
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        resetHeight();
      });
    });
  }

  function initAll() {
    document.querySelectorAll(".incident-log-text-wrap").forEach(bindResize);
    bindResetButtons();
  }

  window.ProdespLogConfigPrefs = {
    STORAGE_KEY: STORAGE_KEY,
    DEFAULT_HEIGHT: DEFAULT_HEIGHT,
    MIN_HEIGHT: MIN_HEIGHT,
    MAX_HEIGHT: MAX_HEIGHT,
    getHeight: getHeight,
    saveHeight: saveHeight,
    applyToWrap: applyToWrap,
    bindResize: bindResize,
    initAll: initAll,
    resetHeight: resetHeight,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
