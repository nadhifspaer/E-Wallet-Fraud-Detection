import numpy as np
import pandas as pd
import pytest

from src import config
from src.config import EXCLUDED_FEATURES, FEATURE_LIST
from src.feature_engineering import build_features, temporal_split


def _frame(rows):
    cols = ["step", "type", "amount", "oldbalanceOrg", "oldbalanceDest"]
    return pd.DataFrame(rows, columns=cols)


def test_no_excluded_feature_in_feature_list():
    assert not set(EXCLUDED_FEATURES) & set(FEATURE_LIST)


def test_build_features_columns_and_dtypes():
    df = _frame([(1, "TRANSFER", 100.0, 100.0, 0.0), (30, "PAYMENT", 5.0, 50.0, 0.0)])
    feats = build_features(df)
    assert list(feats.columns) == FEATURE_LIST
    assert all(pd.api.types.is_numeric_dtype(t) for t in feats.dtypes)


def test_orig_drain_ratio_exact_drain_and_missing():
    df = _frame([(1, "TRANSFER", 100.0, 100.0, 0.0), (2, "CASH_OUT", 10.0, 0.0, 0.0)])
    feats = build_features(df)
    assert feats["orig_drain_ratio"].iloc[0] == 1.0
    assert np.isnan(feats["orig_drain_ratio"].iloc[1])


@pytest.mark.needs_data
def test_temporal_split_has_no_step_overlap():
    steps = np.arange(1, 744)
    df = _frame([(s, "PAYMENT", 1.0, 1.0, 0.0) for s in steps])
    train, test = temporal_split(df)
    assert train["step"].max() <= config.CUTOFF_STEP < test["step"].min()
    assert not set(train["step"]) & set(test["step"])
    assert len(train) + len(test) == len(df)
