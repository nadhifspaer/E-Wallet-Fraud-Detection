import csv
import os
import random
from pathlib import Path

from locust import HttpUser, between, task

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample" / "sample_features.csv"
DROP = {"isFraud", "txn_id"}
NULLABLE = {"orig_drain_ratio"}


def load_payloads() -> list[dict]:
    """Read the sample feature rows as JSON-ready payloads."""
    payloads = []
    with SAMPLE.open(newline="") as f:
        for row in csv.DictReader(f):
            body = {}
            for key, value in row.items():
                if key in DROP:
                    continue
                body[key] = None if value == "" and key in NULLABLE else float(value)
            payloads.append(body)
    return payloads


PAYLOADS = load_payloads()
TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "5"))


class ScoringUser(HttpUser):
    wait_time = between(0.05, 0.15)

    @task
    def predict(self) -> None:
        """Post one random feature vector to the scoring endpoint."""
        with self.client.post(
            "/predict",
            json=random.choice(PAYLOADS),
            timeout=TIMEOUT,
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"status {resp.status_code}")
