"""Lemmatrix data model: databases, entries, tokens and the tag structure.

Everything here is plain Python with no Qt, so it can be tested on its own.
Reading and writing the XML file lives in storage.py.
"""

from __future__ import annotations

import copy
import datetime as _dt
import unicodedata
import uuid
from dataclasses import dataclass, field

# Characters Windows forbids in file names. Glosses, codes and references
# that end up in sound file names may not contain them.
FORBIDDEN_CHARS = '/\\:*?"<>|'


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
# Tag structure: word class -> groups (nested) -> tags
# --------------------------------------------------------------------------

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

    def leaf_groups(self, path: tuple[str, ...] = ()):
        """Yield (path, group) for every group that directly holds tags, in order."""
        here = path + (self.name,)
        if self.tags:
            yield here, self
        for sub in self.groups:
            yield from sub.leaf_groups(here)

    def default_tag(self) -> Tag | None:
        for t in self.tags:
            if t.default:
                return t
        return None


@dataclass
class WordClass:
    name: str
    groups: list[Group] = field(default_factory=list)


@dataclass
class TagStructure:
    word_classes: list[WordClass] = field(default_factory=list)
    all_classes: list[Group] = field(default_factory=list)

    # ---- lookups -------------------------------------------------------
    def word_class(self, name: str) -> WordClass | None:
        for wc in self.word_classes:
            if wc.name == name:
                return wc
        return None

    def word_class_names(self) -> list[str]:
        return [wc.name for wc in self.word_classes]

    def leaf_groups_for(self, word_class: str | None):
        """(path, group) for every tag group open to a word class, in tag order.

        Word-class groups come first, then the all-classes groups. An unknown
        or empty word class gets only the all-classes groups.
        """
        out = []
        wc = self.word_class(word_class) if word_class else None
        if wc:
            for g in wc.groups:
                out.extend(g.leaf_groups((wc.name,)))
        for g in self.all_classes:
            out.extend(g.leaf_groups(("All classes",)))
        return out

    def all_leaf_groups(self):
        """Every leaf group in the structure, word classes first."""
        out = []
        for wc in self.word_classes:
            for g in wc.groups:
                out.extend(g.leaf_groups((wc.name,)))
        for g in self.all_classes:
            out.extend(g.leaf_groups(("All classes",)))
        return out

    def tags_for(self, word_class: str | None) -> list[tuple[Tag, Group]]:
        return [(t, g) for _, g in self.leaf_groups_for(word_class) for t in g.tags]

    def find(self, word_class: str | None, name: str) -> tuple[Tag, Group] | None:
        for t, g in self.tags_for(word_class):
            if t.name == name:
                return t, g
        return None

    def find_anywhere(self, name: str) -> Tag | None:
        for _, g in self.all_leaf_groups():
            for t in g.tags:
                if t.name == name:
                    return t
        return None

    # ---- ordering and checking ----------------------------------------
    def sort(self, word_class: str | None, names) -> list[str]:
        """Sort tag names into tag order. Unknown names keep their order, last."""
        order = {}
        if self.word_class(word_class or ""):
            order = {t.name: i for i, (t, _) in enumerate(self.tags_for(word_class))}
        # Tags from other word classes (or with no word class given) fall back to
        # the order of the whole structure.
        for _, g in self.all_leaf_groups():
            for t in g.tags:
                order.setdefault(t.name, 1000 + len(order))
        names = list(dict.fromkeys(names))  # drop duplicates, keep first
        known = sorted((n for n in names if n in order), key=order.get)
        unknown = [n for n in names if n not in order]
        return known + unknown

    def conflicts(self, word_class: str | None, names) -> list[str]:
        """Describe tags that break the one-tag-per-group rule or don't belong."""
        problems = []
        seen: dict[int, str] = {}
        for n in names:
            hit = self.find(word_class, n)
            if hit is None:
                problems.append(f'"{n}" is not a tag for {word_class or "entries without a word class"}')
                continue
            _, g = hit
            if id(g) in seen:
                problems.append(f'"{seen[id(g)]}" and "{n}" are both in the group "{g.name}"')
            else:
                seen[id(g)] = n
        return problems

    def with_defaults(self, word_class: str | None, names) -> list[str]:
        """Add each group's default where the group has no tag yet."""
        names = list(names)
        used_groups = set()
        for n in names:
            hit = self.find(word_class, n)
            if hit:
                used_groups.add(id(hit[1]))
        for _, g in self.leaf_groups_for(word_class):
            d = g.default_tag()
            if d and id(g) not in used_groups:
                names.append(d.name)
        return self.sort(word_class, names)

    def file_codes(self, word_class: str | None, names) -> list[str]:
        codes = []
        for n in self.sort(word_class, names):
            hit = self.find(word_class, n)
            code = hit[0].file_code() if hit else n
            if code:
                codes.append(code)
        return codes

    def display(self, word_class: str | None, names) -> str:
        """Short label for a tag combination, e.g. 'PL + GEN'."""
        names = self.sort(word_class, names)
        if not names:
            return "Citation"
        labels = []
        for n in names:
            t = self.find(word_class, n)
            t = t[0] if t else self.find_anywhere(n)
            labels.append(t.display() if t else n)
        return " + ".join(labels)

    def duplicate_codes(self) -> list[str]:
        """Codes shared by two tags open to the same word class."""
        problems = []
        classes = self.word_class_names() + [None]
        for wc in classes:
            seen: dict[str, str] = {}
            for t, _ in self.tags_for(wc):
                c = t.file_code()
                if not c:
                    continue
                if c in seen and seen[c] != t.name:
                    msg = f'{wc or "All classes"}: "{seen[c]}" and "{t.name}" share the code {c}'
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


@dataclass
class RefCategory:
    letter: str
    name: str
    numbering: str = "auto"      # auto or manual


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
    sound_folder: str = "Soundfiles"
    filename_pattern: str = "{language}-{variety}_{reference}_{gloss}_{tags}"
    tag_separator: str = "-"
    auto_update_names: bool = True
    pitch_low: int = 1
    pitch_high: int = 5
    pitch_style: str = "contours"
    play_cell_on_click: bool = False
    matrices: list = field(default_factory=list)      # saved MatrixConfig objects
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

    def list_items(self, f: FieldDef) -> list[ListItem]:
        """The list behind a closed field (the word classes for Word Class)."""
        if f.role == "word-class":
            return [ListItem(n) for n in self.tags.word_class_names()]
        return f.items


# --------------------------------------------------------------------------
# Metadata, entries, tokens
# --------------------------------------------------------------------------

@dataclass
class Person:
    """A researcher or a participant (speaker)."""
    code: str
    name: str = ""
    description: str = ""
    consent: str = ""             # participants: folder with the informed-consent documentation


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
class Database:
    metadata: Metadata = field(default_factory=Metadata)
    settings: Settings = field(default_factory=Settings)
    entries: list[Entry] = field(default_factory=list)
    path: str = ""                                    # where it was loaded from / saved to

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

    def entry_by_ref(self, ref: str) -> Entry | None:
        for e in self.entries:
            if e.ref == ref:
                return e
        return None

    def entry_by_id(self, ident: str) -> Entry | None:
        return next((e for e in self.entries if e.id == ident), None) if ident else None

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
        wc = self.word_class(e)
        tags = list(tags)
        if defaults is None:
            defaults = bool(tags)
        if defaults:
            tags = self.settings.tags.with_defaults(wc, tags)
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
