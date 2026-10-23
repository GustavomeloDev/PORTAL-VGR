/**
 * Motivos fora do padrão — compartilhado entre fila de atendimentos e gestão/dashboard.
 * Deve ser carregado antes de script_atendimentos_prodesp.js.
 */
(function (global) {
  "use strict";

  let motivosForaPadraoCache = [];

  function prodespMotivosAttrEsc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function getMotivosContainer(context) {
    return document.getElementById(
      context === "edit" ? "motivos-container-edit" : "motivos-container-create"
    );
  }

  function limparMotivosSelecionados(context) {
    const container = getMotivosContainer(context);
    if (!container) return;
    container.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.checked = false;
    });
  }

  function coletarMotivosSelecionados(context) {
    const container = getMotivosContainer(context);
    if (!container) return [];
    return Array.from(container.querySelectorAll('input[type="checkbox"]:checked'))
      .map((cb) => parseInt(cb.value, 10))
      .filter(Number.isFinite);
  }

  function arraysIguaisNumeros(a, b) {
    const arrA = [...(a || [])].map(Number).filter(Number.isFinite).sort((x, y) => x - y);
    const arrB = [...(b || [])].map(Number).filter(Number.isFinite).sort((x, y) => x - y);
    if (arrA.length !== arrB.length) return false;
    return arrA.every((val, idx) => val === arrB[idx]);
  }

  function renderMotivosView(container, motivos) {
    if (!container) return;
    container.innerHTML = "";

    if (!motivos || motivos.length === 0) {
      container.innerHTML = '<div class="text-muted small">Nenhum motivo informado.</div>';
      return;
    }

    const motivosPorCategoria = motivos.reduce((acc, item) => {
      const categoria = (item.categoria || "Sem categoria").trim();
      if (!acc[categoria]) acc[categoria] = [];
      acc[categoria].push(item);
      return acc;
    }, {});

    const accordionId = `${container.id}-accordion`;
    const accordion = document.createElement("div");
    accordion.className = "accordion accordion-flush motivos-accordion";
    accordion.id = accordionId;

    Object.keys(motivosPorCategoria).sort().forEach((categoria, index) => {
      const categoryItems = motivosPorCategoria[categoria];
      const item = document.createElement("div");
      item.className = "accordion-item border rounded mb-2 shadow-sm";

      const headerId = `${accordionId}-heading-${index}`;
      const collapseId = `${accordionId}-collapse-${index}`;

      item.innerHTML = `
        <h2 class="accordion-header" id="${headerId}">
          <button class="accordion-button ${index === 0 ? "" : "collapsed"} py-2" type="button" data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="${index === 0 ? "true" : "false"}" aria-controls="${collapseId}">
            <span class="fw-semibold">${prodespMotivosAttrEsc(categoria)}</span>
            <span class="badge text-bg-secondary ms-2">${categoryItems.length}</span>
          </button>
        </h2>
        <div id="${collapseId}" class="accordion-collapse collapse ${index === 0 ? "show" : ""}" aria-labelledby="${headerId}" data-bs-parent="#${accordionId}">
          <div class="accordion-body py-2">
            <div class="d-flex flex-wrap gap-2"></div>
          </div>
        </div>
      `;

      const chips = item.querySelector(".d-flex.flex-wrap");
      categoryItems.forEach((motivo) => {
        const badge = document.createElement("span");
        badge.className = "badge text-bg-light border text-dark px-3 py-2 rounded-pill";
        badge.textContent = motivo.descricao || "";
        chips.appendChild(badge);
      });

      accordion.appendChild(item);
    });

    container.appendChild(accordion);
  }

  function renderMotivosForaPadrao(context, motivos, selecionados = []) {
    const container = getMotivosContainer(context);
    if (!container) return;

    container.innerHTML = "";
    const selecionadosSet = new Set((selecionados || []).map((id) => parseInt(id, 10)));

    if (!motivos || motivos.length === 0) {
      container.innerHTML =
        '<div class="col-12"><div class="text-muted small">Nenhum motivo cadastrado.</div></div>';
      return;
    }

    const motivosPorCategoria = motivos.reduce((acc, item) => {
      const categoria = (item.categoria || "Sem categoria").trim();
      if (!acc[categoria]) acc[categoria] = [];
      acc[categoria].push(item);
      return acc;
    }, {});
    const hasAnySelected = (selecionados || []).some((id) => Number.isFinite(parseInt(id, 10)));
    const totalSelected = [...selecionadosSet].length;

    const summary = document.createElement("div");
    summary.className = "d-flex align-items-center justify-content-between mb-2 px-1";
    summary.innerHTML = `
      <div class="small text-muted">Selecione um ou mais motivos.</div>
      <span class="badge text-bg-success motivos-total-selected-badge">${totalSelected} selecionados</span>
    `;
    container.appendChild(summary);

    const accordionId = `${context}-motivos-accordion`;
    const accordion = document.createElement("div");
    accordion.className = "accordion motivos-accordion";
    accordion.id = accordionId;

    Object.keys(motivosPorCategoria).sort().forEach((categoria, index) => {
      const categoryItems = motivosPorCategoria[categoria];
      const selectedCount = categoryItems.filter((motivo) =>
        selecionadosSet.has(parseInt(motivo.id, 10))
      ).length;
      const shouldExpand = selectedCount > 0 || (!hasAnySelected && index === 0);
      const item = document.createElement("div");
      item.className = "accordion-item border rounded mb-2 shadow-sm";
      if (selectedCount > 0) item.classList.add("motivos-selected");

      const headerId = `${accordionId}-heading-${index}`;
      const collapseId = `${accordionId}-collapse-${index}`;

      item.innerHTML = `
        <h2 class="accordion-header" id="${headerId}">
          <button class="accordion-button ${index === 0 ? "" : "collapsed"} py-2" type="button" data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="${index === 0 ? "true" : "false"}" aria-controls="${collapseId}">
            <span class="fw-semibold">${prodespMotivosAttrEsc(categoria)}</span>
            <span class="badge text-bg-${selectedCount > 0 ? "success" : "secondary"} ms-2 motivos-selection-badge">${selectedCount}/${categoryItems.length}</span>
          </button>
        </h2>
        <div id="${collapseId}" class="accordion-collapse collapse ${shouldExpand ? "show" : ""}" aria-labelledby="${headerId}" data-bs-parent="#${accordionId}">
          <div class="accordion-body py-2">
            <div class="row row-cols-1 row-cols-md-2 row-cols-xl-3 g-2"></div>
          </div>
        </div>
      `;

      const grid = item.querySelector(".row");
      categoryItems.forEach((motivo) => {
        const col = document.createElement("div");
        col.className = "col";

        const wrapper = document.createElement("label");
        wrapper.className =
          "form-check border rounded p-2 h-100 d-flex align-items-start gap-2 bg-white motivos-option";
        wrapper.setAttribute("for", `${context}-motivo-${motivo.id}`);

        const input = document.createElement("input");
        input.className = "form-check-input mt-1";
        input.type = "checkbox";
        input.id = `${context}-motivo-${motivo.id}`;
        input.value = motivo.id;
        input.checked = selecionadosSet.has(parseInt(motivo.id, 10));

        const text = document.createElement("span");
        text.className = "fw-medium small";
        text.textContent = motivo.descricao || "";

        wrapper.prepend(input);
        wrapper.appendChild(text);
        col.appendChild(wrapper);
        grid.appendChild(col);
      });

      accordion.appendChild(item);
    });

    container.appendChild(accordion);

    const updateSummary = () => {
      const currentTotalSelected = container.querySelectorAll('input[type="checkbox"]:checked').length;
      const summaryBadge = container.querySelector(".motivos-total-selected-badge");
      if (summaryBadge) summaryBadge.textContent = `${currentTotalSelected} selecionados`;

      container.querySelectorAll(".accordion-item").forEach((section) => {
        const total = section.querySelectorAll('input[type="checkbox"]').length;
        const selected = section.querySelectorAll('input[type="checkbox"]:checked').length;
        const badge = section.querySelector(".motivos-selection-badge");
        if (badge) {
          badge.textContent = `${selected}/${total}`;
          badge.classList.remove("text-bg-secondary", "text-bg-success");
          badge.classList.add(selected > 0 ? "text-bg-success" : "text-bg-secondary");
        }
        section.classList.toggle("motivos-selected", selected > 0);
      });
    };

    container.onchange = updateSummary;
    updateSummary();
  }

  async function carregarMotivosForaPadrao(context) {
    if (!motivosForaPadraoCache.length) {
      const response = await fetch("/prodesp/api/motivos_fora_padrao");
      if (!response.ok) {
        throw new Error("Não foi possível carregar os motivos fora do padrão.");
      }
      motivosForaPadraoCache = await response.json();
    }
    renderMotivosForaPadrao(context, motivosForaPadraoCache, []);
  }

  async function marcarMotivosAtendimento(context, idAtendimento) {
    const response = await fetch(`/prodesp/api/atendimento/${idAtendimento}/motivos`);
    if (!response.ok) {
      throw new Error("Não foi possível carregar os motivos do atendimento.");
    }
    const selecionados = await response.json();
    renderMotivosForaPadrao(context, motivosForaPadraoCache, selecionados);
    return selecionados;
  }

  global.arraysIguaisNumeros = arraysIguaisNumeros;
  global.renderMotivosView = renderMotivosView;
  global.limparMotivosSelecionados = limparMotivosSelecionados;
  global.coletarMotivosSelecionados = coletarMotivosSelecionados;
  global.carregarMotivosForaPadrao = carregarMotivosForaPadrao;
  global.marcarMotivosAtendimento = marcarMotivosAtendimento;
  global.renderMotivosForaPadrao = renderMotivosForaPadrao;
})(window);
