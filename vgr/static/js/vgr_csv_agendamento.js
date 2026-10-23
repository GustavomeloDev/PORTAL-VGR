/**
 * @file vgr/static/js/vgr_csv_agendamento.js
 * @module VGR — Importação de agendamentos via CSV
 *
 * Porta de prodesp/static/js/painel_csv_prodesp.js (mesmos IDs de DOM, mesmo fluxo):
 *   upload → parse no browser → pré-validação (válidas / corrigíveis / sem ação)
 *   → correção inline → POST → resumo + export das não aplicadas.
 * Diferenças VGR:
 *   - coluna tipo_servico (SDWAN | SDWIFI | SDLAN) obrigatória;
 *   - ID VGR alfanumérico (equipamentos.id_vgr);
 *   - contratadas vindas do banco (window.VGR_CSV_CONFIG);
 *   - duplicidade por id_vgr + tipo_servico;
 *   - POST com X-CSRF-Token (before_request do blueprint VGR).
 */
;(function () {
  "use strict"

  const CFG = window.VGR_CSV_CONFIG || {}

  const VGR_CSV_COLS = [
    "id_vgr",
    "tipo_servico",
    "data_agendamento",
    "hora_agendamento",
    "contratada",
    "field",
    "contato_field",
  ]

  const VGR_CSV_PLACEHOLDERS_VAZIOS = new Set([
    "",
    "-",
    "—",
    "–",
    "n/a",
    "na",
    "null",
    "none",
    "sem",
    "s/n",
  ])

  const VGR_CSV_MOTIVOS_NAO_CORRIGIVEIS = [
    "unidade já possui atendimento concluído",
    "unidade não encontrada",
    "unidade inativa",
    "unidade já processada neste arquivo",
    "duplicado no arquivo",
    "erro ao processar o registro",
    "unidade ha exige",
    "unidade já possui atendimento ativo",
    "inativo/finalizado",
    "já iniciado",
  ]

  const MSG_DUPLICATA =
    "ID VGR + tipo de serviço duplicado no arquivo (segunda ocorrência ignorada; mantida a primeira)."

  let MyJson = null
  let csvPreviewState = novoEstado()
  let lastErrosExport = null
  let lastRejeitadasPreviaExport = null

  function novoEstado() {
    return { valid: [], invalid: [], semAcao: [], headers: [], ocultarSemAcaoNoPreview: false }
  }

  // ---------------------------------------------------------------------------
  // Regras (espelho de vgr/vgr/operacao/agendamento_csv_validacao.py)
  // ---------------------------------------------------------------------------

  function motivoCorrigivel(motivo) {
    const m = String(motivo || "")
      .trim()
      .toLowerCase()
    if (!m) return false
    return !VGR_CSV_MOTIVOS_NAO_CORRIGIVEIS.some((frag) => m.includes(frag))
  }

  function rowExportCorrigivel(row) {
    if (row && row.corrigivel === false) return false
    if (row && row.corrigivel === true) return true
    return motivoCorrigivel(row?.motivo)
  }

  function valorAusente(val) {
    if (val == null) return true
    const s = String(val).trim().toLowerCase()
    return !s || VGR_CSV_PLACEHOLDERS_VAZIOS.has(s)
  }

  function idVgrErro(val) {
    const s = String(val || "").trim()
    if (!s) return "ID VGR obrigatório."
    if (s.length > 64) return "ID VGR excede 64 caracteres."
    if (!/^[A-Za-z0-9._/-]+$/.test(s)) {
      return `ID VGR inválido (${s}). Use letras, números, '.', '-', '_' ou '/' (sem espaços).`
    }
    return null
  }

  function tipoServicoCanonico(val) {
    if (valorAusente(val)) return null
    const bruto = String(val).trim().toUpperCase().replace(/[-\s]/g, "")
    const lista = CFG.tiposServico || ["SDWAN", "SDWIFI", "SDLAN"]
    return lista.includes(bruto) ? bruto : null
  }

  function horaValida(val) {
    if (valorAusente(val)) return false
    return /^([01]?\d|2[0-3]):[0-5]\d(:[0-5]\d)?$/.test(String(val).trim())
  }

  function chaveContratada(val) {
    return String(val || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]/g, "")
  }

  function listaContratadasTxt() {
    return (CFG.contratadas || []).join(", ") || "nenhuma contratada configurada"
  }

  function contratadaCanonica(val) {
    const lista = CFG.contratadas || []
    const chave = chaveContratada(val)
    if (!chave) return null
    for (let i = 0; i < lista.length; i++) {
      if (chaveContratada(lista[i]) === chave) return String(lista[i]).trim()
    }
    return null
  }

  function dataValida(val) {
    if (!val) return false
    const s = String(val).trim()
    let d
    let m
    let y
    if (s.includes("/")) {
      const p = s.split("/")
      if (p.length !== 3) return false
      d = parseInt(p[0], 10)
      m = parseInt(p[1], 10)
      y = parseInt(p[2], 10)
    } else if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
      const p = s.split("-")
      y = parseInt(p[0], 10)
      m = parseInt(p[1], 10)
      d = parseInt(p[2], 10)
    } else {
      return false
    }
    if (!y || y < 2000 || m < 1 || m > 12 || d < 1 || d > 31) return false
    const dt = new Date(y, m - 1, d)
    return dt.getFullYear() === y && dt.getMonth() === m - 1 && dt.getDate() === d
  }

  function normalizarDataIso(val) {
    if (!val) return ""
    const s = String(val).trim()
    if (s.includes("/")) {
      const p = s.split("/")
      if (p.length === 3 && dataValida(s)) {
        return `${p[2]}-${String(p[1]).padStart(2, "0")}-${String(p[0]).padStart(2, "0")}`
      }
    }
    return s
  }

  function contatoDigitos(val) {
    return String(val || "").replace(/\D/g, "")
  }

  function validarLinha(obj) {
    const erros = []
    const errId = idVgrErro(obj.id_vgr)
    if (errId) erros.push(errId)

    if (valorAusente(obj.tipo_servico)) {
      erros.push(`Tipo de serviço obrigatório (${(CFG.tiposServico || []).join(", ")}).`)
    } else if (!tipoServicoCanonico(obj.tipo_servico)) {
      erros.push(
        `Tipo de serviço inválido (${obj.tipo_servico}). Use ${(CFG.tiposServico || []).join(", ")}.`
      )
    }

    const temAgenda = !!(obj.data_agendamento || obj.hora_agendamento)
    const temPlanejado =
      !valorAusente(obj.contratada) || !valorAusente(obj.field) || !valorAusente(obj.contato_field)

    if (!temAgenda && !temPlanejado) {
      erros.push("Linha sem dados de agendamento ou planejamento.")
      return erros
    }

    if (temAgenda) {
      if (!obj.data_agendamento) erros.push("Data de agendamento obrigatória.")
      else if (!dataValida(obj.data_agendamento)) {
        erros.push(`Data inválida (${obj.data_agendamento_raw || obj.data_agendamento}). Use dd/mm/yyyy.`)
      }
      if (valorAusente(obj.hora_agendamento)) erros.push("Hora de agendamento obrigatória.")
      else if (!horaValida(obj.hora_agendamento)) {
        erros.push(`Hora inválida (${obj.hora_agendamento}). Use HH:mm.`)
      }
      if (valorAusente(obj.contratada)) {
        erros.push(`Contratada obrigatória para agendamento. Use: ${listaContratadasTxt()}.`)
      } else if (!contratadaCanonica(obj.contratada)) {
        erros.push(`Contratada inválida (${obj.contratada}). Use: ${listaContratadasTxt()}.`)
      }
    } else {
      if (obj.data_agendamento && !dataValida(obj.data_agendamento)) {
        erros.push(`Data inválida (${obj.data_agendamento}). Use dd/mm/yyyy.`)
      }
      if (!valorAusente(obj.hora_agendamento) && !horaValida(obj.hora_agendamento)) {
        erros.push(`Hora inválida (${obj.hora_agendamento}). Use HH:mm.`)
      }
      if (!valorAusente(obj.contratada) && !contratadaCanonica(obj.contratada)) {
        erros.push(`Contratada inválida (${obj.contratada}). Use: ${listaContratadasTxt()}.`)
      }
    }

    if (!valorAusente(obj.field)) {
      if (String(obj.field).length > 128) erros.push("Field excede 128 caracteres.")
      const dig = contatoDigitos(obj.contato_field)
      if (dig.length < 10 || dig.length > 11) {
        erros.push("Contato Field obrigatório (10 ou 11 dígitos) quando Field está preenchido.")
      }
      const contrCanon = contratadaCanonica(obj.contratada)
      const fieldCanon = contratadaCanonica(obj.field)
      if (contrCanon && fieldCanon && contrCanon !== fieldCanon) {
        erros.push(`Field (${fieldCanon}) não corresponde à contratada (${contrCanon}).`)
      }
    }

    return erros
  }

  function chaveLinha(row) {
    const tipo = tipoServicoCanonico(row.tipo_servico) || String(row.tipo_servico || "").trim().toUpperCase()
    return `${String(row.id_vgr || "").trim().toUpperCase()}|${tipo}`
  }

  // ---------------------------------------------------------------------------
  // UI helpers
  // ---------------------------------------------------------------------------

  function showToast(message, type = "info", delay = 5000) {
    const toastContainer = document.querySelector(".toast-container")
    if (!toastContainer) return

    const toastId = "toast-" + Date.now() + "-" + Math.floor(Math.random() * 1000)
    const toastHeaderClass =
      {
        success: "bg-success text-white",
        danger: "bg-danger text-white",
        warning: "bg-warning text-dark",
        info: "bg-primary text-white",
      }[type] || "bg-secondary text-white"

    const toastHtml = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header ${toastHeaderClass}">
                <strong class="me-auto">Notificação</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body">${escapeHtml(message)}</div>
        </div>`

    toastContainer.insertAdjacentHTML("beforeend", toastHtml)
    const toastElement = document.getElementById(toastId)
    const toast = new bootstrap.Toast(toastElement, { delay: delay })
    toastElement.addEventListener("hidden.bs.toast", () => toastElement.remove())
    toast.show()
  }

  function escapeHtml(text) {
    return String(text ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
  }

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]')
    if (meta && meta.content) return meta.content
    const hidden = document.querySelector("input[name='csrf_token']")
    return hidden ? hidden.value : ""
  }

  function formatDataExibicao(row) {
    if (row.data_agendamento_raw) return row.data_agendamento_raw
    const iso = row.data_agendamento
    if (iso && /^\d{4}-\d{2}-\d{2}$/.test(String(iso))) {
      const p = String(iso).split("-")
      return `${p[2]}/${p[1]}/${p[0]}`
    }
    return row.data_agendamento || ""
  }

  function ensureInvalidUid(item, index) {
    if (!item._uid) item._uid = `inv-${Date.now()}-${index}-${item.linha || 0}`
    return item._uid
  }

  function pushRejeitada(row, motivo, linha) {
    const item = { row: row, motivo: motivo, linha: linha, corrigivel: motivoCorrigivel(motivo) }
    if (item.corrigivel) csvPreviewState.invalid.push(item)
    else csvPreviewState.semAcao.push(item)
  }

  function prepareRowForSend(row) {
    const r = { ...row }
    const dataBr = formatDataExibicao(r)
    if (dataBr) {
      r.data_agendamento = normalizarDataIso(dataBr)
      r.data_agendamento_raw = dataBr
    } else {
      delete r.data_agendamento
      delete r.data_agendamento_raw
    }
    const tipo = tipoServicoCanonico(r.tipo_servico)
    if (tipo) r.tipo_servico = tipo
    const contr = contratadaCanonica(r.contratada)
    if (contr) r.contratada = contr
    delete r._uid
    delete r.motivo
    delete r.corrigivel
    return r
  }

  function syncMyJsonFromPreview() {
    MyJson = csvPreviewState.valid.map((v) => prepareRowForSend(v.row))
  }

  function chaveDuplicadaNoPreview(row, excludeUid) {
    const chave = chaveLinha(row)
    if (csvPreviewState.valid.some((v) => chaveLinha(v.row) === chave)) return true
    return csvPreviewState.invalid.some((item) => item._uid !== excludeUid && chaveLinha(item.row) === chave)
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  function renderPreviewTable(rows, motivoCol) {
    if (!rows.length) return '<p class="text-muted small mb-0">Nenhuma linha.</p>'
    const head = VGR_CSV_COLS.map((c) => `<th>${c}</th>`).join("")
    const body = rows
      .map((item) => {
        const r = item.row || item
        const motivo = item.motivo || r.motivo || ""
        const cells = VGR_CSV_COLS.map((c) => {
          const v = c === "data_agendamento" ? formatDataExibicao(r) : r[c]
          return `<td>${escapeHtml(v || "—")}</td>`
        }).join("")
        const extra = motivoCol ? `<td class="text-danger small">${escapeHtml(motivo)}</td>` : ""
        return `<tr>${cells}${extra}</tr>`
      })
      .join("")
    const motivoHead = motivoCol ? "<th>Motivo</th>" : ""
    return `<div class="table-responsive"><table class="table table-sm table-striped mb-0"><thead><tr>${head}${motivoHead}</tr></thead><tbody>${body}</tbody></table></div>`
  }

  function renderEditableInvalidTable(rows) {
    if (!rows.length) return '<p class="text-muted small mb-0">Nenhuma linha rejeitada.</p>'

    const head = VGR_CSV_COLS.map((c) => `<th>${c}</th>`).join("")
    const body = rows
      .map((item, index) => {
        ensureInvalidUid(item, index)
        const r = item.row || item
        const uid = item._uid
        const motivo = item.motivo || r.motivo || ""
        const cells = VGR_CSV_COLS.map((col) => {
          let val = r[col] || ""
          if (col === "data_agendamento") val = formatDataExibicao(r)
          let listAttr = ""
          if (col === "contratada" || col === "field") listAttr = ' list="vgr-csv-contratadas-list"'
          if (col === "tipo_servico") listAttr = ' list="vgr-csv-tipos-servico-list"'
          const inputMode = col === "contato_field" ? ' inputmode="numeric"' : ""
          return `<td><input type="text" class="form-control form-control-sm csv-invalid-input" data-col="${col}" data-uid="${uid}" value="${escapeHtml(val)}"${listAttr}${inputMode}></td>`
        }).join("")
        return `<tr data-csv-invalid-uid="${uid}">
          ${cells}
          <td class="text-danger small csv-invalid-motivo">${escapeHtml(motivo)}</td>
          <td class="text-nowrap">
            <button type="button" class="btn btn-sm btn-outline-success btn-revalidar-invalid-row" data-uid="${uid}" title="Aplicar correções e revalidar">
              <i class="fas fa-check"></i> Aplicar
            </button>
          </td>
        </tr>`
      })
      .join("")

    return `<div class="csv-preview-invalid-scroll"><div class="table-responsive csv-preview-invalid-table"><table class="table table-sm table-bordered mb-0"><thead><tr>${head}<th>Motivo</th><th>Ação</th></tr></thead><tbody>${body}</tbody></table></div></div>`
  }

  function renderCsvPreview() {
    const panel = document.getElementById("csv-preview-panel")
    const summary = document.getElementById("csv-preview-summary")
    const validSection = document.getElementById("csv-preview-valid-section")
    const validCountEl = document.getElementById("csv-preview-valid-count")
    const validEl = document.getElementById("csv-preview-valid")
    const invalidSection = document.getElementById("csv-preview-invalid-section")
    const invalidEl = document.getElementById("csv-preview-invalid")
    const semAcaoSection = document.getElementById("csv-preview-sem-acao-section")
    const semAcaoCountEl = document.getElementById("csv-preview-sem-acao-count")
    const semAcaoEl = document.getElementById("csv-preview-sem-acao")
    const semAcaoResumo = document.getElementById("csv-preview-sem-acao-resumo")
    const btnUpload = document.getElementById("btn-upload")
    const btnExportInvalid = document.getElementById("btn-export-invalid-csv")
    const btnsAplicarTodas = document.querySelectorAll(".btn-aplicar-todas-invalidas")

    if (!panel) return

    const nValid = csvPreviewState.valid.length
    const nInvalid = csvPreviewState.invalid.length
    const nSemAcao = csvPreviewState.semAcao.length
    const nRejeitadasTotal = nInvalid + nSemAcao

    if (!nValid && !nRejeitadasTotal) {
      panel.classList.add("d-none")
      if (btnUpload) btnUpload.disabled = true
      return
    }

    panel.classList.remove("d-none")
    if (summary) {
      let txt = `${nValid} linha(s) válida(s) para envio · ${nInvalid} para correção`
      if (nSemAcao) {
        txt += csvPreviewState.ocultarSemAcaoNoPreview
          ? ` · ${nSemAcao} sem ação no portal (consulte planilha/e-mail)`
          : ` · ${nSemAcao} sem ação no portal`
      }
      summary.textContent = txt
    }

    if (validSection) validSection.classList.toggle("d-none", nValid === 0)
    if (validCountEl) validCountEl.textContent = String(nValid)
    if (validEl) validEl.innerHTML = renderPreviewTable(csvPreviewState.valid, false)

    if (invalidSection) invalidSection.classList.toggle("d-none", nInvalid === 0)
    if (invalidEl) invalidEl.innerHTML = renderEditableInvalidTable(csvPreviewState.invalid)

    const exibirSemAcao = nSemAcao > 0 && !csvPreviewState.ocultarSemAcaoNoPreview
    if (semAcaoSection) semAcaoSection.classList.toggle("d-none", !exibirSemAcao)
    if (semAcaoResumo) {
      if (nSemAcao > 0 && csvPreviewState.ocultarSemAcaoNoPreview) {
        semAcaoResumo.textContent = `${nSemAcao} linha(s) sem ação de correção (concluídas, VGR inexistente ou duplicadas). Use «Baixar todas não aplicadas» ou o e-mail de resumo.`
        semAcaoResumo.classList.remove("d-none")
      } else {
        semAcaoResumo.textContent = ""
        semAcaoResumo.classList.add("d-none")
      }
    }
    if (semAcaoCountEl) semAcaoCountEl.textContent = String(nSemAcao)
    if (semAcaoEl) {
      semAcaoEl.innerHTML = exibirSemAcao ? renderPreviewTable(csvPreviewState.semAcao, true) : ""
    }

    if (btnUpload) btnUpload.disabled = nValid === 0
    if (btnExportInvalid) btnExportInvalid.disabled = nRejeitadasTotal === 0
    btnsAplicarTodas.forEach((btn) => {
      btn.disabled = nInvalid === 0
      btn.classList.toggle("d-none", nInvalid === 0)
    })
  }

  // ---------------------------------------------------------------------------
  // Correção inline
  // ---------------------------------------------------------------------------

  function coletarRowInvalidaDoDom(uid) {
    const tr = document.querySelector(`tr[data-csv-invalid-uid="${CSS.escape(uid)}"]`)
    if (!tr) return null
    const obj = {}
    tr.querySelectorAll(".csv-invalid-input").forEach((input) => {
      const col = input.dataset.col
      const val = String(input.value || "").trim()
      if (col === "data_agendamento") {
        obj.data_agendamento_raw = val
        obj.data_agendamento = val ? normalizarDataIso(val) : ""
      } else {
        obj[col] = val
      }
    })
    return obj
  }

  function revalidarLinhaInvalida(uid, silent) {
    const idx = csvPreviewState.invalid.findIndex((item) => item._uid === uid)
    if (idx === -1) return false

    const entry = csvPreviewState.invalid[idx]
    const edited = coletarRowInvalidaDoDom(uid)
    if (!edited) return false

    const row = { ...entry.row, ...edited }
    entry.row = row

    if (chaveDuplicadaNoPreview(row, uid)) {
      entry.motivo = MSG_DUPLICATA
      if (!silent) {
        renderCsvPreview()
        showToast("ID VGR + tipo de serviço ainda duplicado em outra linha do preview.", "warning")
      }
      return false
    }

    const erros = validarLinha(row)
    if (erros.length) {
      entry.motivo = erros.join(" ")
      if (!silent) {
        renderCsvPreview()
        showToast("Linha ainda inválida. Veja o motivo na tabela.", "warning")
      }
      return false
    }

    csvPreviewState.invalid.splice(idx, 1)
    csvPreviewState.valid.push({ row: row, linha: entry.linha })
    syncMyJsonFromPreview()
    renderCsvPreview()
    if (!silent) {
      showToast(`Linha VGR ${String(row.id_vgr || "").trim()} corrigida e movida para válidas.`, "success")
    }
    return true
  }

  function coletarTodasInvalidasDoDom() {
    csvPreviewState.invalid.forEach((item, index) => {
      ensureInvalidUid(item, index)
      const edited = coletarRowInvalidaDoDom(item._uid)
      if (edited) item.row = { ...item.row, ...edited }
    })
  }

  function aplicarCorrecoesTodasInvalidas() {
    if (!csvPreviewState.invalid.length) {
      showToast("Não há linhas rejeitadas para aplicar.", "info")
      return
    }
    coletarTodasInvalidasDoDom()
    const uids = csvPreviewState.invalid.map((item) => item._uid).slice()
    let ok = 0
    uids.forEach((uid) => {
      if (revalidarLinhaInvalida(uid, true)) ok += 1
    })
    renderCsvPreview()

    if (ok === uids.length) {
      showToast(`${ok} linha(s) corrigida(s) e pronta(s) para envio.`, "success")
    } else if (ok > 0) {
      showToast(`${ok} linha(s) movida(s) para válidas; ${uids.length - ok} ainda rejeitada(s).`, "warning", 8000)
    } else {
      showToast("Nenhuma linha passou na revalidação. Revise os motivos na tabela.", "warning", 8000)
    }
  }

  function importErrosExportToPreview(errosProc, errosPrevia) {
    csvPreviewState = novoEstado()
    csvPreviewState.ocultarSemAcaoNoPreview = true

    const todas = []
    ;(errosProc || []).forEach((r) => todas.push({ ...r }))
    ;(errosPrevia || []).forEach((r) => todas.push({ ...r }))

    if (!todas.length) {
      showToast("Não há linhas do último envio para exibir.", "info")
      return
    }

    let nCorrigivel = 0
    let nSemAcao = 0
    todas.forEach((r, index) => {
      const row = { ...r }
      const motivo = row.motivo || "Rejeitada no processamento."
      delete row.motivo
      delete row.corrigivel
      const item = {
        row: row,
        motivo: motivo,
        linha: index + 1,
        corrigivel: rowExportCorrigivel(r),
        _uid: `post-${Date.now()}-${index}`,
      }
      if (item.corrigivel) {
        csvPreviewState.invalid.push(item)
        nCorrigivel += 1
      } else {
        csvPreviewState.semAcao.push(item)
        nSemAcao += 1
      }
    })

    syncMyJsonFromPreview()
    renderCsvPreview()

    if (nCorrigivel && nSemAcao) {
      showToast(
        `${nCorrigivel} linha(s) para correção · ${nSemAcao} sem ação no portal (concluídas/inexistentes).`,
        "info",
        10000
      )
    } else if (nCorrigivel) {
      showToast(`${nCorrigivel} linha(s) carregadas para correção.`, "info", 8000)
    } else {
      showToast(
        `${nSemAcao} linha(s) sem ação de correção no portal. Consulte a planilha ou o e-mail.`,
        "warning",
        10000
      )
    }
  }

  function getTodasNaoAplicadasUltimoEnvio() {
    const proc = (lastErrosExport || []).map((r) => ({ row: r, motivo: r.motivo }))
    const prev = (lastRejeitadasPreviaExport || []).map((r) => ({ row: r, motivo: r.motivo }))
    return proc.concat(prev)
  }

  function atualizarBotoesUltimoEnvio() {
    const todas = getTodasNaoAplicadasUltimoEnvio()
    const corrigiveis = todas.filter((item) => rowExportCorrigivel(item.row))
    const btnPost = document.getElementById("btn-export-post-erros")
    const btnCorrigir = document.getElementById("btn-corrigir-post-erros")
    if (btnPost) btnPost.classList.toggle("d-none", todas.length === 0)
    if (btnCorrigir) btnCorrigir.classList.toggle("d-none", corrigiveis.length === 0)
  }

  function limparUltimoEnvioCsv() {
    lastErrosExport = null
    lastRejeitadasPreviaExport = null
    atualizarBotoesUltimoEnvio()
  }

  // ---------------------------------------------------------------------------
  // Export
  // ---------------------------------------------------------------------------

  function csvCell(v) {
    const s = String(v ?? "")
    return /[;"\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }

  function rowsToCsvExport(rows) {
    const header = VGR_CSV_COLS.concat(["motivo"]).join(";")
    const lines = rows.map((item) => {
      const r = item.row || item
      const motivo = item.motivo || r.motivo || ""
      const vals = VGR_CSV_COLS.map((c) => {
        let v = r[c] ?? ""
        if (c === "data_agendamento") v = formatDataExibicao(r) || v
        if (c === "hora_agendamento" && v && String(v).length >= 5) v = String(v).trim().slice(0, 5)
        return csvCell(v)
      })
      vals.push(csvCell(motivo))
      return vals.join(";")
    })
    return [header].concat(lines).join("\r\n")
  }

  function downloadTextFile(filename, content) {
    const blob = new Blob(["﻿" + content], { type: "text/csv;charset=utf-8" })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
  }

  function exportInvalidCsv(rows, filename) {
    const previewRows = csvPreviewState.invalid.concat(csvPreviewState.semAcao)
    const data = rows && rows.length ? rows : previewRows
    if (!data.length) {
      showToast("Não há linhas inválidas para exportar.", "info")
      return
    }
    downloadTextFile(filename || "agendamento_vgr_rejeitadas.csv", rowsToCsvExport(data))
  }

  // ---------------------------------------------------------------------------
  // Parse do arquivo
  // ---------------------------------------------------------------------------

  /** Split de uma linha `;` respeitando aspas (o export usa aspas quando há `;`). */
  function splitCsvLine(line) {
    const out = []
    let cur = ""
    let inQuotes = false
    for (let i = 0; i < line.length; i++) {
      const ch = line[i]
      if (inQuotes) {
        if (ch === '"' && line[i + 1] === '"') {
          cur += '"'
          i += 1
        } else if (ch === '"') {
          inQuotes = false
        } else {
          cur += ch
        }
      } else if (ch === '"') {
        inQuotes = true
      } else if (ch === ";") {
        out.push(cur)
        cur = ""
      } else {
        cur += ch
      }
    }
    out.push(cur)
    return out
  }

  function buildCsvPreview(parsedRows) {
    csvPreviewState = novoEstado()
    const vistos = new Set()

    parsedRows.forEach((entry) => {
      const row = entry.row
      const chave = chaveLinha(row)
      if (vistos.has(chave)) {
        pushRejeitada(row, MSG_DUPLICATA, entry.linha)
        return
      }
      vistos.add(chave)

      const erros = validarLinha(row)
      if (erros.length) pushRejeitada(row, erros.join(" "), entry.linha)
      else csvPreviewState.valid.push({ row: row, linha: entry.linha })
    })

    syncMyJsonFromPreview()
    renderCsvPreview()
  }

  function csvToJson(text) {
    const lines = String(text || "")
      .replace(/^﻿/, "")
      .split(/\r?\n/)
      .filter((l) => l.trim() !== "")
    if (!lines.length) {
      buildCsvPreview([])
      return
    }

    const keys = splitCsvLine(lines[0]).map((k) => k.trim().toLowerCase())
    const idx = {}
    VGR_CSV_COLS.forEach((c) => {
      idx[c] = keys.indexOf(c)
    })

    if (idx.id_vgr === -1) {
      showToast("Cabeçalho inválido: coluna «id_vgr» não encontrada. Baixe o modelo.", "danger", 8000)
      buildCsvPreview([])
      return
    }
    if (idx.tipo_servico === -1) {
      showToast("Cabeçalho inválido: coluna «tipo_servico» não encontrada. Baixe o modelo.", "danger", 8000)
      buildCsvPreview([])
      return
    }

    const parsed = []
    lines.slice(1).forEach((line, index) => {
      const item = splitCsvLine(line)
      const get = (col) => (idx[col] !== -1 && item[idx[col]] != null ? String(item[idx[col]]).trim() : "")

      const idVgr = get("id_vgr")
      if (!idVgr) return

      const obj = { id_vgr: idVgr, tipo_servico: get("tipo_servico") }
      const dataRaw = get("data_agendamento")
      if (dataRaw) {
        obj.data_agendamento_raw = dataRaw
        obj.data_agendamento = normalizarDataIso(dataRaw)
      }
      ;["hora_agendamento", "contratada", "field", "contato_field"].forEach((c) => {
        const v = get(c)
        if (v) obj[c] = v
      })

      const temAgenda = obj.data_agendamento || obj.hora_agendamento
      const temPlanejado =
        !valorAusente(obj.contratada) || !valorAusente(obj.field) || !valorAusente(obj.contato_field)
      if (!temAgenda && !temPlanejado) return

      parsed.push({ row: obj, linha: index + 2 })
    })

    csvPreviewState.headers = keys.slice()
    buildCsvPreview(parsed)
  }

  function convertFileInData(file) {
    const reader = new FileReader()
    reader.onload = (event) => {
      csvToJson(event.target.result)
      const nInv = csvPreviewState.invalid.length
      const nSem = csvPreviewState.semAcao.length
      if (nInv || nSem) {
        let msgPrev = `Pré-validação: ${nInv + nSem} linha(s) não serão enviadas.`
        if (nInv && nSem) msgPrev += ` ${nInv} para correção · ${nSem} sem ação no portal.`
        else if (nSem) msgPrev += " Todas sem ação de correção no portal."
        showToast(msgPrev, "warning", 10000)
      } else if (csvPreviewState.valid.length) {
        showToast(`${csvPreviewState.valid.length} linha(s) pronta(s) para envio.`, "success", 5000)
      } else {
        showToast("Nenhuma linha com dados de agendamento encontrada no arquivo.", "info", 6000)
      }
    }
    if (file) reader.readAsText(file, "UTF-8")
  }

  // ---------------------------------------------------------------------------
  // Envio
  // ---------------------------------------------------------------------------

  function buildRejeitadasPreviaPayload() {
    coletarTodasInvalidasDoDom()
    return csvPreviewState.invalid.concat(csvPreviewState.semAcao).map((item) => {
      const row = prepareRowForSend(item.row)
      return {
        id_vgr: row.id_vgr,
        tipo_servico: row.tipo_servico || "",
        data_agendamento: row.data_agendamento || "",
        hora_agendamento: row.hora_agendamento || "",
        contratada: row.contratada || "",
        field: row.field || "",
        contato_field: row.contato_field || "",
        motivo: item.motivo || "Rejeitada na pré-validação (não enviada ao processamento).",
      }
    })
  }

  async function sendCSV() {
    const fileInput = document.querySelector("#input-import-file")
    const btnUpload = document.querySelector("#btn-upload")

    if (!MyJson || !MyJson.length) {
      showToast("Nenhuma linha válida na pré-visualização para envio.", "warning")
      return
    }

    try {
      if (btnUpload) btnUpload.disabled = true
      showToast("Processando envio do arquivo, aguarde...", "info", 3000)

      const res = await fetch(CFG.urlRegister, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRF-Token": csrfToken(),
        },
        body: JSON.stringify({
          keys: VGR_CSV_COLS,
          body: MyJson,
          rejeitadas_previa: buildRejeitadasPreviaPayload(),
        }),
      })

      const data = await res.json().catch(() => ({}))
      const msg = data.msg || data.message

      if (res.ok || res.status === 207) {
        const resumo = data.resumo || {}
        let tipo = "success"
        if (resumo.erros > 0) tipo = "warning"
        else if (!resumo.sucesso && resumo.repetidos > 0) tipo = "info"
        showToast(msg || "Processamento concluído.", tipo, 12000)

        lastErrosExport = data.erros_export || []
        lastRejeitadasPreviaExport = data.rejeitadas_previa_export || []
        atualizarBotoesUltimoEnvio()

        if (fileInput) fileInput.value = ""
        MyJson = null
        csvPreviewState = novoEstado()
        renderCsvPreview()
      } else if (res.status === 403) {
        showToast(msg || "Acesso negado para o seu perfil.", "warning", 8000)
      } else if (res.status === 429) {
        showToast(msg || "Aguarde antes de enviar outro arquivo.", "warning", 8000)
      } else {
        showToast(msg || "Erro ao processar arquivo.", "danger")
      }
    } catch (error) {
      console.error(error)
      showToast("Erro de conexão com o servidor.", "danger")
    } finally {
      if (btnUpload) btnUpload.disabled = csvPreviewState.valid.length === 0
    }
  }

  async function baixarModelo() {
    try {
      const response = await fetch(CFG.urlModelo, { credentials: "same-origin" })
      if (!response.ok) throw new Error(`Erro ${response.status}`)
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = "modelo_agendamento_vgr.csv"
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error(error)
      showToast("Erro ao baixar o modelo CSV.", "danger")
    }
  }

  // ---------------------------------------------------------------------------
  // Eventos
  // ---------------------------------------------------------------------------

  document.addEventListener("click", (e) => {
    const element = e.target
    if (!(element instanceof Element)) return

    if (element.closest("#gerar-csv")) baixarModelo()

    if (element.closest("#btn-upload")) sendCSV()

    if (element.closest("#btn-export-invalid-csv")) exportInvalidCsv()

    if (element.closest("#btn-export-post-erros")) {
      const rows = getTodasNaoAplicadasUltimoEnvio()
      if (!rows.length) {
        showToast("Não há linhas do último envio para exportar.", "info")
        return
      }
      exportInvalidCsv(rows, "agendamento_vgr_nao_aplicadas.csv")
    }

    if (element.closest("#btn-corrigir-post-erros")) {
      importErrosExportToPreview(lastErrosExport, lastRejeitadasPreviaExport)
    }

    if (element.closest(".btn-aplicar-todas-invalidas")) aplicarCorrecoesTodasInvalidas()

    const btnRevalidarRow = element.closest(".btn-revalidar-invalid-row")
    if (btnRevalidarRow && btnRevalidarRow.dataset.uid) {
      revalidarLinhaInvalida(btnRevalidarRow.dataset.uid)
    }
  })

  document.getElementById("csv-preview-invalid")?.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !e.target.classList.contains("csv-invalid-input")) return
    e.preventDefault()
    const uid = e.target.dataset.uid
    if (uid) revalidarLinhaInvalida(uid)
  })

  document.getElementById("input-import-file")?.addEventListener("change", function () {
    const file = this.files[0]
    limparUltimoEnvioCsv()
    if (file) {
      convertFileInData(file)
    } else {
      MyJson = null
      csvPreviewState = novoEstado()
      renderCsvPreview()
    }
  })

  // Exposto só para testes/depuração.
  window.VgrCsvAgendamento = { validarLinha, splitCsvLine, chaveLinha, motivoCorrigivel }
})()
