{% macro parse_fidelity_contract(symbol, description) %}
  named_struct(
    'ticker', NULLIF(REGEXP_EXTRACT({{ symbol }}, '([A-Z]+)[0-9]{6}[CP][0-9]+', 1), ''),
    'expiry_date', TRY_TO_DATE(NULLIF(REGEXP_EXTRACT({{ symbol }}, '[A-Z]+([0-9]{6})[CP][0-9]+', 1), ''), 'yyMMdd'),
    'option_type', NULLIF(REGEXP_EXTRACT({{ symbol }}, '[A-Z]+[0-9]{6}([CP])', 1), ''),
    'strike', TRY_CAST(NULLIF(REGEXP_REPLACE(REGEXP_EXTRACT({{ description }}, '\$([0-9,]*\.?[0-9]+)', 1), ',', ''), '') AS DOUBLE),
    'is_option', {{ symbol }} RLIKE '[A-Z]+[0-9]{6}[CP][0-9]+'
  )
{% endmacro %}
