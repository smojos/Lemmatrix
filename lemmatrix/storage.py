"""Reading and writing Lemmatrix database files (readable UTF-8 XML).

Saving is careful: the new file is written next to the old one first and only
then swapped in, and the previous version is copied into a "Backups" folder
beside the database (the 10 most recent are kept).
"""

from __future__ import annotations

import datetime as _dt
import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from . import pitch as pitchmod
from .matrix import CITATION, EXACT, LOOSE, MatrixConfig, Spec
from .model import (Database, Entry, FieldDef, Group, ListItem, Location, Metadata, Person,
                    RefCategory, Settings, Tag, TagStructure, Token, new_id, nfc)

FORMAT_VERSION = "2"
# Format 1 (to 18 October 2026) tied tags to word classes: <word-class> sections of the tag
# structure plus <all-classes>, and the Word Class list lived there. Format 2 has one free
# hierarchy of groups with "usual for" hints; format 1 files are upgraded when opened.
READABLE = ("1", "2")
BACKUPS_KEPT = 10


class FormatError(Exception):
    pass


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def _text(el) -> str:
    return nfc((el.text or "").strip()) if el is not None else ""


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("yes", "true", "1", "on")


def _load_item(el) -> ListItem:
    return ListItem(nfc(el.get("name", "")), [_load_item(c) for c in el.findall("item")])


def _load_field(el) -> FieldDef:
    f = FieldDef(name=el.get("name", ""), label=el.get("label", ""), role=el.get("role", ""),
                 closed=_bool(el.get("closed")) or _bool(el.get("list")))
    f.items = [_load_item(i) for i in el.findall("item")]
    # Older prototype files kept a flat <value> list.
    f.items += [ListItem(_text(v)) for v in el.findall("value") if _text(v)]
    if f.role == "word-class":
        f.closed = True
    return f


def _split(text: str | None) -> list[str]:
    return [nfc(x.strip()) for x in (text or "").split(",") if x.strip()]


def _load_group(el) -> Group:
    g = Group(name=nfc(el.get("name", "")), usual=_split(el.get("usual")))
    for child in el:
        if child.tag == "tag":
            g.tags.append(Tag(name=nfc(child.get("name", "")), code=nfc(child.get("code", "")),
                              default=_bool(child.get("default")),
                              description=nfc(child.get("description", ""))))
        elif child.tag == "group":
            g.groups.append(_load_group(child))
    return g


def _load_tags(el) -> tuple[TagStructure, list[str]]:
    """The tag structure, and (format 1) the word classes that were its top level."""
    ts = TagStructure()
    classes: list[str] = []
    if el is None:
        return ts, classes
    shared = []
    for child in el:
        if child.tag == "group":
            ts.groups.append(_load_group(child))
        elif child.tag == "word-class":             # format 1: a word class's own groups
            name = nfc(child.get("name", ""))
            classes.append(name)
            groups = [_load_group(g) for g in child.findall("group")]
            if groups:
                ts.groups.append(Group(name, groups=groups, usual=[name]))
        elif child.tag == "all-classes":            # format 1: groups open to every class
            shared = [_load_group(g) for g in child.findall("group")]
    ts.groups += shared
    return ts, classes


KNOWN_SETTINGS = {"entry-fields", "token-fields", "glosses", "tag-structure", "references",
                  "sounds", "pitch", "playback", "display", "tag-conversions", "spelling"}

def _load_specs(el, tag: str) -> list[Spec]:
    out = []
    for c in el.findall(tag):
        match = c.get("match", EXACT)
        tags = frozenset(nfc(t.strip()) for t in (c.get("tags") or "").split(",") if t.strip())
        out.append(Spec(frozenset() if match == CITATION else tags, match))
    return out


