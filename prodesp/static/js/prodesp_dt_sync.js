/**
 * Sincronização PRODESP — reload periódico (KPIs + DataTable) + poll leve de data_revision.
 *
 * Com useRevision (padrão): o tick só faz ajax.reload se data_revision mudou (ou force).
 * Assim a fila com milhares de linhas não trava os botões a cada 90 s sem mudança de dados.
 *
 * Antes/depois do reload: fecha overlays transitórios (ColumnControl, Select2, dropdowns,
 * backdrop órfão) para não deixar camada órfã cobrindo a página.
 */
(function (global) {
  "use strict";

  const DEFAULT_INTERVAL_MS = 90 * 1000;

  function config() {
    const c = global.PRODESP_DT_SYNC || {};
    return {
      intervalMs: Number(c.intervalMs) > 0 ? Number(c.intervalMs) : DEFAULT_INTERVAL_MS,
      useRevision: c.useRevision !== false,
      revisionUrl: (c.revisionUrl || "/prodesp/api/data_revision").replace(/\/$/, ""),
    };
  }

  function msUntilNextSync(intervalMs) {
    const interval = intervalMs || config().intervalMs;
    const elapsed = Date.now() % interval;
    return elapsed === 0 ? interval : interval - elapsed;
  }

  function hasOpenModal() {
    try {
      return document.querySelectorAll(".modal.show").length > 0;
    } catch (_e) {
      return false;
    }
  }

  /**
   * Remove camadas que sobrevivem ao ajax.reload e capturam cliques.
   * Seguro com modal aberto (não fecha o modal; só limpa órfãos se nenhum .show).
   */
  function dismissTransientOverlays() {
    try {
      document.querySelectorAll("div.dtcc-dropdown").forEach(function (el) {
        if (typeof el._close === "function") {
          try {
            el._close();
            return;
          } catch (_closeErr) {
            /* fallback remove abaixo */
          }
        }
        if (el.parentNode) el.parentNode.removeChild(el);
      });
    } catch (_dtcc) {
      /* ignore */
    }

    try {
      if (global.jQuery && global.jQuery.fn && typeof global.jQuery.fn.select2 === "function") {
        global.jQuery(".select2-hidden-accessible").select2("close");
      }
    } catch (_s2) {
      /* ignore */
    }

    try {
      document.querySelectorAll(".select2-container--open").forEach(function (el) {
        el.classList.remove("select2-container--open");
      });
      document.querySelectorAll("body > .select2-container .select2-dropdown").forEach(function (el) {
        var host = el.closest(".select2-container");
        if (host && host.parentNode) host.parentNode.removeChild(host);
      });
    } catch (_s2dom) {
      /* ignore */
    }

    try {
      document.querySelectorAll(".dropdown-menu.show").forEach(function (menu) {
        var toggle =
          (menu.parentElement &&
            menu.parentElement.querySelector("[data-bs-toggle='dropdown']")) ||
          null;
        if (toggle && global.bootstrap && global.bootstrap.Dropdown) {
          var inst = global.bootstrap.Dropdown.getInstance(toggle);
          if (inst) {
            inst.hide();
            return;
          }
        }
        menu.classList.remove("show");
        if (toggle) toggle.setAttribute("aria-expanded", "false");
      });
    } catch (_dd) {
      /* ignore */
    }

    if (!hasOpenModal()) {
      try {
        if (global.ProdespModal && typeof global.ProdespModal.cleanupModalArtifacts === "function") {
          global.ProdespModal.cleanupModalArtifacts();
        } else {
          document.querySelectorAll(".modal-backdrop").forEach(function (el) {
            el.remove();
          });
          document.body.classList.remove("modal-open");
          document.body.style.removeProperty("overflow");
          document.body.style.removeProperty("padding-right");
        }
      } catch (_modal) {
        /* ignore */
      }
    }
  }

  function bindRefreshUi(setLoading) {
    const btn = document.getElementById("btnProdespDtRefreshNow");
    const icon = document.querySelector("#prodesp-dt-last-refresh-label .fa-sync-alt");
    const textEl = document.getElementById("prodesp-dt-last-refresh-text");

    function markUpdated() {
      if (!textEl) return;
      const now = new Date();
      textEl.textContent =
        "Atualizado às " +
        now.toLocaleTimeString("pt-BR", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        });
    }

    function setUiLoading(loading) {
      if (btn) btn.disabled = !!loading;
      if (icon) icon.classList.toggle("fa-spin", !!loading);
      if (typeof setLoading === "function") setLoading(loading);
    }

    if (btn && !btn.dataset.prodespDtSyncBound) {
      btn.dataset.prodespDtSyncBound = "1";
      btn.addEventListener("click", function () {
        if (global.prodespDtSyncInstance && typeof global.prodespDtSyncInstance.forceRefresh === "function") {
          global.prodespDtSyncInstance.forceRefresh();
        }
      });
    }

    return { markUpdated, setUiLoading };
  }

  function create(options) {
    const opts = options || {};
    const cfg = config();
    const intervalMs = opts.intervalMs || cfg.intervalMs;
    const useRevision = opts.useRevision !== undefined ? opts.useRevision : cfg.useRevision;
    const revisionUrl = opts.revisionUrl || cfg.revisionUrl;

    let localRevision = opts.initialRevision != null ? opts.initialRevision : null;
    let timer = null;
    let inFlight = false;
    let pendingForce = false;
    const ui = bindRefreshUi(opts.setLoading);

    function applyServerTime(iso) {
      if (!iso || typeof opts.onServerTime !== "function") return;
      try {
        opts.onServerTime(iso);
      } catch (_e) {
        /* ignore */
      }
    }

    async function fetchRevision() {
      const resp = await fetch(revisionUrl, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!resp.ok) {
        throw new Error("data_revision HTTP " + resp.status);
      }
      return resp.json();
    }

    /**
     * @param {boolean} force — true: sempre ajax.reload (botão Atualizar).
     *   false: com useRevision, só recarrega se data_revision mudou.
     */
    async function tick(force) {
      if (hasOpenModal()) {
        return;
      }
      if (typeof opts.shouldSkip === "function" && opts.shouldSkip(!!force)) {
        return;
      }
      if (inFlight) {
        if (force) pendingForce = true;
        return;
      }

      let shouldReload = !!force || !useRevision;
      let sinceRevision = localRevision;

      if (useRevision) {
        try {
          const data = await fetchRevision();
          applyServerTime(data.server_time);
          const rev = data.data_revision != null ? data.data_revision : data.revision;
          if (rev != null) {
            if (localRevision == null) {
              /* Primeira sync: tabela já veio no load inicial — só ancora a revisão. */
              localRevision = rev;
              sinceRevision = rev;
            } else if (Number(rev) !== Number(localRevision)) {
              sinceRevision = localRevision;
              localRevision = rev;
              shouldReload = true;
            }
          } else if (!force) {
            /* Sem contador no payload: mantém reload periódico por segurança. */
            shouldReload = true;
          }
        } catch (_err) {
          /* Poll falhou: no background não força reload pesado; no force segue. */
          if (!force) {
            return;
          }
          shouldReload = true;
        }
      }

      if (!shouldReload) {
        return;
      }

      if (hasOpenModal()) {
        return;
      }

      const settings = opts.getTableSettings && opts.getTableSettings();
      if (
        settings &&
        settings.jqXHR &&
        settings.jqXHR.readyState !== 4
      ) {
        if (force) pendingForce = true;
        return;
      }

      inFlight = true;
      ui.setUiLoading(true);
      dismissTransientOverlays();
      try {
        await Promise.resolve(opts.onReload(!!force, sinceRevision));
        ui.markUpdated();
      } finally {
        dismissTransientOverlays();
        inFlight = false;
        ui.setUiLoading(false);
        if (pendingForce) {
          pendingForce = false;
          tick(true);
        }
      }
    }

    function schedule() {
      if (timer) clearTimeout(timer);
      const run = function () {
        tick(false).finally(function () {
          timer = setTimeout(run, intervalMs);
        });
      };
      timer = setTimeout(run, msUntilNextSync(intervalMs));
    }

    /** Botão Atualizar / pedido explícito — sempre recarrega a tabela. */
    function forceRefresh() {
      return tick(true);
    }

    /** Voltar à aba / tick leve — só recarrega se data_revision mudou. */
    function checkNow() {
      return tick(false);
    }

    function setRevision(rev) {
      if (rev != null) localRevision = rev;
    }

    function getRevision() {
      return localRevision;
    }

    function stop() {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
    }

    return {
      schedule,
      forceRefresh,
      checkNow,
      setRevision,
      getRevision,
      stop,
      msUntilNextSync: function () {
        return msUntilNextSync(intervalMs);
      },
    };
  }

  global.ProdespDtSync = {
    create,
    msUntilNextSync,
    dismissTransientOverlays,
    hasOpenModal,
    DEFAULT_INTERVAL_MS,
  };
})(typeof window !== "undefined" ? window : globalThis);
