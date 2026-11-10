# Power BI report build spec — Options Trading Analytics

Build the report in Power BI Desktop in **30–45 minutes**. All visuals use the three dbt
marts and the measures in `measures.dax`; the data connection is explained in `README.md`
(BigQuery connector, local CSV/Parquet export, or `sample_data/` for a private-data-free demo).

You need: Power BI Desktop installed, the three mart tables loaded, and this folder open on
a second screen (or printed) so you can copy field names.

## Fastest path — one combined table

`build_dashboard_dataset.py` merges the three marts into a single flat table, so the whole
report can be built from **one import** (no relationships, no query renames). Build it with
`./run.sh powerbi` (real data, local only) or use the committed synthetic
`sample_data/dashboard_synthetic.csv` (620 rows, safe to share). Load it with
**Get Data → Text/CSV**, rename the query to `dashboard`, then add these quick measures
(Modeling → New measure):

```dax
Total Net P&L  = SUM(dashboard[net_pnl])
Total Premium  = SUM(dashboard[premium])
Total Trades   = SUM(dashboard[trades])
Active Tickers = DISTINCTCOUNT(dashboard[ticker])
Last Run Date  = MAX(dashboard[run_date])
```

| Page | Visual | Type | Fields (filter notes) |
|---|---|---|---|
| Wheel Overview | Net P&L / Premium / Trades / Tickers | Cards | the four measures above |
| Wheel Overview | P&L by strategy | Clustered bar | Axis `strategy`, Values `[Total Net P&L]`; filter `source` is `wheel` |
| Wheel Overview | Monthly P&L trend | Line chart | Axis `run_date` (Month), Values `[Total Net P&L]`; filter `source` is `wheel` |
| Wheel Overview | Account slicer | Slicer | `account_label` |
| CSPs & Covered Calls | Put activity | Table | `account_label`, `ticker`, `sells`, `assignments`, `expiries`; filter `source` is `puts` |
| CSPs & Covered Calls | Call premium by ticker | Clustered bar | Axis `ticker`, Values `[Total Premium]`; filter `source` is `calls` |
| CSPs & Covered Calls | Activity split | Donut | Legend `source`, Values `[Total Trades]` |
| Data Quality & Ops | Freshness / size | Cards + table | `[Last Run Date]`, `COUNTROWS(dashboard)`, table of `source` by row count |

Continue below only if you want the richer three-mart model (separate `fct_*` tables,
`DimAccount`, and the full `measures.dax` set).

## Step 0 — data + model (5 min)

1. **Get Data** and load the three marts (`fct_wheel_mechanics`, `fct_cash_secured_puts`,
   `fct_covered_call_premiums`).
2. **Rename the queries** to the bare mart names (`Home → Transform data → right-click →
   Rename`). The CSV export names them `marts__fct_*`; the measures will not resolve until
   they are renamed.
3. **Import the theme:** `View → Themes → Browse for themes → powerbi/theme.json`.
4. **Create the measures table:** `Modeling → New table` → `_Measures = { }`, then add each
   measure from `measures.dax` (`Modeling → New measure`, paste one at a time).
5. **Create `DimAccount`:** `Home → Enter data`, add one column `account_label` with
   `LLC_MAIN`, `ROTH_IRA`, `ROLLOVER_IRA`, `INDIVIDUAL_LEGACY`. In Model view, create
   many-to-one, single-direction relationships from `[account_label]` in each of the three
   fact tables to `DimAccount[account_label]` (drag column onto column). This lets one
   account slicer filter every visual on every page.
6. Canvas **16:9** and three page tabs: `Wheel Overview`, `CSPs & Covered Calls`,
   `Data Quality & Ops`.

## Page 1 — Wheel Overview

Layout: KPI cards across the top, slicers in a strip under them, monthly trend on the left,
bar chart top-right, ticker table bottom-right.

| Visual | Chart type | Fields | Formatting tips |
|---|---|---|---|
| Header | Text box | "Options Trading Analytics — Wheel Overview" | 20 pt, theme foreground color |
| Net P&L card | Card | `[Total Net P&L]` | Currency, 2 decimals, accent color |
| Premium card | Card | `[Total Premium]` | Rename title "Premium Collected"; currency |
| Trades card | Card | `[Trades]` | Whole number |
| Active tickers card | Card | `[Active Tickers]` | Whole number |
| Monthly trend | Line chart | Axis `fct_wheel_mechanics[run_date]` (use the **Month** level), Values `[Total Premium]` and `[Total Net P&L]` | Legend top, no data labels, line width 2; if you prefer a flat text axis, add a calculated column `Month = FORMAT(fct_wheel_mechanics[run_date], "YYYY-MM")` and use it (sorts correctly) |
| P&L by strategy | Clustered bar chart | Axis `fct_wheel_mechanics[strategy]`, Values `[P&L by Strategy]` | Sort descending; data labels on; title "Net P&L by strategy" |
| Top tickers | Table | Rows `fct_wheel_mechanics[ticker]`, Values `[Total Net P&L]`, `[Trades]`, `[Avg DTE]` | Visual filter `ticker` → Top N 10 by `[Total Net P&L]`; sort by P&L desc; data bars on P&L |
| Slicers | Slicers, top row | `DimAccount[account_label]`, `fct_wheel_mechanics[strategy]`, `fct_wheel_mechanics[run_date]` (Between) | Horizontal slicers, 1 row; date slider styled with theme accent |

## Page 2 — CSPs & Covered Calls

