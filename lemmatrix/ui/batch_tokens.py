# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The batch box and its closing box (IDEAS.md idea 64, 24 October 2026; lemmatrix/batch.py).

λ→τ with several lemmas selected opens the batch box: for the selected lemmas or every lemma
shown, the tag chips of the token dialogue (Ctrl+click picks more than one in a group), a count
of what it makes, and Fill predicted translations. Create makes one empty token per lemma and
combination as one undo step, then the closing box offers four things: add them to the ɛλicit
request, filter All data to them, and set up the Lemma/Tag and Tag/Tag matrices.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFrame, QLabel,
                               QMessageBox, QPushButton, QRadioButton, QScrollArea, QVBoxLayout)

from .. import batch, filters as fl, matrix as mx
from . import theme
from .tagpanel import TagPanel

PREF_TRANSLATE = "batch/fill_predicted"


def _classes(db, entries) -> list[str]:
    out: list[str] = []
    for e in entries:
        for c in db.classes(e):
            if c not in out:
                out.append(c)
    return out


class BatchDialog(QDialog):
    """Create tokens for several lemmas: the lemmas, the tags, the count, Create."""

    def __init__(self, main, selected: list, shown: list):
        super().__init__(main)
        self.main, self.db = main, main.doc.db
        self.selected, self.shown = list(selected), list(shown)
        self.plan_: batch.Plan | None = None
        self.setWindowTitle("Create tokens")
        lay = QVBoxLayout(self)
        title = QLabel("Create tokens for several lemmas")
        f = title.font()
        f.setPointSize(f.pointSize() + 3)
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f"color: {theme.colour('pitch').name()};")
        lay.addWidget(title)
        self.for_sel = QRadioButton(f"For the {len(self.selected)} selected lemmas")
        self.for_shown = QRadioButton(f"For all {len(self.shown)} lemmas shown")
        grp = QButtonGroup(self)
        for b in (self.for_sel, self.for_shown):
            grp.addButton(b)
            lay.addWidget(b)
            b.toggled.connect(lambda *_: self._lemmas_changed())
        (self.for_sel if len(self.selected) > 1 else self.for_shown).setChecked(True)
        hint = QLabel("A click picks one tag per group; <b>Ctrl+click</b> picks more. Each lemma gets "
                      "one empty token for each combination, with no speaker or date until it is "
                      "collected.")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.tags = TagPanel()
        self.tags.multi = True
        self.tags.on_change = self._schedule
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.tags)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumHeight(320)
        lay.addWidget(scroll, 1)
        self.show_all = False
        self.show_all_btn = QPushButton()
        self.show_all_btn.setCheckable(True)
        self.show_all_btn.toggled.connect(self._show_all_toggled)
        lay.addWidget(self.show_all_btn, 0, Qt.AlignLeft)
        self.count = QLabel()
        self.count.setWordWrap(True)
        self.count.setStyleSheet("font-weight: 600;")
        lay.addWidget(self.count)
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setStyleSheet(f"color: {theme.muted()};")
        lay.addWidget(self.details)
        self.translate = QCheckBox("Fill predicted translations (where Lemmatrix can predict one)")
        self.translate.setChecked(main.prefs.get_bool(PREF_TRANSLATE, True))
        self.translate.toggled.connect(self._schedule)
        lay.addWidget(self.translate)
        box = QDialogButtonBox()
        self.create_btn = box.addButton("Create", QDialogButtonBox.AcceptRole)
        box.addButton(QDialogButtonBox.Cancel)
        box.accepted.connect(self._create)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._update)
        self.resize(560, 720)
        self._build_tags(set())
        self._update()

    # ---- what is picked ----------------------------------------------
    def lemmas(self) -> list:
        return self.selected if self.for_sel.isChecked() else self.shown

    def picked(self) -> list[str]:
        return self.tags.selected()

    def combos(self) -> list[list[str]]:
        return batch.combinations(self.db, self.picked())

    def _lemmas_changed(self):
        if hasattr(self, "tags"):
            self._build_tags(set(self.picked()))
            self._schedule()

    def _build_tags(self, selected: set):
        hidden = self.tags.build(self.db, selected, classes=_classes(self.db, self.lemmas()),
                                 show_all=self.show_all)
        b = self.show_all_btn
        b.blockSignals(True)
        b.setChecked(self.show_all)
        b.blockSignals(False)
        if self.show_all:
            b.setText("Show usual tags only")
            b.setVisible(True)
        else:
            b.setText(f"Show all tags ({hidden} more group{'s' if hidden != 1 else ''})")
            b.setVisible(hidden > 0)

    def _show_all_toggled(self, on):
        self.show_all = bool(on)
        self._build_tags(set(self.picked()))
        self._schedule()

    def _schedule(self, *_):
        self._timer.start()

    def _update(self):
        combos = self.combos()
        ents = self.lemmas()
        if not combos:
            self.plan_ = None
            self.count.setText("Pick the tags for the new tokens.")
            self.details.setText("")
            self.create_btn.setEnabled(False)
            return
        self.plan_ = p = batch.plan(self.db, ents, combos, translate=self.translate.isChecked(),
                                    predictor=getattr(self.main.doc, "predictor", None))
        n = len(combos)
        made = len(p.made)
        text = (f"→ {n} combination{'s' * (n != 1)} × {len(ents)} lemma{'s' * (len(ents) != 1)} = "
                f"{made} token{'s' * (made != 1)}")
        if p.skipped:
            text += f" ({len(p.skipped)} already there, skipped)"
        self.count.setText(text)
        labels = [" + ".join(mx.chips(self.db, c)) for c in combos]
        lines = ["Combinations: " + ", ".join(labels[:12]) + (" …" if len(labels) > 12 else "")]
        if p.skipped:
            sk = [f"{e.ref} {' + '.join(mx.chips(self.db, c))}" for e, c in p.skipped[:8]]
            lines.append("Already there: " + "; ".join(sk) + (" …" if len(p.skipped) > 8 else ""))
        if p.unusual:
            lines.append(f"⚠ Not usual for the word class of {len(p.unusual)} lemma"
                         f"{'s' * (len(p.unusual) != 1)} (allowed, and marked as anywhere).")
        if self.translate.isChecked() and made:
            lines.append(f"Predicted translations: {p.predicted} of {made}"
                         + (f"; {p.untranslated} left empty" if p.untranslated else "") + ".")
        self.details.setText("\n".join(lines))
        self.create_btn.setEnabled(made > 0)

    # ---- Create ---------------------------------------------------------
    def _create(self):
        self._timer.stop()
        self._update()
        p = self.plan_
        if p is None or not p.made:
            return
        if len(p.made) > batch.LIMIT and QMessageBox.question(
                self, "Create tokens", f"This makes {len(p.made)} tokens. Make them all?") != QMessageBox.Yes:
            return
        self.main.prefs.set_value(PREF_TRANSLATE, self.translate.isChecked())
        self.main.doc.apply_changes(batch.label(p), batch.pairs(p), stamp=False)
        self.accept()


