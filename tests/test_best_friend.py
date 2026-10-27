# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""🐕 linguist's best friend (IDEAS.md idea 21, Josh, 27 October): IPA typing corrections in
Phonetic and Phonemic, each rule an option, Backspace or Ctrl+Z straight after puts back what was
typed."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QInputMethodEvent, QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit  # noqa: E402

from lemmatrix import advanced, bestfriend as bf  # noqa: E402

ALL_ON = lambda rule: True  # noqa: E731


# ---- the rules ------------------------------------------------------------------------------

def test_each_rule():
    c = lambda before, typed: bf.correct(before, typed, ALL_ON)  # noqa: E731
    for apostrophe in ("'", "’", "‘"):
        assert c("k", apostrophe) == (0, "ʼ")
        assert c("", apostrophe) == (0, "ʼ")            # wherever it is typed (Josh)
    assert c("a", "?") == (0, "ʔ")
    assert c("a", "y") == (0, "j") and c("a", "Y") is None
    assert c("a", "g") == (0, "ɡ") and c("a", "G") is None
    assert c("a", ":") == (0, "ː")
    assert c("", "ε") == (0, "ɛ") and c("", "γ") == (0, "ɣ") and c("", "φ") == (0, "ɸ")
    assert c("", "β") is None and c("", "θ") is None    # already the IPA letters
    assert c("", "!") == (0, "ǃ") and c("", "‡") == (0, "ǂ")
    assert c("a", "|") == (0, "ǀ") and c("aǀ", "|") == (1, "ǁ")
    assert c("e", "´") == (0, "́") and c("e", "~") == (0, "̃")
    assert c("é", "~") == (0, "̃")            # marks stack
    assert c("", "^") is None and c("5 ", "^") is None  # no letter before: typed as it is
    assert c("a", "ʼ") is None and c("a", "x") is None


def test_rules_turned_off_leave_it_as_typed():
    only_j = lambda rule: rule is bf.J  # noqa: E731
    assert bf.correct("a", "'", only_j) is None
    assert bf.correct("a", "y", only_j) == (0, "j")


# ---- typing ---------------------------------------------------------------------------------

def _box(win, field="Phonetic"):
    from lemmatrix.ui import fastpaste, keyboards
    fastpaste.set_context(lambda: win.doc.db)
    e = QLineEdit()
    keyboards.tag(e, field)
    return e


def _type(f, e, ch):
    ev = QKeyEvent(QEvent.KeyPress, 0, Qt.NoModifier, ch)
    if not f.eventFilter(e, ev):
        e.insert(ch)                                     # what the box itself would do


def _key(f, e, key, mods=Qt.NoModifier):
    ev = QKeyEvent(QEvent.KeyPress, key, mods)
    if not f.eventFilter(e, ev):
        if key == Qt.Key_Backspace:
            e.backspace()
        elif key == Qt.Key_Z:
            e.undo()


def test_off_by_default_nothing_changes(win):
    from lemmatrix.ui.bestfriend import BestFriendFilter
    f, e = BestFriendFilter(), _box(win)
    for ch in "k'ay":
        _type(f, e, ch)
    assert e.text() == "k'ay"


def test_typing_in_phonetic_and_phonemic(win):
    from lemmatrix.ui.bestfriend import BestFriendFilter
    advanced.set_on(advanced.BEST_FRIEND_KEY, True)
    f = BestFriendFilter()
    for field in ("Phonetic", "Phonemic"):
        e = _box(win, field)
        for ch in "k'a:y?ga||e´":
            _type(f, e, ch)
        assert e.text() == "kʼaːjʔɡaǁé", field


def test_other_fields_untouched(win):
    from lemmatrix.ui.bestfriend import BestFriendFilter
    advanced.set_on(advanced.BEST_FRIEND_KEY, True)
    f = BestFriendFilter()
    for field in ("Translation", "Gloss"):
        e = _box(win, field)
        for ch in "don't, y?":
            _type(f, e, ch)
        assert e.text() == "don't, y?"


def test_a_rule_deselected(win):
    from lemmatrix.ui.bestfriend import BestFriendFilter
    advanced.set_on(advanced.BEST_FRIEND_KEY, True)
    advanced.set_on(bf.J.key, False)
    f, e = BestFriendFilter(), _box(win)
    for ch in "y'":
        _type(f, e, ch)
    assert e.text() == "yʼ"


