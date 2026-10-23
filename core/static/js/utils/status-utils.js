export const StatusUtils = {
    config: {
        success: ['confirmado', 'finalizado', 'ativado'],
        warning: ['pendente', 'aguardando', 'em andamento', 'agendado'],
        danger: ['cancelado', 'improdutiva', 'erro', 'falha'],
        info: ['novo', 'iniciado', 'analise'],
        attention: ['retorno', 'logistica', 'fornecedor'],
        secondary: []
    },
    classes: {
        success: 'bg-success',
        warning: 'bg-warning text-dark',
        danger: 'bg-danger',
        info: 'bg-info text-dark',
        attention: 'bg-warning bg-opacity-75 text-dark',
        cyan: 'bg-cyan text-white',
        secondary: 'bg-secondary'
    },
    // Mapeamento específico para status de agendamentos
    agendamentosStatusMap: {
        'pedente envio a logistica': 'status-gray',
        'tecnico em atendimento': 'status-gray',
        'tecnico em deslocamento': 'status-gray',
        'aguardando retorno logistica': 'status-orange',
        'aguardando retorno fornecedor': 'status-yellow-strong',
        'agendamento concluido': 'status-blue-light',
        'agendamento concluído': 'status-blue-light',
        'finalizado': 'status-green-light',
        'improdutiva': 'status-red'
    },
    getClass(status) {
        if (!status) return this.classes.secondary;
        const s = String(status).toLowerCase().trim();
        
        // Verifica se é um status de agendamentos com mapeamento específico
        if (this.agendamentosStatusMap[s]) {
            return this.agendamentosStatusMap[s];
        }
        
        if (s.trim() === 'retorno logistica') return this.classes.cyan;
        if (this.matches(s, this.config.success)) return this.classes.success;
        if (this.matches(s, this.config.danger)) return this.classes.danger;
        if (this.matches(s, this.config.attention)) return this.classes.attention;
        if (this.matches(s, this.config.warning)) return this.classes.warning;
        if (this.matches(s, this.config.info)) return this.classes.info;
        return this.classes.secondary;
    },
    matches(status, list) {
        return list.some(k => status.includes(k));
    },
    renderBadge(status, extra = '') {
        const cls = this.getClass(status);
        const text = status || 'N/A';
        return `<span class="badge ${cls} ${extra}">${text}</span>`;
    }
};
