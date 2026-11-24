def format_score_six_decimals(value: float) -> str:
    if value < 0.000001:
        return "<0.000001"
    return f"{value:.6f}"
