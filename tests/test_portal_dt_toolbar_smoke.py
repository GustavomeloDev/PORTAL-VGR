"""
Smoke estático: toolkit PortalDt + integração login (sem browser).
Roda com: .venv_portal_pessoal\\Scripts\\python.exe core/tests/test_portal_dt_toolbar_smoke.py
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class PortalDtToolbarSmoke(unittest.TestCase):
    def test_core_assets_exist(self):
        paths = [
            ROOT / "core/static/js/datatable/portal_dt_font_size.js",
            ROOT / "core/static/js/datatable/portal_dt_columns.js",
            ROOT / "core/static/js/datatable/portal_dt_toolbar.js",
            ROOT / "core/static/js/datatable/portal_dt_defaults.js",
            ROOT / "core/static/css/datatable/portal_datatable.css",
        ]
        for p in paths:
            self.assertTrue(p.is_file(), f"missing {p}")

    def test_core_apis_exported(self):
        font = (ROOT / "core/static/js/datatable/portal_dt_font_size.js").read_text(encoding="utf-8")
        cols = (ROOT / "core/static/js/datatable/portal_dt_columns.js").read_text(encoding="utf-8")
        tb = (ROOT / "core/static/js/datatable/portal_dt_toolbar.js").read_text(encoding="utf-8")
        defaults = (ROOT / "core/static/js/datatable/portal_dt_defaults.js").read_text(encoding="utf-8")
        self.assertIn("PortalDtFontSize", font)
        self.assertIn("portal_dt_font_size", font)
        self.assertIn("--portal-dt-font-size", font)
        self.assertIn("PortalDtColumns", cols)
        self.assertIn("metaFromHeader", cols)
        self.assertIn("portal_dt_cols_v1_", cols)
        self.assertIn("safeColumnsAdjust", cols)
        self.assertIn("isTableVisiblyLaidOut", cols)
        self.assertIn("isDataOnlyColumn", cols)
        self.assertIn("_metaCache", cols)
        self.assertIn("isDefinedHiddenInInit", cols)
        self.assertIn("fitScrollColumns", cols)
        self.assertIn("clearDtWidthLocks", cols)
        self.assertIn("clearAoColumnWidths", cols)
        self.assertIn("data-dt-column", cols)
        self.assertIn("captureLabelsFromTableElement", cols)
        self.assertIn("portal_dt_col_labels_v1_", cols)
        self.assertIn("resolveColumnLabel", cols)
        self.assertIn("refreshMenu", cols)
        self.assertIn("Nenhuma coluna disponível", cols)
        dt_js = (ROOT / "login/static/js/dataTables.js").read_text(encoding="utf-8")
        self.assertIn("captureLabelsFromTableElement", dt_js)
        self.assertIn("tblAnalistas", dt_js)
        self.assertIn("PortalDtToolbar", tb)
        self.assertIn("initColsDropdown", tb)
        self.assertIn("data-bs-auto-close", tb)
        self.assertIn("dtcc-dropdown", tb)
        self.assertIn("refreshMenu", tb)
        self.assertIn("Limpar Filtros", tb)
        self.assertIn("PortalDt.clearFilters", tb)
        self.assertIn("loginClearDtSearchStorage", tb)
        self.assertIn("PortalDt", defaults)
        self.assertIn("ccSearchList", defaults)
        self.assertIn("ccOrderOnly", defaults)
        self.assertIn("languagePtBr", defaults)
        self.assertIn("clearFilters", defaults)
        self.assertIn("ccSearchClear", defaults)

    def test_login_defaults_uses_portal_dt(self):
        src = (ROOT / "login/static/js/login_datatables_defaults.js").read_text(encoding="utf-8")
        self.assertIn("PortalDt.ccSearchList", src)
        self.assertIn("PortalDt.languagePtBr", src)
        self.assertIn("PortalDt.orderingSilent", src)

    def test_admin_inv_delegates_portal_dt(self):
        src = (
            ROOT / "prodesp/static/js/script_admin_inventory_common.js"
        ).read_text(encoding="utf-8")
        self.assertIn("PortalDt.ccSearchList", src)
        self.assertIn("PortalDt.languagePtBr", src)

    def test_prodesp_fila_dashboard_use_portal_dt(self):
        base = (ROOT / "prodesp/templates/base_prodesp.html").read_text(encoding="utf-8")
        self.assertIn("portal_dt_defaults.js", base)
        self.assertLess(
            base.index("columnControl.dataTables.js"),
            base.index("portal_dt_defaults.js"),
        )
        fila = (ROOT / "prodesp/static/js/script_atendimentos_prodesp.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("PortalDt.ccSearchList", fila)
        self.assertIn("PortalDt.ccOrderOnly", fila)
        self.assertIn("PortalDt.languagePtBr", fila)
        self.assertIn("prodespDtCcSearchList()", fila)
        self.assertIn("PRODESP_STATUS_FILTER_OPTIONS", fila)
        gestao = (
            ROOT / "prodesp/static/js/script_gestao_atendimentos_prodesp.js"
        ).read_text(encoding="utf-8")
        self.assertIn("PortalDt.ccSearchList", gestao)
        self.assertIn("PortalDt.ccOrderOnly", gestao)
        self.assertIn("PortalDt.languagePtBr", gestao)
        self.assertIn("prodespGestaoDtCcSearchList()", gestao)
        self.assertNotIn(
            "cdn.datatables.net/plug-ins/2.3.2/i18n/pt-BR.json",
            gestao,
        )

    def test_login_defaults_no_layout_clear_button(self):
        src = (ROOT / "login/static/js/login_datatables_defaults.js").read_text(encoding="utf-8")
        self.assertIn("LoginDt", src)
        self.assertIn("mountStandardToolbar", src)
        # Layout padrão não deve mais embutir o botão DT loginSearchClear
        layout_block = re.search(
            r"global\.LOGIN_DT_LAYOUT\s*=\s*\{(.*?)\};",
            src,
            re.S,
        )
        self.assertIsNotNone(layout_block)
        self.assertNotIn("loginSearchClear", layout_block.group(1))
        no_search = re.search(
            r"global\.LOGIN_DT_LAYOUT_NO_SEARCH\s*=\s*\{(.*?)\};",
            src,
            re.S,
        )
        self.assertIsNotNone(no_search)
        self.assertNotIn("loginSearchClear", no_search.group(1))

    def test_base_includes_toolkit_before_page_scripts(self):
        base = (ROOT / "login/templates/base.html").read_text(encoding="utf-8")
        self.assertIn("/core/static/css/datatable/portal_datatable.css", base)
        self.assertIn("/core/static/js/datatable/portal_dt_font_size.js", base)
        self.assertIn("/core/static/js/datatable/portal_dt_columns.js", base)
        self.assertIn("/core/static/js/datatable/portal_dt_toolbar.js", base)
        self.assertIn("/core/static/js/datatable/portal_dt_defaults.js", base)
        # Toolkit no base; defaults continuam por página (depois do block scripts order)
        self.assertLess(
            base.index("portal_dt_defaults.js"),
            base.index("{% block scripts %}"),
        )

    def test_wire_callbacks_present(self):
        checks = [
            (ROOT / "login/static/js/dataTables.js", "limparFiltrosGlobais"),
            (ROOT / "login/static/js/painel_analista.js", "recarregarKpiAnalista"),
            (ROOT / "login/static/js/admin_dashboard_extras.js", "carregarSegLoginEventos"),
            (ROOT / "login/static/js/admin_governance.js", "carregarGovernanca"),
            (ROOT / "login/static/js/admin_saude_banco.js", "carregarSaudeBanco"),
            (ROOT / "login/templates/pages/admin_dashboard.html", "limparFiltrosLogNav"),
        ]
        for path, needle in checks:
            text = path.read_text(encoding="utf-8")
            self.assertIn("registrarAjusteColunasDataTable", text)
            self.assertIn("onRefresh", text)
            self.assertIn(needle, text, f"{path.name} missing {needle}")

    def test_css_neutral_classes(self):
        css = (ROOT / "core/static/css/datatable/portal_datatable.css").read_text(encoding="utf-8")
        self.assertIn(".portal-dt-toolbar", css)
        self.assertIn("--portal-dt-font-size", css)
        self.assertIn("#343a40", css)
        self.assertIn(".portal-dt-acoes", css)
        self.assertIn(".btn-icon", css)
        self.assertIn("--portal-dt-th-padding-y", css)
        self.assertIn("th.col-acoes .dt-column-title", css)
        self.assertIn("--portal-dt-acoes-width", css)
        self.assertIn("opacity: 0 !important", css)
        self.assertIn("border-top-left-radius", css)
        self.assertIn("border-bottom-left-radius", css)
        self.assertIn("border-bottom-right-radius", css)
        self.assertIn("--portal-dt-header-radius", css)
        self.assertIn("--portal-dt-stripe-bg", css)
        self.assertIn("nth-child(even)", css)
        self.assertIn("border-collapse: separate", css)
        self.assertIn("select2-container--bootstrap-5", css)
        self.assertIn("--portal-dt-select2-bg", css)
        self.assertIn("dt-processing", css)
        self.assertIn("dt-scroll-body thead .select2", css)
        self.assertIn("dataTables_empty", css)
        self.assertIn("td.dt-empty", css)
        self.assertIn("--dtcc-button_opacity: 0", css)
        self.assertIn("body div.dtcc-dropdown", css)
        self.assertIn("word-break: break-word", css)
        self.assertNotIn("prodesp-", css)

    def test_base_single_bootstrap(self):
        base = (ROOT / "login/templates/base.html").read_text(encoding="utf-8")
        self.assertEqual(base.count("bootstrap.bundle.min.js"), 1)
        self.assertNotIn("bootstrap.min.js", base)
        self.assertNotIn("@popperjs/core", base)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PortalDtToolbarSmoke)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
