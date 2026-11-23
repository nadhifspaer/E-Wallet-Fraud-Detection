import json

import lightgbm as lgb
import pandas as pd

from src.config import FEATURE_LIST_PATH, LGBM_PARAMS, MODEL_PATH


def train_classifier(X: pd.DataFrame, y: pd.Series, save: bool = False) -> lgb.LGBMClassifier:
    """Fit the LightGBM classifier with fixed hyperparameters, optionally saving it."""
    model = lgb.LGBMClassifier(**LGBM_PARAMS, verbose=-1)
    model.fit(X, y)
    if save:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        model.booster_.save_model(str(MODEL_PATH))
        FEATURE_LIST_PATH.write_text(json.dumps(list(X.columns), indent=2) + "\n")
    return model
