{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['run_date', 'account_label', 'ticker']
) }}

WITH puts AS (
  SELECT *
  FROM {{ ref('stg_fidelity_trades') }}
  WHERE contract_option_type = 'P'
)

SELECT
  run_date,
  account_label,
  contract_ticker AS ticker,
  COUNT(*) AS n_trades,
  SUM(CASE WHEN action LIKE '%SOLD%' THEN 1 ELSE 0 END) AS n_puts_sold,
  SUM(CASE WHEN action LIKE '%ASSIGNED%' THEN 1 ELSE 0 END) AS n_assignments,
  SUM(CASE WHEN action LIKE '%EXPIRED%' THEN 1 ELSE 0 END) AS n_expired,
  SUM(amount_usd) AS net_cash_flow,
  SUM(CASE WHEN action LIKE '%ASSIGNED%' THEN 0 ELSE amount_usd END) AS net_pnl,
  MAX(contract_strike) AS last_strike,
  CURRENT_TIMESTAMP() AS updated_at
FROM puts
{% if is_incremental() %}
WHERE run_date >= DATE_SUB((SELECT MAX(run_date) FROM {{ this }}), 3)
{% endif %}
GROUP BY run_date, account_label, contract_ticker
