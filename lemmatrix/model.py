# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Lemmatrix data model: databases, entries, tokens and the tag structure.

Everything here is plain Python with no Qt, so it can be tested on its own.
Reading and writing the XML file lives in storage.py.
"""

from __future__ import annotations

import copy
import datetime as _dt
import re
import unicodedata
import uuid
from dataclasses import dataclass, field

# Characters Windows forbids in file names. Glosses, codes and references
# that end up in soundfile names may not contain them.
FORBIDDEN_CHARS = '/\\:*?"<>|'


# Characters XML can't hold (control characters, e.g. the line break Word puts on the clipboard
# for Shift+Enter): a file containing one can't be opened again, so they never reach the file.
_NOT_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff\ud800-\udfff]")


def xml_safe(text: str, line_break: str = " ") -> str:
    """text without the characters XML can't hold; Word's line breaks (\\v, \\f) become line_break."""
    if not _NOT_XML.search(text):
        return text
    return _NOT_XML.sub(lambda m: line_break if m.group() in "\x0b\x0c" else "", text)


def write_atomically(path: str, text: str):
    """Write a file via path.saving, flushed to the disk before it replaces the old one, so a power
    cut or a dead battery leaves either the old file or the new one, never half of one."""
    import os
    tmp = path + ".saving"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    return tmp


def sync_file(path) -> None:
    """Make the operating system put a file's contents on the disk now, not when it gets round to
    it, so a power cut or a flat battery straight after can't leave it empty or cut short. (On
    Windows the file must be opened for writing to be flushed.)"""
    import os
    with open(path, "rb+") as fh:
        fh.flush()
        os.fsync(fh.fileno())


def write_bytes_safely(path, data: bytes, suffix: str = ".part") -> None:
    """Write a file as the database is written (the audit, 25 October): into path + suffix, put on
    the disk (sync), then swapped in for the old file, so a crash at any moment leaves the old file
    or the new one, never half of one. For recordings above all: they can't be made again."""
    import os
    from pathlib import Path as _Path
    path = _Path(path)
    tmp = path.with_name(path.name + suffix)
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def nfc(text: str | None) -> str:
    """Normalise text to Unicode NFC so identical-looking strings match."""
    if not text:
        return ""
    return unicodedata.normalize("NFC", text)


def forbidden_in(text: str) -> str:
    """Return the forbidden file-name characters found in text, in order."""
    found = []
    for ch in text or "":
        if ch in FORBIDDEN_CHARS and ch not in found:
            found.append(ch)
    return "".join(found)


def today() -> str:
    return _dt.date.today().isoformat()


_QUOTES = "\"'“”‘’"


def meaning(text: str) -> str:
    """A gloss or translation as shown: in single quotes, ‘goat’ (the Leipzig convention), the
    same everywhere (Josh, 20 October). Quotes already round it aren't doubled."""
    t = (text or "").strip()
    while len(t) >= 2 and t[0] in _QUOTES and t[-1] in _QUOTES:
        t = t[1:-1].strip()
    return f"‘{t}’" if t else ""


def token_form(db: "Database", t, order=("phonemic", "phonetic")) -> str:
    """A token's form where one stands for it: Phonemic, else Phonetic (Josh, 25 October: the
    analysed form before the raw one), or the order given; "" when both are empty."""
    if t is None:
        return ""
    for role in order:
        f = db.settings.token_field(role)
        if f is not None and t.get(f.name):
            return t.get(f.name)
    return ""


def new_id() -> str:
    """A short unique id for an entry or token: notebook links point at it, so they
    survive changes to the reference or the tags."""
    return uuid.uuid4().hex[:10]


# --------------------------------------------------------------------------
# Tag structure: groups (nested) -> tags
# --------------------------------------------------------------------------
#
# One hierarchy for the whole database, organised however the user likes (by word
# class, by construction, by frame...). Any tag can go on any token. Two rules stay:
# a token takes at most one tag from each lowest-level group, and tag names are
# unique in the whole structure (tokens store the names).
#
# A group can say which word classes it is *usual* for (e.g. Verbal: VERB). This is
# only a hint: it decides which groups the token dialogue shows first, which
# defaults new tokens get, and which tags are marked as unusual. Subgroups take
# their parent's hint unless they have their own; a group without one (at any
# level) is usual for every lemma.


# The tag structure's lookups (by name, in order, the usual-for hints) are cached, since every
# soundfile name, chip and save asks them: at 58,000 tokens rebuilding them for each question took
# most of the time spent opening a database (25 October). Any change to a tag, a group or their
# lists bumps a counter, which makes every cached index out of date, so a change made anywhere,
# in any way, is never missed.
_TAG_GENERATION = [0]


def _bump():
    _TAG_GENERATION[0] += 1


class _Watched(list):
    """A list that bumps the tag structure's counter whenever it changes."""

    def __init__(self, items=()):
        super().__init__(items)
        _bump()

    def _changed(name):
        def f(self, *a, **k):
            out = getattr(list, name)(self, *a, **k)
            _bump()
            return out
        f.__name__ = name
        return f

    for _n in ("append", "extend", "insert", "remove", "pop", "clear", "sort", "reverse",
               "__setitem__", "__delitem__", "__iadd__", "__imul__"):
        locals()[_n] = _changed(_n)
    del _n, _changed

    def __deepcopy__(self, memo):
        import copy as _copy
        return type(self)(_copy.deepcopy(list(self), memo))

    def __reduce_ex__(self, protocol):
        return (type(self), (list(self),))


