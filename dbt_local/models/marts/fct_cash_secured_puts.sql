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
  COUNT_IF(action LIKE '%SOLD%') AS n_puts_sold,
  COUNT_IF(action LIKE '%ASSIGNED%') AS n_assignments,
  COUNT_IF(action LIKE '%EXPIRED%') AS n_expired,
  SUM(amount_usd) AS net_cash_flow,
  SUM(CASE WHEN action LIKE '%ASSIGNED%' THEN 0 ELSE amount_usd END) AS net_pnl,
  MAX(contract_strike) AS last_strike,
  CURRENT_TIMESTAMP AS updated_at
FROM puts
{% if is_incremental() %}
WHERE run_date >= (SELECT MAX(run_date) FROM {{ this }}) - INTERVAL 3 DAY
{% endif %}
GROUP BY run_date, account_label, contract_ticker
