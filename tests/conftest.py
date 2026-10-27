# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Shared test setup.

Most feature tests (renames, recordings, matrices...) were written against the prototype's tag
structure: NOUN and VERB groups, no default for Number, an Oblique case. They test the features,
not the defaults, so they keep using that structure. Tests of the defaults themselves are marked
`real_defaults` and see the structure a new database really gets.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

# Every test run gets settings of its own, in a temporary folder, as an .ini file (the audit, 25
# October): runs used to share one real store ("Lemmatrix-tests" in the registry on Windows), so a
# run could inherit what an earlier one left behind. Set before any Lemmatrix module opens them.
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"
_SETTINGS_DIR = tempfile.mkdtemp(prefix="lemmatrix-test-settings-")
os.environ["LEMMATRIX_SETTINGS_FILE"] = os.path.join(_SETTINGS_DIR, "Lemmatrix-tests.ini")

from lemmatrix import defaults  # noqa: E402
from lemmatrix.defaults import EXAMPLES, INSTANCES, _tags  # noqa: E402
from lemmatrix.model import Group, TagStructure  # noqa: E402

SAMPLE = Path(__file__).resolve().parent / "data" / "sample"    # the prototype's sample (feature tests)

REAL_TAG_STRUCTURE = defaults.default_tag_structure


def prototype_tag_structure() -> TagStructure:
    persons = ["1SG", "2SG", "3SG", "1PL", "2PL", "3PL"]
    subjects = [f"{p}.{r}" for p in persons for r in ("A", "S")]
    objects = [f"{p}.O" for p in persons]
    noun = Group("NOUN", groups=[
        Group("Number", _tags(("Singular", "SG"), ("Plural", "PL"))),
        Group("Case", _tags(("Nominative", "NOM"), ("Accusative", "ACC"), ("Ergative", "ERG"),
                            ("Absolutive", "ABS"), ("Genitive", "GEN"), ("Oblique", "OBL"))),
    ], usual=["NOUN"])
    verb = Group("VERB", groups=[
        Group("Subject", _tags(*subjects)),
        Group("Object", _tags(*objects)),
        Group("Stem", _tags("Simple", ("Passive", "PASS"), ("Antipassive", "AP"),
                            ("Causative", "CAUS"), default="Simple")),
        Group("Tense", _tags(("Past", "PST"), ("Present", "PRS"), ("Future", "FUT"))),
        Group("Aspect", _tags(("Perfective", "PFV"), ("Imperfective", "IPFV"))),
        Group("Mood", _tags("Indicative", ("Imperative", "IMP"), default="Indicative")),
        Group("Polarity", _tags("Affirmative", ("Negative", "NEG"), default="Affirmative")),
    ], usual=["VERB"])
    shared = [
        Group("Phonological", groups=[
            Group("Following tone", _tags(("before H", "xH"), ("before L", "xL"))),
            Group("Preceding tone", _tags(("after H", "Hx"), ("after L", "Lx"))),
        ]),
        Group("Syntactic", groups=[
            Group("Position vis predicate", _tags(("preverbal", "PREV"), ("postverbal", "POSTV"),
                                                  ("non-verbal predicate", "PRED"))),
            Group("Utterance position", _tags("isolation", ("utterance-initial", "INI"),
                                              ("utterance-final", "FIN"), default="isolation")),
        ]),
        Group(INSTANCES, groups=[
            Group("Frames", _tags(("Frame 1", "F1"), ("Frame 2", "F2"))),
            Group(EXAMPLES, _tags(("Example 1", "x1"), ("Example 2", "x2"))),
        ]),
    ]
    for g in (noun, verb, *shared):              # descriptions as the prototype had them: none
        for sub in g.walk():
            sub.description = ""
            for t in sub.tags:
                t.description = ""
    return TagStructure([noun, verb, *shared])


def pytest_configure(config):
    config.addinivalue_line("markers", "real_defaults: use the tag structure new databases really get")


def pytest_unconfigure(config):
    shutil.rmtree(_SETTINGS_DIR, ignore_errors=True)


# ---- the windows the feature tests use (one copy here; the audit, 25 October: six copies, each a
# little different, were imported from one test file into another) ----------------------------

@pytest.fixture(scope="session")
def app():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    a = QApplication.instance() or QApplication([])
    # A short double-click interval: the click-to-unselect waits for it before unselecting, and the
    # tests wait with it (the audit, section 8, step 8: real waits cut). Long enough for Qt to
    # still see a double-click sent at once.
    a.styleHints().setMouseDoubleClickInterval(120)
    return a


@pytest.fixture
def make_win(app, monkeypatch):
    """make_win(db) → a main window with this database open: the message boxes answered (Yes),
    a category asked for answered W, and everything left clean afterwards (no unsaved-changes
    question when it closes)."""
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    from lemmatrix.ui import main_window
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QInputDialog, "getItem", lambda parent, title, label, items, *a, **k:
                        (next((i for i in items if str(i).startswith("W")), items[0] if items else ""), True))
    made = []

    def make(db, before_load=None):
        w = main_window.MainWindow()
        if before_load is not None:
            before_load(w)
        w.load_database(db)
        made.append(w)
        return w
    yield make
    for w in made:
        if getattr(w, "utterances_window", None) is not None:
            w.utterances_window.close()
        w.doc.undo.setClean()
        w.doc._settings_dirty = False
        w.close()


