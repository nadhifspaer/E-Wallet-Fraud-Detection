# Serving Benchmark

This report shows how the scoring API behaves on a local single-node kind cluster. Every number is read from `reports/serving_results/*.json`.

**How to read the results**

- **Replica:** one running copy of the API.
- **Autoscaling (HPA):** Kubernetes adds or removes replicas based on CPU use.
- **RPS:** requests per second.
- **p50, p95, p99:** response times. For p95, 95 of 100 requests were faster than this value.
- **Rolling update:** a new version is started step by step while the old one keeps serving.
- **Recreate:** the old version is stopped first, then the new one starts. It is used here as a comparison.

## Environment

- **CPU:** AMD Ryzen 7 8845HS (12 threads visible to WSL2).
- **Memory:** 9.7 GB visible to WSL2.
- **Kernel:** 6.18.33.2-microsoft-standard-WSL2.
- **Cluster:** kind v0.33.0, one control-plane node, metrics-server with insecure kubelet TLS.
- **API:** 2 to 6 replicas, one uvicorn worker each, LightGBM with `n_jobs=1`.
- **Resources per replica:** request 250m CPU and 256Mi memory, limit 500m CPU and 512Mi memory.
- **Rolling update settings:** `maxUnavailable` 0, `maxSurge` 1, 10 s `preStop` sleep, 60 s grace period.
- **Load generator:** Locust, headless, on the same machine as the cluster.

## Results

The targets were set before the runs. Response times are measurements only, with no target.

| Experiment | What was measured | Target | Result |
|---|---|---|---|
| Self-heal, pod deleted | Time until the new pod is Ready | under 30 s | 5.2 s |
| Self-heal, `/tmp/healthy` removed | Restart and Ready again | under 30 s | 10.9 s |
| Self-heal | Failed requests | error rate near 0 | 10 of 14,031 (0.0713%) |
| Rolling update | Failed requests | 0 | 0 of 11,453 |
| Recreate (comparison) | Failed requests | failures expected | 83 of 9,308 |
| Rollback after a failed rollout | Failed requests | 0 | 0 of 11,257 |
| Rollback after a failed rollout | Ready pods during the failed rollout | at least 1 | 2 |
| Rollback after a failed rollout | Image after rollback | previous image | `fraud-api:1.0.0` |
| Scale-out, step profile | Replicas rise above the minimum of 2 | above 2 | peak 5 (max 6) |
| Scale-out, step profile | p95 under overload compared with before | at least 3x | 7.04x (met) |
| Scale-out, step profile | p95 after scale-out compared with overload | at least 50% lower | 47.4% lower (missed) |
| Scale-out, step profile | Return to 2 replicas after the load ends | after the default delay | 335 s |

### Response times

Self-heal and rollout runs used a constant 10 users, each waiting 0.05 to 0.15 s between requests.

| Run | Requests | RPS | p50 ms | p95 ms | p99 ms |
|---|---|---|---|---|---|
| Self-heal | 14,031 | 94.1 | 5.0 | 9.0 | 12.0 |
| Rolling update | 11,453 | 96.2 | 4.0 | 6.0 | 7.0 |
| Recreate | 9,308 | 78.1 | 4.0 | 8.0 | 11.0 |
| Rollback | 11,257 | 94.5 | 5.0 | 8.0 | 10.0 |
| Scale-out, moderate profile (whole run) | 61,118 | 145.4 | 4.0 | 7.0 | 11.0 |
| Scale-out, stress profile (whole run) | 346,667 | 823.7 | 50.0 | 200.0 | 300.0 |

## Capacity test

The autoscaler was removed and the number of replicas was fixed. Load grew by 10 users every 20 s, and each user sent 2.0 requests per second. The load generator (Locust `FastHttpUser`, 1 process) opens a new connection for each request.

