# ingest/bigquery_loader.py
import logging
from datetime import datetime, timezone

from google.cloud import bigquery
from google.cloud.exceptions import NotFound

from ingest.parse_fidelity import NORMALIZED_FIELDS

log = logging.getLogger("ingest")

SCHEMA = [
    bigquery.SchemaField("account_label", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("run_date", "DATE"),
    bigquery.SchemaField("action", "STRING"),
    bigquery.SchemaField("symbol", "STRING"),
    bigquery.SchemaField("description", "STRING"),
    bigquery.SchemaField("type", "STRING"),
    bigquery.SchemaField("price", "FLOAT64"),
    bigquery.SchemaField("quantity", "FLOAT64"),
    bigquery.SchemaField("commission", "FLOAT64"),
    bigquery.SchemaField("fees", "FLOAT64"),
    bigquery.SchemaField("accrued_interest", "FLOAT64"),
    bigquery.SchemaField("amount", "FLOAT64"),
    bigquery.SchemaField("cash_balance", "FLOAT64"),
    bigquery.SchemaField("settlement_date", "DATE"),
    bigquery.SchemaField("currency", "STRING"),
    bigquery.SchemaField("exchange_rate", "FLOAT64"),
    bigquery.SchemaField("source_file", "STRING"),
    bigquery.SchemaField("row_hash", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
]

FLOAT_FIELDS = {"price", "quantity", "commission", "fees", "accrued_interest",
                "amount", "cash_balance", "exchange_rate"}


def _safe_float(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _to_bq_rows(records):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    seen = {}
    for r in records:
        row = {"account_label": r["account_label"], "source_file": r["source_file"],
               "row_hash": r["row_hash"], "ingested_at": now}
        for f in NORMALIZED_FIELDS:
            v = r.get(f)
            if v is None or v == "":
                row[f] = None
            elif f in FLOAT_FIELDS:
                row[f] = _safe_float(v)
            else:
                row[f] = v
        seen.setdefault(row["row_hash"], row)
    return list(seen.values())


def ensure_dataset(client, project_id, dataset):
    ref = client.dataset(dataset, project=project_id)
    try:
        client.get_dataset(ref)
    except NotFound:
        client.create_dataset(bigquery.Dataset(ref), timeout=120)
        log.info("created dataset %s.%s", project_id, dataset)


def ensure_landing_table(client, project_id, dataset, table="fidelity_trades"):
    ref = client.dataset(dataset, project=project_id).table(table)
    try:
        client.get_table(ref)
    except NotFound:
        client.create_table(bigquery.Table(ref, schema=SCHEMA), timeout=120)
        log.info("created table %s.%s.%s", project_id, dataset, table)


def build_merge_sql(project_id, dataset, table, stage_table):
    cols = [f.name for f in SCHEMA]
    insert_cols = ", ".join(f"`{c}`" for c in cols)
    values = ", ".join(f"S.`{c}`" for c in cols)
    return f"""
MERGE `{project_id}.{dataset}.{table}` T
USING `{project_id}.{dataset}.{stage_table}` S
ON T.row_hash = S.row_hash
WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({values})"""


def upsert_records(cfg, records, client=None):
    project_id = cfg.get("project_id")
    if not project_id:
        raise ValueError("GCP_PROJECT_ID is required to upload records to BigQuery")
    if client is None:
        client = bigquery.Client(project=project_id)
    dataset = cfg["raw_dataset"]
    ensure_dataset(client, project_id, dataset)
    ensure_landing_table(client, project_id, dataset)
    if not records:
        log.info("no records to ingest")
        return {"inserted": 0, "updated": 0, "skipped": 0}

    rows = _to_bq_rows(records)
    stage = f"fidelity_trades_stage_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    stage_ref = client.dataset(dataset, project=project_id).table(stage)
    client.create_table(bigquery.Table(stage_ref, schema=SCHEMA), timeout=120)
    try:
        job_config = bigquery.LoadJobConfig(schema=SCHEMA)
        job = client.load_table_from_json(rows, stage_ref, job_config=job_config)
        job.result()
        sql = build_merge_sql(project_id, dataset, "fidelity_trades", stage)
        merge_job = client.query(sql, job_config=bigquery.QueryJobConfig(use_legacy_sql=False))
        merge_job.result()
        rows_affected = merge_job.num_dml_affected_rows
        log.info("merged %d rows into fidelity_trades", rows_affected)
        return {"inserted": rows_affected, "updated": 0, "skipped": max(0, len(rows) - rows_affected)}
    finally:
        client.delete_table(stage_ref, not_found_ok=True)
