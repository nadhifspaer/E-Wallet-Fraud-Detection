import json
import logging
import os
import time

import pyarrow.parquet as pq
from kafka import KafkaProducer

from src import config

logger = logging.getLogger("producer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def load_replay_rows(max_rows: int | None) -> list[dict]:
    """Load test-range rows ordered by (step, txn_id), limited to max_rows."""
    table = pq.read_table(config.DATA_PATH, filters=[("step", ">", config.CUTOFF_STEP)])
    table = table.sort_by([("step", "ascending"), ("txn_id", "ascending")])
    if max_rows:
        table = table.slice(0, max_rows)
    return table.to_pylist()


def main() -> None:
    """Replay test-range rows to Kafka at a configurable rate."""
    bootstrap = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
    topic = os.environ.get("TOPIC", "transactions")
    rate = float(os.environ.get("RATE", "200") or 0)
    max_rows = int(os.environ.get("MAX_ROWS") or 0) or None

    rows = load_replay_rows(max_rows)
    logger.info("replaying %d rows to %s, rate=%s/s", len(rows), topic, rate or "unlimited")
    producer = KafkaProducer(
        bootstrap_servers=bootstrap,
        acks="all",
        linger_ms=20,
        key_serializer=lambda k: str(k).encode(),
        value_serializer=lambda v: json.dumps(v).encode(),
    )
    start = time.monotonic()
    for i, row in enumerate(rows):
        if rate:
            delay = start + i / rate - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        producer.send(topic, key=row["txn_id"], value=row)
    producer.flush()
    producer.close()
    logger.info("replay complete, sent=%d", len(rows))


if __name__ == "__main__":
    main()