class _Bumping:
    """Setting any attribute of a tag or group bumps the counter (lists become watched)."""
    _LISTS: tuple = ()

    def __setattr__(self, name, value):
        if name in self._LISTS and not isinstance(value, _Watched):
            value = _Watched(value)
        object.__setattr__(self, name, value)
        _bump()


@dataclass
class Tag(_Bumping):
    name: str
    code: str = ""
    default: bool = False        # a group's default: real tag, no file-name code
    description: str = ""        # e.g. a frame's carrier sentence

    def file_code(self) -> str:
        return "" if self.default else self.code

    def display(self) -> str:
        """Short label for headers and buttons: the code, or the name."""
        return self.code if (self.code and not self.default) else self.name


@dataclass
class Group(_Bumping):
    _LISTS = ("tags", "groups", "usual")
    name: str
    tags: list[Tag] = field(default_factory=list)
    groups: list["Group"] = field(default_factory=list)
    usual: list[str] = field(default_factory=list)    # word classes it's usual for ([]: its parent's)
    utterances_only: bool = False                      # a rule: its tags go on utterances only (subgroups too)
    description: str = ""

    def leaf_groups(self, path: tuple[str, ...] = ()):
        """Yield (path, group) for every group that directly holds tags, in order."""
        here = path + (self.name,)
        if self.tags:
            yield here, self
        for sub in self.groups:
            yield from sub.leaf_groups(here)

    def walk(self):
        yield self
        for sub in self.groups:
            yield from sub.walk()

    def default_tag(self) -> Tag | None:
        for t in self.tags:
            if t.default:
                return t
        return None


