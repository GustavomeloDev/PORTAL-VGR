"""
Migração PRODESP: criptografa registros existentes (Fernet / FERNET_TECH_KEY).

Pré-requisito SQL: prodesp/sql/009_sensitive_fields_varchar255.sql

Uso (na raiz do repositório, venv ativo):
    python prodesp/migrations/migrate_encrypt_sensitive_fields.py --dry-run
    python prodesp/migrations/migrate_encrypt_sensitive_fields.py

GMUD: rodar dry-run em homolog → aplicar 009 SQL → rodar script → validar portal.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from dotenv import load_dotenv

load_dotenv(override=True)

import core.security.encryption as _enc_mod

_enc_mod._FERNET_CACHE = None

import mysql.connector
from prodesp.credentials.db_config import db_config
from prodesp.prodesp.sensitive_fields_crypto import ensure_encrypted_db_column

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATABASE = os.getenv("PRODESP_MYSQL_DATABASE", "prodesp_db")

BATCHES = (
    (
        "atendimentos",
        "id_atendimentos",
        ("contato_field_atendimentos",),
        "SELECT id_atendimentos, contato_field_atendimentos FROM atendimentos "
        "WHERE contato_field_atendimentos IS NOT NULL AND TRIM(contato_field_atendimentos) <> ''",
    ),
    (
        "unidades",
        "id_unidades",
        ("telefone_contato_unidades", "contato_field_planejada_unidades"),
        "SELECT id_unidades, telefone_contato_unidades, contato_field_planejada_unidades FROM unidades "
        "WHERE (telefone_contato_unidades IS NOT NULL AND TRIM(telefone_contato_unidades) <> '') "
        "   OR (contato_field_planejada_unidades IS NOT NULL AND TRIM(contato_field_planejada_unidades) <> '')",
    ),
    (
        "links",
        "id_link",
        ("pppoe_user_links", "pppoe_pass_links"),
        "SELECT id_link, pppoe_user_links, pppoe_pass_links FROM links "
        "WHERE (pppoe_user_links IS NOT NULL AND TRIM(pppoe_user_links) <> '') "
        "   OR (pppoe_pass_links IS NOT NULL AND TRIM(pppoe_pass_links) <> '')",
    ),
)


def _conn():
    cfg = dict(db_config)
    cfg["database"] = DATABASE
    return mysql.connector.connect(**cfg)


def run(dry_run: bool = False, verbose: bool = False) -> None:
    if not os.getenv("FERNET_TECH_KEY"):
        logger.error("FERNET_TECH_KEY ausente no .env — abortando.")
        sys.exit(1)

    conn = _conn()
    cursor = conn.cursor(dictionary=True)
    total_updated = 0
    total_skipped = 0

    try:
        for table, pk, columns, query in BATCHES:
            cursor.execute(query)
            rows = cursor.fetchall()
            table_updated = 0
            table_skipped = 0
            logger.info("%s: %s registro(s) candidatos", table, len(rows))

            for idx, row in enumerate(rows, start=1):
                pk_val = row[pk]
                updates: dict[str, str] = {}
                for col in columns:
                    raw = row.get(col)
                    if raw is None or not str(raw).strip():
                        continue
                    enc = ensure_encrypted_db_column(col, raw)
                    if enc is None or str(enc) == str(raw):
                        continue
                    updates[col] = enc

                if not updates:
                    table_skipped += 1
                    continue

                set_clause = ", ".join(f"`{c}` = %s" for c in updates)
                sql = f"UPDATE `{table}` SET {set_clause} WHERE `{pk}` = %s"
                params = list(updates.values()) + [pk_val]

                if verbose:
                    logger.info(
                        "[%s] %s id=%s → %s",
                        "DRY-RUN" if dry_run else "UPDATE",
                        table,
                        pk_val,
                        list(updates.keys()),
                    )
                elif idx % 100 == 0:
                    logger.info("%s: processados %s/%s", table, idx, len(rows))

                if not dry_run:
                    cursor.execute(sql, params)
                table_updated += 1

            total_updated += table_updated
            total_skipped += table_skipped
            logger.info(
                "%s: %s atualizado(s), %s sem mudança",
                table,
                table_updated,
                table_skipped,
            )

        if dry_run:
            conn.rollback()
            logger.info(
                "DRY-RUN concluído (nenhuma alteração gravada). Total: %s atualizado(s), %s sem mudança.",
                total_updated,
                total_skipped,
            )
        else:
            conn.commit()
            logger.info(
                "Migração concluída: %s registro(s) atualizados, %s sem mudança.",
                total_updated,
                total_skipped,
            )
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Criptografa campos sensíveis PRODESP existentes.")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem gravar no banco.")
    parser.add_argument("--verbose", action="store_true", help="Loga cada registro alterado.")
    args = parser.parse_args()
    run(dry_run=args.dry_run, verbose=args.verbose)
