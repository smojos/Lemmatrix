# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Make the ɛλicit web page's pictures from lemmatrix/elicit_art.py (Josh's drawings).

    python tools/make_elicit_web.py

Writes docs/elicit/favicon.svg (the main icon; its letters dark or white with the browser's
light or dark mode), docs/elicit/logo.svg (the wordmark, cropped to its drawing) and the PNGs
phones use for a page saved to the home screen (icon-180.png, icon-512.png). Uses Qt, which
Lemmatrix needs anyway.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lemmatrix import elicit_art as art  # noqa: E402

OUT = HERE / "docs" / "elicit"
TEAL, INK = "#198583", "#1b1b1b"
DARK_STYLE = "@media (prefers-color-scheme: dark){.ink{fill:#ffffff}}"


def png(svg: str, size: int, path: Path, background: str | None = None):
    from PySide6.QtCore import QByteArray, QRectF
    from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    QGuiApplication.instance() or QGuiApplication([])
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(QColor(background) if background else QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    m = size * 0.08 if background else 0
    QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(p, QRectF(m, m, size - 2 * m, size - 2 * m))
    p.end()
    img.save(str(path))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "favicon.svg").write_text(art.main(TEAL, INK, DARK_STYLE), encoding="utf-8")
    logo = art.logo(TEAL, INK, style=DARK_STYLE + ".cloud{fill:var(--accent,#198583)}")
    # cropped to the drawing (measured from it: the wordmark sits in a band across the square)
    logo = logo.replace(f'viewBox="0 0 {art.VIEW} {art.VIEW}"', 'viewBox="3.1 10.2 27.6 13.3"', 1)
    (OUT / "logo.svg").write_text(logo, encoding="utf-8")
    for size in (180, 512):                       # on white: home-screen icons have no transparency
        png(art.main(TEAL, INK), size, OUT / f"icon-{size}.png", background="#ffffff")
    print("Wrote", ", ".join(p.name for p in sorted(OUT.glob("*")) if p.suffix in (".svg", ".png")))


if __name__ == "__main__":
    main()
