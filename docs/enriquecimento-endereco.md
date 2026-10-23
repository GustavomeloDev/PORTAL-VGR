# Enriquecimento de endereço — PRODESP

Sugestão automática de CEP, bairro, município, UF e coordenadas a partir do endereço digitado.  
**Não grava no banco** — só preenche campos vazios do formulário; o analista confirma ao salvar.

## API

`POST /prodesp/api/enriquecer-endereco` — `@login_required` (qualquer usuário logado do módulo).

**Módulo:** `prodesp/prodesp/endereco_enriquecimento.py` → `enriquecer_endereco_unidade(payload)`.

## UI

- Botões `btnEnriquecerEnderecoEdit` / `Create` nos modais (`prodesp_atendimento_modals.html`)
- JS: `prodesp_enriquecer_endereco.js` (atendimentos + dashboard; lazy load)
- Auto-trigger com debounce (~900 ms) quando atendimento já iniciado e mudam endereço/número/CEP
- Aplica `updates` nos inputs; toast com `message` / `warnings`

## Entrada / saída

**Input:** `endereco`, `numero`, `bairro`, `municipio`, `estado`, `cep`, `latitude`, `longitude`

**Output (alto nível):**

```text
success, updates, sources, warnings, partial, pending,
confidence (alta|media|baixa), logradouro_match_score, message
```

Só sugere campos vazios ou placeholder (ex.: coordenada `0`).

## Provedores (sem API key no código)

| Etapa | Fonte | Notas |
|-------|--------|------|
| Número | Parse local / `S/N` em rodovia | |
| CEP | ViaCEP → OpenCEP → BrasilAPI | `sleep` ~0,15s entre tentativas |
| Geo | Nominatim (search → structured → reverse) | ~1,1s entre requests; User-Agent definido |

Sem cota server-side própria; a UI recomenda ~2s entre cliques por causa do Nominatim.

## Falhas / avisos comuns

- CEP de outra cidade/UF
- Baixa similaridade do logradouro
- CEP não encontrado
- Nominatim sem resultado
- Endereço + município insuficientes
- Coordenadas placeholder tratadas como vazias
- Confiança `baixa` / `media` → revisar antes de salvar

## Segurança / débitos

- Chamadas CEP usam HTTPS com `verify=False` no cliente HTTP atual (risco MITM no tráfego de saída) — ver [`debitos-conhecidos.md`](debitos-conhecidos.md).
- Não envia dados sensíveis além do endereço público.
- Resultado é sugestão: validação final é do analista + save no servidor.
