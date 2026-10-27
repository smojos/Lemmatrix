# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""One search for every search bar (IDEAS.md idea 86, Josh, 27 October 2026: "Can't the quick
search bars all be one code?").

**Plain** (the default): what's typed is found as typed, one string, nothing is an operator.

**⚡ power search** (Settings → Advanced; this computer, off on a new computer): doubles, so a
single character is never disturbed (Josh: "so as not to disrupt the regular users experience";
a single `-`, `+`, `,`, `/` or `;` is always text):
- `--` leaves an item out of the whole search (`goat ;; sheep --kid`; `--kid` alone: all but kid);
- `++` is AND, across a row's columns (`goat ++ PL`: goat in the Gloss, PL in Tags);
- `;;` is OR; `++` binds tighter (`goat ++ PL ;; sheep` = (goat and PL) or sheep); no brackets;
- `\\` before a double searches for it (`\\--`, `\\++`, `\\;;`).
The lemma searches' own items (the wordlist searches, the taxon search, *Josh*) come in through
`extra`, and only with Power search on.

Items are compared in search form (diacritics folded, any case: `filters.search_form`), as the
grids' text is. No Qt here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable, Iterable

from . import filters as fl

POWER_KEY = "search/power"           # prefs (this computer): Settings → Advanced → Fire
OR, AND, NOT = ";;", "++", "--"
PLACEHOLDER = "⚡ power search"

_power = False
_listeners: list[Callable[[bool], None]] = []


def power() -> bool:
    """Whether ⚡ power search is on (this computer's setting)."""
    return _power


def set_power(on: bool):
    """Turn Power search on or off; every search bar listening searches again."""
    global _power
    on = bool(on)
    if on == _power:
        return
    _power = on
    for fn in list(_listeners):
        try:
            fn(on)
        except RuntimeError:                       # a Qt object already deleted
            _listeners.remove(fn)


def listen(fn: Callable[[bool], None]):
    _listeners.append(fn)


def unlisten(fn: Callable[[bool], None]):
    if fn in _listeners:
        _listeners.remove(fn)


@dataclass(frozen=True)
class Query:
    groups: tuple[tuple[str, ...], ...] = ()      # OR of AND groups, in search form
    excluded: tuple[str, ...] = ()                # left out of the whole search, in search form
    raw_items: tuple[str, ...] = ()               # the items to mark, as typed (for text documents)
    power: bool = False

    def __bool__(self) -> bool:
        return bool(self.groups or self.excluded)

    @property
    def marked(self) -> list[str]:
        """The items to mark (search form): every item that isn't left out."""
        out = []
        for g in self.groups:
            for t in g:
                if t not in out:
                    out.append(t)
        return out

    @property
    def items(self) -> list[str]:
        """Every item, left out or not (search form)."""
        return self.marked + [t for t in self.excluded if t not in self.marked]

    def matches(self, texts: Iterable[str], extra: Callable[[str], bool | None] | None = None) -> bool:
        """Whether a row matches: `texts` are its columns (or parts) in search form, each looked at
        alone (an item never spans two); `extra(item)` → True / False for an item that is a search
        of its own (the lemma searches', Power search only), None to look in the texts."""
        if not self:
            return True
        texts = [t for t in texts if t]
        use_extra = extra is not None and self.power

        def has(item: str) -> bool:
            if use_extra:
                hit = extra(item)
                if hit is not None:
                    return bool(hit)
            return any(item in t for t in texts)

        for x in self.excluded:
            if has(x):
                return False
        if not self.groups:
            return True
        return any(all(has(t) for t in g) for g in self.groups)

    def found(self, hay: str) -> bool:
        """One text (search form) matches."""
        return self.matches([hay])


def _tokens(text: str) -> list[tuple[str, str]]:
    """(kind, text): kind is "text", OR, AND or NOT; a backslash before a double keeps it as text."""
    out: list[tuple[str, str]] = []
    cur: list[str] = []
    k, n = 0, len(text)
    while k < n:
        two = text[k:k + 2]
        if text[k] == "\\" and text[k + 1:k + 3] in (OR, AND, NOT):
            cur.append(text[k + 1:k + 3])
            k += 3
            continue
        if two in (OR, AND, NOT):
            out.append(("text", "".join(cur)))
            cur = []
            out.append((two, two))
            k += 2
            continue
        cur.append(text[k])
        k += 1
    out.append(("text", "".join(cur)))
    return out


@lru_cache(maxsize=512)
def _parse(text: str, on: bool) -> Query:
    text = text or ""
    if not on:
        t = text.strip()
        return Query(((fl.search_form(t),),), (), (t,), False) if t else Query()
    groups: list[tuple[str, ...]] = []
    group: list[str] = []
    excluded: list[str] = []
    raw: list[str] = []
    neg = False
    for kind, val in _tokens(text):
        if kind == "text":
            t = val.strip()
            if not t:
                continue
            f = fl.search_form(t)
            if not f:
                continue
            if neg:
                if f not in excluded:
                    excluded.append(f)
            else:
                group.append(f)
                raw.append(t)
            neg = False
        elif kind == NOT:
            neg = True
        elif kind == AND:
            neg = False
        elif kind == OR:
            if group:
                groups.append(tuple(group))
            group, neg = [], False
    if group:
        groups.append(tuple(group))
    return Query(tuple(groups), tuple(excluded), tuple(raw), True)


def parse(text: str, on: bool | None = None) -> Query:
    """A search as typed → its Query, plain or Power (this computer's setting unless `on`)."""
    return _parse(text or "", power() if on is None else bool(on))


def matches(text: str, parts: Iterable[str], extra=None) -> bool:
    """The search `text` (as typed) against `parts` (plain text, put in search form here)."""
    q = parse(text)
    if not q:
        return True
    return q.matches((fl.search_form(p or "") for p in parts), extra)
