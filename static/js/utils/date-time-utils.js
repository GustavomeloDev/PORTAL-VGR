/**
 * Utilitários para manipulação de datas e horas.
 * Desacoplado para reutilização em todo o sistema.
 */

export const DateTimeUtils = {
    /**
     * Analisa strings de data e hora para criar um objeto Date.
     * Suporta formatos ISO e data/hora separados.
     * @param {string} dateStr - String da data (YYYY-MM-DD).
     * @param {string} timeStr - String da hora (HH:mm:ss).
     * @returns {Date|null} Objeto Date ou null se inválido.
     */
    parse: function(dateStr, timeStr) {
        if (!dateStr) return null;
        try {
            // Se já tiver hora na string de data (ISO)
            if (dateStr.includes('T') || dateStr.includes(' ')) {
                return new Date(dateStr);
            }
            // Se hora for fornecida, combina
            const dateTimeStr = timeStr ? `${dateStr}T${timeStr}` : `${dateStr}T00:00:00`;
            return new Date(dateTimeStr);
        } catch (e) {
            console.error("Erro ao fazer parsing da data:", e);
            return null;
        }
    },

    /**
     * Verifica o status do prazo em relação à data/hora atual.
     * @param {Date} scheduledDate - Data do agendamento.
     * @param {number} warningThresholdHours - Horas antes do vencimento para alerta (default 1).
     * @returns {string|null} 'expired', 'warning' ou null.
     */
    checkDeadlineStatus: function(scheduledDate, warningThresholdHours = 1) {
        if (!scheduledDate) return null;
        
        const now = new Date();
        const diffMs = scheduledDate - now;
        const diffHours = diffMs / (1000 * 60 * 60);

        if (diffMs < 0) {
            return 'expired';
        } else if (diffHours <= warningThresholdHours) {
            return 'warning';
        }
        return null;
    },

    /**
     * Formata data e hora para exibição amigável (PT-BR).
     * @param {Date} dateObj - Objeto Date.
     * @returns {string} String formatada (DD/MM/YYYY HH:mm).
     */
    format: function(dateObj) {
        if (!dateObj) return '-';
        return dateObj.toLocaleString('pt-BR', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    },

    /**
     * Formata para YYYY-MM-DD (Input Date).
     * @param {string|Date} date 
     */
    formatToIsoDate: function(date) {
        if (!date) return '';
        const s = String(date);
        const m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (m) return s;
        const d = new Date(s);
        if (isNaN(d.getTime())) return '';
        return d.toISOString().split('T')[0];
    },
    formatDateBR: function(date) {
        if (!date) return '—';
        try {
            const s = String(date);
            const m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
            if (m) return `${m[3]}/${m[2]}/${m[1]}`;
            const d = new Date(s);
            if (isNaN(d.getTime())) throw new Error('invalid');
            const dd = String(d.getDate()).padStart(2, '0');
            const mm = String(d.getMonth() + 1).padStart(2, '0');
            const yyyy = d.getFullYear();
            return `${dd}/${mm}/${yyyy}`;
        } catch (e) {
            return String(date);
        }
    },
    toInputTime: function(timeStr) {
        if (!timeStr) return '';
        let s = String(timeStr).trim();
        if (!s) return '';
        const dtMatch = s.match(/T(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?/);
        if (dtMatch) {
            const hh = dtMatch[1].padStart(2, '0');
            const mm = dtMatch[2].padStart(2, '0');
            return `${hh}:${mm}`;
        }
        const m = s.match(/(\d{1,2}):(\d{1,2})(?::(\d{1,2})(?:\.\d+)?)?/);
        if (m) {
            const hh = m[1].padStart(2, '0');
            const mm = m[2].padStart(2, '0');
            return `${hh}:${mm}`;
        }
        const d = new Date(s);
        if (!isNaN(d.getTime())) {
            const hh = String(d.getHours()).padStart(2, '0');
            const mm = String(d.getMinutes()).padStart(2, '0');
            return `${hh}:${mm}`;
        }
        const colonIndex = s.indexOf(':');
        if (colonIndex > 0 && s.length >= colonIndex + 3) {
            return s.slice(0, colonIndex + 3);
        }
        return '';
    },
    toInputDateTime: function(dateStr, timeStr) {
        const date = DateTimeUtils.formatToIsoDate(dateStr);
        const time = DateTimeUtils.toInputTime(timeStr) || '00:00';
        if (!date) return '';
        return `${date}T${time}`;
    },
    splitInputDateTime: function(dtLocal) {
        if (!dtLocal) return { date: '', time: '' };
        const m = String(dtLocal).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/);
        if (!m) return { date: '', time: '' };
        const date = `${m[1]}-${m[2]}-${m[3]}`;
        const time = `${m[4]}:${m[5]}:00`;
        return { date, time };
    }
};
