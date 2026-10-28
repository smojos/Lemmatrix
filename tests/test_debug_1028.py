# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Debug, 28 October 2026 (Josh): Texts and utterances back on the text last shown; full screen's
sizes never kept; an utterance's reference edited by hand, and several moved and renumbered
(IDEAS.md idea 107)."""

from test_texts import _add_text  # noqa: F401  (fixtures)


# ---- the text last shown ------------------------------------------------------------------

def test_texts_and_utterances_opens_again_on_the_text_last_shown(win, tmp_path, monkeypatch):
    uw, t1 = _add_text(win, tmp_path, monkeypatch, "One")
    uw, t2 = _add_text(win, tmp_path, monkeypatch, "Two", src=tmp_path / "field2")
    uw.texts.select(t2)
    assert uw.texts.current() is t2
    uw.close()                                    # freed when closed: a new window next time
    uw = win.open_utterances()
    assert uw.texts.current() is t2               # it went back to T001
    win.doc.db.texts.remove(t2)                   # the text gone: the first one
    uw.close()
    uw = win.open_utterances()
    assert uw.texts.current() is t1


# ---- full screen ----------------------------------------------------------------------------

def test_full_screen_sizes_are_never_kept(win):
    uw = win.open_utterances()
    uw.show()
    uw.tabs.setCurrentIndex(0)
    outer = uw.split.sizes()
    uw.full_btn.click()
    assert uw.split.sizes()[1] == 0
    uw._winstate.save()                           # a resize or the window closing saves
    uw.close()
    uw = win.open_utterances()
    uw.show()
    assert not uw.full_screen()
    assert uw.split.sizes()[1] > 0 and uw.texts.page.sizes()[0] > 0
    assert abs(uw.split.sizes()[1] - outer[1]) < 40


def test_sizes_kept_by_an_earlier_full_screen_are_put_right(win):
    uw = win.open_utterances()
    uw.show()
    a, b = uw.split.sizes()
    uw.split.setSizes([a + b, 0])                 # as the version of 28 October morning kept them
    uw.texts.page.setSizes([0, sum(uw.texts.page.sizes())])
    uw._winstate.save()
    uw.close()
    uw = win.open_utterances()
    assert uw.split.sizes()[1] > 0 and uw.texts.page.sizes()[0] > 0


def test_the_cell_never_pulls_the_panel_up_in_full_screen(win):
    uw = win.open_utterances()
    uw.show()
    uw.full_btn.click()
    uw._fit_cell()
    assert uw.split.sizes()[1] == 0
    uw.full_btn.click()
    assert uw.split.sizes()[1] > 0


# ---- idea 107: references by hand -------------------------------------------------------------

def _utterances(win, refs, recorded=True):
    from lemmatrix import storage
    db = win.doc.db
    db.settings.auto_update_names = True
    folder = storage.utterance_folder(db)
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for ref in refs:
        u = db.new_utterance(ref, f"say {ref.lower()}")
        if recorded:
            u.token.file = db.expected_filename(u, u.token)
            (folder / u.token.file).write_bytes(ref.encode())
        db.utterances.append(u)
        out.append(u)
    uw = win.open_utterances()
    uw.refresh()
    return uw, folder, out


def test_a_reference_is_checked_and_written_the_databases_way(win):
    uw, _, (u1, u2) = _utterances(win, ["W001", "W002"], recorded=False)
    db = win.doc.db
    assert db.utterance_reference("w7", u1) == ("W007", "")
    assert db.utterance_reference("U 12", u1) == ("U012", "")
    assert db.utterance_reference("W001", u1) == ("W001", "")          # its own
    ref, why = db.utterance_reference("W002", u1)
    assert ref == "" and "W002" in why                                 # taken: refused
    assert db.utterance_reference("W000", u1)[0] == ""
    assert db.utterance_reference("hello", u1)[0] == ""
    assert db.utterance_reference("Q5", u1)[0] == ""                   # not an utterance category
    assert db.utterance_reference(db.entries[0].ref, u1)[0] == ""      # a lemma's


def test_change_reference_renames_the_recording_with_undo(win, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    uw, folder, (u,) = _utterances(win, ["W012"])
    old = u.token.file
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("w7", True))
    uw.change_reference(u)
    assert u.ref == "W007" and "W007" in u.token.file
    assert (folder / u.token.file).exists() and not (folder / old).exists()
    win.doc.undo.undo()
    assert u.ref == "W012" and (folder / old).exists()


def test_change_reference_refuses_one_that_is_taken(win, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    uw, _, (a, b) = _utterances(win, ["W001", "W002"])
    said = []
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("W002", True))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: said.append(a[2]))
    uw.change_reference(a)
    assert a.ref == "W001" and said and "W002" in said[0]


def test_several_move_and_are_renumbered_from_the_lowest_free_number(win, monkeypatch):
    uw, folder, us = _utterances(win, ["U005", "U002", "W003", "W001"])
    u5, u2, w3, w1 = us
    monkeypatch.setattr(uw, "_ask_category", lambda *a, **k: "W")
    uw.move_several([u5, w1, u2])                 # W001 among them: its number is free again
    # in reference order (U002, U005, W001), each the lowest free W number (W003 is taken)
    assert (u2.ref, u5.ref, w1.ref) == ("W001", "W002", "W004")
    assert w3.ref == "W003"
    for u in (u2, u5, w1, w3):
        assert (folder / u.token.file).exists() and u.ref in u.token.file
        assert (folder / u.token.file).read_bytes() in (b"U002", b"U005", b"W001", b"W003")
    assert (folder / u2.token.file).read_bytes() == b"U002"            # each kept its own recording
    assert (folder / w1.token.file).read_bytes() == b"W001"
    win.doc.undo.undo()                           # one undo step
    assert (u2.ref, u5.ref, w1.ref) == ("U002", "U005", "W001")
    assert (folder / w1.token.file).read_bytes() == b"W001"


def test_several_in_their_own_category_are_closed_up(win, monkeypatch):
    uw, folder, us = _utterances(win, ["W002", "W003", "W009"])
    monkeypatch.setattr(uw, "_ask_category", lambda *a, **k: "W")
    uw.move_several(us)
    assert [u.ref for u in us] == ["W001", "W002", "W003"]
    assert [(folder / u.token.file).read_bytes() for u in us] == [b"W002", b"W003", b"W009"]


def test_the_dialogue_header_edits_the_reference(win):
    from PySide6.QtWidgets import QMessageBox
    from lemmatrix.ui.token_dialog import Slot
    from lemmatrix.ui.utterances import UtteranceDialog
    uw, folder, (a, b) = _utterances(win, ["W001", "W002"])
    dlg = UtteranceDialog(win, [Slot(a, 0)], 0, uw)
    assert dlg.ref_edit.text() == "W001" and dlg.head_row.indexOf(dlg.ref_edit) == 0
    dlg.ref_edit.setText("W002")                  # taken: refused, nothing changes
    said = []
    QMessageBox.warning, keep = (lambda *x, **k: said.append(x[2])), QMessageBox.warning
    try:
        assert not dlg._commit()
    finally:
        QMessageBox.warning = keep
    assert a.ref == "W001" and said
    dlg.ref_edit.setText("w5")
    assert dlg._commit()
    assert a.ref == "W005" and "W005" in a.token.file and (folder / a.token.file).exists()
    assert dlg.ref_edit.text() == "W005"
    dlg.reject()
    win.doc.undo.undo()
    assert a.ref == "W001" and (folder / a.token.file).exists()
