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
  COUNT_IF(action LIKE '%SOLD%') AS n_sells,
  COUNT_IF(action LIKE '%ASSIGNED%') AS n_assignments,
  SUM(amount_usd) AS net_cash_flow,
  SUM(CASE WHEN action LIKE '%ASSIGNED%' THEN 0 ELSE amount_usd END) AS net_pnl,
  GREATEST(ROUND(AVG(DATE_DIFF('day', run_date, contract_expiry_date)), 1), 0) AS avg_dte,
  CURRENT_TIMESTAMP AS updated_at
FROM option_trades
{% if is_incremental() %}
WHERE run_date >= (SELECT MAX(run_date) FROM {{ this }}) - INTERVAL 3 DAY
{% endif %}
GROUP BY run_date, account_label, contract_ticker, strategy
