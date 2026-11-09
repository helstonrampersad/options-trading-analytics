# Databricks notebook source
# MAGIC %md
# MAGIC # Options Trading Pipeline — Medallion (bronze / silver / gold) on Delta Lake
# MAGIC
# MAGIC A self-contained port of the author's BigQuery pipeline (dbt + BigQuery → Databricks + PySpark + Delta).
# MAGIC It reads Fidelity trade-history CSVs and builds three layers:
# MAGIC
# MAGIC | Layer | Object | What it does |
# MAGIC |---|---|---|
# MAGIC | **Bronze** | Delta table `fidelity_trades_bronze` | Raw normalized trades, deduplicated by content hash (`row_hash`), **insert-only MERGE** (first write wins) — the raw record of everything |
# MAGIC | **Silver** | Delta table `stg_fidelity_trades` (rebuilt every run) | Parsed option contracts (ticker / expiry / type / strike) + trade *strategy* classification (wheel, cash-secured puts, covered calls, day trades, LEAPs, margin interest) |
# MAGIC | **Gold** | `fct_wheel_mechanics`, `fct_cash_secured_puts`, `fct_covered_call_premiums` — Delta tables **partitioned by `run_date`**, upserted with **MERGE** | Daily P&L and mechanics per ticker and account — ready for dashboards / reports |
# MAGIC
# MAGIC Tables are Delta tables at a storage location (`DELTA_ROOT`); on Community Edition that is a DBFS path.
# MAGIC Query them with `FROM delta.`<path>`` in any SQL cell.
# MAGIC
# MAGIC **Why this architecture?** It mirrors how production pipelines run on Databricks:
# MAGIC Delta transactions (`MERGE`) keep re-runs idempotent (no duplicates), partitioning keeps queries cheap,
# MAGIC and layering separates *raw facts* from *cleaned facts* from *business aggregates*.
# MAGIC
# MAGIC **Run order:** cells run top to bottom. Everything is idempotent — run it twice and row counts stay the same.
# MAGIC
# MAGIC <br>
# MAGIC **SETUP (one time):** after importing this notebook and uploading your CSVs, open the **CONFIG** cell and
# MAGIC add your own account map with `%env` lines at the top of the cell. Replace the placeholders below with your
# MAGIC real account numbers (from your broker exports / the repo `.env`):
# MAGIC
# MAGIC ```python
# MAGIC %env ACCOUNT_<account_number_1>=LLC_MAIN
# MAGIC %env ACCOUNT_<account_number_2>=ROTH_IRA
# MAGIC %env ACCOUNT_<account_number_3>=ROLLOVER_IRA
# MAGIC %env ACCOUNT_<account_number_4>=INDIVIDUAL_LEGACY
# MAGIC %env FILE_<stem_of_ytd_file>=LLC_MAIN
# MAGIC ```
# MAGIC
# MAGIC *(Real account numbers live only in this notebook's env — never in the shared code below.
# MAGIC `ACCOUNT_<number>` maps raw account numbers to generic labels, the same anonymization as the BigQuery pipeline.)*

# Databricks notebook source
# MAGIC %md
# MAGIC ## 0) Environment and imports

# Databricks notebook source
import os
import re
import csv
import glob
import hashlib
import datetime
import warnings

warnings.filterwarnings("ignore")

from pyspark.sql import SparkSession

# Databricks notebooks already have a live SparkSession; standalone runs create one.
def get_spark():
    active = SparkSession.getActiveSession()
    if active is not None:
        return active
    builder = (
        SparkSession.builder.master("local[1]")
        .appName("options-pipeline")
        .config("spark.jars.packages", "io.delta:delta-spark_2.12:3.2.1")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "4")
    )
    return builder.getOrCreate()

spark = get_spark()
print("Spark", spark.version)

# Databricks notebook source
# MAGIC %md
# MAGIC ## 1) CONFIG — point at your data and accounts
# MAGIC
# MAGIC * `ACCOUNT_<number>` / `FILE_<stem>` — anonymized label map (see SETUP cell above).
# MAGIC * `DATA_DIR` — where the CSVs live locally (default `./data/raw`).
# MAGIC * `DBFS_SOURCE` — on Databricks the uploaded CSVs are copied from DBFS to the driver node first.
# MAGIC * `DELTA_ROOT` — where the bronze/silver/gold Delta tables are stored.

