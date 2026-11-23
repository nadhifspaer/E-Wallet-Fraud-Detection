import numpy as np
import pandas as pd
import pytest

from src.config import FEATURE_LIST
from src.score_pipeline import score


def _frame(n: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame(rng.random((n, len(FEATURE_LIST))), columns=FEATURE_LIST)


def test_score_shape_and_range():
    s = score(_frame())
    assert s.shape == (5,)
    assert ((s >= 0) & (s <= 1)).all()


def test_score_rejects_missing_column():
    with pytest.raises(ValueError):
        score(_frame().drop(columns=[FEATURE_LIST[0]]))


def test_score_rejects_extra_column():
    df = _frame()
    df["unexpected"] = 1.0
    with pytest.raises(ValueError):
        score(df)
