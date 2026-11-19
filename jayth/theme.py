"""Identidad visual: neutros grafito frios + acento indigo-lavanda, en claro y oscuro.
Los iconos son glifos blancos (assets/icons) que se tiñen al color que se pida."""
import os
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QLinearGradient, QPainterPath, QPalette, QGuiApplication
from . import paths

ICON_DIR = os.path.join(paths.APP_DIR, "assets", "icons")
_cache = {}

PALETTES = {
    "dark": {"bg": "#15171c", "side": "#101216", "panel": "#1d2027", "panel2": "#262a33", "hover": "#22262e", "line": "#2b303b",
             "tx": "#e8eaf0", "mut": "#9aa1b2", "faint": "#6c7385", "acc": "#8e9bff", "acc_bg": "#262b4d", "on_acc": "#0d1030",
             "ok": "#4cc38a", "bad": "#f07070", "bad_bg": "#2c1719", "warn": "#f0b450", "warn_bg": "#2b2416", "code": "#0f1115",
             "send": "#e8eaf0", "on_send": "#15171c"},
    "light": {"bg": "#ffffff", "side": "#f5f6f9", "panel": "#f2f3f7", "panel2": "#e9ebf1", "hover": "#eceef3", "line": "#e2e5eb",
              "tx": "#1a1d25", "mut": "#5c6374", "faint": "#8b92a2", "acc": "#5560e6", "acc_bg": "#e9ebfd", "on_acc": "#ffffff",
              "ok": "#1e9a62", "bad": "#d44848", "bad_bg": "#fdeeee", "warn": "#b5730d", "warn_bg": "#fdf4e3", "code": "#f6f7fa",
              "send": "#1a1d25", "on_send": "#ffffff"},
}
C = dict(PALETTES["dark"])
MODE = "dark"
SCALE = [1.0]

