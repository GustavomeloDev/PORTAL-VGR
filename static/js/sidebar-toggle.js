/**
 * Sidebar mobile — abre/fecha .sidebar via #sidebarToggle.
 * Usado pelo base_portal_module (core).
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
