# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""The two archives: copies of the data to share or deposit (IDEAS.md idea 44, 22 October 2026).

Lemmatrix keeps two kinds of thing apart. The **database** is the archivable data: what was
collected and what describes it (lemmas, tokens, utterances, texts, fields, tags, lists such as
the tone classes, metadata). The **notebook** (notes, questions, To Dos, Cogitate's hypotheses),
the **workspace** and, later, Analyze's and Compose's results are the researcher's own work in
progress: they go into every Full backup, but they are not for public sharing. Others can look at
the archived data and come to their own conclusions; they don't get the researcher's unpublished
thoughts. So both archives leave the notebook out by default and always write a blank workspace.

* **Anonymous archive** (``ANONYMOUS``): nobody is named. People's codes are renumbered (SP1,
  SP2… and RS1, RS2… in list order) wherever a code is (speakers, texts, the notebook, TextGrid
  tier names, file names, free text); names, descriptions, emails and consent links all go; the
  language's and variety's names become their codes, and the codes themselves can be hidden too
  (LXX, VXX). No recordings (a voice undoes the anonymising); TextGrids go in (they are text),
  their tier names renumbered. Places: the top level by default. The one to use for letting
  others see your setup, e.g. when feeding the data to AI for help or analysis. The key (old
  code → new code) only ever goes inside the password-protected zip with the consent forms.
* **Ethical archive** (``ETHICAL``): the people who agreed to be identified stay named. A
  participant ticked Identifiable? keeps name and description; a researcher ticked Identifiable?
  keeps name, description and email; everyone else is reduced to their code. Codes stay as
  they are. Only the recordings of speakers who ticked Audio sharing? go in. For sharing the raw
  data and the basic analysis that describes it (the tone classes, the tags) with an archive or
  a colleague.

