# Páginas e fluxos — PRODESP

## Mapa página → JS → APIs

| Página | URL | JS principal | Persistência |
|--------|-----|--------------|--------------|
| Atendimentos | `/prodesp/atendimentos` | `script_atendimentos_prodesp.js`, `prodesp_live_field_validation.js`, `prodesp_blueprint_confirm.js` | create/update, links-update, equipamentos, observações, gerar Blueprint API |
| Dashboard | `/prodesp/dashboard_atendimentos` | Idem + `script_gestao_atendimentos_prodesp.js` | Mesmos endpoints de atendimento |
| Criar Blueprint | `/prodesp/criar_blueprint` | `prodesp_live_field_validation.js`, `prodesp_blueprint_confirm.js` | preview API + `gerar_blueprint_prodesp` (POST form) |
| Admin equipamentos | `/prodesp/admin/equipamentos` | `script_admin_equipamentos_prodesp.js`, `script_admin_inventory_common.js` | `/api/admin/equipamentos*` |
| Admin links | `/prodesp/admin/links` | `script_admin_links_prodesp.js`, `script_admin_inventory_common.js` | `/api/admin/links*` |
| Admin Secretarias Blueprint | `/prodesp/admin/blueprint_secretarias` | `script_admin_blueprint_secretarias_prodesp.js` | `/api/admin/blueprint_secretarias*` |
| CSV Manager | `/prodesp/csv_manager` | `painel_csv_prodesp.js` | `/api/csv/*` — ver [`csv-agendamento-e-massa.md`](csv-agendamento-e-massa.md) |
| Dados em massa | `/prodesp/dados_em_massa_import` | `script_dados_em_massa_csv_prodesp.js` | `/api/dadosemmassa_csv/*` — ver [`csv-agendamento-e-massa.md`](csv-agendamento-e-massa.md) |

## Criação de atendimento

1. Analista informa ID VGR → `GET /prodesp/atendimentos/verificar_id_vgr/<id>` / `GET /unidades/<id_vgr>`.
2. Status **Em Atendimento** dispara `POST /prodesp/atendimentos/create` (unidade + opcionalmente links/equipamentos/obs).
3. Links adicionais: `POST /prodesp/links-update` (com pré-check `POST /prodesp/api/check-uniqueness`).
4. Autosave / salvar: `POST /prodesp/atendimentos/update` (loopbacks passam por unicidade no servidor).

**UI create:** modal `create*` nos partials; validação live VIVO/RC/IPs; **obrigatórios de link** (Tipo, Operadora, Designador, Velocidade + campos por tipo); toast + highlight em duplicidade.

## Edição de atendimento

1. Abre modal edit com `GET /prodesp/atendimentos/<id>`.
2. Permissão: `_prodesp_validar_edicao_atendimento` (analista dono / admin / AG-GP conforme substatus).
3. Campos unidade/atendimento → `POST /prodesp/atendimentos/update`.
4. Links: add / inline edit / delete → `POST /prodesp/links-update` (mesmos obrigatórios do create).
5. Mesmas regras de unicidade e VIVO que no create.

**UI edit:** disponível em **Atendimentos** e **Dashboard** (mesmo JS).

**Falha ao salvar (conclusão / validação):**
- Servidor responde 400 e faz rollback.
- UI restaura Status/Substatus ao último valor persistido (`prodespRevertStatusSubstatusAposFalhaUpdate`) — evita ficar em «Concluído» indevidamente.
- Toast mostra a mensagem de negócio; `console.warn`/`console.error` de auto-save **não** repetem erros esperados (`prodespLogUnexpectedSaveFailure`). A linha vermelha `400 (BAD REQUEST)` na aba Network do browser é normal e não é silenciável via JS.

## Geração de Blueprint

Doc detalhada (Device BP, máscaras, TJSP, manutenção): [`blueprint-csv.md`](blueprint-csv.md).

### Criar Blueprint (`/criar_blueprint`)

1. Busca unidade por ID VGR.
2. Formulário edita MPLS + STATIC + loopbacks + equipamento + LAN SEC/TER/QUA (cascata UI).
3. Submit interceptado: `ProdespBlueprintConfirm.previewThenConfirm` → modal (hostname, IPs/máscaras LAN, Redes, gateways RO, Device BP + motivo).
4. Confirma → overrides voltam ao form → `POST /prodesp/gerar_blueprint_prodesp`.
5. Servidor: limites, `validar_dados_blueprint`, serial duplicado, unicidade, grava unidade/links, gera CSV.

### Atendimentos / Dashboard

1. Botão Gerar Blueprint no modal → `generateWithConfirm(idVgr)`.
2. `POST /api/gerar_blueprint_prodesp/<id_vgr>` sem `confirm` → prévia; com `confirm` + `overrides` → persiste alterações + CSV.
3. Prévia isolada: `GET|POST /api/preview_blueprint_prodesp/<id_vgr>`.

**Highlight:** campos duplicados vermelhos em tempo real; banner “Corrija antes de gerar” no submit do form.

**Partials:** `prodesp_blueprint_confirm_modal.html` (3 páginas); `prodesp_lan_extra_unidades.html` (cascade SEC→TER→QUA).

## Admin inventário e catálogo Blueprint

Páginas só `admin_user == 1` (menu ADMIN):

- **Equipamentos / links** — listagem slim ≠ detalhe; contexto lazy; histórico **por campo** — ver [`admin-ops.md`](admin-ops.md).
- **Secretarias Blueprint** — acrônimo → Device BP / layout / rede LAN / DHCP (sem deploy de código se migration **021** aplicada) — ver [`blueprint-csv.md`](blueprint-csv.md).

## Fluxos auxiliares

| Fluxo | Entrada | Saída |
|-------|---------|--------|
| Caderno de teste | Toolbar no atendimento | APIs `/api/atendimentos/<id>/caderno/*` — ver [`caderno-e-certificados.md`](caderno-e-certificados.md) |
| Certificados | Toolbar (admin) / auto na conclusão | `.../certificados/exportar` — ver [`caderno-e-certificados.md`](caderno-e-certificados.md) |
| Quebra em massa | Dashboard/gestão | `/api/quebra_massa` |
| Relatório gestão | Dashboard | `/download_report` + schedulers e-mail |

## O que permanece igual entre create e edit

- Regras VIVO / Redundante Crítico / STATIC 201.60–201.61
- Campos obrigatórios de link (`validate_link_required_fields`) — ver [`regras-de-negocio.md`](regras-de-negocio.md) §7
- Unicidade WAN, Gateway, ID VGR (por operadora), Designador (por operadora), Loopbacks
- Limites de tamanho (`db_field_limits`)
- Normalização de payload no servidor (`normalize_link_api_payload`)
