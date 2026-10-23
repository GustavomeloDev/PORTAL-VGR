/**
 * Botão «Completar endereço» (DMA / VGR / FUST).
 * POST JSON no endpoint do módulo; aplica updates nos IDs informados.
 * Mensagens da API vão para textContent (sem innerHTML).
 *
 * Ganchos opcionais (retrocompatíveis — quem não passa segue igual):
 *   canRun()                 → string = bloqueia com aviso; falsy = segue.
 *   onApplied(applied, data) → chamado após aplicar os updates nos campos;
 *                              `applied` = só as chaves efetivamente preenchidas.
 *                              Pode devolver Promise: o botão fica em
 *                              "Buscando..." até ela terminar.
 */
(function (global) {
  "use strict";

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    var hidden = document.querySelector("input[name='csrf_token']");
    return hidden ? hidden.value : "";
  }

  function el(id) {
    return id ? document.getElementById(id) : null;
  }

  function val(id) {
    var node = el(id);
    return node ? String(node.value || "").trim() : "";
  }

  function setVal(id, v) {
    var node = el(id);
    if (!node || v == null || String(v).trim() === "") return false;
    node.value = String(v).trim();
    node.dispatchEvent(new Event("input", { bubbles: true }));
    node.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  function setStatus(statusEl, text, kind) {
    if (!statusEl) return;
    statusEl.textContent = text || "";
    statusEl.classList.remove("text-danger", "text-success", "text-warning", "text-muted");
    if (kind === "error") statusEl.classList.add("text-danger");
    else if (kind === "ok") statusEl.classList.add("text-success");
    else if (kind === "warn") statusEl.classList.add("text-warning");
    else statusEl.classList.add("text-muted");
  }

  function toast(opts, message, ok) {
    if (typeof opts.onMessage === "function") {
      opts.onMessage(message, ok);
      return;
    }
    if (window.VgrDt && typeof window.VgrDt.toast === "function") {
      window.VgrDt.toast(message, ok !== false);
    }
  }

  function enriquecer(opts, btn, statusEl) {
    var fields = opts.fields || {};

    if (typeof opts.canRun === "function") {
      var bloqueio = opts.canRun();
      if (bloqueio) {
        setStatus(statusEl, String(bloqueio), "warn");
        toast(opts, String(bloqueio), false);
        return;
      }
    }

    var payload = {
      endereco: val(fields.endereco),
      numero: val(fields.numero),
      bairro: val(fields.bairro),
      municipio: val(fields.municipio) || val(fields.cidade),
      estado: val(fields.estado) || val(fields.uf),
      cidade: val(fields.cidade) || val(fields.municipio),
      uf: val(fields.uf) || val(fields.estado),
      cep: val(fields.cep),
      latitude: val(fields.latitude),
      longitude: val(fields.longitude),
    };
    if (!payload.endereco && !payload.cep) {
      var need = "Informe o endereço ou o CEP para buscar os dados.";
      setStatus(statusEl, need, "warn");
      toast(opts, need, false);
      return;
    }

    var prevHtml = btn ? btn.innerHTML : "";
    if (btn) {
      btn.disabled = true;
      btn.innerHTML =
        '<span class="spinner-border spinner-border-sm me-1"></span>Buscando...';
    }
    setStatus(statusEl, "Consultando ViaCEP / Nominatim…", "");

    fetch(opts.endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data || {} };
        });
      })
      .then(function (pack) {
        var data = pack.data;
        if (!pack.ok || data.success === false) {
          var fail = data.message || "Falha ao completar endereço.";
          setStatus(statusEl, fail, "error");
          toast(opts, fail, false);
          return;
        }
        var updates = data.updates || {};
        var applied = {};
        Object.keys(updates).forEach(function (key) {
          if (fields[key] && setVal(fields[key], updates[key])) {
            applied[key] = String(updates[key]).trim();
          }
        });
        var msg = data.message || "Endereço conferido.";
        var hasWarn = data.warnings && data.warnings.length;
        var kind = hasWarn || data.partial ? "warn" : "ok";
        setStatus(statusEl, msg, kind);
        toast(opts, msg, !hasWarn && !data.partial);

        if (typeof opts.onApplied === "function") {
          /* Erro do gancho fica no gancho: não vira "erro de comunicação". */
          return Promise.resolve()
            .then(function () {
              return opts.onApplied(applied, data);
            })
            .catch(function (err) {
              console.error("[PortalEnriquecerEndereco] onApplied:", err);
            });
        }
      })
      .catch(function () {
        var fail = "Erro de comunicação ao buscar endereço.";
        setStatus(statusEl, fail, "error");
        toast(opts, fail, false);
      })
      .finally(function () {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = prevHtml;
        }
      });
  }

  function bind(opts) {
    opts = opts || {};
    var btn = el(opts.buttonId);
    if (!btn || btn.dataset.portalEnriquecerBound === "1") return;
    btn.dataset.portalEnriquecerBound = "1";
    var statusEl = el(opts.statusId);
    btn.addEventListener("click", function () {
      enriquecer(opts, btn, statusEl);
    });
  }

  global.PortalEnriquecerEndereco = { bind: bind };
})(window);
