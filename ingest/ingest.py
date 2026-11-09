import argparse
import hashlib
import logging
from pathlib import Path

from ingest.anonymize import label_for_filename, sanitize_filename
from ingest.config import load_config
from ingest.parse_fidelity import hash_file_rows, parse_file

log = logging.getLogger("ingest")


def _sha1(path):
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def init_raw(source_dirs, dest):
    dest_dir = Path(dest)
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for src in source_dirs:
        for csv_path in sorted(Path(src).glob("*.csv")):
            target = dest_dir / csv_path.name
            digest = _sha1(csv_path)
            exists_same = target.exists() and _sha1(target) == digest
            if exists_same:
                continue
            target.write_bytes(Path(csv_path).read_bytes())
            copied.append(str(target))
    return copied


def build_records(csv_paths, cfg):
    records = []
    for path in csv_paths:
        name = Path(path).name
        safe_name = sanitize_filename(name, cfg["account_map"])
        try:
            label = label_for_filename(name, cfg["account_map"], cfg["file_map"])
        except ValueError as exc:
            log.warning("skipping %s: %s", safe_name, exc)
            continue
        file_records = []
        for raw in parse_file(str(path), safe_name):
            raw["account_label"] = label
            raw["source_file"] = safe_name
            file_records.append(raw)
        records.extend(hash_file_rows(file_records))
        log.info("%s: %d rows", safe_name, len(file_records))
    return records


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Ingest Fidelity trade CSVs into BigQuery")
    parser.add_argument("--init-raw", action="store_true", help="copy CSVs into data/raw/ first")
    parser.add_argument("--dry-run", action="store_true", help="parse only; do not write to BigQuery")
    parser.add_argument("--strict", action="store_true", help="fail on unknown files instead of skipping")
    parser.add_argument("--env", default=".env", help="path to .env")
    parser.add_argument("--source-dir", default="data/raw", help="directory to scan for CSVs")
    args = parser.parse_args()

    cfg = load_config(args.env)
    if args.init_raw:
        sources = [".", str(Path(__file__).resolve().parents[1] / "data" / "raw"),
                   str(Path(__file__).resolve().parents[1].parent / "optionsDayTrade")]
        init_raw(sources, args.source_dir)
        return
    csv_paths = sorted(Path(args.source_dir).glob("*.csv"))
    records = build_records([str(p) for p in csv_paths], cfg)
    if args.strict:
        unlabeled = [str(p) for p in csv_paths if not _has_label(p, cfg)]
        if unlabeled:
            raise SystemExit(f"strict: unknown files: {unlabeled}")
    if args.dry_run:
        for r in records[:5]:
            log.info("sample: %s", {k: r[k] for k in ("account_label", "run_date", "action", "symbol", "amount", "row_hash")})
        log.info("dry-run total records: %d", len(records))
        return
    from ingest.bigquery_loader import upsert_records
    upsert_records(cfg, records)


def _has_label(path, cfg):
    try:
        label_for_filename(Path(path).name, cfg["account_map"], cfg["file_map"])
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
