# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""🐕 linguist's best friend (IDEAS.md idea 21, Josh, 27 October; Settings → Advanced, off on a new
computer): *auto-correct for common IPA typing errors in phonetic and phonemic fields*, as you type
(never pasted text, never Bulk edit). Each rule is an option of its own. No Qt here: the rules as a
table and `correct`, which the typing filter (`ui/bestfriend.py`) asks for every typed character.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    key: str          # this computer's setting (on unless deselected, once the dog is on)
    label: str        # as Settings → Advanced lists it


EJECTIVE = Rule("edit/bf_ejective", "any apostrophe (' ’ ‘) → ʼ")
GLOTTAL = Rule("edit/bf_glottal", "? → ʔ")
J = Rule("edit/bf_j", "y → j")
G = Rule("edit/bf_g", "g → ɡ (the IPA g)")
LENGTH = Rule("edit/bf_length", ": → ː")
GREEK = Rule("edit/bf_greek", "Greek ε γ φ → ɛ ɣ ɸ")
CLICKS = Rule("edit/bf_clicks", "clicks ! | || ‡ → ǃ ǀ ǁ ǂ")
ACCENTS = Rule("edit/bf_accents", "loose accents ´ ` ^ ¨ ~ after a letter → its combining mark")

RULES = (EJECTIVE, GLOTTAL, J, G, LENGTH, GREEK, CLICKS, ACCENTS)

_SIMPLE = {
    EJECTIVE: {"'": "ʼ", "’": "ʼ", "‘": "ʼ"},   # Josh: the official ejective marker, U+02BC
    GLOTTAL: {"?": "ʔ"},
    J: {"y": "j"},
    G: {"g": "ɡ"},
    LENGTH: {":": "ː"},
    GREEK: {"ε": "ɛ", "γ": "ɣ", "φ": "ɸ"},
    CLICKS: {"!": "ǃ", "‡": "ǂ"},
}
_ACCENTS = {"´": "́", "`": "̀", "^": "̂", "¨": "̈", "~": "̃"}
_DENTAL_CLICK, _LATERAL_CLICK = "ǀ", "ǁ"


def _carries_marks(ch: str) -> bool:
    """A letter, or a combining mark already on one (so marks can stack: é then ~)."""
    cat = unicodedata.category(ch)
    return cat.startswith("L") or unicodedata.combining(ch) != 0


def correct(before: str, typed: str, on) -> tuple[int, str] | None:
    """What a typed character becomes: (how many characters before the cursor it replaces, the text
    put in), or None to type it as it is. `before` is the field's text before the cursor; `on(rule)`
    says whether a rule is turned on."""
    if len(typed) != 1:
        return None
    for rule, table in _SIMPLE.items():
        if typed in table and on(rule):
            return 0, table[typed]
    if typed == "|" and on(CLICKS):
        if before.endswith(_DENTAL_CLICK):            # | | → ǁ, one click
            return 1, _LATERAL_CLICK
        return 0, _DENTAL_CLICK
    if typed in _ACCENTS and on(ACCENTS) and before and _carries_marks(before[-1]):
        return 0, _ACCENTS[typed]
    return None
