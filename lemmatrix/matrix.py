"""Matrix configurations and layouts (no Qt here, so it can be tested).

A matrix configuration is a list of *specs* per axis. Each spec is a set of
tags plus a match type:

    Citation   the token with no tags at all
    Exact      exactly these tags; group defaults (Simple, in isolation, …)
               are unmarked and don't count, so Exact PL still shows
               PL + in isolation
    Loose      at least these tags (Loose SG shows SG, SG + GEN, …)

Lemma/Tag: lemmas down the side (Y), specs across the top (X).
Tag/Tag:   one lemma; specs on both axes. A cell asks for the row's and
           column's tags together; it is Loose if either side is Loose.
           Cells whose tags contradict (two tags of one group) are greyed.

Switching axes on screen is only a display trick: configurations always
keep Y first and X second.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import Database, Entry, Token

CITATION, EXACT, LOOSE = "citation", "exact", "loose"
LEMMA_TAG, TAG_TAG = "lemma-tag", "tag-tag"
NO_CLASS = ""                     # the "(none)" matrix class

DEFAULT_CELL = ["drawing", "Phonetic", "Phonemic", "Translation"]


@dataclass(frozen=True)
class Spec:
    tags: frozenset = frozenset()
    match: str = EXACT

    @classmethod
    def citation(cls) -> "Spec":
        return cls(frozenset(), CITATION)


@dataclass
class MatrixConfig:
    name: str = ""
    kind: str = LEMMA_TAG
    word_class: str = NO_CLASS
    y: list = field(default_factory=list)      # Tag/Tag rows
    x: list = field(default_factory=list)      # columns
    cell: list = field(default_factory=lambda: list(DEFAULT_CELL))

    def copy(self) -> "MatrixConfig":
        return MatrixConfig(self.name, self.kind, self.word_class, list(self.y), list(self.x),
                            list(self.cell))


@dataclass
class AxisItem:
    label: str
    chips: list = field(default_factory=list)  # tag labels shown as chips
    spec: Spec | None = None
    entry: Entry | None = None


@dataclass
class Layout:
    rows: list = field(default_factory=list)
    cols: list = field(default_factory=list)
    cells: dict = field(default_factory=dict)      # (r, c) -> [(entry, token)]
    greyed: set = field(default_factory=set)       # (r, c) that can never hold a token
    entry: Entry | None = None
    message: str = ""

    def spec_at(self, r: int, c: int) -> Spec | None:
        a, b = self.rows[r].spec, self.cols[c].spec
        if a is None:
            return b
        if b is None:
            return a
        return combine(a, b)

    def target(self, r: int, c: int) -> tuple[Entry | None, frozenset]:
        """The entry and tags a new token created in this cell would get."""
        a, b = self.rows[r], self.cols[c]
        entry = a.entry or b.entry or self.entry
        spec = self.spec_at(r, c)
        return entry, (spec.tags if spec else frozenset())

    def tokens(self, r: int, c: int) -> list:
        return self.cells.get((r, c), [])

    def transposed(self) -> "Layout":
        return Layout(rows=self.cols, cols=self.rows,
                      cells={(c, r): v for (r, c), v in self.cells.items()},
                      greyed={(c, r) for (r, c) in self.greyed},
                      entry=self.entry, message=self.message)

    def reading_order(self) -> list:
        """Cells column by column: down each column, then on to the next."""
        return [(r, c) for c in range(len(self.cols)) for r in range(len(self.rows))]


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------

def default_names(db: Database) -> set[str]:
    return {t.name for _, g in db.settings.tags.all_leaf_groups() for t in g.tags if t.default}


def marked(tags, defaults: set[str]) -> frozenset:
    return frozenset(t for t in tags if t not in defaults)


def fits(token_tags, spec: Spec, defaults: set[str]) -> bool:
    tt = set(token_tags)
    if spec.match == CITATION:
        return not tt
    if not spec.tags <= tt:
        return False
    if spec.match == LOOSE:
        return True
    return marked(tt, defaults) == marked(spec.tags, defaults)


def combine(a: Spec, b: Spec) -> Spec:
    """The spec for a Tag/Tag cell from its row and column specs."""
    if a.match == CITATION and b.match == CITATION:
        return Spec.citation()
    if a.match == CITATION:
        return b
    if b.match == CITATION:
        return a
    match = LOOSE if LOOSE in (a.match, b.match) else EXACT
    return Spec(a.tags | b.tags, match)


def global_order(db: Database) -> dict[str, int]:
    order: dict[str, int] = {}
    for _, g in db.settings.tags.all_leaf_groups():
        for t in g.tags:
            order.setdefault(t.name, len(order))
    return order


def sort_key(tags, order: dict[str, int]):
    return (len(tags) > 0, sorted(order.get(t, 10_000) for t in tags), sorted(tags))


def chips(db: Database, tags, word_class: str | None = None) -> list[str]:
    """Short labels (codes, or names for defaults) for a set of tags, in tag order."""
    ts = db.settings.tags
    out = []
    for n in ts.sort(word_class, list(tags)):
        hit = ts.find(word_class, n)
        t = hit[0] if hit else ts.find_anywhere(n)
        out.append(t.display() if t else n)
    return out


def spec_label(db: Database, spec: Spec, word_class: str | None = None) -> str:
    if spec.match == CITATION:
        return "Citation"
    text = " + ".join(chips(db, spec.tags, word_class)) or "(no tags)"
    return text + (" …" if spec.match == LOOSE else "")


def extra_chips(db: Database, token: Token, spec: Spec | None, word_class: str | None,
                defaults: set[str]) -> list[str]:
    """What a token adds to its cell's tags (shown on side-by-side tokens)."""
    base = spec.tags if spec else frozenset()
    extra = marked(set(token.tags) - set(base), defaults)
    return ["+" + c for c in chips(db, extra, word_class)]


