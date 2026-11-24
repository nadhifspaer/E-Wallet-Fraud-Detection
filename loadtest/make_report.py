import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "reports" / "serving_results"
REPORT = ROOT / "reports" / "serving_benchmark.md"


def load(name: str) -> dict | None:
    """Read one result JSON, or None when the run has not happened."""
    path = RESULTS / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


def fmt(value, unit: str = "") -> str:
    """Format a measured value or mark it as not reached."""
    return "not reached" if value is None else f"{value}{unit}"


def capacity_section(cap: dict) -> list[str]:
    """Render the capacity calibration section."""
    g = cap["generator"]
    patch = cap["pod_cpu_patch"]
    lines = [
        "## Capacity calibration",
        "",
        (
            "The HPA was removed and the deployment held at a fixed replica count. The load rose by 10 users every "
            f"{g['step_seconds']} s, each user sending {g['per_user_rps']} requests per second. "
            f"The generator is Locust `FastHttpUser` ({g['processes']} process) and opens a new connection per request. "
            "Per-step p95 is the median of the per-second p95 values after the first 10 s of the step. "
            "The knee is the first step where that p95 and the next step's p95 are both at least 3 times the median p95 of the first three steps."
        ),
        "",
        "| Replicas | Baseline p95 ms | Knee offered rps | Knee measured rps | Max measured rps | CPU ms per request | Generator CPU max % of one core |",
        "|---|---|---|---|---|---|---|",
    ]
    for key in ("1", "2"):
        c = cap["configs"][key]
        cpu = c["cpu_ms_per_request_median"]
        if cpu is None:
            vals = [
                s["cpu_ms_per_request"] for s in c["steps"] if s["cpu_ms_per_request"]
            ]
            cpu = (
                f"{round(sum(vals) / len(vals), 3)} (saturated steps)"
                if vals
                else "n/a"
            )
        lines.append(
            f"| {key} | {c['baseline_p95_ms']} | {c['knee_offered_rps']} | {c['knee_measured_rps']} | "
            f"{c['max_measured_rps']} | {cpu} | {c['locust_cpu_max_pct']} |"
        )
    lines += [
        "",
        (
            f"Generator CPU stayed below 80% of one core in every run (maximum {g['max_process_cpu_pct']}%). "
            "CPU per request is the pod cgroup CPU time divided by the requests served in the step window."
        ),
    ]
    if patch:
        lines.append(
            f"Pod CPU was patched for the calibration and the step run only: request {patch['request']}, limit {patch['limit']}."
        )
    else:
        lines.append(
            "No pod CPU patch was applied. The base manifest values (request 250m, limit 500m) were used."
        )
    lines.append("")
    return lines


def criteria_section(cap: dict) -> list[str]:
    """Render the success criteria fixed before the step run."""
    return [
        "### Success criteria",
        "",
        "Fixed before the run and not changed afterwards.",
        "",
        "- p95 during overload is at least 3 times the p95 before the load step.",
        "- p95 after scale-out is at least 50% lower than the p95 during overload.",
        "",
        "Windows, all measured as the median of Locust per-second p95 values (a 10 s rolling window):",
        "",
        "- Before: from 10 s after the baseline load starts until the step.",
        "- Overload: from 10 s after the step until the first new replica is Ready (from the step itself when that leaves fewer than 5 samples).",
        "- After scale-out: from the first moment the Ready and total pod counts stay unchanged for 60 s, until the step ends.",
        "- Load off: from 10 s after the step ends until the run ends. The baseline load continues so that p95 stays measurable.",
        "",
        (
            f"Load: a constant baseline, one step to the calibrated 2-replica knee of {cap['step_offered_rps']} requests per second "
            f"({cap['step_users']} users), a hold until the HPA settles, then the baseline again. HPA target 50% CPU, minimum 2, maximum 6."
        ),
        "",
    ]


