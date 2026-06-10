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
def test_redact_sql(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test_redact_sql.db")
    result = cli_runner(
        [
            connection,
            db_path,
            "--sql",
            "select name, cat_id from products",
            "--output",
            "out",
            "--redact",
            "out",
            "name",
        ]
    )
    assert 0 == result.exit_code, (result.output, result.exception)
    db = sqlite_utils.Database(db_path)
    assert [
        {"name": "***", "cat_id": 1},
        {"name": "***", "cat_id": 1},
    ] == list(db["out"].rows)


@all_databases
def test_redact_sql_alias(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test_redact_sql_alias.db")
    result = cli_runner(
        [
            connection,
            db_path,
            "--sql",
            "select name as product_name, cat_id from products",
            "--output",
            "out",
            "--redact",
            "out",
            "product_name",
        ]
    )
    assert 0 == result.exit_code, (result.output, result.exception)
    db = sqlite_utils.Database(db_path)
    assert [
        {"product_name": "***", "cat_id": 1},
        {"product_name": "***", "cat_id": 1},
    ] == list(db["out"].rows)


@all_databases
def test_redact_sql_empty(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test_redact_sql_empty.db")
    result = cli_runner(
        [
            connection,
            db_path,
            "--sql",
            "select name from products where id = 999",
            "--output",
            "out",
            "--redact",
            "out",
            "name",
        ]
    )
    assert 0 == result.exit_code, (result.output, result.exception)
