(function () {
  "use strict";

  const V = window.VgrDt;
  if (!V || typeof $ === "undefined" || !$.fn.DataTable) return;

  const modo = window.VGR_ATEND_MODO || "operacao";
  const actor = window.VGR_ACTOR || {};
  const actorLabel = (actor.nome || actor.re || "").trim();
  const PF = window.PortalFieldValidation || null;
  /* Regras de campo VGR (vgr_field_rules.js): mesmas do modal da unidade e da API. */
  const R = window.VgrFieldRules || null;

  const modalEl = document.getElementById("modalVgrAtend");
  const modal = modalEl && window.bootstrap ? new bootstrap.Modal(modalEl) : null;
  const modalViewEl = document.getElementById("modalVgrAtendView");
  const modalView = modalViewEl && window.bootstrap ? new bootstrap.Modal(modalViewEl) : null;

  const errEl = document.getElementById("vgrAtendErro");
  const cc = window.PortalDt ? window.PortalDt.ccSearchList() : [];

  let catalogo = {
    status: [],
    substatus_por_status: {}
  };
  let unidadesCache = [];
  let eqCache = [];
  /* Linha da unidade carregada no painel (GET /vgr/api/unidades/<id>). */
  let vgrUnidadeAtual = null;

  /* Campos da unidade editáveis (mesmos da view Unidades) — auto-save. */
  const VGR_UNI_EDIT_IDS = [
    "vgrAtendNomeUni",
    "vgrAtendCnpjUni",
    "vgrAtendCliente",
    "vgrAtendContatoUni",
    "vgrAtendCodigoUni",
    "vgrAtendTipoUni",
    "vgrAtendTipoProjeto",
    "vgrAtendTopologia",
    "vgrAtendHa",
    "vgrAtendEndereco",
    "vgrAtendBairro",
    "vgrAtendCidade",
    "vgrAtendUf",
    "vgrAtendCep",
    "vgrAtendLatitude",
    "vgrAtendLongitude"
  ];
  /* Travados até o início do atendimento (mesma regra de eq/links/conectividade). */
  const VGR_UNI_LOCK_IDS = VGR_UNI_EDIT_IDS.concat(["btnVgrAtendCompletarEndereco"]);
  /* Dados Field — auto-save. */
  const VGR_FIELD_EDIT_IDS = ["vgrAtendFieldNome", "vgrAtendFieldTel", "vgrAtendFieldContratada"];

  const VGR_UNI_STATUS_PADRAO =
    "Os dados da unidade são salvos automaticamente ao sair de cada campo.";
  const VGR_FIELD_STATUS_PADRAO =
    "Os Dados Field são salvos automaticamente ao sair de cada campo.";

  function vgrSetStatusEl(id, text, kind) {
    var el = document.getElementById(id);
    if (!el) return;
    el.textContent = text || "";
    el.classList.remove("text-danger", "text-success", "text-warning", "text-muted");
    el.classList.add(
      kind === "error" ? "text-danger"
        : kind === "ok" ? "text-success"
        : kind === "warn" ? "text-warning"
        : "text-muted"
    );
  }
  function vgrSetUniStatus(text, kind) {
    vgrSetStatusEl("vgrAtendUniStatus", text, kind);
  }
  function vgrSetFieldStatus(text, kind) {
    vgrSetStatusEl("vgrAtendFieldStatus", text, kind);
  }
  function vgrHoraAgora() {
    return new Date().toLocaleTimeString("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    });
  }

  /** Seleciona o valor; se não existir entre as opções (ex.: cliente inativo,
      valor legado), cria a opção para não exibir em branco. */
  function vgrSelectSetValue(sel, value, label) {
    if (typeof sel === "string") sel = document.getElementById(sel);
    if (!sel) return;
    var v = value != null ? String(value) : "";
    var existe = Array.prototype.some.call(sel.options, function (o) {
      return o.value === v;
    });
    if (v && !existe) sel.add(new Option(label || v, v));
    sel.value = v;
  }

  /**
   * Auto-save com debounce + fila (uma gravação por vez) + pendência.
   * cfg.run() → Promise<boolean>: true = gravado (ou nada a gravar);
   * false = não gravou (validação/API) e a pendência é mantida.
   */
  function vgrCriarAutoSave(cfg) {
    var timer = null;
    var running = null;
    var dirty = false;
    var again = false;

    function exec() {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      if (running) {
        again = true; /* alteração durante a gravação: roda de novo ao terminar */
        return running;
      }
      if (!dirty) return Promise.resolve(true);
      dirty = false;
      running = Promise.resolve()
        .then(cfg.run)
        .then(
          function (ok) {
            if (ok === false) dirty = true;
            return ok !== false;
          },
          function (e) {
            console.error("[VGR] auto-save:", e);
            dirty = true;
            return false;
          }
        )
        .then(function (ok) {
          running = null;
          if (again) {
            again = false;
            return exec();
          }
          return ok;
        });
      return running;
    }

    return {
      /** Marca pendência sem agendar (digitação em curso). */
      mark: function () {
        dirty = true;
      },
      /** Agenda a gravação (debounce). */
      schedule: function () {
        dirty = true;
        if (timer) clearTimeout(timer);
        timer = setTimeout(exec, cfg.delay || 600);
      },
      /** Grava agora o que estiver pendente. Resolve true/false. */
      flush: function () {
        return exec();
      },
      pending: function () {
        return dirty || !!timer || !!running;
      },
      /** Há alteração mais nova que a gravação em curso? */
      hasNewer: function () {
        return dirty || !!timer || again;
      },
      reset: function () {
        if (timer) clearTimeout(timer);
        timer = null;
        dirty = false;
        again = false;
      }
    };
  }

  const vgrUniAuto = vgrCriarAutoSave({
    delay: 600,
    run: function () {
      return vgrAutoSalvarUnidade();
    }
  });
  const vgrFieldAuto = vgrCriarAutoSave({
    delay: 600,
    run: function () {
      return vgrAutoSalvarField();
    }
  });

  let currentFieldId = null;
  let viewAtendId = null;
  let autoSaveDirty = false;

  const FINAIS = {
  "Concluído": 1,
  "Concluído Parcial": 1,
  "Quebra": 1
  };

  /* Cards da fila: status base dos contadores/filtros. */
  const STATUS_AGENDADO = "Agendado";
  const STATUS_FILA = "Em Atendimento";
  /* Substatus sintético (padrão PRODESP): agenda publicada sem atividade iniciada. */
  const SUBSTATUS_SEM_ATENDIMENTO = "Sem atendimento Iniciado";

  /**
   * Padrão PRODESP: um agendamento publicado ("Agendado") cujo atendimento
   * ainda não foi iniciado é tratado como fase de preparação.
   */
  function vgrRowIsAgendado(row) {
    if (!row) return false;
    var stAgend = (row.status_agendamento || "").trim();
    if (stAgend !== STATUS_AGENDADO) return false;
    var semId =
      row.id_atendimento === null ||
      row.id_atendimento === undefined ||
      row.id_atendimento === "";
    var iniciado = Number(row.atendimento_iniciado || 0) === 1;
    /* Sem atendimento vinculado OU atendimento ainda não iniciado. */
    return semId || !iniciado;
  }

  const VGR_SORT_FAIXA = 1e11;      /* largura de cada faixa */
  const VGR_SORT_SPAN_DATA = 1e10;  /* linhas com data_atendimento */
  const VGR_SORT_SEM_DATA = 2e10;   /* sem data_atendimento (após as datadas) */
  const VGR_SORT_SEM_NADA = 3e10;   /* sem data alguma (último da faixa) */

  /** Epoch em segundos (fuso local) a partir de data + hora opcional. */
  function vgrTsSegundos(dataStr, horaStr) {
    var dt = vgrParseDateLocal(dataStr);
    if (!dt) return null;
    var hm = /[T\s](\d{1,2}):(\d{2})(?::(\d{2}))?/.exec(String(dataStr || ""));
    if (!hm && horaStr) {
      hm = /^(\d{1,2}):(\d{2})(?::(\d{2}))?/.exec(String(horaStr).trim());
    }
    if (hm) dt.setHours(Number(hm[1]), Number(hm[2]), Number(hm[3] || 0), 0);
    return Math.floor(dt.getTime() / 1000);
  }

  function vgrSortFaixa(row) {
    var st = (row.status_atendimento || "").trim();
    var semId =
      row.id_atendimento === null ||
      row.id_atendimento === undefined ||
      row.id_atendimento === "";
    if (st === STATUS_FILA) return 0;
    if (semId || st === STATUS_AGENDADO) return 1;
    return 2;
  }

  function vgrSortKeyLista(row) {
    var faixa = vgrSortFaixa(row);
    var dentro;

    /* data_atendimento DESC, horario_inicio DESC */
    var tsAtend = vgrTsSegundos(
      row.data_atendimento,
      row.horario_inicio || row.hora_inicio || null
    );
    if (tsAtend !== null) {
      dentro = VGR_SORT_SPAN_DATA - tsAtend;
    } else {
      /* NULL em DESC vai para o fim; desempate pela agenda (ASC) */
      var tsAgenda = vgrTsSegundos(row.data_agendamento, row.hora_agendamento);
      dentro = tsAgenda !== null ? VGR_SORT_SEM_DATA + tsAgenda : VGR_SORT_SEM_NADA;
    }
    return faixa * VGR_SORT_FAIXA + dentro;
  }

  function vgrNormalizeAtendimentoListRow(row) {
    var r = row && typeof row === "object" ? Object.assign({}, row) : {};
    if (vgrRowIsAgendado(r)) {
      r.status_atendimento = STATUS_AGENDADO;
      r.substatus_atendimento = SUBSTATUS_SEM_ATENDIMENTO;
    }
    r._sort_lista = vgrSortKeyLista(r);
    return r;
  }

  let kpiFilter = null;
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

  function setVal(id, value) {
    var el = document.getElementById(id);
    if (!el) {
      console.warn("[VGR] Campo ausente no DOM (ignorado): #" + id);
      return;
    }
    el.value = value != null && value !== "" ? String(value) : "";
  }

  function fillSelect(el, values, selected, options) {
    options = options || {};
    if (!el) return;
    el.innerHTML = "";
    if (options.emptyLabel) {
      var emptyOpt = document.createElement("option");
      emptyOpt.value = "";
      emptyOpt.textContent = options.emptyLabel;
      if (!selected) emptyOpt.selected = true;
      el.appendChild(emptyOpt);
    }
    (values || []).forEach(function (v) {
      var opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      if (String(v) === String(selected || "")) opt.selected = true;
      el.appendChild(opt);
    });
  }

  function updateSubstatusByStatus(selectedStatus, selectedSubstatus) {
    var sel = document.getElementById("vgrAtendSub");
    if (!sel) return;
    var lista = (catalogo.substatus_por_status || {})[selectedStatus] || [];
    fillSelect(sel, lista, selectedSubstatus || "", {
      emptyLabel: "Selecione o substatus"
    });
  }

  function currentUnidadeId() {
    return document.getElementById("vgrAtendUnidade").value || "";
  }

  function clearUnidadePainel() {
    [
      "vgrAtendTipoUni",
      "vgrAtendTipoProjeto",
      "vgrAtendCodigoUni",
      "vgrAtendHa",
      "vgrAtendTopologia",
      "vgrAtendCliente",
      "vgrAtendNomeUni",
      "vgrAtendContatoUni",
      "vgrAtendEndereco",
      "vgrAtendBairro",
      "vgrAtendCidade",
      "vgrAtendUf",
      "vgrAtendCep",
      "vgrAtendLatitude",
      "vgrAtendLongitude",
      "vgrAtendCnpjUni",
      "vgrAtendHostResumo",
      "vgrAtendEqCount",
      "vgrAtendLinkCount",
      "vgrAtendIdVgr"
    ].forEach(function (id) {
      setVal(id, "");
    });
    vgrUnidadeAtual = null;
    vgrUniAuto.reset();
    vgrSetUniStatus(VGR_UNI_STATUS_PADRAO, "");
    if (R) R.clearStates(document.getElementById("vgrAtendUniForm"));
    eqCache = [];
    eqFixedForm = null;
    linkFixedForm = null;
    vgrSetFixedFormEmpty("vgrAtendEqFormGrid");
    vgrSetFixedFormEmpty("vgrAtendLinkFormGrid");
    ["vgrAtendEqList", "vgrAtendLinkList", "vgrAtendConnList"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.innerHTML = '<div class="text-muted p-2">Selecione uma unidade.</div>';
    });
  }

  /** Só escreve os valores (sem mexer no estado do auto-save). */
  function vgrPreencherCamposUnidade(d) {
    d = d || {};
    vgrSelectSetValue("vgrAtendCliente", d.id_cliente, d.razao_social);
    setVal("vgrAtendNomeUni", d.nome_unidade);
    setVal("vgrAtendCnpjUni", d.cnpj_unidade);
    setVal("vgrAtendContatoUni", d.contato_unidade);
    setVal("vgrAtendCodigoUni", d.codigo_unidade);
    vgrSelectSetValue("vgrAtendTipoUni", d.tipo_unidade || "FILIAL");
    vgrSelectSetValue("vgrAtendTipoProjeto", d.tipo_projeto || "PRATELEIRA");
    vgrSelectSetValue("vgrAtendTopologia", d.topologia_unidades || "");
    vgrSelectSetValue("vgrAtendHa", Number(d.ha) === 1 ? "1" : "0");
    setVal("vgrAtendEndereco", d.endereco);
    setVal("vgrAtendBairro", d.bairro);
    setVal("vgrAtendCidade", d.cidade);
    setVal("vgrAtendUf", d.uf);
    setVal("vgrAtendCep", d.cep);
    /* 0 é coordenada válida: setVal só trata null/"" como vazio */
    setVal("vgrAtendLatitude", d.latitude);
    setVal("vgrAtendLongitude", d.longitude);
    if (R) R.clearStates(document.getElementById("vgrAtendUniForm"));
    if (vgrUniLiveEnd) vgrUniLiveEnd.refresh();
  }

  function fillUnidadePainel(d) {
    d = d || {};
    var mesmaUnidade =
      vgrUnidadeAtual && String(vgrUnidadeAtual.id_unidade) === String(d.id_unidade);
    setVal("vgrAtendIdVgr", d.id_vgr);
    /* Recarga da mesma unidade (ex.: após salvar equipamento) com edição
       pendente: não sobrescreve o que está sendo digitado — o auto-save grava. */
    if (mesmaUnidade && vgrUniAuto.pending()) return;
    vgrUnidadeAtual = d;
    vgrUniAuto.reset();
    vgrPreencherCamposUnidade(d);
    vgrSetUniStatus(VGR_UNI_STATUS_PADRAO, "");
  }

  function renderEqLinksVgr(eqRows, linkRows) {
  var eqContainer = document.getElementById("vgrAtendEqList");
  var lkContainer = document.getElementById("vgrAtendLinkList");
  var connContainer = document.getElementById("vgrAtendConnList");

    eqCache = eqRows || [];
  linkCache = linkRows || [];

  var eqAtivos = eqCache.filter(function (r) {
    return Number(r.ativo) === 1;
  });
  var wanRows = (linkRows || []).filter(function (r) {
    return V.isLinkTipoWan(r.tipo_link);
  });
  var connRows = (linkRows || []).filter(function (r) {
    return V.isLinkTipoUnidade(r.tipo_link);
  });
  var wanAtivos = wanRows.filter(function (r) {
    return Number(r.ativo) === 1;
  });

  /* Mantém os resumos do painel da unidade */
  var eqCountEl = document.getElementById("vgrAtendEqCount");
  var lkCountEl = document.getElementById("vgrAtendLinkCount");
  var hostEl = document.getElementById("vgrAtendHostResumo");
  if (eqCountEl) eqCountEl.value = String(eqAtivos.length);
  if (lkCountEl) lkCountEl.value = String(wanAtivos.length);
  if (hostEl) {
    hostEl.value =
      (eqAtivos[0] && (eqAtivos[0].hostname || eqAtivos[0].serial)) || "";
  }

  /* --- Equipamentos (accordion) --- */
  if (eqContainer) {
    vgrResetIncidentListContainer(eqContainer);
    if (!eqCache.length) {
      eqContainer.innerHTML =
        '<div class="text-muted p-2">Nenhum equipamento.</div>';
    } else {
      eqCache.forEach(function (eq) {
        renderEqCardVgr(eq, eqContainer, eqCache, "edit");
      });
    }
  }

  /* --- Links WAN (accordion) --- */
  if (lkContainer) {
    vgrResetIncidentListContainer(lkContainer);
    if (!wanRows.length) {
      lkContainer.innerHTML =
        '<div class="text-muted p-2">Nenhum link WAN.</div>';
    } else {
      wanRows.forEach(function (link) {
        renderLinkCardVgr(link, lkContainer, wanRows, "edit", "wan");
      });
    }
  }

  /* --- Conectividade da unidade (accordion) --- */
  if (connContainer) {
    vgrResetIncidentListContainer(connContainer);
    if (!connRows.length) {
      connContainer.innerHTML =
        '<div class="text-muted p-2">Nenhuma conectividade da unidade.</div>';
    } else {
      connRows.forEach(function (link) {
        renderLinkCardVgr(link, connContainer, connRows, "edit", "unidade");
      });
    }
  }

  /* --- Formulários fixos (Dados Equipamentos / Dados Links): remontados limpos
         a cada recarga, com a lista de equipamentos atualizada --- */
  vgrMountEqForm();
  vgrMountLinkForm();
  }

  function loadUnidadeDetalhe(idUnidade) {
    if (!idUnidade) {
      clearUnidadePainel();
      return Promise.resolve();
    }
    return Promise.all([
      V.jsonFetch("/vgr/api/unidades/" + encodeURIComponent(idUnidade)),
      V.jsonFetch("/vgr/api/unidades/" + encodeURIComponent(idUnidade) + "/equipamentos"),
      V.jsonFetch("/vgr/api/unidades/" + encodeURIComponent(idUnidade) + "/links")
    ]).then(function (res) {
      if (res[0].status >= 400 || !res[0].d.success) {
        clearUnidadePainel();
        V.toast((res[0].d && res[0].d.message) || "Unidade não carregada.", false);
        return;
      }
      var eqs = (res[1].d && res[1].d.data) || [];
      var lks = (res[2].d && res[2].d.data) || [];
      /* Painel e inventário renderizados de forma isolada: uma falha de DOM
        em um bloco não pode impedir a renderização do outro. */
      try {
        fillUnidadePainel(res[0].d.data || {});
      } catch (e) {
        console.error("[VGR] Falha ao preencher painel da unidade:", e);
      }
      try {
        renderEqLinksVgr(eqs, lks);
      } catch (e) {
        console.error("[VGR] Falha ao renderizar equipamentos/links:", e);
      }
    }).catch(function (e) {
      console.error("[VGR] loadUnidadeDetalhe:", e);
      V.toast("Falha ao carregar detalhes da unidade.", false);
    });
  }

  function loadUnidades(selectedId) {
    return V.jsonFetch("/vgr/api/unidades").then(function (res) {
      unidadesCache = (res.d && res.d.data) || [];
      var sel = document.getElementById("vgrAtendUnidade");
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
            (r.razao_social ? " — " + r.razao_social : "");
          sel.appendChild(opt);
        });

      if (selectedId) sel.value = String(selectedId);
      return unidadesCache;
    });
  }

  function renderLogRows(tbodySel, rows, emptyMsg) {
    var body = document.querySelector(tbodySel);
    if (!body) return;

    if (!rows || !rows.length) {
      body.innerHTML =
        '<tr><td colspan="3" class="text-muted">' + (emptyMsg || "—") + "</td></tr>";
      return;
    }

    body.innerHTML = "";
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      [r.quando, r.quem, r.texto].forEach(function (cell) {
        var td = document.createElement("td");
        td.textContent = cell != null && cell !== "" ? String(cell) : "—";
        if (cell && String(cell).length > 200) {
          td.style.whiteSpace = "pre-wrap";
          td.style.fontSize = "0.8rem";
        }
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
  }

  function renderObsLog(rows, containerId, readonly) {
    var container = document.getElementById(containerId || "vgrAtendObsContainer");
    if (!container) return;
    container.innerHTML = "";

    if (!rows || !rows.length) {
      container.innerHTML = '<div class="text-muted p-2">Nenhuma observação.</div>';
      return;
    }

    rows.forEach(function (r) {
      var rowDiv = document.createElement("div");
      rowDiv.className = "d-flex mb-2 align-items-center";

      var dataInput = document.createElement("input");
      dataInput.type = "text";
      dataInput.className = "form-control form-control-sm text-center me-2";
      dataInput.style.width = "20%";
      dataInput.value = r.quando || "";
      dataInput.title = r.quem || "";
      dataInput.readOnly = true;

      var obsInput = document.createElement("input");
      obsInput.type = "text";
      obsInput.className = "form-control form-control-sm" + (readonly ? "" : " me-2");
      obsInput.style.width = "80%";
      obsInput.value = r.texto || "";
      obsInput.title = r.texto || "";
      obsInput.readOnly = true;

      rowDiv.appendChild(dataInput);
      rowDiv.appendChild(obsInput);

      /* Lixeira só fora do modo leitura */
      if (!readonly) {
        var btnDel = document.createElement("button");
        btnDel.className = "btn btn-sm btn-outline-danger";
        btnDel.innerHTML = '<i class="fas fa-trash"></i>';
        rowDiv.appendChild(btnDel);
      }

      container.appendChild(rowDiv);
    });
  }

  function vgrParseDateLocal(s) {
    if (!s) return null;
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s).trim());
    if (!m) return null;
    var d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    return isNaN(d.getTime()) ? null : d;
  }

  function formatAgendaQuando(d) {
    var dataBr = V.formatBrDate(d.data_agendamento);
    var hora = V.formatBrTime(d.hora_agendamento);
    var parts = [];

    if (dataBr && hora) parts.push(dataBr + " " + hora);
    else if (dataBr) parts.push(dataBr);
    else if (hora) parts.push(hora);

    if (d.hora_inicio || d.hora_fim) {
      parts.push(
        "(" +
          (d.hora_inicio ? V.formatBrTime(d.hora_inicio) : "?") +
          "–" +
          (d.hora_fim ? V.formatBrTime(d.hora_fim) : "?") +
          ")"
      );
    }

    return parts.join(" ");
  }

  /* ============================================================
   Fluxo de início de atendimento (espelho PRODESP):
   status único + campos bloqueados + modal Confirmar Dados Field
   ============================================================ */