def step_section(step: dict | None, cap: dict) -> list[str]:
    """Render the step-profile scale-out section."""
    lines = ["## Scale-out, step profile", ""] + criteria_section(cap)
    if step is None:
        return lines + ["Result pending.", ""]
    load, w, c = step["load"], step["windows"], step["criteria"]
    c1, c2 = (
        c["overload_p95_at_least_3x_before"],
        c["after_scale_out_p95_at_least_50pct_lower"],
    )
    lines += [
        "### Result",
        "",
        (
            f"Baseline {load['base_rps']:.0f} requests per second ({load['base_users']} users) for {load['base_seconds']} s, "
            f"step to {load['step_rps']:.0f} requests per second ({load['step_users']} users) for {load['step_seconds']} s, "
            f"then the baseline again for {load['tail_seconds']} s. "
            f"The deployment started at {step['start_replicas']} replicas after {step['settle_wait_seconds']} s of settling "
            "(three consecutive CPU readings below the target)."
        ),
        "",
        "| Window | Seconds | Samples | Median rps | p95 ms (median) | p95 ms (max) |",
        "|---|---|---|---|---|---|",
    ]
    for name, label in (
        ("before", "Before the step"),
        ("overload", "Overload, before the first new replica is Ready"),
        ("after_scale_out", "After scale-out, replicas stable for 60 s"),
        ("load_off", "After the step ends"),
    ):
        x = w[name]
        lines.append(
            f"| {label} | {x['end'] - x['start']:.0f} | {x['rows']} | {fmt(x['rps'])} | {fmt(x['p95_ms'])} | {fmt(x['p95_max_ms'])} |"
        )
    met = lambda ok: "met" if ok else "missed"
    lines += [
        "",
        "| Criterion | Threshold | Measured | Outcome |",
        "|---|---|---|---|",
        f"| Overload p95 against before | at least {c1['threshold']}x | {fmt(c1['measured_ratio'], 'x')} | {met(c1['met'])} |",
        f"| After scale-out p95 against overload | at least {c2['threshold']:.0%} lower | {fmt(c2['measured_drop'])} (fraction lower) | {met(c2['met'])} |",
        "",
        "| Event | Seconds after the step |",
        "|---|---|",
        f"| First replica count increase seen | {fmt(step['first_scale_up_seconds_after_step'])} |",
        f"| First new replica Ready | {fmt(step['first_new_replica_ready_seconds_after_step'])} |",
        f"| Replica counts stable for 60 s from | {fmt(step['replicas_stable_seconds_after_step'])} |",
        f"| Peak replicas | {step['peak_replicas']} (max {step['max_replicas']}) |",
        f"| Back to {step['min_replicas']} replicas, seconds after the step ends | {fmt(step['scale_down_to_min_seconds_after_step_end'])} |",
        "",
        "Replica count over time (seconds relative to the step; the HPA current and desired replicas and the average CPU utilization it reported):",
        "",
        "| t s | Current | Desired | CPU % of request |",
        "|---|---|---|---|",
    ]
    for s in step["series"][::3]:
        lines.append(
            f"| {s['t']} | {s['current']} | {s['desired']} | {fmt(s['cpu_pct'])} |"
        )
    lines += [
        "",
        "Full series, per-pod CPU and the one-second Ready counts are in `reports/serving_results/hpa_step.json` and `raw/hpa_step/`.",
        "",
    ]
    return lines


def missed_list(step: dict | None, hpa: dict) -> list[str]:
    """List the targets that were not met."""
    out = []
    if step is not None:
        c = step["criteria"]
        if not c["overload_p95_at_least_3x_before"]["met"]:
            out.append(
                f"- Step profile: overload p95 was {c['overload_p95_at_least_3x_before']['measured_ratio']}x the pre-step p95, below the 3x criterion."
            )
        if not c["after_scale_out_p95_at_least_50pct_lower"]["met"]:
            out.append(
                f"- Step profile: p95 after scale-out was {c['after_scale_out_p95_at_least_50pct_lower']['measured_drop']} lower than during overload, below the 50% criterion."
            )
    p95 = hpa["p95_ms_by_phase"]
    if p95["hold_late"] is None or p95["hold_late"] > p95["before"]:
        out.append(
            f"- Moderate profile, p95 recovery: p95 was {p95['before']} ms before the ramp and {p95['hold_late']} ms in the last 120 s of the hold, after the replicas reached {hpa['peak_replicas']}. It did not return to the pre-ramp level."
        )
    return out or ["- None."]


