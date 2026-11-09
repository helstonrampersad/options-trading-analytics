# How to Use This Pipeline Day to Day

Beginner-friendly runbook for the local (DuckDB) pipeline. No cloud account and no private
data are needed for the demo; the full run uses your own broker CSV exports.

## Where to run it

Run everything from the repository root in a **WSL2 Ubuntu terminal** (recommended on Windows)
or a Linux/macOS shell. Native Windows does not have the Python 3.11 + dbt toolchain this repo
expects. In WSL the repo is usually under `/mnt/c/Users/<you>/Downloads/openCode/`:

```bash
cd /mnt/c/Users/<you>/Downloads/openCode/options-trading-analytics
```

All commands below assume that directory.

## One-time setup

```bash
./run.sh setup
```

This creates `.venv` with Python 3.11 and installs the pinned dependencies. It uses `uv` when
available and falls back to `python3 -m venv`; both `requirements.txt` and `requirements-dev.txt`
are installed. If you prefer to do it by hand:

```bash
uv venv .venv --python 3.11
. .venv/bin/activate
uv pip install -r requirements.txt -r requirements-dev.txt
```

## The commands you need

| Command | What it does |
|---|---|
| `./run.sh setup` | one-time: create/repair the venv and install dependencies |
| `./run.sh sample` | synthetic demo: loads `tests/fixtures/sample_history.csv`, runs `dbt run` + `dbt test` against `data/sample.duckdb`. No private data, no cloud |
| `./run.sh daily` | after new exports: ingest `../optionsDayTrade` into `data/local.duckdb`, then incremental `dbt run` |
| `./run.sh full` | first run or after adding old CSVs: same ingest, then `dbt run --full-refresh` |
| `./run.sh test` | 35 pytest tests + 28 dbt tests (incl. P&L reconciliation) |
| `./run.sh powerbi` | export the local marts to `data/exports/powerbi` for the report |
| `./run.sh query "SQL"` | run one read-only query against `data/local.duckdb` and print a table |

Environment overrides: `SOURCE_DIR` (CSV folder, default `../optionsDayTrade`) and
`DUCKDB_PATH` (database file, default `data/local.duckdb`). `run.sh` activates the venv and
exports `DUCKDB_PATH`; raw `dbt` commands need that variable set (see Troubleshooting).

## Try it first: the synthetic demo (no private data)

`./run.sh sample` builds a throwaway DuckDB database from the committed synthetic fixture,
runs the dbt staging views and marts, and executes the full dbt test suite. It is the fastest
way to confirm the toolchain works and to see the pipeline without touching real exports.

```bash
./run.sh sample
```

Inspect the demo with any DuckDB client at `data/sample.duckdb`, or point `run.sh query` at it:

```bash
DUCKDB_PATH=$PWD/data/sample.duckdb ./run.sh query \
  "SELECT strategy, COUNT(*) AS trades FROM marts.fct_wheel_mechanics GROUP BY 1 ORDER BY 2 DESC"
```

The demo database is `data/sample.duckdb` (gitignored, regenerable). Delete it any time.

## Daily loop with your own exports

1. Configure account anonymization **once**. Copy the example file and fill in the real
   account-number → label mappings. The file is gitignored; never commit it.

   ```bash
   cp .env.example .env
   # edit .env: ACCOUNT_<real number>=<LABEL> for each account
   ```

   The four labels are `LLC_MAIN`, `ROTH_IRA`, `ROLLOVER_IRA`, `INDIVIDUAL_LEGACY`. Real
   account numbers exist only in `.env`; ingest rewrites them before any row is built.

2. Export new trade history from your broker and save the CSV into `../optionsDayTrade/`
   (the default `SOURCE_DIR`; override with `SOURCE_DIR=/path/to/csvs ./run.sh daily`).

3. Run the pipeline and tests:

   ```bash
   ./run.sh daily
   ./run.sh test
   ```

4. If tests fail because you added CSVs with **old** trade dates, the 3-day incremental
   window did not rescan them. Run the full rebuild:

   ```bash
   ./run.sh full
   ```

## Looking at the numbers

```bash
./run.sh query "SELECT run_date, account_label, ticker, net_pnl
                FROM marts.fct_wheel_mechanics
                ORDER BY run_date DESC LIMIT 20"
```

Any DuckDB client can open `data/local.duckdb` (VS Code DuckDB extension, DBeaver,
Tabularis). **DuckDB is single-writer:** close the GUI connection before `./run.sh daily`,
or the run fails with a lock/permission error.

## The three layers you can edit

| Layer | File | Change here when |
|---|---|---|
| parsing | `ingest/parse_fidelity.py` | the broker changes the export format |
| classification | `dbt_local/macros/strategy_classification.sql` | a trade is labeled wrong |
| business logic | `dbt_local/models/marts/*.sql` | you want a new metric |

After editing a **mart**, run `./run.sh full` — incremental tables keep their old schema
otherwise. Staging views rebuild on every run, so no refresh is needed for them.

## Power BI export

Build the local marts, then export them for the report:

```bash
./run.sh daily
./run.sh powerbi
# equivalent: make powerbi, or directly:
python powerbi/export_marts.py --db data/local.duckdb --out data/exports/powerbi
```

The exported CSVs and the report assets are described in `powerbi/README.md`. Only synthetic
sample data is committed; real exports stay local and gitignored.

## Where the tables live

```
raw.fidelity_trades              append-only landing table, deduped by row_hash
staging.stg_fidelity_trades      parsed + classified (strategy, contract fields, USD)
marts.fct_wheel_mechanics        P&L by day/account/ticker/strategy
marts.fct_cash_secured_puts      all put activity
marts.fct_covered_call_premiums  all call activity
```

Row counts depend on your own exports, so none are published here.

## Rebuilding from zero

Safe, takes seconds:

```bash
rm data/local.duckdb
./run.sh full
```

## Cloud paths (optional)

BigQuery and Databricks need your own credentials and are not part of the everyday local loop.
See the main `README.md` for the BigQuery auth/run steps and the Databricks notebook/dbt notes.

## Troubleshooting

- **"No .venv"** — run `./run.sh setup`.
- **"Could not find profile" or wrong database from raw `dbt`** — export
  `DUCKDB_PATH=$PWD/data/local.duckdb` first. `run.sh` does this automatically.
- **dbt flags ignored** — flags go *after* the subcommand:
  `dbt run --project-dir dbt_local --profiles-dir dbt_local`.
- **Lock error on `data/local.duckdb`** — a GUI has the file open; close it and rerun.
- **A new column is missing from a mart** — incremental tables need `./run.sh full`.
- **An export file is skipped with a warning** — its filename cannot be mapped to a label.
  Add an `ACCOUNT_*` or `FILE_*` line to `.env`, or rename the file to match the
  `History_for_Account_<number> ...csv` pattern.