Free text can hold other things that identify people (a name not on the list, a village), so
the report lists every replacement for checking, and says so.
"""

from __future__ import annotations

import copy
import csv
import io
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import layout, notebook as nbmod, storage
from .model import Database, Location

ANONYMOUS, ETHICAL = "anonymous", "ethical"
TITLES = {ANONYMOUS: "Anonymous archive", ETHICAL: "Ethical archive"}
SUFFIX = {ANONYMOUS: " (anonymous)", ETHICAL: " (ethical)"}
ANON = SUFFIX[ANONYMOUS]                  # the older name
HIDDEN_LANGUAGE, HIDDEN_VARIETY = "LXX", "VXX"
AI_NOTE = ("This completely anonymised archive is the one to use when you feed your data to AI for help "
           "or analysis: nobody is named in it, and codes are renumbered.")
PRIVATE_NOTE = ("The notebook holds your own work: notes, questions, To Dos and your Cogitate hypotheses "
                "with their evidence. It goes into every Full backup, but it isn't archive data: others can "
                "look at the data and come to their own conclusions, without your unpublished thoughts.")

# fields whose text is a transcription, never searched for names
_TRANSCRIPTION_ROLES = ("lemma", "phonetic", "phonemic", "morphemes", "pitch")


@dataclass
class Options:
    kind: str = ETHICAL
    notebook: bool = False             # include the notebook (the researcher's own work: off by default)
    replace_names: bool = True         # names (and, anonymous, old codes) in free text -> codes
    recordings: bool = True            # ethical only: the recordings of speakers who ticked Audio sharing?
    place_levels: int = 0              # 0: keep every place; n: keep the top n levels only
    consent_password: str = ""         # "": consent forms left out; else a password-protected zip
    hide_language_code: bool = False   # anonymous only: the language code becomes LXX
    hide_variety_code: bool = False    # anonymous only: the variety code becomes VXX

    @classmethod
    def for_kind(cls, kind: str) -> "Options":
        """The defaults agreed for each archive (Josh, 22 October)."""
        if kind == ANONYMOUS:
            return cls(kind=ANONYMOUS, notebook=False, recordings=False, place_levels=1)
        return cls(kind=ETHICAL, notebook=False, recordings=True, place_levels=0)

    @property
    def anonymous(self) -> bool:
        return self.kind == ANONYMOUS

    @property
    def with_recordings(self) -> bool:
        return self.recordings and not self.anonymous


@dataclass
class Report:
    kind: str = ETHICAL
    folder: Path | None = None
    files: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)       # "where: “text” → code"
    renumbered: dict[str, str] = field(default_factory=dict)  # old code -> new (never written in the clear)
    roles: dict[str, str] = field(default_factory=dict)       # old code -> "participant" / "researcher"
    hidden_people: list[str] = field(default_factory=list)    # codes of people reduced to their code
    named_people: list[str] = field(default_factory=list)     # codes of people left named (ethical)
    recordings: int = 0
    missing_recordings: int = 0
    withheld_recordings: int = 0                              # no Audio sharing? (ethical)
    textgrids: int = 0
    unreadable_textgrids: list[str] = field(default_factory=list)
    consent_files: int = 0
    missing_consent: list[str] = field(default_factory=list)
    places_removed: int = 0
    key_written: bool = False
    notebook: bool = False
    scrubber: "Scrubber | None" = field(default=None, repr=False, compare=False)


def zip_available() -> bool:
    try:
        import pyzipper  # noqa: F401
    except ImportError:
        return False
    return True


# --------------------------------------------------------------------------
# What to replace in free text
# --------------------------------------------------------------------------

class Scrubber:
    """Replaces people's names (and, in the anonymous archive, old codes and the language's and
    variety's names) in free text, in one pass, so a replacement is never replaced again."""

    def __init__(self):
        self.exact: dict[str, str] = {}       # matched as written
        self.folded: dict[str, str] = {}      # matched in any case (full names)
        self.rx: re.Pattern | None = None

    def add_name(self, name: str, code: str):
        """A person's full name (any case), then each part of it (3 letters or more, capitalised,
        as written), so "Sample Speaker" goes before "Sample"."""
        name = (name or "").strip()
        if not name or not code or name.lower() in ("redacted", code.lower()):
            return
        self.folded.setdefault(name.lower(), code)
        for part in re.split(r"[\s.,]+", name):
            if len(part) >= 3 and part[:1].isupper():
                self.exact.setdefault(part, code)

    def add_word(self, word: str, code: str, any_case: bool = False):
        if word and code and word != code:
            (self.folded if any_case else self.exact).setdefault(word.lower() if any_case else word, code)

    def compile(self):
        words = sorted(set(self.exact) | set(self.folded), key=len, reverse=True)
        if not words:
            self.rx = None
            return
        alts = [("(?i:" + re.escape(w) + ")") if w in self.folded and w not in self.exact else re.escape(w)
                for w in words]
        self.rx = re.compile(r"(?<!\w)(?:" + "|".join(alts) + r")(?!\w)")

    def __bool__(self):
        return self.rx is not None

    def text(self, text: str, where: str, report: Report | None) -> str:
        if not text or self.rx is None:
            return text

        def sub(m):
            t = m.group()
            code = self.exact.get(t) or self.folded.get(t.lower()) or t
            if report is not None and code != t:
                report.replaced.append(f"{where}: “{t}” → {code}")
            return code
        return self.rx.sub(sub, text)

    def filename(self, name: str) -> str:
        """The same in a file name, whose words are joined by underscores as Praat writes them."""
        if not name or self.rx is None:
            return name
        return self.text(name.replace("_", " "), "", None).replace(" ", "_")


def name_patterns(people) -> list[tuple[re.Pattern, str]]:
    """(pattern, code) for each person's full name, then each part of it: kept for older callers."""
    out = []
    for p in people:
        s = Scrubber()
        s.add_name(p.name, p.code)
        s.compile()
        if s:
            out.append((s.rx, p.code))
    return out


def replace_names(text: str, patterns, where: str, report: Report) -> str:
    """Older callers' replacement, one person at a time."""
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
# Renumbering (the anonymous archive)
# --------------------------------------------------------------------------

