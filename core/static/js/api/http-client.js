export const HttpClient = {
    config: {
        baseUrl: '',
        defaultHeaders: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        timeout: 15000,
        retries: 1,
        retryDelay: 500
    },
    async get(endpoint) {
        return this.request(endpoint, { method: 'GET' });
    },
    async post(endpoint, body = {}) {
        return this.request(endpoint, { method: 'POST', body: JSON.stringify(body) });
    },
    async put(endpoint, body = {}) {
        return this.request(endpoint, { method: 'PUT', body: JSON.stringify(body) });
    },
    async delete(endpoint) {
        return this.request(endpoint, { method: 'DELETE' });
    },
    async request(endpoint, options = {}) {
        const base = this.config.baseUrl || `${location.protocol}//${location.host}`;
        const url = /^https?:\/\//i.test(endpoint) ? endpoint : `${base}${endpoint}`;
        const headers = { ...this.config.defaultHeaders, ...options.headers };
        let lastErr = null;
        let attempt = 0;
        const maxRetries = typeof this.config.retries === 'number' ? this.config.retries : 0;
        const timeoutMs = options.timeout || this.config.timeout || 15000;
        while (attempt <= maxRetries) {
            const controller = new AbortController();
            const tid = setTimeout(() => controller.abort(), timeoutMs);
            try {
                const response = await fetch(url, { ...options, headers, signal: controller.signal });
                clearTimeout(tid);
                if (!response.ok) {
                    let data = null;
                    try { data = await response.json(); } catch (_) {}
                    const error = new Error((data && data.message) || `HTTP ${response.status}`);
                    error.status = response.status;
                    error.data = data;
                    throw error;
                }
                const ct = response.headers.get('content-type') || '';
                if (ct.includes('application/json')) return await response.json();
                return await response.text();
            } catch (e) {
                clearTimeout(tid);
                
                // Se o erro já possui status (ex: 400, 404, 500 lançados acima), relança original
                if (e.status) {
                    throw e;
                }

                lastErr = e;
                const isAbort = e && e.name === 'AbortError';
                const isNetwork = e instanceof TypeError || (e && String(e.message || '').toLowerCase().includes('network'));
                if (attempt < maxRetries && (isAbort || isNetwork)) {
                    attempt += 1;
                    await new Promise(r => setTimeout(r, this.config.retryDelay || 500));
                    continue;
                }
                const friendly = new Error('Falha de conexão com o servidor. Verifique VPN/proxy, endereço base e certificado SSL.');
                friendly.cause = e;
                friendly.status = 0;
                throw friendly;
            }
        }
        throw lastErr;
    }
};