def _load_matrices(el) -> list[MatrixConfig]:
    out = []
    if el is None:
        return out
    for m in el.findall("matrix"):
        cfg = MatrixConfig(name=nfc(m.get("name", "")), kind=m.get("kind", "lemma-tag"))
        cfg.old_class = nfc(m.get("word-class", ""))      # format 1 only, for the upgrade
        cfg.y = _load_specs(m, "y")
        cfg.x = _load_specs(m, "x")
        if m.get("cell") is not None:
            cfg.cell = m.get("cell").split()
        out.append(cfg)
    return out


def _load_settings(el) -> Settings:
    s = Settings()
    if el is None:
        return s
    if (x := el.find("entry-fields")) is not None:
        s.entry_fields = [_load_field(f) for f in x.findall("field")]
    if (x := el.find("token-fields")) is not None:
        s.token_fields = [_load_field(f) for f in x.findall("field")]
    if (x := el.find("glosses")) is not None:
        s.gloss_languages = (x.get("languages") or "en").split()
        s.primary_gloss = x.get("primary") or s.gloss_languages[0]
    s.tags, s.old_classes = _load_tags(el.find("tag-structure"))
    if (x := el.find("references")) is not None:
        s.ref_scheme = x.get("scheme", "categories")
        s.ref_digits = int(x.get("digits", "3") or 3)
        s.ref_categories = [RefCategory(c.get("letter", ""), _text(c), c.get("numbering", "auto"))
                            for c in x.findall("category")]
    if (x := el.find("sounds")) is not None:
        s.sound_folder = x.get("folder", s.sound_folder)
        s.filename_pattern = x.get("pattern", s.filename_pattern)
        s.tag_separator = x.get("tag-separator", s.tag_separator)
        s.auto_update_names = _bool(x.get("auto-update-names"), True)
    if (x := el.find("pitch")) is not None:
        lo, _, hi = (x.get("display-range") or "1-5").partition("-")
        s.pitch_low, s.pitch_high = int(lo or 1), int(hi or 5)
        s.pitch_style = x.get("style", "contours")
    if (x := el.find("playback")) is not None:
        s.play_cell_on_click = _bool(x.get("play-cell-on-click"))
    s.matrices = _load_matrices(el.find("display"))
    if (x := el.find("spelling")) is not None:
        s.spelling_words = [w for w in (nfc(_text(w)).strip() for w in x.findall("word")) if w]
    s.extra = [child for child in el if child.tag not in KNOWN_SETTINGS]
    return s


def _load_values(el, target, multilingual_names: set[str], skip=("token",)):
    for child in el:
        if child.tag in skip:
            continue
        lang = child.get("lang")
        if lang is not None or child.tag in multilingual_names:
            target.multi.setdefault(child.tag, {})[lang or ""] = _text(child)
        else:
            target.values[child.tag] = _text(child)
            if child.get("changed"):
                target.changed[child.tag] = child.get("changed")


def _load_person(el, older: bool = False) -> Person:
    """<participant code="SP1" name="...">description</participant>; older files had the name as text."""
    if el.get("name") is None and older:
        return Person(nfc(el.get("code", "")), _text(el))
    return Person(nfc(el.get("code", "")), nfc(el.get("name", "")), _text(el), nfc(el.get("consent", "")))


def _load_location(el) -> Location:
    return Location(nfc(el.get("name", "")), nfc(el.get("code", "")), _text(el.find("description")),
                    [_load_location(c) for c in el.findall("location")])


def _load_metadata(m) -> Metadata:
    md = Metadata()
    if m is None:
        return md
    if (x := m.find("language")) is not None:
        md.language_code, md.language_name = nfc(x.get("code", "")), _text(x)
    if (x := m.find("variety")) is not None:
        md.variety_code, md.variety_name = nfc(x.get("code", "")), _text(x)
    md.name = _text(m.find("name"))
    md.author = _text(m.find("author"))
    for r in m.findall("researcher"):
        if r.get("code") is None:                # older files: one researcher, who owns the database
            md.author = md.author or _text(r)
        else:
            md.researchers.append(_load_person(r))
    md.participants = [_load_person(p, older=True) for p in m.findall("participant")]
    md.locations = [_load_location(x) for x in m.findall("location")]
    md.description = _text(m.find("description"))
    return md


