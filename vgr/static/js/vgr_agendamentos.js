(function () {
  "use strict";
  const V = window.VgrDt;
  if (!V || typeof $ === "undefined" || !$.fn.DataTable) return;

  const modo = window.VGR_AG_MODO || "operacao";
  const modalEl = document.getElementById("modalVgrAg");
  const modal = modalEl && window.bootstrap ? new bootstrap.Modal(modalEl) : null;
  const errEl = document.getElementById("vgrAgErro");
  const cc = window.PortalDt ? window.PortalDt.ccSearchList() : [];
  const CHECKLIST = [
    ["q_compra_equip", "Processo compra equip?"],
    ["q_equip_mam", "Equipamento com fornecedor?"],
    ["q_email_agendamento", "E-mail de agendamento?"],
    ["q_lote", "Lote?"],
    ["q_ticket_aberto", "Ticket aberto?"],
    ["q_confirma_csi_gp", "Confirmação CSI/GP?"],
    ["q_tem_problema", "Problema?"],
  ];
  let catalogo = { status: [], tipos: [], status_agendado: "Agendado" };
  let unidadesCache = [];
  const PF = window.PortalFieldValidation || null;
  let vgrIncidentItemSeq = 0;

  function showErr(msg) {
    if (!errEl) return;
    if (msg) {
      errEl.textContent = msg;
      errEl.classList.remove("d-none");
    } else {
      errEl.textContent = "";
      errEl.classList.add("d-none");
    }
  }

  function fillSelect(el, values, selected, includeEmpty) {
    if (!el) return;
    el.innerHTML = "";
    if (includeEmpty) {
      var empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "—";
      el.appendChild(empty);
    }
    (values || []).forEach(function (v) {
      if (v === catalogo.status_agendado && el.id === "vgrAgStatus") {
        return;
      }
      var opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      if (String(v) === String(selected || "")) opt.selected = true;
      el.appendChild(opt);
    });
    if (selected === catalogo.status_agendado && el.id === "vgrAgStatus") {
      var optA = document.createElement("option");
      optA.value = catalogo.status_agendado;
      optA.textContent = catalogo.status_agendado + " (somente leitura)";
      optA.selected = true;
      optA.disabled = true;
      el.appendChild(optA);
    }
  }

  function buildChecklist() {
    var wrap = document.getElementById("vgrAgChecklist");
    if (!wrap || wrap.childElementCount) return;
    CHECKLIST.forEach(function (pair) {
      var col = document.createElement("div");
      col.className = "col-md-4";
      var box = document.createElement("div");
      box.className = "form-check";
      var input = document.createElement("input");
      input.className = "form-check-input vgr-ag-q";
      input.type = "checkbox";
      input.id = pair[0];
      input.setAttribute("data-q", pair[0]);
      var label = document.createElement("label");
      label.className = "form-check-label";
      label.htmlFor = pair[0];
      label.textContent = pair[1];
      box.appendChild(input);
      box.appendChild(label);
      col.appendChild(box);
      wrap.appendChild(col);
    });
  }

  function currentUnidadeId() {
    return document.getElementById("vgrAgUnidade").value || "";
  }

  function clearUnidadePainel() {
    [
      "vgrAgIdVgr",
      "vgrAgTipoUni",
      "vgrAgHa",
      "vgrAgCliente",
      "vgrAgNomeUni",
      "vgrAgEndereco",
      "vgrAgBairro",
      "vgrAgCidade",
      "vgrAgUf",
      "vgrAgCep",
      "vgrAgCnpjUni",
      "vgrAgHostResumo",
      "vgrAgEqCount",
      "vgrAgLinkCount",
    ].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.value = "";
    });
    var eqContainer = document.getElementById("vgrAgEqList");
      if (eqContainer) {
        eqContainer.innerHTML =
          '<div class="text-muted p-2">Selecione uma unidade.</div>';
      }
    var lkBody = document.querySelector("#vgrAgTblLinks tbody");
      if (lkBody) {
        lkBody.innerHTML =
          '<tr><td colspan="7" class="text-muted">Selecione uma unidade.</td></tr>';
      }
  }

  function fillUnidadePainel(d) {
    document.getElementById("vgrAgIdVgr").value = d.id_vgr || "";
    document.getElementById("vgrAgTipoUni").value = d.tipo_unidade || "";
    document.getElementById("vgrAgHa").value = Number(d.ha) === 1 ? "Sim" : "Não";
    document.getElementById("vgrAgCliente").value = d.razao_social || "";
    document.getElementById("vgrAgNomeUni").value = d.nome_unidade || "";
    document.getElementById("vgrAgEndereco").value = d.endereco || "";
    document.getElementById("vgrAgBairro").value = d.bairro || "";
    document.getElementById("vgrAgCidade").value = d.cidade || "";
    document.getElementById("vgrAgUf").value = d.uf || "";
    document.getElementById("vgrAgCep").value = d.cep || "";
    document.getElementById("vgrAgCnpjUni").value = d.cnpj_unidade || "";
  }

