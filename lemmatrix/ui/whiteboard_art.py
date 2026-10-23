# SPDX-License-Identifier: LicenseRef-Lemmatrix-Artwork
# Copyright © 2026 Joshua A. G. Smolders. All rights reserved: see ARTWORK.md.
"""Josh's whiteboard artwork: the markers, the duster and the Blackboard icon (IDEAS.md idea 45).

Not under the AGPL. Unmodified copies of Lemmatrix may carry it; modified versions must replace
this module with artwork of their own (ARTWORK.md).
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer

# ---- the tray's things: Josh's marker and duster, with a little polish ------------------------

# a marker lies along x, its cap (Josh's path, with the clip) on the left; viewBox in his units
_MARKER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="91.6 143.4 56.6 10.2">
<defs>
 <linearGradient id="cap" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="{light}"/><stop offset="0.55" stop-color="{mid}"/><stop offset="1" stop-color="{dark}"/>
 </linearGradient>
 <linearGradient id="body" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#ffffff"/><stop offset="0.6" stop-color="#f2f2f2"/><stop offset="1" stop-color="#d5d5d5"/>
 </linearGradient>
</defs>
<rect x="105" y="144.0016" width="42.547" height="8.9968" rx="2.73" ry="2.73" fill="url(#body)"
      stroke="#8c8c8c" stroke-width="0.25"/>
<rect x="112.97" y="144.0016" width="23.524" height="8.9968" fill="url(#cap)"/>
<path fill="url(#cap)" stroke="{dark}" stroke-width="0.2" d="m 96.274744,144.00155 c -0.53922,0 -1.052771,0.10639 -1.521355,0.29817 v 2.76831 c -0.14018,-0.0746 -0.300285,-0.11679 -0.470772,-0.11679 h -0.943095 c -0.554,0 -0.999939,0.44594 -0.999939,0.99994 v 1.0976 c 0,0.554 0.445939,1.00046 0.999939,1.00046 h 0.943095 c 0.170487,0 0.330592,-0.0427 0.470772,-0.11731 v 2.76831 c 0.468621,0.19182 0.982083,0.29817 1.521355,0.29817 h 5.243606 c 1.27973,0 2.41442,-0.59587 3.14555,-1.52549 0.1327,0.13429 0.30025,0.21498 0.48317,0.21498 0.43196,0 0.77928,-0.44594 0.77928,-0.99994 v -4.37544 c 0,-0.554 -0.34732,-1.00046 -0.77928,-1.00046 -0.18292,0 -0.35047,0.0807 -0.48317,0.21497 -0.73113,-0.92961 -1.86582,-1.52548 -3.14555,-1.52548 z"/>
<rect x="95.3" y="144.75" width="9.4" height="1.15" rx="0.55" fill="#ffffff" opacity="0.42"/>
<rect x="106.2" y="144.65" width="40.2" height="1.25" rx="0.6" fill="#ffffff" opacity="0.9"/>
<rect x="113.5" y="144.75" width="22.4" height="1.0" rx="0.5" fill="#ffffff" opacity="0.38"/>
<rect x="147.0" y="145.6" width="0.6" height="5.8" rx="0.3" fill="#b9b9b9"/>
</svg>"""

# the duster: a wooden back with a little grain, a darker joint, the felt underneath
_DUSTER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="-0.6 -0.6 34.4 17.2">
<defs>
 <linearGradient id="wood" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#f0d9a6"/><stop offset="0.55" stop-color="#ddbd7f"/><stop offset="1" stop-color="#c49a55"/>
 </linearGradient>
 <linearGradient id="felt" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#4a4a4a"/><stop offset="1" stop-color="#1c1c1c"/>
 </linearGradient>
</defs>
<rect x="0.2" y="11.6" width="32.8" height="4.4" rx="1.1" fill="url(#felt)"/>
<rect x="0.6" y="11.9" width="32.0" height="0.6" rx="0.3" fill="#6a6a6a" opacity="0.8"/>
<path d="M 2.8 0 H 30.4 A 2.6 2.6 0 0 1 33 2.6 V 11.9 H 0.2 V 2.6 A 2.6 2.6 0 0 1 2.8 0 Z"
      fill="url(#wood)" stroke="#a87d3c" stroke-width="0.25"/>
<path d="M 3 3.4 C 9 2.4, 14 4.6, 21 3.3 S 29 3.0, 31 3.8" fill="none" stroke="#a87d3c" stroke-width="0.3" opacity="0.45"/>
<path d="M 2.6 6.0 C 8 5.2, 13 7.1, 19 6.1 S 27 5.6, 30.6 6.5" fill="none" stroke="#a87d3c" stroke-width="0.28" opacity="0.35"/>
<path d="M 6 8.6 C 11 8.0, 16 9.3, 23 8.5" fill="none" stroke="#a87d3c" stroke-width="0.25" opacity="0.3"/>
<rect x="0.2" y="9.6" width="32.8" height="2.3" fill="#c99d55" opacity="0.85"/>
<rect x="0.2" y="9.6" width="32.8" height="0.35" fill="#a87d3c" opacity="0.6"/>
<rect x="2.6" y="0.7" width="28.2" height="1.0" rx="0.5" fill="#ffffff" opacity="0.5"/>
</svg>"""

# each marker's cap in ink and in chalk: (light, mid, dark)
_CAPS = {False: {"black": ("#6a4c93", "#2a1a40", "#000000"), "red": ("#ff5a3d", "#e0201a", "#770e01"),
                 "blue": ("#4b8dff", "#0a5ee8", "#003383"), "green": ("#3ee04a", "#0b9e1c", "#087c04")},
         True: {"black": ("#ffffff", "#ececec", "#b8b8b8"), "red": ("#ffc2df", "#ff6fb5", "#c8407f"),
                "blue": ("#b6efff", "#2fd0ff", "#0f86ad"), "green": ("#fff4b0", "#ffe14a", "#c7a40c")}}


def _render_svg(svg: str, w: float, h: float, dpr: float) -> QImage:
    img = QImage(max(1, round(w * dpr)), max(1, round(h * dpr)), QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(p, QRectF(0, 0, img.width(), img.height()))
    p.end()
    img.setDevicePixelRatio(dpr)
    return img


def marker_image(tool: str, length: float, blackboard: bool, dpr: float = 2.0) -> QImage:
    light, mid, dark = _CAPS[blackboard][tool]
    svg = _MARKER_SVG.replace("{light}", light).replace("{mid}", mid).replace("{dark}", dark)
    return _render_svg(svg, length, length * 10.2 / 56.6, dpr)


def duster_image(width: float, dpr: float = 2.0) -> QImage:
    return _render_svg(_DUSTER_SVG, width, width * 17.2 / 34.4, dpr)


def blackboard_icon(size: int = 22) -> QIcon:
    """Blackboard: a little board, half white and half black, in a grey frame."""
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size * 2
    r = QRectF(s * 0.1, s * 0.2, s * 0.8, s * 0.6)
    p.setPen(QPen(QColor("#6e6e6e"), s * 0.06))
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(r, s * 0.06, s * 0.06)
    half = QPainterPath()
    half.moveTo(r.topRight())
    half.lineTo(r.bottomRight())
    half.lineTo(r.bottomLeft())
    half.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#1d1f1e"))
    clip = QPainterPath()
    clip.addRoundedRect(r.adjusted(s * 0.03, s * 0.03, -s * 0.03, -s * 0.03), s * 0.04, s * 0.04)
    p.drawPath(half.intersected(clip))
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)
