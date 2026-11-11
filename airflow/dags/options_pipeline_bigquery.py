"""Airflow DAG for the Fidelity options pipeline on BigQuery."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.bash import BashOperator

REPO = os.environ.get(
    "OPTIONS_REPO",
    str(Path(__file__).resolve().parents[2]),
)

DOC_MD = """
# Options pipeline (BigQuery)

Loads Fidelity trade CSVs and builds the BigQuery analytics models:

1. `init_raw` - copies the source CSVs into `data/raw/`.
2. `ingest` - runs `python3 -m ingest.ingest` to load `data/raw/` into BigQuery.
3. `dbt_run` - runs `dbt run --project-dir dbt_project --profiles-dir dbt_project`.
4. `dbt_test` - runs `dbt test` for the same project.

## Credentials

- GCP Application Default Credentials are required:
  `gcloud auth application-default login`
- A `.env` file at the repo root provides `GCP_PROJECT_ID`, `GCP_REGION`,
  `GCP_RAW_DATASET`, `GCP_ANALYTICS_DATASET`, and the `ACCOUNT_*` / `FILE_*`
  anonymization mappings.
- The repo location defaults to `OPTIONS_REPO` and can be overridden with that
  environment variable.
"""

default_args = {
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="options_pipeline_bigquery",
    description="Ingest Fidelity CSVs and build dbt models on BigQuery",
    schedule="0 18 * * 1-5",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["options", "bigquery", "dbt"],
    doc_md=DOC_MD,
) as dag:
    init_raw = BashOperator(
        task_id="init_raw",
        bash_command="python3 -m ingest.ingest --init-raw",
        cwd=REPO,
    )

    ingest = BashOperator(
        task_id="ingest",
        bash_command="set -a; source .env; set +a; python3 -m ingest.ingest",
        cwd=REPO,
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=(
            "set -a; source .env; set +a; "
            "dbt run --project-dir dbt_project --profiles-dir dbt_project"
        ),
        cwd=REPO,
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=(
            "set -a; source .env; set +a; "
            "dbt test --project-dir dbt_project --profiles-dir dbt_project"
        ),
        cwd=REPO,
    )

    init_raw >> ingest >> dbt_run >> dbt_test
