"""Bulk edit: changing many lemmas or tokens at once (no Qt here).

The window (ui/bulk_window.py) picks the rows and an operation; this module
works out exactly what would change, the "plan", without touching anything:

    Replace      find and replace in one field (plain text or a regular expression)
    Shortcut     a predefined change with a direction (y → j, add tie bars, raise pitch)
    Set value    one value for every row (a field, a tag added or removed, the speaker,
                 the date, or the word class, with its tag conversion)
    Copy         one field into another (overwrite, append, or only where empty)
    Clear        empty a field

A plan lists the changed cells (for the preview), the recordings to rename and
any problems. One problem cancels the whole operation, so nothing is changed
halfway: a pitch already at the top of the display range, a tag the word class
doesn't have, two tokens that would end up with the same tags, a recording whose
new name is taken.

Diacritics: text is compared in decomposed form (NFD), so with "Keep diacritics"
on, y → j turns ỹ into j̃ and ý into j́. With it off, a letter carrying a mark
counts as a different letter and is left alone. Modifier letters (ʰ ʷ ʲ) are
letters of their own and are never touched by a change to the letter before them.
"""

from __future__ import annotations

import copy
import datetime as _dt
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from . import pitch as pitchmod
from .model import (Database, Entry, Group, Tag, TagAction, TagStructure, Token, forbidden_in, nfc, today)

LEMMAS, TOKENS = "lemmas", "tokens"
OVERWRITE, APPEND, ONLY_EMPTY = "overwrite", "append", "empty"
ADD_TAG, REMOVE_TAG = "add", "remove"
CONVERT, NEW, DELETE = "convert", "new", "delete"


class BulkError(Exception):
    """A problem with the operation itself (e.g. an invalid regular expression)."""


class RowError(Exception):
    """A problem with one row, which cancels the whole operation."""


# --------------------------------------------------------------------------
# What can be changed
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Target:
    """A field the operations can change. key matches the grid's column key."""
    key: str
    title: str
    kind: str                 # entry, file-gloss, token, speaker, date, tags
    name: str = ""
    lang: str | None = None
    role: str = ""
    closed: bool = False
    comment: bool = False

    @property
    def text(self) -> bool:
        """Free text: can be replaced, copied and cleared."""
        return self.kind in ("entry", "file-gloss", "token", "speaker", "date") and self.role != "word-class"

    @property
    def ipa(self) -> bool:
        return self.role in ("lemma", "phonetic", "phonemic")


def targets(db: Database, level: str) -> list[Target]:
    s = db.settings
    out = []
    if level == LEMMAS:
        for f in s.entry_fields:
            if f.multilingual:
                for lang in s.gloss_languages:
                    title = f"{f.title} ({lang})" if len(s.gloss_languages) > 1 else f.title
                    out.append(Target(f"{f.name}:{lang}", title, "entry", f.name, lang, f.role, False,
                                      f.is_comment))
            else:
                out.append(Target(f.name, f.title, "entry", f.name, None, f.role, f.closed, f.is_comment))
        out.append(Target("file_gloss", "Gloss in file names", "file-gloss"))
    else:
        for f in s.token_fields:
            out.append(Target("f:" + f.name, f.title, "token", f.name,
                              s.primary_gloss if f.multilingual else None, f.role, f.closed, f.is_comment))
        out += [Target("tags", "Tags", "tags", closed=True), Target("speaker", "Speaker", "speaker"),
                Target("date", "Date", "date")]
    return out


def target(db: Database, level: str, key: str) -> Target:
    for t in targets(db, level):
        if t.key == key:
            return t
    raise BulkError(f"There is no field “{key}” for {level}.")


def get_value(t: Target, e: Entry, tok: Token | None) -> str:
    if t.kind == "entry":
        return e.get(t.name, t.lang)
    if t.kind == "file-gloss":
        return e.file_gloss
    if tok is None:
        return ""
    if t.kind == "token":
        return tok.get(t.name, t.lang)
    if t.kind == "speaker":
        return tok.speaker
    if t.kind == "date":
        return tok.collected
    if t.kind == "tags":
        return ", ".join(tok.tags)
    return ""


