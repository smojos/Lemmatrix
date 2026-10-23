# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""What ɛλicit (IDEAS.md idea 19) needs from the rest of the program, built first (20 October):
second languages hidden by default, translations in them on tokens, the participants' consent
ticks and researchers' emails, and the Images folder."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from lemmatrix import anonymise, bulk, filenames, layout, storage  # noqa: E402
from lemmatrix import matrix as mx  # noqa: E402
from lemmatrix.model import Person  # noqa: E402

from test_texts import app, win  # noqa: E402,F401  (the same window)


# ---- people -------------------------------------------------------------------

def test_consent_ticks_and_email_are_saved(win, tmp_path):
    db = win.doc.db
    md = db.metadata
    p = md.participants[0]
    p.identifiable, p.audio_sharing = True, True
    md.participants[1].audio_sharing = False
    md.researchers = [Person("RS1", "Researcher", email="rs@example.org")]
    storage.save(db, tmp_path / "Saved.xml")
    text = (tmp_path / "Saved.xml").read_text(encoding="utf-8")
    assert 'identifiable="yes"' in text and 'audio-sharing="yes"' in text and 'email="rs@example.org"' in text
    back = storage.load(tmp_path / "Saved.xml").metadata
    assert back.participants[0].identifiable and back.participants[0].audio_sharing
    assert not back.participants[1].audio_sharing and not back.participants[1].identifiable
    assert back.researchers[0].email == "rs@example.org"


def test_the_ticks_are_always_written_yes_or_no(win, tmp_path):
    """Format 8 (idea 44): every researcher says identifiable= and every participant both ticks,
    so the file reads the same without knowing the defaults; no email, no email=."""
    db = win.doc.db
    for p in db.metadata.participants + db.metadata.researchers:
        p.identifiable = p.audio_sharing = False
        p.email = ""
    storage.save(db, tmp_path / "Saved.xml")
    text = (tmp_path / "Saved.xml").read_text(encoding="utf-8")
    assert 'identifiable="no" audio-sharing="no"' in text and "email=" not in text
    assert 'identifiable="yes"' not in text


def test_the_anonymous_backup_takes_out_emails_and_keeps_the_ticks(win):
    db = win.doc.db
    db.metadata.researchers = [Person("RS1", "Researcher", email="rs@example.org")]
    db.metadata.participants[0].audio_sharing = True
    out, _ = anonymise.anonymise(db, None, anonymise.Options(), anonymise.Report())
    assert all(not p.email for p in out.metadata.researchers + out.metadata.participants)
    assert out.metadata.participants[0].audio_sharing
    assert db.metadata.researchers[0].email == "rs@example.org"          # the original is untouched


def test_the_lists_dialog_edits_ticks_and_email(win):
    from PySide6.QtCore import Qt
    from lemmatrix.ui.lists_dialog import PeopleEditor
    db = win.doc.db
    ed = PeopleEditor(db, [Person("SP9", "Nine", identifiable=True)], True, lambda c: "")
    t = ed.table
    assert t.item(0, ed.col("identifiable")).checkState() == Qt.Checked
    t.item(0, ed.col("audio")).setCheckState(Qt.Checked)
    p = ed.people()[0]
    assert p.identifiable and p.audio_sharing and p.code == "SP9" and p.name == "Nine"
    rs = PeopleEditor(db, [Person("RS9", "Res", email="not an address")], False, lambda c: "")
    assert "email" in rs.problem()
    rs.table.item(0, rs.col("email")).setText("res@example.org")
    assert rs.problem() == "" and rs.people()[0].email == "res@example.org"


# ---- images -------------------------------------------------------------------