def code_map(db: Database, nb: nbmod.Notebook | None) -> tuple[dict[str, str], dict[str, str]]:
    """(old code -> new code, old code -> role): participants SP1, SP2… then researchers RS1,
    RS2…, in the lists' order; codes used but not listed (a token's speaker, a session's
    person) follow, by kind, in the order they are first met."""
    md = db.metadata
    mapping: dict[str, str] = {}
    roles: dict[str, str] = {}
    count = {"participant": 0, "researcher": 0}
    prefix = {"participant": "SP", "researcher": "RS"}

    def add(code: str, role: str):
        if code and code not in mapping:
            count[role] += 1
            mapping[code] = f"{prefix[role]}{count[role]}"
            roles[code] = role
    for p in md.participants:
        add(p.code, "participant")
    for p in md.researchers:
        add(p.code, "researcher")
    for e in db.items():
        for t in e.tokens:
            add(t.speaker, "participant")
    for t in db.texts:
        for c in t.participants:
            add(c, "participant")
        for c in t.researchers:
            add(c, "researcher")
    if nb is not None:
        for s in nb.sessions:
            for c in s.participants:
                add(c, "participant")
            for c in s.researchers:
                add(c, "researcher")
    return mapping, roles


def _scrubber(db: Database, opts: Options, renumbered: dict[str, str], lang_code: str, var_code: str) -> Scrubber:
    """What the archive replaces in free text, file names and TextGrids. Anonymous: every
    person's name and every old code (codes always, names when replace_names), and the
    language's and variety's names; ethical: the names of the people not ticked Identifiable?."""
    s = Scrubber()
    md = db.metadata
    if opts.anonymous:
        if opts.replace_names:
            for p in md.participants + md.researchers:
                s.add_name(p.name, renumbered.get(p.code, p.code))
            for name, code in ((md.language_name, lang_code), (md.variety_name, var_code)):
                if name and code:
                    s.add_word(name, code, any_case=True)
        for old, new in renumbered.items():
            s.add_word(old, new)
    elif opts.replace_names:
        for p in md.participants + md.researchers:
            if not p.identifiable:
                s.add_name(p.name, p.code)
    s.compile()
    return s


# --------------------------------------------------------------------------
# The copy
# --------------------------------------------------------------------------

def _open_fields(fields) -> list:
    return [f for f in fields if not f.closed and f.role not in _TRANSCRIPTION_ROLES]


def _scrub_values(obj, fields, scrub: Scrubber, where: str, report: Report):
    for f in fields:
        if f.name in obj.values and obj.values[f.name]:
            obj.values[f.name] = scrub.text(obj.values[f.name], f"{where} {f.title}", report)
        for lang, v in list(obj.multi.get(f.name, {}).items()):
            if v:
                obj.multi[f.name][lang] = scrub.text(v, f"{where} {f.title}" + (f" ({lang})" if lang else ""),
                                                     report)


