"""Light and dark themes with one accent colour.

The whole program follows the theme, data views included. Everything drawn
by hand (cells, chips, pitch traces) takes its colours from colour() here, so
both themes stay readable. The accent colour also draws the pitch traces.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

LIGHT, DARK = "light", "dark"
DEFAULT_ACCENT = "#198768"          # the green of the Lemmatrix icon

_state = {"mode": LIGHT, "accent": QColor(DEFAULT_ACCENT)}

# Fixed colours for each theme. The accent-based ones are worked out in colour().
_FIXED = {
    LIGHT: {
        "window": "#efefef", "window_text": "#1b1b1b", "disabled": "#9a9a9a",
        "base": "#ffffff", "alt_base": "#f5f5f5", "text": "#111111", "placeholder": "#8a8a8a",
        "button": "#f4f4f4", "header": "#f0f0f0", "light": "#ffffff", "midlight": "#e3e3e3",
        "mid": "#b8b8b8", "dark": "#9f9f9f", "shadow": "#767676",
        "tooltip": "#ffffdc", "tooltip_text": "#1b1b1b",
        "muted": "#555555",                 # counts and notes
        "faint": "#bbbbbb",                 # an empty value ("—")
        "dim": "#888888",                   # "Citation", names not recorded yet
        "read_only": "#ececec",             # cells not editable in place
        "grid": "#c8c8c8",
        "greyed": "#e4e4e4", "hatch": "#cfcfcf",   # contradictory Tag/Tag cells
        "no_sound": "#b5b5b5", "sound_ok": "#2e9e44", "sound_missing": "#d93030",
        "error": "#c62828", "error_text": "#d32f2f", "error_fill": "#fde0e0",
        "warning": "#b26a00",
        "filter_off": "#f4f4f4", "filter_off_line": "#555555", "filter_off_mark": "#333333",
        "chip_disabled": "#c4c4c4", "chip_disabled_text": "#a0a0a0",
    },
    DARK: {
        "window": "#2b2d30", "window_text": "#e8e8e8", "disabled": "#7a7a7a",
        "base": "#1f2023", "alt_base": "#26272a", "text": "#e8e8e8", "placeholder": "#8a8a8a",
        "button": "#3a3c40", "header": "#323438", "light": "#4a4c50", "midlight": "#404246",
        "mid": "#303236", "dark": "#1b1c1f", "shadow": "#000000",
        "tooltip": "#3a3c40", "tooltip_text": "#e8e8e8",
        "muted": "#a8a8a8",
        "faint": "#5c5e62",
        "dim": "#8c8c8c",
        "read_only": "#2a2b2f",
        "grid": "#45474c",
        "greyed": "#303236", "hatch": "#3d3f44",
        "no_sound": "#6a6c70", "sound_ok": "#4cc265", "sound_missing": "#ff5c5c",
        "error": "#ff6b6b", "error_text": "#ff7070", "error_fill": "#5a2a2a",
        "warning": "#e0a040",
        "filter_off": "#3a3c40", "filter_off_line": "#9a9a9a", "filter_off_mark": "#d0d0d0",
        "chip_disabled": "#4a4c50", "chip_disabled_text": "#707276",
    },
}


# ---- current values --------------------------------------------------------

def mode() -> str:
    return _state["mode"]


def dark() -> bool:
    return _state["mode"] == DARK


def accent() -> QColor:
    return QColor(_state["accent"])


def mix(a: QColor, b: QColor, t: float) -> QColor:
    """a blended toward b by t (0 = a, 1 = b)."""
    return QColor(round(a.red() + (b.red() - a.red()) * t),
                  round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


def _lum(c: QColor) -> float:
    return 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()


def text_on(c: QColor) -> QColor:
    """Black or white, whichever reads better on c."""
    return QColor("black") if _lum(c) > 160 else QColor("white")


def wash(t: float) -> QColor:
    """The accent faded toward the background (white, or dark grey in the dark theme).

    On the dark theme the lightened accent is used, so even a dark accent shows.
    """
    return mix(_bright_accent(), QColor(_FIXED[mode()]["base"]), t)


def ink(t: float) -> QColor:
    """The accent moved toward the text colour: readable on a wash of it."""
    return mix(accent(), QColor(_FIXED[mode()]["text"]), t)


def _bright_accent() -> QColor:
    """The accent, lightened on the dark theme until it shows clearly against dark grey."""
    a = accent()
    if not dark():
        return a
    t = 0.0
    while _lum(mix(a, QColor("white"), t)) < 140 and t < 0.8:
        t += 0.05
    return mix(a, QColor("white"), t)


def colour(name: str) -> QColor:
    """A named colour for the current theme."""
    d = dark()
    if name == "pitch":                       # pitch traces use the accent colour
        return _bright_accent()
    if name == "chip_fill":
        return wash(0.62 if d else 0.80)
    if name == "chip_on":
        return wash(0.45 if d else 0.70)
    if name == "chip_border":
        return wash(0.25 if d else 0.45)
    if name == "chip_text":
        return mix(_bright_accent(), QColor("white"), 0.55) if d else ink(0.62)
    if name == "chip_text_off":
        return mix(_bright_accent(), QColor("white"), 0.25) if d else ink(0.35)
    if name == "chip_blank":                  # an unpicked chip
        return QColor(_FIXED[mode()]["base"])
    if name == "selected_cell":
        return wash(0.82 if d else 0.92)
    if name == "selected_token":
        return wash(0.66 if d else 0.84)
    if name == "selected_token_line":
        return wash(0.15 if d else 0.25)
    if name == "selected_row":
        return wash(0.60 if d else 0.72)
    return QColor(_FIXED[mode()][name])


def muted() -> str:
    """Colour for secondary text such as counts, as a style-sheet value."""
    return colour("muted").name()


# ---- palettes ----------------------------------------------------------------

def _set(p: QPalette, role, value, disabled=None):
    p.setColor(QPalette.All, role, QColor(value))
    if disabled is not None:
        p.setColor(QPalette.Disabled, role, QColor(disabled))


def _palette(data: bool) -> QPalette:
    f = _FIXED[mode()]
    p = QPalette()
    _set(p, QPalette.Window, f["header"] if data else f["window"])
    _set(p, QPalette.WindowText, f["window_text"], f["disabled"])
    _set(p, QPalette.Base, f["base"])
    _set(p, QPalette.AlternateBase, f["alt_base"])
    _set(p, QPalette.Text, f["text"], f["disabled"])
    _set(p, QPalette.PlaceholderText, f["placeholder"])
    _set(p, QPalette.Button, f["header"] if data else f["button"])
    _set(p, QPalette.ButtonText, f["window_text"], f["disabled"])
    _set(p, QPalette.BrightText, f["error"])
    _set(p, QPalette.ToolTipBase, f["tooltip"])
    _set(p, QPalette.ToolTipText, f["tooltip_text"])
    for role, key in ((QPalette.Light, "light"), (QPalette.Midlight, "midlight"), (QPalette.Mid, "mid"),
                      (QPalette.Dark, "dark"), (QPalette.Shadow, "shadow")):
        _set(p, role, f[key])
    a = accent()
    _set(p, QPalette.Link, _bright_accent())
    if data:                                   # a pale selection keeps the data readable
        _set(p, QPalette.Highlight, colour("selected_row"))
        _set(p, QPalette.HighlightedText, f["text"])
    else:
        _set(p, QPalette.Highlight, a)
        _set(p, QPalette.HighlightedText, text_on(a))
    return p


def interface_palette() -> QPalette:
    return _palette(data=False)


def data_palette() -> QPalette:
    """For the lemma list, All data and the matrices."""
    return _palette(data=True)


def as_data(widget):
    widget.setPalette(data_palette())
    widget.setAutoFillBackground(True)
    return widget


# ---- applying ----------------------------------------------------------------

def configure(theme_mode: str, accent_colour: str):
    _state["mode"] = DARK if theme_mode == DARK else LIGHT
    a = QColor(accent_colour)
    _state["accent"] = a if a.isValid() else QColor(DEFAULT_ACCENT)


def apply(app: QApplication | None = None):
    """Give the application the current theme's palette."""
    app = app or QApplication.instance()
    if app is None:
        return
    try:                                    # Qt 6.8+: also darkens the window frame on Windows
        from PySide6.QtCore import Qt
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark if dark() else Qt.ColorScheme.Light)
    except (AttributeError, TypeError):
        pass
    app.setPalette(interface_palette())


def from_prefs(prefs, app: QApplication | None = None):
    configure(prefs.theme, prefs.accent)
    apply(app)
