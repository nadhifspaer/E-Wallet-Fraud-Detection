import os

from locust import LoadTestShape

USERS_START = int(os.environ.get("USERS_START", "10"))
USERS_INC = int(os.environ.get("USERS_INC", "10"))
USERS_MAX = int(os.environ.get("USERS_MAX", "250"))
STEP_SECONDS = int(os.environ.get("STEP_SECONDS", "20"))


class CalibShape(LoadTestShape):
    """Raise the user count by a fixed increment every step."""

    def tick(self):
        users = USERS_START + USERS_INC * int(self.get_run_time() // STEP_SECONDS)
        if users > USERS_MAX:
            return None
        return users, 50
