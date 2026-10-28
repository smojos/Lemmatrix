# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Templates with `>` for else and fields by name, label or abbreviation; the Wordlist export's
form as a template; field names that would call another field (IDEAS.md ideas 71–73, Josh,
26 October 2026)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lemmatrix import defaults, fieldkeys, storage, wordlists as wl  # noqa: E402
from lemmatrix.filenames import build_filename  # noqa: E402
from lemmatrix.model import FieldDef, Token  # noqa: E402


def _lists(db):
    s = db.settings
    return {"lemma": s.entry_fields, "token": s.token_fields, "text": s.text_fields}


# ---- what a field answers to ---------------------------------------------------------------

def test_tone_class_reserves_every_spelling_and_its_abbreviation():
    f = FieldDef("ToneClass", "Tone Class", abbr="tnc")
    for name in ("Tone Class", "tone Class", "Tone class", "tone class", "ToneClass", "toneClass",
                 "Toneclass", "toneclass", "tnc", "TNC", "tone  class"):
        assert fieldkeys.fold(name) in fieldkeys.keys(f), name


def test_a_new_name_that_would_call_another_field_is_refused():
    db = defaults.new_database()
    lists = _lists(db)
    f = FieldDef("Notes", "phonemic")                  # a lemma field labelled as a token field
    lists["lemma"].append(f)
    assert "Phonemic" in fieldkeys.clash(lists, "lemma", f)
    f.label, f.abbr = "Notes", "pht"                    # Phonetic's abbreviation
    assert "Phonetic" in fieldkeys.clash(lists, "lemma", f)
    f.abbr = "tags"                                     # a template's own word
    assert "{tags}" in fieldkeys.clash(lists, "lemma", f)
    f.abbr = "nts"
    assert fieldkeys.clash(lists, "lemma", f) == ""


def test_the_lemma_and_token_comment_are_one_name_not_a_clash():
    db = defaults.new_database()
    lists = _lists(db)
    for kind in ("lemma", "token"):
        for f in lists[kind]:
            assert fieldkeys.clash(lists, kind, f) == "", (kind, f.name)   # a new database is clean


def test_only_what_is_new_for_a_field_is_checked():
    db = defaults.new_database()
    lists = _lists(db)
    tone = next(f for f in lists["lemma"] if f.name == "ToneClass")
    tone.abbr = "pht"                                                  # Phonetic's, from an older file
    before = fieldkeys.keys(tone)
    assert fieldkeys.clash(lists, "lemma", tone, before) == ""         # already there: left alone
    tone.label = "Tags"
    assert "{tags}" in fieldkeys.clash(lists, "lemma", tone, before)  # new: checked
    gloss = next(f for f in lists["lemma"] if f.role == "gloss")
    assert fieldkeys.clash(lists, "lemma", gloss) == ""                # the word Gloss already means


def test_labels_may_not_hold_template_or_file_name_characters():
    assert fieldkeys.label_problem("Tone Class") == ""
    assert fieldkeys.label_problem("Tone {Class}") == "{ }"
    assert fieldkeys.label_problem("A>B") == ">"
    assert fieldkeys.label_problem("Who?") == "?"


# ---- the token fields' abbreviations (format 13) -------------------------------------------

def test_new_databases_and_older_files_have_the_abbreviations(tmp_path):
    db = defaults.new_database()
    assert {f.role: f.abbr for f in db.settings.token_fields} == {
        "phonetic": "pht", "phonemic": "phm", "morphemes": "mph", "constituents": "cns", "pitch": "pch",
        "translation": "trs", "comment": "com"}
    for f in db.settings.token_fields:
        f.abbr = ""
    p = tmp_path / "Old.xml"
    db.path = str(p)
    storage.save(db, p, backup=False)
    p.write_text(p.read_text(encoding="utf-8").replace(f'format="{storage.FORMAT_VERSION}"', 'format="12"'),
                 encoding="utf-8")
    back = storage.load(p)
    assert back.upgraded and back.settings.token_field("phonemic").abbr == "phm"
    back.settings.token_field("phonemic").abbr = "pm"                 # a changed one is kept
    storage.save(back, p, backup=False)
    assert storage.load(p).settings.token_field("phonemic").abbr == "pm"


# ---- soundfile names ------------------------------------------------------------------------

def _entry(db):
    e = db.new_entry("D009", lemma="", gloss="goat")
    t = Token(tags=[])
    t.set("Phonetic", "dʌːm")
    e.tokens = [t]
    db.entries.append(e)
    return e, t


