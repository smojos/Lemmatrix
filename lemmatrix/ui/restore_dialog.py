# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""File → Restore from backup… (IDEAS.md idea 54; Josh, 27 October): From, What, Where, a preview,
then Restore. The work itself is lemmatrix/restore.py."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QGridLayout,
                               QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QRadioButton,
                               QVBoxLayout)

from .. import restore
from . import theme

POINT_NOTE = ("Only the most recent restore point is kept (Backups › Before restore): each restore replaces "
              "it. For a copy that stays, make a full backup first (File → Full backup…).")


def _size(n: int) -> str:
    for unit in ("bytes", "kB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def _heading(text: str) -> QLabel:
    lab = QLabel(text)
    f = lab.font()
    f.setBold(True)
    lab.setFont(f)
    lab.setStyleSheet(f"color: {theme.accent().name()};")
    return lab


class RestoreDialog(QDialog):
    """Choose a source, its parts and where; the preview says what will happen. On accept:
    self.plan and self.keep_newer()."""

    def __init__(self, parent, db_path: str, start_folder: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Restore from backup")
        self.resize(640, 640)
        self.db_path = Path(db_path)
        self.start_folder = start_folder
        self.plan = None
        self._kept = None
        self.source = None
        self.full = None
        self.saves = restore.autosaves(self.db_path)
        self.point = restore.restore_point(self.db_path)
        lay = QVBoxLayout(self)

        lay.addWidget(_heading("From"))
        self.from_group = QButtonGroup(self)
        self.r_auto = QRadioButton("An autosave (the database, notebook and workspace as saved then)")
        self.r_full = QRadioButton("A full backup")
        self.r_point = QRadioButton("Before the last restore")
        for i, r in enumerate((self.r_auto, self.r_full, self.r_point)):
            self.from_group.addButton(r, i)
        lay.addWidget(self.r_auto)
        self.saves_list = QListWidget()
        self.saves_list.setMaximumHeight(150)
        for s in self.saves:
            have = ", ".join(restore.LABELS[p].split(" (")[0] for p in s.parts())
            item = QListWidgetItem(f"{s.label[len('Autosave of '):]}  ·  {have}")
            self.saves_list.addItem(item)
        if not self.saves:
            self.r_auto.setEnabled(False)
            self.r_auto.setText(self.r_auto.text() + ": none in Backups yet")
        lay.addWidget(self.saves_list)
        row = QHBoxLayout()
        row.addWidget(self.r_full)
        self.full_button = QPushButton("Choose…")
        self.full_label = QLabel("")
        self.full_label.setStyleSheet(f"color: {theme.muted()};")
        row.addWidget(self.full_button)
        row.addWidget(self.full_label, 1)
        lay.addLayout(row)
        lay.addWidget(self.r_point)
        if self.point is None:
            self.r_point.setEnabled(False)
            self.r_point.setText(self.r_point.text() + ": no restore point yet")
        else:
            self.r_point.setText(f"{self.point.label} · {_size(restore.size_of(restore.restore_point_folder(self.db_path)))}")

        lay.addWidget(_heading("What"))
        grid = QGridLayout()
        self.part_boxes = {}
        for n, part in enumerate(restore.PARTS):
            box = QCheckBox(restore.LABELS[part])
            box.toggled.connect(self._update)
            self.part_boxes[part] = box
            grid.addWidget(box, n % 4, n // 4)
        lay.addLayout(grid)

        lay.addWidget(_heading("Where"))
        self.where_group = QButtonGroup(self)
        self.r_here = QRadioButton("Here, over this database (what it replaces goes into the restore point)")
        self.r_new = QRadioButton(f"Into a new folder: {QDir.toNativeSeparators(str(restore.new_folder_for(self.db_path)))}")
        self.r_new.setToolTip("A copy beside this database's folder, to look at or compare; this database is untouched.")
        self.where_group.addButton(self.r_here, 0)
        self.where_group.addButton(self.r_new, 1)
        self.r_here.setChecked(True)
        lay.addWidget(self.r_here)
        lay.addWidget(self.r_new)

        lay.addWidget(_heading("What will happen"))
        self.preview = QLabel("")
        self.preview.setWordWrap(True)
        self.preview.setTextFormat(Qt.RichText)
        lay.addWidget(self.preview)
        self.keep_box = QCheckBox("")
        self.keep_box.setChecked(False)               # Josh: off; the backup's version goes back
        self.keep_box.toggled.connect(self._update)
        lay.addWidget(self.keep_box)
        note = QLabel(POINT_NOTE)
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.muted()};")
        lay.addWidget(note)
        lay.addStretch(1)

        self.buttons = QDialogButtonBox()
        self.ok = self.buttons.addButton("Restore", QDialogButtonBox.AcceptRole)
        self.buttons.addButton(QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)

        self.from_group.idToggled.connect(lambda *_: self._source_changed())
        self.where_group.idToggled.connect(lambda *_: self._update())
        self.saves_list.currentRowChanged.connect(lambda *_: self._pick_auto())
        self.full_button.clicked.connect(self._choose_full)
        if self.saves:
            self.r_auto.setChecked(True)
            self.saves_list.setCurrentRow(0)
        self._source_changed()

    # ---- the source -------------------------------------------------------------------------
    def _pick_auto(self):
        if not self.r_auto.isChecked():
            self.r_auto.setChecked(True)
        else:
            self._source_changed()

    def _choose_full(self, path: str = ""):
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Restore from a full backup", self.start_folder,
                                                  "Full backup (*.zip)")
        if not path:
            return
        try:
            self.full = restore.full_backup(path, self.db_path)
        except restore.RestoreError as exc:
            self.full = None
            self.full_label.setText(str(exc))
            return
        self.full_label.setText(Path(path).name)
        if self.r_full.isChecked():
            self._source_changed()
        else:
            self.r_full.setChecked(True)

    def _source_changed(self):
        src = None
        if self.r_auto.isChecked():
            row = self.saves_list.currentRow()
            src = self.saves[row] if 0 <= row < len(self.saves) else None
        elif self.r_full.isChecked():
            src = self.full
        elif self.r_point.isChecked():
            src = self.point
        self.saves_list.setEnabled(self.r_auto.isChecked())
        changed = src is not self.source
        self.source = src
        have = set(src.parts()) if src else set()
        for part, box in self.part_boxes.items():
            box.blockSignals(True)
            box.setEnabled(part in have)
            if part not in have:
                box.setChecked(False)
            elif changed:
                box.setChecked(True)          # everything the source has, to deselect
            box.blockSignals(False)
        self._update()

    # ---- the preview ------------------------------------------------------------------------
    def parts(self) -> list:
        return [p for p, b in self.part_boxes.items() if b.isChecked() and b.isEnabled()]

    def keep_newer(self) -> bool:
        """Read while the dialog is open and kept on accept (hidden afterwards: the review)."""
        if self._kept is not None:
            return self._kept
        return not self.keep_box.isHidden() and self.keep_box.isChecked()

    def accept(self):
        self._kept = not self.keep_box.isHidden() and self.keep_box.isChecked()
        super().accept()

    def _update(self):
        self.plan = None
        self.keep_box.setVisible(False)
        if self.source is None:
            self.preview.setText("Choose what to restore from.")
            self.ok.setEnabled(False)
            return
        parts = self.parts()
        if not parts:
            self.preview.setText("Choose at least one part.")
            self.ok.setEnabled(False)
            return
        into = restore.new_folder_for(self.db_path) if self.r_new.isChecked() else None
        try:
            plan = restore.make_plan(self.db_path, self.source, parts, into)
        except (restore.RestoreError, OSError, *restore.ZIP_ERRORS) as exc:
            self.preview.setText(f"Can't restore from this: {exc}")
            self.ok.setEnabled(False)
            return
        self.plan = plan
        lines = []
        for w in self.source.warnings:
            lines.append(f"<b style='color:{theme.colour('error').name()}'>⚠ {w}</b>")
        s = plan.summary
        if "lemmas" in s:
            lines.append(f"Database: {s['lemmas'][0]:,} → {s['lemmas'][1]:,} lemmas, "
                         f"{s['tokens'][0]:,} → {s['tokens'][1]:,} tokens")
        if "days" in s:
            lines.append(f"Notebook: {s['days'][0]} → {s['days'][1]} days")
        newer = plan.newer()
        for part in plan.parts:
            c = plan.counts[part]
            if part in restore.FILE_PARTS:
                if part == restore.WORKSPACE or (part == restore.NOTEBOOK and "days" not in s):
                    lines.append(f"{restore.LABELS[part]}: " + ("unchanged" if c["same"] else "restored"))
                continue
            bits = []
            if c["add"]:
                bits.append(f"{c['add']} put back")
            if c["replace"]:
                bits.append(f"{c['replace']} replaced" + (f" ({c['newer']} newer here)" if c["newer"] else ""))
            if c["same"]:
                bits.append(f"{c['same']} already the same")
            lines.append(f"{restore.LABELS[part].split(' (')[0]}: " + (", ".join(bits) or "nothing in the backup"))
        lines.append("Files made since the backup are left as they are; nothing is deleted.")
        more = plan.broken_after - plan.broken_now
        if more > 0:
            lines.append(f"<span style='color:{theme.colour('warning').name()}'>⚠ {more} notebook link"
                         f"{'s' if more != 1 else ''} will point at a lemma or token the restored database "
                         "doesn't have (they show as no longer existing).</span>")
        if newer:
            self.keep_box.setText(f"Keep the {newer} file{'s' if newer != 1 else ''} that "
                                  f"{'are' if newer != 1 else 'is'} newer here (re-recorded since the backup)")
            self.keep_box.setVisible(True)
        writes = len(plan.to_write(self.keep_newer()))
        if not writes and not plan.into_new:
            lines.append("<b>Nothing to restore: everything chosen is already as the backup has it.</b>")
        self.preview.setText("<br>".join(lines))
        self.ok.setEnabled(bool(writes) or plan.into_new)
