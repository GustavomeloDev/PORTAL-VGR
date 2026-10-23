# Regras de negócio — PRODESP

Módulos canônicos (servidor é a fonte da verdade; JS só antecipa UX).

## 1. Unicidade de links e loopbacks

**Módulo:** `prodesp/prodesp/link_uniqueness_rules.py`  
**Pré-check:** `POST /prodesp/api/check-uniqueness`  
**Bloqueio em:** `links-update`, `atendimentos/create`, `atendimentos/update` (loopbacks), admin link, gerar Blueprint (form + API).

| Regra | Escopo |
|-------|--------|
| IP WAN repetido | Global entre links; também ≠ Gateway do mesmo link |
| IP Gateway repetido | Global; também ≠ WAN do mesmo link |
| ID VGR do link | Mesma **operadora** |
| Designador | Mesma **operadora** |
| Loopback Vivo / Cliente / On BGP | Distintos entre si e únicos entre unidades |

Mensagens: campo + valor + registro conflitante (tipo, designador, operadora, ID VGR unidade). Na mesma unidade, orienta conferir a qual link pertence.

Lote (Blueprint): detecta duplicata **no formulário** e consulta o banco excluindo todos os `id_link` do lote (evita eco de mensagem).

**UI:** highlight vermelho + hint sob o campo (Blueprint em tempo real; atendimento no bloqueio de save).

## 1.1 Formato Designador / ID VGR do link

**Módulo:** `prodesp/prodesp/link_format_rules.py` (também KPIs admin «fora do padrão»).  
**Bloqueio em:** `validate_link_fields` (create/update atendimento, admin link) + Blueprint form/CSV.

| Campo | Critério |
|-------|----------|
| Designador | **Só VIVO:** apenas dígitos e comprimento ≥ 15 |
| ID VGR do link | Se preenchido: apenas dígitos e comprimento ≥ 7 |

Outras operadoras: Designador livre (unicidade por operadora continua valendo).

## 1.2 Serial Fortinet

**Módulo:** `conclusao_equipamento_rules` + espelho JS em `prodesp_live_field_validation.js`  
(`validateSerialFortinetFormat` / `bindSerialFortinetInput` — borda vermelha/amarela/verde + hint).

| Fluxo | Formato Fortinet |
|-------|-----------------|
| Admin equipamentos | **Sempre** obrigatório no save (server + UX) |
| Atendimento add/edit FGT | **Sempre** no add (UX + server create/update) |
| Blueprint | UX aviso se provisório; **bloqueia** se unidade tem Em Atendimento / Concluído / Parcial |
| Conclusão Concluído | Sempre + cruzamento coleta |

Duplicidade: mesma mensagem «já pertence ao ID VGR …» (não move).  
Admin Links: `initAdminLinkFormValidation` — formato Designador/ID VGR + WAN/GW + pré-check `/api/check-uniqueness` com highlight.

## 2. Operadora VIVO (máscara / gateway)

**Módulo:** `blueprint/link_vivo_rules.py` + JS live validation.

| Tipo | Máscara | Gateway (sem RC) |
|------|---------|------------------|
| MPLS | `255.255.255.248` (/29) | WAN − 1 (ou WAN = GW + 1) |
| STATIC | WAN par → /30 (`…252`); ímpar → /31 (`…254`) | WAN − 1 |

Aplicado na UI e em `normalize_vivo_link_fields` / `normalize_link_api_payload`.

## 3. Redundante Crítico (MPLS + VIVO)

**Módulo:** `blueprint/redundante_critico_rules.py`  
**Coluna:** `redundante_critico_links` TINYINT(1) — migration `sql/017_redundante_critico_links.sql`.

- Só aplica a **MPLS + VIVO**.
- Persistência: flag 0/1 + `ip_wan_links` efetivo (sem coluna “base” separada).
- Toggle idempotente: ±2 no WAN a partir do valor gravado (não acumula).
- Com RC: WAN = GW + 3 / GW = WAN − 3; sem RC: ±1.

## 4. Link STATIC — bloco proibido

**Módulo:** `db_field_limits.validate_static_wan_ip_block`

