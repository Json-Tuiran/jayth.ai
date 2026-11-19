"""Identidad visual de Jayth: carbón verdoso con el verde solo como acento (basado en el sistema de diseño
de Reality Engine, con verdes más sutiles), en claro y oscuro. Incluye el logo, los iconos teñibles,
tooltips propios y el pulido de ventanas emergentes (esquinas redondeadas y sombra nativas de Windows 11)."""
import os, re, ctypes
from PySide6.QtCore import Qt, QRectF, QObject, QEvent
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPalette, QGuiApplication, QImage
from PySide6.QtWidgets import QProxyStyle, QStyle, QWidget
from . import paths, osys

ICON_DIR = os.path.join(paths.ASSETS, "icons")
LOGO = os.path.join(paths.ASSETS, "logo.svg")
UI_FONT = osys.ui_font()
MONO_FONT = osys.mono_font()
_cache = {}

PALETTES = {
    # Reality Engine: Fondo #141716 · Panel #171B1A · Hundida #121715 · Texto #EBF2F0 · Secundario #7A8F85 · Acento #3EBE78 (aquí, más sutil)
    "dark": {"bg": "#141716", "side": "#111413", "panel": "#1A1F1D", "panel2": "#222926", "hover": "#1E2622", "line": "#27302C",
             "tx": "#EBF2F0", "mut": "#97A69E", "faint": "#677870", "acc": "#52B788", "acc_hi": "#6CC99C", "acc_bg": "#1A2D23",
             "on_acc": "#0B140F", "ok": "#5CC98C", "bad": "#F07A7A", "bad_bg": "#2A1618", "warn": "#E9B54E", "warn_bg": "#2A2313",
             "info": "#5BB8E8", "code": "#0F1211", "send": "#EBF2F0", "on_send": "#141716", "close": "#C42B35"},
    "light": {"bg": "#FBFCFB", "side": "#F2F5F3", "panel": "#EFF3F1", "panel2": "#E4EBE7", "hover": "#E9EFEB", "line": "#DAE2DE",
              "tx": "#16201B", "mut": "#54655C", "faint": "#86958D", "acc": "#2E8F62", "acc_hi": "#3AA572", "acc_bg": "#E1F1E8",
              "on_acc": "#FFFFFF", "ok": "#1F9A5B", "bad": "#CC4444", "bad_bg": "#FCEDED", "warn": "#AE720E", "warn_bg": "#FBF2E1",
              "info": "#1D7FB6", "code": "#F4F7F5", "send": "#16201B", "on_send": "#FFFFFF", "close": "#C42B35"},
}
C = dict(PALETTES["dark"])
MODE = "dark"
SCALE = [1.0]

