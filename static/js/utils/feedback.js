
export const Feedback = {
    /**
     * Helper interno para configurar opções do toastr padronizadas
     */
    _configureToastr(type = 'info') {
        if (!window.toastr) return;
        
        window.toastr.options = {
            closeButton: true,
            debug: false,
            newestOnTop: true,
            progressBar: true,
            positionClass: "toast-top-right", // Padronizado: Topo Direito
            preventDuplicates: true,
            onclick: null,
            showDuration: "300",
            hideDuration: "1000",
            timeOut: "8000",           // Padronizado: 8 segundos
            extendedTimeOut: "2000",
            showEasing: "swing",
            hideEasing: "linear",
            showMethod: "fadeIn",
            hideMethod: "fadeOut"
        };
    },

    /**
     * Exibe um toast de confirmação interativo.
     * @param {string} message - A mensagem a ser exibida.
     * @param {Function} onConfirm - A função a ser executada ao confirmar.
     * @param {string} [title="Confirmação"] - O título do toast.
     * @param {string} [type="warning"] - Tipo do toast (warning, error, info).
     */
    showConfirmation(message, onConfirm, title = "Atenção", type = "warning") {
        if (!window.toastr) {
            // Fallback se toastr não estiver carregado
            if (confirm(message)) onConfirm();
            return;
        }

        // ID único para os botões deste toast
        const toastId = 'toast-confirm-' + Date.now();
        
        // Template HTML com botões
        const html = `
            <div class="toast-confirm-content">
                <p class="mb-2">${message}</p>
                <div class="d-flex justify-content-end gap-2 mt-2">
                    <button id="${toastId}-no" class="btn btn-sm btn-light text-dark border-0">Cancelar</button>
                    <button id="${toastId}-yes" class="btn btn-sm btn-danger fw-bold">Confirmar</button>
                </div>
            </div>
        `;

        // Salva opções atuais
        const prevOptions = { ...window.toastr.options };

        // Configurações específicas para modal/persistente
        this._configureToastr();
        window.toastr.options.timeOut = "0"; // Não expira
        window.toastr.options.extendedTimeOut = "0";
        window.toastr.options.tapToDismiss = false;
        window.toastr.options.positionClass = "toast-top-right"; // Confirmação no canto superior direito

        const $toast = window.toastr[type](html, title);

        if ($toast && $toast.length) {
            const btnYes = $toast.find(`#${toastId}-yes`);
            const btnNo = $toast.find(`#${toastId}-no`);

            btnYes.on('click', async function(e) {
                e.preventDefault();
                e.stopPropagation();
                $toast.remove();
                window.toastr.options = prevOptions; // Restaura opções
                if (typeof onConfirm === 'function') await onConfirm();
            });

            btnNo.on('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                $toast.remove();
                window.toastr.options = prevOptions; // Restaura opções
            });
        }
        
        // Restaura opções imediatamente para não afetar outros toasts iniciados depois
        // (Nota: o toast atual já foi criado com as opções modificadas)
        window.toastr.options = prevOptions; 
    },

    /**
     * Exibe um feedback de erro padronizado e amigável.
     * Analisa o erro (objeto ou string) e decide a melhor mensagem.
     * @param {any} error - O erro capturado (Error object, string, ou response object).
     * @param {string} context - O contexto da operação (ex: "Salvar Agendamento", "Upload").
     */
    handleError(error, context = "Erro") {
        console.error(`[Feedback] Erro em '${context}':`, error);

        let title = context;
        let message = "Ocorreu um erro inesperado. Tente novamente.";

        // 1. Se for uma string direta
        if (typeof error === 'string') {
            message = error;
        } 
        // 2. Se for um objeto de erro padrão JS
        else if (error instanceof Error) {
            let baseMessage = error.message || "";
            const payload = error.data && typeof error.data === 'object' ? error.data : null;

            if (payload) {
                if (payload.message) baseMessage = payload.message;
                else if (payload.msg) baseMessage = payload.msg;
                else if (payload.error) baseMessage = payload.error;
            }

            message = baseMessage || error.message || "";

            if (message.includes("Failed to fetch") || message.includes("NetworkError")) {
                message = "Não foi possível conectar ao servidor. Verifique sua internet.";
            }
        }
        // 3. Se for um objeto de resposta da API (customizado)
        else if (typeof error === 'object') {
            const payload = error && error.data && typeof error.data === 'object' ? error.data : error;
            if (payload.message) message = payload.message;
            else if (payload.msg) message = payload.msg;
            else if (payload.error) message = payload.error;
            else if (error.message) message = error.message;
        }

        // Refinamentos de mensagem para ser mais amigável
        const lower = message.toLowerCase();
        if (lower.includes("internal server error") || message.includes("500")) {
            message = "Não foi possível concluir esta operação devido a um problema interno no servidor. Tente novamente em instantes.";
        } else if (lower.includes("network request failed") || lower.includes("failed to fetch") || lower.includes("networkerror")) {
            message = "Não foi possível concluir esta operação por falha na conexão. Verifique sua internet e tente novamente.";
        } else if ((lower.includes("id do link") || lower.includes("id_link")) && lower.includes("observ")) {
            message = "Para alterar o ID do Link (id_link), é obrigatório preencher o campo Observações com uma justificativa clara da mudança (mínimo 15 caracteres).";
            const obsEl = document.getElementById("obs");
            if (obsEl) obsEl.focus();
        } else if (lower.includes("duplicate entry") && lower.includes("uniq_link_idx")) {
            message = "Não foi possível salvar os links deste agendamento porque foi detectada uma inconsistência na posição dos links (mais de um link na mesma posição). Tente salvar novamente; se o erro persistir, entre em contato com o suporte informando o código do projeto.";
        } else if (lower.includes("observa") && lower.includes("15 caracteres")) {
            message = "Para concluir esta alteração, preencha o campo Observação com uma descrição clara da mudança (mínimo 15 caracteres).";
            const obsEl = document.getElementById("obs");
            if (obsEl) obsEl.focus();
        } else if (message.includes("413")) {
            message = "Não foi possível concluir o envio porque o arquivo é maior do que o permitido. Reduza o tamanho e tente novamente.";
        } else if (!message || !message.trim()) {
            message = "Não foi possível concluir esta operação. Tente novamente.";
        } else {
            message = `Não foi possível concluir ${title.toLowerCase()}. Motivo: ${message}`;
        }

        if (window.toastr) {
            this._configureToastr();
            window.toastr.options.timeOut = "10000";
            window.toastr.error(message, title);
        } else {
            alert(`${title}\n\n${message}`);
        }
    },

    /**
     * Exibe um feedback de sucesso.
     * @param {string} message 
     * @param {string} title 
     */
    showSuccess(message, title = "Sucesso") {
        if (window.toastr) {
            this._configureToastr();
            window.toastr.success(message, title);
        } else {
            alert(`${title}\n\n${message}`);
        }
    },

    /**
     * Exibe um feedback de aviso/atenção.
     * @param {string} message 
     * @param {string} title 
     */
    showWarning(message, title = "Atenção") {
        if (window.toastr) {
            this._configureToastr();
            window.toastr.warning(message, title);
        } else {
            alert(`[Atenção] ${message}`);
        }
    },

    /**
     * Exibe um feedback informativo.
     * @param {string} message 
     * @param {string} title 
     */
    showInfo(message, title = "Info") {
        if (window.toastr) {
            this._configureToastr();
            window.toastr.info(message, title);
        }
    }
};
