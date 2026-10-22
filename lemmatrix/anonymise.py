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

Names are replaced everywhere text is kept that isn't a transcription: every field's values
(open or closed, and values of fields since deleted), closed fields' lists, tag and category
names' descriptions, the metadata, file names and labels, TextGrids (except their
transcription tiers), clipped utterances' copies, the tier mapping, and the notebook when it
goes in. Free text can still hold other things that identify people (a name not on the list, a
village), so the report lists every replacement for checking, and says so.
"""

from __future__ import annotations

import copy
import csv
import io
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from . import layout, notebook as nbmod, storage
from .model import Database, Location, tier_base

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

# fields whose text is a transcription, never searched for names (nor the word class: a list
# of grammatical labels)
_TRANSCRIPTION_ROLES = ("lemma", "phonetic", "phonemic", "morphemes", "pitch")
_UNTOUCHED_ROLES = _TRANSCRIPTION_ROLES + ("word-class",)
_KEEP = object()                          # a name that stays as it is (an identifiable person's)


class ArchiveError(ValueError):
    """The archive can't be written there (a folder in use, the database's own folder)."""


@dataclass
class Options:
    kind: str = ETHICAL
    notebook: bool = False             # include the notebook (the researcher's own work: off by default)
    replace_names: bool = True         # names in free text -> codes (always, in the anonymous archive)
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

    @property
    def names(self) -> bool:
        """Whether names in free text are replaced: always in the anonymous archive."""
        return self.replace_names or self.anonymous


@dataclass
class Report:
    kind: str = ETHICAL
    folder: Path | None = None
    files: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)       # "where: “text” → code"
    key: list[tuple[str, str, str]] = field(default_factory=list)  # (kind, old, new): never written in the clear
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
    extra_settings: int = 0                                   # unknown settings elements left out
    renamed_files: int = 0                                    # soundfile and TextGrid names changed
    key_written: bool = False
    notebook: bool = False
    scrubber: "Scrubber | None" = field(default=None, repr=False, compare=False)

    @property
    def renumbered(self) -> dict[str, str]:
        """old -> new for every row of the key (a code in both lists: its participant row)."""
        out: dict[str, str] = {}
        for _, old, new in self.key:
            out.setdefault(old, new)
        return out


def zip_available() -> bool:
    try:
        import pyzipper  # noqa: F401
    except ImportError:
        return False
    return True


# --------------------------------------------------------------------------
# What to replace in free text
# --------------------------------------------------------------------------

def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text) if text else text


class Scrubber:
    """Replaces people's names (and, in the anonymous archive, old codes and the language's and
    variety's names) in free text, in one pass, so a replacement is never replaced again.

    A word counts only as a whole word: the characters either side may not be letters or
    digits, so `KDB` is found in `LXX-KDB_D001.wav` and `Kuku_story` but not in `KDBX`."""

    def __init__(self):
        self.exact: dict[str, object] = {}      # matched as written
        self.folded: dict[str, object] = {}     # matched in any case (full names)
        self.rx: re.Pattern | None = None

    def add_name(self, name: str, code: str):
        """A person's full name (any case), then each part of it of 3 letters or more that
        isn't written in lower case (as written; scripts without capitals count), so "Sample
        Speaker" goes before "Sample"."""
        name = _nfc((name or "").strip())
        if not name or not code or name.lower() in ("redacted", code.lower()):
            return
        self.folded.setdefault(name.lower(), code)
        for part in re.split(r"[\s.,]+", name):
            if len(part) >= 3 and part[:1].isalpha() and not part[:1].islower():
                self.exact.setdefault(part, code)

    def keep_name(self, name: str):
        """A full name that stays as it is (an identifiable person's), even where a part of it
        is also part of a hidden person's name: the longer match wins."""
        name = _nfc((name or "").strip())
        if name:
            self.folded[name.lower()] = _KEEP

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
        self.rx = re.compile(r"(?<![^\W_])(?:" + "|".join(alts) + r")(?![^\W_])")

    def __bool__(self):
        return self.rx is not None

    def text(self, text: str, where: str, report: Report | None) -> str:
        if not text or self.rx is None:
            return text
        text = _nfc(text)

        def sub(m):
            t = m.group()
            code = self.exact.get(t)
            if code is None:
                code = self.folded.get(t.lower(), t)
            if code is _KEEP:
                return t
            if report is not None and code != t:
                report.replaced.append(f"{where}: “{t}” → {code}" if where else f"“{t}” → {code}")
            return code
        return self.rx.sub(sub, text)

    def filename(self, name: str, where: str = "", report: Report | None = None) -> str:
        """The same in a file name, whose words are joined by underscores as Praat writes them."""
        if not name or self.rx is None:
            return name
        return self.text(name.replace("_", " "), where, report).replace(" ", "_")

    def value(self, obj, where: str, report: Report | None):
        """Every string in a JSON-like value (a snapshot's setup)."""
        if isinstance(obj, str):
            return self.text(obj, where, report)
        if isinstance(obj, list):
            return [self.value(x, where, report) for x in obj]
        if isinstance(obj, dict):
            return {self.value(k, where, None) if isinstance(k, str) else k: self.value(v, where, report)
                    for k, v in obj.items()}
        return obj


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
# The plan: who becomes what, and what is replaced
# --------------------------------------------------------------------------

