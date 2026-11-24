import os

from locust import LoadTestShape

BASE_USERS = int(os.environ.get("BASE_USERS", "15"))
STEP_USERS = int(os.environ.get("STEP_USERS", "100"))
BASE_SECONDS = int(os.environ.get("BASE_SECONDS", "90"))
STEP_SECONDS = int(os.environ.get("STEP_SECONDS", "300"))
TAIL_SECONDS = int(os.environ.get("TAIL_SECONDS", "120"))


class StepShape(LoadTestShape):
    """Baseline load, one step up, a hold, then back to the baseline."""

    def tick(self):
        t = self.get_run_time()
        if t < BASE_SECONDS:
            return BASE_USERS, 50
        if t < BASE_SECONDS + STEP_SECONDS:
            return STEP_USERS, 50
        if t < BASE_SECONDS + STEP_SECONDS + TAIL_SECONDS:
            return BASE_USERS, 50
        return None