def _put(t: Target, e: Entry, tok: Token | None, value: str):
    value = nfc(value).strip()
    if t.role == "pitch":
        value = pitchmod.normalise(value)
    if t.kind == "entry":
        e.set(t.name, value, t.lang, bool(t.lang))
    elif t.kind == "file-gloss":
        e.file_gloss = value
    elif t.kind == "token":
        tok.set(t.name, value, t.lang, bool(t.lang))
    elif t.kind == "speaker":
        tok.speaker = value
    elif t.kind == "date":
        tok.collected = value


def _check_value(db: Database, t: Target, value: str):
    """Values that can't be stored in this field raise RowError."""
    if t.kind in ("file-gloss", "speaker") or t.role == "gloss":
        bad = forbidden_in(value)
        if bad:
            raise RowError(f"{bad} can't be used here, because it can end up in file names")
    if t.kind == "date" and value:
        try:
            d = _dt.date.fromisoformat(value)
        except ValueError:
            raise RowError(f"“{value}” isn't a date (YYYY-MM-DD)") from None
        if d.isoformat() > today():
            raise RowError("The date can't be in the future")
    if t.role == "word-class" and value and value not in db.settings.tags.word_class_names():
        raise RowError(f"“{value}” isn't a word class")


# --------------------------------------------------------------------------
# Text changes
# --------------------------------------------------------------------------

def _is_mark(ch: str) -> bool:
    return unicodedata.combining(ch) != 0


def compile_find(find: str, regex: bool, match_case: bool) -> re.Pattern:
    if not find:
        raise BulkError("Type what to find.")
    pattern = unicodedata.normalize("NFD", find)
    if not regex:
        pattern = re.escape(pattern)
    try:
        return re.compile(pattern, 0 if match_case else re.IGNORECASE)
    except re.error as exc:
        raise BulkError(f"The regular expression isn't valid: {exc}") from None


def replace_text(text: str, rx: re.Pattern, replacement: str, regex: bool = False,
                 keep_diacritics: bool = True) -> str:
    """Replace every match of rx in text.

    Works on the decomposed text, so with keep_diacritics a match on a base letter
    keeps the marks that follow it (ỹ → j̃). Without it, a match followed by a mark
    is skipped: the marked letter counts as a different letter.
    """
    s = unicodedata.normalize("NFD", text or "")
    repl = unicodedata.normalize("NFD", replacement or "")
    out, pos = [], 0
    for m in rx.finditer(s):
        if m.start() == m.end():
            continue                          # empty matches would insert everywhere
        if not keep_diacritics and m.end() < len(s) and _is_mark(s[m.end()]):
            continue
        out.append(s[pos:m.start()])
        if regex:
            try:
                out.append(m.expand(repl))
            except (re.error, IndexError) as exc:
                raise BulkError(f"The replacement isn't valid: {exc}") from None
        else:
            out.append(repl)
        pos = m.end()
    out.append(s[pos:])
    return unicodedata.normalize("NFC", "".join(out))


# Affricates: a stop and the fricative made at the same place.
AFFRICATES = {
    "p": "fɸ", "b": "vβ", "t": "sʃɕθɬ", "d": "zʒʑðɮ", "ʈ": "ʂ", "ɖ": "ʐ", "c": "ç", "ɟ": "ʝ",
    "k": "x", "g": "ɣ", "ɡ": "ɣ", "q": "χ", "ɢ": "ʁ",
}
TIE_BARS = "͜͡"            # tie bar above (t͡ʃ) and below (t͜ʃ)
_STOPS = "".join(AFFRICATES)
_FRICS = "".join(sorted(set("".join(AFFRICATES.values()))))
_MARKS = "[̀-͛͝-͢͠-ͯ᷀-᷿⃐-⃿]*"
_UNTIED = re.compile(f"([{_STOPS}])({_MARKS})([{_FRICS}])")
_TIED = re.compile(f"([{_STOPS}])({_MARKS})[{TIE_BARS}]({_MARKS})([{_FRICS}])")


