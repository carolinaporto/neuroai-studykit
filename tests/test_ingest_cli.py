import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ingest.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_parse_pdf_prints_readable_chunks_with_page_locator() -> None:
    result = _run_cli("parse", str(FIXTURES / "synthetic.pdf"))

    assert result.returncode == 0, result.stderr
    assert "chunk 0" in result.stdout
    assert "page=1" in result.stdout
    assert "Neurons and Membrane Potential" in result.stdout


def test_parse_pptx_json_output_round_trips() -> None:
    result = _run_cli("parse", "--json", str(FIXTURES / "synthetic.pptx"))

    assert result.returncode == 0, result.stderr
    chunks = json.loads(result.stdout)
    assert len(chunks) >= 1
    assert all("locators" in c and c["locators"] for c in chunks)


def test_unsupported_extension_fails_clearly() -> None:
    missing = FIXTURES / "synthetic.txt"
    result = _run_cli("parse", str(missing))

    assert result.returncode != 0
