/**
 * @file prodesp/static/js/prodesp_field_limits.js
 * @module PRODESP — Modal (validação de formulário)
 *
 * Finalidade:
 *   Aplica maxlength nos inputs dos modais conforme limites do banco e traduz erros
 *   MySQL «Data too long» para mensagens legíveis ao usuário.
 *
 * Telas:
 *   - atendimentos_prodesp.html
 *
 * Depende de:
 *   - window.PRODESP_FORM_FIELD_LIMITS (injetado pelo template a partir de
 *     prodesp/db_field_limits.FORM_ELEMENT_LIMITS)
 */
(function () {
  "use strict";

  function prodespHumanizeSaveError(detail) {
    if (detail == null || detail === "") return null;
    let s = String(detail).trim();
    s = s.replace(/^Erro interno:\s*/i, "");
    s = s.replace(/^Erro:\s*/i, "");
  s = s.replace(/^\d+\s*\(\d+\):\s*/i, "");
    if (/aceita no máximo|excede o tamanho|caracteres informados/i.test(s)) {
      return s;
    }
    if (/Data too long for column/i.test(s)) {
      const m = s.match(/column '([^']+)'/i);
      const col = m ? m[1].replace(/_/g, " ") : "campo";
      return `O valor informado é longo demais para «${col}». Reduza o texto e tente novamente.`;
    }
    return s;
  }

  function prodespApplyFormFieldLimits(limits) {
    const map = limits || window.PRODESP_FORM_FIELD_LIMITS || {};
    Object.keys(map).forEach(function (id) {
      const max = parseInt(map[id], 10);
      if (!max || max < 1) return;
      const el = document.getElementById(id);
      if (!el) return;
      el.maxLength = max;
      el.setAttribute("maxlength", String(max));
      const hint = `Máximo ${max} caracteres`;
      if (!el.title) el.title = hint;
      el.dataset.prodespMaxLen = String(max);
    });
  }

  window.ProdespFieldLimits = {
    humanizeSaveError: prodespHumanizeSaveError,
    apply: prodespApplyFormFieldLimits,
  };

  document.addEventListener("DOMContentLoaded", function () {
    prodespApplyFormFieldLimits();
  });
})();
