from ingest.config import load_config


def test_load_config_parses_env(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "GCP_PROJECT_ID=my-proj\n"
        "GCP_REGION=us-central1\n"
        "GCP_RAW_DATASET=raw\n"
        "GCP_ANALYTICS_DATASET=analytics\n"
        "ACCOUNT_Z90000000=LLC_MAIN\n"
        "ACCOUNT_900000001=ROTH_IRA\n"
        "FILE_ytd-export=LLC_MAIN\n"
    )
    cfg = load_config(str(env))
    assert cfg["project_id"] == "my-proj"
    assert cfg["region"] == "us-central1"
    assert cfg["account_map"] == {"Z90000000": "LLC_MAIN", "900000001": "ROTH_IRA"}
    assert cfg["file_map"] == {"ytd-export": "LLC_MAIN"}


def test_load_config_allows_missing_project(tmp_path):
    env = tmp_path / ".env"
    env.write_text("GCP_REGION=US\n")
    cfg = load_config(str(env))
    assert cfg["project_id"] is None
    assert cfg["region"] == "US"
