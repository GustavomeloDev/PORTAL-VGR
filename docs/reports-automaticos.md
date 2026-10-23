# Reports automáticos e Personalização (Ajustes operacionais)

Guia dos reports enviados pelo portal (e-mail Microsoft Graph e Teams via Power Automate) e da
tela **Ajustes operacionais → Personalização dos reports**, onde admin/supervisão ajustam agenda,
destinatários e condicionais **sem reiniciar** a aplicação.

## Reports

| ID | Report | Canais | Agendador | Envio |
|----|--------|--------|-----------|-------|
| `MACRO` | Macro FUST + PRODESP (KPIs) | e-mail + Teams | `core/reports/scheduler.py` | `send_reports.enviar_macro` |
| `FUST` | FUST-only (cartão sem PRODESP) | Teams (webhook FUST) | `core/reports/scheduler.py` | `send_reports.enviar_fust` |
| `FILA` | Fila remota sem analista + Analistas disponíveis | e-mail + Teams | `core/reports/scheduler.py` (`tick_fila`) | `send_reports.enviar_fila` |
| `GESTAO` | PRODESP Gestão (XLSX) | e-mail | `prodesp/prodesp/gestao/gestao_relatorio_scheduler.py` | `gestao_relatorio_email.enviar_relatorio_gestao_periodo` |
| `TBRA` | PRODESP Time TBRA (XLSX) | e-mail | `prodesp/prodesp/gestao/tbra_relatorio_scheduler.py` | `tbra_relatorio_email.enviar_relatorio_tbra_periodo` |

Todos os agendadores são threads daemon iniciadas em `run.py`, fuso `America/Sao_Paulo`, poll
padrão de 60 s. A regra de agenda é única: `core/reports/report_settings.py`
(`slot_periodico`, `final_devido`, `executar_tick`).

## De onde vem a configuração

```
.env (padrão)  ──►  kvs.REPORT_CFG_<ID> (JSON salvo pela tela)  ──►  config efetiva
```

1. **`.env`** decide se o agendador **roda nesta instância** (`report_permitido_no_servidor`):
   - MACRO: `SUPERVISORES_MACRO_EMAIL_ENABLED` ou `SUPERVISORES_MACRO_TEAMS_ENABLED`
   - FUST: `SUPERVISORES_MACRO_TEAMS_ENABLED`
   - FILA: `SUPERVISORES_FILA_EMAIL_ENABLED` ou `SUPERVISORES_FILA_TEAMS_ENABLED`
   - GESTAO: `PRODESP_GESTAO_RELATORIO_EMAIL_ENABLED`
   - TBRA: `PRODESP_TIME_TBRA_RELATORIO_EMAIL_ENABLED`

   A tela **não liga** o que o `.env` desligou (selo "Agendador desligado no .env").
2. Os demais valores do `.env` (horários, destinatários, `SKIP_VAZIO`, `FINAL_ENABLED`…) são o
   **padrão** quando o report não tem personalização (selo "Padrão (.env)").
3. Ao salvar na tela, o JSON completo vai para a tabela `kvs` (chave `REPORT_CFG_<ID>`) e passa
   a valer no próximo ciclo (cache de 60 s). "Restaurar padrão (.env)" grava a chave vazia.
4. JSON inválido/corrompido no `kvs` é ignorado campo a campo (log `WARNING`) e cai no `.env`.

> **Atenção:** se DEV e PROD apontam para o mesmo banco, a personalização vale nos dois.

### E-mail × Teams (quem ganha)

- **E-mail:** só a personalização (`Habilitar envio` + `Enviar por e-mail` + Para/Cc).
- **Teams:** precisa das **duas** travas: personalização (`Habilitar envio` + `Enviar no Teams`)
  **e** seção **Webhooks Teams** (master ligado, switch do report ligado e URL preenchida).
  A tela mostra um aviso amarelo quando o webhook impede o envio.

## Campos da tela (por report)

| Campo | Regras |
|-------|--------|
| Habilitar envio / e-mail / Teams | Canais inexistentes no report ficam ocultos e desligados |
| Agenda: **Intervalo** | Início/fim (HH:MM) + "Enviar a cada" 30 min, 1 h, 1 h 30, 2 h ou digitado (5–1440 min). Slot = `(agora − início) // intervalo` |
| Agenda: **Horários fixos** | Lista HH:MM (até 24). Um envio por horário, válido por 60 min (retenta falha). Início/fim ficam ocultos, exceto na Fila |
| Dias da semana | Pelo menos 1 |
| Feriados | **DD-MM-AAAA** (aceita DD/MM/AAAA), separados por `;` ou linha; até 120. Gravado como AAAA-MM-DD |
| Para / Cc | Até 60 e-mails cada; Para obrigatório com e-mail ligado. **Somente admin** altera |
| Report Final | Liga/desliga + hora. Nos reports com Final, os periódicos param na hora do Final e o Final sai no 1º ciclo depois dela (ex.: 18:00 → 18:01). Pendente (ex.: atendimento em aberto) = tenta de novo a cada ciclo até 23:59 |

### Condicionais

