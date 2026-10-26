# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Before the 0.2.0 release (Josh, 23 October): what the release's snapshot holds. The DADR
demonstratives, the release metadata, the EACW's CC BY 4.0, the Zenodo record's notes, the
slogan in About and the welcome box's question."""
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"


ROOT = Path(__file__).resolve().parent.parent
WORDLISTS = ROOT / "lemmatrix" / "wordlists"


def test_addressee_demonstratives_are_dadr():
    """Josh: 2SG is too narrow (plurals are near the addressee too) and a bare 2 is ambiguous."""
    from lemmatrix import wordlists
    for name in ("eacw.tsv", "cawl.tsv", "swadesh.tsv"):
        assert "D2SG" not in (WORDLISTS / name).read_text(encoding="utf-8"), name
    eacw = wordlists.get(wordlists.EACW).by_number
    assert eacw["RLOCDADR"].gloss == "there (near you)"
    assert eacw["R3SGDADR"].gloss == "that (near you)"
    assert eacw["R3PLDADR"].gloss == "those (near you)"
    swadesh = wordlists.get(wordlists.SWADESH).by_number
    assert "R3SGDADR" in swadesh["8"].eacw and "RLOCDADR" in swadesh["10"].eacw


def test_release_metadata():
    licence = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert licence.startswith("GNU AFFERO") or licence.lstrip(" ").startswith("GNU AFFERO")
    assert not licence.startswith("\n")
    for name in ("README.md", "CITATION.cff"):           # the 0.1.1 record is being deleted
        assert "23512412" not in (ROOT / name).read_text(encoding="utf-8"), name
    cff = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    import lemmatrix                                     # every release: one version, one date
    assert f"version: {lemmatrix.__version__}" in cff
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"*Lemmatrix* (version {lemmatrix.__version__})" in readme
    z = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    assert f"date-released: {z['publication_date']}" in cff
    assert not list(ROOT.glob("*.workspace"))           # no workspace left in the repository


def test_zenodo_record_agrees_with_citation():
    import lemmatrix
    z = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    assert z["version"] == lemmatrix.__version__
    assert z["license"] == "agpl-3.0-or-later" and z["upload_type"] == "software"
    assert z["creators"] == [{"name": "Smolders, Joshua A. G."}]
    assert "ARTWORK.md" in z["notes"] and "CC BY 4.0" in z["notes"]
    assert "Human readable, machine processable" in z["description"]


def test_eacw_is_cc_by_where_it_ships():
    from lemmatrix.ui.main_window import about_text
    text = (WORDLISTS / "LICENSE-EACW.md").read_text(encoding="utf-8")
    assert "CC BY 4.0" in text and "eacw.tsv" in text and "Joshua A. G. Smolders" in text
    for name in ("NOTICE.md", "README.md", "THIRD-PARTY.md"):
        assert "LICENSE-EACW.md" in (ROOT / name).read_text(encoding="utf-8"), name
    assert "CC BY 4.0" in about_text()


def test_slogan_in_about():
    from lemmatrix.ui.main_window import about_text
    assert "Human readable, machine processable, ethically collected and shared linguistic data." \
        in about_text()


def test_welcome_box_asks_josh_question(win):
    from lemmatrix.__main__ import welcome_box
    from lemmatrix.ui.main_window import SAMPLE
    dlg = welcome_box(win)
    assert dlg.question.text() == "Would you like to load the sample database to see its capabilities?"
    assert dlg.sample.text().startswith("Yes") and dlg.sample.isDefault()
    assert dlg.sample.isEnabled() == SAMPLE.exists()
    assert dlg.opened.text() == "Open a database…" and dlg.new.text() == "New database…"
    dlg.sample.click()
    assert dlg.choice == "sample"


def test_welcome_box_recent_databases(app, tmp_path):
    from lemmatrix.ui.welcome import WelcomeDialog
    db = tmp_path / "Main.xml"
    dlg = WelcomeDialog(None, [{"path": str(db), "title": "Burun - Maghaja - Main Database"}])
    (b, path), = dlg.recent.items()
    assert b.name == "Main Database" and b.description() == "Burun · Maghaja"
    assert b.toolTip() == str(db)
    b.click()
    assert (dlg.choice, dlg.path) == ("recent", str(db))
    assert WelcomeDialog(None, [], sample_exists=False).sample.isEnabled() is False


def test_welcome_first_start_then_the_most_recent_database(win, tmp_path):
    """Josh, 23 October: the welcome window the first time, then the most recent database until
    the setting is changed (Settings → General, or the tick in the window)."""
    from lemmatrix.__main__ import start_path, welcome_box
    p = win.prefs
    old_mode, old_last = p.welcome_mode, p.last_file
    try:
        p.welcome_mode, p.last_file = "", str(tmp_path / "Main.xml")
        assert start_path([], p) == ""                        # the first start: the welcome window
        dlg = welcome_box(win)
        assert not dlg.every_start.isChecked()
        p.show_welcome = dlg.every_start.isChecked()          # what start-up does after the window
        assert p.welcome_mode == "never" and start_path([], p) == str(tmp_path / "Main.xml")
        p.show_welcome = True                                 # ticked in Settings → General
        assert start_path([], p) == "" and welcome_box(win).every_start.isChecked()
        assert start_path(["other.xml"], p) == "other.xml"    # a file given always wins
    finally:
        p.welcome_mode, p.last_file = old_mode, old_last


def test_settings_has_the_welcome_tick(win):
    from lemmatrix.ui.dialogs import PreferencesDialog
    old = win.prefs.welcome_mode
    try:
        win.prefs.welcome_mode = ""
        dlg = PreferencesDialog(win, win.doc.db, win.prefs)
        assert dlg.welcome.text() == "Show the welcome window at every start"
        assert not dlg.welcome.isChecked()
    finally:
        win.prefs.welcome_mode = old


def test_the_alternative_spelling_is_a_trademark_too():
    """Josh, 24 October: λemmatriχ (an initial lambda, a final chi) is a trademark like Lemmatrix."""
    from lemmatrix.ui.main_window import about_text
    for name in ("NOTICE.md", "README.md", "AUTHORS", "DESIGN.md", ".zenodo.json"):
        assert "λemmatriχ" in (ROOT / name).read_text(encoding="utf-8"), name
    assert "λemmatriχ™" in about_text()