def test_backspace_or_ctrl_z_straight_after_takes_it_back(win):
    from lemmatrix.ui.bestfriend import BestFriendFilter
    advanced.set_on(advanced.BEST_FRIEND_KEY, True)
    f, e = BestFriendFilter(), _box(win)
    _type(f, e, "a")
    _type(f, e, "y")
    assert e.text() == "aj"
    _key(f, e, Qt.Key_Backspace)
    assert e.text() == "ay"                              # the y as typed
    _key(f, e, Qt.Key_Backspace)
    assert e.text() == "a"                               # then Backspace deletes as usual
    _type(f, e, "?")
    _key(f, e, Qt.Key_Z, Qt.ControlModifier)
    assert e.text() == "a?"
    _type(f, e, "|")
    _type(f, e, "|")
    assert e.text() == "a?ǁ"
    _key(f, e, Qt.Key_Backspace)
    assert e.text() == "a?ǀ|"                            # ǁ back to the ǀ and the | typed


def test_another_key_in_between_backspace_deletes(win):
    from lemmatrix.ui.bestfriend import BestFriendFilter
    advanced.set_on(advanced.BEST_FRIEND_KEY, True)
    f, e = BestFriendFilter(), _box(win)
    _type(f, e, "y")
    _type(f, e, "a")
    _key(f, e, Qt.Key_Backspace)
    _key(f, e, Qt.Key_Backspace)
    assert e.text() == ""


def test_pasting_is_untouched(win):
    advanced.set_on(advanced.BEST_FRIEND_KEY, True)
    e = _box(win)
    QApplication.clipboard().setText("k'ay")
    e.paste()
    assert e.text() == "k'ay"


def test_an_input_method_commit(win):
    from lemmatrix.ui.bestfriend import BestFriendFilter
    advanced.set_on(advanced.BEST_FRIEND_KEY, True)
    f, e = BestFriendFilter(), _box(win)
    ev = QInputMethodEvent()
    ev.setCommitString("y")
    assert f.eventFilter(e, ev) and e.text() == "j"


def test_in_the_token_dialogue(win, app):
    from lemmatrix.ui import bestfriend as ubf
    from lemmatrix.ui import fastpaste, keyboards
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    advanced.set_on(advanced.BEST_FRIEND_KEY, True)
    fastpaste.set_context(lambda: win.doc.db)
    f = ubf.install(app)
    try:
        dlg = TokenDialog(win, [Slot(win.doc.db.entries[0], 0)], 0)
        pht = next(w for w in dlg.findChildren(QLineEdit) if keyboards.field_key(w) == "Phonetic")
        pht.setText("")
        for ch in "ka:":
            QApplication.sendEvent(pht, QKeyEvent(QEvent.KeyPress, 0, Qt.NoModifier, ch))
        assert pht.text() == "kaː"
        dlg.reject()
    finally:
        app.removeEventFilter(f)


def test_settings_lists_the_rules(win):
    from PySide6.QtWidgets import QLabel
    from lemmatrix.ui.dialogs import PreferencesDialog
    dlg = PreferencesDialog(win, win.doc.db, win.prefs)
    assert dlg.best_friend_box.text() == "🐕 linguist's best friend" and not dlg.best_friend_box.isChecked()
    assert any(lb.text() == advanced.BEST_FRIEND_LINE for lb in dlg.findChildren(QLabel))
    assert [dlg.bf_rules[r.key].text() for r in bf.RULES] == [r.label for r in bf.RULES]
    assert all(b.isChecked() and not b.isEnabled() for b in dlg.bf_rules.values())
    dlg.best_friend_box.setChecked(True)
    assert all(b.isEnabled() for b in dlg.bf_rules.values())
    dlg.bf_rules[bf.J.key].setChecked(False)
    dlg.apply()
    assert advanced.best_friend() and not advanced.on(bf.J.key) and advanced.on(bf.EJECTIVE.key)
    for key in (advanced.BEST_FRIEND_KEY, bf.J.key):
        win.prefs.set_value(key, key == bf.J.key)
    dlg.reject()


def test_in_all_data_editor(win):
    from lemmatrix.ui import fastpaste
    from lemmatrix.ui.bestfriend import BestFriendFilter
    advanced.set_on(advanced.BEST_FRIEND_KEY, True)
    fastpaste.set_context(lambda: win.doc.db)
    win.show()
    t = win.all_table
    cols = [c.key for c in t.model_.columns]
    idx = t.proxy.index(0, cols.index("f:Phonemic"))
    t.setCurrentIndex(idx)
    t.edit(idx)
    for _ in range(5):
        QApplication.processEvents()
    ed = next(w for w in t.viewport().findChildren(QLineEdit) if w.isVisible())
    ed.setText("")
    f = BestFriendFilter()
    for ch in "ba:":
        _type(f, ed, ch)
    assert ed.text() == "baː"