def _unique_ids(db: Database):
    """Every entry and token gets an id, and no two share one (copies made outside Lemmatrix)."""
    seen = set()
    for e in db.entries:
        for obj in [e, *e.tokens]:
            if not obj.id or obj.id in seen:
                obj.id = new_id()
            seen.add(obj.id)


def load(path: str | os.PathLike) -> Database:
    path = str(path)
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise FormatError(f"This file isn't readable XML: {exc}") from exc
    if root.tag != "database":
        raise FormatError("This isn't a Lemmatrix database (the top element should be <database>).")
    version = root.get("format", FORMAT_VERSION)
    if version not in READABLE:
        raise FormatError(f"This database uses format {root.get('format')}, "
                          f"which this version of Lemmatrix can't read.")

    md = _load_metadata(root.find("metadata"))

    settings = _load_settings(root.find("settings"))
    entry_multi = {f.name for f in settings.entry_fields if f.multilingual}
    token_multi = {f.name for f in settings.token_fields if f.multilingual}
    pitch_fields = [f.name for f in settings.token_fields if f.role == "pitch"]

    db = Database(metadata=md, settings=settings, path=path)
    for el in root.findall("entry"):
        e = Entry(ref=nfc(el.get("ref", "")), file_gloss=nfc(el.get("file-gloss", "")),
                  id=el.get("id", ""))
        _load_values(el, e, entry_multi)
        for tel in el.findall("token"):
            tags = [nfc(t.strip()) for t in (tel.get("tags") or "").split(",") if t.strip()]
            t = Token(tags=tags, speaker=nfc(tel.get("speaker", "")),
                      collected=tel.get("collected", ""), file=nfc(tel.get("file", "")),
                      rerecord=tel.get("rerecord") == "yes", id=tel.get("id", ""))
            _load_values(tel, t, token_multi, skip=())
            for name in pitch_fields:               # older data: lone digits become 55
                if t.values.get(name):
                    t.values[name] = pitchmod.normalise(t.values[name])
            e.tokens.append(t)
        db.entries.append(e)
    _unique_ids(db)
    if version == "1":
        _upgrade_from_1(db)
    return db


