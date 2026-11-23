from locust import LoadTestShape

BASELINE_USERS = 10
PEAK_USERS = 200
BASELINE_SECONDS = 60
RAMP_SECONDS = 120
HOLD_SECONDS = 240


class RampShape(LoadTestShape):
    """Hold the baseline, ramp to the peak, hold, then stop."""

    def tick(self):
        t = self.get_run_time()
        if t < BASELINE_SECONDS:
            return BASELINE_USERS, BASELINE_USERS
        if t < BASELINE_SECONDS + RAMP_SECONDS:
            frac = (t - BASELINE_SECONDS) / RAMP_SECONDS
            users = round(BASELINE_USERS + frac * (PEAK_USERS - BASELINE_USERS))
            return users, 10
        if t < BASELINE_SECONDS + RAMP_SECONDS + HOLD_SECONDS:
            return PEAK_USERS, 10
        return None