def anonymise(db: Database, nb: nbmod.Notebook | None, opts: Options, report: Report):
    """Archive copies of the database and notebook (the originals are untouched)."""
    report.kind = opts.kind
    out = copy.deepcopy(db)
    book = copy.deepcopy(nb) if (nb is not None and opts.notebook) else None
    report.notebook = book is not None
    md = out.metadata
    mapping: dict[str, str] = {}
    if opts.anonymous:
        mapping, roles = code_map(db, nb if opts.notebook else None)
        report.renumbered, report.roles = dict(mapping), roles
        lang_code = md.language_code or (HIDDEN_LANGUAGE if md.language_name else "")
        var_code = md.variety_code or (HIDDEN_VARIETY if md.variety_name else "")
        if opts.hide_language_code and lang_code:
            lang_code = HIDDEN_LANGUAGE
        if opts.hide_variety_code and var_code:
            var_code = HIDDEN_VARIETY
        for old, new, role in ((md.language_code, lang_code, "language"), (md.variety_code, var_code, "variety")):
            if old and new != old:
                report.renumbered[old] = new
                report.roles[old] = role
        scrub = _scrubber(db, opts, report.renumbered, lang_code, var_code)
        md.language_name, md.language_code = lang_code, lang_code
        md.variety_name, md.variety_code = var_code, var_code
        author = (md.author or "").strip()
        owner = next((p for p in db.metadata.researchers if author and author in (p.name, p.code)), None)
        md.author = mapping.get(owner.code, owner.code) if owner else ("Anonymous" if author else "")
        for p in md.participants + md.researchers:
            report.hidden_people.append(p.code)
            p.code = mapping.get(p.code, p.code)
            p.name, p.description, p.consent, p.email = "", "", "", ""
    else:
        scrub = _scrubber(db, opts, {}, "", "")
        for p in md.participants + md.researchers:
            if p.identifiable:
                report.named_people.append(p.code)
            else:
                report.hidden_people.append(p.code)
                p.name, p.description, p.email = "", "", ""
        for p in md.participants:                 # consent forms travel only in the zip
            p.consent, p.email = "", ""
        owner = next((p for p in db.metadata.researchers if md.author and md.author in (p.name, p.code)), None)
        if owner is not None and not owner.identifiable:
            md.author = owner.code
    report.scrubber = scrub
    moved = _trim_places(md.locations, opts.place_levels, report) if opts.place_levels else {}

    def code(c: str) -> str:
        return mapping.get(c, c)

    efields = _open_fields(out.settings.entry_fields)
    tfields = _open_fields(out.settings.token_fields)
    xfields = _open_fields(out.settings.text_fields)
    for e in out.items():                         # lemmas and utterances
        _scrub_values(e, efields, scrub, e.ref, report)
        e.file_gloss = scrub.text(e.file_gloss, "", None)
        src = getattr(e, "source", None)          # a clipped utterance's copy of its line's tiers
        if src is not None:
            src.copied = {scrub.text(k, "", None): scrub.text(v, f"{e.ref} source", report)
                          for k, v in src.copied.items()}
        for t in e.tokens:
            t.speaker = code(t.speaker)
            _scrub_values(t, tfields, scrub, f"{e.ref} token", report)
            t.file = scrub.filename(t.file)
    for t in out.texts:
        t.participants = [code(c) for c in t.participants]
        t.researchers = [code(c) for c in t.researchers]
        if moved:
            t.locations = list(dict.fromkeys(moved.get(k, k) for k in t.locations))
        _scrub_values(t, xfields, scrub, t.ref, report)
        t.file_label = scrub.text(t.file_label, "", None)
        t.file, t.textgrid = scrub.filename(t.file), scrub.filename(t.textgrid)
    for g in out.settings.tags.all_groups():      # tag and group descriptions are free text too
        g.description = scrub.text(g.description, f"Tag group {g.name}", report)
        for tag in g.tags:
            tag.description = scrub.text(tag.description, f"Tag {tag.name}", report)
    md.description = scrub.text(md.description, "Metadata description", report)
    md.name = scrub.text(md.name, "Database name", report)
    for _, loc in md.all_locations():
        loc.description = scrub.text(loc.description, f"Place {loc.name}", report)

    if book is not None:
        for s in book.sessions:
            s.researchers = [code(c) for c in s.researchers]
            s.participants = [code(c) for c in s.participants]
            if moved:
                s.locations = list(dict.fromkeys(moved.get(k, k) for k in s.locations))
            s.notes = scrub.text(s.notes, f"Notebook {s.date} notes", report)
            for q in s.questions + s.todos:
                q.text = scrub.text(q.text, f"Notebook {s.date} {'To Do' if q.is_todo else 'question'}", report)
                q.about = scrub.text(q.about, "", None)
            for c in s.comments:
                c.text = scrub.text(c.text, f"Notebook {s.date} comment", report)
                c.about = scrub.text(c.about, "", None)
        for h in book.hypotheses:                 # hypotheses (Cogitate) are notes too
            where = f"Hypothesis {h.label}"
            h.summary = scrub.text(h.summary, f"{where} summary", report)
            h.formulation = scrub.text(h.formulation, f"{where} formulation", report)
            for ln in h.links:
                ln.note = scrub.text(ln.note, f"{where} link note", report)
                ln.text = scrub.text(ln.text, f"{where} link", report)
                ln.about = scrub.text(ln.about, "", None)
    return out, book


def _consent_files(db: Database) -> list[tuple[str, Path]]:
    """(participant code, file) for every consent file or folder set, as full paths."""
    out = []
    for p in db.metadata.participants:
        if not p.consent:
            continue
        out.append((p.code, layout.consent_full_path(db, p.consent)))
    return out