def add_tie_bars(text: str) -> str:
    """t͡s, d͡ʒ, …: a tie bar between a stop and the fricative at the same place."""
    def fix(m):
        if m.group(3) in AFFRICATES[m.group(1)]:
            return m.group(1) + m.group(2) + "͡" + m.group(3)
        return m.group(0)
    return nfc(_UNTIED.sub(fix, nfc(text)))


def remove_tie_bars(text: str) -> str:
    """Only from affricates: labial-velars like k͡p keep theirs."""
    def fix(m):
        if m.group(4) in AFFRICATES[m.group(1)]:
            return m.group(1) + m.group(2) + m.group(3) + m.group(4)
        return m.group(0)
    return nfc(_TIED.sub(fix, nfc(text)))


def shift_pitch(text: str, step: int, low: int, high: int) -> str:
    """Raise (step 1) or lower (step -1) every pitch digit; past the display range is an error."""
    out = []
    for ch in text or "":
        if ch.isdigit():
            d = int(ch) + step
            if d > high:
                raise RowError(f"{ch} is already the highest pitch of the display range ({low}–{high})"
                               if int(ch) == high else
                               f"{ch} is above the display range ({low}–{high})")
            if d < low:
                raise RowError(f"{ch} is already the lowest pitch of the display range ({low}–{high})"
                               if int(ch) == low else
                               f"{ch} is below the display range ({low}–{high})")
            out.append(str(d))
        else:
            out.append(ch)
    return "".join(out)


@dataclass(frozen=True)
class Direction:
    key: str
    label: str


@dataclass(frozen=True)
class ShortcutDef:
    key: str
    name: str
    roles: tuple[str, ...]                 # the fields it can be used on, by role
    directions: tuple[Direction, ...]
    description: str
    uses_diacritics: bool = False          # the Keep diacritics option applies


SHORTCUTS = (
    ShortcutDef("yj", "y / j", ("lemma", "phonetic", "phonemic"),
                (Direction("y>j", "y → j"), Direction("j>y", "j → y")),
                "Converts every y to j, or every j to y: for data that mixes the two symbols for the "
                "palatal approximant. ʲ and ʸ are left alone.", uses_diacritics=True),
    ShortcutDef("tie", "Tie bar on affricates", ("lemma", "phonetic", "phonemic"),
                (Direction("add", "Add"), Direction("remove", "Remove")),
                "Adds or removes the tie bar between a stop and the fricative made at the same place "
                "(t͡s, d͡ʒ, t͡ʃ, p͡f, k͡x, …). Labial-velars such as k͡p keep theirs. Check the preview: "
                "a stop and fricative in different syllables would be tied too."),
    ShortcutDef("pitch", "Pitch", ("pitch",),
                (Direction("up", "Raise by one"), Direction("down", "Lower by one")),
                "Moves every pitch digit up or down one step. If any ticked token would go past the "
                "display range (Settings → Pitch), nothing is changed."),
)


def shortcut(key: str) -> ShortcutDef:
    for s in SHORTCUTS:
        if s.key == key:
            return s
    raise BulkError(f"There is no shortcut “{key}”.")


def run_shortcut(db: Database, key: str, direction: str, text: str, keep_diacritics: bool = True) -> str:
    if key == "yj":
        find, repl = ("y", "j") if direction == "y>j" else ("j", "y")
        return replace_text(text, re.compile(find), repl, keep_diacritics=keep_diacritics)
    if key == "tie":
        return add_tie_bars(text) if direction == "add" else remove_tie_bars(text)
    if key == "pitch":
        s = db.settings
        return shift_pitch(text, 1 if direction == "up" else -1, s.pitch_low, s.pitch_high)
    raise BulkError(f"There is no shortcut “{key}”.")


# --------------------------------------------------------------------------
# Operations
# --------------------------------------------------------------------------