| Condicional | Reports | Efeito |
|-------------|---------|--------|
| Não enviar sem agenda/atendimento | MACRO, FUST, GESTAO, TBRA | Periódico omitido se total do dia = 0. **Macro:** envia só o projeto com dados (ex.: só FUST); nenhum = não envia |
| Não reenviar se números iguais | todos | Compara os números do último envio do dia (tempo médio fica de fora). Só periódicos; o Final sempre sai. Na Fila, compara o conjunto de unidades — **ligado, anula o "relembrar"** |
| Dia encerrado → Final | MACRO, FUST, GESTAO, TBRA | Teve atividade e 0 em atendimento: periódico omitido e Final enviado na hora (1×/dia) |
| Report Final só com atividade | MACRO, FUST, GESTAO, TBRA | Sem atividade no dia, o Final não sai |
| Limiar da fila (min) | FILA | Tempo mínimo em espera para a unidade entrar no alerta |

Gestão/TBRA mantêm a regra de negócio: o Final só sai com **0 atendimentos em aberto**.

### Fila (comportamento próprio)

- **Intervalo:** unidade nova acima do limiar → alerta imediato; a fila inteira é relembrada a cada
  intervalo enquanto houver atraso.
- **Horários fixos:** unidade nova continua imediata (dentro de início/fim); o relembrar só nos
  horários fixos.
- Final da fila: na hora configurada; não interrompe os alertas.
- Com `SUPERVISORES_FILA_SEMPRE=true` o padrão é 00:00–23:59 e 7 dias.

## Permissões e segurança (rotas)

Base: `/login/admin/ajustes-operacionais/reports` (blueprint `login`).

| Rota | Método | Acesso | Observação |
|------|--------|--------|------------|
| `/data` | GET | admin ou supervisão central | specs + config efetiva + `env_permitido`, `tem_override`, `pode_editar_emails` |
| `/salvar` | POST | admin ou supervisão central | `{report_id, config}`; `report_id` em whitelist; validação estrita → 400 com `erros[]`; supervisor: servidor **mantém** Para/Cc gravados |
| `/restaurar` | POST | **somente admin** | Volta ao `.env` |

- `@login_required` + checagem server-side; anônimo → redirect para login; sem perfil → 403.
- CSRF: POSTs em `/login/admin*` exigem `X-CSRF-Token` (`admin_csrf.js` + `<meta name="csrf-token">`,
  presentes em `admin_dashboard.html` e `supervisao.html`).
- Auditoria `admin_auditoria`: `ajustes_operacionais.reports_salvar` / `reports_restaurar`
  (sem gravar os endereços de e-mail, só quantidades).
- Erro interno → mensagem genérica (sem `str(e)`); e-mails validados contra quebra de linha/cabeçalho.
- JS (`ajustes_reports_script.html`) usa só `textContent`/`.value` com dados da API.

## Arquivos

| Arquivo | Papel |
|---------|-------|
| `core/reports/report_settings.py` | Specs, defaults do `.env`, leitura/gravação `kvs`, validação, agenda, "igual ao último", `executar_tick` |
| `core/reports/send_reports.py` | Macro / FUST-only / Fila com condicionais |
| `core/reports/scheduler.py` | Loop SUPERVISORES (MACRO, FUST, FILA) |
| `prodesp/prodesp/gestao/gestao_relatorio_email.py` | Envio executivo Gestão/TBRA + `executar_report_final` |
| `login/main.py` | Rotas `/admin/ajustes-operacionais/reports/*` |
| `login/models.py` | `LoginDynamicSettings.K_REPORT_CFG` (whitelist de chaves `kvs`) |
| `login/templates/snippets/ajustes_reports_section.html` / `ajustes_reports_script.html` | Tela (incluída em Ajustes operacionais do admin e da Supervisão) |

## Logs úteis

```
reports - MACRO periódico slot 2026-10-14 #4: sem_dados
reports - FUST periódico slot 2026-10-14 #4: desabilitado
reports - TBRA Report Final (2026-10-14): enviado
supervisores - fila snapshot 5 unidade(s) ≥30 min
```

Motivos possíveis: `enviado`, `sem_dados`, `igual`, `encerrado`, `sem_atividade`, `desabilitado`,
`pendente` (Final aguardando), `falha` (retenta no mesmo slot).
`FUST … desabilitado` também aparece quando o webhook FUST está desligado/sem URL.

## Limitações conhecidas

- "Não reenviar igual" fica em memória: após restart o 1º envio sempre sai.
- `*_HORA_LIMITE_FINAL` não é mais usado (Final pendente tenta até 23:59).
- O Final do Macro inclui os dois projetos mesmo com "sem dados" ligado (filtro vale para periódicos).

## Testes

```powershell
.\.venv_portal_pessoal\Scripts\python.exe -m pytest `
  core/tests/test_report_settings.py core/tests/test_supervisor_reports.py `
  login/test_ajustes_reports_routes.py prodesp/prodesp/gestao -q
```

`core/tests/conftest.py` isola a tabela `kvs` (os testes não leem nem gravam o banco real).
Pendência conhecida: `test_html_fila_tem_analistas_e_picos_escapados` (e-mail Final da fila omite
analistas; anterior a esta funcionalidade).
