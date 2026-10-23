# Arquitetura e código — PRODESP

## Visão geral

| Camada | Caminho | Papel |
|--------|---------|--------|
| App Flask | `prodesp/app.py` | Blueprint `prodesp_bp` (`url_prefix=/prodesp`), atendimento/dashboard/admin/CSV/caderno/inventário |
| Rotas Blueprint CSV | `prodesp/prodesp/blueprint/prodesp_routes.py` | Criar/buscar/preview/gerar Blueprint |
| Regras de negócio | `prodesp/prodesp/` | Pacote Python puro + serviços |
| UI | `prodesp/templates/`, `prodesp/static/` | Jinja + JS/CSS |
| Schema | `prodesp/sql/` | Migrations numeradas e views |
| Docs | `prodesp/docs/` | Índice em [`README.md`](README.md) |
| Config | `prodesp/config.ini`, `config_paths.py` | Caminhos de rede (caderno/certificados) |
| Credenciais | `prodesp/credentials/` | **Fora do Git / não documentar segredos** |

Gate de acesso: `_prodesp_enforce_projeto_acesso` no blueprint.

## Árvore do pacote `prodesp/prodesp/`

```
prodesp/prodesp/
├── blueprint/                 # CSV SD-WAN, VIVO, RC, velocidade, rotas Flask
│   ├── prodesp_routes.py
│   ├── prodesp_csv_generator.py   # Device BP, confirm overrides, LAN extra
│   ├── blueprint_catalog.py       # resolve_rule / cache / seed embutido (testes)
│   ├── blueprint_secretaria_repo.py  # CRUD + loader DB (sql/021)
│   ├── prodesp_equipment.py
│   ├── link_vivo_rules.py
│   ├── link_velocity_rules.py
│   ├── redundante_critico_rules.py
│   ├── test_blueprint_detran.py / test_blueprint_catalog.py / …
│   └── agendamento_csv_notifier.py
├── caderno/                   # Caderno .xlsm, SSH FortiGate, certificados
├── gestao/                    # Relatórios e-mail, KPIs, schedulers
├── admin_inventory.py         # Serviços inventário admin (eq/links)
├── admin_atendimento_ops.py   # Exclusão / agenda admin
├── link_uniqueness_rules.py
├── db_field_limits.py
├── atendimento_business_rules.py
├── historico.py               # registrar_log
├── sensitive_fields_crypto.py
├── dashboard_cache.py
├── atendimentos_list_cache.py / atendimentos_list_query.py
├── cache_backend.py
├── agendamento_csv_*.py
└── ticket_noc_validation.py
```

**Imports corretos:** `from prodesp.prodesp.blueprint...` ou relativos em `app.py` (`from .prodesp...`).  
Não usar caminhos legados na raiz plana do pacote.

## Front-end

### Templates principais

| Template | Uso |
|----------|-----|
| `atendimentos_prodesp.html` | Lista + modais create/edit + confirm Blueprint |
| `dashboard_atendimentos_prodesp.html` | Gestão + mesmos modais |
| `prodesp_criar_blueprint.html` | Gerar Blueprint (form) |
| `admin_equipamentos_prodesp.html` | Inventário admin equipamentos |
| `admin_links_prodesp.html` | Inventário admin links |
| `admin_blueprint_secretarias_prodesp.html` | Catálogo acrônimo → Device BP (admin) |
| `csv_prodesp.html` | Manager CSV |
| `prodesp_dados_em_massa_csv.html` | Import em massa |
| `partials/prodesp_atendimento_modals.html` | Modais compartilhados (hints de acrônimo do catálogo) |
| `partials/prodesp_blueprint_confirm_modal.html` | Modal confirmação gerar CSV |
| `partials/prodesp_lan_extra_unidades.html` | Campos LAN SEC/TER/QUA (+ cascade) |

Base: `base_prodesp.html` (jQuery, DataTables, Bootstrap 5, sidebar ADMIN incl. Secretarias Blueprint, perfil).

### JavaScript relevante

| Arquivo | Função |
|---------|--------|
| `script_atendimentos_prodesp.js` | CRUD atendimento, links, autosave, unicidade UI, chama confirm Blueprint |
| `prodesp_blueprint_confirm.js` | Modal confirm, overrides, cascade LAN SEC→TER→QUA |
| `prodesp_live_field_validation.js` | Validação visual (VIVO, RC, loopbacks, unicidade Blueprint) |
| `prodesp_field_limits.js` | maxlength / feedback de tamanho |
| `script_gestao_atendimentos_prodesp.js` | Dashboard/gestão |
| `script_admin_equipamentos_prodesp.js` / `script_admin_links_prodesp.js` | Inventário admin |
| `script_admin_blueprint_secretarias_prodesp.js` | CRUD secretarias Blueprint |
| `script_admin_inventory_common.js` | Helpers compartilhados inventário / admin-inv |
| `prodesp_caderno_teste.js` / `prodesp_certificado_export.js` | Caderno e certificados |
| `prodesp_substatus_flow.js` | Fluxo de substatus |
| `painel_csv_prodesp.js` | CSV manager |

Atendimentos e dashboard carregam o **mesmo** `script_atendimentos_prodesp.js` + modais + `prodesp_blueprint_confirm.js` → create/edit/gerar Blueprint equivalentes nas duas páginas.

## Bibliotecas / stack

| Área | Tecnologia |
|------|------------|
| Backend | Flask, MySQL (connector), Fernet (campos sensíveis) |
| Frontend | Bootstrap 5, jQuery, DataTables (PortalDt), Select2, IMask, Chart.js (dashboard) |
| Caderno | Excel/COM + SSH FortiGate (módulos `fgt_*`) |
| Python | venv `.venv_portal_pessoal` (obrigatório no projeto) |

## Pontos de extensão seguros

1. Novas regras de link → preferir módulo em `prodesp/prodesp/` ou `blueprint/` + chamada em `links-update` / Blueprint.
2. Novas colunas → `db_field_limits.py` + migration em `sql/` + UI.
3. Validação UI → `prodesp_live_field_validation.js` **e** espelho no servidor (nunca só JS).
4. Novo acrônimo / Device BP / regra rede ou DHCP → **Admin → Secretarias Blueprint** (sem edit de código se 021 aplicada); checklist e seed em [`blueprint-csv.md`](blueprint-csv.md).
5. Mutação admin inventário → `registrar_field_changes` (1 linha por coluna) + `_prodesp_mutations_cache_bust()`.

## Manutenção operacional

| Situação | Ação |
|----------|------|
| Mudou Python (CSV/rotas/catálogo) | Restart Waitress / `run.py` (sem auto-reload); mutação admin de secretaria invalida cache no processo |
| Mudou JS confirm | Bump `?v=bp-confirm-*` nos 3 templates + hard refresh |
| Mudou JS Admin Secretarias | Bump `?v=admin-bp-sec-*` + hard refresh |
| Inventário lento | Ver ColumnControl / índices `020_*`; não reativar searchList em colunas de alta cardinalidade sem medir |
| Docs desatualizados | Atualizar `prodesp/docs/` no mesmo PR da feature |
