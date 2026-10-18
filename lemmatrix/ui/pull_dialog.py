"""Pull from source (idea 7, stage 4): the dialogues.

PullDialog shows each field to be replaced, as it is in the utterance and as it is in the
TextGrid now, and offers to cut the clip again where the line's times moved. CheckDialog
(Tools → Check clipped utterances…) lists every clipped utterance whose line has changed or
gone, with Pull, Unlink and Show. pull_utterances() and unlink_utterances() do the work, as
one undo step each; cutting a clip again can't be undone (the old recording goes to the
Recycle Bin, as when a recording is replaced).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile, Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from .. import audio, pull, storage
from . import theme
from .widgets import ipa_font

STATUS_LABELS = {pull.OK: "the same", pull.CHANGED: "changed", pull.MOVED: "times moved",
                 pull.NOT_FOUND: "line not found", pull.NO_TEXTGRID: "TextGrid missing",
                 pull.NO_TEXT: "text deleted"}


def status_label(c: pull.Check) -> str:
    if c.status == pull.CHANGED and c.moved:
        return "changed, times moved"
    return STATUS_LABELS.get(c.status, c.status)


def field_title(db, key: str) -> str:
    name, _, lang = key.partition(":")
    f = db.settings.token_field(name)
    title = f.title if f is not None else name
    return f"{title} ({lang})" if lang and len(db.settings.gloss_languages) > 1 else title


def times(start: float, end: float) -> str:
    from .texts import clock
    return f"{clock(start)}–{clock(end)}"


class PullDialog(QDialog):
    def __init__(self, parent, db, checks: list[pull.Check]):
        super().__init__(parent)
        self.db = db
        self.checks = checks
        n = len(checks)
        self.setWindowTitle("Pull from source")
        lay = QVBoxLayout(self)
        intro = QLabel(("This replaces the fields below with the line as it is in the TextGrid now. "
                        if n == 1 else
                        f"This replaces the fields below in {n} utterances with their lines as they are in "
                        "the TextGrid now. ")
                       + "Other fields, and changes made only in Lemmatrix to other fields, stay as they are.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Utterance", "Field", "In the utterance", "In the TextGrid now"])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.NoSelection)
        ipa = ipa_font()
        moved = 0
        for c in checks:
            u, ln = c.utterance, c.line
            keys = list(dict.fromkeys(ch.key for ch in c.changes if ch.key))
            rows = []
            for key in keys:
                now, new = pull.field_value(db, u, key), ln.values.get(key, "")
                if now != new:
                    f = db.settings.token_field(key.partition(":")[0])
                    rows.append((field_title(db, key), now, new, bool(f and f.role in ("phonetic", "phonemic"))))
            if c.moved:
                moved += 1
                rows.append(("Times", times(u.source.start, u.source.end), times(ln.start, ln.end), False))
            if not rows:
                rows.append(("", "already the same: only the link is updated", "-", False))
            dim = theme.colour("dim")
            for i, (title, now, new, is_ipa) in enumerate(rows):
                it = QTreeWidgetItem([u.ref if i == 0 else "", title, now or "(empty)", new or "(empty)"])
                for col, value in ((2, now), (3, new)):
                    if is_ipa:
                        it.setFont(col, ipa)
                    if not value:
                        it.setForeground(col, dim)
                it.setToolTip(2, now)
                it.setToolTip(3, new)
                self.tree.addTopLevelItem(it)
        for i in range(4):
            self.tree.resizeColumnToContents(i)
        lay.addWidget(self.tree, 1)
        self.recut = QCheckBox()
        self.recut.setChecked(True)
        if moved:
            self.recut.setText(("Cut the clip again from the new times" if moved == 1 else
                                f"Cut the {moved} clips whose times moved again")
                               + " (the old recording goes to the Recycle Bin; undo can't bring it back)")
            lay.addWidget(self.recut)
        else:
            self.recut.setChecked(False)
            self.recut.hide()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Pull")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.resize(760, 360)


def recut(main, c: pull.Check, u) -> str:
    """Cut the utterance's clip again from its line's (new) times. Returns a problem, or ""."""
    db = main.doc.db
    t = c.text
    if not u.token.file:
        return ""                                         # never recorded: nothing to cut again
    if not t.file:
        return f"{u.ref}: {t.ref} has no recording to cut from"
    wav = storage.text_folder(db) / t.file
    if not wav.exists():
        return f"{u.ref}: {t.file} isn't in Soundfiles\\Texts"
    dst = storage.utterance_folder(db) / u.token.file
    tmp = dst.with_name(dst.stem + ".lemmatrix-new.wav")
    pad = max(0, db.settings.clip_padding) / 1000.0
    try:
        length = audio.duration(wav)
        main.player.stop()
        audio.clip_wav(wav, tmp, max(0.0, u.source.start - pad), min(length, u.source.end + pad),
                       u.token.speaker, u.token.collected)
        if dst.exists() and not QFile.moveToTrash(str(dst)):
            dst.unlink()
        tmp.rename(dst)
    except Exception as exc:                              # audio, OS and wave errors alike
        try:
            tmp.unlink()
        except OSError:
            pass
        return f"{u.ref}: {exc}"
    return ""


def pull_utterances(main, parent, checks: list[pull.Check]) -> bool:
    """Pull these utterances from their lines (after the dialogue). One undo step."""
    checks = [c for c in checks if c.pullable]
    if not checks:
        QMessageBox.information(parent, "Pull from source", "There is nothing to pull: the line is the same, "
                                "or it isn't in the TextGrid any more.")
        return False
    db = main.doc.db
    dlg = PullDialog(parent, db, checks)
    if not dlg.exec():
        return False
    pairs = [(c.utterance, pull.pulled(db, c)) for c in checks]
    n = len(pairs)
    problems = main.doc.apply_changes(f"Pull {checks[0].utterance.ref}" if n == 1 else f"Pull {n} utterances",
                                      pairs)
    if problems:
        QMessageBox.warning(parent, "Pull from source", "\n".join(problems))
        return False
    if dlg.recut.isChecked():
        problems = [p for c in checks if c.moved and (p := recut(main, c, c.utterance))]
        if problems:
            QMessageBox.warning(parent, "Pull from source", "These clips weren't cut again:\n\n"
                                + "\n".join(problems[:30]))
    main.statusBar().showMessage(f"Pulled {checks[0].utterance.ref} from its line." if n == 1 else
                                 f"Pulled {n} utterances from their lines.", 6000)
    return True


def unlink_utterances(main, parent, checks: list[pull.Check]) -> bool:
    """Forget where these utterances were clipped from (they keep their fields and recordings)."""
    if not checks:
        return False
    n = len(checks)
    which = checks[0].utterance.ref if n == 1 else f"these {n} utterances"
    if QMessageBox.question(parent, "Unlink from the text",
                            f"Unlink {which} from the text? The fields and recordings stay; Play in context, "
                            "Show the text and Pull from source won't be there any more.") != QMessageBox.Yes:
        return False
    pairs = [(c.utterance, pull.unlinked(c)) for c in checks]
    main.doc.apply_changes(f"Unlink {checks[0].utterance.ref}" if n == 1 else f"Unlink {n} utterances",
                           pairs, stamp=False)
    return True


class CheckDialog(QDialog):
    """Tools → Check clipped utterances…: every clipped utterance whose line changed or went."""

    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setWindowTitle("Check clipped utterances")
        lay = QVBoxLayout(self)
        self.note = QLabel()
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Utterance", "Text", "Line", "In the TextGrid"])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.itemDoubleClicked.connect(lambda *_: self.show_one())
        self.tree.itemSelectionChanged.connect(self._enable)
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.pull_btn = QPushButton("Pull…")
        self.pull_btn.setToolTip("Pull the selected utterances (all that can be, if none are selected)")
        self.pull_btn.clicked.connect(lambda *_: self.pull())
        self.unlink_btn = QPushButton("Unlink…")
        self.unlink_btn.setToolTip("Forget where the selected utterances were clipped from")
        self.unlink_btn.clicked.connect(lambda *_: self.unlink())
        self.show_btn = QPushButton("Show")
        self.show_btn.setToolTip("Show the utterance in Texts and utterances")
        self.show_btn.clicked.connect(lambda *_: self.show_one())
        for b in (self.pull_btn, self.unlink_btn, self.show_btn):
            row.addWidget(b)
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        self.resize(720, 400)
        self.fill()

    def fill(self):
        db = self.main.doc.db
        checks = pull.check_all(db)
        self.flagged = [c for c in checks.values() if c.flagged]
        self.tree.clear()
        err = theme.colour("error")
        for c in self.flagged:
            u, t = c.utterance, c.text
            it = QTreeWidgetItem([f"{u.ref} {u.label}".strip(), f"{t.ref} {db.text_title(t)}".strip() if t else "",
                                  times(u.source.start, u.source.end), status_label(c)])
            it.setData(0, Qt.UserRole, u.id)
            it.setToolTip(3, pull.describe(c))
            if not c.pullable:
                it.setForeground(3, err)
            self.tree.addTopLevelItem(it)
        for i in range(4):
            self.tree.resizeColumnToContents(i)
        total = len(checks)
        if not total:
            self.note.setText("No utterances have been clipped from texts yet.")
        elif not self.flagged:
            self.note.setText(f"All {total} clipped utterance{'s' if total != 1 else ''} match their lines.")
        else:
            n = len(self.flagged)
            self.note.setText(f"{n} of {total} clipped utterances differ from their lines in the TextGrid, or "
                              "their line or TextGrid isn't there. Pull takes the line as it is now; Unlink "
                              "forgets the line (for one that's gone).")
        self._enable()

    def _selected(self) -> list[pull.Check]:
        ids = {it.data(0, Qt.UserRole) for it in self.tree.selectedItems()}
        return [c for c in self.flagged if c.utterance.id in ids]

    def _enable(self):
        sel = self._selected()
        self.pull_btn.setEnabled(any(c.pullable for c in (sel or self.flagged)))
        self.unlink_btn.setEnabled(bool(sel))
        self.show_btn.setEnabled(len(sel) == 1)

    def pull(self):
        if pull_utterances(self.main, self, self._selected() or self.flagged):
            self.fill()

    def unlink(self):
        if unlink_utterances(self.main, self, self._selected()):
            self.fill()

    def show_one(self):
        sel = self._selected()
        if sel:
            self.main.open_utterances(select=sel[0].utterance)
