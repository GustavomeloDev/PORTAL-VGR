/**
 * Regras de perfil multi-departamento (principal + usuario_departamento_extra).
 * Fonte única no front: LOGGED_IN_USER_DEPARTAMENTOS (= departamentos_todos()).
 * IMPLANTAÇÃO/NOC prevalece sobre restrições de SUPERVISORES/GP/TBRA/Agendamento em filas.
 *
 * Cutover: SUPERVISORES, GP e TBRA (mesmo acesso visual). NOC espelha IMPLANTAÇÃO.
 */
(function (global) {
  const PERFIS_GESTAO = ["SUPERVISORES", "GP", "TBRA"];
  const PERFIS_IMPLANTACAO = ["IMPLANTAÇÃO", "NOC"];

  function portalDepartamentosUsuario() {
    if (
      typeof LOGGED_IN_USER_DEPARTAMENTOS !== "undefined" &&
      Array.isArray(LOGGED_IN_USER_DEPARTAMENTOS)
    ) {
      return LOGGED_IN_USER_DEPARTAMENTOS;
    }
    if (
      typeof global.AppConfig !== "undefined" &&
      global.AppConfig.user &&
      Array.isArray(global.AppConfig.user.departments)
    ) {
      return global.AppConfig.user.departments;
    }
    if (
      typeof global.currentUser !== "undefined" &&
      Array.isArray(global.currentUser.departamentos_todos)
    ) {
      return global.currentUser.departamentos_todos;
    }
    return [];
  }

  function portalUsuarioTemDepartamento(nome) {
    const alvo = (nome || "").trim();
    if (!alvo) {
      return false;
    }
    return portalDepartamentosUsuario().indexOf(alvo) >= 0;
  }

  function portalUsuarioTemImplantacao() {
    const depts = portalDepartamentosUsuario();
    for (let i = 0; i < PERFIS_IMPLANTACAO.length; i++) {
      if (depts.indexOf(PERFIS_IMPLANTACAO[i]) >= 0) {
        return true;
      }
    }
    return false;
  }

  function portalUsuarioTemSupervisores() {
    return portalUsuarioTemDepartamento("SUPERVISORES");
  }

  function portalUsuarioTemGp() {
    return portalUsuarioTemDepartamento("GP");
  }

  function portalUsuarioTemTbra() {
    return portalUsuarioTemDepartamento("TBRA");
  }

  function portalUsuarioTemNoc() {
    return portalUsuarioTemDepartamento("NOC");
  }

  /** SUPERVISORES, GP ou TBRA — privilégios de gestão compartilhados (cutover visual). */
  function portalUsuarioTemSupervisoresOuGp() {
    const depts = portalDepartamentosUsuario();
    for (let i = 0; i < PERFIS_GESTAO.length; i++) {
      if (depts.indexOf(PERFIS_GESTAO[i]) >= 0) {
        return true;
      }
    }
    return false;
  }

  /** Restrição de fila (ex.: só Triagem): SUPERVISORES/GP/TBRA/Agendamento sem IMPLANTAÇÃO/NOC. */
  function portalUsuarioUsaRegrasGpAgendamentoRestritas() {
    if (portalUsuarioTemImplantacao()) {
      return false;
    }
    return (
      portalUsuarioTemDepartamento("AGENDAMENTO") ||
      portalUsuarioTemSupervisoresOuGp()
    );
  }

  global.portalDepartamentosUsuario = portalDepartamentosUsuario;
  global.portalUsuarioTemDepartamento = portalUsuarioTemDepartamento;
  global.portalUsuarioTemImplantacao = portalUsuarioTemImplantacao;
  global.portalUsuarioTemSupervisores = portalUsuarioTemSupervisores;
  global.portalUsuarioTemGp = portalUsuarioTemGp;
  global.portalUsuarioTemTbra = portalUsuarioTemTbra;
  global.portalUsuarioTemNoc = portalUsuarioTemNoc;
  global.portalUsuarioTemSupervisoresOuGp = portalUsuarioTemSupervisoresOuGp;
  /** Alias legados de API JS (painéis): mesmo comportamento que SupervisoresOuGp. */
  global.portalUsuarioTemSupervisoresGp = portalUsuarioTemSupervisoresOuGp;
  global.portalIsSupervisorGp = portalUsuarioTemSupervisoresOuGp;
  global.portalUsuarioUsaRegrasGpAgendamentoRestritas =
    portalUsuarioUsaRegrasGpAgendamentoRestritas;
})(typeof window !== "undefined" ? window : globalThis);
