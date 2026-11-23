import json
import os


def main() -> None:
    """Write the rollout experiment result JSON."""
    env = os.environ
    phases = {}
    for name in ("rolling", "recreate", "undo"):
        with open(env["RAW"] + f"/{name}.summary.json") as f:
            phases[name] = json.load(f)
        phases[name]["action_seconds"] = int(env["S_" + name.upper()])
    with open(env["RAW"] + "/undo_ready_during.txt") as f:
        ready_during = int(f.read().strip())
    res = {
        "experiment": "rollout",
        "environment": json.loads(env["ENV_JSON"]),
        "load": {
            "users": 10,
            "seconds": int(env["LOAD_SECONDS"]),
            "hpa": "removed for this experiment",
        },
        "phases": phases,
        "undo": {
            "ready_pods_during_failed_rollout": ready_during,
            "image_after_undo": env["FINAL_IMAGE"],
        },
    }
    with open(env["OUT"] + "/rollout.json", "w") as f:
        json.dump(res, f, indent=2)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
