# tests/test_bigquery_loader.py
import pytest

from ingest.bigquery_loader import SCHEMA, build_merge_sql, upsert_records


def test_schema_has_required_fields():
    names = [f.name for f in SCHEMA]
    for required in ("row_hash", "account_label", "run_date", "amount", "source_file", "ingested_at"):
        assert required in names


def test_merge_sql_references_stage_and_target():
    sql = build_merge_sql("proj", "raw", "fidelity_trades", "stage_x")
    assert "MERGE `proj.raw.fidelity_trades`" in sql
    assert "stage_x" in sql
    assert "ON T.row_hash = S.row_hash" in sql
    assert "WHEN NOT MATCHED THEN INSERT" in sql
    assert "WHEN MATCHED" not in sql


def test_to_bq_rows_dedupes_by_row_hash():
    from ingest.bigquery_loader import _to_bq_rows
    r = {"account_label": "LLC_MAIN", "source_file": "f.csv", "row_hash": "abc",
         "run_date": "2026-08-10", "action": "BUY", "symbol": "SPY", "description": "",
         "type": "", "price": "1", "quantity": "-1", "commission": "", "fees": "0.1",
         "accrued_interest": "", "amount": "10", "cash_balance": "Processing",
         "settlement_date": "2026-08-11", "currency": "USD", "exchange_rate": ""}
    rows = _to_bq_rows([dict(r), dict(r)])
    assert len(rows) == 1
    assert rows[0]["row_hash"] == "abc"


def test_to_bq_rows_empty_strings_become_none():
    from ingest.bigquery_loader import _to_bq_rows
    r = {"account_label": "LLC_MAIN", "source_file": "f.csv", "row_hash": "abc",
         "run_date": "", "action": "", "symbol": "SPY", "description": "",
         "type": "", "price": "not-a-float", "quantity": "-1", "commission": "",
         "fees": "", "accrued_interest": "", "amount": "10",
         "cash_balance": "Processing", "settlement_date": "", "currency": "USD",
         "exchange_rate": ""}
    rows = _to_bq_rows([r])
    row = rows[0]
    assert row["run_date"] is None
    assert row["action"] is None
    assert row["price"] is None
    assert row["cash_balance"] is None


def test_safe_float_strips_commas():
    from ingest.bigquery_loader import _safe_float
    assert _safe_float("1,234.56") == 1234.56
    assert _safe_float("") is None
    assert _safe_float("Processing") is None


def test_upsert_records_requires_project_id():
    with pytest.raises(ValueError, match="GCP_PROJECT_ID"):
        upsert_records({"project_id": None, "raw_dataset": "raw"}, [])
