(function () {
  "use strict";
  const V = window.VgrDt;
  if (!V || typeof $ === "undefined" || !$.fn.DataTable) return;

  const modalEl = document.getElementById("modalVgrField");
  const modal = modalEl && window.bootstrap ? new bootstrap.Modal(modalEl) : null;
  const errEl = document.getElementById("vgrFieldErro");
  const cc = window.PortalDt ? window.PortalDt.ccSearchList() : [];
  /* CPF (DV), e-mails e telefone — mesmas regras do backend (core). */
  const R = window.VgrFieldRules || null;
  const liveField = R
    ? R.bindFieldLive({ cpf: "vgrFieldCpf", emails: "vgrFieldEmails", telefone: "vgrFieldTel" })
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

  function clearForm() {
    document.getElementById("vgrFieldId").value = "";
    document.getElementById("vgrFieldNome").value = "";
    document.getElementById("vgrFieldTel").value = "";
    document.getElementById("vgrFieldRg").value = "";
    document.getElementById("vgrFieldCpf").value = "";
    document.getElementById("vgrFieldEmails").value = "";
    document.getElementById("vgrNovaContratada").value = "";
    var sel = document.getElementById("vgrFieldContratadas");
    if (sel) {
      Array.prototype.forEach.call(sel.options, function (o) {
        o.selected = false;
      });
    }
    showErr("");
    if (R) R.clearStates(modalEl);
  }

  function selectedContratadas() {
    var sel = document.getElementById("vgrFieldContratadas");
    if (!sel) return [];
    return Array.prototype.filter
      .call(sel.options, function (o) {
        return o.selected;
      })
      .map(function (o) {
        return parseInt(o.value, 10);
      })
      .filter(function (n) {
        return n > 0;
      });
  }

  function fillContratadas(options, selectedIds) {
    var sel = document.getElementById("vgrFieldContratadas");
    if (!sel) return;
    var selected = {};
    (selectedIds || []).forEach(function (id) {
      selected[String(id)] = true;
    });
    sel.innerHTML = "";
    (options || []).forEach(function (c) {
      var opt = document.createElement("option");
      opt.value = String(c.id_contratada);
      opt.textContent = c.nome_contratada + (c.cnpj ? " (" + c.cnpj + ")" : "");
      opt.selected = !!selected[String(c.id_contratada)];
      sel.appendChild(opt);
    });
  }

  function loadContratadas(selectedIds) {
    return V.jsonFetch("/vgr/api/contratadas").then(function (res) {
      var rows = (res.d && res.d.data) || [];
      fillContratadas(rows, selectedIds);
      return rows;
    });
  }

  function fillForm(d) {
    document.getElementById("vgrFieldId").value = d.id_field || "";
    document.getElementById("vgrFieldNome").value = d.nome || "";
    document.getElementById("vgrFieldTel").value = d.telefone || "";
    document.getElementById("vgrFieldRg").value = d.rg || "";
    document.getElementById("vgrFieldCpf").value = d.cpf || "";
    document.getElementById("vgrFieldEmails").value = (d.emails || []).join("\n");
    showErr("");
    if (R) R.clearStates(modalEl);
    if (liveField) liveField.refresh();
  }

  function readForm() {
    var emailsRaw = document.getElementById("vgrFieldEmails").value || "";
    var emails = emailsRaw
      .split(/[\n,;]+/)
      .map(function (s) {
        return s.trim();
      })
      .filter(Boolean);
    return {
      nome: document.getElementById("vgrFieldNome").value,
      telefone: document.getElementById("vgrFieldTel").value,
      rg: document.getElementById("vgrFieldRg").value,
      cpf: document.getElementById("vgrFieldCpf").value,
      emails: emails,
      id_contratadas: selectedContratadas(),
    };
  }

  function openCreate() {
    clearForm();
    document.getElementById("modalVgrFieldTitle").textContent = "Novo Field";
    loadContratadas([]).then(function () {
      if (modal) modal.show();
    });
  }

  function openEdit(id) {
    clearForm();
    document.getElementById("modalVgrFieldTitle").textContent = "Editar Field #" + id;
    if (modal) modal.show();
    V.jsonFetch("/vgr/api/fields/" + encodeURIComponent(id)).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Field não encontrado.", false);
        if (modal) modal.hide();
        return;
      }
      var d = res.d.data || {};
      fillForm(d);
      loadContratadas(d.id_contratadas || []);
    });
  }

  const api = $("#tblVgrFields").DataTable(
    V.baseOpts({
      order: [[1, "asc"]],
      ajax: V.clientAjax("/vgr/api/fields"),
      columns: [
        { data: "id_field" },
        {
          data: "nome",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "telefone",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "emails_count",
          render: function (d, t) {
            return V.renderText(d != null ? d : 0, t, "0");
          },
        },
        {
          data: "contratadas_resumo",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "has_rg",
          render: function (d) {
            return Number(d) === 1 || d === true ? "Sim" : "Não";
          },
        },
        {
          data: "has_cpf",
          render: function (d) {
            return Number(d) === 1 || d === true ? "Sim" : "Não";
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
            return V.acoesField(row.id_field, row.ativo);
          },
        },
      ],
      columnDefs: [
        { targets: [1, 2, 3, 4, 5, 6, 7], columnControl: cc },
        { targets: [-1], columnControl: [] },
      ],
    })
  );

  function reload() {
    api.ajax.reload(null, false);
  }

  V.mountToolbar("tblVgrFields", api);

  var btnNovo = document.getElementById("btnVgrFieldNovo");
  if (btnNovo) btnNovo.addEventListener("click", openCreate);

  var btnSalvar = document.getElementById("btnVgrFieldSalvar");
  if (btnSalvar) {
    btnSalvar.addEventListener("click", function () {
      showErr("");
      var id = document.getElementById("vgrFieldId").value;
      var body = readForm();
      var clientErr = R ? R.validateFieldPayload(body) : null;
      if (clientErr) {
        showErr(clientErr);
        if (liveField) liveField.refresh();
        return;
      }
      var url = id ? "/vgr/api/fields/" + encodeURIComponent(id) : "/vgr/api/fields";
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

  var btnAddC = document.getElementById("btnVgrContratadaAdd");
  if (btnAddC) {
    btnAddC.addEventListener("click", function () {
      var nome = (document.getElementById("vgrNovaContratada").value || "").trim();
      if (!nome) {
        V.toast("Informe o nome da contratada.", false);
        return;
      }
      var selected = selectedContratadas();
      btnAddC.disabled = true;
      V.jsonFetch("/vgr/api/contratadas", {
        method: "POST",
        body: JSON.stringify({ nome_contratada: nome }),
      })
        .then(function (res) {
          if (res.status >= 400 || !res.d.success) {
            V.toast((res.d && res.d.message) || "Falha ao criar contratada.", false);
            return;
          }
          var created = (res.d && res.d.data) || {};
          if (created.id_contratada) selected.push(created.id_contratada);
          document.getElementById("vgrNovaContratada").value = "";
          return loadContratadas(selected);
        })
        .finally(function () {
          btnAddC.disabled = false;
        });
    });
  }

  $("#tblVgrFields").on("click", ".vgr-field-edit", function () {
    openEdit(this.getAttribute("data-id"));
  });
  $("#tblVgrFields").on("click", ".vgr-field-desativar", function () {
    var id = this.getAttribute("data-id");
    if (!window.confirm("Desativar Field #" + id + "?")) return;
    V.jsonFetch("/vgr/api/fields/" + encodeURIComponent(id) + "/desativar", {
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
  $("#tblVgrFields").on("click", ".vgr-field-reativar", function () {
    var id = this.getAttribute("data-id");
    V.jsonFetch("/vgr/api/fields/" + encodeURIComponent(id) + "/reativar", {
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
})();
