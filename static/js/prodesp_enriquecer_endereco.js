/**
 * @file prodesp/static/js/prodesp_enriquecer_endereco.js
 * @module PRODESP — Modal (endereço)
 *
 * Finalidade:
 *   Botão «Completar endereço»: preenche número, bairro, CEP e lat/long vazios
 *   ou placeholder nos modais de create/edit, via API de geocodificação/enriquecimento.
 *   Com atendimento iniciado, dispara enriquecimento ao alterar endereço/CEP/número.
 *
 * Telas:
 *   - atendimentos_prodesp.html
 *
 * Depende de:
 *   - IDs de campo edit* e create* no template
 */
(function () {
  const FIELD_MAP = {
    edit: {
      endereco: "editEndereco",
      numero: "editNumero",
      bairro: "editBairro",
      municipio: "editMunicipio",
      estado: "editEstado",
      cep: "editCep",
      latitude: "editLatitude",
      longitude: "editLongitude",
    },
    create: {
      endereco: "createEndereco",
      numero: "createNumero",
      bairro: "createBairro",
      municipio: "createMunicipio",
      estado: "createEstado",
      cep: "createCep",
      latitude: "createLatitude",
      longitude: "createLongitude",
    },
  };

  const AUTO_TRIGGER_KEYS = ["endereco", "numero", "cep"];
  let suppressEnriquecerAuto = false;
  let enriquecerAutoTimeout = null;

  function val(id) {
    const el = document.getElementById(id);
    if (!el) return "";
    return (el.value || "").trim();
  }

  function setVal(id, v) {
    const el = document.getElementById(id);
    if (!el || v == null || String(v).trim() === "") return;
    el.value = String(v).trim();
    if (window.maskInstances && window.maskInstances[id]) {
      try {
        window.maskInstances[id].value = el.value;
      } catch (e) {
        /* ignore */
      }
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function prodespAtendimentoIniciadoParaEnriquecer(mode) {
    if (mode === "edit") {
      const id = document.getElementById("editAtendimentoId")?.value;
      const st = (document.getElementById("editStatus")?.value || "").trim();
      return !!id && st && st !== "Agendado";
    }
    return !!window.currentCreateModalAtendimentoId;
  }

  function prodespScheduleEnriquecerAuto(mode) {
    if (suppressEnriquecerAuto || !prodespAtendimentoIniciadoParaEnriquecer(mode)) return;
    const map = FIELD_MAP[mode];
    if (!map) return;
    if (!val(map.endereco) && !val(map.cep)) return;

    clearTimeout(enriquecerAutoTimeout);
    enriquecerAutoTimeout = setTimeout(() => {
      prodespEnriquecerEndereco(mode, { silent: true });
    }, 900);
  }

  async function prodespEnriquecerEndereco(mode, opts) {
    const silent = !!(opts && opts.silent);
    const map = FIELD_MAP[mode];
    if (!map) return;

    const btn =
      mode === "edit"
        ? document.getElementById("btnEnriquecerEnderecoEdit")
        : document.getElementById("btnEnriquecerEnderecoCreate");

    const payload = {
      endereco: val(map.endereco),
      numero: val(map.numero),
      bairro: val(map.bairro),
      municipio: val(map.municipio),
      estado: val(map.estado),
      cep: val(map.cep),
      latitude: val(map.latitude),
      longitude: val(map.longitude),
    };

    if (!payload.endereco && !payload.cep) {
      if (!silent && typeof showToast === "function") {
        showToast("Informe o endereço ou o CEP para buscar os dados.", "warning");
      }
      return;
    }

    const prevHtml = btn ? btn.innerHTML : "";
    if (btn) {
      btn.disabled = true;
      btn.innerHTML =
        '<span class="spinner-border spinner-border-sm me-1"></span>Buscando...';
    }

    try {
      const res = await fetch("/prodesp/api/enriquecer-endereco", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!data.success) {
        if (!silent && typeof showToast === "function") {
          showToast(data.message || "Falha ao completar endereço.", "danger");
        }
        return;
      }

      const updates = data.updates || {};
      let applied = 0;
      suppressEnriquecerAuto = true;
      try {
        Object.keys(updates).forEach((key) => {
          const fieldId = map[key];
          if (fieldId) {
            setVal(fieldId, updates[key]);
            applied += 1;
          }
        });
      } finally {
        setTimeout(() => {
          suppressEnriquecerAuto = false;
        }, 150);
      }

      if (silent) return;

      if (typeof showToast === "function") {
        const hasWarnings = data.warnings && data.warnings.length > 0;
        const isPartial = data.partial === true;
        let toastType = "info";
        if (applied > 0 && !isPartial && !hasWarnings) {
          toastType = "success";
        } else if (applied > 0 && (isPartial || hasWarnings)) {
          toastType = "warning";
        } else if (applied === 0 && hasWarnings) {
          toastType = "warning";
        }
        showToast(
          data.message ||
            (hasWarnings ? data.warnings.join(" ") : "Nenhum campo precisava ser preenchido."),
          toastType
        );
      }
    } catch (err) {
      console.error("prodespEnriquecerEndereco:", err);
      if (!silent && typeof showToast === "function") {
        showToast("Erro de comunicação ao buscar endereço.", "danger");
      }
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = prevHtml;
      }
    }
  }

  function prodespBindEnriquecerAutoListeners() {
    ["edit", "create"].forEach((mode) => {
      const map = FIELD_MAP[mode];
      if (!map) return;
      AUTO_TRIGGER_KEYS.forEach((key) => {
        const el = document.getElementById(map[key]);
        if (!el || el.dataset.prodespEnriquecerBound === "1") return;
        el.dataset.prodespEnriquecerBound = "1";
        el.addEventListener("input", () => prodespScheduleEnriquecerAuto(mode));
        el.addEventListener("change", () => prodespScheduleEnriquecerAuto(mode));
      });
    });
  }

  function prodespInitEnriquecerEndereco() {
    const btnEdit = document.getElementById("btnEnriquecerEnderecoEdit");
    const btnCreate = document.getElementById("btnEnriquecerEnderecoCreate");
    if (btnEdit && btnEdit.dataset.prodespEnriquecerInit !== "1") {
      btnEdit.dataset.prodespEnriquecerInit = "1";
      btnEdit.addEventListener("click", function () {
        prodespEnriquecerEndereco("edit");
      });
    }
    if (btnCreate && btnCreate.dataset.prodespEnriquecerInit !== "1") {
      btnCreate.dataset.prodespEnriquecerInit = "1";
      btnCreate.addEventListener("click", function () {
        prodespEnriquecerEndereco("create");
      });
    }
    prodespBindEnriquecerAutoListeners();
  }

  document.addEventListener("DOMContentLoaded", prodespInitEnriquecerEndereco);
  if (document.readyState !== "loading") {
    prodespInitEnriquecerEndereco();
  }

  window.prodespEnriquecerEndereco = prodespEnriquecerEndereco;
  window.prodespInitEnriquecerEndereco = prodespInitEnriquecerEndereco;
})();
