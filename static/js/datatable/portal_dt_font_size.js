/**
 * Preferência de tamanho de fonte para DataTables do Portal.
 * CSS var --portal-dt-font-size no wrapper #tableId_wrapper.
 */
(function (global) {
  "use strict";

  var STORAGE_KEY = "portal_dt_font_size";
  var PX = { sm: "12.5px", md: "14px", lg: "16px", xl: "18px" };
  var BODY_CLASS = {
    sm: "portal-dt-font-sm",
    md: "portal-dt-font-md",
    lg: "portal-dt-font-lg",
    xl: "portal-dt-font-xl",
  };
  var ALL_BODY_CLASSES = Object.keys(BODY_CLASS).map(function (k) {
    return BODY_CLASS[k];
  });
  var trackedTableIds = {};
  var resizeBound = false;
  var resizeDebounce = null;
  var resizeObservers = {};

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

  function safeCssEscape(id) {
    if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
      return CSS.escape(id);
    }
    return String(id).replace(/([^a-zA-Z0-9_-])/g, "\\$1");
  }

  function wrapperEl(tableId) {
    return (
      document.getElementById(tableId + "_wrapper") ||
      document.querySelector("#" + safeCssEscape(tableId) + "_wrapper")
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
    w.style.setProperty("--portal-dt-font-size", px);
    w.classList.add("portal-dt-font-on");
  }

  function reapplyToTable(tableId) {
    var key = getSaved();
    syncBodyFontClass(key);
    applyToWrapper(tableId, key);
  }

  function reapplyToTracked() {
    var key = getSaved();
    syncBodyFontClass(key);
    Object.keys(trackedTableIds).forEach(function (id) {
      applyToWrapper(id, key);
    });
  }

  function adjustTableColumns(tableId) {
    if (!global.jQuery || !global.jQuery.fn.dataTable) return;
    var selId = "#" + tableId;
    if (!global.jQuery.fn.dataTable.isDataTable(selId)) return;
    try {
      global.jQuery(selId).DataTable().columns.adjust();
    } catch (err) {
      /* ignore */
    }
  }

  function scheduleAdjustColumns(tableId) {
    if (resizeDebounce) clearTimeout(resizeDebounce);
    resizeDebounce = setTimeout(function () {
      if (tableId) {
        adjustTableColumns(tableId);
      } else {
        Object.keys(trackedTableIds).forEach(adjustTableColumns);
      }
    }, 120);
  }

  function observeWrapper(tableId) {
    if (!global.ResizeObserver) return;
    var w = wrapperEl(tableId);
    if (!w) return;
    if (resizeObservers[tableId]) {
      resizeObservers[tableId].disconnect();
    }
    var ro = new ResizeObserver(function () {
      scheduleAdjustColumns(tableId);
    });
    ro.observe(w);
    resizeObservers[tableId] = ro;
  }

  function bindResizeHandlers(tableId) {
    if (!resizeBound) {
      resizeBound = true;
      global.addEventListener("resize", function () {
        scheduleAdjustColumns();
      });
    }
    if (tableId) observeWrapper(tableId);
  }

  function apply(sizeKey, selectEl) {
    var key = normalizeKey(sizeKey);
    try {
      localStorage.setItem(STORAGE_KEY, key);
    } catch (e) {
      /* ignore */
    }
    reapplyToTracked();
    if (selectEl && selectEl.value !== key) {
      selectEl.value = key;
    }
    document.querySelectorAll(".portal-dt-font-select").forEach(function (sel) {
      if (sel !== selectEl && sel.value !== key) sel.value = key;
    });
    scheduleAdjustColumns();
  }

  function bindSelect(selectEl, tableId) {
    if (!selectEl) return;
    if (tableId) {
      trackedTableIds[tableId] = true;
      bindResizeHandlers(tableId);
    }
    selectEl.value = getSaved();
    if (selectEl.dataset.portalFontBound) return;
    selectEl.dataset.portalFontBound = "1";
    selectEl.addEventListener("change", function () {
      apply(this.value, this);
    });
    reapplyToTable(tableId || Object.keys(trackedTableIds)[0]);
  }

  function trackTable(tableId) {
    if (!tableId) return;
    trackedTableIds[tableId] = true;
    reapplyToTable(tableId);
    bindResizeHandlers(tableId);
    if (!global.jQuery || !global.jQuery.fn.dataTable) return;
    var selId = "#" + tableId;
    if (!global.jQuery.fn.dataTable.isDataTable(selId)) return;
    var api = global.jQuery(selId).DataTable();
    api.off("draw.portalDtFont");
    api.on("draw.portalDtFont", function () {
      reapplyToTable(tableId);
      scheduleAdjustColumns(tableId);
    });
  }

  global.PortalDtFontSize = {
    apply: apply,
    getSaved: getSaved,
    bindSelect: bindSelect,
    reapplyToTable: reapplyToTable,
    trackTable: trackTable,
    scheduleAdjustColumns: scheduleAdjustColumns,
  };
})(typeof window !== "undefined" ? window : globalThis);