def _grid_speakers(db: Database) -> list[str]:
    """The @speaker codes in the texts' TextGrids' tier names and the clipped utterances'
    copies, in the order met (a code only a tier name knows still has to be renumbered)."""
    from . import textgrid as tgmod
    out: list[str] = []
    for t in db.texts:
        if not t.textgrid:
            continue
        path = storage.text_folder(db) / t.textgrid
        try:
            names = [x.name for x in tgmod.tiers(path)] if path.exists() else []
        except Exception:                       # unreadable: it won't go in anyway
            names = []
        out += [tier_base(n)[1] for n in names]
    for u in db.utterances:
        if u.source is not None:
            out += [tier_base(k)[1] for k in u.source.copied]
    return [c for c in dict.fromkeys(out) if c]


def code_map(db: Database, nb: nbmod.Notebook | None) -> tuple[dict[str, str], dict[str, str]]:
    """(participants' old code -> new, researchers' old code -> new): SP1, SP2… and RS1, RS2…,
    in the lists' order; codes used but not listed (a token's speaker, a text's or a session's
    person, a TextGrid tier's @speaker) follow, in the order they are first met. A code in both
    lists gets one of each."""
    md = db.metadata
    pmap: dict[str, str] = {}
    rmap: dict[str, str] = {}

    def add(code: str, m: dict, prefix: str):
        if code and code not in m:
            m[code] = f"{prefix}{len(m) + 1}"
    for p in md.participants:
        add(p.code, pmap, "SP")
    for p in md.researchers:
        add(p.code, rmap, "RS")
    for e in db.items():
        for t in e.tokens:
            add(t.speaker, pmap, "SP")
    for t in db.texts:
        for c in t.participants:
            add(c, pmap, "SP")
        for c in t.researchers:
            add(c, rmap, "RS")
    if nb is not None:
        for s in nb.sessions:
            for c in s.participants:
                add(c, pmap, "SP")
            for c in s.researchers:
                add(c, rmap, "RS")
    for c in _grid_speakers(db):
        if c not in rmap:
            add(c, pmap, "SP")
    return pmap, rmap


@dataclass
class Plan:
    pmap: dict[str, str]
    rmap: dict[str, str]
    lang_code: str
    var_code: str
    scrub: Scrubber
    key: list[tuple[str, str, str]]


