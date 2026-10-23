# Testes — `prodesp.prodesp`

Pacote de testes unitários da lógica PRODESP (regras, cache, lista, sprints de performance).

Testes **colocados** em `blueprint/`, `caderno/` e `gestao/` permanecem junto ao domínio.

## Pré-requisito

Raiz do repo + venv:

```powershell
.\.venv_portal_pessoal\Scripts\python.exe -m unittest discover -s prodesp/prodesp/tests -v
```

Ou módulo explícito:

```powershell
.\.venv_portal_pessoal\Scripts\python.exe -m unittest prodesp.prodesp.tests.test_entity_select -v
.\.venv_portal_pessoal\Scripts\python.exe -m pytest prodesp/prodesp/tests/ -q
```

## Mapa (raiz `tests/`)

| Arquivo | Escopo |
|---------|--------|
| `test_link_uniqueness_rules.py` | Unicidade WAN/GW/VGR/loopbacks |
| `test_conclusao_*_rules.py` | Conclusão equipamentos / links |
| `test_field_limits_scenarios.py` | Limites de campo Blueprint |
| `test_ticket_noc_validation.py` | Ticket NOC |
| `test_substatus_observacao_matrix.py` | Matriz obs × substatus |
| `test_agendamento_csv_*` | Validação / import CSV agenda |
| `test_admin_atendimento_ops.py` | Ops admin atendimento |
| `test_data_revision.py` | Contador data_revision |
| `test_dashboard_cache.py` / `test_atendimentos_list_cache.py` | Caches em memória |
| `test_atendimentos_list_query.py` / `test_tempo_atendimento_list.py` | SQL lista / tempos |
| `test_entity_select.py` | P3 whitelist U/E/L |
| `test_sprint1_performance.py` … `test_sprint7_*` | Sprints performance (timing, cache Login, supervisão, materialização, residual) |
| `test_security_helpers.py` | Helpers segurança (se presente) |

## Colocados (fora desta pasta)

```powershell
.\.venv_portal_pessoal\Scripts\python.exe -m pytest prodesp/prodesp/blueprint/ -q
.\.venv_portal_pessoal\Scripts\python.exe -m unittest prodesp.prodesp.blueprint.test_blueprint_detran -v
.\.venv_portal_pessoal\Scripts\python.exe -m unittest prodesp.prodesp.blueprint.test_redundante_critico_rules -v
.\.venv_portal_pessoal\Scripts\python.exe -m pytest prodesp/prodesp/caderno/ -q
.\.venv_portal_pessoal\Scripts\python.exe -m pytest prodesp/prodesp/gestao/ -q
```

| Arquivo (blueprint/) | Escopo |
|----------------------|--------|
| `test_blueprint_detran.py` | Device BP (DETRAN/TJSP/…), sufixo LAN count, rede/DHCP |
| `test_redundante_critico_rules.py` | RC ±3 |
| `test_blueprint_routes.py` | Rotas (quando executável no ambiente) |

## Performance (programa portal)

Flags, DDL 018/019, baselines e smokes homolog: [`docs/auditoria/fase2/`](../../../../docs/auditoria/fase2/README.md) (não duplicar aqui o change log).