- **p95 per step:** the median of the per-second p95 values, after the first 10 s of the step.
- **Breaking point:** the first step where p95 and the next step's p95 are both at least 3 times the median p95 of the first three steps.
- No change was made to the CPU settings. The base values (request 250m, limit 500m) were used.

| Replicas | p95 at start (ms) | Breaking point, offered RPS | Breaking point, measured RPS | Highest measured RPS | CPU ms per request | Load generator CPU, max (% of one core) |
|---|---|---|---|---|---|---|
| 1 | 56.0 | 180.0 | 176.4 | 176.4 | 1.575 (saturated steps) | 13.8 |
| 2 | 20.0 | 180.0 | 180.0 | 333.2 | 1.567 | 24.4 |

The load generator stayed below 80% of one core in every run (maximum 24.4%). CPU per request is the pod CPU time divided by the requests served in the step.

## Scale-out, step profile

### Plan

Load pattern:

1. A constant base load of 30 RPS (15 users) for 90 s.
2. A step up to 180 RPS (90 users), the breaking point of 2 replicas, for 300 s.
3. The base load again for 120 s.

Autoscaling settings: CPU target 50%, minimum 2 replicas, maximum 6. The run started with 2 replicas after 11 s of settling.

Success criteria were fixed before the run and were not changed:

- p95 under overload is at least 3 times the p95 before the step.
- p95 after scale-out is at least 50% lower than the p95 under overload.

Time windows (each value is the median of Locust per-second p95 values):

- **Before:** from 10 s after the base load starts until the step.
- **Overload:** from 10 s after the step until the first new replica is Ready.
- **After scale-out:** from the moment the pod counts stay unchanged for 60 s, until the step ends.
- **After the step ends:** from 10 s after the step ends until the run ends. The base load continues so p95 can still be measured.

### Result

| Window | Seconds | Samples | Median RPS | p95 ms (median) | p95 ms (max) |
|---|---|---|---|---|---|
| Before the step | 82 | 81 | 30.0 | 27.0 | 75.0 |
| Overload, before the first new replica is Ready | 22 | 22 | 180.0 | 190.0 | 200.0 |
| After scale-out, replicas stable for 60 s | 222 | 221 | 180.0 | 100.0 | 130.0 |
| After the step ends | 110 | 110 | 30.0 | 17.0 | 19.0 |

| Criterion | Target | Result | Outcome |
|---|---|---|---|
| p95 under overload compared with before | at least 3x | 7.04x | met |
| p95 after scale-out compared with overload | at least 50% lower | 47.4% lower | missed |

| Event | Time |
|---|---|
| First new replica Ready | 31.9 s after the step |
| First increase in replica count seen | 43 s after the step |
| Replica count stable for 60 s from | 77.1 s after the step |
| Peak replicas | 5 (max 6) |
| Back to 2 replicas | 335 s after the step ends |

The first row comes from the one-second count of Ready pods. The second row comes from the replica count reported by the autoscaler, sampled about every 5 s. The two sources are sampled differently.

Replicas and CPU over time (seconds relative to the step, selected rows):

| Time (s) | Current replicas | Desired replicas | CPU % of request |
|---|---|---|---|
| -93 | 2 | 2 | 1 |
| -27 | 2 | 2 | 18 |
| 22 | 2 | 2 | 19 |
| 38 | 2 | 4 | 91 |
| 54 | 4 | 4 | 102 |
| 87 | 5 | 5 | 59 |
| 120 to 317 | 5 | 5 | 45 to 50 |
| 334 | 5 | 5 | 18 |
| 474 to 601 | 5 | 5 | 1 |
| 633 | 2 | 2 | 1 |

Selection rule: each single time shows the sample nearest to that time, and each range row shows the lowest to highest value among the samples within the range.

The full series, CPU per pod, and the one-second Ready counts are in `reports/serving_results/hpa_step.json` and `raw/hpa_step/`.

## Scale-out, other runs

### Moderate profile

