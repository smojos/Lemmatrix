# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Automatic keyboard switching (IDEAS.md idea 43, Josh, 24 October), with a stand-in for
Windows' keyboards: which field gets which keyboard, switching on entering and back on leaving,
a keyboard changed by hand left alone, nothing at all while it is off."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget  # noqa: E402

from lemmatrix.ui import keyboards as kb  # noqa: E402
from test_ui import app, win  # noqa: E402,F401

EN, IPA, AM = "hkl:0809:8090809", "tip:0409:{KEYMAN}:{SILIPA}", "tip:045e:{KEYMAN}:{AMHARIC}"


class FakeKeyboards:
    available = True

    def __init__(self):
        self.on = EN
        self.log = []

    def list(self):
        return [kb.Keyboard(EN, "English (United Kingdom) – UK"), kb.Keyboard(IPA, "English – IPA (SIL)"),
                kb.Keyboard(AM, "Amharic – Amharic")]

    def active(self):
        return self.on

    def activate(self, kid):
        self.log.append(kid)
        self.on = kid
        return True


def _settle():
    for _ in range(10):
        QApplication.processEvents()


@pytest.fixture
def setup(app, win):
    fake = FakeKeyboards()
    sw = kb.install(app, fake)
    kb.set_context(lambda: (win.doc.db, win.prefs))
    c = kb.Choices(win.prefs)
    for key in [k for k in win.prefs.q.allKeys() if k.startswith("keyboards/")]:
        win.prefs.q.remove(key)
    db = win.doc.db
    if "ar" not in db.settings.gloss_languages:
        db.settings.gloss_languages.append("ar")
    yield fake, sw, c
    app.removeEventFilter(sw)
    for key in [k for k in win.prefs.q.allKeys() if k.startswith("keyboards/")]:
        win.prefs.q.remove(key)


def test_fields_resolve_to_their_kinds(win):
    db = win.doc.db
    assert kb.resolve(db, "Phonetic") == ("Phonetic", kb.TRANSCRIPTIONS)
    assert kb.resolve(db, "f:Phonemic") == ("Phonemic", kb.TRANSCRIPTIONS)
    assert kb.resolve(db, "lemma") == (db.settings.entry_field("lemma").name, kb.TRANSCRIPTIONS)
    assert kb.resolve(db, "Translation") == ("Translation:en", kb.PRIMARY)
    assert kb.resolve(db, "f:Translation:ar") == ("Translation:ar", "lang:ar")
    assert kb.resolve(db, "gloss:ar")[1] == "lang:ar"
    assert kb.resolve(db, "gloss")[1] == kb.PRIMARY
    assert kb.resolve(db, "Comment")[1] == kb.ELSEWHERE
    assert kb.resolve(db, "Morphemes")[1] == kb.ELSEWHERE
    assert kb.resolve(db, "ref")[1] == kb.ELSEWHERE           # not a field
    assert kb.resolve(db, kb.SEGMENT) == (kb.SEGMENT, kb.TRANSCRIPTIONS)


def test_the_kinds_and_fields_lists(win):
    db = win.doc.db
    if "ar" not in db.settings.gloss_languages:
        db.settings.gloss_languages.append("ar")
    assert [k for k, _ in kb.kinds(db)] == [kb.ELSEWHERE, kb.TRANSCRIPTIONS, kb.PRIMARY, "lang:ar"]
    ids = [fid for fid, _, _ in kb.fields(db)]
    assert "Phonetic" in ids and "Translation:ar" in ids and "Gloss:en" in ids and kb.SEGMENT in ids
    assert "Pitch" not in ids                              # digits: nothing to type with


def test_a_field_overrides_its_kind(setup, win):
    fake, sw, c = setup
    db = win.doc.db
    c.set_kind(kb.TRANSCRIPTIONS, IPA)
    assert c.for_key(db, "Phonemic") == IPA
    c.set_field("Phonemic", kb.DONT)
    assert c.for_key(db, "Phonemic") == kb.DONT and c.for_key(db, "Phonetic") == IPA
    c.set_field("Phonemic", kb.AS_KIND)
    assert c.for_key(db, "Phonemic") == IPA
    assert c.for_key(db, None) == kb.START                 # elsewhere: the keyboard on at start


def _boxes(*keys):
    w = QWidget()
    lay = QVBoxLayout(w)
    eds = []
    for k in keys:
        ed = QLineEdit()
        if k:
            kb.tag(ed, k)
        lay.addWidget(ed)
        eds.append(ed)
    _FOCUSED.clear()
    return w, eds


_FOCUSED = []


