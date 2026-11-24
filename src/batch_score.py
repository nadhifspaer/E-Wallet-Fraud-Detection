import shutil
from datetime import timedelta

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

from src.config import ANCHOR_DATE, DATA_PATH, MAX_STEP, N_DAYS, ROOT
from src.feature_engineering import build_features
from src.score_pipeline import score

SCORED_DIR = ROOT / "data" / "scored"


def window_bounds(day_index: int) -> tuple[int, int]:
    """Return the first and last step of a day window."""
    if not 0 <= day_index < N_DAYS:
        raise ValueError(f"day_index must be in [0, {N_DAYS - 1}]")
    return 24 * day_index + 1, min(24 * day_index + 24, MAX_STEP)


def extract_window(day_index: int) -> pd.DataFrame:
    """Read only the window rows from the processed parquet."""
    start, end = window_bounds(day_index)
    filters = [("step", ">=", start), ("step", "<=", end)]
    return pd.read_parquet(DATA_PATH, filters=filters)


def score_day(day_index: int) -> pd.DataFrame:
    """Score one day window and return txn_id, step, score."""
    rows = extract_window(day_index)
    scores = score(build_features(rows))
    return pd.DataFrame(
        {
            "txn_id": rows["txn_id"].to_numpy(),
            "step": rows["step"].to_numpy(),
            "score": scores,
        }
    )


def partition_dir(day_index: int):
    """Return the output directory of a day partition."""
    return SCORED_DIR / f"date={ANCHOR_DATE + timedelta(days=day_index)}"


def write_partition(df: pd.DataFrame, day_index: int) -> None:
    """Overwrite the day partition with a single parquet file."""
    out = partition_dir(day_index)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    df.to_parquet(out / "part-0.parquet", index=False)


def expected_row_count(day_index: int) -> int:
    """Count the source rows inside a day window."""
    start, end = window_bounds(day_index)
    flt = (ds.field("step") >= start) & (ds.field("step") <= end)
    return ds.dataset(DATA_PATH).count_rows(filter=flt)


def quality_check(day_index: int) -> dict:
    """Validate a written day partition and return its statistics."""
    df = ds.dataset(partition_dir(day_index)).to_table().to_pandas()
    expected = expected_row_count(day_index)
    nulls = int(df[["txn_id", "step", "score"]].isna().sum().sum())
    stats = {
        "day_index": day_index,
        "rows": len(df),
        "expected_rows": expected,
        "nulls": nulls,
        "score_min": float(df["score"].min()),
        "score_max": float(df["score"].max()),
        "score_std": float(np.std(df["score"].to_numpy())),
    }
    errors = []
    if stats["rows"] != expected:
        errors.append(f"row count {stats['rows']} != expected {expected}")
    if nulls:
        errors.append(f"{nulls} nulls in txn_id, step, score")
    if not (stats["score_min"] >= 0.0 and stats["score_max"] <= 1.0):
        errors.append("scores outside [0, 1]")
    if not stats["score_std"] > 0:
        errors.append("score standard deviation is not above 0")
    if errors:
        raise ValueError(f"quality check failed for day {day_index}: {'; '.join(errors)} {stats}")
    return stats


def run_day(day_index: int) -> int:
    """Score a day and write its partition, returning the row count."""
    df = score_day(day_index)
    write_partition(df, day_index)
    return len(df)


if __name__ == "__main__":
    import sys

    print(run_day(int(sys.argv[1])))