def _upgrade_from_1(db: Database):
    """Format 1 → 2: tags no longer belong to word classes.

    Each word class's groups become a top-level group of the same name, usual for that
    class; the all-classes groups follow, with no hint. The Word Class list, which was the
    tag structure's top level, becomes the Word Class field's own list. Tag names must now
    be unique in the whole structure: a name used under two word classes keeps it under the
    first, and is "Name (CLASS)" under the others, in the tokens and saved matrices too.
    Saved matrices are no longer filed by word class; a name used twice gets "(CLASS)".
    Nothing else changes: codes, so sound file names, stay as they were.
    """
    s = db.settings
    classes = getattr(s, "old_classes", [])
    notes = ["This database was made with an earlier Lemmatrix, in which tags belonged to word "
             "classes. Its tag structure has been upgraded: each word class's groups are now a "
             "group of the same name, usual for that word class, and any tag can go on any token. "
             "The file is saved in the new format (a backup of the old one is kept)."]
    wcf = s.entry_field("word-class")
    if wcf is not None and not wcf.items:
        wcf.items = [ListItem(c) for c in classes]
    # A tag name used under two word classes. The same tag (name, code and group name all
    # alike, e.g. Plural PL in NOUN, ADJECTIVE and QUANT › Number) becomes one: the first
    # class's group is made usual for the other classes too. Different tags with one name
    # keep it under the first class and get "Name (CLASS)" under the others.
    renames: dict[str, dict[str, str]] = {}              # word class -> {old name: new name}
    taken = {t.name for t, _ in s.tags.tags()}
    first: dict[str, tuple] = {}                         # tag name -> (tag, group, top group)
    for top in list(s.tags.groups):
        owner = top.usual[0] if top.usual else ""
        for g in list(top.walk()):
            for t in list(g.tags):
                if t.name not in first:
                    first[t.name] = (t, g, top)
                    continue
                if not owner:
                    continue
                t0, g0, top0 = first[t.name]
                if (t0.code, t0.default, g0.name) == (t.code, t.default, g.name):
                    hint = g0.usual or list(top0.usual)
                    if owner not in hint:
                        g0.usual = hint + [owner]
                    g.tags.remove(t)
                    note = (f"“{t.name}” was a tag of several word classes; it is now one tag, in "
                            f"{top0.name} › {g0.name}, usual for {', '.join(g0.usual)}.")
                    if note not in notes:
                        notes = [n for n in notes if not n.startswith(f"“{t.name}” was a tag of several")]
                        notes.append(note)
                    continue
                new = f"{t.name} ({owner})"
                k = 2
                while new in taken:
                    new, k = f"{t.name} ({owner} {k})", k + 1
                taken.add(new)
                renames.setdefault(owner, {})[t.name] = new
                notes.append(f"The tag “{t.name}” was used under more than one word class with a different "
                             f"code or group: under {owner} it is now “{new}”. Rename it in Edit → Lists → "
                             "Tag structure.")
                t.name = new

    def prune(g):
        g.groups = [x for x in g.groups if prune(x)]
        return bool(g.tags or g.groups)
    s.tags.groups = [g for g in s.tags.groups if prune(g)]
    if renames:
        for e in db.entries:
            r = renames.get(db.word_class(e))
            if r:
                for tok in e.tokens:
                    tok.tags = [r.get(x, x) for x in tok.tags]
    names: set[tuple[str, str]] = set()
    for m in s.matrices:
        old = getattr(m, "old_class", "")
        if old in renames:
            m.rename(renames[old], {})
        if (m.kind, m.name) in names:
            m.name = f"{m.name} ({old or '(none)'})"
            notes.append(f"Two saved matrices were called the same; one is now “{m.name}”.")
        names.add((m.kind, m.name))
    db.load_notes = notes


# --------------------------------------------------------------------------
# Saving
# --------------------------------------------------------------------------

def _yes(b: bool) -> str:
    return "yes" if b else "no"


def _save_item(parent, item: ListItem):
    el = ET.SubElement(parent, "item", name=item.name)
    for c in item.children:
        _save_item(el, c)


def _save_field(parent, f: FieldDef):
    el = ET.SubElement(parent, "field", name=f.name)
    if f.label:
        el.set("label", f.label)
    if f.role:
        el.set("role", f.role)
    if f.closed:
        el.set("closed", "yes")
        for item in f.items:
            _save_item(el, item)


def _save_group(parent, g: Group):
    el = ET.SubElement(parent, "group", name=g.name)
    if g.usual:
        el.set("usual", ", ".join(g.usual))
    for t in g.tags:
        tel = ET.SubElement(el, "tag", name=t.name)
        if t.code and not t.default:
            tel.set("code", t.code)
        if t.default:
            tel.set("default", "yes")
        if t.description:
            tel.set("description", t.description)
    for sub in g.groups:
        _save_group(el, sub)


def _save_values(el, obj, field_order: list[FieldDef], languages: list[str]):
    names = [f.name for f in field_order]
    extra = sorted((set(obj.values) | set(obj.multi)) - set(names))
    for name in names + extra:
        if name in obj.multi:
            d = obj.multi[name]
            langs = [l for l in languages if l in d] + sorted(l for l in d if l not in languages)
            for lang in langs:
                if d[lang]:
                    child = ET.SubElement(el, name)
                    if lang:
                        child.set("lang", lang)
                    child.text = d[lang]
        elif obj.values.get(name):
            child = ET.SubElement(el, name)
            child.text = obj.values[name]
            if obj.changed.get(name):
                child.set("changed", obj.changed[name])


