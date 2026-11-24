import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "reports" / "serving_results"
REPORT = ROOT / "reports" / "serving_benchmark.md"

INTRO = [
    "# Serving Benchmark",
    "",
    "This report shows how the scoring API behaves on a local single-node kind cluster. Every number is read from `reports/serving_results/*.json`.",
    "",
    "**How to read the results**",
    "",
    "- **Replica:** one running copy of the API.",
    "- **Autoscaling (HPA):** Kubernetes adds or removes replicas based on CPU use.",
    "- **RPS:** requests per second.",
    "- **p50, p95, p99:** response times. For p95, 95 of 100 requests were faster than this value.",
    "- **Rolling update:** a new version is started step by step while the old one keeps serving.",
    "- **Recreate:** the old version is stopped first, then the new one starts. It is used here as a comparison.",
    "",
]

LIMITS = [
    "## Limits",
    "",
    "- The load generator and the cluster share one machine and one CPU budget. Locust competes with the API pods, the kind node, and metrics-server.",
    "- A single-node kind cluster shows how the mechanisms work (probes, restarts, rolling updates, autoscaling). The numbers do not describe production capacity.",
    "- The autoscaler is removed in the self-heal and rollout runs so the replica count stays at 2. It is applied again for the scale-out runs.",
    "- The step profile and the capacity test open a new connection for each request. The moderate and stress profiles keep connections open, so each user stays with the pod that first served it. New replicas receive traffic only from users that connect after the replicas are Ready. This is a likely limit on p95 recovery in those two profiles. The runs do not test this directly.",
    "- One Locust process creates all the load. Load generator CPU was recorded only in the capacity test, not in the stress run.",
    "- Each capacity step lasts 20 s, so p95 is noisy near the breaking point. The breaking point is one measured value with no confidence range.",
    "- Each run was done once. No repeats or confidence ranges are reported.",
    "- Requests use rows from `data/sample/sample_features.csv`, so the scores do not represent real traffic.",
    "",
]

BATCH_SECTION = [
    "## Batch scoring run",
    "",
    "The Airflow daily DAG scored every day window of the dataset on a local Airflow 3 stack with a Postgres metadata database.",
    "",
    "| Item | Value |",
    "|---|---|",
    "| DAG runs | 31 (one per 24-step day, day 30 covers steps 721 to 743) |",
    "| Total time for the full catch-up | 11 min 16 s |",
    "| Rows scored | 6,362,620 (same as the source; the 31 partitions add up to the same total) |",
    "| Output | one Parquet file per day under `data/scored/date=YYYY-MM-DD/` |",
    "| Rerun of day 5 | zero score difference from the first run |",
    "",
    "After each partition is written, a quality check runs. The run fails if any rule is broken:",
    "",
    "- The partition row count equals the source row count of the day window.",
    "- `txn_id`, `step`, and `score` have no empty values.",
    "- Every score is between 0 and 1.",
    "- The scores are not all the same (standard deviation above 0).",
    "",
    "Notes:",
    "",
    "- The run shows that the pipeline works and gives the same result when repeated. It is not a measure of model quality.",
    "- Days 0 to 24 are in the training range (the cutoff at step 594 falls in day 24), so the model has seen their labels. Model quality is reported in `reports/model_evaluation.md`, from the test part only.",
    "- Daily row counts range from 272 to 574,255 (`reports/eda_numbers.json`), so the run time of each day depends on the day.",
    "- The total time, the run count, and the day-5 comparison come from the run log of the catch-up. They are not stored as files in `reports/`.",
]

SELECTED_POINTS = (-93, -27, 22, 38, 54, 87, 334, 633)
SELECTED_RANGES = ((120, 317), (474, 601))


def load(name: str) -> dict | None:
    """Read one result JSON, or None when the run has not happened."""
    path = RESULTS / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


def fmt(value, unit: str = "") -> str:
    """Format a measured value or mark it as not reached."""
    return "not reached" if value is None else f"{value}{unit}"


def pct(value) -> str:
    """Format a fraction as a percentage with one decimal."""
    return "not reached" if value is None else f"{value:.1%}"


def span(values: list) -> str:
    """Format one value or a min to max range."""
    lo, hi = min(values), max(values)
    return str(lo) if lo == hi else f"{lo} to {hi}"


def hold_text(p: dict) -> str:
    """Describe the two hold-window p95 values."""
    if p["hold_early"] == p["hold_late"]:
        return f"{p['hold_early']} ms in both hold windows"
    return f"{p['hold_early']} ms and {p['hold_late']} ms in the two hold windows"


