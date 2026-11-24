import pytest

from src.config import DATA_PATH, META_PATH

SKIP_REASON = (
    "data/processed is missing, place the PaySim CSV at data/paysim_transactions.csv "
    "and run python -m src.prepare_data"
)


def pytest_configure(config):
    """Register the needs_data marker."""
    config.addinivalue_line("markers", "needs_data: test requires data/processed")


def pytest_collection_modifyitems(config, items):
    """Skip tests that need processed data when it is absent."""
    if META_PATH.exists() and DATA_PATH.exists():
        return
    skip = pytest.mark.skip(reason=SKIP_REASON)
    for item in items:
        if "needs_data" in item.keywords:
            item.add_marker(skip)
