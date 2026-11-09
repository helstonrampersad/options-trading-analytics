import argparse
import datetime
import logging
from pathlib import Path

import duckdb

from ingest.config import load_config
from ingest.ingest import build_records

log = logging.getLogger("duckdb_loader")

NUMERIC_FIELDS = (
    "price",
    "quantity",
    "commission",
    "fees",
    "accrued_interest",
    "amount",
    "cash_balance",
    "exchange_rate",
)
COLUMNS = (
    "account_label",
    "run_date",
    "action",
    "symbol",
    "description",
    "type",
    "price",
    "quantity",
    "commission",
    "fees",
    "accrued_interest",
    "amount",
    "cash_balance",
    "settlement_date",
    "currency",
    "exchange_rate",
    "source_file",
    "row_hash",
    "ingested_at",
)

DDL = """
CREATE TABLE IF NOT EXISTS raw.fidelity_trades (
  account_label VARCHAR,
  run_date DATE,
  action VARCHAR,
  symbol VARCHAR,
  description VARCHAR,
  type VARCHAR,
  price DOUBLE,
  quantity DOUBLE,
  commission DOUBLE,
  fees DOUBLE,
  accrued_interest DOUBLE,
  amount DOUBLE,
  cash_balance DOUBLE,
  settlement_date DATE,
  currency VARCHAR,
  exchange_rate DOUBLE,
  source_file VARCHAR,
  row_hash VARCHAR,
  ingested_at TIMESTAMP
)
"""

MERGE_SQL = """
MERGE INTO raw.fidelity_trades AS t
USING _stage AS s
ON t.row_hash = s.row_hash
WHEN NOT MATCHED THEN INSERT ({cols})
VALUES ({vals})
""".format(
    cols=", ".join(COLUMNS),
    vals=", ".join(f"s.{c}" for c in COLUMNS),
)


def _safe_float(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _to_row(record, ingested_at):
    row = []
    for col in COLUMNS:
        if col == "ingested_at":
            row.append(ingested_at)
        elif col in NUMERIC_FIELDS:
            row.append(_safe_float(record.get(col)))
        else:
            row.append(record.get(col))
    return tuple(row)


def load_records(records, db_path):
    deduped = {}
    for record in records:
        deduped.setdefault(record["row_hash"], record)
    ingested_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    rows = [_to_row(r, ingested_at) for r in deduped.values()]

    con = duckdb.connect(db_path)
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        con.execute(DDL)
        con.execute("CREATE OR REPLACE TEMP TABLE _stage AS SELECT * FROM raw.fidelity_trades WHERE 1=0")
        if rows:
            con.executemany(
                "INSERT INTO _stage VALUES ({})".format(", ".join(["?"] * len(COLUMNS))),
                rows,
            )
        inserted = con.execute(
            "SELECT COUNT(*) FROM _stage s WHERE NOT EXISTS "
            "(SELECT 1 FROM raw.fidelity_trades t WHERE t.row_hash = s.row_hash)"
        ).fetchone()[0]
        if rows:
            con.execute(MERGE_SQL)
        total = con.execute("SELECT COUNT(*) FROM raw.fidelity_trades").fetchone()[0]
    finally:
        con.close()
    log.info("staged %d, inserted %d, total %d", len(rows), inserted, total)
    return {"staged": len(rows), "inserted": inserted, "total": total}


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Load Fidelity trade CSVs into a local DuckDB raw.fidelity_trades table")
    parser.add_argument("--db", default="data/local.duckdb", help="DuckDB file path")
    parser.add_argument("--env", default=".env", help="path to .env")
    parser.add_argument("--source-dir", default="data/raw", help="directory to scan for CSVs")
    args = parser.parse_args()

    cfg = load_config(args.env)
    csv_paths = sorted(Path(args.source_dir).glob("*.csv"))
    records = build_records([str(p) for p in csv_paths], cfg)
    result = load_records(records, args.db)
    log.info("duckdb load complete: %s", result)


if __name__ == "__main__":
    main()
