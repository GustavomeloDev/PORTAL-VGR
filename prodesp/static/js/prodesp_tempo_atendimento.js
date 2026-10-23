/**
 * Cronômetros de tempo de atendimento (etapa + vida) — Atendimentos e Gestão.
 */
(function (global) {
  "use strict";

  const FINAL_STATUSES = new Set([
    "concluído",
    "concluido",
    "concluído parcial",
    "concluido parcial",
    "quebra",
    "quebra tbra",
  ]);

  function formatSecondsToHHMMSS(segundos) {
    const s = Math.max(0, parseInt(segundos, 10) || 0);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  }

  function escapeHtml(text) {
    return String(text ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function badgeClassForSeconds(segundos) {
    const minutos = segundos / 60;
    if (minutos >= 30) return "prodesp-tempo-badge--critico";
    if (minutos >= 15) return "prodesp-tempo-badge--atencao";
    return "prodesp-tempo-badge--ok";
  }

  /** Estados sem HH:MM:SS (sempre no fim da ordenação). */
  const BADGE_SEM_HORA = {
    traco: "prodesp-tempo-badge--sem-hora",
    pendente: "prodesp-tempo-badge--pendente",
    noPrazo: "prodesp-tempo-badge--no-prazo",
    finalizado: "prodesp-tempo-badge--finalizado",
  };

  function renderBadge(text, cls, title) {
    const base = "prodesp-tempo-badge";
    const extra = cls || "";
    return `<span class="badge ${base} ${extra}" title="${escapeHtml(title || "")}">${escapeHtml(text)}</span>`;
  }

  function valorOrdenacaoTempo(valorBruto, dir) {
    const n = typeof valorBruto === "number" ? valorBruto : parseFloat(valorBruto, 10);
    if (isNaN(n) || n >= SORT_NULL) {
      return dir === "asc" ? Number.POSITIVE_INFINITY : Number.NEGATIVE_INFINITY;
    }
    return n;
  }

  function rowStatus(row) {
    return (
      (row && (row.status_atendimentos || row.status_atendimento)) ||
      ""
    )
      .trim()
      .toLowerCase();
  }

  function rowModo(row) {
    return ((row && row.modo_duracao) || "").trim();
  }

  function isFinalizadoRow(row) {
    const modo = rowModo(row);
    return modo === "finalizado" || FINAL_STATUSES.has(rowStatus(row));
  }

  function isAgendadoRow(row) {
    const status = rowStatus(row);
    const modo = rowModo(row);
    return modo === "atraso_agendado" || status === "agendado";
  }

  function nowMs(timeOffset) {
    return Date.now() - (timeOffset || 0);
  }

  const SORT_NULL = 9e15;

  function isIsoValido(iso) {
    return !!(iso && !isNaN(new Date(iso).getTime()));
  }

  function toSortColumnValue(key) {
    if (key !== null && key !== undefined && key >= 0) {
      return key;
    }
    return SORT_NULL;
  }

  function rowSemAtendimento(row) {
    const id = row && (row.id_atendimento ?? row.id_atendimentos);
    return id === null || id === undefined || id === "";
  }

  /** Prioridade padrão da grade: Em Atendimento → Agendado → demais. */
  function listPriority(row) {
    const status = rowStatus(row);
    if (status === "em atendimento") return 0;
    if (rowSemAtendimento(row) || status === "agendado") return 1;
    return 2;
  }

  function parseListDateMs(value) {
    if (!value) return 0;
    if (value instanceof Date && !isNaN(value.getTime())) return value.getTime();
    const s = String(value).trim();
    if (!s) return 0;
    const datePart = s.split(/[T ]/)[0];
    const d = new Date(datePart + "T00:00:00");
    return isNaN(d.getTime()) ? 0 : d.getTime();
  }

  function listRecencyMs(row) {
    const dataAt =
      row.data_atendimento ||
      row.data_atendimentos ||
      row.data_agendamento ||
      row.data_agendamento_unidades;
    const hora =
      row.horario_inicio ||
      row.horario_inicio_atendimentos ||
      row.hora_agendamento ||
      row.hora_agendamento_unidades ||
      "00:00:00";
    const h = String(hora).trim().slice(0, 8);
    const base = parseListDateMs(dataAt);
    if (!base) return 0;
    const parts = h.split(":");
    const hh = parseInt(parts[0], 10) || 0;
    const mm = parseInt(parts[1], 10) || 0;
    const ss = parseInt(parts[2], 10) || 0;
    return base + (hh * 3600 + mm * 60 + ss) * 1000;
  }

  /** Chave única ASC: prioridade operacional e, dentro do grupo, mais recente primeiro. */
  function sortKeyLista(row) {
    const pri = listPriority(row);
    const ms = listRecencyMs(row) || 0;
    return pri * 1e15 - ms;
  }

  function atualizarSortEmLinha(row, timeOffset) {
    if (!row) return row;
    row._sort_etapa = toSortColumnValue(sortKeyEtapa(row, timeOffset || 0));
    row._sort_vida = toSortColumnValue(sortKeyVida(row, timeOffset || 0));
    row._sort_lista = sortKeyLista(row);
    return row;
  }

  function atualizarSortEmLinhas(rows, timeOffset) {
    if (!rows || !rows.length) return rows;
    rows.forEach((row) => atualizarSortEmLinha(row, timeOffset || 0));
    return rows;
  }

  /**
   * Reaplica ordenação quando a tabela está ordenada por colunas de tempo (cronômetro ao vivo).
   */
  function resortDataTableSeTempo(api, timeOffset, colIndices) {
    if (!api || !colIndices || !colIndices.length) return false;
    const orders = api.order();
    const ativo = orders.some((o) => colIndices.indexOf(o[0]) >= 0);
    if (!ativo) return false;
    api.rows().every(function () {
      atualizarSortEmLinha(this.data(), timeOffset || 0);
    });
    api.rows().invalidate("data").draw(false);
    return true;
  }

  function installDataTableTempoSortType() {
    const $ = global.jQuery;
    if (!$ || !$.fn.dataTable || !$.fn.dataTable.ext) return;

    if (!$.fn.dataTable.ext.order["prodesp-tempo"]) {
      $.fn.dataTable.ext.order["prodesp-tempo"] = function (settings, col) {
        const api = this.api();
        let dir = "asc";
        const orders = api.order();
        for (let i = 0; i < orders.length; i++) {
          if (orders[i][0] === col) {
            dir = orders[i][1];
            break;
          }
        }
        return api
          .column(col, { order: "index" })
          .data()
          .map(function (v) {
            return valorOrdenacaoTempo(v, dir);
          });
      };
    }

    if (!$.fn.dataTable.ext.type.order["prodesp-tempo-pre"]) {
      $.fn.dataTable.ext.type.order["prodesp-tempo-pre"] = function (d) {
        const n = typeof d === "number" ? d : parseFloat(d, 10);
        if (isNaN(n) || n >= SORT_NULL) return SORT_NULL;
        return n;
      };
    }
  }

  installDataTableTempoSortType();

  function segundosEntre(isoStart, endMs) {
    if (!isIsoValido(isoStart)) return -1;
    return Math.max(0, Math.floor((endMs - new Date(isoStart).getTime()) / 1000));
  }

  /**
   * Chave de ordenação — Tempo Etapa (null = exibir — / Pendente / No prazo).
   */
  function sortKeyEtapa(row, timeOffset) {
    if (!row) return null;

    if (isAgendadoRow(row)) {
      const iso = row.data_para_js;
      if (!iso || isNaN(new Date(iso).getTime())) return null;
      if (nowMs(timeOffset) < new Date(iso).getTime()) return null;
      const seg = segundosEntre(iso, nowMs(timeOffset));
      return seg >= 0 ? seg : null;
    }

    if (isFinalizadoRow(row)) {
      const etapaIso = row.data_para_js;
      const inicioTotal = row.data_inicio_total_js;
      const segVida = parseInt(row.tempo_em_segundos, 10);
      if (isIsoValido(etapaIso) && isIsoValido(inicioTotal) && !isNaN(segVida)) {
        const endMs = new Date(inicioTotal).getTime() + segVida * 1000;
        const seg = segundosEntre(etapaIso, endMs);
        return seg >= 0 ? seg : null;
      }
      return null;
    }

    // Em andamento: só o início da etapa atual (substatus), nunca o tempo de vida.
    const isoEtapa = row.data_para_js;
    if (!isIsoValido(isoEtapa)) return null;
    const seg = segundosEntre(isoEtapa, nowMs(timeOffset));
    return seg >= 0 ? seg : null;
  }

  /**
   * Chave de ordenação — Tempo de Vida (null = exibir — / Pendente / sem vida).
   * Não usa data_para_js como fallback — evita ordenar igual à etapa em agendados.
   */
  function sortKeyVida(row, timeOffset) {
    if (!row) return null;

    if (isAgendadoRow(row)) {
      return null;
    }

    if (isFinalizadoRow(row)) {
      const tempoFinalizado = String(row.tempo_total_calculado || "").trim();
      const seg = parseInt(row.tempo_em_segundos, 10);
      if (
        tempoFinalizado &&
        tempoFinalizado !== "---" &&
        !tempoFinalizado.startsWith("N/A") &&
        !isNaN(seg)
      ) {
        return seg;
      }
      return null;
    }

    const iso = row.data_inicio_total_js;
    if (!iso || isNaN(new Date(iso).getTime())) return null;
    const seg = segundosEntre(iso, nowMs(timeOffset));
    return seg >= 0 ? seg : null;
  }

  /** @deprecated use sortKeyEtapa */
  function calcSegundosEtapa(row, timeOffset) {
    const key = sortKeyEtapa(row, timeOffset);
    return key === null ? -1 : key;
  }

  /** @deprecated use sortKeyVida */
  function calcSegundosVida(row, timeOffset) {
    const key = sortKeyVida(row, timeOffset);
    return key === null ? -1 : key;
  }

  /** @deprecated use toSortColumnValue(sortKeyEtapa(...)) */
  function sortValueForDataTable(key) {
    return toSortColumnValue(key);
  }

  function renderSpanTempo(kind, row, timeOffset) {
    const status = (row.status_atendimentos || row.status_atendimento || "").trim();
    const statusLower = status.toLowerCase();
    const modoDuracao = rowModo(row);
    const layout = kind === "etapa" ? "tempo-etapa" : "tempo-vida";
    const inicioEtapaISO = row.data_para_js || "";
    const inicioTotalISO = row.data_inicio_total_js || "";
    const tempoFinalizado = row.tempo_total_calculado || "";
    const segundosFinalizados = parseInt(row.tempo_em_segundos, 10);
    const isFinalizado = isFinalizadoRow(row);

    const dataAttrs = `class="${layout}" data-layout="${kind}"
      data-inicio-total="${escapeHtml(inicioTotalISO)}"
      data-inicio-etapa="${escapeHtml(inicioEtapaISO)}"
      data-status="${escapeHtml(status)}"
      data-modo-duracao="${escapeHtml(modoDuracao)}"
      data-finalizado="${escapeHtml(tempoFinalizado)}"
      data-segundos="${row.tempo_em_segundos || 0}"`;

    if (kind === "vida" && isFinalizado && tempoFinalizado && tempoFinalizado !== "---" && !tempoFinalizado.startsWith("N/A")) {
      const cls = !isNaN(segundosFinalizados)
        ? badgeClassForSeconds(segundosFinalizados)
        : BADGE_SEM_HORA.finalizado;
      return `<span ${dataAttrs}>${renderBadge(tempoFinalizado, cls, "Tempo de vida do atendimento (finalizado)")}</span>`;
    }

    if (kind === "etapa" && isFinalizado) {
      const segEtapa = sortKeyEtapa(row, timeOffset);
      if (segEtapa >= 0) {
        return `<span ${dataAttrs}>${renderBadge(
          formatSecondsToHHMMSS(segEtapa),
          badgeClassForSeconds(segEtapa),
          "Tempo na etapa atual ao encerrar"
        )}</span>`;
      }
      return `<span ${dataAttrs}>${renderBadge("—", BADGE_SEM_HORA.traco, "Sem tempo de etapa registrado")}</span>`;
    }

    if (isFinalizado && kind === "vida") {
      return `<span ${dataAttrs}>${renderBadge(status || tempoFinalizado || "—", BADGE_SEM_HORA.finalizado, "Atendimento finalizado")}</span>`;
    }

    if (modoDuracao === "atraso_agendado" || statusLower === "agendado") {
      if (kind === "vida") {
        return `<span ${dataAttrs}>${renderBadge("—", BADGE_SEM_HORA.traco, "Sem tempo de vida (agendado)")}</span>`;
      }
      if (!inicioEtapaISO || isNaN(new Date(inicioEtapaISO))) {
        return `<span ${dataAttrs}>${renderBadge("Pendente", BADGE_SEM_HORA.pendente, "Sem horário agendado")}</span>`;
      }
      const dataAg = new Date(inicioEtapaISO);
      const now = new Date(nowMs(timeOffset));
      if (now < dataAg) {
        return `<span ${dataAttrs}>${renderBadge("No prazo", BADGE_SEM_HORA.noPrazo, "Ainda não passou do horário agendado")}</span>`;
      }
      const atrasoSeg = Math.floor((now - dataAg) / 1000);
      return `<span ${dataAttrs}>${renderBadge(
        formatSecondsToHHMMSS(atrasoSeg),
        badgeClassForSeconds(atrasoSeg),
        `Atraso desde ${dataAg.toLocaleString("pt-BR")}`
      )}</span>`;
    }

    const iso = kind === "vida" ? inicioTotalISO || inicioEtapaISO : inicioEtapaISO || inicioTotalISO;
    if (!iso || isNaN(new Date(iso))) {
      return `<span ${dataAttrs}>${renderBadge("Pendente", BADGE_SEM_HORA.pendente, "Sem referência de tempo")}</span>`;
    }
    const seg = Math.floor((nowMs(timeOffset) - new Date(iso).getTime()) / 1000);
    const title =
      kind === "vida"
        ? `Tempo de vida (desde ${new Date(iso).toLocaleString("pt-BR")})`
        : `Tempo na etapa (desde ${new Date(iso).toLocaleString("pt-BR")})`;
    return `<span ${dataAttrs}>${renderBadge(
      formatSecondsToHHMMSS(seg),
      badgeClassForSeconds(seg),
      title
    )}</span>`;
  }

  /**
   * @param {HTMLElement} cell
   * @param {{ timeOffset?: number, kind?: 'etapa'|'vida' }} opts
   */
  function atualizarCelulaTempo(cell, opts) {
    if (!cell) return;
    const timeOffset = (opts && opts.timeOffset) || 0;
    const kind = (opts && opts.kind) || (cell.classList.contains("tempo-vida") ? "vida" : "etapa");
    const inicioEtapaISO = cell.dataset.inicioEtapa || cell.dataset.inicio || "";
    const inicioTotalISO = cell.dataset.inicioTotal || "";
    const tempoFinalizado = cell.dataset.finalizado || "";
    const segundosFinalizados = parseInt(cell.dataset.segundos, 10);
    const status = (cell.dataset.status || "").trim();
    const modoDuracao = (cell.dataset.modoDuracao || "").trim();
    const statusLower = status.toLowerCase();
    const isFinalizado = modoDuracao === "finalizado" || FINAL_STATUSES.has(statusLower);

    if (kind === "vida" && isFinalizado && tempoFinalizado && tempoFinalizado !== "---" && !tempoFinalizado.startsWith("N/A")) {
      const cls = !isNaN(segundosFinalizados)
        ? badgeClassForSeconds(segundosFinalizados)
        : BADGE_SEM_HORA.finalizado;
      cell.innerHTML = renderBadge(tempoFinalizado, cls, "Tempo de vida do atendimento (finalizado)");
      return;
    }

    if (kind === "etapa" && isFinalizado && inicioEtapaISO && inicioTotalISO && !isNaN(segundosFinalizados)) {
      const endMs = new Date(inicioTotalISO).getTime() + segundosFinalizados * 1000;
      const segEtapa = segundosEntre(inicioEtapaISO, endMs);
      if (segEtapa >= 0) {
        cell.innerHTML = renderBadge(
          formatSecondsToHHMMSS(segEtapa),
          badgeClassForSeconds(segEtapa),
          "Tempo na etapa ao encerrar"
        );
        return;
      }
    }

    if (isFinalizado && kind === "vida") {
      cell.innerHTML = renderBadge(
        status || tempoFinalizado || "—",
        BADGE_SEM_HORA.finalizado,
        "Atendimento finalizado"
      );
      return;
    }

    if (modoDuracao === "atraso_agendado" || statusLower === "agendado") {
      if (kind === "vida") {
        cell.innerHTML = renderBadge("—", BADGE_SEM_HORA.traco, "Sem tempo de vida (agendado)");
        return;
      }
      if (!inicioEtapaISO || isNaN(new Date(inicioEtapaISO))) {
        cell.innerHTML = renderBadge("Pendente", BADGE_SEM_HORA.pendente, "Sem horário agendado");
        return;
      }
      const dataAg = new Date(inicioEtapaISO);
      const now = new Date(nowMs(timeOffset));
      if (now < dataAg) {
        cell.innerHTML = renderBadge("No prazo", BADGE_SEM_HORA.noPrazo, "Ainda não passou do horário agendado");
        return;
      }
      const atrasoSeg = Math.floor((now - dataAg) / 1000);
      cell.innerHTML = renderBadge(
        formatSecondsToHHMMSS(atrasoSeg),
        badgeClassForSeconds(atrasoSeg),
        `Atraso desde ${dataAg.toLocaleString("pt-BR")}`
      );
      return;
    }

    const iso = kind === "vida" ? inicioTotalISO || inicioEtapaISO : inicioEtapaISO || inicioTotalISO;
    if (!iso || isNaN(new Date(iso))) {
      cell.innerHTML = renderBadge("Pendente", BADGE_SEM_HORA.pendente, "Sem referência de tempo");
      return;
    }
    const now = new Date(nowMs(timeOffset));
    const seg = Math.floor((now - new Date(iso)) / 1000);
    const title =
      kind === "vida"
        ? `Tempo de vida (desde ${new Date(iso).toLocaleString("pt-BR")})`
        : `Tempo na etapa (desde ${new Date(iso).toLocaleString("pt-BR")})`;
    cell.innerHTML = renderBadge(
      formatSecondsToHHMMSS(seg),
      badgeClassForSeconds(seg),
      title
    );
  }

  function atualizarTempos(selector, opts) {
    const sel = selector || ".tempo-etapa, .tempo-vida";
    document.querySelectorAll(sel).forEach((cell) => {
      const kind = cell.classList.contains("tempo-vida") ? "vida" : "etapa";
      atualizarCelulaTempo(cell, { ...(opts || {}), kind });
    });
  }

  global.ProdespTempoAtendimento = {
    SORT_NULL,
    formatSecondsToHHMMSS,
    sortKeyEtapa,
    sortKeyVida,
    sortKeyLista,
    listPriority,
    toSortColumnValue,
    sortValueForDataTable,
    atualizarSortEmLinha,
    atualizarSortEmLinhas,
    resortDataTableSeTempo,
    calcSegundosEtapa,
    calcSegundosVida,
    renderSpanTempo,
    atualizarCelulaTempo,
    atualizarTempos,
  };
})(typeof window !== "undefined" ? window : globalThis);
