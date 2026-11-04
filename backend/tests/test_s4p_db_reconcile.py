"""Pure regression tests for fail-closed production DB parity decisions."""
import sqlite3

from s4p_db_reconcile import _invalid_posted_documents, _parse_dsn, compare_snapshots


def _baseline():
    return {
        "tables": {
            "companies": (1, "aaaa"),
            "users": (3, "bbbb"),
            "journal_lines": (2, "cccc"),
        },
        "alembic": ("newest",),
        "money": {"journal_lines": ("10.00", "10.00")},
        "unbalanced_posted_documents": 0,
    }


def test_identical_snapshot_passes():
    assert compare_snapshots(_baseline(), _baseline()) == []


def test_full_row_digest_detects_mutation_with_same_counts():
    source = _baseline()
    target = _baseline()
    target["tables"]["journal_lines"] = (2, "altered")
    assert any("journal_lines" in problem for problem in compare_snapshots(source, target))


def test_monetary_difference_blocks_cutover():
    target = _baseline()
    target["money"]["journal_lines"] = ("10.00", "11.00")
    assert "money differs" in compare_snapshots(_baseline(), target)


def test_unbalanced_posted_document_blocks_cutover():
    target = _baseline()
    target["unbalanced_posted_documents"] = 1
    assert any("unbalanced" in x for x in compare_snapshots(_baseline(), target))


def test_remote_database_requires_tls():
    try:
        _parse_dsn("postgresql://user:fake@db.example.com:5432/postgres", "Source")
    except ValueError as error:
        assert "TLS" in str(error)
    else:
        raise AssertionError("Unencrypted remote Postgres DSN accepted")


def test_reject_missing_credentials():
    try:
        _parse_dsn("postgresql://user@localhost:5432/db", "Target")
    except ValueError:
        pass
    else:
        raise AssertionError("Incomplete DSN accepted")


def _accounting_db():
    """Exercise the actual read-only balance SQL with an isolated in-memory DB."""
    connection = sqlite3.connect(":memory:")
    connection.execute("ATTACH DATABASE ':memory:' AS public")
    connection.execute(
        "CREATE TABLE public.accounting_documents (id TEXT PRIMARY KEY, status TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE public.journal_lines ("
        "accounting_document_id TEXT NOT NULL, debit_amount INTEGER, credit_amount INTEGER)"
    )
    return connection


def test_posted_document_without_lines_blocks_cutover():
    with _accounting_db() as db:
        db.execute("INSERT INTO public.accounting_documents VALUES ('empty', 'POSTED')")
        assert _invalid_posted_documents(db) == 1


def test_reversed_document_without_lines_blocks_cutover():
    with _accounting_db() as db:
        db.execute("INSERT INTO public.accounting_documents VALUES ('empty', 'REVERSED')")
        assert _invalid_posted_documents(db) == 1


def test_balanced_journal_and_unposted_draft_do_not_trigger_false_positive():
    with _accounting_db() as db:
        db.executemany(
            "INSERT INTO public.accounting_documents VALUES (?, ?)",
            [("balanced", "POSTED"), ("draft", "DRAFT")],
        )
        db.executemany(
            "INSERT INTO public.journal_lines VALUES (?, ?, ?)",
            [("balanced", 100, 0), ("balanced", 0, 100)],
        )
        assert _invalid_posted_documents(db) == 0


def test_unbalanced_posted_journal_blocks_cutover():
    with _accounting_db() as db:
        db.execute("INSERT INTO public.accounting_documents VALUES ('bad', 'POSTED')")
        db.execute("INSERT INTO public.journal_lines VALUES ('bad', 100, 0)")
        assert _invalid_posted_documents(db) == 1
