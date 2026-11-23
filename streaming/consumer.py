import json
import logging
import math
import os
import signal
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests
from kafka import KafkaConsumer

from src.config import FEATURE_LIST
from src.feature_engineering import build_features

logger = logging.getLogger("consumer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

HEALTH_FILE = Path("/tmp/healthy")
RETRY_SLEEP_SECONDS = 2.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS scores (
    txn_id INTEGER PRIMARY KEY,
    step INTEGER NOT NULL,
    score REAL NOT NULL,
    label INTEGER NOT NULL,
    latency_ms REAL NOT NULL,
    scored_at TEXT NOT NULL
)
"""

_stop = False


def _json_value(v: float) -> float | None:
    """Return a float, or None for a missing value."""
    v = float(v)
    return None if math.isnan(v) else v


def build_payloads(rows: list[dict]) -> list[dict]:
    """Build one FEATURE_LIST-only payload per raw row."""
    feats = build_features(pd.DataFrame(rows))[FEATURE_LIST]
    return [{k: _json_value(v) for k, v in rec.items()} for rec in feats.to_dict("records")]


def open_store(path: str) -> sqlite3.Connection:
    """Open the SQLite store in WAL mode and ensure the schema."""
    conn = sqlite3.connect(path, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def write_scores(conn: sqlite3.Connection, records: list[tuple]) -> None:
    """Insert score rows, ignoring txn_ids already stored."""
    conn.executemany(
        "INSERT OR IGNORE INTO scores (txn_id, step, score, label, latency_ms, scored_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        records,
    )
    conn.commit()


def post_predict(session: requests.Session, url: str, payload: dict) -> tuple[float, float]:
    """POST one payload and return (score, latency_ms), retrying on connection and 5xx errors."""
    while not _stop:
        start = time.perf_counter()
        try:
            resp = session.post(f"{url}/predict", json=payload, timeout=5)
        except requests.RequestException as exc:
            logger.warning("predict request failed: %s", exc)
            time.sleep(RETRY_SLEEP_SECONDS)
            continue
        latency_ms = (time.perf_counter() - start) * 1000.0
        if resp.status_code >= 500:
            logger.warning("predict returned %d", resp.status_code)
            time.sleep(RETRY_SLEEP_SECONDS)
            continue
        resp.raise_for_status()
        return float(resp.json()["score"]), latency_ms
    raise InterruptedError("shutdown requested")


def _request_stop(signum, frame) -> None:
    """Flag the main loop to stop."""
    global _stop
    _stop = True


def main() -> None:
    """Consume transactions, score them through the API, and store the results."""
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    api_url = os.environ.get("API_URL", "http://api:8000")
    conn = open_store(os.environ.get("SQLITE_PATH", "/data/stream.db"))
    consumer = KafkaConsumer(
        os.environ.get("TOPIC", "transactions"),
        bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092"),
        group_id=os.environ.get("GROUP_ID", "fraud-consumer"),
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        max_poll_records=int(os.environ.get("BATCH_SIZE", "100")),
        value_deserializer=lambda b: json.loads(b),
    )
    session = requests.Session()
    logger.info("consumer started")
    try:
        while not _stop:
            HEALTH_FILE.touch()
            polled = consumer.poll(timeout_ms=1000)
            rows = [msg.value for msgs in polled.values() for msg in msgs]
            if not rows:
                continue
            payloads = build_payloads(rows)
            out = []
            for row, payload in zip(rows, payloads, strict=True):
                score, latency_ms = post_predict(session, api_url, payload)
                scored_at = datetime.now(UTC).isoformat()
                out.append(
                    (row["txn_id"], row["step"], score, row["isFraud"], latency_ms, scored_at)
                )
            write_scores(conn, out)
            consumer.commit()
    except InterruptedError:
        logger.info("shutdown requested mid-batch, batch left uncommitted")
    finally:
        consumer.close()
        conn.close()
        HEALTH_FILE.unlink(missing_ok=True)
        logger.info("consumer stopped")


if __name__ == "__main__":
    main()
