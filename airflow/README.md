# Airflow

Two DAGs schedule the existing pipelines. Nothing under `airflow/` modifies pipeline code.

| DAG | Pipeline | Tasks |
| --- | --- | --- |
| `options_pipeline_bigquery` | BigQuery (`ingest.ingest` + `dbt_project/`) | `init_raw >> ingest >> dbt_run >> dbt_test` |
| `options_pipeline_local` | Local DuckDB (`ingest.duckdb_loader` + `dbt_local/`) | `local_load >> local_dbt_run >> local_dbt_test` |

Both run weekdays at 18:00 (`0 18 * * 1-5`) with `catchup=False`,
`max_active_runs=1`, and 2 retries 5 minutes apart. Each task runs in the repo
root (default the repository root derived from `Path(__file__).resolve().parents[2]`,
override with `GAUNTLET_REPO`).

Pinned to Airflow 3.3.1, which supports Python 3.10. The classic 2-style imports
used by these DAGs (`from airflow import DAG`,
`from airflow.operators.bash import BashOperator`) still work in Airflow 3 via
deprecation shims.

## Run locally

```bash
cd airflow
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

export AIRFLOW_HOME=/tmp/airflow_home
export AIRFLOW__CORE__DAGS_FOLDER="$PWD/dags"
.venv/bin/airflow db migrate        # Airflow 3.x; `airflow db init` on 2.x
.venv/bin/airflow standalone        # scheduler + API server + DAG processor
```

Run a single DAG once without the scheduler (this executes the real local
pipeline and needs `dbt` on `PATH`):

```bash
.venv/bin/airflow dags test options_pipeline_local 2026-09-12
```

The BigQuery DAG needs GCP Application Default Credentials
(`gcloud auth application-default login`) plus a repo-root `.env`; the local DAG
needs no credentials and `DUCKDB_PATH` is set by the DAG itself.

## Production

`airflow standalone` bundles every component for a laptop. In production the same
DAG files run on a scheduler, workers (Celery or Kubernetes executor), a Postgres
metadata database, and a DAG processor. Managed services such as MWAA, Astronomer,
or Cloud Composer deploy this exact `dags/` folder unchanged; only the runtime,
`GAUNTLET_REPO`, and credentials differ.
