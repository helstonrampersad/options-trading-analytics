-- Fails if fct_wheel_mechanics P&L per (account, day) disagrees with staging.
-- NOTE: fct_cash_secured_puts and fct_covered_call_premiums are subsets of
-- fct_wheel_mechanics (puts/calls), so reconciliation compares against the
-- wheel model only to avoid double-counting.
WITH stg AS (
  SELECT account_label, run_date, SUM(amount_usd) AS stg_amount
  FROM {{ ref('stg_fidelity_trades') }}
  WHERE is_option
  GROUP BY account_label, run_date
),
mart AS (
  SELECT account_label, run_date, SUM(net_cash_flow) AS mart_amount
  FROM {{ ref('fct_wheel_mechanics') }}
  GROUP BY account_label, run_date
)
SELECT s.account_label, s.run_date, s.stg_amount, m.mart_amount
FROM stg s
FULL OUTER JOIN mart m USING (account_label, run_date)
WHERE ABS(COALESCE(s.stg_amount, 0) - COALESCE(m.mart_amount, 0)) > 0.01
