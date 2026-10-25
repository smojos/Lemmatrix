# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Column filters for the lemma list and All data (no Qt here).

Every column filter is one of:
    None           show all
    Blanks()       empty values only
    NonBlanks()    non-empty values only
    TextFilter     "Filter for…" on open fields
    ChoiceFilter   "Choose…" on closed fields (lists, word class, tags)
"""

from __future__ import annotations

import functools
import re
import unicodedata
from dataclasses import dataclass, field

ANYWHERE, WHOLE, START, END, REGEX = "anywhere", "whole", "start", "end", "regex"
ANY, NONE, EXACTLY = "any", "none", "exactly"

# In the tag filter's Choose list: stands for "no tags at all" (the citation token).
CITATION_ITEM = "Citation (no tags)"


def fold_diacritics(text: str) -> str:
    """Remove combining marks and modifier letters (ʰ ʷ ʲ ː …), keep base letters. Plain ASCII
    has none, so it comes back as it is; anything else is remembered (the quick search folds
    every cell of every row on each keystroke: at 58,000 tokens that took seconds; 25 October)."""
    if not text or text.isascii():
        return text
    return _fold(text)


def search_form(text: str) -> str:
    """A cell's text as the quick search compares it: diacritics folded, any case."""
    if not text:
        return ""
    if text.isascii():
        return text.lower()
    return _search_form(text)


@functools.lru_cache(maxsize=1 << 18)
def _search_form(text: str) -> str:
    return _fold(text).casefold()


@functools.lru_cache(maxsize=1 << 18)
def _fold(text: str) -> str:
    out = []
    for ch in unicodedata.normalize("NFD", text):
        if unicodedata.combining(ch):
            continue
        if unicodedata.category(ch) == "Lm":       # modifier letters: ʰ ʷ ʲ ˠ ˤ ː ˑ ʼ …
            continue
        out.append(ch)
    return unicodedata.normalize("NFC", "".join(out))


@dataclass
class Blanks:
    def describe(self) -> str:
        return "Blanks"


@dataclass
class NonBlanks:
    def describe(self) -> str:
        return "Non-blanks"


@dataclass
class Flagged:
    """Rows a column flags (e.g. Soundfile: marked to be recorded again)."""
    label: str = "Flagged"

    def describe(self) -> str:
        return self.label


@dataclass
class TextFilter:
    text: str
    mode: str = ANYWHERE
    match_case: bool = False
    match_diacritics: bool = False

    def _prep(self, s: str) -> str:
        if not self.match_diacritics:
            s = fold_diacritics(s)
        if not self.match_case:
            s = s.casefold()
        return s

    def compiled(self):
        if self.mode != REGEX:
            return None
        flags = 0 if self.match_case else re.IGNORECASE
        return re.compile(self.text, flags)

    def matches(self, value: str) -> bool:
        value = value or ""
        if self.mode == REGEX:
            try:
                rx = self.compiled()
            except re.error:
                return False
            target = value if self.match_diacritics else fold_diacritics(value)
            return bool(rx.search(target))
        v, t = self._prep(value), self._prep(self.text)
        if self.mode == WHOLE:
            return v == t
        if self.mode == START:
            return v.startswith(t)
        if self.mode == END:
            return v.endswith(t)
        return t in v

    def describe(self) -> str:
        how = {ANYWHERE: "contains", WHOLE: "is", START: "starts with", END: "ends with",
               REGEX: "matches"}[self.mode]
        return f'{how} “{self.text}”'


@dataclass
class ChoiceFilter:
    selected: set = field(default_factory=set)
    mode: str = ANY                 # any, none, exactly (exactly: tags only)

    def matches_values(self, values: set, unmarked: set = frozenset()) -> bool:
        """values: the item(s) a row has (one for a list field, several for tags)."""
        if self.mode == NONE:
            return not (values & self.selected)
        if self.mode == EXACTLY:
            marked_vals = values - unmarked
            marked_sel = self.selected - unmarked
            return self.selected <= values and marked_vals == marked_sel
        return bool(values & self.selected)

    def describe(self) -> str:
        how = {ANY: "any of", NONE: "none of", EXACTLY: "exactly"}[self.mode]
        items = ", ".join(sorted(self.selected))
        return f"{how} {items}" if items else how


def matches(flt, value, unmarked: set = frozenset()) -> bool:
    """Apply a column filter. value is a string, or a set/list for multi-valued columns."""
    if flt is None:
        return True
    multi = isinstance(value, (set, frozenset, list, tuple))
    empty = (not value) if multi else not (value or "").strip()
    if isinstance(flt, Blanks):
        return empty
    if isinstance(flt, NonBlanks):
        return not empty
    if isinstance(flt, TextFilter):
        if multi:
            return any(flt.matches(v) for v in value)
        return flt.matches(value)
    if isinstance(flt, ChoiceFilter):
        vals = set(value) if multi else ({value} if value else set())
        if multi and not vals:
            vals = {CITATION_ITEM}
        return flt.matches_values(vals, unmarked)
    return True


# ---- kept in the workspace (idea 36): a column filter as JSON and back --------------------------

def encode(flt) -> dict | None:
    """A column filter as a plain dict (for the workspace file); None for none."""
    if isinstance(flt, Blanks):
        return {"kind": "blanks"}
    if isinstance(flt, NonBlanks):
        return {"kind": "non-blanks"}
    if isinstance(flt, Flagged):
        return {"kind": "flagged", "label": flt.label}
    if isinstance(flt, TextFilter):
        return {"kind": "text", "text": flt.text, "mode": flt.mode, "case": flt.match_case,
                "diacritics": flt.match_diacritics}
    if isinstance(flt, ChoiceFilter):
        return {"kind": "choice", "selected": sorted(flt.selected), "mode": flt.mode}
    return None


def decode(d):
    """encode()'s dict back into a filter; None if it can't be read."""
    if not isinstance(d, dict):
        return None
    kind = d.get("kind")
    if kind == "blanks":
        return Blanks()
    if kind == "non-blanks":
        return NonBlanks()
    if kind == "flagged":
        return Flagged(str(d.get("label", "Flagged")))
    if kind == "text" and isinstance(d.get("text"), str):
        mode = d.get("mode", ANYWHERE)
        return TextFilter(d["text"], mode if mode in (ANYWHERE, WHOLE, START, END, REGEX) else ANYWHERE,
                          bool(d.get("case")), bool(d.get("diacritics")))
    if kind == "choice" and isinstance(d.get("selected"), list):
        mode = d.get("mode", ANY)
        return ChoiceFilter({str(x) for x in d["selected"]}, mode if mode in (ANY, NONE, EXACTLY) else ANY)
    return None
