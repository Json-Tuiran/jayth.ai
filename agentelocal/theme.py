"""Tema oscuro, iconos (glifos blancos de assets/icons teñidos al color que se pida) e icono de la aplicacion."""
import os
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QLinearGradient, QPainterPath
from . import paths

ICON_DIR = os.path.join(paths.APP_DIR, "assets", "icons")
_cache = {}

C = {"bg": "#0f1115", "panel": "#161920", "panel2": "#1c2029", "line": "#272c38", "tx": "#e6e8ee", "mut": "#8b93a7",
     "acc": "#7c9cff", "ok": "#3ecf8e", "bad": "#ff6b6b", "warn": "#f5b84b", "code": "#0b0d11"}

QSS = """
* { font-family: 'Segoe UI'; font-size: 10pt; color: %(tx)s; }
QMainWindow, QDialog, #central, #chatHolder { background: %(bg)s; }
#sidebar { background: %(panel)s; border-right: 1px solid %(line)s; }
#header { background: %(panel)s; border-bottom: 1px solid %(line)s; }
#composer { background: %(panel)s; border-top: 1px solid %(line)s; }
QLabel#h1 { font-size: 13pt; font-weight: 600; }
QLabel#muted, QLabel.muted { color: %(mut)s; }
QLabel#section { color: %(mut)s; font-size: 8pt; letter-spacing: 1px; }
QPushButton { background: %(panel2)s; border: 1px solid %(line)s; border-radius: 8px; padding: 6px 12px; }
QPushButton:hover { border-color: %(acc)s; }
QPushButton:disabled { color: %(mut)s; border-color: %(line)s; }
QPushButton[kind="primary"] { background: %(acc)s; color: #0b1020; border-color: %(acc)s; font-weight: 600; }
QPushButton[kind="danger"] { background: %(bad)s; color: #1a0b0b; border-color: %(bad)s; font-weight: 600; }
QPushButton[kind="ok"] { background: %(ok)s; color: #06180f; border-color: %(ok)s; font-weight: 600; }
QPushButton[kind="flat"] { background: transparent; border: none; color: %(mut)s; padding: 2px 6px; }
QPushButton[kind="flat"]:hover { color: %(tx)s; }
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
  background: %(code)s; border: 1px solid %(line)s; border-radius: 8px; padding: 5px 8px; selection-background-color: %(acc)s; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: %(acc)s; }
QComboBox QAbstractItemView { background: %(panel2)s; border: 1px solid %(line)s; selection-background-color: %(acc)s; }
QListWidget { background: transparent; border: none; outline: 0; }
QListWidget::item { padding: 7px 10px; border-radius: 8px; color: %(mut)s; }
QListWidget::item:selected { background: %(panel2)s; color: %(tx)s; }
QListWidget::item:hover { background: %(panel2)s; }
QTableWidget { background: %(code)s; border: 1px solid %(line)s; border-radius: 8px; gridline-color: %(line)s; }
QHeaderView::section { background: %(panel2)s; border: none; padding: 5px; color: %(mut)s; }
QTableWidget::item:selected { background: #2a3350; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: %(line)s; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar:horizontal { height: 0; }
QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; }
QProgressBar { background: %(code)s; border: 1px solid %(line)s; border-radius: 6px; text-align: center; height: 16px; }
QProgressBar::chunk { background: %(acc)s; border-radius: 5px; }
QToolTip { background: %(panel2)s; border: 1px solid %(line)s; color: %(tx)s; padding: 4px; }
QMenu { background: %(panel2)s; border: 1px solid %(line)s; padding: 4px; }
QMenu::item { padding: 6px 18px; border-radius: 6px; }
QMenu::item:selected { background: #2a3350; }
QTabWidget::pane { border: 1px solid %(line)s; border-radius: 8px; top: -1px; }
QTabBar::tab { background: transparent; padding: 7px 14px; color: %(mut)s; }
QTabBar::tab:selected { color: %(tx)s; border-bottom: 2px solid %(acc)s; }
/* chat */
#userBubble { background: %(panel2)s; border: 1px solid %(line)s; border-radius: 12px; }
#card { background: %(panel)s; border: 1px solid %(line)s; border-radius: 10px; }
#card[state="pending"] { border: 1px solid %(acc)s; }
#card[state="danger"] { border: 1px solid %(bad)s; }
#cardHead { background: %(panel2)s; border-top-left-radius: 10px; border-top-right-radius: 10px; }
QLabel#badge { color: %(mut)s; border: 1px solid %(line)s; border-radius: 9px; padding: 0px 8px; font-size: 8pt; }
QLabel#badgeWarn { color: %(bad)s; border: 1px solid %(bad)s; border-radius: 9px; padding: 0px 8px; font-size: 8pt; }
QLabel#status[kind="ok"] { color: %(ok)s; } QLabel#status[kind="bad"] { color: %(bad)s; } QLabel#status[kind="run"] { color: %(warn)s; }
QPlainTextEdit#mono { background: %(code)s; border: none; border-radius: 8px; font-family: Consolas; font-size: 9.5pt; }
QPlainTextEdit#mono[kind="add"] { border-left: 3px solid %(ok)s; } QPlainTextEdit#mono[kind="del"] { border-left: 3px solid %(bad)s; }
QLabel#note { background: %(panel2)s; color: %(mut)s; border-radius: 8px; padding: 8px 12px; }
QLabel#err { background: #2a1517; color: #ffb3b3; border: 1px solid #5a2a2e; border-radius: 8px; padding: 8px 12px; }
QLabel#chip { border: 1px solid %(line)s; border-radius: 10px; padding: 2px 10px; color: %(mut)s; }
QLabel#chip[kind="busy"] { color: %(warn)s; border-color: %(warn)s; } QLabel#chip[kind="wait"] { color: %(acc)s; border-color: %(acc)s; }
#noteBox { background: %(panel2)s; border-radius: 8px; }
#errBox { background: #2a1517; border: 1px solid #5a2a2e; border-radius: 8px; }
#banner { background: #2a2314; border: 1px solid #5a4a1f; border-radius: 8px; }
#banner QLabel { color: %(warn)s; }
QLabel#stats { color: %(mut)s; font-size: 8pt; }
QToolButton { background: transparent; border: none; color: %(mut)s; }
QToolButton:hover { color: %(tx)s; }
""" % C


