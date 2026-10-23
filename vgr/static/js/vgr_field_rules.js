/**
 * VGR — regras de campo no navegador (espelho de vgr/vgr/cadastros/validators.py,
 * que por sua vez usa core/utils/*: network, text_ids, velocity, operadora,
 * link_required, link_vivo, coordinates, validators).
 *
 * Dependências (ordem de <script>):
 *   1. /core/static/js/utils/portal_field_validation.js  → window.PortalFieldValidation
 *   2. vgr_dt_common.js                                  → window.VgrDt (linkFieldVisibility)
 *   3. este arquivo                                      → window.VgrFieldRules
 *
 * O servidor continua sendo a fonte da verdade. Aqui: feedback ao digitar
 * (verde/amarelo/vermelho, mesmo CSS do PortalFieldValidation) e bloqueio
 * antes do POST/PUT com a MESMA mensagem que a API devolveria.
 */
(function (global) {
  "use strict";

  var PF = global.PortalFieldValidation;
  var V = global.VgrDt;
  if (!PF || !V) {
    console.warn("[VGR] VgrFieldRules requer PortalFieldValidation e VgrDt carregados antes.");
    return;
  }

  /* ------------------------------------------------------------------ */
  /* Helpers                                                              */
  /* ------------------------------------------------------------------ */

  function el(ref) {
    if (!ref) return null;
    return typeof ref === "string" ? document.getElementById(ref) : ref;
  }

  function val(ref) {
    var e = el(ref);
    return e ? String(e.value == null ? "" : e.value) : "";
  }

  function trim(v) {
    return String(v == null ? "" : v).trim();
  }

  function digits(v) {
    return String(v == null ? "" : v).replace(/\D+/g, "");
  }

  function isHidden(e) {
    return !e || e.hidden || !!e.closest(".d-none");
  }

  function setState(ref, state, message) {
    var e = el(ref);
    if (e) PF.setLiveFieldState(e, state || "", message || "");
  }

  /** Remove verde/amarelo/vermelho e textos de dica dentro de um container (reset de modal). */
  function clearStates(container) {
    var root = el(container);
    if (!root) return;
    root
      .querySelectorAll(".portal-field-state-error, .portal-field-state-warn, .portal-field-state-ok")
      .forEach(function (x) {
        PF.setLiveFieldState(x, "", "");
      });
    root.querySelectorAll(".portal-field-live-hint").forEach(function (h) {
      h.textContent = "";
      h.classList.remove("is-error-hint", "is-warn-hint", "is-ok-hint");
    });
  }

  /** Liga um calculador de estado {state, message} a input/blur/change. Idempotente. */
  function bindLive(ref, stateFn) {
    var e = el(ref);
    if (!e) return function () {};
    if (e.dataset.vgrLiveBound === "1" && e._vgrLiveRefresh) return e._vgrLiveRefresh;
    e.dataset.vgrLiveBound = "1";
    function refresh() {
      if (isHidden(e)) {
        setState(e, "", "");
        return;
      }
      var st = stateFn(e.value) || {};
      setState(e, st.state, st.message);
    }
    ["input", "blur", "change"].forEach(function (evt) {
      e.addEventListener(evt, refresh);
    });
    e._vgrLiveRefresh = refresh;
    return refresh;
  }

  /** Máscara de digitação (CNPJ/CEP/UF): reescreve o valor mantendo o cursor no fim. */
  function bindMask(ref, formatter) {
    var e = el(ref);
    if (!e || e.dataset.vgrMaskBound === "1") return;
    e.dataset.vgrMaskBound = "1";
    e.addEventListener("input", function () {
      var f = formatter(e.value);
      if (f !== e.value) e.value = f;
    });
  }

  /* ------------------------------------------------------------------ */
  /* CNPJ / CEP / UF / coordenadas (core.utils.validators / coordinates) */
  /* ------------------------------------------------------------------ */

  function cnpjValido(d) {
    if (!/^\d{14}$/.test(d) || /^(\d)\1{13}$/.test(d)) return false;
    function calc(base, pesos) {
      var t = 0;
      for (var i = 0; i < pesos.length; i++) t += Number(base[i]) * pesos[i];
      var r = t % 11;
      return r < 2 ? 0 : 11 - r;
    }
    var d1 = calc(d, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]);
    var d2 = calc(d, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]);
    return d.slice(12) === String(d1) + String(d2);
  }

  function formatCnpj(v) {
    var d = digits(v).slice(0, 14);
    var out = d.slice(0, 2);
    if (d.length > 2) out += "." + d.slice(2, 5);
    if (d.length > 5) out += "." + d.slice(5, 8);
    if (d.length > 8) out += "/" + d.slice(8, 12);
    if (d.length > 12) out += "-" + d.slice(12, 14);
    return out;
  }

  function validateCnpj(v) {
    var d = digits(v);
    if (!d) return null;
    if (d.length !== 14) return "CNPJ deve ter 14 dígitos.";
    if (!cnpjValido(d)) return "CNPJ inválido: dígitos verificadores não conferem.";
    return null;
  }

  function cnpjLiveState(v) {
    var d = digits(v);
    if (!d) return { state: "", message: "" };
    if (d.length < 14) return { state: "warn", message: "CNPJ incompleto (" + d.length + "/14 dígitos)." };
    var err = validateCnpj(v);
    return err ? { state: "error", message: err } : { state: "ok", message: "CNPJ válido." };
  }

  function formatCep(v) {
    var d = digits(v).slice(0, 8);
    return d.length > 5 ? d.slice(0, 5) + "-" + d.slice(5) : d;
  }

  function validateCep(v) {
    var d = digits(v);
    if (!d) return null;
    return d.length === 8 ? null : "CEP deve ter 8 dígitos.";
  }

  function cepLiveState(v) {
    var d = digits(v);
    if (!d) return { state: "", message: "" };
    if (d.length < 8) return { state: "warn", message: "CEP incompleto (" + d.length + "/8 dígitos)." };
    return { state: "ok", message: "CEP no formato 00000-000." };
  }

  var UFS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
  ];

  function formatUf(v) {
    return String(v == null ? "" : v).replace(/[^a-zA-Z]/g, "").toUpperCase().slice(0, 2);
  }

  function validateUf(v) {
    var s = trim(v).toUpperCase();
    if (!s) return null;
    return UFS.indexOf(s) >= 0 ? null : "UF inválida.";
  }

  function ufLiveState(v) {
    var s = trim(v);
    if (!s) return { state: "", message: "" };
    if (s.length < 2) return { state: "warn", message: "UF com 2 letras (ex.: SP)." };
    var err = validateUf(s);
    return err ? { state: "error", message: err } : { state: "ok", message: "" };
  }

  function validateCoordinate(v, label, limite) {
    var s = trim(v);
    if (!s) return null;
    var st = PF.coordinateLiveState(s, label);
    if (st.state === "error") return st.message;
    var n = Number(s.replace(/\s+/g, "").replace(",", "."));
    if (Math.abs(n) > limite) {
      return label + " fora do intervalo permitido (-" + limite + " a " + limite + ").";
    }
    return null;
  }

  function coordinateLiveState(v, label, limite) {
    if (!trim(v)) return { state: "", message: "" };
    var err = validateCoordinate(v, label, limite);
    return err ? { state: "error", message: err } : { state: "ok", message: label + " válida." };
  }

  function validateCoordPair(lat, lon) {
    if (!!trim(lat) !== !!trim(lon)) {
      return "Informe latitude e longitude juntas (ou deixe ambas vazias).";
    }
    return null;
  }

  /**
   * Endereço de cliente/unidade: máscara + estado ao vivo.
   * refs: { cnpj, cep, uf, latitude, longitude } (ids ou elementos).
   */
  function bindEndereco(refs) {
    refs = refs || {};
    var refreshers = [];
    if (refs.cnpj) {
      bindMask(refs.cnpj, formatCnpj);
      refreshers.push(bindLive(refs.cnpj, cnpjLiveState));
    }
    if (refs.cep) {
      bindMask(refs.cep, formatCep);
      refreshers.push(bindLive(refs.cep, cepLiveState));
    }
    if (refs.uf) {
      bindMask(refs.uf, formatUf);
      refreshers.push(bindLive(refs.uf, ufLiveState));
    }
    function coordPair() {
      var lat = el(refs.latitude);
      var lon = el(refs.longitude);
      if (!lat || !lon) return;
      var errPair = validateCoordPair(lat.value, lon.value);
      if (!errPair) return;
      var vazio = !trim(lat.value) ? lat : lon;
      setState(vazio, "warn", "Informe também a " + (vazio === lat ? "latitude." : "longitude."));
    }
    [["latitude", "Latitude", 90], ["longitude", "Longitude", 180]].forEach(function (cfg) {
      var e = el(refs[cfg[0]]);
      if (!e) return;
      var r = bindLive(e, function (v) {
        return coordinateLiveState(v, cfg[1], cfg[2]);
      });
      e.addEventListener("blur", function () {
        var n = trim(e.value).replace(/\s+/g, "").replace(",", ".");
        if (n !== e.value) e.value = n;
        r();
        coordPair();
      });
      refreshers.push(function () {
        r();
        coordPair();
      });
    });
    return {
      refresh: function () {
        refreshers.forEach(function (fn) {
          fn();
        });
      },
    };
  }

  /** Primeira mensagem de erro do bloco de endereço (mesmas frases da API). */
  function validateEndereco(p) {
    p = p || {};
    return (
      validateCnpj(p.cnpj) ||
      validateUf(p.uf) ||
      validateCep(p.cep) ||
      validateCoordinate(p.latitude, "Latitude", 90) ||
      validateCoordinate(p.longitude, "Longitude", 180) ||
      (("latitude" in p || "longitude" in p) ? validateCoordPair(p.latitude, p.longitude) : null)
    );
  }

  function validateClientePayload(p) {
    if (!trim(p.razao_social)) return "Razão social é obrigatória.";
    return validateEndereco({ cnpj: p.cnpj_cliente, uf: p.uf, cep: p.cep });
  }

  function validateUnidadePayload(p) {
    if (!trim(p.id_cliente)) return "Cliente é obrigatório.";
    if (!trim(p.nome_unidade)) return "Nome da unidade é obrigatório.";
    return validateEndereco({
      cnpj: p.cnpj_unidade,
      uf: p.uf,
      cep: p.cep,
      latitude: p.latitude,
      longitude: p.longitude,
    });
  }

  /* ------------------------------------------------------------------ */
  /* Field (CPF / e-mail / telefone) — core.utils.validators              */
  /* ------------------------------------------------------------------ */

  function cpfValido(d) {
    if (!/^\d{11}$/.test(d) || /^(\d)\1{10}$/.test(d)) return false;
    function calc(n) {
      var t = 0;
      for (var i = 0; i < n; i++) t += Number(d[i]) * (n + 1 - i);
      var r = t % 11;
      return r < 2 ? 0 : 11 - r;
    }
    return Number(d[9]) === calc(9) && Number(d[10]) === calc(10);
  }

  function formatCpf(v) {
    var d = digits(v).slice(0, 11);
    var out = d.slice(0, 3);
    if (d.length > 3) out += "." + d.slice(3, 6);
    if (d.length > 6) out += "." + d.slice(6, 9);
    if (d.length > 9) out += "-" + d.slice(9, 11);
    return out;
  }

  function validateCpf(v) {
    var d = digits(v);
    if (!d) return null;
    if (d.length !== 11) return "CPF deve ter 11 dígitos.";
    return cpfValido(d) ? null : "CPF inválido.";
  }

  var EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

  function splitEmails(raw) {
    return String(raw == null ? "" : raw)
      .split(/[\n,;]+/)
      .map(function (s) {
        return s.trim();
      })
      .filter(Boolean);
  }

  function validateEmails(list) {
    var seen = {};
    var unicos = 0;
    for (var i = 0; i < list.length; i++) {
      if (!EMAIL_RE.test(list[i])) return "E-mail inválido: " + list[i].slice(0, 40);
      var k = list[i].toLowerCase();
      if (!seen[k]) {
        seen[k] = 1;
        unicos++;
      }
    }
    return unicos > 20 ? "Máximo de 20 e-mails por Field." : null;
  }

  function telefoneLiveState(v) {
    var d = digits(v);
    if (!d) return { state: "", message: "" };
    if (d.length === 10 || d.length === 11) return { state: "ok", message: "" };
    return { state: "warn", message: "Telefone fora do padrão (DDD + 8 ou 9 dígitos)." };
  }

  function bindFieldLive(refs) {
    refs = refs || {};
    var rs = [];
    if (refs.cpf) {
      bindMask(refs.cpf, formatCpf);
      rs.push(
        bindLive(refs.cpf, function (v) {
          var d = digits(v);
          if (!d) return { state: "", message: "" };
          if (d.length < 11) return { state: "warn", message: "CPF incompleto (" + d.length + "/11)." };
          var err = validateCpf(v);
          return err ? { state: "error", message: err } : { state: "ok", message: "CPF válido." };
        })
      );
    }
    if (refs.emails) {
      rs.push(
        bindLive(refs.emails, function (v) {
          var list = splitEmails(v);
          if (!list.length) return { state: "", message: "" };
          var err = validateEmails(list);
          return err
            ? { state: "error", message: err }
            : { state: "ok", message: list.length + " e-mail(s) válido(s)." };
        })
      );
    }
    if (refs.telefone) rs.push(bindLive(refs.telefone, telefoneLiveState));
    return {
      refresh: function () {
        rs.forEach(function (fn) {
          fn();
        });
      },
    };
  }

  function validateFieldPayload(p) {
    if (!trim(p.nome)) return "Nome é obrigatório.";
    return validateCpf(p.cpf) || validateEmails(p.emails || []);
  }

  /* ------------------------------------------------------------------ */
  /* Equipamento — serial Fortinet, hostname, Ticket NOC, ID VGR          */
  /* ------------------------------------------------------------------ */

  function validateEqPayload(p) {
    if (!trim(p.serial)) return "Serial é obrigatório.";
    if (PF.isFortinetFamily(p.vendor, p.modelo)) {
      var errS = PF.validateSerialFortinet(p.serial, { obrigatorio: true });
      if (errS) return errS;
    }
    if (p.hostname && /\s/.test(trim(p.hostname))) {
      return "O campo «Hostname» não pode conter espaços.";
    }
    if (trim(p.tkt_noc)) {
      var errT = PF.validateTicketNoc(p.tkt_noc);
      if (errT) return errT;
    }
    if (p.id_vgr && PF.sanitizePastedText(p.id_vgr).length > 64) {
      return "ID VGR do equipamento aceita no máximo 64 caracteres.";
    }
    return null;
  }

  /**
   * refs: { serial, vendor, modelo, hostname, tktNoc, idVgr }.
   * Fortinet: serial normalizado (maiúsculas, sem hífen/espaço) e modelo
   * sugerido pelo fragmento do serial (40F, 120G…), como no core.
   */
  function bindEqLive(refs) {
    refs = refs || {};
    var serialEl = el(refs.serial);
    var vendorEl = el(refs.vendor);
    var modeloEl = el(refs.modelo);

    if (refs.idVgr) PF.bindSanitizeInput(el(refs.idVgr), PF.sanitizePastedText);
    if (refs.hostname) {
      PF.bindSanitizeInput(el(refs.hostname), function (s) {
        return String(s == null ? "" : s).replace(/\s+/g, "").toLowerCase();
      });
    }

    function isForti() {
      return PF.isFortinetFamily(vendorEl && vendorEl.value, modeloEl && modeloEl.value);
    }

    function refreshSerial() {
      if (!serialEl) return;
      if (!isForti()) {
        setState(serialEl, trim(serialEl.value) ? "ok" : "", "");
        if (modeloEl) setState(modeloEl, "", "");
        return;
      }
      var st = PF.serialFortinetLiveState(serialEl.value, { obrigatorio: true });
      setState(serialEl, st.state, st.message);
      if (!modeloEl) return;
      var inferido = PF.inferModeloFromSerialStrict(serialEl.value);
      var atual = PF.normalizeModeloFortigate(modeloEl.value);
      if (inferido && (!atual || atual === inferido)) {
        modeloEl.value = inferido;
        setState(modeloEl, "ok", "Modelo mapeado do serial.");
      } else if (inferido && atual !== inferido) {
        setState(modeloEl, "warn", "Modelo diverge do serial — ao salvar será gravado " + inferido + ".");
      } else {
        setState(modeloEl, "", "");
      }
    }

    if (serialEl && serialEl.dataset.vgrEqBound !== "1") {
      serialEl.dataset.vgrEqBound = "1";
      serialEl.addEventListener("input", refreshSerial);
      serialEl.addEventListener("blur", function () {
        if (isForti()) {
          var n = PF.normalizeSerial(serialEl.value);
          if (n !== serialEl.value) serialEl.value = n;
        }
        refreshSerial();
      });
      if (vendorEl) vendorEl.addEventListener("change", refreshSerial);
      if (modeloEl) modeloEl.addEventListener("input", refreshSerial);
    }

    var rHost = bindLive(refs.hostname, function (v) {
      if (!trim(v)) return { state: "", message: "" };
      return /\s/.test(trim(v))
        ? { state: "error", message: "O campo «Hostname» não pode conter espaços." }
        : { state: "ok", message: "" };
    });
    var rTkt = bindLive(refs.tktNoc, function (v) {
      var s = trim(v).replace(/\s+/g, "");
      if (!s) return { state: "", message: "" };
      if (/^1\d{0,5}$/.test(s)) return { state: "warn", message: "Ticket NOC incompleto (7 dígitos)." };
      var err = PF.validateTicketNoc(s);
      return err ? { state: "error", message: err } : { state: "ok", message: "Ticket NOC no padrão." };
    });

    return {
      refresh: function () {
        refreshSerial();
        rHost();
        rTkt();
      },
    };
  }

  /* ------------------------------------------------------------------ */
  /* Link — calculadora IPv4, ID VGR, LP, velocidade, VLAN, operadora     */
  /* ------------------------------------------------------------------ */

  function maskFromPrefix(text) {
    var s = String(text == null ? "" : text);
    var i = s.indexOf("/");
    if (i < 0) return null;
    var n = parseInt(s.slice(i + 1), 10);
    if (isNaN(n) || n < 0 || n > 32) return null;
    var m = n === 0 ? 0 : (0xffffffff << (32 - n)) >>> 0;
    return [m >>> 24, (m >>> 16) & 255, (m >>> 8) & 255, m & 255].join(".");
  }

  function ipToInt(ip) {
    var c = PF.canonicalizeIpv4(ip);
    if (!PF.isValidIpv4(c)) return null;
    var p = c.split(".").map(Number);
    return ((p[0] << 24) >>> 0) + (p[1] << 16) + (p[2] << 8) + p[3];
  }

  function intToIp(n) {
    return [n >>> 24, (n >>> 16) & 255, (n >>> 8) & 255, n & 255].join(".");
  }

  function prefixLen(mask) {
    var n = ipToInt(mask);
    if (n === null) return null;
    var bits = 0;
    for (var i = 31; i >= 0; i--) {
      if ((n >>> i) & 1) bits++;
      else break;
    }
    return bits;
  }

  function maskContigua(mask) {
    return PF.ipv4NetworkAddress("255.255.255.255", mask) !== null;
  }

  /** Resumo da calculadora: rede, broadcast e hosts úteis. */
  function calcRede(ip, mask) {
    var net = PF.ipv4NetworkAddress(ip, mask);
    if (!net) return null;
    var p = prefixLen(mask);
    var netInt = ipToInt(net);
    var hostMask = (~ipToInt(mask)) >>> 0;
    var bcast = intToIp((netInt + hostMask) >>> 0);
    var hosts = p >= 31 ? Math.pow(2, 32 - p) : Math.max(0, Math.pow(2, 32 - p) - 2);
    return { rede: net, prefixo: p, broadcast: bcast, hosts: hosts };
  }

  function validateVlan(v) {
    var s = trim(v).replace(/\s+/g, "");
    if (!s) return null;
    var m = /^(?:vlan)?(\d{1,4})$/i.exec(s);
    if (!m || Number(m[1]) < 1 || Number(m[1]) > 4094) {
      return "VLAN inválida: informe o ID numérico entre 1 e 4094.";
    }
    return null;
  }

  /** Operadora: principal → valor; OUTROS → texto do campo extra (core.operadora). */
  function readOperadora(selRef, outrosRef) {
    var sel = trim(val(selRef)).toUpperCase();
    return {
      select: sel,
      operadora: PF.resolveOperadora(sel, val(outrosRef)) || "",
      outros: PF.normalizeOperadora(val(outrosRef)),
    };
  }

  /** Reabrir formulário: VTAL gravada → select OUTROS + texto VTAL. */
  function fillOperadora(selRef, outrosRef, stored) {
    var sel = el(selRef);
    var outros = el(outrosRef);
    var s = PF.normalizeOperadora(stored);
    var principal = V.OPERADORAS_PRINCIPAIS.indexOf(s) >= 0;
    if (sel) {
      V.fillSelectOptions(sel, V.OPERADORAS, s ? (principal ? s : "OUTROS") : "", {
        emptyLabel: "Selecione...",
      });
    }
    if (outros) outros.value = s && !principal ? s : "";
    if (sel) sel.dispatchEvent(new Event("change", { bubbles: true }));
  }

  /** Zera no payload os campos que não se aplicam ao tipo/modo (ocultos no form). */
  function cleanLinkPayload(p) {
    var vis = V.linkFieldVisibility(p.tipo_link, p.modo_conexao, p.operadora);
    var map = {
      ip_address: vis.ip,
      mascara: vis.mascara,
      gateway: vis.gateway,
      subrede: vis.subrede,
      range_start: vis.range,
      range_end: vis.range,
      vlan: vis.vlan,
      velocidade: vis.vel,
      designador: vis.designador,
      operadora: vis.operadora,
      id_vgr_link: vis.idVgr,
      identificador: vis.porta,
    };
    Object.keys(map).forEach(function (k) {
      if (k in p && !map[k]) p[k] = "";
    });
    if (!vis.operadora) delete p.operadora_outros;
    if (!vis.pppoe) {
      delete p.pppoe_user;
      delete p.pppoe_pass;
    }
    if (!vis.isWan) {
      p.modo_conexao = null;
      p.id_equipamento = null;
    }
    return p;
  }

  /**
   * Validação completa do payload de link (mesma ordem do parse_link_payload):
   * formatos → calculadora IP/máscara → obrigatórios por modo.
   * Retorna a primeira mensagem de erro ou null.
   * Flags opcionais: p._operadora_select, p._has_pppoe_user, p._has_pppoe_pass.
   */
  function validateLinkPayload(p) {
    p = p || {};
    var tipo = trim(p.tipo_link).toUpperCase();
    var modo = trim(p.modo_conexao).toUpperCase();
    var op = trim(p.operadora).toUpperCase();
    var vis = V.linkFieldVisibility(tipo, modo, op);
    var label = ("Link " + tipo).trim();
    var err;

    if (!tipo) return "Tipo de link inválido.";
    if (vis.isWan && !trim(p.id_equipamento)) return "Selecione o equipamento.";
    if (p._operadora_select === "OUTROS" && !op) {
      return "Operadora «OUTROS»: informe o nome da operadora.";
    }

    err = PF.validateIdVgrLinkFormat(p.id_vgr_link);
    if (err) return err;
    if (trim(p.designador)) {
      err = PF.validateDesignadorVivoFormat(p.designador, op);
      if (err) return err;
    }
    if (trim(p.velocidade) && !PF.normalizeVelocityMbps(p.velocidade).value) {
      return "Velocidade inválida. Use Mbps/Gbps (ex.: 300, 300 Mbps, 1G, 10 Gbps).";
    }
    err = validateVlan(p.vlan);
    if (err) return err;

    /* --- isolados --- */
    var ip = PF.normalizeIpText(p.ip_address);
    var mask = PF.canonicalizeIpv4(p.mascara);
    var gw = PF.normalizeIpText(p.gateway);
    var sub = PF.normalizeIpText(p.subrede);

    if (mask) {
      err = PF.validateIpv4(mask, { label: "Máscara" });
      if (err) return err.replace("inválido", "inválida");
      if (!maskContigua(mask)) {
        return "Máscara inválida: não é uma máscara de rede (bits devem ser contíguos, ex.: 255.255.255.0).";
      }
    }

    function absorvePrefixo(txt, campo) {
      var pm = maskFromPrefix(txt);
      if (!pm) return null;
      if (!mask) {
        mask = pm;
        return null;
      }
      if (mask !== pm) {
        return (
          label + ": o prefixo /" + txt.split("/")[1] + " de «" + campo +
          "» não confere com a máscara " + mask + " (esperado " + pm + ")."
        );
      }
      return null;
    }

    if (ip) {
      err = PF.validateIpv4(ip, { label: "IP", allowCidr: true });
      if (err) return err;
      err = absorvePrefixo(ip, "IP");
      if (err) return err;
    }
    if (gw) {
      err = PF.validateIpv4(gw, { label: "Gateway" });
      if (err) return err;
    }
    if (sub) {
      err = PF.validateIpv4(sub, { label: "Subrede", allowCidr: true });
      if (err) return err;
      err = absorvePrefixo(sub, "Subrede");
      if (err) return err;
      if (sub.indexOf("/") >= 0) {
        sub = PF.ipv4NetworkAddress(sub.split("/")[0], maskFromPrefix(sub)) || sub;
      }
    }

    /* --- grupo (calculadora) --- */
    err = PF.validateIpMaskGroup({ ip: ip, mascara: mask, gateway: gw, subrede: sub, label: label });
    if (err) return err;
    if (!ip && sub && mask) {
      var netSub = PF.ipv4NetworkAddress(sub, mask);
      if (netSub && netSub !== PF.canonicalizeIpv4(sub)) {
        return (
          label + ": subrede " + PF.canonicalizeIpv4(sub) +
          " não é endereço de rede para a máscara " + mask + " (esperado " + netSub + ")."
        );
      }
    }

    /* --- ranges --- */
    var rs = PF.normalizeIpText(p.range_start);
    var re = PF.normalizeIpText(p.range_end);
    if (rs) {
      err = PF.validateIpv4(rs, { label: "Início do range" });
      if (err) return err;
    }
    if (re) {
      err = PF.validateIpv4(re, { label: "Fim do range" });
      if (err) return err;
    }
    if ("range_start" in p && "range_end" in p && !!rs !== !!re) {
      return label + ": informe o início e o fim do range.";
    }
    if (rs && re) {
      var a = ipToInt(rs);
      var b = ipToInt(re);
      if (a > b) return label + ": início do range (" + rs + ") maior que o fim (" + re + ").";
      var base = ip || sub;
      var c = base && mask ? calcRede(base.split("/")[0], mask) : null;
      if (c) {
        var netInt = ipToInt(c.rede);
        var bcInt = ipToInt(c.broadcast);
        var pares = [[a, "Início do range", rs], [b, "Fim do range", re]];
        for (var i = 0; i < pares.length; i++) {
          if (pares[i][0] < netInt || pares[i][0] > bcInt) {
            return label + ": " + pares[i][1] + " " + pares[i][2] + " fora da rede " + c.rede + "/" + c.prefixo + ".";
          }
          if (c.prefixo < 31 && (pares[i][0] === netInt || pares[i][0] === bcInt)) {
            return label + ": " + pares[i][1] + " " + pares[i][2] + " não pode ser o endereço de rede nem o de broadcast.";
          }
        }
      }
    }

    if (PF.wanEqualsGateway(ip, gw)) {
      return label + ": IP e Gateway não podem ser iguais. Corrija os campos de endereço.";
    }

    /* --- obrigatórios por modo (core.link_required, exigir_mascara=True) --- */
    if (vis.isWan) {
      var faltam = [];
      if (vis.isStaticMpls) {
        if (!ip) faltam.push("IP");
        if (!mask) faltam.push("Máscara");
        if (!gw) faltam.push("Gateway");
        if (op === "VIVO") {
          if (!trim(p.id_vgr_link)) faltam.push("ID VGR do link (obrigatório para VIVO)");
          if (!trim(p.identificador)) faltam.push("Identificação da porta (obrigatório para VIVO)");
        }
      }
      if (modo === "PPPOE") {
        if (!trim(p.pppoe_user) && !p._has_pppoe_user) faltam.push("PPPoE User");
        if (!trim(p.pppoe_pass) && !p._has_pppoe_pass) faltam.push("PPPoE Password");
      }
      if (faltam.length) {
        return "Campos obrigatórios do link não preenchidos: " + faltam.join(", ") + ".";
      }
    }
    return null;
  }

  /** Remove as chaves internas (_*) antes de enviar à API. */
  function stripInternal(p) {
    var out = {};
    Object.keys(p || {}).forEach(function (k) {
      if (k.charAt(0) !== "_") out[k] = p[k];
    });
    return out;
  }

  function renderPendencias(container, lista, onAplicar) {
    var box = el(container);
    if (!box) return;
    box.textContent = "";
    if (!lista || !lista.length) {
      box.classList.add("d-none");
      return;
    }
    box.classList.remove("d-none");
    var titulo = document.createElement("div");
    titulo.className = "fw-semibold mb-1";
    titulo.textContent = "Pendências VIVO (avisos — não bloqueiam o salvar):";
    box.appendChild(titulo);
    var ul = document.createElement("ul");
    ul.className = "mb-1 ps-3";
    lista.forEach(function (msg) {
      var li = document.createElement("li");
      li.textContent = msg;
      ul.appendChild(li);
    });
    box.appendChild(ul);
    if (typeof onAplicar === "function") {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-sm btn-outline-dark py-0";
      btn.textContent = "Aplicar máscara/gateway padrão VIVO";
      btn.addEventListener("click", onAplicar);
      box.appendChild(btn);
    }
  }

  /**
   * Validação ao vivo do formulário de link.
   * refs: { tipo, modo, operadora, operadoraOutros, idVgr, porta, designador,
   *         ip, mascara, gateway, subrede, rangeStart, rangeEnd, vlan, vel,
   *         pendencias } — ids ou elementos (accordion do atendimento cria
   *         elementos sem id).
   */
  function bindLinkLive(refs) {
    refs = refs || {};
    var E = {};
    Object.keys(refs).forEach(function (k) {
      E[k] = el(refs[k]);
    });

    ["ip", "mascara", "gateway", "subrede", "rangeStart", "rangeEnd"].forEach(function (k) {
      if (E[k]) PF.bindSanitizeInput(E[k], PF.normalizeIpText);
    });
    ["idVgr", "designador"].forEach(function (k) {
      if (E[k]) PF.bindSanitizeInput(E[k], PF.sanitizePastedText);
    });
    if (E.vel) PF.bindVelocityMbpsInput(E.vel);
    if (E.operadora) PF.bindOperadoraSelect(E.operadora, E.operadoraOutros || null, null, null);

    function v(k) {
      return E[k] ? String(E[k].value || "") : "";
    }
    var VIS_KEY = {
      ip: "ip",
      mascara: "mascara",
      gateway: "gateway",
      subrede: "subrede",
      rangeStart: "range",
      rangeEnd: "range",
      idVgr: "idVgr",
      porta: "porta",
      designador: "designador",
      vlan: "vlan",
    };
    /* Visibilidade pela REGRA (linkFieldVisibility), não pelo DOM: independe da
       ordem dos listeners e funciona no accordion do atendimento (sem wraps). */
    function curVis() {
      var opr = readOperadora(E.operadora, E.operadoraOutros);
      return V.linkFieldVisibility(v("tipo"), v("modo"), opr.operadora);
    }
    function show(k) {
      if (!E[k]) return false;
      var flag = VIS_KEY[k];
      return flag ? !!curVis()[flag] : !isHidden(E[k]);
    }
    function st(k, state, msg) {
      if (E[k]) setState(E[k], state, msg);
    }

    function refresh() {
      var opr = readOperadora(E.operadora, E.operadoraOutros);
      var tipo = v("tipo").toUpperCase();
      var modo = v("modo").toUpperCase();
      var vis = V.linkFieldVisibility(tipo, modo, opr.operadora);
      var label = ("Link " + tipo).trim();
      var obrigIp = vis.isWan && vis.isStaticMpls;

      /* limpa estados de campos ocultos */
      ["ip", "mascara", "gateway", "subrede", "rangeStart", "rangeEnd", "idVgr", "porta",
        "designador", "vlan"].forEach(function (k) {
        if (E[k] && !show(k)) st(k, "", "");
      });

      /* ID VGR / porta / LP */
      if (show("idVgr")) {
        var sId = PF.idVgrLinkLiveState(v("idVgr"), { obrigatorio: vis.idVgr });
        st("idVgr", sId.state, sId.message);
      }
      if (show("porta")) {
        st("porta", trim(v("porta")) ? "ok" : "warn",
          trim(v("porta")) ? "" : "Identificação da porta obrigatória (VIVO).");
      }
      if (show("designador")) {
        if (opr.operadora === "VIVO") {
          var sLp = PF.designadorVivoLiveState(v("designador"), "VIVO");
          st("designador", sLp.state, sLp.message);
        } else {
          st("designador", "", "");
        }
      }
      if (show("vlan")) {
        var eVlan = validateVlan(v("vlan"));
        st("vlan", eVlan ? "error" : trim(v("vlan")) ? "ok" : "", eVlan || "");
      }

      /* --- calculadora (campo oculto pela regra não participa do cálculo) --- */
      var ip = show("ip") ? PF.normalizeIpText(v("ip")) : "";
      var maskRaw = show("mascara") ? PF.canonicalizeIpv4(v("mascara")) : "";
      var gw = show("gateway") ? PF.normalizeIpText(v("gateway")) : "";
      var sub = show("subrede") ? PF.normalizeIpText(v("subrede")) : "";
      var mask = maskRaw;
      var okIp = false;
      var okMask = false;

      if (show("ip")) {
        if (!ip) {
          st("ip", obrigIp ? "warn" : "", obrigIp ? "IP obrigatório em " + modo + "." : "");
        } else {
          var eIp = PF.validateIpv4(ip, { label: "IP", allowCidr: true });
          if (eIp) {
            st("ip", (ip.match(/\./g) || []).length < 3 ? "warn" : "error",
              (ip.match(/\./g) || []).length < 3 ? "IP incompleto." : eIp);
          } else {
            okIp = true;
            st("ip", "ok", "IP válido.");
            var pm = maskFromPrefix(ip);
            if (pm && !mask) mask = pm;
          }
        }
      }

      if (show("mascara")) {
        if (!maskRaw) {
          if (mask && okIp) st("mascara", "ok", "Será preenchida pelo prefixo: " + mask + ".");
          else st("mascara", obrigIp ? "warn" : "", obrigIp ? "Máscara obrigatória em " + modo + "." : "");
          okMask = !!mask;
        } else if (!PF.isValidIpv4(maskRaw)) {
          st("mascara", (maskRaw.match(/\./g) || []).length < 3 ? "warn" : "error",
            (maskRaw.match(/\./g) || []).length < 3 ? "Máscara incompleta." : "Máscara inválida.");
        } else if (!maskContigua(maskRaw)) {
          st("mascara", "error", "Máscara inválida: bits devem ser contíguos (ex.: 255.255.255.0).");
        } else {
          okMask = true;
          st("mascara", "ok", "/" + prefixLen(maskRaw) + ".");
        }
      }

      var okGw = false;
      if (show("gateway")) {
        if (!gw) {
          st("gateway", obrigIp ? "warn" : "", obrigIp ? "Gateway obrigatório em " + modo + "." : "");
        } else {
          var sGw = PF.ipv4LiveState(gw, "Gateway");
          st("gateway", sGw.state, sGw.message);
          okGw = sGw.state === "ok";
          if (okGw && PF.wanEqualsGateway(ip, gw)) {
            st("gateway", "error", "IP e Gateway não podem ser iguais.");
            okGw = false;
          }
        }
      }

      if (show("subrede")) {
        if (!sub) st("subrede", "", "");
        else {
          var eSub = PF.validateIpv4(sub, { label: "Subrede", allowCidr: true });
          st("subrede", eSub ? "error" : "ok", eSub || "");
        }
      }

      /* grupo: só quando os isolados estão ok */
      if (okMask && (okIp || sub)) {
        var subCanon = sub && sub.indexOf("/") >= 0
          ? PF.ipv4NetworkAddress(sub.split("/")[0], maskFromPrefix(sub)) || sub
          : sub;
        var eGrp = PF.validateIpMaskGroup({
          ip: okIp ? ip : "",
          mascara: mask,
          gateway: okGw ? gw : "",
          subrede: show("subrede") ? subCanon : "",
          label: label,
        });
        if (eGrp) {
          var alvo = /Gateway/.test(eGrp) ? "gateway" : /subrede/.test(eGrp) ? "subrede" : "ip";
          st(alvo, "error", eGrp);
        } else if (okIp) {
          var c = calcRede(ip.split("/")[0], mask);
          if (c) {
            st("ip", "ok",
              "Rede " + c.rede + "/" + c.prefixo + " · broadcast " + c.broadcast +
              " · " + c.hosts + " host(s) útil(eis).");
          }
          if (show("subrede") && E.subrede && !trim(E.subrede.value) && c) {
            st("subrede", "", "Sugestão: " + c.rede);
          }
        }
        if (!okIp && sub && show("subrede")) {
          var netSub = PF.ipv4NetworkAddress(subCanon, mask);
          if (netSub && netSub !== PF.canonicalizeIpv4(subCanon)) {
            st("subrede", "error", "Subrede deve ser o endereço de rede (esperado " + netSub + ").");
          }
        }
      }

      /* ranges */
      if (show("rangeStart") || show("rangeEnd")) {
        var errR = validateLinkPayload({
          tipo_link: tipo,
          mascara: mask,
          ip_address: okIp ? ip : "",
          subrede: sub,
          range_start: v("rangeStart"),
          range_end: v("rangeEnd"),
        });
        var rsOk = !trim(v("rangeStart")) ? "" : "ok";
        var reOk = !trim(v("rangeEnd")) ? "" : "ok";
        st("rangeStart", rsOk, "");
        st("rangeEnd", reOk, "");
        if (errR && /range/i.test(errR)) {
          var alvoR = /Fim do range/.test(errR) ? "rangeEnd" : "rangeStart";
          if (/informe o início e o fim/.test(errR)) {
            alvoR = trim(v("rangeStart")) ? "rangeEnd" : "rangeStart";
            st(alvoR, "warn", errR);
          } else {
            st(alvoR, "error", errR);
          }
        }
      }

      /* pendências VIVO (core.link_vivo — aviso, não bloqueio) */
      if (E.pendencias) {
        var lista = [];
        if (vis.isWan && vis.isStaticMpls && opr.operadora === "VIVO" && okIp) {
          lista = PF.collectVivoLinkPendencias({
            operadora: "VIVO",
            modo: modo,
            ip: ip.split("/")[0],
            mascara: maskRaw,
            gateway: gw,
            designador: v("designador"),
          });
        }
        var precisaAplicar = lista.some(function (m) {
          return /máscara|gateway/i.test(m);
        });
        renderPendencias(E.pendencias, lista, precisaAplicar ? aplicarPadraoVivo : null);
      }
    }

    function aplicarPadraoVivo() {
      var ipHost = PF.normalizeIpText(v("ip")).split("/")[0];
      var m = PF.deriveVivoMaskFromWan(ipHost, v("modo"));
      var g = PF.deriveVivoGatewayFromWan(ipHost);
      if (E.ip && E.ip.value !== ipHost) E.ip.value = ipHost;
      if (m && E.mascara) E.mascara.value = m;
      if (g && E.gateway) E.gateway.value = g;
      refresh();
    }

    function onBlurCalc() {
      /* CIDR no IP e máscara vazia → preenche a máscara (calculadora) */
      var ip = show("ip") ? PF.normalizeIpText(v("ip")) : "";
      var pm = maskFromPrefix(ip);
      if (pm && E.mascara && !trim(E.mascara.value) && show("mascara")) E.mascara.value = pm;
      /* subrede vazia → sugere a rede de IP+máscara (core maybeFillSubnetFromIpMask) */
      if (E.subrede && show("subrede") && ip) {
        PF.maybeFillSubnetFromIpMask(E.subrede, ip.split("/")[0], PF.canonicalizeIpv4(v("mascara")) || pm);
      }
      refresh();
    }

    Object.keys(E).forEach(function (k) {
      var e = E[k];
      if (!e || k === "pendencias" || e.dataset.vgrLinkLiveBound === "1") return;
      e.dataset.vgrLinkLiveBound = "1";
      e.addEventListener("input", refresh);
      e.addEventListener("change", refresh);
      if (k === "ip" || k === "mascara") e.addEventListener("blur", onBlurCalc);
      else e.addEventListener("blur", refresh);
    });

    return { refresh: refresh, aplicarPadraoVivo: aplicarPadraoVivo };
  }

  /** Toast amarelo com as pendências devolvidas pela API (campo `avisos`). */
  function toastAvisos(avisos) {
    if (!avisos || !avisos.length) return;
    V.toast("Salvo com pendências VIVO: " + avisos.join(" "), true, "warn");
  }

  global.VgrFieldRules = {
    clearStates: clearStates,
    bindLive: bindLive,
    /* cadastro */
    formatCnpj: formatCnpj,
    validateCnpj: validateCnpj,
    formatCep: formatCep,
    validateCep: validateCep,
    validateUf: validateUf,
    validateCoordinate: validateCoordinate,
    bindEndereco: bindEndereco,
    validateEndereco: validateEndereco,
    validateClientePayload: validateClientePayload,
    validateUnidadePayload: validateUnidadePayload,
    /* field */
    formatCpf: formatCpf,
    validateCpf: validateCpf,
    splitEmails: splitEmails,
    bindFieldLive: bindFieldLive,
    validateFieldPayload: validateFieldPayload,
    /* equipamento */
    validateEqPayload: validateEqPayload,
    bindEqLive: bindEqLive,
    /* link */
    maskFromPrefix: maskFromPrefix,
    calcRede: calcRede,
    validateVlan: validateVlan,
    readOperadora: readOperadora,
    fillOperadora: fillOperadora,
    cleanLinkPayload: cleanLinkPayload,
    validateLinkPayload: validateLinkPayload,
    stripInternal: stripInternal,
    bindLinkLive: bindLinkLive,
    renderPendencias: renderPendencias,
    toastAvisos: toastAvisos,
  };
})(window);
