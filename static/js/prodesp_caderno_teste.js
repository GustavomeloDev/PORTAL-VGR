/**
 * Caderno de Teste PRODESP — coleta SSH e geração .xlsm
 */
(function () {
  "use strict";

  const SUBSTATUS_CADERNO = "Em Caderno de Teste";
  const STATUS_PENDENTE = "⚠️Pendente";
  const STATUS_CONCLUIDO = "✔️ Concluido";
  let esaqBase64 = "";
  let esaqErroBblBase64 = "";
  let esaqSpeedtestBase64 = "";
  let activeEsaqPasteAreaId = "prodespCadernoEsaqPaste";
  let coletandoEmAndamento = false;
  let gerandoEmAndamento = false;

  const TOOLBAR_PREFIXES = ["edit", "view", "create", "details"];
  let activeToolbarPrefix = "edit";

  function isAdmin() {
    if (Number(window.PRODESP_ADMIN_USER || 0) === 1) return true;
    if (typeof LOGGED_IN_USER_ADMIN !== "undefined" && Number(LOGGED_IN_USER_ADMIN || 0) === 1) {
      return true;
    }
    return false;
  }

  function getAtendimentoIdForPrefix(prefix) {
    if (!prefix) return "";
    if (prefix === "create") {
      return window.currentCreateModalAtendimentoId
        ? String(window.currentCreateModalAtendimentoId)
        : "";
    }
    const el = document.getElementById(prefix + "AtendimentoId");
    return el && el.value ? String(el.value).trim() : "";
  }

  function prefixFromButton(btn) {
    return (
      btn &&
      btn.closest &&
      btn.closest("[data-prodesp-caderno-prefix]") &&
      btn.closest("[data-prodesp-caderno-prefix]").dataset.prodespCadernoPrefix
    ) || "edit";
  }

  function getAtendimentoId() {
    const fromModal = document.getElementById("prodespCadernoAtendimentoId");
    if (fromModal && fromModal.value) return fromModal.value;
    const active = getAtendimentoIdForPrefix(activeToolbarPrefix);
    if (active) return active;
    const edit = document.getElementById("editAtendimentoId");
    return edit && edit.value ? edit.value : "";
  }

  function substatusForPrefix(prefix, editSubstatusOpt) {
    if (prefix === "edit" && editSubstatusOpt != null) {
      return String(editSubstatusOpt).trim();
    }
    const el = document.getElementById(prefix + "Substatus");
    return (el && el.value ? el.value : "").trim();
  }

  function podeMostrarToolbar(substatus) {
    if (isAdmin()) return true;
    return (substatus || "").trim() === SUBSTATUS_CADERNO;
  }

  function limparToolbarStatusPrefix(prefix) {
    const box = document.getElementById(prefix + "CadernoToolbarStatus");
    const result = document.getElementById(prefix + "CadernoToolbarResult");
    const toolbar = document.getElementById(prefix + "CadernoTesteToolbar");
    if (box) box.classList.add("d-none");
    if (result) {
      result.classList.add("d-none");
      result.textContent = "";
    }
    if (toolbar) toolbar.removeAttribute("aria-busy");
  }

  function atualizarToolbarCaderno(editSubstatusOpt) {
    TOOLBAR_PREFIXES.forEach(function (prefix) {
      const bar = document.getElementById(prefix + "CadernoTesteToolbar");
      if (!bar) return;
      const sub = substatusForPrefix(prefix, prefix === "edit" ? editSubstatusOpt : null);
      const show = podeMostrarToolbar(sub);
      bar.classList.toggle("d-none", !show);
      if (!show) limparToolbarStatusPrefix(prefix);
    });
  }

  function limparToolbarStatus() {
    limparToolbarStatusPrefix(activeToolbarPrefix);
  }

  function setToolbarLoading(loading, text) {
    const prefix = activeToolbarPrefix;
    const box = document.getElementById(prefix + "CadernoToolbarStatus");
    const txt = document.getElementById(prefix + "CadernoToolbarStatusText");
    const result = document.getElementById(prefix + "CadernoToolbarResult");
    const toolbar = document.getElementById(prefix + "CadernoTesteToolbar");
    if (result) result.classList.add("d-none");
    if (box && txt) {
      txt.textContent =
        text || "Coletando logs via SSH (jump → FGT). Normal: 1–3 min. Não clique novamente.";
      box.classList.toggle("d-none", !loading);
      const spin = box.querySelector(".prodesp-caderno-toolbar-spinner");
      if (spin) spin.classList.toggle("d-none", !loading);
    }
    if (toolbar) toolbar.setAttribute("aria-busy", loading ? "true" : "false");
  }

  function setToolbarResult(msg, kind) {
    const prefix = activeToolbarPrefix;
    const box = document.getElementById(prefix + "CadernoToolbarStatus");
    const result = document.getElementById(prefix + "CadernoToolbarResult");
    if (box) box.classList.add("d-none");
    if (!result) return;
    if (!msg) {
      result.classList.add("d-none");
      result.textContent = "";
      return;
    }
    result.className = "alert py-2 px-3 mt-2 mb-0 small alert-" + (kind || "info");
    result.textContent = msg;
    result.classList.remove("d-none");
  }

  const carimboTextoCache = new Map();

  function cacheCarimboTexto(atendimentoId, text, source) {
    const id = String(atendimentoId || "").trim();
    const value = String(text || "");
    if (!id || !value.trim()) return;
    carimboTextoCache.set(id, { text: value, source: source || "xlsm" });
  }

  function obterCarimboCache(atendimentoId) {
    return carimboTextoCache.get(String(atendimentoId || "").trim()) || null;
  }

  function notificarCarimboCopiado(origem) {
    const label =
      origem === "xlsm" || origem === "xlsx" || origem === "caderno gerado"
        ? "caderno gerado"
        : origem === "montado"
          ? "dados montados"
          : origem || "logs coletados";
    toast("Carimbo NOC copiado (" + label + ").", "success", "Carimbo NOC");
  }

  function clipboardCarimboConfiavel() {
    return !!(window.isSecureContext && navigator.clipboard && typeof navigator.clipboard.writeText === "function");
  }

  function labelOrigemCarimbo(source) {
    if (source === "xlsm" || source === "xlsx") return "caderno gerado";
    if (source === "montado") return "dados montados";
    return source || "logs coletados";
  }

  function nomeArquivoCarimboTxt(atendimentoId) {
    const id = String(atendimentoId || "").trim() || "atendimento";
    return "Carimbo_NOC_atendimento_" + id + ".txt";
  }

  function baixarCarimboTxt(text, atendimentoId) {
    const value = String(text || "");
    if (!value.trim()) {
      toast("Nenhum texto do Carimbo NOC para baixar.", "warning", "Carimbo NOC");
      return false;
    }
    const filename = nomeArquivoCarimboTxt(atendimentoId);
    try {
      const blob = new Blob([value], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.rel = "noopener";
      link.style.display = "none";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(function () {
        URL.revokeObjectURL(url);
      }, 1000);
      toast("Arquivo " + filename + " baixado.", "success", "Carimbo NOC");
      return true;
    } catch (e) {
      toast("Não foi possível baixar o arquivo. Use Ctrl+A e Ctrl+C no texto.", "danger", "Carimbo NOC");
      return false;
    }
  }

  function toast(msg, kind, titleOverride) {
    if (typeof window.showToast === "function") {
      window.showToast(msg, kind || "info", undefined, titleOverride);
    }
  }

  async function copiarTextoCarimbo(text) {
    const value = String(text || "");
    if (!value) {
      return false;
    }
    if (!clipboardCarimboConfiavel()) {
      return false;
    }
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch (e) {
      return false;
    }
  }

  function sincronizarBotoesModalCarimbo() {
    const btnCopiar = document.getElementById("btnProdespCarimboNocCopiaConfirmar");
    if (btnCopiar) {
      btnCopiar.classList.toggle("d-none", !clipboardCarimboConfiavel());
    }
  }

  function abrirModalCarimboNocCopia(text, origem, atendimentoId) {
    const modalEl = document.getElementById("prodespCarimboNocCopiaModal");
    const area = document.getElementById("prodespCarimboNocCopiaTexto");
    const hint = document.getElementById("prodespCarimboNocCopiaHint");
    if (!modalEl || !area || typeof bootstrap === "undefined") {
      return false;
    }
    const id = String(atendimentoId || "").trim();
    modalEl.dataset.prodespCarimboAtendimentoId = id;
    area.value = String(text || "");
    sincronizarBotoesModalCarimbo();
    if (hint) {
      const fonte = prodespEscapeHtml(origem || "logs");
      if (clipboardCarimboConfiavel()) {
        hint.innerHTML =
          "Fonte: <strong>" +
          fonte +
          "</strong>. Use <strong>Baixar Carimbo (.txt)</strong>, <strong>Copiar agora</strong> ou <kbd>Ctrl</kbd>+<kbd>A</kbd> e <kbd>Ctrl</kbd>+<kbd>C</kbd>.";
      } else {
        hint.innerHTML =
          "Fonte: <strong>" +
          fonte +
          "</strong>. Em HTTP o navegador bloqueia a área de transferência — use <strong>Baixar Carimbo (.txt)</strong> ou selecione todo o texto (<kbd>Ctrl</kbd>+<kbd>A</kbd>) e copie (<kbd>Ctrl</kbd>+<kbd>C</kbd>).";
      }
    }
    if (typeof window.prodespEnsureModalOnBody === "function") {
      window.prodespEnsureModalOnBody(modalEl);
    } else if (modalEl.parentElement !== document.body) {
      document.body.appendChild(modalEl);
    }
    const editAberto = document.getElementById("editModal")?.classList.contains("show");
    const viewAberto = document.getElementById("viewModal")?.classList.contains("show");
    const cadernoAberto = document.getElementById("prodespCadernoTesteModal")?.classList.contains("show");
    const empilhar = editAberto || viewAberto || cadernoAberto;
    if (empilhar && typeof window.prodespShowStackedModal === "function") {
      window.prodespShowStackedModal(modalEl, { backdrop: false, keyboard: true });
    } else if (typeof window.prodespOpenModal === "function") {
      window.prodespOpenModal(modalEl);
    } else {
      bootstrap.Modal.getOrCreateInstance(modalEl, { backdrop: true, keyboard: true }).show();
      if (window.ProdespModal && typeof window.ProdespModal.syncModalStack === "function") {
        window.ProdespModal.syncModalStack();
      }
    }
    modalEl.addEventListener(
      "shown.bs.modal",
      function onShown() {
        modalEl.removeEventListener("shown.bs.modal", onShown);
        if (window.ProdespModal && typeof window.ProdespModal.syncModalStack === "function") {
          window.ProdespModal.syncModalStack();
        }
        area.focus();
        area.select();
      },
      { once: true }
    );
    return true;
  }

  function prodespEscapeHtml(str) {
    if (typeof window.prodespEscapeHtml === "function") {
      return window.prodespEscapeHtml(str);
    }
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setButtonLoading(btn, loading, idleHtml, loadingHtml) {
    if (!btn) return;
    btn.disabled = !!loading;
    btn.setAttribute("aria-busy", loading ? "true" : "false");
    const label = btn.querySelector(".prodesp-caderno-btn-label");
    const spin = btn.querySelector(".prodesp-caderno-btn-spinner");
    if (label && spin) {
      label.classList.toggle("d-none", loading);
      spin.classList.toggle("d-none", !loading);
    } else if (loading && loadingHtml) {
      btn.dataset.prodespIdleHtml = btn.innerHTML;
      btn.innerHTML = loadingHtml;
    } else if (!loading && btn.dataset.prodespIdleHtml) {
      btn.innerHTML = btn.dataset.prodespIdleHtml;
      delete btn.dataset.prodespIdleHtml;
    }
  }

  function setModalButtonsEnabled(enabled) {
    ["btnProdespCadernoColetar", "btnProdespCadernoGerar"].forEach(function (id) {
      const b = document.getElementById(id);
      if (b && !coletandoEmAndamento && !gerandoEmAndamento) {
        b.disabled = !enabled;
      }
    });
  }

  function setStatus(msg, kind) {
    const el = document.getElementById("prodespCadernoStatus");
    if (!el) return;
    if (!msg) {
      el.classList.add("d-none");
      el.textContent = "";
      return;
    }
    el.className = "alert mt-3 mb-0 alert-" + (kind || "info");
    el.textContent = msg;
    el.classList.remove("d-none");
  }

  function apiUrl(path) {
    const base = window.PRODESP_URL_PREFIX || "/prodesp";
    return base + path;
  }

  function setColetaUi(loading) {
    coletandoEmAndamento = loading;
    document.querySelectorAll(".prodesp-caderno-btn-coletar").forEach(function (b) {
      setButtonLoading(b, loading);
    });
    document.querySelectorAll(".prodesp-caderno-btn-gerar").forEach(function (b) {
      if (b.id === "btnProdespCadernoGerar") return;
      b.disabled = loading || gerandoEmAndamento;
    });
    const modalGerar = document.getElementById("btnProdespCadernoGerar");
    if (modalGerar) modalGerar.disabled = loading || gerandoEmAndamento;
    if (loading) {
      setToolbarLoading(true);
      setStatus("Coletando logs via SSH… Não feche esta janela.", "info");
    } else {
      setToolbarLoading(false);
    }
  }

  async function coletarLogs(id, origem) {
    if (coletandoEmAndamento) {
      toast("Coleta já em andamento. Aguarde a conclusão.", "warning");
      return;
    }
    setColetaUi(true);
    try {
      const res = await fetch(apiUrl("/api/atendimentos/" + id + "/caderno/coletar-logs"), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        credentials: "same-origin",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.success) {
        const tempo = data.elapsed_seconds ? ` (${data.elapsed_seconds}s)` : "";
        const msg = (data.message || "Falha na coleta de logs.") + tempo;
        setToolbarResult(msg, "danger");
        setStatus(msg, "danger");
        toast(msg, "danger", "Erro na coleta");
        return;
      }
      const extra = data.errors && data.errors.length ? " Avisos: " + data.errors.join("; ") : "";
      const tempo = data.elapsed_seconds ? ` (${data.elapsed_seconds}s, ${data.commands_run || 0} comandos)` : "";
      const msg = (data.message || "Coleta concluída.") + tempo + extra;
      const kind = data.errors && data.errors.length ? "warning" : "success";
      setToolbarResult(msg, kind);
      setStatus(msg, kind);
      toast(msg, kind, kind === "warning" ? "Coleta parcial" : "Coleta de logs");
      await atualizarCampoLogsEdicao(id, data.logs_atendimento);
    } catch (e) {
      const msg = "Erro de rede na coleta.";
      setToolbarResult(msg, "danger");
      setStatus(msg, "danger");
      toast(msg, "danger", "Erro na coleta");
    } finally {
      setColetaUi(false);
      setModalButtonsEnabled(true);
    }
  }

  async function atualizarCampoLogsEdicao(id, logsStr) {
    let logs = logsStr;
    if (!logs) {
      try {
        const res = await fetch(apiUrl("/atendimentos/" + id));
        if (res.ok) {
          const d = await res.json();
          logs = d.logs_atendimento;
        }
      } catch (e) {
        return;
      }
    }
    if (typeof window.prodespSyncLogsAposColetaFgt === "function") {
      window.prodespSyncLogsAposColetaFgt(logs);
      return;
    }
    const container = document.getElementById("log-configuracao-remota-edit");
    if (typeof window.reloadLogs === "function" && container) {
      window.reloadLogs(logs, container, "edit");
    }
    ["viewLogs", "detailsLogs"].forEach(function (id) {
      const ta = document.getElementById(id);
      if (ta && logs) ta.value = logs;
    });
  }

  function validarQuestionario() {
    const q = lerQuestionario();
    const camposObr = [
      ["dhcp_server", "Possui DHCP-Server?", "prodespCadernoDhcpServer"],
      ["dhcp_relay", "Possui DHCP-Relay?", "prodespCadernoDhcpRelay"],
      ["vlan", "Possui VLAN?", "prodespCadernoVlan"],
      ["multi_ip_lan", "Possui mais de um IP na LAN?", "prodespCadernoMultiIpLan"],
      ["voip_tipo", "VOIP — CPE ou FGT?", "prodespCadernoVoipTipo"],
    ];
    for (let i = 0; i < camposObr.length; i++) {
      const campo = camposObr[i][0];
      const rotulo = camposObr[i][1];
      const elId = camposObr[i][2];
      if (!(q[campo] || "").trim()) {
        setStatus("Responda: " + rotulo, "danger");
        toast("Responda todas as perguntas do questionário.", "warning");
        const el = document.getElementById(elId);
        if (el) el.focus();
        return false;
      }
    }
    const voip = (q.voip_tipo || "").trim().toUpperCase();
    if (voip === "CPE" || voip === "FGT") {
      if (!(q.voip_nome || "").trim()) {
        setStatus("VOIP — Nome do colaborador é obrigatório quando VOIP ≠ N/A.", "danger");
        toast("Preencha o nome do colaborador VOIP.", "warning");
        return false;
      }
      if (!(q.voip_telefone || "").trim()) {
        setStatus("VOIP — Telefone fixo é obrigatório quando VOIP ≠ N/A.", "danger");
        toast("Preencha o telefone VOIP.", "warning");
        return false;
      }
    }
    const faltando = document.querySelectorAll(".prodesp-caderno-status-teste").length
      ? Array.from(document.querySelectorAll(".prodesp-caderno-status-teste")).filter(function (el) {
          return !(el.value || "").trim();
        })
      : [];
    if (faltando.length) {
      setStatus("Informe o status de todos os testes (Bandwidth e Cliente).", "danger");
      toast("Selecione o status de cada teste.", "warning");
      if (faltando[0]) faltando[0].focus();
      return false;
    }
    return true;
  }

  function resetStatusTestesDefaults() {
    document.querySelectorAll(".prodesp-caderno-status-teste").forEach(function (el) {
      const row = Number(el.getAttribute("data-row") || 0);
      if (row === 40) {
        el.value = STATUS_CONCLUIDO;
      } else if (row >= 41) {
        el.value = STATUS_PENDENTE;
      } else {
        el.value = "";
      }
    });
  }

  function lerStatusTestes() {
    const out = {};
    document.querySelectorAll(".prodesp-caderno-status-teste").forEach(function (el) {
      const row = el.getAttribute("data-row");
      const val = (el.value || "").trim();
      if (row && val) out[row] = val;
    });
    return out;
  }

  function syncVoipObrigatorio() {
    const tipo = ((document.getElementById("prodespCadernoVoipTipo") || {}).value || "").trim().toUpperCase();
    const obr = tipo === "CPE" || tipo === "FGT";
    const bloqueado = !obr;
    ["prodespCadernoVoipNome", "prodespCadernoVoipTel"].forEach(function (id) {
      const el = document.getElementById(id);
      if (!el) return;
      el.required = obr;
      el.disabled = bloqueado;
      el.classList.toggle("bg-light", bloqueado);
      el.classList.toggle("text-muted", bloqueado);
      if (bloqueado) el.value = "";
    });
    ["prodespVoipNomeReq", "prodespVoipTelReq"].forEach(function (id) {
      const el = document.getElementById(id);
      if (el) el.classList.toggle("d-none", !obr);
    });
    ["prodespCadernoVoipNome", "prodespCadernoVoipTel"].forEach(function (id) {
      const el = document.getElementById(id);
      const lbl = el && el.closest(".col-md-6, .col-12");
      if (lbl) lbl.classList.toggle("opacity-50", bloqueado);
    });
  }

  function lerQuestionario() {
    return {
      dhcp_server: (document.getElementById("prodespCadernoDhcpServer") || {}).value || "",
      dhcp_relay: (document.getElementById("prodespCadernoDhcpRelay") || {}).value || "",
      vlan: (document.getElementById("prodespCadernoVlan") || {}).value || "",
      multi_ip_lan: (document.getElementById("prodespCadernoMultiIpLan") || {}).value || "",
      voip_tipo: (document.getElementById("prodespCadernoVoipTipo") || {}).value || "",
      voip_nome: (document.getElementById("prodespCadernoVoipNome") || {}).value || "",
      voip_telefone: (document.getElementById("prodespCadernoVoipTel") || {}).value || "",
      executor_cliente: (document.getElementById("prodespCadernoExecutorCliente") || {}).value || "",
      status_testes: lerStatusTestes(),
    };
  }

  function mostrarDownload(data) {
    const wrap = document.getElementById("prodespCadernoDownloadWrap");
    const link = document.getElementById("prodespCadernoDownloadLink");
    if (!wrap || !link) return;
    const id = getAtendimentoId();
    const href =
      data.download_url ||
      (data.filename
        ? apiUrl("/api/atendimentos/" + id + "/caderno/download?file=" + encodeURIComponent(data.filename))
        : "");
    if (!href) {
      wrap.classList.add("d-none");
      return;
    }
    link.href = href;
    wrap.classList.remove("d-none");
  }

  function portalBandaLargaOk() {
    const sel = document.getElementById("prodespCadernoPortalBblOk");
    return !sel || (sel.value || "SIM").trim().toUpperCase() !== "NÃO";
  }

  function syncPortalBblUi() {
    const ok = portalBandaLargaOk();
    const normalWrap = document.getElementById("prodespCadernoEsaqNormalWrap");
    const indisWrap = document.getElementById("prodespCadernoEsaqIndisponivelWrap");
    if (normalWrap) normalWrap.classList.toggle("d-none", !ok);
    if (indisWrap) indisWrap.classList.toggle("d-none", ok);
    if (ok) {
      activeEsaqPasteAreaId = "prodespCadernoEsaqPaste";
    } else {
      activeEsaqPasteAreaId = esaqErroBblBase64
        ? "prodespCadernoEsaqSpeedtestPaste"
        : "prodespCadernoEsaqErroBblPaste";
    }
  }

  function validarImagensEsaq() {
    if (portalBandaLargaOk()) {
      if (!esaqBase64) {
        setStatus("Imagem ESAQ obrigatória.", "danger");
        toast("Selecione a imagem do teste Brasil Banda Larga antes de gerar.", "warning");
        return false;
      }
      return true;
    }
    if (!esaqErroBblBase64 || !esaqSpeedtestBase64) {
      setStatus("Evidências de erro e Speedtest obrigatórias.", "danger");
      toast(
        "Com Portal Banda Larga indisponível, informe as duas capturas (erro BBL e Speedtest).",
        "warning"
      );
      return false;
    }
    return true;
  }

  /** Limite de espera no browser (fila Excel no servidor + geração). */
  const CADERNO_GERAR_TIMEOUT_MS = 180000;

  async function gerarCaderno(id) {
    if (gerandoEmAndamento) {
      toast("Geração já em andamento.", "warning");
      return;
    }
    if (!validarQuestionario()) return;
    if (!validarImagensEsaq()) return;
    gerandoEmAndamento = true;
    const btnGerar = document.getElementById("btnProdespCadernoGerar");
    const btnColetar = document.getElementById("btnProdespCadernoColetar");
    setButtonLoading(btnGerar, true);
    if (btnColetar) btnColetar.disabled = true;
    setStatus("Gerando caderno…", "info");
    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    const abortTimer = controller
      ? window.setTimeout(function () {
          controller.abort();
        }, CADERNO_GERAR_TIMEOUT_MS)
      : null;
    try {
      const res = await fetch(apiUrl("/api/atendimentos/" + id + "/caderno/gerar"), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        credentials: "same-origin",
        signal: controller ? controller.signal : undefined,
        body: JSON.stringify({
          ...lerQuestionario(),
          portal_banda_larga_ok: portalBandaLargaOk() ? "SIM" : "NÃO",
          imagem_esaq: portalBandaLargaOk() ? esaqBase64 : "",
          imagem_erro_bbl: portalBandaLargaOk() ? "" : esaqErroBblBase64,
          imagem_speedtest: portalBandaLargaOk() ? "" : esaqSpeedtestBase64,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.success) {
        setStatus(data.message || "Falha ao gerar caderno.", "danger");
        toast(data.message || "Falha ao gerar caderno.", "danger");
        return;
      }
      setStatus(data.message || "Caderno gerado.", "success");
      toast(data.message || "Caderno gerado.", "success");
      mostrarDownload(data);
      if (data.carimbo_text) {
        cacheCarimboTexto(id, data.carimbo_text, data.carimbo_source || "xlsm");
      }
      if (data.filename) {
        const dl =
          data.download_url ||
          apiUrl("/api/atendimentos/" + id + "/caderno/download?file=" + encodeURIComponent(data.filename));
        const a = document.createElement("a");
        a.href = dl;
        a.target = "_blank";
        a.rel = "noopener";
        document.body.appendChild(a);
        a.click();
        a.remove();
      }
    } catch (e) {
      const aborted =
        (e && e.name === "AbortError") ||
        (typeof DOMException !== "undefined" && e instanceof DOMException && e.name === "AbortError");
      if (aborted) {
        const msg =
          "Tempo esgotado na geração (~3 min). Se o Excel no servidor estiver ocupado ou travado, aguarde e tente novamente; o servidor interrompe jobs acima de ~170s.";
        setStatus(msg, "danger");
        toast(msg, "warning");
      } else {
        setStatus("Erro de rede na geração.", "danger");
        toast("Erro de rede na geração.", "danger");
      }
    } finally {
      if (abortTimer !== null) window.clearTimeout(abortTimer);
      gerandoEmAndamento = false;
      setButtonLoading(btnGerar, false);
      setModalButtonsEnabled(true);
    }
  }

  function restaurarModaisAposFecharCaderno() {
    window.setTimeout(function () {
      if (window.ProdespModal && typeof window.ProdespModal.syncModalStack === "function") {
        window.ProdespModal.syncModalStack();
      } else if (window.ProdespModal && typeof window.ProdespModal.cleanupModalArtifacts === "function") {
        window.ProdespModal.cleanupModalArtifacts();
      }
    }, 0);
  }

  function abrirModalGerar(id) {
    const hid = document.getElementById("prodespCadernoAtendimentoId");
    if (hid) hid.value = id || getAtendimentoId();
    setStatus("", "");
    esaqBase64 = "";
    esaqErroBblBase64 = "";
    esaqSpeedtestBase64 = "";
    activeEsaqPasteAreaId = "prodespCadernoEsaqPaste";
    const portalSel = document.getElementById("prodespCadernoPortalBblOk");
    if (portalSel) portalSel.value = "SIM";
    syncPortalBblUi();
    const wrapDl = document.getElementById("prodespCadernoDownloadWrap");
    if (wrapDl) wrapDl.classList.add("d-none");
    const file = document.getElementById("prodespCadernoEsaqFile");
    if (file) file.value = "";
    limparAreaEsaq("prodespCadernoEsaqPaste", function () {
      esaqBase64 = "";
    });
    limparAreaEsaq("prodespCadernoEsaqErroBblPaste", function () {
      esaqErroBblBase64 = "";
    });
    limparAreaEsaq("prodespCadernoEsaqSpeedtestPaste", function () {
      esaqSpeedtestBase64 = "";
    });
    resetStatusTestesDefaults();

    const modalEl = document.getElementById("prodespCadernoTesteModal");
    if (!modalEl || !window.bootstrap) return;

    if (typeof window.prodespEnsureModalOnBody === "function") {
      window.prodespEnsureModalOnBody(modalEl);
    } else if (modalEl.parentElement !== document.body) {
      document.body.appendChild(modalEl);
    }

    const editAberto = document.getElementById("editModal")?.classList.contains("show");
    if (editAberto && typeof window.prodespShowStackedModal === "function") {
      window.prodespShowStackedModal(modalEl, { backdrop: false, keyboard: true });
    } else if (typeof window.prodespOpenModal === "function") {
      window.prodespOpenModal(modalEl);
    } else {
      bootstrap.Modal.getOrCreateInstance(modalEl, { backdrop: true, focus: true }).show();
    }

    syncVoipObrigatorio();
    modalEl.addEventListener(
      "shown.bs.modal",
      function onShown() {
        const area = document.getElementById("prodespCadernoEsaqPaste");
        if (area) area.focus();
      },
      { once: true }
    );
    if (coletandoEmAndamento) {
      setStatus("Coleta de logs em andamento…", "info");
      const btnColetar = document.getElementById("btnProdespCadernoColetar");
      setButtonLoading(btnColetar, true);
      if (document.getElementById("btnProdespCadernoGerar")) {
        document.getElementById("btnProdespCadernoGerar").disabled = true;
      }
    }
  }

  function aplicarImagemEsaq(areaId, dataUrl) {
    if (!dataUrl || !areaId) return;
    const handlers = esaqHandlersForArea(areaId);
    handlers.set(dataUrl);
    const sel40 = document.getElementById("prodespCadernoStatus40");
    if (sel40 && !(sel40.value || "").trim()) sel40.value = STATUS_CONCLUIDO;
    const area = document.getElementById(areaId);
    if (!area) return;
    area.querySelectorAll("img.preview, .btn-limpar-esaq").forEach((el) => el.remove());
    const ph = area.querySelector(".placeholder-text");
    if (ph) ph.style.display = "none";
    const img = document.createElement("img");
    img.className = "preview";
    img.src = dataUrl;
    img.alt = "Pré-visualização";
    area.prepend(img);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-danger btn-sm btn-limpar-esaq";
    btn.innerHTML = "✕";
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      limparAreaEsaq(areaId, handlers.clear);
    });
    area.appendChild(btn);
  }

  function limparAreaEsaq(areaId, onClear) {
    if (typeof onClear === "function") onClear();
    const area = document.getElementById(areaId);
    if (!area) return;
    area.querySelectorAll("img.preview, .btn-limpar-esaq").forEach((el) => el.remove());
    const ph = area.querySelector(".placeholder-text");
    if (ph) ph.style.display = "";
  }

  let docPasteHandler = null;

  function ativarPasteGlobal() {
    if (docPasteHandler) return;
    docPasteHandler = function (e) {
      const modal = document.getElementById("prodespCadernoTesteModal");
      if (!modal || !modal.classList.contains("show")) return;
      const items = (e.clipboardData || {}).items || [];
      for (let i = 0; i < items.length; i++) {
        if (items[i].type && items[i].type.indexOf("image") === 0) {
          e.preventDefault();
          processarArquivoEsaq(items[i].getAsFile(), activeEsaqPasteAreaId);
          return;
        }
      }
    };
    document.addEventListener("paste", docPasteHandler);
  }

  function desativarPasteGlobal() {
    if (docPasteHandler) {
      document.removeEventListener("paste", docPasteHandler);
      docPasteHandler = null;
    }
  }

  function esaqHandlersForArea(areaId) {
    if (areaId === "prodespCadernoEsaqErroBblPaste") {
      return {
        set: function (v) {
          esaqErroBblBase64 = v;
        },
        clear: function () {
          esaqErroBblBase64 = "";
        },
      };
    }
    if (areaId === "prodespCadernoEsaqSpeedtestPaste") {
      return {
        set: function (v) {
          esaqSpeedtestBase64 = v;
        },
        clear: function () {
          esaqSpeedtestBase64 = "";
        },
      };
    }
    return {
      set: function (v) {
        esaqBase64 = v;
      },
      clear: function () {
        esaqBase64 = "";
      },
    };
  }

  function bindEsaqPasteArea(areaId) {
    const area = document.getElementById(areaId);
    if (!area) return;

    area.addEventListener("click", function () {
      activeEsaqPasteAreaId = areaId;
      area.focus();
    });
    area.addEventListener("focus", function () {
      activeEsaqPasteAreaId = areaId;
    });

    area.addEventListener("paste", function (e) {
      const items = (e.clipboardData || {}).items || [];
      for (let i = 0; i < items.length; i++) {
        if (items[i].type && items[i].type.indexOf("image") === 0) {
          e.preventDefault();
          activeEsaqPasteAreaId = areaId;
          processarArquivoEsaq(items[i].getAsFile(), areaId);
          return;
        }
      }
    });

    area.addEventListener("dragover", function (e) {
      e.preventDefault();
      area.classList.add("drag-over");
    });
    area.addEventListener("dragleave", function () {
      area.classList.remove("drag-over");
    });
    area.addEventListener("drop", function (e) {
      e.preventDefault();
      area.classList.remove("drag-over");
      activeEsaqPasteAreaId = areaId;
      const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (file && file.type.startsWith("image/")) {
        processarArquivoEsaq(file, areaId);
      }
    });
  }

  function bindEsaqPaste() {
    const modal = document.getElementById("prodespCadernoTesteModal");
    if (modal) {
      modal.addEventListener("shown.bs.modal", ativarPasteGlobal);
      modal.addEventListener("hidden.bs.modal", function () {
        desativarPasteGlobal();
        restaurarModaisAposFecharCaderno();
      });
    }

    bindEsaqPasteArea("prodespCadernoEsaqPaste");
    bindEsaqPasteArea("prodespCadernoEsaqErroBblPaste");
    bindEsaqPasteArea("prodespCadernoEsaqSpeedtestPaste");

    const portalSel = document.getElementById("prodespCadernoPortalBblOk");
    if (portalSel) {
      portalSel.addEventListener("change", syncPortalBblUi);
    }
    syncPortalBblUi();
  }

  function processarArquivoEsaq(file, areaId) {
    if (!file) return;
    const targetId = areaId || activeEsaqPasteAreaId || "prodespCadernoEsaqPaste";
    if (file.size > 6 * 1024 * 1024) {
      setStatus("Imagem muito grande (máx. 6 MB).", "danger");
      return;
    }
    const reader = new FileReader();
    reader.onload = function () {
      aplicarImagemEsaq(targetId, String(reader.result || ""));
    };
    reader.readAsDataURL(file);
  }

  function bindVoip() {
    const sel = document.getElementById("prodespCadernoVoipTipo");
    if (sel) {
      sel.addEventListener("change", syncVoipObrigatorio);
      syncVoipObrigatorio();
    }
  }

  async function obterTextoCarimboParaId(id) {
    const cached = obterCarimboCache(id);
    if (cached && cached.text) {
      return {
        text: cached.text,
        source: cached.source || "caderno",
        origem: labelOrigemCarimbo(cached.source),
      };
    }
    const res = await fetch(apiUrl("/api/atendimentos/" + id + "/caderno/carimbo-texto"), {
      method: "GET",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.success || !data.text) {
      return {
        error: data.message || "Não foi possível obter o Carimbo NOC.",
      };
    }
    const origem = labelOrigemCarimbo(data.source);
    const texto = String(data.text || "");
    cacheCarimboTexto(id, texto, data.source || origem);
    return { text: texto, source: data.source || origem, origem: origem };
  }

  async function copiarCarimboNoc(id) {
    if (!id) {
      toast("Atendimento não identificado.", "warning", "Carimbo NOC");
      return;
    }
    try {
      const data = await obterTextoCarimboParaId(id);
      if (data.error) {
        toast(data.error, "danger", "Carimbo NOC");
        return;
      }
      const texto = data.text;
      const origem = data.origem;

      if (!abrirModalCarimboNocCopia(texto, origem, id)) {
        toast(
          "Não foi possível abrir o painel do Carimbo NOC. Tente novamente.",
          "danger",
          "Carimbo NOC"
        );
        return;
      }

      if (clipboardCarimboConfiavel() && (await copiarTextoCarimbo(texto))) {
        notificarCarimboCopiado(origem);
      }
    } catch (e) {
      toast("Não foi possível obter o Carimbo NOC. Tente novamente.", "danger", "Carimbo NOC");
    }
  }

  let cadernoToolbarButtonsBound = false;

  function bindButtons() {
    if (cadernoToolbarButtonsBound) return;
    cadernoToolbarButtonsBound = true;

    document.addEventListener("click", function (e) {
      const coletar = e.target.closest(".prodesp-caderno-btn-coletar");
      if (coletar && coletar.closest(".prodesp-caderno-toolbar")) {
        activeToolbarPrefix = prefixFromButton(coletar);
        const id = getAtendimentoIdForPrefix(activeToolbarPrefix);
        if (!id) {
          toast("Atendimento não identificado.", "warning");
          return;
        }
        coletarLogs(id, "toolbar");
        return;
      }
      const gerar = e.target.closest(".prodesp-caderno-btn-gerar");
      if (gerar && gerar.closest(".prodesp-caderno-toolbar")) {
        activeToolbarPrefix = prefixFromButton(gerar);
        const id = getAtendimentoIdForPrefix(activeToolbarPrefix);
        if (!id) {
          toast("Atendimento não identificado.", "warning");
          return;
        }
        abrirModalGerar(id);
        return;
      }
      const copiar = e.target.closest(".prodesp-caderno-btn-copiar");
      if (copiar && copiar.closest(".prodesp-caderno-toolbar")) {
        activeToolbarPrefix = prefixFromButton(copiar);
        const id = getAtendimentoIdForPrefix(activeToolbarPrefix);
        if (!id) return;
        copiarCarimboNoc(id);
      }
    });

    const coletarModal = document.getElementById("btnProdespCadernoColetar");
    if (coletarModal) {
      coletarModal.addEventListener("click", function () {
        const id = getAtendimentoId();
        if (!id) return;
        coletarLogs(id, "modal");
      });
    }
    const gerarModal = document.getElementById("btnProdespCadernoGerar");
    if (gerarModal) {
      gerarModal.addEventListener("click", function () {
        const id = getAtendimentoId();
        if (!id) return;
        gerarCaderno(id);
      });
    }
    const copiarModal = document.getElementById("btnProdespCadernoCopiarCarimbo");
    if (copiarModal) {
      copiarModal.addEventListener("click", function () {
        const id = getAtendimentoId();
        if (!id) return;
        copiarCarimboNoc(id);
      });
    }
    const btnCarimboBaixar = document.getElementById("btnProdespCarimboNocBaixarTxt");
    if (btnCarimboBaixar) {
      btnCarimboBaixar.addEventListener("click", function () {
        const area = document.getElementById("prodespCarimboNocCopiaTexto");
        const modalEl = document.getElementById("prodespCarimboNocCopiaModal");
        const texto = area ? area.value : "";
        const aid = modalEl ? modalEl.dataset.prodespCarimboAtendimentoId || "" : "";
        baixarCarimboTxt(texto, aid);
      });
    }
    sincronizarBotoesModalCarimbo();
    const btnCarimboCopiar = document.getElementById("btnProdespCarimboNocCopiaConfirmar");
    if (btnCarimboCopiar) {
      btnCarimboCopiar.addEventListener("click", async function () {
        const area = document.getElementById("prodespCarimboNocCopiaTexto");
        const texto = area ? area.value : "";
        if (!texto) {
          toast("Nenhum texto do Carimbo NOC para copiar.", "warning", "Carimbo NOC");
          return;
        }
        if (await copiarTextoCarimbo(texto)) {
          toast("Carimbo NOC copiado.", "success", "Carimbo NOC");
          const modalEl = document.getElementById("prodespCarimboNocCopiaModal");
          if (modalEl && typeof bootstrap !== "undefined") {
            const inst = bootstrap.Modal.getInstance(modalEl);
            if (inst) inst.hide();
          }
          return;
        }
        if (area) {
          area.focus({ preventScroll: true });
          area.select();
          area.setSelectionRange(0, texto.length);
        }
        toast("Selecione o texto e use Ctrl+C, ou baixe o arquivo .txt.", "warning", "Carimbo NOC");
      });
    }
  }

  function prodespInitCadernoTeste() {
    bindEsaqPaste();
    bindVoip();
    bindButtons();
  }

  document.addEventListener("DOMContentLoaded", prodespInitCadernoTeste);
  if (document.readyState !== "loading") {
    prodespInitCadernoTeste();
  }

  window.prodespCadernoAtualizarToolbar = atualizarToolbarCaderno;
  window.prodespCadernoAbrirModal = abrirModalGerar;
  window.prodespCadernoCopiarCarimbo = copiarCarimboNoc;
  window.prodespInitCadernoTeste = prodespInitCadernoTeste;
})();
