import csv
import json
import os
import statistics

OVERLOAD_RATIO_MIN = 3.0
RECOVERY_DROP_MIN = 0.5
SKIP_AFTER_CHANGE = 10
STABLE_SECONDS = 60
MIN_ROWS = 5


def history(raw: str) -> list[dict]:
    """Read the Aggregated history rows with numeric fields."""
    with open(raw + "/load_stats_history.csv", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["Name"] == "Aggregated"]
    out = []
    for r in rows:
        p95 = None if r["95%"] in ("", "N/A") else float(r["95%"])
        out.append(
            {
                "ts": float(r["Timestamp"]),
                "users": int(r["User Count"]),
                "p95": p95,
                "rps": float(r["Requests/s"]),
            }
        )
    return out


def window(rows: list[dict], a: float, b: float) -> dict:
    """Median and max p95 and median rate of rows in [a, b)."""
    sel = [r for r in rows if a <= r["ts"] < b and r["p95"] is not None]
    if not sel:
        return {
            "p95_ms": None,
            "p95_max_ms": None,
            "rps": None,
            "rows": 0,
            "start": a,
            "end": b,
        }
    return {
        "p95_ms": statistics.median(r["p95"] for r in sel),
        "p95_max_ms": max(r["p95"] for r in sel),
        "rps": round(statistics.median(r["rps"] for r in sel), 1),
        "rows": len(sel),
        "start": a,
        "end": b,
    }


def stable_start(ready: list[tuple], t_from: float) -> float | None:
    """Earliest time at or after t_from from which ready and total counts hold for 60 s."""
    pts = [p for p in ready if p[0] >= t_from]
    for i, (t, r, n) in enumerate(pts):
        span = [p for p in pts[i:] if p[0] <= t + STABLE_SECONDS]
        if span[-1][0] - t >= STABLE_SECONDS - 1 and all(
            (p[1], p[2]) == (r, n) for p in span
        ):
            return t
    return None


def main() -> None:
    """Write the step-profile experiment result JSON."""
    env = os.environ
    raw = env["RAW"]
    base, step = int(env["BASE_USERS"]), int(env["STEP_USERS"])
    rows = history(raw)
    t_first_base = next(r["ts"] for r in rows if r["users"] >= base)
    t_step = next(r["ts"] for r in rows if r["users"] >= step)
    t_off = next(r["ts"] for r in rows if r["ts"] > t_step and r["users"] < step)
    t_end = rows[-1]["ts"] + 1
    with open(raw + "/ready.tsv") as f:
        ready = [
            (float(a), int(b), int(c))
            for a, b, c in (ln.split("\t") for ln in f if ln.strip())
        ]
    t_first_ready = next((t for t, r, _ in ready if t >= t_step and r > 2), None)
    t_stable = stable_start(ready, t_first_ready) if t_first_ready else None

    before = window(rows, t_first_base + SKIP_AFTER_CHANGE, t_step)
    o_start = t_step + SKIP_AFTER_CHANGE
    o_end = t_first_ready if t_first_ready else t_off
    overload = window(rows, o_start, o_end)
    if overload["rows"] < MIN_ROWS:
        overload = window(rows, t_step, o_end)
    after = window(rows, t_stable, t_off) if t_stable else window(rows, t_off, t_off)
    off = window(rows, t_off + SKIP_AFTER_CHANGE, t_end)

    ratio = (
        overload["p95_ms"] / before["p95_ms"]
        if overload["p95_ms"] and before["p95_ms"]
        else None
    )
    drop = (
        1 - after["p95_ms"] / overload["p95_ms"]
        if after["p95_ms"] and overload["p95_ms"]
        else None
    )
    criteria = {
        "overload_p95_at_least_3x_before": {
            "threshold": OVERLOAD_RATIO_MIN,
            "measured_ratio": None if ratio is None else round(ratio, 2),
            "met": ratio is not None and ratio >= OVERLOAD_RATIO_MIN,
        },
        "after_scale_out_p95_at_least_50pct_lower": {
            "threshold": RECOVERY_DROP_MIN,
            "measured_drop": None if drop is None else round(drop, 3),
            "met": drop is not None and drop >= RECOVERY_DROP_MIN,
        },
    }

    t0 = float(env["T0"])
    with open(raw + "/samples.tsv") as f:
        samples = [ln.rstrip("\n").split("\t") for ln in f]
    series = []
    for r in samples:
        cur, des = r[1].split()[:2]
        if cur.isdigit():
            series.append(
                {
                    "t": round(int(r[0]) - t_step),
                    "current": int(cur),
                    "desired": int(des),
                    "cpu_pct": None if r[2] == "NA" else int(r[2]),
                    "top": r[3].strip(),
                }
            )
    ready_series = [
        {"t": round(t - t_step, 1), "ready": r, "total": n} for t, r, n in ready[::5]
    ]
    down = env["T_DOWN"]
    res = {
        "experiment": "hpa_step",
        "environment": json.loads(env["ENV_JSON"]),
        "load": {
            "base_users": base,
            "step_users": step,
            "per_user_rps": float(env["PER_USER_RPS"]),
            "base_rps": base * float(env["PER_USER_RPS"]),
            "step_rps": step * float(env["PER_USER_RPS"]),
            "base_seconds": int(env["BASE_SECONDS"]),
            "step_seconds": int(env["STEP_SECONDS"]),
            "tail_seconds": int(env["TAIL_SECONDS"]),
            "generator": "FastHttpUser, new connection per request",
        },
        "pod_cpu_patch": {"request": env["PATCH_REQUEST"], "limit": env["PATCH_LIMIT"]}
        if env["PATCH_REQUEST"]
        else None,
        "settle_wait_seconds": int(env["SETTLE_SECONDS"]),
        "start_replicas": series[0]["current"],
        "min_replicas": 2,
        "max_replicas": 6,
        "step_start_epoch": t_step,
        "first_new_replica_ready_seconds_after_step": None
        if t_first_ready is None
        else round(t_first_ready - t_step, 1),
        "replicas_stable_seconds_after_step": None
        if t_stable is None
        else round(t_stable - t_step, 1),
        "first_scale_up_seconds_after_step": next(
            (s["t"] for s in series if s["t"] >= 0 and s["current"] > 2), None
        ),
        "peak_replicas": max(s["current"] for s in series),
        "scale_down_to_min_seconds_after_step_end": round(int(down) - t_off)
        if down
        else None,
        "windows": {
            "before": before,
            "overload": overload,
            "after_scale_out": after,
            "load_off": off,
        },
        "criteria": criteria,
        "series": series,
        "ready_series": ready_series,
        "run_start_epoch": t0,
    }
    with open(env["OUT"] + "/hpa_step.json", "w") as f:
        json.dump(res, f, indent=2)
    print(
        json.dumps(
            {k: v for k, v in res.items() if k not in ("series", "ready_series")},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
