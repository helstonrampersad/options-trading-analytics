# Data dictionary — Power BI model

Source of truth: `dbt_local/models/` (DuckDB, local), mirroring `dbt_project/models/` (BigQuery).
Power BI reads **only the marts**; `raw` is never exposed and `staging` is optional detail. On
BigQuery the datasets are `raw`, `analytics_staging`, `analytics_marts` (`GCP_RAW_DATASET` /
`GCP_ANALYTICS_DATASET` env vars; dbt appends `_staging` / `_marts` to the analytics dataset).

## Layers

| Layer | DuckDB | BigQuery | Contents | In report |
|---|---|---|---|---|
| raw | `raw.fidelity_trades` | `raw.fidelity_trades` | append-only landing, deduped on `row_hash` | no |
| staging | `staging.stg_fidelity_trades` | `analytics_staging.stg_fidelity_trades` | normalized view: casts, USD conversion, contract parse, strategy label | optional |
| marts | `marts.fct_*` | `analytics_marts.fct_*` | pre-aggregated activity (verified run: 869 wheel / 416 puts / 489 calls groups) | yes |

Marts are incremental merge-upserts keyed on their grain, reconciled by dbt tests
(`reconcile_pnl`, `reconcile_puts_pnl`, `reconcile_calls_pnl`).

## Marts

**`fct_wheel_mechanics`** — all option activity; grain `run_date`, `account_label`, `ticker`, `strategy`.

| Column | Type | Meaning |
|---|---|---|
| `run_date` | date | trade date |
| `account_label` | text | anonymized account label |
| `ticker` | text | underlying parsed from the contract code |
| `strategy` | text | `PLTR_wheel`, `csp`, `covered_call`, `leap`, `day_trade`, `other` |
| `n_trades` / `n_sells` / `n_assignments` | bigint | option rows / `SOLD` rows / `ASSIGNED` rows in the group |
| `net_cash_flow` | double | total option cash (assignment stock legs included when present) |
| `net_pnl` | double | realized premium P&L (assignment cash excluded) |
| `avg_dte` | double | average days to expiry in the group, floored at 0 |
| `updated_at` | timestamp | last mart load |

**`fct_cash_secured_puts`** — all put option activity; grain `run_date`, `account_label`, `ticker`.
Columns: `n_trades`, `n_puts_sold`, `n_assignments`, `n_expired`, `net_cash_flow`, `net_pnl`,
`last_strike` (highest strike in the group), `updated_at`.

**`fct_covered_call_premiums`** — all call option activity; grain `run_date`, `account_label`,
`ticker`. Columns: `n_trades`, `n_calls_sold`, `n_called_away` (assignments), `n_expired`,
`net_cash_flow`, `net_pnl`, `premium_collected` (cash from sold opening calls only), `updated_at`.

## Staging fields the report may use

| Field | Meaning |
|---|---|
| `run_date`, `account_label` | trade date / anonymized account label |
| `action` | Fidelity action text (`YOU SOLD...`, `ASSIGNED...`, `EXPIRED...`) |
| `symbol` / `description` | raw contract code / description (e.g. `-PLTR260807C155`) |
| `price`, `quantity`, `commission`, `fees`, `amount_usd` | trade economics, already in USD |
| `contract_ticker`, `contract_expiry_date`, `contract_option_type`, `contract_strike` | parsed contract fields |
| `is_option`, `strategy`, `row_hash` | option flag / classification label / dedupe key |

## Conventions and gotchas

- **Sign:** Fidelity statement sign — credits (premium received) are positive.
- **`net_pnl` vs `net_cash_flow`:** P&L excludes assignment stock legs; cash flow includes them
  (equal in the synthetic samples, where assignment rows carry no option cash).
- **No date table is committed:** use `run_date` directly, or create and mark a `DimDate`
  locally (see the note at the end of `measures.dax`).
- **No surrogate keys:** relate the three marts through small dimension tables (`DimAccount`,
  optional `DimDate`) as described in `dashboard-spec.md`.
- **Synthetic vs real:** `sample_data/` is invented and safe to commit; real exports go to
  `data/exports/powerbi/` and stay local (gitignored).
