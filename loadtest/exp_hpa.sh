#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"

PROFILE="${1:-moderate}"
LOCUST_CLASS=""
LOCUST_FILES="$ROOT/loadtest/locustfile.py,$ROOT/loadtest/ramp_shape.py"
CPU_REQUEST_M=250
PATCH_REQUEST=""
PATCH_LIMIT=""
case "$PROFILE" in
  moderate) export THINK_MIN=0.5 THINK_MAX=1.5 OUT_NAME=hpa ;;
  stress) export THINK_MIN=0.05 THINK_MAX=0.15 OUT_NAME=hpa_stress ;;
  step)
    export OUT_NAME=hpa_step PER_USER_RPS=2 BASE_USERS=15 BASE_SECONDS=90 STEP_SECONDS=300 TAIL_SECONDS=120
    STEP_USERS="$(python3 -c "import json; print(json.load(open('$OUT/capacity.json'))['step_users'])")"
    export STEP_USERS
    PATCH_REQUEST="$(python3 -c "import json; p=json.load(open('$OUT/capacity.json'))['pod_cpu_patch']; print(p['request'] if p else '')")"
    PATCH_LIMIT="$(python3 -c "import json; p=json.load(open('$OUT/capacity.json'))['pod_cpu_patch']; print(p['limit'] if p else '')")"
    LOCUST_FILES="$ROOT/loadtest/locustfile_fast.py,$ROOT/loadtest/step_shape.py"
    LOCUST_CLASS="FastScoringUser"
    ;;
  *) echo "usage: exp_hpa.sh [moderate|stress|step]" >&2; exit 2 ;;
esac
RAW="$OUT/raw/$OUT_NAME"
mkdir -p "$RAW"
SCALE_DOWN_WAIT=720

reset_state no_hpa

# apply the per-run CPU patch, reverted at the end by re-applying the manifest
if [ -n "$PATCH_REQUEST" ]; then
  KN patch deployment fraud-api --type=json -p "[{\"op\":\"replace\",\"path\":\"/spec/template/spec/containers/0/resources/requests/cpu\",\"value\":\"$PATCH_REQUEST\"},{\"op\":\"replace\",\"path\":\"/spec/template/spec/containers/0/resources/limits/cpu\",\"value\":\"$PATCH_LIMIT\"}]"
  KN rollout status deployment/fraud-api --timeout=180s
  wait_stable 2
  CPU_REQUEST_M="${PATCH_REQUEST%m}"
fi

# wait for 2 replicas and 3 consecutive CPU readings below the HPA target
TARGET_PCT=50
SETTLE_START="$(date +%s)"
ok=0
for _ in $(seq 1 120); do
  pct="$(KN top pods -l app=fraud-api --no-headers 2>/dev/null | awk -v req="$CPU_REQUEST_M" '{sub("m","",$2); s+=$2; n++} END{if(n==2) printf "%d", s/n/req*100; else print 999}' || true)"
  if [ "$(pod_count)" -eq 2 ] && [ "${pct:-999}" -lt "$TARGET_PCT" ]; then ok=$((ok + 1)); else ok=0; fi
  echo "settle: cpu_pct=$pct consecutive=$ok"
  if [ "$ok" -ge 3 ]; then break; fi
  sleep 5
done
SETTLE_SECONDS=$(($(date +%s) - SETTLE_START))
[ "$ok" -ge 3 ] || { echo "CPU did not settle" >&2; exit 1; }
KN apply -f "$ROOT/k8s/hpa.yaml"
for _ in $(seq 1 24); do
  [ -n "$(KN get hpa fraud-api -o jsonpath='{.status.currentMetrics[0].resource.current.averageUtilization}')" ] && break
  sleep 5
done
[ "$(pod_count)" -eq 2 ] || { echo "not at 2 replicas before ramp" >&2; exit 1; }

: >"$RAW/samples.tsv"
: >"$RAW/ready.tsv"
sample() {
  local ts reps cpu top
  ts="$(date +%s)"
  reps="$(KN get hpa fraud-api -o jsonpath='{.status.currentReplicas}{" "}{.status.desiredReplicas}')"
  cpu="$(KN get hpa fraud-api -o jsonpath='{.status.currentMetrics[0].resource.current.averageUtilization}')"
  top="$(KN top pods -l app=fraud-api --no-headers 2>/dev/null | awk '{printf "%s:%s ", $1, $2}')"
  printf '%s\t%s\t%s\t%s\n' "$ts" "$reps" "${cpu:-NA}" "$top" | tee -a "$RAW/samples.tsv"
}

# one-second ready and total pod counts
poll_ready() {
  while true; do
    printf '%s\t%s\t%s\n' "$(date +%s.%N)" "$(ready_count)" "$(pod_count)" >>"$RAW/ready.tsv"
    sleep 1
  done
}
poll_ready &
POLL_PID=$!
trap 'kill $POLL_PID 2>/dev/null || true' EXIT

T0="$(date +%s)"
"$LOCUST" -f "$LOCUST_FILES" --headless \
  --host "$HOST" --csv "$RAW/load" --csv-full-history --only-summary $LOCUST_CLASS >"$RAW/load.log" 2>&1 &
LOAD_PID=$!

while kill -0 "$LOAD_PID" 2>/dev/null; do
  sample
  sleep 5
done
T_END="$(date +%s)"
echo "== load ended, watching scale-down =="
T_DOWN=""
for _ in $(seq 1 $((SCALE_DOWN_WAIT / 10))); do
  sample
  cur="$(KN get hpa fraud-api -o jsonpath='{.status.currentReplicas}')"
  if [ "$cur" = "2" ]; then
    T_DOWN="$(date +%s)"
    break
  fi
  sleep 10
done
KN get hpa fraud-api | tee "$RAW/hpa_final.log"
kill "$POLL_PID" 2>/dev/null || true

if [ -n "$PATCH_REQUEST" ]; then
  KN apply -f "$ROOT/k8s/deployment.yaml"
  KN rollout status deployment/fraud-api --timeout=180s
fi

RESULT="result_hpa.py"
if [ "$PROFILE" = "step" ]; then RESULT="result_step.py"; fi
ENV_JSON="$(env_json)" RAW="$RAW" OUT="$OUT" T0="$T0" T_END="$T_END" T_DOWN="$T_DOWN" SETTLE_SECONDS="$SETTLE_SECONDS" \
  PATCH_REQUEST="$PATCH_REQUEST" PATCH_LIMIT="$PATCH_LIMIT" \
  python3 "$ROOT/loadtest/$RESULT"