def plan(db: Database, nb: nbmod.Notebook | None, opts: Options) -> Plan:
    """What the archive renumbers and replaces (nothing is changed here)."""
    md = db.metadata
    s = Scrubber()
    key: list[tuple[str, str, str]] = []
    pmap: dict[str, str] = {}
    rmap: dict[str, str] = {}
    lang_code, var_code = md.language_code, md.variety_code
    if opts.anonymous:
        pmap, rmap = code_map(db, nb if opts.notebook else None)
        key += [("participant", o, n) for o, n in pmap.items()]
        key += [("researcher", o, n) for o, n in rmap.items()]
        lang_code = md.language_code or (HIDDEN_LANGUAGE if md.language_name else "")
        var_code = md.variety_code or (HIDDEN_VARIETY if md.variety_name else "")
        if opts.hide_language_code and lang_code:
            lang_code = HIDDEN_LANGUAGE
        if opts.hide_variety_code and var_code:
            var_code = HIDDEN_VARIETY
        for old, new, kind in ((md.language_code, lang_code, "language"), (md.variety_code, var_code, "variety")):
            if old and new != old:
                key.append((kind, old, new))
                s.add_word(old, new)
        for p in md.participants:
            s.add_name(p.name, pmap.get(p.code, p.code))
        for p in md.researchers:
            s.add_name(p.name, rmap.get(p.code, p.code))
            s.add_word(_nfc(p.email), rmap.get(p.code, p.code), any_case=True)   # an email written in a note
        for name, code in ((md.language_name, lang_code), (md.variety_name, var_code)):
            if name and code:
                s.add_word(_nfc(name), code)          # as written: "up the hill" isn't the variety Hill
        for old, new in pmap.items():
            s.add_word(old, new)
        for old, new in rmap.items():
            if old not in pmap:
                s.add_word(old, new)
        olds = set(pmap) | set(rmap)
        for new in list(pmap.values()) + list(rmap.values()):
            if new not in olds:                       # a stray SP1 in free text would now mean someone else
                s.add_word(new, re.sub(r"\d+$", "?", new))
    elif opts.names:
        for p in md.participants + md.researchers:
            if p.identifiable:
                s.keep_name(p.name)
            else:
                s.add_name(p.name, p.code)
                s.add_word(_nfc(p.email), p.code, any_case=True)
    s.compile()
    return Plan(pmap, rmap, lang_code, var_code, s, key)


def archive_stem(db: Database, nb: nbmod.Notebook | None, opts: Options) -> str:
    """The archive's file name stem (and the default folder's start): the database's, with
    names, codes and hidden codes replaced."""
    stem = Path(db.path).stem if db.path else "Database"
    return plan(db, nb, opts).scrub.filename(stem)


# --------------------------------------------------------------------------
# The copy
# --------------------------------------------------------------------------

def _untouched_names(settings) -> set[str]:
    return {f.name for fs in (settings.entry_fields, settings.token_fields, settings.text_fields)
            for f in fs if f.role in _UNTOUCHED_ROLES}


def _scrub_values(obj, skip: set[str], scrub: Scrubber, where: str, report: Report):
    """Every value but the transcriptions and word class: open and closed fields alike, and
    values of fields since deleted (storage still writes them)."""
    for name, v in list(obj.values.items()):
        if v and name not in skip:
            obj.values[name] = scrub.text(v, f"{where} {name}", report)
    for name, langs in obj.multi.items():
        if name in skip:
            continue
        for lang, v in list(langs.items()):
            if v:
                langs[lang] = scrub.text(v, f"{where} {name}" + (f" ({lang})" if lang else ""), report)


def _transcription_tiers(db: Database, mapping) -> set[str]:
    """The tiers (by base name, lower case) a mapping sends to a transcription field."""
    roles = {f.name: f.role for f in db.settings.token_fields}
    m = mapping or db.settings.tier_mapping
    return {r.tier.lower() for r in m.rules if roles.get(r.field) in _TRANSCRIPTION_ROLES}


def _renamed(name: str, scrub: Scrubber, report: Report) -> str:
    """A file name as the archive writes it; counted rather than listed (there can be thousands)."""
    new = scrub.filename(name)
    report.renamed_files += new != name
    return new


