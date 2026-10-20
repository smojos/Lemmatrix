"""Reset to defaults (Edit → Lists): each list goes back to the defaults of a new database, but
anything still in use is kept, so no token, reference or session loses what it points at.

No Qt here: the Lists dialogue calls these and shows the result, which is only applied on OK.
"""

from __future__ import annotations

import copy

from .model import Group, ListItem, Location, Person, RefCategory, TagStructure


def merge_people(defaults: list[Person], current: list[Person], in_use) -> tuple[list[Person], list[str]]:
    """The default people, then the current ones still in use (in_use(code) -> truthy).
    Returns (people, the codes kept)."""
    out = [copy.deepcopy(p) for p in defaults]
    have = {p.code for p in out}
    kept = []
    for p in current:
        if p.code in have:
            if in_use(p.code):                  # a default's code that's in use: keep its details
                out[[q.code for q in out].index(p.code)] = copy.deepcopy(p)
                kept.append(p.code)
        elif in_use(p.code):
            out.append(copy.deepcopy(p))
            kept.append(p.code)
    return out, kept


def merge_locations(defaults: list[Location], current: list[Location], in_use) -> tuple[list[Location], list[str]]:
    """The default places, plus every place in use (in_use(key) -> truthy) with the places above
    it, merged in where the defaults already have that place. Returns (places, the keys kept)."""
    out = copy.deepcopy(defaults)
    kept = []

    def place(chain: list[Location]):
        level = out
        for loc in chain:
            match = next((x for x in level if x.key == loc.key), None)
            if match is None:
                match = Location(loc.name, loc.code, loc.description)
                level.append(match)
            level = match.children

    def walk(loc: Location, chain: list[Location]):
        chain = chain + [loc]
        if in_use(loc.key):
            place(chain)
            kept.append(loc.key)
        for c in loc.children:
            walk(c, chain)

    for loc in current:
        walk(loc, [])
    return out, kept


def merge_items(defaults: list[ListItem], current: list[ListItem], used: set[str]) -> tuple[list[ListItem], list[str]]:
    """A closed field's list: the defaults, then the values in use that the defaults don't have."""
    out = copy.deepcopy(defaults)
    have = {i.name for top in out for i in top.walk()}
    kept = []
    for top in current:
        for i in top.walk():
            if i.name in used and i.name not in have:
                out.append(ListItem(i.name))
                have.add(i.name)
                kept.append(i.name)
    return out, kept


def merge_categories(defaults: list[RefCategory], current: list[RefCategory], in_use) -> tuple[list[RefCategory], list[str]]:
    """Reference categories: the defaults, with the letters in use kept as they are."""
    out = [copy.deepcopy(c) for c in defaults]
    kept = []
    for c in current:
        if not in_use(c.letter):
            continue
        same = next((i for i, d in enumerate(out) if d.letter == c.letter), None)
        if same is None:
            out.append(copy.deepcopy(c))
        else:
            out[same] = copy.deepcopy(c)
        kept.append(c.letter)
    return out, kept


def merge_tags(defaults: TagStructure, current: TagStructure, used: set[str]) -> tuple[TagStructure, list[str]]:
    """The default tag structure, plus every tag in use that it doesn't have, in a group of the
    same path (made if needed). Returns (structure, the tag names kept)."""
    out = copy.deepcopy(defaults)
    have = {t.name for t, _ in out.tags()}
    kept = []
    for path, g in current.leaf_groups():
        for t in g.tags:
            if t.name in used and t.name not in have:
                level, target = out.groups, None
                for name in path:
                    target = next((x for x in level if x.name == name), None)
                    if target is None:
                        target = Group(name)
                        level.append(target)
                    level = target.groups
                target.tags.append(copy.deepcopy(t))
                have.add(t.name)
                kept.append(t.name)
    return out, kept
