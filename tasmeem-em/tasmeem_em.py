# TASMEEM EM Simulator: a point-and-click front end for openEMS.
# Build an antenna from shapes in pop-up windows, check it in 3D, and click Run.
# em_engine.py does the openEMS work in the background. For full control, the design
# can be turned into a plain openEMS Python script and edited/run in the script editor.

import copy
import csv
import html
import re
import json
import math
import os
import subprocess
import sys
import time

# helper processes (openEMS runs, scripts) read and print text as UTF-8 on every system,
# so names with accents or other scripts never break a run on Windows
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

from PyQt5.QtCore import Qt, QProcess, QProcessEnvironment, QSettings, QDir, QRect, QSize, QUrl, QRegExp
from PyQt5.QtGui import (QColor, QFont, QIcon, QKeySequence, QPainter, QSyntaxHighlighter, QTextCharFormat,
                         QTextCursor, QTextFormat, QDesktopServices, QPixmap)
from PyQt5.QtWidgets import (QAction, QApplication, QCheckBox, QComboBox, QCommandLinkButton, QDialog,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QDialogButtonBox, QDockWidget, QDoubleSpinBox, QFileDialog, QFileSystemModel,
                             QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                             QListWidget, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
                             QStyle, QTabWidget, QTextEdit, QToolBar, QTreeView, QVBoxLayout, QWidget)
import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import em_engine as eng

VERSION = "1.3"
if os.name == "nt":      # Windows version: files saved in Documents, openEMS folder next to the app
    WORK = os.path.join(os.path.expanduser("~"), "Documents", "TASMEEM_EM")
    APPCSXCAD = os.path.join(os.path.dirname(HERE), "openEMS", "AppCSXCAD.exe")
    NO_WINDOW = 0x08000000   # do not flash a console window for helper processes
else:
    WORK = os.path.expanduser("~/work") if os.path.isdir(os.path.expanduser("~/work")) else os.path.expanduser("~")
    WORK = os.path.join(WORK, "TASMEEM_EM")
    APPCSXCAD = "/opt/openEMS/bin/AppCSXCAD"
    NO_WINDOW = 0

STEP_LIMIT_NOTE = ("Warning: openEMS reached its safety limit of time steps before the energy had settled "
                   "(it was only down %.0f dB; a finished run reaches -40 dB). These results are not reliable, "
                   "especially the S11 depth, gain and efficiency. In a script, raise MAX_TIMESTEPS and run again.")

# one color per design step, matching the 3D view (green board, gold copper, red port)
STEP_COLORS = {"step1": "#2e7d32", "step2": "#1565c0", "step3": "#b8860b", "step4": "#c62828",
               "step5": "#6a1b9a"}

STYLE = """
QMainWindow, QDialog { background: #eef2f7; }
QMenuBar { background: #1f3b57; color: white; padding: 2px; }
QMenuBar::item { padding: 4px 10px; background: transparent; }
QMenuBar::item:selected { background: #2f5f8f; border-radius: 3px; }
QMenu { background: white; border: 1px solid #b9c6d6; }
QMenu::item { padding: 5px 24px 5px 20px; }
QMenu::item:selected { background: #dbe8f6; color: #102a43; }
QToolBar { background: #dde7f2; border: none; border-bottom: 1px solid #c3d0de; spacing: 4px; padding: 3px; }
QToolButton { padding: 4px 8px; border-radius: 4px; }
QToolButton:hover { background: #c7d9ee; }
QDockWidget { color: #1f3b57; }
QDockWidget::title { background: #c9d8ea; padding: 5px; font-weight: bold; }
QGroupBox { background: white; border: 1px solid #cfd8e3; border-radius: 7px; margin-top: 14px;
            padding: 8px 6px 4px 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 2px 10px; color: white;
                   border-radius: 4px; font-weight: bold; }
QGroupBox#step1::title { background: %(step1)s; }
QGroupBox#step2::title { background: %(step2)s; }
QGroupBox#step3::title { background: %(step3)s; }
QGroupBox#step4::title { background: %(step4)s; }
QGroupBox#step5::title { background: %(step5)s; }
QPushButton { background: #f4f7fb; border: 1px solid #b9c6d6; border-radius: 5px; padding: 5px 10px; }
QPushButton:hover { background: #e1ecf8; border-color: #7fa3cc; }
QPushButton:pressed { background: #c9dcf2; }
QPushButton:disabled { color: #9aa5b1; background: #eef1f4; }
QPushButton#addShape { background: #fff6dc; border-color: #e2c46a; color: #7a5c00; font-weight: bold; }
QPushButton#addShape:hover { background: #ffecb3; }
QPushButton#runButton { background: #2e7d32; color: white; font-weight: bold; font-size: 11pt;
                        border: none; padding: 10px; }
QPushButton#runButton:hover { background: #388e3c; }
QPushButton#runButton:disabled { background: #a5c8a7; color: #eef5ee; }
QPushButton#stopButton:enabled { background: #c62828; color: white; border: none; font-weight: bold; }
QPushButton#startButton { background: #1565c0; color: white; border: none; font-weight: bold; }
QTabWidget::pane { border: 1px solid #c3d0de; background: white; top: -1px; }
QTabBar::tab { background: #dde7f2; border: 1px solid #c3d0de; padding: 6px 14px; margin-right: 2px;
               border-top-left-radius: 5px; border-top-right-radius: 5px; }
QTabBar::tab:selected { background: white; border-top: 3px solid #1565c0; color: #0d47a1; }
QTabBar::tab:hover:!selected { background: #eaf1f9; }
QListWidget, QTreeView, QPlainTextEdit { border: 1px solid #c3d0de; border-radius: 4px; background: white; }
QListWidget::item:selected, QTreeView::item:selected { background: #ffe58a; color: black; }
QStatusBar { background: #1f3b57; color: white; }
QLabel#resultValue { font-size: 16px; font-weight: bold; color: #1565c0; }
QLabel#resultName { color: #52606d; }
QLabel#hint { color: #52606d; }
QLabel#boxInfo { color: #52606d; }
""" % STEP_COLORS


def blank_spin(hi, suffix="", decimals=3):
    """Spin box that starts empty (0 shows as blank) until the user enters a value."""
    s = spin(0, 0, hi, suffix, decimals)
    s.setSpecialValueText(" ")
    return s


def spin(value, lo, hi, suffix="", decimals=3):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setSingleStep(0.1 if decimals > 1 else 1)
    s.setValue(value)
    s.setSuffix(suffix)
    s.setMinimumWidth(110)
    return s