class ClosingDialog(QDialog):
    """Made N tokens: four checkboxes for what comes next (Josh, 24 October: all four)."""

    def __init__(self, main, p: batch.Plan, has_tag_tag: bool):
        super().__init__(main)
        self.setWindowTitle("Tokens made")
        lay = QVBoxLayout(self)
        n, m = len(p.made), len(p.lemmas)
        head = QLabel(f"Made {n} token{'s' * (n != 1)} for {m} lemma{'s' * (m != 1)}"
                      + (f" ({len(p.skipped)} already there)." if p.skipped else "."))
        f = head.font()
        f.setBold(True)
        head.setFont(f)
        lay.addWidget(head)
        note = QLabel("They have no speaker or date until they are recorded. Ctrl+Z takes them all "
                      "away again.")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.elicit = QCheckBox("Add them to the ɛλicit request")
        self.filter = QCheckBox("Filter in All data (these lemmas and tags)")
        self.lemma_tag = QCheckBox("Set up the Lemma/Tag matrix")
        self.tag_tag = QCheckBox("Set up the Tag/Tag matrix")
        for c in (self.elicit, self.filter, self.lemma_tag, self.tag_tag):
            c.setChecked(True)
            lay.addWidget(c)
        if not has_tag_tag:
            self.tag_tag.setChecked(False)
            self.tag_tag.setEnabled(False)
            self.tag_tag.setToolTip("Tag/Tag needs tags from two groups or more (rows and columns).")
        box = QDialogButtonBox(QDialogButtonBox.Ok)
        box.accepted.connect(self.accept)
        lay.addWidget(box)


def follow_up(main, p: batch.Plan, picked, elicit=True, filter_all=True, lemma_tag=True, tag_tag=True) -> list[str]:
    """Do the closing box's checkboxes. Returns what was done, for the status bar."""
    from .main_window import ALL_DATA, LEMMA_TAG, TAG_TAG
    db = main.doc.db
    done = []
    if elicit:
        main.add_to_elicit([t for _, t in p.made])
        done.append("added to the ɛλicit request")
    lt, tt = batch.matrices(db, picked)
    for on, cfg, tab in ((lemma_tag, lt, LEMMA_TAG), (tag_tag, tt, TAG_TAG)):
        if not on or cfg is None:
            continue
        saved = batch.same_saved(db, cfg)
        main.configs[cfg.kind] = saved.copy() if saved is not None else cfg
        name = "Lemma/Tag" if tab == LEMMA_TAG else "Tag/Tag"
        done.append(f"{name}: the saved matrix {mx.shown_matrix_name(saved.name)}" if saved is not None
                    else f"{name} set up (Save matrix to keep it)")
    if filter_all:
        main.lemmas.pin_rows(p.lemmas)
        main.all_table.proxy.set_filter("tags", fl.ChoiceFilter(set(picked), fl.ANY))
        main.all_table._refresh_header()
        main.all_table.filtersChanged.emit()
        main.tabs.setCurrentIndex(ALL_DATA)
        done.append("All data filtered")
    for tab in (LEMMA_TAG, TAG_TAG):
        main._fill_saved(tab)
    main.refresh()
    return done


def run_batch(main) -> batch.Plan | None:
    """λ→τ with several lemmas selected: the batch box, then the closing box."""
    selected = main.lemmas.selected_rows()
    shown = main.lemmas.visible_rows()
    dlg = BatchDialog(main, selected, shown)
    if not dlg.exec():
        return None
    p, picked = dlg.plan_, dlg.picked()
    has_tt = batch.matrices(main.doc.db, picked)[1] is not None
    close = ClosingDialog(main, p, has_tt)
    close.exec()
    done = follow_up(main, p, picked, close.elicit.isChecked(), close.filter.isChecked(),
                     close.lemma_tag.isChecked(), close.tag_tag.isChecked() and has_tt)
    main.statusBar().showMessage(f"{batch.label(p)}" + (": " + "; ".join(done) if done else "") + ".", 12000)
    return p
