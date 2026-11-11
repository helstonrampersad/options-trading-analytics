# Project Status — Options Trading Analytics Pipeline

**Last updated:** 2026-11-10
**Repo:** https://github.com/helstonrampersad/options-trading-analytics (v1.0 tagged; CI green)
**Purpose:** single-page context for future sessions, reviewers, and job-application reference.
Nothing here is secret; the owner's real exports, `.env`, and cloud identifiers are never written to this file.

## What this is

End-to-end analytics over one person's Fidelity options-trade CSV exports across four accounts.
Filenames are anonymized to labels (`LLC_MAIN`, `ROTH_IRA`, `ROLLOVER_IRA`, `INDIVIDUAL_LEGACY`)
before any row is built. The same medallion architecture — raw landing table → dbt staging
views → incremental marts — is implemented four ways across three engines:

| Implementation | Engine | Directory |
|---|---|---|
| BigQuery | dbt (`dbt-bigquery`) | `dbt_project/` |
| Local | dbt (`dbt-duckdb`) | `dbt_local/` |
| Databricks notebook | PySpark + Delta | `databricks/options_pipeline.py` |
| Databricks dbt | dbt (`dbt-databricks`) | `dbt_databricks/` |

The local DuckDB path is the one exercised end to end by tests and CI. Cloud paths require the
owner's credentials and are not part of CI.

## Release status (2026-11-10)

**Repository published to GitHub** and tagged v1.0. The committed tree is publication-safe:
no real trade CSVs, no `.env`, no account numbers, no cloud project IDs or workspace URLs, no
personal absolute paths. The only committed data is the synthetic fixture
`tests/fixtures/sample_history.csv` plus synthetic Power BI sample CSVs under
`powerbi/sample_data/`. The owner's real exports live outside the repo and are gitignored;
`scripts/privacy_check.py` is the pre-push guard.

- **CI:** `.github/workflows/ci.yml` runs on every push/PR/manual dispatch (ruff, pytest,
  end-to-end DuckDB run on the committed synthetic fixture, credential-free `dbt parse` for the
  cloud projects). The first GitHub Actions run (2026-11-09, run `42725377720`) completed
  **success**, and subsequent pushes are green as well.
- **Power BI:** a working one-page dashboard was built in Power BI Desktop from the synthetic
  sample (`powerbi/OptionsTrading.pbix`, gitignored locally) and committed as a public-safe
  screenshot (`powerbi/screenshots/01-wheel-overview.png`): KPI cards, monthly P&L trend, P&L by
  strategy, an account slicer and a ticker/strategy table. The committed assets also include the
  combined dataset builder, DAX measures, theme, data dictionary and the three-page build spec
  for extending it; pages 2–3 are not built yet.
- **Orchestration:** Airflow DAGs and a Databricks Workflows path are authored; neither runs on a
  scheduler in this repo — that is a deployment step, not a claim.

## Verified test evidence

Run on **2026-11-09** on the local toolchain (Python 3.11, dbt on DuckDB):

- `pytest tests/ -q` → **35 passed**.
- `dbt test` → **PASS=28, ERROR=0** (28 dbt tests per project: 25 generic schema tests + 3
  singular P&L reconciliation SQL tests under each project's `tests/` directory, e.g.
  `dbt_local/tests/reconcile_pnl.sql`, `reconcile_puts_pnl.sql`, `reconcile_calls_pnl.sql`).

These are the only verification figures that should be quoted. No row counts, mart counts, or
P&L figures are published in this repo.

## What works locally (verified)

```bash
./run.sh setup     # one-time: uv venv + uv pip install (no make/pip needed)
./run.sh sample    # synthetic fixture -> demo DuckDB -> dbt run + dbt test, no private data
./run.sh daily     # real CSVs from ../optionsDayTrade -> DuckDB ingest + incremental dbt run
./run.sh full      # first load or backlog CSVs: ingest + dbt run --full-refresh
./run.sh test      # 35 pytest + 28 dbt tests
./run.sh query "SELECT strategy, COUNT(*) FROM marts.fct_wheel_mechanics GROUP BY 1"
```

Pipeline mechanics that are confirmed working:

