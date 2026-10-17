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
from .model import (Database, Entry, FieldDef, Group, ListItem, Metadata, Participant,
                    RefCategory, Settings, Tag, TagStructure, Token, WordClass, nfc)

FORMAT_VERSION = "1"
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


def _load_group(el) -> Group:
    g = Group(name=nfc(el.get("name", "")))
    for child in el:
        if child.tag == "tag":
            g.tags.append(Tag(name=nfc(child.get("name", "")), code=nfc(child.get("code", "")),
                              default=_bool(child.get("default")),
                              description=nfc(child.get("description", ""))))
        elif child.tag == "group":
            g.groups.append(_load_group(child))
    return g


def _load_tags(el) -> TagStructure:
    ts = TagStructure()
    if el is None:
        return ts
    for child in el:
        if child.tag == "word-class":
            ts.word_classes.append(WordClass(nfc(child.get("name", "")),
                                             [_load_group(g) for g in child.findall("group")]))
        elif child.tag == "all-classes":
            ts.all_classes = [_load_group(g) for g in child.findall("group")]
    return ts


KNOWN_SETTINGS = {"entry-fields", "token-fields", "glosses", "tag-structure", "references",
                  "sounds", "pitch", "playback", "display"}

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
        cfg = MatrixConfig(name=nfc(m.get("name", "")), kind=m.get("kind", "lemma-tag"),
                           word_class=nfc(m.get("word-class", "")))
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
    s.tags = _load_tags(el.find("tag-structure"))
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


def load(path: str | os.PathLike) -> Database:
    path = str(path)
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise FormatError(f"This file isn't readable XML: {exc}") from exc
    if root.tag != "database":
        raise FormatError("This isn't a Lemmatrix database (the top element should be <database>).")
    if root.get("format", FORMAT_VERSION) != FORMAT_VERSION:
        raise FormatError(f"This database uses format {root.get('format')}, "
                          f"which this version of Lemmatrix can't read.")

    md = Metadata()
    if (m := root.find("metadata")) is not None:
        if (x := m.find("language")) is not None:
            md.language_code, md.language_name = nfc(x.get("code", "")), _text(x)
        if (x := m.find("variety")) is not None:
            md.variety_code, md.variety_name = nfc(x.get("code", "")), _text(x)
        md.researcher = _text(m.find("researcher"))
        md.participants = [Participant(nfc(p.get("code", "")), _text(p)) for p in m.findall("participant")]
        md.description = _text(m.find("description"))

    settings = _load_settings(root.find("settings"))
    entry_multi = {f.name for f in settings.entry_fields if f.multilingual}
    token_multi = {f.name for f in settings.token_fields if f.multilingual}
    pitch_fields = [f.name for f in settings.token_fields if f.role == "pitch"]

    db = Database(metadata=md, settings=settings, path=path)
    for el in root.findall("entry"):
        e = Entry(ref=nfc(el.get("ref", "")), file_gloss=nfc(el.get("file-gloss", "")))
        _load_values(el, e, entry_multi)
        for tel in el.findall("token"):
            tags = [nfc(t.strip()) for t in (tel.get("tags") or "").split(",") if t.strip()]
            t = Token(tags=tags, speaker=nfc(tel.get("speaker", "")),
                      collected=tel.get("collected", ""), file=nfc(tel.get("file", "")))
            _load_values(tel, t, token_multi, skip=())
            for name in pitch_fields:               # older data: lone digits become 55
                if t.values.get(name):
                    t.values[name] = pitchmod.normalise(t.values[name])
            e.tokens.append(t)
        db.entries.append(e)
    return db


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
        if f.role != "word-class":           # the word classes live in the tag structure
            for item in f.items:
                _save_item(el, item)


def _save_group(parent, g: Group):
    el = ET.SubElement(parent, "group", name=g.name)
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
            ET.SubElement(el, name).text = obj.values[name]


def to_element(db: Database) -> ET.Element:
    root = ET.Element("database", format=FORMAT_VERSION)
    md = db.metadata
    m = ET.SubElement(root, "metadata")
    if md.language_code or md.language_name:
        ET.SubElement(m, "language", code=md.language_code).text = md.language_name or None
    if md.variety_code or md.variety_name:
        ET.SubElement(m, "variety", code=md.variety_code).text = md.variety_name or None
    if md.researcher:
        ET.SubElement(m, "researcher").text = md.researcher
    for p in md.participants:
        ET.SubElement(m, "participant", code=p.code).text = p.name or None
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
    for wc in s.tags.word_classes:
        wel = ET.SubElement(x, "word-class", name=wc.name)
        for g in wc.groups:
            _save_group(wel, g)
    if s.tags.all_classes:
        ael = ET.SubElement(x, "all-classes")
        for g in s.tags.all_classes:
            _save_group(ael, g)
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
    if s.matrices:
        disp = ET.SubElement(st, "display")
        for m in s.matrices:
            mel = ET.SubElement(disp, "matrix", {"name": m.name, "kind": m.kind,
                                                 "word-class": m.word_class,
                                                 "cell": " ".join(m.cell)})
            for axis, specs in (("y", m.y), ("x", m.x)):
                for sp in specs:
                    a = {"match": sp.match}
                    if sp.tags:
                        a["tags"] = ", ".join(s.tags.sort(m.word_class or None, list(sp.tags)))
                    ET.SubElement(mel, axis, a)
    for extra in s.extra:
        st.append(extra)

    langs = s.gloss_languages
    for e in db.entries:
        attrs = {"ref": e.ref}
        if e.file_gloss:
            attrs["file-gloss"] = e.file_gloss
        el = ET.SubElement(root, "entry", attrs)
        _save_values(el, e, s.entry_fields, langs)
        for t in e.tokens:
            tattrs = {}
            wc = db.word_class(e)
            if t.tags:
                tattrs["tags"] = ", ".join(s.tags.sort(wc, t.tags))
            for key, val in (("speaker", t.speaker), ("collected", t.collected), ("file", t.file)):
                if val:
                    tattrs[key] = val
            tel = ET.SubElement(el, "token", tattrs)
            _save_values(tel, t, s.token_fields, langs)
    return root


def to_string(db: Database) -> str:
    root = to_element(db)
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def backup_folder(path: str | os.PathLike) -> Path:
    return Path(path).parent / "Backups"


def make_backup(path: str | os.PathLike, keep: int = BACKUPS_KEPT) -> Path | None:
    """Copy the current file into the Backups folder and prune old copies."""
    p = Path(path)
    if not p.exists():
        return None
    folder = backup_folder(p)
    folder.mkdir(exist_ok=True)
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


def save(db: Database, path: str | os.PathLike | None = None, backup: bool = True) -> None:
    path = str(path or db.path)
    if not path:
        raise ValueError("No file name given")
    text = to_string(db)
    tmp = path + ".saving"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    if backup:
        make_backup(path)
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
