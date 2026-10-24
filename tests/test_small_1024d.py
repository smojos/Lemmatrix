# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Josh's small v0 ideas of 24 October evening: the database's setup sent with a report (idea 50),
Hide empty lemmas in the lemma list (55), the lemma dialogue's More arrow (60), and Tone Class
and Inflection Class before Stem type."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from lemmatrix import report, setup_export, storage  # noqa: E402
from lemmatrix.defaults import default_settings, new_database  # noqa: E402
from test_ui import app, win  # noqa: E402,F401


def _settle():
    for _ in range(5):
        QApplication.processEvents()


# ---- the setup with a report (idea 50) -----------------------------------------------------

def test_the_setup_holds_no_data(win, tmp_path):
    db = win.doc.db
    assert db.entries and db.metadata.participants
    path = setup_export.write(db, tmp_path)
    assert path.name.startswith("Lemmatrix setup ")
    out = storage.load(path)
    assert out.entries == [] and out.utterances == [] and out.texts == []
    md = out.metadata
    assert md.participants == [] and md.researchers == [] and md.locations == []
    assert md.language_code == "LXX" and md.variety_code == "VXX"
    assert [f.name for f in out.settings.entry_fields] == [f.name for f in db.settings.entry_fields]
    assert [t.name for t, _ in out.settings.tags.tags()] == [t.name for t, _ in db.settings.tags.tags()]
    text = path.read_text(encoding="utf-8")
    for p in db.metadata.participants + db.metadata.researchers:
        if p.name:
            assert p.name not in text
    assert db.entries                                   # the database itself is untouched
    second = setup_export.write(db, tmp_path)
    assert second != path and second.exists()           # never over an earlier one


def test_the_report_names_the_attachment():
    assert "Attached%3A%20Lemmatrix%20setup" in report.mailto("feature", "Lemmatrix setup 2026-10-24.xml")
    assert "Attached" not in report.mailto("bug")


def test_send_report_offers_the_setup(win, monkeypatch, tmp_path):
    from PySide6.QtGui import QDesktopServices
    urls, opened = [], []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda u: urls.append(u.toString()) or True)
    monkeypatch.setattr(win, "open_folder", lambda f: opened.append(f))
    pick = {"text": "Make the setup file"}

    def fake_exec(box):
        box._clicked = next(b for b in box.buttons() if b.text() == pick["text"])
        return 0
    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: getattr(box, "_clicked", None))
    win.send_report("feature")
    assert opened and any("Attached" in u for u in urls)
    pick["text"] = "Just the email"
    urls.clear()
    win.send_report("bug")
    assert urls and "Attached" not in urls[-1]
    pick["text"] = "Cancel"
    urls.clear()
    win.send_report("bug")
    assert urls == []


# ---- Hide empty lemmas (idea 55) -----------------------------------------------------------

def test_hide_empty_lemmas_leaves_out_lemmas_with_no_token_data(win):
    db = win.doc.db
    empty = db.new_entry("D999", gloss="nothing yet")
    db.entries.append(empty)
    win._setup_columns()
    win.refresh()
    _settle()
    t = win.lemmas
    shown = set(id(r) for r in t.visible_rows())
    assert id(empty) in shown
    win.hide_empty.setChecked(True)
    _settle()
    rows = t.visible_rows()
    assert empty not in rows and rows
    assert all(any(tok.has_content() for tok in e.tokens) for e in rows)
    assert win.doc.ws.get_bool("lemmas/hide_empty")
    win.hide_empty.setChecked(False)
    _settle()
    assert empty in t.visible_rows()
    assert not win.doc.ws.get_bool("lemmas/hide_empty")


# ---- the More arrow (idea 60) --------------------------------------------------------------

def test_the_lemma_dialogue_shows_only_lemma_gloss_and_word_class_at_first(win):
    from lemmatrix.ui.dialogs import EntryDialog, default_more
    db = win.doc.db
    more = default_more(db)
    roles = {f.name: f.role for f in db.settings.entry_fields}
    assert all(roles[n] not in ("lemma", "gloss", "word-class") for n in more)
    assert "ToneClass" in more and "Comment" in more
    win.prefs.set_value("dialogs/lemma_more", False)
    dlg = EntryDialog(win, db, db.entries[0])
    dlg.show()
    _settle()
    assert dlg.more_btn is not None and not dlg.more_btn.isChecked()
    tone = dlg.fields[("ToneClass", "")]
    lemma = dlg.fields[(db.settings.entry_field("lemma").name, "")]
    assert not tone.isVisible() and lemma.isVisible()
    dlg.more_btn.setChecked(True)
    _settle()
    assert tone.isVisible()
    assert win.prefs.get_bool("dialogs/lemma_more")           # remembered on this computer
    dlg.reject()
    win.prefs.set_value("dialogs/lemma_more", False)


def test_the_more_arrow_counts_what_is_filled(win):
    from lemmatrix.ui.dialogs import EntryDialog
    db = win.doc.db
    e = db.entries[0]
    e.set("ToneClass", "H")
    dlg = EntryDialog(win, db, e)
    assert "1 filled" in dlg.more_btn.text() or "filled" in dlg.more_btn.text()
    dlg.reject()


def test_edit_fields_under_more_is_kept_in_the_workspace(win, monkeypatch):
    from lemmatrix.ui import main_window
    from lemmatrix.ui.dialogs import EntryDialog, more_fields

    def fake_exec(dlg):
        for f in dlg.lists["lemma"]:
            if f.name == "ToneClass":
                f._more = False                         # Tone Class always shown
        return 1
    monkeypatch.setattr(main_window.FieldsDialog, "exec", fake_exec)
    monkeypatch.setattr(main_window.FieldsDialog, "apply", lambda dlg: False)
    win.edit_fields()
    db = win.doc.db
    assert "ToneClass" not in more_fields(win, db)
    assert "ToneClass" not in win.doc.ws.get_list("lemma_dialog/more")
    dlg = EntryDialog(win, db, db.entries[0])
    win.prefs.set_value("dialogs/lemma_more", False)
    dlg.show()
    _settle()
    assert dlg.fields[("ToneClass", "")].isVisible()
    dlg.reject()


# ---- the fields' order --------------------------------------------------------------------

def test_tone_and_inflection_class_come_before_stem_type():
    names = [f.name for f in default_settings().entry_fields]
    wc, tc, ic, st = (names.index(n) for n in ("WordClass", "ToneClass", "InflectionClass", "StemType"))
    assert wc < tc < ic < st
    names = [f.name for f in new_database().settings.entry_fields]
    assert names.index("ToneClass") < names.index("StemType")