@dataclass
class Options:
    regex: bool = False
    match_case: bool = False
    keep_diacritics: bool = True
    rename_files: bool = True
    update_comment_dates: bool = False


@dataclass
class Replace:
    target: str
    find: str
    replace: str


@dataclass
class RunShortcut:
    target: str
    shortcut: str
    direction: str


@dataclass
class SetValue:
    target: str
    value: str
    tag_action: str = ADD_TAG                  # tags: add or remove the tag named in value
    conversion: dict[str, TagAction] | None = None   # word class: what happens to the tags


@dataclass
class CopyField:
    source: str
    target: str
    mode: str = OVERWRITE


@dataclass
class ClearField:
    target: str


def describe(op) -> str:
    if isinstance(op, Replace):
        return f"Replace “{op.find}” with “{op.replace}”"
    if isinstance(op, RunShortcut):
        sc = shortcut(op.shortcut)
        d = next((d.label for d in sc.directions if d.key == op.direction), op.direction)
        return f"{sc.name}: {d}"
    if isinstance(op, SetValue):
        if op.target == "tags":
            return f"{'Add' if op.tag_action == ADD_TAG else 'Remove'} the tag {op.value}"
        return f"Set to “{op.value}”" if op.value else "Set to (none)"
    if isinstance(op, CopyField):
        return "Copy field"
    if isinstance(op, ClearField):
        return "Clear field"
    return "Bulk edit"


# --------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------

Row = tuple                                    # (entry, token index) or (entry, None)


def row_key(row: Row):
    e, i = row
    return (id(e), i)


@dataclass
class Change:
    row: Row
    key: str
    old: str
    new: str


@dataclass
class Problem:
    row: Row | None
    key: str
    message: str


@dataclass
class NewTag:
    word_class: str
    group: str
    tag: Tag


@dataclass
class Plan:
    label: str = "Bulk edit"
    level: str = TOKENS
    changes: list[Change] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    pairs: list[tuple[Entry, Entry]] = field(default_factory=list)   # (entry, changed copy)
    renames: list[tuple[Path, Path]] = field(default_factory=list)   # in the order to do them
    missing: list[str] = field(default_factory=list)     # recordings not on disk: names left as they are
    stale: int = 0                                       # names left out of date (renaming off)
    comments: int = 0                                    # comment fields changed
    comment_dates: bool = False                          # those comments will be dated
    new_tags: list[NewTag] = field(default_factory=list)
    new_values: list[tuple[str, str]] = field(default_factory=list)   # (closed field name, value) to list
    tags_converted: int = 0
    speaker_changed: bool = False

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def rows_changed(self) -> int:
        return len({row_key(c.row) for c in self.changes})

    def changes_by_row(self) -> dict:
        return {(row_key(c.row), c.key): c for c in self.changes}

    def problems_by_row(self) -> dict:
        return {(row_key(p.row), p.key): p for p in self.problems if p.row is not None}


def structure_with(ts: TagStructure, new_tags: list[NewTag]) -> TagStructure:
    """A copy of the tag structure with the conversion's new tags added."""
    if not new_tags:
        return ts
    ts = copy.deepcopy(ts)
    for nt in new_tags:
        wc = ts.word_class(nt.word_class)
        if wc is None:
            continue
        group = next((g for _, g in (x for top in wc.groups for x in top.leaf_groups())
                      if g.name == nt.group), None)
        if group is None:
            group = next((g for g in wc.groups if g.name == nt.group), None)
        if group is None:
            group = Group(nt.group or "New tags")
            wc.groups.append(group)
        if not any(t.name == nt.tag.name for t in group.tags):
            group.tags.append(copy.copy(nt.tag))
    return ts


def install_new_tags(db: Database, new_tags: list[NewTag]):
    """Add a conversion's new tags to the database's tag structure (done when applying)."""
    db.settings.tags = structure_with(db.settings.tags, new_tags)


