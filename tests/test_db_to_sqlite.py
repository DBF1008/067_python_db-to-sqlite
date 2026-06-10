import pytest
import sqlite_utils
from sqlite_utils.db import ForeignKey

from .shared import POSTGRESQL_TEST_DB_CONNECTION, all_databases, psycopg2


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


@all_databases
def test_views_with_all(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test.db")
    result = cli_runner([connection, db_path, "--all", "--include-views"])
    assert 0 == result.exit_code, result.output
    db = sqlite_utils.Database(db_path)
    assert "products_view" in set(db.table_names())
    assert [
        {"id": 1, "name": "Bobcat Statue", "cat_id": 1},
        {"id": 2, "name": "Yoga Scarf", "cat_id": 1},
    ] == list(db["products_view"].rows)


@all_databases
def test_specific_views(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test.db")
    result = cli_runner([connection, db_path, "--view", "products_view"])
    assert 0 == result.exit_code, result.output
    db = sqlite_utils.Database(db_path)
    assert {"products_view"} == set(db.table_names())
    assert [
        {"id": 1, "name": "Bobcat Statue", "cat_id": 1},
        {"id": 2, "name": "Yoga Scarf", "cat_id": 1},
    ] == list(db["products_view"].rows)


@all_databases
def test_view_table_name_conflict(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test.db")
    result = cli_runner(
        [connection, db_path, "--table", "products", "--view", "products", "-p"]
    )
    assert 0 == result.exit_code, result.output
    db = sqlite_utils.Database(db_path)
    products_rows = list(db["products"].rows)
    assert all("vendor_id" in row for row in products_rows)
    assert "skipping (table with same name exists)" in result.output


@all_databases
def test_include_views_without_all(connection, tmpdir, cli_runner):
    db_path = str(tmpdir / "test.db")
    result = cli_runner(
        [connection, db_path, "--table", "products", "--include-views"]
    )
    assert 0 != result.exit_code
    assert "--include-views can only be used with --all" in result.output


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
