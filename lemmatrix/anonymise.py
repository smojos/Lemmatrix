# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Export an anonymous backup: a copy of the database (and notebook) safe to share or deposit.

What always goes: the participants' names, descriptions and consent links (their codes
stay, since tokens, sessions and file names use them). What can also go, or be changed:
the researchers' names (and the owner's), the notebook, the participants' names written
in free text (replaced by their codes), the recordings (copied, or not), places below a
chosen level, and the consent forms (left out, or put in a password-protected zip).

Free text can hold other things that identify people (a name not on the list, a place),
so the report lists every replacement for checking, and says so.
"""

from __future__ import annotations

import copy
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import layout, notebook as nbmod, storage
from .model import Database, Location

ANON = " (anonymous)"


@dataclass
class Options:
    researchers: bool = False          # take out the researchers' names (and the owner's) too
    notebook: bool = True              # include the notebook
    replace_names: bool = True         # participants' names in free text -> their codes
    recordings: bool = False           # copy the recordings the tokens use
    place_levels: int = 0              # 0: keep every place; n: keep the top n levels only
    consent_password: str = ""         # "": consent forms left out; else a password-protected zip


@dataclass
class Report:
    folder: Path | None = None
    files: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)       # "where: name → code"
    recordings: int = 0
    missing_recordings: int = 0
    consent_files: int = 0
    missing_consent: list[str] = field(default_factory=list)
    places_removed: int = 0


def zip_available() -> bool:
    try:
        import pyzipper  # noqa: F401
    except ImportError:
        return False
    return True


# --------------------------------------------------------------------------
# Names in free text
# --------------------------------------------------------------------------

def name_patterns(people) -> list[tuple[re.Pattern, str]]:
    """(pattern, code) for each person's full name, then each part of it (3 letters or more,
    capitalised, as a whole word), longest first so "Sample Speaker" goes before "Sample"."""
    found: dict[str, str] = {}
    for p in people:
        name = (p.name or "").strip()
        if not name or not p.code or name.lower() in ("redacted", p.code.lower()):
            continue
        found.setdefault(name, p.code)
        for part in re.split(r"[\s.,]+", name):
            if len(part) >= 3 and part[:1].isupper():
                found.setdefault(part, p.code)
    out = []
    for text in sorted(found, key=len, reverse=True):
        flags = re.IGNORECASE if " " in text else 0           # a full name in any case; parts as written
        out.append((re.compile(r"(?<!\w)" + re.escape(text) + r"(?!\w)", flags), found[text]))
    return out


def replace_names(text: str, patterns, where: str, report: Report) -> str:
    if not text:
        return text
    for rx, code in patterns:
        def sub(m, code=code):
            report.replaced.append(f"{where}: “{m.group()}” → {code}")
            return code
        text = rx.sub(sub, text)
    return text


# --------------------------------------------------------------------------
# Places
# --------------------------------------------------------------------------

def _trim_places(places: list[Location], levels: int, report: Report) -> dict[str, str]:
    """Cut the place list below `levels`; returns key of each removed place -> its kept ancestor's."""
    moved: dict[str, str] = {}

    def trim(loc: Location, depth: int):
        if depth >= levels:
            for _, sub in loc.walk():
                if sub is not loc:
                    moved[sub.key] = loc.key
                    report.places_removed += 1
            loc.children = []
            return
        for c in loc.children:
            trim(c, depth + 1)
    for top in places:
        trim(top, 1)
    return moved


# --------------------------------------------------------------------------
# The copy
# --------------------------------------------------------------------------

def anonymise(db: Database, nb: nbmod.Notebook | None, opts: Options, report: Report):
    """Anonymous copies of the database and notebook (the originals are untouched)."""
    out = copy.deepcopy(db)
    book = copy.deepcopy(nb) if (nb is not None and opts.notebook) else None
    md = out.metadata
    people = list(md.participants) + (list(md.researchers) if opts.researchers else [])
    patterns = name_patterns(people) if opts.replace_names else []
    for p in md.participants:
        p.name, p.description, p.consent = "", "", ""
    if opts.researchers:
        for p in md.researchers:
            p.name, p.description = "", ""
        md.author = ""
    moved = _trim_places(md.locations, opts.place_levels, report) if opts.place_levels else {}

    if patterns:
        efields, tfields = out.comment_fields()
        for e in out.items():                     # lemmas and utterances
            for name in efields:
                v = e.get(name)
                if v:
                    e.set(name, replace_names(v, patterns, f"{e.ref} {name}", report))
            for t in e.tokens:
                for name in tfields:
                    v = t.get(name)
                    if v:
                        t.set(name, replace_names(v, patterns, f"{e.ref} token {name}", report))
        for t in out.texts:                       # texts' own free text
            for f in out.settings.text_fields:
                v = t.get(f.name)
                if v and not f.closed:
                    t.set(f.name, replace_names(v, patterns, f"{t.ref} {f.name}", report))
        md.description = replace_names(md.description, patterns, "Metadata description", report)
    if book is not None:
        for s in book.sessions:
            if moved:
                s.locations = list(dict.fromkeys(moved.get(k, k) for k in s.locations))
            if patterns:
                s.notes = replace_names(s.notes, patterns, f"Notebook {s.date} notes", report)
                for q in s.questions:
                    q.text = replace_names(q.text, patterns, f"Notebook {s.date} question", report)
                for c in s.comments:
                    c.text = replace_names(c.text, patterns, f"Notebook {s.date} comment", report)
    return out, book


