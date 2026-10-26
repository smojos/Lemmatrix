# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Ideas 67 (copy citation forms to empty lemmas), 68 (Don't ask again until the token dialogue
closes) and 69 (filter a date column by a day or a range), Josh, 24–26 October."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lemmatrix import citation_copy, filters  # noqa: E402


# ---- 69: dates ---------------------------------------------------------------------------
def test_a_day_or_a_range():
    day = filters.DateFilter("2026-03-04", "2026-03-04")
    assert day.matches("2026-03-04") and not day.matches("2026-03-05") and not day.matches("")
    rng = filters.DateFilter("2026-03-01", "2026-03-31")
    assert rng.matches("2026-03-15") and not rng.matches("2026-04-01")
    after, before = filters.DateFilter("2026-03-01", ""), filters.DateFilter("", "2026-03-01")
    assert after.matches("2027-01-01") and not after.matches("2026-02-28")
    assert before.matches("2026-03-01") and not before.matches("2026-03-02")
    assert filters.matches(rng, "2026-03-15")
    assert filters.decode(filters.encode(rng)) == rng
    for f in (day, rng, after, before):
        assert f.describe()


def test_only_open_date_columns_are_dates():
    from lemmatrix.ui.table import Column, is_date
    assert is_date(Column("date", "Collected", lambda r: ""))
    assert not is_date(Column("gloss", "Gloss", lambda r: ""))


def test_the_date_dialogue(app):
    from PySide6.QtWidgets import QWidget
    from lemmatrix.ui.filter_dialogs import DateFilterDialog
    host = QWidget()
    dlg = DateFilterDialog(host, "Collected", None, ["2026-03-04", "2026-05-01", ""])
    f = dlg.result_filter()
    assert isinstance(f, filters.DateFilter) and f.start
    dlg.close()
    host.close()


# ---- 67: citation forms -----------------------------------------------------------------
def _empty_some(db, n=3):
    f = db.settings.entry_field("lemma")
    out = []
    for e in db.entries:
        if e.get(f.name).strip():
            e.set(f.name, "")
            out.append(e)
        if len(out) == n:
            break
    return f, out


def test_the_plan_never_touches_a_filled_lemma(win):
    db = win.doc.db
    f, emptied = _empty_some(db)
    p = citation_copy.plan(db)
    assert {id(e) for e, _ in p.copies} | {id(e) for e in p.no_form} == {id(e) for e in emptied}
    assert p.filled == len(db.entries) - len(emptied)
    assert all(form for _, form in p.copies)


def test_copy_is_one_undo_step(win, monkeypatch):
    from lemmatrix.ui import citation_copy_dialog as ccd
    db = win.doc.db
    f, emptied = _empty_some(db)
    win.doc.undo.setClean()
    p = citation_copy.plan(db)
    assert p.copies
    monkeypatch.setattr(ccd.CopyCitationDialog, "exec", lambda self: 1)
    win.copy_citation_forms()
    filled = [e for e, _ in p.copies]
    assert all(e.get(f.name) for e in (next(x for x in db.entries if x.ref == e.ref) for e in filled))
    win.doc.undo.undo()
    assert all(not next(x for x in db.entries if x.ref == e.ref).get(f.name) for e in filled)


def test_deselected_lemmas_are_left(win, app):
    from PySide6.QtCore import Qt
    from lemmatrix.ui.citation_copy_dialog import CopyCitationDialog
    db = win.doc.db
    _empty_some(db)
    dlg = CopyCitationDialog(win, db)
    n = len(dlg.plan.copies)
    assert len(dlg.chosen()) == n
    if n:
        dlg.table.item(0, 0).setCheckState(Qt.Unchecked)
        assert len(dlg.chosen()) == n - 1
        assert dlg.go.text().startswith(f"Copy {n - 1} form")
    dlg._select_all(False)
    assert not dlg.chosen() and not dlg.go.isEnabled()
    dlg.reject()


# ---- 68: Don't ask again ------------------------------------------------------------------
def test_dont_ask_again_lasts_until_the_dialogue_closes(win, monkeypatch):
    from lemmatrix.ui import widgets
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    asked = []

    def answer(parent, title, text, go, check, stop="Cancel"):
        asked.append(check)
        return True, True
    monkeypatch.setattr(widgets, "ask_with_checkbox", answer)
    dlg = TokenDialog(win, [Slot(win.doc.db.entries[0], 0)], 0)
    assert not getattr(dlg, "_record_over_quietly", False)
    assert dlg._ask_record_over("Replace this token's recording?")
    assert dlg._record_over_quietly and "until this dialogue closes" in asked[0]
    dlg.reject()
    again = TokenDialog(win, [Slot(win.doc.db.entries[0], 0)], 0)
    assert not getattr(again, "_record_over_quietly", False)        # a new dialogue asks again
    again.reject()


def test_not_selected_keeps_asking(win, monkeypatch):
    from lemmatrix.ui import widgets
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    monkeypatch.setattr(widgets, "ask_with_checkbox", lambda *a, **k: (True, False))
    dlg = TokenDialog(win, [Slot(win.doc.db.entries[0], 0)], 0)
    assert dlg._ask_record_over("x") and not getattr(dlg, "_record_over_quietly", False)
    monkeypatch.setattr(widgets, "ask_with_checkbox", lambda *a, **k: (False, True))
    assert not dlg._ask_record_over("x") and not getattr(dlg, "_record_over_quietly", False)
    dlg.reject()
