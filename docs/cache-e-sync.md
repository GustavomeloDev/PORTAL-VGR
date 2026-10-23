# Cache e sync de UI — PRODESP

Tudo é **cache em memória do processo** por padrão. No deploy atual (`run.py` → Waitress **1 processo** + threads), isso é suficiente: threads compartilham o mesmo dict/geração.

**Redis (`PRODESP_REDIS_URL`):** adoção **abortada / N/A** neste cenário (sem Memurai/serviço). O caminho no código fica opt-in para um eventual multi-**processo** ou várias instâncias — ver [`performance-flags.md`](performance-flags.md).

## Camadas

| Módulo | Escopo | TTL default | Env |
|--------|--------|-------------|-----|
| `dashboard_cache.py` | Dashboard por `(start_date, end_date)` | 25s | `PRODESP_DASHBOARD_CACHE_TTL_SEC` ou `PRODESP_DATA_CACHE_TTL_SEC` |
| `atendimentos_list_cache.py` | Lista (raw + JSON processado por usuário) + resumo | 60s | `PRODESP_ATENDIMENTOS_LIST_CACHE_TTL_SEC` ou TTL unificado |
| `data_revision.py` | Contador global `_REVISION` (persistido em arquivo temp; sobrevive ao reloader) | — | Cliente: `PRODESP_DT_SYNC_INTERVAL_SEC` (default 90, mín. 15); opcional `PRODESP_DATA_REVISION_FILE` |
| `cache_backend.py` | Backend memória; Redis só se URL setada **e** serviço OK | — | `PRODESP_REDIS_URL` (vazio = memória) |

Além do cache HTTP: hot path pode ler **colunas/snapshot materializados** (`PRODESP_*_READ`) — ver [`performance-flags.md`](performance-flags.md).

TTL `0` desliga aquele cache. `PRODESP_DATA_CACHE_TTL_SEC` unificado sobrescreve os específicos quando definido.

## Invalidação

`_prodesp_mutations_cache_bust()` em `app.py`:

1. `dashboard_cache.bust()`
2. `atendimentos_list_cache.bust()`
3. `data_revision.bump()`

Deve ser chamado após mutações de atendimento / link / unidade / correlatos. **Site sem bust** = tela velha até expirar o TTL.

## Comportamento do cliente

- `prodesp_dt_sync.js`: poll de `/prodesp/api/data_revision`; **ajax.reload só se a revisão mudou** (ou botão Atualizar / force)
- Flag `PRODESP_ATENDIMENTOS_LIST_DELTA` (padrão **off**): se on, a fila usa `GET /api/atendimentos_list_delta` (Fase 2): `updated` (patch ou add), `removed_ids` (remove), `resumo` (KPIs), refresh leve do ColumnControl nas colunas tocadas, `draw(false)`. `fallback_full` / revisão opaca / lote > 100 → full reload
- `bump(atendimento_ids=...)` grava dirty set; bump sem IDs = revisão opaca (delta → fallback)
- Payloads de API podem anexar `data_revision` (`attach_to_payload`)

## Sintomas de UI desatualizada

| Sintoma | Causa provável |
|---------|----------------|
| Outros usuários veem KPIs/linhas antigas por até ~TTL | Cache hit ou mutação sem bust |
| Após bust correto, UI ainda atrasa ~90s | Cliente espera o próximo tick do sync |
| Fila OK e dashboard velho (ou o inverso) | Só um cache invalidado / TTLs diferentes |
| `cache_meta.from_cache: true` com `age_sec` alto | Ainda dentro da janela de TTL |
| Revisão “errada” entre instâncias | Multi-processo sem memória compartilhada |
| Após restart do app | Revisão persiste em arquivo temp (F5 admin inventário não precisa refetch full se nada mudou). Caches de payload em memória esvaziam. |

## Diagnóstico rápido

1. Confirmar se a ação de save chama `_prodesp_mutations_cache_bust`.
2. Temporariamente `PRODESP_DATA_CACHE_TTL_SEC=0` e reproduzir.
3. Usar “Atualizar agora” na página.
4. Em produção multi-worker, esperar divergência breve entre workers até o próximo bust/TTL.
