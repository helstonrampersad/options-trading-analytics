import pytest

from ingest.anonymize import label_for_filename, sanitize_filename


@pytest.fixture
def maps():
    return (
        {"Z90000000": "LLC_MAIN", "900000001": "ROTH_IRA", "Z90000001": "INDIVIDUAL_LEGACY"},
        {"monthly-export": "LLC_MAIN", "ytd-export": "LLC_MAIN"},
    )


def test_label_from_standard_name(maps):
    account_map, file_map = maps
    assert label_for_filename("History_for_Account_Z90000000 (35).csv", account_map, file_map) == "LLC_MAIN"


def test_label_from_year_prefix_name(maps):
    account_map, file_map = maps
    assert label_for_filename("2023-History_for_Account_Z90000001 (42).csv", account_map, file_map) == "INDIVIDUAL_LEGACY"


def test_label_from_file_map(maps):
    account_map, file_map = maps
    assert label_for_filename("ytd-export.csv", account_map, file_map) == "LLC_MAIN"


def test_label_raises_on_unknown(maps):
    account_map, file_map = maps
    with pytest.raises(ValueError, match="unknown account"):
        label_for_filename("History_for_Account_ZZ99999 (1).csv", account_map, file_map)


def test_sanitize_removes_real_numbers(maps):
    account_map, _ = maps
    out = sanitize_filename("2023-History_for_Account_Z90000001 (42).csv", account_map)
    assert "Z90000001" not in out
    assert out == "2023-History_for_Account_INDIVIDUAL_LEGACY (42).csv"
