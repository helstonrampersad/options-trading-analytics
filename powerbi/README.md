# Power BI layer — Options Trading Analytics

The visualization layer for the pipeline: connect **Power BI Desktop** (free, Windows-only)
to the three dbt marts — `fct_wheel_mechanics`, `fct_cash_secured_puts`,
`fct_covered_call_premiums` — and build a three-page report from `dashboard-spec.md`.

The report is prepared here but **not built or published**: you build it locally in Power BI
Desktop and the `.pbix` stays on your machine (gitignored). This folder ships everything
needed — an offline export script, DAX measures, a theme, the page-by-page build spec, a data
dictionary, and synthetic sample data so anyone can demo without private trades.

## What you'll build

- **Wheel Overview** — KPI cards, monthly premium/P&L trend, P&L by strategy, top tickers, slicers.
- **CSPs & Covered Calls** — put/call lifecycle funnels, P&L by ticker, strike/DTE views, account matrix.
- **Data Quality & Ops** — latest run date, mart row counts, strategy mix, reconciliation note.

## Quick start

1. Install Power BI Desktop (section 1).
2. Connect the marts (section 2, Option A BigQuery or Option B local export).
3. Import `theme.json`, add the measures from `measures.dax`, then follow `dashboard-spec.md`.
4. Save as `powerbi/OptionsTrading.pbix` (gitignored) and screenshot page 1 into `screenshots/`.

## Contents

| Path | Purpose |
|---|---|
| `README.md` | this guide — install, connect, build, screenshot |
| `export_marts.py` | export DuckDB raw/staging/marts to CSV or Parquet |
| `measures.dax` | DAX measures for the report (P&L, premium, counts, ratios, freshness) |
| `theme.json` | Power BI report theme — dark-blue/teal finance palette |
| `dashboard-spec.md` | exact 30–45 minute build spec for the three report pages |
| `DATA_DICTIONARY.md` | mart grains, columns, and staging fields used by the report |
| `sample_data/` | synthetic CSVs in the mart schemas — safe to commit, no private data |
| `screenshots/` | placeholder for report screenshots linked from the repo README |

## 1. Install Power BI Desktop

Power BI Desktop is **free** and **Windows-only** (there is no macOS or Linux version). It is
the report authoring tool; publishing to the Power BI Service is a separate, optional step.
Pick one of the three installation routes:

**Option 1 — winget (PowerShell):**

```powershell
winget install --id Microsoft.PowerBI -e --accept-package-agreements --accept-source-agreements
```

If your winget build does not recognise that ID, run `winget search "Power BI Desktop"` and
install the Microsoft-published package that appears.

**Option 2 — Microsoft Store:** open the Store, search for **"Power BI Desktop"**, and install
the app published by Microsoft. The Store version updates itself automatically.

