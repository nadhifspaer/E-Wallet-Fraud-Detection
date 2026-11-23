import json
from functools import lru_cache

import lightgbm as lgb
import numpy as np
import pandas as pd

from src.config import FEATURE_LIST_PATH, MODEL_PATH


@lru_cache(maxsize=1)
def load_feature_list() -> list[str]:
    """Load the saved feature list."""
    return json.loads(FEATURE_LIST_PATH.read_text())


@lru_cache(maxsize=1)
def load_model() -> lgb.Booster:
    """Load the saved booster once per process."""
    return lgb.Booster(model_file=str(MODEL_PATH))


def validate_columns(features_df: pd.DataFrame) -> None:
    """Raise ValueError when columns differ from the saved feature list."""
    expected = load_feature_list()
    missing = [c for c in expected if c not in features_df.columns]
    extra = [c for c in features_df.columns if c not in expected]
    if missing or extra:
        raise ValueError(f"feature mismatch, missing={missing}, extra={extra}")


def score(features_df: pd.DataFrame) -> np.ndarray:
    """Return fraud probabilities for a ready feature matrix."""
    validate_columns(features_df)
    X = features_df[load_feature_list()]
    return np.asarray(load_model().predict(X, num_threads=1), dtype="float64")
