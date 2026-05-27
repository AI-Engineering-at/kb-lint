"""Unit-Tests für kb_lint (W78-A MVP).

Pro Kat 2-3 Tests + Backwards-Compat Read-Only-Run gegen echtes ~/kb/.
Anti-Pattern A33: keine Mocks außerhalb tempdir-Fixtures.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

# Repo-Layout: src/kb_lint.py → in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import kb_lint  # noqa: E402


# ---------------- Fixtures ----------------

@pytest.fixture()
def kb_tmp(tmp_path: Path) -> Path:
    """Erzeugt minimales ~/kb/-Layout in tmpdir."""
    for sub in ("ops", "projects", "wiki", "raw"):
        (tmp_path / sub).mkdir()
    return tmp_path


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


# ---------------- Frontmatter-Parser ----------------

def test_parse_frontmatter_complete():
    text = "---\nstand: 2026-05-27\nmutability: append-only\nclassification: internal\n---\n# Body"
    fm = kb_lint.parse_frontmatter(text)
    assert fm == {
        "stand": "2026-05-27",
        "mutability": "append-only",
        "classification": "internal",
    }


def test_parse_frontmatter_missing_returns_none():
    assert kb_lint.parse_frontmatter("# Just body\nNo frontmatter") is None


def test_parse_frontmatter_unterminated():
    # Öffnendes --- aber kein schließendes
    assert kb_lint.parse_frontmatter("---\nstand: 2026-05-27\nno end\n") is None


# ---------------- Kat A — Frontmatter-Drift ----------------

def test_kat_a_missing_fields(kb_tmp: Path):
    _write(
        kb_tmp / "ops" / "incomplete.md",
        "---\nstand: 2026-05-27\n---\n# Body",
    )
    findings = kb_lint.kat_a_frontmatter_drift(kb_tmp)
    assert len(findings) == 1
    assert "mutability" in findings[0].detail
    assert "classification" in findings[0].detail


def test_kat_a_no_frontmatter(kb_tmp: Path):
    _write(kb_tmp / "wiki" / "naked.md", "# Just a heading\n")
    findings = kb_lint.kat_a_frontmatter_drift(kb_tmp)
    assert len(findings) == 1
    assert findings[0].detail == "no frontmatter block"


def test_kat_a_complete_passes(kb_tmp: Path):
    _write(
        kb_tmp / "projects" / "ok.md",
        "---\nstand: 2026-05-27\nmutability: mutable\nclassification: internal\n---\n# Body",
    )
    assert kb_lint.kat_a_frontmatter_drift(kb_tmp) == []


# ---------------- Kat C — Cross-Ref-Brüche ----------------

def test_kat_c_broken_wikilink(kb_tmp: Path):
    _write(
        kb_tmp / "ops" / "src.md",
        "---\nstand: 2026-05-27\n---\nSee [[wiki/does-not-exist.md]] for more.",
    )
    findings = kb_lint.kat_c_cross_ref_breaks(kb_tmp)
    assert len(findings) == 1
    assert "does-not-exist.md" in findings[0].detail


def test_kat_c_broken_crossref_field(kb_tmp: Path):
    _write(
        kb_tmp / "ops" / "src.md",
        "---\nstand: 2026-05-27\ncross-ref: kb/ops/ghost.md\n---\nBody",
    )
    findings = kb_lint.kat_c_cross_ref_breaks(kb_tmp)
    assert any("ghost.md" in f.detail for f in findings)


def test_kat_c_valid_ref_passes(kb_tmp: Path):
    _write(kb_tmp / "wiki" / "target.md", "# Target")
    _write(
        kb_tmp / "ops" / "src.md",
        "---\nstand: 2026-05-27\n---\nSee [[wiki/target.md]].",
    )
    findings = kb_lint.kat_c_cross_ref_breaks(kb_tmp)
    assert findings == []


# ---------------- Kat F — Stale Reviews ----------------

def test_kat_f_overdue(kb_tmp: Path):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _write(
        kb_tmp / "ops" / "stale.md",
        f"---\nstand: 2026-01-01\nreview-due: {yesterday}\n---\nBody",
    )
    findings = kb_lint.kat_f_stale_reviews(kb_tmp)
    assert len(findings) == 1
    assert yesterday in findings[0].detail


def test_kat_f_future_passes(kb_tmp: Path):
    future = (date.today() + timedelta(days=30)).isoformat()
    _write(
        kb_tmp / "ops" / "fresh.md",
        f"---\nstand: 2026-05-27\nreview-due: {future}\n---\nBody",
    )
    assert kb_lint.kat_f_stale_reviews(kb_tmp) == []


def test_kat_f_no_review_due_skipped(kb_tmp: Path):
    _write(
        kb_tmp / "ops" / "noreview.md",
        "---\nstand: 2026-05-27\n---\nBody",
    )
    assert kb_lint.kat_f_stale_reviews(kb_tmp) == []


# ---------------- Stubs liefern keine Mocks ----------------

def test_kat_b_stub_returns_empty(kb_tmp: Path):
    assert kb_lint.kat_b_pii_scan_stub(kb_tmp) == []


def test_kat_d_quarantine_absent_returns_empty(kb_tmp: Path):
    assert kb_lint.kat_d_quarantine_cascade_stub(kb_tmp) == []


def test_kat_d_quarantine_present(kb_tmp: Path):
    qpath = kb_tmp / ".provenance" / "quarantine.json"
    qpath.parent.mkdir()
    qpath.write_text('{"entries": []}', encoding="utf-8")
    findings = kb_lint.kat_d_quarantine_cascade_stub(kb_tmp)
    assert len(findings) == 1
    assert "quarantine.json" in findings[0].detail


# ---------------- Runner + Formatter ----------------

def test_run_lint_full(kb_tmp: Path):
    _write(kb_tmp / "ops" / "missing.md", "# no frontmatter")
    report = kb_lint.run_lint(kb_tmp)
    assert report.total() >= 1
    d = report.to_dict()
    assert d["kb_root"] == str(kb_tmp)
    assert "kat_a" in d


def test_run_lint_missing_root_records_error(tmp_path: Path):
    ghost = tmp_path / "does-not-exist"
    report = kb_lint.run_lint(ghost)
    assert report.errors
    assert "not found" in report.errors[0]


def test_format_markdown_contains_sections(kb_tmp: Path):
    report = kb_lint.run_lint(kb_tmp)
    md = kb_lint.format_markdown(report)
    for code in ("Kat A", "Kat B", "Kat C", "Kat D", "Kat E", "Kat F"):
        assert code in md


# ---------------- CLI ----------------

def test_cli_json_output(kb_tmp: Path, capsys):
    rc = kb_lint.main(["--kb-root", str(kb_tmp)])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["kb_root"] == str(kb_tmp)
    # Leeres kb → exit 0
    assert rc == 0


def test_cli_markdown_output(kb_tmp: Path, capsys):
    _write(kb_tmp / "ops" / "f.md", "# no fm")
    rc = kb_lint.main(["--kb-root", str(kb_tmp), "--markdown"])
    captured = capsys.readouterr()
    assert "# kb-lint-Lauf" in captured.out
    assert rc == 1  # findings exist


def test_cli_output_file(kb_tmp: Path, tmp_path: Path):
    out_file = tmp_path / "report.json"
    rc = kb_lint.main(
        ["--kb-root", str(kb_tmp), "--output", str(out_file)]
    )
    assert rc == 0
    data = json.loads(out_file.read_text())
    assert data["kb_root"] == str(kb_tmp)


# ---------------- Backwards-Compat: echtes ~/kb/ ----------------

def test_real_kb_runs_without_runner_error():
    """Read-only Lauf gegen echtes ~/kb/. Darf findings haben,
    aber keine Runner-Exceptions."""
    kb = Path.home() / "kb"
    if not kb.exists():
        pytest.skip("kein ~/kb auf dieser Maschine")
    report = kb_lint.run_lint(kb)
    # Errors-Liste darf nur 'not found' enthalten (sollte aber leer sein)
    assert not any("exception" in e.lower() for e in report.errors), report.errors
