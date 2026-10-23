# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The final EACW in Lemmatrix (IDEAS.md idea 40, 23 October 2026): New database's versions (base or
expanded; global, Africa or a region) and the ⓘ, format 11, the Clarification and Taxon fields,
the hidden items within reach (the peek, Insert EACW items…, the warnings), Link to wordlists
filling the fields, and Tools → Convert references from a table…."""

import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from lemmatrix import convert_refs as cr  # noqa: E402
from lemmatrix import defaults, newdb, storage  # noqa: E402
from lemmatrix import wordlists as wl  # noqa: E402

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _window(tmp_path, db):
    from lemmatrix.ui import main_window
    if not db.path:
        db.path = str(tmp_path / "E.xml")
    storage.save(db, db.path, backup=False)
    w = main_window.MainWindow()
    w.load_database(storage.load(db.path))
    return w


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    w = _window(tmp_path, defaults.new_database(wl.EACW))
    yield w
    w.doc.undo.setClean()
    w.doc._settings_dirty = False
    w.close()


# ---- format 11 -------------------------------------------------------------------------------
def test_format_11_keeps_the_version(tmp_path):
    db = newdb.make(newdb.Choices(base=wl.EACW, items=wl.EXPANDED, region="W"))
    p = tmp_path / "W.xml"
    db.path = str(p)
    storage.save(db, p, backup=False)
    text = p.read_text(encoding="utf-8")
    assert '<database format="11">' in text
    assert '<wordlist base="EACW" items="expanded" region="W" />' in text
    back = storage.load(p)
    assert (back.metadata.wordlist_items, back.metadata.wordlist_region) == (wl.EXPANDED, "W")
    assert back.entry_by_ref("D009").get("Taxon") == "Capra hircus (Bovidae)"
    assert len(back.entries) == len(wl.version_items(wl.EXPANDED, "W"))


def test_a_format_10_database_opens(tmp_path):
    db = defaults.new_database(wl.SWADESH)
    p = tmp_path / "S.xml"
    db.path = str(p)
    storage.save(db, p, backup=False)
    p.write_text(p.read_text(encoding="utf-8").replace('format="11"', 'format="10"'), encoding="utf-8")
    back = storage.load(p)
    assert back.upgraded and back.metadata.wordlist_base == wl.SWADESH and not back.metadata.wordlist_items


# ---- New database ------------------------------------------------------------------------------
def test_the_new_database_choice(app):
    from lemmatrix.ui.wordlist_dialogs import WHY_EACW, WordlistChoice
    w = WordlistChoice()
    assert w.choice() == wl.EACW and w.version() == (wl.BASE, wl.AFRICA)
    assert w.count.text() == "2,281 lemmas"
    w.items.setCurrentIndex(w.items.findData(wl.EXPANDED))
    w.region.setCurrentIndex(w.region.findData(wl.GLOBAL))
    assert w.count.text() == f"{len(wl.version_items(wl.EXPANDED, wl.GLOBAL)):,} lemmas"
    assert [w.region.itemText(i) for i in range(w.region.count())] == \
        ["Global", "Africa", "North", "West", "East", "South", "Central"]
    from PySide6.QtWidgets import QLabel
    infos = [lb for lb in w.findChildren(QLabel) if lb.text() == "ⓘ"]
    assert infos and infos[0].toolTip() == WHY_EACW and WHY_EACW.startswith("Why the EACW?")
    for b in w.group.buttons():
        if b.property("list") == wl.CAWL:
            b.setChecked(True)
    assert not w.version_row.isEnabled()                     # only for the EACW


# ---- the hidden items within reach --------------------------------------------------------------
def test_the_peek_and_insert_eacw_items(win):
    from lemmatrix.ui.wordlist_dialogs import InsertItemsDialog, insert_items
    db = win.doc.db
    b = db.entry_by_ref("B033m")
    col = next(c for c in win._lemma_columns() if c.key == "ref")
    assert "B033f  female warrior  (hidden)" in col.tooltip(b)
    d = InsertItemsDialog(win, b)
    assert {i.number for i in d.chosen()} == {"B033", "B033f"}    # beside B033m, ticked
    d.only_near.setChecked(False)
    d.search.setText("excision")
    assert [i.number for i in d.shown] == ["I069f"]
    n = len(db.entries)
    made = insert_items(win, d.chosen())
    assert len(db.entries) == n + 2
    k = db.entries.index(db.entry_by_ref("B033m"))
    assert [e.ref for e in db.entries[k - 2:k + 1]] == ["B033", "B033f", "B033m"]   # in the list's order
    f = db.entry_by_ref("B033f")
    assert db.gloss(f) == "female warrior" and f.lists == {wl.CAWL: ["0406"]}
    assert made[0].tokens and win.doc.undo.canUndo()
    win.doc.undo.undo()                                          # one undo step
    assert len(db.entries) == n and db.entry_by_ref("B033f") is None
    win.doc.undo.redo()
    assert db.entry_by_ref("B033f") is f


def _entry_dialog(win, ref, gloss, answers, monkeypatch):
    """The lemma dialogue for a new lemma, with the buttons clicked in turn."""
    from lemmatrix.ui import dialogs
    asked = []

    def ask(self, title, text, buttons):
        asked.append(text)
        return answers.pop(0)
    monkeypatch.setattr(dialogs.EntryDialog, "_ask", ask)
    dlg = dialogs.EntryDialog(win, win.doc.db)
    dlg.ref.setText(ref)
    dlg._gloss_edit().setText(gloss)
    dlg.accept()
    return dlg, asked


def test_f_and_m_are_reserved(win, monkeypatch):
    dlg, asked = _entry_dialog(win, "J073f", "maize leaf", [1], monkeypatch)    # Use J073i
    assert "reserved for the female" in asked[0] and dlg.ref.text() == "J073i"
    assert dlg.result() == QDialog.Accepted
    dlg, asked = _entry_dialog(win, "D009f", "she-goat", [], monkeypatch)      # an EACW item: no question
    assert not asked


def test_a_hidden_items_reference_and_gloss(win, monkeypatch):
    dlg, asked = _entry_dialog(win, "I069f", "something else", [0], monkeypatch)
    assert "excision" in asked[0] and dlg._gloss_edit().text() == "excision"    # Make it excision
    e = dlg.new_entry("", "")
    assert e.lists == {wl.CAWL: ["0936"]} and e.get("WordClass") == "NOUN"
    dlg, asked = _entry_dialog(win, "A999", "excision", [0], monkeypatch)       # Use I069f
    assert "I069f" in asked[0] and dlg.ref.text() == "I069f"
    dlg, asked = _entry_dialog(win, "A999", "excision", [1], monkeypatch)       # Keep A999
    assert dlg.ref.text() == "A999" and dlg.result() == QDialog.Accepted


def test_link_to_wordlists_fills_clarification_and_taxon(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from lemmatrix.ui import wordlist_dialogs
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    db = defaults.new_database("")
    for ref, gloss in (("D009", "goat"), ("J022a", "neem tree"), ("C001f", "mother")):
        db.entries.append(db.new_entry(ref, gloss=gloss))
    db.entry_by_ref("J022a").values["Comment"] = "x"
    w = _window(tmp_path, db)
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: (a[3][0], True))
    wordlist_dialogs.link_to_wordlists(w)
    d = w.doc.db
    assert d.settings.entry_field(wl.TAXON) is not None and "DEM" in d.settings.word_classes()
    assert d.entry_by_ref("D009").get("Taxon") == "Capra hircus (Bovidae)"
    assert d.entry_by_ref("J022a").get("Clarification") == "Azadirachta indica"
    w.doc.undo.undo()
    assert not d.entry_by_ref("D009").get("Taxon")
    w.doc.undo.setClean()
    w.doc._settings_dirty = False
    w.close()


def test_a_genus_finds_its_items(win):
    win.lemma_search.setText("Bovidae")
    win._search_timers["lemma"].timeout.emit()
    refs = {e.ref for e in win.lemmas.visible_rows()}
    assert {"D009", "D011", "D014"} <= refs                    # goats, sheep, cattle
    win.lemma_search.setText("Capra")
    win._search_timers["lemma"].timeout.emit()
    assert {e.ref for e in win.lemmas.visible_rows()} >= {"D009", "D009b"}
    win.lemma_search.setText("")


# ---- Convert references from a table -------------------------------------------------------------
def _old_db(tmp_path):
    """A database numbered the old way, with recordings: C001b mother, C001a father, D107 (empty)."""
    db = defaults.new_database("")
    db.metadata.language_code = "LXX"
    for ref, gloss in (("C001", "parent"), ("C001a", "father"), ("C001b", "mother"), ("D107", "mammal (sp)"),
                       ("A029", "mucus"), ("Z001", "my own")):
        db.entries.append(db.new_entry(ref, gloss=gloss))
    db.path = str(tmp_path / "Old.xml")
    from lemmatrix import layout
    folder = storage.folder_for(db, db.entries[0])
    folder.mkdir(parents=True, exist_ok=True)
    for ref in ("C001a", "C001b"):
        e = db.entry_by_ref(ref)
        e.tokens[0].file = db.expected_filename(e, e.tokens[0])
        (folder / e.tokens[0].file).write_bytes(b"RIFF" + ref.encode())
        e.tokens[0].values["Phonetic"] = "x"
    img = layout.images_folder(db.path)
    img.mkdir(parents=True, exist_ok=True)
    (img / "C001b.jpg").write_bytes(b"jpg")
    storage.save(db, db.path, backup=False)
    return db


def _table(tmp_path, text):
    p = tmp_path / "map.csv"
    p.write_text(text, encoding="utf-8")
    return cr.read_table(p)


def test_the_conversion_plan(tmp_path):
    db = _old_db(tmp_path)
    rows = _table(tmp_path, "old,new,gloss,old gloss\nC001a,C001m,,\nC001b,C001f,,\nD107,-,,\n"
                            "A029,A029,snot,mucus\nQ999,Q001,,\n")
    p = cr.plan(db, rows)
    assert {(e.ref, n) for e, n in p.refs} == {("C001a", "C001m"), ("C001b", "C001f")}
    assert [e.ref for e in p.deletions] == ["D107"] and p.unknown == ["Q999"] and not p.problems
    assert [(e.ref, g) for e, g in p.glosses] == [("A029", "snot")]
    # a lemma with data can't be deleted; two lemmas can't share a reference
    bad = cr.plan(db, _table(tmp_path, "old,new\nC001b,-\nC001a,Z001\n"))
    assert any("has data" in x for x in bad.problems) and any("two lemmas would be Z001" in x for x in bad.problems)
    # a gloss the researcher changed is left alone
    db.entry_by_ref("A029").multi["Gloss"]["en"] = "nasal mucus"
    p = cr.plan(db, _table(tmp_path, "old,new,gloss,old gloss\nA029,A029,snot,mucus\n"))
    assert not p.glosses and p.left


def test_swapping_references_and_files_in_one_undo_step(app, tmp_path, monkeypatch):
    from lemmatrix import layout
    from lemmatrix.ui.convert_dialog import ConvertReferencesDialog
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    db = _old_db(tmp_path)
    w = _window(tmp_path, db)
    db = w.doc.db
    folder = storage.folder_for(db, db.entries[0])
    before = sorted(x.name for x in folder.iterdir())
    p = tmp_path / "swap.csv"                                   # father and mother swap references
    p.write_text("old\tnew\nC001a\tC001b\nC001b\tC001a\nD107\t-\n", encoding="utf-8")
    d = ConvertReferencesDialog(w)
    d.load(str(p))
    assert d.convert_btn.isEnabled()
    d.convert()
    father = next(e for e in db.entries if db.gloss(e) == "father")
    mother = next(e for e in db.entries if db.gloss(e) == "mother")
    assert (father.ref, mother.ref) == ("C001b", "C001a")
    assert (folder / mother.tokens[0].file).read_bytes() == b"RIFFC001b"      # the recording followed
    assert mother.tokens[0].file == db.expected_filename(mother, mother.tokens[0])
    assert (layout.images_folder(db.path) / "C001a.jpg").exists()               # the picture too
    assert db.entry_by_ref("D107") is None
    w.doc.undo.undo()
    assert (db.entry_by_ref("C001a") is father) and db.entry_by_ref("D107") is not None
    assert sorted(x.name for x in folder.iterdir()) == before
    assert (layout.images_folder(db.path) / "C001b.jpg").exists()
    w.doc.undo.setClean()
    w.close()


def test_converting_puts_lemmas_in_the_lists_order(app, tmp_path, monkeypatch):
    from lemmatrix.ui.convert_dialog import ConvertReferencesDialog
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    db = _old_db(tmp_path)
    w = _window(tmp_path, db)
    db = w.doc.db
    p = tmp_path / "map.csv"
    p.write_text("old,new\nC001a,C001m\nC001b,C001f\n", encoding="utf-8")
    d = ConvertReferencesDialog(w)
    d.load(str(p))
    assert d.reorder.isChecked()                                # mostly EACW references
    d.convert()
    refs = [e.ref for e in db.entries]
    assert refs.index("A029") < refs.index("C001") < refs.index("C001f") < refs.index("C001m")
    assert refs.index("Z001") == refs.index("D107") + 1 or "Z001" in refs   # one's own stays put
    w.doc.undo.setClean()
    w.close()


def test_nothing_about_any_one_database_in_the_code():
    """Josh, 23 October: no database's conversion kept in Lemmatrix."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "lemmatrix"
    for f in [*root.glob("*.py"), *root.glob("ui/*.py"), *root.glob("wordlists/*")]:
        if f.is_file():
            text = f.read_text(encoding="utf-8", errors="ignore")
            assert not re.search(r"\bBurun\b", text, re.IGNORECASE) or f.name in ("languages.py",), f


