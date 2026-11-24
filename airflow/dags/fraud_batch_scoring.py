import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
from airflow.sdk import DAG, get_current_context, task
from airflow.timetables.interval import CronDataIntervalTimetable

from src import batch_score
from src.config import ANCHOR_DATE, N_DAYS
from src.feature_engineering import build_features

ANCHOR = datetime(ANCHOR_DATE.year, ANCHOR_DATE.month, ANCHOR_DATE.day, tzinfo=UTC)
SCRATCH_ROOT = Path("/tmp/fraud_batch_scoring")


def _day_index() -> int:
    """Derive the day index from the data interval start."""
    start = get_current_context()["data_interval_start"]
    return (start.date() - ANCHOR_DATE).days


def _scratch(day_index: int) -> Path:
    """Return the scratch directory of a day."""
    return SCRATCH_ROOT / f"day={day_index}"


with DAG(
    dag_id="fraud_batch_scoring",
    schedule=CronDataIntervalTimetable("@daily", timezone="UTC"),
    start_date=ANCHOR,
    end_date=ANCHOR + timedelta(days=N_DAYS - 1),
    catchup=True,
    max_active_runs=2,
    default_args={"retries": 2, "retry_delay": timedelta(seconds=10)},
    tags=["fraud", "batch"],
) as dag:

    @task
    def extract_window() -> str:
        """Write the window rows to scratch and return the path."""
        day = _day_index()
        scratch = _scratch(day)
        shutil.rmtree(scratch, ignore_errors=True)
        scratch.mkdir(parents=True)
        path = scratch / "window.parquet"
        batch_score.extract_window(day).to_parquet(path, index=False)
        return str(path)

    @task(task_id="build_features")
    def build_features_task(window_path: str) -> str:
        """Build the feature matrix and return its path."""
        path = Path(window_path).with_name("features.parquet")
        build_features(pd.read_parquet(window_path)).to_parquet(path, index=False)
        return str(path)

    @task
    def score_batch(window_path: str, features_path: str) -> str:
        """Score the feature matrix and return the scores path."""
        from src.score_pipeline import score

        rows = pd.read_parquet(window_path, columns=["txn_id", "step"])
        scores = score(pd.read_parquet(features_path))
        rows["score"] = scores
        path = Path(window_path).with_name("scores.parquet")
        rows.to_parquet(path, index=False)
        return str(path)

    @task
    def write_partition(scores_path: str) -> int:
        """Overwrite the day partition and return its row count."""
        df = pd.read_parquet(scores_path)
        batch_score.write_partition(df, _day_index())
        return len(df)

    @task
    def quality_check(written_rows: int) -> dict:
        """Validate the day partition and remove the scratch directory."""
        day = _day_index()
        try:
            stats = batch_score.quality_check(day)
        finally:
            shutil.rmtree(_scratch(day), ignore_errors=True)
        print(stats)
        return stats

    window = extract_window()
    features = build_features_task(window)
    scores = score_batch(window, features)
    quality_check(write_partition(scores))
