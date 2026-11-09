"""Export local DuckDB tables to flat files that Power BI Desktop can read.

Run from the repository root after the local pipeline has built ``data/local.duckdb``::

    python powerbi/export_marts.py
    python powerbi/export_marts.py --format parquet
    python powerbi/export_marts.py --schemas marts --out data/exports/powerbi

Each object is written as ``<schema>__<table>.<extension>`` plus a row in
``_manifest.csv`` (schema, table, file, row_count, exported_at). The database is
opened read-only, so the pipeline database is never modified or write-locked.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
from pathlib import Path

import duckdb

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
UNSAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9_]+")
MANIFEST_COLUMNS = ("schema", "table", "file", "row_count", "exported_at")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Export DuckDB tables/views to CSV or Parquet.")
    parser.add_argument("--db", default="data/local.duckdb", help="DuckDB database file (default: %(default)s)")
    parser.add_argument("--out", default="data/exports/powerbi", help="output directory (default: %(default)s)")
    parser.add_argument(
        "--format", choices=("csv", "parquet"), default="csv", help="output format (default: %(default)s)"
    )
    parser.add_argument("--schemas", default="marts,staging,raw", help="comma-separated schemas (default: %(default)s)")
    return parser.parse_args(argv)


def quote_identifier(name: str) -> str:
    """Quote a DuckDB identifier, refusing anything that is not a plain name."""
    if not IDENTIFIER_RE.match(name):
        raise ValueError(f"refusing to quote unsafe identifier: {name!r}")
    return f'"{name}"'


def safe_name(name: str) -> str:
    """Turn a schema/table name into a safe file-name fragment."""
    return UNSAFE_CHARS_RE.sub("_", name).strip("_") or "unnamed"


def sql_literal(value: str) -> str:
    """Escape a value for a DuckDB single-quoted string literal."""
    return "'" + value.replace("'", "''") + "'"


def discover_objects(
    con: duckdb.DuckDBPyConnection, schemas: list[str]
) -> list[tuple[str, str, str]]:
    """Return ``(schema, table, kind)`` tuples for the requested schemas."""
    placeholders = ", ".join("?" for _ in schemas)
    rows = con.execute(
        "SELECT table_schema, table_name, table_type FROM information_schema.tables "
        f"WHERE table_schema IN ({placeholders}) ORDER BY table_schema, table_name",
        schemas,
    ).fetchall()
    return [tuple(row) for row in rows if row[2] in ("BASE TABLE", "VIEW")]


def export_object(
    con: duckdb.DuckDBPyConnection,
    schema: str,
    table: str,
    out_dir: Path,
    extension: str,
) -> dict[str, object]:
    """Export one DuckDB object and return the manifest fields for it."""
    source = f"{quote_identifier(schema)}.{quote_identifier(table)}"
    row_count = con.execute(f"SELECT COUNT(*) FROM {source}").fetchone()[0]
    file_name = f"{safe_name(schema)}__{safe_name(table)}.{extension}"
    target = out_dir / file_name
    options = "FORMAT CSV, HEADER true" if extension == "csv" else "FORMAT PARQUET"
    con.execute(f"COPY (SELECT * FROM {source}) TO {sql_literal(target.as_posix())} ({options})")
    print(f"  exported {schema}.{table:<28} {row_count:>8,} rows -> {file_name}")
    return {"schema": schema, "table": table, "file": file_name, "row_count": row_count}


def main(argv: list[str] | None = None) -> int:
    """Export the requested DuckDB schemas and return a process exit code."""
    args = parse_args(argv)
    db_path = Path(args.db)
    out_dir = Path(args.out)
    schemas = [name.strip() for name in args.schemas.split(",") if name.strip()]

    if not db_path.is_file():
        print(f"error: DuckDB database not found: {db_path}", file=sys.stderr)
        print("       build it first with './run.sh daily' (or 'make local').", file=sys.stderr)
        return 1
    if not schemas:
        print("error: --schemas selected no schemas.", file=sys.stderr)
        return 1

    extension = args.format
    exported_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    con: duckdb.DuckDBPyConnection | None = None
    try:
        con = duckdb.connect(str(db_path), read_only=True)
        objects = discover_objects(con, schemas)
        if not objects:
            present = con.execute(
                "SELECT DISTINCT table_schema FROM information_schema.tables ORDER BY 1"
            ).fetchall()
            print(f"error: no tables or views found in: {', '.join(schemas)}", file=sys.stderr)
            print(f"       schemas present: {', '.join(p[0] for p in present) or '(none)'}", file=sys.stderr)
            return 1
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest_rows = [
            {**export_object(con, schema, table, out_dir, extension), "exported_at": exported_at}
            for schema, table, _kind in objects
        ]
    except (duckdb.Error, OSError) as exc:
        print(f"error: export failed: {exc}", file=sys.stderr)
        print("       close any GUI or pipeline run holding the database, then retry.", file=sys.stderr)
        return 1
    finally:
        if con is not None:
            con.close()

    manifest_path = out_dir / "_manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(manifest_rows)
    total_rows = sum(int(row["row_count"]) for row in manifest_rows)
    connector = "Text/CSV" if extension == "csv" else "Parquet"
    print(f"\nexported {len(manifest_rows)} object(s), {total_rows:,} rows to {out_dir} ({extension})")
    print(f"manifest: {manifest_path}")
    print(f"next: Power BI Desktop -> Get Data -> {connector} -> the exported files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
