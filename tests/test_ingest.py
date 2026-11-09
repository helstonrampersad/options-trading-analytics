import sys

import ingest.ingest as ingest_mod
from ingest.ingest import build_records, init_raw

CSV = "Run Date,Action,Symbol,Description,Type,Price ($),Quantity,Commission ($),Fees ($),Accrued Interest ($),Amount ($),Cash Balance ($),Settlement Date\n08/10/2026,YOU SOLD ASSIGNED CALLS, -PLTR260807C155,CALL (PLTR) PALANTIR AUG 07 26 $155 (100 SHS),Cash,155,-200,,0.64,,30999.36,Processing,08/10/2026\n"


def test_init_raw_copies_idempotently(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    dest = tmp_path / "dest"
    (src / "History_for_Account_Z90000000 (1).csv").write_text(CSV)
    first = init_raw([str(src)], str(dest))
    assert len(first) == 1
    second = init_raw([str(src)], str(dest))
    assert second == []
    assert (dest / "History_for_Account_Z90000000 (1).csv").exists()


def test_build_records_attaches_label_and_hash(tmp_path):
    p = tmp_path / "History_for_Account_Z90000000 (1).csv"
    p.write_text(CSV)
    cfg = {"account_map": {"Z90000000": "LLC_MAIN"}, "file_map": {}}
    recs = build_records([str(p)], cfg)
    assert len(recs) == 1
    r = recs[0]
    assert r["account_label"] == "LLC_MAIN"
    assert r["source_file"] == "History_for_Account_LLC_MAIN (1).csv"
    assert len(r["row_hash"]) == 32
    assert "Z90000000" not in str(r["source_file"])


def test_build_records_skips_unknown(tmp_path):
    p = tmp_path / "History_for_Account_ZZ00000 (1).csv"
    p.write_text(CSV)
    recs = build_records([str(p)], {"account_map": {}, "file_map": {}})
    assert recs == []


def test_build_records_occurrence_dedup(tmp_path):
    cfg = {"account_map": {"Z90000000": "LLC_MAIN"}, "file_map": {}}
    p1 = tmp_path / "History_for_Account_Z90000000 (1).csv"
    p2 = tmp_path / "History_for_Account_Z90000000 (2).csv"
    p1.write_text(CSV)
    p2.write_text(CSV)
    recs = build_records([str(p1), str(p2)], cfg)
    assert len(recs) == 2
    assert recs[0]["row_hash"] == recs[1]["row_hash"]  # same trade re-exported -> loaders dedup

    row_settled = CSV.split("\n")[1].replace("Processing", "-999.99")
    csv_settled = CSV.replace(CSV.split("\n")[1], row_settled)
    row2 = CSV.split("\n")[1].replace("Processing", "-123.45")
    p3 = tmp_path / "History_for_Account_Z90000000 (3).csv"
    p3.write_text(csv_settled + row2 + "\n")  # same trade twice in one file, both settled
    recs3 = build_records([str(p3)], cfg)
    assert len(recs3) == 2
    assert recs3[0]["row_hash"] != recs3[1]["row_hash"]


def test_build_records_prefers_settled_twin(tmp_path):
    settled = CSV.split("\n")[1].replace("Processing", "-123.45")
    p = tmp_path / "History_for_Account_Z90000000 (4).csv"
    p.write_text(CSV + settled + "\n")  # placeholder twin: only the settled row survives
    cfg = {"account_map": {"Z90000000": "LLC_MAIN"}, "file_map": {}}
    assert len(build_records([str(p)], cfg)) == 1


def test_init_raw_exits_without_upload(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        ingest_mod,
        "load_config",
        lambda env: {"project_id": "p", "account_map": {}, "file_map": {}},
    )
    monkeypatch.setattr(
        ingest_mod,
        "init_raw",
        lambda sources, dest: calls.append((sources, dest)) or [],
    )
    import ingest.bigquery_loader as bq

    def fail_upsert(*args, **kwargs):
        raise AssertionError("upsert_records must not run with --init-raw")

    monkeypatch.setattr(bq, "upsert_records", fail_upsert)
    monkeypatch.setattr(sys, "argv", ["ingest", "--init-raw", "--source-dir", str(tmp_path)])
    ingest_mod.main()
    assert len(calls) == 1
