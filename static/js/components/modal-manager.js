export const ModalManager = {
  open(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const Modal = window.bootstrap?.Modal;
    if (Modal) {
      const m = Modal.getOrCreateInstance(el);
      m.show();
    } else {
      el.style.display = 'block';
      el.classList.add('show');
    }
  },
  close(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const Modal = window.bootstrap?.Modal;
    if (Modal) {
      const m = Modal.getOrCreateInstance(el);
      m.hide();
    } else {
      el.style.display = 'none';
      el.classList.remove('show');
    }
  }
};
