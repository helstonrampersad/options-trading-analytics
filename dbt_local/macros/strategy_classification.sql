{% macro strategy_classification(symbol, description, action, expiry_date) %}
CASE
  WHEN LOWER({{ description }}) LIKE '%interest%' OR LOWER({{ action }}) LIKE '%interest%'
    THEN 'margin_interest'
  WHEN {{ expiry_date }} IS NOT NULL AND EXTRACT(YEAR FROM {{ expiry_date }}) >= 2028
    THEN 'leap'
  WHEN NULLIF(REGEXP_EXTRACT({{ symbol }}, '([A-Z]+)[0-9]{6}[CP][0-9]+', 1), '') = 'PLTR'
    THEN 'PLTR_wheel'
  WHEN UPPER(NULLIF(REGEXP_EXTRACT({{ symbol }}, '([A-Z]+)[0-9]{6}[CP][0-9]+', 1), '')) IN ('SPY', 'QQQ', 'SPXW', 'AVGO', 'NFLX')
    THEN 'day_trade'
  WHEN NULLIF(REGEXP_EXTRACT({{ symbol }}, '[A-Z]+[0-9]{6}([CP])', 1), '') = 'C'
    THEN 'covered_call'
  WHEN NULLIF(REGEXP_EXTRACT({{ symbol }}, '[A-Z]+[0-9]{6}([CP])', 1), '') = 'P'
    THEN 'csp'
  ELSE 'other'
END
{% endmacro %}
