# Performance e materialização — PRODESP

Flags e DDL do programa `feature/performance-v1` que afetam o hot path PRODESP.
O histórico medido e o radar do programa ficam em [`docs/auditoria/fase2/`](../../docs/auditoria/fase2/README.md) — **não duplicar change log aqui**.

## Ritual homolog (PRODESP)

1. Aplicar SQL: `018_substatus_desde_atendimentos.sql` → `019_atendimento_tempo_snapshot.sql` (`docs/auditoria/ops/apply_ddl.py`)
2. `PRODESP_SUBSTATUS_DESDE_WRITE=true` + `PRODESP_TEMPO_SNAPSHOT_WRITE=true` → restart → smoke create/update
3. `PRODESP_SUBSTATUS_DESDE_READ=true` + `PRODESP_TEMPO_SNAPSHOT_READ=true`
4. Rollback leitura: `*_READ=0` (colunas/tabela podem permanecer)

## Módulos código

| Módulo | Papel |
|--------|--------|
| `substatus_materializado.py` | Dual-write `substatus_desde_atendimentos`; READ sem CTE |
| `tempo_snapshot.py` | UPSERT `atendimento_tempo_snapshot`; JOIN snapshot vs view |
| `dashboard_select.py` | Whitelist colunas dashboard / atendimento by id (sem `logs` no path leve) |
| `entity_select.py` | Whitelist unidades / equipamentos / links (P3) |
| `atendimentos_list_query.py` | Base lista; path READ usa coluna/snapshot |
| `cache_backend.py` | Backend memória (default); Redis só se `PRODESP_REDIS_URL` |

## Redis — decisão (2026-07-15)

Com `run.py` em Waitress **um processo** + `WAITRESS_THREADS`, o cache PRODESP já é compartilhado entre requisições (mesma memória). **Não** instalar Redis/Memurai neste cenário.

- Manter `PRODESP_REDIS_URL` **comentado** no `.env`
- Código opt-in permanece (revisitar só se houver **multi-processo** ou várias instâncias atrás do mesmo VIP)
- Doc/históricos de programa: item fechado como N/A — ver painel fase2 item 9

## Env (defaults OFF em código; homolog costuma ON)

Ver bloco em `.env.example`:

- `PRODESP_SUBSTATUS_DESDE_WRITE` / `READ`
- `PRODESP_TEMPO_SNAPSHOT_WRITE` / `READ`
- `PRODESP_REDIS_URL` (deixar vazio / comentado no cenário Waitress atual)
- TTLs: `PRODESP_DASHBOARD_CACHE_TTL_SEC`, lista, etc.

## Testes

```powershell
.\.venv_portal_pessoal\Scripts\python.exe -m unittest prodesp.prodesp.tests.test_sprint4_substatus_materializado prodesp.prodesp.tests.test_sprint5_tempo_snapshot prodesp.prodesp.tests.test_entity_select prodesp.prodesp.tests.test_sprint7_p1_residual -v
```

Mapa completo: [`../prodesp/tests/README.md`](../prodesp/tests/README.md).

