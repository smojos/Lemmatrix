# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Josh's ɛλicit artwork, read from his Inkscape files in lemmatrix/resources/elicit/.

  Elicit.svg                    the button (and the web page's favicon)
  Elicit_recording_waiting.svg  the button while recordings wait for review: a grey cloud, teal rain
  Ellicit_webicon.svg           the logo in the request dialogue and the web page's heading

The files are used as Josh drew them (21 October 2026: the ɛλ and the rain cloud in one grey,
#b3b3b3, which shows on light and dark alike, no shadow), with one change: the teal (#198583) becomes
the theme colour. To change a drawing, replace its file (same name) and run tools/make_elicit_web.py
for the web page's copies. The web icon and the button are the same drawing for now, on purpose:
Josh keeps them as separate files in case one changes.

No Qt in this module.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

FOLDER = Path(__file__).resolve().parent / "resources" / "elicit"
FILES = {"main": "Elicit.svg", "waiting": "Elicit_recording_waiting.svg", "logo": "Ellicit_webicon.svg"}
TEAL = "#198583"                 # Josh's teal in the drawings: becomes the theme colour
GREY = "#b3b3b3"                 # the ɛλ and the rain cloud


@lru_cache(maxsize=None)
def source(kind: str) -> str:
    """The drawing's SVG text as Josh saved it."""
    return (FOLDER / FILES[kind]).read_text(encoding="utf-8")


def svg(kind: str, accent: str = TEAL) -> str:
    """One of the drawings (main, waiting or logo) with its teal in the colour given (an SVG paint
    value, e.g. "#4fb3b1" or "var(--accent,#198583)")."""
    return re.sub(re.escape(TEAL), accent, source(kind), flags=re.IGNORECASE)


def main(accent: str = TEAL) -> str:
    return svg("main", accent)


def waiting(accent: str = TEAL) -> str:
    return svg("waiting", accent)


def logo(accent: str = TEAL) -> str:
    return svg("logo", accent)
