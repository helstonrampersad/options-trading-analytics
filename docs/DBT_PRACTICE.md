# dbt Practice Guide

Hands-on labs for learning dbt on your own data. Everything runs from a **WSL2 Ubuntu terminal** in the repo root (native Windows lacks the toolchain).

Repo root: `~/path/to/options-trading-analytics` — on WSL that is typically
`cd /mnt/c/Users/<you>/Downloads/openCode/options-trading-analytics`.

## One-time terminal setup

```bash
cd ~/path/to/options-trading-analytics
export DUCKDB_PATH=$PWD/data/local.duckdb
alias dbt-local='dbt --project-dir dbt_local --profiles-dir dbt_local'
dbt-local debug          # expect: "All checks passed!"
```

`./run.sh` sets `DUCKDB_PATH` for you (and `./run.sh setup` creates the venv).
Raw `dbt` commands need it because the project's default path points elsewhere.

## How dbt works

- **Models** are SQL files with Jinja (`{{ ref('other_model') }}`). `dbt run` executes them in dependency order.
- **Materializations**: `view` (rebuilt every run) and `incremental` (merged by `unique_key`; schema changes need `--full-refresh`).
- **Tests** are SQL queries. If a test returns **any rows**, it **FAILS**. That is the whole idea.
- Your project layout: `raw` table → `staging` views → `marts` tables.

## Lab 1 — Explore the data

Use the DuckDB VS Code extension, Tabularis, DBeaver, or `make view` (CLI).

| Layer | What it is | Objects |
|---|---|---|
| `raw.fidelity_trades` | deduplicated trade lines (append-only, keyed by `row_hash`) | 1 table |
| `staging.stg_fidelity_trades` | parsed + classified (contract fields, strategy, `amount_usd`) | 5 views |
| `marts.fct_*` | business aggregates (wheel/puts/calls P&L by day+ticker) | 3 tables |

```sql
SELECT count(*) FROM raw.fidelity_trades;
SELECT account_label, count(*) FROM raw.fidelity_trades GROUP BY 1 ORDER BY 2 DESC;
SELECT min(run_date), max(run_date) FROM raw.fidelity_trades;
SELECT strategy, count(*) FROM staging.stg_fidelity_trades GROUP BY 1 ORDER BY 2 DESC;
SELECT * FROM staging.stg_fidelity_trades WHERE is_option LIMIT 20;
SELECT * FROM marts.fct_wheel_mechanics ORDER BY run_date DESC LIMIT 20;
SELECT strategy, SUM(net_pnl) FROM marts.fct_wheel_mechanics GROUP BY 1 ORDER BY 2 DESC;
```

## Lab 2 — See a transformation happen

Read these in order (they are short):

1. `dbt_local/models/staging/stg_fidelity_trades.sql` — the SELECT that builds the view
2. `dbt_local/macros/parse_fidelity_contract.sql` — turns `-PLTR260807C155` into ticker=PLTR, expiry=2026-08-07, type=C, strike=155
3. `dbt_local/macros/strategy_classification.sql` — the CASE logic that labels each trade
4. `dbt_local/models/marts/fct_wheel_mechanics.sql` — the aggregation

See the SQL dbt *actually* sent to the database (Jinja resolved):

```bash
dbt-local compile --select stg_fidelity_trades
# open: dbt_local/target/compiled/gauntlet_local/models/staging/stg_fidelity_trades.sql
```

## Lab 3 — Run tests, see output, break one on purpose

```bash
dbt-local ls --resource-type test             # list all 28 test names
make test-local                               # run them all
dbt-local test --select fct_wheel_mechanics   # run one model's tests
```

Test definitions live in `dbt_local/models/staging/schema.yml` and `dbt_local/models/marts/schema.yml`.

**Break it:** open `dbt_local/models/marts/schema.yml`, find the `accepted_values` test for `strategy`, and delete the line `- csp`. Run `make test-local` → it FAILS and reports how many bad rows.

Now see the actual bad rows:

```bash
dbt-local test --select fct_wheel_mechanics --store-failures
```

Then find and query the audit table:

```sql
SELECT table_schema, table_name FROM information_schema.tables WHERE table_name LIKE '%strategy%';
SELECT * FROM <that table>;
```

Restore the `- csp` line, re-run → green. That is the full test-debugging loop.

## Lab 4 — Write your own test

Create `dbt_local/tests/no_future_trades.sql`:

```sql
SELECT * FROM {{ ref('stg_fidelity_trades') }} WHERE run_date > CURRENT_DATE
```

Run `dbt-local test --select no_future_trades`. It passes (no rows). Change `>` to `<` → it fails. A test is just a query whose result is the list of violations.

## Lab 5 — Modify a transformation

Open `dbt_local/models/marts/fct_wheel_mechanics.sql` and add a column to the SELECT, e.g. `COUNT(DISTINCT contract_ticker) AS n_tickers,`. Then:

```bash
make local-full    # schema changed → needs --full-refresh
```

Query the mart — your new column is there. (Views rebuild every run; incremental tables keep their schema until you full-refresh.)

## Cheat sheet

```bash
dbt-local run                                           # build all models
dbt-local test                                          # run all tests
dbt-local build                                         # run + test in order
dbt-local run --select fct_cash_secured_puts
dbt-local show --select fct_wheel_mechanics --limit 5   # preview without materializing
dbt-local ls                                            # list all resources
dbt-local compile --select <model>                      # just render the SQL
```

## Troubleshooting

- **"Permission denied" / lock error on `data/local.duckdb`**: DuckDB is single-writer. Close the DuckDB extension connection, Tabularis, or DBeaver before running `make local` / `make test-local`.
- **"Could not find profile" or wrong database**: you ran `dbt` without `DUCKDB_PATH` set. Use `make ...` or the `dbt-local` alias after the one-time setup.
- **Model changes do not appear**: incremental marts need `make local-full`.
- **Want to see a failing test's rows**: add `--store-failures`, then query the audit table (Lab 3).

## After the labs

The same structure exists in `dbt_project/` (BigQuery dialect) and `dbt_databricks/` (Spark dialect) — skills transfer directly. Next project step: Power BI on the BigQuery marts.
