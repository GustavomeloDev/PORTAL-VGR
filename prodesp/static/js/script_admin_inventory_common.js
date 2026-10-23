/**
 * Utilitários compartilhados — Admin Equipamentos / Links (PortalDt).
 * KPIs, typeahead de unidade, contexto, sync por data_revision, campos dinâmicos.
 */
(function (global) {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /**
   * Toast inventário. opts: { durationMs, position: 'top'|'bottom', tone }
   * position top + duração maior = útil p/ Modelos/Versões (listas longas).
   */
  function toast(msg, ok, opts) {
    opts = opts || {};
    const durationMs = opts.durationMs != null ? Number(opts.durationMs) : 4500;
    const position = opts.position === "top" ? "top" : "bottom";
    const tone =
      opts.tone ||
      (ok === false ? "danger" : ok ? "success" : "info");
    if (typeof global.showProdespToast === "function" && !opts.forceSoft) {
      global.showProdespToast(msg, tone === "danger" ? "danger" : tone === "warning" ? "warning" : "success");
      return;
    }
    /* Fallback não-bloqueante — alert() trava o poll e a carga da tabela. */
    try {
      let el = document.getElementById("adminInvSoftToast");
      if (!el) {
        el = document.createElement("div");
        el.id = "adminInvSoftToast";
        el.setAttribute("role", "status");
        el.style.cssText =
          "position:fixed;z-index:1080;padding:.75rem 1rem;border-radius:.5rem;" +
          "box-shadow:0 4px 16px rgba(0,0,0,.2);font-size:.875rem;line-height:1.35;" +
          "color:#fff;opacity:0;transition:opacity .2s;pointer-events:none;";
        document.body.appendChild(el);
      }
      if (position === "top") {
        el.style.top = "1rem";
        el.style.bottom = "auto";
        el.style.left = "50%";
        el.style.right = "auto";
        el.style.transform = "translateX(-50%)";
        el.style.maxWidth = "min(42rem, calc(100vw - 2rem))";
      } else {
        el.style.top = "auto";
        el.style.bottom = "1rem";
        el.style.left = "auto";
        el.style.right = "1rem";
        el.style.transform = "none";
        el.style.maxWidth = "22rem";
      }
      el.style.background =
        tone === "danger" ? "#dc3545" : tone === "warning" ? "#fd7e14" : "#198754";
      el.textContent = String(msg || "");
      el.style.opacity = "1";
      clearTimeout(el._hideTimer);
      el._hideTimer = setTimeout(function () {
        el.style.opacity = "0";
      }, Math.max(2000, durationMs || 4500));
    } catch (_e) {
      /* ignore */
    }
  }

  function normalizeStatusKey(status) {
    return String(status || "")
      .trim()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }

  /** Concluído + Concluído Parcial — cobrança de correção. */
  function statusIsCobranca(status) {
    return normalizeStatusKey(status).indexOf("conclu") >= 0;
  }

  /** Em Atendimento — cobre substatus ativos do portal. */
  function statusIsEmAtendimento(status) {
    return normalizeStatusKey(status).indexOf("em atendimento") >= 0;
  }

  function statusIsQuebra(status) {
    return normalizeStatusKey(status).indexOf("quebra") >= 0;
  }

  /** Contagem top (modelo/versão): toast no topo, ~8s. */
  function toastTopCounts(prefix, map, opts) {
    opts = opts || {};
    const topN = opts.topN != null ? opts.topN : 8;
    const top = Object.keys(map || {})
      .map(function (k) {
        return { k: k, n: map[k] };
      })
      .sort(function (a, b) {
        return b.n - a.n;
      });
    if (!top.length) return null;
    toast(
      prefix +
        ": " +
        top
          .slice(0, topN)
          .map(function (x) {
            return x.k + " (" + x.n + ")";
          })
          .join(", "),
      true,
      {
        durationMs: opts.durationMs != null ? opts.durationMs : 8000,
        position: "top",
        tone: "success",
        forceSoft: true,
      }
    );
    return top;
  }

  function jsonFetch(url, opts) {
    const o = Object.assign({ headers: { Accept: "application/json" } }, opts || {});
    if (o.body && !o.headers["Content-Type"]) {
      o.headers["Content-Type"] = "application/json";
    }
    return fetch(url, o).then(async (r) => {
      let d = {};
      try {
        d = await r.json();
      } catch (_e) {
        d = {};
      }
      return { status: r.status, d };
    });
  }

  /** Inferência estrita: só retorna modelo se o serial contiver fragmento conhecido. */
  function inferModeloFromSerialStrict(serial) {
    const rules = global.PRODESP_SERIAL_MODEL_RULES;
    const s = String(serial || "")
      .toUpperCase()
      .replace(/\s/g, "");
    if (!s || !Array.isArray(rules)) return "";
    for (let i = 0; i < rules.length; i++) {
      const frag = rules[i] && rules[i][0];
      const label = rules[i] && rules[i][1];
      if (frag && label && s.indexOf(String(frag).toUpperCase()) >= 0) return label;
    }
    return "";
  }

  /** Inferência de modelo a partir do serial (regras do blueprint). */
  function inferModeloFromSerial(serial) {
    return inferModeloFromSerialStrict(serial) || "FortiGate 40F";
  }

  /**
   * Typeahead de unidade → preenche input hidden/texto com id_vgr.
   * @param {HTMLInputElement} inputEl
   * @param {{ onSelect?: function, hostInputId?: string }} opts
   */
  function bindUnitTypeahead(inputEl, opts) {
    if (!inputEl || inputEl.dataset.adminInvTa === "1") return;
    inputEl.dataset.adminInvTa = "1";
    opts = opts || {};

    const wrap = document.createElement("div");
    wrap.className = "admin-inv-typeahead";
    inputEl.parentNode.insertBefore(wrap, inputEl);
    wrap.appendChild(inputEl);

    const list = document.createElement("ul");
    list.className = "admin-inv-typeahead-list d-none";
    list.setAttribute("role", "listbox");
    wrap.appendChild(list);

    let timer = null;
    let items = [];
    let active = -1;

    function hide() {
      list.classList.add("d-none");
      list.innerHTML = "";
      items = [];
      active = -1;
    }

    function render() {
      list.innerHTML = "";
      if (!items.length) {
        list.classList.add("d-none");
        return;
      }
      items.forEach(function (it, idx) {
        const li = document.createElement("li");
        li.setAttribute("role", "option");
        if (idx === active) li.classList.add("active");
        li.innerHTML =
          "<div><strong>" +
          esc(it.id_vgr) +
          "</strong> · " +
          esc(it.acronimo || "—") +
          "</div>" +
          '<div class="muted">' +
          esc(it.hostname || "") +
          (it.hostname && it.nome ? " · " : "") +
          esc(it.nome || "") +
          "</div>";
        li.addEventListener("mousedown", function (e) {
          e.preventDefault();
          pick(it);
        });
        list.appendChild(li);
      });
      list.classList.remove("d-none");
    }

    function pick(it) {
      inputEl.value = it.id_vgr || "";
      if (opts.hostInputId) {
        const h = document.getElementById(opts.hostInputId);
        if (h) h.value = it.hostname || "";
      }
      if (typeof opts.onSelect === "function") opts.onSelect(it);
      hide();
    }

    function search(q) {
      if (q.length < 2) {
        hide();
        return;
      }
      jsonFetch(
        "/prodesp/api/admin/unidades/search?q=" + encodeURIComponent(q) + "&limit=20"
      ).then(function (res) {
        if (res.status >= 400 || !res.d || !res.d.success) {
          hide();
          return;
        }
        items = res.d.data || [];
        active = items.length ? 0 : -1;
        render();
      });
    }

    inputEl.addEventListener("input", function () {
      const q = inputEl.value.trim();
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () {
        search(q);
      }, 220);
    });

    inputEl.addEventListener("keydown", function (e) {
      if (list.classList.contains("d-none")) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        active = Math.min(items.length - 1, active + 1);
        render();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        active = Math.max(0, active - 1);
        render();
      } else if (e.key === "Enter" && active >= 0 && items[active]) {
        e.preventDefault();
        pick(items[active]);
      } else if (e.key === "Escape") {
        hide();
      }
    });

    inputEl.addEventListener("blur", function () {
      setTimeout(hide, 150);
    });
  }

  /** Mostra/oculta blocos data-link-type conforme select de tipo.
   *  Redundante Crítico (#adminLkRcWrap / .mpls-vivo-redundante*): só MPLS + VIVO.
   */
  function bindLinkTypeFields(tipoSelectId, rootEl, operadoraSelectId) {
    const sel = document.getElementById(tipoSelectId);
    const opEl = operadoraSelectId ? document.getElementById(operadoraSelectId) : null;
    const root = rootEl || document;
    if (!sel) return { refresh: function () {} };

    function isVivo() {
      if (
        global.ProdespLiveValidation &&
        typeof global.ProdespLiveValidation.isVivoOperadora === "function"
      ) {
        return global.ProdespLiveValidation.isVivoOperadora(opEl ? opEl.value : "");
      }
      return (
        String(opEl ? opEl.value : "")
          .trim()
          .toUpperCase() === "VIVO"
      );
    }

    function apply() {
      const t = (sel.value || "").trim();
      const tUp = t.toUpperCase();
      root.querySelectorAll("[data-link-type], [data-link-vivo-idvgr]").forEach(function (el) {
        const types = String(el.getAttribute("data-link-type") || "")
          .split(/\s+/)
          .filter(Boolean);
        const isRc =
          el.id === "adminLkRcWrap" ||
          el.classList.contains("mpls-vivo-redundante-wrapper") ||
          el.classList.contains("mpls-vivo-redundante");
        const isIdVgrLink =
          el.id === "adminLkIdVgrLinkWrap" || el.getAttribute("data-link-vivo-idvgr") === "1";
        let show = !types.length || !t || types.indexOf(t) >= 0 || types.indexOf(tUp) >= 0;
        if (isRc) {
          show = tUp === "MPLS" && isVivo();
        } else if (isIdVgrLink) {
          show = (tUp === "MPLS" || tUp === "STATIC") && isVivo();
        }
        /* Bootstrap d-flex/d-* usam !important — preferir d-none */
        el.classList.toggle("d-none", !show);
        if (show) {
          el.style.removeProperty("display");
        } else {
          el.style.setProperty("display", "none", "important");
          el.querySelectorAll('input[type="checkbox"]').forEach(function (inp) {
            inp.checked = false;
          });
        }
      });
    }
    sel.addEventListener("change", apply);
    if (opEl) {
      opEl.addEventListener("input", apply);
      opEl.addEventListener("change", apply);
    }
    apply();
    return { refresh: apply };
  }

  function bindSerialModelo(serialId, modeloId, hintId) {
    return bindModeloLockedFromSerial(serialId, modeloId, {
      hintId: hintId,
      descricaoId: null,
    });
  }

  /**
   * Modelo derivado do serial (Blueprint/fila).
   * Travado quando igual ao mapeado; liberado só se divergir (correção via select whitelist).
   */
  function bindModeloLockedFromSerial(serialId, modeloSelectId, opts) {
    opts = opts || {};
    const serialEl = document.getElementById(serialId);
    const modeloEl = document.getElementById(modeloSelectId);
    const hintEl = opts.hintId ? document.getElementById(opts.hintId) : null;
    const descEl = opts.descricaoId ? document.getElementById(opts.descricaoId) : null;
    const unlockBtn = opts.unlockBtnId ? document.getElementById(opts.unlockBtnId) : null;
    if (!serialEl || !modeloEl) return { refresh: function () {} };

    const AUTO_DESC = {
      "FortiGate 40F": "Firewall - Stand Alone",
      "FortiGate 60F": "Firewall - Stand Alone",
      "FortiGate 120G": "Firewall - Stand Alone",
      "FortiGate 900G": "Firewall - Stand Alone",
      "FortiGate 3200F": "Firewall - Stand Alone",
      "FortiGate 3700F": "Firewall - Stand Alone",
      "FortiGate 600F": "Firewall - Stand Alone",
      "FortiSwitch 2048F": "Switch",
    };

    function ensureOption(val) {
      if (!val) return;
      let found = false;
      for (let i = 0; i < modeloEl.options.length; i++) {
        if (modeloEl.options[i].value === val) {
          found = true;
          break;
        }
      }
      if (!found) modeloEl.add(new Option(val, val));
    }

    function syncDesc(modelo) {
      if (!descEl) return;
      descEl.value = AUTO_DESC[modelo] || descEl.value || "";
      descEl.readOnly = true;
    }

    function applyLock(lock) {
      modeloEl.disabled = !!lock;
      modeloEl.classList.toggle("read-only-field", !!lock);
      if (unlockBtn) {
        unlockBtn.classList.toggle("d-none", !!lock);
      }
    }

    function refresh() {
      const s = String(serialEl.value || "")
        .toUpperCase()
        .replace(/\s/g, "");
      if (serialEl.value !== s) serialEl.value = s;
      const inferred = inferModeloFromSerialStrict(s);
      const current = (modeloEl.value || "").trim();

      if (inferred) {
        if (!current || current === inferred) {
          ensureOption(inferred);
          modeloEl.value = inferred;
          applyLock(true);
          if (hintEl) {
            hintEl.textContent = "Modelo mapeado do serial (somente leitura).";
            hintEl.className = "form-text text-muted";
          }
        } else {
          ensureOption(current);
          ensureOption(inferred);
          applyLock(false);
          if (hintEl) {
            hintEl.textContent =
              "Modelo diverge do serial (" +
              inferred +
              "). Corrija pela lista — nao use valor livre.";
            hintEl.className = "form-text text-warning";
          }
        }
        syncDesc(modeloEl.value);
      } else {
        applyLock(false);
        if (hintEl) {
          hintEl.textContent =
            "Serial sem mapeamento conhecido — selecione um modelo da lista oficial.";
          hintEl.className = "form-text text-warning";
        }
        syncDesc(modeloEl.value);
      }

      if (opts.serialHintId) {
        const sh = document.getElementById(opts.serialHintId);
        if (sh) {
          const looks =
            /^(?:FGT|FG)/i.test(s) &&
            s.length >= 14 &&
            !/^(123|TEST|TESTE)$/i.test(s);
          sh.textContent = looks
            ? "Serial no formato Fortinet esperado."
            : s
              ? "Serial pode estar fora do padrão Fortinet (FGT…TK… / FG120GTK…)."
              : "";
          sh.className = "form-text " + (looks ? "text-success" : s ? "text-warning" : "");
        }
      }
    }

    serialEl.addEventListener("input", refresh);
    serialEl.addEventListener("change", refresh);
    serialEl.addEventListener("blur", refresh);
    modeloEl.addEventListener("change", function () {
      const inferred = inferModeloFromSerialStrict(serialEl.value);
      if (inferred && modeloEl.value === inferred) applyLock(true);
      syncDesc(modeloEl.value);
      if (hintEl && inferred && modeloEl.value === inferred) {
        hintEl.textContent = "Modelo mapeado do serial (somente leitura).";
        hintEl.className = "form-text text-muted";
      }
    });
    if (unlockBtn) {
      unlockBtn.addEventListener("click", function () {
        const inferred = inferModeloFromSerialStrict(serialEl.value);
        if (inferred) {
          ensureOption(inferred);
          modeloEl.value = inferred;
          applyLock(true);
          syncDesc(inferred);
          if (hintEl) {
            hintEl.textContent = "Modelo restaurado a partir do serial.";
            hintEl.className = "form-text text-success";
          }
        }
      });
    }
    refresh();
    return { refresh: refresh };
  }

  /**
   * Escolhe colunas do grid para preencher a última linha (menos “buracos”).
   * Ex.: 10 → 5; 16 → 4; 6 → 6; 9 → 3.
   */
  function resolveAdminKpiColumns(n) {
    const count = Math.max(1, Number(n) || 1);
    let best = 4;
    let bestWaste = 99;
    [6, 5, 4, 3].forEach(function (cols) {
      if (cols > count && count > 2) return;
      const rem = count % cols;
      const waste = rem === 0 ? 0 : cols - rem;
      if (waste < bestWaste || (waste === bestWaste && cols > best)) {
        best = cols;
        bestWaste = waste;
      }
    });
    if (count <= 2) best = count;
    return best;
  }

  /**
   * KPIs clicáveis (padrão visual Gestão).
   * cards: [{ key, label, hint, color, icon, featured?, section?, test|countFn|onClick }]
   * - featured: Total destacado à esquerda
   * - section: agrupa o restante sob subtítulo
   */
  function mountKpis(containerId, api, cards) {
    const box = document.getElementById(containerId);
    if (!box) return { refresh: function () {}, bind: function () {} };

    let activeKey = "all";
    let filterFn = null;
    let dtApi = api || null;

    const extName = "adminInvKpi_" + containerId;
    if (!$.fn.dataTable.ext.search._adminInvBound) {
      $.fn.dataTable.ext.search._adminInvBound = true;
    }

    function removeExt() {
      const arr = $.fn.dataTable.ext.search;
      for (let i = arr.length - 1; i >= 0; i--) {
        if (arr[i] && arr[i]._adminInvKey === extName) arr.splice(i, 1);
      }
    }

    function paint() {
      if (!dtApi) {
        box.querySelectorAll(".admin-inv-kpi-value").forEach(function (val) {
          val.textContent = "0";
        });
        return;
      }
      const rows = dtApi.rows({ search: "none" }).data().toArray();
      box.querySelectorAll("[data-kpi-key]").forEach(function (card) {
        const key = card.getAttribute("data-kpi-key");
        const def = cards.find(function (c) {
          return c.key === key;
        });
        let n = 0;
        if (def && typeof def.countFn === "function") {
          n = def.countFn(rows);
        } else if (def && typeof def.test === "function") {
          n = rows.filter(function (r) {
            return def.test(r);
          }).length;
        } else {
          n = rows.length;
        }
        const val = card.querySelector(".admin-inv-kpi-value");
        if (val) val.textContent = String(n);
        card.classList.toggle("active", key === activeKey);
      });
    }

    function apply(key) {
      if (!dtApi) return;
      activeKey = key || "all";
      removeExt();
      const def = cards.find(function (c) {
        return c.key === activeKey;
      });
      if (def && typeof def.onClick === "function") {
        def.onClick(dtApi, def);
        paint();
        return;
      }
      if (def && typeof def.test === "function" && activeKey !== "all") {
        filterFn = function (_s, _d, _i, data) {
          return def.test(data);
        };
        filterFn._adminInvKey = extName;
        $.fn.dataTable.ext.search.push(filterFn);
      }
      dtApi.draw();
      paint();
    }

    function buildCardEl(c, opts) {
      opts = opts || {};
      const color = c.color || "#6c757d";
      const icon = c.icon || "fa-chart-simple";
      const iconTone = c.iconTone || "secondary";
      const featured = !!opts.featured || !!c.featured;
      const card = document.createElement("div");
      card.className =
        "card h-100 border-0 shadow-sm admin-inv-kpi-card dashboard-filterable-card" +
        (featured ? " admin-inv-kpi-card--featured" : "");
      card.setAttribute("data-kpi-key", c.key);
      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");
      card.style.cursor = "pointer";
      card.style.setProperty("--admin-kpi-accent", color);
      const valueClass = featured
        ? "fw-bold text-dark mb-0 admin-inv-kpi-value admin-inv-kpi-value--lg"
        : "fw-bold text-dark mb-0 admin-inv-kpi-value";
      card.innerHTML =
        '<div class="card-body d-flex align-items-center justify-content-between p-2' +
        (featured ? " flex-column text-center py-3" : "") +
        '">' +
        (featured
          ? '<div class="w-100 admin-inv-kpi-text">' +
            '<h6 class="text-muted text-uppercase mb-1 admin-inv-kpi-label fw-bold">' +
            esc(c.label) +
            "</h6>" +
            (c.hint
              ? '<small class="text-muted d-block admin-inv-kpi-hint mx-auto">' +
                esc(c.hint) +
                "</small>"
              : "") +
            '<h3 class="' +
            valueClass +
            ' mt-2">0</h3>' +
            "</div>" +
            '<div class="icon-shape bg-' +
            esc(iconTone) +
            " bg-opacity-10 text-" +
            esc(iconTone) +
            ' rounded-circle p-2 mt-2">' +
            '<i class="fas ' +
            esc(icon) +
            ' fa-lg"></i></div>'
          : "<div class=\"admin-inv-kpi-text\">" +
            '<h6 class="text-muted text-uppercase mb-1 admin-inv-kpi-label">' +
            esc(c.label) +
            "</h6>" +
            (c.hint
              ? '<small class="text-muted d-block admin-inv-kpi-hint">' +
                esc(c.hint) +
                "</small>"
              : "") +
            '<h3 class="' +
            valueClass +
            '">0</h3>' +
            "</div>" +
            '<div class="icon-shape bg-' +
            esc(iconTone) +
            " bg-opacity-10 text-" +
            esc(iconTone) +
            ' rounded-circle p-2">' +
            '<i class="fas ' +
            esc(icon) +
            ' fa-lg"></i></div>') +
        "</div>";
      card.addEventListener("click", function () {
        apply(c.key);
      });
      card.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          apply(c.key);
        }
      });
      return card;
    }

    function appendGrid(parent, list) {
      if (!list.length) return;
      const colsXl = resolveAdminKpiColumns(list.length);
      const colsMd = Math.min(colsXl, colsXl >= 5 ? 3 : Math.max(2, Math.min(3, colsXl)));
      const grid = document.createElement("div");
      grid.className = "admin-inv-kpi-grid";
      grid.style.setProperty("--admin-kpi-cols", String(colsXl));
      grid.style.setProperty("--admin-kpi-cols-md", String(colsMd));
      grid.setAttribute("data-kpi-count", String(list.length));
      list.forEach(function (c) {
        grid.appendChild(buildCardEl(c, { featured: false }));
      });
      parent.appendChild(grid);
    }

    const featuredList = cards.filter(function (c) {
      return !!c.featured || c.key === "all";
    });
    /* Só 1 featured: preferir flag; senão o primeiro "all" */
    let featuredCard = null;
    for (let i = 0; i < featuredList.length; i++) {
      if (featuredList[i].featured) {
        featuredCard = featuredList[i];
        break;
      }
    }
    if (!featuredCard && featuredList.length) featuredCard = featuredList[0];

    const rest = cards.filter(function (c) {
      return !featuredCard || c.key !== featuredCard.key;
    });

    const sectionOrder = [];
    const sectionMap = {};
    rest.forEach(function (c) {
      const sec = (c.section && String(c.section).trim()) || "Geral";
      if (!sectionMap[sec]) {
        sectionMap[sec] = [];
        sectionOrder.push(sec);
      }
      sectionMap[sec].push(c);
    });

    box.innerHTML = "";
    const shell = document.createElement("div");
    shell.className = "admin-inv-kpi-shell mb-3";

    if (featuredCard) {
      const featCol = document.createElement("div");
      featCol.className = "admin-inv-kpi-featured";
      featCol.appendChild(buildCardEl(featuredCard, { featured: true }));
      shell.appendChild(featCol);
    }

    const main = document.createElement("div");
    main.className = "admin-inv-kpi-main";
    sectionOrder.forEach(function (secTitle) {
      const sec = document.createElement("div");
      sec.className = "admin-inv-kpi-section";
      const title = document.createElement("div");
      title.className = "admin-inv-kpi-section-title";
      title.textContent = secTitle;
      sec.appendChild(title);
      appendGrid(sec, sectionMap[secTitle]);
      main.appendChild(sec);
    });
    shell.appendChild(main);
    box.appendChild(shell);

    function bind(apiInstance) {
      if (!apiInstance) return;
      dtApi = apiInstance;
      dtApi.off("draw.dt.adminInvKpi");
      dtApi.off("xhr.dt.adminInvKpi");
      dtApi.on("draw.dt.adminInvKpi", paint);
      dtApi.on("xhr.dt.adminInvKpi", function () {
        setTimeout(paint, 0);
      });
      paint();
    }

    if (dtApi) bind(dtApi);
    else paint();

    return {
      refresh: paint,
      clear: function () {
        apply("all");
      },
      apply: apply,
      bind: bind,
    };
  }

  function statusBadgeHtml(status) {
    const s = String(status || "").trim();
    if (!s) return '<span class="badge bg-secondary">—</span>';
    const low = s.toLowerCase();
    let tone = "bg-secondary";
    if (low.indexOf("atendimento") >= 0) tone = "bg-primary";
    else if (low.indexOf("agend") >= 0) tone = "bg-secondary";
    else if (low.indexOf("conclu") >= 0) tone = "bg-success";
    else if (low.indexOf("quebra") >= 0) tone = "bg-danger";
    else if (low.indexOf("aguard") >= 0) tone = "bg-warning text-dark";
    else if (low.indexOf("cancel") >= 0) tone = "bg-dark";
    return '<span class="badge ' + tone + '">' + esc(s) + "</span>";
  }

  function pickAtendimentoFoco(atts) {
    const list = atts || [];
    if (!list.length) return null;
    for (let i = 0; i < list.length; i++) {
      const st = String(list[i].status || "").toLowerCase();
      if (st.indexOf("em atendimento") >= 0) return list[i];
    }
    return list[0];
  }

  /**
   * Faixa de resumo no header do modal (aplica estilo no próprio el — sem div aninhada).
   * opts: { lines: string[], badges: [{label, tone}] }
   */
  function renderSummaryStrip(el, opts) {
    if (!el) return;
    opts = opts || {};
    const badges = opts.badges || [];
    const lines = (opts.lines || []).filter(Boolean);
    const empty = !lines.length && !badges.length;
    el.className = empty ? "admin-inv-summary d-none" : "admin-inv-summary";
    let html = "";
    if (lines.length) {
      html += '<div class="admin-inv-summary-main">' + esc(lines.join(" · ")) + "</div>";
    }
    if (badges.length) {
      html += '<div class="admin-inv-summary-badges">';
      badges.forEach(function (b) {
        if (!b || !b.label) return;
        html +=
          '<span class="badge ' +
          esc(b.tone || "bg-secondary") +
          '">' +
          esc(b.label) +
          "</span>";
      });
      html += "</div>";
    }
    el.innerHTML = html;
  }

  function renderUnidadeBlock(u) {
    if (!u) {
      return '<div class="admin-inv-ctx mb-2"><em class="text-muted">Sem unidade associada.</em></div>';
    }
    return (
      '<div class="admin-inv-ctx mb-2">' +
      '<h6 class="text-primary mb-2">Unidade</h6>' +
      "<div><strong>" +
      esc(u.id_vgr) +
      "</strong> · " +
      esc(u.acronimo || "—") +
      "</div>" +
      "<div class=\"text-break\">" +
      esc(u.hostname || "—") +
      "</div>" +
      '<div class="text-muted text-break">' +
      esc(u.nome || "") +
      (u.municipio ? " — " + esc(u.municipio) + "/" + esc(u.estado || "") : "") +
      "</div></div>"
    );
  }

  function renderAtendimentosBlock(atts) {
    const list = atts || [];
    const foco = pickAtendimentoFoco(list);
    let html = "";
    if (foco) {
      const data = foco.data ? String(foco.data).slice(0, 10) : "—";
      html +=
        '<div class="admin-inv-ctx admin-inv-ctx-foco mb-2">' +
        '<h6 class="text-primary mb-2">Atendimento em foco</h6>' +
        '<div class="d-flex flex-wrap align-items-center gap-2 mb-1">' +
        "<strong>#" +
        esc(foco.id) +
        "</strong> · " +
        esc(data) +
        " " +
        statusBadgeHtml(foco.status) +
        " " +
        statusBadgeHtml(foco.substatus) +
        "</div>" +
        '<div class="small text-muted text-break">Gestão: ' +
        esc(foco.analista_gestao || "—") +
        " · Config: " +
        esc(foco.analista_config || "—") +
        " · Caderno: " +
        esc(foco.analista_caderno || "—") +
        "</div></div>";
    }
    html += '<div class="admin-inv-ctx mb-0">';
    html += '<h6 class="text-primary mb-2">Atendimentos recentes</h6>';
    if (!list.length) {
      html += '<em class="text-muted">Nenhum atendimento encontrado.</em>';
    } else {
      html +=
        '<div class="table-responsive"><table class="table table-sm table-bordered mb-0 admin-inv-ctx-atts">' +
        "<thead><tr>" +
        "<th>ID</th><th>Data</th><th>Status</th><th>Substatus</th>" +
        "<th>Gestão</th><th>Config.</th><th>Caderno</th>" +
        "</tr></thead><tbody>";
      list.forEach(function (a) {
        const data = a.data ? String(a.data).slice(0, 10) : "—";
        const isFoco = foco && String(foco.id) === String(a.id);
        html +=
          '<tr class="' +
          (isFoco ? "admin-inv-ctx-row-foco" : "") +
          '"><td>' +
          esc(a.id) +
          "</td><td>" +
          esc(data) +
          '</td><td class="admin-inv-badge-cell" title="' +
          esc(a.status || "") +
          '">' +
          statusBadgeHtml(a.status) +
          '</td><td class="admin-inv-badge-cell" title="' +
          esc(a.substatus || "") +
          '">' +
          statusBadgeHtml(a.substatus) +
          '</td><td class="text-break" title="' +
          esc(a.analista_gestao || "") +
          '">' +
          esc(a.analista_gestao || "—") +
          '</td><td class="text-break" title="' +
          esc(a.analista_config || "") +
          '">' +
          esc(a.analista_config || "—") +
          '</td><td class="text-break" title="' +
          esc(a.analista_caderno || "") +
          '">' +
          esc(a.analista_caderno || "—") +
          "</td></tr>";
      });
      html += "</tbody></table></div>";
    }
    html += "</div>";
    return html;
  }

  function renderAtivosPanel(el, ctx) {
    if (!el) return;
    const eqs = (ctx && ctx.equipamentos_relacionados) || [];
    const lks = (ctx && ctx.links_relacionados) || [];
    if (!eqs.length && !lks.length) {
      el.innerHTML =
        '<em class="text-muted">Nenhum outro equipamento ou link nesta unidade.</em>';
      return;
    }
    let html = '<div class="row g-3">';
    if (eqs.length) {
      html +=
        '<div class="col-md-6"><div class="admin-inv-ctx h-100">' +
        '<h6 class="text-primary mb-2">Equipamentos (' +
        eqs.length +
        ")</h6><ul class=\"list-unstyled mb-0 small\">";
      eqs.forEach(function (e) {
        html +=
          '<li class="mb-1 text-break"><strong>#' +
          esc(e.id) +
          "</strong> · " +
          esc(e.modelo || "—") +
          " · <code>" +
          esc(e.serial || "—") +
          "</code></li>";
      });
      html += "</ul></div></div>";
    }
    if (lks.length) {
      html +=
        '<div class="col-md-6"><div class="admin-inv-ctx h-100">' +
        '<h6 class="text-primary mb-2">Links (' +
        lks.length +
        ")</h6><ul class=\"list-unstyled mb-0 small\">";
      lks.forEach(function (l) {
        html +=
          '<li class="mb-1 text-break"><strong>#' +
          esc(l.id) +
          "</strong> · " +
          esc(l.tipo || "—") +
          "/" +
          esc(l.operadora || "—") +
          " · " +
          esc(l.ip_wan || l.id_vgr_link || "—") +
          "</li>";
      });
      html += "</ul></div></div>";
    }
    html += "</div>";
    el.innerHTML = html;
  }

  function renderContextoPanel(el, ctx) {
    if (!el) return;
    const u = (ctx && ctx.unidade) || null;
    const atts = (ctx && ctx.atendimentos) || [];
    el.innerHTML = renderUnidadeBlock(u) + renderAtendimentosBlock(atts);
  }

  /** Preenche painéis Contexto + Ativos a partir do pack da API. */
  function fillContextTabs(ctxEl, ativosEl, ctx) {
    renderContextoPanel(ctxEl, ctx);
    renderAtivosPanel(ativosEl, ctx);
  }

  /** mode: 'create' | 'edit' | 'view' */
  function applyModalMode(root, mode) {
    if (!root) return;
    const isView = mode === "view";
    const isEdit = mode === "edit";
    root.querySelectorAll("input, select, textarea, button").forEach(function (el) {
      if (el.closest(".modal-footer")) return;
      if (el.classList.contains("btn-close")) return;
      if (el.getAttribute("data-bs-toggle") === "tab") return;
      if (el.classList.contains("nav-link")) return;
      if (el.id && String(el.id).indexOf("btnAdmin") === 0 && el.type === "button") return;
      if (el.type === "hidden") return;
      if (isView) {
        el.setAttribute("disabled", "disabled");
      } else {
        el.removeAttribute("disabled");
      }
    });
    const vgrLock = root.querySelector("[data-admin-inv-lock-on-edit]");
    if (vgrLock) {
      if (isEdit || isView) vgrLock.setAttribute("readonly", "readonly");
      else vgrLock.removeAttribute("readonly");
      if (isView) vgrLock.setAttribute("disabled", "disabled");
    }
  }

  async function loadUnidadeContextoByVgr(idVgr) {
    const vgr = String(idVgr || "").trim();
    if (!vgr) return null;
    const { status, d } = await jsonFetch(
      "/prodesp/api/admin/unidades/contexto?id_vgr=" + encodeURIComponent(vgr)
    );
    if (status >= 400 || !d || !d.success) return null;
    return d;
  }

  var ADMIN_INV_CACHE_VER = 23;
  var ADMIN_INV_LIST_SCHEMA = 8;
  var ADMIN_INV_CACHE_MAX_AGE_MS = 30 * 60 * 1000;
  /* sessionStorage ~5MB/origem; 1.5MB descartava Links (~4.7k linhas slim ~2MB). */
  var ADMIN_INV_CACHE_MAX_CHARS = 4500000;
  /** Espelho em RAM — evita JSON.parse do sessionStorage a cada F5 na mesma aba. */
  var _memCache = Object.create(null);

  /**
   * Alta cardinalidade (id/designador/hostname…). Documentado para testes /
   * strip de cache antigo — opções vêm do scan client (ajaxOnly:false), como na fila.
   */
  var ADMIN_INV_CC_HEAVY = {
    links: ["id", "designador", "id_vgr_link", "ip_wan", "id_vgr", "hostname"],
    equipamentos: ["id", "serial", "id_vgr", "hostname"],
  };

  var _CC_LIGHT_EQ = [
    "modelo",
    "versao",
    "acronimo",
    "nome_unidade",
    "status_ultimo_atendimento",
    "analista_caderno_ultimo",
  ];
  var _CC_LIGHT_LINKS = [
    "tipo",
    "operadora",
    "acronimo",
    "status_ultimo_atendimento",
    "analista_caderno_ultimo",
  ];
  var _CC_EMPTY_DASH = {
    status_ultimo_atendimento: 1,
    analista_caderno_ultimo: 1,
  };

  /**
   * Espelha DataTables `_normalize(str, false)` (ext.type.search).
   */
  function dtSearchValue(text) {
    const s = text == null ? "" : String(text);
    if (!s || typeof s.normalize !== "function") return s;
    const nfd = s.normalize("NFD");
    return nfd.length !== s.length ? nfd.replace(/[\u0300-\u036f]/g, "") : s;
  }

  /**
   * Igual fila/gestão: PortalDt.ccSearchList() → ajaxOnly:false.
   * Opções no 1º draw a partir do dataset; clique no filtro já tem a lista.
   */
  function ccSearchList() {
    if (global.PortalDt && typeof global.PortalDt.ccSearchList === "function") {
      return global.PortalDt.ccSearchList();
    }
    return [
      [
        { extend: "searchList", ajaxOnly: false },
        "spacer",
        "orderAsc",
        "orderDesc",
        "orderClear",
      ],
    ];
  }

  /** Só reexibe listas dentro do dropdown aberto — nunca no th. */
  function revealColumnControlLists() {
    try {
      document.querySelectorAll("div.dtcc-dropdown .dtcc-list").forEach(function (el) {
        if (el.style.display === "none" && el.childElementCount > 0) {
          el.style.display = "";
        }
      });
    } catch (_e) {
      /* ignore */
    }
  }

  function rowsHaveListSchema(rows) {
    if (!rows || !rows.length) return true;
    return Object.prototype.hasOwnProperty.call(rows[0], "status_ultimo_atendimento");
  }

  function _ccKeysForKind(kind) {
    if (kind === "links") {
      return { light: _CC_LIGHT_LINKS, heavy: ADMIN_INV_CC_HEAVY.links || [] };
    }
    return { light: _CC_LIGHT_EQ, heavy: ADMIN_INV_CC_HEAVY.equipamentos || [] };
  }

  function _ccComplete(cc, keys) {
    if (!cc || typeof cc !== "object") return false;
    for (let i = 0; i < keys.length; i++) {
      if (!Array.isArray(cc[keys[i]])) return false;
    }
    return true;
  }

  /** Remove chaves de alta cardinalidade do columnControl (não persistir no cache). */
  function stripHeavyColumnControl(kind, cc) {
    if (!cc || typeof cc !== "object") return cc || null;
    const heavy = (ADMIN_INV_CC_HEAVY[kind] || []).slice();
    if (!heavy.length) return cc;
    const out = {};
    Object.keys(cc).forEach(function (k) {
      if (heavy.indexOf(k) >= 0) return;
      out[k] = cc[k];
    });
    return out;
  }

  /** Monta opções searchList a partir do array de rows (sem API DataTables). */
  function buildCcOptsFromRows(rows, keys) {
    const list = rows || [];
    const buckets = {};
    let i;
    let j;
    for (i = 0; i < keys.length; i++) buckets[keys[i]] = Object.create(null);
    for (i = 0; i < list.length; i++) {
      const row = list[i];
      if (!row) continue;
      for (j = 0; j < keys.length; j++) {
        const key = keys[j];
        const raw = row[key];
        const text = raw == null ? "" : String(raw).trim();
        const label = _CC_EMPTY_DASH[key] ? text || "—" : text;
        const value = dtSearchValue(label);
        if (!Object.prototype.hasOwnProperty.call(buckets[key], value)) {
          buckets[key][value] = label || "—";
        }
      }
    }
    const out = {};
    for (i = 0; i < keys.length; i++) {
      const key = keys[i];
      const items = Object.keys(buckets[key]).map(function (value) {
        return { label: buckets[key][value], value: value };
      });
      items.sort(function (a, b) {
        return String(a.label).localeCompare(String(b.label), "pt", { sensitivity: "base" });
      });
      out[key] = items;
    }
    return out;
  }

  /**
   * Garante columnControl leve (server). Nunca monta listas de alta cardinalidade.
   */
  function enrichColumnControl(kind, rows, existing) {
    const keys = _ccKeysForKind(kind);
    const light = stripHeavyColumnControl(kind, existing);
    if (_ccComplete(light, keys.light)) return light;
    const built = buildCcOptsFromRows(rows, keys.light);
    return Object.assign({}, light || {}, built);
  }

  function cacheRead(key) {
    if (!key) return null;
    const mem = _memCache[key];
    if (mem) {
      if (mem.ts && Date.now() - Number(mem.ts) > ADMIN_INV_CACHE_MAX_AGE_MS) {
        delete _memCache[key];
      } else if (
        mem.v === ADMIN_INV_CACHE_VER &&
        Array.isArray(mem.data) &&
        mem.revision != null &&
        (mem.schema == null || Number(mem.schema) === ADMIN_INV_LIST_SCHEMA)
      ) {
        return mem;
      } else {
        delete _memCache[key];
      }
    }
    if (!global.sessionStorage) return null;
    try {
      const raw = sessionStorage.getItem(key);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || parsed.v !== ADMIN_INV_CACHE_VER || !Array.isArray(parsed.data)) return null;
      if (parsed.revision == null) return null;
      if (parsed.schema != null && Number(parsed.schema) !== ADMIN_INV_LIST_SCHEMA) return null;
      if (!rowsHaveListSchema(parsed.data)) return null;
      if (parsed.ts && Date.now() - Number(parsed.ts) > ADMIN_INV_CACHE_MAX_AGE_MS) return null;
      _memCache[key] = parsed;
      return parsed;
    } catch (_e) {
      return null;
    }
  }

  function cachePurgeSiblingKeys(key) {
    if (!key || !global.sessionStorage) return;
    const m = String(key).match(/^(prodesp\.admin\.(?:links|equipamentos))\.v\d+$/);
    if (!m) return;
    const prefix = m[1] + ".v";
    try {
      const toRemove = [];
      for (let i = 0; i < sessionStorage.length; i++) {
        const k = sessionStorage.key(i);
        if (k && k.indexOf(prefix) === 0 && k !== key) toRemove.push(k);
      }
      toRemove.forEach(function (k) {
        try {
          sessionStorage.removeItem(k);
        } catch (_e) {
          /* ignore */
        }
        delete _memCache[k];
      });
    } catch (_e) {
      /* ignore */
    }
  }

  function cacheWrite(key, revision, data, columnControl) {
    if (!key || revision == null) return false;
    const payload = {
      v: ADMIN_INV_CACHE_VER,
      schema: ADMIN_INV_LIST_SCHEMA,
      revision: revision,
      data: data || [],
      columnControl: columnControl || null,
      ts: Date.now(),
    };
    _memCache[key] = payload;
    if (!global.sessionStorage) return true;
    let raw;
    try {
      raw = JSON.stringify(payload);
    } catch (_e) {
      return false;
    }
    if (raw.length > ADMIN_INV_CACHE_MAX_CHARS) {
      cacheClear(key);
      return false;
    }
    cachePurgeSiblingKeys(key);
    try {
      sessionStorage.setItem(key, raw);
      return true;
    } catch (_e) {
      try {
        cachePurgeSiblingKeys(key);
        sessionStorage.removeItem(key);
        sessionStorage.setItem(key, raw);
        return true;
      } catch (_e2) {
        try {
          sessionStorage.removeItem(key);
        } catch (_e3) {
          /* ignore */
        }
        return false;
      }
    }
  }

  function cacheClear(key) {
    if (key) delete _memCache[key];
    if (!key || !global.sessionStorage) return;
    try {
      sessionStorage.removeItem(key);
    } catch (_e) {
      /* ignore */
    }
  }

  function _ensureAjaxJson(api) {
    const settings = api.settings()[0];
    if (!settings) return null;
    if (!settings.json || typeof settings.json !== "object") {
      settings.json = { data: api.rows().data().toArray() };
    }
    if (!settings.json.columnControl) settings.json.columnControl = {};
    return settings;
  }

  function _uniqueOptsFromColumn(api, dataSrc, emptyAsDash) {
    const srcs = api.columns().dataSrc().toArray();
    const idx = srcs.indexOf(dataSrc);
    if (idx < 0) return null;
    const found = {};
    const opts = [];
    api.column(idx).data().each(function (raw) {
      const text = raw == null ? "" : String(raw).trim();
      const label = emptyAsDash ? text || "—" : text;
      const value = dtSearchValue(label);
      if (Object.prototype.hasOwnProperty.call(found, value)) return;
      found[value] = 1;
      opts.push({ label: label || "—", value: value });
    });
    opts.sort(function (a, b) {
      return String(a.label).localeCompare(String(b.label), "pt", { sensitivity: "base" });
    });
    return opts;
  }

  /** Injeta opções no JSON e pede reloadOptions (sem remontar a tabela). */
  function applyColumnControlOptions(api, columnControl, redraw) {
    if (!api || !columnControl) return;
    const settings = _ensureAjaxJson(api);
    if (!settings) return;
    Object.keys(columnControl).forEach(function (k) {
      settings.json.columnControl[k] = columnControl[k];
    });
    try {
      api.trigger("xhr", [settings, settings.json]);
    } catch (_e) {
      $(api.table().node()).trigger("xhr.dt", [settings, settings.json]);
    }
    if (redraw !== false) api.draw(false);
    setTimeout(revealColumnControlLists, 0);
  }

  function refreshAdminInvSearchLists(api, dataSrcNames) {
    if (!api) return;
    const names = dataSrcNames || [
      "status_ultimo_atendimento",
      "analista_caderno_ultimo",
    ];
    const map = {};
    names.forEach(function (name) {
      const dash =
        name === "status_ultimo_atendimento" || name === "analista_caderno_ultimo";
      const opts = _uniqueOptsFromColumn(api, name, dash);
      if (opts && opts.length) map[name] = opts;
    });
    if (Object.keys(map).length) applyColumnControlOptions(api, map, true);
  }

  /**
   * Padrão fila: init ColumnControl após dados; listas no 1º draw (ajaxOnly:false).
   * kind mantido no contrato (links|equipamentos).
   */
  function bindPortalDtColumnControl(api, kind) {
    if (!api || typeof $ === "undefined") return;
    void kind;
    let ready = false;

    function reveal() {
      setTimeout(revealColumnControlLists, 0);
    }

    function initOnce() {
      if (ready) return;
      if (!(api.columnControl && typeof api.columnControl.init === "function")) return;
      ready = true;
      try {
        api.columnControl.init();
      } catch (_e) {
        ready = false;
      }
      reveal();
    }

    api.on("xhr.dt.adminInvCc", function () {
      initOnce();
      reveal();
    });
    initOnce();
    reveal();
  }

  /** Enrich desligado — Status/Analista vêm na listagem. */
  function bindUltimoAtendimentoPageEnrich(_api) {
    return { stop: function () {}, refresh: function () {} };
  }

  async function fetchDataRevision() {
    const res = await fetch("/prodesp/api/data_revision", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) throw new Error("data_revision HTTP " + res.status);
    const data = await res.json();
    return data.data_revision != null ? data.data_revision : data.revision;
  }

  /**
   * Ajax client-mode:
   * - sessionStorage + data_revision → F5 instantâneo se nada mudou
   * - since_revision → reload leve enquanto a aba está aberta
   */
  function clientAjax(url, state) {
    state = state || { revision: null, cacheKey: null };
    return function (_request, callback, settings) {
      const bar = document.getElementById("adminInvLoadingBar");
      const cacheKey = state.cacheKey || null;
      const bust = !!state.bustCache;
      state.bustCache = false;

      function setLoading(on) {
        if (bar) bar.classList.toggle("is-on", !!on);
      }

      function finish(rows, rev, persist, _columnControl) {
        if (rev != null) state.revision = rev;
        /*
         * ajaxOnly:false (padrão fila): não injetar columnControl parcial no xhr —
         * o plugin monta as opções a partir do dataset no 1º draw (clique imediato).
         * Cache guarda só data+revision (payload menor / parse mais rápido).
         */
        if (persist && cacheKey && rev != null) {
          cacheWrite(cacheKey, rev, rows, null);
        }
        callback({ data: rows || [] });
        setLoading(false);
      }

      function replaceTableRows(rows, rev, _columnControl) {
        if (rev != null) state.revision = rev;
        if (cacheKey && rev != null) cacheWrite(cacheKey, rev, rows, null);
        try {
          const api = new $.fn.dataTable.Api(settings);
          api.clear();
          api.rows.add(rows || []);
          api.draw(false);
        } catch (_e) {
          /* ignore */
        }
      }

      function fetchList(useSince) {
        const params = new URLSearchParams();
        params.set("mode", "client");
        if (useSince && state.revision != null) {
          params.set("since_revision", String(state.revision));
        }
        /* Atualizar/forceFull: ignora cache de processo no servidor (SQL offline sem bump). */
        if (bust) {
          params.set("force", "1");
        }
        return fetch(url + "?" + params.toString(), {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        }).then(function (r) {
          return r.json();
        });
      }

      setLoading(true);

      if (!bust) {
        const cached = cacheRead(cacheKey);
        if (cached) {
          state.revision = cached.revision;
          const payload = { data: cached.data };
          /*
           * Cache hit não pode hidratar milhares de linhas de forma síncrona
           * dentro do DataTable() — trava o main thread e o browser não pinta
           * os KPIs montados antes. Deferir 1 tick libera o layout (valores 0)
           * e só então aplica o dataset.
           */
          setTimeout(function () {
            try {
              callback(payload);
            } finally {
              setLoading(false);
            }
            fetchDataRevision()
              .then(function (rev) {
                if (rev != null && Number(rev) === Number(cached.revision)) return null;
                setLoading(true);
                state.revision = null;
                return fetchList(false);
              })
              .then(function (json) {
                if (!json) return;
                if (json.data_revision != null) state.revision = json.data_revision;
                replaceTableRows(
                  json.data || [],
                  state.revision,
                  json.columnControl || null
                );
              })
              .catch(function () {
                /* mantém cache se rede falhar */
              })
              .finally(function () {
                setLoading(false);
              });
          }, 0);
          return;
        }
      } else if (cacheKey) {
        cacheClear(cacheKey);
      }

      fetchList(!bust && state.revision != null)
        .then(function (json) {
          if (json && json.data_revision != null) state.revision = json.data_revision;
          const schemaOk =
            json &&
            (json.inventory_list_schema == null ||
              Number(json.inventory_list_schema) === ADMIN_INV_LIST_SCHEMA);
          if (json && json.unchanged && schemaOk) {
            const api = new $.fn.dataTable.Api(settings);
            const rows = api.rows().data().toArray();
            if (rowsHaveListSchema(rows)) {
              finish(rows, state.revision, true, null);
              return;
            }
            state.revision = null;
            return fetchList(false).then(function (full) {
              if (full && full.data_revision != null) state.revision = full.data_revision;
              finish(
                (full && full.data) || [],
                state.revision,
                true,
                (full && full.columnControl) || null
              );
            });
          }
          if (json && json.unchanged && !schemaOk) {
            state.revision = null;
            return fetchList(false).then(function (full) {
              if (full && full.data_revision != null) state.revision = full.data_revision;
              finish(
                (full && full.data) || [],
                state.revision,
                true,
                (full && full.columnControl) || null
              );
            });
          }
          finish(
            (json && json.data) || [],
            state.revision,
            true,
            (json && json.columnControl) || null
          );
        })
        .catch(function () {
          finish([], state.revision, false, null);
        });
    };
  }

  /** Poll data_revision — só recarrega se mudou (E). */
  function bindRevisionSync(api, state) {
    state = state || { revision: null, cacheKey: null };
    let timer = null;
    let reloadInFlight = false;
    const intervalMs =
      (global.PRODESP_DT_SYNC && Number(global.PRODESP_DT_SYNC.intervalMs)) || 90000;

    function sameRev(a, b) {
      if (a == null || b == null) return false;
      return Number(a) === Number(b);
    }

    async function tick(force) {
      if (reloadInFlight && !force) return;
      try {
        const rev = await fetchDataRevision();
        if (rev == null) return;

        /*
         * Carga inicial ainda sem revisão: só ancora o valor.
         * Antes: null !== rev → toast falso + reload que competia com o 1º fetch.
         */
        if (!force && state.revision == null) {
          state.revision = rev;
          return;
        }

        const changed = !sameRev(rev, state.revision);
        if (!force && !changed) return;

        if (!force && changed) {
          toast("Inventário atualizado por outro admin. Atualizando a tabela…", true);
        }

        /* Não zerar revision (evita 2º falso positivo no próximo poll). */
        state.revision = rev;
        state.bustCache = true;
        reloadInFlight = true;
        api.ajax.reload(function () {
          reloadInFlight = false;
        }, false);
      } catch (_e) {
        reloadInFlight = false;
      }
    }

    function schedule() {
      if (timer) clearTimeout(timer);
      timer = setTimeout(function run() {
        tick(false).finally(function () {
          timer = setTimeout(run, intervalMs);
        });
      }, intervalMs);
    }

    schedule();
    return {
      force: function () {
        return tick(true);
      },
      stop: function () {
        if (timer) clearTimeout(timer);
      },
    };
  }

  /** i18n pt-BR — delega ao core PortalDt (fallback local se script não carregou). */
  function dtLanguagePtBr() {
    if (global.PortalDt && typeof global.PortalDt.languagePtBr === "function") {
      return global.PortalDt.languagePtBr();
    }
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
      columnControl: {
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
      },
    };
  }

  global.AdminInv = {
    esc: esc,
    toast: toast,
    toastTopCounts: toastTopCounts,
    normalizeStatusKey: normalizeStatusKey,
    statusIsCobranca: statusIsCobranca,
    statusIsEmAtendimento: statusIsEmAtendimento,
    statusIsQuebra: statusIsQuebra,
    jsonFetch: jsonFetch,
    inferModeloFromSerial: inferModeloFromSerial,
    bindUnitTypeahead: bindUnitTypeahead,
    bindLinkTypeFields: bindLinkTypeFields,
    bindSerialModelo: bindSerialModelo,
    bindModeloLockedFromSerial: bindModeloLockedFromSerial,
    mountKpis: mountKpis,
    renderContextoPanel: renderContextoPanel,
    renderAtivosPanel: renderAtivosPanel,
    fillContextTabs: fillContextTabs,
    renderSummaryStrip: renderSummaryStrip,
    applyModalMode: applyModalMode,
    statusBadgeHtml: statusBadgeHtml,
    loadUnidadeContextoByVgr: loadUnidadeContextoByVgr,
    clientAjax: clientAjax,
    bindRevisionSync: bindRevisionSync,
    bindUltimoAtendimentoPageEnrich: bindUltimoAtendimentoPageEnrich,
    bindPortalDtColumnControl: bindPortalDtColumnControl,
    refreshAdminInvSearchLists: refreshAdminInvSearchLists,
    cacheClear: cacheClear,
    dtLanguagePtBr: dtLanguagePtBr,
    ccSearchList: ccSearchList,
  };
})(typeof window !== "undefined" ? window : globalThis);
