import subprocess
import sys

from src.config import ROOT


def test_score_pipeline_imports_without_meta():
    code = (
        "import src.config as c\n"
        "from pathlib import Path\n"
        "c.META_PATH = Path('/nonexistent/meta.json')\n"
        "import src.score_pipeline\n"
        "print('ok')\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], check=False, cwd=ROOT, capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    assert "ok" in out.stdout