QSS_T = """
* { font-family: 'Segoe UI'; font-size: 10pt; color: %(tx)s; }
QMainWindow, QDialog, #central, #chatHolder, #main { background: %(bg)s; }
QWidget#sidebar { background: %(side)s; }
QWidget#titlebar { background: %(bg)s; }
QLabel#h1 { font-size: 13pt; font-weight: 600; }
QLabel#greeting { font-size: 20pt; font-weight: 600; }
QLabel#muted { color: %(mut)s; }
QLabel#faint, QLabel#stats { color: %(faint)s; font-size: 9pt; }
QLabel#section { color: %(faint)s; font-size: 8.5pt; padding: 10px 8px 2px 8px; }
QPushButton#sectionBtn { background: transparent; border: none; color: %(faint)s; font-size: 8.5pt; padding: 4px 6px; text-align: left; border-radius: 6px; }
QPushButton#sectionBtn:hover { color: %(tx)s; background: %(hover)s; }
QPushButton { background: %(panel)s; border: 1px solid %(line)s; border-radius: 8px; padding: 6px 12px; }
QPushButton:hover { background: %(hover)s; border-color: %(faint)s; }
QPushButton:pressed { background: %(panel2)s; }
QPushButton:disabled { color: %(faint)s; }
QPushButton[kind="primary"], QPushButton[kind="ok"] { background: %(acc)s; color: %(on_acc)s; border-color: %(acc)s; font-weight: 600; }
QPushButton[kind="primary"]:hover, QPushButton[kind="ok"]:hover { background: %(acc_hi)s; border-color: %(acc_hi)s; }
QPushButton[kind="primary"]:disabled, QPushButton[kind="ok"]:disabled { background: %(panel2)s; color: %(faint)s; border-color: %(line)s; }
QPushButton[kind="danger"] { background: transparent; color: %(bad)s; border-color: %(bad)s; }
QPushButton[kind="danger"]:hover { background: %(bad_bg)s; }
QPushButton[kind="flat"] { background: transparent; border: none; color: %(mut)s; padding: 4px 8px; }
QPushButton[kind="flat"]:hover { color: %(tx)s; background: %(hover)s; }
QPushButton#nav { background: transparent; border: none; text-align: left; padding: 7px 8px; color: %(tx)s; border-radius: 8px; }
QPushButton#nav:hover { background: %(hover)s; }
QFrame#segment { background: %(panel)s; border: 1px solid %(line)s; border-radius: 10px; }
QPushButton#segBtn { background: transparent; border: none; border-radius: 7px; padding: 5px 8px; color: %(mut)s; }
QPushButton#segBtn:hover { color: %(tx)s; }
QPushButton#segBtn:checked { background: %(panel2)s; color: %(tx)s; font-weight: 600; }
QPushButton#winBtn, QPushButton#winClose { background: transparent; border: none; border-radius: 0; padding: 0; color: %(mut)s;
  font-family: 'Segoe Fluent Icons', 'Segoe MDL2 Assets'; font-size: 7.5pt; min-width: 46px; max-width: 46px; }
QPushButton#winBtn:hover { background: %(hover)s; color: %(tx)s; }
QPushButton#winClose:hover { background: %(close)s; color: #FFFFFF; }
QPushButton#suggestion { background: transparent; border: 1px solid %(line)s; border-radius: 12px; padding: 10px 14px; text-align: left; color: %(mut)s; }
QPushButton#suggestion:hover { background: %(panel)s; color: %(tx)s; border-color: %(faint)s; }
QPushButton#updateBtn { background: %(acc_bg)s; color: %(acc)s; border: 1px solid %(acc)s; border-radius: 8px; padding: 6px 10px; text-align: left; }
QPushButton#updateBtn:hover { background: %(acc)s; color: %(on_acc)s; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; padding: 7px 14px; color: %(mut)s; }
QTabBar::tab:selected { color: %(tx)s; border-bottom: 2px solid %(acc)s; }
QTabBar::tab:!selected:hover { color: %(tx)s; }
QTreeView { outline: 0; }
QToolButton { background: transparent; border: none; border-radius: 8px; padding: 4px; color: %(mut)s; }
QToolButton:hover { background: %(hover)s; color: %(tx)s; }
QToolButton::menu-indicator { image: none; width: 0; }
QToolButton#modelBtn { font-size: 11pt; font-weight: 600; color: %(tx)s; padding: 5px 10px; }
QToolButton#chip { border: 1px solid %(line)s; border-radius: 13px; padding: 3px 10px; color: %(mut)s; font-size: 9pt; }
QToolButton#chip:checked { background: %(acc_bg)s; color: %(acc)s; border-color: %(acc)s; }
QToolButton#chip:hover { color: %(tx)s; border-color: %(faint)s; }
QToolButton#round { border: 1px solid %(line)s; border-radius: 14px; }
QToolButton#sendBtn { background: %(send)s; border-radius: 16px; }
QToolButton#sendBtn:hover { background: %(acc_hi)s; }
QToolButton#sendBtn:disabled { background: %(panel2)s; }
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
  background: %(panel)s; border: 1px solid %(line)s; border-radius: 8px; padding: 5px 8px; selection-background-color: %(acc)s; selection-color: %(on_acc)s; }
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover { border-color: %(faint)s; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus { border-color: %(acc)s; }
QLineEdit#search { background: %(bg)s; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: %(panel)s; border: 1px solid %(line)s; padding: 4px; outline: 0;
  selection-background-color: %(acc_bg)s; selection-color: %(tx)s; }
QFrame#composerBox { background: %(panel)s; border: 1px solid %(line)s; border-radius: 18px; }
QFrame#composerBox[focus="true"] { border-color: %(acc)s; }
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
QToolTip { background: %(panel2)s; border: 1px solid %(line)s; color: %(tx)s; padding: 6px 9px; font-size: 9pt; }
QMenu { background: %(panel)s; border: 1px solid %(line)s; padding: 6px; }
QMenu::item { padding: 7px 26px 7px 10px; border-radius: 6px; }
QMenu::item:selected { background: %(hover)s; }
QMenu::item:disabled { color: %(faint)s; }
QMenu::separator { height: 1px; background: %(line)s; margin: 5px 8px; }
QMenu::indicator { width: 14px; height: 14px; }
QMenu::icon { padding-left: 6px; }
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
QFrame#toast { background: %(panel2)s; border: 1px solid %(line)s; border-radius: 12px; }
QFrame#planBox { background: %(panel)s; border: 1px solid %(line)s; border-radius: 12px; }
QLabel#badgeWarn { color: %(warn)s; font-size: 9pt; }
QLabel#badge { color: %(acc)s; background: %(acc_bg)s; border-radius: 8px; padding: 1px 7px; font-size: 8.5pt; }
QLabel#status[kind="ok"] { color: %(ok)s; } QLabel#status[kind="bad"] { color: %(bad)s; } QLabel#status[kind="run"] { color: %(warn)s; }
QLabel#avatar { background: %(acc_bg)s; color: %(acc)s; border-radius: 13px; font-weight: 600; font-size: 9pt; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; }
"""
QSS_T = QSS_T.replace("'Segoe UI'", UI_FONT).replace("font-family: Consolas", "font-family: " + MONO_FONT)
QSS = QSS_T % C


