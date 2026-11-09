# ingest/parse_fidelity.py
import csv
import hashlib
import logging
import re
from pathlib import Path

log = logging.getLogger("ingest")

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
            if key in ("price", "quantity", "commission", "fees",
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


def parse_file(path, source_label=None):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    header_idx = find_header(rows)
    header = rows[header_idx]
    has_exchange_qty = any("Exchange Quantity" in h for h in header)
    column_map = LEGACY_MAP if has_exchange_qty else CURRENT_MAP
    out = []
    dropped = 0
    for row in rows[header_idx + 1:]:
        if not row or all(not c.strip() for c in row):
            continue
        record = _normalize_row(row, header, column_map)
        if record["run_date"] is None:
            dropped += 1
            continue
        out.append(record)
    if dropped:
        log.warning(
            "%s: dropped %d rows with unparseable/missing run_date",
            source_label or Path(path).name,
            dropped,
        )
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
    """Hash a trade by its stable payload plus its occurrence index within one export file.

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
