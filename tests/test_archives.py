# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""The Anonymous archive and the Ethical archive (IDEAS.md idea 44), and format 8."""

import os
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from lemmatrix import anonymise, defaults, notebook as nbmod, storage, textgrid as tgmod  # noqa: E402
from lemmatrix.anonymise import ANONYMOUS, ETHICAL, Options  # noqa: E402
from lemmatrix.model import Person, Text  # noqa: E402

from test_ui import app, win  # noqa: F401,E402 (fixtures)

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def _db(tmp_path):
    """A copy of the sample with real-looking people, a text with a TextGrid, comments and a
    notebook (all invented: nothing here is anyone's data)."""
    shutil.copy2(SAMPLES / "Sample.xml", tmp_path / "LXX-VXX_Lexicon.xml")
    shutil.copytree(SAMPLES / "Soundfiles", tmp_path / "Soundfiles")
    db = storage.load(tmp_path / "LXX-VXX_Lexicon.xml")
    md = db.metadata
    md.language_name, md.variety_name = "Sample language", "Hill"
    md.participants = [Person("KDB", "Kuku Dabi", "a farmer", "Consent/KDB.pdf", identifiable=True,
                              audio_sharing=True),
                       Person("HMA", "Hana Mali", "a teacher", "Consent/HMA.pdf")]
    md.researchers = [Person.researcher("JS", "Jo Smith", email="jo@example.org"),
                      Person("AB", "Ann Bell", "assistant", email="ann@example.org")]
    md.author = "Jo Smith"
    (tmp_path / "Consent").mkdir()
    (tmp_path / "Consent" / "KDB.pdf").write_bytes(b"%PDF KDB")
    (tmp_path / "Consent" / "HMA.pdf").write_bytes(b"%PDF HMA")
    for i, e in enumerate(db.entries):
        for t in e.tokens:
            t.speaker = "KDB" if i % 2 == 0 else "HMA"
    db.entries[0].tokens[0].set("Comment", "Kuku said this twice; ask Hana Mali and KDB again")
    db.entries[1].tokens[0].set("Translation", "Hana's goat", "en")
    db.settings.tags.leaf_groups()[0][1].tags[0].description = "as Kuku says it"
    texts = tmp_path / "Soundfiles" / "Texts"
    texts.mkdir(parents=True)
    tgmod.write_example(texts / "LXX-VXX_T001_Kuku_story.TextGrid",
                        {"tx@KDB": [(0.0, 1.0, "dabuuba")], "ft@KDB": [(0.0, 1.0, "Kuku told Hana")]}, 2.0)
    (texts / "LXX-VXX_T001_Kuku_story.wav").write_bytes(b"RIFF")
    db.texts.append(Text("T001", file_label="Kuku story", participants=["KDB"], researchers=["JS"],
                         file="LXX-VXX_T001_Kuku_story.wav", textgrid="LXX-VXX_T001_Kuku_story.TextGrid",
                         values={"Title": "Kuku's story"}))
    book = nbmod.Notebook()
    s = book.add_session("2026-10-01")
    s.participants, s.researchers, s.notes = ["KDB", "HMA"], ["JS"], "Paid Hana for five sessions. H1 looks good."
    return db, book


def _all_text(folder: Path) -> str:
    out = []
    for f in folder.rglob("*"):
        if f.is_file() and f.suffix.lower() in (".xml", ".notebook", ".workspace", ".textgrid"):
            out.append(f.read_text(encoding="utf-8", errors="replace"))
        out.append(f.name)
    return "\n".join(out)


# ---------------------------------------------------------------- format 8

