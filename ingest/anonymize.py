import re

ACCOUNT_RE = re.compile(r"History_for_Account_([A-Z0-9]+)")


def label_for_filename(filename: str, account_map: dict[str, str], file_map: dict[str, str]) -> str:
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


def sanitize_filename(filename: str, account_map: dict[str, str]) -> str:
    def repl(match):
        account = match.group(1)
        return f"History_for_Account_{account_map.get(account, 'REDACTED')}"

    return ACCOUNT_RE.sub(repl, filename)
