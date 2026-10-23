# CSV Agendamento e Inserção em Massa — PRODESP

Dois fluxos distintos no menu de gestão. Não confundir.

| Fluxo | URL | Propósito |
|-------|-----|-----------|
| **CSV Agendamento** | `/prodesp/csv_manager` | Atualiza **agenda/planejamento** de unidades existentes por ID VGR. **Não cria atendimento.** |
| **Inserção em Massa** | `/prodesp/dados_em_massa_import` | **Upsert** de cadastro: unidades (+ links se designador, + equipamentos se serial). |

## CSV Agendamento

### Fluxo UI → API

1. Página `csv_prodesp.html` + `painel_csv_prodesp.js`
2. Modelo: `GET /prodesp/api/csv/gerar` → `modelo_prodesp.csv` (separador `;`)
3. Upload → parse no browser → pré-validação (válidas / corrigíveis / sem ação)
4. Envio: `POST /prodesp/api/csv/register` com `{ keys, body, rejeitadas_previa }`
5. Backend: `processar_importacao_agendamento_csv` → `UPDATE unidades` + logs → commit
6. Resposta 200/207 + e-mail em thread (não desfaz o upload se o e-mail falhar)
7. Rate limit por usuário (default **120s**, env `PRODESP_CSV_UPLOAD_MIN_INTERVAL_SEC`)

### Colunas

`id_vgr`, `data_agendamento`, `hora_agendamento`, `contratada`, `field`, `contato_field`

### Regras principais

- `id_vgr` numérico obrigatório; duplicata no arquivo → erro (mantém a 1ª)
- Com data e/ou hora: data + hora + contratada obrigatórios
- Data: UI `dd/mm/yyyy` → ISO; backend rejeita data **&lt; hoje** (fuso SP)
- Hora: `HH:mm`
- Contratada: whitelist (DELFIA, INELCOM, MAMInfo, SPREAD, Vivo Redes - Capital/Interior)
- Field preenchido → contato 10–11 dígitos; se Field = empresa da lista, deve coincidir com contratada
- Só planejamento (sem agenda) permitido se houver contratada/field/contato
- Bloqueio se a unidade já tem atendimento **Concluído**; VGR inexistente → erro
- Contato sensível: criptografado no DB
- Linhas sem VGR e sem agenda/planejamento: ignoradas

### E-mail pós-import

- `send_agendamento_csv_report` (MS Graph, background)
- Toggle: `PRODESP_AGENDAMENTO_CSV_EMAIL_ENABLED` (default on)
- Destinatários: `PRODESP_AGENDAMENTO_CSV_EMAIL_TO` (ou default no código)
- HTML: sucessos, repetidos, erros, rejeitadas na prévia

### Permissões

`@login_required` + menu gestão (`_prodesp_pode_ver_menu_gestao`: admin ou perfil não “só Implantação”).

### Módulos

| Módulo | Papel |
|--------|--------|
| `agendamento_csv_validacao.py` | Regras de linha |
| `agendamento_csv_import_service.py` | Prefetch, UPDATE, buckets sucesso/erro |
| `blueprint/agendamento_csv_notifier.py` | Relatório e-mail Graph |
| `painel_csv_prodesp.js` | Pré-validação e correção inline |

### Falhas comuns

VGR inválido/inexistente; duplicata no arquivo; data passada; unidade concluída; field sem contato; **429** rate limit; e-mail Graph falha (upload já commitado); resposta **207** com erros parciais.

---

## Inserção em Massa

### Fluxo UI → API

1. Página `prodesp_dados_em_massa_csv.html` + `script_dados_em_massa_csv_prodesp.js`
2. Modelo: `GET /prodesp/api/dadosemmassa_csv/template`
3. Upload: `POST /prodesp/api/dadosemmassa_csv/register` com `{ body }`
4. Por linha: upsert `unidades` → opcional `links` → opcional `equipamentos`
5. Toast + lista de erros — **sem e-mail**

### Colunas (alto nível)

VGR, Intrgov, nome/endereço/geo, IPs/loopbacks, designador/tipo/operadora/IPs/VLAN/velocidade, serial/modelo.

- Chave: `id_vgr_unidades`
- Campos vazios no upsert **não sobrescrevem** valor existente
- Link só se houver `designador_links`; equipamento só se houver `serial_equipamentos`
- Validação de negócio **mais fraca** que o CSV de agendamento (não substitui as regras de unicidade/VIVO do atendimento)

### Permissões

- Página: mesma regra de menu gestão
- APIs `/api/dadosemmassa_csv/*`: hoje só `@login_required` (gap vs página — não confiar só na UI)

### Falhas comuns

Linha sem VGR ignorada; erro SQL genérico; CSV deve usar `;`; desalinhamento histórico de IDs HTML/JS no upload (se o botão não reagir, conferir IDs no template vs script).

---

## Segurança

- Agendamento: gate de gestão + rate limit + SQL parametrizado
- Contato field criptografado
- APIs não devolvem stack ao cliente
- Massa: preferir reforçar o mesmo gate de gestão nas APIs em evolução futura (débito: [`debitos-conhecidos.md`](debitos-conhecidos.md))