- IP WAN iniciando em `201.60.` ou `201.61.` → bloqueio (pedir manobra de IP).
- Vale para atendimento e Blueprint.

## 5. WAN ≠ Gateway (mesmo link)

Validado em `validate_link_wan_gateway_distinct` e reforçado em `link_uniqueness_rules`.

## 6. Velocidade

**Módulo:** `blueprint/link_velocity_rules.py` + inputs `.prodesp-velocity-mbps-input`.

- Aceita `300 Mbps`, `10G`, valores legados ×1000 → grava Mbps numérico.

## 7. Campos obrigatórios de link

**Atendimento / admin / create** — `db_field_limits.validate_link_required_fields` (via `validate_link_fields`):

| Sempre | Por tipo |
|--------|----------|
| Tipo, Operadora, Designador, Velocidade | **MPLS / STATIC:** IP WAN, Gateway, Máscara; **ID VGR do link** se Operadora = VIVO |
| | **PPPoE:** User e Password |
| | **DHCP:** só os comuns |

**Blueprint** — `validar_dados_blueprint` (form + API regenerar), por link MPLS/STATIC presente:

- Operadora, Designador, IP WAN, Gateway, Máscara, Velocidade
- ID VGR se Operadora = VIVO
- Pelo menos um link (MPLS ou STATIC) cadastrado

VLAN e Redundante Crítico permanecem opcionais. UI antecipa; servidor bloqueia.

## 8. Limites de campo / espaços

**Módulo:** `db_field_limits.py`

- Tamanhos alinhados ao MySQL; mensagens “máx. N caracteres”.
- Sem espaços em designador, hostname, acrônimo, loopbacks (conforme lista), etc.
- Coordenadas normalizadas (vírgula → ponto).

## 9. Serial de equipamento

- Inferência de modelo FortiGate: `prodesp_equipment.py` (`infer_modelo_equipamento_from_serial`, `resolve_fortigate_model_fragment`).
- Blueprint: serial duplicado em outra unidade → bloqueio com ID VGR da colisão.

### Device Blueprint (CSV)

**Motor:** `blueprint/prodesp_csv_generator.py` (`resolve_device_blueprint_detail`).  
**Catálogo (fonte viva):** tabelas `prodesp_blueprint_secretaria` / `_alias` — **Admin → Secretarias Blueprint**. Migration `sql/021_blueprint_secretaria_catalog.sql`.  
**Doc completa:** [`blueprint-csv.md`](blueprint-csv.md).

Templates em hub **C3-C4** (exceto **TJSP** / **FLORESTAL** = C1-C2 e **SAPTELE** = C5-C6 no seed); o trecho `40F`/`60F`/… vem do equipamento. Sufixo `REDE_LAN_*` dinâmico se flag do cadastro permitir.

**Exemplos do seed inicial** (produição pode divergir após edições no Admin):

| Acrônimo | Template base (exemplos) |
|----------|---------------|
| DETRAN | `DETRAN_HUB-C3-C4_{modelo}_REDE_LAN_1` |
| DPESP | `DPESP_HUB-C3-C4_{modelo}_REDE_LAN_1` |
| SELJ | `SE_HUB-C3-C4_{modelo}_REDE_LAN_1` |
| SAP | `SAP_HUB-C3-C4_{modelo}_REDE_LAN_1` (+ `emite_dhcp_server_1`) |
| SAPTELE (alias SAP-TELE) | `SAP-TELE_HUB-C5-C6_{modelo}_REDE_LAN_1` (+ `emite_dhcp_server_1`) |
| DER / SDE | `…_HUB-C3-C4_{modelo}_REDE_LAN_1` |
| SEDS | `SEDS_…` + regra rede `antiga` (.0) + DHCP LAN `.10`–`.60` |
| PROCON | `PROCOM_HUB-C3-C4_{modelo}_REDE_LAN_1` |
| PRO-SANGUE (alias PROSANGUE) | `PROSANGUE_HUB-…` |
| SP-AGUAS (alias SPAGUAS) | `SPAGUAS_HUB-…` |
| CEETEPS / POUPATEMPO / PGE / CDHU / JUSTIÇA / FLORESTAL / TJSP / DIPOL | ver seed / Admin |
| **sem cadastro ativo** | `BP_OES_{modelo}` + layout **REDE_LAN** (IP LAN − 1; sem DHCP especial) |

