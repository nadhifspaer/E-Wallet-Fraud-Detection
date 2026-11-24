import csv
import json
import os
import statistics
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "serving_results"
RAW = OUT / "raw" / "capacity"
CTX = "kind-fraud-detection-tabular"
NS = "fraud"
HOST = "http://127.0.0.1:30080"
LOCUST = ROOT / ".venv-loadtest" / "bin" / "locust"
PER_USER_RPS = float(os.environ.get("PER_USER_RPS", "2"))
STEP_SECONDS = int(os.environ.get("STEP_SECONDS", "20"))
SKIP_ROWS = 10
CLK = os.sysconf("SC_CLK_TCK")
POD_CPU_REQUEST = os.environ.get("POD_CPU_REQUEST", "")
POD_CPU_LIMIT = os.environ.get("POD_CPU_LIMIT", "")


def kn(*args: str) -> str:
    """Run kubectl in the project namespace and return stdout."""
    cmd = ["kubectl", "--context", CTX, "-n", NS, *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout


def pods() -> list[str]:
    """Return the names of non-terminating API pods."""
    out = kn(
        "get",
        "pods",
        "-l",
        "app=fraud-api",
        "-o",
        'jsonpath={range .items[*]}{.metadata.name}{" "}{.metadata.deletionTimestamp}{"\\n"}{end}',
    )
    return [ln.split()[0] for ln in out.splitlines() if len(ln.split()) == 1]


def ready_pods() -> int:
    """Count Ready API pods."""
    out = kn(
        "get",
        "pods",
        "-l",
        "app=fraud-api",
        "-o",
        'jsonpath={range .items[*]}{.status.conditions[?(@.type=="Ready")].status}{"\\n"}{end}',
    )
    return out.split().count("True")


def prepare(replicas: int) -> None:
    """Remove the HPA, restore the manifest, patch CPU if asked, and set replicas."""
    kn("delete", "hpa", "fraud-api", "--ignore-not-found")
    kn("apply", "-f", str(ROOT / "k8s" / "deployment.yaml"))
    if POD_CPU_REQUEST and POD_CPU_LIMIT:
        patch = [
            {
                "op": "replace",
                "path": "/spec/template/spec/containers/0/resources/requests/cpu",
                "value": POD_CPU_REQUEST,
            },
            {
                "op": "replace",
                "path": "/spec/template/spec/containers/0/resources/limits/cpu",
                "value": POD_CPU_LIMIT,
            },
        ]
        kn("patch", "deployment", "fraud-api", "--type=json", "-p", json.dumps(patch))
    kn("scale", "deployment", "fraud-api", f"--replicas={replicas}")
    kn("rollout", "status", "deployment/fraud-api", "--timeout=180s")
    for _ in range(120):
        if len(pods()) == replicas and ready_pods() == replicas:
            break
        time.sleep(1)
    time.sleep(10)


def cgroup_usec(pod: str) -> int | None:
    """Read cumulative CPU time of a pod container in microseconds."""
    out = kn("exec", pod, "--", "cat", "/sys/fs/cgroup/cpu.stat")
    for line in out.splitlines():
        if line.startswith("usage_usec"):
            return int(line.split()[1])
    return None


def descendants(root_pid: int) -> dict[int, int]:
    """Return CPU ticks of a process and its descendants."""
    table = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            raw = Path(f"/proc/{entry}/stat").read_text()
        except OSError:
            continue
        fields = raw[raw.rindex(")") + 2 :].split()
        table[int(entry)] = (int(fields[1]), int(fields[11]) + int(fields[12]))
    keep, frontier = {root_pid}, [root_pid]
    while frontier:
        cur = frontier.pop()
        for pid, (ppid, _) in table.items():
            if ppid == cur and pid not in keep:
                keep.add(pid)
                frontier.append(pid)
    return {pid: table[pid][1] for pid in keep if pid in table}


def run_config(replicas: int, users_max: int, processes: int) -> dict:
    """Step the load against a fixed replica count and summarize each step."""
    prepare(replicas)
    names = pods()
    prefix = str(RAW / f"r{replicas}")
    env = {
        **os.environ,
        "PER_USER_RPS": str(PER_USER_RPS),
        "USERS_MAX": str(users_max),
        "STEP_SECONDS": str(STEP_SECONDS),
    }
    cmd = [
        str(LOCUST), "-f", f"{ROOT}/loadtest/locustfile_fast.py,{ROOT}/loadtest/calib_shape.py",
        "--headless", "--host", HOST, "--csv", prefix, "--csv-full-history", "--only-summary",
    ]  # fmt: skip
    if processes > 1:
        cmd += ["--processes", str(processes)]
    cmd.append("FastScoringUser")
    samples = []
    with open(prefix + ".log", "w") as log:
        proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=log)
        while proc.poll() is None:
            ts = time.time()
            samples.append(
                {
                    "ts": ts,
                    "usec": {p: cgroup_usec(p) for p in names},
                    "ticks": descendants(proc.pid),
                }
            )
            time.sleep(max(0.0, 5 - (time.time() - ts)))
    return summarize(prefix, samples, replicas)


