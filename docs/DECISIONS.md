# Design Decisions — Options Trading Analytics Pipeline

Why each non-obvious choice was made. Written for interview narration: each entry is
"the problem, the call, the tradeoff." If you can explain these eight, you can defend
the project cold.

---

## D1. Anonymize at the filename level, before ingest

**Problem:** Fidelity exports carry real account numbers in both filename and rows.
This repo is public.

**Call:** map `ACCOUNT_<number>` / `FILE_<name>` env vars (untracked `.env`) to four
labels — `LLC_MAIN`, `ROTH_IRA`, `ROLLOVER_IRA`, `INDIVIDUAL_LEGACY` — and scrub every
occurrence before a row is built.

**Tradeoff:** setup friction (new account = new `.env` line, unknown files skip with a
warning). Accepted because a leaked account number is unrecoverable; a skipped file is
a rerun.

**Interview line:** "PII isn't filtered at query time, it never enters the warehouse.
The mapping lives in untracked config, so the code is safe to publish."

---

## D2. Row identity is a content hash, not a surrogate key

**Problem:** Fidelity re-exports the same trade many times. `cash_balance` drifts
between exports, and a trade can appear twice — once `Processing`, once settled.

**Call:** `row_hash = md5(account_label + stable payload + occurrence index)`. Exclude
`cash_balance`. Canonicalize numeric formatting (`'0'` vs `'0.000'`). Prefer the settled
row over its `Processing` twin. Identical same-day fills keep distinct occurrence
indexes so genuinely separate trades survive.

**Tradeoff:** not a real natural key — a corrected trade produces a new hash and a new
row. Accepted because the alternative (dedup on business columns) silently collapses
real fills.

**Interview line:** "The dedupe key is content-addressed. Same trade re-exported with a
drifted balance is a no-op; a genuinely identical second fill gets an occurrence index
so it isn't eaten."

---

## D3. Landing is insert-only, first-wins

**Problem:** Most pipelines upsert into raw. Raw should be replayable and auditable.

**Call:** no `WHEN MATCHED UPDATE` on `raw.fidelity_trades` — insert-only on `row_hash`.
Corrections arrive as new rows. Marts *are* true upserts.

**Tradeoff:** raw grows monotonically; queries must resolve to latest. Accepted because
raw is the audit trail — if you mutate it, you can never explain a number that changed.

**Interview line:** "Raw is immutable. Only the marts merge. If a downstream number
moves, I can always point at the exact raw row that caused it."

---

## D4. Staging as views, marts as incremental merges

**Problem:** staging is cheap to recompute and changes often; marts are expensive and
mostly append daily.

**Call:** staging = `view` (rebuilt every run, always current). Marts = `incremental`
merge keyed on `(run_date, account_label, ticker[, strategy])` with a 3-day lookback.

**Tradeoff:** a backlog CSV older than 3 days won't be picked up until
`--full-refresh`. Accepted (and documented) because the daily case is "yesterday
forward," and a full rebuild runs in seconds locally.

**Interview line:** "3-day window because exports are cumulative and late-arriving by a
day or two. Older backfill is an explicit full-refresh, not an accident."

---

## D5. Same architecture, four implementations across three engines — deliberately

**Problem:** a portfolio project that only proves "I can run one tool" is weak.

**Call:** the same medallion (raw → staging → marts) is implemented four ways across
three engines: dbt on BigQuery (`dbt_project/`), dbt on DuckDB (`dbt_local/`), dbt on
Databricks (`dbt_databricks/`), and a PySpark/Delta notebook (`databricks/options_pipeline.py`).
The local DuckDB path is the one exercised end to end in CI.

**Tradeoff:** maintenance multiplies whenever a model changes. Accepted because it
proves dialect portability, gives a credential-free CI path, and lets you answer
"have you used Spark?" honestly.

**Interview line:** "Four implementations, one design. The reconciliation tests are the
check — if Spark and BigQuery disagree, one of my transformations is wrong."

---

## D6. Tests are reconciliation, not just schema

**Problem:** `not_null` and `unique` prove shape, not correctness. A P&L pipeline can be
green and wrong.

**Call:** 28 dbt tests per project — 25 generic schema tests plus 3 singular P&L
reconciliation SQL tests (`reconcile_pnl.sql`, `reconcile_puts_pnl.sql`,
`reconcile_calls_pnl.sql`) that compare staging cash flow against each mart per
account/day and fail over $0.01. Plus 35 pytest unit tests on
anonymization/parsing/hashing.

**Tradeoff:** reconciliation couples tests to mart semantics — change a mart's
definition and the test must change too. Accepted because it's the only test that
catches a silent double-count.

**Interview line:** "Schema tests tell you the table is well-formed. Reconciliation
tells you the number is right. I want both."

---

## D7. `net_pnl` excludes assignment cash; `net_cash_flow` includes it

**Problem:** the wheel has two legs — option premium and stock assignment. Mixing them
makes every P&L number meaningless.

**Call:** `net_pnl` = realized option premium, Fidelity sign, credits positive,
assignment excluded. `net_cash_flow` = total cash including assignments. Both exposed.

**Tradeoff:** two metrics means two ways to be misread by a stakeholder. Accepted
because collapsing them is how wheel strategies get reported wrong.

**Interview line:** "The stock leg is tracked separately by design. If you ask 'did
this trade make money' you need to know which of the two numbers you mean — that's a
business-definition conversation, not a SQL one."

---

## D8. Visualization layer: Power BI over the marts

**Problem:** the marts answer the hard questions, but a warehouse table is not a
portfolio artifact. The dashboard should show wheel premium, assignment events, and
P&L over time without becoming another place private data can leak.

**Call:** Power BI reads only the published marts — never `raw`. The primary path is
the native BigQuery connector pointed at the marts; the local path exports the DuckDB
marts to CSVs (`powerbi/sample_data/` ships synthetic samples only) and builds the same
report from files. Report definitions, DAX measures, and a theme live under `powerbi/`
with a README explaining the connection options.

**Tradeoff:** a separate BI file format is harder to code-review than SQL, and the free
Power BI Desktop path needs manual refresh. Accepted because Power BI is the tool the
target roles list, the report stays reproducible from marts, and the data boundary is
clear: the dashboard sees anonymized labels and aggregate metrics, exactly like the
warehouse.

**Interview line:** "The BI layer is deliberately thin. It connects to the marts, not
to raw data, so the same privacy boundary that protects the warehouse also protects
the report."

---

## What this proves (interview framing)

Not "I wrote dbt models." It's:
- **Data governance** — PII never lands, definitions are explicit (D7).
- **Idempotency** — rerunning is always safe (D2, D3).
- **Cost/performance** — partition + incremental window (D4).
- **Correctness engineering** — reconciliation over schema-only tests (D6).
- **Portability** — same design across engines (D5).

Every one of those maps to a line in a senior data JD.
