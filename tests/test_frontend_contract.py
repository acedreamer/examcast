import json
from pathlib import Path
import re
import subprocess
import sys

from fastapi.testclient import TestClient

from app import app

AUDIT_SCRIPT = Path(
    r"C:\Users\Abishek\.gemini\antigravity-cli\skills\m3-expressive-architect\scripts\audit_m3_spec.py"
)
INDEX_PATH = Path("static/index.html")


def test_frontend_file_served_and_security_contracts():
    assert INDEX_PATH.is_file(), "static/index.html must exist"
    html = INDEX_PATH.read_text(encoding="utf-8")

    # FastAPI root serves index.html
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "DeepExamCast" in resp.text

    # Security & PDF.js 4.10.38 hardening
    assert "pdfjs-dist@4.10.38" in html
    assert "isEvalSupported: false" in html
    assert "URL.createObjectURL(blob)" in html
    assert "innerHTML" not in html

    # Compiled M3 Expressive Spring tokens & reduced-motion guard
    assert "--md-sys-motion-spring-fast-spatial:" in html
    assert "--md-sys-motion-spring-default-spatial:" in html
    assert "--md-sys-motion-spring-fast-effects:" in html
    assert "prefers-reduced-motion" in html

    # Key M3 elements E-01..E-23 hooks present
    for elem_id in [
        "sessionSelect",
        "deleteSessionBtn",
        "uploadBtn",
        "drawerToggleBtn",
        "scriptSheet",
        "fromPageInput",
        "toPageInput",
        "copyPromptBtn",
        "jsonInput",
        "voicePairSelect",
        "resynthesizeBtn",
        "appendBtn",
        "replaceBtn",
        "undoBtn",
        "genProgressBox",
        "drawerAlert",
        "prevLineBtn",
        "playPauseBtn",
        "nextLineBtn",
        "repeatLineBtn",
        "speedGroup",
        "lineScrubber",
        "autoScrollBtn",
        "pdfPane",
        "dialoguePane",
        "snackbarStack",
        "mobileTabs",
    ]:
        assert f'id="{elem_id}"' in html, f"Missing element id={elem_id}"

    # Zero side-stripe >1px borders, gradient text, or emojis
    assert not re.search(r"border-(?:left|right)\s*:\s*[2-9]px", html)
    assert "background-clip: text" not in html


def test_frontend_passes_deterministic_m3_code_audit(tmp_path: Path):
    html = INDEX_PATH.read_text(encoding="utf-8")

    token_match = re.search(r"<style[^>]*data-m3-tokens[^>]*>(.*?)</style>", html, re.DOTALL)
    comp_match = re.search(r"<style[^>]*data-m3-components[^>]*>(.*?)</style>", html, re.DOTALL)
    js_match = re.search(r"<script[^>]*data-m3-app[^>]*>(.*?)</script>", html, re.DOTALL)

    assert token_match and comp_match and js_match

    (tmp_path / "m3_tokens.css").write_text(token_match.group(1), encoding="utf-8")
    (tmp_path / "app_styles.css").write_text(comp_match.group(1), encoding="utf-8")
    (tmp_path / "app_script.js").write_text(js_match.group(1), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), "--code", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"audit_m3_spec.py failed:\n{proc.stdout}\n{proc.stderr}"
    report = json.loads(proc.stdout)
    assert report["passed"] is True
    assert report["errors"] == []
    assert report["warnings"] == []
