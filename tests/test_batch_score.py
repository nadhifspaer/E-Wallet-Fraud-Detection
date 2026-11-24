import numpy as np
import pyarrow.dataset as ds
import pytest

from src import batch_score, config
from src.batch_score import score_day, window_bounds, write_partition
from src.explainability import explain
from src.feature_engineering import build_features
from src.score_pipeline import score

pytestmark = pytest.mark.needs_data


def _count(start: int, end: int) -> int:
    d = ds.dataset(config.DATA_PATH)
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
    assert window_bounds(config.N_DAYS - 1) == (24 * (config.N_DAYS - 1) + 1, config.MAX_STEP)
    assert window_bounds(config.N_DAYS - 1) == (721, 743)


def test_out_of_range_day():
    with pytest.raises(ValueError):
        window_bounds(config.N_DAYS)


def test_explain_shape():
    rows = batch_score.extract_window(0).head(50)
    assert explain(build_features(rows)).shape == (50, 10)


@pytest.fixture(scope="module")
def day0_scores():
    return score_day(0)


def _check(df, tmp_path, monkeypatch):
    monkeypatch.setattr(batch_score, "SCORED_DIR", tmp_path)
    write_partition(df, 0)
    return batch_score.quality_check(0)


def test_quality_check_passes(day0_scores, tmp_path, monkeypatch):
    stats = _check(day0_scores, tmp_path, monkeypatch)
    assert stats["rows"] == stats["expected_rows"] == len(day0_scores)
    assert stats["score_std"] > 0


def test_quality_check_wrong_row_count(day0_scores, tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="row count"):
        _check(day0_scores.iloc[:-1], tmp_path, monkeypatch)


@pytest.mark.parametrize("column", ["txn_id", "step", "score"])
def test_quality_check_null(day0_scores, column, tmp_path, monkeypatch):
    df = day0_scores.copy()
    df[column] = df[column].astype("float64")
    df.loc[df.index[0], column] = np.nan
    with pytest.raises(ValueError, match="nulls"):
        _check(df, tmp_path, monkeypatch)


@pytest.mark.parametrize("bad", [-0.1, 1.1])
def test_quality_check_score_out_of_range(day0_scores, bad, tmp_path, monkeypatch):
    df = day0_scores.copy()
    df.loc[df.index[0], "score"] = bad
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        _check(df, tmp_path, monkeypatch)


def test_quality_check_constant_score(day0_scores, tmp_path, monkeypatch):
    df = day0_scores.copy()
    df["score"] = 0.5
    with pytest.raises(ValueError, match="standard deviation"):
        _check(df, tmp_path, monkeypatch)
