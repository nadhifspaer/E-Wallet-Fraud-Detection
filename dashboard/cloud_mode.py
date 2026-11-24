import pandas as pd
import streamlit as st

from dashboard.score_format import format_score_six_decimals
from src.config import FEATURE_LIST, SAMPLE_PATH
from src.explainability import explain
from src.score_pipeline import score

LABELS = {0: "legitimate", 1: "fraud"}


@st.cache_data
def load_sample() -> pd.DataFrame:
    """Load the sample feature rows."""
    return pd.read_csv(SAMPLE_PATH)


def render() -> None:
    """Render the in-process scoring view."""
    st.title("Transaction fraud score")
    sample = load_sample().set_index("txn_id", drop=False)
    txn_id = st.selectbox(
        "Sample transaction",
        sample.index,
        format_func=lambda t: f"{t} ({LABELS[int(sample.at[t, 'isFraud'])]})",
    )
    row = sample.loc[txn_id]
    features = pd.DataFrame([row[FEATURE_LIST].astype("float64")])
    value = float(score(features)[0])
    left, right = st.columns(2)
    with left:
        st.metric("Score", format_score_six_decimals(value))
        st.caption("Model output, not a calibrated probability.")
        st.write(f"True label: {LABELS[int(row['isFraud'])]}")
        st.dataframe(features.T.rename(columns={features.index[0]: "value"}))
    with right:
        st.subheader("SHAP contributions")
        shap_values = explain(features)[0]
        st.bar_chart(pd.Series(shap_values, index=FEATURE_LIST, name="SHAP value"))
