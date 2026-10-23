# VGR — SQL (`multi_cliente_db`)

Scripts do banco do módulo VGR. **Não** misturar com `vgr_bd` (login).

| Arquivo | Função |
|---------|--------|
| [000_create_database.sql](000_create_database.sql) | `CREATE DATABASE multi_cliente_db` |
| [001_schema_base.sql](001_schema_base.sql) | Inventário, Field, agendamento 1→1 atendimento, histórico |
| [002_atendimento_logs_config.sql](002_atendimento_logs_config.sql) | `atendimentos.logs_configuracao` (P1) — **nao usar em producao nova** |
| [003_links_unidade_sem_equipamento.sql](003_links_unidade_sem_equipamento.sql) | D3: `links.id_equipamento` nullable; LAN+ sem equipamento |
| [004_agendamentos_contratada_planejada.sql](004_agendamentos_contratada_planejada.sql) | CSV Agendamento: `agendamentos.id_contratada_planejada` (FK `contratadas`) + índice `equipamentos (id_vgr, tipo_servico)`. Requer `equipamentos.id_vgr` (DMA 011 ou 010). Rodar uma única vez |
| [010_schema_producao.sql](010_schema_producao.sql) | Schema consolidado para **banco novo**: 000+001+003+DMA 009/011/012/015 **sem** colunas legado (`unidades.id_vgr`, `equipamentos.licenca`, `atendimentos.logs_configuracao`) |

Modelo de referência: [docs/vgr/02-modelo-dados.md](../../docs/vgr/02-modelo-dados.md).

## Aplicar (homolog / local)

```powershell
# Ajuste host/user conforme seu ambiente — senha via prompt ou variável, nunca no Git
mysql -h <host> -u <user> -p < vgr/sql/000_create_database.sql
mysql -h <host> -u <user> -p multi_cliente_db < vgr/sql/001_schema_base.sql
```

Ou no cliente:

```sql
SOURCE vgr/sql/000_create_database.sql;
USE multi_cliente_db;
SOURCE vgr/sql/001_schema_base.sql;
```

## Producao (banco vazio)

```sql
SOURCE vgr/sql/010_schema_producao.sql;
SOURCE vgr/sql/004_agendamentos_contratada_planejada.sql;
SOURCE dma/sql/016_dump_inventario_dma.sql;
```

Nao aplicar `002` (logs no atendimento). O `010` nao inclui o `004`. Dump DMA: ver `dma/sql/README.md`.

## `.env` (exemplo)

```env
VGR_MYSQL_DATABASE=multi_cliente_db
```

Credenciais MySQL compartilhadas do Portal (`HOST`/`USER`/`PASS` ou `MYSQL_*`) — ver `.env.example`.

## Tabelas (resumo)

| Grupo | Tabelas |
|-------|---------|
| Inventário | `clientes`, `unidades`, `equipamentos`, `links`, `licencas`, `coletas_configuracao` |
| Field | `contratadas`, `fields`, `field_emails`, `field_contratadas`, `field_historico` |
| Operação | `agendamentos`, `atendimentos`, `agendamento_fields`, `atendimento_fields` |
| Auditoria | `historico`, `agendamento_status_log`, `atendimento_status_log` |

## Regras no DDL

- `links.id_equipamento` **NOT NULL** (D3)
- `atendimentos.id_agendamento` **UNIQUE** e **NULL** permitido (P3 1→1 + P6 walk-in)
- PII Field: `rg_enc` / `cpf_enc` VARCHAR(255) para Fernet na app
- Status em VARCHAR (labels podem polir sem migration de ENUM)

## Segurança

- Sem secrets neste diretório
- HA (`unidades.ha` → 2× SDWAN no Agendado), Blueprint Fortinet e ACL `VGR` são regras de **aplicação**, não CHECK no MySQL
