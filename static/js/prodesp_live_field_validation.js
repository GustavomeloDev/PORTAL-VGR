/**
 * @file prodesp/static/js/prodesp_live_field_validation.js
 * Validação visual em tempo real: pares WAN/Gateway, bloco STATIC 201.60/201.61,
 * trio de Loopbacks (10.254 / 10.252 / 10.253 + sufixo comum), regra VIVO (máscara/gateway).
 */
(function (global) {
  "use strict";

  const STATE_CLASSES = [
    "prodesp-field-state-empty",
    "prodesp-field-state-warn",
    "prodesp-field-state-ok",
  ];

  const LOOPBACK_PREFIX = {
    vivo: "10.254",
    cliente: "10.252",
    bgp: "10.253",
  };

  const LOOPBACK_ROLE_LABEL = {
    vivo: "Loopback Vivo",
    cliente: "Loopback Cliente",
    bgp: "Loopback On BGP",
  };

  function injectCss() {
    if (document.getElementById("prodesp-live-validation-css")) return;
    const style = document.createElement("style");
    style.id = "prodesp-live-validation-css";
    style.textContent = `
      .prodesp-field-state-empty {
        border-color: #dc3545 !important;
        background-color: #fff5f5 !important;
        box-shadow: 0 0 0 0.15rem rgba(220, 53, 69, 0.2);
      }
      .prodesp-field-state-warn {
        border-color: #ffc107 !important;
        background-color: #fffbeb !important;
        box-shadow: 0 0 0 0.15rem rgba(255, 193, 7, 0.25);
      }
      .prodesp-field-state-ok {
        border-color: #198754 !important;
        background-color: #f0fff4 !important;
        box-shadow: 0 0 0 0.15rem rgba(25, 135, 84, 0.2);
      }
      .prodesp-field-live-hint {
        display: block;
        font-size: 0.75rem;
        margin-top: 0.25rem;
        min-height: 1.1rem;
      }
      .prodesp-field-live-hint.is-empty-hint { color: #dc3545; }
      .prodesp-field-live-hint.is-warn-hint { color: #b58100; }
      .prodesp-field-live-hint.is-ok-hint { color: #198754; }
      .prodesp-link-pair-hint.is-invalid-hint { color: #dc3545; font-size: 0.8rem; }
    `;
    document.head.appendChild(style);
  }

  function resolveEl(ref) {
    if (!ref) return null;
    return typeof ref === "string" ? document.getElementById(ref) : ref;
  }

  function stripIp(val) {
    return (val == null ? "" : String(val)).replace(/\s+/g, "");
  }

  /**
   * Limpa colagem Excel/Word (ZWSP, BOM, soft-hyphen, NBSP, aspas de borda) + espacos.
   * Usado em Designador/ID VGR e demais campos prodesp-no-space.
   */
  function sanitizeLinkPastedText(val) {
    let s = val == null ? "" : String(val);
    if (!s) return "";
    s = s.replace(/[\u200B-\u200D\uFEFF\u00AD\u2060\u00A0\u202F\u2007]/g, "");
    s = s.replace(/\s+/g, "");
    for (let i = 0; i < 3; i++) {
      const n = s.replace(/^['"\u2018\u2019\u201c\u201d]+|['"\u2018\u2019\u201c\u201d]+$/g, "");
      if (n === s) break;
      s = n;
    }
    return s;
  }

  function stripAllSpaces(val) {
    return sanitizeLinkPastedText(val);
  }

  /** IPv4 sem máscara CIDR: apenas dígitos e pontos. */
  function sanitizePlainIpv4(val) {
    return stripIp(val).replace(/\//g, "").replace(/[^0-9.]/g, "");
  }

  function insertTextAtCursor(el, text) {
    const start = el.selectionStart != null ? el.selectionStart : el.value.length;
    const end = el.selectionEnd != null ? el.selectionEnd : el.value.length;
    if (typeof el.setRangeText === "function") {
      el.setRangeText(text, start, end, "end");
    } else {
      el.value = el.value.slice(0, start) + text + el.value.slice(end);
    }
    const np = start + text.length;
    if (el.setSelectionRange) el.setSelectionRange(np, np);
  }

  /**
   * Bloqueia espaços (digitar, colar, inserir).
   * @param {HTMLElement} el
   * @param {{ onAfter?: function }} [opts]
   */
  function bindNoWhitespaceInput(el, opts) {
    if (!el || el.nodeName !== "INPUT" && el.nodeName !== "TEXTAREA") return;
    if (el.dataset.prodespNoSpaceBound === "1") return;
    // Atendimentos: loopbacks já têm paste via bindProdespIpNoWhitespace (+ IMask)
    if (el.dataset.prodespIpNoSpaceBound === "1") return;
    el.dataset.prodespNoSpaceBound = "1";
    const onAfter = opts && opts.onAfter;

    function applyCleaned(triggerSyntheticInput) {
      const cleaned = stripAllSpaces(el.value);
      if (cleaned !== el.value) {
        const pos = el.selectionStart;
        const oldLen = el.value.length;
        el.value = cleaned;
        if (pos != null && el.setSelectionRange) {
          const shrink = Math.max(0, oldLen - cleaned.length);
          el.setSelectionRange(Math.max(0, pos - shrink), Math.max(0, pos - shrink));
        }
        triggerSyntheticInput = true;
      }
      if (triggerSyntheticInput) {
        el.dispatchEvent(new Event("input", { bubbles: true }));
      }
      if (onAfter) onAfter(el);
    }

    el.addEventListener("keydown", function (e) {
      if (e.key === " " || e.code === "Space") e.preventDefault();
    });
    el.addEventListener("paste", function (e) {
      e.preventDefault();
      const raw = (e.clipboardData || window.clipboardData).getData("text") || "";
      insertTextAtCursor(el, stripAllSpaces(raw));
      scheduleAfterPaste(function () {
        applyCleaned(true);
      });
    });
    el.addEventListener("input", function () {
      applyCleaned(false);
    });
  }

  /**
   * IP WAN / Gateway: sem espaços e sem máscara (/). Aceita só IPv4 puro.
   */
  function bindPlainIpv4Input(el, opts) {
    if (!el || el.nodeName !== "INPUT") return;
    if (el.dataset.prodespPlainIpBound === "1") return;
    el.dataset.prodespPlainIpBound = "1";
    const onAfter = opts && opts.onAfter;

    function applyCleaned(triggerSyntheticInput) {
      const cleaned = sanitizePlainIpv4(el.value);
      if (cleaned !== el.value) {
        const pos = el.selectionStart;
        const oldLen = el.value.length;
        el.value = cleaned;
        if (pos != null && el.setSelectionRange) {
          const shrink = Math.max(0, oldLen - cleaned.length);
          el.setSelectionRange(Math.max(0, pos - shrink), Math.max(0, pos - shrink));
        }
        triggerSyntheticInput = true;
      }
      if (triggerSyntheticInput) {
        el.dispatchEvent(new Event("input", { bubbles: true }));
      }
      if (onAfter) onAfter(el);
    }

    el.addEventListener("keydown", function (e) {
      if (e.key === " " || e.code === "Space" || e.key === "/") e.preventDefault();
    });
    el.addEventListener("paste", function (e) {
      e.preventDefault();
      const raw = (e.clipboardData || window.clipboardData).getData("text") || "";
      insertTextAtCursor(el, sanitizePlainIpv4(raw));
      scheduleAfterPaste(function () {
        applyCleaned(true);
      });
    });
    el.addEventListener("input", function () {
      applyCleaned(false);
    });
    el.addEventListener("blur", function () {
      const v = sanitizePlainIpv4(el.value);
      if (!v) {
        el.classList.remove("is-invalid");
        return;
      }
      if (!parseIpv4(v)) {
        el.classList.add("is-invalid");
      } else {
        el.classList.remove("is-invalid");
      }
    });
  }

  /** Após colar, outros handlers podem atualizar o valor no mesmo tick (IMask, blueprint). */
  function scheduleAfterPaste(fn) {
    if (typeof queueMicrotask === "function") {
      queueMicrotask(fn);
    } else {
      setTimeout(fn, 0);
    }
  }

  function compactVelocityText(raw) {
    return String(raw == null ? "" : raw)
      .trim()
      .replace(/,/g, ".")
      .replace(/\s+/g, "")
      .toLowerCase();
  }

  function parseGbpsFromCompact(compact) {
    const m = compact.match(/^(\d+(?:\.\d+)?)(?:gbps|gbit\/s|g)$/i);
    if (!m) return null;
    const mbps = Math.round(parseFloat(m[1]) * 1000);
    return mbps > 0 ? mbps : null;
  }

  function parseMbpsFromCompact(compact) {
    const m = compact.match(/^(\d+(?:\.\d+)?)(?:mbps|mb\/s|mb|m)$/i);
    if (!m) return null;
    const mbps = Math.round(parseFloat(m[1]));
    return mbps > 0 ? mbps : null;
  }

  function normalizePlainMbpsInteger(n) {
    if (!Number.isFinite(n) || n <= 0) return 0;
    if (n >= 100000 && n % 1000 === 0) return Math.floor(n / 1000);
    if (n >= 2000 && n % 1000 === 0) return Math.floor(n / 1000);
    return n;
  }

  function parseVelocityToMbps(val) {
    const raw = String(val == null ? "" : val).trim();
    if (!raw) return { value: "", source: "", raw: "" };

    const compact = compactVelocityText(raw);
    const g = parseGbpsFromCompact(compact);
    if (g != null) return { value: String(g), source: "g", raw: raw };

    const m = parseMbpsFromCompact(compact);
    if (m != null) return { value: String(m), source: "m", raw: raw };

    const digits = sanitizeVelocityMbpsDigits(raw);
    if (!digits) return { value: "", source: "", raw: raw };

    const n = parseInt(digits, 10);
    const normalized = normalizePlainMbpsInteger(n);
    if (!normalized) return { value: "", source: "", raw: raw };
    return { value: String(normalized), source: "plain", raw: raw };
  }

  function formatVelocityMbpsMessage(mbps) {
    if (!mbps) return "";
    const n = parseInt(mbps, 10);
    if (n === 1000) return "1 Gbps (1000 Mbps).";
    if (n === 2500) return "2,5 Gbps (2500 Mbps).";
    if (n === 10000) return "10 Gbps (10000 Mbps).";
    return n + " Mbps.";
  }

  /**
   * Normaliza colagem da planilha (10G, 300 Mbps, 155000, 2,5 Gbps…) para Mbps.
   * @returns {{ value: string, adjusted: boolean, original: string, message: string }}
   */
  function normalizeVelocityMbps(val) {
    const raw = String(val == null ? "" : val).trim();
    if (!raw) {
      return { value: "", adjusted: false, original: "", message: "" };
    }
    const parsed = parseVelocityToMbps(raw);
    if (!parsed.value) {
      return { value: "", adjusted: false, original: raw, message: "" };
    }
    const digits = sanitizeVelocityMbpsDigits(raw);
    let adjusted = false;
    if (parsed.source === "g" || parsed.source === "m") {
      adjusted = parsed.value !== digits;
    } else if (digits) {
      adjusted = parsed.value !== digits;
    }
    let message = formatVelocityMbpsMessage(parsed.value);
    if (adjusted) {
      message = "Ajustado para " + message.replace(/\.$/, "") + " (informado: " + raw + ").";
    }
    return {
      value: parsed.value,
      adjusted: adjusted,
      original: raw,
      message: message,
    };
  }

  function ensureVelocityHint(inputEl) {
    if (!inputEl || !inputEl.parentNode) return null;
    let hint = inputEl.parentNode.querySelector("small[data-velocity-hint]");
    if (!hint) {
      hint = document.createElement("small");
      hint.className = "prodesp-field-live-hint";
      hint.setAttribute("data-velocity-hint", "1");
      inputEl.parentNode.appendChild(hint);
    }
    return hint;
  }

  function paintVelocityMbpsField(el, afterNormalize) {
    if (!el) return null;
    const norm = normalizeVelocityMbps(el.value);
    const hint = ensureVelocityHint(el);
    clearFieldStates(el);
    if (!norm.value) {
      setHint(hint, "", "");
      return norm;
    }
    if (norm.adjusted && afterNormalize) {
      el.classList.add("prodesp-field-state-warn");
      setHint(hint, norm.message, "warn");
    } else {
      el.classList.add("prodesp-field-state-ok");
      setHint(hint, norm.message, "ok");
    }
    return norm;
  }

  function applyVelocityMbpsToField(el, afterNormalize) {
    if (!el) return null;
    const norm = normalizeVelocityMbps(el.value);
    if (norm.value !== el.value) {
      setInputValueSilent(el, norm.value);
    }
    return paintVelocityMbpsField(el, afterNormalize);
  }

  function sanitizeVelocityMbpsDigits(val) {
    return String(val == null ? "" : val).replace(/\D/g, "");
  }

  function isAllowedVelocityInputChar(key) {
    if (/^\d$/.test(key)) return true;
    if (key === "," || key === "." || key === " ") return true;
    return /^[gGmMbBpPsS/]$/i.test(key);
  }

  /** Campo Velocidade: aceita colagem da planilha; grava Mbps (dígitos). */
  function bindVelocityMbpsInput(el) {
    if (!el || el.nodeName !== "INPUT" || el.dataset.prodespVelocityBound === "1") return;
    el.dataset.prodespVelocityBound = "1";
    el.setAttribute("autocomplete", "off");

    function onBlur() {
      applyVelocityMbpsToField(el, true);
    }

    el.addEventListener("keydown", function (e) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const allowed = ["Backspace", "Delete", "Tab", "ArrowLeft", "ArrowRight", "Home", "End", "Enter"];
      if (allowed.indexOf(e.key) >= 0) return;
      if (!isAllowedVelocityInputChar(e.key)) e.preventDefault();
    });
    el.addEventListener("paste", function (e) {
      e.preventDefault();
      const raw = (e.clipboardData || window.clipboardData).getData("text") || "";
      insertTextAtCursor(el, raw);
      scheduleAfterPaste(onBlur);
    });
    el.addEventListener("blur", onBlur);
    applyVelocityMbpsToField(el, true);
  }

  function bindAllVelocityMbpsInputs(root) {
    (root || document).querySelectorAll(".prodesp-velocity-mbps-input").forEach(bindVelocityMbpsInput);
  }

  function clearFieldStates(el) {
    if (!el) return;
    STATE_CLASSES.forEach((c) => el.classList.remove(c));
  }

  function isUniqMarked(el) {
    return !!(el && el.getAttribute("data-prodesp-uniq") === "1");
  }

  function paintFormatState(el, stateClass) {
    if (!el || isUniqMarked(el)) return;
    clearFieldStates(el);
    if (stateClass) el.classList.add(stateClass);
  }

  function setHint(hintEl, text, kind) {
    if (!hintEl) return;
    hintEl.textContent = text || "";
    hintEl.classList.remove("is-empty-hint", "is-warn-hint", "is-ok-hint", "is-invalid-hint");
    if (!text) return;
    if (kind === "empty") hintEl.classList.add("is-empty-hint");
    else if (kind === "warn") hintEl.classList.add("is-warn-hint");
    else if (kind === "ok") hintEl.classList.add("is-ok-hint");
    else if (kind === "invalid") hintEl.classList.add("is-invalid-hint");
  }

  function parseIpv4(val) {
    const v = stripIp(val);
    const m = v.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
    if (!m) return null;
    const parts = m.slice(1, 5).map((n) => parseInt(n, 10));
    if (parts.some((n) => n < 0 || n > 255)) return null;
    return { o1: parts[0], o2: parts[1], o3: parts[2], o4: parts[3], raw: v };
  }

  function ipPrefix(parsed) {
    return parsed ? `${parsed.o1}.${parsed.o2}` : "";
  }

  function ipSuffix(parsed) {
    return parsed ? `${parsed.o3}.${parsed.o4}` : "";
  }

  const VIVO_MASK_MPLS = "255.255.255.248";
  const VIVO_MASK_EVEN = "255.255.255.252";
  const VIVO_MASK_ODD = "255.255.255.254";
  const REDUNDANTE_CRITICO_OFFSET = 2;
  /** Sem RC: WAN = GW+1; com RC: WAN = GW+3 (e o inverso). */
  const VIVO_MPLS_GW_WAN_DELTA = 1;
  const VIVO_MPLS_RC_GW_WAN_DELTA = 3;

  function isMplsLinkTipo(tipo) {
    return String(tipo || "").trim().toUpperCase() === "MPLS";
  }

  function isVivoOperadora(val) {
    return String(val || "").trim().toUpperCase() === "VIVO";
  }

  function appliesRedundanteCritico(tipo, operadora) {
    return isMplsLinkTipo(tipo) && isVivoOperadora(operadora);
  }

  function vivoMplsGwWanDelta(redundanteCritico) {
    return redundanteCritico ? VIVO_MPLS_RC_GW_WAN_DELTA : VIVO_MPLS_GW_WAN_DELTA;
  }

  function ipv4FromInt(n) {
    if (n < 0 || n > 0xffffffff) return "";
    return (
      Math.floor(n / 16777216) +
      "." +
      Math.floor((n % 16777216) / 65536) +
      "." +
      Math.floor((n % 65536) / 256) +
      "." +
      (n % 256)
    );
  }

  function ipv4ToInt(ipVal) {
    const parsed = parseIpv4(sanitizePlainIpv4(ipVal));
    if (!parsed) return null;
    return parsed.o1 * 16777216 + parsed.o2 * 65536 + parsed.o3 * 256 + parsed.o4;
  }

  function offsetIpv4Plain(ipVal, delta) {
    const n = ipv4ToInt(ipVal);
    if (n == null) return "";
    return ipv4FromInt(n + Number(delta || 0));
  }

  function computeWanFromRedundanteBase(baseVal, redundanteCritico) {
    const base = sanitizePlainIpv4(baseVal);
    if (!base) return "";
    if (redundanteCritico) {
      return offsetIpv4Plain(base, REDUNDANTE_CRITICO_OFFSET) || base;
    }
    return base;
  }

  /** Deriva WAN a partir do Gateway (MPLS+VIVO): +1 sem RC, +3 com RC. */
  function deriveVivoWanFromGateway(gwVal, redundanteCritico) {
    const gw = sanitizePlainIpv4(gwVal);
    if (!gw) return "";
    return offsetIpv4Plain(gw, vivoMplsGwWanDelta(!!redundanteCritico));
  }

  /** Deriva Gateway a partir do WAN (MPLS+VIVO): −1 sem RC, −3 com RC. */
  function deriveVivoGatewayFromWanMpls(wanVal, redundanteCritico) {
    const wan = sanitizePlainIpv4(wanVal);
    if (!wan) return "";
    return offsetIpv4Plain(wan, -vivoMplsGwWanDelta(!!redundanteCritico));
  }

  function initRedundanteCriticoMplsVivo(opts) {
    const config = opts || {};
    const wanEl = config.wanEl;
    const checkboxEl = config.checkboxEl;
    const wrapperEl = config.wrapperEl;
    const tipoEl = config.tipoEl;
    const operadoraEl = config.operadoraEl;
    if (!wanEl || !checkboxEl) return null;
    if (checkboxEl._prodespRedundanteCriticoController) {
      return checkboxEl._prodespRedundanteCriticoController;
    }

    let lastChecked = !!checkboxEl.checked;

    function currentTipo() {
      if (typeof config.getTipo === "function") return config.getTipo();
      return tipoEl ? tipoEl.value : "";
    }

    function currentOperadora() {
      if (typeof config.getOperadora === "function") return config.getOperadora();
      return operadoraEl ? operadoraEl.value : "";
    }

    function syncVisibility() {
      const show = appliesRedundanteCritico(currentTipo(), currentOperadora());
      if (wrapperEl) wrapperEl.style.display = show ? "" : "none";
      if (!show && checkboxEl.checked) {
        checkboxEl.checked = false;
        const wan = sanitizePlainIpv4(wanEl.value);
        if (wan && lastChecked) {
          wanEl.value = offsetIpv4Plain(wan, -REDUNDANTE_CRITICO_OFFSET) || wan;
        }
        lastChecked = false;
      }
      return show;
    }

    function applyToggleOffset() {
      if (!syncVisibility()) return "";
      const wan = sanitizePlainIpv4(wanEl.value);
      const checked = !!checkboxEl.checked;
      if (checked === lastChecked) return wan;
      lastChecked = checked;
      if (!wan) return "";
      const next = checkboxEl.checked
        ? offsetIpv4Plain(wan, REDUNDANTE_CRITICO_OFFSET)
        : offsetIpv4Plain(wan, -REDUNDANTE_CRITICO_OFFSET);
      if (next) wanEl.value = next;
      if (typeof config.onAfterApply === "function") config.onAfterApply();
      return next || wan;
    }

    function onToggle() {
      applyToggleOffset();
    }

    checkboxEl.addEventListener("change", onToggle);
    if (tipoEl) tipoEl.addEventListener("change", syncVisibility);
    if (operadoraEl) operadoraEl.addEventListener("change", syncVisibility);

    syncVisibility();

    const controller = {
      refresh: function () {
        const visible = syncVisibility();
        // Refresh é usado após preencher dados do banco: o estado atual vira
        // a referência e não deve deslocar o WAN novamente.
        lastChecked = !!checkboxEl.checked;
        return visible;
      },
      isActive: function () {
        return appliesRedundanteCritico(currentTipo(), currentOperadora()) && checkboxEl.checked;
      },
    };
    checkboxEl._prodespRedundanteCriticoController = controller;
    return controller;
  }

  /** VIVO MPLS → /29; STATIC: par → /30; ímpar → /31; gateway conforme delta MPLS (±1 / ±3). */
  function deriveVivoLinkFields(wanVal, linkTipo, redundanteCritico) {
    const parsed = parseIpv4(sanitizePlainIpv4(wanVal));
    if (!parsed) return null;
    const mask = isMplsLinkTipo(linkTipo)
      ? VIVO_MASK_MPLS
      : parsed.o4 % 2 === 0
        ? VIVO_MASK_EVEN
        : VIVO_MASK_ODD;
    const n = ipv4ToInt(wanVal);
    if (n == null || n <= 0) return null;
    const delta = isMplsLinkTipo(linkTipo)
      ? vivoMplsGwWanDelta(!!redundanteCritico)
      : 1;
    const gateway = ipv4FromInt(n - delta);
    if (!gateway) return null;
    return { mask: mask, gateway: gateway, delta: delta };
  }

  function setInputValueSilent(el, value) {
    if (!el) return false;
    const next = value == null ? "" : String(value);
    if (el.value === next) return false;
    el.value = next;
    return true;
  }

  function vivoExpectedMaskMessage(linkTipo, expectedMask) {
    if (isMplsLinkTipo(linkTipo)) {
      return "VIVO + MPLS: máscara esperada 255.255.255.248 (/29).";
    }
    if (expectedMask === VIVO_MASK_EVEN) {
      return "VIVO + STATIC: IP WAN com último octeto par → máscara 255.255.255.252 (/30).";
    }
    return "VIVO + STATIC: IP WAN com último octeto ímpar → máscara 255.255.255.254 (/31).";
  }

  function validateVivoLinkCompliance(wanVal, maskVal, gwVal, operadoraVal, linkTipo, opts) {
    const options = opts || {};
    const label = options.label || "Link";
    if (!isVivoOperadora(operadoraVal)) {
      return {
        active: false,
        valid: true,
        neutral: true,
        maskOk: true,
        gwOk: true,
        maskMessage: "",
        gwMessage: "",
        summaryMessage: "",
      };
    }
    const wan = sanitizePlainIpv4(wanVal);
    if (!wan) {
      return {
        active: true,
        valid: true,
        neutral: true,
        maskOk: true,
        gwOk: true,
        maskMessage: "",
        gwMessage: "",
        summaryMessage: "",
      };
    }
    const wanCheck = validatePlainIpv4Field(wan, label + " — IP WAN");
    if (!wanCheck.valid) {
      return {
        active: true,
        valid: false,
        neutral: false,
        maskOk: true,
        gwOk: true,
        maskMessage: "",
        gwMessage: "",
        summaryMessage: wanCheck.message,
      };
    }
    const rc = !!(
      typeof options.redundanteCritico === "function"
        ? options.redundanteCritico()
        : options.redundanteCritico
    );
    const derived = deriveVivoLinkFields(wan, linkTipo, rc);
    if (!derived) {
      return {
        active: true,
        valid: false,
        neutral: false,
        maskOk: false,
        gwOk: false,
        maskMessage: label + ": IP WAN inválido para regra VIVO.",
        gwMessage: "",
        summaryMessage: label + ": IP WAN inválido para regra VIVO.",
        expectedMask: "",
        expectedGw: "",
      };
    }
    const mask = stripIp(maskVal);
    const gw = sanitizePlainIpv4(gwVal);
    let maskOk = true;
    let gwOk = true;
    let maskMessage = "";
    let gwMessage = "";
    const deltaLabel = "IP WAN − " + derived.delta;

    if (!mask) {
      maskOk = false;
      maskMessage = vivoExpectedMaskMessage(linkTipo, derived.mask);
    } else if (mask !== derived.mask) {
      maskOk = false;
      maskMessage =
        vivoExpectedMaskMessage(linkTipo, derived.mask) + " Valor informado: " + mask + ".";
    } else {
      maskMessage = "Máscara conforme regra VIVO.";
    }

    if (!gw) {
      gwOk = false;
      gwMessage = "VIVO: gateway esperado " + derived.gateway + " (" + deltaLabel + ").";
    } else if (gw !== derived.gateway) {
      gwOk = false;
      gwMessage =
        "VIVO: gateway esperado " +
        derived.gateway +
        " (" +
        deltaLabel +
        "). Valor informado: " +
        gw +
        ".";
    } else {
      gwMessage =
        "Gateway conforme regra VIVO (" +
        deltaLabel +
        (rc && isMplsLinkTipo(linkTipo) ? "; Redundante Crítico" : "") +
        ").";
    }

    const valid = maskOk && gwOk;
    const parts = [];
    if (!maskOk) parts.push(maskMessage);
    if (!gwOk) parts.push(gwMessage);

    return {
      active: true,
      valid: valid,
      neutral: false,
      maskOk: maskOk,
      gwOk: gwOk,
      maskMessage: maskMessage,
      gwMessage: gwMessage,
      summaryMessage: valid ? "" : label + ": " + parts.join(" "),
      expectedMask: derived.mask,
      expectedGw: derived.gateway,
      derived: derived,
    };
  }

  function ensureVivoFieldHint(inputEl, role) {
    if (!inputEl || !inputEl.parentNode) return null;
    const attr = "data-vivo-hint-" + role;
    let hint = inputEl.parentNode.querySelector("small[" + attr + "]");
    if (!hint) {
      hint = document.createElement("small");
      hint.className = "prodesp-field-live-hint";
      hint.setAttribute(attr, "1");
      inputEl.parentNode.appendChild(hint);
    }
    return hint;
  }

  function paintVivoLinkCompliance(wanEl, maskEl, gwEl, operadoraVal, opts) {
    const options = opts || {};
    if (!isVivoOperadora(operadoraVal)) {
      if (maskEl) {
        clearFieldStates(maskEl);
        setHint(ensureVivoFieldHint(maskEl, "mask"), "", "");
      }
      if (gwEl) {
        clearFieldStates(gwEl);
        setHint(ensureVivoFieldHint(gwEl, "gw"), "", "");
      }
      return { active: false, valid: true, neutral: true };
    }

    const result = validateVivoLinkCompliance(
      wanEl ? wanEl.value : "",
      maskEl ? maskEl.value : "",
      gwEl ? gwEl.value : "",
      operadoraVal,
      typeof options.getLinkTipo === "function"
        ? options.getLinkTipo()
        : options.linkTipo || "STATIC",
      {
        label: options.label,
        redundanteCritico:
          (typeof options.redundanteCritico === "function"
            ? options.redundanteCritico()
            : options.redundanteCritico) ||
          (typeof options.skipGatewayWhen === "function" && options.skipGatewayWhen()),
      }
    );

    if (!result.active || result.neutral) {
      if (maskEl) {
        clearFieldStates(maskEl);
        setHint(ensureVivoFieldHint(maskEl, "mask"), "", "");
      }
      if (gwEl) {
        clearFieldStates(gwEl);
        setHint(ensureVivoFieldHint(gwEl, "gw"), "", "");
      }
      return result;
    }

    if (maskEl) {
      if (!isUniqMarked(maskEl)) clearFieldStates(maskEl);
      const maskHint = ensureVivoFieldHint(maskEl, "mask");
      if (result.maskOk && stripIp(maskEl.value)) {
        paintFormatState(maskEl, "prodesp-field-state-ok");
        setHint(maskHint, result.maskMessage, "ok");
      } else if (!result.maskOk) {
        paintFormatState(maskEl, "prodesp-field-state-warn");
        setHint(maskHint, result.maskMessage, "warn");
      }
    }

    if (gwEl) {
      if (!isUniqMarked(gwEl)) clearFieldStates(gwEl);
      const gwHint = ensureVivoFieldHint(gwEl, "gw");
      if (result.gwOk && sanitizePlainIpv4(gwEl.value)) {
        paintFormatState(gwEl, "prodesp-field-state-ok");
        setHint(gwHint, result.gwMessage, "ok");
      } else if (!result.gwOk) {
        paintFormatState(gwEl, "prodesp-field-state-warn");
        setHint(gwHint, result.gwMessage, "warn");
      }
    }

    return result;
  }

  function applyVivoLinkFields(wanEl, maskEl, gwEl, operadoraVal, opts) {
    if (!isVivoOperadora(operadoraVal)) return false;
    const options = opts || {};
    const linkTipo =
      typeof options.getLinkTipo === "function"
        ? options.getLinkTipo()
        : options.linkTipo || "STATIC";
    const rc = !!(
      typeof options.redundanteCritico === "function"
        ? options.redundanteCritico()
        : options.redundanteCritico ||
          (typeof options.skipGatewayWhen === "function" && options.skipGatewayWhen())
    );
    const source = options.source || "wan";
    let changed = false;

    const wanRaw = wanEl ? sanitizePlainIpv4(wanEl.value) : "";
    const gwRaw = gwEl ? sanitizePlainIpv4(gwEl.value) : "";

    // Gateway preenchido primeiro (MPLS): deriva WAN = GW+1 ou GW+3
    if (
      source === "gateway" &&
      isMplsLinkTipo(linkTipo) &&
      gwRaw &&
      gwEl &&
      wanEl
    ) {
      const nextWan = deriveVivoWanFromGateway(gwRaw, rc);
      if (nextWan && setInputValueSilent(wanEl, nextWan)) changed = true;
    }

    const wanAfter = wanEl ? sanitizePlainIpv4(wanEl.value) : "";
    const derived = deriveVivoLinkFields(wanAfter, linkTipo, rc);
    if (!derived) return changed;

    if (maskEl && !options.skipMask) {
      if (setInputValueSilent(maskEl, derived.mask)) changed = true;
    }

    // WAN preenchido (ou após derivar do GW): aplica gateway = WAN−delta
    if (gwEl && !options.skipGateway && source !== "gateway") {
      if (setInputValueSilent(gwEl, derived.gateway)) changed = true;
    } else if (gwEl && source === "gateway" && !gwRaw && wanAfter) {
      if (setInputValueSilent(gwEl, derived.gateway)) changed = true;
    }

    return changed;
  }

  function initVivoLinkAutoFill(wanRef, gwRef, maskRef, operadoraRef, opts) {
    const wanEl = resolveEl(wanRef);
    const gwEl = resolveEl(gwRef);
    const maskEl = resolveEl(maskRef);
    const operadoraEl = resolveEl(operadoraRef);
    if (!wanEl || !gwEl || !maskEl || !operadoraEl) return null;

    const options = opts || {};

    function resolveRc() {
      return !!(
        typeof options.redundanteCritico === "function"
          ? options.redundanteCritico()
          : options.redundanteCritico ||
            (typeof options.skipGatewayWhen === "function" && options.skipGatewayWhen())
      );
    }

    function runVivoLinkRefresh(doApply, source) {
      const optsRun = Object.assign({}, options, {
        source: source || "wan",
        redundanteCritico: resolveRc,
      });
      if (doApply) {
        applyVivoLinkFields(wanEl, maskEl, gwEl, operadoraEl.value, optsRun);
      }
      const painted = paintVivoLinkCompliance(wanEl, maskEl, gwEl, operadoraEl.value, optsRun);
      if (doApply && options.onAfterApply) options.onAfterApply();
      return painted;
    }

    function bindRefresh(doApply, source) {
      return function () {
        return runVivoLinkRefresh(doApply, source);
      };
    }

    ["input", "change", "blur"].forEach(function (evt) {
      wanEl.addEventListener(evt, bindRefresh(true, "wan"));
    });
    ["input", "change", "blur"].forEach(function (evt) {
      operadoraEl.addEventListener(evt, bindRefresh(true, "wan"));
    });
    ["input", "change", "blur"].forEach(function (evt) {
      maskEl.addEventListener(evt, bindRefresh(false, "wan"));
      gwEl.addEventListener(evt, bindRefresh(true, "gateway"));
    });
    if (options.tipoEl) {
      const tipoEl = resolveEl(options.tipoEl);
      if (tipoEl) {
        ["input", "change", "blur"].forEach(function (evt) {
          tipoEl.addEventListener(evt, bindRefresh(true, "wan"));
        });
      }
    }
    wanEl.addEventListener("paste", function () {
      scheduleAfterPaste(bindRefresh(true, "wan"));
    });
    maskEl.addEventListener("paste", function () {
      scheduleAfterPaste(bindRefresh(false, "wan"));
    });
    gwEl.addEventListener("paste", function () {
      scheduleAfterPaste(bindRefresh(true, "gateway"));
    });
    runVivoLinkRefresh(false, "wan");
    return {
      refresh: function (doApply, source) {
        return runVivoLinkRefresh(doApply !== false, source || "wan");
      },
      validate: function () {
        return runVivoLinkRefresh(false, "wan");
      },
      apply: function (source) {
        return runVivoLinkRefresh(true, source || "wan");
      },
      wanEl: wanEl,
      gwEl: gwEl,
      maskEl: maskEl,
      operadoraEl: operadoraEl,
    };
  }

  function validateVivoBlueprintLinks(form) {
    if (!form) return [];
    const errors = [];
    [
      { prefix: "mpls", operadora: "mpls_operadora", linkTipo: "MPLS", label: "Link MPLS" },
      { prefix: "static", operadora: "static_operadora", linkTipo: "STATIC", label: "Link STATIC (SAI-BL)" },
    ].forEach(function (cfg) {
      const operadoraEl = form.querySelector('[name="' + cfg.operadora + '"]');
      const wanEl = form.querySelector('[name="' + cfg.prefix + '_ip_wan"]');
      const maskEl = form.querySelector('[name="' + cfg.prefix + '_ip_mascara"]');
      const gwEl = form.querySelector('[name="' + cfg.prefix + '_ip_gateway"]');
      const redundanteEl =
        cfg.prefix === "mpls" ? form.querySelector("#mpls_redundante_critico") : null;
      const result = paintVivoLinkCompliance(
        wanEl,
        maskEl,
        gwEl,
        operadoraEl && operadoraEl.value,
        {
          linkTipo: cfg.linkTipo,
          label: cfg.label,
          redundanteCritico: !!(redundanteEl && redundanteEl.checked),
        }
      );
      if (result.active && !result.valid && result.summaryMessage) {
        errors.push(result.summaryMessage);
      }
    });
    return errors;
  }

  function applyVivoBlueprintLinks(form) {
    if (!form) return;
    [
      { prefix: "mpls", operadora: "mpls_operadora", linkTipo: "MPLS" },
      { prefix: "static", operadora: "static_operadora", linkTipo: "STATIC" },
    ].forEach(function (cfg) {
      const operadoraEl = form.querySelector('[name="' + cfg.operadora + '"]');
      const redundanteEl =
        cfg.prefix === "mpls" ? form.querySelector("#mpls_redundante_critico") : null;
      const rc =
        cfg.linkTipo === "MPLS" &&
        isVivoOperadora(operadoraEl && operadoraEl.value) &&
        !!(redundanteEl && redundanteEl.checked);
      applyVivoLinkFields(
        form.querySelector('[name="' + cfg.prefix + '_ip_wan"]'),
        form.querySelector('[name="' + cfg.prefix + '_ip_mascara"]'),
        form.querySelector('[name="' + cfg.prefix + '_ip_gateway"]'),
        operadoraEl && operadoraEl.value,
        {
          linkTipo: cfg.linkTipo,
          redundanteCritico: rc,
          source: "wan",
        }
      );
    });
    validateVivoBlueprintLinks(form);
  }

  function validatePlainIpv4Field(val, label) {
    const v = sanitizePlainIpv4(val);
    if (!v) return { valid: true, message: "" };
    if (v.indexOf("/") >= 0) {
      return {
        valid: false,
        message: `${label}: informe apenas o endereço IPv4, sem máscara (ex.: 10.1.1.1).`,
      };
    }
    if (!parseIpv4(v)) {
      return {
        valid: false,
        message: `${label}: endereço IPv4 inválido.`,
      };
    }
    return { valid: true, message: "" };
  }

  function validateLinkPair(wanVal, gwVal, opts) {
    const wan = sanitizePlainIpv4(wanVal);
    const gw = sanitizePlainIpv4(gwVal);
    const label = (opts && opts.label) || "Link";
    if (!wan && !gw) {
      return { valid: true, state: "neutral", message: "" };
    }
    const wanCheck = validatePlainIpv4Field(wan, `${label} — IP WAN`);
    if (!wanCheck.valid) {
      return { valid: false, state: "invalid", message: wanCheck.message };
    }
    const gwCheck = validatePlainIpv4Field(gw, `${label} — Gateway`);
    if (!gwCheck.valid) {
      return { valid: false, state: "invalid", message: gwCheck.message };
    }
    if (wan && gw && wan === gw) {
      return {
        valid: false,
        state: "invalid",
        message: `${label}: IP WAN e Gateway não podem ser iguais.`,
      };
    }
    if (opts && opts.checkStaticBlock && wan && (wan.indexOf("201.60.") === 0 || wan.indexOf("201.61.") === 0)) {
      return {
        valid: false,
        state: "invalid",
        message:
          `${label}: IP WAN (${wan}) pertence ao bloco 201.60/201.61. ` +
          "Solicite a manobra de IP antes de gerar o Blueprint.",
      };
    }
    if (wan && gw) {
      return { valid: true, state: "ok", message: "IP WAN e Gateway válidos." };
    }
    return { valid: true, state: "neutral", message: "" };
  }

  function paintLinkPair(wanEl, gwEl, result, pairHintEl) {
    if (!isUniqMarked(wanEl)) clearFieldStates(wanEl);
    if (!isUniqMarked(gwEl)) clearFieldStates(gwEl);
    if (result.state === "invalid") {
      paintFormatState(wanEl, "prodesp-field-state-empty");
      paintFormatState(gwEl, "prodesp-field-state-empty");
      setHint(pairHintEl, result.message, "invalid");
    } else if (result.state === "ok") {
      paintFormatState(wanEl, "prodesp-field-state-ok");
      paintFormatState(gwEl, "prodesp-field-state-ok");
      setHint(pairHintEl, result.message, "ok");
    } else {
      setHint(pairHintEl, "", "");
    }
  }

  function initLinkPair(wanRef, gwRef, opts) {
    const wanEl = resolveEl(wanRef);
    const gwEl = resolveEl(gwRef);
    if (!wanEl || !gwEl) return null;

    const options = opts || {};
    const pairHintEl = resolveEl(options.hintRef);

    function resolveOpts() {
      return typeof options.getOpts === "function" ? options.getOpts() : options;
    }

    const refresh = function () {
      const result = validateLinkPair(wanEl.value, gwEl.value, resolveOpts());
      paintLinkPair(wanEl, gwEl, result, pairHintEl);
      return result;
    };

    ["input", "change"].forEach((evt) => {
      wanEl.addEventListener(evt, refresh);
      gwEl.addEventListener(evt, refresh);
    });
    [wanEl, gwEl].forEach((el) => {
      el.addEventListener("paste", function () {
        scheduleAfterPaste(refresh);
      });
    });
    refresh();
    return { refresh, wanEl, gwEl };
  }

  function validateLoopbackTriplet(fieldsByRole, opts) {
    const options = opts || {};
    const emptyHint = options.emptyHint || "Campo obrigatório.";
    const roles = ["vivo", "cliente", "bgp"];
    const parsed = {};
    const states = {};

    roles.forEach((role) => {
      const el = fieldsByRole[role];
      const raw = el ? stripIp(el.value) : "";
      parsed[role] = raw ? parseIpv4(raw) : null;
      states[role] = { empty: !raw, el };
    });

    const filledSuffixes = roles
      .filter((r) => parsed[r])
      .map((r) => ipSuffix(parsed[r]));
    const consensus =
      filledSuffixes.length > 0 && filledSuffixes.every((s) => s === filledSuffixes[0])
        ? filledSuffixes[0]
        : filledSuffixes.length === 1
          ? filledSuffixes[0]
          : null;

    const allFilled = roles.every((r) => !states[r].empty);
    const allValid = roles.every((r) => {
      const p = parsed[r];
      return p && ipPrefix(p) === LOOPBACK_PREFIX[r];
    });
    const suffixAligned =
      consensus &&
      roles.every((r) => !parsed[r] || ipSuffix(parsed[r]) === consensus);

    const allOk = allFilled && allValid && suffixAligned;

    roles.forEach((role) => {
      const el = states[role].el;
      const hintEl = fieldsByRole[`${role}Hint`];
      clearFieldStates(el);
      if (!el) return;

      if (states[role].empty) {
        el.classList.add("prodesp-field-state-empty");
        setHint(hintEl, emptyHint, "empty");
        return;
      }

      const p = parsed[role];
      const expectedPrefix = LOOPBACK_PREFIX[role];
      const wrongPrefix = !p || ipPrefix(p) !== expectedPrefix;
      const wrongSuffix = consensus && p && ipSuffix(p) !== consensus;

      if (allOk) {
        el.classList.add("prodesp-field-state-ok");
        setHint(hintEl, "Alinhado com os demais loopbacks.", "ok");
      } else if (wrongPrefix || wrongSuffix || !p) {
        el.classList.add("prodesp-field-state-warn");
        let msg = "";
        if (!p) {
          msg = "Informe um IPv4 completo (ex.: 10.254.8.31).";
        } else if (wrongPrefix) {
          msg = `${LOOPBACK_ROLE_LABEL[role]}: use prefixo ${expectedPrefix}.x.x`;
        } else if (wrongSuffix) {
          msg = "Os dois últimos octetos devem ser iguais nos três campos.";
        }
        setHint(hintEl, msg, "warn");
      }
    });

    return { valid: allOk, consensus };
  }

  /**
   * Preenche loopbacks vazios a partir do primeiro campo já preenchido (ex.: carga do banco).
   */
  function syncLoopbacksFromPrefilled(fieldsByRole) {
    const roles = ["vivo", "cliente", "bgp"];
    let suffix = "";
    roles.forEach((role) => {
      if (suffix) return;
      const el = fieldsByRole[role];
      const parsed = el && parseIpv4(stripIp(el.value));
      if (parsed) suffix = ipSuffix(parsed);
    });
    if (!suffix) return false;
    let changed = false;
    roles.forEach((role) => {
      const target = fieldsByRole[role];
      if (!target || stripIp(target.value)) return;
      if (setInputValueSilent(target, `${LOOPBACK_PREFIX[role]}.${suffix}`)) {
        changed = true;
      }
    });
    return changed;
  }

  /** Após carregar dados (busca ID, modal edit/create): loopbacks, links VIVO e validação visual. */
  function refreshFormAfterDataLoad(config) {
    const cfg = config || {};
    if (cfg.loopbacks) {
      syncLoopbacksFromPrefilled(cfg.loopbacks);
    }
    if (cfg.loopbackController && cfg.loopbackController.refresh) {
      cfg.loopbackController.refresh();
    }
    if (cfg.form) {
      validateVivoBlueprintLinks(cfg.form);
      bindAllVelocityMbpsInputs(cfg.form);
      cfg.form.querySelectorAll(".prodesp-velocity-mbps-input").forEach(function (el) {
        applyVelocityMbpsToField(el, true);
      });
    }
    if (cfg.linkController) {
      if (cfg.linkController.vivo && cfg.linkController.vivo.validate) {
        cfg.linkController.vivo.validate();
      } else if (cfg.linkController.vivo && cfg.linkController.vivo.refresh) {
        cfg.linkController.vivo.refresh(false);
      }
      if (cfg.linkController.refresh) cfg.linkController.refresh();
    }
    /* Admin inventário / fillForm sem eventos de input. */
    if (cfg.serialEl) {
      paintSerialFortinetField(cfg.serialEl, cfg.serialHintEl || null, cfg.serialOpts || {});
    } else if (cfg.serialController && cfg.serialController.refresh) {
      cfg.serialController.refresh();
    }
    if (cfg.adminLinkController) {
      /* refresh = paintLocal + unicidade remota (igual digitar no campo). */
      if (cfg.adminLinkController.refresh) cfg.adminLinkController.refresh();
      else if (cfg.adminLinkController.paintLocal) cfg.adminLinkController.paintLocal();
    }
    if (cfg.vivoLinkController) {
      if (cfg.vivoLinkController.validate) cfg.vivoLinkController.validate();
      else if (cfg.vivoLinkController.refresh) cfg.vivoLinkController.refresh(false);
    }
    if (cfg.velocityEl && typeof applyVelocityMbpsToField === "function") {
      applyVelocityMbpsToField(cfg.velocityEl, true);
    }
    if (Array.isArray(cfg.linkPairRefresh)) {
      cfg.linkPairRefresh.forEach(function (fn) {
        if (fn) fn();
      });
    }
  }

  function initLoopbackTriplet(config) {
    const cfg = config || {};
    const fields = {
      vivo: resolveEl(cfg.vivo),
      cliente: resolveEl(cfg.cliente),
      bgp: resolveEl(cfg.bgp),
      vivoHint: resolveEl(cfg.vivoHint),
      clienteHint: resolveEl(cfg.clienteHint),
      bgpHint: resolveEl(cfg.bgpHint),
    };

    if (!fields.vivo || !fields.cliente || !fields.bgp) return null;

    ["vivo", "cliente", "bgp"].forEach((role) => {
      bindNoWhitespaceInput(fields[role]);
    });

    const emptyHint = cfg.emptyHint || "Campo obrigatório.";
    let syncLock = false;

    function ensureHintAfter(inputEl, role) {
      const key = `${role}Hint`;
      if (fields[key]) return fields[key];
      const hint = document.createElement("small");
      hint.className = "prodesp-field-live-hint";
      hint.setAttribute("data-loopback-hint", role);
      inputEl.parentNode.appendChild(hint);
      fields[key] = hint;
      return hint;
    }

    ["vivo", "cliente", "bgp"].forEach((role) => ensureHintAfter(fields[role], role));

    const refresh = function () {
      return validateLoopbackTriplet(fields, { emptyHint: emptyHint });
    };

    const syncFrom = function (sourceRole) {
      if (syncLock) return;
      const sourceEl = fields[sourceRole];
      const parsed = parseIpv4(sourceEl.value);
      if (!parsed) {
        refresh();
        return;
      }
      const suffix = ipSuffix(parsed);
      syncLock = true;
      ["vivo", "cliente", "bgp"].forEach((role) => {
        if (role === sourceRole) return;
        const target = fields[role];
        if (!target || document.activeElement === target) return;
        const next = `${LOOPBACK_PREFIX[role]}.${suffix}`;
        setInputValueSilent(target, next);
      });
      syncLock = false;
      refresh();
    };

    ["vivo", "cliente", "bgp"].forEach((role) => {
      const el = fields[role];
      el.addEventListener("input", function () {
        syncFrom(role);
      });
      el.addEventListener("paste", function () {
        scheduleAfterPaste(function () {
          syncFrom(role);
        });
      });
      el.addEventListener("change", refresh);
      el.addEventListener("blur", refresh);
    });

    syncLoopbacksFromPrefilled(fields);
    refresh();
    return { refresh, fields, syncPrefilled: function () {
      syncLoopbacksFromPrefilled(fields);
      return refresh();
    } };
  }

  function blueprintLinkSectionHasContent(form, prefix) {
    const keys = [
      "operadora",
      "designador",
      "id_vgr",
      "ip_wan",
      "ip_gateway",
      "ip_mascara",
      "velocidade",
      "vlan",
    ];
    return keys.some(function (k) {
      const el = form.querySelector('[name="' + prefix + "_" + k + '"]');
      return el && String(el.value || "").trim();
    });
  }

  /** Texto obrigatório (Hostname / Acrônimo) — pinta borda + hint. */
  function paintRequiredTextField(el, opts) {
    injectCss();
    if (!el) return { valid: false, message: (opts && opts.emptyMessage) || "Campo obrigatório." };
    const label = (opts && opts.label) || "Campo";
    const emptyMessage = (opts && opts.emptyMessage) || (label + " é obrigatório.");
    const hint = ensureLiveHint(el);
    const val = String(el.value || "").trim();
    el.classList.remove("is-invalid");
    if (!val) {
      paintFormatState(el, "prodesp-field-state-empty");
      el.classList.add("is-invalid");
      setHint(hint, emptyMessage, "empty");
      return { valid: false, message: emptyMessage };
    }
    paintFormatState(el, "prodesp-field-state-ok");
    setHint(hint, "", "");
    return { valid: true, message: "" };
  }

  function validateCidrIpValue(raw, opts) {
    const required = !!(opts && opts.required);
    const label = (opts && opts.label) || "IP";
    const v = stripIp(raw || "");
    if (!v) {
      if (required) {
        return { valid: false, state: "empty", message: label + " é obrigatório." };
      }
      return { valid: true, state: "empty", message: "" };
    }
    if (v.indexOf("/") < 0) {
      return {
        valid: false,
        state: "invalid",
        message: label + " deve conter a máscara CIDR (ex.: /24).",
      };
    }
    const slash = v.indexOf("/");
    const ipPart = v.slice(0, slash);
    const prefPart = v.slice(slash + 1);
    if (!parseIpv4(ipPart)) {
      return { valid: false, state: "invalid", message: label + ": IP inválido." };
    }
    if (!/^\d{1,2}$/.test(prefPart)) {
      return {
        valid: false,
        state: "invalid",
        message: label + ": prefixo CIDR inválido (0–32).",
      };
    }
    const n = parseInt(prefPart, 10);
    if (n < 0 || n > 32) {
      return {
        valid: false,
        state: "invalid",
        message: label + ": prefixo CIDR inválido (0–32).",
      };
    }
    return { valid: true, state: "ok", message: "" };
  }

  function paintCidrIpField(el, opts) {
    injectCss();
    if (!el) return { valid: true, message: "" };
    const check = validateCidrIpValue(el.value, opts || {});
    const hint = ensureLiveHint(el);
    el.classList.remove("is-invalid");
    if (!check.valid) {
      paintFormatState(el, "prodesp-field-state-empty");
      el.classList.add("is-invalid");
      setHint(hint, check.message, check.state === "empty" ? "empty" : "invalid");
      return check;
    }
    if (check.state === "ok") {
      paintFormatState(el, "prodesp-field-state-ok");
      setHint(hint, "", "");
    } else {
      clearFieldStates(el);
      setHint(hint, "", "");
    }
    return check;
  }

  /** Latitude/Longitude: opcional; se preenchido, deve ser decimal (ponto ou vírgula). */
  const COORD_MAX_CHARS = 13;

  function validateCoordinateValue(raw, opts) {
    const label = (opts && opts.label) || "Latitude/Longitude";
    let s = String(raw == null ? "" : raw).trim();
    if (!s) return { valid: true, state: "empty", message: "", value: "" };
    if (s.length > COORD_MAX_CHARS) {
      return {
        valid: false,
        state: "invalid",
        message:
          "O campo «" +
          label +
          "» aceita no máximo " +
          COORD_MAX_CHARS +
          " caracteres (você informou " +
          s.length +
          ").",
        value: s,
      };
    }
    s = s.replace(/\s+/g, "").replace(",", ".");
    if (!/^-?\d+(\.\d+)?$/.test(s)) {
      return {
        valid: false,
        state: "invalid",
        message:
          "O campo «" +
          label +
          "» deve ser um número decimal válido (use ponto ou vírgula como separador decimal).",
        value: s,
      };
    }
    const n = Number(s);
    if (!isFinite(n)) {
      return {
        valid: false,
        state: "invalid",
        message:
          "O campo «" +
          label +
          "» deve ser um número decimal válido (use ponto ou vírgula como separador decimal).",
        value: s,
      };
    }
    return { valid: true, state: "ok", message: "", value: s };
  }

  function paintCoordinateField(el, opts) {
    injectCss();
    if (!el) return { valid: true, message: "" };
    const label = (opts && opts.label) || "Latitude/Longitude";
    const check = validateCoordinateValue(el.value, { label: label });
    const hint = ensureLiveHint(el);
    el.classList.remove("is-invalid");
    if (!check.valid) {
      paintFormatState(el, "prodesp-field-state-empty");
      el.classList.add("is-invalid");
      setHint(hint, check.message, "invalid");
      return check;
    }
    if (check.state === "ok") {
      paintFormatState(el, "prodesp-field-state-ok");
      setHint(hint, "", "");
    } else {
      clearFieldStates(el);
      setHint(hint, "", "");
    }
    return check;
  }

  /** Velocidade obrigatória quando a seção do link tem conteúdo. */
  function paintVelocityRequiredField(el, opts) {
    injectCss();
    if (!el) return { valid: true, message: "", value: "" };
    const label = (opts && opts.label) || "Link";
    const required = !!(opts && opts.required);
    const hint = ensureVelocityHint(el);
    const norm = normalizeVelocityMbps(el.value);
    el.classList.remove("is-invalid");
    if (!norm.value) {
      if (required) {
        const msg = label + ": Velocidade é obrigatória";
        paintFormatState(el, "prodesp-field-state-empty");
        el.classList.add("is-invalid");
        setHint(hint, msg, "empty");
        return { valid: false, message: msg, value: "" };
      }
      clearFieldStates(el);
      setHint(hint, "", "");
      return { valid: true, message: "", value: "" };
    }
    // paintVelocityMbpsField retorna meta de normalização (sem `valid`);
    // o caller em collectBlueprintLinkErrors usa `if (!vel.valid)` — precisa ser boolean.
    const painted = paintVelocityMbpsField(el, !!(opts && opts.afterNormalize));
    return {
      valid: true,
      message: (painted && painted.message) || "",
      value: norm.value,
    };
  }

  function lanIpFilled(val) {
    return !!stripIp(val || "");
  }

  /**
   * Pendências de unidade alinhadas a validar_dados_blueprint (hostname, acrônimo, CIDR, cascade LAN).
   * Também pinta os campos na página.
   */
  function collectAndPaintBlueprintUnitErrors(form) {
    const errors = [];
    if (!form) return errors;

    const hostEl = form.querySelector('[name="hostname_unidades"]');
    const host = paintRequiredTextField(hostEl, {
      label: "Hostname",
      emptyMessage: "Hostname da Unidade é obrigatório.",
    });
    if (!host.valid) errors.push("Hostname da Unidade");

    const acrEl = form.querySelector('[name="acronimo_unidades"]');
    const acr = paintRequiredTextField(acrEl, {
      label: "Sigla Secretaria (Acrônimo)",
      emptyMessage: "Sigla Secretaria (Acrônimo) é obrigatória.",
    });
    if (!acr.valid) errors.push("Sigla Secretaria (Acrônimo)");

    const lan1El = form.querySelector('[name="ip_lan_01_unidades"]');
    const lan1 = paintCidrIpField(lan1El, { required: true, label: "IP LAN 1" });
    if (!lan1.valid) {
      errors.push(
        lan1.state === "empty"
          ? "IP LAN 1"
          : "IP LAN 1 (Deve conter a máscara CIDR, ex: /24)"
      );
    }

    const lanExtra = [
      { name: "mv_ip_lan_sec_unidades", label: "IP LAN SEC", required: false },
      { name: "mv_ip_lan_ter_unidades", label: "IP LAN TER", required: false },
      { name: "mv_ip_lan_qua_unidades", label: "IP LAN QUA", required: false },
      { name: "mv_ip_wifi_guest_unidades", label: "IP WiFi Guest", required: false },
    ];
    lanExtra.forEach(function (cfg) {
      const el = form.querySelector('[name="' + cfg.name + '"]');
      if (!el) return;
      const check = paintCidrIpField(el, { required: cfg.required, label: cfg.label });
      if (!check.valid) {
        errors.push(cfg.label + " (Deve conter a máscara CIDR, ex: /24)");
      }
    });

    const sec = lanIpFilled(
      (form.querySelector('[name="mv_ip_lan_sec_unidades"]') || {}).value
    );
    const ter = lanIpFilled(
      (form.querySelector('[name="mv_ip_lan_ter_unidades"]') || {}).value
    );
    const qua = lanIpFilled(
      (form.querySelector('[name="mv_ip_lan_qua_unidades"]') || {}).value
    );
    if (ter && !sec) {
      errors.push("IP LAN TER exige IP LAN SEC preenchido");
      const secEl = form.querySelector('[name="mv_ip_lan_sec_unidades"]');
      if (secEl) {
        paintRequiredTextField(secEl, {
          label: "IP LAN SEC",
          emptyMessage: "IP LAN TER exige IP LAN SEC preenchido.",
        });
      }
    }
    if (qua && !sec) {
      errors.push("IP LAN QUA exige IP LAN SEC preenchido");
      const secEl = form.querySelector('[name="mv_ip_lan_sec_unidades"]');
      if (secEl) {
        paintRequiredTextField(secEl, {
          label: "IP LAN SEC",
          emptyMessage: "IP LAN QUA exige IP LAN SEC preenchido.",
        });
      }
    }
    if (qua && !ter) {
      errors.push("IP LAN QUA exige IP LAN TER preenchido");
      const terEl = form.querySelector('[name="mv_ip_lan_ter_unidades"]');
      if (terEl) {
        paintRequiredTextField(terEl, {
          label: "IP LAN TER",
          emptyMessage: "IP LAN QUA exige IP LAN TER preenchido.",
        });
      }
    }

    const serialEl = form.querySelector('[name="serial_equipamentos"]');
    if (serialEl) {
      const serialCheck = paintSerialFortinetField(serialEl, null, {
        obrigatorio: true,
        exigePadrao: false,
      });
      if (!serialCheck.valid) {
        errors.push("Serial Number do Equipamento");
        serialEl.classList.add("is-invalid");
      } else {
        serialEl.classList.remove("is-invalid");
      }
    }

    [
      { name: "latitude_unidades", label: "Latitude" },
      { name: "longitude_unidades", label: "Longitude" },
    ].forEach(function (cfg) {
      const el = form.querySelector('[name="' + cfg.name + '"]');
      if (!el) return;
      const check = paintCoordinateField(el, { label: cfg.label });
      if (!check.valid) errors.push(check.message || cfg.label);
    });

    return errors;
  }

  function paintBlueprintLinkPresenceField(el, message) {
    if (!el) return;
    injectCss();
    const hint = ensureLiveHint(el);
    el.setAttribute("data-prodesp-presence", "1");
    paintFormatState(el, "prodesp-field-state-empty");
    el.classList.add("is-invalid");
    setHint(hint, message, "empty");
  }

  /**
   * Remove marca de «obrigatório / presença» (borda vermelha + hint).
   * Preserva marca de unicidade (data-prodesp-uniq).
   */
  function clearBlueprintLinkPresenceField(el) {
    if (!el) return;
    if (isUniqMarked(el)) return;
    const wasPresence = el.getAttribute("data-prodesp-presence") === "1";
    el.removeAttribute("data-prodesp-presence");
    el.classList.remove("is-invalid");
    // Sempre limpar estado empty de presença; formato/VIVO reaplicam o verde se preciso.
    if (wasPresence || el.classList.contains("prodesp-field-state-empty")) {
      clearFieldStates(el);
      const hint = ensureLiveHint(el);
      if (hint) setHint(hint, "", "");
    }
  }

  function paintBlueprintLinkIdentifierOk(desOrIdEl, kind, operadoraVal, rawValue) {
    if (!desOrIdEl) return;
    clearBlueprintLinkPresenceField(desOrIdEl);
    paintLinkFormatField(desOrIdEl, kind, operadoraVal, sanitizeLinkPastedText(rawValue));
  }

  function collectBlueprintLinkErrors(form) {
    const errors = validateVivoBlueprintLinks(form);
    [
      { prefix: "mpls", label: "Link MPLS", staticBlock: false },
      { prefix: "static", label: "Link STATIC (SAI-BL)", staticBlock: true },
    ].forEach(function (cfg) {
      const hasContent = blueprintLinkSectionHasContent(form, cfg.prefix);
      const opEl = form.querySelector('[name="' + cfg.prefix + '_operadora"]');
      const desEl = form.querySelector('[name="' + cfg.prefix + '_designador"]');
      const maskEl = form.querySelector('[name="' + cfg.prefix + '_ip_mascara"]');
      const velEl = form.querySelector('[name="' + cfg.prefix + '_velocidade"]');
      const idVgrEl = form.querySelector('[name="' + cfg.prefix + '_id_vgr"]');
      const wanEl = form.querySelector('[name="' + cfg.prefix + '_ip_wan"]');
      const gwEl = form.querySelector('[name="' + cfg.prefix + '_ip_gateway"]');

      if (hasContent) {
        if (!opEl || !String(opEl.value || "").trim()) {
          errors.push(cfg.label + ": Operadora é obrigatória");
          paintBlueprintLinkPresenceField(opEl, cfg.label + ": Operadora é obrigatória.");
        } else if (opEl) {
          clearBlueprintLinkPresenceField(opEl);
        }
        if (!desEl || !String(desEl.value || "").trim()) {
          errors.push(cfg.label + ": Designador é obrigatório");
          paintBlueprintLinkPresenceField(desEl, cfg.label + ": Designador (LP) é obrigatório.");
        } else if (desEl) {
          paintBlueprintLinkIdentifierOk(desEl, "designador", opEl && opEl.value, desEl.value);
        }
        if (!maskEl || !String(maskEl.value || "").trim()) {
          errors.push(cfg.label + ": IP Máscara");
          paintBlueprintLinkPresenceField(maskEl, cfg.label + ": IP Máscara é obrigatória.");
        } else if (maskEl) {
          clearBlueprintLinkPresenceField(maskEl);
        }
        const vel = paintVelocityRequiredField(velEl, {
          label: cfg.label,
          required: true,
        });
        if (!vel.valid) errors.push(cfg.label + ": Velocidade");
        if (isVivoOperadora(opEl && opEl.value)) {
          if (!idVgrEl || !String(idVgrEl.value || "").trim()) {
            errors.push(cfg.label + ": ID VGR (Obrigatório para VIVO)");
            paintBlueprintLinkPresenceField(idVgrEl, cfg.label + ": ID VGR obrigatório para VIVO.");
          } else {
            paintBlueprintLinkIdentifierOk(idVgrEl, "id_vgr", opEl.value, idVgrEl.value);
          }
        } else if (idVgrEl) {
          if (String(idVgrEl.value || "").trim()) {
            paintBlueprintLinkIdentifierOk(idVgrEl, "id_vgr", opEl && opEl.value, idVgrEl.value);
          } else {
            clearBlueprintLinkPresenceField(idVgrEl);
          }
        }
        const wanVal = sanitizePlainIpv4(wanEl && wanEl.value);
        const gwVal = sanitizePlainIpv4(gwEl && gwEl.value);
        if (!wanVal) {
          errors.push(cfg.label + ": IP WAN");
          paintBlueprintLinkPresenceField(wanEl, cfg.label + ": IP WAN é obrigatório.");
        } else if (wanEl) {
          clearBlueprintLinkPresenceField(wanEl);
        }
        if (!gwVal) {
          errors.push(cfg.label + ": IP Gateway");
          paintBlueprintLinkPresenceField(gwEl, cfg.label + ": IP Gateway é obrigatório.");
        } else if (gwEl) {
          clearBlueprintLinkPresenceField(gwEl);
        }
      } else if (velEl) {
        paintVelocityRequiredField(velEl, { label: cfg.label, required: false });
      }

      const result = validateLinkPair(wanEl && wanEl.value, gwEl && gwEl.value, {
        label: cfg.label,
        checkStaticBlock: cfg.staticBlock,
      });
      if (!result.valid) {
        errors.push(result.message);
        if (wanEl && /IP WAN/i.test(result.message)) {
          paintBlueprintLinkPresenceField(wanEl, result.message);
        }
        if (gwEl && /Gateway/i.test(result.message)) {
          paintBlueprintLinkPresenceField(gwEl, result.message);
        }
        if (wanEl && gwEl && /iguais/i.test(result.message)) {
          paintBlueprintLinkPresenceField(wanEl, result.message);
          paintBlueprintLinkPresenceField(gwEl, result.message);
        }
        if (wanEl && /201\.60|201\.61/i.test(result.message)) {
          paintBlueprintLinkPresenceField(wanEl, result.message);
        }
      }
    });

    const mplsHas = blueprintLinkSectionHasContent(form, "mpls");
    const staticHas = blueprintLinkSectionHasContent(form, "static");
    if (!mplsHas && !staticHas) {
      errors.push("Pelo menos um link (MPLS ou STATIC) deve estar cadastrado");
    }

    const localUniq = detectLocalBlueprintUniqueness(form);
    localUniq.errors.forEach(function (msg) {
      if (errors.indexOf(msg) < 0) errors.push(msg);
    });
    return errors;
  }

  /**
   * Valida + pinta unidade/links/loopbacks (espelha pendências do modal/server).
   * @returns {{ valid: boolean, errors: string[] }}
   */
  function validateBlueprintForm(formRef) {
    const form = resolveEl(formRef) || document.getElementById("blueprint-form");
    if (!form) return { valid: true, errors: [] };
    injectCss();
    const unitErrors = collectAndPaintBlueprintUnitErrors(form);
    const linkErrors = collectBlueprintLinkErrors(form);
    const loopback = form._prodespLoopbackCtrl;
    let loopResult = { valid: true };
    if (loopback && typeof loopback.refresh === "function") {
      loopResult = loopback.refresh() || { valid: true };
    } else {
      const lb = initLoopbackTriplet({
        vivo: form.querySelector('[name="loopback_vivo_unidades"]'),
        cliente: form.querySelector('[name="loopback_cliente_unidades"]'),
        bgp: form.querySelector('[name="loopback_on_bgp_unidades"]'),
        emptyHint: "Campo vazio — obrigatório para Blueprint.",
      });
      if (lb && lb.refresh) loopResult = lb.refresh() || { valid: true };
      form._prodespLoopbackCtrl = lb;
    }
    const allErrors = unitErrors.concat(linkErrors);
    if (!loopResult.valid) {
      allErrors.push(
        "Loopbacks: preencha os três campos com prefixos 10.254 / 10.252 / 10.253 e os mesmos dois últimos octetos."
      );
    }
    showBlueprintBanner(form, allErrors);
    if (allErrors.length) {
      const firstInvalid = form.querySelector(".is-invalid, .prodesp-field-state-empty");
      if (firstInvalid && typeof firstInvalid.focus === "function") {
        try {
          firstInvalid.focus({ preventScroll: true });
        } catch (_e) {
          firstInvalid.focus();
        }
      }
    }
    return { valid: !allErrors.length, errors: allErrors };
  }

  /** Mapeia mensagens do server/modal → name dos inputs para pintar na página. */
  function mapBlueprintPendenciasToMarks(errors) {
    const marks = {};
    (errors || []).forEach(function (raw) {
      const e = String(raw || "");
      if (/Hostname/i.test(e)) marks.hostname_unidades = e;
      if (/Acr[oô]nimo|Sigla Secretaria/i.test(e)) marks.acronimo_unidades = e;
      if (/IP LAN 1/i.test(e)) marks.ip_lan_01_unidades = e;
      if (/Serial/i.test(e)) marks.serial_equipamentos = e;
      if (/Latitude/i.test(e)) marks.latitude_unidades = e;
      if (/Longitude/i.test(e)) marks.longitude_unidades = e;
      if (/IP LAN SEC|LAN TER exige IP LAN SEC|LAN QUA exige IP LAN SEC/i.test(e)) {
        marks.mv_ip_lan_sec_unidades = e;
      }
      if (/IP LAN TER|LAN QUA exige IP LAN TER/i.test(e)) marks.mv_ip_lan_ter_unidades = e;
      if (/IP LAN QUA/i.test(e) && !/exige IP LAN/i.test(e)) marks.mv_ip_lan_qua_unidades = e;
      if (/WiFi Guest|wifi guest/i.test(e)) marks.mv_ip_wifi_guest_unidades = e;
      if (/Loopback Vivo/i.test(e)) marks.loopback_vivo_unidades = e;
      if (/Loopback Cliente/i.test(e)) marks.loopback_cliente_unidades = e;
      if (/Loopback On BGP|On BGP/i.test(e)) marks.loopback_on_bgp_unidades = e;
      if (/MPLS.*Operadora|Link MPLS: Operadora/i.test(e)) marks.mpls_operadora = e;
      if (/MPLS.*Designador|Link MPLS: Designador/i.test(e)) marks.mpls_designador = e;
      if (/MPLS.*IP WAN|Link MPLS: IP WAN/i.test(e)) marks.mpls_ip_wan = e;
      if (/MPLS.*[Gg]ateway|Link MPLS: IP Gateway/i.test(e)) marks.mpls_ip_gateway = e;
      if (/MPLS.*[Mm][áa]scara|Link MPLS: IP Máscara/i.test(e)) marks.mpls_ip_mascara = e;
      if (/MPLS.*Velocidade|Link MPLS: Velocidade/i.test(e)) marks.mpls_velocidade = e;
      if (/MPLS.*ID VGR|Link MPLS: ID VGR/i.test(e)) marks.mpls_id_vgr = e;
      if (/STATIC.*Operadora|Link STATIC: Operadora/i.test(e)) marks.static_operadora = e;
      if (/STATIC.*Designador|Link STATIC: Designador/i.test(e)) marks.static_designador = e;
      if (/STATIC.*IP WAN|Link STATIC: IP WAN/i.test(e)) marks.static_ip_wan = e;
      if (/STATIC.*[Gg]ateway|Link STATIC: IP Gateway/i.test(e)) marks.static_ip_gateway = e;
      if (/STATIC.*[Mm][áa]scara|Link STATIC: IP Máscara/i.test(e)) marks.static_ip_mascara = e;
      if (/STATIC.*Velocidade|Link STATIC: Velocidade/i.test(e)) marks.static_velocidade = e;
      if (/STATIC.*ID VGR|Link STATIC: ID VGR/i.test(e)) marks.static_id_vgr = e;
    });
    return marks;
  }

  function paintBlueprintServerPendencias(formRef, errors) {
    const form = resolveEl(formRef) || document.getElementById("blueprint-form");
    if (!form) return;
    injectCss();
    validateBlueprintForm(form);
    const marks = mapBlueprintPendenciasToMarks(errors);
    paintBlueprintUniquenessMarks(form, marks);
    showBlueprintBanner(form, errors && errors.length ? errors : null);
  }

  function bindBlueprintRequiredLiveFields(form) {
    if (!form || form.dataset.prodespReqBound === "1") return;
    form.dataset.prodespReqBound = "1";

    function refreshUnit() {
      collectAndPaintBlueprintUnitErrors(form);
    }

    ["hostname_unidades", "acronimo_unidades"].forEach(function (name) {
      const el = form.querySelector('[name="' + name + '"]');
      if (!el) return;
      ["input", "change", "blur"].forEach(function (evt) {
        el.addEventListener(evt, function () {
          paintRequiredTextField(el, {
            label: name === "hostname_unidades" ? "Hostname" : "Sigla Secretaria (Acrônimo)",
            emptyMessage:
              name === "hostname_unidades"
                ? "Hostname da Unidade é obrigatório."
                : "Sigla Secretaria (Acrônimo) é obrigatória.",
          });
        });
      });
    });

    [
      { name: "ip_lan_01_unidades", label: "IP LAN 1", required: true },
      { name: "mv_ip_lan_sec_unidades", label: "IP LAN SEC", required: false },
      { name: "mv_ip_lan_ter_unidades", label: "IP LAN TER", required: false },
      { name: "mv_ip_lan_qua_unidades", label: "IP LAN QUA", required: false },
      { name: "mv_ip_wifi_guest_unidades", label: "IP WiFi Guest", required: false },
    ].forEach(function (cfg) {
      const el = form.querySelector('[name="' + cfg.name + '"]');
      if (!el) return;
      ["input", "change", "blur"].forEach(function (evt) {
        el.addEventListener(evt, function () {
          paintCidrIpField(el, { required: cfg.required, label: cfg.label });
          if (!cfg.required) refreshUnit();
        });
      });
    });

    [
      { name: "latitude_unidades", label: "Latitude" },
      { name: "longitude_unidades", label: "Longitude" },
    ].forEach(function (cfg) {
      const el = form.querySelector('[name="' + cfg.name + '"]');
      if (!el) return;
      ["input", "change", "blur"].forEach(function (evt) {
        el.addEventListener(evt, function () {
          if (evt === "blur") {
            var v = (el.value || "").trim().replace(/\s+/g, "");
            if (v) el.value = v.replace(",", ".");
          }
          paintCoordinateField(el, { label: cfg.label });
        });
      });
    });

    const serialEl = form.querySelector('[name="serial_equipamentos"]');
    if (serialEl) {
      ["input", "change", "blur"].forEach(function (evt) {
        serialEl.addEventListener(evt, function () {
          const check = paintSerialFortinetField(serialEl, null, {
            obrigatorio: true,
            exigePadrao: false,
          });
          if (!check.valid) serialEl.classList.add("is-invalid");
          else serialEl.classList.remove("is-invalid");
        });
      });
    }

    const linkRefreshers = [];
    ["mpls", "static"].forEach(function (prefix) {
      const label = prefix === "mpls" ? "Link MPLS" : "Link STATIC (SAI-BL)";
      const velEl = form.querySelector('[name="' + prefix + '_velocidade"]');
      const desEl = form.querySelector('[name="' + prefix + '_designador"]');
      const opEl = form.querySelector('[name="' + prefix + '_operadora"]');
      const maskEl = form.querySelector('[name="' + prefix + '_ip_mascara"]');
      const idVgrEl = form.querySelector('[name="' + prefix + '_id_vgr"]');
      const wanEl = form.querySelector('[name="' + prefix + '_ip_wan"]');
      const gwEl = form.querySelector('[name="' + prefix + '_ip_gateway"]');
      function refreshLinkPresence() {
        if (!blueprintLinkSectionHasContent(form, prefix)) {
          if (velEl) paintVelocityRequiredField(velEl, { label: label, required: false });
          return;
        }
        if (desEl && !String(desEl.value || "").trim()) {
          paintBlueprintLinkPresenceField(desEl, label + ": Designador (LP) é obrigatório.");
        } else if (desEl) {
          paintBlueprintLinkIdentifierOk(desEl, "designador", opEl && opEl.value, desEl.value);
        }
        if (opEl && !String(opEl.value || "").trim()) {
          paintBlueprintLinkPresenceField(opEl, label + ": Operadora é obrigatória.");
        } else if (opEl) {
          clearBlueprintLinkPresenceField(opEl);
        }
        if (maskEl && !String(maskEl.value || "").trim()) {
          paintBlueprintLinkPresenceField(maskEl, label + ": IP Máscara é obrigatória.");
        } else if (maskEl) {
          clearBlueprintLinkPresenceField(maskEl);
        }
        if (velEl) paintVelocityRequiredField(velEl, { label: label, required: true });
        if (isVivoOperadora(opEl && opEl.value)) {
          if (idVgrEl && !String(idVgrEl.value || "").trim()) {
            paintBlueprintLinkPresenceField(idVgrEl, label + ": ID VGR obrigatório para VIVO.");
          } else if (idVgrEl) {
            paintBlueprintLinkIdentifierOk(idVgrEl, "id_vgr", opEl.value, idVgrEl.value);
          }
        } else if (idVgrEl) {
          if (String(idVgrEl.value || "").trim()) {
            paintBlueprintLinkIdentifierOk(idVgrEl, "id_vgr", opEl && opEl.value, idVgrEl.value);
          } else {
            clearBlueprintLinkPresenceField(idVgrEl);
          }
        }
        const wanVal = sanitizePlainIpv4(wanEl && wanEl.value);
        const gwVal = sanitizePlainIpv4(gwEl && gwEl.value);
        if (!wanVal) {
          paintBlueprintLinkPresenceField(wanEl, label + ": IP WAN é obrigatório.");
        } else if (wanEl) {
          clearBlueprintLinkPresenceField(wanEl);
        }
        if (!gwVal) {
          paintBlueprintLinkPresenceField(gwEl, label + ": IP Gateway é obrigatório.");
        } else if (gwEl) {
          clearBlueprintLinkPresenceField(gwEl);
        }
        if (wanVal && gwVal) {
          const pair = validateLinkPair(wanEl.value, gwEl.value, {
            label: label,
            checkStaticBlock: prefix === "static",
          });
          if (!pair.valid) {
            paintBlueprintLinkPresenceField(wanEl, pair.message);
            paintBlueprintLinkPresenceField(gwEl, pair.message);
          }
        }
      }
      linkRefreshers.push(refreshLinkPresence);
      [velEl, desEl, opEl, maskEl, idVgrEl, wanEl, gwEl].forEach(function (el) {
        if (!el) return;
        ["input", "change", "blur"].forEach(function (evt) {
          el.addEventListener(evt, refreshLinkPresence);
        });
        // paste preventDefault (no-space/ip) — reforça refresh após o valor limpo
        el.addEventListener("paste", function () {
          scheduleAfterPaste(refreshLinkPresence);
        });
      });
    });

    form._prodespBlueprintLinkRefreshers = linkRefreshers;
  }

  /**
   * Pinta estado visual no load (dados do banco), igual aos loopbacks — sem banner.
   */
  function paintBlueprintInitialState(formRef) {
    const form = resolveEl(formRef) || document.getElementById("blueprint-form");
    if (!form) return;
    injectCss();
    collectAndPaintBlueprintUnitErrors(form);
    const refreshers = form._prodespBlueprintLinkRefreshers || [];
    refreshers.forEach(function (fn) {
      if (typeof fn === "function") fn();
    });
  }

  function ensureUniqFieldHint(inputEl) {
    if (!inputEl || !inputEl.parentNode) return null;
    let hint = inputEl.parentNode.querySelector("small[data-uniq-hint]");
    if (!hint) {
      hint = document.createElement("small");
      hint.className = "prodesp-field-live-hint";
      hint.setAttribute("data-uniq-hint", "1");
      inputEl.parentNode.appendChild(hint);
    }
    return hint;
  }

  function clearBlueprintUniquenessMarks(form) {
    if (!form) return;
    form.querySelectorAll("[data-prodesp-uniq='1']").forEach(function (el) {
      el.removeAttribute("data-prodesp-uniq");
      el.classList.remove("is-invalid");
      clearFieldStates(el);
      const hint = el.parentNode && el.parentNode.querySelector("small[data-uniq-hint]");
      if (hint) setHint(hint, "", "");
    });
  }

  function paintBlueprintUniquenessMarks(form, marks) {
    clearBlueprintUniquenessMarks(form);
    if (!marks) return;
    Object.keys(marks).forEach(function (name) {
      const el = form.querySelector('[name="' + name + '"]');
      if (!el) return;
      el.setAttribute("data-prodesp-uniq", "1");
      clearFieldStates(el);
      el.classList.add("prodesp-field-state-empty");
      el.classList.add("is-invalid");
      const hint = ensureUniqFieldHint(el);
      setHint(hint, marks[name], "invalid");
    });
  }

  function readBlueprintLinkSnapshot(form, prefix) {
    const val = function (suffix) {
      const el = form.querySelector('[name="' + prefix + "_" + suffix + '"]');
      return el ? String(el.value || "").trim() : "";
    };
    const idEl = form.querySelector('[name="' + prefix + '_id_link"]');
    return {
      prefix: prefix,
      id: idEl && idEl.value ? idEl.value : "",
      tipo: prefix.toUpperCase(),
      operadora: val("operadora").toUpperCase(),
      designador: val("designador"),
      id_vgr: val("id_vgr"),
      wan: sanitizePlainIpv4(val("ip_wan")),
      gw: sanitizePlainIpv4(val("ip_gateway")),
      label: "Link " + prefix.toUpperCase() + (val("designador") ? " — " + val("designador") : ""),
    };
  }

  function detectLocalBlueprintUniqueness(form) {
    const links = ["mpls", "static"].map(function (p) {
      return readBlueprintLinkSnapshot(form, p);
    });
    const errors = [];
    const marks = {};
    const mark = function (prefix, field, msg) {
      const name = prefix + "_" + field;
      if (!marks[name]) marks[name] = msg;
    };

    links.forEach(function (snap) {
      const fmt = validateLinkFormatFields({
        operadora: snap.operadora,
        designador: snap.designador,
        idVgr: snap.id_vgr,
      });
      if (!fmt.valid) {
        errors.push(fmt.message);
        if (/Designador/i.test(fmt.message)) mark(snap.prefix, "designador", fmt.message);
        if (/ID VGR/i.test(fmt.message)) mark(snap.prefix, "id_vgr", fmt.message);
      }
    });

    function crossCheck(a, b) {
      if (a.wan && b.wan && a.wan === b.wan) {
        const msg =
          "IP WAN «" + a.wan + "» repetido entre " + a.label + " e " + b.label + " no mesmo formulário.";
        errors.push(msg);
        mark(a.prefix, "ip_wan", msg);
        mark(b.prefix, "ip_wan", msg);
      }
      if (a.gw && b.gw && a.gw === b.gw) {
        const msg =
          "IP Gateway «" + a.gw + "» repetido entre " + a.label + " e " + b.label + " no mesmo formulário.";
        errors.push(msg);
        mark(a.prefix, "ip_gateway", msg);
        mark(b.prefix, "ip_gateway", msg);
      }
      if (a.wan && b.gw && a.wan === b.gw) {
        const msg =
          "IP WAN «" + a.wan + "» de " + a.label + " coincide com o Gateway de " + b.label + " no formulário.";
        errors.push(msg);
        mark(a.prefix, "ip_wan", msg);
        mark(b.prefix, "ip_gateway", msg);
      }
      if (a.gw && b.wan && a.gw === b.wan) {
        const msg =
          "IP Gateway «" + a.gw + "» de " + a.label + " coincide com o WAN de " + b.label + " no formulário.";
        errors.push(msg);
        mark(a.prefix, "ip_gateway", msg);
        mark(b.prefix, "ip_wan", msg);
      }
      if (a.operadora && b.operadora && a.operadora === b.operadora) {
        if (a.designador && b.designador && a.designador === b.designador) {
          const msg =
            "Designador «" + a.designador + "» (Operadora " + a.operadora + ") repetido entre " +
            a.label + " e " + b.label + " no formulário.";
          errors.push(msg);
          mark(a.prefix, "designador", msg);
          mark(b.prefix, "designador", msg);
        }
        if (a.id_vgr && b.id_vgr && a.id_vgr === b.id_vgr) {
          const msg =
            "ID VGR do link «" + a.id_vgr + "» (Operadora " + a.operadora + ") repetido entre " +
            a.label + " e " + b.label + " no formulário.";
          errors.push(msg);
          mark(a.prefix, "id_vgr", msg);
          mark(b.prefix, "id_vgr", msg);
        }
      }
    }

    if (links.length >= 2) crossCheck(links[0], links[1]);

    links.forEach(function (lnk) {
      if (lnk.wan && lnk.gw && lnk.wan === lnk.gw) {
        const msg = lnk.label + ": IP WAN e Gateway não podem ser iguais.";
        errors.push(msg);
        mark(lnk.prefix, "ip_wan", msg);
        mark(lnk.prefix, "ip_gateway", msg);
      }
    });

    return { errors: errors, marks: marks, links: links };
  }

  function mapServerUniquenessToMarks(form, serverErrors) {
    const marks = {};
    const local = detectLocalBlueprintUniqueness(form);
    Object.keys(local.marks).forEach(function (k) {
      marks[k] = local.marks[k];
    });
    const msgs = serverErrors || [];
    ["mpls", "static"].forEach(function (prefix) {
      const snap = readBlueprintLinkSnapshot(form, prefix);
      msgs.forEach(function (msg) {
        const m = String(msg || "");
        if (snap.wan && m.indexOf("«" + snap.wan + "»") >= 0 && /IP WAN/i.test(m)) {
          marks[prefix + "_ip_wan"] = m;
        }
        if (snap.gw && m.indexOf("«" + snap.gw + "»") >= 0 && /IP Gateway|Gateway/i.test(m)) {
          marks[prefix + "_ip_gateway"] = m;
        }
        if (snap.designador && m.indexOf("«" + snap.designador + "»") >= 0 && /Designador/i.test(m)) {
          marks[prefix + "_designador"] = m;
        }
        if (snap.id_vgr && m.indexOf("«" + snap.id_vgr + "»") >= 0 && /ID VGR/i.test(m)) {
          marks[prefix + "_id_vgr"] = m;
        }
      });
    });
    const lbFields = [
      ["loopback_vivo_unidades", /Loopback Vivo/i],
      ["loopback_cliente_unidades", /Loopback Cliente/i],
      ["loopback_on_bgp_unidades", /Loopback On BGP|On BGP/i],
    ];
    lbFields.forEach(function (pair) {
      const name = pair[0];
      const re = pair[1];
      const el = form.querySelector('[name="' + name + '"]');
      const val = el ? sanitizePlainIpv4(el.value) : "";
      msgs.forEach(function (msg) {
        const m = String(msg || "");
        if (val && m.indexOf("«" + val + "»") >= 0 && re.test(m)) {
          marks[name] = m;
        } else if (re.test(m) && /mesma unidade|loopback/i.test(m)) {
          marks[name] = m;
        }
      });
    });
    return marks;
  }

  function buildBlueprintUniquenessPayload(form) {
    const idUnidadeEl = form.querySelector('[name="id_unidades"]');
    const linksPayload = ["mpls", "static"].map(function (prefix) {
      const snap = readBlueprintLinkSnapshot(form, prefix);
      return {
        id: snap.id || null,
        id_link: snap.id || null,
        tipo_links: snap.tipo,
        operadora_links: snap.operadora,
        designador_links: snap.designador,
        id_vgr_links: snap.id_vgr,
        ip_wan_links: snap.wan,
        ip_gateway_links: snap.gw,
      };
    });
    return {
      id_unidade: idUnidadeEl ? idUnidadeEl.value : "",
      links: linksPayload,
      loopbacks: {
        loopback_vivo_unidades: (form.querySelector('[name="loopback_vivo_unidades"]') || {}).value || "",
        loopback_cliente_unidades: (form.querySelector('[name="loopback_cliente_unidades"]') || {}).value || "",
        loopback_on_bgp_unidades: (form.querySelector('[name="loopback_on_bgp_unidades"]') || {}).value || "",
      },
    };
  }

  function initBlueprintUniquenessWatch(form) {
    if (!form || form.dataset.prodespUniqWatch === "1") return;
    form.dataset.prodespUniqWatch = "1";
    let timer = null;
    let reqSeq = 0;

    function applyLocal() {
      const local = detectLocalBlueprintUniqueness(form);
      paintBlueprintUniquenessMarks(form, local.marks);
      return local;
    }

    function runRemote() {
      const local = applyLocal();
      const payload = buildBlueprintUniquenessPayload(form);
      const seq = ++reqSeq;
      fetch("/prodesp/api/check-uniqueness", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (seq !== reqSeq) return;
          if (data && data.ok === false) {
            const marks = mapServerUniquenessToMarks(
              form,
              data.errors && data.errors.length ? data.errors : [data.message]
            );
            paintBlueprintUniquenessMarks(form, marks);
          } else if (!local.errors.length) {
            clearBlueprintUniquenessMarks(form);
          } else {
            paintBlueprintUniquenessMarks(form, local.marks);
          }
        })
        .catch(function () {
          /* pré-check remoto opcional; submit ainda valida */
        });
    }

    function schedule() {
      applyLocal();
      if (timer) clearTimeout(timer);
      timer = setTimeout(runRemote, 450);
    }

    const watchNames = [
      "mpls_ip_wan", "mpls_ip_gateway", "mpls_designador", "mpls_id_vgr", "mpls_operadora",
      "static_ip_wan", "static_ip_gateway", "static_designador", "static_id_vgr", "static_operadora",
      "loopback_vivo_unidades", "loopback_cliente_unidades", "loopback_on_bgp_unidades",
    ];
    watchNames.forEach(function (name) {
      const el = form.querySelector('[name="' + name + '"]');
      if (!el) return;
      ["input", "change"].forEach(function (evt) {
        el.addEventListener(evt, schedule);
      });
      el.addEventListener("paste", function () {
        scheduleAfterPaste(schedule);
      });
    });

    // Após paint de formato (verde), reaplicar vermelho de duplicidade
    form.addEventListener("prodesp:after-format-paint", schedule);
    applyLocal();
    setTimeout(runRemote, 300);

    return { refresh: schedule, applyLocal: applyLocal, runRemote: runRemote };
  }

  function showBlueprintBanner(form, messages) {
    let banner = form.querySelector("#blueprint-validation-banner");
    if (!banner) {
      banner = document.createElement("div");
      banner.id = "blueprint-validation-banner";
      banner.className = "alert alert-danger shadow-sm mb-3 d-none";
      banner.setAttribute("role", "alert");
      form.insertBefore(banner, form.firstChild);
    }
    if (!messages || !messages.length) {
      banner.classList.add("d-none");
      banner.replaceChildren();
      return;
    }
    banner.classList.remove("d-none");
    banner.replaceChildren();
    const title = document.createElement("strong");
    title.innerHTML = '<i class="fas fa-exclamation-triangle me-2"></i>Corrija antes de gerar:';
    const ul = document.createElement("ul");
    ul.className = "mb-0 mt-2";
    messages.forEach(function (m) {
      const li = document.createElement("li");
      li.textContent = m;
      ul.appendChild(li);
    });
    banner.appendChild(title);
    banner.appendChild(ul);
    banner.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function prepareBlueprintFormValues(form) {
    applyVivoBlueprintLinks(form);
    form.querySelectorAll(".prodesp-ip-plain-only").forEach(function (el) {
      el.value = sanitizePlainIpv4(el.value);
    });
    form.querySelectorAll(".prodesp-ip-input").forEach(function (el) {
      if (el.classList.contains("prodesp-ip-plain-only")) return;
      el.value = stripIp(el.value);
    });
    form.querySelectorAll(".prodesp-no-space-input").forEach(function (el) {
      el.value = stripAllSpaces(el.value);
    });
    form.querySelectorAll(".prodesp-coord-input").forEach(function (el) {
      var v = (el.value || "").trim().replace(/\s+/g, "");
      if (v) el.value = v.replace(",", ".");
    });
    form.querySelectorAll(".prodesp-velocity-mbps-input").forEach(function (el) {
      const norm = normalizeVelocityMbps(el.value);
      el.value = norm.value;
    });
  }

  function initBlueprintForm(formRef) {
    const form = resolveEl(formRef) || document.getElementById("blueprint-form");
    if (!form) return null;

    const linkPairs = [];
    const vivoControllers = [];
    [
      { prefix: "mpls", label: "Link MPLS", hint: "mpls-link-hint" },
      { prefix: "static", label: "Link STATIC (SAI-BL)", hint: "static-link-hint", staticBlock: true },
    ].forEach(function (cfg) {
      const wanEl = form.querySelector('[name="' + cfg.prefix + '_ip_wan"]');
      const gwEl = form.querySelector('[name="' + cfg.prefix + '_ip_gateway"]');
      let hintEl = document.getElementById(cfg.hint);
      if (!hintEl && wanEl && wanEl.closest(".card-body")) {
        hintEl = document.createElement("div");
        hintEl.id = cfg.hint;
        hintEl.className = "prodesp-link-pair-hint mb-2";
        const gwWrap = gwEl && gwEl.closest(".form-group");
        if (gwWrap && gwWrap.parentNode) {
          const row = gwWrap.closest(".row");
          if (row && row.parentNode) {
            row.parentNode.insertBefore(hintEl, row.nextSibling);
          }
        }
      }
      const pair = initLinkPair(wanEl, gwEl, {
        label: cfg.label,
        hintRef: hintEl,
        checkStaticBlock: !!cfg.staticBlock,
      });
      if (pair) linkPairs.push(pair);

      const operadoraEl = form.querySelector('[name="' + cfg.prefix + '_operadora"]');
      const maskEl = form.querySelector('[name="' + cfg.prefix + '_ip_mascara"]');
      let redundanteCtrl = null;
      let vivo = null;
      if (cfg.prefix === "mpls") {
        const redundanteEl = form.querySelector("#mpls_redundante_critico");
        const redundanteWrap = form.querySelector(".mpls-redundante-critico-row");
        if (redundanteEl) {
          redundanteCtrl = initRedundanteCriticoMplsVivo({
            wanEl: wanEl,
            checkboxEl: redundanteEl,
            wrapperEl: redundanteWrap,
            getTipo: function () {
              return "MPLS";
            },
            getOperadora: function () {
              return operadoraEl ? operadoraEl.value : "";
            },
            onAfterApply: function () {
              if (vivo && vivo.apply) vivo.apply("wan");
              else if (vivo && vivo.validate) vivo.validate();
              if (pair && pair.refresh) pair.refresh();
            },
          });
        }
      }
      vivo = initVivoLinkAutoFill(wanEl, gwEl, maskEl, operadoraEl, {
        linkTipo: cfg.prefix === "mpls" ? "MPLS" : "STATIC",
        label: cfg.label,
        onAfterApply: function () {
          if (pair && pair.refresh) pair.refresh();
        },
        redundanteCritico: function () {
          return redundanteCtrl && redundanteCtrl.isActive();
        },
      });
      if (vivo) vivoControllers.push(vivo);
    });

    const loopback = initLoopbackTriplet({
      vivo: form.querySelector('[name="loopback_vivo_unidades"]'),
      cliente: form.querySelector('[name="loopback_cliente_unidades"]'),
      bgp: form.querySelector('[name="loopback_on_bgp_unidades"]'),
      emptyHint: "Campo vazio — obrigatório para Blueprint.",
    });
    form._prodespLoopbackCtrl = loopback;

    form.querySelectorAll(".prodesp-no-space-input").forEach(function (el) {
      bindNoWhitespaceInput(el);
    });
    form.querySelectorAll(".prodesp-ip-plain-only").forEach(function (el) {
      bindPlainIpv4Input(el);
    });
    bindAllVelocityMbpsInputs(form);
    bindBlueprintRequiredLiveFields(form);

    const uniqWatch = initBlueprintUniquenessWatch(form);

    form.addEventListener("submit", function (e) {
      linkPairs.forEach(function (p) {
        if (p && p.refresh) p.refresh();
      });
      vivoControllers.forEach(function (v) {
        if (v && v.validate) v.validate();
      });
      if (loopback && loopback.refresh) loopback.refresh();
      if (uniqWatch && uniqWatch.applyLocal) uniqWatch.applyLocal();

      const validated = validateBlueprintForm(form);
      if (!validated.valid) {
        e.preventDefault();
        if (typeof e.stopImmediatePropagation === "function") e.stopImmediatePropagation();
        else e.stopPropagation();
        if (global.ProdespSubmitGuard && typeof global.ProdespSubmitGuard.unlockForm === "function") {
          global.ProdespSubmitGuard.unlockForm(form);
        }
        return;
      }

      /* 1º submit com modal de confirmação: só validou/pintou; o confirm.js abre o modal. */
      if (form.dataset.bpConfirmOk !== "1" && document.getElementById("modalBlueprintConfirm")) {
        return;
      }

      prepareBlueprintFormValues(form);
      showBlueprintBanner(form, []);

      // Pré-checagem de duplicidade no servidor antes de gravar/gerar
      if (form.dataset.prodespUniqChecked === "1") {
        form.dataset.prodespUniqChecked = "";
        return;
      }
      e.preventDefault();
      const payload = buildBlueprintUniquenessPayload(form);
      fetch("/prodesp/api/check-uniqueness", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (data && data.ok === false) {
            const errs =
              data.errors && data.errors.length
                ? data.errors
                : [data.message || "Duplicidade encontrada."];
            paintBlueprintUniquenessMarks(form, mapServerUniquenessToMarks(form, errs));
            showBlueprintBanner(form, errs);
            return;
          }
          clearBlueprintUniquenessMarks(form);
          form.dataset.prodespUniqChecked = "1";
          if (typeof form.requestSubmit === "function") form.requestSubmit();
          else form.submit();
        })
        .catch(function () {
          form.dataset.prodespUniqChecked = "1";
          if (typeof form.requestSubmit === "function") form.requestSubmit();
          else form.submit();
        });
    });

    refreshFormAfterDataLoad({
      loopbacks: {
        vivo: form.querySelector('[name="loopback_vivo_unidades"]'),
        cliente: form.querySelector('[name="loopback_cliente_unidades"]'),
        bgp: form.querySelector('[name="loopback_on_bgp_unidades"]'),
      },
      loopbackController: loopback,
      form: form,
      linkPairRefresh: linkPairs.map(function (p) {
        return p && p.refresh;
      }),
    });
    vivoControllers.forEach(function (v) {
      if (v && v.validate) v.validate();
    });
    if (uniqWatch && uniqWatch.refresh) uniqWatch.refresh();
    /* Hostname/CIDR/serial/links: pintar no load (dados do banco), como os loopbacks. */
    paintBlueprintInitialState(form);

    return { linkPairs, loopback, vivoControllers, form, uniqWatch };
  }

  function linkLabelFromTipoDesignador(tipo, designador) {
    const t = String(tipo || "Link").trim();
    const d = String(designador || "").trim();
    return "Link " + t + (d ? " — Designador: " + d : "");
  }

  /**
   * ID VGR do link: só exibe (e exige) para MPLS/STATIC + operadora VIVO — alinhado ao Blueprint.
   */
  function syncAtendimentoLinkIdVgrVisibility(context) {
    const prefix = String(context || "");
    const wrap = document.querySelector(
      "#" + prefix + "-link-fields-container .link-id-vgr-vivo-wrapper"
    );
    if (!wrap) return false;
    const tipoEl = document.getElementById(prefix + "LinkTipo");
    const operadoraEl = document.getElementById(prefix + "LinkOperadora");
    const input = document.getElementById(prefix + "LinkIdVgr");
    const tipo = String((tipoEl && tipoEl.value) || "")
      .trim()
      .toUpperCase();
    const tipoOk = tipo === "MPLS" || tipo === "STATIC";
    const show = tipoOk && isVivoOperadora(operadoraEl && operadoraEl.value);
    wrap.style.display = show ? "" : "none";
    if (input) {
      if (show) input.setAttribute("required", "required");
      else input.removeAttribute("required");
    }
    return show;
  }

  /**
   * Formulário de link nos modais de atendimento (edit/create) — mesmas regras do Blueprint:
   * WAN/Gateway, bloco STATIC 201.60/201.61, VIVO (máscara/gateway).
   */
  function initAtendimentoLinkForm(context) {
    const prefix = String(context || "");
    const tipoEl = document.getElementById(prefix + "LinkTipo");
    const designadorEl = document.getElementById(prefix + "LinkDesignador");
    const wanEl = document.getElementById(prefix + "LinkIpWan");
    const gwEl = document.getElementById(prefix + "LinkIpGateway");
    const maskEl = document.getElementById(prefix + "LinkIpMascara");
    const operadoraEl = document.getElementById(prefix + "LinkOperadora");
    const redundanteEl = document.getElementById(prefix + "LinkRedundanteCritico");
    const redundanteWrap = document.querySelector(
      '#' + prefix + '-link-fields-container .mpls-vivo-redundante-wrapper'
    );
    if (!wanEl || !gwEl) return null;

    syncAtendimentoLinkIdVgrVisibility(prefix);
    if (operadoraEl) {
      operadoraEl.addEventListener("change", function () {
        syncAtendimentoLinkIdVgrVisibility(prefix);
      });
    }

    let hintEl = document.getElementById(prefix + "-link-pair-hint");
    if (!hintEl) {
      const container = document.getElementById(prefix + "-link-fields-container");
      if (container) {
        hintEl = document.createElement("div");
        hintEl.id = prefix + "-link-pair-hint";
        hintEl.className = "prodesp-link-pair-hint mb-2 col-12 link-field-wrapper";
        hintEl.setAttribute("data-link-type", "STATIC MPLS");
        container.appendChild(hintEl);
      }
    }

    const pair = initLinkPair(wanEl, gwEl, {
      hintRef: hintEl,
      getOpts: function () {
        const tipo = tipoEl ? tipoEl.value : "";
        const designador = designadorEl ? designadorEl.value : "";
        return {
          label: linkLabelFromTipoDesignador(tipo, designador),
          checkStaticBlock: String(tipo).toUpperCase() === "STATIC",
        };
      },
    });

    let redundanteCtrl = null;
    let vivo = null;
    if (redundanteEl) {
      redundanteCtrl = initRedundanteCriticoMplsVivo({
        wanEl: wanEl,
        checkboxEl: redundanteEl,
        wrapperEl: redundanteWrap,
        tipoEl: tipoEl,
        operadoraEl: operadoraEl,
        onAfterApply: function () {
          if (vivo && vivo.apply) vivo.apply("wan");
          else if (vivo && vivo.validate) vivo.validate();
          if (pair && pair.refresh) pair.refresh();
        },
      });
    }

    vivo = initVivoLinkAutoFill(wanEl, gwEl, maskEl, operadoraEl, {
      tipoEl: tipoEl,
      getLinkTipo: function () {
        return tipoEl ? tipoEl.value : "STATIC";
      },
      label: linkLabelFromTipoDesignador(
        tipoEl ? tipoEl.value : "",
        designadorEl ? designadorEl.value : ""
      ),
      onAfterApply: function () {
        if (pair && pair.refresh) pair.refresh();
      },
      redundanteCritico: function () {
        return redundanteCtrl && redundanteCtrl.isActive();
      },
    });

    if (tipoEl) {
      tipoEl.addEventListener("change", function () {
        syncAtendimentoLinkIdVgrVisibility(prefix);
        if (vivo && vivo.validate) vivo.validate();
        else if (vivo && vivo.refresh) vivo.refresh(true);
        if (pair && pair.refresh) pair.refresh();
      });
    }
    if (designadorEl) {
      designadorEl.addEventListener("input", function () {
        if (pair && pair.refresh) pair.refresh();
      });
    }

    return {
      pair: pair,
      vivo: vivo,
      redundante: redundanteCtrl,
      refresh: function () {
        syncAtendimentoLinkIdVgrVisibility(prefix);
        if (pair && pair.refresh) pair.refresh();
        if (vivo && vivo.validate) vivo.validate();
      },
    };
  }

  /** Linha inline de link (tabela) — mesmas regras VIVO + WAN/Gateway. */
  function initInlineAtendimentoLinkRow(wanEl, gwEl, maskEl, operadoraEl, tipoEl, designadorEl, extras) {
    if (!wanEl || !gwEl) return null;
    const extra = extras || {};
    const pair = initLinkPair(wanEl, gwEl, {
      getOpts: function () {
        const tipo = tipoEl ? tipoEl.value : "";
        const designador = designadorEl ? designadorEl.value : "";
        return {
          label: linkLabelFromTipoDesignador(tipo, designador),
          checkStaticBlock: String(tipo).toUpperCase() === "STATIC",
        };
      },
    });
    const vivo = initVivoLinkAutoFill(wanEl, gwEl, maskEl, operadoraEl, {
      tipoEl: tipoEl,
      getLinkTipo: function () {
        return tipoEl ? tipoEl.value : "STATIC";
      },
      label: linkLabelFromTipoDesignador(
        tipoEl ? tipoEl.value : "",
        designadorEl ? designadorEl.value : ""
      ),
      onAfterApply: function () {
        if (pair && pair.refresh) pair.refresh();
      },
      skipGatewayWhen: function () {
        if (typeof extra.skipGatewayWhen === "function") return !!extra.skipGatewayWhen();
        return false;
      },
      redundanteCritico: function () {
        if (typeof extra.redundanteCritico === "function") return !!extra.redundanteCritico();
        return !!extra.redundanteCritico;
      },
    });
    if (tipoEl) {
      tipoEl.addEventListener("change", function () {
        if (vivo && vivo.validate) vivo.validate();
        else if (vivo && vivo.refresh) vivo.refresh(true);
        if (pair && pair.refresh) pair.refresh();
      });
    }
    return {
      pair: pair,
      vivo: vivo,
      refresh: function () {
        if (pair && pair.refresh) pair.refresh();
        if (vivo && vivo.validate) vivo.validate();
      },
    };
  }

  function validateLinkFormatFields(fields) {
    const operadora = String(fields.operadora || fields.operadora_links || "").trim();
    // Mesma higienizacao de colagem do backend (link_format_rules.sanitize_link_pasted_text)
    const designador = sanitizeLinkPastedText(
      fields.designador || fields.designador_links || ""
    );
    const idVgr = sanitizeLinkPastedText(
      fields.idVgr || fields.id_vgr || fields.id_vgr_links || ""
    );
    const DES_MIN = 15;
    const VGR_MIN = 7;
    if (isVivoOperadora(operadora) && designador) {
      if (!/^\d+$/.test(designador) || designador.length < DES_MIN) {
        return {
          valid: false,
          message:
            "Designador «" +
            designador +
            "» fora do padrão VIVO: use apenas dígitos com no mínimo " +
            DES_MIN +
            " caracteres (ex.: circuito de 15 dígitos).",
        };
      }
    }
    if (idVgr) {
      if (!/^\d+$/.test(idVgr) || idVgr.length < VGR_MIN) {
        return {
          valid: false,
          message:
            "ID VGR do link «" +
            idVgr +
            "» fora do padrão: use apenas dígitos com no mínimo " +
            VGR_MIN +
            " caracteres (ex.: 1737352).",
        };
      }
    }
    return { valid: true, message: "" };
  }

  /**
   * Valida e normaliza link antes de salvar (addLinkLogic / edição inline).
   * Retorna { valid, message, ipWan, ipGateway, ipMascara }.
   */
  function validateAtendimentoLinkRequired(fields) {
    const tipo = String(fields.tipo || "").trim();
    const tipoUp = tipo.toUpperCase();
    const operadora = String(fields.operadora || "").trim();
    const designador = String(fields.designador || "").trim();
    const velocidade = String(fields.velocidade || "").trim();
    const missing = [];
    if (!tipo) missing.push("Tipo");
    if (!operadora) missing.push("Operadora");
    if (!designador) missing.push("Designador");
    if (!velocidade) missing.push("Velocidade");
    if (tipoUp === "MPLS" || tipoUp === "STATIC") {
      if (!String(fields.ipWan || "").trim()) missing.push("IP WAN");
      if (!String(fields.ipGateway || "").trim()) missing.push("IP Gateway");
      if (!String(fields.ipMascara || "").trim()) missing.push("IP Máscara");
      if (isVivoOperadora(operadora) && !String(fields.idVgr || "").trim()) {
        missing.push("ID VGR do Link");
      }
    } else if (tipoUp === "PPPOE") {
      if (!String(fields.pppoeUser || "").trim()) missing.push("PPPoE User");
      if (!String(fields.pppoePass || "").trim()) missing.push("PPPoE Password");
    }
    if (missing.length) {
      return {
        valid: false,
        message: "Campos obrigatórios do link não preenchidos: " + missing.join(", ") + ".",
      };
    }
    return { valid: true, message: "" };
  }

  function validateAtendimentoLinkSubmit(fields) {
    const req = validateAtendimentoLinkRequired(fields);
    if (!req.valid) {
      return {
        valid: false,
        message: req.message,
        ipWan: sanitizePlainIpv4(fields.ipWan),
        ipGateway: sanitizePlainIpv4(fields.ipGateway),
        ipMascara: stripIp(fields.ipMascara),
      };
    }

    const fmt = validateLinkFormatFields(fields);
    if (!fmt.valid) {
      return {
        valid: false,
        message: fmt.message,
        ipWan: sanitizePlainIpv4(fields.ipWan),
        ipGateway: sanitizePlainIpv4(fields.ipGateway),
        ipMascara: stripIp(fields.ipMascara),
      };
    }

    const tipo = fields.tipo;
    const designador = fields.designador;
    const operadora = fields.operadora;
    const redundanteCritico =
      appliesRedundanteCritico(tipo, operadora) && !!fields.redundanteCritico;
    let ipWan = sanitizePlainIpv4(fields.ipWan);
    let ipGw = sanitizePlainIpv4(fields.ipGateway);
    let ipMask = stripIp(fields.ipMascara);

    if (isVivoOperadora(operadora) && ipWan) {
      const compliance = validateVivoLinkCompliance(ipWan, ipMask, ipGw, operadora, tipo, {
        label: linkLabelFromTipoDesignador(tipo, designador),
        redundanteCritico: redundanteCritico,
      });
      if (!compliance.valid && compliance.summaryMessage) {
        return {
          valid: false,
          message: compliance.summaryMessage,
          ipWan: ipWan,
          ipGateway: ipGw,
          ipMascara: ipMask,
        };
      }
      const derived = deriveVivoLinkFields(ipWan, tipo, redundanteCritico);
      if (derived) {
        ipMask = derived.mask;
        ipGw = derived.gateway;
      }
    }

    const label = linkLabelFromTipoDesignador(tipo, designador);
    const pairResult = validateLinkPair(ipWan, ipGw, {
      label: label,
      checkStaticBlock: String(tipo).toUpperCase() === "STATIC",
    });
    if (!pairResult.valid) {
      return { valid: false, message: pairResult.message, ipWan: ipWan, ipGateway: ipGw, ipMascara: ipMask };
    }

    const wanCheck = validatePlainIpv4Field(ipWan, label + " — IP WAN");
    if (!wanCheck.valid) {
      return { valid: false, message: wanCheck.message, ipWan: ipWan, ipGateway: ipGw, ipMascara: ipMask };
    }
    const gwCheck = validatePlainIpv4Field(ipGw, label + " — Gateway");
    if (!gwCheck.valid) {
      return { valid: false, message: gwCheck.message, ipWan: ipWan, ipGateway: ipGw, ipMascara: ipMask };
    }

    return { valid: true, message: "", ipWan: ipWan, ipGateway: ipGw, ipMascara: ipMask };
  }

  const TICKET_NOC_PATTERN = /^1\d{6}$/;

  function sanitizeTicketNoc(val) {
    return stripAllSpaces(val).replace(/\D/g, "").slice(0, 7);
  }

  function validateTicketNocFormat(val, opts) {
    const required = opts && opts.required;
    const s = sanitizeTicketNoc(val);
    if (!s) {
      if (required) {
        return {
          valid: false,
          message:
            "Para Status e Substatus «Concluído», o campo Ticket NOC é obrigatório.",
          value: "",
        };
      }
      return { valid: true, value: "", message: "" };
    }
    if (!TICKET_NOC_PATTERN.test(s)) {
      return {
        valid: false,
        message:
          "Ticket NOC inválido: informe 7 dígitos numéricos começando em 1 (ex.: 1680355).",
        value: s,
      };
    }
    return { valid: true, value: s, message: "" };
  }

  function bindTicketNocInput(el) {
    if (!el || el.nodeName !== "INPUT") return;
    if (el.dataset.prodespTicketNocBound === "1") return;
    el.dataset.prodespTicketNocBound = "1";
    el.setAttribute("maxlength", "7");
    el.setAttribute("inputmode", "numeric");
    el.setAttribute("autocomplete", "off");

    function applyCleaned(triggerSyntheticInput) {
      const cleaned = sanitizeTicketNoc(el.value);
      if (cleaned !== el.value) {
        const pos = el.selectionStart;
        const oldLen = el.value.length;
        el.value = cleaned;
        if (pos != null && el.setSelectionRange) {
          const shrink = Math.max(0, oldLen - cleaned.length);
          el.setSelectionRange(Math.max(0, pos - shrink), Math.max(0, pos - shrink));
        }
        triggerSyntheticInput = true;
      }
      if (triggerSyntheticInput) {
        el.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }

    el.addEventListener("keydown", function (e) {
      if (e.key === " " || e.code === "Space") e.preventDefault();
    });
    el.addEventListener("paste", function (e) {
      e.preventDefault();
      const raw = (e.clipboardData || window.clipboardData).getData("text") || "";
      insertTextAtCursor(el, sanitizeTicketNoc(raw));
      scheduleAfterPaste(function () {
        applyCleaned(true);
      });
    });
    el.addEventListener("input", function () {
      applyCleaned(false);
    });
    el.addEventListener("blur", function () {
      const result = validateTicketNocFormat(el.value, { required: false });
      if (result.value && result.value !== el.value) {
        el.value = result.value;
      }
      if (!result.valid && result.value) {
        el.classList.add("is-invalid");
      } else {
        el.classList.remove("is-invalid");
      }
    });
  }

  function initTicketNocFields(fieldIds) {
    (fieldIds || []).forEach(function (id) {
      bindTicketNocInput(resolveEl(id));
    });
  }

  /* ── Equipamento / serial Fortinet (espelha conclusao_equipamento_rules.py) ── */

  const SERIAL_MODEL_ALT = "900G|400F|200F|120G|100F|90G|80F|70F|60F|40F";
  const SERIAL_FORTINET_RE = new RegExp(
    "^(?:FGT|FG)(?:" + SERIAL_MODEL_ALT + ")TK[A-Z0-9]{6,10}$",
    "i"
  );
  const SERIAL_FAKE = {
    "123": 1,
    "1234": 1,
    "12345": 1,
    "123456": 1,
    "000": 1,
    "0000": 1,
    "0": 1,
    "1": 1,
    "12": 1,
    "999": 1,
    TEST: 1,
    TESTE: 1,
    TEMP: 1,
    PROVISORIO: 1,
    "N/A": 1,
    NA: 1,
    XXX: 1,
    XXXX: 1,
    SERIAL: 1,
    SERIALNUM: 1,
    FGT40F: 1,
    FGT60F: 1,
  };

  function normalizeSerialFortinet(val) {
    return stripAllSpaces(val).toUpperCase();
  }

  function serialFortinetValido(val) {
    const s = normalizeSerialFortinet(val);
    if (!s || SERIAL_FAKE[s]) return false;
    if (s.indexOf("XXX") >= 0) return false;
    if (/^\d+$/.test(s) && s.length <= 8) return false;
    return SERIAL_FORTINET_RE.test(s);
  }

  /**
   * @param {string} val
   * @param {{ obrigatorio?: boolean, exigePadrao?: boolean }} [opts]
   * exigePadrao=false → serial provisório só gera aviso (Blueprint antecipado).
   */
  function validateSerialFortinetFormat(val, opts) {
    opts = opts || {};
    const obrigatorio = !!opts.obrigatorio;
    const exigePadrao = opts.exigePadrao !== false;
    const s = normalizeSerialFortinet(val);
    if (!s) {
      if (obrigatorio) {
        return {
          valid: false,
          state: "empty",
          value: "",
          message: "Número de série do FortiGate é obrigatório.",
        };
      }
      return { valid: true, state: "neutral", value: "", message: "" };
    }
    if (serialFortinetValido(s)) {
      return {
        valid: true,
        state: "ok",
        value: s,
        message: "Serial Fortinet no padrão.",
      };
    }
    const msg =
      "Número de série «" +
      s +
      "» inválido ou provisório. Use o padrão FGT40FTK… / FGT60FTK… / FG120GTK… " +
      "(ex.: FGT40FTK2409D6QK).";
    if (!exigePadrao) {
      return {
        valid: true,
        state: "warn",
        value: s,
        message: msg + " Aceito só em blueprint antecipado / sem atendimento ativo.",
      };
    }
    return { valid: false, state: "invalid", value: s, message: msg };
  }

  function validateEquipamentoSubmit(fields, opts) {
    opts = opts || {};
    const serialCheck = validateSerialFortinetFormat(fields.serial, {
      obrigatorio: opts.obrigatorio !== false,
      exigePadrao: opts.exigePadrao !== false,
    });
    if (!serialCheck.valid) {
      return { valid: false, message: serialCheck.message, serial: serialCheck.value };
    }
    if (serialCheck.state === "warn" && opts.blockWarn) {
      return { valid: false, message: serialCheck.message, serial: serialCheck.value };
    }
    const versao = stripAllSpaces(fields.versao || "");
    if (versao && /\s/.test(String(fields.versao || ""))) {
      return {
        valid: false,
        message: "Versão do equipamento não pode conter espaços.",
        serial: serialCheck.value,
      };
    }
    return {
      valid: true,
      message: "",
      serial: serialCheck.value,
      versao: versao,
      state: serialCheck.state,
    };
  }

  function ensureLiveHint(el, hintId) {
    if (!el) return null;
    if (hintId) {
      const byId = document.getElementById(hintId);
      if (byId) return byId;
    }
    let hint = el.parentNode && el.parentNode.querySelector("small.prodesp-field-live-hint, .form-text[data-live-hint]");
    if (!hint && el.parentNode) {
      hint = document.createElement("small");
      hint.className = "prodesp-field-live-hint form-text";
      hint.setAttribute("data-live-hint", "1");
      el.parentNode.appendChild(hint);
    }
    return hint;
  }

  function paintSerialFortinetField(serialEl, hintEl, opts) {
    injectCss();
    const check = validateSerialFortinetFormat(serialEl ? serialEl.value : "", opts || {});
    const hint = hintEl || ensureLiveHint(serialEl);
    if (!serialEl) return check;
    if (check.state === "ok") {
      paintFormatState(serialEl, "prodesp-field-state-ok");
      setHint(hint, check.message, "ok");
    } else if (check.state === "warn") {
      paintFormatState(serialEl, "prodesp-field-state-warn");
      setHint(hint, check.message, "warn");
    } else if (check.state === "empty" || check.state === "invalid") {
      paintFormatState(serialEl, "prodesp-field-state-empty");
      setHint(hint, check.message, check.state === "empty" ? "empty" : "invalid");
    } else {
      clearFieldStates(serialEl);
      setHint(hint, "", "");
    }
    return check;
  }

  /**
   * Bind serial Fortinet + hint visual.
   * opts: { hintId, obrigatorio, exigePadrao, onAfter, skipInitialPaint }
   * skipInitialPaint: útil em modais admin (campo vazio no DOM escondido não deve ficar vermelho
   * até o fillForm; use refresh/paint após carregar dados).
   */
  function bindSerialFortinetInput(serialEl, opts) {
    serialEl = resolveEl(serialEl);
    if (!serialEl) return null;
    /* Rebind: devolver controller da instância já ligada (admin fillForm depende de .refresh). */
    if (serialEl.dataset.prodespSerialBound === "1" && serialEl._prodespSerialCtrl) {
      return serialEl._prodespSerialCtrl;
    }
    if (serialEl.dataset.prodespSerialBound === "1") return null;
    serialEl.dataset.prodespSerialBound = "1";
    injectCss();
    opts = opts || {};
    const hint = ensureLiveHint(serialEl, opts.hintId);
    bindNoWhitespaceInput(serialEl, {
      onAfter: function () {
        paintSerialFortinetField(serialEl, hint, opts);
        if (opts.onAfter) opts.onAfter(serialEl);
      },
    });
    ["input", "change", "blur"].forEach(function (ev) {
      serialEl.addEventListener(ev, function () {
        paintSerialFortinetField(serialEl, hint, opts);
      });
    });
    if (!opts.skipInitialPaint) {
      paintSerialFortinetField(serialEl, hint, opts);
    }
    const ctrl = {
      refresh: function () {
        return paintSerialFortinetField(serialEl, hint, opts);
      },
      validate: function () {
        return validateSerialFortinetFormat(serialEl.value, opts);
      },
    };
    serialEl._prodespSerialCtrl = ctrl;
    return ctrl;
  }

  function paintLinkFormatField(el, kind, operadora, value) {
    if (!el) return;
    injectCss();
    const hint = ensureLiveHint(el);
    const snap = {
      operadora: operadora,
      designador: kind === "designador" ? value : "",
      idVgr: kind === "id_vgr" ? value : "",
    };
    if (kind === "designador" && !isVivoOperadora(operadora)) {
      clearFieldStates(el);
      setHint(hint, "", "");
      return;
    }
    if (!String(value || "").trim()) {
      clearFieldStates(el);
      setHint(hint, "", "");
      return;
    }
    const fmt = validateLinkFormatFields(snap);
    if (!fmt.valid) {
      paintFormatState(el, "prodesp-field-state-empty");
      setHint(hint, fmt.message, "invalid");
    } else {
      paintFormatState(el, "prodesp-field-state-ok");
      setHint(hint, kind === "designador" ? "Designador no padrão VIVO." : "ID VGR no padrão.", "ok");
    }
  }

  /**
   * Admin Links: formato + unicidade remota com highlight nos campos.
   * opts: { getIdUnidade, getLinkId, fields: { tipo, operadora, designador, idVgr, wan, gw, ... els } }
   */
  function initAdminLinkFormValidation(opts) {
    opts = opts || {};
    const f = opts.fields || {};
    injectCss();
    let timer = null;
    let reqSeq = 0;

    function readSnap() {
      const val = function (el) {
        return el ? String(el.value || "").trim() : "";
      };
      return {
        id: opts.getLinkId ? opts.getLinkId() : "",
        id_unidade: opts.getIdUnidade ? opts.getIdUnidade() : "",
        tipo: val(f.tipo),
        operadora: val(f.operadora).toUpperCase(),
        designador: sanitizeLinkPastedText(val(f.designador)),
        id_vgr: sanitizeLinkPastedText(val(f.idVgr)),
        wan: sanitizePlainIpv4(val(f.wan)),
        gw: sanitizePlainIpv4(val(f.gw)),
      };
    }

    function paintLocal() {
      const snap = readSnap();
      paintLinkFormatField(f.designador, "designador", snap.operadora, snap.designador);
      paintLinkFormatField(f.idVgr, "id_vgr", snap.operadora, snap.id_vgr);
      if (f.wan && f.gw) {
        const pair = validateLinkPair(snap.wan, snap.gw, {
          label: "Link",
          checkStaticBlock: String(snap.tipo).toUpperCase() === "STATIC",
        });
        const wanHint = ensureLiveHint(f.wan);
        const gwHint = ensureLiveHint(f.gw);
        if (!pair.valid && (snap.wan || snap.gw)) {
          paintFormatState(f.wan, "prodesp-field-state-empty");
          paintFormatState(f.gw, "prodesp-field-state-empty");
          setHint(wanHint, pair.message, "invalid");
          setHint(gwHint, pair.message, "invalid");
        } else if (snap.wan && snap.gw) {
          paintFormatState(f.wan, "prodesp-field-state-ok");
          paintFormatState(f.gw, "prodesp-field-state-ok");
          setHint(wanHint, "IP WAN e Gateway ok.", "ok");
          setHint(gwHint, "", "");
        } else if (!snap.wan && !snap.gw) {
          clearFieldStates(f.wan);
          clearFieldStates(f.gw);
          setHint(wanHint, "", "");
          setHint(gwHint, "", "");
        }
      }
      /* Mesma regra VIVO (mascara/GW) de Blueprint/Atendimentos. */
      if (f.wan && f.gw && f.mascara && isVivoOperadora(snap.operadora)) {
        paintVivoLinkCompliance(f.wan, f.mascara, f.gw, snap.operadora, {
          label: "Link admin",
          linkTipo: snap.tipo || "STATIC",
          getLinkTipo: function () {
            return snap.tipo || "STATIC";
          },
          redundanteCritico: opts.redundanteCritico || false,
        });
      }
      if (f.velocidade) {
        applyVelocityMbpsToField(f.velocidade, true);
      }
    }

    function clearUniq() {
      [f.designador, f.idVgr, f.wan, f.gw].forEach(function (el) {
        if (!el) return;
        el.removeAttribute("data-prodesp-uniq");
      });
    }

    function paintUniq(msgs) {
      clearUniq();
      const list = msgs || [];
      list.forEach(function (msg) {
        const m = String(msg || "");
        const mark = function (el) {
          if (!el) return;
          el.setAttribute("data-prodesp-uniq", "1");
          clearFieldStates(el);
          el.classList.add("prodesp-field-state-empty");
          el.classList.add("is-invalid");
          setHint(ensureLiveHint(el), m, "invalid");
        };
        if (/Designador/i.test(m)) mark(f.designador);
        if (/ID VGR/i.test(m)) mark(f.idVgr);
        if (/IP WAN/i.test(m)) mark(f.wan);
        if (/IP Gateway|Gateway/i.test(m)) mark(f.gw);
      });
    }

    function runRemote() {
      paintLocal();
      const snap = readSnap();
      if (!snap.designador && !snap.id_vgr && !snap.wan && !snap.gw) return;
      const seq = ++reqSeq;
      const payload = {
        id_unidade: snap.id_unidade || "",
        links: [
          {
            id: snap.id || null,
            id_link: snap.id || null,
            tipo_links: snap.tipo,
            operadora_links: snap.operadora,
            designador_links: snap.designador,
            id_vgr_links: snap.id_vgr,
            ip_wan_links: snap.wan,
            ip_gateway_links: snap.gw,
          },
        ],
      };
      fetch("/prodesp/api/check-uniqueness", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (seq !== reqSeq) return;
          if (data && data.ok === false) {
            paintUniq(data.errors && data.errors.length ? data.errors : [data.message]);
          } else {
            clearUniq();
            paintLocal();
          }
        })
        .catch(function () {
          /* pré-check opcional */
        });
    }

    function schedule() {
      paintLocal();
      if (timer) clearTimeout(timer);
      timer = setTimeout(runRemote, 450);
    }

    [
      f.tipo,
      f.operadora,
      f.designador,
      f.idVgr,
      f.wan,
      f.gw,
      f.mascara,
      f.velocidade,
    ].forEach(function (el) {
      if (!el) return;
      ["input", "change"].forEach(function (ev) {
        el.addEventListener(ev, schedule);
      });
    });
    paintLocal();
    return { refresh: schedule, paintLocal: paintLocal, runRemote: runRemote };
  }

  global.ProdespLiveValidation = {
    injectCss,
    bindNoWhitespaceInput,
    bindPlainIpv4Input,
    bindTicketNocInput,
    sanitizePlainIpv4,
    sanitizeTicketNoc,
    validateTicketNocFormat,
    initTicketNocFields,
    stripAllSpaces,
    sanitizeLinkPastedText,
    scheduleAfterPaste,
    initLinkPair,
    initLoopbackTriplet,
    initBlueprintForm,
    validateLinkPair,
    validateLoopbackTriplet,
    validatePlainIpv4Field,
    collectBlueprintLinkErrors,
    collectAndPaintBlueprintUnitErrors,
    validateBlueprintForm,
    paintBlueprintServerPendencias,
    mapBlueprintPendenciasToMarks,
    paintRequiredTextField,
    paintCidrIpField,
    validateCidrIpValue,
    paintCoordinateField,
    validateCoordinateValue,
    paintVelocityRequiredField,
    bindBlueprintRequiredLiveFields,
    paintBlueprintInitialState,
    detectLocalBlueprintUniqueness,
    paintBlueprintUniquenessMarks,
    clearBlueprintUniquenessMarks,
    initBlueprintUniquenessWatch,
    isVivoOperadora,
    appliesRedundanteCritico,
    computeWanFromRedundanteBase,
    initRedundanteCriticoMplsVivo,
    deriveVivoLinkFields,
    validateVivoLinkCompliance,
    paintVivoLinkCompliance,
    validateVivoBlueprintLinks,
    applyVivoLinkFields,
    initVivoLinkAutoFill,
    applyVivoBlueprintLinks,
    syncLoopbacksFromPrefilled,
    refreshFormAfterDataLoad,
    setInputValueSilent,
    initAtendimentoLinkForm,
    syncAtendimentoLinkIdVgrVisibility,
    initInlineAtendimentoLinkRow,
    validateAtendimentoLinkSubmit,
    validateAtendimentoLinkRequired,
    validateLinkFormatFields,
    linkLabelFromTipoDesignador,
    normalizeSerialFortinet,
    serialFortinetValido,
    validateSerialFortinetFormat,
    validateEquipamentoSubmit,
    paintSerialFortinetField,
    bindSerialFortinetInput,
    initAdminLinkFormValidation,
    LOOPBACK_PREFIX,
    sanitizeVelocityMbpsDigits,
    normalizeVelocityMbps,
    bindVelocityMbpsInput,
    bindAllVelocityMbpsInputs,
    applyVelocityMbpsToField,
  };
})(typeof window !== "undefined" ? window : globalThis);