- Each user waits 0.5 to 1.5 s between requests and keeps its connection open (keep-alive).
- Users grow from 10 to 200 over 120 s, then stay at 200 for 240 s.
- The run started with 2 replicas after 17 s of settling.
- First replica increase: 184 s after the start of the ramp. Peak: 4 replicas. Back to 2 replicas: 350 s after the load ended.

| Phase | Seconds from start | p95 ms |
|---|---|---|
| Before the ramp | 0 to 60 | 4.0 |
| Ramp | 60 to 180 | 6.0 |
| Hold, early | 180 to 300 | 7.0 |
| Hold, late | 300 to 420 | 7.0 |

Data: `reports/serving_results/hpa.json`.

### Stress profile

- Each user waits 0.05 to 0.15 s between requests and keeps its connection open. The ramp is the same, 10 to 200 users.
- Average load over the whole run: 823.7 RPS (346,667 requests, 0 failures). Replicas reached 6.
- p95 was 9.0 ms before the ramp, 160.0 ms during the ramp, and 210.0 ms in both hold windows. It did not recover.
- The limit was the single machine, shared with the load generator.

Data: `reports/serving_results/hpa_stress.json`.

## Targets missed

- **Step profile:** p95 after scale-out was 47.4% lower than under overload. The target was 50%.
- **Moderate profile:** p95 was 4.0 ms before the ramp and 7.0 ms in the last 120 s of the hold, with 4 replicas. It did not return to the starting level.
- **Stress profile:** p95 was 9.0 ms before the ramp and 210.0 ms in both hold windows, with 6 replicas. It did not recover.

## Limits

- The load generator and the cluster share one machine and one CPU budget. Locust competes with the API pods, the kind node, and metrics-server.
- A single-node kind cluster shows how the mechanisms work (probes, restarts, rolling updates, autoscaling). The numbers do not describe production capacity.
- The autoscaler is removed in the self-heal and rollout runs so the replica count stays at 2. It is applied again for the scale-out runs.
- The step profile and the capacity test open a new connection for each request. The moderate and stress profiles keep connections open, so each user stays with the pod that first served it. New replicas receive traffic only from users that connect after the replicas are Ready. This is a likely limit on p95 recovery in those two profiles. The runs do not test this directly.
- One Locust process creates all the load. Load generator CPU was recorded only in the capacity test, not in the stress run.
- Each capacity step lasts 20 s, so p95 is noisy near the breaking point. The breaking point is one measured value with no confidence range.
- Each run was done once. No repeats or confidence ranges are reported.
- Requests use rows from `data/sample/sample_features.csv`, so the scores do not represent real traffic.

## Batch scoring run

The Airflow daily DAG scored every day window of the dataset on a local Airflow 3 stack with a Postgres metadata database.

| Item | Value |
|---|---|
| DAG runs | 31 (one per 24-step day, day 30 covers steps 721 to 743) |
| Total time for the full catch-up | 11 min 16 s |
| Rows scored | 6,362,620 (same as the source; the 31 partitions add up to the same total) |
| Output | one Parquet file per day under `data/scored/date=YYYY-MM-DD/` |
| Rerun of day 5 | zero score difference from the first run |

After each partition is written, a quality check runs. The run fails if any rule is broken:

- The partition row count equals the source row count of the day window.
- `txn_id`, `step`, and `score` have no empty values.
- Every score is between 0 and 1.
- The scores are not all the same (standard deviation above 0).

Notes:

- The run shows that the pipeline works and gives the same result when repeated. It is not a measure of model quality.
- Days 0 to 24 are in the training range (the cutoff at step 594 falls in day 24), so the model has seen their labels. Model quality is reported in `reports/model_evaluation.md`, from the test part only.
- Daily row counts range from 272 to 574,255 (`reports/eda_numbers.json`), so the run time of each day depends on the day.
- The total time, the run count, and the day-5 comparison come from the run log of the catch-up. They are not stored as files in `reports/`.