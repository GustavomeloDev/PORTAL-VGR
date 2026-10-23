(function () {
  "use strict";
  const V = window.VgrDt;
  const id = window.VGR_CLIENTE_ID;
  if (!V || !id || typeof $ === "undefined" || !$.fn.DataTable) return;

  const cc = window.PortalDt ? window.PortalDt.ccSearchList() : [];

  const apiU = $("#tblVgrClienteUnidades").DataTable(
    V.baseOpts({
      order: [[1, "asc"]],
      ajax: V.clientAjax("/vgr/api/clientes/" + id + "/unidades"),
      columns: [
        { data: "id_unidade" },
        {
          data: "nome_unidade",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "id_vgr",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "tipo_unidade",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "cidade",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "ha",
          render: function (d) {
            return V.yesNo(d);
          },
        },
        {
          data: "ativo",
          render: function (d) {
            return V.yesNo(d);
          },
        },
        {
          data: "id_unidade",
          orderable: false,
          searchable: false,
          className: "col-acoes portal-dt-acoes",
          render: function (uid) {
            return V.acoesAbrir("/vgr/unidades/" + uid);
          },
        },
      ],
      columnDefs: [
        { targets: [1, 2, 3, 4, 5, 6], columnControl: cc },
        { targets: [-1], columnControl: [] },
      ],
    })
  );
  V.mountToolbar("tblVgrClienteUnidades", apiU);

  const apiAg = $("#tblVgrClienteAg").DataTable(
    V.baseOpts({
      order: [[0, "desc"]],
      ajax: V.clientAjax("/vgr/api/clientes/" + id + "/agendamentos"),
      columns: [
        { data: "id_agendamento" },
        {
          data: "nome_unidade",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "status_agendamento",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "data_agendamento",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "tipo",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "analista_destino",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "ativo",
          render: function (d) {
            return V.yesNo(d);
          },
        },
      ],
      columnDefs: [{ targets: [1, 2, 3, 4, 5, 6], columnControl: cc }],
    })
  );
  V.mountToolbar("tblVgrClienteAg", apiAg);

  const apiAt = $("#tblVgrClienteAt").DataTable(
    V.baseOpts({
      order: [[0, "desc"]],
      ajax: V.clientAjax("/vgr/api/clientes/" + id + "/atendimentos"),
      columns: [
        { data: "id_atendimento" },
        {
          data: "nome_unidade",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "status_atendimento",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "substatus_atendimento",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "analista_atuante",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "id_agendamento",
          render: function (d, t) {
            return V.renderText(d, t);
          },
        },
        {
          data: "ativo",
          render: function (d) {
            return V.yesNo(d);
          },
        },
      ],
      columnDefs: [{ targets: [1, 2, 3, 4, 5, 6], columnControl: cc }],
    })
  );
  V.mountToolbar("tblVgrClienteAt", apiAt);

  var btnOff = document.getElementById("btnVgrCliDetalheDesativar");
  if (btnOff) {
    btnOff.addEventListener("click", function () {
      var cid = this.getAttribute("data-id");
      if (!window.confirm("Desativar cliente #" + cid + "?")) return;
      V.jsonFetch("/vgr/api/clientes/" + encodeURIComponent(cid) + "/desativar", {
        method: "POST",
        body: "{}",
      }).then(function (res) {
        if (res.status >= 400 || !res.d.success) {
          V.toast((res.d && res.d.message) || "Falha ao desativar.", false);
          return;
        }
        window.location.reload();
      });
    });
  }
  var btnOn = document.getElementById("btnVgrCliDetalheReativar");
  if (btnOn) {
    btnOn.addEventListener("click", function () {
      var cid = this.getAttribute("data-id");
      V.jsonFetch("/vgr/api/clientes/" + encodeURIComponent(cid) + "/reativar", {
        method: "POST",
        body: "{}",
      }).then(function (res) {
        if (res.status >= 400 || !res.d.success) {
          V.toast((res.d && res.d.message) || "Falha ao reativar.", false);
          return;
        }
        window.location.reload();
      });
    });
  }
})();
