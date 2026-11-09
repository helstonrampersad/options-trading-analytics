{{ config(materialized='view') }}

SELECT * FROM {{ ref('stg_fidelity_trades') }}
WHERE account_label = 'LLC_MAIN'
