from dotenv import dotenv_values

PREFIX_ACCOUNT = "ACCOUNT_"
PREFIX_FILE = "FILE_"


def load_config(env_path: str = ".env") -> dict:
    values = dotenv_values(env_path)
    account_map = {}
    file_map = {}
    for key, value in values.items():
        if key.startswith(PREFIX_ACCOUNT) and value:
            account_map[key[len(PREFIX_ACCOUNT):]] = value
        elif key.startswith(PREFIX_FILE) and value:
            file_map[key[len(PREFIX_FILE):]] = value
    return {
        "project_id": values.get("GCP_PROJECT_ID"),
        "region": values.get("GCP_REGION", "US"),
        "raw_dataset": values.get("GCP_RAW_DATASET", "raw"),
        "analytics_dataset": values.get("GCP_ANALYTICS_DATASET", "analytics"),
        "account_map": account_map,
        "file_map": file_map,
    }
