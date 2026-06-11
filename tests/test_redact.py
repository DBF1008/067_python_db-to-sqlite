import pytest
import sqlite_utils
from sqlite_utils.db import ForeignKey

from .shared import all_databases


@all_databases
def test_redact(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test_redact.db")
    result = cli_runner(
        [
            connection,
            db_path,
            "--all",
            "--redact",
            "products",
            "name",
            "--redact",
            "products",
            "vendor_id",
        ]
    )
    assert 0 == result.exit_code, (result.output, result.exception)
    db = sqlite_utils.Database(db_path)
    assert [
        {"id": 1, "name": "***", "cat_id": 1, "vendor_id": "***", "price": None},
        {"id": 2, "name": "***", "cat_id": 1, "vendor_id": "***", "price": 2.1},
    ] == list(db["products"].rows)
    assert [
        ForeignKey(
            table="products",
            column="cat_id",
            other_table="categories",
            other_column="id",
        )
    ] == sorted(db["products"].foreign_keys)


@all_databases
def test_redact_sql_query(connection, tmpdir, cli_runner):
    """Redaction rules should apply to --sql query results by output table name."""
    db_path = str(tmpdir / "test_redact_sql.db")
    result = cli_runner(
        [
            connection,
            db_path,
            "--sql",
            "select name, cat_id, vendor_id from products",
            "--output",
            "my_output",
            "--redact",
            "my_output",
            "name",
            "--redact",
            "my_output",
            "vendor_id",
        ]
    )
    assert 0 == result.exit_code, (result.output, result.exception)
    db = sqlite_utils.Database(db_path)
    assert {"my_output"} == set(db.table_names())
    assert [
        {"name": "***", "cat_id": 1, "vendor_id": "***"},
        {"name": "***", "cat_id": 1, "vendor_id": "***"},
    ] == list(db["my_output"].rows)


@all_databases
def test_redact_sql_query_aliased_columns(connection, tmpdir, cli_runner):
    """Redaction should match on the final output column name, even when aliased."""
    db_path = str(tmpdir / "test_redact_alias.db")
    result = cli_runner(
        [
            connection,
            db_path,
            "--sql",
            "select name as product_name, cat_id as category from products",
            "--output",
            "report",
            "--redact",
            "report",
            "product_name",
        ]
    )
    assert 0 == result.exit_code, (result.output, result.exception)
    db = sqlite_utils.Database(db_path)
    assert {"report"} == set(db.table_names())
    assert [
        {"product_name": "***", "category": 1},
        {"product_name": "***", "category": 1},
    ] == list(db["report"].rows)


@all_databases
def test_redact_sql_query_empty_result(connection, tmpdir, cli_runner):
    """An empty query result should still create the output table, with redaction configured."""
    db_path = str(tmpdir / "test_redact_empty.db")
    result = cli_runner(
        [
            connection,
            db_path,
            "--sql",
            "select name, cat_id from products where 1=0",
            "--output",
            "empty_out",
            "--redact",
            "empty_out",
            "name",
        ]
    )
    assert 0 == result.exit_code, (result.output, result.exception)
    db = sqlite_utils.Database(db_path)
    assert "empty_out" in db.table_names()
    assert [] == list(db["empty_out"].rows)
    # Column names should still be present in the schema
    column_names = [c.name for c in db["empty_out"].columns]
    assert "name" in column_names
    assert "cat_id" in column_names


@all_databases
def test_redact_sql_query_no_redact_unchanged(connection, tmpdir, cli_runner):
    """SQL query without matching redact rules should leave data untouched."""
    db_path = str(tmpdir / "test_no_redact.db")
    result = cli_runner(
        [
            connection,
            db_path,
            "--sql",
            "select name, cat_id from products",
            "--output",
            "out",
            "--redact",
            "other_table",
            "name",
        ]
    )
    assert 0 == result.exit_code, (result.output, result.exception)
    db = sqlite_utils.Database(db_path)
    assert [
        {"name": "Bobcat Statue", "cat_id": 1},
        {"name": "Yoga Scarf", "cat_id": 1},
    ] == list(db["out"].rows)