def _consent_files(db: Database) -> list[tuple[str, Path]]:
    """(participant code, file) for every consent file or folder set, as full paths."""
    out = []
    for p in db.metadata.participants:
        if not p.consent:
            continue
        out.append((p.code, layout.consent_full_path(db, p.consent)))
    return out


def export(db: Database, nb: nbmod.Notebook | None, folder: str | Path, opts: Options) -> Report:
    """Write the anonymous backup into folder (made if needed). Returns what was done."""
    report = Report(folder=Path(folder))
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stem = Path(db.path).stem if db.path else "Database"
    out, book = anonymise(db, nb, opts, report)
    target = folder / f"{stem}{ANON}.xml"

    if opts.recordings:
        # the fixed layout there too: tokens' recordings in Tokens, utterances' in Utterances
        for items, src_folder, sub in ((db.entries, storage.sound_folder(db), layout.TOKENS),
                                       (db.utterances, storage.utterance_folder(db), layout.UTTERANCES)):
            names = sorted({t.file for e in items for t in e.tokens if t.file})
            if not names:
                continue
            dst_folder = folder / layout.SOUNDFILES / sub
            dst_folder.mkdir(parents=True, exist_ok=True)
            for name in names:
                src = src_folder / name
                if src.exists():
                    shutil.copy2(src, dst_folder / name)
                    report.recordings += 1
                else:
                    report.missing_recordings += 1
        names = sorted({n for t in db.texts for n in (t.file, t.textgrid) if n})
        if names:                                 # texts' recordings and TextGrids, in Soundfiles/Texts
            dst_folder = folder / layout.SOUNDFILES / layout.TEXTS
            dst_folder.mkdir(parents=True, exist_ok=True)
            for name in names:
                src = storage.text_folder(db) / name
                if src.exists():
                    shutil.copy2(src, dst_folder / name)
                    report.recordings += name.lower().endswith(".wav")
                else:
                    report.missing_recordings += 1

    out.path = str(target)
    storage.save(out, target, backup=False)
    report.files.append(target.name)
    if book is not None and book.sessions:
        nb_path = nbmod.path_for(target)
        nbmod.save(book, nb_path, target.name)
        report.files.append(nb_path.name)

    if opts.consent_password:
        import pyzipper
        zpath = folder / f"{stem} consent forms (password).zip"
        with pyzipper.AESZipFile(zpath, "w", compression=pyzipper.ZIP_DEFLATED,
                                 encryption=pyzipper.WZ_AES) as zf:
            zf.setpassword(opts.consent_password.encode("utf-8"))
            for code, path in _consent_files(db):
                files = [path] if path.is_file() else sorted(x for x in path.rglob("*") if x.is_file()) \
                    if path.is_dir() else []
                if not files:
                    report.missing_consent.append(code)
                for f in files:
                    inside = f"{code}/{f.relative_to(path) if path.is_dir() else f.name}"
                    zf.write(f, inside)
                    report.consent_files += 1
        report.files.append(zpath.name)
    return report


def summary(report: Report, opts: Options) -> str:
    """What the export wrote and changed, for the message at the end."""
    lines = [f"Written to {report.folder}:", *(f"  • {f}" for f in report.files)]
    lines.append("Participants' names, descriptions and consent links were taken out (their codes stay).")
    if opts.researchers:
        lines.append("Researchers' names and the owner's name were taken out too.")
    if opts.recordings:
        lines.append(f"{report.recordings} recording(s) copied"
                     + (f"; {report.missing_recordings} weren't in the sound folder." if report.missing_recordings
                        else "."))
    if opts.place_levels:
        lines.append(f"{report.places_removed} place(s) below level {opts.place_levels} were left out.")
    if opts.consent_password:
        lines.append(f"{report.consent_files} consent file(s) are in the password-protected zip"
                     + (f"; none found for {', '.join(report.missing_consent)}." if report.missing_consent else "."))
    if report.replaced:
        lines.append(f"\nNames replaced in free text ({len(report.replaced)}):")
        lines += [f"  • {r}" for r in report.replaced[:25]]
        if len(report.replaced) > 25:
            lines.append(f"  … and {len(report.replaced) - 25} more")
    lines.append("\nComments and notes can still hold things that identify people (a name that isn't on "
                 "the participant list, a village). Read them through before sharing.")
    return "\n".join(lines)