class _Style(QProxyStyle):
    """Tooltips que aparecen antes y se quedan lo justo (los de Qt tardan casi un segundo)."""

    def styleHint(self, hint, option=None, widget=None, data=None):
        if hint == QStyle.SH_ToolTip_WakeUpDelay:
            return 380
        if hint == QStyle.SH_ToolTip_FallAsleepDelay:
            return 1600
        return super().styleHint(hint, option, widget, data)


# ---------------------------------------------------------------- ventanas emergentes con el diseño del programa
def _dwm(hwnd, attr, val):
    if not osys.WIN:
        return
    v = ctypes.c_int(val)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))


def _colorref(hexcol):
    h = hexcol.lstrip("#")
    return int(h[4:6], 16) << 16 | int(h[2:4], 16) << 8 | int(h[0:2], 16)   # 0x00BBGGRR


def titlebar_colors(w):
    """Barra de titulo nativa con los colores del tema (Windows 11), para dialogos."""
    if os.name != "nt":
        return
    try:
        hwnd = int(w.winId())
        _dwm(hwnd, 20, 1 if MODE == "dark" else 0)      # modo oscuro
        _dwm(hwnd, 35, _colorref(C["bg"]))              # color de la barra
        _dwm(hwnd, 36, _colorref(C["tx"]))              # color del texto
        _dwm(hwnd, 34, _colorref(C["line"]))            # borde
    except Exception:
        pass


def rounded(w, small=False):
    """Esquinas redondeadas y sombra nativas (Windows 11) para menus, desplegables y tooltips."""
    if os.name != "nt":
        return
    try:
        _dwm(int(w.winId()), 33, 3 if small else 2)    # DWMWA_WINDOW_CORNER_PREFERENCE: redondeado / pequeño
    except Exception:
        pass


class _Polisher(QObject):
    def eventFilter(self, obj, e):
        if e.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
            cls = obj.metaObject().className()
            if cls in ("QMenu", "QComboBoxPrivateContainer"):
                rounded(obj)
            elif cls == "QTipLabel":
                rounded(obj, small=True)
            elif obj.inherits("QDialog") and not getattr(obj, "_titled", False):
                obj._titled = True
                titlebar_colors(obj)
        return False


_polisher = None


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
    """Aplica el tema (system | dark | light) y el tamaño de texto (%): estilo, paleta, hoja de estilos y pulido de ventanas."""
    global QSS, MODE, _polisher
    MODE = resolve(name)
    C.clear()
    C.update(PALETTES[MODE])
    f = max(0.7, min(1.6, (scale or 100) / 100.0))
    QSS = re.sub(r"(\d+(?:\.\d+)?)pt", lambda m: "%.1fpt" % (float(m.group(1)) * f), QSS_T % C)
    SCALE[0] = f
    _cache.clear()
    app.setStyle(_Style("Fusion"))
    pal = QPalette()
    for role, col in ((QPalette.Window, C["bg"]), (QPalette.WindowText, C["tx"]), (QPalette.Base, C["panel"]), (QPalette.AlternateBase, C["panel2"]),
                      (QPalette.Text, C["tx"]), (QPalette.Button, C["panel"]), (QPalette.ButtonText, C["tx"]), (QPalette.Highlight, C["acc"]),
                      (QPalette.HighlightedText, C["on_acc"]), (QPalette.ToolTipBase, C["panel2"]), (QPalette.ToolTipText, C["tx"]),
                      (QPalette.PlaceholderText, C["faint"]), (QPalette.Link, C["acc"])):
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
    if _polisher is None:
        _polisher = _Polisher(app)
        app.installEventFilter(_polisher)
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


def logo(size):
    """Logo de Jayth (assets/logo.svg) como imagen nítida del tamaño pedido."""
    key = ("__logo__", size)
    if key in _cache:
        return _cache[key]
    from PySide6.QtSvg import QSvgRenderer
    dpr = 2.0
    img = QImage(int(size * dpr), int(size * dpr), QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(LOGO).render(p, QRectF(0, 0, img.width(), img.height()))
    p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    _cache[key] = pm
    return pm


def make_icon():
    ic = QIcon()
    for s in (16, 20, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(logo(s))
    return ic