def _shared(db: Database, speaker: str) -> bool:
    """Whether a recording by this speaker may go into the ethical archive (Audio sharing?)."""
    p = db.metadata.participant(speaker) if speaker else None
    return bool(p and p.audio_sharing)


def _copy_textgrid(src: Path, dst: Path, scrub: Scrubber) -> bool:
    """A TextGrid with its tier names and text put through the scrubber (renumbered codes in
    tx@SP1, names replaced). False if it couldn't be read (it is then left out, not copied as is)."""
    if not scrub:
        shutil.copy2(src, dst)
        return True
    from . import textgrid as tgmod
    try:
        from praatio import textgrid
        tg = tgmod.read_grid(src)
        new = textgrid.Textgrid(tg.minTimestamp, tg.maxTimestamp)
        for tier in tg.tiers:
            entries = [e._replace(label=scrub.text(e.label, "", None)) for e in tier.entries]
            new.addTier(tier.new(name=scrub.text(tier.name, "", None), entries=entries))
        new.save(str(dst), format="long_textgrid", includeBlankSpaces=True)
        return True
    except Exception:                          # praatio raises several kinds
        return False


def export(db: Database, nb: nbmod.Notebook | None, folder: str | Path, opts: Options) -> Report:
    """Write the archive into folder (made if needed). Returns what was done."""
    report = Report(kind=opts.kind, folder=Path(folder))
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    out, book = anonymise(db, nb, opts, report)
    scrub = report.scrubber                     # the same replacements, for file names and TextGrids
    stem = Path(db.path).stem if db.path else "Database"
    out_stem = scrub.filename(stem) if opts.anonymous else stem
    target = folder / f"{out_stem}{SUFFIX[opts.kind]}.xml"

    if opts.with_recordings:
        # the fixed layout there too: tokens' recordings in Tokens, utterances' in Utterances;
        # only those whose speaker agreed to audio sharing
        for items, copies, src_folder, sub in ((db.entries, out.entries, storage.sound_folder(db), layout.TOKENS),
                                               (db.utterances, out.utterances, storage.utterance_folder(db),
                                                layout.UTTERANCES)):
            names: dict[str, str] = {}
            for e, ce in zip(items, copies):
                for t, ct in zip(e.tokens, ce.tokens):
                    if not t.file:
                        continue
                    if _shared(db, t.speaker):
                        names[t.file] = ct.file
                    else:
                        report.withheld_recordings += 1
            if not names:
                continue
            dst_folder = folder / layout.SOUNDFILES / sub
            dst_folder.mkdir(parents=True, exist_ok=True)
            for name, new in sorted(names.items()):
                src = src_folder / name
                if src.exists():
                    shutil.copy2(src, dst_folder / new)
                    report.recordings += 1
                else:
                    report.missing_recordings += 1
    # texts: TextGrids always (text, not voices), their recordings only in the ethical archive
    # and only when every participant of the text agreed to audio sharing
    for t, ct in zip(db.texts, out.texts):
        for name, new, is_grid in ((t.file, ct.file, False), (t.textgrid, ct.textgrid, True)):
            if not name:
                continue
            if not is_grid:
                if not opts.with_recordings:
                    continue
                if not t.participants or not all(_shared(db, c) for c in t.participants):
                    report.withheld_recordings += 1
                    continue
            src = storage.text_folder(db) / name
            if not src.exists():
                report.missing_recordings += 1
                continue
            dst_folder = folder / layout.SOUNDFILES / layout.TEXTS
            dst_folder.mkdir(parents=True, exist_ok=True)
            if is_grid:
                if _copy_textgrid(src, dst_folder / new, scrub):
                    report.textgrids += 1
                else:
                    report.unreadable_textgrids.append(name)
            else:
                shutil.copy2(src, dst_folder / new)
                report.recordings += 1

    out.path = str(target)
    storage.save(out, target, backup=False)
    report.files.append(target.name)
    from . import workspace as wsmod                # a blank one: no working state goes with the data
    wsmod.save_blank(wsmod.path_for(target))
    if book is not None and book.sessions + book.hypotheses:
        nb_path = nbmod.path_for(target)
        nbmod.save(book, nb_path, target.name)
        report.files.append(nb_path.name)

    if opts.consent_password:
        import pyzipper
        zpath = folder / f"{out_stem} consent forms (password).zip"
        with pyzipper.AESZipFile(zpath, "w", compression=pyzipper.ZIP_DEFLATED,
                                 encryption=pyzipper.WZ_AES) as zf:
            zf.setpassword(opts.consent_password.encode("utf-8"))
            for code, path in _consent_files(db):
                files = [path] if path.is_file() else sorted(x for x in path.rglob("*") if x.is_file()) \
                    if path.is_dir() else []
                if not files:
                    report.missing_consent.append(code)
                inner = report.renumbered.get(code, code) if opts.anonymous else code
                for f in files:
                    inside = f"{inner}/{f.relative_to(path) if path.is_dir() else f.name}"
                    zf.write(f, inside)
                    report.consent_files += 1
            if opts.anonymous and report.renumbered:   # the key: only ever here, never in the clear
                buf = io.StringIO()
                w = csv.writer(buf)
                w.writerow(["kind", "old code", "new code"])
                for old, new in report.renumbered.items():
                    w.writerow([report.roles.get(old, ""), old, new])
                zf.writestr("Code key.csv", "﻿" + buf.getvalue())
                report.key_written = True
        report.files.append(zpath.name)
    return report


