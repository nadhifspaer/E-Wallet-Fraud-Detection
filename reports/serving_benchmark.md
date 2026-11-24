# Serving Benchmark

Measured behavior of the scoring API on a local single-node kind cluster. Every number below is read from `reports/serving_results/*.json`.

## Environment

- CPU: AMD Ryzen 7 8845HS w/ Radeon 780M Graphics (12 threads visible to WSL2)
- RAM visible to WSL2: 9.7 GB
- Kernel: 6.18.33.2-microsoft-standard-WSL2
- Cluster: kind v0.33.0 go1.26.7 linux/amd64, one control-plane node, metrics-server with insecure kubelet TLS
- Workload: 2 to 6 API replicas, one uvicorn worker each, LightGBM with `n_jobs=1`
- Requests: 250m CPU, 256Mi memory. Limits: 500m CPU, 512Mi memory
- Rolling update settings: maxUnavailable 0, maxSurge 1, a 10 s `preStop` sleep, 60 s termination grace period
- Load generator: Locust, headless, on the same machine as the cluster

## Results

Targets are proposals fixed before the runs. Latency values are measurements, with no latency target.

| Experiment | Measurement | Proposed target | Measured |
|---|---|---|---|
| Self-heal, pod deleted | Replacement Ready | under 30 s | 5.2 s |
| Self-heal, `/tmp/healthy` removed | Restarts 0 to 1, Ready again | under 30 s | 10.9 s |
| Self-heal | Locust failures | error rate near 0 | 10 of 14031 (0.0713%) |
| Rolling update | Failed requests | 0 | 0 of 11453 |
| Recreate (control) | Failed requests | failures expected | 83 of 9308 |
| Rollout undo | Failed requests during failed rollout and undo | 0 | 0 of 11257 |
| Rollout undo | Ready pods during the failed rollout | at least 1 | 2 |
| Rollout undo | Image after undo | previous image | `fraud-api:1.0.0` |
| Scale-out, step profile | Replicas rise above the minimum of 2 | above minimum | peak 5 (max 6) |
| Scale-out, step profile | Overload p95 against before | at least 3x | 7.04x (met) |
| Scale-out, step profile | p95 after scale-out against overload | at least 50% lower | 0.474 lower (missed) |
| Scale-out, step profile | Return to minimum after the step ends | after the default scale-down delay | 335 s |

### Latency

Self-heal and rollout runs: constant 10 users with a think time of 0.05 to 0.15 s per user. Other runs are described in their sections.

| Run | Requests | RPS | p50 ms | p95 ms | p99 ms |
|---|---|---|---|---|---|
| Self-heal | 14031 | 94.1 | 5.0 | 9.0 | 12.0 |
| Rolling update | 11453 | 96.2 | 4.0 | 6.0 | 7.0 |
| Recreate | 9308 | 78.1 | 4.0 | 8.0 | 11.0 |
| Rollout undo | 11257 | 94.5 | 5.0 | 8.0 | 10.0 |
| Scale-out, moderate profile, whole run | 61118 | 145.4 | 4.0 | 7.0 | 11.0 |
| Scale-out, stress run, whole run | 346667 | 823.7 | 50.0 | 200.0 | 300.0 |

## Capacity calibration

The HPA was removed and the deployment held at a fixed replica count. The load rose by 10 users every 20 s, each user sending 2.0 requests per second. The generator is Locust `FastHttpUser` (1 process) and opens a new connection per request. Per-step p95 is the median of the per-second p95 values after the first 10 s of the step. The knee is the first step where that p95 and the next step's p95 are both at least 3 times the median p95 of the first three steps.

| Replicas | Baseline p95 ms | Knee offered rps | Knee measured rps | Max measured rps | CPU ms per request | Generator CPU max % of one core |
|---|---|---|---|---|---|---|
| 1 | 56.0 | 180.0 | 176.4 | 176.4 | 1.575 (saturated steps) | 13.8 |
| 2 | 20.0 | 180.0 | 180.0 | 333.2 | 1.567 | 24.4 |

Generator CPU stayed below 80% of one core in every run (maximum 24.4%). CPU per request is the pod cgroup CPU time divided by the requests served in the step window.
No pod CPU patch was applied. The base manifest values (request 250m, limit 500m) were used.

## Scale-out, step profile

### Success criteria

Fixed before the run and not changed afterwards.

- p95 during overload is at least 3 times the p95 before the load step.
- p95 after scale-out is at least 50% lower than the p95 during overload.

Windows, all measured as the median of Locust per-second p95 values (a 10 s rolling window):

- Before: from 10 s after the baseline load starts until the step.
- Overload: from 10 s after the step until the first new replica is Ready (from the step itself when that leaves fewer than 5 samples).
- After scale-out: from the first moment the Ready and total pod counts stay unchanged for 60 s, until the step ends.
- Load off: from 10 s after the step ends until the run ends. The baseline load continues so that p95 stays measurable.

Load: a constant baseline, one step to the calibrated 2-replica knee of 180.0 requests per second (90 users), a hold until the HPA settles, then the baseline again. HPA target 50% CPU, minimum 2, maximum 6.

### Result

Baseline 30 requests per second (15 users) for 90 s, step to 180 requests per second (90 users) for 300 s, then the baseline again for 120 s. The deployment started at 2 replicas after 11 s of settling (three consecutive CPU readings below the target).