function renderEqLinks(eqRows, linkRows) {
  var eqAtivos = (eqRows || []).filter(function (r) {
    return Number(r.ativo) === 1;
  });
  var lkAtivos = (linkRows || []).filter(function (r) {
    return Number(r.ativo) === 1;
  });
  document.getElementById("vgrAgEqCount").value = String(eqAtivos.length);
  document.getElementById("vgrAgLinkCount").value = String(lkAtivos.length);
  document.getElementById("vgrAgHostResumo").value =
    (eqAtivos[0] && (eqAtivos[0].hostname || eqAtivos[0].serial)) || "";
  renderEqListVgr(eqRows);
  renderLinksTableVgr(linkRows);
}

/* ============================================================
   Helpers de accordion (espelho de vgr_atendimentos.js)
   ============================================================ */
function vgrNextIncidentItemId(prefix) {
  vgrIncidentItemSeq += 1;
  return prefix + "-" + Date.now() + "-" + vgrIncidentItemSeq;
}
function vgrEnsureIncidentAccordionList(containerEl) {
  if (!containerEl) return null;
  var acc = containerEl.querySelector(":scope > .prodesp-incident-accordion");
  if (!acc) {
    acc = containerEl.querySelector(":scope > .vgr-incident-accordion");
  }
  if (!acc) {
    containerEl.innerHTML = "";
    acc = document.createElement("div");
    acc.className = "prodesp-incident-accordion accordion accordion-flush";
    if (containerEl.id) acc.id = containerEl.id + "-accordion";
    containerEl.appendChild(acc);
  }
  return acc;
}
function vgrResetIncidentListContainer(containerEl) {
  if (!containerEl) return null;
  containerEl.innerHTML = "";
  return vgrEnsureIncidentAccordionList(containerEl);
}
function vgrIncidentSummaryText(parts) {
  return parts.filter(function (p) { return p && String(p).trim(); }).join(" · ") || "—";
}
function vgrCreateIncidentActionsGroup(buttons) {
  var group = document.createElement("div");
  group.className = "prodesp-incident-actions btn-group btn-group-sm flex-shrink-0";
  buttons.forEach(function (b) { group.appendChild(b); });
  return group;
}
function vgrCreateIncidentToggleBtn(collapseId, summary, expanded) {
  var btn = document.createElement("button");
  btn.type = "button";
  btn.className = "accordion-button py-2 " + (expanded ? "" : "collapsed");
  btn.setAttribute("data-bs-toggle", "collapse");
  btn.setAttribute("data-bs-target", "#" + collapseId);
  btn.setAttribute("aria-expanded", expanded ? "true" : "false");
  btn.setAttribute("aria-controls", collapseId);
  btn.textContent = summary;
  return btn;
}
function vgrCreateIncidentFieldCol(label, control, colClass) {
  var col = document.createElement("div");
  col.className = colClass || "col-md-4 col-sm-6";
  var lbl = document.createElement("label");
  lbl.className = "form-label form-label-sm mb-0 text-muted small";
  lbl.textContent = label;
  col.append(lbl, control);
  return col;
}
function vgrCreateIncidentReadonlyCol(label, text) {
  var val = document.createElement("div");
  val.className = "form-control form-control-sm bg-light prodesp-incident-readonly text-break";
  val.textContent = text || "—";
  return vgrCreateIncidentFieldCol(label, val);
}
function vgrBuildIncidentAccordionItem(summary, accordionParentId) {
  var itemId = vgrNextIncidentItemId("vgr-inc");
  var collapseId = itemId + "-pane";
  var item = document.createElement("div");
  item.className = "accordion-item prodesp-incident-accordion-item border-0 border-bottom";
  var header = document.createElement("h2");
  header.className = "accordion-header m-0";
  var headerRow = document.createElement("div");
  headerRow.className = "prodesp-incident-accordion-header d-flex align-items-stretch w-100";
  var toggleBtn = vgrCreateIncidentToggleBtn(collapseId, summary, false);
  var actionsSlot = document.createElement("div");
  actionsSlot.className = "prodesp-incident-actions-slot d-flex align-items-center pe-2";
  headerRow.append(toggleBtn, actionsSlot);
  header.appendChild(headerRow);
  var collapse = document.createElement("div");
  collapse.id = collapseId;
  collapse.className = "accordion-collapse collapse";
  if (accordionParentId) collapse.setAttribute("data-bs-parent", "#" + accordionParentId);
  var body = document.createElement("div");
  body.className = "accordion-body py-2 px-3";
  var grid = document.createElement("div");
  grid.className = "row g-2 prodesp-incident-fields-grid";
  body.appendChild(grid);
  collapse.appendChild(body);
  item.append(header, collapse);
  return { item: item, grid: grid, actionsSlot: actionsSlot, collapse: collapse, toggleBtn: toggleBtn };
}
function vgrBuildVendorSelect(selected) {
  var sel = document.createElement("select");
  sel.className = "form-select form-select-sm";
  var emptyOpt = document.createElement("option");
  emptyOpt.value = "";
  emptyOpt.textContent = "Selecione...";
  sel.appendChild(emptyOpt);
  (V.VENDORS || []).forEach(function (v) {
    var opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    sel.appendChild(opt);
  });
  if (selected) sel.value = String(selected);
  return sel;
}
function vgrBuildTipoServicoSelect(selected) {
  var sel = document.createElement("select");
  sel.className = "form-select form-select-sm";
  var emptyOpt = document.createElement("option");
  emptyOpt.value = "";
  emptyOpt.textContent = "Selecione...";
  sel.appendChild(emptyOpt);
  ["SDWAN", "SDWIFI", "SDLAN"].forEach(function (v) {
    var opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    sel.appendChild(opt);
  });
  if (selected) sel.value = String(selected);
  return sel;
}
function vgrBuildLicencaSelect(selected) {
  var sel = document.createElement("select");
  sel.className = "form-select form-select-sm";
  var emptyOpt = document.createElement("option");
  emptyOpt.value = "";
  emptyOpt.textContent = "Selecione...";
  sel.appendChild(emptyOpt);
  ["EA", "A la Carte"].forEach(function (v) {
    var opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    sel.appendChild(opt);
  });
  if (selected) sel.value = String(selected);
  return sel;
}
function vgrAttachCopyIcon(colEl, textToCopy) {
  if (!textToCopy || textToCopy === "—") return;
  var readonlyDiv = colEl.querySelector(".prodesp-incident-readonly");
  if (!readonlyDiv) return;
  var icon = document.createElement("i");
  icon.className = "far fa-copy btn-copy-inline ms-2 text-muted";
  icon.title = "Copiar";
  icon.style.cursor = "pointer";
  icon.onclick = function (e) {
    e.stopPropagation();
    navigator.clipboard.writeText(String(textToCopy)).then(function () {
      V.toast("'" + textToCopy + "' copiado!", true);
    }).catch(function () {
      V.toast("Falha ao copiar.", false);
    });
  };
  readonlyDiv.appendChild(icon);
}
/* ============================================================
   RENDERIZAÇÃO / CRUD DE EQUIPAMENTO (accordion inline)
   Mesma lógica e campos da view de atendimento.
   ============================================================ */
