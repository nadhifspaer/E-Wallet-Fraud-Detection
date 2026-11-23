from functools import lru_cache

import numpy as np
import pandas as pd
import shap

from src.score_pipeline import load_feature_list, load_model, validate_columns


@lru_cache(maxsize=1)
def _explainer() -> shap.TreeExplainer:
    """Build the TreeExplainer once per process."""
    return shap.TreeExplainer(load_model())


def explain(features_df: pd.DataFrame) -> np.ndarray:
    """Return SHAP values shaped (rows, number of features)."""
    validate_columns(features_df)
    values = _explainer().shap_values(features_df[load_feature_list()])
    if isinstance(values, list):
        values = values[-1]
    return np.asarray(values)
