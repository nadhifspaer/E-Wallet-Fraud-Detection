import json
import math
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "processed" / "transactions.parquet"
META_PATH = ROOT / "data" / "processed" / "meta.json"

_META = json.loads(META_PATH.read_text())

MAX_STEP = int(_META["max_step"])
CUTOFF_STEP = math.floor(0.8 * MAX_STEP)
N_DAYS = math.ceil(MAX_STEP / 24)
ANCHOR_DATE = date(2026, 1, 1)

TYPES = ["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"]

EXCLUDED_FEATURES = [
    "isFraud",
    "isFlaggedFraud",
    "newbalanceOrig",
    "newbalanceDest",
    "nameOrig",
    "nameDest",
    "step",
    "txn_id",
]

FEATURE_LIST = [
    "hour_of_day",
    "amount",
    "oldbalanceOrg",
    "oldbalanceDest",
    *[f"type_{t}" for t in TYPES],
    "orig_drain_ratio",
]

LGBM_PARAMS = {
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 63,
    "random_state": 42,
    "class_weight": "balanced",
}

K_FIXED = (100, 500, 1000)
K_VOLUME_FRACTIONS = (0.001, 0.005)
TARGET_RECALLS = (0.8, 0.9)

# assumed cost of one false positive in currency units, not derivable from PaySim
FRICTION_COST_PER_FP = 5.0


def k_values(n_test_rows: int, n_test_fraud: int) -> list[int]:
    """Return the sorted unique K values for a given test split."""
    ks = {*K_FIXED, int(n_test_fraud)}
    ks.update(round(f * n_test_rows) for f in K_VOLUME_FRACTIONS)
    return sorted(k for k in ks if k > 0)
