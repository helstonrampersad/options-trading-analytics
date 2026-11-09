#!/usr/bin/env python3
"""Pre-push privacy scan for this repository (standard library only).

    python scripts/privacy_check.py              # scan for private-data shapes
    python scripts/privacy_check.py --env .env   # also search for real .env values

Exit 0 = clean, 1 = hits. Matches are masked: no account number or token is printed.
"""

import argparse
import os
import re
import sys
from pathlib import Path

# Directories that never contain publishable source (private data, caches, envs).
SKIP_DIRS = {
    ".git", ".venv", "venv", "data", "target", "logs", "__pycache__", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", "dbt_packages", "node_modules", ".vscode", ".idea",
    "spark-warehouse", "metastore_db",
}

PATTERNS = [
    ("real Fidelity export filename", re.compile(r"History_for_Account_[0-9A-Z]+")),
    ("Databricks access token", re.compile(r"dapi[0-9a-f]{32,}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_-]{30,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY")),
    ("GitHub token", re.compile(r"ghp_[0-9A-Za-z]{20,}")),
    ("Slack token", re.compile(r"xox[abp]-")),
    ("Databricks workspace URL", re.compile(r"dbc-[a-z0-9-]+\.cloud\.databricks\.com")),
    ("Windows user path", re.compile(r"C:\\Users\\[A-Za-z0-9_-]+\\", re.IGNORECASE)),
    ("WSL Windows user path", re.compile(r"/mnt/c/Users/[A-Za-z0-9_-]+/", re.IGNORECASE)),
    ("gcloud config path", re.compile(r"\.config/gcloud")),
]

# Documented fake account tokens used by unit tests; otherwise the scanner would
# flag its own synthetic fixtures. Real broker exports never look like these.
PLACEHOLDER_ACCOUNTS = {"Z90000000", "Z90000001", "ZZ00000", "ZZ99999", "LLC", "INDIVIDUAL", "REDACTED"}
ENV_KEYS = {"GCP_PROJECT_ID", "DATABRICKS_HOST", "DATABRICKS_TOKEN"}
MAX_BYTES = 5_000_000


def is_placeholder(text: str) -> bool:
    """True for synthetic account tokens used in tests (e.g. Z90000000)."""
    token = text.rsplit("_", 1)[-1]
    return token in PLACEHOLDER_ACCOUNTS or (token.startswith("Z") and set(token[1:]) == {"0"})


def mask(text: str) -> str:
    text = text.strip()
    return "*" * len(text) if len(text) <= 8 else text[:8] + "..." + text[-2:]


def iter_text_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name == ".env" or (name.startswith(".env") and name != ".env.example"):
                continue  # local secret files are expected; they must stay uncommitted
            path = Path(dirpath) / name
            if path.resolve() == Path(__file__).resolve():
                continue  # this file intentionally contains the patterns themselves
            try:
                data = path.read_bytes()
            except OSError:
                continue
            if len(data) > MAX_BYTES or b"\x00" in data[:1024]:
                continue
            try:
                yield path, data.decode("utf-8")
            except UnicodeDecodeError:
                continue


def load_env_values(path: Path) -> dict[str, str]:
    """Tiny .env parser: map each sensitive key to the real value to search for (never printed)."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("\"'")
        if key in ENV_KEYS and len(value) >= 4:
            values[key] = value
        elif key.startswith("ACCOUNT_") and len(key) > len("ACCOUNT_") + 3:
            # .env holds ACCOUNT_<real account number>=<public label>, so the secret is
            # the part of the KEY, not the label value.
            values[key] = key[len("ACCOUNT_"):]
    return values


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fail if private data or secrets look publishable.")
    parser.add_argument("--env", default=".env", help="also search for real values from this env file")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    env_path = Path(args.env) if Path(args.env).is_absolute() else root / args.env
    env_values = load_env_values(env_path) if env_path.is_file() else {}
    if not env_path.is_file():
        print(f"note: {env_path.name} not found - skipping real-value scan")

    hits = []
    scanned = 0
    for path, text in iter_text_files(root):
        scanned += 1
        rel = path.relative_to(root)
        for lineno, line in enumerate(text.splitlines(), 1):
            for label, pattern in PATTERNS:
                for match in pattern.finditer(line):
                    if label.startswith("real Fidelity") and is_placeholder(match.group()):
                        continue
                    hits.append(f"{rel}:{lineno}: {label}: {mask(match.group())}")
            for key, value in env_values.items():
                if value not in line:
                    continue
                if rel.name == ".env.example" and line.lstrip().startswith("ACCOUNT_"):
                    continue  # documented placeholder mappings, not real values
                # Never echo the key for ACCOUNT_*: its suffix IS the real account number.
                label = "ACCOUNT_***" if key.startswith("ACCOUNT_") else key
                hits.append(f"{rel}:{lineno}: real {label} value (masked)")
    if hits:
        print("PRIVACY CHECK FAILED - potential private data found:")
        for hit in hits:
            print(f"  {hit}")
        print(f"\n{len(hits)} hit(s). Remove or anonymize them before pushing.")
        return 1

    print(f"Privacy check passed: scanned {scanned} files, no private-data patterns found.")
    if env_values:
        print(f"Also searched {len(env_values)} real value(s) from {env_path.name}: none appear in the repo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