def tool_icon(kind):
    """Small drawn icons for the toolbar (shapes, port, run, results)."""
    from PyQt5.QtGui import QPen, QBrush, QPolygonF, QPainterPath
    from PyQt5.QtCore import QPointF, QRectF
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    gold, edge = QColor("#e8b923"), QColor("#7a5c00")
    p.setPen(QPen(edge, 3))
    p.setBrush(QBrush(gold))
    if kind == "rectangle":
        p.drawRect(QRectF(10, 18, 44, 28))
    elif kind == "taper":
        p.drawPolygon(QPolygonF([QPointF(6, 26), QPointF(58, 12), QPointF(58, 52), QPointF(6, 38)]))
    elif kind == "arc":
        path = QPainterPath()
        path.arcMoveTo(QRectF(6, 10, 52, 52), 0)
        path.arcTo(QRectF(6, 10, 52, 52), 0, 180)
        path.arcTo(QRectF(18, 22, 28, 28), 180, -180)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "port":
        p.setPen(QPen(QColor("#8b0000"), 3))
        p.setBrush(QBrush(QColor("#e53935")))
        p.drawRect(QRectF(30, 24, 28, 16))
        p.setPen(QPen(QColor("#8b0000"), 5))
        p.drawLine(QPointF(6, 32), QPointF(26, 32))
        p.drawPolygon(QPolygonF([QPointF(26, 24), QPointF(34, 32), QPointF(26, 40)]))
    elif kind == "run":
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#2e7d32")))
        p.drawPolygon(QPolygonF([QPointF(16, 8), QPointF(56, 32), QPointF(16, 56)]))
    elif kind == "stop":
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#c62828")))
        p.drawRoundedRect(QRectF(12, 12, 40, 40), 6, 6)
    elif kind == "check":
        p.setPen(QPen(QColor("#2e7d32"), 8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF([QPointF(10, 34), QPointF(26, 50), QPointF(54, 14)]))
    elif kind == "mesh":
        p.setPen(QPen(QColor("#1565c0"), 2))
        p.setBrush(Qt.NoBrush)
        for v in (8, 14, 20, 32, 44, 50, 56):
            p.drawLine(QPointF(v, 8), QPointF(v, 56))
            p.drawLine(QPointF(8, v), QPointF(56, v))
    elif kind == "s11":
        p.setPen(QPen(QColor("#9e9e9e"), 2))
        p.drawLine(QPointF(6, 58), QPointF(60, 58))
        p.drawLine(QPointF(6, 58), QPointF(6, 4))
        p.setPen(QPen(QColor("#c62828"), 4))
        p.setBrush(Qt.NoBrush)
        path = QPainterPath(QPointF(8, 12))
        path.cubicTo(QPointF(24, 12), QPointF(28, 54), QPointF(32, 54))
        path.cubicTo(QPointF(36, 54), QPointF(40, 12), QPointF(58, 12))
        p.drawPath(path)
    elif kind == "farfield":
        p.setPen(QPen(QColor("#0d47a1"), 3))
        p.setBrush(QBrush(QColor("#64b5f6")))
        path = QPainterPath(QPointF(32, 58))
        path.cubicTo(QPointF(0, 30), QPointF(14, 4), QPointF(32, 4))
        path.cubicTo(QPointF(50, 4), QPointF(64, 30), QPointF(32, 58))
        p.drawPath(path)
        p.setPen(QPen(QColor("#2e7d32"), 6))
        p.drawLine(QPointF(14, 60), QPointF(50, 60))
    elif kind == "script":
        p.setPen(QPen(QColor("#6a1b9a"), 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF([QPointF(22, 14), QPointF(8, 32), QPointF(22, 50)]))
        p.drawPolyline(QPolygonF([QPointF(42, 14), QPointF(56, 32), QPointF(42, 50)]))
    p.end()
    return QIcon(pm)


def app_icon():
    p = os.path.join(HERE, "icon.png")
    return QIcon(p) if os.path.exists(p) else QIcon()


def short_path(path):
    """Path relative to the work folder, for messages."""
    try:
        return os.path.relpath(path, WORK)
    except ValueError:
        return path


SHAPE_FIELDS = {
    # type: [(key, label, default, min, max, suffix)]
    "rectangle": [("x", "Center x", 0, -1000, 1000, " mm"), ("y", "Center y", 0, -1000, 1000, " mm"),
                  ("length", "Length (along x)", 20, 0.01, 1000, " mm"),
                  ("width", "Width (along y)", 5, 0.01, 1000, " mm")],
    "taper": [("start", "Start position", -10, -1000, 1000, " mm"), ("end", "End position", 10, -1000, 1000, " mm"),
              ("center", "Center line", 0, -1000, 1000, " mm"),
              ("width1", "Width at start", 2, 0.01, 1000, " mm"), ("width2", "Width at end", 8, 0.01, 1000, " mm")],
    "arc": [("x", "Center x", 0, -1000, 1000, " mm"), ("y", "Center y", 0, -1000, 1000, " mm"),
            ("r_inner", "Inner radius", 8, 0, 1000, " mm"), ("r_outer", "Outer radius", 12, 0.01, 1000, " mm"),
            ("angle_start", "Start angle", 0, -360, 360, " deg"), ("angle_stop", "Stop angle", 180, -360, 360, " deg")],
}
SHAPE_HELP = {
    "rectangle": "A trace or a plane. Position is the center of the rectangle.",
    "taper": "A trapezoid that changes width from start to end, for example a feed taper.",
    "arc": "A curved strip between an inner and outer radius. 0 deg points along +x.",
}


# ---------------------------------------------------------------- pop-up windows

class ShapeDialog(QDialog):
    """Pop-up window for one shape. Calls preview(shape) whenever a value changes."""

    def __init__(self, parent, shape_type, shape=None, preview=None):
        super().__init__(parent)
        self.shape_type = shape_type
        self.preview = preview
        self.setWindowTitle(("Edit " if shape else "Add ") + shape_type)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(SHAPE_HELP[shape_type]))
        form = QFormLayout()
        self.name = QLineEdit(shape["name"] if shape else shape_type.capitalize())
        form.addRow("Name", self.name)
        if shape_type == "taper":
            self.axis = QComboBox()
            self.axis.addItems(["along x", "along y"])
            if shape and shape.get("axis") == "y":
                self.axis.setCurrentIndex(1)
            self.axis.currentIndexChanged.connect(self.changed)
            form.addRow("Direction", self.axis)
        self.fields = {}
        for key, label, default, lo, hi, suffix in SHAPE_FIELDS[shape_type]:
            w = spin(shape[key] if shape else default, lo, hi, suffix)
            w.valueChanged.connect(self.changed)
            self.fields[key] = w
            form.addRow(label, w)
        lay.addLayout(form)
        tip = QLabel("The 3D view updates as you type (shown in orange).")
        tip.setStyleSheet("color: #b85c00;")
        lay.addWidget(tip)
        self.error = QLabel("")
        self.error.setStyleSheet("color: #c62828; font-weight: bold;")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self.changed()

    def value(self):
        s = {"type": self.shape_type, "name": self.name.text() or self.shape_type}
        for key, w in self.fields.items():
            s[key] = w.value()
        if self.shape_type == "taper":
            s["axis"] = "x" if self.axis.currentIndex() == 0 else "y"
        return s

    def problem(self):
        s = self.value()
        if s["type"] == "taper" and abs(s["end"] - s["start"]) < 1e-6:
            return "Start and end positions must be different."
        if s["type"] == "arc":
            if s["r_inner"] >= s["r_outer"]:
                return "The inner radius must be smaller than the outer radius."
            span = abs(s["angle_stop"] - s["angle_start"])
            if span < 1e-6:
                return "Start and stop angles must be different."
            if span > 360 + 1e-6:
                return "The angle range cannot be more than 360 degrees."
        return ""

    def changed(self, *args):
        msg = self.problem()
        self.error.setText(msg)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(not msg)
        if self.preview and not msg:
            self.preview(self.value())


class PortDialog(QDialog):
    def __init__(self, parent, port, preview=None):
        super().__init__(parent)
        self.preview = preview
        self.setWindowTitle("Port (where the signal goes in)")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Microstrip port. Put it at the start of the feed line, pointing into the board."))
        port = port or {"x": 0, "y": 0, "width": 2.86, "length": 10, "direction": "-x", "impedance": 50}
        form = QFormLayout()
        self.x = spin(port["x"], -1000, 1000, " mm")
        self.y = spin(port["y"], -1000, 1000, " mm")
        self.width = spin(port["width"], 0.01, 1000, " mm")
        self.length = spin(port["length"], 0.1, 1000, " mm")
        self.direction = QComboBox()
        self.direction.addItems(["-x", "+x", "-y", "+y"])
        self.direction.setCurrentText(port["direction"])
        self.z = spin(port["impedance"], 1, 1000, " ohm", 1)
        form.addRow("Start x", self.x)
        form.addRow("Start y", self.y)
        form.addRow("Strip width", self.width)
        form.addRow("Port length", self.length)
        form.addRow("Points toward", self.direction)
        form.addRow("Impedance", self.z)
        lay.addLayout(form)
        for w in [self.x, self.y, self.width, self.length, self.z]:
            w.valueChanged.connect(self.changed)
        self.direction.currentIndexChanged.connect(self.changed)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.changed()

    def value(self):
        return {"x": self.x.value(), "y": self.y.value(), "width": self.width.value(),
                "length": self.length.value(), "direction": self.direction.currentText(),
                "impedance": self.z.value()}

    def changed(self, *args):
        if self.preview:
            self.preview(self.value())


class StartScreen(QDialog):
    """Title screen shown when the app opens. self.choice tells the main window what to do."""

    def __init__(self, parent, recent):
        super().__init__(parent)
        self.choice = None
        self.setWindowTitle("Welcome to TASMEEM EM Simulator")
        self.setMinimumSize(760, 500)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        banner = QWidget()
        banner.setFixedWidth(270)
        banner.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1f3b57, stop:1 #2e7d32);")
        b = QVBoxLayout(banner)
        b.setContentsMargins(24, 30, 24, 24)
        logo = QLabel()
        pix = QPixmap(os.path.join(HERE, "icon.png"))
        if not pix.isNull():
            logo.setPixmap(pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setStyleSheet("background: transparent;")
        b.addWidget(logo)
        t = QLabel("TASMEEM\nEM Simulator")
        t.setStyleSheet("color: white; font-size: 24px; font-weight: bold; background: transparent;")
        b.addWidget(t)
        sub = QLabel("Antenna and EM simulation\nwith openEMS, no scripting needed.")
        sub.setStyleSheet("color: #d7e6f5; font-size: 12px; background: transparent;")
        b.addWidget(sub)
        b.addStretch()
        v = QLabel("Version %s  |  openEMS v0.37\nsdmay27-30, Iowa State University" % VERSION)
        v.setStyleSheet("color: #b7cde3; font-size: 10px; background: transparent;")
        b.addWidget(v)
        outer.addWidget(banner)

        right = QWidget()
        r = QVBoxLayout(right)
        r.setContentsMargins(24, 20, 24, 16)
        head = QLabel("Start")
        head.setStyleSheet("font-size: 18px; font-weight: bold; color: #1f3b57;")
        r.addWidget(head)
        for key, title, desc in [
                ("empty", "New empty design", "Start with a blank board and build the antenna from shapes."),
                ("open", "Open project...", "Open a saved design (.json)."),
                ("script", "Open openEMS script...", "Edit and run your own openEMS Python script.")]:
            btn = QCommandLinkButton(title, desc)
            btn.clicked.connect(lambda _, k=key: self.pick(k))
            r.addWidget(btn)
        r.addWidget(QLabel("Recent files"))
        self.recent = QListWidget()
        self.recent.setMaximumHeight(110)
        for f in recent:
            self.recent.addItem(f)
        if not recent:
            self.recent.addItem("(nothing yet)")
            self.recent.setEnabled(False)
        self.recent.itemDoubleClicked.connect(lambda item: self.pick("recent:" + item.text()))
        r.addWidget(self.recent)
        self.show_again = QCheckBox("Show this screen when the app opens")
        self.show_again.setChecked(True)
        r.addWidget(self.show_again)
        outer.addWidget(right, 1)

    def pick(self, key):
        self.choice = key
        self.accept()


# ---------------------------------------------------------------- script editor

class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)

        def fmt(color, bold=False, italic=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Bold)
            f.setFontItalic(italic)
            return f

        kw = ["and", "as", "assert", "break", "class", "continue", "def", "del", "elif", "else", "except",
              "False", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "None",
              "not", "or", "pass", "raise", "return", "True", "try", "while", "with", "yield"]
        self.rules = [(QRegExp(r"\b%s\b" % k), fmt("#0033b3", True)) for k in kw]
        self.rules += [(QRegExp(r"\b(print|range|len|min|max|list|dict|abs|open|str|float|int)\b"), fmt("#7a3e9d")),
                       (QRegExp(r"\b[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?\b"), fmt("#1750eb")),
                       (QRegExp(r"\b[A-Z_][A-Z0-9_]{2,}\b"), fmt("#871094", True)),
                       (QRegExp(r"\"[^\"]*\""), fmt("#067d17")),
                       (QRegExp(r"'[^']*'"), fmt("#067d17")),
                       (QRegExp(r"#[^\n]*"), fmt("#8c8c8c", italic=True))]

    def highlightBlock(self, text):
        for rx, f in self.rules:
            i = rx.indexIn(text, 0)
            while i >= 0:
                n = rx.matchedLength()
                self.setFormat(i, n, f)
                i = rx.indexIn(text, i + n)


class LineNumbers(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.number_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_numbers(event)


class CodeEditor(QPlainTextEdit):
    """Plain text editor with line numbers and Python colors. self.path is the file (None = new)."""

    def __init__(self, path=None, text=""):
        super().__init__()
        self.path = path
        f = QFont("Consolas" if os.name == "nt" else "DejaVu Sans Mono")
        f.setStyleHint(QFont.Monospace)
        f.setPointSize(10)
        self.setFont(f)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.numbers = LineNumbers(self)
        self.blockCountChanged.connect(lambda _: self.setViewportMargins(self.number_width(), 0, 0, 0))
        self.updateRequest.connect(self.update_numbers)
        self.cursorPositionChanged.connect(self.mark_line)
        self.setViewportMargins(self.number_width(), 0, 0, 0)
        if path is None or path.endswith(".py"):
            self.highlighter = PythonHighlighter(self.document())
        self.setPlainText(text)
        self.document().setModified(False)
        self.mark_line()

    def number_width(self):
        return 14 + self.fontMetrics().horizontalAdvance("9") * max(3, len(str(self.blockCount())))

    def update_numbers(self, rect, dy):
        if dy:
            self.numbers.scroll(0, dy)
        else:
            self.numbers.update(0, rect.y(), self.numbers.width(), rect.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.numbers.setGeometry(QRect(cr.left(), cr.top(), self.number_width(), cr.height()))

    def paint_numbers(self, event):
        painter = QPainter(self.numbers)
        painter.fillRect(event.rect(), QColor("#eef2f7"))
        block = self.firstVisibleBlock()
        n = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        h = int(self.blockBoundingRect(block).height())
        current = self.textCursor().blockNumber()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible():
                painter.setPen(QColor("#1565c0") if n == current else QColor("#8a99a8"))
                painter.drawText(0, top, self.numbers.width() - 6, h, Qt.AlignRight, str(n + 1))
            block = block.next()
            top += h
            n += 1

    def mark_line(self):
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(QColor("#fff8dc"))
        sel.format.setProperty(QTextFormat.FullWidthSelection, True)
        sel.cursor = self.textCursor()
        sel.cursor.clearSelection()
        self.setExtraSelections([sel])

    def title(self):
        name = os.path.basename(self.path) if self.path else "untitled.py"
        return name + (" *" if self.document().isModified() else "")


# ---------------------------------------------------------------- main window

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        for d in [WORK, os.path.join(WORK, "projects"), os.path.join(WORK, "scripts"), os.path.join(WORK, "em_runs")]:
            os.makedirs(d, exist_ok=True)
        self.settings = QSettings("TASMEEM", "EM Simulator")
        self.setWindowIcon(app_icon())
        self.resize(1500, 920)
        self.project = self.empty_project()
        self.project_file = None
        self.dirty = False
        self.temp_shape = None      # shape being edited in a pop-up (drawn in orange)
        self.temp_port = None
        self.proc = None
        self.run_dir = None
        self.results = None
        self.results_range = None
        self.view_angle = (30, -60)
        self.something_drawn = False
        self.stopped = False
        self.log_buffer = ""
        self.build_actions()

        self.tabs = QTabWidget()
        self.view_tab = self.build_view_tab()
        self.results_tab = self.build_results_tab()
        self.ff_tab = self.build_farfield_tab()
        self.editor_tab = self.build_editor_tab()
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas" if os.name == "nt" else "DejaVu Sans Mono", 9))
        for w, name in [(self.view_tab, "3D View"), (self.results_tab, "S11 Results"), (self.ff_tab, "Far Field"),
                        (self.editor_tab, "Script Editor"), (self.log, "Log")]:
            self.tabs.addTab(w, name)
        self.setCentralWidget(self.tabs)

        self.design_dock = QDockWidget("Design", self)
        self.design_dock.setObjectName("design_dock")
        self.design_dock.setWidget(self.build_design_panel())
        self.design_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.design_dock)
        self.files_dock = QDockWidget("File Browser", self)
        self.files_dock.setObjectName("files_dock")
        self.files_dock.setWidget(self.build_file_browser())
        self.files_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.files_dock)
        self.tabifyDockWidget(self.design_dock, self.files_dock)
        self.design_dock.raise_()
        self.resizeDocks([self.design_dock], [475], Qt.Horizontal)

        self.build_menus()
        self.build_toolbar()
        self.statusBar().showMessage("Ready. Work folder: " + WORK)
        self.load_into_form()
        self.update_title()

    # ---------------------------------------------------------------- actions and menus

    def act(self, text, slot, shortcut=None, icon=None, tip=None):
        a = QAction(text, self)
        a.triggered.connect(lambda checked=False: slot())
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if icon is not None:
            a.setIcon(self.style().standardIcon(icon))
        if tip:
            a.setStatusTip(tip)
        return a

    def build_actions(self):
        S = QStyle
        self.a_new = self.act("New empty design", self.new_empty, "Ctrl+N", S.SP_FileIcon)
        self.a_open = self.act("Open project...", self.open_project, "Ctrl+O", S.SP_DialogOpenButton)
        self.a_save = self.act("Save", self.save_current, "Ctrl+S", S.SP_DialogSaveButton,
                               "Save the project, or the script when the Script Editor is open")
        self.a_save_as = self.act("Save project as...", lambda: self.save_project(True), "Ctrl+Shift+S")
        self.a_new_script = self.act("New script", self.new_script, None, S.SP_FileIcon)
        self.a_open_script = self.act("Open script...", self.open_script_dialog, "Ctrl+Shift+O", S.SP_DialogOpenButton)
        self.a_save_script = self.act("Save script", self.save_script, None, S.SP_DialogSaveButton)
        self.a_save_script_as = self.act("Save script as...", lambda: self.save_script(True))
        self.a_touchstone = self.act("Save S11 as Touchstone (.s1p)...", self.save_touchstone)
        self.a_start = self.act("Start screen...", self.show_start_screen)
        self.a_quit = self.act("Quit", self.close, "Ctrl+Q")

        self.a_undo = self.act("Undo", lambda: self.edit_call("undo"), "Ctrl+Z")
        self.a_redo = self.act("Redo", lambda: self.edit_call("redo"), "Ctrl+Y")
        self.a_cut = self.act("Cut", lambda: self.edit_call("cut"), "Ctrl+X")
        self.a_copy = self.act("Copy", lambda: self.edit_call("copy"), "Ctrl+C")
        self.a_paste = self.act("Paste", lambda: self.edit_call("paste"), "Ctrl+V")
        self.a_select_all = self.act("Select all", lambda: self.edit_call("selectAll"), "Ctrl+A")
        self.a_find = self.act("Find in script...", self.find_text, "Ctrl+F")
        self.a_edit_shape = self.act("Edit selected shape...", self.edit_shape, "Ctrl+E", S.SP_FileDialogDetailedView,
                                     "Edit the selected shape")
        self.a_dup_shape = self.act("Duplicate selected shape", self.duplicate_shape, "Ctrl+D", S.SP_FileLinkIcon,
                                    "Duplicate the selected shape")
        self.a_del_shape = self.act("Delete selected shape", self.delete_shape, "Delete")
        self.a_del_shape.setShortcutContext(Qt.WidgetShortcut)
        for a in [self.a_undo, self.a_redo, self.a_cut, self.a_copy, self.a_paste, self.a_select_all]:
            a.setShortcutContext(Qt.WidgetShortcut)     # let text boxes keep their own shortcuts

        self.a_check = self.act("Check design", self.check_only, "F7", S.SP_DialogApplyButton,
                                "Look for problems before running")
        self.a_run = self.act("Check 3D and run design", self.check_and_run, "Ctrl+R", S.SP_MediaPlay)
        self.a_run_script = self.act("Run script", self.run_script, "F5", S.SP_MediaPlay)
        self.a_stop = self.act("Stop simulation", self.stop_run, "Shift+F5", S.SP_MediaStop)
        self.a_stop_script = self.act("Stop", self.stop_run, None, S.SP_MediaStop)
        self.a_mesh = self.act("Show mesh", self.show_mesh_view, None, S.SP_FileDialogContentsView,
                               "Show the design with its simulation mesh in AppCSXCAD")
        self.a_script_mesh = self.act("Show script model in AppCSXCAD", self.show_script_model)
        self.a_show_log = self.act("Show log", lambda: self.tabs.setCurrentWidget(self.log), "Ctrl+L")
        self.a_stop.setEnabled(False)
        self.a_stop_script.setEnabled(False)

        self.a_gen_script = self.act("Generate script from design", self.generate_script, "Ctrl+G",
                                     S.SP_FileDialogDetailedView, "Write the openEMS script for the current design")
        self.a_appcsxcad = self.act("Open AppCSXCAD viewer", self.open_appcsxcad)
        self.a_open_run = self.act("Open last run folder", self.open_run_folder, None, S.SP_DirOpenIcon)
        self.a_open_work = self.act("Open work folder", lambda: self.open_folder(WORK), None, S.SP_DirHomeIcon)

        self.a_add_rect = self.act("Add rectangle...", lambda: self.add_shape("rectangle"), "Ctrl+Shift+R",
                                   tip="Add a rectangle (trace or plane)")
        self.a_add_taper = self.act("Add taper...", lambda: self.add_shape("taper"), "Ctrl+Shift+T",
                                    tip="Add a taper (a strip that changes width)")
        self.a_add_arc = self.act("Add arc...", lambda: self.add_shape("arc"), "Ctrl+Shift+A",
                                  tip="Add an arc (curved strip between two radii)")
        self.a_set_port = self.act("Set port...", self.set_port, "Ctrl+Shift+P", tip="Set the port (signal input)")
        self.a_tab_s11 = self.act("S11 results", lambda: self.tabs.setCurrentWidget(self.results_tab), None,
                                  tip="Show S11, Smith chart, impedance and the data table")
        self.a_tab_ff = self.act("Far field", lambda: self.tabs.setCurrentWidget(self.ff_tab), None,
                                 tip="Show the 3D radiation pattern, gain and efficiency")
        self.a_tab_script = self.act("Script editor", lambda: self.tabs.setCurrentWidget(self.editor_tab), None,
                                     tip="Open the Script Editor")
        for a, k in [(self.a_add_rect, "rectangle"), (self.a_add_taper, "taper"), (self.a_add_arc, "arc"),
                     (self.a_set_port, "port"), (self.a_check, "check"), (self.a_mesh, "mesh"),
                     (self.a_run, "run"), (self.a_stop, "stop"), (self.a_tab_s11, "s11"), (self.a_tab_ff, "farfield"),
                     (self.a_tab_script, "script"), (self.a_run_script, "run"), (self.a_stop_script, "stop")]:
            a.setIcon(tool_icon(k))
        self.a_keys = self.act("Keyboard shortcuts", self.show_shortcuts, "Ctrl+/")

        self.a_help = self.act("Quick start guide", self.show_help, "F1", S.SP_DialogHelpButton)
        self.a_shapes_help = self.act("Shapes and ports reference", self.show_shapes_help)
        self.a_about = self.act("About TASMEEM EM Simulator", self.show_about)

    def build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&File")
        for a in [self.a_new, self.a_open, self.a_save, self.a_save_as, None,
                  self.a_new_script, self.a_open_script, self.a_save_script, self.a_save_script_as, None,
                  self.a_touchstone, None]:
            m.addSeparator() if a is None else m.addAction(a)
        self.recent_menu = m.addMenu("Recent files")
        self.recent_menu.aboutToShow.connect(self.fill_recent_menu)
        m.addSeparator()
        m.addAction(self.a_start)
        m.addAction(self.a_quit)

        m = mb.addMenu("&Edit")
        for a in [self.a_undo, self.a_redo, None, self.a_cut, self.a_copy, self.a_paste, self.a_select_all, None,
                  self.a_find, None, self.a_add_rect, self.a_add_taper, self.a_add_arc, self.a_set_port, None,
                  self.a_edit_shape, self.a_dup_shape, self.a_del_shape]:
            m.addSeparator() if a is None else m.addAction(a)

        m = mb.addMenu("&Debug")
        for a in [self.a_check, self.a_mesh, self.a_run, None, self.a_run_script, self.a_script_mesh, None,
                  self.a_stop, self.a_show_log]:
            m.addSeparator() if a is None else m.addAction(a)

        m = mb.addMenu("&Tools")
        for a in [self.a_gen_script, None, self.a_appcsxcad, None, self.a_open_run,
                  self.a_open_work]:
            m.addSeparator() if a is None else m.addAction(a)

        m = mb.addMenu("&Window")
        m.addAction(self.design_dock.toggleViewAction())
        m.addAction(self.files_dock.toggleViewAction())
        m.addSeparator()
        for i, name in enumerate(["3D View", "S11 Results", "Far Field", "Script Editor", "Log"]):
            m.addAction(self.act(name, lambda i=i: self.tabs.setCurrentIndex(i), "Ctrl+%d" % (i + 1)))
        m.addSeparator()
        m.addAction(self.act("Reset layout", self.reset_layout))

        m = mb.addMenu("&Help")
        for a in [self.a_help, self.a_shapes_help, self.a_keys, None, self.a_about]:
            m.addSeparator() if a is None else m.addAction(a)

    def build_toolbar(self):
        tb = QToolBar("Main")
        tb.setObjectName("main_toolbar")
        tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
        tb.setIconSize(QSize(26, 26))
        tb.setMovable(False)
        for a in [self.a_new, self.a_open, self.a_save, None,
                  self.a_add_rect, self.a_add_taper, self.a_add_arc, self.a_set_port, None,
                  self.a_edit_shape, self.a_dup_shape, None,
                  self.a_check, self.a_mesh, self.a_run, self.a_stop, None,
                  self.a_tab_s11, self.a_tab_ff, self.a_tab_script, None, self.a_open_run]:
            if a is None:
                tb.addSeparator()
                continue
            tb.addAction(a)
            tip = a.statusTip() or a.text().rstrip(".")
            if a.shortcut().toString():
                tip += "  (" + a.shortcut().toString(QKeySequence.NativeText) + ")"
            a.setToolTip(tip)
        self.addToolBar(tb)

    def edit_call(self, name):
        w = QApplication.focusWidget()
        if w is not None and hasattr(w, name):
            getattr(w, name)()

    # ---------------------------------------------------------------- layout

    def build_design_panel(self):
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(6, 0, 6, 4)
        lay.setSpacing(2)

        g = QGroupBox("1. Board (substrate)")
        g.setObjectName("step1")
        f = QGridLayout(g)
        f.setHorizontalSpacing(8)
        self.b_len = blank_spin(1000, " mm")
        self.b_wid = blank_spin(1000, " mm")
        self.b_th = blank_spin(50, " mm")
        self.material = QComboBox()
        self.material.addItems(["Choose...", "FR-4", "Rogers RO4003C", "Custom"])
        self.material.setItemData(1, "epsR 4.3, loss tangent 0.025", Qt.ToolTipRole)
        self.material.setItemData(2, "epsR 3.38, loss tangent 0.0027", Qt.ToolTipRole)
        self.material.setItemData(3, "Type your own permittivity and loss tangent", Qt.ToolTipRole)
        self.material.currentIndexChanged.connect(self.material_changed)
        self.b_eps = blank_spin(100, "", 3)
        self.b_tan = blank_spin(1, "", 4)
        self.b_gnd = QCheckBox("Ground plane under the board")
        self.b_gnd.setChecked(True)
        for row, (l1, w1, l2, w2) in enumerate([("Length (x)", self.b_len, "Width (y)", self.b_wid),
                                                 ("Thickness", self.b_th, "Material", self.material),
                                                 ("Permittivity", self.b_eps, "Loss tangent", self.b_tan)]):
            f.addWidget(QLabel(l1), row, 0)
            f.addWidget(w1, row, 1)
            f.addWidget(QLabel(l2), row, 2)
            f.addWidget(w2, row, 3)
        f.addWidget(self.b_gnd, 3, 0, 1, 4)
        for w in (self.b_len, self.b_wid, self.b_th, self.material, self.b_eps, self.b_tan):
            w.setMinimumWidth(88)
        lay.addWidget(g)

        g = QGroupBox("2. Frequency and mesh")
        g.setObjectName("step2")
        f = QGridLayout(g)
        f.setHorizontalSpacing(8)
        self.f_start = blank_spin(200, " GHz")
        self.f_stop = blank_spin(200, " GHz")
        self.mesh = QComboBox()
        self.mesh.addItems(["coarse", "normal", "fine"])
        self.mesh.setCurrentText("normal")
        self.box_label = QLabel()
        self.box_label.setObjectName("boxInfo")
        f.addWidget(QLabel("Start"), 0, 0)
        f.addWidget(self.f_start, 0, 1)
        f.addWidget(QLabel("Stop"), 0, 2)
        f.addWidget(self.f_stop, 0, 3)
        f.addWidget(QLabel("Mesh"), 1, 0)
        f.addWidget(self.mesh, 1, 1)
        f.addWidget(self.box_label, 2, 0, 1, 4)
        for w in (self.f_start, self.f_stop, self.mesh):
            w.setMinimumWidth(88)
        self.box_label.setWordWrap(True)
        lay.addWidget(g)

        g = QGroupBox("3. Shapes (top copper)")
        g.setObjectName("step3")
        v = QVBoxLayout(g)
        row = QHBoxLayout()
        for t in ["rectangle", "taper", "arc"]:
            b = QPushButton("+ " + t.capitalize())
            b.setObjectName("addShape")
            b.clicked.connect(lambda _, t=t: self.add_shape(t))
            row.addWidget(b)
        v.addLayout(row)
        self.shape_list = QListWidget()
        self.shape_list.setMinimumHeight(70)
        self.shape_list.setMaximumHeight(105)
        self.shape_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.shape_list.setTextElideMode(Qt.ElideRight)     # long names end in "..."; full text in the tooltip
        self.shape_list.itemDoubleClicked.connect(lambda *_: self.edit_shape())
        self.shape_list.currentRowChanged.connect(lambda *_: self.redraw())
        self.shape_list.addAction(self.a_del_shape)
        v.addWidget(self.shape_list)
        row = QHBoxLayout()
        for text, fn in [("Edit", self.edit_shape), ("Duplicate", self.duplicate_shape),
                         ("Delete", self.delete_shape)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        v.addLayout(row)
        lay.addWidget(g)

        g = QGroupBox("4. Port")
        g.setObjectName("step4")
        v = QHBoxLayout(g)
        self.port_label = QLabel()
        self.port_label.setWordWrap(True)
        v.addWidget(self.port_label, 1)
        b = QPushButton("Set port...")
        b.clicked.connect(self.set_port)
        v.addWidget(b, 0, Qt.AlignVCenter)
        lay.addWidget(g)
        lay.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        g = QGroupBox("5. Check and run")
        g.setObjectName("step5")
        v = QVBoxLayout(g)
        self.run_btn = QPushButton("Check 3D and Run")
        self.run_btn.setObjectName("runButton")
        self.run_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.run_btn.clicked.connect(self.check_and_run)
        v.addWidget(self.run_btn)
        self.stop_btn = QPushButton("Stop simulation")
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_run)
        v.addWidget(self.stop_btn)
        self.status = QLabel("Ready.")
        self.status.setWordWrap(True)
        self.status.setMinimumWidth(10)
        v.addWidget(self.status)

        side = QWidget()
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.addWidget(scroll, 1)
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(6, 0, 6, 6)
        bl.addWidget(g)
        sv.addWidget(box)
        side.setMinimumWidth(470)

        for w in [self.b_len, self.b_wid, self.b_th, self.b_eps, self.b_tan, self.f_start, self.f_stop]:
            w.valueChanged.connect(self.form_changed)
        self.b_gnd.stateChanged.connect(self.form_changed)
        self.mesh.currentIndexChanged.connect(self.form_changed)
        return side

    def build_file_browser(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        for icon, tip, fn in [(QStyle.SP_FileDialogToParent, "Up", self.browse_up),
                              (QStyle.SP_DirHomeIcon, "Work folder", lambda: self.browse_to(WORK)),
                              (QStyle.SP_DirOpenIcon, "Other folder...", self.browse_choose),
                              (QStyle.SP_BrowserReload, "Refresh", lambda: self.browse_to(self.browse_dir))]:
            b = QPushButton(tip)
            b.setIcon(self.style().standardIcon(icon))
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        v.addLayout(row)
        self.browse_label = QLabel()
        self.browse_label.setWordWrap(True)
        self.browse_label.setStyleSheet("color: #52606d;")
        v.addWidget(self.browse_label)
        self.fs_model = QFileSystemModel()
        self.fs_model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)
        self.tree = QTreeView()
        self.tree.setModel(self.fs_model)
        for col in (1, 2, 3):
            self.tree.setColumnHidden(col, col != 3)
        self.tree.setColumnWidth(0, 260)
        self.tree.doubleClicked.connect(lambda idx: self.open_any(self.fs_model.filePath(idx)))
        v.addWidget(self.tree)
        hint = QLabel("Double-click: .json opens a design (or its results), .py/.m/.txt opens in the "
                      "Script Editor, .xml opens in AppCSXCAD.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #52606d; font-size: 9pt;")
        v.addWidget(hint)
        self.browse_dir = WORK
        self.fs_model.setRootPath(WORK)
        self.browse_to(WORK)
        return w

    def build_view_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.fig3d = Figure(figsize=(8, 6))
        self.fig3d.patch.set_facecolor("#ffffff")
        self.canvas3d = FigureCanvasQTAgg(self.fig3d)
        self.ax3d = self.fig3d.add_subplot(111, projection="3d")
        self.triad = self.fig3d.add_axes([0.005, 0.005, 0.14, 0.14])
        self.triad.set_axis_off()
        self.canvas3d.mpl_connect("motion_notify_event", self.on_3d_drag)
        self.canvas3d.mpl_connect("button_release_event", lambda e: self.update_triad(True))
        row = QHBoxLayout()
        for text, elev, azim in [("3D view", 30, -60), ("Top view", 90, -90), ("Side view", 0, -90)]:
            b = QPushButton(text)
            b.clicked.connect(lambda _, e=elev, a=azim: self.set_view(e, a))
            row.addWidget(b)
        legend = QLabel('Drag to rotate.  <span style="color:#b8860b">&#9632;</span> copper  '
                        '<span style="color:#e53935">&#9632;</span> port  '
                        '<span style="color:#5aa05a">&#9632;</span> board (height not to scale)  '
                        '<span style="color:#ff9a3c">&#9632;</span> being edited')
        row.addWidget(legend)
        row.addStretch()
        v.addLayout(row)
        v.addWidget(self.canvas3d, 1)
        self.fig3d.subplots_adjust(left=0, right=1, bottom=0, top=0.95)
        return w

    def build_results_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        grid = QGridLayout()
        self.r_labels = {}
        for i, (key, text) in enumerate([("f_res", "Resonance"), ("s11", "S11 at resonance"),
                                         ("bw", "-10 dB bandwidth"), ("dir", "Directivity"), ("gain", "Gain"),
                                         ("eff", "Radiation efficiency"), ("time", "Solver time")]):
            name = QLabel(text)
            name.setObjectName("resultName")
            grid.addWidget(name, 0, i)
            lab = QLabel("-")
            lab.setObjectName("resultValue")
            grid.addWidget(lab, 1, i)
            self.r_labels[key] = lab
        v.addLayout(grid)
        self.r_note = QLabel("Run a simulation to see results here.")
        self.r_note.setWordWrap(True)
        self.r_note.setObjectName("hint")
        v.addWidget(self.r_note)

        self.rtabs = QTabWidget()
        # S11 plot with markers
        page = QWidget()
        pv = QVBoxLayout(page)
        self.fig_s11 = Figure(figsize=(8, 5))
        self.canvas_s11 = FigureCanvasQTAgg(self.fig_s11)
        self.canvas_s11.mpl_connect("button_press_event", self.s11_click)
        row = QHBoxLayout()
        row.addWidget(NavigationToolbar2QT(self.canvas_s11, page))
        hint = QLabel("Click the curve to place a marker. Right-click to remove all markers.")
        hint.setObjectName("hint")
        row.addWidget(hint)
        row.addStretch()
        clear = QPushButton("Clear markers")
        clear.clicked.connect(self.clear_markers)
        row.addWidget(clear)
        pv.addLayout(row)
        pv.addWidget(self.canvas_s11, 1)
        self.marker_label = QLabel("")
        self.marker_label.setWordWrap(True)
        pv.addWidget(self.marker_label)
        self.rtabs.addTab(page, "S11 (dB)")
        # Smith chart and impedance
        self.fig_smith, self.canvas_smith = Figure(figsize=(6, 6)), None
        self.canvas_smith = FigureCanvasQTAgg(self.fig_smith)
        page = QWidget()
        pv = QVBoxLayout(page)
        pv.addWidget(NavigationToolbar2QT(self.canvas_smith, page))
        pv.addWidget(self.canvas_smith, 1)
        self.rtabs.addTab(page, "Smith chart")
        self.fig_z = Figure(figsize=(8, 5))
        self.canvas_z = FigureCanvasQTAgg(self.fig_z)
        page = QWidget()
        pv = QVBoxLayout(page)
        pv.addWidget(NavigationToolbar2QT(self.canvas_z, page))
        pv.addWidget(self.canvas_z, 1)
        self.rtabs.addTab(page, "Input impedance")
        # data table
        page = QWidget()
        pv = QVBoxLayout(page)
        row = QHBoxLayout()
        self.only_range = QCheckBox("Only my frequency range")
        self.only_range.setChecked(True)
        self.only_range.stateChanged.connect(lambda *_: self.fill_table())
        row.addWidget(self.only_range)
        row.addStretch()
        b1 = QPushButton("Copy table")
        b1.clicked.connect(self.copy_table)
        b2 = QPushButton("Export CSV...")
        b2.clicked.connect(self.export_csv)
        row.addWidget(b1)
        row.addWidget(b2)
        pv.addLayout(row)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        pv.addWidget(self.table, 1)
        self.rtabs.addTab(page, "Data table")
        v.addWidget(self.rtabs, 1)

        self.run_path_label = QLabel("")
        self.run_path_label.setWordWrap(True)
        self.run_path_label.setMinimumWidth(10)
        v.addWidget(self.run_path_label)
        self.markers = []
        return w

    def build_farfield_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(QLabel("View"))
        self.ff_view = QComboBox()
        self.ff_view.addItems(["3D pattern", "2D cuts", "Polar cuts"])
        self.ff_view.currentIndexChanged.connect(lambda *_: self.show_far_field())
        row.addWidget(self.ff_view)
        row.addSpacing(20)
        row.addWidget(QLabel("Frequency"))
        self.ff_freq = spin(0, 0, 1000, " GHz", 4)
        self.ff_freq.setSingleStep(0.01)
        row.addWidget(self.ff_freq)
        self.ff_calc = QPushButton("Calculate at this frequency")
        self.ff_calc.setObjectName("startButton")
        self.ff_calc.clicked.connect(self.calc_far_field)
        row.addWidget(self.ff_calc)
        row.addStretch()
        exp = QPushButton("Export CSV...")
        exp.clicked.connect(self.export_far_field)
        row.addWidget(exp)
        v.addLayout(row)
        grid = QGridLayout()
        self.ff_labels = {}
        for i, (key, text) in enumerate([("f", "Frequency"), ("dir", "Directivity"), ("gain", "Gain"),
                                         ("rgain", "Realized gain"), ("eff", "Radiation efficiency"),
                                         ("max", "Strongest direction")]):
            name = QLabel(text)
            name.setObjectName("resultName")
            grid.addWidget(name, 0, i)
            lab = QLabel("-")
            lab.setObjectName("resultValue")
            grid.addWidget(lab, 1, i)
            self.ff_labels[key] = lab
        v.addLayout(grid)
        self.ff_note = QLabel("Run a simulation; the far field at the resonance is calculated automatically.")
        self.ff_note.setObjectName("hint")
        self.ff_note.setWordWrap(True)
        v.addWidget(self.ff_note)
        self.fig_ff = Figure(figsize=(8, 6))
        self.canvas_ff = FigureCanvasQTAgg(self.fig_ff)
        v.addWidget(NavigationToolbar2QT(self.canvas_ff, w))
        v.addWidget(self.canvas_ff, 1)
        self.ff = None
        self.ff_proc = None
        return w

    def build_editor_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        tb = QToolBar()
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.editor_toolbar = tb
        v.addWidget(tb)
        info = QLabel("  Click \"Generate from design\" for the default openEMS script of your design, "
                      "then change it or write your own. Run it with F5; results show in the Results tab.")
        info.setWordWrap(True)
        info.setStyleSheet("background: #fff6dc; color: #7a5c00; padding: 5px; border-bottom: 1px solid #e2c46a;")
        v.addWidget(info)
        self.editors = QTabWidget()
        self.editors.setTabsClosable(True)
        self.editors.setMovable(True)
        self.editors.tabCloseRequested.connect(self.close_editor)
        v.addWidget(self.editors, 1)
        return w

    def fill_editor_toolbar(self):
        tb = self.editor_toolbar
        for a in [self.a_new_script, self.a_open_script, self.a_save_script, None, self.a_gen_script, None,
                  self.a_run_script, self.a_stop_script, self.a_script_mesh]:
            tb.addSeparator() if a is None else tb.addAction(a)

    def reset_layout(self):
        for d in (self.design_dock, self.files_dock):
            d.setFloating(False)
            d.show()
            self.addDockWidget(Qt.LeftDockWidgetArea, d)
        self.tabifyDockWidget(self.design_dock, self.files_dock)
        self.design_dock.raise_()
        self.resizeDocks([self.design_dock], [475], Qt.Horizontal)

    # ---------------------------------------------------------------- project <-> form

    def empty_project(self):
        """A new design starts with nothing filled in, like a blank CST project."""
        return {"name": "New design",
                "board": {"length": 0.0, "width": 0.0, "thickness": 0.0, "epsR": 0.0, "tanD": 0.0, "ground": True},
                "airbox": [0.0, 0.0, 0.0], "freq": {"start": 0.0, "stop": 0.0}, "mesh": "normal",
                "shapes": [], "port": None}

    def board_ready(self):
        b = self.project["board"]
        return b["length"] > 0 and b["width"] > 0

    def update_box(self):
        """Simulation (air) box: the board plus about half a wavelength on every side."""
        b = self.project["board"]
        fs, fe = self.project["freq"]["start"], self.project["freq"]["stop"]
        if self.board_ready() and fs > 0 and fe > fs:
            lam = 299.792458 / ((fs + fe) / 2)        # mm, at the center frequency
            lam = max(lam, 0.5 * 299.792458 / fs)      # wide ranges: keep a quarter wavelength at the low end
            xy = round((max(b["length"], b["width"]) + lam) / 10) * 10
            self.project["airbox"] = [float(xy), float(xy), float(round(1.2 * lam / 10) * 10)]
        self.update_mesh_info()

    def update_mesh_info(self):
        ab = self.project["airbox"]
        text = "Simulation box %.0f x %.0f x %.0f mm" % tuple(ab) if ab[0] > 0 else \
            "Simulation box: set steps 1 and 2 first"
        tip = "Simulation box around the board (set automatically)."
        f = self.project["freq"]
        if ab[0] > 0 and self.board_ready() and 0 < f["start"] < f["stop"]:
            try:
                n = eng.estimate_cells(self.project)
                text += ", about %s mesh cells" % ("%.1f million" % (n / 1e6) if n >= 1e6 else
                                                     "%.0f thousand" % (n / 1e3))
                tip += " About %d mesh cells; more cells means a longer run." % n
            except Exception:
                pass
        self.box_label.setText(text)
        self.box_label.setToolTip(tip)

    def update_title(self):
        name = self.project.get("name", "design")
        if self.project_file:
            name = os.path.basename(self.project_file)
        self.setWindowTitle("TASMEEM EM Simulator - %s%s" % (name, " *" if self.dirty else ""))

    def set_dirty(self, d=True):
        self.dirty = d
        self.update_title()

    def load_into_form(self):
        p = self.project
        b = p["board"]
        widgets = [self.b_len, self.b_wid, self.b_th, self.b_eps, self.b_tan, self.f_start, self.f_stop,
                   self.b_gnd, self.mesh, self.material]
        for w in widgets:
            w.blockSignals(True)
        self.b_len.setValue(b["length"])
        self.b_wid.setValue(b["width"])
        self.b_th.setValue(b["thickness"])
        self.b_eps.setValue(b["epsR"])
        self.b_tan.setValue(b["tanD"])
        self.b_gnd.setChecked(b.get("ground", True))
        self.f_start.setValue(p["freq"]["start"])
        self.f_stop.setValue(p["freq"]["stop"])
        self.mesh.setCurrentText(p.get("mesh", "normal"))
        known = {(4.3, 0.025): 1, (3.38, 0.0027): 2}
        self.material.setCurrentIndex(known.get((b["epsR"], b["tanD"]), 0 if b["epsR"] == 0 else 3))
        for w in widgets:
            w.blockSignals(False)
        self.refresh_lists()

    def form_changed(self, *args):
        b = self.project["board"]
        b["length"], b["width"], b["thickness"] = self.b_len.value(), self.b_wid.value(), self.b_th.value()
        b["epsR"], b["tanD"], b["ground"] = self.b_eps.value(), self.b_tan.value(), self.b_gnd.isChecked()
        self.project["freq"] = {"start": self.f_start.value(), "stop": self.f_stop.value()}
        self.project["mesh"] = self.mesh.currentText()
        known = {(4.3, 0.025): 1, (3.38, 0.0027): 2}
        i = known.get((round(b["epsR"], 4), round(b["tanD"], 5)), 0 if b["epsR"] == 0 else 3)
        if self.material.currentIndex() != i and not (i == 3 and self.material.currentIndex() == 3):
            self.material.blockSignals(True)
            self.material.setCurrentIndex(i)
            self.material.blockSignals(False)
        self.update_box()
        self.set_dirty()
        self.redraw()

    def material_changed(self, i):
        if i == 1:
            self.b_eps.setValue(4.3)
            self.b_tan.setValue(0.025)
        elif i == 2:
            self.b_eps.setValue(3.38)
            self.b_tan.setValue(0.0027)
        elif i == 3:
            self.b_eps.setFocus()

    def refresh_lists(self):
        row = self.shape_list.currentRow()
        self.shape_list.blockSignals(True)
        self.shape_list.clear()
        for s in self.project["shapes"]:
            if s["type"] == "rectangle":
                info = "%g x %g mm at (%g, %g)" % (s["length"], s["width"], s["x"], s["y"])
            elif s["type"] == "taper":
                info = "%g to %g mm wide" % (s["width1"], s["width2"])
            else:
                info = "r %g to %g mm, %g to %g deg" % (s["r_inner"], s["r_outer"], s["angle_start"], s["angle_stop"])
            self.shape_list.addItem("%s  (%s, %s)" % (s["name"], s["type"], info))
            self.shape_list.item(self.shape_list.count() - 1).setToolTip(self.shape_list.item(
                self.shape_list.count() - 1).text())
        if not self.project["shapes"]:
            self.shape_list.addItem("No shapes yet. Use + Rectangle, + Taper or + Arc.")
            self.shape_list.item(0).setForeground(QColor("#8a99a8"))
            self.shape_list.item(0).setFlags(Qt.NoItemFlags)
        self.shape_list.blockSignals(False)
        if 0 <= row < len(self.project["shapes"]):
            self.shape_list.setCurrentRow(row)
        pt = self.project["port"]
        if pt:
            text = "At (%g, %g) mm, %g mm wide, %g mm long, pointing %s, %g ohm" % (
                pt["x"], pt["y"], pt["width"], pt["length"], pt["direction"], pt["impedance"])
            self.port_label.setText(text.replace("-", "\u2212"))   # a minus sign never splits "-x" across lines
        else:
            self.port_label.setText("No port yet.")
        self.update_mesh_info()
        self.redraw()

    # ---------------------------------------------------------------- shapes and port

    def selected_shape(self):
        i = self.shape_list.currentRow()
        return i if 0 <= i < len(self.project["shapes"]) else -1

    def preview_shape(self, s):
        self.temp_shape = s
        self.redraw()

    def preview_port(self, pt):
        self.temp_port = pt
        self.redraw()

    def add_shape(self, t):
        self.tabs.setCurrentWidget(self.view_tab)
        d = ShapeDialog(self, t, preview=self.preview_shape)
        ok = d.exec_()
        self.temp_shape = None
        if ok:
            self.project["shapes"].append(d.value())
            self.refresh_lists()
            self.shape_list.setCurrentRow(len(self.project["shapes"]) - 1)
            self.set_dirty()
        else:
            self.redraw()

    def edit_shape(self):
        i = self.selected_shape()
        if i < 0:
            self.statusBar().showMessage("Select a shape in the list first.", 4000)
            return
        self.tabs.setCurrentWidget(self.view_tab)
        old = self.project["shapes"][i]
        self.project["shapes"][i] = dict(old, hidden=True)
        d = ShapeDialog(self, old["type"], old, preview=self.preview_shape)
        ok = d.exec_()
        self.temp_shape = None
        self.project["shapes"][i] = d.value() if ok else old
        if ok:
            self.set_dirty()
        self.refresh_lists()

    def duplicate_shape(self):
        i = self.selected_shape()
        if i < 0:
            self.statusBar().showMessage("Select a shape in the list first.", 4000)
            return
        s = copy.deepcopy(self.project["shapes"][i])
        s["name"] += " copy"
        self.project["shapes"].insert(i + 1, s)
        self.refresh_lists()
        self.shape_list.setCurrentRow(i + 1)
        self.set_dirty()
        self.statusBar().showMessage("Duplicated. Use Edit to move the copy.", 4000)

    def delete_shape(self):
        i = self.selected_shape()
        if i >= 0:
            del self.project["shapes"][i]
            self.refresh_lists()
            self.set_dirty()

    def set_port(self):
        self.tabs.setCurrentWidget(self.view_tab)
        old = self.project["port"]
        self.project["port"] = None
        d = PortDialog(self, old, preview=self.preview_port)
        ok = d.exec_()
        self.temp_port = None
        self.project["port"] = d.value() if ok else old
        if ok:
            self.set_dirty()
        self.refresh_lists()

    # ---------------------------------------------------------------- 3D view

    def set_view(self, elev, azim):
        self.ax3d.view_init(elev, azim)      # redraw() keeps whatever angle the axes have
        self.redraw()

    def redraw(self):
        ax = self.ax3d
        try:
            self.view_angle = (ax.elev, ax.azim)
        except AttributeError:
            pass
        ax.clear()
        ax.set_facecolor("#ffffff")
        b = self.project["board"]
        shapes = [sh for sh in self.project["shapes"] if not sh.get("hidden")]
        if self.temp_shape:
            shapes = shapes + [self.temp_shape]
        pt = self.temp_port or self.project["port"]

        # how big the drawing is: the board, or whatever has been drawn so far
        if self.board_ready():
            L, W = b["length"], b["width"]
        else:
            xs_all, ys_all = [], []
            for sh in shapes:
                xs, ys = eng.shape_outline(sh)
                xs_all += list(xs)
                ys_all += list(ys)
            if pt:
                xs_all += [pt["x"] - pt["length"], pt["x"] + pt["length"]]
                ys_all += [pt["y"] - pt["length"], pt["y"] + pt["length"]]
            if not xs_all:
                ax.set_axis_off()      # nothing created yet: a blank workspace
                self.something_drawn = False
                self.triad.set_visible(False)
                self.canvas3d.draw_idle()
                return
            L = 2 * max(abs(v) for v in xs_all) or 10.0
            W = 2 * max(abs(v) for v in ys_all) or 10.0
        ax.set_axis_on()
        self.something_drawn = True
        H = b["thickness"]
        zs = max(H, 0.04 * max(L, W))      # drawn board height (exaggerated so it is visible)

        def flat(xs, ys, z, color, alpha, edge="k", lw=0.6):
            ax.add_collection3d(Poly3DCollection([list(zip(xs, ys, [z] * len(xs)))], facecolor=color,
                                                 edgecolor=edge, alpha=alpha, linewidths=lw))

        if self.board_ready():
            bx, by = [-L / 2, L / 2, L / 2, -L / 2], [-W / 2, -W / 2, W / 2, W / 2]
            flat(bx, by, zs, "#8fd18f", 0.35)
            for i in range(4):     # board sides
                j = (i + 1) % 4
                ax.add_collection3d(Poly3DCollection([[(bx[i], by[i], 0), (bx[j], by[j], 0), (bx[j], by[j], zs),
                                                       (bx[i], by[i], zs)]], facecolor="#5aa05a", alpha=0.35,
                                                     edgecolor="#336633", linewidths=0.5))
            if b.get("ground", True):
                flat(bx, by, 0, "#c87533", 0.5)

        selected = self.selected_shape()
        for i, sh in enumerate(self.project["shapes"]):
            if sh.get("hidden"):
                continue
            xs, ys = eng.shape_outline(sh)
            flat(xs, ys, zs + 0.01, "#e8b923" if i != selected else "#ffd75e", 0.95,
                 edge="#7a5c00" if i != selected else "#1f5fbf", lw=0.8 if i != selected else 2)
        if self.temp_shape:
            xs, ys = eng.shape_outline(self.temp_shape)
            flat(xs, ys, zs + 0.02, "#ff9a3c", 0.95, edge="#b85c00", lw=2)

        if pt:
            sign = -1 if pt["direction"].startswith("-") else 1
            if pt["direction"][1] == "x":
                xs = [pt["x"], pt["x"] + sign * pt["length"]]
                ys = [pt["y"] - pt["width"] / 2, pt["y"] + pt["width"] / 2]
            else:
                xs = [pt["x"] - pt["width"] / 2, pt["x"] + pt["width"] / 2]
                ys = [pt["y"], pt["y"] + sign * pt["length"]]
            shapes_now = [sh for sh in self.project["shapes"] if not sh.get("hidden")]
            if self.temp_shape:
                shapes_now.append(self.temp_shape)
            connected = eng.port_status({"port": pt, "shapes": shapes_now})[0] if shapes_now else False
            color, edge, label = ("#e53935", "#8b0000", "port") if connected else \
                ("#ff9800", "#e65100", "port (not connected)")
            flat([xs[0], xs[1], xs[1], xs[0]], [ys[0], ys[0], ys[1], ys[1]], zs + 0.03, color, 0.9,
                 edge=edge, lw=1.5)
            ax.text(pt["x"], pt["y"], zs * 2.5, label, color=edge)

        m = max(L, W) / 2 * 1.05
        ax.set_xlim(-m, m)
        ax.set_ylim(-m, m)
        ax.set_zlim(0, max(L, W) * 0.3)
        ax.set_box_aspect((1, 1, 0.3))
        ax.set_zticks([])
        for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
            axis.set_rotate_label(False)       # keep axis titles level, not slanted with the axis
        elev, azim = self.view_angle
        xlabel, ylabel = "x (mm)", "y (mm)"
        if abs(elev) < 5 and abs(abs(azim) - 90) < 5:
            ax.set_yticks([])          # side view: the y axis points at the viewer, so hide its labels
            ylabel = ""
        elif abs(elev) < 5 and (abs(azim) < 5 or abs(abs(azim) - 180) < 5):
            ax.set_xticks([])
            xlabel = ""
        pad = 12 if abs(elev) >= 5 else 24     # flat side views need more room under the numbers
        ax.set_xlabel(xlabel, rotation=0, labelpad=pad)
        ax.set_ylabel(ylabel, rotation=0, labelpad=pad)
        ax.view_init(elev, azim)
        self.update_triad()
        self.canvas3d.draw_idle()

    def on_3d_drag(self, event):
        if event.button is not None and event.inaxes is self.ax3d:
            self.update_triad(True)

    def update_triad(self, draw=False):
        """Small x/y/z arrows that turn with the 3D view, like the axis gizmo in CST."""
        t = self.triad
        t.clear()
        t.set_axis_off()
        t.set_xlim(-1.35, 1.35)
        t.set_ylim(-1.35, 1.35)
        t.set_aspect("equal")
        t.set_visible(self.something_drawn)
        e, a = math.radians(self.ax3d.elev), math.radians(self.ax3d.azim)
        # screen right/up components of the x, y, z unit vectors for this camera angle
        vecs = [("x", -math.sin(a), -math.sin(e) * math.cos(a), "#c62828"),
                ("y", math.cos(a), -math.sin(e) * math.sin(a), "#2e7d32"),
                ("z", 0.0, math.cos(e), "#1565c0")]
        for name, dx, dy, c in vecs:
            if math.hypot(dx, dy) < 0.08:          # pointing at the viewer: show a dot
                t.plot([0], [0], "o", color=c, ms=6)
                t.text(0.12, 0.12, name, color=c, fontsize=10, fontweight="bold")
                continue
            t.annotate("", xy=(dx, dy), xytext=(0, 0),
                       arrowprops=dict(arrowstyle="-|>", color=c, lw=2, mutation_scale=12))
            t.text(dx * 1.22, dy * 1.22, name, color=c, fontsize=10, fontweight="bold", ha="center", va="center")
        if draw:
            self.canvas3d.draw_idle()

    # ---------------------------------------------------------------- run the design

    def check_only(self):
        problems = eng.check_project(self.project)
        if problems:
            QMessageBox.warning(self, "Fix these first", "\n\n".join(problems))
            return
        warnings = eng.check_warnings(self.project)
        if warnings:
            QMessageBox.information(self, "Design check", "No errors. The design can run, but check these:\n\n" +
                                    "\n\n".join(warnings))
        else:
            QMessageBox.information(self, "Design check", "No problems found. The design is ready to run.")

    def check_and_run(self):
        if self.proc is not None:
            QMessageBox.information(self, "Busy", "A simulation is already running. Stop it first.")
            return
        problems = eng.check_project(self.project)
        if problems:
            QMessageBox.warning(self, "Fix these first", "\n\n".join(problems))
            return
        warnings = eng.check_warnings(self.project)
        self.tabs.setCurrentWidget(self.view_tab)
        p = self.project
        d = QDialog(self)
        d.setWindowTitle("Check before running")
        v = QVBoxLayout(d)
        row = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(self.style().standardIcon(QStyle.SP_MessageBoxQuestion).pixmap(40, 40))
        row.addWidget(icon, 0, Qt.AlignTop)
        text = QLabel("<b>Check the 3D view. Does the structure look right?</b><br><br>"
                      "%d shape(s), board %.1f x %.1f x %.2f mm, epsR %.2f<br>%.2f to %.2f GHz, %s mesh"
                      % (len(p["shapes"]), p["board"]["length"], p["board"]["width"], p["board"]["thickness"],
                         p["board"]["epsR"], p["freq"]["start"], p["freq"]["stop"], p["mesh"]))
        row.addWidget(text, 1)
        v.addLayout(row)
        try:
            n = eng.estimate_cells(p)
            info = QLabel(self.box_label.text() + ".")
            info.setObjectName("hint")
            v.addWidget(info)
        except Exception:
            pass
        for wtxt in warnings:
            wl = QLabel("Warning: " + wtxt)
            wl.setWordWrap(True)
            wl.setStyleSheet("color: #8a5a00; background: #fff6dc; padding: 4px; border-radius: 3px;")
            v.addWidget(wl)
        buttons = QHBoxLayout()
        run_b = QPushButton("Yes, run it")
        run_b.setObjectName("startButton")
        mesh_b = QPushButton("Show detailed 3D with mesh")
        back_b = QPushButton("No, go back")
        run_b.clicked.connect(d.accept)
        back_b.clicked.connect(d.reject)
        mesh_b.clicked.connect(self.show_mesh_view)      # the dialog stays open while the viewer is shown
        buttons.addStretch()
        for btn in (run_b, mesh_b, back_b):
            buttons.addWidget(btn)
        v.addLayout(buttons)
        run_b.setDefault(True)
        ok = d.exec_() == QDialog.Accepted
        d.deleteLater()
        QApplication.processEvents()       # let the dialog disappear before the run starts
        if not ok:
            return
        self.run_dir = self.new_run_dir(p.get("name", "run"))
        pf = os.path.join(self.run_dir, "project.json")
        with open(pf, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=2)
        self.results_range = (p["freq"]["start"], p["freq"]["stop"])
        self.start_process([os.path.join(HERE, "em_engine.py"), "run", pf, self.run_dir],
                           "Running openEMS on the design")

    def new_run_dir(self, name):
        name = "".join(c if c.isascii() and c.isalnum() else "_" for c in name)   # openEMS needs plain folder names
        name = re.sub(r"_+", "_", name).strip("_")[:40] or "design"
        d = os.path.join(WORK, "em_runs", name + "_" + time.strftime("%Y%m%d_%H%M%S"))
        os.makedirs(d, exist_ok=True)
        return d

    def view_xml(self, xml):
        if not os.path.exists(APPCSXCAD):
            QMessageBox.warning(self, "AppCSXCAD not found", APPCSXCAD)
            return
        self.status.setText("Close the AppCSXCAD window to come back.")
        viewer = subprocess.Popen([APPCSXCAD, "--disableEdit", xml])
        while viewer.poll() is None:          # keep this window responsive while the viewer is open
            QApplication.processEvents()
            time.sleep(0.05)
        self.status.setText("Ready.")

    def show_mesh_view(self):
        problems = eng.check_project(self.project)
        if problems:
            QMessageBox.warning(self, "Fix these first", "\n".join(problems))
            return
        d = os.path.join(WORK, "em_runs", "_preview")
        os.makedirs(d, exist_ok=True)
        pf = os.path.join(d, "project.json")
        with open(pf, "w", encoding="utf-8") as f:
            json.dump(self.project, f, indent=2)
        self.status.setText("Building the detailed view...")
        QApplication.processEvents()
        r = subprocess.run([sys.executable, os.path.join(HERE, "em_engine.py"), "export", pf, d],
                           capture_output=True, encoding="utf-8", errors="replace",
                           creationflags=NO_WINDOW)
        xml = os.path.join(d, "model.xml")
        if r.returncode != 0 or not os.path.exists(xml):
            QMessageBox.warning(self, "Could not build the model", r.stdout[-1500:] + r.stderr[-1500:])
            self.status.setText("Ready.")
            return
        self.view_xml(xml)

    # ---------------------------------------------------------------- background process (design or script)

    def start_process(self, args, message):
        self.log.clear()
        self.log_buffer = ""
        self.log_line("TASMEEM: " + message + "\nTASMEEM: output folder " + self.run_dir)
        self.tabs.setCurrentWidget(self.log)
        self.proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONPATH", HERE + os.pathsep + env.value("PYTHONPATH", ""))
        env.insert("PYTHONUNBUFFERED", "1")
        self.proc.setProcessEnvironment(env)
        self.proc.setWorkingDirectory(self.run_dir)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self.read_output)
        self.proc.finished.connect(self.run_finished)
        self.stopped = False
        self.proc.start(sys.executable, ["-u"] + args)
        self.set_running(True)
        self.status.setText(message + "... (the Log tab shows progress)")
        self.status.setStyleSheet("color: #1565c0;")
        self.t_start = time.time()

    def set_running(self, running):
        self.run_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.a_run.setEnabled(not running)
        self.a_run_script.setEnabled(not running)
        self.a_stop.setEnabled(running)
        self.a_stop_script.setEnabled(running)

    def log_line(self, text):
        for line in text.split("\n"):
            esc = html.escape(line)
            if line.startswith("TASMEEM:"):
                self.log.appendHtml('<b style="color:#1565c0">%s</b>' % esc)
            elif "Error" in line or "Traceback" in line or "error:" in line.lower():
                self.log.appendHtml('<span style="color:#c62828">%s</span>' % esc)
            elif "Warning" in line:
                self.log.appendHtml('<span style="color:#b8860b">%s</span>' % esc)
            else:
                self.log.appendHtml('<span style="color:#222">%s</span>' % (esc or "&nbsp;"))

    def read_output(self):
        text = self.log_buffer + bytes(self.proc.readAllStandardOutput()).decode(errors="replace")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")
        self.log_buffer = lines.pop()          # keep a partial last line for the next chunk
        if lines:
            self.log_line("\n".join(lines))
        for line in lines:
            if "Timestep" in line:
                self.status.setText("Running openEMS... %s" % line.strip()[:70])

    def stop_run(self):
        if self.proc:
            self.stopped = True
            self.proc.kill()
            self.status.setText("Stopping...")

    def run_finished(self, code, status):
        if self.log_buffer:
            self.log_line(self.log_buffer)
            self.log_buffer = ""
        self.proc = None
        self.set_running(False)
        res_file = os.path.join(self.run_dir, "results.json")
        if self.stopped or code != 0 or not os.path.exists(res_file):
            if self.stopped:
                msg = "Stopped. Nothing was saved from this run."
                self.log_line("TASMEEM: stopped by the user")
            elif code != 0:
                msg = "The run did not finish. See the Log tab (the last red lines say why)."
            else:
                msg = "The script finished but saved no results (no results.json)."
            self.status.setText(msg)
            self.status.setStyleSheet("color: #c62828;")
            self.statusBar().showMessage(msg)
            return
        self.record_convergence(res_file)
        self.load_results(res_file)
        self.tabs.setCurrentWidget(self.results_tab)
        msg = "Done in %.0f s. Saved in %s" % (time.time() - self.t_start, short_path(self.run_dir))
        self.status.setText(msg)
        self.status.setToolTip(self.run_dir)
        self.status.setStyleSheet("color: #2e7d32; font-weight: bold;")
        self.statusBar().showMessage(msg)

    def record_convergence(self, res_file):
        """openEMS prints whether it stopped at the time step limit and how far the energy fell.
        Keep that with the results, so the Results tab can say how settled the run was."""
        text = self.log.toPlainText()
        energies = re.findall(r"Energy:\s*~?\s*[0-9.eE+-]+\s*\(\s*-\s*([0-9.]+)\s*dB\)", text)
        done = re.findall(r"end-criteria of\s*-?[0-9.]+\s*dB reached after\s*([0-9]+)\s*timesteps\s*\(\s*(-?[0-9.]+)\s*dB\)",
                          text)
        try:
            with open(res_file, encoding="utf-8") as f:
                r = json.load(f)
            r["hit_step_limit"] = "Max. number of timesteps was reached" in text
            if done:
                r["energy_dB"] = float(done[-1][1])
                r["timesteps"] = int(done[-1][0])
            elif energies:
                r["energy_dB"] = -float(energies[-1])
            with open(res_file, "w", encoding="utf-8") as f:
                json.dump(r, f)
        except (OSError, ValueError):
            pass

    def load_results(self, res_file):
        with open(res_file, encoding="utf-8") as f:
            self.results = json.load(f)
        self.run_dir = os.path.dirname(os.path.abspath(res_file))
        r = self.results
        if "f_start_GHz" in r:
            self.results_range = (r["f_start_GHz"], r["f_stop_GHz"])
        elif self.results_range is None:
            self.results_range = (self.project["freq"]["start"], self.project["freq"]["stop"])
        self.markers = []
        self.show_results()
        ff_file = os.path.join(self.run_dir, "farfield.json")
        self.ff = None
        if os.path.exists(ff_file):
            with open(ff_file, encoding="utf-8") as f:
                self.ff = json.load(f)
        self.ff_freq.setValue(self.ff["f_GHz"] if self.ff else r["f_res_GHz"])
        self.show_far_field()

    def show_results(self):
        r = self.results
        nan = float("nan")
        self.r_labels["f_res"].setText("%.3f GHz" % r["f_res_GHz"])
        self.r_labels["s11"].setText("%.2f dB" % r["s11_min_dB"])
        self.r_labels["bw"].setText("%.3f to %.3f GHz" % tuple(r["bandwidth_GHz"]) if r["bandwidth_GHz"]
                                    else "not below -10 dB")
        self.r_labels["dir"].setText("%.2f dBi" % r["directivity_dBi"])
        g, e = r.get("gain_dBi", nan), r.get("efficiency", nan)
        self.r_labels["gain"].setText("%.2f dBi" % g if math.isfinite(g) else "-")
        self.r_labels["eff"].setText("%.0f %%" % (100 * e) if math.isfinite(e) else "-")
        self.r_labels["time"].setText("%.0f s" % r.get("runtime_s", 0))
        notes = []
        if r.get("hit_step_limit"):
            notes.append(STEP_LIMIT_NOTE % r.get("energy_dB", float("nan")))
        elif "energy_dB" in r:
            notes.append("openEMS ran until the energy had settled (%.0f dB%s), so the results are converged."
                         % (r["energy_dB"], ", %d time steps" % r["timesteps"] if "timesteps" in r else ""))
        if r.get("res_at_edge"):
            notes.append("The lowest S11 is at the edge of your frequency range, so the real resonance may be "
                         "outside it. Widen the range in step 2 and run again.")
        self.r_note.setText("  ".join(notes) if notes else "")
        self.r_note.setStyleSheet("color: #8a5a00;" if (r.get("hit_step_limit") or r.get("res_at_edge"))
                                  else "color: #2e7d32;")
        self.draw_s11()
        self.draw_smith()
        self.draw_impedance()
        self.fill_table()
        self.run_path_label.setText("Saved in: " + self.run_dir + "   (S11.s1p, results.json, farfield.json)")

    def view_range(self):
        r = self.results
        fs, fe = self.results_range
        pad = 0.25 * (fe - fs)
        lo, hi = fs - pad, fe + pad
        if not lo <= r["f_res_GHz"] <= hi:
            lo, hi = min(lo, r["f_res_GHz"] - pad), max(hi, r["f_res_GHz"] + pad)
        return lo, hi

    def draw_s11(self):
        r = self.results
        self.fig_s11.clear()
        a1 = self.fig_s11.add_subplot(111)
        self.ax_s11 = a1
        a1.plot(r["freq_GHz"], r["s11_dB"], color="#c62828", lw=2, label="S11")
        a1.axhline(-10, color="k", ls="--", lw=1, label="-10 dB")
        fs, fe = self.results_range
        a1.axvspan(fs, fe, color="#1565c0", alpha=0.07, label="your range")
        a1.plot([r["f_res_GHz"]], [r["s11_min_dB"]], "ko")
        a1.annotate("%.3f GHz\n%.2f dB" % (r["f_res_GHz"], r["s11_min_dB"]), (r["f_res_GHz"], r["s11_min_dB"]),
                    textcoords="offset points", xytext=(10, 10))
        lo, hi = self.view_range()
        a1.set_xlim(lo, hi)
        inside = [v for f, v in zip(r["freq_GHz"], r["s11_dB"]) if lo <= f <= hi]
        a1.set_ylim(min(-15, min(inside) - 3), max(2, max(inside) + 1))
        a1.set_xlabel("Frequency (GHz)")
        a1.set_ylabel("|S11| (dB)", rotation=0, ha="left", va="bottom")
        a1.yaxis.set_label_coords(-0.02, 1.01)
        a1.set_title("S11 (input match)", pad=22)
        a1.grid(True, alpha=0.4)
        colors = ["#1565c0", "#2e7d32", "#6a1b9a", "#ef6c00", "#00838f", "#ad1457"]
        lines = []
        for n, i in enumerate(self.markers):
            f, v = r["freq_GHz"][i], r["s11_dB"][i]
            c = colors[n % len(colors)]
            a1.axvline(f, color=c, ls=":", lw=1.2)
            a1.plot([f], [v], "o", color=c)
            a1.annotate("M%d" % (n + 1), (f, v), textcoords="offset points", xytext=(6, -14), color=c)
            lines.append("<span style='color:%s'><b>M%d</b></span> %.4f GHz: %.2f dB" % (c, n + 1, f, v))
        self.marker_label.setText("&nbsp;&nbsp;&nbsp;".join(lines))
        a1.legend(loc="lower left")
        self.fig_s11.tight_layout()
        self.canvas_s11.draw_idle()

    def s11_click(self, event):
        if not self.results or event.inaxes is not getattr(self, "ax_s11", None):
            return
        if self.canvas_s11.toolbar is not None and self.canvas_s11.toolbar.mode:
            return                           # zoom or pan is active
        if event.button == 3:
            self.clear_markers()
            return
        if event.button != 1 or event.xdata is None:
            return
        fr = self.results["freq_GHz"]
        i = min(range(len(fr)), key=lambda k: abs(fr[k] - event.xdata))
        if i not in self.markers:
            self.markers.append(i)
        self.draw_s11()

    def clear_markers(self):
        self.markers = []
        if self.results:
            self.draw_s11()

    def range_indices(self, only_range=True):
        r = self.results
        if not only_range:
            return list(range(len(r["freq_GHz"])))
        fs, fe = self.results_range
        return [i for i, f in enumerate(r["freq_GHz"]) if fs - 1e-9 <= f <= fe + 1e-9]

    def draw_smith(self):
        r = self.results
        self.fig_smith.clear()
        ax = self.fig_smith.add_subplot(111)
        ax.set_aspect("equal")
        ax.axis("off")
        if "s11_re" not in r:
            ax.text(0.5, 0.5, "This run is from an older version.\nRun it again to see the Smith chart.",
                    ha="center", va="center", transform=ax.transAxes)
            self.canvas_smith.draw_idle()
            return
        from matplotlib.patches import Circle
        clip = Circle((0, 0), 1, transform=ax.transData, fill=False)
        ax.add_patch(Circle((0, 0), 1, fill=False, color="#555", lw=1.2))
        for rr in (0.2, 0.5, 1, 2, 5):
            ax.add_patch(Circle((rr / (1 + rr), 0), 1 / (1 + rr), fill=False, color="#bbb", lw=0.7))
            ax.text(rr / (1 + rr) - 1 / (1 + rr) + 0.01, 0.02, "%g" % rr, fontsize=7, color="#888")
        for xx in (0.2, 0.5, 1, 2, 5):
            for sgn in (1, -1):
                c = Circle((1, sgn / xx), 1 / xx, fill=False, color="#bbb", lw=0.7)
                ax.add_patch(c)
                c.set_clip_path(clip)
        ax.plot([-1, 1], [0, 0], color="#bbb", lw=0.7)
        idx = self.range_indices(True)
        gr = [r["s11_re"][i] for i in idx]
        gi = [r["s11_im"][i] for i in idx]
        ax.plot(gr, gi, color="#c62828", lw=2, label="S11, %.2f to %.2f GHz" % self.results_range)
        k = min(range(len(r["freq_GHz"])), key=lambda j: abs(r["freq_GHz"][j] - r["f_res_GHz"]))
        ax.plot([r["s11_re"][k]], [r["s11_im"][k]], "ko")
        zr, zi = r["zin_re"][k], r["zin_im"][k]
        ax.annotate("%.3f GHz\nZ = %.1f %+.1fj ohm" % (r["f_res_GHz"], zr, zi), (r["s11_re"][k], r["s11_im"][k]),
                    textcoords="offset points", xytext=(10, 10))
        ax.plot([gr[0]], [gi[0]], "s", color="#1565c0", ms=5)
        ax.plot([gr[-1]], [gi[-1]], "^", color="#1565c0", ms=6)
        ax.set_xlim(-1.08, 1.08)
        ax.set_ylim(-1.08, 1.08)
        ax.set_title("Smith chart (normalised to %g ohm). Square = start, triangle = stop." % r.get("z0", 50),
                     fontsize=10)
        ax.legend(loc="lower left", fontsize=8)
        self.canvas_smith.draw_idle()

    def draw_impedance(self):
        r = self.results
        self.fig_z.clear()
        ax = self.fig_z.add_subplot(111)
        lo, hi = self.view_range()
        idx = [i for i, f in enumerate(r["freq_GHz"]) if lo <= f <= hi]
        f = [r["freq_GHz"][i] for i in idx]
        ax.plot(f, [r["zin_re"][i] for i in idx], color="#1565c0", lw=2, label="Real part (resistance)")
        ax.plot(f, [r["zin_im"][i] for i in idx], color="#ef6c00", lw=2, ls="--", label="Imaginary part (reactance)")
        ax.axhline(r.get("z0", 50), color="#2e7d32", lw=1, ls=":", label="%g ohm" % r.get("z0", 50))
        ax.axhline(0, color="k", lw=0.6)
        ax.axvline(r["f_res_GHz"], color="#888", lw=1, ls=":")
        ax.set_xlim(lo, hi)
        ax.set_xlabel("Frequency (GHz)")
        ax.set_ylabel("Zin (ohm)", rotation=0, ha="left", va="bottom")
        ax.yaxis.set_label_coords(-0.02, 1.01)
        ax.set_title("Input impedance at the port", pad=22)
        ax.grid(True, alpha=0.4)
        ax.legend(loc="best")
        self.fig_z.tight_layout()
        self.canvas_z.draw_idle()

    def table_rows(self):
        r = self.results
        rows = []
        for i in self.range_indices(self.only_range.isChecked()):
            mag = 10 ** (r["s11_dB"][i] / 20)
            vswr = (1 + mag) / (1 - mag) if mag < 1 else float("inf")
            row = [r["freq_GHz"][i], r["s11_dB"][i]]
            if "s11_re" in r:
                row += [r["s11_re"][i], r["s11_im"][i]]
            row += [r["zin_re"][i], r["zin_im"][i], vswr]
            rows.append(row)
        head = ["Frequency (GHz)", "|S11| (dB)"] + (["S11 real", "S11 imag"] if "s11_re" in r else []) + \
               ["Zin real (ohm)", "Zin imag (ohm)", "VSWR"]
        return head, rows

    def fill_table(self):
        if not self.results:
            return
        head, rows = self.table_rows()
        self.table.clear()
        self.table.setColumnCount(len(head))
        self.table.setRowCount(len(rows))
        self.table.setHorizontalHeaderLabels(head)
        for i, row in enumerate(rows):
            for j, v in enumerate(row):
                txt = ("%.4f" % v) if j == 0 else ("%.3f" % v if math.isfinite(v) else "inf")
                it = QTableWidgetItem(txt)
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(i, j, it)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def copy_table(self):
        if not self.results:
            return
        head, rows = self.table_rows()
        text = "\t".join(head) + "\n" + "\n".join("\t".join("%.6g" % v for v in row) for row in rows)
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("Copied %d rows. Paste into Excel or a document." % len(rows), 4000)

    def export_csv(self):
        if not self.results:
            QMessageBox.information(self, "No results yet", "Run a simulation first.")
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Export S11 data", os.path.join(self.run_dir or WORK, "S11.csv"),
                                            "CSV (*.csv)")
        if fn:
            if not fn.lower().endswith(".csv"):
                fn += ".csv"
            head, rows = self.table_rows()
            with open(fn, "w", newline="", encoding="utf-8") as f:
                wr = csv.writer(f)
                wr.writerow(head)
                wr.writerows(rows)
            self.statusBar().showMessage("Saved " + fn, 5000)

    # ---------------------------------------------------------------- far field

    def show_far_field(self):
        self.fig_ff.clear()
        ff = self.ff
        for k in self.ff_labels:
            self.ff_labels[k].setText("-")
        if not ff:
            self.ff_note.setText("No far-field data for this run yet. Pick a frequency and click Calculate."
                                 if self.results else
                                 "Run a simulation; the far field at the resonance is calculated automatically.")
            self.canvas_ff.draw_idle()
            return
        nan = float("nan")
        self.ff_labels["f"].setText("%.4f GHz" % ff["f_GHz"])
        self.ff_labels["dir"].setText("%.2f dBi" % ff["directivity_dBi"])
        for k, key in (("gain", "gain_dBi"), ("rgain", "realized_gain_dBi")):
            v = ff.get(key, nan)
            self.ff_labels[k].setText("%.2f dBi" % v if v is not None and math.isfinite(v) else "-")
        e = ff.get("efficiency", nan)
        self.ff_labels["eff"].setText("%.0f %%" % (100 * e) if e is not None and math.isfinite(e) else "-")
        if ff["max_theta"] in (0, 180):
            self.ff_labels["max"].setText("straight %s (%sz)" % (("up", "+") if ff["max_theta"] == 0 else ("down", "-")))
        else:
            self.ff_labels["max"].setText("theta %g, phi %g deg" % (ff["max_theta"], ff["max_phi"]))
        self.ff_note.setText("Gain = directivity x radiation efficiency. Realized gain also counts the power "
                             "reflected at the port (S11). theta is measured from +z (straight up from the board), "
                             "phi from +x.")
        import numpy as np
        th = np.radians(np.array(ff["theta"]))
        ph = np.radians(np.array(ff["phi"]))
        P = np.array(ff["pattern_dBi"])            # [theta, phi]
        top = float(np.max(P))
        floor = top - 30.0
        view = self.ff_view.currentText()
        if view == "3D pattern":
            from matplotlib import cm
            from matplotlib.colors import Normalize
            ax = self.fig_ff.add_subplot(111, projection="3d")
            T, F = np.meshgrid(th, ph, indexing="ij")
            R = np.clip(P - floor, 0, None) / 30.0
            X, Y, Z = R * np.sin(T) * np.cos(F), R * np.sin(T) * np.sin(F), R * np.cos(T)
            norm = Normalize(floor, top)
            ax.plot_surface(X, Y, Z, facecolors=cm.jet(norm(P)), rstride=1, cstride=1, linewidth=0,
                            antialiased=False, shade=False)
            for (dx, dy, dz, lab, c) in [(1.15, 0, 0, "x", "#c62828"), (0, 1.15, 0, "y", "#2e7d32"),
                                         (0, 0, 1.15, "z", "#1565c0")]:
                ax.plot([0, dx], [0, dy], [0, dz], color=c, lw=1.5)
                ax.text(dx * 1.05, dy * 1.05, dz * 1.05, lab, color=c, fontsize=11, fontweight="bold")
            ax.set_xlim(-1, 1)
            ax.set_ylim(-1, 1)
            ax.set_zlim(-1, 1)
            ax.set_box_aspect((1, 1, 1))
            ax.set_axis_off()
            sm = cm.ScalarMappable(norm=norm, cmap=cm.jet)
            sm.set_array([])
            cb = self.fig_ff.colorbar(sm, ax=ax, shrink=0.7, pad=0.02)
            cb.set_label("Directivity (dBi)")
            ax.set_title("3D radiation pattern at %.4f GHz (30 dB range)" % ff["f_GHz"])
        else:
            def cut(phi_deg):
                j0 = int(np.argmin(np.abs(np.degrees(ph) - phi_deg)))
                j1 = int(np.argmin(np.abs(np.degrees(ph) - (phi_deg + 180))))
                t = np.concatenate([-np.degrees(th[::-1]), np.degrees(th[1:])])
                v = np.concatenate([P[::-1, j1], P[1:, j0]])
                return t, v
            t0, v0 = cut(0)
            t9, v9 = cut(90)
            if view == "2D cuts":
                ax = self.fig_ff.add_subplot(111)
                ax.plot(t0, v0, color="#1f3b57", lw=2, label="xz-plane (phi = 0)")
                ax.plot(t9, v9, color="#2e7d32", lw=2, ls="--", label="yz-plane (phi = 90)")
                ax.set_xlim(-180, 180)
                ax.set_ylim(floor, top + 3)
                ax.set_xlabel("Theta (deg)")
                ax.set_ylabel("Directivity (dBi)", rotation=0, ha="left", va="bottom")
                ax.yaxis.set_label_coords(-0.02, 1.01)
                ax.grid(True, alpha=0.4)
                ax.legend(loc="lower center")
                ax.set_title("Radiation pattern cuts at %.4f GHz" % ff["f_GHz"], pad=22)
            else:
                ax = self.fig_ff.add_subplot(111, projection="polar")
                ax.set_theta_zero_location("N")
                ax.set_theta_direction(-1)
                ax.plot(np.radians(t0), np.clip(v0, floor, None), color="#1f3b57", lw=2, label="xz-plane (phi = 0)")
                ax.plot(np.radians(t9), np.clip(v9, floor, None), color="#2e7d32", lw=2, ls="--",
                        label="yz-plane (phi = 90)")
                ax.set_ylim(floor, top + 1)
                ax.legend(loc="lower left", bbox_to_anchor=(-0.15, -0.12))
                ax.set_title("Polar pattern at %.4f GHz (dBi, 0 deg = +z)" % ff["f_GHz"], pad=18)
        self.fig_ff.tight_layout()
        self.canvas_ff.draw_idle()

    def calc_far_field(self):
        if not self.results or not self.run_dir:
            QMessageBox.information(self, "No run", "Run a simulation first, or open a run's results.json.")
            return
        if self.proc is not None or self.ff_proc is not None:
            QMessageBox.information(self, "Busy", "Wait for the current calculation to finish.")
            return
        f = self.ff_freq.value()
        fr = self.results["freq_GHz"]
        if not fr[0] - 1e-9 <= f <= fr[-1] + 1e-9:
            QMessageBox.warning(self, "Outside the simulated band",
                                "This run covers %.3f to %.3f GHz. Pick a frequency inside that band."
                                % (fr[0], fr[-1]))
            return
        if not os.path.isdir(os.path.join(self.run_dir, "sim")):
            QMessageBox.warning(self, "Simulation data missing", "The run folder has no 'sim' folder any more.")
            return
        pj, sc = os.path.join(self.run_dir, "project.json"), os.path.join(self.run_dir, "script.py")
        if os.path.exists(pj):
            args = [os.path.join(HERE, "em_engine.py"), "farfield", pj, self.run_dir, "%.4f" % f]
        elif os.path.exists(sc):
            args = [sc, self.run_dir, "--farfield=%.4f" % f]
        else:
            QMessageBox.warning(self, "Cannot recalculate", "This run folder has no project.json or script.py.")
            return
        self.ff_target = os.path.join(self.run_dir, "farfield_%.4fGHz.json" % f)
        self.ff_proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONPATH", HERE + os.pathsep + env.value("PYTHONPATH", ""))
        self.ff_proc.setProcessEnvironment(env)
        self.ff_proc.setWorkingDirectory(self.run_dir)
        self.ff_proc.setProcessChannelMode(QProcess.MergedChannels)
        self.ff_proc.finished.connect(self.far_field_done)
        self.ff_calc.setEnabled(False)
        self.ff_note.setText("Calculating the far field at %.4f GHz (no new simulation, about 10 to 60 s)..." % f)
        self.ff_proc.start(sys.executable, ["-u"] + args)

    def far_field_done(self, code, status):
        out = bytes(self.ff_proc.readAllStandardOutput()).decode(errors="replace")
        self.ff_proc = None
        self.ff_calc.setEnabled(True)
        if out.strip():
            self.log_line(out.rstrip())
        if code != 0 or not os.path.exists(self.ff_target):
            last = [l for l in out.splitlines() if l.strip()]
            QMessageBox.warning(self, "Far field failed", (last[-1] if last else "No output.") +
                                "\n\nSee the Log tab for details.")
            self.show_far_field()
            return
        with open(self.ff_target, encoding="utf-8") as f:
            self.ff = json.load(f)
        self.show_far_field()

    def export_far_field(self):
        if not self.ff:
            QMessageBox.information(self, "No far field yet", "Run a simulation first.")
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Export far field", os.path.join(
            self.run_dir or WORK, "farfield_%.4fGHz.csv" % self.ff["f_GHz"]), "CSV (*.csv)")
        if fn:
            if not fn.lower().endswith(".csv"):
                fn += ".csv"
            with open(fn, "w", newline="", encoding="utf-8") as f:
                wr = csv.writer(f)
                wr.writerow(["theta (deg)", "phi (deg)", "directivity (dBi)"])
                for i, t in enumerate(self.ff["theta"]):
                    for j, p in enumerate(self.ff["phi"]):
                        wr.writerow([t, p, "%.3f" % self.ff["pattern_dBi"][i][j]])
            self.statusBar().showMessage("Saved " + fn, 5000)

    # ---------------------------------------------------------------- script editor

    def current_editor(self):
        w = self.editors.currentWidget()
        return w if isinstance(w, CodeEditor) else None

    def add_editor(self, path=None, text=""):
        ed = CodeEditor(path, text)
        ed.document().modificationChanged.connect(lambda _: self.update_editor_title(ed))
        i = self.editors.addTab(ed, ed.title())
        self.editors.setTabToolTip(i, path or "not saved yet")
        self.editors.setCurrentIndex(i)
        self.tabs.setCurrentWidget(self.editor_tab)
        return ed

    def update_editor_title(self, ed):
        i = self.editors.indexOf(ed)
        if i >= 0:
            self.editors.setTabText(i, ed.title())
            self.editors.setTabToolTip(i, ed.path or "not saved yet")

    def new_script(self):
        self.add_editor(None, "# My openEMS script\n# Tip: Tools > Generate openEMS script from design gives a "
                              "full working example.\n\nimport em_engine as tasmeem\nfrom CSXCAD import "
                              "ContinuousStructure\nfrom openEMS import openEMS\n\n")

    def generate_script(self):
        f = self.project["freq"]
        if not self.board_ready() or not (0 < f["start"] < f["stop"]):
            QMessageBox.information(self, "Generate script",
                                    "Set the board (step 1) and the frequency range (step 2) first.")
            return
        if not self.project["shapes"] or not self.project["port"]:
            ans = QMessageBox.question(self, "Generate script",
                                       "The design has no shapes or no port yet. Generate the script anyway?")
            if ans != QMessageBox.Yes:
                return
        ed = self.add_editor(None, eng.make_script(self.project))
        ed.document().setModified(True)
        self.update_editor_title(ed)
        self.statusBar().showMessage("Default script for the design. Edit it, then Run script (F5).", 6000)

    def open_script_dialog(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Open script", os.path.join(WORK, "scripts"),
                                            "Scripts (*.py *.m *.txt);;All files (*)")
        if fn:
            self.open_text_file(fn)

    def open_text_file(self, fn):
        for i in range(self.editors.count()):
            ed = self.editors.widget(i)
            if ed.path and os.path.abspath(ed.path) == os.path.abspath(fn):
                self.editors.setCurrentIndex(i)
                self.tabs.setCurrentWidget(self.editor_tab)
                return ed
        try:
            with open(fn, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            QMessageBox.warning(self, "Could not open", str(e))
            return None
        self.add_recent(fn)
        return self.add_editor(fn, text)

    def save_script(self, save_as=False):
        ed = self.current_editor()
        if ed is None:
            return False
        path = ed.path
        if save_as or path is None:
            start = path or os.path.join(WORK, "scripts", "my_antenna.py")
            path, _ = QFileDialog.getSaveFileName(self, "Save script", start, "Python script (*.py);;All files (*)")
            if not path:
                return False
            if "." not in os.path.basename(path):
                path += ".py"
        with open(path, "w", encoding="utf-8") as f:
            f.write(ed.toPlainText())
        ed.path = path
        if path.endswith(".py") and not hasattr(ed, "highlighter"):
            ed.highlighter = PythonHighlighter(ed.document())
        ed.document().setModified(False)
        self.update_editor_title(ed)
        self.add_recent(path)
        self.statusBar().showMessage("Saved " + path, 4000)
        return True

    def close_editor(self, i):
        ed = self.editors.widget(i)
        if ed.document().isModified():
            ans = QMessageBox.question(self, "Unsaved script", "Save changes to %s?" % ed.title().rstrip(" *"),
                                       QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if ans == QMessageBox.Cancel:
                return
            if ans == QMessageBox.Save:
                self.editors.setCurrentIndex(i)
                if not self.save_script():
                    return
        self.editors.removeTab(i)

    def find_text(self):
        ed = self.current_editor()
        if ed is None or self.tabs.currentWidget() is not self.editor_tab:
            self.statusBar().showMessage("Find works in the Script Editor.", 3000)
            return
        word, ok = QInputDialog.getText(self, "Find", "Find text:", text=getattr(self, "last_find", ""))
        if ok and word:
            self.last_find = word
            if not ed.find(word):
                ed.moveCursor(QTextCursor.Start)      # wrap around
                if not ed.find(word):
                    self.statusBar().showMessage("'%s' not found." % word, 3000)

    def run_script(self):
        if self.proc is not None:
            QMessageBox.information(self, "Busy", "A simulation is already running. Stop it first.")
            return
        ed = self.current_editor()
        if ed is None:
            QMessageBox.information(self, "No script", "Open a script or click Generate from design first.")
            self.tabs.setCurrentWidget(self.editor_tab)
            return
        if ed.path and not ed.path.endswith(".py"):
            QMessageBox.information(self, "Not a Python script", "Only Python (.py) scripts can be run here.")
            return
        if ed.path and ed.document().isModified():
            self.save_script()                   # like Octave: save before running
        name = os.path.splitext(os.path.basename(ed.path))[0] if ed.path else "script"
        self.run_dir = self.new_run_dir(name)
        script = os.path.join(self.run_dir, "script.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(ed.toPlainText())
        self.results_range = None
        self.start_process([script, self.run_dir], "Running script " + (os.path.basename(ed.path) if ed.path else
                                                                        "(not saved)"))

    def show_script_model(self):
        ed = self.current_editor()
        if ed is None:
            QMessageBox.information(self, "No script", "Open a script or click Generate from design first.")
            return
        d = os.path.join(WORK, "em_runs", "_preview")
        os.makedirs(d, exist_ok=True)
        script = os.path.join(d, "script.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(ed.toPlainText())
        env = dict(os.environ)
        env["PYTHONPATH"] = HERE + os.pathsep + env.get("PYTHONPATH", "")
        self.status.setText("Building the script model...")
        QApplication.processEvents()
        r = subprocess.run([sys.executable, script, d, "--setup-only"], capture_output=True, encoding="utf-8", errors="replace", env=env,
                           cwd=d, creationflags=NO_WINDOW)
        xml = os.path.join(d, "model.xml")
        if r.returncode != 0 or not os.path.exists(xml):
            QMessageBox.warning(self, "Could not build the script model",
                                "The script needs to support --setup-only (generated scripts do).\n\n" +
                                (r.stdout[-1200:] + r.stderr[-1200:]))
            self.status.setText("Ready.")
            return
        self.view_xml(xml)

    # ---------------------------------------------------------------- files

    def add_recent(self, path):
        recent = [p for p in (self.settings.value("recent", []) or []) if p != path]
        recent.insert(0, path)
        self.settings.setValue("recent", recent[:8])

    def recent_files(self):
        return [p for p in (self.settings.value("recent", []) or []) if os.path.exists(p)]

    def fill_recent_menu(self):
        self.recent_menu.clear()
        files = self.recent_files()
        if not files:
            a = self.recent_menu.addAction("(nothing yet)")
            a.setEnabled(False)
        for p in files:
            self.recent_menu.addAction(p, lambda p=p: self.open_any(p))

    def confirm_discard(self):
        if not self.dirty:
            return True
        ans = QMessageBox.question(self, "Unsaved design", "Save changes to the current design?",
                                   QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if ans == QMessageBox.Save:
            return self.save_project()
        return ans == QMessageBox.Discard

    def set_project(self, p, path=None):
        self.project = p
        self.project_file = path
        self.load_into_form()
        self.set_dirty(False)
        self.tabs.setCurrentWidget(self.view_tab)

    def new_empty(self):
        if self.confirm_discard():
            self.set_project(self.empty_project())

    def open_project(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Open project", os.path.join(WORK, "projects"),
                                            "TASMEEM EM project (*.json)")
        if fn:
            self.open_project_file(fn)

    def open_project_file(self, fn):
        try:
            with open(fn, encoding="utf-8-sig") as f:
                p = json.load(f)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Could not open", str(e))
            return
        p, problem = eng.clean_project(p)
        if problem:
            QMessageBox.warning(self, "Not a design", "This .json file is not a TASMEEM EM design, or a value in "
                                "it is wrong:\n\n" + problem)
            return
        if self.confirm_discard():
            self.set_project(p, fn)
            self.update_box()          # the simulation box is always set automatically
            self.add_recent(fn)

    def save_current(self):
        if self.tabs.currentWidget() is self.editor_tab and self.current_editor() is not None:
            self.save_script()
        else:
            self.save_project()

    def save_project(self, save_as=False):
        fn = self.project_file
        if save_as or not fn:
            start = fn or os.path.join(WORK, "projects", "".join(
                c if c.isalnum() or c in "-_ " else "_" for c in self.project.get("name", "antenna")) + ".json")
            fn, _ = QFileDialog.getSaveFileName(self, "Save project", start, "TASMEEM EM project (*.json)")
            if not fn:
                return False
            if not fn.endswith(".json"):
                fn += ".json"
            self.project["name"] = os.path.splitext(os.path.basename(fn))[0]
        p = copy.deepcopy(self.project)
        p["shapes"] = [{k: v for k, v in s.items() if k != "hidden"} for s in p["shapes"]]
        with open(fn, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=2)
        self.project_file = fn
        self.add_recent(fn)
        self.set_dirty(False)
        self.redraw()
        self.statusBar().showMessage("Saved " + fn, 4000)
        return True

    def open_any(self, path):
        """Open whatever was double-clicked in the file browser or picked from Recent files."""
        if os.path.isdir(path):
            self.browse_to(path)
            return
        ext = os.path.splitext(path)[1].lower()
        if os.path.basename(path) == "results.json":
            self.results_range = None
            self.load_results(path)
            self.tabs.setCurrentWidget(self.results_tab)
        elif ext == ".json":
            self.open_project_file(path)
        elif ext in (".py", ".m", ".txt", ".s1p", ".csv", ".log", ".md", ".ini", ".cfg"):
            self.open_text_file(path)
        elif ext == ".xml":
            self.view_xml(path)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def save_touchstone(self):
        src = os.path.join(self.run_dir or "", "S11.s1p")
        if not self.results or not os.path.exists(src):
            QMessageBox.information(self, "No results yet", "Run a simulation first.")
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Save S11", os.path.join(WORK, "S11.s1p"), "Touchstone (*.s1p)")
        if fn:
            with open(src, encoding="utf-8") as a, open(fn, "w", encoding="utf-8") as b:
                b.write(a.read())
            self.statusBar().showMessage("Saved " + fn + " (opens in Qucs-S / QucsStudio)", 5000)

    def browse_to(self, d):
        if not os.path.isdir(d):
            return
        self.browse_dir = d
        self.fs_model.setRootPath(d)
        self.tree.setRootIndex(self.fs_model.index(d))
        self.browse_label.setText(d)

    def browse_up(self):
        self.browse_to(os.path.dirname(self.browse_dir.rstrip("/\\")) or self.browse_dir)

    def browse_choose(self):
        d = QFileDialog.getExistingDirectory(self, "Choose folder", self.browse_dir)
        if d:
            self.browse_to(d)

    def open_folder(self, d):
        QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    def open_run_folder(self):
        if self.run_dir and os.path.isdir(self.run_dir):
            self.open_folder(self.run_dir)
        else:
            self.open_folder(os.path.join(WORK, "em_runs"))

    def open_appcsxcad(self):
        if os.path.exists(APPCSXCAD):
            subprocess.Popen([APPCSXCAD])
        else:
            QMessageBox.warning(self, "AppCSXCAD not found", APPCSXCAD)

    # ---------------------------------------------------------------- start screen, help, closing

    def show_start_screen(self):
        d = StartScreen(self, self.recent_files())
        d.show_again.setChecked(self.settings.value("show_start", "true") == "true")
        d.exec_()
        self.settings.setValue("show_start", "true" if d.show_again.isChecked() else "false")
        c = d.choice
        if c == "empty":
            self.new_empty()
        elif c == "open":
            self.open_project()
        elif c == "script":
            self.open_script_dialog()
        elif c and c.startswith("recent:"):
            self.open_any(c[7:])

    def show_help(self):
        QMessageBox.about(self, "Quick start", """<h3>Quick start</h3>
<ol>
<li><b>Board</b>: size, thickness and material of the substrate. Pick FR-4 or Rogers to fill in the
permittivity and loss tangent, or Custom to type your own.</li>
<li><b>Frequency and mesh</b>: the range you care about. Coarse is a quick check, fine is slower and more exact.
The simulation box around the board is set automatically.</li>
<li><b>Shapes</b>: add rectangles (traces or planes), tapers and arcs. Each opens a pop-up and the
3D view updates while you type. Edit, Duplicate and Delete work on the selected shape.</li>
<li><b>Port</b>: where the signal goes in, at the start of the feed line. It must touch copper; an
unconnected port turns orange in the 3D view.</li>
<li><b>Check and run</b>: confirm the 3D view, the mesh size and any warnings, optionally see the mesh in
AppCSXCAD, then run. openEMS runs until the energy in the model has died away (-40 dB), so the results are
converged; a normal-mesh patch takes about 10 to 15 minutes.</li>
</ol>
<p><b>Results</b>: the S11 Results tab has the S11 curve (click to place markers), a Smith chart, the input
impedance and a data table you can export. The Far Field tab shows the 3D radiation pattern, 2D and polar cuts,
directivity, gain and efficiency, and can recalculate the far field at any frequency without a new run.</p>
<p><b>Toolbar</b>: hover a button to see what it does and its shortcut (Help &gt; Keyboard shortcuts lists them all).</p>
<p><b>Scripts</b>: Tools &gt; Generate script from design (Ctrl+G) opens the full openEMS Python
script for your design in the Script Editor. Change anything and press F5 to run it.</p>
<p><b>Files</b>: everything is saved under <code>%s</code> (projects, scripts, em_runs).
The File Browser tab on the left opens them with a double-click.</p>""" % html.escape(WORK))

    def show_shapes_help(self):
        QMessageBox.about(self, "Shapes and ports", """<h3>Shapes (all lengths in mm)</h3>
<p><b>Rectangle</b>: center (x, y), length along x, width along y. Use it for feed lines, patches and planes.</p>
<p><b>Taper</b>: a trapezoid along x or y, from <i>start</i> to <i>end</i> on a center line, changing
from <i>width at start</i> to <i>width at end</i>. Use it for tapered feeds and transitions.</p>
<p><b>Arc</b>: a curved strip around a center (x, y) between an inner and outer radius, from the start
angle to the stop angle (0 deg points along +x). Inner radius 0 gives a pie slice; 0 to 360 deg gives a ring.</p>
<h3>Port</h3>
<p>A microstrip port starts at (x, y) on the board edge and points into the board along the feed.
Its width should match the feed line. The impedance is usually 50 ohm.</p>
<p>The 3D view shows the board height exaggerated so it is easy to see.</p>""")

    def show_shortcuts(self):
        rows = [("Ctrl+N", "New empty design"), ("Ctrl+O", "Open project"), ("Ctrl+S", "Save (design or script)"),
                ("Ctrl+Shift+S", "Save project as"), ("Ctrl+Shift+R", "Add rectangle"), ("Ctrl+Shift+T", "Add taper"),
                ("Ctrl+Shift+A", "Add arc"), ("Ctrl+Shift+P", "Set port"), ("Ctrl+E", "Edit selected shape"),
                ("Ctrl+D", "Duplicate selected shape"), ("Delete", "Delete selected shape (in the shape list)"),
                ("F7", "Check design"), ("Ctrl+R", "Check 3D and run the design"), ("Shift+F5", "Stop simulation"),
                ("Ctrl+G", "Generate script from design"), ("F5", "Run script"), ("Ctrl+F", "Find in script"),
                ("Ctrl+Shift+O", "Open script"), ("Ctrl+1 to Ctrl+5", "3D View, S11 Results, Far Field, Script Editor, Log"),
                ("Ctrl+L", "Show log"), ("F1", "Quick start guide"), ("Ctrl+/", "This list"), ("Ctrl+Q", "Quit")]
        html_rows = "".join("<tr><td style='padding:2px 14px 2px 0'><b>%s</b></td><td>%s</td></tr>" % r for r in rows)
        QMessageBox.about(self, "Keyboard shortcuts", "<h3>Keyboard shortcuts</h3><table>%s</table>" % html_rows)

    def show_about(self):
        QMessageBox.about(self, "About", """<h3>TASMEEM EM Simulator %s</h3>
<p>A point-and-click front end for the openEMS FDTD solver (v0.37), part of TASMEEM: an integrated
infrastructure for electronics design and simulation using open-source tools.</p>
<p>Team sdmay27-30, Iowa State University.</p>
<p>openEMS and CSXCAD by Thorsten Liebig (GPL). Python, Qt (PyQt5), NumPy, Matplotlib and h5py.</p>""" % VERSION)

    def closeEvent(self, event):
        if self.proc is not None:
            if QMessageBox.question(self, "Simulation running", "A simulation is running. Stop it and quit?") \
                    != QMessageBox.Yes:
                event.ignore()
                return
            self.proc.kill()
            self.proc.waitForFinished(3000)
        for i in range(self.editors.count() - 1, -1, -1):
            if self.editors.widget(i).document().isModified():
                self.editors.setCurrentIndex(i)
                self.tabs.setCurrentWidget(self.editor_tab)
                n = self.editors.count()
                self.close_editor(i)
                if self.editors.count() == n:      # cancelled
                    event.ignore()
                    return
        if not self.confirm_discard():
            event.ignore()
            return
        event.accept()


def main():
    QApplication.setAttribute(Qt.AA_DisableWindowContextHelpButton)
    app = QApplication(sys.argv)
    app.setApplicationName("TASMEEM EM Simulator")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_icon())
    w = MainWindow()
    w.fill_editor_toolbar()
    w.show()
    if w.settings.value("show_start", "true") == "true":
        w.show_start_screen()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
