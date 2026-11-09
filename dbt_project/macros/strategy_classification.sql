{% macro strategy_classification(symbol, description, action, expiry_date) %}
CASE
  WHEN LOWER({{ description }}) LIKE '%interest%' OR LOWER({{ action }}) LIKE '%interest%'
    THEN 'margin_interest'
  WHEN {{ expiry_date }} IS NOT NULL AND EXTRACT(YEAR FROM {{ expiry_date }}) >= 2028
    THEN 'leap'
  WHEN REGEXP_EXTRACT({{ symbol }}, r'([A-Z]+)\d{6}[CP]\d+') = 'PLTR'
    THEN 'PLTR_wheel'
  WHEN UPPER(REGEXP_EXTRACT({{ symbol }}, r'([A-Z]+)\d{6}[CP]\d+')) IN ('SPY', 'QQQ', 'SPXW', 'AVGO', 'NFLX')
    THEN 'day_trade'
  WHEN REGEXP_EXTRACT({{ symbol }}, r'[A-Z]+\d{6}([CP])') = 'C'
    THEN 'covered_call'
  WHEN REGEXP_EXTRACT({{ symbol }}, r'[A-Z]+\d{6}([CP])') = 'P'
    THEN 'csp'
  ELSE 'other'
END
{% endmacro %}
