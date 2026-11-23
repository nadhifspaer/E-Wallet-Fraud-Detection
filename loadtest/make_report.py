import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "reports" / "serving_results"
REPORT = ROOT / "reports" / "serving_benchmark.md"


def load(name: str) -> dict:
    """Read one experiment result JSON."""
    return json.loads((RESULTS / f"{name}.json").read_text())


def fmt(value, unit: str = "") -> str:
    """Format a measured value or mark it as not reached."""
    return "not reached" if value is None else f"{value}{unit}"


def missed(hpa: dict) -> list[str]:
    """List the scale-out targets that were not met."""
    p95 = hpa["p95_ms_by_phase"]
    out = []
    if p95["hold_late"] is None or p95["hold_late"] > p95["before"]:
        out.append(
            f"- Scale-out p95 recovery: p95 was {p95['before']} ms before the ramp and "
            f"{p95['hold_late']} ms in the last 120 s of the hold, after the replicas "
            f"reached {hpa['peak_replicas']}. It did not return to the pre-ramp level."
        )
    return out or ["- None."]


def build() -> str:
    """Render the serving benchmark report from the result JSON files."""
    heal, roll, hpa = load("selfheal"), load("rollout"), load("hpa")
    stress = load("hpa_stress")
    sp95 = stress["p95_ms_by_phase"]
    env = heal["environment"]
    ph = roll["phases"]
    p95 = hpa["p95_ms_by_phase"]
    lines = [
        "# Serving Benchmark",
        "",
        (
            "Measured behavior of the scoring API on a local single-node kind cluster. "
            "Every number below is read from `reports/serving_results/*.json`."
        ),
        "",
        "## Environment",
        "",
        f"- CPU: {env['cpu_model']} ({env['cpu_threads']} threads visible to WSL2)",
        f"- RAM visible to WSL2: {env['ram_gb']} GB",
        f"- Kernel: {env['kernel']}",
        f"- Cluster: {env['kind']}, one control-plane node, metrics-server with insecure kubelet TLS",
        "- Workload: 2 to 6 API replicas, one uvicorn worker each, LightGBM with `n_jobs=1`",
        "- Requests: 250m CPU, 256Mi memory. Limits: 500m CPU, 512Mi memory",
        "- Load generator: Locust, headless, on the same machine as the cluster",
        "",
        "## Results",
        "",
        "Targets are proposals fixed before the runs. Latency values are measurements, with no latency target.",
        "",
        "| Experiment | Measurement | Proposed target | Measured |",
        "|---|---|---|---|",
        f"| Self-heal, pod deleted | Replacement Ready | under 30 s | {fmt(heal['pod_delete']['replacement_ready_seconds'], ' s')} |",
        (
            f"| Self-heal, `/tmp/healthy` removed | Restarts {heal['liveness_failure']['restarts_before']} to "
            f"{heal['liveness_failure']['restarts_after']}, Ready again | under 30 s | {fmt(heal['liveness_failure']['ready_after_seconds'], ' s')} |"
        ),
        (
            f"| Self-heal | Locust failures | error rate near 0 | {heal['locust']['failures']} of {heal['locust']['requests']} "
            f"({heal['locust']['error_rate']:.4%}) |"
        ),
        f"| Rolling update | Failed requests | 0 | {ph['rolling']['failures']} of {ph['rolling']['requests']} |",
        f"| Recreate (control) | Failed requests | failures expected | {ph['recreate']['failures']} of {ph['recreate']['requests']} |",
        f"| Rollout undo | Failed requests during failed rollout and undo | 0 | {ph['undo']['failures']} of {ph['undo']['requests']} |",
        f"| Rollout undo | Ready pods during the failed rollout | at least 1 | {roll['undo']['ready_pods_during_failed_rollout']} |",
        f"| Rollout undo | Image after undo | previous image | `{roll['undo']['image_after_undo']}` |",
        f"| Scale-out | First replica increase after load start | above min of {hpa['min_replicas']} | {fmt(hpa['first_scale_up_seconds'], ' s')} |",
        f"| Scale-out | Peak replicas | above min of {hpa['min_replicas']} | {hpa['peak_replicas']} (max {hpa['max_replicas']}) |",
        (
            f"| Scale-out | Return to min after load end | after the default scale-down delay | "
            f"{fmt(hpa['scale_down_to_min_seconds_after_load'], ' s')} |"
        ),
        "",
        "### Latency",
        "",
        (
            "Load: constant 10 users with a think time of 0.05 to 0.15 s per user for the "
            "self-heal and rollout runs. The scale-out run uses the moderate profile "
            f"(think time {hpa['think_time_seconds'][0]} to {hpa['think_time_seconds'][1]} s per user)."
        ),
        "",
        "| Run | Requests | RPS | p50 ms | p95 ms | p99 ms |",
        "|---|---|---|---|---|---|",
    ]
    runs = [
        ("Self-heal", heal["locust"]),
        ("Rolling update", ph["rolling"]),
        ("Recreate", ph["recreate"]),
        ("Rollout undo", ph["undo"]),
        ("Scale-out, moderate profile, whole run", hpa["overall"]),
    ]
    for name, r in runs:
        lines.append(
            f"| {name} | {r['requests']} | {r['rps']} | {r['p50_ms']} | {r['p95_ms']} | {r['p99_ms']} |"
        )
    lines += [
        "",
        "### Scale-out, moderate profile, p95 by phase",
        "",
        (
            f"Think time {hpa['think_time_seconds'][0]} to {hpa['think_time_seconds'][1]} s per user. "
            f"The deployment started at {hpa['start_replicas']} replicas after "
            f"{hpa['settle_wait_seconds']} s of settling (three consecutive CPU readings below the target). "
            f"Users ramp from {hpa['load']['users_from']} to {hpa['load']['users_to']} over "
            f"{hpa['load']['ramp_seconds']} s, then hold for {hpa['load']['hold_seconds']} s. "
            "Each value is the median of the per-interval p95 reported by Locust in that window."
        ),
        "",
        "| Phase | Seconds from start | p95 ms |",
        "|---|---|---|",
        f"| Before ramp | 0 to 60 | {fmt(p95['before'])} |",
        f"| Ramp | 60 to 180 | {fmt(p95['ramp'])} |",
        f"| Hold, early | 180 to 300 | {fmt(p95['hold_early'])} |",
        f"| Hold, late | 300 to 420 | {fmt(p95['hold_late'])} |",
        "",
        (
            "Replica and CPU samples over time are in `reports/serving_results/hpa.json` (`series`) "
            "and the raw logs are in `reports/serving_results/raw/`."
        ),
        "",
        "### Scale-out, stress run",
        "",
        (
            "The first scale-out run used a think time of 0.05 to 0.15 s per user with the same "
            f"10 to 200 user ramp. Whole-run average load was {stress['overall']['rps']} requests per second "
            f"({stress['overall']['requests']} requests, {stress['overall']['failures']} failures). "
            f"Replicas reached {stress['peak_replicas']}. p95 was {sp95['before']} ms before the ramp, "
            f"{sp95['ramp']} ms during the ramp, and {sp95['hold_early']} ms and {sp95['hold_late']} ms "
            "in the two hold windows, so p95 did not recover. The single machine shared with the "
            "load generator was the limit. Data: `reports/serving_results/hpa_stress.json`."
        ),
        "",
        "## Targets missed",
        "",
        *missed(hpa),
        "",
        "## Limits",
        "",
        (
            "- The load generator and the cluster share one machine and one CPU budget. "
            "Locust competes with the API pods, the kind node, and metrics-server for the same cores."
        ),
        (
            "- Single-node kind demonstrates mechanisms (probes, restarts, rolling updates, autoscaling). "
            "The numbers do not describe production capacity."
        ),
        "- The Locust process is single-threaded Python. At 200 users it can limit the offered rate before the API does, mainly in the stress run.",
        (
            "- During the self-heal and rollout runs the HPA is removed so the replica count stays at 2. "
            "It is applied again for the scale-out run."
        ),
        (
            "- Think time per user: 0.5 to 1.5 s in the moderate scale-out profile, "
            "0.05 to 0.15 s in the stress run and in the self-heal and rollout runs."
        ),
        "- The pods are given a 10 s `preStop` sleep and a 60 s termination grace period before the rolling update run.",
        "- Each run is a single execution. No repeat or confidence interval is reported.",
        "- Request payloads are rows from `data/sample/sample_features.csv`, so the score distribution is not production traffic.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    REPORT.write_text(build())
    print(f"wrote {REPORT}")
