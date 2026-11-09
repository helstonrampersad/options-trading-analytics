{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['run_date', 'account_label', 'ticker'],
    partition_by={'field': 'run_date', 'data_type': 'date'},
    require_partition_filter=false
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
  COUNTIF(action LIKE '%SOLD%') AS n_calls_sold,
  COUNTIF(action LIKE '%ASSIGNED%') AS n_called_away,
  COUNTIF(action LIKE '%EXPIRED%') AS n_expired,
  SUM(amount_usd) AS net_cash_flow,
  SUM(CASE WHEN action LIKE '%ASSIGNED%' THEN 0 ELSE amount_usd END) AS net_pnl,
  SUM(IF(action LIKE '%SOLD%', amount_usd, 0)) AS premium_collected,
  CURRENT_TIMESTAMP() AS updated_at
FROM calls
{% if is_incremental() %}
WHERE run_date >= DATE_SUB((SELECT MAX(run_date) FROM {{ this }}), INTERVAL 3 DAY)
{% endif %}
GROUP BY run_date, account_label, contract_ticker
