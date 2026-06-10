import itertools
import json

import click
from sqlalchemy import create_engine, inspect, text
from sqlite_utils import Database


@click.command()
@click.version_option()
@click.argument("connection")
@click.argument("path", type=click.Path(exists=False), required=True)
@click.option("--all", help="Detect and copy all tables", is_flag=True)
@click.option("--table", help="Specific tables to copy", multiple=True)
@click.option("--skip", help="When using --all skip these tables", multiple=True)
@click.option(
    "--redact",
    help="(table, column) pairs to redact with ***",
    nargs=2,
    type=str,
    multiple=True,
)
@click.option("--sql", help="Optional SQL query to run")
@click.option("--output", help="Table in which to save --sql query results")
@click.option("--pk", help="Optional column to use as a primary key")
@click.option(
    "--index-fks/--no-index-fks",
    default=True,
    help="Should foreign keys have indexes? Default on",
)
@click.option("-p", "--progress", help="Show progress bar", is_flag=True)
@click.option("--summary", help="Show a human-readable export summary on stderr", is_flag=True)
@click.option("--summary-json", help="Output export summary as JSON to stdout", is_flag=True)
@click.option("--postgres-schema", help="PostgreSQL schema to use")
def cli(
    connection,
    path,
    all,
    table,
    skip,
    redact,
    sql,
    output,
    pk,
    index_fks,
    progress,
    summary,
    summary_json,
    postgres_schema,
):
    """
    Load data from any database into SQLite.

    PATH is a path to the SQLite file to create, e.c. /tmp/my_database.db

    CONNECTION is a SQLAlchemy connection string, for example:

        postgresql://localhost/my_database
        postgresql://username:passwd@localhost/my_database

        mysql://root@localhost/my_database
        mysql://username:passwd@localhost/my_database

    More: https://docs.sqlalchemy.org/en/13/core/engines.html#database-urls
    """
    if not all and not table and not sql:
        raise click.ClickException("--all OR --table OR --sql required")
    if skip and not all:
        raise click.ClickException("--skip can only be used with --all")
    redact_columns = {}
    for table_name, column_name in redact:
        redact_columns.setdefault(table_name, set()).add(column_name)
    summary_data = {
        "tables": [],
        "foreign_keys": {"added": [], "skipped": []},
        "sql": None,
    }
    db = Database(path)
    if postgres_schema:
        conn_args = {"options": "-csearch_path={}".format(postgres_schema)}
    else:
        conn_args = {}
    if connection.startswith("postgres://"):
        connection = connection.replace("postgres://", "postgresql://")
    db_conn = create_engine(connection, connect_args=conn_args).connect()
    inspector = inspect(db_conn)
    # Figure out which tables we are copying, if any
    tables = table
    if all:
        tables = inspector.get_table_names()
    if tables:
        foreign_keys_to_add = []
        for i, table in enumerate(tables):
            if progress:
                click.echo("{}/{}: {}".format(i + 1, len(tables), table), err=True)
            if table in skip:
                if progress:
                    click.echo("  ... skipping", err=True)
                if summary or summary_json:
                    summary_data["tables"].append({
                        "name": table,
                        "rows": 0,
                        "skipped": True,
                        "empty": False,
                        "redacted_columns": [],
                    })
                continue
            pks = inspector.get_pk_constraint(table)["constrained_columns"]
            if len(pks) == 1:
                pks = pks[0]
            fks = inspector.get_foreign_keys(table)
            foreign_keys_to_add.extend(
                [
                    (
                        # table, column, other_table, other_column
                        table,
                        fk["constrained_columns"][0],
                        fk["referred_table"],
                        fk["referred_columns"][0],
                    )
                    for fk in fks
                ]
            )
            count = None
            table_quoted = db_conn.dialect.identifier_preparer.quote_identifier(table)
            if progress:
                count = db_conn.execute(
                    text("select count(*) from {}".format(table_quoted))
                ).fetchone()[0]
            results = db_conn.execute(text("select * from {}".format(table_quoted)))
            redact_these = redact_columns.get(table) or set()
            rows = (redacted_dict(r, redact_these) for r in results)
            # Make sure generator is not empty
            try:
                first = next(rows)
            except StopIteration:
                # This is an empty table - create an empty copy
                if not db[table].exists():
                    create_columns = {}
                    for column in inspector.get_columns(table):
                        try:
                            column_type = column["type"].python_type
                        except NotImplementedError:
                            column_type = str
                        create_columns[column["name"]] = column_type
                    db[table].create(create_columns)
                if summary or summary_json:
                    summary_data["tables"].append({
                        "name": table,
                        "rows": 0,
                        "skipped": False,
                        "empty": True,
                        "redacted_columns": sorted(redact_these),
                    })
            else:
                rows = itertools.chain([first], rows)
                if summary or summary_json:
                    rows = RowCounter(rows)
                if progress:
                    with click.progressbar(rows, length=count) as bar:
                        db[table].insert_all(bar, pk=pks, replace=True)
                else:
                    db[table].insert_all(rows, pk=pks, replace=True)
                if summary or summary_json:
                    summary_data["tables"].append({
                        "name": table,
                        "rows": rows.count,
                        "skipped": False,
                        "empty": False,
                        "redacted_columns": sorted(redact_these),
                    })
        foreign_keys_to_add_final = []
        for table, column, other_table, other_column in foreign_keys_to_add:
            reason = None
            if not db[table].exists():
                reason = "source_table_missing"
            elif table in skip:
                reason = "source_table_skipped"
            elif not db[other_table].exists():
                reason = "referred_table_missing"
            elif other_table in skip:
                reason = "referred_table_skipped"
            elif (table, column) in redact:
                reason = "column_redacted"
            if reason is None:
                foreign_keys_to_add_final.append(
                    (table, column, other_table, other_column)
                )
                if summary or summary_json:
                    summary_data["foreign_keys"]["added"].append({
                        "table": table,
                        "column": column,
                        "other_table": other_table,
                        "other_column": other_column,
                    })
            elif summary or summary_json:
                summary_data["foreign_keys"]["skipped"].append({
                    "table": table,
                    "column": column,
                    "other_table": other_table,
                    "other_column": other_column,
                    "reason": reason,
                })
        if foreign_keys_to_add_final:
            # Add using .add_foreign_keys() to avoid running multiple VACUUMs
            if progress:
                click.echo(
                    "\nAdding {} foreign key{}\n{}".format(
                        len(foreign_keys_to_add_final),
                        "s" if len(foreign_keys_to_add_final) != 1 else "",
                        "\n".join(
                            "  {}.{} => {}.{}".format(*fk)
                            for fk in foreign_keys_to_add_final
                        ),
                    ),
                    err=True,
                )
            db.add_foreign_keys(foreign_keys_to_add_final)
    if sql:
        if not output:
            raise click.ClickException("--sql must be accompanied by --output")
        results = db_conn.execute(text(sql))
        rows = (dict(r._mapping) for r in results)
        if summary or summary_json:
            rows = RowCounter(rows)
        db[output].insert_all(rows, pk=pk)
        if summary or summary_json:
            summary_data["sql"] = {
                "query": sql,
                "output_table": output,
                "rows": rows.count,
            }
    if index_fks:
        db.index_foreign_keys()
    if summary:
        click.echo(_format_text_summary(summary_data), err=True)
    if summary_json:
        click.echo(json.dumps(summary_data, indent=2))