def to_element(db: Database) -> ET.Element:
    root = ET.Element("database", format=FORMAT_VERSION)
    md = db.metadata
    m = ET.SubElement(root, "metadata")
    if md.language_code or md.language_name:
        ET.SubElement(m, "language", code=md.language_code).text = md.language_name or None
    if md.variety_code or md.variety_name:
        ET.SubElement(m, "variety", code=md.variety_code).text = md.variety_name or None
    if md.name:
        ET.SubElement(m, "name").text = md.name
    if md.author:
        ET.SubElement(m, "author").text = md.author
    for tag, people in (("researcher", md.researchers), ("participant", md.participants)):
        for p in people:
            a = {"code": p.code, "name": p.name}
            if p.consent:
                a["consent"] = p.consent
            ET.SubElement(m, tag, a).text = p.description or None
    def location(parent, loc: Location):
        a = {"name": loc.name}
        if loc.code:
            a["code"] = loc.code
        el = ET.SubElement(parent, "location", a)
        if loc.description:
            ET.SubElement(el, "description").text = loc.description
        for c in loc.children:
            location(el, c)
    for loc in md.locations:
        location(m, loc)
    if md.description:
        ET.SubElement(m, "description").text = md.description

    s = db.settings
    st = ET.SubElement(root, "settings")
    x = ET.SubElement(st, "entry-fields")
    for f in s.entry_fields:
        _save_field(x, f)
    x = ET.SubElement(st, "token-fields")
    for f in s.token_fields:
        _save_field(x, f)
    ET.SubElement(st, "glosses", languages=" ".join(s.gloss_languages), primary=s.primary_gloss)
    x = ET.SubElement(st, "tag-structure")
    for g in s.tags.groups:
        _save_group(x, g)
    x = ET.SubElement(st, "references", scheme=s.ref_scheme, digits=str(s.ref_digits))
    for c in s.ref_categories:
        cel = ET.SubElement(x, "category", letter=c.letter)
        if c.numbering != "auto":
            cel.set("numbering", c.numbering)
        cel.text = c.name
    ET.SubElement(st, "sounds", {"folder": s.sound_folder, "pattern": s.filename_pattern,
                                 "tag-separator": s.tag_separator,
                                 "auto-update-names": _yes(s.auto_update_names)})
    ET.SubElement(st, "pitch", {"display-range": f"{s.pitch_low}-{s.pitch_high}",
                                "style": s.pitch_style})
    if s.spelling_words:                          # the spellcheck's own words, one per line
        sp = ET.SubElement(st, "spelling")
        for w in sorted(dict.fromkeys(s.spelling_words), key=str.lower):
            ET.SubElement(sp, "word").text = w
    if s.matrices:
        disp = ET.SubElement(st, "display")
        for m in s.matrices:
            mel = ET.SubElement(disp, "matrix", {"name": m.name, "kind": m.kind,
                                                 "cell": " ".join(m.cell)})
            for axis, specs in (("y", m.y), ("x", m.x)):
                for sp in specs:
                    a = {"match": sp.match}
                    if sp.tags:
                        a["tags"] = ", ".join(s.tags.sort(list(sp.tags)))
                    ET.SubElement(mel, axis, a)
    for extra in s.extra:
        st.append(extra)

    langs = s.gloss_languages
    for e in db.entries:
        attrs = {"ref": e.ref}
        if e.file_gloss:
            attrs["file-gloss"] = e.file_gloss
        attrs["id"] = e.id
        el = ET.SubElement(root, "entry", attrs)
        _save_values(el, e, s.entry_fields, langs)
        for t in e.tokens:
            tattrs = {}
            if t.tags:
                tattrs["tags"] = ", ".join(s.tags.sort(t.tags))
            for key, val in (("speaker", t.speaker), ("collected", t.collected), ("file", t.file)):
                if val:
                    tattrs[key] = val
            if t.rerecord:
                tattrs["rerecord"] = "yes"
            tattrs["id"] = t.id
            tel = ET.SubElement(el, "token", tattrs)
            _save_values(tel, t, s.token_fields, langs)
    return root


