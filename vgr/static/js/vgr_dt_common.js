/**
 * Helpers DataTables VGR — alinhado ao PortalDt (core) / admin PRODESP.
 * serverSide: false; ColumnControl via PortalDt.ccSearchList(); toolbar PortalDtToolbar.
 */
(function (global) {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /**
   * Texto para coluna + ColumnControl searchList.
   * Nunca retorna null (CC 1.0.6 faz val.toString() e quebra com nulls da API).
   */
  function renderText(d, t, emptyDisplay) {
    var empty = emptyDisplay != null ? emptyDisplay : "—";
    if (d == null || d === "") {
      return t === "display" ? empty : "";
    }
    if (t === "display") return esc(d);
    return String(d);
  }

  function yesNo(v) {
    return Number(v) === 1 || v === true ? "Sim" : "Não";
  }

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") || "" : "";
  }

  function jsonFetch(url, opts) {
    opts = opts || {};
    var headers = Object.assign(
      {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      opts.headers || {}
    );
    if (opts.body && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    var method = String(opts.method || "GET").toUpperCase();
    if (method !== "GET" && method !== "HEAD") {
      headers["X-CSRF-Token"] = csrfToken();
    }
    return fetch(url, Object.assign({}, opts, { headers: headers, credentials: "same-origin" })).then(
      function (res) {
        return res.json().catch(function () {
          return { success: false, message: "Resposta inválida do servidor." };
        }).then(function (d) {
          return { status: res.status, d: d || {} };
        });
      }
    );
  }

  /** kind opcional: "warn" → amarelo e mais tempo na tela (avisos não bloqueantes). */
  function toast(msg, ok, kind) {
    var el = document.getElementById("vgrToast");
    if (!el) {
      el = document.createElement("div");
      el.id = "vgrToast";
      el.className = "position-fixed bottom-0 end-0 p-3";
      el.style.zIndex = "1080";
      document.body.appendChild(el);
    }
    var isWarn = kind === "warn";
    var cls = isWarn ? "text-bg-warning" : ok ? "text-bg-success" : "text-bg-danger";
    var id = "vgrToastItem" + Date.now();
    el.insertAdjacentHTML(
      "beforeend",
      '<div id="' +
        id +
        '" class="toast align-items-center ' +
        cls +
        ' border-0 show mb-2" role="status">' +
        '<div class="d-flex"><div class="toast-body"></div>' +
        '<button type="button" class="btn-close' + (isWarn ? "" : " btn-close-white") + ' me-2 m-auto" data-bs-dismiss="toast" aria-label="Fechar"></button>' +
        "</div></div>"
    );
    var item = document.getElementById(id);
    if (item) {
      var body = item.querySelector(".toast-body");
      if (body) body.textContent = String(msg || (ok ? "OK" : "Falha"));
      setTimeout(function () {
        if (item && item.parentNode) item.parentNode.removeChild(item);
      }, isWarn ? 8000 : 3500);
    }
  }

  function mountToolbar(tableId, api, opts) {
    if (!global.PortalDtToolbar || !api) return;
    opts = opts || {};
    global.PortalDtToolbar.mount(null, {
      tableId: tableId,
      api: api,
      onRefresh: function () {
        if (api.ajax && typeof api.ajax.reload === "function") {
          api.ajax.reload(null, false);
        } else {
          api.draw(false);
        }
      },
      onClearExtra: opts.onClearExtra,
    });
  }

  function clientAjax(url, filterFn) {
    return {
      url: url,
      dataSrc: function (json) {
        if (!json || json.success === false) {
          console.warn("VGR DT:", (json && json.message) || "falha na API");
          return [];
        }
        var rows = json.data || [];
        if (typeof filterFn === "function") {
          return rows.filter(filterFn);
        }
        return rows;
      },
    };
  }

  function languageFallback() {
    return {
      emptyTable: "Nenhum registro encontrado",
      info: "Mostrando de _START_ até _END_ de _TOTAL_ registros",
      infoEmpty: "Mostrando 0 até 0 de 0 registro(s)",
      infoFiltered: "(Filtrados de _MAX_ registros)",
      lengthMenu: "Exibir _MENU_ resultados por página",
      loadingRecords: "Carregando...",
      processing: "Carregando...",
      search: "🔍",
      searchPlaceholder: "Buscar registros",
      zeroRecords: "Nenhum registro encontrado",
      paginate: { next: "›", previous: "‹", first: "«", last: "»" },
    };
  }

  function baseOpts(extra) {
    const PortalDt = global.PortalDt || {};
    const opts = {
      serverSide: false,
      processing: false,
      deferRender: true,
      pageLength: 25,
      autoWidth: false,
      ordering: PortalDt.orderingSilent
        ? PortalDt.orderingSilent()
        : { indicators: false, handler: false },
      language: PortalDt.languagePtBr
        ? PortalDt.languagePtBr()
        : languageFallback(),
    };
    return Object.assign(opts, extra || {});
  }

  function acoesAbrir(href) {
    return (
      '<span class="portal-dt-acoes-inner">' +
      '<a class="btn-icon text-primary" href="' +
      esc(href) +
      '" title="Abrir"><i class="fa-solid fa-eye"></i></a>' +
      "</span>"
    );
  }

  function acoesCliente(id, ativo) {
    var open =
      '<a class="btn-icon text-primary" href="/vgr/clientes/' +
      esc(id) +
      '" title="Abrir"><i class="fa-solid fa-eye"></i></a>';
    var edit =
      '<button type="button" class="btn-icon text-secondary vgr-cli-edit" data-id="' +
      esc(id) +
      '" title="Editar"><i class="fa-solid fa-pen"></i></button>';
    var toggle =
      Number(ativo) === 1
        ? '<button type="button" class="btn-icon text-danger vgr-cli-desativar" data-id="' +
          esc(id) +
          '" title="Desativar"><i class="fa-solid fa-ban"></i></button>'
        : '<button type="button" class="btn-icon text-success vgr-cli-reativar" data-id="' +
          esc(id) +
          '" title="Reativar"><i class="fa-solid fa-rotate-left"></i></button>';
    return (
      '<span class="portal-dt-acoes-inner">' + open + edit + toggle + "</span>"
    );
  }

  function acoesUnidade(id, ativo) {
    var open =
      '<a class="btn-icon text-primary" href="/vgr/unidades/' +
      esc(id) +
      '" title="Abrir"><i class="fa-solid fa-eye"></i></a>';
    var edit =
      '<button type="button" class="btn-icon text-secondary vgr-uni-edit" data-id="' +
      esc(id) +
      '" title="Editar"><i class="fa-solid fa-pen"></i></button>';
    var toggle =
      Number(ativo) === 1
        ? '<button type="button" class="btn-icon text-danger vgr-uni-desativar" data-id="' +
          esc(id) +
          '" title="Desativar"><i class="fa-solid fa-ban"></i></button>'
        : '<button type="button" class="btn-icon text-success vgr-uni-reativar" data-id="' +
          esc(id) +
          '" title="Reativar"><i class="fa-solid fa-rotate-left"></i></button>';
    return (
      '<span class="portal-dt-acoes-inner">' + open + edit + toggle + "</span>"
    );
  }

  function acoesEquipamento(id, ativo) {
    var edit =
      '<button type="button" class="btn-icon text-secondary vgr-eq-edit" data-id="' +
      esc(id) +
      '" title="Editar"><i class="fa-solid fa-pen"></i></button>';
    var toggle =
      Number(ativo) === 1
        ? '<button type="button" class="btn-icon text-danger vgr-eq-desativar" data-id="' +
          esc(id) +
          '" title="Desativar"><i class="fa-solid fa-ban"></i></button>'
        : '<button type="button" class="btn-icon text-success vgr-eq-reativar" data-id="' +
          esc(id) +
          '" title="Reativar"><i class="fa-solid fa-rotate-left"></i></button>';
    return '<span class="portal-dt-acoes-inner">' + edit + toggle + "</span>";
  }

  function acoesLink(id, ativo) {
    var edit =
      '<button type="button" class="btn-icon text-secondary vgr-link-edit" data-id="' +
      esc(id) +
      '" title="Editar"><i class="fa-solid fa-pen"></i></button>';
    var toggle =
      Number(ativo) === 1
        ? '<button type="button" class="btn-icon text-danger vgr-link-desativar" data-id="' +
          esc(id) +
          '" title="Desativar"><i class="fa-solid fa-ban"></i></button>'
        : '<button type="button" class="btn-icon text-success vgr-link-reativar" data-id="' +
          esc(id) +
          '" title="Reativar"><i class="fa-solid fa-rotate-left"></i></button>';
    return '<span class="portal-dt-acoes-inner">' + edit + toggle + "</span>";
  }

  function acoesField(id, ativo) {
    var edit =
      '<button type="button" class="btn-icon text-secondary vgr-field-edit" data-id="' +
      esc(id) +
      '" title="Editar"><i class="fa-solid fa-pen"></i></button>';
    var toggle =
      Number(ativo) === 1
        ? '<button type="button" class="btn-icon text-danger vgr-field-desativar" data-id="' +
          esc(id) +
          '" title="Desativar"><i class="fa-solid fa-ban"></i></button>'
        : '<button type="button" class="btn-icon text-success vgr-field-reativar" data-id="' +
          esc(id) +
          '" title="Reativar"><i class="fa-solid fa-rotate-left"></i></button>';
    return '<span class="portal-dt-acoes-inner">' + edit + toggle + "</span>";
  }

  function acoesAtendimento(id, ativo) {
    var view =
      '<button type="button" class="btn-icon text-primary vgr-atend-view" data-id="' +
      esc(id) +
      '" title="Visualizar"><i class="fa-solid fa-eye"></i></button>';
    var edit =
      '<button type="button" class="btn-icon text-secondary vgr-atend-edit" data-id="' +
      esc(id) +
      '" title="Editar"><i class="fa-solid fa-pen"></i></button>';
    var toggle =
      Number(ativo) === 1
        ? '<button type="button" class="btn-icon text-danger vgr-atend-desativar" data-id="' +
          esc(id) +
          '" title="Desativar"><i class="fa-solid fa-ban"></i></button>'
        : '<button type="button" class="btn-icon text-success vgr-atend-reativar" data-id="' +
          esc(id) +
          '" title="Reativar"><i class="fa-solid fa-rotate-left"></i></button>';
    return (
      '<span class="portal-dt-acoes-inner">' + view + edit + toggle + "</span>"
    );
  }

  function acoesAgendamento(id, ativo, status) {
    var edit =
      '<button type="button" class="btn-icon text-secondary vgr-ag-edit" data-id="' +
      esc(id) +
      '" title="Editar"><i class="fa-solid fa-pen"></i></button>';
    var confirmar =
      status !== "Agendado"
        ? '<button type="button" class="btn-icon text-warning vgr-ag-confirmar" data-id="' +
          esc(id) +
          '" title="Confirmar Agendado"><i class="fa-solid fa-calendar-check"></i></button>'
        : "";
    var improd =
      '<button type="button" class="btn-icon text-danger vgr-ag-improdutivo" data-id="' +
      esc(id) +
      '" title="Improdutiva"><i class="fa-solid fa-triangle-exclamation"></i></button>';
    var toggle =
      Number(ativo) === 1
        ? '<button type="button" class="btn-icon text-danger vgr-ag-desativar" data-id="' +
          esc(id) +
          '" title="Desativar"><i class="fa-solid fa-ban"></i></button>'
        : '<button type="button" class="btn-icon text-success vgr-ag-reativar" data-id="' +
          esc(id) +
          '" title="Reativar"><i class="fa-solid fa-rotate-left"></i></button>';
    return (
      '<span class="portal-dt-acoes-inner">' +
      edit +
      confirmar +
      improd +
      toggle +
      "</span>"
    );
  }

  function formatBrDate(val) {
    if (val == null || val === "") return "";
    var s = String(val).trim();
    var m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) return m[3] + "/" + m[2] + "/" + m[1];
    var d = new Date(s);
    if (!isNaN(d.getTime()) && s.indexOf("T") >= 0) {
      var dd = String(d.getDate()).padStart(2, "0");
      var mm = String(d.getMonth() + 1).padStart(2, "0");
      var yyyy = d.getFullYear();
      return dd + "/" + mm + "/" + yyyy;
    }
    return s;
  }

  function formatBrTime(val) {
    if (val == null || val === "") return "";
    var s = String(val).trim();
    var m = s.match(/^(\d{1,2}):(\d{2})(?::\d{2})?/);
    if (m) return m[1].padStart(2, "0") + ":" + m[2];
    return s;
  }

  function formatBrDateTime(dateVal, timeVal) {
    var d = formatBrDate(dateVal);
    var t = formatBrTime(timeVal);
    if (d && t) return d + " " + t;
    if (d) return d;
    // datetime único ISO
    var s = String(dateVal == null ? "" : dateVal).trim();
    var m = s.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
    if (m) return m[3] + "/" + m[2] + "/" + m[1] + " " + m[4] + ":" + m[5];
    return formatBrDate(s) || s;
  }

  var VENDORS = [
    "Fortinet",
    "Meraki",
    "TP-Link",
    "Omada",
    "Viptela",
    "Cisco",
    "Outro",
  ];
  /* Padrão core (operadora.py): principais + sentinel OUTROS (texto livre em
     campo extra). O sentinel não é gravado; o servidor grava o texto. */
  var OPERADORAS = ["VIVO", "CLARO", "TIM", "OI", "OUTROS"];
  var OPERADORAS_PRINCIPAIS = ["VIVO", "CLARO", "TIM", "OI"];
  var TIPOS_LINK_WAN = ["WAN"];
  var TIPOS_LINK_UNIDADE = [
    "LAN",
    "LOOPBACK_VIVO",
    "LOOPBACK_CLIENTE",
    "LOOPBACK_ON_BGP",
    "TRANSITO",
    "TUNNEL",
    "DHCP_SERVER",
    "EXCLUDED_RANGE",
    "AP_RANGE",
    "REDE_VLAN",
  ];

  function isLinkTipoUnidade(tipo) {
    return TIPOS_LINK_UNIDADE.indexOf(String(tipo || "").toUpperCase()) >= 0;
  }

  function isLinkTipoWan(tipo) {
    return String(tipo || "").toUpperCase() === "WAN";
  }

  function fillTipoLinkSelect(sel, scope, selected) {
    if (!sel) return;
    var values = scope === "unidade" ? TIPOS_LINK_UNIDADE : TIPOS_LINK_WAN;
    var cur = selected != null ? String(selected) : "";
    sel.innerHTML = "";
    values.forEach(function (v) {
      var o = document.createElement("option");
      o.value = v;
      o.textContent = v;
      sel.appendChild(o);
    });
    if (cur && values.indexOf(cur) < 0) {
      var ox = document.createElement("option");
      ox.value = cur;
      ox.textContent = cur + " (legado)";
      sel.appendChild(ox);
    }
    sel.value = cur && (values.indexOf(cur) >= 0 || sel.querySelector('option[value="' + cur + '"]'))
      ? cur
      : values[0];
  }

  function normalizeVendor(v) {
    var s = String(v || "").trim();
    if (/^fortigate$/i.test(s)) return "Fortinet";
    return s;
  }

  function fillSelectOptions(sel, values, selected, opts) {
    if (!sel) return;
    opts = opts || {};
    var keepEmpty = opts.keepEmpty !== false;
    var emptyLabel = opts.emptyLabel != null ? opts.emptyLabel : "Selecione...";
    var cur = selected != null ? String(selected) : String(sel.value || "");
    if (opts.normalizeVendor) cur = normalizeVendor(cur);
    sel.innerHTML = "";
    if (keepEmpty) {
      var o0 = document.createElement("option");
      o0.value = "";
      o0.textContent = emptyLabel;
      sel.appendChild(o0);
    }
    var seen = {};
    (values || []).forEach(function (v) {
      seen[String(v)] = 1;
      var o = document.createElement("option");
      o.value = v;
      o.textContent = v;
      sel.appendChild(o);
    });
    if (cur && !seen[cur]) {
      var ox = document.createElement("option");
      ox.value = cur;
      ox.textContent = cur + " (legado)";
      sel.appendChild(ox);
    }
    if (cur) sel.value = cur;
  }

  var TIPOS_LINK_COM_RANGE = ["DHCP_SERVER", "EXCLUDED_RANGE", "AP_RANGE"];

  /**
   * Regra única de visibilidade dos campos de link (modal da unidade e
   * accordion do atendimento usam a mesma fonte). Alinhado ao core
   * link_required.wan_grupos_visiveis: modo só em WAN; IP/máscara/GW em
   * STATIC/MPLS; PPPoE; VIVO+STATIC/MPLS → ID VGR + porta.
   * Conectividade da unidade: IP (exceto DHCP_SERVER), máscara/subrede
   * (exceto loopbacks/túnel) e ranges (DHCP/AP/EXCLUDED).
   */
  function linkFieldVisibility(tipo, modo, operadora) {
    tipo = String(tipo || "").toUpperCase();
    modo = String(modo || "").toUpperCase();
    var op = String(operadora || "").toUpperCase();
    var isWan = tipo === "WAN";
    var isStaticMpls = modo === "STATIC" || modo === "MPLS";
    var isLoopback = tipo.indexOf("LOOPBACK") === 0;
    var vis = {
      isWan: isWan,
      isStaticMpls: isStaticMpls,
      eq: isWan,
      modo: isWan,
      operadora: isWan,
      operadoraOutros: isWan && op === "OUTROS",
      designador: isWan,
      vel: isWan,
      ip: isWan ? isStaticMpls : tipo !== "DHCP_SERVER",
      mascara: isWan ? isStaticMpls : !isLoopback,
      gateway: isWan && isStaticMpls,
      subrede: !isWan && !isLoopback && tipo !== "TUNNEL",
      range: !isWan && TIPOS_LINK_COM_RANGE.indexOf(tipo) >= 0,
      vlan: isWan || tipo === "LAN" || tipo === "REDE_VLAN",
      pppoe: isWan && modo === "PPPOE",
      idVgr: isWan && isStaticMpls && op === "VIVO",
      porta: isWan && isStaticMpls && op === "VIVO",
    };
    return vis;
  }

  /**
   * Visibilidade de campos de link (prefixo de ids, ex.: vgrAtLink / vgrLink).
   */
  function syncLinkFormFields(prefix) {
    var tipoEl = document.getElementById(prefix + "Tipo");
    var modoEl = document.getElementById(prefix + "Modo");
    var opEl = document.getElementById(prefix + "Operadora");
    if (!tipoEl) return;
    var tipo = String(tipoEl.value || "").toUpperCase();
    var modo = String((modoEl && modoEl.value) || "").toUpperCase();
    var op = String((opEl && opEl.value) || "").toUpperCase();
    var vis = linkFieldVisibility(tipo, modo, op);

    function setWrap(idSuffix, show) {
      var wrap = document.getElementById(prefix + idSuffix + "Wrap");
      var el = document.getElementById(prefix + idSuffix);
      if (wrap) wrap.classList.toggle("d-none", !show);
      else if (el) {
        var col = el.closest(".col-md-2, .col-md-3, .col-md-4, .col-md-6, .col-12");
        if (col) col.classList.toggle("d-none", !show);
      }
      /* não limpa valor ao ocultar (edit não perde dado); collect ignora ocultos */
    }

    setWrap("Eq", vis.eq);
    setWrap("Modo", vis.modo);
    if (!vis.isWan && modoEl) modoEl.value = "";
    setWrap("Ip", vis.ip);
    setWrap("Mascara", vis.mascara);
    setWrap("Gateway", vis.gateway);
    setWrap("Subrede", vis.subrede);
    setWrap("RangeStart", vis.range);
    setWrap("RangeEnd", vis.range);
    setWrap("Vel", vis.vel);
    setWrap("Designador", vis.designador);
    setWrap("Operadora", vis.operadora);
    setWrap("OperadoraOutros", vis.operadoraOutros);
    setWrap("Vlan", vis.vlan);
    setWrap("PppoeUser", vis.pppoe);
    setWrap("PppoePass", vis.pppoe);
    setWrap("IdVgr", vis.idVgr);
    setWrap("Porta", vis.porta);
    var pend = document.getElementById(prefix + "Pendencias");
    if (pend && !(vis.isWan && vis.isStaticMpls && op === "VIVO")) {
      pend.classList.add("d-none");
    }

    var hint = document.getElementById(prefix + "CampoHint");
    if (hint) {
      if (!vis.isWan) {
        hint.textContent = vis.range
          ? "Conectividade da unidade: informe máscara/subrede e o range (início e fim dentro da rede)."
          : "Conectividade da unidade (sem equipamento). Modo WAN não se aplica.";
      } else if (op === "VIVO" && vis.isStaticMpls) {
        hint.textContent =
          "VIVO + " + modo + ": informe IP, máscara, gateway, ID VGR do link e identificação da porta.";
      } else if (vis.isStaticMpls) {
        hint.textContent = modo + ": IP, máscara e gateway são obrigatórios.";
      } else if (vis.pppoe) {
        hint.textContent = "PPPoE: informe usuário e senha (em branco mantém os já gravados).";
      } else if (modo === "DHCP") {
        hint.textContent = "DHCP: IP obtido automaticamente — campos de IP ocultos.";
      } else {
        hint.textContent = "Selecione o modo de conexão da WAN.";
      }
    }
  }

  function bindLinkFormLogic(prefix) {
    ["Tipo", "Modo", "Operadora"].forEach(function (suf) {
      var el = document.getElementById(prefix + suf);
      if (el) {
        el.addEventListener("change", function () {
          syncLinkFormFields(prefix);
        });
      }
    });
    syncLinkFormFields(prefix);
  }

  global.VgrDt = {
    esc: esc,
    renderText: renderText,
    yesNo: yesNo,
    formatBrDate: formatBrDate,
    formatBrTime: formatBrTime,
    formatBrDateTime: formatBrDateTime,
    VENDORS: VENDORS,
    OPERADORAS: OPERADORAS,
    OPERADORAS_PRINCIPAIS: OPERADORAS_PRINCIPAIS,
    TIPOS_LINK_COM_RANGE: TIPOS_LINK_COM_RANGE,
    linkFieldVisibility: linkFieldVisibility,
    TIPOS_LINK_WAN: TIPOS_LINK_WAN,
    TIPOS_LINK_UNIDADE: TIPOS_LINK_UNIDADE,
    isLinkTipoUnidade: isLinkTipoUnidade,
    isLinkTipoWan: isLinkTipoWan,
    fillTipoLinkSelect: fillTipoLinkSelect,
    fillSelectOptions: fillSelectOptions,
    syncLinkFormFields: syncLinkFormFields,
    bindLinkFormLogic: bindLinkFormLogic,
    csrfToken: csrfToken,
    jsonFetch: jsonFetch,
    toast: toast,
    mountToolbar: mountToolbar,
    clientAjax: clientAjax,
    baseOpts: baseOpts,
    acoesAbrir: acoesAbrir,
    acoesCliente: acoesCliente,
    acoesUnidade: acoesUnidade,
    acoesEquipamento: acoesEquipamento,
    acoesLink: acoesLink,
    acoesField: acoesField,
    acoesAtendimento: acoesAtendimento,
    acoesAgendamento: acoesAgendamento,
  };
})(window);
