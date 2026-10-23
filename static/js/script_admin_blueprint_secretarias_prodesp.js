/**
 * Admin PRODESP — catálogo Secretarias Blueprint (PortalDt + AdminInv).
 */
(function () {
  "use strict";

  const AI = window.AdminInv;
  if (!AI) {
    console.error("AdminInv comum não carregado");
    return;
  }

  const CAMPOS_LABEL = {
    acronimo: "Acrônimo",
    nome_exibicao: "Nome",
    ativo: "Ativo",
    device_blueprint_template: "Device template",
    layout_csv: "Layout CSV",
    rede_lan_regra: "Rede LAN",
    aplica_sufixo_lan_dinamico: "Sufixo LAN",
    dhcp_lan_start_octeto: "DHCP início",
    dhcp_lan_end_octeto: "DHCP fim",
    emite_dhcp_server_1: "DHCP Server 1",
    legado_omitir_dhcp_server: "Omitir DHCP legado",
    mostrar_em_hint_ui: "Hint UI",
    observacao: "Observação",
    aliases: "Aliases",
  };

  function labelCampo(campo) {
    const k = String(campo || "").trim();
    return CAMPOS_LABEL[k] || k || "—";
  }

  function acoesHtml(id) {
    return (
      '<span class="portal-dt-acoes-inner">' +
      '<button type="button" class="btn-icon text-info admin-bp-sec-view" data-id="' +
      id +
      '" title="Visualizar"><i class="fa-solid fa-eye"></i></button>' +
      '<button type="button" class="btn-icon text-secondary admin-bp-sec-hist" data-id="' +
      id +
      '" title="Histórico"><i class="fa-solid fa-clock-rotate-left"></i></button>' +
      '<button type="button" class="btn-icon text-primary admin-bp-sec-edit" data-id="' +
      id +
      '" title="Editar"><i class="fa-solid fa-pen"></i></button>' +
      '<button type="button" class="btn-icon text-danger admin-bp-sec-del" data-id="' +
      id +
      '" title="Inativar"><i class="fa-solid fa-ban"></i></button>' +
      "</span>"
    );
  }

  let api = null;
  let modalEl = null;
  let modal = null;
  let modalMode = "create";
  let histModalEl = null;
  let histModal = null;

  function setFooterMode(mode) {
    modalMode = mode;
    const btnSave = document.getElementById("btnAdminBpSecSalvar");
    const btnCancel = document.getElementById("btnAdminBpSecCancel");
    const isView = mode === "view";
    if (btnSave) btnSave.classList.toggle("d-none", isView);
    if (btnCancel) btnCancel.textContent = isView ? "Fechar" : "Cancelar";
    AI.applyModalMode(document.getElementById("modalAdminBpSec"), mode);
  }

  function collectPayload() {
    return {
      acronimo: (document.getElementById("adminBpSecAcronimo").value || "").trim(),
      nome_exibicao: (document.getElementById("adminBpSecNome").value || "").trim(),
      ativo: document.getElementById("adminBpSecAtivo").value === "1",
      aliases: document.getElementById("adminBpSecAliases").value || "",
      device_blueprint_template: (document.getElementById("adminBpSecTemplate").value || "").trim(),
      layout_csv: document.getElementById("adminBpSecLayout").value,
      rede_lan_regra: document.getElementById("adminBpSecRede").value,
      aplica_sufixo_lan_dinamico: document.getElementById("adminBpSecSufixo").value === "1",
      dhcp_lan_start_octeto: (document.getElementById("adminBpSecDhcpStart").value || "").trim(),
      dhcp_lan_end_octeto: (document.getElementById("adminBpSecDhcpEnd").value || "").trim(),
      emite_dhcp_server_1: document.getElementById("adminBpSecDhcpSrv1").value === "1",
      legado_omitir_dhcp_server: document.getElementById("adminBpSecOmitLegado").value === "1",
      mostrar_em_hint_ui: document.getElementById("adminBpSecHint").value === "1",
      observacao: (document.getElementById("adminBpSecObs").value || "").trim(),
    };
  }

  function fillForm(d) {
    d = d || {};
    document.getElementById("adminBpSecId").value = d.id || "";
    document.getElementById("adminBpSecAcronimo").value = d.acronimo || "";
    document.getElementById("adminBpSecNome").value = d.nome_exibicao || "";
    document.getElementById("adminBpSecAtivo").value =
      d.ativo === false || d.ativo === 0 ? "0" : "1";
    document.getElementById("adminBpSecAliases").value = (d.aliases || []).join(", ");
    document.getElementById("adminBpSecTemplate").value = d.device_blueprint_template || "";
    document.getElementById("adminBpSecLayout").value = d.layout_csv || "rede_lan";
    document.getElementById("adminBpSecRede").value = d.rede_lan_regra || "nova";
    document.getElementById("adminBpSecSufixo").value =
      d.aplica_sufixo_lan_dinamico === false || d.aplica_sufixo_lan_dinamico === 0 ? "0" : "1";
    document.getElementById("adminBpSecDhcpStart").value = d.dhcp_lan_start_octeto || "";
    document.getElementById("adminBpSecDhcpEnd").value = d.dhcp_lan_end_octeto || "";
    document.getElementById("adminBpSecDhcpSrv1").value = d.emite_dhcp_server_1 ? "1" : "0";
    document.getElementById("adminBpSecOmitLegado").value = d.legado_omitir_dhcp_server
      ? "1"
      : "0";
    document.getElementById("adminBpSecHint").value =
      d.mostrar_em_hint_ui === false || d.mostrar_em_hint_ui === 0 ? "0" : "1";
    document.getElementById("adminBpSecObs").value = d.observacao || "";
    refreshDhcpPreview();
  }

  function clearForm() {
    fillForm({});
  }

  function openCreate() {
    clearForm();
    document.getElementById("modalAdminBpSecTitle").textContent = "Nova secretaria";
    setFooterMode("create");
    modal.show();
  }

  function openById(id, mode) {
    AI.jsonFetch("/prodesp/api/admin/blueprint_secretarias/" + id, {
      credentials: "same-origin",
    }).then(function (res) {
      const d = res.d || {};
      if (res.status >= 400 || !d.success) {
        AI.toast((d && d.message) || "Falha ao carregar", false);
        return;
      }
      fillForm(d.data);
      document.getElementById("modalAdminBpSecTitle").textContent =
        mode === "view" ? "Visualizar secretaria" : "Editar secretaria";
      setFooterMode(mode);
      modal.show();
    });
  }

  function formatHistDate(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return String(iso);
      return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" });
    } catch (e) {
      return String(iso);
    }
  }

  function formatCell(val) {
    const s = val == null || val === "" ? "—" : String(val);
    return AI.esc(s);
  }

  function openHistorico(id) {
    if (!histModal) return;
    const title = document.getElementById("modalAdminBpSecHistoricoTitle");
    const meta = document.getElementById("adminBpSecHistMeta");
    const loading = document.getElementById("adminBpSecHistLoading");
    const empty = document.getElementById("adminBpSecHistEmpty");
    const tbody = document.getElementById("adminBpSecHistBody");
    if (title) title.textContent = "Histórico · id " + id;
    if (meta) meta.textContent = "Carregando auditoria…";
    if (tbody) tbody.innerHTML = "";
    if (empty) empty.classList.add("d-none");
    if (loading) loading.classList.remove("d-none");
    histModal.show();

    AI.jsonFetch("/prodesp/api/admin/blueprint_secretarias/" + id + "/historico", {
      credentials: "same-origin",
    }).then(function (res) {
      if (loading) loading.classList.add("d-none");
      const d = res.d || {};
      if (res.status >= 400 || !d.success) {
        AI.toast((d && d.message) || "Falha ao carregar histórico", false);
        if (meta) meta.textContent = "Não foi possível carregar o histórico.";
        return;
      }
      const acr = d.acronimo || (d.found === false ? "(cadastro removido)" : "");
      if (title) {
        title.textContent = acr
          ? "Histórico · " + acr + " (id " + id + ")"
          : "Histórico · id " + id;
      }
      if (meta) {
        meta.textContent =
          "Somente leitura · tabela historico · " +
          (d.data || []).length +
          " registro(s). RE e valores por campo.";
      }
      const rows = d.data || [];
      if (!rows.length) {
        if (empty) empty.classList.remove("d-none");
        return;
      }
      if (!tbody) return;
      const frag = document.createDocumentFragment();
      rows.forEach(function (h) {
        const tr = document.createElement("tr");
        const user =
          [h.usuario_re_historico, h.usuario_nome_historico].filter(Boolean).join(" — ") ||
          "—";
        tr.innerHTML =
          "<td class=\"text-nowrap small\">" +
          formatCell(formatHistDate(h.data_alteracao_historico)) +
          "</td>" +
          "<td class=\"small\">" +
          formatCell(user) +
          "</td>" +
          "<td class=\"small\">" +
          formatCell(labelCampo(h.campo_alterado_historico)) +
          "</td>" +
          '<td class="small font-monospace text-break">' +
          formatCell(h.valor_antigo_historico) +
          "</td>" +
          '<td class="small font-monospace text-break">' +
          formatCell(h.valor_novo_historico) +
          "</td>" +
          '<td class="small text-nowrap">' +
          formatCell(h.operacao_historico) +
          "</td>";
        frag.appendChild(tr);
      });
      tbody.appendChild(frag);
    });
  }

  function save() {
    const id = (document.getElementById("adminBpSecId").value || "").trim();
    const payload = collectPayload();
    const url = id
      ? "/prodesp/api/admin/blueprint_secretarias/" + id
      : "/prodesp/api/admin/blueprint_secretarias";
    const method = id ? "PUT" : "POST";
    AI.jsonFetch(url, { method: method, body: JSON.stringify(payload), credentials: "same-origin" }).then(function (res) {
      const d = res.d || {};
      if (res.status >= 400 || !d.success) {
        AI.toast((d && d.message) || "Falha ao salvar", false);
        return;
      }
      AI.toast(d.message || "Salvo.", true);
      modal.hide();
      if (api) api.ajax.reload(null, false);
    });
  }

  function deactivate(id) {
    if (
      !window.confirm(
        "Inativar esta secretaria? Unidades com o acrônimo passam a usar BP_OES (default)."
      )
    ) {
      return;
    }
    AI.jsonFetch("/prodesp/api/admin/blueprint_secretarias/" + id, {
      method: "DELETE",
      body: JSON.stringify({ hard: false }),
      credentials: "same-origin",
    }).then(function (res) {
      const d = res.d || {};
      if (res.status >= 400 || !d.success) {
        AI.toast((d && d.message) || "Falha ao inativar", false);
        return;
      }
      AI.toast(d.message || "Inativada.", true);
      if (api) api.ajax.reload(null, false);
    });
  }

  function dhcpRangeLabel(row) {
    if (row.dhcp_lan_start_octeto && row.dhcp_lan_end_octeto) {
      return "." + row.dhcp_lan_start_octeto + "–." + row.dhcp_lan_end_octeto;
    }
    return "—";
  }

  function refreshDhcpPreview() {
    const el = document.getElementById("adminBpSecDhcpPreview");
    if (!el) return;
    const a = (document.getElementById("adminBpSecDhcpStart").value || "").trim();
    const b = (document.getElementById("adminBpSecDhcpEnd").value || "").trim();
    if (!a && !b) {
      el.innerHTML =
        "Preview CSV: <strong>sem faixa DHCP LAN</strong> (colunas vazias) — padrão da maioria; " +
        "só <span class=\"font-monospace\">SEDS</span> costuma usar 10 → 60.";
      return;
    }
    if (!a || !b) {
      el.textContent = "Preview CSV: informe início e fim juntos (ex. SEDS: 10 e 60).";
      return;
    }
    el.innerHTML =
      "Preview CSV (ex. IP LAN da unidade <code>10.138.42.129</code>): " +
      "<code>MV_DHCP_START_LAN=10.138.42." +
      AI.esc(a) +
      "</code> · <code>MV_DHCP_END_LAN=10.138.42." +
      AI.esc(b) +
      "</code>" +
      (a === "10" && b === "60"
        ? ' — <span class="text-success">mesma faixa do seed SEDS</span>.'
        : ".");
  }

  function wireDhcpPreview() {
    ["adminBpSecDhcpStart", "adminBpSecDhcpEnd"].forEach(function (id) {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener("input", refreshDhcpPreview);
      el.addEventListener("change", refreshDhcpPreview);
    });
  }

  function init() {
    modalEl = document.getElementById("modalAdminBpSec");
    if (!modalEl || typeof bootstrap === "undefined") return;
    modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    histModalEl = document.getElementById("modalAdminBpSecHistorico");
    if (histModalEl) {
      histModal = bootstrap.Modal.getOrCreateInstance(histModalEl);
    }
    wireDhcpPreview();

    const btnNovo = document.getElementById("btnAdminBpSecNovo");
    if (btnNovo) btnNovo.addEventListener("click", openCreate);
    const btnSave = document.getElementById("btnAdminBpSecSalvar");
    if (btnSave) btnSave.addEventListener("click", save);

    const table = document.getElementById("tblAdminBpSec");
    if (!table || typeof $ === "undefined" || !$.fn.DataTable) return;

    /* Largura de ações tratada via CSS (.admin-bp-sec-dt). */

    api = $("#tblAdminBpSec").DataTable({
      serverSide: false,
      processing: false,
      deferRender: true,
      pageLength: 25,
      autoWidth: false,
      order: [[1, "asc"]],
      ordering: { indicators: false, handler: false },
      ajax: {
        url: "/prodesp/api/admin/blueprint_secretarias",
        dataSrc: function (json) {
          if (!json || json.success === false) {
            AI.toast((json && json.message) || "Falha ao listar catálogo", false);
            return [];
          }
          const bar = document.getElementById("adminInvLoadingBar");
          if (bar) bar.classList.remove("is-on");
          return json.data || [];
        },
      },
      columns: [
        { data: "id", title: "ID", width: "52px", className: "text-start" },
        { data: "acronimo", title: "Acrônimo", width: "110px", className: "text-start" },
        {
          data: "aliases",
          title: "Aliases",
          width: "120px",
          className: "text-start",
          render: function (a, t) {
            const s = (a || []).join(", ");
            if (t !== "display") return s;
            return s ? AI.esc(s) : "—";
          },
        },
        { data: "layout_csv", title: "Layout", width: "80px", className: "text-start" },
        { data: "rede_lan_regra", title: "Rede LAN", width: "72px", className: "text-start" },
        {
          data: "device_blueprint_template",
          title: "Device template",
          className: "text-start",
          render: function (tpl, t) {
            const s = String(tpl || "");
            if (t !== "display") return s;
            if (!s) return "—";
            const short = s.length > 48 ? s.slice(0, 46) + "…" : s;
            return (
              '<span class="font-monospace small text-break" title="' +
              AI.esc(s) +
              '">' +
              AI.esc(short) +
              "</span>"
            );
          },
        },
        {
          data: "aplica_sufixo_lan_dinamico",
          title: "Sufixo LAN",
          width: "80px",
          className: "text-start",
          render: function (v, t) {
            const s = v ? "sim" : "não";
            return t === "display" ? s : s;
          },
        },
        {
          data: null,
          title: "DHCP LAN",
          width: "110px",
          className: "text-start",
          render: function (_d, t, row) {
            const s = dhcpRangeLabel(row);
            if (t !== "display") return s;
            if (s === "—") return "—";
            const isSeds = String(row.acronimo || "").toUpperCase() === "SEDS";
            const tip = isSeds
              ? "Seed SEDS: faixa .10–.60 a partir do IP LAN"
              : "Últimos octetos da faixa MV_DHCP_* (prefixo = IP LAN da unidade)";
            return (
              '<span title="' +
              AI.esc(tip) +
              '">' +
              AI.esc(s) +
              (isSeds ? ' <span class="text-muted small">(SEDS seed)</span>' : "") +
              "</span>"
            );
          },
        },
        {
          data: "emite_dhcp_server_1",
          title: "DHCP Srv1",
          width: "80px",
          className: "text-start",
          render: function (v) {
            return v ? "sim" : "—";
          },
        },
        {
          data: "ativo",
          title: "Ativo",
          width: "80px",
          className: "text-start",
          render: function (v, t) {
            if (t !== "display") return v ? "ativo" : "inativo";
            return v
              ? '<span class="badge bg-success">ativo</span>'
              : '<span class="badge bg-secondary">inativo</span>';
          },
        },
        {
          data: "id",
          title: "Ações",
          orderable: false,
          searchable: false,
          className: "col-acoes portal-dt-acoes text-center",
          width: "152px",
          render: function (id) {
            return acoesHtml(id);
          },
        },
      ],
      columnDefs: [
        {
          targets: [0, 5],
          columnControl: [],
        },
        {
          targets: [1, 2, 3, 4, 6, 7, 8, 9],
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
        AI.bindPortalDtColumnControl(this.api(), "blueprint_secretarias");
      },
    });

    if (window.PortalDtToolbar) {
      PortalDtToolbar.mount(null, {
        tableId: "tblAdminBpSec",
        api: api,
        onRefresh: function () {
          if (api) api.ajax.reload(null, false);
        },
      });
    }

    $("#tblAdminBpSec tbody")
      .on("click", ".admin-bp-sec-view", function () {
        openById($(this).data("id"), "view");
      })
      .on("click", ".admin-bp-sec-hist", function () {
        openHistorico($(this).data("id"));
      })
      .on("click", ".admin-bp-sec-edit", function () {
        openById($(this).data("id"), "edit");
      })
      .on("click", ".admin-bp-sec-del", function () {
        deactivate($(this).data("id"));
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