- Header sniffing for both Fidelity formats (13-column current, 17-column legacy) and CR-only files.
- Account anonymization from the gitignored `.env` before a row is built; unknown files skip with a warning.
- md5 content-hash identity (`row_hash`) with occurrence indexes, `cash_balance` excluded, settled row
  preferred over the `Processing` placeholder twin.
- Insert-only landing and incremental merge marts keyed on `(run_date, account_label, ticker[, strategy])`
  with a 3-day lookback. Backlogged older CSVs need `./run.sh full`.
- dbt layering: staging views (`stg_fidelity_*`) → three incremental marts
  (`fct_wheel_mechanics`, `fct_cash_secured_puts`, `fct_covered_call_premiums`).
- DuckDB single-writer gotcha: close any GUI connection before running the pipeline.

## Cloud paths (implemented, need owner credentials)

**BigQuery** — `dbt_project/` targets the BigQuery adapter. Auth is Application Default
Credentials (`gcloud auth application-default login`); connection settings come from environment
variables (`GCP_PROJECT_ID`, `GCP_REGION`, `GCP_RAW_DATASET`, `GCP_ANALYTICS_DATASET`), not from
committed files. Ingestion is `python -m ingest.ingest`; transforms are
`dbt run --project-dir dbt_project --profiles-dir dbt_project`. The region must match the raw
dataset location (the project uses the US multi-region). CI runs only a credential-free
`dbt parse` for this project.

**Databricks** — `databricks/options_pipeline.py` is a single-file PySpark/Delta medallion notebook
(bronze → silver → gold, partition-by-`run_date`, MERGE upserts); `dbt_databricks/` is the same dbt
models in Spark SQL. Both are written for a Databricks Free Edition workspace and need a host,
HTTP path, and short-lived PAT supplied through environment variables. No workspace URL, token, or
catalog identifier is committed. CI runs only a credential-free `dbt parse`.

**Airflow** — `airflow/dags/` contains `options_pipeline_local` and `options_pipeline_bigquery`
(weekday schedule, `catchup=False`, retries). See `airflow/README.md`. Deploying them to a scheduler
is future work; the repo does not claim scheduled runs.

## Known gaps / honest caveats

- CI is green and the tree is pushed; the next polish step is building pages 2–3 of the Power BI
  report (`powerbi/dashboard-spec.md` has the full spec).
- A Power BI report can be built locally from the committed dataset, measures and spec; the
  `.pbix` is intentionally not committed.
- BigQuery and Databricks runs depend on owner credentials and were not exercised in the
  release-prep verification above.
- The four implementations share a design, not a runtime; keeping them in sync is manual.
- Some `History_for_Account_...` exports are skipped by design: a filename whose stem has a
  hyphen cannot match a `FILE_*` key, and those rows already appear in the monthly exports.

## Roadmap

1. Extend the Power BI report to pages 2–3 (CSP/covered-call lifecycle and data-quality pages)
   and refresh the README screenshot.
2. `dbt docs generate` and link a lineage screenshot from the README.
3. Deploy the Airflow DAGs to a scheduler, or schedule the Databricks notebook with Databricks Workflows.
4. Optional differentiator: MCP server + data-health watchdog + agent skill (see `docs/MCP_AGENT_LAYER.md`,
   parked until the release and applications are done).

## Resume bullets (defensible as written)

- Built an end-to-end options-trading analytics pipeline in Python 3.11 and dbt: header-sniffing
  broker CSV ingest, account anonymization before warehouse entry, md5 content-hash dedupe,
  insert-only raw landing, and three incremental merge marts with P&L reconciliation tests.
- Implemented the same medallion design four ways across three engines (dbt on BigQuery, DuckDB,
  and Databricks; PySpark/Delta notebook), with 35 pytest tests and 28 dbt tests per project
  including singular P&L reconciliation tests, and credential-free CI on a synthetic fixture.
- Authored Airflow DAGs for local and BigQuery pipelines, a PySpark/Delta Databricks notebook,
  and Power BI report assets over the marts; documented architecture, privacy design, design
  trade-offs, and operational runbooks in-repo.
