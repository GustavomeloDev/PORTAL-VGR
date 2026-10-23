/**
 * Exportação de certificados FortiGate PRODESP — SSH + TFTP (mesmo fluxo da coleta de logs).
 */
(function () {
  "use strict";

  const TOOLBAR_PREFIXES = ["edit", "view", "create", "details"];
  let activeToolbarPrefix = "edit";
  let exportandoEmAndamento = false;

  function isAdmin() {
    if (Number(window.PRODESP_ADMIN_USER || 0) === 1) return true;
    if (typeof LOGGED_IN_USER_ADMIN !== "undefined" && Number(LOGGED_IN_USER_ADMIN || 0) === 1) {
      return true;
    }
    return false;
  }

  function apiUrl(path) {
    const base = window.PRODESP_URL_PREFIX || "/prodesp";
    return base + path;
  }

  function toast(msg, kind) {
    if (typeof window.showToast === "function") {
      window.showToast(msg, kind || "info");
      return;
    }
    if (typeof window.toastr !== "undefined") {
      window.toastr[kind === "danger" ? "error" : kind || "info"](msg);
    }
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
      (btn &&
        btn.closest &&
        btn.closest("[data-prodesp-certificado-prefix]") &&
        btn.closest("[data-prodesp-certificado-prefix]").dataset.prodespCertificadoPrefix) ||
      "edit"
    );
  }

  function setButtonLoading(btn, loading) {
    if (!btn) return;
    const label = btn.querySelector(".prodesp-certificado-btn-label");
    const spin = btn.querySelector(".prodesp-certificado-btn-spinner");
    btn.disabled = loading;
    if (label) label.classList.toggle("d-none", loading);
    if (spin) spin.classList.toggle("d-none", !loading);
  }

  function limparToolbarStatusPrefix(prefix) {
    const box = document.getElementById(prefix + "CertificadoToolbarStatus");
    const result = document.getElementById(prefix + "CertificadoToolbarResult");
    const toolbar = document.getElementById(prefix + "CertificadoToolbar");
    if (box) box.classList.add("d-none");
    if (result) {
      result.classList.add("d-none");
      result.textContent = "";
    }
    if (toolbar) toolbar.removeAttribute("aria-busy");
  }

  function setToolbarLoading(loading, text) {
    const prefix = activeToolbarPrefix;
    const box = document.getElementById(prefix + "CertificadoToolbarStatus");
    const txt = document.getElementById(prefix + "CertificadoToolbarStatusText");
    const result = document.getElementById(prefix + "CertificadoToolbarResult");
    const toolbar = document.getElementById(prefix + "CertificadoToolbar");
    if (result) result.classList.add("d-none");
    if (box && txt) {
      txt.textContent =
        text ||
        "Exportando certificado(s) via SSH (jump → FGT) e TFTP. Normal: 1–3 min. Não clique novamente.";
      box.classList.toggle("d-none", !loading);
      const spin = box.querySelector(".prodesp-certificado-toolbar-spinner");
      if (spin) spin.classList.toggle("d-none", !loading);
    }
    if (toolbar) toolbar.setAttribute("aria-busy", loading ? "true" : "false");
  }

  function setToolbarResult(msg, kind) {
    const prefix = activeToolbarPrefix;
    const box = document.getElementById(prefix + "CertificadoToolbarStatus");
    const result = document.getElementById(prefix + "CertificadoToolbarResult");
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

  function atualizarToolbarCertificado() {
    TOOLBAR_PREFIXES.forEach(function (prefix) {
      const bar = document.getElementById(prefix + "CertificadoToolbar");
      if (!bar) return;
      bar.classList.toggle("d-none", !isAdmin());
      if (!isAdmin()) limparToolbarStatusPrefix(prefix);
    });
  }

  function setExportUi(loading) {
    exportandoEmAndamento = loading;
    document.querySelectorAll(".prodesp-certificado-btn-exportar").forEach(function (b) {
      setButtonLoading(b, loading);
    });
    setToolbarLoading(loading);
  }

  function formatResultMessage(data) {
    const tempo = data.elapsed_seconds ? " (" + data.elapsed_seconds + "s)" : "";
    let msg = (data.message || "Exportação concluída.") + tempo;
    const certs = data.certificados || [];
    const okList = certs.filter(function (c) {
      return c.ok;
    });
    if (okList.length) {
      msg +=
        " Arquivos: " +
        okList
          .map(function (c) {
            return c.arquivo || c.nome;
          })
          .join(", ");
    }
    if (data.errors && data.errors.length) {
      msg += " Detalhes: " + data.errors.slice(0, 3).join("; ");
      if (data.errors.length > 3) {
        msg += " (+" + (data.errors.length - 3) + " mais)";
      }
    }
    const failed = certs.filter(function (c) {
      return !c.ok && c.erro;
    });
    if (failed.length && !okList.length && !(data.errors && data.errors.length)) {
      msg += " Detalhe: " + failed.slice(0, 2).map(function (c) {
        return (c.nome || "?") + " — " + c.erro;
      }).join("; ");
    }
    if (data.email_enviado === false) {
      msg += " E-mail não enviado.";
    }
    return msg;
  }

  async function exportarCertificado(id) {
    if (exportandoEmAndamento) {
      toast("Exportação já em andamento. Aguarde a conclusão.", "warning");
      return;
    }
    if (!id) {
      toast("Salve o atendimento antes de exportar o certificado.", "warning");
      return;
    }
    setExportUi(true);
    try {
      const res = await fetch(apiUrl("/api/atendimentos/" + id + "/certificados/exportar"), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        credentials: "same-origin",
      });
      const data = await res.json().catch(function () {
        return {};
      });
      if (!res.ok || !data.success) {
        const msg = formatResultMessage(data) || data.message || "Falha na exportação do certificado.";
        setToolbarResult(msg, "danger");
        toast(msg, "danger");
        return;
      }
      const msg = formatResultMessage(data);
      const kind = data.errors && data.errors.length ? "warning" : "success";
      setToolbarResult(msg, kind);
      toast(msg, kind);
    } catch (e) {
      const msg = "Erro de rede na exportação do certificado.";
      setToolbarResult(msg, "danger");
      toast(msg, "danger");
    } finally {
      setExportUi(false);
    }
  }

  function bindEvents() {
    document.querySelectorAll(".prodesp-certificado-btn-exportar").forEach(function (btn) {
      if (btn.dataset.prodespCertificadoBound === "1") return;
      btn.dataset.prodespCertificadoBound = "1";
      btn.addEventListener("click", function () {
        activeToolbarPrefix = prefixFromButton(btn);
        const id = getAtendimentoIdForPrefix(activeToolbarPrefix);
        exportarCertificado(id);
      });
    });
  }

  function prodespInitCertificadoExport() {
    atualizarToolbarCertificado();
    bindEvents();
  }

  window.prodespInitCertificadoExport = prodespInitCertificadoExport;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", prodespInitCertificadoExport);
  } else {
    prodespInitCertificadoExport();
  }
})();
