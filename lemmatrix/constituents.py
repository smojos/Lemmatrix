# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The Constituents tier (IDEAS.md idea 91, designed with Josh, 28 October): labelled brackets
over the words of the line it aligns with (Phonemic by default). No Qt here.

The notation (Josh: "flexible enough to allow embedding and gaps… single letter floating labels…
as opposed to phrasal brackets [ ] vp"):

- ``_``            a word with no label of its own;
- a bare label     a floating label on one word (``V``, ``A``, ``ADJ``);
- ``[ … ]LABEL``   a phrase, its label right after the closing bracket; brackets nest.

Each ``_`` or bare label takes the next unit of the reference line (its alignment units, so a
``{braced}`` group in Phonemic counts as one), so the transcription is never copied into the
tier. Words outside every bracket are the gaps. Spaces round brackets are optional:
``[_[ADJ]MOD]NP`` reads as ``[_ [ADJ]MOD]NP``.

    >>> p = parse("[_ [ADJ]MOD]NP V [_ _]NP")
    >>> [s.label for s in p.slots]
    ['', 'ADJ', 'V', '', '']
    >>> [(x.label, x.start, x.end, x.depth) for x in p.phrases]
    [('MOD', 1, 1, 1), ('NP', 0, 1, 0), ('NP', 3, 4, 0)]

Stored and written into the TextGrid exactly as typed (its tier is cns by default)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ROLE = "constituents"
NAME, ABBR, TIER = "Constituents", "cns", "cns"
WORD = "_"
_TOKEN = re.compile(r"\[|\]([^\s\[\]_]*)|_|[^\s\[\]_]+")
_CAPS = re.compile(r"^[A-Z0-9.]+$")


@dataclass
class Slot:
    index: int
    label: str = ""            # a floating label on its word ("" for _)


@dataclass
class Phrase:
    label: str
    start: int                 # the first and last slot it spans
    end: int
    depth: int                 # 0: outermost


@dataclass
class Parse:
    slots: list[Slot] = field(default_factory=list)
    phrases: list[Phrase] = field(default_factory=list)      # inner ones first (as they close)
    errors: list[str] = field(default_factory=list)

    @property
    def depth(self) -> int:
        """How many levels of brackets deep it goes (0: none)."""
        return max((p.depth for p in self.phrases), default=-1) + 1

    def labels(self) -> list[str]:
        """Every label used: the phrases' and the floating ones, in order, each once."""
        out = []
        for x in [s.label for s in self.slots] + [p.label for p in self.phrases]:
            if x and x not in out:
                out.append(x)
        return out


def parse(text: str) -> Parse:
    out = Parse()
    stack: list[int] = []                  # the slot index where each open bracket started
    for m in _TOKEN.finditer(text or ""):
        tok = m.group(0)
        if tok == "[":
            stack.append(len(out.slots))
        elif tok.startswith("]"):
            if not stack:
                out.errors.append("a ] with no [ before it")
                continue
            start = stack.pop()
            if start == len(out.slots):
                out.errors.append(f"an empty bracket{' ' + m.group(1) if m.group(1) else ''}")
                continue
            out.phrases.append(Phrase(m.group(1) or "", start, len(out.slots) - 1, len(stack)))
        elif tok in (WORD, "{}"):                 # {}: an empty segment of a word-level tier
            out.slots.append(Slot(len(out.slots)))
        else:
            out.slots.append(Slot(len(out.slots), tok))
    if stack:
        out.errors.append(f"{len(stack)} bracket{'s' if len(stack) > 1 else ''} not closed")
    return out


def words(text: str) -> int:
    """How many words of the reference line the notation takes."""
    return len(parse(text).slots)


def problem(text: str, units: int | None) -> str:
    """What's wrong with a Constituents line, in words ("" if nothing): brackets not closed, or
    not as many words as the line it aligns with has (units; None: no line to align with)."""
    if not (text or "").strip():
        return ""
    p = parse(text)
    if p.errors:
        return "; ".join(p.errors).capitalize()
    if units is not None and units and len(p.slots) != units:
        return f"{len(p.slots)} word{'s' if len(p.slots) != 1 else ''} here, {units} in the line it lines up with"
    return ""


def flat(text: str) -> str:
    """The notation readable on one line where nothing lines it up: as typed, spaces tidied."""
    return " ".join((text or "").split())


def is_caps(label: str) -> bool:
    """An all-caps abbreviation (NP, V, 3SG): small caps with /[β]/ on."""
    return bool(_CAPS.match(label or "")) and any(c.isalpha() for c in label)


# ---- the labels -------------------------------------------------------------------------
# Defaults (Josh, 28 October): grammatical relations, phrases, topic and focus; the word-level
# labels come from the Word Class list (its abbreviations). All caps, for easy small caps.
# Whether S groups with A or with O depends on the language's alignment (nominative-accusative,
# ergative-absolutive, split; Josh): for now plain text, no grouping rule.
DEFAULT_LABELS = [
    ("Relations", [("S", "intransitive subject"), ("A", "transitive subject"), ("O", "transitive object"),
                   ("V", "verb"), ("OBL", "oblique")]),
    ("Phrases", [("NP", "noun phrase"), ("VP", "verb phrase"), ("PP", "adpositional phrase"),
                 ("AP", "adjective phrase"), ("ADVP", "adverb phrase"), ("CP", "complementizer phrase")]),
    ("Topic and focus", [("TOP", "topic"), ("FOC", "focus")]),
]
WORD_LEVEL = "Word-level (from the Word Class list)"


def default_labels():
    from .model import ListItem
    return [ListItem(group, [ListItem(name, abbr=abbr) for abbr, name in items])
            for group, items in DEFAULT_LABELS]


def known_labels(settings) -> set[str]:
    """Every label the lists offer: the Constituent labels' abbreviations (and names), and the
    word classes' abbreviations (and names)."""
    out = set()
    for top in settings.constituent_labels:
        for it in top.walk():
            if it.abbr:
                out.add(it.abbr)
            elif it.children == [] and it is not top:
                out.add(it.name)
    f = settings.entry_field("word-class")
    for top in (f.items if f is not None else []):
        for it in top.walk():
            out.add(it.abbr or it.name)
    return out


def unknown(settings, text: str) -> list[str]:
    """The labels of a line that no list has (marked, like an unusual tag; never refused)."""
    known = known_labels(settings)
    return [x for x in parse(text).labels() if x not in known]


def label_tip(settings, label: str) -> str:
    """What a label stands for, from the lists ("NP: noun phrase"; "" if it isn't listed)."""
    for top in settings.constituent_labels:
        for it in top.walk():
            if it.abbr == label and it.name:
                return f"{label}: {it.name}"
    f = settings.entry_field("word-class")
    for top in (f.items if f is not None else []):
        for it in top.walk():
            if it.abbr == label:
                return f"{label}: {it.name}"
    return ""


# ---- LaTeX (for the export of idea 2, later) ----------------------------------------------
def to_brackets(text: str, words_: list[str]) -> str:
    """The line as LaTeX labelled brackets with the words put in (gb4e, expex, linguex):
    [$_{NP}$ kʊ̀ʊn [$_{MOD}$ rɪ̀ɪŋ]] tʌ́ … A floating label sits over its word."""
    p = parse(text)
    if p.errors or len(p.slots) != len(words_):
        return " ".join(words_)
    opens: dict[int, list[Phrase]] = {}
    closes: dict[int, int] = {}
    for x in p.phrases:
        opens.setdefault(x.start, []).append(x)
        closes[x.end] = closes.get(x.end, 0) + 1
    out = []
    for s in p.slots:
        w = words_[s.index]
        if s.label:
            w = f"\\overset{{\\textsc{{{s.label.lower()}}}}}{{\\text{{{w}}}}}"
        pre = "".join(f"[$_{{\\textsc{{{x.label.lower()}}}}}$ " if x.label else "[ "
                      for x in sorted(opens.get(s.index, []), key=lambda x: x.depth))
        out.append(pre + w + "]" * closes.get(s.index, 0))
    return " ".join(out)
