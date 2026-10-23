# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Predictive translation: suggesting a token's English translation from the others (no Qt here).

If father with the tags SG, 2POSS is translated "your father", then mother with the same tags
is probably "your mother". Each English translation that contains its lemma's English gloss
becomes a template for its tags: "your {gloss}". A token whose English translation is empty
is offered the most common template for its tags, filled in with its own gloss.

    - The gloss can be inflected: "goats" for goat, "men" for man, "he ate it" for eat. The
      inflections come from lemminflect (offline, MIT licence). Without it, only translations
      with the gloss unchanged give templates.
    - A leading "to" is ignored when the translation doesn't have it ("to eat" in "I ate").
    - Group defaults (Simple, isolation...) don't count when tags are compared, as in the
      matrices' Exact columns, so a new token's defaults don't keep it from matching.
    - Templates from lemmas of the same word class come first (Kinship before Relational
      before NOUN), then those from every lemma.
    - English translations only; glosses are never predicted.

Nothing is stored: the templates are worked out from the database and kept in memory. Each
call checks every entry against what it was last time, so the templates follow every edit,
and only changed entries are worked out again. Nothing is marked on an accepted suggestion: it
is an ordinary translation and counts as evidence for further suggestions (agreed with Josh,
18 October 2026: a repeated mistake is easier to spot, and Bulk edit fixes it everywhere).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

from .model import Database, Entry, Token

LANG = "en"

try:                                         # optional: without it, no inflected forms
    from lemminflect import getInflection as _get_inflection
except ImportError:                          # pragma: no cover - lemminflect is in requirements.txt
    _get_inflection = None

# Inflections looked for, in order of preference when a form fits several.
NOUN_TAGS = ("NNS",)
VERB_TAGS = ("VBZ", "VBD", "VBN", "VBG")
ADJ_TAGS = ("JJR", "JJS")
ALL_TAGS = NOUN_TAGS + VERB_TAGS + ADJ_TAGS
# Before these, an ambiguous past form ("walked") is the participle (VBN), otherwise the past (VBD).
AUXILIARIES = {"have", "has", "had", "having", "be", "been", "being", "is", "are", "was", "were",
               "am", "get", "gets", "got", "gotten"}

_WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")
_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]")


def available() -> bool:
    """Whether inflected forms can be recognised and made (lemminflect is installed)."""
    return _get_inflection is not None


# --------------------------------------------------------------------------
# Glosses and words
# --------------------------------------------------------------------------

def _words(text: str) -> list[re.Match]:
    return list(_WORD.finditer(text or ""))


def gloss_variants(gloss: str) -> list[list[str]]:
    """The gloss as words: as it is, and without a leading "to" (verbs).

    Bracketed notes are left out, and only the first of several glosses counts
    ("father; dad" is father).
    """
    g = _BRACKETS.sub(" ", gloss or "")
    first = next((p for p in re.split(r"[;,/]", g) if p.strip()), "")
    words = [m.group() for m in _words(first)]
    if not words:
        return []
    out = [words]
    if len(words) > 1 and words[0].lower() == "to":
        out.append(words[1:])
    return out


@lru_cache(maxsize=20000)
def _forms(word: str) -> dict[str, tuple[str, ...]]:
    """Inflected form (lower case) -> the inflection tags that give it, for one gloss word."""
    out: dict[str, list[str]] = {}
    if _get_inflection is None:
        return {}
    base = word.lower()
    for tag in ALL_TAGS:
        for form in _get_inflection(base, tag) or ():
            f = form.lower()
            if f != base:
                out.setdefault(f, []).append(tag)
    return {f: tuple(t) for f, t in out.items()}


@lru_cache(maxsize=20000)
def inflect(word: str, tag: str) -> str:
    """word in the inflection tag (goat, NNS -> goats); "" if it can't be made."""
    if not tag:
        return word
    if _get_inflection is None:
        return ""
    forms = _get_inflection(word.lower(), tag) or ()
    if not forms:
        return ""
    out = forms[0]
    if word[:1].isupper():
        out = out[:1].upper() + out[1:]
    return out


def _is_verb(classes) -> bool:
    return any("VERB" in c.upper() for c in classes)


