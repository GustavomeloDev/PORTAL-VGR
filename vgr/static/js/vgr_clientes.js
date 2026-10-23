(function () {
  "use strict";
  const V = window.VgrDt;
  if (!V || typeof $ === "undefined" || !$.fn.DataTable) return;

  const modalEl = document.getElementById("modalVgrCliente");
  const modal = modalEl && window.bootstrap ? new bootstrap.Modal(modalEl) : null;
  const errEl = document.getElementById("vgrCliErro");
  /* CNPJ (DV), CEP e UF — mesmas regras do backend (core). */
  const R = window.VgrFieldRules || null;
  const liveEnd = R ? R.bindEndereco({ cnpj: "vgrCliCnpj", cep: "vgrCliCep", uf: "vgrCliUf" }) : null;

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

  function clearForm() {
    document.getElementById("vgrCliId").value = "";
    document.getElementById("vgrCliRazao").value = "";
    document.getElementById("vgrCliCnpj").value = "";
    document.getElementById("vgrCliEndereco").value = "";
    document.getElementById("vgrCliCidade").value = "";
    document.getElementById("vgrCliUf").value = "";
    document.getElementById("vgrCliCep").value = "";
    document.getElementById("vgrCliLt").value = "";
    document.getElementById("vgrCliGpCs").value = "";
    showErr("");
    if (R) R.clearStates(modalEl);
  }

  function fillForm(d) {
    document.getElementById("vgrCliId").value = d.id_cliente || "";
    document.getElementById("vgrCliRazao").value = d.razao_social || "";
    document.getElementById("vgrCliCnpj").value = d.cnpj_cliente || "";
    document.getElementById("vgrCliEndereco").value = d.endereco_principal || "";
    document.getElementById("vgrCliCidade").value = d.cidade || "";
    document.getElementById("vgrCliUf").value = d.uf || "";
    document.getElementById("vgrCliCep").value = d.cep || "";
    document.getElementById("vgrCliLt").value = d.lider_tecnico || "";
    document.getElementById("vgrCliGpCs").value = d.nome_gp_cs_clientes || "";
    showErr("");
    if (R) R.clearStates(modalEl);
    if (liveEnd) liveEnd.refresh();
  }

  function readForm() {
    return {
      razao_social: document.getElementById("vgrCliRazao").value,
      cnpj_cliente: document.getElementById("vgrCliCnpj").value,
      endereco_principal: document.getElementById("vgrCliEndereco").value,
      cidade: document.getElementById("vgrCliCidade").value,
      uf: document.getElementById("vgrCliUf").value,
      cep: document.getElementById("vgrCliCep").value,
      lider_tecnico: document.getElementById("vgrCliLt").value,
      nome_gp_cs_clientes: document.getElementById("vgrCliGpCs").value,
    };
  }

  function openCreate() {
    clearForm();
    document.getElementById("modalVgrClienteTitle").textContent = "Novo cliente";
    if (modal) modal.show();
  }

  function openEdit(id) {
    clearForm();
    document.getElementById("modalVgrClienteTitle").textContent = "Editar cliente #" + id;
    if (modal) modal.show();
    V.jsonFetch("/vgr/api/clientes/" + encodeURIComponent(id)).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Cliente não encontrado.", false);
        if (modal) modal.hide();
        return;
      }
      fillForm(res.d.data || {});
    });
  }

  const api = $("#tblVgrClientes").DataTable(
    V.baseOpts({
      order: [[1, "asc"]],
      ajax: V.clientAjax("/vgr/api/clientes"),
      columns: [
        { data: "id_cliente", className: "text-start" },
        {
          data: "razao_social",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "cnpj_cliente",
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
          data: "lider_tecnico",
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
            return V.acoesCliente(row.id_cliente, row.ativo);
          },
        },
      ],
      columnDefs: [
        {
          targets: [1, 2, 3, 4, 5, 6],
          columnControl: window.PortalDt ? window.PortalDt.ccSearchList() : [],
        },
        { targets: [-1], columnControl: [] },
      ],
    })
  );

  function reload() {
    api.ajax.reload(null, false);
  }

  V.mountToolbar("tblVgrClientes", api);

  var btnNovo = document.getElementById("btnVgrClienteNovo");
  if (btnNovo) btnNovo.addEventListener("click", openCreate);

  var btnSalvar = document.getElementById("btnVgrClienteSalvar");
  if (btnSalvar) {
    btnSalvar.addEventListener("click", function () {
      showErr("");
      var id = document.getElementById("vgrCliId").value;
      var body = readForm();
      var clientErr = R ? R.validateClientePayload(body) : null;
      if (clientErr) {
        showErr(clientErr);
        if (liveEnd) liveEnd.refresh();
        return;
      }
      var url = id ? "/vgr/api/clientes/" + encodeURIComponent(id) : "/vgr/api/clientes";
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

  $("#tblVgrClientes").on("click", ".vgr-cli-edit", function () {
    openEdit(this.getAttribute("data-id"));
  });

  $("#tblVgrClientes").on("click", ".vgr-cli-desativar", function () {
    var id = this.getAttribute("data-id");
    if (!window.confirm("Desativar cliente #" + id + "? O histórico permanece; ativo=0.")) return;
    V.jsonFetch("/vgr/api/clientes/" + encodeURIComponent(id) + "/desativar", {
      method: "POST",
      body: "{}",
    }).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Falha ao desativar.", false);
        return;
      }
      V.toast(res.d.message || "Desativado.", true);
      reload();
    });
  });

  $("#tblVgrClientes").on("click", ".vgr-cli-reativar", function () {
    var id = this.getAttribute("data-id");
    V.jsonFetch("/vgr/api/clientes/" + encodeURIComponent(id) + "/reativar", {
      method: "POST",
      body: "{}",
    }).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Falha ao reativar.", false);
        return;
      }
      V.toast(res.d.message || "Reativado.", true);
      reload();
    });
  });

  if (window.VGR_CLIENTE_AUTO_EDIT) {
    openEdit(window.VGR_CLIENTE_AUTO_EDIT);
  }
})();
