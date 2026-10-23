export const MaskUtils = {
  apply(root = document) {
    try {
      const $ = window.jQuery || window.$;
      const hasMask = !!($ && $.fn && $.fn.mask);
      const scope = root instanceof Element ? root : document;

      const inputs = scope.querySelectorAll('input, textarea');
      inputs.forEach((el) => {
        const name = (el.getAttribute('name') || '').toLowerCase();
        const id = (el.id || '').toLowerCase();
        const dataMask = el.getAttribute('data-mask');

        if (hasMask && dataMask) {
          $(el).mask(dataMask);
          return;
        }

        if (!hasMask) return;

        const isPhone =
          name.includes('telefone') ||
          name.includes('contato') ||
          id.includes('telefone') ||
          id.includes('contato');

        const isCnpj =
          name.includes('cnpj') || id.includes('cnpj');

        const isCep =
          name.includes('cep') || id.includes('cep');

        if (isPhone) {
          // Comportamento dinâmico para 10 ou 11 dígitos (Padrão brasileiro)
          const behavior = function (val) {
            return val.replace(/\D/g, '').length === 11 ? '(00) 00000-0000' : '(00) 0000-00009';
          };
          
          const options = {
            onKeyPress: function (val, e, field, options) {
              field.mask(behavior.apply({}, arguments), options);
            },
            clearIfNotMatch: false
          };

          $(el).mask(behavior, options);
          return;
        }

        if (isCnpj) {
          $(el).mask('00.000.000/0000-00');
          return;
        }

        if (isCep) {
          $(el).mask('00000-000');
          return;
        }
      });
    } catch (e) {
      console.warn('[MaskUtils] falha ao aplicar máscaras:', e);
    }
  },
};