def test_format_8_ticks_researchers_and_writes_both_ticks(tmp_path):
    p = tmp_path / "Old.xml"
    text = (SAMPLES / "Sample.xml").read_text(encoding="utf-8")
    text = text.replace(f'format="{storage.FORMAT_VERSION}"', 'format="7"')
    text = text.replace(' identifiable="yes"', "").replace(' identifiable="no"', "").replace(' audio-sharing="no"', "")
    p.write_text(text, encoding="utf-8")
    db = storage.load(p)
    assert db.upgraded
    assert all(r.identifiable for r in db.metadata.researchers)         # ticked on opening
    assert not any(x.identifiable or x.audio_sharing for x in db.metadata.participants)
    storage.save(db, p, backup=False)
    saved = p.read_text(encoding="utf-8")
    assert '<database format="8">' in saved
    assert '<researcher code="RS1" name="Researcher 1" identifiable="yes" />' in saved
    assert '<participant code="SP1" name="Speaker 1" identifiable="no" audio-sharing="no" />' in saved
    again = storage.load(p)
    assert not again.upgraded and again.metadata.researchers[0].identifiable


def test_a_researcher_unticked_stays_unticked(tmp_path):
    db = storage.load(SAMPLES / "Sample.xml")
    db.metadata.researchers[1].identifiable = False
    storage.save(db, tmp_path / "S.xml", backup=False)
    back = storage.load(tmp_path / "S.xml")
    assert [r.identifiable for r in back.metadata.researchers] == [True, False]


def test_new_researchers_are_identifiable_new_participants_not():
    assert all(p.identifiable for p in defaults.default_researchers())
    assert not any(p.identifiable for p in defaults.default_participants())
    assert Person.researcher("RS9").identifiable and not Person("SP9").identifiable


def test_the_lists_add_a_ticked_researcher(win):
    from PySide6.QtCore import Qt
    from lemmatrix.ui.lists_dialog import PeopleEditor
    ed = PeopleEditor(win.doc.db, [], False, lambda c: 0)
    ed._add_row(Person.researcher("RS7", "New one"))
    it = ed.table.item(0, ed.col("identifiable"))
    assert it.checkState() == Qt.Checked
    it.setCheckState(Qt.Unchecked)
    assert not ed.people()[0].identifiable


# ---------------------------------------------------------------- the anonymous archive

def test_the_anonymous_archive_names_nobody_and_renumbers_every_code(tmp_path):
    import pyzipper
    db, book = _db(tmp_path)
    opts = Options.for_kind(ANONYMOUS)
    opts.notebook, opts.consent_password = True, "pw"
    rep = anonymise.export(db, book, tmp_path / "out", opts)
    out = storage.load(tmp_path / "out" / "LXX-VXX_Lexicon (anonymous).xml")
    md = out.metadata
    assert [(p.code, p.name, p.description, p.consent) for p in md.participants] == [
        ("SP1", "", "", ""), ("SP2", "", "", "")]
    assert [(p.code, p.name, p.email) for p in md.researchers] == [("RS1", "", ""), ("RS2", "", "")]
    assert md.author == "RS1"
    assert md.language_name == "LXX" and md.variety_name == "VXX"            # names become codes
    assert {t.speaker for e in out.entries for t in e.tokens} == {"SP1", "SP2"}
    assert out.entries[0].tokens[0].get("Comment") == "SP1 said this twice; ask SP2 and SP1 again"
    assert out.entries[1].tokens[0].get("Translation", "en") == "SP2's goat"
    t = out.texts[0]
    assert t.participants == ["SP1"] and t.researchers == ["RS1"] and t.get("Title") == "SP1's story"
    assert "Kuku" not in t.textgrid and "Kuku" not in t.file
    grid = tmp_path / "out" / "Soundfiles" / "Texts" / t.textgrid
    tiers = tgmod.tiers(grid)
    assert sorted(x.name for x in tiers) == ["ft@SP1", "tx@SP1"]
    assert "SP1 told SP2" in grid.read_text(encoding="utf-8")
    assert not list((tmp_path / "out").rglob("*.wav"))                        # no recordings at all
    back = nbmod.load(tmp_path / "out" / "LXX-VXX_Lexicon (anonymous).notebook").session("2026-10-01")
    assert back.participants == ["SP1", "SP2"] and back.researchers == ["RS1"]
    assert back.notes.startswith("Paid SP2 for five sessions.")
    everything = _all_text(tmp_path / "out")
    for gone in ("Kuku", "Dabi", "Hana", "Mali", "Jo Smith", "Ann Bell", "KDB", "HMA", "jo@example.org",
                 "farmer", "Consent/"):
        assert gone not in everything, gone
    with pyzipper.AESZipFile(tmp_path / "out" / "LXX-VXX_Lexicon consent forms (password).zip") as zf:
        zf.setpassword(b"pw")
        assert zf.read("SP1/KDB.pdf") == b"%PDF KDB"
        key = zf.read("Code key.csv").decode("utf-8-sig")
    assert "participant,KDB,SP1" in key and "researcher,AB,RS2" in key
    assert rep.key_written and "key" in anonymise.summary(rep, opts)
    assert db.metadata.participants[0].name == "Kuku Dabi"                     # the original is untouched
    assert db.entries[0].tokens[0].speaker == "KDB"


