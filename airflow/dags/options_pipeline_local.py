"""Airflow DAG for the Fidelity options pipeline on local DuckDB."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.bash import BashOperator

REPO = os.environ.get(
    "GAUNTLET_REPO",
    str(Path(__file__).resolve().parents[2]),
)
DUCKDB_PATH = os.path.join(REPO, "data", "local.duckdb")

TASK_ENV = {
    **os.environ,
    "DUCKDB_PATH": DUCKDB_PATH,
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
}

DOC_MD = """
# Options pipeline (local DuckDB)

Runs the same options pipeline without any cloud dependencies:

1. `local_load` - runs `python3 -m ingest.duckdb_loader` to load `data/raw/`
   into `data/local.duckdb`.
2. `local_dbt_run` - runs `dbt run --project-dir dbt_local --profiles-dir dbt_local`.
3. `local_dbt_test` - runs `dbt test` for the same project.

## Requirements

- `dbt` must be on `PATH` (the tasks pass `PATH` through).
- `DUCKDB_PATH` is set to `<repo>/data/local.duckdb` for the dbt tasks.
- The repo location defaults to `GAUNTLET_REPO` and can be overridden with that
  environment variable.
"""

default_args = {
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="options_pipeline_local",
    description="Load Fidelity CSVs into DuckDB and build local dbt models",
    schedule="0 18 * * 1-5",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["options", "duckdb", "dbt"],
    doc_md=DOC_MD,
) as dag:
    local_load = BashOperator(
        task_id="local_load",
        bash_command=(
            "python3 -m ingest.duckdb_loader "
            "--db data/local.duckdb --source-dir data/raw --env .env"
        ),
        cwd=REPO,
        env=TASK_ENV,
    )

    local_dbt_run = BashOperator(
        task_id="local_dbt_run",
        bash_command="dbt run --project-dir dbt_local --profiles-dir dbt_local",
        cwd=REPO,
        env=TASK_ENV,
    )

    local_dbt_test = BashOperator(
        task_id="local_dbt_test",
        bash_command="dbt test --project-dir dbt_local --profiles-dir dbt_local",
        cwd=REPO,
        env=TASK_ENV,
    )

    local_load >> local_dbt_run >> local_dbt_test
