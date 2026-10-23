# Documentação PRODESP

Módulo de implantação SD-WAN / atendimento do Portal Implantação (prefixo Flask `/prodesp`).

## Índice

| Documento | Conteúdo |
|-----------|----------|
| [Arquitetura e código](arquitetura.md) | Pastas, pacotes Python, JS, templates, bibliotecas, imports |
| [Páginas e fluxos](paginas-e-fluxos.md) | Telas, create/edit, Blueprint (confirm), CSV, caderno, admin inventário / Secretarias Blueprint |
| [Blueprint CSV](blueprint-csv.md) | Device BP dinâmico, **catálogo MySQL**, modal confirmação, máscaras, cascade LAN, manutenção |
| [Regras de negócio](regras-de-negocio.md) | Unicidade, VIVO, RC, STATIC, **obrigatórios de link**, Device BP, conclusão FGT, substatus, limites |
| [Substatus e permissões](substatus-e-permissoes.md) | Quem edita, fluxo de etapas, obs obrigatória, Quebra/TBRA |
| [Caderno e certificados](caderno-e-certificados.md) | SSH FGT, motor COM/openpyxl, pool N=2, timeout UI, caminhos/envs, certificados |
| [CSV Agendamento e Massa](csv-agendamento-e-massa.md) | Agenda por VGR, upsert em massa, e-mail, validações |
| [Dashboard e gestão](dashboard-e-gestao.md) | KPIs, download report, schedulers e-mail gestão/TBRA |
| [Cache e sync](cache-e-sync.md) | TTL, bust, data_revision, UI desatualizada |
| [Admin ops](admin-ops.md) | APIs admin, exclusão, auditoria, inventário eq/links, **Secretarias Blueprint** |
| [Enriquecimento de endereço](enriquecimento-endereco.md) | ViaCEP/Nominatim, sugestão de campos, UI |
| [Checklist de deploy](checklist-deploy.md) | Migrations **008–021**, smoke, segurança, rollback |
| [Débitos conhecidos](debitos-conhecidos.md) | Templates ausentes, gaps de permissão, hardening |
| [APIs e segurança](apis-e-seguranca.md) | Rotas, auth, CSRF/IDOR, validações server-side |
| [SQL e dados](sql-e-dados.md) | Migrations, views, planilhas, artefatos estáticos |
| [Performance / materialização](performance-flags.md) | Flags P0, DDL 018/019, entity_select; link fase2 |

README técnico do pacote Python: [`../prodesp/README.md`](../prodesp/README.md).  
Testes unitários: [`../prodesp/tests/README.md`](../prodesp/tests/README.md).

## Como rodar testes (venv obrigatório)

Na raiz do repositório:

```powershell
.\.venv_portal_pessoal\Scripts\python.exe -m unittest discover -s prodesp/prodesp/tests -v
.\.venv_portal_pessoal\Scripts\python.exe -m unittest prodesp.prodesp.tests.test_link_uniqueness_rules prodesp.prodesp.blueprint.test_redundante_critico_rules prodesp.prodesp.tests.test_conclusao_equipamento_rules prodesp.prodesp.tests.test_conclusao_links_rules -v
.\.venv_portal_pessoal\Scripts\python.exe -m unittest prodesp.prodesp.blueprint.test_blueprint_detran -v
.\.venv_portal_pessoal\Scripts\python.exe -m pytest prodesp/prodesp/blueprint/test_blueprint_catalog.py prodesp/prodesp/blueprint/test_blueprint_secretaria_flow.py -q
.\.venv_portal_pessoal\Scripts\python.exe -m pytest prodesp/prodesp/blueprint/test_blueprint_secretaria_http.py -q
.\.venv_portal_pessoal\Scripts\python.exe -m prodesp.prodesp.blueprint.test_blueprint_routes
.\.venv_portal_pessoal\Scripts\python.exe -m unittest prodesp.prodesp.caderno.test_caderno_prodesp -v
```

Programa performance (portal): [`../../docs/auditoria/fase2/README.md`](../../docs/auditoria/fase2/README.md).

## Escopo do módulo

- Cadastro e edição de **atendimentos** e dados de **unidade / links / equipamentos / loopbacks**
- Geração de **Blueprint CSV** (SD-WAN) com confirmação (máscaras / Rede LAN / Device BP dinâmico via **catálogo**)
- **Dashboard** de gestão e relatórios
- **Admin inventário** global (equipamentos / links) com histórico por campo
- **Admin Secretarias Blueprint** — acrônimo → template Device BP / regras LAN (MySQL)
- **Caderno de teste** FortiGate e export de certificados
- Importação CSV de **agendamento / dados em massa**

## Manutenção da documentação

Ao entregar feature relevante no módulo:

1. Atualizar o doc de domínio (ex.: Blueprint → [`blueprint-csv.md`](blueprint-csv.md)).
2. Espelhar estrutura/arquivos novos em [`arquitetura.md`](arquitetura.md).
3. Rotas novas → [`apis-e-seguranca.md`](apis-e-seguranca.md); SQL → [`sql-e-dados.md`](sql-e-dados.md) + checklist.
4. Débito consciente → [`debitos-conhecidos.md`](debitos-conhecidos.md).
