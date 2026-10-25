# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Snapshots (Josh, 24 October; IDEAS.md idea 16): a searchable list like Questions and To Dos. The
camera takes one into the day; View → Snapshots and the notebook's tab restore, rename, pin, link
and delete; a hypothesis citing a deleted snapshot keeps its own copy; badges on the app bar."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from test_texts import app, win  # noqa: E402,F401

VIEW = {"tab": 1, "lemma": "D001"}


def test_snapshots_round_trip_in_the_notebook(tmp_path):
    from lemmatrix import notebook as nb
    book = nb.Notebook()
    s, snap = nb.take_snapshot(book, "2026-10-16", VIEW, "Lemma/Tag · D001", "10:15")
    snap.pinned = True
    nb.save(book, tmp_path / "x.notebook")
    text = (tmp_path / "x.notebook").read_text(encoding="utf-8")
    assert 'format="4"' in text and "<snapshot " in text and 'pinned="yes"' in text
    back = nb.load(tmp_path / "x.notebook")
    (s2, x), = back.all_snapshots()
    assert (x.id, x.name, x.view, x.time, x.pinned) == (snap.id, "Lemma/Tag · D001", VIEW, "10:15", True)
    assert not back.dirty and nb.matches(s2, None, "lemma/tag")


def test_older_snapshot_links_go_into_the_list(tmp_path):
    from lemmatrix import hypotheses as hy, notebook as nb
    book = nb.Notebook()
    j = hy.Journal(book)
    h = hy.make(book, j, "2026-10-16", "Tone spreads")
    hy.add_link(book, j, "2026-10-16", h, hy.snapshot_link(VIEW, "Lemma/Tag · D001", date="2026-10-16"))
    nb.save(book, tmp_path / "x.notebook")
    back = nb.load(tmp_path / "x.notebook")         # the link had no target: listed on opening
    assert back.upgraded and back.dirty
    (s, snap), = back.all_snapshots()
    ln = back.hypotheses[0].links[0]
    assert s.date == "2026-10-16" and ln.target == snap.id and snap.view == VIEW
    assert hy.label(None, back, ln) == "Lemma/Tag · D001"


def test_a_deleted_snapshot_still_restores_from_its_hypothesis():
    from lemmatrix import hypotheses as hy, notebook as nb
    book = nb.Notebook()
    _, snap = nb.take_snapshot(book, "2026-10-16", VIEW, "All data · 98 lemmas")
    ln = hy.snapshot_link(snap.view, snap.name, target=snap.id)
    snap.name = "Plurals"                           # renamed: the link follows the name
    assert hy.label(None, book, ln) == "Plurals"
    nb.delete_snapshot(book, snap)
    assert not book.all_snapshots()
    assert not hy.is_gone(None, book, ln) and hy.find(None, book, ln) == VIEW
    assert "deleted from the list" in hy.label(None, book, ln)
    same = hy.snapshot_link(VIEW, "x", target=snap.id)
    assert ln.same_item(same) and not ln.same_item(hy.snapshot_link(VIEW, "x", target="other"))


def test_the_camera_takes_one_with_undo_and_a_history_line(win):
    from lemmatrix import notebook as nb
    book = win.doc.notebook
    day = win.work_date()
    before = len(book.all_snapshots())
    s, snap = win.take_snapshot(animate=False)
    assert len(book.all_snapshots()) == before + 1 and snap.view == win.view_state()
    assert nb.HISTORY_HEADINGS[nb.SNAPSHOT_HISTORY] in s.notes and snap.name in s.notes
    assert win.badge_counts()["snapshots"] >= 1
    win.doc.undo.undo()
    assert len(book.all_snapshots()) == before
    assert nb.HISTORY_HEADINGS[nb.SNAPSHOT_HISTORY] not in (book.session(day).notes if book.session(day) else "")
    win.doc.undo.redo()
    assert len(book.all_snapshots()) == before + 1


