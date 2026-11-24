PY := .venv/bin/python

.PHONY: setup check train ablation up down

COMPOSE := docker compose --env-file .env -f docker/docker-compose.yml

# create the virtual environment and install dependencies
setup:
	python3.11 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt -r requirements-dev.txt

# lint and run tests
check:
	$(PY) -m ruff check .
	$(PY) -m pytest -q

# train the classifier and write metrics
train:
	$(PY) -m src.train

# run the additive feature ablation
ablation:
	$(PY) -m src.ablation

# build and start the streaming stack
up:
	@test -f .env || cp .env.example .env
	$(COMPOSE) up -d --build

# stop the streaming stack and remove its volumes
down:
	@test -f .env || cp .env.example .env
	$(COMPOSE) down -v

KIND_CLUSTER := fraud-detection-tabular
KCTX := kind-$(KIND_CLUSTER)
KUBECTL := kubectl --context $(KCTX)
API_TAG := 1.0.0
API_TAG_NEXT := 1.0.1
BATCH_TAG := 1.0.0
METRICS_SERVER := https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.8.0/components.yaml

.PHONY: kind-up k8s-apply k8s-batch loadtest-env loadtest kind-down

# create the kind cluster, install metrics-server, build and load the images
kind-up:
	kind create cluster --config k8s/kind-config.yaml
	$(KUBECTL) apply -f $(METRICS_SERVER)
	$(KUBECTL) -n kube-system patch deployment metrics-server --type=json \
		-p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
	docker build -f docker/Dockerfile.api -t fraud-api:$(API_TAG) .
	docker tag fraud-api:$(API_TAG) fraud-api:$(API_TAG_NEXT)
	docker build -f docker/Dockerfile.batch -t fraud-batch:$(BATCH_TAG) .
	kind load docker-image --name $(KIND_CLUSTER) fraud-api:$(API_TAG) fraud-api:$(API_TAG_NEXT) fraud-batch:$(BATCH_TAG)

# apply the serving manifests and wait for the rollout
k8s-apply:
	$(KUBECTL) apply -f k8s/namespace.yaml
	$(KUBECTL) apply -f k8s/configmap.yaml -f k8s/deployment.yaml -f k8s/service.yaml -f k8s/hpa.yaml -f k8s/pdb.yaml
	$(KUBECTL) -n fraud rollout status deployment/fraud-api --timeout=180s

# run the one-day batch scoring job
k8s-batch:
	$(KUBECTL) -n fraud delete job fraud-batch-score --ignore-not-found
	$(KUBECTL) apply -f k8s/batch-score-job.yaml
	$(KUBECTL) -n fraud wait --for=condition=complete job/fraud-batch-score --timeout=300s
	$(KUBECTL) -n fraud logs job/fraud-batch-score

# create the load test virtual environment
loadtest-env:
	python3.11 -m venv .venv-loadtest
	.venv-loadtest/bin/python -m pip install -r loadtest/requirements.txt

# run the three serving experiments and generate the report
loadtest: loadtest-env
	loadtest/exp_selfheal.sh
	loadtest/exp_rollout.sh
	loadtest/exp_hpa.sh
	$(PY) loadtest/make_report.py

# delete the kind cluster
kind-down:
	kind delete cluster --name $(KIND_CLUSTER)

AIRFLOW_COMPOSE := docker compose --env-file .env -f docker/docker-compose.airflow.yml

.PHONY: airflow-up airflow-down airflow-test

# prepare .env and start the Airflow stack
airflow-up:
	airflow/prepare_env.sh
	$(AIRFLOW_COMPOSE) up -d --build

# stop the Airflow stack and remove its volumes
airflow-down:
	airflow/prepare_env.sh
	$(AIRFLOW_COMPOSE) down -v

# run the DAG tests inside the Airflow image
airflow-test:
	airflow/prepare_env.sh
	$(AIRFLOW_COMPOSE) build scheduler
	$(AIRFLOW_COMPOSE) run --rm --no-deps --entrypoint python \
		-v $(CURDIR)/tests:/opt/project/tests:ro scheduler -m pytest -q -p no:cacheprovider /opt/project/tests/test_dag.py