def test_image_names_follow_reference_and_tags(win, tmp_path):
    db = win.doc.db
    e = db.entries[0]
    cit = next(t for t in e.tokens if t.is_citation)
    plural = next((t for t in e.tokens if "Plural" in t.tags), None)
    assert filenames.image_stem(db, e, cit) == e.ref
    if plural is not None:
        assert filenames.image_stem(db, e, plural).startswith(e.ref + "_PL")
    folder = layout.images_folder(db.path)
    folder.mkdir(exist_ok=True)
    assert filenames.find_image(db, e, cit) is None
    (folder / f"{e.ref}.GIF").write_bytes(b"GIF89a")
    assert filenames.find_image(db, e, cit).name == f"{e.ref}.GIF"
    if plural is not None:
        assert filenames.find_image(db, e, plural) is None               # no falling back on the lemma's


def test_a_new_database_has_an_images_folder(tmp_path):
    layout.create_layout(tmp_path / "New.xml")
    assert (tmp_path / "Images").is_dir()


# ---- second languages ------------------------------------------------------------

def test_second_language_columns_exist_but_are_not_shown_by_default(win):
    keys = [c.key for c in win._all_columns()]
    assert "gloss:ar" in keys and "f:Translation:ar" in keys
    assert "gloss:ar" not in win._default_all_keys() and "f:Translation:ar" not in win._default_all_keys()
    assert "Gloss:ar" not in win._default_lemma_keys()


def test_editing_a_second_language_translation_in_all_data(win):
    row = win.all_table.model_.rows[0]
    before = row.token.get("Translation", "en")
    win._cell_edited(row, "f:Translation:ar", "ماعز")
    t = row.entry.tokens[row.index]
    assert t.get("Translation", "ar") == "ماعز" and t.get("Translation", "en") == before
    win.doc.undo.undo()
    assert not row.entry.tokens[row.index].get("Translation", "ar")


def test_configure_cell_offers_second_languages_unticked(win):
    db = win.doc.db
    keys = [k for k, _ in mx.cell_options(db)]
    assert keys.index("Translation:ar") == keys.index("Translation") + 1
    assert "Translation:ar" not in mx.DEFAULT_CELL
    e = db.entries[0]
    t = e.tokens[0]
    t.set("Translation", "عربي", "ar")
    assert mx.cell_text(db, t, "Translation:ar") == "عربي"
    assert mx.cell_text(db, t, "Translation") == t.get("Translation", "en")


def test_bulk_edit_can_set_second_language_translations(win):
    db = win.doc.db
    tg = bulk.target(db, bulk.TOKENS, "f:Translation:ar")
    assert tg.lang == "ar" and tg.title == "Translation (ar)"


def test_the_token_dialogue_has_other_languages_folded_away(win):
    from lemmatrix.ui.token_dialog import TokenDialog
    from lemmatrix.ui.token_dialog import Slot
    win.prefs.set_value("dialogs/other_languages", False)
    e = win.doc.db.entries[0]
    dlg = TokenDialog(win, [Slot(e, 0, tuple(e.tokens[0].tags))], 0)
    ed = dlg.other_edits[("Translation", "ar")]
    assert dlg.others_btn is not None and not dlg.others_btn.isChecked()
    assert ed.isHidden()
    dlg.others_btn.setChecked(True)
    assert not ed.isHidden() and win.prefs.get_bool("dialogs/other_languages")
    ed.setText("ماعز")
    dlg._collect()
    assert dlg.token.get("Translation", "ar") == "ماعز"
    assert dlg.token.get("Translation", "en") == e.tokens[0].get("Translation", "en")
    dlg.others_btn.setChecked(False)
    dlg.reject()
    win.prefs.set_value("dialogs/other_languages", False)


def test_the_lemma_dialogue_folds_the_arabic_gloss_away(win):
    from lemmatrix.ui.dialogs import EntryDialog
    win.prefs.set_value("dialogs/other_languages", False)
    e = win.doc.db.entries[0]
    dlg = EntryDialog(win, win.doc.db, e)
    ar = dlg.fields[("Gloss", "ar")]
    assert dlg.others_btn is not None and ar.isHidden()
    assert ar.text() == e.get("Gloss", "ar")                           # still saved as it was
    dlg.others_btn.setChecked(True)
    assert not ar.isHidden()
    win.prefs.set_value("dialogs/other_languages", False)
    dlg.reject()