QSS_T = """
* { font-family: 'Segoe UI'; font-size: 10pt; color: %(tx)s; }
QMainWindow, QDialog, #central, #chatHolder, #main { background: %(bg)s; }
QWidget#sidebar { background: %(side)s; }
QLabel#h1 { font-size: 13pt; font-weight: 600; }
QLabel#greeting { font-size: 20pt; font-weight: 600; }
QLabel#muted { color: %(mut)s; }
QLabel#faint, QLabel#stats { color: %(faint)s; font-size: 9pt; }
QLabel#section { color: %(faint)s; font-size: 8.5pt; padding: 10px 8px 2px 8px; }
QPushButton { background: %(panel)s; border: 1px solid %(line)s; border-radius: 8px; padding: 6px 12px; }
QPushButton:hover { background: %(hover)s; border-color: %(faint)s; }
QPushButton:disabled { color: %(faint)s; }
QPushButton[kind="primary"] { background: %(acc)s; color: %(on_acc)s; border-color: %(acc)s; font-weight: 600; }
QPushButton[kind="ok"] { background: %(acc)s; color: %(on_acc)s; border-color: %(acc)s; font-weight: 600; }
QPushButton[kind="danger"] { background: transparent; color: %(bad)s; border-color: %(bad)s; }
QPushButton[kind="flat"] { background: transparent; border: none; color: %(mut)s; padding: 4px 8px; }
QPushButton[kind="flat"]:hover { color: %(tx)s; background: %(hover)s; }
QPushButton#nav { background: transparent; border: none; text-align: left; padding: 7px 8px; color: %(tx)s; border-radius: 8px; }
QPushButton#nav:hover { background: %(hover)s; }
QFrame#segment { background: %(panel)s; border: 1px solid %(line)s; border-radius: 10px; }
QPushButton#segBtn { background: transparent; border: none; border-radius: 7px; padding: 5px 8px; color: %(mut)s; }
QPushButton#segBtn:hover { color: %(tx)s; }
QPushButton#segBtn:checked { background: %(panel2)s; color: %(tx)s; font-weight: 600; }
QTabWidget::pane { border: none; }
QTabBar::tab:!selected:hover { color: %(tx)s; }
QTreeView { outline: 0; }
QPushButton#suggestion { background: transparent; border: 1px solid %(line)s; border-radius: 12px; padding: 10px 14px; text-align: left; color: %(mut)s; }
QPushButton#suggestion:hover { background: %(panel)s; color: %(tx)s; }
QToolButton { background: transparent; border: none; border-radius: 8px; padding: 4px; color: %(mut)s; }
QToolButton:hover { background: %(hover)s; color: %(tx)s; }
QToolButton::menu-indicator { image: none; width: 0; }
QToolButton#modelBtn { font-size: 11pt; font-weight: 600; color: %(tx)s; padding: 5px 10px; }
QToolButton#chip { border: 1px solid %(line)s; border-radius: 13px; padding: 3px 10px; color: %(mut)s; font-size: 9pt; }
QToolButton#chip:checked { background: %(acc_bg)s; color: %(acc)s; border-color: %(acc)s; }
QToolButton#chip:hover { color: %(tx)s; }
QToolButton#round { border: 1px solid %(line)s; border-radius: 14px; }
QToolButton#sendBtn { background: %(send)s; border-radius: 16px; }
QToolButton#sendBtn:disabled { background: %(panel2)s; }
QToolButton#sendBtn[stop="true"] { background: %(send)s; }
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
  background: %(panel)s; border: 1px solid %(line)s; border-radius: 8px; padding: 5px 8px; selection-background-color: %(acc)s; selection-color: %(on_acc)s; }
QLineEdit:focus, QComboBox:focus { border-color: %(acc)s; }
QLineEdit#search { background: %(bg)s; }
QComboBox QAbstractItemView { background: %(panel)s; border: 1px solid %(line)s; selection-background-color: %(acc_bg)s; selection-color: %(tx)s; }
QFrame#composerBox { background: %(panel)s; border: 1px solid %(line)s; border-radius: 18px; }
QFrame#composerBox[focus="true"] { border-color: %(faint)s; }
QPlainTextEdit#composerEdit { background: transparent; border: none; padding: 2px 4px; font-size: 10.5pt; }
QListWidget#history { background: transparent; border: none; outline: 0; }
QListWidget#history::item { padding: 7px 8px; border-radius: 8px; color: %(tx)s; }
QListWidget#history::item:selected { background: %(panel2)s; color: %(tx)s; }
QListWidget#history::item:hover:!selected { background: %(hover)s; }
QTableWidget { background: %(panel)s; border: 1px solid %(line)s; border-radius: 8px; gridline-color: %(line)s; }
QHeaderView::section { background: %(panel2)s; border: none; padding: 5px; color: %(mut)s; }
QTableWidget::item:selected { background: %(acc_bg)s; color: %(tx)s; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: %(line)s; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: %(faint)s; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar:horizontal { height: 0; }
QProgressBar { background: %(panel)s; border: 1px solid %(line)s; border-radius: 6px; text-align: center; height: 16px; }
QProgressBar::chunk { background: %(acc)s; border-radius: 5px; }
QToolTip { background: %(panel2)s; border: 1px solid %(line)s; color: %(tx)s; padding: 4px; }
QMenu { background: %(panel)s; border: 1px solid %(line)s; border-radius: 10px; padding: 5px; }
QMenu::item { padding: 6px 22px 6px 10px; border-radius: 6px; }
QMenu::item:selected { background: %(hover)s; }
QMenu::item:disabled { color: %(faint)s; }
QMenu::separator { height: 1px; background: %(line)s; margin: 4px 6px; }
QMenu::indicator { width: 14px; height: 14px; }
QTabWidget::pane { border: 1px solid %(line)s; border-radius: 8px; top: -1px; }
QTabBar::tab { background: transparent; padding: 7px 14px; color: %(mut)s; }
QTabBar::tab:selected { color: %(tx)s; border-bottom: 2px solid %(acc)s; }
QFrame#userBubble { background: %(panel2)s; border-radius: 16px; }
QFrame#stepsBox { background: transparent; border: 1px solid %(line)s; border-radius: 10px; }
QFrame#stepsBox[pending="true"] { border: 1px solid %(acc)s; }
QFrame#approval { background: %(panel)s; border-radius: 8px; }
QPlainTextEdit#mono { background: %(code)s; border: 1px solid %(line)s; border-radius: 8px; font-family: Consolas; font-size: 9.5pt; }
QPlainTextEdit#mono[kind="add"] { border-left: 3px solid %(ok)s; } QPlainTextEdit#mono[kind="del"] { border-left: 3px solid %(bad)s; }
QFrame#noteBox { background: %(panel)s; border-radius: 10px; }
QFrame#errBox { background: %(bad_bg)s; border: 1px solid %(bad)s; border-radius: 10px; }
QFrame#banner { background: %(warn_bg)s; border: 1px solid %(warn)s; border-radius: 10px; }
QFrame#banner QLabel { color: %(warn)s; }
QLabel#badgeWarn { color: %(warn)s; font-size: 9pt; }
QLabel#status[kind="ok"] { color: %(ok)s; } QLabel#status[kind="bad"] { color: %(bad)s; } QLabel#status[kind="run"] { color: %(warn)s; }
QLabel#avatar { background: %(acc_bg)s; color: %(acc)s; border-radius: 13px; font-weight: 600; font-size: 9pt; }
QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; }
"""
QSS = QSS_T % C