def summarize(prefix: str, samples: list[dict], replicas: int) -> dict:
    """Combine Locust history with cgroup and process samples per step."""
    with open(prefix + "_stats_history.csv", newline="") as f:
        rows = [
            r
            for r in csv.DictReader(f)
            if r["Name"] == "Aggregated" and int(r["User Count"]) > 0
        ]
    steps, group = [], []
    for r in rows:
        if group and r["User Count"] != group[-1]["User Count"]:
            steps.append(group)
            group = []
        group.append(r)
    steps.append(group)
    out = []
    for g in steps:
        used = g[SKIP_ROWS:] if len(g) > SKIP_ROWS + 3 else g
        p95 = [float(r["95%"]) for r in used if r["95%"] not in ("", "N/A")]
        ta, tb = float(used[0]["Timestamp"]), float(used[-1]["Timestamp"])
        inside = [s for s in samples if ta <= s["ts"] <= tb]
        cpu_cores = cpu_ms_req = share = gen = None
        if len(inside) >= 2:
            a, b = inside[0], inside[-1]
            dt = b["ts"] - a["ts"]
            deltas = {
                p: b["usec"][p] - a["usec"][p]
                for p in a["usec"]
                if a["usec"][p] is not None and b["usec"].get(p) is not None
            }
            total = sum(deltas.values())
            req = int(used[-1]["Total Request Count"]) - int(
                used[0]["Total Request Count"]
            )
            cpu_cores = round(total / 1e6 / dt, 3)
            cpu_ms_req = round(total / 1000 / req, 3) if req > 0 else None
            share = (
                round(min(deltas.values()) / total, 3)
                if total and len(deltas) > 1
                else None
            )
            gen = round(
                max(
                    (b["ticks"].get(p, 0) - a["ticks"].get(p, 0)) / CLK / dt * 100
                    for p in b["ticks"]
                ),
                1,
            )
        out.append(
            {
                "users": int(g[0]["User Count"]),
                "offered_rps": int(g[0]["User Count"]) * PER_USER_RPS,
                "rps": round(
                    statistics.median(float(r["Requests/s"]) for r in used), 1
                ),
                "p95_ms": statistics.median(p95) if p95 else None,
                "failures": int(used[-1]["Total Failure Count"])
                - int(used[0]["Total Failure Count"]),
                "pod_cpu_cores": cpu_cores,
                "cpu_ms_per_request": cpu_ms_req,
                "min_pod_cpu_share": share,
                "locust_cpu_max_pct": gen,
            }
        )
    base = statistics.median(s["p95_ms"] for s in out[:3] if s["p95_ms"] is not None)
    knee = next(
        (
            i
            for i in range(len(out) - 1)
            if out[i]["p95_ms"]
            and out[i + 1]["p95_ms"]
            and out[i]["p95_ms"] >= 3 * base
            and out[i + 1]["p95_ms"] >= 3 * base
        ),
        None,
    )
    calm = [
        s["cpu_ms_per_request"]
        for s in out
        if s["cpu_ms_per_request"]
        and s["p95_ms"]
        and s["p95_ms"] < 2 * base
        and s["rps"] > 10
    ]
    gens = [s["locust_cpu_max_pct"] for s in out if s["locust_cpu_max_pct"] is not None]
    return {
        "replicas": replicas,
        "baseline_p95_ms": base,
        "knee_step_index": knee,
        "knee_users": out[knee]["users"] if knee is not None else None,
        "knee_offered_rps": out[knee]["offered_rps"] if knee is not None else None,
        "knee_measured_rps": out[knee]["rps"] if knee is not None else None,
        "max_measured_rps": max(s["rps"] for s in out),
        "cpu_ms_per_request_median": round(statistics.median(calm), 3)
        if calm
        else None,
        "locust_cpu_max_pct": max(gens) if gens else None,
        "steps": out,
    }


def main() -> None:
    """Calibrate capacity at 1 and 2 replicas and write capacity.json."""
    RAW.mkdir(parents=True, exist_ok=True)
    processes = int(os.environ.get("LOCUST_PROCESSES", "1"))
    configs = {
        "1": run_config(1, int(os.environ.get("USERS_MAX_1", "120")), processes),
        "2": run_config(2, int(os.environ.get("USERS_MAX_2", "240")), processes),
    }
    env = json.loads(
        subprocess.run(
            ["python3", str(ROOT / "loadtest" / "env_info.py")],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    gens = [
        c["locust_cpu_max_pct"]
        for c in configs.values()
        if c["locust_cpu_max_pct"] is not None
    ]
    res = {
        "environment": env,
        "generator": {
            "user_class": "FastHttpUser",
            "per_user_rps": PER_USER_RPS,
            "connection": "new connection per request",
            "processes": processes,
            "step_seconds": STEP_SECONDS,
            "max_process_cpu_pct": max(gens) if gens else None,
            "below_80_pct": bool(gens) and max(gens) < 80,
        },
        "pod_cpu_patch": {"request": POD_CPU_REQUEST, "limit": POD_CPU_LIMIT}
        if POD_CPU_REQUEST
        else None,
        "hpa": "removed during calibration",
        "configs": configs,
        "step_users": configs["2"]["knee_users"],
        "step_offered_rps": configs["2"]["knee_offered_rps"],
    }
    (OUT / "capacity.json").write_text(json.dumps(res, indent=2))
    kn("apply", "-f", str(ROOT / "k8s" / "deployment.yaml"))
    print(json.dumps({k: v for k, v in res.items() if k != "configs"}, indent=2))
    for c in configs.values():
        print({k: v for k, v in c.items() if k != "steps"})


if __name__ == "__main__":
    main()
