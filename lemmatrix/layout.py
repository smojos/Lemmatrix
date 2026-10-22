# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""The fixed folder layout of a database's main folder (format 4, 18 October 2026).

    Main folder/
    ├─ <database>.xml
    ├─ <database>.notebook
    ├─ <database>.workspace    working state: saved matrices, filters, the session… (idea 36)
    ├─ Soundfiles/
    │  ├─ Tokens/              lemma tokens' recordings
    │  ├─ Utterances/          (idea 7, stage 2)
    │  ├─ Texts/               (idea 7, stage 3)
    │  └─ _Deleted recordings/ deleted tokens' recordings, held for undo
    ├─ Backups/                the automatic local backups
    ├─ Documentation/          consent forms and other documentation
    ├─ Images/                 pictures for ɛλicit requests, named by reference and tags (idea 19)
    ├─ Whiteboard/             drawings saved from Tools → Whiteboard (idea 45), the researcher's own
    └─ Exports/                where File → Export starts

Lemmatrix assumes this layout instead of keeping paths in the settings. One database per
main folder: two would share Soundfiles. Also here: relinking consent forms moved into
Documentation, and the full backup (the whole main folder as one zip). No Qt in this module.
"""

from __future__ import annotations

import datetime as _dt
import os
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

SOUNDFILES = "Soundfiles"
TOKENS = "Tokens"
UTTERANCES = "Utterances"
TEXTS = "Texts"
HELD = "_Deleted recordings"
BACKUPS = "Backups"
DOCUMENTATION = "Documentation"
EXPORTS = "Exports"
IMAGES = "Images"
WHITEBOARD = "Whiteboard"                  # made when a drawing is first saved (idea 45)
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif")
REMIND_DAYS = 7                            # the full-backup reminder


def main_folder(db_path) -> Path:
    """The folder the database file is in (the current folder for an unsaved database)."""
    return Path(db_path).parent if db_path else Path.cwd()


def soundfiles(db_path) -> Path:
    return main_folder(db_path) / SOUNDFILES


def tokens_folder(db_path) -> Path:
    return soundfiles(db_path) / TOKENS


def texts_folder(db_path) -> Path:
    return soundfiles(db_path) / TEXTS


def utterances_folder(db_path) -> Path:
    return soundfiles(db_path) / UTTERANCES


def held_folder(db_path) -> Path:
    return soundfiles(db_path) / HELD


def backups_folder(db_path) -> Path:
    return main_folder(db_path) / BACKUPS


def documentation_folder(db_path) -> Path:
    return main_folder(db_path) / DOCUMENTATION


def exports_folder(db_path) -> Path:
    return main_folder(db_path) / EXPORTS


def images_folder(db_path) -> Path:
    return main_folder(db_path) / IMAGES


def create_layout(db_path):
    """The folders a new database starts with (Backups comes with the first save)."""
    for folder in (tokens_folder(db_path), utterances_folder(db_path), texts_folder(db_path),
                   documentation_folder(db_path), images_folder(db_path),
                   exports_folder(db_path)):
        folder.mkdir(parents=True, exist_ok=True)


def existing_folder(folder: Path) -> Path:
    """The folder, made if it isn't there yet (for a file dialogue to start in)."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return folder.parent
    return folder


# --------------------------------------------------------------------------
# One database per main folder
# --------------------------------------------------------------------------

def is_database(path: Path) -> bool:
    """Whether a file is a Lemmatrix database (its top element is <database>); cheap."""
    try:
        for _, el in ET.iterparse(str(path), events=("start",)):
            return el.tag == "database"
    except (ET.ParseError, OSError, UnicodeError, ValueError):
        return False
    return False


