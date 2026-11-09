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
    TRY_CAST(price AS DOUBLE) AS price,
    TRY_CAST(quantity AS DOUBLE) AS quantity,
    TRY_CAST(commission AS DOUBLE) AS commission,
    TRY_CAST(fees AS DOUBLE) AS fees,
    TRY_CAST(accrued_interest AS DOUBLE) AS accrued_interest,
    TRY_CAST(amount AS DOUBLE) * COALESCE(TRY_CAST(exchange_rate AS DOUBLE), 1.0) AS amount_usd,
    TRY_CAST(cash_balance AS DOUBLE) AS cash_balance,
    settlement_date,
    currency,
    TRY_CAST(exchange_rate AS DOUBLE) AS exchange_rate,
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