**Option 3 — official Microsoft download page:** follow the instructions at
[Get Power BI Desktop](https://learn.microsoft.com/en-us/power-bi/fundamentals/desktop-get-the-desktop)
and choose the 64-bit installer. Reinstalling over an older version keeps report files.

## 2. Connect the data

Choose the path that fits: **BigQuery** for the real pipeline, **local export** for offline
work, or **DuckDB ODBC** for a live local connection.

### Option A — BigQuery (native connector)

Use this when the BigQuery pipeline has produced the marts (`make pipeline`; datasets
`raw`, `analytics_staging`, `analytics_marts`).

1. Power BI Desktop → **Get Data**.
2. **Database → Google BigQuery → Connect**. The connector ships with Power BI Desktop; if it
   is missing, update the app.
3. Sign in with the Google account that can read the GCP project (OAuth in the browser).
4. In the Navigator, expand the project, then the **`analytics_marts`** dataset. The default
   dataset name comes from dbt: `GCP_ANALYTICS_DATASET` (default `analytics`) + `_marts`.
5. Tick `fct_wheel_mechanics`, `fct_cash_secured_puts`, `fct_covered_call_premiums` → **Load**.
   Optionally load `analytics_staging` views as well for trade-level detail.

Reference: [Google BigQuery connector](https://learn.microsoft.com/en-us/power-query/connectors/google-bigquery).
Refreshes need the Google credential; Power BI prompts on the first refresh. Do **not** load the
`raw` dataset into the report.

### Option B — local DuckDB export (offline, no cloud)

Use this for a self-contained demo, a machine without GCP access, or the synthetic samples.

1. Build the local marts first: `./run.sh daily` (or `make local`). This creates
   `data/local.duckdb`.
2. Export them for Power BI:

   ```bash
   python powerbi/export_marts.py
   # equivalent Makefile shortcut:
   make powerbi
   ```

   Defaults: `--db data/local.duckdb --out data/exports/powerbi --format csv`. Add
   `--format parquet` for Parquet files, or `--schemas marts` to export only the marts.
3. The folder gets one file per object (`marts__fct_wheel_mechanics.csv`, ...) plus
   `_manifest.csv` with schema / table / file / row_count / exported_at.
4. Power BI Desktop → **Get Data → Text/CSV** (or **Parquet**), select the `fct_*.csv` files
   from `data/exports/powerbi/`. Keep delimiter **Comma**; dates parse automatically.
5. **Rename the queries** to the bare table names — `marts__fct_wheel_mechanics` →
   `fct_wheel_mechanics` — because `measures.dax` references those names.
6. **Load**, then continue with the build spec.

The export contains private data: `data/exports/` is gitignored and must never be committed.

### Option C — DuckDB ODBC (advanced, optional)

For a live local connection that refreshes without CSV files:

1. Install the **64-bit DuckDB ODBC driver** (see the
   [DuckDB ODBC docs](https://duckdb.org/docs/stable/clients/odbc/overview)); bitness must
   match Power BI Desktop.
2. Register a DSN in the Windows **ODBC Data Source Administrator** pointing at
   `data/local.duckdb`.
3. Power BI → **Get Data → ODBC** → pick the DSN → open the `marts` schema and load the three
   `fct_*` tables.
4. Keep the DuckDB file closed for writers while Power BI reads it (DuckDB is single-writer).

This is the least portable option; the CSV/Parquet route (Option B) is enough for a portfolio demo.

## 3. Build the report

1. Import the theme: **View → Themes → Browse for themes** → `powerbi/theme.json`.
2. Create a blank `_Measures` table and add the measures from `measures.dax`.
3. Follow **`dashboard-spec.md`** page by page (Wheel Overview, CSPs & Covered Calls,
   Data Quality & Ops).
4. **File → Save as** → `powerbi/OptionsTrading.pbix`. It is gitignored — never commit it.

## 4. Demo without private data

`sample_data/` holds hand-written synthetic CSVs in the exact mart schemas (10 wheel / 6 puts /
6 calls rows, invented tickers and premiums). They are safe to commit and let anyone build
the report without the owner's trades: import them like Option B, skipping the export step.
See `sample_data/README.md` for the manifest and column dictionary.

## 5. Screenshots for the repo README

`screenshots/` is an empty placeholder (`.gitkeep`) so the folder exists in git. After
building page 1, capture it (`Win+Shift+S`, or **File → Export → PDF** and crop) and save it
as `powerbi/screenshots/wheel-overview.png` (optionally `csp-covered-calls.png`), then link
the image from the repo README. For public screenshots use the **synthetic sample data**, not
real balances — no account numbers or private P&L should appear in any committed image.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Google BigQuery is not in Get Data | Update Power BI Desktop; the connector is built in |
| `run_date` arrives as text | In Power Query, change the column type to **Date** (locale: English (United States)) |
| Measures error "cannot find table ..." | Rename the Power Query queries to the bare `fct_*` names |
| Refresh can't find the file | Re-run `python powerbi/export_marts.py`; don't move `data/exports/powerbi/` |
| "Could not open database" from the export | Close other DuckDB GUIs/pipeline runs (single-writer), then retry |

## Privacy & reproducibility

- Only synthetic `sample_data/` is committed; real exports and the `.pbix` are gitignored.
  No account numbers, credentials, or `.env` values belong anywhere in this folder.
- Rebuild: run the local pipeline → `python powerbi/export_marts.py` → refresh; on BigQuery
  run `make pipeline` → refresh. The pipeline is deterministic and fully idempotent.

