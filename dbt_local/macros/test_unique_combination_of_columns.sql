{% test unique_combination_of_columns(model, combination_of_columns) %}
SELECT *
FROM (
  SELECT {{ combination_of_columns | join(', ') }}
  FROM {{ model }}
  GROUP BY {{ combination_of_columns | join(', ') }}
  HAVING COUNT(*) > 1
) AS validation_errors
{% endtest %}
