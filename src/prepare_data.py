import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "paysim_transactions.csv"
OUT_DIR = ROOT / "data" / "processed"
PARQUET_PATH = OUT_DIR / "transactions.parquet"
META_PATH = OUT_DIR / "meta.json"

DTYPES = {
    "step": "int16",
    "type": "category",
    "amount": "float64",
    "nameOrig": "category",
    "oldbalanceOrg": "float64",
    "newbalanceOrig": "float64",
    "nameDest": "category",
    "oldbalanceDest": "float64",
    "newbalanceDest": "float64",
    "isFraud": "int8",
    "isFlaggedFraud": "int8",
}


def prepare() -> dict:
    """Convert the raw CSV to a sorted Parquet file and write its metadata."""
    df = pd.read_csv(RAW_PATH, dtype=DTYPES)
    df.insert(0, "txn_id", pd.RangeIndex(len(df)).astype("int32"))
    df = df.sort_values(["step", "txn_id"], kind="stable").reset_index(drop=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PARQUET_PATH, index=False)

    meta = {
        "max_step": int(df["step"].max()),
        "row_count": len(df),
        "fraud_count": int(df["isFraud"].sum()),
    }
    META_PATH.write_text(json.dumps(meta, indent=2) + "\n")
    return meta


if __name__ == "__main__":
    print(prepare())