def summary(report: Report, opts: Options) -> str:
    """What the export wrote and changed, for the message at the end."""
    lines = [f"{TITLES[opts.kind]} written to {report.folder}:", *(f"  • {f}" for f in report.files)]
    if opts.anonymous:
        people = sum(1 for r in report.roles.values() if r in ("participant", "researcher"))
        lines.append(f"Nobody is named: {people} people's codes were renumbered (SP1…, RS1…), and every name, "
                     "description, email and consent link was taken out.")
        hidden = [r for r in report.roles.values() if r in ("language", "variety")]
        if hidden:
            lines.append(f"The {' and '.join(hidden)} code{'s were' if len(hidden) > 1 else ' was'} hidden too "
                         f"({', '.join(v for k, v in report.renumbered.items() if report.roles.get(k) in hidden)}).")
        lines.append("The key (old code → new code) is in the password-protected zip." if report.key_written
                     else "No key was kept: the renumbering can't be undone from the archive.")
        lines.append("No recordings went in (a voice undoes the anonymising)."
                     + (f" {report.textgrids} TextGrid(s) went in, with their tier names renumbered."
                        if report.textgrids else ""))
    else:
        lines.append(f"{len(report.named_people)} identifiable people kept their names; "
                     f"{len(report.hidden_people)} others are their codes only.")
        if opts.with_recordings:
            lines.append(f"{report.recordings} recording(s) copied"
                         + (f"; {report.withheld_recordings} left out (no Audio sharing? agreement)"
                            if report.withheld_recordings else "")
                         + (f"; {report.missing_recordings} weren't in the soundfiles folders" if
                            report.missing_recordings else "") + ".")
        if report.textgrids:
            lines.append(f"{report.textgrids} TextGrid(s) copied.")
    if report.unreadable_textgrids:
        lines.append(f"Left out, unreadable: {', '.join(report.unreadable_textgrids)}.")
    if opts.place_levels:
        lines.append(f"{report.places_removed} place(s) below level {opts.place_levels} were left out.")
    if opts.consent_password:
        lines.append(f"{report.consent_files} consent file(s) are in the password-protected zip"
                     + (f"; none found for {', '.join(report.missing_consent)}." if report.missing_consent else "."))
    lines.append("The notebook went in, at your choice." if report.notebook else
                 "The notebook (your notes, questions and hypotheses) stayed out: it is your own work, "
                 "kept in your Full backups.")
    if report.replaced:
        lines.append(f"\nReplaced in free text ({len(report.replaced)}):")
        lines += [f"  • {r}" for r in report.replaced[:25]]
        if len(report.replaced) > 25:
            lines.append(f"  … and {len(report.replaced) - 25} more")
    lines.append("\nComments, translations and TextGrids can still hold things that identify people (a name "
                 "that isn't on the lists, a village). Read them through before sharing.")
    return "\n".join(lines)