def test_the_history_can_be_switched_off(win):
    from lemmatrix import notebook as nb
    win.doc.ws_set(nb.HISTORY_SETTINGS[nb.SNAPSHOT_HISTORY], False)
    s, _ = win.take_snapshot(animate=False)
    assert nb.HISTORY_HEADINGS[nb.SNAPSHOT_HISTORY] not in s.notes
    win.doc.ws_set(nb.HISTORY_SETTINGS[nb.SNAPSHOT_HISTORY], True)


def test_the_window_renames_pins_and_deletes(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from lemmatrix.ui import notebook_dialog as nd
    _, snap = win.take_snapshot(animate=False)
    dlg = win.open_snapshots()
    assert isinstance(dlg, nd.SnapshotsDialog) and dlg.tree.topLevelItemCount() >= 1
    dlg.fill(snap.id)
    asked = []
    monkeypatch.setattr(nd, "ask_text", lambda *a, **k: asked.append(k) or "My plurals")
    dlg.rename()
    assert asked[-1].get("one_line")                               # a name: one line (audit, 25 October)
    hit = win.doc.notebook.snapshot(snap.id)
    assert hit[1].name == "My plurals"
    dlg.fill(snap.id)
    dlg.toggle_pin()
    assert win.doc.notebook.snapshot(snap.id)[1].pinned
    dlg.fill(snap.id)
    dlg.toggle_pin()
    assert win.doc.undo.undoText() == "Unpin snapshot"              # it said Pin either way
    win.doc.undo.undo()
    assert win.doc.notebook.all_snapshots()[0][1].id == snap.id     # pinned on top
    dlg.fill(snap.id)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    dlg.delete()
    assert win.doc.notebook.snapshot(snap.id) is None
    win.doc.undo.undo()                                              # the delete undone
    assert win.doc.notebook.snapshot(snap.id) is not None
    dlg.close()


def test_the_notebook_has_a_snapshots_tab(win):
    from lemmatrix.ui.notebook_dialog import SNAPSHOTS_TAB, HYPOTHESES_TAB
    win.take_snapshot(animate=False)
    win.open_notebook(win.work_date())
    tabs = win.notebook_dialog.tabs
    assert tabs.tabText(SNAPSHOTS_TAB).startswith("Snapshots (") and tabs.tabText(HYPOTHESES_TAB).startswith("Hypotheses")
    assert win.notebook_dialog.s_panel.tree.topLevelItemCount() >= 1
    win.notebook_dialog.close()


def test_badges_switch_off_one_by_one(win):
    from lemmatrix.ui.dialogs import BADGE_SNAPSHOTS
    win.take_snapshot(animate=False)
    win.update_badges()
    btn, badge = win.badges["snapshots"]
    assert not badge.isHidden() and badge.text() != ""
    win.prefs.set_value(BADGE_SNAPSHOTS, False)
    win.update_badges()
    assert badge.isHidden()
    win.prefs.set_value(BADGE_SNAPSHOTS, True)
    assert set(win.badges) == {"questions", "snapshots", "todo"}


def test_the_camera_click_takes_a_snapshot_and_the_menu_is_kept(win):
    before = len(win.doc.notebook.all_snapshots())
    win._camera_button().click()
    assert len(win.doc.notebook.all_snapshots()) == before + 1
    names = [a.text() for a in win.menuBar().actions()]
    view = next(a.menu() for a in win.menuBar().actions() if a.text().replace("&", "") == "View")
    snaps = next(a for a in view.actions() if a.text().replace("&", "") == "Snapshots")
    assert snaps.shortcut().toString() == "Ctrl+Shift+P" and names


def test_archives_scrub_listed_snapshots():
    from lemmatrix import notebook as nb
    import inspect
    from lemmatrix import anonymise
    assert "sess.snapshots" in inspect.getsource(anonymise)
    book = nb.Notebook()
    nb.take_snapshot(book, "2026-10-16", {"search": "SP1"}, "SP1 words")
    assert book.all_snapshots()[0][1].view == {"search": "SP1"}
