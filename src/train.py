import json

import pandas as pd

from src.config import CUTOFF_STEP, DATA_PATH, FRICTION_COST_PER_FP, METRICS_PATH
from src.evaluate import evaluate_test
from src.feature_engineering import build_features, temporal_split
from src.model import train_classifier


def run() -> dict:
    """Train on the train side, evaluate on the test side, write metrics.json."""
    df = pd.read_parquet(DATA_PATH)
    train, test = temporal_split(df)
    model = train_classifier(build_features(train), train["isFraud"], save=True)
    score = model.predict_proba(build_features(test))[:, 1]
    metrics = {
        "cutoff_step": CUTOFF_STEP,
        "friction_cost_per_fp": FRICTION_COST_PER_FP,
        "train": {
            "n_rows": len(train),
            "n_fraud": int(train["isFraud"].sum()),
            "prevalence": float(train["isFraud"].mean()),
        },
        "test": evaluate_test(test, score),
    }
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2) + "\n")
    return metrics


if __name__ == "__main__":
    m = run()
    for name, pop in m["test"].items():
        print(name, pop["n_rows"], pop["n_fraud"], round(pop["pr_auc"], 4))
