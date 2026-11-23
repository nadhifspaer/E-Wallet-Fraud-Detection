import numpy as np
import pandas as pd

from src import config
from src.config import FEATURE_LIST, TYPES


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build the feature matrix with exactly FEATURE_LIST columns."""
    out = pd.DataFrame(index=df.index)
    out["hour_of_day"] = (df["step"].to_numpy() % 24).astype("int8")
    out["amount"] = df["amount"].astype("float64")
    out["oldbalanceOrg"] = df["oldbalanceOrg"].astype("float64")
    out["oldbalanceDest"] = df["oldbalanceDest"].astype("float64")
    for t in TYPES:
        out[f"type_{t}"] = (df["type"].astype(str) == t).astype("int8")
    old = out["oldbalanceOrg"].to_numpy()
    safe = np.where(old == 0, np.nan, old)
    out["orig_drain_ratio"] = out["amount"].to_numpy() / safe
    return out[FEATURE_LIST]


def temporal_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split rows into train (step <= CUTOFF_STEP) and test (step > CUTOFF_STEP)."""
    mask = df["step"] <= config.CUTOFF_STEP
    return df[mask], df[~mask]
