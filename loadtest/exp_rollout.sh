#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"

EXP=rollout
RAW="$OUT/raw/$EXP"
mkdir -p "$RAW"
LOAD_SECONDS=120
declare -A SECS

phase() {
  local name="$1" fn="$2" t
  echo "== $name =="
  start_load "$RAW/$name" 10 "$LOAD_SECONDS"
  sleep 15
  t="$(date +%s)"
  "$fn"
  SECS[$name]="$(($(date +%s) - t))"
  wait_load
  python3 "$ROOT/loadtest/summarize.py" "$RAW/$name" | tee "$RAW/$name.summary.json"
}

do_rolling() {
  KN set image deployment/fraud-api api=fraud-api:1.0.1
  KN rollout status deployment/fraud-api --timeout=180s
}

do_recreate() {
  KN patch deployment fraud-api -p '{"spec":{"strategy":{"type":"Recreate","rollingUpdate":null}}}'
  KN set image deployment/fraud-api api=fraud-api:1.0.0
  KN rollout status deployment/fraud-api --timeout=180s
}

do_undo() {
  KN patch deployment fraud-api -p '{"spec":{"strategy":{"type":"RollingUpdate","rollingUpdate":{"maxUnavailable":0,"maxSurge":1}}}}'
  KN set image deployment/fraud-api api=fraud-api:9.9.9-missing
  sleep 25
  echo "-- state during the failed rollout --"
  KN get pods -l app=fraud-api | tee "$RAW/undo_failed_state.log"
  ready_count >"$RAW/undo_ready_during.txt"
  KN rollout undo deployment/fraud-api
  KN rollout status deployment/fraud-api --timeout=180s
}

reset_state no_hpa
phase rolling do_rolling
wait_stable 2
phase recreate do_recreate
wait_stable 2
phase undo do_undo
wait_stable 2
FINAL_IMAGE="$(KN get deployment fraud-api -o jsonpath='{.spec.template.spec.containers[0].image}')"
echo "final image after undo: $FINAL_IMAGE"
reset_state no_hpa

ENV_JSON="$(env_json)" FINAL_IMAGE="$FINAL_IMAGE" RAW="$RAW" OUT="$OUT" LOAD_SECONDS="$LOAD_SECONDS" \
  S_ROLLING="${SECS[rolling]}" S_RECREATE="${SECS[recreate]}" S_UNDO="${SECS[undo]}" \
  python3 "$ROOT/loadtest/result_rollout.py"