def apply(app):
    """Estilo Fusion + paleta oscura (casillas, seleccion) + hoja de estilos."""
    from PySide6.QtGui import QPalette
    app.setStyle("Fusion")
    pal = QPalette()
    for role, col in ((QPalette.Window, C["bg"]), (QPalette.WindowText, C["tx"]), (QPalette.Base, C["code"]), (QPalette.AlternateBase, C["panel2"]),
                      (QPalette.Text, C["tx"]), (QPalette.Button, C["panel2"]), (QPalette.ButtonText, C["tx"]), (QPalette.Highlight, C["acc"]),
                      (QPalette.HighlightedText, "#0b1020"), (QPalette.ToolTipBase, C["panel2"]), (QPalette.ToolTipText, C["tx"]),
                      (QPalette.PlaceholderText, C["mut"]), (QPalette.Link, C["acc"])):
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(QSS)


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
    dpr = 2.0      # nitido en pantallas con escalado
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
    """Icono de la app: degradado con el glifo de terminal."""
    glyph = QPixmap(os.path.join(ICON_DIR, "cod_terminal.png"))
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(s, s)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        g = QLinearGradient(0, 0, s, s)
        g.setColorAt(0, QColor("#7c9cff"))
        g.setColorAt(1, QColor("#a78bfa"))
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
            tp.fillRect(tint.rect(), QColor("#0b1020"))
            tp.end()
            p.drawPixmap((s - tint.width()) // 2, (s - tint.height()) // 2, tint)
        p.end()
        ic.addPixmap(pm)
    return ic
