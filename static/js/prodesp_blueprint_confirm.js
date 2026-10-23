/**
 * Modal de confirmação do Blueprint PRODESP.
 * - Atendimentos: POST /api/gerar_blueprint_prodesp sem confirm → prévia; com confirm → gera.
 * - Criar blueprint: prévia com overrides do formulário; confirma → callback.
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

  function toast(msg, type) {
    if (typeof global.showToast === "function") {
      global.showToast(msg, type || "info");
      return;
    }
    try {
      console.log("[blueprint]", type, msg);
    } catch (_e) {
      /* ignore */
    }
  }

  /** Dispara download sem navegar a página (mesmo padrão do caderno). */
  function triggerBlueprintDownload(url) {
    if (!url) return;
    try {
      const a = document.createElement("a");
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (_e) {
      try {
        global.location.href = url;
      } catch (_e2) {
        /* ignore */
      }
    }
  }

  /** Form da página criar_blueprint (submit guard trava antes do modal). */
  function blueprintPageForm() {
    return document.getElementById("blueprint-form");
  }

  function unlockBlueprintPageForm() {
    const guard = global.ProdespSubmitGuard;
    if (!guard || typeof guard.unlockForm !== "function") return;
    const form = blueprintPageForm();
    if (form) guard.unlockForm(form);
  }

  function unlockBlueprintUi() {
    unlockBlueprintPageForm();
    const guard = global.ProdespSubmitGuard;
    const confirmBtn = document.getElementById("bpConfirmBtnGerar");
    if (confirmBtn && guard) guard.unlock(confirmBtn);
  }

  /** Ao fechar modal sem confirmar: libera “Gerando…” / form travado. */
  function bindModalDismissUnlock() {
    const el = document.getElementById("modalBlueprintConfirm");
    if (!el || el._bpConfirmDismissBound) return;
    el._bpConfirmDismissBound = true;
    el.addEventListener("hidden.bs.modal", function () {
      const form = blueprintPageForm();
      /* Confirmação já disparou submit real — não mexer no lock de navegação. */
      if (form && form.dataset.bpConfirmOk === "1") return;
      unlockBlueprintUi();
    });
  }

  function maskSelectHtml(lan, options) {
    const opts = options || [];
    const mapped = (lan && lan.mapped_mask) || "";
    let html = '<select class="form-select form-select-sm bp-confirm-mask">';
    let found = false;
    opts.forEach(function (o) {
      const sel = o.mask === mapped ? " selected" : "";
      if (sel) found = true;
      html +=
        '<option value="' +
        esc(o.mask) +
        '"' +
        sel +
        ">" +
        esc(o.label || o.mask) +
        "</option>";
    });
    if (mapped && !found) {
      html =
        '<option value="' +
        esc(mapped) +
        '" selected>' +
        esc(lan.mask_label || mapped) +
        " (regra)</option>" +
        html.slice(html.indexOf(">") + 1);
    }
    if (!mapped && !opts.length) {
      html += '<option value="">—</option>';
    }
    html += "</select>";
    return html;
  }

  function renderConfirm(payload) {
    const modalEl = document.getElementById("modalBlueprintConfirm");
    if (!modalEl || !payload) return null;

    const errBox = document.getElementById("bpConfirmErrors");
    if (errBox) {
      if (payload.valid === false && payload.errors && payload.errors.length) {
        errBox.textContent =
          "Pendências: " + (payload.errors || []).join(", ");
        errBox.classList.remove("d-none");
      } else {
        errBox.textContent = "";
        errBox.classList.add("d-none");
      }
    }

    const host = document.getElementById("bpConfirmHostname");
    if (host) host.value = payload.hostname || "";

    const lanRows = document.getElementById("bpConfirmLanRows");
    if (lanRows) {
      lanRows.innerHTML = "";
      lanRows.className = "bp-confirm-lan-list";

      const blockTitles = {
        lan: "LAN 1",
        lan_sec: "LAN SEC",
        lan_ter: "LAN TER",
        lan_qua: "LAN QUA",
      };
      const redesByLan = {};
      (payload.redes || []).forEach(function (rede) {
        if (rede.lan_key) redesByLan[rede.lan_key] = rede;
      });

      (payload.lans || []).forEach(function (lan) {
        const rede = redesByLan[lan.key] || null;
        const show =
          lan.show ||
          lan.filled ||
          lan.key === "lan" ||
          (rede && (rede.filled || rede.key === "rede_lan"));
        if (!show) return;

        const block = document.createElement("div");
        block.className = "bp-confirm-lan-block";
        block.dataset.lanKey = lan.key;
        if (rede && rede.js_key) block.dataset.redeJs = rede.js_key;

        const title = blockTitles[lan.key] || lan.label || lan.key;
        const hint = lan.allow_mask_without_ip
          ? '<div class="form-text small text-muted mb-2">Sem IP: a máscara será usada junto com a Rede LAN neste bloco.</div>'
          : "";

        const redeRo = rede && rede.editable === false ? " readonly" : "";
        const redeVal = rede ? rede.value || "" : "";
        const redeLabel = rede
          ? rede.label
          : lan.key === "lan"
            ? "Rede LAN 1 (calculada)"
            : "Rede LAN";
        const redePlaceholder =
          rede && rede.editable === false ? "" : "IP de rede (opcional)";

        block.innerHTML =
          '<div class="bp-confirm-lan-block-title">' +
          esc(title) +
          "</div>" +
          hint +
          '<div class="row g-2 align-items-end">' +
          '<div class="col-md-4">' +
          '<label class="form-label small mb-0">IP</label>' +
          '<input type="text" class="form-control form-control-sm bp-confirm-ip" value="' +
          esc(lan.ip_cidr || "") +
          '" placeholder="IP/CIDR">' +
          "</div>" +
          '<div class="col-md-4">' +
          '<label class="form-label small mb-0">Máscara</label>' +
          maskSelectHtml(lan, payload.mask_options) +
          "</div>" +
          '<div class="col-md-4">' +
          '<label class="form-label small mb-0">' +
          esc(redeLabel) +
          "</label>" +
          '<input type="text" class="form-control form-control-sm bp-confirm-rede" value="' +
          esc(redeVal) +
          '" placeholder="' +
          esc(redePlaceholder) +
          '"' +
          redeRo +
          ">" +
          "</div>" +
          "</div>";
        lanRows.appendChild(block);
      });
    }

    const gw = document.getElementById("bpConfirmGateways");
    if (gw) {
      const list = payload.gateways || [];
      if (!list.length) {
        gw.textContent = "Nenhum gateway MPLS/STATIC cadastrado.";
      } else {
        gw.innerHTML = list
          .map(function (g) {
            return (
              "<div><strong>" +
              esc(g.tipo) +
              "</strong> " +
              esc(g.operadora) +
              " · WAN " +
              esc(g.ip_wan) +
              " · GW " +
              esc(g.gateway) +
              " · Mask " +
              esc(g.mascara) +
              "</div>"
            );
          })
          .join("");
      }
    }

    const bp = document.getElementById("bpConfirmDeviceBp");
    if (bp) bp.textContent = payload.device_blueprint || "—";
    const motivo = document.getElementById("bpConfirmDeviceMotivo");
    if (motivo) motivo.textContent = payload.device_blueprint_motivo || "";

    const btn = document.getElementById("bpConfirmBtnGerar");
    if (btn) btn.disabled = payload.valid === false;

    return modalEl;
  }

  function collectOverrides() {
    const out = {};
    const host = document.getElementById("bpConfirmHostname");
    if (host) out.hostname = host.value.trim();

    const keyToIp = {
      lan: "ip_lan_01",
      lan_sec: "mv_ip_lan_sec",
      lan_ter: "mv_ip_lan_ter",
      lan_qua: "mv_ip_lan_qua",
    };
    document.querySelectorAll("#bpConfirmLanRows [data-lan-key]").forEach(function (block) {
      const key = block.getAttribute("data-lan-key");
      const ipInput = block.querySelector(".bp-confirm-ip");
      const maskSel = block.querySelector(".bp-confirm-mask");
      const redeInput = block.querySelector(".bp-confirm-rede");
      const redeJs = block.getAttribute("data-rede-js");
      const ipJs = keyToIp[key];
      if (ipJs && ipInput) out[ipJs] = ipInput.value.trim();
      if (maskSel && maskSel.value) out["mask_" + key] = maskSel.value;
      if (redeJs && redeInput && !redeInput.readOnly) {
        out[redeJs] = redeInput.value.trim();
      }
    });
    return out;
  }

  function openModal(payload) {
    const el = renderConfirm(payload);
    if (!el || typeof bootstrap === "undefined") return null;
    const modal = bootstrap.Modal.getOrCreateInstance(el);
    modal.show();
    return modal;
  }

  /**
   * Fluxo atendimentos: 1º POST prévia, 2º POST confirm+overrides.
   */
  async function generateWithConfirm(idVgr) {
    if (!idVgr) {
      toast("ID VGR não encontrado para gerar o blueprint.", "danger");
      return;
    }
    bindModalDismissUnlock();
    try {
      toast("Preparando confirmação do blueprint...", "info");
      const r1 = await fetch("/prodesp/api/gerar_blueprint_prodesp/" + encodeURIComponent(idVgr), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({}),
      });
      const j1 = await r1.json();
      if (!j1.success) {
        toast(j1.message || "Falha ao preparar blueprint.", "danger");
        unlockBlueprintUi();
        return;
      }
      if (!j1.needs_confirm || !j1.confirm) {
        if (j1.download_url) {
          toast(j1.message || "Blueprint gerado.", "success");
          triggerBlueprintDownload(j1.download_url);
        }
        return;
      }

      const modal = openModal(j1.confirm);
      if (
        j1.confirm &&
        j1.confirm.valid === false &&
        j1.confirm.errors &&
        j1.confirm.errors.length &&
        global.ProdespLiveValidation &&
        typeof global.ProdespLiveValidation.paintBlueprintServerPendencias === "function"
      ) {
        /* Fila/gestão: não há form criar_blueprint; helper é no-op sem #blueprint-form. */
        global.ProdespLiveValidation.paintBlueprintServerPendencias(
          document.getElementById("blueprint-form"),
          j1.confirm.errors
        );
      }
      const btn = document.getElementById("bpConfirmBtnGerar");
      if (!btn) return;

      const onConfirm = async function () {
        const guard = global.ProdespSubmitGuard;
        if (guard) {
          guard.lock(btn, { label: "Gerando…", autoUnlockMs: 120000 });
        } else {
          btn.disabled = true;
        }
        try {
          const overrides = collectOverrides();
          const r2 = await fetch(
            "/prodesp/api/gerar_blueprint_prodesp/" + encodeURIComponent(idVgr),
            {
              method: "POST",
              headers: { "Content-Type": "application/json", Accept: "application/json" },
              credentials: "same-origin",
              body: JSON.stringify({ confirm: true, overrides: overrides }),
            }
          );
          const j2 = await r2.json();
          if (j2.success && j2.download_url) {
            if (modal) modal.hide();
            toast(j2.message || "Blueprint gerado.", "success");
            triggerBlueprintDownload(j2.download_url);
            return;
          }
          toast(j2.message || "Não foi possível gerar.", "danger");
          if (j2.confirm) openModal(j2.confirm);
        } catch (err) {
          console.error(err);
          toast("Erro ao gerar blueprint. Verifique o console.", "danger");
        } finally {
          if (guard) guard.unlock(btn);
          else btn.disabled = false;
        }
      };

      btn.onclick = onConfirm;
    } catch (err) {
      console.error(err);
      toast("Erro ao gerar blueprint. Verifique o console.", "danger");
      unlockBlueprintUi();
    }
  }

  /**
   * Fluxo página criar_blueprint: prévia com form completo (+ overrides opcionais).
   * @param {string} idVgr
   * @param {object} payloadOrOverrides — { form, overrides } ou só overrides (legado)
   * @param {Function} onConfirm
   */
  async function previewThenConfirm(idVgr, payloadOrOverrides, onConfirm) {
    bindModalDismissUnlock();
    const payload =
      payloadOrOverrides &&
      typeof payloadOrOverrides === "object" &&
      (payloadOrOverrides.form || payloadOrOverrides.overrides)
        ? {
            form: payloadOrOverrides.form || undefined,
            overrides: payloadOrOverrides.overrides || {},
          }
        : { overrides: payloadOrOverrides || {} };
    try {
      const r = await fetch(
        "/prodesp/api/preview_blueprint_prodesp/" + encodeURIComponent(idVgr),
        {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          credentials: "same-origin",
          body: JSON.stringify(payload),
        }
      );
      const j = await r.json();
      if (!j.success || !j.confirm) {
        toast((j && j.message) || "Falha na prévia do blueprint.", "danger");
        unlockBlueprintUi();
        return;
      }
      openModal(j.confirm);
      /* Modal aberto: libera o botão da página (cancelar / clique fora). */
      unlockBlueprintPageForm();
      const formEl = blueprintPageForm();
      if (
        formEl &&
        j.confirm &&
        j.confirm.valid === false &&
        j.confirm.errors &&
        j.confirm.errors.length &&
        global.ProdespLiveValidation &&
        typeof global.ProdespLiveValidation.paintBlueprintServerPendencias === "function"
      ) {
        global.ProdespLiveValidation.paintBlueprintServerPendencias(formEl, j.confirm.errors);
      }
      const btn = document.getElementById("bpConfirmBtnGerar");
      if (!btn) return;
      btn.onclick = function () {
        const form = blueprintPageForm();
        const guard = global.ProdespSubmitGuard;
        if (form && guard && typeof guard.lockForm === "function") {
          guard.lockForm(form, { label: "Gerando Blueprint…" });
        }
        const ov = collectOverrides();
        if (typeof onConfirm === "function") onConfirm(ov);
      };
    } catch (err) {
      console.error(err);
      toast("Erro na prévia do blueprint. Verifique o console.", "danger");
      unlockBlueprintUi();
    }
  }

  /** Serializa campos do form Criar Blueprint (inclui links MPLS/STATIC). */
  function collectFormFields(formEl) {
    const out = {};
    if (!formEl || !formEl.elements) return out;
    Array.prototype.forEach.call(formEl.elements, function (el) {
      if (!el || !el.name || el.disabled) return;
      const tag = (el.tagName || "").toLowerCase();
      const type = (el.type || "").toLowerCase();
      if (type === "submit" || type === "button" || type === "file") return;
      if (type === "checkbox" || type === "radio") {
        if (el.checked) out[el.name] = el.value || "1";
        return;
      }
      if (tag === "select" && el.multiple) {
        const vals = [];
        Array.prototype.forEach.call(el.options, function (opt) {
          if (opt.selected) vals.push(opt.value);
        });
        out[el.name] = vals;
        return;
      }
      out[el.name] = el.value;
    });
    return out;
  }

  /** Cascata SEC → TER → QUA (IP + Rede) via data-lan-tier / data-lan-role. */
  function bindLanCascade(root) {
    const scope = root || document;

    function filled(el) {
      return !!(el && String(el.value || "").trim());
    }

    function syncBlock(block) {
      if (!block) return;
      const byTier = { sec: [], ter: [], qua: [] };
      block.querySelectorAll("[data-lan-tier]").forEach(function (el) {
        const t = el.getAttribute("data-lan-tier");
        if (byTier[t]) byTier[t].push(el);
      });
      const secIp = byTier.sec.find(function (e) {
        return e.getAttribute("data-lan-role") === "ip";
      });
      const terIp = byTier.ter.find(function (e) {
        return e.getAttribute("data-lan-role") === "ip";
      });
      /* Porta: IP SEC (preferencial); Rede SEC também conta se IP ainda vazio */
      const secOk = filled(secIp) || byTier.sec.some(filled);
      const terOk = filled(terIp) || byTier.ter.some(filled);

      byTier.sec.forEach(function (el) {
        if (!el.readOnly) el.disabled = false;
      });
      byTier.ter.forEach(function (el) {
        if (el.readOnly) return;
        el.disabled = !secOk;
        if (!secOk) el.value = "";
      });
      byTier.qua.forEach(function (el) {
        if (el.readOnly) return;
        el.disabled = !(secOk && terOk);
        if (!(secOk && terOk)) el.value = "";
      });
    }

    function sync() {
      const blocks = scope.querySelectorAll("[data-prodesp-lan-extra]");
      if (blocks.length) {
        blocks.forEach(syncBlock);
        return;
      }
      /* fallback: agrupa por formulário */
      const groups = {};
      scope.querySelectorAll("[data-lan-tier]").forEach(function (el) {
        const form = el.closest("form") || el.closest("[data-prodesp-lan-extra]") || scope;
        const key = form.id || "anon";
        if (!groups[key]) groups[key] = form;
      });
      Object.keys(groups).forEach(function (k) {
        syncBlock(groups[k]);
      });
    }

    function onLanEvent(ev) {
      const t = ev.target;
      if (!t || !t.getAttribute) return;
      if (t.getAttribute("data-lan-tier")) sync();
    }

    ["input", "change", "blur", "keyup", "paste"].forEach(function (evt) {
      scope.addEventListener(evt, onLanEvent, true);
    });
    sync();
    /* Valores pré-preenchidos / IMask: re-sincroniza após paint */
    setTimeout(sync, 0);
    setTimeout(sync, 300);
  }

  global.ProdespBlueprintConfirm = {
    generateWithConfirm: generateWithConfirm,
    previewThenConfirm: previewThenConfirm,
    collectOverrides: collectOverrides,
    collectFormFields: collectFormFields,
    openModal: openModal,
    bindLanCascade: bindLanCascade,
    triggerDownload: triggerBlueprintDownload,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      bindLanCascade(document);
      bindModalDismissUnlock();
    });
  } else {
    bindLanCascade(document);
    bindModalDismissUnlock();
  }
})(typeof window !== "undefined" ? window : globalThis);
