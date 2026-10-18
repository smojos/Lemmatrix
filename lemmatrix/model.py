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
# that end up in sound file names may not contain them.
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


@dataclass
class Tag:
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
class Group:
    name: str
    tags: list[Tag] = field(default_factory=list)
    groups: list["Group"] = field(default_factory=list)
    usual: list[str] = field(default_factory=list)    # word classes it's usual for ([]: its parent's)
    utterances_only: bool = False                      # a rule: its tags go on utterances only (subgroups too)

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
class TagStructure:
    groups: list[Group] = field(default_factory=list)

    # ---- lookups -------------------------------------------------------
    def leaf_groups(self) -> list[tuple[tuple[str, ...], Group]]:
        """(path, group) for every group that holds tags, in tag order."""
        return [x for g in self.groups for x in g.leaf_groups()]

    def all_groups(self):
        for g in self.groups:
            yield from g.walk()

    def tags(self) -> list[tuple[Tag, Group]]:
        return [(t, g) for _, g in self.leaf_groups() for t in g.tags]

    def find(self, name: str) -> tuple[Tag, Group] | None:
        for t, g in self.tags():
            if t.name == name:
                return t, g
        return None

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
        out: dict[int, tuple[str, ...]] = {}

        def walk(g: Group, inherited: tuple[str, ...]):
            mine = tuple(g.usual) or inherited
            out[id(g)] = mine
            for sub in g.groups:
                walk(sub, mine)
        for g in self.groups:
            walk(g, ())
        return out

    def only_map(self) -> dict[int, bool]:
        """id(group) -> whether it is for utterances only (marked on it or on a group above it)."""
        out: dict[int, bool] = {}

        def walk(g: Group, inherited: bool):
            mine = g.utterances_only or inherited
            out[id(g)] = mine
            for sub in g.groups:
                walk(sub, mine)
        for g in self.groups:
            walk(g, False)
        return out

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
        order = {t.name: i for i, (t, _) in enumerate(self.tags())}
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

    def duplicate_names(self) -> list[str]:
        seen: dict[str, int] = {}
        for t, _ in self.tags():
            seen[t.name] = seen.get(t.name, 0) + 1
        return [n for n, k in seen.items() if k > 1]

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


@dataclass
class FieldDef:
    name: str                    # XML element name, no spaces
    label: str = ""
    role: str = ""               # lemma, gloss, word-class, phonetic, phonemic, pitch, translation
    closed: bool = False         # values come from a list kept in settings
    items: list[ListItem] = field(default_factory=list)

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
        return self.role in ("lemma", "gloss", "word-class", "phonetic", "phonemic", "pitch",
                             "translation")

    def all_values(self) -> list[str]:
        return [i.name for top in self.items for i in top.walk()]

    def add_value(self, value: str):
        if value and value not in self.all_values():
            self.items.append(ListItem(value))


LEMMAS, UTTERANCES = "lemmas", "utterances"      # what a reference category is for


@dataclass
class RefCategory:
    letter: str
    name: str
    numbering: str = "auto"      # auto or manual
    kind: str = LEMMAS           # lemmas or utterances (U, W, X, Y, Z by default)


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
    old_sound_folder: str = ""   # format 3 and before: the settable sound folder (read, never written)
    filename_pattern: str = "{language}-{variety}_{reference}_{gloss}_{tags}"
    utterance_pattern: str = "{language}-{variety}_{reference}_{label}"   # utterances: no tags
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

    def token_field(self, role_or_name: str) -> FieldDef | None:
        for f in self.token_fields:
            if f.role == role_or_name or f.name == role_or_name:
                return f
        return None

    def categories(self, kind: str = LEMMAS) -> list[RefCategory]:
        return [c for c in self.ref_categories if c.kind == kind]

    def category(self, ref: str) -> RefCategory | None:
        """The category a reference belongs to, by its letters (W001 -> W)."""
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
class Person:
    """A researcher or a participant (speaker)."""
    code: str
    name: str = ""
    description: str = ""
    consent: str = ""             # participants: the file documenting informed consent


Participant = Person              # the older name


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
class Utterance(Entry):
    """A one-off sentence or phrase with no lemma: one reference, one token (one transcription,
    one recording). file_gloss is its file label ("hare ran"), copied into its file name;
    lemmas are the ids of the lemmas it is linked to by hand."""
    lemmas: list[str] = field(default_factory=list)

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
class Database:
    metadata: Metadata = field(default_factory=Metadata)
    settings: Settings = field(default_factory=Settings)
    entries: list[Entry] = field(default_factory=list)
    utterances: list[Utterance] = field(default_factory=list)
    path: str = ""                                    # where it was loaded from / saved to
    load_notes: list = field(default_factory=list, compare=False)   # e.g. what an upgrade changed

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
    def list_for(self, item: Entry) -> list:
        """The list an entry or utterance lives in."""
        return self.utterances if is_utterance(item) else self.entries

    def utterance_by_ref(self, ref: str) -> Utterance | None:
        return next((u for u in self.utterances if u.ref == ref), None)

    def utterance_by_id(self, ident: str) -> Utterance | None:
        return next((u for u in self.utterances if u.id == ident), None) if ident else None

    def item_by_id(self, ident: str) -> Entry | None:
        """An entry or an utterance, by id (notebook links point at either)."""
        return self.entry_by_id(ident) or self.utterance_by_id(ident)

    def items(self) -> list[Entry]:
        """Every entry, then every utterance."""
        return [*self.entries, *self.utterances]

    def all_tokens(self):
        """(entry or utterance, token) for every token in the database."""
        for e in self.items():
            for t in e.tokens:
                yield e, t

    def ref_taken(self, ref: str) -> bool:
        return self.entry_by_ref(ref) is not None or self.utterance_by_ref(ref) is not None

    def suggest_utterance_reference(self, letter: str) -> str:
        """Next free reference in an utterance category: W001, W002… and on past W999 to W1000."""
        digits = self.settings.ref_digits
        highest = 0
        for u in self.items():
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
        highest = 0
        for e in self.entries:
            r = e.ref
            if r.startswith(letter) and r[len(letter):].isdigit() and len(r) - len(letter) == digits:
                highest = max(highest, int(r[len(letter):]))
        return f"{letter}{highest + 1:0{digits}d}"

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

    # ---- sound files -------------------------------------------------
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

    def researcher_codes(self) -> list[str]:
        return [p.code for p in self.metadata.researchers]
