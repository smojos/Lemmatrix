"""Moving tokens to another lemma (IDEAS.md idea 11, built 19 October 2026).

A moved token keeps everything it has: its id (so notebook links follow it), its tags (any
that aren't usual for the new lemma's word class are marked, as anywhere), its fields and
its recording. Plain Python with no Qt; the window's part is in main_window.py.

- A citation token (no tags) takes the place of the new lemma's citation token if that one
  is empty (nothing typed, no recording): every new lemma starts with one.
- A token whose tags a token of the new lemma already has (or whose recording's name would be
  another recording's) can be given an Example tag (x1, x2…), so its recording gets a name of
  its own; otherwise it moves as it is, and its recording keeps its old name.
- The recording is renamed with the new reference and gloss when names update automatically
  (Settings → Sound); otherwise its name is left out of date, as for any other change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .model import Database, Entry, Group, Tag, Token


@dataclass
class Move:
    source: Entry
    index: int
    token: Token                      # the token as it will be in the new lemma
    replaces: int | None = None       # the new lemma's empty citation token it takes the place of
    clash: str = ""                   # why it needs an Example tag ("" when it doesn't)
    example: str = ""                 # the Example tag that would give it a name of its own
    rename: tuple[Path, Path] | None = None


@dataclass
class Plan:
    target: Entry
    moves: list[Move] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)     # recordings that can't be renamed

    @property
    def clashes(self) -> list[Move]:
        return [m for m in self.moves if m.clash]


def _empty(t: Token) -> bool:
    return not t.file and not any(v.strip() for v in t.values.values()) and \
        not any(v.strip() for d in t.multi.values() for v in d.values())


def examples_group(db: Database) -> Group | None:
    from .defaults import EXAMPLES
    return next((g for _, g in db.settings.tags.leaf_groups() if g.name.lower() == EXAMPLES.lower()), None)


def plan(db: Database, picked: list[tuple[Entry, int]], target: Entry, folder: Path) -> Plan:
    """What moving these tokens (entry, token index) into target would do. folder: the tokens'
    sound folder."""
    p = Plan(target)
    taken_tags = {frozenset(t.tags) for t in target.tokens}
    citation = next((i for i, t in enumerate(target.tokens) if not t.tags), None)
    free_citation = citation if citation is not None and _empty(target.tokens[citation]) else None
    if free_citation is not None:
        taken_tags.discard(frozenset())
    names = {t.file.lower() for e in db.entries for t in e.tokens if t.file}
    planned: list[Token] = []
    probe = target.copy()
    for e, i in picked:
        if e is target:
            continue
        t = e.tokens[i].copy()
        m = Move(e, i, t)
        if not t.tags and free_citation is not None:
            m.replaces, free_citation = free_citation, None
        elif frozenset(t.tags) in taken_tags:
            m.clash = f"{target.ref} already has a token with the same tags"
        else:
            exp = db.expected_filename(probe, t).lower()
            if t.file.lower() != exp and exp in names:
                m.clash = f"{db.expected_filename(probe, t)} is already another recording's name"
        after = t
        if m.clash:
            m.example = free_example(db, probe, t, planned)
            group = examples_group(db)
            mine = {x.name for x in group.tags} if group else set()
            after = t.copy()                          # as it will be with its Example tag
            after.tags = db.settings.tags.sort([x for x in t.tags if x not in mine] + [m.example])
        taken_tags.add(frozenset(after.tags))
        planned.append(after)
        names.add(db.expected_filename(probe, after).lower())
        p.moves.append(m)
    return p


def free_example(db: Database, target: Entry, t: Token, planned: list[Token] = ()) -> str:
    """The first Example tag that gives t, in target, tags and a recording name of its own
    ("Example N" past the last one if all are taken: added by apply())."""
    group = examples_group(db)
    mine = {x.name for x in group.tags} if group else set()
    base = [x for x in t.tags if x not in mine]
    used = {frozenset(o.tags) for o in [*target.tokens, *planned]}
    names = {o.file.lower() for e in db.entries for o in e.tokens if o.file}
    for tag in (group.tags if group else []):
        probe = t.copy()
        probe.tags = db.settings.tags.sort(base + [tag.name])
        if frozenset(probe.tags) not in used and db.expected_filename(target, probe).lower() not in names:
            return tag.name
    n = len(group.tags) + 1 if group else 1
    all_names = {x.name for x, _ in db.settings.tags.tags()}
    while f"Example {n}" in all_names:
        n += 1
    return f"Example {n}"


def _ensure_example(db: Database, name: str) -> bool:
    """Add the tag Example N (code xN) to the Examples group if it isn't there. True if added."""
    from .defaults import EXAMPLES, INSTANCES
    ts = db.settings.tags
    if ts.tag(name):
        return False
    group = examples_group(db)
    if group is None:
        top = next((g for g in ts.groups if g.name.lower() == INSTANCES.lower()), None)
        if top is None:
            top = Group(INSTANCES)
            ts.groups.append(top)
        group = Group(EXAMPLES)
        top.groups.append(group)
    n = name.rsplit(" ", 1)[-1]
    group.tags.append(Tag(name, f"x{n}"))
    return True


def changes(db: Database, p: Plan, folder: Path, add_examples: bool) -> tuple[list, list, bool]:
    """([(entry, changed copy)], [(old path, new path)] renames, whether the tag structure grew),
    for Document.apply_changes. add_examples: give clashing tokens their Example tag."""
    grew = False
    group_names = {x.name for x in examples_group(db).tags} if examples_group(db) else set()
    sources: dict[int, tuple[Entry, Entry]] = {}
    after_target = p.target.copy()
    replaced: list[int] = []
    renames, taken = [], set()
    for m in p.moves:
        t = m.token
        if m.clash and add_examples and m.example:
            grew = _ensure_example(db, m.example) or grew
            t.tags = db.settings.tags.sort([x for x in t.tags if x not in group_names] + [m.example])
            m.clash = ""
        if m.replaces is not None:
            replaced.append(m.replaces)
        after_target.tokens.append(t)
        if t.file and db.settings.auto_update_names and not m.clash:
            new = db.expected_filename(after_target, t)
            src, dst = folder / t.file, folder / new
            if new != t.file:
                if not src.exists():
                    p.problems.append(f"{t.file}: not in its sound folder")
                elif (dst.exists() and not _same(src, dst)) or dst.name.lower() in taken:
                    p.problems.append(f"{t.file}: {new} already exists")
                else:
                    renames.append((src, dst))
                    taken.add(dst.name.lower())
                    t.file = new
        src_e = sources.setdefault(id(m.source), (m.source, m.source.copy()))[1]
        src_e.tokens[m.index] = None
    for i in sorted(replaced, reverse=True):          # the empty citation tokens moved tokens replace
        after_target.tokens.pop(i)
    pairs = []
    for e, after in sources.values():
        after.tokens = [t for t in after.tokens if t is not None]
        pairs.append((e, after))
    pairs.append((p.target, after_target))
    return pairs, renames, grew


def _same(a: Path, b: Path) -> bool:
    from .storage import same_file
    return same_file(a, b)
