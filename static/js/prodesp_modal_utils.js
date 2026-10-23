/**
 * Utilitários Bootstrap Modal PRODESP — evita backdrop cinza preso e body.modal-open órfão.
 */
(function () {
  "use strict";

  const MODAL_BASE_Z = 1055;
  const BACKDROP_Z = 1050;

  function countOpenModals() {
    return document.querySelectorAll(".modal.show").length;
  }

  /** Sincroniza backdrop e z-index após abrir/fechar modal empilhado (ex.: caderno sobre edição). */
  function syncModalStack() {
    const openModals = Array.from(document.querySelectorAll(".modal.show"));

    document.querySelectorAll(".modal:not(.show)").forEach((modalEl) => {
      modalEl.style.removeProperty("z-index");
    });

    if (openModals.length === 0) {
      document.querySelectorAll(".modal-backdrop").forEach((el) => el.remove());
      document.body.classList.remove("modal-open");
      document.body.style.removeProperty("overflow");
      document.body.style.removeProperty("padding-right");
      return;
    }

    document.body.classList.add("modal-open");

    let backdrops = Array.from(document.querySelectorAll(".modal-backdrop"));
    while (backdrops.length > 1) {
      backdrops.pop().remove();
      backdrops = Array.from(document.querySelectorAll(".modal-backdrop"));
    }

    let backdrop = backdrops[0];
    if (!backdrop) {
      backdrop = document.createElement("div");
      backdrop.className = "modal-backdrop fade show";
      document.body.appendChild(backdrop);
    }

    backdrop.style.zIndex = String(BACKDROP_Z);
    openModals.forEach((modalEl, index) => {
      modalEl.style.zIndex = String(MODAL_BASE_Z + index * 20);
    });
  }

  function cleanupModalArtifacts() {
    syncModalStack();
  }

  function ensureOnBody(modalEl) {
    if (modalEl && modalEl.parentElement !== document.body) {
      document.body.appendChild(modalEl);
    }
  }

  function open(modalEl, options = {}) {
    if (!modalEl || typeof bootstrap === "undefined") {
      return null;
    }
    ensureOnBody(modalEl);
    const inst = bootstrap.Modal.getOrCreateInstance(modalEl, {
      backdrop: options.backdrop ?? true,
      keyboard: options.keyboard ?? true,
      focus: options.focus ?? true,
    });
    inst.show();
    return inst;
  }

  function blurFocusedDescendant(modalEl) {
    const active = document.activeElement;
    if (active && modalEl.contains(active) && typeof active.blur === "function") {
      active.blur();
    }
  }

  function initModalFocusFix() {
    document.querySelectorAll(".modal").forEach((modalEl) => {
      if (modalEl.dataset.prodespFocusFix === "1") return;
      modalEl.dataset.prodespFocusFix = "1";
      modalEl.addEventListener("hide.bs.modal", () => {
        blurFocusedDescendant(modalEl);
      });
    });
  }

  function initGlobalCleanup() {
    document.addEventListener("hidden.bs.modal", () => {
      window.setTimeout(syncModalStack, 0);
    });
    initModalFocusFix();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initGlobalCleanup);
  } else {
    initGlobalCleanup();
  }

  window.ProdespModal = {
    cleanupModalArtifacts,
    syncModalStack,
    ensureOnBody,
    open,
  };
})();
