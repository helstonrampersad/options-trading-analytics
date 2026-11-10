# Synthetic sample data for the Power BI report

**These files are 100% synthetic and safe to commit.** They are hand-written rows with
invented trades, tickers, and premiums — no real account numbers, no real positions, no real
P&L. Account labels use the same anonymized labels as the pipeline (`LLC_MAIN`, `ROTH_IRA`;
the other two labels exist in the real data but are not needed for a sample).

They exist so anyone cloning the repo can build and demo the Power BI report without
credentials or private data. For the owner's real numbers, run the local pipeline
(`./run.sh daily`) and export instead: `python powerbi/export_marts.py`.

## Files

Each CSV is a small excerpt in the **exact mart schema** produced by dbt
(`dbt_local/models/marts/*.sql`), so it can be imported as-is.

| File | dbt model | Grain | Rows |
|---|---|---|---|
| `fct_wheel_mechanics.csv` | `marts.fct_wheel_mechanics` | run_date, account_label, ticker, strategy | 10 |
| `fct_cash_secured_puts.csv` | `marts.fct_cash_secured_puts` | run_date, account_label, ticker | 6 |
| `fct_covered_call_premiums.csv` | `marts.fct_covered_call_premiums` | run_date, account_label, ticker | 6 |
| `dashboard_synthetic.csv` | combined table from `build_dashboard_dataset.py` | run_date, account_label, ticker, strategy, source | 620 |

`dashboard_synthetic.csv` is the **fast path** for building the report: one import, no
relationships. It is generated deterministically by
`python powerbi/build_dashboard_dataset.py --mode synthetic` and uses the same column set as
the real combined export (`data/exports/powerbi/dashboard.csv`, gitignored).

The three files are mutually consistent on purpose: for these rows,
`fct_wheel_mechanics` equals the union of the put and call groups (same
`run_date` / `account_label` / `ticker`), so you can sanity-check the model and
demonstrate the reconciliation logic on the data-quality page. Rows cover every
strategy value used by the report (`PLTR_wheel`, `csp`, `covered_call`, `leap`,
`day_trade`; `other` is a valid value but not present in these excerpts) and
include assignment, expiration, and buy-to-close activity.

## Column dictionary

All amounts are USD and use the Fidelity statement sign (credits positive). Dates are ISO
`YYYY-MM-DD`; `updated_at` is the pipeline load timestamp (same value in every sample row).

### `fct_wheel_mechanics.csv` — all option activity, one row per group

| Column | Type | Meaning |
|---|---|---|
| `run_date` | date | trade date (pipeline run date) |
| `account_label` | text | anonymized account: `LLC_MAIN`, `ROTH_IRA`, ... |
| `ticker` | text | underlying ticker parsed from the contract code |
| `strategy` | text | `PLTR_wheel`, `csp`, `covered_call`, `leap`, `day_trade`, `other` |
| `n_trades` | integer | option trade rows in this group |
| `n_sells` | integer | rows whose action contains `SOLD` |
| `n_assignments` | integer | rows whose action contains `ASSIGNED` |
| `net_cash_flow` | decimal | total option cash, assignment stock leg included |
| `net_pnl` | decimal | realized premium P&L, assignment cash excluded |
| `avg_dte` | decimal | average days to expiry for the group (floored at 0) |
| `updated_at` | timestamp | mart load timestamp |

### `fct_cash_secured_puts.csv` — all put option activity

| Column | Type | Meaning |
|---|---|---|
| `run_date`, `account_label`, `ticker` | — | group keys (see above) |
| `n_trades` | integer | put trade rows in this group |
| `n_puts_sold` | integer | rows whose action contains `SOLD` |
| `n_assignments` | integer | rows whose action contains `ASSIGNED` |
| `n_expired` | integer | rows whose action contains `EXPIRED` |
| `net_cash_flow` | decimal | total put cash (same sign convention) |
| `net_pnl` | decimal | realized put premium P&L |
| `last_strike` | decimal | highest strike seen in the group (`MAX(contract_strike)`) |
| `updated_at` | timestamp | mart load timestamp |

### `fct_covered_call_premiums.csv` — all call option activity

| Column | Type | Meaning |
|---|---|---|
| `run_date`, `account_label`, `ticker` | — | group keys (see above) |
| `n_trades` | integer | call trade rows in this group |
| `n_calls_sold` | integer | rows whose action contains `SOLD` |
| `n_called_away` | integer | rows whose action contains `ASSIGNED` (called away) |
| `n_expired` | integer | rows whose action contains `EXPIRED` |
| `net_cash_flow` | decimal | total call cash (same sign convention) |
| `net_pnl` | decimal | realized call premium P&L |
| `premium_collected` | decimal | cash from sold (opening) calls only |
| `updated_at` | timestamp | mart load timestamp |

## Loading in Power BI Desktop

1. **Get Data → Text/CSV**, pick one file at a time (repeat for all three).
2. When prompted, keep **Delimiter = Comma**, **Data Type Detection = Based on first 200 rows**.
3. Rename each query to the bare table name (`fct_wheel_mechanics`, ...) — the measures in
   `../measures.dax` reference those names.
4. Build the shared model described in `../dashboard-spec.md` Step 0 (a small `DimAccount`
   table plus one-to-many relationships that filter the facts) so the account slicer filters
   all three tables. The same model applies when you import the real export instead of these
   samples.
