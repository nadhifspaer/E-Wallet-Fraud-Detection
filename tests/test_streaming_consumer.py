import json
import subprocess
import sys

import pandas as pd

from src.config import FEATURE_LIST, ROOT
from streaming.consumer import build_payloads, open_store, write_scores


def _rows() -> list[dict]:
    base = {
        "txn_id": 1,
        "step": 600,
        "type": "TRANSFER",
        "amount": 100.0,
        "nameOrig": "C1",
        "oldbalanceOrg": 500.0,
        "newbalanceOrig": 400.0,
        "nameDest": "C2",
        "oldbalanceDest": 0.0,
        "newbalanceDest": 100.0,
        "isFraud": 1,
        "isFlaggedFraud": 0,
    }
    zero = {**base, "txn_id": 2, "oldbalanceOrg": 0.0}
    return [base, zero]


def test_payload_has_exactly_feature_list_keys():
    for payload in build_payloads(_rows()):
        assert set(payload) == set(FEATURE_LIST)
        assert "isFraud" not in payload


def test_missing_drain_ratio_serializes_as_null():
    payloads = build_payloads(_rows())
    assert payloads[0]["orig_drain_ratio"] == 0.2
    assert payloads[1]["orig_drain_ratio"] is None
    text = json.dumps(payloads[1], allow_nan=False)
    assert '"orig_drain_ratio": null' in text


def test_duplicate_txn_id_leaves_one_row(tmp_path):
    conn = open_store(str(tmp_path / "stream.db"))
    rec = (7, 600, 0.5, 1, 3.2, "2026-01-01T00:00:00+00:00")
    write_scores(conn, [rec])
    write_scores(conn, [(7, 600, 0.9, 0, 9.9, "2026-01-02T00:00:00+00:00")])
    rows = pd.read_sql("SELECT * FROM scores", conn)
    assert len(rows) == 1
    assert rows.loc[0, "score"] == 0.5
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_consumer_imports_without_meta():
    code = (
        "import src.config as c\n"
        "from pathlib import Path\n"
        "c.META_PATH = Path('/nonexistent/meta.json')\n"
        "import streaming.consumer as m\n"
        "m.build_payloads([{'step': 1, 'type': 'CASH_IN', 'amount': 1.0,"
        " 'oldbalanceOrg': 2.0, 'oldbalanceDest': 3.0}])\n"
        "print('ok')\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], check=False, cwd=ROOT, capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    assert "ok" in out.stdout
