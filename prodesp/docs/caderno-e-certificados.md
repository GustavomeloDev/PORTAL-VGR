# Caderno de teste e certificados — PRODESP

Fluxos FortiGate ligados ao atendimento: coleta SSH, geração do `.xlsm`, carimbo NOC e export de certificados.

## Caderno de teste

### Fluxo (UI → API → arquivos)

1. Toolbar/modal no atendimento (`prodesp_caderno_teste.js`) — visível em substatus **Em Caderno de Teste** ou para **admin**.
2. **Coleta de logs** — `POST /prodesp/api/atendimentos/<id>/caderno/coletar-logs`  
   → SSH (jump → FGT) → grava bloco em `logs_atendimentos` + histórico.  
   Inclui `get sys status` (primeiro comando) e um resumo no log:
   `Version do equipamento`, `Número de Serie`, `Hostname` (parse de Version/Serial-Number/Hostname).  
   Na conclusão (Status+Substatus «Concluído»), esses valores são cruzados com o cadastro
   (`conclusao_equipamento_rules.py`) quando a coleta existir.
   Links MPLS/STATIC também são cruzados (`conclusao_links_rules.py`) com
   `get sys interface physical` / `show sys interface` / ARP (IP, máscara, gateway peer,
   ID VGR e velocidade da description) — ver [`regras-de-negocio.md`](regras-de-negocio.md) §10.
3. **Gerar caderno** — questionário + evidências no modal → `POST .../caderno/gerar`  
   → exige bloco FGT nos logs → preenche template MULTI-OES → `.xlsx`/`.xlsm` local + cópia na rede.
4. **Download** — `GET .../caderno/download?file=...` (local, depois rede; valida ID VGR no nome).
5. **Carimbo** — `GET .../caderno/carimbo-texto`.

### Quem pode usar

| Perfil | Acesso |
|--------|--------|
| Admin | Sempre |
| Analista / Implantação | Substatus **Em Caderno de Teste** e (dono do campo `analista_caderno_teste_atendimentos` **ou** dept Implantação) |
| Atendimento já concluído | Não-admin → indisponível |

Todas as rotas: `@login_required`.

### Pré-requisitos

- `loopback_vivo_unidades` preenchido (destino SSH).
- Coleta FGT **antes** de gerar (bloco nos logs).
- Questionário completo; VOIP CPE/FGT exige nome/telefone quando aplicável.
- Evidências: ESAQ **ou** (erro BBL + Speedtest), conforme UI.
- Template em `prodesp/static/caderno_teste/modelo/` (MULTI-OES v3; preferência `.xlsx`, fallback `.xlsm`).
- Em produção Windows: Microsoft Excel instalado no host do Portal (motor COM).

### Motor de geração

`PRODESP_CADERNO_ENGINE` (padrão **`auto`**):

| Valor | Quando usa | Observação |
|-------|------------|------------|
| `auto` | Windows + Excel/pywin32 → **excel_com**; senão openpyxl | **Padrão de produção** |
| `excel_com` / `excel` / `com` | Força Excel COM (win32) | Preserva fórmulas, drawings, links externos do MULTI-OES |
| `openpyxl` | Só gravação Python | Dev/Linux ou diagnóstico — **não usar em produção Windows** com o template MULTI-OES |

**Por que openpyxl não serve no MULTI-OES em produção:** ao regravar o workbook, o Excel pode pedir reparo e descartar/corromper partes do template (fórmulas em sheets, `externalLinks`, shapes/drawings/logos). Imagens **inseridas** na geração (ESAQ) podem até aparecer, mas o arquivo deixa de ser fiel ao modelo. Itaú/RD usam openpyxl porque o template deles é mais simples; o PRODESP depende do COM.

Preferir `PRODESP_CADERNO_ENGINE=auto` (ou `excel_com`) no servidor Windows.

### Concorrência e timeout (Excel COM)

No Waitress multi-thread, várias gerações ao mesmo tempo competem pelo Excel. O Portal limita com um **pool de slots** no processo:

| Parâmetro | Env | Padrão | Limite |
|-----------|-----|--------|--------|
| Slots paralelos | `PRODESP_CADERNO_EXCEL_POOL_SIZE` | **2** | 1–4 (`1` = fila estritamente serial) |
| Espera por slot livre | `PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC` | **60** s | 5–300 |
| **Teto duro do job COM** | `PRODESP_CADERNO_EXCEL_JOB_TIMEOUT_SEC` | **170** s | 1–300 (prod: manter ≥120) — mata o PID Excel da geração e libera o slot |
| Timeout no browser | `CADERNO_GERAR_TIMEOUT_MS` em `prodesp_caderno_teste.js` | **180** s | AbortController — mensagem amigável se estourar |