def other_databases(db_path) -> list[Path]:
    """Other Lemmatrix databases in the same main folder (they would share its Soundfiles)."""
    if not db_path:
        return []
    me = Path(db_path)
    out = []
    try:
        candidates = sorted(main_folder(me).glob("*.xml"))
    except OSError:
        return []
    for p in candidates:
        try:
            if p.name == me.name or (me.exists() and os.path.samefile(p, me)):
                continue
        except OSError:
            continue
        if is_database(p):
            out.append(p)
    return out


# --------------------------------------------------------------------------
# Consent forms moved into Documentation
# --------------------------------------------------------------------------

def consent_full_path(db, consent: str) -> Path | None:
    """A consent link as a full path (a relative one is relative to the main folder)."""
    if not consent:
        return None
    p = Path(consent.replace("\\", os.sep) if os.sep == "/" else consent)
    if not p.is_absolute() and db.path:
        p = main_folder(db.path) / p
    return p


def relink_consent(db) -> list[str]:
    """Consent forms that aren't where their links say, found by name in Documentation.

    The link is changed to the form's place in Documentation (relative to the main folder).
    Returns the participant codes relinked."""
    if not db.path:
        return []
    doc = documentation_folder(db.path)
    if not doc.is_dir():
        return []
    index: dict[str, Path] = {}
    try:
        for root, dirs, files in os.walk(doc):
            for name in list(files) + list(dirs):
                index.setdefault(name.lower(), Path(root) / name)
    except OSError:
        return []
    relinked = []
    main = main_folder(db.path)
    for p in db.metadata.participants:
        if not p.consent:
            continue
        current = consent_full_path(db, p.consent)
        if current is not None and current.exists():
            continue
        found = index.get(current.name.lower()) if current is not None else None
        if found is None:
            continue
        try:
            p.consent = str(found.relative_to(main))
        except ValueError:
            p.consent = str(found)
        relinked.append(p.code)
    return relinked


# --------------------------------------------------------------------------
# Full backup: the whole main folder as one zip
# --------------------------------------------------------------------------

STORED = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".zip", ".7z", ".jpg", ".jpeg", ".png", ".pdf", ".mp4")


def full_backup_name(db_path, day: _dt.date | None = None) -> str:
    """e.g. "LXX-VXX_Complete_Lexicon 2026-10-18.zip"."""
    day = day or _dt.date.today()
    return f"{Path(db_path).stem} {day.isoformat()}.zip"


def inside(path: Path, folder: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(folder).resolve())
        return True
    except (ValueError, OSError):
        return False


def backup_files(db_path) -> list[Path]:
    """Every file the full backup takes: the main folder and its subfolders, without the
    open-database markers and half-finished saves."""
    main = main_folder(db_path)
    out = []
    for root, dirs, files in os.walk(main):
        dirs.sort()
        for name in sorted(files):
            if name.endswith(".lemmatrix-lock") or name.endswith(".lemmatrix-renaming") \
                    or name.endswith(".tmp"):
                continue
            out.append(Path(root) / name)
    return out


class Cancelled(Exception):
    pass


def full_backup(db_path, target, progress=None) -> int:
    """Zip the main folder (and everything in it) to target, which must be outside it.

    progress(done, total, name) is called before each file; it can raise Cancelled. The zip
    is written under a temporary name first, so a cancelled or failed backup leaves nothing
    behind. Recordings and other already-compressed files are stored as they are (they hardly
    compress), everything else is compressed. Returns the number of files."""
    main = main_folder(db_path)
    target = Path(target)
    if inside(target, main):
        raise ValueError("A full backup can't go inside the database's own folder.")
    files = backup_files(db_path)
    tmp = target.with_name(target.name + ".part")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            for n, f in enumerate(files):
                rel = f.relative_to(main)
                if progress is not None:
                    progress(n, len(files), str(rel))
                kind = zipfile.ZIP_STORED if f.suffix.lower() in STORED else zipfile.ZIP_DEFLATED
                zf.write(f, Path(main.name) / rel, compress_type=kind)
            if progress is not None:
                progress(len(files), len(files), "")
        os.replace(tmp, target)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return len(files)


