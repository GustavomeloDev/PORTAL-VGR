# prodesp.prodesp — lógica de negócio PRODESP

Pacote Python com regras, geração de artefatos e relatórios do módulo PRODESP.  
A aplicação Flask fica em `prodesp/app.py`; o scheduler de gestão é iniciado em `run.py`.

**Documentação completa do módulo:** [`../docs/README.md`](../docs/README.md)  
**Performance / flags P0:** [`../docs/performance-flags.md`](../docs/performance-flags.md)  
**Testes:** [`tests/README.md`](tests/README.md)  
**Programa portal (auditoria):** [`../../docs/auditoria/fase2/README.md`](../../docs/auditoria/fase2/README.md)

## Estrutura

```
prodesp/prodesp/
├── blueprint/          # Blueprint CSV (SD-WAN), equipamentos, rotas Flask e e-mail de agendamento
├── caderno/            # Caderno de teste (.xlsm), coleta SSH FortiGate, carimbo NOC
├── gestao/             # Relatórios executivos, KPIs, observações e scheduler de e-mail
├── tests/              # Testes unitários da raiz (sprints perf + regras compartilhada)
└── (raiz compartilhada)
    ├── entity_select.py / dashboard_select.py     # P3 whitelist SELECT
    ├── substatus_materializado.py / tempo_snapshot.py  # P0 dual-write / READ
    ├── atendimentos_list_query.py / *_cache.py / cache_backend.py
    ├── link_uniqueness_rules.py
    ├── db_field_limits.py
    ├── atendimento_business_rules.py
    ├── historico.py
    ├── sensitive_fields_crypto.py
    └── data_revision.py
```

### Imports

| Área | Exemplo |
|------|---------|
| Blueprint | `from prodesp.prodesp.blueprint.prodesp_csv_generator import gerar_csv_blueprint_prodesp` |
| Caderno | `from prodesp.prodesp.caderno.caderno_teste_service import executar_geracao` |
| Gestão | `from prodesp.prodesp.gestao.gestao_relatorio_email import calcular_kpis_gestao` |
| Compartilhado | `from prodesp.prodesp.db_field_limits import validate_blueprint_form_limits` |
| Testes | `python -m unittest prodesp.prodesp.tests.test_entity_select` |

Dentro de `prodesp/app.py`, use imports relativos ao pacote `prodesp`:  
`from .prodesp.blueprint import prodesp_routes`, `from .prodesp.caderno.caderno_teste_service import ...`.

**Não usar** caminhos legados na raiz de `prodesp/prodesp/` (ex.: `prodesp.prodesp.prodesp_csv_generator`) — os módulos foram movidos para `blueprint/`, `caderno/` ou `gestao/`.

### Regra VIVO (links MPLS / STATIC no Blueprint)

Quando a operadora é **VIVO** (`link_vivo_rules.py` + `prodesp_live_field_validation.js`):

- **MPLS** → máscara `255.255.255.248` (/29)
- **STATIC** (e demais): último octeto do IP WAN **par** → `255.255.255.252` (/30); **ímpar** → `255.255.255.254` (/31)
- **Gateway** = IP WAN − 1 (ex.: WAN `200.159.30.22` → gateway `200.159.30.21`)

Aplicado na UI ao digitar o WAN e no servidor em `_parse_blueprint_link_data`.

**Confirmação / Device BP / catálogo secretarias / LAN:** ver [`docs/blueprint-csv.md`](../docs/blueprint-csv.md).
Admin CRUD: `/prodesp/admin/blueprint_secretarias` — `blueprint_catalog.py` + `blueprint_secretaria_repo.py`.

**Atendimentos e dashboard** (`atendimentos_prodesp.html`, `dashboard_atendimentos_prodesp.html`): os modais edit/create usam `ProdespLiveValidation.initAtendimentoLinkForm()` — mesmas regras de WAN/Gateway, bloco STATIC 201.60/201.61, VIVO e loopbacks. Persistência via `/prodesp/links-update` normaliza VIVO no servidor (`normalize_link_api_payload`).

### Redundante Crítico (MPLS + VIVO)

Ver `redundante_critico_rules.py` e `docs/regras-de-negocio.md`: flag `redundante_critico_links` + WAN efetivo; com RC usa delta ±3 entre WAN e Gateway.

### Unicidade (bloqueio de duplicidade)

Ver `link_uniqueness_rules.py` e `docs/regras-de-negocio.md`: WAN, Gateway, ID VGR/designador por operadora, loopbacks. Pré-check `POST /prodesp/api/check-uniqueness`; highlight em tempo real no Blueprint.

## Testes

Na raiz do repositório, com `.venv_portal_pessoal` ativo — detalhes em [`tests/README.md`](tests/README.md):

```powershell
# Pacote tests/ (raiz compartilhada + sprints)
.venv_portal_pessoal\Scripts\python.exe -m unittest discover -s prodesp/prodesp/tests -v

# Blueprint / caderno / gestão (colocados)
.venv_portal_pessoal\Scripts\python.exe -m pytest prodesp/prodesp/blueprint/ -q
.venv_portal_pessoal\Scripts\python.exe -m unittest prodesp.prodesp.blueprint.test_redundante_critico_rules -v
.venv_portal_pessoal\Scripts\python.exe -m pytest prodesp/prodesp/caderno/ -q
.venv_portal_pessoal\Scripts\python.exe -m pytest prodesp/prodesp/gestao/ -q
```

## Artefatos estáticos

| Recurso | Caminho |
|---------|---------|
| CSV blueprint | `prodesp/static/csv_prodesp/` |
| Template caderno | `prodesp/static/caderno_teste/modelo/` |
| Cadernos gerados (portal) | `prodesp/static/caderno_teste/gerados/` |
| Cadernos rede/OneDrive | `{caderno_teste_rede_base}/{acronimo}/` — ver `prodesp/config_paths.py` e `prodesp/config.ini` |
| UI caderno | `prodesp/static/js/prodesp_caderno_teste.js` |

## APIs relacionadas (app)

- Blueprint: rotas em `prodesp.prodesp.blueprint.prodesp_routes` (preview + gerar com confirm/overrides) — [`docs/blueprint-csv.md`](../docs/blueprint-csv.md)
- Caderno: `POST /prodesp/api/atendimentos/<id>/caderno/coletar-logs`, `.../gerar`, `GET .../carimbo-texto`, `.../download`
- Admin inventário: `/prodesp/api/admin/equipamentos|links` (+ histórico por campo) — [`docs/admin-ops.md`](../docs/admin-ops.md)
- Admin Secretarias Blueprint: `/prodesp/api/admin/blueprint_secretarias` — [`docs/admin-ops.md`](../docs/admin-ops.md) / [`docs/blueprint-csv.md`](../docs/blueprint-csv.md)
