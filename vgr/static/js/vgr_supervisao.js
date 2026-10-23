(function () {
  "use strict";
  const V = window.VgrDt;
  if (!V) return;

  function set(id, n) {
    var el = document.getElementById(id);
    if (el) el.textContent = String(n);
  }

  Promise.all([
    V.jsonFetch("/vgr/api/atendimentos?modo=gestao"),
    V.jsonFetch("/vgr/api/agendamentos?modo=gestao"),
  ]).then(function (pair) {
    var atend = (pair[0].d && pair[0].d.data) || [];
    var ags = (pair[1].d && pair[1].d.data) || [];
    var ativosAt = atend.filter(function (r) {
      return Number(r.ativo) === 1;
    });
    var ativosAg = ags.filter(function (r) {
      return Number(r.ativo) === 1;
    });
    set("vgrSupAtend", ativosAt.length);
    set("vgrSupAg", ativosAg.length);
    set(
      "vgrSupGestao",
      ativosAt.filter(function (r) {
        return (
          r.substatus_atendimento === "Aguarda Gestão" ||
          r.substatus_atendimento === "Triagem"
        );
      }).length
    );
    set(
      "vgrSupAgendado",
      ativosAg.filter(function (r) {
        return r.status_agendamento === "Agendado";
      }).length
    );
  });
})();
