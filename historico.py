import json
from flask import session
from flask_login import current_user
from core.logger import get_logger

logging = get_logger("PRODESP")


# ─────────────────────────────────────────────
# CAMADA 1 — Deserialização genérica
# ─────────────────────────────────────────────

def parse_json_list(val) -> list:
    """
    Converte qualquer entrada em lista Python de forma segura.
    Aceita: None, '', 'null', [], {}, list, dict, str JSON.
    """
    if val in (None, '', 'null', [], {}):
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, dict):
        return []
    try:
        obj = json.loads(val)
        return obj if isinstance(obj, list) else []
    except Exception as e:
        logging.warning(
            f"[parse_json_list] Não foi possível parsear: {val!r} | Erro: {e}"
        )
        return []


def _is_json_list(val) -> bool:
    """
    Detecta se o valor é (ou representa) uma lista JSON.
    Retorna True se for list, ou string que deserializa para list.
    """
    if isinstance(val, list):
        return True
    if not isinstance(val, str):
        return False
    stripped = val.strip()
    if not stripped.startswith('['):
        return False
    try:
        obj = json.loads(stripped)
        return isinstance(obj, list)
    except Exception:
        return False


# ─────────────────────────────────────────────
# CAMADA 2 — Representação por item
# ─────────────────────────────────────────────

# Ordem fixa de chaves conhecidas para garantir representação estável.
# Independente de como o JSON chegou do banco ou do frontend,
# a string gerada será sempre a mesma para o mesmo conteúdo.
_CHAVES_ORDENADAS = [
    # Temporais — sempre primeiro
    'data_observacao', 'data', 'hora', 'datetime', 'data_hora',
    'timestamp', 'created_at', 'updated_at', 'date',
    # Autor
    'analista', 'usuario', 'user', 'autor', 'author',
    'nome', 'name', 'operador',
    # Conteúdo — sempre por último
    'observacao_rd', 'observacao', 'obs', 'descricao',
    'description', 'texto', 'text', 'mensagem', 'message', 'nota',
]


def _repr_generica(item: dict) -> str:
    """
    Representa um item dict como string sem nomes de chaves.

    A ordem segue _CHAVES_ORDENADAS para garantir que o mesmo item
    sempre produza a mesma string, independente da ordem das chaves
    no JSON original (que pode variar entre leituras do banco).

    Chaves desconhecidas vão ao final, em ordem alfabética.
    Valores nulos ou vazios são ignorados.

    Exemplos de saída:
      "17/03/2026 13:31:25 | teste da versão do historico 2.0 2"
      "2026-03-04 | 15:18 | Ingrid Da Silva Lima | teste de observação"
    """
    chaves_conhecidas = [k for k in _CHAVES_ORDENADAS if k in item]
    chaves_restantes  = sorted(k for k in item.keys() if k not in _CHAVES_ORDENADAS)

    partes = []
    for k in chaves_conhecidas + chaves_restantes:
        v = item.get(k)
        if v is not None and str(v).strip() != '':
            partes.append(str(v).strip())

    return " | ".join(partes)


# Mapa opcional: sobrescreve a representação genérica para campos específicos.
# Se o campo NÃO estiver aqui, usa _repr_generica automaticamente.
_CAMPO_REPR_MAP: dict[str, callable] = {}


def _get_repr_fn(campo: str) -> callable:
    """
    Retorna a função de representação para o campo.
    Se não houver sobrescrita registrada, usa a genérica.
    """
    return _CAMPO_REPR_MAP.get(campo, _repr_generica)


# ─────────────────────────────────────────────
# CAMADA 3 — Diff entre dois estados JSON
# Retorna lista de tuplas (antigo, novo) — uma por item alterado
# ─────────────────────────────────────────────

def _diff_json_list(campo: str, val_antigo, val_novo) -> list[tuple[str, str]]:
    """
    Calcula a diferença entre dois valores de lista JSON.

    Retorna uma lista de tuplas (antigo_fmt, novo_fmt), onde:
      - Itens removidos   → (repr_item, '')
      - Itens adicionados → ('', repr_item)

    Cada tupla representa um INSERT separado no histórico.
    Se nada mudou, retorna lista vazia.
    """
    repr_fn = _get_repr_fn(campo)

    lista_antiga = parse_json_list(val_antigo)
    lista_nova   = parse_json_list(val_novo)

    set_antigas = {
        repr_fn(o)
        for o in lista_antiga
        if isinstance(o, dict)
    }
    set_novas = {
        repr_fn(o)
        for o in lista_nova
        if isinstance(o, dict)
    }

    removidas   = set_antigas - set_novas   # estavam antes e não estão depois
    adicionadas = set_novas   - set_antigas # não estavam antes e agora estão

    resultado = []

    # Itens removidos: antigo=repr, novo=''
    for repr_item in sorted(removidas):
        resultado.append((repr_item, ''))

    # Itens adicionados: antigo='', novo=repr
    for repr_item in sorted(adicionadas):
        resultado.append(('', repr_item))

    return resultado


# ─────────────────────────────────────────────
# FUNÇÃO AUXILIAR — INSERT único no histórico
# ─────────────────────────────────────────────