def _db_with(db: Database, ts: TagStructure) -> Database:
    """The database seen through another tag structure (for file names), without copying entries."""
    if ts is db.settings.tags:
        return db
    view = copy.copy(db)
    view.settings = copy.copy(db.settings)
    view.settings.tags = ts
    return view


# ---- word class changes ---------------------------------------------------

def all_classes_tag(ts: TagStructure, name: str) -> bool:
    return any(t.name == name for _, g in ts.leaf_groups_for(None) for t in g.tags)


@dataclass
class Stranded:
    """A tag in use that the new word class doesn't keep automatically."""
    name: str
    from_class: str
    group: str
    tokens: int
    suggested: TagAction


def stranded_tags(db: Database, entries, new_wc: str) -> tuple[list[Stranded], dict[str, int]]:
    """Tags of the entries' tokens that need a decision, and the all-classes tags that are kept.

    Lemmas already of the new class are left out. A tag the new class also has (by name) is
    suggested as Convert to that tag; the rest are left for the user to choose.
    """
    ts = db.settings.tags
    need: dict[str, Stranded] = {}
    kept: dict[str, int] = {}
    for e in entries:
        old = db.word_class(e)
        if old == new_wc:
            continue
        for t in e.tokens:
            for name in t.tags:
                if all_classes_tag(ts, name):
                    kept[name] = kept.get(name, 0) + 1
                    continue
                if name not in need:
                    hit = ts.find(old or None, name)
                    group = hit[1].name if hit else ""
                    same = ts.find(new_wc or None, name)
                    need[name] = Stranded(name, old, group, 0,
                                          TagAction(CONVERT, name) if same else TagAction())
                need[name].tokens += 1
    order = {n: i for i, n in enumerate(ts.sort(None, list(need)))}
    return sorted(need.values(), key=lambda s: order.get(s.name, 0)), kept


def check_conversion(db: Database, new_wc: str, actions: dict[str, TagAction],
                     stranded: list[Stranded]) -> list[str]:
    """Problems with the choices in the conversion dialogue (before anything is planned)."""
    ts = db.settings.tags
    msgs = []
    new_codes: dict[str, str] = {}
    for s in stranded:
        a = actions.get(s.name)
        if a is None or not a.kind:
            msgs.append(f"Choose what happens to {s.name}.")
            continue
        if a.kind == CONVERT:
            if not a.tag or ts.find(new_wc or None, a.tag) is None:
                msgs.append(f"{s.name}: choose a tag of {new_wc or '(none)'} to convert it to.")
        elif a.kind == NEW:
            name = nfc(a.tag).strip()
            if not name:
                msgs.append(f"{s.name}: give the new tag a name.")
            elif "," in name:
                msgs.append(f"{s.name}: tag names can't contain commas.")
            elif ts.find(new_wc or None, name) is not None:
                msgs.append(f"{s.name}: {new_wc} already has a tag called {name}; choose Convert to.")
            if forbidden_in(a.code):
                msgs.append(f"{s.name}: {forbidden_in(a.code)} can't be used in a code (file names).")
            if name in new_codes and new_codes[name] != a.code:
                msgs.append(f"The new tag {name} is given two different codes.")
            new_codes.setdefault(name, a.code)
            if not new_wc:
                msgs.append("New tags can only be made in a word class, not for (none).")
    return list(dict.fromkeys(msgs))


def new_tags_for(new_wc: str, actions: dict[str, TagAction]) -> list[NewTag]:
    out, seen = [], set()
    for a in actions.values():
        if a.kind == NEW and a.tag and a.tag not in seen:
            seen.add(a.tag)
            out.append(NewTag(new_wc, a.group or "New tags", Tag(nfc(a.tag).strip(), nfc(a.code).strip())))
    return out


