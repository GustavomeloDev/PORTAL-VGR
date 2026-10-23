/**
 * Fluxo status/substatus atendimento VGR — espelho PRODESP (populateSubstatus).
 * Fonte: API /vgr/api/atendimentos/catalogo (substatus_por_status + regras).
 */
(function (global) {
  "use strict";

  function normalizeFluxo(sub) {
    var s = String(sub || "").trim();
    if (s === "Triagem") return "Aguarda Gestão";
    if (s === "Aguarda Fornecedor") return "Aguarda Contratada";
    return s;
  }

  function destinosAgGp(oldSub, regras) {
    var gestao = { "Aguarda Gestão": 1, Triagem: 1 };
    var paralelos = {};
    (regras.paralelos_ag_gp || []).forEach(function (p) {
      paralelos[p] = 1;
    });
    var fila = regras.fila_inicial || "Aguardando Config. Remota";
    var old = String(oldSub || "").trim();
    var out = {};
    function addSet(arr) {
      Object.keys(arr).forEach(function (k) {
        if (arr[k]) out[k] = 1;
      });
    }
    if (gestao[old] || old === "Aguarda Gestão") {
      addSet(gestao);
      addSet(paralelos);
      out[fila] = 1;
      return out;
    }
    if (old === fila) {
      addSet(gestao);
      out[fila] = 1;
      addSet(paralelos);
      return out;
    }
    if (paralelos[old]) {
      addSet(gestao);
      addSet(paralelos);
      out[fila] = 1;
      return out;
    }
    return out;
  }

  /**
   * @param {HTMLSelectElement} subEl
   * @param {string} statusValue
   * @param {string|null} currentSubstatus
   * @param {object} catalogo
   * @param {object} opts { isAgGp, context }
   */
  function populateSubstatus(subEl, statusValue, currentSubstatus, catalogo, opts) {
    if (!subEl) return;
    opts = opts || {};
    var status = String(statusValue || "").trim();
    var cur = normalizeFluxo(currentSubstatus);
    var porStatus = (catalogo && catalogo.substatus_por_status) || {};
    var fluxo = (catalogo && catalogo.substatus_fluxo) || [];
    var retorno = {};
    ((catalogo && catalogo.substatus_retorno_fluxo) || []).forEach(function (s) {
      retorno[s] = 1;
    });
    var regras = (catalogo && catalogo.regras) || {};
    var isAgGp = !!opts.isAgGp;

    subEl.innerHTML = "";
    var ph = document.createElement("option");
    ph.value = "";
    ph.textContent = "Selecione...";
    ph.disabled = true;
    ph.selected = true;
    subEl.appendChild(ph);
    subEl.disabled = !status;
    if (!status) return;

    var options = [];

    if (status === "Em Atendimento") {
      var baseline = cur;
      var allowed = [];
      var idx = fluxo.indexOf(baseline);
      if (!baseline || idx < 0) {
        allowed = fluxo.slice();
      } else if (baseline === "Aguardando Caderno de Teste") {
        allowed = fluxo.slice();
      } else {
        for (var i = 0; i < fluxo.length; i++) {
          var sub = fluxo[i];
          if (i < idx) {
            if (retorno[sub]) allowed.push(sub);
          } else if (i <= idx + 1) {
            allowed.push(sub);
          }
        }
      }
      allowed.forEach(function (s) {
        options.push(s);
      });
      var paralelos = isAgGp
        ? regras.paralelos_ag_gp || []
        : (catalogo.substatus_paralelos || []);
      paralelos.forEach(function (p) {
        if (options.indexOf(p) < 0) options.splice(Math.min(1, options.length), 0, p);
      });
      if (isAgGp) {
        var allowedDest = destinosAgGp(cur || regras.fila_inicial, regras);
        options = options.filter(function (o) {
          return !!allowedDest[o];
        });
        if (cur && options.indexOf(cur) < 0 && allowedDest[cur]) {
          options.unshift(cur);
        } else if (cur && options.indexOf(cur) < 0) {
          options.unshift(cur);
        }
      }
    } else {
      options = (porStatus[status] || []).slice();
    }

    // Garante valor atual na lista (legado)
    if (cur && options.indexOf(cur) < 0) {
      options.unshift(cur);
    }

    options.forEach(function (s) {
      var o = document.createElement("option");
      o.value = s;
      o.textContent = s;
      subEl.appendChild(o);
    });

    var valueToSet = "";
    if (cur && options.indexOf(cur) >= 0) valueToSet = cur;
    else if (options.length === 1) valueToSet = options[0];
    else if (
      status === "Em Atendimento" &&
      options.indexOf(regras.fila_inicial || "Aguardando Config. Remota") >= 0 &&
      opts.context === "create"
    ) {
      valueToSet = "Aguarda Gestão";
      if (options.indexOf(valueToSet) < 0) valueToSet = options[0] || "";
    }
    if (valueToSet) {
      subEl.value = valueToSet;
      ph.selected = false;
    }
  }

  global.VgrAtendimentoStatusFlow = {
    normalizeFluxo: normalizeFluxo,
    populateSubstatus: populateSubstatus,
    destinosAgGp: destinosAgGp,
  };
})(window);
