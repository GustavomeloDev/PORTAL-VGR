/**
 * Defaults neutros DataTables + ColumnControl (Portal).
 * Carregar depois do plugin ColumnControl e antes dos scripts de página.
 *
 * Regras:
 * - Coluna filtrável → searchList (não searchText; sem dropdown aninhado).
 * - ajaxOnly:false no client-side → opções no 1º draw; abertura imediata.
 * - JSON columnControl só se completo ou lista fixa; parcial + ajaxOnly:true esconde colunas.
 */
(function (global) {
  "use strict";

  /**
   * @param {{ ajaxOnly?: boolean }} [opts]
   * @returns {Array}
   */
  function ccSearchList(opts) {
    const ajaxOnly = opts && opts.ajaxOnly === true;
    return [
      [
        { extend: "searchList", ajaxOnly: ajaxOnly },
        "spacer",
        "orderAsc",
        "orderDesc",
        "orderClear",
      ],
    ];
  }

  /** Colunas só ordenáveis (ex.: tempos) — sem checklist. */
  function ccOrderOnly() {
    return [["orderAsc", "orderDesc", "orderClear"]];
  }

  function orderingSilent() {
    return { indicators: false, handler: false };
  }

  function languageColumnControl() {
    return {
      search: "Pesquisar colunas",
      orderAsc: "Ordenar asc",
      orderDesc: "Ordenar desc",
      orderClear: "Limpar ordenação",
      buttons: {
        search: "Pesquisar colunas",
        searchPlaceholder: "Digite para buscar...",
      },
      list: {
        all: "Selecionar tudo",
        empty: "Vazio",
        none: "Limpar seleção",
        search: "Buscar...",
      },
    };
  }

  /**
   * i18n pt-BR inline (sem fetch ao CDN na init).
   * @returns {object}
   */
  function languagePtBr() {
    return {
      emptyTable: "Nenhum registro encontrado",
      info: "Mostrando de _START_ até _END_ de _TOTAL_ registros",
      infoEmpty: "Mostrando 0 até 0 de 0 registro(s)",
      infoFiltered: "(Filtrados de _MAX_ registros)",
      infoThousands: ".",
      lengthMenu: "Exibir _MENU_ resultados por página",
      loadingRecords: "Carregando...",
      processing: "Carregando...",
      search: "🔍",
      searchPlaceholder: "Buscar registros",
      zeroRecords: "Nenhum registro encontrado",
      decimal: ",",
      thousands: ".",
      paginate: { next: "›", previous: "‹", first: "«", last: "»" },
      columnControl: languageColumnControl(),
    };
  }

  /**
   * columnDefs com searchList nos targets (excluir Ações no caller).
   * @param {number|number[]} targets
   * @param {object} [extra] — merge em cada def (ex.: { orderable: false })
   */
  function columnDefsSearchList(targets, extra) {
    return [
      Object.assign(
        {
          targets: targets,
          columnControl: ccSearchList(),
        },
        extra || {}
      ),
    ];
  }

  /**
   * Limpa busca global + filtros de coluna + ColumnControl (searchList).
   * Usado pela toolbar do core (login e PRODESP). Sem dependência do módulo login.
   * @param {object} api — DataTables API
   * @param {{ skipDraw?: boolean }} [opts]
   */
  function clearFilters(api, opts) {
    if (!api) return;
    opts = opts || {};
    try {
      api.search("");
    } catch (e0) {
      /* ignore */
    }
    try {
      const container = api.table().container();
      if (container) {
        const inp = container.querySelector(".dt-search input");
        if (inp) inp.value = "";
      }
    } catch (e1) {
      /* ignore */
    }
    try {
      if (typeof api.columns().ccSearchClear === "function") {
        api.columns().ccSearchClear();
      }
    } catch (e2) {
      /* fallback abaixo */
    }
    try {
      api.columns().every(function () {
        this.search("");
        try {
          this.search.fixed("dtcc", "");
        } catch (e3) {
          /* sem fixed */
        }
        try {
          this.search.fixed("dtcc-list", "");
        } catch (e4) {
          /* sem searchList */
        }
      });
    } catch (e5) {
      /* ignore */
    }
    if (!opts.skipDraw) {
      try {
        api.draw(false);
      } catch (e6) {
        /* ignore */
      }
    }
  }

  global.PortalDt = {
    ccSearchList: ccSearchList,
    ccOrderOnly: ccOrderOnly,
    orderingSilent: orderingSilent,
    languageColumnControl: languageColumnControl,
    languagePtBr: languagePtBr,
    columnDefsSearchList: columnDefsSearchList,
    clearFilters: clearFilters,
  };
})(typeof window !== "undefined" ? window : globalThis);
