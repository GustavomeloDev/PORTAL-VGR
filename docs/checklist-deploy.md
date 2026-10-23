# Checklist de deploy — PRODESP

Checklist operacional para subir ou atualizar o módulo. Não inclui valores de segredo.

## 1. Pré-requisitos

- [ ] Venv `.venv_portal_pessoal` (ou equivalente do ambiente) com deps instaladas
- [ ] Credenciais DB / Graph / SSH FGT apenas em env ou `credentials/` **fora do Git**
- [ ] `.env` / `config.ini` revisados no alvo (caminhos de caderno/certificados)
- [ ] Backup do schema/dados se for aplicar migration destrutiva

## 2. Migrations SQL (`prodesp/sql/`)

Aplicar em ordem no banco PRODESP:

| # | Arquivo | Notas |
|---|---------|--------|
| 008 | `008_planejada_unidades.sql` | Colunas planejada em `unidades` |
| 009 | `009_sensitive_fields_varchar255.sql` | **Antes** do script Fernet |
| 010 | `010_hostname_unidades_varchar80.sql` | Hostname |
| 011 | `011_dashboard_perf_indexes.sql` | Índices dashboard (idempotente) |
| 012 | `012_observacoes_historico_indexes.sql` | Índices obs/histórico |
| 013 | `013_fix_atendimentos_status_log_triggers.sql` | Triggers status_log |
| 014 | `014_atendimentos_list_perf.sql` | Índices lista |
| 015 | `015_logs_atendimentos_mediumtext.sql` | Logs MEDIUMTEXT |
| 016 | `016_mv_opcionais_unidades.sql` | Colunas MV_* |
| 017 | `017_redundante_critico_links.sql` | Flag Redundante Crítico |
| 018 | `018_substatus_desde_atendimentos.sql` | Coluna materializada substatus (P0-01) |
| 019 | `019_atendimento_tempo_snapshot.sql` | Snapshot tempos (P0-02) |
| 020 | `020_admin_inventory_ultimo_atendimento_idx.sql` | Índice último atendimento (inventário admin) |
| 021 | `021_blueprint_secretaria_catalog.sql` | Catálogo Device Blueprint / secretarias (+ seed inicial) — **Admin → Secretarias Blueprint** |

Ritual flags WRITE→READ: [`performance-flags.md`](performance-flags.md).

Views (aplicar/atualizar se o ambiente ainda não tiver):

- [ ] `vw_agendamentos_e_atendimentos_ativos.sql`
- [ ] `vw_tempo_atendimento_detalhado.sql`

Pós-009 (se ainda houver dados em claro):

- [ ] `prodesp/migrations/migrate_encrypt_sensitive_fields.py` (homologar antes)

## 3. Código e processo

- [ ] Deploy do branch/commit desejado
- [ ] Restart do processo Flask / workers (`run.py` sobe schedulers gestão/TBRA)
- [ ] Confirmar flags de e-mail **off** até validar destinatários de homologação

## 4. Smoke funcional (mínimo)

| Fluxo | Checagem |
|-------|----------|
| Login + projeto PRODESP | Acessa `/prodesp/atendimentos` |
| Create atendimento | Inicia por ID VGR |
| Edit link | Save OK; duplicidade WAN bloqueia com mensagem |
| Blueprint | Busca VGR → modal confirmação → gerar; Device BP / máscara; ou banner unicidade |
| Admin inventário | Só admin; listagem + transferir; histórico 1 linha/campo |
| Admin Secretarias Blueprint | Só admin; listagem OK; se 021 ausente → 503 / alerta; criar/editar secretaria e gerar CSV com o acrônimo |
| Dashboard (gestão) | KPIs carregam; “Atualizar agora” |
| CSV Agendamento | Download modelo (sem upload prod se não for o momento) |
| Caderno (homolog) | `ENGINE=auto`; Excel no host; coleta + gerar; pool N=2; teto job ~170s; timeout UI ~180s |

## 5. Segurança pós-deploy

- [ ] Usuário só Implantação **não** acessa menu gestão / dashboard
- [ ] Usuário sem dono **não** edita etapa «Em …» de outro analista
- [ ] API mutável sem login → redirect/401
- [ ] Nenhum `.env` / dump / planilha sensível no pacote de deploy
- [ ] Revisar [`debitos-conhecidos.md`](debitos-conhecidos.md) (rotas legadas / gaps)
## 6. Observabilidade

- [ ] Logs sem stack SQL ao cliente
- [ ] Se UI “atrasada”: ver [`cache-e-sync.md`](cache-e-sync.md)
- [ ] Schedulers: 1º envio só após enable + destinatário de teste

## 7. Rollback rápido

- [ ] Reverter commit/release anterior
- [ ] Migrations já aplicadas: avaliar script reverso **só se existir** (várias são additive — não reverter às cegas)
- [ ] Bust implícito no restart (cache/revisão em memória zeram)

## Referências

- Docs: [`README.md`](README.md)
- Regras de link: [`regras-de-negocio.md`](regras-de-negocio.md)
- Permissões: [`substatus-e-permissoes.md`](substatus-e-permissoes.md)
- Caderno: [`caderno-e-certificados.md`](caderno-e-certificados.md)
