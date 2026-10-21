# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Make the program icons from lemmatrix/resources/lemmatrix.svg.

    python tools/make_icons.py

Needs cairosvg and Pillow (for building only; Lemmatrix itself doesn't). The icon
is flat (Josh's design of 21 October: no shadow behind the letters).

Writes lemmatrix/resources/icons/lemmatrix-<size>.png and lemmatrix.ico.
"""

from __future__ import annotations

import io
from pathlib import Path

import cairosvg
from PIL import Image

HERE = Path(__file__).resolve().parent.parent
RES = HERE / "lemmatrix" / "resources"
SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256, 512]
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


def render(svg: str, size: int) -> Image.Image:
    png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def main():
    svg = (RES / "lemmatrix.svg").read_text(encoding="utf-8")
    out = RES / "icons"
    out.mkdir(exist_ok=True)
    images = {}
    for size in SIZES:
        scale = 4 if size < 128 else 2                    # draw large, then shrink, for clean edges
        img = render(svg, size * scale).resize((size, size), Image.LANCZOS)
        img.save(out / f"lemmatrix-{size}.png")
        images[size] = img
    images[256].save(RES / "lemmatrix.ico", sizes=[(s, s) for s in ICO_SIZES],
                     append_images=[images[s] for s in ICO_SIZES if s != 256])
    print("icons written to", out, "and", RES / "lemmatrix.ico")


if __name__ == "__main__":
    main()
