#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CTX="kind-fraud-detection-tabular"
NS="fraud"
HOST="http://127.0.0.1:30080"
LOCUST="$ROOT/.venv-loadtest/bin/locust"
OUT="$ROOT/reports/serving_results"

KN() { kubectl --context "$CTX" -n "$NS" "$@"; }

# pod name, restart count, ready flag, deletion timestamp
pods_state() {
  KN get pods -l app=fraud-api -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.containerStatuses[0].restartCount}{" "}{.status.conditions[?(@.type=="Ready")].status}{" "}{.metadata.deletionTimestamp}{"\n"}{end}'
}

# count of Ready pods that are not terminating
ready_count() { pods_state | awk '$3=="True" && $4==""' | wc -l; }

# total non-terminating pods
pod_count() { pods_state | awk '$4==""' | wc -l; }

wait_stable() {
  local want="$1" i
  for i in $(seq 1 180); do
    if [ "$(ready_count)" -eq "$want" ] && [ "$(pod_count)" -eq "$want" ] \
      && [ "$(curl -s -o /dev/null -w '%{http_code}' "$HOST/ready")" = "200" ]; then
      return 0
    fi
    sleep 1
  done
  echo "timeout waiting for $want ready pods" >&2
  return 1
}

# restore the deployment to its manifest state with 2 replicas
reset_state() {
  if [ "${1:-}" = "no_hpa" ]; then KN delete hpa fraud-api --ignore-not-found; fi
  KN apply -f "$ROOT/k8s/deployment.yaml"
  KN scale deployment fraud-api --replicas=2
  KN rollout status deployment/fraud-api --timeout=180s
  wait_stable 2
}

# start a headless constant-user Locust run in the background
start_load() {
  LOAD_PREFIX="$1"
  LOAD_T0="$(date +%s.%N)"
  "$LOCUST" -f "$ROOT/loadtest/locustfile.py" --headless -u "$2" -r "$2" -t "${3}s" \
    --host "$HOST" --csv "$LOAD_PREFIX" --csv-full-history --only-summary \
    >"$LOAD_PREFIX.log" 2>&1 &
  LOAD_PID=$!
}

wait_load() { wait "$LOAD_PID" || true; }

# environment facts for the report
env_json() {
  python3 "$ROOT/loadtest/env_info.py"
}