def resolve(name):
    if name in PALETTES:
        return name
    try:
        if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Light:
            return "light"
    except Exception:
        pass
    return "dark"


def apply(app, name="system", scale=100):
    """Aplica el tema (system | dark | light) y el tamaño de texto (% ): paleta de Qt, hoja de estilos y colores de iconos."""
    global QSS, MODE
    import re
    MODE = resolve(name)
    C.clear()
    C.update(PALETTES[MODE])
    f = max(0.7, min(1.6, (scale or 100) / 100.0))
    QSS = re.sub(r"(\d+(?:\.\d+)?)pt", lambda m: "%.1fpt" % (float(m.group(1)) * f), QSS_T % C)
    SCALE[0] = f
    _cache.clear()
    app.setStyle("Fusion")
    pal = QPalette()
    for role, col in ((QPalette.Window, C["bg"]), (QPalette.WindowText, C["tx"]), (QPalette.Base, C["panel"]), (QPalette.AlternateBase, C["panel2"]),
                      (QPalette.Text, C["tx"]), (QPalette.Button, C["panel"]), (QPalette.ButtonText, C["tx"]), (QPalette.Highlight, C["acc"]),
                      (QPalette.HighlightedText, C["on_acc"]), (QPalette.ToolTipBase, C["panel2"]), (QPalette.ToolTipText, C["tx"]),
                      (QPalette.PlaceholderText, C["faint"]), (QPalette.Link, C["acc"])):
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
    return MODE


def restyle(w):
    w.style().unpolish(w)
    w.style().polish(w)


def pix(name, color=None, size=18):
    """Glifo de assets/icons/<name>.png teñido del color indicado (los originales son blancos)."""
    key = (name, color or C["tx"], size)
    if key in _cache:
        return _cache[key]
    src = QPixmap(os.path.join(ICON_DIR, name + ".png"))
    if src.isNull():
        return QPixmap()
    dpr = 2.0
    src = src.scaled(int(size * dpr), int(size * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
    out = QPixmap(src.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.drawPixmap(0, 0, src)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(out.rect(), QColor(key[1]))
    p.end()
    out.setDevicePixelRatio(dpr)
    _cache[key] = out
    return out


def icon(name, color=None, size=18):
    return QIcon(pix(name, color, size))


def make_icon():
    """Icono de la app: degradado indigo-lavanda con el glifo de terminal."""
    glyph = QPixmap(os.path.join(ICON_DIR, "cod_terminal.png"))
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(s, s)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        g = QLinearGradient(0, 0, s, s)
        g.setColorAt(0, QColor("#8e9bff"))
        g.setColorAt(1, QColor("#b18cff"))
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, s, s), s * 0.22, s * 0.22)
        p.fillPath(path, g)
        if not glyph.isNull():
            gs = int(s * 0.64)
            gl = glyph.scaled(gs, gs, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            tint = QPixmap(gl.size())
            tint.fill(Qt.transparent)
            tp = QPainter(tint)
            tp.drawPixmap(0, 0, gl)
            tp.setCompositionMode(QPainter.CompositionMode_SourceIn)
            tp.fillRect(tint.rect(), QColor("#0d1030"))
            tp.end()
            p.drawPixmap((s - tint.width()) // 2, (s - tint.height()) // 2, tint)
        p.end()
        ic.addPixmap(pm)
    return ic
