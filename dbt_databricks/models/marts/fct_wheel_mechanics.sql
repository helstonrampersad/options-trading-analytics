{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['run_date', 'account_label', 'ticker', 'strategy']
) }}

WITH option_trades AS (
  SELECT *
  FROM {{ ref('stg_fidelity_trades') }}
  WHERE is_option
)

SELECT
  run_date,
  account_label,
  contract_ticker AS ticker,
  strategy,
  COUNT(*) AS n_trades,
  SUM(CASE WHEN action LIKE '%SOLD%' THEN 1 ELSE 0 END) AS n_sells,
  SUM(CASE WHEN action LIKE '%ASSIGNED%' THEN 1 ELSE 0 END) AS n_assignments,
  SUM(amount_usd) AS net_cash_flow,
  SUM(CASE WHEN action LIKE '%ASSIGNED%' THEN 0 ELSE amount_usd END) AS net_pnl,
  GREATEST(ROUND(AVG(DATEDIFF(contract_expiry_date, run_date)), 1), 0) AS avg_dte,
  CURRENT_TIMESTAMP() AS updated_at
FROM option_trades
{% if is_incremental() %}
WHERE run_date >= DATE_SUB((SELECT MAX(run_date) FROM {{ this }}), 3)
{% endif %}
GROUP BY run_date, account_label, contract_ticker, strategy