# Databricks notebook source
IS_DATABRICKS = "dbutils" in dir()

# 1a. Account map -------------------------------------------------------------
ACCOUNT_MAP = {k[len("ACCOUNT_"):]: v for k, v in os.environ.items() if k.startswith("ACCOUNT_")}
FILE_MAP = {k[len("FILE_"):]: v for k, v in os.environ.items() if k.startswith("FILE_")}
if not ACCOUNT_MAP:
    print("⚠️  No ACCOUNT_* env vars found. Add %env lines at the top of this cell, e.g.:")
    print("    %env ACCOUNT_<account_number>=LLC_MAIN")
    print("    (see the SETUP notes in the first cell)")

# 1b. Source data + Delta storage --------------------------------------------
LOCAL_DIR = os.environ.get("DATA_DIR", "data/raw")
DBFS_SOURCE = os.environ.get("DBFS_SOURCE", "dbfs:/FileStore/tables")
WORK_DIR = "/tmp/fidelity_trades"
DELTA_ROOT = os.environ.get("DELTA_ROOT", "dbfs:/FileStore/fidelity_delta" if IS_DATABRICKS else "/tmp/fidelity_delta")

BRONZE_PATH = DELTA_ROOT + "/fidelity_trades_bronze"
SILVER_PATH = DELTA_ROOT + "/stg_fidelity_trades"
GOLD_PATHS = {
    "wheel": DELTA_ROOT + "/fct_wheel_mechanics",
    "puts": DELTA_ROOT + "/fct_cash_secured_puts",
    "calls": DELTA_ROOT + "/fct_covered_call_premiums",
}

print("account mappings loaded:", len(ACCOUNT_MAP))
print("file_map keys:", sorted(FILE_MAP))
print("on Databricks:", IS_DATABRICKS, "| source:", DBFS_SOURCE if IS_DATABRICKS else LOCAL_DIR)
print("DELTA_ROOT:", DELTA_ROOT)

# Databricks notebook source
# MAGIC %md
# MAGIC ## 2) Bronze — load & normalize the raw Fidelity trade CSVs
# MAGIC
# MAGIC Parsing rules mirror the Python side of the original pipeline:
# MAGIC - Fidelity exports come in two header layouts (13-column “Price ($)” and 17-column legacy); a header row containing
# MAGIC   `Run Date` is sniffed wherever it sits (files have a preamble), and dates like `M/D/YYYY` / `M-D-YYYY`
# MAGIC   are normalized to ISO *before* hashing, so duplicates across export formats collapse.
# MAGIC - Each normalized trade gets a content hash `row_hash = md5(account_label | field | …)`.
# MAGIC - The Bronze table is **append-only**: MERGE inserts rows whose hash is new and never updates old ones —
# MAGIC   an identical re-run inserts nothing.

# Databricks notebook source
NORMALIZED_FIELDS = [
    "run_date", "action", "symbol", "description", "type", "price", "quantity",
    "commission", "fees", "accrued_interest", "amount", "cash_balance",
    "settlement_date", "currency", "exchange_rate",
]

CURRENT_MAP = {
    "Run Date": "run_date", "Action": "action", "Symbol": "symbol",
    "Description": "description", "Type": "type", "Price ($)": "price",
    "Quantity": "quantity", "Commission ($)": "commission", "Fees ($)": "fees",
    "Accrued Interest ($)": "accrued_interest", "Amount ($)": "amount",
    "Cash Balance ($)": "cash_balance", "Settlement Date": "settlement_date",
}

LEGACY_MAP = {
    "Run Date": "run_date", "Action": "action", "Symbol": "symbol",
    "Description": "description", "Type": "type", "Price": "price",
    "Quantity": "quantity", "Exchange Rate": "exchange_rate",
    "Commission": "commission", "Fees": "fees",
    "Accrued Interest": "accrued_interest", "Amount": "amount",
    "Cash Balance": "cash_balance", "Settlement Date": "settlement_date",
    "Exchange Currency": "exchange_currency", "Currency": "currency",
}

_MDY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_MDY_DASH_RE = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")

ACCOUNT_RE = re.compile(r"History_for_Account_([A-Z0-9]+)")


def _clean(value):
    if value is None:
        return None
    value = value.strip()
    return value if value != "" else None


