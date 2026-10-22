# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""The whiteboard (IDEAS.md idea 45, 22 October): markers, eraser, Blackboard, Wipe, undo, kept in
the workspace until wiped, Save, Copy and Link to hypothesis…."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

import datetime as dt  # noqa: E402

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from lemmatrix import hypotheses as hy  # noqa: E402
from lemmatrix import layout, storage  # noqa: E402
from lemmatrix import whiteboard as wb  # noqa: E402
from test_ui import app, win  # noqa: E402,F401


# ---- the board itself (no Qt) -----------------------------------------------------------

def test_strokes_round_trip_with_and_without_pressure():
    s = wb.Stroke("red", 6)
    for x in range(10):
        s.add(x * 3, 2 * x)
    s.add(27.2, 18.1)                        # under half a pixel from the last: left out
    assert len(s.points) == 10
    p = wb.Stroke("blue", 10)
    p.add(1, 1, 0.2)
    p.add(5, 5, 1.0)
    assert p.width(0) < p.width(1) == 10
    b = wb.Board()
    b.strokes = [s, p]
    b.blackboard = True
    b.sizes["eraser"] = 70
    b.tool = "eraser"
    again = wb.Board.from_json(b.to_json())
    assert [(x.tool, x.size, x.points) for x in again.strokes] == [(x.tool, x.size, x.points) for x in b.strokes]
    assert again.strokes[0].pressure is None and again.strokes[1].pressure == [0.2, 1.0]
    assert again.blackboard and again.sizes["eraser"] == 70 and again.tool == "eraser"


def test_a_broken_workspace_value_gives_an_empty_board():
    assert wb.Board.from_json("nonsense").strokes == []
    b = wb.Board.from_json({"strokes": [{"t": "red", "p": [1]}, {"t": "weird", "s": 999, "p": [1, 2, 3, 4]}],
                            "sizes": {"black": -5}})
    assert len(b.strokes) == 1 and b.strokes[0].tool == "black" and b.strokes[0].size == wb.MARKER_RANGE[1]
    assert b.sizes["black"] == wb.MARKER_RANGE[0]


def test_sizes_step_inside_their_range():
    assert wb.step_size("black", 4, 1) == 5
    assert wb.step_size("black", 4, -10) == wb.MARKER_RANGE[0]
    assert wb.step_size("eraser", 40, 50) == wb.SIZE_RANGE["eraser"][1]


def test_colours_follow_the_board():
    assert wb.colour("black", False) == wb.INK["black"]
    assert wb.colour("black", True) == wb.CHALK["black"]          # white on the blackboard
    assert wb.colour("blue", True) == wb.CHALK["blue"]


def test_file_names_are_dated_and_never_taken(tmp_path):
    when = dt.datetime(2026, 10, 22, 12, 30)
    assert wb.file_name(when) == "Whiteboard 2026-10-22 12-30.png"
    assert wb.file_name(when, "png", ["whiteboard 2026-10-22 12-30.png"]) == "Whiteboard 2026-10-22 12-30 (2).png"
    db = tmp_path / "Lex.xml"
    p = wb.new_path(db, "jpg", when)
    assert p.parent == tmp_path / "Whiteboard" and p.parent.is_dir() and p.suffix == ".jpg"
    p.write_bytes(b"x")
    assert wb.new_path(db, "jpg", when).name.endswith("(2).jpg")
    assert wb.relative(db, p) == "Whiteboard/Whiteboard 2026-10-22 12-30.jpg"
    assert wb.resolve(db, wb.relative(db, p)) == p
    p.unlink()
    assert wb.resolve(db, "Whiteboard/Whiteboard 2026-10-22 12-30.jpg") is None


