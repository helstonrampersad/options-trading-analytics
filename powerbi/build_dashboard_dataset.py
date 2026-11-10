#!/usr/bin/env python3
"""Build a single flat Power BI dataset from the dbt marts.

Two modes:

    # real data (local use only - the output is gitignored and contains real trades)
    python powerbi/build_dashboard_dataset.py --mode real \
        --db data/local.duckdb --out data/exports/powerbi/dashboard.csv

    # fully synthetic demo data (safe to commit; used by powerbi/sample_data/)
    python powerbi/build_dashboard_dataset.py --mode synthetic \
        --out powerbi/sample_data/dashboard_synthetic.csv

The combined table keeps all three marts in one import so the report needs a
single Text/CSV connection.  ``source`` tells the report which mart a row came
from (wheel / puts / calls) - filter on it in Power BI before aggregating.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import random
from pathlib import Path

COLUMNS = [
    "run_date", "account_label", "ticker", "strategy", "source", "option_type",
    "trades", "sells", "assignments", "expiries", "net_pnl", "net_cash_flow",
    "premium", "avg_dte",
]

REAL_SQL = """
WITH wheel AS (
    SELECT
        CAST(run_date AS DATE)              AS run_date,
        account_label,
        ticker,
        strategy,
        'wheel'                             AS source,
        CASE strategy
            WHEN 'csp'           THEN 'PUT'
            WHEN 'covered_call'  THEN 'CALL'
            ELSE 'MIXED'
        END                                 AS option_type,
        CAST(n_trades AS BIGINT)            AS trades,
        CAST(n_sells AS BIGINT)             AS sells,
        CAST(n_assignments AS BIGINT)       AS assignments,
        CAST(NULL AS BIGINT)                AS expiries,
        CAST(net_pnl AS DOUBLE)             AS net_pnl,
        CAST(net_cash_flow AS DOUBLE)       AS net_cash_flow,
        CAST(NULL AS DOUBLE)                AS premium,
        CAST(avg_dte AS DOUBLE)             AS avg_dte
    FROM marts.fct_wheel_mechanics
),
puts AS (
    SELECT
        CAST(run_date AS DATE), account_label, ticker, 'csp', 'puts', 'PUT',
        CAST(n_trades AS BIGINT), CAST(n_puts_sold AS BIGINT),
        CAST(n_assignments AS BIGINT), CAST(n_expired AS BIGINT),
        CAST(net_pnl AS DOUBLE), CAST(net_cash_flow AS DOUBLE),
        CAST(NULL AS DOUBLE), CAST(NULL AS DOUBLE)
    FROM marts.fct_cash_secured_puts
),
calls AS (
    SELECT
        CAST(run_date AS DATE), account_label, ticker, 'covered_call', 'calls', 'CALL',
        CAST(n_trades AS BIGINT), CAST(n_calls_sold AS BIGINT),
        CAST(n_called_away AS BIGINT), CAST(n_expired AS BIGINT),
        CAST(net_pnl AS DOUBLE), CAST(net_cash_flow AS DOUBLE),
        CAST(premium_collected AS DOUBLE), CAST(NULL AS DOUBLE)
    FROM marts.fct_covered_call_premiums
)
SELECT * FROM wheel
UNION ALL SELECT * FROM puts
UNION ALL SELECT * FROM calls
ORDER BY run_date, source, account_label, ticker
"""

ACCOUNTS = ["LLC_MAIN", "ROTH_IRA", "ROLLOVER_IRA", "INDIVIDUAL_LEGACY"]
TICKERS = ["PLTR", "MU", "AMZN", "AMD", "NFLX", "ARM", "TSLA", "SPY"]
WHEEL_STRATEGIES = ["csp", "covered_call", "PLTR_wheel", "leap", "day_trade", "other"]


def _business_days(start: dt.date, end: dt.date) -> list[str]:
    days, day = [], start
    while day <= end:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += dt.timedelta(days=1)
    return days


def build_synthetic(seed: int = 20261109) -> list[list[object]]:
    """Invented rows shaped like the real combined table - no private data."""
    rng = random.Random(seed)
    days = _business_days(dt.date(2025, 1, 2), dt.date(2026, 11, 6))

    def money(low: float, high: float) -> float:
        return round(rng.uniform(low, high), 2)

    rows: list[list[object]] = []
    for _ in range(260):  # wheel activity (all option strategies)
        strategy = rng.choice(WHEEL_STRATEGIES)
        option_type = {"csp": "PUT", "covered_call": "CALL"}.get(strategy, "MIXED")
        trades = rng.randint(1, 6)
        rows.append([
            rng.choice(days), rng.choice(ACCOUNTS), rng.choice(TICKERS), strategy,
            "wheel", option_type, trades, rng.randint(1, trades), rng.randint(0, 1),
            rng.randint(0, 2), money(-400, 900), money(-2500, 2500), 0.0, rng.randint(2, 60),
        ])
    for _ in range(180):  # put activity
        trades = rng.randint(1, 5)
        rows.append([
            rng.choice(days), rng.choice(ACCOUNTS), rng.choice(TICKERS), "csp",
            "puts", "PUT", trades, rng.randint(1, trades), rng.randint(0, 2),
            rng.randint(0, 2), money(-250, 500), money(-1800, 1800), 0.0, rng.randint(2, 45),
        ])
    for _ in range(180):  # call activity
        trades = rng.randint(1, 5)
        rows.append([
            rng.choice(days), rng.choice(ACCOUNTS), rng.choice(TICKERS), "covered_call",
            "calls", "CALL", trades, rng.randint(1, trades), rng.randint(0, 1),
            rng.randint(0, 2), money(-150, 700), money(-1200, 2200), money(20, 900), 0.0,
        ])
    rows.sort(key=lambda r: (str(r[0]), str(r[4])))
    return rows


def build_real(db_path: Path) -> list[list[object]]:
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("duckdb is required for --mode real (pip install -r requirements.txt)") from exc
    if not db_path.is_file():
        raise SystemExit(f"DuckDB file not found: {db_path}\nRun ./run.sh full first (or point --db at it).")
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        result = con.execute(REAL_SQL).fetchall()
    finally:
        con.close()
    return [list(r) for r in result]


def write_csv(rows: list[list[object]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the combined Power BI dashboard dataset.")
    parser.add_argument("--mode", choices=["real", "synthetic"], default="real")
    parser.add_argument("--db", default="data/local.duckdb", help="DuckDB file (real mode)")
    parser.add_argument("--out", default=None, help="output CSV path")
    parser.add_argument("--seed", type=int, default=20261109, help="synthetic mode seed")
    args = parser.parse_args(argv)

    if args.mode == "real":
        rows = build_real(Path(args.db))
        out = Path(args.out or "data/exports/powerbi/dashboard.csv")
        note = "Contains real trade data - keep it local (data/exports/ is gitignored)."
    else:
        rows = build_synthetic(seed=args.seed)
        out = Path(args.out or "powerbi/sample_data/dashboard_synthetic.csv")
        note = "Synthetic demo data - safe to commit."

    write_csv(rows, out)
    by_source: dict[str, int] = {}
    for row in rows:
        by_source[str(row[4])] = by_source.get(str(row[4]), 0) + 1
    print(f"wrote {len(rows):,} rows to {out}")
    print("rows by source: " + ", ".join(f"{k}={v}" for k, v in sorted(by_source.items())))
    print(note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