Comportamento:

1. Até N gerações rodam em paralelo (cada uma com `DispatchEx` + temp próprio).
2. A (N+1)ª **espera** até `LOCK_WAIT_SEC`; se não liberar → `ExcelComBusyError` / mensagem “limite de gerações simultâneas…”.
3. Cada job COM roda em thread com **teto duro** (`JOB_TIMEOUT_SEC`). Se estourar → `taskkill /F /T` no PID daquela instância → `ExcelComTimeoutError` → slot liberado (evita hang de horas).
4. A API **não segura conexão MySQL** durante o Excel: lê contexto → fecha pool → gera → reabre só para histórico. Falha no histórico após arquivo gerado é logada e **não** vira 500.
5. A UI também evita reentrada no mesmo modal (`gerandoEmAndamento`) e cancela o `fetch` após 180s.
6. Capacidade prática ≈ tamanho do pool; geração típica no host pode levar ~40–70s — por isso o wait padrão permanece **60s** (não reduzir sem medir o tempo real de `/caderno/gerar`).

Reinício do Portal recria o pool (tamanho lido do env na 1ª geração).

### Caminhos e envs (sem segredos)

| Destino / env | Resolução |
|---------------|-----------|
| Template | `static/caderno_teste/modelo/` (`MULTI-OES_…v3.xlsx` preferido) |
| Gerados (portal) | `static/caderno_teste/gerados/` ou `PRODESP_CADERNO_LOCAL_DIR` (recomendado **fora** do OneDrive) |
| Work temp COM | `PRODESP_CADERNO_WORK_DIR` — SaveAs temporário antes de publicar em `gerados/` |
| Rede / OneDrive | `[Paths] caderno_teste_rede_base` → `PRODESP_CADERNO_NETWORK_DIR` → default OneDrive → `{acronimo}/` |
| Motor | `PRODESP_CADERNO_ENGINE` (`auto` / `excel_com` / `openpyxl`) |
| Pool / wait | `PRODESP_CADERNO_EXCEL_POOL_SIZE`, `PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC` |

Config: `prodesp/config.ini` + `prodesp/config_paths.py` + `.env` do Portal.

Credenciais SSH **somente** via env (`PRODESP_FGT_*`, jump, `PRODESP_SSH_*`) — nunca no Git.

Timeouts de coleta: `PRODESP_SSH_CONNECT_TIMEOUT` (jump), `PRODESP_SSH_CHANNEL_TIMEOUT` (túnel FGT:22).

| Env diagnóstico | Padrão | Uso |
|-----------------|--------|-----|
| `PRODESP_SSH_DIAG_PING` | `1` (ligado) | Após falha de rede/SSH no FGT (não em auth), reabre o jump e roda `ping -c N` até o loopback; anexa ao toast |
| `PRODESP_SSH_DIAG_PING_COUNT` | `5` (máx. 10) | Contagem ICMP do diagnóstico |

FGT destino é **sempre porta 22**. Portas 3122/3222/22 no plano são do **jump** (principal e fallback / backup host).

### Falhas comuns

| Sintoma | Causa típica |
|---------|----------------|
| Coleta: jump inacessível | Host/porta do jump, firewall, credencial jump |
| Coleta: «encerrou a conexão SSH» / ping 0% loss | FGT `:22` fecha no handshake (ACL/allowaccess/trusted-host); L3 pode estar ok |
| Coleta: ping 100% loss | Rota/loopback/VPN a partir daquele jump |
| Coleta: auth FGT | `PRODESP_FGT_USER` / password — **sem** ping diagnóstico |
| Gerar sem coleta | Falta bloco FGT em `logs_atendimentos` |
| Template ausente | Pasta `modelo/` incompleta |
| Sem cópia SharePoint | Rede/OneDrive indisponível ou path de outro perfil (`WinError 5`) — arquivo **local** pode existir mesmo assim |
| Download 503 | Arquivo travado (Excel/OneDrive) — retry |
| Gerar “ocupado” | Pool COM esgotado — aguardar ~1 min; ver `POOL_SIZE` / `LOCK_WAIT_SEC` |
| UI “Gerando…” e depois timeout | AbortController 180s; Excel lento, fila ou hang COM — checar logs `excel_com: slot` e processos `EXCEL.EXE` |
| Excel pede reparo / logos sumiram | Motor `openpyxl` no MULTI-OES — voltar para `auto`/`excel_com` |
| Hang com várias gerações | Pool alto demais ou OneDrive em `gerados/` — reduzir `POOL_SIZE` para 1 e usar `LOCAL_DIR`/`WORK_DIR` locais |

