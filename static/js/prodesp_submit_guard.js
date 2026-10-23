/**
 * Anti duplo-clique / duplo-submit PRODESP.
 * - form[data-prodesp-submit-guard]: trava submits no 1º envio (navegação/POST).
 * - button[data-prodesp-submit-guard]: bloqueia reentrada se já locked.
 * - button[data-prodesp-guard-eager]: trava no 1º clique (antes do handler).
 * - API: ProdespSubmitGuard.lock / unlock / wrapAsync
 */
(function (global) {
  "use strict";

  var ATTR = "data-prodesp-submit-guard";
  var EAGER = "data-prodesp-guard-eager";
  var LOCKED = "data-prodesp-guard-locked";
  var ORIG_HTML = "data-prodesp-guard-html";
  var DEFAULT_LABEL = "Aguarde…";
  var AUTO_UNLOCK_MS = 120000;

  function _el(target) {
    if (!target) return null;
    if (typeof target === "string") return document.getElementById(target);
    return target;
  }

  function _isLocked(el) {
    return !!(el && el.getAttribute(LOCKED) === "1");
  }

  function lock(target, opts) {
    opts = opts || {};
    var el = _el(target);
    if (!el) return false;
    var already = _isLocked(el);
    el.setAttribute(LOCKED, "1");
    var soft = !!opts.soft;
    if (!soft && (el.tagName === "BUTTON" || el.tagName === "INPUT")) {
      try {
        el.disabled = true;
      } catch (_e) {}
      if (opts.label && el.tagName === "BUTTON") {
        if (!el.getAttribute(ORIG_HTML)) {
          el.setAttribute(ORIG_HTML, el.innerHTML);
        }
        var spinner =
          '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ';
        el.innerHTML = spinner + (opts.label || DEFAULT_LABEL);
      }
    }
    if (el._prodespGuardTimer) {
      clearTimeout(el._prodespGuardTimer);
      el._prodespGuardTimer = null;
    }
    var ms = opts.autoUnlockMs != null ? opts.autoUnlockMs : AUTO_UNLOCK_MS;
    if (ms > 0) {
      el._prodespGuardTimer = setTimeout(function () {
        unlock(el);
      }, ms);
    }
    return !already;
  }

  function unlock(target) {
    var el = _el(target);
    if (!el) return;
    if (el._prodespGuardTimer) {
      clearTimeout(el._prodespGuardTimer);
      el._prodespGuardTimer = null;
    }
    el.removeAttribute(LOCKED);
    if (el.tagName === "BUTTON" || el.tagName === "INPUT") {
      try {
        el.disabled = false;
      } catch (_e) {}
      var html = el.getAttribute(ORIG_HTML);
      if (html != null && el.tagName === "BUTTON") {
        el.innerHTML = html;
        el.removeAttribute(ORIG_HTML);
      }
    }
  }

  /** Libera form + todos os submits (necessário quando submit é interceptado por modal). */
  function unlockForm(form) {
    form = _el(form);
    if (!form) return;
    if (form._prodespGuardTimer) {
      clearTimeout(form._prodespGuardTimer);
      form._prodespGuardTimer = null;
    }
    form.removeAttribute(LOCKED);
    var list = form.querySelectorAll('button[type="submit"], input[type="submit"]');
    for (var i = 0; i < list.length; i++) {
      unlock(list[i]);
    }
  }

  /** Trava submits do form (mesmo contrato do listener de submit). */
  function lockForm(form, opts) {
    opts = opts || {};
    form = _el(form);
    if (!form) return;
    _lockFormSubmits(form, opts.label || "Gerando…");
  }

  function wrapAsync(target, fn, opts) {
    opts = opts || {};
    return async function (ev) {
      var el = _el(target) || (ev && ev.currentTarget);
      if (!el) return;
      if (_isLocked(el)) {
        if (ev) {
          ev.preventDefault();
          ev.stopPropagation();
        }
        return;
      }
      lock(el, {
        label: opts.label || DEFAULT_LABEL,
        autoUnlockMs: opts.autoUnlockMs != null ? opts.autoUnlockMs : AUTO_UNLOCK_MS,
      });
      try {
        return await fn.call(this, ev);
      } finally {
        if (!opts.keepLocked) unlock(el);
      }
    };
  }

  function _lockFormSubmits(form, label) {
    if (!form) return;
    var list = form.querySelectorAll('button[type="submit"], input[type="submit"]');
    for (var i = 0; i < list.length; i++) {
      /* autoUnlock so do botao deixava o form LOCKED; o proximo clique morria. */
      lock(list[i], {
        label: label || "Enviando…",
        autoUnlockMs: 0,
      });
    }
    form.setAttribute(LOCKED, "1");
    if (form._prodespGuardTimer) {
      clearTimeout(form._prodespGuardTimer);
      form._prodespGuardTimer = null;
    }
    form._prodespGuardTimer = setTimeout(function () {
      unlockForm(form);
    }, AUTO_UNLOCK_MS);
  }

  function bindForm(form, opts) {
    opts = opts || {};
    if (!form || form._prodespGuardBound) return;
    form._prodespGuardBound = true;
    form.addEventListener(
      "submit",
      function (ev) {
        if (form.getAttribute(LOCKED) === "1") {
          ev.preventDefault();
          ev.stopImmediatePropagation();
          return;
        }
        _lockFormSubmits(form, opts.label || "Gerando…");
      },
      true
    );
  }

  function _onCaptureClick(ev) {
    var t = ev.target;
    if (!t || !t.closest) return;
    var btn = t.closest("[" + ATTR + "]");
    if (!btn || btn.tagName === "FORM") return;
    if (btn.tagName !== "BUTTON" && btn.tagName !== "INPUT" && btn.tagName !== "A") {
      return;
    }
    if (btn.type === "submit" && btn.form && btn.form.hasAttribute(ATTR)) {
      return;
    }
    if (_isLocked(btn)) {
      ev.preventDefault();
      ev.stopImmediatePropagation();
      return;
    }
    // Soft-lock (só flag): anti bounce sem disabled no mesmo clique (senão o handler pode não rodar).
    var eager = btn.hasAttribute(EAGER);
    if (eager) {
      lock(btn, {
        label: btn.getAttribute("data-prodesp-guard-label") || DEFAULT_LABEL,
        autoUnlockMs: Number(btn.getAttribute("data-prodesp-guard-ms")) || AUTO_UNLOCK_MS,
      });
    } else {
      lock(btn, { soft: true, autoUnlockMs: 4000 });
    }
  }

  function autoBind(root) {
    root = root || document;
    var forms = root.querySelectorAll("form[" + ATTR + "]");
    for (var i = 0; i < forms.length; i++) {
      bindForm(forms[i]);
    }
  }

  function init() {
    document.addEventListener("click", _onCaptureClick, true);
    autoBind(document);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  global.ProdespSubmitGuard = {
    lock: lock,
    unlock: unlock,
    lockForm: lockForm,
    unlockForm: unlockForm,
    wrapAsync: wrapAsync,
    bindForm: bindForm,
    autoBind: autoBind,
    isLocked: function (t) {
      return _isLocked(_el(t));
    },
  };
})(typeof window !== "undefined" ? window : this);
