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

from test_ui import app, win  # noqa: E402,F401

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
    assert "date-released: 2026-10-23" in cff and "version: 0.2.0" in cff
    assert not list(ROOT.glob("*.workspace"))           # no workspace left in the repository


def test_zenodo_record_agrees_with_citation():
    import lemmatrix
    z = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    assert z["version"] == lemmatrix.__version__ == "0.2.0"
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
    box, sample, opened, new, recent = welcome_box(win)
    assert box.text() == "Would you like to load the sample database to see its capabilities?"
    assert sample.text().startswith("Yes")
    if SAMPLE.exists():
        assert box.defaultButton() is sample and sample.isEnabled()
    labels = [b.text() for b in box.buttons()]
    assert "Open a database…" in labels and "New database…" in labels and "Close" in labels
