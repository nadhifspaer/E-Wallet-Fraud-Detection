import os
import random

from locust import constant_throughput, task
from locust.contrib.fasthttp import FastHttpUser
from locustfile import PAYLOADS, TIMEOUT


class FastScoringUser(FastHttpUser):
    """Fixed-rate user that opens a new connection per request."""

    wait_time = constant_throughput(float(os.environ.get("PER_USER_RPS", "2")))
    network_timeout = TIMEOUT
    connection_timeout = TIMEOUT

    @task
    def predict(self) -> None:
        """Post one random feature vector to the scoring endpoint."""
        with self.client.post(
            "/predict",
            json=random.choice(PAYLOADS),
            headers={"Connection": "close"},
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"status {resp.status_code}")
