# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Josh's v0 ideas of 24 October: Acknowledgements in the metadata (idea 59: Support and Thanks,
the thanks only in an Ethical archive when chosen) and Check wordlist integrity (66: one report,
select and fix, one undo step; the EACW's editions, and the update offered on opening)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from lemmatrix import anonymise as an  # noqa: E402
from lemmatrix import newdb, setup_export, storage  # noqa: E402
from lemmatrix import wordlist_check as wc  # noqa: E402
from lemmatrix import wordlists as wl  # noqa: E402
from lemmatrix.model import Support, Thanks, Token  # noqa: E402


def _settle():
    for _ in range(5):
        QApplication.processEvents()


# ---- idea 59: acknowledgements ----------------------------------------------------------------

def _acknowledged(db):
    db.metadata.support = [Support("Leverhulme Trust", "ECF-2026-001", "fieldwork in 2026"),
                           Support("SOAS", "", "")]
    db.metadata.thanks = [Thanks("Amina Yusuf", "hosting the team"), Thanks("The village council", "")]
    return db


def test_acknowledgements_are_saved_and_read(tmp_path):
    db = _acknowledged(newdb.make(newdb.Choices(base=wl.SWADESH)))
    p = tmp_path / "A.xml"
    db.path = str(p)
    storage.save(db, p, backup=False)
    text = p.read_text(encoding="utf-8")
    assert f'<database format="{storage.FORMAT_VERSION}">' in text and "<acknowledgements>" in text
    assert '<support organisation="Leverhulme Trust" grant="ECF-2026-001">fieldwork in 2026</support>' in text
    assert '<thanks who="Amina Yusuf">hosting the team</thanks>' in text
    back = storage.load(p).metadata
    assert back.support == db.metadata.support and back.thanks == db.metadata.thanks


def test_a_format_11_database_opens(tmp_path):
    db = newdb.make(newdb.Choices(base=wl.SWADESH))
    p = tmp_path / "B.xml"
    db.path = str(p)
    storage.save(db, p, backup=False)
    p.write_text(p.read_text(encoding="utf-8").replace(f'format="{storage.FORMAT_VERSION}"', 'format="11"'), encoding="utf-8")
    back = storage.load(p)
    assert back.upgraded and back.metadata.support == [] and back.metadata.thanks == []


def test_the_archives_and_the_thanks(win):
    db = _acknowledged(win.doc.db)
    try:
        out, _ = an.anonymise(db, None, an.Options.for_kind(an.ETHICAL), rep := an.Report())
        assert out.metadata.thanks == [] and rep.thanks_out == 2           # off by default
        assert out.metadata.support[0].organisation == "Leverhulme Trust"
        opts = an.Options.for_kind(an.ETHICAL)
        opts.thanks = True
        out, _ = an.anonymise(db, None, opts, rep := an.Report())
        assert [t.who for t in out.metadata.thanks] == ["Amina Yusuf", "The village council"]
        assert "informed consent" in an.summary(rep, opts)
        opts = an.Options.for_kind(an.ANONYMOUS)
        opts.thanks = True                                                 # never in the anonymous one
        out, _ = an.anonymise(db, None, opts, an.Report())
        assert out.metadata.thanks == [] and out.metadata.support
        assert setup_export.setup_copy(db).metadata.support == []
        assert db.metadata.thanks                                          # the database untouched
    finally:
        db.metadata.support, db.metadata.thanks = [], []


def test_the_metadata_dialogue_edits_both_lists(win):
    from lemmatrix.ui.dialogs import MetadataDialog
    db = win.doc.db
    dlg = MetadataDialog(win, db)
    dlg.support.add(["British Academy", "SG-1", "recordings"])
    dlg.support.add(["", "", ""])                                          # an empty row is dropped
    dlg.thanks.add(["My family", "patience"])
    dlg.apply()
    try:
        assert db.metadata.support == [Support("British Academy", "SG-1", "recordings")]
        assert db.metadata.thanks == [Thanks("My family", "patience")]
        dlg2 = MetadataDialog(win, db)
        assert dlg2.thanks.rows() == [["My family", "patience"]]
        dlg2.thanks.table.setCurrentCell(0, 0)
        dlg2.thanks.remove()
        dlg2.apply()
        assert db.metadata.thanks == []
    finally:
        db.metadata.support, db.metadata.thanks = [], []


def test_the_ethical_archive_offers_the_thanks(win):
    from lemmatrix.ui.export_dialog import ArchiveExportDialog as ArchiveDialog
    db = win.doc.db
    db.metadata.thanks = [Thanks("Amina Yusuf", "hosting the team")]
    try:
        d = ArchiveDialog(win, an.ETHICAL)
        assert d.thanks.isEnabled() and not d.thanks.isChecked()
        d.thanks.setChecked(True)
        assert d.options().thanks
        d.set_kind(an.ANONYMOUS)
        assert not d.thanks.isEnabled() and not d.options().thanks
        d.reject()
    finally:
        db.metadata.thanks = []


# ---- idea 66: wordlist integrity ---------------------------------------------------------------

@pytest.fixture
def no_renumbering(monkeypatch):
    """The editions without 2026-10-27's renumbering: these tests set an older version on a database
    built from the newest list, which a real older database never is (its references are the old
    numbers); the renumbering has tests of its own (tests/test_edition_20261027.py)."""
    from dataclasses import replace
    eds = tuple(replace(e, renumbered="", old_glosses="", redesignated=frozenset()) for e in wl.EDITIONS)
    monkeypatch.setattr(wl, "EDITIONS", eds)


def _eacw_db(version=""):
    db = newdb.make(newdb.Choices(base=wl.EACW, items=wl.BASE, region=wl.AFRICA))
    db.metadata.wordlist_version = version
    return db


def test_new_eacw_databases_are_on_the_shipped_edition():
    db = newdb.make(newdb.Choices(base=wl.EACW))
    assert db.metadata.wordlist_version == wl.EACW_VERSION and not wc.out_of_date(db)
    assert wc.check(db) == []
    assert wl.editions_since("") == list(wl.EDITIONS[1:])


def test_the_check_finds_and_selects_what_the_update_changed(no_renumbering):
    db = _eacw_db("")                                    # the first edition
    eacw = wl.get(wl.EACW)
    db.entries = [e for e in db.entries if e.ref not in ("C015f", "D002")]   # C015f newly default
    c009 = db.new_entry("C009", gloss="child (offspring)")                    # newly hidden, empty
    c012 = db.new_entry("C012", gloss="cousin")
    c012.tokens.append(Token(values={"Phonetic": "ba"}))                      # newly hidden, with data
    d001b = db.new_entry("A009b", gloss="x")                                  # hidden long ago, empty
    goat = db.entry_by_ref("D009") or db.entries[5]
    goat.lists = {"CAWL": ["9999"]}                                           # out of date numbers
    db.entries += [c009, c012, d001b]
    assert wc.out_of_date(db)
    fs = wc.check(db)
    by = {(f.kind, f.ref): f for f in fs}
    assert by[(wc.MISSING, "C015f")].selected and not by[(wc.MISSING, "D002")].selected
    assert by[(wc.HIDDEN, "C009")].selected and by[(wc.HIDDEN, "C009")].fixable
    assert not by[(wc.HIDDEN, "C012")].fixable                                # data: never removed
    assert by[(wc.HIDDEN, "A009b")].fixable and not by[(wc.HIDDEN, "A009b")].selected
    assert by[(wc.NUMBERS, goat.ref)].selected
    assert any(f.kind == wc.ORDER for f in fs)                                # the three added at the end
    assert "A009b" in eacw.by_number


def test_the_plan_never_drops_a_lemma_with_data(no_renumbering):
    db = _eacw_db("")
    c012 = db.new_entry("C012", gloss="cousin")
    c012.tokens.append(Token(values={"Phonetic": "ba"}))
    db.entries.append(c012)
    fs = wc.check(db)
    for f in fs:
        f.selected = True
    order, pairs, made = wc.plan(db, fs, lambda item: db.new_entry(item.number, gloss=item.gloss))
    assert c012 in order
    assert {e.ref for e in made} == {f.ref for f in fs if f.kind == wc.MISSING}


def test_fix_the_selected_is_one_undo_step(win, monkeypatch, no_renumbering):
    from lemmatrix.ui import wordlist_dialogs as wd
    db = win.doc.db
    wl.link_as_eacw(db)                                  # the tests' sample isn't built on a list
    before = [e.ref for e in db.entries]
    version = db.metadata.wordlist_version
    db.metadata.wordlist_version = ""
    e = db.entries[0]
    e.lists = {"CAWL": ["9999"]}

    def fake_exec(d):
        d.tree.topLevelItem(0).setCheckState(0, Qt.Checked)     # a whole kind
        return QDialog.Accepted
    monkeypatch.setattr(wd.IntegrityDialog, "exec", fake_exec)
    win.check_wordlist_integrity()
    assert db.metadata.wordlist_version == wl.EACW_VERSION
    assert e.lists.get("CAWL") != ["9999"]
    win.doc.undo.undo()
    assert db.metadata.wordlist_version == "" and e.lists == {"CAWL": ["9999"]}
    assert [x.ref for x in db.entries] == before
    win.doc.undo.redo()
    win.doc.undo.undo()
    db.metadata.wordlist_version = version
    win.doc.undo.clear()
    win.doc.mark_clean() if hasattr(win.doc, "mark_clean") else None


def test_opening_an_older_edition_offers_the_update(win, monkeypatch, no_renumbering):
    from lemmatrix.ui import wordlist_dialogs as wd
    db = win.doc.db
    wl.link_as_eacw(db)
    version = db.metadata.wordlist_version
    db.metadata.wordlist_version = ""
    c009 = db.new_entry("C009", gloss="child (offspring)")
    db.entries.append(c009)
    try:
        box = wd.offer_update(win)
        assert box is not None and "2026-10-24" in box.text()
        update = next(b for b in box.buttons() if b.text() == "Update")
        update.click()
        _settle()
        assert c009 not in db.entries and db.metadata.wordlist_version == wl.EACW_VERSION
        win.doc.undo.undo()
        assert c009 in db.entries
    finally:
        db.entries[:] = [x for x in db.entries if x is not c009]
        db.metadata.wordlist_version = version
        win.doc.undo.clear()
        box = getattr(win, "_wordlist_notice", None)
        if box is not None:
            box.close()


def test_nothing_to_update_records_the_edition_quietly(no_renumbering):
    from types import SimpleNamespace
    from lemmatrix.ui import wordlist_dialogs as wd
    db = _eacw_db("")                     # the whole base list: nothing the update changed is missing
    assert not any(f.selected and f.fixable for f in wc.check(db))
    assert wd.offer_update(SimpleNamespace(doc=SimpleNamespace(db=db))) is None
    assert db.metadata.wordlist_version == wl.EACW_VERSION


def test_the_samples_are_on_the_shipped_edition():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "samples"
    for p in root.rglob("*.xml"):
        db = storage.load(p)
        if wl.is_eacw(db):
            assert not wc.out_of_date(db), p.name
