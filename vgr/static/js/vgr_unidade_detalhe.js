(function () {
  "use strict";
  const V = window.VgrDt;
  const id = window.VGR_UNIDADE_ID;
  if (!V || !id || typeof $ === "undefined" || !$.fn.DataTable) return;

  const cc = window.PortalDt ? window.PortalDt.ccSearchList() : [];
  const modalEqEl = document.getElementById("modalVgrEq");
  const modalLinkEl = document.getElementById("modalVgrLink");
  const modalEq =
    modalEqEl && window.bootstrap ? new bootstrap.Modal(modalEqEl) : null;
  const modalLink =
    modalLinkEl && window.bootstrap ? new bootstrap.Modal(modalLinkEl) : null;
  const errEq = document.getElementById("vgrEqErro");
  const errLink = document.getElementById("vgrLinkErro");
  /* Regras de campo VGR (espelho do backend + core). */
  const R = window.VgrFieldRules || null;
  const liveEq = R
    ? R.bindEqLive({
        serial: "vgrEqSerial",
        vendor: "vgrEqVendor",
        modelo: "vgrEqModelo",
        hostname: "vgrEqHostname",
        tktNoc: "vgrEqTktNoc",
      })
    : null;
  const liveLink = R
    ? R.bindLinkLive({
        tipo: "vgrLinkTipo",
        modo: "vgrLinkModo",
        operadora: "vgrLinkOperadora",
        operadoraOutros: "vgrLinkOperadoraOutros",
        idVgr: "vgrLinkIdVgr",
        porta: "vgrLinkPorta",
        designador: "vgrLinkDesignador",
        ip: "vgrLinkIp",
        mascara: "vgrLinkMascara",
        gateway: "vgrLinkGateway",
        subrede: "vgrLinkSubrede",
        rangeStart: "vgrLinkRangeStart",
        rangeEnd: "vgrLinkRangeEnd",
        vlan: "vgrLinkVlan",
        vel: "vgrLinkVel",
        pendencias: "vgrLinkPendencias",
      })
    : null;
  /* PPPoE já gravado (cifrado): satisfaz obrigatoriedade sem reenviar. */
  var linkPppoeFlags = { user: false, pass: false };

  function colEsc(field) {
    return {
      data: field,
      render: function (d, t) {
        return V.renderText(d, t);
      },
    };
  }

  function showErr(el, msg) {
    if (!el) return;
    if (msg) {
      el.textContent = msg;
      el.classList.remove("d-none");
    } else {
      el.textContent = "";
      el.classList.add("d-none");
    }
  }

  function resetEqForm() {
    document.getElementById("vgrEqId").value = "";
    document.getElementById("vgrEqSerial").value = "";
    V.fillSelectOptions(
      document.getElementById("vgrEqVendor"),
      V.VENDORS,
      "",
      { emptyLabel: "Selecione..." }
    );
    document.getElementById("vgrEqModelo").value = "";
    document.getElementById("vgrEqHostname").value = "";
    document.getElementById("vgrEqTipo").value = "";
    document.getElementById("vgrEqLicenca").value = "";
    document.getElementById("vgrEqTktSae").value = "";
    document.getElementById("vgrEqTktNoc").value = "";
    document.getElementById("vgrEqFortcloud").value = "";
    document.getElementById("vgrEqFortcloudHint").textContent = "";
    showErr(errEq, null);
    if (R) R.clearStates(modalEqEl);
  }

  function fillEqForm(d) {
    document.getElementById("vgrEqId").value = d.id_equipamento || "";
    document.getElementById("vgrEqSerial").value = d.serial || "";
    V.fillSelectOptions(
      document.getElementById("vgrEqVendor"),
      V.VENDORS,
      d.vendor || "",
      { emptyLabel: "Selecione...", normalizeVendor: true }
    );
    document.getElementById("vgrEqModelo").value = d.modelo || "";
    document.getElementById("vgrEqHostname").value = d.hostname || "";
    document.getElementById("vgrEqTipo").value = d.tipo_servico || "";
    document.getElementById("vgrEqLicenca").value = d.licenca || "";
    document.getElementById("vgrEqTktSae").value = d.tkt_sae || "";
    document.getElementById("vgrEqTktNoc").value = d.tkt_noc || "";
    document.getElementById("vgrEqFortcloud").value = "";
    document.getElementById("vgrEqFortcloudHint").textContent = d.has_fortcloud_key
      ? "Já existe chave cadastrada. Em branco mantém a atual."
      : "Nenhuma chave cadastrada.";
    showErr(errEq, null);
    if (R) R.clearStates(modalEqEl);
    if (liveEq) liveEq.refresh();
  }

  function collectEqPayload() {
    var payload = {
      serial: document.getElementById("vgrEqSerial").value,
      vendor: document.getElementById("vgrEqVendor").value,
      modelo: document.getElementById("vgrEqModelo").value,
      hostname: document.getElementById("vgrEqHostname").value,
      tipo_servico: document.getElementById("vgrEqTipo").value,
      licenca: document.getElementById("vgrEqLicenca").value,
      tkt_sae: document.getElementById("vgrEqTktSae").value,
      tkt_noc: document.getElementById("vgrEqTktNoc").value,
    };
    var fk = document.getElementById("vgrEqFortcloud").value;
    if (fk && String(fk).trim() !== "") {
      payload.fortcloud_key = fk;
    }
    return payload;
  }

  function clientValidateEq(payload) {
    if (R) return R.validateEqPayload(payload);
    var PF = window.PortalFieldValidation;
    if (!PF) return null;
    if (PF.isFortinetFamily(payload.vendor, payload.modelo)) {
      var errS = PF.validateSerialFortinet(payload.serial, { obrigatorio: true });
      if (errS) return errS;
    }
    if (payload.hostname && /\s/.test(String(payload.hostname).trim())) {
      return "O campo «Hostname» não pode conter espaços.";
    }
    if (payload.tkt_noc) {
      var errT = PF.validateTicketNoc(payload.tkt_noc);
      if (errT) return errT;
    }
    return null;
  }

  var linkFormScope = "wan"; /* wan | unidade */

  function clientValidateLink(payload) {
    if (R) return R.validateLinkPayload(payload);
    var PF = window.PortalFieldValidation;
    if (!PF) return null;
    if (payload.tipo_link === "WAN" && !payload.id_equipamento) {
      return "Selecione o equipamento.";
    }
    if (payload.designador) {
      payload.designador = PF.sanitizePastedText(payload.designador);
    }
    if (payload.ip_address) {
      var errIp = PF.validateIpv4(payload.ip_address, {
        label: "IP",
        allowCidr: true,
      });
      if (errIp) return errIp;
    }
    if (payload.gateway) {
      var errGw = PF.validateIpv4(payload.gateway, { label: "Gateway" });
      if (errGw) return errGw;
    }
    if (PF.wanEqualsGateway(payload.ip_address, payload.gateway)) {
      return "IP e Gateway não podem ser iguais.";
    }
    return null;
  }

  function setLinkFormScope(scope, selectedTipo) {
    linkFormScope = scope === "unidade" ? "unidade" : "wan";
    V.fillTipoLinkSelect(
      document.getElementById("vgrLinkTipo"),
      linkFormScope,
      selectedTipo || (linkFormScope === "wan" ? "WAN" : "LAN")
    );
    V.syncLinkFormFields("vgrLink");
  }

  function resetLinkForm(scope) {
    document.getElementById("vgrLinkId").value = "";
    document.getElementById("vgrLinkModo").value = "";
    linkPppoeFlags = { user: false, pass: false };
    if (R) {
      R.fillOperadora("vgrLinkOperadora", "vgrLinkOperadoraOutros", "");
    } else {
      V.fillSelectOptions(
        document.getElementById("vgrLinkOperadora"),
        V.OPERADORAS,
        "",
        { emptyLabel: "Selecione..." }
      );
    }
    document.getElementById("vgrLinkSubrede").value = "";
    document.getElementById("vgrLinkRangeStart").value = "";
    document.getElementById("vgrLinkRangeEnd").value = "";
    document.getElementById("vgrLinkIdVgr").value = "";
    document.getElementById("vgrLinkPorta").value = "";
    document.getElementById("vgrLinkDesignador").value = "";
    document.getElementById("vgrLinkIp").value = "";
    document.getElementById("vgrLinkMascara").value = "";
    document.getElementById("vgrLinkGateway").value = "";
    document.getElementById("vgrLinkVlan").value = "";
    document.getElementById("vgrLinkVel").value = "";
    document.getElementById("vgrLinkPppoeUser").value = "";
    document.getElementById("vgrLinkPppoePass").value = "";
    showErr(errLink, null);
    setLinkFormScope(scope || "wan");
    if (R) {
      R.clearStates(modalLinkEl);
      R.renderPendencias("vgrLinkPendencias", []);
    }
  }

  function fillLinkForm(d) {
    document.getElementById("vgrLinkId").value = d.id_link || "";
    document.getElementById("vgrLinkEq").value = String(d.id_equipamento || "");
    var scope = V.isLinkTipoUnidade(d.tipo_link) ? "unidade" : "wan";
    setLinkFormScope(scope, d.tipo_link || "WAN");
    document.getElementById("vgrLinkModo").value = d.modo_conexao || "";
    linkPppoeFlags = {
      user: Number(d.has_pppoe_user) === 1,
      pass: Number(d.has_pppoe_pass) === 1,
    };
    if (R) {
      R.fillOperadora("vgrLinkOperadora", "vgrLinkOperadoraOutros", d.operadora || "");
    } else {
      V.fillSelectOptions(
        document.getElementById("vgrLinkOperadora"),
        V.OPERADORAS,
        d.operadora || "",
        { emptyLabel: "Selecione..." }
      );
    }
    document.getElementById("vgrLinkSubrede").value = d.subrede || "";
    document.getElementById("vgrLinkRangeStart").value = d.range_start || "";
    document.getElementById("vgrLinkRangeEnd").value = d.range_end || "";
    document.getElementById("vgrLinkIdVgr").value = d.id_vgr_link || "";
    document.getElementById("vgrLinkPorta").value = d.identificador || "";
    document.getElementById("vgrLinkDesignador").value = d.designador || "";
    document.getElementById("vgrLinkIp").value = d.ip_address || "";
    document.getElementById("vgrLinkMascara").value = d.mascara || "";
    document.getElementById("vgrLinkGateway").value = d.gateway || "";
    document.getElementById("vgrLinkVlan").value = d.vlan || "";
    document.getElementById("vgrLinkVel").value = d.velocidade || "";
    document.getElementById("vgrLinkPppoeUser").value = "";
    document.getElementById("vgrLinkPppoePass").value = "";
    showErr(errLink, null);
    V.syncLinkFormFields("vgrLink");
    if (R) {
      R.clearStates(modalLinkEl);
      /* normaliza velocidade legada ("300 Mbps" → 300) e recalcula estados */
      document.getElementById("vgrLinkVel").dispatchEvent(new Event("blur"));
      if (liveLink) liveLink.refresh();
    }
  }

  function collectLinkPayload() {
    var tipo = document.getElementById("vgrLinkTipo").value;
    var modo = document.getElementById("vgrLinkModo").value || null;
    if (tipo !== "WAN") modo = null;
    var opr = R
      ? R.readOperadora("vgrLinkOperadora", "vgrLinkOperadoraOutros")
      : { select: document.getElementById("vgrLinkOperadora").value, operadora: document.getElementById("vgrLinkOperadora").value, outros: "" };
    var payload = {
      tipo_link: tipo,
      modo_conexao: modo,
      operadora: tipo === "WAN" ? opr.operadora : "",
      operadora_outros: tipo === "WAN" ? opr.outros : "",
      _operadora_select: opr.select,
      _has_pppoe_user: linkPppoeFlags.user,
      _has_pppoe_pass: linkPppoeFlags.pass,
      subrede: document.getElementById("vgrLinkSubrede").value,
      range_start: document.getElementById("vgrLinkRangeStart").value,
      range_end: document.getElementById("vgrLinkRangeEnd").value,
      id_vgr_link: tipo === "WAN" ? document.getElementById("vgrLinkIdVgr").value : "",
      identificador: tipo === "WAN" ? document.getElementById("vgrLinkPorta").value : "",
      designador: tipo === "WAN" ? document.getElementById("vgrLinkDesignador").value : "",
      ip_address: document.getElementById("vgrLinkIp").value,
      mascara: document.getElementById("vgrLinkMascara").value,
      gateway: tipo === "WAN" ? document.getElementById("vgrLinkGateway").value : "",
      vlan: document.getElementById("vgrLinkVlan").value,
      velocidade: tipo === "WAN" ? document.getElementById("vgrLinkVel").value : "",
    };
    if (tipo === "WAN") {
      payload.id_equipamento = document.getElementById("vgrLinkEq").value;
    } else {
      payload.id_equipamento = null;
    }
    var pu = document.getElementById("vgrLinkPppoeUser").value;
    var pp = document.getElementById("vgrLinkPppoePass").value;
    if (pu && String(pu).trim() !== "") payload.pppoe_user = pu;
    if (pp && String(pp).trim() !== "") payload.pppoe_pass = pp;
    /* campos que não se aplicam ao tipo/modo não vão preenchidos (ocultos) */
    return R ? R.cleanLinkPayload(payload) : payload;
  }

  function fillEqSelect(rows, selectedId) {
    var sel = document.getElementById("vgrLinkEq");
    if (!sel) return;
    sel.innerHTML = "";
    (rows || []).forEach(function (r) {
      if (Number(r.ativo) !== 1 && String(r.id_equipamento) !== String(selectedId || "")) {
        return;
      }
      var opt = document.createElement("option");
      opt.value = String(r.id_equipamento);
      var label =
        (r.hostname || r.serial || "#" + r.id_equipamento) +
        (r.serial ? " (" + r.serial + ")" : "");
      opt.textContent = label;
      sel.appendChild(opt);
    });
    if (selectedId) sel.value = String(selectedId);
  }

  function loadEqOptions(selectedId) {
    return V.jsonFetch("/vgr/api/unidades/" + encodeURIComponent(id) + "/equipamentos").then(
      function (res) {
        var rows = (res.d && res.d.data) || [];
        fillEqSelect(rows, selectedId);
        return rows;
      }
    );
  }

  const apiEq = $("#tblVgrUnidadeEq").DataTable(
    V.baseOpts({
      order: [[0, "asc"]],
      ajax: V.clientAjax("/vgr/api/unidades/" + id + "/equipamentos"),
      columns: [
        { data: "id_equipamento" },
        colEsc("vendor"),
        colEsc("modelo"),
        colEsc("serial"),
        colEsc("hostname"),
        colEsc("tipo_servico"),
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
          render: function (_d, t, row) {
            if (t !== "display") return "";
            return V.acoesEquipamento(row.id_equipamento, row.ativo);
          },
        },
      ],
      columnDefs: [
        { targets: [1, 2, 3, 4, 5, 6], columnControl: cc },
        { targets: -1, orderable: false, searchable: false },
      ],
    })
  );
  V.mountToolbar("tblVgrUnidadeEq", apiEq);

  const apiLk = $("#tblVgrUnidadeLinks").DataTable(
    V.baseOpts({
      order: [[0, "asc"]],
      ajax: V.clientAjax("/vgr/api/unidades/" + id + "/links", function (r) {
        return V.isLinkTipoWan(r.tipo_link);
      }),
      columns: [
        { data: "id_link" },
        {
          data: "eq_hostname",
          render: function (d, t, row) {
            if (t !== "display") return d;
            var label = d || row.eq_serial || "#" + row.id_equipamento;
            return V.esc(label);
          },
        },
        colEsc("tipo_link"),
        colEsc("modo_conexao"),
        colEsc("designador"),
        colEsc("ip_address"),
        colEsc("operadora"),
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
          render: function (_d, t, row) {
            if (t !== "display") return "";
            return V.acoesLink(row.id_link, row.ativo);
          },
        },
      ],
      columnDefs: [
        { targets: [1, 2, 3, 4, 5, 6, 7], columnControl: cc },
        { targets: -1, orderable: false, searchable: false },
      ],
    })
  );
  V.mountToolbar("tblVgrUnidadeLinks", apiLk);

  const apiConn = $("#tblVgrUnidadeConn").DataTable(
    V.baseOpts({
      order: [[0, "asc"]],
      ajax: V.clientAjax("/vgr/api/unidades/" + id + "/links", function (r) {
        return V.isLinkTipoUnidade(r.tipo_link);
      }),
      columns: [
        { data: "id_link" },
        colEsc("tipo_link"),
        colEsc("ip_address"),
        colEsc("mascara"),
        colEsc("vlan"),
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
          render: function (_d, t, row) {
            if (t !== "display") return "";
            return V.acoesLink(row.id_link, row.ativo);
          },
        },
      ],
      columnDefs: [
        { targets: [1, 2, 3, 4, 5], columnControl: cc },
        { targets: -1, orderable: false, searchable: false },
      ],
    })
  );
  V.mountToolbar("tblVgrUnidadeConn", apiConn);

  function reloadLinkTables() {
    apiLk.ajax.reload(null, false);
    apiConn.ajax.reload(null, false);
  }

  const apiAg = $("#tblVgrUnidadeAg").DataTable(
    V.baseOpts({
      order: [[0, "desc"]],
      ajax: V.clientAjax("/vgr/api/unidades/" + id + "/agendamentos"),
      columns: [
        { data: "id_agendamento" },
        colEsc("status_agendamento"),
        colEsc("data_agendamento"),
        colEsc("tipo"),
        colEsc("analista_destino"),
        {
          data: "ativo",
          render: function (d) {
            return V.yesNo(d);
          },
        },
      ],
      columnDefs: [{ targets: [1, 2, 3, 4, 5], columnControl: cc }],
    })
  );
  V.mountToolbar("tblVgrUnidadeAg", apiAg);

  const apiAt = $("#tblVgrUnidadeAt").DataTable(
    V.baseOpts({
      order: [[0, "desc"]],
      ajax: V.clientAjax("/vgr/api/unidades/" + id + "/atendimentos"),
      columns: [
        { data: "id_atendimento" },
        colEsc("status_atendimento"),
        colEsc("substatus_atendimento"),
        colEsc("analista_atuante"),
        {
          data: "id_agendamento",
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
      ],
      columnDefs: [{ targets: [1, 2, 3, 4, 5], columnControl: cc }],
    })
  );
  V.mountToolbar("tblVgrUnidadeAt", apiAt);

  function openEqCreate() {
    resetEqForm();
    document.getElementById("modalVgrEqTitle").textContent = "Novo equipamento";
    if (modalEq) modalEq.show();
  }

  function openEqEdit(eqId) {
    V.jsonFetch("/vgr/api/equipamentos/" + encodeURIComponent(eqId)).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Falha ao carregar equipamento.", false);
        return;
      }
      fillEqForm(res.d.data || {});
      document.getElementById("modalVgrEqTitle").textContent =
        "Editar equipamento #" + eqId;
      if (modalEq) modalEq.show();
    });
  }

  function openLinkCreate(scope) {
    resetLinkForm(scope || "wan");
    if (linkFormScope === "unidade") {
      document.getElementById("modalVgrLinkTitle").textContent = "Nova conectividade";
      if (modalLink) modalLink.show();
      return;
    }
    loadEqOptions(null).then(function (rows) {
      if (!rows.length) {
        V.toast("Cadastre um equipamento ativo antes de criar link WAN.", false);
        return;
      }
      document.getElementById("modalVgrLinkTitle").textContent = "Novo link WAN";
      if (modalLink) modalLink.show();
    });
  }

  function openLinkEdit(linkId) {
    V.jsonFetch("/vgr/api/links/" + encodeURIComponent(linkId)).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Falha ao carregar link.", false);
        return;
      }
      var d = res.d.data || {};
      var after = function () {
        fillLinkForm(d);
        document.getElementById("modalVgrLinkTitle").textContent =
          V.isLinkTipoUnidade(d.tipo_link)
            ? "Editar conectividade #" + linkId
            : "Editar link WAN #" + linkId;
        if (modalLink) modalLink.show();
      };
      if (V.isLinkTipoUnidade(d.tipo_link)) {
        after();
      } else {
        loadEqOptions(d.id_equipamento).then(after);
      }
    });
  }

  var btnEqNovo = document.getElementById("btnVgrEqNovo");
  if (btnEqNovo) btnEqNovo.addEventListener("click", openEqCreate);

  var btnEqSalvar = document.getElementById("btnVgrEqSalvar");
  if (btnEqSalvar) {
    btnEqSalvar.addEventListener("click", function () {
      showErr(errEq, null);
      var eqId = document.getElementById("vgrEqId").value;
      var payload = collectEqPayload();
      var clientErr = clientValidateEq(payload);
      if (clientErr) {
        showErr(errEq, clientErr);
        return;
      }
      var body = JSON.stringify(payload);
      var url = eqId
        ? "/vgr/api/equipamentos/" + encodeURIComponent(eqId)
        : "/vgr/api/unidades/" + encodeURIComponent(id) + "/equipamentos";
      var method = eqId ? "PUT" : "POST";
      V.jsonFetch(url, { method: method, body: body }).then(function (res) {
        if (res.status >= 400 || !res.d.success) {
          showErr(errEq, (res.d && res.d.message) || "Falha ao salvar.");
          return;
        }
        if (modalEq) modalEq.hide();
        V.toast(res.d.message || "Salvo.", true);
        apiEq.ajax.reload(null, false);
        reloadLinkTables();
      });
    });
  }

  var btnLinkNovo = document.getElementById("btnVgrLinkNovo");
  if (btnLinkNovo) btnLinkNovo.addEventListener("click", function () {
    openLinkCreate("wan");
  });
  var btnConnNovo = document.getElementById("btnVgrConnNovo");
  if (btnConnNovo) btnConnNovo.addEventListener("click", function () {
    openLinkCreate("unidade");
  });

  var btnLinkSalvar = document.getElementById("btnVgrLinkSalvar");
  if (btnLinkSalvar) {
    btnLinkSalvar.addEventListener("click", function () {
      showErr(errLink, null);
      var linkId = document.getElementById("vgrLinkId").value;
      var payload = collectLinkPayload();
      var clientErr = clientValidateLink(payload);
      if (clientErr) {
        showErr(errLink, clientErr);
        return;
      }
      var apiPayload = R ? R.stripInternal(payload) : payload;
      var body = JSON.stringify(apiPayload);
      var url = linkId
        ? "/vgr/api/links/" + encodeURIComponent(linkId)
        : "/vgr/api/unidades/" + encodeURIComponent(id) + "/links";
      var method = linkId ? "PUT" : "POST";
      var uniqBody = JSON.stringify(
        Object.assign({}, apiPayload, {
          id_unidade: id,
          exclude_id: linkId || null,
        })
      );
      V.jsonFetch("/vgr/api/links/check-uniqueness", {
        method: "POST",
        body: uniqBody,
      }).then(function (pre) {
        if (pre.status === 409 || (pre.d && pre.d.unique === false)) {
          showErr(errLink, (pre.d && pre.d.message) || "Conflito de unicidade.");
          return null;
        }
        if (pre.status >= 400 && pre.d && pre.d.success === false) {
          showErr(errLink, (pre.d && pre.d.message) || "Falha na verificação.");
          return null;
        }
        return V.jsonFetch(url, { method: method, body: body });
      }).then(function (res) {
        if (!res) return;
        if (res.status >= 400 || !res.d.success) {
          showErr(errLink, (res.d && res.d.message) || "Falha ao salvar.");
          return;
        }
        if (modalLink) modalLink.hide();
        V.toast(res.d.message || "Salvo.", true);
        if (R) R.toastAvisos(res.d.avisos);
        reloadLinkTables();
      });
    });
  }

  $("#tblVgrUnidadeEq").on("click", ".vgr-eq-edit", function () {
    openEqEdit(this.getAttribute("data-id"));
  });
  $("#tblVgrUnidadeEq").on("click", ".vgr-eq-desativar", function () {
    var eqId = this.getAttribute("data-id");
    if (!window.confirm("Desativar equipamento #" + eqId + "?")) return;
    V.jsonFetch("/vgr/api/equipamentos/" + encodeURIComponent(eqId) + "/desativar", {
      method: "POST",
      body: "{}",
    }).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Falha ao desativar.", false);
        return;
      }
      V.toast(res.d.message || "Desativado.", true);
      apiEq.ajax.reload(null, false);
    });
  });
  $("#tblVgrUnidadeEq").on("click", ".vgr-eq-reativar", function () {
    var eqId = this.getAttribute("data-id");
    V.jsonFetch("/vgr/api/equipamentos/" + encodeURIComponent(eqId) + "/reativar", {
      method: "POST",
      body: "{}",
    }).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Falha ao reativar.", false);
        return;
      }
      V.toast(res.d.message || "Reativado.", true);
      apiEq.ajax.reload(null, false);
    });
  });

  $("#tblVgrUnidadeLinks, #tblVgrUnidadeConn").on("click", ".vgr-link-edit", function () {
    openLinkEdit(this.getAttribute("data-id"));
  });
  $("#tblVgrUnidadeLinks, #tblVgrUnidadeConn").on("click", ".vgr-link-desativar", function () {
    var linkId = this.getAttribute("data-id");
    if (!window.confirm("Desativar #" + linkId + "?")) return;
    V.jsonFetch("/vgr/api/links/" + encodeURIComponent(linkId) + "/desativar", {
      method: "POST",
      body: "{}",
    }).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Falha ao desativar.", false);
        return;
      }
      V.toast(res.d.message || "Desativado.", true);
      reloadLinkTables();
    });
  });
  $("#tblVgrUnidadeLinks, #tblVgrUnidadeConn").on("click", ".vgr-link-reativar", function () {
    var linkId = this.getAttribute("data-id");
    V.jsonFetch("/vgr/api/links/" + encodeURIComponent(linkId) + "/reativar", {
      method: "POST",
      body: "{}",
    }).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Falha ao reativar.", false);
        return;
      }
      V.toast(res.d.message || "Reativado.", true);
      reloadLinkTables();
    });
  });

  var btnOff = document.getElementById("btnVgrUniDetalheDesativar");
  if (btnOff) {
    btnOff.addEventListener("click", function () {
      var uid = this.getAttribute("data-id");
      if (!window.confirm("Desativar unidade #" + uid + "?")) return;
      V.jsonFetch("/vgr/api/unidades/" + encodeURIComponent(uid) + "/desativar", {
        method: "POST",
        body: "{}",
      }).then(function (res) {
        if (res.status >= 400 || !res.d.success) {
          V.toast((res.d && res.d.message) || "Falha ao desativar.", false);
          return;
        }
        window.location.reload();
      });
    });
  }
  var btnOn = document.getElementById("btnVgrUniDetalheReativar");
  if (btnOn) {
    btnOn.addEventListener("click", function () {
      var uid = this.getAttribute("data-id");
      V.jsonFetch("/vgr/api/unidades/" + encodeURIComponent(uid) + "/reativar", {
        method: "POST",
        body: "{}",
      }).then(function (res) {
        if (res.status >= 400 || !res.d.success) {
          V.toast((res.d && res.d.message) || "Falha ao reativar.", false);
          return;
        }
        window.location.reload();
      });
    });
  }
  V.bindLinkFormLogic("vgrLink");
})();
