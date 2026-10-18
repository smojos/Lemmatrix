"""Matrix configurations and layouts (no Qt here, so it can be tested).

A matrix configuration is a list of *specs* per axis. Each spec is a set of
tags plus a match type:

    Citation   the token with no tags at all
    Exact      exactly these tags; group defaults (Simple, isolation, …)
               are unmarked and don't count, so Exact PL still shows
               PL + isolation
    Loose      at least these tags (Loose SG shows SG, SG + GEN, …)

Lemma/Tag: lemmas down the side (Y), specs across the top (X). The lemmas are the
           ones the lemma list shows, whatever their word class. Until a matrix is
           configured or chosen it is blank.
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
    y: list = field(default_factory=list)      # Tag/Tag rows
    x: list = field(default_factory=list)      # columns
    cell: list = field(default_factory=lambda: list(DEFAULT_CELL))
    blank: bool = False      # cleared on purpose (a Lemma/Tag matrix with no columns isn't automatic)

    def copy(self) -> "MatrixConfig":
        return MatrixConfig(self.name, self.kind, list(self.y), list(self.x), list(self.cell), self.blank)

    def rename(self, tags: dict[str, str], classes: dict[str, str] | None = None) -> None:
        """Follow renamed tags (old name -> new name)."""

        def fix(spec):
            return Spec(frozenset(tags.get(t, t) for t in spec.tags), spec.match)
        self.x = [fix(s) for s in self.x]
        self.y = [fix(s) for s in self.y]


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
    return {t.name for t, _ in db.settings.tags.tags() if t.default}


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


UNKNOWN = 10 ** 9


class Order(dict):
    """tag name -> place in the tag order; .frames holds the frame tags."""
    frames: frozenset = frozenset()


def global_order(db: Database) -> Order:
    order = Order()
    frames = set()
    for path, g in db.settings.tags.leaf_groups():
        for t in g.tags:
            order.setdefault(t.name, len(order))
            if any(p.lower() == "frames" for p in (*path, g.name)):
                frames.add(t.name)
    order.frames = frozenset(frames)
    return order


def sort_key(tags, order: dict[str, int]):
    """Tag order, with frames as a second key: each form comes first on its own, then in
    its frames (Citation, f1, f2, PL, PL f1, PL f2 ...)."""
    frames = getattr(order, "frames", frozenset())
    base = [t for t in tags if t not in frames]
    framed = [t for t in tags if t in frames]

    def key(ts):
        return (len(ts) > 0, sorted(order.get(t, UNKNOWN) for t in ts), sorted(ts))
    return key(base), key(framed)


class Unusual(str):
    """A chip label for a tag that isn't usual for its lemma's word class (the soft warning).

    It is an ordinary string everywhere; the chip painter draws it differently.
    """
    note: str = ""


def chips(db: Database, tags, entry: Entry | None = None) -> list[str]:
    """Short labels (codes, or names for defaults) for a set of tags, in tag order.

    With an entry, tags that aren't usual for its word class come back as Unusual labels.
    """
    ts = db.settings.tags
    odd = set(db.unusual_tags(entry, tags)) if entry is not None else set()
    out = []
    for n in ts.sort(list(tags)):
        t = ts.tag(n)
        label = t.display() if t else n
        if n in odd:
            label = Unusual(label)
            label.note = unusual_note(db, entry, n)
        out.append(label)
    return out


def unusual_note(db: Database, entry: Entry, name: str) -> str:
    """“Plural isn't usual for VERB lemmas (NOUN › Number is usual for NOUN)”."""
    ts = db.settings.tags
    hit = ts.find(name)
    if hit is None:
        return ""
    hint = ts.usual_map().get(id(hit[1]), ())
    wc = db.word_class(entry) or "(no word class)"
    return (f"{name} isn't usual for {wc} lemmas ({' › '.join(ts.path_of(hit[1]))} is usual for "
            f"{', '.join(hint)})")


def unusual_notes(db: Database, entry: Entry, names) -> list[str]:
    return [unusual_note(db, entry, n) for n in db.unusual_tags(entry, names)]


def spec_label(db: Database, spec: Spec, entry: Entry | None = None) -> str:
    if spec.match == CITATION:
        return "Citation"
    text = " + ".join(chips(db, spec.tags, entry)) or "(no tags)"
    return text + (" …" if spec.match == LOOSE else "")


def extra_chips(db: Database, token: Token, spec: Spec | None, entry: Entry | None,
                defaults: set[str]) -> list[str]:
    """What a token adds to its cell's tags (shown on side-by-side tokens)."""
    base = spec.tags if spec else frozenset()
    extra = marked(set(token.tags) - set(base), defaults)
    return ["+" + c if not isinstance(c, Unusual) else _plus(c) for c in chips(db, extra, entry)]


def _plus(c: "Unusual") -> "Unusual":
    u = Unusual("+" + c)
    u.note = c.note
    return u


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
    # A token carrying only defaults (e.g. just "isolation") still needs a column.
    if frozenset() in found:
        specs.append(Spec(frozenset(), EXACT))
    return specs


def auto_tag_specs(db: Database, entries) -> list[Spec]:
    """A Loose line for every (non-default) tag present, in tag order: for Tag/Tag axes."""
    defaults = default_names(db)
    order = global_order(db)
    found = {t for e in entries for tok in e.tokens for t in marked(tok.tags, defaults)}
    return [Spec(frozenset([t]), LOOSE) for t in sorted(found, key=lambda t: (order.get(t, UNKNOWN), t))]


def _sorted_hits(hits, order, defaults=frozenset()):
    """Side-by-side tokens in tag order (group defaults ignored)."""
    return sorted(hits, key=lambda et: sort_key(marked(et[1].tags, defaults), order))


def lemma_tag_layout(db: Database, entries: list[Entry], config: MatrixConfig | None,
                     entry_label: str = "lemma") -> Layout:
    """The lemma list's lemmas down the side, the configured columns across the top.

    Blank until a matrix is configured or chosen (Configure matrix → Restore all present
    fills in every tag combination the lemmas have).
    """
    if config is None or not config.x:
        return Layout(message="Blank matrix: use Configure matrix to add columns, or choose a saved matrix.")
    if not entries:
        return Layout(message="No lemmas pass the lemma list's search and filters.")
    defaults = default_names(db)
    order = global_order(db)
    specs = list(config.x)
    cols = [AxisItem(spec_label(db, s), [] if s.match == CITATION else chips(db, s.tags), s)
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
    return lay


def tag_tag_layout(db: Database, entry: Entry | None, config: MatrixConfig | None) -> Layout:
    """One lemma's paradigm: row specs down the side, column specs across the top."""
    if entry is None:
        return Layout(message="Select a lemma in the lemma list to show its paradigm.")
    if config is None or not config.x or not config.y:
        return Layout(entry=entry, message="Please configure a matrix.")
    defaults = default_names(db)
    order = global_order(db)
    ts = db.settings.tags

    def item(s):
        return AxisItem(spec_label(db, s, entry), [] if s.match == CITATION else chips(db, s.tags, entry), s)

    rows = [item(s) for s in config.y]
    cols = [item(s) for s in config.x]
    lay = Layout(rows=rows, cols=cols, entry=entry)
    for r, row in enumerate(rows):
        for c, col in enumerate(cols):
            spec = combine(row.spec, col.spec)
            if ts.conflicts(list(spec.tags)):
                lay.greyed.add((r, c))
                continue
            hits = [(entry, t) for t in entry.tokens if fits(t.tags, spec, defaults)]
            if hits:
                lay.cells[(r, c)] = _sorted_hits(hits, order, defaults)
    return lay