Layout: two lifecycle funnels on the left, P&L by ticker top-right, strike/DTE views middle,
account matrix at the bottom.

Funnels need a stage order, so create two tiny disconnected tables first
(**Modeling → New table**, DAX):

```dax
PutFunnel  = DATATABLE ( "Stage", STRING, "Order", INTEGER, { { "Sold", 1 }, { "Assigned", 2 }, { "Expired", 3 } } )
CallFunnel = DATATABLE ( "Stage", STRING, "Order", INTEGER, { { "Sold", 1 }, { "Called away", 2 }, { "Expired", 3 } } )
```

and two measures (create them in `_Measures` once the tables exist):

```dax
Put Funnel Value  = SWITCH ( SELECTEDVALUE ( PutFunnel[Stage] ),  "Sold", [Puts Sold],  "Assigned", [Puts Assigned],  "Expired", [Puts Expired] )
Call Funnel Value = SWITCH ( SELECTEDVALUE ( CallFunnel[Stage] ), "Sold", [Calls Sold], "Called away", [Calls Called Away], "Expired", [Calls Expired] )
```

| Visual | Chart type | Fields | Formatting tips |
|---|---|---|---|
| Put lifecycle | Funnel | Category `PutFunnel[Stage]`, Values `[Put Funnel Value]` | Title "Puts: sold → assigned / expired"; right-click the stage column → **Sort by column → Order** |
| Call lifecycle | Funnel | Category `CallFunnel[Stage]`, Values `[Call Funnel Value]` | Same styling; teal palette from the theme |
| P&L by ticker | Bar chart | Axis `fct_wheel_mechanics[ticker]`, Values `[Total Net P&L]` | Sort descending, data labels, conditional color by sign |
| Strike view | Column chart | Axis `fct_cash_secured_puts[last_strike]`, Values `[Puts Sold]` | Strike exists only in the puts mart (`last_strike`); title "Puts sold by strike" |
| DTE view | Column chart | Axis `fct_wheel_mechanics[ticker]`, Values `[Avg DTE]` | Optional bucket: calculated column `DTE Bucket = SWITCH(TRUE(), fct_wheel_mechanics[avg_dte] <= 7, "0-7d", fct_wheel_mechanics[avg_dte] <= 30, "8-30d", fct_wheel_mechanics[avg_dte] <= 90, "31-90d", "90d+")` and use it as the axis |
| Account matrix | Matrix | Rows `DimAccount[account_label]`, Values `[Puts Sold]`, `[Puts Assigned]`, `[Calls Sold]`, `[Calls Called Away]`, `[Assignment Rate]` | Assignment rate as %, conditional color scale on it |

## Page 3 — Data Quality & Ops

Layout: a row of four cards, "rows by account" chart, "rows by day" table, strategy donut on
the right, reconciliation note as a text box at the bottom.

| Visual | Chart type | Fields | Formatting tips |
|---|---|---|---|
| Latest run | Card | `[Latest Run Date]` | Short date format; title "Latest pipeline run" |
| Run days | Card | `[Run Days]` | Whole number |
| Groups | Card | `[Groups]` | Whole number; title "Mart rows (groups)" |
| Other share | Card | `[Other Strategy Share]` | Percentage |
| Rows by account | Clustered column | Axis `DimAccount[account_label]`, Values `[Wheel Groups]`, `[Put Groups]`, `[Call Groups]` | Legend top; mart row counts per account |
| Rows by day | Table | Rows `fct_wheel_mechanics[run_date]`, Values `[Wheel Groups]` | Sort date descending; mention "wheel rows" in the title |
| Strategy mix | Donut | Legend `fct_wheel_mechanics[strategy]`, Values `[Trades]` | Shows the `other` slice next to `Other Strategy Share` |
| Reconciliation note | Text box | dbt tests `reconcile_pnl`, `reconcile_puts_pnl`, `reconcile_calls_pnl` compare staging cash flow with each mart per account/day and fail above $0.01; run `./run.sh test` (or `make test-local`) to re-verify. | 10 pt, muted color |

## Save, screenshot, and ship

1. **File → Save as** → `powerbi/OptionsTrading.pbix`. It is gitignored — **never commit it**.
2. Take a screenshot of page 1 (`Win+Shift+S`, or Power BI `File → Export → PDF` then crop)
   and save it as `powerbi/screenshots/wheel-overview.png` (page 2 optional:
   `csp-covered-calls.png`). Add them to the repo README later.
3. Refresh: with the CSV/Parquet path, re-run `python powerbi/export_marts.py`, replace the
   files, then `Home → Refresh`. With BigQuery, just `Refresh` (credentials required).

## Formatting conventions

- Titles: "Net P&L", "Premium collected", "Trades" — sentence case, no axis titles.
- Currency: `$#,##0.00`; percentages: `0.0%`; dates: `yyyy-mm-dd`.
- Keep the theme's dark-blue/teal palette; color negative P&L with the theme `bad` red.
- Don't add a date table unless you need MTD/YTD — see the `DimDate` note in `measures.dax`.

## Final checklist

- [ ] Three pages named as above, theme applied, all measures resolving.
- [ ] `DimAccount` slicer filters every page; strategy/date slicers work on page 1.
- [ ] No errors in the visual headers after `Home → Refresh`.
- [ ] `OptionsTrading.pbix` saved locally and still untracked (`git status` shows nothing new).
- [ ] Screenshot saved under `powerbi/screenshots/` using synthetic data for public sharing.
