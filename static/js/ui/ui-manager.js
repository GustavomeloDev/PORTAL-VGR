export const UIManager = {
  waitEl: null,
  showWait(message = 'Carregando...') {
    if (!this.waitEl) {
      const el = document.createElement('div');
      el.id = 'global-wait-overlay';
      el.style.position = 'fixed';
      el.style.top = '0';
      el.style.left = '0';
      el.style.right = '0';
      el.style.bottom = '0';
      el.style.background = 'rgba(0,0,0,0.3)';
      el.style.zIndex = '2000';
      el.style.display = 'flex';
      el.style.alignItems = 'center';
      el.style.justifyContent = 'center';
      el.style.backdropFilter = 'blur(1px)';
      const box = document.createElement('div');
      box.style.background = '#fff';
      box.style.padding = '12px 18px';
      box.style.borderRadius = '8px';
      box.style.boxShadow = '0 4px 12px rgba(0,0,0,0.2)';
      box.style.fontFamily = 'inherit';
      box.style.color = '#333';
      box.textContent = message;
      el.appendChild(box);
      document.body.appendChild(el);
      this.waitEl = el;
    } else {
      this.waitEl.querySelector('div').textContent = message;
      this.waitEl.style.display = 'flex';
    }
  },
  hideWait() {
    if (this.waitEl) this.waitEl.style.display = 'none';
  },
  showToast(message, type = 'info') {
    const t = window.toastr;
    if (t && t[type]) {
      t.options = { positionClass: 'toast-top-right', timeOut: 3000 };
      t[type](message);
    } else {
      alert(message);
    }
  },
  async showConfirm(message, onConfirm) {
    const ok = window.confirm(message);
    if (ok && typeof onConfirm === 'function') {
      try {
        await onConfirm();
      } catch (_) {}
    }
    return ok;
  }
};
