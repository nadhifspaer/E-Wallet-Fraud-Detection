import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from src.config import (
    EVAL_POPULATIONS,
    FRICTION_COST_PER_FP,
    FRICTION_MULTIPLIERS,
    TARGET_RECALLS,
    k_values,
)


def _ranked_flags(score: np.ndarray, y: np.ndarray, target: float) -> tuple[float, np.ndarray]:
    """Return the score threshold reaching the target recall and the flag mask."""
    order = np.argsort(-score, kind="stable")
    need = int(np.ceil(target * y.sum()))
    cum_tp = np.cumsum(y[order])
    idx = int(np.searchsorted(cum_tp, need))
    threshold = float(score[order][idx])
    return threshold, score >= threshold


def _fpr_and_cost(score: np.ndarray, y: np.ndarray, amount: np.ndarray, target: float) -> dict:
    """FPR and cost at the score threshold that reaches the target recall."""
    threshold, flag = _ranked_flags(score, y, target)
    fraud = y == 1
    tp = int((flag & fraud).sum())
    fp = int((flag & ~fraud).sum())
    n_legit = int((~fraud).sum())
    prevented = float(amount[flag & fraud].sum())
    missed = float(amount[~flag & fraud].sum())
    cost = {}
    for mult in FRICTION_MULTIPLIERS:
        friction = fp * FRICTION_COST_PER_FP * mult
        cost[f"friction_x{mult:g}"] = {
            "friction_cost": friction,
            "total_cost": missed + friction,
            "net_benefit": prevented - friction,
        }
    return {
        "threshold": threshold,
        "flagged": int(flag.sum()),
        "tp": tp,
        "fp": fp,
        "recall": tp / int(fraud.sum()),
        "fpr": fp / n_legit,
        "prevented_loss": prevented,
        "missed_loss": missed,
        "cost": cost,
    }


def evaluate_population(y, score, amount) -> dict:
    """Compute all metrics for one population."""
    y = np.asarray(y).astype(int)
    score = np.asarray(score, dtype=float)
    amount = np.asarray(amount, dtype=float)
    n_rows, n_fraud = len(y), int(y.sum())
    order = np.argsort(-score, kind="stable")
    cum_tp = np.cumsum(y[order])
    precision_at_k, recall_at_k = {}, {}
    for k in (k for k in k_values(n_rows, n_fraud) if k <= n_rows):
        tp_k = int(cum_tp[k - 1])
        recall_at_k[str(k)] = tp_k / n_fraud
        if k <= n_fraud:
            precision_at_k[str(k)] = tp_k / k
    return {
        "n_rows": n_rows,
        "n_fraud": n_fraud,
        "prevalence": n_fraud / n_rows,
        "median_legit_amount": float(np.median(amount[y == 0])),
        "pr_auc": float(average_precision_score(y, score)),
        "precision_at_k": precision_at_k,
        "recall_at_k": recall_at_k,
        "at_target_recall": {
            f"{t:g}": _fpr_and_cost(score, y, amount, t) for t in TARGET_RECALLS
        },
    }


def population_mask(types: pd.Series, name: str) -> np.ndarray:
    """Boolean mask of the rows belonging to a named evaluation population."""
    allowed = EVAL_POPULATIONS[name]
    if allowed is None:
        return np.ones(len(types), dtype=bool)
    return types.astype(str).isin(allowed).to_numpy()


def evaluate_test(test: pd.DataFrame, score: np.ndarray) -> dict:
    """Evaluate test-split scores on every population."""
    out = {}
    for name in EVAL_POPULATIONS:
        m = population_mask(test["type"], name)
        out[name] = evaluate_population(
            test["isFraud"].to_numpy()[m], score[m], test["amount"].to_numpy()[m]
        )
    return out
