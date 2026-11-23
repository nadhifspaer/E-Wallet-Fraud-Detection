import numpy as np
import pyarrow.dataset as ds
import pytest

from src import batch_score
from src.batch_score import score_day, window_bounds, write_partition
from src.config import DATA_PATH, MAX_STEP, N_DAYS
from src.explainability import explain
from src.feature_engineering import build_features
from src.score_pipeline import score


def _count(start: int, end: int) -> int:
    d = ds.dataset(DATA_PATH)
    return d.count_rows(filter=(ds.field("step") >= start) & (ds.field("step") <= end))


def test_row_count_matches_window():
    start, end = window_bounds(0)
    assert len(score_day(0)) == _count(start, end)


def test_score_day_equals_score_of_features():
    rows = batch_score.extract_window(5)
    expected = score(build_features(rows))
    out = score_day(5)
    assert np.array_equal(out["score"].to_numpy(), expected)
    assert list(out.columns) == ["txn_id", "step", "score"]


def test_partition_rewrite_keeps_row_count(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_score, "SCORED_DIR", tmp_path)
    df = score_day(0)
    write_partition(df, 0)
    write_partition(df, 0)
    out = ds.dataset(batch_score.partition_dir(0))
    assert out.count_rows() == len(df)


def test_last_day_window():
    assert window_bounds(N_DAYS - 1) == (24 * (N_DAYS - 1) + 1, MAX_STEP)
    assert window_bounds(N_DAYS - 1) == (721, 743)


def test_out_of_range_day():
    with pytest.raises(ValueError):
        window_bounds(N_DAYS)


def test_explain_shape():
    rows = batch_score.extract_window(0).head(50)
    assert explain(build_features(rows)).shape == (50, 10)
