# Débitos conhecidos — PRODESP

Itens conhecidos que ainda geram risco operacional ou de segurança. Atualizar este arquivo ao corrigir.

## Templates / rotas legadas

| Item | Evidência | Impacto | Direção sugerida |
|------|-----------|---------|------------------|
| `supervisao_prodesp.html` ausente | Rota `/prodesp/supervisao` ainda renderiza o template; arquivo não existe; fora do nav | `TemplateNotFound` se a URL for acessada | Remover rota ou restaurar template |
| `prodesp_criar_csv.html` ausente | `/criar_csv`, `/buscar_unidade_csv`, `/gerar_csv_prodesp` ainda referenciam; UI substituída por Blueprint | UI morta; POSTs legados ainda alcançáveis | Remover rotas ou redirecionar para `/criar_blueprint` |

## Permissões

| Item | Evidência | Impacto | Direção sugerida |
|------|-----------|---------|------------------|
| APIs de inserção em massa | Página exige menu gestão; `/api/dadosemmassa_csv/*` só `@login_required` | Qualquer login que conheça a URL pode chamar upsert | Aplicar o mesmo gate `_prodesp_pode_ver_menu_gestao` nas APIs |

Ver [`csv-agendamento-e-massa.md`](csv-agendamento-e-massa.md).

## Schema / KPIs

| Item | Impacto | Direção sugerida |
|------|---------|------------------|
| View `vw_tempo_atendimento_detalhado` sem colunas novas (`tempo_aguarda_gestao`, `tempo_com_suporte`, etc.) | KPIs degradam com fallback | Aplicar SQL/views do pacote `prodesp/sql/` |

## Segurança / hardening

| Item | Impacto | Direção sugerida |
|------|---------|------------------|
| Enriquecimento CEP com `verify=False` | MITM no tráfego de saída para provedores de CEP | Habilitar verificação TLS com CA adequada |
| Admin `fetch` sem CSRF explícito | Depende da política global do portal | Alinhar ao padrão CSRF do monólito |
| Auditoria admin devolve PPPoE em claro | Exposição se dump/compartilhamento indevido | Restringir campos ou mascarar na UI |

Ver [`admin-ops.md`](admin-ops.md) e [`enriquecimento-endereco.md`](enriquecimento-endereco.md).

## Multi-processo / cache

Cache e `data_revision` são **por processo**. Em vários workers, a UI pode divergir por alguns segundos até TTL/bust. Ver [`cache-e-sync.md`](cache-e-sync.md).

O **catálogo de secretarias Blueprint** também é cache de processo (TTL ~60s); escrita no Admin invalida no worker que gravou — outros workers atualizam no TTL.

## Blueprint / confirmação

| Item | Impacto | Direção sugerida |
|------|---------|------------------|
| Máscara sem IP no form `/criar_blueprint` | No POST form, máscara só reescreve CIDR se o IP estiver preenchido; emissão `MV_MASK_*` só-com-Rede é coberta pelo fluxo API (atendimentos/dashboard) | Hidden `_blueprint_mask_*` no form ou unificar geração no confirm API |

## Caderno de teste

| Item | Impacto | Direção sugerida |
|------|---------|------------------|
| Forçar `PRODESP_CADERNO_ENGINE=openpyxl` em produção Windows | Excel pede reparo; drawings/links externos do MULTI-OES podem ser descartados | Manter `auto` / `excel_com`; ver [`caderno-e-certificados.md`](caderno-e-certificados.md) |
| `gerados/` ou work temp sob OneDrive | Lock/publicação lenta ou hang sob carga | `PRODESP_CADERNO_LOCAL_DIR` + `PRODESP_CADERNO_WORK_DIR` em disco local |

## O que não é débito (só lembrar)

- Unicidade e VIVO/RC: regras ativas no servidor + UI.
- Schedulers de e-mail: off por default até env — comportamento esperado.
- Planilhas `.xlsx` locais: não entram em commit de feature.
- Device BP dinâmico / catálogo Secretarias Blueprint / modal confirm: documentados em [`blueprint-csv.md`](blueprint-csv.md); **nova secretaria sem deploy** se migration **021** + Admin.
- Fallback acrônimo sem cadastro ativo: `BP_OES_{modelo}` + layout REDE_LAN (não exige mapa no código).
- Pool Excel COM N=2 + teto duro de job 170s (kill PID) + UI 180s: comportamento esperado documentado em [`caderno-e-certificados.md`](caderno-e-certificados.md).
- Geração de caderno solta a conexão MySQL durante o Excel e reabre só para histórico.