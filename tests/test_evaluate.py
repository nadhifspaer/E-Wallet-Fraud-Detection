import json

import lightgbm as lgb
import numpy as np
import pandas as pd

from src.evaluate import evaluate_population
from src.model import train_classifier


def _toy():
    y = np.array([1, 1, 0, 0, 0, 0, 1, 0, 0, 0])
    score = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05])
    amount = np.array([100.0, 200.0, 5.0, 5.0, 5.0, 5.0, 300.0, 5.0, 5.0, 5.0])
    return y, score, amount


def test_precision_skipped_above_fraud_count_and_recall_kept():
    y, score, amount = _toy()
    m = evaluate_population(y, score, amount)
    assert all(int(k) <= m["n_fraud"] for k in m["precision_at_k"])
    assert m["recall_at_k"]["3"] == 2 / 3
    assert m["precision_at_k"]["3"] == 2 / 3
    assert "100" not in m["precision_at_k"]


def test_target_recall_threshold_and_cost():
    y, score, amount = _toy()
    m = evaluate_population(y, score, amount)
    t = m["at_target_recall"]["0.8"]
    assert t["recall"] == 1.0
    assert t["tp"] == 3 and t["fp"] == 4
    assert t["missed_loss"] == 0.0
    assert t["cost"]["friction_x10"]["friction_cost"] == 4 * 10000.0 * 10
    assert m["median_legit_amount"] == 5.0
    assert m["prevalence"] == 0.3


def test_train_classifier_saves_and_reloads(tmp_path, monkeypatch):
    import src.model as model_mod

    monkeypatch.setattr(model_mod, "MODEL_PATH", tmp_path / "model.txt")
    monkeypatch.setattr(model_mod, "FEATURE_LIST_PATH", tmp_path / "feature_list.json")
    rng = np.random.default_rng(0)
    X = pd.DataFrame({"a": rng.normal(size=400), "b": rng.normal(size=400)})
    y = pd.Series((X["a"] > 1).astype(int))
    clf = train_classifier(X, y, save=True)
    booster = lgb.Booster(model_file=str(tmp_path / "model.txt"))
    assert np.allclose(booster.predict(X), clf.predict_proba(X)[:, 1])
    assert json.loads((tmp_path / "feature_list.json").read_text()) == ["a", "b"]
