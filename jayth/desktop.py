# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Aplicacion de escritorio Jayth (Qt). Dos modos:
- Chat: conversaciones para cualquier tarea.
- Code: proyectos con arbol de archivos, editor, terminal y el agente trabajando dentro de la carpeta del proyecto."""
import os, re, sys, json, uuid, time, shutil, threading, ctypes, datetime, subprocess
from PySide6.QtCore import (Qt, QTimer, Signal, QObject, QSize, QPoint, QRect, QEvent, QPropertyAnimation, QEasingCurve,
                            QParallelAnimationGroup)
from PySide6.QtGui import QPixmap, QImage, QKeySequence, QShortcut, QGuiApplication, QActionGroup, QCursor, QTransform, QFont, QIcon, QTextCursor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
                               QListWidget, QListWidgetItem, QScrollArea, QFrame, QPlainTextEdit, QFileDialog, QMessageBox, QMenu,
                               QSystemTrayIcon, QSizePolicy, QToolButton, QInputDialog, QLineEdit, QStackedWidget, QSplitter,
                               QGraphicsOpacityEffect, QAbstractButton, QComboBox, QLayout)
from . import APP_NAME, core, paths, osys, i18n, agent as A, tools as T
from .i18n import tr
if osys.WIN:
    from ctypes import wintypes
from . import theme, panels
from .theme import C, restyle, make_icon, icon, pix
from .wizard import SetupWizard, ModelsDialog, btn, lbl, set_icon, run_bg
from .settings_ui import SettingsDialog
from .codeview import EditorTabs, FileTree, Terminal, ProjectDialog
from .feedback import FeedbackDialog
from .widgets import TextView, FlowLayout, OptionRow, ElidedLabel, FitLabel, Collapsible, elide_list
from . import updater
from . import chatview as CV
from . import overlay as OV

MODE_LABEL = {k: v.split(":")[0] for k, v in A.MODES.items()}
CODE_NAME = APP_NAME + " Code"
SHOW_IN = tr("Mostrar en el Explorador") if osys.WIN else (tr("Mostrar en el Finder") if osys.MAC else tr("Abrir la carpeta"))


# ---------------------------------------------------------------- utilidades de interfaz
def pix_label(name, color=None, size=16):
    l = QLabel()
    l.setPixmap(pix(name, color, size))
    l.setFixedSize(size + 4, size + 4)
    l.setAlignment(Qt.AlignCenter)
    return l


def tbtn(ico, tip="", cb=None, color=None, size=18, name=None):
    b = QToolButton()
    b.setIcon(icon(ico, color or C["mut"], size))
    b.setIconSize(QSize(size, size))
    b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    if name:
        b.setObjectName(name)
    if cb:
        b.clicked.connect(cb)
    return b


def hline():
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet("background:%s" % C["line"])
    return f


def mono(text, kind=None, max_h=260):
    """Codigo o salida de un comando: caja monoespaciada que se parte al ancho; si es larga se muestra plegada
    (difuminado abajo y flecha para verla entera) en vez de una barra de desplazamiento dentro del chat."""
    return Collapsible(TextView(text, "plain", mono=True, kind=kind), limit=max_h, fade=C["bg"], slack=40)


def md_label(text=""):
    """Respuesta del agente en Markdown. Nunca ensancha el panel: parte código, rutas y URL largas. Los bloques de código
    llevan barra propia, los comandos botones de copiar y ejecutar y las rutas son enlaces (ver chatview)."""
    v = CV.MessageView("10.5pt")
    v.setText(text)
    return v


class Clickable(QWidget):
    clicked = Signal()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()


_HOTKEY = None
_SPEAKER, _SPEAKING, _SPEAK_OK = None, None, None


def speaker():
    """Lector de voz único de la aplicación."""
    global _SPEAKER
    if _SPEAKER is None:
        from .voice import Speaker
        _SPEAKER = Speaker()
    return _SPEAKER


def speaker_available():
    global _SPEAK_OK
    if _SPEAK_OK is None:
        try:
            from .voice import Speaker
            _SPEAK_OK = Speaker.available()
        except Exception:
            _SPEAK_OK = False
    return _SPEAK_OK

# ---------------------------------------------------------------- animaciones
def animations_on():
    return core.SET.snapshot().get("animations", True)


def fade_in(w, ms=220):
    """Aparicion suave; el efecto se retira al terminar (los efectos graficos ralentizan el texto)."""
    if not animations_on():
        return
    eff = QGraphicsOpacityEffect(w)
    eff.setOpacity(0.0)
    w.setGraphicsEffect(eff)
    a = QPropertyAnimation(eff, b"opacity", w)
    a.setDuration(ms)
    a.setStartValue(0.0)
    a.setEndValue(1.0)
    a.setEasingCurve(QEasingCurve.OutCubic)
    a.finished.connect(lambda: w.setGraphicsEffect(None))
    a.start(QPropertyAnimation.DeleteWhenStopped)


class Spinner(QLabel):
    """Icono de carga que gira (o fijo si las animaciones estan desactivadas)."""

    def __init__(self, name="est_cargando", color=None, size=14):
        super().__init__()
        self.base = pix(name, color or C["acc"], size)
        self.size_ = size
        self.setFixedSize(size + 4, size + 4)
        self.setAlignment(Qt.AlignCenter)
        self.angle = 0
        self.t = QTimer(self, interval=60, timeout=self._step)
        self.setPixmap(self.base)

    def start(self, name=None, color=None):
        if name:
            self.base = pix(name, color or C["acc"], self.size_)
        self.setPixmap(self.base)
        if animations_on():
            self.t.start()

    def stop(self, pixmap=None):
        self.t.stop()
        self.setPixmap(pixmap or self.base)

    def _step(self):
        self.angle = (self.angle + 30) % 360
        p = self.base.transformed(QTransform().rotate(self.angle), Qt.SmoothTransformation)
        p.setDevicePixelRatio(self.base.devicePixelRatio())
        self.setPixmap(p)


class WaveBars(QWidget):
    """Onda de audio: barras que avanzan de derecha a izquierda con el volumen del micrófono. En modo «procesando»
    las barras ondulan suavemente (mientras la voz se pasa a texto)."""

    def __init__(self, bars=48):
        super().__init__()
        from collections import deque
        self.levels = deque([0.0] * bars, maxlen=bars)
        self.busy = False
        self.phase = 0.0
        self.setMinimumHeight(28)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def push(self, level):
        self.levels.append(max(0.0, min(1.0, level)))
        self.update()

    def set_busy(self, on):
        self.busy = on
        self.update()

    def tick(self):
        self.phase += 0.35
        self.update()

    def paintEvent(self, e):
        from PySide6.QtGui import QPainter, QColor
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self.levels)
        w, h = self.width(), self.height()
        step = w / float(n)
        bw = max(2.0, step * 0.55)
        col = QColor(C["acc"] if not self.busy else C["mut"])
        p.setPen(Qt.NoPen)
        for i, lv in enumerate(self.levels):
            if self.busy:
                lv = 0.25 + 0.2 * math.sin(self.phase + i * 0.45)
            bh = max(3.0, lv * (h - 4))
            x = i * step + (step - bw) / 2
            col.setAlphaF(0.45 + 0.55 * (i / float(n)))       # lo más reciente (a la derecha) más intenso
            p.setBrush(col)
            p.drawRoundedRect(x, (h - bh) / 2, bw, bh, bw / 2, bw / 2)
        p.end()


class Toast(QFrame):
    """Aviso flotante dentro de la ventana (abajo a la derecha) con accion opcional."""

    def __init__(self, parent, text, action=None, on_action=None, ms=7000, icon_name="est_info", color=None):
        super().__init__(parent)
        self.setObjectName("toast")
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 10, 8, 10)
        h.setSpacing(10)
        h.addWidget(pix_label(icon_name, color or C["acc"], 16), 0, Qt.AlignTop)
        t = lbl(text)
        t.setMaximumWidth(330)
        h.addWidget(t, 1)
        if action:
            b = btn(action, "primary")
            b.clicked.connect(lambda: (on_action(), self.close_()))
            h.addWidget(b, 0, Qt.AlignVCenter)
        h.addWidget(tbtn("ui_cerrar", tr("Cerrar"), self.close_, size=11), 0, Qt.AlignTop)
        self.adjustSize()
        self.eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.eff)
        self.eff.setOpacity(0.0)
        self._place()
        self.show()
        self.raise_()
        self._anim(1.0)
        QTimer.singleShot(ms, self.close_)

    def _place(self, dy=0):
        p = self.parentWidget()
        self.move(p.width() - self.width() - 22, p.height() - self.height() - 120 - dy)

    def _anim(self, to, done=None):
        a = QPropertyAnimation(self.eff, b"opacity", self)
        a.setDuration(200 if animations_on() else 1)
        a.setStartValue(self.eff.opacity())
        a.setEndValue(to)
        if done:
            a.finished.connect(done)
        a.start(QPropertyAnimation.DeleteWhenStopped)

    def close_(self):
        try:
            if self.isVisible() and not getattr(self, "_closing", False):
                self._closing = True
                self._anim(0.0, self.deleteLater)
        except RuntimeError:      # ya destruido
            pass


class ImageLabel(QLabel):
    """Imagen que se reduce al ancho disponible (sin ensanchar el panel); clic para verla a tamaño completo."""

    def __init__(self, path, max_w=600, max_h=380):
        super().__init__()
        self.path = path
        self.max_w, self.max_h = max_w, max_h
        self.src = QPixmap(path)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setMinimumWidth(40)
        self._scaled_w = -1
        self._rescale(max_w)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tr("Clic para abrir a tamaño completo"))

    def _rescale(self, avail):
        if self.src.isNull():
            return
        w = max(40, min(self.max_w, avail))
        if w == self._scaled_w:
            return
        self._scaled_w = w
        pm = self.src.scaled(w, self.max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pm)
        self.setFixedHeight(pm.height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._rescale(self.width())

    def sizeHint(self):
        pm = self.pixmap()
        return QSize(pm.width() if pm is not None and not pm.isNull() else 40, self.height())

    def mousePressEvent(self, e):
        if os.path.isfile(self.path):
            osys.open_path(self.path)


def note(text, error=False):
    f = QFrame()
    f.setObjectName("errBox" if error else "noteBox")
    h = QHBoxLayout(f)
    h.setContentsMargins(12, 8, 12, 8)
    h.addWidget(pix_label("est_error" if error else "est_info", C["bad"] if error else C["mut"]), 0, Qt.AlignTop)
    h.addWidget(TextView(text, "plain", color=C["bad"] if error else C["mut"]), 1)
    return f


GROUP_ROLE = Qt.UserRole + 1
# nombre interno del grupo (se guarda en «folded» de los ajustes) -> texto que se muestra
GROUP_NAMES = {"Hoy": tr("Hoy"), "Ayer": tr("Ayer"), "Últimos 7 días": tr("Últimos 7 días"),
               "Últimos 30 días": tr("Últimos 30 días"), "Anteriores": tr("Anteriores")}


def fill_history(lst, sessions, current, query="", empty_text=tr("Tus conversaciones aparecerán aquí"), folded=()):
    """Rellena una lista con conversaciones agrupadas por fecha (Hoy, Ayer, …). Los grupos en 'folded' salen plegados
    (clic en la cabecera del grupo para plegar o desplegar). Al buscar se muestran todos."""
    lst.blockSignals(True)
    lst.clear()
    today = datetime.date.today()
    groups = []
    for s in sessions:
        d = (today - datetime.date.fromtimestamp(s.updated)).days
        grp = "Hoy" if d <= 0 else "Ayer" if d == 1 else "Últimos 7 días" if d < 7 else "Últimos 30 días" if d < 30 else "Anteriores"
        if not groups or groups[-1][0] != grp:
            groups.append((grp, []))
        groups[-1][1].append(s)
    for grp, items in groups:
        shut = grp in folded and not query and not any(s.id == current for s in items)
        shown = GROUP_NAMES.get(grp, grp)
        h = QListWidgetItem(("▸  %s  ·  %d" % (shown, len(items))) if shut else ("▾  " + shown))
        h.setFlags(Qt.ItemIsEnabled)
        h.setData(GROUP_ROLE, grp)
        h.setToolTip(tr("Clic para desplegar") if shut else tr("Clic para plegar"))
        h.setForeground(QGuiApplication.palette().placeholderText())
        f = h.font()
        f.setPointSizeF(8.5)
        h.setFont(f)
        lst.addItem(h)
        if shut:
            continue
        for s in items:
            _history_item(lst, s, current)
    if not sessions:
        e = QListWidgetItem(tr("Sin resultados") if query else empty_text)
        e.setFlags(Qt.NoItemFlags)
        e.setForeground(QGuiApplication.palette().placeholderText())
        lst.addItem(e)
    lst.blockSignals(False)


def _history_item(lst, s, current):
    it = QListWidgetItem(s.title)
    if s.run is not None:
        it.setIcon(icon("est_cargando", C["warn"], 14))
    it.setData(Qt.UserRole, s.id)
    it.setToolTip(s.title)
    lst.addItem(it)
    if s.id == current:
        it.setSelected(True)
        lst.setCurrentItem(it)


# ---------------------------------------------------------------- descripcion legible de cada accion
def _n(n, one, many):
    """'1 cambio' / '3 cambios'."""
    return "%d %s" % (n, one if n == 1 else many)


def _b(p):
    p = str(p or "").rstrip("\\/")
    return os.path.basename(p) or p


def _q(s, n=56):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


STEP = {  # herramienta: (infinitivo, pasado, objeto)
    "read_file": (tr("leer"), tr("Leyó"), lambda a: _b(a.get("path"))),
    "write_file": (tr("escribir"), tr("Escribió"), lambda a: _b(a.get("path"))),
    "create_document": (tr("crear el documento"), tr("Creó el documento"), lambda a: _b(a.get("path"))),
    "run_python": (tr("analizar con Python"), tr("Analizó con Python"), lambda a: ""),
    "show_canvas": (tr("mostrar en el lienzo"), tr("Mostró en el lienzo"), lambda a: tr("«%s»") % _q(a.get("title"), 50)),
    "edit_file": (tr("editar"), tr("Editó"), lambda a: _b(a.get("path"))),
    "list_dir": (tr("listar"), tr("Listó"), lambda a: _b(a.get("path")) or tr("la carpeta de trabajo")),
    "search_files": (tr("buscar"), tr("Buscó"), lambda a: tr("«%s»") % _q(a.get("pattern") or a.get("glob") or "*", 40)),
    "run_command": (tr("ejecutar"), tr("Ejecutó"), lambda a: _q(a.get("command", "").splitlines()[0] if a.get("command") else "")),
    "open_target": (tr("abrir"), tr("Abrió"), lambda a: _b(a.get("target"))),
    "wait": (tr("esperar"), tr("Esperó"), lambda a: "%s s" % a.get("seconds")),
    "web_fetch": (tr("leer"), tr("Leyó"), lambda a: _q(str(a.get("url", "")).split("//")[-1], 48)),
    "web_search": (tr("buscar en la web"), tr("Buscó en la web"), lambda a: tr("«%s»") % _q(a.get("query"), 44)),
    "download_file": (tr("descargar"), tr("Descargó"), lambda a: _b(str(a.get("url", "")).split("?")[0])),
    "screenshot": (tr("capturar la pantalla"), tr("Capturó la pantalla"), lambda a: ""),
    "click": (tr("hacer clic"), tr("Hizo clic"), lambda a: tr("en (%s, %s)") % (a.get("x"), a.get("y"))),
    "move_mouse": (tr("mover el ratón"), tr("Movió el ratón"), lambda a: tr("a (%s, %s)") % (a.get("x"), a.get("y"))),
    "scroll": (tr("desplazar"), tr("Desplazó"), lambda a: str(a.get("amount"))),
    "type_text": (tr("escribir"), tr("Escribió"), lambda a: tr("«%s»") % _q(a.get("text"), 40)),
    "press_keys": (tr("pulsar"), tr("Pulsó"), lambda a: str(a.get("keys", ""))),
    "list_windows": (tr("listar las ventanas"), tr("Listó las ventanas"), lambda a: ""),
    "focus_window": (tr("activar la ventana"), tr("Activó la ventana"), lambda a: tr("«%s»") % _q(a.get("title"), 40)),
    "multi_edit": (tr("editar"), tr("Editó"), lambda a: "%s (%s)" % (_b(a.get("path")), _n(len(a.get("edits") or []), tr("cambio"), tr("cambios")))),
    "move_path": (tr("mover"), tr("Movió"), lambda a: "%s → %s" % (_b(a.get("source")), _b(a.get("dest")))),
    "delete_path": (tr("enviar a la papelera"), tr("Envió a la papelera"), lambda a: _b(a.get("path"))),
    "command_output": (tr("revisar la salida de"), tr("Revisó la salida de"), lambda a: str(a.get("id"))),
    "stop_command": (tr("detener"), tr("Detuvo"), lambda a: str(a.get("id"))),
    "read_document": (tr("leer el documento"), tr("Leyó el documento"), lambda a: _b(a.get("path"))),
    "view_image": (tr("ver la imagen"), tr("Vio la imagen"), lambda a: _b(a.get("path"))),
    "remember": (tr("recordar"), tr("Recordó"), lambda a: tr("«%s»") % _q(a.get("fact"), 50)),
    "forget": (tr("olvidar"), tr("Olvidó"), lambda a: tr("«%s»") % _q(a.get("text"), 50)),
    "schedule_task": (tr("programar la tarea"), tr("Programó la tarea"), lambda a: tr("«%s»") % _q(a.get("name"), 50)),
    "list_tasks": (tr("ver las tareas programadas"), tr("Consultó las tareas programadas"), lambda a: ""),
    "cancel_task": (tr("quitar la tarea"), tr("Quitó la tarea"), lambda a: tr("«%s»") % _q(a.get("task"), 50)),
    "use_skill": (tr("usar la habilidad"), tr("Usó la habilidad"), lambda a: tr("«%s»") % _q(a.get("name"), 50)),
    "ui_elements": (tr("leer la interfaz de"), tr("Leyó la interfaz de"), lambda a: tr("«%s»") % _q(a.get("window"), 40)),
    "click_element": (tr("pulsar"), tr("Pulsó"), lambda a: (tr("«%s»") % _q(a.get("name"), 40)) if a.get("name") else tr("el elemento %s") % a.get("index")),
    "drag": (tr("arrastrar"), tr("Arrastró"), lambda a: tr("de (%s, %s) a (%s, %s)") % (a.get("x1"), a.get("y1"), a.get("x2"), a.get("y2"))),
    "browser_open": (tr("abrir"), tr("Abrió"), lambda a: _q(str(a.get("url", "")).split("//")[-1], 48)),
    "browser_read": (tr("leer la página"), tr("Leyó la página"), lambda a: ""),
    "browser_click": (tr("pulsar"), tr("Pulsó"), lambda a: (tr("«%s»") % _q(a.get("text"), 40)) if a.get("text") else tr("el elemento %s") % a.get("index")),
    "browser_type": (tr("escribir"), tr("Escribió"), lambda a: tr("«%s»") % _q(a.get("text"), 40)),
    "browser_screenshot": (tr("capturar la página"), tr("Capturó la página"), lambda a: ""),
}
BROWSER_NAV = {"back": (tr("volver atrás"), tr("Volvió atrás"), tr("Volviendo atrás…")), "forward": (tr("ir adelante"), tr("Fue adelante"), tr("Yendo adelante…")),
               "reload": (tr("recargar la página"), tr("Recargó la página"), tr("Recargando la página…")),
               "down": (tr("bajar por la página"), tr("Bajó por la página"), tr("Bajando por la página…")),
               "up": (tr("subir por la página"), tr("Subió por la página"), tr("Subiendo por la página…")),
               "top": (tr("ir al principio de la página"), tr("Fue al principio de la página"), tr("Yendo al principio…")),
               "bottom": (tr("ir al final de la página"), tr("Fue al final de la página"), tr("Yendo al final…"))}
WINDOW_ACT = {"maximize": (tr("maximizar"), tr("Maximizó"), tr("Maximizando")), "minimize": (tr("minimizar"), tr("Minimizó"), tr("Minimizando")),
              "restore": (tr("restaurar"), tr("Restauró"), tr("Restaurando")), "close": (tr("cerrar"), tr("Cerró"), tr("Cerrando")), "move": (tr("mover"), tr("Movió"), tr("Moviendo")),
              "resize": (tr("cambiar el tamaño de"), tr("Cambió el tamaño de"), tr("Cambiando el tamaño de"))}


# mientras se ejecuta: «Escribiendo calculadora.py…», «Ejecutando python app.py…»
GERUND = {
    "read_file": tr("Leyendo"), "write_file": tr("Escribiendo"), "create_document": tr("Creando el documento"), "run_python": tr("Analizando con Python"),
    "show_canvas": tr("Preparando el lienzo"), "edit_file": tr("Editando"), "list_dir": tr("Explorando"), "search_files": tr("Buscando"),
    "run_command": tr("Ejecutando"), "open_target": tr("Abriendo"), "wait": tr("Esperando"), "web_fetch": tr("Leyendo"), "web_search": tr("Buscando en la web"),
    "download_file": tr("Descargando"), "screenshot": tr("Capturando la pantalla"), "click": tr("Haciendo clic"), "move_mouse": tr("Moviendo el ratón"),
    "scroll": tr("Desplazando"), "type_text": tr("Escribiendo"), "press_keys": tr("Pulsando"), "list_windows": tr("Revisando las ventanas"),
    "focus_window": tr("Activando la ventana"), "multi_edit": tr("Editando"), "move_path": tr("Moviendo"), "delete_path": tr("Enviando a la papelera"),
    "command_output": tr("Revisando la salida de"), "stop_command": tr("Deteniendo"), "read_document": tr("Leyendo el documento"),
    "view_image": tr("Mirando la imagen"), "remember": tr("Guardando en la memoria"), "forget": tr("Olvidando"), "schedule_task": tr("Programando la tarea"),
    "list_tasks": tr("Consultando las tareas programadas"), "cancel_task": tr("Quitando la tarea"), "use_skill": tr("Usando la habilidad"),
    "ui_elements": tr("Leyendo la interfaz de"), "click_element": tr("Pulsando"), "drag": tr("Arrastrando"),
    "browser_open": tr("Abriendo"), "browser_read": tr("Leyendo la página"), "browser_click": tr("Pulsando"), "browser_type": tr("Escribiendo"),
    "browser_screenshot": tr("Capturando la página"),
}


def describe_parts(name, args, phase):
    """(verbo, objeto): «Escribió» + «calculadora.py». El objeto se resalta en la interfaz."""
    args = args or {}
    if name.startswith("mcp__"):           # herramienta de un conector MCP: «Usó servidor › herramienta»
        parts = name.split("__")
        srv, tool = (parts[1].replace("_", " "), parts[2].replace("_", " ")) if len(parts) > 2 else (name, "")
        lead = {"pending": tr("Quiere usar"), "run": tr("Usando")}.get(phase, tr("Usó"))
        return lead, "%s › %s%s" % (srv, tool, "…" if phase == "run" else "")
    if name == "browser_nav":
        inf, past, ger = BROWSER_NAV.get(str(args.get("action", "")).lower(), (tr("navegar"), tr("Navegó"), tr("Navegando…")))
        return {"pending": tr("Quiere %s") % inf, "run": ger}.get(phase, past), ""
    if name == "window_action":
        inf, past, ger = WINDOW_ACT.get(str(args.get("action", "")).lower(), (tr("manejar"), tr("Manejó"), tr("Manejando")))
        lead = {"pending": tr("Quiere %s") % inf, "run": ger}.get(phase, past)
        return tr("%s la ventana") % lead, tr("«%s»%s") % (_q(args.get("window"), 40), "…" if phase == "run" else "")
    if name == "clipboard":
        w = str(args.get("action", "")).lower() in ("write", "set", "copy")
        inf, past, ger = (tr("copiar al portapapeles"), tr("Copió al portapapeles"), tr("Copiando al portapapeles")) if w else \
                         (tr("leer el portapapeles"), tr("Leyó el portapapeles"), tr("Leyendo el portapapeles"))
        lead = {"pending": tr("Quiere %s") % inf, "run": ger + ("" if w else "…")}.get(phase, past)
        return lead, (tr("«%s»") % _q(args.get("text"), 40)) if w else ""
    if name == "screenshot" and args.get("zoom"):
        return {"pending": tr("Quiere ampliar una zona de la pantalla"), "run": tr("Ampliando una zona de la pantalla…")}.get(phase, tr("Amplió una zona de la pantalla")), ""
    if name == "screenshot" and args.get("window"):            # captura de una sola ventana
        lead = {"pending": tr("Quiere capturar la ventana"), "run": tr("Capturando la ventana")}.get(phase, tr("Capturó la ventana"))
        return lead, tr("«%s»%s") % (_q(args["window"], 40), "…" if phase == "run" else "")
    if name == "run_command" and args.get("background") and phase != "pending":
        return (tr("Iniciando en segundo plano") if phase == "run" else tr("Inició en segundo plano")), _q(args.get("command", "")) + ("…" if phase == "run" else "")
    inf, past, obj = STEP.get(name, (name, name, lambda a: ""))
    try:
        o = obj(args)
    except Exception:
        o = ""
    if phase == "pending":
        return tr("Quiere %s") % inf, o
    if phase == "run":
        lead = GERUND.get(name, inf[:1].upper() + inf[1:])
        return (lead, o + "…") if o else (lead + "…", "")
    return past, o


def describe(name, args, phase):
    lead, o = describe_parts(name, args, phase)
    return ("%s %s" % (lead, o)).strip()


def diff_badge(name, a):
    if name == "write_file":
        return "+%d" % (str(a.get("content", "")).count("\n") + 1), ""
    if name == "edit_file":
        return "+%d" % (str(a.get("new", "")).count("\n") + 1), "−%d" % (str(a.get("old", "")).count("\n") + 1)
    if name == "multi_edit":
        e = [x for x in (a.get("edits") or []) if isinstance(x, dict)]
        return "+%d" % sum(str(x.get("new", "")).count("\n") + 1 for x in e), "−%d" % sum(str(x.get("old", "")).count("\n") + 1 for x in e)
    return "", ""


# ---------------------------------------------------------------- pasos del agente
class StepRow(QWidget):
    """Una accion del agente en una linea, sin caja: icono de lo que hace (con un arco que gira mientras se ejecuta),
    «Escribiendo calculadora.py…» con un brillo que lo recorre y, al terminar, «Escribió calculadora.py». Se despliega
    para ver detalles y muestra la aprobacion en linea."""

    def __init__(self, ev, on_decide):
        super().__init__()
        self.ev = ev
        self.id = ev["id"]
        self.pending = ev["approval"] == "pending"
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head = Clickable()
        head.setObjectName("stepHead")
        head.setAttribute(Qt.WA_StyledBackground, True)
        head.setAttribute(Qt.WA_Hover, True)
        head.setCursor(Qt.PointingHandCursor)
        self.head = head
        h = QHBoxLayout(head)
        h.setContentsMargins(0, 1, 6, 1)
        h.setSpacing(6)
        self.st_icon = CV.ActivityIcon(CV.tool_icon(ev["name"]), C["mut"], 14)
        h.addWidget(self.st_icon)
        self.title = CV.Shimmer()             # una linea; si no cabe termina en «…» (completa en el tooltip)
        h.addWidget(self.title, 1)
        add, rem = diff_badge(ev["name"], ev.get("args") or {})
        for txt, col in ((add, C["ok"]), (rem, C["bad"])):
            if txt:
                l = QLabel(txt)
                l.setStyleSheet("color:%s; font-size:9pt" % col)
                h.addWidget(l)
        if ev.get("danger"):
            h.addWidget(pix_label("est_aviso", C["warn"], 14))
        # etiqueta discreta en español (categoria), no el nombre interno de la herramienta
        tn = QLabel("MCP" if ev["name"].startswith("mcp__") else T.CATEGORIES.get(ev.get("category"), "") or T.TOOL_LABELS.get(ev["name"], ""))
        tn.setObjectName("faint")
        tn.setToolTip(T.TOOL_LABELS.get(ev["name"], ev["name"]))
        h.addWidget(tn)
        self.box = None
        self.phase = "run"
        self.b_undo = tbtn("acc_refrescar", tr("Deshacer este cambio (restaura los archivos)"), size=13)
        self.b_undo.hide()
        h.addWidget(self.b_undo)
        self.chev = QLabel()
        h.addWidget(self.chev)
        head.clicked.connect(self.toggle)
        v.addWidget(head)
        self.details = QWidget()
        self.dl = QVBoxLayout(self.details)
        self.dl.setContentsMargins(30, 2, 6, 8)
        self.dl.setSpacing(6)
        self._args(ev["name"], ev.get("args") or {})
        self.details.hide()
        v.addWidget(self.details)
        self.approval = None
        if self.pending:
            self.approval = QFrame()
            self.approval.setObjectName("approval")
            av = QVBoxLayout(self.approval)
            av.setContentsMargins(12, 10, 12, 10)
            if ev.get("danger"):
                av.addWidget(TextView(tr("Acción delicada: revisa bien el detalle antes de permitirla."), "plain", color=C["warn"], size="9pt"))
            bw = QWidget()
            row = FlowLayout(bw)
            cat = T.CATEGORIES.get(ev["category"], ev["category"])
            for text, kind, dec in ((tr("Permitir"), "primary", "allow"), (tr("Siempre «%s» aquí") % cat.lower(), None, "allow_category"),
                                    (tr("Denegar"), "danger", "deny")):
                b = btn(text, kind)
                b.clicked.connect(lambda _=False, d=dec: self._decide(d, on_decide))
                row.addWidget(b)
            av.addWidget(bw)
            wrap = QWidget()
            wl = QVBoxLayout(wrap)
            wl.setContentsMargins(30, 2, 6, 8)
            wl.addWidget(self.approval)
            v.addWidget(wrap)
            self.approval_wrap = wrap
            self.details.show()
            self._set("pending")
        elif ev["approval"] == "blocked":
            self._set("blocked")
        else:
            self._set("run")

    def _args(self, name, a):
        kv = lambda k, val: TextView("<span style='color:%s'>%s:</span> %s" % (C["faint"], k, str(val).replace("&", "&amp;").replace("<", "&lt;")), "html")
        if name == "run_command":
            self.dl.addWidget(mono(a.get("command", "")))
            if a.get("cwd"):
                self.dl.addWidget(kv(tr("carpeta"), a["cwd"]))
        elif name == "write_file":
            self.dl.addWidget(kv(tr("archivo"), a.get("path", "")))
            self.dl.addWidget(mono(str(a.get("content", ""))[:20000], "add", 300))
        elif name == "edit_file":
            self.dl.addWidget(kv(tr("archivo"), a.get("path", "")))
            self.dl.addWidget(mono(str(a.get("old", "")), "del", 160))
            self.dl.addWidget(mono(str(a.get("new", "")), "add", 160))
        else:
            for k, val in a.items():
                if k == "_raw":
                    self.dl.addWidget(mono(str(val)))
                elif isinstance(val, str) and ("\n" in val or len(val) > 160):
                    # codigo o texto largo (p. ej. el Python que se envia a Blender): en bloque monoespaciado plegable
                    self.dl.addWidget(kv(k, ""))
                    self.dl.addWidget(mono(val[:20000], None, 220))
                else:
                    self.dl.addWidget(kv(k, val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)))

    def _set(self, phase):
        self.phase = phase
        tool = CV.tool_icon(self.ev["name"])
        ico, col = {"pending": ("est_aviso", C["acc"]), "run": (tool, C["acc"]), "ok": (tool, C["mut"]),
                    "err": ("est_error", C["bad"]), "denied": ("est_bloqueado", C["bad"]), "blocked": ("est_bloqueado", C["faint"])}[phase]
        self.st_icon.set_icon(ico, col)
        live = phase == "run" and self.ev.get("ts", 0) > time.time() - 30
        self.st_icon.set_active(live)             # el arco gira mientras se ejecuta
        lead, obj = describe_parts(self.ev["name"], self.ev.get("args"), {"pending": "pending", "run": "run"}.get(phase, "done"))
        if phase == "denied":
            lead = describe_parts(self.ev["name"], self.ev.get("args"), "pending")[0].replace(tr("Quiere"), tr("No se permitió"), 1)
        if phase == "blocked":
            obj = (tr("%s (bloqueado: solo lectura)") % obj).strip()
        text = ("%s %s" % (lead, obj)).strip()
        self.title.setText(text, len(lead) + 1 if obj else -1)
        self.title.set_active(live)
        self.title.set_color(C["bad"] if phase == "err" else C["mut"], C["tx"])
        self.head.setToolTip(text)
        self._chev()

    def _chev(self):
        self.chev.setPixmap(pix("ui_chevron_abajo" if self.details.isVisible() else "ui_chevron_derecha", C["faint"], 10))

    def toggle(self):
        self.details.setVisible(not self.details.isVisible())
        self._chev()

    def _decide(self, d, cb):
        for b in self.approval.findChildren(QPushButton):
            b.setEnabled(False)
        cb(self.id, d)

    def resolved(self, decision):
        self.pending = False
        if self.approval:
            self.approval_wrap.hide()
        self.details.hide()
        self._set("run" if decision in ("allow", "allow_category") else "denied")

    def result(self, ok, text, image):
        self._set("ok" if ok else "err")
        if ok and text and self.ev["name"] in ("browser_click", "click_element"):     # «Pulsó el elemento 7» -> «Pulsó «Iniciar sesión»»
            m = re.search(r"«([^»\n]{1,60})»", text.split("\n", 1)[0])
            if m:
                t = tr("Pulsó «%s»") % m.group(1)
                self.title.setText(t, len(tr("Pulsó")) + 1)
                self.head.setToolTip(t)
        if text:
            self.dl.addWidget(mono(text, max_h=300))
        if image:                             # la imagen queda a la vista bajo las acciones (también con el resumen plegado)
            p = os.path.join(paths.IMG_DIR, image)
            if self.box is not None:
                self.box.add_preview(p)
            else:
                self.dl.addWidget(ImageLabel(p))
                self.details.show()
        if not ok:
            self.details.show()
        if ok and self.ev["name"] == "create_document" and self.box is not None:
            m = re.search(r"documento \w+ (.+?\.(?:docx|xlsx|pptx|pdf)) \(", text or "", re.I)
            if m:
                self.doc_card = self.box.add_doc(m.group(1))
        self._chev()

    def undone(self):
        self.b_undo.hide()
        self.is_undone = True
        card = getattr(self, "doc_card", None)
        if card is not None and not os.path.isfile(card.path):      # el documento ya no existe: fuera su tarjeta
            card.hide()
            if self.box is not None:
                self.box.extras.setVisible(any(not self.box.ev_.itemAt(i).widget().isHidden() for i in range(self.box.ev_.count())))
        self.title.setText(tr("%s  · deshecho") % self.title.text())
        self.title.set_color(C["faint"], C["faint"])
        self.title.set_strike(True)


# Resumen de varias acciones seguidas en una frase («Editó 2 archivos, buscó en los archivos y ejecutó un comando»)
GROUP = {
    "read_file": (tr("leyó un archivo"), tr("leyó %d archivos")), "write_file": (tr("creó un archivo"), tr("creó %d archivos")),
    "edit_file": (tr("editó un archivo"), tr("editó %d archivos")), "list_dir": (tr("exploró una carpeta"), tr("exploró %d carpetas")),
    "search_files": (tr("buscó en los archivos"), tr("hizo %d búsquedas")), "run_command": (tr("ejecutó un comando"), tr("ejecutó %d comandos")),
    "command_output": (tr("revisó un proceso"), tr("revisó %d procesos")), "stop_command": (tr("detuvo un proceso"), tr("detuvo %d procesos")),
    "web_search": (tr("buscó en internet"), tr("hizo %d búsquedas en internet")), "web_fetch": (tr("leyó una página web"), tr("leyó %d páginas web")),
    "download_file": (tr("descargó un archivo"), tr("descargó %d archivos")), "read_document": (tr("leyó un documento"), tr("leyó %d documentos")),
    "create_document": (tr("creó un documento"), tr("creó %d documentos")), "view_image": (tr("vio una imagen"), tr("vio %d imágenes")),
    "screenshot": (tr("hizo una captura de pantalla"), tr("hizo %d capturas de pantalla")), "move_path": (tr("movió un archivo"), tr("movió %d archivos")),
    "delete_path": (tr("envió un archivo a la papelera"), tr("envió %d archivos a la papelera")), "remember": (tr("guardó una preferencia"), tr("guardó %d preferencias")),
    "control": (tr("usó el ratón y el teclado"), tr("usó el ratón y el teclado")), "open_target": (tr("abrió un programa o archivo"), tr("abrió %d programas o archivos")),
    "wait": (tr("esperó un momento"), tr("esperó %d veces")),
    "browser_open": (tr("abrió una página"), tr("abrió %d páginas")), "browser_read": (tr("leyó la página"), tr("leyó %d veces la página")),
    "browser_click": (tr("pulsó en la página"), tr("pulsó %d veces en la página")), "browser_type": (tr("escribió en la página"), tr("rellenó %d campos")),
    "browser_nav": (tr("navegó por la página"), tr("navegó %d veces")), "browser_screenshot": (tr("capturó la página"), tr("capturó %d veces la página")),
    "run_python": (tr("analizó los datos con Python"), tr("hizo %d análisis con Python")), "show_canvas": (tr("mostró algo en el lienzo"), tr("actualizó el lienzo %d veces")),
}
_GROUP_ALIAS = {"multi_edit": "edit_file", "click": "control", "move_mouse": "control", "scroll": "control", "type_text": "control",
                "press_keys": "control", "list_windows": "control", "focus_window": "control", "ui_elements": "control",
                "click_element": "control", "drag": "control", "window_action": "control", "clipboard": "control"}


def summarize_steps(rows):
    order, seen = [], {}
    for r in rows:
        name, a = r.ev["name"], r.ev.get("args") or {}
        if name.startswith("mcp__"):
            key = ("mcp", name.split("__")[1].replace("_", " ") if name.count("__") >= 2 else "")
        else:
            key = _GROUP_ALIAS.get(name, name)
        if key not in seen:
            seen[key] = set()
            order.append(key)
        # leer o editar el mismo archivo varias veces cuenta como uno
        seen[key].add(str(a.get("path") or a.get("url") or a.get("command") or r.id) if key in ("read_file", "edit_file", "write_file", "read_document") else r.id)
    parts = []
    for key in order:
        n = len(seen[key])
        if isinstance(key, tuple):
            srv = key[1] or tr("un conector")
            parts.append((tr("usó %s") % srv) if n == 1 else (tr("usó %s (%d veces)") % (srv, n)))
        elif key in GROUP:
            one, many = GROUP[key]
            parts.append(one if n == 1 else (many % n if "%d" in many else many))
        else:
            parts.append((tr("hizo %d acción más") if n == 1 else tr("hizo %d acciones más")) % n)
    if not parts:
        return ""
    text = parts[0] if len(parts) == 1 else tr("%s y %s") % (", ".join(parts[:-1]), parts[-1])
    return text[:1].upper() + text[1:]


DOC_KIND = {".docx": ("W", "2B579A", tr("Documento de Word")), ".xlsx": ("X", "217346", tr("Hoja de Excel")),
            ".pptx": ("P", "C43E1C", tr("Presentación de PowerPoint")), ".pdf": ("PDF", "B3261E", tr("Documento PDF"))}


class DocCard(QFrame):
    """Tarjeta de un documento creado por el agente: tipo, nombre, tamaño y botones para abrirlo."""

    def __init__(self, path):
        super().__init__()
        self.setObjectName("docCard")
        self.path = path
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 8, 8, 8)
        h.setSpacing(10)
        tag, col, kind = DOC_KIND.get(os.path.splitext(path)[1].lower(), ("DOC", "607068", tr("Documento")))
        badge = QLabel(tag)
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(38, 46)
        badge.setStyleSheet("background:#%s; color:white; border-radius:6px; font-weight:700; font-size:%s" % (col, "10pt" if len(tag) > 1 else "15pt"))
        h.addWidget(badge)
        info = QVBoxLayout()
        info.setSpacing(1)
        name = ElidedLabel(os.path.basename(path))
        name.setStyleSheet("font-weight:600")
        info.addWidget(name)
        try:
            size = T._human(os.path.getsize(path))
        except OSError:
            size = ""
        sub = ElidedLabel("%s · %s" % (kind, size) if size else kind)
        sub.setObjectName("faint")
        info.addWidget(sub)
        h.addLayout(info, 1)
        h.addWidget(btn(tr("Abrir"), "primary", lambda: os.path.isfile(self.path) and osys.open_path(self.path)))
        h.addWidget(tbtn("act_carpeta_abierta", tr("Mostrar en la carpeta"), lambda: reveal(self.path), size=15))
        self.setToolTip(path)


class CanvasCard(QFrame):
    """Tarjeta de algo que el agente puso en el lienzo; un clic lo vuelve a abrir."""

    def __init__(self, item, on_open):
        super().__init__()
        self.setObjectName("docCard")
        self.setCursor(Qt.PointingHandCursor)
        self.item, self.on_open = item, on_open
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 8, 8, 8)
        h.setSpacing(10)
        tag = {"html": "</>", "markdown": "¶", "svg": "◇", "code": "{ }"}.get(item.get("kind"), "▣")
        badge = QLabel(tag)
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(38, 46)
        badge.setStyleSheet("background:%s; color:%s; border-radius:6px; font-weight:700; font-size:11pt" % (C["acc_bg"], C["acc"]))
        h.addWidget(badge)
        info = QVBoxLayout()
        info.setSpacing(1)
        name = ElidedLabel(item.get("title", ""))
        name.setStyleSheet("font-weight:600")
        info.addWidget(name)
        kind = {"html": tr("Página web"), "markdown": tr("Documento"), "svg": tr("Dibujo"), "code": tr("Código")}.get(item.get("kind"), tr("Lienzo"))
        sub = ElidedLabel(tr("%s · versión %s") % (kind, item.get("version", 1)))
        sub.setObjectName("faint")
        info.addWidget(sub)
        h.addLayout(info, 1)
        h.addWidget(btn(tr("Ver en el lienzo"), "primary", lambda: self.on_open(self.item)))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.on_open(self.item)


def rounded(pm, r=8):
    """Miniatura con las esquinas redondeadas y un borde fino (como una tarjeta)."""
    from PySide6.QtGui import QPainter, QPainterPath, QColor, QPen
    out = QPixmap(pm.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0.5, 0.5, pm.width() - 1, pm.height() - 1, r, r)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pm)
    p.setClipping(False)
    p.setPen(QPen(QColor(C["line"]), 1))
    p.drawPath(path)
    p.end()
    return out


class Preview(QLabel):
    """Miniatura de una imagen que el agente ha visto o creado (una captura de lo que está probando, un gráfico…);
    un clic la abre en grande."""

    def __init__(self, path, max_w=520, max_h=300):
        super().__init__()
        self.path = path
        pm = QPixmap(path)
        if not pm.isNull():
            self.setPixmap(rounded(pm.scaled(min(max_w, pm.width()), min(max_h, pm.height()), Qt.KeepAspectRatio, Qt.SmoothTransformation)))
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tr("Clic para verla en grande"))
        self.setObjectName("thumb")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and os.path.isfile(self.path):
            osys.open_path(self.path)


def reveal(path):
    """Muestra el archivo seleccionado en el Explorador / Finder (o abre su carpeta)."""
    osys.reveal(path)


class StepsBox(QFrame):
    """Acciones seguidas del agente, como líneas del mensaje (sin caja alrededor). Mientras trabaja se ven una a una;
    al terminar, si son varias, se resumen en una línea («Editó 2 archivos y ejecutó un comando  +12 −3 ›») que se
    despliega con un clic. Las imágenes que ve y los documentos que crea quedan siempre a la vista debajo."""

    def __init__(self):
        super().__init__()
        self.setObjectName("stepsBox")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.v.setSpacing(0)
        self.rows = []
        self.closed = False
        self.head = Clickable()
        self.head.setObjectName("stepHead")
        self.head.setAttribute(Qt.WA_StyledBackground, True)
        self.head.setAttribute(Qt.WA_Hover, True)
        self.head.setCursor(Qt.PointingHandCursor)
        hh = QHBoxLayout(self.head)
        hh.setContentsMargins(0, 1, 6, 1)
        hh.setSpacing(6)
        self.h_icons = QWidget()                   # iconos de los tipos de acción (hasta tres, superpuestos)
        self.h_icons.setFixedSize(24, 24)
        self.h_icon = QLabel(self.h_icons)
        self.h_icon.setGeometry(0, 0, 24, 24)
        hh.addWidget(self.h_icons)
        self.h_text = ElidedLabel()
        self.h_text.setStyleSheet("color:%s" % C["mut"])
        hh.addWidget(self.h_text, 1)
        self.h_add, self.h_rem, self.h_fail = QLabel(), QLabel(), QLabel()
        for l, col in ((self.h_add, C["ok"]), (self.h_rem, C["bad"]), (self.h_fail, C["bad"])):
            l.setStyleSheet("color:%s; font-size:9pt" % col)
            hh.addWidget(l)
        self.h_chev = QLabel()
        hh.addWidget(self.h_chev)
        self.head.clicked.connect(self.toggle)
        self.head.hide()
        self.v.addWidget(self.head)
        self.body = QWidget()
        self.bv = QVBoxLayout(self.body)
        self.bv.setContentsMargins(0, 0, 0, 0)
        self.bv.setSpacing(2)
        self.v.addWidget(self.body)
        self.extras = QWidget()
        self.ev_ = QVBoxLayout(self.extras)
        self.ev_.setContentsMargins(30, 4, 6, 4)
        self.ev_.setSpacing(6)
        self.extras.hide()
        self.v.addWidget(self.extras)

    def add(self, row):
        self.rows.append(row)
        self.bv.addWidget(row)
        if len(self.rows) > 1 and row.ev.get("ts", 0) > time.time() - 3:
            fade_in(row)                       # la primera aparece con la caja entera (sin efectos anidados)
        if self.closed:                      # llegó otra acción a una caja ya resumida: se vuelve a ver entera
            self.closed = False
            self.body.show()
            self.head.hide()
        self.refresh()

    def refresh(self):
        self.setProperty("pending", any(r.pending for r in self.rows))
        restyle(self)

    def add_preview(self, path):
        if path and os.path.isfile(path):
            self.ev_.addWidget(Preview(path, 300, 180), 0, Qt.AlignLeft)     # miniatura: se ve cómo va quedando
            self.images = getattr(self, "images", []) + [path]
            self.extras.show()

    def add_canvas(self, item, on_open):
        self.ev_.addWidget(CanvasCard(item, on_open))
        self.extras.show()

    def add_doc(self, path):
        if path and os.path.isfile(path):
            card = DocCard(path)
            self.ev_.addWidget(card)
            self.extras.show()
            return card
        return None

    def finish(self):
        """El agente pasó a otra cosa: varias acciones terminadas se resumen en una línea."""
        if self.closed or len(self.rows) < 2 or any(r.pending or r.phase == "run" for r in self.rows):
            return
        self.closed = True
        add = rem = 0
        for r in self.rows:
            if r.phase == "ok" and not getattr(r, "is_undone", False):
                a, d = diff_badge(r.ev["name"], r.ev.get("args") or {})
                add += int(a[1:] or 0)
                rem += int(d[1:] or 0)
        fails = sum(1 for r in self.rows if r.phase in ("err", "denied"))
        self.h_text.setText(summarize_steps(self.rows))
        self.h_text.setToolTip("\n".join(r.title.text() for r in self.rows))
        self.h_add.setText("+%d" % add if add else "")
        self.h_rem.setText("−%d" % rem if rem else "")
        self.h_fail.setText((tr("%d ha fallado") if fails == 1 else tr("%d han fallado")) % fails if fails else "")
        self.h_icon.setPixmap(self._icon_stack(fails))
        self.head.show()
        self.body.hide()
        self._chev()

    def _icon_stack(self, fails):
        """Iconos de los distintos tipos de acción, un poco superpuestos (o el aviso si alguna falló)."""
        from PySide6.QtGui import QPainter, QColor
        names = []
        for r in self.rows:
            n = CV.tool_icon(r.ev["name"])
            if n not in names:
                names.append(n)
        names = ["est_aviso"] if fails else names[:3]
        dpr = self.devicePixelRatioF() or 1.0
        out = QPixmap(int(24 * dpr), int(24 * dpr))
        out.setDevicePixelRatio(dpr)
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(names)
        size = 14 if n == 1 else 11
        offs = [(5, 5)] if n == 1 else [(1, 2), (11, 11)] if n == 2 else [(1, 1), (12, 3), (6, 12)]
        for name, (x, y) in zip(names, offs):
            if n > 1:                              # un círculo del color del fondo separa los iconos superpuestos
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(C["bg"]))
                p.drawEllipse(x - 1, y - 1, size + 2, size + 2)
            p.drawPixmap(x, y, pix(name, C["warn"] if fails else C["mut"], size))
        p.end()
        return out

    def _chev(self):
        self.h_chev.setPixmap(pix("ui_chevron_abajo" if self.body.isVisible() else "ui_chevron_derecha", C["faint"], 10))

    def toggle(self):
        self.body.setVisible(not self.body.isVisible())
        self._chev()


# ---------------------------------------------------------------- mensajes
class AssistantBlock(QWidget):
    """Un paso del modelo. Arriba, una línea animada con lo que está haciendo («Leyendo tu mensaje…», «Revisando la
    salida…», «Pensando… 12 s»); si razonó, queda «Pensó durante 12 s ›» y un clic despliega el pensamiento. Debajo, su
    texto (con código, comandos y rutas interactivos) y, en la respuesta final, los botones."""

    def __init__(self, started, step=1, after=None):
        super().__init__()
        self.started = started
        # primer paso: el modelo lee el mensaje; despues, lo que devolvieron las herramientas (frases segun la ultima)
        self.kind = CV.activity_kind(after) if (step or 1) > 1 else "start"
        self.r_start = self.r_end = None
        self.reasoning = ""
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        self.act = CV.ActivityLine()
        self.act.run(CV.WAIT.get(self.kind, CV.WAIT["other"]), started, CV.WAIT_ICON.get(self.kind, "ia_controlador"),
                     live=started > time.time() - 5)
        self.act.clicked.connect(self.toggle_think)
        self.status = self.act                     # (nombre anterior: la línea de espera)
        v.addWidget(self.act)
        self.peek = ElidedLabel()                  # mientras piensa: la última frase de su pensamiento, tenue
        self.peek.setObjectName("thinkPeek")
        self.peek.hide()
        v.addWidget(self.peek)
        self.think_view = CV.ThinkView()
        self.think_fold = Collapsible(self.think_view, limit=280, fade=C["bg"], slack=80)
        self.think_fold.hide()
        v.addWidget(self.think_fold)
        self.body = md_label()
        self.body.hide()
        v.addWidget(self.body)
        self.actions = QWidget()
        ah = QHBoxLayout(self.actions)
        ah.setContentsMargins(0, 0, 0, 0)
        ah.setSpacing(2)
        self.b_copy = tbtn("acc_copiar", tr("Copiar respuesta"), self.copy, size=15)
        self.b_regen = tbtn("acc_refrescar", tr("Regenerar respuesta"), size=15)
        self.b_report = tbtn("est_aviso", tr("Informar de un problema con esta respuesta"), self.report, size=15)
        self.b_undo_all = QPushButton(tr("Deshacer cambios"))
        self.b_undo_all.setProperty("kind", "flat")
        self.b_undo_all.setIcon(icon("acc_refrescar", C["mut"], 13))
        self.b_undo_all.setToolTip(tr("Restaura todos los archivos que el agente cambió en esta respuesta"))
        self.b_undo_all.hide()
        self.b_speak = tbtn("voz_altavoz", tr("Leer en voz alta"), self.speak, size=15)
        self.b_speak.setVisible(speaker_available())
        ah.addWidget(self.b_copy)
        ah.addWidget(self.b_speak)
        ah.addWidget(self.b_regen)
        ah.addWidget(self.b_report)
        ah.addWidget(self.b_undo_all)
        ah.addStretch(1)
        self.stats = FitLabel()              # una sola linea: si no cabe, una version mas corta
        self.stats.setObjectName("stats")
        self.stats.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        ah.addWidget(self.stats, 1)
        self.actions.hide()
        v.addWidget(self.actions)
        self.text = ""

    def tick(self, now):
        if self.act.live:
            self.act.tick(now)

    def delta(self, kind, text, ts):
        if kind == "reasoning":
            if self.r_start is None:
                self.r_start = ts
                live = ts > time.time() - 5
                self.act.show()
                self.act.run(CV.think_phrases(self.kind), ts, "ia_controlador", live=live)
                self.act.set_expandable(True)
            self.reasoning += text
            if self.think_fold.isVisible():
                self.think_view.append(text)
            elif self.act.live:
                self._peek()
        else:
            self._end_think(ts)
            if self.r_start is None:
                self.act.hide()                     # empezó a escribir sin pensar: fuera la línea de espera
            self.text += text
            self.body.show()
            # el Markdown se vuelve a dibujar como mucho cada 90 ms: con modelos rapidos llegan decenas de trozos por segundo
            if not getattr(self, "_render_t", None):
                self._render_t = QTimer(self, singleShot=True, interval=90, timeout=lambda: self.body.setText(self.text))
            if not self._render_t.isActive():
                self._render_t.start()

    def _peek(self):
        """La última frase que está pensando, en una línea tenue (para ver que avanza sin desplegar nada)."""
        tail = self.reasoning[-400:].replace("\r", "")
        lines = [l.strip() for l in tail.split("\n") if l.strip()]
        last = lines[-1] if lines else ""
        if len(last) > 160:
            last = "…" + last[-159:]
        self.peek.setText(last)
        self.peek.setVisible(bool(last))

    def toggle_think(self):
        on = not self.think_fold.isVisible()
        if on:
            self.think_view.setText(self.reasoning)
        self.think_fold.setVisible(on)
        self.act.set_open(on)
        self.peek.setVisible(False if on else (self.act.live and bool(self.peek.text())))

    def _end_think(self, ts):
        if self.r_start and not self.r_end:
            self.r_end = ts
            self.act.done(CV.thought_for(self.r_end - self.r_start))
            self.peek.hide()

    def finish(self, text, ts):
        self._end_think(ts)
        if self.r_start is None:
            self.act.done("")
            self.act.hide()
        if getattr(self, "_render_t", None):
            self._render_t.stop()
        if not text and self.text:
            self.body.setText(self.text)            # ultimo trozo pendiente de dibujar
        if text:
            self.text = text
            self.body.setText(text)
            self.body.show()

    def empty(self):
        return not self.text and self.r_start is None

    def add_gallery(self, paths_):
        """Debajo de la respuesta final: miniaturas de lo que el agente capturó o generó en esta respuesta (cómo quedó)."""
        paths_ = [p for p in paths_ if os.path.isfile(p)]
        if not paths_ or getattr(self, "gallery", None) is not None:
            return
        self.gallery = QWidget()
        fl = FlowLayout(self.gallery, spacing=8)
        for p in paths_:
            fl.addWidget(Preview(p, 340 if len(paths_) == 1 else 220, 210 if len(paths_) == 1 else 140))
        lay = self.layout()
        lay.insertWidget(lay.indexOf(self.actions), self.gallery)

    def copy(self):
        QGuiApplication.clipboard().setText(self.text)
        self.b_copy.setIcon(icon("ui_check", C["ok"], 15))
        QTimer.singleShot(1200, lambda: self.b_copy.setIcon(icon("acc_copiar", C["mut"], 15)))

    def speak(self):
        """Lee esta respuesta en voz alta; si ya se está leyendo, la detiene."""
        global _SPEAKING
        sp = speaker()
        if _SPEAKING is self and sp.speaking():
            sp.stop()
            _SPEAKING = None
            self.b_speak.setIcon(icon("voz_altavoz", C["mut"], 15))
            self.b_speak.setToolTip(tr("Leer en voz alta"))
            return
        if _SPEAKING is not None:
            try:
                _SPEAKING.b_speak.setIcon(icon("voz_altavoz", C["mut"], 15))
            except RuntimeError:
                pass
        if sp.speak(self.text, core.SET.snapshot().get("voice_rate", 0.0)):
            _SPEAKING = self
            self.b_speak.setIcon(icon("trans_detener", C["acc"], 13))
            self.b_speak.setToolTip(tr("Detener la lectura"))
            me = self

            def watch():                       # cuando termina de leer, el botón vuelve a su estado
                global _SPEAKING
                if _SPEAKING is not me:
                    return
                if sp.speaking():
                    return QTimer.singleShot(400, watch)
                _SPEAKING = None
                try:
                    me.b_speak.setIcon(icon("voz_altavoz", C["mut"], 15))
                    me.b_speak.setToolTip(tr("Leer en voz alta"))
                except RuntimeError:
                    pass
            QTimer.singleShot(900, watch)

    def report(self):
        excerpt = self.text if len(self.text) < 1500 else self.text[:1500] + "…"
        FeedbackDialog(self.window(), "error", tr("Respuesta con problemas:\n\n> %s\n\nQué esperaba: ") % excerpt.replace("\n", "\n> ")).exec()


def user_bubble(ev, compact=False):
    wrap = QWidget()
    h = QHBoxLayout(wrap)
    h.setContentsMargins(0, 6, 0, 2)
    h.addStretch(1)
    box = QFrame()
    box.setObjectName("userBubble")
    box.setMaximumWidth(380 if compact else 560)
    v = QVBoxLayout(box)
    v.setContentsMargins(14, 9, 14, 9)
    for n in ev.get("images") or []:
        v.addWidget(ImageLabel(os.path.join(paths.IMG_DIR, n), 240, 160))
    for fname in ev.get("files") or []:
        fl = QHBoxLayout()
        fl.addWidget(pix_label("acc_nuevo", C["acc"], 14), 0, Qt.AlignTop)
        fv = TextView(fname, "plain", color=C["mut"])
        fv.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        fl.addWidget(fv, 1)
        v.addLayout(fl)
    t = TextView(ev["text"], "plain", size="10.5pt")
    t.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)     # la burbuja se ajusta al texto y se parte si no cabe
    # un mensaje muy largo se muestra plegado: difuminado abajo y flecha para desplegarlo
    fold = Collapsible(t, limit=200, fade=C["panel2"], slack=50)
    fold.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    v.addWidget(fold)
    box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)   # tan ancha como su texto; si no cabe, se estrecha
    h.addWidget(box)
    return wrap


class PlanPanel(QFrame):
    """Lista de tareas que mantiene el agente (update_plan), fija sobre el cuadro de mensaje."""

    def __init__(self):
        super().__init__()
        self.setObjectName("planBox")
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(4)
        head = Clickable()
        head.setCursor(Qt.PointingHandCursor)
        hh = QHBoxLayout(head)
        hh.setContentsMargins(0, 0, 0, 0)
        hh.addWidget(pix_label("ui_check", C["acc"], 14))
        self.title = QLabel()
        self.title.setStyleSheet("font-weight:600")
        hh.addWidget(self.title, 1)
        self.chev = QLabel("⌄")
        self.chev.setStyleSheet("color:%s" % C["faint"])
        hh.addWidget(self.chev)
        head.clicked.connect(self.toggle)
        v.addWidget(head)
        self.body = QWidget()
        self.bl = QVBoxLayout(self.body)
        self.bl.setContentsMargins(22, 2, 0, 2)
        self.bl.setSpacing(3)
        v.addWidget(self.body)
        self.hide()

    def toggle(self):
        self.body.setVisible(not self.body.isVisible())
        self.chev.setText("⌄" if self.body.isVisible() else "›")

    def set_items(self, items, live=True):
        while self.bl.count():
            it = self.bl.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not items:
            return self.hide()
        done = sum(1 for i in items if i.get("status") == "completed")
        self.title.setText(tr("Plan · %d de %d") % (done, len(items)))
        for i in items:
            st = i.get("status", "pending")
            row = QWidget()
            r = QHBoxLayout(row)
            r.setContentsMargins(0, 0, 0, 0)
            if st == "in_progress":
                sp = Spinner(size=12)
                if live:
                    sp.start()
                r.addWidget(sp)
            else:
                r.addWidget(pix_label("ui_check", C["ok"], 12) if st == "completed" else QLabel("○"))
            esc = str(i.get("content", "")).replace("&", "&amp;").replace("<", "&lt;")
            style = "text-decoration: line-through;" if st == "completed" else "font-weight:600;" if st == "in_progress" else ""
            t = TextView("<span style='%s'>%s</span>" % (style, esc), "html", color=C["faint"] if st == "completed" else C["tx"])
            r.addWidget(t, 1)
            self.bl.addWidget(row)
        self.show()
        self.body.setVisible(done < len(items))
        self.chev.setText("⌄" if self.body.isVisible() else "›")


class QuestionCard(QFrame):
    """El agente pregunta (ask_user): opciones como botones y respuesta libre."""

    def __init__(self, ev, on_answer, live=True):
        super().__init__()
        self.setObjectName("stepsBox")
        self.setProperty("pending", live)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)
        hh = QHBoxLayout()
        hh.addWidget(pix_label("ui_ayuda", C["acc"], 16), 0, Qt.AlignTop)
        hh.addWidget(TextView(ev["question"], "plain", size="10.5pt", bold=True), 1)
        v.addLayout(hh)
        self.inputs = QWidget()
        il = QVBoxLayout(self.inputs)
        il.setContentsMargins(24, 0, 0, 0)
        il.setSpacing(6)
        for o in ev.get("options") or []:
            b = OptionRow(o)
            b.clicked.connect(lambda _=False, o=o: self._send(o, on_answer))
            il.addWidget(b)
        r2 = QHBoxLayout()
        self.free = QLineEdit()
        self.free.setPlaceholderText(tr("Otra respuesta…"))
        self.free.returnPressed.connect(lambda: self.free.text().strip() and self._send(self.free.text().strip(), on_answer))
        r2.addWidget(self.free, 1)
        r2.addWidget(btn(tr("Responder"), "primary", lambda: self.free.text().strip() and self._send(self.free.text().strip(), on_answer)))
        il.addLayout(r2)
        v.addWidget(self.inputs)
        self.answer_lbl = TextView("", "plain", color=C["mut"])
        self.answer_lbl.hide()
        v.addWidget(self.answer_lbl)
        self.inputs.setVisible(live)
        self.id = ev["id"]

    def _send(self, text, cb):
        self.inputs.setEnabled(False)
        cb(self.id, text)

    def answered(self, text):
        self.inputs.hide()
        self.setProperty("pending", False)
        restyle(self)
        self.answer_lbl.setText((tr("Tu respuesta: %s") % text) if text else tr("Sin respuesta"))
        self.answer_lbl.show()


CHAT_SUGGESTIONS = [("acc_examinar", tr("Ordena mi carpeta de Descargas por tipo de archivo")),
                    ("cod_terminal", tr("Crea un script de Python que renombre mis fotos por fecha")),
                    ("vista_captura", tr("Haz una captura de pantalla y dime qué ves")),
                    ("herr_espacio_mundo", tr("Busca en la web las novedades de llama.cpp y resúmelas"))]
CODE_SUGGESTIONS = [("acc_examinar", tr("Explícame la estructura de este proyecto")),
                    ("acc_nuevo", tr("Crea un README.md que describa este proyecto")),
                    ("acc_buscar", tr("Revisa el código, busca errores y propón arreglos")),
                    ("cod_terminal", tr("Crea una página web sencilla con HTML, CSS y JavaScript"))]


class EmptyState(QWidget):
    def __init__(self, title, subtitle, suggestions, on_pick, compact=False):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 30 if compact else 70, 0, 0)
        v.setSpacing(14 if compact else 18)
        logo = QLabel()
        logo.setPixmap(theme.logo(44 if compact else 60))
        logo.setAlignment(Qt.AlignCenter)
        v.addWidget(logo)
        g = QLabel(title)
        g.setObjectName("greeting")
        if compact:
            g.setStyleSheet("font-size:14pt")
        g.setAlignment(Qt.AlignCenter)
        g.setWordWrap(True)
        v.addWidget(g)
        s = QLabel(subtitle)
        s.setObjectName("muted")
        s.setAlignment(Qt.AlignCenter)
        s.setWordWrap(True)
        v.addWidget(s)
        grid = QGridLayout()
        grid.setSpacing(8)
        cols = 1 if compact else 2
        for i, (ico, text) in enumerate(suggestions):
            b = OptionRow(text, ico, name="suggestion")
            b.setMinimumHeight(42 if compact else 48)
            b.clicked.connect(lambda _=False, t=text: on_pick(t))
            grid.addWidget(b, i // cols, i % cols)
        for c in range(cols):
            grid.setColumnStretch(c, 1)
        v.addLayout(grid)


# ---------------------------------------------------------------- compositor
def local_files(mime):
    """Rutas locales de un arrastre o portapapeles (archivos del Explorador/Finder)."""
    if mime is None or not mime.hasUrls():
        return []
    return [os.path.normpath(u.toLocalFile()) for u in mime.urls() if u.isLocalFile() and u.toLocalFile()]


class ComposerEdit(QPlainTextEdit):
    submit = Signal()
    pasted_image = Signal(QImage)
    pasted_files = Signal(list)
    focus = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("composerEdit")
        self.setPlaceholderText(tr("Escribe un mensaje…"))
        self.textChanged.connect(self._grow)
        self._grow()

    def _grow(self):
        n = int(self.document().size().height())
        lines = max(1, min(9, n))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if n > 9 else Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(lines * self.fontMetrics().lineSpacing() + 14)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            self.submit.emit()
            return
        super().keyPressEvent(e)

    def insertFromMimeData(self, src):
        files = local_files(src)
        if files:                            # archivos copiados en el Explorador (Ctrl+V) o soltados aqui
            self.pasted_files.emit(files)
            return
        if src.hasImage():
            img = src.imageData()
            if isinstance(img, QImage) and not img.isNull():
                self.pasted_image.emit(img)
                return
        super().insertFromMimeData(src)

    def canInsertFromMimeData(self, src):
        return bool(local_files(src)) or src.hasImage() or super().canInsertFromMimeData(src)

    def focusInEvent(self, e):
        self.focus.emit(True)
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        self.focus.emit(False)
        super().focusOutEvent(e)


# ---------------------------------------------------------------- panel de conversacion (sirve a los dos modos)
class ChatPanel(QWidget):
    changed = Signal()            # cambia la conversacion o su estado (para refrescar listas y cabecera)
    file_written = Signal(str)    # el agente escribio/edito un archivo (ruta absoluta)

    def __init__(self, main, compact=False):
        super().__init__()
        self.main = main
        self.compact = compact
        self.setAcceptDrops(True)            # arrastrar archivos o imagenes sobre la conversacion los adjunta
        self.project_id = None
        self.sid = None
        self.ev_i = 0
        self.cur = None
        self.steps = None
        self.rows = {}
        self.blocks = []
        self.empty = None
        self.waiting = 0
        self.busy = False
        self.pending_imgs = []
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        holder.setObjectName("chatHolder")
        holder.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)   # la columna nunca es mas ancha que el panel
        self.scroll.viewport().setObjectName("chatHolder")
        hl = QHBoxLayout(holder)
        hl.setSizeConstraint(QLayout.SetNoConstraint)
        m = 14 if compact else 24
        hl.setContentsMargins(m, 12, m, 20)
        self.col = QWidget()
        if not compact:
            self.col.setMaximumWidth(780)
        self.cl = QVBoxLayout(self.col)
        self.cl.setContentsMargins(0, 0, 0, 0)
        self.cl.setSpacing(12)
        self.cl.addStretch(1)
        hl.addWidget(self.col, 1)
        self.scroll.setWidget(holder)
        self.stick = True
        sb = self.scroll.verticalScrollBar()
        sb.rangeChanged.connect(lambda lo, hi: self.stick and sb.setValue(hi))
        sb.valueChanged.connect(lambda val: setattr(self, "stick", val >= sb.maximum() - 60))
        v.addWidget(self.scroll, 1)
        v.addWidget(self._composer())
        self.pump_t = QTimer(self, interval=60, timeout=self.pump)
        self.pump_t.start()
        self.tick_t = QTimer(self, interval=1000, timeout=lambda: self.cur and self.cur.tick(time.time()))
        self.tick_t.start()

    # ---- compositor
    def _composer(self):
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        m = 14 if self.compact else 24
        v.setContentsMargins(m, 0, m, 10)
        inner = QWidget()
        self.composer_inner = inner
        if not self.compact:
            inner.setMaximumWidth(780)
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 0, 0)
        iv.setSpacing(6)
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(12, 6, 8, 6)
        bl.addWidget(pix_label("est_aviso", C["warn"], 15))
        self.ban_txt = QLabel()
        self.ban_txt.setWordWrap(True)
        bl.addWidget(self.ban_txt, 1)
        self.ban_btn = btn(tr("Encender modelo"), "primary", self.main.toggle_llm)
        bl.addWidget(self.ban_btn)
        iv.addWidget(self.banner)
        self.plan_panel = PlanPanel()
        iv.addWidget(self.plan_panel)
        self.box = QFrame()
        self.box.setObjectName("composerBox")
        bv = QVBoxLayout(self.box)
        bv.setContentsMargins(12, 10, 10, 8)
        bv.setSpacing(6)
        self.thumbs_w = QWidget()
        self.thumbs = FlowLayout(self.thumbs_w)
        self.thumbs_w.hide()
        bv.addWidget(self.thumbs_w)
        self.input = ComposerEdit()
        self.input.submit.connect(self.send)
        self.input.pasted_image.connect(lambda img: self._add_image(qimage=img))
        self.input.pasted_files.connect(self.add_paths)
        self.input.focus.connect(lambda f: (self.box.setProperty("focus", f), restyle(self.box)))
        self.input.textChanged.connect(self._sync_send)
        # franja de grabación: punto rojo, tiempo y onda que se mueve con la voz
        self.rec_bar = QFrame()
        self.rec_bar.setObjectName("recBar")
        rb = QHBoxLayout(self.rec_bar)
        rb.setContentsMargins(10, 4, 4, 4)
        rb.setSpacing(10)
        self.rec_dot = QLabel()
        self.rec_dot.setFixedSize(10, 10)
        rb.addWidget(self.rec_dot)
        self.rec_time = QLabel("0:00")
        self.rec_time.setObjectName("muted")
        self.rec_time.setMinimumWidth(36)
        rb.addWidget(self.rec_time)
        self.rec_wave = WaveBars()
        rb.addWidget(self.rec_wave, 1)
        self.rec_cancel = tbtn("ui_cerrar", tr("Descartar la grabación"), lambda: self.cancel_dictation(), size=12)
        rb.addWidget(self.rec_cancel)
        self.rec_bar.hide()
        bv.addWidget(self.rec_bar)
        bv.addWidget(self.input)
        row = QHBoxLayout()
        row.setSpacing(6)
        plus = tbtn("acc_anadir", tr("Adjuntar"), size=14, name="round")
        plus.setFixedSize(28, 28)
        plus.setPopupMode(QToolButton.InstantPopup)
        pm = QMenu(self)
        pm.addAction(icon("acc_nuevo"), tr("Adjuntar archivos o documentos…"), self.attach_files)
        pm.addAction(icon("uij_imagen"), tr("Adjuntar imagen…"), self.attach)
        pm.addAction(icon("vista_captura"), tr("Adjuntar captura de pantalla"), self.attach_screenshot)
        pm.addSeparator()
        self.assist_menu = pm.addMenu(icon("ia_controlador"), tr("Usar un asistente"))
        self.assist_menu.aboutToShow.connect(self._fill_assist_menu)
        plus.setMenu(pm)
        plus.setToolTip(tr("Adjuntar archivos, documentos, imágenes o una captura"))
        row.addWidget(plus)
        self.mode_chip = QToolButton()
        self.mode_chip.setObjectName("chip")
        self.mode_chip.setIcon(icon("est_bloqueado", C["mut"], 13))
        self.mode_chip.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.mode_chip.setPopupMode(QToolButton.InstantPopup)
        mm = QMenu(self)
        grp = QActionGroup(self)
        self.mode_actions = {}
        for k, desc in A.MODES.items():
            a = mm.addAction(MODE_LABEL[k])
            a.setCheckable(True)
            a.setToolTip(desc)
            grp.addAction(a)
            a.triggered.connect(lambda _=False, k=k: (core.SET.update({"mode": k}), self.main.sync()))
            self.mode_actions[k] = a
        mm.setToolTipsVisible(True)
        self.mode_chip.setMenu(mm)
        # modelo (con el esfuerzo dentro de su menu) junto al boton de enviar; los botones bajan de linea si no caben
        chips_w = QWidget()
        chips = FlowLayout(chips_w, spacing=6)
        chips.addWidget(plus)
        chips.addWidget(self.mode_chip)
        self.model_chip = QToolButton()
        self.model_chip.setObjectName("chip")
        self.model_chip.setIcon(icon("ia_controlador", C["mut"], 13))
        self.model_chip.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.model_chip.setPopupMode(QToolButton.InstantPopup)
        self.model_chip_menu = QMenu(self)
        self.model_chip_menu.setToolTipsVisible(True)
        self.model_chip_menu.aboutToShow.connect(lambda: self.main._fill_model_menu(self.model_chip_menu))
        self.model_chip.setMenu(self.model_chip_menu)
        chips.addWidget(self.model_chip)
        row.removeWidget(plus)
        row.addWidget(chips_w, 1)
        self.chips_w, self.plus_btn = chips_w, plus
        _rs = chips_w.resizeEvent
        chips_w.resizeEvent = lambda e: (_rs(e), self._fit_model_chip())
        self.mic_btn = QToolButton()                 # dictar con el micrófono
        self.mic_btn.setObjectName("round")
        self.mic_btn.setFixedSize(32, 32)
        self.mic_btn.setIcon(icon("voz_microfono", C["mut"], 16))
        self.mic_btn.setIconSize(QSize(16, 16))
        self.mic_btn.setCursor(Qt.PointingHandCursor)
        self.mic_btn.setToolTip(tr("Dictar con el micrófono"))
        self.mic_btn.setAccessibleName(tr("Dictar"))
        self.mic_btn.clicked.connect(lambda: self.toggle_dictation())
        row.addWidget(self.mic_btn, 0, Qt.AlignBottom)
        self._rec = None
        self.send_btn = QToolButton()
        self.send_btn.setObjectName("sendBtn")
        self.send_btn.setFixedSize(32, 32)
        self.send_btn.setIconSize(QSize(16, 16))
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(lambda: self.stop() if self.busy else self.send())
        row.addWidget(self.send_btn, 0, Qt.AlignBottom)
        bv.addLayout(row)
        iv.addWidget(self.box)
        if not self.compact:
            hint = QLabel(tr("Se ejecuta en tu equipo. Revisa cada acción antes de permitirla · ratón a la esquina superior izquierda = detener el control"))
            hint.setObjectName("faint")
            hint.setAlignment(Qt.AlignCenter)
            hint.setWordWrap(True)
            iv.addWidget(hint)
        # centrado y ocupando todo el ancho disponible hasta el maximo (antes la alineacion lo encogia)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(inner, 1000)
        row.addStretch(1)
        v.addLayout(row)
        return wrap

    # ---- conversacion
    def session(self):
        return core.SESSIONS.get(self.sid) if self.sid else None

    def workspace(self):
        cfg = core.SET.snapshot()
        p = core.project(cfg, self.project_id)
        return p["path"] if p else cfg["workspace"]

    # ---- botones de las respuestas (comandos y rutas)
    def _code_page(self):
        """La página del proyecto si este chat es el de su panel (allí hay editor y terminal)."""
        code = getattr(self.main, "code", None)
        return code if (code is not None and getattr(code, "chat", None) is self and code.project) else None

    def run_in_terminal(self, cmd):
        """Ejecuta un comando que sugirió el agente: en la terminal del proyecto si estamos en uno; si no, en una
        ventana de terminal del sistema abierta en la carpeta de trabajo."""
        cmd = (cmd or "").strip()
        if not cmd:
            return False
        if T.is_dangerous("run_command", {"command": cmd}, None):
            r = QMessageBox.question(self, APP_NAME, tr("Este comando puede borrar o cambiar cosas importantes de tu equipo:\n\n%s\n\n"
                                     "¿Ejecutarlo de todos modos?") % cmd[:800], QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                return False
        code = self._code_page()
        if code is not None:
            code.toggle_terminal(True)
            term = code.term
            if term.proc is None:
                term.start(code.project["path"])
            for line in cmd.split("\n"):
                if line.strip():
                    term.run(line)
            return True
        try:
            if osys.open_terminal(cmd, self.workspace()):
                return True
        except Exception as e:
            self.main.toast(tr("No pude abrir una terminal: %s") % e, icon_name="est_error", color=C["bad"])
            return False
        self.main.toast(tr("No encontré ninguna terminal en el sistema. Copia el comando y pégalo en la tuya."), icon_name="est_aviso", color=C["warn"])
        return False

    def can_edit(self, path):
        from .codeview import TEXT_EXT
        return self._code_page() is not None and os.path.splitext(path)[1].lower() in TEXT_EXT

    def open_in_editor(self, path):
        code = self._code_page()
        if code is not None:
            code.tabs.open(path)
        else:
            osys.open_path(path)

    def clear(self):
        while self.cl.count() > 1:
            it = self.cl.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()

    def set_column_width(self, px):
        """Ancho maximo de la conversacion y del compositor (None = todo el ancho disponible)."""
        if self.compact:
            return
        mx = px or 16777215
        self.col.setMaximumWidth(mx)
        self.composer_inner.setMaximumWidth(mx)

    def add(self, w):
        self.cl.insertWidget(self.cl.count() - 1, w)
        if getattr(self, "_live", False):
            fade_in(w)                    # solo lo que llega en vivo, no al reabrir una conversacion
        return w

    def open_session(self, sid):
        old = core.SESSIONS.get(self.sid) if self.sid else None
        if old is not None and old.temp and old.id != sid:      # al salir de un chat temporal, desaparece
            if old.run:
                old.run.request_stop()
            core.SESSIONS.pop(old.id, None)
        self.temp_next = False
        self.assistant_next = None
        self.sid = sid
        self.ev_i = 0
        self.cur = None
        self.steps = None
        self.boxes = []
        self.rows = {}
        self.blocks = []
        self.waiting = 0
        self.busy = False
        self.stick = True
        self.questions = {}
        self.turn_undo = False
        self.clear()
        s = self.session()
        self.empty = None
        if not s or not s.events:
            self.empty = self.add(self._empty_state())
        self.plan_panel.set_items((s.data.get("plan") if s else None) or [], live=False)
        self.sync()
        self.changed.emit()

    def _empty_state(self):
        if self.project_id:
            p = core.project(core.SET.snapshot(), self.project_id)
            return EmptyState(tr("¿Qué construimos en «%s»?") % (p["name"] if p else tr("tu proyecto")),
                              tr("Trabajo dentro de la carpeta del proyecto. Verás cada archivo que cree o cambie."),
                              CODE_SUGGESTIONS, self._pick, self.compact)
        if getattr(self, "temp_next", False):
            return EmptyState(tr("Chat temporal"), tr("Esta conversación no se guardará en el historial y no usa ni cambia la memoria. "
                              "Al empezar otra conversación, desaparece."), [], self._pick, self.compact)
        name = core.SET.snapshot().get("user_name", "").strip()
        return EmptyState((tr("¿En qué te ayudo, %s?") % name) if name else tr("¿En qué te ayudo hoy?"),
                          tr("Puedo trabajar con tus archivos, programas y la web. Cada acción la ves y la apruebas tú."),
                          CHAT_SUGGESTIONS, self._pick, self.compact)

    def _pick(self, text):
        self.input.setPlainText(text)
        self.input.setFocus()
        self.input.moveCursor(self.input.textCursor().MoveOperation.End)

    def _last_visible(self):
        for i in range(self.cl.count() - 2, -1, -1):
            w = self.cl.itemAt(i).widget()
            # oculto = ocultado a propósito; un widget recién añadido aún no se ha mostrado (al reabrir una
            # conversación llegan todos los eventos de golpe) y no debe contar como oculto
            if w is not None and not (w.isHidden() and w.testAttribute(Qt.WA_WState_ExplicitShowHide)):
                return w
        return None

    def pump(self):
        s = self.session()
        if not s:
            return
        if self.ev_i > len(s.events):          # la conversacion se recorto (regenerar): reconstruir
            return self.open_session(self.sid)
        with s.cond:
            new = s.events[self.ev_i:self.ev_i + 400]
        for ev in new:
            try:
                self._live = ev.get("ts", 0) > time.time() - 3
                self.handle(ev)
            except Exception as e:
                print("evento", ev.get("t"), e, file=sys.stderr)
        self.ev_i += len(new)
        busy = s.run is not None
        if busy != self.busy:
            self.busy = busy
            if not busy:
                self._stale()
            self.sync()
            self.changed.emit()

    def handle(self, ev):
        t = ev["t"]
        if t == "user":
            if self.empty is not None:
                self.empty.hide()
                self.empty.deleteLater()
                self.empty = None
            self._end_steps()
            self.cur = None
            self.turn_blocks = []
            self.turn_images = []
            self.last_tool = None
            self.add(user_bubble(ev, self.compact))
        elif t == "turn_start":
            if self.cur is not None and self.cur.empty():   # un paso anterior sin texto ni pensamiento: fuera su línea de espera
                self.cur.hide()
                self.cur.deleteLater()
            self.cur = self.add(AssistantBlock(ev["ts"], ev.get("step", 1), getattr(self, "last_tool", None)))
            if ev["ts"] < time.time() - 5:
                self.cur.status.hide()     # reconstruyendo una conversacion guardada
        elif t == "delta":
            if self.cur is None:
                self.cur = self.add(AssistantBlock(ev["ts"]))
            self.cur.delta(ev["kind"], ev["text"], ev["ts"])
        elif t == "stats":
            if self.cur is not None and ev.get("gen_n"):
                tok = "%s tok" % ev["gen_n"]
                tps = (" · %.1f tok/s" % ev["tps"]) if ev.get("tps") else ""
                cut = tr(" · cortado por límite") if ev.get("finish") == "length" else ""
                ctx = ctx_s = ""
                if ev.get("ctx_used") and ev.get("ctx_max"):
                    ctx = tr(" · contexto %.1fk de %dk") % (ev["ctx_used"] / 1000.0, ev["ctx_max"] // 1000)
                    ctx_s = " · %.1fk/%dk" % (ev["ctx_used"] / 1000.0, ev["ctx_max"] // 1000)
                self.cur.stats.set_options([tok + tps + cut + ctx, tok + tps + cut + ctx_s, (tps[3:] or tok) + cut + ctx_s,
                                            (cut[3:] or (ctx_s[3:] or tok))],
                                           tr("Memoria de la conversación usada por el modelo. Al acercarse al límite, Jayth resume lo antiguo."))
        elif t == "assistant_end":
            if self.cur is None and ev["text"]:
                self.cur = self.add(AssistantBlock(ev["ts"]))
            if self.cur is not None:
                self.cur.finish(ev["text"], ev["ts"])
                if self.cur.empty():
                    self.cur.hide()
                    self.cur.deleteLater()
                else:
                    self.blocks.append(self.cur)
                    self.turn_blocks = getattr(self, "turn_blocks", []) + [self.cur]
                    self.cur.b_regen.clicked.connect(self.regenerate)
                    self._end_steps()
                self.cur = None
        elif t == "tool_call" and ev["name"] == "update_plan":
            pass                                        # se muestra en el panel del plan (evento «plan»)
        elif t == "plan":
            self.plan_panel.set_items(ev.get("items") or [], live=getattr(self, "_live", False))
        elif t == "question":
            card = QuestionCard(ev, self.answer, live=getattr(self, "_live", False) or self.busy)
            self.questions[ev["id"]] = card
            self.add(card)
            self._end_steps()
            if card.inputs.isVisible():
                self.waiting += 1
                self.sync()
                self.main.notify_pending(tr("tiene una pregunta: %s") % ev["question"], ev["ts"])
        elif t == "answer":
            q = self.questions.get(ev["id"])
            if q:
                if q.inputs.isVisible():
                    self.waiting = max(0, self.waiting - 1)
                q.answered(ev.get("text", ""))
                self.sync()
        elif t == "undo":
            for cid in ev.get("ids") or []:
                if cid in self.rows:
                    self.rows[cid].undone()
            self.add(note(tr("Cambios deshechos: %s") % ", ".join(os.path.basename(f) for f in ev.get("files") or [])))
            self._end_steps()
        elif t == "compacted":
            self.add(note(tr("Resumí la parte antigua de la conversación para que el modelo no la olvide ni se quede sin memoria.")))
            self._end_steps()
        elif t == "plan_ready":
            if getattr(self, "_live", False):
                self.add(self._plan_ready_card())
                self._end_steps()
        elif t == "tool_call":
            self.last_tool = ev["name"]
            row = StepRow(ev, self.decide)
            self.rows[ev["id"]] = row
            if self.steps is None or self._last_visible() is not self.steps:
                self._end_steps()
                self.steps = self.add(StepsBox())
                self.boxes = [b for b in getattr(self, "boxes", []) if b.parent() is not None] + [self.steps]
            self.steps.add(row)
            row.box = self.steps
            if row.pending:
                self.waiting += 1
                self.sync()
                self.main.notify_pending(describe(ev["name"], ev.get("args"), "pending"), ev["ts"])
        elif t == "approval":
            r = self.rows.get(ev["id"])
            if r:
                if r.pending:
                    self.waiting = max(0, self.waiting - 1)
                r.resolved(ev["decision"])
                r.box.refresh()
                self.sync()
        elif t == "tool_result":
            if ev.get("ok"):                     # imágenes de esta respuesta (capturas, gráficos): se repiten al final
                for n in (ev.get("images") or ([ev["image"]] if ev.get("image") else [])):
                    p = os.path.join(paths.IMG_DIR, n)
                    imgs = getattr(self, "turn_images", None)
                    if imgs is None:
                        imgs = self.turn_images = []
                    if p not in imgs:
                        imgs.append(p)
            r = self.rows.get(ev["id"])
            if r:
                r.result(ev["ok"], ev.get("text") or "", ev.get("image"))
                if ev["ok"] and r.ev["name"] in ("remember", "forget") and ev["ts"] > time.time() - 10:
                    fact = str((r.ev.get("args") or {}).get("fact") or (r.ev.get("args") or {}).get("text") or "")
                    self.main.toast((tr("Guardado en la memoria: «%s»") if r.ev["name"] == "remember" else tr("Olvidado: «%s»")) % fact[:90],
                                    tr("Ver memoria"), lambda: self.main.settings("Personalización"), icon_name="ia_memoria")
                if ev["ok"] and r.box is not None:
                    for n in (ev.get("images") or [])[1:]:           # el resto de gráficos de un análisis
                        r.box.add_preview(os.path.join(paths.IMG_DIR, n))
                    if ev.get("canvas"):
                        r.box.add_canvas(ev["canvas"], self.main.open_canvas)
                        if ev["ts"] > time.time() - 10:               # en directo se abre solo; al reabrir la conversación, no
                            self.main.open_canvas(ev["canvas"])
                            QTimer.singleShot(80, lambda: OV.glow(getattr(self.main, "canvas", None), 1.8))
                if ev.get("undo") and ev["ok"]:
                    from . import harness
                    if harness.has_snapshot(self.sid, ev["id"]):
                        r.b_undo.show()
                        if not getattr(r, "_undo_wired", False):
                            r._undo_wired = True
                            r.b_undo.clicked.connect(lambda _=False, cid=ev["id"]: self.undo(cid))
                        self.turn_undo = True
                if ev["ok"] and r.ev["name"] in ("write_file", "edit_file", "multi_edit", "create_document") and ev["ts"] > time.time() - 10:
                    p = str((r.ev.get("args") or {}).get("path", ""))
                    if p:
                        self.file_written.emit(os.path.normpath(p if os.path.isabs(p) else os.path.join(self.workspace(), p)))
        elif t in ("info", "error"):
            self.add(note(tr("Detenido por ti.") if (t == "info" and ev["text"] == "Detenido.") else ev["text"], t == "error"))
            self._end_steps()
        elif t == "turn_end":
            if self.cur is not None and self.cur.empty():
                self.cur.hide()
                self.cur.deleteLater()
            self.cur = None
            self._stale()
            self._end_steps()
            for b in getattr(self, "boxes", []):
                try:
                    b.finish()
                except RuntimeError:
                    pass
            # botones y estadisticas solo al final de cada respuesta: las frases intermedias entre acciones quedan limpias
            tb = getattr(self, "turn_blocks", [])
            for b in tb[:-1]:
                b.final = False
            if tb:
                tb[-1].final = True
                imgs = getattr(self, "turn_images", None) or []
                near = self._just_above(tb[-1])          # las que ya se ven justo encima no se repiten
                imgs = [p for p in imgs if p not in (getattr(near, "images", None) or [])]
                if imgs:
                    tb[-1].add_gallery(imgs[-4:])       # cómo quedó: las últimas capturas, bajo la respuesta
            self.turn_blocks = []
            self.turn_images = []
            for b in self.blocks:
                b.actions.setVisible(getattr(b, "final", True))
                b.b_regen.hide()
                b.b_undo_all.hide()
            if self.blocks:
                self.blocks[-1].b_regen.show()      # solo la ultima respuesta se puede regenerar
                if self.turn_undo:
                    last = self.blocks[-1]
                    last.b_undo_all.show()
                    if not getattr(last, "_undo_wired", False):
                        last._undo_wired = True
                        last.b_undo_all.clicked.connect(self.undo_turn)
            self.turn_undo = False
            for q in self.questions.values():
                if q.inputs.isVisible():
                    q.answered("")

    def _just_above(self, w):
        """El elemento visible inmediatamente anterior a w en la conversación."""
        for i in range(self.cl.indexOf(w) - 1, -1, -1):
            x = self.cl.itemAt(i).widget()
            if x is not None and not (x.isHidden() and x.testAttribute(Qt.WA_WState_ExplicitShowHide)):
                return x
        return None

    # ---- plan, preguntas y deshacer
    def _plan_ready_card(self):
        f = QFrame()
        f.setObjectName("noteBox")
        h = QHBoxLayout(f)
        h.setContentsMargins(14, 10, 10, 10)
        h.addWidget(pix_label("ui_check", C["acc"], 16))
        h.addWidget(lbl(tr("Plan listo. Revísalo y, si te convence, ejecútalo.")), 1)
        h.addWidget(btn(tr("Seguir ajustando"), cb=lambda: self.input.setFocus()))
        h.addWidget(btn(tr("Ejecutar el plan"), "primary", lambda: self.execute_plan(f), "hub_lanzar"))
        return f

    def execute_plan(self, card=None):
        if self.busy or not self.session():
            return
        mode = getattr(self, "exec_mode", "ask")
        core.SET.update({"mode": mode})
        self.main.sync()
        if card is not None:
            card.hide()
        self.session().send(tr("Adelante: ejecuta el plan aprobado paso a paso, actualizando la lista de tareas."))
        self.busy = True
        self.sync()

    def answer(self, cid, text):
        s = self.session()
        if s:
            s.answer(cid, text)

    def undo(self, cid):
        s = self.session()
        if s and s.run is None:
            files = s.undo(cid)
            if files:
                self.main.toast(tr("Restaurado: %s") % ", ".join(os.path.basename(f) for f in files), icon_name="acc_refrescar", color=C["ok"])
                for f in files:
                    self.file_written.emit(f)
        elif s:
            self.main.toast(tr("Espera a que el agente termine para deshacer."), icon_name="est_aviso", color=C["warn"])

    def undo_turn(self):
        s = self.session()
        if not s or s.run is not None:
            return
        files = s.undo_turn()
        for b in self.blocks:                # ya no queda nada que deshacer en esta respuesta
            b.b_undo_all.hide()
        if files:
            self.main.toast((tr("Deshecho %d cambio de archivo.") if len(files) == 1 else tr("Deshechos %d cambios de archivos.")) % len(files),
                            icon_name="acc_refrescar", color=C["ok"])
            for f in files:
                self.file_written.emit(f)

    def _end_steps(self):
        """Cierra la caja de acciones en curso: si tenía varias, queda resumida en una línea."""
        if self.steps is not None:
            try:
                self.steps.finish()
            except RuntimeError:               # el widget ya se borró
                pass
        self.steps = None

    def _stale(self):
        for r in self.rows.values():
            if r.pending:
                r.resolved("cancel")
                r.box.refresh()
        self.waiting = 0
        self.sync()

    def decide(self, cid, decision):
        s = self.session()
        if s and s.run:
            s.run.resolve(cid, decision)

    def regenerate(self):
        s = self.session()
        if s:
            err = s.regenerate()
            if err:
                QMessageBox.information(self, APP_NAME, err)
            self.open_session(self.sid)

    def send(self):
        text = self.input.toPlainText().strip()
        files = list(getattr(self, "pending_files", []))
        if self.busy or (not text and not self.pending_imgs and not files):
            return
        if not core.SET.ready():
            return self.main.fix_not_ready()
        if not self.session():
            temp = bool(getattr(self, "temp_next", False))
            aid = getattr(self, "assistant_next", None)
            ns = core.new_session(self.project_id, temp=temp)
            if aid:
                ns.data["assistant"] = aid
            self.open_session(ns.id)
            if temp:
                self.add(note(tr("Chat temporal: esta conversación no se guarda en el historial y no usa ni cambia la memoria.")))
        err = self.session().send(text, list(self.pending_imgs), files)
        if err:
            return QMessageBox.information(self, APP_NAME, err)
        self.input.clear()
        self.pending_imgs = []
        self.pending_files = []
        self._render_thumbs()
        self.busy = True
        self.stick = True
        self.sync()
        self.changed.emit()

    def stop(self):
        s = self.session()
        if s and s.run:
            s.run.request_stop()

    def _add_image(self, src=None, qimage=None):
        name = uuid.uuid4().hex[:12] + ".png"
        if qimage is None:
            ext = os.path.splitext(src)[1].lower()
            if ext in (".jpg", ".jpeg", ".webp", ".gif"):
                name = name[:-4] + ext
            shutil.copyfile(src, os.path.join(paths.IMG_DIR, name))
        else:
            qimage.save(os.path.join(paths.IMG_DIR, name), "PNG")
        self.pending_imgs.append(name)
        self._render_thumbs()

    def attach(self):
        files, _ = QFileDialog.getOpenFileNames(self, tr("Adjuntar imágenes"), os.path.expanduser("~"), tr("Imágenes (*.png *.jpg *.jpeg *.webp *.gif)"))
        for f in files:
            self._add_image(src=f)

    def attach_files(self):
        """Documentos y archivos de texto o código: su contenido se incluye en el mensaje."""
        files, _ = QFileDialog.getOpenFileNames(self, tr("Adjuntar archivos"), self.workspace(),
                                                tr("Documentos y texto (*.txt *.md *.py *.js *.ts *.json *.csv *.html *.css *.xml *.yml *.yaml *.log "
                                                "*.docx *.xlsx *.pptx *.pdf *.ps1 *.bat *.ini *.toml *.sql *.c *.cpp *.h *.cs *.java *.go *.rs);;Todos (*.*)"))
        imgs = [f for f in files if os.path.splitext(f)[1].lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif")]
        for f in imgs:
            self._add_image(src=f)
        self.pending_files = list(getattr(self, "pending_files", [])) + [os.path.normpath(f) for f in files if f not in imgs]
        self._render_thumbs()

    def _fit_model_chip(self):
        """El botón «modelo · esfuerzo» acorta el nombre del modelo lo justo para que todo quepa en una línea
        (en el panel estrecho del modo Code antes bajaba a una segunda línea)."""
        name, label = getattr(self, "_chip_name", ""), getattr(self, "_chip_label", "")
        if not name:
            return
        fm = self.model_chip.fontMetrics()
        cur = self.model_chip.text()
        pad = self.model_chip.sizeHint().width() - fm.horizontalAdvance(cur) if cur else 40
        mode_full = self.mode_chip.fontMetrics().horizontalAdvance(self.mode_chip.text()) + 44   # icono, texto y margenes
        need = pad + fm.horizontalAdvance(" · " + label) + 56                                   # minimo razonable para el nombre
        free = self.chips_w.width() - self.plus_btn.width() - 2 * 6 - 2
        compact_mode = free - mode_full < need                         # muy estrecho: el modo queda solo con su icono
        style = Qt.ToolButtonIconOnly if compact_mode else Qt.ToolButtonTextBesideIcon
        if self.mode_chip.toolButtonStyle() != style:
            self.mode_chip.setToolButtonStyle(style)
            self.mode_chip.setToolTip((tr("Modo: %s. Cómo actúa el agente: pregunta, automático, solo lectura o plan.") % self.mode_chip.text())
                                      if compact_mode else tr("Cómo actúa el agente: pregunta, automático, solo lectura o plan."))
        free -= 34 if compact_mode else mode_full
        room = free - pad - fm.horizontalAdvance(" · " + label)
        room = min(room, 120 if self.compact else 220)
        if room < 48:                         # muy estrecho: solo el modelo; el esfuerzo queda en el tooltip y en el menú
            text = fm.elidedText(name, Qt.ElideRight, max(40, min(free - pad, 120)))
        else:
            text = "%s · %s" % (fm.elidedText(name, Qt.ElideRight, room), label)
        if text != cur:
            self.model_chip.setText(text)

    # ---- asistente de la conversación
    def assistant_id(self):
        s = self.session()
        return (s.data.get("assistant") if s else None) or getattr(self, "assistant_next", None)

    def _fill_assist_menu(self):
        from . import assistants as AS
        m = self.assist_menu
        m.clear()
        cur, started = self.assistant_id(), bool(self.session() and self.session().events)
        for a in AS.all_assistants():
            act = m.addAction(a["name"])
            act.setCheckable(True)
            act.setChecked(a["id"] == cur)
            act.triggered.connect(lambda _=False, i=a["id"]: self.set_assistant(None if i == self.assistant_id() else i))
        if not AS.all_assistants():
            na = m.addAction(tr("Aún no tienes asistentes"))
            na.setEnabled(False)
        m.addSeparator()
        m.addAction(tr("Crear o editar asistentes…"), lambda: self.main.assistants())
        if started:
            m.setToolTipsVisible(True)

    def set_assistant(self, aid):
        """Elige el asistente de la conversación (si ya había empezado, se abre una nueva con él)."""
        if self.busy:
            return
        if self.session() and self.session().events:
            self.open_session(None)
        self.assistant_next = aid
        s = self.session()
        if s:
            s.data["assistant"] = aid
        self._render_thumbs()
        self.input.setFocus()

    IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")

    def add_paths(self, paths_):
        """Adjunta rutas soltadas o pegadas: imagenes como imagen, archivos por su contenido, carpetas por su ruta."""
        dirs = []
        for f in paths_:
            if os.path.isdir(f):
                dirs.append(f)
            elif os.path.splitext(f)[1].lower() in self.IMG_EXTS:
                self._add_image(src=f)
            elif os.path.isfile(f) and f not in getattr(self, "pending_files", []):
                self.pending_files = list(getattr(self, "pending_files", [])) + [f]
        if dirs:                             # una carpeta no se adjunta entera: el agente la explora con sus herramientas
            cur = self.input.toPlainText()
            self.input.setPlainText((cur + ("\n" if cur and not cur.endswith("\n") else "")) + "\n".join(tr("Carpeta: %s") % d for d in dirs))
            self.input.moveCursor(QTextCursor.End)
        self._render_thumbs()
        self.input.setFocus()

    def dragEnterEvent(self, e):
        if local_files(e.mimeData()) or e.mimeData().hasImage():
            e.acceptProposedAction()
            self._drop_hint(True)

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._drop_hint(False)

    def dropEvent(self, e):
        self._drop_hint(False)
        files = local_files(e.mimeData())
        if files:
            self.add_paths(files)
        elif e.mimeData().hasImage():
            img = e.mimeData().imageData()
            if isinstance(img, QImage) and not img.isNull():
                self._add_image(qimage=img)
        e.acceptProposedAction()

    def _drop_hint(self, on):
        if on and not getattr(self, "_drop", None):
            self._drop = QLabel(tr("Suelta aquí para adjuntar\nimágenes, documentos o archivos"), self)
            self._drop.setObjectName("dropHint")
            self._drop.setAlignment(Qt.AlignCenter)
            self._drop.setAttribute(Qt.WA_TransparentForMouseEvents)
        if getattr(self, "_drop", None):
            self._drop.setGeometry(self.rect().adjusted(10, 10, -10, -10))
            self._drop.setVisible(on)
            self._drop.raise_()

    def attach_screenshot(self):
        win = self.window()
        win.hide()

        def grab():
            try:
                self._add_image(qimage=QImage.fromData(T.capture(1600)[0]))
            finally:
                win.showNormal()
                win.raise_()
                win.activateWindow()
        QTimer.singleShot(350, grab)

    def _render_thumbs(self):
        while self.thumbs.count():
            it = self.thumbs.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        for n in self.pending_imgs:
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(0)
            im = QLabel()
            im.setPixmap(QPixmap(os.path.join(paths.IMG_DIR, n)).scaled(72, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            h.addWidget(im)
            h.addWidget(tbtn("ui_cerrar", tr("Quitar"), lambda _=False, n=n: (self.pending_imgs.remove(n), self._render_thumbs()), size=12), 0, Qt.AlignTop)
            self.thumbs.addWidget(w)
        from . import assistants as AS
        a = AS.get(self.assistant_id())
        if a:                                # etiqueta del asistente elegido (se quita con ×, antes de empezar)
            w = QFrame()
            w.setObjectName("noteBox")
            h = QHBoxLayout(w)
            h.setContentsMargins(8, 4, 2, 4)
            h.setSpacing(4)
            h.addWidget(pix_label("ia_controlador", C["acc"], 13))
            h.addWidget(QLabel(tr("Asistente: %s") % a["name"]))
            if not (self.session() and self.session().events):
                h.addWidget(tbtn("ui_cerrar", tr("Quitar el asistente"), lambda _=False: self.set_assistant(None), size=11))
            self.thumbs.addWidget(w)
        for f in getattr(self, "pending_files", []):
            w = QFrame()
            w.setObjectName("noteBox")
            h = QHBoxLayout(w)
            h.setContentsMargins(8, 4, 2, 4)
            h.setSpacing(4)
            h.addWidget(pix_label("acc_nuevo", C["acc"], 13))
            nm = QLabel()
            nm.setText(nm.fontMetrics().elidedText(os.path.basename(f), Qt.ElideMiddle, 170))
            h.addWidget(nm)
            h.addWidget(tbtn("ui_cerrar", tr("Quitar"), lambda _=False, f=f: (self.pending_files.remove(f), self._render_thumbs()), size=11))
            w.setToolTip(f)
            self.thumbs.addWidget(w)
        self.thumbs_w.setVisible(bool(self.pending_imgs or getattr(self, "pending_files", []) or a))
        self._sync_send()

    # ---- dictado por voz
    def toggle_dictation(self):
        from . import voice
        if self._rec is not None and self._rec.recording():
            return self._stop_dictation()
        if not voice.Recorder.available():
            return self.main.toast(tr("No encuentro ningún micrófono en este equipo."), icon_name="est_aviso", color=C["warn"])
        if not voice.stt_ready():
            return self._prepare_dictation()
        self._rec = voice.Recorder()
        try:
            self._rec.start()
        except Exception as e:
            self._rec = None
            return self.main.toast(tr("No se pudo usar el micrófono: %s") % e, icon_name="est_aviso", color=C["warn"])
        self._rec_t0 = time.time()
        self._rec_ph = self.input.placeholderText()
        self.input.setPlaceholderText(tr("Escuchando… habla con normalidad y pulsa ■ para terminar"))
        self.mic_btn.setIcon(icon("trans_detener", C["bad"], 14))
        self.mic_btn.setToolTip(tr("Terminar el dictado"))
        self.rec_wave.set_busy(False)
        self.rec_cancel.show()
        self.rec_bar.show()
        self._rec_timer = QTimer(self, interval=45, timeout=self._rec_tick)     # ~22 veces por segundo: la onda fluye
        self._rec_timer.start()
        self._rec_tick()

    def _rec_tick(self):
        if self._rec is None:
            if self.rec_wave.busy:                # pasando a texto: las barras ondulan
                self.rec_wave.tick()
            return
        secs = time.time() - self._rec_t0
        self.rec_wave.push(self._rec.level())
        self.rec_time.setText("%d:%02d" % (int(secs) // 60, int(secs) % 60))
        on = int(secs * 2) % 2 == 0               # punto rojo que palpita
        self.rec_dot.setStyleSheet("background:%s; border-radius:5px" % (C["bad"] if on else C["bad_bg"]))
        if secs >= 180:                           # tope de tres minutos por dictado
            self._stop_dictation()

    def cancel_dictation(self):
        """Descarta lo grabado sin transcribirlo."""
        if self._rec is not None:
            self._rec.cancel()
        self._rec = None
        self._end_rec_ui()

    def _end_rec_ui(self):
        if getattr(self, "_rec_timer", None):
            self._rec_timer.stop()
        self.rec_bar.hide()
        self.rec_wave.set_busy(False)
        self.mic_btn.setEnabled(True)
        self.mic_btn.setIcon(icon("voz_microfono", C["mut"], 16))
        self.mic_btn.setToolTip(tr("Dictar con el micrófono"))
        self.input.setPlaceholderText(getattr(self, "_rec_ph", tr("Escribe un mensaje…")))

    def _stop_dictation(self):
        from . import voice
        rec, self._rec = self._rec, None
        self.mic_btn.setIcon(icon("voz_microfono", C["mut"], 16))
        self.mic_btn.setToolTip(tr("Dictar con el micrófono"))
        path = rec.stop() if rec else None
        if not path:
            self._end_rec_ui()
            return self.main.toast(tr("No se grabó nada."), icon_name="est_aviso", color=C["warn"])
        self.rec_wave.set_busy(True)              # la franja sigue a la vista mientras se transcribe
        self.rec_cancel.hide()
        self.rec_dot.setStyleSheet("background:%s; border-radius:5px" % C["acc"])
        self.rec_time.setText("…")
        self.input.setPlaceholderText(tr("Pasando tu voz a texto…"))
        self.mic_btn.setEnabled(False)
        cfg = core.SET.snapshot()

        def done(r):
            self._end_rec_ui()
            if isinstance(r, Exception):
                return self.main.toast(str(r), icon_name="est_aviso", color=C["warn"])
            if not str(r).strip():
                return self.main.toast(tr("No entendí nada en la grabación."), icon_name="est_aviso", color=C["warn"])
            cur = self.input.toPlainText()
            self.input.setPlainText((cur + (" " if cur and not cur.endswith((" ", "\n")) else "")) + str(r).strip())
            self.input.moveCursor(QTextCursor.End)
            self.input.setFocus()
        run_bg(lambda: voice.transcribe(path, cfg.get("voice_model") or "base", cfg.get("voice_lang") or ""), done)

    def _prepare_dictation(self):
        from . import voice
        if getattr(self.main, "_voice_setup", False):
            return self.main.toast(tr("El dictado se está preparando; te aviso cuando esté listo."), icon_name="est_info")
        if QMessageBox.question(self, tr("Preparar el dictado"),
                                tr("Para dictar, %s descarga una sola vez el reconocimiento de voz (unos 450 MB con el modelo). "
                                "Funciona en tu equipo, sin enviar tu voz a ningún sitio.\n\n¿Prepararlo ahora?") % APP_NAME) != QMessageBox.StandardButton.Yes:
            return
        self.main._voice_setup = True
        self.main.toast(tr("Preparando el dictado en segundo plano (unos minutos)…"), icon_name="est_info", ms=9000)

        def done(r):
            self.main._voice_setup = False
            if isinstance(r, Exception):
                return self.main.toast(tr("No se pudo preparar el dictado: %s") % str(r)[:200], icon_name="est_aviso", color=C["warn"])
            self.main.toast(tr("Dictado listo: pulsa el micrófono y habla."), icon_name="ui_check", color=C["ok"], ms=9000)
        model = core.SET.snapshot().get("voice_model") or "base"
        run_bg(lambda: voice.ensure_stt(model=model), done)

    def _sync_send(self):
        has = bool(self.input.toPlainText().strip() or self.pending_imgs or getattr(self, "pending_files", []))
        self.send_btn.setEnabled(self.busy or has)
        self.send_btn.setIcon(icon("trans_detener" if self.busy else "lista_subir", C["on_send"] if (self.busy or has) else C["faint"], 14 if self.busy else 16))
        self.send_btn.setToolTip(tr("Detener") if self.busy else tr("Enviar (Enter)"))

    def sync(self):
        cfg = core.SET.snapshot()
        llm = self.main.llm
        st = llm.get("state", "off")
        ext = cfg["llm_mode"] == "external"
        self.banner.setVisible(st != "ready")
        why = core.not_ready(cfg)
        if why == "model_file":
            m = core.active_model(cfg)
            self.ban_txt.setText(tr("No encuentro el archivo de «%s» donde estaba. Si lo moviste de carpeta o de disco, lo busco yo.")
                                 % (core.model_title(m) or m.get("name")))
            self.ban_btn.setText(tr("Buscarlo"))
            self.ban_btn.show()
        elif why:
            self.ban_txt.setText(tr("Aún no hay un modelo configurado.") if why != "engine" else tr("Falta el motor llama.cpp."))
            self.ban_btn.setText(tr("Configurar"))
            self.ban_btn.show()
        elif st == "loading":
            self.ban_txt.setText(tr("Cargando el modelo en memoria. En equipos sin GPU puede tardar unos minutos."))
            self.ban_btn.hide()
        else:
            self.ban_txt.setText(tr("El servidor externo no responde.") if ext else (llm.get("error") or tr("El modelo está apagado.")))
            self.ban_btn.setText(tr("Encender modelo"))
            self.ban_btn.setVisible(not ext)
        self.mode_chip.setText(MODE_LABEL.get(cfg["mode"], cfg["mode"]))
        self.mode_chip.setToolTip(A.MODES.get(cfg["mode"], ""))
        if cfg["mode"] not in ("plan", "readonly"):
            self.exec_mode = cfg["mode"]          # al aprobar un plan se vuelve a este modo
        if cfg["mode"] in self.mode_actions:
            self.mode_actions[cfg["mode"]].setChecked(True)
        eff = core.effort_of(cfg)
        label, desc = next((l, d) for k, l, d in core.EFFORTS if k == eff)
        ext = cfg["llm_mode"] == "external"
        m = core.active_model(cfg)
        name = ((cfg["external_model"] or tr("servidor externo")).split("/")[-1]) if ext else (core.model_title(m) if m else tr("Elegir modelo"))
        self._chip_name, self._chip_label = name, label
        self._fit_model_chip()                                          # modelo · esfuerzo (se cambian en el mismo menú)
        self.model_chip.setToolTip(tr("%s\nEsfuerzo %s: %s\nPulsa para cambiar de modelo o de esfuerzo.") % (
            ("%s · %s" % (core.model_title(m), core.model_quant(m))) if (m and not ext) else name, label.lower(), desc))
        if not self.rec_bar.isVisible():         # mientras se dicta, la caja dice «Escuchando…» / «Pasando tu voz a texto…»
            self.input.setPlaceholderText(tr("Pide algo sobre el proyecto…") if self.project_id else tr("Escribe un mensaje…"))
        self._sync_send()


# ---------------------------------------------------------------- pagina del modo Code
CODE_LAYOUT = {"tree": True, "term": True, "agent": True, "agent_side": "right", "term_pos": "bottom",
               "w_tree": 230, "w_agent": 420, "h_term": 220, "w_term": 420, "focus": None}
CHAT_WIDTHS = [(tr("Estrecha"), 660), (tr("Normal"), 780), (tr("Ancha"), 1040), (tr("Todo el ancho"), 0)]


class CodePage(QWidget):
    layout_changed = Signal()

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.project = None
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        v.addWidget(self.stack)
        # sin proyecto
        e = QWidget()
        ev = QVBoxLayout(e)
        ev.addStretch(1)
        logo = QLabel()
        logo.setPixmap(theme.logo(60))
        logo.setAlignment(Qt.AlignCenter)
        ev.addWidget(logo)
        g = QLabel(CODE_NAME)
        g.setObjectName("greeting")
        g.setAlignment(Qt.AlignCenter)
        ev.addWidget(g)
        s = QLabel(tr("Crea un proyecto o abre una carpeta. El agente trabajará dentro de ella:\ncrea y edita archivos, ejecuta comandos y te muestra cada cambio en el editor."))
        s.setObjectName("muted")
        s.setAlignment(Qt.AlignCenter)
        ev.addWidget(s)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn(tr("Nuevo proyecto"), "primary", main.new_project, "acc_anadir"))
        row.addWidget(btn(tr("Abrir carpeta…"), cb=main.open_folder_project, ico="act_carpeta_abierta"))
        row.addStretch(1)
        ev.addLayout(row)
        ev.addStretch(2)
        self.stack.addWidget(e)
        # espacio de trabajo: explorador | editor (+ terminal) | agente. Todo se redimensiona, se pliega y se recuerda;
        # el agente puede ir a la izquierda o a la derecha y la terminal abajo o a la derecha del editor.
        ws = QWidget()
        wl = QHBoxLayout(ws)
        wl.setContentsMargins(0, 0, 0, 0)
        self.split = panels.Splitter(Qt.Horizontal, "codeSplit")
        from .explorer import ExplorerPanel
        left = ExplorerPanel(tbtn)                       # nombre y botones, «Ir a un archivo…» y el árbol con iconos
        self.left = self.explorer = left
        left.setProperty("foldable", True)
        left.setMinimumWidth(160)
        self.tree = left.tree
        self.proj_lbl = left.name
        left.open_file.connect(lambda p: self.tabs.open(p))
        self.split.addWidget(left)
        QShortcut(QKeySequence("Ctrl+P"), self, activated=lambda: (self.toggle_tree(True), self.explorer.focus_finder()))
        center = panels.Splitter(Qt.Vertical, "codeCenter")
        center.setProperty("main", True)
        self.tabs = EditorTabs()
        self.tabs.setProperty("main", True)
        self.tabs.setMinimumSize(260, 120)
        center.addWidget(self.tabs)
        self.term = Terminal()
        self.term.setProperty("foldable", True)
        self.term.setMinimumSize(220, 90)
        center.addWidget(self.term)
        self.center = center
        self.split.addWidget(center)
        self.chat = ChatPanel(main, compact=True)
        self.chat.changed.connect(main.on_chat_changed)
        self.chat.file_written.connect(self.tabs.refresh)
        self.chat.file_written.connect(lambda _p: OV.glow(self.tabs, 1.4))      # el agente acaba de escribir aquí
        self.chat.file_written.connect(self.tree.mark_changed)                   # y en el árbol queda marcado
        self.tabs.currentChanged.connect(lambda i: getattr(self.tabs.widget(i), "path", None) and self.tree.reveal(self.tabs.widget(i).path))
        self.chat.setMinimumWidth(320)
        self.chat.setProperty("foldable", True)
        self.split.addWidget(self.chat)
        self.split.changed.connect(self._moved)
        self.center.changed.connect(self._moved)
        wl.addWidget(self.split)
        self.stack.addWidget(ws)
        self.lay = dict(CODE_LAYOUT)
        self._sized = False

    # ---- distribucion de paneles
    PANELS = (("left", "tree", "w_tree"), ("chat", "agent", "w_agent"))

    def _term_key(self):
        return "w_term" if self.lay["term_pos"] == "right" else "h_term"

    def _size_of(self, split, w, key):
        if w.isHidden() or not self._sized:
            return int(w.property("last_size") or self.lay[key])
        return split.sizes()[split.indexOf(w)] or int(self.lay[key])

    def layout_state(self):
        """Estado actual para guardarlo en los ajustes."""
        st = dict(self.lay)
        for attr, k, wk in self.PANELS:
            w = getattr(self, attr)
            st[k] = not w.isHidden()
            st[wk] = self._size_of(self.split, w, wk)
        st["term"] = not self.term.isHidden()
        st[self._term_key()] = self._size_of(self.center, self.term, self._term_key())
        return st

    def apply_layout(self, lay):
        self.lay = dict(CODE_LAYOUT, **{k: v for k, v in (lay or {}).items() if k in CODE_LAYOUT})
        self._place_agent(self.lay["agent_side"])
        self.center.setOrientation(Qt.Horizontal if self.lay["term_pos"] == "right" else Qt.Vertical)
        for attr, k, wk in self.PANELS:
            w = getattr(self, attr)
            w.setProperty("last_size", int(self.lay[wk]))
            w.setVisible(bool(self.lay[k]))
        self.term.setProperty("last_size", int(self.lay[self._term_key()]))
        self.term.setVisible(bool(self.lay["term"]))
        self._sized = False
        if self.isVisible():
            QTimer.singleShot(0, self._apply_sizes)

    def _apply_sizes(self):
        """Da a cada panel su tamaño guardado en píxeles y el resto al editor."""
        tot = self.split.width() - self.split.handleWidth() * (self.split.count() - 1)
        if tot < 300 or self.stack.currentIndex() != 1:
            return
        sizes = []
        for i in range(self.split.count()):
            w = self.split.widget(i)
            key = "w_tree" if w is self.left else "w_agent" if w is self.chat else None
            sizes.append(int(w.property("last_size") or self.lay[key]) if key and not w.isHidden() else 0)
        sizes[self.split.indexOf(self.center)] = max(300, tot - sum(sizes))
        for i in range(self.split.count()):           # al cambiar el tamaño de la ventana solo crece o encoge el editor
            self.split.setStretchFactor(i, 1 if self.split.widget(i) is self.center else 0)
        self.center.setStretchFactor(0, 1)
        self.center.setStretchFactor(1, 0)
        self.split.setSizes(sizes)
        vertical = self.center.orientation() == Qt.Vertical
        ctot = (self.center.height() if vertical else self.center.width()) - self.center.handleWidth()
        t = int(self.term.property("last_size") or self.lay[self._term_key()]) if not self.term.isHidden() else 0
        self.center.setSizes([max(160, ctot - t), t])
        self._sized = True

    def showEvent(self, e):
        super().showEvent(e)
        if not self._sized:
            QTimer.singleShot(0, self._apply_sizes)

    def _moved(self):
        if self._sized:
            self.lay.update(self.layout_state())
            self.layout_changed.emit()

    def _toggle(self, w, key, on=None, split=None, keep_focus=False):
        split = split or self.split
        on = w.isHidden() if on is None else bool(on)
        if self._sized and not w.isHidden():
            sz = split.sizes()[split.indexOf(w)]
            if sz > 0:
                w.setProperty("last_size", sz)
        panels.set_visible(split, w, on, animated=animations_on() and self.isVisible() and self._sized)
        self.lay[key] = on
        if not keep_focus and on:
            self.lay["focus"] = None
        self.layout_changed.emit()
        self.main.sync()

    def toggle_tree(self, on=None):
        self._toggle(self.left, "tree", on)

    def toggle_agent(self, on=None):
        self._toggle(self.chat, "agent", on)
        if not self.chat.isHidden():
            self.chat.input.setFocus()

    def toggle_terminal(self, on=None):
        self._toggle(self.term, "term", on, self.center)
        if not self.term.isHidden():
            self.term.inp.setFocus()

    def _place_agent(self, side):
        self.split.insertWidget(0 if side == "left" else self.split.count() - 1, self.chat)

    def set_agent_side(self, side):
        if self._sized:
            self.lay.update(self.layout_state())
        self.lay["agent_side"] = side
        self._place_agent(side)
        self._apply_sizes()
        self.layout_changed.emit()

    def set_term_pos(self, pos):
        if self._sized:
            self.lay.update(self.layout_state())
        self.lay["term_pos"] = pos
        self.center.setOrientation(Qt.Horizontal if pos == "right" else Qt.Vertical)
        self.term.setProperty("last_size", int(self.lay[self._term_key()]))
        if self.term.isHidden():
            self._toggle(self.term, "term", True, self.center)
        self._apply_sizes()
        self.layout_changed.emit()

    def toggle_focus(self):
        """Modo enfoque: solo el editor (se recuerda qué había abierto para volver igual)."""
        prev = self.lay.get("focus")
        trio = ((self.left, "tree", self.split), (self.term, "term", self.center), (self.chat, "agent", self.split))
        if prev:
            self.lay["focus"] = None
            for w, k, sp in trio:
                if prev.get(k):
                    self._toggle(w, k, True, sp, keep_focus=True)
            if prev.get("side", True):
                self.main.set_sidebar(True)
        else:
            state = {k: not w.isHidden() for w, k, _ in trio}
            state["side"] = self.main.side_pinned()
            for w, k, sp in trio:
                self._toggle(w, k, False, sp, keep_focus=True)
            self.main.set_sidebar(False)
            self.lay["focus"] = state
            self.main.toast(tr("Modo enfoque: solo el editor. Pulsa Ctrl+Shift+M para volver."), ms=3500, icon_name="app_pantalla_completa")
        self.layout_changed.emit()
        self.main.sync()

    def reset_layout(self):
        self.apply_layout({})
        self._apply_sizes()
        self.layout_changed.emit()

    def set_project(self, p):
        if self.project and p and self.project["id"] == p["id"]:
            return
        if self.tabs.has_dirty():
            self.tabs.close_all()
        else:
            while self.tabs.tabs():
                self.tabs.close_tab(self.tabs.indexOf(self.tabs.tabs()[0]))
        self.project = p
        if not p:
            self.stack.setCurrentIndex(0)
            self.term.stop()
            return
        os.makedirs(p["path"], exist_ok=True)
        self.stack.setCurrentIndex(1)
        if not self._sized:
            QTimer.singleShot(0, self._apply_sizes)
        self.explorer.set_project(p["name"], p["path"])
        self.term.root = p["path"]
        self.term.start(p["path"])
        self.chat.project_id = p["id"]
        ss = core.sessions_for(p["id"])
        self.chat.open_session(ss[0].id if ss else None)

    def _new_file(self):
        if not self.project:
            return
        n, ok = QInputDialog.getText(self, tr("Nuevo archivo"), tr("Nombre (puede incluir carpetas, p. ej. src/main.py):"))
        if ok and n.strip():
            fp = os.path.join(self.project["path"], n.strip())
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            if not os.path.exists(fp):
                open(fp, "w", encoding="utf-8").close()
            self.tabs.open(fp)


class _Sig(QObject):
    status = Signal(object)


# ---------------------------------------------------------------- ventana principal
class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_icon())
        self.resize(1320, 840)
        self.setMinimumSize(960, 600)
        self.llm = {"state": "off"}
        self.sig = _Sig()
        self.sig.status.connect(self._got_status)
        self._polling = False
        self._sig_chat = self._sig_code = None
        self._swapping = False
        self.mode = "chat"
        cfg = core.SET.snapshot()
        # barra de titulo integrada: se quita la de Windows conservando el ajuste a los bordes, la sombra y las animaciones
        self.frameless = bool(cfg.get("custom_titlebar", True)) and os.name == "nt"
        if self.frameless:
            self.setWindowFlag(Qt.FramelessWindowHint, True)   # Qt no reserva bordes; Windows recupera sus estilos en showEvent
        self.update_info = None
        self.model_news = []
        self.folded, self.chat_width, self._side_sized = set(), 780, False
        self._build()
        from . import providers as _pv
        _pv.migrate()                        # el antiguo servidor externo único pasa a la lista de servicios
        self._init_peek()
        self._init_quick()
        self._init_tasks()
        self._init_models()
        # cuando el agente usa el ratón y el teclado: brillo en los bordes de la pantalla, su puntero y un aviso
        self.overlay = OV.ControlOverlay()
        T.UI_HOOK = self.overlay.notify
        # navegador integrado: el agente lo usa con browser_* (el panel se crea la primera vez que hace falta)
        from .browser import BrowserBridge
        self.browser = None
        self.browser_bridge = BrowserBridge(self.browser_panel)
        T.BROWSER = self.browser_bridge
        self._tray()
        self.chat.open_session(None)
        self.code.set_project(core.project(cfg, cfg["active_project"]))
        self.set_mode(cfg.get("app_mode") or "chat", save=False)
        self.poll_t = QTimer(self, interval=2500, timeout=self.poll)
        self.poll_t.start()
        self.poll()
        QTimer.singleShot(2500, self._update_on_start)                            # «se actualizó» o una versión ya descargada
        QTimer.singleShot(9000, self.check_news)                                   # novedades al poco de abrir…
        self.news_t = QTimer(self, interval=6 * 3600 * 1000, timeout=self.check_news)   # …y cada 6 horas
        self.news_t.start()
        QTimer.singleShot(1500, self.sync_mcp)
        # distribucion de paneles guardada (anchos, paneles plegados, lados) y atajos
        self._restore_layout(cfg.get("layout") or {})
        self.code.layout_changed.connect(self._save_layout_soon)
        self.hsplit.changed.connect(self._save_layout_soon)
        self._layout_t = QTimer(self, singleShot=True, interval=500, timeout=self._save_layout)
        for keys, fn in (("Ctrl+N", self.new_conversation), ("Ctrl+K", self.focus_search), ("Ctrl+Shift+S", self.toggle_sidebar),
                         ("Ctrl+1", lambda: self.set_mode("chat")), ("Ctrl+2", lambda: self.set_mode("code")),
                         ("Ctrl+`", lambda: self._code_do(self.code.toggle_terminal)),
                         ("Ctrl+B", lambda: self._code_do(self.code.toggle_tree)),
                         ("Ctrl+L", lambda: self._code_do(self.code.toggle_agent)),
                         ("Ctrl+Shift+M", lambda: self._code_do(self.code.toggle_focus)),
                         ("Escape", self._escape)):
            QShortcut(QKeySequence(keys), self, activated=fn)

    def _code_do(self, fn):
        """Acciones de paneles del modo Code (solo con un proyecto abierto)."""
        if self.mode == "code" and self.code.project:
            fn()

    # ---- distribucion de paneles: se guarda sola y se restaura al abrir
    def _restore_layout(self, lay):
        lay = lay if isinstance(lay, dict) else {}
        self.folded = set(lay.get("folded") or [])
        self.chat_width = lay.get("chat_width", 780)
        self.chat.set_column_width(self.chat_width)
        self.side.setProperty("last_size", int(lay.get("side_w") or 264))
        self._side_sized = False
        if not lay.get("side_pinned"):       # por defecto oculta: se asoma al pasar el raton por ☰ y se fija con un clic
            self.side.hide()
            self.b_expand.show()
        for key, sec, w in (("projects", self.sec_projects, self.plist), ("convs", self.sec_convs, self.clist)):
            on = (lay.get("sections") or {}).get(key, True)
            sec.set_open(on)
            w.setVisible(on)
        self.code.apply_layout(lay.get("code"))

    def _layout_state(self):
        side_w = self.side.property("last_size") or 264
        if self.side_pinned() and self._side_sized:
            side_w = self.hsplit.sizes()[0] or side_w
        return {"side_pinned": self.side_pinned(), "side_w": int(side_w), "code": self.code.layout_state(),
                "chat_width": self.chat_width, "folded": sorted(self.folded),
                "sections": {"projects": self.sec_projects.opened, "convs": self.sec_convs.opened}}

    def _save_layout_soon(self):
        if getattr(self, "_layout_t", None):
            self._layout_t.start()

    def _save_layout(self):
        core.SET.update({"layout": self._layout_state()})

    def _apply_side_width(self):
        tot = self.hsplit.width() - self.hsplit.handleWidth()
        if tot < 400 or self._peek or self.hsplit.indexOf(self.side) < 0:
            return
        w = int(self.side.property("last_size") or 264)
        self.hsplit.setSizes([w if not self.side.isHidden() else 0, tot - (w if not self.side.isHidden() else 0)])
        self._side_sized = True

    def reset_layout(self):
        self.folded = set()
        self.chat_width = 780
        self.chat.set_column_width(780)
        self.side.setProperty("last_size", 264)
        self.set_sidebar(False)              # distribucion de fabrica: barra lateral oculta (se asoma con ☰)
        for sec, w in ((self.sec_projects, self.plist), (self.sec_convs, self.clist)):
            sec.set_open(True)
            w.show()
        self.code.reset_layout()
        self._sig_chat = self._sig_code = None
        self.refresh_lists()
        self._save_layout()
        self.toast(tr("Distribución de paneles restablecida."), ms=2500, icon_name="act_layout_ui")

    def set_chat_width(self, px):
        self.chat_width = px
        self.chat.set_column_width(px)
        self._save_layout_soon()

    def _fill_layout_menu(self):
        m = self.layout_menu
        m.clear()

        def check(text, on, fn, ico=None, keys=""):
            a = m.addAction(icon(ico) if ico else QIcon(), text + ("\t" + keys if keys else ""), lambda *_: fn())   # sin pasar «checked»
            a.setCheckable(True)
            a.setChecked(bool(on))
            return a
        check(tr("Barra lateral fija"), self.side_pinned(), self.toggle_sidebar, "ui_barra_lateral", "Ctrl+Shift+S")
        if self.mode == "code" and self.code.project:
            c = self.code
            check(tr("Explorador de archivos"), not c.left.isHidden(), c.toggle_tree, "pan_explorador", "Ctrl+B")
            check(tr("Terminal"), not c.term.isHidden(), c.toggle_terminal, "pan_consola", "Ctrl+`")
            check(tr("Panel del agente"), not c.chat.isHidden(), c.toggle_agent, "mat_comentario", "Ctrl+L")
            m.addSeparator()
            g1 = QActionGroup(m)
            for side, text in (("left", tr("Agente a la izquierda")), ("right", tr("Agente a la derecha"))):
                a = check(text, c.lay["agent_side"] == side, lambda s=side: c.set_agent_side(s), "uij_alinear_izq" if side == "left" else "uij_alinear_der")
                g1.addAction(a)
            g2 = QActionGroup(m)
            for pos, text, ico in (("bottom", tr("Terminal debajo del editor"), "ui_dividir_v"), ("right", tr("Terminal a la derecha del editor"), "ui_dividir_h")):
                a = check(text, c.lay["term_pos"] == pos, lambda p=pos: c.set_term_pos(p), ico)
                g2.addAction(a)
            m.addSeparator()
            check(tr("Modo enfoque (solo el editor)"), c.lay.get("focus"), c.toggle_focus, "app_pantalla_completa", "Ctrl+Shift+M")
        else:
            m.addSeparator()
            sub = m.addMenu(icon("uij_layout_horizontal"), tr("Ancho de la conversación"))
            g = QActionGroup(sub)
            for text, px in CHAT_WIDTHS:
                a = sub.addAction(text, lambda *_, px=px: self.set_chat_width(px))
                a.setCheckable(True)
                a.setChecked((self.chat_width or 0) == px)
                g.addAction(a)
        m.addSeparator()
        m.addAction(icon("acc_refrescar"), tr("Restablecer la distribución"), self.reset_layout)

    def sync_mcp(self):
        """Arranca los conectores MCP configurados (en segundo plano) y avisa si alguno falla."""
        from . import harness
        servers = core.SET.snapshot().get("mcp_servers") or []
        if not servers and not harness.MCP:
            return

        def done(st):
            if isinstance(st, Exception):
                return
            bad = {n: e for n, e in st.items() if e}
            if bad:
                self.toast(tr("No se pudo conectar: %s") % "; ".join("%s (%s)" % (n, e[:80]) for n, e in bad.items()), icon_name="est_aviso", color=C["warn"])
        run_bg(lambda: harness.mcp_sync(servers), done)

    # ---- construccion
    def _build(self):
        central = QWidget()
        central.setObjectName("central")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)
        # barra lateral | contenido, con divisor arrastrable (doble clic: plegar la barra)
        self.hsplit = panels.Splitter(Qt.Horizontal, "mainSplit")
        self.hsplit.addWidget(self._sidebar())
        main = QWidget()
        main.setObjectName("main")
        main.setProperty("main", True)
        mv = QVBoxLayout(main)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(0)
        mv.addWidget(self._header())
        mv.addWidget(hline())
        self.pages = QStackedWidget()
        self.chat = ChatPanel(self)
        self.chat.changed.connect(self.on_chat_changed)
        self.pages.addWidget(self.chat)
        self.code = CodePage(self)
        self.pages.addWidget(self.code)
        # lienzo: a la derecha de la conversacion; aparece cuando el agente muestra algo en el
        from .canvas import CanvasPanel
        self.body_split = panels.Splitter(Qt.Horizontal, "bodySplit")
        self.body_split.addWidget(self.pages)
        self.canvas = CanvasPanel(self)
        self.canvas.closed.connect(lambda: self.set_canvas(False))
        self.canvas.hide()
        self.body_split.addWidget(self.canvas)
        self.body_split.setStretchFactor(0, 1)
        self.body_split.setStretchFactor(1, 1)
        mv.addWidget(self.body_split, 1)
        self.hsplit.addWidget(main)
        self.hsplit.setStretchFactor(0, 0)
        self.hsplit.setStretchFactor(1, 1)
        root.addWidget(self.hsplit, 1)

    def _nav(self, layout, ico, text, cb, tip=""):
        b = QPushButton(text)
        b.setObjectName("nav")
        b.setIcon(icon(ico, C["tx"], 16))
        b.setIconSize(QSize(16, 16))
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip("%s  ·  %s" % (text, tip) if tip else text)
        b.clicked.connect(cb)
        layout.addWidget(b)
        return b

    def _sidebar(self):
        self.side = QWidget()
        self.side.setObjectName("sidebar")
        self.side.setMinimumWidth(200)                 # el ancho se ajusta arrastrando el borde y se recuerda
        self.side.setMaximumWidth(460)
        self.side.setProperty("foldable", True)
        sv = QVBoxLayout(self.side)
        sv.setContentsMargins(10, 0, 10, 10)
        sv.setSpacing(2)
        self.side_top = QWidget()            # zona de arrastre de la ventana (junto con la cabecera)
        self.side_top.setFixedHeight(46)
        top = QHBoxLayout(self.side_top)
        top.setContentsMargins(2, 0, 0, 0)
        logo = QLabel()
        logo.setPixmap(theme.logo(24))
        top.addWidget(logo)
        name = QLabel(APP_NAME)
        name.setStyleSheet("font-weight:700; font-size:12pt")
        top.addWidget(name, 1)
        b_hide = tbtn("ui_menu_hamburguesa", tr("Ocultar barra lateral  ·  Ctrl+Shift+S"), self.toggle_sidebar, size=16)
        b_hide.setAccessibleName(tr("Ocultar barra lateral"))
        top.addWidget(b_hide)
        sv.addWidget(self.side_top)
        sv.addSpacing(4)
        seg = QFrame()
        seg.setObjectName("segment")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(3, 3, 3, 3)
        sl.setSpacing(3)
        self.seg_chat = QPushButton("Chat")
        self.seg_code = QPushButton("Code")
        for b, m, tip in ((self.seg_chat, "chat", tr("Conversaciones (Ctrl+1)")), (self.seg_code, "code", tr("Proyectos de código (Ctrl+2)"))):
            b.setObjectName("segBtn")
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, m=m: self.set_mode(m))
            sl.addWidget(b)
        sv.addWidget(seg)
        sv.addSpacing(8)
        self.side_stack = QStackedWidget()
        # -- lateral del modo Chat
        cw = QWidget()
        cl = QVBoxLayout(cw)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(2)
        self._nav(cl, "acc_renombrar", tr("Nueva conversación"), self.new_conversation, "Ctrl+N")
        self._nav(cl, "acc_buscar", tr("Buscar"), self.focus_search, "Ctrl+K")
        self._nav(cl, "ia_controlador", tr("Modelos"), self.models)
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText(tr("Buscar en tus conversaciones"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda: (setattr(self, "_sig_chat", None), self.refresh_lists()))
        self.search.hide()
        cl.addWidget(self.search)
        cl.addSpacing(6)
        self.list = QListWidget()
        self.list.setObjectName("history")
        elide_list(self.list)
        self.list.itemClicked.connect(lambda it: self._history_click(it, self.chat))
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(lambda pos: self._session_menu(self.list, pos, self.chat))
        cl.addWidget(self.list, 1)
        self.side_stack.addWidget(cw)
        # -- lateral del modo Code
        kw = QWidget()
        kl = QVBoxLayout(kw)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.setSpacing(2)
        self._nav(kl, "acc_anadir", tr("Nuevo proyecto"), self.new_project)
        self._nav(kl, "act_carpeta_abierta", tr("Abrir carpeta…"), self.open_folder_project)
        # secciones plegables: Proyectos y Conversaciones del proyecto
        self.sec_projects = panels.Section(tr("Proyectos"))
        kl.addWidget(self.sec_projects)
        self.plist = QListWidget()
        self.plist.setObjectName("history")
        elide_list(self.plist)
        self.plist.setMaximumHeight(170)
        self.plist.itemClicked.connect(lambda it: it.data(Qt.UserRole) and self.select_project(it.data(Qt.UserRole)))
        self.plist.setContextMenuPolicy(Qt.CustomContextMenu)
        self.plist.customContextMenuRequested.connect(self._project_menu)
        kl.addWidget(self.plist)
        self.sec_convs = panels.Section(tr("Conversaciones del proyecto"))
        self.sec_convs.extra.addWidget(tbtn("acc_renombrar", tr("Nueva conversación del proyecto (Ctrl+N)"), self.new_conversation, size=14))
        kl.addWidget(self.sec_convs)
        self.sec_projects.toggled.connect(lambda on: self._fold_section(self.plist, on))
        self.sec_convs.toggled.connect(lambda on: self._fold_section(self.clist, on))
        self.clist = QListWidget()
        self.clist.setObjectName("history")
        elide_list(self.clist)
        self.clist.itemClicked.connect(lambda it: self._history_click(it, self.code.chat))
        self.clist.setContextMenuPolicy(Qt.CustomContextMenu)
        self.clist.customContextMenuRequested.connect(lambda pos: self._session_menu(self.clist, pos, self.code.chat))
        kl.addWidget(self.clist, 1)
        kl.addStretch(0)                   # con las listas plegadas, lo demás queda arriba
        self.side_stack.addWidget(kw)
        sv.addWidget(self.side_stack, 1)
        self.update_btn = QPushButton(tr("  Actualización disponible"))
        self.update_btn.setObjectName("updateBtn")
        self.update_btn.setIcon(icon("acc_descargar", C["acc"], 15))
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.clicked.connect(self._update_clicked)
        self.update_btn.hide()
        sv.addWidget(self.update_btn)
        sv.addSpacing(4)
        sv.addWidget(hline())
        # perfil: generico (sin datos de nadie) y con un menu util, como en las apps de escritorio habituales
        foot = QPushButton()
        foot.setObjectName("nav")
        foot.setCursor(Qt.PointingHandCursor)
        foot.setToolTip(tr("Tu perfil y ajustes"))
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(6, 6, 6, 6)
        self.avatar = QLabel()
        self.avatar.setObjectName("avatar")
        self.avatar.setFixedSize(26, 26)
        self.avatar.setAlignment(Qt.AlignCenter)
        fh.addWidget(self.avatar)
        self.user_lbl = QLabel()
        fh.addWidget(self.user_lbl, 1)
        fh.addWidget(pix_label("ui_menu_horizontal", C["mut"], 14))
        foot.setMinimumHeight(42)
        pm = QMenu(self)
        pm.addAction(icon("acc_ajustes"), tr("Ajustes"), lambda: self.settings("General"))
        pm.addAction(icon("mat_comentario"), tr("Personalización"), lambda: self.settings("Personalización"))
        pm.addAction(icon("ia_memoria"), tr("Memoria"), lambda: self.settings("Personalización"))
        pm.addAction(icon("ia_controlador"), tr("Asistentes y habilidades"), self.assistants)
        pm.addAction(icon("acc_refrescar"), tr("Tareas programadas"), self.tasks)
        pm.addAction(icon("ia_controlador"), tr("Modelos"), self.models)
        pm.addAction(icon("hub_conectar"), tr("Modelos por API…"), self.providers)
        pm.addSeparator()
        pm.addAction(icon("inp_teclado"), tr("Atajos de teclado"), lambda: self.settings("Atajos de teclado"))
        pm.addAction(icon("mat_comentario"), tr("Enviar comentarios…"), lambda: FeedbackDialog(self, "idea").exec())
        pm.addAction(icon("est_error"), tr("Informar de un error…"), lambda: FeedbackDialog(self, "error").exec())
        pm.addAction(icon("acc_refrescar"), tr("Buscar actualizaciones"), lambda: self.check_news(manual=True))
        pm.addAction(icon("est_info"), tr("Acerca de %s") % APP_NAME, lambda: self.settings("Acerca de"))
        pm.addSeparator()
        pm.addAction(icon("ui_cerrar"), tr("Salir"), self.quit_app)
        foot.clicked.connect(lambda: pm.exec(foot.mapToGlobal(QPoint(0, 0)) - QPoint(0, pm.sizeHint().height() + 4)))   # se abre hacia arriba
        sv.addWidget(foot)
        return self.side

    def _header(self):
        head = QWidget()
        head.setObjectName("titlebar")
        head.setFixedHeight(46)
        self.head = head                     # tambien es la barra de titulo de la ventana (zona de arrastre)
        h = QHBoxLayout(head)
        h.setContentsMargins(14, 0, 0 if self.frameless else 14, 0)
        h.setSpacing(6)
        self.b_expand = tbtn("ui_menu_hamburguesa", tr("Barra lateral: pasa el ratón para verla, clic para dejarla fija  ·  Ctrl+Shift+S"),
                             self.toggle_sidebar, size=16)
        self.b_expand.setAccessibleName(tr("Barra lateral"))
        self.b_expand.hide()
        h.addWidget(self.b_expand)
        self.model_btn = QToolButton()
        self.model_btn.setObjectName("modelBtn")
        self.model_btn.setPopupMode(QToolButton.InstantPopup)
        self.model_menu = QMenu(self)
        self.model_menu.aboutToShow.connect(self._fill_model_menu)
        self.model_btn.setMenu(self.model_menu)
        self.model_btn.hide()                # el modelo se elige en la barra del mensaje; aqui queda el estado del motor
        h.addWidget(self.model_btn)
        self.status_lbl = QLabel()
        h.addWidget(self.status_lbl)
        h.addStretch(1)
        self.title = QLabel()
        self.title.setObjectName("muted")
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.title.setAlignment(Qt.AlignCenter)
        h.addWidget(self.title, 2)
        h.addStretch(1)
        # paneles del modo Code: se resaltan cuando estan visibles
        self.b_tree = tbtn("pan_explorador", tr("Explorador de archivos  ·  Ctrl+B"), lambda: self.code.toggle_tree())
        self.b_term = tbtn("pan_consola", tr("Terminal  ·  Ctrl+`"), lambda: self.code.toggle_terminal())
        self.b_agent = tbtn("mat_comentario", tr("Panel del agente  ·  Ctrl+L"), lambda: self.code.toggle_agent())
        for b in (self.b_tree, self.b_term, self.b_agent):
            h.addWidget(b)
        self.b_temp = QToolButton()
        self.b_temp.setObjectName("chip")
        self.b_temp.setText(tr("Temporal"))
        self.b_temp.setCheckable(True)
        self.b_temp.setCursor(Qt.PointingHandCursor)
        self.b_temp.setAccessibleName(tr("Chat temporal"))
        self.b_temp.setToolTip(tr("Chat temporal: una conversación que no se guarda en el historial y no usa ni cambia la memoria"))
        self.b_temp.clicked.connect(lambda on: self.toggle_temp(on))
        h.addWidget(self.b_temp)
        self.b_web = tbtn("herr_espacio_mundo", tr("Navegador de Jayth: navega tú o pide al agente que use una web por ti"), lambda: self.set_browser(None))
        h.addWidget(self.b_web)
        self.b_layout = tbtn("act_layout_ui", tr("Distribución de paneles"))
        self.b_layout.setPopupMode(QToolButton.InstantPopup)
        self.layout_menu = QMenu(self)
        self.layout_menu.aboutToShow.connect(self._fill_layout_menu)
        self.b_layout.setMenu(self.layout_menu)
        h.addWidget(self.b_layout)
        self.b_folder = tbtn("act_carpeta_abierta", "", lambda: osys.open_path(self.current_panel().workspace()))
        h.addWidget(self.b_folder)
        more = tbtn("ui_menu_horizontal", tr("Más opciones"))
        more.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(self)
        m.addAction(icon("acc_renombrar"), tr("Renombrar conversación"), lambda: self._rename(self.current_panel().session()))
        m.addAction(icon("act_carpeta_abierta"), tr("Abrir carpeta de trabajo"), lambda: osys.open_path(self.current_panel().workspace()))
        m.addSeparator()
        m.addAction(icon("acc_eliminar", C["bad"]), tr("Borrar conversación"), lambda: self._delete(self.current_panel().session(), self.current_panel()))
        more.setMenu(m)
        h.addWidget(more)
        if self.frameless:
            h.addSpacing(8)
            # botones de ventana con la fuente de iconos de Windows (Segoe Fluent / MDL2)
            self.b_min = self._winbtn("", tr("Minimizar"), self.showMinimized)
            self.b_max = self._winbtn("", tr("Maximizar"), self.toggle_max)
            self.b_close = self._winbtn("", tr("Cerrar"), self.close, close=True)
            for b in (self.b_min, self.b_max, self.b_close):
                h.addWidget(b, 0, Qt.AlignTop)
        return head

    def _winbtn(self, glyph, tip, cb, close=False):
        b = QPushButton(glyph)
        b.setObjectName("winClose" if close else "winBtn")
        b.setFixedHeight(46)
        b.setToolTip(tip)
        b.clicked.connect(cb)
        return b

    def toggle_max(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def changeEvent(self, e):
        super().changeEvent(e)
        if getattr(self, "frameless", False) and hasattr(self, "b_max") and e.type() == e.Type.WindowStateChange:
            self.b_max.setText("" if self.isMaximized() else "")
            self.b_max.setToolTip(tr("Restaurar") if self.isMaximized() else tr("Maximizar"))

    # ---- barra de titulo integrada (Windows): se quita la nativa y se indica a Windows que zonas son "titulo" y "borde"
    def _native_frame(self):
        """Barra de titulo integrada: devuelve a la ventana sin marco los estilos de una ventana normal (ajuste a los
        bordes, animaciones, redimensionado y, sobre todo, maximizar al area de trabajo sin tapar la barra de tareas).
        Debe hacerse ANTES de mostrarla: si se maximiza sin WS_CAPTION, Windows la trata como pantalla completa."""
        if not getattr(self, "frameless", False) or getattr(self, "_frame_done", False):
            return
        self._frame_done = True
        hwnd = int(self.winId())                  # crea la ventana nativa (todavia oculta)
        try:
            u = ctypes.windll.user32
            style = u.GetWindowLongW(hwnd, -16)
            u.SetWindowLongW(hwnd, -16, style | 0x00040000 | 0x00C00000 | 0x00010000 | 0x00020000)   # THICKFRAME|CAPTION|MAXIMIZEBOX|MINIMIZEBOX

            class MARGINS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int), ("t", ctypes.c_int), ("b", ctypes.c_int)]
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(MARGINS(1, 1, 1, 1)))   # mantiene la sombra
            u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0020 | 0x0002 | 0x0001 | 0x0004 | 0x0010)              # FRAMECHANGED|NOMOVE|NOSIZE|NOZORDER|NOACTIVATE
            theme.rounded(self)
        except Exception:
            pass

    def showEvent(self, e):
        self._native_frame()                      # por si se mostro sin pasar por main()
        super().showEvent(e)
        if not getattr(self, "_side_sized", True):
            QTimer.singleShot(0, self._apply_side_width)        # ancho guardado de la barra lateral, en pixeles reales

    def nativeEvent(self, event_type, message):
        if not getattr(self, "frameless", False) or not hasattr(self, "head") or bytes(event_type) != b"windows_generic_MSG":
            return super().nativeEvent(event_type, message)
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0083 and msg.wParam:                    # WM_NCCALCSIZE: toda la ventana es area de cliente
            if self.isMaximized():                                  # al maximizar Windows desborda el monitor por el grosor del borde
                user32 = ctypes.windll.user32
                dpi = user32.GetDpiForWindow(msg.hWnd) or 96
                f = user32.GetSystemMetricsForDpi(32, dpi) + user32.GetSystemMetricsForDpi(92, dpi)   # SM_CXSIZEFRAME + SM_CXPADDEDBORDER

                class NCCALCSIZE_PARAMS(ctypes.Structure):
                    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]
                p = NCCALCSIZE_PARAMS.from_address(msg.lParam)
                p.rgrc[0].left += f
                p.rgrc[0].top += f
                p.rgrc[0].right -= f
                p.rgrc[0].bottom -= f
            return True, 0
        if msg.message == 0x0084:                                   # WM_NCHITTEST
            return True, self._hit_test()
        return super().nativeEvent(event_type, message)

    def _hit_test(self):
        pos = self.mapFromGlobal(QCursor.pos())
        x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
        b = 6
        if not self.isMaximized():
            left, right, top, bottom = x < b, x >= w - b, y < b, y >= h - b
            if top and left:
                return 13          # HTTOPLEFT
            if top and right:
                return 14          # HTTOPRIGHT
            if bottom and left:
                return 16          # HTBOTTOMLEFT
            if bottom and right:
                return 17          # HTBOTTOMRIGHT
            if left:
                return 10          # HTLEFT
            if right:
                return 11          # HTRIGHT
            if top:
                return 12          # HTTOP
            if bottom:
                return 15          # HTBOTTOM
        for zone in (self.head, self.side_top):
            if zone.isVisible() and zone.rect().contains(zone.mapFromGlobal(QCursor.pos())):
                child = self.childAt(pos)
                while child is not None and child is not zone:
                    if isinstance(child, (QAbstractButton, QLineEdit, QComboBox)):
                        return 1   # HTCLIENT: los botones siguen funcionando
                    child = child.parentWidget()
                return 2           # HTCAPTION: arrastrar, doble clic para maximizar y ajuste a los bordes
        return 1

    # ---- ventana rápida (atajo global)
    def _init_quick(self):
        from .quick import QuickWindow, GlobalHotkey
        self.quick = QuickWindow()
        self.quick.submit.connect(self.quick_send)
        global _HOTKEY                    # uno por proceso: al recrear la ventana (cambio de tema) se reutiliza
        if _HOTKEY is None:
            _HOTKEY = GlobalHotkey()
        else:
            try:
                _HOTKEY.pressed.disconnect()
            except (RuntimeError, TypeError):
                pass
        self.hotkey = _HOTKEY
        self.hotkey.pressed.connect(self.quick_open)
        if os.environ.get("JAYTH_NO_HOTKEY") != "1":       # las pruebas no registran atajos globales
            self._apply_hotkey()

    def _apply_hotkey(self, tell=False):
        combo = (core.SET.snapshot().get("quick_hotkey") or "").strip()
        if combo and combo == self.hotkey.combo and self.hotkey.active():
            return
        ok = self.hotkey.start(combo)
        if combo and not ok:
            self.toast(self.hotkey.error, icon_name="est_aviso", color=C["warn"])
        elif tell and ok:
            self.toast(tr("Ventana rápida: pulsa %s desde cualquier programa.") % combo, icon_name="ui_check", color=C["ok"])

    def quick_open(self):
        if self.quick.isVisible():
            return self.quick.hide()
        shot = None
        if core.SET.snapshot().get("computer_control", True) is not False:
            try:
                shot = T.capture(1600)[0]              # lo que hay en pantalla ahora, antes de que aparezca la ventana
            except Exception:
                shot = None
        self.quick.popup(shot)

    def quick_send(self, text, shot):
        """Pregunta hecha desde la ventana rápida: conversación nueva en modo Chat, con la captura si se pidió."""
        self._show()
        if self.mode != "chat":
            self.set_mode("chat")
        p = self.chat
        if p.busy:
            return self.toast(tr("El agente sigue trabajando; espera a que termine o detenlo."), icon_name="est_aviso", color=C["warn"])
        p.open_session(None)
        if shot:
            p._add_image(qimage=QImage.fromData(shot))
        p.input.setPlainText(text)
        p.send()

    # ---- lienzo
    def open_canvas(self, item):
        """Muestra en el lienzo un contenido creado por el agente ({title, kind, path, version, slug})."""
        if not item or not os.path.isfile(item.get("path", "")):
            return self.toast(tr("Ese contenido del lienzo ya no existe."), icon_name="est_aviso", color=C["warn"])
        self.canvas.load(item)
        self.set_canvas(True)

    # ---- navegador integrado (comparte el sitio del lienzo: se ve uno u otro)
    def browser_panel(self):
        """Muestra el navegador (lo crea la primera vez) y lo devuelve; lo usan el botón y las herramientas del agente."""
        if self.browser is None:
            from .browser import BrowserPanel
            self.browser = BrowserPanel(self)
            self.browser.closed.connect(lambda: self.set_browser(False))
            self.browser.hide()
            self.body_split.addWidget(self.browser)
            self.body_split.setStretchFactor(self.body_split.indexOf(self.browser), 1)
        self.set_browser(True)
        return self.browser

    def set_browser(self, on=None):
        if self.browser is None:
            if on is False:
                return
            self.browser_panel()
            return
        if on is None:
            on = self.browser.isHidden()
        if on == (not self.browser.isHidden()):
            return
        size = None
        if on:
            self.set_canvas(False)
            total = self.body_split.width()
            size = int(self.browser.property("last_size") or 0)
            if size < total * 0.4:
                size = int(total * 0.55)
        panels.set_visible(self.body_split, self.browser, on, animated=animations_on() and self.isVisible(), size=size)
        self.b_web.setIcon(icon("herr_espacio_mundo", C["acc"] if on else C["mut"], 18))

    def set_canvas(self, on):
        if on and self.browser is not None and not self.browser.isHidden():
            self.set_browser(False)
        if on == (not self.canvas.isHidden()):
            return
        size = None
        if on:                                   # la primera vez, algo más de la mitad: es donde está el trabajo
            total = self.body_split.width()
            size = int(self.canvas.property("last_size") or 0)
            if size < total * 0.35:              # nunca se abre como una tira estrecha
                size = int(total * 0.52)
        panels.set_visible(self.body_split, self.canvas, on, animated=animations_on() and self.isVisible(), size=size)

    def _tray(self):
        self.tray = QSystemTrayIcon(make_icon(), self)
        self.tray.setToolTip(APP_NAME)
        m = QMenu()
        m.addAction(icon("acc_abrir_externo"), tr("Mostrar"), self._show)
        m.addAction(icon("mat_comentario"), tr("Pregunta rápida"), lambda: QTimer.singleShot(250, self.quick_open))
        m.addAction(icon("trans_detener"), tr("Detener agente"), lambda: (self.chat.stop(), self.code.chat.stop()))
        m.addSeparator()
        m.addAction(icon("ui_cerrar"), tr("Salir"), self.quit_app)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(lambda r: r == QSystemTrayIcon.Trigger and self._show())
        self.tray.show()

    def _show(self):
        self.showMaximized()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        self._quitting = True
        self.close()

    def restart_app(self):
        """Cierra Jayth y lo vuelve a abrir (p. ej. tras cambiar el idioma de la interfaz). Si hay una actualización
        lista, se instala de paso."""
        self._restart = True
        self.quit_app()
        if self.isVisible():                 # el usuario canceló la salida (archivos sin guardar, agente trabajando)
            self._restart = False
            self._quitting = False

    def restart_to_update(self):
        """«Reiniciar para actualizar»: cierra Jayth, instala la versión descargada y lo vuelve a abrir."""
        if any(s.run for s in core.SESSIONS.values()):
            return QMessageBox.information(self, APP_NAME, tr("Espera a que el agente termine antes de actualizar."))
        self.restart_app()

    def notify_pending(self, text, ts):
        if core.SET.snapshot().get("notifications", True) and not self.isActiveWindow() and ts > time.time() - 10:
            self.tray.showMessage(APP_NAME, tr("El agente espera tu aprobación: %s") % text, QSystemTrayIcon.Information, 6000)

    # ---- modos
    def current_panel(self):
        return self.code.chat if self.mode == "code" else self.chat

    def set_mode(self, mode, save=True):
        self.mode = mode
        self.seg_chat.setChecked(mode == "chat")
        self.seg_code.setChecked(mode == "code")
        for b, m in ((self.seg_chat, "chat"), (self.seg_code, "code")):
            b.setIcon(icon("mat_comentario" if m == "chat" else "cod_terminal", C["tx"] if m == mode else C["mut"], 14))
        self.side_stack.setCurrentIndex(0 if mode == "chat" else 1)
        self.pages.setCurrentIndex(0 if mode == "chat" else 1)
        if save:
            core.SET.update({"app_mode": mode})
        self._sig_chat = self._sig_code = None
        self.refresh_lists()
        self.sync()

    # ---- barra lateral: oculta por defecto. Al pasar el raton por ☰ se asoma flotando sobre el contenido y se
    #      cierra sola cuando el raton sale; un clic en ☰ la deja fija (integrada) hasta volver a pulsarlo.
    def side_pinned(self):
        return not self._peek and self.hsplit.indexOf(self.side) >= 0 and not self.side.isHidden()

    def _init_peek(self):
        self._peek = False
        self._peek_away = 0.0
        self._peek_open_t = QTimer(self, singleShot=True, interval=140, timeout=self._peek_open)
        self._peek_t = QTimer(self, interval=90, timeout=self._peek_check)
        self.b_expand.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if obj is getattr(self, "b_expand", None):
            if ev.type() == QEvent.Enter and not self.side_pinned():
                self._peek_open_t.start()
            elif ev.type() == QEvent.Leave:
                self._peek_open_t.stop()
        return super().eventFilter(obj, ev)

    def _peek_geometry(self):
        g = self.hsplit.geometry()
        top = self.head.height() + 1                    # debajo de la cabecera: ☰ sigue a la vista y se puede pulsar
        w = int(self.side.property("last_size") or 264)
        return QRect(g.x(), g.y() + top, min(w, max(200, g.width() - 120)), g.height() - top)

    def _peek_open(self):
        if self._peek or self.side_pinned() or not self.isVisible():
            return
        self._peek = True
        self.side.hide()
        self.side.setParent(self.centralWidget())        # sale del Splitter: flota sin mover el resto
        self.side_top.hide()
        self.side.setProperty("peek", True)
        theme.restyle(self.side)             # borde a la derecha para separarla del contenido (sin sombra: es mas ligero)
        self.side.setGeometry(self._peek_geometry())
        self.side.show()
        self.side.raise_()
        self._peek_away = 0.0
        self._peek_t.start()

    def _peek_check(self):
        if not self._peek:
            return self._peek_t.stop()
        self.side.setGeometry(self._peek_geometry())    # sigue a la ventana si cambia de tamaño
        if QApplication.activePopupWidget() or QApplication.activeModalWidget():
            self._peek_away = 0.0                       # menu contextual o dialogo abierto desde la barra
            return
        pos = QCursor.pos()
        inside = self.side.rect().contains(self.side.mapFromGlobal(pos)) or \
            (self.b_expand.isVisible() and self.b_expand.rect().contains(self.b_expand.mapFromGlobal(pos)))
        if inside:
            self._peek_away = 0.0
        elif not self._peek_away:
            self._peek_away = time.time()
        elif time.time() - self._peek_away > 0.3:      # un pequeño margen por si el raton se sale sin querer
            self._peek_close()

    def _peek_close(self):
        if not self._peek:
            return
        self._peek_t.stop()
        self._peek = False
        self.side.hide()
        self.side.setProperty("peek", False)
        theme.restyle(self.side)
        self.side_top.show()
        self.hsplit.insertWidget(0, self.side)          # vuelve a su sitio (oculta) para cuando se fije
        self.hsplit.setStretchFactor(0, 0)
        self.hsplit.setStretchFactor(1, 1)

    def toggle_sidebar(self):
        if self._peek:                                  # estaba asomada: el clic la deja fija
            self._peek_close()
            self.set_sidebar(True)
            return
        self._peek_open_t.stop()
        self.set_sidebar(not self.side_pinned())

    def set_sidebar(self, on):
        """Fija u oculta la barra lateral conservando el ancho que le diste."""
        if self._peek:
            self._peek_close()
        if on == self.side_pinned():
            return
        self.b_expand.setVisible(not on)
        if not on and self._side_sized:
            w = self.hsplit.sizes()[0]
            if w > 0:
                self.side.setProperty("last_size", w)
        panels.set_visible(self.hsplit, self.side, on, animated=animations_on() and self.isVisible() and self._side_sized)
        self._save_layout_soon()

    def toast(self, text, action=None, on_action=None, ms=7000, icon_name="est_info", color=None):
        return Toast(self.centralWidget(), text, action, on_action, ms, icon_name, color)

    # ---- novedades: versiones nuevas de Jayth y de los modelos
    def check_news(self, manual=False):
        cfg = core.SET.snapshot()
        if cfg.get("auto_update_check", True) or manual:
            run_bg(updater.check_app, lambda r: self._got_app_news(r, manual))
        if cfg.get("model_news", True) and cfg["models"]:
            run_bg(lambda: updater.check_models(cfg["models"], set(cfg.get("model_news_seen") or [])), self._got_model_news)

    def _got_app_news(self, r, manual):
        if isinstance(r, Exception):
            if manual:
                self.toast(tr("No pude consultar si hay actualizaciones (¿sin internet?)."), icon_name="est_aviso", color=C["warn"])
            return
        if not r:
            if getattr(self, "_upd_state", None) != "ready":
                self._set_update_state(None)
            if manual:
                self.toast(tr("Tienes la última versión de %s.") % APP_NAME, icon_name="ui_check", color=C["ok"])
            return
        self.update_info = r
        if not updater.can_update_in_background():          # copias de git o del instalador de código: como siempre
            self._set_update_state("available")
            self.update_btn.setToolTip(tr("Versión del %s: %s") % (r["date"], r["message"]))
            self.toast(tr("Hay una versión nueva de %s (%s): «%s».") % (APP_NAME, r["date"], r["message"]), tr("Actualizar"), self.install_update,
                       12000, "acc_descargar")
            return
        d = updater.ready()
        if d and d.get("version") == r.get("version"):
            return self._update_ready(d, announce=manual)
        if getattr(self, "_upd_state", None) == "downloading":
            return
        if manual or core.SET.snapshot().get("auto_install_updates", True):
            return self._download_update()                   # en segundo plano: no interrumpe nada
        self._set_update_state("available")
        self.update_btn.setToolTip(tr("Versión del %s: %s") % (r["date"], r["message"]))
        self.toast(tr("Hay una versión nueva de %s (%s): «%s».") % (APP_NAME, r["date"], r["message"]), tr("Descargar"),
                   self._download_update, 12000, "acc_descargar")

    # ---- actualización en segundo plano: disponible → descargando → lista («Reiniciar para actualizar»)
    def _set_update_state(self, st):
        self._upd_state = st
        b = self.update_btn
        b.setVisible(st is not None)
        if st == "available":
            b.setText(tr("  Actualización disponible"))
            b.setIcon(icon("acc_descargar", C["acc"], 15))
        elif st == "downloading":
            b.setText(tr("  Descargando actualización… %d %%") % getattr(self, "_upd_pct", 0))
            b.setIcon(icon("acc_descargar", C["acc"], 15))
            b.setToolTip(tr("Se descarga en segundo plano; puedes seguir trabajando."))
        elif st == "ready":
            b.setText(tr("  Reiniciar para actualizar"))
            b.setIcon(icon("acc_refrescar", C["acc"], 15))

    def _update_clicked(self):
        st = getattr(self, "_upd_state", None)
        if st == "ready":
            return self.restart_to_update()
        if st == "downloading":
            return self.toast(tr("La actualización se está descargando en segundo plano; puedes seguir trabajando."), ms=4000,
                              icon_name="acc_descargar")
        if updater.can_update_in_background():
            return self._download_update()
        self.install_update()

    def _download_update(self):
        info = self.update_info
        if not info or getattr(self, "_upd_state", None) == "downloading":
            return
        self._upd_pct = 0

        def progress(done, total, phase):            # en el hilo de la descarga: solo se guarda el porcentaje
            if total:
                self._upd_pct = min(100, int(done * 100 / total))

        def finished(r):
            self._upd_timer.stop()
            if isinstance(r, Exception):
                self._set_update_state("available")
                self.update_btn.setToolTip(tr("No se pudo descargar la actualización (%s). Pulsa para reintentar.") % r)
                return
            self._update_ready(r, announce=True)
        self._set_update_state("downloading")
        self._upd_timer = QTimer(self, interval=800, timeout=lambda: self._set_update_state("downloading"))
        self._upd_timer.start()
        run_bg(lambda: updater.download_update(info, progress), finished)

    def _update_ready(self, d, announce):
        self._set_update_state("ready")
        on_exit = core.SET.snapshot().get("auto_install_updates", True)
        self.update_btn.setToolTip((tr("La versión %s está lista. Se instalará sola al cerrar %s; pulsa aquí para instalarla ahora.")
                                    if on_exit else tr("La versión %s está lista. Pulsa aquí para instalarla (%s se reiniciará).")) % (d["version"], APP_NAME))
        if announce:
            self.toast((tr("La versión %s de %s está lista. Se instalará al cerrar la app, o reinicia ahora.") if on_exit
                        else tr("La versión %s de %s está lista para instalar.")) % (d["version"], APP_NAME),
                       tr("Reiniciar ahora"), self.restart_to_update, 12000, "acc_refrescar")

    def _update_on_start(self):
        """Al abrir: aviso de que se acaba de actualizar, o una versión que ya estaba descargada de antes."""
        if not updater.can_update_in_background():
            return
        done = updater.just_updated()
        if done:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            url = done.get("url") or "https://github.com/%s/releases/tag/v%s" % (updater.REPO, done["version"])
            self.toast(tr("%s se actualizó a la versión %s.") % (APP_NAME, done["version"]), tr("Novedades"),
                       lambda: QDesktopServices.openUrl(QUrl(url)), 10000, "ui_check", C["ok"])
            return
        d = updater.ready()
        if d:
            self.update_info = dict(d, asset=None)
            self._update_ready(d, announce=False)

    def _got_model_news(self, news):
        if isinstance(news, Exception) or not news:
            return
        self.model_news = news
        seen = list(core.SET.snapshot().get("model_news_seen") or [])
        for n in news:
            self.toast(tr("Nuevo modelo disponible: %s (más reciente que tu %s).") % (n["title"], n["for"]), tr("Ver"),
                       lambda r=n["repo"]: self.setup("model", r), 15000, "ia_controlador")
            seen.append(n["repo"])
        core.SET.update({"model_news_seen": seen[-50:]})

    def install_update(self):
        if updater.can_update_in_background():                # app empaquetada: siempre por el camino sin interrupciones
            return self.restart_to_update() if updater.ready() else self._download_update()
        info = self.update_info
        if not info:
            return
        if any(s.run for s in core.SESSIONS.values()):
            return QMessageBox.information(self, APP_NAME, tr("Espera a que el agente termine antes de actualizar."))
        if QMessageBox.question(self, tr("Actualizar %s") % APP_NAME, tr("Versión del %s:\n«%s»\n\n%s se cerrará, se actualizará y volverá a abrirse. "
                                "Tus conversaciones, ajustes y modelos se conservan. ¿Actualizar ahora?") % (info["date"], info["message"], APP_NAME)) \
                != QMessageBox.StandardButton.Yes:
            return
        def done(r):
            if isinstance(r, Exception):
                return QMessageBox.warning(self, APP_NAME, tr("No se pudo actualizar: %s") % r)
            ok, how = r
            if not ok:
                return QMessageBox.warning(self, APP_NAME, how)
            if how == "restart":
                updater.restart()
            self.quit_app()
        if updater.installed()["kind"] == "frozen":          # hay que descargar el paquete: en segundo plano
            self.update_btn.setEnabled(False)
            self.update_btn.setText(tr("  Descargando actualización…"))
            self.toast(tr("Descargando la versión nueva. %s se reiniciará al terminar.") % APP_NAME, ms=6000, icon_name="acc_descargar")
            run_bg(lambda: updater.apply_update(info), done)
        else:
            done(updater.apply_update(info))

    def focus_search(self):
        if self.mode != "chat":
            self.set_mode("chat")
        if not self.side_pinned():           # con el teclado la barra se fija (al asomarse se cerraria sin el raton)
            self.set_sidebar(True)
        self.search.show()
        self.search.setFocus()
        self.search.selectAll()

    def _escape(self):
        if self._peek:
            self._peek_close()
            return
        if self.search.isVisible() and (self.search.hasFocus() or self.search.text()):
            self.search.clear()
            self.search.hide()

    def new_conversation(self):
        if self.mode == "code" and not self.code.project:
            return self.new_project()
        p = self.current_panel()
        p.open_session(None)
        p.input.setFocus()

    # ---- proyectos
    def new_project(self):
        d = ProjectDialog(self)
        if d.exec() and d.result_project:
            self.select_project(d.result_project["id"])

    def open_folder_project(self):
        path = QFileDialog.getExistingDirectory(self, tr("Abrir carpeta como proyecto"), os.path.expanduser("~"))
        if not path:
            return
        cfg = core.SET.snapshot()
        found = next((p for p in cfg["projects"] if os.path.normcase(p["path"]) == os.path.normcase(os.path.normpath(path))), None)
        p = found or core.SET.add_project(os.path.basename(os.path.normpath(path)), path)
        self.select_project(p["id"])

    def select_project(self, pid):
        core.SET.update({"active_project": pid})
        self.code.set_project(core.project(core.SET.snapshot(), pid))
        if self.mode != "code":
            self.set_mode("code")
        self._sig_code = None
        self.refresh_lists()
        self.sync()

    def _project_menu(self, pos):
        it = self.plist.itemAt(pos)
        if not it or not it.data(Qt.UserRole):
            return
        p = core.project(core.SET.snapshot(), it.data(Qt.UserRole))
        m = QMenu(self)
        a_edit = m.addAction(icon("acc_renombrar"), tr("Editar proyecto…"))
        a_os = m.addAction(icon("act_carpeta_abierta"), SHOW_IN)
        m.addSeparator()
        a_rm = m.addAction(icon("ui_cerrar", C["bad"]), tr("Quitar de la lista"))
        a = m.exec(self.plist.mapToGlobal(pos))
        if a == a_edit:
            d = ProjectDialog(self, p)
            if d.exec() and self.code.project and self.code.project["id"] == p["id"]:
                self.code.project = None
                self.code.set_project(d.result_project)
        elif a == a_os:
            osys.open_path(p["path"])
        elif a == a_rm:
            if QMessageBox.question(self, tr("Quitar proyecto"), tr("¿Quitar «%s» de la lista? La carpeta y sus archivos no se borran.") % p["name"]) == QMessageBox.StandardButton.Yes:
                core.SET.remove_project(p["id"])
                cfg = core.SET.snapshot()
                self.code.set_project(core.project(cfg, cfg["active_project"]))
        self._sig_code = None
        self.refresh_lists()
        self.sync()

    # ---- listas laterales
    def on_chat_changed(self):
        self._sig_chat = self._sig_code = None
        self.refresh_lists()
        self.sync()

    def refresh_lists(self):
        q = self.search.text().strip().lower() if self.search.isVisible() else ""
        ss = [s for s in core.sessions_for(None) if not q or q in s.search_text()]
        sig = (q, [(s.id, s.title, s.run is not None) for s in ss], self.chat.sid)
        if sig != self._sig_chat:
            self._sig_chat = sig
            fill_history(self.list, ss, self.chat.sid, q, folded=self.folded)
        cfg = core.SET.snapshot()
        pid = self.code.project["id"] if self.code.project else None
        cs = core.sessions_for(pid) if pid else []
        sig = ([(p["id"], p["name"]) for p in cfg["projects"]], pid, [(s.id, s.title, s.run is not None) for s in cs], self.code.chat.sid)
        if sig != self._sig_code:
            self._sig_code = sig
            self.plist.clear()
            for p in cfg["projects"]:
                it = QListWidgetItem(icon("act_carpeta", C["acc"] if p["id"] == pid else C["mut"], 14), p["name"])
                it.setData(Qt.UserRole, p["id"])
                it.setToolTip(p["path"])
                self.plist.addItem(it)
                if p["id"] == pid:
                    it.setSelected(True)
            if not cfg["projects"]:
                e = QListWidgetItem(tr("Aún no hay proyectos"))
                e.setFlags(Qt.NoItemFlags)
                e.setForeground(QGuiApplication.palette().placeholderText())
                self.plist.addItem(e)
            fill_history(self.clist, cs, self.code.chat.sid, empty_text=tr("Las conversaciones del proyecto aparecerán aquí"), folded=self.folded)

    def _history_click(self, it, panel):
        """Clic en el historial: abre la conversación o pliega/despliega su grupo (Hoy, Ayer…)."""
        grp = it.data(GROUP_ROLE)
        if grp:
            self.folded.symmetric_difference_update({grp})
            self._sig_chat = self._sig_code = None
            self.refresh_lists()
            self._save_layout_soon()
        elif it.data(Qt.UserRole):
            panel.open_session(it.data(Qt.UserRole))

    def _fold_section(self, lst, on):
        lst.setVisible(on)
        self._save_layout_soon()

    def _session_menu(self, lst, pos, panel):
        it = lst.itemAt(pos)
        if not it or not it.data(Qt.UserRole):
            return
        s = core.SESSIONS.get(it.data(Qt.UserRole))
        m = QMenu(self)
        a_ren = m.addAction(icon("acc_renombrar"), tr("Renombrar"))
        a_del = m.addAction(icon("acc_eliminar", C["bad"]), tr("Borrar"))
        a = m.exec(lst.mapToGlobal(pos))
        if a == a_ren:
            self._rename(s)
        elif a == a_del:
            self._delete(s, panel)

    def _rename(self, s):
        if not s:
            return
        t, ok = QInputDialog.getText(self, tr("Renombrar"), tr("Nuevo nombre:"), text=s.title)
        if ok and t.strip():
            s.rename(t)          # a partir de aqui el modelo ya no cambia el nombre
            self.on_chat_changed()

    def _delete(self, s, panel):
        if not s:
            return
        if QMessageBox.question(self, tr("Borrar conversación"), tr("¿Borrar «%s»? No se puede deshacer.") % s.title) == QMessageBox.StandardButton.Yes:
            s.delete()
            if panel.sid == s.id:
                panel.open_session(None)
            self.on_chat_changed()

    # ---- modelo y estado
    def _fill_model_menu(self, m=None):
        """Menu del modelo: tus modelos (variante a la derecha), Esfuerzo ›, Más modelos › y el interruptor del motor."""
        m = m if m is not None else self.model_menu
        m.clear()
        m.setToolTipsVisible(True)
        cfg = core.SET.snapshot()
        ext = cfg["llm_mode"] == "external"
        grp = QActionGroup(m)
        for md in cfg["models"]:
            caps = core.model_caps(md, compute=False)     # lo guardado (se lee del archivo en segundo plano al abrir Jayth)
            right = " · ".join(x for x in (core.model_quant(md), core.caps_text(caps, short=True)) if x)
            a = m.addAction(core.model_title(md) + ("\t" + right if right else ""))
            a.setCheckable(True)
            a.setChecked(not ext and md["id"] == cfg["active_model"])
            a.setToolTip(md.get("path", "") + (("\n" + core.caps_text(caps)) if caps else ""))
            grp.addAction(a)
            a.triggered.connect(lambda _=False, i=md["id"]: self._use_model(i))
        # modelos por API de los servicios guardados (OpenAI, Claude, Gemini, Ollama…)
        from . import providers as PV
        provs = PV.saved(cfg)
        for p in provs:
            for name in p.get("models") or []:
                a = m.addAction("%s\t%s" % (name.split("/")[-1] if len(name) > 34 else name, p["name"]))
                a.setCheckable(True)
                a.setChecked(ext and cfg.get("external_provider") == p["id"] and cfg["external_model"] == name)
                a.setToolTip("%s · %s" % (name, p["url"]))
                grp.addAction(a)
                a.triggered.connect(lambda _=False, p=p, n=name: (PV.use(p, n), setattr(self, "llm", {"state": "off"}), self.poll(), self.sync()))
        if (ext or cfg["external_model"]) and not provs:
            a = m.addAction(tr("%s\tservidor externo") % (cfg["external_model"] or cfg["external_url"]))
            a.setCheckable(True)
            a.setChecked(ext)
            grp.addAction(a)
            a.triggered.connect(lambda: (core.LLM_MGR.stop(), core.SET.update({"llm_mode": "external"}), self.poll()))
        if not cfg["models"] and not (ext or cfg["external_model"]) and not provs:
            na = m.addAction(tr("Aún no tienes modelos"))
            na.setEnabled(False)
        m.addSeparator()
        # esfuerzo: cuanto razona el modelo antes de responder
        eff = core.effort_of(cfg)
        label = next(l for k, l, d in core.EFFORTS if k == eff)
        em = m.addMenu(icon("ia_memoria"), tr("Esfuerzo\t%s") % label)
        em.setToolTipsVisible(True)
        eg = QActionGroup(em)
        hints = {"low": tr("más rápido"), "medium": tr("equilibrado"), "high": tr("más preciso")}
        for k, l, d in core.EFFORTS:
            a = em.addAction("%s\t%s" % (l, hints[k]))
            a.setCheckable(True)
            a.setChecked(k == eff)
            a.setToolTip(d)
            eg.addAction(a)
            a.triggered.connect(lambda _=False, k=k: (core.set_effort(k), self.sync()))
        more = m.addMenu(icon("acc_anadir"), tr("Más modelos"))
        more.addAction(icon("acc_descargar"), tr("Descargar o añadir un modelo…"), lambda: self.setup("model"))
        more.addAction(icon("ia_controlador"), tr("Gestionar modelos…"), self.models)
        more.addAction(icon("hub_conectar"), tr("Modelos por API (OpenAI, Claude, Gemini, Ollama…)…"), self.providers)
        if not ext:
            m.addSeparator()
            sec = m.addAction(tr("Motor"))
            sec.setEnabled(False)
            st = self.llm.get("state", "off")
            on = m.addAction(tr("Modelo encendido") if st != "loading" else tr("Cargando el modelo…"))
            on.setCheckable(True)
            on.setChecked(st in ("ready", "loading"))
            on.setToolTip(tr("Encendido, el modelo ocupa memoria y responde al momento; apagado, libera la memoria."))
            on.triggered.connect(lambda _=False: self.toggle_llm())

    def toggle_temp(self, on):
        """Empieza (o abandona) un chat temporal en el modo Chat."""
        p = self.chat
        if p.busy:
            self.b_temp.setChecked(not on)
            return self.toast(tr("Espera a que el agente termine."), icon_name="est_aviso", color=C["warn"])
        p.open_session(None)                 # conversación nueva (y, si había un chat temporal, se descarta)
        if on:
            p.temp_next = True
            p.open_session(None)             # redibuja el estado vacío…
            p.temp_next = True               # …que vuelve a apagar la marca
            if p.empty is not None:
                p.empty.hide()
                p.empty.deleteLater()
            p.empty = p.add(p._empty_state())
        p.input.setFocus()
        self.sync()

    # ---- tareas programadas
    def _init_tasks(self):
        self._task_runs = {}                 # id de conversación -> nombre de la tarea en marcha
        self._task_queue = []                # tareas pedidas a mano que esperan a que el modelo esté listo
        self.task_t = QTimer(self, interval=20000, timeout=self._tick_tasks)
        self.task_t.start()
        QTimer.singleShot(6000, self._tick_tasks)

    def tasks(self):
        from .tasks_ui import TasksDialog
        TasksDialog(self).exec()

    def _model_ready(self):
        """True si se puede lanzar al agente ya; si el modelo local está apagado, lo enciende y devuelve False."""
        cfg = core.SET.snapshot()
        if cfg["llm_mode"] == "external":
            return True
        st = core.LLM_MGR.status().get("state")
        if st == "ready":
            return True
        if st == "off":
            core.LLM_MGR.start()
            self.llm = {"state": "loading"}
            self.sync()
        return False

    def run_task(self, t, manual=False):
        """Lanza una tarea programada. Devuelve un texto de error o None."""
        from . import schedule as SC
        if not core.SET.ready():
            return tr("Aún no hay un modelo configurado.")
        if not self._model_ready():
            if manual and t["id"] not in self._task_queue:
                self._task_queue.append(t["id"])
            return tr("El modelo se está encendiendo: la tarea empezará en cuanto esté listo.") if manual else "esperando al modelo"
        s, err = SC.start(t)
        if err:
            return err
        self._task_runs[s.id] = t["name"]
        self.task_t.setInterval(4000)        # mientras haya tareas en marcha se mira más a menudo
        self._sig_chat = None
        self.refresh_lists()
        return None

    def _tick_tasks(self):
        from . import schedule as SC
        # 1) avisar de las que han terminado
        for sid, name in list(self._task_runs.items()):
            s = core.SESSIONS.get(sid)
            if s is None or s.run is None:
                self._task_runs.pop(sid)
                if s is not None:
                    self.toast(tr("Tarea «%s» terminada.") % name, tr("Ver resultado"), lambda sid=sid: self.open_task_result(sid),
                               ms=15000, icon_name="ui_check", color=C["ok"])
                    if core.SET.snapshot().get("notifications", True) and not self.isActiveWindow():
                        self.tray.showMessage(APP_NAME, tr("Tarea «%s» terminada. Ábrelo para ver el resultado.") % name, QSystemTrayIcon.Information, 8000)
                    self._sig_chat = None
                    self.refresh_lists()
        if not self._task_runs:
            self.task_t.setInterval(20000)
        # 2) lanzar las que tocan (de una en una: el modelo local atiende una conversación cada vez)
        if self._task_runs or any(s.run is not None for s in core.SESSIONS.values()):
            return
        pending = [t for t in SC.all_tasks() if t["id"] in self._task_queue] + SC.due()
        for t in pending[:1]:
            err = self.run_task(t)
            if err is None and t["id"] in self._task_queue:
                self._task_queue.remove(t["id"])
            elif err and err != "esperando al modelo":
                self.toast(tr("No se pudo ejecutar la tarea «%s»: %s") % (t["name"], err), icon_name="est_aviso", color=C["warn"])
                SC.update(t["id"], enabled=False)

    def open_task_result(self, sid):
        if sid not in core.SESSIONS:
            return
        self._show()
        if self.mode != "chat":
            self.set_mode("chat")
        self.chat.open_session(sid)

    def assistants(self, tab=0):
        from .assistants import AssistantsDialog
        AssistantsDialog(self, tab).exec()
        for p in (self.chat, self.code.chat):
            p._render_thumbs()

    def providers(self):
        from .providers import ProvidersDialog
        ProvidersDialog(self).exec()
        self.poll()
        self.sync()

    def _use_model(self, mid):
        cfg = core.SET.snapshot()
        if cfg["active_model"] == mid and cfg["llm_mode"] == "local":
            return
        core.LLM_MGR.stop()
        core.SET.update({"active_model": mid, "llm_mode": "local"})
        self.llm = {"state": "off"}
        self.sync()
        self.warn_if_not_agent(core.active_model(core.SET.snapshot()))
        if QMessageBox.question(self, APP_NAME, tr("¿Encender el nuevo modelo ahora?")) == QMessageBox.StandardButton.Yes:
            self.toggle_llm()

    def warn_if_not_agent(self, m):
        """Avisa si el modelo elegido no sabe usar herramientas (el agente no podrá actuar con él)."""
        caps = core.model_caps(m, compute=False) if m else None
        if caps and not caps.get("tools"):
            self.toast(tr("«%s» no usa herramientas: podrás conversar con él, pero el agente no podrá trabajar con archivos, "
                       "comandos ni la web. Para eso elige un modelo agéntico.") % core.model_title(m),
                       tr("Ver modelos"), lambda: self.setup("model"), ms=15000, icon_name="est_aviso", color=C["warn"])

    # --- modelos que cambiaron de sitio (ver relocate.py)
    def _init_models(self):
        from . import relocate as R
        self._deep_busy = self._deep_done = False
        self._start_when_found = False
        self._told = set()
        self._drives = set(R.drives())
        self.models_t = QTimer(self, interval=60000, timeout=self._tick_models)
        self.models_t.start()
        # al abrir: enlazar lo que se movió, añadir lo que se haya pegado en la carpeta de modelos y leer los tipos
        QTimer.singleShot(2500, lambda: self.check_models("quick" if R.problems(core.SET.snapshot()) else "guess",
                                                          add_new=True, then=lambda rep: self._caps_in_background()))

    def check_models(self, level="quick", folders=None, add_new=False, explicit=False, then=None, deep=True):
        """Busca en segundo plano los modelos que no están en su sitio y avisa de lo que haya arreglado. Si con la
        búsqueda rápida no aparecen, sigue con todos los discos (una vez por sesión)."""
        from . import relocate as R

        def done(rep):
            if isinstance(rep, Exception):
                rep = {"pending": True, "error": str(rep)}
            self._models_report(rep)
            if rep.get("missing") and deep and level != "deep" and not self._deep_busy and not self._deep_done:
                self._deep_busy = True
                act = core.active_model(core.SET.snapshot())
                if act and (rep.get("by_id") or {}).get(act["id"], ("",))[0] == "missing":
                    self.toast(tr("Busco «%s» en todos tus discos; puede tardar unos minutos. Si sabes dónde está, indícalo en "
                               "Modelos → Localizar…") % (core.model_title(act) or act.get("name")), tr("Ver modelos"), self.models,
                               ms=12000, icon_name="acc_buscar", color=C["acc"])
                run_bg(lambda: R.run("deep"), self._deep_finished)
            if then:
                then(rep)
        run_bg(lambda: R.run(level, folders, add_new, explicit), done)

    def _deep_finished(self, rep):
        self._deep_busy, self._deep_done = False, True
        if isinstance(rep, Exception):
            return
        self._models_report(rep, final=True)

    def _models_report(self, rep, final=False):
        from . import relocate as R
        if rep.get("error"):
            return
        text = R.summary(rep)
        if text:
            self.toast(text, tr("Ver modelos"), self.models, ms=14000, icon_name="ui_check", color=C["ok"])
            self.sync()
            if self._start_when_found and core.SET.ready():
                self._start_when_found = False
                self.toggle_llm()
        # lo que sigue pendiente se cuenta una sola vez (no en cada revisión)
        news = {}
        for t, d in rep.get("copying") or []:
            news[("copying", t)] = {"copying": [(t, d)]}
        for t, d in rep.get("offline") or []:
            news[("offline", t)] = {"offline": [(t, d)]}
        if final:
            for t in rep.get("missing") or []:
                news[("missing", t)] = {"missing": [t]}
        for k, part in news.items():
            if k not in self._told:
                self._told.add(k)
                self.toast(R.pending_text(part), tr("Ver modelos"), self.models, ms=16000, icon_name="est_aviso", color=C["warn"])
        for k in list(self._told):        # si se resolvió, se volverá a avisar si reaparece
            if k[0] in ("copying", "offline") and not any(t == k[1] for t, _ in rep.get(k[0]) or []) and not rep.get("error"):
                self._told.discard(k)

    def _tick_models(self):
        """Cada minuto, solo si falta algo: mira los sitios evidentes; si se conectó un disco, lo recorre entero."""
        from . import relocate as R
        if not R.problems(core.SET.snapshot()):
            return
        now = set(R.drives())
        new, self._drives = now - self._drives, now
        copying = any(k[0] == "copying" for k in self._told)
        self.check_models("quick" if copying else "guess", folders=sorted(new) or None, deep=False)

    def fix_not_ready(self):
        """Lo que haya que hacer para poder usar el modelo: buscar su archivo si se movió, o el asistente."""
        cfg = core.SET.snapshot()
        why = core.not_ready(cfg)
        if why == "model_file":
            m = core.active_model(cfg)
            self._start_when_found = True
            self.toast(tr("Busco «%s»: ya no está en %s.") % (core.model_title(m) or m.get("name"), os.path.dirname(m.get("path", "")) or tr("su carpeta")),
                       ms=6000, icon_name="acc_buscar", color=C["acc"])
            return self.check_models("quick")
        return self.setup()

    def _caps_in_background(self):
        """Lee del GGUF el tipo de los modelos que aún no lo tienen guardado (o cuyo archivo cambió)."""
        todo = [m for m in core.SET.snapshot()["models"] if os.path.isfile(m.get("path", "")) and core.model_caps(m, compute=False) is None]
        if todo:
            run_bg(lambda: [core.model_caps(m) for m in todo], lambda r: None)

    def poll(self):
        self.refresh_lists()
        if self._polling:
            return
        self._polling = True

        def work():
            try:
                st = core.LLM_MGR.status()
            except Exception as e:
                st = {"state": "off", "error": str(e)}
            self.sig.status.emit(st)
        threading.Thread(target=work, daemon=True).start()

    def _got_status(self, st):
        self._polling = False
        self.llm = st
        cfg = core.SET.snapshot()
        mine = core.LLM_MGR.mine()
        # precalentamiento: en cuanto el modelo propio esta listo, procesar instrucciones y herramientas en segundo plano
        if st.get("state") == "ready" and mine and cfg["warmup"] and not core.LLM_MGR.warm and cfg["llm_mode"] == "local":
            threading.Thread(target=core.LLM_MGR.warmup, daemon=True).start()
        # apagar el modelo tras un tiempo sin uso (libera memoria)
        idle = int(cfg.get("idle_unload") or 0)
        if idle and mine and st.get("state") == "ready" and not any(s.run for s in core.SESSIONS.values()) \
                and time.time() - core.LAST_USE[0] > idle * 60:
            core.LLM_MGR.stop()
            self.llm = {"state": "off"}
            if cfg.get("notifications", True):
                self.tray.showMessage(APP_NAME, tr("Apagué el modelo tras %d minutos sin uso para liberar memoria.") % idle, QSystemTrayIcon.Information, 5000)
        self.sync()

    def sync(self):
        cfg = core.SET.snapshot()
        st = self.llm.get("state", "off")
        ext = cfg["llm_mode"] == "external"
        m = core.active_model(cfg)
        name = (tr("Externo · %s") % (cfg["external_model"] or cfg["external_url"])) if ext else (core.model_title(m) if m else tr("Sin modelo"))
        self.model_btn.setText(name + "  ⌄")
        self.model_btn.setToolTip(("%s · %s · %s" % (core.model_title(m), core.model_quant(m), m.get("path", ""))) if (m and not ext) else tr("Elegir modelo"))
        col, txt = {"ready": (C["ok"], tr("Listo · externo") if ext else tr("Listo · local")), "loading": (C["warn"], tr("Cargando…"))}.get(st, (C["faint"], tr("Apagado")))
        if st == "ready" and self.llm.get("warm") == "warming":
            col, txt = C["warn"], tr("Preparando el agente…")
        self.status_lbl.setText("<span style='color:%s'>●</span> <span style='color:%s'>%s</span>" % (col, C["mut"], txt))
        panel = self.current_panel()
        s = panel.session()
        if self.mode == "code" and self.code.project:
            self.title.setText(self.code.project["name"] + (" · " + s.title if s and s.events else ""))
        else:
            self.title.setText((tr("Chat temporal") if s.temp else s.title) if s and s.events else ("" if self.mode == "chat" else CODE_NAME))
        temp_on = self.mode == "chat" and (bool(getattr(self.chat, "temp_next", False)) or bool(self.chat.session() and self.chat.session().temp))
        self.b_temp.setVisible(self.mode == "chat")
        self.b_temp.setChecked(temp_on)
        self.b_folder.setToolTip(tr("Carpeta de trabajo: %s") % panel.workspace())
        in_code = self.mode == "code" and self.code.project is not None
        for b, w, ico in ((self.b_tree, self.code.left, "pan_explorador"), (self.b_term, self.code.term, "pan_consola"),
                          (self.b_agent, self.code.chat, "mat_comentario")):
            b.setVisible(in_code)
            b.setIcon(icon(ico, C["acc"] if not w.isHidden() else C["faint"], 18))
        un = (cfg.get("user_name") or "").strip()     # nunca se usa el usuario de Windows: el perfil es generico
        self.user_lbl.setText(un or tr("Tu perfil"))
        if un:
            self.avatar.setPixmap(QPixmap())
            self.avatar.setText("".join(p[0] for p in un.split()[:2]).upper())
        else:
            self.avatar.setText("")
            self.avatar.setPixmap(pix("ia_controlador", C["acc"], 15))
        waiting = self.chat.waiting + self.code.chat.waiting
        self.setWindowTitle((tr("● Esperando tu aprobación · %s") if waiting else "%s") % (CODE_NAME if self.mode == "code" else APP_NAME))
        for p in (self.chat, self.code.chat):
            p.sync()

    def toggle_llm(self):
        if not core.SET.ready():
            return self.fix_not_ready()
        if self.llm.get("state", "off") == "off":
            err = core.LLM_MGR.start()
            if err:
                return QMessageBox.warning(self, APP_NAME, err)
            self.llm = {"state": "loading"}
        else:
            core.LLM_MGR.stop()
            self.llm = {"state": "off"}
        self.sync()
        QTimer.singleShot(800, self.poll)

    def setup(self, start="welcome", repo=None):
        w = SetupWizard(self, start=start, repo=repo)
        if w.exec() and w.start_llm:
            core.LLM_MGR.stop()
            core.LLM_MGR.start()
        self.poll()
        self.sync()

    def models(self):
        ModelsDialog(self).exec()
        self.poll()
        self.sync()

    def settings(self, page="General"):
        b = core.SET.snapshot()
        SettingsDialog(self, page).exec()
        a = core.SET.snapshot()
        if a.get("quick_hotkey") != b.get("quick_hotkey"):
            self._apply_hotkey(tell=True)
        if a.get("models_dir") != b.get("models_dir") and a.get("models_dir"):
            # nueva carpeta de modelos: enlazar los que se movieron allí y añadir los que ya hubiera dentro
            self.check_models("guess", folders=[a["models_dir"]], add_new=True, explicit=True)
        if (a["theme"], a["font_scale"]) != (b["theme"], b["font_scale"]):
            return self._swap_window()
        self.poll()
        self.sync()
        for p in (self.chat, self.code.chat):
            if p.empty is not None:
                p.open_session(p.sid)

    def _swap_window(self):
        """Aplica un tema nuevo recreando la ventana (los iconos se tiñen al crearse)."""
        cfg = core.SET.snapshot()
        theme.apply(QApplication.instance(), cfg["theme"], cfg["font_scale"])
        chat_sid, code_sid = self.chat.sid, self.code.chat.sid
        self.code.term.stop()
        w = Main()
        w.chat.open_session(chat_sid)
        if w.code.project:
            w.code.chat.open_session(code_sid)
        w.setGeometry(self.geometry())
        w.showMaximized() if self.isMaximized() else w.show()
        _dark_titlebar(w)
        QApplication.instance()._main = w
        self._swapping = True
        self.tray.hide()
        self.close()

    def closeEvent(self, e):
        if self._swapping:
            return e.accept()
        if core.SET.snapshot().get("close_to_tray") and not getattr(self, "_quitting", False) and QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()       # sigue funcionando en la bandeja; «Salir» del menú la cierra de verdad
            if not getattr(self, "_tray_told", False):
                self._tray_told = True
                self.tray.showMessage(APP_NAME, tr("%s sigue funcionando aquí. Para cerrarlo, usa «Salir».") % APP_NAME, QSystemTrayIcon.Information, 4000)
            return e.ignore()
        if self.code.tabs.has_dirty():
            r = QMessageBox.question(self, tr("Cambios sin guardar"), tr("Hay archivos con cambios sin guardar. ¿Guardarlos antes de salir?"),
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel:
                return e.ignore()
            if r == QMessageBox.StandardButton.Save:
                for t in self.code.tabs.tabs():
                    if t.dirty:
                        t.save()
        busy = [s for s in core.SESSIONS.values() if s.run]
        if busy and QMessageBox.question(self, tr("Salir"), tr("El agente está trabajando. ¿Detenerlo y salir?")) != QMessageBox.StandardButton.Yes:
            return e.ignore()
        self.code.term.stop()
        core.shutdown()
        self.tray.hide()
        e.accept()
        reopen = getattr(self, "_restart", False)
        try:
            upd = updater.ready() if updater.can_update_in_background() else None
        except Exception:
            upd = None
        try:
            if upd and (reopen or core.SET.snapshot().get("auto_install_updates", True)):
                # la versión descargada se instala ahora que Jayth se cierra: en silencio al salir, o con una ventanita
                # «Actualizando…» y volviendo a abrirlo si se pidió reiniciar
                updater.install_when_closed(upd, reopen=reopen)
                reopen = False
        except Exception:
            pass
        if reopen:                                   # reinicio sin actualización (p. ej. cambio de idioma)
            from PySide6.QtCore import QProcess
            argv = osys.launch_argv()
            QProcess.startDetached(argv[0], argv[1:])
        QApplication.quit()


def _dark_titlebar(w):
    """Con la barra nativa (si se desactiva la integrada) al menos se pinta con los colores del tema."""
    if not getattr(w, "frameless", False):
        theme.titlebar_colors(w)


def install_qt_language(app):
    """Textos propios de Qt en el idioma de la interfaz: menús contextuales (Copiar, Seleccionar todo…) y botones
    estándar (Sí/No). En inglés no hace falta nada: es el idioma original de Qt."""
    from PySide6.QtCore import QTranslator, QLibraryInfo
    if i18n.LANG == "en":
        return True
    folders = [QLibraryInfo.path(QLibraryInfo.TranslationsPath)]
    if osys.FROZEN:
        folders.append(os.path.join(getattr(sys, "_MEIPASS", paths.APP_DIR), "PySide6", "translations"))
    name = {"pt": "qtbase_pt_BR"}.get(i18n.LANG, "qtbase_" + i18n.LANG)     # Qt trae el portugués de Brasil
    for d in folders:
        qt_tr = QTranslator(app)
        if qt_tr.load(name, d):
            app.installTranslator(qt_tr)
            app._qt_tr = qt_tr
            return True
    return False


def selftest(app):
    """Comprobación del paquete (se usa en la compilación automática): carga todo y cierra con código 0 si está bien."""
    import importlib.util, platform as _pf
    from . import hardware as HW, provision as P, __version__
    checks = {}

    def ok(name, fn):
        try:
            r = fn()
            checks[name] = "ok" if r in (None, True) else str(r)
        except Exception as e:
            checks[name] = "ERROR: %r" % e
    ok("logo", lambda: not theme.logo(64).isNull() or "logo vacío")
    ok("icons", lambda: not theme.pix("ia_controlador").isNull() or "faltan iconos")
    ok("icon", lambda: os.path.isfile(paths.ICON) or "falta " + paths.ICON)
    ok("modules", lambda: [m for m in ("certifi", "pypdf") + (() if osys.WIN else ("mss", "pynput")) if not importlib.util.find_spec(m)] or None)
    ok("certifi", lambda: os.path.isfile(__import__("certifi").where()) or "sin certificados")
    # buscar modelos movidos y leer su tipo (se importan dentro de funciones: comprobar que van en el paquete)
    ok("models_relocate", lambda: (importlib.import_module("jayth.relocate").drives(), importlib.import_module("jayth.gguf")) and None)
    # respuestas con código, comandos y rutas; resaltado de sintaxis; capa de control del ratón
    ok("chat_view", lambda: None if [s[0] for s in CV.split_md("Hola `C:\\x`\n```bash\nls\n```\n```py\nx = 1\n```")] == ["md", "cmd", "code"]
       and CV.CodeBlock() and OV.ControlOverlay() else "trozos mal partidos")
    ok("browser", lambda: importlib.import_module("jayth.browser").to_url("ejemplo.com").toString() == "https://ejemplo.com" and None)
    # vistas del editor (Markdown, Office, PDF, imágenes) y el explorador con sus iconos
    ok("doc_views", lambda: None if importlib.import_module("jayth.docview").DOC_KIND and not importlib.import_module("jayth.explorer").file_icon("a.py").isNull()
       else "faltan las vistas del editor")
    ok("hardware", lambda: HW.summary(HW.detect()) and None)
    ok("engine", lambda: bool(P.LLAMA_PATTERNS) or "sin motores")
    ok("qt_language", lambda: install_qt_language(app) or "sin traducción de Qt al idioma " + i18n.LANG)
    ok("i18n", lambda: i18n.LANG == "es" or len(i18n.CATALOG) > 500 or "falta el catálogo de " + i18n.LANG)
    ok("tools", lambda: len(T.TOOLS) >= 25 or "faltan herramientas")
    ok("shell", lambda: "JAYTH_OK" in __import__("subprocess").run(osys.shell_argv("echo JAYTH_OK"), capture_output=True, text=True,
                                                                     timeout=60, **osys.popen_kwargs()).stdout or "la terminal no responde")
    def documents():
        import tempfile
        from . import office
        d = tempfile.mkdtemp(prefix="jayth_st_")
        try:
            for ext in (".docx", ".xlsx", ".pptx", ".pdf"):
                office.create(os.path.join(d, "prueba" + ext), "# Prueba\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n- uno")
            return all(os.path.getsize(os.path.join(d, "prueba" + e)) > 300 for e in (".docx", ".xlsx", ".pptx", ".pdf")) or "documentos vacíos"
        finally:
            shutil.rmtree(d, ignore_errors=True)
    ok("documents", documents)
    from . import canvas as _canvas
    web = bool(_canvas.web_view_class())
    # en Linux el navegador integrado depende de bibliotecas del sistema: si faltan, el lienzo abre el navegador normal
    ok("canvas", lambda: web or not (osys.WIN or osys.MAC) or "falta el navegador integrado (Qt WebEngine)")

    def web_page():                           # comprobación a fondo (solo si se pide): carga una página de verdad
        from PySide6.QtCore import QEventLoop, QUrl
        v = _canvas.web_view_class()()
        done, loop = [], QEventLoop()
        v.loadFinished.connect(lambda good: (done.append(good), loop.quit()))
        v.setHtml("<html><body><h1>hola</h1><script>document.title='js-ok'</script></body></html>", QUrl("https://lienzo.jayth.local/"))
        v.resize(400, 300)
        v.show()
        QTimer.singleShot(25000, loop.quit)
        loop.exec()
        end = time.time() + 3
        while v.title() != "js-ok" and time.time() < end:
            app.processEvents()
        title = v.title()
        v.close()
        return (bool(done) and done[0] and title == "js-ok") or "la página no cargó (cargada=%s, título=%r)" % (done, title)
    if os.environ.get("JAYTH_SELFTEST_WEB") == "1":
        ok("web_page", web_page)
    os.environ["JAYTH_NO_HOTKEY"] = "1"       # la comprobación no registra atajos globales

    def window():
        w = Main()
        w.tray.hide()
        w.poll_t.stop()
        w.news_t.stop()
    ok("window", window)

    def voice_parts():                        # las piezas de Qt para la voz deben venir en el paquete
        import importlib
        bad = []
        for m in ("PySide6.QtTextToSpeech", "PySide6.QtMultimedia"):
            try:
                importlib.import_module(m)
            except Exception as e:
                bad.append("%s: %s" % (m, e))
        # en Linux dependen de bibliotecas de sonido del sistema (PulseAudio): si faltan, la voz se desactiva sola
        if bad and not (osys.WIN or osys.MAC):
            report_extra["voice_missing"] = bad
            return None
        return "; ".join(bad) or None
    report_extra = {}
    ok("voice_modules", voice_parts)
    # que haya voces o micrófono depende del equipo (en los servidores de compilación no hay): solo se informa
    from . import voice as _vc
    report = {"version": __version__, "os": osys.os_label(), "arch": _pf.machine(), "frozen": osys.FROZEN, "web_canvas": web,
              "voices": _vc.Speaker.available(), "microphone": _vc.Recorder.available(), "checks": checks}
    report.update(report_extra)
    text = json.dumps(report, ensure_ascii=False, indent=1)
    try:
        print(text, flush=True)
    except Exception:
        pass
    with open(os.path.join(paths.HOME, "selftest.json"), "w", encoding="utf-8") as f:
        f.write(text)
    core.shutdown()
    return 0 if all(v == "ok" for v in checks.values()) else 1


def main():
    if osys.WIN:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Jayth.App")   # icono propio en la barra de tareas
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("jayth")        # Linux: enlaza la ventana con jayth.desktop (icono correcto en el dock/panel)
    install_qt_language(app)
    from .widgets import install_screen_fit
    install_screen_fit(app)                  # ningún diálogo más grande que la pantalla
    cfg = core.SET.snapshot()
    theme.apply(app, cfg["theme"], cfg["font_scale"])
    app.setWindowIcon(make_icon())
    app.setQuitOnLastWindowClosed(False)
    core.load_sessions()
    if "--selftest" in sys.argv:
        sys.exit(selftest(app))
    w = Main()
    app._main = w
    _dark_titlebar(w)
    if "--minimized" in sys.argv and QSystemTrayIcon.isSystemTrayAvailable():   # arranque con el sistema: queda en la bandeja
        w.tray.showMessage(APP_NAME, tr("%s está listo en la bandeja del sistema.") % APP_NAME, QSystemTrayIcon.Information, 3000)
    else:
        w.showMaximized()                  # siempre a pantalla completa
    if core.SET.load_error:
        QTimer.singleShot(500, lambda: QMessageBox.warning(w, APP_NAME, core.SET.load_error))
    why = core.not_ready(cfg)
    if why == "model_file":           # el modelo se movió: lo busca la revisión del arranque (no hace falta el asistente)
        w._start_when_found = bool(cfg["autostart_llm"] or "--start-llm" in sys.argv)
    elif why and "--no-wizard" not in sys.argv:
        QTimer.singleShot(300, w.setup)
    elif (cfg["autostart_llm"] or "--start-llm" in sys.argv) and cfg["llm_mode"] == "local":
        core.LLM_MGR.start()
        w.llm = {"state": "loading"}
        w.sync()
    sys.exit(app.exec())
