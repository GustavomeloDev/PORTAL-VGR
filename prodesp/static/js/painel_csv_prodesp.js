/**
 * @file prodesp/static/js/painel_csv_prodesp.js
 * @module PRODESP — Importação de agendamentos via CSV
 */
let MyJson = null
let keys = ["id_vgr"]
let csvPreviewState = {
  valid: [],
  invalid: [],
  semAcao: [],
  headers: [],
  rawRows: [],
  ocultarSemAcaoNoPreview: false,
}

const PRODESP_CSV_PLACEHOLDERS_VAZIOS = new Set([
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

const PRODESP_CSV_MOTIVOS_NAO_CORRIGIVEIS = [
  "unidade já possui atendimento concluído",
  "unidade não encontrada",
  "id vgr duplicado no arquivo",
  "erro ao processar o registro",
]

function prodespMotivoCsvCorrigivel(motivo) {
  const m = String(motivo || "")
    .trim()
    .toLowerCase()
  if (!m) return false
  return !PRODESP_CSV_MOTIVOS_NAO_CORRIGIVEIS.some((frag) => m.includes(frag))
}

function prodespRowExportCorrigivel(row) {
  if (row && row.corrigivel === false) return false
  if (row && row.corrigivel === true) return true
  return prodespMotivoCsvCorrigivel(row?.motivo)
}

function prodespCsvPushRejeitada(row, motivo, linha, uidPrefix) {
  const item = {
    row: row,
    motivo: motivo,
    linha: linha,
    corrigivel: prodespMotivoCsvCorrigivel(motivo),
  }
  if (uidPrefix) item._uid = `${uidPrefix}-${Date.now()}-${csvPreviewState.invalid.length + csvPreviewState.semAcao.length}`
  if (item.corrigivel) csvPreviewState.invalid.push(item)
  else csvPreviewState.semAcao.push(item)
}

const PRODESP_CSV_COLS = [
  "id_vgr",
  "data_agendamento",
  "hora_agendamento",
  "contratada",
  "field",
  "contato_field",
]

function prodespCsvValorAusente(val) {
  if (val == null) return true
  const s = String(val).trim().toLowerCase()
  return !s || PRODESP_CSV_PLACEHOLDERS_VAZIOS.has(s)
}

function prodespCsvIdVgrValido(val) {
  const s = String(val || "").trim()
  return !!s && /^\d+$/.test(s)
}

function prodespCsvHoraValida(val) {
  if (prodespCsvValorAusente(val)) return false
  const s = String(val).trim()
  return /^([01]?\d|2[0-3]):[0-5]\d(:[0-5]\d)?$/.test(s)
}

function prodespCsvContratadaPermitida(val) {
  const lista = window.PRODESP_CONTRATADAS_PERMITIDAS || []
  if (!lista.length) return !prodespCsvValorAusente(val)
  const bruto = String(val || "")
    .trim()
    .toLowerCase()
  return lista.some((c) => String(c).trim().toLowerCase() === bruto)
}

function prodespCsvContratadaCanonica(val) {
  const lista = window.PRODESP_CONTRATADAS_PERMITIDAS || []
  const bruto = String(val || "")
    .trim()
    .toLowerCase()
  for (let i = 0; i < lista.length; i++) {
    if (String(lista[i]).trim().toLowerCase() === bruto) return lista[i]
  }
  return null
}

function prodespCsvDataValida(val) {
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

function prodespCsvNormalizarDataIso(val) {
  if (!val) return ""
  const s = String(val).trim()
  if (s.includes("/")) {
    const p = s.split("/")
    if (p.length === 3 && prodespCsvDataValida(s)) {
      return `${p[2]}-${String(p[1]).padStart(2, "0")}-${String(p[0]).padStart(2, "0")}`
    }
    return s
  }
  return s
}

function prodespCsvContatoDigitos(val) {
  return String(val || "").replace(/\D/g, "")
}

function prodespValidarLinhaAgendamentoCsv(obj) {
  const erros = []
  if (!prodespCsvIdVgrValido(obj.id_vgr)) {
    erros.push(`ID VGR inválido (${obj.id_vgr || ""}). Use somente números.`)
  }

  const temAgenda = !!(obj.data_agendamento || obj.hora_agendamento)
  const temPlanejado = !!(
    !prodespCsvValorAusente(obj.contratada) ||
    !prodespCsvValorAusente(obj.field) ||
    !prodespCsvValorAusente(obj.contato_field)
  )

  if (!temAgenda && !temPlanejado) {
    erros.push("Linha sem dados de agendamento ou planejamento.")
    return erros
  }

  if (temAgenda) {
    if (!obj.data_agendamento) {
      erros.push("Data de agendamento obrigatória.")
    } else if (!prodespCsvDataValida(obj.data_agendamento)) {
      erros.push(`Data inválida (${obj.data_agendamento}). Use dd/mm/yyyy.`)
    }
    if (prodespCsvValorAusente(obj.hora_agendamento)) {
      erros.push("Hora de agendamento obrigatória.")
    } else if (!prodespCsvHoraValida(obj.hora_agendamento)) {
      erros.push(`Hora inválida (${obj.hora_agendamento}). Use HH:mm.`)
    }
    if (prodespCsvValorAusente(obj.contratada)) {
      erros.push("Contratada obrigatória para agendamento.")
    } else if (!prodespCsvContratadaPermitida(obj.contratada)) {
      erros.push(`Contratada inválida (${obj.contratada}).`)
    }
  } else {
    if (obj.data_agendamento && !prodespCsvDataValida(obj.data_agendamento)) {
      erros.push(`Data inválida (${obj.data_agendamento}). Use dd/mm/yyyy.`)
    }
    if (
      !prodespCsvValorAusente(obj.hora_agendamento) &&
      !prodespCsvHoraValida(obj.hora_agendamento)
    ) {
      erros.push(`Hora inválida (${obj.hora_agendamento}). Use HH:mm.`)
    }
    if (
      !prodespCsvValorAusente(obj.contratada) &&
      !prodespCsvContratadaPermitida(obj.contratada)
    ) {
      erros.push(`Contratada inválida (${obj.contratada}).`)
    }
  }

  if (!prodespCsvValorAusente(obj.field)) {
    if (String(obj.field).length > 60) {
      erros.push("Field excede 60 caracteres.")
    }
    const dig = prodespCsvContatoDigitos(obj.contato_field)
    if (dig.length < 10 || dig.length > 11) {
      erros.push("Contato Field obrigatório (10 ou 11 dígitos) quando Field está preenchido.")
    }
    const contrCanon = prodespCsvContratadaCanonica(obj.contratada)
    const fieldCanon = prodespCsvContratadaCanonica(obj.field)
    if (contrCanon && fieldCanon && contrCanon !== fieldCanon) {
      erros.push(
        `Field (${fieldCanon}) não corresponde à contratada (${contrCanon}).`
      )
    }
  }

  return erros
}

function showToast(message, type = "info", delay = 5000) {
  const toastContainer = document.querySelector(".toast-container")
  if (!toastContainer) return

  const toastId = "toast-" + Date.now()
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
            <div class="toast-body">${message}</div>
        </div>`

  toastContainer.insertAdjacentHTML("beforeend", toastHtml)
  const toastElement = document.getElementById(toastId)
  const toast = new bootstrap.Toast(toastElement, { delay: delay })
  toastElement.addEventListener("hidden.bs.toast", () => toastElement.remove())
  toast.show()
}

function prodespEscapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}

function prodespCsvFormatDataExibicao(row) {
  if (row.data_agendamento_raw) return row.data_agendamento_raw
  const iso = row.data_agendamento
  if (iso && /^\d{4}-\d{2}-\d{2}$/.test(String(iso))) {
    const p = String(iso).split("-")
    return `${p[2]}/${p[1]}/${p[0]}`
  }
  return row.data_agendamento || ""
}

function prodespEnsureInvalidUid(item, index) {
  if (!item._uid) {
    item._uid = `inv-${Date.now()}-${index}-${item.linha || 0}`
  }
  return item._uid
}

function prodespPrepareRowForSend(row) {
  const r = { ...row }
  const dataBr = prodespCsvFormatDataExibicao(r)
  if (dataBr) {
    r.data_agendamento = prodespCsvNormalizarDataIso(dataBr)
    r.data_agendamento_raw = dataBr
  } else {
    delete r.data_agendamento
    delete r.data_agendamento_raw
  }
  delete r._uid
  delete r.motivo
  return r
}

function prodespSyncMyJsonFromPreview() {
  MyJson = csvPreviewState.valid.map((v) => prodespPrepareRowForSend(v.row))
}

function prodespIdVgrDuplicadoNoPreview(idVgr, excludeUid) {
  const id = String(idVgr || "").trim()
  if (!id) return false
  const dupValid = csvPreviewState.valid.some(
    (v) => String(v.row.id_vgr || "").trim() === id
  )
  if (dupValid) return true
  return csvPreviewState.invalid.some(
    (item) =>
      item._uid !== excludeUid && String(item.row.id_vgr || "").trim() === id
  )
}

function prodespRenderPreviewTable(rows, motivoCol) {
  if (!rows.length) {
    return '<p class="text-muted small mb-0">Nenhuma linha.</p>'
  }
  const head = PRODESP_CSV_COLS.map((c) => `<th>${c}</th>`).join("")
  const body = rows
    .map((item) => {
      const r = item.row || item
      const motivo = item.motivo || r.motivo || ""
      const cells = PRODESP_CSV_COLS.map(
        (c) => `<td>${prodespEscapeHtml(r[c] || "—")}</td>`
      ).join("")
      const extra = motivoCol
        ? `<td class="text-danger small">${prodespEscapeHtml(motivo)}</td>`
        : ""
      return `<tr>${cells}${extra}</tr>`
    })
    .join("")
  const motivoHead = motivoCol ? "<th>Motivo</th>" : ""
  return `<div class="table-responsive"><table class="table table-sm table-striped mb-0"><thead><tr>${head}${motivoHead}</tr></thead><tbody>${body}</tbody></table></div>`
}

function prodespRenderEditableInvalidTable(rows) {
  if (!rows.length) {
    return '<p class="text-muted small mb-0">Nenhuma linha rejeitada.</p>'
  }

  const head = PRODESP_CSV_COLS.map((c) => `<th>${c}</th>`).join("")
  const body = rows
    .map((item, index) => {
      prodespEnsureInvalidUid(item, index)
      const r = item.row || item
      const uid = item._uid
      const motivo = item.motivo || r.motivo || ""
      const cells = PRODESP_CSV_COLS.map((col) => {
        let val = r[col] || ""
        if (col === "data_agendamento") val = prodespCsvFormatDataExibicao(r)
        const listAttr =
          col === "contratada" || col === "field"
            ? ' list="prodesp-csv-contratadas-list"'
            : ""
        const inputType = col === "id_vgr" ? "text" : "text"
        const inputMode = col === "id_vgr" || col === "contato_field" ? ' inputmode="numeric"' : ""
        return `<td><input type="${inputType}" class="form-control form-control-sm csv-invalid-input" data-col="${col}" data-uid="${uid}" value="${prodespEscapeHtml(val)}"${listAttr}${inputMode}></td>`
      }).join("")
      return `<tr data-csv-invalid-uid="${uid}">
        ${cells}
        <td class="text-danger small csv-invalid-motivo">${prodespEscapeHtml(motivo)}</td>
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

function prodespColetarRowInvalidaDoDom(uid) {
  const tr = document.querySelector(`tr[data-csv-invalid-uid="${uid}"]`)
  if (!tr) return null
  const obj = {}
  tr.querySelectorAll(".csv-invalid-input").forEach((input) => {
    const col = input.dataset.col
    const val = String(input.value || "").trim()
    if (col === "data_agendamento") {
      obj.data_agendamento_raw = val
      obj.data_agendamento = val ? prodespCsvNormalizarDataIso(val) : ""
    } else {
      obj[col] = val
    }
  })
  return obj
}

function prodespRevalidarLinhaInvalida(uid, silent) {
  const idx = csvPreviewState.invalid.findIndex((item) => item._uid === uid)
  if (idx === -1) return false

  const entry = csvPreviewState.invalid[idx]
  const edited = prodespColetarRowInvalidaDoDom(uid)
  if (!edited) return false

  const row = { ...entry.row, ...edited }
  entry.row = row

  const idVgr = String(row.id_vgr || "").trim()
  if (prodespIdVgrDuplicadoNoPreview(idVgr, uid)) {
    entry.motivo =
      "ID VGR duplicado no arquivo (segunda ocorrência ignorada; mantida a primeira)."
    if (!silent) {
      prodespRenderCsvPreview()
      showToast("ID VGR ainda duplicado em outra linha do preview.", "warning")
    }
    return false
  }

  const erros = prodespValidarLinhaAgendamentoCsv(row)
  if (erros.length) {
    entry.motivo = erros.join(" ")
    if (!silent) {
      prodespRenderCsvPreview()
      showToast("Linha ainda inválida. Veja o motivo na tabela.", "warning")
    }
    return false
  }

  csvPreviewState.invalid.splice(idx, 1)
  csvPreviewState.valid.push({ row: row, linha: entry.linha })
  prodespSyncMyJsonFromPreview()
  prodespRenderCsvPreview()
  if (!silent) {
    showToast(`Linha VGR ${idVgr} corrigida e movida para válidas.`, "success")
  }
  return true
}

function prodespColetarTodasInvalidasDoDom() {
  csvPreviewState.invalid.forEach((item, index) => {
    prodespEnsureInvalidUid(item, index)
    const edited = prodespColetarRowInvalidaDoDom(item._uid)
    if (edited) item.row = { ...item.row, ...edited }
  })
}

function prodespAplicarCorrecoesTodasInvalidas() {
  if (!csvPreviewState.invalid.length) {
    showToast("Não há linhas rejeitadas para aplicar.", "info")
    return
  }

  prodespColetarTodasInvalidasDoDom()
  const uids = csvPreviewState.invalid.map((item) => item._uid).slice()
  let ok = 0
  uids.forEach((uid) => {
    if (prodespRevalidarLinhaInvalida(uid, true)) ok += 1
  })
  prodespRenderCsvPreview()

  if (ok === uids.length) {
    showToast(`${ok} linha(s) corrigida(s) e pronta(s) para envio.`, "success")
  } else if (ok > 0) {
    showToast(
      `${ok} linha(s) movida(s) para válidas; ${uids.length - ok} ainda rejeitada(s).`,
      "warning",
      8000
    )
  } else {
    showToast("Nenhuma linha passou na revalidação. Revise os motivos na tabela.", "warning", 8000)
  }
}

function prodespImportErrosExportToPreview(errosProc, errosPrevia) {
  csvPreviewState.valid = []
  csvPreviewState.invalid = []
  csvPreviewState.semAcao = []
  csvPreviewState.ocultarSemAcaoNoPreview = true

  const todas = []
  ;(errosProc || []).forEach((r) => todas.push({ ...r, _origem: "processamento" }))
  ;(errosPrevia || []).forEach((r) => todas.push({ ...r, _origem: "previa" }))

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
    delete row._origem
    const item = {
      row: row,
      motivo: motivo,
      linha: index + 1,
      corrigivel: prodespRowExportCorrigivel(r),
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

  prodespSyncMyJsonFromPreview()
  prodespRenderCsvPreview()

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

function prodespGetTodasNaoAplicadasUltimoEnvio() {
  const proc = (window.prodespLastCsvErrosExport || []).map((r) => ({
    row: r,
    motivo: r.motivo,
  }))
  const prev = (window.prodespLastCsvRejeitadasPreviaExport || []).map((r) => ({
    row: r,
    motivo: r.motivo,
  }))
  return proc.concat(prev)
}

function prodespAtualizarBotoesUltimoEnvio() {
  const todas = prodespGetTodasNaoAplicadasUltimoEnvio()
  const corrigiveis = todas.filter((item) => prodespRowExportCorrigivel(item.row))
  const btnPost = document.getElementById("btn-export-post-erros")
  const btnCorrigir = document.getElementById("btn-corrigir-post-erros")
  if (btnPost) btnPost.classList.toggle("d-none", todas.length === 0)
  if (btnCorrigir) btnCorrigir.classList.toggle("d-none", corrigiveis.length === 0)
}

function prodespLimparUltimoEnvioCsv() {
  window.prodespLastCsvErrosExport = null
  window.prodespLastCsvRejeitadasPreviaExport = null
  prodespAtualizarBotoesUltimoEnvio()
}

function prodespRenderCsvPreview() {
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

  if (validSection) {
    validSection.classList.toggle("d-none", nValid === 0)
  }
  if (validCountEl) {
    validCountEl.textContent = String(nValid)
  }
  if (validEl) {
    validEl.innerHTML = prodespRenderPreviewTable(csvPreviewState.valid, false)
  }

  if (invalidSection) {
    invalidSection.classList.toggle("d-none", nInvalid === 0)
  }
  if (invalidEl) {
    invalidEl.innerHTML = prodespRenderEditableInvalidTable(csvPreviewState.invalid)
  }

  const exibirSemAcao = nSemAcao > 0 && !csvPreviewState.ocultarSemAcaoNoPreview
  if (semAcaoSection) {
    semAcaoSection.classList.toggle("d-none", !exibirSemAcao)
  }
  if (semAcaoResumo) {
    if (nSemAcao > 0 && csvPreviewState.ocultarSemAcaoNoPreview) {
      semAcaoResumo.textContent = `${nSemAcao} linha(s) sem ação de correção (concluídas, VGR inexistente ou duplicadas). Use «Baixar todas não aplicadas» ou o e-mail de resumo.`
      semAcaoResumo.classList.remove("d-none")
    } else {
      semAcaoResumo.textContent = ""
      semAcaoResumo.classList.add("d-none")
    }
  }
  if (semAcaoCountEl) {
    semAcaoCountEl.textContent = String(nSemAcao)
  }
  if (semAcaoEl && exibirSemAcao) {
    semAcaoEl.innerHTML = prodespRenderPreviewTable(csvPreviewState.semAcao, true)
  } else if (semAcaoEl) {
    semAcaoEl.innerHTML = ""
  }

  if (btnUpload) btnUpload.disabled = nValid === 0
  if (btnExportInvalid) btnExportInvalid.disabled = nRejeitadasTotal === 0
  btnsAplicarTodas.forEach((btn) => {
    btn.disabled = nInvalid === 0
    btn.classList.toggle("d-none", nInvalid === 0)
  })
}

function prodespRowsToCsvExport(rows) {
  const header = PRODESP_CSV_COLS.concat(["motivo"]).join(";")
  const lines = rows.map((item) => {
    const r = item.row || item
    const motivo = item.motivo || r.motivo || ""
    const vals = PRODESP_CSV_COLS.map((c) => {
      let v = r[c] ?? ""
      if (c === "data_agendamento") {
        v = prodespCsvFormatDataExibicao(r) || v
      }
      if (c === "hora_agendamento" && v && String(v).length >= 5) {
        v = String(v).trim().slice(0, 8)
      }
      v = String(v).replace(/"/g, '""')
      return v.includes(";") ? `"${v}"` : v
    })
    vals.push(motivo.includes(";") ? `"${motivo.replace(/"/g, '""')}"` : motivo)
    return vals.join(";")
  })
  return [header].concat(lines).join("\n")
}

function prodespDownloadTextFile(filename, content) {
  const blob = new Blob(["\ufeff" + content], { type: "text/csv;charset=utf-8" })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

function prodespExportInvalidCsv(rows, filename) {
  const previewRows = csvPreviewState.invalid.concat(csvPreviewState.semAcao)
  const data = rows && rows.length ? rows : previewRows
  if (!data.length) {
    showToast("Não há linhas inválidas para exportar.", "info")
    return
  }
  prodespDownloadTextFile(filename || "agendamento_rejeitadas.csv", prodespRowsToCsvExport(data))
}

function prodespBuildCsvPreview(parsedRows) {
  csvPreviewState.valid = []
  csvPreviewState.invalid = []
  csvPreviewState.semAcao = []
  csvPreviewState.ocultarSemAcaoNoPreview = false
  const seenVgr = new Set()

  parsedRows.forEach((entry) => {
    const row = entry.row
    const idVgr = String(row.id_vgr || "").trim()

    if (seenVgr.has(idVgr)) {
      prodespCsvPushRejeitada(
        row,
        "ID VGR duplicado no arquivo (segunda ocorrência ignorada; mantida a primeira).",
        entry.linha
      )
      return
    }
    seenVgr.add(idVgr)

    const erros = prodespValidarLinhaAgendamentoCsv(row)
    if (erros.length) {
      prodespCsvPushRejeitada(row, erros.join(" "), entry.linha)
    } else {
      csvPreviewState.valid.push({ row: row, linha: entry.linha })
    }
  })

  prodespSyncMyJsonFromPreview()
  prodespRenderCsvPreview()
}

function csvToJson(text) {
  keys = []
  const lines = text.trim().split("\n")
  const list = lines.map((line) =>
    line.includes("\r") ? line.slice(0, -1).split(";") : line.split(";")
  )

  list[0].forEach((item) => {
    keys.push(item.trim().toLowerCase())
  })

  const idxId = keys.indexOf("id_vgr")
  const idxData = keys.indexOf("data_agendamento")
  const idxHora = keys.indexOf("hora_agendamento")
  const idxContratada = keys.indexOf("contratada")
  const idxField = keys.indexOf("field")
  const idxContatoField = keys.indexOf("contato_field")

  const parsed = []

  list.slice(1).forEach((item, index) => {
    if (idxId === -1 || !item[idxId] || String(item[idxId]).trim() === "") return

    const obj = { id_vgr: String(item[idxId]).trim() }

    if (idxData !== -1 && item[idxData]) {
      const raw = String(item[idxData]).trim()
      obj.data_agendamento_raw = raw
      obj.data_agendamento = prodespCsvNormalizarDataIso(raw)
    }
    if (idxHora !== -1 && item[idxHora]) {
      obj.hora_agendamento = String(item[idxHora]).trim()
    }
    if (idxContratada !== -1 && item[idxContratada]) {
      obj.contratada = String(item[idxContratada]).trim()
    }
    if (idxField !== -1 && item[idxField]) {
      obj.field = String(item[idxField]).trim()
    }
    if (idxContatoField !== -1 && item[idxContatoField]) {
      obj.contato_field = String(item[idxContatoField]).trim()
    }

    const temAgenda = obj.data_agendamento || obj.hora_agendamento
    const temPlanejado =
      !prodespCsvValorAusente(obj.contratada) ||
      !prodespCsvValorAusente(obj.field) ||
      !prodespCsvValorAusente(obj.contato_field)
    if (!temAgenda && !temPlanejado) return

    parsed.push({ row: obj, linha: index + 2 })
  })

  csvPreviewState.headers = keys.slice()
  prodespBuildCsvPreview(parsed)
}

function convertFileInData(file) {
  const reader = new FileReader()
  reader.onload = (event) => {
    csvToJson(event.target.result)
    if (csvPreviewState.invalid.length || csvPreviewState.semAcao.length) {
      const nInv = csvPreviewState.invalid.length
      const nSem = csvPreviewState.semAcao.length
      let msgPrev = `Pré-validação: ${nInv + nSem} linha(s) não serão enviadas.`
      if (nInv && nSem) msgPrev += ` ${nInv} para correção · ${nSem} sem ação no portal.`
      else if (nSem) msgPrev += ` Todas sem ação de correção no portal.`
      showToast(msgPrev, "warning", 10000)
    } else if (csvPreviewState.valid.length) {
      showToast(
        `${csvPreviewState.valid.length} linha(s) pronta(s) para envio.`,
        "success",
        5000
      )
    }
  }
  if (file) reader.readAsText(file)
}

function prodespBuildRejeitadasPreviaPayload() {
  prodespColetarTodasInvalidasDoDom()
  return csvPreviewState.invalid.map((item) => {
    const row = prodespPrepareRowForSend(item.row)
    return {
      id_vgr: row.id_vgr,
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

    const rejeitadasPrevia = prodespBuildRejeitadasPreviaPayload()

    const res = await fetch("api/csv/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        keys: keys,
        body: MyJson,
        rejeitadas_previa: rejeitadasPrevia,
      }),
    })

    const data = await res.json()

    if (res.ok || res.status === 207) {
      const resumo = data.resumo || {}
      let tipo = "success"
      if (resumo.erros > 0 && resumo.sucesso > 0) tipo = "warning"
      else if (resumo.erros > 0 && !resumo.sucesso) tipo = "warning"
      else if (!resumo.sucesso && resumo.repetidos > 0) tipo = "info"
      showToast(data.msg || "Processamento concluído.", tipo, 12000)

      window.prodespLastCsvErrosExport = data.erros_export || []
      window.prodespLastCsvRejeitadasPreviaExport = data.rejeitadas_previa_export || []
      prodespAtualizarBotoesUltimoEnvio()

      fileInput.value = ""
      MyJson = null
      csvPreviewState = { valid: [], invalid: [], semAcao: [], headers: [], rawRows: [], ocultarSemAcaoNoPreview: false }
      prodespRenderCsvPreview()
    } else if (res.status === 403) {
      showToast(data.msg || "Acesso negado para o seu perfil.", "warning", 8000)
    } else if (res.status === 429) {
      showToast(data.msg || "Aguarde antes de enviar outro arquivo.", "warning", 8000)
    } else {
      showToast(data.msg || "Erro ao processar arquivo.", "danger")
    }
  } catch (error) {
    console.error(error)
    showToast("Erro de conexão com o servidor.", "danger")
  } finally {
    if (btnUpload) btnUpload.disabled = csvPreviewState.valid.length === 0
  }
}

document.addEventListener("click", async (e) => {
  const element = e.target

  if (element.id === "gerar-csv" || element.closest("#gerar-csv")) {
    try {
      const response = await fetch("api/csv/gerar")
      if (!response.ok) throw new Error(`Erro ${response.status}`)
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = "modelo_prodesp.csv"
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error(error)
      showToast("Erro ao baixar o modelo CSV.", "danger")
    }
  }

  if (element.id === "btn-upload" || element.closest("#btn-upload")) {
    sendCSV()
  }

  if (element.id === "btn-export-invalid-csv" || element.closest("#btn-export-invalid-csv")) {
    prodespExportInvalidCsv()
  }

  if (element.id === "btn-export-post-erros" || element.closest("#btn-export-post-erros")) {
    const rows = prodespGetTodasNaoAplicadasUltimoEnvio()
    if (!rows.length) {
      showToast("Não há linhas do último envio para exportar.", "info")
      return
    }
    prodespExportInvalidCsv(rows, "agendamento_nao_aplicadas.csv")
  }

  if (element.id === "btn-corrigir-post-erros" || element.closest("#btn-corrigir-post-erros")) {
    prodespImportErrosExportToPreview(
      window.prodespLastCsvErrosExport,
      window.prodespLastCsvRejeitadasPreviaExport
    )
  }

  if (element.closest(".btn-aplicar-todas-invalidas")) {
    prodespAplicarCorrecoesTodasInvalidas()
  }

  const btnRevalidarRow = element.closest(".btn-revalidar-invalid-row")
  if (btnRevalidarRow) {
    const uid = btnRevalidarRow.dataset.uid
    if (uid) prodespRevalidarLinhaInvalida(uid)
  }
})

document.getElementById("csv-preview-invalid")?.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" || !e.target.classList.contains("csv-invalid-input")) return
  e.preventDefault()
  const uid = e.target.dataset.uid
  if (uid) prodespRevalidarLinhaInvalida(uid)
})

document.getElementById("input-import-file")?.addEventListener("change", function () {
  const file = this.files[0]
  prodespLimparUltimoEnvioCsv()
  if (file) convertFileInData(file)
  else {
    MyJson = null
    csvPreviewState = { valid: [], invalid: [], semAcao: [], headers: [], rawRows: [], ocultarSemAcaoNoPreview: false }
    prodespRenderCsvPreview()
  }
})