def test_drawing_links_find_their_file_and_break_when_it_goes(tmp_path):
    from lemmatrix.model import Database
    db = Database()
    db.path = str(tmp_path / "Lex.xml")
    f = tmp_path / "Whiteboard" / "Whiteboard 2026-10-22 12-30.png"
    f.parent.mkdir()
    f.write_bytes(b"png")
    ln = hy.drawing_link("Whiteboard/Whiteboard 2026-10-22 12-30.png", hy.EVIDENCE)
    assert ln.kind == hy.DRAWING and hy.find(db, None, ln) == f
    assert hy.label(db, None, ln) == "Drawing: Whiteboard 2026-10-22 12-30.png"
    assert not hy.is_gone(db, None, ln)
    assert ln.same_item(hy.drawing_link("Whiteboard/Whiteboard 2026-10-22 12-30.png"))
    f.unlink()
    assert hy.is_gone(db, None, ln)
    assert "Whiteboard folder" in hy.gone_text(ln)


def test_drawing_links_are_kept_in_the_notebook(tmp_path):
    import xml.etree.ElementTree as ET

    from lemmatrix import notebook as nbmod
    book = nbmod.Notebook()
    j = hy.Journal(book)
    h = hy.make(book, j, "2026-10-22", "Tone spreads rightward")
    h.links.append(hy.drawing_link("Whiteboard/a.png", hy.COUNTER, "the tree"))
    root = ET.Element("notebook")
    hy.write_xml(book, root)
    again = nbmod.Notebook()
    hy.read_xml(again, ET.fromstring(ET.tostring(root)))
    ln = again.hypotheses[0].links[0]
    assert (ln.kind, ln.target, ln.mark, ln.note, ln.about) == (hy.DRAWING, "Whiteboard/a.png", hy.COUNTER,
                                                               "the tree", "a.png")


# ---- the window -----------------------------------------------------------------------

def _draw(w, tool, pts, size=None):
    w.pick(tool)
    if size:
        w.board.sizes[tool] = size
    w.sheet.begin(QPointF(*pts[0]))
    for p in pts[1:]:
        w.sheet.extend(QPointF(*p))
    w.sheet.finish()


def _pixel(img: QImage, x, y, scale=wb.SAVE_SCALE) -> QColor:
    return img.pixelColor(int(x * scale), int(y * scale))


def test_tools_menu_opens_it_and_there_is_no_button(win):
    acts = {a.text().replace("&", ""): a for m in win.menuBar().actions() if m.menu()
            for a in m.menu().actions()}
    a = acts["Whiteboard"]
    assert a.shortcut().toString() == "Ctrl+Shift+W"
    a.trigger()
    assert win.whiteboard_window is not None and win.whiteboard_window.isVisible()
    head = [win.head_icons.itemAt(i).widget() for i in range(win.head_icons.count())]
    assert len(head) == 6                    # ɛλicit, χμλ, Cogitate, ?, To Do, Texts and utterances


def test_drawing_with_each_marker_and_rubbing_out(win):
    w = win.open_whiteboard()
    _draw(w, "red", [(100, 100), (200, 100)], 10)
    _draw(w, "blue", [(100, 200), (200, 200)], 10)
    _draw(w, "eraser", [(150, 80), (150, 120)], 30)
    img = w.image()
    assert _pixel(img, 110, 100) == QColor(wb.INK["red"])
    assert _pixel(img, 150, 100) == QColor("#ffffff")            # rubbed out
    assert _pixel(img, 150, 200) == QColor(wb.INK["blue"])
    assert img.width() == wb.SHEET_W * 2 and img.height() == wb.SHEET_H * 2


def test_blackboard_recolours_everything(win):
    w = win.open_whiteboard()
    _draw(w, "black", [(100, 100), (200, 100)], 10)
    _draw(w, "green", [(100, 300), (200, 300)], 10)
    w.blackboard_btn.setChecked(True)
    img = w.image()
    assert _pixel(img, 10, 10) == QColor(wb.BOARD[True])
    assert _pixel(img, 150, 100) == QColor(wb.CHALK["black"])    # black became white
    assert _pixel(img, 150, 300) == QColor(wb.CHALK["green"])    # green became yellow
    w.blackboard_btn.setChecked(False)
    assert _pixel(w.image(), 150, 100) == QColor(wb.INK["black"])


