# kb-lint

<!-- AIE-SSOT-BLOCK v1.0 · kanonisch: kb/ops/standards/PROJEKT-CLAUDE-BLOCK.md · NICHT lokal editieren -->
## AIE-Standards (gelten in jedem Projekt)
- **Gitea = Code-SSOT** (`10.40.10.82:3050/joe/<repo>`): committen + pushen IMMER nach Gitea. GitHub = nur öffentlicher Spiegel (Schreibrichtung intern→extern, NIE via GitHub zurück).
- **Secrets nie im Repo**: `.env`/Keys in `.gitignore`; Werte in aie-vault/OpenBao (`secret/<domain>/<service>-<key>`). Vor jedem Erst-Push: `git ls-files | grep -iE '\.env$|secret|credential|token|\.pem$|\.key$'` muss leer sein. Token nie in Remote-URLs (osxkeychain-Helper nutzt sie automatisch).
- **KEIN-MOCK (A33)**: keine Fakes/Stubs/Platzhalter in Prod-Pfaden; leer/down → ehrlich `—`. Test-Mocks nur unter `tests/`.
- **Verify-vor-Behaupten (M126)**: „läuft/grün/deployed/gefixt" nur mit gemessenem Beweis (Testlauf, Live-Probe, Senken-Check) — nie aus Doku/Memory/Agent-Summary.
- **Uncommitted = ungesichert**: Arbeitsstände regelmäßig committen + nach Gitea pushen — nur Gepushtes überlebt den Platten-Tod.
- **Bauteil-DoD**: Code + Tests + lauffähig + reproduzierbar + bedienbar; „fertig" = aktiviert + gemessen + genutzt, nicht „gebaut".
- **Wo-ist-was**: Bestand → `~/kb/ops/WAS-WIR-HABEN.md` · Fehler ZUERST → `~/kb/ops/KNOWN-ERRORS-DB.md` (troubleshoot-Skill) · Betriebsmodell/Tiers → `~/kb/ops/WER-MACHT-WAS.md` · System-Fakten → `~/kb/SYSTEM-FACTS.md`.

## Projekt-Spezifisches

<TODO: Build/Run/Test-Kommandos>
