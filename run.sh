#!/usr/bin/env bash
# Local entry point for the pipeline - works on WSL2/Ubuntu/Git Bash (no make needed).
#
# Usage: ./run.sh <command>        (run ./run.sh help for the full command list)
#
# Environment overrides:
#   SOURCE_DIR   folder with the Fidelity CSV exports (default: ../optionsDayTrade)
#   DUCKDB_PATH  local DuckDB file (default: data/local.duckdb)
set -euo pipefail
cd "$(dirname "$0")"

VENV=.venv
SOURCE_DIR="${SOURCE_DIR:-../optionsDayTrade}"
DUCKDB_PATH="${DUCKDB_PATH:-$PWD/data/local.duckdb}"
export DUCKDB_PATH

usage() {
  cat <<'EOF'
Usage: ./run.sh <command>

Commands:
  setup    Create (or recreate) .venv with Python 3.11 and install pinned deps.
  daily    Ingest new CSVs from SOURCE_DIR, then run dbt locally (incremental).
  full     Same as daily, but rebuild marts with --full-refresh.
  test     Run pytest and the dbt tests for dbt_local.
  sample   Run the whole local pipeline on the committed synthetic fixture
           (tests/fixtures/sample_history.csv) - no cloud, no private data.
  powerbi  Export marts to data/exports/powerbi for the Power BI report.
  query    Run a read-only SQL query, e.g. ./run.sh query "SELECT 1".
  help     Show this help.

Environment overrides:
  SOURCE_DIR   folder with Fidelity CSVs (default: ../optionsDayTrade)
  DUCKDB_PATH  local DuckDB file (default: data/local.duckdb)
EOF
}

source_venv() {
  # Linux/WSL venvs use bin/, Windows/Git Bash venvs use Scripts/.
  if [ -f "$VENV/bin/activate" ]; then
    # shellcheck disable=SC1091
    . "$VENV/bin/activate"
  elif [ -f "$VENV/Scripts/activate" ]; then
    # shellcheck disable=SC1091
    . "$VENV/Scripts/activate"
  else
    echo "error: no activate script in $VENV. Run: ./run.sh setup" >&2
    exit 1
  fi
}

setup_venv() {
  if command -v uv >/dev/null 2>&1; then
    echo "== creating .venv with uv (Python 3.11) =="
    uv venv --clear "$VENV" --python 3.11
    source_venv
    echo "== installing pinned dependencies =="
    if ! uv pip install -r requirements.txt -r requirements-dev.txt; then
      echo "error: dependency install failed. Check your network and requirements.txt." >&2
      exit 1
    fi
  else
    if ! command -v python3 >/dev/null 2>&1; then
      echo "error: python3 not found. Install Python 3.11 (or uv) and retry." >&2
      exit 1
    fi
    echo "== creating .venv with python3 (uv not found) =="
    rm -rf "$VENV"
    python3 -m venv "$VENV"
    source_venv
    echo "== installing pinned dependencies =="
    python -m pip install --upgrade pip
    if ! python -m pip install -r requirements.txt -r requirements-dev.txt; then
      echo "error: dependency install failed. Check your network and requirements.txt." >&2
      exit 1
    fi
  fi
}

activate_venv() {
  if [ ! -d "$VENV" ]; then
    echo "error: no .venv found. Run: ./run.sh setup" >&2
    exit 1
  fi
  source_venv
  if ! command -v dbt >/dev/null 2>&1; then
    echo "error: dbt is not installed in .venv. Re-run: ./run.sh setup" >&2
    exit 1
  fi
}

dbt_local() {
  dbt "$@" --project-dir dbt_local --profiles-dir dbt_local
}

case "${1:-help}" in
  setup)
    setup_venv
    echo "setup complete. Next: ./run.sh sample"
    ;;
  daily)
    activate_venv
    echo "== ingest (SOURCE_DIR=$SOURCE_DIR) =="
    python -m ingest.duckdb_loader --db "$DUCKDB_PATH" --source-dir "$SOURCE_DIR"
    echo "== dbt run (incremental) =="
    dbt_local run
    ;;
  full)
    activate_venv
    echo "== ingest + full dbt rebuild (SOURCE_DIR=$SOURCE_DIR) =="
    python -m ingest.duckdb_loader --db "$DUCKDB_PATH" --source-dir "$SOURCE_DIR"
    dbt_local run --full-refresh
    ;;
  test)
    activate_venv
    python -m pytest tests/ -q
    dbt_local test
    ;;
  sample)
    activate_venv
    mkdir -p data
    sample_db="$PWD/data/sample.duckdb"
    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' EXIT
    cp tests/fixtures/sample_history.csv "$tmpdir/"
    printf 'GCP_PROJECT_ID=local-sample\nFILE_sample_history=LLC_MAIN\n' > "$tmpdir/sample.env"
    rm -f "$sample_db"
    echo "== sample ingest: tests/fixtures/sample_history.csv -> data/sample.duckdb =="
    python -m ingest.duckdb_loader --db "$sample_db" --source-dir "$tmpdir" --env "$tmpdir/sample.env"
    export DUCKDB_PATH="$sample_db"
    echo "== dbt run (dbt_local) =="
    dbt_local run
    echo "== dbt test (dbt_local) =="
    dbt_local test
    echo "sample pipeline complete: data/sample.duckdb (gitignored, safe to delete)"
    ;;
  powerbi)
    activate_venv
    mkdir -p data/exports/powerbi
    python powerbi/export_marts.py --db "$DUCKDB_PATH" --out data/exports/powerbi
    ;;
  query)
    activate_venv
    shift
    if [ "$#" -eq 0 ]; then
      echo "usage: ./run.sh query \"SELECT ...\"" >&2
      exit 1
    fi
    python - "$*" <<'PY'
import os
import sys

import duckdb

db = os.environ.get("DUCKDB_PATH", "data/local.duckdb")
con = duckdb.connect(db, read_only=True)
rows = con.execute(sys.argv[1]).fetchall()
cols = [d[0] for d in con.description]
print(" | ".join(cols))
for r in rows:
    print(" | ".join("" if v is None else str(v) for v in r))
PY
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "error: unknown command: $1" >&2
    echo
    usage
    exit 1
    ;;
esac
