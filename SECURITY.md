# Security Policy

## Scope

This repository is a personal analytics project: Python ingest, dbt models, Airflow DAGs,
and a PySpark notebook that turn broker CSV exports into trade-analytics marts. It is not a
service, holds no production systems, and accepts no user data. Reports about dependencies,
the CI workflow, or committed files are still welcome.

## Data privacy by design

- **No personal data in the repository.** The repo ships no real broker CSV exports, no
  account numbers, no `.env` file, no real P&L, no cloud project IDs, and no
  workspace URLs or tokens.
- **Synthetic data only.** The only committed datasets are the synthetic fixture
  `tests/fixtures/sample_history.csv` and synthetic Power BI sample CSVs under
  `powerbi/sample_data/`.
- **Account anonymization happens before the warehouse.** Real account numbers appear only
  in a local, gitignored `.env` as `ACCOUNT_<number>=<LABEL>` mappings. The ingest code
  substitutes one of four labels (`LLC_MAIN`, `ROTH_IRA`, `ROLLOVER_IRA`,
  `INDIVIDUAL_LEGACY`) and scrubs account numbers from filenames before a row is built, so
  the warehouse and every committed artifact see labels only.
- **Secrets stay local.** Credentials are supplied through environment variables (for
  example Application Default Credentials for BigQuery and a short-lived PAT for
  Databricks). Nothing is hardcoded; `.env` is gitignored.
- **The owner's real exports are never committed.** Real CSV exports live outside the
  repository (a sibling folder) and are excluded by `.gitignore` along with `.env`,
  DuckDB files, dbt build artifacts, and Spark/Airflow state.

## Pre-push guard

`scripts/privacy_check.py` scans the working tree for Fidelity export filenames,
`ACCOUNT_<number>` mapping keys, and known secret shapes. Run it before pushing:

```bash
python scripts/privacy_check.py
```

The account-number allowlist is deliberately tiny and explicit: the only permitted tokens are
the synthetic values used by the tests (`Z90000000`, `Z90000001`, `900000001`, `900000002`,
`ZZ00000`, `ZZ99999`), the label-prefix words `LLC`/`INDIVIDUAL` that appear inside already
sanitized filenames, and the literal `REDACTED` fallback. Any other `ACCOUNT_...` key is
reported — including in `.env.example` and test fixtures — so a real account number cannot hide
behind a placeholder-looking file. There is no pattern or prefix rule that could accidentally
whitelist a real broker account number.

It is a safety net, not a substitute for careful review. If it flags a file, remove the
sensitive content rather than modifying the check. The optional `--env .env` mode also searches
for the real values configured in the local untracked `.env`; matches are masked and values are
never printed. Note that the guard only reads text files — it does not OCR screenshots or
inspect `.pbix` binaries, so review images manually before committing them.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use GitHub's private
vulnerability reporting on this repository (Security tab → "Report a vulnerability"), or
contact the repository owner directly through their GitHub profile. Include what you found,
where, and how it could be exploited. You can expect an acknowledgement within a few days.

For a leaked credential or account identifier, revoke/rotate it first, then report.
