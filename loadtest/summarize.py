import csv
import json
import sys


def summarize(prefix: str, t0: float | None = None, t1: float | None = None) -> dict:
    """Summarize a Locust CSV run, optionally within an epoch-time window."""
    with open(f"{prefix}_stats.csv", newline="") as f:
        agg = next(r for r in csv.DictReader(f) if r["Name"] == "Aggregated")
    out = {
        "requests": int(agg["Request Count"]),
        "failures": int(agg["Failure Count"]),
        "rps": round(float(agg["Requests/s"]), 1),
        "p50_ms": float(agg["50%"]),
        "p95_ms": float(agg["95%"]),
        "p99_ms": float(agg["99%"]),
    }
    out["error_rate"] = round(out["failures"] / max(out["requests"], 1), 6)
    if t0 is not None:
        with open(f"{prefix}_stats_history.csv", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["Name"] == "Aggregated"]
        win = [
            float(r["95%"])
            for r in rows
            if t0 <= float(r["Timestamp"]) < t1 and r["95%"] not in ("", "N/A")
        ]
        out["window_p95_ms_median"] = sorted(win)[len(win) // 2] if win else None
        out["window_samples"] = len(win)
    return out


if __name__ == "__main__":
    print(json.dumps(summarize(sys.argv[1]), indent=2))
