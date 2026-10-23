/**
 * Visibilidade de colunas em DataTables (persistência localStorage).
 */
(function (global) {
  "use strict";

  var STORAGE_PREFIX = "portal_dt_cols_v1_";
  var LABELS_PREFIX = "portal_dt_col_labels_v1_";
  /** Meta estável por tabela (defaultVisible/locked) — refreshMenu só atualiza labels. */
  var _metaCache = {};

  function loadLabelSnapshot(tableId) {
    try {
      var raw = localStorage.getItem(LABELS_PREFIX + tableId);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : null;
    } catch (e) {
      return null;
    }
  }

  function saveLabelSnapshot(tableId, labels) {
    try {
      localStorage.setItem(LABELS_PREFIX + tableId, JSON.stringify(labels));
    } catch (e) {
      /* quota */
    }
  }

  function persistLabelSnapshot(tableId, meta) {
    if (!tableId || !meta || !meta.length) return;
    var snap = loadLabelSnapshot(tableId) || {};
    var changed = false;
    meta.forEach(function (col) {
      if (!col.label || /^Coluna \d+$/i.test(col.label)) return;
      var key = String(col.idx);
      if (snap[key] !== col.label) {
        snap[key] = col.label;
        changed = true;
      }
    });
    if (changed) saveLabelSnapshot(tableId, snap);
  }

  /**
   * Lê <thead> original antes do DataTable (scrollX remove/clona o header depois).
   * Chamar imediatamente antes de `$(table).DataTable(...)`.
   */
  function captureLabelsFromTableElement(tableId) {
    if (!tableId) return;
    var table = document.getElementById(tableId);
    if (!table || !table.tHead || !table.tHead.rows || !table.tHead.rows[0]) return;
    var snap = loadLabelSnapshot(tableId) || {};
    var changed = false;
    var cells = table.tHead.rows[0].cells;
    for (var i = 0; i < cells.length; i++) {
      var lab = labelFromNode(cells[i]);
      if (!lab) continue;
      var key = String(i);
      if (snap[key] !== lab) {
        snap[key] = lab;
        changed = true;
      }
    }
    if (changed) saveLabelSnapshot(tableId, snap);
  }

  function labelFromSnapshot(tableId, idx) {
    var snap = loadLabelSnapshot(tableId);
    if (!snap) return "";
    return normalizeLabel(snap[String(idx)] || "");
  }

  function storageKey(tableId) {
    return STORAGE_PREFIX + tableId;
  }

  function loadPrefs(tableId) {
    try {
      var raw = localStorage.getItem(storageKey(tableId));
      if (!raw) return null;
      var parsed = JSON.parse(raw);
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

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function safeCssEscape(id) {
    if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
      return CSS.escape(id);
    }
    return String(id).replace(/([^a-zA-Z0-9_-])/g, "\\$1");
  }

  function normalizeLabel(s) {
    return String(s == null ? "" : s)
      .replace(/<[^>]*>/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function labelFromNode(node) {
    if (!node) return "";
    try {
      var titleEl = node.querySelector(".dt-column-title");
      if (titleEl) {
        var tit = normalizeLabel(titleEl.textContent);
        if (tit) return tit;
      }
    } catch (e0) {
      /* ignore */
    }
    try {
      var btnText = node.querySelector(".dtcc-button-text");
      if (btnText) {
        var bt = normalizeLabel(btnText.textContent);
        if (bt) return bt;
      }
    } catch (eBtn) {
      /* ignore */
    }
    try {
      var ariaBtn = node.querySelector("button.dtcc-button[aria-label]");
      if (ariaBtn) {
        var aria = normalizeLabel(ariaBtn.getAttribute("aria-label"));
        if (aria && !/^column\s*control/i.test(aria)) return aria;
      }
    } catch (eAria) {
      /* ignore */
    }
    try {
      var clone = node.cloneNode(true);
      var kill = clone.querySelectorAll(
        ".dtcc, .dt-column-order, button, svg, .dtcc-button-icon, .dtcc-button"
      );
      for (var i = 0; i < kill.length; i++) {
        if (kill[i].parentNode) kill[i].parentNode.removeChild(kill[i]);
      }
      var cleaned = normalizeLabel(clone.textContent);
      if (cleaned) return cleaned;
    } catch (e1) {
      /* ignore */
    }
    return normalizeLabel(node.textContent);
  }

  function headerNodesForIndex(api, idx) {
    var nodes = [];
    /* Preferir data-dt-column / API: querySelectorAll(th)[idx] quebra com colunas ocultas
       (NodeList só tem th visíveis → label errado, ex. "Ações"). */
    try {
      var container = api.table().container();
      if (container) {
        var byAttr = container.querySelectorAll(
          'th[data-dt-column="' + idx + '"], td[data-dt-column="' + idx + '"]'
        );
        for (var a = 0; a < byAttr.length; a++) nodes.push(byAttr[a]);
      }
    } catch (e0) {
      /* ignore */
    }
    try {
      var hdr = api.column(idx).header();
      if (hdr) nodes.push(hdr);
    } catch (e1) {
      /* ignore */
    }
    try {
      var settings = api.settings()[0];
      var col = settings && settings.aoColumns ? settings.aoColumns[idx] : null;
      if (col && col.nTh) nodes.push(col.nTh);
    } catch (e2) {
      /* ignore */
    }
    return nodes;
  }

  function titleFromSettings(api, idx) {
    try {
      if (api.column && typeof api.column(idx).title === "function") {
        var apiTitle = normalizeLabel(api.column(idx).title());
        if (apiTitle) return apiTitle;
      }
    } catch (e0) {
      /* ignore */
    }
    try {
      var settings = api.settings()[0];
      var col = settings && settings.aoColumns ? settings.aoColumns[idx] : null;
      if (col) {
        var raw = normalizeLabel(col.sTitle || col.title || "");
        if (raw) return raw;
        if (col.nTh) {
          var fromNth = labelFromNode(col.nTh);
          if (fromNth) return fromNth;
        }
      }
      if (settings.nTHead && settings.nTHead.rows && settings.nTHead.rows[0]) {
        var headCell = settings.nTHead.rows[0].cells[idx];
        if (headCell) {
          var fromTHead = labelFromNode(headCell);
          if (fromTHead) return fromTHead;
        }
      }
    } catch (e1) {
      /* ignore */
    }
    return "";
  }

  function resolveColumnLabel(api, idx, tableId) {
    /* Settings/API primeiro — estável com coluna hidden; DOM indexado por último. */
    var fromSettings = titleFromSettings(api, idx);
    if (fromSettings) return fromSettings;
    if (tableId) {
      var fromSnap = labelFromSnapshot(tableId, idx);
      if (fromSnap) return fromSnap;
    }
    var nodes = headerNodesForIndex(api, idx);
    for (var i = 0; i < nodes.length; i++) {
      var label = labelFromNode(nodes[i]);
      if (label) return label;
    }
    return "";
  }

  function enrichMetaLabels(api, tableId, meta) {
    return meta.map(function (col) {
      var next = cloneMetaEntry(col);
      if (!next.label || /^Coluna \d+$/i.test(next.label)) {
        var stable = resolveColumnLabel(api, col.idx, tableId);
        if (stable) next.label = stable;
      }
      if (!next.label) next.label = "Coluna " + (col.idx + 1);
      return next;
    });
  }

  function cloneMetaEntry(col) {
    return {
      idx: col.idx,
      label: col.label,
      locked: !!col.locked,
      defaultVisible: col.defaultVisible !== false,
    };
  }

  function isDataOnlyColumn(api, idx) {
    try {
      var settings = api.settings()[0];
      var col = settings && settings.aoColumns ? settings.aoColumns[idx] : null;
      if (col && col.className) {
        var cn = col.className;
        if (typeof cn === "string" && cn.indexOf("portal-dt-col-data-only") !== -1) return true;
        if (Array.isArray(cn) && cn.indexOf("portal-dt-col-data-only") !== -1) return true;
      }
      if (col && col.nTh && col.nTh.classList && col.nTh.classList.contains("portal-dt-col-data-only")) {
        return true;
      }
      var header = api.column(idx).header();
      if (header && header.classList && header.classList.contains("portal-dt-col-data-only")) {
        return true;
      }
    } catch (e) {
      /* ignore */
    }
    return false;
  }

  function refreshMetaLabels(api, tableId, cachedMeta) {
    return cachedMeta.map(function (col) {
      var next = cloneMetaEntry(col);
      var fromSettings = titleFromSettings(api, col.idx);
      if (fromSettings) {
        next.label = fromSettings;
        return next;
      }
      if (!next.label || /^Coluna \d+$/i.test(next.label)) {
        var label = resolveColumnLabel(api, col.idx, tableId);
        if (label) next.label = label;
      }
      if (!next.label) next.label = "Coluna " + (col.idx + 1);
      return next;
    });
  }

  function targetMatchesIndex(targets, idx) {
    if (targets === idx || targets === "_all") return true;
    if (Array.isArray(targets)) {
      for (var i = 0; i < targets.length; i++) {
        if (targets[i] === idx || targets[i] === "_all") return true;
      }
    }
    return false;
  }

  /**
   * visible:false na definição inicial (columnDefs/columns) — não o estado após stateSave.
   * Com stateSave, this.visible() já vem false no F5 e não pode lockar o toggle.
   */
  function isDefinedHiddenInInit(api, idx) {
    try {
      var settings = api.settings()[0];
      var oInit = settings && settings.oInit;
      if (!oInit) return false;
      if (Array.isArray(oInit.columns) && oInit.columns[idx] && oInit.columns[idx].visible === false) {
        return true;
      }
      var defs = oInit.columnDefs || [];
      for (var d = 0; d < defs.length; d++) {
        var def = defs[d];
        if (!def || def.visible !== false) continue;
        if (targetMatchesIndex(def.targets, idx)) return true;
      }
    } catch (e) {
      /* ignore */
    }
    return false;
  }

  /**
   * Meta a partir dos <th> da tabela (snapshot inicial — não reexecutar após o usuário ocultar colunas).
   * @param {object} api — DataTables API
   * @param {{ lockLastIfAcoes?: boolean, lockHiddenColumns?: boolean }} [opts]
   * @returns {Array<{idx:number,label:string,locked?:boolean,defaultVisible?:boolean}>}
   */
  function metaFromHeader(api, opts, tableId) {
    opts = opts || {};
    var lockHidden = opts.lockHiddenColumns !== false;
    var lockAcoes = opts.lockLastIfAcoes !== false;
    var meta = [];
    if (!api || !api.columns) return meta;
    api.columns().every(function (idx) {
      var header = "";
      try {
        header = resolveColumnLabel(api, idx, tableId);
      } catch (e) {
        header = "";
      }
      if (!header) header = "Coluna " + (idx + 1);

      var definedHidden = isDefinedHiddenInInit(api, idx) || isDataOnlyColumn(api, idx);

      var locked = false;
      var headerKey = header.replace(/\s+/g, "");
      if (lockAcoes && /^a[cç][oõ]es$/i.test(headerKey)) {
        locked = true;
      }
      /* Só locka data-only / visible:false da definição — NÃO o oculto pelo usuário (stateSave/prefs). */
      if (definedHidden && lockHidden) {
        locked = true;
      }

      meta.push({
        idx: idx,
        label: header,
        locked: locked,
        /* defaultVisible: definição; prefs/stateSave aplicam depois em applySaved. */
        defaultVisible: definedHidden ? false : true,
      });
    });
    return meta;
  }

  function resolveMeta(api, tableId, metaOrOpts, mode) {
    if (Array.isArray(metaOrOpts)) {
      var explicit = metaOrOpts.map(cloneMetaEntry);
      _metaCache[tableId] = explicit;
      return explicit;
    }
    if (mode === "init" || !_metaCache[tableId]) {
      _metaCache[tableId] = metaFromHeader(api, metaOrOpts || { lockLastIfAcoes: true }, tableId);
      _metaCache[tableId] = enrichMetaLabels(api, tableId, _metaCache[tableId]);
      persistLabelSnapshot(tableId, _metaCache[tableId]);
      return _metaCache[tableId];
    }
    var refreshed = refreshMetaLabels(api, tableId, _metaCache[tableId]);
    _metaCache[tableId] = refreshed;
    persistLabelSnapshot(tableId, refreshed);
    return refreshed;
  }

  /**
   * columns.adjust() em aba display:none / scrollX incompleto estoura
   * scrollHeight e quebra o Deferred do jQuery (tabelas seguintes não iniciam).
   */
  function isTableVisiblyLaidOut(api) {
    try {
      var node = api.table().node();
      if (!node || !node.isConnected) return false;
      if (node.offsetParent === null && !(node.getClientRects && node.getClientRects().length)) {
        var style = global.getComputedStyle ? global.getComputedStyle(node) : null;
        if (style && style.display === "none") return false;
        var pane = node.closest ? node.closest(".tab-pane") : null;
        if (pane && !pane.classList.contains("active") && !pane.classList.contains("show")) {
          return false;
        }
      }
      return true;
    } catch (e) {
      return false;
    }
  }

  function clearDtWidthLocks(container) {
    if (!container) return;
    Array.prototype.forEach.call(
      container.querySelectorAll(".dt-scroll-head colgroup, .dt-scroll-body colgroup"),
      function (el) {
        if (el.parentNode) el.parentNode.removeChild(el);
      }
    );
    Array.prototype.forEach.call(
      container.querySelectorAll(
        ".dt-scroll-head table, .dt-scroll-body table, .dt-scroll-head th, .dt-scroll-body th, .dt-scroll-body td"
      ),
      function (el) {
        el.style.width = "";
        el.style.minWidth = "";
        el.style.maxWidth = "";
      }
    );
    var headInner = container.querySelector(".dt-scroll-headInner");
    if (headInner) {
      headInner.style.width = "";
      headInner.style.minWidth = "";
      headInner.style.maxWidth = "";
    }
  }

  function clearAoColumnWidths(api) {
    try {
      var settings = api.settings()[0];
      var cols = settings && settings.aoColumns;
      if (!cols) return;
      for (var i = 0; i < cols.length; i++) {
        cols[i].sWidth = null;
        cols[i].sWidthOrig = null;
        if (Object.prototype.hasOwnProperty.call(cols[i], "width")) {
          cols[i].width = null;
        }
      }
    } catch (e) {
      /* ignore */
    }
  }

  /**
   * Após show/hide de colunas com scrollX + autoWidth:false:
   * redistribui larguras — preenche o container se couber; senão scroll real.
   */
  function fitScrollColumns(api) {
    var container = api.table().container();
    if (!container) {
      api.columns.adjust();
      return;
    }
    clearAoColumnWidths(api);
    clearDtWidthLocks(container);

    var scrollBody = container.querySelector(".dt-scroll-body");
    var bodyTable = container.querySelector(".dt-scroll-body table");
    var headTable = container.querySelector(".dt-scroll-head table");
    var headInner = container.querySelector(".dt-scroll-headInner");
    if (!scrollBody || !bodyTable) {
      api.columns.adjust();
      return;
    }

    var avail = scrollBody.clientWidth;
    if (!(avail > 0)) {
      api.columns.adjust();
      return;
    }

    /* 1) Mede largura natural do conteúdo (sem trava de 100%). */
    bodyTable.style.width = "auto";
    if (headTable) headTable.style.width = "auto";
    if (headInner) headInner.style.width = "auto";
    api.columns.adjust();

    var natural = Math.max(bodyTable.scrollWidth || 0, bodyTable.offsetWidth || 0);
    /* 2) Cabe no container → preenche (some gap + scrollbar fantasma).
          Não cabe → largura do conteúdo (scroll horizontal real). */
    var target = natural > avail + 2 ? natural : avail;

    bodyTable.style.width = target + "px";
    if (headTable) headTable.style.width = target + "px";
    if (headInner) headInner.style.width = target + "px";
    api.columns.adjust();

    scrollBody.scrollLeft = 0;
    var scrollHead = container.querySelector(".dt-scroll-head");
    if (scrollHead) scrollHead.scrollLeft = 0;
  }

  function safeColumnsAdjust(api, andDraw) {
    if (!api || !api.columns) return;
    if (!isTableVisiblyLaidOut(api)) {
      if (typeof global.agendarAjusteDataTablesVisiveis === "function") {
        global.agendarAjusteDataTablesVisiveis(80);
      }
      return;
    }
    try {
      fitScrollColumns(api);
      if (andDraw) {
        api.draw(false);
        global.setTimeout(function () {
          try {
            if (!isTableVisiblyLaidOut(api)) return;
            fitScrollColumns(api);
          } catch (e2) {
            /* ignore */
          }
        }, 0);
      } else {
        global.setTimeout(function () {
          try {
            if (!isTableVisiblyLaidOut(api)) return;
            fitScrollColumns(api);
          } catch (e3) {
            /* ignore */
          }
        }, 0);
      }
    } catch (e) {
      if (typeof global.agendarAjusteDataTablesVisiveis === "function") {
        global.agendarAjusteDataTablesVisiveis(120);
      }
    }
  }

  function applySaved(api, tableId, meta) {
    if (!api || !meta || !meta.length) return;
    var saved = loadPrefs(tableId);
    meta.forEach(function (col) {
      if (col.locked) {
        /* Mantém data-only ocultas; Ações (locked + visible) intactas. */
        if (col.defaultVisible === false) {
          try {
            api.column(col.idx).visible(false, false);
          } catch (e) {
            /* ignore */
          }
        }
        return;
      }
      var vis = col.defaultVisible !== false;
      if (saved && Object.prototype.hasOwnProperty.call(saved, String(col.idx))) {
        vis = !!saved[String(col.idx)];
      }
      try {
        api.column(col.idx).visible(vis, false);
      } catch (e2) {
        /* coluna inválida / tabela destruída */
      }
    });
    safeColumnsAdjust(api, false);
  }

  function persistFromApi(api, tableId, meta) {
    var prefs = {};
    meta.forEach(function (col) {
      if (col.locked) return;
      try {
        prefs[String(col.idx)] = api.column(col.idx).visible();
      } catch (e) {
        /* ignore */
      }
    });
    savePrefs(tableId, prefs);
    persistLabelSnapshot(tableId, meta);
  }

  function showAll(api, tableId, meta) {
    if (!api) return;
    meta.forEach(function (col) {
      /* Não reexibir colunas data-only (Situação, etc.). */
      if (col.locked && col.defaultVisible === false) return;
      try {
        api.column(col.idx).visible(true, false);
      } catch (e) {
        /* ignore */
      }
    });
    persistFromApi(api, tableId, meta);
    safeColumnsAdjust(api, true);
  }

  function mountUi(tableId, api, meta) {
    if (!global.jQuery) return;
    var $ = global.jQuery;
    var menuId = "portalDtColsMenu-" + tableId;
    var btnAllId = "portalDtColsShowAll-" + tableId;
    var $menu = $("#" + safeCssEscape(menuId));
    var $btnAll = $("#" + safeCssEscape(btnAllId));
    if (!$menu.length || !$btnAll.length) return;

    $menu.empty();
    var added = 0;
    meta.forEach(function (col) {
      if (col.locked) return;
      var checked = api.column(col.idx).visible();
      var $li = $("<li></li>");
      var $label = $(
        '<label class="dropdown-item d-flex align-items-center gap-2 mb-0" style="cursor:pointer;">' +
          '<input type="checkbox" class="form-check-input m-0 portal-dt-col-toggle" data-idx="' +
          col.idx +
          '" ' +
          (checked ? "checked" : "") +
          "/>" +
          "<span>" +
          escapeHtml(col.label) +
          "</span>" +
          "</label>"
      );
      $li.append($label);
      $menu.append($li);
      added += 1;
    });
    if (!added) {
      $menu.append(
        $('<li><span class="dropdown-item-text text-muted small">Nenhuma coluna disponível</span></li>')
      );
    }

    $menu.off("change.portalCols").on("change.portalCols", ".portal-dt-col-toggle", function () {
      var idx = parseInt(this.getAttribute("data-idx"), 10);
      if (isNaN(idx)) return;
      try {
        api.column(idx).visible(!!this.checked, false);
      } catch (e) {
        return;
      }
      persistFromApi(api, tableId, meta);
      safeColumnsAdjust(api, true);
    });

    $btnAll.off("click.portalCols").on("click.portalCols", function () {
      showAll(api, tableId, meta);
      $menu.find(".portal-dt-col-toggle").prop("checked", true);
    });
  }

  /**
   * @param {object} api
   * @param {string} tableId
   * @param {Array|{lockLastIfAcoes?:boolean}|null} [metaOrOpts]
   */
  function init(api, tableId, metaOrOpts) {
    if (!api || !tableId) return null;
    var meta = resolveMeta(api, tableId, metaOrOpts, "init");
    applySaved(api, tableId, meta);
    mountUi(tableId, api, meta);
    return meta;
  }

  /** Reconstrói o menu Colunas (labels + checkboxes) sem reaplicar prefs nem re-lockar colunas ocultas. */
  function refreshMenu(api, tableId, metaOrOpts) {
    if (!api || !tableId) return null;
    var meta = resolveMeta(api, tableId, metaOrOpts, "refresh");
    mountUi(tableId, api, meta);
    return meta;
  }

  global.PortalDtColumns = {
    init: init,
    refreshMenu: refreshMenu,
    showAll: showAll,
    metaFromHeader: metaFromHeader,
    applySaved: applySaved,
    safeColumnsAdjust: safeColumnsAdjust,
    captureLabelsFromTableElement: captureLabelsFromTableElement,
  };
})(typeof window !== "undefined" ? window : globalThis);
