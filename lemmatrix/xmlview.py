# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""The XML viewer's workings (IDEAS.md idea 23, 21 October 2026): no Qt here.

The viewer shows the database as `storage.to_string` writes it (what Save would write now, unsaved
changes included), read-only. It opens at the selected token or lemma, found by its id, and its
search ignores diacritics and capitals as every other search bar does (searchmark.spans), with an
index built once per text so each keystroke is a plain `str.find`.
"""

from __future__ import annotations

import re

from . import filters as fl


def line_of(text: str, kind: str, ident: str) -> int | None:
    """The 0-based line of the `<entry …>` or `<token …>` (kind) whose id is `ident`, or None."""
    if not ident:
        return None
    m = re.search(rf'<{kind}\b[^>]*\bid="{re.escape(ident)}"', text)
    if m is None:
        return None
    return text.count("\n", 0, m.start())


class FoldedText:
    """`text` folded as the searches fold it (diacritics dropped, capitals ignored), with a map back
    from each folded character to the character of `text` it came from."""

    def __init__(self, text: str):
        self.text = text
        cache: dict[str, str] = {}
        parts: list[str] = []
        owner: list[int] = []
        lone: list[bool] = []                   # True where a character folds to nothing (a diacritic)
        for i, ch in enumerate(text):
            f = cache.get(ch)
            if f is None:
                f = cache[ch] = fl.fold_diacritics(ch).casefold() if not ch.isascii() else ch.lower()
            parts.append(f)
            owner.extend([i] * len(f))
            lone.append(not f)
        self.flat = "".join(parts)
        self.owner = owner
        self.lone = lone

    def find_all(self, query: str, limit: int = 100_000) -> list[tuple[int, int]]:
        """(start, end) in `text` of every match of `query` (raw: folded here), the diacritics that
        follow a match included, as searchmark.spans marks them."""
        q = fl.fold_diacritics(query).casefold()
        if not q:
            return []
        out: list[tuple[int, int]] = []
        at = 0
        n = len(self.text)
        while len(out) < limit:
            j = self.flat.find(q, at)
            if j < 0:
                break
            start, end = self.owner[j], self.owner[j + len(q) - 1] + 1
            while end < n and self.lone[end]:
                end += 1
            if out and start <= out[-1][1]:
                out[-1] = (out[-1][0], max(end, out[-1][1]))
            else:
                out.append((start, end))
            at = j + len(q)
        return out