function renderEqCardVgr(eqObj, containerEl) {
  if (!containerEl) {
    console.error("Container de equipamentos não encontrado.", containerEl);
    return;
  }
  var accordion = vgrEnsureIncidentAccordionList(containerEl);
  if (!accordion) return;
  var summary = vgrIncidentSummaryText([
    eqObj.hostname || eqObj.serial,
    eqObj.vendor,
    eqObj.modelo,
  ]);
  var shell = vgrBuildIncidentAccordionItem(summary, accordion.id);
  var item = shell.item;
  var grid = shell.grid;
  var actionsSlot = shell.actionsSlot;
  var collapse = shell.collapse;
  var showCollapse = function (open) {
    var inst = bootstrap.Collapse.getOrCreateInstance(collapse, { toggle: false });
    if (open) inst.show();
    else inst.hide();
  };
  var renderViewMode = function () {
    showCollapse(false);
    item.classList.remove("prodesp-incident-item-editing");
    shell.toggleBtn.textContent = summary;
    grid.innerHTML = "";
    grid.appendChild(vgrCreateIncidentReadonlyCol("ID", eqObj.id_equipamento));
    grid.appendChild(vgrCreateIncidentReadonlyCol("ID VGR", eqObj.id_vgr));
    grid.appendChild(vgrCreateIncidentReadonlyCol("Vendor", eqObj.vendor));
    grid.appendChild(vgrCreateIncidentReadonlyCol("Modelo", eqObj.modelo));
    var serialCol = vgrCreateIncidentReadonlyCol("Serial", eqObj.serial);
    vgrAttachCopyIcon(serialCol, eqObj.serial);
    grid.appendChild(serialCol);
    grid.appendChild(vgrCreateIncidentReadonlyCol("Hostname", eqObj.hostname));
    grid.appendChild(vgrCreateIncidentReadonlyCol("Tipo Serviço", eqObj.tipo_servico));
    grid.appendChild(vgrCreateIncidentReadonlyCol("Licença", eqObj.licenca));
    var tktCol = vgrCreateIncidentReadonlyCol("TKT NOC", eqObj.tkt_noc);
    vgrAttachCopyIcon(tktCol, eqObj.tkt_noc);
    grid.appendChild(tktCol);
    grid.appendChild(vgrCreateIncidentReadonlyCol("Ativo", V.yesNo(eqObj.ativo)));
    var editButton = document.createElement("button");
    editButton.innerHTML = '<i class="fas fa-pencil-alt"></i>';
    editButton.type = "button";
    editButton.className = "btn btn-sm btn-outline-primary";
    editButton.title = "Editar Equipamento";
    editButton.onclick = function (e) { e.stopPropagation(); renderEditMode(); };
    actionsSlot.innerHTML = "";
    actionsSlot.appendChild(vgrCreateIncidentActionsGroup([editButton]));
  };
  var renderEditMode = function () {
    showCollapse(true);
    item.classList.add("prodesp-incident-item-editing");
    shell.toggleBtn.textContent = "Editando equipamento…";
    grid.innerHTML = "";
    var idVgrInp = document.createElement("input");
    idVgrInp.className = "form-control form-control-sm";
    idVgrInp.value = eqObj.id_vgr || "";
    var serialInp = document.createElement("input");
    serialInp.className = "form-control form-control-sm";
    serialInp.value = eqObj.serial || "";
    var vendorSel = vgrBuildVendorSelect(eqObj.vendor);
    var modeloInp = document.createElement("input");
    modeloInp.className = "form-control form-control-sm";
    modeloInp.value = eqObj.modelo || "";
    var hostnameInp = document.createElement("input");
    hostnameInp.className = "form-control form-control-sm";
    hostnameInp.value = eqObj.hostname || "";
    var tipoSel = vgrBuildTipoServicoSelect(eqObj.tipo_servico);
    var licencaSel = vgrBuildLicencaSelect(eqObj.licenca);
    var tktInp = document.createElement("input");
    tktInp.className = "form-control form-control-sm";
    tktInp.value = eqObj.tkt_noc || "";
    grid.append(
      vgrCreateIncidentFieldCol("ID VGR", idVgrInp, "col-md-6"),
      vgrCreateIncidentFieldCol("Serial *", serialInp, "col-md-6"),
      vgrCreateIncidentFieldCol("Vendor", vendorSel, "col-md-6"),
      vgrCreateIncidentFieldCol("Modelo", modeloInp, "col-md-6"),
      vgrCreateIncidentFieldCol("Hostname", hostnameInp, "col-md-6"),
      vgrCreateIncidentFieldCol("Tipo Serviço", tipoSel, "col-md-6"),
      vgrCreateIncidentFieldCol("Licença", licencaSel, "col-md-6"),
      vgrCreateIncidentFieldCol("TKT NOC", tktInp, "col-md-6")
    );
    var saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.innerHTML = '<i class="fas fa-check me-1"></i>Salvar';
    saveBtn.className = "btn btn-sm btn-success";
    saveBtn.title = "Salvar edição do equipamento";
    saveBtn.onclick = function (e) {
      e.stopPropagation();
      var serial = (serialInp.value || "").trim();
      if (!serial) {
        V.toast("Serial é obrigatório.", false);
        return;
      }
      var payload = {
        serial: serial,
        vendor: vendorSel.value,
        modelo: (modeloInp.value || "").trim(),
        hostname: (hostnameInp.value || "").trim(),
        id_vgr: (idVgrInp.value || "").trim() || null,
        tipo_servico: tipoSel.value || null,
        licenca: licencaSel.value,
        tkt_noc: (tktInp.value || "").trim(),
      };
      if (payload.tkt_noc && PF && PF.validateTicketNoc) {
        var errT = PF.validateTicketNoc(payload.tkt_noc);
        if (errT) {
          V.toast(errT, false);
          return;
        }
      }
      var uni = currentUnidadeId();
      if (!uni) {
        V.toast("Unidade não selecionada.", false);
        return;
      }
      var url = "/vgr/api/equipamentos/" + encodeURIComponent(eqObj.id_equipamento);
      saveBtn.disabled = true;
      V.jsonFetch(url, { method: "PUT", body: JSON.stringify(payload) })
        .then(function (res) {
          if (res.status >= 400 || !res.d.success) {
            V.toast((res.d && res.d.message) || "Falha ao salvar equipamento.", false);
            return;
          }
          V.toast(res.d.message || "Equipamento salvo.", true);
          loadUnidadeDetalhe(uni);
        })
        .finally(function () {
          saveBtn.disabled = false;
        });
    };
    var cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.innerHTML = '<i class="fas fa-times me-1"></i>Cancelar';
    cancelBtn.className = "btn btn-sm btn-secondary";
    cancelBtn.title = "Cancelar edição";
    cancelBtn.onclick = function (e) { e.stopPropagation(); renderViewMode(); };
    actionsSlot.innerHTML = "";
    actionsSlot.appendChild(vgrCreateIncidentActionsGroup([saveBtn, cancelBtn]));
  };
  accordion.appendChild(item);
  renderViewMode();
}
/** Cria accordion em branco para novo equipamento (POST na unidade selecionada). */
function vgrCreateNewEqInline() {
  var uni = currentUnidadeId();
  if (!uni) {
    V.toast("Selecione a unidade antes.", false);
    return;
  }
  var container = document.getElementById("vgrAgEqList");
  if (!container) return;
  var accordion = vgrEnsureIncidentAccordionList(container);
  if (!accordion) return;
  var shell = vgrBuildIncidentAccordionItem("Novo equipamento", accordion.id);
  var item = shell.item;
  var grid = shell.grid;
  var actionsSlot = shell.actionsSlot;
  var collapse = shell.collapse;
  var showCollapse = function (open) {
    var inst = bootstrap.Collapse.getOrCreateInstance(collapse, { toggle: false });
    if (open) inst.show();
    else inst.hide();
  };
  showCollapse(true);
  item.classList.add("prodesp-incident-item-editing");
  shell.toggleBtn.textContent = "Novo equipamento…";
  var idVgrInp = document.createElement("input");
  idVgrInp.className = "form-control form-control-sm";
  var serialInp = document.createElement("input");
  serialInp.className = "form-control form-control-sm";
  var vendorSel = vgrBuildVendorSelect("");
  var modeloInp = document.createElement("input");
  modeloInp.className = "form-control form-control-sm";
  var hostnameInp = document.createElement("input");
  hostnameInp.className = "form-control form-control-sm";
  var tipoSel = vgrBuildTipoServicoSelect("");
  var licencaSel = vgrBuildLicencaSelect("");
  var tktInp = document.createElement("input");
  tktInp.className = "form-control form-control-sm";
  grid.append(
    vgrCreateIncidentFieldCol("ID VGR", idVgrInp, "col-md-6"),
    vgrCreateIncidentFieldCol("Serial *", serialInp, "col-md-6"),
    vgrCreateIncidentFieldCol("Vendor", vendorSel, "col-md-6"),
    vgrCreateIncidentFieldCol("Modelo", modeloInp, "col-md-6"),
    vgrCreateIncidentFieldCol("Hostname", hostnameInp, "col-md-6"),
    vgrCreateIncidentFieldCol("Tipo Serviço", tipoSel, "col-md-6"),
    vgrCreateIncidentFieldCol("Licença", licencaSel, "col-md-6"),
    vgrCreateIncidentFieldCol("TKT NOC", tktInp, "col-md-6")
  );
  var saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.innerHTML = '<i class="fas fa-check me-1"></i>Salvar';
  saveBtn.className = "btn btn-sm btn-success";
  saveBtn.title = "Salvar novo equipamento";
  saveBtn.onclick = function (e) {
    e.stopPropagation();
    var serial = (serialInp.value || "").trim();
    if (!serial) {
      V.toast("Serial é obrigatório.", false);
      return;
    }
    var payload = {
      serial: serial,
      vendor: vendorSel.value,
      modelo: (modeloInp.value || "").trim(),
      hostname: (hostnameInp.value || "").trim(),
      id_vgr: (idVgrInp.value || "").trim() || null,
      tipo_servico: tipoSel.value || null,
      licenca: licencaSel.value,
      tkt_noc: (tktInp.value || "").trim(),
    };
    if (payload.tkt_noc && PF && PF.validateTicketNoc) {
      var errT = PF.validateTicketNoc(payload.tkt_noc);
      if (errT) {
        V.toast(errT, false);
        return;
      }
    }
    var url = "/vgr/api/unidades/" + encodeURIComponent(uni) + "/equipamentos";
    saveBtn.disabled = true;
    V.jsonFetch(url, { method: "POST", body: JSON.stringify(payload) })
      .then(function (res) {
        if (res.status >= 400 || !res.d.success) {
          V.toast((res.d && res.d.message) || "Falha ao salvar equipamento.", false);
          return;
        }
        V.toast(res.d.message || "Equipamento criado.", true);
        loadUnidadeDetalhe(uni);
      })
      .finally(function () {
        saveBtn.disabled = false;
      });
  };
  var cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.innerHTML = '<i class="fas fa-times me-1"></i>Cancelar';
  cancelBtn.className = "btn btn-sm btn-secondary";
  cancelBtn.title = "Cancelar criação";
  cancelBtn.onclick = function (e) {
    e.stopPropagation();
    item.remove();
  };
  actionsSlot.innerHTML = "";
  actionsSlot.appendChild(vgrCreateIncidentActionsGroup([saveBtn, cancelBtn]));
  accordion.appendChild(item);
  item.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/* Equipamentos: accordion inline (mesma lógica/campos da view de atendimento). */
function renderEqListVgr(eqRows) {
  var container = document.getElementById("vgrAgEqList");
  if (!container) return;
  vgrResetIncidentListContainer(container);
  if (!eqRows || !eqRows.length) {
    container.innerHTML = '<div class="text-muted p-2">Nenhum equipamento.</div>';
    return;
  }
  eqRows.forEach(function (eq) {
    renderEqCardVgr(eq, container);
  });
}
  /* Links: permanecem somente leitura (tabela). */
  function renderLinksTableVgr(linkRows) {
    var lkBody = document.querySelector("#vgrAgTblLinks tbody");
    if (!lkBody) return;
    if (!linkRows || !linkRows.length) {
      lkBody.innerHTML = '<tr><td colspan="7" class="text-muted">Nenhum link.</td></tr>';
      return;
    }
    lkBody.innerHTML = "";
    linkRows.forEach(function (r) {
      var tr = document.createElement("tr");
      var eqLabel = r.eq_hostname || r.eq_serial || "#" + r.id_equipamento;
      [
        r.id_link,
        eqLabel,
        r.tipo_link,
        r.modo_conexao,
        r.ip_address,
        r.operadora,
        V.yesNo(r.ativo),
      ].forEach(function (cell) {
        var td = document.createElement("td");
        td.textContent = cell != null && cell !== "" ? String(cell) : "—";
        tr.appendChild(td);
      });
      lkBody.appendChild(tr);
    });
  }

  function loadUnidadeDetalhe(idUnidade) {
    if (!idUnidade) {
      clearUnidadePainel();
      return Promise.resolve();
    }
    return Promise.all([
      V.jsonFetch("/vgr/api/unidades/" + encodeURIComponent(idUnidade)),
      V.jsonFetch("/vgr/api/unidades/" + encodeURIComponent(idUnidade) + "/equipamentos"),
      V.jsonFetch("/vgr/api/unidades/" + encodeURIComponent(idUnidade) + "/links"),
    ]).then(function (res) {
      if (res[0].status >= 400 || !res[0].d.success) {
        clearUnidadePainel();
        V.toast((res[0].d && res[0].d.message) || "Unidade não carregada.", false);
        return;
      }
      fillUnidadePainel(res[0].d.data || {});
      renderEqLinks((res[1].d && res[1].d.data) || [], (res[2].d && res[2].d.data) || []);
    });
  }

  function loadUnidades(selectedId) {
    return V.jsonFetch("/vgr/api/unidades").then(function (res) {
      unidadesCache = (res.d && res.d.data) || [];
      var sel = document.getElementById("vgrAgUnidade");
      sel.innerHTML = '<option value="">Selecione...</option>';
      unidadesCache
        .filter(function (r) {
          return Number(r.ativo) === 1 || String(r.id_unidade) === String(selectedId || "");
        })
        .forEach(function (r) {
          var opt = document.createElement("option");
          opt.value = String(r.id_unidade);
          opt.textContent =
            (r.nome_unidade || "#" + r.id_unidade) +
            (r.id_vgr ? " [" + r.id_vgr + "]" : "") +
            (Number(r.ha) === 1 ? " [HA]" : "") +
            (r.razao_social ? " — " + r.razao_social : "");
          sel.appendChild(opt);
        });
      if (selectedId) sel.value = String(selectedId);
      return unidadesCache;
    });
  }

  function findUnidadeByIdVgr(idVgr) {
    var q = String(idVgr || "").trim().toLowerCase();
    if (!q) return null;
    for (var i = 0; i < unidadesCache.length; i++) {
      var u = unidadesCache[i];
      if (String(u.id_vgr || "").trim().toLowerCase() === q) return u;
    }
    return null;
  }

  function loadFields(selectedIds) {
    return V.jsonFetch("/vgr/api/fields").then(function (res) {
      var rows = (res.d && res.d.data) || [];
      var sel = document.getElementById("vgrAgFields");
      var selected = {};
      (selectedIds || []).forEach(function (id) {
        selected[String(id)] = true;
      });
      sel.innerHTML = "";
      rows
        .filter(function (r) {
          return Number(r.ativo) === 1 || selected[String(r.id_field)];
        })
        .forEach(function (r) {
          var opt = document.createElement("option");
          opt.value = String(r.id_field);
          opt.textContent =
            (r.nome || "#" + r.id_field) + (r.telefone ? " — " + r.telefone : "");
          opt.selected = !!selected[String(r.id_field)];
          sel.appendChild(opt);
        });
      return rows;
    });
  }

  function selectedFields() {
    var sel = document.getElementById("vgrAgFields");
    return Array.prototype.filter
      .call(sel.options, function (o) {
        return o.selected;
      })
      .map(function (o) {
        return parseInt(o.value, 10);
      });
  }

  function clearForm() {
    buildChecklist();
    document.getElementById("vgrAgId").value = "";
    document.getElementById("vgrAgData").value = "";
    document.getElementById("vgrAgHora").value = "";
    document.getElementById("vgrAgHoraIni").value = "";
    document.getElementById("vgrAgHoraFim").value = "";
    document.getElementById("vgrAgAnalista").value = "";
    document.getElementById("vgrAgLivre").checked = false;
    document.getElementById("vgrAgSub").value = "";
    document.getElementById("vgrAgObs").value = "";
    document.querySelectorAll(".vgr-ag-q").forEach(function (el) {
      el.checked = false;
    });
    fillSelect(
      document.getElementById("vgrAgStatus"),
      catalogo.status,
      "Pendente envio a logística"
    );
    fillSelect(document.getElementById("vgrAgTipo"), catalogo.tipos, "", true);
    document.getElementById("btnVgrAgConfirmar").classList.add("d-none");
    document.getElementById("btnVgrAgImprodutivo").classList.add("d-none");
    clearUnidadePainel();
    showErr("");
    var tabBtn = document.getElementById("vgrAgTabUnidadeBtn");
    if (tabBtn && window.bootstrap && bootstrap.Tab) {
      bootstrap.Tab.getOrCreateInstance(tabBtn).show();
    }
  }

  function timeVal(v) {
    if (!v) return "";
    return String(v).slice(0, 5);
  }

  function fillForm(d) {
    buildChecklist();
    document.getElementById("vgrAgId").value = d.id_agendamento || "";
    fillSelect(
      document.getElementById("vgrAgStatus"),
      catalogo.status,
      d.status_agendamento || ""
    );
    fillSelect(document.getElementById("vgrAgTipo"), catalogo.tipos, d.tipo || "", true);
    document.getElementById("vgrAgData").value = d.data_agendamento
      ? String(d.data_agendamento).slice(0, 10)
      : "";
    document.getElementById("vgrAgHora").value = timeVal(d.hora_agendamento);
    document.getElementById("vgrAgHoraIni").value = timeVal(d.hora_inicio);
    document.getElementById("vgrAgHoraFim").value = timeVal(d.hora_fim);
    document.getElementById("vgrAgAnalista").value = d.analista_destino || "";
    document.getElementById("vgrAgLivre").checked = Number(d.analista_livre) === 1;
    document.getElementById("vgrAgSub").value = d.substatus_agendamento || "";
    document.getElementById("vgrAgObs").value = d.observacoes || "";
    CHECKLIST.forEach(function (pair) {
      var el = document.getElementById(pair[0]);
      if (el) el.checked = Number(d[pair[0]]) === 1;
    });
    var isAg = d.status_agendamento === catalogo.status_agendado;
    document.getElementById("btnVgrAgConfirmar").classList.toggle("d-none", isAg);
    document.getElementById("btnVgrAgImprodutivo").classList.remove("d-none");
    showErr("");
  }

  function readForm() {
    var payload = {
      id_unidade: document.getElementById("vgrAgUnidade").value,
      status_agendamento: document.getElementById("vgrAgStatus").value,
      substatus_agendamento: document.getElementById("vgrAgSub").value,
      data_agendamento: document.getElementById("vgrAgData").value || null,
      hora_agendamento: document.getElementById("vgrAgHora").value || null,
      hora_inicio: document.getElementById("vgrAgHoraIni").value || null,
      hora_fim: document.getElementById("vgrAgHoraFim").value || null,
      tipo: document.getElementById("vgrAgTipo").value || null,
      analista_destino: document.getElementById("vgrAgAnalista").value,
      analista_livre: document.getElementById("vgrAgLivre").checked ? 1 : 0,
      observacoes: document.getElementById("vgrAgObs").value,
      id_fields: selectedFields(),
    };
    CHECKLIST.forEach(function (pair) {
      var el = document.getElementById(pair[0]);
      payload[pair[0]] = el && el.checked ? 1 : 0;
    });
    return payload;
  }

  var listUrl =
    "/vgr/api/agendamentos" +
    (modo === "gestao" ? "?modo=gestao" : "?apenas_ativos=1");

  const api = $("#tblVgrAgendamentos").DataTable(
    V.baseOpts({
      order: [[0, "desc"]],
      ajax: V.clientAjax(listUrl),
      columns: [
        { data: "id_agendamento" },
        {
          data: "razao_social",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "nome_unidade",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "status_agendamento",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "data_agendamento",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "tipo",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "analista_destino",
          render: function (d, t, row) {
            if (Number(row.analista_livre) === 1) {
              return t === "display" || t === "filter" ? "Livre" : "Livre";
            }
            return V.renderText(d, t);
          },
        },
        {
          data: "ha",
          render: function (d) {
            return V.yesNo(d);
          },
        },
        {
          data: "id_atendimento",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "fields_count",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "ativo",
          render: function (d) {
            return V.yesNo(d);
          },
        },
        {
          data: null,
          orderable: false,
          searchable: false,
          className: "col-acoes portal-dt-acoes",
          render: function (_d, _t, row) {
            return V.acoesAgendamento(row.id_agendamento, row.ativo, row.status_agendamento);
          },
        },
      ],
      columnDefs: [
        { targets: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], columnControl: cc },
        { targets: [-1], columnControl: [] },
      ],
    })
  );

  function reload() {
    api.ajax.reload(null, false);
  }

  V.mountToolbar("tblVgrAgendamentos", api);

  document.getElementById("vgrAgUnidade").addEventListener("change", function () {
    loadUnidadeDetalhe(this.value);
  });

  document.getElementById("vgrAgIdVgr").addEventListener("change", function () {
    var found = findUnidadeByIdVgr(this.value);
    if (!found) {
      V.toast("ID VGR não encontrado nas unidades carregadas.", false);
      return;
    }
    document.getElementById("vgrAgUnidade").value = String(found.id_unidade);
    loadUnidadeDetalhe(found.id_unidade);
  });

  function openCreate() {
    clearForm();
    document.getElementById("modalVgrAgTitle").textContent = "Novo agendamento";
    Promise.all([loadUnidades(null), loadFields([])]).then(function () {
      if (modal) modal.show();
    });
  }

  function openEdit(id) {
    clearForm();
    document.getElementById("modalVgrAgTitle").textContent = "Editar agendamento #" + id;
    if (modal) modal.show();
    V.jsonFetch("/vgr/api/agendamentos/" + encodeURIComponent(id)).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Agendamento não encontrado.", false);
        if (modal) modal.hide();
        return;
      }
      var d = res.d.data || {};
      Promise.all([loadUnidades(d.id_unidade), loadFields(d.id_fields || [])]).then(
        function () {
          fillForm(d);
          return loadUnidadeDetalhe(d.id_unidade);
        }
      );
    });
  }

  function confirmarAgendado(id) {
    if (
      !window.confirm(
        "Confirmar Agendado? Será criado/vinculado o atendimento 1→1 e a agenda será publicada."
      )
    ) {
      return;
    }
    V.jsonFetch(
      "/vgr/api/agendamentos/" + encodeURIComponent(id) + "/confirmar-agendado",
      { method: "POST", body: JSON.stringify({ confirmar: true }) }
    ).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Falha ao confirmar.", false);
        showErr((res.d && res.d.message) || "Falha ao confirmar.");
        return;
      }
      V.toast(res.d.message || "Agendado.", true);
      if (modal) modal.hide();
      reload();
    });
  }

  function marcarImprodutivo(id) {
    if (
      !window.confirm(
        "Marcar como Improdutiva? Em seguida crie um NOVO agendamento para reagendar (P3)."
      )
    ) {
      return;
    }
    V.jsonFetch("/vgr/api/agendamentos/" + encodeURIComponent(id) + "/improdutivo", {
      method: "POST",
      body: JSON.stringify({}),
    }).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Falha.", false);
        return;
      }
      V.toast(res.d.message || "Improdutiva.", true);
      if (modal) modal.hide();
      reload();
    });
  }

  V.jsonFetch("/vgr/api/agendamentos/catalogo").then(function (res) {
    if (res.d && res.d.success) catalogo = res.d.data || catalogo;
    buildChecklist();
  });

  var btnNovo = document.getElementById("btnVgrAgNovo");
  if (btnNovo) btnNovo.addEventListener("click", openCreate);

  var btnSalvar = document.getElementById("btnVgrAgSalvar");
  if (btnSalvar) {
    btnSalvar.addEventListener("click", function () {
      showErr("");
      var id = document.getElementById("vgrAgId").value;
      var body = readForm();
      if (!body.id_unidade) {
        showErr("Selecione a unidade (aba Dados Unidade e Conectividade).");
        return;
      }
      if (!id && body.status_agendamento === catalogo.status_agendado) {
        showErr("Crie o agendamento e depois use Confirmar Agendado.");
        return;
      }
      var url = id
        ? "/vgr/api/agendamentos/" + encodeURIComponent(id)
        : "/vgr/api/agendamentos";
      var method = id ? "PUT" : "POST";
      btnSalvar.disabled = true;
      V.jsonFetch(url, { method: method, body: JSON.stringify(body) })
        .then(function (res) {
          if (res.status >= 400 || !res.d.success) {
            showErr((res.d && res.d.message) || "Falha ao salvar.");
            V.toast((res.d && res.d.message) || "Falha ao salvar.", false);
            return;
          }
          V.toast(res.d.message || "Salvo.", true);
          if (modal) modal.hide();
          reload();
        })
        .finally(function () {
          btnSalvar.disabled = false;
        });
    });
  }

  document.getElementById("btnVgrAgConfirmar").addEventListener("click", function () {
    var id = document.getElementById("vgrAgId").value;
    if (id) confirmarAgendado(id);
  });
  document.getElementById("btnVgrAgImprodutivo").addEventListener("click", function () {
    var id = document.getElementById("vgrAgId").value;
    if (id) marcarImprodutivo(id);
  });
  var btnEqNovo = document.getElementById("btnVgrAgEqNovo");
  if (btnEqNovo) {
    btnEqNovo.addEventListener("click", function () {
      vgrCreateNewEqInline();
    });
  }

  $("#tblVgrAgendamentos").on("click", ".vgr-ag-edit", function () {
    openEdit(this.getAttribute("data-id"));
  });
  $("#tblVgrAgendamentos").on("click", ".vgr-ag-confirmar", function () {
    confirmarAgendado(this.getAttribute("data-id"));
  });
  $("#tblVgrAgendamentos").on("click", ".vgr-ag-improdutivo", function () {
    marcarImprodutivo(this.getAttribute("data-id"));
  });
  $("#tblVgrAgendamentos").on("click", ".vgr-ag-desativar", function () {
    var id = this.getAttribute("data-id");
    if (!window.confirm("Desativar agendamento #" + id + "?")) return;
    V.jsonFetch("/vgr/api/agendamentos/" + encodeURIComponent(id) + "/desativar", {
      method: "POST",
      body: "{}",
    }).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Falha.", false);
        return;
      }
      reload();
    });
  });
  $("#tblVgrAgendamentos").on("click", ".vgr-ag-reativar", function () {
    var id = this.getAttribute("data-id");
    V.jsonFetch("/vgr/api/agendamentos/" + encodeURIComponent(id) + "/reativar", {
      method: "POST",
      body: "{}",
    }).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Falha.", false);
        return;
      }
      reload();
    });
  });
})();
