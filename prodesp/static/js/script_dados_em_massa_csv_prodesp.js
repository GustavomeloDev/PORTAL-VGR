/**
 * @file prodesp/static/js/script_dados_em_massa_csv_prodesp.js
 * @module PRODESP — Importação em massa (unidades/links/equipamentos)
 *
 * Finalidade:
 *   Upload de CSV para carga em massa: download do modelo, envio do arquivo e feedback
 *   via toast. Comunica com /prodesp/api/dadosemmassa_csv/*.
 *
 * Telas:
 *   - prodesp/templates/prodesp_dados_em_massa_csv.html
 *
 * Depende de:
 *   - Bootstrap 5 (toast), fetch API
 */
// ======= VARIAVEL GLOBAL ============ //
let MyJson = null;
let keys = [];

// ======= FUNÇÃO TOAST (Bootstrap 5) ============ //
function showToast(message, type = "info", delay = 5000) {
    const toastContainer = document.querySelector(".toast-container");
    if (!toastContainer) return;

    const toastId = "toast-" + Date.now();
    const toastHeaderClass = {
        success: "bg-success text-white",
        danger: "bg-danger text-white",
        warning: "bg-warning text-dark",
        info: "bg-primary text-white",
    }[type] || "bg-secondary text-white";

    const toastHtml = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header ${toastHeaderClass}">
                <strong class="me-auto">Notificação</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body">${message}</div>
        </div>`;

    toastContainer.insertAdjacentHTML("beforeend", toastHtml);
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, { delay: delay });
    toastElement.addEventListener("hidden.bs.toast", () => toastElement.remove());
    toast.show();
}

// ======= EVENT DELEGATION PARA BOTÕES ============ //
document.addEventListener('click', async (e) => {
    const element = e.target;

    // Botão Gerar Modelo
    if (element.id === 'gerar-csv' || element.closest('#gerar-csv')) {
        try {
            const response = await fetch('/prodesp/api/dadosemmassa_csv/template');
            if (!response.ok) throw new Error(`Erro ${response.status}`);
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'modelo_importacao_prodesp.csv';
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
        } catch (error) {
            console.error('Erro ao baixar o CSV:', error);
            showToast('Erro ao baixar o modelo CSV.', 'danger');
        }
    }

    // Botão Upload
    if (element.id === 'btn-upload' || element.closest('#btn-upload') || element.id === 'btnSubmitDadosEmMassa') {
        if (element.id === 'btnSubmitDadosEmMassa' || element.closest('#btnSubmitDadosEmMassa')) e.preventDefault();
        sendCSV();
    }
});

// ======= LISTENER PARA SELEÇÃO DE ARQUIVO ============ //
document.addEventListener('change', (e) => {
    if (e.target.id === 'csvFileInput') {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = event => csvToJson(event.target.result);
            reader.readAsText(file);
        }
    }
});

// ======= CONVERTE O TEXTO DO CSV EM JSON ============ //
function csvToJson(text) {
    const lines = text.trim().split('\n');
    const list = lines.map(line => line.includes('\r') ? line.slice(0, -1).split(';') : line.split(';'));
    if (list.length < 2) return;

    keys = list[0].map(h => h.trim().toLowerCase());
    MyJson = list.slice(1).map(values => {
        const obj = {};
        keys.forEach((h, i) => {
            if (h) obj[h] = values[i] ? values[i].trim() : '';
        });
        return obj;
    }).filter(row => row[keys[0]] !== ""); // Filtra linhas vazias
}

// ======= ENVIA OS DADOS PARA O BACKEND ============ //
async function sendCSV() {
    const fileInput = document.getElementById('csvFileInput');
    const btnUpload = document.getElementById('btnSubmitDadosEmMassa');
    const statusDiv = document.getElementById('dadosEmMassaStatus');

    if (fileInput && fileInput.files[0] && MyJson && MyJson.length > 0) {
        try {
            if (btnUpload) btnUpload.disabled = true;
            showToast("Processando envio, aguarde...", "info", 3000);

            const res = await fetch('/prodesp/api/dadosemmassa_csv/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ body: MyJson })
            });
            const data = await res.json();
            if (res.ok || res.status === 207) {
                showToast(data.msg || 'Dados processados com sucesso!', res.status === 207 ? 'warning' : 'success', 10000);
                if (statusDiv) statusDiv.classList.remove('d-none');
                document.getElementById('dadosEmMassaMsg').textContent = data.msg;
                if (data.errors && data.errors.length) {
                    document.getElementById('dadosEmMassaErrors').innerHTML = data.errors.slice(0, 10).join('<br>') + (data.errors.length > 10 ? '<br>...' : '');
                }
                fileInput.value = '';
                MyJson = null;
            } else {
                showToast(data.msg || 'Erro ao processar arquivo.', 'danger');
            }
        } catch (error) {
            console.error(error);
            showToast('Erro de conexão com o servidor.', 'danger');
        } finally {
            if (btnUpload) btnUpload.disabled = false;
        }
    } else {
        showToast('Por favor, selecione um arquivo CSV válido.', 'warning');
    }
}
