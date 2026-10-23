# core — Módulo de Infraestrutura Compartilhada

Módulo central com os alicerces técnicos reutilizados por todos os outros módulos do portal
(agendamentos, login, rd, fust, etc.).  
Não possui lógica de negócio própria — fornece apenas infraestrutura.

---

## Estrutura de Diretórios

```
core/
├── app.py                   # Blueprint Flask /core (health-check)
├── logger.py                # Configuração centralizada de logging
├── base/                    # Classes base abstratas (Controller, Service, Repository)
│   ├── controller.py
│   ├── service.py
│   └── repository.py
├── database/                # Camada de acesso ao banco de dados
│   ├── connection.py        # Wrapper DB_REQUEST (mysql-connector)
│   ├── clients_config.py    # ClientBaseRepository + helpers de conexão por módulo
│   ├── config.py            # Configurações globais de banco
│   └── repository.py        # BaseRepository (versão legada — em migração)
├── exceptions/              # Hierarquia de exceções customizadas
│   └── base_exceptions.py
├── integrations/            # Integrações externas
│   ├── email.py             # GraphAuthService + EmailTemplateService (Microsoft Graph)
│   └── microsoft_auth.py    # GraphAuthService isolado (autenticação MSAL)
├── repository/              # Repositórios de domínio compartilhados
│   ├── RConnection.py       # openConnection (compatibilidade legada)
│   ├── RClientes.py
│   ├── REquipamentos.py
│   ├── RLinks.py
│   ├── RAtendimento.py
│   ├── exceptions.py        # NotFoundError, QueryError, ConnectionError
│   └── table_repository.py  # TableRepository genérico
├── security/
│   └── encryption.py        # Criptografia Fernet (FERNET_TECH_KEY) + hash de senha
├── blueprint/
│   └── model_blueprint.py   # Blueprint de modelo para novos módulos
├── static/                  # Assets compartilhados (CSS/JS)
│   ├── css/datatable/       # portal_datatable.css (toolbar / cabeçalho DT)
│   └── js/
│       ├── datatable/       # PortalDt* (toolbar, columns, font, defaults CC)
│       └── utils/           # PortalFieldValidation, PortalEnriquecerEndereco
├── docs/
│   ├── datatable-toolbar.md          # Toolkit DataTables
│   ├── validacoes-campos-link.md     # ID VGR, LP, IP/máscara, operadora, velocidade, serial
│   ├── validacao-ipv4-mascara.md     # Calculadora IP + máscara (detalhe)
│   ├── enriquecimento-endereco.md   # Completar endereço (ViaCEP / Nominatim)
│   └── reports-automaticos.md       # Reports e-mail/Teams + Personalização (Ajustes operacionais)
├── reports/                 # Reports SUPERVISORES (Macro, FUST-only, Fila) + report_settings
├── tests/
│   ├── test_portal_dt_toolbar_smoke.py
│   ├── test_fortinet_serial_network.py
│   ├── test_endereco_enriquecimento.py
│   └── test_portal_validations_high_medium.py
└── utils/
    ├── sanitizers.py / validators.py
    ├── network.py                    # IPv4, máscara, grupo IP/GW/subrede
    ├── endereco_enriquecimento.py      # Fachada enriquecer_endereco_portal
    ├── endereco_enriquecimento_engine.py
    ├── fortinet_serial.py, coordinates.py, text_ids.py
    ├── operadora.py, link_required.py, link_vivo.py
    ├── velocity.py, ticket_noc.py, timing.py
```

---

## Variáveis de Ambiente Necessárias

| Variável               | Uso                                                               |
|------------------------|-------------------------------------------------------------------|
| `HOST`                 | Host do banco de dados MySQL                                      |
| `USER`                 | Usuário do banco de dados                                         |
| `PASS`                 | Senha do banco de dados                                           |
| `PORT`                 | Porta do banco de dados (padrão: 3306)                            |
| `CLIENT_DB_NAME`       | Sobrescreve o nome do banco para todos os módulos cliente         |
| `DATABASE_<MODULO>`    | Sobrescreve o nome do banco para um módulo específico             |
| `FERNET_TECH_KEY`      | Chave Fernet (base64 URL-safe) para criptografia de dados sensíveis |
| `MICROSOFT_CLIENT_ID`  | Client ID do app Azure AD                                         |
| `MICROSOFT_CLIENT_SECRET` | Secret do app Azure AD                                         |
| `MICROSOFT_TENANT_ID`  | ID do tenant Azure AD                                             |
| `LOG_LEVEL`            | Nível de log: DEBUG, INFO, WARNING, ERROR, CRITICAL (padrão: INFO)|