def test_undo_redo_and_wipe(win, monkeypatch):
    w = win.open_whiteboard()
    _draw(w, "red", [(10, 10), (50, 50)])
    _draw(w, "blue", [(60, 60), (90, 90)])
    w.undo()
    assert [s.tool for s in w.board.strokes] == ["red"]
    w.redo()
    assert [s.tool for s in w.board.strokes] == ["red", "blue"]
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    assert not w.ask_wipe() and len(w.board.strokes) == 2
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    assert w.ask_wipe() and w.board.strokes == []
    w.undo()                                 # Wipe comes back with Ctrl+Z
    assert len(w.board.strokes) == 2


def test_double_clicking_the_eraser_offers_to_wipe(win, monkeypatch):
    w = win.open_whiteboard()
    _draw(w, "red", [(10, 10), (50, 50)])
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(1) or QMessageBox.Yes)
    cx, cy = w.tray.PLACES[wb.ERASER][:2]
    QTest.mouseDClick(w.tray, Qt.LeftButton, Qt.NoModifier, QPoint(cx, cy))
    assert asked and w.board.strokes == []
    assert w.board.tool == wb.ERASER         # the click picked it too


def test_clicking_a_marker_in_the_tray_picks_it(win):
    w = win.open_whiteboard()
    for key in ("red", "blue", "green", "black", wb.ERASER):
        cx, cy = w.tray.PLACES[key][:2]
        assert w.tray.hit(QPointF(cx, cy)) == key
        QTest.mouseClick(w.tray, Qt.LeftButton, Qt.NoModifier, QPoint(cx, cy))
        assert w.board.tool == key
    assert w.tray.hit(QPointF(w.tray.width() - 3, 3)) is None


def test_the_mouse_wheel_sets_the_size(win):
    from PySide6.QtGui import QWheelEvent
    w = win.open_whiteboard()
    w.pick("green")
    before = w.board.sizes["green"]
    ev = QWheelEvent(QPointF(100, 100), QPointF(100, 100), QPoint(0, 0), QPoint(0, 240), Qt.NoButton,
                     Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(w.sheet, ev)
    assert w.board.sizes["green"] > before
    assert w.board.sizes["red"] == wb.DEFAULT_SIZE["red"]         # each tool its own size


def test_mouse_strokes(win):
    w = win.open_whiteboard()
    w.pick("blue")
    QTest.mousePress(w.sheet, Qt.LeftButton, Qt.NoModifier, QPoint(20, 20))
    QTest.mouseMove(w.sheet, QPoint(60, 40))
    QTest.mouseMove(w.sheet, QPoint(100, 60))
    QTest.mouseRelease(w.sheet, Qt.LeftButton, Qt.NoModifier, QPoint(100, 60))
    assert len(w.board.strokes) == 1 and w.board.strokes[0].tool == "blue"
    assert w.board.strokes[0].pressure is None


def test_kept_in_the_workspace_until_wiped(win):
    w = win.open_whiteboard()
    _draw(w, "red", [(10, 10), (50, 50)])
    w.set_blackboard(True)
    assert win.doc.write_workspace() or True
    w.close()
    win.whiteboard_window.deleteLater()
    win.whiteboard_window = None
    again = win.open_whiteboard()
    assert [s.tool for s in again.board.strokes] == ["red"] and again.board.blackboard
    assert again.blackboard_btn.isChecked()
    from lemmatrix import workspace as wsmod
    ws = wsmod.load(wsmod.path_for(win.doc.db.path), win.doc.db)
    assert ws.get_dict("whiteboard")["strokes"]                # in the file beside the database


def test_another_database_closes_it(win):
    win.open_whiteboard()
    win.load_database(storage.load(win.doc.db.path))
    assert win.whiteboard_window is None


def test_save_png_and_jpeg_into_the_whiteboard_folder(win):
    w = win.open_whiteboard()
    _draw(w, "red", [(10, 10), (50, 50)], 8)
    p = w.save("png")
    assert p.parent == layout.main_folder(win.doc.db.path) / "Whiteboard" and p.suffix == ".png"
    img = QImage(str(p))
    assert (img.width(), img.height()) == (wb.SHEET_W * 2, wb.SHEET_H * 2)
    assert w.board.saved == "Whiteboard/" + p.name and not w.board.changed
    j = w.save("jpg")
    assert j.suffix == ".jpg" and j != p and not QImage(str(j)).isNull()
    w.set_blackboard(True)
    b = w.save("png")
    assert _pixel(QImage(str(b)), 600, 400) == QColor(wb.BOARD[True])    # saved as it looks
    assert "Whiteboard" in [x[0] for x in win.FOLDERS if x] and layout.WHITEBOARD in win.MADE_ON_DEMAND


def test_save_needs_a_saved_database(win, monkeypatch):
    w = win.open_whiteboard()
    monkeypatch.setattr(win.doc.db, "path", "")
    told = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: told.append(a[2]))
    assert w.save() is None and "Save the database first" in told[0]