def convert_tags(ts: TagStructure, old_wc: str, new_wc: str, tags: list[str],
                 actions: dict[str, TagAction]) -> list[str]:
    """One token's tags after its lemma changes from old_wc to new_wc."""
    out = []
    for name in tags:
        if all_classes_tag(ts, name):
            out.append(name)
            continue
        a = actions.get(name)
        if a is None or not a.kind:
            if ts.find(new_wc or None, name):
                out.append(name)              # the new class has it too
                continue
            raise RowError(f"No choice made for the tag {name}")
        if a.kind in (CONVERT, NEW):
            out.append(nfc(a.tag).strip())
    return ts.sort(new_wc or None, out)


# ---- building a plan ------------------------------------------------------

def new_duplicates(orig: Entry, after: Entry) -> list[tuple[int, int]]:
    """Pairs of token indexes (in after) with the same tags, that didn't have the same tags before.

    Tokens are matched by id, so pairs that were already duplicates aren't blamed on the change.
    """
    before = {t.id: frozenset(t.tags) for t in orig.tokens}
    seen: dict[frozenset, int] = {}
    dups = []
    for i, t in enumerate(after.tokens):
        k = frozenset(t.tags)
        if k in seen:
            j = seen[k]
            a, b = after.tokens[j], t
            if not (a.id in before and b.id in before and before[a.id] == before[b.id]):
                dups.append((j, i))
        else:
            seen[k] = i
    return dups