@dataclass
class TagStructure(_Bumping):
    _LISTS = ("groups",)
    groups: list[Group] = field(default_factory=list)

    def __deepcopy__(self, memo):
        import copy as _copy
        return TagStructure(_copy.deepcopy(list(self.groups), memo))    # without the cache

    # ---- the cached index (see _TAG_GENERATION) --------------------------------------
    def _index(self) -> dict:
        c = self.__dict__.get("_cache")
        if c is not None and c["gen"] == _TAG_GENERATION[0]:
            return c
        leaves = [x for g in self.groups for x in g.leaf_groups()]
        tags = [(t, g) for _, g in leaves for t in g.tags]
        by_name: dict = {}
        for t, g in tags:
            by_name.setdefault(t.name, (t, g))
        usual: dict[int, tuple[str, ...]] = {}
        only: dict[int, bool] = {}

        def walk(g: Group, inherited: tuple[str, ...], inherited_only: bool):
            mine = tuple(g.usual) or inherited
            usual[id(g)] = mine
            only[id(g)] = g.utterances_only or inherited_only
            for sub in g.groups:
                walk(sub, mine, only[id(g)])
        for g in self.groups:
            walk(g, (), False)
        c = {"gen": _TAG_GENERATION[0], "leaves": leaves, "tags": tags, "by_name": by_name,
             "order": {t.name: i for i, (t, _) in enumerate(tags)}, "usual": usual, "only": only}
        object.__setattr__(self, "_cache", c)     # not a change: no bump
        return c

    # ---- lookups -------------------------------------------------------
    def leaf_groups(self) -> list[tuple[tuple[str, ...], Group]]:
        """(path, group) for every group that holds tags, in tag order."""
        return list(self._index()["leaves"])

    def all_groups(self):
        for g in self.groups:
            yield from g.walk()

    def tags(self) -> list[tuple[Tag, Group]]:
        return list(self._index()["tags"])

    def find(self, name: str) -> tuple[Tag, Group] | None:
        return self._index()["by_name"].get(name)

    def tag(self, name: str) -> Tag | None:
        hit = self.find(name)
        return hit[0] if hit else None

    def path_of(self, group: Group) -> tuple[str, ...]:
        for path, g in self.leaf_groups():
            if g is group:
                return path
        return (group.name,)

    # ---- usual-for hints -----------------------------------------------
    def usual_map(self) -> dict[int, tuple[str, ...]]:
        """id(group) -> the word classes it is usual for, inherited ((): every lemma)."""
        return dict(self._index()["usual"])

    def only_map(self) -> dict[int, bool]:
        """id(group) -> whether it is for utterances only (marked on it or on a group above it)."""
        return dict(self._index()["only"])

    def for_utterances_only(self, group: Group, only: dict | None = None) -> bool:
        return (only or self.only_map()).get(id(group), False)

    def utterance_only_tags(self) -> set[str]:
        """The names of the tags that go on utterances only."""
        only = self.only_map()
        return {t.name for _, g in self.leaf_groups() if only.get(id(g)) for t in g.tags}

    def is_usual(self, group: Group, classes, usual: dict | None = None) -> bool:
        """classes: the lemma's word class and the classes above it in the Word Class list."""
        hint = (usual or self.usual_map()).get(id(group), ())
        return not hint or bool(set(hint) & set(classes))

    def usual_groups(self, classes) -> list[tuple[tuple[str, ...], Group]]:
        """The groups usual for a lemma of these classes (never the utterance-only ones)."""
        usual, only = self.usual_map(), self.only_map()
        return [(p, g) for p, g in self.leaf_groups()
                if self.is_usual(g, classes, usual) and not only.get(id(g))]

    def unusual(self, classes, names) -> list[str]:
        """The tags among names whose group isn't usual for a lemma of these classes."""
        usual, only = self.usual_map(), self.only_map()
        out = []
        for n in names:
            hit = self.find(n)
            if hit and (not self.is_usual(hit[1], classes, usual) or only.get(id(hit[1]))):
                out.append(n)             # (a tag for utterances only, on a lemma token, too)
        return out

    def rename_classes(self, renames: dict[str, str]):
        """Follow renamed word classes in the hints."""
        if not renames:
            return
        for g in self.all_groups():
            g.usual = list(dict.fromkeys(renames.get(c, c) for c in g.usual))

    # ---- ordering and checking ----------------------------------------
    def sort(self, names) -> list[str]:
        """Sort tag names into tag order. Unknown names keep their order, last."""
        order = self._index()["order"]
        names = list(dict.fromkeys(names))  # drop duplicates, keep first
        known = sorted((n for n in names if n in order), key=order.get)
        unknown = [n for n in names if n not in order]
        return known + unknown

    def conflicts(self, names) -> list[str]:
        """Describe tags that break the one-tag-per-group rule or aren't in the structure."""
        problems = []
        seen: dict[int, str] = {}
        for n in names:
            hit = self.find(n)
            if hit is None:
                problems.append(f'"{n}" is not in the tag structure')
                continue
            _, g = hit
            if id(g) in seen:
                problems.append(f'"{seen[id(g)]}" and "{n}" are both in the group "{g.name}"')
            else:
                seen[id(g)] = n
        return problems

    def with_defaults(self, names, classes=()) -> list[str]:
        """Add the default of each group usual for the lemma, where the group has no tag yet."""
        names = list(names)
        used_groups = set()
        for n in names:
            hit = self.find(n)
            if hit:
                used_groups.add(id(hit[1]))
        for _, g in self.usual_groups(classes):
            d = g.default_tag()
            if d and id(g) not in used_groups:
                names.append(d.name)
        return self.sort(names)

    def file_codes(self, names) -> list[str]:
        codes = []
        for n in self.sort(names):
            t = self.tag(n)
            code = t.file_code() if t else n
            if code:
                codes.append(code)
        return codes

    def display(self, names) -> str:
        """Short label for a tag combination, e.g. 'PL + GEN'."""
        names = self.sort(names)
        if not names:
            return "Citation"
        labels = []
        for n in names:
            t = self.tag(n)
            labels.append(t.display() if t else n)
        return " + ".join(labels)

    def descriptions(self, names) -> str:
        """The descriptions of these tags, one line each ("Frame 1: I saw ___"), for tooltips;
        "" if none of them has one."""
        out = []
        for n in self.sort(names):
            t = self.tag(n)
            if t and t.description:
                out.append(f"{t.name}: {t.description}")
        return "\n".join(out)

    def tag_tip(self, names, empty: str = "Citation (no tags)") -> str:
        """A tooltip for a tag combination: the names, then any descriptions."""
        names = self.sort(names)
        tip = ", ".join(names) or empty
        d = self.descriptions(names)
        return tip + ("\n" + d if d else "")

    def duplicate_codes(self) -> list[str]:
        """Codes shared by two tags: their file names couldn't be told apart."""
        problems = []
        seen: dict[str, str] = {}
        for t, _ in self.tags():
            c = t.file_code()
            if not c:
                continue
            if c in seen and seen[c] != t.name:
                msg = f'"{seen[c]}" and "{t.name}" share the code {c}'
                if msg not in problems:
                    problems.append(msg)
            seen.setdefault(c, t.name)
        return problems


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

@dataclass
class ListItem:
    """One value in a closed field's list; lists can be hierarchical."""
    name: str
    children: list["ListItem"] = field(default_factory=list)

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


# Fields other features depend on: they can be relabelled and moved, but not deleted (idea 9).
CORE_ROLES = ("lemma", "gloss", "word-class", "stem-type", "phonetic", "phonemic", "morphemes", "pitch",
              "translation", "comment", "title", "genre", "status")
NEW_ROLES = ("stem-type",)          # core fields added after databases existed: "added", not "restored"


