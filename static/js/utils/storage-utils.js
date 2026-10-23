/**
 * Utilitário para gerenciamento de LocalStorage com expiração (TTL)
 */
export class StorageUtils {
    /**
     * Salva um item com expiração
     * @param {string} key - Chave de armazenamento
     * @param {any} value - Valor a ser armazenado
     * @param {number} ttlInMinutes - Tempo de vida em minutos (Padrão: 1440 = 24h)
     */
    static set(key, value, ttlInMinutes = 1440) {
        const now = new Date();
        const item = {
            value: value,
            expiry: now.getTime() + (ttlInMinutes * 60 * 1000)
        };
        try {
            localStorage.setItem(key, JSON.stringify(item));
        } catch (e) {
            console.warn("StorageUtils: Falha ao salvar item (Quota exceeded?)", e);
        }
    }

    /**
     * Recupera um item verificando a expiração
     * @param {string} key - Chave de armazenamento
     * @returns {any|null} - Valor armazenado ou null se expirado/não existir
     */
    static get(key) {
        const itemStr = localStorage.getItem(key);
        if (!itemStr) return null;

        try {
            const item = JSON.parse(itemStr);
            const now = new Date();

            if (now.getTime() > item.expiry) {
                localStorage.removeItem(key);
                return null;
            }
            return item.value;
        } catch (e) {
            console.error("StorageUtils: Erro ao parsear item", e);
            return null;
        }
    }

    /**
     * Remove um item específico
     * @param {string} key 
     */
    static remove(key) {
        localStorage.removeItem(key);
    }

    /**
     * Limpa itens expirados com um prefixo específico (Manutenção)
     * @param {string} prefix 
     */
    static cleanup(prefix) {
        Object.keys(localStorage).forEach(key => {
            if (prefix && !key.startsWith(prefix)) return;
            this.get(key); // O método get já remove se estiver expirado
        });
    }
}
