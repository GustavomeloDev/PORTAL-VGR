import { StorageUtils } from "./storage-utils.js";

/**
 * Gerenciador de Auto-Save para Formulários
 * Monitora todos os campos do formulário e salva no LocalStorage temporariamente.
 */
export class FormAutoSave {
    /**
     * @param {string|HTMLElement} formElement - O elemento do formulário ou seletor
     * @param {string} uniqueId - Identificador único para este registro (ex: 'agendamento_123')
     * @param {string[]} fieldsToMonitor - Lista de IDs ou Names dos campos a monitorar (opcional, se vazio monitora todos)
     * @param {Object} options - Opções adicionais { ttl: 1440, debounce: 500 }
     */
    constructor(formElement, uniqueId, fieldsToMonitor = [], options = {}) {
        this.form = typeof formElement === 'string' ? document.querySelector(formElement) : formElement;
        this.uniqueId = uniqueId;
        this.fields = fieldsToMonitor;
        this.options = {
            ttl: 1440, // 24h em minutos
            debounce: 500,
            keyPrefix: 'autosave_',
            ...options
        };
        this.storageKey = `${this.options.keyPrefix}${this.uniqueId}`;
        this.timeout = null;
        this._initialized = false;
        this._boundSaveHandler = null;
        this._expectedUniqueId = null;
        
        if (!this.form) {
            console.error("FormAutoSave: Formulário não encontrado.");
        }
    }

    /**
     * Inicia o monitoramento dos campos
     */
    init() {
        if (!this.form) return;
        if (this._initialized) return;
        this._initialized = true;

        // Se não houver campos específicos definidos, monitora todos os campos do formulário
        if (this.fields.length === 0) {
            this._boundSaveHandler = () => this.debouncedSave();
            this.form.addEventListener('input', this._boundSaveHandler);
            this.form.addEventListener('change', this._boundSaveHandler);
            return;
        }

        this.fields.forEach(fieldKey => {
            const inputs = this._getInputsByFieldKey(fieldKey);
            inputs.forEach(input => {
                input.addEventListener('input', () => this.debouncedSave());
                input.addEventListener('change', () => this.debouncedSave());
            });
        });
    }

    /**
     * Salva os dados no storage com debounce
     */
    debouncedSave() {
        if (this.timeout) clearTimeout(this.timeout);
        this.timeout = setTimeout(() => this.save(), this.options.debounce);
    }

    /**
     * Coleta e salva os dados atuais
     */
    save() {
        if (this._expectedUniqueId && this.uniqueId !== this._expectedUniqueId) {
            this.switchUniqueId(this._expectedUniqueId);
        }
        const data = {};

        const saveInputValue = (fieldKey, inputOrInputs) => {
            const inputs = Array.isArray(inputOrInputs) ? inputOrInputs : [inputOrInputs];
            if (inputs.length === 0) return;

            const first = inputs[0];
            if (first.type === 'file') return;

            if (first.type === 'radio') {
                const selected = inputs.find(r => r && r.checked);
                if (selected) data[fieldKey] = selected.value;
                return;
            }

            if (first.type === 'checkbox' && inputs.length > 1) {
                data[fieldKey] = inputs.filter(c => c && c.checked).map(c => c.value);
                return;
            }

            const input = first;
            if (input.type === 'checkbox') {
                data[fieldKey] = input.checked;
                return;
            }

            if (input.tagName === 'SELECT' && input.multiple) {
                data[fieldKey] = Array.from(input.selectedOptions).map(o => o.value);
                return;
            }

            data[fieldKey] = input.value;
        };

        if (this.fields.length === 0) {
            const inputs = this.form.querySelectorAll('input, textarea, select');
            inputs.forEach(input => {
                const fieldKey = input.id || input.name;
                if (!fieldKey) return;
                const resolvedInputs = this._getInputsByFieldKey(fieldKey);
                saveInputValue(fieldKey, resolvedInputs.length > 0 ? resolvedInputs : input);
            });
        } else {
            this.fields.forEach(fieldKey => {
                const inputs = this._getInputsByFieldKey(fieldKey);
                if (inputs.length > 0) saveInputValue(fieldKey, inputs);
            });
        }

        // Salva apenas se houver algo coletado
        if (Object.keys(data).length > 0) {
            StorageUtils.set(this.storageKey, data, this.options.ttl);
            // console.debug(`[AutoSave] Dados salvos para ${this.uniqueId}`, data);
        }
    }

    /**
     * Verifica se há dados salvos e retorna
     * @returns {Object|null}
     */
    getSavedData() {
        return StorageUtils.get(this.storageKey);
    }

