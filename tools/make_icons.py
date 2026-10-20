# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Make the program icons from lemmatrix/resources/lemmatrix.svg.

    python tools/make_icons.py

Needs cairosvg and Pillow (for building only; Lemmatrix itself doesn't). The
SVG's soft glow behind the letters is an SVG filter, which cairosvg doesn't
draw, so it is redone here: the letters' outline is blurred, darkened and laid
between the background and the letters.

Writes lemmatrix/resources/icons/lemmatrix-<size>.png and lemmatrix.ico.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import cairosvg
from PIL import Image, ImageChops, ImageFilter

HERE = Path(__file__).resolve().parent.parent
RES = HERE / "lemmatrix" / "resources"
SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256, 512]
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


def render(svg: str, size: int) -> Image.Image:
    png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def main():
    svg = (RES / "lemmatrix.svg").read_text(encoding="utf-8")
    view = float(re.search(r'viewBox="0 0 ([\d.]+)', svg).group(1))
    std = float(re.search(r'stdDeviation="([\d.]+)"', svg).group(1))
    opacity = float(re.search(r'flood-opacity="([\d.]+)"', svg).group(1))
    no_filter = re.sub(r";?filter:url\(#\w+\)", "", svg)
    background = re.sub(r"<path\b.*?/>", "", no_filter, flags=re.S)
    letters = re.sub(r"<rect\b.*?/>", "", no_filter, flags=re.S)
    out = RES / "icons"
    out.mkdir(exist_ok=True)
    images = {}
    for size in SIZES:
        scale = 4 if size < 128 else 2                    # draw large, then shrink, for clean edges
        big = size * scale
        bg, fg = render(background, big), render(letters, big)
        glow = fg.getchannel("A").filter(ImageFilter.GaussianBlur(std / view * big))
        glow = glow.point(lambda a: int(a * opacity))
        glow = ImageChops.multiply(glow, bg.getchannel("A"))       # stays inside the rounded square
        shadow = Image.new("RGBA", bg.size, (0, 0, 0, 0))
        shadow.putalpha(glow)
        img = Image.alpha_composite(Image.alpha_composite(bg, shadow), fg)
        img = img.resize((size, size), Image.LANCZOS)
        img.save(out / f"lemmatrix-{size}.png")
        images[size] = img
    images[256].save(RES / "lemmatrix.ico", sizes=[(s, s) for s in ICO_SIZES],
                     append_images=[images[s] for s in ICO_SIZES if s != 256])
    print("icons written to", out, "and", RES / "lemmatrix.ico")


if __name__ == "__main__":
    main()