---

## Camadas e Responsabilidades

### `core/database/connection.py` — `DB_REQUEST`

Context manager sobre `mysql.connector`. Gerencia cursor, auto-commit, rollback e fechamento
seguro da conexão.  
Método | Descrição
-------|----------
`get_all(query, id)` | SELECT retornando lista de dicionários
`get_one(query, value)` | SELECT retornando único dicionário
`insert(query, values)` | INSERT com commit automático (se `auto_commit=True`)
`update(query, values)` | UPDATE/DELETE com commit automático
`commit()` / `rollback()` | Controle explícito de transação

### `core/database/clients_config.py` — `ClientBaseRepository`

Repositório base para módulos que usam banco isolado (agendamentos, etc.).  
Lê credenciais do ambiente e abre conexão por módulo (com prioridade:
`<MODULO>_DB_NAME` → `DATABASE_<MODULO>` → argumento padrão).

```python
from core.database.clients_config import ClientBaseRepository

class MeuRepository(ClientBaseRepository):
    def __init__(self):
        super().__init__('nome_do_banco')
```

### `core/base/` — Classes Abstratas

| Classe            | Herança | Propósito                                              |
|-------------------|---------|--------------------------------------------------------|
| `BaseRepository`  | `ABC`   | CRUD genérico; aceita nome de banco ou objeto de conexão |
| `BaseService`     | `ABC`   | Validação de campos, controle de multitenancy          |
| `BaseController`  | `ABC`   | Extração de dados do request Flask, tenant/user da sessão |

### `core/security/encryption.py`

Criptografia **Fernet** simétrica para campos sensíveis.  
Requer `FERNET_TECH_KEY` no ambiente. Sem a chave, os dados passam sem criptografia
(comportamento de fallback seguro para desenvolvimento).

| Função                    | Descrição                                              |
|---------------------------|--------------------------------------------------------|
| `encrypt_text(value)`     | Criptografa uma string                                 |
| `decrypt_text(value)`     | Descriptografa token Fernet                            |
| `encrypt_fields(data, fields)` | Criptografa campos específicos de um dict         |
| `decrypt_fields(data, fields)` | Descriptografa campos específicos de um dict      |
| `encrypt_list_fields(items, fields)` | Criptografa campos em lista de dicts       |
| `decrypt_list_fields(items, fields)` | Descriptografa campos em lista de dicts    |
| `encrypt_pwd(plain)`      | Gera hash de senha com Werkzeug (bcrypt)               |
| `check_pwd(plain, hashed)`| Verifica senha contra hash                             |

### `core/exceptions/base_exceptions.py`

Hierarquia de exceções da aplicação:

```
BaseAppException
├── ValidationError        # Dados inválidos
├── BusinessRuleError      # Violação de regra de negócio
├── RepositoryError        # Falha no banco de dados
├── AuthenticationError    # Falha de autenticação
├── AuthorizationError     # Acesso negado
├── NotFoundError          # Recurso não encontrado
└── DuplicateError         # Recurso duplicado
```

### `core/integrations/`

**`microsoft_auth.py`** — `GraphAuthService`  
Autentica no Azure AD via MSAL (`ConfidentialClientApplication`) e retorna access token
para o Microsoft Graph API. Requer `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` e
`MICROSOFT_TENANT_ID`.

**`email.py`** — `GraphAuthService` + `EmailTemplateService`  
Versão estendida de autenticação Graph combinada com montagem de templates de e-mail HTML
(inclui assinatura corporativa Vita e anexo de logo via CID).

### `core/logger.py` — `setup_logger`

Configura o logger raiz com:
- Arquivo rotativo `logs/system.log` (5 MB / 5 backups)
- Handler de console (DEBUG em dev)
- Silencia libs barulhentas: `paramiko`, `urllib3`, `werkzeug`, `mysql.connector`, etc.

Deve ser chamado **uma única vez** no `run.py`, antes de qualquer import de blueprint:

```python
from core.logger import setup_logger
setup_logger(name="app", log_file="logs/app.log")
```