/* Travados antes do início; liberados por vgrUiPostCreate(). Inclui os
   campos da unidade (auto-save só após o início do atendimento). */
const VGR_CREATE_LOCK_IDS = [
  "vgrAtendFieldNome",
  "vgrAtendFieldTel",
  "vgrAtendFieldContratada",
  "vgrAtendObsNova",
  "btnVgrAtendObsAdd",
  "btnVgrAtendEqNovo",
  "btnVgrAtendLinkNovo",
  "btnVgrAtendConnNovo"
].concat(VGR_UNI_LOCK_IDS);

/** Pré-create: placeholder + status único + tudo bloqueado (padrão PRODESP). */
function vgrUiPreCreate(hasUnidade) {
  var st = document.getElementById("vgrAtendStatus");
  var sub = document.getElementById("vgrAtendSub");
  if (st) {
    st.innerHTML = "";
    var ph = document.createElement("option");
    ph.value = "";
    ph.textContent = "Selecione o status...";
    ph.disabled = true;
    ph.selected = true;
    st.appendChild(ph);
    st.add(new Option("Em Atendimento", "Em Atendimento"));
    st.value = "";
    st.disabled = !hasUnidade;
  }
  if (sub) {
    sub.innerHTML = "";
    var phs = document.createElement("option");
    phs.value = "";
    phs.textContent = "Selecione o substatus...";
    phs.disabled = true;
    phs.selected = true;
    sub.appendChild(phs);
    sub.disabled = true;
  }
  VGR_CREATE_LOCK_IDS.forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.disabled = true;
  });
  var uni = document.getElementById("vgrAtendUnidade");
  var idv = document.getElementById("vgrAtendIdVgr");
  if (uni) uni.disabled = false;
  if (idv) idv.disabled = false;
}
/** Pós-create/edit: libera operação e trava a unidade (já vinculada). */
function vgrUiPostCreate() {
  var st = document.getElementById("vgrAtendStatus");
  var sub = document.getElementById("vgrAtendSub");
  if (st) {
    var cur = (st.value || "").trim() || "Em Atendimento";
    fillSelect(st, ["Em Atendimento", "Concluído Parcial", "Concluído", "Quebra"], cur);
    st.disabled = false;
  }
  if (sub) {
    sub.disabled = false;
    updateSubstatusByStatus(st ? st.value : "Em Atendimento", sub.value || "");
  }
  VGR_CREATE_LOCK_IDS.forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.disabled = false;
  });
  var uni = document.getElementById("vgrAtendUnidade");
  var idv = document.getElementById("vgrAtendIdVgr");
  if (uni) uni.disabled = true;
  if (idv) idv.disabled = true;
}
function vgrRefreshStatusAvailability() {
  if (document.getElementById("vgrAtendId").value) return;
  var st = document.getElementById("vgrAtendStatus");
  var uni = document.getElementById("vgrAtendUnidade").value;
  if (st) st.disabled = !uni;
}
/** Modal de confirmação dos Dados Field antes de iniciar (padrão PRODESP). */
var vgrConfirmFieldOpen = false;
function vgrOpenConfirmFieldModal() {
  var dupCount = document.querySelectorAll('[id="vgrConfirmFieldModal"]').length;
  if (dupCount > 1) {
    console.warn(
      "[VGR] #vgrConfirmFieldModal duplicado no DOM (" + dupCount +
        "x). Verifique se o partial vgr_atendimento_modals.html foi incluído mais de uma vez."
    );
  }
  var modalEl = document.getElementById("vgrConfirmFieldModal");
  if (!modalEl) {
    console.error("[VGR] Modal #vgrConfirmFieldModal não encontrado no DOM.");
    return Promise.resolve({ confirmed: false });
  }
  /* Empilhamento correto sobre o modal de atendimento (último no <body> fica por cima). */
  if (modalEl.parentElement !== document.body) {
    document.body.appendChild(modalEl);
  }
  /* Busca ESCOPADA no próprio modal: listeners sempre nos botões do modal exibido. */
  var q = function (id) {
    return modalEl.querySelector("#" + id);
  };
  var inpCont = q("vgrConfirmFieldContratada");
  var inpNome = q("vgrConfirmFieldNome");
  var inpTel = q("vgrConfirmFieldContato");
  var btnOk = q("vgrConfirmFieldOk");
  var btnCancel = q("vgrConfirmFieldCancel");
  if (!inpCont || !inpNome || !inpTel || !btnOk || !btnCancel) {
    console.error("[VGR] Modal Confirmar Dados Field incompleto (inputs/botões ausentes).");
    return Promise.resolve({ confirmed: false });
  }
  if (vgrConfirmFieldOpen) {
    return Promise.resolve({ confirmed: false });
  }
  vgrConfirmFieldOpen = true;

  /* Pré-preenche com o que já está no painel Dados Field (texto livre). */
  var painelCont = document.getElementById("vgrAtendFieldContratada");
  var painelNome = document.getElementById("vgrAtendFieldNome");
  var painelTel = document.getElementById("vgrAtendFieldTel");
  inpCont.value = ((painelCont && painelCont.value) || "").trim();
  inpNome.value = ((painelNome && painelNome.value) || "").trim();
  inpTel.value = ((painelTel && painelTel.value) || "").trim();
  [inpCont, inpNome, inpTel].forEach(function (el) {
    el.classList.remove("is-invalid");
  });

  var bs = bootstrap.Modal.getOrCreateInstance(modalEl, {
    backdrop: "static",
    keyboard: false
  });

  return new Promise(function (resolve) {
    var settled = false;
    var done = function (r) {
      if (settled) return;
      settled = true;
      vgrConfirmFieldOpen = false;
      btnOk.removeEventListener("click", onOk);
      btnCancel.removeEventListener("click", onCancel);
      modalEl.removeEventListener("hidden.bs.modal", onHidden);
      resolve(r);
    };
    var onOk = function () {
      var cont = (inpCont.value || "").trim();
      var nome = (inpNome.value || "").trim();
      var tel = (inpTel.value || "").replace(/\D/g, "");
      inpCont.classList.toggle("is-invalid", !cont);
      inpNome.classList.toggle("is-invalid", !nome);
      inpTel.classList.toggle("is-invalid", !tel);
      var missing = [];
      if (!cont) missing.push("Contratada");
      if (!nome) missing.push("Field");
      if (!tel) missing.push("Contato Field");
      if (missing.length) {
        V.toast("Para iniciar o atendimento, preencha: " + missing.join(", ") + ".", false);
        return;
      }
      done({ confirmed: true, contratada: cont, field: nome, contato: tel });
      bs.hide();
    };
    var onCancel = function () {
      bs.hide(); /* resolve via hidden.bs.modal → { confirmed: false } */
    };
    var onHidden = function () {
      done({ confirmed: false });
    };
    btnOk.addEventListener("click", onOk);
    btnCancel.addEventListener("click", onCancel);
    modalEl.addEventListener("hidden.bs.modal", onHidden);
    bs.show();
    modalEl.addEventListener(
      "shown.bs.modal",
      function () {
        inpCont.focus();
      },
      { once: true }
    );
  });
}
  /** Status «Em Atendimento» sem atendimento ainda: confirma Field e cria (POST). */
  async function vgrStartCreateFlow(stEl) {
    var uni = document.getElementById("vgrAtendUnidade").value;
    if (!uni) {
      V.toast("Selecione a unidade antes de iniciar o atendimento.", false);
      stEl.value = "";
      return;
    }
    var res = await vgrOpenConfirmFieldModal();
    if (!res.confirmed) {
      stEl.value = "";
      V.toast("Início do atendimento cancelado.", true);
      return;
    }
    document.getElementById("vgrAtendFieldNome").value = res.field;
    document.getElementById("vgrAtendFieldTel").value = res.contato;
    document.getElementById("vgrAtendFieldContratada").value = res.contratada;
    var body = readForm();
    body.status_atendimento = "Em Atendimento";
    body.substatus_atendimento = ""; /* server default: Aguarda Gestão */
    body.field_snaps = {
      snap_nome: res.field,
      snap_telefone: res.contato,
      snap_contratada_nome: res.contratada
    };
    stEl.disabled = true;
    V.jsonFetch("/vgr/api/atendimentos", { method: "POST", body: JSON.stringify(body) })
      .then(function (r) {
        if (r.status >= 400 || !r.d.success) {
          V.toast((r.d && r.d.message) || "Falha ao iniciar atendimento.", false);
          stEl.value = "";
          return;
        }
        var d = r.d.data || {};
        document.getElementById("vgrAtendId").value = String(d.id_atendimento || "");
        document.getElementById("modalVgrAtendTitle").textContent =
          "Atendimento #" + (d.id_atendimento || "");
        vgrPersistedStatus = (d.status_atendimento || "Em Atendimento").trim();
        vgrPersistedSubstatus = (d.substatus_atendimento || "").trim();
        var f0 = (d.fields || [])[0] || null;
        vgrFieldPersistedSnap = f0
          ? {
              snap_nome: (f0.snap_nome || "").trim(),
              snap_telefone: (f0.snap_telefone || "").trim(),
              snap_contratada_nome: (f0.snap_contratada_nome || "").trim()
            }
          : null;
        fillFieldPanel(d.fields || []);
        vgrUiPostCreate();
        V.toast("Atendimento #" + d.id_atendimento + " iniciado.", true);
        autoSaveDirty = true;
      })
      .finally(function () {
        stEl.disabled = false;
      });
  }

  /** UI pré-início para edição de atendimento NÃO iniciado (agenda publicada). */
  function vgrUiPreCreateEdit() {
    var st = document.getElementById("vgrAtendStatus");
    var sub = document.getElementById("vgrAtendSub");
    if (st) {
      st.innerHTML = "";
      var ph = document.createElement("option");
      ph.value = "Agendado";
      ph.textContent = "Agendado (somente leitura)";
      ph.disabled = true;
      ph.selected = true;
      st.appendChild(ph);
      st.add(new Option("Em Atendimento", "Em Atendimento"));
      st.disabled = false;
    }
    if (sub) {
      sub.innerHTML = "";
      var phs = document.createElement("option");
      phs.value = "";
      phs.textContent = "Selecione o substatus...";
      phs.disabled = true;
      phs.selected = true;
      sub.appendChild(phs);
      sub.disabled = true;
    }
    VGR_CREATE_LOCK_IDS.forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.disabled = true;
    });
    var uni = document.getElementById("vgrAtendUnidade");
    var idv = document.getElementById("vgrAtendIdVgr");
    if (uni) uni.disabled = true; /* unidade já vinculada à agenda */
    if (idv) idv.disabled = true;
  }
  /** Lápis em atendimento não iniciado: confirma Field e inicia via PUT (espelho PRODESP). */
  async function vgrStartInitFlowEdit(stEl) {
    var id = document.getElementById("vgrAtendId").value;
    if (!id) return;
    var res = await vgrOpenConfirmFieldModal();
    if (!res.confirmed) {
      stEl.value = "Agendado";
      V.toast("Início do atendimento cancelado.", true);
      return;
    }
    document.getElementById("vgrAtendFieldNome").value = res.field;
    document.getElementById("vgrAtendFieldTel").value = res.contato;
    document.getElementById("vgrAtendFieldContratada").value = res.contratada;
    var body = readForm();
    body.status_atendimento = "Em Atendimento";
    body.substatus_atendimento = ""; /* server default: Aguarda Gestão */
    stEl.disabled = true;
    V.jsonFetch("/vgr/api/atendimentos/" + encodeURIComponent(id), {
      method: "PUT",
      body: JSON.stringify(body)
    })
      .then(function (r) {
        if (r.status >= 400 || !r.d.success) {
          V.toast((r.d && r.d.message) || "Falha ao iniciar atendimento.", false);
          stEl.value = "Agendado";
          return;
        }
        /* Snapshot do Field confirmado (cria/atualiza vínculo); depois relê o
           atendimento: a resposta do PUT é anterior à gravação do Field. */
        return vgrSalvarDadosField(true)
          .then(function () {
            return V.jsonFetch("/vgr/api/atendimentos/" + encodeURIComponent(id));
          })
          .then(function (rFresh) {
            var d =
              (rFresh && rFresh.status < 400 && rFresh.d && rFresh.d.success && rFresh.d.data) ||
              r.d.data ||
              {};
            vgrEditNaoIniciado = false;
            vgrPersistedStatus = (d.status_atendimento || "Em Atendimento").trim();
            vgrPersistedSubstatus = (d.substatus_atendimento || "").trim();
            var f0 = (d.fields || [])[0] || null;
            vgrFieldPersistedSnap = f0
              ? {
                  snap_nome: (f0.snap_nome || "").trim(),
                  snap_telefone: (f0.snap_telefone || "").trim(),
                  snap_contratada_nome: (f0.snap_contratada_nome || "").trim()
                }
              : null;
            fillFieldPanel(d.fields || []);
            vgrUiPostCreate();
            updateSubstatusByStatus(vgrPersistedStatus, vgrPersistedSubstatus);
            V.toast("Atendimento #" + id + " iniciado.", true);
            autoSaveDirty = true;
          });
      })
      .finally(function () {
        stEl.disabled = false;
      });
  }

  function fillFieldPanel(fields) {
    var empty = document.getElementById("vgrAtendFieldEmpty");
    var list = document.getElementById("vgrAtendFieldList");
    var inpCont = document.getElementById("vgrAtendFieldContratada");
    currentFieldId = null;
    list.classList.remove("d-none");
    if (!fields || !fields.length) {
      empty.classList.remove("d-none");
      document.getElementById("vgrAtendFieldId").value = "";
      document.getElementById("vgrAtendFieldNome").value = "";
      document.getElementById("vgrAtendFieldTel").value = "";
      if (inpCont) inpCont.value = "";
      return;
    }
    empty.classList.add("d-none");
    var f = fields[0];
    currentFieldId = f.id_field;
    document.getElementById("vgrAtendFieldId").value = String(f.id_field);
    document.getElementById("vgrAtendFieldNome").value = f.snap_nome || "";
    document.getElementById("vgrAtendFieldTel").value = f.snap_telefone || "";
    if (inpCont) inpCont.value = f.snap_contratada_nome || "";
  }

  function clearForm() {
    document.getElementById("vgrAtendId").value = "";
    document.getElementById("vgrAtendAgenda").value = "";
    document.getElementById("vgrAtendAgendaStatus").value = "";
    document.getElementById("vgrAtendAgendaData").value = "";
    document.getElementById("vgrAtendAgendaHora").value = "";
    document.getElementById("vgrAtendAnalista").value = actorLabel;
    document.getElementById("vgrAtendAnalista").readOnly = true;
    document.getElementById("vgrAtendAnalistaHint").textContent = "Preenchido com quem inicia o atendimento.";
    ["vgrAtendIdVgrSdwan", "vgrAtendIdVgrSdwifi", "vgrAtendIdVgrSdlan"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.value = "";
    });
    document.getElementById("vgrAtendObsNova").value = "";

    renderObsLog([]);
    fillFieldPanel([]);
    vgrFieldAuto.reset();
    vgrSetFieldStatus(VGR_FIELD_STATUS_PADRAO, "");
    vgrPersistedStatus = "";
    vgrPersistedSubstatus = "";
    vgrFieldPersistedSnap = null;
    vgrObsTransicaoStaged = "";
    vgrEditNaoIniciado = false;

    vgrUiPreCreate(false);

    clearUnidadePainel();
    showErr("");

    var tabBtn = document.getElementById("vgrAtendTabUnidadeBtn");
    if (tabBtn && window.bootstrap && bootstrap.Tab) {
      bootstrap.Tab.getOrCreateInstance(tabBtn).show();
    }
  }

  function fillFormAtendimento(d) {
    document.getElementById("vgrAtendId").value = d.id_atendimento || "";
    document.getElementById("vgrAtendAgenda").value = d.id_agendamento || "";

    var stAg = d.status_agendamento || "";
    if (d.agenda_substatus) stAg += (stAg ? " / " : "") + d.agenda_substatus;
    document.getElementById("vgrAtendAgendaStatus").value = stAg;
    document.getElementById("vgrAtendAgendaData").value = d.data_agendamento ? (function() {
      var dt = vgrParseDateLocal(d.data_agendamento);
      return dt ? V.formatBrDate(dt) : d.data_agendamento;
    })() : "";
    document.getElementById("vgrAtendAgendaHora").value = d.hora_agendamento ? (V.formatBrTime ? V.formatBrTime(d.hora_agendamento) : d.hora_agendamento) : "";

    fillSelect(
      document.getElementById("vgrAtendStatus"),
      catalogo.status,
      d.status_atendimento || "Em Atendimento"
    );

    updateSubstatusByStatus(
      d.status_atendimento || "",
      d.substatus_atendimento || ""
    );

    var locked = Number(d.atendimento_iniciado) === 1;
    document.getElementById("vgrAtendAnalista").value =
      d.analista_atuante || actorLabel || "";
    document.getElementById("vgrAtendAnalista").readOnly = true;
    document.getElementById("vgrAtendAnalistaHint").textContent = locked
      ? "Analista bloqueado após início (P13)."
      : "Será gravado como você ao iniciar Atendimento.";

    var idVgrPorServico = {
      vgrAtendIdVgrSdwan: d.id_vgr_sdwan,
      vgrAtendIdVgrSdwifi: d.id_vgr_sdwifi,
      vgrAtendIdVgrSdlan: d.id_vgr_sdlan
    };
    Object.keys(idVgrPorServico).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) {
        var v = idVgrPorServico[id];
        el.value = v != null && v !== "" ? String(v) : "";
      }
    });

    renderObsLog(d.observacoes_log || []);
    fillFieldPanel(d.fields || []);
    vgrPersistedStatus = (d.status_atendimento || "").trim();
    vgrPersistedSubstatus = (d.substatus_atendimento || "").trim();
    var f0 = (d.fields || [])[0] || null;
    vgrFieldPersistedSnap = f0
      ? {
          snap_nome: (f0.snap_nome || "").trim(),
          snap_telefone: (f0.snap_telefone || "").trim(),
          snap_contratada_nome: (f0.snap_contratada_nome || "").trim()
        }
      : null;
    vgrObsTransicaoStaged = "";
    showErr("");
  }

  function readForm() {
    var agenda = document.getElementById("vgrAtendAgenda").value;
    return {
      id_unidade: document.getElementById("vgrAtendUnidade").value,
      id_agendamento: agenda ? agenda : null,
      status_atendimento: document.getElementById("vgrAtendStatus").value,
      substatus_atendimento: document.getElementById("vgrAtendSub").value,
      analista_atuante:
        document.getElementById("vgrAtendAnalista").value || actorLabel
    };
  }

    /* ============================================================
    Bloqueios de salvamento/finalização (espelho PRODESP)
    ============================================================ */
  let linkCache = [];
  let vgrPersistedStatus = "";
  let vgrPersistedSubstatus = "";
  let vgrFieldPersistedSnap = null;
  let vgrObsTransicaoStaged = "";
  let vgrEditNaoIniciado = false;
  let vgrSuppressAutoSave = false;
  let vgrSubstatusChangeInFlight = false;
  const VGR_OBS_TRANSICAO_MIN = 10;
  const VGR_FILAS_AGUARDANDO_CONFIG = [
    "Aguardando Config. Remota",
    "Aguardando Config. MPLS",
    "Aguardando Caderno de Teste"
  ];
  const VGR_AGUARDA_EXTERNO = ["Aguarda Cliente", "Aguarda Contratada"];
  function vgrIsSubstatusGestao(sub) {
    return (sub || "").trim() === "Aguarda Gestão";
  }
  function vgrIsTransicaoGestaoParaFilaConfig(oldSub, newSub) {
    return (
      vgrIsSubstatusGestao(oldSub) &&
      VGR_FILAS_AGUARDANDO_CONFIG.indexOf((newSub || "").trim()) >= 0
    );
  }
  function vgrIsEntradaAguardaExterno(oldSub, newSub) {
    var n = (newSub || "").trim();
    return VGR_AGUARDA_EXTERNO.indexOf(n) >= 0 && n !== (oldSub || "").trim();
  }
  function vgrRequiresTicketNoc(status, sub) {
    return (status || "").trim() === "Concluído" && (sub || "").trim() === "Concluído";
  }
  function vgrMarkInvalid(id, invalid) {
    var el = document.getElementById(id);
    if (!el) return;
    el.classList.toggle("is-invalid", !!invalid);
  }

  /** Mesma UX do PRODESP: is-invalid + abre a aba do primeiro campo inválido. */
  function vgrValidateFields(rules) {
    var missing = [];
    var firstTab = null;
    rules.forEach(function (rule) {
      var el = document.getElementById(rule.id);
      if (el) el.classList.remove("is-invalid");
    });
    rules.forEach(function (rule) {
      var el = document.getElementById(rule.id);
      if (!el) return;
      if (!el.value || String(el.value).trim() === "") {
        missing.push(rule.name);
        el.classList.add("is-invalid");
        var pane = el.closest(".tab-pane");
        if (pane && !firstTab) firstTab = pane;
      }
    });
    if (firstTab && window.bootstrap && bootstrap.Tab) {
      var btn = document.querySelector('button[data-bs-target="#' + firstTab.id + '"]');
      if (btn) bootstrap.Tab.getOrCreateInstance(btn).show();
    }
    return missing;
  }

  /** Abre uma aba do modal de edição pelo id do botão. */
  function vgrShowTab(btnId) {
    var btn = document.getElementById(btnId);
    if (btn && window.bootstrap && bootstrap.Tab) {
      bootstrap.Tab.getOrCreateInstance(btn).show();
    }
  }

  /** Ticket NOC válido (mesma regra do cadastro de equipamento). */
  function vgrTicketNocValido(val) {
    val = (val || "").trim();
    if (!val) return false;
    if (PF && PF.validateTicketNoc) return !PF.validateTicketNoc(val);
    return /^1\d{6}$/.test(val);
  }

  /** Concluído/Concluído exige inventário completo, incluindo Ticket NOC do equipamento. */
  function vgrValidateInventarioConcluido(status, sub) {
    if (!vgrRequiresTicketNoc(status, sub)) return [];
    var missing = [];
    var eqAtivos = (eqCache || []).filter(function (e) {
      return Number(e.ativo) === 1;
    });
    var wanAtivos = (linkCache || []).filter(function (l) {
      return Number(l.ativo) === 1 && V.isLinkTipoWan(l.tipo_link);
    });
    if (!eqAtivos.length) missing.push("Equipamento ativo cadastrado");
    else {
      if (!eqAtivos.some(function (e) { return (e.hostname || "").trim(); }))
        missing.push("Hostname do equipamento ativo");
      if (!eqAtivos.some(function (e) { return (e.id_vgr || "").trim(); }))
        missing.push("ID VGR do equipamento ativo");
      /* Para exigir de TODOS os ativos, troque `some` por `every` na linha abaixo. */
      if (!eqAtivos.some(function (e) { return vgrTicketNocValido(e.tkt_noc); }))
        missing.push("Ticket NOC do equipamento ativo (obrigatório em Status/Substatus Concluído)");
    }
    if (!wanAtivos.length) missing.push("Link WAN ativo");
    if (missing.length) vgrShowTab("vgrAtendTabEqLinksBtn");
    return missing;
  }

  function vgrReadFieldSnaps() {
    return {
      snap_nome: (document.getElementById("vgrAtendFieldNome").value || "").trim(),
      snap_telefone: (document.getElementById("vgrAtendFieldTel").value || "").trim(),
      snap_contratada_nome: (document.getElementById("vgrAtendFieldContratada").value || "").trim()
    };
  }

  function vgrValidateDadosField() {
    var snaps = vgrReadFieldSnaps();
    var missing = [];
    vgrMarkInvalid("vgrAtendFieldNome", !snaps.snap_nome);
    vgrMarkInvalid("vgrAtendFieldTel", !snaps.snap_telefone);
    vgrMarkInvalid("vgrAtendFieldContratada", !snaps.snap_contratada_nome);
    if (!snaps.snap_nome) missing.push("Field");
    if (!snaps.snap_telefone) missing.push("Contato Field");
    if (!snaps.snap_contratada_nome) missing.push("Contratada");
    return missing;
  }

  function vgrFieldPanelDirty() {
    var cur = vgrReadFieldSnaps();
    var p = vgrFieldPersistedSnap || { snap_nome: "", snap_telefone: "", snap_contratada_nome: "" };
    return (
      cur.snap_nome !== (p.snap_nome || "") ||
      cur.snap_telefone !== (p.snap_telefone || "") ||
      cur.snap_contratada_nome !== (p.snap_contratada_nome || "")
    );
  }

  function vgrNotifyBlocked(missing, intro) {
    var msg = (intro || "Preencha os campos obrigatórios") + ": " + missing.join(", ") + ".";
    showErr(msg);
    V.toast(msg, false);
  }

  function vgrRevertStatusSubstatus(statusVal, subVal) {
    vgrSuppressAutoSave = true;
    var stEl = document.getElementById("vgrAtendStatus");
    stEl.value = statusVal || "Em Atendimento";
    updateSubstatusByStatus(stEl.value, subVal || "");
    vgrSuppressAutoSave = false;
  }

  /** Modal genérico de observação obrigatória (contador + mín. N chars, padrão PRODESP). */
  function vgrOpenObsModal(opts) {
    var modalEl = document.getElementById("vgrObsModal");
    var textoEl = document.getElementById("vgrObsTexto");
    var counterEl = document.getElementById("vgrObsCounter");
    var helpEl = document.getElementById("vgrObsHelp");
    var titleEl = document.getElementById("vgrObsTitulo");
    var descEl = document.getElementById("vgrObsDescricao");
    var btnSave = document.getElementById("vgrObsSalvar");
    var btnCancel = document.getElementById("vgrObsCancelar");
    if (!modalEl || !textoEl || !btnSave || !btnCancel) {
      return Promise.resolve({ action: "cancel" });
    }
    var min = opts.min || VGR_OBS_TRANSICAO_MIN;
    if (titleEl) titleEl.textContent = opts.titulo || "Observação obrigatória";
    if (descEl)
      descEl.textContent =
        opts.descricao || "Descreva o ocorrido. Este texto será salvo em Observações.";
    if (helpEl) helpEl.textContent = "Mínimo de " + min + " caracteres para salvar.";
    textoEl.value = "";
    var update = function () {
      var n = (textoEl.value || "").trim().length;
      if (counterEl) counterEl.textContent = n + "/" + min;
      btnSave.disabled = n < min;
    };
    textoEl.oninput = update;
    update();
    var bsModal = bootstrap.Modal.getOrCreateInstance(modalEl, {
      backdrop: "static",
      keyboard: false
    });
    return new Promise(function (resolve) {
      var settled = false;
      var done = function (r) {
        if (settled) return;
        settled = true;
        btnSave.removeEventListener("click", onSave);
        btnCancel.removeEventListener("click", onCancel);
        modalEl.removeEventListener("hidden.bs.modal", onHidden);
        resolve(r);
      };
      var onSave = function () {
        done({ action: "save", texto: (textoEl.value || "").trim() });
        bsModal.hide();
      };
      var onCancel = function () { bsModal.hide(); };
      var onHidden = function () { done({ action: "cancel" }); };
      btnSave.addEventListener("click", onSave);
      btnCancel.addEventListener("click", onCancel);
      modalEl.addEventListener("hidden.bs.modal", onHidden);
      bsModal.show();
      setTimeout(function () { textoEl.focus(); }, 50);
    });
  }

  /** Salva o painel Dados Field (auto-save e transições). */
  function vgrSalvarDadosField(quiet) {
    var id = document.getElementById("vgrAtendId").value;
    var fid = document.getElementById("vgrAtendFieldId").value || currentFieldId;
    if (!id) return Promise.resolve(false);
    var payload = vgrReadFieldSnaps();
    var isCreate = !fid;
    if (isCreate && !payload.snap_nome) return Promise.resolve(false);
    var url = isCreate
      ? "/vgr/api/atendimentos/" + encodeURIComponent(id) + "/fields"
      : "/vgr/api/atendimentos/" + encodeURIComponent(id) + "/fields/" + encodeURIComponent(fid);
    var method = isCreate ? "POST" : "PUT";
    return V.jsonFetch(url, { method: method, body: JSON.stringify(payload) }).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Falha ao salvar Field.", false);
        return false;
      }
      /* Atualiza só o vínculo — não reescreve os inputs (usuário pode estar digitando). */
      var f0 = ((res.d.data && res.d.data.fields) || [])[0] || null;
      if (f0) {
        currentFieldId = f0.id_field;
        document.getElementById("vgrAtendFieldId").value = String(f0.id_field);
        var empty = document.getElementById("vgrAtendFieldEmpty");
        if (empty) empty.classList.add("d-none");
      }
      vgrFieldPersistedSnap = payload;
      if (!quiet) {
        V.toast(
          res.d.message || (isCreate ? "Field cadastrado no atendimento." : "Field atualizado."),
          true
        );
      }
      return true;
    });
  }
  /** Guards compartilhados (auto-save e botão Salvar). */
  async function vgrRunSaveGuards(body) {
    var status = (body.status_atendimento || "").trim();
    var sub = (body.substatus_atendimento || "").trim();
    var missing = [];
    if (FINAIS[status]) {
      missing = missing.concat(
        vgrValidateFields([
          { id: "vgrAtendSub", name: "Substatus" },
          { id: "vgrAtendAnalista", name: "Analista atuante" }
        ])
      );
    }
    missing = missing.concat(vgrValidateInventarioConcluido(status, sub));
    if (vgrIsTransicaoGestaoParaFilaConfig(vgrPersistedSubstatus, sub)) {
      var missingField = vgrValidateDadosField();
      if (missingField.length) missing = missing.concat(missingField);
      else if (vgrFieldAuto.pending() || vgrFieldPanelDirty()) {
        /* Usa a mesma fila do auto-save: evita duas gravações concorrentes */
        vgrFieldAuto.mark();
        if (!(await vgrFieldAuto.flush())) missing.push("Dados Field (não foi possível salvar)");
      }
    }
    if (missing.length) {
      vgrNotifyBlocked(missing, "Para salvar com este status/substatus, preencha");
      return { ok: false, missing: missing };
    }
    return { ok: true, missing: [] };
  }
  /** Fluxo do change de substatus (ordem PRODESP: Quebra → aguarda externo → guards → save). */
  async function vgrOnSubstatusChange() {
    if (vgrSubstatusChangeInFlight || vgrSuppressAutoSave) return;
    var subEl = document.getElementById("vgrAtendSub");
    var stEl = document.getElementById("vgrAtendStatus");
    var newSub = (subEl.value || "").trim();
    var oldSub = vgrPersistedSubstatus;
    var status = (stEl.value || "").trim();
    if (!newSub || newSub === oldSub) {
      autoSave();
      return;
    }
    /* 1) Encerramento com Quebra: motivo obrigatório */
    if (status === "Quebra" && newSub.indexOf("Quebra") === 0 && vgrPersistedStatus !== "Quebra") {
      vgrSubstatusChangeInFlight = true;
      try {
        vgrRevertStatusSubstatus(vgrPersistedStatus, oldSub);
        var resQ = await vgrOpenObsModal({
          titulo: "Motivo da quebra",
          descricao: "Descreva o motivo da quebra. O texto será salvo em Observações.",
          min: VGR_OBS_TRANSICAO_MIN
        });
        if (resQ.action !== "save") return;
        vgrObsTransicaoStaged = resQ.texto;
        vgrSuppressAutoSave = true;
        stEl.value = "Quebra";
        updateSubstatusByStatus("Quebra", newSub);
        vgrSuppressAutoSave = false;
        await autoSave();
      } finally {
        vgrSubstatusChangeInFlight = false;
      }
      return;
    }
    /* 2) Entrada em Aguarda Cliente/Contratada: observação obrigatória */
    if (vgrIsEntradaAguardaExterno(oldSub, newSub)) {
      vgrSubstatusChangeInFlight = true;
      try {
        vgrRevertStatusSubstatus(status, oldSub);
        var resA = await vgrOpenObsModal({
          titulo: newSub,
          descricao: "Descreva o ocorrido. Este texto será salvo em Observações.",
          min: VGR_OBS_TRANSICAO_MIN
        });
        if (resA.action !== "save") return;
        vgrObsTransicaoStaged = resA.texto;
        vgrSuppressAutoSave = true;
        updateSubstatusByStatus(status, newSub);
        vgrSuppressAutoSave = false;
        await autoSave();
      } finally {
        vgrSubstatusChangeInFlight = false;
      }
      return;
    }
    autoSave();
  }

  async function autoSave() {
    if (vgrSuppressAutoSave) return false;
    if (vgrEditNaoIniciado) {
      showErr("Inicie o atendimento pelo status «Em Atendimento» (confirmação dos Dados Field).");
      return false;
    }
    var body = readForm();
    if (!body.id_unidade) {
      showErr("Selecione a unidade (aba Dados Unidade e Conectividade).");
      return;
    }
    if (vgrEditNaoIniciado) {
      showErr("Inicie o atendimento pelo status «Em Atendimento» (confirmação dos Dados Field).");
      return;
    }
    var sub = document.getElementById("vgrAtendSub").value;
    if (!sub) {
      return false; // não salva com substatus vazio ("Selecione o substatus")
    }
    var guards = await vgrRunSaveGuards(body);
    if (!guards.ok) {
      vgrRevertStatusSubstatus(vgrPersistedStatus, vgrPersistedSubstatus);
      return false;
    }
    if (vgrObsTransicaoStaged) body.observacao_transicao = vgrObsTransicaoStaged;
    var id = document.getElementById("vgrAtendId").value;
    if (!id) {
      var snaps = vgrReadFieldSnaps();
      if (snaps.snap_nome) body.field_snaps = snaps;
    }
    var url = id
      ? "/vgr/api/atendimentos/" + encodeURIComponent(id)
      : "/vgr/api/atendimentos";
    var method = id ? "PUT" : "POST";
    showErr("");
    return V.jsonFetch(url, { method: method, body: JSON.stringify(body) }).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        showErr((res.d && res.d.message) || "Falha ao salvar automaticamente.");
        V.toast((res.d && res.d.message) || "Falha no salvamento automático.", false);
        return false;
      }
      var novoId = res.d.data && res.d.data.id_atendimento;
      if (!id && novoId) {
        document.getElementById("vgrAtendId").value = String(novoId);
        document.getElementById("modalVgrAtendTitle").textContent =
          "Atendimento #" + novoId;
        V.toast("Atendimento #" + novoId + " criado.", true);
      } else {
        V.toast("Alterações salvas automaticamente.", true);
      }
      /* Não reescreve o painel Field se há edição dele em curso (auto-save próprio). */
      if (!vgrFieldAuto.pending()) {
        fillFieldPanel((res.d.data && res.d.data.fields) || []);
      }
      vgrPersistedStatus = (body.status_atendimento || "").trim();
      vgrPersistedSubstatus = (body.substatus_atendimento || "").trim();
      vgrObsTransicaoStaged = "";
      autoSaveDirty = true;
      showErr("");
      return true;
    });
  }
  /* A Gestão injeta a própria fonte (linhas do período) e os parâmetros de data;
     sem isso, a Fila usa a fonte padrão. */
  var listUrl =
    window.VGR_ATEND_LIST_URL ||
    "/vgr/api/atendimentos" +
      (modo === "gestao" ? "?modo=gestao" : "?apenas_ativos=1");

  /* Padrão PRODESP: preserva o V.clientAjax e apenas envolve o dataSrc
    para aplicar a normalização sintética em cada linha carregada. */
  var vgrListAjax = V.clientAjax(listUrl);
  if (typeof window.VGR_ATEND_LIST_PARAMS === "function") {
    vgrListAjax.data = function (d) {
      var base = d && !Array.isArray(d) ? d : {};
      return Object.assign(base, window.VGR_ATEND_LIST_PARAMS() || {});
    };
  }
  var _vgrOrigDataSrc = vgrListAjax.dataSrc;
  vgrListAjax.dataSrc = function (json) {
    var rows =
      typeof _vgrOrigDataSrc === "function"
        ? _vgrOrigDataSrc(json)
        : (json && json.data) || [];
    return (rows || []).map(vgrNormalizeAtendimentoListRow);
  };

  /* Índices fixos (mesma ideia de PRODESP_DT_COL_*) */
  const VGR_DT_COL_ACOES = 10;
  const VGR_DT_COL_LISTA = 11; /* oculta: prioridade da fila */
  const VGR_DT_ORDEM_PADRAO = [[VGR_DT_COL_LISTA, "asc"]];

  function vgrRenderData(d, t) {
    if (!d) return "";
    if (t !== "display") return d; /* ISO cru → ordena corretamente */
    var dt = vgrParseDateLocal(d);
    return dt ? V.formatBrDate(dt) : d;
  }

  const api = $("#tblVgrAtendimentos").DataTable(
    V.baseOpts({
      order: VGR_DT_ORDEM_PADRAO,
      ajax: vgrListAjax,
      columns: [
        { data: "data_agendamento", defaultContent: "", render: vgrRenderData },
        {
          data: "hora_agendamento",
          defaultContent: "",
          render: function (d, t) {
            if (!d) return "";
            if (t !== "display") return d;
            return V.formatBrTime ? V.formatBrTime(d) : d;
          }
        },
        { data: "data_atendimento", defaultContent: "", render: vgrRenderData },
        {
          data: "razao_social",
          defaultContent: "",
          render: function (d, t) {
            if (t !== "display") return d || "";
            d = d || "";
            return d.length > 25 ? d.substring(0, 25) + "..." : d;
          }
        },
        { data: "analista_atuante", defaultContent: "", render: function (d, t) { return V.renderText(d, t); } },
        { data: "status_atendimento", defaultContent: "", render: function (d, t) { return V.renderText(d, t); } },
        { data: "substatus_atendimento", defaultContent: "", render: function (d, t) { return V.renderText(d, t); } },
        { data: "id_vgr_sdwan", defaultContent: "", render: function (d, t) { return V.renderText(d, t); } },
        { data: "id_vgr_sdwifi", defaultContent: "", render: function (d, t) { return V.renderText(d, t); } },
        { data: "id_vgr_sdlan", defaultContent: "", render: function (d, t) { return V.renderText(d, t); } },
        {
          data: null,
          orderable: false,
          searchable: false,
          className: "col-acoes portal-dt-acoes",
          render: function (_d, _t, row) {
            /* Gestão: agenda sem atendimento criado → abre a unidade
               (equivalente ao viewUnitOnly do PRODESP). */
            var semAtendimento =
              row.id_atendimento === null ||
              row.id_atendimento === undefined ||
              row.id_atendimento === "";
            if (semAtendimento) {
              return row.id_unidade
                ? V.acoesAbrir("/vgr/unidades/" + encodeURIComponent(row.id_unidade))
                : "";
            }
            return V.acoesAtendimento(row.id_atendimento, row.ativo);
          }
        },
        {
          /* Prioridade da fila (padrão PRODESP _sort_lista) */
          data: "_sort_lista",
          visible: false,
          searchable: false,
          orderable: true,
          defaultContent: 4 * VGR_SORT_FAIXA
        }
      ],
      columnDefs: [
        { targets: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], columnControl: cc },
        { targets: [VGR_DT_COL_ACOES, VGR_DT_COL_LISTA], columnControl: [] }
      ],
      drawCallback: function () {
        refreshKpis(this.api());
      }
    })
  );

  /* "Dia atual" local (YYYY-MM-DD) — base dos cards da fila. */
  function vgrHojeLocalIso() {
    var d = new Date();
    var m = String(d.getMonth() + 1).padStart(2, "0");
    var dd = String(d.getDate()).padStart(2, "0");
    return d.getFullYear() + "-" + m + "-" + dd;
  }
  /* Linha pertence ao dia atual (data de agenda OU data de abertura). */
  function vgrRowDiaAtual(row) {
    if (!row) return false;
    var hoje = vgrHojeLocalIso();
    var dag = String(row.data_agendamento || "").substring(0, 10);
    var dat = String(row.data_atendimento || "").substring(0, 10);
    return dag === hoje || dat === hoje;
  }

  function refreshKpis(dtApi) {
    /* Cards da fila = SOMENTE linhas do dia atual (agenda ou abertura),
      enquanto a tabela exibe o histórico operacional (sem Concluídos).
      KPIs contam todas as linhas do dia, não as filtradas pela tabela. */
    var rows = dtApi.rows().data().toArray().filter(vgrRowDiaAtual);
    var agendados = 0;
    var totalFila = 0;
    var porSubstatus = {};
    rows.forEach(function (r) {
      var stAtend = (r.status_atendimento || "").trim();
      var sub = (r.substatus_atendimento || "").trim();
      if (vgrRowIsAgendado(r)) agendados++;
      if (stAtend === STATUS_FILA) {
        totalFila++;
        porSubstatus[sub] = (porSubstatus[sub] || 0) + 1;
      }
    });
    var set = function (id, n) {
      var el = document.getElementById(id);
      if (el) el.textContent = String(n);
    };
    set("vgrKpiAgendados", agendados);
    set("vgrKpiTotalFila", totalFila);
    document
      .querySelectorAll(".vgr-fila-kpi-grid .filter-card[data-vgr-substatus]")
      .forEach(function (card) {
        var sub = card.getAttribute("data-vgr-substatus") || "";
        var el = card.querySelector("[data-vgr-substatus-valor]");
        if (el) el.textContent = String(porSubstatus[sub] || 0);
      });
  }

  $.fn.dataTable.ext.search.push(function (_settings, _data, dataIndex) {
    if (!kpiFilter || _settings.nTable.id !== "tblVgrAtendimentos") return true;
    var row = api.row(dataIndex).data();
    if (!row) return true;
    /* Card clicado = fila do dia: o filtro também restringe ao dia atual,
      para que as linhas exibidas confiram com o número do card.
      Sem card clicado, a tabela mostra o histórico (sem Concluídos). */
    if (!vgrRowDiaAtual(row)) return false;
    if (kpiFilter === "todos") return true;
    var stAtend = (row.status_atendimento || "").trim();
    /* Card Agendados: usa o estado sintético (padrão PRODESP). */
    if (kpiFilter === "agendados") return vgrRowIsAgendado(row);
    /* Filas ativas: apenas atendimentos operacionais em andamento. */
    if (kpiFilter === "filas-ativas") return stAtend === STATUS_FILA;
    if (kpiFilter.indexOf("substatus::") === 0) {
      var sub = kpiFilter.slice("substatus::".length);
      return stAtend === STATUS_FILA && (row.substatus_atendimento || "").trim() === sub;
    }
    return true;
  });

  var kpiGridEl = document.querySelector(".vgr-fila-kpi-grid");
  if (kpiGridEl) {
    kpiGridEl.addEventListener("click", function (ev) {
      var card = ev.target.closest(".filter-card");
      if (!card) return;
      var sub = card.getAttribute("data-vgr-substatus");
      var next = sub
        ? "substatus::" + sub
        : (card.getAttribute("data-vgr-filter") || "todos");
      kpiFilter = kpiFilter === next ? null : next;
      api.draw();
    });
  }

  function reload() {
    api.ajax.reload(null, false);
  }

  /* API pública: a Gestão de atendimentos recarrega/filtra esta mesma tabela. */
  window.VgrAtendimentos = { api: api, reload: reload };

  V.mountToolbar("tblVgrAtendimentos", api, {
    onClearExtra: function () {
      kpiFilter = null;
      document.dispatchEvent(new CustomEvent("vgr:atendimentos:limpar"));
      api.order(VGR_DT_ORDEM_PADRAO).draw();
    }
  });

  document.getElementById("vgrAtendUnidade").addEventListener("change", function () {
    loadUnidadeDetalhe(this.value);
    vgrRefreshStatusAvailability();
  });
  function applyUnidadeSelecionada(idUnidade) {
    return loadUnidades(idUnidade).then(function () {
      var sel = document.getElementById("vgrAtendUnidade");
      sel.value = String(idUnidade);
      return loadUnidadeDetalhe(idUnidade).then(function () {
        vgrRefreshStatusAvailability();
      });
    });
  }
  function buscarUnidadePorIdVgr() {
    var inp = document.getElementById("vgrAtendIdVgr");
    if (!inp) return;
    var v = PF ? PF.sanitizePastedText(inp.value) : (inp.value || "").trim();
    if (v !== inp.value) inp.value = v;
    if (!v) return;
    V.jsonFetch("/vgr/api/unidades/by-id-vgr/" + encodeURIComponent(v)).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "ID VGR não encontrado (equipamentos.id_vgr).", false);
        return;
      }
      var u = res.d.data || {};
      if (!u.id_unidade) {
        V.toast("Unidade não encontrada para o ID VGR.", false);
        return;
      }
      applyUnidadeSelecionada(u.id_unidade);
    });
  }
  var vgrIdVgrInput = document.getElementById("vgrAtendIdVgr");
  if (vgrIdVgrInput) {
    vgrIdVgrInput.addEventListener("change", buscarUnidadePorIdVgr);
    vgrIdVgrInput.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        ev.preventDefault();
        buscarUnidadePorIdVgr();
      }
    });
  }

  /* ============================================================
     AUTO-SAVE — aba Unidade (PUT /vgr/api/unidades/<id>) e Dados
     Field (POST/PUT /vgr/api/atendimentos/<id>/fields).
     Grava ao SAIR do campo (change); a digitação só marca pendência.
     Edição liberada apenas após o início do atendimento.
     ============================================================ */
  var vgrUniLiveEnd = R
    ? R.bindEndereco({
        cnpj: "vgrAtendCnpjUni",
        cep: "vgrAtendCep",
        uf: "vgrAtendUf",
        latitude: "vgrAtendLatitude",
        longitude: "vgrAtendLongitude"
      })
    : null;

  /** Atendimento criado e iniciado (mesma condição que destrava os campos). */
  function vgrEdicaoLiberada() {
    return !!document.getElementById("vgrAtendId").value && !vgrEditNaoIniciado;
  }

  /* Opções de cliente (mesma fonte do modal de Unidades), carregadas uma vez. */
  var vgrClientesOpcoesPromise = null;
  function vgrCarregarClientesOpcoes() {
    if (vgrClientesOpcoesPromise) return vgrClientesOpcoesPromise;
    vgrClientesOpcoesPromise = V.jsonFetch("/vgr/api/clientes/opcoes")
      .then(function (res) {
        var sel = document.getElementById("vgrAtendCliente");
        if (!sel) return;
        var atual = sel.value;
        var atualTxt = sel.selectedIndex >= 0 ? sel.options[sel.selectedIndex].textContent : "";
        sel.innerHTML = "";
        sel.add(new Option("Selecione…", ""));
        ((res.d && res.d.data) || []).forEach(function (r) {
          sel.add(new Option(r.razao_social || "#" + r.id_cliente, String(r.id_cliente)));
        });
        if (atual) vgrSelectSetValue(sel, atual, atualTxt);
      })
      .catch(function (e) {
        vgrClientesOpcoesPromise = null; /* permite nova tentativa */
        console.error("[VGR] clientes/opcoes:", e);
      });
    return vgrClientesOpcoesPromise;
  }

  /** Mesmo payload do readForm() da view Unidades (parse_unidade_payload, partial=False). */
  function vgrLerFormUnidade() {
    var g = function (id) {
      var el = document.getElementById(id);
      return el ? el.value : "";
    };
    return {
      id_cliente: g("vgrAtendCliente"),
      nome_unidade: g("vgrAtendNomeUni"),
      contato_unidade: g("vgrAtendContatoUni"),
      cnpj_unidade: g("vgrAtendCnpjUni"),
      codigo_unidade: g("vgrAtendCodigoUni"),
      tipo_unidade: g("vgrAtendTipoUni") || "FILIAL",
      tipo_projeto: g("vgrAtendTipoProjeto") || "PRATELEIRA",
      ha: g("vgrAtendHa") || "0",
      topologia_unidades: g("vgrAtendTopologia"),
      endereco: g("vgrAtendEndereco"),
      bairro: g("vgrAtendBairro"),
      cidade: g("vgrAtendCidade"),
      uf: g("vgrAtendUf"),
      cep: g("vgrAtendCep"),
      latitude: g("vgrAtendLatitude"),
      longitude: g("vgrAtendLongitude")
    };
  }

  /** Mantém o select «Unidade» e o cache coerentes após renomear/trocar cliente. */
  function vgrAtualizarOpcaoUnidade(d) {
    if (!d || d.id_unidade == null) return;
    var id = String(d.id_unidade);
    unidadesCache.forEach(function (r) {
      if (String(r.id_unidade) === id) Object.assign(r, d);
    });
    var sel = document.getElementById("vgrAtendUnidade");
    if (!sel) return;
    Array.prototype.forEach.call(sel.options, function (o) {
      if (o.value === id) {
        o.textContent = (d.nome_unidade || "#" + id) + (d.razao_social ? " — " + d.razao_social : "");
      }
    });
  }

  /** Execução do auto-save da unidade (chamada pela fila vgrUniAuto). */
  function vgrAutoSalvarUnidade() {
    var idUni = currentUnidadeId();
    if (!idUni || !vgrUnidadeAtual || !vgrEdicaoLiberada()) return Promise.resolve(true);

    var body = vgrLerFormUnidade();
    var errCli = R ? R.validateUnidadePayload(body) : null;
    if (errCli) {
      vgrSetUniStatus("Não salvo: " + errCli, "error");
      if (vgrUniLiveEnd) vgrUniLiveEnd.refresh();
      return Promise.resolve(false);
    }

    vgrSetUniStatus("Salvando dados da unidade…", "");
    return V.jsonFetch("/vgr/api/unidades/" + encodeURIComponent(idUni), {
      method: "PUT",
      body: JSON.stringify(body)
    }).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        var msg = (res.d && res.d.message) || "Falha ao salvar dados da unidade.";
        /* Valor alterado e depois revertido: MySQL não altera linha → não é erro. */
        if (/nenhuma altera/i.test(msg)) {
          vgrSetUniStatus("Sem alterações a salvar.", "ok");
          return true;
        }
        vgrSetUniStatus("Não salvo: " + msg, "error");
        V.toast(msg, false);
        return false;
      }
      var d = res.d.data || {};
      vgrUnidadeAtual = d;
      vgrAtualizarOpcaoUnidade(d);
      /* Reaplica a versão normalizada do servidor só se nada mais foi editado. */
      if (!vgrUniAuto.hasNewer() && String(currentUnidadeId()) === String(idUni)) {
        vgrPreencherCamposUnidade(d);
      }
      vgrSetUniStatus("Salvo automaticamente às " + vgrHoraAgora() + ".", "ok");
      return true;
    });
  }

  /** Execução do auto-save dos Dados Field (chamada pela fila vgrFieldAuto). */
  function vgrAutoSalvarField() {
    if (!vgrEdicaoLiberada()) return Promise.resolve(true);
    if (!vgrFieldPanelDirty()) return Promise.resolve(true);
    var fid = document.getElementById("vgrAtendFieldId").value || currentFieldId;
    if (!fid && !vgrReadFieldSnaps().snap_nome) {
      vgrSetFieldStatus("Informe o nome do Field para salvar.", "warn");
      vgrMarkInvalid("vgrAtendFieldNome", true);
      return Promise.resolve(false);
    }
    vgrMarkInvalid("vgrAtendFieldNome", false);
    vgrSetFieldStatus("Salvando Dados Field…", "");
    return vgrSalvarDadosField(true).then(function (ok) {
      vgrSetFieldStatus(
        ok ? "Salvo automaticamente às " + vgrHoraAgora() + "." : "Não salvo — veja o aviso.",
        ok ? "ok" : "error"
      );
      return ok;
    });
  }

  /* Ligação dos campos: digitação marca pendência; sair do campo grava. */
  VGR_UNI_EDIT_IDS.forEach(function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("input", function () {
      if (vgrUnidadeAtual && vgrEdicaoLiberada()) vgrUniAuto.mark();
    });
    el.addEventListener("change", function () {
      if (vgrUnidadeAtual && vgrEdicaoLiberada()) vgrUniAuto.schedule();
    });
  });
  VGR_FIELD_EDIT_IDS.forEach(function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("input", function () {
      if (vgrEdicaoLiberada()) vgrFieldAuto.mark();
    });
    el.addEventListener("change", function () {
      if (vgrEdicaoLiberada()) vgrFieldAuto.schedule();
    });
  });

  /* Completar endereço — preenche os vazios; os eventos change disparados
     pelo core agendam UM auto-save (debounce) com todos os campos. */
  if (window.PortalEnriquecerEndereco && window.PortalEnriquecerEndereco.bind) {
    window.PortalEnriquecerEndereco.bind({
      buttonId: "btnVgrAtendCompletarEndereco",
      statusId: "vgrAtendUniStatus",
      endpoint: "/vgr/api/enriquecer-endereco",
      fields: {
        endereco: "vgrAtendEndereco",
        bairro: "vgrAtendBairro",
        cidade: "vgrAtendCidade",
        municipio: "vgrAtendCidade",
        uf: "vgrAtendUf",
        estado: "vgrAtendUf",
        cep: "vgrAtendCep",
        latitude: "vgrAtendLatitude",
        longitude: "vgrAtendLongitude"
      },
      canRun: function () {
        if (!currentUnidadeId() || !vgrUnidadeAtual) {
          return "Selecione a unidade antes de completar o endereço.";
        }
        return vgrEdicaoLiberada() ? null : "Inicie o atendimento para editar a unidade.";
      },
      onApplied: function (applied) {
        if (!applied || !Object.keys(applied).length) {
          vgrSetUniStatus("Nada a completar: o endereço já está preenchido.", "ok");
        }
      }
    });
  } else {
    console.warn(
      "[VGR] portal_enriquecer_endereco.js não carregado: botão «Completar endereço» inativo."
    );
  }

  vgrCarregarClientesOpcoes();

  document.getElementById("vgrAtendAgenda").addEventListener("change", function () {
    var agId = this.value;
    var atId = document.getElementById("vgrAtendId").value;
    if (atId || !agId) return; // na edição o painel já vem via fillFormAtendimento

    V.jsonFetch("/vgr/api/agendamentos/" + encodeURIComponent(agId)).then(function (res) {
      if (res.status >= 400 || !res.d.success) return;
      var d = res.d.data || {};
      fillFieldPanel(d.fields || []);
    });
  });

  if (modalEl && window.bootstrap) {
    /* X / Cancelar / ESC: grava o que estiver pendente antes de fechar;
       se não for possível gravar, pede confirmação para descartar. */
    var vgrFechandoModal = false;
    modalEl.addEventListener("hide.bs.modal", function (ev) {
      if (ev.target !== modalEl || vgrFechandoModal) return;
      if (!vgrUniAuto.pending() && !vgrFieldAuto.pending()) return;
      ev.preventDefault();
      Promise.all([vgrUniAuto.flush(), vgrFieldAuto.flush()]).then(function (r) {
        var ok = r[0] && r[1];
        if (
          ok ||
          window.confirm(
            "Algumas alterações não puderam ser salvas automaticamente (veja os avisos). Fechar e descartar?"
          )
        ) {
          vgrUniAuto.reset();
          vgrFieldAuto.reset();
          vgrFechandoModal = true;
          bootstrap.Modal.getOrCreateInstance(modalEl).hide();
        } else if (!r[0]) {
          vgrShowTab("vgrAtendTabUnidadeBtn");
        } else {
          vgrShowTab("vgrAtendTabAtendBtn");
        }
      });
    });
    modalEl.addEventListener("hidden.bs.modal", function () {
      vgrFechandoModal = false;
      if (autoSaveDirty) {
        autoSaveDirty = false;
        reload();
      }
    });
  }

  function openCreate() {
    clearForm();
    document.getElementById("modalVgrAtendTitle").textContent = "Novo Atendimento";
    loadUnidades(null).then(function () {
      if (modal) modal.show();
    });
  }

  function openEdit(id) {
    clearForm();
    document.getElementById("modalVgrAtendTitle").textContent = "Atendimento #" + id;
    if (modal) modal.show();
    V.jsonFetch("/vgr/api/atendimentos/" + encodeURIComponent(id)).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Atendimento não encontrado.", false);
        if (modal) modal.hide();
        return;
      }
      var d = res.d.data || {};
      /* Dados do atendimento (status, observações, fields) renderizados
        imediatamente, independentes do carregamento do inventário. */
      fillFormAtendimento(d);
      /* Atendimento não iniciado (agenda publicada): mesmas regras do create —
        UI travada, status único «Em Atendimento» + Confirmar Dados Field. */
      vgrEditNaoIniciado =
        Number(d.atendimento_iniciado) !== 1 ||
        (d.status_atendimento || "").trim() === "Agendado";
      if (vgrEditNaoIniciado) {
        vgrUiPreCreateEdit();   /* trava até confirmar os Dados Field */
      } else {
        vgrUiPostCreate();      /* atendimento em andamento: libera */
      }

      loadUnidades(d.id_unidade)
        .then(function () {
          return loadUnidadeDetalhe(d.id_unidade);
        })
        .catch(function (e) {
          console.error("[VGR] openEdit -> unidade/inventário:", e);
          V.toast("Falha ao carregar unidade/inventário do atendimento.", false);
        });
    });
  }

  V.jsonFetch("/vgr/api/atendimentos/catalogo").then(function (res) {
    if (res.d && res.d.success) {
      catalogo = res.d.data || catalogo;
      document
        .getElementById("vgrAtendStatus")
        .addEventListener("change", function () {
          var novoStatus = this.value;
          var idAt = document.getElementById("vgrAtendId").value;
          if (novoStatus === "Em Atendimento") {
            if (!idAt) {
              vgrStartCreateFlow(this);
              return;
            }
            if (vgrEditNaoIniciado) {
              vgrStartInitFlowEdit(this);
              return;
            }
          }
          updateSubstatusByStatus(novoStatus, "");
          /* Bloqueio imediato ao escolher final (exceto Quebra, tratada no substatus) */
          if (FINAIS[novoStatus] && novoStatus !== "Quebra") {
            var body = readForm();
            var missing = vgrValidateInventarioConcluido(
              novoStatus,
              body.substatus_atendimento
            );
            if (missing.length) {
              vgrNotifyBlocked(missing, "Para usar o status «" + novoStatus + "», preencha");
              vgrRevertStatusSubstatus(vgrPersistedStatus, vgrPersistedSubstatus);
            }
          }
        });
    }
  });

  var btnNovo = document.getElementById("btnVgrAtendNovo");
  if (btnNovo) btnNovo.addEventListener("click", openCreate);

  var btnSalvar = document.getElementById("btnVgrAtendSalvar");
  if (btnSalvar) {
    btnSalvar.addEventListener("click", async function () {
      showErr("");
      var body = readForm();
      if (!body.id_unidade) {
        showErr("Selecione a unidade (aba Dados Unidade e Conectividade).");
        return;
      }
      var idChk = document.getElementById("vgrAtendId").value;
      var subChk = (document.getElementById("vgrAtendSub").value || "").trim();
      if (!idChk && !subChk) {
        showErr(
          "Inicie o atendimento pelo status «Em Atendimento» (confirmação dos Dados Field)."
        );
        return;
      }
      /* Auto-save pendente (unidade / Dados Field): grava antes do atendimento. */
      var okAuto = await Promise.all([vgrUniAuto.flush(), vgrFieldAuto.flush()]);
      if (!okAuto[0] || !okAuto[1]) {
        showErr(
          "Há dados da unidade ou do Field que não puderam ser salvos. Corrija os campos indicados."
        );
        vgrShowTab(!okAuto[0] ? "vgrAtendTabUnidadeBtn" : "vgrAtendTabAtendBtn");
        return;
      }
      var status = (body.status_atendimento || "").trim();
      var sub = (body.substatus_atendimento || "").trim();
      /* Fluxo Quebra via botão Salvar (se o modal ainda não rodou) */
      if (status === "Quebra" && vgrPersistedStatus !== "Quebra" && !vgrObsTransicaoStaged) {
        var resQ = await vgrOpenObsModal({
          titulo: "Motivo da quebra",
          descricao: "Descreva o motivo da quebra. O texto será salvo em Observações.",
          min: VGR_OBS_TRANSICAO_MIN
        });
        if (resQ.action !== "save") return;
        vgrObsTransicaoStaged = resQ.texto;
      }
      var guards = await vgrRunSaveGuards(body);
      if (!guards.ok) return;
      if (vgrObsTransicaoStaged) body.observacao_transicao = vgrObsTransicaoStaged;
      var id = document.getElementById("vgrAtendId").value;
      if (!id) {
        var snaps = vgrReadFieldSnaps();
        if (snaps.snap_nome) body.field_snaps = snaps;
      }
      var url = id
        ? "/vgr/api/atendimentos/" + encodeURIComponent(id)
        : "/vgr/api/atendimentos";
      var method = id ? "PUT" : "POST";
      btnSalvar.disabled = true;
      V.jsonFetch(url, { method: method, body: JSON.stringify(body) })
        .then(function (res) {
          if (res.status >= 400 || !res.d.success) {
            showErr((res.d && res.d.message) || "Falha ao salvar.");
            V.toast((res.d && res.d.message) || "Falha ao salvar.", false);
            return;
          }
          vgrPersistedStatus = status;
          vgrPersistedSubstatus = sub;
          vgrObsTransicaoStaged = "";
          V.toast(res.d.message || "Salvo.", true);
          if (modal) modal.hide();
          reload();
        })
        .finally(function () {
          btnSalvar.disabled = false;
        });
    });
  }

  var btnObs = document.getElementById("btnVgrAtendObsAdd");
  if (btnObs) {
    btnObs.addEventListener("click", function () {
      var id = document.getElementById("vgrAtendId").value;
      if (!id) {
        V.toast("Salve o atendimento antes de adicionar observações.", false);
        return;
      }
      if (!document.getElementById("vgrAtendObsContainer")) {
        V.toast("Container de observações não encontrado (vgrAtendObsContainer).", false);
        return;
      }
      var texto = (document.getElementById("vgrAtendObsNova").value || "").trim();
      if (!texto) {
        V.toast("Informe o texto da observação.", false);
        return;
      }
      btnObs.disabled = true;
      V.jsonFetch("/vgr/api/atendimentos/" + encodeURIComponent(id) + "/observacoes", {
        method: "POST",
        body: JSON.stringify({ texto: texto })
      })
        .then(function (res) {
          if (res.status >= 400 || !res.d.success) {
            V.toast((res.d && res.d.message) || "Falha ao adicionar.", false);
            return;
          }
          document.getElementById("vgrAtendObsNova").value = "";
          var lista =
            (res.d.data && (res.d.data.observacoes_log || res.d.data.observacoes)) || null;
          if (lista) {
            renderObsLog(lista);
          } else {
            /* API não devolveu a lista: recarrega o atendimento para renderizar fiel ao banco*/
            V.jsonFetch("/vgr/api/atendimentos/" + encodeURIComponent(id)).then(function (res2) {
              if (res2.status >= 400 || !res2.d.success) return;
              var d2 = res2.d.data || {};
              renderObsLog(d2.observacoes_log || d2.observacoes || []);
            });
          }
          V.toast(res.d.message || "Observação adicionada.", true);
        })
        .finally(function () {
          btnObs.disabled = false;
        });
    });
  }

  /* ============================================================
     MODAL DE VISUALIZAÇÃO — mesmo layout/campos do criar/editar,
     somente leitura (sem botões de ação)
     ============================================================ */
  const VGR_VIEW_FIELD_IDS = [
    "vgrViewIdVgr", "vgrViewAgenda", "vgrViewAgendaStatus", "vgrViewAgendaData",
    "vgrViewAgendaHora", "vgrViewUnidade", "vgrViewNomeUni", "vgrViewCnpjUni",
    "vgrViewEndereco", "vgrViewBairro", "vgrViewCidade", "vgrViewUf", "vgrViewCep",
    "vgrViewLatitude", "vgrViewLongitude", "vgrViewCodigoUni", "vgrViewTipoProjeto",
    "vgrViewTipoUni", "vgrViewTopologia", "vgrViewHa", "vgrViewCliente",
    "vgrViewContatoUni", "vgrViewHostResumo", "vgrViewEqCount", "vgrViewLinkCount",
    "vgrViewAnalista", "vgrViewStatus", "vgrViewSub",
    "vgrViewIdVgrSdwan", "vgrViewIdVgrSdwifi", "vgrViewIdVgrSdlan",
    "vgrViewFieldNome", "vgrViewFieldTel", "vgrViewFieldContratada"
  ];

  function vgrFmtDataBr(s) {
    if (!s) return "";
    var dt = vgrParseDateLocal(s);
    return dt ? V.formatBrDate(dt) : String(s);
  }

  function vgrFmtHoraBr(s) {
    if (!s) return "";
    return V.formatBrTime ? V.formatBrTime(s) : String(s);
  }

  function vgrViewReset() {
    VGR_VIEW_FIELD_IDS.forEach(function (id) {
      setVal(id, "");
    });
    var fEmpty = document.getElementById("vgrViewFieldEmpty");
    if (fEmpty) fEmpty.classList.add("d-none");

    ["vgrViewConnList", "vgrViewEqList", "vgrViewLinkList"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.innerHTML = '<div class="text-muted p-2">Carregando...</div>';
    });
    var obs = document.getElementById("vgrViewObsContainer");
    if (obs) obs.innerHTML = "";
    var hist = document.getElementById("vgrViewHistBody");
    if (hist) hist.innerHTML = "";

    var tabBtn = document.getElementById("vgrViewTabUnidadeBtn");
    if (tabBtn && window.bootstrap && bootstrap.Tab) {
      bootstrap.Tab.getOrCreateInstance(tabBtn).show();
    }
  }

  /** Aba 1: agendamento + unidade + resumo (espelho de fillUnidadePainel/fillFormAtendimento). */
  function vgrViewFillUnidade(u, d, eqs, lks) {
    var stAg = d.status_agendamento || "";
    if (d.agenda_substatus) stAg += (stAg ? " / " : "") + d.agenda_substatus;

    setVal("vgrViewAgenda", d.id_agendamento);
    setVal("vgrViewAgendaStatus", stAg);
    setVal("vgrViewAgendaData", vgrFmtDataBr(d.data_agendamento));
    setVal("vgrViewAgendaHora", vgrFmtHoraBr(d.hora_agendamento));

    setVal("vgrViewIdVgr", u.id_vgr);
    setVal("vgrViewUnidade", d.nome_unidade || u.nome_unidade);
    setVal("vgrViewNomeUni", u.nome_unidade || d.nome_unidade);
    setVal("vgrViewCnpjUni", u.cnpj_unidade);
    setVal("vgrViewContatoUni", u.contato_unidade);
    setVal("vgrViewCodigoUni", u.codigo_unidade);

    /* Selects desabilitados: mesmos tipos/valores do modal de edição */
    var selCli = document.getElementById("vgrViewCliente");
    if (selCli) selCli.innerHTML = "";
    vgrSelectSetValue("vgrViewCliente", u.id_cliente, u.razao_social || d.razao_social);
    vgrSelectSetValue("vgrViewTipoUni", u.tipo_unidade || "");
    vgrSelectSetValue("vgrViewTipoProjeto", u.tipo_projeto || "");
    vgrSelectSetValue("vgrViewTopologia", u.topologia_unidades || "");
    vgrSelectSetValue("vgrViewHa", Number(u.ha) === 1 ? "1" : "0");

    setVal("vgrViewEndereco", u.endereco);
    setVal("vgrViewBairro", u.bairro);
    setVal("vgrViewCidade", u.cidade);
    setVal("vgrViewUf", u.uf);
    setVal("vgrViewCep", u.cep);
    setVal("vgrViewLatitude", u.latitude);
    setVal("vgrViewLongitude", u.longitude);

    var eqAtivos = eqs.filter(function (e) {
      return Number(e.ativo) === 1;
    });
    var wanAtivos = lks.filter(function (l) {
      return Number(l.ativo) === 1 && V.isLinkTipoWan(l.tipo_link);
    });
    setVal("vgrViewHostResumo", (eqAtivos[0] && (eqAtivos[0].hostname || eqAtivos[0].serial)) || "");
    setVal("vgrViewEqCount", eqAtivos.length);
    setVal("vgrViewLinkCount", wanAtivos.length);
  }

  /** Aba 2: atendimento + field + observações. */
  function vgrViewFillAtend(d) {
    setVal("vgrViewAnalista", d.analista_atuante);
    setVal("vgrViewStatus", d.status_atendimento);
    setVal("vgrViewSub", d.substatus_atendimento);
    setVal("vgrViewIdVgrSdwan", d.id_vgr_sdwan);
    setVal("vgrViewIdVgrSdwifi", d.id_vgr_sdwifi);
    setVal("vgrViewIdVgrSdlan", d.id_vgr_sdlan);

    var f = (d.fields || [])[0] || null;
    setVal("vgrViewFieldNome", f && f.snap_nome);
    setVal("vgrViewFieldTel", f && f.snap_telefone);
    setVal("vgrViewFieldContratada", f && f.snap_contratada_nome);
    var fEmpty = document.getElementById("vgrViewFieldEmpty");
    if (fEmpty) fEmpty.classList.toggle("d-none", !!f);

    renderObsLog(d.observacoes_log || d.observacoes || [], "vgrViewObsContainer", true);
  }

  /** Aba 1 (conectividade) e Aba 3 (equipamentos e links): mesmos accordions da edição, em modo "view". */
  function vgrViewRenderInventario(eqs, lks) {
    var connBox = document.getElementById("vgrViewConnList");
    var eqBox = document.getElementById("vgrViewEqList");
    var lkBox = document.getElementById("vgrViewLinkList");

    var connRows = lks.filter(function (r) {
      return V.isLinkTipoUnidade(r.tipo_link);
    });
    var wanRows = lks.filter(function (r) {
      return V.isLinkTipoWan(r.tipo_link);
    });

    if (connBox) {
      vgrResetIncidentListContainer(connBox);
      if (!connRows.length) {
        connBox.innerHTML = '<div class="text-muted p-2">Nenhuma conectividade da unidade.</div>';
      } else {
        connRows.forEach(function (link) {
          renderLinkCardVgr(link, connBox, connRows, "view", "unidade");
        });
      }
    }

    if (eqBox) {
      vgrResetIncidentListContainer(eqBox);
      if (!eqs.length) {
        eqBox.innerHTML = '<div class="text-muted p-2">Nenhum equipamento.</div>';
      } else {
        eqs.forEach(function (eq) {
          renderEqCardVgr(eq, eqBox, eqs, "view");
        });
      }
    }

    if (lkBox) {
      vgrResetIncidentListContainer(lkBox);
      if (!wanRows.length) {
        lkBox.innerHTML = '<div class="text-muted p-2">Nenhum link WAN.</div>';
      } else {
        wanRows.forEach(function (link) {
          renderLinkCardVgr(link, lkBox, wanRows, "view", "wan");
        });
      }
    }
  }

  /** Aba Histórico. */
  function vgrViewRenderHist(logs) {
    var hist = document.getElementById("vgrViewHistBody");
    if (!hist) return;
    hist.innerHTML = "";
    if (!logs.length) {
      hist.innerHTML = '<tr><td colspan="5" class="text-muted">Sem histórico.</td></tr>';
      return;
    }
    logs.forEach(function (r) {
      var tr = document.createElement("tr");
      var st = (r.status_anterior || "—") + " → " + (r.status_novo || "—");
      var sub = (r.substatus_anterior || "—") + " → " + (r.substatus_novo || "—");
      [
        V.formatBrDateTime(r.criado_em),
        st,
        sub,
        r.usuario_nome || r.usuario_re,
        r.observacao
      ].forEach(function (c) {
        var td = document.createElement("td");
        td.textContent = c != null && c !== "" ? String(c) : "—";
        tr.appendChild(td);
      });
      hist.appendChild(tr);
    });
  }

  function openView(id) {
    viewAtendId = id;
    vgrViewReset();
    document.getElementById("modalVgrAtendViewTitle").textContent =
      "Visualizar atendimento #" + id;
    if (modalView) modalView.show();

    V.jsonFetch("/vgr/api/atendimentos/" + encodeURIComponent(id)).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Não encontrado.", false);
        if (modalView) modalView.hide();
        return;
      }

      var d = res.d.data || {};
      var uni = encodeURIComponent(d.id_unidade);

      /* Dados do atendimento aparecem de imediato, sem esperar o inventário. */
      try {
        vgrViewFillAtend(d);
        vgrViewRenderHist(d.status_log || []);
      } catch (e) {
        console.error("[VGR] openView -> atendimento:", e);
      }

      Promise.all([
        V.jsonFetch("/vgr/api/unidades/" + uni),
        V.jsonFetch("/vgr/api/unidades/" + uni + "/equipamentos"),
        V.jsonFetch("/vgr/api/unidades/" + uni + "/links")
      ])
        .then(function (parts) {
          var u = (parts[0].d && parts[0].d.data) || {};
          var eqs = (parts[1].d && parts[1].d.data) || [];
          var lks = (parts[2].d && parts[2].d.data) || [];
          /* Blocos isolados: falha de DOM em um não derruba o outro. */
          try {
            vgrViewFillUnidade(u, d, eqs, lks);
          } catch (e) {
            console.error("[VGR] openView -> unidade:", e);
          }
          try {
            vgrViewRenderInventario(eqs, lks);
          } catch (e) {
            console.error("[VGR] openView -> inventário:", e);
          }
        })
        .catch(function (e) {
          console.error("[VGR] openView:", e);
          V.toast("Falha ao carregar unidade/inventário do atendimento.", false);
        });
    });
  }

  var btnViewEdit = document.getElementById("btnVgrAtendViewEdit");
  if (btnViewEdit) {
    btnViewEdit.addEventListener("click", function () {
      if (modalView) modalView.hide();
      if (viewAtendId) openEdit(viewAtendId);
    });
  }

  /* --- Eq / Link CRUD (inventário da unidade)--- */

  function yn(v) {
    return Number(v) === 1 ? "Sim" : "Não";
  }

  document.getElementById("btnVgrAtendEqNovo").addEventListener("click", vgrAddEquipamentoFixo);
  document.getElementById("btnVgrAtendLinkNovo").addEventListener("click", vgrAddLinkFixo);
  var btnConnNovo = document.getElementById("btnVgrAtendConnNovo");
  if (btnConnNovo) {
    btnConnNovo.addEventListener("click", function () {
      vgrCreateNewLinkInline("unidade");
    });
  }

  document.getElementById("vgrAtendSub").addEventListener("change", function () {
    vgrOnSubstatusChange();
  });

  $("#tblVgrAtendimentos").on("click", ".vgr-atend-view", function () {
    openView(this.getAttribute("data-id"));
  });

  $("#tblVgrAtendimentos").on("click", ".vgr-atend-edit", function () {
    openEdit(this.getAttribute("data-id"));
  });

  $("#tblVgrAtendimentos").on("click", ".vgr-atend-desativar", function () {
    var id = this.getAttribute("data-id");
    if (!window.confirm("Desativar atendimento #" + id + "?")) return;

    V.jsonFetch("/vgr/api/atendimentos/" + encodeURIComponent(id) + "/desativar", {
      method: "POST",
      body: "{}"
    }).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Falha ao desativar.", false);
        return;
      }

      V.toast(res.d.message || "Desativado.", true);
      reload();
    });
  });

  $("#tblVgrAtendimentos").on("click", ".vgr-atend-reativar", function () {
    var id = this.getAttribute("data-id");
    if (!window.confirm("Reativar atendimento #" + id + "?")) return;

    V.jsonFetch("/vgr/api/atendimentos/" + encodeURIComponent(id) + "/reativar", {
      method: "POST",
      body: "{}"
    }).then(function (res) {
      if (res.status >= 400 || !res.d.success) {
        V.toast((res.d && res.d.message) || "Falha ao reativar.", false);
        return;
      }

      V.toast(res.d.message || "Reativado.", true);
      reload();
    });
  });

  /* ============================================================
   Helpers de accordion
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
    btn.className = "accordion-button py-2" + (expanded ? "" : " collapsed");
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

  /* ============================================================
   PASSO 4.2 — Renderização de cards (accordion inline)
   Padrão visual PRODESP adaptado ao schema VGR
   ============================================================ */

  /** Helper: cria <select> de Vendor com opções do VGR */
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

  /** Helper: cria <select> de Tipo de Serviço */
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

  /** Helper: cria <select> de Licença */
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

  /** Helper: cria <select> de Modo de Conexão */
  function vgrBuildModoConexaoSelect(selected) {
    var sel = document.createElement("select");
    sel.className = "form-select form-select-sm";
    var emptyOpt = document.createElement("option");
    emptyOpt.value = "";
    emptyOpt.textContent = "Selecione...";
    sel.appendChild(emptyOpt);
    ["STATIC", "DHCP", "PPPOE", "MPLS"].forEach(function (v) {
      var opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      sel.appendChild(opt);
    });
    if (selected) sel.value = String(selected);
    return sel;
  }

  /** Helper: cria <select> de Operadora */
  function vgrBuildOperadoraSelect(selected) {
    var sel = document.createElement("select");
    sel.className = "form-select form-select-sm";
    var emptyOpt = document.createElement("option");
    emptyOpt.value = "";
    emptyOpt.textContent = "Selecione...";
    sel.appendChild(emptyOpt);
    (V.OPERADORAS || []).forEach(function (v) {
      var opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      sel.appendChild(opt);
    });
    if (selected) sel.value = String(selected);
    return sel;
  }

  /** Helper: campo «Outra operadora» (sentinel OUTROS do core). */
  function vgrBuildOperadoraOutrosInput() {
    var inp = document.createElement("input");
    inp.type = "text";
    inp.className = "form-control form-control-sm text-uppercase d-none";
    inp.maxLength = 50;
    inp.autocomplete = "off";
    inp.placeholder = "Ex.: VTAL, EMBRATEL";
    return inp;
  }

  /** Mostra a coluna «Outra operadora» só quando o select está em OUTROS. */
  function vgrBindOutrosCol(operSel, outrosCol) {
    function sync() {
      outrosCol.classList.toggle("d-none", String(operSel.value || "").toUpperCase() !== "OUTROS");
    }
    operSel.addEventListener("change", sync);
    sync();
  }

  /** Inputs extras da conectividade (subrede + range), padrão do modal da unidade. */
  function vgrBuildConnExtraInputs(linkObj) {
    function mk(value, placeholder) {
      var inp = document.createElement("input");
      inp.className = "form-control form-control-sm";
      inp.autocomplete = "off";
      inp.maxLength = 50;
      inp.value = value || "";
      if (placeholder) inp.placeholder = placeholder;
      return inp;
    }
    return {
      subrede: mk(linkObj && linkObj.subrede, "Endereço de rede (ex.: 10.1.2.0)"),
      rangeStart: mk(linkObj && linkObj.range_start, ""),
      rangeEnd: mk(linkObj && linkObj.range_end, "")
    };
  }

  /** Visibilidade das colunas da conectividade pela regra única (VgrDt.linkFieldVisibility). */
  function vgrBindConnVisibility(tipoSel, cols) {
    function sync() {
      var vis = V.linkFieldVisibility(tipoSel.value, "", "");
      if (cols.ip) cols.ip.classList.toggle("d-none", !vis.ip);
      if (cols.mascara) cols.mascara.classList.toggle("d-none", !vis.mascara);
      if (cols.subrede) cols.subrede.classList.toggle("d-none", !vis.subrede);
      if (cols.rangeStart) cols.rangeStart.classList.toggle("d-none", !vis.range);
      if (cols.rangeEnd) cols.rangeEnd.classList.toggle("d-none", !vis.range);
      if (cols.vlan) cols.vlan.classList.toggle("d-none", !vis.vlan);
    }
    tipoSel.addEventListener("change", sync);
    sync();
  }

  /** Caixa de pendências VIVO (aviso, não bloqueio) dentro do accordion. */
  function vgrBuildPendenciasBox() {
    var box = document.createElement("div");
    box.className = "col-12 alert alert-warning small py-2 px-3 mb-0 d-none";
    box.setAttribute("role", "status");
    return box;
  }

  /**
   * Valida o payload de link inline com as mesmas regras do backend.
   * Retorna o payload limpo para a API ou null (já exibiu o erro em toast).
   */
  function vgrPrepareLinkPayload(payload, live) {
    if (!R) return payload;
    R.cleanLinkPayload(payload);
    var err = R.validateLinkPayload(payload);
    if (err) {
      V.toast(err, false);
      if (live) live.refresh();
      return null;
    }
    return R.stripInternal(payload);
  }

  /* ============================================================
     LINK WAN — formulário dinâmico por modo (padrão PRODESP)
     Modo (STATIC / MPLS / DHCP / PPPoE) decide os campos, como o
     handleLinkTypeChange do PRODESP (.link-field-wrapper[data-link-type]):
       STATIC/MPLS → IP WAN, Gateway, Máscara (+ ID VGR e porta se VIVO)
       DHCP        → sem IP (obtido do provedor)
       PPPoE       → usuário e senha
     Comuns: Equipamento, Designador (LP), Operadora, VLAN, Velocidade.
     Campo ocultado por troca de modo/operadora tem o valor limpo.
     ============================================================ */
  var VGR_WAN_MODOS = [
    { value: "STATIC", label: "STATIC" },
    { value: "MPLS", label: "MPLS" },
    { value: "DHCP", label: "DHCP" },
    { value: "PPPOE", label: "PPPoE" }
  ];

  function vgrWanInput(value, opts) {
    opts = opts || {};
    var inp = document.createElement("input");
    inp.type = opts.type || "text";
    inp.className = "form-control form-control-sm";
    inp.autocomplete = opts.type === "password" ? "new-password" : "off";
    if (opts.maxLength) inp.maxLength = opts.maxLength;
    if (opts.placeholder) inp.placeholder = opts.placeholder;
    if (opts.inputMode) inp.inputMode = opts.inputMode;
    inp.value = value != null ? String(value) : "";
    return inp;
  }

  /**
   * Monta o formulário WAN dentro do grid do accordion.
   * opts.isEdit: edição (PPPoE em branco = manter credenciais gravadas).
   * Retorna { eqSel, live, collect() } — collect() devolve o payload já
   * validado (mesmas regras da API) ou null (erro exibido em toast).
   */
  function vgrBuildWanLinkForm(grid, linkObj, opts) {
    linkObj = linkObj || {};
    opts = opts || {};
    var isEdit = !!opts.isEdit;

    /* tipo_link fixo: o accordion de Links WAN só cria/edita WAN */
    var tipoHidden = document.createElement("input");
    tipoHidden.type = "hidden";
    tipoHidden.value = "WAN";

    var eqSel = document.createElement("select");
    eqSel.className = "form-select form-select-sm";
    eqSel.add(new Option("Carregando...", ""));

    var modoSel = document.createElement("select");
    modoSel.className = "form-select form-select-sm";
    var ph = new Option("Selecione o tipo...", "");
    ph.disabled = true;
    modoSel.add(ph);
    VGR_WAN_MODOS.forEach(function (m) {
      modoSel.add(new Option(m.label, m.value));
    });
    var modoAtual = String(linkObj.modo_conexao || "").toUpperCase();
    modoSel.value = modoAtual;
    if (!modoSel.value) modoSel.selectedIndex = 0;

    var operSel = vgrBuildOperadoraSelect("");
    var operOutrosInp = vgrBuildOperadoraOutrosInput();
    if (R) R.fillOperadora(operSel, operOutrosInp, linkObj.operadora || "");
    else operSel.value = linkObj.operadora || "";

    var designInp = vgrWanInput(linkObj.designador, {
      maxLength: 100,
      placeholder: "LP (VIVO: 15 dígitos)"
    });
    var vlanInp = vgrWanInput(linkObj.vlan, { maxLength: 50, inputMode: "numeric", placeholder: "1 a 4094" });
    var velInp = vgrWanInput(linkObj.velocidade, { maxLength: 50 });
    var idVgrInp = vgrWanInput(linkObj.id_vgr_link, {
      maxLength: 64,
      inputMode: "numeric",
      placeholder: "Mín. 7 dígitos"
    });
    var portaInp = vgrWanInput(linkObj.identificador, { maxLength: 50, placeholder: "Porta conectada (ex.: wan1)" });
    var ipInp = vgrWanInput(linkObj.ip_address, { maxLength: 50, placeholder: "Ex.: 187.51.205.114 ou /30" });
    var gwInp = vgrWanInput(linkObj.gateway, { maxLength: 50 });
    var maskInp = vgrWanInput(linkObj.mascara, { maxLength: 50, placeholder: "Ex.: 255.255.255.252" });
    var userInp = vgrWanInput("", {
      maxLength: 255,
      placeholder: isEdit ? "Em branco = manter o atual" : ""
    });
    var passInp = vgrWanInput("", {
      type: "password",
      maxLength: 255,
      placeholder: isEdit ? "Em branco = manter a atual" : ""
    });

    var col = function (label, ctrl, cls) {
      return vgrCreateIncidentFieldCol(label, ctrl, cls || "col-md-4 col-sm-6");
    };
    var hintTxt = function (text) {
      var c = document.createElement("div");
      c.className = "col-12";
      var s = document.createElement("small");
      s.className = "text-muted";
      s.textContent = text;
      c.appendChild(s);
      return c;
    };

    var cols = {
      outros: col("Outra operadora *", operOutrosInp),
      idVgr: col("ID VGR do Link *", idVgrInp),
      porta: col("Identificação da Porta *", portaInp),
      ip: col("IP WAN *", ipInp),
      gateway: col("Gateway *", gwInp),
      mascara: col("Máscara *", maskInp),
      ipHint: hintTxt(
        "Operadora VIVO: STATIC → último octeto par /30, ímpar /31; MPLS → /29; gateway = IP WAN − 1. " +
          "Digite o IP com /prefixo para preencher a máscara."
      ),
      dhcpHint: hintTxt("DHCP: o IP WAN é obtido automaticamente do provedor — não há IP, gateway ou máscara a informar."),
      pppoeUser: col("PPPoE User *", userInp),
      pppoePass: col("PPPoE Password *", passInp)
    };
    var pendBox = vgrBuildPendenciasBox();

    grid.append(
      col("Equipamento *", eqSel),
      col("Tipo (modo) *", modoSel),
      col("Designador (LP)", designInp),
      col("Operadora", operSel),
      cols.outros,
      cols.idVgr,
      cols.porta,
      col("VLAN", vlanInp),
      col("Velocidade (Mbps)", velInp),
      cols.ip,
      cols.gateway,
      cols.mascara,
      cols.ipHint,
      cols.dhcpHint,
      cols.pppoeUser,
      cols.pppoePass,
      pendBox
    );

    var live = R
      ? R.bindLinkLive({
          tipo: tipoHidden,
          modo: modoSel,
          operadora: operSel,
          operadoraOutros: operOutrosInp,
          idVgr: idVgrInp,
          porta: portaInp,
          designador: designInp,
          ip: ipInp,
          mascara: maskInp,
          gateway: gwInp,
          vlan: vlanInp,
          vel: velInp,
          pendencias: pendBox
        })
      : null;

    function operadoraAtual() {
      return R ? R.readOperadora(operSel, operOutrosInp).operadora : operSel.value;
    }

    /* Mostra/oculta por modo e operadora; userChange=true limpa o que sumiu. */
    function sync(userChange) {
      var modo = String(modoSel.value || "").toUpperCase();
      var vis = V.linkFieldVisibility("WAN", modo, operadoraAtual());
      var mapa = [
        [cols.outros, vis.operadoraOutros, [operOutrosInp]],
        [cols.idVgr, vis.idVgr, [idVgrInp]],
        [cols.porta, vis.porta, [portaInp]],
        [cols.ip, vis.ip, [ipInp]],
        [cols.gateway, vis.gateway, [gwInp]],
        [cols.mascara, vis.mascara, [maskInp]],
        [cols.ipHint, vis.isStaticMpls, []],
        [cols.dhcpHint, modo === "DHCP", []],
        [cols.pppoeUser, vis.pppoe, [userInp]],
        [cols.pppoePass, vis.pppoe, [passInp]]
      ];
      mapa.forEach(function (m) {
        m[0].classList.toggle("d-none", !m[1]);
        if (!m[1] && userChange) {
          m[2].forEach(function (inp) {
            if (inp.value) inp.value = "";
          });
        }
      });
      if (!(vis.isStaticMpls && operadoraAtual() === "VIVO")) pendBox.classList.add("d-none");
      if (live) live.refresh();
    }

    modoSel.addEventListener("change", function () {
      sync(true);
    });
    operSel.addEventListener("change", function () {
      sync(true);
    });
    operOutrosInp.addEventListener("input", function () {
      sync(false);
    });

    sync(false);
    if (live) velInp.dispatchEvent(new Event("blur"));

    var eqPromise = vgrLoadEqOptionsIntoSelect(eqSel, linkObj.id_equipamento || null);

    function collect() {
      if (!modoSel.value) {
        V.toast("Selecione o tipo (modo) do link: STATIC, MPLS, DHCP ou PPPoE.", false);
        modoSel.classList.add("is-invalid");
        return null;
      }
      modoSel.classList.remove("is-invalid");
      if (!eqSel.value) {
        V.toast("Selecione o equipamento.", false);
        return null;
      }
      var opr = R
        ? R.readOperadora(operSel, operOutrosInp)
        : { select: operSel.value, operadora: operSel.value, outros: "" };
      var payload = {
        tipo_link: "WAN",
        modo_conexao: modoSel.value,
        operadora: opr.operadora,
        operadora_outros: opr.outros,
        _operadora_select: opr.select,
        /* edição: credencial PPPoE já gravada é conferida no servidor (has_pppoe_*) */
        _has_pppoe_user: isEdit,
        _has_pppoe_pass: isEdit,
        id_vgr_link: (idVgrInp.value || "").trim(),
        identificador: (portaInp.value || "").trim(),
        designador: (designInp.value || "").trim(),
        ip_address: (ipInp.value || "").trim(),
        mascara: (maskInp.value || "").trim(),
        gateway: (gwInp.value || "").trim(),
        vlan: (vlanInp.value || "").trim(),
        velocidade: (velInp.value || "").trim(),
        id_equipamento: eqSel.value
      };
      if ((userInp.value || "").trim()) payload.pppoe_user = userInp.value.trim();
      if ((passInp.value || "").trim()) payload.pppoe_pass = passInp.value.trim();
      return vgrPrepareLinkPayload(payload, live);
    }

    return { eqSel: eqSel, eqPromise: eqPromise, live: live, collect: collect };
  }

  /** Campos exibidos na visualização do link WAN — só os do modo gravado. */
  function vgrWanViewFields(linkObj) {
    var modo = String(linkObj.modo_conexao || "").toUpperCase();
    var vis = V.linkFieldVisibility("WAN", modo, linkObj.operadora);
    var modoLabel = modo === "PPPOE" ? "PPPoE" : modo;
    var out = [
      ["ID", linkObj.id_link],
      ["Tipo (modo)", modoLabel],
      ["Designador (LP)", linkObj.designador],
      ["Operadora", linkObj.operadora],
      ["VLAN", linkObj.vlan],
      ["Velocidade (Mbps)", linkObj.velocidade]
    ];
    if (vis.idVgr || linkObj.id_vgr_link) out.push(["ID VGR do Link", linkObj.id_vgr_link]);
    if (vis.porta || linkObj.identificador) out.push(["Porta", linkObj.identificador]);
    if (vis.isStaticMpls) {
      out.push(["IP WAN", linkObj.ip_address], ["Gateway", linkObj.gateway], ["Máscara", linkObj.mascara]);
    }
    if (modo === "DHCP") out.push(["IP WAN", "Obtido via DHCP"]);
    if (vis.pppoe) out.push(["PPPoE", "Credenciais gravadas no servidor (cifradas)"]);
    return out;
  }

  /**
   * Botão de lixeira (desativar) — ou de reativar quando o item já está inativo.
   * kind: "equipamentos" | "links". Recarrega a unidade ao concluir.
   */
  function vgrBuildToggleAtivoButton(kind, id, ativo, label) {
    var isAtivo = Number(ativo) === 1;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = isAtivo ? "btn btn-sm btn-outline-danger" : "btn btn-sm btn-outline-success";
    btn.innerHTML = isAtivo ? '<i class="fas fa-trash"></i>' : '<i class="fas fa-undo"></i>';
    btn.title = (isAtivo ? "Desativar " : "Reativar ") + label;
    btn.onclick = function (e) {
      e.stopPropagation();
      var uni = currentUnidadeId();
      if (!uni) return;
      if (isAtivo && !window.confirm("Desativar este " + label.toLowerCase() + "?")) return;
      btn.disabled = true;
      V.jsonFetch(
        "/vgr/api/" + kind + "/" + encodeURIComponent(id) + (isAtivo ? "/desativar" : "/reativar"),
        { method: "POST" }
      )
        .then(function (res) {
          if (res.status >= 400 || !res.d.success) {
            V.toast((res.d && res.d.message) || "Falha ao atualizar o registro.", false);
            return;
          }
          V.toast(res.d.message || (isAtivo ? "Desativado." : "Reativado."), true);
          loadUnidadeDetalhe(uni);
        })
        .finally(function () {
          btn.disabled = false;
        });
    };
    return btn;
  }

  /** Helper: anexa ícone de copiar a uma coluna readonly */
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

  /** Helper: carrega equipamentos ativos da unidade em um <select> */
  function vgrLoadEqOptionsIntoSelect(selectEl, selectedId) {
    var uni = currentUnidadeId();
    selectEl.innerHTML = "";
    return V.jsonFetch(
      "/vgr/api/unidades/" + encodeURIComponent(uni) + "/equipamentos"
    ).then(function (res) {
      var rows = ((res.d && res.d.data) || []).filter(function (r) {
        return Number(r.ativo) === 1;
      });
      rows.forEach(function (r) {
        var opt = document.createElement("option");
        opt.value = String(r.id_equipamento);
        opt.textContent =
          (r.hostname || r.serial || "#" + r.id_equipamento) +
          (r.tipo_servico ? " (" + r.tipo_servico + ")" : "");
        selectEl.appendChild(opt);
      });
      if (selectedId) selectEl.value = String(selectedId);
      return rows;
    });
  }

  /* ============================================================
    RENDERIZAÇÃO DE EQUIPAMENTO (accordion inline)
  ============================================================ */
  function renderEqCardVgr(eqObj, containerEl, context, mode) {
    if (!containerEl) {
      console.error("Container de equipamentos não encontrado.", containerEl);
      return;
    }
    var accordion = vgrEnsureIncidentAccordionList(containerEl);
    if (!accordion) return;

    var summary = vgrIncidentSummaryText([
      eqObj.hostname || eqObj.serial,
      eqObj.vendor,
      eqObj.modelo
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

    /* --- MODO VISUALIZAÇÃO --- */
    var renderViewMode = function () {
      showCollapse(false);
      item.classList.remove("prodesp-incident-item-editing");
      shell.toggleBtn.textContent = summary;
      grid.innerHTML = "";

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

      if (mode === "view") {
        actionsSlot.innerHTML = "";
        return;
      }

      var editButton = document.createElement("button");
      editButton.innerHTML = '<i class="fas fa-pencil-alt"></i>';
      editButton.type = "button";
      editButton.className = "btn btn-sm btn-outline-primary";
      editButton.title = "Editar Equipamento";
      editButton.onclick = function (e) { e.stopPropagation(); renderEditMode(); };

      actionsSlot.innerHTML = "";
      actionsSlot.appendChild(vgrCreateIncidentActionsGroup([editButton, vgrBuildToggleAtivoButton("equipamentos", eqObj.id_equipamento, eqObj.ativo, "Equipamento")]));
    };

    /* --- MODO EDIÇÃO --- */
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
      tktInp.maxLength = 7;
      tktInp.inputMode = "numeric";
      tktInp.placeholder = "Ex.: 1680355";
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
      var liveEqInline = R
        ? R.bindEqLive({
            serial: serialInp,
            vendor: vendorSel,
            modelo: modeloInp,
            hostname: hostnameInp,
            tktNoc: tktInp,
            idVgr: idVgrInp
          })
        : null;
      if (liveEqInline) liveEqInline.refresh();

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
          tkt_noc: (tktInp.value || "").trim()
        };
        var errEq = R ? R.validateEqPayload(payload) : null;
        if (!errEq && payload.tkt_noc && PF && PF.validateTicketNoc) {
          errEq = PF.validateTicketNoc(payload.tkt_noc);
        }
        if (errEq) {
          V.toast(errEq, false);
          if (liveEqInline) liveEqInline.refresh();
          return;
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

  /* ============================================================
    RENDERIZAÇÃO DE LINK (accordion inline)
    linkScope: "wan" ou "unidade"
    ============================================================ */
  /**
   * Card de link no accordion.
   * Antes a assinatura tinha 4 parâmetros e as chamadas enviavam 5
   * (link, container, rows, "edit", escopo): o escopo chegava como "edit",
   * isWan ficava false e TODO link abria como conectividade LAN.
   * O tipo_link gravado é a fonte da verdade; o escopo é só reforço.
   */
  function renderLinkCardVgr(linkObj, containerEl, context, mode, linkScope) {
    if (!containerEl) {
      console.error("Container de links não encontrado.", containerEl);
      return;
    }
    var accordion = vgrEnsureIncidentAccordionList(containerEl);
    if (!accordion) return;

    var isWan = V.isLinkTipoWan(linkObj.tipo_link) || (!linkObj.tipo_link && linkScope === "wan");

    var summary = vgrIncidentSummaryText(
      isWan
        ? [
            linkObj.modo_conexao === "PPPOE" ? "PPPoE" : linkObj.modo_conexao || "WAN",
            linkObj.designador || linkObj.identificador,
            linkObj.operadora,
            linkObj.ip_address
          ]
        : [linkObj.tipo_link, linkObj.ip_address, linkObj.vlan ? "VLAN " + linkObj.vlan : ""]
    );

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

    /* --- MODO VISUALIZAÇÃO --- */
    var renderViewMode = function () {
      showCollapse(false);
      item.classList.remove("prodesp-incident-item-editing");
      shell.toggleBtn.textContent = summary;
      grid.innerHTML = "";

      if (isWan) {
        /* só os campos do modo gravado (STATIC/MPLS/DHCP/PPPoE) */
        vgrWanViewFields(linkObj).forEach(function (f) {
          grid.appendChild(vgrCreateIncidentReadonlyCol(f[0], f[1]));
        });
      } else {
        grid.appendChild(vgrCreateIncidentReadonlyCol("ID", linkObj.id_link));
        grid.appendChild(vgrCreateIncidentReadonlyCol("Tipo", linkObj.tipo_link));
        grid.appendChild(vgrCreateIncidentReadonlyCol("IP", linkObj.ip_address));
        grid.appendChild(vgrCreateIncidentReadonlyCol("Máscara", linkObj.mascara));
        grid.appendChild(vgrCreateIncidentReadonlyCol("Subrede", linkObj.subrede));
        if (linkObj.range_start || linkObj.range_end) {
          grid.appendChild(
            vgrCreateIncidentReadonlyCol(
              "Range",
              (linkObj.range_start || "?") + " – " + (linkObj.range_end || "?")
            )
          );
        }
        grid.appendChild(vgrCreateIncidentReadonlyCol("VLAN", linkObj.vlan));
      }
      grid.appendChild(vgrCreateIncidentReadonlyCol("Ativo", V.yesNo(linkObj.ativo)));

      if (mode === "view") {
        actionsSlot.innerHTML = "";
        return;
      }

      var editButton = document.createElement("button");
      editButton.innerHTML = '<i class="fas fa-pencil-alt"></i>';
      editButton.type = "button";
      editButton.className = "btn btn-sm btn-outline-primary";
      editButton.title = isWan ? "Editar Link WAN" : "Editar Conectividade";
      editButton.onclick = function (e) { e.stopPropagation(); renderEditMode(); };

      actionsSlot.innerHTML = "";
      actionsSlot.appendChild(
        vgrCreateIncidentActionsGroup([
          editButton,
          vgrBuildToggleAtivoButton("links", linkObj.id_link, linkObj.ativo, isWan ? "Link WAN" : "Conectividade")
        ])
      );
    };

    /* --- MODO EDIÇÃO --- */
    var renderEditMode = function () {
      showCollapse(true);
      item.classList.add("prodesp-incident-item-editing");
      shell.toggleBtn.textContent = isWan ? "Editando link WAN…" : "Editando conectividade…";
      grid.innerHTML = "";

      if (isWan) {
        /* ===== LINK WAN — campos dinâmicos por modo (padrão PRODESP) ===== */
        var wanForm = vgrBuildWanLinkForm(grid, linkObj, { isEdit: true });
        wanForm.eqPromise.then(function (rows) {
          if (!rows.length) {
            wanForm.eqSel.innerHTML = "";
            wanForm.eqSel.add(new Option("Nenhum equipamento ativo", ""));
          }
        });

        var saveBtn = document.createElement("button");
        saveBtn.type = "button";
        saveBtn.innerHTML = '<i class="fas fa-check me-1"></i>Salvar';
        saveBtn.className = "btn btn-sm btn-success";
        saveBtn.title = "Salvar edição do link";
        saveBtn.onclick = function (e) {
          e.stopPropagation();
          var payload = wanForm.collect();
          if (!payload) return;

          var uni = currentUnidadeId();
          if (!uni) {
            V.toast("Unidade não selecionada.", false);
            return;
          }
          var url = "/vgr/api/links/" + encodeURIComponent(linkObj.id_link);
          saveBtn.disabled = true;
          V.jsonFetch(url, { method: "PUT", body: JSON.stringify(payload) })
            .then(function (res) {
              if (res.status >= 400 || !res.d.success) {
                V.toast((res.d && res.d.message) || "Falha ao salvar link.", false);
                return;
              }
              V.toast(res.d.message || "Link salvo.", true);
              if (R) R.toastAvisos(res.d.avisos);
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

      } else {
        /* ===== CONECTIVIDADE DA UNIDADE ===== */
        var tipoConnSel = document.createElement("select");
        tipoConnSel.className = "form-select form-select-sm";
        V.fillTipoLinkSelect(tipoConnSel, "unidade", linkObj.tipo_link || "LAN");

        var ipConnInp = document.createElement("input");
        ipConnInp.className = "form-control form-control-sm";
        ipConnInp.value = linkObj.ip_address || "";

        var maskConnInp = document.createElement("input");
        maskConnInp.className = "form-control form-control-sm";
        maskConnInp.value = linkObj.mascara || "";

        var vlanConnInp = document.createElement("input");
        vlanConnInp.className = "form-control form-control-sm";
        vlanConnInp.value = linkObj.vlan || "";

        var connExtra = vgrBuildConnExtraInputs(linkObj);
        var connCols = {
          ip: vgrCreateIncidentFieldCol("IP", ipConnInp, "col-md-6"),
          mascara: vgrCreateIncidentFieldCol("Máscara", maskConnInp, "col-md-6"),
          subrede: vgrCreateIncidentFieldCol("Subrede", connExtra.subrede, "col-md-6"),
          rangeStart: vgrCreateIncidentFieldCol("Início do range", connExtra.rangeStart, "col-md-6"),
          rangeEnd: vgrCreateIncidentFieldCol("Fim do range", connExtra.rangeEnd, "col-md-6"),
          vlan: vgrCreateIncidentFieldCol("VLAN", vlanConnInp, "col-md-6")
        };
        grid.append(
          vgrCreateIncidentFieldCol("Tipo", tipoConnSel, "col-md-6"),
          connCols.ip,
          connCols.mascara,
          connCols.subrede,
          connCols.rangeStart,
          connCols.rangeEnd,
          connCols.vlan
        );
        vgrBindConnVisibility(tipoConnSel, connCols);
        /* Calculadora IP/máscara/subrede/range ao vivo (mesma regra do modal da unidade) */
        var liveConn = R
          ? R.bindLinkLive({
              tipo: tipoConnSel,
              ip: ipConnInp,
              mascara: maskConnInp,
              subrede: connExtra.subrede,
              rangeStart: connExtra.rangeStart,
              rangeEnd: connExtra.rangeEnd,
              vlan: vlanConnInp
            })
          : null;
        if (liveConn) liveConn.refresh();

        var saveConnBtn = document.createElement("button");
        saveConnBtn.type = "button";
        saveConnBtn.innerHTML = '<i class="fas fa-check me-1"></i>Salvar';
        saveConnBtn.className = "btn btn-sm btn-success";
        saveConnBtn.title = "Salvar edição da conectividade";
        saveConnBtn.onclick = function (e) {
          e.stopPropagation();
          var payload = {
            tipo_link: tipoConnSel.value,
            modo_conexao: null,
            operadora: "",
            id_vgr_link: "",
            identificador: "",
            designador: "",
            ip_address: (ipConnInp.value || "").trim(),
            mascara: (maskConnInp.value || "").trim(),
            gateway: "",
            subrede: (connExtra.subrede.value || "").trim(),
            range_start: (connExtra.rangeStart.value || "").trim(),
            range_end: (connExtra.rangeEnd.value || "").trim(),
            vlan: (vlanConnInp.value || "").trim(),
            velocidade: "",
            id_equipamento: null
          };
          payload = vgrPrepareLinkPayload(payload, liveConn);
          if (!payload) return;
          var uni = currentUnidadeId();
          if (!uni) {
            V.toast("Unidade não selecionada.", false);
            return;
          }
          var url = "/vgr/api/links/" + encodeURIComponent(linkObj.id_link);
          saveConnBtn.disabled = true;
          V.jsonFetch(url, { method: "PUT", body: JSON.stringify(payload) })
            .then(function (res) {
              if (res.status >= 400 || !res.d.success) {
                V.toast((res.d && res.d.message) || "Falha ao salvar conectividade.", false);
                return;
              }
              V.toast(res.d.message || "Conectividade salva.", true);
              loadUnidadeDetalhe(uni);
            })
            .finally(function () {
              saveConnBtn.disabled = false;
            });
        };

        var cancelConnBtn = document.createElement("button");
        cancelConnBtn.type = "button";
        cancelConnBtn.innerHTML = '<i class="fas fa-times me-1"></i>Cancelar';
        cancelConnBtn.className = "btn btn-sm btn-secondary";
        cancelConnBtn.title = "Cancelar edição";
        cancelConnBtn.onclick = function (e) { e.stopPropagation(); renderViewMode(); };

        actionsSlot.innerHTML = "";
        actionsSlot.appendChild(vgrCreateIncidentActionsGroup([saveConnBtn, cancelConnBtn]));
      }
    };

    accordion.appendChild(item);
    renderViewMode();
  }

  /* ============================================================
   PASSO 4.3 — Criação inline (botões "Novo")
   ============================================================ */

  /* ------------------------------------------------------------
     Formulários FIXOS de Equipamento e Link (padrão PRODESP):
     campos sempre visíveis no topo da aba + botão «Adicionar»;
     os itens já cadastrados ficam na lista (accordion) abaixo,
     com edição inline pelo lápis.
     ------------------------------------------------------------ */
  var eqFixedForm = null;
  var linkFixedForm = null;

  function vgrSetFixedFormEmpty(gridId) {
    var g = document.getElementById(gridId);
    if (g) g.innerHTML = '<div class="col-12 text-muted small">Selecione uma unidade.</div>';
  }

  /** Monta (ou remonta limpo) o formulário fixo de equipamento. */
  function vgrMountEqForm() {
    var grid = document.getElementById("vgrAtendEqFormGrid");
    if (!grid) return;
    eqFixedForm = null;
    var uni = currentUnidadeId();
    if (!uni) {
      vgrSetFixedFormEmpty("vgrAtendEqFormGrid");
      return;
    }
    grid.innerHTML = "";

    function mkInp(extra) {
      var i = document.createElement("input");
      i.className = "form-control form-control-sm";
      i.autocomplete = "off";
      if (extra) Object.keys(extra).forEach(function (k) { i[k] = extra[k]; });
      return i;
    }
    var idVgrInp = mkInp();
    var serialInp = mkInp();
    var vendorSel = vgrBuildVendorSelect("");
    var modeloInp = mkInp();
    var hostnameInp = mkInp();
    var tipoSel = vgrBuildTipoServicoSelect("");
    var licencaSel = vgrBuildLicencaSelect("");
    var tktInp = mkInp({ maxLength: 7, inputMode: "numeric", placeholder: "Ex.: 1680355" });

    grid.append(
      vgrCreateIncidentFieldCol("ID VGR", idVgrInp, "col-md-4 col-sm-6"),
      vgrCreateIncidentFieldCol("Serial *", serialInp, "col-md-4 col-sm-6"),
      vgrCreateIncidentFieldCol("Vendor", vendorSel, "col-md-4 col-sm-6"),
      vgrCreateIncidentFieldCol("Modelo", modeloInp, "col-md-4 col-sm-6"),
      vgrCreateIncidentFieldCol("Hostname", hostnameInp, "col-md-4 col-sm-6"),
      vgrCreateIncidentFieldCol("Tipo Serviço", tipoSel, "col-md-4 col-sm-6"),
      vgrCreateIncidentFieldCol("Licença", licencaSel, "col-md-4 col-sm-6"),
      vgrCreateIncidentFieldCol("TKT NOC", tktInp, "col-md-4 col-sm-6")
    );
    var live = R
      ? R.bindEqLive({
          serial: serialInp,
          vendor: vendorSel,
          modelo: modeloInp,
          hostname: hostnameInp,
          tktNoc: tktInp,
          idVgr: idVgrInp
        })
      : null;

    eqFixedForm = {
      /** Valida e devolve o payload (ou null com o erro em toast). */
      collect: function () {
        var serial = (serialInp.value || "").trim();
        if (!serial) {
          V.toast("Serial é obrigatório.", false);
          serialInp.focus();
          return null;
        }
        var payload = {
          serial: serial,
          vendor: vendorSel.value,
          modelo: (modeloInp.value || "").trim(),
          hostname: (hostnameInp.value || "").trim(),
          id_vgr: (idVgrInp.value || "").trim() || null,
          tipo_servico: tipoSel.value || null,
          licenca: licencaSel.value,
          tkt_noc: (tktInp.value || "").trim()
        };
        var errEq = R ? R.validateEqPayload(payload) : null;
        if (!errEq && payload.tkt_noc && PF && PF.validateTicketNoc) {
          errEq = PF.validateTicketNoc(payload.tkt_noc);
        }
        if (errEq) {
          V.toast(errEq, false);
          if (live) live.refresh();
          return null;
        }
        return payload;
      }
    };
  }

  /** Monta (ou remonta limpo) o formulário fixo de link WAN (campos por modo). */
  function vgrMountLinkForm() {
    var grid = document.getElementById("vgrAtendLinkFormGrid");
    if (!grid) return;
    linkFixedForm = null;
    var uni = currentUnidadeId();
    if (!uni) {
      vgrSetFixedFormEmpty("vgrAtendLinkFormGrid");
      return;
    }
    grid.innerHTML = "";
    linkFixedForm = vgrBuildWanLinkForm(grid, null, { isEdit: false });
  }

  function vgrAddEquipamentoFixo() {
    var uni = currentUnidadeId();
    if (!uni) {
      V.toast("Selecione a unidade antes.", false);
      return;
    }
    if (!eqFixedForm) return;
    var payload = eqFixedForm.collect();
    if (!payload) return;
    var btn = document.getElementById("btnVgrAtendEqNovo");
    if (btn) btn.disabled = true;
    V.jsonFetch("/vgr/api/unidades/" + encodeURIComponent(uni) + "/equipamentos", {
      method: "POST",
      body: JSON.stringify(payload)
    })
      .then(function (res) {
        if (res.status >= 400 || !res.d.success) {
          V.toast((res.d && res.d.message) || "Falha ao salvar equipamento.", false);
          return;
        }
        V.toast(res.d.message || "Equipamento adicionado.", true);
        loadUnidadeDetalhe(uni); /* recarrega a lista e remonta os formulários limpos */
      })
      .finally(function () {
        if (btn) btn.disabled = false;
      });
  }

  function vgrAddLinkFixo() {
    var uni = currentUnidadeId();
    if (!uni) {
      V.toast("Selecione a unidade antes.", false);
      return;
    }
    if (!linkFixedForm) return;
    linkFixedForm.eqPromise.then(function (rows) {
      if (!rows.length) {
        V.toast("Cadastre um equipamento ativo antes de adicionar um link WAN.", false);
        return;
      }
      var payload = linkFixedForm.collect();
      if (!payload) return;
      var btn = document.getElementById("btnVgrAtendLinkNovo");
      if (btn) btn.disabled = true;
      V.jsonFetch("/vgr/api/unidades/" + encodeURIComponent(uni) + "/links", {
        method: "POST",
        body: JSON.stringify(payload)
      })
        .then(function (res) {
          if (res.status >= 400 || !res.d.success) {
            V.toast((res.d && res.d.message) || "Falha ao salvar link.", false);
            return;
          }
          V.toast(res.d.message || "Link WAN adicionado.", true);
          if (R) R.toastAvisos(res.d.avisos);
          loadUnidadeDetalhe(uni);
        })
        .finally(function () {
          if (btn) btn.disabled = false;
        });
    });
  }

  /**
   * Cria accordion em branco para novo link.
   * @param {string} linkScope - "wan" ou "unidade"
   */
  function vgrCreateNewLinkInline(linkScope) {
  var uni = currentUnidadeId();
  if (!uni) {
    V.toast("Selecione a unidade antes.", false);
    return;
  }

  var isWan = linkScope === "wan";
  var container = document.getElementById(isWan ? "vgrAtendLinkList" : "vgrAtendConnList");
  if (!container) return;

  var accordion = vgrEnsureIncidentAccordionList(container);
  if (!accordion) return;

  var title = isWan ? "Novo link WAN…" : "Nova conectividade…";
  var shell = vgrBuildIncidentAccordionItem(title, accordion.id);
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
  shell.toggleBtn.textContent = title;

  if (isWan) {
    /* ===== NOVO LINK WAN — campos dinâmicos por modo (padrão PRODESP) ===== */
    var wanForm = vgrBuildWanLinkForm(grid, null, { isEdit: false });
    /* Sem equipamento ativo não há link WAN (equipamento é obrigatório) */
    wanForm.eqPromise.then(function (rows) {
      if (!rows.length) {
        V.toast("Cadastre um equipamento ativo antes de criar link WAN.", false);
        item.remove();
      }
    });

    var saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.innerHTML = '<i class="fas fa-check me-1"></i>Salvar';
    saveBtn.className = "btn btn-sm btn-success";
    saveBtn.title = "Salvar novo link WAN";
    saveBtn.onclick = function (e) {
      e.stopPropagation();
      var payload = wanForm.collect();
      if (!payload) return;

      var url = "/vgr/api/unidades/" + encodeURIComponent(uni) + "/links";
      saveBtn.disabled = true;
      V.jsonFetch(url, { method: "POST", body: JSON.stringify(payload) })
        .then(function (res) {
          if (res.status >= 400 || !res.d.success) {
            V.toast((res.d && res.d.message) || "Falha ao salvar link.", false);
            return;
          }
          V.toast(res.d.message || "Link WAN criado.", true);
          if (R) R.toastAvisos(res.d.avisos);
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

  } else {
    /* ===== NOVA CONECTIVIDADE ===== */
    var tipoConnSel = document.createElement("select");
    tipoConnSel.className = "form-select form-select-sm";
    V.fillTipoLinkSelect(tipoConnSel, "unidade", "LAN");

    var ipConnInp = document.createElement("input");
    ipConnInp.className = "form-control form-control-sm";

    var maskConnInp = document.createElement("input");
    maskConnInp.className = "form-control form-control-sm";

    var vlanConnInp = document.createElement("input");
    vlanConnInp.className = "form-control form-control-sm";

    var connExtra = vgrBuildConnExtraInputs(null);
    var connCols = {
      ip: vgrCreateIncidentFieldCol("IP", ipConnInp, "col-md-6"),
      mascara: vgrCreateIncidentFieldCol("Máscara", maskConnInp, "col-md-6"),
      subrede: vgrCreateIncidentFieldCol("Subrede", connExtra.subrede, "col-md-6"),
      rangeStart: vgrCreateIncidentFieldCol("Início do range", connExtra.rangeStart, "col-md-6"),
      rangeEnd: vgrCreateIncidentFieldCol("Fim do range", connExtra.rangeEnd, "col-md-6"),
      vlan: vgrCreateIncidentFieldCol("VLAN", vlanConnInp, "col-md-6")
    };
    grid.append(
      vgrCreateIncidentFieldCol("Tipo", tipoConnSel, "col-md-6"),
      connCols.ip,
      connCols.mascara,
      connCols.subrede,
      connCols.rangeStart,
      connCols.rangeEnd,
      connCols.vlan
    );
    vgrBindConnVisibility(tipoConnSel, connCols);
    /* Calculadora IP/máscara/subrede/range ao vivo (mesma regra do modal da unidade) */
    var liveConn = R
      ? R.bindLinkLive({
          tipo: tipoConnSel,
          ip: ipConnInp,
          mascara: maskConnInp,
          subrede: connExtra.subrede,
          rangeStart: connExtra.rangeStart,
          rangeEnd: connExtra.rangeEnd,
          vlan: vlanConnInp
        })
      : null;
    if (liveConn) liveConn.refresh();

    var saveConnBtn = document.createElement("button");
    saveConnBtn.type = "button";
    saveConnBtn.innerHTML = '<i class="fas fa-check me-1"></i>Salvar';
    saveConnBtn.className = "btn btn-sm btn-success";
    saveConnBtn.title = "Salvar nova conectividade";
    saveConnBtn.onclick = function (e) {
      e.stopPropagation();
      var payload = {
        tipo_link: tipoConnSel.value,
        modo_conexao: null,
        operadora: "",
        id_vgr_link: "",
        identificador: "",
        designador: "",
        ip_address: (ipConnInp.value || "").trim(),
        mascara: (maskConnInp.value || "").trim(),
        gateway: "",
        subrede: (connExtra.subrede.value || "").trim(),
        range_start: (connExtra.rangeStart.value || "").trim(),
        range_end: (connExtra.rangeEnd.value || "").trim(),
        vlan: (vlanConnInp.value || "").trim(),
        velocidade: "",
        id_equipamento: null
      };
      payload = vgrPrepareLinkPayload(payload, liveConn);
      if (!payload) return;
      var url = "/vgr/api/unidades/" + encodeURIComponent(uni) + "/links";
      saveConnBtn.disabled = true;
      V.jsonFetch(url, { method: "POST", body: JSON.stringify(payload) })
        .then(function (res) {
          if (res.status >= 400 || !res.d.success) {
            V.toast((res.d && res.d.message) || "Falha ao salvar conectividade.", false);
            return;
          }
          V.toast(res.d.message || "Conectividade criada.", true);
          loadUnidadeDetalhe(uni);
        })
        .finally(function () {
          saveConnBtn.disabled = false;
        });
    };

    var cancelConnBtn = document.createElement("button");
    cancelConnBtn.type = "button";
    cancelConnBtn.innerHTML = '<i class="fas fa-times me-1"></i>Cancelar';
    cancelConnBtn.className = "btn btn-sm btn-secondary";
    cancelConnBtn.title = "Cancelar criação";
    cancelConnBtn.onclick = function (e) {
      e.stopPropagation();
      item.remove();
    };

    actionsSlot.innerHTML = "";
    actionsSlot.appendChild(vgrCreateIncidentActionsGroup([saveConnBtn, cancelConnBtn]));
  }

  accordion.appendChild(item);
  item.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
})();
