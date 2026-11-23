import ast
from pathlib import Path

BANNED = {"requests", "kafka", "sqlite3", "httpx", "urllib", "urllib3", "http", "aiohttp"}
CLOUD_MODE = Path(__file__).resolve().parents[1] / "dashboard" / "cloud_mode.py"


def _imported_roots() -> set[str]:
    tree = ast.parse(CLOUD_MODE.read_text())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_cloud_mode_has_no_network_or_store_imports():
    assert not _imported_roots() & BANNED
