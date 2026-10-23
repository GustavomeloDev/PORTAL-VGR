# Completar endereço (`core.utils.endereco_enriquecimento`)

Padrão do portal para **sugerir** número, bairro, CEP, município/UF e lat/long a partir do que o usuário já digitou.

- **Não grava no banco.** O módulo decide persistir depois (save da unidade / blueprint).
- **Prodesp** mantém cópia própria (`prodesp/prodesp/endereco_enriquecimento.py`) e **não** importa este pacote.

```
core/utils/endereco_enriquecimento_engine.py   # motor (ViaCEP / OpenCEP / BrasilAPI / Nominatim)
core/utils/endereco_enriquecimento.py          # fachada enriquecer_endereco_portal
core/static/js/utils/portal_enriquecer_endereco.js
```

O motor **não** importa `prodesp.credentials`. Logs: `PORTAL.endereco`.

---

## Consumidores atuais

| Módulo | Rota POST (login + CSRF) | JS `PortalEnriquecerEndereco.bind` |
|--------|---------------------------|-------------------------------------|
| **DMA** | `POST /dma/api/enriquecer-endereco` (`dma/app.py`) | `dma_blueprints.js` — botão `btnCompletarEndereco` |
| **VGR** | `POST /vgr/api/enriquecer-endereco` (`vgr/app.py`) | `vgr_unidades.js` — botão `btnVgrCompletarEndereco` |
| **FUST** | `POST /fust/api/enriquecer-endereco` (`fust/app.py`) | `script_chamados_fust.js` — criar/editar/gestão |
| **Prodesp** | `POST /prodesp/api/enriquecer-endereco` | Motor **local** do módulo, não o Core |

---

## Python — como chamar

Módulos novos devem usar **somente** a fachada:

```python
from core.utils.endereco_enriquecimento import enriquecer_endereco_portal

result = enriquecer_endereco_portal({
    "endereco": "Rua Curitiba 1001",
    "numero": "",
    "bairro": "",
    "cidade": "Belo Horizonte",   # alias de municipio
    "uf": "MG",                    # alias de estado
    "cep": "",
    "latitude": "",
    "longitude": "",
})
```

A fachada:

1. Recorta strings (máx. 500).
2. Mapeia `cidade` → `municipio` e `uf` → `estado` na entrada.
3. Chama `enriquecer_endereco_unidade`.
4. Devolve também `updates.cidade` / `updates.uf` se o motor preencheu município/estado.

### Contrato de retorno

```json
{
  "success": true,
  "updates": { "bairro": "...", "cep": "...", "latitude": "...", "longitude": "..." },
  "warnings": [],
  "message": "Endereço conferido.",
  "partial": false,
  "sources": ["cep_viacep", "..."]
}
```

- `success: false` + `message` se o motor falhar.
- Só sugere campo **vazio ou placeholder** (`x`, `n/a`, `0`, etc.). Não sobrescreve dado válido.
- Exceções de rede: o **endpoint do módulo** captura e devolve 500 genérico (sem stack ao cliente).

### Rota Flask (padrão DMA / VGR)

```python
@bp.route("/api/enriquecer-endereco", methods=["POST"])
@login_required
def api_enriquecer_endereco():
    data = request.get_json(silent=True) or {}
    try:
        from core.utils.endereco_enriquecimento import enriquecer_endereco_portal
        return jsonify(enriquecer_endereco_portal(data))
    except Exception:
        log.exception("enriquecer endereco")
        return jsonify(success=False, message="Falha ao completar endereço.", updates={}), 500
```

Exigir CSRF no `before_request` do blueprint (DMA/VGR já fazem). Não persistir `updates` nesta rota.

Motor direto (só se precisar dos nomes `municipio`/`estado` sem alias):

```python
from core.utils.endereco_enriquecimento_engine import enriquecer_endereco_unidade
```

---

## JavaScript — como chamar

```html
<script src="/core/static/js/utils/portal_enriquecer_endereco.js?v=1"></script>
```

```js
window.PortalEnriquecerEndereco.bind({
  buttonId: "btnCompletarEndereco",
  statusId: "endereco-enriquecer-status",
  endpoint: "/dma/api/enriquecer-endereco",
  fields: {
    endereco: "endereco",
    numero: "numero",          // opcional
    bairro: "bairro",
    cidade: "cidade",
    municipio: "cidade",       // mesmo input se o form usa cidade
    uf: "uf",
    estado: "uf",
    cep: "cep",
    latitude: "latitude",
    longitude: "longitude",
  },
  // onMessage: function (msg, ok) { ... }  // opcional; senão VgrDt.toast
});
```

Comportamento:

- POST JSON + `X-CSRF-Token` + `X-Requested-With`.
- Sem endereço **e** sem CEP → aviso, não chama API.
- Aplica `updates` via `value` + eventos `input`/`change`.
- Status em `textContent` (sem `innerHTML` com texto da API).

---

## Fontes externas (motor)

Ordem típica:

1. Número extraído do logradouro (`Rua X, 100`).
2. CEP: ViaCEP → OpenCEP → BrasilAPI.
3. Geocode: Nominatim search / structured / reverse.

User-Agent: `PortalImplantacao/1.0 (endereco-enriquecimento; contato TI Vivo)`.

Chamadas HTTP saem do **servidor** (não do browser), com timeout. Falha de API vira aviso/`partial`, não 500, salvo exceção não tratada na fachada.

---

## Como testar

Automatizado (sem HTTP externo — motor mockado na fachada):

```powershell
.\.venv_portal_pessoal\Scripts\python.exe -m pytest `
  core/tests/test_endereco_enriquecimento.py -q
```

Confere: alias `cidade`/`uf`, truncamento de 500 caracteres, motor no pacote `core` (sem `prodesp.credentials`).

**Manual DMA:** blueprints → Completar endereço com logradouro+cidade → bairro/CEP/lat long sugeridos; salvar blueprint à parte.

**Manual VGR:** unidades → novo/editar → Completar endereço → campos preenchidos no modal; gravar unidade só no Salvar.

**Segurança:** usuário sem login → redirect; POST sem CSRF → rejeitado pelo `before_request` do módulo.

---

## O que não fazer

- Não apontar DMA/VGR para `prodesp.prodesp.endereco_enriquecimento`.
- Não alterar o motor da Prodesp “para ficar igual” sem pedido — cópias independentes de propósito.
- Não gravar no banco dentro de `enriquecer_endereco_portal`.
- Não usar `innerHTML` com `data.message` da API.
