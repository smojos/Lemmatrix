# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Automatic keyboard switching (IDEAS.md idea 43, designed and built with Josh, 24 October).

Lemmatrix can be told which installed keyboard to use for each kind of field (transcriptions,
the primary language's glosses and translations, each second language) and, under Advanced,
for each field; entering a field switches to its keyboard, and leaving it switches back to the
"elsewhere" keyboard. It is off until set up, the choices belong to this computer (the
keyboards installed differ between computers), and a keyboard changed by hand inside a field is
left alone until the field is left (Lemmatrix only acts when a field is entered or left).

On Windows every input method is a profile of the Text Services Framework: the plain keyboard
layouts (English (United Kingdom) – UK) and the text services such as Keyman's keyboards (SIL
IPA, Amharic) alike, so one list covers both. The profiles are listed and switched through
ITfInputProcessorProfileMgr with ctypes (no extra package); if that isn't reachable, the plain
keyboard layouts are listed and switched instead. Elsewhere (Mac, Linux) there is nothing to
switch yet.

The Ctrl+Space fix (ctrlspace.py) asks Windows whether Ctrl is held, so switching keyboards
doesn't touch it.

Which field a text box is: the dialogues, the in-place editors of the matrices, a text's lines
and the utterance cell, and the phonetics scratchpad's Segments pads say so with tag(); the
grids' in-place editors are found through their table's column. Anything else (search bars,
column filters, Bulk edit's Find and Replace, notes) is "elsewhere".
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QLineEdit, QPlainTextEdit, QTextEdit

PROPERTY = "lemmatrix_keyboard_field"      # set on a text box by tag(): the field it edits
SEGMENT = "segment"                        # the Segments pads: typed as transcriptions

# The kinds (Josh: by kind, with Advanced for per field)
ELSEWHERE, TRANSCRIPTIONS, PRIMARY = "elsewhere", "transcriptions", "primary"
LANG = "lang:"                             # + a second language's code: lang:ar

# A choice's values
DONT = ""                                  # Don't switch
START = "start"                            # the keyboard that was on when Lemmatrix started (Elsewhere's default)
AS_KIND = "kind"                           # Advanced: the field follows its kind

TRANSCRIPTION_ROLES = ("lemma", "phonetic", "phonemic")

PREF_ON = "keyboards/on"
PREF_KIND = "keyboards/kind/"
PREF_FIELD = "keyboards/field/"


@dataclass
class Keyboard:
    id: str                                # tip:0409:{clsid}:{profile} or hkl:0409:4090409
    name: str                              # as Windows names it: English (United Kingdom) – UK


# ---- which field, which kind -------------------------------------------------------------------

def resolve(db, key: str) -> tuple[str, str]:
    """(field id, kind) for a field key as the editors know it: a field's name ("Phonetic"), with a
    language ("Translation:ar"), a grid column's key ("f:Phonetic", "f:Translation:ar", "lemma",
    "gloss", "gloss:ar") or SEGMENT. The field id is the field's name, with its language for a
    gloss or translation ("Gloss:en"); a key that is no field is the elsewhere kind."""
    if key == SEGMENT:
        return SEGMENT, TRANSCRIPTIONS
    if db is None or not key:
        return key or "", ELSEWHERE
    s = db.settings
    k = key[2:] if key.startswith("f:") else key
    name, _, lang = k.partition(":")
    if name in ("lemma", "gloss") and not s.token_field(name):
        f = s.entry_field(name)
    else:
        f = s.token_field(name) or s.entry_field(name) or s.text_field(name)
    if f is None:
        return key, ELSEWHERE
    if f.multilingual:
        lang = lang or s.primary_gloss
        return f"{f.name}:{lang}", (PRIMARY if lang == s.primary_gloss else LANG + lang)
    if f.role in TRANSCRIPTION_ROLES:
        return f.name, TRANSCRIPTIONS
    if f.role == "title":
        return f.name, PRIMARY
    return f.name, ELSEWHERE


def kinds(db) -> list[tuple[str, str]]:
    """The basic table's rows: (kind, label)."""
    s = db.settings if db is not None else None
    primary = s.primary_gloss if s else "en"
    rows = [(ELSEWHERE, "Elsewhere"), (TRANSCRIPTIONS, "Transcriptions"),
            (PRIMARY, f"Glosses and translations ({primary})")]
    for lang in dict.fromkeys(s.gloss_languages if s else []):
        if lang != primary:
            rows.append((LANG + lang, f"Glosses and translations ({lang})"))
    return rows


KIND_TIPS = {ELSEWHERE: "Every field not listed here (comments, Morphemes…), the search bars, column filters "
                        "and Bulk edit's Find and Replace",
             TRANSCRIPTIONS: "Lemma, Phonetic and Phonemic, and the phonetics scratchpad's Segments pads",
             PRIMARY: "Glosses, translations and texts' titles in the primary language"}


def fields(db) -> list[tuple[str, str, str]]:
    """Advanced's rows: (field id, label, kind), every lemma, token and text field, each gloss and
    translation language its own row; Pitch left out (digits)."""
    if db is None:
        return []
    s = db.settings
    out, seen = [], set()
    where_of: dict[str, list[str]] = {}            # a name several lists share (Comment) is one row
    for where, flist in (("lemmas", s.entry_fields), ("tokens", s.token_fields), ("texts", s.text_fields)):
        for f in flist:
            where_of.setdefault(f.name, []).append(where)
    for where, flist in (("Lemma", s.entry_fields), ("Token", s.token_fields), ("Text", s.text_fields)):
        for f in flist:
            if f.closed or f.role == "pitch":
                continue                      # a list to pick from, or digits: nothing to type with
            langs = s.gloss_languages if f.multilingual else [""]
            for lang in langs:
                fid, kind = resolve(db, f"{f.name}:{lang}" if lang else f.name)
                if fid in seen:
                    continue
                seen.add(fid)
                shared = where_of.get(f.name, [])
                label = (f"{f.title} ({', '.join(shared)})" if len(shared) > 1
                         else f"{where}: {f.title}" + (f" ({lang})" if lang else ""))
                out.append((fid, label, kind))
    out.append((SEGMENT, "Phonetics scratchpad: the Segments pads", TRANSCRIPTIONS))
    return out


# ---- the choices (this computer) ------------------------------------------------------------------

class Choices:
    """What this computer has chosen, read from and written to the preferences."""

    def __init__(self, prefs):
        self.prefs = prefs

    @property
    def on(self) -> bool:
        return self.prefs.get_bool(PREF_ON, False)

    @on.setter
    def on(self, v: bool):
        self.prefs.set_value(PREF_ON, bool(v))

    def kind(self, kind: str) -> str:
        v = self.prefs.get_value(PREF_KIND + kind)
        if v is None:
            return START if kind == ELSEWHERE else DONT
        return str(v)

    def set_kind(self, kind: str, value: str):
        self.prefs.set_value(PREF_KIND + kind, value)

    def field(self, fid: str) -> str:
        v = self.prefs.get_value(PREF_FIELD + fid)
        return AS_KIND if v is None else str(v)

    def set_field(self, fid: str, value: str):
        if value == AS_KIND:
            self.prefs.q.remove(PREF_FIELD + fid)
        else:
            self.prefs.set_value(PREF_FIELD + fid, value)

    def for_key(self, db, key: str | None) -> str:
        """The choice for a text box's field key (None: not a field, so Elsewhere's)."""
        if key is None:
            return self.kind(ELSEWHERE)
        fid, kind = resolve(db, key)
        own = self.field(fid)
        return own if own != AS_KIND else self.kind(kind)


# ---- the keyboards (Windows) -------------------------------------------------------------------

class NoKeyboards:
    """Not Windows: nothing to list or switch."""
    available = False

    def list(self) -> list[Keyboard]:
        return []

    def active(self) -> str:
        return ""

    def activate(self, kid: str) -> bool:
        return False


class WindowsKeyboards:
    """The input profiles of the Text Services Framework, through ctypes; plain keyboard layouts
    if TSF can't be reached."""
    available = True

    def __init__(self):
        self._mgr = None
        self._profiles = None
        try:
            self._init_tsf()
        except Exception:
            self._mgr = None

    # -- COM by hand (no comtypes) --
    def _init_tsf(self):
        import ctypes
        from ctypes import POINTER, byref, c_void_p, wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                        ("Data4", ctypes.c_ubyte * 8)]

        class PROFILE(ctypes.Structure):          # TF_INPUTPROCESSORPROFILE
            _fields_ = [("dwProfileType", wintypes.DWORD), ("langid", wintypes.WORD),
                        ("clsid", GUID), ("guidProfile", GUID), ("catid", GUID),
                        ("hklSubstitute", c_void_p), ("dwCaps", wintypes.DWORD),
                        ("hkl", c_void_p), ("dwFlags", wintypes.DWORD)]

        self._ct, self._GUID, self._PROFILE = ctypes, GUID, PROFILE
        ole32 = ctypes.windll.ole32
        ole32.CoInitializeEx(None, 0x2)           # apartment-threaded; Qt has usually done it already

        def guid(text):
            g = GUID()
            ole32.CLSIDFromString(ctypes.c_wchar_p(text), byref(g))
            return g
        clsid = guid("{33C53A50-F456-4884-B049-85FD643ECFED}")       # CLSID_TF_InputProcessorProfiles
        iid_profiles = guid("{1F02B6C5-7842-4EE6-8A0B-9A24183A95CA}")  # ITfInputProcessorProfiles
        iid_mgr = guid("{71C6E74C-0F28-11D8-A82A-00065B84435C}")       # ITfInputProcessorProfileMgr
        self._cat_keyboard = guid("{34745C63-B2F0-4784-8B67-5E12C8701A31}")  # GUID_TFCAT_TIP_KEYBOARD
        p = c_void_p()
        if ole32.CoCreateInstance(byref(clsid), None, 1, byref(iid_profiles), byref(p)) != 0 or not p:
            raise OSError("TSF not available")
        self._profiles = p
        m = c_void_p()
        if self._call(p, 0, ctypes.c_long, [POINTER(GUID), POINTER(c_void_p)], byref(iid_mgr), byref(m)) != 0:
            raise OSError("no ITfInputProcessorProfileMgr")
        self._mgr = m

    def _call(self, obj, index, restype, argtypes, *args):
        # restype c_long for the COM methods, never ctypes.HRESULT: HRESULT raises OSError on a
        # failing result, so the "!= 0" checks after every call could never fire, and one keyboard
        # whose name couldn't be read hid every Keyman keyboard from Settings (the audit, 25 October)
        ct = self._ct
        vtbl = ct.cast(obj, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
        fn = ct.WINFUNCTYPE(restype, ct.c_void_p, *argtypes)(vtbl[index])
        return fn(obj, *args)

    @staticmethod
    def _guid_text(g) -> str:
        return "{%08X-%04X-%04X-%s-%s}" % (g.Data1, g.Data2, g.Data3, bytes(g.Data4[:2]).hex().upper(),
                                            bytes(g.Data4[2:]).hex().upper())

    def _id(self, pr) -> str:
        if pr.dwProfileType == 1:                 # TF_PROFILETYPE_INPUTPROCESSOR (Keyman, IMEs)
            return f"tip:{pr.langid:04x}:{self._guid_text(pr.clsid)}:{self._guid_text(pr.guidProfile)}"
        return f"hkl:{pr.langid:04x}:{(pr.hkl or 0):x}"

    def _enum(self):
        ct = self._ct
        e = ct.c_void_p()
        if self._call(self._mgr, 6, ct.c_long, [ct.c_ushort, ct.POINTER(ct.c_void_p)], 0, ct.byref(e)) != 0:
            return []
        out = []
        while True:
            pr = self._PROFILE()
            got = ct.c_ulong(0)
            hr = self._call(e, 4, ct.c_long, [ct.c_ulong, ct.POINTER(self._PROFILE), ct.POINTER(ct.c_ulong)],
                            1, ct.byref(pr), ct.byref(got))
            if hr != 0 or got.value == 0:
                break
            if pr.dwFlags & 0x2:                   # TF_IPP_FLAG_ENABLED: the ones in the language bar
                out.append(pr)
        self._call(e, 2, ct.c_ulong, [])          # Release
        return out

    def _language(self, langid: int) -> str:
        ct = self._ct
        k = ct.windll.kernel32
        buf = ct.create_unicode_buffer(85)
        if k.LCIDToLocaleName(langid, buf, 85, 0):
            out = ct.create_unicode_buffer(200)
            if k.GetLocaleInfoEx(buf.value, 0x2, out, 200):      # LOCALE_SLOCALIZEDDISPLAYNAME
                return out.value
            return buf.value
        return f"Language {langid:04x}"

    def _layout_name(self, hkl: int) -> str:
        import winreg
        langid, dev = hkl & 0xFFFF, (hkl >> 16) & 0xFFFF
        klid = f"{dev:08X}" if (dev & 0xF000) != 0xF000 else None
        base = r"SYSTEM\CurrentControlSet\Control\Keyboard Layouts"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as root:
                if klid is None:                   # a layout id: find the layout with that Layout Id
                    want = f"{dev & 0x0FFF:04X}"
                    i = 0
                    while True:
                        name = winreg.EnumKey(root, i)
                        i += 1
                        with winreg.OpenKey(root, name) as k:
                            try:
                                if str(winreg.QueryValueEx(k, "Layout Id")[0]).upper() == want:
                                    klid = name
                                    break
                            except OSError:
                                pass
                with winreg.OpenKey(root, klid) as k:
                    return str(winreg.QueryValueEx(k, "Layout Text")[0])
        except OSError:
            return f"{langid:04x}"

    def _name(self, pr) -> str:
        lang = self._language(pr.langid)
        if pr.dwProfileType == 1:
            ct = self._ct
            from ctypes import POINTER, byref
            bstr = ct.c_void_p()                  # a BSTR, freed once read
            hr = self._call(self._profiles, 12, ct.c_long,
                            [POINTER(self._GUID), ct.c_ushort, POINTER(self._GUID), POINTER(ct.c_void_p)],
                            byref(pr.clsid), pr.langid, byref(pr.guidProfile), byref(bstr))
            desc = ""
            if hr == 0 and bstr.value:
                desc = ct.wstring_at(bstr.value)
                ct.windll.oleaut32.SysFreeString(bstr)
            return f"{lang} – {desc or 'input method'}"
        return f"{lang} – {self._layout_name(pr.hkl or 0)}"

    # -- the three calls --
    def list(self) -> list[Keyboard]:
        if self._mgr is not None:
            try:
                profiles = self._enum()
            except Exception:
                profiles = None
            if profiles is not None:
                out = []
                for p in profiles:                # one profile that fails is named plainly, never
                    try:                          # loses the others
                        out.append(Keyboard(self._id(p), self._name(p)))
                    except Exception:
                        try:
                            out.append(Keyboard(self._id(p), f"Keyboard {p.langid:04x}"))
                        except Exception:
                            pass
                return out
        return [Keyboard(f"hkl:{h & 0xFFFF:04x}:{h:x}", self._hkl_name(h)) for h in self._hkls()]

    def active(self) -> str:
        if self._mgr is not None:
            try:
                ct = self._ct
                pr = self._PROFILE()
                if self._call(self._mgr, 10, ct.c_long, [ct.POINTER(self._GUID), ct.POINTER(self._PROFILE)],
                              ct.byref(self._cat_keyboard), ct.byref(pr)) == 0:
                    return self._id(pr)
            except Exception:
                pass
        try:
            import ctypes
            u = ctypes.windll.user32
            u.GetKeyboardLayout.restype = ctypes.c_void_p      # a handle: all 64 bits, as TSF's
            u.GetKeyboardLayout.argtypes = [ctypes.c_ulong]
            h = u.GetKeyboardLayout(0) or 0
            return f"hkl:{h & 0xFFFF:04x}:{h:x}"
        except Exception:
            return ""

    def activate(self, kid: str) -> bool:
        if not kid:
            return False
        if self._mgr is not None:
            for pr in self._enum():
                if self._id(pr) == kid:
                    ct = self._ct
                    flags = 0x10000000 | 0x4      # TF_IPPMF_FORPROCESS | DONTCARECURRENTINPUTLANGUAGE
                    return self._call(self._mgr, 3, ct.c_long,
                                      [ct.c_ulong, ct.c_ushort, ct.POINTER(self._GUID), ct.POINTER(self._GUID),
                                       ct.c_void_p, ct.c_ulong],
                                      pr.dwProfileType, pr.langid, ct.byref(pr.clsid),
                                      ct.byref(pr.guidProfile), pr.hkl, flags) == 0
        if kid.startswith("hkl:"):
            try:
                import ctypes
                h = int(kid.rsplit(":", 1)[1], 16)
                u = ctypes.windll.user32
                u.ActivateKeyboardLayout.restype = ctypes.c_void_p
                u.ActivateKeyboardLayout.argtypes = [ctypes.c_void_p, ctypes.c_uint]
                return bool(u.ActivateKeyboardLayout(h, 0))
            except Exception:
                return False
        return False

    # -- the plain keyboard layouts, if TSF can't be reached --
    def _hkls(self) -> list[int]:
        try:
            import ctypes
            u = ctypes.windll.user32
            n = u.GetKeyboardLayoutList(0, None)
            arr = (ctypes.c_void_p * n)()
            u.GetKeyboardLayoutList(n, arr)
            return [a or 0 for a in arr]          # whole handles (custom and IME layouts were cut to
                                                  # 32 bits, so one layout had two ids: audit, 25 October)
        except Exception:
            return []

    def _hkl_name(self, h: int) -> str:
        try:
            return f"{self._language(h & 0xFFFF)} – {self._layout_name(h)}"
        except Exception:
            return f"Keyboard {h:x}"


def backend():
    if sys.platform == "win32":
        try:
            return WindowsKeyboards()
        except Exception:
            return NoKeyboards()
    return NoKeyboards()


# ---- tagging the text boxes ---------------------------------------------------------------------

def tag(widget, key: str):
    """Say which field a text box edits: a field's name, Name:lang, or SEGMENT."""
    widget.setProperty(PROPERTY, key)
    return widget


TEXT_WIDGETS = (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox)


def field_key(widget) -> str | None:
    """The field key of the text box that has the cursor, or None (not a field: elsewhere)."""
    w, depth = widget, 0
    while w is not None and depth < 4:            # an editable combo box's line edit, a spin box's…
        v = w.property(PROPERTY)
        if v:
            return str(v)
        w, depth = w.parentWidget(), depth + 1
    from .table import FilterTable                # a grid's in-place editor: its column's key
    w = widget.parentWidget()
    while w is not None:
        if isinstance(w, FilterTable):
            idx = w.currentIndex()               # the cell being edited (the editor gets the cursor
            if idx.isValid():                    # just before the table says it is editing)
                col = w.model_.columns[w.proxy.mapToSource(idx).column()]
                return col.key
            return None
        w = w.parentWidget()
    return None


# ---- switching ----------------------------------------------------------------------------------

SKIP_REASONS = (Qt.ActiveWindowFocusReason, Qt.PopupFocusReason)   # alt-tab back, a menu closing


class KeyboardSwitcher(QObject):
    """Installed on the application (install()); told the open database and the preferences by
    set_context()."""

    def __init__(self, parent=None, keyboards=None):
        super().__init__(parent)
        self.keyboards = keyboards or backend()
        self.context: Callable[[], tuple] = lambda: (None, None)    # () -> (db, prefs)
        self.start = self.keyboards.active() if self.keyboards.available else ""
        self._back = QTimer(self)
        self._back.setSingleShot(True)
        self._back.setInterval(0)
        self._back.timeout.connect(self._to_elsewhere)

    def _choices(self):
        db, prefs = self.context()
        if prefs is None:
            return db, None
        c = Choices(prefs)
        return db, (c if c.on and self.keyboards.available else None)

    def _target(self, choice: str) -> str:
        return self.start if choice == START else choice

    def switch_to(self, choice: str):
        kid = self._target(choice)
        try:                                      # never let a keyboard problem get in the way of typing
            if kid and kid != self.keyboards.active():
                self.keyboards.activate(kid)
        except Exception:
            pass

    def _to_elsewhere(self):
        db, c = self._choices()
        if c is not None:
            self.switch_to(c.kind(ELSEWHERE))

    def eventFilter(self, obj, event):
        t = event.type()
        if t in (QEvent.FocusIn, QEvent.FocusOut) and isinstance(obj, TEXT_WIDGETS) \
                and event.reason() not in SKIP_REASONS:
            db, c = self._choices()
            if c is not None:
                if t == QEvent.FocusIn:
                    self._back.stop()
                    self.switch_to(c.for_key(db, field_key(obj)))
                else:
                    self._back.start()            # back to Elsewhere's, unless another field takes over
        return False


_SWITCHER: KeyboardSwitcher | None = None


def install(app, keyboards=None) -> KeyboardSwitcher:
    global _SWITCHER
    _SWITCHER = KeyboardSwitcher(app, keyboards)
    app.installEventFilter(_SWITCHER)
    return _SWITCHER


def set_context(fn: Callable[[], tuple]):
    """The main window tells the switcher where the open database and the preferences are."""
    if _SWITCHER is not None:
        _SWITCHER.context = fn


def installed() -> list[Keyboard]:
    s = _SWITCHER
    try:
        return s.keyboards.list() if s is not None and s.keyboards.available else []
    except Exception:
        return []


def available() -> bool:
    s = _SWITCHER
    return bool(s is not None and s.keyboards.available)


# ---- Settings → General → Keyboards (this computer) ---------------------------------------------

def _combo(keyboards: list[Keyboard], value: str, *, elsewhere=False, as_kind=False):
    from PySide6.QtWidgets import QComboBox
    cb = QComboBox()
    if as_kind:
        cb.addItem("As its kind", AS_KIND)
    if elsewhere:
        cb.addItem("The keyboard on when Lemmatrix starts", START)
    cb.addItem("Don't switch", DONT)
    for k in keyboards:
        cb.addItem(k.name, k.id)
    i = cb.findData(value)
    if i < 0 and value not in (DONT, START, AS_KIND):    # chosen on another day: no longer installed
        cb.addItem(f"{value} (not installed)", value)
        i = cb.count() - 1
        from . import theme
        cb.setItemData(i, theme.colour("error_text"), Qt.ForegroundRole)
    cb.setCurrentIndex(max(0, i))
    return cb


class KeyboardSection:
    """The widgets of Settings → General → Keyboards: the on/off checkbox, one row per kind and
    Advanced… (one row per field). apply() writes them to this computer's preferences."""

    def __init__(self, parent, db, prefs):
        from PySide6.QtWidgets import QCheckBox, QFormLayout, QLabel, QPushButton, QWidget
        self.db, self.prefs, self.parent = db, prefs, parent
        self.choices = Choices(prefs)
        self.keyboards = installed()
        self.on = QCheckBox("Switch keyboards automatically when a field gets the cursor")
        self.on.setChecked(self.choices.on)
        self.on.setToolTip("Entering a field switches to the keyboard chosen for it (e.g. Keyman's SIL IPA "
                           "for Phonetic); leaving it switches back to Elsewhere's. A keyboard you change by "
                           "hand inside a field is left alone until you leave the field.")
        self.table = QWidget()
        form = QFormLayout(self.table)
        form.setContentsMargins(0, 0, 0, 0)
        self.rows: dict[str, object] = {}
        for kind, label in kinds(db):
            cb = _combo(self.keyboards, self.choices.kind(kind), elsewhere=(kind == ELSEWHERE))
            lab = QLabel(label)
            tip = KIND_TIPS.get(kind, f"Glosses and translations in {kind[len(LANG):]}")
            lab.setToolTip(tip)
            cb.setToolTip(tip)
            form.addRow(lab, cb)
            self.rows[kind] = cb
        self.fields: dict[str, str] = {fid: self.choices.field(fid) for fid, _, _ in fields(db)}
        self.advanced = QPushButton("Advanced…")
        self.advanced.setToolTip("A keyboard for each field, where it should differ from its kind's")
        self.advanced.clicked.connect(lambda *_: self._advanced())
        form.addRow("", self.advanced)
        if not available():
            self.on.setEnabled(False)
            self.table.setEnabled(False)
            self.on.setToolTip("Keyboard switching is Windows-only for now.")
            self.note = QLabel("Keyboard switching is Windows-only for now.")
        else:
            self.note = None
        self.on.toggled.connect(self.table.setEnabled)
        self.table.setEnabled(self.on.isChecked() and available())

    def widgets(self) -> list:
        return [w for w in (self.note, self.on, self.table) if w is not None]

    def _advanced(self):
        dlg = AdvancedDialog(self.parent, self.db, self.keyboards, self.fields,
                             {k: cb.currentData() for k, cb in self.rows.items()})
        if dlg.exec():
            self.fields = dlg.values()

    def apply(self):
        c = self.choices
        c.on = self.on.isChecked()
        for kind, cb in self.rows.items():
            c.set_kind(kind, cb.currentData())
        for fid, v in self.fields.items():
            c.set_field(fid, v)


def AdvancedDialog(parent, db, keyboards_: list[Keyboard], current: dict[str, str], kind_values: dict[str, str]):
    """One row per field: As its kind (the basic table's choice, shown in grey beside it), Don't
    switch, or a keyboard."""
    from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLabel, QScrollArea,
                                   QVBoxLayout, QWidget)

    class _Dialog(QDialog):
        def __init__(self):
            super().__init__(parent)
            self.setWindowTitle("Keyboards for each field")
            self.resize(620, 520)
            lay = QVBoxLayout(self)
            note = QLabel("A field on “As its kind” uses its kind's keyboard from the Settings table.")
            note.setWordWrap(True)
            lay.addWidget(note)
            inner = QWidget()
            form = QFormLayout(inner)
            names = {k.id: k.name for k in keyboards_}
            labels = dict(kinds(db))
            self.combos = {}
            for fid, label, kind in fields(db):
                cb = _combo(keyboards_, current.get(fid, AS_KIND), as_kind=True)
                kv = kind_values.get(kind, DONT)
                shown = {DONT: "Don't switch", START: "the keyboard on when Lemmatrix starts"}.get(kv, names.get(kv, kv))
                cb.setItemText(0, f"As its kind: {shown}")
                cb.setToolTip(labels.get(kind, kind))
                form.addRow(label, cb)
                self.combos[fid] = cb
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setWidget(inner)
            lay.addWidget(area, 1)
            bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            bb.accepted.connect(self.accept)
            bb.rejected.connect(self.reject)
            lay.addWidget(bb)

        def values(self) -> dict[str, str]:
            return {fid: cb.currentData() for fid, cb in self.combos.items()}

    return _Dialog()
