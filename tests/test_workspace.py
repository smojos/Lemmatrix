# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""The workspace file (IDEAS.md idea 36, 21 October): the database's working state beside it.

The database keeps what describes the data or is needed to read it; the workspace keeps what
you're working on (saved matrices, rerecord flags, the spelling list, the session, the view,
filters, columns…); how it looks (widths, theme) stays on the computer."""

import shutil
from pathlib import Path

from lemmatrix import matrix as mx, storage, workspace as wsmod
from lemmatrix import filters as fl

from test_ui import SAMPLES, app, win  # noqa: F401 (fixtures)


def _matrix(name="Plurals"):
    return mx.MatrixConfig(name=name, kind=mx.LEMMA_TAG,
                           x=[mx.Spec.citation(), mx.Spec(frozenset({"Plural"}), mx.EXACT)], cell=["Phonetic"])


def test_round_trip(tmp_path):
    db = storage.load(SAMPLES / "Sample.xml")
    db.path = str(tmp_path / "Lex.xml")
    s = db.settings
    s.matrices = [_matrix()]
    s.spelling_words = ["Pade", "tilapia"]
    s.play_cell_on_click, s.pitch_style = True, "letters"
    tok = db.entries[1].tokens[0]
    tok.rerecord = True
    ws = wsmod.Workspace()
    ws.set("columns/lemma", ["ref", "f:Lemma"])
    ws.set("session", {"participants": ["SP1"]})
    ws.set("view", {"tab": 2, "filters": {"lemma": {"filters": {"f:Lemma": {"kind": "blanks"}}}}})
    storage.save(db, db.path, backup=False)
    wsmod.save(ws, db)
    text = (tmp_path / "Lex.workspace").read_text(encoding="utf-8")
    assert "<matrix name=\"Plurals\"" in text and f'<token id="{tok.id}">' in text and "<word>Pade</word>" in text
    xml = (tmp_path / "Lex.xml").read_text(encoding="utf-8")
    assert f'format="{storage.FORMAT_VERSION}"' in xml
    for gone in ("<matrix", "rerecord", "<spelling", "style=", "<display"):
        assert gone not in xml                                  # none of it in the database
    again = storage.load(db.path)
    assert not again.workspace_from_file and again.settings.matrices == []
    back = wsmod.load(tmp_path / "Lex.workspace", again)
    a = again.settings
    assert a.matrices == [_matrix()] and sorted(a.spelling_words) == ["Pade", "tilapia"]
    assert a.play_cell_on_click and a.pitch_style == "letters"
    assert again.entries[1].tokens[0].rerecord and not again.entries[0].tokens[0].rerecord
    assert back.get_list("columns/lemma") == ["ref", "f:Lemma"]
    assert back.get_dict("session") == {"participants": ["SP1"]}
    assert back.get_dict("view")["tab"] == 2


def test_an_unreadable_workspace_is_never_written_over(tmp_path):
    db = storage.load(SAMPLES / "Sample.xml")
    db.path = str(tmp_path / "Lex.xml")
    p = tmp_path / "Lex.workspace"
    p.write_text("<workspace><oops", encoding="utf-8")
    try:
        wsmod.load(p, db)
        assert False, "should not read"
    except wsmod.WorkspaceError:
        pass
    wsmod.save(wsmod.Workspace(path=str(p), unreadable=True), db)
    assert p.read_text(encoding="utf-8") == "<workspace><oops"


def test_filters_as_plain_data():
    for f in (fl.Blanks(), fl.NonBlanks(), fl.Flagged("Rerecord"), fl.TextFilter("dɪ", fl.START, True, False),
              fl.ChoiceFilter({"Plural", fl.CITATION_ITEM}, fl.EXACTLY)):
        assert fl.decode(fl.encode(f)) == f
    assert fl.decode({"kind": "nonsense"}) is None and fl.decode("x") is None


# ---- in the window -----------------------------------------------------------------------

def test_an_older_database_moves_its_working_state_out_quietly(win, tmp_path):
    db = win.doc.db                                   # the test sample is format 6
    assert db.workspace_from_file
    assert (tmp_path / "Sample.workspace").exists()          # made when it was opened
    assert win.doc.dirty                                     # so saving writes format 7
    db.settings.matrices.append(_matrix())
    db.entries[0].tokens[0].rerecord = True
    assert win.save()
    xml = (tmp_path / "Sample.xml").read_text(encoding="utf-8")
    assert f'format="{storage.FORMAT_VERSION}"' in xml and "rerecord" not in xml and "<matrix" not in xml
    text = (tmp_path / "Sample.workspace").read_text(encoding="utf-8")
    assert 'name="Plurals"' in text and db.entries[0].tokens[0].id in text
    assert any(f.suffix == ".workspace" for f in (tmp_path / "Backups").iterdir())   # a copy on saving


def test_saving_a_matrix_doesnt_mark_the_database_unsaved(win, tmp_path, monkeypatch):
    from lemmatrix.ui import main_window
    from lemmatrix.ui.main_window import LEMMA_TAG
    win.save()
    cfg = win.config_for(LEMMA_TAG)
    cfg.x = [mx.Spec.citation(), mx.Spec(frozenset({"Plural"}), mx.EXACT)]
    monkeypatch.setattr(main_window, "ask_matrix_name", lambda *a, **k: "Plurals")
    win.save_matrix(LEMMA_TAG)
    assert not win.doc.dirty
    win.doc.write_workspace()
    assert 'name="Plurals"' in (tmp_path / "Sample.workspace").read_text(encoding="utf-8")


def _format_7(win, tmp_path) -> Path:
    win.save()                                               # format 7, with its workspace beside it
    return tmp_path / "Sample.workspace"


def test_a_missing_workspace_asks(win, tmp_path, monkeypatch):
    from lemmatrix.ui.main_window import LEMMA_TAG
    ws = _format_7(win, tmp_path)
    win.doc.db.settings.matrices.append(_matrix())
    win.doc.write_workspace()
    kept = tmp_path / "elsewhere.workspace"
    shutil.move(ws, kept)
    path = win.doc.db.path
    answers = iter([None, str(kept), ""])
    asked = []
    monkeypatch.setattr(win, "_ask_missing_workspace", lambda db: asked.append(1) or next(answers))
    other = tmp_path / "other"
    other.mkdir()
    win.open_file(path)                                      # Cancel: not opened again
    assert asked == [1]
    win.open_file(path)                                      # Locate…: copied beside it and read
    assert ws.exists() and [m.name for m in win.doc.db.settings.matrices] == ["Plurals"]
    ws.unlink()
    win.open_file(path)                                      # Start a new workspace: the defaults
    assert win.doc.db.settings.matrices == [] and ws.exists()
    assert len(asked) == 3 and LEMMA_TAG


def test_each_database_comes_back_as_it_was_left(win, tmp_path):
    """Filters, searches, the pin, columns and the options row: each database its own (idea 36)."""
    win.save()                                               # (opening another asks to save first)
    db = win.doc.db
    win.lemmas.proxy.set_filter("WordClass", fl.ChoiceFilter({"NOUN"}))
    win.lemmas.filtersChanged.emit()
    win.all_search.setText("goat")
    win.lemmas.toggle_pin(db.entries[0])
    win.autoplay.setChecked(True)
    win.only_data.setChecked(True)
    win.doc.ws_set("columns/alldata", ["ref", "tags", "f:Phonetic"])
    win._save_view()
    win.doc.write_workspace()
    path = db.path
    other = tmp_path / "Other"                               # another database: nothing of these
    other.mkdir()
    shutil.copy2(SAMPLES / "Sample.xml", other / "Other.xml")
    win.open_file(str(other / "Other.xml"))
    assert not win.lemmas.proxy.filters and win.lemmas.proxy.pinned is None
    assert win.all_search.text() == "" and not win.autoplay.isChecked() and not win.only_data.isChecked()
    win.save()
    win.open_file(path)                                      # back: all as left
    assert "WordClass" in win.lemmas.proxy.filters
    assert win.lemmas.proxy.pinned == win.doc.db.entries[0].id
    assert win.all_search.text() == "goat"
    assert win.autoplay.isChecked() and win.only_data.isChecked()
    assert win.all_table.visible_keys() == ["ref", "tags", "f:Phonetic"]
    text = (tmp_path / "Sample.workspace").read_text(encoding="utf-8")
    assert "width" not in text.lower() and "geometry" not in text.lower()   # how it looks stays on the computer


def test_the_session_and_speaker_are_in_the_workspace(win, tmp_path):
    from lemmatrix.ui import chiprow as chips
    win.sess_rows[chips.PARTICIPANTS].set_keys(["SP1"])
    win._session_people_changed()
    win.set_speaker("SP1")
    win.doc.write_workspace()
    text = (tmp_path / "Sample.workspace").read_text(encoding="utf-8")
    assert 'name="session"' in text and 'name="session/speaker"' in text and '"SP1"' in text


def test_the_anonymous_backup_has_a_blank_workspace(win, tmp_path):
    from lemmatrix import anonymise
    win.doc.db.settings.matrices.append(_matrix())
    win.doc.ws_set("session", {"participants": ["SP1"]})
    anonymise.export(win.doc.db, win.doc.notebook, tmp_path / "anon", anonymise.Options())
    ws = next((tmp_path / "anon").glob("*.workspace"))
    text = ws.read_text(encoding="utf-8")
    assert "Plurals" not in text and "SP1" not in text and "<settings" in text


def test_full_backup_includes_the_workspace(win, tmp_path):
    from lemmatrix import layout
    win.save()
    assert tmp_path / "Sample.workspace" in layout.backup_files(win.doc.db.path)


def test_texts_and_utterances_filters_and_the_spelling_ignore_list_are_kept(win):
    uw = win.open_utterances()
    uw.search.setText("hare")
    uw.texts.search.setText("story")
    uw.close()
    uw = win.open_utterances()
    assert uw.search.text() == "hare" and uw.texts.search.text() == "story"
    uw.close()
    win.ignore_spelling("Tilapia")
    assert "tilapia" in win.spelling_ignored and win.doc.ws.get_list("spelling/ignored") == ["tilapia"]
