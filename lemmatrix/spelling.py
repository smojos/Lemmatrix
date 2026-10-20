# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Spelling: English translations and glosses checked against two word lists (no Qt here).

A word is spelled correctly if either knows it:

    - pyspellchecker (MIT licence, offline): general English, little words included (the, of,
      and), but American spellings only. It also suggests corrections (recieve -> receive).
    - lemminflect (already used for predicted translations): nouns, verbs and adjectives,
      British spellings included (colour, favour, recognise), with all their inflections.

plus the database's own word list (Sample variety, people's names, local terms), kept in its
settings as <spelling><word>…</word></spelling>, so it travels with the database.

Not checked: anything in brackets, words with digits, words in capitals (1SG, PL, f2) or with
a capital inside them (xH), single
letters other than a and I, and words with letters outside English (IPA, Arabic): those are
glossing conventions or transcriptions, not English spelling. Only the English translation
and the English gloss are checked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from .model import Database, Entry, nfc

LANG = "en"

try:
    from spellchecker import SpellChecker as _SpellChecker
except ImportError:                          # pragma: no cover - pyspellchecker is in requirements.txt
    _SpellChecker = None
try:
    from lemminflect import getAllInflections as _inflections, getAllLemmas as _lemmas
except ImportError:                          # pragma: no cover
    _inflections = _lemmas = None

