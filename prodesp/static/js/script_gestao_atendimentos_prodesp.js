/**
 * @file prodesp/static/js/script_gestao_atendimentos_prodesp.js
 * @module PRODESP — Dashboard de gestão
 *
 * Finalidade:
 *   Dashboard executivo: filtro por período, KPIs macro, gráficos (timeline, substatus
 *   por status, contratada), painéis colapsáveis, tabela #tabela-gestao-atendimentos,
 *   exportação XLSX/CSV e KPIs de tempo por etapa (quando autorizado).
 *
 * Telas:
 *   - prodesp/templates/dashboard_atendimentos_prodesp.html
 *
 * Depende de:
 *   - jQuery, Bootstrap 5, Chart.js, DataTables 2 + ColumnControl
 *   - core/static/js/datatable/portal_dt_defaults.js (PortalDt)
 *   - prodesp_datatable_page_length.js, prodesp_datatable_font_size.js
 *   - prodesp_chart_collapse_prefs.js, prodesp_historico_view.js
 *
 * API principal:
 *   GET /prodesp/api/gestao_atendimentos (dados agregados + linhas da tabela)
 */
$(function () {
    function prodespGestaoEsc(s) {
        if (s == null || s === undefined) return "";
        return String(s)
            .replace(/&/g, "&amp;")
            .replace(/"/g, "&quot;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }

    function prodespGestaoIsAdminUser() {
        return parseInt(String(window.PRODESP_ADMIN_USER || 0), 10) === 1;
    }

    /** ColumnControl / i18n — core PortalDt (fallback se script não carregou). */
    function prodespGestaoDtCcSearchList() {
        if (window.PortalDt && typeof window.PortalDt.ccSearchList === "function") {
            return window.PortalDt.ccSearchList();
        }
        return [
            [
                { extend: "searchList", ajaxOnly: false },
                "spacer",
                "orderAsc",
                "orderDesc",
                "orderClear",
            ],
        ];
    }

    function prodespGestaoDtCcOrderOnly() {
        if (window.PortalDt && typeof window.PortalDt.ccOrderOnly === "function") {
            return window.PortalDt.ccOrderOnly();
        }
        return [["orderAsc", "orderDesc", "orderClear"]];
    }

    function prodespGestaoDtOrderingSilent() {
        if (window.PortalDt && typeof window.PortalDt.orderingSilent === "function") {
            return window.PortalDt.orderingSilent();
        }
        return { indicators: false, handler: false };
    }

    function prodespGestaoDtLanguage() {
        if (window.PortalDt && typeof window.PortalDt.languagePtBr === "function") {
            return window.PortalDt.languagePtBr();
        }
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
            columnControl: {
                search: "Pesquisar colunas",
                orderAsc: "Ordenar asc",
                orderDesc: "Ordenar desc",
                orderClear: "Limpar ordenação",
                buttons: {
                    search: "Pesquisar colunas",
                    searchPlaceholder: "Digite para buscar...",
                },
                list: {
                    all: "Selecionar tudo",
                    empty: "Vazio",
                    none: "Limpar seleção",
                    search: "Buscar...",
                },
            },
        };
    }

    async function prodespGestaoAdminExcluirAtendimentoFetch(idAtendimento) {
        try {
            const resp = await fetch(`/prodesp/api/admin/atendimento/${idAtendimento}`, { method: "DELETE" });
            const json = await resp.json().catch(() => ({}));
            if (!resp.ok || !json.success) {
                showToast(json.message || "Não foi possível excluir o atendimento.", "danger");
                return;
            }
            showToast(json.message || "Atendimento excluído.", "success");
            refreshDashboardData();
        } catch (_e) {
            showToast("Erro ao excluir atendimento.", "danger");
        }
    }

    function prodespGestaoAdminExcluirAtendimento(idAtendimento) {
        if (!prodespGestaoIsAdminUser()) return;
        const msg =
            `Excluir permanentemente o atendimento #${idAtendimento}?\n\n` +
            "Logs, observações vinculadas e registros do atendimento serão removidos. " +
            "Esta ação não pode ser desfeita.";
        if (!window.confirm(msg)) return;
        void prodespGestaoAdminExcluirAtendimentoFetch(idAtendimento);
    }

    async function prodespGestaoAdminRemoverAgendamentoFetch(idVgr) {
        try {
            const resp = await fetch(
                `/prodesp/api/admin/unidade/vgr/${encodeURIComponent(idVgr)}/agendamento`,
                { method: "DELETE" }
            );
            const json = await resp.json().catch(() => ({}));
            if (!resp.ok || !json.success) {
                showToast(json.message || "Não foi possível remover o agendamento.", "danger");
                return;
            }
            showToast(json.message || "Agendamento removido.", "success");
            refreshDashboardData();
        } catch (_e) {
            showToast("Erro ao remover agendamento.", "danger");
        }
    }

    function prodespGestaoAdminRemoverAgendamento(idVgr) {
        if (!prodespGestaoIsAdminUser()) return;
        const vgr = String(idVgr || "").trim();
        if (!vgr) return;
        const msg =
            `Remover o agendamento da unidade VGR ${vgr}?\n\n` +
            "Data e hora agendadas serão limpas. Esta ação não pode ser desfeita.";
        if (!window.confirm(msg)) return;
        void prodespGestaoAdminRemoverAgendamentoFetch(idVgr);
    }

    // ==================================================================
    // VARIÁVEIS GLOBAIS
    // ===================================================================
    let dataTableInstance = null;
    let rawAtendimentosData = []; // Armazena TODOS os dados
    let rawScheduledData = {}; // Armazena dados de agendamento (Programado)
    let rawMotivosForaPadraoData = [];
    let rawTemposEtapaData = null;
    let dashboardAjaxXhr = null;
    let latestDashboardLoadSeq = 0;
    let dashboardAppliedLoadSeq = 0;
    /** Período efetivamente carregado (só muda ao alterar datas / limpar filtros / carga inicial). */
    let dashboardDatesAtLastApply = { start: "", end: "" };
    /** Metadados por seq (data() → dataSrc), para quando jqXHR não estiver disponível. */
    const dashboardLoadMetaBySeq = new Map();
    let dashboardLoadingWatchdogTimer = null;
    const DASHBOARD_LOAD_WATCHDOG_MS = 20000;
    let timelineChartInstance = null;
    let contratadaChartInstance = null;
    const substatusByStatusChartInstances = {};

    /** Gráficos de substatus no painel «Distribuição» — um por status principal. */
    const SUBSTATUS_CHART_GROUPS = [
        {
            key: 'migrados',
            aggKey: 'migrados',
            title: 'Migrados',
            canvasId: 'chartSubstatusMigrados',
            panelClass: 'dashboard-substatus-chart-panel--migrados',
        },
        {
            key: 'em-atendimento',
            aggKey: 'emAtendimento',
            title: 'Em atendimento',
            canvasId: 'chartSubstatusEmAtendimento',
            panelClass: 'dashboard-substatus-chart-panel--em-atendimento',
        },
        {
            key: 'quebra',
            aggKey: 'quebra',
            title: 'Quebra',
            canvasId: 'chartSubstatusQuebra',
            panelClass: 'dashboard-substatus-chart-panel--quebra',
        },
        {
            key: 'parcial',
            aggKey: 'parcial',
            title: 'Concluído parcial',
            canvasId: 'chartSubstatusParcial',
            panelClass: 'dashboard-substatus-chart-panel--parcial',
        },
    ];
    let activeContratadaFilter = null;
    /** Filtro da tabela alinhado ao KPI «Agendadas no período» (data_agendamento preenchido). */
    let activeAgendadasPeriodoFilter = false;
    let timeOffset = 0;

    /** Índices de coluna Status/Substatus (alinhados a ProdespDtColumns / GESTAO_META). */
    function prodespGestaoDtCol(name) {
        const cols = window.ProdespDtColumns && window.ProdespDtColumns.GESTAO_COL;
        if (cols && cols[name] != null && cols[name] >= 0) {
            return cols[name];
        }
        const fallback = { STATUS: 8, SUBSTATUS: 9 };
        return fallback[name] != null ? fallback[name] : -1;
    }

    const SUBSTATUS_META = {
        Triagem: { label: 'Aguarda Gestão', icon: 'fas fa-filter', color: 'text-secondary' },
        'Aguarda Gestão': { label: 'Aguarda Gestão', icon: 'fas fa-filter', color: 'text-secondary' },
        'Aguardando Cliente': { label: 'Aguardando Cliente', icon: 'fas fa-user-clock', color: 'text-warning' },
        'Aguarda Contratada': { label: 'Aguarda Contratada', icon: 'fas fa-building', color: 'text-warning' },
        'Aguarda Licença': { label: 'Aguarda Licença', icon: 'fas fa-id-card', color: 'text-warning' },
        'Com Suporte': { label: 'Com Suporte', icon: 'fas fa-life-ring', color: 'text-info' },
        'Aguardando Config. Remota': { label: 'Ag. Cfg. Remota', icon: 'fas fa-hourglass-half', color: 'text-secondary' },
        'Em Configuração Remota': { label: 'Em Cfg. Remota', icon: 'fas fa-laptop-code', color: 'text-primary' },
        'Aguardando Config. MPLS': { label: 'Ag. Cfg. MPLS', icon: 'fas fa-hourglass-half', color: 'text-secondary' },
        'Em Configuração do MPLS': { label: 'Em Cfg. MPLS', icon: 'fas fa-network-wired', color: 'text-primary' },
        'Aguardando Caderno de Teste': { label: 'Ag. Cad. Teste', icon: 'fas fa-hourglass-half', color: 'text-secondary' },
        'Em Caderno de Teste': { label: 'Em Cad. Teste', icon: 'fas fa-clipboard-list', color: 'text-info' },
        'Pendente Configuração Remota': { label: 'Pend. Cfg. Remota', icon: 'fas fa-laptop-medical', color: 'text-warning' },
        'Pendente Configuração MPLS': { label: 'Pend. Cfg. MPLS', icon: 'fas fa-network-wired', color: 'text-warning' },
        'Pendente Link IPD': { label: 'Pend. Link IPD', icon: 'fas fa-satellite-dish', color: 'text-warning' },
        'Pendente Link MPLS': { label: 'Pend. Link MPLS', icon: 'fas fa-ethernet', color: 'text-warning' },
        'Quebra Field': { label: 'Quebra Field', icon: 'fas fa-hard-hat', color: 'text-danger' },
        'Quebra Link': { label: 'Quebra Link', icon: 'fas fa-unlink', color: 'text-danger' },
        'Quebra Infra': { label: 'Quebra Infra', icon: 'fas fa-city', color: 'text-danger' },
        'Quebra Hardware': { label: 'Quebra Hardware', icon: 'fas fa-server', color: 'text-danger' },
        'Quebra Cliente': { label: 'Quebra Cliente', icon: 'fas fa-store-slash', color: 'text-danger' },
        'Quebra Vita': { label: 'Quebra Vita', icon: 'fas fa-building', color: 'text-danger' },
        Concluído: { label: 'Migrado', icon: 'fas fa-check-double', color: 'text-success' },
    };

    /**
     * Capacidade máxima de substatus por status (espelha populateSubstatus em script_atendimentos_prodesp.js).
     * Em Atendimento: 7 etapas do fluxo + Aguardando Cliente + Com Suporte + Aguarda Contratada + Aguarda Licença = 11.
     * Concluído Parcial: 5 opções no select.
     * Quebra: Link, Infra, Hardware, Field, Cliente, Vita = 6.
     */
    const DASHBOARD_SUBSTATUS_CAPACITY = {
        migrados: { max: 1, gridCols: 1, spanFull: false },
        'em-atendimento': { max: 11, gridCols: 3, spanFull: false },
        quebra: { max: 6, gridCols: 3, spanFull: false },
        parcial: { max: 5, gridCols: 3, spanFull: false },
    };

    const DASHBOARD_STATUS_GROUPS = [
        {
            id: 'resumo',
            title: 'Atendimentos',
            hint: 'Unidades com atendimento iniciado no período (exclui só agendamento)',
            groupClass: 'dashboard-group-resumo',
            icon: 'fas fa-headset',
            iconColor: 'text-secondary',
            filterMode: 'tem-atendimento',
        },
        {
            id: 'migrados',
            title: 'Migrados',
            hint: 'Entrega com êxito — status e substatus «Concluído» (não inclui quebras)',
            groupClass: 'dashboard-group-migrados',
            icon: 'fas fa-check-double',
            iconColor: 'text-success',
            filterMode: 'migrados',
            substatusKeys: ['Concluído'],
        },
        {
            id: 'em-atendimento',
            title: 'Em atendimento',
            hint: 'Status «Em Atendimento» — filas e etapas em andamento',
            groupClass: 'dashboard-group-em-atendimento',
            icon: 'fas fa-cogs',
            iconColor: 'text-primary',
            filterMode: 'status',
            filterValue: 'Em Atendimento',
        },
        {
            id: 'quebra',
            title: 'Quebra',
            hint: 'Status «Quebra» — motivos de não conclusão',
            groupClass: 'dashboard-group-quebra',
            icon: 'fas fa-times-circle',
            iconColor: 'text-danger',
            filterMode: 'status',
            filterValue: 'Quebra',
        },
        {
            id: 'parcial',
            title: 'Concluído parcial',
            hint:
                'Entrega parcial — substatus «Pendente…», Quebra Field e demais opções do status',
            groupClass: 'dashboard-group-parcial',
            icon: 'fas fa-adjust',
            iconColor: 'text-info',
            filterMode: 'status',
            filterValue: 'Concluído Parcial',
        },
    ];

    // ======================================================================
    // FUNÇÕES UTILITÁRIAS
    // ======================================================================
    /**
     * Exibe uma notificação toast do Bootstrap 5
     * @param {string} message - Mensagem a ser exibida
     * @param {string} type - Tipo do toast (success, danger, warning, info)
     * @param {number} delay - Tempo de exibição em ms
     */
    function showToast(message, type = "info", delay = 5000) {
        const toastContainer = document.querySelector(".toast-container");
        if (!toastContainer) {
            console.error("Toast container not found!");
            alert(message);
            return;
        }

        const toastId = "toast-" + Date.now();
        const toastHeaderClass =
            {
                success: "bg-success text-white",
                danger: "bg-danger text-white",
                warning: "bg-warning text-dark",
                info: "bg-primary text-white",
            }[type] || "bg-secondary text-white";

        const toastIcon =
            {
                success: '<i class="fas fa-check-circle me-2"></i>',
                danger: '<i class="fas fa-times-circle me-2"></i>',
                warning: '<i class="fas fa-exclamation-triangle me-2"></i>',
                info: '<i class="fas fa-info-circle me-2"></i>',
            }[type] || '<i class="fas fa-bell me-2"></i>';

        const toastHtml = `
            <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
                <div class="toast-header ${toastHeaderClass}">
                    ${toastIcon}
                    <strong class="me-auto">Atenção</strong>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
                <div class="toast-body">${message}</div>
            </div>`;

        toastContainer.insertAdjacentHTML("beforeend", toastHtml);
        const toastElement = document.getElementById(toastId);
        const toast = new bootstrap.Toast(toastElement, { delay: delay });
        toastElement.addEventListener("hidden.bs.toast", () => toastElement.remove());
        toast.show();
    }

    /**
     * Formata segundos para o formato HH:MM:SS
     * @param {number} totalSeconds - Total de segundos a ser formatado
     * @returns {string} Tempo formatado
     */
    function formatSecondsToHHMMSS(totalSeconds) {
        if (isNaN(totalSeconds) || totalSeconds < 0) {
            return "00:00:00";
        }
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = Math.round(totalSeconds % 60);
        return [hours, minutes, seconds]
            .map((v) => String(v).padStart(2, "0"))
            .join(":");
    }

    /** Linhas que na tabela aparecem como "Agendado" (sem atendimento criado). */
    function rowEhSomenteAgendado(row) {
        const id = row.id_atendimento;
        return id === null || id === undefined || id === "";
    }

    /** YYYY-MM-DD a partir de data ISO/Date/string (agenda ou realização). */
    function prodespDayStr(val) {
        if (val == null || val === "") return "";
        if (val instanceof Date && !isNaN(val.getTime())) {
            const y = val.getFullYear();
            const m = String(val.getMonth() + 1).padStart(2, "0");
            const d = String(val.getDate()).padStart(2, "0");
            return `${y}-${m}-${d}`;
        }
        let s = String(val).trim();
        if (!s) return "";
        if (s.includes("T")) s = s.split("T")[0];
        else if (s.includes(" ")) s = s.split(" ")[0];
        return s.length >= 10 ? s.substring(0, 10) : s;
    }

    function prodespRowAgendaDay(row) {
        return prodespDayStr(row.data_agendamento_timeline || row.data_agendamento);
    }

    function prodespRowRealDay(row) {
        return prodespDayStr(
            row.data_atendimentos || row.data_atendimento || row.data_evento
        );
    }

    function prodespDayInRange(day, minS, maxS) {
        return !!(day && minS && maxS && day >= minS && day <= maxS);
    }

    function prodespIsStatusAtivoGestao(row) {
        return (row.status_atendimentos || "").trim() === "Em Atendimento";
    }

    /**
     * Detalhe do card Total no período (espelha dashboard_escopo.detalhar_total_periodo).
     * Agendado no período = data de agenda no filtro; senão com atividade → Fora Escopo.
     */
    function prodespDetalharTotalPeriodo(rows, minS, maxS) {
        const det = {
            agendados_pend: 0,
            agendados_finalizados: 0,
            agendados_ativos: 0,
            fora_escopo_finalizados: 0,
            fora_escopo_ativos: 0,
        };
        (rows || []).forEach((row) => {
            if (rowEhSomenteAgendado(row)) {
                det.agendados_pend++;
                return;
            }
            const agendaOk = prodespDayInRange(prodespRowAgendaDay(row), minS, maxS);
            const ativo = prodespIsStatusAtivoGestao(row);
            if (agendaOk) {
                if (ativo) det.agendados_ativos++;
                else det.agendados_finalizados++;
            } else if (ativo) {
                det.fora_escopo_ativos++;
            } else {
                det.fora_escopo_finalizados++;
            }
        });
        det.total =
            det.agendados_pend +
            det.agendados_finalizados +
            det.agendados_ativos +
            det.fora_escopo_finalizados +
            det.fora_escopo_ativos;
        return det;
    }

    function prodespFormatHintTotalPeriodo(det) {
        return (
            `${det.agendados_pend} Agendados Pend. + ` +
            `${det.agendados_finalizados} Agendados Finalizados + ` +
            `${det.agendados_ativos} Agendados Ativos + ` +
            `${det.fora_escopo_finalizados} Fora Escopo Finalizado + ` +
            `${det.fora_escopo_ativos} Fora Escopo Ativo`
        );
    }

    /**
     * Séries do gráfico Evolução Diária (espelha dashboard_escopo.timeline_series).
     * Fora Escopo no dia da realização quando a agenda não é o mesmo dia.
     */
    function prodespBuildTimelineSeries(rows, minS, maxS) {
        const scheduledUnits = {};
        const realized = {};
        const foraEscopo = {};

        (rows || []).forEach((row) => {
            const agenda = prodespRowAgendaDay(row);
            if (prodespDayInRange(agenda, minS, maxS)) {
                if (!scheduledUnits[agenda]) scheduledUnits[agenda] = new Set();
                const uid = row.id_unidades != null ? row.id_unidades : row.id_unidade;
                const key =
                    uid != null && uid !== ""
                        ? String(uid)
                        : `_row_${row.id_atendimento || Math.random()}`;
                scheduledUnits[agenda].add(key);
            }

            if (rowEhSomenteAgendado(row)) return;
            const real = prodespRowRealDay(row);
            if (!prodespDayInRange(real, minS, maxS)) return;
            if (agenda && agenda === real) {
                realized[real] = (realized[real] || 0) + 1;
            } else {
                foraEscopo[real] = (foraEscopo[real] || 0) + 1;
            }
        });

        const scheduled = {};
        Object.keys(scheduledUnits).forEach((d) => {
            scheduled[d] = scheduledUnits[d].size;
        });
        return { scheduled, realized, foraEscopo };
    }

    /**
     * % Migrados (card taxa-sucesso-valor) — mesma regra do e-mail (calc_pct_migrados_gestao).
     * Migrados (Concluído + substatus Concluído) ÷ total (agendados + com atividade).
     */
    function prodespCalcPctMigradosGestao(migrados, total) {
        const m = Number(migrados) || 0;
        const t = Number(total) || 0;
        return t > 0 ? Math.round((m / t) * 100) : 0;
    }

    /**
     * Chave de contratada para filtro/KPI/gráfico.
     * Agendados (sem atendimento): contratada planejada da unidade.
     * Com atividade: contratada do atendimento; se vazia, fallback na planejada.
     */
    function prodespContratadaRowKey(row) {
        if (rowEhSomenteAgendado(row)) {
            const planejada = (
                row.contratada_planejada_unidades ||
                row.contratada_atendimentos ||
                ""
            ).trim();
            return planejada || "Não Informado";
        }
        const efetiva = (row.contratada_atendimentos || "").trim();
        if (efetiva) {
            return efetiva;
        }
        const planejada = (row.contratada_planejada_unidades || "").trim();
        return planejada || "Não Informado";
    }

    function prodespContratadaCellHtml(text) {
        const label = (text || "").trim() || "Não Informado";
        const esc = String(label)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/"/g, "&quot;");
        return `<span class="prodesp-dt-contratada-text" title="${esc}">${esc}</span>`;
    }

    /** Com filtro ativo: atendimentos pela contratada efetiva; agendados pela contratada planejada. */
    function prodespFiltrarRowsContratada(rows, contratada) {
        if (!contratada) {
            return rows;
        }
        return rows.filter((row) => prodespContratadaRowKey(row) === contratada);
    }

    function updateContratadaFilterBar() {
        const bar = document.getElementById("dashboard-contratada-filter-bar");
        const label = document.getElementById("dashboard-contratada-filter-label");
        const kpiRow = document.getElementById("dashboard-kpi-macro-row");
        if (!bar) {
            return;
        }
        if (activeContratadaFilter) {
            bar.classList.remove("d-none");
            if (label) {
                label.textContent = activeContratadaFilter;
            }
            if (kpiRow) {
                kpiRow.classList.add("dashboard-kpi-row--filtered");
            }
        } else {
            bar.classList.add("d-none");
            if (kpiRow) {
                kpiRow.classList.remove("dashboard-kpi-row--filtered");
            }
        }
    }

    function prodespSyncContratadaTableFilter() {
        if (dataTableInstance) {
            dataTableInstance.draw();
        }
    }

    function prodespRowTemAgendamentoVisivel(row) {
        const d = row && row.data_agendamento;
        return d != null && String(d).trim() !== "";
    }

    function prodespRegistrarFiltrosCustomizadosDashboardDataTable() {
        if (window._prodespDashboardDtSearchRegistered) {
            return;
        }
        $.fn.dataTable.ext.search.push(function (settings, _data, dataIndex, rowData) {
            const tableId = settings.nTable && settings.nTable.id;
            if (tableId !== "tabela-gestao-atendimentos") {
                return true;
            }
            const row =
                rowData ||
                (dataTableInstance && dataTableInstance.row(dataIndex).data());
            if (!row) {
                return true;
            }
            if (activeAgendadasPeriodoFilter && !prodespRowTemAgendamentoVisivel(row)) {
                return false;
            }
            if (!activeContratadaFilter) {
                return true;
            }
            return prodespContratadaRowKey(row) === activeContratadaFilter;
        });
        window._prodespDashboardDtSearchRegistered = true;
    }

    /** Chaves de substatus devem coincidir com o banco (ex.: "Em Configuração Remota"). */
    function prodespNormalizarChaveCardSubstatus(key) {
        const k = (key || "").trim();
        const aliases = {
            "Configuração Remota": "Em Configuração Remota",
            "Configuração do MPLS": "Em Configuração do MPLS",
            "Caderno de Teste": "Em Caderno de Teste",
            Triagem: "Aguarda Gestão",
        };
        return aliases[k] || k;
    }

    function prodespSubstatusMeta(key) {
        return SUBSTATUS_META[key] || {
            label: key,
            icon: 'fas fa-circle',
            color: 'text-muted',
        };
    }

    function prodespEhQuebraSubstatus(substatus) {
        return /^Quebra\b/i.test((substatus || '').trim());
    }

    /**
     * Agrupa contagens por status (visão supervisor) e substatus dentro de cada grupo.
     */
    function aggregateStatusSubstatus(rows) {
        const groups = {
            resumo: { total: 0, items: {} },
            migrados: { total: 0, items: {} },
            emAtendimento: { total: 0, items: {} },
            quebra: { total: 0, items: {} },
            parcial: { total: 0, items: {} },
        };

        rows.forEach((row) => {
            if (rowEhSomenteAgendado(row)) {
                return;
            }
            groups.resumo.total++;

            const status = (row.status_atendimentos || '').trim();
            const substatusRaw = (row.substatus_atendimentos || '').trim();
            const subKey = substatusRaw ? prodespNormalizarChaveCardSubstatus(substatusRaw) : '';

            if (status === 'Concluído' && subKey === 'Concluído') {
                groups.migrados.total++;
                groups.migrados.items[subKey] = (groups.migrados.items[subKey] || 0) + 1;
                return;
            }
            if (status === 'Quebra' || prodespEhQuebraSubstatus(subKey)) {
                groups.quebra.total++;
                if (subKey) {
                    groups.quebra.items[subKey] = (groups.quebra.items[subKey] || 0) + 1;
                }
                return;
            }
            if (status === 'Concluído Parcial') {
                groups.parcial.total++;
                if (subKey) {
                    groups.parcial.items[subKey] = (groups.parcial.items[subKey] || 0) + 1;
                }
                return;
            }
            if (status === 'Em Atendimento') {
                groups.emAtendimento.total++;
                if (subKey) {
                    groups.emAtendimento.items[subKey] = (groups.emAtendimento.items[subKey] || 0) + 1;
                }
            }
        });

        return groups;
    }

    function computeAgendadosKpis(rows) {
        let comAtendimento = 0;
        let aguardandoAtendimento = 0;
        rows.forEach((row) => {
            if (!row.data_agendamento) {
                return;
            }
            if (rowEhSomenteAgendado(row)) {
                aguardandoAtendimento++;
            } else {
                comAtendimento++;
            }
        });
        const totalAgendadas = comAtendimento + aguardandoAtendimento;
        const taxa =
            totalAgendadas > 0
                ? Math.round((comAtendimento / totalAgendadas) * 100)
                : 0;
        return {
            totalAgendadas,
            comAtendimento,
            aguardandoAtendimento,
            taxaRealizacao: taxa,
        };
    }

    // ===============================
    // FUNÇÕES DE MANIPULAÇÃO DE DADOS
    // ===============================

    /**
     * Atualiza os cards estatísticos
     * @param {Array} dataToProcess - Dados para processamento
     * @param {Date} minDate - Data mínima do filtro
     * @param {Date} maxDate - Data máxima do filtro
     */
    function updateStats(dataToProcess, minDate, maxDate, scheduledData = {}) {
        const filtroContratada = activeContratadaFilter;
        const rowsContratada = prodespFiltrarRowsContratada(dataToProcess, filtroContratada);
        const kpiData = rowsContratada.filter((row) => !rowEhSomenteAgendado(row));

        let agendadosNoPeriodo = 0;
        rowsContratada.forEach((row) => {
            if (rowEhSomenteAgendado(row)) {
                agendadosNoPeriodo++;
            }
        });

        const minS =
            $("#startDate").val() ||
            (minDate instanceof Date ? prodespDayStr(minDate) : prodespDayStr(minDate));
        const maxS =
            $("#endDate").val() ||
            (maxDate instanceof Date ? prodespDayStr(maxDate) : prodespDayStr(maxDate));

        // === KPIs macro (respeitam filtro de contratada quando ativo) ===
        const counts = {
            total: 0,
            agendados: agendadosNoPeriodo,
            com_atividade: 0,
            em_atendimento: 0,
            aguardando_cliente: 0,
            aguarda_gestao: 0,
            aguarda_contratada: 0,
            aguarda_licenca: 0,
            concluído_parcial: 0,
            concluídos: 0,
            quebra: 0,
            quebra_tbra: 0,
            outros_status: 0,
        };
        let totalSecondsArray = [];

        kpiData.forEach((row) => {
            counts.com_atividade++;
            const status = (row.status_atendimentos || "").trim();
            const sub = prodespNormalizarChaveCardSubstatus(
                (row.substatus_atendimentos || "").trim()
            );

            if (status === "Em Atendimento") {
                counts.em_atendimento++;
                if (sub === "Aguardando Cliente") {
                    counts.aguardando_cliente++;
                } else if (sub === "Aguarda Gestão" || sub === "Triagem") {
                    counts.aguarda_gestao++;
                } else if (sub === "Aguarda Contratada") {
                    counts.aguarda_contratada++;
                } else if (sub === "Aguarda Licença") {
                    counts.aguarda_licenca++;
                }
            } else if (status === "Concluído Parcial") {
                counts.concluído_parcial++;
            } else if (status === "Concluído" && sub === "Concluído") {
                counts.concluídos++;
            } else if (status === "Quebra") {
                counts.quebra++;
            } else if (status === "Quebra TBRA") {
                counts.quebra_tbra++;
            } else {
                counts.outros_status++;
            }
            if (row.tempo_em_segundos != null) {
                totalSecondsArray.push(row.tempo_em_segundos);
            }
        });

        counts.total = agendadosNoPeriodo + counts.com_atividade;

        const periodoDet = prodespDetalharTotalPeriodo(rowsContratada, minS, maxS);
        const timelineSeries = prodespBuildTimelineSeries(rowsContratada, minS, maxS);

        // === Agregações para donut (período completo / filtro contratada) ===
        const contratadaAgg = {};
        dataToProcess.forEach((row) => {
            const contratadaKey = prodespContratadaRowKey(row);
            if (!rowEhSomenteAgendado(row) || contratadaKey !== "Não Informado") {
                contratadaAgg[contratadaKey] = (contratadaAgg[contratadaKey] || 0) + 1;
            }
        });

        const statusGroupsAgg = aggregateStatusSubstatus(kpiData);

        const substatusTitle = document.getElementById("substatus-chart-title");
        if (substatusTitle) {
            substatusTitle.textContent = filtroContratada
                ? "Substatus por status (visão filtrada)"
                : "Substatus por status";
        }

        const somaStatus =
            counts.em_atendimento +
            counts.quebra +
            counts.quebra_tbra +
            counts.concluído_parcial +
            counts.concluídos +
            counts.outros_status;
        const somaPartes = counts.agendados + counts.com_atividade;

        $("#total-atendimentos-count").text(counts.total);
        const $agendadosMacro = $("#agendados-macro-count");
        $agendadosMacro.text(counts.agendados);
        if (filtroContratada) {
            $agendadosMacro.attr(
                "title",
                "Agendados da contratada selecionada (sem atividade iniciada)"
            );
        } else {
            $agendadosMacro.removeAttr("title");
        }
        $("#em-atendimento-count").text(counts.em_atendimento);
        $("#aguardando-cliente-macro-count").text(counts.aguardando_cliente);
        $("#aguarda-gestao-macro-count").text(counts.aguarda_gestao);
        $("#aguarda-contratada-macro-count").text(counts.aguarda_contratada);
        $("#aguarda-licenca-macro-count").text(counts.aguarda_licenca);
        $("#concluídos-parcial-count").text(counts.concluído_parcial);
        $("#concluídos-count").text(counts.concluídos);
        $("#quebra-count").text(counts.quebra);
        $("#quebra-tbra-count").text(counts.quebra_tbra);

        const hintEl = document.getElementById("total-periodo-hint");
        if (hintEl) {
            let hint = prodespFormatHintTotalPeriodo(periodoDet);
            if (filtroContratada) {
                hint += " · contratada filtrada";
            }
            if (periodoDet.total !== counts.total) {
                hint += ` · conferência: ${periodoDet.total}/${counts.total}`;
            } else if (somaPartes !== counts.total) {
                hint += ` · conferência: ${somaPartes}/${counts.total}`;
            }
            if (somaStatus !== counts.com_atividade && counts.com_atividade > 0) {
                hint += ` · status: ${somaStatus}/${counts.com_atividade}`;
            }
            hintEl.textContent = hint;
        }

        const descEl = document.getElementById("total-periodo-desc");
        if (descEl) {
            descEl.innerHTML =
                "Detalhe: <strong>Agendados</strong> (pend./finaliz./ativos) + <strong>Fora de Escopo</strong> (finaliz./ativos) no filtro";
        }

        const taxaSucesso = prodespCalcPctMigradosGestao(
            counts.concluídos,
            counts.total
        );
        $("#taxa-sucesso-valor").text(taxaSucesso + "%");
        const taxaHint = document.getElementById("taxa-migrados-hint");
        if (taxaHint) {
            const base = counts.total > 0
                ? `${counts.concluídos} ÷ ${counts.total} no período`
                : "Migrados ÷ total no período";
            taxaHint.textContent = base;
            taxaHint.title =
                "Migrados (status Concluído + substatus Concluído) ÷ total no período (agendados + com atividade iniciada)";
        }

        let mediaTempoStr = "00:00:00";
        if (totalSecondsArray.length > 0) {
            const avgSeconds = totalSecondsArray.reduce((a, b) => a + b, 0) / totalSecondsArray.length;
            mediaTempoStr = formatSecondsToHHMMSS(avgSeconds);
        }
        $("#media-tempo-atendimento-valor").text(mediaTempoStr);

        updateCharts(statusGroupsAgg, timelineSeries, contratadaAgg);
        renderStatusSubstatusGroups(statusGroupsAgg);
        updateAgendadosKpis(
            computeAgendadosKpis(filtroContratada ? rowsContratada : dataToProcess),
            timelineSeries.scheduled,
            filtroContratada
        );
        prodespRenderTemposEtapaComFiltro();
        renderMotivosForaPadraoSummary(rawMotivosForaPadraoData);
        updateContratadaFilterBar();
    }

    /**
     * Recalcula KPIs/cards com os dados já filtrados pelo servidor para o período atual.
     * (Evita re-filtrar no cliente e somar dias de respostas defasadas.)
     */
    function recalculateAndUpdateCards() {
        const minDateStr = $("#startDate").val();
        const maxDateStr = $("#endDate").val();

        if (!minDateStr || !maxDateStr) {
            updateStats([]);
            return;
        }

        const minDate = new Date(minDateStr + "T00:00:00");
        const maxDate = new Date(maxDateStr + "T23:59:59");
        updateStats(rawAtendimentosData, minDate, maxDate, rawScheduledData);
        prodespSyncContratadaTableFilter();
    }

    function prodespSetDashboardKpisLoading(loading) {
        const row = document.getElementById("dashboard-kpi-macro-row");
        if (row) {
            row.classList.toggle("dashboard-kpi-row--loading", !!loading);
        }
    }

    function prodespResetDashboardKpiDisplay() {
        prodespSetDashboardKpisLoading(true);
        [
            "#total-atendimentos-count",
            "#agendados-macro-count",
            "#em-atendimento-count",
            "#aguardando-cliente-macro-count",
            "#aguarda-contratada-macro-count",
            "#aguarda-licenca-macro-count",
            "#quebra-count",
            "#quebra-tbra-count",
            "#concluídos-parcial-count",
            "#concluídos-count",
            "#aguarda-gestao-macro-count",
        ].forEach(function (sel) {
            $(sel).text("—");
        });
        $("#taxa-sucesso-valor").text("—");
        $("#media-tempo-atendimento-valor").text("—");
        const hintEl = document.getElementById("total-periodo-hint");
        if (hintEl) {
            hintEl.textContent = "Carregando período…";
        }
        const taxaHint = document.getElementById("taxa-migrados-hint");
        if (taxaHint) {
            taxaHint.textContent = "—";
        }
    }

    function prodespResolveDashboardAjaxSettings(arg2, arg3) {
        if (arg3 && (arg3.jqXHR != null || arg3.oApi != null)) {
            return arg3;
        }
        if (arg2 && (arg2.jqXHR != null || arg2.oApi != null)) {
            return arg2;
        }
        return null;
    }

    function prodespResolveDashboardLoadMeta(xhr) {
        if (xhr && xhr.__loadSeq != null) {
            return (
                dashboardLoadMetaBySeq.get(xhr.__loadSeq) || {
                    seq: xhr.__loadSeq,
                    start: (xhr.__loadStart || "").trim(),
                    end: (xhr.__loadEnd || "").trim(),
                }
            );
        }
        return dashboardLoadMetaBySeq.get(latestDashboardLoadSeq) || null;
    }

    function prodespCurrentDashboardDateRange() {
        return {
            start: ($("#startDate").val() || "").trim(),
            end: ($("#endDate").val() || "").trim(),
        };
    }

    function prodespDashboardLoadAccepted(meta) {
        if (!meta || meta.seq == null || meta.seq !== latestDashboardLoadSeq) {
            return false;
        }
        return (
            meta.start === dashboardDatesAtLastApply.start &&
            meta.end === dashboardDatesAtLastApply.end
        );
    }

    function prodespClearDashboardLoadingWatchdog() {
        if (dashboardLoadingWatchdogTimer) {
            clearTimeout(dashboardLoadingWatchdogTimer);
            dashboardLoadingWatchdogTimer = null;
        }
    }

    function prodespArmDashboardLoadingWatchdog() {
        prodespClearDashboardLoadingWatchdog();
        dashboardLoadingWatchdogTimer = setTimeout(function () {
            dashboardLoadingWatchdogTimer = null;
            if (!document.getElementById("dashboard-kpi-macro-row")) {
                return;
            }
            const row = document.getElementById("dashboard-kpi-macro-row");
            if (!row.classList.contains("dashboard-kpi-row--loading")) {
                return;
            }
            if (dashboardLoadMetaBySeq.has(latestDashboardLoadSeq)) {
                return;
            }
            prodespOnDashboardReloadComplete(true);
        }, DASHBOARD_LOAD_WATCHDOG_MS);
    }

    function prodespOnDashboardReloadComplete(fromWatchdog) {
        prodespClearDashboardLoadingWatchdog();

        if (dashboardAppliedLoadSeq === latestDashboardLoadSeq && dashboardAppliedLoadSeq > 0) {
            prodespAfterDashboardDataLoaded(dashboardAppliedLoadSeq);
            if (!fromWatchdog) {
                prodespMarcarDtAtualizado();
            }
            return;
        }

        if (dashboardLoadMetaBySeq.has(latestDashboardLoadSeq)) {
            return;
        }

        if (dashboardAjaxXhr && dashboardAjaxXhr.readyState !== 4 && !fromWatchdog) {
            return;
        }

        prodespSetDashboardKpisLoading(false);
        if (!fromWatchdog) {
            prodespMarcarDtAtualizado();
        }
    }

    /** Limpa KPIs ao trocar período — evita exibir totais do intervalo anterior. */
    function prodespMarkDashboardPeriodPending() {
        dashboardAppliedLoadSeq = 0;
        prodespResetDashboardKpiDisplay();
        prodespArmDashboardLoadingWatchdog();
    }

    /**
     * Mantém intervalo coerente conforme o campo editado (sem lock de dia único):
     * - se Data Início > Data Fim → Data Fim = Data Início
     * - se Data Fim < Data Início → Data Início = Data Fim
     * Datas futuras permitidas (agendamentos).
     */
    function prodespNormalizeDashboardDateRange(changedEl) {
        const $start = $("#startDate");
        const $end = $("#endDate");
        const startVal = ($start.val() || "").trim();
        const endVal = ($end.val() || "").trim();
        if (!startVal || !endVal || startVal <= endVal) {
            return;
        }
        const changedId = changedEl && changedEl.id;
        if (changedId === "startDate") {
            $end.val(startVal);
        } else if (changedId === "endDate") {
            $start.val(endVal);
        } else {
            // preset / limpar / sem origem: sobe o fim
            $end.val(startVal);
        }
    }

    /** Garante que o calendário nativo não bloqueie datas futuras (agendamentos). */
    function prodespAllowFutureDashboardDates() {
        const startEl = document.getElementById("startDate");
        const endEl = document.getElementById("endDate");
        if (startEl) startEl.removeAttribute("max");
        if (endEl) endEl.removeAttribute("max");
    }

    /** Normaliza intervalo e recarrega KPIs/tabela imediatamente (sem debounce). */
    function prodespRefreshDashboardForCurrentDates(changedEl) {
        prodespNormalizeDashboardDateRange(changedEl);
        const cur = prodespCurrentDashboardDateRange();
        if (!cur.start || !cur.end) {
            return;
        }
        dashboardDatesAtLastApply = { start: cur.start, end: cur.end };
        prodespMarkDashboardPeriodPending();
        refreshDashboardData();
    }

    /** Callback global para presets (onclick / aplicarPresetPeriodoLogin). */
    window.prodespRefreshDashboardForCurrentDates = function () {
        prodespRefreshDashboardForCurrentDates(null);
    };

    function prodespAplicarPresetPeriodoDashboard(preset) {
        const L = window.LoginPeriodoDatas;
        if (L && typeof L.aplicarPreset === "function") {
            L.aplicarPreset(
                "startDate",
                "endDate",
                preset,
                function () {
                    prodespAllowFutureDashboardDates();
                    prodespRefreshDashboardForCurrentDates(null);
                },
                true
            );
            return;
        }
        if (typeof window.aplicarPresetPeriodoLogin === "function") {
            window.aplicarPresetPeriodoLogin(
                "startDate",
                "endDate",
                preset,
                "prodespRefreshDashboardForCurrentDates"
            );
            prodespAllowFutureDashboardDates();
            return;
        }
        prodespRefreshDashboardForCurrentDates(null);
    }
    window.prodespAplicarPresetPeriodoDashboard = prodespAplicarPresetPeriodoDashboard;

    function buildSubstatusCardHtml(subKey, count, filterMode) {
        const meta = prodespSubstatusMeta(subKey);
        const filterAttrs =
            filterMode === 'migrados'
                ? 'data-filter-mode="migrados"'
                : `data-filter-mode="substatus" data-filter-value="${subKey}"`;
        return `
            <div class="dashboard-substatus-card-item">
                <div class="substatus-card card h-100 border-0 shadow-sm dashboard-filterable-card" ${filterAttrs}>
                    <div class="card-body text-center p-2 d-flex flex-column justify-content-center">
                        <div class="substatus-icon ${meta.color} mb-1"><i class="${meta.icon} fa-lg"></i></div>
                        <h4 class="substatus-count fw-bold mb-0">${count}</h4>
                        <p class="substatus-label text-muted small mb-0 mt-1">${meta.label}</p>
                    </div>
                </div>
            </div>`;
    }

    function substatusCardsLayoutClass(groupId) {
        const cap = DASHBOARD_SUBSTATUS_CAPACITY[groupId];
        const cols = cap ? cap.gridCols : 2;
        return `dashboard-substatus-cards--grid-cols-${cols}`;
    }

    function renderSubstatusRow(items, filterMode, groupId) {
        const keys = Object.keys(items || {}).sort(
            (a, b) => (items[b] || 0) - (items[a] || 0)
        );
        if (!keys.length) {
            return '<p class="text-muted small mb-0">Nenhum substatus neste grupo no período.</p>';
        }
        const layoutClass = substatusCardsLayoutClass(groupId);
        return `<div class="dashboard-substatus-cards ${layoutClass}">${keys
            .map((k) => buildSubstatusCardHtml(k, items[k], filterMode))
            .join('')}</div>`;
    }

    function renderStatusSubstatusGroups(agg) {
        const container = document.getElementById('status-substatus-groups-container');
        if (!container) return;

        const groupDataMap = {
            resumo: agg.resumo,
            migrados: agg.migrados,
            'em-atendimento': agg.emAtendimento,
            quebra: agg.quebra,
            parcial: agg.parcial,
        };

        const parts = [];
        DASHBOARD_STATUS_GROUPS.forEach((def) => {
            const data = groupDataMap[def.id];
            if (!data || data.total === 0) {
                return;
            }

            const headerFilterAttrs =
                def.filterMode && def.filterMode !== 'substatus'
                    ? `data-filter-mode="${def.filterMode}"${
                          def.filterValue ? ` data-filter-value="${def.filterValue}"` : ''
                      }`
                    : '';

            let bodyHtml = '';
            if (def.id === 'resumo') {
                bodyHtml =
                    '<p class="text-muted small mb-0">Use o total acima ou filtre pela tabela. Demais grupos detalham substatus por status.</p>';
            } else if (def.id === 'migrados') {
                bodyHtml = renderSubstatusRow(data.items, 'migrados', def.id);
            } else {
                bodyHtml = renderSubstatusRow(data.items, 'substatus', def.id);
            }

            const cap = DASHBOARD_SUBSTATUS_CAPACITY[def.id];
            const spanFull =
                def.id === 'resumo' || (cap && cap.spanFull)
                    ? ' dashboard-status-group--span-full'
                    : '';

            parts.push(`
                <section class="dashboard-status-group ${def.groupClass}${spanFull}">
                    <div class="dashboard-status-group-header">
                        <div>
                            <p class="dashboard-status-group-title mb-0">
                                <i class="${def.icon} ${def.iconColor} me-2"></i>${def.title}
                            </p>
                            <p class="dashboard-status-group-hint">${def.hint}</p>
                        </div>
                        <div class="text-end ${headerFilterAttrs ? 'dashboard-filterable-card' : ''}" style="${headerFilterAttrs ? 'cursor:pointer' : ''}" ${headerFilterAttrs}>
                            <span class="text-muted small d-block">Total</span>
                            <span class="dashboard-status-group-total">${data.total}</span>
                        </div>
                    </div>
                    ${bodyHtml}
                </section>
            `);
        });

        if (!parts.length) {
            container.innerHTML =
                '<p class="text-muted mb-0">Nenhum atendimento iniciado no período selecionado.</p>';
            return;
        }
        container.innerHTML = parts.join('');
    }

    function updateAgendadosKpis(kpis, scheduledData, filtroContratada) {
        const container = document.getElementById("agendados-kpi-container");
        if (!container) return;

        const notaEl = document.getElementById("agendados-kpi-nota");
        if (notaEl) {
            notaEl.textContent = filtroContratada
                ? "Visão da contratada selecionada: agendados usam a contratada planejada; ativos usam a contratada do atendimento."
                : "Contagem por data de agendamento no filtro. «Com atendimento» = unidade que já teve atividade registrada no período.";
        }

        const programadosTimeline = Object.values(scheduledData || {}).reduce(
            (a, b) => a + b,
            0
        );

        const aguardandoValor = kpis.aguardandoAtendimento;
        const aguardandoHint = filtroContratada
            ? "Agendadas da contratada sem atendimento iniciado"
            : "Agendadas sem atendimento iniciado";

        const cards = [
            {
                label: "Agendadas no período",
                value: kpis.totalAgendadas,
                hint: filtroContratada
                    ? "Com agenda e atividade da contratada"
                    : "Com data de agendamento no filtro",
                icon: "fas fa-calendar-day",
                color: "primary",
                filterMode: filtroContratada ? null : "agendadas-periodo",
            },
            {
                label: "Com atendimento",
                value: kpis.comAtendimento,
                hint: "Atividade registrada (não só agendamento)",
                icon: "fas fa-user-check",
                color: "success",
                filterMode: "tem-atendimento",
            },
            {
                label: "Aguardando atendimento",
                value: aguardandoValor,
                hint: aguardandoHint,
                icon: "fas fa-clock",
                color: "warning",
                filterMode: filtroContratada ? null : "somente-agendado",
            },
            {
                label: "Taxa de realização",
                value: `${kpis.taxaRealizacao}%`,
                hint: filtroContratada
                    ? "Com atendimento ÷ agendadas da contratada"
                    : "Com atendimento ÷ agendadas no período",
                icon: "fas fa-percentage",
                color: "secondary",
                filterMode: null,
            },
        ];

        if (
            !filtroContratada &&
            programadosTimeline > 0 &&
            programadosTimeline !== kpis.aguardandoAtendimento
        ) {
            cards.push({
                label: "Pico agendado (soma diária)",
                value: programadosTimeline,
                hint: "Soma das barras cinzas — total agendado por dia, não só pendentes",
                icon: "fas fa-chart-line",
                color: "info",
                filterMode: null,
            });
        }

        container.innerHTML = cards
            .map(
                (c) => `
            <div class="col-xl-3 col-lg-4 col-md-6">
                <div class="card h-100 border-0 shadow-sm dashboard-kpi-agendado ${
                    c.filterMode ? "dashboard-filterable-card" : ""
                }" ${c.filterMode ? `data-filter-mode="${c.filterMode}"` : ""} style="${
                    c.filterMode ? "cursor:pointer" : ""
                }">
                    <div class="card-body d-flex align-items-center justify-content-between p-3">
                        <div>
                            <h6 class="text-muted text-uppercase mb-1" style="font-size:0.72rem;">${c.label}</h6>
                            <small class="text-muted d-block" style="font-size:0.65rem;">${c.hint}</small>
                            <h3 class="fw-bold text-dark mb-0 mt-1">${c.value}</h3>
                        </div>
                        <div class="icon-shape bg-${c.color} bg-opacity-10 text-${c.color} rounded-circle p-3">
                            <i class="${c.icon} fa-lg"></i>
                        </div>
                    </div>
                </div>
            </div>`
            )
            .join("");
    }

    const PRODESP_ETAPAS_TEMPO_ESPERA_JS = [
        { key: "aguardando_cliente", field: "tempo_aguardando_cliente", label: "Aguardando Cliente" },
        { key: "aguardando_config_remota", field: "tempo_aguardando_config_remota", label: "Aguardando Configuração Remota" },
        { key: "aguardando_mpls", field: "tempo_aguardando_mpls", label: "Aguardando MPLS" },
        { key: "aguardando_caderno", field: "tempo_aguardando_caderno", label: "Aguardando Caderno de Teste" },
    ];

    const PRODESP_ETAPAS_TEMPO_PRODUTIVO_JS = [
        { key: "aguarda_gestao", field: "tempo_aguarda_gestao", label: "Aguarda Gestão", analista: "analista_atuante_atendimentos" },
        { key: "com_suporte", field: "tempo_com_suporte", label: "Com Suporte", analista: null },
        { key: "config_remota", field: "tempo_config_remota", label: "Configuração Remota", analista: "analista_configuracao_atendimentos" },
        { key: "config_mpls", field: "tempo_config_mpls", label: "Configuração MPLS", analista: "analista_mpls_atendimentos" },
        { key: "caderno_teste", field: "tempo_caderno_teste", label: "Caderno de Teste", analista: "analista_caderno_teste_atendimentos" },
    ];

    function prodespTempoValorParaSegundos(val) {
        if (val == null || val === "") return null;
        if (typeof val === "number") return Math.max(0, Math.floor(val));
        const s = String(val).trim();
        if (!s) return null;
        const parts = s.split(":");
        if (parts.length >= 3) {
            return (
                parseInt(parts[0], 10) * 3600 +
                parseInt(parts[1], 10) * 60 +
                parseInt(parts[2], 10)
            );
        }
        return null;
    }

    function prodespMediaSegundosLista(segundosList) {
        if (!segundosList.length) return "00:00:00";
        const avg = Math.floor(
            segundosList.reduce((a, b) => a + b, 0) / segundosList.length
        );
        return formatSecondsToHHMMSS(avg);
    }

    function prodespEtapaTempoStat(rows, field, analistaField) {
        const valores = [];
        let maxSeg = -1;
        let maxRow = null;
        rows.forEach((row) => {
            const seg = prodespTempoValorParaSegundos(row[field]);
            if (seg == null || seg <= 0) return;
            valores.push(seg);
            if (seg > maxSeg) {
                maxSeg = seg;
                maxRow = row;
            }
        });

        let maior_ofensor = null;
        if (maxRow) {
            const idIntragovRaw = maxRow.id_intragov;
            maior_ofensor = {
                id_atendimento: maxRow.id_atendimentos,
                id_vgr: (maxRow.id_vgr || "").trim(),
                acronimo: (maxRow.acronimo || "").trim(),
                id_intragov:
                    idIntragovRaw != null && String(idIntragovRaw).trim()
                        ? String(idIntragovRaw).trim()
                        : null,
                analista:
                    analistaField && (maxRow[analistaField] || "").trim()
                        ? String(maxRow[analistaField]).trim()
                        : null,
                tempo: formatSecondsToHHMMSS(maxSeg),
            };
        }

        return {
            tempo_medio: prodespMediaSegundosLista(valores),
            ocorrencias: valores.length,
            maior_ofensor,
        };
    }

    function prodespBuildTemposEtapaKpisFromLinhas(linhas, legenda, linhasOriginais) {
        const geralSecs = [];
        const atendSecs = [];
        const esperaDiffSecs = [];
        linhas.forEach((row) => {
            const g = prodespTempoValorParaSegundos(row.tempo_total_geral);
            const a = prodespTempoValorParaSegundos(row.tempo_total_atendimento);
            if (g != null) geralSecs.push(g);
            if (a != null) atendSecs.push(a);
            if (g != null && a != null) esperaDiffSecs.push(Math.max(0, g - a));
        });

        const mapEtapas = (defs) =>
            defs.map((d) => ({
                key: d.key,
                label: d.label,
                ...prodespEtapaTempoStat(linhas, d.field, d.analista || null),
            }));

        return {
            resumo_ciclo: {
                total_atendimentos: linhas.length,
                tempo_total_geral_medio: prodespMediaSegundosLista(geralSecs),
                tempo_total_atendimento_medio: prodespMediaSegundosLista(atendSecs),
                diferenca_espera_media: prodespMediaSegundosLista(esperaDiffSecs),
                legenda: legenda || {},
            },
            espera: mapEtapas(PRODESP_ETAPAS_TEMPO_ESPERA_JS),
            produtivo: mapEtapas(PRODESP_ETAPAS_TEMPO_PRODUTIVO_JS),
            linhas: linhasOriginais || linhas,
        };
    }

    function prodespTemposEtapaPayloadParaExibicao(rawPayload, contratada) {
        if (!rawPayload) return null;
        const legenda = rawPayload.resumo_ciclo?.legenda || {};
        const linhasBase = rawPayload.linhas || [];
        if (!contratada) {
            return rawPayload;
        }
        const linhasFiltradas = linhasBase.filter(
            (row) => prodespContratadaRowKey(row) === contratada
        );
        const built = prodespBuildTemposEtapaKpisFromLinhas(
            linhasFiltradas,
            legenda,
            linhasBase
        );
        built.filtro_contratada = contratada;
        return built;
    }

    function prodespRenderTemposEtapaComFiltro() {
        const payload = prodespTemposEtapaPayloadParaExibicao(
            rawTemposEtapaData,
            activeContratadaFilter
        );
        renderTemposEtapaKpis(payload);
    }

    function renderTemposEtapaKpis(payload) {
        const resumoEl = document.getElementById("tempos-etapa-resumo-container");
        const groupsEl = document.getElementById("tempos-etapa-groups-container");
        const emptyEl = document.getElementById("tempos-etapa-empty");
        if (!resumoEl || !groupsEl) return;

        const notaEl = document.getElementById("tempos-etapa-nota");
        if (notaEl) {
            notaEl.textContent = payload?.filtro_contratada
                ? `Tempos médios da contratada ${payload.filtro_contratada}. Geral = ciclo completo · Atendimento = etapas produtivas.`
                : "Atendimentos com data de realização no período. Geral = ciclo completo · Atendimento = etapas produtivas.";
        }

        if (!payload || !payload.resumo_ciclo) {
            resumoEl.innerHTML = "";
            groupsEl.innerHTML = "";
            if (emptyEl) {
                emptyEl.classList.remove("d-none");
                emptyEl.textContent = "Dados de tempo indisponíveis para o período.";
            }
            return;
        }

        const resumo = payload.resumo_ciclo;
        const leg = resumo.legenda || {};

        if (emptyEl) {
            if ((resumo.total_atendimentos ?? 0) === 0) {
                emptyEl.classList.remove("d-none");
                emptyEl.textContent = payload.filtro_contratada
                    ? "Nenhum atendimento com tempos calculados para esta contratada no período."
                    : "Nenhum atendimento com tempos calculados no período.";
            } else {
                emptyEl.classList.add("d-none");
            }
        }

        const resumoCards = [
            {
                cls: "dashboard-tempo-etapa-card--resumo-geral",
                title: "Tempo Total Geral Médio",
                hint: leg.geral || "Ciclo completo do atendimento.",
                value: resumo.tempo_total_geral_medio || "00:00:00",
            },
            {
                cls: "dashboard-tempo-etapa-card--resumo-atend",
                title: "Tempo Total Atendimento Médio",
                hint: leg.atendimento || "Apenas tempo produtivo (sem Aguardando).",
                value: resumo.tempo_total_atendimento_medio || "00:00:00",
            },
            {
                cls: "dashboard-tempo-etapa-card--resumo-espera",
                title: "Diferença Média (Espera)",
                hint: leg.espera || "Geral − Atendimento, por atendimento.",
                value: resumo.diferenca_espera_media || "00:00:00",
            },
            {
                cls: "",
                title: "Atendimentos no período",
                hint: "",
                value: String(resumo.total_atendimentos ?? 0),
            },
        ];

        resumoEl.innerHTML = resumoCards
            .map(
                (c) => `
            <div class="col-md-6 col-xl-3">
                <div class="dashboard-tempo-etapa-card dashboard-tempo-etapa-card--compact ${c.cls}">
                    <div class="dashboard-tempo-etapa-label">${c.title}</div>
                    <div class="dashboard-tempo-etapa-metric text-dark">${c.value}</div>
                    ${c.hint ? `<small class="text-muted d-block dashboard-tempo-etapa-hint">${c.hint}</small>` : ""}
                </div>
            </div>`
            )
            .join("");

        function renderOfensor(ofensor) {
            if (!ofensor || !ofensor.tempo) {
                return "";
            }
            const identParts = [
                ofensor.id_atendimento != null
                    ? `#${ofensor.id_atendimento}`
                    : "",
                ofensor.id_vgr ? `VGR ${ofensor.id_vgr}` : "",
                ofensor.id_intragov ? `INTRAGOV ${ofensor.id_intragov}` : "",
                ofensor.acronimo || ofensor.unidade || "",
                ofensor.analista || "",
            ].filter(Boolean);
            const identHtml = identParts.length
                ? ` · ${identParts.join(" · ")}`
                : "";
            return ` · Máx. <strong>${ofensor.tempo}</strong>${identHtml}`;
        }

        function renderEtapaCards(etapas, tipo) {
            const tipoCls =
                tipo === "espera"
                    ? "dashboard-tempo-etapa-card--espera"
                    : "dashboard-tempo-etapa-card--produtivo";
            return (etapas || [])
                .map(
                    (e) => `
                <div class="dashboard-tempo-etapa-card dashboard-tempo-etapa-card--compact ${tipoCls}">
                    <div class="dashboard-tempo-etapa-label">${e.label}</div>
                    <div class="dashboard-tempo-etapa-metric text-dark">${e.tempo_medio || "00:00:00"}</div>
                    <div class="dashboard-tempo-etapa-meta text-muted">Ocorr.: <strong>${e.ocorrencias ?? 0}</strong>${renderOfensor(e.maior_ofensor)}</div>
                </div>`
                )
                .join("");
        }

        const grupos = [
            {
                key: "espera",
                title: "Tempos de Espera",
                groupClass: "dashboard-group-tempos-espera",
                etapas: payload.espera,
            },
            {
                key: "produtivo",
                title: "Tempos Produtivos",
                groupClass: "dashboard-group-tempos-produtivo",
                etapas: payload.produtivo,
            },
        ];

        groupsEl.innerHTML = grupos
            .map(
                (g) => `
            <section class="dashboard-status-group ${g.groupClass} mb-2">
                <p class="dashboard-status-group-title mb-2">${g.title}</p>
                <div class="dashboard-tempos-etapa-grid">${renderEtapaCards(g.etapas, g.key)}</div>
            </section>`
            )
            .join("");

        if (emptyEl) {
            const semDados = (resumo.total_atendimentos || 0) === 0;
            emptyEl.classList.toggle("d-none", !semDados);
        }
    }

    function renderMotivosForaPadraoSummary(motivosData) {
        const container = document.getElementById('fora-padrao-summary-container');
        if (!container) return;

        container.innerHTML = '';
        if (!motivosData || motivosData.length === 0) return;

        const cards = motivosData.map(item => `
            <div class="col-md-4 col-lg-3">
                <div class="card border-0 shadow-sm h-100">
                    <div class="card-body">
                        <div class="text-muted small text-uppercase">${item.categoria || ''}</div>
                        <div class="fw-bold">${item.descricao || ''}</div>
                        <div class="text-primary fs-5">${item.total || 0}</div>
                    </div>
                </div>
            </div>
        `).join('');

        container.innerHTML = cards;
    }

    function renderMotivosView(container, motivos) {
        if (!container) return;
        container.innerHTML = "";

        if (!motivos || motivos.length === 0) {
            container.innerHTML = '<div class="text-muted small">Nenhum motivo informado.</div>';
            return;
        }

        const motivosPorCategoria = motivos.reduce((acc, item) => {
            const categoria = (item.categoria || "Sem categoria").trim();
            if (!acc[categoria]) acc[categoria] = [];
            acc[categoria].push(item);
            return acc;
        }, {});

        const accordionId = `${container.id}-accordion`;
        const accordion = document.createElement("div");
        accordion.className = "accordion accordion-flush motivos-accordion";
        accordion.id = accordionId;

        Object.keys(motivosPorCategoria).sort().forEach((categoria, index) => {
            const categoryItems = motivosPorCategoria[categoria];
            const item = document.createElement("div");
            item.className = "accordion-item border rounded mb-2 shadow-sm";
            const headerId = `${accordionId}-heading-${index}`;
            const collapseId = `${accordionId}-collapse-${index}`;

            item.innerHTML = `
                <h2 class="accordion-header" id="${headerId}">
                    <button class="accordion-button ${index === 0 ? "" : "collapsed"} py-2" type="button" data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="${index === 0 ? "true" : "false"}" aria-controls="${collapseId}">
                        <span class="fw-semibold">${prodespGestaoEsc(categoria)}</span>
                        <span class="badge text-bg-primary ms-2">${categoryItems.length}</span>
                    </button>
                </h2>
                <div id="${collapseId}" class="accordion-collapse collapse ${index === 0 ? "show" : ""}" aria-labelledby="${headerId}" data-bs-parent="#${accordionId}">
                    <div class="accordion-body py-2">
                        <div class="d-flex flex-wrap gap-2"></div>
                    </div>
                </div>
            `;

            const chips = item.querySelector(".d-flex.flex-wrap");
            categoryItems.forEach(motivo => {
                const badge = document.createElement("span");
                badge.className = "badge text-bg-light border text-dark px-3 py-2 rounded-pill";
                badge.textContent = motivo.descricao || "";
                chips.appendChild(badge);
            });

            accordion.appendChild(item);
        });

        container.appendChild(accordion);
    }

    function prodespSubstatusChartColor(label) {
        const statusColors = {
            "Em Atendimento": "#0d6efd",
            "Quebra": "#dc3545",
            "Concluído Parcial": "#0dcaf0",
            "Concluído": "#198754",
            "Sem Substatus": "#adb5bd",
            "Em Configuração Remota": "#0d6efd",
            "Em Configuração do MPLS": "#6610f2",
            "Em Caderno de Teste": "#0dcaf0",
            "Pendente": "#ffc107",
            "Configuração": "#0d6efd",
            "Triagem": "#6c757d",
            "Aguardando Cliente": "#fd7e14",
            "Caderno de Teste": "#0dcaf0",
        };
        const defaultColor = "#6c757d";
        if (statusColors[label]) {
            return statusColors[label];
        }
        const lowerLabel = (label || "").toLowerCase();
        if (lowerLabel.includes("quebra")) {
            return statusColors["Quebra"];
        }
        if (lowerLabel.includes("aguardando cliente")) {
            return statusColors["Aguardando Cliente"];
        }
        if (lowerLabel.includes("pendente") || lowerLabel.includes("pendencia")) {
            return statusColors["Pendente"];
        }
        if (lowerLabel.includes("configura")) {
            return statusColors["Configuração"];
        }
        if (lowerLabel.includes("atendimento")) {
            return statusColors["Em Atendimento"];
        }
        if (lowerLabel.includes("conclu")) {
            return statusColors["Concluído"];
        }
        return defaultColor;
    }

    /**
     * Gráficos de barras horizontais — substatus por status (legível com muitas categorias).
     */
    function updateSubstatusChartsByStatus(statusGroupsAgg) {
        SUBSTATUS_CHART_GROUPS.forEach((group) => {
            const agg = statusGroupsAgg[group.aggKey] || { total: 0, items: {} };
            const entries = Object.entries(agg.items || {})
                .filter(([, count]) => count > 0)
                .sort((a, b) => b[1] - a[1]);
            const substatusKeys = entries.map(([name]) => name);
            const displayLabels = substatusKeys.map((key) => prodespSubstatusMeta(key).label);
            const values = entries.map(([, count]) => count);

            const panel = document.querySelector(
                `[data-chart-group="${group.key}"]`
            );
            const canvas = document.getElementById(group.canvasId);
            const wrap = panel?.querySelector(".dashboard-substatus-chart-canvas-wrap");
            const emptyEl = panel?.querySelector(".dashboard-substatus-chart-empty");
            const totalBadge = panel?.querySelector(".substatus-chart-total");

            if (totalBadge) {
                totalBadge.textContent = String(agg.total || 0);
            }
            if (!canvas || !panel) {
                return;
            }

            if (entries.length === 0) {
                if (substatusByStatusChartInstances[group.key]) {
                    substatusByStatusChartInstances[group.key].destroy();
                    delete substatusByStatusChartInstances[group.key];
                }
                if (wrap) {
                    wrap.classList.add("d-none");
                }
                if (emptyEl) {
                    emptyEl.classList.remove("d-none");
                }
                return;
            }

            if (wrap) {
                wrap.classList.remove("d-none");
                const barHeight = 26;
                const h = Math.max(72, Math.min(300, substatusKeys.length * barHeight + 20));
                wrap.style.height = `${h}px`;
            }
            if (emptyEl) {
                emptyEl.classList.add("d-none");
            }

            const bgColors = substatusKeys.map((key) => prodespSubstatusChartColor(key));
            const groupTotal = agg.total || values.reduce((a, b) => a + b, 0);

            const chartOptions = {
                type: "bar",
                data: {
                    labels: displayLabels,
                    datasets: [
                        {
                            data: values,
                            backgroundColor: bgColors,
                            borderWidth: 0,
                            borderRadius: 4,
                            barThickness: 20,
                            maxBarThickness: 24,
                        },
                    ],
                },
                plugins: [ChartDataLabels],
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    layout: { padding: { right: 28 } },
                    plugins: {
                        legend: { display: false },
                        datalabels: {
                            anchor: "end",
                            align: "end",
                            offset: 4,
                            color: "#495057",
                            font: { size: 10, weight: "bold" },
                            formatter: (value) => (value > 0 ? value : ""),
                        },
                        tooltip: {
                            callbacks: {
                                label(context) {
                                    const fullName =
                                        context.chart.$prodespSubstatusKeys?.[
                                            context.dataIndex
                                        ] ?? context.label;
                                    const pct =
                                        groupTotal > 0
                                            ? ((context.raw / groupTotal) * 100).toFixed(1)
                                            : "0";
                                    return `${fullName}: ${context.raw} (${pct}%)`;
                                },
                            },
                        },
                    },
                    scales: {
                        x: {
                            beginAtZero: true,
                            ticks: { precision: 0, font: { size: 10 } },
                            grid: { borderDash: [2, 4] },
                        },
                        y: {
                            ticks: { font: { size: 10 }, autoSkip: false },
                            grid: { display: false },
                        },
                    },
                    onHover(event, elements) {
                        event.native.target.style.cursor = elements[0]
                            ? "pointer"
                            : "default";
                    },
                    onClick(event, elements) {
                        if (!elements.length) {
                            return;
                        }
                        const chart = substatusByStatusChartInstances[group.key];
                        if (!chart) {
                            return;
                        }
                        const filterKey =
                            chart.$prodespSubstatusKeys?.[elements[0].index] ??
                            chart.data.labels[elements[0].index];
                        prodespAplicarFiltroDashboard(
                            $('<div>').attr({
                                "data-filter-mode": "substatus",
                                "data-filter-value": filterKey,
                            })
                        );
                    },
                },
            };

            if (substatusByStatusChartInstances[group.key]) {
                const chart = substatusByStatusChartInstances[group.key];
                chart.data.labels = displayLabels;
                chart.data.datasets[0].data = values;
                chart.data.datasets[0].backgroundColor = bgColors;
                chart.$prodespSubstatusKeys = substatusKeys;
                chart.update();
            } else {
                const chart = new Chart(canvas, chartOptions);
                chart.$prodespSubstatusKeys = substatusKeys;
                substatusByStatusChartInstances[group.key] = chart;
            }
        });
    }

    /**
     * Renderiza/Atualiza os gráficos com Chart.js
     * @param {Object} statusGroupsAgg
     * @param {{scheduled: Object, realized: Object, foraEscopo: Object}} timelineSeries
     * @param {Object} contratadaData
     */
    function updateCharts(statusGroupsAgg, timelineSeries, contratadaData) {
        updateSubstatusChartsByStatus(statusGroupsAgg || {});

        const series = timelineSeries || {};
        const dateData = series.realized || {};
        const scheduledData = series.scheduled || {};
        const foraData = series.foraEscopo || {};

        // --- Gráfico de Evolução Diária (Bar - Comparativo) ---
        const performedDates = Object.keys(dateData);
        const scheduledDates = Object.keys(scheduledData);
        const foraDates = Object.keys(foraData);
        const sortedDates = [
            ...new Set([...performedDates, ...scheduledDates, ...foraDates]),
        ].sort();

        const performedValues = sortedDates.map((d) => dateData[d] || 0);
        const scheduledValues = sortedDates.map((d) => scheduledData[d] || 0);
        const foraValues = sortedDates.map((d) => foraData[d] || 0);

        // --- CONFIGURAÇÃO DE METAS MENSAIS ---
        // Defina aqui a meta para cada mês específico (formato 'YYYY-MM': valor)
        const METAS_MENSAIS = {
            '2025-01': 45,
            '2025-02': 30,
            '2025-03': 40, 
            '2025-04': 45,
        };
        const META_PADRAO = 45;

        const metaValues = sortedDates.map(d => METAS_MENSAIS[d.substring(0, 7)] || META_PADRAO);
        const maxMetaGrafico = Math.max(...metaValues, META_PADRAO, 1);

        // Formata data para DD/MM
        const dateLabels = sortedDates.map(d => {
            const parts = d.split('-');
            return parts.length === 3 ? `${parts[2]}/${parts[1]}` : d;
        });

        const ctxTimeline = document.getElementById('chartTimeline');
        if (ctxTimeline) {
            if (
                timelineChartInstance &&
                (!timelineChartInstance.data.datasets ||
                    timelineChartInstance.data.datasets.length < 4)
            ) {
                timelineChartInstance.destroy();
                timelineChartInstance = null;
            }
            if (timelineChartInstance) {
                timelineChartInstance.data.labels = dateLabels;
                timelineChartInstance.data.datasets[0].data = performedValues;
                timelineChartInstance.data.datasets[1].data = scheduledValues;
                timelineChartInstance.data.datasets[2].data = foraValues;
                timelineChartInstance.data.datasets[3].data = metaValues;
                if (timelineChartInstance.options?.scales?.y) {
                    timelineChartInstance.options.scales.y.suggestedMax = maxMetaGrafico + 5;
                }
                timelineChartInstance.update();
            } else {
                timelineChartInstance = new Chart(ctxTimeline, {
                    type: 'bar',
                    data: {
                        labels: dateLabels,
                        datasets: [
                            {
                                label: 'Realizado',
                                data: performedValues,
                                backgroundColor: '#0d6efd',
                                borderRadius: 4,
                                barThickness: 'flex',
                                maxBarThickness: 40,
                                order: 3
                            },
                            {
                                label: 'Agendado',
                                data: scheduledValues,
                                backgroundColor: '#6c757d',
                                borderRadius: 4,
                                barThickness: 'flex',
                                maxBarThickness: 40,
                                order: 2
                            },
                            {
                                label: 'Fora Escopo',
                                data: foraValues,
                                backgroundColor: '#fd7e14',
                                borderRadius: 4,
                                barThickness: 'flex',
                                maxBarThickness: 40,
                                order: 1
                            },
                            {
                                type: 'line',
                                label: 'Meta',
                                data: metaValues,
                                borderColor: '#dc3545',
                                borderWidth: 2,
                                fill: false,
                                pointRadius: 0,
                                tension: 0,
                                order: 0
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: true, position: 'top' }
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                grid: { borderDash: [2, 4] },
                                ticks: { precision: 0 },
                                suggestedMax: maxMetaGrafico + 5
                            },
                            x: { grid: { display: false } }
                        }
                    }
                });
            }
        }

        // --- Gráfico de Contratada (Doughnut) ---
        const contratadaLabels = Object.keys(contratadaData);
        const contratadaValues = Object.values(contratadaData);
        // Paleta de cores para contratadas
        const palette = [
            "#0d6efd", "#6610f2", "#6f42c1", "#d63384", "#dc3545",
            "#fd7e14", "#ffc107", "#198754", "#20c997", "#0dcaf0"
        ];
        const contratadaBgColors = contratadaLabels.map((_, i) => palette[i % palette.length]);

        const contratadaOffsets = contratadaLabels.map(label => label === activeContratadaFilter ? 20 : 0);

        const ctxContratada = document.getElementById('chartContratada');
        if (ctxContratada) {
            const helper = document.getElementById('contratada-chart-helper');
            if (helper) helper.style.display = 'block';

            if (contratadaChartInstance) {
                contratadaChartInstance.data.labels = contratadaLabels;
                contratadaChartInstance.data.datasets[0].data = contratadaValues;
                contratadaChartInstance.data.datasets[0].backgroundColor = contratadaBgColors;
                contratadaChartInstance.data.datasets[0].offset = contratadaOffsets;
                contratadaChartInstance.update();
            } else {
                contratadaChartInstance = new Chart(ctxContratada, {
                    type: 'doughnut',
                    data: {
                        labels: contratadaLabels,
                        datasets: [{
                            data: contratadaValues,
                            backgroundColor: contratadaBgColors,
                            borderWidth: 0,
                            hoverOffset: 4,
                            offset: contratadaOffsets
                        }]
                    },
                    plugins: [ChartDataLabels],
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { position: 'right', labels: { usePointStyle: true, padding: 20 } },
                            title: { display: false },
                            datalabels: {
                                color: '#fff',
                                font: { weight: 'bold' },
                                formatter: (value) => value > 0 ? value : ''
                            }
                        },
                        onClick: (evt, elements) => {
                            if (!elements.length) {
                                activeContratadaFilter = null;
                                recalculateAndUpdateCards();
                                return;
                            }
                            const idx = elements[0].index;
                            const label = contratadaChartInstance.data.labels[idx];
                            if (label) {
                                if (activeContratadaFilter === label) {
                                    activeContratadaFilter = null;
                                } else {
                                    activeContratadaFilter = label;
                                }
                                recalculateAndUpdateCards();
                            }
                        }
                    }
                });
            }
        }
    }

    // =============================================================
    // CONFIGURAÇÃO DA DATATABLE
    // =============================================================

    function prodespDtSyncScrollColumns() {
        if (!dataTableInstance) return;
        try {
            dataTableInstance.columns.adjust();
        } catch (e) {
            /* ignore */
        }
        if (window.ProdespDtFontSize && typeof window.ProdespDtFontSize.scheduleAdjustColumns === "function") {
            window.ProdespDtFontSize.scheduleAdjustColumns();
        }
    }

    /**
     * Inicializa a DataTable com todas as configurações necessárias
     */
    function initializeDataTable() {
        prodespRegistrarFiltrosCustomizadosDashboardDataTable();

        // Se a instância já existe, não faz nada para evitar reinicialização.
        if ($.fn.DataTable.isDataTable("#tabela-gestao-atendimentos")) {
            // Se precisar recarregar os dados, use o método ajax.reload()
            if (dataTableInstance) {
                dataTableInstance.ajax.reload(null, false); // false = não reseta a paginação
            }
            return;
        }

        // Função de ordenação para datas no formato dd/mm/yyyy
        $.fn.dataTable.ext.type.order["date-br-pre"] = function (d) {
            if (!d) return 0;
            var parts = d.split("/");
            if (parts.length < 3) return 0;
            return parseInt(parts[2] + parts[1] + parts[0], 10);
        };

        if ($.fn.DataTable.isDataTable("#tabela-gestao-atendimentos")) {
            return;
        }

        $.fn.dataTable.ext.type.order["date-br-pre"] = function (d) {
            if (!d) return 0;
            var parts = d.split("/");
            if (parts.length < 3) return 0;
            return parseInt(parts[2] + parts[1] + parts[0], 10);
        };

        dataTableInstance = $("#tabela-gestao-atendimentos").DataTable({
            // ✅ 1. Mover a chamada AJAX para dentro da configuração da DataTable
            ajax: {
                url: "/prodesp/api/dashboard_data",
                type: "GET",
                // Envia as datas do filtro como parte da requisição
                data: function(d) {
                    latestDashboardLoadSeq += 1;
                    const meta = {
                        seq: latestDashboardLoadSeq,
                        start: dashboardDatesAtLastApply.start,
                        end: dashboardDatesAtLastApply.end,
                    };
                    dashboardLoadMetaBySeq.set(meta.seq, meta);
                    d.start_date = meta.start;
                    d.end_date = meta.end;
                },
                beforeSend: function (xhr) {
                    const meta = dashboardLoadMetaBySeq.get(latestDashboardLoadSeq);
                    if (meta) {
                        xhr.__loadSeq = meta.seq;
                        xhr.__loadStart = meta.start;
                        xhr.__loadEnd = meta.end;
                    }
                    if (
                        dashboardAjaxXhr &&
                        dashboardAjaxXhr !== xhr &&
                        dashboardAjaxXhr.readyState !== 4
                    ) {
                        const abortedSeq = dashboardAjaxXhr.__loadSeq;
                        if (abortedSeq != null) {
                            dashboardLoadMetaBySeq.delete(abortedSeq);
                        }
                        try {
                            dashboardAjaxXhr.abort();
                        } catch (_e) {
                            /* ignore */
                        }
                    }
                    dashboardAjaxXhr = xhr;
                },
                // dataSrc agora é uma função para processar a resposta
                dataSrc: function(json, arg2, arg3) {
                    const settings = prodespResolveDashboardAjaxSettings(arg2, arg3);
                    const xhr = settings && (settings.jqXHR || settings.oXHR);
                    const meta = prodespResolveDashboardLoadMeta(xhr);
                    if (!prodespDashboardLoadAccepted(meta)) {
                        if (meta && meta.seq != null) {
                            dashboardLoadMetaBySeq.delete(meta.seq);
                        }
                        return [];
                    }

                    dashboardAppliedLoadSeq = meta.seq;
                    dashboardLoadMetaBySeq.delete(meta.seq);
                    rawAtendimentosData = json.atendimentos || [];
                    rawScheduledData = json.scheduled || {};
                    rawMotivosForaPadraoData = json.motivos_fora_padrao || [];
                    rawTemposEtapaData = json.tempos_etapa || null;
                    prodespRenderTemposEtapaComFiltro();

                    if (json.server_time) {
                        const serverTime = new Date(json.server_time);
                        const clientTime = new Date();
                        timeOffset = clientTime - serverTime;
                    }
                    if (json.data_revision != null && window.prodespGestaoDtSync) {
                        window.prodespGestaoDtSync.setRevision(json.data_revision);
                    }

                    if (window.ProdespTempoAtendimento && typeof window.ProdespTempoAtendimento.atualizarSortEmLinhas === "function") {
                        window.ProdespTempoAtendimento.atualizarSortEmLinhas(rawAtendimentosData, timeOffset);
                    }

                    return rawAtendimentosData;
                },
                error: function (xhr) {
                    if (xhr && (xhr.statusText === "abort" || xhr.status === 0)) {
                        return;
                    }
                    prodespOnDashboardReloadComplete(false);
                },
            },
            // ❌ Remove 'data: []', pois agora os dados vêm do AJAX
            language: prodespGestaoDtLanguage(),
            processing: true, 
            columns: [{ 
                data: "id_vgr",
                defaultContent: ""
            }, {
                data: null,
                defaultContent: "",
                render: (data, type, row) => {
                    const label = prodespContratadaRowKey(row) || "Não Informado";
                    if (type !== "display") return label;
                    return prodespContratadaCellHtml(label);
                },
            }, { 
                data: "data_agendamento",
                render: (data) => {
                    if (!data) return "";
                    const datePart = data.split(/[T ]/)[0];
                    return new Date(datePart + "T00:00:00").toLocaleDateString("pt-BR");
                },
                defaultContent: "",
            }, { 
                data: "hora_agendamento",
                defaultContent: "",
            }, { 
                data: "data_atendimentos",
                render: (data) => {
                    if (!data) return "";
                    const datePart = data.split(/[T ]/)[0];
                    return new Date(datePart + "T00:00:00").toLocaleDateString("pt-BR");
                },
                defaultContent: "",
            }, {
                data: "acronimo",
                defaultContent: "",
            }, {
                data: "endereco",
                defaultContent: ""
            }, {
                data: "municipio",
                defaultContent: ""
            }, {
                data: "status_atendimentos",
                render: (data) => {
                    return data || "Agendado";
                },
                defaultContent: "Agendado"
            }, { 
                data: "substatus_atendimentos",
                defaultContent: "—"
            }, { 
                data: "analista_atuante_atendimentos",
                defaultContent: "",
            }, { 
                data: "analista_configuracao_atendimentos",
                defaultContent: "",
            }, { 
                data: "analista_mpls_atendimentos",
                defaultContent: "",
            }, { 
                data: "analista_caderno_teste_atendimentos",
                defaultContent: "",
            }, {
                name: "prodesp_tempo_etapa",
                data: "_sort_etapa",
                orderable: true,
                searchable: false,
                defaultContent: 9e15,
                render: (data, type, row) => {
                    if (type !== "display") return data;
                    const T = window.ProdespTempoAtendimento;
                    return T ? T.renderSpanTempo("etapa", row, timeOffset) : "";
                },
            }, {
                name: "prodesp_tempo_vida",
                data: "_sort_vida",
                orderable: true,
                searchable: false,
                defaultContent: 9e15,
                render: (data, type, row) => {
                    if (type !== "display") return data;
                    const T = window.ProdespTempoAtendimento;
                    return T ? T.renderSpanTempo("vida", row, timeOffset) : "";
                },
            }, {
                data: "id_atendimento",
                render: (data, type, row) => {
                    const parts = [];
                    if (data) {
                        parts.push(
                            `<button type="button" class="btn-icon open-details-modal" data-id-atendimento="${data}" title="Ver Detalhes Atendimento"><i class="fa fa-eye"></i></button>`
                        );
                        if (window.PRODESP_GESTAO_OPERAR_ATENDIMENTOS && row.pode_editar) {
                            parts.push(
                                `<button type="button" class="btn-icon open-edit-gestao-modal" data-id-atendimento="${data}" title="Editar atendimento"><i class="fas fa-edit"></i></button>`
                            );
                        } else if (window.PRODESP_GESTAO_OPERAR_ATENDIMENTOS && row.pode_editar === false) {
                            const msgTooltip =
                                (typeof prodespPodeEditarAtendimento === "function"
                                    ? prodespPodeEditarAtendimento(row).msg
                                    : "") ||
                                (row.edicao_msg || "");
                            if (msgTooltip) {
                                parts.push(
                                    `<button type="button" class="btn-icon text-muted" disabled title="${prodespGestaoEsc(msgTooltip)}"><i class="fas fa-edit"></i></button>`
                                );
                            }
                        }
                    } else if (window.PRODESP_GESTAO_OPERAR_ATENDIMENTOS && row.id_vgr) {
                        parts.push(
                            `<button type="button" class="btn-icon open-create-gestao-modal" data-id-vgr="${prodespGestaoEsc(row.id_vgr)}" title="Iniciar atendimento para unidade agendada"><i class="fas fa-plus-circle"></i></button>`
                        );
                        parts.push(
                            `<button type="button" class="btn-icon" onclick="viewUnitOnly('${prodespGestaoEsc(row.id_vgr)}')" title="Visualizar Dados da Unidade"><i class="fas fa-eye"></i></button>`
                        );
                    } else if (row.id_vgr) {
                        parts.push(
                            `<button type="button" class="btn-icon" onclick="viewUnitOnly('${prodespGestaoEsc(row.id_vgr)}')" title="Visualizar Dados da Unidade"><i class="fas fa-eye"></i></button>`
                        );
                    }
                    if (prodespGestaoIsAdminUser()) {
                        if (data) {
                            parts.push(
                                `<button type="button" class="btn-icon text-danger prodesp-admin-excluir-atendimento" data-id-atendimento="${data}" title="Excluir atendimento (admin)"><i class="fas fa-trash-alt"></i></button>`
                            );
                        } else if (row.id_vgr) {
                            parts.push(
                                `<button type="button" class="btn-icon text-danger prodesp-admin-remover-agendamento" data-id-vgr="${prodespGestaoEsc(row.id_vgr)}" title="Remover agendamento (admin)"><i class="fas fa-calendar-times"></i></button>`
                            );
                        }
                    }
                    return `<span class="prodesp-dt-acoes-inner">${parts.join("")}</span>`;
                },
                defaultContent: "",
                orderable: false,
            },
            {
                data: "_sort_lista",
                visible: false,
                searchable: false,
                orderable: true,
                defaultContent: 2e15,
            }],
            autoWidth: false,
            scrollX: true,
            ...(window.ProdespDtPageLength
                ? window.ProdespDtPageLength.dtOptions()
                : {
                      pageLength: 10,
                      lengthMenu: [
                          [5, 10, 25, 50, 100, 150, 200, -1],
                          [5, 10, 25, 50, 100, 150, 200, "Todos"],
                      ],
                  }),
            columnDefs: [
                { targets: 0, width: "92px", className: "prodesp-dt-compact col-id-vgr prodesp-dt-center" },
                { targets: 1, width: "100px", className: "prodesp-dt-wrap prodesp-dt-contratada prodesp-dt-left" },
                { targets: 2, width: "88px", className: "prodesp-dt-wrap prodesp-dt-center" },
                { targets: 3, width: "88px", className: "prodesp-dt-wrap prodesp-dt-center" },
                { targets: 4, width: "88px", className: "prodesp-dt-wrap prodesp-dt-center" },
                { targets: 5, width: "112px", className: "prodesp-dt-wrap prodesp-dt-left" },
                { targets: 6, width: "160px", className: "prodesp-dt-wrap prodesp-dt-left" },
                { targets: 7, width: "120px", className: "prodesp-dt-wrap prodesp-dt-left" },
                { targets: 8, width: "92px", className: "prodesp-dt-wrap prodesp-dt-center" },
                { targets: 9, width: "108px", className: "prodesp-dt-wrap prodesp-dt-left" },
                { targets: [10, 11, 12, 13], width: "88px", className: "prodesp-dt-wrap prodesp-dt-analista prodesp-dt-left" },
                {
                    targets: 14,
                    width: "92px",
                    type: "prodesp-tempo",
                    orderDataType: "prodesp-tempo",
                    searchable: false,
                    orderable: true,
                    className: "prodesp-dt-tempo-etapa prodesp-dt-center",
                    columnControl: prodespGestaoDtCcOrderOnly(),
                },
                {
                    targets: 15,
                    width: "92px",
                    type: "prodesp-tempo",
                    orderDataType: "prodesp-tempo",
                    searchable: false,
                    orderable: true,
                    className: "prodesp-dt-tempo-vida prodesp-dt-center",
                    columnControl: prodespGestaoDtCcOrderOnly(),
                },
                {
                    targets: 16,
                    width: "104px",
                    searchable: false,
                    orderable: false,
                    className: "prodesp-dt-compact prodesp-dt-acoes prodesp-dt-center",
                },
                {
                    targets: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13],
                    columnControl: prodespGestaoDtCcSearchList(),
                },
            ],
            order: [[17, "asc"]],
            ordering: prodespGestaoDtOrderingSilent(),
            stateSave: false,
            // ✅ 2. Usar o initComplete para executar código após o carregamento
            initComplete: function(settings, json) {
                // 'json' aqui contém a resposta completa do AJAX
                const api = this.api();

                if (window.ProdespDtPageLength && typeof window.ProdespDtPageLength.bindSave === "function") {
                    window.ProdespDtPageLength.bindSave(api);
                }

                // Agora é seguro inicializar os filtros, pois a tabela tem dados.
                if (api.columnControl) {
                    api.columnControl.init();
                }
                if (window.ProdespDtColumns && typeof window.ProdespDtColumns.initTable === "function") {
                    window.ProdespDtColumns.initTable(api, "tabela-gestao-atendimentos");
                }
                if (window.ProdespDtFontSize && typeof window.ProdespDtFontSize.refresh === "function") {
                    window.ProdespDtFontSize.refresh();
                }
                prodespDtSyncScrollColumns();
                setTimeout(prodespDtSyncScrollColumns, 150);

                // E também é seguro calcular as estatísticas.
                prodespOnDashboardReloadComplete(false);
            }
        });

        dataTableInstance.on("draw", function () {
            if (
                window.ProdespDtFontSize &&
                typeof window.ProdespDtFontSize.reapplySavedToTable === "function"
            ) {
                window.ProdespDtFontSize.reapplySavedToTable("tabela-gestao-atendimentos");
            }
            prodespDtSyncScrollColumns();
            atualizarTempoAtendimento();
        });

        dataTableInstance.on("preDraw.dt", function () {
            const T = window.ProdespTempoAtendimento;
            if (!T || typeof T.atualizarSortEmLinha !== "function") return;
            const orders = dataTableInstance.order();
            const tempoOrdenado = orders.some((o) => o[0] === 12 || o[0] === 13);
            if (!tempoOrdenado) return;
            dataTableInstance.rows().every(function () {
                T.atualizarSortEmLinha(this.data(), timeOffset);
            });
        });
    }



    // ==============================================================================
    // FUNÇÕES DE CARREGAMENTO DE DADOS
    // ==============================================================================

    function prodespMarcarDtAtualizado() {
        const el = document.getElementById("prodesp-dt-last-refresh-text");
        if (!el) return;
        const now = new Date();
        el.textContent =
            "Atualizado às " +
            now.toLocaleTimeString("pt-BR", {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
            });
    }

    function prodespAfterDashboardDataLoaded(loadSeq) {
        if (dashboardAppliedLoadSeq <= 0) {
            return;
        }
        if (loadSeq != null && loadSeq !== dashboardAppliedLoadSeq) {
            return;
        }
        if (dashboardAppliedLoadSeq !== latestDashboardLoadSeq) {
            return;
        }
        if (
            dashboardDatesAtLastApply.start !== ($("#startDate").val() || "").trim() ||
            dashboardDatesAtLastApply.end !== ($("#endDate").val() || "").trim()
        ) {
            return;
        }
        prodespClearDashboardLoadingWatchdog();
        prodespRenderTemposEtapaComFiltro();
        renderMotivosForaPadraoSummary(rawMotivosForaPadraoData);
        const startDateObj = new Date($("#startDate").val() + "T00:00:00");
        const endDateObj = new Date($("#endDate").val() + "T23:59:59");
        updateStats(rawAtendimentosData, startDateObj, endDateObj, rawScheduledData);
        prodespSetDashboardKpisLoading(false);
        prodespDtSyncScrollColumns();
        setTimeout(prodespDtSyncScrollColumns, 150);
    }

    function refreshDashboardData() {
        prodespSetDashboardKpisLoading(true);
        prodespArmDashboardLoadingWatchdog();
        if (window.prodespGestaoDtSync) {
            window.prodespGestaoDtSync.forceRefresh();
            return;
        }
        if (dataTableInstance) {
            dataTableInstance.ajax.reload(function () {
                prodespOnDashboardReloadComplete(false);
            }, false);
        }
    }

    // =================================================================
    // FUNÇÕES DE ATUALIZAÇÃO EM TEMPO REAL - TEMPO ATENDIMENTO
    // =================================================================

    /**
     * Atualiza os cronômetros de tempo de atendimento
     */
    function atualizarTempoAtendimento() {
        const T = window.ProdespTempoAtendimento;
        if (T && typeof T.atualizarTempos === "function") {
            T.atualizarTempos(".tempo-etapa, .tempo-vida", { timeOffset });
            return;
        }
        document.querySelectorAll(".tempo-etapa, .tempo-vida").forEach((cell) => {
            const inicioISO = cell.dataset.inicio;
            const tempoFinalizado = cell.dataset.finalizado;
            const segundosFinalizados = parseInt(cell.dataset.segundos);
            const status = (cell.dataset.status || "").trim();
            const modoDuracao = (cell.dataset.modoDuracao || "").trim();
            const statusLower = status.toLowerCase();
            
            const finalStatuses = [
                "concluído",
                "quebra",
                "concluído parcial",
                "concluido",
                "concluido parcial"
            ];

            // Helper for color class (Azul < 15min, Amarelo < 30min, Vermelho >= 30min)
            const getBadgeClass = (segundos) => {
                const minutos = segundos / 60;
                if (minutos >= 30) return "bg-danger";
                if (minutos >= 15) return "bg-warning text-dark";
                return "bg-info text-dark"; 
            };

            // 1. Atendimento finalizado (view/log) — não atualiza em tempo real
            const isFinalizado =
                modoDuracao === "finalizado" || finalStatuses.includes(statusLower);
            if (
                isFinalizado &&
                tempoFinalizado &&
                tempoFinalizado !== "---" &&
                !tempoFinalizado.startsWith("N/A")
            ) {
                let badgeClass = "bg-secondary";
                let displayText = tempoFinalizado;

                if (!displayText || displayText === "---") {
                     displayText = status; 
                } else {
                    if (!isNaN(segundosFinalizados)) {
                        badgeClass = getBadgeClass(segundosFinalizados);
                    }
                }
                
                cell.innerHTML = `<span class="badge ${badgeClass}" title="Atendimento finalizado">${prodespGestaoEsc(displayText)}</span>`;
                return;
            }
            if (isFinalizado) {
                cell.innerHTML = `<span class="badge bg-secondary" title="Atendimento finalizado">${prodespGestaoEsc(status || tempoFinalizado || "—")}</span>`;
                return;
            }

            // 2. Pendente (sem referência de tempo)
            if (!inicioISO || isNaN(new Date(inicioISO))) {
                cell.innerHTML = '<span class="badge bg-dark">Pendente</span>';
                return;
            }

            const dataInicio = new Date(inicioISO);
            const now = new Date();
            const adjustedNow = new Date(now.getTime() - timeOffset);

            // 3. Agendado: atraso desde data + hora agendadas (atualiza a cada 1s)
            if (modoDuracao === "atraso_agendado" || statusLower === "agendado") {
                if (adjustedNow < dataInicio) {
                    cell.innerHTML =
                        '<span class="badge bg-secondary" title="Ainda não passou do horário agendado">No prazo</span>';
                    return;
                }
                const atrasoSeg = Math.floor((adjustedNow - dataInicio) / 1000);
                const tempoAtraso = formatSecondsToHHMMSS(atrasoSeg);
                const badgeAtraso = getBadgeClass(atrasoSeg);
                cell.innerHTML = `<span class="badge ${badgeAtraso}" title="Atraso desde o horário agendado (${prodespGestaoEsc(dataInicio.toLocaleString("pt-BR"))})">${prodespGestaoEsc(tempoAtraso)}</span>`;
                return;
            }

            // 4. Em andamento (início do atendimento ou último substatus)
            const diffSegundos = Math.floor((adjustedNow - dataInicio) / 1000);
            const tempoFormatado = formatSecondsToHHMMSS(diffSegundos);
            const badgeClass = getBadgeClass(diffSegundos);

            const tituloEtapa =
                modoDuracao === "em_andamento"
                    ? `Tempo na etapa atual (desde ${dataInicio.toLocaleString("pt-BR")})`
                    : `Em andamento. Iniciado em ${dataInicio.toLocaleString("pt-BR")}`;
            cell.innerHTML = `<span class="badge ${badgeClass}" title="${prodespGestaoEsc(tituloEtapa)}">${prodespGestaoEsc(tempoFormatado)}</span>`;
        });
    }

    // ==============================================================================
    // EVENT LISTENERS
    // ==============================================================================

    // Inicialização (padrão hoje/hoje; datas futuras permitidas)
    const Lpd = window.LoginPeriodoDatas;
    const today =
        Lpd && typeof Lpd.hojeISO === "function"
            ? Lpd.hojeISO()
            : new Date().toISOString().slice(0, 10);
    if (!$("#startDate").val()) {
        $("#startDate").val(today);
    }
    if (!$("#endDate").val()) {
        $("#endDate").val(today);
    }
    // Não usar LoginPeriodoDatas.vincularPar: ele sempre sobe o fim;
    // aqui o ajuste depende de qual campo o usuário alterou.
    prodespAllowFutureDashboardDates();
    prodespNormalizeDashboardDateRange(null);
    dashboardDatesAtLastApply = prodespCurrentDashboardDateRange();

    initializeDataTable();
    if (window.ProdespDtSync) {
        window.prodespGestaoDtSync = window.ProdespDtSync.create({
            getTableSettings: function () {
                return dataTableInstance && dataTableInstance.settings()[0];
            },
            onServerTime: function (iso) {
                timeOffset = Date.now() - new Date(iso).getTime();
            },
            onReload: function () {
                return new Promise(function (resolve) {
                    dataTableInstance.ajax.reload(function () {
                        prodespOnDashboardReloadComplete(false);
                        resolve();
                    }, false);
                });
            },
        });
        window.prodespDtSyncInstance = window.prodespGestaoDtSync;
        window.prodespGestaoDtSync.schedule();
    }
    setInterval(() => {
        const T = window.ProdespTempoAtendimento;
        if (dataTableInstance && T && typeof T.resortDataTableSeTempo === "function") {
            T.resortDataTableSeTempo(dataTableInstance, timeOffset, [14, 15]);
        }
        atualizarTempoAtendimento();
    }, 1000);

    document.addEventListener("visibilitychange", function () {
        if (document.visibilityState !== "hidden" && window.prodespGestaoDtSync) {
            if (typeof window.prodespGestaoDtSync.checkNow === "function") {
                window.prodespGestaoDtSync.checkNow();
            } else {
                window.prodespGestaoDtSync.forceRefresh();
            }
        }
    });

    // Datas: recarga imediata ao alterar (normaliza só intervalo invertido; sem lock dia único)
    $("#startDate, #endDate").on("change", function () {
        prodespRefreshDashboardForCurrentDates(this);
    });

    $(document).on("click", "[data-prodesp-periodo-preset]", function () {
        const preset = $(this).attr("data-prodesp-periodo-preset");
        if (preset) {
            prodespAplicarPresetPeriodoDashboard(preset);
        }
    });

    function prodespLimparFiltroContratada() {
        activeContratadaFilter = null;
        recalculateAndUpdateCards();
    }

    /** Limpa busca global, column.search e filtros manuais do ColumnControl (search.fixed dtcc-list). */
    function prodespGestaoClearTableColumnFilters(dtApi) {
        if (!dtApi) return;
        dtApi.search("");
        dtApi.columns().search("");
        if (typeof dtApi.columns().ccSearchClear === "function") {
            dtApi.columns().ccSearchClear();
        } else {
            dtApi.columns().every(function () {
                const searchList = this.columnControl && this.columnControl.searchList();
                if (searchList && searchList.length) {
                    searchList.val([]).trigger("change.select2", [true]);
                }
            });
        }
    }

    $(document).on("click", "#clear-contratada-filter, #clear-contratada-filter-kpi", function () {
        prodespLimparFiltroContratada();
    });

    function prodespAplicarFiltroDashboard($el) {
        if (!dataTableInstance) return;

        const filterMode = $el.data("filter-mode");
        const filterValue = $el.data("filter-value");
        const columnIndex = $el.data("filter-column");

        activeAgendadasPeriodoFilter = filterMode === "agendadas-periodo";

        prodespGestaoClearTableColumnFilters(dataTableInstance);

        const colStatus = dataTableInstance.column(prodespGestaoDtCol("STATUS"));
        const colSubstatus = dataTableInstance.column(prodespGestaoDtCol("SUBSTATUS"));

        const applyColumn = (column, value, useRegex) => {
            const searchList = column.columnControl && column.columnControl.searchList();
            if (searchList && searchList.length && !useRegex) {
                searchList.val(value === "all" || !value ? [] : [value]).trigger("change");
            } else {
                const term = value ? (useRegex ? value : `^${value}$`) : "";
                column.search(term, !!useRegex, false);
            }
        };

        if (filterMode === "migrados") {
            applyColumn(colStatus, "Concluído", true);
            applyColumn(colSubstatus, "Concluído", true);
        } else if (filterMode === "tem-atendimento") {
            applyColumn(colStatus, "^(?!Agendado$).+", true);
            colSubstatus.search("");
        } else if (filterMode === "somente-agendado") {
            applyColumn(colStatus, "^Agendado$", true);
            colSubstatus.search("");
        } else if (filterMode === "agendadas-periodo") {
            colStatus.search("");
            colSubstatus.search("");
            dataTableInstance.search("");
        } else if (filterMode === "status" && filterValue) {
            applyColumn(colStatus, filterValue, true);
            colSubstatus.search("");
        } else if (filterMode === "substatus" && filterValue != null) {
            colStatus.search("");
            applyColumn(colSubstatus, filterValue, true);
        } else if (filterMode === "aguardando-cliente") {
            applyColumn(colStatus, "Em Atendimento", true);
            applyColumn(colSubstatus, "Aguardando Cliente", true);
        } else if (filterMode === "aguarda-gestao") {
            applyColumn(colStatus, "Em Atendimento", true);
            applyColumn(colSubstatus, "^Aguarda Gestão$|^Triagem$", true);
        } else if (filterMode === "aguarda-contratada") {
            applyColumn(colStatus, "Em Atendimento", true);
            applyColumn(colSubstatus, "^Aguarda Contratada$", true);
        } else if (filterMode === "aguarda-licenca") {
            applyColumn(colStatus, "Em Atendimento", true);
            applyColumn(colSubstatus, "^Aguarda Licença$", true);
        } else if (columnIndex != null && filterValue != null) {
            applyColumn(dataTableInstance.column(columnIndex), filterValue, true);
        }

        dataTableInstance.draw();

        $('html, body').animate({
            scrollTop: $("#table-section-header").offset().top - 70,
        }, 500);
    }

    $(document).on("click", ".dashboard-filterable-card", function (e) {
        if ($(e.target).closest("#clear-contratada-filter").length) {
            return;
        }
        prodespAplicarFiltroDashboard($(this));
    });

    // Handler para o card "Agent ID Pendente"
    $("#agent-id-pendente-count").closest(".performance-card").on("click", function () {
        prodespGestaoClearTableColumnFilters(dataTableInstance);

        const column = dataTableInstance.column(11); // A. Config. (após coluna Município)
        column.search("Pendente", true, false).draw();

        $('html, body').animate({
            scrollTop: $("#table-section-header").offset().top - 70
        }, 500);
    });

    // Limpar filtros
    $("#btnClearFilters").on("click", function () {
        // 1. Reseta os campos de data para o dia atual
        const Lclear = window.LoginPeriodoDatas;
        if (Lclear && typeof Lclear.resetarParHoje === "function") {
            Lclear.resetarParHoje("startDate", "endDate");
        } else {
            const todayClear =
                Lclear && typeof Lclear.hojeISO === "function"
                    ? Lclear.hojeISO()
                    : new Date().toISOString().slice(0, 10);
            $("#startDate").val(todayClear);
            $("#endDate").val(todayClear);
        }
        prodespAllowFutureDashboardDates();
        prodespNormalizeDashboardDateRange(null);
        const curClear = prodespCurrentDashboardDateRange();
        dashboardDatesAtLastApply = { start: curClear.start, end: curClear.end };

        // Reseta filtros customizados da tabela
        activeContratadaFilter = null;
        activeAgendadasPeriodoFilter = false;
        updateContratadaFilterBar();

        // 2. Limpa busca global, column.search e filtros manuais ColumnControl
        prodespGestaoClearTableColumnFilters(dataTableInstance);

        // 3. Recarrega dados do novo período (KPIs + tabela no mesmo ciclo).
        prodespMarkDashboardPeriodPending();
        refreshDashboardData();
    });

    // ==============================================================================
    // HANDLERS PARA CARDS NÃO-FILTRÁVEIS POR PADRÃO
    // ==============================================================================

    $("#card-total-periodo").on("click", function () {
        if (activeContratadaFilter) {
            activeContratadaFilter = null;
            updateContratadaFilterBar();
        }
        activeAgendadasPeriodoFilter = false;
        if (!dataTableInstance) return;
        prodespGestaoClearTableColumnFilters(dataTableInstance);
        dataTableInstance.draw();
        recalculateAndUpdateCards();

        $('html, body').animate({
            scrollTop: $("#table-section-header").offset().top - 70
        }, 500);
    });

    // ===============================================================================
    // HANDLERS DE MODAIS
    // ===============================================================================

    function fillDetailsModal(data) {
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (!el) return;
            if (val == null || val === undefined) {
                el.value = "";
                return;
            }
            const s = typeof val === "string" ? val.trim() : String(val).trim();
            el.value = s === "" || s === "None" || s === "null" ? "" : s;
        };

        // Aba: Dados Unidade e Conectividade
        setVal("detailsDataAgendamento", data.data_agendamento);
        setVal("detailsHoraAgendamento", data.hora_agendamento);
        setVal("detailsIdVgr", data.id_vgr);
        setVal("detailsNome", data.nome);
        setVal("detailsEndereco", data.endereco);
        setVal("detailsNumero", data.numero);
        setVal("detailsBairro", data.bairro);
        setVal("detailsCep", data.cep);
        setVal("detailsMunicipio", data.municipio);
        setVal("detailsEstado", data.estado);
        setVal("detailsComplemento", data.complemento);
        setVal("detailsLatitude", data.latitude);
        setVal("detailsLongitude", data.longitude);
        setVal("detailsTelefoneContato", data.telefone_contato);
        setVal("detailsAcronimo", data.acronimo);
        setVal("detailsHostname", data.hostname);
        setVal("detailsIpLan01", data.ip_lan_01);
        setVal("detailsIpLanTransito", data.ip_lan_transito);
        setVal("detailsIdintragov", data.id_intragov);
        setVal("detailsLoopbackVivo", data.loopback_vivo);
        setVal("detailsLoopbackCliente", data.loopback_cliente);
        setVal("detailsLoopbackOnBgp", data.loopback_on_bgp);
        [
            ["mv_ip_lan_sec", "detailsMvIpLanSec"],
            ["mv_rede_lan_sec", "detailsMvRedeLanSec"],
            ["mv_ip_lan_ter", "detailsMvIpLanTer"],
            ["mv_rede_lan_ter", "detailsMvRedeLanTer"],
            ["mv_ip_lan_qua", "detailsMvIpLanQua"],
            ["mv_rede_lan_qua", "detailsMvRedeLanQua"],
            ["mv_ip_transito", "detailsMvIpTransito"],
            ["mv_mask_transito", "detailsMvMaskTransito"],
            ["mv_ip_swt", "detailsMvIpSwt"],
            ["mv_rede_voz", "detailsMvRedeVoz"],
            ["mv_mask_voz", "detailsMvMaskVoz"],
            ["mv_rede_lan_assoc", "detailsMvRedeLanAssoc"],
            ["mv_mask_lan_assoc", "detailsMvMaskLanAssoc"],
            ["mv_rede_totem", "detailsMvRedeTotem"],
            ["mv_mask_totem", "detailsMvMaskTotem"],
            ["mv_rede_wifi_guest", "detailsMvRedeWifiGuest"],
            ["mv_ip_wifi_guest", "detailsMvIpWifiGuest"],
            ["mv_dhcp_start_wifi_guest", "detailsMvDhcpStartWifiGuest"],
            ["mv_dhcp_end_wifi_guest", "detailsMvDhcpEndWifiGuest"],
            ["mv_reserva_start_wifi_guest", "detailsMvReservaStartWifiGuest"],
            ["mv_reserva_end_wifi_guest", "detailsMvReservaEndWifiGuest"],
        ].forEach(([key, elId]) => setVal(elId, data[key]));

        // Aba: Atendimento
        setVal("detailsAtendimentoId", data.id_atendimentos);
        setVal("detailsContratada", data.contratada);
        setVal("detailsField", data.field_responsavel);
        setVal("detailsContatoField", data.contato_field);
        setVal("detailsAnalistaAtuante", data.analista_atuante);
        setVal("detailsAnalistaConfiguracao", data.analista_configuracao);
        setVal("detailsAnalistaMplsAtendimentos", data.analista_mpls_atendimentos);
        setVal("detailsAnalistaCadernoTeste", data.analista_caderno_teste);
        setVal("detailsTicketNoc", data.ticket_noc);
        setVal("detailsLogs", data.logs_atendimento);
        renderMotivosView(document.getElementById("detailsMotivosForaPadrao"), data.motivos_fora_padrao || []);
        setVal("detailsStatus", data.status_atendimento);
        setVal("detailsSubstatus", data.substatus_atendimento);
        if (typeof window.prodespCadernoAtualizarToolbar === "function") {
            window.prodespCadernoAtualizarToolbar();
        }
    }

    $("#tabela-gestao-atendimentos tbody").on("click", ".open-details-modal", function () {
        const atendimentoId = this.dataset.idAtendimento;

        fetch(`/prodesp/atendimentos/${atendimentoId}?include=historico,marcos`)
            .then((res) => (res.ok ? res.json() : Promise.reject(res.statusText)))
            .then((data) => {
                const historicoResposta = data.historico_auditoria || { dados: data.historico_atendimento };
                const marcosResposta = data.marcos_atividade || [];
                fillDetailsModal(data);

                // Aba: Equipamentos e Links (accordion — mesmo padrão create/edit)
                window.prodespPopulateEquipamentosViewList(
                    document.getElementById("log-equipamento-details"),
                    data.equipamentos,
                    "Nenhum equipamento."
                );
                window.prodespPopulateLinksViewList(
                    document.getElementById("log-link-details"),
                    data.links,
                    "Nenhum link."
                );

                // Aba: Atendimento (Observações)
                const logObservacaoDetails = document.getElementById("log-observacao-details");
                const noObservacaoDetails = document.getElementById("no-observacao-details");
                
                logObservacaoDetails.innerHTML = '<div class="titles-incident"><span>DATA</span><span>OBSERVAÇÕES</span></div>';

                if (data.observacoes && data.observacoes.length > 0) {
                    noObservacaoDetails.style.display = "none";
                    const ordenadas =
                        typeof window.prodespSortObservacoesDesc === "function"
                            ? window.prodespSortObservacoesDesc(data.observacoes)
                            : data.observacoes;
                    ordenadas.forEach((obs) => renderObservacaoCardDetails(obs, logObservacaoDetails));
                } else {
                    noObservacaoDetails.style.display = "block";
                }

                // Aba: Marcos da Atividade
                const marcosContainer = document.getElementById("marcos-container");
                marcosContainer.innerHTML = renderMarcos(marcosResposta);

                // Aba: Histórico
                const historicoContainer = document.getElementById("historico-container");
                const isAdmin = historicoResposta.admin_user === 1;
                historicoContainer.innerHTML =
                    typeof window.renderHistoricoCompleto === "function"
                        ? window.renderHistoricoCompleto(historicoResposta, isAdmin)
                        : renderHistorico(historicoResposta.dados, isAdmin);
                if (typeof window.prodespBindHistoricoCollapseControls === "function") {
                    window.prodespBindHistoricoCollapseControls(historicoContainer);
                }

                const detailsEl = document.getElementById("detailsModal");
                if (window.ProdespModal && typeof window.ProdespModal.open === "function") {
                    window.ProdespModal.open(detailsEl);
                } else {
                    bootstrap.Modal.getOrCreateInstance(detailsEl).show();
                }
            })
            .catch((error) => {
                console.error("Erro ao buscar detalhes do atendimento:", error);
                showToast("Não foi possível carregar os detalhes do atendimento.", "danger");
            });
    });

    if (window.PRODESP_GESTAO_OPERAR_ATENDIMENTOS) {
        $("#btnGestaoNovoAtendimento").on("click", function () {
            if (typeof window.openCreateModal === "function") {
                window.openCreateModal();
            }
        });

        $("#tabela-gestao-atendimentos tbody").on("click", ".open-edit-gestao-modal", function () {
            const id = parseInt(this.dataset.idAtendimento, 10);
            if (!id || typeof window.editDetails !== "function") return;
            window.editDetails(id).then(function () {
                if (typeof refreshDashboardData === "function") {
                    refreshDashboardData();
                }
            });
        });

        $("#tabela-gestao-atendimentos tbody").on("click", ".open-create-gestao-modal", function () {
            const idVgr = (this.dataset.idVgr || "").trim();
            if (!idVgr) return;
            if (typeof window.openCreateWithVgr === "function") {
                window.openCreateWithVgr(idVgr);
            } else if (typeof window.openCreateModal === "function") {
                window.openCreateModal();
            }
        });

        $("#tabela-gestao-atendimentos tbody").on("click", ".prodesp-admin-excluir-atendimento", function (e) {
            e.preventDefault();
            e.stopPropagation();
            const btn = e.target.closest(".prodesp-admin-excluir-atendimento");
            if (!btn) return;
            const id = parseInt(btn.dataset.idAtendimento, 10);
            if (!id) return;
            prodespGestaoAdminExcluirAtendimento(id);
        });

        $("#tabela-gestao-atendimentos tbody").on("click", ".prodesp-admin-remover-agendamento", function (e) {
            e.preventDefault();
            e.stopPropagation();
            const btn = e.target.closest(".prodesp-admin-remover-agendamento");
            if (!btn) return;
            const idVgr = (btn.dataset.idVgr || "").trim();
            if (!idVgr) return;
            prodespGestaoAdminRemoverAgendamento(idVgr);
        });

        const PRODESP_QUEBRA_MASSA_SUBSTATUS = {
            Quebra: [
                "Quebra Link",
                "Quebra Infra",
                "Quebra Hardware",
                "Quebra Field",
                "Quebra Cliente",
                "Quebra Vita",
            ],
            "Quebra TBRA": ["Quebra SCI", "Quebra Técnica"],
        };

        function prodespPreencherSubstatusQuebraMassa() {
            const tipo = ($("#quebraMassaTipo").val() || "Quebra").trim();
            const $sub = $("#quebraMassaSubstatus");
            $sub.empty();
            (PRODESP_QUEBRA_MASSA_SUBSTATUS[tipo] || []).forEach((s) => {
                $sub.append(new Option(s, s));
            });
        }

        function prodespContratadaCanonicaQuebraMassa(nome) {
            const bruto = (nome || "").trim();
            if (!bruto) {
                return null;
            }
            const permitidas = window.PRODESP_CONTRATADAS_PERMITIDAS || [];
            for (let i = 0; i < permitidas.length; i += 1) {
                if (String(permitidas[i]).toLowerCase() === bruto.toLowerCase()) {
                    return permitidas[i];
                }
            }
            return null;
        }

        function prodespQuebraMassaDadosPlanejados(row) {
            const contratada = prodespContratadaCanonicaQuebraMassa(
                row.contratada_planejada_unidades || row.contratada_atendimentos
            );
            const field = (row.field_planejada_unidades || row.field_atendimentos || "").trim();
            const contatoRaw = row.contato_field_planejada_unidades || row.contato_field_atendimentos || "";
            const contatoDigits = String(contatoRaw).replace(/\D/g, "");
            const contatoValido = contatoDigits.length >= 10 && contatoDigits.length <= 11;
            const falhas = [];
            const avisos = [];
            if (!contratada) {
                falhas.push("contratada");
            }
            if (!field) {
                avisos.push("field padrão «-»");
            }
            if (!contatoValido) {
                avisos.push("contato zerado");
            }
            return {
                ok: falhas.length === 0,
                falhas,
                avisos,
                contratada,
                field: field || "-",
                contatoDigits: contatoValido ? contatoDigits : "00000000000",
            };
        }

        function prodespFormatarDataQuebraMassa(data) {
            if (!data) return "";
            const datePart = String(data).split(/[T ]/)[0];
            if (!datePart) return "";
            return new Date(`${datePart}T00:00:00`).toLocaleDateString("pt-BR");
        }

        function prodespParseTokensBuscaQuebraMassa(raw) {
            return String(raw || "")
                .split(/[\s,;\t\r\n]+/)
                .map((t) => t.trim().toLowerCase())
                .filter(Boolean);
        }

        function prodespVgrCombinaTokenQuebraMassa(vgr, token) {
            if (!vgr || !token) return false;
            return vgr === token || vgr.includes(token) || token.includes(vgr);
        }

        function prodespTokenPareceVgrQuebraMassa(token) {
            return /^\d{4,}$/.test(String(token || ""));
        }

        function prodespItemVisivelQuebraMassa(vgr, texto, tokens, raw) {
            if (!tokens.length) return true;
            const multiId =
                tokens.length > 1 || /[,;\n\r\t]/.test(raw);
            if (multiId) {
                return tokens.some((t) => prodespVgrCombinaTokenQuebraMassa(vgr, t));
            }
            const q = tokens[0];
            if (prodespTokenPareceVgrQuebraMassa(q)) {
                return prodespVgrCombinaTokenQuebraMassa(vgr, q);
            }
            return texto.indexOf(q) >= 0 || vgr.indexOf(q) >= 0;
        }

        function prodespFiltrarListaQuebraMassa() {
            const raw = ($("#quebraMassaBusca").val() || "").trim();
            const tokens = prodespParseTokensBuscaQuebraMassa(raw);

            $("#quebraMassaLista .quebra-massa-item").each(function () {
                const $el = $(this);
                const vgr = String(
                    $el.attr("data-vgr") || $el.find(".quebra-massa-vgr").val() || ""
                )
                    .trim()
                    .toLowerCase();
                const texto = String($el.attr("data-search") || "").toLowerCase();
                const visivel = prodespItemVisivelQuebraMassa(vgr, texto, tokens, raw);
                // d-flex do Bootstrap usa !important — .toggle() não oculta; usar d-none
                $el.toggleClass("d-none", !visivel);
            });
            $("#quebraMassaLista .quebra-massa-grupo").each(function () {
                const $grupo = $(this);
                const itensVisiveis = $grupo.find(".quebra-massa-item").not(".d-none").length;
                $grupo.toggleClass("d-none", tokens.length > 0 && itensVisiveis === 0);
            });
        }

        function prodespListarAgendadosQuebraMassa() {
            const $lista = $("#quebraMassaLista");
            $lista.empty();
            if (!dataTableInstance) {
                $lista.html('<p class="text-muted small mb-0">Carregue a tabela primeiro.</p>');
                return;
            }
            const rows = [];
            dataTableInstance.rows({ search: "applied" }).every(function () {
                const row = this.data();
                if (!row) return;
                if (!rowEhSomenteAgendado(row) || !row.data_agendamento) {
                    return;
                }
                rows.push(row);
            });
            if (!rows.length) {
                $lista.html('<p class="text-muted small mb-0">Nenhuma unidade agendada visível no filtro atual.</p>');
                return;
            }

            const grupos = {};
            rows.forEach((row) => {
                const chave = prodespContratadaRowKey(row);
                if (!grupos[chave]) {
                    grupos[chave] = [];
                }
                grupos[chave].push(row);
            });

            const chaves = Object.keys(grupos).sort((a, b) => {
                if (a === "Não Informado") return 1;
                if (b === "Não Informado") return -1;
                return a.localeCompare(b, "pt-BR");
            });

            const $accordion = $('<div class="accordion accordion-flush" id="quebraMassaAccordion"></div>');

            chaves.forEach((contratadaGrupo, gi) => {
                const itens = grupos[contratadaGrupo].slice().sort((a, b) => {
                    const da = prodespFormatarDataQuebraMassa(a.data_agendamento);
                    const db = prodespFormatarDataQuebraMassa(b.data_agendamento);
                    if (da !== db) return da.localeCompare(db, "pt-BR");
                    return String(a.id_vgr || "").localeCompare(String(b.id_vgr || ""), "pt-BR");
                });
                const incompletos = itens.filter((row) => !prodespQuebraMassaDadosPlanejados(row).ok).length;
                const comPadrao = itens.filter((row) => {
                    const d = prodespQuebraMassaDadosPlanejados(row);
                    return d.ok && d.avisos.length > 0;
                }).length;
                const collapseId = `qm-collapse-${gi}`;
                const headingId = `qm-heading-${gi}`;
                const expandido = gi === 0 ? "show" : "";
                const btnCollapsed = gi === 0 ? "" : "collapsed";

                const $grupo = $(`
                    <div class="accordion-item quebra-massa-grupo border rounded mb-2" data-grupo="${prodespGestaoEsc(contratadaGrupo)}">
                        <h2 class="accordion-header d-flex align-items-stretch" id="${headingId}">
                            <button class="accordion-button ${btnCollapsed} py-2 flex-grow-1" type="button"
                                data-bs-toggle="collapse" data-bs-target="#${collapseId}"
                                aria-expanded="${gi === 0 ? "true" : "false"}" aria-controls="${collapseId}">
                                <span class="d-flex align-items-center flex-wrap gap-1">
                                    <strong class="small">${prodespGestaoEsc(contratadaGrupo)}</strong>
                                    <span class="badge text-bg-secondary">${itens.length}</span>
                                    ${incompletos ? `<span class="badge text-bg-warning text-dark">${incompletos} sem contratada</span>` : ""}
                                    ${comPadrao ? `<span class="badge text-bg-info text-dark">${comPadrao} com padrão</span>` : ""}
                                </span>
                            </button>
                            <button type="button" class="btn btn-link btn-sm py-0 px-2 align-self-center quebra-massa-marcar-grupo flex-shrink-0"
                                data-grupo-idx="${gi}" title="Marcar itens habilitados desta contratada">Marcar</button>
                        </h2>
                        <div id="${collapseId}" class="accordion-collapse collapse ${expandido}">
                            <div class="accordion-body py-1 px-2"></div>
                        </div>
                    </div>
                `);
                const $corpo = $grupo.find(".accordion-body");

                itens.forEach((row) => {
                    const vgr = String(row.id_vgr || "").trim();
                    const end = (row.endereco || "").trim();
                    const dataFmt = prodespFormatarDataQuebraMassa(row.data_agendamento);
                    const dados = prodespQuebraMassaDadosPlanejados(row);
                    const fieldResumo = ` · Field: ${dados.field}`;
                    let aviso = "";
                    if (!dados.ok) {
                        aviso = `<span class="text-warning small d-block">Sem contratada válida no agendamento</span>`;
                    } else if (dados.avisos.length) {
                        aviso = `<span class="text-muted small d-block">Será usado: ${prodespGestaoEsc(dados.avisos.join(", "))}</span>`;
                    }
                    const searchText = [vgr, dataFmt, end, dados.field, contratadaGrupo].join(" ");

                    $corpo.append(
                        `<label class="d-flex align-items-start gap-2 py-1 border-bottom quebra-massa-item ${dados.ok ? "" : "opacity-75"}"
                            data-vgr="${prodespGestaoEsc(vgr)}"
                            data-search="${prodespGestaoEsc(searchText)}">
                            <input type="checkbox" class="form-check-input mt-1 quebra-massa-vgr"
                                value="${prodespGestaoEsc(vgr)}"
                                data-grupo-idx="${gi}"
                                ${dados.ok ? "" : "disabled"} />
                            <span class="small">
                                <strong>${prodespGestaoEsc(vgr)}</strong>${dataFmt ? ` · ${prodespGestaoEsc(dataFmt)}` : ""}${end ? ` — ${prodespGestaoEsc(end)}` : ""}${prodespGestaoEsc(fieldResumo)}
                                ${aviso}
                            </span>
                        </label>`
                    );
                });

                $accordion.append($grupo);
            });

            $lista.append($accordion);
            prodespFiltrarListaQuebraMassa();
        }

        function prodespResetQuebraMassaConfirmarBtn() {
            const $btn = $("#quebraMassaConfirmar");
            $btn.prop("disabled", false).html(
                '<i class="fas fa-check me-1"></i>Confirmar quebra'
            );
        }

        let prodespQuebraMassaEmAndamento = false;

        function prodespAbrirQuebraMassaModal() {
            const modalEl = document.getElementById("quebraMassaModal");
            if (!modalEl) {
                showToast("Modal de quebra em massa não encontrado.", "danger");
                return;
            }
            if (window.ProdespModal && typeof window.ProdespModal.ensureOnBody === "function") {
                window.ProdespModal.ensureOnBody(modalEl);
            }
            prodespQuebraMassaEmAndamento = false;
            prodespResetQuebraMassaConfirmarBtn();
            prodespPreencherSubstatusQuebraMassa();
            $("#quebraMassaObservacao").val("");
            $("#quebraMassaBusca").val("");
            prodespListarAgendadosQuebraMassa();
            if (window.ProdespModal && typeof window.ProdespModal.open === "function") {
                window.ProdespModal.open(modalEl);
            } else if (typeof bootstrap !== "undefined") {
                bootstrap.Modal.getOrCreateInstance(modalEl).show();
            } else {
                showToast("Bootstrap não disponível para abrir o modal.", "danger");
            }
        }

        function prodespFecharQuebraMassaModal() {
            const modalEl = document.getElementById("quebraMassaModal");
            if (!modalEl) return;
            const inst = typeof bootstrap !== "undefined" ? bootstrap.Modal.getInstance(modalEl) : null;
            if (inst) {
                inst.hide();
            }
            if (window.ProdespModal && typeof window.ProdespModal.cleanupModalArtifacts === "function") {
                window.setTimeout(() => window.ProdespModal.cleanupModalArtifacts(), 0);
            }
        }

        $("#btnGestaoQuebraMassa").on("click", function () {
            prodespAbrirQuebraMassaModal();
        });

        $("#quebraMassaTipo").on("change", prodespPreencherSubstatusQuebraMassa);

        $("#quebraMassaSelecionarVisiveis").on("click", function () {
            $("#quebraMassaLista .quebra-massa-vgr:not(:disabled)")
                .filter(function () {
                    return !$(this).closest(".quebra-massa-item").hasClass("d-none");
                })
                .prop("checked", true);
        });

        $("#quebraMassaBusca").on("input keyup search", prodespFiltrarListaQuebraMassa);

        $("#quebraMassaExpandirGrupos").on("click", function () {
            $("#quebraMassaAccordion .accordion-collapse").each(function () {
                if (typeof bootstrap !== "undefined") {
                    bootstrap.Collapse.getOrCreateInstance(this, { toggle: false }).show();
                } else {
                    $(this).addClass("show");
                }
            });
        });

        $("#quebraMassaRecolherGrupos").on("click", function () {
            $("#quebraMassaAccordion .accordion-collapse").each(function () {
                if (typeof bootstrap !== "undefined") {
                    bootstrap.Collapse.getOrCreateInstance(this, { toggle: false }).hide();
                } else {
                    $(this).removeClass("show");
                }
            });
        });

        $(document).on("click", ".quebra-massa-marcar-grupo", function (e) {
            e.preventDefault();
            e.stopPropagation();
            const idx = String($(this).attr("data-grupo-idx") ?? "");
            $(`#quebraMassaLista .quebra-massa-vgr[data-grupo-idx="${idx}"]:not(:disabled)`)
                .filter(function () {
                    return !$(this).closest(".quebra-massa-item").hasClass("d-none");
                })
                .prop("checked", true);
        });

        $("#quebraMassaConfirmar").on("click", async function () {
            if (prodespQuebraMassaEmAndamento) {
                showToast("Quebra em massa já está em processamento. Aguarde a conclusão.", "warning");
                return;
            }
            const ids = [...new Set(
                $("#quebraMassaLista .quebra-massa-vgr:checked")
                    .map(function () { return String($(this).val() || "").trim(); })
                    .get()
                    .filter(Boolean)
            )];
            const observacao = ($("#quebraMassaObservacao").val() || "").trim();
            const payload = {
                ids_vgr: ids,
                status: ($("#quebraMassaTipo").val() || "").trim(),
                substatus: ($("#quebraMassaSubstatus").val() || "").trim(),
                observacao,
            };
            if (!ids.length) {
                showToast("Selecione ao menos uma unidade agendada com contratada válida no agendamento.", "warning");
                return;
            }
            if (observacao.length < 10) {
                showToast("Informe a observação da quebra (mín. 10 caracteres).", "warning");
                return;
            }
            const rotulo = ids.length === 1 ? "1 unidade" : `${ids.length} unidades`;
            if (!window.confirm(`Confirmar quebra em massa para ${rotulo}? Esta ação não pode ser desfeita pelo mesmo clique.`)) {
                return;
            }
            const btn = this;
            prodespQuebraMassaEmAndamento = true;
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Processando…';
            try {
                const resp = await fetch("/prodesp/api/quebra_massa", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                });
                const json = await resp.json().catch(() => ({}));
                if (!resp.ok || !json.success) {
                    const extra = (json.erros || []).join(" ");
                    const msg =
                        json.message ||
                        (resp.status >= 500
                            ? "Falha interna na quebra em massa. Tente novamente ou contate o suporte."
                            : "Falha na quebra em massa.");
                    showToast(extra ? `${msg} ${extra}` : msg, "danger");
                    return;
                }
                if (json.erros && json.erros.length) {
                    showToast(`${json.message} Avisos: ${json.erros.join(" ")}`, "warning");
                } else {
                    showToast(json.message || "Quebra em massa concluída.", "success");
                }
                prodespFecharQuebraMassaModal();
                refreshDashboardData();
            } catch (e) {
                console.error(e);
                showToast("Erro ao processar quebra em massa.", "danger");
            } finally {
                prodespQuebraMassaEmAndamento = false;
                prodespResetQuebraMassaConfirmarBtn();
            }
        });
    }

    /**
     * Visualiza os dados da unidade e conectividade (pré-carregamento) quando não há atendimento.
     * @param {string} idVgr - O ID VGR da unidade.
     */
    window.viewUnitOnly = function(idVgr) {
        fetch(`/prodesp/unidades/${encodeURIComponent(idVgr)}`)
            .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
            .then(json => {
                if (!json.success) throw new Error(json.message);
                const u = json.unidade;
                
                const d = {
                    ...u,
                    id_atendimentos: null,
                    status_atendimento: "Agendado",
                    substatus_atendimento: "",
                    analista_atuante: "",
                    analista_configuracao: "",
                    analista_mpls_atendimentos: "",
                    analista_caderno_teste: "",
                    contratada: "",
                    field_responsavel: "",
                    contato_field: "",
                    logs_atendimento: "",
                    data_atendimento: null,
                    observacoes: [],
                    equipamentos: u.equipamentos || [],
                    links: u.links || []
                };

                fillDetailsModal(d);
                document.getElementById("log-equipamento-details").innerHTML = '<div class="text-muted p-2">Dados carregados da Unidade (Atendimento não iniciado).</div>';
                document.getElementById("log-link-details").innerHTML = '<div class="text-muted p-2">Dados carregados da Unidade (Atendimento não iniciado).</div>';
                document.getElementById("marcos-container").innerHTML = '<div class="text-center text-muted p-3"><em>— Atendimento não iniciado —</em></div>';
                const histContainer = document.getElementById("historico-container");
                const idUnidade = u.id_unidade || u.id_unidades;
                if (histContainer && idUnidade && typeof window.renderHistoricoCompleto === "function") {
                    fetch(`/prodesp/historico_unidade/${idUnidade}`)
                        .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
                        .then((histU) => {
                            histContainer.innerHTML = window.renderHistoricoCompleto(
                                {
                                    historico_atendimento: [],
                                    historico_unidade: histU.historico_unidade || [],
                                    historico_equipamentos: histU.historico_equipamentos || [],
                                    historico_links: histU.historico_links || [],
                                    historico_observacao: (histU.historico_unidade || []).filter((h) => {
                                        const c = (h.campo_alterado_historico || "").trim();
                                        return c === "Observação" || c === "Observacao";
                                    }),
                                    eventos_relacionados: [],
                                    observacoes: (u.observacoes || []).map((o) => ({
                                        ...o,
                                        escopo: "unidade",
                                    })),
                                    equipamentos: u.equipamentos || [],
                                    links: u.links || [],
                                },
                                histU.admin_user === 1
                            );
                            if (typeof window.prodespBindHistoricoCollapseControls === "function") {
                                window.prodespBindHistoricoCollapseControls(histContainer);
                            }
                        })
                        .catch(() => {
                            histContainer.innerHTML =
                                '<div class="text-muted ms-2 mt-2">Não foi possível carregar o histórico da unidade.</div>';
                        });
                } else if (histContainer) {
                    histContainer.innerHTML =
                        '<div class="text-muted ms-2 mt-2">Nenhum histórico de atendimento (unidade sem ID).</div>';
                }
                const detailsEl = document.getElementById("detailsModal");
                if (window.ProdespModal && typeof window.ProdespModal.open === "function") {
                    window.ProdespModal.open(detailsEl);
                } else {
                    bootstrap.Modal.getOrCreateInstance(detailsEl).show();
                }
            })
            .catch(err => {
                console.error("Erro em viewUnitOnly:", err);
                showToast("Não foi possível carregar os dados da unidade.", "danger");
            });
    };

    // ==============================================================================
    // RENDERIZAÇÃO DOS MARCOS DA ATIVIDADE - MODAL DETALHES
    // ==============================================================================

    function renderMarcos(marcos) {
        if (!marcos || !marcos.length) {
            return `<div class="text-center text-muted p-3"><em>— Nenhum marco de atividade registrado —</em></div>`;
        }

        const formatar = (str) => {
            if (!str) return "—";
            const d = new Date(str);
            return `${d.toLocaleDateString("pt-BR")} às ${d.toLocaleTimeString("pt-BR", {
                hour: "2-digit",
                minute: "2-digit",
            })}`;
        };

        const formatarDuracao = (segundos) => {
            if (segundos == null || isNaN(segundos)) return "—";
            if (segundos < 0) return "Inválido";
            const h = Math.floor(segundos / 3600);
            const m = Math.floor((segundos % 3600) / 60);
            const s = Math.floor(segundos % 60);
            return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
        };

        // 🎨 Define a cor da linha (Lógica baseada em intervalos de 15 minutos)
        const getClasse = (marco, duracao) => {
            if (!duracao || marco === "Concluído") return "";
            
            const minutos = duracao / 60;
            
            if (minutos >= 30) return "vermelho";
            if (minutos >= 15) return "amarelo";
            return "azul"; 
        };

        // 📊 Legenda
        const legendaHTML = `
            <div class="mb-3 small">
            <strong>Legenda:</strong>
            <div class="mt-2"><span class="badge bg-info text-dark">Azul</span> — Até 15 minutos</div>
            <div class="mt-2"><span class="badge bg-warning text-dark">Amarelo</span> — Entre 15 e 30 minutos</div>
            <div class="mt-2"><span class="badge bg-danger">Vermelho</span> — Acima de 30 minutos</div>
            </div>
        `;

        const tableRows = marcos.map(m => {
            const classe = getClasse(m.marco, m.duracao);
            let cor = "";
            if (classe === "vermelho") cor = "table-danger";
            else if (classe === "amarelo") cor = "table-warning";
            else if (classe === "azul") cor = "table-info";

            return `
            <tr class="${cor}">
                <td>${typeof prodespLabelMarcoAtividade === "function" ? prodespLabelMarcoAtividade(m.marco) : (m.marco === "Triagem" ? "Aguarda Gestão" : (m.marco || "—"))}</td>
                <td>${formatar(m.inicio)}</td>
                <td>${formatar(m.fim)}</td>
                <td>${formatarDuracao(m.duracao)}</td>
            </tr>
        `}).join("");

        return `
            <h6 class="text-uppercase text-secondary mb-3">⏳ Marcos da Atividade</h6>
            ${legendaHTML}
            <div class="table-responsive mt-3">
                <table class="table table-sm table-bordered table-striped">
                    <thead class="table-light"><tr><th>Marco</th><th>Início</th><th>Fim</th><th>Duração</th></tr></thead>
                    <tbody>${tableRows}</tbody>
                </table>
            </div>
        `;
    }

    // ================================================================================
    // FUNÇÃO RENDERIZAÇÃO DAS OBSERVAÇÕES - MODAL DETALHES
    // ================================================================================

    function renderObservacaoCardDetails(observacaoObj, containerEl) {
        const card = document.createElement("div");
        card.classList.add("card-incident");
        const fields = document.createElement("div");
        fields.classList.add("fields");
        const makeDiv = (cls, txt) => {
            const d = document.createElement("div");
            d.classList.add(cls);
            d.style.whiteSpace = "pre-wrap";
            d.textContent = txt || "—";
            return d;
        };

        let dataFormatada = observacaoObj.timestamp || observacaoObj.data_observacao;
        if (dataFormatada && typeof dataFormatada === "string") {
            try {
                const dataObj = new Date(dataFormatada.replace(" ", "T") + (dataFormatada.endsWith("Z") ? "" : "Z"));
                if (!isNaN(dataObj.getTime())) {
                    dataFormatada = dataObj.toLocaleString("pt-BR");
                }
            } catch (e) {
                console.error("Erro ao converter data:", e);
                dataFormatada = dataFormatada.replace(" ", "T") + (dataFormatada.endsWith("Z") ? "" : "Z");
            }
        } else if (dataFormatada instanceof Date) {
            dataFormatada = dataFormatada.toLocaleString("pt-BR");
        }
        fields.appendChild(makeDiv("incident-data", dataFormatada));
        fields.appendChild(makeDiv("incident-chamado", observacaoObj.texto || observacaoObj.observacao_prodesp || "-"));
        card.appendChild(fields);
        containerEl.appendChild(card);
    }

    // ==============================================================================
    // RENDERIZAÇÃO DO HISTÓRICO - MODAL DETALHES
    // ==============================================================================

    /**
     * Renderiza a tabela de histórico com base na permissão do usuário.
     * @param {Array} historicoData - Array de objetos de log do histórico.
     * @param {boolean} isAdmin - Flag que indica se o usuário é administrador.
     * @returns {string} O HTML completo da tabela de histórico.
     */
    function renderHistorico(historicoData, isAdmin) {
        if (!historicoData || historicoData.length === 0) {
            return '<div class="text-muted ms-2 mt-2">Nenhum histórico encontrado.</div>';
        }

        // Mapeamento de nomes de campos para nomes amigáveis
        const fieldNameMapping = {
            data_atendimentos: "Data de Atuação",
            status_atendimentos: "Status",
            substatus_atendimentos: "Substatus",
            detalhamento_quebra_atendimentos: "Detalhamento Quebra",
            analista_atuante_atendimentos: "Analista Gestão",
            contratada_atendimentos: "Contratada",
            field_atendimentos: "Field",
            contato_field_atendimentos: "Contato Field",
            situacao_atual_atendimentos: "Situação Atual",
            material_faltante_atendimentos: "Material Faltante",
            situacao_entrega_atendimentos: "Situação Entrega",
            situacao_setup_atendimentos: "Situação Setup",
            horario_inicio_atendimentos: "Horário Início",
            horario_finalizacao_atendimentos: "Horário Finalização",
        };

        const formatarData = (dataStr) => {
            if (!dataStr) return "—";
            try {
                const dataObj = new Date(dataStr);
                if (!isNaN(dataObj.getTime())) {
                    return dataObj.toLocaleString("pt-BR");
                }
            } catch (e) {
                /* Mantém a string original se falhar */
            }
            return dataStr;
        };

        if (isAdmin) {
            const tableRows = historicoData.map((log) => {
                const campoAmigavel = fieldNameMapping[log.campo_alterado_historico] || log.campo_alterado_historico;
                return `
                    <tr>
                        <td>${formatarData(log.data_alteracao_historico)}</td>
                        <td>${log.usuario_re_historico || ''} – ${log.usuario_nome_historico || "—"}</td>
                        <td>${campoAmigavel || "—"}</td>
                        <td>${log.valor_antigo_historico || "—"}</td>
                        <td>${log.valor_novo_historico || "—"}</td>
                        <td>${log.operacao_historico || "—"}</td>
                    </tr>
                `;
            }).join("");

            return `
                <div class="table-responsive">
                    <table class="table table-sm table-striped table-hover">
                        <thead><tr><th>Data</th><th>Usuário</th><th>Campo Alterado</th><th>Valor Antigo</th><th>Valor Novo</th><th>Op.</th></tr></thead>
                        <tbody>${tableRows}</tbody>
                    </table>
                </div>
            `;
        } else {
            const tableRows = historicoData.map((log) => `
                <tr>
                    <td>${formatarData(log.data_alteracao_historico)}</td>
                    <td>${log.usuario_re_historico || ''} – ${log.usuario_nome_historico || "—"}</td>
                    <td>${log.valor_novo_historico || "—"}</td>
                </tr>
            `).join("");

            return `
                <div class="table-responsive">
                    <table class="table table-sm table-striped table-hover">
                        <thead><tr><th>Data</th><th>Usuário</th><th>Informação</th></tr></thead>
                        <tbody>${tableRows}</tbody>
                    </table>
                </div>
            `;
        }
    }

    // ==============================================================================
    // HANDLER PARA DOWNLOAD DE RELATÓRIO
    // ==============================================================================
    function handleDownload(format) {
        const startDate = $("#startDate").val();
        const endDate = $("#endDate").val();

        if (!startDate || !endDate) {
            showToast("Por favor, selecione um período de datas para gerar o relatório.", "warning");
            return;
        }

        const downloadUrl = `/prodesp/download_report?start_date=${startDate}&end_date=${endDate}&format=${format}`;

        // Mensagem melhorada com spinner e layout mais amigável
        const msg = `
            <div class="d-flex align-items-center">
                <div class="spinner-border spinner-border-sm text-primary me-2" role="status" aria-hidden="true"></div>
                <div>Gerando relatório <strong>${format.toUpperCase()}</strong>.<br>O download iniciará automaticamente em instantes.</div>
            </div>
        `;
        showToast(msg, "info", 5000); // Exibe por 8 segundos

        // Inicia o download
        window.location.href = downloadUrl;
    }

    // Adiciona os listeners de clique aos botões de download
    $("#btnDownloadXLSX").on("click", function (e) {
        e.preventDefault();
        handleDownload("xlsx");
    });

    $("#btnDownloadCSV").on("click", function (e) {
        e.preventDefault();
        handleDownload("csv");
    });

});
