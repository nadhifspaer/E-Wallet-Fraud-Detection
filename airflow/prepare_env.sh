#!/usr/bin/env bash
# create .env from the example, fill missing keys, set the host user id
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || cp .env.example .env
while IFS= read -r line; do
  key="${line%%=*}"
  grep -q "^${key}=" .env || echo "$line" >> .env
done < .env.example
sed -i "s/^AIRFLOW_UID=.*/AIRFLOW_UID=$(id -u)/" .env
for key in AIRFLOW_JWT_SECRET AIRFLOW_API_SECRET_KEY; do
  if grep -q "^${key}=generate$" .env; then
    sed -i "s/^${key}=generate$/${key}=$(openssl rand -hex 32)/" .env
  fi
done
if grep -q "^AIRFLOW_FERNET_KEY=generate$" .env; then
  sed -i "s|^AIRFLOW_FERNET_KEY=generate$|AIRFLOW_FERNET_KEY=$(openssl rand -base64 32 | tr '+/' '-_')|" .env
fi
