#!/usr/bin/env python3
"""kb_lint.py — Karpathy Stage 6 Health-Checks für ~/kb/.

M40-Bauteil. SSOT: ~/.claude/skills/kb-lint/SKILL.md.

MVP Welle W78-A: Kat A (Frontmatter-Drift), Kat C (Cross-Ref-Brüche),
Kat F (Stale-Reviews). Kat B seit 2026-08-10 echt; D/E sind noch Stubs.

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
import subprocess
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


# ---------------- Nicht-prüfbare Dateien (2026-08-10) ----------------
# Anlass: von 15 Restbefunden am 2026-08-10 waren 13 Artefakte dieses Prüfers und nicht
# Mängel des Substrats — 8 Dateien, die `.gitignore` bewusst fängt (`*token*`, `*credential*`,
# `*secret*`), 3 generierte pytest-Caches, 2 Verweise, die von der kb-Wurzel aus auflösen.
# Ein Bericht mit hoher Falsch-Positiv-Quote erzieht seinen Leser zum Wegsehen; genau so sind
# auf swarm1 sechs Tage lang 256→302 Befunde ungelesen geblieben.
#
# Die Ausnahme wird GEZÄHLT und im Bericht genannt. Eine stille Ausnahme wäre schlimmer als
# der Falschbefund, weil niemand mehr sieht, dass etwas nicht geprüft wurde.
UEBERSPRUNGEN: dict = {}
_IGNORIERT_CACHE: dict = {}


def _gitignoriert(kb_root: Path) -> set:
    """Alle .md, die git bewusst ignoriert — EIN Aufruf je kb_root, nicht einer je Datei.

    Ohne git gibt es hier KEINE Aussage, und die leere Menge heißt deshalb
    „nichts ausgenommen" (alles wird geprüft) und nicht „nichts ignoriert".
    Die sichere Richtung ist die, die keine Ausnahme erfindet.
    """
    schluessel = str(kb_root)
    if schluessel in _IGNORIERT_CACHE:
        return _IGNORIERT_CACHE[schluessel]
    treffer: set = set()
    try:
        alle = [str(p) for p in kb_root.rglob("*.md")]
        if alle:
            r = subprocess.run(
                ["git", "-C", str(kb_root), "check-ignore", "--stdin"],
                input="\n".join(alle), capture_output=True, text=True, timeout=90,
            )
            treffer = {str(Path(z).resolve()) for z in r.stdout.splitlines() if z.strip()}
    except Exception:  # noqa: BLE001 — kein git, kein Timeout-Budget: keine Ausnahme
        treffer = set()
    _IGNORIERT_CACHE[schluessel] = treffer
    return treffer


def nicht_pruefbar(md: Path, kb_root: Path) -> Optional[str]:
    """Grund, warum diese Datei die Pflichten nicht schulden kann — oder None."""
    s = str(md)
    if ".pytest_cache" in s:
        return "generiertes Artefakt (pytest)"
    if "/archiv/" in s or "/archive/" in s:
        return "eingefrorenes Archiv — byte-identisch, per Definition ohne Pflege"
    if str(md.resolve()) in _gitignoriert(kb_root):
        return "von git bewusst ignoriert — kann kein Commit-Datum haben"
    return None


def _ueberspringen(md: Path, kb_root: Path) -> bool:
    grund = nicht_pruefbar(md, kb_root)
    if grund is None:
        return False
    UEBERSPRUNGEN.setdefault(grund, []).append(str(md))
    return True


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
    kat_b: List[Finding] = field(default_factory=list)  # PII — echt seit 2026-08-10
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
    # Toleriere HTML-Kommentar-gewrapptes Frontmatter (<!--\n---\n...\n---\n-->),
    # Konvention der Always-Loaded-Files (SYSTEM-FACTS etc.) — Tooling-Haertung 2026-05-31.
    t = text.lstrip()
    if t.startswith("<!--"):
        t = t[4:].lstrip()
    if not t.startswith("---"):
        return None
    text = t
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
            # Tooling-Haertung 2026-05-31: rotierende Watcher-Outputs (launchd ueberschreibt taeglich)
            # + eingefrorene Klassifikations-Backup-Snapshots (DOCU-VERSIONING-LOCK Tier-4) = kein Drift.
            if _ueberspringen(md, kb_root):
                continue
            if md.name.endswith(("-daily.md", "-latest.md")) or ".classification-sweep-backup" in str(md):
                continue
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
    # Fallback: relativ zu Source-File — und wenn das nicht existiert, gegen die kb-Wurzel.
    # Anlass 2026-08-10: `cross-ref: MASTER-PLAN.md` in ops/ wurde als Bruch gemeldet, obwohl
    # `kb/MASTER-PLAN.md` existiert. Dasselbe bei NORDSTERN.md. Zwei von 15 Restbefunden waren
    # allein diese eine fehlende Zeile.
    relativ = (source_md.parent / raw_ref).resolve()
    if relativ.exists():
        return relativ
    von_wurzel = (kb_root / raw_ref).resolve()
    return von_wurzel if von_wurzel.exists() else relativ


def kat_c_cross_ref_breaks(
    kb_root: Path, scan_dirs: Iterable[str] = DEFAULT_SCAN_DIRS
) -> List[Finding]:
    findings: List[Finding] = []
    for sub in scan_dirs:
        base = kb_root / sub
        if not base.exists():
            continue
        for md in base.rglob("*.md"):
            if _ueberspringen(md, kb_root):
                continue
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
            if _ueberspringen(md, kb_root):
                continue
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

# ---------------- Kat B — PII-Scan (2026-08-10, ersetzt den Stub) ----------------
#
# WARUM DIESE KATEGORIE ZUERST DRAN WAR
# `kb-compile` und `kb-fileback` führen den PII-Scan beide als Pflicht-Vorbedingung.
# Bis heute war er `return []` mit dem Docstring „Stub liefert leere Liste (kein
# Mock!)" — ehrlich deklariert und als Vorbedingung trotzdem wertlos: wer ihn
# abfragt, bekommt immer grün. Gemessen am 2026-08-10 gegen den Mac-Bestand:
# kat_b 0 Befunde, so wie an jedem Tag davor.
#
# WAS DIESER SCANNER FINDET — UND WAS NICHT
# Er findet STRUKTURIERTE Kennungen: Mailadressen, IBAN, österreichische
# Sozialversicherungsnummern, Telefonnummern, Geburtsdaten im Kontext. Er findet
# **keine Namen**, keine Anschriften in Fließtext und nichts, was erst im
# Zusammenhang personenbeziehbar wird.
#
# Diese Grenze steht IM BERICHT, nicht nur hier. Anlass ist ein gemessener
# Hausbefund: der Geheimnis-Detektor findet Zufallsstrings, aber kein
# menschliches Passwort (1 von 5 erkannt). Sein „kein Fund" ist kein Freispruch —
# und dieser hier ist es genauso wenig. Ein Nullbefund, der seine Blindstellen
# verschweigt, ist gefährlicher als gar keiner.

# Synthetische Kanarienvögel. Jeder Ausdruck muss seinen eigenen finden, sonst
# meldet der Scanner sich selbst als kaputt statt „keine Befunde" zu sagen.
_PII_KANARIE = (
    "kontakt: erika.mustermann@beispiel.invalid | "
    "IBAN AT61 1904 3002 3457 3201 | "
    "SVNR 1234 010180 | "
    "Tel +43 660 1234567 | "
    "geboren am 01.01.1980"
)

_PII_MUSTER: List[tuple] = [
    ("Mailadresse", "warn",
     re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    # Ländercode aus der echten IBAN-Liste, nicht [A-Z]{2}. Der erste Lauf am
    # 2026-08-10 meldete sonst `QQ0…` aus WORKFLOW-INVENTORY-N8N.md:90 als IBAN —
    # in Wahrheit ein n8n-Workflow-Kennzeichen. Ein Wächter, dessen lautester
    # Befund falsch ist, erzieht seinen Leser zum Wegsehen.
    ("IBAN", "error",
     re.compile(r"\b(?:AT|BE|BG|CH|CY|CZ|DE|DK|EE|ES|FI|FR|GB|GR|HR|HU|IE|IS|IT|"
                r"LI|LT|LU|LV|MC|MT|NL|NO|PL|PT|RO|SE|SI|SK|SM)"
                r"\d{2}(?:[ ]?[A-Za-z0-9]{4}){3,7}\b")),
    ("Sozialversicherungsnummer (AT)", "error",
     re.compile(r"\b\d{4}[ ]?(?:0[1-9]|[12]\d|3[01])(?:0[1-9]|1[0-2])\d{2}\b")),
    ("Telefonnummer", "warn",
     re.compile(r"(?:\+|00)(?:43|49|41)[ /-]?\d[\d /-]{6,}\d")),
    ("Geburtsdatum im Kontext", "error",
     re.compile(r"\b(?:geb(?:oren)?\.?|DOB|date of birth)\s*(?:am\s*)?[:\-]?\s*"
                r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", re.I)),
]

# Bewusst nicht gemeldet — und die Zahl der Unterdrückungen steht im Bericht.
# Eine stille Erlaubnisliste ist dieselbe Krankheit wie eine Attrappe: von außen
# sieht beides aus wie „nichts gefunden".
_PII_ERLAUBT = re.compile(
    r"noreply@|no-reply@|@example\.|@beispiel\.invalid|\.invalid\b"
    r"|@localhost|@aie\.local"
    r"|austria\.jf@protonmail\.com"          # Joes eigene, bewusst im Substrat
    r"|[a-z0-9._%+-]+@(?:users\.)?noreply\."
    # Eigene Geschäftsadressen. Sie machen 106 von 110 Treffern des ersten Laufs
    # aus (40 eindeutige, davon kontakt@ 22x, joe@ 14x). Sie hier NICHT zu
    # unterdrücken hiesse, den Bericht unlesbar zu machen und damit wertlos —
    # sechs Tage lang blieben auf swarm1 256→302 Befunde ungelesen, weil genau
    # das passiert war. Die Zahl der Unterdrückungen steht im Bericht.
    r"|@ai-engineering\.at|@zugangsweg\.at|@foxlabs\.at|@aie\.at"
    # Interne Namensräume. `root@lt-homelap-legion.nb.aie` sieht für den
    # Ausdruck wie eine Mailadresse aus und ist ein SSH-Ziel. Diese TLDs
    # existieren im öffentlichen DNS nicht — dorthin kann niemand schreiben.
    r"|@[\w.-]+\.(?:nb\.aie|aie|local|lan|internal|invalid)\b",
    re.I,
)

# Verzeichnisse, in denen strukturierte Kennungen erwartbar und legitim sind.
_PII_AUSGENOMMEN = ("tests/", "/tests/", ".provenance/")


def kat_b_pii_scan(kb_root: Path, scan_dirs: Iterable[str] = DEFAULT_SCAN_DIRS) -> List[Finding]:
    """Sucht strukturierte personenbezogene Kennungen. Nennt seine Blindstellen mit."""
    findings: List[Finding] = []

    # --- Positivkontrolle ZUERST: findet jeder Ausdruck seinen Kanarienvogel? ---
    blind = [name for name, _, rx in _PII_MUSTER if not rx.search(_PII_KANARIE)]
    if blind:
        # Kein „keine Befunde" von einem Werkzeug, das nachweislich nicht sieht.
        return [Finding(
            kat="B",
            path="(Selbsttest)",
            detail=("SONDE KAPUTT — diese Ausdrücke finden ihren eigenen Kanarienvogel "
                    f"nicht: {', '.join(blind)}. Der Lauf sagt über das Substrat NICHTS."),
            severity="error",
        )]

    unterdrueckt = 0
    geprueft = 0
    for sub in scan_dirs:
        base = kb_root / sub
        if not base.exists():
            continue
        for md in base.rglob("*.md"):
            if _ueberspringen(md, kb_root):
                continue
            rel = str(md.relative_to(kb_root))
            if any(a in f"/{rel}" for a in _PII_AUSGENOMMEN):
                continue
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError) as exc:
                findings.append(Finding(kat="B", path=rel,
                                        detail=f"nicht lesbar: {exc}", severity="warn"))
                continue
            geprueft += 1
            for name, severity, rx in _PII_MUSTER:
                for treffer in rx.finditer(text):
                    roh = treffer.group(0)
                    if _PII_ERLAUBT.search(roh):
                        unterdrueckt += 1
                        continue
                    zeile = text.count("\n", 0, treffer.start()) + 1
                    # Der Wert selbst geht NIE in den Bericht — sonst trägt der
                    # Befund die Daten weiter, vor denen er warnt.
                    findings.append(Finding(
                        kat="B", path=f"{rel}:{zeile}",
                        detail=f"{name} — {_maskiere(roh)}",
                        severity=severity,
                    ))

    # Der Nenner und die Grenze gehören in den Befund, nicht in die Doku.
    findings.append(Finding(
        kat="B",
        path="(Erhebung)",
        detail=(f"{geprueft} Dateien geprüft, {unterdrueckt} Treffer per Erlaubnisliste "
                f"unterdrückt. GRENZE: findet strukturierte Kennungen (Mail, IBAN, SVNR, "
                f"Telefon, Geburtsdatum im Kontext) — findet KEINE Namen, keine Anschriften "
                f"im Fließtext, nichts nur im Zusammenhang Personenbeziehbares. "
                f"Ein Nullbefund ist deshalb kein Freispruch."),
        severity="info",
    ))
    return findings


def _maskiere(wert: str) -> str:
    """Erste 3 und letzte 2 Zeichen, Rest verdeckt. Nie der volle Wert."""
    w = wert.strip()
    if len(w) <= 6:
        return "…" * len(w)
    return f"{w[:3]}…{w[-2:]} ({len(w)} Zeichen)"


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
    UEBERSPRUNGEN.clear()   # je Lauf neu — sonst summiert sich der Zähler über Testläufe
    try:
        report.kat_a = kat_a_frontmatter_drift(kb_root, scan_dirs)
        report.kat_c = kat_c_cross_ref_breaks(kb_root, scan_dirs)
        report.kat_f = kat_f_stale_reviews(kb_root, scan_dirs, today=today)
        report.kat_b = kat_b_pii_scan(kb_root, scan_dirs)
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
        f"- uebersprungen (nicht pruefbar): {sum(len(v) for v in UEBERSPRUNGEN.values())}",
    ]
    # Die Ausnahme steht IM Bericht. Eine stille Ausnahme waere schlimmer als der Falschbefund.
    for grund, dateien in sorted(UEBERSPRUNGEN.items()):
        lines.append(f"  - {len(dateien)}x {grund}")
    lines.append("")
    sections = [
        ("A", "Frontmatter-Drift (M32)"),
        ("B", "PII-Scan (Mail/IBAN/SVNR/Tel/Geburtsdatum — findet KEINE Namen)"),
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

    # Ein Linter, der "sauber" nicht von "nichts gefunden" unterscheiden kann, ist
    # schlimmer als keiner -- er meldet Gruen fuer ein Verzeichnis, das es nicht gibt.
    # Gemessen 2026-08-01 beim Ausrollen auf swarm1: dort ist $HOME=/root, die Vorgabe
    # ~/kb zeigte auf /root/kb (existiert nicht), Ergebnis "0 findings", Exit 0.
    # Genau die Falschmeldung, gegen die dieses Werkzeug gebaut ist.
    if not kb_root.is_dir():
        print(f"kb-lint: ABBRUCH -- kb-root '{kb_root}' existiert nicht oder ist kein "
              f"Verzeichnis. Das ist KEIN sauberes Ergebnis, sondern eine nicht "
              f"stattgefundene Messung. Richtiges Verzeichnis mit --kb-root angeben.",
              file=sys.stderr)
        return 3

    gefunden = sum(1 for sub in args.scan_dirs
                   for _ in (kb_root / sub).rglob("*.md")
                   if (kb_root / sub).is_dir())
    if gefunden == 0:
        print(f"kb-lint: ABBRUCH -- unter '{kb_root}' liegt KEINE Markdown-Datei in den "
              f"Scan-Verzeichnissen ({', '.join(args.scan_dirs)}). Null Befunde aus null "
              f"Dateien ist kein Gruen.", file=sys.stderr)
        return 3

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