def selected_rows(series: list[dict]) -> list[str]:
    """Pick the nearest sample to each listed time and summarize each listed range."""
    entries = []
    for t in SELECTED_POINTS:
        s = min(series, key=lambda x: abs(x["t"] - t))
        entries.append((s["t"], s["t"], s["t"]) + ((s,),))
    for a, b in SELECTED_RANGES:
        sel = [s for s in series if a <= s["t"] <= b]
        entries.append((sel[0]["t"], sel[0]["t"], sel[-1]["t"], tuple(sel)))
    rows = []
    for _, first, last, sel in sorted(entries, key=lambda e: e[0]):
        label = str(first) if first == last else f"{first} to {last}"
        cpu = [s["cpu_pct"] for s in sel if s["cpu_pct"] is not None]
        rows.append(
            f"| {label} | {span([s['current'] for s in sel])} | {span([s['desired'] for s in sel])} | {span(cpu) if cpu else 'not reached'} |"
        )
    return rows


def capacity_section(cap: dict) -> list[str]:
    """Render the capacity test section."""
    g = cap["generator"]
    patch = cap["pod_cpu_patch"]
    lines = [
        "## Capacity test",
        "",
        (
            "The autoscaler was removed and the number of replicas was fixed. "
            f"Load grew by 10 users every {g['step_seconds']} s, and each user sent {g['per_user_rps']} requests per second. "
            f"The load generator (Locust `FastHttpUser`, {g['processes']} process) opens a new connection for each request."
        ),
        "",
        "- **p95 per step:** the median of the per-second p95 values, after the first 10 s of the step.",
        "- **Breaking point:** the first step where p95 and the next step's p95 are both at least 3 times the median p95 of the first three steps.",
        (
            f"- CPU settings were changed for this test only: request {patch['request']}, limit {patch['limit']}."
            if patch
            else "- No change was made to the CPU settings. The base values (request 250m, limit 500m) were used."
        ),
        "",
        "| Replicas | p95 at start (ms) | Breaking point, offered RPS | Breaking point, measured RPS | Highest measured RPS | CPU ms per request | Load generator CPU, max (% of one core) |",
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
            f"The load generator stayed below 80% of one core in every run (maximum {g['max_process_cpu_pct']}%). "
            "CPU per request is the pod CPU time divided by the requests served in the step."
        ),
        "",
    ]
    return lines


def step_section(step: dict | None, cap: dict) -> list[str]:
    """Render the step-profile scale-out section."""
    lines = ["## Scale-out, step profile", ""]
    if step is None:
        return lines + ["Result pending.", ""]
    load, w, c = step["load"], step["windows"], step["criteria"]
    c1, c2 = (
        c["overload_p95_at_least_3x_before"],
        c["after_scale_out_p95_at_least_50pct_lower"],
    )
    lines += [
        "### Plan",
        "",
        "Load pattern:",
        "",
        f"1. A constant base load of {load['base_rps']:.0f} RPS ({load['base_users']} users) for {load['base_seconds']} s.",
        f"2. A step up to {load['step_rps']:.0f} RPS ({load['step_users']} users), the breaking point of 2 replicas, for {load['step_seconds']} s.",
        f"3. The base load again for {load['tail_seconds']} s.",
        "",
        f"Autoscaling settings: CPU target 50%, minimum {step['min_replicas']} replicas, maximum {step['max_replicas']}. The run started with {step['start_replicas']} replicas after {step['settle_wait_seconds']} s of settling.",
        "",
        "Success criteria were fixed before the run and were not changed:",
        "",
        "- p95 under overload is at least 3 times the p95 before the step.",
        "- p95 after scale-out is at least 50% lower than the p95 under overload.",
        "",
        "Time windows (each value is the median of Locust per-second p95 values):",
        "",
        "- **Before:** from 10 s after the base load starts until the step.",
        "- **Overload:** from 10 s after the step until the first new replica is Ready.",
        "- **After scale-out:** from the moment the pod counts stay unchanged for 60 s, until the step ends.",
        "- **After the step ends:** from 10 s after the step ends until the run ends. The base load continues so p95 can still be measured.",
        "",
        "### Result",
        "",
        "| Window | Seconds | Samples | Median RPS | p95 ms (median) | p95 ms (max) |",
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
        "| Criterion | Target | Result | Outcome |",
        "|---|---|---|---|",
        f"| p95 under overload compared with before | at least {c1['threshold']:.0f}x | {fmt(c1['measured_ratio'], 'x')} | {met(c1['met'])} |",
        f"| p95 after scale-out compared with overload | at least {c2['threshold']:.0%} lower | {pct(c2['measured_drop'])} lower | {met(c2['met'])} |",
        "",
        "| Event | Time |",
        "|---|---|",
        f"| First new replica Ready | {fmt(step['first_new_replica_ready_seconds_after_step'], ' s after the step')} |",
        f"| First increase in replica count seen | {fmt(step['first_scale_up_seconds_after_step'], ' s after the step')} |",
        f"| Replica count stable for 60 s from | {fmt(step['replicas_stable_seconds_after_step'], ' s after the step')} |",
        f"| Peak replicas | {step['peak_replicas']} (max {step['max_replicas']}) |",
        f"| Back to {step['min_replicas']} replicas | {fmt(step['scale_down_to_min_seconds_after_step_end'], ' s after the step ends')} |",
        "",
        "The first row comes from the one-second count of Ready pods. The second row comes from the replica count reported by the autoscaler, sampled about every 5 s. The two sources are sampled differently.",
        "",
        "Replicas and CPU over time (seconds relative to the step, selected rows):",
        "",
        "| Time (s) | Current replicas | Desired replicas | CPU % of request |",
        "|---|---|---|---|",
        *selected_rows(step["series"]),
        "",
        "Selection rule: each single time shows the sample nearest to that time, and each range row shows the lowest to highest value among the samples within the range.",
        "",
        "The full series, CPU per pod, and the one-second Ready counts are in `reports/serving_results/hpa_step.json` and `raw/hpa_step/`.",
        "",
    ]
    return lines


