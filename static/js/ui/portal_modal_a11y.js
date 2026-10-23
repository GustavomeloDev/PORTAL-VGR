/**
 * A11y Bootstrap modal — evita aria-hidden em ancestral com foco (Chrome/Edge).
 * Em hide.bs.modal, remove o foco de qualquer descendente antes do aria-hidden=true.
 * Incluir depois do bootstrap.bundle.
 */
(function () {
  "use strict";

  function blurIfInside(modalEl) {
    if (!modalEl || modalEl.nodeType !== 1) return;
    var active = document.activeElement;
    if (!active || active === document.body || active === document.documentElement) {
      return;
    }
    if (modalEl.contains(active) && typeof active.blur === "function") {
      active.blur();
    }
  }

  document.addEventListener(
    "hide.bs.modal",
    function (ev) {
      blurIfInside(ev.target);
    },
    true
  );
})();
