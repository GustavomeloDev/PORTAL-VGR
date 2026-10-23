/**
 * Toolbar padrão DataTables: Limpar Filtros, Atualizar, Colunas, Texto.
 */
(function (global) {
  "use strict";

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function formatRefreshTime(d) {
    d = d || new Date();
    return (
      "Atualizado às " +
      pad2(d.getHours()) +
      ":" +
      pad2(d.getMinutes()) +
      ":" +
      pad2(d.getSeconds())
    );
  }

  function resolveHost(hostElOrSelector, tableId) {
    var host = null;
    if (typeof hostElOrSelector === "string") {
      host = document.querySelector(hostElOrSelector);
    } else if (hostElOrSelector && hostElOrSelector.nodeType === 1) {
      host = hostElOrSelector;
    }
    if (host) return host;

    var table = document.getElementById(tableId);
    if (!table) return null;

    var existing = table.parentElement
      ? table.parentElement.querySelector(
          ':scope > .portal-dt-toolbar-host[data-portal-dt-table="' + tableId + '"]'
        )
      : null;
    if (existing) return existing;

    var before = table.closest(".dataTables_wrapper") || table;
    host = document.createElement("div");
    host.className = "portal-dt-toolbar-host mb-2";
    host.setAttribute("data-portal-dt-table", tableId);
    before.parentNode.insertBefore(host, before);
    return host;
  }

  function tableHasAjax(api) {
    try {
      var s = api.settings()[0];
      return !!(s && s.ajax);
    } catch (e) {
      return false;
    }
  }

  function buildHtml(tableId, showRefresh) {
    var menuId = "portalDtColsMenu-" + tableId;
    var btnAllId = "portalDtColsShowAll-" + tableId;
    var fontId = "portalDtFontSize-" + tableId;
    var clearId = "portalDtClear-" + tableId;
    var refreshId = "portalDtRefresh-" + tableId;
    var refreshTextId = "portalDtRefreshText-" + tableId;
    var refreshBarClass = showRefresh ? "" : " d-none";

    return (
      '<div class="d-flex gap-2 mb-0 flex-wrap align-items-center portal-dt-toolbar w-100">' +
      '<button type="button" class="btn btn-outline-secondary" id="' +
      clearId +
      '" title="Limpar todos os filtros da tabela">' +
      '<i class="fas fa-eraser me-1" aria-hidden="true"></i>Limpar Filtros' +
      "</button>" +
      '<div class="d-flex flex-wrap align-items-center gap-2 ms-auto">' +
      '<div class="portal-dt-refresh-bar border-end pe-2 me-1' +
      refreshBarClass +
      '">' +
      '<small class="text-muted mb-0" aria-live="polite">' +
      '<i class="fas fa-sync-alt me-1" aria-hidden="true"></i>' +
      '<span id="' +
      refreshTextId +
      '">—</span>' +
      "</small>" +
      '<button type="button" class="btn btn-sm btn-outline-secondary" id="' +
      refreshId +
      '" title="Recarregar dados da tabela" aria-label="Atualizar tabela">' +
      '<i class="fas fa-redo me-1" aria-hidden="true"></i>Atualizar' +
      "</button>" +
      "</div>" +
      '<div class="dropdown">' +
      '<button type="button" class="btn btn-sm btn-outline-secondary dropdown-toggle" id="portalDtColsBtn-' +
      tableId +
      '" data-bs-toggle="dropdown" data-bs-auto-close="outside" aria-expanded="false">' +
      '<i class="fas fa-columns me-1" aria-hidden="true"></i>Colunas' +
      "</button>" +
      '<ul class="dropdown-menu dropdown-menu-end portal-dt-cols-menu" id="' +
      menuId +
      '"></ul>' +
      "</div>" +
      '<button type="button" class="btn btn-sm btn-outline-secondary" id="' +
      btnAllId +
      '">Mostrar todas</button>' +
      '<div class="portal-dt-font-control d-flex align-items-center gap-2" title="Tamanho do texto da tabela (salvo neste navegador)">' +
      '<label for="' +
      fontId +
      '" class="text-muted mb-0"><i class="fas fa-text-height me-1" aria-hidden="true"></i>Texto</label>' +
      '<select id="' +
      fontId +
      '" class="form-select form-select-sm portal-dt-font-select" style="width: auto; min-width: 8.5rem;" aria-label="Tamanho do texto da tabela">' +
      '<option value="sm">Pequeno</option>' +
      '<option value="md">Padrão</option>' +
      '<option value="lg">Grande</option>' +
      '<option value="xl">Muito grande</option>' +
      "</select>" +
      "</div>" +
      "</div>" +
      "</div>"
    );
  }

  function setRefreshLabel(tableId, when) {
    var el = document.getElementById("portalDtRefreshText-" + tableId);
    if (el) el.textContent = formatRefreshTime(when);
  }

  /**
   * @param {Element|string|null} hostElOrSelector
   * @param {{
   *   tableId: string,
   *   api: object,
   *   onRefresh?: Function,
   *   onClearExtra?: Function,
   *   columnsMeta?: Array,
   *   showRefresh?: boolean
   * }} options
   */
  function mount(hostElOrSelector, options) {
    options = options || {};
    var tableId = options.tableId;
    var api = options.api;
    if (!tableId || !api) return null;

    var hasAjax = tableHasAjax(api);
    var showRefresh =
      options.showRefresh != null
        ? !!options.showRefresh
        : typeof options.onRefresh === "function" || hasAjax;

    var host = resolveHost(hostElOrSelector, tableId);
    if (!host) return null;

    if (host.getAttribute("data-portal-dt-mounted") === tableId) {
      /* Remonta bindings se API mudou (destroy/reinit). */
    }
    host.setAttribute("data-portal-dt-mounted", tableId);
    host.innerHTML = buildHtml(tableId, showRefresh);

    var clearBtn = document.getElementById("portalDtClear-" + tableId);
    var refreshBtn = document.getElementById("portalDtRefresh-" + tableId);
    var fontSel = document.getElementById("portalDtFontSize-" + tableId);

    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        /* Preferir limpeza completa do login (storage + ColumnControl); senão core PortalDt. */
        if (typeof global.loginClearDtSearchStorage === "function") {
          global.loginClearDtSearchStorage(api);
        } else if (global.PortalDt && typeof global.PortalDt.clearFilters === "function") {
          global.PortalDt.clearFilters(api);
        } else {
          try {
            api.search("");
            api.columns().every(function () {
              this.search("");
            });
            api.draw(false);
          } catch (e) {
            /* ignore */
          }
        }
        if (typeof options.onClearExtra === "function") {
          try {
            options.onClearExtra(api);
          } catch (e2) {
            /* ignore */
          }
        }
      });
    }

    if (refreshBtn && showRefresh) {
      refreshBtn.addEventListener("click", function () {
        var icon = refreshBtn.querySelector(".fa-redo, .fa-sync-alt");
        if (icon) icon.classList.add("fa-spin");
        refreshBtn.disabled = true;
        var done = function () {
          setRefreshLabel(tableId);
          if (icon) icon.classList.remove("fa-spin");
          refreshBtn.disabled = false;
        };
        try {
          if (typeof options.onRefresh === "function") {
            var ret = options.onRefresh(api);
            if (ret && typeof ret.then === "function") {
              ret.then(done, done);
            } else {
              global.setTimeout(done, 200);
            }
          } else if (api.ajax && typeof api.ajax.reload === "function") {
            api.ajax.reload(done, false);
          } else {
            done();
          }
        } catch (e) {
          done();
        }
      });
      setRefreshLabel(tableId);
    }

    if (global.PortalDtFontSize && fontSel) {
      global.PortalDtFontSize.trackTable(tableId);
      global.PortalDtFontSize.bindSelect(fontSel, tableId);
    }

    if (global.PortalDtColumns) {
      try {
        global.PortalDtColumns.init(api, tableId, options.columnsMeta || { lockLastIfAcoes: true });
      } catch (eCols) {
        /* não derrubar init da DataTable / tabelas seguintes no Deferred */
        if (typeof console !== "undefined" && console.warn) {
          console.warn("PortalDtColumns.init:", tableId, eCols);
        }
      }
      /* ColumnControl pode montar o thead depois; reforça labels. */
      global.setTimeout(function () {
        try {
          if (global.PortalDtColumns && typeof global.PortalDtColumns.refreshMenu === "function") {
            global.PortalDtColumns.refreshMenu(
              api,
              tableId,
              options.columnsMeta || { lockLastIfAcoes: true }
            );
          }
        } catch (eRefresh) {
          /* ignore */
        }
      }, 0);
    }

    initColsDropdown(tableId, api, options.columnsMeta || { lockLastIfAcoes: true });

    api.off("xhr.portalDtToolbar draw.portalDtToolbar");
    if (showRefresh) {
      api.on("xhr.portalDtToolbar", function () {
        setRefreshLabel(tableId);
      });
      api.on("draw.portalDtToolbar", function () {
        /* timestamp só em xhr; draw local não sobrescreve */
      });
    }

    return host;
  }

  function dismissColumnControlPanels() {
    document.querySelectorAll("div.dtcc-dropdown").forEach(function (el) {
      if (el.parentNode) el.parentNode.removeChild(el);
    });
  }

  function initColsDropdown(tableId, api, columnsMeta) {
    var btn = document.getElementById("portalDtColsBtn-" + tableId);
    if (!btn) return;
    try {
      if (global.bootstrap && global.bootstrap.Dropdown) {
        global.bootstrap.Dropdown.getOrCreateInstance(btn, {
          autoClose: "outside",
          popperConfig: { strategy: "fixed" },
        });
      }
    } catch (e) {
      if (typeof console !== "undefined" && console.warn) {
        console.warn("PortalDtToolbar.Dropdown:", tableId, e);
      }
    }
    /* Ao abrir Colunas: fecha ColumnControl e reconstrói nomes reais. */
    btn.addEventListener("show.bs.dropdown", function () {
      dismissColumnControlPanels();
      try {
        if (api && global.PortalDtColumns && typeof global.PortalDtColumns.refreshMenu === "function") {
          global.PortalDtColumns.refreshMenu(api, tableId, columnsMeta);
        }
      } catch (eRefresh) {
        /* ignore */
      }
    });
  }

  global.PortalDtToolbar = {
    mount: mount,
    formatRefreshTime: formatRefreshTime,
    setRefreshLabel: setRefreshLabel,
  };
})(typeof window !== "undefined" ? window : globalThis);