@dataclass
class FieldDef:
    name: str                    # XML element name, no spaces
    label: str = ""
    role: str = ""               # lemma, gloss, word-class, phonetic, phonemic, pitch, translation
    closed: bool = False         # values come from a list kept in settings
    items: list[ListItem] = field(default_factory=list)
    abbr: str = ""               # its abbreviation, e.g. pht (format 13; ideas 72 and 73, Josh, 26 October)

    @property
    def title(self) -> str:
        return self.label or self.name

    @property
    def multilingual(self) -> bool:
        return self.role in ("gloss", "translation")

    @property
    def is_comment(self) -> bool:
        """Comment fields are the ones the notebook records (by name: Comment, Comments...)."""
        return not self.multilingual and (self.role == "comment" or "comment" in self.name.lower())

    @property
    def builtin(self) -> bool:
        """Built-in fields can be relabelled and moved but not deleted."""
        return self.role in CORE_ROLES

    def all_values(self) -> list[str]:
        return [i.name for top in self.items for i in top.walk()]

    def add_value(self, value: str):
        if value and value not in self.all_values():
            self.items.append(ListItem(value))


LEMMAS, UTTERANCES, TEXTS = "lemmas", "utterances", "texts"      # what a reference category is for


SEQUENCE = "sequence"     # the reference scheme with no categories: references are numbers
SEQ = "#"                 # the one category the sequence scheme offers (never written into a reference)
SEQUENCE_NAMES = {"lemmas": "Next number", "utterances": "Next number", "texts": "Next number"}


@dataclass
class RefCategory:
    letter: str
    name: str
    numbering: str = "auto"      # auto or manual
    kind: str = LEMMAS           # lemmas, utterances (U, W, X, Y, Z by default) or texts (T, S)

    @property
    def label(self) -> str:
        """How the category is offered in a list: "D  Mammals", or just "Next number"."""
        return self.name if self.letter == SEQ else f"{self.letter}  {self.name}"


@dataclass
class TierRule:
    """A TextGrid tier, by name (the part before any @speaker), and the field it fills in
    ("" = ignored); lang for a multilingual field such as Translation."""
    tier: str
    field: str = ""
    lang: str = ""

    @property
    def key(self) -> str:
        return f"{self.field}:{self.lang}" if self.lang else self.field


SPEAKER_FIELD = "@speaker"   # a tier mapping target: the tier's text is the line's speaker code


def tier_base(name: str) -> tuple[str, str]:
    """("tx", "SP1") for "tx@SP1"; ("tx", "") for "tx"."""
    base, _, speaker = (name or "").partition("@")
    return base.strip(), speaker.strip()


@dataclass
class TierMapping:
    """Which TextGrid tiers fill which fields. The main tier's intervals are the lines."""
    main: str = "tx"
    rules: list[TierRule] = field(default_factory=list)

    def rule(self, tier: str) -> TierRule | None:
        base = tier_base(tier)[0].lower()
        return next((r for r in self.rules if r.tier.lower() == base), None)

    def is_main(self, tier: str) -> bool:
        return tier_base(tier)[0].lower() == self.main.lower()

    def copy(self) -> "TierMapping":
        return copy.deepcopy(self)


@dataclass
class Settings:
    entry_fields: list[FieldDef] = field(default_factory=list)
    token_fields: list[FieldDef] = field(default_factory=list)
    gloss_languages: list[str] = field(default_factory=lambda: ["en"])
    primary_gloss: str = "en"
    tags: TagStructure = field(default_factory=TagStructure)
    ref_scheme: str = "categories"
    ref_digits: int = 3
    ref_categories: list[RefCategory] = field(default_factory=list)
    filename_pattern: str = "{language}-{variety}_{reference}_{gloss}_{tags}"
    utterance_pattern: str = "{language}-{variety}_{reference}_{label}"   # utterances: no tags
    text_pattern: str = "{language}-{variety}_{reference}_{title}"        # texts and songs
    clip_padding: int = 100                       # ms of the text's recording kept either side of a clip
    text_fields: list[FieldDef] = field(default_factory=list)   # Title, Genre, Status, Description...
    tier_mapping: TierMapping = field(default_factory=TierMapping)
    tag_separator: str = "-"
    auto_update_names: bool = True
    pitch_low: int = 1
    pitch_high: int = 5
    pitch_style: str = "contours"
    play_cell_on_click: bool = False
    matrices: list = field(default_factory=list)      # saved MatrixConfig objects
    spelling_words: list[str] = field(default_factory=list)   # the spellcheck's own word list (Sample variety...)
    extra: list = field(default_factory=list)   # unknown settings elements, kept as-is

    def entry_field(self, role_or_name: str) -> FieldDef | None:
        for f in self.entry_fields:
            if f.role == role_or_name or f.name == role_or_name:
                return f
        return None

    def text_field(self, role_or_name: str) -> FieldDef | None:
        for f in self.text_fields:
            if f.role == role_or_name or f.name == role_or_name:
                return f
        return None

    def token_field(self, role_or_name: str) -> FieldDef | None:
        for f in self.token_fields:
            if f.role == role_or_name or f.name == role_or_name:
                return f
        return None

    def categories(self, kind: str = LEMMAS) -> list[RefCategory]:
        if self.ref_scheme == SEQUENCE:
            # a database built on the CAWL or Swadesh (idea 40, Josh, 22 October): no categories;
            # lemmas, utterances and texts all take the next number
            return [RefCategory(SEQ, SEQUENCE_NAMES.get(kind, "Next number"), kind=kind)]
        return [c for c in self.ref_categories if c.kind == kind]

    def ref_prefix(self, letter: str) -> str:
        """The letters a category's references start with ("" for the next-number scheme)."""
        return "" if letter == SEQ else letter

    def category(self, ref: str) -> RefCategory | None:
        """The category a reference belongs to, by its letters (W001 -> W)."""
        if self.ref_scheme == SEQUENCE:
            return None
        m = re.match(r"[A-Za-z]+", ref or "")
        if not m:
            return None
        return next((c for c in self.ref_categories if c.letter == m.group(0)), None)

    def list_items(self, f: FieldDef) -> list[ListItem]:
        """The list behind a closed field."""
        return f.items

    def word_classes(self) -> list[str]:
        """Every value in the Word Class list, nested ones included, in list order."""
        f = self.entry_field("word-class")
        return f.all_values() if f else []

    def class_and_above(self, word_class: str) -> list[str]:
        """A word class and the classes above it in the Word Class list (Kinship -> Relational, NOUN)."""
        if not word_class:
            return []
        f = self.entry_field("word-class")

        def find(items, path):
            for it in items:
                if it.name == word_class:
                    return path + [it.name]
                hit = find(it.children, path + [it.name])
                if hit:
                    return hit
            return None
        path = find(f.items, []) if f else None
        return list(reversed(path)) if path else [word_class]


