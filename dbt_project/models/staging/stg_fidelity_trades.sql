{{ config(materialized='view') }}

WITH base AS (
  SELECT * FROM {{ source('raw', 'fidelity_trades') }}
),

parsed AS (
  SELECT
    account_label,
    run_date,
    action,
    symbol,
    description,
    type,
    SAFE_CAST(price AS FLOAT64) AS price,
    SAFE_CAST(quantity AS FLOAT64) AS quantity,
    SAFE_CAST(commission AS FLOAT64) AS commission,
    SAFE_CAST(fees AS FLOAT64) AS fees,
    SAFE_CAST(accrued_interest AS FLOAT64) AS accrued_interest,
    SAFE_CAST(amount AS FLOAT64) * IFNULL(SAFE_CAST(exchange_rate AS FLOAT64), 1.0) AS amount_usd,
    SAFE_CAST(cash_balance AS FLOAT64) AS cash_balance,
    settlement_date,
    currency,
    SAFE_CAST(exchange_rate AS FLOAT64) AS exchange_rate,
    source_file,
    row_hash,
    {{ parse_fidelity_contract('symbol', 'description') }} AS contract
  FROM base
)

SELECT
  account_label,
  run_date,
  action,
  symbol,
  description,
  type,
  price,
  quantity,
  commission,
  fees,
  accrued_interest,
  amount_usd,
  cash_balance,
  settlement_date,
  currency,
  exchange_rate,
  source_file,
  row_hash,
  contract.ticker AS contract_ticker,
  contract.expiry_date AS contract_expiry_date,
  contract.option_type AS contract_option_type,
  contract.strike AS contract_strike,
  contract.is_option AS is_option,
  {{ strategy_classification('symbol', 'description', 'action', 'contract.expiry_date') }} AS strategy
FROM parsed