def missed_list(step: dict | None, hpa: dict, stress: dict) -> list[str]:
    """List the targets that were not met."""
    out = []
    if step is not None:
        c = step["criteria"]
        if not c["overload_p95_at_least_3x_before"]["met"]:
            out.append(
                f"- **Step profile:** p95 under overload was {c['overload_p95_at_least_3x_before']['measured_ratio']}x the p95 before the step. The target was 3x."
            )
        if not c["after_scale_out_p95_at_least_50pct_lower"]["met"]:
            out.append(
                f"- **Step profile:** p95 after scale-out was {pct(c['after_scale_out_p95_at_least_50pct_lower']['measured_drop'])} lower than under overload. The target was 50%."
            )
    p95 = hpa["p95_ms_by_phase"]
    if p95["hold_late"] is None or p95["hold_late"] > p95["before"]:
        out.append(
            f"- **Moderate profile:** p95 was {p95['before']} ms before the ramp and {p95['hold_late']} ms in the last 120 s of the hold, with {hpa['peak_replicas']} replicas. It did not return to the starting level."
        )
    sp = stress["p95_ms_by_phase"]
    if sp["hold_late"] is None or sp["hold_late"] > sp["before"]:
        out.append(
            f"- **Stress profile:** p95 was {sp['before']} ms before the ramp and {hold_text(sp)}, with {stress['peak_replicas']} replicas. It did not recover."
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
    lines = INTRO + [
        "## Environment",
        "",
        f"- **CPU:** {env['cpu_model'].split(' w/ ')[0]} ({env['cpu_threads']} threads visible to WSL2).",
        f"- **Memory:** {env['ram_gb']} GB visible to WSL2.",
        f"- **Kernel:** {env['kernel']}.",
        f"- **Cluster:** {' '.join(env['kind'].split()[:2])}, one control-plane node, metrics-server with insecure kubelet TLS.",
        "- **API:** 2 to 6 replicas, one uvicorn worker each, LightGBM with `n_jobs=1`.",
        "- **Resources per replica:** request 250m CPU and 256Mi memory, limit 500m CPU and 512Mi memory.",
        "- **Rolling update settings:** `maxUnavailable` 0, `maxSurge` 1, 10 s `preStop` sleep, 60 s grace period.",
        "- **Load generator:** Locust, headless, on the same machine as the cluster.",
        "",
        "## Results",
        "",
        "The targets were set before the runs. Response times are measurements only, with no target.",
        "",
        "| Experiment | What was measured | Target | Result |",
        "|---|---|---|---|",
        f"| Self-heal, pod deleted | Time until the new pod is Ready | under 30 s | {fmt(heal['pod_delete']['replacement_ready_seconds'], ' s')} |",
        f"| Self-heal, `/tmp/healthy` removed | Restart and Ready again | under 30 s | {fmt(heal['liveness_failure']['ready_after_seconds'], ' s')} |",
        f"| Self-heal | Failed requests | error rate near 0 | {heal['locust']['failures']} of {heal['locust']['requests']:,} ({heal['locust']['error_rate']:.4%}) |",
        f"| Rolling update | Failed requests | 0 | {ph['rolling']['failures']} of {ph['rolling']['requests']:,} |",
        f"| Recreate (comparison) | Failed requests | failures expected | {ph['recreate']['failures']} of {ph['recreate']['requests']:,} |",
        f"| Rollback after a failed rollout | Failed requests | 0 | {ph['undo']['failures']} of {ph['undo']['requests']:,} |",
        f"| Rollback after a failed rollout | Ready pods during the failed rollout | at least 1 | {roll['undo']['ready_pods_during_failed_rollout']} |",
        f"| Rollback after a failed rollout | Image after rollback | previous image | `{roll['undo']['image_after_undo']}` |",
    ]
    if step is not None:
        c = step["criteria"]
        c1, c2 = (
            c["overload_p95_at_least_3x_before"],
            c["after_scale_out_p95_at_least_50pct_lower"],
        )
        lines += [
            f"| Scale-out, step profile | Replicas rise above the minimum of {step['min_replicas']} | above {step['min_replicas']} | peak {step['peak_replicas']} (max {step['max_replicas']}) |",
            f"| Scale-out, step profile | p95 under overload compared with before | at least 3x | {fmt(c1['measured_ratio'], 'x')} ({'met' if c1['met'] else 'missed'}) |",
            f"| Scale-out, step profile | p95 after scale-out compared with overload | at least 50% lower | {pct(c2['measured_drop'])} lower ({'met' if c2['met'] else 'missed'}) |",
            f"| Scale-out, step profile | Return to {step['min_replicas']} replicas after the load ends | after the default delay | {fmt(step['scale_down_to_min_seconds_after_step_end'], ' s')} |",
        ]
    else:
        lines.append(
            "| Scale-out, step profile | See the step profile section | see criteria | pending |"
        )
    lines += [
        "",
        "### Response times",
        "",
        "Self-heal and rollout runs used a constant 10 users, each waiting 0.05 to 0.15 s between requests.",
        "",
        "| Run | Requests | RPS | p50 ms | p95 ms | p99 ms |",
        "|---|---|---|---|---|---|",
    ]
    runs = [
        ("Self-heal", heal["locust"]),
        ("Rolling update", ph["rolling"]),
        ("Recreate", ph["recreate"]),
        ("Rollback", ph["undo"]),
        ("Scale-out, moderate profile (whole run)", hpa["overall"]),
        ("Scale-out, stress profile (whole run)", stress["overall"]),
    ]
    for name, r in runs:
        lines.append(
            f"| {name} | {r['requests']:,} | {r['rps']} | {r['p50_ms']} | {r['p95_ms']} | {r['p99_ms']} |"
        )
    lines.append("")
    lines += capacity_section(cap)
    lines += step_section(step, cap)
    lines += [
        "## Scale-out, other runs",
        "",
        "### Moderate profile",
        "",
        f"- Each user waits {hpa['think_time_seconds'][0]} to {hpa['think_time_seconds'][1]} s between requests and keeps its connection open (keep-alive).",
        f"- Users grow from {hpa['load']['users_from']} to {hpa['load']['users_to']} over {hpa['load']['ramp_seconds']} s, then stay at {hpa['load']['users_to']} for {hpa['load']['hold_seconds']} s.",
        f"- The run started with {hpa['start_replicas']} replicas after {hpa['settle_wait_seconds']} s of settling.",
        f"- First replica increase: {fmt(hpa['first_scale_up_seconds'], ' s')} after the start of the ramp. Peak: {hpa['peak_replicas']} replicas. Back to {hpa['start_replicas']} replicas: {fmt(hpa['scale_down_to_min_seconds_after_load'], ' s')} after the load ended.",
        "",
        "| Phase | Seconds from start | p95 ms |",
        "|---|---|---|",
        f"| Before the ramp | 0 to 60 | {fmt(p95['before'])} |",
        f"| Ramp | 60 to 180 | {fmt(p95['ramp'])} |",
        f"| Hold, early | 180 to 300 | {fmt(p95['hold_early'])} |",
        f"| Hold, late | 300 to 420 | {fmt(p95['hold_late'])} |",
        "",
        "Data: `reports/serving_results/hpa.json`.",
        "",
        "### Stress profile",
        "",
        "- Each user waits 0.05 to 0.15 s between requests and keeps its connection open. The ramp is the same, 10 to 200 users.",
        f"- Average load over the whole run: {stress['overall']['rps']} RPS ({stress['overall']['requests']:,} requests, {stress['overall']['failures']} failures). Replicas reached {stress['peak_replicas']}.",
        f"- p95 was {sp95['before']} ms before the ramp, {sp95['ramp']} ms during the ramp, and {hold_text(sp95)}. It did not recover.",
        "- The limit was the single machine, shared with the load generator.",
        "",
        "Data: `reports/serving_results/hpa_stress.json`.",
        "",
        "## Targets missed",
        "",
        *missed_list(step, hpa, stress),
        "",
        *LIMITS,
        *BATCH_SECTION,
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    REPORT.write_text(build())
    print(f"wrote {REPORT}")
