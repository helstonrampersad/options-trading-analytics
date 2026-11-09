import duckdb

from ingest.duckdb_loader import load_records


def _record(amount, row_hash, run_date="2024-01-15"):
    return {
        "run_date": run_date,
        "action": "YOU SOLD OPENING TRANSACTION PUT -PLTR240119P15",
        "symbol": " -PLTR240119P15",
        "description": "PUT PLTR 19 JAN 24 $15",
        "type": "Trade",
        "price": "1.50",
        "quantity": "-1",
        "commission": "-1.00",
        "fees": "0",
        "accrued_interest": None,
        "amount": "150.00",
        "cash_balance": "1000.00",
        "settlement_date": "2024-01-16",
        "currency": "USD",
        "exchange_rate": "1.0",
        "account_label": "LLC_MAIN",
        "source_file": "History_for_Account_LLC_MAIN (1).csv",
        "row_hash": row_hash,
    }


def test_load_records_is_idempotent(tmp_path):
    db = tmp_path / "trades.duckdb"
    records = [
        _record("150.00", "hash-a"),
        _record("150.00", "hash-a"),
        _record("200.00", "hash-b"),
    ]

    first = load_records(records, str(db))
    assert first["inserted"] == 2

    second = load_records(records, str(db))
    assert second["inserted"] == 0

    con = duckdb.connect(str(db))
    count = con.execute("SELECT COUNT(*) FROM raw.fidelity_trades").fetchone()[0]
    uniq = con.execute("SELECT COUNT(DISTINCT row_hash) FROM raw.fidelity_trades").fetchone()[0]
    assert count == 2
    assert uniq == 2
    con.close()


def test_load_records_coerces_numeric_strings(tmp_path):
    db = tmp_path / "trades.duckdb"
    load_records([_record("150.00", "hash-a")], str(db))

    con = duckdb.connect(str(db))
    amount, price, accrued = con.execute(
        "SELECT amount, price, accrued_interest FROM raw.fidelity_trades"
    ).fetchone()
    assert amount == 150.0
    assert price == 1.5
    assert accrued is None
    con.close()