def _scrub_mapping(m, scrub: Scrubber):
    if m is None:
        return
    m.main = scrub.text(m.main, "", None)
    for r in m.rules:
        r.tier = scrub.text(r.tier, "Tier mapping", None)


def anonymise(db: Database, nb: nbmod.Notebook | None, opts: Options, report: Report):
    """Archive copies of the database and notebook (the originals are untouched)."""
    report.kind = opts.kind
    out = copy.deepcopy(db)
    book = copy.deepcopy(nb) if (nb is not None and opts.notebook) else None
    report.notebook = book is not None
    md = out.metadata
    p = plan(db, nb, opts)
    scrub = report.scrubber = p.scrub
    report.key = list(p.key)
    pmap, rmap = p.pmap, p.rmap

    if opts.anonymous:
        author = (md.author or "").strip()
        owner = next((r for r in db.metadata.researchers if author and author in (r.name, r.code)), None)
        md.author = rmap.get(owner.code, owner.code) if owner else ("Anonymous" if author else "")
        md.language_name, md.language_code = p.lang_code, p.lang_code
        md.variety_name, md.variety_code = p.var_code, p.var_code
        for person, m in [(x, pmap) for x in md.participants] + [(x, rmap) for x in md.researchers]:
            report.hidden_people.append(person.code)
            person.code = m.get(person.code, person.code)
            person.name, person.description, person.consent, person.email = "", "", "", ""
    else:
        for person in md.participants + md.researchers:
            if person.identifiable:
                report.named_people.append(person.code)
                person.description = scrub.text(person.description, f"{person.code} description", report)
            else:
                report.hidden_people.append(person.code)
                person.name, person.description, person.email = "", "", ""
            person.consent = ""                   # consent forms travel only in the zip
        for person in md.participants:
            person.email = ""
        author = (md.author or "").strip()
        owner = next((r for r in db.metadata.researchers if author and author in (r.name, r.code)), None)
        if owner is not None and not owner.identifiable:
            md.author = owner.code
        else:
            md.author = scrub.text(md.author, "Owner", report)
    moved = _trim_places(md.locations, opts.place_levels, report) if opts.place_levels else {}

    def pc(c: str) -> str:
        return pmap.get(c, c)

    def rc(c: str) -> str:
        return rmap.get(c, c)

    skip = _untouched_names(out.settings)
    texts_by_id = {t.id: t for t in db.texts}
    for e in out.items():                         # lemmas and utterances
        _scrub_values(e, skip, scrub, e.ref, report)
        e.file_gloss = scrub.text(e.file_gloss, f"{e.ref} file label", report)
        src = getattr(e, "source", None)          # a clipped utterance's copy of its line's tiers
        if src is not None:
            text = texts_by_id.get(src.text)
            keep = _transcription_tiers(db, text.tiers if text else None)
            src.copied = {scrub.text(k, "", None):
                          v if tier_base(k)[0].lower() in keep else scrub.text(v, f"{e.ref} source", report)
                          for k, v in src.copied.items()}
        for t in e.tokens:
            t.speaker = pc(t.speaker)
            _scrub_values(t, skip, scrub, f"{e.ref} token", report)
            t.file = _renamed(t.file, scrub, report)
    for t in out.texts:
        t.participants = [pc(c) for c in t.participants]
        t.researchers = [rc(c) for c in t.researchers]
        if moved:
            t.locations = list(dict.fromkeys(moved.get(k, k) for k in t.locations))
        _scrub_values(t, skip, scrub, t.ref, report)
        t.file_label = scrub.text(t.file_label, f"{t.ref} file label", report)
        t.file, t.textgrid = _renamed(t.file, scrub, report), _renamed(t.textgrid, scrub, report)
        _scrub_mapping(t.tiers, scrub)
    s = out.settings
    _scrub_mapping(s.tier_mapping, scrub)
    for fs in (s.entry_fields, s.token_fields, s.text_fields):   # closed fields' lists
        for f in fs:
            if f.closed and f.role not in _UNTOUCHED_ROLES:
                for top in f.items:
                    for item in top.walk():
                        item.name = scrub.text(item.name, f"List {f.title}", report)
    for g in s.tags.all_groups():                 # tag and group descriptions are free text too
        g.description = scrub.text(g.description, f"Tag group {g.name}", report)
        for tag in g.tags:
            tag.description = scrub.text(tag.description, f"Tag {tag.name}", report)
    for c in s.ref_categories:
        c.name = scrub.text(c.name, f"Category {c.letter}", report)
    if s.extra:                                   # settings this version doesn't know: left out
        report.extra_settings = len(s.extra)
        s.extra = []
    md.description = scrub.text(md.description, "Metadata description", report)
    md.name = scrub.text(md.name, "Database name", report)
    for _, loc in md.all_locations():
        loc.description = scrub.text(loc.description, f"Place {loc.name}", report)

    if book is not None:
        for sess in book.sessions:
            sess.researchers = [rc(c) for c in sess.researchers]
            sess.participants = [pc(c) for c in sess.participants]
            if moved:
                sess.locations = list(dict.fromkeys(moved.get(k, k) for k in sess.locations))
            sess.notes = scrub.text(sess.notes, f"Notebook {sess.date} notes", report)
            for q in sess.questions + sess.todos:
                q.text = scrub.text(q.text, f"Notebook {sess.date} {'To Do' if q.is_todo else 'question'}", report)
                q.about = scrub.text(q.about, f"Notebook {sess.date} link", report)
            for c in sess.comments:
                c.text = scrub.text(c.text, f"Notebook {sess.date} comment", report)
                c.about = scrub.text(c.about, f"Notebook {sess.date} link", report)
        for h in book.hypotheses:                 # hypotheses (Cogitate) are notes too
            where = f"Hypothesis {h.label}"
            h.summary = scrub.text(h.summary, f"{where} summary", report)
            h.formulation = scrub.text(h.formulation, f"{where} formulation", report)
            for ln in h.links:
                ln.note = scrub.text(ln.note, f"{where} link note", report)
                ln.text = scrub.text(ln.text, f"{where} link", report)
                ln.about = scrub.text(ln.about, f"{where} link", report)
                if ln.view:
                    ln.view = scrub.value(ln.view, f"{where} snapshot", report)
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


