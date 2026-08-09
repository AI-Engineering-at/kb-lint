"""Prüft die Ausnahme vom 2026-08-10 — und zwar in beide Richtungen.

Eine Ausnahme, die einen echten Befund frisst, ist schlimmer als der Falschbefund.
Deshalb steht hier neben jedem 'wird uebersprungen' ein 'wird trotzdem gemeldet'.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
import kb_lint


def _kb(tmp_path):
    ops = tmp_path / "ops"
    (ops / "archiv").mkdir(parents=True)
    (ops / ".pytest_cache").mkdir(parents=True)
    # 1 echter Mangel — MUSS gemeldet werden (das ist die Positivkontrolle des Tests)
    (ops / "echt-ohne-frontmatter.md").write_text("# Echt\n\nkein Frontmatter\n")
    # 2 nicht prüfbar
    (ops / "archiv" / "2026-01-01-alt.md").write_text("# Archiv\n\neingefroren\n")
    (ops / ".pytest_cache" / "README.md").write_text("# pytest cache\n")
    return tmp_path


def test_echter_mangel_wird_weiter_gemeldet(tmp_path):
    kb = _kb(tmp_path)
    f = kb_lint.kat_a_frontmatter_drift(kb, ["ops"])
    pfade = [p.name for p in map(pathlib.Path, (x.path for x in f))]
    assert "echt-ohne-frontmatter.md" in pfade, \
        "Die Ausnahme hat einen echten Befund gefressen — genau das darf sie nicht"


def test_archiv_und_generiertes_werden_uebersprungen(tmp_path):
    kb = _kb(tmp_path)
    f = kb_lint.kat_a_frontmatter_drift(kb, ["ops"])
    # NICHT den ganzen Pfad pruefen: pytest benennt das Temp-Verzeichnis nach der
    # Testfunktion, also enthaelt jeder Pfad hier "archiv". Erster Anlauf am 2026-08-10
    # war deshalb rot, obwohl der Code richtig lag — die Sonde, nicht das Ziel.
    namen = [pathlib.Path(x.path).name for x in f]
    eltern = [pathlib.Path(x.path).parent.name for x in f]
    assert "2026-01-01-alt.md" not in namen, "Archiv darf keine Pflege schulden"
    assert "archiv" not in eltern, "keine Datei aus einem archiv/-Ordner darf gemeldet werden"
    assert ".pytest_cache" not in eltern, "Generiertes ist kein Wissen"


def test_ausnahme_wird_gezaehlt_nicht_verschwiegen(tmp_path):
    kb = _kb(tmp_path)
    kb_lint.UEBERSPRUNGEN.clear()
    kb_lint.kat_a_frontmatter_drift(kb, ["ops"])
    ges = sum(len(v) for v in kb_lint.UEBERSPRUNGEN.values())
    assert ges == 2, f"erwartet 2 gezaehlte Ausnahmen, gezaehlt {ges} — eine stille Ausnahme ist der Fehler"
    assert any("Archiv" in g for g in kb_lint.UEBERSPRUNGEN), "Grund muss benannt sein"


def test_verweis_loest_auch_von_der_kb_wurzel_auf(tmp_path):
    kb = tmp_path
    (kb / "ops").mkdir()
    (kb / "MASTER-PLAN.md").write_text("# Plan\n")
    (kb / "ops" / "zeigt-darauf.md").write_text(
        "---\nstand: 2026-01-01\nmutability: mutable-mit-stand\nclassification: internal\n---\n\n"
        "# X\n\ncross-ref: MASTER-PLAN.md\n")
    f = kb_lint.kat_c_cross_ref_breaks(kb, ["ops"])
    assert not f, f"MASTER-PLAN.md liegt in der kb-Wurzel — kein Bruch, gemeldet wurde aber {f}"
