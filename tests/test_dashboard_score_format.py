import pytest

from dashboard.score_format import format_score_six_decimals


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.0, "<0.000001"),
        (3.1e-5, "0.000031"),
        (0.5, "0.500000"),
        (0.9775, "0.977500"),
        (1.0, "1.000000"),
    ],
)
def test_format_score_six_decimals(value, expected):
    assert format_score_six_decimals(value) == expected