def _normalize_date(value):
    if not value:
        return None
    match = _MDY_RE.match(value) or _MDY_DASH_RE.match(value)
    if not match:
        return None
    return f"{match.group(3)}-{int(match.group(1)):02d}-{int(match.group(2)):02d}"


def find_header(rows):
    for i, row in enumerate(rows):
        if row and any("Run Date" in cell for cell in row):
            return i
    raise ValueError("no header row containing 'Run Date' found")


def _normalize_row(raw_row, header, column_map):
    row = {}
    for idx, h in enumerate(header):
        key = column_map.get(h.strip())
        if key:
            value = raw_row[idx] if idx < len(raw_row) else None
            if key == "price":
                value = value.strip() if value is not None else None
            elif key in ("quantity", "commission", "fees",
                         "accrued_interest", "amount", "cash_balance", "exchange_rate"):
                value = _clean(value)
            elif key in ("run_date", "settlement_date"):
                value = _normalize_date(_clean(value))
            elif key in ("action", "symbol", "description", "type", "currency"):
                value = value.strip() if isinstance(value, str) else value
            row[key] = value
    for f in NORMALIZED_FIELDS:
        row.setdefault(f, None)
    if row.get("currency") is None:
        row["currency"] = "USD"
    return row


def parse_file(path):
    """Parse one Fidelity CSV export into normalized row dicts (junk/footer rows dropped)."""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    header_idx = find_header(rows)
    header = rows[header_idx]
    has_exchange_qty = any("Exchange Quantity" in h for h in header)
    column_map = LEGACY_MAP if has_exchange_qty else CURRENT_MAP
    out = []
    for row in rows[header_idx + 1:]:
        if not row or all(not c.strip() for c in row):
            continue
        record = _normalize_row(row, header, column_map)
        if record["run_date"] is None:  # footer / unparseable rows carry no date
            continue
        out.append(record)
    return out


HASH_FIELDS = [f for f in NORMALIZED_FIELDS if f != "cash_balance"]


def _canonical(value):
    """Canonical string form: numbers are normalized so '0' and '0.000' compare equal."""
    if value is None:
        return ""
    text = str(value).strip()
    if text == "":
        return ""
    try:
        return str(float(text.replace(",", "")))
    except ValueError:
        return text


def stable_payload(row):
    """Trade identity ignoring cash_balance: exports re-list the same trade with a drifted balance."""
    return row["account_label"] + "|" + "|".join(_canonical(row.get(f)) for f in HASH_FIELDS)


def row_hash(row, occurrence=1):
    """Stable payload + occurrence index within one export file.

    Cumulative exports repeat the same trade in every file (same occurrence -> same hash -> deduped).
    Genuinely separate identical trades appear as occurrences 1..n within a file and are all kept.
    Use hash_file_rows() to assign hashes for a whole file.
    """
    payload = f"{stable_payload(row)}|#{occurrence}"
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def _has_settled_balance(row):
    balance = row.get("cash_balance")
    if balance is None:
        return False
    text = str(balance).strip()
    return bool(text) and text.lower() != "processing"


def hash_file_rows(rows):
    """Assign occurrence-aware row hashes to one file's rows.

    Rows whose balance is still 'Processing' are placeholder twins of settled rows: when a
    file contains both, only the settled version is kept. Exact duplicates (same stable
    payload and same cash_balance) are collapsed, then rows are sorted canonically so
    occurrence indices pair up across exports even when fills are listed in a different order.
    """
    by_payload = {}
    for row in rows:
        by_payload.setdefault(stable_payload(row), []).append(row)
    unique = []
    for payload, group in by_payload.items():
        settled = [r for r in group if _has_settled_balance(r)]
        keep = settled if settled else group
        seen_exact = set()
        for row in keep:
            exact = payload + "|" + _canonical(row.get("cash_balance"))
            if exact in seen_exact:
                continue
            seen_exact.add(exact)
            unique.append(row)
    unique.sort(key=lambda r: (stable_payload(r), _canonical(r.get("cash_balance"))))
    occurrences = {}
    for row in unique:
        key = stable_payload(row)
        occurrences[key] = occurrences.get(key, 0) + 1
        row["row_hash"] = row_hash(row, occurrences[key])
    return unique


