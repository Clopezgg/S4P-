#!/usr/bin/env python3
"""Read-only, fail-closed parity verification for an S4P PostgreSQL migration.

Run from an authorized private environment with both secret DSNs injected as
environment variables. No schema or data is ever modified by this command.
A healthy HTTP endpoint does NOT replace this row-level check.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Mapping
from urllib.parse import parse_qs, urlsplit

import psycopg
from psycopg import sql

REQUIRED_TABLES = frozenset({"companies", "users", "projects", "accounting_documents", "journal_lines", "alembic_version"})
MONEY_COLUMNS = {
    "journal_lines": ("debit_amount", "credit_amount"),
    "remittances": ("original_amount", "base_amount"),
    "general_expenses": ("amount",),
    "treasury_transfers": ("amount",),
}


def _parse_dsn(raw: str, label: str) -> tuple[str, tuple[str, int, str]]:
    if not raw:
        raise ValueError(f"{label} database DSN missing from secure environment")
    dsn = raw.replace("postgresql+psycopg://", "postgresql://", 1)
    parts = urlsplit(dsn)
    if parts.scheme not in {"postgres", "postgresql"} or not all(
        (parts.hostname, parts.username, parts.password, parts.path.strip("/"))
    ):
        raise ValueError(f"{label} database DSN is incomplete")
    ssl = parse_qs(parts.query).get("sslmode", [None])[0]
    if parts.hostname not in {"localhost", "127.0.0.1", "::1"} and ssl != "require":
        raise ValueError(f"{label} remote database DSN must explicitly require TLS")
    return dsn, (parts.hostname, parts.port or 5432, parts.path.strip("/"))


def _public_tables(conn: psycopg.Connection) -> list[str]:
    return [name for (name,) in conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
    ).fetchall()]


def _primary_key(conn: psycopg.Connection, table: str) -> list[str]:
    return [name for (name,) in conn.execute(
        "SELECT kcu.column_name FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "ON kcu.constraint_catalog=tc.constraint_catalog "
        "AND kcu.constraint_schema=tc.constraint_schema "
        "AND kcu.constraint_name=tc.constraint_name "
        "AND kcu.table_name=tc.table_name "
        "WHERE tc.table_schema='public' AND tc.table_name=%s "
        "AND tc.constraint_type='PRIMARY KEY' ORDER BY kcu.ordinal_position",
        (table,),
    ).fetchall()]


def _full_table_digest(conn: psycopg.Connection, table: str) -> tuple[int, str]:
    """Content digest for every row, ordered by the primary key.

    Uses Decimal and UUID representations without converting money to float.
    Tables without a PK are sorted by a JSON representation; duplicate rows
    remain in the stream and cannot disappear unnoticed.
    """
    columns = [c for (c,) in conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
        (table,),
    )]
    pks = _primary_key(conn, table)
    query = sql.SQL("SELECT * FROM {}.{}").format(sql.Identifier("public"), sql.Identifier(table))
    if pks:
        query += sql.SQL(" ORDER BY ") + sql.SQL(", ").join(map(sql.Identifier, pks))
    else:
        query += sql.SQL(" ORDER BY md5(row_to_json({})::text)").format(sql.Identifier(table))
    cursor = conn.cursor(name="s4p_parity_" + hashlib.sha1(table.encode()).hexdigest()[:12])
    cursor.execute(query)
    digest = hashlib.sha256()
    count = 0
    try:
        while rows := cursor.fetchmany(500):
            for row in rows:
                record = dict(zip(columns, row, strict=True))
                payload = json.dumps(
                    record, default=str, sort_keys=True, ensure_ascii=False,
                    separators=(",", ":"), allow_nan=False,
                ).encode("utf-8")
                digest.update(len(payload).to_bytes(8, "big"))
                digest.update(payload)
                count += 1
    finally:
        cursor.close()
    return count, digest.hexdigest()


def _money_totals(conn: psycopg.Connection, tables: set[str]) -> dict[str, tuple[str, ...]]:
    totals: dict[str, tuple[str, ...]] = {}
    for table, fields in MONEY_COLUMNS.items():
        if table not in tables:
            continue
        expr = sql.SQL(", ").join(
            sql.SQL("COALESCE(SUM({}), 0)::text").format(sql.Identifier(field))
            for field in fields
        )
        row = conn.execute(
            sql.SQL("SELECT {} FROM {}.{}").format(
                expr, sql.Identifier("public"), sql.Identifier(table)
            )
        ).fetchone()
        totals[table] = tuple(row or ())
    return totals


def _invalid_posted_documents(conn: psycopg.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM ("
        "SELECT d.id FROM public.accounting_documents d "
        "JOIN public.journal_lines l ON l.accounting_document_id=d.id "
        "WHERE d.status IN ('POSTED','REVERSED') GROUP BY d.id "
        "HAVING SUM(l.debit_amount) <> SUM(l.credit_amount)"
        ") unbalanced"
    ).fetchone()
    return int(row[0]) if row else 0


def _snapshot(conn: psycopg.Connection) -> dict:
    conn.execute("SET TRANSACTION READ ONLY")
    conn.execute("SET TIME ZONE 'UTC'")
    tables = _public_tables(conn)
    missing = REQUIRED_TABLES - set(tables)
    if missing:
        raise ValueError("Business schema missing mandatory tables: " + ", ".join(sorted(missing)))
    rows = {table: _full_table_digest(conn, table) for table in tables}
    versions = tuple(sorted(v for (v,) in conn.execute("SELECT version_num FROM public.alembic_version")))
    if len(versions) != 1:
        raise ValueError("Exactly one Alembic head must be installed")
    unbalanced = _invalid_posted_documents(conn)
    return {
        "tables": rows,
        "alembic": versions,
        "money": _money_totals(conn, set(tables)),
        "unbalanced_posted_documents": unbalanced,
    }


def compare_snapshots(source: Mapping, target: Mapping) -> list[str]:
    errors: list[str] = []
    for category in ("tables", "alembic", "money"):
        if source[category] != target[category]:
            if category == "tables":
                all_names = set(source["tables"]) | set(target["tables"])
                bad = sorted(name for name in all_names if source["tables"].get(name) != target["tables"].get(name))
                errors.append(f"Tables or complete row digests differ: {', '.join(bad)}")
            else:
                errors.append(f"{category} differs")
    if source["unbalanced_posted_documents"] != 0 or target["unbalanced_posted_documents"] != 0:
        errors.append("At least one posted/reversed accounting document is unbalanced")
    return errors


def main() -> int:
    try:
        source_url, source_id = _parse_dsn(os.environ.get("S4P_SOURCE_DATABASE_URL", ""), "Source")
        target_url, target_id = _parse_dsn(os.environ.get("S4P_TARGET_DATABASE_URL", ""), "Target")
        if source_id == target_id:
            raise ValueError("Source and target database identities are equal")
        with psycopg.connect(source_url, connect_timeout=20) as source:
            source_snapshot = _snapshot(source)
        with psycopg.connect(target_url, connect_timeout=20) as target:
            target_snapshot = _snapshot(target)
        problems = compare_snapshots(source_snapshot, target_snapshot)
        if problems:
            for problem in problems:
                print("BLOCKED: " + problem, file=sys.stderr)
            return 1
        table_count = len(source_snapshot["tables"])
        row_count = sum(count for count, _ in source_snapshot["tables"].values())
        print(f"PASS: {table_count} public tables; {row_count} rows; "
              "full-row digests, Alembic, monetary totals and posting balance match.")
        print("READ-ONLY parity only. Production DATABASE_URL was not modified.")
        return 0
    except Exception as exc:
        # Never render DSNs, credentials or SQL error values in CI/logs.
        print(f"BLOCKED: parity verification could not finish ({type(exc).__name__}).",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
