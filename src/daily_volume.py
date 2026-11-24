import json

import pandas as pd

from src.config import DATA_PATH, REPORTS_DIR

EDA_PATH = REPORTS_DIR / "eda_numbers.json"


def daily_volume() -> dict:
    """Count rows and fraud rows per 24-step day window."""
    df = pd.read_parquet(DATA_PATH, columns=["step", "isFraud"])
    day = (df["step"].astype("int64") - 1) // 24
    grouped = df.groupby(day)["isFraud"].agg(["size", "sum"])
    return {
        "rows": {str(int(d)): int(r) for d, r in grouped["size"].items()},
        "fraud": {str(int(d)): int(r) for d, r in grouped["sum"].items()},
    }


def run() -> dict:
    """Write the daily volume block into the EDA numbers file."""
    numbers = json.loads(EDA_PATH.read_text())
    numbers["daily"] = daily_volume()
    EDA_PATH.write_text(json.dumps(numbers, indent=2) + "\n")
    return numbers["daily"]


if __name__ == "__main__":
    out = run()
    rows = list(out["rows"].values())
    print(len(rows), min(rows), max(rows))