def _inserir_historico(cursor,
                       re_user: str,
                       name_user: str,
                       tabela: str,
                       id_registro: int,
                       campo: str,
                       antigo: str,
                       novo: str,
                       operacao: str):
    """
    Executa um único INSERT na tabela historico.
    A operação é ajustada automaticamente:
      - DELETE: antigo != '' e novo == ''
      - INSERT: antigo == '' e novo != ''
      - UPDATE: antigo != '' e novo != '' (ou qualquer outro caso padrão)
    """
    # Normaliza para string
    antigo_str = antigo if antigo is not None else ''
    novo_str   = novo   if novo   is not None else ''

    # Decide operação real
    if antigo_str and not novo_str:
        op_real = 'DELETE'
    elif not antigo_str and novo_str:
        op_real = 'INSERT'
    else:
        op_real = operacao or 'UPDATE'

    sql = """
        INSERT INTO historico (
            usuario_re_historico,
            usuario_nome_historico,
            tabela_afetada_historico,
            id_registro_afetado_historico,
            campo_alterado_historico,
            valor_antigo_historico,
            valor_novo_historico,
            operacao_historico
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    cursor.execute(sql, (
        re_user,
        name_user,
        tabela,
        id_registro,
        campo,
        antigo_str,
        novo_str,
        op_real
    ))

# ─────────────────────────────────────────────
# FUNÇÃO PRINCIPAL
# ─────────────────────────────────────────────

def registrar_log(conn,
                  tabela_afetada_historico: str,
                  id_registro_afetado_historico: int,
                  campo_alterado_historico: str,
                  valor_antigo_historico,
                  valor_novo_historico,
                  operacao_historico: str):
    """
    Insere linhas em historico (tabela de auditoria).

    Comportamento para campos JSON (lista de dicts):
      - Cada item alterado gera um INSERT separado.
      - Representação com ordem fixa de chaves (_CHAVES_ORDENADAS) para
        evitar falsos positivos causados por variação de ordem no JSON.
      - Valores exibidos sem nomes de chaves.
      - Itens sem alteração real são ignorados.

    Comportamento para campos escalares:
      - Um único INSERT com valor convertido para string.

    O commit é responsabilidade do chamador.
    """

    re_user   = getattr(current_user, 're_user', None)   or session.get('re_usuario')
    name_user = getattr(current_user, 'nome_user', None) or session.get('nome_usuario')

    é_json = _is_json_list(valor_antigo_historico) or _is_json_list(valor_novo_historico)

    try:
        with conn.cursor() as c:

            if é_json:
                try:
                    diffs = _diff_json_list(
                        campo_alterado_historico,
                        valor_antigo_historico,
                        valor_novo_historico
                    )
                    # Nenhuma diferença real — não grava nada
                    if not diffs:
                        return

                    # Um INSERT por item alterado
                    for antigo_fmt, novo_fmt in diffs:
                        _inserir_historico(
                            c,
                            re_user, name_user,
                            tabela_afetada_historico,
                            id_registro_afetado_historico,
                            campo_alterado_historico,
                            antigo_fmt,
                            novo_fmt,
                            operacao_historico
                        )

                except Exception as e:
                    logging.error(
                        f"[registrar_log] Erro ao processar JSON do campo "
                        f"'{campo_alterado_historico}': {e}"
                    )
                    # fallback: grava o valor cru em um único INSERT
                    _inserir_historico(
                        c,
                        re_user, name_user,
                        tabela_afetada_historico,
                        id_registro_afetado_historico,
                        campo_alterado_historico,
                        str(valor_antigo_historico) if valor_antigo_historico is not None else '',
                        str(valor_novo_historico)   if valor_novo_historico   is not None else '',
                        operacao_historico
                    )

            else:
                # Campo escalar — um único INSERT
                _inserir_historico(
                    c,
                    re_user, name_user,
                    tabela_afetada_historico,
                    id_registro_afetado_historico,
                    campo_alterado_historico,
                    str(valor_antigo_historico) if valor_antigo_historico is not None else '',
                    str(valor_novo_historico)   if valor_novo_historico   is not None else '',
                    operacao_historico
                )

    except Exception as e:
        logging.error(
            f"[registrar_log] Erro ao inserir no histórico | "
            f"tabela={tabela_afetada_historico} | "
            f"id={id_registro_afetado_historico} | "
            f"campo={campo_alterado_historico} | "
            f"Erro: {e}"
        )
        raise


def registrar_logs_lote(
    conn,
    entries: list[tuple],
    *,
    re_user: str | None = None,
    name_user: str | None = None,
) -> None:
    """
    Insere vários registros de auditoria em uma única operação (CSV em lote).
    Cada item: (tabela, id_registro, campo, antigo, novo, operacao).
    """
    if not entries:
        return

    re_user = re_user or getattr(current_user, "re_user", None) or session.get("re_usuario")
    name_user = name_user or getattr(current_user, "nome_user", None) or session.get("nome_usuario")

    rows: list[tuple] = []
    for tabela, id_registro, campo, antigo, novo, operacao in entries:
        antigo_str = "" if antigo is None else str(antigo)
        novo_str = "" if novo is None else str(novo)
        if antigo_str and not novo_str:
            op_real = "DELETE"
        elif not antigo_str and novo_str:
            op_real = "INSERT"
        else:
            op_real = operacao or "UPDATE"
        rows.append(
            (
                re_user,
                name_user,
                tabela,
                id_registro,
                campo,
                antigo_str,
                novo_str,
                op_real,
            )
        )

    sql = """
        INSERT INTO historico (
            usuario_re_historico,
            usuario_nome_historico,
            tabela_afetada_historico,
            id_registro_afetado_historico,
            campo_alterado_historico,
            valor_antigo_historico,
            valor_novo_historico,
            operacao_historico
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    try:
        with conn.cursor() as c:
            c.executemany(sql, rows)
    except Exception as e:
        logging.error("[registrar_logs_lote] Erro ao inserir histórico em lote: %s", e)
        raise