### Módulos

| Módulo | Papel |
|--------|--------|
| `caderno_teste_service.py` | Orquestra permissões, coleta, geração, download |
| `fgt_ssh_collector.py` | SSH jump→FGT (paramiko) + whitelist de comandos + diagnostic ping |
| `fgt_command_registry.py` | Comandos CLI permitidos por acrônimo |
| `fgt_sys_status.py` | Parse de `get sys status` (version/serial/hostname) para resumo no log |
| `fgt_admin_cleanup.py` | Remove user local `admin` ao fim da coleta |
| `gerador_caderno_prodesp.py` | Orquestra motor (`auto`/`excel_com`/`openpyxl`) e preenchimento |
| `gerador_caderno_excel_com.py` | Motor de **produção** Windows (COM + pool de slots) |
| `caderno_template_map.py` | Células/âncoras do template |
| `caderno_carimbo_links.py` / `carimbo_noc_export.py` | Carimbo NOC |
| `caderno_interface_resolver.py` / `fgt_model_interfaces.py` | Interfaces FGT |
| `prodesp_caderno_teste.js` | Modal UI, AbortController 180s, anti reentrada |

---

## Certificados

### Fluxo manual (admin)

1. UI `prodesp_certificado_export.js` → `POST /prodesp/api/atendimentos/<id>/certificados/exportar`.
2. `exportar_certificados_atendimento` → SSH CLI PEM e/ou TFTP → pasta local + rede → e-mail Graph (zip/cer).

### Fluxo automático

- Hook no save do atendimento (`_prodesp_hook_certificado_auto_export`) na **primeira** transição para status/substatus de conclusão.
- Thread daemon; elegibilidade por flag/env e acrônimos (default tipicamente `POUPATEMPO,DER` via `PRODESP_CERTIFICADO_AUTO_*`).
- Sem botão na UI para o analista comum.

### Quem pode usar

| Ação | Quem |
|------|------|
| Export manual | **Somente admin** |
| Auto-export | Backend, se habilitado e acrônimo elegível |

### Caminhos

| Destino | Resolução |
|---------|-----------|
| Local | `prodesp/var/certificados/` ou `PRODESP_CERTIFICADO_LOCAL_DIR` |
| Rede | `[Paths] certificados_rede_base` / por acrônimo → envs `PRODESP_CERTIFICADO_NETWORK_*` → `{acronimo}/{hostname}/` |

### Pré-requisitos / falhas

- TFTP quando método exige `.p12` / modo tftp: FGT precisa alcançar TFTP:69 (local ou jump).
- E-mail: `PRODESP_CERTIFICADO_EMAIL_TO` + Graph configurado.
  - Por acrônimo (prioridade sobre o global): `PRODESP_CERTIFICADO_EMAIL_TO_ACRONIMOS=POUPATEMPO=a@x;DER=b@y` (`;` separa acrônimos, `,` separa e-mails).
  - Cópia fixa em todo envio: `PRODESP_CERTIFICADO_EMAIL_CC` (deduplicada se já estiver no Para).
- Auto desligado se `PRODESP_CERTIFICADO_AUTO_EXPORT` off ou acrônimo fora da lista.

### Módulos

| Módulo | Papel |
|--------|--------|
| `certificado_export_service.py` | Export + e-mail + histórico |
| `certificado_auto_export.py` | Agenda export na conclusão |
| `fgt_cert_exporter.py` | `.cer` / `.p12` via SSH/TFTP |
| `fgt_ssh_tftp.py` | Servidor TFTP temporário |

---

## Segurança

- Rotas autenticadas; caderno com checagem de substatus/dono; certificado manual só admin.
- Comandos FGT em whitelist (`fgt_command_registry`).
- Download valida nome/arquivo (não path traversal livre).
- Segredos só em env/credentials — não documentar valores.
