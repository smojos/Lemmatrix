# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""File → Restore from backup… (IDEAS.md idea 54, 27 October): the sources, the plan, the restore
point, and that nothing is lost on the way."""

import os
import shutil
import time
import zipfile
from pathlib import Path

import pytest

from lemmatrix import layout, restore, storage

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def _database(tmp_path) -> Path:
    main = tmp_path / "Main"
    main.mkdir()
    for suffix in (".xml", ".notebook", ".workspace"):
        shutil.copy2(SAMPLES / f"Sample{suffix}", main / f"Sample{suffix}")
    tok = main / "Soundfiles" / "Tokens"
    tok.mkdir(parents=True)
    (tok / "a.wav").write_bytes(b"A" * 10)
    (tok / "b.wav").write_bytes(b"B" * 10)
    (main / "Soundfiles" / "_Deleted recordings").mkdir()
    (main / "Soundfiles" / "_Deleted recordings" / "gone.wav").write_bytes(b"G")
    (main / "Documentation").mkdir()
    (main / "Documentation" / "form.pdf").write_bytes(b"pdf")
    for f in main.rglob("*"):                      # all older than what the tests write
        if f.is_file():
            _age(f, 3600)
    return main / "Sample.xml"


def _age(path: Path, seconds: float):
    t = time.time() - seconds
    os.utime(path, (t, t))


def _autosave(db: Path):
    """The three copies a save makes, as storage.make_backup names them, a second apart."""
    for suffix in (".xml", ".notebook", ".workspace"):
        storage.make_backup(db.with_suffix(suffix))
        time.sleep(1.05)


def _zip(db: Path, target: Path) -> Path:
    layout.full_backup(db, target)
    return target


# ---- sources ------------------------------------------------------------------------------------
def test_autosaves_grouped_into_saves(tmp_path):
    db = _database(tmp_path)
    _autosave(db)
    saves = restore.autosaves(db)
    assert len(saves) == 1
    assert set(saves[0].parts()) == {restore.DATABASE, restore.NOTEBOOK, restore.WORKSPACE}
    assert saves[0].label.startswith("Autosave of ")


def test_a_part_pruned_away_is_missing_from_its_save(tmp_path):
    db = _database(tmp_path)
    _autosave(db)
    for f in layout.backups_folder(db).glob("*.notebook"):
        f.unlink()
    (s,) = restore.autosaves(db)
    assert restore.NOTEBOOK not in s.parts() and restore.DATABASE in s.parts()


def test_full_backup_source(tmp_path):
    db = _database(tmp_path)
    src = restore.full_backup(_zip(db, tmp_path / "b.zip"), db)
    assert not src.warnings
    assert set(src.parts()) >= {restore.DATABASE, restore.SOUNDFILES, restore.DOCUMENTATION}
    rels = {m.rel for m in src.members[restore.SOUNDFILES]}
    assert "Soundfiles/Tokens/a.wav" in rels
    assert not any("_Deleted recordings" in r for r in rels)      # held recordings aren't restored


def test_full_backup_of_another_database_warns(tmp_path):
    db = _database(tmp_path)
    z = _zip(db, tmp_path / "b.zip")
    other = tmp_path / "Other" / "Other.xml"
    other.parent.mkdir()
    shutil.copy2(SAMPLES / "Test-300.xml", other)
    src = restore.full_backup(z, other)
    assert src.warnings


def test_not_a_backup(tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("a.txt", "x")
        zf.writestr("b/c.txt", "y")
    db = _database(tmp_path)
    with pytest.raises(restore.RestoreError):
        restore.full_backup(bad, db)


# ---- folders: missing and changed put back, newer here a choice, nothing deleted ---------------
def test_folders_put_back_missing_and_changed(tmp_path):
    db = _database(tmp_path)
    tok = db.parent / "Soundfiles" / "Tokens"
    _age(tok / "a.wav", 3600)
    _age(tok / "b.wav", 3600)
    src = restore.full_backup(_zip(db, tmp_path / "b.zip"), db)
    (tok / "a.wav").unlink()                       # lost
    (tok / "b.wav").write_bytes(b"new take")       # re-recorded since: newer here
    (tok / "c.wav").write_bytes(b"made since")     # not in the backup
    plan = restore.make_plan(db, src, [restore.SOUNDFILES])
    c = plan.counts[restore.SOUNDFILES]
    assert c["add"] == 1 and c["replace"] == 1 and c["newer"] == 1
    rep = restore.apply(plan, keep_newer=True, db_path=db)
    assert not rep.failed
    assert (tok / "a.wav").read_bytes() == b"A" * 10
    assert (tok / "b.wav").read_bytes() == b"new take"         # kept: newer here
    assert (tok / "c.wav").exists()                            # never deleted
    assert rep.kept_newer == 1
    rep = restore.apply(restore.make_plan(db, src, [restore.SOUNDFILES]), db_path=db)
    assert (tok / "b.wav").read_bytes() == b"B" * 10           # the backup's version
    point = restore.restore_point_folder(db)
    assert (point / "Soundfiles" / "Tokens" / "b.wav").read_bytes() == b"new take"


def test_unchanged_files_are_not_written(tmp_path):
    db = _database(tmp_path)
    src = restore.full_backup(_zip(db, tmp_path / "b.zip"), db)
    plan = restore.make_plan(db, src, [restore.SOUNDFILES, restore.DOCUMENTATION])
    assert not plan.to_write()


# ---- the restore point: only what was replaced, and it gives back the state before --------------
def test_restore_point_round_trip(tmp_path):
    db = _database(tmp_path)
    _age(db, 7200)
    _autosave(db)                                  # holds the database as it was
    before = db.read_bytes()
    text = db.read_text("utf-8").replace("<name>Sample</name>", "<name>Changed</name>")
    db.write_text(text, "utf-8")
    changed = db.read_bytes()
    (s,) = restore.autosaves(db)
    plan = restore.make_plan(db, s, [restore.DATABASE])
    rep = restore.apply(plan, db_path=db)
    assert not rep.failed and db.read_bytes() == before
    point = restore.restore_point_folder(db)
    assert (point / "Sample.xml").read_bytes() == changed
    assert sorted(p.name for p in point.iterdir()) == ["Sample.xml", restore.MANIFEST]
    back = restore.restore_point(db)                # restoring from it gives back the state before
    rep = restore.apply(restore.make_plan(db, back, [restore.DATABASE]), db_path=db)
    assert db.read_bytes() == changed
    assert (restore.restore_point_folder(db) / "Sample.xml").read_bytes() == before   # only one kept


def test_only_the_latest_restore_point_is_kept(tmp_path):
    db = _database(tmp_path)
    src = restore.full_backup(_zip(db, tmp_path / "b.zip"), db)
    doc = db.parent / "Documentation" / "form.pdf"
    for content in (b"first", b"second!"):
        doc.write_bytes(content)
        restore.apply(restore.make_plan(db, src, [restore.DOCUMENTATION]), db_path=db)
    backups = layout.backups_folder(db)
    points = [p for p in backups.iterdir() if p.is_dir()]
    assert [p.name for p in points] == [restore.RESTORE_POINT]
    assert (points[0] / "Documentation" / "form.pdf").read_bytes() == b"second!"


def test_discard_callback_gets_the_old_point(tmp_path):
    db = _database(tmp_path)
    src = restore.full_backup(_zip(db, tmp_path / "b.zip"), db)
    doc = db.parent / "Documentation" / "form.pdf"
    trashed = []
    for content in (b"first", b"second!"):
        doc.write_bytes(content)
        restore.apply(restore.make_plan(db, src, [restore.DOCUMENTATION]), db_path=db,
                      discard=lambda f: (trashed.append(f.name), f.unlink()))
    assert "form.pdf" in trashed


def test_autosaves_never_prune_the_restore_point(tmp_path):
    db = _database(tmp_path)
    src = restore.full_backup(_zip(db, tmp_path / "b.zip"), db)
    (db.parent / "Documentation" / "form.pdf").write_bytes(b"first")
    restore.apply(restore.make_plan(db, src, [restore.DOCUMENTATION]), db_path=db)
    for _ in range(3):
        storage.make_backup(db)
    assert (restore.restore_point_folder(db) / "Documentation" / "form.pdf").exists()


# ---- failures: old or new, never half; the point kept ---------------------------------------------
def test_failure_part_way_keeps_old_files_and_point(tmp_path, monkeypatch):
    db = _database(tmp_path)
    tok = db.parent / "Soundfiles" / "Tokens"
    src = restore.full_backup(_zip(db, tmp_path / "b.zip"), db)
    (tok / "a.wav").write_bytes(b"x")
    (tok / "b.wav").write_bytes(b"y")
    plan = restore.make_plan(db, src, [restore.SOUNDFILES])
    real = restore._write_from
    calls = []

    def flaky(fh, dest, mtime):
        calls.append(dest.name)
        if dest.parent.name == "Tokens" and len([c for c in calls if c.endswith(".wav")]) == 4:
            fh.close()
            raise OSError("disk full")
        return real(fh, dest, mtime)
    monkeypatch.setattr(restore, "_write_from", flaky)
    rep = restore.apply(plan, db_path=db)
    assert rep.failed
    assert {(tok / n).read_bytes() for n in ("a.wav", "b.wav")} <= {b"A" * 10, b"B" * 10, b"x", b"y"}
    assert not list(tok.glob("*.part"))
    assert rep.point is not None and "interrupted" in rep.point.name and rep.point.is_dir()


# ---- mixed times, older formats, a new folder ---------------------------------------------------
def test_mixed_times_count_broken_links(tmp_path):
    db = _database(tmp_path)
    tiny = tmp_path / "tiny"
    tiny.mkdir()
    shutil.copy2(SAMPLES / "Test-300.xml", tiny / "Sample.xml")   # another database's lemmas
    with zipfile.ZipFile(tmp_path / "b.zip", "w") as zf:
        zf.write(tiny / "Sample.xml", "Main/Sample.xml")
    src = restore.full_backup(tmp_path / "b.zip", db)
    plan = restore.make_plan(db, src, [restore.DATABASE])
    assert plan.broken_after > plan.broken_now
    assert plan.summary["lemmas"][0] != plan.summary["lemmas"][1]


def test_into_a_new_folder_leaves_the_database_alone(tmp_path):
    db = _database(tmp_path)
    src = restore.full_backup(_zip(db, tmp_path / "b.zip"), db)
    before = {p: p.read_bytes() for p in db.parent.rglob("*") if p.is_file()}
    target = restore.new_folder_for(db)
    plan = restore.make_plan(db, src, [restore.NOTEBOOK, restore.SOUNDFILES], into=target)
    rep = restore.apply(plan, db_path=db)
    assert not rep.failed
    assert {p: p.read_bytes() for p in db.parent.rglob("*") if p.is_file()} == before
    stem = plan.new_stem
    assert (target / f"{stem}.xml").exists()                    # the current XML copied in to open it
    assert (target / f"{stem}.notebook").exists()
    assert (target / "Soundfiles" / "Tokens" / "a.wav").exists()
    loaded = storage.load(target / f"{stem}.xml")
    assert loaded.entries


def test_an_autosave_of_an_older_format_still_opens(tmp_path):
    db = _database(tmp_path)
    old = SAMPLES.parent / "tests" / "data" / "sample"
    olds = sorted(old.glob("*.xml"))
    if not olds:
        pytest.skip("no older-format test database")
    shutil.copy2(olds[0], db)                       # as if the database had been this older file
    _autosave(db)
    shutil.copy2(SAMPLES / "Sample.xml", db)
    (s,) = restore.autosaves(db)
    restore.apply(restore.make_plan(db, s, [restore.DATABASE]), db_path=db)
    assert storage.load(db).entries


def test_note_line(tmp_path):
    db = _database(tmp_path)
    _autosave(db)
    (s,) = restore.autosaves(db)
    plan = restore.make_plan(db, s, [restore.DATABASE, restore.NOTEBOOK])
    assert restore.note_line(plan).startswith("Restored from the autosave of ")
    assert restore.note_line(plan).endswith(": Database, Notebook")


# ---- the window and the main window -------------------------------------------------------------
def _open(make_win, tmp_path):
    db = _database(tmp_path)
    w = make_win(storage.load(db))
    return w, db


def test_restore_in_place_from_the_main_window(make_win, tmp_path, monkeypatch):
    from lemmatrix.ui import restore_dialog
    w, db = _open(make_win, tmp_path)
    _autosave(db)
    before = db.read_bytes()
    n = len(w.doc.db.entries)
    w.doc.db.entries.pop(0)                                       # a lemma gone, saved
    w.save()
    assert db.read_bytes() != before
    monkeypatch.setattr(restore_dialog.RestoreDialog, "exec", lambda self: True)
    assert w.restore_from_backup()
    assert Path(w.doc.db.path) == db                              # opened again
    assert len(w.doc.db.entries) == n                             # the lemma is back
    point = restore.restore_point_folder(db)
    assert (point / "Sample.xml").exists()
    notes = "\n".join(s.notes for s in w.doc.notebook.sessions)
    assert "=====RESTORE HISTORY=====" in notes and "Restored from the autosave of" in notes


def test_the_dialog_greys_what_a_source_lacks(make_win, tmp_path):
    from lemmatrix.ui.restore_dialog import RestoreDialog
    w, db = _open(make_win, tmp_path)
    _autosave(db)
    dlg = RestoreDialog(w, str(db))
    assert dlg.r_auto.isChecked()
    assert dlg.part_boxes[restore.DATABASE].isEnabled()
    assert not dlg.part_boxes[restore.SOUNDFILES].isEnabled()
    assert not dlg.r_point.isEnabled()
    dlg._choose_full(str(_zip(db, tmp_path / "b.zip")))
    assert dlg.r_full.isChecked() and dlg.part_boxes[restore.SOUNDFILES].isEnabled()
    dlg.close()


def test_the_newer_here_checkbox_starts_off(make_win, tmp_path):
    from lemmatrix.ui.restore_dialog import RestoreDialog
    w, db = _open(make_win, tmp_path)
    z = _zip(db, tmp_path / "b.zip")
    (db.parent / "Soundfiles" / "Tokens" / "a.wav").write_bytes(b"re-recorded")
    dlg = RestoreDialog(w, str(db))
    dlg._choose_full(str(z))
    for p, b in dlg.part_boxes.items():
        b.setChecked(p == restore.SOUNDFILES)
    assert not dlg.keep_box.isHidden() and not dlg.keep_box.isChecked()
    assert dlg.ok.isEnabled()
    dlg.close()


def test_refused_while_open_elsewhere(make_win, tmp_path, monkeypatch):
    from lemmatrix.ui import main_window
    w, db = _open(make_win, tmp_path)
    elsewhere = type("Info", (), {"describe": lambda self: "the laptop"})()
    monkeypatch.setattr(main_window.lockmod, "held_elsewhere", lambda p: elsewhere)
    assert not w.restore_from_backup()


def test_a_zip_member_outside_the_folder_is_never_written(tmp_path):
    db = _database(tmp_path)
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(db, "Main/Sample.xml")
        zf.writestr("Main/Soundfiles/../../outside.wav", b"x")
        zf.writestr("Main/Soundfiles/Tokens/ok.wav", b"ok")
    src = restore.full_backup(z, db)
    plan = restore.make_plan(db, src, [restore.SOUNDFILES])
    assert [i.member.rel for i in plan.items] == ["Soundfiles/Tokens/ok.wav"]
    restore.apply(plan, db_path=db)
    assert not (tmp_path / "outside.wav").exists()


# ---- the independent review's findings (27 October) ----------------------------------------------
def test_keep_newer_survives_the_dialog_closing(make_win, tmp_path):
    from lemmatrix.ui.restore_dialog import RestoreDialog
    w, db = _open(make_win, tmp_path)
    z = _zip(db, tmp_path / "b.zip")
    (db.parent / "Soundfiles" / "Tokens" / "a.wav").write_bytes(b"re-recorded")
    dlg = RestoreDialog(w, str(db))
    dlg._choose_full(str(z))
    dlg.keep_box.setChecked(True)
    dlg.accept()
    assert dlg.keep_newer()


def test_duplicate_members_never_wipe_the_original(tmp_path):
    db = _database(tmp_path)
    tok = db.parent / "Soundfiles" / "Tokens"
    (tok / "a.wav").write_bytes(b"ORIGINAL-HERE")
    z = tmp_path / "dup.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(db, "Main/Sample.xml")
        zf.writestr("Main/Soundfiles/Tokens/a.wav", b"v1-backup")
        zf.writestr("Main/Soundfiles/Tokens/A.wav", b"v2-backup")
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with zipfile.ZipFile(z, "a") as zf:
            zf.writestr("Main/Soundfiles/Tokens/a.wav", b"v3-backup")
    src = restore.full_backup(z, db)
    restore.apply(restore.make_plan(db, src, [restore.SOUNDFILES]), db_path=db)
    assert (restore.restore_point_folder(db) / "Soundfiles" / "Tokens" / "a.wav").read_bytes() == b"ORIGINAL-HERE"


def test_a_stray_top_level_file_and_a_damaged_member(tmp_path):
    db = _database(tmp_path)
    z = tmp_path / "odd.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(db, "Main/Sample.xml")
        zf.writestr("readme.txt", "hello")
    assert restore.full_backup(z, db).parts()
    bad = tmp_path / "bad.zip"
    data = bytearray(Path(z).read_bytes())
    i = data.find(b"<database")
    if i > 0:
        data[i:i + 40] = b"\x00" * 40               # garbled inside the stored data
    bad.write_bytes(bytes(data))
    try:
        src = restore.full_backup(bad, db)
        restore.make_plan(db, src, [restore.DATABASE])
    except restore.RestoreError:
        pass


def test_a_file_written_after_the_plan_is_still_copied_first(tmp_path):
    db = _database(tmp_path)
    ws = db.with_suffix(".workspace")
    src = restore.full_backup(_zip(db, tmp_path / "b.zip"), db)
    ws.unlink()
    plan = restore.make_plan(db, src, [restore.WORKSPACE])
    ws.write_text("written after the plan", "utf-8")
    restore.apply(plan, db_path=db)
    assert (restore.restore_point_folder(db) / "Sample.workspace").read_text("utf-8") == "written after the plan"


def test_zip_dates_hours_apart_count_as_the_same(tmp_path):
    db = _database(tmp_path)
    src = restore.full_backup(_zip(db, tmp_path / "b.zip"), db)
    for m in src.members[restore.SOUNDFILES]:
        m.mtime -= 3 * 3600                        # made in a time zone three hours ahead
    plan = restore.make_plan(db, src, [restore.SOUNDFILES])
    assert not plan.to_write()
