"""Light and dark interface themes with an accent colour.

Only the interface follows the theme. Data (the lemma list, All data and the
matrices) always stays black on white/grey, so transcriptions read the same
in either theme.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

LIGHT, DARK = "light", "dark"
DEFAULT_ACCENT = "#3a78d4"
DEFAULT_PITCH = "#1f4fd1"

_state = {"mode": LIGHT, "accent": QColor(DEFAULT_ACCENT), "pitch": QColor(DEFAULT_PITCH)}


# ---- current values --------------------------------------------------------

def mode() -> str:
    return _state["mode"]


def accent() -> QColor:
    return QColor(_state["accent"])


def pitch_colour() -> QColor:
    return QColor(_state["pitch"])


def mix(a: QColor, b: QColor, t: float) -> QColor:
    """a blended toward b by t (0 = a, 1 = b)."""
    return QColor(round(a.red() + (b.red() - a.red()) * t),
                  round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


def tint(t: float) -> QColor:
    """The accent faded toward white: tint(0.85) is a pale wash of it."""
    return mix(accent(), QColor("white"), t)


def shade(t: float) -> QColor:
    """The accent darkened toward black (for text on pale tints)."""
    return mix(accent(), QColor("black"), t)


def text_on(c: QColor) -> QColor:
    """Black or white, whichever reads better on c."""
    lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return QColor("black") if lum > 160 else QColor("white")


def muted() -> str:
    """Colour for secondary text such as counts, as a style-sheet value."""
    return "#a8a8a8" if mode() == DARK else "#555555"


# ---- palettes ----------------------------------------------------------------

def _set(p: QPalette, role, colour, disabled=None):
    p.setColor(QPalette.All, role, QColor(colour))
    if disabled is not None:
        p.setColor(QPalette.Disabled, role, QColor(disabled))


def interface_palette() -> QPalette:
    p = QPalette()
    a = accent()
    if mode() == DARK:
        _set(p, QPalette.Window, "#2b2d30")
        _set(p, QPalette.WindowText, "#e8e8e8", "#7a7a7a")
        _set(p, QPalette.Base, "#1f2023")
        _set(p, QPalette.AlternateBase, "#2a2b2e")
        _set(p, QPalette.Text, "#e8e8e8", "#7a7a7a")
        _set(p, QPalette.PlaceholderText, "#8a8a8a")
        _set(p, QPalette.Button, "#3a3c40")
        _set(p, QPalette.ButtonText, "#e8e8e8", "#7a7a7a")
        _set(p, QPalette.BrightText, "#ff6b6b")
        _set(p, QPalette.ToolTipBase, "#3a3c40")
        _set(p, QPalette.ToolTipText, "#e8e8e8")
        _set(p, QPalette.Light, "#4a4c50")
        _set(p, QPalette.Midlight, "#404246")
        _set(p, QPalette.Mid, "#303236")
        _set(p, QPalette.Dark, "#1b1c1f")
        _set(p, QPalette.Shadow, "#000000")
        _set(p, QPalette.Link, mix(a, QColor("white"), 0.35))
    else:
        _set(p, QPalette.Window, "#efefef")
        _set(p, QPalette.WindowText, "#1b1b1b", "#9a9a9a")
        _set(p, QPalette.Base, "#ffffff")
        _set(p, QPalette.AlternateBase, "#f5f5f5")
        _set(p, QPalette.Text, "#1b1b1b", "#9a9a9a")
        _set(p, QPalette.PlaceholderText, "#8a8a8a")
        _set(p, QPalette.Button, "#f4f4f4")
        _set(p, QPalette.ButtonText, "#1b1b1b", "#9a9a9a")
        _set(p, QPalette.BrightText, "#d32f2f")
        _set(p, QPalette.ToolTipBase, "#ffffdc")
        _set(p, QPalette.ToolTipText, "#1b1b1b")
        _set(p, QPalette.Light, "#ffffff")
        _set(p, QPalette.Midlight, "#e3e3e3")
        _set(p, QPalette.Mid, "#b8b8b8")
        _set(p, QPalette.Dark, "#9f9f9f")
        _set(p, QPalette.Shadow, "#767676")
        _set(p, QPalette.Link, a)
    _set(p, QPalette.Highlight, a)
    _set(p, QPalette.HighlightedText, text_on(a))
    return p


def data_palette() -> QPalette:
    """Black on white for data views, whatever the theme (headers light grey)."""
    p = QPalette()
    _set(p, QPalette.Window, "#f0f0f0")
    _set(p, QPalette.WindowText, "#111111", "#9a9a9a")
    _set(p, QPalette.Base, "#ffffff")
    _set(p, QPalette.AlternateBase, "#f5f5f5")
    _set(p, QPalette.Text, "#111111", "#9a9a9a")
    _set(p, QPalette.Button, "#f0f0f0")
    _set(p, QPalette.ButtonText, "#111111", "#9a9a9a")
    _set(p, QPalette.Light, "#ffffff")
    _set(p, QPalette.Midlight, "#e3e3e3")
    _set(p, QPalette.Mid, "#b8b8b8")
    _set(p, QPalette.Dark, "#9f9f9f")
    _set(p, QPalette.Shadow, "#767676")
    _set(p, QPalette.ToolTipBase, "#ffffdc")
    _set(p, QPalette.ToolTipText, "#1b1b1b")
    _set(p, QPalette.PlaceholderText, "#8a8a8a")
    _set(p, QPalette.Highlight, tint(0.72))
    _set(p, QPalette.HighlightedText, "#111111")
    return p


def as_data(widget):
    """Keep a data widget black on white whatever the theme."""
    widget.setPalette(data_palette())
    widget.setAutoFillBackground(True)
    return widget


# ---- applying ----------------------------------------------------------------

def configure(theme_mode: str, accent_colour: str, pitch: str):
    _state["mode"] = DARK if theme_mode == DARK else LIGHT
    a = QColor(accent_colour)
    _state["accent"] = a if a.isValid() else QColor(DEFAULT_ACCENT)
    c = QColor(pitch)
    _state["pitch"] = c if c.isValid() else QColor(DEFAULT_PITCH)


def apply(app: QApplication | None = None):
    """Give the application the current theme's palette."""
    app = app or QApplication.instance()
    if app is None:
        return
    try:                                    # Qt 6.8+: also darkens the window frame on Windows
        from PySide6.QtCore import Qt
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark if mode() == DARK else Qt.ColorScheme.Light)
    except (AttributeError, TypeError):
        pass
    app.setPalette(interface_palette())


def from_prefs(prefs, app: QApplication | None = None):
    configure(prefs.theme, prefs.accent, prefs.pitch_colour)
    apply(app)
