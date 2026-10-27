# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""File → Restore from backup… (IDEAS.md idea 54; designed with Josh 27 October). No Qt here.

Three sources:
- **Autosaves** in Backups/: on each save the previous XML, notebook and workspace are each copied
  as {stem}_YYYY-MM-DD_HHMMSS.{xml,notebook,workspace} (storage.make_backup), seconds apart and
  pruned each on its own. Copies within GROUP_SECONDS of each other are one save.
- **Full backups**: the zip File → Full backup makes (the main folder's top folder inside it).
- **The restore point**: Backups/Before restore/, what the last restore replaced (Josh: only the
  most recent is kept; a permanent copy is a Full backup's job).

Any combination of PARTS. Folders: what the backup has is put back when missing or changed; files
made since are left alone, nothing is ever deleted; a file newer here is replaced unless the
researcher keeps them (a checkbox, off by default; Josh). Every file replaced is first copied into
the new restore point, and every file is written under a temporary name, put on the disk and
swapped in, so a failure at any moment leaves the old file or the new one, never half of one.
"Changed" is judged by size and date only, never by reading the file, so OneDrive's online-only
recordings aren't downloaded just to compare.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import time
import xml.etree.ElementTree as ET
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from . import layout

DATABASE, NOTEBOOK, WORKSPACE = "database", "notebook", "workspace"
SOUNDFILES, DOCUMENTATION, IMAGES, WHITEBOARD, ELICIT = "soundfiles", "documentation", "images", "whiteboard", "elicit"
FILE_PARTS = {DATABASE: ".xml", NOTEBOOK: ".notebook", WORKSPACE: ".workspace"}
FOLDER_PARTS = {SOUNDFILES: layout.SOUNDFILES, DOCUMENTATION: layout.DOCUMENTATION, IMAGES: layout.IMAGES,
                WHITEBOARD: layout.WHITEBOARD, ELICIT: "Elicit"}
PARTS = (DATABASE, NOTEBOOK, WORKSPACE, SOUNDFILES, DOCUMENTATION, IMAGES, WHITEBOARD, ELICIT)
LABELS = {DATABASE: "Database (XML)", NOTEBOOK: "Notebook", WORKSPACE: "Workspace",
          SOUNDFILES: "Soundfiles (Tokens, Utterances, Texts, Segments)", DOCUMENTATION: "Documentation",
          IMAGES: "Images", WHITEBOARD: "Whiteboard", ELICIT: "Elicit"}
SKIPPED_FOLDERS = {layout.HELD}            # deleted recordings held for undo: not restored
RESTORE_POINT = "Before restore"           # in Backups/
MANIFEST = "restore.json"
GROUP_SECONDS = 10
SAME_SECONDS = 2.0                         # zip dates have two-second steps
_STAMP = re.compile(r"_(\d{4}-\d{2}-\d{2})_(\d{6})(?:_\d+)?$")


class RestoreError(Exception):
    pass


# what a damaged or unusual zip raises while being read (the review, 27 October)
ZIP_ERRORS = (zipfile.BadZipFile, zlib.error, RuntimeError, EOFError, NotImplementedError, KeyError)


# --------------------------------------------------------------------------
# What a source holds: for each part, (path relative to the main folder, how to read it, size, date)
# --------------------------------------------------------------------------
@dataclass
class Member:
    rel: str                               # where it goes, relative to the main folder ("/" separators)
    size: int
    mtime: float
    path: Path | None = None               # a file on disk, or
    zip_name: str = ""                     # a member of the source's zip


@dataclass
class Source:
    kind: str                              # "autosave", "full", "point"
    label: str
    members: dict = field(default_factory=dict)    # part -> [Member]
    zip_path: Path | None = None
    when: float = 0.0                      # for listing: the data's own date
    stem: str = ""                         # the database's stem inside the source
    warnings: list = field(default_factory=list)

    def parts(self) -> list[str]:
        return [p for p in PARTS if self.members.get(p)]

    def open(self, m: Member):
        if m.path is not None:
            return open(m.path, "rb")
        zf = zipfile.ZipFile(self.zip_path)
        fh = zf.open(m.zip_name)
        orig_close = fh.close

        def close():
            orig_close()
            zf.close()
        fh.close = close
        return fh


def _when_text(ts: float) -> str:
    d = _dt.datetime.fromtimestamp(ts)
    return f"{d.day} {d.strftime('%B %Y, %H:%M')}"


def autosaves(db_path) -> list[Source]:
    """The autosaves in Backups/, one Source per save, newest first."""
    db_path = Path(db_path)
    stem = db_path.stem
    folder = layout.backups_folder(db_path)
    if not folder.is_dir():
        return []
    pattern = layout.backup_name_pattern(stem)
    found = []                             # (stamp time, part, path)
    for f in folder.iterdir():
        mt = pattern.match(f.name)
        if not mt or not f.is_file():
            continue
        st = _STAMP.match(mt.group(1))
        try:
            when = _dt.datetime.strptime(st.group(1) + st.group(2), "%Y-%m-%d%H%M%S").timestamp()
        except (AttributeError, ValueError):
            continue
        part = {v: k for k, v in FILE_PARTS.items()}[mt.group(2)]
        found.append((when, part, f))
    found.sort(key=lambda x: x[0], reverse=True)
    groups: list[list] = []
    for when, part, f in found:
        g = groups[-1] if groups else None
        if g is not None and g[0][0] - when <= GROUP_SECONDS and part not in {p for _, p, _ in g}:
            g.append((when, part, f))
        else:
            groups.append([(when, part, f)])
    out = []
    for g in groups:
        src = Source("autosave", "", stem=stem)
        for _, part, f in g:
            s = f.stat()
            src.members[part] = [Member(stem + FILE_PARTS[part], s.st_size, s.st_mtime, path=f)]
        data = src.members.get(DATABASE) or next(iter(src.members.values()))
        src.when = data[0].mtime            # when that version was written (copy2 keeps the date)
        src.label = "Autosave of " + _when_text(src.when)
        out.append(src)
    out.sort(key=lambda s: s.when, reverse=True)
    return out


def _folder_part(rel_parts: tuple) -> str | None:
    if len(rel_parts) < 2:
        return None
    for part, name in FOLDER_PARTS.items():
        if rel_parts[0] == name:
            if part == SOUNDFILES and rel_parts[1] in SKIPPED_FOLDERS:
                return None
            return part
    return None


def _unsafe(rel: str) -> bool:
    """A member whose path could land outside the main folder ("..", absolute, a drive, a
    backslash): never restored (a zip from elsewhere could hold one)."""
    if not rel or rel.startswith("/") or "\\" in rel or ":" in rel:
        return True
    return any(p in ("", ".", "..") for p in rel.split("/"))


def _skip_name(name: str) -> bool:
    return name.endswith(layout.HALF_WRITTEN) or name.endswith(".lemmatrix-lock")


def _zip_time(info: zipfile.ZipInfo) -> float:
    try:
        return time.mktime(info.date_time + (0, 0, -1))
    except (OverflowError, ValueError):
        return 0.0


def _read_head(fh, n=8192) -> str:
    try:
        return fh.read(n).decode("utf-8", "replace")
    finally:
        fh.close()


def _identity(head: str) -> tuple[str, str]:
    """(language code, database name) from the start of a database file."""
    code = re.search(r'<language[^>]*\bcode="([^"]*)"', head)
    name = re.search(r"<name>([^<]*)</name>", head)
    return (code.group(1) if code else "", name.group(1) if name else "")


def full_backup(zip_path, db_path=None) -> Source:
    """A full backup zip as a Source. Warns (Source.warnings) if it looks like another database."""
    zip_path = Path(zip_path)
    try:
        zf = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise RestoreError(f"{zip_path.name} can't be read as a zip: {exc}")
    try:
        with zf:
            return _full_backup(zf, zip_path, db_path)
    except ZIP_ERRORS as exc:
        raise RestoreError(f"{zip_path.name} can't be read: {exc}")


def _full_backup(zf, zip_path, db_path):
    infos = [i for i in zf.infolist() if not i.is_dir()]
    tops = {i.filename.split("/", 1)[0] for i in infos if "/" in i.filename}
    if len(tops) != 1:
        raise RestoreError(f"{zip_path.name} isn't a Lemmatrix full backup (it should hold one folder).")
    top = tops.pop()
    xmls = [i for i in infos if i.filename.count("/") == 1 and i.filename.lower().endswith(".xml")]
    dbs = [i for i in xmls if "<database" in _read_head(zf.open(i), 400)]
    if not dbs:
        raise RestoreError(f"{zip_path.name} has no Lemmatrix database in it.")
    want = Path(db_path).stem if db_path else ""
    chosen = next((i for i in dbs if Path(i.filename).stem == want), dbs[0])
    stem = Path(chosen.filename).stem
    src = Source("full", f"Full backup {zip_path.name}", zip_path=zip_path, stem=stem,
                 when=_zip_time(chosen))
    cur_stem = want or stem
    for i in infos:
        if "/" not in i.filename:
            continue                   # a stray file beside the top folder
        rel = i.filename.split("/", 1)[1]
        if _unsafe(rel):
            continue
        parts = tuple(rel.split("/"))
        if _skip_name(parts[-1]):
            continue
        m = Member(rel, i.file_size, _zip_time(i), zip_name=i.filename)
        if len(parts) == 1:
            for part, suffix in FILE_PARTS.items():
                if rel == stem + suffix:
                    m.rel = cur_stem + suffix       # it goes over the current database's file
                    src.members[part] = [m]
            continue
        part = _folder_part(parts)
        if part is not None:
            src.members.setdefault(part, []).append(m)
    if db_path and Path(db_path).exists():
        here = _identity(Path(db_path).read_text("utf-8", "replace")[:8192])
        there = _identity(_read_head(zf.open(chosen)))
        if stem != want:
            src.warnings.append(f"The database in this backup is {stem}.xml, not {want}.xml.")
        if here[0] and there[0] and here[0] != there[0]:
            src.warnings.append(f"Its language code is {there[0]}, this database's is {here[0]}.")
        elif here[1] and there[1] and here[1] != there[1]:
            src.warnings.append(f"Its name is “{there[1]}”, this database's is “{here[1]}”.")
    return src


def restore_point_folder(db_path) -> Path:
    return layout.backups_folder(db_path) / RESTORE_POINT


def restore_point(db_path) -> Source | None:
    """Backups/Before restore as a Source (what the last restore replaced), if there is one."""
    folder = restore_point_folder(db_path)
    if not folder.is_dir():
        return None
    stem = Path(db_path).stem
    info = {}
    try:
        info = json.loads((folder / MANIFEST).read_text("utf-8"))
    except (OSError, ValueError):
        pass
    src = Source("point", "", stem=stem)
    for f in folder.rglob("*"):
        if not f.is_file() or f.name == MANIFEST or _skip_name(f.name):
            continue
        rel = f.relative_to(folder).as_posix()
        parts = tuple(rel.split("/"))
        s = f.stat()
        m = Member(rel, s.st_size, s.st_mtime, path=f)
        if len(parts) == 1:
            for part, suffix in FILE_PARTS.items():
                if f.suffix == suffix:
                    m.rel = stem + suffix
                    src.members[part] = [m]
            continue
        part = _folder_part(parts)
        if part is not None:
            src.members.setdefault(part, []).append(m)
    made = info.get("made", "")
    src.when = folder.stat().st_mtime
    src.label = "Before the last restore" + (f" ({made})" if made else "")
    return src


def size_of(folder: Path) -> int:
    total = 0
    for f in folder.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            pass
    return total


# --------------------------------------------------------------------------
# The plan: what each chosen part does
# --------------------------------------------------------------------------
@dataclass
class Item:
    part: str
    member: Member
    action: str                            # "add", "replace", "same"
    newer_here: bool = False
    source_member: Member | None = None    # read from (rel may differ: a restored copy's own name)


@dataclass
class Plan:
    source: Source
    parts: list
    main: Path                             # where it goes
    items: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)     # part -> {"add":…, "replace":…, "same":…, "newer":…}
    summary: dict = field(default_factory=dict)    # "xml": (lemmas now, lemmas after) …
    broken_now: int = 0
    broken_after: int = 0
    into_new: bool = False
    new_stem: str = ""

    def to_write(self, keep_newer: bool = False) -> list[Item]:
        return [i for i in self.items if i.action != "same" and not (keep_newer and i.newer_here)]

    def newer(self) -> int:
        return sum(1 for i in self.items if i.newer_here)


def _same(m: Member, dest: Path) -> tuple[bool, bool]:
    """(the same file, the one here newer), by size and date only. A zip's dates are local time
    with no time zone, so for a zip's file the same size and a date a whole number of hours
    away (a backup made in another time zone, or across the clocks changing) counts as the same."""
    try:
        s = dest.stat()
    except OSError:
        return False, False
    diff = s.st_mtime - m.mtime
    if s.st_size == m.size:
        if abs(diff) <= SAME_SECONDS:
            return True, False
        if m.zip_name and abs(diff) <= 14 * 3600 + SAME_SECONDS and \
                abs(diff - round(diff / 3600) * 3600) <= SAME_SECONDS:
            return True, False
    return False, diff > SAME_SECONDS


def _xml_counts(fh) -> tuple[int, int, set]:
    """(lemmas, tokens, every id) of a database file."""
    lemmas = tokens = 0
    ids = set()
    try:
        for _, el in ET.iterparse(fh, events=("end",)):
            if el.tag == "entry":
                lemmas += 1
            elif el.tag == "token":
                tokens += 1
            i = el.get("id")
            if i:
                ids.add(i)
            if el.tag in ("entry", "utterance", "text"):
                el.clear()
    except ET.ParseError:
        pass
    finally:
        fh.close()
    return lemmas, tokens, ids


def _notebook_refs(fh) -> tuple[int, set]:
    """(days, every entry and token id it links to) of a notebook file."""
    days = 0
    refs = set()
    try:
        for _, el in ET.iterparse(fh, events=("end",)):
            if el.tag == "session":
                days += 1
            for a in ("entry", "token"):
                v = el.get(a)
                if v:
                    refs.add(v)
    except ET.ParseError:
        pass
    finally:
        fh.close()
    return days, refs


def _open_here(path: Path):
    try:
        return open(path, "rb")
    except OSError:
        return None


def new_folder_for(db_path, day: _dt.date | None = None) -> Path:
    """A new folder beside the main folder for restoring into: "<main folder> restored YYYY-MM-DD"."""
    main = layout.main_folder(db_path)
    base = f"{main.name} restored {(day or _dt.date.today()).isoformat()}"
    target = main.parent / base
    n = 1
    while target.exists():
        n += 1
        target = main.parent / f"{base} ({n})"
    return target


def make_plan(db_path, source: Source, parts, into: Path | None = None) -> Plan:
    """What restoring these parts of source does. into: a new folder (the database untouched)."""
    db_path = Path(db_path)
    stem = db_path.stem
    parts = [p for p in PARTS if p in set(parts) and source.members.get(p)]
    if not parts:
        raise RestoreError("Choose at least one part the backup has.")
    main = Path(into) if into else layout.main_folder(db_path)
    plan = Plan(source, parts, main, into_new=into is not None)
    if into is not None:
        plan.new_stem = f"{stem} (restored {_dt.date.today().isoformat()})"
    seen = set()                           # one file per place (Windows and macOS ignore case)
    for part in parts:
        c = plan.counts.setdefault(part, {"add": 0, "replace": 0, "same": 0, "newer": 0})
        for m in source.members[part]:
            rel = m.rel
            key = rel.casefold().rstrip(". ")
            if key in seen:
                continue
            seen.add(key)
            if into is not None and part in FILE_PARTS:
                rel = plan.new_stem + FILE_PARTS[part]
            dest = main / rel
            if not layout.inside(dest, main) or _unsafe(rel):
                continue                   # never outside the main folder
            same, newer = _same(m, dest)
            action = "same" if same else ("replace" if dest.exists() else "add")
            item = Item(part, Member(rel, m.size, m.mtime, m.path, m.zip_name), action,
                        newer_here=newer and part in FOLDER_PARTS, source_member=m)
            plan.items.append(item)
            c[action] += 1
            c["newer"] += item.newer_here
    # the data's own counts, and links the result would leave pointing at nothing
    xml_now = _open_here(db_path)
    now = _xml_counts(xml_now) if xml_now else (0, 0, set())
    after = now
    if DATABASE in parts:
        try:
            after = _xml_counts(source.open(source.members[DATABASE][0]))
        except ZIP_ERRORS as exc:
            raise RestoreError(f"The backup's database can't be read: {exc}")
        plan.summary["lemmas"] = (now[0], after[0])
        plan.summary["tokens"] = (now[1], after[1])
    from . import notebook as nbmod
    nb_now = _open_here(nbmod.path_for(db_path))
    nb = _notebook_refs(nb_now) if nb_now else (0, set())
    nb_after = nb
    if NOTEBOOK in parts:
        try:
            nb_after = _notebook_refs(source.open(source.members[NOTEBOOK][0]))
        except ZIP_ERRORS as exc:
            raise RestoreError(f"The backup's notebook can't be read: {exc}")
        plan.summary["days"] = (nb[0], nb_after[0])
    if into is not None and DATABASE not in parts:
        after = now                        # the current database is copied in
    if into is not None and NOTEBOOK not in parts:
        nb_after = (0, set())
    plan.broken_now = len(nb[1] - now[2])
    plan.broken_after = len(nb_after[1] - after[2])
    return plan


# --------------------------------------------------------------------------
# Doing it
# --------------------------------------------------------------------------
def _write_from(fh, dest: Path, mtime: float):
    """dest from fh: under a temporary name, on the disk, swapped in; the source's date kept."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    try:
        with fh, open(tmp, "wb") as out:
            shutil.copyfileobj(fh, out, 1024 * 1024)
            out.flush()
            os.fsync(out.fileno())
        if mtime:
            os.utime(tmp, (mtime, mtime))
        os.replace(tmp, dest)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _copy_safely(src: Path, dest: Path):
    _write_from(open(src, "rb"), dest, src.stat().st_mtime)


@dataclass
class Report:
    written: int = 0
    added: list = field(default_factory=list)
    replaced: list = field(default_factory=list)
    kept_newer: int = 0
    failed: str = ""
    point: Path | None = None


def apply(plan: Plan, keep_newer: bool = False, discard=None, db_path=None, progress=None) -> Report:
    """Restore. In place: every file replaced is first copied into a new restore point, which
    becomes Backups/Before restore once everything is written; the old one is then discarded
    (discard(path) for each file, e.g. to the Recycle Bin; removed if none). Into a new folder: the
    chosen parts there, the current database's XML too if the XML wasn't chosen.
    progress(done, total, name) may raise to stop. A failure stops at once: Report.failed says
    why, and the restore point so far is kept as "Before restore (interrupted …)"."""
    rep = Report()
    items = plan.to_write(keep_newer)
    rep.kept_newer = plan.newer() if keep_newer else 0
    src = plan.source
    if plan.into_new:
        plan.main.mkdir(parents=True, exist_ok=False)
        for sub in (layout.SOUNDFILES, layout.BACKUPS, layout.DOCUMENTATION, layout.EXPORTS):
            (plan.main / sub).mkdir(exist_ok=True)
        try:
            for n, it in enumerate(items):
                if progress:
                    progress(n, len(items), it.member.rel)
                _write_from(src.open(it.source_member), plan.main / it.member.rel, it.member.mtime)
                rep.added.append(it.member.rel)
                rep.written += 1
            if DATABASE not in plan.parts and db_path:
                _copy_safely(Path(db_path), plan.main / (plan.new_stem + ".xml"))
                rep.written += 1
        except Exception as exc:
            rep.failed = str(exc)
        return rep
    backups = layout.backups_folder(db_path or (plan.main / "x.xml"))
    backups.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now()
    work = backups / (RESTORE_POINT + ".new")
    if work.exists():                      # left by an interrupted restore: kept, never deleted
        work.rename(_free(backups / f"{RESTORE_POINT} (interrupted {_dt.datetime.fromtimestamp(work.stat().st_mtime):%Y-%m-%d %H%M%S})"))
    work.mkdir()
    manifest = {"made": f"{stamp.day} {stamp:%B %Y, %H:%M}", "source": src.label, "parts": plan.parts,
                "replaced": rep.replaced, "added": rep.added}
    try:
        for n, it in enumerate(items):
            if progress:
                progress(n, len(items), it.member.rel)
            dest = plan.main / it.member.rel
            existed = dest.exists()        # now, not when the plan was made
            if existed and not (work / it.member.rel).exists():
                _copy_safely(dest, work / it.member.rel)
            _write_from(src.open(it.source_member), dest, it.member.mtime)
            (rep.replaced if existed else rep.added).append(it.member.rel)
            rep.written += 1
    except Exception as exc:
        rep.failed = str(exc)
    try:
        (work / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=1), "utf-8")
    except OSError as exc:
        rep.failed = rep.failed or f"the restore point's note couldn't be written: {exc}"
    if rep.failed:
        rep.point = _free(backups / f"{RESTORE_POINT} (interrupted {stamp:%Y-%m-%d %H%M%S})")
        work.rename(rep.point)
        return rep
    old = backups / RESTORE_POINT
    if old.exists():
        _discard_tree(old, discard)
    if old.exists():                       # couldn't be cleared: kept under another name
        old.rename(_free(backups / f"{RESTORE_POINT} (older)"))
    work.rename(old)
    rep.point = old
    return rep


def _free(path: Path) -> Path:
    out, n = path, 1
    while out.exists():
        n += 1
        out = path.with_name(f"{path.name} ({n})")
    return out


def _discard_tree(folder: Path, discard=None):
    """The old restore point goes: each file through discard(path) -> bool (the Recycle Bin),
    or removed when there is none; folders emptied that way are removed."""
    for f in sorted(folder.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        try:
            if f.is_file():
                if discard is None:
                    f.unlink()
                else:
                    discard(f)
            else:
                f.rmdir()
        except OSError:
            pass
    try:
        folder.rmdir()
    except OSError:
        pass


def note_line(plan: Plan) -> str:
    """The line written in today's notes, under =====RESTORE HISTORY=====."""
    what = ", ".join("Database" if p == DATABASE else LABELS[p].split(" (")[0] for p in plan.parts)
    src = plan.source
    if src.kind == "autosave":
        where = "the a" + src.label[1:]
    elif src.kind == "full":
        where = "the full backup " + (src.zip_path.name if src.zip_path else "")
    else:
        where = "before the last restore"
    into = " (into a new folder)" if plan.into_new else ""
    return f"Restored from {where}{into}: {what}"
