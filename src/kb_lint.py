#!/usr/bin/env python3
"""kb_lint.py — Karpathy Stage 6 Health-Checks für ~/kb/.

M40-Bauteil. SSOT: ~/.claude/skills/kb-lint/SKILL.md.

MVP Welle W78-A: Kat A (Frontmatter-Drift), Kat C (Cross-Ref-Brüche),
Kat F (Stale-Reviews). Kat B/D/E sind Stubs für W79+.

Anti-Pattern-Vakzinen:
- A33 KEIN-MOCK: Wenn .provenance/quarantine.json fehlt → leeres Result,
  nie hardcoded Fake-Findings.
- Regel 5 (Aufräumen): tempdir-Tests räumen ihr eigenes tmp.
- ISC2 CC: read-only Tool (Confidentiality preserved, Integrity unchanged).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Optional


# Pflicht-Frontmatter-Felder pro Kat A (DOCU-VERSIONING-LOCK Regel 17)
FRONTMATTER_REQUIRED = ("stand", "mutability", "classification")

# Cross-Ref-Pattern: [[wiki/foo.md]], [[kb/ops/bar.md]], cross-ref: kb/ops/baz.md,
# cross-ref: ~/kb/ops/x.md
WIKILINK_RE = re.compile(r"\[\[([^\]]+\.md)\]\]")
CROSSREF_RE = re.compile(
    r"^\s*cross[-_]?ref\s*:\s*([~A-Za-z0-9_./\-]+\.md)",
    re.IGNORECASE | re.MULTILINE,
)

# Default-Scope (Spec)
DEFAULT_SCAN_DIRS = ("ops", "projects", "wiki")


@dataclass
class Finding:
    kat: str
    path: str
    detail: str
    severity: str = "info"  # info | warn | error


@dataclass
class LintReport:
    started: str
    kb_root: str
    kat_a: List[Finding] = field(default_factory=list)
    kat_b: List[Finding] = field(default_factory=list)  # PII — Stub W79+
    kat_c: List[Finding] = field(default_factory=list)
    kat_d: List[Finding] = field(default_factory=list)  # Quarantine — Stub
    kat_e: List[Finding] = field(default_factory=list)  # Suggested — Stub
    kat_f: List[Finding] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def total(self) -> int:
        return sum(
            len(getattr(self, f"kat_{k}"))
            for k in ("a", "b", "c", "d", "e", "f")
        )

    def to_dict(self) -> dict:
        out = {
            "started": self.started,
            "kb_root": self.kb_root,
            "errors": self.errors,
            "total_findings": self.total(),
        }
        for k in ("a", "b", "c", "d", "e", "f"):
            out[f"kat_{k}"] = [asdict(f) for f in getattr(self, f"kat_{k}")]
        return out


# ---------------- Frontmatter-Parser ----------------

def parse_frontmatter(text: str) -> Optional[dict]:
    """Mini-YAML-Parser: liest --- ... --- Block am File-Anfang.

    Bewusst stdlib-only — PyYAML wäre overkill für key: value Frontmatter.
    Unterstützt: simple key: value, ignoriert komplexe Strukturen.
    """
    if not text.startswith("---"):
        return None
    lines = text.split("\n")
    if len(lines) < 2:
        return None
    # Finde schließendes ---
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return None
    out: dict = {}
    for raw in lines[1:end_idx]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            continue
        key, _, val = raw.partition(":")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


# ---------------- Kat A — Frontmatter-Drift ----------------

def kat_a_frontmatter_drift(
    kb_root: Path, scan_dirs: Iterable[str] = DEFAULT_SCAN_DIRS
) -> List[Finding]:
    findings: List[Finding] = []
    for sub in scan_dirs:
        base = kb_root / sub
        if not base.exists():
            continue
        for md in base.rglob("*.md"):
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError) as exc:
                findings.append(
                    Finding(
                        kat="A",
                        path=str(md),
                        detail=f"read-error: {exc}",
                        severity="error",
                    )
                )
                continue
            fm = parse_frontmatter(text)
            if fm is None:
                findings.append(
                    Finding(
                        kat="A",
                        path=str(md),
                        detail="no frontmatter block",
                        severity="warn",
                    )
                )
                continue
            missing = [k for k in FRONTMATTER_REQUIRED if k not in fm]
            if missing:
                findings.append(
                    Finding(
                        kat="A",
                        path=str(md),
                        detail=f"missing fields: {', '.join(missing)}",
                        severity="warn",
                    )
                )
    return findings


# ---------------- Kat C — Cross-Ref-Brüche ----------------

def _resolve_cross_ref(raw_ref: str, source_md: Path, kb_root: Path) -> Path:
    """Resolviert relative/abs/~-Pfade zu konkretem Path-Objekt."""
    raw_ref = raw_ref.strip()
    if raw_ref.startswith("~"):
        return Path(raw_ref).expanduser()
    if raw_ref.startswith("/"):
        return Path(raw_ref)
    # kb/... oder wiki/... interpretieren wir relativ zu kb_root
    if raw_ref.startswith("kb/"):
        return kb_root / raw_ref[len("kb/"):]
    if raw_ref.startswith(("wiki/", "ops/", "projects/", "raw/", "personal/")):
        return kb_root / raw_ref
    # Fallback: relativ zu Source-File
    return (source_md.parent / raw_ref).resolve()


def kat_c_cross_ref_breaks(
    kb_root: Path, scan_dirs: Iterable[str] = DEFAULT_SCAN_DIRS
) -> List[Finding]:
    findings: List[Finding] = []
    for sub in scan_dirs:
        base = kb_root / sub
        if not base.exists():
            continue
        for md in base.rglob("*.md"):
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue
            refs: List[str] = []
            refs.extend(WIKILINK_RE.findall(text))
            refs.extend(CROSSREF_RE.findall(text))
            for ref in refs:
                target = _resolve_cross_ref(ref, md, kb_root)
                if not target.exists():
                    findings.append(
                        Finding(
                            kat="C",
                            path=str(md),
                            detail=f"broken ref → {ref}",
                            severity="warn",
                        )
                    )
    return findings


# ---------------- Kat F — Stale Reviews ----------------

def _parse_review_due(val: str) -> Optional[date]:
    val = val.strip()
    # Akzeptiere YYYY-MM-DD oder volle ISO
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(val[: len(fmt) + 2], fmt).date()
        except ValueError:
            continue
    return None


def kat_f_stale_reviews(
    kb_root: Path,
    scan_dirs: Iterable[str] = DEFAULT_SCAN_DIRS,
    today: Optional[date] = None,
) -> List[Finding]:
    if today is None:
        today = date.today()
    findings: List[Finding] = []
    for sub in scan_dirs:
        base = kb_root / sub
        if not base.exists():
            continue
        for md in base.rglob("*.md"):
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue
            fm = parse_frontmatter(text)
            if not fm or "review-due" not in fm:
                continue
            due = _parse_review_due(fm["review-due"])
            if due and due < today:
                findings.append(
                    Finding(
                        kat="F",
                        path=str(md),
                        detail=f"review-due {due.isoformat()} < {today.isoformat()}",
                        severity="warn",
                    )
                )
    return findings


# ---------------- Stubs Kat B/D/E (W79+) ----------------

def kat_b_pii_scan_stub(kb_root: Path) -> List[Finding]:
    """TODO W79+: Regex+LLM-Scan. Stub liefert leere Liste (kein Mock!)."""
    return []


def kat_d_quarantine_cascade_stub(kb_root: Path) -> List[Finding]:
    """TODO W79+: liest .provenance/quarantine.json. Wenn nicht vorhanden → leer."""
    qpath = kb_root / ".provenance" / "quarantine.json"
    if not qpath.exists():
        return []
    # Vorerst nur Existenz melden — echte Cascade-Logik in W79+
    return [
        Finding(
            kat="D",
            path=str(qpath),
            detail="quarantine.json existiert (Cascade-Analyse W79+)",
            severity="info",
        )
    ]


def kat_e_suggested_concepts_stub(kb_root: Path) -> List[Finding]:
    """TODO W79+: aie-semantic-search-Clustering. Stub leer."""
    return []


# ---------------- Runner ----------------

def run_lint(
    kb_root: Path,
    scan_dirs: Iterable[str] = DEFAULT_SCAN_DIRS,
    today: Optional[date] = None,
) -> LintReport:
    report = LintReport(
        started=datetime.now().isoformat(timespec="seconds"),
        kb_root=str(kb_root),
    )
    if not kb_root.exists():
        report.errors.append(f"kb_root not found: {kb_root}")
        return report
    try:
        report.kat_a = kat_a_frontmatter_drift(kb_root, scan_dirs)
        report.kat_c = kat_c_cross_ref_breaks(kb_root, scan_dirs)
        report.kat_f = kat_f_stale_reviews(kb_root, scan_dirs, today=today)
        report.kat_b = kat_b_pii_scan_stub(kb_root)
        report.kat_d = kat_d_quarantine_cascade_stub(kb_root)
        report.kat_e = kat_e_suggested_concepts_stub(kb_root)
    except Exception as exc:  # noqa: BLE001
        report.errors.append(f"runner-exception: {type(exc).__name__}: {exc}")
    return report


# ---------------- Output-Formatter ----------------

def format_markdown(report: LintReport) -> str:
    lines = [
        f"# kb-lint-Lauf {report.started}",
        "",
        f"- kb_root: `{report.kb_root}`",
        f"- total findings: {report.total()}",
        "",
    ]
    sections = [
        ("A", "Frontmatter-Drift (M32)"),
        ("B", "PII-Scan (Stub W79+)"),
        ("C", "Cross-Ref-Brüche"),
        ("D", "Quarantine-Cascades (Stub W79+)"),
        ("E", "Suggested Concepts (Stub W79+)"),
        ("F", "Stale Reviews"),
    ]
    for code, title in sections:
        kat = getattr(report, f"kat_{code.lower()}")
        lines.append(f"## Kat {code} — {title}")
        if not kat:
            lines.append("- (keine Befunde)")
        else:
            for f in kat:
                lines.append(f"- [{f.severity}] `{f.path}` — {f.detail}")
        lines.append("")
    if report.errors:
        lines.append("## Runner-Errors")
        for err in report.errors:
            lines.append(f"- {err}")
        lines.append("")
    return "\n".join(lines)


# ---------------- CLI ----------------

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="kb-lint",
        description="Karpathy Stage 6 Health-Checks für ~/kb/ (MVP W78-A).",
    )
    p.add_argument(
        "--kb-root",
        default=str(Path.home() / "kb"),
        help="Root-Verzeichnis (default: ~/kb).",
    )
    p.add_argument(
        "--scan-dirs",
        nargs="+",
        default=list(DEFAULT_SCAN_DIRS),
        help=f"Subdirs (default: {' '.join(DEFAULT_SCAN_DIRS)}).",
    )
    p.add_argument(
        "--markdown",
        action="store_true",
        help="Markdown-Report statt JSON ausgeben.",
    )
    p.add_argument(
        "--output",
        help="Datei zum Schreiben (default: stdout).",
    )
    args = p.parse_args(argv)

    kb_root = Path(args.kb_root).expanduser()
    report = run_lint(kb_root, scan_dirs=args.scan_dirs)

    if args.markdown:
        out = format_markdown(report)
    else:
        out = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        print(out)

    if report.errors:
        return 2
    if report.total() > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