# --------------------------------------------------------------------------
# Word classes
# --------------------------------------------------------------------------

def class_of(db: Database, e: Entry) -> str:
    wc = db.word_class(e)
    return wc if wc in db.settings.tags.word_class_names() else NO_CLASS


def in_class(db: Database, entries, word_class: str) -> list[Entry]:
    return [e for e in entries if class_of(db, e) == word_class]


def class_label(word_class: str) -> str:
    return word_class or "(none)"


# --------------------------------------------------------------------------
# Layouts
# --------------------------------------------------------------------------

def auto_specs(db: Database, entries) -> list[Spec]:
    """Citation, then an Exact column for every marked combination present."""
    defaults = default_names(db)
    order = global_order(db)
    found = set()
    has_citation = False
    for e in entries:
        for t in e.tokens:
            if not t.tags:
                has_citation = True
            else:
                found.add(marked(t.tags, defaults))
    specs = [Spec.citation()] if has_citation else []
    specs += [Spec(k, EXACT) for k in sorted(found, key=lambda s: sort_key(s, order)) if k]
    # A token carrying only defaults (e.g. just "in isolation") still needs a column.
    if frozenset() in found:
        specs.append(Spec(frozenset(), EXACT))
    return specs


def _sorted_hits(hits, order, defaults=frozenset()):
    """Side-by-side tokens in tag order (group defaults ignored)."""
    return sorted(hits, key=lambda et: sort_key(marked(et[1].tags, defaults), order))


def lemma_tag_layout(db: Database, entries: list[Entry], config: MatrixConfig | None,
                     entry_label: str = "lemma") -> Layout:
    """Lemmas (already limited to one class) down the side, specs across the top."""
    if not entries:
        return Layout(message="No lemmas of this class pass the lemma list's search and filters.")
    defaults = default_names(db)
    order = global_order(db)
    specs = list(config.x) if (config and config.x) else auto_specs(db, entries)
    wc = class_of(db, entries[0])
    cols = [AxisItem(spec_label(db, s, wc), [] if s.match == CITATION else chips(db, s.tags, wc), s)
            for s in specs]
    rows = []
    for e in entries:
        text = {"reference": e.ref, "gloss": db.gloss(e)}.get(entry_label) or db.lemma(e) or e.ref
        rows.append(AxisItem(text, entry=e))
    lay = Layout(rows=rows, cols=cols)
    for r, row in enumerate(rows):
        toks = row.entry.tokens
        for c, col in enumerate(cols):
            hits = [(row.entry, t) for t in toks if fits(t.tags, col.spec, defaults)]
            if hits:
                lay.cells[(r, c)] = _sorted_hits(hits, order, defaults)
    if not cols:
        lay.message = "These lemmas have no tokens yet."
    return lay


def tag_tag_layout(db: Database, entry: Entry | None, config: MatrixConfig | None) -> Layout:
    """One lemma's paradigm: row specs down the side, column specs across the top."""
    if entry is None:
        return Layout(message="Select a lemma in the lemma list to show its paradigm.")
    if config is None or not config.x or not config.y:
        return Layout(entry=entry, message="Please configure a matrix.")
    wc = class_of(db, entry)
    if config.word_class != wc:
        return Layout(entry=entry, message=f"This matrix is for {class_label(config.word_class)} "
                                           f"lemmas; {entry.ref} is {class_label(wc)}.")
    defaults = default_names(db)
    order = global_order(db)
    ts = db.settings.tags

    def item(s):
        return AxisItem(spec_label(db, s, wc), [] if s.match == CITATION else chips(db, s.tags, wc), s)

    rows = [item(s) for s in config.y]
    cols = [item(s) for s in config.x]
    lay = Layout(rows=rows, cols=cols, entry=entry)
    for r, row in enumerate(rows):
        for c, col in enumerate(cols):
            spec = combine(row.spec, col.spec)
            if ts.conflicts(wc or None, list(spec.tags)):
                lay.greyed.add((r, c))
                continue
            hits = [(entry, t) for t in entry.tokens if fits(t.tags, spec, defaults)]
            if hits:
                lay.cells[(r, c)] = _sorted_hits(hits, order, defaults)
    return lay
