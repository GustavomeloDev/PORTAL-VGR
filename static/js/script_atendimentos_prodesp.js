/**
 * @file prodesp/static/js/script_atendimentos_prodesp.js
 * @module PRODESP — Fila de atendimentos (analista)
 *
 * Finalidade:
 *   Orquestra a tela operacional de atendimentos: DataTable (#tabela-atendimentos),
 *   cards de fila/KPI, filtros por status e substatus, modais de create/edit/view,
 *   regras de permissão (admin, GP, agendamento, dono do atendimento), links,
 *   equipamentos, observações, histórico e integrações com APIs /prodesp/api/*.
 *
 * Telas:
 *   - prodesp/templates/atendimentos_prodesp.html
 *
 * Depende de:
 *   - jQuery, Bootstrap 5, DataTables 2 + ColumnControl, Select2
 *   - prodesp_datatable_page_length.js, prodesp_datatable_font_size.js
 *   - prodesp_historico_view.js, prodesp_enriquecer_endereco.js, prodesp_field_limits.js
 *   - portal_perfil_rules.js (regras GP/Agendamento)
 *
 * Variáveis globais do template:
 *   LOGGED_IN_USER_ADMIN, USUARIO_LOGADO, USER_TEM_AGENDAMENTO, etc.
 *
 * Notas:
 *   Arquivo principal e mais extenso do módulo; funções prodesp* no topo são helpers
 *   reutilizados dentro deste script. Preferências de tabela ficam nos módulos ProdespDt*.
 */
function prodespIsAdminUser() {
  return parseInt(String(typeof LOGGED_IN_USER_ADMIN !== "undefined" ? LOGGED_IN_USER_ADMIN : 0), 10) === 1;
}

async function prodespAdminExcluirAtendimentoFetch(idAtendimento) {
  try {
    const resp = await fetch(`/prodesp/api/admin/atendimento/${idAtendimento}`, { method: "DELETE" });
    const json = await resp.json().catch(() => ({}));
    if (!resp.ok || !json.success) {
      showToast(json.message || "Não foi possível excluir o atendimento.", "danger");
      return;
    }
    showToast(json.message || "Atendimento excluído.", "success");
    const dt = $("#tabela-atendimentos").DataTable();
    if (dt && dt.ajax) dt.ajax.reload(null, false);
  } catch (_e) {
    showToast("Erro ao excluir atendimento.", "danger");
  }
}

function prodespAdminExcluirAtendimento(idAtendimento, ev) {
  if (ev) {
    ev.preventDefault();
    ev.stopPropagation();
  }
  if (!prodespIsAdminUser()) return false;
  const msg =
    `Excluir permanentemente o atendimento #${idAtendimento}?\n\n` +
    "Logs, observações vinculadas e registros do atendimento serão removidos. " +
    "Esta ação não pode ser desfeita.";
  if (!window.confirm(msg)) return false;
  void prodespAdminExcluirAtendimentoFetch(idAtendimento);
  return false;
}

async function prodespAdminRemoverAgendamentoFetch(idVgr) {
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
    const dt = $("#tabela-atendimentos").DataTable();
    if (dt && dt.ajax) dt.ajax.reload(null, false);
  } catch (_e) {
    showToast("Erro ao remover agendamento.", "danger");
  }
}

function prodespAdminRemoverAgendamento(idVgr, ev) {
  if (ev) {
    ev.preventDefault();
    ev.stopPropagation();
  }
  if (!prodespIsAdminUser()) return false;
  const vgr = String(idVgr || "").trim();
  if (!vgr) return false;
  const msg =
    `Remover o agendamento da unidade VGR ${vgr}?\n\n` +
    "Data e hora agendadas serão limpas. Esta ação não pode ser desfeita.";
  if (!window.confirm(msg)) return false;
  void prodespAdminRemoverAgendamentoFetch(idVgr);
  return false;
}

function prodespIsAgendamentoOuGp() {
  if (typeof portalUsuarioUsaRegrasGpAgendamentoRestritas === "function") {
    return portalUsuarioUsaRegrasGpAgendamentoRestritas();
  }
  return (
    (typeof USER_TEM_AGENDAMENTO !== "undefined" && USER_TEM_AGENDAMENTO) ||
    (typeof USER_TEM_SUPERVISORES_GP !== "undefined" && USER_TEM_SUPERVISORES_GP)
  );
}

/** AG / Supervisor-GP / Admin: editar Dados Field antes de iniciar atendimento. */
function prodespPodeEditarDadosFieldPreAtendimento() {
  return prodespIsAdminUser() || prodespIsAgendamentoOuGp();
}

const PRODESP_CREATE_DADOS_FIELD_IDS = [
  "createContratada",
  "createField",
  "createContatoField",
];

function prodespSetCreateDadosFieldEnabled(enabled) {
  PRODESP_CREATE_DADOS_FIELD_IDS.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.disabled = !enabled;
    if (el.tagName === "INPUT") {
      el.readOnly = !enabled;
    }
  });
}

/** Libera Dados Field no create quando a unidade está carregada e ainda sem atendimento. */
function prodespApplyDadosFieldPreAtendimentoUi() {
  if (currentCreateModalAtendimentoId) return;
  const pode = prodespPodeEditarDadosFieldPreAtendimento();
  const unidadeOk = !!selectedUnidadeId;
  prodespSetCreateDadosFieldEnabled(pode && unidadeOk);
}

const PRODESP_DEFAULT_FORTIOS_VERSION = "7.4.11";

function prodespFortiosVersionOrDefault(versao) {
  const v = String(versao == null ? "" : versao).trim();
  return v || PRODESP_DEFAULT_FORTIOS_VERSION;
}

function prodespParseAtendimentoDate(raw) {
  if (!raw) return null;
  const s = String(raw).trim();
  // API envia date.isoformat() → "YYYY-MM-DD"; Date(s) usa UTC e vira dia anterior no fuso BR
  const dateOnly = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:$|[T\s])/);
  if (dateOnly) {
    const y = parseInt(dateOnly[1], 10);
    const m = parseInt(dateOnly[2], 10) - 1;
    const day = parseInt(dateOnly[3], 10);
    const local = new Date(y, m, day);
    return !isNaN(local.getTime()) ? local : null;
  }
  const d = new Date(s);
  return !isNaN(d.getTime()) ? d : null;
}

function prodespIsAtendimentoDateToday(raw) {
  const d = prodespParseAtendimentoDate(raw);
  if (!d) return false;
  const hoje =
    typeof PRODESP_DATA_HOJE !== "undefined" && PRODESP_DATA_HOJE
      ? prodespParseAtendimentoDate(PRODESP_DATA_HOJE)
      : new Date();
  if (!hoje) return false;
  return (
    d.getFullYear() === hoje.getFullYear() &&
    d.getMonth() === hoje.getMonth() &&
    d.getDate() === hoje.getDate()
  );
}

/** Preferência: flags da API (backend); fallback JS para compatibilidade. */
function prodespPermissaoEdicao(d) {
  if (!d) return { ok: false, msg: "Dados do atendimento indisponíveis." };
  if (prodespIsAdminUser()) return { ok: true };
  const clientCheck = prodespPodeEditarAtendimento(d);
  if (d.pode_editar === true) return { ok: true };
  return clientCheck;
}

/** Observações após encerramento (Quebra etc.): finalizado no dia permanece gravável. */
function prodespPodeSalvarObservacaoAtendimento(d) {
  if (!d) return { ok: false, msg: "Dados do atendimento indisponíveis." };
  if (prodespIsAdminUser()) return { ok: true };
  const st = (d.status_atendimento || d.status_atendimentos || "").trim();
  const raw = d.data_atendimento_raw || d.data_atendimento || d.data_atendimentos;
  const finalStatusesObs = ["Concluído", "Quebra", "Quebra TBRA", "Concluído Parcial"];
  if (finalStatusesObs.includes(st)) {
    if (!prodespIsAtendimentoDateToday(raw)) {
      return { ok: false, msg: "Edição permitida apenas para atendimentos da data atual." };
    }
    return { ok: true };
  }
  return prodespPodeEditarAtendimento(d);
}

/**
 * Exibe o ícone de lápis na grade (só cliente, linha completa da DataTable).
 * Não usar pode_editar da API aqui — ela pode divergir e esconder o botão indevidamente.
 */
function prodespLinhaPodeEditar(row) {
  if (!row) return false;
  const id = row.id_atendimento;
  if (id === null || id === undefined || id === "") return false;
  return prodespPodeEditarAtendimento(row).ok;
}

function prodespNormalizarNomeComparacao(nome) {
  return String(nome || "")
    .trim()
    .replace(/\s+/g, " ")
    .toLocaleLowerCase("pt-BR");
}

function prodespNomesAnalistaIguais(a, b) {
  const na = prodespNormalizarNomeComparacao(a);
  const nb = prodespNormalizarNomeComparacao(b);
  return !!(na && nb && na === nb);
}

const SUBSTATUS_AGUARDANDO_CLIENTE = "Aguardando Cliente";
const SUBSTATUS_AGUARDA_CONTRATADA = "Aguarda Contratada";
const SUBSTATUS_AGUARDA_LICENCA = "Aguarda Licença";
const STATUS_QUEBRA_TBRA = "Quebra TBRA";
const SUBSTATUS_QUEBRA_TBRA_SCI = "Quebra SCI";
const SUBSTATUS_QUEBRA_TBRA_TECNICA = "Quebra Técnica";
const PRODESP_SUBSTATUS_AGUARDA_EXTERNO = new Set([
  SUBSTATUS_AGUARDANDO_CLIENTE,
  SUBSTATUS_AGUARDA_CONTRATADA,
  SUBSTATUS_AGUARDA_LICENCA,
]);
/** Opções paralelas no select — perfil AG/GP/Supervisor (sem «Com Suporte»). */
const PRODESP_SUBSTATUS_PARALELOS_AG_GP = [
  SUBSTATUS_AGUARDANDO_CLIENTE,
  SUBSTATUS_AGUARDA_CONTRATADA,
  SUBSTATUS_AGUARDA_LICENCA,
];
/** Cliente, Contratada e Licença: Gestão e Implantação editam e movimentam. */
const PRODESP_SUBSTATUS_EDICAO_COMPARTILHADA = new Set([
  SUBSTATUS_AGUARDANDO_CLIENTE,
  SUBSTATUS_AGUARDA_CONTRATADA,
  SUBSTATUS_AGUARDA_LICENCA,
]);
/** Triagem e Aguarda Gestão: somente Gestão/AG/GP. */
const PRODESP_SUBSTATUS_EDICAO_SOMENTE_GESTAO = new Set([
  "Triagem",
  SUBSTATUS_AGUARDA_GESTAO,
]);
/** Única fila «Aguardando …» operacional no select AG/GP. */
const PRODESP_FILA_AGUARDANDO_GESTAO = SUBSTATUS_INICIAL_FILA;
/** Opções paralelas exibidas no select (Implantação / demais perfis). */
const PRODESP_SUBSTATUS_PARALELOS_SELECT = [
  ...PRODESP_SUBSTATUS_PARALELOS_AG_GP,
  SUBSTATUS_COM_SUPORTE,
];
const PRODESP_SUBSTATUS_QUEBRA_TBRA = [SUBSTATUS_QUEBRA_TBRA_SCI, SUBSTATUS_QUEBRA_TBRA_TECNICA];

/** Analistas MPLS (time terceiro) — alinhado a atendimento_business_rules.ANALISTAS_MPLS_TERCEIRO_OPCOES */
const PRODESP_ANALISTAS_MPLS_TERCEIRO = [
  "Cassio Jose Valeriano De Alcantara",
  "Diego Roberto Rosa Moreira Lima",
  "Edson Francisco Da Silva",
  "Jose Luciano Ferreira De Melo",
  "Persio De Oliveira Bomfim",
  "Rafael Rangel Tofolo",
  "Tiago Vinicius Costa De Souza",
  "Wagner Rodrigues Da Silva",
];
const PRODESP_ANALISTA_MPLS_OUTROS_VALUE = "__OUTROS__";
const PRODESP_SUBSTATUS_EM_CONFIG_MPLS = "Em Configuração do MPLS";
/** Evita confirm ao preencher MPLS programaticamente (load do modal). */
let prodespMplsSubstatusPromptSuppress = false;

/** Status usados no PRODESP — lista fixa no filtro ColumnControl (evita sumir com deferRender/paginação). */
const PRODESP_STATUS_FILTER_OPTIONS = [
  { label: "Agendado", value: "Agendado" },
  { label: "Em Atendimento", value: "Em Atendimento" },
  { label: "Concluído", value: "Concluído" },
  { label: "Concluído Parcial", value: "Concluído Parcial" },
  { label: "Quebra", value: "Quebra" },
  { label: "Quebra TBRA", value: "Quebra TBRA" },
];

const PRODESP_DT_COL_STATUS = 8;
const PRODESP_DT_COL_SUBSTATUS = 9;
const PRODESP_DT_COL_TEMPO_ETAPA = 14;
const PRODESP_DT_COL_TEMPO_VIDA = 15;
const PRODESP_DT_COL_ACOES = 16;
const PRODESP_DT_COL_LISTA = 17;

function prodespAtendimentosDtCol(name) {
  const cols = window.ProdespDtColumns && window.ProdespDtColumns.ATENDIMENTOS_COL;
  if (cols && cols[name] != null && cols[name] >= 0) {
    return cols[name];
  }
  const fallback = {
    STATUS: PRODESP_DT_COL_STATUS,
    SUBSTATUS: PRODESP_DT_COL_SUBSTATUS,
    TEMPO_ETAPA: PRODESP_DT_COL_TEMPO_ETAPA,
    TEMPO_VIDA: PRODESP_DT_COL_TEMPO_VIDA,
    ACOES: PRODESP_DT_COL_ACOES,
  };
  return fallback[name] != null ? fallback[name] : -1;
}

function prodespContratadaListCell(row) {
  if (!row) return "Não Informado";
  const planejada = (row.contratada_planejada_unidades || row.contratada_planejada || "").trim();
  const efetiva = (row.contratada || row.contratada_atendimentos || "").trim();
  const semAtendimento =
    row.id_atendimento === null ||
    row.id_atendimento === undefined ||
    row.id_atendimento === "";
  const st = (row.status_atendimento || row.status_atendimentos || "").trim();
  if (semAtendimento || st === "Agendado" || !st) {
    return planejada || efetiva || "Não Informado";
  }
  return efetiva || planejada || "Não Informado";
}

function prodespContratadaListCellHtml(row) {
  const text = prodespContratadaListCell(row);
  if (!text) return "";
  const esc = String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/"/g, "&quot;");
  return `<span class="prodesp-dt-contratada-text" title="${esc}">${esc}</span>`;
}

const PRODESP_SUBSTATUS_EM_CONFIG_REMOTA = "Em Configuração Remota";

/** Substatus que entram no «Total nas filas» (alinhado a app.py filas_substatuses). */
const PRODESP_FILAS_ATIVAS_SUBSTATUS = new Set([
  "Triagem",
  SUBSTATUS_AGUARDA_GESTAO,
  SUBSTATUS_COM_SUPORTE,
  "Aguardando Cliente",
  SUBSTATUS_AGUARDA_CONTRATADA,
  SUBSTATUS_AGUARDA_LICENCA,
  "Aguardando Config. Remota",
  "Em Configuração Remota",
  "Aguardando Config. MPLS",
  "Em Configuração do MPLS",
  "Aguardando Caderno de Teste",
  "Em Caderno de Teste",
]);

function prodespNormalizeAtendimentoListRow(row) {
  const r = row && typeof row === "object" ? { ...row } : {};
  const st = (r.status_atendimento || "").trim();
  const sub = (r.substatus_atendimento || "").trim();
  const semAtendimento =
    r.id_atendimento === null ||
    r.id_atendimento === undefined ||
    r.id_atendimento === "";
  if (!st && (semAtendimento || sub === "Sem atendimento iniciado")) {
    r.status_atendimento = "Agendado";
  }
  r._prodesp_pode_editar = prodespPodeEditarAtendimento(r).ok;
  return r;
}

/** Garante opção no select2 do ColumnControl (ex.: filtro pelo card Agendados). */
function prodespEnsureSearchListOptions(column, values) {
  const searchList = column && column.columnControl && column.columnControl.searchList();
  if (!searchList || !searchList.length) return;
  const list = Array.isArray(values) ? values : [values];
  list.forEach((val) => {
    if (val == null || val === "") return;
    const v = String(val);
    let found = false;
    searchList.find("option").each(function () {
      if (String($(this).val()) === v) found = true;
    });
    if (!found) {
      searchList.append(new Option(v, v, false, false));
    }
  });
}

function prodespRefreshStatusColumnSearchList(api) {
  if (!api || !api.column) return;
  prodespEnsureSearchListOptions(
    api.column(PRODESP_DT_COL_STATUS),
    PRODESP_STATUS_FILTER_OPTIONS.map((o) => o.value)
  );
}

let prodespCardExtSearchFn = null;
const prodespListIsAdmin = Number(window.PRODESP_ADMIN_USER || 0) === 1;
/** Admin: completo nativo; demais: só fila ativa. */
let prodespListScope = prodespListIsAdmin ? "completo" : "fila";
let prodespListCardFilter = "";
const prodespListServerSide =
  window.PRODESP_LIST_SERVER_SIDE === true ||
  window.PRODESP_LIST_SERVER_SIDE === 1 ||
  String(window.PRODESP_LIST_SERVER_SIDE || "0") === "1";

function prodespListDefaultScope() {
  return prodespListIsAdmin ? "completo" : "fila";
}

function prodespListEffectiveScope() {
  if (prodespListIsAdmin) {
    const chk = document.getElementById("prodespListSomenteFilaAtiva");
    if (chk && chk.checked) return "fila";
    return "completo";
  }
  return prodespListScope || "fila";
}

function prodespListSetCardFilter({ filterMode, statusFilter, substatus } = {}) {
  prodespListCardFilter = "";
  if (filterMode === "migrados") {
    prodespListCardFilter = "mode:migrados";
  } else if (filterMode === "aguardando-cliente") {
    prodespListCardFilter = "mode:aguardando-cliente";
  } else if (filterMode === "aguarda-contratada") {
    prodespListCardFilter = "mode:aguarda-contratada";
  } else if (filterMode === "aguarda-licenca") {
    prodespListCardFilter = "mode:aguarda-licenca";
  } else if (filterMode === "aguarda-gestao") {
    prodespListCardFilter = "mode:aguarda-gestao";
  } else if (filterMode === "filas-ativas") {
    prodespListCardFilter = "mode:filas-ativas";
  } else if (statusFilter === "Agendado") {
    prodespListCardFilter = "mode:agendados";
  } else if (statusFilter) {
    prodespListCardFilter = "status:" + statusFilter;
  } else if (substatus) {
    prodespListCardFilter = "substatus:" + substatus;
  }
}

function prodespRowIsAgendado(row) {
  if (!row) return false;
  const st = (row.status_atendimento || "").trim();
  const sub = (row.substatus_atendimento || "").trim();
  const semId =
    row.id_atendimento === null ||
    row.id_atendimento === undefined ||
    row.id_atendimento === "";
  if (st === "Agendado") return true;
  return semId && (sub === "Sem atendimento iniciado" || !sub);
}

function prodespIsSubstatusAguardaContratada(sub) {
  const s = (sub || "").trim();
  return s === SUBSTATUS_AGUARDA_CONTRATADA;
}

function prodespDestinosSubstatusAgGp(oldSubstatus) {
  const gestao = new Set([SUBSTATUS_AGUARDA_GESTAO, "Triagem"]);
  const filaAguardandoGestao = new Set([PRODESP_FILA_AGUARDANDO_GESTAO]);
  const paralelos = new Set(
    prodespIsAgendamentoOuGp()
      ? PRODESP_SUBSTATUS_PARALELOS_AG_GP
      : PRODESP_SUBSTATUS_PARALELOS_SELECT
  );
  const old = (oldSubstatus || "").trim();
  if (!old) {
    return new Set([PRODESP_FILA_AGUARDANDO_GESTAO, ...gestao, ...paralelos]);
  }
  if (gestao.has(old) || old === SUBSTATUS_AGUARDA_GESTAO) {
    return new Set([...gestao, ...paralelos, ...filaAguardandoGestao]);
  }
  if (old === PRODESP_FILA_AGUARDANDO_GESTAO) {
    return new Set([...gestao, PRODESP_FILA_AGUARDANDO_GESTAO, ...paralelos]);
  }
  if (paralelos.has(old)) {
    return new Set([...gestao, ...paralelos, ...filaAguardandoGestao]);
  }
  return new Set();
}

function prodespMensagemTransicaoSubstatusAgGpNegada(oldSub, newSub) {
  const oldLabel =
    typeof prodespNormalizarSubstatusFluxo === "function"
      ? prodespNormalizarSubstatusFluxo(oldSub || SUBSTATUS_AGUARDA_GESTAO)
      : oldSub || SUBSTATUS_AGUARDA_GESTAO;
  return (
    `Seu perfil (Agendamento, SUPERVISORES ou GP) não pode mover o substatus ` +
    `de «${oldLabel}» para «${newSub}». ` +
    "Envie apenas para filas «Aguardando …» ou pendências paralelas; " +
    "etapas «Em …» são assumidas pelo time de Implantação."
  );
}

function prodespIsStatusFinalEncerramento(status) {
  const s = (status || "").trim();
  return ["Concluído", "Quebra", "Quebra TBRA", "Concluído Parcial"].includes(s);
}

/** Substatus de encerramento «Quebra» / «Quebra TBRA» (sem depender de helpers definidos mais abaixo). */
function prodespIsSubstatusEncerramentoQuebra(sub, statusOpt) {
  const s = (sub || "").trim();
  const st = (statusOpt || "").trim();
  if (st === "Quebra TBRA") {
    return s === "Quebra SCI" || s === "Quebra Técnica";
  }
  if (st === "Quebra" || !st) {
    return s.startsWith("Quebra") && s !== "Quebra SCI" && s !== "Quebra Técnica";
  }
  return false;
}

function prodespValidarTransicaoSubstatusAgGp(oldSub, newSub, statusOpt) {
  if (!prodespIsAgendamentoOuGp()) return null;
  const status = (statusOpt || "").trim();
  if (prodespIsStatusFinalEncerramento(status)) return null;
  const old = (oldSub || "").trim();
  const neu = (newSub || "").trim();
  if (!neu || neu === old) return null;
  if (prodespIsSubstatusEncerramentoQuebra(neu, status)) {
    const origemEncerramento = old || SUBSTATUS_INICIAL_FILA;
    const allowedEncerramento = prodespDestinosSubstatusAgGp(origemEncerramento);
    if (allowedEncerramento.size > 0) return null;
  }
  const origem = old || SUBSTATUS_AGUARDA_GESTAO;
  const allowed = prodespDestinosSubstatusAgGp(origem);
  if (allowed.has(neu)) return null;
  if (
    (neu === SUBSTATUS_AGUARDA_GESTAO || neu === "Triagem") &&
    allowed.has(SUBSTATUS_AGUARDA_GESTAO)
  ) {
    return null;
  }
  return prodespMensagemTransicaoSubstatusAgGpNegada(origem, neu);
}

function prodespMensagemEdicaoRestritaAgGp() {
  return (
    `Seu perfil (Agendamento, SUPERVISORES ou GP) só pode editar em «${SUBSTATUS_AGUARDA_GESTAO}», ` +
    `«${PRODESP_FILA_AGUARDANDO_GESTAO}», ou pendências paralelas ` +
    `(«${SUBSTATUS_AGUARDA_LICENCA}», «${SUBSTATUS_AGUARDA_CONTRATADA}», ` +
    `«${SUBSTATUS_AGUARDANDO_CLIENTE}»).`
  );
}

function prodespMensagemEdicaoApenasGestao() {
  return (
    "Este substatus é exclusivo do time de Agendamento/Gestão. " +
    "Somente perfis de Agendamento, GP ou SUPERVISORES podem editar ou movimentar."
  );
}

/** Substatus já persistido no modal (último save bem-sucedido). */
function prodespSubstatusPersistidoModal(mode) {
  if (mode === "edit") {
    return (
      editPersistedSubstatus ||
      (originalData.substatus_atendimento || originalData.substatus_atendimentos || "")
    ).trim();
  }
  return (
    createPersistedSubstatus ||
    createFlowBaselineSubstatus ||
    SUBSTATUS_INICIAL_FILA
  ).trim();
}

/**
 * Permissão para salvar/auto-save no modal: permite Implantação enviar para Aguarda Gestão
 * (entrada na fila Gestão) e ignora re-save silencioso quando o substatus já foi persistido.
 */
function prodespResolvePermEdicaoModalSalvar(data, mode) {
  if (!data) return { ok: false, msg: "Dados do atendimento indisponíveis." };
  if (prodespIsAdminUser()) return { ok: true };

  const prefix = mode === "edit" ? "edit" : "create";
  const domSub = (document.getElementById(`${prefix}Substatus`)?.value || "").trim();
  const persistedSub = prodespSubstatusPersistidoModal(mode);

  if (
    typeof prodespIsEntradaAguardaGestao === "function" &&
    prodespIsEntradaAguardaGestao(persistedSub, domSub) &&
    !prodespIsAgendamentoOuGp()
  ) {
    return { ok: true };
  }

  if (domSub && domSub === persistedSub && PRODESP_SUBSTATUS_EDICAO_SOMENTE_GESTAO.has(domSub)) {
    return { ok: true, noop: true };
  }

  const rowForPerm = {
    ...data,
    substatus_atendimento: persistedSub,
    substatus_atendimentos: persistedSub,
  };
  return prodespPermissaoEdicao(rowForPerm);
}

function prodespRowInFilasAtivas(row) {
  if (!row) return false;
  const sub = (row.substatus_atendimento || "").trim();
  return PRODESP_FILAS_ATIVAS_SUBSTATUS.has(sub);
}

function prodespSetCardExtSearch(fn) {
  if (prodespCardExtSearchFn) {
    const idx = $.fn.dataTable.ext.search.indexOf(prodespCardExtSearchFn);
    if (idx >= 0) {
      $.fn.dataTable.ext.search.splice(idx, 1);
    }
  }
  prodespCardExtSearchFn = fn;
  if (fn) {
    $.fn.dataTable.ext.search.push(fn);
  }
}

function prodespClearColumnControlUi(dtApi) {
  if (!dtApi) return;
  if (typeof dtApi.columns().ccSearchClear === "function") {
    dtApi.columns().ccSearchClear();
    return;
  }
  dtApi.columns().every(function () {
    const sl = this.columnControl && this.columnControl.searchList();
    if (sl && sl.length) {
      sl.val([]).trigger("change.select2", [true]);
    }
  });
}

/** Filtro de coluna via column.search (não deixa o searchList do ColumnControl sobrescrever). */
function prodespApplyDtColumnFilter(column, value, useRegex) {
  if (!column) return;
  const sl = column.columnControl && column.columnControl.searchList();
  if (sl && sl.length) {
    sl.val([]).trigger("change.select2", [true]);
  }
  if (value == null || value === "") {
    column.search("", false, false);
    return;
  }
  const v = String(value);
  if (prodespListServerSide) {
    column.search(v, false, false);
    if (sl && sl.length) {
      prodespEnsureSearchListOptions(column, v);
      sl.val([v]).trigger("change.select2", [true]);
    }
    column.draw();
    return;
  }
  const term = useRegex ? v : "^" + $.fn.dataTable.util.escapeRegex(v) + "$";
  column.search(term, useRegex || true, false);
  if (sl && sl.length) {
    prodespEnsureSearchListOptions(column, v);
    sl.val([v]).trigger("change.select2", [true]);
  }
}

function prodespClearAllTableFilters(dtApi) {
  if (!dtApi) return;
  prodespListCardFilter = "";
  prodespListScope = prodespListDefaultScope();
  const chkFila = document.getElementById("prodespListSomenteFilaAtiva");
  if (chkFila) chkFila.checked = false;
  prodespSetCardExtSearch(null);
  dtApi.search("");
  dtApi.columns().search("");
  prodespClearColumnControlUi(dtApi);
  if (prodespListServerSide) {
    dtApi.ajax.reload();
  } else {
    dtApi.draw();
  }
}

/** Envia buscas do ColumnControl no payload server-side (quando PRODESP_LIST_SERVER_SIDE=1). */
function prodespListSyncColumnControlToAjax(d, dtSettings) {
  if (!d.columns || !dtSettings) return;
  const api = new $.fn.dataTable.Api(dtSettings);
  api.columns().every(function () {
    const colIdx = this.index();
    const cc = this.columnControl;
    if (!cc || typeof cc.searchList !== "function") return;
    const sl = cc.searchList();
    if (!sl || !sl.length) return;
    let selected = sl.val();
    if (selected == null || selected === "" || (Array.isArray(selected) && !selected.length)) {
      return;
    }
    const values = Array.isArray(selected) ? selected : [selected];
    const term = values.map(String).filter(Boolean).join("|");
    if (d.columns[colIdx] && d.columns[colIdx].search) {
      d.columns[colIdx].search.value = term;
      d.columns[colIdx].search.regex = false;
    }
  });
}

/** ColumnControl + serverSide: sincroniza searchList → column.search (MySQL). */
function prodespBindColumnControlServerSide(dtApi) {
  if (!prodespListServerSide || !dtApi || !dtApi.columnControl) return;
  dtApi.columns().every(function (colIdx) {
    const cc = this.columnControl;
    if (!cc || typeof cc.searchList !== "function") return;
    const sl = cc.searchList();
    if (!sl || !sl.length) return;
    sl.off("change.prodespListSs select2:select.prodespListSs select2:unselect.prodespListSs");
    const sync = function () {
      prodespListCardFilter = "";
      let selected = sl.val();
      if (selected == null || selected === "") {
        dtApi.column(colIdx).search("", false, false);
      } else {
        const values = Array.isArray(selected) ? selected : [selected];
        const term = values.map(String).filter(Boolean).join("|");
        dtApi.column(colIdx).search(term, false, false);
      }
      dtApi.draw();
    };
    sl.on("change.prodespListSs", sync);
    sl.on("select2:select.prodespListSs select2:unselect.prodespListSs", sync);
  });
}

/** ColumnControl + serverSide: busca vai ao MySQL (texto plano, sem regex). */
function prodespBindServerSideColumnSearch(dtApi) {
  if (!prodespListServerSide || !dtApi) return;
  dtApi.off("column-search.dt.prodespList");
  dtApi.on("column-search.dt.prodespList", function (_e, settings, colIdx) {
    if (settings.nTable.id !== "tabela-atendimentos") return;
    prodespListCardFilter = "";
    const col = dtApi.column(colIdx);
    const cur = col.search();
    if (cur && /[\^$()]/.test(cur)) {
      const plain = String(cur).replace(/^\^|\$$/g, "").replace(/^\(|\)$/g, "");
      col.search(plain.split("|")[0] || "", false, false);
    }
  });
}

/** Regras alinhadas ao backend (_prodesp_validar_edicao_atendimento). */
function prodespEhFilaAguardando(sub) {
  const s = (sub || "").trim();
  return s.startsWith("Aguardando") && s !== SUBSTATUS_AGUARDANDO_CLIENTE;
}

function prodespIndiceFluxoSubstatus(sub) {
  return PRODESP_FLUXO_SUBSTATUS_ORDEM.indexOf(prodespNormalizarSubstatusFluxo(sub));
}

function prodespPrecisaAnalistaMplsTerceiro(oldSubstatus, newSubstatus) {
  const oldS = (oldSubstatus || "").trim();
  const newS = (newSubstatus || "").trim();
  if (newS === PRODESP_SUBSTATUS_EM_CONFIG_MPLS && newS !== oldS) return true;
  if (oldS === PRODESP_SUBSTATUS_EM_CONFIG_MPLS && newS !== oldS) {
    const io = prodespIndiceFluxoSubstatus(oldS);
    const in_ = prodespIndiceFluxoSubstatus(newS);
    return io >= 0 && in_ > io;
  }
  return false;
}

function prodespMensagemAnalistaMplsObrigatorio(oldSubstatus, newSubstatus) {
  const oldS = (oldSubstatus || "").trim();
  const newS = (newSubstatus || "").trim();
  if (newS === PRODESP_SUBSTATUS_EM_CONFIG_MPLS && newS !== oldS) {
    return "Para entrar em Em Configuração do MPLS, informe o analista MPLS (time terceiro)";
  }
  return "Para avançar após Em Configuração do MPLS, informe o analista MPLS (time terceiro)";
}

function prodespAnalistaMplsTerceiroValido(valor) {
  return ((valor || "").trim().length >= 3);
}

function prodespInitAnalistaMplsSelectOptions(context) {
  const sel = document.getElementById(`${context}AnalistaMplsSelect`);
  if (!sel || sel.dataset.prodespMplsInit === "1") return;
  PRODESP_ANALISTAS_MPLS_TERCEIRO.forEach((nome) => {
    sel.add(new Option(nome, nome));
  });
  sel.add(new Option("Outros", PRODESP_ANALISTA_MPLS_OUTROS_VALUE));
  sel.dataset.prodespMplsInit = "1";
}

function prodespGetAnalistaMplsValor(context) {
  const hidden = document.getElementById(`${context}AnalistaMplsAtendimentos`);
  return (hidden?.value || "").trim();
}

function prodespSyncAnalistaMplsHidden(context) {
  const sel = document.getElementById(`${context}AnalistaMplsSelect`);
  const outros = document.getElementById(`${context}AnalistaMplsOutros`);
  const hidden = document.getElementById(`${context}AnalistaMplsAtendimentos`);
  if (!hidden) return;
  if (sel && !sel.classList.contains("d-none")) {
    if (sel.value === PRODESP_ANALISTA_MPLS_OUTROS_VALUE) {
      hidden.value = (outros?.value || "").trim();
    } else {
      hidden.value = (sel.value || "").trim();
    }
  }
}

function prodespSetAnalistaMplsValor(context, valor) {
  prodespMplsSubstatusPromptSuppress = true;
  try {
    prodespInitAnalistaMplsSelectOptions(context);
    const v = (valor || "").trim();
    const hidden = document.getElementById(`${context}AnalistaMplsAtendimentos`);
    const sel = document.getElementById(`${context}AnalistaMplsSelect`);
    const outros = document.getElementById(`${context}AnalistaMplsOutros`);
    const display = document.getElementById(`${context}AnalistaMplsDisplay`);
    if (hidden) hidden.value = v;
    if (!sel) return;
    if (v && PRODESP_ANALISTAS_MPLS_TERCEIRO.includes(v)) {
      sel.value = v;
      if (outros) {
        outros.value = "";
        outros.classList.add("d-none");
      }
    } else if (v) {
      sel.value = PRODESP_ANALISTA_MPLS_OUTROS_VALUE;
      if (outros) {
        outros.value = v;
        outros.classList.remove("d-none");
      }
    } else {
      sel.value = "";
      if (outros) {
        outros.value = "";
        outros.classList.add("d-none");
      }
    }
    if (display && display.classList.contains("prodesp-analista-mpls-display") && !display.classList.contains("d-none")) {
      display.textContent = v || "—";
    }
    prodespSyncAnalistaMplsHidden(context);
  } finally {
    prodespMplsSubstatusPromptSuppress = false;
  }
}

function prodespUpdateAnalistaMplsUi(context, substatus, opts = {}) {
  prodespInitAnalistaMplsSelectOptions(context);
  const sub = (substatus || "").trim();
  const emMplsOuFila =
    sub === PRODESP_SUBSTATUS_EM_CONFIG_MPLS || sub === "Aguardando Config. MPLS";
  const formDisabled = opts.formDisabled === true;
  const adminOverride = prodespIsAdminUser() && !formDisabled;
  const canEdit = (emMplsOuFila && !formDisabled) || adminOverride;
  const sel = document.getElementById(`${context}AnalistaMplsSelect`);
  const outros = document.getElementById(`${context}AnalistaMplsOutros`);
  const display = document.getElementById(`${context}AnalistaMplsDisplay`);
  if (!sel || !display) return;

  if (canEdit) {
    sel.classList.remove("d-none");
    display.classList.add("d-none");
    sel.disabled = false;
    if (outros) {
      const showOutros = sel.value === PRODESP_ANALISTA_MPLS_OUTROS_VALUE;
      outros.classList.toggle("d-none", !showOutros);
      outros.disabled = !showOutros;
      if (showOutros) outros.readOnly = false;
    }
  } else {
    sel.classList.add("d-none");
    sel.disabled = true;
    if (outros) {
      outros.classList.add("d-none");
      outros.disabled = true;
    }
    display.classList.remove("d-none");
    display.textContent = prodespGetAnalistaMplsValor(context) || "—";
  }
  prodespSyncAnalistaMplsHidden(context);
}

function prodespConfirmIrParaEmConfigMpls(analistaNome) {
  const modalEl = document.getElementById("prodespConfirmMplsModal");
  const analistaEl = document.getElementById("prodespConfirmMplsAnalista");
  const subNomeEl = document.getElementById("prodespConfirmMplsSubstatusNome");
  const btnSim = document.getElementById("prodespConfirmMplsSim");
  const btnNao = document.getElementById("prodespConfirmMplsNao");
  if (!modalEl || !btnSim || !btnNao) {
    const fallback =
      `Deseja enviar este atendimento para «${PRODESP_SUBSTATUS_EM_CONFIG_MPLS}»?\n\n` +
      `Analista MPLS: ${analistaNome}`;
    return Promise.resolve(window.confirm(fallback));
  }

  if (analistaEl) analistaEl.textContent = analistaNome || "—";
  if (subNomeEl) subNomeEl.textContent = PRODESP_SUBSTATUS_EM_CONFIG_MPLS;

  const bsModal = prodespShowStackedModal(modalEl);

  return new Promise((resolve) => {
    let settled = false;
    const done = (ok) => {
      if (settled) return;
      settled = true;
      btnSim.removeEventListener("click", onSim);
      btnNao.removeEventListener("click", onNao);
      modalEl.removeEventListener("hidden.bs.modal", onHidden);
      bsModal.hide();
      resolve(ok);
    };
    const onSim = () => done(true);
    const onNao = () => done(false);
    const onHidden = () => done(false);
    btnSim.addEventListener("click", onSim);
    btnNao.addEventListener("click", onNao);
    modalEl.addEventListener("hidden.bs.modal", onHidden);
  });
}

/**
 * Confirmação dos Dados Field antes de criar «Em Atendimento».
 * @returns {Promise<{confirmed: boolean, contratada?: string, field?: string, contato_field?: string}>}
 */
function prodespConfirmDadosFieldAntesIniciar() {
  const modalEl = document.getElementById("prodespConfirmDadosFieldModal");
  const selContratada = document.getElementById("confirmDadosFieldContratada");
  const inpField = document.getElementById("confirmDadosFieldField");
  const inpContato = document.getElementById("confirmDadosFieldContato");
  const btnOk = document.getElementById("prodespConfirmDadosFieldConfirmar");
  const btnCancel = document.getElementById("prodespConfirmDadosFieldCancelar");

  const readCreate = () => ({
    contratada: (document.getElementById("createContratada")?.value || "").trim(),
    field: (document.getElementById("createField")?.value || "").trim(),
    contato_field: (document.getElementById("createContatoField")?.value || "").replace(/\D/g, ""),
  });

  if (!modalEl || !selContratada || !inpField || !inpContato || !btnOk || !btnCancel) {
    const cur = readCreate();
    const ok = !!(cur.contratada && cur.field && cur.contato_field);
    if (!ok) {
      showToast(
        "Para iniciar «Em Atendimento», preencha Contratada, Field e Contato Field.",
        "warning"
      );
      return Promise.resolve({ confirmed: false });
    }
    const fallback =
      "Confirmar Dados Field e iniciar o atendimento?\n\n" +
      `Contratada: ${cur.contratada}\nField: ${cur.field}\nContato: ${cur.contato_field}`;
    return Promise.resolve(
      window.confirm(fallback)
        ? { confirmed: true, ...cur }
        : { confirmed: false }
    );
  }

  const cur = readCreate();
  prodespEnsureContratadaOption("confirmDadosFieldContratada", cur.contratada);
  selContratada.value = cur.contratada || "";
  inpField.value = cur.field || "";
  inpContato.value = cur.contato_field || "";
  if (typeof aplicarMascaraTelefone === "function" && !inpContato.dataset.maskBound) {
    aplicarMascaraTelefone(inpContato);
    inpContato.dataset.maskBound = "1";
  }

  const bsModal = prodespShowStackedModal(modalEl);

  return new Promise((resolve) => {
    let settled = false;
    const done = (payload) => {
      if (settled) return;
      settled = true;
      btnOk.removeEventListener("click", onOk);
      btnCancel.removeEventListener("click", onCancel);
      modalEl.removeEventListener("hidden.bs.modal", onHidden);
      bsModal.hide();
      resolve(payload);
    };
    const onOk = () => {
      const contratada = (selContratada.value || "").trim();
      const field = (inpField.value || "").trim();
      const contato_field = (inpContato.value || "").replace(/\D/g, "");
      const missing = [];
      if (!contratada || (selContratada.options[selContratada.selectedIndex]?.disabled)) {
        missing.push("Contratada");
      }
      if (!field) missing.push("Field");
      if (!contato_field) missing.push("Contato Field");
      if (missing.length) {
        showToast(
          `Para iniciar o atendimento, preencha: ${missing.join(", ")}.`,
          "warning"
        );
        return;
      }
      done({ confirmed: true, contratada, field, contato_field });
    };
    const onCancel = () => done({ confirmed: false });
    const onHidden = () => done({ confirmed: false });
    btnOk.addEventListener("click", onOk);
    btnCancel.addEventListener("click", onCancel);
    modalEl.addEventListener("hidden.bs.modal", onHidden);
  });
}

function prodespApplyDadosFieldConfirmadosAoCreate(dados) {
  if (!dados) return;
  if (dados.contratada != null) {
    prodespEnsureContratadaOption("createContratada", dados.contratada);
    const el = document.getElementById("createContratada");
    if (el) el.value = dados.contratada;
  }
  if (dados.field != null) {
    const el = document.getElementById("createField");
    if (el) el.value = dados.field;
  }
  if (dados.contato_field != null) {
    const el = document.getElementById("createContatoField");
    if (el) el.value = dados.contato_field;
  }
}

async function prodespMaybeIrParaEmConfigMplsAposAnalista(context) {
  if (prodespMplsSubstatusPromptSuppress) return;

  const subEl = document.getElementById(`${context}Substatus`);
  const statusEl = document.getElementById(`${context}Status`);
  if (!subEl || subEl.disabled) return;

  const subAtual = (subEl.value || "").trim();
  if (subAtual === PRODESP_SUBSTATUS_EM_CONFIG_MPLS) return;

  prodespSyncAnalistaMplsHidden(context);
  const analista = prodespGetAnalistaMplsValor(context);
  if (!prodespAnalistaMplsTerceiroValido(analista)) return;

  const confirmou = await prodespConfirmIrParaEmConfigMpls(analista);
  if (!confirmou) return;

  const oldSub = (
    (context === "edit"
      ? editPersistedSubstatus || editFlowBaselineSubstatus
      : createPersistedSubstatus || createFlowBaselineSubstatus) || subAtual
  ).trim();

  const mplsMissing = prodespValidateAnalistaMplsTerceiro(
    context,
    oldSub,
    PRODESP_SUBSTATUS_EM_CONFIG_MPLS
  );
  if (mplsMissing.length > 0) {
    prodespNotifyValidationBlocked(
      mplsMissing,
      prodespMensagemAnalistaMplsObrigatorio(oldSub, PRODESP_SUBSTATUS_EM_CONFIG_MPLS)
    );
    return;
  }

  prodespMplsSubstatusPromptSuppress = true;
  try {
    subEl.value = PRODESP_SUBSTATUS_EM_CONFIG_MPLS;
    if (statusEl) {
      populateSubstatus(
        subEl,
        statusEl.value,
        PRODESP_SUBSTATUS_EM_CONFIG_MPLS,
        undefined,
        undefined,
        context
      );
    }
    subEl.dispatchEvent(new Event("change", { bubbles: true }));
    prodespUpdateAnalistaMplsUi(context, PRODESP_SUBSTATUS_EM_CONFIG_MPLS, {
      formDisabled: false,
    });
  } finally {
    prodespMplsSubstatusPromptSuppress = false;
  }
}

async function prodespOnAnalistaMplsSelectChange(context) {
  const sel = document.getElementById(`${context}AnalistaMplsSelect`);
  const outros = document.getElementById(`${context}AnalistaMplsOutros`);
  if (!sel) return;
  const showOutros = sel.value === PRODESP_ANALISTA_MPLS_OUTROS_VALUE;
  if (outros) {
    outros.classList.toggle("d-none", !showOutros);
    outros.disabled = !showOutros;
    if (!showOutros) outros.value = "";
    else outros.focus();
  }
  prodespSyncAnalistaMplsHidden(context);
  const hidden = document.getElementById(`${context}AnalistaMplsAtendimentos`);
  if (hidden) hidden.dispatchEvent(new Event("input", { bubbles: true }));

  if (sel.value && sel.value !== PRODESP_ANALISTA_MPLS_OUTROS_VALUE) {
    await prodespMaybeIrParaEmConfigMplsAposAnalista(context);
  }
}

function prodespValidateAnalistaMplsTerceiro(context, oldSubstatus, newSubstatus) {
  if (!prodespPrecisaAnalistaMplsTerceiro(oldSubstatus, newSubstatus)) return [];
  prodespSyncAnalistaMplsHidden(context);
  const val = prodespGetAnalistaMplsValor(context);
  if (!prodespAnalistaMplsTerceiroValido(val)) {
    const sel = document.getElementById(`${context}AnalistaMplsSelect`);
    if (sel) sel.classList.add("is-invalid");
    return ["Analista MPLS (terceiro)"];
  }
  const sel = document.getElementById(`${context}AnalistaMplsSelect`);
  if (sel) sel.classList.remove("is-invalid");
  return [];
}

function prodespResolverDonoEdicao(d) {
  if (!d) return { etapa: null, dono: "" };
  const sub = (d.substatus_atendimento || d.substatus_atendimentos || "").trim();

  if (PRODESP_SUBSTATUS_EDICAO_COMPARTILHADA.has(sub)) {
    return { etapa: null, dono: "" };
  }

  if (prodespEhFilaAguardando(sub) || sub === PRODESP_SUBSTATUS_EM_CONFIG_MPLS) {
    return { etapa: null, dono: "" };
  }

  const analistaPorEtapa = {
    Triagem: (d.analista_atuante || d.analista_atuante_atendimentos || "").trim(),
    "Em Configuração Remota": (d.analista_configuracao || d.analista_configuracao_atendimentos || "").trim(),
    "Em Caderno de Teste": (d.analista_caderno_teste || d.analista_caderno_teste_atendimentos || "").trim(),
  };
  const etapasAtivas = Object.keys(analistaPorEtapa);

  if (PRODESP_SUBSTATUS_AGUARDA_EXTERNO.has(sub)) {
    for (let i = etapasAtivas.length - 1; i >= 0; i--) {
      const et = etapasAtivas[i];
      if (analistaPorEtapa[et]) return { etapa: et, dono: analistaPorEtapa[et] };
    }
    return { etapa: SUBSTATUS_AGUARDA_GESTAO, dono: analistaPorEtapa[SUBSTATUS_AGUARDA_GESTAO] || analistaPorEtapa.Triagem };
  }

  if (!etapasAtivas.includes(sub)) {
    return { etapa: null, dono: "" };
  }
  return { etapa: sub, dono: analistaPorEtapa[sub] || "" };
}

function prodespPodeEditarAtendimento(d) {
  if (!d) return { ok: false, msg: "Dados do atendimento indisponíveis." };
  if (prodespIsAdminUser()) return { ok: true };

  const st = (d.status_atendimento || d.status_atendimentos || "").trim();
  const sub = (d.substatus_atendimento || d.substatus_atendimentos || "").trim();
  const raw = d.data_atendimento_raw || d.data_atendimento || d.data_atendimentos;

  const allowedAgGp = new Set([
    "Triagem",
    SUBSTATUS_AGUARDA_GESTAO,
    PRODESP_FILA_AGUARDANDO_GESTAO,
    ...PRODESP_SUBSTATUS_PARALELOS_AG_GP,
  ]);

  if (prodespIsAgendamentoOuGp()) {
    if (!allowedAgGp.has(sub)) {
      return {
        ok: false,
        msg: prodespMensagemEdicaoRestritaAgGp(),
      };
    }
    if (st !== "Em Atendimento") {
      return { ok: false, msg: "Edição permitida apenas para atendimentos em andamento." };
    }
    if (!prodespIsAtendimentoDateToday(raw)) {
      return { ok: false, msg: "Edição permitida apenas para atendimentos da data atual." };
    }
    return { ok: true };
  }

  if (st !== "Em Atendimento") {
    return { ok: false, msg: "Edição permitida apenas para atendimentos em andamento." };
  }
  if (!prodespIsAtendimentoDateToday(raw)) {
    return { ok: false, msg: "Edição permitida apenas para atendimentos da data atual." };
  }

  if (PRODESP_SUBSTATUS_EDICAO_SOMENTE_GESTAO.has(sub)) {
    return { ok: false, msg: prodespMensagemEdicaoApenasGestao() };
  }

  if (PRODESP_SUBSTATUS_EDICAO_COMPARTILHADA.has(sub)) {
    return { ok: true };
  }

  if (prodespEhFilaAguardando(sub) || sub === PRODESP_SUBSTATUS_EM_CONFIG_MPLS) {
    return { ok: true };
  }

  const etapasAtivas = new Set([
    "Triagem",
    SUBSTATUS_AGUARDA_GESTAO,
    "Em Configuração Remota",
    "Em Caderno de Teste",
  ]);
  const { etapa, dono } = prodespResolverDonoEdicao(d);
  const eu = (typeof USUARIO_LOGADO !== "undefined" ? USUARIO_LOGADO : "").trim();

  if (etapasAtivas.has(sub) && !dono) {
    return {
      ok: false,
      msg:
        `A etapa '${sub}' ainda não foi assumida por um analista. ` +
        "Altere o substatus para assumir o atendimento antes de editar outros campos.",
    };
  }
  if (dono && eu && !prodespNomesAnalistaIguais(dono, eu)) {
    return {
      ok: false,
      msg: `Somente o analista '${dono}' pode editar este atendimento na etapa '${etapa}'.`,
    };
  }

  return { ok: true };
}

let motivosForaPadraoOriginalEdit = [];

/** i18n pt-BR — PortalDt (fallback local se o script do core não carregou). */
function prodespAtendimentosDataTableLanguage() {
  const lang =
    window.PortalDt && typeof window.PortalDt.languagePtBr === "function"
      ? window.PortalDt.languagePtBr()
      : {
          emptyTable: "Nenhum registro encontrado",
          info: "Mostrando de _START_ até _END_ de _TOTAL_ registros",
          infoEmpty: "Mostrando 0 até 0 de 0 registro(s)",
          infoFiltered: "(Filtrados de _MAX_ registros)",
          infoThousands: ".",
          lengthMenu: "Exibir _MENU_ resultados por página",
          loadingRecords: "Carregando...",
          processing: "Carregando...",
          search: "🔍",
          searchPlaceholder: "Buscar registros",
          zeroRecords: "Nenhum registro encontrado",
          decimal: ",",
          thousands: ".",
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
  lang.aria = {
    sortAscending: ": Ordenar colunas de forma ascendente",
    sortDescending: ": Ordenar colunas de forma descendente",
  };
  return lang;
}

/** ColumnControl padrão (core PortalDt). */
function prodespDtCcSearchList() {
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

function prodespDtCcOrderOnly() {
  if (window.PortalDt && typeof window.PortalDt.ccOrderOnly === "function") {
    return window.PortalDt.ccOrderOnly();
  }
  return [["orderAsc", "orderDesc", "orderClear"]];
}

function prodespDtOrderingSilent() {
  if (window.PortalDt && typeof window.PortalDt.orderingSilent === "function") {
    return window.PortalDt.orderingSilent();
  }
  return { indicators: false, handler: false };
}

$(function () {
  // PLUGIN DATATABLES: Ordenação de data no formato dd/mm/yyyy 
  $.fn.dataTable.ext.type.order['date-br-pre'] = function (d) {
    if (!d) return 0;
    var parts = d.split('/');
    if (parts.length < 3) return 0;
    return parseInt(parts[2] + parts[1] + parts[0], 10);
  };

  // 📊 Inicialização do DataTable (somente na tela de Atendimentos)
  const $tabelaAtendimentos = $("#tabela-atendimentos");
  if (!$tabelaAtendimentos.length) {
    return;
  }
  let prodespFilaTimeOffset = 0;
  const table = $tabelaAtendimentos.DataTable({
    serverSide: prodespListServerSide,
    ajax: {
      url: "/prodesp/api/atendimentos_list",
      data: function (d) {
        d.scope = prodespListEffectiveScope();
        d.card_filter = prodespListCardFilter || "";
        if (prodespListServerSide) {
          prodespListSyncColumnControlToAjax(d, this);
        }
      },
      dataSrc: function (json) {
        if (json && json.resumo) updateTopCards(json.resumo);
        if (json && json.server_time) {
          prodespFilaTimeOffset = Date.now() - new Date(json.server_time).getTime();
        }
        if (json && json.data_revision != null && window.prodespFilaDtSync) {
          window.prodespFilaDtSync.setRevision(json.data_revision);
        }
        if (json && json.data_revision != null) {
          window.prodespFilaLastDataRevision = Number(json.data_revision);
        }
        const raw = json.data || json.atendimentos || [];
        const rows = raw.map(prodespNormalizeAtendimentoListRow);
        if (window.ProdespTempoAtendimento && typeof window.ProdespTempoAtendimento.atualizarSortEmLinhas === "function") {
          window.ProdespTempoAtendimento.atualizarSortEmLinhas(rows, prodespFilaTimeOffset);
        }
        return rows;
      },
      error: function (xhr, error, thrown) {
        if (
          error === "abort" ||
          thrown === "abort" ||
          (xhr && (xhr.statusText === "abort" || xhr.status === 0))
        ) {
          return;
        }
        console.error("Erro no carregamento da tabela:", thrown || error);
        showToast("Erro ao carregar dados da tabela. Verifique o console.", "danger");
      }
    },
    /* true: indicador no wrapper durante ajax.reload (não cobre a toolbar). */
    processing: true,
    columns: [
      { data: "id_vgr" },
      {
        data: "contratada",
        defaultContent: "",
        render: (data, type, row) => {
          const cellRow = { ...row, contratada: data || row.contratada };
          if (type !== "display") return prodespContratadaListCell(cellRow);
          return prodespContratadaListCellHtml(cellRow);
        },
      },
      {
        data: "data_agendamento",
        render: (data) => {
          if (!data) return "";
          const dt = prodespParseAtendimentoDate(data);
          return dt ? dt.toLocaleDateString("pt-BR") : data;
        }
      },
      { data: "hora_agendamento" },
      {
        data: "data_atendimento",
        render: (data, type, row) => {
          if (!data) return "";
          const dt = prodespParseAtendimentoDate(data);
          if (!dt) return data;
          if (type === "sort") return data + (row.horario_inicio || "00:00:00");
          return dt.toLocaleDateString("pt-BR");
        }
      },
      { data: "acronimo", defaultContent: "" },
      { data: "endereco", defaultContent: "" },
      { data: "municipio", defaultContent: "" },
      { data: "status_atendimento" },
      { data: "substatus_atendimento" },
      { data: "analista_atuante" },
      { data: "analista_configuracao" },
      { data: "analista_mpls_atendimentos" },
      { data: "analista_caderno_teste" },
      {
        name: "prodesp_tempo_etapa",
        data: "_sort_etapa",
        orderable: true,
        searchable: false,
        defaultContent: 9e15,
        render: (data, type, row) => {
          if (type !== "display") return data;
          const T = window.ProdespTempoAtendimento;
          return T ? T.renderSpanTempo("etapa", row, prodespFilaTimeOffset) : "";
        },
      },
      {
        name: "prodesp_tempo_vida",
        data: "_sort_vida",
        orderable: true,
        searchable: false,
        defaultContent: 9e15,
        render: (data, type, row) => {
          if (type !== "display") return data;
          const T = window.ProdespTempoAtendimento;
          return T ? T.renderSpanTempo("vida", row, prodespFilaTimeOffset) : "";
        },
      },
      {
        data: "id_atendimento",
        render: function (data, type, row) {
          if (type === "sort" || type === "filter") {
            return data ?? "";
          }

          let html = "";

          // Ícone do Olho (Visualização)
          if (data) {
            html += `<button class="btn-icon" onclick="viewDetails(${data})" title="Visualizar Atendimento"><i class="fas fa-eye"></i></button>`;
          } else {
            html += `<button class="btn-icon" onclick="viewUnitOnly('${row.id_vgr}')" title="Visualizar Dados da Unidade"><i class="fas fa-eye"></i></button>`;
          }

          // Ícone do Lápis (Edição / Início) — regra JS na linha (analistas + data + substatus)
          if (data && prodespLinhaPodeEditar(row)) {
            html += `<button class="btn-icon" onclick="editDetails(${data})" title="Editar Atendimento"><i class="fas fa-pencil-alt"></i></button>`;
          } else if (!data) {
            html += `<button class="btn-icon" onclick="openCreateWithVgr('${row.id_vgr}')" title="Observações / Iniciar Atendimento"><i class="fas fa-pencil-alt"></i></button>`;
          }

          if (prodespIsAdminUser()) {
            if (data) {
              html += `<button type="button" class="btn-icon text-danger" onclick="return prodespAdminExcluirAtendimento(${data}, event)" title="Excluir atendimento (admin)"><i class="fas fa-trash-alt"></i></button>`;
            } else if (row.id_vgr) {
              html += `<button type="button" class="btn-icon text-danger" onclick="return prodespAdminRemoverAgendamento('${row.id_vgr}', event)" title="Remover agendamento (admin)"><i class="fas fa-calendar-times"></i></button>`;
            }
          }
          return `<span class="prodesp-dt-acoes-inner">${html}</span>`;
        }
      },
      {
        data: "_sort_lista",
        visible: false,
        searchable: false,
        orderable: true,
        defaultContent: 2e15,
      },
    ],
    language: prodespAtendimentosDataTableLanguage(),
    // ⚙️ Configurações gerais da tabela
    // Ordenação via ColumnControl; sem triângulos nativos do DataTables 2 (dt-column-order)
    ordering: prodespDtOrderingSilent(),
    order: [[PRODESP_DT_COL_LISTA, "asc"]],
    deferRender: true,
  /* Larguras fixas (px) + scrollX; texto longo quebra linha (className prodesp-dt-wrap) */
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
        targets: PRODESP_DT_COL_TEMPO_ETAPA,
        width: "92px",
        type: "prodesp-tempo",
        orderDataType: "prodesp-tempo",
        searchable: false,
        orderable: true,
        className: "prodesp-dt-tempo-etapa prodesp-dt-center",
        columnControl: prodespDtCcOrderOnly(),
      },
      {
        targets: PRODESP_DT_COL_TEMPO_VIDA,
        width: "92px",
        type: "prodesp-tempo",
        orderDataType: "prodesp-tempo",
        searchable: false,
        orderable: true,
        className: "prodesp-dt-tempo-vida prodesp-dt-center",
        columnControl: prodespDtCcOrderOnly(),
      },
      {
        targets: PRODESP_DT_COL_ACOES,
        width: "104px",
        searchable: false,
        orderable: false,
        className: "prodesp-dt-compact prodesp-dt-acoes prodesp-dt-center",
      },
      {
        targets: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13],
        columnControl: prodespDtCcSearchList(),
      },
      {
        targets: PRODESP_DT_COL_STATUS,
        columnControl: [
          [
            {
              extend: "searchList",
              ajaxOnly: false,
              options: PRODESP_STATUS_FILTER_OPTIONS,
            },
            "spacer",
            "orderAsc",
            "orderDesc",
            "orderClear",
          ],
        ],
      },
    ],
    stateSave: false,

    // 📊 Configurações de busca 
    // 📊 Configurações de exibição
    initComplete: function (_settings, json) {
      const api = this.api();

      if (json && json.server_time) {
        prodespFilaTimeOffset = Date.now() - new Date(json.server_time).getTime();
      }
      if (json && json.data_revision != null && window.prodespFilaDtSync) {
        window.prodespFilaDtSync.setRevision(json.data_revision);
      }
      if (json && json.data_revision != null) {
        window.prodespFilaLastDataRevision = Number(json.data_revision);
      }

      if (window.ProdespDtPageLength && typeof window.ProdespDtPageLength.bindSave === "function") {
        window.ProdespDtPageLength.bindSave(api);
      }

      const urlParams = new URLSearchParams(window.location.search);
      const idVgrToSearch = urlParams.get("search_id_vgr");
      const openEditId = urlParams.get("open_edit");

      if (api.columnControl) {
        api.columnControl.init();
      }
      prodespBindColumnControlServerSide(api);
      prodespBindServerSideColumnSearch(api);
      if (window.ProdespDtColumns && typeof window.ProdespDtColumns.initTable === "function") {
        window.ProdespDtColumns.initTable(api, "tabela-atendimentos");
      }
      prodespRefreshStatusColumnSearchList(api);
      if (window.ProdespDtFontSize && typeof window.ProdespDtFontSize.refresh === "function") {
        window.ProdespDtFontSize.refresh();
      }

      if (idVgrToSearch) {
        const idVgrColumn = api.column(0);
        const idVgrSelect = $(idVgrColumn.header()).find("select");
        if (prodespListServerSide) {
          idVgrColumn.search(idVgrToSearch, false, false);
        } else {
          idVgrColumn.search("^" + $.fn.dataTable.util.escapeRegex(idVgrToSearch) + "$", true, false);
        }
        api.draw();
        if (idVgrSelect.find(`option[value='${idVgrToSearch}']`).length === 0) {
          const newOption = new Option(idVgrToSearch, idVgrToSearch, true, true);
          idVgrSelect.append(newOption);
        }
        idVgrSelect.val([idVgrToSearch]).trigger("change.select2");
      }

      if (openEditId) {
        const newUrlParams = new URLSearchParams(window.location.search);
        newUrlParams.delete("open_edit");
        if (idVgrToSearch) newUrlParams.set("search_id_vgr", idVgrToSearch);
        const newUrl = `${window.location.pathname}?${newUrlParams.toString()}`;
        window.history.replaceState({}, document.title, newUrl);
        setTimeout(() => editDetails(openEditId), 250);
      }

      if (typeof portalConsumirOpenView === "function" && typeof viewDetails === "function") {
        portalConsumirOpenView(viewDetails);
      }
      if (window.ProdespTempoAtendimento && typeof window.ProdespTempoAtendimento.atualizarTempos === "function") {
        window.ProdespTempoAtendimento.atualizarTempos(".tempo-etapa, .tempo-vida");
      }
      api.columns.adjust();
      const refreshEl = document.getElementById("prodesp-dt-last-refresh-text");
      if (refreshEl) {
        const now = new Date();
        refreshEl.textContent =
          "Atualizado às " +
          now.toLocaleTimeString("pt-BR", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          });
      }
    },
    drawCallback: function () {
      if (window.ProdespTempoAtendimento && typeof window.ProdespTempoAtendimento.atualizarTempos === "function") {
        window.ProdespTempoAtendimento.atualizarTempos(".tempo-etapa, .tempo-vida");
      }
      this.api().columns.adjust();
    },
  });

  $tabelaAtendimentos.on("preDraw.dt", function (_e, settings) {
    const api = new $.fn.dataTable.Api(settings);
    const T = window.ProdespTempoAtendimento;
    if (!T || typeof T.atualizarSortEmLinha !== "function") return;
    const orders = api.order();
    const tempoOrdenado = orders.some(
      (o) => o[0] === PRODESP_DT_COL_TEMPO_ETAPA || o[0] === PRODESP_DT_COL_TEMPO_VIDA
    );
    if (!tempoOrdenado) return;
    api.rows().every(function () {
      T.atualizarSortEmLinha(this.data(), prodespFilaTimeOffset);
    });
  });

  // Função para atualizar os contadores no topo da página
  function updateTopCards(resumo) {
    if (!resumo) return;
    const agendados = resumo.agendados ?? 0;

    $("#card-total-geral").text(resumo.total_geral);
    $("#card-total-aguarda-gestao").text(
      typeof prodespContagemKpiAguardaGestao === "function"
        ? prodespContagemKpiAguardaGestao(resumo.substatus_counts)
        : (resumo.substatus_counts[SUBSTATUS_AGUARDA_GESTAO] || 0) +
          (resumo.substatus_counts["Triagem"] || 0)
    );
    $("#card-agendados-fila").text(agendados);

    $("#card-aguarda-contratada").text(
      resumo.substatus_counts[SUBSTATUS_AGUARDA_CONTRATADA] || 0
    );
    $("#card-aguarda-licenca").text(
      resumo.substatus_counts[SUBSTATUS_AGUARDA_LICENCA] || 0
    );

    const substatusCounts = resumo.substatus_counts || {};
    Object.keys(substatusCounts).forEach((key) => {
      const $card = $(`[data-substatus="${key}"]`);
      const $val = $card.find(".prodesp-kpi-value").first();
      if ($val.length) {
        $val.text(substatusCounts[key]);
      } else {
        $card.find("h3").first().text(substatusCounts[key]);
      }
    });
  }

  function prodespAfterFilaDataLoaded() {
    prodespRefreshStatusColumnSearchList(table);
    if (
      window.ProdespDtFontSize &&
      typeof window.ProdespDtFontSize.reapplySavedToTable === "function"
    ) {
      window.ProdespDtFontSize.reapplySavedToTable("tabela-atendimentos");
    }
  }

  function prodespFilaFullAjaxReload() {
    return new Promise(function (resolve) {
      table.ajax.reload(function () {
        prodespAfterFilaDataLoaded();
        resolve();
      }, false);
    });
  }

  /**
   * Garante opções do ColumnControl nas colunas tocadas pelo delta (status/sub/analistas).
   * Não reconstrói as 14 colunas × N linhas — só injeta valores novos nos searchList.
   */
  function prodespRefreshColumnOptionsFromDeltaRows(api, rows) {
    if (!api || !rows || !rows.length) return;
    const statusVals = [];
    const subVals = [];
    const analistaCols = [
      { idx: 10, key: "analista_atuante" },
      { idx: 11, key: "analista_configuracao" },
      { idx: 12, key: "analista_mpls_atendimentos" },
      { idx: 13, key: "analista_caderno_teste" },
    ];
    const analistaVals = [[], [], [], []];
    rows.forEach(function (r) {
      if (!r) return;
      if (r.status_atendimento) statusVals.push(r.status_atendimento);
      if (r.substatus_atendimento) subVals.push(r.substatus_atendimento);
      analistaCols.forEach(function (c, i) {
        if (r[c.key]) analistaVals[i].push(r[c.key]);
      });
    });
    if (statusVals.length) {
      prodespEnsureSearchListOptions(api.column(PRODESP_DT_COL_STATUS), statusVals);
    }
    if (subVals.length) {
      prodespEnsureSearchListOptions(api.column(PRODESP_DT_COL_SUBSTATUS), subVals);
    }
    analistaCols.forEach(function (c, i) {
      if (analistaVals[i].length) {
        prodespEnsureSearchListOptions(api.column(c.idx), analistaVals[i]);
      }
    });
    prodespRefreshStatusColumnSearchList(api);
  }

  /**
   * Sync da fila (Fase 2): com PRODESP_LIST_DELTA, patch add/update/remove + KPIs.
   * fallback_full / gap opaco / lote grande → ajax.reload. force (Atualizar) sempre full.
   * @param {boolean} force
   * @param {number|null|undefined} sinceRevision — revisão conhecida antes do tick (para delta)
   */
  function prodespFilaSyncReload(force, sinceRevision) {
    const deltaOn =
      window.PRODESP_LIST_DELTA === true ||
      window.PRODESP_LIST_DELTA === 1 ||
      String(window.PRODESP_LIST_DELTA || "0") === "1";
    if (force || !deltaOn) {
      return prodespFilaFullAjaxReload();
    }

    let sinceRev = sinceRevision;
    if (sinceRev == null && window.prodespFilaDtSync && typeof window.prodespFilaDtSync.getRevision === "function") {
      sinceRev = window.prodespFilaDtSync.getRevision();
    }
    if (sinceRev == null && typeof window.prodespFilaLastDataRevision === "number") {
      sinceRev = window.prodespFilaLastDataRevision;
    }
    if (sinceRev == null || sinceRev < 0) {
      return prodespFilaFullAjaxReload();
    }

    const scope = encodeURIComponent(prodespListEffectiveScope());
    const url =
      "/prodesp/api/atendimentos_list_delta?since_revision=" +
      encodeURIComponent(String(sinceRev)) +
      "&scope=" +
      scope;

    /** Acima disso, full reload (evita micro-travadas em mutação em massa). */
    const DELTA_MAX_PATCH = 100;

    return fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error("delta HTTP " + resp.status);
        return resp.json();
      })
      .then(function (payload) {
        if (payload && payload.data_revision != null) {
          window.prodespFilaLastDataRevision = Number(payload.data_revision);
          if (window.prodespFilaDtSync && typeof window.prodespFilaDtSync.setRevision === "function") {
            window.prodespFilaDtSync.setRevision(payload.data_revision);
          }
        }
        if (!payload || payload.unchanged) {
          return;
        }
        if (payload.fallback_full) {
          return prodespFilaFullAjaxReload();
        }

        const updated = (payload.updated || []).concat(payload.added || []);
        const removedIds = payload.removed_ids || [];
        if (updated.length + removedIds.length > DELTA_MAX_PATCH) {
          return prodespFilaFullAjaxReload();
        }
        if (!updated.length && !removedIds.length) {
          if (payload.resumo) updateTopCards(payload.resumo);
          return;
        }

        const byId = {};
        table.rows().every(function () {
          const d = this.data();
          if (!d) return;
          const aid = d.id_atendimento;
          if (aid != null && aid !== "") {
            byId[String(aid)] = this.index();
          }
        });

        // Patch/add antes do remove: índices do byId ficam inválidos após .remove().
        const touchedForCc = [];
        const toAdd = [];
        updated.forEach(function (row) {
          const aid = row && row.id_atendimento;
          if (aid == null || aid === "") return;
          const normalized = prodespNormalizeAtendimentoListRow(row);
          touchedForCc.push(normalized);
          const idx = byId[String(aid)];
          if (idx == null) {
            toAdd.push(normalized);
            return;
          }
          const apiRow = table.row(idx);
          const prev = apiRow.data() || {};
          apiRow.data(Object.assign({}, prev, normalized));
        });

        if (removedIds.length) {
          const removeSet = {};
          removedIds.forEach(function (rid) {
            removeSet[String(rid)] = true;
          });
          table.rows(function (_idx, data) {
            return (
              data &&
              data.id_atendimento != null &&
              data.id_atendimento !== "" &&
              !!removeSet[String(data.id_atendimento)]
            );
          }).remove();
        }

        toAdd.forEach(function (normalized) {
          table.row.add(normalized);
        });

        if (payload.resumo) updateTopCards(payload.resumo);
        prodespRefreshColumnOptionsFromDeltaRows(table, touchedForCc);
        table.rows().invalidate("data").draw(false);
        if (
          window.ProdespDtFontSize &&
          typeof window.ProdespDtFontSize.reapplySavedToTable === "function"
        ) {
          window.ProdespDtFontSize.reapplySavedToTable("tabela-atendimentos");
        }
        if (window.ProdespTempoAtendimento && typeof window.ProdespTempoAtendimento.atualizarTempos === "function") {
          window.ProdespTempoAtendimento.atualizarTempos(".tempo-etapa, .tempo-vida", {
            timeOffset: prodespFilaTimeOffset,
          });
        }
      })
      .catch(function () {
        return prodespFilaFullAjaxReload();
      });
  }

  if (window.ProdespDtSync) {
    window.prodespFilaDtSync = window.ProdespDtSync.create({
      getTableSettings: function () {
        return table.settings()[0];
      },
      onServerTime: function (iso) {
        prodespFilaTimeOffset = Date.now() - new Date(iso).getTime();
      },
      onReload: function (force, sinceRevision) {
        return prodespFilaSyncReload(!!force, sinceRevision);
      },
    });
    window.prodespDtSyncInstance = window.prodespFilaDtSync;
    window.prodespFilaDtSync.schedule();
  }

  setInterval(() => {
    const T = window.ProdespTempoAtendimento;
    if (
      !prodespListServerSide &&
      T &&
      typeof T.resortDataTableSeTempo === "function"
    ) {
      T.resortDataTableSeTempo(table, prodespFilaTimeOffset, [PRODESP_DT_COL_TEMPO_ETAPA, PRODESP_DT_COL_TEMPO_VIDA]);
    }
    if (T && typeof T.atualizarTempos === "function") {
      T.atualizarTempos(".tempo-etapa, .tempo-vida", { timeOffset: prodespFilaTimeOffset });
    }
  }, 1000);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && window.prodespFilaDtSync) {
      /* checkNow: só reload se data_revision mudou (evita travar 3k+ linhas ao focar a aba). */
      if (typeof window.prodespFilaDtSync.checkNow === "function") {
        window.prodespFilaDtSync.checkNow();
      } else {
        window.prodespFilaDtSync.forceRefresh();
      }
    }
  });

  $("#btnClearFilters").on("click", function () {
    prodespClearAllTableFilters(table);
  });

  $("#prodespListSomenteFilaAtiva").on("change", function () {
    prodespListScope = this.checked ? "fila" : "completo";
    table.ajax.reload();
  });

  // --- FILTRO POR CARDS ---
  $(".filter-card").on("click", function () {
    const substatus = $(this).data("substatus");
    const statusFilter = $(this).data("status-filter");
    const filterMode = $(this).data("filter-mode");

    if (prodespListServerSide) {
      prodespListSetCardFilter({ filterMode, statusFilter, substatus });
      prodespSetCardExtSearch(null);
      table.search("");
      table.columns().search("");
      prodespClearColumnControlUi(table);
      table.ajax.reload(null, true);
      $("html, body").animate(
        { scrollTop: $("#tabela-atendimentos").offset().top },
        500
      );
      return;
    }

    const colStatus = table.column(PRODESP_DT_COL_STATUS);
    const colSubstatus = table.column(PRODESP_DT_COL_SUBSTATUS);

    prodespSetCardExtSearch(null);
    table.search("");
    table.columns().search("");
    prodespClearColumnControlUi(table);

    if (filterMode === "migrados") {
      prodespApplyDtColumnFilter(colStatus, "Concluído", false);
      prodespApplyDtColumnFilter(colSubstatus, "Concluído", false);
    } else if (filterMode === "aguardando-cliente") {
      prodespApplyDtColumnFilter(colStatus, "Em Atendimento", false);
      prodespApplyDtColumnFilter(colSubstatus, "Aguardando Cliente", false);
    } else if (filterMode === "aguarda-contratada") {
      prodespApplyDtColumnFilter(colStatus, "Em Atendimento", false);
      colSubstatus.search("", false, false);
      prodespSetCardExtSearch(function (settings, _searchData, dataIndex) {
        if (settings.nTable.id !== "tabela-atendimentos") {
          return true;
        }
        const row = table.row(dataIndex).data();
        const sub = (row?.substatus_atendimento || "").trim();
        return prodespIsSubstatusAguardaContratada(sub);
      });
    } else if (filterMode === "aguarda-licenca") {
      prodespApplyDtColumnFilter(colStatus, "Em Atendimento", false);
      prodespApplyDtColumnFilter(colSubstatus, SUBSTATUS_AGUARDA_LICENCA, false);
    } else if (statusFilter === "Agendado") {
      colSubstatus.search("", false, false);
      colStatus.search("", false, false);
      prodespSetCardExtSearch(function (settings, _searchData, dataIndex) {
        if (settings.nTable.id !== "tabela-atendimentos") {
          return true;
        }
        const row = table.row(dataIndex).data();
        return prodespRowIsAgendado(row);
      });
    } else if (filterMode === "aguarda-gestao") {
      colStatus.search("", false, false);
      colSubstatus.search("", false, false);
      prodespSetCardExtSearch(function (settings, _searchData, dataIndex) {
        if (settings.nTable.id !== "tabela-atendimentos") {
          return true;
        }
        const row = table.row(dataIndex).data();
        const sub = (row?.substatus_atendimento || "").trim();
        return sub === "Triagem" || sub === SUBSTATUS_AGUARDA_GESTAO;
      });
    } else if (filterMode === "filas-ativas") {
      colStatus.search("", false, false);
      colSubstatus.search("", false, false);
      prodespSetCardExtSearch(function (settings, _searchData, dataIndex) {
        if (settings.nTable.id !== "tabela-atendimentos") {
          return true;
        }
        const row = table.row(dataIndex).data();
        return prodespRowInFilasAtivas(row);
      });
    } else if (statusFilter) {
      colSubstatus.search("", false, false);
      prodespApplyDtColumnFilter(colStatus, statusFilter, false);
    } else if (substatus) {
      colStatus.search("", false, false);
      prodespApplyDtColumnFilter(colSubstatus, substatus, false);
    }

    table.draw();

    $("html, body").animate(
      {
        scrollTop: $("#tabela-atendimentos").offset().top,
      },
      500
    );
  });

  // --- GERAÇÃO DE BLUEPRINT ---
  async function generateBlueprint(idVgr) {
    if (window.ProdespBlueprintConfirm && typeof window.ProdespBlueprintConfirm.generateWithConfirm === "function") {
      return window.ProdespBlueprintConfirm.generateWithConfirm(idVgr);
    }
    if (!idVgr) {
      showToast("ID VGR não encontrado para gerar o blueprint.", "danger");
      return;
    }

    try {
      showToast("Gerando blueprint...", "info");
      const response = await fetch(`/prodesp/api/gerar_blueprint_prodesp/${idVgr}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm: true }),
      });

      const result = await response.json();

      if (result.success) {
        showToast(result.message, "success");
        if (result.download_url) {
          if (
            window.ProdespBlueprintConfirm &&
            typeof window.ProdespBlueprintConfirm.triggerDownload === "function"
          ) {
            window.ProdespBlueprintConfirm.triggerDownload(result.download_url);
          } else {
            const a = document.createElement("a");
            a.href = result.download_url;
            a.target = "_blank";
            a.rel = "noopener";
            document.body.appendChild(a);
            a.click();
            a.remove();
          }
        }
      } else {
        showToast(result.message, "danger");
      }
    } catch (error) {
      console.error("Erro ao gerar blueprint:", error);
      showToast("Erro ao gerar blueprint. Verifique o console.", "danger");
    }
  }

  // Event listener para o botão de blueprint no modal de visualização
  $('#btnGenerateBlueprintView').on('click', function() {
    const idVgr = $('#viewIdVgr').val();
    generateBlueprint(idVgr);
  });

  // Event listener para o botão de blueprint no modal de edição
  $('#btnGenerateBlueprintEdit').on('click', function() {
    const idVgr = $('#editIdVgr').val();
    generateBlueprint(idVgr);
  });

  // Event listener para o botão de blueprint no modal de criação
  $('#btnGenerateBlueprintCreate').on('click', function() {
    const idVgr = $('#createIdVgr').val();
    generateBlueprint(idVgr);
  });

  function prodespDtSyncScrollColumns() {
    try {
      table.columns.adjust();
    } catch (e) {
      /* ignore */
    }
    if (window.ProdespDtFontSize && typeof window.ProdespDtFontSize.scheduleAdjustColumns === "function") {
      window.ProdespDtFontSize.scheduleAdjustColumns();
    }
  }

  $(window).on("resize", prodespDtSyncScrollColumns);
  table.on("draw", prodespDtSyncScrollColumns);

  // --- MÁSCARAS ---
  const coordinateMaskDefinition = { mask: Number, signed: true, scale: 8, radix: '.', mapToRadix: [','], normalizeZeros: true, padFractionalZeros: false };
  ['editLatitude', 'editLongitude', 'createLatitude', 'createLongitude'].forEach(id => {
    const el = document.getElementById(id);
    if (el) maskInstances[id] = IMask(el, coordinateMaskDefinition);
  });

  const serialMaskDefinition = { mask: /^[a-zA-Z0-9\-]*$/, prepare: str => str.toUpperCase() };

  [
    { id: 'editEquipamentoSerial', mask: serialMaskDefinition }, { id: 'createEquipamentoSerial', mask: serialMaskDefinition }
  ].forEach(field => {
    const el = document.getElementById(field.id);
    if (el) maskInstances[field.id] = IMask(el, field.mask);
  });

  // --- MÁSCARAS E VALIDAÇÃO PARA IP / CIDR ---
  const ipPlainMaskDefinition = { mask: /^[0-9.]*$/ };
  const ipCidrMaskDefinition = { mask: /^[0-9./]*$/ };
  const ipCidrFieldIds = new Set(["editIpLan01", "createIpLan01"]);
  const ipPlainFieldIds = [
    "editIpLanTransito", "createIpLanTransito",
    "editLoopbackVivo", "createLoopbackVivo",
    "editLoopbackCliente", "createLoopbackCliente",
    "editLoopbackOnBgp", "createLoopbackOnBgp",
    "editLinkIpWan", "createLinkIpWan",
    "editLinkIpGateway", "createLinkIpGateway",
    "editLinkIpMascara", "createLinkIpMascara",
  ];

  function prodespBindIpFieldMask(el, allowCidr) {
    if (!el) return;
    maskInstances[el.id] = IMask(el, allowCidr ? ipCidrMaskDefinition : ipPlainMaskDefinition);
    bindProdespIpNoWhitespace(el);
    el.addEventListener("blur", () => {
      const val = prodespStripIpSpaces(el.value.trim());
      if (val === "") {
        el.classList.remove("is-invalid");
        return;
      }
      if (!prodespIsValidIpFieldValue(val, allowCidr)) {
        el.classList.add("is-invalid");
        const label = document.querySelector(`label[for="${el.id}"]`)?.textContent || "IP";
        const hint = allowCidr
          ? "IPv4 com máscara CIDR (ex: 10.14.128.1/24)"
          : "endereço IPv4 válido (ex: 192.168.0.1)";
        showToast(`O campo "${label}" deve conter um ${hint}.`, "warning");
      } else {
        el.classList.remove("is-invalid");
      }
    });
  }

  ipCidrFieldIds.forEach((id) => {
    prodespBindIpFieldMask(document.getElementById(id), true);
  });
  ipPlainFieldIds.forEach((id) => {
    prodespBindIpFieldMask(document.getElementById(id), false);
  });
  PRODESP_MV_OPCIONAIS_JS_KEYS.forEach((col) => {
    ["edit", "create"].forEach((prefix) => {
      prodespBindIpFieldMask(document.getElementById(idFor(prefix, col)), false);
    });
  });

  PRODESP_NO_WHITESPACE_FIELD_IDS.forEach((id) => {
    bindProdespNoWhitespace(document.getElementById(id));
  });

  prodespInitLiveFieldValidation();

  if (window.ProdespLiveValidation && ProdespLiveValidation.bindAllVelocityMbpsInputs) {
    ProdespLiveValidation.bindAllVelocityMbpsInputs(document);
  }

  // --- LÓGICA PARA LINKS CONDICIONAIS ---
  function handleLinkTypeChange(context) {
    const typeSelect = document.getElementById(`${context}LinkTipo`);
    if (!typeSelect) return;

    const selectedType = typeSelect.value;
    const container = document.getElementById(`${context}-link-fields-container`);
    if (!container) return;

    const fields = container.querySelectorAll('.link-field-wrapper');

    fields.forEach(field => {
      const linkTypeAttr = field.dataset.linkType;
      const supportedTypes = linkTypeAttr ? linkTypeAttr.split(' ') : [];
      const isRedundanteCritico = field.classList.contains('mpls-vivo-redundante-wrapper');
      const operadora = document.getElementById(`${context}LinkOperadora`)?.value || "";
      const isVivo = window.ProdespLiveValidation
        ? ProdespLiveValidation.isVivoOperadora(operadora)
        : String(operadora).trim().toUpperCase() === "VIVO";
      const shouldShow =
        supportedTypes.includes(selectedType) &&
        (!isRedundanteCritico || (selectedType === "MPLS" && isVivo));

      if (shouldShow) {
        field.style.display = '';
      } else {
        field.style.display = 'none';
        const input = field.querySelector('input, select');
        if (input) {
          if (input.type === "checkbox") input.checked = false;
          else input.value = '';
        }
      }
    });
    // ID VGR do link: só VIVO (depois do toggle por tipo, para não reaparecer com CLARO/OUTRA)
    if (window.ProdespLiveValidation && ProdespLiveValidation.syncAtendimentoLinkIdVgrVisibility) {
      ProdespLiveValidation.syncAtendimentoLinkIdVgrVisibility(context);
    }
    prodespRefreshLiveFieldValidation(context);
  }

  ['create', 'edit'].forEach(context => {
    const typeSelect = document.getElementById(`${context}LinkTipo`);
    if (typeSelect) {
      typeSelect.addEventListener('change', () => handleLinkTypeChange(context));
      handleLinkTypeChange(context); // Initial call
    }
    const operSelect = document.getElementById(`${context}LinkOperadora`);
    if (operSelect) {
      operSelect.addEventListener('change', () => {
        handleLinkTypeChange(context);
        if (window.ProdespLiveValidation && ProdespLiveValidation.syncAtendimentoLinkIdVgrVisibility) {
          ProdespLiveValidation.syncAtendimentoLinkIdVgrVisibility(context);
        }
      });
    }
  });

  // --- LÓGICA PARA DESCRIÇÃO AUTOMÁTICA DE EQUIPAMENTOS ---
  ['create', 'edit'].forEach(context => {
    const modeloSelect = document.getElementById(`${context}EquipamentoModelo`);
    const descricaoInput = document.getElementById(`${context}EquipamentoDescricao`);
    const serialEl = document.getElementById(`${context}EquipamentoSerial`);
    
    if (modeloSelect && descricaoInput) {
      modeloSelect.addEventListener('change', function() {
        const selectedModel = this.value; // Get the selected model value
        const autoDescModels = [
          "FortiGate 40F", "FortiGate 60F", "FortiGate 120G", 
          "FortiGate 900G", "FortiGate 3200F", "FortiGate 3700F",
          "FortiGate 600F" // Include FortiGate 600F in auto-description
        ];
        
        // Clear previous description
        descricaoInput.value = "";
        
        if (autoDescModels.includes(selectedModel)) {
          descricaoInput.value = "Firewall - Stand Alone";
        } else if (selectedModel === "FortiSwitch 2048F") {
          descricaoInput.value = "Switch"; // Specific description for FortiSwitch
        }
      });
    }

    if (serialEl && modeloSelect) {
      const onSerialModelo = () => prodespSyncEquipamentoModeloFromSerial(context);
      serialEl.addEventListener('input', onSerialModelo);
      serialEl.addEventListener('change', onSerialModelo);
      serialEl.addEventListener('paste', function () {
        const run = () => prodespSyncEquipamentoModeloFromSerial(context);
        if (typeof queueMicrotask === "function") queueMicrotask(run);
        else setTimeout(run, 0);
      });
      if (
        window.ProdespLiveValidation &&
        ProdespLiveValidation.bindSerialFortinetInput
      ) {
        ProdespLiveValidation.bindSerialFortinetInput(serialEl, {
          obrigatorio: true,
          exigePadrao: true,
          onAfter: onSerialModelo,
        });
      }
    }
  });

  // --- COLLAPSE ICON TOGGLE ---
  $('.chart-collapse').on('show.bs.collapse', function () {
    $(this).parent().find('.card-header button i').removeClass('fa-plus').addClass('fa-minus');
  }).on('hide.bs.collapse', function () {
    $(this).parent().find('.card-header button i').removeClass('fa-minus').addClass('fa-plus');
  });
});

function prodespInitLiveFieldValidation() {
  if (!window.ProdespLiveValidation) return;
  ProdespLiveValidation.injectCss();
  window._prodespLiveValidation = window._prodespLiveValidation || {};
  ["edit", "create"].forEach((ctx) => {
    window._prodespLiveValidation[`loopback_${ctx}`] = ProdespLiveValidation.initLoopbackTriplet({
      vivo: `${ctx}LoopbackVivo`,
      cliente: `${ctx}LoopbackCliente`,
      bgp: `${ctx}LoopbackOnBgp`,
      emptyHint: "Campo obrigatório.",
    });
    window._prodespLiveValidation[`link_${ctx}`] = ProdespLiveValidation.initAtendimentoLinkForm(ctx);
  });
  ProdespLiveValidation.initTicketNocFields(["editTicketNoc", "createTicketNoc"]);
}

function prodespRefreshLiveFieldValidation(prefix) {
  if (!window._prodespLiveValidation || !prefix) return;
  if (window.ProdespLiveValidation && ProdespLiveValidation.refreshFormAfterDataLoad) {
    ProdespLiveValidation.refreshFormAfterDataLoad({
      loopbacks: {
        vivo: document.getElementById(prefix + "LoopbackVivo"),
        cliente: document.getElementById(prefix + "LoopbackCliente"),
        bgp: document.getElementById(prefix + "LoopbackOnBgp"),
      },
      loopbackController: window._prodespLiveValidation[`loopback_${prefix}`],
      linkController: window._prodespLiveValidation[`link_${prefix}`],
    });
    const linkCtrl = window._prodespLiveValidation[`link_${prefix}`];
    if (linkCtrl && linkCtrl.refresh) linkCtrl.refresh();
    const velEl = document.getElementById(prefix + "LinkVelocidade");
    if (velEl && ProdespLiveValidation.applyVelocityMbpsToField) {
      ProdespLiveValidation.applyVelocityMbpsToField(velEl, true);
    }
    return;
  }
  const lb = window._prodespLiveValidation[`loopback_${prefix}`];
  if (lb && lb.refresh) lb.refresh();
  const link = window._prodespLiveValidation[`link_${prefix}`];
  if (link && link.refresh) link.refresh();
}

/** Remove espaços em IP/CIDR (mesmo critério da tela Gerar Blueprint). */
function prodespStripIpSpaces(str) {
  return (str == null ? "" : String(str)).replace(/\s+/g, "");
}

/** Remove espaços + ruído típico de colagem (ZWSP/BOM/aspas) — alinhado a ProdespLiveValidation. */
function prodespStripAllSpaces(str) {
  if (window.ProdespLiveValidation && typeof ProdespLiveValidation.sanitizeLinkPastedText === "function") {
    return ProdespLiveValidation.sanitizeLinkPastedText(str);
  }
  let s = str == null ? "" : String(str);
  s = s.replace(/[\u200B-\u200D\uFEFF\u00AD\u2060\u00A0\u202F\u2007]/g, "");
  s = s.replace(/\s+/g, "");
  for (let i = 0; i < 3; i++) {
    const n = s.replace(/^['"\u2018\u2019\u201c\u201d]+|['"\u2018\u2019\u201c\u201d]+$/g, "");
    if (n === s) break;
    s = n;
  }
  return s;
}

function prodespValueHasWhitespace(str) {
  return /\s/.test(str == null ? "" : String(str));
}

const PRODESP_DEFAULT_MODELO_EQUIPAMENTO = "FortiGate 40F";

/** Inferência de modelo FortiGate a partir do serial (alinhado a prodesp_equipment.py / blueprint). */
function prodespInferModeloEquipamentoFromSerial(serial) {
  const rules = window.PRODESP_SERIAL_MODEL_RULES;
  const s = (serial || "").toUpperCase().replace(/\s/g, "");
  if (!s) return "";
  if (Array.isArray(rules)) {
    for (let i = 0; i < rules.length; i++) {
      const pair = rules[i];
      const fragment = pair && pair[0];
      const label = pair && pair[1];
      if (fragment && label && s.includes(String(fragment).toUpperCase())) {
        return label;
      }
    }
  }
  return PRODESP_DEFAULT_MODELO_EQUIPAMENTO;
}

function prodespGetEquipamentoSerialValue(context) {
  const fieldId = `${context}EquipamentoSerial`;
  const mask = maskInstances[fieldId];
  if (mask) {
    return String(mask.value || "").trim().toUpperCase();
  }
  const el = document.getElementById(fieldId);
  return el ? String(el.value || "").trim().toUpperCase() : "";
}

function prodespSetEquipamentoModeloSelect(selectEl, modelo) {
  if (!selectEl || !modelo) return false;
  const val = String(modelo).trim();
  if (!val) return false;
  let found = false;
  for (let i = 0; i < selectEl.options.length; i++) {
    if (selectEl.options[i].value === val) {
      found = true;
      break;
    }
  }
  if (!found) {
    selectEl.add(new Option(val, val));
  }
  selectEl.value = val;
  selectEl.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}

function prodespSyncEquipamentoModeloFromSerial(context) {
  const modeloSelect = document.getElementById(`${context}EquipamentoModelo`);
  if (!modeloSelect || modeloSelect.disabled) return;
  const serial = prodespGetEquipamentoSerialValue(context);
  if (!serial) return;
  const inferred = prodespInferModeloEquipamentoFromSerial(serial);
  if (inferred) {
    prodespSetEquipamentoModeloSelect(modeloSelect, inferred);
  }
}

function bindProdespNoWhitespace(el) {
  if (!el || el.nodeName !== "INPUT" || el.dataset.prodespNoSpaceBound === "1") return;
  el.dataset.prodespNoSpaceBound = "1";
  el.addEventListener("keydown", function (e) {
    if (e.key === " " || e.code === "Space") e.preventDefault();
  });
  el.addEventListener("paste", function (e) {
    e.preventDefault();
    const text = prodespStripAllSpaces((e.clipboardData || window.clipboardData).getData("text"));
    const start = el.selectionStart != null ? el.selectionStart : el.value.length;
    const end = el.selectionEnd != null ? el.selectionEnd : el.value.length;
    if (typeof el.setRangeText === "function") {
      el.setRangeText(text, start, end, "end");
    } else {
      el.value = el.value.slice(0, start) + text + el.value.slice(end);
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  el.addEventListener("input", function () {
    const cleaned = prodespStripAllSpaces(el.value);
    if (cleaned === el.value) return;
    const pos = el.selectionStart;
    const oldLen = el.value.length;
    const m = maskInstances[el.id];
    if (m) {
      m.value = cleaned;
    } else {
      el.value = cleaned;
      if (pos != null && el.setSelectionRange) {
        const shrink = Math.max(0, oldLen - cleaned.length);
        el.setSelectionRange(Math.max(0, pos - shrink), Math.max(0, pos - shrink));
      }
    }
  });
}

const PRODESP_NO_WHITESPACE_FIELD_IDS = [
  "editEquipamentoVersao",
  "createEquipamentoVersao",
  "editEquipamentoSerial",
  "createEquipamentoSerial",
  "editLatitude",
  "createLatitude",
  "editLongitude",
  "createLongitude",
  "editHostname",
  "createHostname",
  "editAcronimo",
  "createAcronimo",
  "editLinkDesignador",
  "createLinkDesignador",
  "editLinkIdVgr",
  "createLinkIdVgr",
  "editLinkVlan",
  "createLinkVlan",
];

function prodespValidateLinkIpRules(tipo, designador, ipWan, ipGateway) {
  const wan = prodespStripIpSpaces(ipWan);
  const gw = prodespStripIpSpaces(ipGateway);
  if (!wan || !gw || wan !== gw) return true;
  const ctx =
    (tipo || "Link").trim() +
    (designador ? ` — Designador: ${String(designador).trim()}` : "");
  showToast(
    `${ctx}: IP WAN e Gateway não podem ser iguais. Corrija os campos IP WAN e Gateway.`,
    "warning"
  );
  return false;
}

/** Select de operadora (VIVO / CLARO / OUTRA), alinhado ao Blueprint. Preserva valor legado fora da lista. */
function prodespCreateLinkOperadoraSelect(currentValue) {
  const sel = document.createElement("select");
  sel.className = "form-select form-select-sm";
  sel.appendChild(new Option("", ""));
  const val = String(currentValue || "").trim();
  const upper = val.toUpperCase();
  ["VIVO", "CLARO"].forEach((op) => sel.appendChild(new Option(op, op)));
  if (val && upper !== "VIVO" && upper !== "CLARO" && upper !== "OUTRA") {
    sel.appendChild(new Option(val, val));
  }
  sel.appendChild(new Option("OUTRA", "OUTRA"));
  if (upper === "VIVO" || upper === "CLARO" || upper === "OUTRA") {
    sel.value = upper;
  } else if (val) {
    sel.value = val;
  }
  return sel;
}

function prodespCreateLinkEditLabeledCell(label, control) {
  const wrap = document.createElement("div");
  wrap.className = "incident-data prodesp-link-edit-cell";
  const lbl = document.createElement("span");
  lbl.className = "prodesp-link-edit-label text-muted";
  lbl.textContent = label;
  wrap.append(lbl, control);
  return wrap;
}

function prodespValidateNoWhitespaceFieldValue(value, label, el) {
  if (!prodespValueHasWhitespace(value)) {
    if (el) el.classList.remove("is-invalid");
    return true;
  }
  if (el) el.classList.add("is-invalid");
  showToast(`O campo «${label}» não pode conter espaços.`, "warning");
  return false;
}

function prodespSanitizePlainIpValue(val) {
  return prodespStripIpSpaces(val).replace(/\//g, "").replace(/[^0-9.]/g, "");
}

function bindProdespIpNoWhitespace(el) {
  if (!el || el.nodeName !== "INPUT" || el.dataset.prodespIpNoSpaceBound === "1") return;
  el.dataset.prodespIpNoSpaceBound = "1";
  const plainOnly = el.classList && el.classList.contains("prodesp-ip-plain-only");

  function cleanValue(raw) {
    return plainOnly ? prodespSanitizePlainIpValue(raw) : prodespStripIpSpaces(raw);
  }

  el.addEventListener("keydown", function (e) {
    if (e.key === " " || e.code === "Space") e.preventDefault();
    if (plainOnly && e.key === "/") e.preventDefault();
  });
  el.addEventListener("paste", function (e) {
    e.preventDefault();
    const text = cleanValue((e.clipboardData || window.clipboardData).getData("text"));
    const m = maskInstances[el.id];
    if (m) {
      m.value = text;
    } else {
      const start = el.selectionStart != null ? el.selectionStart : el.value.length;
      const end = el.selectionEnd != null ? el.selectionEnd : el.value.length;
      if (typeof el.setRangeText === "function") {
        el.setRangeText(text, start, end, "end");
      } else {
        el.value = el.value.slice(0, start) + text + el.value.slice(end);
      }
    }
    const fireInput = function () {
      el.dispatchEvent(new Event("input", { bubbles: true }));
    };
    if (typeof queueMicrotask === "function") {
      queueMicrotask(fireInput);
    } else {
      setTimeout(fireInput, 0);
    }
  });
  el.addEventListener("input", function () {
    const cleaned = cleanValue(el.value);
    if (cleaned === el.value) return;
    const m = maskInstances[el.id];
    if (m) {
      m.value = cleaned;
    } else {
      const pos = el.selectionStart;
      const oldLen = el.value.length;
      el.value = cleaned;
      if (pos != null && el.setSelectionRange) {
        const shrink = Math.max(0, oldLen - cleaned.length);
        el.setSelectionRange(Math.max(0, pos - shrink), Math.max(0, pos - shrink));
      }
    }
  });
}

// Objeto para armazenar as instâncias das máscaras (escopo global)
const maskInstances = {};

// ----------------------------------------------------------------------------------------
//FUNÇÕES PARA MÁSCARA DE TELEFONE
// ----------------------------------------------------------------------------------------
function aplicarMascaraTelefone(input) {
  input.addEventListener("input", () => {
    let valor = input.value.replace(/\D/g, ""); // Remove tudo que não é número
    let maskedValue = "";
    const isCelularComNove = valor.length >= 3 && valor.charAt(2) === "9"; // Determina o tipo de número pelo terceiro dígito (o primeiro após o DDD) // Assume que se tiver menos de 3 dígitos, ainda não sabemos o tipo.
    const maxDigits = isCelularComNove ? 11 : 10; // 11 para celular (DD + 9xxxx-xxxx), 10 para fixo (DD + xxxx-xxxx) // Define o limite máximo de dígitos para o número limpo
    if (valor.length > maxDigits) {
      valor = valor.slice(0, maxDigits);
    }

    // Aplica a máscara
    if (valor.length > 0) {
      maskedValue = `(${valor.slice(0, 2)}`; // (XX
    }
    if (valor.length > 2) {
      if (isCelularComNove) {
        // Formato para celular 9xxxx-xxxx (11 dígitos no total)
        if (valor.length <= 7) {
          // Até o 5º dígito do número (ex: 95475)
          maskedValue += `) ${valor.slice(2)}`;
        } else {
          // Depois do 5º dígito do número (ex: 95475-8008)
          maskedValue += `) ${valor.slice(2, 7)}-${valor.slice(7)}`;
        }
      } else {

        if (valor.length <= 6) {
          // Até o 4º dígito do número (ex: 4051)
          maskedValue += `) ${valor.slice(2)}`;
        } else {
          // Depois do 4º dígito do número (ex: 4051-3220)
          maskedValue += `) ${valor.slice(2, 6)}-${valor.slice(6)}`;
        }
      }
    }

    input.value = maskedValue;
  });

  // Impede colar caracteres inválidos e aplica a máscara
  input.addEventListener("paste", (e) => {
    const paste = (e.clipboardData || window.clipboardData).getData("text");
    const cleanedPaste = paste.replace(/\D/g, ""); // Remove não-dígitos da string colada

    // Apenas se o que foi colado (limpo) for inteiramente dígitos
    if (!/^\d+$/.test(cleanedPaste)) {
      e.preventDefault(); // Impede a colagem se contiver algo além de números
    } else {
      // Permite a colagem, mas depois dispara o evento 'input' para aplicar a máscara e o limite
      e.preventDefault(); // Previne a colagem padrão para controlar o que entra
      input.value = cleanedPaste; // Define o valor limpo
      setTimeout(() => {
        input.dispatchEvent(new Event("input")); // Dispara o evento 'input' para aplicar a máscara e o limite
      }, 0);
    }
  });

  // Impede digitação de letras ou símbolos
  input.addEventListener("keypress", (e) => {
    // Permite apenas dígitos
    if (!/\d/.test(e.key)) {
      e.preventDefault();
    }
  });
}

$(function () {
  const phoneFields = [
    'editContatoField',
    'editTelefoneContato',
    'createContatoField',
    'createTelefoneContato',
    'confirmDadosFieldContato',
  ];
  phoneFields.forEach(id => {
    const element = document.getElementById(id);
    if (element) {
      aplicarMascaraTelefone(element);
    }
  });
});

/**
 * Copia o texto de um campo ao clicar no ícone.
 * @param {Event} event O evento de clique.
 */
function handleCopyClick(event) {
  const copyBtn = event.target.closest('.btn-copy, .btn-copy-inline');
  if (!copyBtn) return; // Sai se o clique não foi em um botão/ícone de cópia

  let textToCopy = '';

  // Lógica para botões dentro de um input-group
  if (copyBtn.classList.contains('btn-copy')) {
    const input = copyBtn.closest('.input-group').querySelector('input, select');
    if (input) {
      textToCopy = input.value;
    }
  }
  // Lógica para ícones dentro da lista de equipamentos
  else if (copyBtn.classList.contains('btn-copy-inline')) {
    // Pega o texto do nó pai, removendo o texto do próprio ícone
    const parent = copyBtn.parentNode;
    const clone = parent.cloneNode(true);
    clone.removeChild(clone.querySelector('.btn-copy-inline'));
    textToCopy = clone.textContent.trim();
  }

  if (textToCopy) {
    navigator.clipboard.writeText(textToCopy).then(() => {
      showToast(`'${textToCopy}' copiado!`, 'success');
    }).catch(err => {
      console.error('Erro ao copiar:', err);
      showToast('Falha ao copiar para a área de transferência.', 'danger');
    });
  } else {
    showToast('Nada para copiar.', 'info');
  }
}

// Adiciona os listeners de clique aos modais usando delegação de eventos
document.addEventListener('DOMContentLoaded', () => {
  const editModalEl = document.getElementById('editModal');
  const createModalEl = document.getElementById('createModal');
  if (editModalEl) editModalEl.addEventListener('click', handleCopyClick);
  if (createModalEl) createModalEl.addEventListener('click', handleCopyClick);
});

/** Tempo visível do toast (ms) — mensagens de erro/validação ficam mais tempo para leitura. */
const PRODESP_TOAST_DELAYS_MS = {
  success: 9000,
  info: 14000,
  warning: 18000,
  danger: 22000,
};

function prodespEscapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Exibe uma notificação (toast).
 * @param {string} message Mensagem a ser exibida.
 * @param {string} type Tipo do toast: 'success', 'danger', 'warning', 'info'.
 * @param {number} [delay] Tempo em ms antes de fechar (padrão conforme o tipo).
 */
function showToast(message, type = "info", delay, titleOverride) {
  const toastContainer = document.querySelector(".toast-container");
  const texto = (message == null || message === "") ? "Operação não concluída." : String(message);
  if (!toastContainer) {
    console.error("Toast container not found!");
    alert(texto);
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

  const toastTitle =
    titleOverride ||
    {
      success: "Sucesso",
      danger: "Erro ao salvar",
      warning: "Atenção",
      info: "Informação",
    }[type] ||
    "Atenção";

  const effectiveDelay = delay ?? PRODESP_TOAST_DELAYS_MS[type] ?? 15000;
  const safeBody = prodespEscapeHtml(texto);

  const toastHtml = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header ${toastHeaderClass}">
                ${toastIcon}
                <strong class="me-auto">${toastTitle}</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body">${safeBody}</div>
        </div>`;

  toastContainer.insertAdjacentHTML("beforeend", toastHtml);
  const toastElement = document.getElementById(toastId);
  const toast = new bootstrap.Toast(toastElement, { delay: effectiveDelay, autohide: true });
  toastElement.addEventListener("hidden.bs.toast", () => toastElement.remove());
  toast.show();
}

/** Mensagem de sucesso padronizada (botão Salvar e auto-save). */
function prodespNotifySaveSuccess(modalKind) {
  const msg =
    modalKind === "create"
      ? "Atendimento Salvo com sucesso!"
      : "Dados salvos com sucesso!";
  showToast(msg, "success");
}

/**
 * Mensagens de validação/negócio já exibidas em toast — não poluir o console.
 * Rede/exceção inesperada continua em console.error.
 */
const PRODESP_EXPECTED_BUSINESS_ERROR_RE =
  /campo «|aceita no máximo|excede o tamanho|obrigat|preencha|Ticket NOC|permissão|perfil|conflito|já assumiu|Somente o analista|ainda não foi assumida|já pertence|designador|serial|divergente|coleta FGT|unicidade|já usado|duplicad|Gateway|IP WAN|Máscara|Velocidade|Operadora|Hostname|não preenchidos|bloquead|manobra|fora do padrão|Quebra|Concluído|loopback|comunicação com o servidor|conexão|Failed to fetch|network error|timeout/i;

function prodespIsExpectedBusinessError(detail) {
  const m = String(detail || "").trim();
  if (!m) return false;
  return PRODESP_EXPECTED_BUSINESS_ERROR_RE.test(m);
}

/**
 * Loga falha de save só se for inesperada (toast já cobre negócio esperado).
 * @param {string} label Prefixo do log
 * @param {*} detail Mensagem do backend ou erro
 * @param {Error} [err] Exceção de rede/parse
 */
function prodespLogUnexpectedSaveFailure(label, detail, err) {
  if (err) {
    const msg = detail || (err && err.message) || "";
    if (prodespIsExpectedBusinessError(msg) || prodespIsExpectedBusinessError(err.message)) {
      return;
    }
    console.error(label || "PRODESP save", detail || "", err);
    return;
  }
  if (prodespIsExpectedBusinessError(detail)) {
    return;
  }
  console.warn(label || "PRODESP save", detail || "falha ao salvar");
}

/**
 * Falha ao persistir — prioriza a mensagem da API (usuários leem só o início).
 * @param {string|null} scope Contexto curto (ex.: "observações"); omita se a API já explicou o erro
 * @param {string} [detail] Mensagem do backend ou descrição do erro
 */
function prodespNotifySaveFailure(scope, detail) {
  const humanized =
    window.ProdespFieldLimits && typeof window.ProdespFieldLimits.humanizeSaveError === "function"
      ? window.ProdespFieldLimits.humanizeSaveError(detail)
      : null;
  const motivo =
    (humanized && String(humanized).trim()) ||
    (detail && String(detail).trim()) ||
    "Verifique os campos do formulário e tente novamente.";

  const motivoJaEsclarece = PRODESP_EXPECTED_BUSINESS_ERROR_RE.test(motivo);
  const escopoEvitar = !scope || /substatus|dados principais/i.test(String(scope));

  if (motivoJaEsclarece || escopoEvitar) {
    showToast(motivo, "danger");
    return;
  }
  showToast(`Não foi possível salvar (${scope}): ${motivo}`, "danger");
}

function prodespGetPersistedStatusSubstatus(mode) {
  const isEdit = mode === "edit";
  const status = isEdit
    ? (editPersistedStatus || (originalData && originalData.status_atendimento) || "").trim()
    : (
        createPersistedStatus ||
        (currentCreateModalAtendimentoId ? "Em Atendimento" : "")
      ).trim();
  const sub = isEdit
    ? (
        editPersistedSubstatus ||
        editFlowBaselineSubstatus ||
        (originalData && originalData.substatus_atendimento) ||
        ""
      ).trim()
    : (
        createPersistedSubstatus ||
        createFlowBaselineSubstatus ||
        SUBSTATUS_INICIAL_FILA
      ).trim();
  return { status, sub };
}

/** Restaura status/substatus persistidos após validação bloqueada. */
function prodespRevertStatusSubstatusParaPersistido(mode) {
  const { status, sub } = prodespGetPersistedStatusSubstatus(mode);
  if (!status && !sub) return;
  prodespRevertStatusSubstatusParaValor(mode, status, sub);
  if (mode === "edit") {
    editLastModalSubstatus = sub;
  }
  if (mode === "edit" && autoSaveEditTimeout) clearTimeout(autoSaveEditTimeout);
  if (mode === "create" && typeof autoSaveTimeout !== "undefined" && autoSaveTimeout) {
    clearTimeout(autoSaveTimeout);
  }
}

/** Campos obrigatórios pendentes antes de permitir salvar/finalizar. */
function prodespNotifyValidationBlocked(emptyFields, intro, revertMode) {
  if (!emptyFields || emptyFields.length === 0) return;
  if (revertMode) {
    prodespRevertStatusSubstatusParaPersistido(revertMode);
  }
  const prefix = intro || "Preencha os campos obrigatórios";
  showToast(`${prefix}: ${emptyFields.join(", ")}.`, "warning");
}

function prodespNotifyNetworkFailure(scope) {
  prodespNotifySaveFailure(scope, "Falha de comunicação com o servidor. Verifique sua conexão e tente novamente.");
}

/** Mensagem legível quando fetch/rede falha (evita "Failed to fetch" para o analista). */
function prodespFriendlyFetchError(err) {
  if (!err) {
    return "Falha de comunicação com o servidor. Verifique sua conexão e tente novamente.";
  }
  const m = String(err.message || err);
  if (/failed to fetch|networkerror|network error|load failed|aborted|timeout/i.test(m)) {
    return "Falha de comunicação com o servidor. Verifique sua conexão e tente novamente.";
  }
  return m;
}

/** Revalida ID VGR imediatamente antes de criar atendimento (evita modal stale). */
async function prodespRevalidarIdVgrParaCreate(idVgr) {
  const trimmed = (idVgr || "").trim();
  if (!trimmed) return { proceed: true };
  try {
    const checkResponse = await fetch(
      `/prodesp/atendimentos/verificar_id_vgr/${encodeURIComponent(trimmed)}`
    );
    const checkData = await checkResponse.json();
    if (!checkData.aviso) return { proceed: true };
    if (checkData.action_type === "redirect_edit") {
      return {
        proceed: false,
        redirectEdit: true,
        atendimentoId: checkData.atendimento_id,
        message: checkData.mensagem,
      };
    }
    if (checkData.action_type === "block_creation") {
      return { proceed: false, block: true, message: checkData.mensagem };
    }
    return { proceed: true, warn: checkData.mensagem };
  } catch (err) {
    return {
      proceed: false,
      block: true,
      message: prodespFriendlyFetchError(err),
    };
  }
}

function prodespRedirecionarCreateParaEdicao(atendimentoId, message) {
  const msg =
    message ||
    "Este agendamento já foi iniciado. Redirecionando para o atendimento em andamento.";
  showToast(msg, "info");
  const createModalEl = document.getElementById("createModal");
  const inst = createModalEl ? bootstrap.Modal.getInstance(createModalEl) : null;
  if (inst) inst.hide();
  if (atendimentoId) {
    setTimeout(() => editDetails(atendimentoId), 500);
  }
}

function prodespTratarRespostaCreateDuplicada(httpRes, result) {
  if (
    httpRes &&
    httpRes.status === 409 &&
    result &&
    result.action_type === "redirect_edit" &&
    result.atendimento_id
  ) {
    prodespRedirecionarCreateParaEdicao(result.atendimento_id, result.message);
    return true;
  }
  return false;
}

function prodespRevertSubstatusAposConflito(mode) {
  const ctx = mode === "create" ? "create" : "edit";
  const persisted =
    mode === "create"
      ? createPersistedSubstatus
      : editPersistedSubstatus || editFlowBaselineSubstatus;
  const subEl = document.getElementById(`${ctx}Substatus`);
  const statusEl = document.getElementById(`${ctx}Status`);
  if (!subEl || !persisted) return;
  suppressAguardandoClienteChange = true;
  prodespSuppressAutosave = true;
  setSubstatusWithFlow(subEl, statusEl, persisted, ctx, ctx);
  prodespSuppressAutosave = false;
  suppressAguardandoClienteChange = false;
}

function prodespTratarRespostaSubstatusConflict(httpRes, result, mode) {
  if (!httpRes || httpRes.status !== 409 || !result || !result.message) return false;
  const isConflict =
    result.action_type === "substatus_conflict" ||
    /já assumiu este atendimento/i.test(String(result.message));
  if (!isConflict) return false;
  prodespRevertSubstatusAposConflito(mode);
  setTimeout(() => location.reload(), 4000);
  return true;
}

/**
 * Após falha no POST /atendimentos/update (validação, divergência FGT, etc.),
 * restaura Status/Substatus ao último valor persistido — o servidor fez rollback
 * e a UI não deve permanecer em «Concluído» (ou outro status não gravado).
 * Conflito 409 já trata revert + reload.
 * @returns {boolean} true se foi conflito 409
 */
function prodespRevertStatusSubstatusAposFalhaUpdate(mode, httpRes, result) {
  if (prodespTratarRespostaSubstatusConflict(httpRes, result, mode)) {
    return true;
  }
  prodespRevertStatusSubstatusParaPersistido(mode);
  return false;
}

function prodespNormalizeAutoSaveOpts(options) {
  if (typeof options === "boolean") {
    return { showSuccessToast: options, notifyFailure: true, forceIncludeFields: [] };
  }
  const o = options || {};
  return {
    showSuccessToast: !!o.showSuccessToast,
    notifyFailure: o.notifyFailure !== false,
    skipQuebraEncerramentoCheck: !!o.skipQuebraEncerramentoCheck,
    forceIncludeFields: Array.isArray(o.forceIncludeFields) ? o.forceIncludeFields : [],
  };
}

/** Evita auto-save paralelo enquanto o modal de encerramento com Quebra está aberto. */
let prodespQuebraEncerramentoInProgress = false;
/** Evita handlers paralelos no change de substatus (edit tinha 3 listeners async). */
let prodespSubstatusChangeInFlight = false;

/**
 * Controla o estado de carregamento de um botão.
 * @param {HTMLButtonElement} button O botão.
 * @param {boolean} isLoading True para mostrar o spinner, false para reverter.
 * @param {string} [loadingText='Aguarde...'] Texto durante o carregamento.
 */
function setButtonLoading(button, isLoading, loadingText = 'Aguarde...') {
  if (!button) return;

  if (isLoading) {
    if (globalThis.ProdespSubmitGuard) {
      ProdespSubmitGuard.lock(button, { label: loadingText, autoUnlockMs: 120000 });
      return;
    }
    if (!button.dataset.originalContent) {
      button.dataset.originalContent = button.innerHTML;
    }
    const spinner = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
    button.innerHTML = `${spinner} ${loadingText}`;
    button.disabled = true;
  } else {
    if (globalThis.ProdespSubmitGuard) {
      ProdespSubmitGuard.unlock(button);
      return;
    }
    if (button.dataset.originalContent) {
      button.innerHTML = button.dataset.originalContent;
    }
    button.disabled = false;
  }
}

// ------------------------------------------------------------------------------------------------
// FUNÇÕES PARA O CAMPO SUBSTATUS
// ------------------------------------------------------------------------------------------------

const AGUARDANDO_CLIENTE_MIN_CHARS = 10;
const QUEBRA_ATENDIMENTO_MIN_CHARS = 10;
let suppressQuebraEncerramentoChange = false;

// Evita reentrância quando mudamos o select via código
let suppressAguardandoClienteChange = false;

/** Substatus persistido após último salvamento bem-sucedido (edição). */
let editPersistedSubstatus = "";

/** Status persistido após último salvamento bem-sucedido (edição). */
let editPersistedStatus = "";

/** Substatus persistido após último salvamento bem-sucedido (criação). */
let createPersistedSubstatus = "";

/** Status persistido após último salvamento bem-sucedido (criação). */
let createPersistedStatus = "";

/** Etapa base do fluxo quando substatus atual é "Aguardando Cliente" (edição). */
let editFlowBaselineSubstatus = "";

/** Etapa base do fluxo quando substatus atual é "Aguardando Cliente" (criação). */
let createFlowBaselineSubstatus = "";

/** Substatus atual no modal de edição (para detectar retrocesso no fluxo). */
let editLastModalSubstatus = "";

function formatObservacaoDataHoraProdesp() {
  const agora = new Date();
  const fmt2 = (n) => String(n).padStart(2, "0");
  return (
    fmt2(agora.getDate()) +
    "/" +
    fmt2(agora.getMonth() + 1) +
    "/" +
    agora.getFullYear() +
    " " +
    fmt2(agora.getHours()) +
    ":" +
    fmt2(agora.getMinutes()) +
    ":" +
    fmt2(agora.getSeconds())
  );
}

const PRODESP_ETAPAS_LIBERACAO_ANALISTA = [
  {
    filaSubstatuses: [SUBSTATUS_AGUARDA_GESTAO, "Triagem"],
    fieldKey: "AnalistaAtuante",
    label: "Gestão",
    flowIdx: 0,
  },
  {
    filaSubstatuses: ["Aguardando Config. Remota"],
    fieldKey: "AnalistaConfiguracao",
    label: "Configuração Remota",
    flowIdx: 2,
  },
  {
    filaSubstatuses: ["Aguardando Config. MPLS"],
    fieldKey: "mpls",
    label: "MPLS",
    flowIdx: 4,
  },
  {
    filaSubstatuses: ["Aguardando Caderno de Teste"],
    fieldKey: "AnalistaCadernoTeste",
    label: "Caderno de Teste",
    flowIdx: 6,
  },
];

function prodespLimparCampoAnalistaEtapa(context, fieldKey) {
  const prefix = context === "edit" ? "edit" : "create";
  if (fieldKey === "mpls") {
    if (!prodespGetAnalistaMplsValor(context)) return false;
    prodespSetAnalistaMplsValor(context, "");
    prodespUpdateAnalistaMplsUi(context, document.getElementById(`${prefix}Substatus`)?.value, {
      formDisabled: false,
    });
    return true;
  }
  const el = document.getElementById(`${prefix}${fieldKey}`);
  if (!el || !(el.value || "").trim()) return false;
  el.value = "";
  el.dispatchEvent(new Event("input", { bubbles: true }));
  return true;
}

function prodespLimparAnalistaComObservacao(context, fieldKey, etapaLabel) {
  const prefix = context === "edit" ? "edit" : "create";
  let nomeAnterior = "";
  if (fieldKey === "mpls") {
    nomeAnterior = prodespGetAnalistaMplsValor(context);
    if (!nomeAnterior) return;
    prodespLimparCampoAnalistaEtapa(context, fieldKey);
  } else {
    const el = document.getElementById(`${prefix}${fieldKey}`);
    if (!el) return;
    nomeAnterior = (el.value || "").trim();
    if (!nomeAnterior) return;
    prodespLimparCampoAnalistaEtapa(context, fieldKey);
  }
  const sub = (document.getElementById(`${prefix}Substatus`)?.value || "").trim();
  const obsObj = {
    data_observacao: formatObservacaoDataHoraProdesp(),
    observacao_prodesp: `[${sub || etapaLabel}] Atendimento liberado na etapa ${etapaLabel}. Analista anterior: ${nomeAnterior}.`,
  };
  if (context === "edit") {
    newObservacao.push(obsObj);
  } else {
    newObservacaoCreate.push(obsObj);
  }
  appendObservacaoToUI(context, obsObj);
}

/**
 * Zera analista(s) da etapa ao entrar em fila Aguardando ou retroceder no fluxo.
 * @param {{ comObservacao?: boolean }} opts — false: só limpa campos (pós-save / alinhar UI ao backend)
 */
function prodespAplicarLiberacaoAnalistasCampos(context, oldSub, newSub, opts = {}) {
  const comObservacao = opts.comObservacao !== false;
  const oldNorm = prodespNormalizarSubstatusFluxo((oldSub || "").trim());
  const newNorm = prodespNormalizarSubstatusFluxo((newSub || "").trim());
  if (!newNorm || oldNorm === newNorm) return;

  const newIdx = prodespIndiceFluxoSubstatus(newNorm);
  const oldIdx = prodespIndiceFluxoSubstatus(oldNorm);

  PRODESP_ETAPAS_LIBERACAO_ANALISTA.forEach((etapa) => {
    const entrouFila = etapa.filaSubstatuses.some(
      (s) => prodespNormalizarSubstatusFluxo(s) === newNorm
    );
    const retrocedeuEtapa =
      newIdx >= 0 && oldIdx >= 0 && newIdx < oldIdx && etapa.flowIdx > newIdx;
    if (!entrouFila && !retrocedeuEtapa) return;
    if (comObservacao) {
      prodespLimparAnalistaComObservacao(context, etapa.fieldKey, etapa.label);
    } else {
      prodespLimparCampoAnalistaEtapa(context, etapa.fieldKey);
    }
  });
}

/** Mantém originalData alinhado aos campos de analista visíveis no modal. */
function prodespSyncOriginalDataAnalistasFromDom(context) {
  if (context !== "edit" || !originalData) return;
  const pairs = [
    ["AnalistaAtuante", ["analista_atuante"]],
    ["AnalistaConfiguracao", ["analista_configuracao"]],
    ["AnalistaCadernoTeste", ["analista_caderno_teste", "analista_caderno_teste_atendimentos"]],
  ];
  pairs.forEach(([suffix, keys]) => {
    const el = document.getElementById(`edit${suffix}`);
    if (!el) return;
    const val = (el.value || "").trim();
    keys.forEach((k) => {
      originalData[k] = val;
    });
  });
  if (typeof prodespGetAnalistaMplsValor === "function") {
    originalData.analista_mpls_atendimentos = prodespGetAnalistaMplsValor("edit");
  }
}

/** Limpa analista da etapa ao voltar ou colocar em fila Aguardando. */
function prodespProcessarLiberacaoAnalistas(context, oldSub, newSub) {
  prodespAplicarLiberacaoAnalistasCampos(context, oldSub, newSub, {
    comObservacao: true,
  });
}

function prodespApplyAnalistaImplantacaoAdminUi(context, formDisabled) {
  const isAdmin = prodespIsAdminUser();
  const datalistId = "prodespAnalistasImplantacaoDatalist";
  ["AnalistaAtuante", "AnalistaConfiguracao", "AnalistaCadernoTeste"].forEach((suffix) => {
    const el = document.getElementById(`${context}${suffix}`);
    if (!el) return;
    if (isAdmin && !formDisabled) {
      el.readOnly = false;
      if (document.getElementById(datalistId)) {
        el.setAttribute("list", datalistId);
      }
    } else {
      el.readOnly = true;
      el.removeAttribute("list");
    }
  });
}

function getPersistedSubstatus(mode) {
  return mode === "edit"
    ? (editPersistedSubstatus || "").trim()
    : (createPersistedSubstatus || "").trim();
}

function isEnteringAguardaExterno(mode) {
  const prefix = mode === "edit" ? "edit" : "create";
  const statusEl = document.getElementById(`${prefix}Status`);
  const subEl = document.getElementById(`${prefix}Substatus`);
  if (!statusEl || !subEl) return false;
  if (statusEl.value !== "Em Atendimento") return false;

  const subNow = (subEl.value || "").trim();
  const subWas = getPersistedSubstatus(mode);

  return PRODESP_SUBSTATUS_AGUARDA_EXTERNO.has(subNow) && subNow !== subWas;
}

/** @deprecated use isEnteringAguardaExterno */
function isEnteringAguardandoCliente(mode) {
  return isEnteringAguardaExterno(mode);
}

function prodespGetPersistedStatus(mode) {
  return mode === "edit"
    ? (editPersistedStatus || "").trim()
    : (createPersistedStatus || "").trim();
}

function prodespIsSubstatusQuebra(substatus) {
  const s = (substatus || "").trim();
  if (PRODESP_SUBSTATUS_QUEBRA_TBRA.includes(s)) return false;
  return s.startsWith("Quebra");
}

function prodespIsSubstatusQuebraTbra(substatus) {
  return PRODESP_SUBSTATUS_QUEBRA_TBRA.includes((substatus || "").trim());
}

function prodespWasQuebraEncerrado(mode) {
  const st = prodespGetPersistedStatus(mode);
  const sub = getPersistedSubstatus(mode);
  if (st === "Quebra" && prodespIsSubstatusQuebra(sub)) return true;
  if (st === STATUS_QUEBRA_TBRA && prodespIsSubstatusQuebraTbra(sub)) return true;
  return false;
}

function isEnteringQuebraEncerramento(mode) {
  const prefix = mode === "edit" ? "edit" : "create";
  const statusEl = document.getElementById(`${prefix}Status`);
  const subEl = document.getElementById(`${prefix}Substatus`);
  if (!statusEl || !subEl) return false;
  const statusNow = (statusEl.value || "").trim();
  const subNow = (subEl.value || "").trim();
  const isQuebraNormal = statusNow === "Quebra" && prodespIsSubstatusQuebra(subNow);
  const isQuebraTbra = statusNow === STATUS_QUEBRA_TBRA && prodespIsSubstatusQuebraTbra(subNow);
  if (!isQuebraNormal && !isQuebraTbra) return false;
  if (prodespWasQuebraEncerrado(mode) && getPersistedSubstatus(mode) === subNow) {
    return false;
  }
  return !prodespWasQuebraEncerrado(mode) || getPersistedSubstatus(mode) !== subNow;
}

function prodespValidateMotivosQuebraObrigatorios(context) {
  const statusEl = document.getElementById(context === "edit" ? "editStatus" : "createStatus");
  const subEl = document.getElementById(context === "edit" ? "editSubstatus" : "createSubstatus");
  if (!statusEl || !subEl) return [];
  if ((statusEl.value || "").trim() !== "Quebra") return [];
  if (!prodespIsSubstatusQuebra(subEl.value)) return [];
  const motivos = window.coletarMotivosSelecionados(context);
  if (motivos.length < 1) return ["Fora do padrão (ao menos 1 motivo)"];
  return [];
}

/** Garante modal auxiliar fora do editModal/createModal (evita backdrop preso). */
function prodespEnsureModalOnBody(modalEl) {
  if (window.ProdespModal && typeof window.ProdespModal.ensureOnBody === "function") {
    window.ProdespModal.ensureOnBody(modalEl);
    return;
  }
  if (modalEl && modalEl.parentElement !== document.body) {
    document.body.appendChild(modalEl);
  }
}

function prodespOpenModal(modalEl, options = {}) {
  if (window.ProdespModal && typeof window.ProdespModal.open === "function") {
    return window.ProdespModal.open(modalEl, options);
  }
  prodespEnsureModalOnBody(modalEl);
  const inst = bootstrap.Modal.getOrCreateInstance(modalEl, options);
  inst.show();
  return inst;
}

function prodespShowStackedModal(modalEl, options = {}) {
  prodespEnsureModalOnBody(modalEl);
  const useBackdrop = options.backdrop ?? "static";
  const bsModal = bootstrap.Modal.getOrCreateInstance(modalEl, {
    backdrop: useBackdrop,
    keyboard: options.keyboard ?? false,
  });
  modalEl.addEventListener(
    "shown.bs.modal",
    () => {
      if (window.ProdespModal && typeof window.ProdespModal.syncModalStack === "function") {
        window.ProdespModal.syncModalStack();
        return;
      }
      const openCount = document.querySelectorAll(".modal.show").length;
      if (openCount < 2) return;
      const z = 1055 + (openCount - 1) * 20;
      modalEl.style.zIndex = String(z);
      if (useBackdrop !== false) {
        const backdrops = document.querySelectorAll(".modal-backdrop.show");
        if (backdrops.length) {
          backdrops[backdrops.length - 1].style.zIndex = String(z - 10);
        }
      }
    },
    { once: true }
  );
  modalEl.addEventListener(
    "hidden.bs.modal",
    () => {
      window.setTimeout(() => {
        if (window.ProdespModal && typeof window.ProdespModal.syncModalStack === "function") {
          window.ProdespModal.syncModalStack();
        }
      }, 0);
    },
    { once: true }
  );
  bsModal.show();
  return bsModal;
}

window.prodespEnsureModalOnBody = prodespEnsureModalOnBody;
window.prodespOpenModal = prodespOpenModal;
window.prodespShowStackedModal = prodespShowStackedModal;
window.reloadLogs = reloadLogs;

/**
 * Sincroniza toolbar do caderno de teste com o substatus do modal de edição.
 * @param {string} [substatusOpt] — se informado, usa este valor (evita leitura após revert do auto-save).
 */
async function prodespSyncCadernoToolbarAll(editSubstatusOpt) {
  if (typeof window.prodespEnsureModalScripts === "function") {
    try {
      await window.prodespEnsureModalScripts(["caderno", "certificado"]);
    } catch (err) {
      console.warn("Caderno de teste: falha ao carregar script da toolbar.", err);
      return;
    }
  }
  if (typeof window.prodespCadernoAtualizarToolbar !== "function") return;
  window.prodespCadernoAtualizarToolbar(editSubstatusOpt);
}

async function prodespSyncCadernoToolbarEdit(substatusOpt) {
  await prodespSyncCadernoToolbarAll(substatusOpt);
}

function prodespRevertStatusSubstatusParaValor(mode, statusValor, substatusValor) {
  const prefix = mode === "edit" ? "edit" : "create";
  const statusEl = document.getElementById(`${prefix}Status`);
  const subEl = document.getElementById(`${prefix}Substatus`);
  if (!statusEl || !subEl) return;
  suppressQuebraEncerramentoChange = true;
  suppressAguardandoClienteChange = true;
  prodespSuppressAutosave = true;
  const statusEfetivo =
    (statusValor || "").trim() ||
    (mode === "create" && currentCreateModalAtendimentoId ? "Em Atendimento" : "");
  statusEl.value = statusEfetivo;
  setSubstatusWithFlow(subEl, statusEl, substatusValor || "", mode, prefix);
  prodespSuppressAutosave = false;
  suppressQuebraEncerramentoChange = false;
  suppressAguardandoClienteChange = false;
  if (mode === "edit") {
    void prodespSyncCadernoToolbarEdit(substatusValor);
  }
}

async function openQuebraAtendimentoModal(substatusLabel) {
  const modalEl = document.getElementById("quebraAtendimentoModal");
  const inputEl = document.getElementById("quebraAtendimentoTexto");
  const counterEl = document.getElementById("quebraAtendimentoCounter");
  const btnSave = document.getElementById("quebraAtendimentoSalvar");
  const btnCancel = document.getElementById("quebraAtendimentoCancelar");
  const helpEl = document.getElementById("quebraAtendimentoHelp");
  const subLabelEl = document.getElementById("quebraAtendimentoSubstatusLabel");
  if (!modalEl || !inputEl || !btnSave || !btnCancel) {
    showToast("Modal de Quebra não encontrado no HTML.", "danger");
    return { action: "cancel" };
  }

  if (subLabelEl) subLabelEl.textContent = substatusLabel || "Quebra";
  inputEl.value = "";
  const updateCounter = () => {
    const n = (inputEl.value || "").trim().length;
    if (counterEl) counterEl.textContent = `${n}/${QUEBRA_ATENDIMENTO_MIN_CHARS}`;
    const ok = n >= QUEBRA_ATENDIMENTO_MIN_CHARS;
    btnSave.disabled = !ok;
    if (helpEl) helpEl.classList.toggle("text-danger", !ok);
    if (helpEl) helpEl.classList.toggle("text-muted", ok);
  };
  inputEl.oninput = updateCounter;
  updateCounter();

  const bsModal = prodespShowStackedModal(modalEl);

  return await new Promise((resolve) => {
    let settled = false;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      btnSave.removeEventListener("click", onSave);
      btnCancel.removeEventListener("click", onCancel);
      modalEl.removeEventListener("hidden.bs.modal", onHidden);
      resolve(result);
    };
    const onHidden = () => finish({ action: "cancel" });
    const onCancel = () => {
      bsModal.hide();
    };
    const onSave = async () => {
      const texto = (inputEl.value || "").trim();
      if (texto.length < QUEBRA_ATENDIMENTO_MIN_CHARS) return;
      finish({ action: "save", texto });
      bsModal.hide();
    };
    btnSave.addEventListener("click", onSave);
    btnCancel.addEventListener("click", onCancel);
    modalEl.addEventListener("hidden.bs.modal", onHidden);
    setTimeout(() => inputEl.focus(), 50);
  });
}

/**
 * Fluxo obrigatório ao encerrar com Status Quebra + substatus Quebra *.
 * Retorna true se o fluxo foi acionado (independente de sucesso/cancelamento).
 */
async function prodespRunQuebraEncerramentoFlow(mode, substatusSelectEl, statusSelectEl) {
  if (suppressQuebraEncerramentoChange || prodespQuebraEncerramentoInProgress) return false;
  if (!isEnteringQuebraEncerramento(mode)) return false;

  const subNow = (substatusSelectEl.value || "").trim();
  const statusNow = (statusSelectEl.value || "").trim();
  const isQuebraTbra = statusNow === STATUS_QUEBRA_TBRA;
  const statusTarget = isQuebraTbra ? STATUS_QUEBRA_TBRA : "Quebra";
  const prevStatus =
    prodespGetPersistedStatus(mode) ||
    (mode === "edit" ? (originalData?.status_atendimento || "Em Atendimento") : "Em Atendimento");
  const prevSub =
    getPersistedSubstatus(mode) ||
    (mode === "edit"
      ? (originalData?.substatus_atendimento || "Triagem")
      : SUBSTATUS_INICIAL_FILA);

  if (!isQuebraTbra) {
    const motivosMissing = prodespValidateMotivosQuebraObrigatorios(mode);
    if (motivosMissing.length > 0) {
      prodespRevertStatusSubstatusParaValor(mode, prevStatus, prevSub);
      prodespNotifyValidationBlocked(
        motivosMissing,
        "Para encerrar com Quebra, selecione ao menos um motivo em Fora do padrão"
      );
      return true;
    }
  }

  prodespRevertStatusSubstatusParaValor(mode, prevStatus, prevSub);
  if (mode === "edit" && autoSaveEditTimeout) clearTimeout(autoSaveEditTimeout);
  if (mode === "create" && typeof autoSaveTimeout !== "undefined" && autoSaveTimeout) {
    clearTimeout(autoSaveTimeout);
  }

  prodespQuebraEncerramentoInProgress = true;
  let ok = false;
  try {
    const saidaOk =
      typeof prodespRunObservacaoSaidaPreQuebra === "function"
        ? await prodespRunObservacaoSaidaPreQuebra(mode, prevSub)
        : true;
    if (!saidaOk) {
      return true;
    }

    const res = await openQuebraAtendimentoModal(subNow);
    if (res.action !== "save") {
      const arrStaging = mode === "edit" ? newObservacao : newObservacaoCreate;
      if (arrStaging && typeof prodespDescartarObservacaoTransicaoStaging === "function") {
        arrStaging
          .filter((o) => o._transicaoStaging)
          .slice()
          .forEach((o) => prodespDescartarObservacaoTransicaoStaging(mode, o));
      }
      return true;
    }

    suppressQuebraEncerramentoChange = true;
    statusSelectEl.value = statusTarget;
    populateSubstatus(substatusSelectEl, statusTarget, subNow, undefined, undefined, mode, {
      emitChange: false,
    });
    substatusSelectEl.value = subNow;
    suppressQuebraEncerramentoChange = false;

    if (mode === "edit" && autoSaveEditTimeout) clearTimeout(autoSaveEditTimeout);
    if (mode === "create" && typeof autoSaveTimeout !== "undefined" && autoSaveTimeout) {
      clearTimeout(autoSaveTimeout);
    }

    const saveOpts = {
      showSuccessToast: false,
      notifyFailure: true,
      skipQuebraEncerramentoCheck: true,
      forceIncludeFields: ["status", "substatus"],
    };

    if (typeof prodespStageObservacaoQuebraEncerramento === "function") {
      prodespStageObservacaoQuebraEncerramento({
        data_observacao: formatObservacaoDataHoraProdesp(),
        observacao_prodesp: `[${subNow}] ${res.texto}`,
      });
    }

    ok =
      mode === "edit"
        ? await autoSaveEditModalData(saveOpts)
        : await autoSaveCreateModalData(saveOpts);

    if (!ok) {
      showToast(
        "Encerramento com Quebra não concluído. Status e substatus anteriores foram restaurados.",
        "warning"
      );
      prodespRevertStatusSubstatusParaValor(mode, prevStatus, prevSub);
      return true;
    }

    prodespNotifySaveSuccess(mode === "edit" ? "edit" : "create");

    if (mode === "edit") {
      editPersistedStatus = (document.getElementById("editStatus")?.value || "").trim();
      editPersistedSubstatus = (document.getElementById("editSubstatus")?.value || "").trim();
    } else {
      createPersistedStatus = (document.getElementById("createStatus")?.value || "").trim();
      createPersistedSubstatus = (document.getElementById("createSubstatus")?.value || "").trim();
    }
    return true;
  } finally {
    prodespQuebraEncerramentoInProgress = false;
  }
}

function setSubstatusWithFlow(subEl, statusEl, valueToSet, mode, context) {
  populateSubstatus(
    subEl,
    statusEl.value,
    valueToSet,
    undefined,
    undefined,
    context,
    { emitChange: false }
  );

  // garante substatus paralelos no fluxo Em Atendimento (somente nomenclatura atual)
  if (statusEl.value === "Em Atendimento") {
    PRODESP_SUBSTATUS_PARALELOS_SELECT.forEach((par) => {
      if (![...subEl.options].some((o) => o.value === par)) {
        subEl.add(new Option(par, par));
      }
    });
  }
}

function appendObservacaoToUI(mode, obsObj) {
  try {
    if (typeof renderObservacaoCard !== "function") return;
    const containerId = mode === "edit" ? "log-observacao-edit" : "log-observacao-create";
    const container = document.getElementById(containerId);
    if (!container) return;

    const targetArray = mode === "edit" ? newObservacao : newObservacaoCreate;
    const deletedArray = mode === "edit" ? deletedObservacaoIds : [];
    renderObservacaoCard(obsObj, container, targetArray, deletedArray);
  } catch (e) {
    console.warn("Falha ao renderizar observação na UI:", e);
  }
}

async function openAguardandoClienteModal(mode, substatusLabel, subWas) {
  const modalEl = document.getElementById("aguardandoClienteModal");
  const inputEl = document.getElementById("aguardandoClienteTexto");
  const counterEl = document.getElementById("aguardandoClienteCounter");
  const btnSave = document.getElementById("aguardandoClienteSalvar");
  const btnCancel = document.getElementById("aguardandoClienteCancelar");
  const helpEl = document.getElementById("aguardandoClienteHelp");
  const titleEl = document.getElementById("aguardandoClienteModalLabel");
  const bodyEl = document.getElementById("aguardandoClienteDescricao");
  if (!modalEl || !inputEl || !btnSave || !btnCancel) {
    showToast("Modal de aguardo externo não encontrado no HTML.", "danger");
    return { action: "cancel" };
  }

  const entradaLabel = substatusLabel || SUBSTATUS_AGUARDANDO_CLIENTE;
  const baseModal = {
    titleText: entradaLabel,
    bodyText:
      "Descreva o ocorrido. Este texto será salvo em Observações.",
    entradaLabel,
  };
  const copy =
    typeof prodespEnriquecerModalObsTransicaoEntrada === "function"
      ? prodespEnriquecerModalObsTransicaoEntrada(subWas, baseModal)
      : baseModal;
  if (titleEl) titleEl.textContent = copy.titleText;
  if (bodyEl) bodyEl.textContent = copy.bodyText;

  inputEl.value = "";
  const updateCounter = () => {
    const n = (inputEl.value || "").trim().length;
    if (counterEl) counterEl.textContent = `${n}/${AGUARDANDO_CLIENTE_MIN_CHARS}`;
    const ok = n >= AGUARDANDO_CLIENTE_MIN_CHARS;
    btnSave.disabled = !ok;
    if (helpEl) helpEl.classList.toggle("text-danger", !ok);
    if (helpEl) helpEl.classList.toggle("text-muted", ok);
  };
  inputEl.oninput = updateCounter;
  updateCounter();

  const bsModal = prodespShowStackedModal(modalEl);

  return await new Promise((resolve) => {
    let settled = false;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      btnSave.removeEventListener("click", onSave);
      btnCancel.removeEventListener("click", onCancel);
      modalEl.removeEventListener("hidden.bs.modal", onHidden);
      resolve(result);
    };
    const onHidden = () => finish({ action: "cancel" });
    const onCancel = () => {
      bsModal.hide();
    };
    const onSave = async () => {
      const texto = (inputEl.value || "").trim();
      if (texto.length < AGUARDANDO_CLIENTE_MIN_CHARS) return;
      finish({ action: "save", texto });
      bsModal.hide();
    };

    btnSave.addEventListener("click", onSave);
    btnCancel.addEventListener("click", onCancel);
    modalEl.addEventListener("hidden.bs.modal", onHidden);

    setTimeout(() => inputEl.focus(), 50);
  });
}

/**
 * Fluxo único para Aguardando Cliente / Aguarda Contratada / Aguarda Licença.
 * Retorna true se o fluxo foi acionado (sucesso ou cancelamento).
 */
async function prodespRunAguardaExternoSubstatusFlow(mode, substatusSelectEl, statusSelectEl) {
  if (suppressAguardandoClienteChange) return false;
  if (!isEnteringAguardaExterno(mode)) return false;

  const targetSub = (substatusSelectEl.value || "").trim();
  const prev = getPersistedSubstatus(mode) || "Triagem";
  suppressAguardandoClienteChange = true;
  setSubstatusWithFlow(substatusSelectEl, statusSelectEl, prev, mode, mode);
  suppressAguardandoClienteChange = false;

  if (mode === "edit" && autoSaveEditTimeout) clearTimeout(autoSaveEditTimeout);
  if (mode === "create" && typeof autoSaveTimeout !== "undefined" && autoSaveTimeout) {
    clearTimeout(autoSaveTimeout);
  }

  const res = await openAguardandoClienteModal(mode, targetSub, prev);
  if (res.action !== "save") {
    return true;
  }

  suppressAguardandoClienteChange = true;
  setSubstatusWithFlow(substatusSelectEl, statusSelectEl, targetSub, mode, mode);
  suppressAguardandoClienteChange = false;

  const obsPrefix = `[${targetSub}]`;
  const obsObj =
    typeof prodespRegistrarObservacaoTransicaoStaging === "function"
      ? prodespRegistrarObservacaoTransicaoStaging(mode, obsPrefix, res.texto)
      : (() => {
          const fallback = {
            data_observacao: formatObservacaoDataHoraProdesp(),
            observacao_prodesp: `${obsPrefix} ${res.texto}`,
            _transicaoStaging: true,
          };
          if (mode === "edit") {
            newObservacao.push(fallback);
          } else {
            newObservacaoCreate.push(fallback);
          }
          appendObservacaoToUI(mode, fallback);
          if (typeof prodespStageTransicaoObservacoes === "function") {
            prodespStageTransicaoObservacoes([fallback]);
          }
          return fallback;
        })();

  const saveFn = mode === "edit" ? autoSaveEditModalData : autoSaveCreateModalData;
  const ok = await saveFn({ showSuccessToast: true, notifyFailure: true });
  if (!ok) {
    if (typeof prodespDescartarObservacaoTransicaoStaging === "function") {
      prodespDescartarObservacaoTransicaoStaging(mode, obsObj);
    }
    showToast(
      `Substatus não alterado: o salvamento de «${targetSub}» não foi concluído. A observação não foi salva e o substatus anterior foi restaurado.`,
      "warning"
    );
    suppressAguardandoClienteChange = true;
    setSubstatusWithFlow(substatusSelectEl, statusSelectEl, prev, mode, mode);
    suppressAguardandoClienteChange = false;
    return true;
  }

  delete obsObj._transicaoStaging;

  if (mode === "edit") {
    editPersistedSubstatus = (document.getElementById("editSubstatus")?.value || "").trim();
    editPersistedStatus = (document.getElementById("editStatus")?.value || "").trim();
    editLastModalSubstatus = editPersistedSubstatus;
  } else {
    createPersistedSubstatus = (document.getElementById("createSubstatus")?.value || "").trim();
    createPersistedStatus = (document.getElementById("createStatus")?.value || "").trim();
  }
  return true;
}

function formatHoraParaInputTime(val) {
  if (val == null || val === "") return "";
  const s = String(val).trim();
  const m = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/.exec(s);
  if (!m) return s;
  const h = String(parseInt(m[1], 10)).padStart(2, "0");
  return `${h}:${m[2]}`;
}

const PRODESP_LAN_EXTRA_JS_KEYS = [
  "mv_ip_lan_sec",
  "mv_rede_lan_sec",
  "mv_ip_lan_ter",
  "mv_rede_lan_ter",
  "mv_ip_lan_qua",
  "mv_rede_lan_qua",
];

const PRODESP_LAN_EXTRA_CIDR_JS_KEYS = new Set([
  "mv_ip_lan_sec",
  "mv_ip_lan_ter",
  "mv_ip_lan_qua",
]);

const PRODESP_MASKED_IP_COLS = new Set([
  "ip_lan_01",
  "ip_lan_transito",
  "loopback_vivo",
  "loopback_cliente",
  "loopback_on_bgp",
  "mv_ip_transito",
  "mv_mask_transito",
  "mv_ip_swt",
  "mv_rede_voz",
  "mv_mask_voz",
  "mv_rede_lan_assoc",
  "mv_mask_lan_assoc",
  "mv_rede_totem",
  "mv_mask_totem",
  "mv_rede_wifi_guest",
  "mv_ip_wifi_guest",
  "mv_dhcp_start_wifi_guest",
  "mv_dhcp_end_wifi_guest",
  "mv_reserva_start_wifi_guest",
  "mv_reserva_end_wifi_guest",
  ...PRODESP_LAN_EXTRA_JS_KEYS,
]);

/** Campos opcionais MV_* (Blueprint CSV) — chaves JS alinhadas ao banco/API. */
const PRODESP_MV_OPCIONAIS_JS_KEYS = [
  "mv_ip_transito",
  "mv_mask_transito",
  "mv_ip_swt",
  "mv_rede_voz",
  "mv_mask_voz",
  "mv_rede_lan_assoc",
  "mv_mask_lan_assoc",
  "mv_rede_totem",
  "mv_mask_totem",
  "mv_rede_wifi_guest",
  "mv_ip_wifi_guest",
  "mv_dhcp_start_wifi_guest",
  "mv_dhcp_end_wifi_guest",
  "mv_reserva_start_wifi_guest",
  "mv_reserva_end_wifi_guest",
];

const PRODESP_MV_CIDR_JS_KEYS = new Set(["mv_ip_wifi_guest"]);

const PRODESP_IP_CIDR_FIELD_SUFFIXES = new Set([
  "IpLan01",
  "MvIpLanSec",
  "MvIpLanTer",
  "MvIpLanQua",
  "MvIpWifiGuest",
]);

function prodespMvOpcionaisKeyMapEntries() {
  const m = {};
  PRODESP_MV_OPCIONAIS_JS_KEYS.forEach((k) => {
    m[k] = `${k}_unidades`;
  });
  return m;
}

function prodespCollectMvOpcionaisFromPrefix(prefix) {
  const out = {};
  PRODESP_MV_OPCIONAIS_JS_KEYS.forEach((col) => {
    const el = document.getElementById(idFor(prefix, col));
    if (!el) return;
    const raw = prodespReadEditableFieldValue(el, col);
    out[col] = PRODESP_MV_CIDR_JS_KEYS.has(col)
      ? prodespStripIpSpaces(raw)
      : prodespSanitizePlainIpValue(raw);
  });
  return out;
}

function prodespLanExtraKeyMapEntries() {
  const m = {};
  PRODESP_LAN_EXTRA_JS_KEYS.forEach((k) => {
    m[k] = `${k}_unidades`;
  });
  return m;
}

function prodespCollectLanExtraFromPrefix(prefix) {
  const out = {};
  PRODESP_LAN_EXTRA_JS_KEYS.forEach((col) => {
    const el = document.getElementById(idFor(prefix, col));
    if (!el) return;
    const raw = prodespReadEditableFieldValue(el, col);
    out[col] = PRODESP_LAN_EXTRA_CIDR_JS_KEYS.has(col)
      ? prodespStripIpSpaces(raw)
      : prodespSanitizePlainIpValue(raw);
  });
  return out;
}

const PRODESP_IPV4_OCTET =
  "(?:25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})";
const PRODESP_IPV4_REGEX = new RegExp(
  `^${PRODESP_IPV4_OCTET}\\.${PRODESP_IPV4_OCTET}\\.${PRODESP_IPV4_OCTET}\\.${PRODESP_IPV4_OCTET}$`
);
const PRODESP_IPV4_CIDR_REGEX = new RegExp(
  `^${PRODESP_IPV4_OCTET}\\.${PRODESP_IPV4_OCTET}\\.${PRODESP_IPV4_OCTET}\\.${PRODESP_IPV4_OCTET}\\/(?:[0-9]|[1-2][0-9]|3[0-2])$`
);

function prodespIsValidIpFieldValue(val, allowCidr) {
  const v = prodespStripIpSpaces(val || "");
  if (!v) return true;
  if (allowCidr) return PRODESP_IPV4_CIDR_REGEX.test(v) || PRODESP_IPV4_REGEX.test(v);
  return PRODESP_IPV4_REGEX.test(v);
}

/** Grava valor no input e na máscara IMask (evita unmaskedValue vazio após setVal). */
function prodespSetMaskedFieldValue(prefix, fieldSuffix, value) {
  const elId = `${prefix}${fieldSuffix}`;
  const el = document.getElementById(elId);
  const v = prodespCoerceInputValue(value);
  if (!el) return;
  const mask = maskInstances[elId];
  if (mask) {
    mask.value = v;
    if (PRODESP_IP_CIDR_FIELD_SUFFIXES.has(fieldSuffix) && v) {
      el.value = v;
    }
  } else {
    el.value = v;
  }
}

/** Lê IP LAN 1 com CIDR preservando o prefixo completo (ex.: /23, não /2). */
function prodespReadIpCidrFieldValue(el) {
  if (!el) return "";
  const mask = maskInstances[el.id];
  const fromEl = prodespStripIpSpaces(String(el.value ?? "").trim());
  if (!mask) return fromEl;
  const fromMask = prodespStripIpSpaces(
    mask.unmaskedValue != null ? String(mask.unmaskedValue).trim() : ""
  );
  const candidates = [fromEl, fromMask].filter(Boolean);
  const withCidr = candidates.filter((v) => v.includes("/"));
  if (withCidr.length) {
    return withCidr.sort((a, b) => b.length - a.length)[0];
  }
  return fromEl || fromMask;
}

/** Lê valor do formulário respeitando máscara; prioriza o que está visível no input. */
function prodespReadEditableFieldValue(el, col) {
  if (!el) return "";
  const mask = maskInstances[el.id];
  const fromEl = String(el.value ?? "").trim();
  if (!mask) return fromEl;
  const fromMask = mask.unmaskedValue != null ? String(mask.unmaskedValue).trim() : "";
  if (col === "latitude" || col === "longitude") {
    return fromEl || fromMask;
  }
  if (col === "ip_lan_01") {
    return prodespReadIpCidrFieldValue(el);
  }
  if (PRODESP_MASKED_IP_COLS.has(col)) {
    return prodespStripIpSpaces(fromEl || fromMask);
  }
  return fromMask || fromEl;
}

/** API do modal usa alias (ex. latitude); keyMap pode apontar para *_unidades. */
function prodespGetOriginalFieldValue(originalData, col, mappedKey) {
  if (!originalData) return "";
  const v = mappedKey ? originalData[mappedKey] : undefined;
  const raw = v !== undefined && v !== null ? v : originalData[col];
  if (raw == null) return "";
  return String(raw);
}

function normalizeComparableValue(col, value) {
  if (value == null) return null;
  const s = typeof value === "string" ? value.trim() : String(value);
  if (s === "") return "";
  if (col === "hora_agendamento") {
    return formatHoraParaInputTime(s) || "";
  }
  if (col === "latitude" || col === "longitude") {
    const n = Number.parseFloat(s.replace(",", "."));
    if (!Number.isFinite(n)) return s;
    return Math.round(n * 1e8) / 1e8;
  }
  if (PRODESP_MASKED_IP_COLS.has(col)) {
    return prodespStripIpSpaces(s);
  }
  return s;
}

function valuesDiffer(col, novo, antigo) {
  const a = normalizeComparableValue(col, novo);
  const b = normalizeComparableValue(col, antigo);
  // trata null/"" como equivalentes para comparação
  if ((a == null || a === "") && (b == null || b === "")) return false;
  // Evita DELETE acidental: antigo preenchido e novo vazio (máscara desincronizada)
  if (
    (a == null || a === "") &&
    b !== "" &&
    b != null &&
    (PRODESP_MASKED_IP_COLS.has(col) || col === "latitude" || col === "longitude")
  ) {
    return false;
  }
  return a !== b;
}

/**
 * Preenche o select de substatus conforme o status.
 * @param {HTMLSelectElement} substatusSelectEl O elemento <select> do substatus.
 * @param {string} statusValue O valor do status selecionado.
 * @param {string} currentSubstatus O valor atual do substatus.
 * @param {string} userDepartment O departamento do usuário (global ou passado).
 * @param {object} gruposFilas Objeto com a configuração de grupos e substatus.
 */
function populateSubstatus(
  substatusSelectEl,
  statusValue,
  currentSubstatus = null,
  userDepartment = typeof USER_DEPARTMENT !== "undefined" ? USER_DEPARTMENT : "TODOS",
  gruposFilas = typeof GRUPOS_FILAS_JS !== "undefined" ? GRUPOS_FILAS_JS : {},
  context,
  populateOpts = {}
) {
  if (!substatusSelectEl) return;

  const valueBefore = (substatusSelectEl.value || "").trim();
  const currentValue = substatusSelectEl.value ? substatusSelectEl.value.trim() : "";
  const statusValueClean = statusValue ? statusValue.trim() : "";
  const substatusToRestoreRaw =
    currentSubstatus !== null ? currentSubstatus.toString().trim() : currentValue;
  const substatusToRestore =
    typeof prodespNormalizarSubstatusFluxo === "function"
      ? prodespNormalizarSubstatusFluxo(substatusToRestoreRaw)
      : substatusToRestoreRaw;

  substatusSelectEl.innerHTML = '<option selected disabled value="">Selecione o Substatus...</option>';
  substatusSelectEl.disabled = !statusValueClean;

  if (!statusValueClean) return;

  let options = [];
  if (statusValueClean === "Em Atendimento") {
    const orderedProgression = [...PRODESP_FLUXO_SUBSTATUS_ORDEM];

    let allowedSubstatusesForSelection = [];
    const previousAllowed = [
      SUBSTATUS_AGUARDA_GESTAO,
      SUBSTATUS_INICIAL_FILA,
      "Aguardando Config. MPLS",
      "Aguardando Caderno de Teste",
    ];

    let baselineForFlow = prodespNormalizarSubstatusFluxo(substatusToRestore);
    if (
      context === "create" &&
      !substatusToRestoreRaw.trim() &&
      !createPersistedSubstatus
    ) {
      baselineForFlow = SUBSTATUS_INICIAL_FILA;
    }
    if (
      substatusToRestore === SUBSTATUS_AGUARDANDO_CLIENTE ||
      prodespIsSubstatusAguardaContratada(substatusToRestore) ||
      substatusToRestore === SUBSTATUS_AGUARDA_LICENCA ||
      substatusToRestore === SUBSTATUS_COM_SUPORTE
    ) {
      if (context === "edit") {
        baselineForFlow = prodespNormalizarSubstatusFluxo(
          editFlowBaselineSubstatus || SUBSTATUS_INICIAL_FILA
        );
      } else if (context === "create") {
        baselineForFlow = prodespNormalizarSubstatusFluxo(
          createFlowBaselineSubstatus || SUBSTATUS_INICIAL_FILA
        );
      }
    }

    if (!baselineForFlow || baselineForFlow === "") {
      if (prodespIsAgendamentoOuGp()) {
        allowedSubstatusesForSelection = [
          PRODESP_FILA_AGUARDANDO_GESTAO,
          SUBSTATUS_AGUARDA_GESTAO,
          ...PRODESP_SUBSTATUS_PARALELOS_AG_GP,
        ];
      } else {
        allowedSubstatusesForSelection = [SUBSTATUS_INICIAL_FILA, "Em Configuração Remota"];
      }
    } else {
      const currentIndex = orderedProgression.indexOf(baselineForFlow);

      if (currentIndex === -1) {
        allowedSubstatusesForSelection = orderedProgression.slice();
      } else if (baselineForFlow === "Aguardando Caderno de Teste") {
        allowedSubstatusesForSelection = orderedProgression.slice();
      } else {
        for (let i = 0; i < orderedProgression.length; i++) {
          const sub = orderedProgression[i];
          if (i < currentIndex) {
            if (previousAllowed.includes(sub)) allowedSubstatusesForSelection.push(sub);
          } else if (i <= currentIndex + 1) {
            allowedSubstatusesForSelection.push(sub);
          }
        }
      }
    }

    orderedProgression.forEach((sub) => {
      if (allowedSubstatusesForSelection.includes(sub)) {
        options.push({ value: sub, text: sub });
      }
    });

    if (
      substatusToRestore === "Triagem" &&
      !options.some((o) => o.value === "Triagem")
    ) {
      options.unshift({ value: "Triagem", text: SUBSTATUS_AGUARDA_GESTAO });
    }

    const paralelos = prodespIsAgendamentoOuGp()
      ? PRODESP_SUBSTATUS_PARALELOS_AG_GP
      : PRODESP_SUBSTATUS_PARALELOS_SELECT;
    paralelos.forEach((par) => {
      if (!options.some((o) => o.value === par)) {
        options.splice(1, 0, { value: par, text: par });
      }
    });

    if (prodespIsAgendamentoOuGp()) {
      const originForAgGp = (
        substatusToRestore ||
        (context === "create" ? SUBSTATUS_INICIAL_FILA : SUBSTATUS_AGUARDA_GESTAO)
      ).trim();
      const allowedDest = prodespDestinosSubstatusAgGp(originForAgGp);
      if (allowedDest.size) {
        options = options.filter((o) => allowedDest.has(o.value));
        if (
          substatusToRestore &&
          !options.some((o) => o.value === substatusToRestore)
        ) {
          options.unshift({
            value: substatusToRestore,
            text:
              substatusToRestore === "Triagem"
                ? SUBSTATUS_AGUARDA_GESTAO
                : substatusToRestore,
          });
        }
      }
    }
  } else if (statusValueClean === "Concluído") {
    options.push({ value: "Concluído", text: "Concluído" });
  } else if (statusValueClean === "Concluído Parcial") {
    options.push({ value: "Pendente Configuração Remota", text: "Pendente Configuração Remota" }, { value: "Pendente Configuração MPLS", text: "Pendente Configuração MPLS" }, { value: "Quebra Field", text: "Quebra Field" }, { value: "Pendente Link IPD", text: "Pendente Link IPD" }, { value: "Pendente Link MPLS", text: "Pendente Link MPLS" });
  } else if (statusValueClean === "Quebra") {
    options.push(
      { value: "Quebra Link", text: "Quebra Link" },
      { value: "Quebra Infra", text: "Quebra Infra" },
      { value: "Quebra Hardware", text: "Quebra Hardware" },
      { value: "Quebra Field", text: "Quebra Field" },
      { value: "Quebra Cliente", text: "Quebra Cliente" },
      { value: "Quebra Vita", text: "Quebra Vita" }
    );
  } else if (statusValueClean === STATUS_QUEBRA_TBRA) {
    options.push(
      { value: SUBSTATUS_QUEBRA_TBRA_SCI, text: SUBSTATUS_QUEBRA_TBRA_SCI },
      { value: SUBSTATUS_QUEBRA_TBRA_TECNICA, text: SUBSTATUS_QUEBRA_TBRA_TECNICA }
    );
  }

  options.forEach(opt => substatusSelectEl.add(new Option(opt.text, opt.value)));

  // Tenta restaurar o valor anterior. Se estiver vazio (novo atendimento), tenta selecionar "Triagem" por padrão
  let valueToSet = options.some(opt => opt.value === substatusToRestore) ? substatusToRestore : "";
  
  if (valueToSet === "" && options.some((opt) => opt.value === SUBSTATUS_INICIAL_FILA)) {
    valueToSet = SUBSTATUS_INICIAL_FILA;
  } else if (valueToSet === "" && options.length === 1) {
    valueToSet = options[0].value;
  }

  substatusSelectEl.value = valueToSet;

  const valueAfter = (substatusSelectEl.value || "").trim();
  const emitChange = populateOpts.emitChange !== false;
  if (
    emitChange &&
    !suppressAguardandoClienteChange &&
    !suppressQuebraEncerramentoChange &&
    !prodespSuppressAutosave &&
    valueAfter &&
    valueAfter !== valueBefore
  ) {
    substatusSelectEl.dispatchEvent(new Event("change", { bubbles: true }));
  }

  // Preenche analista da etapa ativa (exceto MPLS — terceiro escolhido manualmente)
  if (statusValueClean === "Em Atendimento" && typeof USUARIO_LOGADO !== "undefined" && USUARIO_LOGADO && context) {
    const analystFieldsMap = {
      [SUBSTATUS_AGUARDA_GESTAO]: document.getElementById(`${context}AnalistaAtuante`),
      Triagem: document.getElementById(`${context}AnalistaAtuante`),
      "Em Configuração Remota": document.getElementById(`${context}AnalistaConfiguracao`),
      "Em Caderno de Teste": document.getElementById(`${context}AnalistaCadernoTeste`),
    };

    const selectedSubstatus = substatusSelectEl.value;
    const targetAnalystField = analystFieldsMap[selectedSubstatus];

    if (targetAnalystField && !targetAnalystField.value?.trim()) {
      targetAnalystField.value = USUARIO_LOGADO;
      targetAnalystField.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  if (context) {
    prodespUpdateAnalistaMplsUi(context, substatusSelectEl.value, {
      formDisabled: populateOpts.formDisabled === true,
    });
  }
}

// ------------------------------------------------------------------------------------------------
// FUNÇÃO PARA UPDATE DO MODAL DE EDIÇÃO
// ------------------------------------------------------------------------------------------------
let originalData = {};

/** Após coleta FGT: alinha originalData para o auto-save não reenviar dump antigo. */
function prodespSyncLogsAposColetaFgt(logs) {
  const text = logs || "";
  if (originalData) {
    originalData.logs_atendimento = text;
  }
  if (typeof reloadLogs === "function") {
    const editEl = document.getElementById("log-configuracao-remota-edit");
    if (editEl) reloadLogs(text, editEl, "edit");
    const createEl = document.getElementById("log-configuracao-remota-create");
    if (createEl) reloadLogs(text, createEl, "create");
  }
  ["viewLogs", "detailsLogs"].forEach(function (elId) {
    const ta = document.getElementById(elId);
    if (ta && text) ta.value = text;
  });
}
window.prodespSyncLogsAposColetaFgt = prodespSyncLogsAposColetaFgt;

/**
 * Desabilita/habilita todos os campos do formulário de edição.
 * @param {boolean} isDisabled True para desabilitar, false para habilitar.
 */
function setAllEditFieldsDisabled(isDisabled) {
  const form = document.getElementById("editForm");
  const elements = form.querySelectorAll("input, select, textarea");
  elements.forEach((el) => {
    if (el.type !== "hidden") {
      // Usa 'readOnly' em campos de texto para permitir cópia do conteúdo.
      if (
        el.tagName === "TEXTAREA" ||
        (el.tagName === "INPUT" &&
          ["text", "tel", "email", "number", "url"].includes(el.type))
      ) {
        // Mantém os campos de analista e descrição de equipamentos sempre bloqueados para edição manual
        const isMplsTerceiroField =
          el.classList.contains("prodesp-analista-mpls-select") ||
          el.classList.contains("prodesp-analista-mpls-outros");
        const isAnalystField =
          el.id.toLowerCase().includes("analista") && !isMplsTerceiroField;
        const isDescriptionField = el.id.toLowerCase().includes("equipamentodescricao");
        if (isAnalystField && prodespIsAdminUser() && !isDisabled) {
          el.readOnly = false;
          if (document.getElementById("prodespAnalistasImplantacaoDatalist")) {
            el.setAttribute("list", "prodespAnalistasImplantacaoDatalist");
          }
        } else {
          el.readOnly = (isAnalystField || isDescriptionField) ? true : isDisabled;
        }
      } else {
        // Para 'select', 'checkbox', 'radio' e outros tipos de 'input', usa 'disabled'.
        el.disabled = isDisabled;
      }
    }
  });

  // Desabilita/habilita os botões de "Adicionar"
  document.getElementById("btn-add-observacao-edit").disabled = isDisabled;
  document.getElementById("btn-add-equipamento-edit").disabled = isDisabled;
  document.getElementById("btn-add-link-edit").disabled = isDisabled;
  const subEdit = (document.getElementById("editSubstatus")?.value || "").trim();
  prodespUpdateAnalistaMplsUi("edit", subEdit, { formDisabled: isDisabled });
}


// ------------------------------------------------------------------------------------------------------
// FUNÇÃO PARA AUTO-SALVAR DADOS NO MODAL DE EDIÇÃO
// ------------------------------------------------------------------------------------------------------
let autoSaveEditTimeout = null;
/** Bloqueia auto-save durante preenchimento/abertura do modal (evita save ao abrir). */
let prodespSuppressAutosave = false;

function prodespUnidadeObservacoesAtivas() {
  return !!selectedUnidadeId && !currentCreateModalAtendimentoId;
}

/** Libera textarea/botão de observações no modal criar (unidade carregada, atendimento não iniciado). */
function prodespSetCreateUnidadeObservacoesEnabled(enabled) {
  const obsEl = document.getElementById("createObservacaoTexto");
  const addBtn = document.getElementById("btn-add-observacao-create");
  if (obsEl) obsEl.disabled = !enabled;
  if (addBtn) addBtn.disabled = !enabled;
  const obsLog = document.getElementById("log-observacao-create");
  if (obsLog && enabled) {
    obsLog.querySelectorAll("button").forEach((btn) => {
      btn.disabled = false;
    });
  }
}
let existingEquipments = []; // Array para armazenar equipamentos existentes e facilitar a validação
let existingLinks = []; // Array para armazenar links existentes e facilitar a validação
let existingLinksCreate = []; // Array para links no modal de criação
let editingEquipmentId = null; // ID do equipamento em edição
let editingLinkId = null;      // ID do link em edição

async function autoSaveEditModalData(options = false) {
  const { showSuccessToast, notifyFailure, skipQuebraEncerramentoCheck, forceIncludeFields } =
    prodespNormalizeAutoSaveOpts(options);
  let failureNotified = false;
  let failureWasExpectedBusiness = false;
  const fail = (scope, detail) => {
    if (prodespIsExpectedBusinessError(detail)) {
      failureWasExpectedBusiness = true;
    }
    if (notifyFailure) {
      prodespNotifySaveFailure(scope, detail);
      failureNotified = true;
    }
  };

  const id = +document.getElementById("editAtendimentoId").value;
  if (!id) {
    console.warn("Attempted auto-save for edit modal without an existing attendance ID.");
    return false;
  }

  const permEdicao = prodespResolvePermEdicaoModalSalvar(originalData, "edit");
  if (!permEdicao.ok) {
    showToast(permEdicao.msg, "warning");
    return false;
  }
  if (permEdicao.noop) {
    return true;
  }

  const substatusAtual = (document.getElementById("editSubstatus")?.value || "").trim();
  const oldSubAuto = (
    editPersistedSubstatus ||
    (originalData.substatus_atendimento || "").trim() ||
    "Triagem"
  ).trim();
  const dadosFieldMissingAuto = prodespValidateDadosFieldTriagemParaAguardando(
    "edit",
    oldSubAuto,
    substatusAtual
  );
  if (dadosFieldMissingAuto.length > 0) {
    prodespRevertSubstatusParaValor("edit", oldSubAuto || "Triagem");
    prodespNotifyValidationBlocked(
      dadosFieldMissingAuto,
      "Para enviar da Gestão para a fila Aguardando, preencha os Dados Field"
    );
    return false;
  }

  const mplsMissingAuto = prodespValidateAnalistaMplsTerceiro("edit", oldSubAuto, substatusAtual);
  if (mplsMissingAuto.length > 0) {
    prodespRevertSubstatusParaValor("edit", oldSubAuto || "Triagem");
    prodespNotifyValidationBlocked(
      mplsMissingAuto,
      prodespMensagemAnalistaMplsObrigatorio(oldSubAuto, substatusAtual)
    );
    prodespUpdateAnalistaMplsUi("edit", substatusAtual, { formDisabled: false });
    return false;
  }

  const statusAuto = (document.getElementById("editStatus")?.value || "").trim();
  const hostnameMissingAuto = prodespValidateHostnameObrigatorio(
    "edit",
    oldSubAuto,
    substatusAtual,
    statusAuto
  );
  if (hostnameMissingAuto.length > 0) {
    prodespRevertSubstatusParaValor("edit", oldSubAuto || "Triagem");
    prodespNotifyValidationBlocked(
      hostnameMissingAuto,
      "Para sair de «Em Configuração Remota» ou concluir, preencha o Hostname",
      "edit"
    );
    return false;
  }

  const quebraMotivosAuto = prodespValidateMotivosQuebraObrigatorios("edit");
  if (quebraMotivosAuto.length > 0) {
    prodespNotifyValidationBlocked(
      quebraMotivosAuto,
      "Para encerrar com Quebra, selecione ao menos um motivo em Fora do padrão",
      "edit"
    );
    return false;
  }
  if (!skipQuebraEncerramentoCheck && isEnteringQuebraEncerramento("edit")) {
    prodespNotifyValidationBlocked(
      ["Motivo da quebra (observação)"],
      "Selecione o substatus de Quebra novamente para registrar o motivo da quebra",
      "edit"
    );
    return false;
  }

  if (substatusAtual && substatusAtual !== oldSubAuto) {
    prodespAplicarLiberacaoAnalistasCampos("edit", oldSubAuto, substatusAtual, {
      comObservacao: true,
    });
  }

  let savedSomething = false;
  const updates = [];
  const motivosForaPadrao = window.coletarMotivosSelecionados("edit");

  const editableJsFields = [
    "logs",
    "status",
    "substatus",
    "analista_atuante",
    "analista_configuracao",
    "analista_mpls_atendimentos",
    "analista_caderno_teste",
    "contratada",
    "field",
    "contato_field",

    "nome",
    "acronimo",
    "hostname",
    "endereco",
    "numero",
    "bairro",
    "municipio",
    "estado",
    "complemento",
    "data_agendamento",
    "hora_agendamento",
    "cep",
    "latitude",
    "longitude",
    "telefone_contato",
    "ip_lan_01",
    "ip_lan_transito",
    "id_intragov",
    "loopback_vivo",
    "loopback_cliente",
    "loopback_on_bgp",
    "ticket_noc",
    ...PRODESP_MV_OPCIONAIS_JS_KEYS,
    ...PRODESP_LAN_EXTRA_JS_KEYS,
  ];

  const keyMap = {
    status: "status_atendimento",
    substatus: "substatus_atendimento",
    analista_atuante: "analista_atuante",
    analista_configuracao: "analista_configuracao",
    analista_mpls_atendimentos: "analista_mpls_atendimentos",
    analista_caderno_teste: "analista_caderno_teste_atendimentos",
    contratada: "contratada",
    field: "field_responsavel",
    contato_field: "contato_field",
    logs: "logs_atendimento",
    nome: "nome",
    acronimo: "acronimo_unidades",
    hostname: "hostname_unidades",
    endereco: "endereco_unidades",
    numero: "numero_unidades",
    bairro: "bairro_unidades",
    municipio: "municipio_unidades",
    estado: "estado_unidades",
    complemento: "complemento_unidades",
    data_agendamento: "data_agendamento_unidades",
    hora_agendamento: "hora_agendamento_unidades",
    cep: "cep_unidades",
    latitude: "latitude_unidades",
    longitude: "longitude_unidades",
    telefone_contato: "telefone_contato_unidades",
    ip_lan_01: "ip_lan_01_unidades",
    ip_lan_transito: "ip_lan_transito_unidades",
    id_intragov: "id_intragov_unidades",
    loopback_vivo: "loopback_vivo_unidades",
    loopback_cliente: "loopback_cliente_unidades",
    loopback_on_bgp: "loopback_on_bgp_unidades",
    ticket_noc: "ticket_noc_unidades",
    ...prodespMvOpcionaisKeyMapEntries(),
    ...prodespLanExtraKeyMapEntries(),
  };

  editableJsFields.forEach((col) => {
    let novo;
    if (col === "logs") {
      novo = serializeLogEntries(logsEdit);
    } else {
      const el = document.getElementById(idFor("edit", col));
      if (!el) return;
      novo = prodespReadEditableFieldValue(el, col);
    }

    // Previne envio de string vazia para campos de data, hora ou coordenadas (evita erro no MySQL)
    if (novo === "" && ["data_agendamento", "hora_agendamento", "latitude", "longitude"].includes(col)) {
      novo = null;
    }

    const originalKey = keyMap[col];
    if (!originalKey) return;

    const antigo = prodespGetOriginalFieldValue(originalData, col, originalKey);

    const forceField = forceIncludeFields.includes(col);
    const novoTrim = typeof novo === "string" ? novo.trim() : novo;
    if (forceField && (novoTrim == null || novoTrim === "")) {
      return;
    }

    if (valuesDiffer(col, novo, antigo) || forceField) {
      updates.push({
        coluna: col,
        valor: novo,
      });
    }
  });

  let allSuccess = true;
  const hadMainUpdates =
    updates.length > 0 || !window.arraysIguaisNumeros(motivosForaPadrao, motivosForaPadraoOriginalEdit);

  // 1. Campos principais (status, substatus, etc.)
  if (hadMainUpdates) {
    const hasLbUpdate = updates.some((u) =>
      ["loopback_vivo", "loopback_cliente", "loopback_on_bgp"].includes(u.coluna)
    );
    if (hasLbUpdate) {
      const uniqOk = await prodespCheckUniquenessBeforeSave({
        id_unidade: originalData.id_unidades_atendimentos || originalData.id_unidades,
        loopbacks: prodespCollectLoopbacksForUniqueness("edit"),
      }, { context: "edit" });
      if (!uniqOk) {
        fail(null, "Loopback duplicado. Corrija antes de salvar.");
        return;
      }
    }
    try {
      const statusValue = document.getElementById("editStatus")?.value || "";
      const resMain = await fetch("/prodesp/atendimentos/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: id,
          updates: updates,
          motivos_fora_padrao: motivosForaPadrao,
          finalizing: prodespIsFinalStatus(statusValue),
          ...(typeof prodespPayloadObservacoesAtomicasUpdate === "function"
            ? prodespPayloadObservacoesAtomicasUpdate()
            : {
                transicao_observacoes:
                  typeof prodespConsumeTransicaoObservacoes === "function"
                    ? prodespConsumeTransicaoObservacoes()
                    : null,
              }),
        }),
      });
      const resultMain = await resMain.json();
      if (!resultMain.success) {
        fail(null, resultMain.message);
        allSuccess = false;
        prodespRevertStatusSubstatusAposFalhaUpdate("edit", resMain, resultMain);
      } else {
        savedSomething = true;
        if (typeof prodespAplicarObservacoesTransicaoPersistidasNoUpdate === "function") {
          prodespAplicarObservacoesTransicaoPersistidasNoUpdate("edit", resultMain);
        }
        updates.forEach((u) => {
          const mapped = keyMap[u.coluna];
          if (mapped) originalData[mapped] = u.valor;
          if (
            mapped ||
            PRODESP_MASKED_IP_COLS.has(u.coluna) ||
            u.coluna === "latitude" ||
            u.coluna === "longitude"
          ) {
            originalData[u.coluna] = u.valor;
          }
        });
        if (substatusAtual && substatusAtual !== oldSubAuto) {
          prodespAplicarLiberacaoAnalistasCampos("edit", oldSubAuto, substatusAtual, {
            comObservacao: false,
          });
        }
        prodespSyncOriginalDataAnalistasFromDom("edit");
        motivosForaPadraoOriginalEdit = [...motivosForaPadrao];
        editPersistedSubstatus = (document.getElementById("editSubstatus").value || "").trim();
        editPersistedStatus = (document.getElementById("editStatus").value || "").trim();
        void prodespSyncCadernoToolbarEdit();
      }
    } catch (err) {
      fail(null, prodespFriendlyFetchError(err));
      allSuccess = false;
      prodespRevertStatusSubstatusParaPersistido("edit");
      prodespLogUnexpectedSaveFailure("Auto-save (Edit): falha inesperada ao atualizar dados principais.", null, err);
    }
  }

  // 2. Observações — somente após dados principais salvos com sucesso
  if (allSuccess && (newObservacao.length > 0 || deletedObservacaoIds.length > 0)) {
    const obsOk = await prodespSaveAtendimentoObservacoes("edit", {
      toast: false,
      includeTransicaoStaging: true,
    });
    if (obsOk) {
      savedSomething = true;
      newObservacao.forEach((o) => delete o._transicaoStaging);
    } else {
      allSuccess = false;
    }
  } else if (
    !allSuccess &&
    typeof prodespDescartarObservacaoTransicaoStaging === "function"
  ) {
    newObservacao
      .filter((o) => o._transicaoStaging)
      .slice()
      .forEach((o) => prodespDescartarObservacaoTransicaoStaging("edit", o));
  }

  // 3. Salve novo equipamentos e deleta
  if (newEquipamentoEdit.length > 0 || deletedEquipamentoIds.length > 0) {
    const equipmentsToSave = [...newEquipamentoEdit];
    newEquipamentoEdit.length = 0;

    try {
      const respEq = await fetch("/prodesp/equipamentos-update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_atendimento: id,
          id_unidade_equipamentos: originalData.id_unidades_atendimentos,
          new_equipamentos: equipmentsToSave,
          deleted_equipamentos: deletedEquipamentoIds,
        }),
      });
      const resultEq = await respEq.json();
      if (!resultEq.success) {
        fail("equipamentos", resultEq.message);
        newEquipamentoEdit.push(...equipmentsToSave);
        allSuccess = false;
      } else {
        savedSomething = true;
        deletedEquipamentoIds.length = 0;
      }
    } catch (err) {
      fail("equipamentos", prodespFriendlyFetchError(err));
      newEquipamentoEdit.push(...equipmentsToSave);
      allSuccess = false;
      prodespLogUnexpectedSaveFailure("Auto-save (Edit): Falha ao salvar equipamentos.", null, err);
    }
  }

  // 4. Salve novos links e deleta
  if (newLinksEdit.length > 0 || deletedLinkIds.length > 0) {
    const linksToSave = [...newLinksEdit];
    newLinksEdit.length = 0;

    try {
      const respLnk = await fetch("/prodesp/links-update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_atendimento: id,
          id_unidade_links: originalData.id_unidades_atendimentos,
          id_vgr: document.getElementById("editIdVgr").value.trim(),
          new_links: linksToSave,
          deleted_links: deletedLinkIds,
        }),
      });
      const resultLnk = await respLnk.json();
      if (!resultLnk.success) {
        fail("links", resultLnk.message);
        newLinksEdit.push(...linksToSave);
        allSuccess = false;
      } else {
        savedSomething = true;
        deletedLinkIds.length = 0;
      }
    } catch (err) {
      fail("links", prodespFriendlyFetchError(err));
      newLinksEdit.push(...linksToSave);
      allSuccess = false;
      prodespLogUnexpectedSaveFailure("Auto-save (Edit): Falha ao salvar links.", null, err);
    }
  }

  if (allSuccess) {
    if (showSuccessToast && savedSomething) {
      prodespNotifySaveSuccess("edit");
    }
  } else {
    if (!failureWasExpectedBusiness) {
      prodespLogUnexpectedSaveFailure("Auto-save (Edit) falhou para atendimento ID: " + id);
    }
    if (notifyFailure && !failureNotified) {
      prodespNotifySaveFailure(null, "Não foi possível salvar todas as alterações. Verifique as mensagens acima.");
    }
  }
  return allSuccess;
}

/**
 * Preenche os campos de um modal (Edição ou Visualização) com os dados do atendimento.
 * @param {Object} d - Objeto com os dados do atendimento.
 * @param {string} prefix - Prefixo dos IDs dos elementos ('edit' ou 'view').
 */
function prodespCoerceInputValue(val) {
  if (val == null || val === undefined) return "";
  const s = typeof val === "string" ? val.trim() : String(val).trim();
  if (s === "" || s === "None" || s === "null") return "";
  return s;
}

function fillModalFields(d, prefix) {
  const setVal = (id, val) => {
    const el = document.getElementById(prefix + id);
    if (el) el.value = prodespCoerceInputValue(val);
  };

  if (prefix === 'edit') {
    setVal("AtendimentoId", d.id_atendimentos);
  } else if (prefix === 'view') {
    setVal("AtendimentoId", d.id_atendimentos);
  }

  setVal("Status", d.status_atendimento);

  // Popula substatus apenas para edição, para visualização é apenas input text
  if (prefix === 'edit') {
    const substatusSelect = document.getElementById("editSubstatus"); // Passa o contexto 'edit'
    // Garante que os valores iniciais estão limpos de espaços para evitar falha no select
    const statusInit = d.status_atendimento ? d.status_atendimento.trim() : "";
    const substatusInit = d.substatus_atendimento ? d.substatus_atendimento.trim() : "";
    populateSubstatus(substatusSelect, statusInit, substatusInit, undefined, undefined, "edit", {
      emitChange: false,
    });
  } else {
    setVal("Substatus", d.substatus_atendimento);
  }

  setVal("AnalistaAtuante", d.analista_atuante);
  setVal("AnalistaConfiguracao", d.analista_configuracao);
  if (prefix === "edit" || prefix === "create") {
    prodespSetAnalistaMplsValor(prefix, d.analista_mpls_atendimentos || d.analista_mpls);
  } else {
    setVal("AnalistaMplsAtendimentos", d.analista_mpls_atendimentos);
  }
  setVal("AnalistaCadernoTeste", d.analista_caderno_teste);
  setVal("TicketNoc", d.ticket_noc);
  if (prefix === "edit") {
    prodespEnsureContratadaOption("editContratada", d.contratada);
  }
  setVal("Contratada", d.contratada);
  setVal("Field", d.field_responsavel);
  setVal("ContatoField", d.contato_field);

  if (prefix === 'view') {
    setVal("Logs", d.logs_atendimento);
    const motivosContainer = document.getElementById("viewMotivosForaPadrao");
    window.renderMotivosView(motivosContainer, d.motivos_fora_padrao || []);
  } else {
    reloadLogs(d.logs_atendimento, document.getElementById(`log-configuracao-remota-${prefix}`), prefix);
  }

  setVal("IdVgr", d.id_vgr);
  setVal("Nome", d.nome);
  setVal("Acronimo", d.acronimo);
  setVal("Hostname", d.hostname);
  setVal("TelefoneContato", d.telefone_contato);
  setVal("Endereco", d.endereco);
  setVal("Numero", d.numero);
  setVal("Complemento", d.complemento);
  setVal("Bairro", d.bairro);
  setVal("Municipio", d.municipio);
  setVal("Estado", d.estado);
  setVal("Cep", d.cep);
  setVal("DataAgendamento", d.data_agendamento);
  setVal("HoraAgendamento", formatHoraParaInputTime(d.hora_agendamento));

  if (prefix === "edit" || prefix === "create") {
    prodespSetMaskedFieldValue(prefix, "Latitude", d.latitude);
    prodespSetMaskedFieldValue(prefix, "Longitude", d.longitude);
    prodespSetMaskedFieldValue(prefix, "IpLan01", d.ip_lan_01);
    prodespSetMaskedFieldValue(prefix, "IpLanTransito", d.ip_lan_transito);
    prodespSetMaskedFieldValue(prefix, "LoopbackVivo", d.loopback_vivo);
    prodespSetMaskedFieldValue(prefix, "LoopbackCliente", d.loopback_cliente);
    prodespSetMaskedFieldValue(prefix, "LoopbackOnBgp", d.loopback_on_bgp);
  } else {
    setVal("Latitude", d.latitude);
    setVal("Longitude", d.longitude);
    setVal("IpLan01", d.ip_lan_01);
    setVal("IpLanTransito", d.ip_lan_transito);
    setVal("LoopbackVivo", d.loopback_vivo);
    setVal("LoopbackCliente", d.loopback_cliente);
    setVal("LoopbackOnBgp", d.loopback_on_bgp);
  }

  PRODESP_MV_OPCIONAIS_JS_KEYS.forEach((col) => {
    const suffix = pascalize(col);
    if (prefix === "edit" || prefix === "create") {
      prodespSetMaskedFieldValue(prefix, suffix, d[col]);
    } else {
      setVal(suffix, d[col]);
    }
  });
  PRODESP_LAN_EXTRA_JS_KEYS.forEach((col) => {
    const suffix = pascalize(col);
    if (prefix === "edit" || prefix === "create") {
      prodespSetMaskedFieldValue(prefix, suffix, d[col]);
    } else {
      setVal(suffix, d[col]);
    }
  });

  setVal("Idintragov", d.id_intragov);

  if (prefix === "edit" || prefix === "create") {
    prodespRefreshLiveFieldValidation(prefix);
  }
}

async function prodespFetchAtendimentoDetalhes(id, includeQuery = "") {
  const numId = parseInt(id, 10);
  if (!Number.isFinite(numId)) {
    throw new Error("ID de atendimento inválido.");
  }
  const qs = includeQuery ? (includeQuery.startsWith("?") ? includeQuery : `?${includeQuery}`) : "";
  const res = await fetch(`/prodesp/atendimentos/${numId}${qs}`);
  let body = null;
  try {
    body = await res.json();
  } catch (_e) {
    body = null;
  }
  if (!res.ok) {
    const msg =
      (body && (body.message || body.error || body.erro)) ||
      res.statusText ||
      "Não foi possível carregar o atendimento.";
    throw new Error(msg);
  }
  return body;
}

function viewDetails(id) {
  const bootKinds = ["historico", "caderno", "certificado"];
  const boot =
    typeof window.prodespEnsureModalScripts === "function"
      ? window.prodespEnsureModalScripts(bootKinds)
      : Promise.resolve();
  boot
    .then(() => prodespFetchAtendimentoDetalhes(id, "include=historico,marcos"))
    .then((d) => {
      const marcos = d.marcos_atividade || [];
      const historicoRes = d.historico_auditoria || { dados: d.historico_atendimento };
      // Preenche os campos do modal de visualização
      fillModalFields(d, 'view');

      // Renderiza Observações (somente leitura)
      const obsContainer = document.getElementById("log-observacao-view");
      obsContainer.innerHTML = '<div class="titles-incident"><span>DATA</span><span>OBSERVAÇÕES</span></div>';
      const obsOrdenadas = prodespSortObservacoesDesc(d.observacoes || []);
      if (obsOrdenadas.length > 0) {
        obsOrdenadas.forEach((obs) => {
          const card = document.createElement("div");
          card.classList.add("card-incident");
          const fields = document.createElement("div");
          fields.classList.add("fields");
          const dataDiv = document.createElement("div");
          dataDiv.classList.add("incident-data");
          dataDiv.textContent = obs.timestamp || obs.data_observacao || "-";
          const textoDiv = document.createElement("div");
          textoDiv.classList.add("incident-chamado");
          textoDiv.style.whiteSpace = "pre-wrap";
          textoDiv.textContent = obs.texto || obs.observacao_prodesp || "-";
          fields.appendChild(dataDiv);
          fields.appendChild(textoDiv);
          card.appendChild(fields);
          obsContainer.appendChild(card);
        });
      } else {
        obsContainer.innerHTML += '<div class="text-muted p-2">Nenhuma observação.</div>';
      }

      // Renderiza Equipamentos (somente leitura — accordion)
      prodespPopulateEquipamentosViewList(
        document.getElementById("log-equipamento-view"),
        d.equipamentos,
        "Nenhum equipamento."
      );

      // Renderiza Links (somente leitura — accordion)
      prodespPopulateLinksViewList(
        document.getElementById("log-link-view"),
        d.links,
        "Nenhum link."
      );

      // Renderiza Marcos
      document.getElementById("log-marcos-view").innerHTML = renderMarcos(marcos);

      // Renderiza Histórico
      const historicoContainer = document.getElementById("log-historico-view");
      if (historicoContainer) {
        historicoContainer.innerHTML = window.renderHistoricoCompleto(
          historicoRes,
          historicoRes.admin_user === 1
        );
        if (typeof window.prodespBindHistoricoCollapseControls === "function") {
          window.prodespBindHistoricoCollapseControls(historicoContainer);
        }
      }

      // Força abertura da primeira aba
      const firstTabEl = document.getElementById("view-dados-unidade-tab");
      if (firstTabEl) bootstrap.Tab.getOrCreateInstance(firstTabEl).show();

      prodespOpenModal(document.getElementById("viewModal"));
      void prodespSyncCadernoToolbarAll();
    })
    .catch((err) => {
      console.error("Erro em viewDetails:", err);
      const msg = (err && err.message) || String(err) || "Não foi possível abrir a visualização.";
      showToast(msg, "danger", undefined, "Erro ao visualizar");
    });
}

async function editDetails(id) {
  try {
    if (typeof window.prodespEnsureModalScripts === "function") {
      await window.prodespEnsureModalScripts(["historico", "enriquecer", "caderno", "certificado"]);
    }
    const response = await fetch(`/prodesp/atendimentos/${id}`);
    if (!response.ok) {
      const errorData = await response.json();
      showToast(errorData.message || "Erro ao carregar atendimento.", "danger");
      return;
    }
    const d = await response.json();

    const permEdicao = prodespPermissaoEdicao(d);
    if (!permEdicao.ok) {
      showToast(permEdicao.msg, "warning");
      return;
    }

    originalData = d; //Salva os dados originais para comparação
    editPersistedSubstatus = (d.substatus_atendimento || "").trim();
    editPersistedStatus = (d.status_atendimento || "").trim();
    editFlowBaselineSubstatus = editPersistedSubstatus;
    if (PRODESP_SUBSTATUS_AGUARDA_EXTERNO.has(editPersistedSubstatus)) {
      try {
        const r = await (await fetch(`/prodesp/atendimentos/${id}/substatus_baseline`)).json();
        if (r && r.success && r.baseline) editFlowBaselineSubstatus = r.baseline.trim();
        if (!editFlowBaselineSubstatus) editFlowBaselineSubstatus = "Triagem";
      } catch (e) {
        editFlowBaselineSubstatus = "Triagem";
      }
    }

    prodespSuppressAutosave = true;
    if (autoSaveEditTimeout) clearTimeout(autoSaveEditTimeout);

    // --- 1. Preenche todos os campos do formulário usando a função auxiliar ---
    fillModalFields(d, "edit");
    window.limparMotivosSelecionados("edit");
    try {
      await window.carregarMotivosForaPadrao("edit");
      motivosForaPadraoOriginalEdit = await window.marcarMotivosAtendimento("edit", id);
    } catch (motivosErr) {
      console.error("Erro ao carregar motivos fora do padrão:", motivosErr);
      motivosForaPadraoOriginalEdit = [];
    }

    // --- 2. Determina a editabilidade do formulário com base no status e na data ---
    const SUBSTATUS_ESPECIAIS = [];
    const isEditable = true; // Já validamos acima

    setAllEditFieldsDisabled(false);

    // --- 3. Aplica a lógica de UI (listeners) ---
    const statusSelect = document.getElementById("editStatus");
    const substatusSelect = document.getElementById("editSubstatus");
    const analistaInput = document.getElementById("editAnalistaAtuante");
    const btnSave = document.getElementById("btnSalvar");
    const editFormEl = document.getElementById("editForm");

    // Limpa listeners antigos para evitar duplicação
    if (statusSelect._editChangeListener)
      statusSelect.removeEventListener("change", statusSelect._editChangeListener);
    if (editFormEl._inputListener)
      editFormEl.removeEventListener("input", editFormEl._inputListener);
    if (editFormEl._changeListener)
      editFormEl.removeEventListener("change", editFormEl._changeListener);

    // Define o estado GERAL do formulário
    btnSave.disabled = false;

    // Habilita Salvar ao editar; auto-save só na mudança de substatus (não em input/status).
    editFormEl._inputListener = function () {
      btnSave.disabled = false;
    };
    editFormEl.addEventListener("input", editFormEl._inputListener);

    editFormEl._changeListener = function () {
      btnSave.disabled = false;
    };
    editFormEl.addEventListener("change", editFormEl._changeListener);

    // Lógica de "Assumir" o atendimento ao abrir o modal.
    const takeoverStatuses = [
      "Em Atendimento",
      "Quebra",
      "Concluído Parcial",
      "Concluído",
    ];
    // APENAS assume se o campo estiver vazio.
    if (
      takeoverStatuses.includes(d.status_atendimento) &&
      (!d.analista_atuante || d.analista_atuante.trim() === "")
    ) {
      analistaInput.value = USUARIO_LOGADO;
    }

    // Listener de MUDANÇA DE STATUS para controlar a UI de campos específicos (substatus, analista).
    statusSelect._editChangeListener = function () {
      const novoStatus = this.value;
      const oldStatus = originalData.status_atendimento;
      const finalStatuses = ["Concluído", "Quebra", "Concluído Parcial"];
      const id = +document.getElementById("editAtendimentoId").value;
      const analistaInput = document.getElementById("editAnalistaAtuante");
      const substatusSelect = document.getElementById("editSubstatus");

      // Popula substatus; se o valor mudar (ex. Concluído→Concluído, Em Atendimento→Triagem), dispara evento change
      populateSubstatus(substatusSelect, novoStatus, substatusSelect.value, undefined, undefined, "edit");

      // Lógica para preencher analista de triagem se estiver vazio e status for de atuação
      const takeoverStatuses = ["Em Atendimento", "Quebra", STATUS_QUEBRA_TBRA, "Concluído Parcial", "Concluído"];
      if (takeoverStatuses.includes(novoStatus) && (!analistaInput.value || analistaInput.value.trim() === "")) {
        analistaInput.value = USUARIO_LOGADO;
      }

      prodespApplyAnalistaImplantacaoAdminUi("edit", false);
      prodespUpdateAnalistaMplsUi("edit", substatusSelect.value, { formDisabled: false });
      prodespSyncCadernoToolbarEdit();
    };
    statusSelect.addEventListener("change", statusSelect._editChangeListener);

    // Listener único de substatus (ordem: Quebra → Aguarda externo → observações → validações → auto-save)
    if (substatusSelect._editSubstatusChangeListener)
      substatusSelect.removeEventListener("change", substatusSelect._editSubstatusChangeListener);
    if (substatusSelect._quebraChangeListener)
      substatusSelect.removeEventListener("change", substatusSelect._quebraChangeListener);
    if (substatusSelect._acChangeListener)
      substatusSelect.removeEventListener("change", substatusSelect._acChangeListener);
    substatusSelect._quebraChangeListener = null;
    substatusSelect._acChangeListener = null;

    editLastModalSubstatus = (d.substatus_atendimento || "").trim();

    substatusSelect._editSubstatusChangeListener = async function () {
      if (
        prodespSubstatusChangeInFlight ||
        prodespQuebraEncerramentoInProgress ||
        suppressQuebraEncerramentoChange
      ) {
        return;
      }
      prodespSubstatusChangeInFlight = true;
      try {
        const novoSub = (this.value || "").trim();
        const oldSub = (
          editLastModalSubstatus || getPersistedSubstatus("edit") || SUBSTATUS_INICIAL_FILA
        ).trim();
        const agGpBlock = prodespValidarTransicaoSubstatusAgGp(
          oldSub,
          novoSub,
          (statusSelect.value || "").trim()
        );
        if (agGpBlock) {
          prodespRevertSubstatusParaValor("edit", oldSub || SUBSTATUS_AGUARDA_GESTAO);
          showToast(agGpBlock, "warning");
          prodespSyncCadernoToolbarEdit();
          return;
        }

        if (!suppressQuebraEncerramentoChange) {
          const handledQuebra = await prodespRunQuebraEncerramentoFlow(
            "edit",
            substatusSelect,
            statusSelect
          );
          if (handledQuebra) {
            editLastModalSubstatus = (substatusSelect.value || "").trim();
            prodespSyncCadernoToolbarEdit();
            return;
          }
        }

        const handledAguarda = await prodespRunAguardaExternoSubstatusFlow(
          "edit",
          substatusSelect,
          statusSelect
        );
        if (handledAguarda) {
          prodespSyncCadernoToolbarEdit();
          return;
        }

        const handledObs = await prodespRunObservacaoSubstatusFlows(
          "edit",
          substatusSelect,
          statusSelect
        );
        if (handledObs) {
          editLastModalSubstatus = (this.value || "").trim();
          prodespSyncCadernoToolbarEdit();
          return;
        }

        const statusAtual = (statusSelect.value || "").trim();
        if (
          suppressQuebraEncerramentoChange ||
          ((statusAtual === "Quebra" || statusAtual === STATUS_QUEBRA_TBRA) &&
            (prodespIsSubstatusQuebra(novoSub) || prodespIsSubstatusQuebraTbra(novoSub)) &&
            isEnteringQuebraEncerramento("edit"))
        ) {
          return;
        }
        if (prodespIsTriagemParaFilaAguardando(oldSub, novoSub)) {
          const dadosFieldMissing = prodespValidateDadosFieldTriagemParaAguardando(
            "edit",
            oldSub,
            novoSub
          );
          if (dadosFieldMissing.length > 0) {
            prodespRevertSubstatusParaValor("edit", oldSub);
            prodespNotifyValidationBlocked(
              dadosFieldMissing,
              `Para enviar de «${SUBSTATUS_AGUARDA_GESTAO}» para a fila Aguardando, preencha os Dados Field`
            );
            prodespSyncCadernoToolbarEdit();
            return;
          }
        }

        const mplsMissing = prodespValidateAnalistaMplsTerceiro("edit", oldSub, novoSub);
        if (mplsMissing.length > 0) {
          prodespRevertSubstatusParaValor("edit", oldSub);
          prodespNotifyValidationBlocked(
            mplsMissing,
            prodespMensagemAnalistaMplsObrigatorio(oldSub, novoSub)
          );
          prodespUpdateAnalistaMplsUi("edit", novoSub, { formDisabled: false });
          prodespSyncCadernoToolbarEdit();
          return;
        }

        const hostnameMissing = prodespValidateHostnameObrigatorio(
          "edit",
          oldSub,
          novoSub,
          statusAtual
        );
        if (hostnameMissing.length > 0) {
          prodespRevertSubstatusParaValor("edit", oldSub);
          prodespNotifyValidationBlocked(
            hostnameMissing,
            "Para sair de «Em Configuração Remota» ou concluir, preencha o Hostname",
            "edit"
          );
          prodespSyncCadernoToolbarEdit();
          return;
        }

        prodespProcessarLiberacaoAnalistas("edit", oldSub, novoSub);

        editLastModalSubstatus = novoSub;
        populateSubstatus(this, statusSelect.value, novoSub, undefined, undefined, "edit");
        prodespUpdateAnalistaMplsUi("edit", novoSub, { formDisabled: false });

        void prodespSyncCadernoToolbarEdit(novoSub);
        if (!suppressAguardandoClienteChange && !isEnteringAguardaExterno("edit")) {
          prodespTriggerAutoSaveFromSubstatusChange("edit");
        }
        void prodespSyncCadernoToolbarEdit();
      } finally {
        prodespSubstatusChangeInFlight = false;
      }
    };
    substatusSelect.addEventListener("change", substatusSelect._editSubstatusChangeListener);


    // Sincroniza UI de status/substatus sem disparar auto-save (não usar dispatchEvent aqui)
    populateSubstatus(
      substatusSelect,
      (d.status_atendimento || "").trim(),
      (d.substatus_atendimento || "").trim(),
      undefined,
      undefined,
      "edit",
      { emitChange: false }
    );
    prodespApplyAnalistaImplantacaoAdminUi("edit", !permEdicao.ok);
    prodespUpdateAnalistaMplsUi("edit", (d.substatus_atendimento || "").trim(), {
      formDisabled: !permEdicao.ok,
    });
    await prodespSyncCadernoToolbarEdit();

    // --- 4. Recarrega listas de observações e equipamentos ---
    reloadObservacoes(d.observacoes, "edit");
    reloadEquipamentos(d.equipamentos);
    reloadLinks(d.links);

    prodespSuppressAutosave = false;

    // Força abertura da primeira aba
    const firstTabEl = document.getElementById("edit-dados-unidade-conectividade-tab");
    if (firstTabEl) bootstrap.Tab.getOrCreateInstance(firstTabEl).show();

    // --- 5. Exibe o modal ---
    prodespOpenModal(document.getElementById("editModal"));

    if (
      parseInt(String(typeof LOGGED_IN_USER_ADMIN !== "undefined" ? LOGGED_IN_USER_ADMIN : 0), 10) === 1
    ) {
      prodespLoadAdminAuditTab(id);
    }
  } catch (err) {
    prodespSuppressAutosave = false;
    console.error("Erro em editDetails:", err);
    showToast(err.message, "danger");
  }
}


function pascalize(s) {
  return s
    .split(/[_\-]/)
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join("");
}

function idFor(prefix, col) {
  const customMap = { 'id_intragov': 'Idintragov' };
  const suffix = customMap[col] || pascalize(col);
  return prefix + suffix;
}

/** Status que exigem validação completa antes de salvar/finalizar. */
const PRODESP_FINAL_STATUSES = ["Concluído", "Quebra", STATUS_QUEBRA_TBRA, "Concluído Parcial"];

const PRODESP_EDIT_FINAL_VALIDATION_RULES = [
  { id: "editStatus", name: "Status" },
  { id: "editSubstatus", name: "Substatus" },
  { id: "editAnalistaAtuante", name: "Analista Atuante" },
  { id: "editContratada", name: "Contratada" },
  { id: "editField", name: "Field" },
  { id: "editContatoField", name: "Contato Field" },
  { id: "editIdVgr", name: "ID VGR" },
  { id: "editAcronimo", name: "Acrônimo" },
  { id: "editEndereco", name: "Endereço" },
  { id: "editNumero", name: "N°" },
  { id: "editBairro", name: "Bairro" },
  { id: "editMunicipio", name: "Município" },
  { id: "editEstado", name: "Estado" },
  { id: "editCep", name: "CEP" },
  { id: "editLatitude", name: "Latitude" },
  { id: "editLongitude", name: "Longitude" },
];

const PRODESP_CREATE_FINAL_VALIDATION_RULES = [
  { id: "createStatus", name: "Status" },
  { id: "createSubstatus", name: "Substatus" },
  { id: "createAnalistaAtuante", name: "Analista Atuante" },
  { id: "createContratada", name: "Contratada" },
  { id: "createField", name: "Field" },
  { id: "createContatoField", name: "Contato Field" },
  { id: "createIdVgr", name: "ID VGR" },
  { id: "createAcronimo", name: "Acrônimo" },
  { id: "createEndereco", name: "Endereço" },
  { id: "createNumero", name: "N°" },
  { id: "createBairro", name: "Bairro" },
  { id: "createMunicipio", name: "Município" },
  { id: "createEstado", name: "Estado" },
  { id: "createCep", name: "CEP" },
  { id: "createLatitude", name: "Latitude" },
  { id: "createLongitude", name: "Longitude" },
];

function prodespIsFinalStatus(statusValue) {
  return PRODESP_FINAL_STATUSES.includes(statusValue);
}

function prodespRequiresTicketNoc(statusValue, substatusValue) {
  return (
    (statusValue || "").trim() === "Concluído" &&
    (substatusValue || "").trim() === "Concluído"
  );
}

function prodespPrecisaHostnameSaidaConfigRemota(oldSubstatus, newSubstatus) {
  const oldSub = (oldSubstatus || "").trim();
  const newSub = (newSubstatus || "").trim();
  return oldSub === PRODESP_SUBSTATUS_EM_CONFIG_REMOTA && newSub !== oldSub;
}

function prodespValidateHostnameObrigatorio(context, oldSubstatus, newSubstatus, statusValue) {
  const precisaSaida =
    oldSubstatus != null &&
    newSubstatus != null &&
    prodespPrecisaHostnameSaidaConfigRemota(oldSubstatus, newSubstatus);
  const precisaConcluido = (statusValue || "").trim() === "Concluído";
  if (!precisaSaida && !precisaConcluido) return [];

  const hostEl = document.getElementById(context === "edit" ? "editHostname" : "createHostname");
  if (!hostEl || !(hostEl.value || "").trim()) {
    if (hostEl) hostEl.classList.add("is-invalid");
    return ["Hostname"];
  }
  if (hostEl) hostEl.classList.remove("is-invalid");
  return [];
}

/** Filas operacionais após Triagem (alinhado a atendimento_business_rules.FILAS_AGUARDANDO_APOS_TRIAGEM). */
const PRODESP_FILAS_AGUARDANDO_POS_TRIAGEM = [
  "Aguardando Config. Remota",
  "Aguardando Config. MPLS",
  "Aguardando Caderno de Teste",
];

function prodespIsTriagemParaFilaAguardando(oldSubstatus, newSubstatus) {
  return prodespIsGestaoParaFilaAguardando(oldSubstatus, newSubstatus);
}

/** Garante option no select de edição para valor legado (ex.: «Vivo Redes» antigo). */
function prodespEnsureContratadaOption(selectId, valor) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  const v = (valor || "").trim();
  if (!v) return;
  if ([...sel.options].some((o) => o.value === v)) return;
  sel.add(new Option(`${v} (legado)`, v));
}

function prodespDadosFieldValidationRules(context) {
  const p = context === "edit" ? "edit" : "create";
  return [
    { id: `${p}Contratada`, name: "Contratada" },
    { id: `${p}Field`, name: "Field" },
    { id: `${p}ContatoField`, name: "Contato Field" },
  ];
}

/** Valida Contratada, Field e Contato Field antes de Triagem → fila Aguardando. */
function prodespValidateDadosFieldTriagemParaAguardando(context, oldSubstatus, newSubstatus) {
  if (!prodespIsTriagemParaFilaAguardando(oldSubstatus, newSubstatus)) {
    return [];
  }
  const emptyFields = validateFields(prodespDadosFieldValidationRules(context));
  const contatoEl = document.getElementById(
    context === "edit" ? "editContatoField" : "createContatoField"
  );
  if (contatoEl) {
    const digits = (contatoEl.value || "").replace(/\D/g, "");
    if (!digits) {
      if (!emptyFields.includes("Contato Field")) {
        emptyFields.push("Contato Field");
      }
      contatoEl.classList.add("is-invalid");
    }
  }
  return emptyFields;
}

function prodespRevertSubstatusParaValor(context, substatusValor) {
  const mode = context === "edit" ? "edit" : "create";
  const subEl = document.getElementById(mode === "edit" ? "editSubstatus" : "createSubstatus");
  const statusEl = document.getElementById(mode === "edit" ? "editStatus" : "createStatus");
  if (!subEl || !statusEl || !substatusValor) return;
  const { status } = prodespGetPersistedStatusSubstatus(mode);
  const statusValor = status || (mode === "create" ? "Em Atendimento" : statusEl.value || "Em Atendimento");
  suppressAguardandoClienteChange = true;
  prodespSuppressAutosave = true;
  prodespRevertStatusSubstatusParaValor(mode, statusValor, substatusValor);
  prodespSuppressAutosave = false;
  suppressAguardandoClienteChange = false;
}

/** Valida Ticket NOC quando Status e Substatus são Concluído. */
function prodespValidateTicketNoc(context) {
  const prefix = context === "edit" ? "edit" : "create";
  const status = (
    document.getElementById(`${prefix}Status`)?.value || ""
  ).trim();
  const substatus = (
    document.getElementById(`${prefix}Substatus`)?.value || ""
  ).trim();
  const ticketEl = document.getElementById(`${prefix}TicketNoc`);
  if (!prodespRequiresTicketNoc(status, substatus)) {
    if (ticketEl) ticketEl.classList.remove("is-invalid");
    return [];
  }
  const validateFn =
    window.ProdespLiveValidation && ProdespLiveValidation.validateTicketNocFormat;
  if (validateFn) {
    const result = validateFn(ticketEl ? ticketEl.value : "", { required: true });
    if (!result.valid) {
      if (ticketEl) ticketEl.classList.add("is-invalid");
      return ["Ticket NOC"];
    }
    if (ticketEl) {
      ticketEl.classList.remove("is-invalid");
      if (result.value) ticketEl.value = result.value;
    }
    return [];
  }
  if (!ticketEl || !(ticketEl.value || "").trim()) {
    if (ticketEl) ticketEl.classList.add("is-invalid");
    return ["Ticket NOC"];
  }
  ticketEl.classList.remove("is-invalid");
  return [];
}

function prodespScheduleEditAutoSave(showSuccessToast) {
  clearTimeout(autoSaveEditTimeout);
  autoSaveEditTimeout = setTimeout(
    () =>
      autoSaveEditModalData({
        showSuccessToast: !!showSuccessToast,
        notifyFailure: true,
      }),
    500
  );
}

function prodespScheduleCreateAutoSave(showSuccessToast) {
  if (!currentCreateModalAtendimentoId) return;
  clearTimeout(autoSaveTimeout);
  autoSaveTimeout = setTimeout(
    () =>
      autoSaveCreateModalData({
        showSuccessToast: !!showSuccessToast,
        notifyFailure: true,
      }),
    500
  );
}

/** Auto-save após adicionar ou remover observação manual (não persiste staging de transição). */
function prodespTriggerAutoSaveFromObservacaoChange(context) {
  if (prodespSuppressAutosave) return;
  const isEdit = context === "edit";
  if (isEdit && !+document.getElementById("editAtendimentoId")?.value) return;
  if (!isEdit && !currentCreateModalAtendimentoId) return;
  prodespSaveAtendimentoObservacoes(context, { toast: false, includeTransicaoStaging: false });
}

/**
 * Auto-save disparado apenas pelo evento change do substatus (usuário ou populate com valor novo).
 */
function prodespTriggerAutoSaveFromSubstatusChange(context) {
  if (prodespSuppressAutosave || prodespQuebraEncerramentoInProgress) return;
  const isEdit = context === "edit";
  const status = (document.getElementById(isEdit ? "editStatus" : "createStatus")?.value || "").trim();
  const substatus = (document.getElementById(isEdit ? "editSubstatus" : "createSubstatus")?.value || "").trim();

  if (!status || !substatus) return;
  if (isEdit && !+document.getElementById("editAtendimentoId")?.value) return;
  if (!isEdit && !currentCreateModalAtendimentoId) return;

  const oldSub = (
    isEdit
      ? editPersistedSubstatus || editFlowBaselineSubstatus
      : createPersistedSubstatus || createFlowBaselineSubstatus || "Triagem"
  ).trim();
  const dadosFieldMissing = prodespValidateDadosFieldTriagemParaAguardando(
    context,
    oldSub,
    substatus
  );
  if (dadosFieldMissing.length > 0) {
    prodespRevertSubstatusParaValor(context, oldSub || "Triagem");
    prodespNotifyValidationBlocked(
      dadosFieldMissing,
      "Para enviar da Gestão para a fila Aguardando, preencha os Dados Field"
    );
    return;
  }

  const hostnameMissingSub = prodespValidateHostnameObrigatorio(
    context,
    oldSub,
    substatus,
    status
  );
  if (hostnameMissingSub.length > 0) {
    prodespRevertSubstatusParaValor(context, oldSub || "Triagem");
    prodespNotifyValidationBlocked(
      hostnameMissingSub,
      "Para sair de «Em Configuração Remota», preencha o Hostname",
      context
    );
    return;
  }

  if (prodespIsFinalStatus(status)) {
    const rules = isEdit ? PRODESP_EDIT_FINAL_VALIDATION_RULES : PRODESP_CREATE_FINAL_VALIDATION_RULES;
    const emptyFields = validateFields(rules);
    const ticketMissing = prodespValidateTicketNoc(isEdit ? "edit" : "create");
    const hostnameMissing = prodespValidateHostnameObrigatorio(
      isEdit ? "edit" : "create",
      oldSub,
      substatus,
      status
    );
    const allMissing = [...emptyFields, ...ticketMissing, ...hostnameMissing];
    if (allMissing.length > 0) {
      prodespNotifyValidationBlocked(
        allMissing,
        "Para salvar com este status, preencha os campos",
        isEdit ? "edit" : "create"
      );
      return;
    }
  }

  if (isEdit) {
    prodespScheduleEditAutoSave(true);
  } else {
    prodespScheduleCreateAutoSave(true);
  }
}

/**
 * Valida um conjunto de campos de formulário e gerencia a UI do Accordion.
 * @param {Array<Object>} rules - Um array de objetos, onde cada objeto define uma regra de validação. Ex: {id: 'createNome', name: 'Nome da Unidade'}
 * @returns {Array<string>} - Um array com os nomes dos campos inválidos.
 */
function validateFields(rules) {
  const emptyFields = [];
  let firstInvalidTab = null;
  let firstInvalidAccordionPanel = null;

  // 1. Limpa a validação anterior de todos os campos e headers do accordion
  rules.forEach(rule => {
    const el = document.getElementById(rule.id);
    if (el) {
      el.classList.remove('is-invalid');
      // Clean up tab buttons if we add invalid class to them
      const tabPane = el.closest('.tab-pane');
      if (tabPane) {
        const tabId = tabPane.id;
        const tabButton = document.querySelector(`button[data-bs-target="#${tabId}"]`);
        if (tabButton) tabButton.classList.remove('is-invalid', 'text-danger');
      }
      const accordionItem = el.closest('.accordion-item');
      if (accordionItem) {
        const accordionButton = accordionItem.querySelector('.accordion-button');
        if (accordionButton) {
          accordionButton.classList.remove('is-invalid');
        }
      }
    }
  });

  // 2. Itera sobre as regras para encontrar campos inválidos
  for (const rule of rules) {
    const el = document.getElementById(rule.id);

    // A validação checa se o elemento existe e se seu valor está vazio ou se é um select com a opção 'disabled' selecionada.
    if (el && (!el.value || el.value.trim() === '' || (el.tagName === 'SELECT' && el.options[el.selectedIndex].disabled))) {
      emptyFields.push(rule.name);
      el.classList.add('is-invalid'); // Destaca o campo

      // Handle Tabs
      const tabPane = el.closest('.tab-pane');
      if (tabPane && !firstInvalidTab) {
        firstInvalidTab = tabPane;
      }
      if (tabPane) {
        const tabId = tabPane.id;
        const tabButton = document.querySelector(`button[data-bs-target="#${tabId}"]`);
        if (tabButton) tabButton.classList.add('text-danger'); // Visual cue
      }

      // Encontra o accordion pai e o destaca também
      const accordionItem = el.closest('.accordion-item');
      if (accordionItem) {
        const accordionButton = accordionItem.querySelector('.accordion-button');
        const accordionPanel = accordionItem.querySelector('.accordion-collapse');

        if (accordionButton) {
          accordionButton.classList.add('is-invalid');
        }

        // Armazena o primeiro painel inválido para abri-lo depois
        if (accordionPanel && !firstInvalidAccordionPanel) {
          firstInvalidAccordionPanel = accordionPanel;
        }
      }
    }
  }

  // 3. Switch to invalid tab/accordion
  if (firstInvalidTab) {
    const tabId = firstInvalidTab.id;
    const tabButton = document.querySelector(`button[data-bs-target="#${tabId}"]`);
    if (tabButton) {
      const tab = new bootstrap.Tab(tabButton);
      tab.show();
    }
  } else if (firstInvalidAccordionPanel) {
    const bsCollapse = new bootstrap.Collapse(firstInvalidAccordionPanel, {
      toggle: false // Garante que apenas vamos mostrar, não alternar
    });
    bsCollapse.show();
  }

  return emptyFields; // Retorna a lista de nomes de campos para a mensagem de toast
}

async function saveEdit() {
  const saveButton = document.getElementById('btnSalvar');
  setButtonLoading(saveButton, true, 'Salvando...');

  try {
    const id = +document.getElementById("editAtendimentoId").value;
    if (!id) {
      showToast("ID do atendimento não encontrado.", "danger");
      return;
    }

    const permEdicao = prodespResolvePermEdicaoModalSalvar(originalData, "edit");
    if (!permEdicao.ok) {
      showToast(permEdicao.msg, "warning");
      return;
    }
    if (permEdicao.noop) {
      return;
    }

    const statusValue = document.getElementById("editStatus").value;
    const substatusValue = document.getElementById("editSubstatus").value;
    const substatusValueTrim = (substatusValue || "").trim();
    const isFinalizing = prodespIsFinalStatus(statusValue);
    const motivosForaPadrao = window.coletarMotivosSelecionados("edit");
    const oldSubSave = (originalData.substatus_atendimento || editPersistedSubstatus || "").trim();
    const dadosFieldMissingSave = prodespValidateDadosFieldTriagemParaAguardando(
      "edit",
      oldSubSave,
      (substatusValue || "").trim()
    );
    if (dadosFieldMissingSave.length > 0) {
      prodespNotifyValidationBlocked(
        dadosFieldMissingSave,
        "Para enviar da Gestão para a fila Aguardando, preencha os Dados Field",
        "edit"
      );
      return;
    }
    const mplsMissingSave = prodespValidateAnalistaMplsTerceiro(
      "edit",
      oldSubSave,
      (substatusValue || "").trim()
    );
    if (mplsMissingSave.length > 0) {
      prodespNotifyValidationBlocked(
        mplsMissingSave,
        prodespMensagemAnalistaMplsObrigatorio(oldSubSave, (substatusValue || "").trim()),
        "edit"
      );
      prodespUpdateAnalistaMplsUi("edit", substatusValue, { formDisabled: false });
      return;
    }
    const hostnameMissingSave = prodespValidateHostnameObrigatorio(
      "edit",
      oldSubSave,
      substatusValueTrim,
      statusValue
    );
    if (hostnameMissingSave.length > 0) {
      prodespNotifyValidationBlocked(
        hostnameMissingSave,
        "Para sair de «Em Configuração Remota» ou concluir, preencha o Hostname",
        "edit"
      );
      return;
    }
    const quebraMotivosSave = prodespValidateMotivosQuebraObrigatorios("edit");
    if (quebraMotivosSave.length > 0) {
      prodespNotifyValidationBlocked(
        quebraMotivosSave,
        "Para encerrar com Quebra, selecione ao menos um motivo em Fora do padrão",
        "edit"
      );
      return;
    }
    if (statusValue === "Quebra" && isEnteringQuebraEncerramento("edit")) {
      prodespNotifyValidationBlocked(
        ["Motivo da quebra (observação)"],
        "Selecione o substatus de Quebra novamente para registrar o motivo da quebra",
        "edit"
      );
      return;
    }

    if (substatusValueTrim && substatusValueTrim !== oldSubSave) {
      prodespAplicarLiberacaoAnalistasCampos("edit", oldSubSave, substatusValueTrim, {
        comObservacao: true,
      });
    }
    // --- Validações antes de salvar ---
    if (isFinalizing) {
      const emptyFields = validateFields(PRODESP_EDIT_FINAL_VALIDATION_RULES);
      const ticketMissing = prodespValidateTicketNoc("edit");
      const hostnameMissing = prodespValidateHostnameObrigatorio(
        "edit",
        oldSubSave,
        substatusValueTrim,
        statusValue
      );
      const allMissing = [...emptyFields, ...ticketMissing, ...hostnameMissing];
      if (allMissing.length > 0) {
        prodespNotifyValidationBlocked(
          allMissing,
          "Para finalizar, preencha os campos obrigatórios",
          "edit"
        );
        return;
      }
    }

    // --- Coleta de atualizações --- 
    const updates = [];
    const jsFields = [
      "status",
      "substatus",
      "analista_atuante",
      "analista_configuracao",
      "analista_mpls_atendimentos",
      "analista_caderno_teste",
      "contratada",
      "field",
      "contato_field",
      "logs",
      "nome",
      "acronimo",
      "hostname",
      "endereco",
      "numero",
      "bairro",
      "municipio",
      "estado",
      "complemento",
      "data_agendamento",
      "hora_agendamento",
      "cep",
      "latitude",
      "longitude",
      "telefone_contato",
      "ip_lan_01",
      "ip_lan_transito",
      "id_intragov",
      "loopback_vivo",
      "loopback_cliente",
      "loopback_on_bgp",
      "ticket_noc",
      ...PRODESP_MV_OPCIONAIS_JS_KEYS,
    ...PRODESP_LAN_EXTRA_JS_KEYS,
    ];
    const keyMap = {
      status: "status_atendimento",
      substatus: "substatus_atendimento",
      analista_atuante: "analista_atuante",
      analista_configuracao: "analista_configuracao",
      analista_mpls_atendimentos: "analista_mpls_atendimentos",
      analista_caderno_teste: "analista_caderno_teste_atendimentos",
      contratada: "contratada",
      field: "field_responsavel",
      contato_field: "contato_field",
      logs: "logs_atendimento",
      nome: "nome",
      acronimo: "acronimo_unidades",
      hostname: "hostname_unidades",
      endereco: "endereco_unidades",
      numero: "numero_unidades",
      bairro: "bairro_unidades",
      municipio: "municipio_unidades",
      estado: "estado_unidades",
      complemento: "complemento_unidades",
      data_agendamento: "data_agendamento_unidades",
      hora_agendamento: "hora_agendamento_unidades",
      cep: "cep_unidades",
      latitude: "latitude_unidades",
      longitude: "longitude_unidades",
      telefone_contato: "telefone_contato_unidades",
      ip_lan_01: "ip_lan_01_unidades",
        ip_lan_transito: "ip_lan_transito_unidades",
      id_intragov: "id_intragov_unidades",
      loopback_vivo: "loopback_vivo_unidades",
      loopback_cliente: "loopback_cliente_unidades",
      loopback_on_bgp: "loopback_on_bgp_unidades",
      ticket_noc: "ticket_noc_unidades",
      ...prodespMvOpcionaisKeyMapEntries(),
      ...prodespLanExtraKeyMapEntries(),
    };

    jsFields.forEach((col) => {
      let novo;
      if (col === "logs") {
        novo = serializeLogEntries(logsEdit);
      } else {
        const el = document.getElementById(idFor("edit", col));
        if (!el) return;
        novo = prodespReadEditableFieldValue(el, col);
      }

      if (PRODESP_MASKED_IP_COLS.has(col) && typeof novo === "string") {
        novo = prodespStripIpSpaces(novo);
      }

      // Previne envio de string vazia para campos de data, hora ou coordenadas
      if (novo === "" && ["data_agendamento", "hora_agendamento", "latitude", "longitude"].includes(col)) {
        novo = null;
      }

      const originalKey = keyMap[col];
      if (
        originalKey &&
        valuesDiffer(col, novo, prodespGetOriginalFieldValue(originalData, col, originalKey))
      ) {
        updates.push({ coluna: col, valor: novo });
      }
    });

    const motivosAlterados = !window.arraysIguaisNumeros(motivosForaPadrao, motivosForaPadraoOriginalEdit);

    if (updates.length === 0 && !motivosAlterados && newObservacao.length === 0 && newEquipamentoEdit.length === 0 && newLinksEdit.length === 0 && deletedObservacaoIds.length === 0 && deletedEquipamentoIds.length === 0 && deletedLinkIds.length === 0) {
      showToast("Nenhuma alteração para salvar.", "info");
      return;
    }

    // --- Processo de salvamento em etapas (mesma ordem do auto-save) ---
    let allSuccess = true;

    if (updates.length > 0 || motivosAlterados) {
      const hasLbUpdate = updates.some((u) =>
        ["loopback_vivo", "loopback_cliente", "loopback_on_bgp"].includes(u.coluna)
      );
      if (hasLbUpdate) {
        const uniqOk = await prodespCheckUniquenessBeforeSave({
          id_unidade: originalData.id_unidades_atendimentos || originalData.id_unidades,
          loopbacks: prodespCollectLoopbacksForUniqueness("edit"),
        }, { context: "edit" });
        if (!uniqOk) return;
      }
      const response = await fetch("/prodesp/atendimentos/update", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id,
          updates,
          motivos_fora_padrao: motivosForaPadrao,
          finalizing: isFinalizing,
          ...(typeof prodespPayloadObservacoesAtomicasUpdate === "function"
            ? prodespPayloadObservacoesAtomicasUpdate()
            : {
                transicao_observacoes:
                  typeof prodespConsumeTransicaoObservacoes === "function"
                    ? prodespConsumeTransicaoObservacoes()
                    : null,
              }),
        }),
      });
      let resp;
      try {
        resp = await response.json();
      } catch (parseErr) {
        prodespNotifySaveFailure(null, prodespFriendlyFetchError(parseErr));
        allSuccess = false;
        prodespRevertStatusSubstatusParaPersistido("edit");
        resp = null;
      }
      if (resp && !resp.success) {
        prodespNotifySaveFailure(null, resp.message);
        allSuccess = false;
        prodespRevertStatusSubstatusAposFalhaUpdate("edit", response, resp);
      } else if (resp && resp.success) {
        if (typeof prodespAplicarObservacoesTransicaoPersistidasNoUpdate === "function") {
          prodespAplicarObservacoesTransicaoPersistidasNoUpdate("edit", resp);
        }
        motivosForaPadraoOriginalEdit = [...motivosForaPadrao];
        updates.forEach((u) => {
          const mapped = keyMap[u.coluna];
          if (mapped) originalData[mapped] = u.valor;
        });
        if (substatusValueTrim && substatusValueTrim !== oldSubSave) {
          prodespAplicarLiberacaoAnalistasCampos("edit", oldSubSave, substatusValueTrim, {
            comObservacao: false,
          });
        }
        prodespSyncOriginalDataAnalistasFromDom("edit");
        editPersistedSubstatus = (document.getElementById("editSubstatus").value || "").trim();
        editPersistedStatus = (document.getElementById("editStatus").value || "").trim();
        if (
          editPersistedSubstatus &&
          !PRODESP_SUBSTATUS_AGUARDA_EXTERNO.has(editPersistedSubstatus) &&
          editPersistedSubstatus !== SUBSTATUS_COM_SUPORTE
        ) {
          editFlowBaselineSubstatus = editPersistedSubstatus;
        }
      }
    }

    if (allSuccess && (newObservacao.length > 0 || deletedObservacaoIds.length > 0)) {
      const obsOk = await prodespSaveAtendimentoObservacoes("edit", {
        toast: false,
        includeTransicaoStaging: true,
      });
      if (!obsOk) {
        allSuccess = false;
      } else {
        newObservacao.forEach((o) => delete o._transicaoStaging);
      }
    } else if (
      !allSuccess &&
      typeof prodespDescartarObservacaoTransicaoStaging === "function"
    ) {
      newObservacao
        .filter((o) => o._transicaoStaging)
        .slice()
        .forEach((o) => prodespDescartarObservacaoTransicaoStaging("edit", o));
    }

    if (allSuccess && (newEquipamentoEdit.length > 0 || deletedEquipamentoIds.length > 0)) {
      const respEq = await fetch("/prodesp/equipamentos-update", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_atendimento: id,
          id_unidade_equipamentos: originalData.id_unidades_atendimentos,
          new_equipamentos: newEquipamentoEdit,
          deleted_equipamentos: deletedEquipamentoIds,
        }),
      }).then((r) => r.json());
      if (!respEq.success) {
        prodespNotifySaveFailure("equipamentos", respEq.message);
        allSuccess = false;
      }
    }

    if (allSuccess && (newLinksEdit.length > 0 || deletedLinkIds.length > 0)) {
      const respLnk = await fetch("/prodesp/links-update", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_atendimento: id,
          id_unidade_links: originalData.id_unidades_atendimentos,
          new_links: newLinksEdit,
          deleted_links: deletedLinkIds,
        }),
      }).then((r) => r.json());
      if (!respLnk.success) {
        prodespNotifySaveFailure("links", respLnk.message);
        allSuccess = false;
      }
    }

    // --- Finalização ---
    if (allSuccess) {
      prodespNotifySaveSuccess("edit");
      const dt = $("#tabela-atendimentos").DataTable();
      if (dt && dt.ajax) {
        dt.ajax.reload(null, false);
      }
    } else {
      prodespNotifySaveFailure("atendimento", "Uma ou mais etapas falharam. Verifique as mensagens acima.");
    }
  } finally {
    setButtonLoading(saveButton, false); // Garante que o botão seja reativado
  }
}

// ------------------------------
// REFERÊNCIAS GLOBAIS
// ------------------------------

const createIdVgrEl = document.getElementById("createIdVgr");
const createForm = document.getElementById("createForm");
const createStatusEl = document.getElementById("createStatus");
const createSubstatusEl = document.getElementById("createSubstatus");
let selectedUnidadeId = null;
let currentCreateModalAtendimentoId = null;
window.currentCreateModalAtendimentoId = null;
const btnCreateIncident = document.getElementById("btnCreateIncident");
const logConfiguracaoRemotaEdit = document.getElementById("log-configuracao-remota-edit");
const logConfiguracaoRemotaCreate = document.getElementById("log-configuracao-remota-create");

// This variable is not used anywhere else, can be removed.
let originalCreateStatusOptions;

// -------------------------------------------------------------------------------
// FUNÇÃO DE LIMPEZA DOS CAMPOS DA UNIDADE
// -------------------------------------------------------------------------------

function setCreateModalFieldsDisabled(isDisabled) {
  const form = document.getElementById("createForm");
  const elements = form.querySelectorAll("input, select, textarea");
  elements.forEach((el) => {
    if (el.type === "hidden" && el.id === "createAnalistaMplsAtendimentos") return;
    // Desabilita todos os campos por padrão, permitindo que o ID VGR seja preenchido
    if (el.id !== "createIdVgr") {
      // Garante que o campo de descrição de equipamento seja sempre apenas leitura
      if (el.id === "createEquipamentoDescricao") {
        el.readOnly = true;
        el.disabled = isDisabled; // Segue o estado de bloqueio geral do formulário
      } else {
        el.disabled = isDisabled;
      }
    }
  });

  // Controla os botões de ação e adição de itens do formulário de criação
  const actionButtonIds = [
    "btn-add-log-create",
    "btn-add-observacao-create",
    "btn-add-equipamento-create",
    "btn-confirm-equipamento-create",
    "btn-cancel-equipamento-create",
    "btn-add-link-create",
    "btn-confirm-link-create",
    "btn-cancel-link-create",
    "btnCreateIncident"
  ];

  actionButtonIds.forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = isDisabled;
  });

  // Bloqueia/Desbloqueia botões dentro das listas renderizadas (Equipamentos, Links, Observações, Logs)
  const listContainers = ["log-equipamento-create", "log-link-create", "log-observacao-create", "log-configuracao-remota-create"];
  listContainers.forEach(containerId => {
    const container = document.getElementById(containerId);
    if (container) {
      const internalButtons = container.querySelectorAll("button");
      internalButtons.forEach(btn => btn.disabled = isDisabled);
    }
  });
  const subCreate = (document.getElementById("createSubstatus")?.value || "").trim();
  prodespUpdateAnalistaMplsUi("create", subCreate, { formDisabled: isDisabled });
  prodespApplyAnalistaImplantacaoAdminUi("create", isDisabled);
  if (isDisabled) {
    prodespApplyDadosFieldPreAtendimentoUi();
  }
}

function clearCreateUnidadeFields() {
  [
    "createNome",
    "createAcronimo",
    "createHostname",
    "createEndereco",
    "createNumero",
    "createComplemento",
    "createBairro",
    "createMunicipio",
    "createEstado",
    "createDataAgendamento",
    "createHoraAgendamento",
    "createCep",
    "createLatitude",
    "createLongitude",
    "createTelefoneContato",
    "createIpLan01",
    "createIpLanTransito",
    "createIdintragov",
    // These are not in the clear list, but should be.
    // 'createLoopbackVivo', 'createLoopbackCliente'
    "createLoopbackVivo",
    "createLoopbackCliente",
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });
  selectedUnidadeId = null;
}

// -------------------------------------------------------------------------------
// PRÉ‑CARREGA UNIDADE QUANDO ID VGR É PREENCHIDO
// -------------------------------------------------------------------------------
if (createIdVgrEl) {
  createIdVgrEl.addEventListener("blur", async () => {
    const idVgr = createIdVgrEl.value.trim();
    if (!idVgr) {
      // Se limpar o campo, volta ao estado de bloqueio total
      setCreateModalFieldsDisabled(true);
      prodespSetCreateUnidadeObservacoesEnabled(false);
      return;
    }

    try {
      // 1. Validar se a unidade existe e buscar seus dados (campos, equipamentos e links)
      const unidadeResponse = await fetch(`/prodesp/unidades/${encodeURIComponent(idVgr)}`);
      const json = await unidadeResponse.json();

      if (!json.success) {
        // Bloqueio se não encontrar o ID VGR na base de unidades
        showToast("ID VGR não encontrado na base de dados. Por favor, realize o upload das informações via CSV - Inserção em Massa.", "danger");
        setCreateModalFieldsDisabled(true); // Re-disables all except ID VGR
        if (createStatusEl) {
          createStatusEl.disabled = true;
          createStatusEl.value = "";
        }
        clearCreateUnidadeFields();
        selectedUnidadeId = null;
        prodespSetCreateUnidadeObservacoesEnabled(false);
        return;
      }

      // Unidade encontrada: popula as informações básicas e os equipamentos/links
      const u = json.unidade;
      selectedUnidadeId = u.id_unidade;

      document.getElementById("createNome").value = u.nome || "";
      document.getElementById("createAcronimo").value = u.acronimo || "";
      document.getElementById("createHostname").value = u.hostname || "";
      document.getElementById("createEndereco").value = u.endereco || "";
      document.getElementById("createNumero").value = u.numero || "";
      document.getElementById("createComplemento").value = u.complemento || "";
      document.getElementById("createBairro").value = u.bairro || "";
      document.getElementById("createMunicipio").value = u.municipio || "";
      document.getElementById("createEstado").value = u.estado || "";
      document.getElementById("createDataAgendamento").value = u.data_agendamento || "";
      document.getElementById("createHoraAgendamento").value = formatHoraParaInputTime(u.hora_agendamento) || "";
      prodespEnsureContratadaOption("createContratada", u.contratada_planejada);
      const createContratadaEl = document.getElementById("createContratada");
      if (createContratadaEl) createContratadaEl.value = u.contratada_planejada || "";
      const createFieldEl = document.getElementById("createField");
      if (createFieldEl) createFieldEl.value = u.field_planejada || "";
      const createContatoFieldEl = document.getElementById("createContatoField");
      if (createContatoFieldEl) createContatoFieldEl.value = u.contato_field_planejada || "";
      document.getElementById("createCep").value = u.cep || "";
      prodespSetMaskedFieldValue("create", "Latitude", u.latitude);
      prodespSetMaskedFieldValue("create", "Longitude", u.longitude);
      document.getElementById("createTelefoneContato").value = u.telefone_contato || "";
      prodespSetMaskedFieldValue("create", "IpLan01", u.ip_lan_01);
      prodespSetMaskedFieldValue("create", "IpLanTransito", u.ip_lan_transito);
      document.getElementById("createIdintragov").value = u.id_intragov || "";
      prodespSetMaskedFieldValue("create", "LoopbackVivo", u.loopback_vivo);
      prodespSetMaskedFieldValue("create", "LoopbackCliente", u.loopback_cliente);
      prodespSetMaskedFieldValue("create", "LoopbackOnBgp", u.loopback_on_bgp);
      PRODESP_MV_OPCIONAIS_JS_KEYS.forEach((col) => {
        prodespSetMaskedFieldValue("create", pascalize(col), u[col]);
      });
      PRODESP_LAN_EXTRA_JS_KEYS.forEach((col) => {
        prodespSetMaskedFieldValue("create", pascalize(col), u[col]);
      });
      const createTicketNocEl = document.getElementById("createTicketNoc");
      if (createTicketNocEl) createTicketNocEl.value = prodespCoerceInputValue(u.ticket_noc);

      // Carrega Equipamentos e Links vindos do banco para a UI do modal de criação
      reloadEquipamentos(u.equipamentos, 'create');
      reloadLinks(u.links, 'create');
      prodespRefreshLiveFieldValidation('create');

      newObservacaoUnidade.length = 0;
      deletedObservacaoUnidadeIds.length = 0;
      reloadObservacoes(u.observacoes || [], "unidade");
      prodespSetCreateUnidadeObservacoesEnabled(true);

      // ID VGR encontrado: Desbloqueia APENAS o campo de status para iniciar o atendimento
      if (createStatusEl) createStatusEl.disabled = false;
      prodespApplyDadosFieldPreAtendimentoUi();

      // 2. Verificar histórico de atendimentos (Redirecionamento ou Avisos)
      const checkResponse = await fetch(`/prodesp/atendimentos/verificar_id_vgr/${encodeURIComponent(idVgr)}`);
      const checkData = await checkResponse.json();

      if (checkData.aviso) {
        if (checkData.action_type === "redirect_edit") {
          showToast(checkData.mensagem, "info");
          bootstrap.Modal.getInstance(document.getElementById("createModal")).hide();
          setTimeout(() => editDetails(checkData.atendimento_id), 500);
          return;
        }

        if (checkData.action_type === "block_creation") {
          showToast(checkData.mensagem, "danger");
          setCreateModalFieldsDisabled(true);
          prodespSetCreateUnidadeObservacoesEnabled(false);
          if (createStatusEl) createStatusEl.disabled = true;
          return;
        }

        if (checkData.action_type === "warn_and_continue") {
          showToast(checkData.mensagem, "warning");
          
          // Observações carregadas do atendimento anterior:
          if (checkData.previous_observacoes && checkData.previous_observacoes.length > 0) {
            const obsContainer = document.getElementById('log-observacao-create');
            if (obsContainer) {
              const obsTitle = document.createElement('p');
              obsTitle.className = 'text-muted fst-italic mt-2';
              obsTitle.textContent = 'Observações carregadas do atendimento anterior:';
              obsContainer.insertBefore(obsTitle, obsContainer.querySelector('.titles-incident'));

              checkData.previous_observacoes.forEach(obs => {
                const normalized = {
                  data_observacao: obs.data_observacao,
                  observacao_prodesp: obs.observacao_prodesp,
                  _stagingPreviousAtendimento: true,
                };
                if (!newObservacaoCreate.some(o => o.observacao_prodesp === normalized.observacao_prodesp)) {
                  newObservacaoCreate.push(normalized);
                  renderObservacaoCard(normalized, obsContainer, newObservacaoCreate, null);
                }
              });
            }
          }
        }
      }
    } catch (err) {
      console.error("Erro no fluxo de validação do ID VGR:", err);
      showToast("Ocorreu um erro ao processar os dados do ID VGR.", "danger");
    }
  });
}

// -----------------------------------------------------------------------------------
// ABRE O MODAL DE CRIAÇÃO
// -----------------------------------------------------------------------------------
async function openCreateModal() {
  if (typeof window.prodespEnsureModalScripts === "function") {
    await window.prodespEnsureModalScripts(["enriquecer", "caderno", "certificado"]);
  }
  createForm.reset();
  clearCreateUnidadeFields();
  newObservacaoCreate.length = 0;
  newObservacaoUnidade.length = 0;
  deletedObservacaoUnidadeIds.length = 0;
  newEquipamentoCreate.length = 0;
  newLinksCreate.length = 0;
  // Reset editing states
  editingEquipmentId = null;
  existingEquipmentsCreate.length = 0;
  existingLinksCreate.length = 0;
  currentCreateModalAtendimentoId = null;
  window.currentCreateModalAtendimentoId = null;
  createPersistedSubstatus = "";
  const createMotivoAc = document.getElementById("createAguardandoClienteMotivo");
  if (createMotivoAc) createMotivoAc.value = "";
  window.limparMotivosSelecionados("create");

  // Estado inicial: a maioria dos campos e botões desabilitados
  setCreateModalFieldsDisabled(true);
  prodespSetCreateUnidadeObservacoesEnabled(false);
  if (createIdVgrEl) createIdVgrEl.disabled = false; // Habilita apenas o campo ID VGR

  const createAnalistaAtuanteEl = document.getElementById(
    "createAnalistaAtuante"
  );
  if (createAnalistaAtuanteEl) {
    createAnalistaAtuanteEl.value = USUARIO_LOGADO;
  }

  ["createAnalistaConfiguracao", "createAnalistaCadernoTeste"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });
  prodespApplyAnalistaImplantacaoAdminUi("create", true);
  prodespSetAnalistaMplsValor("create", "");
  prodespUpdateAnalistaMplsUi("create", "", { formDisabled: true });

  // Popula o campo Status com apenas a opção inicial
  if (createStatusEl) {
    createStatusEl.innerHTML = '<option selected disabled value="">Selecione o status...</option>';
    createStatusEl.add(new Option("Em Atendimento", "Em Atendimento"));
  }
  // Garante que o Substatus comece desabilitado e limpo
  const substatusEl = document.getElementById("createSubstatus");
  if (substatusEl) {
    substatusEl.innerHTML =
      '<option selected disabled value="">Selecione o Substatus...</option>';
    substatusEl.disabled = true;
  }

  if (btnCreateIncident) btnCreateIncident.textContent = "Criar";

  if (logContainerObservacaoCreate && observacaoCreateHeaderHtml) {
    // Ensure the header is present before setting innerHTML
    if (!logContainerObservacaoCreate.querySelector('.titles-incident')) {
        logContainerObservacaoCreate.innerHTML = observacaoCreateHeaderHtml;
    }
    logContainerObservacaoCreate.innerHTML = observacaoCreateHeaderHtml;
  }
  if (logContainerEquipamentoCreate) {
    prodespResetIncidentListContainer(logContainerEquipamentoCreate);
  }
  if (logContainerLinkCreate) {
    prodespResetIncidentListContainer(logContainerLinkCreate);
  }

  window.carregarMotivosForaPadrao("create").catch(err => {
    console.error("Erro ao carregar motivos fora do padrão:", err);
  });

  // Reset button states for equipment and links
  toggleEditButtons('create', false);

  // Força abertura da primeira aba
  const firstTabEl = document.getElementById("create-dados-unidade-conectividade-tab");
  if (firstTabEl) bootstrap.Tab.getOrCreateInstance(firstTabEl).show();

  prodespOpenModal(document.getElementById("createModal"));
  void prodespSyncCadernoToolbarAll();
}

window.openCreateModal = openCreateModal;

function getCreateModalData() {
  prodespSyncAnalistaMplsHidden("create");
  return {
    status: document.getElementById("createStatus").value,
    substatus: document.getElementById("createSubstatus").value,
    analista_atuante: document.getElementById("createAnalistaAtuante").value,
    analista_configuracao: document.getElementById("createAnalistaConfiguracao").value,
    analista_mpls_atendimentos: prodespGetAnalistaMplsValor("create"),
    analista_caderno_teste: document.getElementById("createAnalistaCadernoTeste").value,
    contratada: document.getElementById("createContratada").value,
    field: document.getElementById("createField").value,
    contato_field: (document.getElementById("createContatoField")?.value || "").replace(/\D/g, ""),
    motivos_fora_padrao: window.coletarMotivosSelecionados("create"),
  };
}

/** Campos de unidade do modal criar (alinhado a edit jsFields / unit_fields_map no backend). */
function prodespCollectCreateUnidadeFields() {
  const readIp = (id, col) => {
    const el = document.getElementById(id);
    if (!el) return "";
    return prodespReadEditableFieldValue(el, col);
  };
  return {
    nome: (document.getElementById("createNome")?.value || "").trim(),
    acronimo: (document.getElementById("createAcronimo")?.value || "").trim(),
    hostname: (document.getElementById("createHostname")?.value || "").trim(),
    endereco: (document.getElementById("createEndereco")?.value || "").trim(),
    numero: (document.getElementById("createNumero")?.value || "").trim(),
    complemento: (document.getElementById("createComplemento")?.value || "").trim(),
    bairro: (document.getElementById("createBairro")?.value || "").trim(),
    municipio: (document.getElementById("createMunicipio")?.value || "").trim(),
    estado: (document.getElementById("createEstado")?.value || "").trim(),
    data_agendamento: document.getElementById("createDataAgendamento")?.value || "",
    hora_agendamento: document.getElementById("createHoraAgendamento")?.value || "",
    cep: (document.getElementById("createCep")?.value || "").trim(),
    latitude: readIp("createLatitude", "latitude"),
    longitude: readIp("createLongitude", "longitude"),
    telefone_contato: (document.getElementById("createTelefoneContato")?.value || "").trim(),
    ip_lan_01: prodespStripIpSpaces(readIp("createIpLan01", "ip_lan_01")),
    ip_lan_transito: prodespStripIpSpaces(readIp("createIpLanTransito", "ip_lan_transito")),
    id_intragov: (document.getElementById("createIdintragov")?.value || "").trim(),
    loopback_vivo: prodespStripIpSpaces(readIp("createLoopbackVivo", "loopback_vivo")),
    loopback_cliente: prodespStripIpSpaces(readIp("createLoopbackCliente", "loopback_cliente")),
    loopback_on_bgp: prodespStripIpSpaces(readIp("createLoopbackOnBgp", "loopback_on_bgp")),
    ticket_noc: (document.getElementById("createTicketNoc")?.value || "").trim(),
    ...Object.assign({}, prodespCollectMvOpcionaisFromPrefix("create"), prodespCollectLanExtraFromPrefix("create")),
  };
}

/** Colunas do POST /atendimentos/update no fluxo criar (finalizar / auto-save substatus). */
const PRODESP_CREATE_UPDATE_FIELD_KEYS = [
  "status",
  "substatus",
  "analista_atuante",
  "analista_configuracao",
  "analista_mpls_atendimentos",
  "analista_caderno_teste",
  "contratada",
  "field",
  "contato_field",
  "logs",
  "nome",
  "acronimo",
  "hostname",
  "endereco",
  "numero",
  "bairro",
  "municipio",
  "estado",
  "complemento",
  "data_agendamento",
  "hora_agendamento",
  "cep",
  "latitude",
  "longitude",
  "telefone_contato",
  "ip_lan_01",
  "ip_lan_transito",
  "id_intragov",
  "loopback_vivo",
  "loopback_cliente",
  "loopback_on_bgp",
  "ticket_noc",
  ...PRODESP_MV_OPCIONAIS_JS_KEYS,
  ...PRODESP_LAN_EXTRA_JS_KEYS,
];
function getSanitizedValue(elementId) {
  const el = document.getElementById(elementId);
  if (!el) return null;

  if (
    el.tagName === "SELECT" &&
    el.options[el.selectedIndex] &&
    el.options[el.selectedIndex].disabled
  ) {
    return null;
  }
  return el.value || null;
}

if (createStatusEl) {
  // Listener para o campo Status no Modal de Criação
  createStatusEl.addEventListener("change", async function () {
    const statusValue = this.value;
    const idVgrValue = document.getElementById("createIdVgr").value.trim();
    const substatusEl = document.getElementById("createSubstatus");
    const finalStatusesForValidation = ["Concluído", "Quebra", "Concluído Parcial"];

    if (finalStatusesForValidation.includes(statusValue)) {
      // Regras de validação para finalização
      const validationRules = [
        { id: 'createSubstatus', name: 'Substatus' },
        { id: 'createField', name: 'Field' },
        { id: 'createContatoField', name: 'Contato Field' },
        { id: 'createContratada', name: 'Contratada' },
      ];

      // Executa a validação aprimorada que destaca campos e accordions
      const emptyFields = validateFields(validationRules);
      const ticketMissing =
        prodespRequiresTicketNoc(statusValue, document.getElementById("createSubstatus")?.value)
          ? prodespValidateTicketNoc("create")
          : [];

      if (emptyFields.length > 0 || ticketMissing.length > 0) {
        prodespNotifyValidationBlocked(
          [...emptyFields, ...ticketMissing],
          `Para usar o status «${statusValue}», preencha os campos obrigatórios`,
          "create"
        );
        return;
      }
    }

    // Lógica para popular dinamicamente o Substatus
    if (substatusEl) {
      const subInicial =
        createPersistedSubstatus || SUBSTATUS_INICIAL_FILA;
      populateSubstatus(
        substatusEl,
        statusValue,
        statusValue === "Em Atendimento" ? subInicial : substatusEl.value,
        undefined,
        undefined,
        "create",
        { emitChange: false }
      );
      if (statusValue === "Em Atendimento" && !createPersistedSubstatus) {
        createFlowBaselineSubstatus = SUBSTATUS_INICIAL_FILA;
        if (
          substatusEl.querySelector(`option[value="${SUBSTATUS_INICIAL_FILA}"]`)
        ) {
          substatusEl.value = SUBSTATUS_INICIAL_FILA;
        }
      }
    }

    if (
      !selectedUnidadeId && !idVgrValue &&
      (statusValue === "Em Atendimento")
    ) {
      showToast("Por favor, preencha o ID VGR e selecione uma unidade antes de definir o status.", "warning");
      this.value = ""; // Redefine status de seleção
      return;
    }

    let payload;

    if (statusValue === "Em Atendimento") {
      // Inicia atendimento com status "Em Atendimento"
      if (!currentCreateModalAtendimentoId) {
        const fieldConfirm = await prodespConfirmDadosFieldAntesIniciar();
        if (!fieldConfirm.confirmed) {
          this.value = "";
          if (substatusEl) {
            substatusEl.innerHTML =
              '<option selected disabled value="">Selecione o Substatus...</option>';
            substatusEl.disabled = true;
          }
          showToast("Início do atendimento cancelado.", "info");
          return;
        }
        prodespApplyDadosFieldConfirmadosAoCreate(fieldConfirm);

        setCreateModalFieldsDisabled(false);
        payload = {
          status: statusValue,
          id_vgr: idVgrValue,
          id_unidade: selectedUnidadeId,
          analista_atuante: document.getElementById("createAnalistaAtuante").value,
          analista_configuracao: document.getElementById("createAnalistaConfiguracao").value,
          analista_mpls_atendimentos: prodespGetAnalistaMplsValor("create"),
          analista_caderno_teste: document.getElementById("createAnalistaCadernoTeste").value,
          substatus: getSanitizedValue("createSubstatus") || SUBSTATUS_INICIAL_FILA,
          contratada: getSanitizedValue("createContratada"),
          logs: serializeLogEntries(logsCreate),
          field: getSanitizedValue("createField"),
          contato_field: (document.getElementById("createContatoField")?.value || "").replace(/\D/g, ""),
          ...prodespCollectCreateUnidadeFields(),
          new_observacoes: newObservacaoCreate,
          new_equipamentos: newEquipamentoCreate,
          new_links: newLinksCreate,
        };

        try {
          const reval = await prodespRevalidarIdVgrParaCreate(idVgrValue);
          if (!reval.proceed) {
            if (reval.redirectEdit) {
              prodespRedirecionarCreateParaEdicao(reval.atendimentoId, reval.message);
            } else {
              showToast(reval.message || "Não foi possível iniciar o atendimento.", "danger");
            }
            this.value = "";
            setCreateModalFieldsDisabled(true);
            if (createStatusEl) createStatusEl.disabled = false;
            prodespApplyDadosFieldPreAtendimentoUi();
            return;
          }

          const res = await fetch("/prodesp/atendimentos/create", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const result = await res.json();
          if (result.success) {
            currentCreateModalAtendimentoId = result.id;
            window.currentCreateModalAtendimentoId = result.id;
            if (typeof window.prodespCadernoAtualizarToolbar === "function") {
              window.prodespCadernoAtualizarToolbar();
            }
            createPersistedStatus = (statusValue || "Em Atendimento").trim();
            createPersistedSubstatus = (
              getSanitizedValue("createSubstatus") || SUBSTATUS_INICIAL_FILA
            ).trim();
            createFlowBaselineSubstatus = createPersistedSubstatus;
            if (result.id_unidade) selectedUnidadeId = result.id_unidade;
            if (btnCreateIncident)
              btnCreateIncident.textContent = "Salvar Atendimento";
            showToast(`Atendimento iniciado com sucesso. ID: ${result.id}`, "success");

            createStatusEl.innerHTML = '<option selected disabled value="">Selecione o status...</option>'; // Mantém o placeholder
            createStatusEl.add(new Option("Em Atendimento", "Em Atendimento"));
            createStatusEl.add(new Option("Quebra", "Quebra"));
            createStatusEl.add(new Option("Concluído", "Concluído"));
            createStatusEl.add(new Option("Concluído Parcial", "Concluído Parcial"));
            createStatusEl.value = statusValue;

            deletedObservacaoUnidadeIds.length = 0;
            newObservacaoUnidade.length = 0;
            await prodespReloadObservacoesFromAtendimento(result.id, "create");
            newEquipamentoCreate.length = 0;
            newLinksCreate.length = 0;
          } else if (prodespTratarRespostaCreateDuplicada(res, result)) {
            this.value = "";
            setCreateModalFieldsDisabled(true);
            if (createStatusEl) createStatusEl.disabled = false;
            prodespApplyDadosFieldPreAtendimentoUi();
          } else {
            showToast(`Erro ao iniciar atendimento: ${result.message}`, "danger");
            this.value = "";
            setCreateModalFieldsDisabled(true);
            if (createStatusEl) createStatusEl.disabled = false;
            prodespApplyDadosFieldPreAtendimentoUi();
          }
        } catch (err) {
          showToast(`Erro de comunicação ao criar atendimento: ${prodespFriendlyFetchError(err)}`, "danger");
          this.value = "";
          setCreateModalFieldsDisabled(true);
          if (createStatusEl) createStatusEl.disabled = false;
          prodespApplyDadosFieldPreAtendimentoUi();
        }
      } else {
        setCreateModalFieldsDisabled(false);
      }
    } else {
      if (currentCreateModalAtendimentoId) {
        setCreateModalFieldsDisabled(false);
      } else {
        setCreateModalFieldsDisabled(true);
      }
    }
  });
}

["edit", "create"].forEach((ctx) => {
  prodespInitAnalistaMplsSelectOptions(ctx);
  const selMpls = document.getElementById(`${ctx}AnalistaMplsSelect`);
  const outrosMpls = document.getElementById(`${ctx}AnalistaMplsOutros`);
  if (selMpls && !selMpls.dataset.prodespBound) {
    selMpls.dataset.prodespBound = "1";
    selMpls.addEventListener("change", () => {
      void prodespOnAnalistaMplsSelectChange(ctx);
    });
  }
  if (outrosMpls && !outrosMpls.dataset.prodespBound) {
    outrosMpls.dataset.prodespBound = "1";
    outrosMpls.addEventListener("input", () => {
      prodespSyncAnalistaMplsHidden(ctx);
      document.getElementById(`${ctx}AnalistaMplsAtendimentos`)?.dispatchEvent(
        new Event("input", { bubbles: true })
      );
    });
    outrosMpls.addEventListener("blur", () => {
      const sel = document.getElementById(`${ctx}AnalistaMplsSelect`);
      if (sel?.value === PRODESP_ANALISTA_MPLS_OUTROS_VALUE) {
        void prodespMaybeIrParaEmConfigMplsAposAnalista(ctx);
      }
    });
  }
});

if (createSubstatusEl) {
  // Listener único de substatus no create (mesma ordem do edit)
  createSubstatusEl.addEventListener("change", async function () {
    if (
      prodespSubstatusChangeInFlight ||
      prodespQuebraEncerramentoInProgress ||
      suppressQuebraEncerramentoChange
    ) {
      return;
    }
    prodespSubstatusChangeInFlight = true;
    try {
      const oldSub = (
        createPersistedSubstatus ||
        createFlowBaselineSubstatus ||
        SUBSTATUS_INICIAL_FILA
      ).trim();
      const novoSub = (this.value || "").trim();
      const agGpBlockCreate = prodespValidarTransicaoSubstatusAgGp(
        oldSub,
        novoSub,
        (createStatusEl?.value || "").trim()
      );
      if (agGpBlockCreate) {
        prodespRevertSubstatusParaValor("create", oldSub || SUBSTATUS_INICIAL_FILA);
        showToast(agGpBlockCreate, "warning");
        return;
      }
      if (!suppressQuebraEncerramentoChange) {
        const handledQuebra = await prodespRunQuebraEncerramentoFlow(
          "create",
          createSubstatusEl,
          createStatusEl
        );
        if (handledQuebra) return;
      }
      const handledAguarda = await prodespRunAguardaExternoSubstatusFlow(
        "create",
        createSubstatusEl,
        createStatusEl
      );
      if (handledAguarda) return;
      const handledObs = await prodespRunObservacaoSubstatusFlows(
        "create",
        createSubstatusEl,
        createStatusEl
      );
      if (handledObs) return;
      if (prodespIsTriagemParaFilaAguardando(oldSub, novoSub)) {
        const dadosFieldMissing = prodespValidateDadosFieldTriagemParaAguardando(
          "create",
          oldSub,
          novoSub
        );
        if (dadosFieldMissing.length > 0) {
          prodespRevertSubstatusParaValor("create", oldSub || SUBSTATUS_INICIAL_FILA);
          prodespNotifyValidationBlocked(
            dadosFieldMissing,
            "Para enviar da Gestão para a fila Aguardando, preencha os Dados Field"
          );
          return;
        }
      }

      const mplsMissingCreate = prodespValidateAnalistaMplsTerceiro("create", oldSub, novoSub);
      if (mplsMissingCreate.length > 0) {
        prodespRevertSubstatusParaValor("create", oldSub || SUBSTATUS_INICIAL_FILA);
        prodespNotifyValidationBlocked(
          mplsMissingCreate,
          prodespMensagemAnalistaMplsObrigatorio(oldSub, novoSub)
        );
        prodespUpdateAnalistaMplsUi("create", novoSub, { formDisabled: false });
        return;
      }

      const hostnameMissingCreate = prodespValidateHostnameObrigatorio(
        "create",
        oldSub,
        novoSub,
        (createStatusEl?.value || "").trim()
      );
      if (hostnameMissingCreate.length > 0) {
        prodespRevertSubstatusParaValor("create", oldSub || SUBSTATUS_INICIAL_FILA);
        prodespNotifyValidationBlocked(
          hostnameMissingCreate,
          "Para sair de «Em Configuração Remota» ou concluir, preencha o Hostname",
          "create"
        );
        return;
      }

      prodespProcessarLiberacaoAnalistas("create", oldSub, novoSub);

      populateSubstatus(this, createStatusEl.value, this.value, undefined, undefined, "create");
      prodespUpdateAnalistaMplsUi("create", novoSub, { formDisabled: false });
      if (typeof window.prodespCadernoAtualizarToolbar === "function") {
        window.prodespCadernoAtualizarToolbar();
      }

      if (suppressAguardandoClienteChange) return;

      if (!isEnteringAguardaExterno("create")) {
        prodespTriggerAutoSaveFromSubstatusChange("create");
      }
    } finally {
      prodespSubstatusChangeInFlight = false;
    }
  });
}


// ---------------------------------------------------------------------------------
// FUNÇÃO PARA AUTO-SALVAR DADOS NO MODAL DE CRIAÇÃO
// ---------------------------------------------------------------------------------
let autoSaveTimeout = null; // Global variable for debounce timeout

async function autoSaveCreateModalData(options = false) {
  const { showSuccessToast, notifyFailure, skipQuebraEncerramentoCheck } =
    prodespNormalizeAutoSaveOpts(options);
  let failureNotified = false;
  let failureWasExpectedBusiness = false;
  const fail = (scope, detail) => {
    if (prodespIsExpectedBusinessError(detail)) {
      failureWasExpectedBusiness = true;
    }
    if (notifyFailure) {
      prodespNotifySaveFailure(scope, detail);
      failureNotified = true;
    }
  };

  if (!currentCreateModalAtendimentoId) {
    console.warn("Attempted auto-save without an existing attendance ID.");
    return false;
  }

  const substatusAtualCreate = (document.getElementById("createSubstatus")?.value || "").trim();
  const oldSubCreate = (
    createPersistedSubstatus || createFlowBaselineSubstatus || SUBSTATUS_INICIAL_FILA
  ).trim();
  const dadosFieldMissingCreate = prodespValidateDadosFieldTriagemParaAguardando(
    "create",
    oldSubCreate,
    substatusAtualCreate
  );
  if (dadosFieldMissingCreate.length > 0) {
    prodespRevertSubstatusParaValor("create", oldSubCreate || SUBSTATUS_INICIAL_FILA);
    prodespNotifyValidationBlocked(
      dadosFieldMissingCreate,
      "Para enviar da Gestão para a fila Aguardando, preencha os Dados Field"
    );
    return false;
  }

  const mplsMissingCreateAuto = prodespValidateAnalistaMplsTerceiro(
    "create",
    oldSubCreate,
    substatusAtualCreate
  );
  if (mplsMissingCreateAuto.length > 0) {
    prodespRevertSubstatusParaValor("create", oldSubCreate || SUBSTATUS_INICIAL_FILA);
    prodespNotifyValidationBlocked(
      mplsMissingCreateAuto,
      prodespMensagemAnalistaMplsObrigatorio(oldSubCreate, substatusAtualCreate)
    );
    prodespUpdateAnalistaMplsUi("create", substatusAtualCreate, { formDisabled: false });
    return false;
  }

  const statusCreateAuto = (document.getElementById("createStatus")?.value || "").trim();
  const hostnameMissingCreateAuto = prodespValidateHostnameObrigatorio(
    "create",
    oldSubCreate,
    substatusAtualCreate,
    statusCreateAuto
  );
  if (hostnameMissingCreateAuto.length > 0) {
    prodespRevertSubstatusParaValor("create", oldSubCreate || SUBSTATUS_INICIAL_FILA);
    prodespNotifyValidationBlocked(
      hostnameMissingCreateAuto,
      "Para sair de «Em Configuração Remota» ou concluir, preencha o Hostname",
      "create"
    );
    return false;
  }

  const quebraMotivosCreateAuto = prodespValidateMotivosQuebraObrigatorios("create");
  if (quebraMotivosCreateAuto.length > 0) {
    prodespNotifyValidationBlocked(
      quebraMotivosCreateAuto,
      "Para encerrar com Quebra, selecione ao menos um motivo em Fora do padrão",
      "create"
    );
    return false;
  }
  if (!skipQuebraEncerramentoCheck && isEnteringQuebraEncerramento("create")) {
    prodespNotifyValidationBlocked(
      ["Motivo da quebra (observação)"],
      "Selecione o substatus de Quebra novamente para registrar o motivo da quebra",
      "create"
    );
    return false;
  }

  if (substatusAtualCreate && substatusAtualCreate !== oldSubCreate) {
    prodespAplicarLiberacaoAnalistasCampos("create", oldSubCreate, substatusAtualCreate, {
      comObservacao: true,
    });
  }

  let savedSomething = false;
  const updates = [];
  const payloadForLists = {
    // Dados necessários para observações e atualizações de equipamentos
    id_atendimento: currentCreateModalAtendimentoId,
    id_unidade_equipamentos: selectedUnidadeId,
    new_observacoes: newObservacaoCreate,
    new_equipamentos: newEquipamentoCreate,
    new_links: newLinksCreate,
  };

  // Coletar todos os dados atuais do formulário para os principais campos da Unidade
  const currentFormData = getCreateModalData();
  const motivosForaPadrao = currentFormData.motivos_fora_padrao || [];
  delete currentFormData.motivos_fora_padrao;

  const combinedData = {
    ...currentFormData,
    ...prodespCollectCreateUnidadeFields(),
  };

  for (const key in combinedData) {
    if (key === "motivos_fora_padrao") continue;
    let val = combinedData[key];
    if (key === 'logs') {
      val = serializeLogEntries(logsCreate);
    } else if (typeof val === 'string') {
      val = val.trim();
    }
    if ((key === "hora_agendamento" || key === "data_agendamento") && (val === "" || val == null)) {
      continue;
    }
    updates.push({ coluna: key, valor: val });
  }

  let allSuccess = true;

  // 1. Atualiza dados principais (substatus, unidade, etc.)
  if (updates.length > 0) {
    const hasLbUpdate = updates.some((u) =>
      ["loopback_vivo", "loopback_cliente", "loopback_on_bgp"].includes(u.coluna)
    );
    if (hasLbUpdate) {
      const uniqOk = await prodespCheckUniquenessBeforeSave({
        id_unidade: selectedUnidadeId,
        loopbacks: prodespCollectLoopbacksForUniqueness("create"),
      }, { context: "create" });
      if (!uniqOk) {
        fail(null, "Loopback duplicado. Corrija antes de salvar.");
        return;
      }
    }
    try {
      const statusValue = document.getElementById("createStatus")?.value || "";
      const resMain = await fetch("/prodesp/atendimentos/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: currentCreateModalAtendimentoId,
          updates: updates,
          motivos_fora_padrao: motivosForaPadrao,
          finalizing: prodespIsFinalStatus(statusValue),
          ...(typeof prodespPayloadObservacoesAtomicasUpdate === "function"
            ? prodespPayloadObservacoesAtomicasUpdate()
            : {
                transicao_observacoes:
                  typeof prodespConsumeTransicaoObservacoes === "function"
                    ? prodespConsumeTransicaoObservacoes()
                    : null,
              }),
        }),
      });
      const resultMain = await resMain.json();
      if (!resultMain.success) {
        fail(null, resultMain.message);
        allSuccess = false;
        prodespRevertStatusSubstatusAposFalhaUpdate("create", resMain, resultMain);
      } else {
        savedSomething = true;
        if (typeof prodespAplicarObservacoesTransicaoPersistidasNoUpdate === "function") {
          prodespAplicarObservacoesTransicaoPersistidasNoUpdate("create", resultMain);
        }
        if (substatusAtualCreate && substatusAtualCreate !== oldSubCreate) {
          prodespAplicarLiberacaoAnalistasCampos(
            "create",
            oldSubCreate,
            substatusAtualCreate,
            { comObservacao: false }
          );
        }
        createPersistedSubstatus = (
          document.getElementById("createSubstatus").value || ""
        ).trim();
        createPersistedStatus = (
          document.getElementById("createStatus").value || ""
        ).trim();
      }
    } catch (err) {
      fail(null, prodespFriendlyFetchError(err));
      allSuccess = false;
      prodespRevertStatusSubstatusParaPersistido("create");
      prodespLogUnexpectedSaveFailure("Auto-save: Falha ao atualizar dados principais.", null, err);
    }
  }

  // 2. Observações pendentes — somente após dados principais salvos com sucesso
  if (allSuccess && newObservacaoCreate.length > 0) {
    const obsOk = await prodespSaveAtendimentoObservacoes("create", {
      toast: false,
      includeTransicaoStaging: true,
    });
    if (!obsOk) {
      allSuccess = false;
    } else {
      savedSomething = true;
      newObservacaoCreate.forEach((o) => delete o._transicaoStaging);
    }
  } else if (
    !allSuccess &&
    typeof prodespDescartarObservacaoTransicaoStaging === "function"
  ) {
    newObservacaoCreate
      .filter((o) => o._transicaoStaging)
      .slice()
      .forEach((o) => prodespDescartarObservacaoTransicaoStaging("create", o));
  }

  // 3. Save new equipments
  if (payloadForLists.new_equipamentos.length > 0) {
    const equipmentsToSave = [...newEquipamentoCreate];
    newEquipamentoCreate.length = 0;

    try {
      const respEq = await fetch("/prodesp/equipamentos-update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...payloadForLists,
          new_equipamentos: equipmentsToSave,
        }),
      });
      const resultEq = await respEq.json();
      if (!resultEq.success) {
        fail("equipamentos", resultEq.message);
        newEquipamentoCreate.push(...equipmentsToSave);
        allSuccess = false;
      } else {
        savedSomething = true;
      }
    } catch (err) {
      fail("equipamentos", prodespFriendlyFetchError(err));
      newEquipamentoCreate.push(...equipmentsToSave);
      allSuccess = false;
      prodespLogUnexpectedSaveFailure("Auto-save: Falha ao salvar novos equipamentos.", null, err);
    }
  }

  // 4. Save new links
  if (payloadForLists.new_links.length > 0) {
    const linksToSave = [...newLinksCreate];
    newLinksCreate.length = 0;

    try {
      const respLnk = await fetch("/prodesp/links-update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_unidade_links: selectedUnidadeId,
          new_links: linksToSave,
        }),
      });
      const resultLnk = await respLnk.json();
      if (!resultLnk.success) {
        fail("links", resultLnk.message);
        newLinksCreate.push(...linksToSave);
        allSuccess = false;
      } else {
        savedSomething = true;
      }
    } catch (err) {
      fail("links", prodespFriendlyFetchError(err));
      newLinksCreate.push(...linksToSave);
      allSuccess = false;
      prodespLogUnexpectedSaveFailure("Auto-save: Falha ao salvar novos links.", null, err);
    }
  }

  if (allSuccess) {
    if (showSuccessToast && savedSomething) {
      prodespNotifySaveSuccess("create");
    }
  } else {
    if (!failureWasExpectedBusiness) {
      prodespLogUnexpectedSaveFailure(
        "Auto-save falhou para atendimento ID: " + currentCreateModalAtendimentoId
      );
    }
    if (notifyFailure && !failureNotified) {
      prodespNotifySaveFailure(null, "Não foi possível salvar todas as alterações. Verifique as mensagens acima.");
    }
  }
  return allSuccess;
}

// ------------------------------------------------------------------
// SALVA NOVO ATENDIMENTO
// ------------------------------------------------------------------
async function handleCreateModalSave() {

  const statusValue = document.getElementById('createStatus').value;
  const substatusValue = document.getElementById('createSubstatus').value;
  const finalStatuses = ["Concluído", "Quebra", "Concluído Parcial"];
  const isFinalizing = finalStatuses.includes(statusValue);
  const motivosForaPadrao = window.coletarMotivosSelecionados("create");



  const emptyFields = validateFields(PRODESP_CREATE_FINAL_VALIDATION_RULES);
  const ticketMissing = prodespValidateTicketNoc("create");
  const oldSubCreateSave = (
    createPersistedSubstatus || createFlowBaselineSubstatus || SUBSTATUS_INICIAL_FILA
  ).trim();
  const hostnameMissingSave = prodespValidateHostnameObrigatorio(
    "create",
    oldSubCreateSave,
    (substatusValue || "").trim(),
    statusValue
  );
  const allMissing = [...emptyFields, ...ticketMissing, ...hostnameMissingSave];

  if (allMissing.length > 0) {
    prodespNotifyValidationBlocked(allMissing, "Campos obrigatórios não preenchidos", "create");
    return;
  }

  if (currentCreateModalAtendimentoId) {
    // Este é o caminho de FINALIZAÇÃO.
    let allSuccess = true;
    const updates = [];
    const atendimentoData = getCreateModalData();
    delete atendimentoData.motivos_fora_padrao;
    const payload = {
      ...atendimentoData,
      ...prodespCollectCreateUnidadeFields(),
    };

    PRODESP_CREATE_UPDATE_FIELD_KEYS.forEach((key) => {
      if (key === "logs") {
        updates.push({ coluna: key, valor: serializeLogEntries(logsCreate) });
      } else if (payload.hasOwnProperty(key) && payload[key] !== null && payload[key] !== undefined) {
        updates.push({ coluna: key, valor: payload[key] });
      }
    });

    // ETAPA 1: Atualizar os dados principais (substatus/status antes das observações).
    if (updates.length > 0) {
      try {
        const resMain = await fetch("/prodesp/atendimentos/update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id: currentCreateModalAtendimentoId,
            updates: updates,
            motivos_fora_padrao: motivosForaPadrao,
            finalizing: true,
            ...(typeof prodespPayloadObservacoesAtomicasUpdate === "function"
              ? prodespPayloadObservacoesAtomicasUpdate()
              : {
                  transicao_observacoes:
                    typeof prodespConsumeTransicaoObservacoes === "function"
                      ? prodespConsumeTransicaoObservacoes()
                      : null,
                }),
          }),
        });
        const resultMain = await resMain.json();
        if (!resultMain.success) {
          prodespNotifySaveFailure(null, resultMain.message);
          allSuccess = false;
          prodespRevertStatusSubstatusAposFalhaUpdate("create", resMain, resultMain);
        } else {
          if (typeof prodespAplicarObservacoesTransicaoPersistidasNoUpdate === "function") {
            prodespAplicarObservacoesTransicaoPersistidasNoUpdate("create", resultMain);
          }
          createPersistedSubstatus = (
            document.getElementById("createSubstatus").value || ""
          ).trim();
        }
      } catch (err) {
        prodespNotifySaveFailure(null, prodespFriendlyFetchError(err));
        allSuccess = false;
        prodespRevertStatusSubstatusParaPersistido("create");
        prodespLogUnexpectedSaveFailure("Erro em fetch /prodesp/atendimentos/update:", null, err);
      }
    }

    // ETAPA 2: Observações — somente após substatus/status gravados com sucesso.
    if (allSuccess && newObservacaoCreate.length > 0) {
      const obsOk = await prodespSaveAtendimentoObservacoes("create", {
        toast: false,
        includeTransicaoStaging: true,
      });
      if (!obsOk) {
        allSuccess = false;
      } else {
        newObservacaoCreate.forEach((o) => delete o._transicaoStaging);
      }
    } else if (
      !allSuccess &&
      typeof prodespDescartarObservacaoTransicaoStaging === "function"
    ) {
      newObservacaoCreate
        .filter((o) => o._transicaoStaging)
        .slice()
        .forEach((o) => prodespDescartarObservacaoTransicaoStaging("create", o));
    }

    // ETAPA 3: Adicionar novos equipamentos.
    if (allSuccess && newEquipamentoCreate.length > 0) {
      try {
        const respEq = await fetch("/prodesp/equipamentos-update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id_unidade_equipamentos: selectedUnidadeId,
            new_equipamentos: newEquipamentoCreate,
            deleted_equipamentos: [],
          }),
        }).then((r) => r.json());
        if (!respEq.success) {
          prodespNotifySaveFailure("equipamentos", respEq.message);
          allSuccess = false;
        }
      } catch (err) {
        prodespNotifySaveFailure(null, prodespFriendlyFetchError(err));
        allSuccess = false;
      }
    }

    // ETAPA 4: Adicionar novos links.
    if (allSuccess && newLinksCreate.length > 0) {
      try {
        const respLnk = await fetch("/prodesp/links-update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id_unidade_links: selectedUnidadeId,
            new_links: newLinksCreate,
            deleted_links: [],
          }),
        }).then((r) => r.json());
        if (!respLnk.success) {
          prodespNotifySaveFailure("links", respLnk.message);
          allSuccess = false;
        }
      } catch (err) {
        prodespNotifySaveFailure(null, prodespFriendlyFetchError(err));
        allSuccess = false;
      }
    }

    // FINALIZAÇÃO
    if (allSuccess) {
      prodespNotifySaveSuccess("create");
    } else {
      prodespNotifySaveFailure("atendimento", "Uma ou mais etapas falharam. Verifique as mensagens acima.");
    }
  } else {
    // Este é o caminho de CRIAÇÃO inicial.
    const atendimentoCreate = getCreateModalData();
    delete atendimentoCreate.motivos_fora_padrao;
    const payload = {
      id_unidade: selectedUnidadeId,
      id_vgr: document.getElementById("createIdVgr").value.trim(),
      ...atendimentoCreate,
      ...prodespCollectCreateUnidadeFields(),
      logs: serializeLogEntries(logsCreate),
      new_observacoes: newObservacaoCreate,
      new_equipamentos: newEquipamentoCreate,
      new_links: newLinksCreate,
    };

    const idVgrCreate = document.getElementById("createIdVgr").value.trim();
    if ((payload.status || statusValue) === "Em Atendimento") {
      const subFinal = (payload.substatus || document.getElementById("createSubstatus")?.value || "").trim();
      const origemCreate =
        createPersistedSubstatus ||
        createFlowBaselineSubstatus ||
        SUBSTATUS_INICIAL_FILA;
      const msgAgGpSave = prodespValidarTransicaoSubstatusAgGp(
        origemCreate,
        subFinal,
        (payload.status || statusValue || "").trim()
      );
      if (msgAgGpSave) {
        showToast(msgAgGpSave, "warning");
        return;
      }
      const reval = await prodespRevalidarIdVgrParaCreate(idVgrCreate);
      if (!reval.proceed) {
        if (reval.redirectEdit) {
          prodespRedirecionarCreateParaEdicao(reval.atendimentoId, reval.message);
        } else {
          showToast(reval.message || "Não foi possível iniciar o atendimento.", "danger");
        }
        return;
      }
    }

    try {
      const res = await fetch("/prodesp/atendimentos/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!data.success) {
        if (prodespTratarRespostaCreateDuplicada(res, data)) return;
        throw new Error(data.message);
      }
      createPersistedSubstatus = (
        document.getElementById("createSubstatus").value || ""
      ).trim();
      showToast("Atendimento criado com sucesso: " + data.id, "success");
      editingEquipmentId = null; // Reset editing state
      editingLinkId = null;     // Reset editing state
    } catch (err) {
      console.error("Erro ao criar atendimento:", err);
      showToast("Erro ao criar atendimento: " + err.message, "danger");
    }
  }
}
window.handleCreateModalSave = handleCreateModalSave;

// ----------------------------------------------------------------------------------------
// VARIÁVEIS GLOBAIS PARA OBSERVAÇÕES EDIÇÃO
// ----------------------------------------------------------------------------------------
const newObservacao = [];
const deletedObservacaoIds = [];
const newEquipamentoEdit = [];
const deletedEquipamentoIds = [];
const newLinksEdit = [];
const deletedLinkIds = [];
let logsEdit = [];
let logsCreate = [];

const PRODESP_COLETA_FGT_INI = "--- COLETA FGT AUTO INÍCIO ---";
const PRODESP_COLETA_FGT_FIM = "--- COLETA FGT AUTO FIM ---";

function prodespIsColetaFgtText(text) {
  const t = String(text || "").trim();
  return t.includes(PRODESP_COLETA_FGT_INI);
}

function prodespMakeColetaFgtLogEntry(text) {
  return {
    timestamp: "",
    user: "",
    text: String(text || "").trim(),
    fgtAutoColeta: true,
  };
}

function prodespNormalizeColetaLogEntry(entry) {
  if (!entry || !entry.text) return entry;
  if (!prodespIsColetaFgtText(entry.text)) return entry;
  return prodespMakeColetaFgtLogEntry(entry.text);
}

function prodespStripLegacyColetaLogPrefix(text) {
  let raw = String(text || "").trim();
  if (!raw) return raw;
  raw = raw.replace(/^\[—\]\s*—:\s*/gm, "");
  return raw.trim();
}

function serializeLogEntries(entries) {
  return (entries || [])
    .map((l) => {
      if (l && l.fgtAutoColeta) {
        return prodespStripLegacyColetaLogPrefix(String(l.text || "").trim());
      }
      return `[${l.timestamp}] ${l.user}: ${l.text}`;
    })
    .filter((s) => s !== "")
    .join("\n");
}

function parseManualLogChunk(chunk) {
  const LOG_LINE_RE = /^\[(.*?)\] (.*?): (.*)$/;
  const lines = String(chunk || "").split("\n");
  const entries = [];
  let current = null;

  for (const rawLine of lines) {
    if (rawLine.trim() === "" && current) {
      current.text += "\n";
      continue;
    }

    const match = rawLine.match(LOG_LINE_RE);
    if (match) {
      current = { timestamp: match[1], user: match[2], text: match[3] };
      entries.push(current);
      continue;
    }

    if (current) {
      current.text += (current.text ? "\n" : "") + rawLine;
    } else if (rawLine.trim() !== "") {
      const stripped = prodespStripLegacyColetaLogPrefix(rawLine);
      if (prodespIsColetaFgtText(stripped)) {
        current = prodespMakeColetaFgtLogEntry(stripped);
        entries.push(current);
      } else {
        current = { timestamp: "—", user: "—", text: rawLine };
        entries.push(current);
      }
    }
  }

  return entries.map(prodespNormalizeColetaLogEntry);
}

// ---------------------------------------------------------------------------------------
// VARIÁVEIS GLOBAIS PARA OBSERVAÇÕES CRIAÇÃO
// ---------------------------------------------------------------------------------------
const newObservacaoCreate = [];
const newObservacaoUnidade = [];
const deletedObservacaoUnidadeIds = [];
const observacoesEditPersistidas = [];

// ---------------------------------------------------------------------------------------
// ELEMENTOS DO DOM PARA OBSERVAÇÕES - EDIÇÃO
// ---------------------------------------------------------------------------------------
const logContainerObservacao = document.querySelector("#log-observacao-edit");
const observacaoHeader = logContainerObservacao ? logContainerObservacao.querySelector(".titles-incident") : null;
const observacaoHeaderHtml = observacaoHeader ? observacaoHeader.outerHTML : "";

const observacaoEl = document.getElementById("editObservacaoTexto");
const btnAddObservacao = document.getElementById("btn-add-observacao-edit");
const btnSave = document.getElementById("btnSalvar");

// Evita submit nativo do formulário (botões dinâmicos de link/equipamento dentro do form)
document.getElementById("editForm")?.addEventListener("submit", (e) => e.preventDefault());
document.getElementById("createForm")?.addEventListener("submit", (e) => e.preventDefault());

// ---------------------------------------------------------------------------------------
// ELEMENTOS DO DOM PARA OBSERVAÇÕES - CRIAÇÃO 
// ---------------------------------------------------------------------------------------
const logContainerObservacaoCreate = document.querySelector("#log-observacao-create");
const observacaoCreateHeader = logContainerObservacaoCreate ? logContainerObservacaoCreate.querySelector(".titles-incident") : null;
const observacaoCreateHeaderHtml = observacaoCreateHeader ? observacaoCreateHeader.outerHTML : "";

const observacaoCreateEl = document.getElementById("createObservacaoTexto");
const btnAddObservacaoCreate = document.getElementById("btn-add-observacao-create");

/** Recarrega observações via GET /atendimentos/{id} (fonte única após persistir). */
async function prodespReloadObservacoesFromAtendimento(idAtendimento, context) {
  if (!idAtendimento) {
    return false;
  }
  try {
    const detail = await (await fetch(`/prodesp/atendimentos/${idAtendimento}`)).json();
    if (detail && Array.isArray(detail.observacoes)) {
      if (context === "edit") {
        originalData.observacoes = detail.observacoes;
      }
      reloadObservacoes(detail.observacoes, context);
      return true;
    }
  } catch (err) {
    console.warn("Falha ao recarregar observações do atendimento:", err);
  }
  return false;
}

async function prodespSaveUnidadeObservacoes() {
  if (!prodespUnidadeObservacoesAtivas()) return false;
  const pendingNew = newObservacaoUnidade.filter((o) => !o.id_observacao);
  if (!pendingNew.length && !deletedObservacaoUnidadeIds.length) return true;
  try {
    const res = await fetch("/prodesp/unidades-observacoes-update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id_unidade: +selectedUnidadeId,
        new_observacoes: pendingNew,
        deleted_observacoes: deletedObservacaoUnidadeIds,
      }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.message || "Erro ao salvar observações.");
    deletedObservacaoUnidadeIds.length = 0;
    reloadObservacoes(data.observacoes || [], "unidade");
    prodespSetCreateUnidadeObservacoesEnabled(true);
    showToast(data.message || "Observação salva.", "success");
    return true;
  } catch (err) {
    console.error("prodespSaveUnidadeObservacoes:", err);
    showToast(err.message || "Erro ao salvar observações.", "danger");
    return false;
  }
}

/**
 * Persiste observações do atendimento imediatamente (independente de saveEdit/auto-save).
 * Mesma regra da unidade agendada: «Adicionar» grava no banco na hora.
 */
async function prodespSaveAtendimentoObservacoes(context, options = {}) {
  const { toast = true, includeTransicaoStaging = false } = options;
  const isEdit = context === "edit";
  const idAtendimento = isEdit
    ? +document.getElementById("editAtendimentoId")?.value
    : +currentCreateModalAtendimentoId;
  if (!idAtendimento) {
    return false;
  }

  if (isEdit) {
    const permEdicao = prodespPodeSalvarObservacaoAtendimento(originalData);
    if (!permEdicao.ok) {
      showToast(permEdicao.msg, "warning");
      return false;
    }
  }

  const pendingNew = (isEdit ? newObservacao : newObservacaoCreate).filter(
    (o) => !o.id_observacao && (includeTransicaoStaging || !o._transicaoStaging)
  );
  const deleted = isEdit ? deletedObservacaoIds : [];
  if (!pendingNew.length && !deleted.length) {
    return true;
  }

  const pendingSnapshot = pendingNew.map((o) => {
    const clean = { ...o };
    delete clean._transicaoStaging;
    return clean;
  });
  const deletedSnapshot = [...deleted];

  try {
    const res = await fetch("/prodesp/observacoes-update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id_atendimento: idAtendimento,
        new_observacoes: pendingSnapshot,
        deleted_observacoes: deletedSnapshot,
      }),
    });
    const data = await res.json();
    if (!data.success) {
      throw new Error(data.message || "Erro ao salvar observações.");
    }

    if (isEdit) {
      newObservacao.length = 0;
      deletedObservacaoIds.length = 0;
    } else {
      const stagingOnly = newObservacaoCreate.filter(
        (o) => o._stagingPreviousAtendimento && !o.id_observacao
      );
      newObservacaoCreate.length = 0;
      newObservacaoCreate.push(...stagingOnly);
    }

    if (Array.isArray(data.observacoes)) {
      if (isEdit) {
        originalData.observacoes = data.observacoes;
      }
      reloadObservacoes(data.observacoes, isEdit ? "edit" : "create");
    } else {
      await prodespReloadObservacoesFromAtendimento(
        idAtendimento,
        isEdit ? "edit" : "create"
      );
    }

    if (toast) {
      showToast(data.message || "Observação salva.", "success");
    }
    return true;
  } catch (err) {
    console.error("prodespSaveAtendimentoObservacoes:", err);
    if (isEdit) {
      pendingSnapshot.forEach((o) => {
        if (
          !newObservacao.some(
            (x) =>
              x.data_observacao === o.data_observacao &&
              x.observacao_prodesp === o.observacao_prodesp
          )
        ) {
          newObservacao.push(o);
        }
      });
    } else {
      pendingSnapshot.forEach((o) => {
        if (
          !newObservacaoCreate.some(
            (x) =>
              x.data_observacao === o.data_observacao &&
              x.observacao_prodesp === o.observacao_prodesp
          )
        ) {
          newObservacaoCreate.push(o);
        }
      });
    }
    showToast(err.message || "Erro ao salvar observações.", "danger");
    return false;
  }
}

// --------------------------------------------------------------------------------
// FUNÇÕES DE OBSERVAÇÕES
// --------------------------------------------------------------------------------
// Função genérica para renderizar um card de observação
// Recebe o objeto da observação, o container onde ela será adicionada
// e a lista de observações à qual ela pertence (para remoção)
function renderObservacaoCard(
  observacaoObj,
  containerEl,
  targetArray,
  deletedArray = null
) {
  if (!containerEl) {
    console.error("Container de log não encontrado para renderizar card.", containerEl);
    return;
  }

  const card = document.createElement("div");
  card.classList.add("card-incident");
  const fields = document.createElement("div");
  fields.classList.add("fields");

  const makeDiv = (cls, txt) => {
    const d = document.createElement("div");
    d.classList.add(cls);
    d.style.whiteSpace = "pre-wrap"; // Preserva quebras de linha e espaços
    d.textContent = txt || "—";
    return d;
  };

  fields.appendChild(makeDiv("incident-data", observacaoObj.data_observacao));
  fields.appendChild(makeDiv("incident-chamado", observacaoObj.observacao_prodesp));

  const delButton = document.createElement("button");
  delButton.textContent = "🗑️";
  delButton.type = "button";
  delButton.classList.add("btn", "btn-sm", "btn-outline-danger", "ms-2"); // Adicionei algumas classes Bootstrap para melhor visual

  delButton.addEventListener("click", async () => {
    card.remove(); // Remove o card visualmente do DOM

    // Lógica para remover do array correto
    if (observacaoObj.id_observacao && deletedArray) {
      // Se tem ID do banco e há array de deletados (edição)
      deletedArray.push(observacaoObj.id_observacao);
    }

    const idx = targetArray.indexOf(observacaoObj);
    if (idx > -1) {
      targetArray.splice(idx, 1); // Remove do array de origem
    }

    if (
      prodespUnidadeObservacoesAtivas() &&
      containerEl &&
      String(containerEl.id || "").includes("create")
    ) {
      await prodespSaveUnidadeObservacoes();
      return;
    }

    const obsMode =
      containerEl && String(containerEl.id || "").includes("create") ? "create" : "edit";
    if (obsMode === "edit" || currentCreateModalAtendimentoId) {
      await prodespSaveAtendimentoObservacoes(obsMode);
    }
  });

  // Bloqueio se for modal de criação e atendimento não iniciado (sem unidade carregada)
  if (
    containerEl &&
    containerEl.id.includes("create") &&
    !currentCreateModalAtendimentoId &&
    !prodespUnidadeObservacoesAtivas()
  ) {
    delButton.disabled = true;
  }

  card.appendChild(fields);
  card.appendChild(delButton);
  containerEl.appendChild(card);

  if (
    prodespUnidadeObservacoesAtivas() &&
    containerEl &&
    String(containerEl.id || "").includes("create")
  ) {
    delButton.disabled = false;
  }
}

// --- Lógica de Adição de Observações ---

// Adicionar Observação - MODAL DE EDIÇÃO
if (btnAddObservacao) {
  // Verifica se o botão existe antes de adicionar o listener
  btnAddObservacao.addEventListener("click", () => {
    const agora = new Date();
    const fmt2 = (n) => String(n).padStart(2, "0");
    const dataHora = fmt2(agora.getDate()) + "/" + fmt2(agora.getMonth() + 1) + "/" + agora.getFullYear() + " " + fmt2(agora.getHours()) + ":" + fmt2(agora.getMinutes()) + ":" + fmt2(agora.getSeconds());
    const observacaoText = observacaoEl ? observacaoEl.value.trim() : ""; // Pega o valor do input de edição

    if (!observacaoText) {
      return showToast(
        "Preencha o campo de observação do modal de edição.",
        "warning"
      );
    }

    const observacaoObj = {
      data_observacao: dataHora,
      observacao_prodesp: observacaoText,
    };

    // Impede duplicação exata
    if (
      newObservacao.some(
        (x) =>
          x.data_observacao === observacaoObj.data_observacao &&
          x.observacao_prodesp === observacaoObj.observacao_prodesp
      )
    ) {
      return showToast(
        "Esta observação já foi adicionada na edição.",
        "warning"
      );
    }

    newObservacao.push(observacaoObj);
    prodespRefreshObservacaoCards(
      logContainerObservacao,
      observacaoHeaderHtml,
      newObservacao,
      deletedObservacaoIds
    );
    if (observacaoEl) observacaoEl.value = "";
    prodespSaveAtendimentoObservacoes("edit");
  });
} else {
  console.warn("Botão 'btn-add-observacao-edit' não encontrado. Verifique seu HTML.");
}

// Adicionar Observação - MODAL DE CRIAÇÃO
if (btnAddObservacaoCreate) {
  btnAddObservacaoCreate.addEventListener("click", async () => {
    const agora = new Date();
    const fmt2 = (n) => String(n).padStart(2, "0");
    const dataHora = fmt2(agora.getDate()) + "/" + fmt2(agora.getMonth() + 1) + "/" + agora.getFullYear() + " " + fmt2(agora.getHours()) + ":" + fmt2(agora.getMinutes()) + ":" + fmt2(agora.getSeconds());
    const observacaoText = observacaoCreateEl ? observacaoCreateEl.value.trim() : "";
    if (!observacaoText) {
      return showToast("Preencha o campo de observação.", "warning");
    }

    const observacaoObj = {
      data_observacao: dataHora,
      observacao_prodesp: observacaoText,
    };

    if (prodespUnidadeObservacoesAtivas()) {
      if (
        newObservacaoUnidade.some(
          (x) =>
            x.data_observacao === observacaoObj.data_observacao &&
            x.observacao_prodesp === observacaoObj.observacao_prodesp
        )
      ) {
        return showToast("Esta observação já foi adicionada.", "warning");
      }
      newObservacaoUnidade.push(observacaoObj);
      prodespRefreshObservacaoCards(
        logContainerObservacaoCreate,
        observacaoCreateHeaderHtml,
        newObservacaoUnidade,
        deletedObservacaoUnidadeIds
      );
      if (observacaoCreateEl) observacaoCreateEl.value = "";
      await prodespSaveUnidadeObservacoes();
      return;
    }

    if (
      newObservacaoCreate.some(
        (x) =>
          x.data_observacao === observacaoObj.data_observacao &&
          x.observacao_prodesp === observacaoObj.observacao_prodesp
      )
    ) {
      return showToast("Esta observação já foi adicionada na criação.", "warning");
    }

    newObservacaoCreate.push(observacaoObj);
    prodespRefreshObservacaoCards(
      logContainerObservacaoCreate,
      observacaoCreateHeaderHtml,
      newObservacaoCreate,
      null
    );
    if (observacaoCreateEl) observacaoCreateEl.value = "";
    await prodespSaveAtendimentoObservacoes("create");
  });
} else {
  console.warn(
    "Botão 'btn-add-observacao-create' não encontrado. Verifique seu HTML."
  );
}

// --- Funções de Limpeza e Recarregamento (Foco na Edição) ---

// Limpa observações QUANDO FECHA O MODAL DE EDIÇÃO
const modalEl = document.getElementById("editModal");
if (modalEl) {
  modalEl.addEventListener("hide.bs.modal", () => {
    // Redefine o conteúdo do container de observações para o cabeçalho inicial
    if (logContainerObservacao) {
      logContainerObservacao.innerHTML = observacaoHeaderHtml;
    }
    newObservacao.length = 0;
    deletedObservacaoIds.length = 0;
    // if (btnSave) btnSave.disabled = true; // Desabilita ao fechar 
    if (observacaoEl) observacaoEl.value = ""; // Limpa o input de observação
    const editMotivoAc = document.getElementById("editAguardandoClienteMotivo");
    if (editMotivoAc) editMotivoAc.value = "";

    // Limpa a busca URL com o INEP do atendimento que foi redirecionado 
    // This logic seems specific to FUST project, not Prodesp.
    // It also reloads the page, which might not be desired if only clearing URL params.
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has("search_id_vgr")) {
      urlParams.delete("search_id_vgr");
      const newUrl = `${window.location.pathname}?${urlParams.toString()}`;
      window.history.replaceState({}, document.title, newUrl);
      const dt = $("#tabela-atendimentos").DataTable();
      if (dt) {
        dt.column(0).search("", false, false);
        dt.ajax.reload(null, false);
      }
    }

    if (logConfiguracaoRemotaEdit) {
        const header = logConfiguracaoRemotaEdit.querySelector(".titles-incident");
        if (header) {
            logConfiguracaoRemotaEdit.innerHTML = header.outerHTML;
        }
    }
  });
}

// --- Lógica para o Modal de Criação (Limpeza) ---

// Limpa observações QUANDO FECHA O MODAL DE CRIAÇÃO
const createModalEl = document.getElementById("createModal");
if (createModalEl) {
  createModalEl.addEventListener("hide.bs.modal", () => {
    if (logContainerObservacaoCreate) {
      logContainerObservacaoCreate.innerHTML = observacaoCreateHeaderHtml ||
        '<div class="titles-incident"><span>DATA</span><span>OBSERVAÇÕES</span><span></span></div>'; // Fallback header
    }
    newObservacaoCreate.length = 0;
    newObservacaoUnidade.length = 0;
    deletedObservacaoUnidadeIds.length = 0;
    prodespSetCreateUnidadeObservacoesEnabled(false);
    if (observacaoCreateEl) observacaoCreateEl.value = "";
    const createMotivoAcHide = document.getElementById("createAguardandoClienteMotivo");
    if (createMotivoAcHide) createMotivoAcHide.value = "";

    // Reset other create modal specific things
    currentCreateModalAtendimentoId = null;
  window.currentCreateModalAtendimentoId = null;
    createPersistedSubstatus = "";
    setCreateModalFieldsDisabled(false); // Re-enable all fields
    if (createForm) createForm.reset();
    clearCreateUnidadeFields();
    if (logContainerEquipamentoCreate) {
      prodespResetIncidentListContainer(logContainerEquipamentoCreate);
    }
    newEquipamentoCreate.length = 0;
    if (logContainerLinkCreate) {
      prodespResetIncidentListContainer(logContainerLinkCreate);
    }
    newLinksCreate.length = 0;

    // Reset editing states for create modal
    editingEquipmentId = null;
    editingLinkId = null;
    toggleEditButtons('create', false);
    if (logConfiguracaoRemotaCreate) {
      const header = logConfiguracaoRemotaCreate.querySelector(".titles-incident");
      if (header) {
          logConfiguracaoRemotaCreate.innerHTML = header.outerHTML;
      }
    }
    if (btnCreateIncident) btnCreateIncident.textContent = "Criar";
  });
}

// ------------------------------
// VARIÁVEIS GLOBAIS PARA EQUIPAMENTOS EDIÇÃO
// ------------------------------
// ------------------------------
// VARIÁVEIS GLOBAIS PARA EQUIPAMENTOS CRIAÇÃO
// ------------------------------
const newEquipamentoCreate = [];
const newLinksCreate = [];
const existingEquipmentsCreate = []; // Para armazenar equipamentos de atendimentos anteriores para validação de duplicatas

// ------------------------------
// ELEMENTOS DO DOM PARA EQUIPAMENTOS - EDIÇÃO
// ------------------------------
const logContainerEquipamentoEdit = document.querySelector("#log-equipamento-edit");
const logContainerLinkEdit = document.querySelector("#log-link-edit");

const equipamentoModeloEditEl = document.getElementById("editEquipamentoModelo");
const equipamentoSerialEditEl = document.getElementById("editEquipamentoSerial");
const equipamentoVersaoEditEl = document.getElementById("editEquipamentoVersao");
const equipamentoMacEditEl = document.getElementById("editEquipamentoMac"); // Assuming MAC field exists
const equipamentoIotEditEl = document.getElementById("editEquipamentoIot"); // Assuming IoT field exists
const equipamentoDescricaoEditEl = document.getElementById("editEquipamentoDescricao");
// Removed btnAddEquipamentoEdit as it's now dynamically controlled
const btnAddLinkEdit = document.getElementById("btn-add-link-edit");

// -----------------------------------------------------------------------------------
// ELEMENTOS DO DOM PARA EQUIPAMENTOS - CRIAÇÃO
// -----------------------------------------------------------------------------------
const logContainerEquipamentoCreate = document.querySelector("#log-equipamento-create");
const logContainerLinkCreate = document.querySelector("#log-link-create");
const equipamentoModeloCreateEl = document.getElementById("createEquipamentoModelo");
const equipamentoSerialCreateEl = document.getElementById("createEquipamentoSerial");
const equipamentoVersaoCreateEl = document.getElementById("createEquipamentoVersao");
const equipamentoDescricaoCreateEl = document.getElementById("createEquipamentoDescricao");
const btnAddEquipamentoCreate = document.getElementById("btn-add-equipamento-create");

// --------------------------------------------------------------------------------
// FUNÇÕES AUXILIARES PARA EQUIPAMENTOS
// --------------------------------------------------------------------------------

// Helper function to manage equipment button visibility
function toggleEditButtons(context, isEditing) {
    const addBtn = document.getElementById(`btn-add-equipamento-${context}`);
    const confirmBtn = document.getElementById(`btn-confirm-equipamento-${context}`);
    const cancelBtn = document.getElementById(`btn-cancel-equipamento-${context}`);

    if (addBtn) addBtn.classList.toggle('d-none', isEditing);
    if (confirmBtn) confirmBtn.classList.toggle('d-none', !isEditing);
    if (cancelBtn) cancelBtn.classList.toggle('d-none', !isEditing);

    // Desabilita/Habilita o botão de adicionar link. 
    // No contexto de criação, só habilita se o atendimento já foi iniciado.
    const addLinkBtn = document.getElementById(`btn-add-link-${context}`);
    if (addLinkBtn) {
        addLinkBtn.disabled = isEditing || (context === 'create' && !currentCreateModalAtendimentoId);
    }
}

// Helper function to manage link button visibility
function toggleEditLinkButtons(context, isEditing) {
    const addBtn = document.getElementById(`btn-add-link-${context}`);
    const confirmBtn = document.getElementById(`btn-confirm-link-${context}`);
    const cancelBtn = document.getElementById(`btn-cancel-link-${context}`);

    if (addBtn) addBtn.classList.toggle('d-none', isEditing);
    if (confirmBtn) confirmBtn.classList.toggle('d-none', !isEditing);
    if (cancelBtn) cancelBtn.classList.toggle('d-none', !isEditing);

    // Desabilita/Habilita o botão de adicionar equipamento.
    // No contexto de criação, só habilita se o atendimento já foi iniciado.
    const addEquipBtn = document.getElementById(`btn-add-equipamento-${context}`);
    if (addEquipBtn) {
        addEquipBtn.disabled = isEditing || (context === 'create' && !currentCreateModalAtendimentoId);
    }
}

// Function to clear equipment form fields
function clearEquipmentForm(context) {
    const getEl = (id) => document.getElementById(`${context}${id}`);
    getEl('EquipamentoModelo').value = "";
    getEl('EquipamentoDescricao').value = "";
    getEl('EquipamentoVersao').value = PRODESP_DEFAULT_FORTIOS_VERSION;
    // Assuming these exist based on context
    const macEl = getEl('EquipamentoMac');
    if (macEl) macEl.value = "";
    const iotEl = getEl('EquipamentoIot');
    if (iotEl) iotEl.checked = false;

    if (maskInstances[`${context}EquipamentoSerial`]) maskInstances[`${context}EquipamentoSerial`].value = ''; else getEl('EquipamentoSerial').value = '';
    // Hide numero field if it was visible
    const numeroWrapper = document.getElementById(`${context}EquipamentoNumeroWrapper`);
    if (numeroWrapper) numeroWrapper.classList.add('d-none');
    const numeroEl = getEl('EquipamentoNumero');
    if (numeroEl) numeroEl.value = '';
}

// Function to clear link form fields
function clearLinkForm(context) {
    const getEl = (id) => document.getElementById(`${context}Link${id}`);
    const fields = ['Designador', 'Tipo', 'Operadora', 'Vlan', 'IpWan', 'IpGateway', 'IpMascara', 'Velocidade', 'PppoeUser', 'PppoePass', 'IdVgr'];
    fields.forEach(f => { const el = getEl(f); if (el) el.value = ""; });
    const redundanteEl = document.getElementById(`${context}LinkRedundanteCritico`);
    if (redundanteEl) redundanteEl.checked = false;
    const typeSelect = getEl('Tipo');
    if (typeSelect) typeSelect.dispatchEvent(new Event('change')); // Trigger change to hide/show conditional fields
}

function cancelEditEquipment(context) {
    editingEquipmentId = null;
    toggleEditButtons(context, false);
    clearEquipmentForm(context);
}

function cancelEditLink(context) {
    editingLinkId = null;
    toggleEditLinkButtons(context, false);
    clearLinkForm(context);
}

// --------------------------------------------------------------------------------
// LISTAS ACCORDION — equipamentos e links (modais create/edit)
// --------------------------------------------------------------------------------

let prodespIncidentItemSeq = 0;

function prodespNextIncidentItemId(prefix) {
  prodespIncidentItemSeq += 1;
  return `${prefix}-${Date.now()}-${prodespIncidentItemSeq}`;
}

function prodespEnsureIncidentAccordionList(containerEl) {
  if (!containerEl) return null;
  let acc = containerEl.querySelector(":scope > .prodesp-incident-accordion");
  if (!acc) {
    containerEl.innerHTML = "";
    acc = document.createElement("div");
    acc.className = "prodesp-incident-accordion accordion accordion-flush";
    if (containerEl.id) acc.id = `${containerEl.id}-accordion`;
    containerEl.appendChild(acc);
  }
  return acc;
}

function prodespResetIncidentListContainer(containerEl) {
  if (!containerEl) return null;
  containerEl.innerHTML = "";
  return prodespEnsureIncidentAccordionList(containerEl);
}

[logContainerEquipamentoEdit, logContainerLinkEdit, logContainerEquipamentoCreate, logContainerLinkCreate]
  .forEach((el) => prodespResetIncidentListContainer(el));

function prodespIncidentSummaryText(parts) {
  return parts.filter((p) => p && String(p).trim()).join(" · ") || "—";
}

/** Linha resumo do accordion de links (create/edit/view). */
function prodespLinkAccordionSummary(linkObj) {
  const head = prodespIncidentSummaryText([linkObj.tipo, linkObj.designador, linkObj.operadora]);
  const extras = [];
  const push = (label, val) => {
    const v = val != null ? String(val).trim() : "";
    if (v) extras.push(`${label}: ${v}`);
  };
  push("VGR", linkObj.id_vgr);
  push("WAN", linkObj.ip_wan);
  if (linkObj.redundante_critico) extras.push("Redund. Crítico");
  push("GW", linkObj.ip_gateway);
  push("Másc", linkObj.ip_mascara);
  push("Vel", linkObj.velocidade);
  return extras.length ? `${head} · ${extras.join(" · ")}` : head;
}

function prodespNormalizeEquipamentoForDisplay(eq) {
  return {
    modelo: eq?.modelo,
    serial: eq?.serial,
    versao: prodespFortiosVersionOrDefault(eq?.versao),
    descricao: eq?.descricao,
  };
}

function prodespNormalizeLinkForDisplay(lnk) {
  const redundanteRaw =
    lnk?.redundante_critico ?? lnk?.redundante_critico_links ?? false;
  return {
    id_vgr: lnk?.id_vgr ?? lnk?.id_vgr_links,
    tipo: lnk?.tipo ?? lnk?.tipo_links,
    designador: lnk?.designador ?? lnk?.designador_links,
    operadora: lnk?.operadora ?? lnk?.operadora_links,
    vlan: lnk?.vlan ?? lnk?.vlan_links,
    velocidade: lnk?.velocidade ?? lnk?.velocidade_links,
    ip_wan: lnk?.ip_wan ?? lnk?.ip_wan_links,
    redundante_critico:
      redundanteRaw === true ||
      redundanteRaw === 1 ||
      String(redundanteRaw).trim() === "1",
    ip_gateway: lnk?.ip_gateway ?? lnk?.ip_gateway_links,
    ip_mascara: lnk?.ip_mascara ?? lnk?.ip_mascara_links,
    pppoe_user: lnk?.pppoe_user ?? lnk?.pppoe_user_links,
    pppoe_pass: lnk?.pppoe_pass ?? lnk?.pppoe_pass_links,
  };
}

function prodespRenderEquipamentoViewAccordion(equipamentoObj, containerEl) {
  if (!containerEl) return;
  const eq = prodespNormalizeEquipamentoForDisplay(equipamentoObj);
  const accordion = prodespEnsureIncidentAccordionList(containerEl);
  if (!accordion) return;

  const summary = prodespIncidentSummaryText([eq.modelo, eq.serial, eq.versao]);
  const shell = prodespBuildIncidentAccordionItem(summary, accordion.id);
  const { item, grid } = shell;

  if (eq.serial && String(eq.serial).includes("Erro")) {
    item.classList.add("text-danger", "bg-danger-subtle");
    item.title = "Falha na coleta deste equipamento via SSH. Verifique a conectividade.";
  }

  grid.appendChild(prodespCreateIncidentReadonlyCol("Modelo", eq.modelo));
  const serialCol = prodespCreateIncidentReadonlyCol("Serial", eq.serial);
  if (eq.serial && eq.serial !== "—") {
    const icon = document.createElement("i");
    icon.className = "far fa-copy btn-copy-inline ms-2 text-muted";
    icon.title = "Copiar Serial";
    icon.style.cursor = "pointer";
    icon.onclick = (e) => {
      e.stopPropagation();
      navigator.clipboard.writeText(String(eq.serial)).then(() => showToast(`'${eq.serial}' copiado!`, "success"));
    };
    serialCol.querySelector(".prodesp-incident-readonly")?.appendChild(icon);
  }
  grid.appendChild(serialCol);
  grid.appendChild(prodespCreateIncidentReadonlyCol("Versão", eq.versao));
  grid.appendChild(prodespCreateIncidentReadonlyCol("Descrição", eq.descricao));

  accordion.appendChild(item);
}

function prodespRenderLinkViewAccordion(linkObj, containerEl) {
  if (!containerEl) return;
  const lnk = prodespNormalizeLinkForDisplay(linkObj);
  const accordion = prodespEnsureIncidentAccordionList(containerEl);
  if (!accordion) return;

  const shell = prodespBuildIncidentAccordionItem(prodespLinkAccordionSummary(lnk), accordion.id);
  const { item, grid } = shell;

  [
    ["ID VGR", lnk.id_vgr],
    ["Tipo", lnk.tipo],
    ["Designador", lnk.designador],
    ["Operadora", lnk.operadora],
    ["VLAN", lnk.vlan],
    ["Velocidade", lnk.velocidade],
    ["IP WAN", lnk.ip_wan],
    ["Redundante Crítico", lnk.redundante_critico ? "Sim" : "Não"],
    ["Gateway", lnk.ip_gateway],
    ["Máscara", lnk.ip_mascara],
    ["PPPoE User", lnk.pppoe_user],
    ["PPPoE Pass", lnk.pppoe_pass],
  ].forEach(([label, val]) => grid.appendChild(prodespCreateIncidentReadonlyCol(label, val)));

  accordion.appendChild(item);
}

function prodespPopulateEquipamentosViewList(containerEl, equipamentos, emptyMessage) {
  if (!containerEl) return;
  containerEl.innerHTML = "";
  if (!equipamentos || equipamentos.length === 0) {
    containerEl.innerHTML = `<div class="text-muted p-2">${emptyMessage || "Nenhum equipamento."}</div>`;
    return;
  }
  equipamentos.forEach((eq) => prodespRenderEquipamentoViewAccordion(eq, containerEl));
}

function prodespPopulateLinksViewList(containerEl, links, emptyMessage) {
  if (!containerEl) return;
  containerEl.innerHTML = "";
  if (!links || links.length === 0) {
    containerEl.innerHTML = `<div class="text-muted p-2">${emptyMessage || "Nenhum link."}</div>`;
    return;
  }
  links.forEach((lnk) => prodespRenderLinkViewAccordion(lnk, containerEl));
}

function prodespCreateIncidentActionsGroup(buttons) {
  const group = document.createElement("div");
  group.className = "prodesp-incident-actions btn-group btn-group-sm flex-shrink-0";
  buttons.forEach((b) => group.appendChild(b));
  return group;
}

function prodespCreateIncidentToggleBtn(collapseId, summary, expanded) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = `accordion-button py-2${expanded ? "" : " collapsed"}`;
  btn.setAttribute("data-bs-toggle", "collapse");
  btn.setAttribute("data-bs-target", `#${collapseId}`);
  btn.setAttribute("aria-expanded", expanded ? "true" : "false");
  btn.setAttribute("aria-controls", collapseId);
  btn.textContent = summary;
  return btn;
}

function prodespCreateIncidentFieldCol(label, control, colClass) {
  const col = document.createElement("div");
  col.className = colClass || "col-md-4 col-sm-6";
  const lbl = document.createElement("label");
  lbl.className = "form-label form-label-sm mb-0 text-muted small";
  lbl.textContent = label;
  col.append(lbl, control);
  return col;
}

function prodespCreateIncidentReadonlyCol(label, text) {
  const val = document.createElement("div");
  val.className = "form-control form-control-sm bg-light prodesp-incident-readonly text-break";
  val.textContent = text || "—";
  return prodespCreateIncidentFieldCol(label, val);
}

function prodespBuildIncidentAccordionItem(summary, accordionParentId) {
  const itemId = prodespNextIncidentItemId("inc");
  const collapseId = `${itemId}-pane`;
  const item = document.createElement("div");
  item.className = "accordion-item prodesp-incident-accordion-item border-0 border-bottom";

  const header = document.createElement("h2");
  header.className = "accordion-header m-0";

  const headerRow = document.createElement("div");
  headerRow.className = "prodesp-incident-accordion-header d-flex align-items-stretch w-100";

  const toggleBtn = prodespCreateIncidentToggleBtn(collapseId, summary, false);
  const actionsSlot = document.createElement("div");
  actionsSlot.className = "prodesp-incident-actions-slot d-flex align-items-center pe-2";

  headerRow.append(toggleBtn, actionsSlot);
  header.appendChild(headerRow);

  const collapse = document.createElement("div");
  collapse.id = collapseId;
  collapse.className = "accordion-collapse collapse";
  if (accordionParentId) {
    collapse.setAttribute("data-bs-parent", `#${accordionParentId}`);
  }
  const body = document.createElement("div");
  body.className = "accordion-body py-2 px-3";
  const grid = document.createElement("div");
  grid.className = "row g-2 prodesp-incident-fields-grid";
  body.appendChild(grid);
  collapse.appendChild(body);

  item.append(header, collapse);
  return { item, grid, actionsSlot, collapse, toggleBtn };
}

// --------------------------------------------------------------------------------
// FUNÇÕES DE EQUIPAMENTOS
// --------------------------------------------------------------------------------

// Função genérica para renderizar um equipamento (accordion — modais create/edit)
function renderEquipamentoCard(equipamentoObj, containerEl, targetArray, deletedArray = null, context = 'edit') {
  if (!containerEl) {
    console.error("Container de log de equipamentos não encontrado para renderizar card.", containerEl);
    return;
  }

  const accordion = prodespEnsureIncidentAccordionList(containerEl);
  if (!accordion) return;

  const summary = prodespIncidentSummaryText([
    equipamentoObj.modelo,
    equipamentoObj.serial,
    prodespFortiosVersionOrDefault(equipamentoObj.versao),
  ]);
  const shell = prodespBuildIncidentAccordionItem(summary, accordion.id);
  const { item, grid, actionsSlot, collapse } = shell;

  if (equipamentoObj.serial && equipamentoObj.serial.includes("Erro")) {
    item.classList.add("text-danger", "bg-danger-subtle");
    item.title = "Falha na coleta deste equipamento via SSH. Verifique a conectividade.";
  }

  const showCollapse = (open) => {
    const inst = bootstrap.Collapse.getOrCreateInstance(collapse, { toggle: false });
    if (open) inst.show();
    else inst.hide();
  };

  const renderViewMode = () => {
    showCollapse(false);
    item.classList.remove("prodesp-incident-item-editing");
    shell.toggleBtn.textContent = prodespIncidentSummaryText([
      equipamentoObj.modelo,
      equipamentoObj.serial,
      prodespFortiosVersionOrDefault(equipamentoObj.versao),
    ]);
    grid.innerHTML = "";
    grid.appendChild(prodespCreateIncidentReadonlyCol("Modelo", equipamentoObj.modelo));
    const serialCol = prodespCreateIncidentReadonlyCol("Serial", equipamentoObj.serial);
    if (equipamentoObj.serial && equipamentoObj.serial !== "—") {
      const icon = document.createElement("i");
      icon.className = "far fa-copy btn-copy-inline ms-2 text-muted";
      icon.title = "Copiar Serial";
      icon.style.cursor = "pointer";
      icon.onclick = (e) => {
        e.stopPropagation();
        navigator.clipboard.writeText(equipamentoObj.serial).then(() => showToast(`'${equipamentoObj.serial}' copiado!`, "success"));
      };
      serialCol.querySelector(".prodesp-incident-readonly")?.appendChild(icon);
    }
    grid.appendChild(serialCol);
    grid.appendChild(prodespCreateIncidentReadonlyCol("Versão", prodespFortiosVersionOrDefault(equipamentoObj.versao)));
    grid.appendChild(prodespCreateIncidentReadonlyCol("Descrição", equipamentoObj.descricao));

    const editButton = document.createElement("button");
    editButton.innerHTML = '<i class="fas fa-pencil-alt"></i>';
    editButton.type = "button";
    editButton.className = "btn btn-sm btn-outline-primary";
    editButton.title = "Editar Equipamento";
    editButton.onclick = (e) => { e.stopPropagation(); renderEditMode(); };

    const delButton = document.createElement("button");
    delButton.innerHTML = '<i class="fas fa-trash"></i>';
    delButton.type = "button";
    delButton.className = "btn btn-sm btn-outline-danger";
    delButton.title = "Excluir Equipamento";
    delButton.onclick = (e) => { e.stopPropagation(); deleteEquipment(); };

    if (context === "create" && !currentCreateModalAtendimentoId) {
      editButton.disabled = delButton.disabled = true;
    }
    actionsSlot.innerHTML = "";
    actionsSlot.appendChild(prodespCreateIncidentActionsGroup([editButton, delButton]));
  };

  const renderEditMode = () => {
    showCollapse(true);
    item.classList.add("prodesp-incident-item-editing");
    shell.toggleBtn.textContent = "Editando equipamento…";
    grid.innerHTML = "";

    const sel = document.createElement("select");
    sel.className = "form-select form-select-sm";
    ["FortiGate 40F", "FortiGate 60F", "FortiGate 120G", "FortiGate 900G", "FortiGate 3200F", "FortiGate 3700F", "FortiGate 600F", "FortiSwitch 2048F"].forEach((opt) => sel.add(new Option(opt, opt)));
    sel.value = equipamentoObj.modelo || "";

    const serialInp = document.createElement("input");
    serialInp.className = "form-control form-control-sm";
    serialInp.value = equipamentoObj.serial || "";
    IMask(serialInp, { mask: /^[a-zA-Z0-9\-]*$/, prepare: (str) => str.toUpperCase() });

    const versaoInp = document.createElement("input");
    versaoInp.className = "form-control form-control-sm";
    versaoInp.value = prodespFortiosVersionOrDefault(equipamentoObj.versao);

    const descInp = document.createElement("input");
    descInp.className = "form-control form-control-sm";
    descInp.readOnly = true;
    descInp.value = equipamentoObj.descricao || "";

    sel.onchange = () => {
      const val = sel.value;
      const autoDescModels = ["FortiGate 40F", "FortiGate 60F", "FortiGate 120G", "FortiGate 900G", "FortiGate 3200F", "FortiGate 3700F", "FortiGate 600F"];
      descInp.value = autoDescModels.includes(val) ? "Firewall - Stand Alone" : (val === "FortiSwitch 2048F" ? "Switch" : "");
    };

    grid.append(
      prodespCreateIncidentFieldCol("Modelo", sel, "col-md-6"),
      prodespCreateIncidentFieldCol("Serial", serialInp, "col-md-6"),
      prodespCreateIncidentFieldCol("Versão", versaoInp, "col-md-6"),
      prodespCreateIncidentFieldCol("Descrição", descInp, "col-md-6")
    );

    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.innerHTML = '<i class="fas fa-check me-1"></i>Salvar';
    saveBtn.className = "btn btn-sm btn-success";
    saveBtn.title = "Salvar edição do equipamento";
    saveBtn.onclick = async (e) => {
      e.stopPropagation();
      let modelo = sel.value;
      const serial = serialInp.value.trim().toUpperCase();
      if (!modelo && serial) {
        modelo = prodespInferModeloEquipamentoFromSerial(serial);
        if (modelo) prodespSetEquipamentoModeloSelect(sel, modelo);
      }
      if (!modelo || !serial) return showToast("Modelo e Serial são obrigatórios.", "warning");

      const attendanceId = context === "edit" ? +document.getElementById("editAtendimentoId").value : currentCreateModalAtendimentoId;
      const unitId = context === "edit" ? originalData.id_unidades_atendimentos : selectedUnidadeId;

      try {
        const res = await fetch("/prodesp/equipamentos-update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id_atendimento: attendanceId,
            id_unidade_equipamentos: unitId,
            new_equipamentos: [{ id: equipamentoObj.id_equipamento, modelo, serial, versao: prodespFortiosVersionOrDefault(versaoInp.value), descricao: descInp.value }],
            deleted_equipamentos: [],
          }),
        });
        const r = await res.json();
        if (r.success) {
          showToast("Equipamento atualizado!", "success");
          await prodespApplyEquipamentosApiResult(r, context, attendanceId);
        } else showToast(r.message, "danger");
      } catch (_e) { showToast("Erro ao salvar.", "danger"); }
    };

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.innerHTML = '<i class="fas fa-times me-1"></i>Cancelar';
    cancelBtn.className = "btn btn-sm btn-secondary";
    cancelBtn.title = "Cancelar edição do equipamento";
    cancelBtn.onclick = (e) => { e.stopPropagation(); renderViewMode(); };

    actionsSlot.innerHTML = "";
    actionsSlot.appendChild(prodespCreateIncidentActionsGroup([saveBtn, cancelBtn]));
  };

  const deleteEquipment = async () => {
    if (equipamentoObj.id_equipamento) {
      const attendanceId = context === "edit" ? +document.getElementById("editAtendimentoId").value : currentCreateModalAtendimentoId;
      const unitId = context === "edit" ? originalData.id_unidades_atendimentos : selectedUnidadeId;

      try {
        const res = await fetch("/prodesp/equipamentos-update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id_atendimento: attendanceId,
            id_unidade_equipamentos: unitId,
            new_equipamentos: [],
            deleted_equipamentos: [equipamentoObj.id_equipamento],
          }),
        });
        const result = await res.json();
        if (result.success) {
          showToast("Equipamento removido do banco.", "success");
          await prodespApplyEquipamentosApiResult(result, context, attendanceId);
        } else {
          showToast(result.message, "danger");
        }
      } catch (_e) { showToast("Erro ao excluir equipamento.", "danger"); }
    } else {
      item.remove();
      const idx = targetArray.findIndex((eq) => eq.serial === equipamentoObj.serial);
      if (idx > -1) targetArray.splice(idx, 1);
    }
  };

  accordion.appendChild(item);
  renderViewMode();
}

/**
 * Lógica unificada para adicionar um equipamento nos modais de criação ou edição.
 * @param {('create'|'edit')} context - O contexto do modal (criação ou edição).
 */
async function addEquipmentLogic(context) {
  // Mapeia os elementos do DOM com base no contexto
  const getEl = (id) => document.getElementById(`${context}${id}`);
  const elements = {
    modelo: getEl('EquipamentoModelo'),
    serial: getEl('EquipamentoSerial'),
    versao: getEl('EquipamentoVersao'),
    descricao: getEl('EquipamentoDescricao'),
    logContainer: document.getElementById(`log-equipamento-${context}`),
  };

  if (!elements.modelo || !elements.serial) {
    return showToast("Campos de equipamento não encontrados. Recarregue a página (Ctrl+F5).", "danger");
  }

  // Obtém os valores dos campos, aplicando formatação
  let modelo = (elements.modelo.value || "").trim();
  const serial = prodespGetEquipamentoSerialValue(context);
  if (!modelo && serial) {
    modelo = prodespInferModeloEquipamentoFromSerial(serial);
    if (modelo) prodespSetEquipamentoModeloSelect(elements.modelo, modelo);
    modelo = (elements.modelo.value || modelo || "").trim();
  }
  const descricao = elements.descricao.value.trim();
  const versao = prodespFortiosVersionOrDefault(elements.versao ? elements.versao.value : "");
  const equipmentId = editingEquipmentId;

  if (
    !prodespValidateNoWhitespaceFieldValue(serial, "Número de série", elements.serial) ||
    !prodespValidateNoWhitespaceFieldValue(versao, "Versão do equipamento (FortiOS)", elements.versao)
  ) {
    return;
  }

  if (
    window.ProdespLiveValidation &&
    ProdespLiveValidation.validateEquipamentoSubmit
  ) {
    const eqCheck = ProdespLiveValidation.validateEquipamentoSubmit(
      { serial: serial, versao: versao },
      { obrigatorio: true, exigePadrao: true }
    );
    if (!eqCheck.valid) {
      if (ProdespLiveValidation.paintSerialFortinetField) {
        ProdespLiveValidation.paintSerialFortinetField(elements.serial, null, {
          obrigatorio: true,
          exigePadrao: true,
        });
      }
      return showToast(eqCheck.message || "Serial Fortinet inválido.", "warning");
    }
  }

  // Validação de campos obrigatórios
  if (!modelo || !serial) {
    return showToast("Para adicionar um equipamento, Modelo e Serial são obrigatórios.", "warning");
  }

  const existingEquipArray = context === 'edit' ? existingEquipments : existingEquipmentsCreate;
  const dupEquipSameUnit = existingEquipArray.find(
    (eq) => (eq.serial || '').trim().toUpperCase() === serial && eq.id_equipamento !== equipmentId
  );
  if (dupEquipSameUnit && equipmentId) {
    return showToast("Este equipamento (Serial) já está adicionado nesta unidade.", "warning");
  }

  const attendanceId = context === 'edit' ? +document.getElementById("editAtendimentoId").value : currentCreateModalAtendimentoId;
  const unitId = context === 'edit' ? originalData.id_unidades_atendimentos : selectedUnidadeId;
  if (!attendanceId) return showToast("Inicie o atendimento antes de adicionar itens.", "warning");

  const eqPayload = { modelo, serial, versao, descricao };
  const resolvedEquipId = equipmentId || (dupEquipSameUnit ? dupEquipSameUnit.id_equipamento : null);
  if (resolvedEquipId) eqPayload.id = resolvedEquipId;

  try {
    const res = await fetch("/prodesp/equipamentos-update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id_atendimento: attendanceId,
        id_unidade_equipamentos: unitId,
        new_equipamentos: [eqPayload],
        deleted_equipamentos: []
      }),
    });
    const result = await res.json();
    if (result.success) {
      showToast(resolvedEquipId ? "Equipamento atualizado!" : "Equipamento adicionado!", "success");
      await prodespApplyEquipamentosApiResult(result, context, attendanceId);

      // Reseta o estado da UI
      cancelEditEquipment(context);
    } else {
      showToast(result.message, "danger");
    }
  } catch (err) { showToast("Erro ao salvar equipamento.", "danger"); }
}

// Adiciona os listeners aos botões, chamando a função unificada 
document.getElementById('btn-add-equipamento-edit')?.addEventListener('click', () => addEquipmentLogic('edit'));
document.getElementById('btn-confirm-equipamento-edit')?.addEventListener('click', () => addEquipmentLogic('edit'));
document.getElementById('btn-cancel-equipamento-edit')?.addEventListener('click', () => cancelEditEquipment('edit'));

document.getElementById('btn-add-equipamento-create')?.addEventListener('click', () => addEquipmentLogic('create'));
document.getElementById('btn-confirm-equipamento-create')?.addEventListener('click', () => addEquipmentLogic('create'));
document.getElementById('btn-cancel-equipamento-create')?.addEventListener('click', () => cancelEditEquipment('create'));

// --------------------------------------------------------------------------------
// FUNÇÕES DE LINKS
// --------------------------------------------------------------------------------

function renderLinkCard(linkObj, containerEl, targetArray, deletedArray = null, context = 'edit') {
  if (!containerEl) return;

  const accordion = prodespEnsureIncidentAccordionList(containerEl);
  if (!accordion) return;

  const summary = prodespLinkAccordionSummary(linkObj);
  const shell = prodespBuildIncidentAccordionItem(summary, accordion.id);
  const { item, grid, actionsSlot, collapse } = shell;

  const showCollapse = (open) => {
    const inst = bootstrap.Collapse.getOrCreateInstance(collapse, { toggle: false });
    if (open) inst.show();
    else inst.hide();
  };

  const linkViewFields = () => [
    ["ID VGR", linkObj.id_vgr],
    ["Tipo", linkObj.tipo],
    ["Designador", linkObj.designador],
    ["Operadora", linkObj.operadora],
    ["VLAN", linkObj.vlan],
    ["Velocidade", linkObj.velocidade],
    ["IP WAN", linkObj.ip_wan],
    ["Redundante Crítico", linkObj.redundante_critico ? "Sim" : "Não"],
    ["Gateway", linkObj.ip_gateway],
    ["Máscara", linkObj.ip_mascara],
    ["PPPoE User", linkObj.pppoe_user],
    ["PPPoE Pass", linkObj.pppoe_pass],
  ];

  const renderViewMode = () => {
    showCollapse(false);
    item.classList.remove("prodesp-incident-item-editing");
    shell.toggleBtn.textContent = prodespLinkAccordionSummary(linkObj);
    grid.innerHTML = "";
    linkViewFields().forEach(([label, val]) => {
      grid.appendChild(prodespCreateIncidentReadonlyCol(label, val));
    });

    const editButton = document.createElement("button");
    editButton.innerHTML = '<i class="fas fa-pencil-alt"></i>';
    editButton.type = "button";
    editButton.className = "btn btn-sm btn-outline-primary";
    editButton.title = "Editar Link";
    editButton.onclick = (e) => { e.stopPropagation(); renderEditMode(); };

    const delButton = document.createElement("button");
    delButton.innerHTML = '<i class="fas fa-trash"></i>';
    delButton.type = "button";
    delButton.className = "btn btn-sm btn-outline-danger";
    delButton.title = "Excluir Link";
    delButton.onclick = (e) => { e.stopPropagation(); deleteLink(); };

    if (context === "create" && !currentCreateModalAtendimentoId) {
      editButton.disabled = delButton.disabled = true;
    }
    actionsSlot.innerHTML = "";
    actionsSlot.appendChild(prodespCreateIncidentActionsGroup([editButton, delButton]));
  };

  const renderEditMode = () => {
    showCollapse(true);
    item.classList.add("prodesp-incident-item-editing");
    shell.toggleBtn.textContent = "Editando link…";
    grid.innerHTML = "";

    const idVgrInp = document.createElement("input"); idVgrInp.className = "form-control form-control-sm"; idVgrInp.value = linkObj.id_vgr || "";
    const typeSel = document.createElement("select"); typeSel.className = "form-select form-select-sm";
    ["STATIC", "MPLS", "DHCP", "PPPoE"].forEach((opt) => typeSel.add(new Option(opt, opt))); typeSel.value = linkObj.tipo || "";
    const desigInp = document.createElement("input"); desigInp.className = "form-control form-control-sm"; desigInp.value = linkObj.designador || "";
    const operSel = prodespCreateLinkOperadoraSelect(linkObj.operadora);
    const vlanInp = document.createElement("input"); vlanInp.className = "form-control form-control-sm"; vlanInp.value = linkObj.vlan || "";
    const velInp = document.createElement("input"); velInp.className = "form-control form-control-sm prodesp-velocity-mbps-input"; velInp.value = linkObj.velocidade || "";
    const wanInp = document.createElement("input"); wanInp.className = "form-control form-control-sm prodesp-ip-plain-only"; wanInp.value = linkObj.ip_wan || "";
    const gwInp = document.createElement("input"); gwInp.className = "form-control form-control-sm prodesp-ip-plain-only"; gwInp.value = linkObj.ip_gateway || "";
    const maskInp = document.createElement("input"); maskInp.className = "form-control form-control-sm"; maskInp.value = linkObj.ip_mascara || "";
    const redundanteChk = document.createElement("input");
    redundanteChk.type = "checkbox";
    redundanteChk.className = "form-check-input";
    redundanteChk.checked = !!linkObj.redundante_critico;
    const redundanteCol = prodespCreateIncidentFieldCol("Redundante Crítico", redundanteChk);
    redundanteCol.classList.add("mpls-vivo-redundante-wrapper");
    bindProdespNoWhitespace(idVgrInp);
    bindProdespNoWhitespace(vlanInp);
    bindProdespNoWhitespace(velInp);
    bindProdespIpNoWhitespace(wanInp);
    bindProdespIpNoWhitespace(gwInp);
    bindProdespIpNoWhitespace(maskInp);
    bindProdespNoWhitespace(desigInp);
    if (window.ProdespLiveValidation) {
      let inlineVivo = null;
      const redundanteCtrl = ProdespLiveValidation.initRedundanteCriticoMplsVivo({
        wanEl: wanInp,
        checkboxEl: redundanteChk,
        wrapperEl: redundanteCol,
        tipoEl: typeSel,
        operadoraEl: operSel,
        onAfterApply: function () {
          if (inlineVivo && inlineVivo.apply) inlineVivo.apply("wan");
          ProdespLiveValidation.paintVivoLinkCompliance(wanInp, maskInp, gwInp, operSel.value, {
            linkTipo: typeSel.value,
            label: ProdespLiveValidation.linkLabelFromTipoDesignador(typeSel.value, desigInp.value),
            redundanteCritico: !!redundanteChk.checked,
          });
        },
      });
      inlineVivo = ProdespLiveValidation.initInlineAtendimentoLinkRow(wanInp, gwInp, maskInp, operSel, typeSel, desigInp, {
        redundanteCritico: function () {
          return !!redundanteChk.checked;
        },
      });
      ProdespLiveValidation.bindVelocityMbpsInput(velInp);
      ProdespLiveValidation.paintVivoLinkCompliance(wanInp, maskInp, gwInp, operSel.value, {
        linkTipo: typeSel.value,
        label: ProdespLiveValidation.linkLabelFromTipoDesignador(typeSel.value, desigInp.value),
        redundanteCritico: !!redundanteChk.checked,
      });
    }
    const uInp = document.createElement("input"); uInp.className = "form-control form-control-sm"; uInp.value = linkObj.pppoe_user || "";
    const pInp = document.createElement("input"); pInp.className = "form-control form-control-sm"; pInp.value = linkObj.pppoe_pass || "";

    const idVgrCol = prodespCreateIncidentFieldCol("ID VGR do Link", idVgrInp);
    const syncInlineIdVgr = () => {
      const tipo = String(typeSel.value || "").trim().toUpperCase();
      const tipoOk = tipo === "MPLS" || tipo === "STATIC";
      const operadora = String(operSel.value || "").trim();
      const isVivo = window.ProdespLiveValidation
        ? ProdespLiveValidation.isVivoOperadora(operadora)
        : operadora.toUpperCase() === "VIVO";
      const show = tipoOk && isVivo;
      idVgrCol.style.display = show ? "" : "none";
      if (show) idVgrInp.setAttribute("required", "required");
      else idVgrInp.removeAttribute("required");
    };
    typeSel.addEventListener("change", syncInlineIdVgr);
    operSel.addEventListener("change", syncInlineIdVgr);

    [
      idVgrCol,
      prodespCreateIncidentFieldCol("Tipo", typeSel),
      prodespCreateIncidentFieldCol("Designador", desigInp),
      prodespCreateIncidentFieldCol("Operadora", operSel),
      prodespCreateIncidentFieldCol("VLAN", vlanInp),
      prodespCreateIncidentFieldCol("Velocidade", velInp),
      prodespCreateIncidentFieldCol("IP WAN", wanInp),
      redundanteCol,
      prodespCreateIncidentFieldCol("Gateway", gwInp),
      prodespCreateIncidentFieldCol("Máscara", maskInp),
      prodespCreateIncidentFieldCol("PPPoE User", uInp),
      prodespCreateIncidentFieldCol("PPPoE Pass", pInp),
    ].forEach((col) => grid.appendChild(col));
    syncInlineIdVgr();

    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.innerHTML = '<i class="fas fa-check me-1"></i>Salvar';
    saveBtn.className = "btn btn-sm btn-success";
    saveBtn.title = "Salvar edição do link";
    saveBtn.onclick = async (e) => {
      e.stopPropagation();
      if (!typeSel.value || !desigInp.value.trim()) return showToast("Tipo e Designador são obrigatórios.", "warning");
      const designadorVal = desigInp.value.trim();
      if (window.ProdespLiveValidation) {
        ProdespLiveValidation.paintVivoLinkCompliance(wanInp, maskInp, gwInp, operSel.value, {
          linkTipo: typeSel.value,
          label: ProdespLiveValidation.linkLabelFromTipoDesignador(typeSel.value, designadorVal),
          redundanteCritico: !!redundanteChk.checked,
        });
      }
      const wanVal = prodespStripIpSpaces(wanInp.value);
      const gwVal = prodespStripIpSpaces(gwInp.value);
      const maskVal = prodespStripIpSpaces(maskInp.value);
      if (!prodespValidateNoWhitespaceFieldValue(designadorVal, "Designador", desigInp)) return;
      let finalWan = wanVal;
      let finalGw = gwVal;
      let finalMask = maskVal;
      if (window.ProdespLiveValidation) {
        const velNorm = ProdespLiveValidation.normalizeVelocityMbps(velInp.value);
        velInp.value = velNorm.value;
        ProdespLiveValidation.applyVelocityMbpsToField(velInp, true);
        const vr = ProdespLiveValidation.validateAtendimentoLinkSubmit({
          tipo: typeSel.value,
          designador: designadorVal,
          operadora: operSel.value.trim(),
          velocidade: velInp.value.trim(),
          idVgr: idVgrInp.value.trim(),
          ipWan: wanVal,
          redundanteCritico: redundanteChk.checked,
          ipGateway: gwVal,
          ipMascara: maskVal,
          pppoeUser: uInp.value.trim(),
          pppoePass: pInp.value.trim(),
        });
        if (!vr.valid) {
          ProdespLiveValidation.paintVivoLinkCompliance(wanInp, maskInp, gwInp, operSel.value.trim(), {
            linkTipo: typeSel.value,
            label: ProdespLiveValidation.linkLabelFromTipoDesignador(typeSel.value, designadorVal),
            redundanteCritico: !!redundanteChk.checked,
          });
          showToast(vr.message, "warning");
          return;
        }
        finalWan = vr.ipWan;
        finalGw = vr.ipGateway;
        finalMask = vr.ipMascara;
      } else if (!prodespValidateLinkIpRules(typeSel.value, designadorVal, wanVal, gwVal)) {
        return;
      }
      const attendanceId = context === "edit" ? +document.getElementById("editAtendimentoId").value : currentCreateModalAtendimentoId;
      const unitId = context === "edit" ? originalData.id_unidades_atendimentos : selectedUnidadeId;
      const linkPayload = {
        id: linkObj.id_link,
        id_vgr: idVgrInp.value.trim(),
        tipo: typeSel.value,
        designador: designadorVal,
        operadora: operSel.value.trim(),
        vlan: vlanInp.value.trim(),
        velocidade: velInp.value.trim(),
        ip_wan: finalWan,
        redundante_critico: redundanteChk.checked,
        ip_gateway: finalGw,
        ip_mascara: finalMask,
        pppoe_user: uInp.value.trim(),
        pppoe_pass: pInp.value.trim(),
      };
      try {
        const uniqOk = await prodespCheckUniquenessBeforeSave({
          id_unidade: unitId,
          links: [linkPayload],
        }, {
          elements: [wanInp, gwInp, desigInp, idVgrInp].filter(Boolean),
        });
        if (!uniqOk) return;
        const res = await fetch("/prodesp/links-update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id_atendimento: attendanceId,
            id_unidade_links: unitId,
            new_links: [linkPayload],
            deleted_links: [],
          }),
        });
        const r = await res.json();
        if (r.success) {
          showToast("Link atualizado!", "success");
          await prodespApplyLinksApiResult(r, context, attendanceId);
        } else showToast(r.message, "danger");
      } catch (_e) { showToast("Erro ao salvar.", "danger"); }
    };

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.innerHTML = '<i class="fas fa-times me-1"></i>Cancelar';
    cancelBtn.className = "btn btn-sm btn-secondary";
    cancelBtn.title = "Cancelar edição do link";
    cancelBtn.onclick = (e) => { e.stopPropagation(); renderViewMode(); };

    actionsSlot.innerHTML = "";
    actionsSlot.appendChild(prodespCreateIncidentActionsGroup([saveBtn, cancelBtn]));
  };

  const deleteLink = async () => {
    if (linkObj.id_link) {
      const attendanceId = context === "edit" ? +document.getElementById("editAtendimentoId").value : currentCreateModalAtendimentoId;
      const unitId = context === "edit" ? originalData.id_unidades_atendimentos : selectedUnidadeId;
      try {
        const res = await fetch("/prodesp/links-update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id_atendimento: attendanceId,
            id_unidade_links: unitId,
            new_links: [],
            deleted_links: [linkObj.id_link],
          }),
        });
        const result = await res.json();
        if (result.success) {
          showToast("Link removido do banco.", "success");
          await prodespApplyLinksApiResult(result, context, attendanceId);
        } else { showToast(result.message, "danger"); }
      } catch (_e) { showToast("Erro ao excluir link.", "danger"); }
    } else {
      item.remove();
      const idx = targetArray.findIndex((l) => l.designador === linkObj.designador);
      if (idx > -1) targetArray.splice(idx, 1);
    }
  };

  accordion.appendChild(item);
  renderViewMode();
}

async function prodespCheckUniquenessBeforeSave(payload, paintOpts) {
  try {
    const res = await fetch("/prodesp/api/check-uniqueness", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    const data = await res.json();
    if (data && data.ok === false) {
      const msgs =
        data.errors && data.errors.length
          ? data.errors
          : [data.message || "Há valores duplicados. Corrija antes de salvar."];
      if (paintOpts) {
        prodespPaintAtendimentoUniqueness(paintOpts, msgs);
      }
      showToast(msgs.join(" "), "danger", Math.min(12000, 5000 + msgs.length * 1500));
      return false;
    }
    if (paintOpts) {
      prodespClearAtendimentoUniqueness(paintOpts);
    }
    return true;
  } catch (_e) {
    // Se a pré-checagem falhar, o save no servidor ainda bloqueia.
    return true;
  }
}

function prodespCollectLoopbacksForUniqueness(prefix) {
  const read = (suffix) => {
    const el = document.getElementById(prefix + suffix);
    return prodespStripIpSpaces(el ? el.value || "" : "");
  };
  return {
    loopback_vivo_unidades: read("LoopbackVivo"),
    loopback_cliente_unidades: read("LoopbackCliente"),
    loopback_on_bgp_unidades: read("LoopbackOnBgp"),
  };
}

function prodespPaintFieldUniqError(el, message) {
  if (!el) return;
  el.setAttribute("data-prodesp-uniq", "1");
  el.classList.remove("prodesp-field-state-ok", "prodesp-field-state-warn");
  el.classList.add("prodesp-field-state-empty", "is-invalid");
  let hint = el.parentNode && el.parentNode.querySelector("small[data-uniq-hint]");
  if (!hint && el.parentNode) {
    hint = document.createElement("small");
    hint.className = "prodesp-field-live-hint is-invalid-hint";
    hint.setAttribute("data-uniq-hint", "1");
    el.parentNode.appendChild(hint);
  }
  if (hint) {
    hint.textContent = message || "Valor duplicado.";
    hint.classList.add("is-invalid-hint");
  }
}

function prodespClearFieldUniqError(el) {
  if (!el || el.getAttribute("data-prodesp-uniq") !== "1") return;
  el.removeAttribute("data-prodesp-uniq");
  el.classList.remove("prodesp-field-state-empty", "is-invalid");
  const hint = el.parentNode && el.parentNode.querySelector("small[data-uniq-hint]");
  if (hint) hint.textContent = "";
}

function prodespClearAtendimentoUniqueness(paintOpts) {
  const els = prodespResolveUniquenessPaintElements(paintOpts);
  els.forEach(prodespClearFieldUniqError);
}

function prodespResolveUniquenessPaintElements(paintOpts) {
  const opts = paintOpts || {};
  const out = [];
  if (opts.context) {
    const ctx = opts.context;
    ["IpWan", "IpGateway", "Designador", "IdVgr", "LoopbackVivo", "LoopbackCliente", "LoopbackOnBgp"].forEach(
      (suffix) => {
        const el = document.getElementById(ctx + "Link" + suffix) || document.getElementById(ctx + suffix);
        if (el) out.push(el);
      }
    );
  }
  if (opts.elements) {
    opts.elements.forEach((el) => {
      if (el) out.push(el);
    });
  }
  return out;
}

function prodespPaintAtendimentoUniqueness(paintOpts, messages) {
  const msgs = messages || [];
  const els = prodespResolveUniquenessPaintElements(paintOpts);
  prodespClearAtendimentoUniqueness(paintOpts);
  const rules = [
    { re: /IP WAN/i, keys: [/IpWan$/i, /ip_wan/i] },
    { re: /IP Gateway|Gateway/i, keys: [/IpGateway$/i, /ip_gateway/i] },
    { re: /Designador/i, keys: [/Designador$/i, /designador/i] },
    { re: /ID VGR/i, keys: [/IdVgr$/i, /id_vgr/i] },
    { re: /Loopback Vivo/i, keys: [/LoopbackVivo$/i] },
    { re: /Loopback Cliente/i, keys: [/LoopbackCliente$/i] },
    { re: /On BGP|Loopback On BGP/i, keys: [/LoopbackOnBgp$/i] },
  ];
  msgs.forEach((msg) => {
    const m = String(msg || "");
    rules.forEach((rule) => {
      if (!rule.re.test(m)) return;
      els.forEach((el) => {
        const id = el.id || el.name || "";
        if (rule.keys.some((k) => k.test(id))) {
          prodespPaintFieldUniqError(el, m);
        }
      });
    });
  });
}

async function addLinkLogic(context) {
  const getEl = (id) => document.getElementById(`${context}Link${id}`);
  const fields = ['Designador', 'Tipo', 'Operadora', 'Vlan', 'IpWan', 'IpGateway', 'IpMascara', 'Velocidade', 'PppoeUser', 'PppoePass', 'IdVgr'];
  const values = {};
  fields.forEach(f => {
    const el = getEl(f);
    values[f] = el ? el.value.trim() : '';
  });
  const redundanteEl = document.getElementById(`${context}LinkRedundanteCritico`);
  values.RedundanteCritico = !!(redundanteEl && redundanteEl.checked);
  values.IpWan = prodespSanitizePlainIpValue(values.IpWan);
  values.IpGateway = prodespSanitizePlainIpValue(values.IpGateway);
  values.IpMascara = prodespStripIpSpaces(values.IpMascara);

  if (window.ProdespLiveValidation && ProdespLiveValidation.normalizeVelocityMbps) {
    const velEl = getEl("Velocidade");
    const velNorm = ProdespLiveValidation.normalizeVelocityMbps(values.Velocidade);
    values.Velocidade = velNorm.value;
    if (velEl && ProdespLiveValidation.applyVelocityMbpsToField) {
      ProdespLiveValidation.applyVelocityMbpsToField(velEl, true);
    }
  }

  if (window.ProdespLiveValidation) {
    const wanEl = getEl("IpWan");
    const gwEl = getEl("IpGateway");
    const maskEl = getEl("IpMascara");
    const operEl = getEl("Operadora");
    const tipoVal = values.Tipo;
    const vr = ProdespLiveValidation.validateAtendimentoLinkSubmit({
      tipo: tipoVal,
      designador: values.Designador,
      operadora: values.Operadora,
      velocidade: values.Velocidade,
      idVgr: values.IdVgr,
      ipWan: values.IpWan,
      redundanteCritico: values.RedundanteCritico,
      ipGateway: values.IpGateway,
      ipMascara: values.IpMascara,
      pppoeUser: values.PppoeUser,
      pppoePass: values.PppoePass,
    });
    if (!vr.valid) {
      ProdespLiveValidation.paintVivoLinkCompliance(wanEl, maskEl, gwEl, operEl && operEl.value, {
        linkTipo: tipoVal,
        label: ProdespLiveValidation.linkLabelFromTipoDesignador(tipoVal, values.Designador),
        redundanteCritico: !!values.RedundanteCritico,
      });
      showToast(vr.message, "warning");
      return;
    }
    values.IpWan = vr.ipWan;
    values.IpGateway = vr.ipGateway;
    values.IpMascara = vr.ipMascara;
  }

  if (
    !prodespValidateNoWhitespaceFieldValue(values.Designador, "Designador", getEl("Designador")) ||
    !prodespValidateNoWhitespaceFieldValue(values.IdVgr, "ID VGR do Link", getEl("IdVgr")) ||
    !prodespValidateNoWhitespaceFieldValue(values.Vlan, "VLAN", getEl("Vlan")) ||
    !prodespValidateNoWhitespaceFieldValue(values.Velocidade, "Velocidade (Mbps)", getEl("Velocidade"))
  ) {
    return;
  }
  if (!window.ProdespLiveValidation &&
    !prodespValidateLinkIpRules(values.Tipo, values.Designador, values.IpWan, values.IpGateway)
  ) {
    return;
  }
  if (values.IpWan && !prodespIsValidIpFieldValue(values.IpWan, false)) {
    const wanEl = getEl("IpWan");
    if (wanEl) wanEl.classList.add("is-invalid");
    return showToast("IP WAN: informe um endereço IPv4 válido, sem máscara (ex.: 10.1.1.1).", "warning");
  }
  if (values.IpGateway && !prodespIsValidIpFieldValue(values.IpGateway, false)) {
    const gwEl = getEl("IpGateway");
    if (gwEl) gwEl.classList.add("is-invalid");
    return showToast("Gateway: informe um endereço IPv4 válido, sem máscara (ex.: 10.1.1.1).", "warning");
  }

  // Check if 'id' is present for an update operation
  const linkId = editingLinkId;

  if (!values.Tipo) return showToast("O campo Tipo de Link é obrigatório.", "warning");
  if (!values.Designador) return showToast("O campo Designador é obrigatório.", "warning");
  if (!values.Operadora) return showToast("O campo Operadora é obrigatório.", "warning");
  if (!values.Velocidade) return showToast("O campo Velocidade é obrigatório.", "warning");

  const existingLnkArray = context === 'edit' ? existingLinks : existingLinksCreate;
  const dupLinkByDesignador = existingLnkArray.find(
    (l) =>
      (l.designador || '').trim().toUpperCase() === values.Designador.toUpperCase() &&
      l.id_link !== linkId
  );
  const idVgrForDup = (getEl('IdVgr')?.value.trim() || document.getElementById(`${context}IdVgr`)?.value.trim() || '');
  const dupLinkByIdVgr = idVgrForDup
    ? existingLnkArray.find(
        (l) => (l.id_vgr || '').trim() === idVgrForDup && l.id_link !== linkId
      )
    : null;
  if ((dupLinkByDesignador || dupLinkByIdVgr) && linkId) {
    return showToast("Este designador ou ID de link já foi adicionado nesta unidade.", "warning");
  }

  const attendanceId = context === 'edit' ? +document.getElementById("editAtendimentoId").value : currentCreateModalAtendimentoId;
  const unitId = context === 'edit' ? originalData.id_unidades_atendimentos : selectedUnidadeId;
  if (!attendanceId) return showToast("Inicie o atendimento antes de adicionar links.", "warning");

  const idVgrInput = getEl('IdVgr');
  const mainIdVgr = document.getElementById(`${context}IdVgr`).value.trim();

  const linkObj = {
    designador: values.Designador,
    tipo: values.Tipo,
    operadora: values.Operadora,
    vlan: values.Vlan,
    ip_wan: values.IpWan,
    redundante_critico: values.RedundanteCritico,
    ip_gateway: values.IpGateway,
    ip_mascara: values.IpMascara,
    velocidade: values.Velocidade,
    pppoe_user: values.PppoeUser,
    pppoe_pass: values.PppoePass,
    id_vgr: (idVgrInput && idVgrInput.value.trim()) ? idVgrInput.value.trim() : mainIdVgr,
    id: linkId || (dupLinkByDesignador?.id_link ?? dupLinkByIdVgr?.id_link ?? null),
  };

  try {
    const uniqOk = await prodespCheckUniquenessBeforeSave({
      id_unidade: unitId,
      links: [linkObj],
    }, { context: context });
    if (!uniqOk) return;

    const res = await fetch("/prodesp/links-update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id_atendimento: attendanceId,
        id_unidade_links: unitId,
        new_links: [linkObj],
        deleted_links: []
      }),
    });
    const result = await res.json();
    if (result.success) {
      showToast("Link salvo!", "success");
      await prodespApplyLinksApiResult(result, context, attendanceId);

      cancelEditLink(context);
    } else {
      showToast(result.message, "danger");
      return;
    }
  } catch (err) { return showToast("Erro ao conectar ao servidor.", "danger"); }
}

document.getElementById('btn-add-link-edit')?.addEventListener('click', () => addLinkLogic('edit'));
document.getElementById('btn-confirm-link-edit')?.addEventListener('click', () => addLinkLogic('edit'));
document.getElementById('btn-cancel-link-edit')?.addEventListener('click', () => cancelEditLink('edit'));

document.getElementById('btn-add-link-create')?.addEventListener('click', () => addLinkLogic('create'));
document.getElementById('btn-confirm-link-create')?.addEventListener('click', () => addLinkLogic('create'));
document.getElementById('btn-cancel-link-create')?.addEventListener('click', () => cancelEditLink('create'));

// --------------------------------------------------------------------------------
// FUNÇÕES DE LOGS (Adicionar texto ao textarea)
// --------------------------------------------------------------------------------
function parseLogString(logString) {
  if (!logString || typeof logString !== "string") return [];

  let raw = logString.replace(/^\uFEFF/, "").trim();
  raw = prodespStripLegacyColetaLogPrefix(raw);

  const entries = [];
  let remaining = raw;

  while (remaining.length > 0) {
    const iniIdx = remaining.indexOf(PRODESP_COLETA_FGT_INI);
    if (iniIdx === -1) {
      entries.push(...parseManualLogChunk(remaining));
      break;
    }

    if (iniIdx > 0) {
      entries.push(...parseManualLogChunk(remaining.slice(0, iniIdx)));
    }

    const fromIni = remaining.slice(iniIdx);
    const fimIdx = fromIni.indexOf(PRODESP_COLETA_FGT_FIM);
    if (fimIdx === -1) {
      entries.push(prodespMakeColetaFgtLogEntry(fromIni.trim()));
      break;
    }

    const coletaEnd = fimIdx + PRODESP_COLETA_FGT_FIM.length;
    entries.push(prodespMakeColetaFgtLogEntry(fromIni.slice(0, coletaEnd).trim()));
    remaining = fromIni.slice(coletaEnd);
  }

  return entries;
}

function renderLogCard(logObj, containerEl, targetArray) {
  if (!containerEl) return;
  const card = document.createElement("div");
  card.classList.add("card-incident", "prodesp-log-config-card");

  const makeDiv = (cls, txt) => {
    const d = document.createElement("div");
    d.classList.add(cls);
    d.textContent = txt || "—";
    return d;
  };

  const metaCol = document.createElement("div");
  metaCol.classList.add("prodesp-log-config-meta");
  if (logObj.fgtAutoColeta) {
    metaCol.appendChild(makeDiv("incident-data", "Coleta FGT"));
    metaCol.appendChild(makeDiv("incident-user", "automático"));
  } else {
    metaCol.appendChild(makeDiv("incident-data", logObj.timestamp));
    metaCol.appendChild(makeDiv("incident-user", logObj.user));
  }

  const textWrap = document.createElement("div");
  textWrap.classList.add("incident-log-text-wrap");
  textWrap.appendChild(makeDiv("incident-log-text", logObj.text));

  const delButton = document.createElement("button");
  delButton.innerHTML = '<i class="fas fa-trash"></i>';
  delButton.type = "button";
  delButton.title = "Remover log";
  delButton.classList.add("btn", "btn-sm", "btn-outline-danger");
  delButton.addEventListener("click", () => {
    card.remove();
    const idx = targetArray.indexOf(logObj);
    if (idx > -1) targetArray.splice(idx, 1);
    const context = containerEl.id.includes("edit") ? "edit" : "create";
    const form = document.getElementById(`${context}Form`);
    if (form) form.dispatchEvent(new Event("input", { bubbles: true }));
  });

  if (
    containerEl &&
    containerEl.id.includes("create") &&
    !currentCreateModalAtendimentoId
  ) {
    delButton.disabled = true;
  }

  card.appendChild(metaCol);
  card.appendChild(textWrap);
  card.appendChild(delButton);
  containerEl.appendChild(card);

  if (window.ProdespLogConfigPrefs) {
    window.ProdespLogConfigPrefs.bindResize(textWrap);
  }
}

function reloadLogs(logString, containerEl, context) {
  if (!containerEl) return;
  const logsData = parseLogString(logString);
  const header = containerEl.querySelector(".titles-incident");
  containerEl.innerHTML = header ? header.outerHTML : "";
  const targetArray = (context === 'edit') ? logsEdit : logsCreate;
  targetArray.length = 0;
  logsData.forEach(log => {
    targetArray.push(log);
    renderLogCard(log, containerEl, targetArray);
  });
}

function addLogLogic(context) {
  const inputEl = document.getElementById(`${context}LogInput`);
  const containerEl = document.getElementById(`log-configuracao-remota-${context}`);

  if (!inputEl || !containerEl) return;

  const text = inputEl.value.trim();
  if (!text) {
    return showToast("Digite um texto para adicionar ao log.", "warning");
  }

  const logObj = {
    timestamp: new Date().toLocaleString('pt-BR'),
    user: typeof USUARIO_LOGADO !== 'undefined' ? USUARIO_LOGADO : 'Usuário',
    text: text
  };

  const targetArray = (context === 'edit') ? logsEdit : logsCreate;
  targetArray.push(logObj);
  renderLogCard(logObj, containerEl, targetArray);

  inputEl.value = ""; // Limpa o input

  const form = document.getElementById(`${context}Form`);
  if (form) form.dispatchEvent(new Event('input', { bubbles: true }));
}

document.getElementById('btn-add-log-edit')?.addEventListener('click', () => addLogLogic('edit'));
document.getElementById('btn-add-log-create')?.addEventListener('click', () => addLogLogic('create'));

// -------------------------------------------------
// Funções de Limpeza e Recarregamento (Edição de Equipamentos)
// -------------------------------------------------
// Limpa equipamentos QUANDO FECHA O MODAL DE EDIÇÃO
if (modalEl) {
  modalEl.addEventListener("hide.bs.modal", () => {
    // Reset editing states
    editingEquipmentId = null;
    editingLinkId = null;
    // Lógica de limpeza para equipamentos
    const container = document.getElementById("log-equipamento-edit");
    if (container) prodespResetIncidentListContainer(container);

    newEquipamentoEdit.length = 0;
    deletedEquipamentoIds.length = 0;
    // Limpa os inputs também
    if (equipamentoModeloEditEl) equipamentoModeloEditEl.value = "";
    if (equipamentoSerialEditEl) equipamentoSerialEditEl.value = "";
    if (equipamentoMacEditEl) equipamentoMacEditEl.value = ""; // Clear MAC field
    if (equipamentoIotEditEl) equipamentoIotEditEl.checked = false; // Clear IoT checkbox
    if (equipamentoDescricaoEditEl) equipamentoDescricaoEditEl.value = "";
    if (equipamentoVersaoEditEl) equipamentoVersaoEditEl.value = PRODESP_DEFAULT_FORTIOS_VERSION;

    // Limpeza Links
    const linkContainer = document.getElementById("log-link-edit");
    if (linkContainer) prodespResetIncidentListContainer(linkContainer);
    // No need to clear newLinksEdit/deletedLinkIds here, they are handled by saveEdit
    // Clear link form fields
    clearLinkForm('edit');

    if (document.getElementById("editLogInput")) document.getElementById("editLogInput").value = "";
    toggleEditButtons('edit', false); // Ensure buttons are reset
  });
}

// Limpa equipamentos QUANDO FECHA O MODAL DE CRIAÇÃO
if (createModalEl) {
  createModalEl.addEventListener("hide.bs.modal", () => {
    // Lógica de limpeza para equipamentos
    const container = document.getElementById("log-equipamento-create");
    if (container) prodespResetIncidentListContainer(container);

    newEquipamentoCreate.length = 0;
    // Limpa os inputs também
    if (equipamentoModeloCreateEl) equipamentoModeloCreateEl.value = "";
    // Missing clear for other equipment fields
    // if (equipamentoSerialCreateEl) equipamentoSerialCreateEl.value = "";
    if (equipamentoSerialCreateEl) equipamentoSerialCreateEl.value = "";
    if (equipamentoDescricaoCreateEl) equipamentoDescricaoCreateEl.value = "";
    if (equipamentoVersaoCreateEl) equipamentoVersaoCreateEl.value = PRODESP_DEFAULT_FORTIOS_VERSION;

    if (document.getElementById("createLogInput")) document.getElementById("createLogInput").value = "";
  });
}

// -------------------------------------------------
// Funções para RECARREGAR Observações e Equipamentos
// -------------------------------------------------

/**
 * Normaliza item de observação vindo da API ou do histórico.
 */
function prodespNormalizeObservacaoItem(obs) {
  return {
    id_observacao: obs.id ?? obs.id_observacao ?? null,
    data_observacao: obs.timestamp || obs.data_observacao || "",
    observacao_prodesp: obs.texto ?? obs.observacao_prodesp ?? "",
    _stagingPreviousAtendimento: !!obs._stagingPreviousAtendimento,
  };
}

function prodespParseObservacaoDate(value) {
  if (!value) return 0;
  const s = String(value).trim();
  const br = s.match(
    /^(\d{2})\/(\d{2})\/(\d{4})[,\s]+(\d{2}):(\d{2})(?::(\d{2}))?/
  );
  if (br) {
    return new Date(
      Number(br[3]),
      Number(br[2]) - 1,
      Number(br[1]),
      Number(br[4]),
      Number(br[5]),
      Number(br[6] || 0)
    ).getTime();
  }
  const iso = Date.parse(s.includes("T") ? s : s.replace(" ", "T"));
  return Number.isNaN(iso) ? 0 : iso;
}

function prodespSortObservacoesDesc(observacoes) {
  return [...observacoes].sort((a, b) => {
    const itemA = prodespNormalizeObservacaoItem(a);
    const itemB = prodespNormalizeObservacaoItem(b);
    return (
      prodespParseObservacaoDate(itemB.data_observacao) -
      prodespParseObservacaoDate(itemA.data_observacao)
    );
  });
}

function prodespObservacaoMatchKey(obs) {
  const n = prodespNormalizeObservacaoItem(obs);
  return `${n.id_observacao ?? ""}|${n.data_observacao}|${n.observacao_prodesp}`;
}

function prodespRefreshObservacaoCards(
  containerEl,
  headerHtml,
  targetArray,
  deletedArr = null
) {
  if (!containerEl) return;
  containerEl.innerHTML = headerHtml || "";

  let items = [...targetArray];
  if (String(containerEl.id || "").includes("edit")) {
    items = [...observacoesEditPersistidas, ...newObservacao];
  }

  const sorted = prodespSortObservacoesDesc(items);
  const renderedKeys = new Set();
  sorted.forEach((obs) => {
    const key = prodespObservacaoMatchKey(obs);
    if (renderedKeys.has(key)) return;
    renderedKeys.add(key);

    const normalized = prodespNormalizeObservacaoItem(obs);
    const inPersisted = observacoesEditPersistidas.some(
      (o) => prodespObservacaoMatchKey(o) === key
    );
    const arr = inPersisted ? observacoesEditPersistidas : targetArray;
    const stored =
      arr.find((o) => prodespObservacaoMatchKey(o) === key) || normalized;
    renderObservacaoCard(
      stored,
      containerEl,
      arr,
      inPersisted ? deletedObservacaoIds : deletedArr
    );
  });
}

window.prodespSortObservacoesDesc = prodespSortObservacoesDesc;
window.prodespParseObservacaoDate = prodespParseObservacaoDate;

/**
 * Recarrega e renderiza as observações de um atendimento.
 * @param {Array} observacoesData - O array de observações já buscado do backend.
 */
function reloadObservacoes(observacoesData, context = 'edit') {
  let containerEl;
  let headerHtml;
  let deletedArr;
  let targetArray;

  const stagingPreviousAtendimento =
    context === "unidade" || context === "create"
      ? newObservacaoCreate.filter(
          (o) => o._stagingPreviousAtendimento && !o.id_observacao
        )
      : [];

  if (context === "unidade") {
    containerEl = logContainerObservacaoCreate;
    headerHtml = observacaoCreateHeaderHtml;
    deletedArr = deletedObservacaoUnidadeIds;
    targetArray = newObservacaoUnidade;
    newObservacaoUnidade.length = 0;
  } else if (context === 'create') {
    containerEl = logContainerObservacaoCreate;
    headerHtml = observacaoCreateHeaderHtml;
    deletedArr = [];
    targetArray = newObservacaoCreate;
    if (currentCreateModalAtendimentoId) {
      newObservacaoCreate.length = 0;
    }
  } else {
    containerEl = logContainerObservacao;
    headerHtml = observacaoHeaderHtml;
    deletedArr = deletedObservacaoIds;
    targetArray = observacoesEditPersistidas;
    observacoesEditPersistidas.length = 0;
  }

  if (containerEl) {
    containerEl.innerHTML = headerHtml;
  }

  const baseItems = Array.isArray(observacoesData) ? [...observacoesData] : [];
  const stagingItems =
    context === "unidade" || context === "create" ? [...stagingPreviousAtendimento] : [];

  const displayItems = prodespSortObservacoesDesc([...baseItems, ...stagingItems]);
  displayItems.forEach((obs) => {
    const obsObj = prodespNormalizeObservacaoItem(obs);
    const isStaging = !!obsObj._stagingPreviousAtendimento;
    const arr = isStaging ? newObservacaoCreate : targetArray;
    const matchObs = (o) =>
      (o.id_observacao != null &&
        obsObj.id_observacao != null &&
        o.id_observacao === obsObj.id_observacao) ||
      (o.data_observacao === obsObj.data_observacao &&
        o.observacao_prodesp === obsObj.observacao_prodesp);

    let stored = arr.find(matchObs);
    if (!stored) {
      arr.push(obsObj);
      stored = obsObj;
    }
    renderObservacaoCard(
      stored,
      containerEl,
      arr,
      isStaging ? null : deletedArr
    );
  });
}

/** Usa listas retornadas pelo POST; fallback GET só se a API não enviar equipamentos. */
async function prodespApplyEquipamentosApiResult(result, context, attendanceId) {
  if (result && Array.isArray(result.equipamentos)) {
    reloadEquipamentos(result.equipamentos, context);
    return;
  }
  if (attendanceId) {
    const detailRes = await fetch(`/prodesp/atendimentos/${attendanceId}`);
    const detailData = await detailRes.json();
    reloadEquipamentos(detailData.equipamentos, context);
  }
}

/** Usa listas retornadas pelo POST; fallback GET só se a API não enviar links. */
async function prodespApplyLinksApiResult(result, context, attendanceId) {
  if (result && Array.isArray(result.links)) {
    reloadLinks(result.links, context);
    return;
  }
  if (attendanceId) {
    const detailRes = await fetch(`/prodesp/atendimentos/${attendanceId}`);
    const detailData = await detailRes.json();
    reloadLinks(detailData.links, context);
  }
}

/**
 * Recarrega e renderiza os equipamentos de uma Unidade no modal.
 * @param {Array} equipamentosData - O array de equipamentos já buscado do backend.
 * @param {string} context - 'edit' ou 'create' (para determinar qual container usar).
 */
function reloadEquipamentos(equipamentosData, context = 'edit') {
  const logContainer = document.getElementById(`log-equipamento-${context}`);
  if (logContainer) {
    prodespResetIncidentListContainer(logContainer);
  }

  const targetArray = context === 'edit' ? existingEquipments : existingEquipmentsCreate;
  targetArray.length = 0;

  if (Array.isArray(equipamentosData)) {
    equipamentosData.forEach((eq) => {
      // Cria um objeto com a estrutura que a função de renderização espera
      const eqObj = {
        id_equipamento: eq.id,
        modelo: eq.modelo,
        serial: String(eq.serial || "").trim().toUpperCase(),
        versao: prodespFortiosVersionOrDefault(eq.versao),
        descricao: eq.descricao,
      };
      targetArray.push(eqObj);

      // Renderiza o card
      renderEquipamentoCard(
        eqObj,
        logContainer,
        targetArray,
        context === 'edit' ? deletedEquipamentoIds : null, // Only pass deleted array for edit context
        context
      );
    });
  }
}

function reloadLinks(linksData, context = 'edit') {
  const logContainer = document.getElementById(`log-link-${context}`);
  if (logContainer) {
    prodespResetIncidentListContainer(logContainer);
  }

  if (context === 'edit') {
    existingLinks.length = 0;
  } else {
    existingLinksCreate.length = 0; // Clear for create context
  }

  if (Array.isArray(linksData)) {
    linksData.forEach((lnk) => {
      const normalizedLink = prodespNormalizeLinkForDisplay(lnk);
      const lnkObj = {
        id_link: lnk.id,
        id_vgr: lnk.id_vgr_links,
        designador: lnk.designador_links,
        tipo: lnk.tipo_links,
        operadora: lnk.operadora_links,
        vlan: lnk.vlan_links,
        ip_wan: lnk.ip_wan_links,
        redundante_critico: normalizedLink.redundante_critico,
        ip_gateway: lnk.ip_gateway_links,
        ip_mascara: lnk.ip_mascara_links,
        velocidade: lnk.velocidade_links,
        pppoe_user: lnk.pppoe_user_links,
        pppoe_pass: lnk.pppoe_pass_links,
      };
      
      if (context === 'edit') {
        existingLinks.push(lnkObj);
      } else {
        existingLinksCreate.push(lnkObj); // Add to create context array
      }

      renderLinkCard(lnkObj, logContainer, context === 'edit' ? existingLinks : existingLinksCreate, context === 'edit' ? deletedLinkIds : null, context);
    });
  }
}

// ------------------------------
// RENDER MARCOS EXIBIÇÃO
// ------------------------------
function renderMarcos(marcos) {
  // 🛑 Caso não haja dados, exibe mensagem padrão
  if (!marcos || !marcos.length) {
    return `<div class="text-center text-muted p-3"><em>— Nenhum marco registrado —</em></div>`;
  }

  // ⏱️ Metas definidas por etapa (Exemplo adaptado para PRODESP)
  const metas = {
    "Aguarda Gestão": { horaIdeal: 8, duracaoIdeal: 1 * 3600 },
    "Em Configuração Remota": { horaIdeal: 9, duracaoIdeal: 2 * 3600 },
    "Em Configuração do MPLS": { horaIdeal: 11, duracaoIdeal: 1 * 3600 },
    "Em Caderno de Teste": { horaIdeal: 12, duracaoIdeal: 1 * 3600 },
    "Concluído": { horaIdeal: 13, duracaoIdeal: 0 },
  };

  // 📅 Formata datas
  const formatar = (str) => {
    if (!str) return "—";
    const d = new Date(str);
    return `${d.toLocaleDateString("pt-BR")} às ${d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
  };

  // ⏳ Converte segundos em "HH:mm:ss"
  const formatarDuracao = (segundos) => {
    if (segundos == null || isNaN(segundos)) return "—";
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

  // 📋 Gera texto legível da meta
  const formatarMeta = (marco, meta) => {
    if (typeof prodespLabelMarcoAtividade === "function") {
      return prodespLabelMarcoAtividade(marco);
    }
    return marco === "Triagem" ? "Aguarda Gestão" : marco;
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

  // 📦 Gera a tabela
  return `
    <h6 class="text-uppercase text-secondary mb-3 mt-3">⏳ Marcos da Atividade</h6>
    ${legendaHTML}
    <div class="table-responsive mt-4">
      <table class="table table-bordered table-sm">
        <thead>
          <tr>
            <th>Marco</th>
            <th>Início</th>
            <th>Fim</th>
            <th>Duração</th>
          </tr>
        </thead>
        <tbody>
          ${marcos.map((m) => {
    const classe = getClasse(m.marco, m.duracao);
    let cor = "";
    if (classe === "vermelho") cor = "table-danger";
    else if (classe === "amarelo") cor = "table-warning";
    else if (classe === "azul") cor = "table-info";
    const meta = metas[m.marco];

    return `
                <tr class="${cor}">
                  <td>${formatarMeta(m.marco, meta)}</td>
                  <td>${formatar(m.inicio)}</td>
                  <td>${formatar(m.fim)}</td>
                  <td>${formatarDuracao(m.duracao)}</td>
                </tr>
              `;
  }).join("")}
        </tbody>
      </table>
    </div>
  `;
}

// ------------------------------
// RENDER HISTÓRICO
// ------------------------------
let prodespAdminAuditPendingRow = null;

function prodespAdminAuditMultiEditEnabled() {
  return !!document.getElementById("adminAuditMultiEdit")?.checked;
}

function prodespAdminAuditCanSave(section, rowId) {
  if (prodespAdminAuditMultiEditEnabled()) return true;
  if (!prodespAdminAuditPendingRow) return true;
  if (
    prodespAdminAuditPendingRow.section === section &&
    String(prodespAdminAuditPendingRow.id) === String(rowId)
  ) {
    return true;
  }
  showToast(
    "Edite apenas uma linha por vez. Salve ou recarregue antes de alterar outra, ou marque «Permitir edição simultânea».",
    "warning"
  );
  return false;
}

function prodespAdminAuditMarkDirty(section, rowId) {
  if (prodespAdminAuditMultiEditEnabled()) return;
  prodespAdminAuditPendingRow = { section, id: String(rowId) };
  document.querySelectorAll("#edit-admin-audit-pane tbody tr").forEach((tr) => {
    tr.classList.remove("table-warning");
  });
  const sel =
    section === "sl"
      ? `tr[data-log-id="${rowId}"]`
      : section === "hist"
        ? `tr[data-hist-id="${rowId}"]`
        : section === "hist-u"
          ? `tr[data-hist-un-id="${rowId}"]`
          : section === "obs"
            ? `tr[data-obs-id="${rowId}"]`
            : section === "eq"
              ? `tr[data-eq-id="${rowId}"]`
              : `tr[data-link-id="${rowId}"]`;
  document.querySelector(sel)?.classList.add("table-warning");
}

function prodespAdminAuditClearDirty() {
  prodespAdminAuditPendingRow = null;
  document
    .querySelectorAll("#edit-admin-audit-pane tbody tr.table-warning")
    .forEach((tr) => tr.classList.remove("table-warning"));
}

/**
 * Abre o modal de criação de atendimento já preenchendo o ID VGR e disparando o carregamento.
 * @param {string} idVgr - O ID VGR da unidade.
 */
async function openCreateWithVgr(idVgr) {
  await openCreateModal();
  const el = document.getElementById("createIdVgr");
  if (el) {
    el.value = idVgr;
    // Dispara o evento blur para que a lógica existente de carregamento via ID VGR seja executada
    el.dispatchEvent(new Event('blur'));
  }
}

/**
 * Visualiza os dados da unidade e conectividade (pré-carregamento) quando não há atendimento.
 * @param {string} idVgr - O ID VGR da unidade.
 */
function viewUnitOnly(idVgr) {
  fetch(`/prodesp/unidades/${encodeURIComponent(idVgr)}`)
    .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
    .then(json => {
      if (!json.success) throw new Error(json.message);
      const u = json.unidade;

      const viewTitleEl = document.querySelector("#viewModal .modal-title");
      if (viewTitleEl) {
        viewTitleEl.innerHTML =
          '<i class="fas fa-eye me-2"></i>Pré-visualização da Unidade';
      }

      // Objeto fake para preencher os campos da unidade no modal de visualização
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
        observacoes: u.observacoes || [],
        equipamentos: u.equipamentos || [],
        links: u.links || [],
        ip_lan_01: u.ip_lan_01 || "",
      };

      fillModalFields(d, 'view');

      const obsContainer = document.getElementById("log-observacao-view");
      obsContainer.innerHTML =
        '<div class="titles-incident"><span>DATA</span><span>OBSERVAÇÕES</span></div>';
      if (u.observacoes && u.observacoes.length > 0) {
        u.observacoes.forEach((obs) => {
          const card = document.createElement("div");
          card.classList.add("card-incident");
          card.innerHTML = `
            <div class="fields">
              <div class="incident-data">${obs.timestamp || "-"}</div>
              <div class="incident-chamado">${prodespAttrEsc(obs.texto) || "-"}</div>
            </div>`;
          obsContainer.appendChild(card);
        });
      } else {
        obsContainer.innerHTML +=
          '<div class="text-muted p-2">Nenhuma observação registrada.</div>';
      }

      prodespPopulateEquipamentosViewList(
        document.getElementById("log-equipamento-view"),
        d.equipamentos,
        "Nenhum equipamento cadastrado."
      );

      prodespPopulateLinksViewList(
        document.getElementById("log-link-view"),
        d.links,
        "Nenhum link cadastrado."
      );

      document.getElementById("log-marcos-view").innerHTML = '<div class="text-center text-muted p-3"><em>— Atendimento não iniciado —</em></div>';

      const idUnidade = u.id_unidade || u.id_unidades;
      if (idUnidade) {
        fetch(`/prodesp/historico_unidade/${idUnidade}`)
          .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
          .then((histU) => {
            const histEl = document.getElementById("log-historico-view");
            histEl.innerHTML = window.renderHistoricoCompleto(
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
              window.prodespBindHistoricoCollapseControls(histEl);
            }
          })
          .catch(() => {
            document.getElementById("log-historico-view").innerHTML =
              '<div class="text-muted ms-2 mt-2">Não foi possível carregar o histórico da unidade.</div>';
          });
      } else {
        document.getElementById("log-historico-view").innerHTML =
          '<div class="text-muted ms-2 mt-2">Unidade sem identificador para histórico.</div>';
      }

      prodespOpenModal(document.getElementById("viewModal"));
    })
    .catch(err => {
      console.error("Erro em viewUnitOnly:", err);
      showToast("Não foi possível carregar os dados da unidade.", "danger");
    });
}

function prodespIsoToDatetimeLocal(iso) {
  if (!iso) return "";
  const s = String(iso).trim();
  if (!s) return "";
  if (s.includes("T") && (s.includes("+") || s.endsWith("Z"))) {
    const dt = new Date(s);
    if (isNaN(dt.getTime())) return "";
    const p = (n) => String(n).padStart(2, "0");
    return `${dt.getFullYear()}-${p(dt.getMonth() + 1)}-${p(dt.getDate())}T${p(dt.getHours())}:${p(dt.getMinutes())}`;
  }
  const norm = s.replace(" ", "T");
  return norm.length >= 16 ? norm.slice(0, 16) : norm.slice(0, 10) + "T00:00";
}

function prodespDatetimeLocalToMysql(v) {
  if (!v) return null;
  const s = String(v).trim().replace("T", " ");
  if (s.length === 16) return s + ":00";
  return s;
}

function prodespAttrEsc(s) {
  if (s == null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function prodespRenderAdminStatusLogTbody(rows) {
  const tb = document.getElementById("tbodyAdminStatusLog");
  if (!tb) return;
  tb.innerHTML = (rows || [])
    .map((r) => {
      const id = r.id_log_atendimentos_status;
      const q = prodespIsoToDatetimeLocal(r.alterado_em_log);
      return (
        `<tr data-log-id="${id}">` +
        `<td class="align-middle small">${id}</td>` +
        `<td><select class="form-select form-select-sm admin-sl-tipo" data-id="${id}">` +
        `<option value="substatus"${r.tipo_campo_log === "substatus" ? " selected" : ""}>substatus</option>` +
        `<option value="status"${r.tipo_campo_log === "status" ? " selected" : ""}>status</option>` +
        `</select></td>` +
        `<td><input type="text" class="form-control form-control-sm admin-sl-ant" data-id="${id}" value="${prodespAttrEsc(r.valor_anterior_log)}" maxlength="50"/></td>` +
        `<td><input type="text" class="form-control form-control-sm admin-sl-novo" data-id="${id}" value="${prodespAttrEsc(r.valor_novo_log)}" maxlength="50"/></td>` +
        `<td><input type="datetime-local" class="form-control form-control-sm admin-sl-quando" data-id="${id}" value="${q}"/></td>` +
        `<td class="prodesp-admin-audit-col-acoes align-middle">` +
        `<div class="d-flex flex-wrap gap-1">` +
        `<button type="button" class="btn btn-sm btn-primary btn-admin-sl-save" data-id="${id}">Salvar</button>` +
        `<button type="button" class="btn btn-sm btn-outline-danger btn-admin-sl-del" data-id="${id}">Excluir</button>` +
        `</div></td></tr>`
      );
    })
    .join("");
}

function prodespRenderAdminHistoricoTbody(rows) {
  const tb = document.getElementById("tbodyAdminHistorico");
  if (!tb) return;
  tb.innerHTML = (rows || [])
    .map((r) => {
      const id = r.id_log_historico;
      const q = prodespIsoToDatetimeLocal(r.data_alteracao_historico);
      return (
        `<tr data-hist-id="${id}">` +
        `<td class="align-middle small">${id}</td>` +
        `<td><input type="datetime-local" class="form-control form-control-sm admin-h-quando" data-id="${id}" value="${q}"/></td>` +
        `<td><input type="text" class="form-control form-control-sm admin-h-re" data-id="${id}" value="${prodespAttrEsc(r.usuario_re_historico)}" maxlength="8"/></td>` +
        `<td><input type="text" class="form-control form-control-sm admin-h-nome" data-id="${id}" value="${prodespAttrEsc(r.usuario_nome_historico)}" maxlength="100"/></td>` +
        `<td><input type="text" class="form-control form-control-sm admin-h-campo" data-id="${id}" value="${prodespAttrEsc(r.campo_alterado_historico)}" maxlength="255"/></td>` +
        `<td><select class="form-select form-select-sm admin-h-op" data-id="${id}">` +
        ["INSERT", "UPDATE", "DELETE"]
          .map(
            (o) =>
              `<option value="${o}"${(r.operacao_historico || "").toUpperCase() === o ? " selected" : ""}>${o}</option>`
          )
          .join("") +
        `</select></td>` +
        `<td><textarea class="form-control form-control-sm admin-h-ant" data-id="${id}" rows="1">${prodespAttrEsc(r.valor_antigo_historico)}</textarea></td>` +
        `<td><textarea class="form-control form-control-sm admin-h-novo" data-id="${id}" rows="1">${prodespAttrEsc(r.valor_novo_historico)}</textarea></td>` +
        `<td class="prodesp-admin-audit-col-acoes align-middle">` +
        `<div class="d-flex flex-wrap gap-1">` +
        `<button type="button" class="btn btn-sm btn-primary btn-admin-h-save" data-id="${id}">Salvar</button>` +
        `<button type="button" class="btn btn-sm btn-outline-danger btn-admin-h-del" data-id="${id}">Excluir</button>` +
        `</div></td></tr>`
      );
    })
    .join("");
}

function prodespRenderAdminHistoricoUnidadeTbody(rows) {
  const tb = document.getElementById("tbodyAdminHistoricoUnidade");
  if (!tb) return;
  tb.innerHTML = (rows || [])
    .map((r) => {
      const id = r.id_log_historico;
      const q = prodespIsoToDatetimeLocal(r.data_alteracao_historico);
      return (
        `<tr data-hist-un-id="${id}">` +
        `<td class="align-middle small">${id}</td>` +
        `<td><input type="datetime-local" class="form-control form-control-sm admin-hu-quando" data-id="${id}" value="${q}"/></td>` +
        `<td><input type="text" class="form-control form-control-sm admin-hu-re" data-id="${id}" value="${prodespAttrEsc(r.usuario_re_historico)}" maxlength="8"/></td>` +
        `<td><input type="text" class="form-control form-control-sm admin-hu-nome" data-id="${id}" value="${prodespAttrEsc(r.usuario_nome_historico)}" maxlength="100"/></td>` +
        `<td><input type="text" class="form-control form-control-sm admin-hu-campo" data-id="${id}" value="${prodespAttrEsc(r.campo_alterado_historico)}" maxlength="255"/></td>` +
        `<td><select class="form-select form-select-sm admin-hu-op" data-id="${id}">` +
        ["INSERT", "UPDATE", "DELETE"]
          .map(
            (o) =>
              `<option value="${o}"${(r.operacao_historico || "").toUpperCase() === o ? " selected" : ""}>${o}</option>`
          )
          .join("") +
        `</select></td>` +
        `<td><textarea class="form-control form-control-sm admin-hu-ant" data-id="${id}" rows="1">${prodespAttrEsc(r.valor_antigo_historico)}</textarea></td>` +
        `<td><textarea class="form-control form-control-sm admin-hu-novo" data-id="${id}" rows="1">${prodespAttrEsc(r.valor_novo_historico)}</textarea></td>` +
        `<td class="prodesp-admin-audit-col-acoes align-middle">` +
        `<div class="d-flex flex-wrap gap-1">` +
        `<button type="button" class="btn btn-sm btn-primary btn-admin-hu-save" data-id="${id}">Salvar</button>` +
        `<button type="button" class="btn btn-sm btn-outline-danger btn-admin-hu-del" data-id="${id}">Excluir</button>` +
        `</div></td></tr>`
      );
    })
    .join("");
}

function prodespRenderAdminObservacoesTbody(rows) {
  const tb = document.getElementById("tbodyAdminObservacoes");
  if (!tb) return;
  tb.innerHTML = (rows || [])
    .map((r) => {
      const id = r.id;
      const q = prodespIsoToDatetimeLocal(r.timestamp_iso || r.timestamp);
      return (
        `<tr data-obs-id="${id}">` +
        `<td class="align-middle small">${id}</td>` +
        `<td class="align-middle"><span class="badge bg-${r.escopo === "atendimento" ? "primary" : "secondary"}">${r.escopo}</span></td>` +
        `<td><input type="datetime-local" class="form-control form-control-sm admin-obs-quando" data-id="${id}" value="${q}"/></td>` +
        `<td><textarea class="form-control form-control-sm admin-obs-texto" data-id="${id}" rows="2">${prodespAttrEsc(r.texto)}</textarea></td>` +
        `<td class="prodesp-admin-audit-col-acoes align-middle">` +
        `<div class="d-flex flex-wrap gap-1">` +
        `<button type="button" class="btn btn-sm btn-primary btn-admin-obs-save" data-id="${id}">Salvar</button>` +
        `<button type="button" class="btn btn-sm btn-outline-secondary btn-admin-obs-des" data-id="${id}" title="Remove vínculo com o atendimento">Desassoc.</button>` +
        `<button type="button" class="btn btn-sm btn-outline-danger btn-admin-obs-del" data-id="${id}">Excluir</button>` +
        `</div></td></tr>`
      );
    })
    .join("");
}

function prodespRenderAdminEquipamentosTbody(rows) {
  const tb = document.getElementById("tbodyAdminEquipamentos");
  if (!tb) return;
  tb.innerHTML = (rows || [])
    .map((r) => {
      const id = r.id;
      return (
        `<tr data-eq-id="${id}">` +
        `<td class="align-middle small">${id}</td>` +
        `<td><input type="text" class="form-control form-control-sm admin-eq-modelo" data-id="${id}" value="${prodespAttrEsc(r.modelo)}" maxlength="50"/></td>` +
        `<td><input type="text" class="form-control form-control-sm admin-eq-serial" data-id="${id}" value="${prodespAttrEsc(r.serial)}" maxlength="50"/></td>` +
        `<td><input type="text" class="form-control form-control-sm admin-eq-versao" data-id="${id}" value="${prodespAttrEsc(r.versao)}" maxlength="50"/></td>` +
        `<td><input type="text" class="form-control form-control-sm admin-eq-desc" data-id="${id}" value="${prodespAttrEsc(r.descricao)}" maxlength="255"/></td>` +
        `<td class="prodesp-admin-audit-col-acoes align-middle">` +
        `<div class="d-flex flex-wrap gap-1">` +
        `<button type="button" class="btn btn-sm btn-primary btn-admin-eq-save" data-id="${id}">Salvar</button>` +
        `<button type="button" class="btn btn-sm btn-outline-secondary btn-admin-eq-des" data-id="${id}">Desassoc.</button>` +
        `<button type="button" class="btn btn-sm btn-outline-danger btn-admin-eq-del" data-id="${id}">Excluir</button>` +
        `</div></td></tr>`
      );
    })
    .join("");
}

function prodespRenderAdminLinksTbody(rows) {
  const tb = document.getElementById("tbodyAdminLinks");
  if (!tb) return;
  tb.innerHTML = (rows || [])
    .map((r) => {
      const id = r.id;
      return (
        `<tr data-link-id="${id}">` +
        `<td class="align-middle small">${id}</td>` +
        `<td><input type="text" class="form-control form-control-sm admin-lnk-designador" data-id="${id}" value="${prodespAttrEsc(r.designador_links)}" maxlength="30"/></td>` +
        `<td><input type="text" class="form-control form-control-sm admin-lnk-tipo" data-id="${id}" value="${prodespAttrEsc(r.tipo_links)}" maxlength="100"/></td>` +
        `<td><input type="text" class="form-control form-control-sm admin-lnk-operadora" data-id="${id}" value="${prodespAttrEsc(r.operadora_links)}" maxlength="100"/></td>` +
        `<td><input type="text" class="form-control form-control-sm admin-lnk-vlan" data-id="${id}" value="${prodespAttrEsc(r.vlan_links)}" maxlength="10"/></td>` +
        `<td class="prodesp-admin-audit-col-acoes align-middle">` +
        `<div class="d-flex flex-wrap gap-1">` +
        `<button type="button" class="btn btn-sm btn-primary btn-admin-lnk-save" data-id="${id}">Salvar</button>` +
        `<button type="button" class="btn btn-sm btn-outline-secondary btn-admin-lnk-des" data-id="${id}">Desassoc.</button>` +
        `<button type="button" class="btn btn-sm btn-outline-danger btn-admin-lnk-del" data-id="${id}">Excluir</button>` +
        `</div></td></tr>`
      );
    })
    .join("");
}

async function prodespLoadAdminAuditTab(atendimentoId) {
  if (
    parseInt(String(typeof LOGGED_IN_USER_ADMIN !== "undefined" ? LOGGED_IN_USER_ADMIN : 0), 10) !== 1
  )
    return;
  const tbSl = document.getElementById("tbodyAdminStatusLog");
  if (!tbSl) return;
  prodespAdminAuditClearDirty();
  try {
    const res = await fetch(`/prodesp/api/admin/atendimento/${atendimentoId}/auditoria`);
    const data = await res.json();
    if (!res.ok) {
      showToast(data.message || "Erro ao carregar auditoria.", "danger");
      return;
    }
    window.prodespAdminAuditUnidadeId = data.id_unidade;
    prodespRenderAdminStatusLogTbody(data.status_log);
    prodespRenderAdminHistoricoTbody(data.historico_atendimento || data.historico);
    prodespRenderAdminHistoricoUnidadeTbody(data.historico_unidade);
    prodespRenderAdminObservacoesTbody(data.observacoes);
    prodespRenderAdminEquipamentosTbody(data.equipamentos);
    prodespRenderAdminLinksTbody(data.links);
  } catch (e) {
    console.error(e);
    showToast("Erro ao carregar auditoria.", "danger");
  }
}

function initProdespAdminAuditUi() {
  if (
    parseInt(String(typeof LOGGED_IN_USER_ADMIN !== "undefined" ? LOGGED_IN_USER_ADMIN : 0), 10) !== 1
  )
    return;

  document.getElementById("btnAdminAuditReload")?.addEventListener("click", () => {
    const id = document.getElementById("editAtendimentoId")?.value;
    if (id) prodespLoadAdminAuditTab(parseInt(id, 10));
  });

  document.getElementById("edit-admin-audit-tab")?.addEventListener("shown.bs.tab", () => {
    const id = document.getElementById("editAtendimentoId")?.value;
    if (id) prodespLoadAdminAuditTab(parseInt(id, 10));
  });

  document.getElementById("adminAuditMultiEdit")?.addEventListener("change", () => {
    prodespAdminAuditClearDirty();
  });

  const auditPane = document.getElementById("edit-admin-audit-pane");
  auditPane?.addEventListener("focusin", (ev) => {
    const tr = ev.target.closest("tr");
    if (!tr || !ev.target.matches("input, textarea, select")) return;
    if (tr.dataset.logId) prodespAdminAuditMarkDirty("sl", tr.dataset.logId);
    else if (tr.dataset.histId) prodespAdminAuditMarkDirty("hist", tr.dataset.histId);
    else if (tr.dataset.histUnId) prodespAdminAuditMarkDirty("hist-u", tr.dataset.histUnId);
    else if (tr.dataset.obsId) prodespAdminAuditMarkDirty("obs", tr.dataset.obsId);
    else if (tr.dataset.eqId) prodespAdminAuditMarkDirty("eq", tr.dataset.eqId);
    else if (tr.dataset.linkId) prodespAdminAuditMarkDirty("link", tr.dataset.linkId);
  });

  const tbodySl = document.getElementById("tbodyAdminStatusLog");
  if (tbodySl) {
    tbodySl.addEventListener("click", async (ev) => {
      const idAtt = document.getElementById("editAtendimentoId")?.value;
      if (!idAtt) return;
      const aid = parseInt(idAtt, 10);
      const t = ev.target;
      if (t.classList.contains("btn-admin-sl-save")) {
        const lid = parseInt(t.getAttribute("data-id"), 10);
        if (!prodespAdminAuditCanSave("sl", lid)) return;
        const tr = tbodySl.querySelector(`tr[data-log-id="${lid}"]`);
        if (!tr) return;
        const body = {
          tipo_campo_log: tr.querySelector(".admin-sl-tipo")?.value,
          valor_anterior_log: tr.querySelector(".admin-sl-ant")?.value,
          valor_novo_log: tr.querySelector(".admin-sl-novo")?.value,
          alterado_em_log: prodespDatetimeLocalToMysql(tr.querySelector(".admin-sl-quando")?.value),
        };
        const res = await fetch(`/prodesp/api/admin/atendimento/${aid}/status_log/${lid}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const j = await res.json();
        if (!res.ok) {
          showToast(j.message || "Erro ao salvar.", "danger");
          return;
        }
        showToast("Registro de status_log atualizado.", "success");
        prodespAdminAuditClearDirty();
        prodespLoadAdminAuditTab(aid);
      }
      if (t.classList.contains("btn-admin-sl-del")) {
        if (!confirm("Excluir este registro de status_log?")) return;
        const lid = parseInt(t.getAttribute("data-id"), 10);
        const res = await fetch(`/prodesp/api/admin/atendimento/${aid}/status_log/${lid}`, {
          method: "DELETE",
        });
        const j = await res.json().catch(() => ({}));
        if (!res.ok) {
          showToast(j.message || "Erro ao excluir.", "danger");
          return;
        }
        showToast("Registro excluído.", "success");
        prodespLoadAdminAuditTab(aid);
      }
    });
  }

  document.getElementById("btnAdminSlInsert")?.addEventListener("click", async () => {
    const idAtt = document.getElementById("editAtendimentoId")?.value;
    if (!idAtt) return;
    const aid = parseInt(idAtt, 10);
    const body = {
      tipo_campo_log: document.getElementById("adminSlTipoNew")?.value,
      valor_anterior_log: document.getElementById("adminSlAntNew")?.value,
      valor_novo_log: document.getElementById("adminSlNovoNew")?.value,
      alterado_em_log: prodespDatetimeLocalToMysql(document.getElementById("adminSlQuandoNew")?.value),
    };
    const res = await fetch(`/prodesp/api/admin/atendimento/${aid}/status_log`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await res.json();
    if (!res.ok) {
      showToast(j.message || "Erro ao inserir.", "danger");
      return;
    }
    showToast("Registro inserido.", "success");
    prodespLoadAdminAuditTab(aid);
  });

  const tbodyH = document.getElementById("tbodyAdminHistorico");
  if (tbodyH) {
    tbodyH.addEventListener("click", async (ev) => {
      const idAtt = document.getElementById("editAtendimentoId")?.value;
      if (!idAtt) return;
      const aid = parseInt(idAtt, 10);
      const t = ev.target;
      if (t.classList.contains("btn-admin-h-save")) {
        const hid = parseInt(t.getAttribute("data-id"), 10);
        if (!prodespAdminAuditCanSave("hist", hid)) return;
        const tr = tbodyH.querySelector(`tr[data-hist-id="${hid}"]`);
        if (!tr) return;
        const body = {
          data_alteracao_historico: prodespDatetimeLocalToMysql(tr.querySelector(".admin-h-quando")?.value),
          usuario_re_historico: tr.querySelector(".admin-h-re")?.value,
          usuario_nome_historico: tr.querySelector(".admin-h-nome")?.value,
          campo_alterado_historico: tr.querySelector(".admin-h-campo")?.value,
          operacao_historico: tr.querySelector(".admin-h-op")?.value,
          valor_antigo_historico: tr.querySelector(".admin-h-ant")?.value,
          valor_novo_historico: tr.querySelector(".admin-h-novo")?.value,
        };
        const res = await fetch(`/prodesp/api/admin/atendimento/${aid}/historico/${hid}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const j = await res.json();
        if (!res.ok) {
          showToast(j.message || "Erro ao salvar.", "danger");
          return;
        }
        showToast("Histórico atualizado.", "success");
        prodespAdminAuditClearDirty();
        prodespLoadAdminAuditTab(aid);
      }
      if (t.classList.contains("btn-admin-h-del")) {
        if (!confirm("Excluir este registro de histórico?")) return;
        const hid = parseInt(t.getAttribute("data-id"), 10);
        const res = await fetch(`/prodesp/api/admin/atendimento/${aid}/historico/${hid}`, {
          method: "DELETE",
        });
        const j = await res.json().catch(() => ({}));
        if (!res.ok) {
          showToast(j.message || "Erro ao excluir.", "danger");
          return;
        }
        showToast("Registro excluído.", "success");
        prodespAdminAuditClearDirty();
        prodespLoadAdminAuditTab(aid);
      }
    });
  }

  const tbodyHu = document.getElementById("tbodyAdminHistoricoUnidade");
  if (tbodyHu) {
    tbodyHu.addEventListener("click", async (ev) => {
      const idAtt = document.getElementById("editAtendimentoId")?.value;
      if (!idAtt) return;
      const aid = parseInt(idAtt, 10);
      const t = ev.target;
      if (t.classList.contains("btn-admin-hu-save")) {
        const hid = parseInt(t.getAttribute("data-id"), 10);
        if (!prodespAdminAuditCanSave("hist-u", hid)) return;
        const tr = tbodyHu.querySelector(`tr[data-hist-un-id="${hid}"]`);
        if (!tr) return;
        const body = {
          data_alteracao_historico: prodespDatetimeLocalToMysql(tr.querySelector(".admin-hu-quando")?.value),
          usuario_re_historico: tr.querySelector(".admin-hu-re")?.value,
          usuario_nome_historico: tr.querySelector(".admin-hu-nome")?.value,
          campo_alterado_historico: tr.querySelector(".admin-hu-campo")?.value,
          operacao_historico: tr.querySelector(".admin-hu-op")?.value,
          valor_antigo_historico: tr.querySelector(".admin-hu-ant")?.value,
          valor_novo_historico: tr.querySelector(".admin-hu-novo")?.value,
        };
        const res = await fetch(`/prodesp/api/admin/atendimento/${aid}/historico_unidade/${hid}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const j = await res.json();
        if (!res.ok) {
          showToast(j.message || "Erro ao salvar.", "danger");
          return;
        }
        showToast("Histórico da unidade atualizado.", "success");
        prodespAdminAuditClearDirty();
        prodespLoadAdminAuditTab(aid);
      }
      if (t.classList.contains("btn-admin-hu-del")) {
        if (!confirm("Excluir este registro de histórico da unidade?")) return;
        const hid = parseInt(t.getAttribute("data-id"), 10);
        const res = await fetch(`/prodesp/api/admin/atendimento/${aid}/historico_unidade/${hid}`, {
          method: "DELETE",
        });
        const j = await res.json().catch(() => ({}));
        if (!res.ok) {
          showToast(j.message || "Erro ao excluir.", "danger");
          return;
        }
        showToast("Registro excluído.", "success");
        prodespAdminAuditClearDirty();
        prodespLoadAdminAuditTab(aid);
      }
    });
  }

  document.getElementById("btnAdminHistUnInsert")?.addEventListener("click", async () => {
    const uid = window.prodespAdminAuditUnidadeId;
    if (!uid) {
      showToast("Unidade não carregada. Recarregue a auditoria.", "warning");
      return;
    }
    const body = {
      data_alteracao_historico: prodespDatetimeLocalToMysql(
        document.getElementById("adminHistUnQuandoNew")?.value
      ),
      usuario_re_historico: document.getElementById("adminHistUnReNew")?.value,
      usuario_nome_historico: document.getElementById("adminHistUnNomeNew")?.value,
      campo_alterado_historico: document.getElementById("adminHistUnCampoNew")?.value,
      operacao_historico: document.getElementById("adminHistUnOpNew")?.value,
      valor_antigo_historico: document.getElementById("adminHistUnAntNew")?.value,
      valor_novo_historico: document.getElementById("adminHistUnNovoNew")?.value,
    };
    const res = await fetch(`/prodesp/api/admin/unidade/${uid}/historico`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await res.json();
    if (!res.ok) {
      showToast(j.message || "Erro ao inserir.", "danger");
      return;
    }
    const idAtt = document.getElementById("editAtendimentoId")?.value;
    if (idAtt) prodespLoadAdminAuditTab(parseInt(idAtt, 10));
    showToast("Histórico da unidade inserido.", "success");
  });

  const bindAdminEntityTable = (tbodyId, handlers) => {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    tbody.addEventListener("click", async (ev) => {
      const idAtt = document.getElementById("editAtendimentoId")?.value;
      if (!idAtt) return;
      const aid = parseInt(idAtt, 10);
      const t = ev.target;
      for (const h of handlers) {
        if (t.classList.contains(h.cls)) {
          await h.fn(aid, parseInt(t.getAttribute("data-id"), 10), t, tbody);
          return;
        }
      }
    });
  };

  bindAdminEntityTable("tbodyAdminObservacoes", [
    {
      cls: "btn-admin-obs-save",
      fn: async (aid, oid, _t, tbody) => {
        if (!prodespAdminAuditCanSave("obs", oid)) return;
        const tr = tbody.querySelector(`tr[data-obs-id="${oid}"]`);
        const body = {
          texto: tr.querySelector(".admin-obs-texto")?.value,
          timestamp: prodespDatetimeLocalToMysql(tr.querySelector(".admin-obs-quando")?.value),
        };
        const res = await fetch(`/prodesp/api/admin/atendimento/${aid}/observacoes/${oid}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const j = await res.json();
        if (!res.ok) {
          showToast(j.message || "Erro ao salvar.", "danger");
          return;
        }
        showToast("Observação atualizada.", "success");
        prodespAdminAuditClearDirty();
        prodespLoadAdminAuditTab(aid);
      },
    },
    {
      cls: "btn-admin-obs-des",
      fn: async (aid, oid) => {
        if (!confirm("Desassociar observação do atendimento (mantém na unidade)?")) return;
        const res = await fetch(`/prodesp/api/admin/atendimento/${aid}/observacoes/${oid}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ desassociar_atendimento: true }),
        });
        const j = await res.json();
        if (!res.ok) {
          showToast(j.message || "Erro.", "danger");
          return;
        }
        showToast(j.message || "Observação desassociada.", "success");
        prodespLoadAdminAuditTab(aid);
      },
    },
    {
      cls: "btn-admin-obs-del",
      fn: async (aid, oid) => {
        if (!confirm("Excluir observação permanentemente?")) return;
        const res = await fetch(`/prodesp/api/admin/atendimento/${aid}/observacoes/${oid}`, {
          method: "DELETE",
        });
        const j = await res.json().catch(() => ({}));
        if (!res.ok) {
          showToast(j.message || "Erro ao excluir.", "danger");
          return;
        }
        showToast("Observação excluída.", "success");
        prodespLoadAdminAuditTab(aid);
      },
    },
  ]);

  bindAdminEntityTable("tbodyAdminEquipamentos", [
    {
      cls: "btn-admin-eq-save",
      fn: async (aid, eid, _t, tbody) => {
        if (!prodespAdminAuditCanSave("eq", eid)) return;
        const tr = tbody.querySelector(`tr[data-eq-id="${eid}"]`);
        const body = {
          modelo: tr.querySelector(".admin-eq-modelo")?.value,
          serial: tr.querySelector(".admin-eq-serial")?.value,
          versao: tr.querySelector(".admin-eq-versao")?.value,
          descricao: tr.querySelector(".admin-eq-desc")?.value,
        };
        const res = await fetch(`/prodesp/api/admin/atendimento/${aid}/equipamentos/${eid}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const j = await res.json();
        if (!res.ok) {
          showToast(j.message || "Erro ao salvar.", "danger");
          return;
        }
        showToast("Equipamento atualizado.", "success");
        prodespAdminAuditClearDirty();
        prodespLoadAdminAuditTab(aid);
      },
    },
    {
      cls: "btn-admin-eq-des",
      fn: async (aid, eid) => {
        if (!confirm("Desassociar equipamento da unidade?")) return;
        const res = await fetch(`/prodesp/api/admin/atendimento/${aid}/equipamentos/${eid}`, {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ desassociar: true }),
        });
        const j = await res.json();
        if (!res.ok) {
          showToast(j.message || "Erro.", "danger");
          return;
        }
        showToast("Equipamento desassociado.", "success");
        prodespLoadAdminAuditTab(aid);
      },
    },
    {
      cls: "btn-admin-eq-del",
      fn: async (aid, eid) => {
        if (!confirm("Excluir equipamento permanentemente?")) return;
        const res = await fetch(`/prodesp/api/admin/atendimento/${aid}/equipamentos/${eid}`, {
          method: "DELETE",
        });
        const j = await res.json().catch(() => ({}));
        if (!res.ok) {
          showToast(j.message || "Erro ao excluir.", "danger");
          return;
        }
        showToast("Equipamento excluído.", "success");
        prodespLoadAdminAuditTab(aid);
      },
    },
  ]);

  bindAdminEntityTable("tbodyAdminLinks", [
    {
      cls: "btn-admin-lnk-save",
      fn: async (aid, lid, _t, tbody) => {
        if (!prodespAdminAuditCanSave("link", lid)) return;
        const tr = tbody.querySelector(`tr[data-link-id="${lid}"]`);
        const body = {
          designador: tr.querySelector(".admin-lnk-designador")?.value,
          tipo: tr.querySelector(".admin-lnk-tipo")?.value,
          operadora: tr.querySelector(".admin-lnk-operadora")?.value,
          vlan: tr.querySelector(".admin-lnk-vlan")?.value,
        };
        const res = await fetch(`/prodesp/api/admin/atendimento/${aid}/links/${lid}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const j = await res.json();
        if (!res.ok) {
          showToast(j.message || "Erro ao salvar.", "danger");
          return;
        }
        showToast("Link atualizado.", "success");
        prodespAdminAuditClearDirty();
        prodespLoadAdminAuditTab(aid);
      },
    },
    {
      cls: "btn-admin-lnk-des",
      fn: async (aid, lid) => {
        if (!confirm("Desassociar link da unidade?")) return;
        const res = await fetch(`/prodesp/api/admin/atendimento/${aid}/links/${lid}`, {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ desassociar: true }),
        });
        const j = await res.json();
        if (!res.ok) {
          showToast(j.message || "Erro.", "danger");
          return;
        }
        showToast("Link desassociado.", "success");
        prodespLoadAdminAuditTab(aid);
      },
    },
    {
      cls: "btn-admin-lnk-del",
      fn: async (aid, lid) => {
        if (!confirm("Excluir link permanentemente?")) return;
        const res = await fetch(`/prodesp/api/admin/atendimento/${aid}/links/${lid}`, {
          method: "DELETE",
        });
        const j = await res.json().catch(() => ({}));
        if (!res.ok) {
          showToast(j.message || "Erro ao excluir.", "danger");
          return;
        }
        showToast("Link excluído.", "success");
        prodespLoadAdminAuditTab(aid);
      },
    },
  ]);

  document.getElementById("btnAdminHistInsert")?.addEventListener("click", async () => {
    const idAtt = document.getElementById("editAtendimentoId")?.value;
    if (!idAtt) return;
    const aid = parseInt(idAtt, 10);
    const body = {
      data_alteracao_historico: prodespDatetimeLocalToMysql(
        document.getElementById("adminHistQuandoNew")?.value
      ),
      usuario_re_historico: document.getElementById("adminHistReNew")?.value,
      usuario_nome_historico: document.getElementById("adminHistNomeNew")?.value,
      campo_alterado_historico: document.getElementById("adminHistCampoNew")?.value,
      operacao_historico: document.getElementById("adminHistOpNew")?.value,
      valor_antigo_historico: document.getElementById("adminHistAntNew")?.value,
      valor_novo_historico: document.getElementById("adminHistNovoNew")?.value,
    };
    const res = await fetch(`/prodesp/api/admin/atendimento/${aid}/historico`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await res.json();
    if (!res.ok) {
      showToast(j.message || "Erro ao inserir.", "danger");
      return;
    }
    showToast("Histórico inserido.", "success");
    prodespLoadAdminAuditTab(aid);
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initProdespAdminAuditUi);
} else {
  initProdespAdminAuditUi();
}

// ------------------------------
// REDEFINE window para onclick
// ------------------------------
window.viewDetails = viewDetails;
window.editDetails = editDetails;
window.saveEdit = saveEdit;
window.openCreateWithVgr = openCreateWithVgr;
window.viewUnitOnly = viewUnitOnly;
window.prodespPopulateEquipamentosViewList = prodespPopulateEquipamentosViewList;
window.prodespPopulateLinksViewList = prodespPopulateLinksViewList;
