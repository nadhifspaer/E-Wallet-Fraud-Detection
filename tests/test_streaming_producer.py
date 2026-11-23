import pandas as pd
import pytest

from src import config
from streaming import producer

CUTOFF = 10


@pytest.fixture
def parquet_path(tmp_path, monkeypatch):
    rows = [(s, f"C{i}") for i, s in enumerate([3, 12, 8, 15, 11, 10, 20, 1, 14, 11, 9, 13])]
    df = pd.DataFrame(
        {
            "txn_id": range(len(rows), 0, -1),
            "step": [r[0] for r in rows],
            "type": "TRANSFER",
            "amount": 1.0,
            "nameOrig": [r[1] for r in rows],
            "oldbalanceOrg": 5.0,
            "newbalanceOrig": 4.0,
            "oldbalanceDest": 0.0,
            "isFraud": 0,
        }
    )
    df["type"] = df["type"].astype("category")
    df["nameOrig"] = df["nameOrig"].astype("category")
    path = tmp_path / "transactions.parquet"
    df.to_parquet(path, row_group_size=4, index=False)
    monkeypatch.setattr(config, "DATA_PATH", path)
    monkeypatch.setattr(config, "CUTOFF_STEP", CUTOFF, raising=False)
    return df


def test_row_count_matches_steps_above_cutoff(parquet_path):
    df = parquet_path
    rows = producer.load_replay_rows(None)
    assert len(rows) == int((df["step"] > CUTOFF).sum())
    assert all(r["step"] > CUTOFF for r in rows)


def test_rows_ordered_by_step_then_txn_id(parquet_path):
    rows = producer.load_replay_rows(None)
    keys = [(r["step"], r["txn_id"]) for r in rows]
    assert keys == sorted(keys)


def test_only_replay_columns_loaded(parquet_path):
    rows = producer.load_replay_rows(None)
    assert set(rows[0]) == set(producer.REPLAY_COLUMNS)


def test_max_rows_limits_count(parquet_path):
    full = producer.load_replay_rows(None)
    limited = producer.load_replay_rows(3)
    assert len(limited) == 3
    assert limited == full[:3]


def test_empty_range_returns_no_rows(parquet_path, monkeypatch):
    monkeypatch.setattr(config, "CUTOFF_STEP", 1000, raising=False)
    assert producer.load_replay_rows(None) == []
