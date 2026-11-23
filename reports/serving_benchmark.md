# Serving Benchmark

Measured behavior of the scoring API on a local single-node kind cluster. Every number below is read from `reports/serving_results/*.json`.

## Environment

- CPU: AMD Ryzen 7 8845HS w/ Radeon 780M Graphics (12 threads visible to WSL2)
- RAM visible to WSL2: 9.7 GB
- Kernel: 6.18.33.2-microsoft-standard-WSL2
- Cluster: kind v0.33.0 go1.26.7 linux/amd64, one control-plane node, metrics-server with insecure kubelet TLS
- Workload: 2 to 6 API replicas, one uvicorn worker each, LightGBM with `n_jobs=1`
- Requests: 250m CPU, 256Mi memory. Limits: 500m CPU, 512Mi memory
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
| Scale-out | First replica increase after load start | above min of 2 | 60 s |
| Scale-out | Peak replicas | above min of 2 | 6 (max 6) |
| Scale-out | Return to min after load end | after the default scale-down delay | 350 s |

### Latency

Load: constant 10 users for the self-heal and rollout runs.

| Run | Requests | RPS | p50 ms | p95 ms | p99 ms |
|---|---|---|---|---|---|
| Self-heal | 14031 | 94.1 | 5.0 | 9.0 | 12.0 |
| Rolling update | 11453 | 96.2 | 4.0 | 6.0 | 7.0 |
| Recreate | 9308 | 78.1 | 4.0 | 8.0 | 11.0 |
| Rollout undo | 11257 | 94.5 | 5.0 | 8.0 | 10.0 |
| Scale-out, whole run | 346667 | 823.7 | 50.0 | 200.0 | 300.0 |

### Scale-out, p95 by phase

Users ramp from 10 to 200 over 120 s, then hold for 240 s. Each value is the median of the per-interval p95 reported by Locust in that window.

| Phase | Seconds from start | p95 ms |
|---|---|---|
| Before ramp | 0 to 60 | 9.0 |
| Ramp | 60 to 180 | 160.0 |
| Hold, early | 180 to 300 | 210.0 |
| Hold, late | 300 to 420 | 210.0 |

Replica and CPU samples over time are in `reports/serving_results/hpa.json` (`series`) and the raw logs are in `reports/serving_results/raw/`.

## Targets missed

- Scale-out p95 recovery: p95 was 9.0 ms before the ramp and 210.0 ms in the last 120 s of the hold, after the replicas reached 6. It did not return to the pre-ramp level.

## Limits

- The load generator and the cluster share one machine and one CPU budget. Locust competes with the API pods, the kind node, and metrics-server for the same cores.
- Single-node kind demonstrates mechanisms (probes, restarts, rolling updates, autoscaling). The numbers do not describe production capacity.
- The Locust process is single-threaded Python. At 200 users it can limit the offered rate before the API does.
- During the self-heal and rollout runs the HPA is removed so the replica count stays at 2. It is applied again for the scale-out run.
- Each user waits 0.05 to 0.15 s between requests (unchanged from the first round). At 200 users this saturates the API pods and the shared CPU.
- The pods are given a 10 s `preStop` sleep and a 60 s termination grace period before the rolling update run.
- Each run is a single execution. No repeat or confidence interval is reported.
- Request payloads are rows from `data/sample/sample_features.csv`, so the score distribution is not production traffic.