def _pick_tag(tags: tuple[str, ...], verb: bool, after: str) -> str:
    """The inflection meant, when a form fits several (walks: NNS or VBZ; walked: VBD or VBN)."""
    order = (VERB_TAGS + NOUN_TAGS + ADJ_TAGS) if verb else (NOUN_TAGS + ADJ_TAGS + VERB_TAGS)
    if "VBD" in tags and "VBN" in tags and after.lower() in AUXILIARIES:
        return "VBN"
    return min(tags, key=lambda t: order.index(t) if t in order else len(order))


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Template:
    """A translation with the gloss taken out: prefix + gloss (perhaps inflected) + suffix."""
    prefix: str
    suffix: str
    tag: str = ""             # the gloss's inflection ("" = as it is)
    head: str = "last"        # which gloss word is inflected: first (verbs: ran away) or last (nouns)
    cap: bool = False         # the gloss starts with a capital letter here
    to: bool = True           # a gloss's leading "to" is kept

    def pattern(self) -> str:
        """For display, e.g. "your {gloss}s"."""
        g = "{gloss}" + ({"NNS": "s", "VBZ": "s", "VBD": "ed", "VBN": "en", "VBG": "ing",
                          "JJR": "er", "JJS": "est"}.get(self.tag, ""))
        return f"{self.prefix}{g}{self.suffix}"

    def render(self, gloss: str) -> str:
        """The translation for another gloss; "" when the gloss can't be inflected as needed."""
        variants = gloss_variants(gloss)
        if not variants:
            return ""
        words = list(variants[-1] if (not self.to and len(variants) > 1) else variants[0])
        if self.tag:
            i = 0 if self.head == "first" else len(words) - 1
            w = inflect(words[i], self.tag)
            if not w:
                return ""
            words[i] = w
        text = " ".join(words)
        if self.cap:
            text = text[:1].upper() + text[1:]
        return f"{self.prefix}{text}{self.suffix}"


def extract(translation: str, gloss: str, classes=()) -> Template | None:
    """The template a translation gives, if its gloss is in it (inflected or not)."""
    tr = translation or ""
    found = _words(tr)
    if not found:
        return None
    verb = _is_verb(classes)
    for variant_no, gwords in enumerate(gloss_variants(gloss)):
        n = len(gwords)
        glow = [w.lower() for w in gwords]
        for i in range(len(found) - n + 1):
            span = found[i:i + n]
            # the gloss's words next to each other, with only spaces between them
            if any(tr[a.end():b.start()].strip() for a, b in zip(span, span[1:])):
                continue
            tag, head, ok = "", 0, True
            for j, m in enumerate(span):
                w = m.group().lower()
                if w == glow[j]:
                    continue
                tags = _forms(glow[j]).get(w)
                if not tags or tag:               # one inflected word at most
                    ok = False
                    break
                before = found[i + j - 1].group() if i + j > 0 else ""
                tag, head = _pick_tag(tags, verb, before), j
            if not ok:
                continue
            if n == 1:
                where = "first" if tag.startswith("VB") else "last"
            else:
                where = "first" if (tag and head == 0) else "last"
            first = span[0].group()
            cap = first[:1].isupper() and not gwords[0][:1].isupper()
            return Template(tr[:span[0].start()], tr[span[-1].end():], tag, where, cap,
                            to=(variant_no == 0))
    return None


# --------------------------------------------------------------------------
# The predictor
# --------------------------------------------------------------------------

@dataclass
class Suggestion:
    text: str
    template: Template
    count: int                                   # tokens with this template for these tags
    sources: list[str] = field(default_factory=list)   # their lemmas' glosses (a few)
    word_class: str = ""                         # the word class it was learned from ("": every lemma)

    def describe(self) -> str:
        """For a tooltip: what the suggestion is based on."""
        names = [f"‘{s}’" for s in self.sources[:3]]
        if self.count > len(names):
            names.append(f"{self.count - len(names)} more")
        if len(names) > 1:
            listed = ", ".join(names[:-1]) + " and " + names[-1]
        else:
            listed = names[0] if names else ""
        where = f" ({self.word_class} lemmas)" if self.word_class else ""
        tokens = f"{self.count} token{'s' if self.count != 1 else ''}"
        return f"Suggested from the translations of {listed}{where}: {tokens} with these tags."


