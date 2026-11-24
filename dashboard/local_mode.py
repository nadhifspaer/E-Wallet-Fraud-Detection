import os
import sqlite3
from datetime import UTC, datetime, timedelta

import pandas as pd
import streamlit as st

from dashboard.score_format import format_score_six_decimals

REFRESH_SECONDS = 2
RATE_WINDOW_SECONDS = 10
FEED_ROWS = 50


def open_readonly(path: str) -> sqlite3.Connection:
    """Open the SQLite store through a read-only URI connection."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
    conn.execute("PRAGMA query_only=ON")
    return conn


def read_state(conn: sqlite3.Connection) -> tuple[int, int, pd.DataFrame]:
    """Return total rows, rows in the recent window, and the latest feed rows."""
    cutoff = (datetime.now(UTC) - timedelta(seconds=RATE_WINDOW_SECONDS)).isoformat()
    total = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
    recent = conn.execute("SELECT COUNT(*) FROM scores WHERE scored_at >= ?", (cutoff,)).fetchone()[0]
    feed = pd.read_sql_query(
        "SELECT txn_id, step, score, label, latency_ms, scored_at FROM scores "
        "ORDER BY scored_at DESC, txn_id DESC LIMIT ?",
        conn,
        params=(FEED_ROWS,),
    )
    return total, recent, feed


@st.fragment(run_every=REFRESH_SECONDS)
def live_feed() -> None:
    """Show the live feed and refresh it on a timer."""
    path = os.environ.get("SQLITE_PATH", "/data/stream.db")
    try:
        conn = open_readonly(path)
        try:
            total, recent, feed = read_state(conn)
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        st.info(f"Waiting for the stream store: {exc}")
        return
    left, right = st.columns(2)
    left.metric("Total rows", total)
    right.metric(f"Rows per second (last {RATE_WINDOW_SECONDS} s)", f"{recent / RATE_WINDOW_SECONDS:.1f}")
    shown = feed.assign(score=feed["score"].map(format_score_six_decimals))
    st.dataframe(shown, hide_index=True, use_container_width=True)
    st.caption("Score is the model output, not a calibrated probability.")


def render() -> None:
    """Render the live stream view."""
    st.title("Live transaction feed")
    live_feed()
