#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"

EXP=selfheal
RAW="$OUT/raw/$EXP"
mkdir -p "$RAW"
LOAD_SECONDS=150

reset_state no_hpa
start_load "$RAW/load" 10 "$LOAD_SECONDS"
KN get pods -l app=fraud-api -w -o wide >"$RAW/pods_watch.log" 2>&1 &
WATCH=$!
trap 'kill $WATCH 2>/dev/null || true' EXIT
sleep 20

echo "== pod deletion =="
VICTIM="$(pods_state | awk 'NR==1{print $1}')"
OLD="$(pods_state | awk '{print $1}' | sort | tr '\n' ' ')"
T_A="$(date +%s.%N)"
KN delete pod "$VICTIM" --wait=false
READY_A=""
for _ in $(seq 1 240); do
  new_ready="$(pods_state | awk -v old="$OLD" '$3=="True" && $4=="" && index(" " old " ", " " $1 " ")==0' | wc -l)"
  if [ "$new_ready" -ge 1 ] && [ "$(ready_count)" -ge 2 ]; then
    READY_A="$(python3 -c "import time; print(round(time.time() - $T_A, 1))")"
    break
  fi
  sleep 0.5
done
echo "victim=$VICTIM replacement_ready_seconds=$READY_A"
pods_state
wait_stable 2
sleep 10

echo "== liveness failure =="
POD="$(pods_state | awk 'NR==1{print $1}')"
RESTARTS_BEFORE="$(pods_state | awk -v p="$POD" '$1==p{print $2}')"
T_B="$(date +%s.%N)"
KN exec "$POD" -- rm /tmp/healthy
READY_B=""
RESTARTS_AFTER="$RESTARTS_BEFORE"
for _ in $(seq 1 240); do
  RESTARTS_AFTER="$(pods_state | awk -v p="$POD" '$1==p{print $2}')"
  ready="$(pods_state | awk -v p="$POD" '$1==p{print $3}')"
  if [ "${RESTARTS_AFTER:-0}" -gt "$RESTARTS_BEFORE" ] && [ "$ready" = "True" ]; then
    READY_B="$(python3 -c "import time; print(round(time.time() - $T_B, 1))")"
    break
  fi
  sleep 0.5
done
echo "pod=$POD restarts $RESTARTS_BEFORE -> $RESTARTS_AFTER ready_after_seconds=$READY_B"
KN get events --field-selector "involvedObject.name=$POD" --sort-by=.lastTimestamp \
  -o custom-columns=REASON:.reason,MESSAGE:.message | tee "$RAW/liveness_events.log"
wait_load
kill "$WATCH" 2>/dev/null || true
echo "== watch log tail =="
tail -n 15 "$RAW/pods_watch.log"

ENV_JSON="$(env_json)" READY_A="$READY_A" READY_B="$READY_B" POD="$POD" VICTIM="$VICTIM" \
  RB="$RESTARTS_BEFORE" RA="$RESTARTS_AFTER" RAW="$RAW" OUT="$OUT" LOAD_SECONDS="$LOAD_SECONDS" \
  python3 "$ROOT/loadtest/result_selfheal.py"