def translation_field(db: Database) -> str:
    f = db.settings.token_field("translation")
    return f.name if f else ""


def tag_key(db: Database, tags) -> frozenset:
    """The tags compared: group defaults don't count."""
    defaults = {t.name for t, _ in db.settings.tags.tags() if t.default}
    return frozenset(n for n in tags if n not in defaults)


class Predictor:
    def __init__(self):
        self._entries: dict[str, tuple] = {}     # entry id -> (fingerprint, contributions)
        self._settings_key = None
        self._index: dict = {}                   # (word class or "", tag key) -> {Template: [count, glosses]}

    # ---- learning ------------------------------------------------------
    def _contributions(self, db: Database, e: Entry, fname: str, classes: list[str]) -> list:
        gloss = db.gloss(e, LANG)
        if not gloss:
            return []
        out = []
        for t in e.tokens:
            text = t.get(fname, LANG).strip()
            if not text:
                continue
            tpl = extract(text, gloss, classes)
            if tpl is not None:
                out.append((tag_key(db, t.tags), tpl, gloss))
        return out

    def refresh(self, db: Database):
        """Bring the templates up to date with the database (only changed entries are redone)."""
        s = db.settings
        fname = translation_field(db)
        skey = (fname, tuple(sorted(t.name for t, _ in s.tags.tags() if t.default)),
                tuple(s.word_classes()), available())
        if skey != self._settings_key:
            self._settings_key = skey
            self._entries.clear()
        changed = False
        seen = set()
        for e in db.entries:
            seen.add(e.id)
            wc = db.word_class(e)
            fp = (db.gloss(e, LANG), wc,
                  tuple((tuple(t.tags), t.get(fname, LANG)) for t in e.tokens if t.get(fname, LANG)))
            old = self._entries.get(e.id)
            if old is not None and old[0] == fp:
                continue
            classes = db.classes(e)
            self._entries[e.id] = (fp, tuple(classes), self._contributions(db, e, fname, classes))
            changed = True
        for gone in [k for k in self._entries if k not in seen]:
            del self._entries[gone]
            changed = True
        order = [e.id for e in db.entries]
        if changed or not self._index or order != getattr(self, "_order", None):
            self._order = order
            self._rebuild()

    def _rebuild(self):
        """Ties between templates go to the one from the earliest lemma in the database."""
        index: dict = {}
        for eid in self._order:
            _, classes, contribs = self._entries[eid]
            for key, tpl, gloss in contribs:
                for level in tuple(classes) + ("",):
                    slot = index.setdefault((level, key), {}).setdefault(tpl, [0, []])
                    slot[0] += 1
                    if len(slot[1]) < 5 and gloss not in slot[1]:
                        slot[1].append(gloss)
        self._index = index

    # ---- suggesting ----------------------------------------------------
    def suggest(self, db: Database, e: Entry, tags, current: str = "",
                refresh: bool = True) -> Suggestion | None:
        """The suggested English translation for a token of e with these tags, if its own is empty.

        refresh=False skips checking the database for changes: for many suggestions in a row
        (a repaint of All data) after one refresh().
        """
        if current.strip() or not translation_field(db):
            return None
        gloss = db.gloss(e, LANG)
        if not gloss:
            return None
        if refresh or not self._index:
            self.refresh(db)
        key = tag_key(db, tags)
        for level in tuple(db.classes(e)) + ("",):
            bucket = self._index.get((level, key))
            if not bucket:
                continue
            ranked = sorted(bucket.items(), key=lambda kv: -kv[1][0])   # stable: earliest lemma wins ties
            for tpl, (count, sources) in ranked:
                text = tpl.render(gloss)
                if text:
                    return Suggestion(text, tpl, count, list(sources), level)
        return None

    def suggest_for(self, db: Database, e: Entry, t: Token) -> Suggestion | None:
        fname = translation_field(db)
        return self.suggest(db, e, t.tags, t.get(fname, LANG) if fname else "")

    def templates(self, db: Database) -> dict:
        """(word class or "", tag key) -> {Template: count}: for checking and tests."""
        self.refresh(db)
        return {k: Counter({t: v[0] for t, v in b.items()}) for k, b in self._index.items()}
