# APIs e segurança — PRODESP

Prefixo: `/prodesp`. Blueprint Flask com `@login_required` nas rotas sensíveis e checagem de projeto.

## Grupos de API

### Atendimento / unidade

| Método | Rota | Função |
|--------|------|--------|
| POST | `/atendimentos/create` | Cria atendimento (+ unidade/links opcionais) |
| POST | `/atendimentos/update` | Atualiza atendimento/unidade (loopbacks com unicidade) |
| GET | `/atendimentos/<id>` | Detalhe |
| POST | `/links-update` | Cria/atualiza/exclui links |
| POST | `/equipamentos-update` | Equipamentos |
| POST | `/observacoes-update` | Observações do atendimento |
| POST | `/api/check-uniqueness` | Pré-validação (não muta dados) |
| GET | `/api/atendimentos_list` | DataTables |
| GET | `/api/data_revision` | Revisão para sync de UI |

### Blueprint

| Método | Rota | Função |
|--------|------|--------|
| GET | `/criar_blueprint` | Página |
| POST | `/buscar_unidade_blueprint` | Busca por ID VGR |
| POST | `/gerar_blueprint_prodesp` | Salva + gera CSV (após modal no browser) |
| GET/POST | `/api/preview_blueprint_prodesp/<id_vgr>` | Prévia do modal (hostname, LANs, máscaras, Device BP); body opcional `overrides` |
| POST | `/api/gerar_blueprint_prodesp/<id_vgr>` | Sem `confirm=true` → `{ needs_confirm, confirm }`; com confirm + overrides → persiste + CSV |
| GET | `/download/blueprint/<filename>` | Download |

Overrides típicos: `hostname`, `ip_lan_01`, `mv_ip_lan_*`, `mv_rede_lan_*`, `mask_lan` / `mask_lan_sec` / ….  
Doc: [`blueprint-csv.md`](blueprint-csv.md).

### Dashboard / gestão

| Método | Rota | Função |
|--------|------|--------|
| GET | `/dashboard_atendimentos` | Página |
| GET | `/api/dashboard_data`, `/api/dashboard_kpis` | Dados/KPIs |
| GET | `/download_report` | Relatório |

### Admin

Rotas `/api/admin/...` — auditoria, status_log, histórico, CRUD forçado de obs/equip/links, delete atendimento. Exigem perfil admin.

Inventário global (páginas HTML + API, só `admin_user == 1`):

| Método | Rota | Função |
|--------|------|--------|
| GET | `/admin/equipamentos` | Página DataTables (PortalDt) + KPIs |
| GET | `/admin/links` | Página DataTables (PortalDt) + KPIs |
| GET | `/api/admin/unidades/search?q=` | Typeahead unidades (admin) |
| GET | `/api/admin/unidades/contexto?id_vgr=` | Preview unidade + atendimentos + ativos (criação) |
| GET | `/api/admin/ultimo_atendimento_map?ids=` | Enrich status/analista da página visível (máx. 100 ids; admin). Listagens client não fazem mais batch global. |
| GET/POST | `/api/admin/equipamentos` | Lista client **slim** (colunas/KPIs da grade; sem mac/licença/descrição). Detalhe + campos de formulário = `GET /equipamentos/<id>`. Contexto/ativos = `.../contexto` (lazy). |
| GET | `/api/admin/equipamentos/<id>/contexto` | Unidade + atendimentos (3 analistas) + equipamentos/links relacionados na unidade |
| GET/PUT/DELETE | `/api/admin/equipamentos/<id>` | Detalhe / editar / excluir |
| POST | `/api/admin/equipamentos/<id>/transferir` | Move para outra unidade (`id_vgr` ou `id_unidade`). UI envia `expected_id_unidade` → **409** se outro admin já moveu. |
| POST | `/api/admin/equipamentos/<id>/desassociar` | FK unidade null (`expected_id_unidade` opcional → 409 se divergir) |
| GET/POST | `/api/admin/links` | Lista client **slim** (sem PPPoE/decrypt). Decrypt PPPoE só no `GET /links/<id>` (modal). Status/analista = enrich da página. KPI «ID VGR fora» = não numérico puro |
| GET | `/api/admin/links/<id>/contexto` | Unidade + atendimentos + ativos relacionados (mesmo pacote) |
| GET/PUT/DELETE | `/api/admin/links/<id>` | Detalhe / editar / excluir |
| POST | `/api/admin/links/<id>/transferir` | Transferência (`expected_id_unidade` → 409 se conflitar) |
| POST | `/api/admin/links/<id>/desassociar` | FK unidade null (`expected_id_unidade` → 409 se conflitar) |

