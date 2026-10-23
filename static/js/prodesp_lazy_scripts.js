/**
 * Carregamento tardio de scripts PRODESP (P3 — reduz parse inicial).
 */
(function () {
  "use strict";

  const _promises = Object.create(null);

  function prodespLoadScriptOnce(url) {
    if (!url) return Promise.reject(new Error("URL inválida"));
    if (_promises[url]) return _promises[url];
    _promises[url] = new Promise(function (resolve, reject) {
      const existing = document.querySelector('script[data-prodesp-lazy-src="' + url + '"]');
      if (existing) {
        if (existing.dataset.prodespLoaded === "1") {
          resolve();
          return;
        }
        existing.addEventListener("load", function () {
          resolve();
        });
        existing.addEventListener("error", function () {
          reject(new Error("Falha ao carregar " + url));
        });
        return;
      }
      const s = document.createElement("script");
      s.src = url;
      s.async = true;
      s.dataset.prodespLazySrc = url;
      s.addEventListener("load", function () {
        s.dataset.prodespLoaded = "1";
        resolve();
      });
      s.addEventListener("error", function () {
        delete _promises[url];
        reject(new Error("Falha ao carregar " + url));
      });
      document.head.appendChild(s);
    });
    return _promises[url];
  }

  const MODAL_SCRIPTS = {
    historico: "/prodesp/static/js/prodesp_historico_view.js",
    enriquecer: "/prodesp/static/js/prodesp_enriquecer_endereco.js",
    caderno: "/prodesp/static/js/prodesp_caderno_teste.js?v=caderno-ssh-diag-1",
    certificado: "/prodesp/static/js/prodesp_certificado_export.js",
  };

  async function prodespEnsureModalScripts(kinds) {
    const list = Array.isArray(kinds) ? kinds : [kinds];
    const prefix = window.PRODESP_URL_PREFIX || "/prodesp";
    const tasks = list.map(function (kind) {
      const rel = MODAL_SCRIPTS[kind];
      if (!rel) return Promise.resolve();
      const url = rel.startsWith("/") ? rel : prefix + "/static/js/" + rel;
      return prodespLoadScriptOnce(url).then(function () {
        if (kind === "enriquecer" && typeof window.prodespInitEnriquecerEndereco === "function") {
          window.prodespInitEnriquecerEndereco();
        }
        if (kind === "caderno" && typeof window.prodespInitCadernoTeste === "function") {
          window.prodespInitCadernoTeste();
        }
        if (kind === "certificado" && typeof window.prodespInitCertificadoExport === "function") {
          window.prodespInitCertificadoExport();
        }
      });
    });
    await Promise.all(tasks);
  }

  window.prodespLoadScriptOnce = prodespLoadScriptOnce;
  window.prodespEnsureModalScripts = prodespEnsureModalScripts;
})();
