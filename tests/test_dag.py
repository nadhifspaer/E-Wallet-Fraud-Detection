import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("airflow.timetables.interval")

from airflow.timetables.base import TimeRestriction
from airflow.timetables.interval import CronDataIntervalTimetable

from src.config import ANCHOR_DATE, N_DAYS

DAG_FILE = Path(__file__).resolve().parents[1] / "airflow" / "dags" / "fraud_batch_scoring.py"


@pytest.fixture(scope="module")
def dag():
    spec = importlib.util.spec_from_file_location("fraud_batch_scoring", DAG_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.dag


def _day_indices(dag):
    restriction = TimeRestriction(earliest=dag.start_date, latest=dag.end_date, catchup=dag.catchup)
    days, last = [], None
    while True:
        info = dag.timetable.next_dagrun_info(
            last_automated_data_interval=last, restriction=restriction
        )
        if info is None:
            return days
        days.append((info.data_interval.start.date() - ANCHOR_DATE).days)
        last = info.data_interval


def test_dag_imports_with_expected_tasks(dag):
    assert dag.dag_id == "fraud_batch_scoring"
    assert set(dag.task_dict) == {
        "extract_window",
        "build_features",
        "score_batch",
        "write_partition",
        "quality_check",
    }


def test_dag_settings(dag):
    assert isinstance(dag.timetable, CronDataIntervalTimetable)
    assert dag.catchup is True
    assert dag.max_active_runs == 2
    assert dag.default_args["retries"] == 2
    assert (dag.end_date.date() - dag.start_date.date()).days == N_DAYS - 1


def test_runs_map_to_day_indices_without_gaps_or_duplicates(dag):
    days = _day_indices(dag)
    assert days == list(range(N_DAYS))