def _copy_textgrid(db: Database, text, src: Path, dst: Path, scrub: Scrubber, report: Report) -> bool:
    """A TextGrid with its tier names and text put through the scrubber (renumbered codes in
    tx@SP1, names replaced), its transcription tiers' text left as it is. False if it couldn't
    be read (it is then left out, not copied as is)."""
    if not scrub:
        shutil.copy2(src, dst)
        return True
    from . import textgrid as tgmod
    keep = _transcription_tiers(db, text.tiers)
    try:
        from praatio import textgrid
        tg = tgmod.read_grid(src)
        new = textgrid.Textgrid(tg.minTimestamp, tg.maxTimestamp)
        taken: set[str] = set()
        for tier in tg.tiers:
            name = scrub.text(tier.name, f"{text.ref} TextGrid tier", report)
            base = name
            n = 2
            while name in taken:                  # two names that became one
                name, n = f"{base} ({n})", n + 1
            taken.add(name)
            if tier_base(tier.name)[0].lower() in keep:
                entries = list(tier.entries)
            else:
                entries = [e._replace(label=scrub.text(e.label, f"{text.ref} TextGrid {name}", report))
                           for e in tier.entries]
            new.addTier(tier.new(name=name, entries=entries))
        new.save(str(dst), format="long_textgrid", includeBlankSpaces=True)
        return True
    except Exception:                          # praatio raises several kinds
        return False


def check_folder(db: Database, folder: str | Path):
    """An archive goes into a new or empty folder of its own, never the database's own folder
    or its soundfiles (so nothing from an earlier export stays in it, and no original is
    written over). Raises ArchiveError."""
    folder = Path(folder)
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise ArchiveError(f"{folder} isn't empty. An archive goes into a new or empty folder of its own, so "
                           "nothing from an earlier export stays in it.")
    if db.path:
        main = Path(db.path).resolve().parent
        target = folder.resolve()
        if target == main or target.is_relative_to(main / layout.SOUNDFILES):
            raise ArchiveError("An archive can't go into the database's own folder or its Soundfiles folder.")


