/**
 * @file vgr/static/js/vgr_gestao_atendimentos.js
 * @module VGR — Gestão de atendimentos
 *
 * Espelho do dashboard de gestão PRODESP (script_gestao_atendimentos_prodesp.js):
 *   - filtro de período (Data Início/Fim + Hoje/Ontem/7d);
 *   - painel de KPIs macro com cards clicáveis que filtram a tabela;
 *   - tabela #tblVgrAtendimentos (a MESMA da fila, montada por vgr_atendimentos.js,
 *     com os mesmos modais de visualizar/editar), carregada com as linhas do período;
 *   - download do Relatório de Atividades (XLSX/CSV).
 *
 * Fonte única: GET /vgr/api/gestao/atendimentos devolve as linhas da tabela
 * (`data`) e os KPIs (`resumo`) no MESMO payload — card e tabela nunca divergem.
 * Cada linha traz `gestao_grupos` (chaves de KPI) usado pelo filtro dos cards.
 *
 * Regras de calendário (prodesp/docs/dashboard-e-gestao.md):
 *   - padrão ao abrir: hoje/hoje; datas futuras permitidas;
 *   - início > fim (mudou início) → fim = início; fim < início (mudou fim) → início = fim;
 *   - alterar data recarrega KPIs + tabela no `change` (sem botão Aplicar);
 *   - presets: Hoje, Ontem, 7d (hoje−6 → hoje); Limpar Filtros volta para hoje.
 *
 * Depende de: jQuery + DataTables, vgr_dt_common.js (VgrDt), vgr_atendimentos.js
 * (cria a tabela e expõe window.VgrAtendimentos) e, opcionalmente,
 * login/static/js/login_periodo_datas.js (LoginPeriodoDatas).
 */
