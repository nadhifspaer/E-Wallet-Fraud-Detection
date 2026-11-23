import json
import os

from summarize import summarize

PHASES = (
    ("before", 0, 60),
    ("ramp", 60, 180),
    ("hold_early", 180, 300),
    ("hold_late", 300, 420),
)


def main() -> None:
    """Write the HPA experiment result JSON."""
    env = os.environ
    raw, t0, t_end = env["RAW"], float(env["T0"]), float(env["T_END"])
    with open(raw + "/samples.tsv") as f:
        rows = [line.rstrip("\n").split("\t") for line in f]
    series = []
    for r in rows:
        cur, des = r[1].split()[:2]
        if cur.isdigit():
            series.append(
                {
                    "t": int(r[0]) - int(t0),
                    "current": int(cur),
                    "desired": int(des),
                    "cpu_pct": None if r[2] == "NA" else int(r[2]),
                }
            )
    phases = {n: summarize(raw + "/load", t0 + a, t0 + b) for n, a, b in PHASES}
    down = env["T_DOWN"]
    res = {
        "experiment": "hpa",
        "environment": json.loads(env["ENV_JSON"]),
        "load": {
            "users_from": 10,
            "users_to": 200,
            "ramp_seconds": 120,
            "hold_seconds": 240,
        },
        "settle_wait_seconds": int(env["SETTLE_SECONDS"]),
        "start_replicas": series[0]["current"],
        "min_replicas": 2,
        "max_replicas": 6,
        "first_scale_up_seconds": next(
            (s["t"] for s in series if s["current"] > 2), None
        ),
        "peak_replicas": max(s["current"] for s in series),
        "load_end_seconds": round(t_end - t0),
        "scale_down_to_min_seconds_after_load": round(int(down) - t_end)
        if down
        else None,
        "p95_ms_by_phase": {k: v["window_p95_ms_median"] for k, v in phases.items()},
        "overall": summarize(raw + "/load"),
        "series": series,
    }
    with open(env["OUT"] + "/hpa.json", "w") as f:
        json.dump(res, f, indent=2)
    print(json.dumps({k: v for k, v in res.items() if k != "series"}, indent=2))


if __name__ == "__main__":
    main()