def detect_primary_key(db_conn, table):
    inspector = inspect(db_conn)
    pks = inspector.get_pk_constraint(table)["constrained_columns"]
    if len(pks) > 1:
        raise click.ClickException("Multiple primary keys not currently supported")
    return pks[0] if pks else None


def redacted_dict(row, redact):
    d = dict(row._mapping)
    for key in redact:
        if key in d:
            d[key] = "***"
    return d


class RowCounter:
    def __init__(self, iterator):
        self.count = 0
        self._iterator = iterator

    def __iter__(self):
        for row in self._iterator:
            self.count += 1
            yield row


def _format_text_summary(data):
    lines = ["--- Export Summary ---"]
    tables = data.get("tables", [])
    if tables:
        copied = [t for t in tables if not t["skipped"]]
        skipped = [t for t in tables if t["skipped"]]
        lines.append("Tables copied: {}".format(len(copied)))
        for t in copied:
            suffix = ""
            if t["empty"]:
                suffix = " (empty)"
            elif t["redacted_columns"]:
                suffix = " (redacted: {})".format(", ".join(t["redacted_columns"]))
            row_word = "row" if t["rows"] == 1 else "rows"
            lines.append("  {}: {} {}{}".format(t["name"], t["rows"], row_word, suffix))
        if skipped:
            lines.append("Tables skipped: {}".format(len(skipped)))
            for t in skipped:
                lines.append("  {}".format(t["name"]))
    fks = data.get("foreign_keys", {})
    added = fks.get("added", [])
    skipped_fks = fks.get("skipped", [])
    if added:
        lines.append("Foreign keys added: {}".format(len(added)))
        for fk in added:
            lines.append("  {}.{} => {}.{}".format(
                fk["table"], fk["column"], fk["other_table"], fk["other_column"]
            ))
    if skipped_fks:
        lines.append("Foreign keys skipped: {}".format(len(skipped_fks)))
        for fk in skipped_fks:
            lines.append("  {}.{} => {}.{} ({})".format(
                fk["table"], fk["column"], fk["other_table"], fk["other_column"],
                fk["reason"],
            ))
    sql = data.get("sql")
    if sql:
        lines.append("SQL query: {}".format(sql["query"]))
        lines.append("Output table: {}".format(sql["output_table"]))
        row_word = "row" if sql["rows"] == 1 else "rows"
        lines.append("Rows: {} {}".format(sql["rows"], row_word))
    return "\n".join(lines)


if __name__ == "__main__":
    cli()