def reminder_due(last: str, snoozed: str, first_seen: str, today: _dt.date | None = None) -> bool:
    """Whether to remind about a full backup: the last one is REMIND_DAYS or more days old (or,
    with none yet, the database was first opened that long ago), and the reminder isn't
    put off. Dates are ISO strings; "" for none."""
    today = today or _dt.date.today()

    def day(s):
        try:
            return _dt.date.fromisoformat(s) if s else None
        except ValueError:
            return None
    if (d := day(snoozed)) is not None and today < d:
        return False
    since = day(last) or day(first_seen)
    return since is not None and (today - since).days >= REMIND_DAYS


# --------------------------------------------------------------------------
# File → Rename database
# --------------------------------------------------------------------------

class RenameError(Exception):
    pass


BAD_IN_FILE_NAMES = '/\\:*?"<>|'


def suggested_stem(old_stem: str, old_name: str, new_name: str, language: str = "", variety: str = "") -> str:
    """The file name for a renamed database: the old file name with its name part swapped
    ("LXX-VXX_Complete_Lexicon" → "LXX-VXX_Main_Database"), or language-variety_name."""
    new_part = "_".join(new_name.split())
    for old_part in ("_".join(old_name.split()), old_name.strip()):
        if old_part and old_part in old_stem:
            return old_stem.replace(old_part, new_part, 1)
    prefix = "-".join(p for p in (language, variety) if p)
    return f"{prefix}_{new_part}" if prefix and new_part else new_part or old_stem


def stem_problem(stem: str) -> str:
    """Why the name can't be a file name ("" if it can)."""
    if not stem.strip():
        return "The file name is empty."
    bad = sorted({c for c in stem if c in BAD_IN_FILE_NAMES})
    if bad:
        return f"File names can't have {' '.join(bad)} in them."
    if stem != stem.strip() or stem.endswith("."):
        return "A file name can't begin or end with a space, or end with a full stop."
    return ""


def _backup_pattern(stem: str):
    import re
    return re.compile(re.escape(stem) + r"(_\d{4}-\d{2}-\d{2}_\d{6}(?:_\d+)?)(\.xml|\.notebook|\.workspace)$")


def rename_plan(db_path, new_stem: str) -> list[tuple[Path, Path]]:
    """What renaming the database renames: the database, its notebook, its workspace and its automatic
    backups (so they are still cleared out as new ones are made). Raises RenameError."""
    old = Path(db_path)
    problem = stem_problem(new_stem)
    if problem:
        raise RenameError(problem)
    new = old.with_name(new_stem + old.suffix)
    plan = [(old, new)]
    notebook = old.with_suffix(".notebook")
    if notebook.exists():
        plan.append((notebook, new.with_suffix(".notebook")))
    workspace = old.with_suffix(".workspace")
    if workspace.exists():
        plan.append((workspace, new.with_suffix(".workspace")))
    folder = backups_folder(old)
    if folder.is_dir():
        pat = _backup_pattern(old.stem)
        for f in sorted(folder.iterdir()):
            m = pat.match(f.name)
            if m:
                plan.append((f, f.with_name(new_stem + m.group(1) + m.group(2))))
    for src, dst in plan:
        if dst.exists() and not _same(src, dst):
            raise RenameError(f"There is already a {dst.name} in {dst.parent.name}.")
    return plan


def _same(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def rename_database(db_path, new_stem: str) -> Path:
    """Rename the database file, its notebook and its backups; all or nothing. Returns the
    new path. Raises RenameError."""
    plan = rename_plan(db_path, new_stem)
    done = []
    for src, dst in plan:
        try:
            if src.name != dst.name:
                src.rename(dst)
            done.append((src, dst))
        except OSError as exc:
            for s, d in reversed(done):
                try:
                    d.rename(s)
                except OSError:
                    pass
            raise RenameError(f"Couldn't rename {src.name}: {exc}") from exc
    return plan[0][1]
