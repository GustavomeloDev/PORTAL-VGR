# Dashboard, gestão e schedulers — PRODESP

Página: `/prodesp/dashboard_atendimentos`  
JS: `script_gestao_atendimentos_prodesp.js` (+ sync `prodesp_dt_sync.js`)  
Acesso: perfil de **gestão** (Implantação “só analista” é redirecionado para atendimentos).

## Rotas

| Rota | Função |
|------|--------|
| `GET /prodesp/dashboard_atendimentos` | Página |
| `GET /prodesp/api/dashboard_data` | Linhas, agenda, motivos, tempos (+ `data_revision`) |
| `GET /prodesp/api/dashboard_kpis` | Cards/KPIs |
| `GET /prodesp/api/data_revision` | Poll leve de revisão |
| `GET /prodesp/download_report` | XLSX/CSV manual do período |

Filtro por período na UI; download usa o mesmo gate de gestão.

## Filtro de calendário (Data Início / Data Fim)

Campos: `#startDate` e `#endDate` (`type="date"`).  
Lógica: `script_gestao_atendimentos_prodesp.js` (+ presets via `login/static/js/login_periodo_datas.js`).

| Regra | Comportamento |
|------|----------------|
| Padrão ao abrir | Hoje / hoje |
| Intervalo livre | Início e fim podem diferir (ex.: 10/07 a 12/07); **não** há lock de “dia único” |
| Início > fim (usuário mudou **início**) | Data Fim = Data Início |
| Fim < início (usuário mudou **fim**) | Data Início = Data Fim |
| Datas futuras | Permitidas (agendamentos); atributo `max` é removido após load/preset |
| Ao alterar data | Normaliza e **recarrega** KPIs + tabela no evento `change` (sem botão Aplicar) |
| Presets | **Hoje** (hoje–hoje), **Ontem** (ontem–ontem), **7d** (hoje−6 → hoje) |
| Limpar filtros | Volta para hoje/hoje e recarrega |
| Download report | Usa o mesmo `#startDate` / `#endDate` (`start_date` / `end_date` na query) |

## Relatórios por e-mail (schedulers)

Iniciados em `run.py` (threads daemon), **desligados por default** até habilitar env.

Agenda, destinatários (Para/Cc), dias/feriados, Report Final e condicionais são editáveis em
**Ajustes operacionais → Personalização dos reports** (abas *PRODESP Gestão* e *PRODESP Time TBRA*),
gravados na `kvs` e válidos sem restart. Os valores do `.env` abaixo são o **padrão** quando não há
personalização; o `*_EMAIL_ENABLED` continua decidindo se o agendador roda na instância.
Guia completo: [`core/docs/reports-automaticos.md`](../../core/docs/reports-automaticos.md).

### Gestão (`gestao_relatorio_scheduler.py` → `gestao_relatorio_email.py`)

| Item | Comportamento (padrão `.env` → campo na tela) |
|------|----------------|
| Enable | `PRODESP_GESTAO_RELATORIO_EMAIL_ENABLED` (default false) — gate do servidor |
| Poll | `PRODESP_GESTAO_RELATORIO_POLL_SECONDS` (default 60, mín. 15) |
| Dias | Seg–sex, fuso `America/Sao_Paulo` → *Dias da semana* + *Feriados* |
| Periódico | `HORA_INICIO`–`HORA_FIM` (default 10–18), a cada 30 min → *Intervalo* ou *Horários fixos* |
| Skip vazio | `SKIP_VAZIO` → *Não enviar sem agenda/atendimento* |
| Skip dia encerrado | 0 `Em Atendimento` (Parcial/Concluído/Quebra = finalizado) com atividade → omite periódico e envia **Report Final** 1× → *Dia encerrado* |
| Final do dia | `FINAL_ENABLED`, após `HORA_FIM` → *Report Final* + hora; exige 0 em aberto (pendente = tenta a cada ciclo até 23:59); *Final só com atividade* |
| Repetição | *Não reenviar se números iguais* (KPIs gerais + por contratada) |
| Conteúdo | KPIs + XLSX/HTML (variant `gestao`, inclui tempos / Tck NOC) |
| Transporte | MS Graph (`MS_GRAPH_*`); `PRODESP_GESTAO_RELATORIO_EMAIL_TO` → *Para* / *Cc* (só admin edita) |

### TBRA (`tbra_relatorio_scheduler.py` → `tbra_relatorio_email.py`)

| Item | Comportamento (padrão `.env` → campo na tela) |
|------|----------------|
| Enable | `PRODESP_TIME_TBRA_RELATORIO_EMAIL_ENABLED` (default false) — gate do servidor |
| Horários | `PRODESP_TIME_TBRA_RELATORIO_HORARIOS` default `11,15,18,22` → *Horários fixos* (ou *Intervalo*) |
| Skip | Mesmas condicionais do gestão |
| Final | Após o **último horário** (ou hora do Final configurada); antecipado se dia encerrado. Mesmo corpo/anexo variant `tbra` |
| Conteúdo | Variant `tbra` (colunas mais enxutas); Final = `tipo_relatorio=final` |

`*_HORA_LIMITE_FINAL` não é mais usado.

**Nota:** no HTML, “X ativos” sob o total = registros **com atividade** no período (já iniciados), não o KPI Em Atendimento.

## Sync da UI

Ver [`cache-e-sync.md`](cache-e-sync.md): cache em memória + poll de `data_revision` + reload periódico (~90s).

## Módulos

| Módulo | Papel |
|--------|--------|
| `gestao_relatorio_email.py` | Monta e envia relatório gestão |
| `gestao_relatorio_scheduler.py` | Agenda envios gestão |
| `tbra_relatorio_email.py` / `tbra_relatorio_scheduler.py` | Variante TBRA |
| `relatorio_tempos.py` / `relatorio_observacoes.py` | Dados de tempos e observações |
| `dashboard_cache.py` | Cache do dashboard |

## Operação

1. Confirmar envs Graph e flags de enable **antes** de ligar em produção.
2. Smoke: abrir dashboard, trocar período, “Atualizar agora”, download report.
3. Schedulers: validar 1 envio de teste em horário controlado (destinatário de homologação).
4. Se KPIs “atrasados”, ver cache/TTL e se mutações chamam `_prodesp_mutations_cache_bust`.
