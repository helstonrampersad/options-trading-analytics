{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['run_date', 'account_label', 'ticker']
) }}

WITH calls AS (
  SELECT *
  FROM {{ ref('stg_fidelity_trades') }}
  WHERE contract_option_type = 'C'
)

SELECT
  run_date,
  account_label,
  contract_ticker AS ticker,
  COUNT(*) AS n_trades,
  SUM(CASE WHEN action LIKE '%SOLD%' THEN 1 ELSE 0 END) AS n_calls_sold,
  SUM(CASE WHEN action LIKE '%ASSIGNED%' THEN 1 ELSE 0 END) AS n_called_away,
  SUM(CASE WHEN action LIKE '%EXPIRED%' THEN 1 ELSE 0 END) AS n_expired,
  SUM(amount_usd) AS net_cash_flow,
  SUM(CASE WHEN action LIKE '%ASSIGNED%' THEN 0 ELSE amount_usd END) AS net_pnl,
  SUM(CASE WHEN action LIKE '%SOLD%' THEN amount_usd ELSE 0 END) AS premium_collected,
  CURRENT_TIMESTAMP() AS updated_at
FROM calls
{% if is_incremental() %}
WHERE run_date >= DATE_SUB((SELECT MAX(run_date) FROM {{ this }}), 3)
{% endif %}
GROUP BY run_date, account_label, contract_ticker