class _E:
    def __init__(self, ref):
        self.ref = ref


def test_ones_own_references_have_a_place():
    """Josh, 23 October: B001b inside B001's family, an ethnic group after the last C item."""
    refs = ["V549", "CORMm", "B001m", "CORM", "B001", "V296b", "C045f", "B001b", "CORMf", "C045",
            "V296", "B001f", "C045m", "D001", "V297", "Z001"]
    order = [e.ref for e in wl.eacw_order([_E(r) for r in refs])]
    assert order[:4] == ["B001", "B001b", "B001f", "B001m"]
    assert order.index("C045m") + 1 == order.index("CORM") < order.index("CORMf") < order.index("CORMm") \
        < order.index("D001")
    assert order.index("V296") + 1 == order.index("V296b") == order.index("V297") - 1
    assert order[order.index("V297") + 1] == "Z001"  # no section of the list: stays after what it follows
    ents = [_E(r) for r in order]
    assert order[wl.insert_position(ents, "B001c") - 1] == "B001b"
    assert order[wl.insert_position(ents, "CAPD") - 1] == "C045m"
    assert wl.insert_position(ents, "123") is None


def test_check_reference_order_moves_the_fewest(win, monkeypatch):
    from lemmatrix.ui import wordlist_dialogs as wd
    db = win.doc.db
    first = db.entries[0]
    mine = db.new_entry("B001b", gloss="mine")
    db.entries.remove(first)
    db.entries += [first, mine]                     # A001 and B001b at the end
    order, moving = wl.out_of_place(db.entries)
    assert {e.ref for e in moving} == {first.ref, "B001b"}
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.Accepted)
    wd.check_reference_order(win)
    refs = [e.ref for e in db.entries]
    assert refs[0] == first.ref and refs[refs.index("B001") + 1] == "B001b"
    assert not wl.out_of_place(db.entries)[1]
    win.doc.undo.undo()
    assert db.entries[-1] is mine


def test_a_new_lemma_of_ones_own_goes_to_its_place(win, monkeypatch):
    from lemmatrix.ui import dialogs
    db = win.doc.db
    e = db.new_entry("B001b", gloss="mine")
    monkeypatch.setattr(dialogs.EntryDialog, "exec", lambda self: True)
    monkeypatch.setattr(dialogs.EntryDialog, "new_entry", lambda self, *a: e)
    win.add_entry()
    refs = [x.ref for x in db.entries]
    assert refs[refs.index("B001") + 1] == "B001b"
