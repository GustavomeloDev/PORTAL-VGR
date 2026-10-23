/**
 * Admin PRODESP — inventário de links (PortalDt + KPIs + contexto + campos por tipo).
 */
(function () {
  "use strict";

  const AI = window.AdminInv;
  if (!AI) {
    console.error("AdminInv comum não carregado");
    return;
  }

  function acoesHtml(id, idUnidade) {
    const uidAttr =
      idUnidade != null && idUnidade !== ""
        ? ' data-id-unidade="' + AI.esc(String(idUnidade)) + '"'
        : ' data-id-unidade=""';
    return (
      '<span class="portal-dt-acoes-inner">' +
      '<button type="button" class="btn-icon text-info admin-lk-view" data-id="' +
      id +
      '"' +
      uidAttr +
      ' title="Ver contexto"><i class="fa-solid fa-eye"></i></button>' +
      '<button type="button" class="btn-icon text-primary admin-lk-edit" data-id="' +
      id +
      '"' +
      uidAttr +
      ' title="Editar"><i class="fa-solid fa-pen"></i></button>' +
      '<button type="button" class="btn-icon text-warning admin-lk-xfer" data-id="' +
      id +
      '"' +
      uidAttr +
      ' title="Transferir"><i class="fa-solid fa-right-left"></i></button>' +
      '<button type="button" class="btn-icon text-secondary admin-lk-unlink" data-id="' +
      id +
      '"' +
      uidAttr +
      ' title="Desassociar"><i class="fa-solid fa-link-slash"></i></button>' +
      '<button type="button" class="btn-icon text-danger admin-lk-del" data-id="' +
      id +
      '" title="Excluir"><i class="fa-solid fa-trash"></i></button>' +
      "</span>"
    );
  }

  let api = null;
  let modalLk = null;
  let modalXfer = null;
  let kpiApi = null;
  let modalMode = "create";
  const ajaxState = {
    revision: null,
    cacheKey: "prodesp.admin.links.v16",
    kind: "links",
  };

  function reload(forceFull) {
    if (forceFull) {
      ajaxState.revision = null;
      ajaxState.bustCache = true;
    }
    if (api) api.ajax.reload(null, false);
  }

  let linkTypeCtrl = null;
  let rcCtrl = null;
  let vivoCtrl = null;
  let linkValCtrl = null;

  function appliesRc() {
    const tipo = (document.getElementById("adminLkTipo").value || "").trim().toUpperCase();
    const op = (document.getElementById("adminLkOperadora").value || "").trim().toUpperCase();
    return tipo === "MPLS" && op === "VIVO";
  }

  function paintLkLiveValidation() {
    if (!window.ProdespLiveValidation) return;
    if (ProdespLiveValidation.refreshFormAfterDataLoad) {
      ProdespLiveValidation.refreshFormAfterDataLoad({
        adminLinkController: linkValCtrl,
        vivoLinkController: vivoCtrl,
        velocityEl: document.getElementById("adminLkVelocidade"),
      });
      return;
    }
    if (linkValCtrl && linkValCtrl.paintLocal) linkValCtrl.paintLocal();
    else if (linkValCtrl && linkValCtrl.refresh) linkValCtrl.refresh();
    if (vivoCtrl && vivoCtrl.validate) vivoCtrl.validate();
    else if (vivoCtrl && vivoCtrl.refresh) vivoCtrl.refresh(false);
  }

  function schedulePaintLkLiveValidation() {
    setTimeout(function () {
      paintLkLiveValidation();
      requestAnimationFrame(function () {
        paintLkLiveValidation();
      });
    }, 0);
  }

  function refreshLinkFieldVisibility() {
    if (linkTypeCtrl) linkTypeCtrl.refresh();
    if (rcCtrl && typeof rcCtrl.refresh === "function") rcCtrl.refresh();
    if (linkTypeCtrl) linkTypeCtrl.refresh();
  }

  function setFooterMode(mode, hasUnit) {
    modalMode = mode;
    const btnSave = document.getElementById("btnAdminLkSalvar");
    const btnCancel = document.getElementById("btnAdminLkCancel");
    const btnXfer = document.getElementById("btnAdminLkFooterXfer");
    const btnUnlink = document.getElementById("btnAdminLkFooterUnlink");
    const isCreate = mode === "create";
    const isEdit = mode === "edit";
    const isView = mode === "view";
    if (btnSave) btnSave.classList.toggle("d-none", isView);
    if (btnCancel) btnCancel.textContent = isView ? "Fechar" : "Cancelar";
    if (btnXfer) btnXfer.classList.toggle("d-none", isCreate);
    if (btnUnlink) btnUnlink.classList.toggle("d-none", !isEdit || !hasUnit);
    AI.applyModalMode(document.getElementById("modalAdminLk"), mode);
    refreshLinkFieldVisibility();
  }

  function paintSummary(d, ctx) {
    d = d || {};
    const u = (ctx && ctx.unidade) || null;
    const link = (ctx && ctx.link) || {};
    const badges = [];
    if (d.id_unidade || (u && u.id_unidade) || d.id_vgr) {
      badges.push({ label: "Associado", tone: "bg-success" });
    } else if (d.id) {
      badges.push({ label: "Órfão", tone: "bg-danger" });
    }
    const rc = Number(d.redundante_critico != null ? d.redundante_critico : link.redundante_critico);
    if (rc === 1) badges.push({ label: "RC", tone: "bg-warning text-dark" });
    const fora = Number(d.id_vgr_fora_padrao != null ? d.id_vgr_fora_padrao : link.id_vgr_fora_padrao);
    if (fora === 1) badges.push({ label: "ID VGR fora", tone: "bg-danger" });
    const desFora = Number(
      d.designador_fora_padrao != null ? d.designador_fora_padrao : link.designador_fora_padrao
    );
    if (desFora === 1) badges.push({ label: "Designador fora", tone: "bg-danger" });
    const lines = [];
    if (d.id) lines.push("#" + d.id);
    const tipo = d.tipo || link.tipo;
    if (tipo) lines.push(tipo);
    const op = d.operadora || link.operadora;
    if (op) lines.push(op);
    const vgr = d.id_vgr || (u && u.id_vgr) || "";
    if (vgr) lines.push("VGR " + vgr);
    if (u && u.acronimo) lines.push(u.acronimo);
    else if (d.acronimo) lines.push(d.acronimo);
    AI.renderSummaryStrip(document.getElementById("adminLkSummary"), {
      lines: lines,
      badges: badges,
    });
  }

  function resetContextPanels() {
    document.getElementById("adminLkContexto").innerHTML =
      '<em class="text-muted">Contexto aparece ao editar/visualizar ou ao escolher a unidade na criação.</em>';
    document.getElementById("adminLkAtivos").innerHTML =
      '<em class="text-muted">Ativos da unidade aparecem ao carregar o contexto.</em>';
  }

  function showDadosTab() {
    const btn = document.getElementById("adminLkTabDadosBtn");
    if (btn && window.bootstrap && bootstrap.Tab) {
      bootstrap.Tab.getOrCreateInstance(btn).show();
    }
  }

  async function previewUnidadeFromVgr(vgr) {
    const ctxEl = document.getElementById("adminLkContexto");
    const ativosEl = document.getElementById("adminLkAtivos");
    ctxEl.innerHTML = '<em class="text-muted">Carregando preview da unidade…</em>';
    ativosEl.innerHTML = '<em class="text-muted">Carregando…</em>';
    const d = await AI.loadUnidadeContextoByVgr(vgr);
    if (!d) {
      ctxEl.innerHTML = '<em class="text-danger">Unidade não encontrada para preview.</em>';
      ativosEl.innerHTML = '<em class="text-muted">—</em>';
      return;
    }
    AI.fillContextTabs(ctxEl, ativosEl, d);
  }

  function clearForm() {
    document.getElementById("adminLkId").value = "";
    document.getElementById("adminLkIdUnidade").value = "";
    document.getElementById("adminLkIdVgr").value = "";
    document.getElementById("adminLkHostname").value = "";
    document.getElementById("adminLkTipo").value = "";
    document.getElementById("adminLkOperadora").value = "";
    document.getElementById("adminLkDesignador").value = "";
    document.getElementById("adminLkIdVgrLink").value = "";
    document.getElementById("adminLkIpWan").value = "";
    document.getElementById("adminLkIpGateway").value = "";
    document.getElementById("adminLkIpMascara").value = "";
    document.getElementById("adminLkVlan").value = "";
    document.getElementById("adminLkVelocidade").value = "";
    document.getElementById("adminLkRc").checked = false;
    document.getElementById("adminLkPppoeUser").value = "";
    document.getElementById("adminLkPppoePass").value = "";
    resetContextPanels();
    AI.renderSummaryStrip(document.getElementById("adminLkSummary"), { lines: [], badges: [] });
    refreshLinkFieldVisibility();
  }

  function fillForm(d) {
    document.getElementById("adminLkId").value = d.id || "";
    document.getElementById("adminLkIdUnidade").value =
      d.id_unidade != null && d.id_unidade !== "" ? String(d.id_unidade) : "";
    document.getElementById("adminLkIdVgr").value = d.id_vgr || "";
    document.getElementById("adminLkHostname").value = d.hostname || "";
    document.getElementById("adminLkTipo").value = d.tipo || "";
    document.getElementById("adminLkOperadora").value = d.operadora || "";
    document.getElementById("adminLkDesignador").value = d.designador || "";
    document.getElementById("adminLkIdVgrLink").value = d.id_vgr_link || "";
    document.getElementById("adminLkIpWan").value = d.ip_wan || "";
    document.getElementById("adminLkIpGateway").value = d.ip_gateway || "";
    document.getElementById("adminLkIpMascara").value = d.ip_mascara || "";
    document.getElementById("adminLkVlan").value = d.vlan || "";
    document.getElementById("adminLkVelocidade").value = d.velocidade || "";
    document.getElementById("adminLkRc").checked = !!Number(d.redundante_critico);
    document.getElementById("adminLkPppoeUser").value = d.pppoe_user || "";
    document.getElementById("adminLkPppoePass").value = "";
    document.getElementById("adminLkPppoePass").placeholder = d.pppoe_pass_set
      ? "deixe vazio para manter"
      : "senha";
    refreshLinkFieldVisibility();
    paintLkLiveValidation();
  }

  async function loadContexto(id, baseData) {
    const ctxEl = document.getElementById("adminLkContexto");
    const ativosEl = document.getElementById("adminLkAtivos");
    ctxEl.innerHTML = '<em class="text-muted">Carregando contexto…</em>';
    ativosEl.innerHTML = '<em class="text-muted">Carregando…</em>';
    try {
      const { status, d } = await AI.jsonFetch("/prodesp/api/admin/links/" + id + "/contexto");
      if (status >= 400 || !d || !d.success) {
        ctxEl.innerHTML =
          '<em class="text-danger">' + AI.esc((d && d.message) || "Falha ao carregar.") + "</em>";
        ativosEl.innerHTML = '<em class="text-muted">—</em>';
        return;
      }
      AI.fillContextTabs(ctxEl, ativosEl, d);
      paintSummary(Object.assign({}, baseData || {}, d.link || {}), d);
      const hasUnit = !!(d.unidade && d.unidade.id_unidade);
      if (modalMode === "edit") setFooterMode("edit", hasUnit);
    } catch (_e) {
      ctxEl.innerHTML = '<em class="text-danger">Falha de rede no contexto.</em>';
      ativosEl.innerHTML = '<em class="text-muted">—</em>';
    }
  }

  function openTransfer(id, expectedUid) {
    document.getElementById("adminLkTransferId").value = id;
    document.getElementById("adminLkTransferExpectedUid").value =
      expectedUid != null && expectedUid !== "" ? String(expectedUid) : "";
    document.getElementById("adminLkTransferVgr").value = "";
    document.getElementById("adminLkTransferHost").textContent = "";
    document.getElementById("adminLkTransferInfo").textContent = "Link #" + id;
    modalXfer.show();
  }

  async function doUnlink(id, expectedUid) {
    if (!window.confirm("Desassociar link #" + id + " da unidade?")) return;
    const body = {
      expected_id_unidade:
        expectedUid != null && expectedUid !== "" ? Number(expectedUid) : null,
    };
    const { status, d } = await AI.jsonFetch("/prodesp/api/admin/links/" + id + "/desassociar", {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (status >= 400 || !d.success) {
      AI.toast((d && d.message) || "Falha ao desassociar.", false);
      if (status === 409) reload(true);
      return;
    }
    AI.toast(d.message || "Desassociado.", true);
    modalLk.hide();
    reload(true);
  }

  let openEditSeq = 0;

  function openEdit(id, viewOnly) {
    const seq = ++openEditSeq;
    const formRoot = document.getElementById("adminLkFormRoot");
    const btnSave = document.getElementById("btnAdminLkSalvar");
    clearForm();
    document.getElementById("adminLkId").value = id || "";
    document.getElementById("modalAdminLkTitle").textContent =
      (viewOnly ? "Visualizar" : "Editar") + " link #" + id + "…";
    setFooterMode(viewOnly ? "view" : "edit", false);
    if (btnSave) btnSave.disabled = true;
    if (formRoot) formRoot.classList.add("opacity-50", "pe-none");
    paintSummary({ id: id }, null);
    showDadosTab();
    document.getElementById("adminLkContexto").innerHTML =
      '<em class="text-muted">Carregando contexto…</em>';
    document.getElementById("adminLkAtivos").innerHTML =
      '<em class="text-muted">Carregando…</em>';
    modalLk.show();

    AI.jsonFetch("/prodesp/api/admin/links/" + encodeURIComponent(id))
      .then(function (res) {
        if (seq !== openEditSeq) return;
        if (formRoot) formRoot.classList.remove("opacity-50", "pe-none");
        if (btnSave) btnSave.disabled = !!viewOnly;
        if (res.status >= 400 || !res.d || res.d.success === false) {
          AI.toast((res.d && res.d.message) || "Não encontrado.", false);
          modalLk.hide();
          return;
        }
        const data = res.d.data || {};
        try {
          fillForm(data);
          document.getElementById("modalAdminLkTitle").textContent =
            (viewOnly ? "Visualizar" : "Editar") + " link #" + id;
          const hasUnit = !!(data.id_vgr || data.id_unidade);
          setFooterMode(viewOnly ? "view" : "edit", hasUnit);
          paintSummary(data, null);
          showDadosTab();
          schedulePaintLkLiveValidation();
          loadContexto(id, data);
        } catch (_e) {
          AI.toast("Falha ao montar o formulário do link.", false);
        }
      })
      .catch(function () {
        if (seq !== openEditSeq) return;
        if (formRoot) formRoot.classList.remove("opacity-50", "pe-none");
        if (btnSave) btnSave.disabled = false;
        AI.toast("Falha de rede ao abrir o link.", false);
        modalLk.hide();
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    modalLk = new bootstrap.Modal(document.getElementById("modalAdminLk"));
    modalXfer = new bootstrap.Modal(document.getElementById("modalAdminLkTransfer"));

    AI.bindUnitTypeahead(document.getElementById("adminLkIdVgr"), {
      hostInputId: "adminLkHostname",
      onSelect: function (it) {
        if (modalMode === "create" && it && it.id_vgr) {
          previewUnidadeFromVgr(it.id_vgr);
        }
      },
    });
    AI.bindUnitTypeahead(document.getElementById("adminLkTransferVgr"), {
      onSelect: function (it) {
        document.getElementById("adminLkTransferHost").textContent =
          (it.hostname || "") + (it.nome ? " · " + it.nome : "");
      },
    });
    linkTypeCtrl = AI.bindLinkTypeFields(
      "adminLkTipo",
      document.getElementById("adminLkFormRoot"),
      "adminLkOperadora"
    );

    if (window.ProdespLiveValidation) {
      const root = document.getElementById("adminLkFormRoot");
      if (root) {
        root.querySelectorAll(".prodesp-ip-plain-only").forEach(function (el) {
          if (ProdespLiveValidation.bindPlainIpv4Input) ProdespLiveValidation.bindPlainIpv4Input(el);
        });
        root.querySelectorAll(".prodesp-no-space-input").forEach(function (el) {
          if (ProdespLiveValidation.bindNoWhitespaceInput) ProdespLiveValidation.bindNoWhitespaceInput(el);
        });
        if (ProdespLiveValidation.bindAllVelocityMbpsInputs) {
          ProdespLiveValidation.bindAllVelocityMbpsInputs(root);
        }
        if (ProdespLiveValidation.initVivoLinkAutoFill) {
          vivoCtrl = ProdespLiveValidation.initVivoLinkAutoFill(
            document.getElementById("adminLkIpWan"),
            document.getElementById("adminLkIpGateway"),
            document.getElementById("adminLkIpMascara"),
            document.getElementById("adminLkOperadora"),
            {
              tipoEl: document.getElementById("adminLkTipo"),
              getLinkTipo: function () {
                return document.getElementById("adminLkTipo").value || "STATIC";
              },
              label: "Link admin",
              redundanteCritico: function () {
                return appliesRc() && document.getElementById("adminLkRc").checked;
              },
              onAfterApply: function () {
                if (linkValCtrl && linkValCtrl.paintLocal) linkValCtrl.paintLocal();
              },
            }
          );
        }
        if (ProdespLiveValidation.initRedundanteCriticoMplsVivo) {
          rcCtrl = ProdespLiveValidation.initRedundanteCriticoMplsVivo({
            wanEl: document.getElementById("adminLkIpWan"),
            checkboxEl: document.getElementById("adminLkRc"),
            wrapperEl: document.getElementById("adminLkRcWrap"),
            tipoEl: document.getElementById("adminLkTipo"),
            operadoraEl: document.getElementById("adminLkOperadora"),
            onAfterApply: function () {
              if (vivoCtrl && vivoCtrl.apply) vivoCtrl.apply("wan");
              else if (vivoCtrl && vivoCtrl.validate) vivoCtrl.validate();
              paintLkLiveValidation();
            },
          });
          refreshLinkFieldVisibility();
        }
        if (ProdespLiveValidation.initAdminLinkFormValidation) {
          linkValCtrl = ProdespLiveValidation.initAdminLinkFormValidation({
            getIdUnidade: function () {
              return document.getElementById("adminLkIdUnidade").value.trim();
            },
            getLinkId: function () {
              return document.getElementById("adminLkId").value.trim();
            },
            redundanteCritico: function () {
              return appliesRc() && document.getElementById("adminLkRc").checked;
            },
            fields: {
              tipo: document.getElementById("adminLkTipo"),
              operadora: document.getElementById("adminLkOperadora"),
              designador: document.getElementById("adminLkDesignador"),
              idVgr: document.getElementById("adminLkIdVgrLink"),
              wan: document.getElementById("adminLkIpWan"),
              gw: document.getElementById("adminLkIpGateway"),
              mascara: document.getElementById("adminLkIpMascara"),
              velocidade: document.getElementById("adminLkVelocidade"),
            },
          });
        }
      }
    }

    const modalLkEl = document.getElementById("modalAdminLk");
    if (modalLkEl) {
      modalLkEl.addEventListener("shown.bs.modal", function () {
        if (document.getElementById("adminLkId").value.trim()) {
          schedulePaintLkLiveValidation();
        }
      });
    }

    function tipoEq(t) {
      return function (r) {
        return String(r.tipo || "").toUpperCase() === t;
      };
    }

    /* KPIs antes do DataTable — layout visível durante o ajax */
    function foraVgr(r) {
      return Number(r.id_vgr_fora_padrao) === 1;
    }
    function foraDes(r) {
      return Number(r.designador_fora_padrao) === 1;
    }
    kpiApi = AI.mountKpis("adminLkKpis", null, [
      {
        key: "all",
        label: "Total",
        hint: "Limpar filtro",
        featured: true,
        color: "#6c757d",
        icon: "fa-layer-group",
        iconTone: "secondary",
        test: null,
      },
      {
        key: "assoc",
        section: "Inventário",
        label: "Associados",
        hint: "Com unidade",
        color: "#198754",
        icon: "fa-link",
        iconTone: "success",
        test: function (r) {
          return Number(r.associado) === 1;
        },
      },
      {
        key: "orfao",
        section: "Inventário",
        label: "Órfãos",
        hint: "Sem unidade",
        color: "#dc3545",
        icon: "fa-unlink",
        iconTone: "danger",
        test: function (r) {
          return Number(r.associado) !== 1;
        },
      },
      {
        key: "static",
        section: "Inventário",
        label: "STATIC",
        color: "#0d6efd",
        icon: "fa-network-wired",
        iconTone: "primary",
        test: tipoEq("STATIC"),
      },
      {
        key: "pppoe",
        section: "Inventário",
        label: "PPPoE",
        color: "#6610f2",
        icon: "fa-key",
        iconTone: "info",
        test: tipoEq("PPPOE"),
      },
      {
        key: "mpls",
        section: "Inventário",
        label: "MPLS",
        color: "#20c997",
        icon: "fa-project-diagram",
        iconTone: "success",
        test: tipoEq("MPLS"),
      },
      {
        key: "rc",
        section: "Inventário",
        label: "RC",
        hint: "Redundante crítico",
        color: "#fd7e14",
        icon: "fa-shield-alt",
        iconTone: "warning",
        test: function (r) {
          return Number(r.redundante_critico) === 1;
        },
      },
      {
        key: "sem_wan",
        section: "Inventário",
        label: "Sem IP WAN",
        color: "#6f42c1",
        icon: "fa-globe",
        iconTone: "secondary",
        test: function (r) {
          return !String(r.ip_wan || "").trim();
        },
      },
      {
        key: "vgr_out",
        section: "Fora do padrão",
        label: "ID VGR fora",
        hint: "Não numérico / <7 dígitos",
        color: "#dc3545",
        icon: "fa-exclamation-circle",
        iconTone: "danger",
        test: foraVgr,
      },
      {
        key: "vgr_out_cob",
        section: "Fora do padrão",
        label: "VGR fora · Concluído",
        hint: "Concluído / Parcial — cobrar",
        color: "#198754",
        icon: "fa-clipboard-check",
        iconTone: "success",
        test: function (r) {
          return foraVgr(r) && AI.statusIsCobranca(r.status_ultimo_atendimento);
        },
      },
      {
        key: "vgr_out_atend",
        section: "Fora do padrão",
        label: "VGR fora · Em Atend.",
        hint: "Corrigir até o final",
        color: "#0d6efd",
        icon: "fa-spinner",
        iconTone: "primary",
        test: function (r) {
          return foraVgr(r) && AI.statusIsEmAtendimento(r.status_ultimo_atendimento);
        },
      },
      {
        key: "vgr_out_quebra",
        section: "Fora do padrão",
        label: "VGR fora · Quebra",
        hint: "Atenção (novo atend. virá)",
        color: "#fd7e14",
        icon: "fa-exclamation-triangle",
        iconTone: "warning",
        test: function (r) {
          return foraVgr(r) && AI.statusIsQuebra(r.status_ultimo_atendimento);
        },
      },
      {
        key: "des_out",
        section: "Fora do padrão",
        label: "Designador fora",
        hint: "VIVO · não numérico / <15",
        color: "#dc3545",
        icon: "fa-barcode",
        iconTone: "danger",
        test: foraDes,
      },
      {
        key: "des_out_cob",
        section: "Fora do padrão",
        label: "Des. fora · Concluído",
        hint: "VIVO · Concluído/Parcial — cobrar",
        color: "#198754",
        icon: "fa-clipboard-check",
        iconTone: "success",
        test: function (r) {
          return foraDes(r) && AI.statusIsCobranca(r.status_ultimo_atendimento);
        },
      },
      {
        key: "des_out_atend",
        section: "Fora do padrão",
        label: "Des. fora · Em Atend.",
        hint: "VIVO · corrigir até o final",
        color: "#0d6efd",
        icon: "fa-spinner",
        iconTone: "primary",
        test: function (r) {
          return foraDes(r) && AI.statusIsEmAtendimento(r.status_ultimo_atendimento);
        },
      },
      {
        key: "des_out_quebra",
        section: "Fora do padrão",
        label: "Des. fora · Quebra",
        hint: "VIVO · atenção (novo atend.)",
        color: "#fd7e14",
        icon: "fa-exclamation-triangle",
        iconTone: "warning",
        test: function (r) {
          return foraDes(r) && AI.statusIsQuebra(r.status_ultimo_atendimento);
        },
      },
    ]);

    /* 1 tick: browser pinta KPIs (0) antes do init pesado do DataTables/CC. */
    setTimeout(function () {
    api = $("#tblAdminLinks").DataTable({
      serverSide: false,
      processing: false,
      deferRender: true,
      pageLength: 25,
      autoWidth: false,
      order: [[0, "desc"]],
      ordering: { indicators: false, handler: false },
      ajax: AI.clientAjax("/prodesp/api/admin/links", ajaxState),
      columns: [
        { data: "id", title: "ID", width: "52px", className: "text-start" },
        { data: "tipo", title: "Tipo", width: "72px", className: "text-start" },
        { data: "operadora", title: "Operadora", width: "80px", className: "text-start" },
        { data: "designador", title: "Designador", width: "120px", className: "text-start" },
        { data: "id_vgr_link", title: "ID VGR Link", width: "100px", className: "text-start" },
        { data: "ip_wan", title: "IP WAN", width: "110px", className: "text-start" },
        { data: "id_vgr", title: "ID VGR Unidade", width: "100px", className: "text-start" },
        { data: "hostname", title: "Hostname", width: "170px", className: "text-start" },
        { data: "acronimo", title: "Acrônimo", width: "90px", className: "text-start" },
        {
          data: "status_ultimo_atendimento",
          title: "Status (último atend.)",
          width: "120px",
          className: "text-start",
          defaultContent: "",
          type: "string",
          render: function (d, t) {
            const s = String(d == null ? "" : d).trim();
            /* filter/sort/type: texto puro (CC searchList). display: badge. */
            if (t === "display") return AI.statusBadgeHtml(s);
            return s || "—";
          },
        },
        {
          data: "analista_caderno_ultimo",
          title: "Analista caderno (último)",
          width: "140px",
          className: "text-start",
          defaultContent: "",
          type: "string",
          render: function (d, t) {
            const s = String(d == null ? "" : d).trim();
            if (t !== "display") return s || "—";
            return s
              ? '<span class="text-break" title="' + AI.esc(s) + '">' + AI.esc(s) + "</span>"
              : "—";
          },
        },
        {
          data: "id",
          title: "Ações",
          orderable: false,
          searchable: false,
          className: "col-acoes portal-dt-acoes text-center",
          width: "188px",
          render: function (id, _t, row) {
            return acoesHtml(id, row && row.id_unidade);
          },
        },
      ],
      columnDefs: [
        {
          /* Alta cardinalidade: sem ColumnControl (acelera mount). */
          targets: [0, 3, 4, 5, 6, 7],
          columnControl: [],
        },
        {
          /* Baixa cardinalidade + Status/Analista. */
          targets: [1, 2, 8, 9, 10],
          columnControl: AI.ccSearchList(),
        },
        {
          targets: [-1],
          orderable: false,
          searchable: false,
          columnControl: [],
        },
      ],
      language: AI.dtLanguagePtBr(),
      initComplete: function () {
        AI.bindPortalDtColumnControl(this.api(), "links");
      },
    });
    if (kpiApi && typeof kpiApi.bind === "function") kpiApi.bind(api);

    if (window.PortalDtToolbar) {
      PortalDtToolbar.mount(null, {
        tableId: "tblAdminLinks",
        api: api,
        onRefresh: function () {
          reload(true);
        },
        onClearExtra: function () {
          if (kpiApi) kpiApi.clear();
        },
      });
    }

    AI.bindRevisionSync(api, ajaxState);
    AI.bindUltimoAtendimentoPageEnrich(api);

    document.getElementById("btnAdminLkNovo").addEventListener("click", function () {
      clearForm();
      document.getElementById("modalAdminLkTitle").textContent = "Novo link";
      setFooterMode("create", false);
      showDadosTab();
      modalLk.show();
    });

    document.getElementById("btnAdminLkFooterXfer").addEventListener("click", function () {
      const id = document.getElementById("adminLkId").value.trim();
      if (id) openTransfer(id, document.getElementById("adminLkIdUnidade").value);
    });
    document.getElementById("btnAdminLkFooterUnlink").addEventListener("click", function () {
      const id = document.getElementById("adminLkId").value.trim();
      if (id) doUnlink(id, document.getElementById("adminLkIdUnidade").value);
    });

    document.getElementById("btnAdminLkSalvar").addEventListener("click", async function () {
      const btn = this;
      const G = window.ProdespSubmitGuard;
      const id = document.getElementById("adminLkId").value.trim();
      const unitVgr = document.getElementById("adminLkIdVgr").value.trim();
      if (!id && !unitVgr) {
        AI.toast("Informe o ID VGR da unidade.", false);
        if (G) G.unlock(btn);
        return;
      }
      const fields = {
        tipo: document.getElementById("adminLkTipo").value.trim(),
        operadora: document.getElementById("adminLkOperadora").value.trim(),
        designador: document.getElementById("adminLkDesignador").value.trim(),
        id_vgr: document.getElementById("adminLkIdVgrLink").value.trim(),
        ip_wan: document.getElementById("adminLkIpWan").value.trim(),
        ip_gateway: document.getElementById("adminLkIpGateway").value.trim(),
        ip_mascara: document.getElementById("adminLkIpMascara").value.trim(),
        vlan: document.getElementById("adminLkVlan").value.trim(),
        velocidade: document.getElementById("adminLkVelocidade").value.trim(),
        redundante_critico: appliesRc() && document.getElementById("adminLkRc").checked ? 1 : 0,
        pppoe_user: document.getElementById("adminLkPppoeUser").value.trim(),
        pppoe_pass: document.getElementById("adminLkPppoePass").value,
      };

      if (window.ProdespLiveValidation && ProdespLiveValidation.validateAtendimentoLinkSubmit) {
        const check = ProdespLiveValidation.validateAtendimentoLinkSubmit({
          tipo: fields.tipo,
          operadora: fields.operadora,
          designador: fields.designador,
          velocidade: fields.velocidade,
          ipWan: fields.ip_wan,
          ipGateway: fields.ip_gateway,
          ipMascara: fields.ip_mascara,
          idVgr: fields.id_vgr,
          pppoeUser: fields.pppoe_user,
          pppoePass: fields.pppoe_pass || (id ? "••••••" : ""),
          redundanteCritico: !!fields.redundante_critico,
        });
        if (!check.valid) {
          AI.toast(check.message || "Validação do link falhou.", false);
          if (G) G.unlock(btn);
          return;
        }
        if (check.ipWan) fields.ip_wan = check.ipWan;
        if (check.ipGateway) fields.ip_gateway = check.ipGateway;
        if (check.ipMascara) fields.ip_mascara = check.ipMascara;
      }

      if (G) G.lock(btn, { label: "Salvando…", autoUnlockMs: 120000 });
      try {
        const body = id
          ? fields
          : Object.assign({}, fields, {
              id_vgr_unidade: unitVgr,
              id_vgr_link: fields.id_vgr,
            });
        const url = id ? "/prodesp/api/admin/links/" + id : "/prodesp/api/admin/links";
        const method = id ? "PUT" : "POST";
        const { status, d } = await AI.jsonFetch(url, {
          method: method,
          body: JSON.stringify(body),
        });
        if (status >= 400 || !d.success) {
          AI.toast((d && d.message) || "Falha ao salvar.", false);
          return;
        }
        AI.toast(d.message || "Salvo.", true);
        modalLk.hide();
        reload(true);
      } finally {
        if (G) G.unlock(btn);
      }
    });

    document.getElementById("btnAdminLkTransferOk").addEventListener("click", async function () {
      const btn = this;
      const G = window.ProdespSubmitGuard;
      const id = document.getElementById("adminLkTransferId").value;
      const id_vgr = document.getElementById("adminLkTransferVgr").value.trim();
      if (!id_vgr) {
        AI.toast("Informe o ID VGR destino.", false);
        if (G) G.unlock(btn);
        return;
      }
      if (G) G.lock(btn, { label: "Transferindo…", autoUnlockMs: 120000 });
      try {
        const { status, d } = await AI.jsonFetch("/prodesp/api/admin/links/" + id + "/transferir", {
          method: "POST",
          body: JSON.stringify({
            id_vgr: id_vgr,
            expected_id_unidade: (function () {
              const raw = document.getElementById("adminLkTransferExpectedUid").value;
              return raw === "" ? null : Number(raw);
            })(),
          }),
        });
        if (status >= 400 || !d.success) {
          AI.toast((d && d.message) || "Falha na transferência.", false);
          if (status === 409) {
            modalXfer.hide();
            reload(true);
          }
          return;
        }
        AI.toast(d.message || "Transferido.", true);
        modalXfer.hide();
        reload(true);
      } finally {
        if (G) G.unlock(btn);
      }
    });

    $("#tblAdminLinks").on("click", ".admin-lk-view", function () {
      openEdit(this.getAttribute("data-id"), true);
    });
    $("#tblAdminLinks").on("click", ".admin-lk-edit", function () {
      openEdit(this.getAttribute("data-id"), false);
    });
    $("#tblAdminLinks").on("click", ".admin-lk-xfer", function () {
      openTransfer(this.getAttribute("data-id"), this.getAttribute("data-id-unidade"));
    });
    $("#tblAdminLinks").on("click", ".admin-lk-unlink", async function () {
      await doUnlink(this.getAttribute("data-id"), this.getAttribute("data-id-unidade"));
    });
    $("#tblAdminLinks").on("click", ".admin-lk-del", async function () {
      const id = this.getAttribute("data-id");
      if (!window.confirm("Excluir definitivamente o link #" + id + "?")) return;
      const { status, d } = await AI.jsonFetch("/prodesp/api/admin/links/" + id, { method: "DELETE" });
      if (status >= 400 || !d.success) {
        AI.toast((d && d.message) || "Falha ao excluir.", false);
        return;
      }
      AI.toast(d.message || "Excluído.", true);
      reload(true);
    });
    }, 0); /* fim setTimeout: paint KPIs antes do DataTable */
  });
})();
