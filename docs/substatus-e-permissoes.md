# Substatus e permissões — PRODESP

Fonte da verdade: `prodesp/prodesp/atendimento_business_rules.py`.  
Espelho UI: `prodesp/static/js/prodesp_substatus_flow.js` + `script_atendimentos_prodesp.js`.  
Servidor: `_prodesp_validar_edicao_atendimento` em `app.py`.

## Status vs substatus

| Conceito | Campo | Papel |
|----------|-------|--------|
| **Status** | `status_atendimentos` | Ciclo de vida do ticket |
| **Substatus** | `substatus_atendimentos` | Etapa operacional dentro do fluxo |

### Status

- Operacional: `Em Atendimento`
- Finais (`FINAL_STATUSES_ATENDIMENTO`): `Concluído`, `Concluído Parcial`, `Quebra`, `Quebra TBRA`

### Substatus (fluxo principal)

Ordem (`FLUXO_SUBSTATUS_ORDEM`):

`Aguarda Gestão` → `Aguardando Config. Remota` → `Em Configuração Remota` → `Aguardando Config. MPLS` → `Em Configuração do MPLS` → `Aguardando Caderno de Teste` → `Em Caderno de Teste`

- Legado: `Triagem` → normalizado para `Aguarda Gestão`
- Paralelos: `Aguardando Cliente`, `Aguarda Contratada`, `Aguarda Licença`, `Com Suporte`
- Quebra normal: substatus que começam com `Quebra` (exceto SCI/Técnica)
- Quebra TBRA: apenas `Quebra SCI` ou `Quebra Técnica`

## Quem pode editar

| Perfil | Quando |
|--------|--------|
| **Admin** (`admin_user == 1`) | Sempre (ignora data/dono/AG-GP) |
| **AG / GP / SUPERVISORES** (dept `AGENDAMENTO` / `GP` / `SUPERVISORES` e **não** Implantação) | Substatus ∈ gestão + `Aguardando Config. Remota` + pendências externas; status `Em Atendimento`; **data = hoje** |
| **Implantação / analista** | `Em Atendimento` + hoje; **bloqueado** em Triagem/Aguarda Gestão; em etapas «Em …» precisa ser o **dono** (coluna de analista da etapa); filas «Aguardando …» sem dono (qualquer um assume) |

### AG/GP/SUPERVISORES — movimentos de substatus

- Permitido: gestão ↔ `Aguardando Config. Remota` ↔ pendências externas; Quebra a partir de etapas editáveis AG/GP/SUPERVISORES.
- **Bloqueado:** avançar para «Em …» (ex.: Em Configuração Remota) ou filas de Implantação (MPLS/Caderno).
- Cutover 2026: perfis canônicos `SUPERVISORES` e `GP` (legado `Supervisores/GP` removido). Hoje ambos seguem as mesmas regras restritas; futuro: permissões extras só em SUPERVISORES.

Funções: `validar_edicao_atendimento`, `destinos_substatus_permitidos_ag_gp`, `validar_transicao_substatus_ag_gp`.

## Observação obrigatória em transição

Resolver: `resolver_regra_observacao_substatus_transicao` (prioridade fixa).

| Prioridade | Situação | Prefixo típico | Mín. chars |
|------------|----------|----------------|------------|
| 1 | Entrar Aguarda Gestão / Triagem | `[Aguarda Gestão]` | 30 |
| 2 | Retorno na ordem do fluxo | `[Retorno] old → new:` | 10 |
| 3 | Entrar Com Suporte | `[Com Suporte - entrada]` | 10 |
| 4 | Entrar Cliente / Contratada / Licença | `[destino]` | 10 |
| 5 | Sair Com Suporte | `[Com Suporte - saída]` | 10 |
| 6 | Sair gestão (não para externo) | `[Aguarda Gestão - saída]` | 30 |

- Validação: `check_observacao_substatus_transicao`.
- Payload: `transicao_observacoes` no update.
- UI prepara texto antes do save (`prodespRegistrarObservacaoTransicaoStaging`).
- Matriz de testes: `test_substatus_observacao_matrix.py`.

## Quebra e Quebra TBRA

### Status `Quebra`

- Substatus deve ser Quebra **normal** (`is_substatus_quebra_normal`).
- Exige motivo «Fora do padrão».
- Observação de encerramento: prefixo do substatus + ≥10 chars.
- Saída de Gestão/Suporte para Quebra ainda pode exigir obs de **saída** (UI pode coletar dupla).

### Status `Quebra TBRA`

- Substatus exatamente `Quebra SCI` ou `Quebra Técnica`.
- Mesmo padrão de obs de encerramento quando enviada.

### Depois de Quebrar

- Não-admin: formulário de campos bloqueado (status ≠ Em Atendimento).
- Observação no **mesmo dia** ainda permitida (`validar_edicao_observacao_atendimento`).

## Travas de campo ligadas ao substatus

Não há tabela separada de locks — vêm das regras + UI:

| Situação | Efeito |
|----------|--------|
| `pode_editar` falso | Formulário desabilitado |
| Colunas de analista | Read-only (admin pode liberar); preenchidas ao assumir «Em …» |
| Entrar / sair Em Configuração do MPLS | Exige **analista MPLS** (`check_analista_mpls_em_config_mpls`) |
| Gestão → fila Aguardando | Exige Contratada / Field / Contato Field |
| Criar com status «Em Atendimento» | Exige Dados Field (confirmação na UI; gate `check_dados_field_create_em_atendimento`) |
| Sair Em Configuração Remota ou status → Concluído | Hostname obrigatório |
| Status+Substatus «Concluído» | Ticket NOC + serial Fortinet válido; se houver coleta FGT, cruzar equipamento (`get sys status`) e links MPLS/STATIC (`physical`/`show`/ARP) — `conclusao_equipamento_rules` + `conclusao_links_rules`. Em 400, UI reverte Status/Substatus ao persistido. |
| Entrar «Aguardando …» / regressão | Limpa colunas de analista da etapa |
| «Em …» sem analista | Não edita outros campos até assumir (mudança de substatus) |

## Funções-chave (referência rápida)

**Edição / dono:** `validar_edicao_atendimento`, `resolver_dono_edicao_atendimento`, `validar_dono_edicao_atendimento`  
**AG/GP:** `usuario_usa_regras_edicao_gp_agendamento_restritas_dict`, `validar_transicao_substatus_ag_gp`  
**Concorrência:** `check_atendimento_substatus_update`, `check_substatus_change_conflict`  
**Obs:** `resolver_regra_observacao_substatus_transicao`, `check_observacao_substatus_transicao`, `check_observacao_quebra_encerramento`  
**Gates:** `check_dados_field_triagem_para_fila_aguardando`, `check_dados_field_create_em_atendimento`, `check_hostname_obrigatorio_transicao`, `check_analista_mpls_em_config_mpls`, `validate_conclusao_equipamento`, `validate_conclusao_links`

App: `_prodesp_validar_edicao_atendimento`, `_prodesp_is_agendamento_ou_gp`, `_prodesp_anexar_flags_edicao`.

## Segurança

- Permissão **sempre** revalidada no servidor (não confiar só no select da UI).
- Admin é exceção explícita — documentar quem tem `admin_user` no processo de acesso.
- Transições com obs mínima reduzem encerramento sem justificativa.
