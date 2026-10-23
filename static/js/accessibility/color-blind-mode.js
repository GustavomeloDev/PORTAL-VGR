export const ColorBlindMode = {
  storageKey: 'colorBlindModeEnabled',
  isEnabled() {
    try {
      return localStorage.getItem(this.storageKey) === '1';
    } catch (_) {
      return document.body.classList.contains('cb-mode');
    }
  },
  apply(enabled) {
    const on = !!enabled;
    document.body.classList.toggle('cb-mode', on);
    try {
      localStorage.setItem(this.storageKey, on ? '1' : '0');
    } catch (_) {}
  },
  toggle() {
    this.apply(!this.isEnabled());
  },
  init(buttonId = 'colorBlindToggle') {
    // Apply stored state on load
    this.apply(this.isEnabled());
    // Hook UI toggle
    const btn = document.getElementById(buttonId);
    if (btn) {
      btn.addEventListener('click', () => {
        this.toggle();
        // Optional: visual feedback
        const on = this.isEnabled();
        btn.classList.toggle('active', on);
        btn.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
    }
  }
};

// Auto-init if running as a module and DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  ColorBlindMode.init();
});
