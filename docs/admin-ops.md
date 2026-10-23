# Admin ops — PRODESP

Operações administrativas sob `/prodesp/api/admin/...`.  
**Gate:** `@login_required` + `_prodesp_require_admin_api()` (`admin_user == 1`). Não-admin → `403` «Apenas administradores.»

Módulo de exclusão/agenda: `prodesp/prodesp/admin_atendimento_ops.py`.  
UI: painéis em `script_atendimentos_prodesp.js` / `script_gestao_atendimentos_prodesp.js`.

## Rotas

| Método | Path | Função |
|--------|------|--------|
| GET | `/atendimento/<id>/auditoria` | Pacote: status_log, históricos, obs, equipamentos, links (PPPoE descriptografado) |
| POST | `/atendimento/<id>/status_log` | Insere log de status/substatus (pode ser retroativo) |
| PUT/DELETE | `.../status_log/<log_id>` | Edita/remove linha (deve pertencer ao atendimento) |
| POST | `/atendimento/<id>/historico` | Insere histórico em `atendimentos` |
| PUT/DELETE | `.../historico/<hid>` | Edita/remove; 403 se tabela/id incorretos |
| POST | `/unidade/<id>/historico` | Histórico em `unidades` |
| PUT/DELETE | `.../historico_unidade/<hid>` | Edita/remove histórico da unidade do atendimento |
| PUT/DELETE | `.../observacoes/<obs_id>` | Edita texto/ts, desassocia ou apaga (+ log) |
| PUT/DELETE | `.../equipamentos/<eq_id>` | Atualiza / desassocia / apaga |
| PUT/DELETE | `.../links/<link_id>` | Atualiza (PPPoE criptografado) / desassocia / apaga |
| DELETE | `/atendimento/<id>` | Exclusão em cascata (logs, obs, fora_padrão, histórico, atendimento) |
| DELETE | `/unidade/vgr/<id_vgr>/agendamento` | Limpa data/hora de agendamento; **409** se já existe atendimento na data |

## Comportamento das exclusões

| Op | Detalhe |
|----|---------|
| `admin_excluir_atendimento` | Remove dependências e o atendimento; registra log na unidade |
| `admin_remover_agendamento` | Zera `data/hora_agendamento_unidades` sem apagar a unidade |

Mutações devem chamar `_prodesp_mutations_cache_bust()` (lista/dashboard).

## Inventário global (equipamentos / links)

Páginas: `/prodesp/admin/equipamentos`, `/prodesp/admin/links` (`admin_user == 1`).  
APIs: ver tabela em [`apis-e-seguranca.md`](apis-e-seguranca.md). Serviços: `admin_inventory.py`; rotas em `app.py`.

### KPIs de inventário (fora do padrão × status)

Flags server-side na listagem de links:

| Flag | Regra (vazio ≠ fora) |
|------|----------------------|
| `id_vgr_fora_padrao` | só dígitos **e** comprimento ≥ 7 |
| `designador_fora_padrao` | **somente operadora VIVO**; só dígitos **e** comprimento ≥ 15 |

Cards extras filtram o universo “fora” por `status_ultimo_atendimento`:

- **Concluído / Concluído Parcial** — cobrança de correção  
- **Em Atendimento** — corrigir até o final  
- **Quebra** — atenção (novo atendimento virá)

Equipamentos: mesma visão para **FGT fora**; KPIs **Modelos** e **Versões** (distintos + toast top no topo ~8s).

Layout dos KPIs (padrão Gestão): **Total** destacado à esquerda; demais cards em seções com subtítulo — Links: *Inventário* / *Fora do padrão*; Equipamentos: *Inventário* / *Cobrança / atenção* / *Modelos / Versões*. Faixa colorida à esquerda + ícone à direita.

### Histórico e UPDATE (1 linha / campo + partial SET)

Em create / update / delete / transferir / desassociar o servidor:

1. Calcula o diff (`collect_field_changes`).
2. **Só `UPDATE` colunas que mudaram** (`apply_partial_update`). Se diff vazio → **noop** (sem SQL).
3. Grava histórico via `registrar_field_changes` → `registrar_log` **uma linha por coluna**.

O mesmo padrão parcial + histórico por campo vale para `/equipamentos-update` e `/links-update` do modal de atendimento.

Formato (igual blueprint / `atendimentos/update`):