def export(db: Database, nb: nbmod.Notebook | None, folder: str | Path, opts: Options) -> Report:
    """Write the archive into folder (new or empty; made if needed). Returns what was done."""
    check_folder(db, folder)
    report = Report(kind=opts.kind, folder=Path(folder))
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    out, book = anonymise(db, nb, opts, report)
    scrub = report.scrubber
    stem = Path(db.path).stem if db.path else "Database"
    out_stem = scrub.filename(stem)
    target = folder / f"{out_stem}{SUFFIX[opts.kind]}.xml"
    pmap = {o: n for k, o, n in report.key if k == "participant"}

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
                if _copy_textgrid(db, t, src, dst_folder / new, scrub, report):
                    report.textgrids += 1
                else:
                    report.unreadable_textgrids.append(new)
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
                inner = pmap.get(code, code) if opts.anonymous else code
                # the names inside a zip can be read without the password: only the code, never
                # the original file name (which may hold a name or an old code)
                for i, f in enumerate(files, 1):
                    name = "consent" + (f"-{i}" if len(files) > 1 else "") + f.suffix.lower()
                    zf.write(f, f"{inner}/{name}")
                    report.consent_files += 1
            if opts.anonymous and report.key:      # the key: only ever here, never in the clear
                buf = io.StringIO()
                w = csv.writer(buf)
                w.writerow(["kind", "old code", "new code"])
                for kind, old, new in report.key:
                    w.writerow([kind, old, new])
                zf.writestr("key.csv", "﻿" + buf.getvalue())
                report.key_written = True
        report.files.append(zpath.name)
    return report


def summary(report: Report, opts: Options) -> str:
    """What the export wrote and changed, for the message at the end."""
    lines = [f"{TITLES[opts.kind]} written to {report.folder}:", *(f"  • {f}" for f in report.files)]
    if opts.anonymous:
        people = sum(1 for k, _, _ in report.key if k in ("participant", "researcher"))
        lines.append(f"Nobody is named: {people} codes were renumbered (SP1…, RS1…), and every name, "
                     "description, email and consent link was taken out.")
        hidden = [(k, n) for k, _, n in report.key if k in ("language", "variety")]
        if hidden:
            lines.append("Hidden too: " + ", ".join(f"the {k} code (now {n})" for k, n in hidden) + ".")
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
    if report.renamed_files:
        lines.append(f"{report.renamed_files} soundfile and TextGrid name(s) changed to match.")
    if report.unreadable_textgrids:
        lines.append(f"Left out, unreadable: {', '.join(report.unreadable_textgrids)}.")
    if report.extra_settings:
        lines.append(f"{report.extra_settings} setting(s) this version doesn't know were left out.")
    if opts.place_levels:
        lines.append(f"{report.places_removed} place(s) below level {opts.place_levels} were left out.")
    if opts.consent_password:
        lines.append(f"{report.consent_files} consent file(s) are in the password-protected zip, named by code"
                     + (f"; none found for {', '.join(report.missing_consent)}." if report.missing_consent else "."))
    lines.append("The notebook went in, at your choice." if report.notebook else
                 "The notebook (your notes, questions and hypotheses) stayed out: it is your own work, "
                 "kept in your Full backups.")
    if report.replaced:
        lines.append(f"\nReplaced ({len(report.replaced)}):")
        lines += [f"  • {r}" for r in report.replaced[:25]]
        if len(report.replaced) > 25:
            lines.append(f"  … and {len(report.replaced) - 25} more")
    lines.append("\nComments, translations and TextGrids can still hold things that identify people (a name "
                 "that isn't on the lists, a village). Read them through before sharing.")
    return "\n".join(lines)