def test_soundfile_names_take_else_and_abbreviations():
    db = defaults.new_database()
    e, t = _entry(db)
    s = db.settings
    s.filename_pattern = "{reference}_{phm>pht}"
    assert build_filename(db, e, t) == "D009_dʌːm.wav"               # no Phonemic: the Phonetic
    t.set("Phonemic", "dʌ́ʌm")
    assert build_filename(db, e, t) == "D009_dʌ́ʌm.wav"
    s.filename_pattern = "{reference}_{Word Class}"                  # a label with a space, any case
    e.set(s.entry_field("word-class").name, "NOUN")
    assert build_filename(db, e, t) == "D009_NOUN.wav"


def test_the_default_soundfile_names_are_unchanged():
    db = defaults.new_database()
    e, t = _entry(db)
    e.file_gloss = "goat"
    s = db.settings
    s.filename_pattern = "{reference}_{gloss}_{tags}"
    assert build_filename(db, e, t) == "D009_goat.wav"               # {gloss} still the file gloss


# ---- the Wordlist export's form --------------------------------------------------------------

def test_the_default_form_is_phonemic_else_phonetic_and_the_word_class():
    db = defaults.new_database(wl.SWADESH)
    s = db.settings
    e = db.entries[0]
    assert wl.export_form(db, e) == ""                                # not collected: blank, no word class
    e.tokens[0].set(s.token_field("phonetic").name, "ʔàbɔ̀")
    wc = e.get(s.entry_field("word-class").name)
    assert wl.export_form(db, e) == " ".join(x for x in ("ʔàbɔ̀", wc) if x)
    e.tokens[0].set(s.token_field("phonemic").name, "ʔàbɔ")
    assert wl.export_form(db, e).startswith("ʔàbɔ ") or wl.export_form(db, e) == "ʔàbɔ"
    assert wl.export_form(db, e, "{pht}") == "ʔàbɔ̀"                   # an abbreviation
    assert wl.export_form(db, e, "{Lemma>Phonetic} [{Gloss}]") == "ʔàbɔ̀ [I]"


def test_a_template_name_that_calls_nothing_is_reported():
    db = defaults.new_database()
    assert wl.template_unknown(db, "{Phonemic>Phonetic} {Word Class}") == []
    assert wl.template_unknown(db, "{Phonemik} {tnc}") == ["Phonemik", "tnc"]


def test_the_export_dialog_keeps_its_template(win):
    from lemmatrix.ui.wordlist_dialogs import WordlistExportDialog
    d = WordlistExportDialog(win)
    assert d.template_text() == wl.DEFAULT_TEMPLATE and d.preset.currentData() == wl.DEFAULT_TEMPLATE
    d.template.setText("{pht} {Gloss}")
    assert d.preset.currentData() is None                            # Custom…
    assert win.doc.ws.get(wl.TEMPLATE_KEY) == "{pht} {Gloss}"         # the database's workspace
    d.template.setText("{pht} {nothing}")
    assert "nothing" in d.example.text()
    d.reject()
    again = WordlistExportDialog(win)
    assert again.template_text() == "{pht} {nothing}"
    again.reject()


# ---- Edit → Fields ---------------------------------------------------------------------------

def test_edit_fields_warns_and_refuses_a_calling_name(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from lemmatrix.ui.fields_dialog import FieldsDialog
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    dlg = FieldsDialog(win, win.doc.db)
    row = next(i for i, f in enumerate(dlg.lists["token"]) if f.role == "phonetic")
    dlg.widgets["token"].setCurrentRow(row)
    dlg.abbr.setText("phm")
    dlg.abbr.textEdited.emit("phm")
    assert not dlg.problem.isHidden() and "Phonemic" in dlg.problem.text()
    dlg.accept()
    assert warned and dlg.result() != 1                     # refused
    dlg.abbr.setText("ph{")
    dlg.abbr.textEdited.emit("ph{")
    assert "{" in dlg.problem.text()
    dlg.abbr.setText("pht")
    dlg.abbr.textEdited.emit("pht")
    assert dlg.problem.isHidden()
    dlg.reject()


# ---- the edit dialogues' labels --------------------------------------------------------------

def test_abbreviated_labels_with_the_name_in_the_hover(win, monkeypatch):
    from lemmatrix.ui import widgets
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    from PySide6.QtWidgets import QLabel
    monkeypatch.setattr(widgets, "ABBREVIATE", True)
    f = win.doc.db.settings.token_field("phonetic")
    assert widgets.caption(f) == f.abbr
    dlg = TokenDialog(win, [Slot(win.doc.db.entries[0], 0)], 0)
    labels = {lbl.text(): lbl.toolTip() for lbl in dlg.findChildren(QLabel)}
    assert labels.get(f.abbr) == f.title
    dlg.reject()
    monkeypatch.setattr(widgets, "ABBREVIATE", False)
    assert widgets.caption(f) == f.title