_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*(?:-[^\W\d_]+(?:['’][^\W\d_]+)*)*|[\w'’-]*\d[\w'’-]*")
_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_POSSESSIVE = re.compile(r"['’]s?$", re.IGNORECASE)
_ENGLISH = re.compile(r"^[a-z'’-]+$")
_checker = None


def available() -> bool:
    return _SpellChecker is not None or _lemmas is not None


def _speller():
    global _checker
    if _checker is None and _SpellChecker is not None:
        _checker = _SpellChecker(language="en", distance=2)
    return _checker


@lru_cache(maxsize=100000)
def _known_word(w: str) -> bool:
    """w: lower case, one word (no hyphen)."""
    sp = _speller()
    if sp is not None and w in sp:
        return True
    if _lemmas is not None and (_lemmas(w) or _inflections(w)):
        return True
    if w.endswith(("'s", "’s")):                 # the goat's
        return _known_word(w[:-2])
    if w.endswith(("s'", "s’")):                 # the goats'
        return _known_word(w[:-1])
    return False


def _checked(word: str) -> bool:
    """Whether a word is checked at all (not a glossing convention, number or transcription)."""
    if any(ch.isdigit() for ch in word):
        return False
    letters = [ch for ch in word if ch.isalpha()]
    if len(letters) >= 2 and all(ch.isupper() for ch in letters):    # PL, 1SG, NOUN
        return False
    if any(ch.isupper() for ch in letters[1:]) and not all(ch.isupper() for ch in letters):
        return False                                                  # codes like xH
    low = word.lower()
    if len(low) == 1:
        return False
    return bool(_ENGLISH.match(low.replace("’", "'")))


class Checker:
    """Checks words against the dictionaries and the database's word list."""

    def __init__(self, words=()):
        self.set_words(words)

    def set_words(self, words):
        self.words = {nfc(w).lower() for w in words if w}

    def known(self, word: str) -> bool:
        low = nfc(word).lower().replace("’", "'")
        if low in self.words or not _checked(word):
            return True
        if _known_word(low):
            return True
        if "-" in low:                           # mother-in-law: each part
            return all(not p or p in self.words or _known_word(p) for p in low.split("-"))
        return False

    def misspelled(self, text: str) -> list[tuple[int, int, str]]:
        """(start, end, word) of each unknown word in text, in order."""
        if not text:
            return []
        hidden = _BRACKETS.sub(lambda m: " " * len(m.group()), text)
        out = []
        for m in _WORD.finditer(hidden):
            w = m.group()
            base = _POSSESSIVE.sub("", w) or w         # goatt's: the word is goatt
            if not self.known(base):
                out.append((m.start(), m.start() + len(base), base))
        return out

    def suggestions(self, word: str, limit: int = 6, thorough: bool = False) -> list[str]:
        """Corrections, most likely first, in the word's own capitalisation.

        Quick (the default): words one change away (a letter added, dropped, changed or two
        swapped), which catches most typos at once. thorough: two changes away too, which can
        take a second for a word with nothing near it (Check spelling's chosen word).
        """
        out = list(_suggest(word.lower(), thorough))[:limit]
        if word[:1].isupper():
            out = [w[:1].upper() + w[1:] for w in out]
        return out


@lru_cache(maxsize=5000)
def _suggest(low: str, thorough: bool) -> tuple[str, ...]:
    sp = _speller()
    if sp is None:
        return ()
    freq = sp.word_usage_frequency
    near = sp.known(sp.edit_distance_1(low))
    if thorough and not near:
        near = sp.known(sp.edit_distance_2(low))
    return tuple(w for w in sorted(near, key=lambda w: (-freq(w), w)) if w != low)


def checker_for(db: Database) -> Checker:
    return Checker(db.settings.spelling_words)


# --------------------------------------------------------------------------
# The fields checked, and a scan of the whole database
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Place:
    """A field the spelling is checked in."""
    level: str                   # entry or token
    name: str                    # the field's name
    title: str


def places(db: Database) -> list[Place]:
    """The English gloss and the English translation, if the database has them."""
    s = db.settings
    out = []
    g = s.entry_field("gloss")
    if g and LANG in s.gloss_languages:
        out.append(Place("entry", g.name, g.title))
    t = s.token_field("translation")
    if t and LANG in s.gloss_languages:
        out.append(Place("token", t.name, t.title))
    return out


@dataclass
class Occurrence:
    entry: Entry
    index: int | None            # the token's index, or None for the lemma's gloss
    place: Place
    text: str


@dataclass
class Unknown:
    word: str                                   # as it is spelled (first one found)
    occurrences: list[Occurrence] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.occurrences)

    def where(self) -> str:
        return ", ".join(dict.fromkeys(o.place.title for o in self.occurrences))


def scan(db: Database, checker: Checker | None = None) -> list[Unknown]:
    """Every unknown word in the English glosses and translations (lemmas' and utterances'),
    most frequent first."""
    checker = checker or checker_for(db)
    found: dict[str, Unknown] = {}
    pl = places(db)
    for e in db.items():                          # utterances' translations too
        for p in pl:
            items = [(None, e.get(p.name, LANG))] if p.level == "entry" else \
                    [(i, t.get(p.name, LANG)) for i, t in enumerate(e.tokens)]
            for i, text in items:
                seen_here = set()
                for _, _, w in checker.misspelled(text):
                    key = w.lower()
                    if key in seen_here:
                        continue
                    seen_here.add(key)
                    found.setdefault(key, Unknown(w)).occurrences.append(Occurrence(e, i, p, text))
    return sorted(found.values(), key=lambda u: (-u.count, u.word.lower()))


def replace_word(text: str, word: str, new: str) -> str:
    """Replace word wherever it stands as a whole word (any capitalisation), keeping a capital."""
    # a whole word: possibly followed by a possessive ('s or ') but not by more letters
    rx = re.compile(r"(?<![\w'’-])" + re.escape(word) + r"(?=$|[^\w'’-]|['’][sS]?(?![\w'’-]))",
                    re.IGNORECASE)

    def fix(m):
        old = m.group()
        if old[:1].isupper() and new[:1].islower():
            return new[:1].upper() + new[1:]
        return new
    return rx.sub(fix, text or "")


def replacements(db: Database, unknown: Unknown, new: str) -> list[tuple[Entry, Entry]]:
    """(entry, changed copy) for replacing an unknown word everywhere it was found."""
    out: dict[int, tuple[Entry, Entry]] = {}
    for o in unknown.occurrences:
        e = o.entry
        if id(e) not in out:
            out[id(e)] = (e, e.copy())
        after = out[id(e)][1]
        if o.index is None:
            after.set(o.place.name, replace_word(after.get(o.place.name, LANG), unknown.word, new), LANG, True)
        else:
            t = after.tokens[o.index]
            t.set(o.place.name, replace_word(t.get(o.place.name, LANG), unknown.word, new), LANG, True)
    return [(e, a) for e, a in out.values() if e != a]