Catálogo **Secretarias Blueprint** (só `admin_user == 1`; migration `021`):

| Método | Rota | Função |
|--------|------|--------|
| GET | `/admin/blueprint_secretarias` | Página DataTables (PortalDt) + CRUD modal |
| GET/POST | `/api/admin/blueprint_secretarias` | Lista (client) / cria secretaria; **503** se tabela ausente |
| GET/PUT/DELETE | `/api/admin/blueprint_secretarias/<id>` | Detalhe / edita / soft-inativa (`hard: false`) ou hard-delete (`hard: true`) |

CRUD grava em `prodesp_blueprint_secretaria` (+ alias) e **invalida cache** de processo do catálogo. Sem `admin_user` → **403**. Erros via `_prodesp_json_error` (sem stack/SQL ao cliente). Doc: [`admin-ops.md`](admin-ops.md), [`blueprint-csv.md`](blueprint-csv.md).

Menu **ADMIN** no sidebar (separado de GESTÃO). Contrato UI inventário: **listagem ≠ detalhe** — DataTables só colunas visíveis; formulário e decrypt sob demanda por id; aba Contexto lazy.

**Histórico inventário / modal ativos:** create/update/delete/transfer gravam **uma linha por coluna** e o `UPDATE` é **parcial** (`admin_inventory.apply_partial_update`). Diff vazio → sem SQL. Senha PPPoE mascarada.

Doc ops: [`admin-ops.md`](admin-ops.md). Inventário + secretarias Blueprint + auditoria atendimento.

### Caderno / certificados

`/api/atendimentos/<id>/caderno/*`, `/certificados/exportar` — ownership do atendimento + login.

### Enriquecimento de endereço

`POST /api/enriquecer-endereco` — sugestão de CEP/geo (não grava DB). Doc: [`enriquecimento-endereco.md`](enriquecimento-endereco.md).

## Controles de segurança (checklist do módulo)

| Risco | Mitigação |
|-------|-----------|
| Acesso anônimo | `@login_required` |
| Projeto errado | `_prodesp_enforce_projeto_acesso` |
| IDOR atendimento | `_prodesp_validar_edicao_atendimento` / checagem de ownership |
| Injection SQL | Queries parametrizadas (`%s`); colunas dinâmicas com whitelist |
| XSS | Preferir `textContent` em banners/toasts; evitar `innerHTML` com dados de API |
| Secrets | Sem senhas no Git; crypto em `sensitive_fields_crypto` |
| Erros | APIs não devolvem stack/SQL ao cliente (`_prodesp_json_error`) |
| Upload/download | Path controlado (`safe_join` / pastas do módulo) |
| Unicidade | Sempre revalidada no servidor (JS é só UX) |
| Campos obrigatórios de link | Atendimento: `validate_link_required_fields`. Blueprint: `validar_dados_blueprint` (Operadora/Designador + WAN/GW/Máscara/Velocidade; ID VGR se VIVO). Detalhe: [`regras-de-negocio.md`](regras-de-negocio.md) §7 |
| Conclusão × coleta FGT | Equipamento + links; 400 com rollback. UI reverte Status/Substatus; toast sem spam de console em erro de negócio esperado |

## Contratos que não devem quebrar

- Payloads DataTables (`/api/atendimentos_list`)
- Shape JSON de detalhe do atendimento (campos consumidos pelo JS)
- Nomes de colunas `*_links` / `*_unidades` usados no Blueprint e Power BI / views SQL
- Flag `redundante_critico_links` (0/1) e WAN efetivo

## Testes de regressão sugeridos

1. Create atendimento → add link VIVO → save OK.
2. Edit link com WAN duplicado de outro link → bloqueio + highlight.
3. Blueprint com MPLS/STATIC iguais em WAN → vermelho em tempo real + banner no gerar.
4. Gerar Blueprint: modal confirma → Device BP reflete contagem LAN; máscara ≠ CIDR → linha em histórico da unidade.
5. Regenerar Blueprint API sem confirm → `needs_confirm`; com dados inconsistentes no banco → 400 com `errors`.
6. Usuário sem permissão de edição → 403/mensagem, sem mutação.
7. Conclusão com serial divergente da coleta → 400 + toast; Status/Substatus voltam ao valor anterior (sem `console.error` de negócio).
8. Admin inventário: criar/transferir equipamento → histórico por campo (`serial_equipamentos`, `id_unidades_equipamentos`, …); não-admin → 403.
9. Admin Secretarias Blueprint: não-admin → 403; admin cria/edita acrônimo → CSV usa template novo; inativo → fallback `BP_OES` + layout REDE_LAN (ver testes HTTP/flow).