    /**
     * Limpa os dados salvos para esta instância
     */
    clear() {
        StorageUtils.remove(this.storageKey);
        // console.debug(`[AutoSave] Dados limpos para ${this.uniqueId}`);
    }

    /**
     * Restaura os dados nos campos
     * @param {boolean} notify - Se true, pode implementar callback visual (não implementado aqui)
     * @returns {boolean} - True se restaurou algo
     */
    restore() {
        const data = this.getSavedData();
        if (!data) return false;

        let restoredCount = 0;
        
        // Se não houver campos específicos definidos, restaura todos os campos salvos
        const fieldsToRestore = this.fields.length > 0 ? this.fields : Object.keys(data);

        const applyValue = (input, value) => {
            if (!input) return false;

            if (input.type === 'file') return false;

            if (input.type === 'checkbox') {
                if (Array.isArray(value)) {
                    input.checked = value.includes(input.value);
                } else {
                    input.checked = !!value;
                }
            } else if (input.tagName === 'SELECT' && input.multiple && Array.isArray(value)) {
                const selected = new Set(value.map(v => String(v)));
                Array.from(input.options).forEach(opt => {
                    opt.selected = selected.has(String(opt.value));
                });
            } else {
                input.value = value;
            }

            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        };

        fieldsToRestore.forEach(fieldKey => {
            const value = data[fieldKey];
            if (value === undefined || value === null) return;

            const inputs = this._getInputsByFieldKey(fieldKey);
            if (inputs.length === 0) return;

            const first = inputs[0];
            if (first.type === 'radio') {
                const radio = inputs.find(r => r && String(r.value) === String(value));
                if (radio) {
                    radio.checked = true;
                    radio.dispatchEvent(new Event('input', { bubbles: true }));
                    radio.dispatchEvent(new Event('change', { bubbles: true }));
                    restoredCount++;
                }
                return;
            }

            inputs.forEach(input => {
                if (applyValue(input, value)) restoredCount++;
            });
        });

        return restoredCount > 0;
    }

    /**
     * Método auxiliar para obter todos os campos do formulário
     * @returns {string[]} Array com IDs e names dos campos
     */
    getAllFormFields() {
        const fields = [];
        const inputs = this.form.querySelectorAll('input, textarea, select');
        
        inputs.forEach(input => {
            // Prioriza o ID, se não houver, usa o name
            const fieldId = input.id || input.name;
            if (fieldId && !fields.includes(fieldId)) {
                fields.push(fieldId);
            }
        });
        
        return fields;
    }

    _getInputsByFieldKey(fieldKey) {
        if (!this.form || !fieldKey) return [];

        const byId = document.getElementById(fieldKey);
        if (byId && this.form.contains(byId)) return [byId];

        const named = this.form.elements && this.form.elements.namedItem(fieldKey);
        if (named) {
            if (named instanceof RadioNodeList) {
                return Array.from(named).filter(Boolean);
            }
            return [named];
        }

        try {
            const escaped = this._escapeAttributeValue(fieldKey);
            return Array.from(this.form.querySelectorAll(`[name="${escaped}"]`));
        } catch (e) {
            return [];
        }
    }

    _escapeAttributeValue(value) {
        return String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    }

    /**
     * Limpa os dados salvos (chamar ao salvar o formulário com sucesso)
     */
    clear() {
        StorageUtils.remove(this.storageKey);
    }
    
    /**
     * Método estático para verificar se existe rascunho sem instanciar tudo
     */
    static hasDraft(uniqueId, keyPrefix='autosave_') {
        return !!StorageUtils.get(`${keyPrefix}${uniqueId}`);
    }

    static makeKey(uniqueId, keyPrefix='autosave_') {
        return `${keyPrefix}${uniqueId}`;
    }

    switchUniqueId(newUniqueId) {
        if (!newUniqueId || newUniqueId === this.uniqueId) return;

        const oldKey = this.storageKey;
        const newKey = FormAutoSave.makeKey(newUniqueId, this.options.keyPrefix);

        const oldData = StorageUtils.get(oldKey);
        const newData = StorageUtils.get(newKey);

        if (oldData && !newData) {
            StorageUtils.set(newKey, oldData, this.options.ttl);
            StorageUtils.remove(oldKey);
        }

        this.uniqueId = newUniqueId;
        this.storageKey = newKey;
    }

    destroy() {
        if (!this.form) return;
        if (this.timeout) {
            clearTimeout(this.timeout);
            this.timeout = null;
        }
        if (this._boundSaveHandler) {
            this.form.removeEventListener('input', this._boundSaveHandler);
            this.form.removeEventListener('change', this._boundSaveHandler);
            this._boundSaveHandler = null;
        }
        this._initialized = false;
    }

    setExpectedUniqueId(expectedId) {
        this._expectedUniqueId = expectedId;
    }
}