def _focus(ed):
    """The cursor moves into ed (sent as the window system would: offscreen windows don't get focus)."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QFocusEvent
    if _FOCUSED:
        QApplication.sendEvent(_FOCUSED.pop(), QFocusEvent(QEvent.FocusOut, Qt.TabFocusReason))
    if ed is not None:
        QApplication.sendEvent(ed, QFocusEvent(QEvent.FocusIn, Qt.TabFocusReason))
        _FOCUSED.append(ed)
    _settle()


def test_entering_switches_and_leaving_switches_back(setup):
    fake, sw, c = setup
    c.on = True
    c.set_kind(kb.TRANSCRIPTIONS, IPA)
    c.set_kind("lang:ar", AM)
    w, (phon, trans_ar, search) = _boxes("Phonetic", "Translation:ar", None)
    _focus(phon)
    assert fake.on == IPA
    _focus(trans_ar)
    assert fake.on == AM
    _focus(search)                                         # a search bar: elsewhere
    assert fake.on == EN
    _focus(phon)
    _focus(None)                                           # leaving for something that isn't a field
    assert fake.on == EN
    w.close()


def test_a_keyboard_changed_by_hand_is_left_alone_until_the_field_is_left(setup):
    fake, sw, c = setup
    c.on = True
    c.set_kind(kb.TRANSCRIPTIONS, IPA)
    w, (phon, other) = _boxes("Phonetic", "Comment")
    _focus(phon)
    assert fake.on == IPA
    fake.on = AM                                           # changed by hand while typing
    _settle()
    assert fake.on == AM                                   # Lemmatrix doesn't touch it
    _focus(other)
    assert fake.on == EN                                   # until the field is left
    w.close()


def test_off_means_nothing_happens(setup):
    fake, sw, c = setup
    c.on = False
    c.set_kind(kb.TRANSCRIPTIONS, IPA)
    w, (phon,) = _boxes("Phonetic")
    _focus(phon)
    assert fake.log == [] and fake.on == EN
    w.close()


def test_dont_switch_leaves_the_keyboard_as_it_is(setup):
    fake, sw, c = setup
    c.on = True
    c.set_kind(kb.ELSEWHERE, kb.DONT)
    c.set_kind(kb.TRANSCRIPTIONS, IPA)
    w, (phon, comment) = _boxes("Phonetic", "Comment")
    _focus(phon)
    _focus(comment)
    assert fake.on == IPA                                  # Elsewhere is Don't switch
    w.close()


def test_the_dialogues_and_grids_say_which_field(setup, win):
    """The token dialogue's fields and All data's in-place editor."""
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    fake, sw, c = setup
    goat = win.doc.db.entry_by_ref("D001")
    dlg = TokenDialog(win, [Slot(goat, 0)], 0)
    keys = {ed.property(kb.PROPERTY) for ed in dlg.edits.values()} if hasattr(dlg, "edits") else set()
    assert "Phonetic" in keys and "Translation" in keys
    dlg.reject()
    from lemmatrix.ui.main_window import ALL_DATA
    win.resize(1400, 780)
    win.show()
    win.tabs.setCurrentIndex(ALL_DATA)
    _settle()
    t = win.all_table
    col = next(i for i, cl in enumerate(t.model_.columns) if cl.key == "f:Phonetic")
    idx = t.proxy.index(0, col)
    t.setCurrentIndex(idx)
    t.edit(idx)
    _settle()
    ed = QApplication.focusWidget()
    assert isinstance(ed, QLineEdit) and kb.field_key(ed) == "f:Phonetic"
    t.closePersistentEditor(idx)


def test_settings_section_writes_the_choices(setup, win):
    fake, sw, c = setup
    from PySide6.QtWidgets import QDialog
    sec = kb.KeyboardSection(QDialog(win), win.doc.db, win.prefs)
    assert sec.on.isEnabled()
    sec.on.setChecked(True)
    cb = sec.rows[kb.TRANSCRIPTIONS]
    cb.setCurrentIndex(cb.findData(IPA))
    sec.fields["Phonemic"] = kb.DONT
    sec.apply()
    assert c.on and c.kind(kb.TRANSCRIPTIONS) == IPA and c.field("Phonemic") == kb.DONT
    assert c.kind(kb.ELSEWHERE) == kb.START


def test_a_keyboard_no_longer_installed_is_shown_as_such(setup, win):
    fake, sw, c = setup
    c.set_kind(kb.TRANSCRIPTIONS, "tip:0409:{GONE}:{GONE}")
    from PySide6.QtWidgets import QDialog
    sec = kb.KeyboardSection(QDialog(win), win.doc.db, win.prefs)
    assert "(not installed)" in sec.rows[kb.TRANSCRIPTIONS].currentText()


def test_not_windows_greys_the_section(app, win):
    sw = kb.install(app, kb.NoKeyboards())
    try:
        from PySide6.QtWidgets import QDialog
        sec = kb.KeyboardSection(QDialog(win), win.doc.db, win.prefs)
        assert not sec.on.isEnabled() and sec.note is not None
    finally:
        app.removeEventFilter(sw)
