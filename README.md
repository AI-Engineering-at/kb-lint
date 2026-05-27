# kb-lint

> Karpathy-Stage-6 knowledge-base health checks: frontmatter drift, cross-ref breakage, stale reviews (M40 Bauteil #79).

**Stand:** 2026-05-27
**Status:** Bauteil-Mac (Reife-5), LIVE launchd (daily 04:00)
**Visibility:** public
**Bauteil-ID:** #79 (M40 Reife-5)

## Zweck

kb_lint.py — Karpathy Stage 6 Health-Checks für ~/kb/.

M40-Bauteil. SSOT: ~/.claude/skills/kb-lint/SKILL.md.

MVP Welle W78-A: Kat A (Frontmatter-Drift), Kat C (Cross-Ref-Brüche),
Kat F (Stale-Reviews). Kat B/D/E sind Stubs für W79+.

Anti-Pattern-Vakzinen:
- A33 KEIN-MOCK: Wenn .provenance/quarantine.json fehlt → leeres Result,
  nie hardcoded Fake-Findings.
- Regel 5 (Aufräumen): tempdir-Tests räumen ihr eigenes tmp.
- ISC2 CC: read-only Tool (Confidentiality preserved, Integrity unchanged).

## Struktur

```
kb-lint/
├── src/                 # Source code (Python 3)
├── tests/               # pytest test suite
├── README.md
├── LICENSE
└── .github/workflows/   # CI: ruff + pytest
```

## Quick Start

```bash
# Install (stdlib-only — no requirements.txt needed)
git clone https://github.com/AI-Engineering-at/kb-lint.git
cd kb-lint

# Run tests
pytest tests/ -v

# Lint
ruff check src/ tests/
```

## Compliance & Doctrine

- **Anti-Pattern A33 (KEIN-MOCK-ABSOLUT):** echte Datenquellen, keine Fake-Fallbacks.
- **ISC2-CC-Framing:** dokumentiert in src/-Header (CIA-Triad, Risk-Treatment, Defense-in-Depth).
- **Append-only Code:** Refactor via DEC-Eintrag (kb/DECISIONS.md).
- **Action-Logging:** alle non-trivialen Aktionen via `action_log_writer.py` (SHA-256 hash chain).

## Cross-Reference

- Bauteil-Inventar: `kb/ops/BAUTEILE-INVENTAR.md` (Eintrag #79)
- Build-Beleg (raw): `kb/raw/2026-05-27-w78-a-bauteil-79-kb-lint.md`
- Skill-Definition (falls vorhanden): `~/.claude/skills/kb-lint/SKILL.md`

## License

MIT — see [LICENSE](LICENSE).
