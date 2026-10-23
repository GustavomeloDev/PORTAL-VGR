/**
 * PRODESP — fluxos de substatus com observação obrigatória (retorno, Aguarda Gestão, Com Suporte).
 * Carregar antes de script_atendimentos_prodesp.js.
 */
(function (global) {
  const SUBSTATUS_LEGACY_TRIAGEM = "Triagem";
  const SUBSTATUS_AGUARDA_GESTAO = "Aguarda Gestão";
  const SUBSTATUS_COM_SUPORTE = "Com Suporte";
  const SUBSTATUS_INICIAL_FILA = "Aguardando Config. Remota";
  const SUBSTATUS_AGUARDA_EXTERNO = new Set([
    "Aguardando Cliente",
    "Aguarda Contratada",
    "Aguarda Licença",
  ]);

  const RETORNO_SUBSTATUS_MIN_CHARS = 10;
  const AGUARDA_GESTAO_MIN_CHARS = 30;
  const COM_SUPORTE_MIN_CHARS = 10;

  const PRODESP_FLUXO_SUBSTATUS_ORDEM = [
    SUBSTATUS_AGUARDA_GESTAO,
    SUBSTATUS_INICIAL_FILA,
    "Em Configuração Remota",
    "Aguardando Config. MPLS",
    "Em Configuração do MPLS",
    "Aguardando Caderno de Teste",
    "Em Caderno de Teste",
  ];

  let suppressObsSubstatusChange = false;
  let prodespLastTransicaoObservacoes = null;

  function prodespNormalizarSubstatusFluxo(sub) {
    const s = (sub || "").trim();
    if (s === SUBSTATUS_LEGACY_TRIAGEM) return SUBSTATUS_AGUARDA_GESTAO;
    if (s === "Aguarda Fornecedor") return "Aguarda Contratada";
    return s;
  }

  function prodespIsSubstatusGestao(sub) {
    const s = (sub || "").trim();
    return s === SUBSTATUS_LEGACY_TRIAGEM || s === SUBSTATUS_AGUARDA_GESTAO;
  }

  function prodespIndiceFluxoSubstatusNovo(sub) {
    return PRODESP_FLUXO_SUBSTATUS_ORDEM.indexOf(prodespNormalizarSubstatusFluxo(sub));
  }

  function prodespIsRetornoDeFila(oldSub, newSub) {
    const io = prodespIndiceFluxoSubstatusNovo(oldSub);
    const in_ = prodespIndiceFluxoSubstatusNovo(newSub);
    return io >= 0 && in_ >= 0 && in_ < io;
  }

  function prodespIsEntradaAguardaGestao(oldSub, newSub) {
    const o = (oldSub || "").trim();
    const n = (newSub || "").trim();
    return prodespIsSubstatusGestao(n) && !prodespIsSubstatusGestao(o);
  }

  function prodespIsSaidaAguardaGestao(oldSub, newSub) {
    const o = (oldSub || "").trim();
    const n = (newSub || "").trim();
    return prodespIsSubstatusGestao(o) && !prodespIsSubstatusGestao(n);
  }

  function prodespIsEntradaComSuporte(oldSub, newSub) {
    const o = (oldSub || "").trim();
    const n = (newSub || "").trim();
    return n === SUBSTATUS_COM_SUPORTE && o !== SUBSTATUS_COM_SUPORTE;
  }

  function prodespIsSaidaComSuporte(oldSub, newSub) {
    const o = (oldSub || "").trim();
    const n = (newSub || "").trim();
    return o === SUBSTATUS_COM_SUPORTE && n !== SUBSTATUS_COM_SUPORTE;
  }

  function prodespIsEntradaAguardaExterno(oldSub, newSub) {
    const o = (oldSub || "").trim();
    const n = (newSub || "").trim();
    return SUBSTATUS_AGUARDA_EXTERNO.has(n) && n !== o;
  }

  function prodespIsGestaoParaFilaAguardando(oldSub, newSub) {
    const filas = [
      "Aguardando Config. Remota",
      "Aguardando Config. MPLS",
      "Aguardando Caderno de Teste",
    ];
    return prodespIsSubstatusGestao(oldSub) && filas.includes((newSub || "").trim());
  }

  function prodespContagemKpiAguardaGestao(counts) {
    if (!counts) return 0;
    return (counts[SUBSTATUS_AGUARDA_GESTAO] || 0) + (counts[SUBSTATUS_LEGACY_TRIAGEM] || 0);
  }

  /** Aguarda Gestão/Triagem ou Com Suporte exigem contexto de saída ao mudar de substatus. */
  function prodespSubstatusExigeObsSaida(oldSub) {
    const s = prodespNormalizarSubstatusFluxo((oldSub || "").trim());
    return prodespIsSubstatusGestao(s) || s === SUBSTATUS_COM_SUPORTE;
  }

  /**
   * Opção 1: uma observação cobre saída do substatus paralelo + motivo da entrada.
   * Backend valida só o prefixo da entrada; o texto orienta o analista.
   */
  function prodespEnriquecerModalObsTransicaoEntrada(subWas, base) {
    const entradaLabel = (base.entradaLabel || base.titleText || "").trim();
    const bodyEntrada =
      (base.bodyText || "").trim() ||
      `Informe o contexto para «${entradaLabel}». O texto será salvo em Observações.`;
    if (!prodespSubstatusExigeObsSaida(subWas)) {
      return {
        titleText: base.titleText || entradaLabel,
        bodyText: bodyEntrada,
      };
    }
    const s = prodespNormalizarSubstatusFluxo((subWas || "").trim());
    const saidaLabel = s === SUBSTATUS_COM_SUPORTE ? SUBSTATUS_COM_SUPORTE : SUBSTATUS_AGUARDA_GESTAO;
    const saidaHint =
      s === SUBSTATUS_COM_SUPORTE
        ? "como o caso foi tratado ou encaminhado no Com Suporte"
        : "a devolutiva do time de Aguarda Gestão";
    return {
      titleText: `${entradaLabel} (saída de ${saidaLabel})`,
      bodyText:
        `Em um único texto, informe: (1) ${saidaHint}; (2) o motivo para «${entradaLabel}». ` +
        "Será salvo em Observações com o prefixo da entrada.",
    };
  }

  function prodespConsumeTransicaoObservacoes() {
    const v = prodespLastTransicaoObservacoes;
    prodespLastTransicaoObservacoes = null;
    return v;
  }

  /** Disponibiliza observação de transição para o POST /atendimentos/update (validação server-side). */
  function prodespStageTransicaoObservacoes(obsArr) {
    prodespLastTransicaoObservacoes = obsArr;
  }

  let prodespLastObservacaoQuebraEncerramento = null;

  function prodespStageObservacaoQuebraEncerramento(obsObj) {
    prodespLastObservacaoQuebraEncerramento = obsObj;
  }

  function prodespConsumeObservacaoQuebraEncerramento() {
    const v = prodespLastObservacaoQuebraEncerramento;
    prodespLastObservacaoQuebraEncerramento = null;
    return v;
  }

  /** Payload de observações gravadas atomicamente no POST /atendimentos/update. */
  function prodespPayloadObservacoesAtomicasUpdate() {
    return {
      transicao_observacoes:
        typeof prodespConsumeTransicaoObservacoes === "function"
          ? prodespConsumeTransicaoObservacoes()
          : null,
      observacao_quebra_encerramento:
        typeof prodespConsumeObservacaoQuebraEncerramento === "function"
          ? prodespConsumeObservacaoQuebraEncerramento()
          : null,
    };
  }

  /**
   * Registra observação de transição de substatus apenas em memória/UI.
   * Persiste no banco na mesma transação do POST /atendimentos/update (após todas as validações).
   */
  function prodespRegistrarObservacaoTransicaoStaging(mode, prefix, texto) {
    const obsObj = {
      data_observacao:
        typeof formatObservacaoDataHoraProdesp === "function"
          ? formatObservacaoDataHoraProdesp()
          : new Date().toISOString(),
      observacao_prodesp: prodespMontarTextoObservacaoTransicao(prefix, texto),
      _transicaoStaging: true,
    };

    if (mode === "edit") {
      if (typeof newObservacao !== "undefined") newObservacao.push(obsObj);
    } else if (typeof newObservacaoCreate !== "undefined") {
      newObservacaoCreate.push(obsObj);
    }
    if (typeof appendObservacaoToUI === "function") appendObservacaoToUI(mode, obsObj);
    prodespStageTransicaoObservacoes([obsObj]);
    return obsObj;
  }

  /** Evita prefixo duplicado quando o analista cola texto que já inclui o rótulo da transição. */
  function prodespMontarTextoObservacaoTransicao(prefix, texto) {
    const p = (prefix || "").trim();
    let body = (texto || "").trim();
    if (p && body.startsWith(p)) {
      body = body.slice(p.length).trim().replace(/^[:\-\s]+/, "");
    }
    return body ? `${p} ${body}`.trim() : p;
  }

  /** Remove observação de transição que ficou só na UI/array local (substatus não concluiu). */
  function prodespDescartarObservacaoTransicaoStaging(mode, obsObj) {
    const arr =
      mode === "edit"
        ? typeof newObservacao !== "undefined"
          ? newObservacao
          : null
        : typeof newObservacaoCreate !== "undefined"
          ? newObservacaoCreate
          : null;
    if (arr && obsObj) {
      const idx = arr.indexOf(obsObj);
      if (idx >= 0) {
        arr.splice(idx, 1);
      } else {
        const i = arr.findIndex(
          (o) =>
            o._transicaoStaging &&
            o.observacao_prodesp === obsObj.observacao_prodesp
        );
        if (i >= 0) arr.splice(i, 1);
      }
    }
    prodespLastTransicaoObservacoes = null;

    if (mode === "edit" && typeof reloadObservacoes === "function") {
      reloadObservacoes(
        typeof originalData !== "undefined" ? originalData.observacoes || [] : [],
        "edit"
      );
      return;
    }
    if (mode === "create" && typeof prodespReloadObservacoesFromAtendimento === "function") {
      const idAtend =
        typeof currentCreateModalAtendimentoId !== "undefined"
          ? currentCreateModalAtendimentoId
          : null;
      if (idAtend) {
        void prodespReloadObservacoesFromAtendimento(idAtend, "create");
      }
    }
  }

  async function prodespOpenObsTextModal(config) {
    const modalEl = document.getElementById(config.modalId);
    const inputEl = document.getElementById(config.inputId);
    const counterEl = document.getElementById(config.counterId);
    const btnSave = document.getElementById(config.saveId);
    const btnCancel = document.getElementById(config.cancelId);
    const helpEl = document.getElementById(config.helpId);
    const titleEl = config.titleId ? document.getElementById(config.titleId) : null;

    if (!modalEl || !inputEl || !btnSave || !btnCancel) {
      if (typeof showToast === "function") {
        showToast(`Modal ${config.modalId} não encontrado no HTML.`, "danger");
      }
      return { action: "cancel" };
    }

    if (titleEl && config.titleText) titleEl.textContent = config.titleText;
    const bodyEl = config.bodyId ? document.getElementById(config.bodyId) : null;
    if (bodyEl && config.bodyText) bodyEl.textContent = config.bodyText;
    inputEl.value = "";
    const minChars = config.minChars || 10;

    const updateCounter = () => {
      const n = (inputEl.value || "").trim().length;
      if (counterEl) counterEl.textContent = `${n}/${minChars}`;
      const ok = n >= minChars;
      btnSave.disabled = !ok;
      if (helpEl) {
        helpEl.classList.toggle("text-danger", !ok);
        helpEl.classList.toggle("text-muted", ok);
      }
    };
    inputEl.oninput = updateCounter;
    updateCounter();

    const bsModal =
      typeof prodespShowStackedModal === "function"
        ? prodespShowStackedModal(modalEl)
        : bootstrap.Modal.getOrCreateInstance(modalEl, { backdrop: "static", keyboard: false });
    if (typeof prodespShowStackedModal !== "function") bsModal.show();

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
      const onCancel = () => bsModal.hide();
      const onSave = () => {
        const texto = (inputEl.value || "").trim();
        if (texto.length < minChars) return;
        finish({ action: "save", texto });
        bsModal.hide();
      };
      btnSave.addEventListener("click", onSave);
      btnCancel.addEventListener("click", onCancel);
      modalEl.addEventListener("hidden.bs.modal", onHidden);
      setTimeout(() => inputEl.focus(), 50);
    });
  }

  async function prodespRunObservacaoSubstatusFlows(mode, subEl, statusEl) {
    if (suppressObsSubstatusChange) return false;
    if (!subEl || !statusEl) return false;
    const statusNow = (statusEl.value || "").trim();
    if (statusNow === "Quebra" || statusNow === "Quebra TBRA") return false;

    const subNow = (subEl.value || "").trim();
    const subWas = (
      typeof getPersistedSubstatus === "function" ? getPersistedSubstatus(mode) : ""
    ).trim();
    if (!subNow || subNow === subWas) return false;

    const isFinalStatusNow =
      statusNow === "Concluído" || statusNow === "Concluído Parcial";
    if (statusNow !== "Em Atendimento" && !isFinalStatusNow) return false;

    if (prodespIsEntradaAguardaExterno(subWas, subNow) && !isFinalStatusNow) return false;

    let prefix = "";
    let minChars = 10;
    let modalCfg = null;
    let targetSub = subNow;

    if (isFinalStatusNow) {
      if (prodespIsSaidaComSuporte(subWas, subNow)) {
        prefix = "[Com Suporte - saída]";
        minChars = COM_SUPORTE_MIN_CHARS;
        modalCfg = {
          modalId: "comSuporteModal",
          inputId: "comSuporteTexto",
          counterId: "comSuporteCounter",
          saveId: "comSuporteSalvar",
          cancelId: "comSuporteCancelar",
          helpId: "comSuporteHelp",
          titleId: "comSuporteTitulo",
          titleText: "Saída de Com Suporte",
          bodyId: "comSuporteDescricao",
          bodyText:
            "Descreva a solução do problema antes de concluir. Este texto será salvo em Observações.",
        };
      } else if (prodespIsSaidaAguardaGestao(subWas, subNow)) {
        prefix = `[${SUBSTATUS_AGUARDA_GESTAO} - saída]`;
        minChars = AGUARDA_GESTAO_MIN_CHARS;
        modalCfg = {
          modalId: "aguardaGestaoModal",
          inputId: "aguardaGestaoTexto",
          counterId: "aguardaGestaoCounter",
          saveId: "aguardaGestaoSalvar",
          cancelId: "aguardaGestaoCancelar",
          helpId: "aguardaGestaoHelp",
          titleId: "aguardaGestaoModalLabel",
          titleText: "Saída de Aguarda Gestão",
          bodyId: "aguardaGestaoDescricao",
          bodyText:
            "Informe a devolutiva antes de concluir. O texto será salvo em Observações.",
        };
      } else {
        return false;
      }
    } else if (prodespIsEntradaAguardaGestao(subWas, subNow)) {
      targetSub = SUBSTATUS_AGUARDA_GESTAO;
      prefix = `[${SUBSTATUS_AGUARDA_GESTAO}]`;
      minChars = AGUARDA_GESTAO_MIN_CHARS;
      modalCfg = {
        modalId: "aguardaGestaoModal",
        inputId: "aguardaGestaoTexto",
        counterId: "aguardaGestaoCounter",
        saveId: "aguardaGestaoSalvar",
        cancelId: "aguardaGestaoCancelar",
        helpId: "aguardaGestaoHelp",
        titleId: "aguardaGestaoModalLabel",
        titleText: "Aguarda Gestão",
        bodyId: "aguardaGestaoDescricao",
        bodyText:
          "Informe o contexto para o time Gestão. O texto será salvo em Observações.",
      };
    } else if (prodespIsRetornoDeFila(subWas, subNow)) {
      prefix = `[Retorno] ${subWas} → ${subNow}:`;
      minChars = RETORNO_SUBSTATUS_MIN_CHARS;
      modalCfg = {
        modalId: "retornoSubstatusModal",
        inputId: "retornoSubstatusTexto",
        counterId: "retornoSubstatusCounter",
        saveId: "retornoSubstatusSalvar",
        cancelId: "retornoSubstatusCancelar",
        helpId: "retornoSubstatusHelp",
        titleId: "retornoSubstatusTitulo",
        titleText: `Retorno: ${subWas} → ${subNow}`,
      };
    } else if (prodespIsEntradaComSuporte(subWas, subNow)) {
      prefix = "[Com Suporte - entrada]";
      minChars = COM_SUPORTE_MIN_CHARS;
      modalCfg = {
        modalId: "comSuporteModal",
        inputId: "comSuporteTexto",
        counterId: "comSuporteCounter",
        saveId: "comSuporteSalvar",
        cancelId: "comSuporteCancelar",
        helpId: "comSuporteHelp",
        titleId: "comSuporteTitulo",
        titleText: "Entrada em Com Suporte",
        bodyId: "comSuporteDescricao",
        bodyText:
          "Descreva o problema que está ocorrendo. Este texto será salvo em Observações.",
      };
    } else if (prodespIsSaidaComSuporte(subWas, subNow)) {
      prefix = "[Com Suporte - saída]";
      minChars = COM_SUPORTE_MIN_CHARS;
      modalCfg = {
        modalId: "comSuporteModal",
        inputId: "comSuporteTexto",
        counterId: "comSuporteCounter",
        saveId: "comSuporteSalvar",
        cancelId: "comSuporteCancelar",
        helpId: "comSuporteHelp",
        titleId: "comSuporteTitulo",
        titleText: "Saída de Com Suporte",
        bodyId: "comSuporteDescricao",
        bodyText:
          "Descreva a solução do problema. Este texto será salvo em Observações.",
      };
    } else if (prodespIsSaidaAguardaGestao(subWas, subNow)) {
      prefix = `[${SUBSTATUS_AGUARDA_GESTAO} - saída]`;
      minChars = AGUARDA_GESTAO_MIN_CHARS;
      modalCfg = {
        modalId: "aguardaGestaoModal",
        inputId: "aguardaGestaoTexto",
        counterId: "aguardaGestaoCounter",
        saveId: "aguardaGestaoSalvar",
        cancelId: "aguardaGestaoCancelar",
        helpId: "aguardaGestaoHelp",
        titleId: "aguardaGestaoModalLabel",
        titleText: "Saída de Aguarda Gestão",
        bodyId: "aguardaGestaoDescricao",
        bodyText:
          "Informe o contexto da devolutiva ao fluxo operacional. O texto será salvo em Observações.",
      };
    } else {
      return false;
    }

    const isEntradaComObs =
      !isFinalStatusNow &&
      (prodespIsEntradaAguardaGestao(subWas, subNow) ||
        prodespIsEntradaComSuporte(subWas, subNow));
    if (isEntradaComObs && modalCfg) {
      const enriched = prodespEnriquecerModalObsTransicaoEntrada(subWas, {
        titleText: modalCfg.titleText,
        bodyText: modalCfg.bodyText,
        entradaLabel: targetSub,
      });
      modalCfg = {
        ...modalCfg,
        titleText: enriched.titleText,
        bodyText: enriched.bodyText,
      };
    }

    const prevStatus = (
      typeof prodespGetPersistedStatus === "function" ? prodespGetPersistedStatus(mode) : "Em Atendimento"
    ).trim();
    const prevSub = subWas || SUBSTATUS_INICIAL_FILA;

    suppressObsSubstatusChange = true;
    if (typeof suppressAguardandoClienteChange !== "undefined") suppressAguardandoClienteChange = true;
    if (typeof setSubstatusWithFlow === "function") {
      setSubstatusWithFlow(subEl, statusEl, prevSub, mode, mode);
    } else {
      subEl.value = prevSub;
    }
    suppressObsSubstatusChange = false;
    if (typeof suppressAguardandoClienteChange !== "undefined") suppressAguardandoClienteChange = false;

    if (mode === "edit" && typeof autoSaveEditTimeout !== "undefined" && autoSaveEditTimeout) {
      clearTimeout(autoSaveEditTimeout);
    }
    if (mode === "create" && typeof autoSaveTimeout !== "undefined" && autoSaveTimeout) {
      clearTimeout(autoSaveTimeout);
    }

    const res = await prodespOpenObsTextModal({ ...modalCfg, minChars });
    if (res.action !== "save") return false;

    suppressObsSubstatusChange = true;
    if (typeof suppressAguardandoClienteChange !== "undefined") suppressAguardandoClienteChange = true;
    if (typeof setSubstatusWithFlow === "function") {
      setSubstatusWithFlow(subEl, statusEl, targetSub, mode, mode);
    } else {
      subEl.value = targetSub;
    }
    suppressObsSubstatusChange = false;
    if (typeof suppressAguardandoClienteChange !== "undefined") suppressAguardandoClienteChange = false;

    const obsObj = prodespRegistrarObservacaoTransicaoStaging(mode, prefix, res.texto);

    const saveOk =
      mode === "edit" && typeof autoSaveEditModalData === "function"
        ? await autoSaveEditModalData({ showSuccessToast: true, notifyFailure: true })
        : mode === "create" && typeof autoSaveCreateModalData === "function"
          ? await autoSaveCreateModalData({ showSuccessToast: true, notifyFailure: true })
          : true;

    if (!saveOk) {
      prodespDescartarObservacaoTransicaoStaging(mode, obsObj);
      if (typeof showToast === "function") {
        showToast(
          "Alteração de substatus não concluída. A observação de transição não foi salva e o substatus anterior foi restaurado.",
          "warning"
        );
      }
      if (typeof prodespRevertStatusSubstatusParaValor === "function") {
        prodespRevertStatusSubstatusParaValor(mode, prevStatus, prevSub);
      }
      return true;
    }

    delete obsObj._transicaoStaging;

    if (
      mode === "edit" &&
      typeof autoSaveEditTimeout !== "undefined" &&
      autoSaveEditTimeout
    ) {
      clearTimeout(autoSaveEditTimeout);
    }
    if (
      mode === "create" &&
      typeof autoSaveTimeout !== "undefined" &&
      autoSaveTimeout
    ) {
      clearTimeout(autoSaveTimeout);
    }

    if (
      mode === "edit" &&
      targetSub === SUBSTATUS_AGUARDA_GESTAO &&
      typeof prodespApplyAnalistaImplantacaoAdminUi === "function" &&
      !prodespIsAgendamentoOuGp?.()
    ) {
      prodespApplyAnalistaImplantacaoAdminUi("edit", true);
    }

    if (mode === "edit") {
      if (typeof editPersistedSubstatus !== "undefined") {
        editPersistedSubstatus = (document.getElementById("editSubstatus")?.value || "").trim();
      }
      if (typeof editPersistedStatus !== "undefined") {
        editPersistedStatus = (document.getElementById("editStatus")?.value || "").trim();
      }
      if (
        typeof editFlowBaselineSubstatus !== "undefined" &&
        editPersistedSubstatus &&
        editPersistedSubstatus !== "Aguardando Cliente" &&
        editPersistedSubstatus !== SUBSTATUS_COM_SUPORTE
      ) {
        editFlowBaselineSubstatus = editPersistedSubstatus;
      }
    } else {
      if (typeof createPersistedSubstatus !== "undefined") {
        createPersistedSubstatus = (document.getElementById("createSubstatus")?.value || "").trim();
      }
      if (typeof createPersistedStatus !== "undefined") {
        createPersistedStatus = (document.getElementById("createStatus")?.value || "").trim();
      }
      if (
        typeof createFlowBaselineSubstatus !== "undefined" &&
        createPersistedSubstatus &&
        createPersistedSubstatus !== "Aguardando Cliente" &&
        createPersistedSubstatus !== SUBSTATUS_COM_SUPORTE
      ) {
        createFlowBaselineSubstatus = createPersistedSubstatus;
      }
    }

    return true;
  }

  /**
   * Antes do encerramento com Quebra: exige observação de saída de Aguarda Gestão ou Com Suporte.
   * Retorna false se o usuário cancelar ou a observação não for gravada.
   */
  async function prodespRunObservacaoSaidaPreQuebra(mode, prevSub) {
    const prev = (prevSub || "").trim();
    if (!prev) return true;

    let prefix = "";
    let minChars = COM_SUPORTE_MIN_CHARS;
    let modalCfg = null;

    if (prodespIsSubstatusGestao(prev)) {
      prefix = `[${SUBSTATUS_AGUARDA_GESTAO} - saída]`;
      minChars = AGUARDA_GESTAO_MIN_CHARS;
      modalCfg = {
        modalId: "aguardaGestaoModal",
        inputId: "aguardaGestaoTexto",
        counterId: "aguardaGestaoCounter",
        saveId: "aguardaGestaoSalvar",
        cancelId: "aguardaGestaoCancelar",
        helpId: "aguardaGestaoHelp",
        titleId: "aguardaGestaoModalLabel",
        titleText: "Saída de Aguarda Gestão",
        bodyId: "aguardaGestaoDescricao",
        bodyText:
          "Informe o contexto da devolutiva antes de encerrar com Quebra. O texto será salvo em Observações.",
      };
    } else if (prev === SUBSTATUS_COM_SUPORTE) {
      prefix = "[Com Suporte - saída]";
      minChars = COM_SUPORTE_MIN_CHARS;
      modalCfg = {
        modalId: "comSuporteModal",
        inputId: "comSuporteTexto",
        counterId: "comSuporteCounter",
        saveId: "comSuporteSalvar",
        cancelId: "comSuporteCancelar",
        helpId: "comSuporteHelp",
        titleId: "comSuporteTitulo",
        titleText: "Saída de Com Suporte",
        bodyId: "comSuporteDescricao",
        bodyText:
          "Descreva a solução do problema antes de encerrar com Quebra. Este texto será salvo em Observações.",
      };
    } else {
      return true;
    }

    const res = await prodespOpenObsTextModal({ ...modalCfg, minChars });
    if (res.action !== "save") return false;

    const obsObj = prodespRegistrarObservacaoTransicaoStaging(mode, prefix, res.texto);
    return true;
  }

  function prodespLabelMarcoAtividade(marco) {
    const s = (marco || "").trim();
    if (s === SUBSTATUS_LEGACY_TRIAGEM) return SUBSTATUS_AGUARDA_GESTAO;
    return s || "—";
  }

  global.SUBSTATUS_LEGACY_TRIAGEM = SUBSTATUS_LEGACY_TRIAGEM;
  global.SUBSTATUS_AGUARDA_GESTAO = SUBSTATUS_AGUARDA_GESTAO;
  global.SUBSTATUS_COM_SUPORTE = SUBSTATUS_COM_SUPORTE;
  global.SUBSTATUS_INICIAL_FILA = SUBSTATUS_INICIAL_FILA;
  global.PRODESP_FLUXO_SUBSTATUS_ORDEM = PRODESP_FLUXO_SUBSTATUS_ORDEM;
  global.prodespNormalizarSubstatusFluxo = prodespNormalizarSubstatusFluxo;
  global.prodespLabelMarcoAtividade = prodespLabelMarcoAtividade;
  global.prodespIsSubstatusGestao = prodespIsSubstatusGestao;
  global.prodespIsEntradaAguardaGestao = prodespIsEntradaAguardaGestao;
  global.prodespIsSaidaAguardaGestao = prodespIsSaidaAguardaGestao;
  global.prodespIsEntradaAguardaExterno = prodespIsEntradaAguardaExterno;
  global.prodespIsRetornoDeFila = prodespIsRetornoDeFila;
  global.prodespRunObservacaoSaidaPreQuebra = prodespRunObservacaoSaidaPreQuebra;
  global.prodespIsGestaoParaFilaAguardando = prodespIsGestaoParaFilaAguardando;
  global.prodespContagemKpiAguardaGestao = prodespContagemKpiAguardaGestao;
  global.prodespRunObservacaoSubstatusFlows = prodespRunObservacaoSubstatusFlows;
  /** Remove do array local observações de transição já gravadas atomicamente no update. */
  function prodespAplicarObservacoesTransicaoPersistidasNoUpdate(mode, resultMain) {
    if (!resultMain || !resultMain.observacoes_transicao_persistidas) return;
    const arr =
      mode === "edit"
        ? typeof newObservacao !== "undefined"
          ? newObservacao
          : null
        : typeof newObservacaoCreate !== "undefined"
          ? newObservacaoCreate
          : null;
    if (arr) {
      for (let i = arr.length - 1; i >= 0; i--) {
        if (arr[i]._transicaoStaging) arr.splice(i, 1);
      }
    }
    if (Array.isArray(resultMain.observacoes) && typeof reloadObservacoes === "function") {
      if (mode === "edit" && typeof originalData !== "undefined") {
        originalData.observacoes = resultMain.observacoes;
      }
      reloadObservacoes(resultMain.observacoes, mode);
    }
  }

  global.prodespAplicarObservacoesTransicaoPersistidasNoUpdate =
    prodespAplicarObservacoesTransicaoPersistidasNoUpdate;
  global.prodespConsumeTransicaoObservacoes = prodespConsumeTransicaoObservacoes;
  global.prodespStageObservacaoQuebraEncerramento = prodespStageObservacaoQuebraEncerramento;
  global.prodespConsumeObservacaoQuebraEncerramento = prodespConsumeObservacaoQuebraEncerramento;
  global.prodespPayloadObservacoesAtomicasUpdate = prodespPayloadObservacoesAtomicasUpdate;
  global.prodespStageTransicaoObservacoes = prodespStageTransicaoObservacoes;
  global.prodespRegistrarObservacaoTransicaoStaging = prodespRegistrarObservacaoTransicaoStaging;
  global.prodespDescartarObservacaoTransicaoStaging = prodespDescartarObservacaoTransicaoStaging;
  global.prodespMontarTextoObservacaoTransicao = prodespMontarTextoObservacaoTransicao;
  global.prodespSubstatusExigeObsSaida = prodespSubstatusExigeObsSaida;
  global.prodespEnriquecerModalObsTransicaoEntrada = prodespEnriquecerModalObsTransicaoEntrada;
})(typeof window !== "undefined" ? window : globalThis);