def test_copy_puts_the_drawing_on_the_clipboard(win):
    w = win.open_whiteboard()
    _draw(w, "green", [(100, 100), (200, 100)], 12)
    w.copy()
    img = QApplication.clipboard().image()
    assert img.width() == wb.SHEET_W * 2
    assert img.pixelColor(300, 200) == QColor(wb.INK["green"])


def test_link_to_hypothesis_saves_first_then_links(win, monkeypatch):
    from lemmatrix.ui import cogitate
    w = win.open_whiteboard()
    _draw(w, "red", [(10, 10), (50, 50)])
    book = win.doc.notebook
    j = hy.Journal(book)
    h = hy.make(book, j, win.work_date(), "Tone spreads rightward")

    class Picker:
        MAKE = "make"

        def __init__(self, main, link, parent=None):
            self.link = link
            self.choice = h.id
            link.mark = hy.EVIDENCE

        def exec(self):
            return True
    monkeypatch.setattr(cogitate, "LinkPicker", Picker)
    assert w.link_to_hypothesis() is not None
    ln = hy.by_id(book, h.id).links[-1]
    assert ln.kind == hy.DRAWING and ln.mark == hy.EVIDENCE
    f = hy.find(win.doc.db, book, ln)
    assert f is not None and f.is_file() and f.parent.name == "Whiteboard"
    n = len(list(f.parent.iterdir()))
    w.link_to_hypothesis()                   # nothing new drawn: the same file, not another save
    assert len(list(f.parent.iterdir())) == n
    opened = []
    monkeypatch.setattr("PySide6.QtGui.QDesktopServices.openUrl", lambda url: opened.append(url.toLocalFile()))
    assert cogitate.open_link(win, ln)
    assert opened and opened[0].endswith(f.name)


def test_drawings_never_go_into_an_archive(win, tmp_path):
    from lemmatrix import anonymise
    w = win.open_whiteboard()
    _draw(w, "red", [(10, 10), (50, 50)])
    w.save("png")
    for kind in ("anonymous", "ethical"):
        out = tmp_path / kind
        anonymise.export(win.doc.db, win.doc.notebook, out, anonymise.Options.for_kind(kind))
        assert out.is_dir() and not any("Whiteboard" in p.name for p in out.rglob("*"))


def test_a_pen_draws_thinner_when_pressed_lightly(win):
    from PySide6.QtGui import QPointingDevice, QTabletEvent
    w = win.open_whiteboard()
    w.pick("black")
    w.board.sizes["black"] = 20
    dev = QPointingDevice.primaryPointingDevice()

    def send(kind, x, pressure, buttons):
        ev = QTabletEvent(kind, dev, QPointF(x, 100), QPointF(x, 100), pressure, 0.0, 0.0, 0.0, 0.0, 0.0,
                          Qt.NoModifier, Qt.LeftButton, buttons)
        QApplication.sendEvent(w.sheet, ev)
    send(QTabletEvent.TabletPress, 50, 0.1, Qt.LeftButton)
    send(QTabletEvent.TabletMove, 150, 0.1, Qt.LeftButton)
    send(QTabletEvent.TabletMove, 250, 1.0, Qt.LeftButton)
    send(QTabletEvent.TabletRelease, 250, 1.0, Qt.NoButton)
    s = w.board.strokes[-1]
    assert s.pressure is not None and s.width(0) < s.width(2) == 20
    again = wb.Board.from_json(w.board.to_json()).strokes[-1]
    assert again.pressure == s.pressure