def test_no_key_without_the_zip(tmp_path):
    db, book = _db(tmp_path)
    opts = Options.for_kind(ANONYMOUS)
    rep = anonymise.export(db, book, tmp_path / "out", opts)
    assert not rep.key_written and not list((tmp_path / "out").glob("*.zip"))
    assert "can't be undone" in anonymise.summary(rep, opts)
    assert "KDB" not in _all_text(tmp_path / "out")


def test_hiding_the_language_and_variety_codes(tmp_path):
    db, book = _db(tmp_path)
    db.metadata.language_code, db.metadata.variety_code = "BDI", "MGJ"
    for e in db.entries:
        for t in e.tokens:
            if t.file:
                t.file = t.file.replace("LXX-VXX", "BDI-MGJ")
    db.path = str(tmp_path / "BDI-MGJ_Lexicon.xml")
    opts = Options.for_kind(ANONYMOUS)
    opts.hide_language_code = opts.hide_variety_code = True
    anonymise.export(db, book, tmp_path / "out", opts)
    out = storage.load(tmp_path / "out" / "LXX-VXX_Lexicon (anonymous).xml")
    md = out.metadata
    assert (md.language_code, md.language_name, md.variety_code, md.variety_name) == ("LXX", "LXX", "VXX", "VXX")
    assert all("BDI" not in t.file and "MGJ" not in t.file for e in out.entries for t in e.tokens)
    assert "BDI" not in _all_text(tmp_path / "out") and "Hill" not in _all_text(tmp_path / "out")


def test_only_the_language_code_hidden(tmp_path):
    db, book = _db(tmp_path)
    db.metadata.language_code, db.metadata.variety_code = "BDI", "MGJ"
    opts = Options.for_kind(ANONYMOUS)
    opts.hide_language_code = True
    out, _ = anonymise.anonymise(db, book, opts, anonymise.Report())
    assert (out.metadata.language_code, out.metadata.variety_code) == ("LXX", "MGJ")


# ---------------------------------------------------------------- the ethical archive

def test_the_ethical_archive_names_only_the_identifiable(tmp_path):
    db, book = _db(tmp_path)
    opts = Options.for_kind(ETHICAL)
    rep = anonymise.export(db, book, tmp_path / "out", opts)
    out = storage.load(tmp_path / "out" / "LXX-VXX_Lexicon (ethical).xml")
    kdb, hma = out.metadata.participants
    assert (kdb.code, kdb.name, kdb.description, kdb.consent) == ("KDB", "Kuku Dabi", "a farmer", "")
    assert (hma.code, hma.name, hma.description, hma.consent) == ("HMA", "", "", "")
    js, ab = out.metadata.researchers
    assert (js.name, js.email) == ("Jo Smith", "jo@example.org")               # identifiable: email kept
    assert (ab.name, ab.email, ab.description) == ("", "", "")
    assert out.metadata.author == "Jo Smith" and out.metadata.language_name == "Sample language"
    assert out.entries[0].tokens[0].get("Comment") == "Kuku said this twice; ask HMA and KDB again"
    assert out.entries[1].tokens[0].get("Translation", "en") == "HMA's goat"
    # recordings: only Kuku's (he agreed to audio sharing); Hana's are left out
    copied = {f.name for f in (tmp_path / "out" / "Soundfiles" / "Tokens").glob("*.wav")}
    kuku = {t.file for e in db.entries for t in e.tokens if t.file and t.speaker == "KDB"}
    hana = {t.file for e in db.entries for t in e.tokens if t.file and t.speaker == "HMA"}
    assert copied and copied <= kuku and not copied & hana
    assert rep.withheld_recordings == sum(1 for e in db.entries for t in e.tokens if t.file and t.speaker == "HMA")
    assert (tmp_path / "out" / "Soundfiles" / "Texts" / "LXX-VXX_T001_Kuku_story.wav").exists()
    grid = (tmp_path / "out" / "Soundfiles" / "Texts" / "LXX-VXX_T001_Kuku_story.TextGrid").read_text(encoding="utf-8")
    assert "Kuku told HMA" in grid and "tx@KDB" in grid                        # codes stay
    assert "Hana" not in _all_text(tmp_path / "out")
    assert "identifiable people kept their names" in anonymise.summary(rep, opts)


