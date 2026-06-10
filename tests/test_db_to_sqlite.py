import pytest
import sqlite_utils
from sqlite_utils.db import ForeignKey

from .shared import POSTGRESQL_TEST_DB_CONNECTION, all_databases, psycopg2

import json


@all_databases
def test_db_to_sqlite(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test.db")
    cli_runner([connection, db_path, "--all"])
    db = sqlite_utils.Database(db_path)
    assert {
        "categories",
        "products",
        "vendors",
        "vendor_categories",
        "user",
        "empty_table",
    } == set(db.table_names())
    assert [
        {"id": 1, "name": "Bobcat Statue", "cat_id": 1, "vendor_id": 1, "price": None},
        {"id": 2, "name": "Yoga Scarf", "cat_id": 1, "vendor_id": None, "price": 2.1},
    ] == list(db["products"].rows)
    assert [{"id": 1, "name": "Junk"}] == list(db["categories"].rows)
    assert [{"cat_id": 1, "vendor_id": 1}] == list(db["vendor_categories"].rows)
    assert [{"id": 1, "name": "Lila"}] == list(db["user"].rows)
    assert (
        db["empty_table"].schema
        == "CREATE TABLE [empty_table] (\n   [id] INTEGER,\n   [name] TEXT,\n   [ip] TEXT\n)"
    )
    # Check foreign keys
    assert [
        ForeignKey(
            table="products",
            column="cat_id",
            other_table="categories",
            other_column="id",
        ),
        ForeignKey(
            table="products",
            column="vendor_id",
            other_table="vendors",
            other_column="id",
        ),
    ] == sorted(db["products"].foreign_keys)
    # Confirm vendor_categories has a compound primary key
    assert db["vendor_categories"].pks == ["cat_id", "vendor_id"]


@all_databases
def test_index_fks(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test_with_fks.db")
    # With --no-index-fks should create no indexes
    cli_runner([connection, db_path, "--all", "--no-index-fks"])
    db = sqlite_utils.Database(db_path)
    assert [] == db["products"].indexes
    # Without it (the default) it should create the indexes
    cli_runner([connection, db_path, "--all"])
    db = sqlite_utils.Database(db_path)
    assert [["cat_id"], ["vendor_id"]] == [i.columns for i in db["products"].indexes]


@all_databases
def test_specific_tables(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test_specific_tables.db")
    result = cli_runner(
        [connection, db_path, "--table", "categories", "--table", "products", "-p"]
    )
    assert 0 == result.exit_code, result.output
    db = sqlite_utils.Database(db_path)
    assert {"categories", "products"} == set(db.table_names())
    assert (
        "1/2: categories\n\n2/2: products\n\n\nAdding 1 foreign key\n  products.cat_id => categories.id\n"
        == result.output
    )


@all_databases
def test_sql_query(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test_sql.db")
    # Without --output it throws an error
    result = cli_runner(
        [connection, db_path, "--sql", "select name, cat_id from products"]
    )
    assert 0 != result.exit_code
    assert "Error: --sql must be accompanied by --output" == result.output.strip()
    # With --output it does the right thing
    result = cli_runner(
        [
            connection,
            db_path,
            "--sql",
            "select name, cat_id from products",
            "--output",
            "out",
        ]
    )
    assert 0 == result.exit_code, result.output
    db = sqlite_utils.Database(db_path)
    assert {"out"} == set(db.table_names())
    assert [
        {"name": "Bobcat Statue", "cat_id": 1},
        {"name": "Yoga Scarf", "cat_id": 1},
    ] == list(db["out"].rows)


@pytest.mark.skipif(psycopg2 is None, reason="pip install psycopg2")
def test_postgres_schema(tmpdir, cli_runner):
    db_path = str(tmpdir / "test_sql.db")
    connection = POSTGRESQL_TEST_DB_CONNECTION
    result = cli_runner(
        [connection, db_path, "--all", "--postgres-schema", "other_schema"]
    )
    assert result.exit_code == 0
    db = sqlite_utils.Database(db_path)
    assert db.tables[0].schema == (
        "CREATE TABLE [other_schema_categories] (\n"
        "   [id] INTEGER PRIMARY KEY,\n"
        "   [name] TEXT\n"
        ")"
    )


@all_databases
def test_summary_text(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test.db")
    result = cli_runner([connection, db_path, "--all", "--summary"])
    assert 0 == result.exit_code, result.output
    output = result.output
    assert "--- Export Summary ---" in output
    assert "Tables copied:" in output
    assert "categories: 1 row" in output
    assert "products: 2 rows" in output
    assert "empty_table: 0 rows (empty)" in output
    assert "Foreign keys added:" in output
    assert "products.cat_id => categories.id" in output


@all_databases
def test_summary_json(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test.db")
    result = cli_runner([connection, db_path, "--all", "--summary-json"])
    assert 0 == result.exit_code, result.output
    data = json.loads(result.output)
    table_names = [t["name"] for t in data["tables"]]
    assert "categories" in table_names
    assert "products" in table_names
    assert "empty_table" in table_names
    products = [t for t in data["tables"] if t["name"] == "products"][0]
    assert products["rows"] == 2
    assert products["skipped"] is False
    assert products["empty"] is False
    empty = [t for t in data["tables"] if t["name"] == "empty_table"][0]
    assert empty["rows"] == 0
    assert empty["empty"] is True
    assert len(data["foreign_keys"]["added"]) > 0
    fk_added = data["foreign_keys"]["added"]
    assert any(
        fk["table"] == "products" and fk["column"] == "cat_id"
        for fk in fk_added
    )


@all_databases
def test_summary_json_sql(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test.db")
    result = cli_runner([
        connection, db_path,
        "--sql", "select name, cat_id from products",
        "--output", "out",
        "--summary-json",
    ])
    assert 0 == result.exit_code, result.output
    data = json.loads(result.output)
    assert data["sql"]["query"] == "select name, cat_id from products"
    assert data["sql"]["output_table"] == "out"
    assert data["sql"]["rows"] == 2
    assert data["tables"] == []


@all_databases
def test_summary_with_redact(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test.db")
    result = cli_runner([
        connection, db_path, "--all",
        "--redact", "products", "name",
        "--redact", "products", "vendor_id",
        "--summary-json",
    ])
    assert 0 == result.exit_code, result.output
    data = json.loads(result.output)
    products = [t for t in data["tables"] if t["name"] == "products"][0]
    assert sorted(products["redacted_columns"]) == ["name", "vendor_id"]
    skipped_fks = data["foreign_keys"]["skipped"]
    assert any(
        fk["table"] == "products"
        and fk["column"] == "vendor_id"
        and fk["reason"] == "column_redacted"
        for fk in skipped_fks
    )


@all_databases
def test_summary_with_skip(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test.db")
    result = cli_runner([
        connection, db_path, "--all",
        "--skip", "empty_table",
        "--summary-json",
    ])
    assert 0 == result.exit_code, result.output
    data = json.loads(result.output)
    empty = [t for t in data["tables"] if t["name"] == "empty_table"][0]
    assert empty["skipped"] is True
    assert empty["rows"] == 0
    copied = [t for t in data["tables"] if not t["skipped"]]
    assert len(copied) >= 4


@all_databases
def test_summary_default_unchanged(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test.db")
    result = cli_runner([connection, db_path, "--all"])
    assert 0 == result.exit_code
    assert "Export Summary" not in result.output
    assert result.output == ""