# --------------------------------------------------------------------------
# Metadata, entries, tokens
# --------------------------------------------------------------------------

@dataclass
class Support:
    """Acknowledgements (IDEAS.md idea 59, Josh, 24 October): an organisation's support of the
    project: who, the grant or its number, and what it funded."""
    organisation: str = ""
    grant: str = ""
    funded: str = ""


@dataclass
class Thanks:
    """Acknowledgements (idea 59): a personal thank-you, to a person or a group, and what for. Left
    out of the Anonymous archive, and of the Ethical one unless chosen there (Josh: a person thanked
    may not have signed an agreement)."""
    who: str = ""
    what_for: str = ""


@dataclass
class Person:
    """A researcher or a participant (speaker)."""
    code: str
    name: str = ""
    description: str = ""
    consent: str = ""             # participants: the file documenting informed consent
    email: str = ""               # researchers: where ɛλicit tells them recordings are in (idea 19)
    identifiable: bool = False    # may be named in an Ethical archive (idea 44): a participant agreed to it in
                                  # the consent form (unticked for a new one); a researcher is ticked when added
    audio_sharing: bool = False   # participants: agreed in the consent form that their recordings be shared

    @classmethod
    def researcher(cls, code: str, name: str = "", **kw) -> "Person":
        """A new researcher: Identifiable? ticked (Josh, 22 October)."""
        kw.setdefault("identifiable", True)
        return cls(code, name, **kw)




@dataclass
class Location:
    """A place in the hierarchical list of locations (country > region > village)."""
    name: str
    code: str = ""
    description: str = ""
    children: list["Location"] = field(default_factory=list)

    @property
    def key(self) -> str:
        """What sessions store: the code, or the name for a place without one."""
        return self.code or self.name

    def walk(self, path: tuple = ()):
        """(path of names above it, location) for this place and everything in it."""
        yield path, self
        for c in self.children:
            yield from c.walk(path + (self.name,))


@dataclass
class Metadata:
    language_code: str = ""
    language_name: str = ""
    variety_code: str = ""
    variety_name: str = ""
    name: str = ""                # the database's own name, e.g. "Complete Lexicon" (not its file name)
    author: str = ""              # who owns the database
    researchers: list[Person] = field(default_factory=list)
    participants: list[Person] = field(default_factory=list)
    locations: list[Location] = field(default_factory=list)
    description: str = ""
    wordlist_base: str = ""       # EACW, CAWL or SWADESH: the list the references are numbers of (format 9)
    wordlist_items: str = ""      # EACW: base (its default items) or expanded (format 11)
    wordlist_region: str = ""     # EACW: global, africa, or a region N W E S C (format 11)
    # typological features (format 10; IDEAS.md ideas 9 and 56): data about the language, read near
    # the top of the file by people and machines. "tone": tonal, intonational or unspecified
    typology: dict[str, str] = field(default_factory=lambda: {"tone": "tonal"})
    wordlist_version: str = ""    # EACW: the version of the list the database is up to date with (format 12)
    support: list[Support] = field(default_factory=list)    # acknowledgements (format 12, idea 59)
    thanks: list[Thanks] = field(default_factory=list)

    def researcher(self, code: str) -> Person | None:
        return next((p for p in self.researchers if p.code == code), None)

    def participant(self, code: str) -> Person | None:
        return next((p for p in self.participants if p.code == code), None)

    def all_locations(self):
        """(path of names above it, location) for every place, in list order."""
        for top in self.locations:
            yield from top.walk()

    def location(self, key: str) -> Location | None:
        return next((loc for _, loc in self.all_locations() if loc.key == key), None)

    def location_path(self, key: str) -> str:
        """"Sudan › Blue Nile District › Sample variety village" for a location key."""
        for path, loc in self.all_locations():
            if loc.key == key:
                return " › ".join(path + (loc.name,))
        return key


