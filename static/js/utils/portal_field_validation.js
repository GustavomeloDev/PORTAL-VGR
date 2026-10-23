/**
 * Núcleo compartilhado de validação de campos (espelho leve do core Python).
 * Uso: PortalFieldValidation.validateIpv4(...) / sanitizePastedText(...)
 */
(function (global) {
  "use strict";

  var PASTE_INVISIBLE = /[\u200B-\u200D\uFEFF\u00AD\u2060\u00A0\u202F\u2007]/g;
  var EDGE_QUOTES = /^['"\u2018\u2019\u201c\u201d]+|['"\u2018\u2019\u201c\u201d]+$/g;
  var IPV4_OCTET = "(?:25[0-5]|2[0-4]\\d|1?\\d?\\d)";
  var IPV4_RE = new RegExp("^" + IPV4_OCTET + "(?:\\." + IPV4_OCTET + "){3}$");
  var CIDR_RE = new RegExp(
    "^" + IPV4_OCTET + "(?:\\." + IPV4_OCTET + "){3}/(?:3[0-2]|[12]?\\d)$"
  );
  var TICKET_NOC_RE = /^1\d{6}$/;
  var FORTINET_MODELS = [
    "900G",
    "400F",
    "200F",
    "120G",
    "100F",
    "90G",
    "80F",
    "70F",
    "60F",
    "40F",
  ];
  var FORTINET_MODEL_LABELS = {
    "900G": "FortiGate 900G",
    "400F": "FortiGate 400F",
    "200F": "FortiGate 200F",
    "120G": "FortiGate 120G",
    "100F": "FortiGate 100F",
    "90G": "FortiGate 90G",
    "80F": "FortiGate 80F",
    "70F": "FortiGate 70F",
    "60F": "FortiGate 60F",
    "40F": "FortiGate 40F",
  };
  var FAKE_SERIALS = {
    "123": 1,
    "1234": 1,
    TEST: 1,
    TESTE: 1,
    FGT40F: 1,
    FGT60F: 1,
  };

  function sanitizePastedText(val) {
    var s = String(val == null ? "" : val);
    if (!s) return "";
    s = s.replace(PASTE_INVISIBLE, "").replace(/\s+/g, "");
    for (var i = 0; i < 3; i++) {
      var n = s.replace(EDGE_QUOTES, "");
      if (n === s) break;
      s = n;
    }
    return s;
  }

  function normalizeIpText(val) {
    return String(val == null ? "" : val)
      .trim()
      .replace(/\s+/g, "")
      .replace(/,/g, ".");
  }

  function canonicalizeIpv4(val) {
    var s = normalizeIpText(val);
    if (!s) return "";
    if (s.indexOf("/") >= 0) s = s.split("/")[0];
    s = s.replace(/[^0-9.]/g, "");
    var parts = s.split(".");
    if (parts.length !== 4 || parts.some(function (p) { return p === ""; })) return s;
    var nums = [];
    for (var i = 0; i < 4; i++) {
      if (!/^\d+$/.test(parts[i])) return s;
      var n = parseInt(parts[i], 10);
      if (n > 255) return s;
      nums.push(n);
    }
    return nums.join(".");
  }

  function isValidIpv4(val) {
    var s = normalizeIpText(val);
    return !!s && IPV4_RE.test(s);
  }

  function isValidIpv4Cidr(val) {
    var s = normalizeIpText(val);
    return !!s && CIDR_RE.test(s);
  }

  function validateIpv4(val, opts) {
    opts = opts || {};
    var label = opts.label || "IP";
    var s = opts.canonicalize ? canonicalizeIpv4(val) : normalizeIpText(val);
    if (!s) {
      return opts.obrigatorio ? label + " é obrigatório." : null;
    }
    if (opts.allowCidr) {
      if (isValidIpv4(s) || isValidIpv4Cidr(s)) return null;
      return label + " inválido. Use IPv4 ou CIDR.";
    }
    if (isValidIpv4(s)) return null;
    if (s.indexOf("/") >= 0) return label + " deve ser IPv4 sem CIDR.";
    return label + " inválido.";
  }

  function wanEqualsGateway(wan, gw) {
    var w = normalizeIpText(wan).split("/")[0];
    var g = normalizeIpText(gw).split("/")[0];
    return !!w && !!g && w === g;
  }

  function normalizeSerial(val) {
    return String(val == null ? "" : val)
      .trim()
      .replace(/[\s-]+/g, "")
      .toUpperCase();
  }

  function serialFortinetValido(val) {
    var s = normalizeSerial(val);
    if (!s || FAKE_SERIALS[s]) return false;
    if (s.indexOf("XXX") >= 0) return false;
    if (/^\d+$/.test(s) && s.length <= 8) return false;
    var alt = FORTINET_MODELS.join("|");
    var re = new RegExp("^(?:FGT|FG)(?:" + alt + ")TK[A-Z0-9]{8}$", "i");
    return re.test(s);
  }

  function validateSerialFortinet(val, opts) {
    opts = opts || {};
    var s = normalizeSerial(val);
    if (!s) {
      return opts.obrigatorio
        ? "Cadastre o número de série real do FortiGate."
        : null;
    }
    if (serialFortinetValido(s)) return null;
    return "Número de série Fortinet inválido ou provisório.";
  }

  function isFortinetFamily(vendor, modelo) {
    var blob = String(vendor || "") + " " + String(modelo || "");
    blob = blob.toLowerCase();
    return (
      blob.indexOf("fortinet") >= 0 ||
      blob.indexOf("fortigate") >= 0 ||
      blob.indexOf("forti-gate") >= 0
    );
  }

  function fortinetModeloFragment(raw) {
    var compact = String(raw == null ? "" : raw)
      .trim()
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, "");
    if (!compact) return "";
    for (var i = 0; i < FORTINET_MODELS.length; i++) {
      if (compact.indexOf(FORTINET_MODELS[i]) >= 0) return FORTINET_MODELS[i];
    }
    return "";
  }

  function normalizeModeloFortigate(raw) {
    var frag = fortinetModeloFragment(raw);
    if (frag) return FORTINET_MODEL_LABELS[frag] || "FortiGate " + frag;
    return String(raw == null ? "" : raw).trim();
  }

  function inferModeloFromSerialStrict(serial) {
    var s = normalizeSerial(serial);
    if (!s) return "";
    for (var i = 0; i < FORTINET_MODELS.length; i++) {
      var frag = FORTINET_MODELS[i];
      if (s.indexOf(frag) >= 0) return FORTINET_MODEL_LABELS[frag] || "FortiGate " + frag;
    }
    return "";
  }

  function inferModeloFromSerial(serial) {
    return inferModeloFromSerialStrict(serial) || "FortiGate 40F";
  }

  function serialFortinetLiveState(val, opts) {
    opts = opts || {};
    var s = normalizeSerial(val);
    if (!s) {
      return opts.obrigatorio
        ? { state: "warn", message: "Serial Fortinet pendente (padrão FGT40FTK… / FG120GTK…)." }
        : { state: "", message: "" };
    }
    if (serialFortinetValido(s)) {
      return { state: "ok", message: "Serial no padrão Fortinet." };
    }
    if (/^FG/i.test(s) && s.length < 16) {
      return {
        state: "warn",
        message: "Serial Fortinet incompleto (16 caracteres, ex.: FGT40FTK2409D6QK).",
      };
    }
    return {
      state: "error",
      message: "Serial Fortinet inválido ou provisório (FGT40FTK… / FG120GTK…).",
    };
  }

  function resolveEl(ref) {
    if (!ref) return null;
    if (typeof ref === "string") return document.getElementById(ref);
    return ref;
  }

  function bindModeloLockedFromSerial(serialRef, modeloRef, opts) {
    opts = opts || {};
    var serialEl = resolveEl(serialRef);
    var modeloEl = resolveEl(modeloRef);
    if (!serialEl || !modeloEl) return { refresh: function () {} };
    if (modeloEl.dataset.portalModeloBound === "1") {
      return { refresh: function () {} };
    }
    modeloEl.dataset.portalModeloBound = "1";

    function isSelect() {
      return modeloEl.tagName === "SELECT";
    }

    function ensureOption(val) {
      if (!val || !isSelect()) return;
      for (var i = 0; i < modeloEl.options.length; i++) {
        if (modeloEl.options[i].value === val) return;
      }
      modeloEl.add(new Option(val, val));
    }

    function fillOfficialOptions() {
      if (!isSelect()) return;
      FORTINET_MODELS.forEach(function (frag) {
        ensureOption(FORTINET_MODEL_LABELS[frag]);
      });
    }

    function setModeloValue(val) {
      if (!val) return;
      if (isSelect()) ensureOption(val);
      modeloEl.value = val;
    }

    function applyLock(lock) {
      if (isSelect()) {
        modeloEl.disabled = !!lock;
      } else {
        modeloEl.readOnly = !!lock;
      }
      modeloEl.classList.toggle("read-only-field", !!lock);
    }

    function currentModelo() {
      return normalizeModeloFortigate(modeloEl.value);
    }

    function refresh() {
      var s = normalizeSerial(serialEl.value);
      if (serialEl.value !== s) serialEl.value = s;
      var inferred = inferModeloFromSerialStrict(s);
      var current = currentModelo();
      fillOfficialOptions();

      if (inferred) {
        if (!current || current === inferred) {
          setModeloValue(inferred);
          applyLock(true);
          setLiveFieldState(modeloEl, "ok", "Modelo mapeado do serial (somente leitura).");
        } else {
          ensureOption(current);
          ensureOption(inferred);
          applyLock(false);
          setLiveFieldState(
            modeloEl,
            "warn",
            "Modelo diverge do serial (" + inferred + "). Corrija pela lista oficial."
          );
        }
      } else {
        applyLock(false);
        if (s) {
          setLiveFieldState(
            modeloEl,
            "warn",
            "Serial sem mapeamento conhecido — selecione um modelo da lista oficial."
          );
        } else if (current) {
          setLiveFieldState(modeloEl, "ok", "Modelo da lista oficial.");
        } else {
          setLiveFieldState(modeloEl, "", "");
        }
      }

      var serialState = serialFortinetLiveState(s, { obrigatorio: opts.obrigatorio !== false });
      setLiveFieldState(serialEl, serialState.state, serialState.message);
    }

    fillOfficialOptions();
    if (modeloEl.value) {
      var official = normalizeModeloFortigate(modeloEl.value);
      if (official && official !== modeloEl.value) {
        var alias = modeloEl.value;
        if (isSelect()) {
          ensureOption(official);
          modeloEl.value = official;
          for (var i = modeloEl.options.length - 1; i >= 0; i--) {
            if (modeloEl.options[i].value === alias) modeloEl.remove(i);
          }
        } else {
          modeloEl.value = official;
        }
      }
    }

    var form = serialEl.form || modeloEl.form;
    if (form && !form.dataset.portalModeloSubmitBound) {
      form.dataset.portalModeloSubmitBound = "1";
      form.addEventListener(
        "submit",
        function () {
          if (isSelect() && modeloEl.disabled) modeloEl.disabled = false;
        },
        true
      );
    }

    bindSanitizeInput(serialEl, normalizeSerial);
    serialEl.addEventListener("input", refresh);
    serialEl.addEventListener("change", refresh);
    serialEl.addEventListener("blur", refresh);
    modeloEl.addEventListener("change", function () {
      var inferred = inferModeloFromSerialStrict(serialEl.value);
      var current = currentModelo();
      if (inferred && current === inferred) {
        setModeloValue(inferred);
        applyLock(true);
        setLiveFieldState(modeloEl, "ok", "Modelo mapeado do serial (somente leitura).");
      }
    });
    refresh();
    return { refresh: refresh };
  }

  function validateTicketNoc(val, opts) {
    opts = opts || {};
    var s = String(val == null ? "" : val)
      .trim()
      .replace(/\s+/g, "");
    if (!s) {
      return opts.obrigatorio ? "Ticket NOC é obrigatório." : null;
    }
    if (!TICKET_NOC_RE.test(s)) {
      return "Ticket NOC inválido (7 dígitos começando em 1).";
    }
    return null;
  }

  function isDigitsMinLen(val, minDigits) {
    var s = sanitizePastedText(val);
    return !!s && /^\d+$/.test(s) && s.length >= (minDigits || 0);
  }

  var ID_VGR_LINK_MIN = 7;
  var DESIGNADOR_VIVO_MIN = 15;
  var VIVO_MASK_MPLS = "255.255.255.248";
  var VIVO_MASK_EVEN = "255.255.255.252";
  var VIVO_MASK_ODD = "255.255.255.254";

  function isVivoOperadora(val) {
    return String(val || "").trim().toUpperCase() === "VIVO";
  }

  function validateIdVgrLinkFormat(val, opts) {
    opts = opts || {};
    var s = sanitizePastedText(val);
    if (!s) {
      return opts.obrigatorio ? "ID VGR do link é obrigatório." : null;
    }
    if (!/^\d+$/.test(s) || s.length < ID_VGR_LINK_MIN) {
      return (
        "ID VGR do link inválido: apenas dígitos e no mínimo " +
        ID_VGR_LINK_MIN +
        " caracteres."
      );
    }
    return null;
  }

  function idVgrLinkLiveState(val, opts) {
    opts = opts || {};
    var s = sanitizePastedText(val);
    if (!s) {
      return opts.obrigatorio
        ? { state: "warn", message: "ID VGR do link pendente (mínimo 7 dígitos)." }
        : { state: "", message: "" };
    }
    if (!/^\d+$/.test(s)) {
      return { state: "error", message: "ID VGR do link: use apenas dígitos." };
    }
    if (s.length < ID_VGR_LINK_MIN) {
      return {
        state: "warn",
        message: "ID VGR pendente: faltam dígitos (mínimo " + ID_VGR_LINK_MIN + ").",
      };
    }
    return { state: "ok", message: "ID VGR no padrão." };
  }

  function validateDesignadorVivoFormat(val, operadora, opts) {
    opts = opts || {};
    if (!isVivoOperadora(operadora)) return null;
    var s = sanitizePastedText(val);
    if (!s) {
      return opts.obrigatorio ? "Designador VIVO (LP) é obrigatório." : null;
    }
    if (!/^\d+$/.test(s) || s.length < DESIGNADOR_VIVO_MIN) {
      return (
        "Designador VIVO (LP) inválido: apenas dígitos e no mínimo " +
        DESIGNADOR_VIVO_MIN +
        " caracteres."
      );
    }
    return null;
  }

  function designadorVivoLiveState(val, operadora, opts) {
    opts = opts || {};
    if (!isVivoOperadora(operadora)) return { state: "", message: "" };
    var s = sanitizePastedText(val);
    if (!s) {
      return {
        state: "warn",
        message: "Designador (LP) VIVO pendente: 15 dígitos.",
      };
    }
    if (!/^\d+$/.test(s)) {
      return { state: "error", message: "Designador VIVO (LP): use apenas dígitos." };
    }
    if (s.length < DESIGNADOR_VIVO_MIN) {
      return {
        state: "warn",
        message:
          "LP pendente: faltam dígitos (mínimo " + DESIGNADOR_VIVO_MIN + ").",
      };
    }
    return { state: "ok", message: "Designador (LP) no padrão VIVO." };
  }

  function ipv4LiveState(val, label, opts) {
    opts = opts || {};
    var s = opts.canonicalize ? canonicalizeIpv4(val) : normalizeIpText(val);
    if (!s) {
      if (opts.obrigatorio) {
        return { state: "error", message: (label || "IP") + " é obrigatório." };
      }
      return { state: "", message: "" };
    }
    var err = validateIpv4(s, { label: label || "IP", canonicalize: !!opts.canonicalize });
    if (!err) return { state: "ok", message: (label || "IP") + " válido." };
    if ((s.match(/\./g) || []).length < 3) {
      return { state: "warn", message: (label || "IP") + " incompleto." };
    }
    return { state: "error", message: err };
  }

  function coordinateLiveState(val, label, opts) {
    opts = opts || {};
    var field = label || "Coordenada";
    var s = String(val == null ? "" : val).trim();
    if (!s) {
      return opts.obrigatorio
        ? { state: "error", message: field + " é obrigatória." }
        : { state: "", message: "" };
    }
    if (s.length > 20) {
      return {
        state: "error",
        message: "O campo «" + field + "» aceita no máximo 20 caracteres.",
      };
    }
    var n = s.replace(/\s+/g, "").replace(",", ".");
    if (!/^-?\d+(\.\d+)?$/.test(n)) {
      return {
        state: "error",
        message: "O campo «" + field + "» deve ser um número decimal válido.",
      };
    }
    return { state: "ok", message: field + " válida." };
  }

  function parseIpv4Octets(val) {
    var s = canonicalizeIpv4(val);
    var m = s.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
    if (!m) return null;
    var parts = [+m[1], +m[2], +m[3], +m[4]];
    if (parts.some(function (n) { return n < 0 || n > 255; })) return null;
    return parts;
  }

  function ipv4ToUint(parts) {
    return (
      ((parts[0] << 24) >>> 0) +
      (parts[1] << 16) +
      (parts[2] << 8) +
      parts[3]
    ) >>> 0;
  }

  function isContiguousNetmask(parts) {
    if (!parts) return false;
    var n = ipv4ToUint(parts);
    var seenZero = false;
    for (var i = 31; i >= 0; i--) {
      var bit = (n >>> i) & 1;
      if (bit === 1) {
        if (seenZero) return false;
      } else {
        seenZero = true;
      }
    }
    return true;
  }

  function prefixLenFromMask(parts) {
    if (!parts || !isContiguousNetmask(parts)) return null;
    var n = ipv4ToUint(parts);
    var bits = 0;
    for (var i = 31; i >= 0; i--) {
      if ((n >>> i) & 1) bits++;
      else break;
    }
    return bits;
  }

  function networkPartsFrom(ipParts, maskParts) {
    return [
      ipParts[0] & maskParts[0],
      ipParts[1] & maskParts[1],
      ipParts[2] & maskParts[2],
      ipParts[3] & maskParts[3],
    ];
  }

  function ipv4NetworkAddress(ip, mask) {
    var a = parseIpv4Octets(ip);
    var m = parseIpv4Octets(mask);
    if (!a || !m || !isContiguousNetmask(m)) return null;
    return networkPartsFrom(a, m).join(".");
  }

  function validateIpMaskGroup(opts) {
    opts = opts || {};
    var label = opts.label || "Link";
    var ip = canonicalizeIpv4(opts.ip);
    var mask = canonicalizeIpv4(opts.mascara);
    if (!ip || !mask) return null;
    if (!isValidIpv4(ip) || !isValidIpv4(mask)) return null;
    var ipParts = parseIpv4Octets(ip);
    var maskParts = parseIpv4Octets(mask);
    if (!ipParts || !maskParts || !isContiguousNetmask(maskParts)) {
      return (
        label +
        ": máscara inválida (não é uma máscara de rede). Use, por exemplo, 255.255.255.0."
      );
    }
    var netParts = networkPartsFrom(ipParts, maskParts);
    var net = netParts.join(".");
    var plen = prefixLenFromMask(maskParts);
    var ipInt = ipv4ToUint(ipParts);
    var netInt = ipv4ToUint(netParts);
    var hostMask = (~ipv4ToUint(maskParts)) >>> 0;
    var bcastInt = (netInt + hostMask) >>> 0;
    if (plen !== null && plen < 31) {
      if (ipInt === netInt) {
        return (
          label +
          ": IP " +
          ip +
          " é o endereço de rede " +
          net +
          "/" +
          plen +
          ". Use um IP de host."
        );
      }
      if (ipInt === bcastInt) {
        return label + ": IP " + ip + " é o endereço de broadcast. Use um IP de host.";
      }
    }
    var gw = canonicalizeIpv4(opts.gateway);
    if (gw && isValidIpv4(gw)) {
      var gwParts = parseIpv4Octets(gw);
      var gwNet = networkPartsFrom(gwParts, maskParts).join(".");
      if (gwNet !== net) {
        return (
          label +
          ": Gateway " +
          gw +
          " não pertence à rede " +
          net +
          "/" +
          plen +
          " (máscara " +
          mask +
          ")."
        );
      }
      var gwInt = ipv4ToUint(gwParts);
      if (plen !== null && plen < 31) {
        if (gwInt === netInt) {
          return label + ": Gateway não pode ser o endereço de rede " + net + ".";
        }
        if (gwInt === bcastInt) {
          return label + ": Gateway não pode ser o endereço de broadcast.";
        }
      }
    }
    var subRaw = String(opts.subrede == null ? "" : opts.subrede).trim();
    if (subRaw) {
      var subHost = canonicalizeIpv4(subRaw);
      if (isValidIpv4(subHost) && subHost !== net) {
        return (
          label +
          ": subrede " +
          subHost +
          " não corresponde à rede de " +
          ip +
          "/" +
          mask +
          " (esperado " +
          net +
          ")."
        );
      }
    }
    return null;
  }

  function maybeFillSubnetFromIpMask(subnetEl, ip, mask) {
    if (!subnetEl) return false;
    if (String(subnetEl.value || "").trim()) return false;
    var net = ipv4NetworkAddress(ip, mask);
    if (!net) return false;
    subnetEl.value = net;
    return true;
  }

  function deriveVivoMaskFromWan(ipWan, modo, opts) {
    opts = opts || {};
    var parts = parseIpv4Octets(ipWan);
    if (!parts) return null;
    var mplsUsa29 = opts.mplsUsa29 !== false;
    if (mplsUsa29 && normalizeWanModo(modo) === "MPLS") return VIVO_MASK_MPLS;
    return parts[3] % 2 === 0 ? VIVO_MASK_EVEN : VIVO_MASK_ODD;
  }

  function deriveVivoGatewayFromWan(ipWan) {
    var parts = parseIpv4Octets(ipWan);
    if (!parts) return null;
    var n = parts[0] * 16777216 + parts[1] * 65536 + parts[2] * 256 + parts[3];
    if (n < 1) return null;
    n -= 1;
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

  function vivoMaskMessage(modo, expected) {
    if (normalizeWanModo(modo) === "MPLS" && expected === VIVO_MASK_MPLS) {
      return "VIVO + MPLS: máscara esperada " + VIVO_MASK_MPLS + " (/29).";
    }
    if (expected === VIVO_MASK_EVEN) {
      return "VIVO: último octeto par → máscara " + VIVO_MASK_EVEN + " (/30).";
    }
    return "VIVO: último octeto ímpar → máscara " + VIVO_MASK_ODD + " (/31).";
  }

  function collectVivoLinkPendencias(fields, opts) {
    opts = opts || {};
    fields = fields || {};
    if (!isVivoOperadora(fields.operadora)) return [];
    var out = [];
    var expectedMask = deriveVivoMaskFromWan(fields.ip, fields.modo, opts);
    var expectedGw = deriveVivoGatewayFromWan(fields.ip);
    var mask = normalizeIpText(fields.mascara);
    var gw = normalizeIpText(fields.gateway).split("/")[0];
    if (expectedMask) {
      if (!mask) out.push(vivoMaskMessage(fields.modo, expectedMask));
      else if (mask !== expectedMask) {
        out.push(vivoMaskMessage(fields.modo, expectedMask) + " Valor informado: " + mask + ".");
      }
    }
    if (expectedGw) {
      if (!gw) out.push("VIVO: gateway esperado " + expectedGw + " (IP WAN − 1).");
      else if (gw !== expectedGw) {
        out.push(
          "VIVO: gateway esperado " + expectedGw + " (IP WAN − 1). Valor informado: " + gw + "."
        );
      }
    }
    if (!sanitizePastedText(fields.designador)) {
      out.push("Designador (LP) VIVO pendente: 15 dígitos.");
    }
    return out;
  }

  var LIVE_STATE_CLASSES = [
    "portal-field-state-error",
    "portal-field-state-warn",
    "portal-field-state-ok",
    "invalid-field",
    "valid-field",
  ];

  function injectLiveCss() {
    if (document.getElementById("portal-live-validation-css")) return;
    var style = document.createElement("style");
    style.id = "portal-live-validation-css";
    style.textContent =
      ".portal-field-state-error{border-color:#dc3545!important;background-color:#fff5f5!important;box-shadow:0 0 0 0.15rem rgba(220,53,69,.2)}" +
      ".portal-field-state-warn{border-color:#ffc107!important;background-color:#fffbeb!important;box-shadow:0 0 0 0.15rem rgba(255,193,7,.25)}" +
      ".portal-field-state-ok{border-color:#198754!important;background-color:#f0fff4!important;box-shadow:0 0 0 0.15rem rgba(25,135,84,.2)}" +
      ".portal-field-live-hint{display:block;font-size:.75rem;margin-top:.25rem;min-height:1.1rem}" +
      ".portal-field-live-hint.is-error-hint{color:#dc3545}" +
      ".portal-field-live-hint.is-warn-hint{color:#b58100}" +
      ".portal-field-live-hint.is-ok-hint{color:#198754}";
    document.head.appendChild(style);
  }

  function ensureLiveHint(el, opts) {
    if (!el) return null;
    opts = opts || {};
    var anchor = opts.hintAfter || el;
    if (el._portalLiveHint && document.body.contains(el._portalLiveHint)) {
      if (el._portalLiveHint.previousElementSibling !== anchor) {
        anchor.insertAdjacentElement("afterend", el._portalLiveHint);
      }
      return el._portalLiveHint;
    }
    var next = anchor.nextElementSibling;
    if (next && next.classList.contains("portal-field-live-hint")) {
      el._portalLiveHint = next;
      return next;
    }
    var hint = document.createElement("small");
    hint.className = "portal-field-live-hint";
    anchor.insertAdjacentElement("afterend", hint);
    el._portalLiveHint = hint;
    return hint;
  }

  function setLiveFieldState(el, state, message, opts) {
    if (!el) return;
    injectLiveCss();
    LIVE_STATE_CLASSES.forEach(function (c) {
      el.classList.remove(c);
    });
    if (state === "error") el.classList.add("portal-field-state-error", "invalid-field");
    else if (state === "warn") el.classList.add("portal-field-state-warn");
    else if (state === "ok") el.classList.add("portal-field-state-ok", "valid-field");
    var hint = ensureLiveHint(el, opts);
    if (!hint) return;
    hint.textContent = message || "";
    hint.classList.remove("is-error-hint", "is-warn-hint", "is-ok-hint");
    if (state === "error") hint.classList.add("is-error-hint");
    else if (state === "warn") hint.classList.add("is-warn-hint");
    else if (state === "ok") hint.classList.add("is-ok-hint");
  }

  function bindSanitizeInput(el, cleaner) {
    if (!el || el.dataset.portalSanitizeBound === "1") return;
    el.dataset.portalSanitizeBound = "1";
    function apply() {
      var cleaned = cleaner(el.value);
      if (cleaned !== el.value) el.value = cleaned;
    }
    el.addEventListener("keydown", function (e) {
      if (e.key === " " || e.code === "Space") e.preventDefault();
    });
    el.addEventListener("paste", function (e) {
      e.preventDefault();
      var raw = (e.clipboardData || window.clipboardData).getData("text") || "";
      el.value = cleaner(raw);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    });
    el.addEventListener("input", apply);
  }

  var WAN_MODOS_COM_IP = { STATIC: true, MPLS: true };

  function normalizeWanModo(modo) {
    return String(modo == null ? "" : modo)
      .trim()
      .toUpperCase();
  }

  function wanGruposVisiveis(modo, opts) {
    opts = opts || {};
    var m = normalizeWanModo(modo);
    var vis = { comuns: true };
    if (!m) return vis;
    if (WAN_MODOS_COM_IP[m]) {
      vis.ip = true;
      vis.vlan_wan = true;
      if (!opts.idVgrSoVivo || String(opts.operadora || "").trim().toUpperCase() === "VIVO") {
        vis.id_vgr_link = true;
      }
    } else if (m === "PPPOE") {
      vis.pppoe = true;
    } else if (m === "DHCP") {
      vis.dhcp = true;
    }
    return vis;
  }

  function wanCampoVisivel(modo, grupo, opts) {
    return !!wanGruposVisiveis(modo, opts)[grupo];
  }

  function applyWanModoVisibility(rootEl, modo, opts) {
    if (!rootEl) return wanGruposVisiveis(modo, opts);
    var vis = wanGruposVisiveis(modo, opts);
    rootEl.querySelectorAll("[data-wan-grupo]").forEach(function (el) {
      var g = el.getAttribute("data-wan-grupo");
      var on = !!vis[g];
      el.classList.toggle("d-none", !on);
      el.hidden = !on;
    });
    return vis;
  }

  var OPERADORAS_PRINCIPAIS_SET = { VIVO: 1, CLARO: 1, TIM: 1, OI: 1 };
  var OPERADORA_SENTINEL_OUTROS = "OUTROS";

  function normalizeOperadora(val) {
    var s = String(val == null ? "" : val)
      .trim()
      .replace(/\s+/g, " ")
      .toUpperCase();
    if (!s || s === OPERADORA_SENTINEL_OUTROS) return "";
    return s.slice(0, 50);
  }

  function resolveOperadora(selectVal, outrosVal, fallback) {
    var sel = String(selectVal == null ? "" : selectVal)
      .trim()
      .replace(/\s+/g, " ")
      .toUpperCase();
    if (sel === OPERADORA_SENTINEL_OUTROS) return normalizeOperadora(outrosVal);
    if (OPERADORAS_PRINCIPAIS_SET[sel]) return sel;
    return normalizeOperadora(fallback || outrosVal || selectVal);
  }

  function bindOperadoraSelect(selectEl, outrosEl, hiddenEl, onChange) {
    if (!selectEl || selectEl.dataset.portalOperadoraBound === "1") return;
    selectEl.dataset.portalOperadoraBound = "1";

    function sync() {
      var sel = String(selectEl.value || "")
        .trim()
        .toUpperCase();
      var isOutros = sel === OPERADORA_SENTINEL_OUTROS;
      if (outrosEl) {
        outrosEl.classList.toggle("d-none", !isOutros);
        outrosEl.hidden = !isOutros;
        if (isOutros) {
          var up = String(outrosEl.value || "")
            .replace(/\s+/g, " ")
            .toUpperCase();
          if (up !== outrosEl.value) outrosEl.value = up;
        }
      }
      var resolved = resolveOperadora(sel, outrosEl && outrosEl.value);
      if (hiddenEl && hiddenEl.value !== resolved) {
        hiddenEl.value = resolved;
        hiddenEl.dispatchEvent(new Event("input", { bubbles: true }));
        hiddenEl.dispatchEvent(new Event("change", { bubbles: true }));
      }
      if (typeof onChange === "function") onChange(resolved);
    }

    selectEl.addEventListener("change", sync);
    if (outrosEl) {
      outrosEl.addEventListener("input", function () {
        var up = String(outrosEl.value || "")
          .replace(/\s+/g, " ")
          .toUpperCase();
        if (up !== outrosEl.value) outrosEl.value = up;
        sync();
      });
      outrosEl.addEventListener("blur", function () {
        outrosEl.value = normalizeOperadora(outrosEl.value);
        sync();
      });
    }
    sync();
  }

  function sanitizeVelocityDigits(val) {
    return String(val == null ? "" : val).replace(/\D/g, "");
  }

  function compactVelocityText(raw) {
    return String(raw == null ? "" : raw)
      .trim()
      .replace(/,/g, ".")
      .replace(/\s+/g, "")
      .toLowerCase();
  }

  function parseVelocityToMbps(val) {
    var raw = String(val == null ? "" : val).trim();
    if (!raw) return { value: "", source: "" };
    var compact = compactVelocityText(raw);
    var g = compact.match(/^(\d+(?:\.\d+)?)(?:gbps|gbit\/s|g)$/i);
    if (g) {
      var gb = Math.round(parseFloat(g[1]) * 1000);
      return gb > 0 ? { value: String(gb), source: "g" } : { value: "", source: "" };
    }
    var m = compact.match(/^(\d+(?:\.\d+)?)(?:mbps|mb\/s|mb|m)$/i);
    if (m) {
      var mb = Math.round(parseFloat(m[1]));
      return mb > 0 ? { value: String(mb), source: "m" } : { value: "", source: "" };
    }
    var digits = sanitizeVelocityDigits(raw);
    if (!digits) return { value: "", source: "" };
    var n = parseInt(digits, 10);
    if (!n) return { value: "", source: "" };
    if (n >= 100000 && n % 1000 === 0) n = Math.floor(n / 1000);
    else if (n >= 2000 && n % 1000 === 0) n = Math.floor(n / 1000);
    return { value: String(n), source: "plain" };
  }

  function formatVelocityMbpsMessage(mbps) {
    if (!mbps) return "";
    var n = parseInt(mbps, 10);
    if (n === 1000) return "1 Gbps (1000 Mbps).";
    if (n === 2500) return "2,5 Gbps (2500 Mbps).";
    if (n === 10000) return "10 Gbps (10000 Mbps).";
    return n + " Mbps.";
  }

  function normalizeVelocityMbps(val) {
    var raw = String(val == null ? "" : val).trim();
    if (!raw) return { value: "", adjusted: false, original: "", message: "" };
    var parsed = parseVelocityToMbps(raw);
    if (!parsed.value) return { value: "", adjusted: false, original: raw, message: "" };
    var digits = sanitizeVelocityDigits(raw);
    var adjusted = parsed.value !== digits;
    var message = formatVelocityMbpsMessage(parsed.value);
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

  function applyVelocityMbpsToField(el, afterNormalize) {
    if (!el) return null;
    var norm = normalizeVelocityMbps(el.value);
    if (norm.value && norm.value !== el.value) el.value = norm.value;
    else if (el.value && !norm.value) el.value = sanitizeVelocityDigits(el.value);
    if (norm.value) {
      setLiveFieldState(
        el,
        afterNormalize && norm.adjusted ? "warn" : "ok",
        norm.message
      );
    } else if (String(el.value || "").trim()) {
      setLiveFieldState(el, "error", "Velocidade: use apenas números (Mbps).");
    } else {
      setLiveFieldState(el, "", "");
    }
    return norm;
  }

  function bindVelocityMbpsInput(el) {
    if (!el || el.nodeName !== "INPUT" || el.dataset.portalVelocityBound === "1") return;
    el.dataset.portalVelocityBound = "1";
    el.setAttribute("autocomplete", "off");
    el.setAttribute("inputmode", "numeric");
    el.setAttribute("placeholder", el.getAttribute("placeholder") || "Mbps (somente números)");

    function onCommit() {
      applyVelocityMbpsToField(el, true);
    }

    el.addEventListener("keydown", function (e) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      var nav = ["Backspace", "Delete", "Tab", "ArrowLeft", "ArrowRight", "Home", "End", "Enter"];
      if (nav.indexOf(e.key) >= 0) return;
      if (!/^\d$/.test(e.key)) e.preventDefault();
    });
    el.addEventListener("paste", function (e) {
      e.preventDefault();
      var raw = (e.clipboardData || window.clipboardData).getData("text") || "";
      var norm = normalizeVelocityMbps(raw);
      el.value = norm.value || sanitizeVelocityDigits(raw);
      onCommit();
    });
    el.addEventListener("input", function () {
      var digits = sanitizeVelocityDigits(el.value);
      if (digits !== el.value) el.value = digits;
    });
    el.addEventListener("blur", onCommit);
    applyVelocityMbpsToField(el, true);
  }

  global.PortalFieldValidation = {
    sanitizePastedText: sanitizePastedText,
    normalizeIpText: normalizeIpText,
    canonicalizeIpv4: canonicalizeIpv4,
    isValidIpv4: isValidIpv4,
    isValidIpv4Cidr: isValidIpv4Cidr,
    validateIpv4: validateIpv4,
    wanEqualsGateway: wanEqualsGateway,
    normalizeSerial: normalizeSerial,
    serialFortinetValido: serialFortinetValido,
    validateSerialFortinet: validateSerialFortinet,
    serialFortinetLiveState: serialFortinetLiveState,
    isFortinetFamily: isFortinetFamily,
    FORTINET_MODELS: FORTINET_MODELS,
    FORTINET_MODEL_LABELS: FORTINET_MODEL_LABELS,
    fortinetModeloFragment: fortinetModeloFragment,
    normalizeModeloFortigate: normalizeModeloFortigate,
    inferModeloFromSerialStrict: inferModeloFromSerialStrict,
    inferModeloFromSerial: inferModeloFromSerial,
    bindModeloLockedFromSerial: bindModeloLockedFromSerial,
    validateTicketNoc: validateTicketNoc,
    isDigitsMinLen: isDigitsMinLen,
    isVivoOperadora: isVivoOperadora,
    validateIdVgrLinkFormat: validateIdVgrLinkFormat,
    validateDesignadorVivoFormat: validateDesignadorVivoFormat,
    idVgrLinkLiveState: idVgrLinkLiveState,
    designadorVivoLiveState: designadorVivoLiveState,
    ipv4LiveState: ipv4LiveState,
    coordinateLiveState: coordinateLiveState,
    ipv4NetworkAddress: ipv4NetworkAddress,
    validateIpMaskGroup: validateIpMaskGroup,
    maybeFillSubnetFromIpMask: maybeFillSubnetFromIpMask,
    deriveVivoMaskFromWan: deriveVivoMaskFromWan,
    deriveVivoGatewayFromWan: deriveVivoGatewayFromWan,
    collectVivoLinkPendencias: collectVivoLinkPendencias,
    setLiveFieldState: setLiveFieldState,
    bindSanitizeInput: bindSanitizeInput,
    normalizeWanModo: normalizeWanModo,
    wanGruposVisiveis: wanGruposVisiveis,
    wanCampoVisivel: wanCampoVisivel,
    applyWanModoVisibility: applyWanModoVisibility,
    OPERADORAS_PRINCIPAIS: ["VIVO", "CLARO", "TIM", "OI"],
    OPERADORA_SENTINEL_OUTROS: "OUTROS",
    normalizeOperadora: normalizeOperadora,
    resolveOperadora: resolveOperadora,
    bindOperadoraSelect: bindOperadoraSelect,
    normalizeVelocityMbps: normalizeVelocityMbps,
    bindVelocityMbpsInput: bindVelocityMbpsInput,
  };
})(window);
