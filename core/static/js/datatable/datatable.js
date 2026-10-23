import { DateTimeUtils } from '../utils/date-time-utils.js';
import { StatusUtils } from '../utils/status-utils.js';

export const DataTableModule = {
  /**
   * Limpa filtros da tabela e inputs associados
   * @param {string|Object} tableSelectorOrInstance - Seletor ou instância da tabela
   * @param {Object} opts - Opções: { inputsSelector, onClear }
   */
  clearFilters(tableSelectorOrInstance, opts = {}) {
    let table = tableSelectorOrInstance;
    if (typeof tableSelectorOrInstance === 'string' && window.jQuery?.fn?.DataTable) {
      table = window.jQuery(tableSelectorOrInstance).DataTable();
    }
    
    if (table) {
      table.search('').columns().search('').draw();
    }
    
    if (opts.inputsSelector) {
      const inputs = document.querySelectorAll(opts.inputsSelector);
      inputs.forEach(el => {
        if (el.type === 'checkbox' || el.type === 'radio') {
            el.checked = false;
        } else {
            el.value = '';
        }
        el.dispatchEvent(new Event('change', { bubbles: true }));
      });
    }
    
    if (typeof opts.onClear === 'function') {
      opts.onClear();
    }
  },

  renderDateColumn(dateField, timeField) {
    return function (data) {
      const d = data?.[dateField] || '';
      const t = data?.[timeField] || '';
      const dd = DateTimeUtils.formatDateBR(d);
      const tt = t ? String(t).slice(0, 5) : '';
      return `${dd}${tt ? ' ' + tt : ''}`;
    };
  },
  deadlineRowCallback(dateField, timeField, opts = {}) {
    const warningThresholdHours = Number(opts.warningThresholdHours ?? 1);    // amarelo quando faltam <= X horas
    const graceAfterHours = Number(opts.graceAfterHours ?? 24);               // não marca vermelho por até X horas após o horário
    return function (row, data) {
      const d = data?.[dateField];
      const t = data?.[timeField];
      if (!d) return;
      const scheduled = DateTimeUtils.parse(d, t);
      if (!(scheduled instanceof Date) || isNaN(scheduled.getTime())) return;
      const now = new Date();
      const diffMs = scheduled - now;
      const diffHours = diffMs / (1000 * 60 * 60);
      const status = String(data?.status || '').toLowerCase();
      const isAttention = StatusUtils.matches(status, StatusUtils.config.attention) || status.includes('envio ao portal');
      const sameDay =
        scheduled.getFullYear() === now.getFullYear() &&
        scheduled.getMonth() === now.getMonth() &&
        scheduled.getDate() === now.getDate();
      if (diffHours < 0) {
        // Passou do horário: aplica regra de graça para estados de atenção (ex.: fornecedor/logistica/retorno)
        if (isAttention && Math.abs(diffHours) <= graceAfterHours) {
          row.classList.add('table-warning');
        } else {
          row.classList.add('table-danger');
        }
      } else if (diffHours <= warningThresholdHours) {
        row.classList.add('table-warning');
      } else if (sameDay) {
        row.classList.add('table-primary');
      }
    };
  },
  initDateFilter(tableSelector, columnIndex, containerSelector, opts = {}) {
    const container = document.querySelector(containerSelector);
    if (!container) return;
    // Layout
    const wrap = document.createElement('div');
    wrap.className = 'date-range d-flex align-items-center gap-3';
    const groupStart = document.createElement('div');
    groupStart.className = 'date-group flex-fill';
    const labelStart = document.createElement('label');
    labelStart.textContent = (opts.labelStart || 'Data Início') + ':';
    labelStart.className = 'form-label mb-1';
    const start = document.createElement('input');
    start.type = 'date';
    start.className = 'form-control';
    start.placeholder = 'dd/mm/aaaa';
    const groupEnd = document.createElement('div');
    groupEnd.className = 'date-group flex-fill';
    const labelEnd = document.createElement('label');
    labelEnd.textContent = (opts.labelEnd || 'Data Fim') + ':';
    labelEnd.className = 'form-label mb-1';
    const end = document.createElement('input');
    end.type = 'date';
    end.className = 'form-control';
    end.placeholder = 'dd/mm/aaaa';
    groupStart.appendChild(labelStart);
    groupStart.appendChild(start);
    groupEnd.appendChild(labelEnd);
    groupEnd.appendChild(end);
    wrap.appendChild(groupStart);
    wrap.appendChild(groupEnd);
    container.innerHTML = '';
    container.appendChild(wrap);
    // Filtro
    const tableEl = window.jQuery?.fn?.DataTable ? window.jQuery(tableSelector).DataTable() : null;
    if (!tableEl) return;
    const rowDateField = opts.rowDateField || null;
    const rowTimeField = opts.rowTimeField || null;
    const filterFn = function(settings, data, dataIndex, rowData) {
      const sVal = start.value;
      const eVal = end.value;
      if (!sVal && !eVal) return true;
      let scheduled = null;
      if (rowDateField) {
        scheduled = DateTimeUtils.parse(rowData?.[rowDateField], rowData?.[rowTimeField]);
      } else {
        // fallback: tenta ler a célula da coluna
        const cell = tableEl.cell(dataIndex, columnIndex).data();
        // esperado "DD/MM/YYYY HH:mm" ou "DD/MM/YYYY"
        const m = String(cell || '').match(/(\d{2})\/(\d{2})\/(\d{4})(?:\s+(\d{2}):(\d{2}))?/);
        if (m) {
          const iso = `${m[3]}-${m[2]}-${m[1]}`;
          const time = m[4] && m[5] ? `${m[4]}:${m[5]}:00` : '00:00:00';
          scheduled = DateTimeUtils.parse(iso, time);
        }
      }
      if (!(scheduled instanceof Date) || isNaN(scheduled.getTime())) return true;
      const startDate = sVal ? new Date(`${sVal}T00:00:00`) : null;
      const endDate = eVal ? new Date(`${eVal}T23:59:59`) : null;
      if (startDate && scheduled < startDate) return false;
      if (endDate && scheduled > endDate) return false;
      return true;
    };
    window.jQuery.fn.dataTable.ext.search.push(filterFn);
    const apply = () => tableEl.draw();
    start.addEventListener('change', apply);
    end.addEventListener('change', apply);
  },
  
  /**
   * Configura filtros de KPI para cards clicáveis
   * Novo padrão (obrigatório): objeto de configuração.
   * @param {Object} config
   * @param {string} config.tableSelector - Seletor da tabela DataTable
   * @param {number} config.columnIndex - Índice da coluna a ser filtrada
   * @param {Array} config.filters - Array de filtros [{cardId, filterRegex}]
   * @param {string} [config.clearButtonId] - ID do botão para limpar filtros (opcional)
   */
  initKpiFilters(config) {
    const tableSelector = config?.tableSelector;
    const columnIndex = config?.columnIndex;
    const filters = config?.filters;
    const clearButtonId = config?.clearButtonId || null;

    if (!tableSelector || typeof columnIndex !== 'number' || !Array.isArray(filters)) {
      console.warn('Configuração inválida para initKpiFilters. Use { tableSelector, columnIndex, filters, clearButtonId? }.');
      return;
    }

    const tableEl = window.jQuery?.fn?.DataTable ? window.jQuery(tableSelector).DataTable() : null;
    if (!tableEl) {
      console.warn(`Tabela ${tableSelector} não encontrada. Filtros de KPI não configurados.`);
      return;
    }

    // Função para aplicar filtro
    const applyFilter = (regex) => {
      tableEl.column(columnIndex).search(regex, true, false).draw();
    };

    // Função para limpar filtros
    const clearFilters = () => {
      tableEl.search('').columns().search('').draw();
    };

    // Configura cada card de KPI
    filters.forEach(filter => {
      const cardElement = document.getElementById(filter.cardId);
      if (cardElement) {
        const card = cardElement.closest('.performance-card') || cardElement;
        card.style.cursor = 'pointer';
        card.addEventListener('click', () => {
          applyFilter(filter.filterRegex);
        });
      }
    });

    // Configura botão de limpar filtros
    if (clearButtonId) {
      const clearBtn = document.getElementById(clearButtonId);
      if (clearBtn) {
        clearBtn.addEventListener('click', clearFilters);
      }
    }
  }
};
