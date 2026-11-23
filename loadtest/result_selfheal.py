import json
import os

from summarize import summarize


def main() -> None:
    """Write the self-heal experiment result JSON."""
    env = os.environ
    with open(env["RAW"] + "/liveness_events.log") as f:
        events = f.read().splitlines()
    res = {
        "experiment": "selfheal",
        "environment": json.loads(env["ENV_JSON"]),
        "load": {
            "users": 10,
            "seconds": int(env["LOAD_SECONDS"]),
            "hpa": "removed for this experiment",
        },
        "pod_delete": {
            "victim": env["VICTIM"],
            "replacement_ready_seconds": float(env["READY_A"])
            if env["READY_A"]
            else None,
        },
        "liveness_failure": {
            "pod": env["POD"],
            "restarts_before": int(env["RB"]),
            "restarts_after": int(env["RA"]),
            "ready_after_seconds": float(env["READY_B"]) if env["READY_B"] else None,
            "events": [
                e
                for e in events
                if any(k in e for k in ("Unhealthy", "Killing", "Started"))
            ],
        },
        "locust": summarize(env["RAW"] + "/load"),
    }
    with open(env["OUT"] + "/selfheal.json", "w") as f:
        json.dump(res, f, indent=2)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
