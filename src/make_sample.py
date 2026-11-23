import pandas as pd

from src.config import CUTOFF_STEP, DATA_PATH, FEATURE_LIST, SAMPLE_PATH
from src.feature_engineering import build_features

SEED = 42
N_FRAUD = 100
N_NON_FRAUD = 400
MIN_MISSING_RATIO = 5


def build_sample(test: pd.DataFrame) -> pd.DataFrame:
    """Draw the display sample from test-range rows with a fixed seed."""
    fraud = test[test["isFraud"] == 1].sample(N_FRAUD, random_state=SEED)
    legit = test[test["isFraud"] == 0]
    feats = build_features(legit)
    missing = legit[feats["orig_drain_ratio"].isna()]
    present = legit.drop(index=missing.index)
    n_missing = max(MIN_MISSING_RATIO, round(N_NON_FRAUD * len(missing) / len(legit)))
    picked = pd.concat(
        [
            missing.sample(n_missing, random_state=SEED),
            present.sample(N_NON_FRAUD - n_missing, random_state=SEED),
        ]
    )
    rows = pd.concat([fraud, picked]).sort_values("txn_id")
    out = build_features(rows)
    out.insert(0, "txn_id", rows["txn_id"].to_numpy())
    out["isFraud"] = rows["isFraud"].to_numpy()
    return out.reset_index(drop=True)[["txn_id", *FEATURE_LIST, "isFraud"]]


def run() -> pd.DataFrame:
    """Write the sample CSV and return it."""
    df = pd.read_parquet(DATA_PATH)
    sample = build_sample(df[df["step"] > CUTOFF_STEP])
    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(SAMPLE_PATH, index=False)
    return sample


if __name__ == "__main__":
    s = run()
    print(len(s), int(s["isFraud"].sum()), int(s["orig_drain_ratio"].isna().sum()))