def test_an_unidentifiable_owner_becomes_their_code(tmp_path):
    db, book = _db(tmp_path)
    db.metadata.author = "Ann Bell"
    out, _ = anonymise.anonymise(db, book, Options.for_kind(ETHICAL), anonymise.Report())
    assert out.metadata.author == "AB"


def test_a_text_with_a_speaker_who_did_not_agree_keeps_its_recording_back(tmp_path):
    db, book = _db(tmp_path)
    db.texts[0].participants = ["KDB", "HMA"]
    rep = anonymise.export(db, book, tmp_path / "out", Options.for_kind(ETHICAL))
    texts = tmp_path / "out" / "Soundfiles" / "Texts"
    assert not list(texts.glob("*.wav")) and list(texts.glob("*.TextGrid"))
    assert rep.withheld_recordings >= 1


# ---------------------------------------------------------------- the researcher's own work stays out

@pytest.mark.parametrize("kind", [ANONYMOUS, ETHICAL])
def test_the_notebook_and_workspace_stay_out_by_default(tmp_path, kind):
    """Josh, 22 October: the notebook, Cogitate and the workspace are the researcher's own work,
    not archive data: both archives leave the notebook out unless it is ticked, and the workspace
    is always blank."""
    db, book = _db(tmp_path)
    opts = Options.for_kind(kind)
    assert not opts.notebook
    rep = anonymise.export(db, book, tmp_path / "out", opts)
    assert not list((tmp_path / "out").glob("*.notebook")) and not rep.notebook
    ws = next((tmp_path / "out").glob("*.workspace")).read_text(encoding="utf-8")
    assert "<matrix" not in ws and "session" not in ws
    assert "your own work" in anonymise.summary(rep, opts)


def test_the_defaults_of_each_archive():
    a, e = Options.for_kind(ANONYMOUS), Options.for_kind(ETHICAL)
    assert (a.notebook, a.with_recordings, a.place_levels) == (False, False, 1)
    assert (e.notebook, e.with_recordings, e.place_levels) == (False, True, 0)


# ---------------------------------------------------------------- the dialogue

def test_the_dialogue_switches_its_defaults(win):
    from lemmatrix.ui.export_dialog import ArchiveExportDialog
    d = ArchiveExportDialog(win, ANONYMOUS)
    assert "anonymous archive" in d.windowTitle() and d.ai_note.isVisibleTo(d)
    assert not d.notebook.isChecked() and not d.recordings.isEnabled() and d.places.currentData() == 1
    assert "anonymous archive" in d.folder.text()
    o = d.options()
    assert o.kind == ANONYMOUS and not o.with_recordings
    d.kind_buttons[ETHICAL].setChecked(True)
    assert d.kind == ETHICAL and not d.ai_note.isVisibleTo(d) and not d.codes_row.isVisibleTo(d)
    assert d.recordings.isEnabled() and d.recordings.isChecked() and d.places.currentData() == 0
    assert "ethical archive" in d.folder.text()
    assert not d.options().hide_language_code


def test_the_menu_has_both_archives(win):
    from PySide6.QtWidgets import QMenu
    texts = [a.text().replace("&", "") for m in win.menuBar().findChildren(QMenu) for a in m.actions()]
    assert "Anonymous archive…" in texts and "Ethical archive…" in texts
    assert not any("Anonymous backup" in t for t in texts)
