# Convenience targets for people who have GNU Make installed.
# `./run.sh` is the primary interface and needs nothing extra (WSL2/Ubuntu/Git Bash).
SHELL := /bin/bash
.DEFAULT_GOAL := help

DUCKDB_PATH := $(CURDIR)/data/local.duckdb
SAMPLE_DB := $(CURDIR)/data/sample.duckdb
SAMPLE_DIR := $(CURDIR)/data/sample
SOURCE_DIR ?= ../optionsDayTrade
DBT_BQ := dbt
DBT_BQ_FLAGS := --project-dir dbt_project --profiles-dir dbt_project
DBT_LOCAL := dbt
DBT_LOCAL_FLAGS := --project-dir dbt_local --profiles-dir dbt_local

.PHONY: help pipeline ingest dbt local local-load local-dbt local-full dbt-full test test-local test-dbt sample powerbi view clean

help:
	@echo "Options pipeline targets:"
	@echo "  make pipeline    - BigQuery: ingest CSVs then run dbt (staging + marts)"
	@echo "  make ingest      - BigQuery: ingest CSVs into raw.fidelity_trades (idempotent)"
	@echo "  make dbt         - BigQuery: dbt run"
	@echo "  make local       - DuckDB: load raw.fidelity_trades then dbt run (no cloud needed)"
	@echo "  make local-full  - DuckDB: same, but --full-refresh marts (use after adding older CSVs)"
	@echo "  make dbt-full    - BigQuery: dbt run --full-refresh (same reason)"
	@echo "  make local-load  - DuckDB: load CSVs into data/local.duckdb"
	@echo "  make local-dbt   - DuckDB: dbt run"
	@echo "  make sample      - DuckDB: end-to-end pipeline on the committed synthetic fixture"
	@echo "  make powerbi     - export marts to data/exports/powerbi for the Power BI report"
	@echo "  make view        - open data/local.duckdb in the duckdb CLI"
	@echo "  make test        - ruff + python unit tests (ingest + anonymization)"
	@echo "  make test-dbt    - BigQuery dbt tests (incl. P&L reconciliation)"
	@echo "  make test-local  - DuckDB dbt tests (incl. P&L reconciliation)"
	@echo ""
	@echo "CSV source folder: $(SOURCE_DIR)  (override: make local SOURCE_DIR=path/to/csvs)"

pipeline: ingest dbt

ingest:
	python3 -m ingest.ingest --source-dir "$(SOURCE_DIR)"

dbt:
	set -a; . ./.env 2>/dev/null; set +a; $(DBT_BQ) run $(DBT_BQ_FLAGS)

local: local-load local-dbt

local-full: local-load
	DUCKDB_PATH="$(DUCKDB_PATH)" $(DBT_LOCAL) run $(DBT_LOCAL_FLAGS) --full-refresh

dbt-full:
	set -a; . ./.env 2>/dev/null; set +a; $(DBT_BQ) run $(DBT_BQ_FLAGS) --full-refresh

local-load:
	python3 -m ingest.duckdb_loader --db data/local.duckdb --source-dir "$(SOURCE_DIR)"

local-dbt:
	DUCKDB_PATH="$(DUCKDB_PATH)" $(DBT_LOCAL) run $(DBT_LOCAL_FLAGS)

# End-to-end demo on tests/fixtures/sample_history.csv: no cloud, no private data.
sample:
	rm -rf "$(SAMPLE_DIR)" "$(SAMPLE_DB)"
	mkdir -p "$(SAMPLE_DIR)"
	cp tests/fixtures/sample_history.csv "$(SAMPLE_DIR)/"
	printf 'GCP_PROJECT_ID=local-sample\nFILE_sample_history=LLC_MAIN\n' > "$(SAMPLE_DIR)/sample.env"
	python3 -m ingest.duckdb_loader --db "$(SAMPLE_DB)" --source-dir "$(SAMPLE_DIR)" --env "$(SAMPLE_DIR)/sample.env"
	DUCKDB_PATH="$(SAMPLE_DB)" $(DBT_LOCAL) run $(DBT_LOCAL_FLAGS)
	DUCKDB_PATH="$(SAMPLE_DB)" $(DBT_LOCAL) test $(DBT_LOCAL_FLAGS)

# Export the marts plus the single combined Power BI table (gitignored output).
powerbi:
	python3 powerbi/export_marts.py --db "$(DUCKDB_PATH)" --out data/exports/powerbi
	python3 powerbi/build_dashboard_dataset.py --mode real --db "$(DUCKDB_PATH)" --out data/exports/powerbi/dashboard.csv

# ruff needs the dev tools: .venv/bin/activate, or ./run.sh setup installed them.
test:
	ruff check ingest tests scripts
	python3 -m pytest tests/ -q

test-dbt:
	set -a; . ./.env 2>/dev/null; set +a; $(DBT_BQ) test $(DBT_BQ_FLAGS)

test-local:
	DUCKDB_PATH="$(DUCKDB_PATH)" $(DBT_LOCAL) test $(DBT_LOCAL_FLAGS)

view:
	duckdb "$(DUCKDB_PATH)"

clean:
	rm -rf dbt_project/target dbt_project/logs dbt_local/target dbt_local/logs dbt_databricks/target dbt_databricks/logs
	rm -rf "$(SAMPLE_DIR)" "$(SAMPLE_DB)"