| Coluna histórico | Conteúdo |
|------------------|----------|
| `tabela_afetada_historico` | `equipamentos` ou `links` |
| `id_registro_afetado_historico` | PK do ativo |
| `campo_alterado_historico` | nome real da coluna (`designador_links`, `serial_equipamentos`, `id_unidades_links`, …) |
| `valor_antigo_historico` / `valor_novo_historico` | valores antes/depois (vazio no lado inexistente) |
| `operacao_historico` | INSERT / UPDATE / DELETE conforme o par antigo/novo |

Casos especiais:

- **Transferência / desassociação**: só `id_unidades_equipamentos` ou `id_unidades_links` (origem → destino ou NULL).
- **Exclusão**: snapshot de todas as colunas auditáveis com `valor_novo` vazio (operação DELETE).
- **PPPoE senha**: nunca em claro — `(definida)` / `(redefinida)` / remoção.

Índice de apoio à listagem (último atendimento): `sql/020_admin_inventory_ultimo_atendimento_idx.sql`.

### Manutenção inventário

| Situação | Nota |
|----------|------|
| Nova mutação admin | Sempre `registrar_field_changes` + cache bust; espelhar eq e links |
| Performance DataTables | Evitar ColumnControl `searchList` em colunas de alta cardinalidade |
| Contrato list ≠ detail | Não inchir payload da listagem com PPPoE/mac/licença |

## Secretarias Blueprint (catálogo Device BP)

Página: `/prodesp/admin/blueprint_secretarias` (menu **ADMIN → Secretarias Blueprint**).  
APIs: `GET/POST /api/admin/blueprint_secretarias`, `GET/PUT/DELETE /api/admin/blueprint_secretarias/<id>`.  
Código: `blueprint_secretaria_repo.py` + cache `blueprint_catalog.py`; rotas em `app.py`. Schema: `sql/021_blueprint_secretaria_catalog.sql`.

| Op | Detalhe |
|----|---------|
| List / create / update | JSON (PortalDt); valida acrônimo, template, layout, flags |
| DELETE soft | Body `{ "hard": false }` — `ativo=0`; geração cai em fallback `BP_OES` |
| DELETE hard | Body `{ "hard": true }` — remove cadastro (+ aliases) |
| Tabela ausente | API **503** + mensagem orientando aplicar 021; página mostra alerta |
| Auditoria | Create/update/soft/hard → `historico` com `tabela_afetada_historico = prodesp_blueprint_secretaria`, **1 linha por campo** (`registrar_field_changes`), user RE/nome via `registrar_log` |
| UI histórico | Botão ⟲ na grade → modal; `GET /api/admin/blueprint_secretarias/<id>/historico` (admin, só leitura) |

Após escrita: grava **histórico** (mesma conexão/transação) e **invalida cache** de processo (TTL ~60s entre workers). Em multi-worker a regra nova pode demorar até o TTL em workers que não receberam o write.

Uso: incluir secretaria / template Device BP **sem deploy de código** (com 021 aplicada). Doc de domínio: [`blueprint-csv.md`](blueprint-csv.md).

## Riscos e mitigações

| Risco | Mitigação / atenção |
|-------|---------------------|
| Delete destrutivo irreversível | Só `admin_user=1`; confirmar na UI |
| Forjar trilha de auditoria | Uso restrito a admin; ownership de linhas relacionadas |
| Segredos de link na auditoria | PPPoE descriptografado só nesta API admin |
| Bypass de regras de negócio | Admin ignora dono/substatus — processo interno deve limitar quem é admin |
| Injection | SQL parametrizado; erros via `_prodesp_json_error` |
| Inventário sem trilha | Diff por campo real + máscara de senha; gate admin |
| Catálogo Blueprint errado em massa | Gate admin; soft-inactivate antes de hard-delete; smoke CSV no acrônimo |

## Uso recomendado

1. Preferir correção pelo fluxo normal (edit atendimento) sempre que possível.
2. Admin para: limpar agendamento errado, corrigir log/histórico, remoção excepcional de atendimento, inventário global (transferência/desassociação), **e cadastro de secretarias Blueprint**.
3. Após delete/agenda/inventário/catálogo: validar lista + (se aplicável) gerar Blueprint no acrônimo.
4. Não documentar/compartilhar dumps da auditoria com PPPoE em claro.