@dataclass
class Token:
    tags: list[str] = field(default_factory=list)
    speaker: str = ""
    collected: str = ""
    file: str = ""                                      # actual recording name on disk
    rerecord: bool = False                              # flagged: the recording should be made again
    values: dict[str, str] = field(default_factory=dict)            # Phonetic, Pitch, ...
    multi: dict[str, dict[str, str]] = field(default_factory=dict)  # Translation -> {lang: text}
    changed: dict[str, str] = field(default_factory=dict)  # comment field -> date it was last changed
    id: str = field(default_factory=new_id, compare=False)

    @property
    def is_citation(self) -> bool:
        return not self.tags

    def get(self, name: str, lang: str | None = None) -> str:
        if name in self.multi:
            d = self.multi[name]
            if lang:
                return d.get(lang, "")
            return next(iter(d.values()), "")
        return self.values.get(name, "")

    def set(self, name: str, text: str, lang: str | None = None, multilingual: bool = False):
        text = nfc(text)
        if multilingual or lang:
            d = self.multi.setdefault(name, {})
            if text:
                d[lang or ""] = text
            else:
                d.pop(lang or "", None)
                if not d:
                    self.multi.pop(name, None)
        elif text:
            self.values[name] = text
        else:
            self.values.pop(name, None)

    def has_content(self) -> bool:
        return bool(self.values or self.multi or self.file)

    def copy(self) -> "Token":
        return copy.deepcopy(self)


@dataclass
class Entry:
    ref: str
    file_gloss: str = ""
    values: dict[str, str] = field(default_factory=dict)            # Lemma, WordClass, ...
    multi: dict[str, dict[str, str]] = field(default_factory=dict)  # Gloss -> {lang: text}
    tokens: list[Token] = field(default_factory=list)
    changed: dict[str, str] = field(default_factory=dict)  # comment field -> date it was last changed
    id: str = field(default_factory=new_id, compare=False)
    # From (Josh, 22 October): what the lemma comes from, beside its Stem type: lemmas it is built from
    # (by id) and languages it was borrowed from (ISO 639-3 codes, or a name as typed)
    from_lemmas: list[str] = field(default_factory=list)
    from_languages: list[str] = field(default_factory=list)
    # Comparative wordlists (idea 40, Josh, 22 October; format 9): the numbers of the lists other than
    # the database's base, e.g. {"CAWL": ["0345"], "SWADESH": ["42"]}; hidden in the views
    lists: dict[str, list[str]] = field(default_factory=dict)

    def add_token(self, t: "Token"):
        """A new token at its place (Josh, 23 October: tokens can be a bit hodgepodge, but the
        citation form always comes first): a citation token (no tags) after the citation tokens at
        the start, any other at the end."""
        if t.is_citation:
            k = 0
            while k < len(self.tokens) and self.tokens[k].is_citation:
                k += 1
            self.tokens.insert(k, t)
        else:
            self.tokens.append(t)

    def citation_token(self) -> "Token | None":
        """The lemma's citation token (no tags), else its first token."""
        return next((t for t in self.tokens if t.is_citation), self.tokens[0] if self.tokens else None)

    def get(self, name: str, lang: str | None = None) -> str:
        if name in self.multi:
            d = self.multi[name]
            if lang:
                return d.get(lang, "")
            return next(iter(d.values()), "")
        return self.values.get(name, "")

    def set(self, name: str, text: str, lang: str | None = None, multilingual: bool = False):
        text = nfc(text)
        if multilingual or lang:
            d = self.multi.setdefault(name, {})
            if text:
                d[lang or ""] = text
            else:
                d.pop(lang or "", None)
                if not d:
                    self.multi.pop(name, None)
        elif text:
            self.values[name] = text
        else:
            self.values.pop(name, None)

    def copy(self) -> "Entry":
        return copy.deepcopy(self)


@dataclass
class ClipSource:
    """Where a clipped utterance came from: a line of a text (its times), what was copied from
    each tier, and when the TextGrid was last changed (for Pull, stage 4)."""
    text: str                                    # the text's id
    start: float
    end: float
    copied: dict[str, str] = field(default_factory=dict)   # tier name -> its text, as copied
    modified: str = ""                           # the TextGrid's last-modified time, ISO


@dataclass
class Utterance(Entry):
    """A one-off sentence or phrase with no lemma: one reference, one token (one transcription,
    one recording). file_gloss is its file label ("hare ran"), copied into its file name;
    lemmas are the ids of the lemmas it is linked to by hand; source, for one clipped from a
    text, its line."""
    lemmas: list[str] = field(default_factory=list)
    source: ClipSource | None = None

    @property
    def token(self) -> Token:
        if not self.tokens:
            self.tokens.append(Token())
        return self.tokens[0]

    @property
    def label(self) -> str:
        return self.file_gloss

    def copy(self) -> "Utterance":
        return copy.deepcopy(self)


def is_utterance(obj) -> bool:
    return isinstance(obj, Utterance)


