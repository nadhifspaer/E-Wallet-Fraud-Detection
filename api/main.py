import hashlib
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from pydantic import ConfigDict, Field, create_model

from src import score_pipeline
from src.config import FEATURE_LIST_PATH, MODEL_PATH

logger = logging.getLogger("fraud_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

HEALTH_FILE = Path("/tmp/healthy")
NULLABLE_FEATURES = {"orig_drain_ratio"}

FEATURES: list[str] = json.loads(FEATURE_LIST_PATH.read_text())

_fields = {
    name: (float | None if name in NULLABLE_FEATURES else float, Field(...)) for name in FEATURES
}
PredictRequest = create_model(
    "PredictRequest",
    __config__=ConfigDict(extra="forbid"),
    **_fields,
)

registry = CollectorRegistry()
REQUESTS = Counter(
    "api_requests_total", "Total requests", ["method", "path", "status"], registry=registry
)
LATENCY = Histogram(
    "api_request_latency_seconds", "Request latency in seconds", ["path"], registry=registry
)
ERRORS = Counter("api_errors_total", "Responses with status 5xx", registry=registry)
IN_FLIGHT = Gauge("api_in_flight_requests", "Requests in flight", registry=registry)

state = {"ready": False, "model_version": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the model once and mark the service healthy."""
    state["model_version"] = hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()[:8]
    score_pipeline.load_feature_list()
    score_pipeline.load_model()
    HEALTH_FILE.touch()
    state["ready"] = True
    logger.info("model loaded, version=%s", state["model_version"])
    yield
    state["ready"] = False
    HEALTH_FILE.unlink(missing_ok=True)
    logger.info("shutdown complete")


app = FastAPI(title="Fraud scoring API", lifespan=lifespan)


@app.middleware("http")
async def record_metrics(request: Request, call_next):
    """Record request count, latency, errors, and in-flight gauge."""
    path = request.url.path
    IN_FLIGHT.inc()
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        IN_FLIGHT.dec()
        LATENCY.labels(path).observe(time.perf_counter() - start)
        REQUESTS.labels(request.method, path, str(status)).inc()
        if status >= 500:
            ERRORS.inc()


@app.post("/predict")
def predict(payload: PredictRequest):
    """Score one ready feature vector."""
    if not state["ready"]:
        return JSONResponse({"detail": "model not loaded"}, status_code=503)
    row = pd.DataFrame([payload.model_dump()], columns=FEATURES).astype("float64")
    s = float(score_pipeline.score(row)[0])
    return {"score": min(max(s, 0.0), 1.0), "model_version": state["model_version"]}


@app.get("/ready")
def ready():
    """Return 200 once the model is loaded, else 503."""
    if state["ready"]:
        return {"status": "ready"}
    return JSONResponse({"status": "loading"}, status_code=503)


@app.get("/health")
def health():
    """Return 200 while the health file exists, else 503."""
    if HEALTH_FILE.exists():
        return {"status": "ok"}
    return JSONResponse({"status": "unhealthy"}, status_code=503)


@app.get("/metrics")
def metrics():
    """Expose Prometheus metrics."""
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
