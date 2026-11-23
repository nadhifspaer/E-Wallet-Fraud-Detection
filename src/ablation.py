import json

import matplotlib
import pandas as pd
from sklearn.metrics import average_precision_score

from src.config import (
    ABLATION_FIG_PATH,
    ABLATION_PATH,
    DATA_PATH,
    EVAL_POPULATIONS,
    FEATURE_LIST,
    TYPES,
)
from src.evaluate import population_mask
from src.feature_engineering import build_features, temporal_split
from src.model import train_classifier

matplotlib.use("Agg")
import matplotlib.pyplot as plt

TYPE_COLS = [f"type_{t}" for t in TYPES]
V1 = ["amount", "hour_of_day"]
V2 = V1 + TYPE_COLS
V3 = V2 + ["oldbalanceOrg", "oldbalanceDest"]
V4 = V3 + ["orig_drain_ratio"]
V5 = V4 + ["newbalanceOrig", "newbalanceDest"]
VARIANTS = {
    "1 amount, hour": V1,
    "2 + type": V2,
    "3 + old balances": V3,
    "4 + drain ratio": V4,
    "5 + new balances": V5,
}


def _features(frame: pd.DataFrame) -> pd.DataFrame:
    """Final feature matrix plus the new-balance columns used by the last variant only."""
    X = build_features(frame)
    X["newbalanceOrig"] = frame["newbalanceOrig"].astype("float64")
    X["newbalanceDest"] = frame["newbalanceDest"].astype("float64")
    return X


def _plot(results: dict) -> None:
    """Bar chart of test PR-AUC per variant for both populations."""
    names = list(results)
    width = 0.38
    fig, ax = plt.subplots(figsize=(10, 4.5))
    series = (("transfer_cash_out", "TRANSFER and CASH_OUT", "#2c6fbb"), ("all_rows", "All rows", "#c0392b"))
    for i, (pop, label, color) in enumerate(series):
        vals = [results[n]["pr_auc"][pop] for n in names]
        ax.bar([j + (i - 0.5) * width for j in range(len(names))], vals, width, label=label, color=color)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=15)
    ax.set_title("Test PR-AUC by ablation variant")
    ax.set_xlabel("Variant")
    ax.set_ylabel("PR-AUC")
    ax.legend()
    fig.tight_layout()
    ABLATION_FIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ABLATION_FIG_PATH, dpi=150)
    plt.close(fig)


def run() -> dict:
    """Train each additive variant on the same split and score the test side."""
    assert set(V4) == set(FEATURE_LIST)
    df = pd.read_parquet(DATA_PATH)
    train, test = temporal_split(df)
    X_train, X_test = _features(train), _features(test)
    masks = {n: population_mask(test["type"], n) for n in EVAL_POPULATIONS}
    y_test = test["isFraud"].to_numpy()
    results = {}
    for name, cols in VARIANTS.items():
        model = train_classifier(X_train[cols], train["isFraud"])
        score = model.predict_proba(X_test[cols])[:, 1]
        results[name] = {
            "n_features": len(cols),
            "features": cols,
            "pr_auc": {
                p: float(average_precision_score(y_test[m], score[m])) for p, m in masks.items()
            },
        }
        print(name, results[name]["pr_auc"])
    ABLATION_PATH.write_text(json.dumps(results, indent=2) + "\n")
    _plot(results)
    return results


if __name__ == "__main__":
    run()
