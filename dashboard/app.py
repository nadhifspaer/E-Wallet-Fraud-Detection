import importlib
import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MODES = {"cloud": "dashboard.cloud_mode", "local": "dashboard.local_mode"}

st.set_page_config(page_title="Fraud detection", layout="wide")
mode = os.environ.get("APP_MODE", "cloud")
if mode not in MODES:
    st.error(f"APP_MODE must be one of {sorted(MODES)}, got {mode!r}")
    st.stop()
importlib.import_module(MODES[mode]).render()