@pytest.fixture
def win(make_win, tmp_path):
    """The main window on a copy of the prototype's sample (tests/data/sample)."""
    from lemmatrix import storage
    shutil.copy2(SAMPLE / "Sample.xml", tmp_path / "Sample.xml")
    shutil.copytree(SAMPLE / "Soundfiles", tmp_path / "Soundfiles")
    w = make_win(storage.load(tmp_path / "Sample.xml"))
    w.prefs.confirm_delete = True
    return w


@pytest.fixture(autouse=True)
def _prototype_tags(request, monkeypatch):
    if request.node.get_closest_marker("real_defaults") is None:
        monkeypatch.setattr(defaults, "default_tag_structure", prototype_tag_structure)


@pytest.fixture(autouse=True)
def _message_boxes_never_wait(monkeypatch):
    """A message box a test hasn't answered takes its default button at once, as if Enter were
    pressed (26 October: the sample's workspace was last used the day before, so opening it asked
    "It's a new day…" and the test waited for ever). Tests that answer a box themselves patch exec
    or clickedButton as before, which wins over this."""
    try:
        from PySide6.QtWidgets import QMessageBox
    except ImportError:
        return

    def exec_(box):
        b = box.defaultButton() or (box.buttons()[0] if box.buttons() else None)
        box._test_answer = b
        return int(box.standardButton(b)) if b is not None else 0
    monkeypatch.setattr(QMessageBox, "exec", exec_)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: getattr(box, "_test_answer", None))


@pytest.fixture(autouse=True)
def _ask_through_question(monkeypatch):
    """widgets.ask (a question with buttons named for what they do) answers as the test's
    QMessageBox.question does, so tests set one answer for both kinds of question."""
    try:
        from PySide6.QtWidgets import QMessageBox

        from lemmatrix.ui import widgets
    except ImportError:
        return
    monkeypatch.setattr(widgets, "real_ask", widgets.ask, raising=False)   # for testing ask itself
    monkeypatch.setattr(widgets, "ask", lambda parent, title, text, go, stop="Cancel", icon=None:
                        QMessageBox.question(parent, title, text) in (QMessageBox.Yes, QMessageBox.Save,
                                                                     QMessageBox.Ok))
    monkeypatch.setattr(widgets, "real_choose", widgets.choose, raising=False)

    def choose(parent, title, text, choices, cancel="Cancel", escape=None):
        """Yes (Save, Ok) the first answer, No the second, anything else Cancel (or Esc's)."""
        r = QMessageBox.question(parent, title, text)
        if r in (QMessageBox.Yes, QMessageBox.Save, QMessageBox.Ok):
            return 0
        if r == QMessageBox.No and len(choices) > 1:
            return 1
        return escape if not cancel else None
    monkeypatch.setattr(widgets, "choose", choose)
    monkeypatch.setattr(widgets, "real_ask_with_checkbox", widgets.ask_with_checkbox, raising=False)
    monkeypatch.setattr(widgets, "ask_with_checkbox", lambda parent, title, text, go, check, stop="Cancel": (
        QMessageBox.question(parent, title, text) in (QMessageBox.Yes, QMessageBox.Save, QMessageBox.Ok), False))


@pytest.fixture(autouse=True)
def _no_old_computer_settings():
    """Opening a format 6 database copies this computer's settings into its new workspace (idea
    36). In tests that copy would carry one test's columns or options into the next (the test
    settings are one store), so the settings that move are cleared before each test."""
    try:
        from lemmatrix.ui.prefs import settings_store
    except ImportError:
        yield
        return
    q = settings_store()
    if q.fileName() == os.environ.get("LEMMATRIX_SETTINGS_FILE"):     # never the real preferences
        for key in ("columns", "lines", "views", "sessions", "fullbackup", "matrix/autoplay",
                    "matrix/only_with_data", "notebook/sort",
                    "session/speaker", "search/power", "recording/hot_mic", "edit/fast_paste",
                    "edit/best_friend", "recording/auto_snip", "recording/snip_before",
                    "recording/snip_after", "recording/snip_gap"):
            q.remove(key)
        for key in [k for k in q.allKeys() if k.startswith("edit/bf_")]:
            q.remove(key)
    yield


@pytest.fixture(autouse=True)
def _plain_search():
    """⚡ Power search (idea 86) is off at the start of every test, as on a new computer, and off
    again after it (a test that turns it on can't leave it on for the next)."""
    from lemmatrix import advanced, search
    search.set_power(False)
    from lemmatrix import bestfriend
    def reset():
        for key in (advanced.HOT_MIC_KEY, advanced.FAST_PASTE_KEY, advanced.BEST_FRIEND_KEY,
                    advanced.AUTO_SNIP_KEY):
            advanced.set_on(key, False)           # 🔥 hot mic, 📋 fast paste, 🐕, ✂: off too
        for key, (_, default) in advanced.SNIP_MARGINS.items():
            advanced.set_margin(key, default)
        for rule in bestfriend.RULES:
            advanced.set_on(rule.key, True)       # the dog's rules: on, as on a new computer
    reset()
    yield
    search.set_power(False)
    reset()
