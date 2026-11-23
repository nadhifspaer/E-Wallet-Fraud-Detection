#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"

EXP=hpa
RAW="$OUT/raw/$EXP"
mkdir -p "$RAW"
SCALE_DOWN_WAIT=720

reset_state no_hpa

# wait for 2 replicas and 3 consecutive CPU readings below the HPA target
CPU_REQUEST_M=250
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
sample() {
  local ts reps cpu top
  ts="$(date +%s)"
  reps="$(KN get hpa fraud-api -o jsonpath='{.status.currentReplicas}{" "}{.status.desiredReplicas}')"
  cpu="$(KN get hpa fraud-api -o jsonpath='{.status.currentMetrics[0].resource.current.averageUtilization}')"
  top="$(KN top pods -l app=fraud-api --no-headers 2>/dev/null | awk '{printf "%s:%s ", $1, $2}')"
  printf '%s\t%s\t%s\t%s\n' "$ts" "$reps" "${cpu:-NA}" "$top" | tee -a "$RAW/samples.tsv"
}

T0="$(date +%s)"
"$LOCUST" -f "$ROOT/loadtest/locustfile.py,$ROOT/loadtest/ramp_shape.py" --headless \
  --host "$HOST" --csv "$RAW/load" --csv-full-history --only-summary >"$RAW/load.log" 2>&1 &
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

ENV_JSON="$(env_json)" RAW="$RAW" OUT="$OUT" T0="$T0" T_END="$T_END" T_DOWN="$T_DOWN" SETTLE_SECONDS="$SETTLE_SECONDS" \
  python3 "$ROOT/loadtest/result_hpa.py"
