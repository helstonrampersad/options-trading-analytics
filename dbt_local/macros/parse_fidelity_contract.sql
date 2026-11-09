{% macro parse_fidelity_contract(symbol, description) %}
  struct_pack(
    ticker := NULLIF(REGEXP_EXTRACT({{ symbol }}, '([A-Z]+)[0-9]{6}[CP][0-9]+', 1), ''),
    expiry_date := TRY_STRPTIME(NULLIF(REGEXP_EXTRACT({{ symbol }}, '[A-Z]+([0-9]{6})[CP][0-9]+', 1), ''), '%y%m%d')::DATE,
    option_type := NULLIF(REGEXP_EXTRACT({{ symbol }}, '[A-Z]+[0-9]{6}([CP])', 1), ''),
    strike := TRY_CAST(NULLIF(REGEXP_REPLACE(REGEXP_EXTRACT({{ description }}, '\$([0-9,]*\.?[0-9]+)', 1), ',', ''), '') AS DOUBLE),
    is_option := REGEXP_MATCHES({{ symbol }}, '[A-Z]+[0-9]{6}[CP][0-9]+')
  )
{% endmacro %}
