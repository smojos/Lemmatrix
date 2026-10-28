# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""19 October, evening: protected core fields, tag safety, tag descriptions, utterances in the tools,
moving tokens to another lemma."""

import os


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from lemmatrix import export, storage  # noqa: E402
from lemmatrix.defaults import ensure_core_fields, new_database  # noqa: E402
from lemmatrix.model import FieldDef  # noqa: E402



# ---- protected core fields --------------------------------------------------------------

def test_core_fields_cant_be_deleted():
    s = new_database().settings
    for kind in (s.entry_fields, s.token_fields, s.text_fields):
        comment = next(f for f in kind if f.name == "Comment")
        assert comment.role == "comment" and comment.builtin and comment.is_comment
    for role in ("phonetic", "phonemic", "morphemes", "pitch", "translation"):
        assert s.token_field(role).builtin
    assert not s.entry_field("ToneClass").builtin


def test_missing_core_fields_come_back_and_comments_get_their_role(tmp_path):
    db = new_database()
    s = db.settings
    s.token_fields = [f for f in s.token_fields if f.role not in ("morphemes", "comment")]
    s.token_fields.append(FieldDef("Comments"))                   # an older file's plain comment field
    s.entry_fields = [f if f.role != "comment" else FieldDef("Comment") for f in s.entry_fields]
    restored = ensure_core_fields(s)
    assert restored == ["Morphemes"]                                  # Comments only got its role
    assert [f.name for f in s.token_fields][:4] == ["Phonetic", "Phonemic", "Morphemes", "Constituents"]
    assert s.token_field("comment").name == "Comments"
    assert s.entry_field("comment").name == "Comment"
    db.path = str(tmp_path / "x.xml")
    storage.save(db, backup=False)
    again = storage.load(db.path)
    assert not again.load_notes and again.settings.token_field("comment").name == "Comments"
    # deleted outside Lemmatrix (or before it was protected): restored on opening, with a note
    text = open(db.path, encoding="utf-8").read().replace('<field name="Morphemes" role="morphemes" abbr="mph" />', "")
    open(db.path, "w", encoding="utf-8").write(text)
    db3 = storage.load(db.path)
    assert db3.settings.token_field("morphemes") is not None
    assert any("Morphemes" in n for n in db3.load_notes)


def test_fields_dialog_greys_delete_for_core_fields(win):
    from lemmatrix.ui.fields_dialog import FieldsDialog
    dlg = FieldsDialog(win, win.doc.db)
    names = [f.name for f in dlg.lists["token"]]
    dlg.widgets["token"].setCurrentRow(names.index("Morphemes"))
    assert not dlg.delete_buttons["token"].isEnabled()
    assert "not deleted" in dlg.delete_buttons["token"].toolTip()
    dlg.widgets["lemma"].setCurrentRow([f.name for f in dlg.lists["lemma"]].index("ToneClass"))
    assert dlg.delete_buttons["lemma"].isEnabled()
    dlg.reject()


# ---- tag safety ------------------------------------------------------------------------

def _tag_item(dlg, name):
    from lemmatrix.ui.dialogs import NAME
    return next(it for it in dlg._tag_items() if it.text(NAME) == name)


def test_deleting_a_used_tag_takes_it_off_or_is_refused(win, monkeypatch):
    from lemmatrix.ui.dialogs import TagStructureDialog
    db = win.doc.db
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    dlg = TagStructureDialog(win, db)
    dlg.tree.setCurrentItem(_tag_item(dlg, "Genitive"))
    dlg._delete()                                   # D001 PL+GEN and PL would both be PL
    assert warned and "D001" in warned[0] and "two tokens" in warned[0]
    assert _tag_item(dlg, "Genitive") is not None and not dlg.deleted_tags()
    frame = next(t.name for t, _ in db.settings.tags.tags() if t.code.lower() == "f2")
    dlg.tree.setCurrentItem(_tag_item(dlg, frame))
    dlg._delete()
    assert dlg.deleted_tags() == {frame}
    goat = db.entry_by_ref("D001")
    t = next(t for t in goat.tokens if frame in t.tags)
    win._apply_tags(dlg)
    t = next(x for x in db.entry_by_ref("D001").tokens if x.id == t.id)
    assert frame not in t.tags and db.settings.tags.tag(frame) is None
    # names update automatically in the sample: the recording follows the new name
    assert t.file == "LXX-VXX_D001_goat_PL-xH.wav"
    assert (storage.sound_folder(db) / t.file).exists()


def test_changed_codes_offer_to_rename_only_their_recordings(win, monkeypatch):
    from lemmatrix.ui.dialogs import CODE, TagStructureDialog
    db = win.doc.db
    db.settings.auto_update_names = False
    goat = db.entry_by_ref("D001")
    sg = next(t for t in goat.tokens if t.tags == ["Singular", "isolation"])
    asked = []

    def fake_exec(box):
        asked.append(box.text())
        box._clicked = next(b for b in box.buttons() if b.text() == "Rename")
        return 0
    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box._clicked)
    dlg = TagStructureDialog(win, db)
    _tag_item(dlg, "Singular").setText(CODE, "SING")
    win._apply_tags(dlg)
    goat = db.entry_by_ref("D001")
    sg = next(t for t in goat.tokens if t.id == sg.id)
    assert asked and "codes changed" in asked[0]
    assert sg.file == "LXX-VXX_D001_goat_SING.wav"
    assert (storage.sound_folder(db) / sg.file).exists()
    pl = next(t for t in goat.tokens if t.tags == ["Plural", "isolation"])
    assert pl.file == "LXX-VXX_D001_goat_PL.wav"                 # left alone
    win.doc.undo.undo()                                          # the renames are one undo step
    sg = next(t for t in db.entry_by_ref("D001").tokens if t.id == sg.id)
    assert sg.file == "LXX-VXX_D001_goat_SG.wav"


def test_leaving_names_out_of_date(win, monkeypatch):
    from lemmatrix.ui.dialogs import CODE, TagStructureDialog
    db = win.doc.db
    db.settings.auto_update_names = False

    def fake_exec(box):
        box._clicked = next(b for b in box.buttons() if b.text().startswith("Leave"))
        return 0
    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box._clicked)
    dlg = TagStructureDialog(win, db)
    _tag_item(dlg, "Plural").setText(CODE, "PLU")
    win._apply_tags(dlg)
    pl = next(t for t in db.entry_by_ref("D001").tokens if t.tags == ["Plural", "isolation"])
    assert pl.file == "LXX-VXX_D001_goat_PL.wav"
    assert db.expected_filename(db.entry_by_ref("D001"), pl) == "LXX-VXX_D001_goat_PLU.wav"


# ---- tag descriptions -----------------------------------------------------------------

def test_tag_and_group_descriptions_are_kept_and_shown(win, tmp_path):
    from lemmatrix.ui.dialogs import DESC, NAME, TagStructureDialog
    db = win.doc.db
    dlg = TagStructureDialog(win, db)
    _tag_item(dlg, "Plural").setText(DESC, "more than one")
    number = next(it for it in (dlg.tree.topLevelItem(0).child(i)
                                for i in range(dlg.tree.topLevelItem(0).childCount()))
                  if it.text(NAME) == "Number")
    number.setText(DESC, "how many")
    win._apply_tags(dlg)
    ts = db.settings.tags
    assert ts.tag("Plural").description == "more than one"
    assert next(g for g in ts.all_groups() if g.name == "Number").description == "how many"
    assert ts.tag_tip(["Plural", "isolation"]) == "Plural, isolation\nPlural: more than one"
    assert ts.tag_tip([]) == "Citation (no tags)"
    path = tmp_path / "d.xml"
    storage.save(db, path, backup=False)
    again = storage.load(path).settings.tags
    assert next(g for g in again.all_groups() if g.name == "Number").description == "how many"
    # All data's Tags column shows it
    col = next(c for c in win.all_table.model_.columns if c.key == "tags")
    row = next(r for r in win.all_table.model_.rows if r.token.tags == ["Plural", "isolation"])
    assert "more than one" in col.tooltip(row)
    header, rows = export.tag_structure_table(db)
    assert header[:3] == ["Group", "Tag", "Code"]
    assert ["NOUN › Number", "Plural", "PL", "", "", "more than one"] in rows
    assert ["NOUN › Number", "", "", "", "NOUN", "how many"] in rows


# ---- utterances in Check spelling, CSV export and Find missing recordings ----------------

def _utterance(db, ref="W001", label="hare ran", translation="the hare ran quikly"):
    u = db.new_utterance(ref, label, speaker="SP1")
    u.token.set("Translation", translation, "en", True)
    db.utterances.append(u)
    return u


def test_utterances_are_spell_checked(win):
    from lemmatrix import spelling
    db = win.doc.db
    u = _utterance(db)
    hits = {x.word: x for x in spelling.scan(db, win.spell_checker)}
    assert "quikly" in hits and hits["quikly"].occurrences[0].entry is u
    pairs = spelling.replacements(db, hits["quikly"], "quickly")
    win.doc.apply_changes("Spelling", pairs)
    assert db.utterances[0].token.get("Translation", "en") == "the hare ran quickly"


def test_entire_database_export_has_utterances():
    db = new_database()
    db.entries.append(db.new_entry("D001", "ɗæær", "goat"))
    _utterance(db)
    header, rows = export.database_table(db)
    assert header[:2] == ["Reference", "Kind"]
    row = next(r for r in rows if r[1] == "Utterance")
    assert row[0] == "W001" and row[header.index("Gloss in file names")] == "hare ran"
    assert "the hare ran quikly" in row
    assert all(r[1] == "Lemma" for r in rows if r[0] != "W001")
    # without utterances the export is as before (no Kind column)
    assert export.database_table(new_database())[0][0:2] != ["Reference", "Kind"]


def test_find_missing_recordings_links_utterances(win):
    db = win.doc.db
    u = _utterance(db)
    folder = storage.utterance_folder(db)
    folder.mkdir(parents=True, exist_ok=True)
    name = db.expected_filename(u, u.token)
    (folder / name).write_bytes(b"RIFF")
    (folder / "LXX-VXX_W0012_other.wav").write_bytes(b"RIFF")      # W0012 isn't W001
    found, lost = win.missing_recordings()
    assert [(e.ref, n) for e, _, n, _ in found] == [("W001", name)]
    win.find_missing_recordings()
    assert db.utterances[0].token.file == name


# ---- moving a token to another lemma ---------------------------------------------------

def _move(win, monkeypatch, ref, tags, to, answer="Add"):
    """Select the token of ref with these tags in All data and move it to the lemma to."""
    from lemmatrix.ui import main_window as mw, move_dialog
    db = win.doc.db
    src = db.entry_by_ref(ref)
    i = next(i for i, t in enumerate(src.tokens) if t.tags == tags)
    target = db.entry_by_ref(to) if isinstance(to, str) else to

    class Fake:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return True

        def chosen(self):
            return target
    monkeypatch.setattr(move_dialog, "MoveTokenDialog", Fake)

    def fake_exec(box):
        box._clicked = next(b for b in box.buttons() if b.text().replace("&", "").startswith(answer))
        return 0
    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box._clicked)
    win.tabs.setCurrentIndex(mw.ALL_DATA)
    win.refresh()
    win.all_table.select_row(mw.TokenRow(src, i))
    t = src.tokens[i]
    win.move_token()
    return src, target, t


def test_move_a_token_with_its_recording_and_undo(win, monkeypatch):
    db = win.doc.db
    folder = storage.sound_folder(db)
    src, sheep, t = _move(win, monkeypatch, "D001", ["Plural", "before H", "isolation", "f2"], "D003")
    moved = next(x for x in sheep.tokens if x.id == t.id)          # same id: notebook links follow
    assert moved.tags == t.tags and moved.get("Phonetic") == t.get("Phonetic")
    assert all(x.id != t.id for x in src.tokens)
    assert moved.file == "LXX-VXX_D003_sheep_PL-xH-f2.wav"
    assert (folder / moved.file).exists() and not (folder / t.file).exists()
    win.doc.undo.undo()                                             # one step: tokens and recording
    assert any(x.id == t.id for x in src.tokens) and all(x.id != t.id for x in sheep.tokens)
    assert (folder / t.file).exists() and not (folder / moved.file).exists()


def test_same_tags_get_an_example_tag_or_move_as_they_are(win, monkeypatch):
    db = win.doc.db
    _, sheep, t = _move(win, monkeypatch, "D001", ["Plural", "isolation"], "D003", answer="Add")   # Add x1
    moved = next(x for x in sheep.tokens if x.id == t.id)
    assert "Example 1" in moved.tags and moved.file == "LXX-VXX_D003_sheep_PL-x1.wav"
    _, sheep, t = _move(win, monkeypatch, "D002", ["Plural", "isolation"], "D003", answer="Move it")   # as it is
    moved = next(x for x in sheep.tokens if x.id == t.id)
    assert moved.tags == ["Plural", "isolation"] and moved.file == "LXX-VXX_D002_lion_PL.wav"
    _, _, t = _move(win, monkeypatch, "E001", ["Plural", "Genitive", "isolation"], "D002", answer="Cancel")  # Cancel
    assert any(x.id == t.id for x in db.entry_by_ref("E001").tokens)


def test_a_citation_token_takes_an_empty_citations_place(win, monkeypatch):
    db = win.doc.db
    cow = db.new_entry("D004", "naa", "cow", "NOUN")
    db.entries.append(cow)
    _, cow, t = _move(win, monkeypatch, "D001", [], cow)
    assert len(cow.tokens) == 1 and cow.tokens[0].id == t.id
    assert cow.tokens[0].file == "LXX-VXX_D004_cow.wav"
    assert all(x.tags for x in db.entry_by_ref("D001").tokens)        # the old lemma just loses it


def test_moving_to_another_word_class_marks_unusual_tags(win, monkeypatch):
    from lemmatrix import matrix as mx
    db = win.doc.db
    db.settings.auto_update_names = False
    _, eat, t = _move(win, monkeypatch, "D001", ["Plural", "Genitive", "isolation"], "V001")
    moved = next(x for x in eat.tokens if x.id == t.id)
    assert mx.unusual_notes(db, eat, moved.tags)                       # Plural, Genitive: NOUN groups
    assert moved.file == "LXX-VXX_D001_goat_PL-GEN.wav"               # names not updated automatically
    assert "out of date" in win.statusBar().currentMessage()


def test_move_dialog_searches_and_puts_the_same_word_class_first(win):
    from lemmatrix.ui.move_dialog import MoveTokenDialog
    db = win.doc.db
    eat = db.entry_by_ref("V001")
    dlg = MoveTokenDialog(win, db, eat, 0)
    refs = [dlg.list.item(i).data(Qt.UserRole).ref for i in range(dlg.list.count())]
    assert refs[0] == "V002" and "V001" not in refs and len(refs) == len(db.entries) - 1
    dlg.find.setText("SHEEP")
    assert [dlg.list.item(i).data(Qt.UserRole).ref for i in range(dlg.list.count())] == ["D003"]
    assert dlg.chosen().ref == "D003"
    dlg.find.setText("zzz")
    assert dlg.list.count() == 0 and not dlg.buttons.buttons()[0].isEnabled()
    dlg.reject()
