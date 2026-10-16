"""Laying out tokens for the matrix view (no Qt here, so it can be tested).

Matching rule used everywhere: a token fits a cell when it has all of the
cell's tags and no other *marked* tags. Group defaults (Simple, Indicative,
Affirmative, in isolation, ...) are unmarked, so they never stop a token
fitting a cell, but a header can still ask for one explicitly.

"Exactly" shows only those exact fits. "Includes" also adds a labelled
sub-row (e.g. "+ xH") under a header for each extra combination found, so
tokens with the same tags line up across entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import Database, Entry, Group, Token

EXACTLY = "exactly"
INCLUDES = "includes"


@dataclass
class AxisItem:
    label: str
    tags: frozenset = frozenset()      # tags this row/column contributes
    entry: Entry | None = None         # set on entry axes
    sub: bool = False                  # an Includes sub-row ("+ xH")
    group_none: bool = False           # Tag/Tag "(none)" item


@dataclass
class Layout:
    rows: list[AxisItem] = field(default_factory=list)
    cols: list[AxisItem] = field(default_factory=list)
    cells: dict = field(default_factory=dict)          # (r, c) -> [(entry, token)]
    entry: Entry | None = None                         # Tag/Tag: the entry shown
    message: str = ""                                  # shown when there's nothing to lay out

    def target(self, r: int, c: int) -> tuple[Entry | None, frozenset]:
        """The entry and tags a new token in this cell would get."""
        a, b = self.rows[r], self.cols[c]
        entry = a.entry or b.entry or self.entry
        return entry, a.tags | b.tags

    def tokens(self, r: int, c: int) -> list[tuple[Entry, Token]]:
        return self.cells.get((r, c), [])

    def transposed(self) -> "Layout":
        return Layout(rows=self.cols, cols=self.rows,
                      cells={(c, r): v for (r, c), v in self.cells.items()},
                      entry=self.entry, message=self.message)

    def reading_order(self) -> list[tuple[int, int]]:
        """Cells column by column: down each column, then on to the next."""
        return [(r, c) for c in range(len(self.cols)) for r in range(len(self.rows))]


# --------------------------------------------------------------------------
# Tags helpers
# --------------------------------------------------------------------------

def global_order(db: Database) -> dict[str, int]:
    order: dict[str, int] = {}
    for _, g in db.settings.tags.all_leaf_groups():
        for t in g.tags:
            order.setdefault(t.name, len(order))
    return order


def default_names(db: Database) -> set[str]:
    return {t.name for _, g in db.settings.tags.all_leaf_groups() for t in g.tags if t.default}


def marked(tags, defaults: set[str]) -> frozenset:
    return frozenset(t for t in tags if t not in defaults)


def fits(token_tags, cell_tags, defaults: set[str]) -> bool:
    tt = set(token_tags)
    return set(cell_tags) <= tt and marked(tt, defaults) == marked(cell_tags, defaults)


def sort_key(tags, order: dict[str, int]):
    return (len(tags) > 0, sorted(order.get(t, 10_000) for t in tags), sorted(tags))


def label(db: Database, tags, word_class: str | None = None) -> str:
    return db.settings.tags.display(word_class, list(tags))


# --------------------------------------------------------------------------
# Filters
# --------------------------------------------------------------------------

@dataclass
class TokenFilter:
    """Which tokens the matrix shows. Empty parts don't restrict anything.

    tags: group name path -> set of tag names (any of them; groups combine with AND)
    """
    tags: dict = field(default_factory=dict)
    citation_only: bool = False
    speakers: set = field(default_factory=set)
    dates: set = field(default_factory=set)
    text: str = ""

    def active(self) -> bool:
        return bool(any(self.tags.values()) or self.citation_only or self.speakers
                    or self.dates or self.text)

    def accepts(self, t: Token) -> bool:
        if self.citation_only and t.tags:
            return False
        tt = set(t.tags)
        for wanted in self.tags.values():
            if wanted and not (tt & set(wanted)):
                return False
        if self.speakers and t.speaker not in self.speakers:
            return False
        if self.dates and t.collected not in self.dates:
            return False
        if self.text:
            needle = self.text.casefold()
            hay = [*t.values.values(), *(v for d in t.multi.values() for v in d.values()),
                   *t.tags, t.speaker, t.file]
            if not any(needle in h.casefold() for h in hay):
                return False
        return True


# --------------------------------------------------------------------------
# Layouts
# --------------------------------------------------------------------------

def auto_headers(db: Database, entries, tfilter: TokenFilter | None = None) -> list[frozenset]:
    """Every marked tag combination present among the shown tokens, citation first."""
    defaults = default_names(db)
    order = global_order(db)
    found = set()
    for e in entries:
        for t in e.tokens:
            if tfilter is None or tfilter.accepts(t):
                found.add(marked(t.tags, defaults))
    return sorted(found, key=lambda s: sort_key(s, order))


def _expand(db, headers: list[frozenset], tokens_for_header, mode, word_class=None):
    """Turn headers into axis items, adding Includes sub-rows."""
    defaults = default_names(db)
    order = global_order(db)
    items = []
    for h in headers:
        items.append(AxisItem(label(db, h, word_class), frozenset(h)))
        if mode != INCLUDES or not h:        # the citation row never expands
            continue
        extras = set()
        for tags in tokens_for_header(h):
            extra = marked(set(tags) - set(h), defaults)
            if extra:
                extras.add(frozenset(extra))
        for ex in sorted(extras, key=lambda s: sort_key(s, order)):
            items.append(AxisItem("+ " + label(db, ex, word_class), frozenset(h) | ex, sub=True))
    return items


def entry_tag_layout(db: Database, entries: list[Entry], headers: list[frozenset] | None,
                     mode: str = EXACTLY, tfilter: TokenFilter | None = None,
                     entry_label: str = "lemma") -> Layout:
    """Tag combinations down the side, entries across the top."""
    tfilter = tfilter or TokenFilter()
    if not entries:
        return Layout(message="No entries to show. Check the lemma list's search and filters.")
    if headers is None:
        headers = auto_headers(db, entries, tfilter)
        if mode == INCLUDES:
            # Keep only the smallest combinations; the larger ones become their sub-rows.
            headers = [h for h in headers
                       if not h or not any(o and o < h for o in headers)]
    defaults = default_names(db)

    def tokens_for_header(h):
        for e in entries:
            for t in e.tokens:
                if tfilter.accepts(t) and set(h) <= set(t.tags):
                    yield t.tags

    rows = _expand(db, headers, tokens_for_header, mode)
    cols = []
    for e in entries:
        if entry_label == "reference":
            text = e.ref
        elif entry_label == "gloss":
            text = db.gloss(e)
        else:
            text = db.lemma(e) or e.ref
        cols.append(AxisItem(text, entry=e))
    lay = Layout(rows=rows, cols=cols)
    for c, col in enumerate(cols):
        for r, row in enumerate(rows):
            hits = [(col.entry, t) for t in col.entry.tokens
                    if tfilter.accepts(t) and fits(t.tags, row.tags, defaults)]
            if hits:
                lay.cells[(r, c)] = hits
    if not rows:
        lay.message = "No tokens match the current filters."
    return lay


def tag_tag_layout(db: Database, entry: Entry | None, row_group: Group | None,
                   col_group: Group | None, mode: str = EXACTLY,
                   tfilter: TokenFilter | None = None) -> Layout:
    """One entry's paradigm: one group's tags down the side, another's across."""
    tfilter = tfilter or TokenFilter()
    if entry is None:
        return Layout(message="Select an entry in the lemma list to show its paradigm.")
    if row_group is None or col_group is None:
        return Layout(entry=entry, message="Choose a group for the rows and one for the columns "
                                           "(Set up token display).")
    wc = db.word_class(entry)
    defaults = default_names(db)
    tokens = [t for t in entry.tokens if tfilter.accepts(t)]
    rgroup_tags = {t.name for t in row_group.tags}
    cgroup_tags = {t.name for t in col_group.tags}

    def axis(group, group_tags):
        items = [AxisItem(t.display(), frozenset([t.name])) for t in group.tags]
        if any(not (set(t.tags) & group_tags) for t in tokens):
            items.append(AxisItem("—", frozenset(), group_none=True))
        return items

    base_rows = axis(row_group, rgroup_tags)
    cols = axis(col_group, cgroup_tags)
    rows = []
    for br in base_rows:
        rows.append(br)
        if mode != INCLUDES:
            continue
        extras = set()
        for t in tokens:
            tt = set(t.tags)
            if not br.tags <= tt or (br.group_none and tt & rgroup_tags):
                continue
            for col in cols:
                if not col.tags <= tt or (col.group_none and tt & cgroup_tags):
                    continue
                extra = marked(tt - br.tags - col.tags - rgroup_tags - cgroup_tags, defaults)
                if extra:
                    extras.add(frozenset(extra))
        order = global_order(db)
        for ex in sorted(extras, key=lambda s: sort_key(s, order)):
            rows.append(AxisItem("+ " + label(db, ex, wc), br.tags | ex, sub=True,
                                 group_none=br.group_none))
    lay = Layout(rows=rows, cols=cols, entry=entry)
    for r, row in enumerate(rows):
        for c, col in enumerate(cols):
            cell = row.tags | col.tags
            hits = []
            for t in tokens:
                tt = set(t.tags)
                if row.group_none and tt & rgroup_tags:
                    continue
                if col.group_none and tt & cgroup_tags:
                    continue
                if fits(tt, cell, defaults):
                    hits.append((entry, t))
            if hits:
                lay.cells[(r, c)] = hits
    return lay