def plan(db: Database, level: str, rows: list[Row], op, opts: Options | None = None,
         folder: Path | None = None, on_disk: set[str] | None = None) -> Plan:
    """Work out what op would change in rows, without changing anything.

    rows: (entry, token index) for tokens, (entry, None) for lemmas, in the grid's order.
    folder, on_disk: the sound folder and the names in it (for renaming recordings).
    """
    opts = opts or Options()
    p = Plan(label=f"Bulk edit: {describe(op)}", level=level)
    tgt = target(db, level, op.target)
    src = target(db, level, op.source) if isinstance(op, CopyField) else None
    ts = db.settings.tags
    rx = None
    if isinstance(op, Replace):
        if not tgt.text:
            raise BulkError(f"{tgt.title} can't be changed with Replace.")
        rx = compile_find(op.find, opts.regex, opts.match_case)
    if isinstance(op, RunShortcut):
        sc = shortcut(op.shortcut)
        if tgt.role not in sc.roles:
            raise BulkError(f"{sc.name} can't be used on {tgt.title}.")
    if isinstance(op, CopyField):
        if src.key == tgt.key:
            raise BulkError("Choose two different fields.")
        if not (src.text and tgt.text):
            raise BulkError("Only text fields can be copied.")
    if isinstance(op, ClearField) and (tgt.kind == "tags" or tgt.role == "word-class"):
        raise BulkError(f"{tgt.title} can't be cleared here: use Set value.")
    word_class_change = isinstance(op, SetValue) and tgt.role == "word-class"
    if word_class_change:
        new_wc = op.value
        p.new_tags = new_tags_for(new_wc, op.conversion or {})
        ts = structure_with(ts, p.new_tags)
    if isinstance(op, SetValue) and tgt.kind == "tags":
        if not op.value or ts.find_anywhere(op.value) is None:
            raise BulkError("Choose a tag.")
    if isinstance(op, SetValue) and tgt.kind != "tags":
        try:
            _check_value(db, tgt, op.value)
        except RowError as exc:
            raise BulkError(str(exc)) from None

    afters: dict[int, Entry] = {}
    originals: dict[int, Entry] = {}
    order: list[int] = []

    def after_of(e: Entry) -> Entry:
        if id(e) not in afters:
            afters[id(e)] = e.copy()
            originals[id(e)] = e
            order.append(id(e))
        return afters[id(e)]

    for row in rows:
        e, i = row
        ae = after_of(e)
        tok = ae.tokens[i] if i is not None else None
        if level == TOKENS and tok is None:
            continue
        old = get_value(tgt, e, e.tokens[i] if i is not None else None)
        try:
            if isinstance(op, Replace):
                new = replace_text(old, rx, op.replace, opts.regex, opts.keep_diacritics)
            elif isinstance(op, RunShortcut):
                new = run_shortcut(db, op.shortcut, op.direction, old, opts.keep_diacritics)
            elif isinstance(op, CopyField):
                value = get_value(src, e, e.tokens[i] if i is not None else None)
                if op.mode == ONLY_EMPTY:
                    new = old if old.strip() else value
                elif op.mode == APPEND:
                    new = f"{old} {value}".strip() if value else old
                else:
                    new = value
            elif isinstance(op, ClearField):
                new = ""
            elif isinstance(op, SetValue) and tgt.kind == "tags":
                wc = db.word_class(e)
                names = list(tok.tags)
                if op.tag_action == REMOVE_TAG:
                    names = [n for n in names if n != op.value]
                elif op.value not in names:
                    hit = ts.find(wc or None, op.value)
                    if hit is None:
                        raise RowError(f"{wc or 'A lemma without a word class'} has no tag {op.value}")
                    group = hit[1]
                    names = [n for n in names if not any(t.name == n for t in group.tags)] + [op.value]
                tok.tags = ts.sort(wc or None, names)
                new = ", ".join(tok.tags)
            else:                               # SetValue on a field
                new = op.value
            new = nfc(new)
            if tgt.role == "pitch":
                new = pitchmod.normalise(new)
            if tgt.kind != "tags":
                _check_value(db, tgt, new)
        except RowError as exc:
            p.problems.append(Problem(row, tgt.key, str(exc)))
            continue
        if new.strip() == old.strip():
            continue
        if tgt.kind != "tags":
            _put(tgt, ae, tok, new)
        if word_class_change:
            old_wc = db.word_class(e)
            for k, t in enumerate(ae.tokens):
                try:
                    converted = convert_tags(ts, old_wc, new_wc, t.tags, op.conversion or {})
                except RowError as exc:
                    p.problems.append(Problem(row, tgt.key, f"{e.ref}: {exc}"))
                    continue
                if converted != t.tags:
                    p.tags_converted += 1
                t.tags = converted
                for msg in ts.conflicts(new_wc or None, t.tags):
                    p.problems.append(Problem(row, tgt.key, f"{e.ref}: {msg}"))
        if tgt.closed and tgt.role != "word-class" and tgt.kind == "entry" and new:
            fdef = db.settings.entry_field(tgt.name)
            if fdef and new not in fdef.all_values() and (tgt.name, new) not in p.new_values:
                p.new_values.append((tgt.name, new))
        if tgt.closed and tgt.kind == "token" and new:
            fdef = db.settings.token_field(tgt.name)
            if fdef and new not in fdef.all_values() and (tgt.name, new) not in p.new_values:
                p.new_values.append((tgt.name, new))
        if tgt.kind == "speaker":
            p.speaker_changed = True
        if tgt.comment:
            p.comments += 1
        p.changes.append(Change(row, tgt.key, old, new))

    # Tokens of one lemma that would end up with the same tags
    wcf = db.settings.entry_field("word-class")
    for eid in order:
        e, ae = originals[eid], afters[eid]
        wc = ae.get(wcf.name) if wcf else ""
        for a, b in new_duplicates(e, ae):
            label = ts.display(wc or None, ae.tokens[a].tags)
            row = (e, b) if level == TOKENS else (e, None)
            p.problems.append(Problem(row, tgt.key, f"{e.ref}: two tokens would both be {label}"))

    p.pairs = [(originals[i], afters[i]) for i in order if originals[i] != afters[i]]
    p.comment_dates = bool(p.comments) and opts.update_comment_dates
    _plan_renames(_db_with(db, ts), p, opts, folder, on_disk)
    return p