def build() -> str:
    """Render the serving benchmark report from the result JSON files."""
    heal, roll, hpa = load("selfheal"), load("rollout"), load("hpa")
    stress, cap, step = load("hpa_stress"), load("capacity"), load("hpa_step")
    env = heal["environment"]
    ph = roll["phases"]
    p95 = hpa["p95_ms_by_phase"]
    sp95 = stress["p95_ms_by_phase"]
    lines = [
        "# Serving Benchmark",
        "",
        "Measured behavior of the scoring API on a local single-node kind cluster. Every number below is read from `reports/serving_results/*.json`.",
        "",
        "## Environment",
        "",
        f"- CPU: {env['cpu_model']} ({env['cpu_threads']} threads visible to WSL2)",
        f"- RAM visible to WSL2: {env['ram_gb']} GB",
        f"- Kernel: {env['kernel']}",
        f"- Cluster: {env['kind']}, one control-plane node, metrics-server with insecure kubelet TLS",
        "- Workload: 2 to 6 API replicas, one uvicorn worker each, LightGBM with `n_jobs=1`",
        "- Requests: 250m CPU, 256Mi memory. Limits: 500m CPU, 512Mi memory",
        "- Rolling update settings: maxUnavailable 0, maxSurge 1, a 10 s `preStop` sleep, 60 s termination grace period",
        "- Load generator: Locust, headless, on the same machine as the cluster",
        "",
        "## Results",
        "",
        "Targets are proposals fixed before the runs. Latency values are measurements, with no latency target.",
        "",
        "| Experiment | Measurement | Proposed target | Measured |",
        "|---|---|---|---|",
        f"| Self-heal, pod deleted | Replacement Ready | under 30 s | {fmt(heal['pod_delete']['replacement_ready_seconds'], ' s')} |",
        f"| Self-heal, `/tmp/healthy` removed | Restarts {heal['liveness_failure']['restarts_before']} to {heal['liveness_failure']['restarts_after']}, Ready again | under 30 s | {fmt(heal['liveness_failure']['ready_after_seconds'], ' s')} |",
        f"| Self-heal | Locust failures | error rate near 0 | {heal['locust']['failures']} of {heal['locust']['requests']} ({heal['locust']['error_rate']:.4%}) |",
        f"| Rolling update | Failed requests | 0 | {ph['rolling']['failures']} of {ph['rolling']['requests']} |",
        f"| Recreate (control) | Failed requests | failures expected | {ph['recreate']['failures']} of {ph['recreate']['requests']} |",
        f"| Rollout undo | Failed requests during failed rollout and undo | 0 | {ph['undo']['failures']} of {ph['undo']['requests']} |",
        f"| Rollout undo | Ready pods during the failed rollout | at least 1 | {roll['undo']['ready_pods_during_failed_rollout']} |",
        f"| Rollout undo | Image after undo | previous image | `{roll['undo']['image_after_undo']}` |",
    ]
    if step is not None:
        c = step["criteria"]
        c1, c2 = (
            c["overload_p95_at_least_3x_before"],
            c["after_scale_out_p95_at_least_50pct_lower"],
        )
        lines += [
            f"| Scale-out, step profile | Replicas rise above the minimum of {step['min_replicas']} | above minimum | peak {step['peak_replicas']} (max {step['max_replicas']}) |",
            f"| Scale-out, step profile | Overload p95 against before | at least 3x | {fmt(c1['measured_ratio'], 'x')} ({'met' if c1['met'] else 'missed'}) |",
            f"| Scale-out, step profile | p95 after scale-out against overload | at least 50% lower | {fmt(c2['measured_drop'])} lower ({'met' if c2['met'] else 'missed'}) |",
            f"| Scale-out, step profile | Return to minimum after the step ends | after the default scale-down delay | {fmt(step['scale_down_to_min_seconds_after_step_end'], ' s')} |",
        ]
    else:
        lines.append(
            "| Scale-out, step profile | See the step profile section | see criteria | pending |"
        )
    lines += [
        "",
        "### Latency",
        "",
        "Self-heal and rollout runs: constant 10 users with a think time of 0.05 to 0.15 s per user. Other runs are described in their sections.",
        "",
    ]
    lines += [
        "| Run | Requests | RPS | p50 ms | p95 ms | p99 ms |",
        "|---|---|---|---|---|---|",
    ]
    runs = [
        ("Self-heal", heal["locust"]),
        ("Rolling update", ph["rolling"]),
        ("Recreate", ph["recreate"]),
        ("Rollout undo", ph["undo"]),
        ("Scale-out, moderate profile, whole run", hpa["overall"]),
        ("Scale-out, stress run, whole run", stress["overall"]),
    ]
    for name, r in runs:
        lines.append(
            f"| {name} | {r['requests']} | {r['rps']} | {r['p50_ms']} | {r['p95_ms']} | {r['p99_ms']} |"
        )
    lines.append("")
    lines += capacity_section(cap)
    lines += step_section(step, cap)
    lines += [
        "## Scale-out, supporting runs",
        "",
        "### Moderate profile",
        "",
        (
            f"Think time {hpa['think_time_seconds'][0]} to {hpa['think_time_seconds'][1]} s per user, keep-alive sessions. Users ramp from {hpa['load']['users_from']} to {hpa['load']['users_to']} over {hpa['load']['ramp_seconds']} s, then hold for {hpa['load']['hold_seconds']} s. "
            f"The deployment started at {hpa['start_replicas']} replicas after {hpa['settle_wait_seconds']} s of settling. First replica increase {fmt(hpa['first_scale_up_seconds'], ' s')} after the ramp start, peak {hpa['peak_replicas']} replicas, back to the minimum {fmt(hpa['scale_down_to_min_seconds_after_load'], ' s')} after load ended. Each p95 is the median of the per-interval p95 in that window."
        ),
        "",
        "| Phase | Seconds from start | p95 ms |",
        "|---|---|---|",
        f"| Before ramp | 0 to 60 | {fmt(p95['before'])} |",
        f"| Ramp | 60 to 180 | {fmt(p95['ramp'])} |",
        f"| Hold, early | 180 to 300 | {fmt(p95['hold_early'])} |",
        f"| Hold, late | 300 to 420 | {fmt(p95['hold_late'])} |",
        "",
        "Data: `reports/serving_results/hpa.json`.",
        "",
        "### Stress run",
        "",
        (
            f"Think time 0.05 to 0.15 s per user, keep-alive sessions, the same 10 to 200 user ramp. Whole-run average load was {stress['overall']['rps']} requests per second ({stress['overall']['requests']} requests, {stress['overall']['failures']} failures). Replicas reached {stress['peak_replicas']}. "
            f"p95 was {sp95['before']} ms before the ramp, {sp95['ramp']} ms during the ramp, and {sp95['hold_early']} ms and {sp95['hold_late']} ms in the two hold windows, so p95 did not recover. The single machine shared with the load generator was the limit. Data: `reports/serving_results/hpa_stress.json`."
        ),
        "",
        "## Targets missed",
        "",
        *missed_list(step, hpa),
        "",
        "## Limits",
        "",
        "- The load generator and the cluster share one machine and one CPU budget. Locust competes with the API pods, the kind node, and metrics-server for the same cores.",
        "- Single-node kind demonstrates mechanisms (probes, restarts, rolling updates, autoscaling). The numbers do not describe production capacity.",
        "- During the self-heal and rollout runs the HPA is removed so the replica count stays at 2. It is applied again for the scale-out runs.",
        "- The step profile and the calibration use a new connection per request. The moderate and stress runs use keep-alive sessions, so their connections stay with the pods that existed when each user started.",
        "- Calibration steps last 20 s and the p95 values are noisy near the knee. The knee is a single measured rate, not a confidence interval.",
        "- Each run is a single execution. No repeat or confidence interval is reported.",
        "- Request payloads are rows from `data/sample/sample_features.csv`, so the score distribution is not production traffic.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    REPORT.write_text(build())
    print(f"wrote {REPORT}")
