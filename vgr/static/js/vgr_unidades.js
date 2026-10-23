(function () {
  "use strict";
  const V = window.VgrDt;
  if (!V || typeof $ === "undefined" || !$.fn.DataTable) return;

  const modalEl = document.getElementById("modalVgrUnidade");
  const modal = modalEl && window.bootstrap ? new bootstrap.Modal(modalEl) : null;
  const errEl = document.getElementById("vgrUniErro");
  const selCliente = document.getElementById("vgrUniCliente");
  let clienteCache = {};
  /* CNPJ (DV), CEP, UF e lat/long — mesmas regras do backend (core). */
  const R = window.VgrFieldRules || null;
  const liveEnd = R
    ? R.bindEndereco({
        cnpj: "vgrUniCnpj",
        cep: "vgrUniCep",
        uf: "vgrUniUf",
        latitude: "vgrUniLatitude",
        longitude: "vgrUniLongitude",
      })
    : null;

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

  function updateMatrizHint() {
    var hint = document.getElementById("vgrUniMatrizHint");
    if (!hint) return;
    hint.style.display =
      document.getElementById("vgrUniTipo").value === "MATRIZ" ? "block" : "none";
  }

  function clearForm() {
    document.getElementById("vgrUniId").value = "";
    document.getElementById("vgrUniNome").value = "";
    document.getElementById("vgrUniContato").value = "";
    document.getElementById("vgrUniCnpj").value = "";
    document.getElementById("vgrUniCodigo").value = "";
    document.getElementById("vgrUniTipo").value = "FILIAL";
    document.getElementById("vgrUniTipoProjeto").value = "PRATELEIRA";
    document.getElementById("vgrUniHa").value = "0";
    document.getElementById("vgrUniTopologia").value = "";
    document.getElementById("vgrUniEndereco").value = "";
    document.getElementById("vgrUniBairro").value = "";
    document.getElementById("vgrUniCidade").value = "";
    document.getElementById("vgrUniUf").value = "";
    document.getElementById("vgrUniCep").value = "";
    document.getElementById("vgrUniLatitude").value = "";
    document.getElementById("vgrUniLongitude").value = "";
    showErr("");
    updateMatrizHint();
    if (R) R.clearStates(modalEl);
  }

  function fillForm(d) {
    document.getElementById("vgrUniId").value = d.id_unidade || "";
    if (selCliente && d.id_cliente != null) selCliente.value = String(d.id_cliente);
    document.getElementById("vgrUniNome").value = d.nome_unidade || "";
    document.getElementById("vgrUniContato").value = d.contato_unidade || "";
    document.getElementById("vgrUniCnpj").value = d.cnpj_unidade || "";
    document.getElementById("vgrUniCodigo").value = d.codigo_unidade || "";
    document.getElementById("vgrUniTipo").value = d.tipo_unidade || "FILIAL";
    document.getElementById("vgrUniTipoProjeto").value = d.tipo_projeto || "PRATELEIRA";
    document.getElementById("vgrUniHa").value = Number(d.ha) === 1 ? "1" : "0";
    document.getElementById("vgrUniTopologia").value = d.topologia_unidades || "";
    document.getElementById("vgrUniEndereco").value = d.endereco || "";
    document.getElementById("vgrUniBairro").value = d.bairro || "";
    document.getElementById("vgrUniCidade").value = d.cidade || "";
    document.getElementById("vgrUniUf").value = d.uf || "";
    document.getElementById("vgrUniCep").value = d.cep || "";
    /* 0 é coordenada válida: não usar || "" (DECIMAL chega como número) */
    document.getElementById("vgrUniLongitude").value =
      d.longitude != null && d.longitude !== "" ? String(d.longitude) : "";
    document.getElementById("vgrUniLatitude").value =
      d.latitude != null && d.latitude !== "" ? String(d.latitude) : "";
    showErr("");
    updateMatrizHint();
    if (R) R.clearStates(modalEl);
    if (liveEnd) liveEnd.refresh();
  }

  function readForm() {
    return {
      id_cliente: selCliente ? selCliente.value : "",
      nome_unidade: document.getElementById("vgrUniNome").value,
      contato_unidade: document.getElementById("vgrUniContato").value,
      cnpj_unidade: document.getElementById("vgrUniCnpj").value,
      codigo_unidade: document.getElementById("vgrUniCodigo").value,
      tipo_unidade: document.getElementById("vgrUniTipo").value,
      tipo_projeto: document.getElementById("vgrUniTipoProjeto").value,
      ha: document.getElementById("vgrUniHa").value,
      topologia_unidades: document.getElementById("vgrUniTopologia").value,
      endereco: document.getElementById("vgrUniEndereco").value,
      bairro: document.getElementById("vgrUniBairro").value,
      cidade: document.getElementById("vgrUniCidade").value,
      uf: document.getElementById("vgrUniUf").value,
      cep: document.getElementById("vgrUniCep").value,
      latitude: document.getElementById("vgrUniLatitude").value,
      longitude: document.getElementById("vgrUniLongitude").value,
    };
  }

  function loadClientesOpcoes(preferredId) {
    return V.jsonFetch("/vgr/api/clientes/opcoes").then(function (res) {
      if (!selCliente) return;
      selCliente.innerHTML = "";
      var opt0 = document.createElement("option");
      opt0.value = "";
      opt0.textContent = "Selecione…";
      selCliente.appendChild(opt0);
      var rows = (res.d && res.d.data) || [];
      rows.forEach(function (r) {
        var o = document.createElement("option");
        o.value = String(r.id_cliente);
        o.textContent = r.razao_social || ("#" + r.id_cliente);
        selCliente.appendChild(o);
      });
      if (preferredId) selCliente.value = String(preferredId);
    });
  }

  function prefillMatrizFromCliente() {
    if (document.getElementById("vgrUniTipo").value !== "MATRIZ") return;
    var cid = selCliente && selCliente.value;
    if (!cid) return;
    var hasAddr = document.getElementById("vgrUniEndereco").value.trim();
    if (hasAddr) return;
    var cached = clienteCache[cid];
    function apply(cli) {
      if (!cli) return;
      if (!document.getElementById("vgrUniEndereco").value)
        document.getElementById("vgrUniEndereco").value = cli.endereco_principal || "";
      if (!document.getElementById("vgrUniCidade").value)
        document.getElementById("vgrUniCidade").value = cli.cidade || "";
      if (!document.getElementById("vgrUniUf").value)
        document.getElementById("vgrUniUf").value = cli.uf || "";
      if (!document.getElementById("vgrUniCep").value)
        document.getElementById("vgrUniCep").value = cli.cep || "";
      if (liveEnd) liveEnd.refresh();
    }
    if (cached) {
      apply(cached);
      return;
    }
    V.jsonFetch("/vgr/api/clientes/" + encodeURIComponent(cid)).then(function (res) {
      if (res.status >= 400 || !res.d.success) return;
      clienteCache[cid] = res.d.data || {};
      apply(clienteCache[cid]);
    });
  }

  function openCreate(presetClienteId) {
    clearForm();
    document.getElementById("modalVgrUnidadeTitle").textContent = "Nova unidade";
    loadClientesOpcoes(presetClienteId).then(function () {
      if (modal) modal.show();
    });
  }

  function openEdit(id) {
    clearForm();
    document.getElementById("modalVgrUnidadeTitle").textContent = "Editar unidade #" + id;
    loadClientesOpcoes(null).then(function () {
      if (modal) modal.show();
      return V.jsonFetch("/vgr/api/unidades/" + encodeURIComponent(id));
    }).then(function (res) {
      if (!res) return;
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Unidade não encontrada.", false);
        if (modal) modal.hide();
        return;
      }
      fillForm(res.d.data || {});
    });
  }

  const api = $("#tblVgrUnidades").DataTable(
    V.baseOpts({
      order: [[2, "asc"]],
      ajax: V.clientAjax("/vgr/api/unidades"),
      columns: [
        { data: "id_unidade", className: "text-start" },
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
          data: "tipo_unidade",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "cidade",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "uf",
          render: function (d, t) {
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
            return V.acoesUnidade(row.id_unidade, row.ativo);
          },
        },
      ],
      columnDefs: [
        {
          targets: [1, 2, 3, 4, 5, 6, 7],
          columnControl: window.PortalDt ? window.PortalDt.ccSearchList() : [],
        },
        { targets: [-1], columnControl: [] },
      ],
    })
  );

  function reload() {
    api.ajax.reload(null, false);
  }

  V.mountToolbar("tblVgrUnidades", api);

  var btnNovo = document.getElementById("btnVgrUnidadeNova");
  if (btnNovo) {
    btnNovo.addEventListener("click", function () {
      openCreate(window.VGR_UNIDADE_PRESET_CLIENTE || "");
    });
  }

  document.getElementById("vgrUniTipo").addEventListener("change", function () {
    updateMatrizHint();
    prefillMatrizFromCliente();
  });
  if (selCliente) {
    selCliente.addEventListener("change", prefillMatrizFromCliente);
  }

  var btnSalvar = document.getElementById("btnVgrUnidadeSalvar");
  if (btnSalvar) {
    btnSalvar.addEventListener("click", function () {
      showErr("");
      var id = document.getElementById("vgrUniId").value;
      var body = readForm();
      var clientErr = R ? R.validateUnidadePayload(body) : null;
      if (clientErr) {
        showErr(clientErr);
        if (liveEnd) liveEnd.refresh();
        return;
      }
      var url = id ? "/vgr/api/unidades/" + encodeURIComponent(id) : "/vgr/api/unidades";
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

  $("#tblVgrUnidades").on("click", ".vgr-uni-edit", function () {
    openEdit(this.getAttribute("data-id"));
  });
  $("#tblVgrUnidades").on("click", ".vgr-uni-desativar", function () {
    var id = this.getAttribute("data-id");
    if (!window.confirm("Desativar unidade #" + id + "?")) return;
    V.jsonFetch("/vgr/api/unidades/" + encodeURIComponent(id) + "/desativar", {
      method: "POST",
      body: "{}",
    }).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Falha ao desativar.", false);
        return;
      }
      V.toast(res.d.message || "Desativada.", true);
      reload();
    });
  });
  $("#tblVgrUnidades").on("click", ".vgr-uni-reativar", function () {
    var id = this.getAttribute("data-id");
    V.jsonFetch("/vgr/api/unidades/" + encodeURIComponent(id) + "/reativar", {
      method: "POST",
      body: "{}",
    }).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Falha ao reativar.", false);
        return;
      }
      V.toast(res.d.message || "Reativada.", true);
      reload();
    });
  });

  if (window.VGR_UNIDADE_AUTO_EDIT) {
    openEdit(window.VGR_UNIDADE_AUTO_EDIT);
  } else if (window.VGR_UNIDADE_AUTO_NOVO) {
    openCreate(window.VGR_UNIDADE_PRESET_CLIENTE || "");
  }

  if (window.PortalEnriquecerEndereco && window.PortalEnriquecerEndereco.bind) {
    window.PortalEnriquecerEndereco.bind({
      buttonId: "btnVgrCompletarEndereco",
      statusId: "vgrUniEnderecoStatus",
      endpoint: "/vgr/api/enriquecer-endereco",
      fields: {
        endereco: "vgrUniEndereco",
        bairro: "vgrUniBairro",
        cidade: "vgrUniCidade",
        municipio: "vgrUniCidade",
        uf: "vgrUniUf",
        estado: "vgrUniUf",
        cep: "vgrUniCep",
        latitude: "vgrUniLatitude",
        longitude: "vgrUniLongitude",
      },
    });
  }
})();