### `core/utils/` — validação e texto (importar o módulo, não `core.utils.__init__`)

`core/utils/__init__.py` só reexporta sanitizers/validators clássicos. DMA e VGR importam **arquivos** (`from core.utils.network import ...`).

| Arquivo | Papel | DMA | VGR |
|---------|--------|-----|-----|
| `network.py` | IPv4, máscara, `validate_ip_mask_group` | validators + seed | `parse_link_payload` |
| `endereco_enriquecimento.py` | `enriquecer_endereco_portal` | `POST /dma/api/enriquecer-endereco` | `POST /vgr/api/enriquecer-endereco` |
| `fortinet_serial.py` | Serial / modelo Fortigate | validators, licenças, seed | validators equipamento |
| `coordinates.py` | lat/long | validators, seed | validators unidade |
| `text_ids.py` | hostname, ID VGR, designador, paste | validators, hostname, licenças | validators |
| `ticket_noc.py` | Ticket NOC (7 dígitos, começa em 1) | — | atendimento / equipamento |
| `operadora.py` | VIVO/CLARO/TIM/OI/STARLINK/VTAL/ATIVA + OUTROS | app + validators | — |
| `link_required.py` | Campos WAN por modo | validators, CSV | `parse_link_payload` |
| `link_vivo.py` | Pendências VIVO (não bloqueio) | validators | — |
| `velocity.py` | Mbps | validators, CSV, seed | link |
| `validators.py` | e-mail, CNPJ, CPF | — | CPF |
| `sanitizers.py` | string/CNPJ/CPF/CEP | — | — |
| `timing.py` | tempos de request | app Flask (outros módulos) | — |

Guias com chamada, exemplos e testes:

- [docs/validacoes-campos-link.md](docs/validacoes-campos-link.md) — ID VGR, LP, IP/máscara, operadora, VIVO, velocidade, serial, hostname, lat/long, ticket NOC, CPF
- [docs/validacao-ipv4-mascara.md](docs/validacao-ipv4-mascara.md) — calculadora IP + máscara (grupo)
- [docs/enriquecimento-endereco.md](docs/enriquecimento-endereco.md)

**JS compartilhado** (`/core/static/js/utils/`):

| Asset | Global | DMA | VGR |
|-------|--------|-----|-----|
| `portal_field_validation.js` | `PortalFieldValidation` | blueprints (grupo IP/máscara + fill subrede) | unidade detalhe + atendimentos (IPv4, serial, ticket; grupo máscara no **servidor**) |
| `portal_enriquecer_endereco.js` | `PortalEnriquecerEndereco` | blueprints | modal unidades |

Prodesp **não** usa o motor de endereço nem a calculadora de máscara do Core (cópia e regras próprias).

### Reports automáticos (e-mail / Teams)

`core/reports/` envia os reports SUPERVISORES (Macro FUST + PRODESP, FUST-only, Fila sem analista)
e concentra em `report_settings.py` a agenda/condicionais de **todos** os reports, inclusive
PRODESP Gestão e TBRA. Configuração editável em **Ajustes operacionais → Personalização dos reports**
(padrão = `.env`).

→ [docs/reports-automaticos.md](docs/reports-automaticos.md)

### DataTables — toolbar compartilhada

Assets em `core/static/.../datatable/` (`PortalDtToolbar`, `PortalDtColumns`, `PortalDtFontSize`).  
Consumidos hoje pelo módulo **login**; guia de uso, visual ColumnControl e checklist:

→ [docs/datatable-toolbar.md](docs/datatable-toolbar.md)

Smoke: `.\.venv_portal_pessoal\Scripts\python.exe core\tests\test_portal_dt_toolbar_smoke.py`

Validação / endereço:

```powershell
.\.venv_portal_pessoal\Scripts\python.exe -m pytest `
  core/tests/test_fortinet_serial_network.py `
  core/tests/test_endereco_enriquecimento.py `
  core/tests/test_portal_validations_high_medium.py -q
```

---

## Endpoint Exposto

| Rota          | Método | Descrição                  |
|---------------|--------|----------------------------|
| `/core/health`| GET    | Retorna `{"status": "ok"}` |
| `/core/`      | GET    | Redireciona para `/login`  |

---

## Como Gerar a Chave Fernet

```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
# Cole o valor gerado na variável FERNET_TECH_KEY do seu .env
```
