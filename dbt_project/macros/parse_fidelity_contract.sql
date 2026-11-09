{% macro parse_fidelity_contract(symbol, description) %}
STRUCT(
  REGEXP_EXTRACT({{ symbol }}, r'([A-Z]+)\d{6}[CP]\d+') AS ticker,
  SAFE.PARSE_DATE('%y%m%d', REGEXP_EXTRACT({{ symbol }}, r'[A-Z]+(\d{6})[CP]\d+')) AS expiry_date,
  REGEXP_EXTRACT({{ symbol }}, r'[A-Z]+\d{6}([CP])') AS option_type,
  SAFE_CAST(REGEXP_REPLACE(REGEXP_EXTRACT({{ description }}, r'\$([\d,]*\.?\d+)'), r',', '') AS FLOAT64) AS strike,
  REGEXP_CONTAINS({{ symbol }}, r'[A-Z]+\d{6}[CP]\d+') AS is_option
)
{% endmacro %}