def to_string(db: Database) -> str:
    root = to_element(db)
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def backup_folder(path: str | os.PathLike, chosen: str | os.PathLike | None = None) -> Path:
    """Where backups of a database go: the chosen folder, or "Backups" next to it."""
    return Path(chosen) if chosen else Path(path).parent / "Backups"


def make_backup(path: str | os.PathLike, keep: int = BACKUPS_KEPT,
                folder: str | os.PathLike | None = None) -> Path | None:
    """Copy the current file into the backup folder and prune old copies."""
    p = Path(path)
    if not p.exists():
        return None
    folder = backup_folder(p, folder)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    target = folder / f"{p.stem}_{stamp}{p.suffix}"
    n = 1
    while target.exists():
        n += 1
        target = folder / f"{p.stem}_{stamp}_{n}{p.suffix}"
    shutil.copy2(p, target)
    old = sorted(folder.glob(f"{p.stem}_*{p.suffix}"), key=lambda f: f.stat().st_mtime)
    for f in old[:-keep] if keep else old:
        try:
            f.unlink()
        except OSError:
            pass
    return target


def save(db: Database, path: str | os.PathLike | None = None, backup: bool = True,
         backup_dir: str | os.PathLike | None = None) -> None:
    """Write the database (atomically). The previous version goes to the Backups folder
    next to it, or to backup_dir if given."""
    path = str(path or db.path)
    if not path:
        raise ValueError("No file name given")
    text = to_string(db)
    tmp = path + ".saving"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    if backup:
        make_backup(path, folder=backup_dir)
    os.replace(tmp, path)
    db.path = path


# Windows marks files that OneDrive (or another cloud service) keeps online only:
_RECALL_ON_DATA_ACCESS = 0x00400000
_RECALL_ON_OPEN = 0x00040000
_OFFLINE = 0x00001000
_MAC_DATALESS = 0x40000000          # macOS SF_DATALESS (iCloud / OneDrive "online only")


def is_cloud_only(entry) -> bool:
    """True if a file (an os.DirEntry or a path) is online-only: reading it needs a download."""
    try:
        st = entry.stat() if hasattr(entry, "stat") and not isinstance(entry, (str, Path)) \
            else os.stat(entry)
    except OSError:
        return False
    attrs = getattr(st, "st_file_attributes", 0)
    if attrs & (_RECALL_ON_DATA_ACCESS | _RECALL_ON_OPEN | _OFFLINE):
        return True
    return bool(getattr(st, "st_flags", 0) & _MAC_DATALESS)


def scan_sound_folder(folder: Path) -> tuple[set[str], set[str]]:
    """(names of the files in the folder, names of those that are online-only)."""
    names, cloud = set(), set()
    try:
        with os.scandir(folder) as it:
            for entry in it:
                try:
                    if not entry.is_file():
                        continue
                except OSError:
                    continue
                names.add(entry.name)
                if is_cloud_only(entry):
                    cloud.add(entry.name)
    except OSError:
        pass
    return names, cloud


def same_file(a: Path, b: Path) -> bool:
    """True if two paths are one file (e.g. names differing only in case on Windows)."""
    try:
        return a.exists() and b.exists() and os.path.samefile(a, b)
    except OSError:
        return False


def sound_folder(db: Database) -> Path:
    """Absolute folder for recordings: relative paths are relative to the database file."""
    folder = Path(db.settings.sound_folder or ".")
    if not folder.is_absolute():
        base = Path(db.path).parent if db.path else Path.cwd()
        folder = base / folder
    return folder