def label_for_filename(filename, account_map, file_map):
    match = ACCOUNT_RE.search(filename)
    if match:
        account = match.group(1)
        if account in account_map:
            return account_map[account]
        raise ValueError(f"unknown account {account!r} in filename {filename!r}")
    stem = filename.rsplit(".", 1)[0]
    if stem in file_map:
        return file_map[stem]
    raise ValueError(f"unknown account in filename {filename!r}")


def sanitize_filename(filename, account_map):
    def repl(match):
        account = match.group(1)
        return f"History_for_Account_{account_map.get(account, 'REDACTED')}"

    return ACCOUNT_RE.sub(repl, filename)


def _to_float(value):
    """Same lenient numeric coercion as the BigQuery loader: '' and junk become None."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_date(iso):
    if iso is None:
        return None
    return datetime.date.fromisoformat(iso)


def collect_source_files():
    """Return local paths of every Fidelity CSV to process (DBFS is copied down on Databricks)."""
    if IS_DATABRICKS:
        os.makedirs(WORK_DIR, exist_ok=True)
        try:
            dbutils.fs.cp(DBFS_SOURCE, "file:" + WORK_DIR, recurse=True)
        except Exception as e:  # noqa: BLE001
            print("⚠️  DBFS copy failed — check DBFS_SOURCE:", e)
        return sorted(glob.glob(os.path.join(WORK_DIR, "*.csv")))
    return sorted(glob.glob(os.path.join(LOCAL_DIR, "*.csv")))

# Databricks notebook source
def build_bronze_rows():
    """Parse every source file into typed, labeled, deduplicated records."""
    seen, out, skipped, parsed_files = set(), [], [], 0
    for path in collect_source_files():
        filename = os.path.basename(path)
        try:
            account_label = label_for_filename(filename, ACCOUNT_MAP, FILE_MAP)
        except ValueError as exc:
            skipped.append(str(exc))
            continue
        parsed_files += 1
        rows = []
        for record in parse_file(path):
            record["account_label"] = account_label
            record["source_file"] = sanitize_filename(filename, ACCOUNT_MAP)
            rows.append(record)
        for record in hash_file_rows(rows):
            h = record["row_hash"]
            if h in seen:            # cumulative exports repeat the same trades
                continue
            seen.add(h)
            out.append((
                account_label,
                _to_date(record["run_date"]),
                record["action"], record["symbol"], record["description"],
                record["type"],
                _to_float(record["price"]), _to_float(record["quantity"]),
                _to_float(record["commission"]), _to_float(record["fees"]),
                _to_float(record["accrued_interest"]), _to_float(record["amount"]),
                _to_float(record["cash_balance"]),
                _to_date(record["settlement_date"]),
                record["currency"], _to_float(record["exchange_rate"]),
                record["source_file"], h,
                datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
            ))
    for msg in skipped:
        print("  skip:", msg)
    print(f"parsed {parsed_files} files | {len(out)} unique trade rows after dedupe")
    return out


BRONZE_SCHEMA = (
    "account_label STRING, run_date DATE, action STRING, symbol STRING, description STRING, type STRING, "
    "price DOUBLE, quantity DOUBLE, commission DOUBLE, fees DOUBLE, accrued_interest DOUBLE, amount DOUBLE, "
    "cash_balance DOUBLE, settlement_date DATE, currency STRING, exchange_rate DOUBLE, "
    "source_file STRING, row_hash STRING, ingested_at TIMESTAMP"
)


def delta_table_exists(path):
    """True if a Delta table already exists at path; only missing-table errors are swallowed."""
    try:
        spark.read.load(path, format="delta").limit(0)
        return True
    except Exception as exc:  # noqa: BLE001 - re-raised below unless the table is missing
        text = str(exc).lower()
        if "does not exist" in text or "not a delta table" in text or "path_not_found" in text:
            return False
        raise


def ingest_bronze(rows):
    """Insert-only MERGE into Delta: a row_hash already present is left untouched (first write wins)."""
    if not rows:
        print("nothing to ingest")
        return
    df = spark.createDataFrame(rows, schema=BRONZE_SCHEMA).dropDuplicates(["row_hash"])
    df.createOrReplaceTempView("new_bronze")
    if delta_table_exists(BRONZE_PATH):
        spark.sql("""
            MERGE INTO delta.`%s` AS tgt
            USING new_bronze AS src
            ON tgt.row_hash = src.row_hash
            WHEN NOT MATCHED THEN INSERT *
        """ % BRONZE_PATH)
    else:
        df.write.format("delta").mode("append").save(BRONZE_PATH)  # first run: create
    return spark.read.load(BRONZE_PATH, format="delta").count()


rows = build_bronze_rows()
total = ingest_bronze(rows)
print(f"Bronze table now has {total} rows")
spark.sql(
    "SELECT account_label, COUNT(*) AS n FROM delta.`%s` GROUP BY account_label ORDER BY account_label" % BRONZE_PATH
).show()

# Databricks notebook source
# MAGIC %md
# MAGIC ## 3) Silver — parse contracts and classify strategies
# MAGIC
# MAGIC The silver layer is rebuilt from bronze on every run (like the dbt staging view it mirrors). It derives:
# MAGIC - **contract** parsed from the Fidelity symbol (` -PLTR260807C155` → ticker `PLTR`, expiry `2026-08-07`, call) and strike from the description (`$155`)
# MAGIC - **strategy** from the ticker / expiry / action rules of the original business logic.
# MAGIC
# MAGIC Option strategies on this account: `margin_interest`, `leap` (expiry ≥ 2028), `PLTR_wheel`,
# MAGIC `day_trade` (SPY/QQQ/SPXW/AVGO/NFLX), `covered_call`, `csp` (cash-secured puts), `other`.

# Databricks notebook source
def rebuild_silver():
    spark.sql("""
        CREATE OR REPLACE TABLE delta.`%s` USING DELTA AS
        SELECT
            account_label, run_date, action, symbol, description, type,
            price, quantity, commission, fees, accrued_interest,
            amount * COALESCE(exchange_rate, 1.0) AS amount_usd,
            cash_balance, settlement_date, currency, exchange_rate,
            source_file, row_hash,
            REGEXP_EXTRACT(symbol, '([A-Z]+)[0-9]{6}[CP][0-9]+')                         AS contract_ticker,
            TO_DATE(REGEXP_EXTRACT(symbol, '[A-Z]+([0-9]{6})[CP][0-9]+'), 'yyMMdd')     AS contract_expiry_date,
            REGEXP_EXTRACT(symbol, '[A-Z]+[0-9]{6}([CP])')                              AS contract_option_type,
            CAST(REGEXP_REPLACE(REGEXP_EXTRACT(description, '\\$([0-9,]*\\.?[0-9]+)'), ',', '') AS DOUBLE) AS contract_strike,
            symbol RLIKE '[A-Z]+[0-9]{6}[CP][0-9]+'                                     AS is_option,
            CASE
                WHEN LOWER(description) LIKE '%%interest%%' OR LOWER(action) LIKE '%%interest%%' THEN 'margin_interest'
                WHEN TO_DATE(REGEXP_EXTRACT(symbol, '[A-Z]+([0-9]{6})[CP][0-9]+'), 'yyMMdd') IS NOT NULL
                     AND YEAR(TO_DATE(REGEXP_EXTRACT(symbol, '[A-Z]+([0-9]{6})[CP][0-9]+'), 'yyMMdd')) >= 2028 THEN 'leap'
                WHEN REGEXP_EXTRACT(symbol, '([A-Z]+)[0-9]{6}[CP][0-9]+') = 'PLTR' THEN 'PLTR_wheel'
                WHEN UPPER(REGEXP_EXTRACT(symbol, '([A-Z]+)[0-9]{6}[CP][0-9]+')) IN ('SPY', 'QQQ', 'SPXW', 'AVGO', 'NFLX') THEN 'day_trade'
                WHEN REGEXP_EXTRACT(symbol, '[A-Z]+[0-9]{6}([CP])') = 'C' THEN 'covered_call'
                WHEN REGEXP_EXTRACT(symbol, '[A-Z]+[0-9]{6}([CP])') = 'P' THEN 'csp'
                ELSE 'other'
            END AS strategy
        FROM delta.`%s`
    """ % (SILVER_PATH, BRONZE_PATH))


rebuild_silver()
print("Silver layer rebuilt")
spark.sql(
    "SELECT strategy, COUNT(*) AS n FROM delta.`%s` GROUP BY strategy ORDER BY n DESC" % SILVER_PATH
).show()

# Databricks notebook source
# MAGIC %md
# MAGIC ## 4) Gold — partitioned marts, upserted with MERGE
# MAGIC
# MAGIC Three **Delta tables partitioned by `run_date`** — the same daily marts the BigQuery side produces, so the
# MAGIC numbers you see here match that pipeline exactly. Each run recomputes the aggregates from silver and
# MAGIC **MERGE-upserts** them by business key, so re-runs never duplicate a day.
# MAGIC
# MAGIC Sign convention: Fidelity records sold-opening premiums as positive and bought-closing
# MAGIC amounts as negative. `net_cash_flow = SUM(amount_usd)` is total cash (assignment stock leg
# MAGIC included); `net_pnl` is premium P&L only — assignments excluded, same sign as the premium.

# Databricks notebook source
GOLD_DEFS = [
    {
        "path": GOLD_PATHS["wheel"],
        "columns": (
            "run_date DATE, account_label STRING, ticker STRING, strategy STRING, "
            "n_trades BIGINT, n_sells BIGINT, n_assignments BIGINT, "
            "net_cash_flow DOUBLE, net_pnl DOUBLE, avg_dte DOUBLE, updated_at TIMESTAMP"
        ),
        "on": "tgt.run_date = src.run_date AND tgt.account_label = src.account_label "
              "AND tgt.ticker = src.ticker AND tgt.strategy = src.strategy",
        "sql": """
            SELECT
                run_date, account_label, contract_ticker AS ticker, strategy,
                COUNT(*)                                                AS n_trades,
                COUNT_IF(action LIKE '%%SOLD%%')                          AS n_sells,
                COUNT_IF(action LIKE '%%ASSIGNED%%')                      AS n_assignments,
                SUM(amount_usd)                                         AS net_cash_flow,
                SUM(CASE WHEN action LIKE '%%ASSIGNED%%' THEN 0 ELSE amount_usd END) AS net_pnl,
                GREATEST(ROUND(AVG(DATEDIFF(contract_expiry_date, run_date)), 1), 0) AS avg_dte,
                CURRENT_TIMESTAMP()                                     AS updated_at
            FROM delta.`%s`
            WHERE is_option
            GROUP BY run_date, account_label, contract_ticker, strategy
        """,
    },
    {
        "path": GOLD_PATHS["puts"],
        "columns": (
            "run_date DATE, account_label STRING, ticker STRING, "
            "n_trades BIGINT, n_puts_sold BIGINT, n_assignments BIGINT, n_expired BIGINT, "
            "net_cash_flow DOUBLE, net_pnl DOUBLE, last_strike DOUBLE, updated_at TIMESTAMP"
        ),
        "on": "tgt.run_date = src.run_date AND tgt.account_label = src.account_label "
              "AND tgt.ticker = src.ticker",
        "sql": """
            SELECT
                run_date, account_label, contract_ticker AS ticker,
                COUNT(*)                                AS n_trades,
                COUNT_IF(action LIKE '%%SOLD%%')          AS n_puts_sold,
                COUNT_IF(action LIKE '%%ASSIGNED%%')      AS n_assignments,
                COUNT_IF(action LIKE '%%EXPIRED%%')       AS n_expired,
                SUM(amount_usd)                         AS net_cash_flow,
                SUM(CASE WHEN action LIKE '%%ASSIGNED%%' THEN 0 ELSE amount_usd END) AS net_pnl,
                MAX(contract_strike)                    AS last_strike,
                CURRENT_TIMESTAMP()                     AS updated_at
            FROM delta.`%s`
            WHERE contract_option_type = 'P'
            GROUP BY run_date, account_label, contract_ticker
        """,
    },
    {
        "path": GOLD_PATHS["calls"],
        "columns": (
            "run_date DATE, account_label STRING, ticker STRING, "
            "n_trades BIGINT, n_calls_sold BIGINT, n_called_away BIGINT, n_expired BIGINT, "
            "net_cash_flow DOUBLE, net_pnl DOUBLE, premium_collected DOUBLE, updated_at TIMESTAMP"
        ),
        "on": "tgt.run_date = src.run_date AND tgt.account_label = src.account_label "
              "AND tgt.ticker = src.ticker",
        "sql": """
            SELECT
                run_date, account_label, contract_ticker AS ticker,
                COUNT(*)                                       AS n_trades,
                COUNT_IF(action LIKE '%%SOLD%%')                 AS n_calls_sold,
                COUNT_IF(action LIKE '%%ASSIGNED%%')             AS n_called_away,
                COUNT_IF(action LIKE '%%EXPIRED%%')              AS n_expired,
                SUM(amount_usd)                                AS net_cash_flow,
                SUM(CASE WHEN action LIKE '%%ASSIGNED%%' THEN 0 ELSE amount_usd END) AS net_pnl,
                SUM(IF(action LIKE '%%SOLD%%', amount_usd, 0.0)) AS premium_collected,
                CURRENT_TIMESTAMP()                            AS updated_at
            FROM delta.`%s`
            WHERE contract_option_type = 'C'
            GROUP BY run_date, account_label, contract_ticker
        """,
    },
]

for g in GOLD_DEFS:
    spark.sql(g["sql"] % SILVER_PATH).createOrReplaceTempView("gold_agg")
    if delta_table_exists(g["path"]):
        spark.sql("""
            MERGE INTO delta.`%s` AS tgt
            USING gold_agg AS src
            ON %s
            WHEN MATCHED THEN UPDATE SET *
            WHEN NOT MATCHED THEN INSERT *
        """ % (g["path"], g["on"]))
    else:
        spark.table("gold_agg").write.format("delta").mode("append").partitionBy("run_date").save(g["path"])
    n = spark.read.load(g["path"], format="delta").count()
    keys = ["run_date", "account_label", "ticker"] + (["strategy"] if g["path"].endswith("wheel_mechanics") else [])
    d = spark.read.load(g["path"], format="delta").select(*keys).distinct().count()
    print(f"{g['path'].split('/')[-1]}: {n} rows | distinct business keys: {d} | no dupes: {n == d}")

# Databricks notebook source
# MAGIC %md
# MAGIC ## 5) Verify & explore
# MAGIC
# MAGIC The mart counts match the other pipelines' outputs (BigQuery, DuckDB) to the row and to the cent.
# MAGIC **Re-run the whole notebook:** bronze's insert-only MERGE adds nothing and gold MERGE-upserts the same keys —
# MAGIC counts stay exactly the same (that's the idempotency guarantee).
# MAGIC
# MAGIC **Try these in new cells** (partition pruning makes `WHERE run_date` cheap):
# MAGIC
# MAGIC ```sql
# MAGIC -- 1. Delta time travel: what did the wheel table look like one version ago?
# MAGIC SELECT * FROM delta.`/FileStore/fidelity_delta/fct_wheel_mechanics` VERSION AS OF 1
# MAGIC
# MAGIC -- 2. Your best wheel days
# MAGIC SELECT run_date, account_label, ticker, n_sells, n_assignments, net_pnl
# MAGIC FROM delta.`/FileStore/fidelity_delta/fct_wheel_mechanics`
# MAGIC WHERE run_date >= '2026-01-01'
# MAGIC ORDER BY net_pnl DESC LIMIT 10
# MAGIC
# MAGIC -- 3. Premium collected per ticker from covered calls (all time)
# MAGIC SELECT ticker, ROUND(SUM(premium_collected), 2) AS premium
# MAGIC FROM delta.`/FileStore/fidelity_delta/fct_covered_call_premiums`
# MAGIC GROUP BY ticker ORDER BY premium DESC
# MAGIC ```
# MAGIC
# MAGIC On a real Databricks workspace you would also run `OPTIMIZE` (compaction) and let a **workflow job**
# MAGIC schedule this notebook — Community Edition has no job scheduler, so just hit **Run all** after downloading fresh CSVs.

# Databricks notebook source
print("=" * 60)
print("FINAL COUNTS")
print("=" * 60)
for name, path in [("bronze fidelity_trades_bronze", BRONZE_PATH),
                   ("silver stg_fidelity_trades", SILVER_PATH),
                   ("gold  fct_wheel_mechanics", GOLD_PATHS["wheel"]),
                   ("gold  fct_cash_secured_puts", GOLD_PATHS["puts"]),
                   ("gold  fct_covered_call_premiums", GOLD_PATHS["calls"])]:
    print(f"{name}: {spark.read.load(path, format='delta').count()} rows")
