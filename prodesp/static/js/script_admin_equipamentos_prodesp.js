/**
 * Admin PRODESP — inventário de equipamentos (PortalDt + KPIs + contexto).
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
      '<button type="button" class="btn-icon text-info admin-eq-view" data-id="' +
      id +
      '"' +
      uidAttr +
      ' title="Ver contexto"><i class="fa-solid fa-eye"></i></button>' +
      '<button type="button" class="btn-icon text-primary admin-eq-edit" data-id="' +
      id +
      '"' +
      uidAttr +
      ' title="Editar"><i class="fa-solid fa-pen"></i></button>' +
      '<button type="button" class="btn-icon text-warning admin-eq-xfer" data-id="' +
      id +
      '"' +
      uidAttr +
      ' title="Transferir"><i class="fa-solid fa-right-left"></i></button>' +
      '<button type="button" class="btn-icon text-secondary admin-eq-unlink" data-id="' +
      id +
      '"' +
      uidAttr +
      ' title="Desassociar"><i class="fa-solid fa-link-slash"></i></button>' +
      '<button type="button" class="btn-icon text-danger admin-eq-del" data-id="' +
      id +
      '" title="Excluir"><i class="fa-solid fa-trash"></i></button>' +
      "</span>"
    );
  }

  let api = null;
  let modalEq = null;
  let modalXfer = null;
  let kpiApi = null;
  let modalMode = "create";
  const ajaxState = {
    revision: null,
    cacheKey: "prodesp.admin.equipamentos.v16",
    kind: "equipamentos",
  };
  let sync = null;
  let serialCtrl = null;

  function paintEqLiveValidation() {
    const serialEl = document.getElementById("adminEqSerial");
    if (!serialEl || !window.ProdespLiveValidation) return;
    const opts = { obrigatorio: true, exigePadrao: true };
    if (serialCtrl && serialCtrl.refresh) {
      serialCtrl.refresh();
    } else if (ProdespLiveValidation.paintSerialFortinetField) {
      ProdespLiveValidation.paintSerialFortinetField(
        serialEl,
        document.getElementById("adminEqSerialHint"),
        opts
      );
    }
  }

  function schedulePaintEqLiveValidation() {
    /* Após fillForm + setFooterMode/modeloCtrl: 2 ticks garantem paint final no modal. */
    setTimeout(function () {
      paintEqLiveValidation();
      requestAnimationFrame(function () {
        paintEqLiveValidation();
      });
    }, 0);
  }

  function reload(forceFull) {
    if (forceFull) {
      ajaxState.revision = null;
      ajaxState.bustCache = true;
    }
    if (api) api.ajax.reload(null, false);
  }

  let modeloCtrl = null;

  function setFooterMode(mode, hasUnit) {
    modalMode = mode;
    const btnSave = document.getElementById("btnAdminEqSalvar");
    const btnCancel = document.getElementById("btnAdminEqCancel");
    const btnXfer = document.getElementById("btnAdminEqFooterXfer");
    const btnUnlink = document.getElementById("btnAdminEqFooterUnlink");
    const isCreate = mode === "create";
    const isEdit = mode === "edit";
    const isView = mode === "view";
    if (btnSave) btnSave.classList.toggle("d-none", isView);
    if (btnCancel) btnCancel.textContent = isView ? "Fechar" : "Cancelar";
    if (btnXfer) btnXfer.classList.toggle("d-none", isCreate);
    if (btnUnlink) btnUnlink.classList.toggle("d-none", !isEdit || !hasUnit);
    AI.applyModalMode(document.getElementById("modalAdminEq"), mode);
    if (modeloCtrl) modeloCtrl.refresh();
  }

  function paintSummary(d, ctx) {
    d = d || {};
    const u = (ctx && ctx.unidade) || null;
    const badges = [];
    if (d.id_unidade || (u && u.id_unidade) || d.id_vgr) {
      badges.push({ label: "Associado", tone: "bg-success" });
    } else if (d.id) {
      badges.push({ label: "Órfão", tone: "bg-danger" });
    }
    if (Number(d.fgt_padrao) === 1 || (ctx && ctx.equipamento && Number(ctx.equipamento.fgt_padrao) === 1)) {
      badges.push({ label: "FGT no padrão", tone: "bg-primary" });
    } else if (d.serial || (ctx && ctx.equipamento)) {
      const fp =
        ctx && ctx.equipamento && ctx.equipamento.fgt_padrao != null
          ? Number(ctx.equipamento.fgt_padrao)
          : Number(d.fgt_padrao);
      if (fp === 0) badges.push({ label: "FGT fora", tone: "bg-warning text-dark" });
    }
    const lines = [];
    if (d.id) lines.push("#" + d.id);
    if (d.modelo) lines.push(d.modelo);
    const vgr = d.id_vgr || (u && u.id_vgr) || "";
    if (vgr) lines.push("VGR " + vgr);
    if (u && u.acronimo) lines.push(u.acronimo);
    else if (d.acronimo) lines.push(d.acronimo);
    AI.renderSummaryStrip(document.getElementById("adminEqSummary"), {
      lines: lines,
      badges: badges,
    });
  }

  function resetContextPanels() {
    document.getElementById("adminEqContexto").innerHTML =
      '<em class="text-muted">Contexto aparece ao editar/visualizar ou ao escolher a unidade na criação.</em>';
    document.getElementById("adminEqAtivos").innerHTML =
      '<em class="text-muted">Ativos da unidade aparecem ao carregar o contexto.</em>';
  }

  function showDadosTab() {
    const btn = document.getElementById("adminEqTabDadosBtn");
    if (btn && window.bootstrap && bootstrap.Tab) {
      bootstrap.Tab.getOrCreateInstance(btn).show();
    }
  }

  async function previewUnidadeFromVgr(vgr) {
    const ctxEl = document.getElementById("adminEqContexto");
    const ativosEl = document.getElementById("adminEqAtivos");
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
    document.getElementById("adminEqId").value = "";
    document.getElementById("adminEqIdUnidade").value = "";
    document.getElementById("adminEqIdVgr").value = "";
    document.getElementById("adminEqHostname").value = "";
    document.getElementById("adminEqSerial").value = "";
    document.getElementById("adminEqModelo").value = "";
    document.getElementById("adminEqVersao").value = "7.4.11";
    document.getElementById("adminEqMac").value = "";
    document.getElementById("adminEqLicenca").value = "";
    document.getElementById("adminEqDescricao").value = "";
    document.getElementById("adminEqHint").textContent = "";
    document.getElementById("adminEqSerialHint").textContent = "";
    document.getElementById("adminEqModeloHint").textContent = "";
    resetContextPanels();
    AI.renderSummaryStrip(document.getElementById("adminEqSummary"), { lines: [], badges: [] });
    if (modeloCtrl) modeloCtrl.refresh();
    /* Sem eventos de input: limpa vermelho residual do bind; fill repinta depois. */
    const serialEl = document.getElementById("adminEqSerial");
    if (serialEl && window.ProdespLiveValidation) {
      if (String(serialEl.value || "").trim() === "") {
        if (ProdespLiveValidation.paintSerialFortinetField) {
          /* Não pintar empty obrigatório em limpeza do modal (evita flash vermelho). */
          serialEl.classList.remove("is-invalid", "is-valid");
          ["prodesp-field-state-ok", "prodesp-field-state-warn", "prodesp-field-state-empty"].forEach(
            function (c) {
              serialEl.classList.remove(c);
            }
          );
          const hint = document.getElementById("adminEqSerialHint");
          if (hint) {
            hint.textContent = "";
            hint.classList.remove("is-empty-hint", "is-warn-hint", "is-ok-hint", "is-invalid-hint");
          }
        }
      } else {
        paintEqLiveValidation();
      }
    }
  }

  function fillForm(d) {
    document.getElementById("adminEqId").value = d.id || "";
    document.getElementById("adminEqIdUnidade").value =
      d.id_unidade != null && d.id_unidade !== "" ? String(d.id_unidade) : "";
    document.getElementById("adminEqIdVgr").value = d.id_vgr || "";
    document.getElementById("adminEqHostname").value = d.hostname || "";
    document.getElementById("adminEqSerial").value = d.serial || "";
    const modeloEl = document.getElementById("adminEqModelo");
    const m = (d.modelo || "").trim();
    if (m) {
      let found = false;
      for (let i = 0; i < modeloEl.options.length; i++) {
        if (modeloEl.options[i].value === m) {
          found = true;
          break;
        }
      }
      if (!found) modeloEl.add(new Option(m, m));
      modeloEl.value = m;
    } else {
      modeloEl.value = "";
    }
    document.getElementById("adminEqVersao").value = d.versao || "7.4.11";
    document.getElementById("adminEqMac").value = d.mac || "";
    document.getElementById("adminEqLicenca").value = d.licenca || "";
    document.getElementById("adminEqDescricao").value = d.descricao || "";
    if (modeloCtrl) modeloCtrl.refresh();
    paintEqLiveValidation();
  }

  function payloadFromForm() {
    const modeloEl = document.getElementById("adminEqModelo");
    return {
      id_vgr: document.getElementById("adminEqIdVgr").value.trim(),
      serial: document.getElementById("adminEqSerial").value.trim(),
      modelo: modeloEl.value.trim(),
      versao: document.getElementById("adminEqVersao").value.trim(),
      mac: document.getElementById("adminEqMac").value.trim(),
      licenca: document.getElementById("adminEqLicenca").value.trim(),
      descricao: document.getElementById("adminEqDescricao").value.trim(),
    };
  }

  async function loadContexto(id, baseData) {
    const ctxEl = document.getElementById("adminEqContexto");
    const ativosEl = document.getElementById("adminEqAtivos");
    ctxEl.innerHTML = '<em class="text-muted">Carregando contexto…</em>';
    ativosEl.innerHTML = '<em class="text-muted">Carregando…</em>';
    try {
      const { status, d } = await AI.jsonFetch(
        "/prodesp/api/admin/equipamentos/" + id + "/contexto"
      );
      if (status >= 400 || !d || !d.success) {
        ctxEl.innerHTML =
          '<em class="text-danger">' + AI.esc((d && d.message) || "Falha ao carregar.") + "</em>";
        ativosEl.innerHTML = '<em class="text-muted">—</em>';
        return;
      }
      AI.fillContextTabs(ctxEl, ativosEl, d);
      paintSummary(Object.assign({}, baseData || {}, d.equipamento || {}), d);
      const hasUnit = !!(d.unidade && d.unidade.id_unidade);
      if (modalMode === "edit") setFooterMode("edit", hasUnit);
    } catch (_e) {
      ctxEl.innerHTML = '<em class="text-danger">Falha de rede no contexto.</em>';
      ativosEl.innerHTML = '<em class="text-muted">—</em>';
    }
  }

  function openTransfer(id, expectedUid) {
    document.getElementById("adminEqTransferId").value = id;
    document.getElementById("adminEqTransferExpectedUid").value =
      expectedUid != null && expectedUid !== "" ? String(expectedUid) : "";
    document.getElementById("adminEqTransferVgr").value = "";
    document.getElementById("adminEqTransferHost").textContent = "";
    document.getElementById("adminEqTransferInfo").textContent = "Equipamento #" + id;
    modalXfer.show();
  }

  async function doUnlink(id, expectedUid) {
    if (!window.confirm("Desassociar equipamento #" + id + " da unidade?")) return;
    const body = {
      expected_id_unidade:
        expectedUid != null && expectedUid !== "" ? Number(expectedUid) : null,
    };
    const { status, d } = await AI.jsonFetch("/prodesp/api/admin/equipamentos/" + id + "/desassociar", {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (status >= 400 || !d.success) {
      AI.toast((d && d.message) || "Falha ao desassociar.", false);
      if (status === 409) reload(true);
      return;
    }
    AI.toast(d.message || "Desassociado.", true);
    modalEq.hide();
    reload(true);
  }

  let openEditSeq = 0;

  function openEdit(id, viewOnly) {
    const seq = ++openEditSeq;
    const formRoot = document.getElementById("adminEqFormRoot");
    const btnSave = document.getElementById("btnAdminEqSalvar");
    clearForm();
    document.getElementById("adminEqId").value = id || "";
    document.getElementById("modalAdminEqTitle").textContent =
      (viewOnly ? "Visualizar" : "Editar") + " equipamento #" + id + "…";
    document.getElementById("adminEqHint").textContent = "Carregando dados…";
    setFooterMode(viewOnly ? "view" : "edit", false);
    if (btnSave) btnSave.disabled = true;
    if (formRoot) formRoot.classList.add("opacity-50", "pe-none");
    paintSummary({ id: id }, null);
    showDadosTab();
    document.getElementById("adminEqContexto").innerHTML =
      '<em class="text-muted">Carregando contexto…</em>';
    document.getElementById("adminEqAtivos").innerHTML =
      '<em class="text-muted">Carregando…</em>';
    modalEq.show();

    AI.jsonFetch("/prodesp/api/admin/equipamentos/" + encodeURIComponent(id))
      .then(function (res) {
        if (seq !== openEditSeq) return;
        if (formRoot) formRoot.classList.remove("opacity-50", "pe-none");
        if (btnSave) btnSave.disabled = !!viewOnly;
        if (res.status >= 400 || !res.d || res.d.success === false) {
          AI.toast((res.d && res.d.message) || "Não encontrado.", false);
          modalEq.hide();
          return;
        }
        const data = res.d.data || {};
        try {
          fillForm(data);
          document.getElementById("modalAdminEqTitle").textContent =
            (viewOnly ? "Visualizar" : "Editar") + " equipamento #" + id;
          document.getElementById("adminEqHint").textContent = viewOnly
            ? ""
            : "Na edição, altere a unidade via Transferir.";
          const hasUnit = !!(data.id_vgr || data.id_unidade);
          setFooterMode(viewOnly ? "view" : "edit", hasUnit);
          paintSummary(data, null);
          showDadosTab();
          schedulePaintEqLiveValidation();
          loadContexto(id, data);
        } catch (_e) {
          AI.toast("Falha ao montar o formulário do equipamento.", false);
        }
      })
      .catch(function () {
        if (seq !== openEditSeq) return;
        if (formRoot) formRoot.classList.remove("opacity-50", "pe-none");
        if (btnSave) btnSave.disabled = false;
        AI.toast("Falha de rede ao abrir o equipamento.", false);
        modalEq.hide();
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    modalEq = new bootstrap.Modal(document.getElementById("modalAdminEq"));
    modalXfer = new bootstrap.Modal(document.getElementById("modalAdminEqTransfer"));

    AI.bindUnitTypeahead(document.getElementById("adminEqIdVgr"), {
      hostInputId: "adminEqHostname",
      onSelect: function (it) {
        if (modalMode === "create" && it && it.id_vgr) {
          previewUnidadeFromVgr(it.id_vgr);
        }
      },
    });
    AI.bindUnitTypeahead(document.getElementById("adminEqTransferVgr"), {
      onSelect: function (it) {
        document.getElementById("adminEqTransferHost").textContent =
          (it.hostname || "") + (it.nome ? " · " + it.nome : "");
      },
    });
    modeloCtrl = AI.bindModeloLockedFromSerial("adminEqSerial", "adminEqModelo", {
      hintId: "adminEqModeloHint",
      descricaoId: "adminEqDescricao",
      unlockBtnId: "btnAdminEqModeloSerial",
    });
    if (window.ProdespLiveValidation) {
      if (ProdespLiveValidation.bindSerialFortinetInput) {
        serialCtrl = ProdespLiveValidation.bindSerialFortinetInput("adminEqSerial", {
          hintId: "adminEqSerialHint",
          obrigatorio: true,
          exigePadrao: true,
          skipInitialPaint: true,
        });
      } else if (ProdespLiveValidation.bindNoWhitespaceInput) {
        const el = document.getElementById("adminEqSerial");
        if (el) ProdespLiveValidation.bindNoWhitespaceInput(el);
      }
      if (ProdespLiveValidation.bindNoWhitespaceInput) {
        const mac = document.getElementById("adminEqMac");
        if (mac) ProdespLiveValidation.bindNoWhitespaceInput(mac);
      }
    }

    const modalEqEl = document.getElementById("modalAdminEq");
    if (modalEqEl) {
      modalEqEl.addEventListener("shown.bs.modal", function () {
        if (document.getElementById("adminEqId").value.trim()) {
          schedulePaintEqLiveValidation();
        }
      });
    }

    /* KPIs antes do DataTable — layout visível durante o ajax */
    function fgtFora(r) {
      return Number(r.fgt_padrao) !== 1;
    }
    kpiApi = AI.mountKpis("adminEqKpis", null, [
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
        label: "Sem unidade",
        hint: "Órfãos",
        color: "#dc3545",
        icon: "fa-unlink",
        iconTone: "danger",
        test: function (r) {
          return Number(r.associado) !== 1;
        },
      },
      {
        key: "fgt_ok",
        section: "Inventário",
        label: "FGT no padrão",
        hint: "Serial Fortinet",
        color: "#0d6efd",
        icon: "fa-check-circle",
        iconTone: "primary",
        test: function (r) {
          return Number(r.fgt_padrao) === 1;
        },
      },
      {
        key: "fgt_out",
        section: "Inventário",
        label: "FGT fora",
        hint: "Serial inválido",
        color: "#fd7e14",
        icon: "fa-exclamation-triangle",
        iconTone: "warning",
        test: fgtFora,
      },
      {
        key: "fgt_out_cob",
        section: "Cobrança / atenção",
        label: "FGT fora · Concluído",
        hint: "Concluído / Parcial — cobrar",
        color: "#198754",
        icon: "fa-clipboard-check",
        iconTone: "success",
        test: function (r) {
          return fgtFora(r) && AI.statusIsCobranca(r.status_ultimo_atendimento);
        },
      },
      {
        key: "fgt_out_atend",
        section: "Cobrança / atenção",
        label: "FGT fora · Em Atend.",
        hint: "Corrigir até o final",
        color: "#0d6efd",
        icon: "fa-spinner",
        iconTone: "primary",
        test: function (r) {
          return fgtFora(r) && AI.statusIsEmAtendimento(r.status_ultimo_atendimento);
        },
      },
      {
        key: "fgt_out_quebra",
        section: "Cobrança / atenção",
        label: "FGT fora · Quebra",
        hint: "Atenção (novo atend. virá)",
        color: "#dc3545",
        icon: "fa-exclamation-triangle",
        iconTone: "danger",
        test: function (r) {
          return fgtFora(r) && AI.statusIsQuebra(r.status_ultimo_atendimento);
        },
      },
      {
        key: "modelos",
        section: "Modelos / Versões",
        label: "Modelos",
        hint: "Distintos · clique = top",
        color: "#6610f2",
        icon: "fa-cubes",
        iconTone: "info",
        countFn: function (rows) {
          const map = {};
          rows.forEach(function (r) {
            const m = (r.modelo || "—").trim() || "—";
            map[m] = 1;
          });
          return Object.keys(map).length;
        },
        onClick: function (dtApi) {
          const rows = dtApi.rows({ search: "none" }).data().toArray();
          const map = {};
          rows.forEach(function (r) {
            const m = (r.modelo || "—").trim() || "—";
            map[m] = (map[m] || 0) + 1;
          });
          const top = AI.toastTopCounts("Top modelo", map, { topN: 8, durationMs: 8000 });
          if (!top || !top.length) return;
          dtApi.columns().search("");
          dtApi
            .column(2)
            .search("^" + $.fn.dataTable.util.escapeRegex(top[0].k) + "$", true, false)
            .draw();
        },
      },
      {
        key: "versoes",
        section: "Modelos / Versões",
        label: "Versões",
        hint: "Distintas · clique = top (hoje 7.4.11)",
        color: "#0dcaf0",
        icon: "fa-code-branch",
        iconTone: "info",
        countFn: function (rows) {
          const map = {};
          rows.forEach(function (r) {
            const v = (r.versao || "—").trim() || "—";
            map[v] = 1;
          });
          return Object.keys(map).length;
        },
        onClick: function (dtApi) {
          const rows = dtApi.rows({ search: "none" }).data().toArray();
          const map = {};
          rows.forEach(function (r) {
            const v = (r.versao || "—").trim() || "—";
            map[v] = (map[v] || 0) + 1;
          });
          const top = AI.toastTopCounts("Top versão", map, { topN: 8, durationMs: 8000 });
          if (!top || !top.length) return;
          dtApi.columns().search("");
          dtApi
            .column(3)
            .search("^" + $.fn.dataTable.util.escapeRegex(top[0].k) + "$", true, false)
            .draw();
        },
      },
    ]);

    /* 1 tick: browser pinta KPIs (0) antes do init pesado do DataTables/CC. */
    setTimeout(function () {
    api = $("#tblAdminEquipamentos").DataTable({
      serverSide: false,
      processing: false,
      deferRender: true,
      pageLength: 25,
      autoWidth: false,
      order: [[0, "desc"]],
      ordering: { indicators: false, handler: false },
      ajax: AI.clientAjax("/prodesp/api/admin/equipamentos", ajaxState),
      columns: [
        { data: "id", title: "ID", width: "52px", className: "text-start" },
        { data: "serial", title: "Serial", width: "140px", className: "text-start" },
        { data: "modelo", title: "Modelo", width: "110px", className: "text-start" },
        { data: "versao", title: "Versão", width: "64px", className: "text-start" },
        { data: "id_vgr", title: "ID VGR Unidade", width: "100px", className: "text-start" },
        { data: "hostname", title: "Hostname", width: "180px", className: "text-start" },
        { data: "acronimo", title: "Acrônimo", width: "90px", className: "text-start" },
        { data: "nome_unidade", title: "Unidade", width: "160px", className: "text-start" },
        {
          data: "status_ultimo_atendimento",
          title: "Status (último atend.)",
          width: "120px",
          className: "text-start",
          defaultContent: "",
          type: "string",
          render: function (d, t) {
            const s = String(d == null ? "" : d).trim();
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
          targets: [0, 4, 5],
          columnControl: [],
        },
        {
          targets: [1, 2, 3, 6, 7, 8, 9],
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
        AI.bindPortalDtColumnControl(this.api(), "equipamentos");
      },
    });
    if (kpiApi && typeof kpiApi.bind === "function") kpiApi.bind(api);

    if (window.PortalDtToolbar) {
      PortalDtToolbar.mount(null, {
        tableId: "tblAdminEquipamentos",
        api: api,
        onRefresh: function () {
          reload(true);
        },
        onClearExtra: function () {
          if (kpiApi) kpiApi.clear();
        },
      });
    }

    sync = AI.bindRevisionSync(api, ajaxState);
    AI.bindUltimoAtendimentoPageEnrich(api);

    document.getElementById("btnAdminEqNovo").addEventListener("click", function () {
      clearForm();
      document.getElementById("modalAdminEqTitle").textContent = "Novo equipamento";
      document.getElementById("adminEqHint").textContent = "";
      setFooterMode("create", false);
      showDadosTab();
      modalEq.show();
      /* create: serial vazio é erro real → pinta só após o modal visível. */
      setTimeout(function () {
        paintEqLiveValidation();
      }, 0);
    });

    document.getElementById("btnAdminEqFooterXfer").addEventListener("click", function () {
      const id = document.getElementById("adminEqId").value.trim();
      if (id) openTransfer(id, document.getElementById("adminEqIdUnidade").value);
    });
    document.getElementById("btnAdminEqFooterUnlink").addEventListener("click", function () {
      const id = document.getElementById("adminEqId").value.trim();
      if (id) doUnlink(id, document.getElementById("adminEqIdUnidade").value);
    });

    document.getElementById("btnAdminEqSalvar").addEventListener("click", async function () {
      const btn = this;
      const G = window.ProdespSubmitGuard;
      const id = document.getElementById("adminEqId").value.trim();
      const body = payloadFromForm();
      if (!body.serial) {
        AI.toast("Serial é obrigatório.", false);
        if (G) G.unlock(btn);
        return;
      }
      if (
        window.ProdespLiveValidation &&
        ProdespLiveValidation.validateEquipamentoSubmit
      ) {
        const eqCheck = ProdespLiveValidation.validateEquipamentoSubmit(
          { serial: body.serial, versao: body.versao },
          { obrigatorio: true, exigePadrao: true }
        );
        if (!eqCheck.valid) {
          AI.toast(eqCheck.message || "Serial Fortinet inválido.", false);
          if (ProdespLiveValidation.paintSerialFortinetField) {
            ProdespLiveValidation.paintSerialFortinetField(
              document.getElementById("adminEqSerial"),
              document.getElementById("adminEqSerialHint"),
              { obrigatorio: true, exigePadrao: true }
            );
          }
          if (G) G.unlock(btn);
          return;
        }
        if (eqCheck.serial) body.serial = eqCheck.serial;
      }
      if (!id && !body.id_vgr) {
        AI.toast("Informe o ID VGR da unidade.", false);
        if (G) G.unlock(btn);
        return;
      }
      if (G) G.lock(btn, { label: "Salvando…", autoUnlockMs: 120000 });
      try {
        const url = id ? "/prodesp/api/admin/equipamentos/" + id : "/prodesp/api/admin/equipamentos";
        const method = id ? "PUT" : "POST";
        const { status, d } = await AI.jsonFetch(url, { method: method, body: JSON.stringify(body) });
        if (status >= 400 || !d.success) {
          AI.toast((d && d.message) || "Falha ao salvar.", false);
          return;
        }
        AI.toast(d.message || "Salvo.", true);
        modalEq.hide();
        reload(true);
      } finally {
        if (G) G.unlock(btn);
      }
    });

    document.getElementById("btnAdminEqTransferOk").addEventListener("click", async function () {
      const btn = this;
      const G = window.ProdespSubmitGuard;
      const id = document.getElementById("adminEqTransferId").value;
      const id_vgr = document.getElementById("adminEqTransferVgr").value.trim();
      if (!id_vgr) {
        AI.toast("Informe o ID VGR destino.", false);
        if (G) G.unlock(btn);
        return;
      }
      if (G) G.lock(btn, { label: "Transferindo…", autoUnlockMs: 120000 });
      try {
        const { status, d } = await AI.jsonFetch("/prodesp/api/admin/equipamentos/" + id + "/transferir", {
          method: "POST",
          body: JSON.stringify({
            id_vgr: id_vgr,
            expected_id_unidade: (function () {
              const raw = document.getElementById("adminEqTransferExpectedUid").value;
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

    $("#tblAdminEquipamentos").on("click", ".admin-eq-view", function () {
      openEdit(this.getAttribute("data-id"), true);
    });
    $("#tblAdminEquipamentos").on("click", ".admin-eq-edit", function () {
      openEdit(this.getAttribute("data-id"), false);
    });
    $("#tblAdminEquipamentos").on("click", ".admin-eq-xfer", function () {
      openTransfer(this.getAttribute("data-id"), this.getAttribute("data-id-unidade"));
    });
    $("#tblAdminEquipamentos").on("click", ".admin-eq-unlink", async function () {
      await doUnlink(this.getAttribute("data-id"), this.getAttribute("data-id-unidade"));
    });
    $("#tblAdminEquipamentos").on("click", ".admin-eq-del", async function () {
      const id = this.getAttribute("data-id");
      if (!window.confirm("Excluir definitivamente o equipamento #" + id + "?")) return;
      const { status, d } = await AI.jsonFetch("/prodesp/api/admin/equipamentos/" + id, { method: "DELETE" });
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
