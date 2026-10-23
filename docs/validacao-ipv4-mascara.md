# Validação IPv4 por máscara (`core.utils.network`)

Calculadora de rede compartilhada: **IP + máscara** definem a rede; **gateway** e **subrede** (quando preenchidos) devem pertencer a ela.

Não inclui regra de operadora (VIVO `/30`, bloco `201.60`, MPLS). Isso fica no módulo (`link_vivo`, `operadora`, `link_required`).

**Espelho JS:** `core/static/js/utils/portal_field_validation.js` → `window.PortalFieldValidation`.

---

## Consumidores atuais

| Módulo | Python | JS |
|--------|--------|----|
| **DMA** | `dma/dma/validators.py` — LAN/VLAN (IP+máscara+subrede) e WAN (IP+máscara+gateway) | `dma_blueprints.js` — `validateIpMaskGroup` + `maybeFillSubnetFromIpMask` |
| **VGR** | `vgr/vgr/cadastros/validators.py` (`parse_link_payload`) — IP+máscara+gateway+subrede | Carrega o script; validação de grupo **só no servidor**. O cliente checa IPv4 isolado e `wanEqualsGateway` |
| **Prodesp** | Não usa este pacote para o grupo IP/máscara | — |
| Seed DMA | `normalize_ipv4_excel_artifact` em `dma/sql/gerar_seed_dma.py` | — |

---

## Python — como chamar

```python
from core.utils.network import (
    validate_ipv4_field,
    validate_netmask_field,
    validate_wan_gateway_distinct,
    validate_ip_mask_group,
    ipv4_network_address,
)
```

Todas as `validate_*` devolvem `str` (mensagem) ou `None` (ok).

### 1) Campo isolado (primeiro)

```python
err = validate_ipv4_field(ip, label="WAN1 IP")
err = validate_netmask_field(mascara, label="WAN1 máscara")
err = validate_ipv4_field(gw, label="WAN1 Gateway")
err = validate_wan_gateway_distinct(ip, gw, label="WAN1")
```

- `validate_ipv4_field(..., allow_cidr=True)` aceita `10.0.0.1/24`.
- `validate_netmask_field` exige máscara pontilhada **contígua** (`255.255.255.0` ok; `255.255.0.255` não).

### 2) Grupo (depois dos isolados)

```python
err = validate_ip_mask_group(
    ip=ip,
    mascara=mascara,
    gateway=gw,          # opcional
    subrede=subrede,     # opcional (LAN/VLAN)
    label="WAN1",
)
if err:
    errors.append(err)
```

Regras do grupo (quando IP e máscara estão preenchidos e são IPv4 válidos):

- Máscara inválida (bits não contíguos) → erro.
- Prefixo `< 31`: IP/gateway não podem ser endereço de **rede** nem **broadcast**.
- Gateway preenchido e válido deve estar **na mesma rede**.
- Subrede preenchida deve ser o **endereço de rede** (ex.: `10.1.2.0`), não um host.
- Campo vazio no grupo **não bloqueia** (o isolado já tratou obrigatoriedade).

`/30` (WAN típica): os dois hosts da subrede são válidos — Claro WAN+1 e VIVO WAN−1 passam.

### 3) Derivar subrede

```python
from core.utils.network import ipv4_network_address

net = ipv4_network_address("10.1.2.254", "255.255.255.0")
# "10.1.2.0"
```

### Outras funções úteis

| Função | Uso |
|--------|-----|
| `normalize_ip_text` | Remove espaços |
| `canonicalize_ipv4` | Host canônico (Excel 12 dígitos, zeros à esquerda, CIDR → host) |
| `normalize_ipv4_excel_artifact` | `187115201143` → `187.115.201.143` |
| `is_valid_ipv4` / `is_valid_ipv4_cidr` | Booleanos |
| `is_valid_dotted_netmask` | Bits 1 contíguos |

---

## JavaScript — como chamar

```html
<script src="/core/static/js/utils/portal_field_validation.js?v=7"></script>
```

Subir `?v=` ao alterar o arquivo (Waitress não faz cache-bust).

```js
var V = window.PortalFieldValidation;
var err = V.validateIpMaskGroup({
  ip: wanEl.value,
  mascara: maskEl.value,
  gateway: gwEl.value,
  subrede: subnetEl.value, // LAN/VLAN
  label: "WAN 1",
});
if (err) { /* bloquear submit / setLiveFieldState */ }

// Preenche subrede só se o campo estiver vazio
V.maybeFillSubnetFromIpMask(subnetEl, ip, mask);
```

Helpers alinhados ao Python: `validateIpv4`, `ipv4NetworkAddress`, `wanEqualsGateway`, `ipv4LiveState`.

---

## Exemplos

**WAN /30 válida (os dois hosts):**

```text
IP 187.51.205.114  máscara 255.255.255.252  GW 187.51.205.113  → ok
IP 187.51.205.113  máscara 255.255.255.252  GW 187.51.205.114  → ok
```

**Gateway fora da rede:**

```python
validate_ip_mask_group(
    ip="187.51.205.114",
    mascara="255.255.255.252",
    gateway="187.51.205.1",
    label="WAN 1",
)
# "WAN 1: Gateway 187.51.205.1 não pertence à rede 187.51.205.112/30 ..."
```

**VLAN: subrede deve ser a rede, não o host:**

```python
validate_ip_mask_group(
    ip="10.1.2.254",
    mascara="255.255.255.0",
    subrede="10.1.2.254",
    label="VLAN 1",
)
# erro: esperado 10.1.2.0
```

---

## Como testar

```powershell
.\.venv_portal_pessoal\Scripts\python.exe -m pytest `
  core/tests/test_fortinet_serial_network.py -q
```

Casos em `TestIpMaskCalculator`: rede `/30`, gateway em outra rede, VLAN divergente, máscara não contígua, grupo vazio não bloqueia.

**Manual DMA:** blueprints → WAN STATIC com IP e gateway em redes diferentes → não gera CSV. LAN: preencher IP+máscara deve sugerir subrede; subrede errada bloqueia.

**Manual VGR:** cadastro de link WAN com máscara e gateway fora da rede → API 400 (`ValueError`). O JS da unidade **não** replica o grupo; o servidor é a fonte da verdade.

---

## O que não fazer

- Não copiar a calculadora para o módulo.
- Não usar `GROUP BY` / string concat em IP.
- Não tratar pendência VIVO “gateway = WAN−1” como bloqueio aqui — isso é `link_vivo.collect_vivo_link_pendencias`.
