# SQL e dados — PRODESP

## Migrations (`prodesp/sql/`)

Aplicar em ordem numérica no ambiente alvo. Checklist operacional: [`checklist-deploy.md`](checklist-deploy.md).

| Arquivo | Objetivo |
|---------|----------|
| `008_planejada_unidades.sql` | Colunas de planejamento em `unidades` |
| `009_sensitive_fields_varchar255.sql` | Amplia colunas para tokens Fernet |
| `010_hostname_unidades_varchar80.sql` | Hostname |
| `011_dashboard_perf_indexes.sql` | Índices dashboard |
| `012_observacoes_historico_indexes.sql` | Índices observações/histórico |
| `013_fix_atendimentos_status_log_triggers.sql` | Triggers/UNIQUE status_log |
| `014_atendimentos_list_perf.sql` | Índices lista de atendimentos |
| `015_logs_atendimentos_mediumtext.sql` | Logs → MEDIUMTEXT |
| `016_mv_opcionais_unidades.sql` | Colunas opcionais MV_* |
| `017_lan_sec_wifi_guest_unidades.sql` | Rename `ip_lan_02`→`mv_ip_lan_sec` (VARCHAR 255, legado) + LAN TER/QUA + WiFi Guest |
| `017_redundante_critico_links.sql` | Flag `redundante_critico_links` em `links` |
| `018_substatus_desde_atendimentos.sql` | P0-01 coluna `substatus_desde` + backfill |
| `019_atendimento_tempo_snapshot.sql` | P0-02 tabela snapshot tempos + backfill |
| `020_admin_inventory_ultimo_atendimento_idx.sql` | Índice `(id_unidades_atendimentos, id_atendimentos)` para enrich inventário admin |
| `021_blueprint_secretaria_catalog.sql` | Tabelas `prodesp_blueprint_secretaria` + `prodesp_blueprint_secretaria_alias` (Device Blueprint por acrônimo) + seed |

Flags / ritual WRITE→READ: [`performance-flags.md`](performance-flags.md). Programa: `docs/auditoria/fase2/`.

### Views

| Arquivo | Uso |
|---------|-----|
| `vw_agendamentos_e_atendimentos_ativos.sql` | Agenda/atendimentos ativos |
| `vw_tempo_atendimento_detalhado.sql` | Tempos por etapa |

## Migração de dados Python

`prodesp/migrations/migrate_encrypt_sensitive_fields.py` — criptografa linhas existentes (requer `009` antes).

## Planilhas (`prodesp/banco_dados/`)

Fontes operacionais (SDWAN, Updates, modelos). **Não versionar alterações locais de `.xlsx` em commits de feature** salvo pedido explícito de dados.

## Artefatos estáticos gerados

| Recurso | Caminho |
|---------|---------|
| CSV Blueprint | `prodesp/static/csv_prodesp/` |
| Modelo caderno | `prodesp/static/caderno_teste/modelo/` |
| Cadernos gerados (portal) | `prodesp/static/caderno_teste/gerados/` |
| Rede / OneDrive | `config_paths.py` + `config.ini` (`caderno_teste_rede_base`, etc.) |

## Tabelas centrais (referência)

| Tabela | Papel |
|--------|-------|
| `unidades` | Site (ID VGR, endereço, loopbacks, IPs LAN, LAN SEC/TER/QUA, WiFi Guest, MV_*) |
| `atendimentos` | Ciclo de implantação (status, substatus, analistas, logs) |
| `links` | MPLS/STATIC (WAN, GW, máscara, designador, id_vgr, operadora, RC) |
| `equipamentos` | Serial/modelo/versão FortiGate |
| `observacoes` | Notas ligadas a atendimento/unidade |
| `status_log` / histórico | Auditoria de mudanças |
| `prodesp_blueprint_secretaria` | Catálogo acrônimo → template Device BP / layout CSV / rede LAN / DHCP (Admin + gerador) |
| `prodesp_blueprint_secretaria_alias` | Aliases de acrônimo para o mesmo cadastro (ex. PROSANGUE → PRO-SANGUE) |

Unicidade de IPs/designadores **não** depende só de UNIQUE no MySQL: a regra de negócio está em `link_uniqueness_rules.py` (permite mensagens claras ao analista).

Catálogo Blueprint (resolução em runtime + CRUD): `blueprint_catalog.py` / `blueprint_secretaria_repo.py`. Doc: [`blueprint-csv.md`](blueprint-csv.md).
