/**
 * @file prodesp/static/js/sidebar-toggle.js
 * @module PRODESP — Layout (sidebar mobile)
 *
 * Finalidade:
 *   Abre/fecha a sidebar em telas pequenas (#sidebarToggle) e fecha ao clicar fora.
 *
 * Telas:
 *   - atendimentos_prodesp.html, dashboard_atendimentos_prodesp.html (indireto)
 *   - csv_prodesp.html, prodesp_criar_blueprint.html
 *
 * Depende de:
 *   - layout.css (.sidebar.open)
 */
const toggleButton = document.getElementById("sidebarToggle");
const sidebar = document.querySelector(".sidebar");

if (toggleButton && sidebar) {
  toggleButton.addEventListener("click", () => {
    sidebar.classList.toggle("open");
  });

  document.addEventListener("click", (e) => {
    if (!sidebar.contains(e.target) && !toggleButton.contains(e.target)) {
      sidebar.classList.remove("open");
    }
  });
}