**Rede LAN:** default `nova` = IP − 1; `antiga` = .0 (configurável por secretaria).  
**DHCP LAN** e **dhcp_server_1** também vêm do cadastro.

**LAN SEC / TER / QUA (opcional):** colunas `mv_ip_lan_*_unidades` (CIDR) + `mv_rede_lan_*_unidades` (IP rede sem máscara). No CSV: `MV_IP_LAN_*` sem CIDR, `MV_MASK_LAN_*` do CIDR **ou** da máscara confirmada sem IP (`_lan_extra_triple`). UI: cascata SEC→TER→QUA (`prodesp_blueprint_confirm.js`).

**Confirmação pré-geração:** modal edita hostname / IPs / máscaras / Redes SEC–QUA; gateways RO; mostra Device BP + motivo. Overrides: `apply_blueprint_confirm_overrides`. Histórico se máscara ≠ CIDR mapeado (ou máscara sem IP).

**WiFi Guest (opcional, accordion MV):** `mv_ip_wifi_guest` (CIDR) → CSV `MV_IP_WIFI_GUEST` + `MV_MASK_WIFI_GUEST`; demais (`MV_REDE_*`, DHCP, reserva) IP puro. Migration `017_lan_sec_wifi_guest_unidades.sql` (renomeia `ip_lan_02` → `mv_ip_lan_sec`).

**`MV_INTF_*`:** só na geração do CSV, mapa por modelo `40F` / `60F` / `120G` / `900G`; outros modelos → vazios. Sem coluna no banco.

## 10. Atendimento (status / substatus / ownership)

**Módulo:** `atendimento_business_rules.py`  
**Doc detalhada:** [`substatus-e-permissoes.md`](../docs/substatus-e-permissoes.md)

- Matriz de substatus, Quebra/TBRA, restrições AG/GP, analista atuante.
- Edição só se permitido server-side (não confiar na UI).
- Observação mínima em várias transições (gestão, retorno de fila, externos, Quebra).

### Conclusão (Status + Substatus «Concluído»)

**Módulo:** `conclusao_equipamento_rules.py` + `conclusao_links_rules.py`

| Regra | Quando |
|-------|--------|
| Serial Fortinet no padrão `FGTxx…TK…` ou `FG120GTK…` (ex. `FGT40FTK2409D6QK`, `FG120GTK25006244`) | Sempre — bloqueia provisórios (`123`, `TEST`, etc.) |
| Hostname / Serial / Version = coleta FGT (`get sys status`) | Só se existir coleta nos logs |
| Ticket NOC | Já existente |
| Links MPLS/STATIC × coleta | Só se existir `get sys interface physical` e/ou `show sys interface` |

**Cruzamento de links** (quando houver coleta de interface):

| Campo | Fonte na coleta |
|-------|-----------------|
| IP WAN + Máscara | `get sys interface physical` (`ip:`) e/ou `set ip` do show |
| Gateway | Peer da /30–/31 a partir do IP coletado; se /29+, `get sys arp` na interface |
| ID VGR + Velocidade | `set description` (`SAI-BL_INET1_{id}_{vel}Mb`) ou `estimated-*-bandwidth` |
| Tipo | Marcadores description (`SCM`→MPLS, `SAI-BL`→STATIC) |

Sem coleta de interface → não bloqueia links. Associação interface↔link por IP/rede (mesmo resolver do carimbo).

**UX na falha de conclusão:** Status/Substatus voltam ao valor persistido; toast com a mensagem; console do DevTools não repete erros de negócio esperados (só falhas inesperadas/rede).

## 11. Ticket NOC

**Módulo:** `ticket_noc_validation.py` — formato `1` + 6 dígitos (quando aplicável).

## 12. Campos sensíveis

**Módulo:** `sensitive_fields_crypto.py` — PPPoE etc. criptografados (Fernet) antes de gravar.