def plan_edit(db: Database, entry: Entry, after: Entry, opts: Options,
              folder: Path | None = None, on_disk: set[str] | None = None,
              new_tags: list[NewTag] | None = None) -> Plan:
    """A plan for one entry changed some other way (e.g. in the entry dialogue): its renames
    and problems, like a bulk edit's."""
    p = Plan(label=f"Edit {entry.ref}", level=LEMMAS)
    p.new_tags = list(new_tags or [])
    ts = structure_with(db.settings.tags, p.new_tags)
    wcf = db.settings.entry_field("word-class")
    wc = after.get(wcf.name) if wcf else ""
    for t in after.tokens:
        for msg in ts.conflicts(wc or None, t.tags):
            p.problems.append(Problem((entry, None), "", f"{entry.ref}: {msg}"))
    for a, b in new_duplicates(entry, after):
        p.problems.append(Problem((entry, None), "", f"{entry.ref}: two tokens would both be "
                                                     f"{ts.display(wc or None, after.tokens[a].tags)}"))
    p.pairs = [(entry, after)]
    _plan_renames(_db_with(db, ts), p, opts, folder, on_disk)
    return p


def _plan_renames(db: Database, p: Plan, opts: Options, folder: Path | None, on_disk: set[str] | None):
    """Recordings whose names change: renamed (in a safe order) or left out of date."""
    if folder is None:
        return
    on_disk = on_disk or set()
    disk_lower = {n.lower() for n in on_disk}
    moves: list[tuple[str, str, Token, Entry]] = []
    for orig, after in p.pairs:
        for t in after.tokens:
            if not t.file:
                continue
            new = db.expected_filename(after, t)
            if new == t.file:
                continue
            if not opts.rename_files:
                p.stale += 1
                continue
            if t.file not in on_disk:
                p.missing.append(t.file)
                continue
            moves.append((t.file, new, t, orig))
    sources = {m[0].lower() for m in moves}
    targets_seen: dict[str, str] = {}
    for old, new, t, orig in moves:
        low = new.lower()
        if low in targets_seen:
            p.problems.append(Problem((orig, None), "", f"{old} and {targets_seen[low]} would both be "
                                                        f"renamed {new}"))
        targets_seen[low] = old
        if low in disk_lower and low not in sources and low != old.lower():
            p.problems.append(Problem((orig, None), "", f"{old} can't be renamed {new}: a file of that "
                                                        "name is already in the sound folder"))
    # Order: a recording moves out of a name before another moves into it.
    pending = list(moves)
    ordered = []
    while pending:
        busy = {m[0].lower() for m in pending}
        ready = [m for m in pending if m[1].lower() not in busy or m[1].lower() == m[0].lower()]
        if not ready:
            p.problems.append(Problem(None, "", "Some recordings would swap names with each other. "
                                                "Do the change in two steps."))
            break
        for m in ready:
            pending.remove(m)
            ordered.append(m)
    for old, new, t, _ in ordered:
        t.file = new
        p.renames.append((folder / old, folder / new))


def summary(p: Plan, level: str) -> list[str]:
    """The preview's lines, besides the count."""
    lines = []
    if p.renames:
        lines.append(f"{len(p.renames)} recording{'s' if len(p.renames) != 1 else ''} will be renamed")
    if p.stale:
        lines.append(f"{p.stale} sound file name{'s' if p.stale != 1 else ''} will be out of date "
                     "(Rename sound files is off)")
    if p.missing:
        lines.append(f"{len(p.missing)} recording{'s' if len(p.missing) != 1 else ''} aren't in the sound "
                     "folder: their names are left as they are")
    if p.comments:
        if p.comment_dates:
            lines.append(f"{p.comments} comment{'s' if p.comments != 1 else ''} will be dated "
                         "with the session's date and go into that day's notebook record")
        else:
            lines.append(f"{p.comments} comment{'s' if p.comments != 1 else ''} will change; "
                         "their dates stay as they are")
    if p.tags_converted:
        lines.append(f"{p.tags_converted} token{'s' if p.tags_converted != 1 else ''} get converted tags")
    for nt in p.new_tags:
        lines.append(f"New tag {nt.tag.name} ({nt.tag.code or 'no code'}) in {nt.word_class} › {nt.group}")
    for name, value in p.new_values:
        lines.append(f"“{value}” is added to the {name} list")
    if p.speaker_changed:
        lines.append("The speaker inside the recordings' own metadata isn't changed")
    return lines
