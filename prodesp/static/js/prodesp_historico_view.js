/**
 * @file prodesp/static/js/prodesp_historico_view.js
 * @module PRODESP — Modal (aba Histórico)
 *
 * Finalidade:
 *   Renderiza histórico de alterações em accordion (visualização read-only e completo
 *   para admin), com expandir/recolher todos.
 *
 * Telas:
 *   - atendimentos_prodesp.html, dashboard_atendimentos_prodesp.html
 *
 * Expõe (window):
 *   - renderHistorico, renderHistoricoCompleto, prodespBindHistoricoCollapseControls
 *
 * Usado por:
 *   - script_atendimentos_prodesp.js, script_gestao_atendimentos_prodesp.js
 */
(function () {
  function prodespHistoricoAccordionPanel(uid, sectionId, title, innerHtml, expanded) {
    const collapseId = `${uid}-${sectionId}`;
    const expandedCls = expanded ? " show" : "";
    const btnCollapsed = expanded ? "" : " collapsed";
    const ariaExpanded = expanded ? "true" : "false";
    return (
      `<div class="accordion-item">` +
      `<h2 class="accordion-header">` +
      `<button class="accordion-button${btnCollapsed} py-2" type="button" data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="${ariaExpanded}" aria-controls="${collapseId}">` +
      `<span class="text-primary fw-semibold">${title}</span>` +
      `</button></h2>` +
      `<div id="${collapseId}" class="accordion-collapse collapse${expandedCls}" data-hist-section="${sectionId}" data-bs-parent="#${uid}-accordion">` +
      `<div class="accordion-body pt-2 pb-3">${innerHtml}</div>` +
      `</div></div>`
    );
  }

  const HIST_SECTION_PREFS_KEY = "prodesp_historico_accordion_sections";

  function loadHistoricoSectionPrefs() {
    try {
      const raw = localStorage.getItem(HIST_SECTION_PREFS_KEY);
      if (!raw) return {};
      const obj = JSON.parse(raw);
      return obj && typeof obj === "object" ? obj : {};
    } catch (e) {
      return {};
    }
  }

  function saveHistoricoSectionPref(sectionId, expanded) {
    if (!sectionId) return;
    try {
      const all = loadHistoricoSectionPrefs();
      all[sectionId] = !!expanded;
      localStorage.setItem(HIST_SECTION_PREFS_KEY, JSON.stringify(all));
    } catch (e) {
      /* quota / modo privado */
    }
  }

  function historicoSectionExpanded(sectionId, defaultOpen) {
    const prefs = loadHistoricoSectionPrefs();
    if (Object.prototype.hasOwnProperty.call(prefs, sectionId)) {
      return !!prefs[sectionId];
    }
    return !!defaultOpen;
  }

  function renderHistorico(historicoData, isAdmin) {
    if (!historicoData || historicoData.length === 0) {
      return '<div class="text-muted ms-2 mt-2">Nenhum histórico encontrado.</div>';
    }

    const formatarData = (dataStr) => {
      if (!dataStr) return "—";
      try {
        const dataObj = new Date(dataStr);
        if (!isNaN(dataObj.getTime())) {
          return dataObj.toLocaleString("pt-BR");
        }
      } catch (e) {
        /* ignore */
      }
      return dataStr;
    };

    if (isAdmin) {
      const tableRows = historicoData
        .map(
          (log) => `
        <tr>
          <td>${formatarData(log.data_alteracao_historico)}</td>
          <td>${log.usuario_re_historico || ""} – ${log.usuario_nome_historico || "—"}</td>
          <td>${log.campo_alterado_historico || "—"}</td>
          <td>${log.valor_antigo_historico || "—"}</td>
          <td>${log.valor_novo_historico || "—"}</td>
          <td>${log.operacao_historico || "—"}</td>
        </tr>
      `
        )
        .join("");

      return `<div class="table-responsive"><table class="table table-sm table-striped table-hover mb-0"><thead><tr><th>Data</th><th>Usuário</th><th>Campo Alterado</th><th>Valor Antigo</th><th>Valor Novo</th><th>Op.</th></tr></thead><tbody>${tableRows}</tbody></table></div>`;
    }

    const tableRows = historicoData
      .map(
        (log) => `
      <tr>
        <td>${formatarData(log.data_alteracao_historico)}</td>
        <td>${log.usuario_re_historico || ""} – ${log.usuario_nome_historico || "—"}</td>
        <td>${log.valor_novo_historico || "—"}</td>
      </tr>
    `
      )
      .join("");

    return `<div class="table-responsive"><table class="table table-sm table-striped table-hover mb-0"><thead><tr><th>Data</th><th>Usuário</th><th>Informação</th></tr></thead><tbody>${tableRows}</tbody></table></div>`;
  }

  function renderHistoricoCompleto(payload, isAdmin) {
    if (!payload) {
      return '<div class="text-muted ms-2 mt-2">Nenhum histórico encontrado.</div>';
    }

    const uid = "ph" + Date.now();
    const histAt = payload.historico_atendimento || payload.dados || [];
    const histObs =
      payload.historico_observacao ||
      (payload.eventos_relacionados || []).filter((h) => {
        const c = (h.campo_alterado_historico || "").trim();
        return c === "Observação" || c === "Observacao";
      });

    const panels = [
      {
        id: "atendimento",
        title: "Histórico do atendimento",
        html: renderHistorico(histAt, isAdmin),
        open: historicoSectionExpanded("atendimento", true),
      },
      {
        id: "unidade",
        title: "Histórico da unidade",
        html: renderHistorico(payload.historico_unidade || [], isAdmin),
        open: historicoSectionExpanded("unidade", false),
      },
      {
        id: "observacao",
        title: "Historico Observação",
        html: renderHistorico(histObs, isAdmin),
        open: historicoSectionExpanded("observacao", true),
      },
      {
        id: "equipamento",
        title: "Historico Equipamento",
        html: renderHistorico(payload.historico_equipamentos || [], isAdmin),
        open: historicoSectionExpanded("equipamento", false),
      },
      {
        id: "links",
        title: "Historico Links",
        html: renderHistorico(payload.historico_links || [], isAdmin),
        open: historicoSectionExpanded("links", false),
      },
    ];

    const accordionBody = panels
      .map((p) => prodespHistoricoAccordionPanel(uid, p.id, p.title, p.html, p.open))
      .join("");

    return (
      `<div class="prodesp-historico-view" data-historico-root="${uid}">` +
      `<div class="d-flex flex-wrap gap-2 mb-2">` +
      `<button type="button" class="btn btn-sm btn-outline-secondary" data-hist-action="expand-all" data-hist-root="${uid}">Expandir todos</button>` +
      `<button type="button" class="btn btn-sm btn-outline-secondary" data-hist-action="collapse-all" data-hist-root="${uid}">Recolher todos</button>` +
      `</div>` +
      `<div class="accordion prodesp-historico-accordion" id="${uid}-accordion">${accordionBody}</div>` +
      `</div>`
    );
  }

  function prodespBindHistoricoCollapseControls(container) {
    const root =
      typeof container === "string"
        ? document.querySelector(container)
        : container;
    if (!root) return;

    const wrap = root.querySelector(".prodesp-historico-view") || root;
    const accordion = wrap.querySelector(".prodesp-historico-accordion");
    if (!accordion) return;

    const setAll = (show) => {
      accordion.querySelectorAll(".accordion-collapse").forEach((el) => {
        const inst = bootstrap.Collapse.getOrCreateInstance(el, { toggle: false });
        if (show) inst.show();
        else inst.hide();
        const sectionId = el.getAttribute("data-hist-section");
        if (sectionId) saveHistoricoSectionPref(sectionId, show);
      });
      accordion.querySelectorAll(".accordion-button").forEach((btn) => {
        btn.classList.toggle("collapsed", !show);
        btn.setAttribute("aria-expanded", show ? "true" : "false");
      });
    };

    wrap.querySelectorAll('[data-hist-action="expand-all"]').forEach((btn) => {
      btn.onclick = () => setAll(true);
    });
    wrap.querySelectorAll('[data-hist-action="collapse-all"]').forEach((btn) => {
      btn.onclick = () => setAll(false);
    });

    accordion.querySelectorAll(".accordion-collapse[data-hist-section]").forEach((el) => {
      const sectionId = el.getAttribute("data-hist-section");
      if (!sectionId) return;
      el.addEventListener("shown.bs.collapse", () => saveHistoricoSectionPref(sectionId, true));
      el.addEventListener("hidden.bs.collapse", () => saveHistoricoSectionPref(sectionId, false));
    });
  }

  window.renderHistorico = renderHistorico;
  window.renderHistoricoCompleto = renderHistoricoCompleto;
  window.prodespBindHistoricoCollapseControls = prodespBindHistoricoCollapseControls;
})();
