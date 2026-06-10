"""Tests for empty table and empty query handling using SQLite as source.

These tests don't require MySQL or PostgreSQL.
"""
import sqlite3

import sqlite_utils

from click.testing import CliRunner

from db_to_sqlite import cli


def _create_source_db(path):
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE populated (
            id INTEGER PRIMARY KEY NOT NULL,
            name TEXT NOT NULL
        );
        INSERT INTO populated (id, name) VALUES (1, 'Alice');

        CREATE TABLE empty_single_pk (
            id INTEGER PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            note TEXT
        );

        CREATE TABLE empty_compound_pk (
            alpha INTEGER NOT NULL,
            bravo INTEGER NOT NULL,
            PRIMARY KEY (alpha, bravo)
        );

        CREATE TABLE empty_no_pk (
            x TEXT NOT NULL,
            y TEXT
        );
        """
    )
    conn.close()


def test_empty_table_preserves_primary_key(tmpdir):
    src = tmpdir / "source.db"
    dst = str(tmpdir / "dest.db")
    _create_source_db(src)
    result = CliRunner().invoke(
        cli.cli,
        ["sqlite:///{}".format(src), dst, "--table", "empty_single_pk"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    db = sqlite_utils.Database(dst)
    assert db["empty_single_pk"].exists()
    assert db["empty_single_pk"].pks == ["id"]
    assert [] == list(db["empty_single_pk"].rows)


def test_empty_table_preserves_not_null(tmpdir):
    src = tmpdir / "source.db"
    dst = str(tmpdir / "dest.db")
    _create_source_db(src)
    result = CliRunner().invoke(
        cli.cli,
        ["sqlite:///{}".format(src), dst, "--table", "empty_single_pk"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    db = sqlite_utils.Database(dst)
    not_null_cols = {
        col.name for col in db["empty_single_pk"].columns if col.notnull
    }
    assert "id" in not_null_cols
    assert "name" in not_null_cols
    assert "note" not in not_null_cols


def test_empty_table_preserves_compound_pk(tmpdir):
    src = tmpdir / "source.db"
    dst = str(tmpdir / "dest.db")
    _create_source_db(src)
    result = CliRunner().invoke(
        cli.cli,
        ["sqlite:///{}".format(src), dst, "--table", "empty_compound_pk"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    db = sqlite_utils.Database(dst)
    assert db["empty_compound_pk"].pks == ["alpha", "bravo"]
    assert [] == list(db["empty_compound_pk"].rows)


def test_empty_table_no_pk(tmpdir):
    src = tmpdir / "source.db"
    dst = str(tmpdir / "dest.db")
    _create_source_db(src)
    result = CliRunner().invoke(
        cli.cli,
        ["sqlite:///{}".format(src), dst, "--table", "empty_no_pk"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    db = sqlite_utils.Database(dst)
    assert db["empty_no_pk"].exists()
    assert db["empty_no_pk"].pks == ["rowid"]


def test_all_with_empty_tables(tmpdir):
    src = tmpdir / "source.db"
    dst = str(tmpdir / "dest.db")
    _create_source_db(src)
    result = CliRunner().invoke(
        cli.cli,
        ["sqlite:///{}".format(src), dst, "--all"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    db = sqlite_utils.Database(dst)
    assert {
        "populated",
        "empty_single_pk",
        "empty_compound_pk",
        "empty_no_pk",
    } == set(db.table_names())
    assert [{"id": 1, "name": "Alice"}] == list(db["populated"].rows)
    assert [] == list(db["empty_single_pk"].rows)


def test_populated_table_unaffected(tmpdir):
    src = tmpdir / "source.db"
    dst = str(tmpdir / "dest.db")
    _create_source_db(src)
    result = CliRunner().invoke(
        cli.cli,
        ["sqlite:///{}".format(src), dst, "--table", "populated"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    db = sqlite_utils.Database(dst)
    assert [{"id": 1, "name": "Alice"}] == list(db["populated"].rows)
    assert db["populated"].pks == ["id"]


def test_empty_sql_query_creates_table(tmpdir):
    src = tmpdir / "source.db"
    dst = str(tmpdir / "dest.db")
    _create_source_db(src)
    result = CliRunner().invoke(
        cli.cli,
        [
            "sqlite:///{}".format(src),
            dst,
            "--sql",
            "select id, name from populated where 1=0",
            "--output",
            "query_result",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    db = sqlite_utils.Database(dst)
    assert db["query_result"].exists()
    assert [] == list(db["query_result"].rows)
    assert ["id", "name"] == [col.name for col in db["query_result"].columns]


def test_empty_sql_query_with_pk(tmpdir):
    src = tmpdir / "source.db"
    dst = str(tmpdir / "dest.db")
    _create_source_db(src)
    result = CliRunner().invoke(
        cli.cli,
        [
            "sqlite:///{}".format(src),
            dst,
            "--sql",
            "select id, name from populated where 1=0",
            "--output",
            "query_result",
            "--pk",
            "id",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    db = sqlite_utils.Database(dst)
    assert db["query_result"].pks == ["id"]


def test_nonempty_sql_query_still_works(tmpdir):
    src = tmpdir / "source.db"
    dst = str(tmpdir / "dest.db")
    _create_source_db(src)
    result = CliRunner().invoke(
        cli.cli,
        [
            "sqlite:///{}".format(src),
            dst,
            "--sql",
            "select id, name from populated",
            "--output",
            "query_result",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    db = sqlite_utils.Database(dst)
    assert [{"id": 1, "name": "Alice"}] == list(db["query_result"].rows)