| Window | Seconds | Samples | Median rps | p95 ms (median) | p95 ms (max) |
|---|---|---|---|---|---|
| Before the step | 82 | 81 | 30.0 | 27.0 | 75.0 |
| Overload, before the first new replica is Ready | 22 | 22 | 180.0 | 190.0 | 200.0 |
| After scale-out, replicas stable for 60 s | 222 | 221 | 180.0 | 100.0 | 130.0 |
| After the step ends | 110 | 110 | 30.0 | 17.0 | 19.0 |

| Criterion | Threshold | Measured | Outcome |
|---|---|---|---|
| Overload p95 against before | at least 3.0x | 7.04x | met |
| After scale-out p95 against overload | at least 50% lower | 0.474 (fraction lower) | missed |

| Event | Seconds after the step |
|---|---|
| First replica count increase seen | 43 |
| First new replica Ready | 31.9 |
| Replica counts stable for 60 s from | 77.1 |
| Peak replicas | 5 (max 6) |
| Back to 2 replicas, seconds after the step ends | 335 |

Replica count over time (seconds relative to the step; the HPA current and desired replicas and the average CPU utilization it reported):

| t s | Current | Desired | CPU % of request |
|---|---|---|---|
| -93 | 2 | 2 | 1 |
| -76 | 2 | 2 | 3 |
| -60 | 2 | 2 | 14 |
| -44 | 2 | 2 | 14 |
| -27 | 2 | 2 | 18 |
| -11 | 2 | 2 | 18 |
| 5 | 2 | 2 | 17 |
| 22 | 2 | 2 | 19 |
| 38 | 2 | 4 | 91 |
| 54 | 4 | 4 | 102 |
| 71 | 4 | 4 | 74 |
| 87 | 5 | 5 | 59 |
| 104 | 5 | 5 | 54 |
| 120 | 5 | 5 | 49 |
| 137 | 5 | 5 | 50 |
| 153 | 5 | 5 | 49 |
| 170 | 5 | 5 | 49 |
| 186 | 5 | 5 | 49 |
| 202 | 5 | 5 | 48 |
| 219 | 5 | 5 | 50 |
| 235 | 5 | 5 | 50 |
| 252 | 5 | 5 | 48 |
| 268 | 5 | 5 | 49 |
| 285 | 5 | 5 | 49 |
| 301 | 5 | 5 | 49 |
| 317 | 5 | 5 | 45 |
| 334 | 5 | 5 | 18 |
| 350 | 5 | 5 | 9 |
| 366 | 5 | 5 | 9 |
| 383 | 5 | 5 | 10 |
| 399 | 5 | 5 | 10 |
| 415 | 5 | 5 | 9 |
| 442 | 5 | 5 | 9 |
| 474 | 5 | 5 | 1 |
| 506 | 5 | 5 | 1 |
| 538 | 5 | 5 | 1 |
| 569 | 5 | 5 | 1 |
| 601 | 5 | 5 | 1 |
| 633 | 2 | 2 | 1 |

Full series, per-pod CPU and the one-second Ready counts are in `reports/serving_results/hpa_step.json` and `raw/hpa_step/`.

## Scale-out, supporting runs

### Moderate profile

Think time 0.5 to 1.5 s per user, keep-alive sessions. Users ramp from 10 to 200 over 120 s, then hold for 240 s. The deployment started at 2 replicas after 17 s of settling. First replica increase 184 s after the ramp start, peak 4 replicas, back to the minimum 350 s after load ended. Each p95 is the median of the per-interval p95 in that window.

| Phase | Seconds from start | p95 ms |
|---|---|---|
| Before ramp | 0 to 60 | 4.0 |
| Ramp | 60 to 180 | 6.0 |
| Hold, early | 180 to 300 | 7.0 |
| Hold, late | 300 to 420 | 7.0 |

Data: `reports/serving_results/hpa.json`.

### Stress run

Think time 0.05 to 0.15 s per user, keep-alive sessions, the same 10 to 200 user ramp. Whole-run average load was 823.7 requests per second (346667 requests, 0 failures). Replicas reached 6. p95 was 9.0 ms before the ramp, 160.0 ms during the ramp, and 210.0 ms and 210.0 ms in the two hold windows, so p95 did not recover. The single machine shared with the load generator was the limit. Data: `reports/serving_results/hpa_stress.json`.

## Targets missed

- Step profile: p95 after scale-out was 0.474 lower than during overload, below the 50% criterion.
- Moderate profile, p95 recovery: p95 was 4.0 ms before the ramp and 7.0 ms in the last 120 s of the hold, after the replicas reached 4. It did not return to the pre-ramp level.

## Limits

- The load generator and the cluster share one machine and one CPU budget. Locust competes with the API pods, the kind node, and metrics-server for the same cores.
- Single-node kind demonstrates mechanisms (probes, restarts, rolling updates, autoscaling). The numbers do not describe production capacity.
- During the self-heal and rollout runs the HPA is removed so the replica count stays at 2. It is applied again for the scale-out runs.
- The step profile and the calibration use a new connection per request. The moderate and stress runs use keep-alive sessions, so their connections stay with the pods that existed when each user started.
- Calibration steps last 20 s and the p95 values are noisy near the knee. The knee is a single measured rate, not a confidence interval.
- Each run is a single execution. No repeat or confidence interval is reported.
- Request payloads are rows from `data/sample/sample_features.csv`, so the score distribution is not production traffic.