@dataclass
class Text:
    """A text or song: a catalogue record with a recording and its Praat TextGrid. The lines
    stay in the TextGrid (read when needed); file_label is the title as it was when the text
    was added, used in the files' names. tiers: this text's own tier mapping, if it differs
    from the database's."""
    ref: str
    file_label: str = ""
    date: str = ""
    participants: list[str] = field(default_factory=list)
    researchers: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    file: str = ""                               # the recording, in Soundfiles/Texts
    textgrid: str = ""                           # the TextGrid, beside it
    values: dict[str, str] = field(default_factory=dict)   # Title, Genre, Status, Description...
    changed: dict[str, str] = field(default_factory=dict)
    tiers: TierMapping | None = None
    id: str = field(default_factory=new_id, compare=False)

    def get(self, name: str, lang: str | None = None) -> str:
        return self.values.get(name, "")

    def set(self, name: str, text: str, lang: str | None = None, multilingual: bool = False):
        text = nfc(text)
        if text:
            self.values[name] = text
        else:
            self.values.pop(name, None)

    @property
    def multi(self):
        return {}

    def copy(self) -> "Text":
        return copy.deepcopy(self)


def is_text(obj) -> bool:
    return isinstance(obj, Text)


@dataclass
class Database:
    metadata: Metadata = field(default_factory=Metadata)
    settings: Settings = field(default_factory=Settings)
    entries: list[Entry] = field(default_factory=list)
    utterances: list[Utterance] = field(default_factory=list)
    texts: list[Text] = field(default_factory=list)
    path: str = ""                                    # where it was loaded from / saved to
    load_notes: list = field(default_factory=list, compare=False)   # e.g. what an upgrade changed
    added_fields: list = field(default_factory=list, compare=False)   # new core fields added on opening
    # read from a format before 7, so the working state (saved matrices, rerecord flags, the
    # spelling list…) came from the database file: its workspace is to be made from it (idea 36)
    workspace_from_file: bool = field(default=False, compare=False)
    # read from an older format (upgraded quietly; saving writes the current one)
    upgraded: bool = field(default=False, compare=False)

    # ---- convenience accessors ---------------------------------------
    def lemma(self, e: Entry) -> str:
        f = self.settings.entry_field("lemma")
        return e.get(f.name) if f else ""

    def gloss(self, e: Entry, lang: str | None = None) -> str:
        f = self.settings.entry_field("gloss")
        return e.get(f.name, lang or self.settings.primary_gloss) if f else ""

    def word_class(self, e: Entry) -> str:
        f = self.settings.entry_field("word-class")
        return e.get(f.name) if f else ""

    def classes(self, e: Entry) -> list[str]:
        """The entry's word class and those above it: what the tag groups' hints are matched with."""
        return self.settings.class_and_above(self.word_class(e))

    def unusual_tags(self, e: Entry, names) -> list[str]:
        """Tags among names that aren't usual for the entry's word class (the soft warning).
        Utterances have no word class: nothing is unusual on them."""
        if is_utterance(e):
            return []
        return self.settings.tags.unusual(self.classes(e), names)

    def entry_by_ref(self, ref: str) -> Entry | None:
        for e in self.entries:
            if e.ref == ref:
                return e
        return None

    def entry_by_id(self, ident: str) -> Entry | None:
        return next((e for e in self.entries if e.id == ident), None) if ident else None

    # ---- utterances --------------------------------------------------
    def list_for(self, item) -> list:
        """The list an entry, utterance or text lives in."""
        if is_text(item):
            return self.texts
        return self.utterances if is_utterance(item) else self.entries

    def utterance_by_ref(self, ref: str) -> Utterance | None:
        return next((u for u in self.utterances if u.ref == ref), None)

    def utterance_by_id(self, ident: str) -> Utterance | None:
        return next((u for u in self.utterances if u.id == ident), None) if ident else None

    def item_by_id(self, ident: str) -> Entry | None:
        """An entry or an utterance, by id (notebook links point at either)."""
        return self.entry_by_id(ident) or self.utterance_by_id(ident)

    def text_by_id(self, ident: str) -> Text | None:
        return next((t for t in self.texts if t.id == ident), None) if ident else None

    def text_by_ref(self, ref: str) -> Text | None:
        return next((t for t in self.texts if t.ref == ref), None)

    def clipped_from(self, text: Text) -> list[Utterance]:
        return [u for u in self.utterances if u.source is not None and u.source.text == text.id]

    def mapping_for(self, text: Text) -> TierMapping:
        return text.tiers if text.tiers is not None else self.settings.tier_mapping

    def text_title(self, text: Text) -> str:
        f = self.settings.text_field("title")
        return text.get(f.name) if f else ""

    def expected_text_name(self, text: Text, extension: str = ".wav") -> str:
        from .filenames import build_text_filename
        return build_text_filename(self, text, extension)

    def items(self) -> list[Entry]:
        """Every entry, then every utterance."""
        return [*self.entries, *self.utterances]

    def all_tokens(self):
        """(entry or utterance, token) for every token in the database."""
        for e in self.items():
            for t in e.tokens:
                yield e, t

    def ref_taken(self, ref: str) -> bool:
        return (self.entry_by_ref(ref) is not None or self.utterance_by_ref(ref) is not None
                or self.text_by_ref(ref) is not None)

    def suggest_utterance_reference(self, letter: str) -> str:
        """Next free reference in an utterance or text category: W001, W002… and on past W999 to W1000."""
        digits = self.settings.ref_digits
        if letter == SEQ:
            return self._next_number()
        highest = 0
        for u in [*self.items(), *self.texts]:
            r = u.ref
            if r.startswith(letter) and r[len(letter):].isdigit():
                highest = max(highest, int(r[len(letter):]))
        return f"{letter}{highest + 1:0{digits}d}"

    def new_utterance(self, ref: str, label: str = "", speaker: str = "", date: str = "") -> Utterance:
        """A new utterance with its one token (no tags: utterances have no word class to take
        defaults from)."""
        return Utterance(ref=nfc(ref), file_gloss=nfc(label),
                         tokens=[Token(speaker=speaker, collected=date)])

    def linked_lemmas(self, u: Utterance) -> list[Entry]:
        return [e for e in (self.entry_by_id(i) for i in u.lemmas) if e is not None]

    def comment_fields(self) -> tuple[list[str], list[str]]:
        """Names of the comment fields: (entry fields, token fields)."""
        s = self.settings
        return ([f.name for f in s.entry_fields if f.is_comment],
                [f.name for f in s.token_fields if f.is_comment])

    def stamp_comments(self, before: Entry | None, after: Entry, date: str):
        """Give comment fields that changed between before and after the date of the change.

        Tokens are matched by id, so a token edited through a copy still counts as itself;
        a new token's comments count as changed.
        """
        if not date:
            return
        if is_text(after):                          # a text's comment fields
            for name in (f.name for f in self.settings.text_fields if f.is_comment):
                if (before.get(name) if before else "") != after.get(name):
                    after.changed[name] = date
            return
        efields, tfields = self.comment_fields()
        for name in efields:
            if (before.get(name) if before else "") != after.get(name):
                after.changed[name] = date
        old = {t.id: t for t in before.tokens} if before else {}
        for t in after.tokens:
            prev = old.get(t.id)
            for name in tfields:
                if (prev.get(name) if prev else "") != t.get(name):
                    t.changed[name] = date

    # ---- references --------------------------------------------------
    def suggest_reference(self, letter: str) -> str:
        """Next free automatic reference in a category, e.g. D010. Never reuses gaps."""
        digits = self.settings.ref_digits
        if letter == SEQ:
            return self._next_number()
        highest = 0
        refs = [e.ref for e in self.entries]
        if self.metadata.wordlist_base == "EACW":   # never a number the EACW has, hidden items included
            from . import wordlists
            refs += [i.number for i in wordlists.get(wordlists.EACW).items]
        for r in refs:
            if r.startswith(letter) and r[len(letter):].isdigit():   # D1000 counts too (the audit, 25 October)
                highest = max(highest, int(r[len(letter):]))
        return f"{letter}{highest + 1:0{digits}d}"

    def _next_number(self) -> str:
        """The next-number scheme (a database built on the CAWL or Swadesh): one sequence for
        lemmas, utterances and texts, after the highest reference that is a number (1701 after the
        CAWL's 1700)."""
        highest = max((int(x.ref) for x in [*self.items(), *self.texts] if x.ref.isdigit()), default=0)
        return f"{highest + 1:0{self.settings.ref_digits}d}"

    # ---- creating things ---------------------------------------------
    def new_entry(self, ref: str, lemma: str = "", gloss: str = "", word_class: str = "",
                  speaker: str = "", date: str = "") -> Entry:
        s = self.settings
        e = Entry(ref=nfc(ref), file_gloss=nfc(gloss))
        if (f := s.entry_field("lemma")):
            e.set(f.name, lemma)
        if (f := s.entry_field("gloss")) and gloss:
            e.set(f.name, gloss, s.primary_gloss)
        if (f := s.entry_field("word-class")) and word_class:
            e.set(f.name, word_class)
        if (f := s.entry_field("stem-type")) and "simple" in f.all_values():
            e.set(f.name, "simple")                       # Stem type starts as simple (Josh, 23 October)
        e.tokens.append(Token(speaker=speaker, collected=date))   # citation token
        return e

    def new_token(self, e: Entry, tags=(), speaker: str = "", date: str = "",
                  defaults: bool | None = None) -> Token:
        """A new token with the given tags plus each open group's default.

        By default a token requested with no tags is a citation token and stays
        tagless; pass defaults=True to pre-select the defaults anyway (e.g. for
        "Add new token", where the tags are picked afterwards).
        """
        tags = list(tags)
        if defaults is None:
            defaults = bool(tags)
        if defaults:
            tags = self.settings.tags.with_defaults(tags, self.classes(e))
        return Token(tags=tags, speaker=speaker, collected=date)

    # ---- soundfiles -------------------------------------------------
    def expected_filename(self, e: Entry, t: Token) -> str:
        from .filenames import build_filename
        return build_filename(self, e, t)

    def duplicate_filenames(self) -> dict[str, list[tuple[Entry, Token]]]:
        seen: dict[str, list] = {}
        for e in self.entries:
            for t in e.tokens:
                seen.setdefault(self.expected_filename(e, t).lower(), []).append((e, t))
        return {k: v for k, v in seen.items() if len(v) > 1}

    def participant_codes(self) -> list[str]:
        return [p.code for p in self.metadata.participants]