(function () {
  "use strict";

  var CFG = window.VGR_GESTAO || {};
  var RELATORIO_URL = CFG.relatorioUrl || "/vgr/gestao/atendimentos/relatorio";
  var AUTO_REFRESH_MS = Math.max(Number(CFG.autoRefreshMs) || 90000, 15000);
  var TABLE_ID = "tblVgrAtendimentos";

  var KPI_KEYS = [
    "total",
    "agendados",
    "em_atendimento",
    "aguarda_cliente",
    "aguarda_contratada",
    "fluxo_tecnico",
    "quebra",
    "concluido_parcial",
    "day_after",
    "concluidos",
    "pct_concluidos",
    "tempo_medio",
    "aguarda_gestao",
  ];

  var FILTRO_LABELS = {
    agendados: "Agendados (sem atividade iniciada)",
    em_atendimento: "Em Atendimento",
    aguarda_cliente: "Aguarda Cliente",
    aguarda_contratada: "Aguarda Contratada",
    aguarda_gestao: "Aguarda Gestão",
    fluxo_tecnico: "Fluxo Técnico",
    quebra: "Quebra",
    concluido_parcial: "Concluído Parcial",
    day_after: "Day After",
    concluidos: "Concluídos",
  };

  var gestaoFiltro = null;
  var autoTimer = null;

  function byId(id) {
    return document.getElementById(id);
  }

  function toast(msg, ok, kind) {
    if (window.VgrDt && typeof window.VgrDt.toast === "function") {
      window.VgrDt.toast(msg, ok, kind);
    } else {
      window.alert(msg);
    }
  }

  function dtApi() {
    if (window.VgrAtendimentos && window.VgrAtendimentos.api) {
      return window.VgrAtendimentos.api;
    }
    if (window.jQuery && $.fn.dataTable && $.fn.dataTable.isDataTable("#" + TABLE_ID)) {
      return $("#" + TABLE_ID).DataTable();
    }
    return null;
  }

  // ==================================================================
  // DATAS (local — evita o deslocamento de fuso do toISOString)
  // ==================================================================
  function isoLocal(d) {
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1).padStart(2, "0");
    var day = String(d.getDate()).padStart(2, "0");
    return y + "-" + m + "-" + day;
  }

  function hojeISO() {
    var L = window.LoginPeriodoDatas;
    if (L && typeof L.hojeISO === "function") {
      return L.hojeISO();
    }
    return isoLocal(new Date());
  }

  function deslocarDias(iso, dias) {
    var p = String(iso).split("-");
    var d = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
    d.setDate(d.getDate() + dias);
    return isoLocal(d);
  }

  function periodoAtual() {
    return {
      start: (byId("startDate").value || "").trim(),
      end: (byId("endDate").value || "").trim(),
    };
  }

  /** Datas futuras permitidas (agendamentos): remove `max` do calendário nativo. */
  function permitirDatasFuturas() {
    byId("startDate").removeAttribute("max");
    byId("endDate").removeAttribute("max");
  }

  /** Mantém o intervalo coerente conforme o campo editado (sem lock de dia único). */
  function normalizarIntervalo(changedEl) {
    var $start = byId("startDate");
    var $end = byId("endDate");
    var s = ($start.value || "").trim();
    var e = ($end.value || "").trim();
    if (!s || !e || s <= e) return;
    if (changedEl && changedEl.id === "endDate") {
      $start.value = e;
    } else {
      // startDate, preset, limpar ou sem origem: sobe o fim
      $end.value = s;
    }
  }

  function aplicarPresetLocal(preset) {
    var hoje = hojeISO();
    var ini = hoje;
    var fim = hoje;
    if (preset === "ontem") {
      ini = deslocarDias(hoje, -1);
      fim = ini;
    } else if (preset === "7d") {
      ini = deslocarDias(hoje, -6);
    }
    byId("startDate").value = ini;
    byId("endDate").value = fim;
  }

  function aplicarPreset(preset) {
    var L = window.LoginPeriodoDatas;
    if (L && typeof L.aplicarPreset === "function") {
      L.aplicarPreset(
        "startDate",
        "endDate",
        preset,
        function () {
          permitirDatasFuturas();
          recarregarParaPeriodo(null);
        },
        true
      );
      return;
    }
    aplicarPresetLocal(preset);
    permitirDatasFuturas();
    recarregarParaPeriodo(null);
  }

  // ==================================================================
  // KPIs (vêm no mesmo payload da tabela: json.resumo)
  // ==================================================================
  function kpiEls() {
    return document.querySelectorAll("[data-vgr-kpi]");
  }

  function setLoading(loading) {
    var row = byId("vgr-gestao-kpi-macro-row");
    if (row) row.classList.toggle("dashboard-kpi-row--loading", !!loading);
    var icon = byId("vgrGestaoRefreshIcon");
    if (icon) icon.classList.toggle("fa-spin", !!loading);
  }

  /** Limpa os cards ao trocar período — não exibe totais do intervalo anterior. */
  function marcarPeriodoPendente() {
    kpiEls().forEach(function (el) {
      el.textContent = "—";
    });
    var hint = byId("vgrGestaoTotalHint");
    if (hint) hint.textContent = "Carregando período…";
    var taxa = byId("vgrGestaoTaxaHint");
    if (taxa) taxa.textContent = "—";
  }

  function renderKpis(resumo) {
    var k = (resumo && resumo.kpis) || {};
    kpiEls().forEach(function (el) {
      var key = el.getAttribute("data-vgr-kpi");
      if (KPI_KEYS.indexOf(key) < 0) return;
      var val = k[key];
      if (val == null || val === "") val = key === "tempo_medio" ? "00:00:00" : 0;
      el.textContent = String(val) + (el.getAttribute("data-vgr-kpi-suffix") || "");
    });

    var hint = byId("vgrGestaoTotalHint");
    if (hint) hint.textContent = (resumo && resumo.hint_total) || "—";

    var taxa = byId("vgrGestaoTaxaHint");
    if (taxa) {
      taxa.textContent =
        Number(k.total) > 0
          ? k.concluidos + " ÷ " + k.total + " no período"
          : "Concluídos ÷ total no período";
    }

    var tempo = byId("vgrGestaoTempoHint");
    if (tempo) {
      var n = Number(k.tempo_medio_amostras) || 0;
      tempo.textContent = n
        ? "Abertura → fechamento · " + n + " finalizado(s)"
        : "Abertura → fechamento (finalizados)";
    }
  }

  function marcarAtualizado() {
    var el = byId("vgrGestaoLastRefresh");
    if (!el) return;
    el.textContent =
      "Atualizado às " +
      new Date().toLocaleTimeString("pt-BR", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
  }

  /** Resposta da tabela (xhr.dt): aplica os KPIs se for do período atual. */
  function aoCarregarTabela(json) {
    if (json && json.resumo && json.resumo.periodo) {
      var atual = periodoAtual();
      var pr = json.resumo.periodo;
      // Resposta defasada (período trocado no meio do caminho): outra carga está
      // a caminho — mantém o «carregando» e não mexe nos cards.
      if (pr.start_date !== atual.start || pr.end_date !== atual.end) return;
    }
    setLoading(false);
    if (!json || json.success === false || !json.resumo) {
      marcarPeriodoPendente();
      var hint = byId("vgrGestaoTotalHint");
      if (hint) hint.textContent = "—";
      toast((json && json.message) || "Falha ao carregar os atendimentos do período.", false);
      return;
    }
    renderKpis(json.resumo);
    marcarAtualizado();
  }

  // ==================================================================
  // TABELA: recarga e filtro pelos cards
  // ==================================================================
  function recarregarTabela(resetPaging) {
    var api = dtApi();
    if (!api) return;
    setLoading(true);
    api.ajax.reload(null, !!resetPaging);
  }

  function agendarAutoRefresh() {
    if (autoTimer) clearTimeout(autoTimer);
    autoTimer = setTimeout(function () {
      if (document.visibilityState !== "hidden") {
        recarregarTabela(false);
      }
      agendarAutoRefresh();
    }, AUTO_REFRESH_MS);
  }

  /** Normaliza intervalo e recarrega imediatamente (sem debounce, igual PRODESP). */
  function recarregarParaPeriodo(changedEl) {
    normalizarIntervalo(changedEl);
    var per = periodoAtual();
    if (!per.start || !per.end) return;
    marcarPeriodoPendente();
    recarregarTabela(true);
    agendarAutoRefresh();
  }

  function registrarFiltroCards() {
    if (window._vgrGestaoDtSearchRegistered || !(window.jQuery && $.fn.dataTable)) return;
    $.fn.dataTable.ext.search.push(function (settings, _data, _idx, rowData) {
      if (!gestaoFiltro || !settings.nTable || settings.nTable.id !== TABLE_ID) return true;
      var grupos = (rowData && rowData.gestao_grupos) || [];
      return grupos.indexOf(gestaoFiltro) >= 0;
    });
    window._vgrGestaoDtSearchRegistered = true;
  }

  function atualizarIndicadorFiltro() {
    document.querySelectorAll(".vgr-gestao-filterable-card").forEach(function (card) {
      var key = card.getAttribute("data-vgr-gestao-filtro") || "";
      card.classList.toggle("vgr-gestao-card-ativo", !!gestaoFiltro && key === gestaoFiltro);
    });
    var bar = byId("vgr-gestao-filtro-bar");
    var label = byId("vgr-gestao-filtro-label");
    if (bar) bar.classList.toggle("d-none", !gestaoFiltro);
    if (label) label.textContent = gestaoFiltro ? FILTRO_LABELS[gestaoFiltro] || gestaoFiltro : "";
  }

  function aplicarFiltroCard(key) {
    gestaoFiltro = key || null;
    atualizarIndicadorFiltro();
    var api = dtApi();
    if (api) api.draw();
  }

  function rolarParaTabela() {
    var header = byId("vgr-gestao-table-header");
    if (!header) return;
    var top = header.getBoundingClientRect().top + window.pageYOffset - 70;
    window.scrollTo({ top: top, behavior: "smooth" });
  }

  /** Limpa busca global, column.search e filtros do ColumnControl (padrão PRODESP). */
  function limparFiltrosColunas(api) {
    if (!api) return;
    api.search("");
    api.columns().search("");
    if (typeof api.columns().ccSearchClear === "function") {
      api.columns().ccSearchClear();
    }
  }

  // ==================================================================
  // RELATÓRIO
  // ==================================================================
  function baixarRelatorio(format) {
    var per = periodoAtual();
    if (!per.start || !per.end) {
      toast("Por favor, selecione um período de datas para gerar o relatório.", false, "warn");
      return;
    }
    var url =
      RELATORIO_URL +
      "?start_date=" +
      encodeURIComponent(per.start) +
      "&end_date=" +
      encodeURIComponent(per.end) +
      "&format=" +
      encodeURIComponent(format);
    toast(
      "Gerando relatório " + format.toUpperCase() + ". O download iniciará automaticamente em instantes.",
      true
    );
    window.location.href = url;
  }

  // ==================================================================
  // INICIALIZAÇÃO E EVENTOS
  // ==================================================================
  /** Liga os eventos da tabela já — antes de a 1ª carga AJAX terminar. */
  function ligarTabela() {
    var tableEl = byId(TABLE_ID);
    if (!tableEl || !window.jQuery) return;
    registrarFiltroCards();
    $(tableEl)
      .on("preXhr.dt", function () {
        setLoading(true);
      })
      .on("xhr.dt", function (_e, _settings, json) {
        aoCarregarTabela(json);
      });
    // Se a 1ª carga já terminou antes deste bind, aplica o que já chegou.
    var api = dtApi();
    var json = api && api.ajax && typeof api.ajax.json === "function" ? api.ajax.json() : null;
    if (json) aoCarregarTabela(json);
  }

  function init() {
    var $start = byId("startDate");
    var $end = byId("endDate");
    if (!$start || !$end) return;

    var hoje = hojeISO();
    if (!$start.value) $start.value = hoje;
    if (!$end.value) $end.value = hoje;
    permitirDatasFuturas();
    normalizarIntervalo(null);

    [$start, $end].forEach(function (el) {
      el.addEventListener("change", function () {
        recarregarParaPeriodo(this);
      });
    });

    document.querySelectorAll("[data-vgr-periodo-preset]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var preset = btn.getAttribute("data-vgr-periodo-preset");
        if (preset) aplicarPreset(preset);
      });
    });

    document.querySelectorAll(".vgr-gestao-filterable-card").forEach(function (card) {
      var acionar = function () {
        var key = card.getAttribute("data-vgr-gestao-filtro") || "";
        // Total: limpa o filtro. Demais: alterna (2º clique no mesmo card limpa).
        aplicarFiltroCard(!key || key === gestaoFiltro ? null : key);
        rolarParaTabela();
      };
      card.addEventListener("click", acionar);
      card.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          acionar();
        }
      });
    });

    var btnFiltroLimpar = byId("btnVgrGestaoFiltroLimpar");
    if (btnFiltroLimpar) {
      btnFiltroLimpar.addEventListener("click", function () {
        aplicarFiltroCard(null);
      });
    }
    // «Limpar» da toolbar da tabela (PortalDtToolbar) também zera o filtro do card.
    document.addEventListener("vgr:atendimentos:limpar", function () {
      gestaoFiltro = null;
      atualizarIndicadorFiltro();
    });

    var btnClear = byId("btnVgrGestaoClear");
    if (btnClear) {
      btnClear.addEventListener("click", function () {
        var L = window.LoginPeriodoDatas;
        if (L && typeof L.resetarParHoje === "function") {
          L.resetarParHoje("startDate", "endDate");
        } else {
          var h = hojeISO();
          $start.value = h;
          $end.value = h;
        }
        permitirDatasFuturas();
        gestaoFiltro = null;
        atualizarIndicadorFiltro();
        limparFiltrosColunas(dtApi());
        recarregarParaPeriodo(null);
      });
    }

    var btnRefresh = byId("btnVgrGestaoRefreshNow");
    if (btnRefresh) {
      btnRefresh.addEventListener("click", function () {
        recarregarTabela(false);
        agendarAutoRefresh();
      });
    }

    var btnXlsx = byId("btnVgrDownloadXLSX");
    if (btnXlsx) {
      btnXlsx.addEventListener("click", function (e) {
        e.preventDefault();
        baixarRelatorio("xlsx");
      });
    }
    var btnCsv = byId("btnVgrDownloadCSV");
    if (btnCsv) {
      btnCsv.addEventListener("click", function (e) {
        e.preventDefault();
        baixarRelatorio("csv");
      });
    }

    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState !== "hidden") {
        recarregarTabela(false);
        agendarAutoRefresh();
      }
    });

    atualizarIndicadorFiltro();
    agendarAutoRefresh();
  }

  // Bind imediato (a tabela já foi criada por vgr_atendimentos.js, carregado antes).
  ligarTabela();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
