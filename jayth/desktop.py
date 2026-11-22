# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Aplicacion de escritorio Jayth (Qt). Dos modos:
- Chat: conversaciones para cualquier tarea.
- Code: proyectos con arbol de archivos, editor, terminal y el agente trabajando dentro de la carpeta del proyecto."""
import os, re, sys, json, uuid, time, shutil, threading, ctypes, datetime, subprocess
from PySide6.QtCore import (Qt, QTimer, Signal, QObject, QSize, QPoint, QRect, QRectF, QEvent, QPropertyAnimation, QEasingCurve,
                            QParallelAnimationGroup)
from PySide6.QtGui import QPixmap, QImage, QKeySequence, QShortcut, QGuiApplication, QActionGroup, QCursor, QTransform, QFont, QIcon, QTextCursor, QColor
from PySide6.QtWidgets import (QApplication, QWidgetAction, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
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

MODE_LABEL = {k: re.split("[:：]", v)[0] for k, v in A.MODES.items()}       # japonés y chino usan «：»
EFFORT_CHIP = {"low": tr("esfuerzo bajo"), "medium": tr("esfuerzo medio"), "high": tr("esfuerzo alto")}
MODE_ICON = {"readonly": "est_bloqueado", "plan": "ui_menu_hamburguesa", "ask": "ui_ayuda", "edits": "acc_renombrar", "auto": "hub_lanzar"}
HINT = {"readonly": tr("Se ejecuta en tu equipo. En Solo lectura no cambia nada"),
        "plan": tr("Se ejecuta en tu equipo. Primero propone un plan; no cambia nada hasta que lo apruebes"),
        "ask": tr("Se ejecuta en tu equipo. Revisa cada acción antes de permitirla"),
        "edits": tr("Se ejecuta en tu equipo. Edita archivos sin preguntar; lo demás te lo pregunta"),
        "auto": tr("Se ejecuta en tu equipo. En Automático actúa sin preguntar, salvo lo peligroso")}
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
    b.setAccessibleName(tip.split("  ·  ")[0] if tip else (name or ico))   # los lectores de pantalla dicen qué es (sin el atajo)
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


class Veil(Clickable):
    """Velo semitransparente sobre el contenido (p. ej. detrás de la barra lateral que se asoma); un clic lo cierra."""

    def __init__(self, parent, alpha=60):
        super().__init__(parent)
        self.alpha = alpha

    def paintEvent(self, e):
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, self.alpha))
        p.end()


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

    def __init__(self, parent, text, action=None, on_action=None, ms=7000, icon_name="est_info", color=None, above=None):
        super().__init__(parent)
        self.setObjectName("toast")
        self.above = above                    # función que da la altura (en la ventana) por encima de la cual debe quedar
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
        y = p.height() - self.height() - 120 - dy
        try:                                   # el cuadro de mensaje crece al escribir: el aviso queda siempre por encima
            top = self.above() if self.above else None
            if top is not None:
                y = min(y, int(top) - self.height() - 12)
        except Exception:
            pass
        self.move(p.width() - self.width() - 22, max(48, y))

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
        self.setToolTip(tr("Clic para verla en grande"))

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
            show_image(self, self.path)


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


def fill_history(lst, sessions, current, query="", empty_text=tr("Aún no hay conversaciones"), folded=()):
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
    if p in ("", ".", "./", ".\\"):          # la propia carpeta de trabajo: quien llama pone «la carpeta de trabajo»
        return ""
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
    "search_knowledge": (tr("buscar en tu conocimiento"), tr("Buscó en tu conocimiento"), lambda a: tr("«%s»") % _q(a.get("query"), 50)),
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
    "jayth_guide": (tr("consultar la guía de Jayth"), tr("Consultó la guía de Jayth"), lambda a: (tr("«%s»") % _q(a.get("topic"), 50)) if a.get("topic") else ""),
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
    "generate_image": (tr("crear la imagen"), tr("Creó la imagen"), lambda a: tr("«%s»") % _q(a.get("prompt"), 50)),
    "connect_service": (tr("proponer conectar"), tr("Propuso conectar"), lambda a: _svc_name(a.get("service"))),
    "replace_in_files": (tr("reemplazar en varios archivos"), tr("Reemplazó en varios archivos"),
                         lambda a: tr("«%s» → «%s»") % (_q(a.get("pattern"), 24), _q(a.get("replacement"), 24))),
    "delegate": (tr("encargar a un ayudante"), tr("Encargó a un ayudante"), lambda a: tr("«%s»") % _q(a.get("title") or a.get("task"), 50)),
    "undo_changes": (tr("deshacer sus cambios"), tr("Deshizo sus cambios"), lambda a: ""),
}


def _svc_name(cid):
    from . import conectores as CN
    c = CN.find(str(cid or "").lower())
    return c["name"] if c else str(cid or "")
BROWSER_NAV = {"back": (tr("volver atrás"), tr("Volvió atrás"), tr("Volviendo atrás…")), "forward": (tr("ir adelante"), tr("Fue adelante"), tr("Yendo adelante…")),
               "reload": (tr("recargar la página"), tr("Recargó la página"), tr("Recargando la página…")),
               "down": (tr("bajar por la página"), tr("Bajó por la página"), tr("Bajando por la página…")),
               "up": (tr("subir por la página"), tr("Subió por la página"), tr("Subiendo por la página…")),
               "top": (tr("ir al principio de la página"), tr("Fue al principio de la página"), tr("Yendo al principio…")),
               "bottom": (tr("ir al final de la página"), tr("Fue al final de la página"), tr("Yendo al final…"))}
WINDOW_ACT = {"maximize": (tr("maximizar la ventana"), tr("Maximizó la ventana"), tr("Maximizando la ventana")),
              "minimize": (tr("minimizar la ventana"), tr("Minimizó la ventana"), tr("Minimizando la ventana")),
              "restore": (tr("restaurar la ventana"), tr("Restauró la ventana"), tr("Restaurando la ventana")),
              "close": (tr("cerrar la ventana"), tr("Cerró la ventana"), tr("Cerrando la ventana")),
              "move": (tr("mover la ventana"), tr("Movió la ventana"), tr("Moviendo la ventana")),
              "resize": (tr("cambiar el tamaño de la ventana"), tr("Cambió el tamaño de la ventana"), tr("Cambiando el tamaño de la ventana"))}


# mientras se ejecuta: «Escribiendo calculadora.py…», «Ejecutando python app.py…»
GERUND = {
    "read_file": tr("Leyendo"), "write_file": tr("Escribiendo"), "create_document": tr("Creando el documento"), "run_python": tr("Analizando con Python"),
    "show_canvas": tr("Preparando el lienzo"), "edit_file": tr("Editando"), "list_dir": tr("Explorando"), "search_files": tr("Buscando"),
    "run_command": tr("Ejecutando"), "open_target": tr("Abriendo"), "wait": tr("Esperando"), "web_fetch": tr("Leyendo"), "web_search": tr("Buscando en la web"),
    "download_file": tr("Descargando"), "screenshot": tr("Capturando la pantalla"), "click": tr("Haciendo clic"), "move_mouse": tr("Moviendo el ratón"),
    "scroll": tr("Desplazando"), "type_text": tr("Escribiendo"), "press_keys": tr("Pulsando"), "list_windows": tr("Revisando las ventanas"),
    "focus_window": tr("Activando la ventana"), "multi_edit": tr("Editando"), "move_path": tr("Moviendo"), "delete_path": tr("Enviando a la papelera"),
    "command_output": tr("Revisando la salida de"), "stop_command": tr("Deteniendo"), "read_document": tr("Leyendo el documento"),
    "view_image": tr("Mirando la imagen"), "jayth_guide": tr("Consultando la guía de Jayth"), "remember": tr("Guardando en la memoria"), "forget": tr("Olvidando"), "schedule_task": tr("Programando la tarea"),
    "list_tasks": tr("Consultando las tareas programadas"), "cancel_task": tr("Quitando la tarea"), "use_skill": tr("Usando la habilidad"),
    "ui_elements": tr("Leyendo la interfaz de"), "click_element": tr("Pulsando"), "drag": tr("Arrastrando"),
    "browser_open": tr("Abriendo"), "browser_read": tr("Leyendo la página"), "browser_click": tr("Pulsando"), "browser_type": tr("Escribiendo"),
    "browser_screenshot": tr("Capturando la página"), "generate_image": tr("Creando la imagen"), "connect_service": tr("Proponiendo conectar"),
    "search_knowledge": tr("Buscando en tu conocimiento"), "replace_in_files": tr("Reemplazando en varios archivos"),
    "delegate": tr("Un ayudante trabaja en"), "undo_changes": tr("Deshaciendo sus cambios"),
}


def _lead(phase, inf, past, ger):
    """La acción según la fase: pendiente («Quiere leer»), denegada, en curso («Leyendo») o hecha («Leyó»)."""
    if phase == "pending":
        return tr("Quiere %s") % inf
    if phase == "denied":
        return tr("No se permitió %s") % inf
    if phase == "err":                          # falló: nunca en pasado, que diría que se hizo
        return tr("No se pudo %s") % inf
    return ger if phase == "run" else past


def describe_parts(name, args, phase):
    """(verbo, objeto): «Escribió» + «calculadora.py». El objeto se resalta en la interfaz.
    phase: pending, denied, run, done o err."""
    args = args or {}
    if name.startswith("mcp__"):           # herramienta de un conector MCP: «Usó servidor › herramienta»
        parts = name.split("__")
        srv, tool = (parts[1].replace("_", " "), parts[2].replace("_", " ")) if len(parts) > 2 else (name, "")
        return _lead(phase, tr("usar"), tr("Usó"), tr("Usando")), "%s › %s%s" % (srv, tool, "…" if phase == "run" else "")
    if name == "browser_nav":
        inf, past, ger = BROWSER_NAV.get(str(args.get("action", "")).lower(), (tr("navegar"), tr("Navegó"), tr("Navegando…")))
        return _lead(phase, inf, past, ger), ""
    if name == "window_action":
        inf, past, ger = WINDOW_ACT.get(str(args.get("action", "")).lower(),
                                        (tr("manejar la ventana"), tr("Manejó la ventana"), tr("Manejando la ventana")))
        return _lead(phase, inf, past, ger), tr("«%s»%s") % (_q(args.get("window"), 40), "…" if phase == "run" else "")
    if name == "clipboard":
        w = str(args.get("action", "")).lower() in ("write", "set", "copy")
        inf, past, ger = (tr("copiar al portapapeles"), tr("Copió al portapapeles"), tr("Copiando al portapapeles")) if w else                          (tr("leer el portapapeles"), tr("Leyó el portapapeles"), tr("Leyendo el portapapeles") + "…")
        return _lead(phase, inf, past, ger), (tr("«%s»") % _q(args.get("text"), 40)) if w else ""
    if name == "screenshot" and args.get("zoom"):
        return _lead(phase, tr("ampliar una zona de la pantalla"), tr("Amplió una zona de la pantalla"),
                     tr("Ampliando una zona de la pantalla…")), ""
    if name == "screenshot" and args.get("window"):            # captura de una sola ventana
        return _lead(phase, tr("capturar la ventana"), tr("Capturó la ventana"), tr("Capturando la ventana")),             tr("«%s»%s") % (_q(args["window"], 40), "…" if phase == "run" else "")
    if name == "run_command" and args.get("background") and phase in ("run", "done"):
        return (tr("Iniciando en segundo plano") if phase == "run" else tr("Inició en segundo plano")), _q(args.get("command", "")) + ("…" if phase == "run" else "")
    inf, past, obj = STEP.get(name, (name, name, lambda a: ""))
    try:
        o = obj(args)
    except Exception:
        o = ""
    if phase == "run":
        lead = GERUND.get(name, inf[:1].upper() + inf[1:])
        return (lead, o + "…") if o else (lead + "…", "")
    return _lead(phase, inf, past, ""), o


def join_step(lead, obj):
    """Une la acción y su objeto como lo escribe cada idioma («Leyó main.py»; en alemán «Gelesen: main.py»).
    Devuelve el texto y dónde empieza el objeto (para resaltarlo), o -1 si no hay objeto."""
    if not obj:
        return lead.strip(), -1
    fmt = tr("%s %s")
    return fmt % (lead, obj), len(fmt % (lead, ""))


def describe(name, args, phase):
    return join_step(*describe_parts(name, args, phase))[0]


def about_to(name):
    """«Va a escribir»: el modelo ya eligió la herramienta y está escribiendo sus datos (un archivo largo puede tardar)."""
    if name.startswith("mcp__"):
        parts = name.split("__")
        inf = tr("usar %s") % (parts[1].replace("_", " ") if len(parts) > 1 else name)
    else:
        inf = {"browser_nav": tr("navegar"), "window_action": tr("manejar la ventana"), "clipboard": tr("usar el portapapeles"),
               "use_tools": tr("cargar más herramientas")}.get(name) or STEP.get(name, (name,))[0]
    return tr("Va a %s") % inf


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
# nombres de los datos de cada acción como los lee una persona (si no, salía «path:», «query:»… en cualquier idioma)
ARG_LABEL = {"path": tr("ruta"), "url": tr("dirección"), "query": tr("búsqueda"), "command": tr("comando"), "cwd": tr("carpeta"),
             "content": tr("contenido"), "target": tr("destino"), "dest": tr("destino"), "source": tr("origen"),
             "window": tr("ventana"), "title": tr("título"), "text": tr("texto"), "keys": tr("teclas"), "index": tr("número"),
             "name": tr("nombre"), "filter": tr("filtro"), "code": tr("código"), "question": tr("pregunta"),
             "options": tr("opciones"), "pattern": tr("patrón"), "timeout": tr("tiempo máximo"), "action": tr("acción"),
             "prompt": tr("descripción"), "button": tr("botón"), "max_results": tr("resultados"), "args": tr("argumentos"),
             "items": tr("tareas"), "fact": tr("dato"), "topic": tr("tema"), "reason": tr("motivo"), "service": tr("servicio"),
             "task": tr("tarea"), "language": tr("idioma"), "seconds": tr("segundos")}


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
        # el detalle (los datos de la acción y su resultado) se monta la primera vez que se despliega: casi nunca se
        # mira, y en una conversación larga eran cientos de cajas de texto ocultas que costaban segundos al abrirla
        self._filled = False
        self._later = []
        self.details.hide()
        v.addWidget(self.details)
        self.approval = None
        if self.pending:
            self.approval = QFrame()
            self.approval.setObjectName("approval")
            av = QVBoxLayout(self.approval)
            av.setContentsMargins(12, 10, 12, 10)
            if ev.get("danger"):
                av.addWidget(TextView(tr("Acción delicada: revisa bien el detalle antes de permitirla. Esta se confirma siempre, también "
                                         "en el modo automático."), "plain", color=C["warn"], size="9pt"))
            if ev.get("account"):
                av.addWidget(TextView(tr("Actúa en tu cuenta de %s: puede publicar, enviar o gastar créditos.") % ev["account"], "plain",
                                      color=C["warn"], size="9pt"))
            bw = QWidget()
            row = FlowLayout(bw)
            cat = T.CATEGORIES.get(ev["category"], ev["category"])
            opts = [(tr("Permitir"), "primary", "allow")]
            if not ev.get("danger") and not ev.get("account"):     # lo delicado se confirma cada vez: sin «Siempre…»
                opts.append((tr("Siempre «%s» aquí") % cat.lower(), None, "allow_category"))
            opts.append((tr("Denegar"), "danger", "deny"))
            for text, kind, dec in opts:
                b = btn(text, kind)
                b.clicked.connect(lambda _=False, d=dec: self._decide(d, on_decide))
                row.addWidget(b)
            av.addWidget(bw)
            # «no, y haz esto otro»: se deniega y el agente recibe tu indicación (como en los agentes de escritorio actuales)
            self.instead = QLineEdit()
            self.instead.setPlaceholderText(tr("O dile qué hacer en su lugar y pulsa Intro…"))
            self.instead.setAccessibleName(tr("Qué hacer en su lugar"))
            self.instead.returnPressed.connect(lambda: self.instead.text().strip() and
                                               self._decide("deny:" + self.instead.text().strip(), on_decide))
            av.addWidget(self.instead)
            wrap = QWidget()
            wl = QVBoxLayout(wrap)
            wl.setContentsMargins(30, 2, 6, 8)
            wl.addWidget(self.approval)
            v.addWidget(wrap)
            self.approval_wrap = wrap
            self.open_details()
            self._set("pending")
        elif ev["approval"] == "blocked":
            self._set("blocked")
        else:
            self._set("run")

    def fill(self):
        """Monta el detalle si aún no lo está: primero los datos de la acción y luego lo que haya llegado después."""
        if self._filled:
            return
        self._filled = True
        self._args(self.ev["name"], self.ev.get("args") or {})
        later, self._later = self._later, []
        for make in later:
            self.dl.addWidget(make())

    def add_detail(self, make):
        """Añade una pieza al detalle: ya, si está montado; si no, cuando se despliegue."""
        if self._filled:
            self.dl.addWidget(make())
        else:
            self._later.append(make)

    def open_details(self):
        self.fill()
        self.details.show()

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
                    self.dl.addWidget(kv(ARG_LABEL.get(k, k), ""))
                    self.dl.addWidget(mono(val[:20000], None, 220))
                else:
                    self.dl.addWidget(kv(ARG_LABEL.get(k, k), val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)))

    def _set(self, phase):
        self.phase = phase
        tool = CV.tool_icon(self.ev["name"])
        # pendiente de tu permiso: en ámbar, como lo que espera algo de ti (en verde parecía hecho)
        ico, col = {"pending": ("est_aviso", C["warn"]), "run": (tool, C["acc"]), "ok": (tool, C["mut"]),
                    "err": ("est_error", C["bad"]), "denied": ("est_bloqueado", C["bad"]), "blocked": ("est_bloqueado", C["faint"])}[phase]
        self.st_icon.set_icon(ico, col)
        live = phase == "run" and self.ev.get("ts", 0) > time.time() - 30
        self.st_icon.set_active(live)             # el arco gira mientras se ejecuta
        lead, obj = describe_parts(self.ev["name"], self.ev.get("args"),
                                   {"pending": "pending", "run": "run", "denied": "denied", "err": "err"}.get(phase, "done"))
        if phase == "blocked":
            obj = (tr("%s (bloqueado: solo lectura)") % obj).strip()
        text, at = join_step(lead, obj)
        self.title.setText(text, at)
        self.title.set_active(live)
        self.title.set_color(C["bad"] if phase == "err" else C["mut"], C["tx"])
        self.head.setToolTip(text)
        self._chev()

    def _chev(self):
        # (isHidden y no isVisible: dentro de un resumen plegado nada «es visible», pero el detalle sí puede estar abierto)
        self.chev.setPixmap(pix("ui_chevron_derecha" if self.details.isHidden() else "ui_chevron_abajo", C["faint"], 10))

    def toggle(self):
        opening = self.details.isHidden()
        if opening:
            self.fill()
        self.details.setVisible(opening)
        self._chev()

    def _decide(self, d, cb):
        for b in self.approval.findChildren(QPushButton):
            b.setEnabled(False)
        self.instead.setEnabled(False)
        cb(self.id, d)

    def resolved(self, decision):
        self.pending = False
        if self.approval:
            self.approval_wrap.hide()
        self.details.hide()
        self._set("run" if decision in ("allow", "allow_category") else "denied")
        said = decision[5:].strip() if (decision or "").startswith("deny:") else ""
        if said and getattr(self, "said", None) is None:     # lo que le dijiste que hiciera en su lugar, bajo la acción
            self.said = TextView(tr("Le pediste: «%s»") % said, "plain", color=C["mut"], size="9pt")
            w = QWidget()
            sl = QVBoxLayout(w)
            sl.setContentsMargins(30, 0, 6, 4)
            sl.addWidget(self.said)
            self.layout().insertWidget(1, w)

    def live(self, info):
        """Avance de una acción larga (crear una imagen): un lienzo animado con la fase, el paso y los tiempos, que
        avanzan cada segundo. No se enseñan las capas a medio hacer: la imagen aparece entera al terminar."""
        if info is getattr(self, "_last_info", None):   # sin novedades desde la última vez (llega cada medio segundo)
            return
        self._last_info = info
        if getattr(self, "live_w", None) is None:
            w = QWidget()
            lv = QVBoxLayout(w)
            lv.setContentsMargins(30, 2, 6, 8)
            lv.setSpacing(6)
            self.live_canvas = GenCanvas()
            lv.addWidget(self.live_canvas, 0, Qt.AlignLeft)
            self.layout().insertWidget(1, w)
            self.live_w = w
            fade_in(w, 300)
        self.live_canvas.set_info(info)

    def result(self, ok, text, image):
        if getattr(self, "live_w", None) is not None:
            self.live_w.hide()
            self.live_w.deleteLater()
            self.live_w = None
        if self.ev["name"] == "generate_image":
            image = None                              # la imagen creada se muestra en grande en su tarjeta
        self._set("ok" if ok else ("denied" if self.phase == "denied" else "err"))    # denegada: sigue «No se permitió…»
        if ok and text and self.ev["name"] in ("browser_click", "click_element"):     # «Pulsó el elemento 7» -> «Pulsó «Iniciar sesión»»
            m = re.search(r"«([^»\n]{1,60})»", text.split("\n", 1)[0])
            if m:
                t, at = join_step(tr("Pulsó"), tr("«%s»") % m.group(1))
                self.title.setText(t, at)
                self.head.setToolTip(t)
        denied = self.phase == "denied"           # «No se permitió…» ya lo dice; el texto para el modelo sobra
        if text and not denied:
            self.add_detail(lambda: mono(text, max_h=300))
        if image and self.ev["name"] != "show_canvas":     # (la captura del lienzo es para el modelo: el usuario ya tiene el lienzo)
            # la imagen queda a la vista bajo las acciones (también con el resumen plegado)
            p = os.path.join(paths.IMG_DIR, image)
            if self.box is not None:
                self.box.add_preview(p, self)
            else:
                self.add_detail(lambda: ImageLabel(p))
                self.open_details()
        if not ok and not denied:
            self.open_details()
        if ok and self.ev["name"] == "create_document" and self.box is not None:
            m = re.search(r"documento \w+ (.+?\.(?:docx|xlsx|pptx|pdf)) \(", text or "", re.I)
            if m:
                self.doc_card = self.box.add_doc(m.group(1))
        self._chev()

    def needs_setup(self):
        """La acción no pudo hacerse porque falta instalar algo (el generador de imágenes): aviso, no error."""
        self.details.hide()
        self.st_icon.set_icon("est_aviso", C["warn"])
        self.st_icon.set_active(False)
        t = tr("Para crear la imagen falta instalar el generador de imágenes")
        self.title.setText(t, -1)
        self.title.set_active(False)
        self.title.set_color(C["mut"], C["tx"])
        self.head.setToolTip(t)
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
    "generate_image": (tr("creó una imagen"), tr("creó %d imágenes")),
    "search_knowledge": (tr("buscó en tu conocimiento"), tr("hizo %d búsquedas en tu conocimiento")),
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
    text = parts[0]
    for p in parts[1:-1]:
        text = tr("%s, %s") % (text, p)              # en japonés y chino, con «、»
    if len(parts) > 1:
        text = tr("%s y %s") % (text, parts[-1])
    text = i18n.cjk_spacing(text)
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


# ---------------------------------------------------------------- imágenes del chat: visor superpuesto
GENERATED = {}       # copia interna de una imagen creada -> el archivo real (para «mostrar en la carpeta»)


class Lightbox(QWidget):
    """Una imagen del chat en grande, sobre toda la ventana (como en los programas de chat actuales): fondo oscurecido,
    flechas a los lados si hay varias, contador y un botón de cerrar. Esc o un clic fuera la cierran; ← → cambian."""

    def __init__(self, win, images, start=0):
        super().__init__(win)
        self.images = list(images)
        self.i = max(0, min(start, len(self.images) - 1))
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)
        self._src, self._scaled, self._hot, self._alpha, self._zones = QPixmap(), None, "", 0.0, {}
        self._win = win
        win.installEventFilter(self)
        self.setGeometry(win.rect())
        self._load()
        self.show()
        self.raise_()
        self.setFocus()
        self._t0 = time.time()
        self._fade = QTimer(self, interval=16, timeout=self._step)
        if animations_on():
            self._fade.start()
        else:
            self._alpha = 1.0

    def _step(self):
        self._alpha = min(1.0, (time.time() - self._t0) / 0.16)
        if self._alpha >= 1.0:
            self._fade.stop()
        self.update()

    def _load(self):
        self._src = QPixmap(self.images[self.i]) if self.images else QPixmap()
        self._scaled = None
        self.update()

    def real_path(self):
        p = self.images[self.i] if self.images else ""
        return GENERATED.get(p, p)

    def go(self, d):
        if len(self.images) > 1:
            self.i = (self.i + d) % len(self.images)
            self._load()

    def eventFilter(self, obj, e):
        if obj is self._win and e.type() == QEvent.Resize:
            self.setGeometry(self._win.rect())
            self._scaled = None
        return False

    def _image_rect(self):
        if self._src.isNull():
            return QRect()
        top = self._top()
        mw, mh = max(80, self.width() - 150), max(80, self.height() - top - 110)
        k = min(mw / self._src.width(), mh / self._src.height(), 1.0 if min(self._src.width(), self._src.height()) >= 400 else 2.0)
        w, h = max(1, int(self._src.width() * k)), max(1, int(self._src.height() * k))
        return QRect((self.width() - w) // 2, top + 30 + (self.height() - top - 110 - h) // 2, w, h)

    def _top(self):
        """Alto de la barra de título propia de la ventana: ahí los clics son del sistema (mover la ventana), así que
        el botón de cerrar va por debajo."""
        return 46 if getattr(self._win, "frameless", False) else 0

    def paintEvent(self, e):
        from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(8, 10, 10, int(222 * self._alpha)))
        p.setOpacity(self._alpha)
        r = self._image_rect()
        self._zones = {}
        if not r.isNull():
            dpr = self.devicePixelRatioF() or 1.0
            if self._scaled is None or self._scaled[0] != (r.width(), r.height()):
                pm = self._src.scaled(int(r.width() * dpr), int(r.height() * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                pm.setDevicePixelRatio(dpr)
                self._scaled = ((r.width(), r.height()), pm)
            path = QPainterPath()
            path.addRoundedRect(QRectF(r), 8, 8)
            p.save()
            p.setClipPath(path)
            p.drawPixmap(r.topLeft(), self._scaled[1])
            p.restore()
            self._zones["image"] = r
        else:
            p.setPen(QColor(230, 235, 233))
            p.drawText(self.rect(), Qt.AlignCenter, tr("No se pudo leer la imagen."))

        def round_btn(key, cx, cy, glyph):
            rr = QRect(int(cx - 20), int(cy - 20), 40, 40)
            self._zones[key] = rr
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 60 if self._hot == key else 30))
            p.drawEllipse(rr)
            pen = QPen(QColor(240, 244, 242), 2)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            if glyph == "x":
                p.drawLine(int(cx - 6), int(cy - 6), int(cx + 6), int(cy + 6))
                p.drawLine(int(cx + 6), int(cy - 6), int(cx - 6), int(cy + 6))
            else:
                s = 1 if glyph == ">" else -1
                p.drawLine(int(cx - 3 * s), int(cy - 7), int(cx + 4 * s), int(cy))
                p.drawLine(int(cx + 4 * s), int(cy), int(cx - 3 * s), int(cy + 7))
        round_btn("close", self.width() - 38, self._top() + 34, "x")
        if len(self.images) > 1:
            mid = self._top() + (self.height() - self._top()) / 2 - 10
            round_btn("prev", 38, mid, "<")
            round_btn("next", self.width() - 38, mid, ">")
        # pie: nombre, contador y dos acciones discretas
        f = self.font()
        f.setPointSizeF(9.5)
        p.setFont(f)
        fm = p.fontMetrics()
        name = os.path.basename(self.real_path())
        cap = name + ("   %d / %d" % (self.i + 1, len(self.images)) if len(self.images) > 1 else "")
        y = self.height() - 44
        p.setPen(QColor(236, 240, 238))
        p.drawText(QRect(0, y, self.width(), 20), Qt.AlignCenter, fm.elidedText(cap, Qt.ElideMiddle, self.width() - 200))
        links = [("open", tr("Abrir con su programa")), ("folder", tr("Mostrar en la carpeta"))]
        total = sum(fm.horizontalAdvance(t) for k, t in links) + 28
        x = (self.width() - total) // 2
        for k, t in links:
            w = fm.horizontalAdvance(t)
            rr = QRect(x - 4, y + 20, w + 8, 20)
            self._zones[k] = rr
            p.setPen(QColor(255, 255, 255) if self._hot == k else QColor(170, 182, 176))
            p.drawText(rr, Qt.AlignCenter, t)
            x += w + 28
        p.end()

    def _at(self, pos):
        for k in ("close", "prev", "next", "open", "folder", "image"):
            r = self._zones.get(k)
            if r is not None and r.contains(pos):
                return k
        return ""

    def mouseMoveEvent(self, e):
        hot = self._at(e.position().toPoint())
        hot = "" if hot == "image" else hot
        if hot != self._hot:
            self._hot = hot
            self.setCursor(Qt.PointingHandCursor if hot else Qt.ArrowCursor)
            self.update()

    def mousePressEvent(self, e):
        k = self._at(e.position().toPoint())
        if k == "prev":
            self.go(-1)
        elif k == "next":
            self.go(1)
        elif k == "open":
            osys.open_path(self.real_path())
        elif k == "folder":
            reveal(self.real_path())
        elif k != "image":                       # el botón de cerrar o cualquier punto fuera de la imagen
            self.close()
        e.accept()

    def wheelEvent(self, e):
        if e.angleDelta().y():
            self.go(-1 if e.angleDelta().y() > 0 else 1)
        e.accept()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.close()
        elif e.key() in (Qt.Key_Left, Qt.Key_Up, Qt.Key_PageUp):
            self.go(-1)
        elif e.key() in (Qt.Key_Right, Qt.Key_Down, Qt.Key_PageDown):
            self.go(1)
        else:
            e.accept()

    def closeEvent(self, e):
        try:
            self._win.removeEventFilter(self)
        except RuntimeError:
            pass
        super().closeEvent(e)


def show_image(widget, path):
    """Abre `path` en el visor superpuesto. Si la imagen está en una conversación, las flechas recorren todas las de
    esa conversación, en su orden."""
    if not path or not os.path.isfile(path):
        return None
    win = widget.window()
    group = [path]
    panel = widget
    while panel is not None and not (hasattr(panel, "cl") and hasattr(panel, "sid")):
        panel = panel.parentWidget()
    if panel is not None:
        found = []
        for x in panel.col.findChildren(QLabel):
            q = getattr(x, "path", None)
            if q and isinstance(x, (Preview, ImageLabel)) and os.path.isfile(q):
                try:
                    y = x.mapTo(panel.col, QPoint(0, 0)).y()
                except RuntimeError:
                    continue
                found.append((y, q))
        found.sort(key=lambda t: t[0])
        seen, real = [], set()
        for y, q in found:                         # la misma imagen puede verse dos veces (tarjeta y resumen final)
            key = os.path.normcase(GENERATED.get(q, q))
            if key not in real or q == path:
                if key in real:                    # se queda la que se pulsó
                    seen = [s for s in seen if os.path.normcase(GENERATED.get(s, s)) != key]
                real.add(key)
                seen.append(q)
        if path in seen:
            group = seen
    old = win.findChild(Lightbox)
    if old is not None:
        old.close()
    return Lightbox(win, group, group.index(path))


class GenCanvas(QWidget):
    """Mientras se crea una imagen: un lienzo con su proporción y una animación suave (luces que se mueven y una barra
    de avance), en vez de las capas a medio hacer del generador. Los tiempos avanzan cada segundo."""

    def __init__(self):
        super().__init__()
        self.info = None
        self.setFixedSize(280, 280)
        self._t0 = time.time()
        self._timer = QTimer(self, interval=40 if animations_on() else 500, timeout=self.update)
        self._timer.start()

    def set_info(self, info):
        self.info = info
        w, h = (info.get("size") or (1, 1))
        k = min(300.0 / max(1, w), 230.0 / max(1, h))
        size = QSize(max(120, int(w * k)), max(90, int(h * k)))
        if size != self.size():
            self.setFixedSize(size)
        self.update()

    def paintEvent(self, e):
        import math
        from PySide6.QtGui import QPainter, QColor, QPainterPath, QLinearGradient, QRadialGradient
        from . import imagegen as IG
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 10, 10)
        p.setClipPath(path)
        p.fillPath(path, QColor(C["code"]))
        t = time.time() - self._t0
        acc = QColor(C["acc"])
        for n, (sx, sy, ph, rad, al) in enumerate(((0.9, 0.7, 0.0, 0.75, 70), (0.6, 1.1, 2.1, 0.6, 52), (1.3, 0.5, 4.0, 0.5, 40))):
            cx = r.width() * (0.5 + 0.34 * math.sin(t * 0.45 * sx + ph))
            cy = r.height() * (0.5 + 0.34 * math.cos(t * 0.38 * sy + ph * 1.3))
            g = QRadialGradient(cx, cy, max(r.width(), r.height()) * rad)
            c = QColor(acc) if n != 1 else QColor(C.get("warn", C["acc"]))
            c.setAlpha(al)
            g.setColorAt(0.0, c)
            c2 = QColor(c)
            c2.setAlpha(0)
            g.setColorAt(1.0, c2)
            p.fillRect(r, g)
        # un brillo que recorre el lienzo en diagonal
        x = ((t * 0.28) % 1.6 - 0.3) * r.width()
        sh = QLinearGradient(x - 70, 0, x + 70, 0)
        sh.setColorAt(0.0, QColor(255, 255, 255, 0))
        sh.setColorAt(0.5, QColor(255, 255, 255, 22))
        sh.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(r, sh)
        info = self.info or {}
        f = self.font()
        f.setPointSizeF(10)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(C["tx"]))
        phase = IG.PHASES.get(info.get("phase") or "preparando", IG.PHASES["preparando"])
        if info.get("phase") == "dibujando" and info.get("steps"):
            phase += " · " + tr("paso %d de %d") % (min(info["steps"], (info.get("step") or 0) + 1), info["steps"])
        p.drawText(r.adjusted(10, 0, -10, -18), Qt.AlignCenter | Qt.TextWordWrap, phase)
        f.setBold(False)
        f.setPointSizeF(9)
        p.setFont(f)
        p.setPen(QColor(C["mut"]))
        left = IG.remaining(info)
        line = tr("llevas %s") % IG.clock(IG.elapsed(info)) + (
            (" · " + (tr("quedan ~%s") if info.get("guess") else tr("quedan %s")) % IG.clock(left)) if left is not None else "")
        p.drawText(r.adjusted(10, 26, -10, 0), Qt.AlignCenter, line)
        # barra de avance (cuando se sabe cuánto queda)
        frac = IG.fraction(info)
        bar = QRectF(14, r.height() - 14, r.width() - 28, 4)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 28))
        p.drawRoundedRect(bar, 2, 2)
        if frac > 0:
            p.setBrush(acc)
            p.drawRoundedRect(QRectF(bar.x(), bar.y(), max(4.0, bar.width() * frac), bar.height()), 2, 2)
        p.setClipping(False)
        p.setPen(QColor(C["line"]))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.end()


class ImageCard(QFrame):
    """Imagen creada por el agente: a la vista, con su nombre y medidas debajo. Un clic la abre en grande sobre la
    ventana (ahí están «Abrir con su programa» y «Mostrar en la carpeta»)."""

    def __init__(self, path):
        super().__init__()
        self.setObjectName("docCard")
        self.path = path
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(8)
        v.addWidget(Preview(path, 380, 300), 0, Qt.AlignLeft)
        pm = QImage(path)
        try:
            size = T._human(os.path.getsize(path))
        except OSError:
            size = ""
        sub = ElidedLabel(" · ".join(x for x in (os.path.basename(path), "%d × %d" % (pm.width(), pm.height()) if not pm.isNull() else "", size) if x))
        sub.setObjectName("faint")
        v.addWidget(sub)
        self.setToolTip(path)
        self.setMaximumWidth(400)


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
            show_image(self, self.path)


def reveal(path):
    """Muestra el archivo seleccionado en el Explorador / Finder (o abre su carpeta)."""
    osys.reveal(path)


class StepsBox(QFrame):
    """Acciones seguidas del agente, como líneas del mensaje (sin caja alrededor). Mientras trabaja se ven una a una;
    al terminar, si son varias, se resumen en una línea («Editó 2 archivos y ejecutó un comando  +12 −3 ›») que se
    despliega con un clic. Lo que pensó entre una acción y otra («Pensó 4 s ›») va dentro, entre ellas, en vez de
    repetirse como líneas sueltas en la conversación. Las imágenes que ve y los documentos que crea quedan siempre a la
    vista debajo."""

    def __init__(self):
        super().__init__()
        self.setObjectName("stepsBox")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.v.setSpacing(0)
        self.rows = []
        self.thoughts = []                         # lo que pensó antes de cada acción (bloques sin texto)
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
            self._place_previews()
        self.refresh()

    def add_thought(self, block):
        """Un paso en el que solo pensó y luego actuó: su «Pensó 4 s ›» queda aquí, justo antes de la acción."""
        self.thoughts.append(block)
        self.bv.addWidget(block)
        if self.closed:
            self.closed = False
            self.body.show()
            self.head.hide()

    def refresh(self):
        self.setProperty("pending", any(r.pending for r in self.rows))
        restyle(self)

    def add_preview(self, path, row=None):
        if not (path and os.path.isfile(path)):
            return
        self.images = getattr(self, "images", []) + [path]
        # bajo su acción… salvo que una acción posterior esté esperando tu permiso: su tarjeta no debe moverse bajo el ratón
        waiting = row in self.rows and any(r.pending for r in self.rows[self.rows.index(row) + 1:])
        if row is None or row not in self.rows or waiting:
            self.ev_.addWidget(Preview(path, 300, 180), 0, Qt.AlignLeft)     # miniatura: se ve cómo va quedando
            self.extras.show()
            return
        # la de una acción concreta (una captura): justo debajo de esa acción
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(30, 2, 6, 4)
        h.addWidget(Preview(path, 300, 180), 0, Qt.AlignLeft)
        h.addStretch(1)
        self.row_previews = getattr(self, "row_previews", []) + [(row, wrap)]
        after = row
        for r, w in self.row_previews[:-1]:          # varias de la misma acción: en su orden
            if r is row:
                after = w
        self.bv.insertWidget(self.bv.indexOf(after) + 1, wrap)
        self._place_previews()

    def _place_previews(self):
        """Caja desplegada: cada miniatura bajo su acción. Plegada en una línea: abajo, para que sigan a la vista."""
        folded = not self.body.isVisible() and self.closed
        for row, wrap in getattr(self, "row_previews", []):
            try:
                in_body = self.bv.indexOf(wrap) >= 0
                if folded and in_body:
                    self.bv.removeWidget(wrap)
                    wrap.layout().setContentsMargins(0, 0, 0, 0)
                    self.ev_.addWidget(wrap)
                    self.extras.show()
                elif not folded and not in_body:
                    self.ev_.removeWidget(wrap)
                    wrap.layout().setContentsMargins(30, 2, 6, 4)
                    after = row
                    for r, w in self.row_previews:
                        if r is row and w is not wrap and self.bv.indexOf(w) >= 0:
                            after = w
                    self.bv.insertWidget(self.bv.indexOf(after) + 1, wrap)
            except RuntimeError:
                continue
        if self.ev_.count() == 0:
            self.extras.hide()

    def add_canvas(self, item, on_open):
        self.ev_.addWidget(CanvasCard(item, on_open))
        self.extras.show()

    def add_image(self, path, row=None, copy=None, live=False):
        if path and os.path.isfile(path):
            card = ImageCard(path)
            self.ev_.addWidget(card, 0, Qt.AlignLeft)
            self.images = getattr(self, "images", []) + [path]
            self.cards = getattr(self, "cards", []) + [(card, row, copy)]
            self.extras.show()
            if live:
                fade_in(card, 700)                 # aparece entera, de una vez (no por capas)

    def fold_images(self, shown):
        """Al acabar el turno: las imágenes creadas que ya se ven bajo la respuesta final se pliegan dentro de su
        acción («Creó la imagen …» se despliega con un clic), como el resto de acciones."""
        left = []
        for card, row, copy in getattr(self, "cards", []):
            try:
                if row is not None and copy in shown and card.parent() is not None:
                    self.ev_.removeWidget(card)
                    row.fill()
                    row.dl.addWidget(card)
                    row._chev()
                    continue
            except RuntimeError:
                continue
            left.append((card, row, copy))
        self.cards = left
        if self.ev_.count() == 0:
            self.extras.hide()

    def add_widget(self, w):
        self.ev_.addWidget(w)
        self.extras.show()
        return w

    def add_doc(self, path):
        if path and os.path.isfile(path):
            card = DocCard(path)
            self.ev_.addWidget(card)
            self.extras.show()
            return card
        return None

    def finish(self):
        """El agente pasó a otra cosa: varias acciones terminadas (o una y lo que pensó) se resumen en una línea."""
        if self.closed or not self.rows or len(self.rows) + len(self.thoughts) < 2 or any(r.pending or r.phase == "run" for r in self.rows):
            return
        if len(self.rows) == 1 and self.rows[0].phase != "ok":
            return                                  # una sola acción que falló o no permitiste: su error (o lo que le pediste) a la vista
        self.closed = True
        add = rem = 0
        for r in self.rows:
            if r.phase == "ok" and not getattr(r, "is_undone", False):
                a, d = diff_badge(r.ev["name"], r.ev.get("args") or {})
                add += int(a[1:] or 0)
                rem += int(d[1:] or 0)
        fails = sum(1 for r in self.rows if r.phase in ("err", "denied"))
        self.h_text.setText(summarize_steps(self.rows) if len(self.rows) > 1 else self.rows[0].title.text())
        self.h_text.setToolTip("\n".join(r.title.text() for r in self.rows))
        self.h_add.setText("+%d" % add if add else "")
        self.h_rem.setText("−%d" % rem if rem else "")
        self.h_fail.setText((tr("%d ha fallado") if fails == 1 else tr("%d han fallado")) % fails if fails else "")
        self.h_icon.setPixmap(self._icon_stack(fails))
        self.head.show()
        self.body.hide()
        self._place_previews()
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
        self._place_previews()
        self._chev()


# acciones que cambian archivos (salen en la tarjeta de cambios de la respuesta)
CHANGE_TOOLS = ("write_file", "edit_file", "multi_edit", "replace_in_files", "create_document", "delete_path", "move_path")


def divider(text, icon_name=None, color=None):
    """Una línea de texto tenue centrada entre dos rayas finas (marcas de la conversación)."""
    w = QWidget()
    w.setObjectName("divider")
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 2, 0, 2)
    h.setSpacing(8)
    h.addWidget(hline(), 1)
    if icon_name:
        h.addWidget(pix_label(icon_name, color or C["faint"], 13))
    l = QLabel(text)
    l.setObjectName("faint")
    h.addWidget(l)
    h.addWidget(hline(), 1)
    w.label = l
    return w


def worked_line(seconds, spent=None):
    """«Trabajó durante 3 min 12 s»: la línea que cierra un turno con acciones, debajo de la respuesta final. Con un modelo
    por API añade lo que costó el turno: «· 5,8 M tokens · ≈ 23,40 US$»."""
    text = tr("Trabajó durante %s") % CV.fmt_secs(seconds)
    if spent and (spent.get("i") or spent.get("o")):
        from .providers import tok_short, money
        text += " · " + tr("%s tokens") % tok_short(spent["i"] + spent["o"])
        if spent["sin_precio"] < spent["n"]:
            text += " · " + ("≈ " if spent.get("estimado") else "") + money(spent["usd"])
    return divider(text)


def steer_bubble(ev, compact=False):
    """Lo que escribiste mientras el agente trabajaba, en el punto en que lo vio."""
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(2)
    v.addWidget(user_bubble(ev, compact))
    l = QLabel(tr("Lo escribiste mientras trabajaba; lo vio aquí"))
    l.setObjectName("faint")
    l.setAlignment(Qt.AlignRight)
    v.addWidget(l)
    return w


class ChangesCard(QFrame):
    """Bajo la respuesta: los archivos que el agente cambió en ella, con las líneas añadidas y quitadas, para abrirlos o
    devolverlos uno a uno a como estaban (o todos a la vez)."""

    def __init__(self, files, on_open, on_undo):
        super().__init__()
        self.setObjectName("changesCard")
        self.files = files                         # [{path, add, rem, note, can_undo, undone}]
        self.on_undo = on_undo
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 6, 6, 6)
        v.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 2)
        head.setSpacing(6)
        head.addWidget(pix_label("acc_renombrar", C["mut"], 14))
        n = len(files)
        self.h_text = QLabel((tr("Cambió %d archivo") if n == 1 else tr("Cambió %d archivos")) % n)
        self.h_text.setStyleSheet("color:%s; font-weight:600" % C["mut"])
        head.addWidget(self.h_text)
        add, rem = sum(f["add"] for f in files), sum(f["rem"] for f in files)
        for txt, col in (("+%d" % add if add else "", C["ok"]), ("−%d" % rem if rem else "", C["bad"])):
            if txt:
                l = QLabel(txt)
                l.setStyleSheet("color:%s; font-size:9pt" % col)
                head.addWidget(l)
        head.addStretch(1)
        self.b_all = QPushButton(tr("Deshacer todo"))
        self.b_all.setProperty("kind", "flat")
        self.b_all.setIcon(icon("acc_refrescar", C["mut"], 13))
        self.b_all.setToolTip(tr("Restaura todos los archivos que el agente cambió en esta respuesta"))
        self.b_all.clicked.connect(lambda: self.on_undo(list(self.files)))
        head.addWidget(self.b_all)
        v.addLayout(head)
        self.rows = []
        for f in files:
            row = Clickable()
            row.setObjectName("changeRow")
            row.setAttribute(Qt.WA_StyledBackground, True)
            row.setAttribute(Qt.WA_Hover, True)
            row.setCursor(Qt.PointingHandCursor)
            row.setToolTip(tr("Abrir %s") % f["path"])
            rh = QHBoxLayout(row)
            rh.setContentsMargins(20, 2, 2, 2)
            rh.setSpacing(8)
            name = ElidedLabel(os.path.basename(f["path"]))
            rh.addWidget(name, 1)
            note_l = QLabel(f.get("note") or "")
            note_l.setObjectName("faint")
            rh.addWidget(note_l)
            for txt, col in (("+%d" % f["add"] if f["add"] else "", C["ok"]), ("−%d" % f["rem"] if f["rem"] else "", C["bad"])):
                l = QLabel(txt)
                l.setStyleSheet("color:%s; font-size:9pt" % col)
                rh.addWidget(l)
                l.setVisible(bool(txt))                # (después de colocarla: si no, sale un instante como ventanita)
            b = tbtn("acc_refrescar", tr("Devolver este archivo a como estaba"), lambda _=False, f=f: self.on_undo([f]), size=13)
            rh.addWidget(b)
            row.clicked.connect(lambda f=f: on_open(f["path"]))
            v.addWidget(row)
            self.rows.append((f, row, name, note_l, b))
        # con muchos archivos la tarjeta se comería la pantalla: se ven los primeros y el resto se despliega con un clic
        self.folded = len(files) > self.SHOWN + 1
        self.b_more = QPushButton()
        self.b_more.setProperty("kind", "flat")
        self.b_more.setCursor(Qt.PointingHandCursor)
        self.b_more.setStyleSheet("text-align:left; padding:3px 20px; color:%s" % C["mut"])
        self.b_more.clicked.connect(lambda: self.fold(not self.folded))
        v.addWidget(self.b_more)
        self.b_more.setVisible(self.folded)
        self.fold(self.folded)
        self.refresh()

    SHOWN = 6        # filas a la vista cuando hay más archivos que estos

    def fold(self, on):
        """Plegada: solo los primeros archivos y «Ver los N archivos»; desplegada: todos y «Ver menos»."""
        self.folded = bool(on)
        for i, (f, row, *_r) in enumerate(self.rows):
            row.setVisible(not self.folded or i < self.SHOWN)
        n = len(self.rows)
        self.b_more.setText((tr("Ver los %d archivos") % n) if self.folded else tr("Ver menos"))
        self.b_more.setIcon(icon("ui_chevron_abajo" if self.folded else "ui_chevron_arriba", C["mut"], 12))

    def refresh(self):
        left = 0
        for f, row, name, note_l, b in self.rows:
            b.setVisible(f["can_undo"] and not f["undone"])
            left += bool(f["can_undo"] and not f["undone"])
            if f["undone"]:
                name.setStyleSheet("color:%s; text-decoration: line-through" % C["faint"])
                note_l.setText(tr("deshecho"))
        self.b_all.setVisible(left >= 2)

    def mark_undone(self, paths_):
        keys = {os.path.normcase(os.path.normpath(p)) for p in paths_}
        for f, *_ in self.rows:
            if any(os.path.normcase(os.path.normpath(p)) in keys for p in f["paths"]):
                f["undone"] = True
        self.refresh()


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
        self.p_start = None                      # el modelo escribe los datos de una acción: «Va a escribir · 2 KB»
        self.body = md_label()
        self.body.hide()
        v.addWidget(self.body)
        self._read = None                        # avance real de la lectura (tokens leídos, total, velocidad, cuándo)
        self.q_start = None                      # el modelo escribe pero no llega nada visible: se dice, con cuánto lleva
        self.on_regen = None                     # qué hacer al pulsar «Regenerar» (lo pone el panel)
        self._stats = None                       # cifras del paso, a la espera de que exista la fila de botones
        self.text = ""

    # El pensamiento desplegable, las líneas de «va a escribir…» y de silencio y la fila de botones casi nunca se ven
    # (solo la respuesta final lleva botones; el pensamiento se despliega a mano). Se crean la primera vez que alguien
    # las pide —basta con nombrarlas, como siempre— y ocupan su sitio de siempre. Antes se creaban en cada paso: en una
    # conversación larga eran miles de piezas ocultas y la mayor parte del tiempo que tardaba en abrirse.
    _PARTS = {"think_view": "_make_think", "think_fold": "_make_think", "prep": "_make_prep", "quiet_line": "_make_quiet",
              "actions": "_make_actions", "b_copy": "_make_actions", "b_regen": "_make_actions", "b_report": "_make_actions",
              "b_undo_all": "_make_actions", "b_speak": "_make_actions", "stats": "_make_actions"}

    def __getattr__(self, name):
        make = AssistantBlock._PARTS.get(name)
        if make is None:
            raise AttributeError(name)
        getattr(self, make)()
        return self.__dict__[name]

    def has(self, name):
        """¿Existe ya esa pieza? (para preguntar por ella sin crearla)"""
        return name in self.__dict__

    @property
    def actions(self):                       # (QWidget ya tiene un «actions» propio: sin esto se devolvería ese)
        if "actions" not in self.__dict__:
            self._make_actions()
        return self.__dict__["actions"]

    def _make_think(self):
        tv = CV.ThinkView()
        fold = Collapsible(tv, limit=280, fade=C["bg"], slack=80)
        fold.hide()
        lay = self.layout()
        lay.insertWidget(lay.indexOf(self.peek) + 1, fold)       # (colocada antes de poder mostrarse: sin ventanitas)
        self.__dict__.update(think_view=tv, think_fold=fold)

    def _make_prep(self):
        w = CV.ActivityLine()
        w.hide()
        lay = self.layout()
        lay.insertWidget(lay.indexOf(self.body), w)
        self.__dict__["prep"] = w

    def _make_quiet(self):
        w = CV.ActivityLine()
        w.hide()
        lay = self.layout()
        lay.insertWidget(lay.indexOf(self.body) + 1, w)
        self.__dict__["quiet_line"] = w

    def _make_actions(self):
        actions = QWidget()
        ah = QHBoxLayout(actions)
        ah.setContentsMargins(0, 0, 0, 0)
        ah.setSpacing(2)
        b_copy = tbtn("acc_copiar", tr("Copiar respuesta"), self.copy, size=15)
        b_regen = tbtn("acc_refrescar", tr("Regenerar respuesta"), size=15)
        b_regen.clicked.connect(lambda *_: self.on_regen() if self.on_regen else None)
        b_report = tbtn("est_aviso", tr("Informar de un problema con esta respuesta"), self.report, size=15)
        b_undo_all = QPushButton(tr("Deshacer cambios"))
        b_undo_all.setProperty("kind", "flat")
        b_undo_all.setIcon(icon("acc_refrescar", C["mut"], 13))
        b_undo_all.setToolTip(tr("Restaura todos los archivos que el agente cambió en esta respuesta"))
        b_undo_all.hide()
        b_speak = tbtn("voz_altavoz", tr("Leer en voz alta"), self.speak, size=15)
        ah.addWidget(b_copy)
        ah.addWidget(b_speak)
        # visible u oculto, pero ya colocado: una pieza sin sitio que se hace visible es, por un instante, una ventanita suelta
        b_speak.setVisible(speaker_available())
        ah.addWidget(b_regen)
        ah.addWidget(b_report)
        ah.addWidget(b_undo_all)
        ah.addStretch(1)
        stats = FitLabel()                   # una sola linea: si no cabe, una version mas corta
        stats.setObjectName("stats")
        stats.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        ah.addWidget(stats, 1)
        actions.hide()
        self.layout().addWidget(actions)     # al final: lo que va «sobre los botones» ya está antes
        self.__dict__.update(actions=actions, b_copy=b_copy, b_regen=b_regen, b_report=b_report, b_undo_all=b_undo_all,
                             b_speak=b_speak, stats=stats)
        if self._stats:
            stats.set_options(*self._stats)

    def set_stats(self, options, tip):
        """Cifras del paso (tokens, velocidad, coste) para la fila de botones; si aún no existe, se guardan."""
        self._stats = (options, tip)
        if self.has("stats"):
            self.stats.set_options(options, tip)

    def set_actions(self, on):
        """Enseña u oculta la fila de botones de la respuesta (sin crearla solo para ocultarla)."""
        if on or self.has("actions"):
            self.actions.setVisible(on)
            self.b_regen.hide()
            self.b_undo_all.hide()

    def _above_actions(self):
        lay = self.layout()
        return lay.indexOf(self.actions) if self.has("actions") else lay.count()

    def tick(self, now):
        if self.act.live:
            if self._read and self.r_start is None:
                self.act.extra = self._read_text(now)
            self.act.tick(now)
        if self.has("prep") and self.prep.live:
            self.prep.tick(now)
        if self.has("quiet_line") and self.quiet_line.live:
            self.quiet_line.tick(now)

    def reading(self, done, total, tps, ts):
        """El motor dice cuánto lleva leído: «Leyendo tu mensaje… 40 s · 45 % · queda ~1 min»."""
        if self.r_start is not None or self.text or total < 200:      # lecturas cortas: no hace falta
            return
        self._read = (int(done), int(total), float(tps or 0), ts)
        self.act.extra = self._read_text(time.time())
        self.act.tick(time.time())

    def _read_text(self, now):
        done, total, tps, ts = self._read
        if tps > 0:                               # entre aviso y aviso (llegan por tandas) se estima con la velocidad medida
            done = min(total, done + tps * max(0.0, now - ts))
        pct = int(min(99, 100.0 * done / max(1, total)))
        left = (total - done) / tps if tps > 0 else 0
        if pct <= 0 and not left:
            return tr("%s tokens") % i18n.number(total, 0)
        return "%d %%" % pct + ((" · " + tr("queda ~%s") % CV.fmt_secs(left if left < 60 else round(left / 60.0) * 60)) if left >= 5 else "")

    def quiet(self, tokens, secs, ts, api=False):
        """El modelo sigue escribiendo pero no llega texto, pensamiento ni acción: que se vea que trabaja y cuánto lleva."""
        if self.q_start is None:
            self.q_start = ts - secs
            self.quiet_line.show()
            self.quiet_line.run((tr("El servicio prepara la respuesta: piensa sin mostrarlo y entrega cada acción de una vez") if api else
                                 tr("El modelo sigue escribiendo, pero aún no llega nada que mostrar"),), self.q_start, "est_info",
                                live=ts > time.time() - 8)
            self.quiet_line.setToolTip(tr("Los modelos por API no envían su razonamiento ni las acciones a medio escribir, así que pueden "
                                          "pasar minutos sin que llegue nada. Si la petición se queda colgada, Jayth la corta y le pide continuar.")
                                       if api else
                                       tr("El motor confirma que el modelo sigue generando. Si no produce nada, Jayth lo interrumpe y le pide continuar."))
        self.quiet_line.t_start = self.q_start = ts - secs     # el tiempo que lleva callado lo dice el vigilante
        self.quiet_line.extra = (tr("%s tokens") % i18n.number(tokens, 0)) if tokens else ""
        self.quiet_line.tick(time.time())

    def _end_quiet(self):
        if self.q_start is not None:
            self.q_start = None
            self.quiet_line.done("")
            self.quiet_line.hide()

    def delta(self, kind, text, ts):
        self._end_quiet()
        if kind == "reasoning":
            if self.r_start is None:
                self.r_start = ts
                live = ts > time.time() - 5
                self.act.show()
                self.act.run(CV.think_phrases(self.kind), ts, "ia_controlador", live=live)
                self.act.set_expandable(True)
            self.reasoning += text
            if self.has("think_fold") and self.think_fold.isVisible():
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
        if tail and not tail[-1].isspace() and tail[-1] not in ".,;:!?)…»\"'。，、！？" and " " in last:
            last = last.rsplit(" ", 1)[0]         # la palabra que aún se está escribiendo no se enseña a medias
        if len(last) > 160:
            cut = last[-159:]
            last = "…" + (cut.split(" ", 1)[1] if " " in cut else cut)    # ni la primera, cortada por delante
        self.peek.setText(last)
        self.peek.setVisible(bool(last))

    def toggle_think(self):
        on = not self.think_fold.isVisible()
        if on:
            self.think_view.setText(self.reasoning)
        self.think_fold.setVisible(on)
        self.act.set_open(on)
        self.peek.setVisible(False if on else (self.act.live and bool(self.peek.text())))

    def preparing(self, name, chars, ts):
        """El modelo está escribiendo una acción (el contenido de un archivo, un comando…): cuál y cuánto lleva."""
        self._end_quiet()
        self._end_think(ts)
        if self.r_start is None:
            self.act.hide()                      # no está leyendo: ya escribe
        if self.p_start is None:
            self.p_start = ts
            self.prep.show()
            self.prep.run((about_to(name),), ts, CV.tool_icon(name), live=ts > time.time() - 5)
        else:
            self.prep.phrases = (about_to(name),)
        self.prep.extra = i18n.size(chars) if chars >= 400 else ""
        self.prep.tick(time.time())

    def halt_prep(self):
        if self.p_start is not None:
            self.prep.done("")
            self.prep.hide()

    def _end_think(self, ts):
        if self.r_start and not self.r_end:
            self.r_end = ts
            self.act.done(self._thought_label())
            self.peek.hide()

    def _thought_label(self):
        return CV.thought_for(self.r_end - self.r_start) + (tr(" · resumen") if getattr(self, "think_summary", False) else "")

    def mark_summary(self):
        """Claude muestra un resumen de lo que pensó (no el razonamiento entero): se dice junto a «Pensó durante…»."""
        if getattr(self, "think_summary", False):
            return
        self.think_summary = True
        if self.r_start and self.r_end:
            self.act.done(self._thought_label())
        try:
            self.act.setToolTip(tr("El servicio muestra un resumen de lo que pensó el modelo, no su razonamiento completo."))
        except Exception:
            pass

    def finish(self, text, ts):
        self._end_think(ts)
        self._end_quiet()
        self.halt_prep()
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

    def thought_only(self):
        """Solo pensó (sin escribir nada): su «Pensó 4 s ›» puede ir dentro de las acciones que siguen."""
        return not (self.text or "").strip() and self.r_start is not None and getattr(self, "gallery", None) is None

    def add_extra(self, w):
        """Algo bajo la respuesta y sobre sus botones (el resumen de los cambios)."""
        self.layout().insertWidget(self._above_actions(), w)
        return w

    def add_gallery(self, paths_):
        """Debajo de la respuesta final: miniaturas de lo que el agente capturó o generó en esta respuesta (cómo quedó)."""
        paths_ = [p for p in paths_ if os.path.isfile(p)]
        if not paths_ or getattr(self, "gallery", None) is not None:
            return
        self.gallery = QWidget()
        fl = FlowLayout(self.gallery, spacing=8)
        for p in paths_:
            fl.addWidget(Preview(p, 340 if len(paths_) == 1 else 220, 210 if len(paths_) == 1 else 140))
        self.layout().insertWidget(self._above_actions(), self.gallery)

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


class UserMessage(QWidget):
    """Mensaje del usuario: la burbuja y, al pasar el ratón, sus acciones (copiar, editar y reenviar, reintentar, volver a
    este punto, nueva conversación desde aquí), como en los agentes de escritorio actuales."""

    def __init__(self, ev, compact=False, panel=None):
        super().__init__()
        self.ev, self.panel = ev, panel
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.v.setSpacing(0)
        self.v.addWidget(user_bubble(ev, compact))
        self.editor = None
        self.actions = QWidget()
        ah = QHBoxLayout(self.actions)
        ah.setContentsMargins(0, 0, 0, 0)
        ah.setSpacing(2)
        ah.addStretch(1)
        self.b_copy = tbtn("acc_copiar", tr("Copiar mensaje"), self.copy, size=14)
        self.b_edit = tbtn("acc_renombrar", tr("Editar y volver a enviar"), self.start_edit, size=14)
        self.b_retry = tbtn("acc_refrescar", tr("Reintentar desde aquí"), lambda: self.panel.retry_from(self.ev["i"]), size=14)
        self.b_more = tbtn("ui_menu_horizontal", tr("Más acciones"), self.more, size=14)
        for b in (self.b_copy, self.b_edit, self.b_retry, self.b_more):
            ah.addWidget(b)
        self.fx = QGraphicsOpacityEffect(self.actions)
        self.fx.setOpacity(0.0)                       # aparecen al pasar el ratón (el hueco se reserva: nada salta)
        self.actions.setGraphicsEffect(self.fx)
        self.v.addWidget(self.actions)
        if panel is None or "i" not in ev:
            self.actions.hide()

    def enterEvent(self, e):
        self.fx.setOpacity(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        if not getattr(self, "_menu_open", False):
            self.fx.setOpacity(0.0)
        super().leaveEvent(e)

    def copy(self):
        QGuiApplication.clipboard().setText(self.ev.get("text") or "")
        self.b_copy.setIcon(icon("ui_check", C["ok"], 14))
        QTimer.singleShot(1200, lambda: self.b_copy.setIcon(icon("acc_copiar", C["mut"], 14)))

    def more(self):
        m = QMenu(self)
        m.addAction(icon("acc_refrescar"), tr("Volver a este punto"), lambda: self.panel.rewind_to(self.ev["i"]))
        m.addAction(icon("acc_nuevo"), tr("Nueva conversación desde aquí"), lambda: self.panel.fork_from(self.ev["i"]))
        self._menu_open = True
        m.exec(self.b_more.mapToGlobal(self.b_more.rect().bottomLeft()))
        self._menu_open = False
        if not self.underMouse():
            self.fx.setOpacity(0.0)

    def start_edit(self):
        if not self.panel.can_rewind():
            return
        if self.editor is None:
            self.editor = QFrame()
            self.editor.setObjectName("composerBox")
            ev = QVBoxLayout(self.editor)
            ev.setContentsMargins(12, 10, 10, 8)
            self.edit = QPlainTextEdit(self.ev.get("text") or "")
            self.edit.setFrameShape(QFrame.NoFrame)
            lines = (self.ev.get("text") or "").count("\n") + 1
            self.edit.setFixedHeight(min(240, max(64, 22 * lines + 18)))
            ev.addWidget(self.edit)
            r = QHBoxLayout()
            hint = lbl(tr("Se quitará lo que vino después de este mensaje."), "faint")
            r.addWidget(hint, 1)
            r.addWidget(btn(tr("Cancelar"), cb=self.cancel_edit))
            r.addWidget(btn(tr("Enviar"), "primary", self.submit_edit))
            ev.addLayout(r)
            QShortcut(QKeySequence("Ctrl+Return"), self.edit, activated=self.submit_edit)
            QShortcut(QKeySequence("Escape"), self.edit, activated=self.cancel_edit)
            self.v.insertWidget(1, self.editor)
        self.edit.setPlainText(self.ev.get("text") or "")
        self.v.itemAt(0).widget().hide()
        self.actions.hide()
        self.editor.show()
        self.edit.setFocus()
        self.edit.moveCursor(QTextCursor.End)

    def cancel_edit(self):
        if self.editor is not None:
            self.editor.hide()
        self.v.itemAt(0).widget().show()
        self.actions.show()

    def submit_edit(self):
        text = self.edit.toPlainText().strip()
        if text:
            self.panel.edit_from(self.ev["i"], text)


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
        self.ico = pix_label("ui_check", C["acc"], 14)       # ✓ solo con todo hecho; mientras tanto, el de lista
        hh.addWidget(self.ico)
        self.title = QLabel()
        self.title.setStyleSheet("font-weight:600")
        hh.addWidget(self.title, 1)
        self.chev = QLabel()
        self.chev.setPixmap(pix("ui_chevron_abajo", C["faint"], 10))     # la misma flecha que el resto de plegables
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
        self.chev.setPixmap(pix("ui_chevron_abajo" if self.body.isVisible() else "ui_chevron_derecha", C["faint"], 10))

    def set_items(self, items, live=True):
        while self.bl.count():
            it = self.bl.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not items:
            return self.hide()
        done = sum(1 for i in items if i.get("status") == "completed")
        self.title.setText(tr("Plan · %d de %d") % (done, len(items)))
        self.ico.setPixmap(pix("ui_check" if done == len(items) else "uij_alinear_izq", C["acc"], 14))
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
        self.chev.setPixmap(pix("ui_chevron_abajo" if self.body.isVisible() else "ui_chevron_derecha", C["faint"], 10))


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


CHAT_SUGGESTIONS = [("acc_examinar", tr("Dime qué hay en mi carpeta de Descargas y qué ocupa más")),   # solo mira: nada que deshacer
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
        self.sub = s                                   # el chat lo cambia si cambias el modo de permisos
        self.by_mode = False
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


class ContextRing(QToolButton):
    """Memoria de la conversación que usa el modelo (su «contexto»), como un anillo que se va llenando junto al cuadro de
    texto: del color de acento con sitio de sobra, ámbar desde el 70 % (Jayth empieza a recortar) y rojo desde el 85 % (resume lo antiguo). Con un
    clic: cuánto ocupa, qué hará Jayth al llegar al tope y «Resumir ahora»."""
    TRIM, SUMMARY = A.Run.TRIM_AT, A.Run.SUMMARY_AT

    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.used = self.max = 0
        self.setCursor(Qt.PointingHandCursor)
        self.setPopupMode(QToolButton.InstantPopup)
        self.setAccessibleName(tr("Memoria de la conversación"))
        self.setStyleSheet("QToolButton { border: none; background: transparent; border-radius: 16px; }"
                           "QToolButton:hover { background: %s; } QToolButton::menu-indicator { image: none; width: 0; }" % C["hover"])
        self.menu_ = QMenu(self)
        self.menu_.setToolTipsVisible(True)
        self.menu_.aboutToShow.connect(self._fill)
        self.setMenu(self.menu_)
        self.setFixedSize(32, 32)
        self.hide()

    def frac(self):
        return min(1.0, self.used / float(self.max)) if self.max else 0.0

    def color(self):
        f = self.frac()
        return C["acc"] if f < self.TRIM else C["warn"] if f < self.SUMMARY else C["bad"]

    def set_value(self, used, mx):
        self.used, self.max = max(0, int(used)), max(0, int(mx))
        self.setVisible(bool(self.max))
        if not self.max:
            return
        pct = int(round(100 * self.frac()))
        self.setFixedSize(60, 32)                     # el porcentaje siempre (antes, solo desde el 70 %)
        self.setToolTip(tr("Memoria de la conversación: %s de %s tokens (%d %%).\nCerca del tope, Jayth recorta y resume lo "
                           "antiguo para no perderlo. Pulsa para ver más.") % (self._k(self.used), self._k(self.max), pct)
                        + (("\n" + self.cost_text()) if self.cost_text() else ""))
        self.update()

    def cost_text(self):
        """Con un modelo por API: lo que lleva gastado esta conversación y cuánto de lo leído salió de la caché (lo que
        sale de la caché se cobra a una fracción). Se recalcula como mucho cada 5 s."""
        sid = getattr(self.panel, "sid", None)
        now = time.time()
        last = getattr(self, "_cost_at", None)
        if last is None or last[0] != sid or now - last[1] > 5:
            from . import consumo as U
            try:
                s = U.session_summary(sid)
            except Exception:
                s = None
            if s:
                from .providers import money
                self._cost = (tr("Esta conversación: %d peticiones") % s["n"]
                              + ((" · ≈ " + money(s["usd"])) if s["usd"] is not None else "")
                              + (tr(" · %d %% leído de la caché") % round(s["cache"])))
            else:
                self._cost = ""
            self._cost_at = (sid, now)
        return self._cost

    @staticmethod
    def _k(n):
        return ("%sk" % i18n.number(n / 1000.0)) if n >= 1000 else str(n)

    def _fill(self):
        m = self.menu_
        m.clear()
        pct = int(round(100 * self.frac()))
        a = m.addAction(tr("Memoria de la conversación: %s de %s tokens (%d %%)") % (self._k(self.used), self._k(self.max), pct))
        a.setEnabled(False)
        self._cost_at = (None, 0)
        if self.cost_text():                             # con un modelo por API: lo gastado y cuánto salió de la caché
            c = m.addAction(self.cost_text())
            c.setEnabled(False)
        left = self.SUMMARY - self.frac()
        info = (tr("Va sobrada: queda mucho antes del tope.") if self.frac() < 0.5 else
                tr("Al llegar al %d %%, Jayth recortará las salidas antiguas de las herramientas y, si no basta, resumirá lo "
                   "antiguo.") % int(100 * self.TRIM) if self.frac() < self.TRIM else
                tr("Casi llena: en el próximo paso Jayth resumirá lo antiguo para no perderlo.") if left > 0 else
                tr("Llena: Jayth resume lo antiguo en el próximo paso. También puedes resumir ahora."))
        b = m.addAction(info)
        b.setEnabled(False)
        m.addSeparator()
        busy = self.panel.busy
        r = m.addAction(icon("ia_memoria", C["mut"]), tr("Resumir ahora"), self.panel.compact_now)
        r.setEnabled(not busy)
        r.setToolTip(tr("El modelo resume lo antiguo de esta conversación y libera memoria (lo reciente se queda tal cual).")
                     if not busy else tr("Espera a que termine lo que está haciendo."))
        m.addAction(icon("acc_nuevo", C["mut"]), tr("Empezar una conversación nueva"), self.panel.main.new_conversation)

    def paintEvent(self, e):
        super().paintEvent(e)
        from PySide6.QtGui import QPainter, QPen, QColor
        from PySide6.QtCore import QRectF
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(7, 7, 18, 18)
        track = QColor(C["faint"])
        track.setAlphaF(0.45)
        p.setPen(QPen(track, 2.2))
        p.drawEllipse(r)
        f = self.frac()
        if f > 0:
            fill = QColor(self.color())                 # el «quesito» de dentro: se lee como un medidor, no como «cargando»
            fill.setAlphaF(0.30)
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawPie(r.adjusted(3, 3, -3, -3), 90 * 16, -max(8, int(f * 360 * 16)))
            p.setBrush(Qt.NoBrush)
            pen = QPen(QColor(self.color()), 2.6)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(r, 90 * 16, -max(8, int(f * 360 * 16)))
        if self.width() > 40:
            font = p.font()
            font.setPointSizeF(8.5)
            p.setFont(font)
            p.setPen(QColor(self.color()))
            p.drawText(QRectF(29, 0, self.width() - 30, self.height()), Qt.AlignVCenter | Qt.AlignLeft, "%d %%" % int(round(100 * f)))
        p.end()


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
    _load = 0                     # número de apertura: lo que quede pendiente de una anterior no toca la actual
    _loading = None               # apertura que aún se está montando (su número), o None
    _plan_late = None             # último plan visto mientras se monta: se pinta una vez, al final
    _plan_items = ()              # el plan a la vista (para volver a él al recortar la conversación)
    _cur_i = -1                   # número del evento que se está pintando
    _mark_next = None             # mensaje tuyo cuya primera pieza aún no se ha colocado
    _veil = None                  # velo que tapa el chat mientras se monta una conversación larga
    _load_t = None                # temporizador que va montando los trozos
    LOAD_FIRST = 0.12             # segundos montando de un tirón antes de enseñar el velo (las cortas caben de sobra)
    LOAD_SLICE = 0.02             # y después, por trozos así de cortos: la ventana sigue respondiendo

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
        hl.setContentsMargins(m, 12, m, 28 if compact else 40)      # aire entre el último mensaje y el cuadro de texto
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
        # mientras una acción espera tu permiso (o una pregunta, tu respuesta) el chat no sigue el final: su tarjeta se queda
        # quieta bajo el ratón aunque llegue contenido debajo (antes se movía justo cuando ibas a pulsar «Permitir»)
        sb.rangeChanged.connect(lambda lo, hi: self.stick and not getattr(self, "waiting", 0) and sb.setValue(hi))
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
        bl.addWidget(tbtn("ui_cerrar", tr("Ocultar este aviso (vuelve si cambia algo)"), self._dismiss_banner, size=11), 0, Qt.AlignTop)
        self._ban_key = self._ban_dismissed = None
        self._ban_want = False
        self._ban_timer = QTimer(self)        # el aviso sale tras un momento: los estados de paso (al abrir, al
        self._ban_timer.setSingleShot(True)   # retomar un modelo ya cargado) no lo hacen parpadear
        self._ban_timer.setInterval(1200)
        self._ban_timer.timeout.connect(lambda: self.banner.setVisible(self._ban_want))
        self._queued = False                 # mensaje esperando a que el modelo termine de encenderse
        iv.addWidget(self.banner)
        self.plan_panel = PlanPanel()
        iv.addWidget(self.plan_panel)
        self.queue_box = QFrame()                # lo que escribiste mientras trabaja: lo verá en su próximo paso
        self.queue_box.setObjectName("queueBox")
        ql = QVBoxLayout(self.queue_box)
        ql.setContentsMargins(12, 6, 6, 6)
        ql.setSpacing(4)
        self.queue_box.hide()
        iv.addWidget(self.queue_box)
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
        self.mode_chip.setIcon(icon(MODE_ICON["ask"], C["mut"], 13))
        self.mode_chip.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.mode_chip.setPopupMode(QToolButton.InstantPopup)
        mm = QMenu(self)
        grp = QActionGroup(self)
        self.mode_actions = {}
        for k, desc in A.MODES.items():
            # una línea por modo con lo que pide y lo que no (antes, solo el nombre; lo demás, en una ayuda flotante)
            rest = re.split("[:：]", desc, 1)[-1].strip()
            a = mm.addAction(icon(MODE_ICON.get(k, "est_bloqueado"), C["warn"] if k == "auto" else C["mut"], 14),
                             "%s  —  %s" % (MODE_LABEL[k], rest))
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
        self.ctx_ring = ContextRing(self)            # memoria de la conversación usada por el modelo
        row.addWidget(self.ctx_ring, 0, Qt.AlignBottom)
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
        self.queue_btn = QToolButton()               # trabajando: enviar sin pararlo (lo verá en su próximo paso)
        self.queue_btn.setObjectName("round")
        self.queue_btn.setFixedSize(32, 32)
        self.queue_btn.setIcon(icon("lista_subir", C["tx"], 16))
        self.queue_btn.setIconSize(QSize(16, 16))
        self.queue_btn.setCursor(Qt.PointingHandCursor)
        self.queue_btn.setToolTip(tr("Enviar sin detenerlo: lo verá en su próximo paso (Intro)"))
        self.queue_btn.setAccessibleName(tr("Enviar mientras trabaja"))
        self.queue_btn.clicked.connect(lambda: self.send())
        self.queue_btn.hide()
        row.addWidget(self.queue_btn, 0, Qt.AlignBottom)
        self.send_btn = QToolButton()
        self.send_btn.setObjectName("sendBtn")
        self.send_btn.setFixedSize(32, 32)
        self.send_btn.setIconSize(QSize(16, 16))
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(lambda: self.stop() if self.busy else self.send())
        row.addWidget(self.send_btn, 0, Qt.AlignBottom)
        bv.addLayout(row)
        iv.addWidget(self.box)
        self.hint = None
        if not self.compact:
            self.hint = hint = QLabel()
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
        if self._mark_next is not None:                  # la primera pieza de tu mensaje: ahí se corta al volver a él
            self._marks.get(self._mark_next, {})["first"] = w
            self._mark_next = None
        if getattr(self, "_live", False):
            fade_in(w)                    # solo lo que llega en vivo, no al reabrir una conversacion
        return w

    def open_session(self, sid):
        """Abre una conversación sin enseñarla a medias: se monta sin pintar, sin animaciones de entrada, y aparece
        entera y ya colocada al final. Una corta cabe en un instante; una larga se monta por trozos cortos detrás de
        un velo («Abriendo la conversación…») para que la ventana no se quede congelada. Antes se veía vaciarse,
        rellenarse por tandas de 400 eventos (cada una, un parón) y saltar la barra mientras cada pieza tomaba su
        tamaño: el chat cargaba «a tirones»."""
        self._load += 1                                          # deja sin efecto lo pendiente de la apertura anterior
        self._loading = None
        self._plan_late = None
        nxt = core.SESSIONS.get(sid) if sid else None
        if nxt is None or not nxt.events:                        # vacía: no hay nada que esconder
            self._open(sid)
            self._unveil()
            return
        self.scroll.setUpdatesEnabled(False)
        self._open(sid)
        self._loading = self._load
        self._load_step(self._load, self.LOAD_FIRST)

    def _load_step(self, load, budget):
        """Monta otro trozo de la conversación que se está abriendo; al acabar, la coloca y la enseña."""
        try:
            if load != self._load or self._loading != load:      # ya se abrió otra: se encarga la suya
                return
            s = self.session()
            if budget != self.LOAD_FIRST and self._load_waits(s):
                return                                           # sigue al entrar en este panel (showEvent)
            end = time.time() + budget
            while s is not None and self.ev_i < len(s.events) and time.time() < end:
                before = self.ev_i
                self._feed(s, end)
                if self.ev_i == before:
                    break
            if s is not None and self.ev_i < len(s.events):
                self._veil_on()
                if self._load_t is None:                 # un solo temporizador: si no, cada llamada abriría otra cadena
                    self._load_t = QTimer(self, singleShot=True, interval=1)
                    self._load_t.timeout.connect(lambda: self._loading is not None and self._load_step(self._loading, self.LOAD_SLICE))
                return self._load_t.start()
            self._loading = None
            if self._plan_late is not None:
                self.plan_panel.set_items(self._plan_late, live=s is not None and s.run is not None)
                self._plan_late = None
            self.stick = True
            self.pump()                                          # lo que haya llegado entretanto y el estado (ocupado, cola)
            QTimer.singleShot(0, lambda: self._settle(load, 0, -1))
        except RuntimeError:
            pass

    def _load_waits(self, s):
        """¿Puede esperar el resto de la carga? Sí mientras la ventana esté a la vista pero este panel no (al arrancar en
        Chat, el de Code; y al revés) y su agente no esté trabajando: montarlo entonces solo restaría fluidez a lo que
        sí se ve. Se retoma al entrar en el panel."""
        try:
            return (not self.isVisible()) and self.window().isVisible() and not self.window().isMinimized() \
                and (s is None or s.run is None)
        except RuntimeError:
            return False

    def showEvent(self, e):
        super().showEvent(e)
        if self._loading is not None:                            # se quedó a medias mientras no se veía: ahora sí
            QTimer.singleShot(0, lambda: self._loading is not None and self._load_step(self._loading, self.LOAD_SLICE))

    def _settle(self, load, n, last):
        """Fin de una apertura: espera a que el contenido deje de cambiar de alto (cada pieza toma su tamaño en las
        vueltas siguientes), se coloca al final y solo entonces vuelve a pintar. Como mucho, medio segundo."""
        try:
            if load != self._load:                               # ya se abrió otra conversación: se encarga la suya
                return
            sb = self.scroll.verticalScrollBar()
            hi = sb.maximum()
            if self.stick and not self.waiting:
                sb.setValue(hi)
            if hi != last and n < 14:
                return QTimer.singleShot(35, lambda: self._settle(load, n + 1, hi))
            self._unveil()
            self.scroll.viewport().update()
        except RuntimeError:
            pass

    def _veil_on(self):
        """Tapa el chat mientras se monta una conversación larga: en vez de verla a medias, el fondo liso y, si se
        alarga, un aviso discreto (en una conversación mediana el aviso solo sería un parpadeo)."""
        if self._veil is None:
            self._veil = w = QWidget(self)
            w.setAttribute(Qt.WA_StyledBackground, True)
            vl = QVBoxLayout(w)
            self._veil_msg = msg = QWidget()
            row = QHBoxLayout(msg)
            row.setSpacing(8)
            self._veil_spin = Spinner(size=16)
            row.addStretch(1)
            row.addWidget(self._veil_spin)
            lab = QLabel(tr("Abriendo la conversación…"))
            lab.setObjectName("faint")
            row.addWidget(lab)
            row.addStretch(1)
            vl.addStretch(1)
            vl.addWidget(msg)
            vl.addStretch(1)
            msg.hide()
            w.hide()
        self._veil.setGeometry(self.scroll.geometry())
        if self._veil.isHidden():
            self._veil_t0 = time.time()
            self._veil.setStyleSheet("background:%s" % C["bg"])
            self._veil.raise_()
            self._veil.show()
        elif self._veil_msg.isHidden() and time.time() - self._veil_t0 > 0.4:
            self._veil_msg.show()
            self._veil_spin.start()

    def _unveil(self):
        if self._veil is not None and not self._veil.isHidden():
            self._veil_spin.stop()
            self._veil_msg.hide()
            self._veil.hide()
        self.scroll.setUpdatesEnabled(True)

    def _open(self, sid):
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
        self.turn_rows = []
        self.change_cards = []
        self._turn_card = None
        self._queue_sig = None
        self._plan_cards = []
        self._marks = {}                 # por cada mensaje tuyo: el punto del chat justo antes de él (para recortar ahí)
        self._mark_next = None
        s0 = core.SESSIONS.get(sid) if sid else None
        self._plan_items = list((s0.data.get("plan") if s0 else None) or [])
        self.ctx_ring.set_value(0, 0)
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
        cfg = core.SET.snapshot()
        name = cfg.get("user_name", "").strip()
        e = EmptyState((tr("¿En qué te ayudo, %s?") % name) if name else tr("¿En qué te ayudo hoy?"),
                       self._mode_subtitle(cfg.get("mode")), CHAT_SUGGESTIONS, self._pick, self.compact)
        e.by_mode = True
        return e

    @staticmethod
    def _mode_subtitle(mode):
        """Qué hará el agente, según el modo de permisos (antes decía «cada acción la apruebas tú» también en Automático)."""
        return {"readonly": tr("Puedo leer tus archivos. En modo Solo lectura no cambio nada, no ejecuto nada y no uso la red."),
                "plan": tr("Puedo trabajar con tus archivos, programas y la web. En modo Planificar primero investigo y te "
                           "propongo un plan: no cambio nada hasta que lo apruebes."),
                "edits": tr("Puedo trabajar con tus archivos, programas y la web. Edito archivos sin preguntar; para ejecutar, "
                            "usar la red o manejar el ordenador te pido permiso."),
                "auto": tr("Puedo trabajar con tus archivos, programas y la web. En modo Automático actúo sin preguntar (salvo "
                           "lo peligroso): verás cada acción en el chat."),
                }.get(mode, tr("Puedo trabajar con tus archivos, programas y la web. Antes de cualquier acción que cambie algo, "
                               "te pido permiso."))

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

    def _feed(self, s, end=None):
        """Pasa al chat los eventos que falten (hasta 400, o hasta la hora «end» si se da)."""
        with s.cond:
            new = s.events[self.ev_i:self.ev_i + 400]
        n = 0
        for ev in new:
            try:
                self._live = ev.get("ts", 0) > time.time() - 3
                self._cur_i = self.ev_i + n
                self.handle(ev)
            except Exception as e:
                print("evento", ev.get("t"), e, file=sys.stderr)
            n += 1
            if end is not None and time.time() >= end:
                break
        self.ev_i += n

    def pump(self):
        if self._loading is not None:          # aún se está montando: otro trozo y nada más (el estado, al acabar)
            return self._load_step(self._loading, self.LOAD_SLICE)
        s = self.session()
        if not s:
            return
        if self.ev_i > len(s.events):          # la conversacion se recorto (regenerar): reconstruir
            return self.reload_quiet()
        self._feed(s)
        if T.PROGRESS:                                   # acciones largas en curso (crear una imagen): su avance
            for cid, info in list(T.PROGRESS.items()):
                r = self.rows.get(cid)
                if r is not None and r.phase == "run":
                    try:
                        r.live(info)
                    except Exception as e:
                        print("avance", cid, e, file=sys.stderr)
        busy = s.run is not None
        if busy != self.busy:
            self.busy = busy
            if not busy:
                self._stale()
                left = list(getattr(s, "leftover", None) or [])
                if left:                                 # lo escribiste mientras trabajaba y no llegó a verlo
                    s.leftover = []
                    cur = self.input.toPlainText().strip()
                    self.input.setPlainText("\n\n".join(([cur] if cur else []) + left))
                    self.input.moveCursor(QTextCursor.End)
                    self.main.toast(tr("Tu mensaje en cola no llegó a enviarse: sigue en el cuadro de texto."),
                                    icon_name="est_info", ms=8000)
            self.sync()
            self.changed.emit()
        self._render_queue()

    def handle(self, ev):
        t = ev["t"]
        if t == "user":
            self._mark(self._cur_i)
            if self.empty is not None:
                self.empty.hide()
                self.empty.deleteLater()
                self.empty = None
            self._end_steps()
            self.cur = None
            self.turn_blocks = []
            self.turn_images = []
            self.turn_rows = []
            self.turn_t0 = ev["ts"]
            self.turn_spent = None                      # modelo por API: tokens y coste de este turno
            self.last_tool = None
            if ev.get("marker") == "plan":              # «Ejecutar el plan»: una marca, no un mensaje tuyo con texto interno
                for c in getattr(self, "_plan_cards", []):   # la tarjeta «Plan listo» ya está respondida
                    try:
                        c.hide()
                    except RuntimeError:
                        pass
                self._plan_cards = []
                self.add(divider(tr("Aprobaste el plan: se ejecuta paso a paso"), "ui_check", C["ok"]))
            else:
                self.add(UserMessage(ev, self.compact, self))
        elif t == "steer":                              # lo escribiste mientras trabajaba: lo vio en este punto
            self._end_steps()
            self.add(steer_bubble(ev, self.compact))
            self._render_queue(force=True)
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
        elif t == "tool_prep":                      # solo en directo: al reabrir una conversación ya no aporta nada
            if self.cur is not None and ev["ts"] > time.time() - 5:
                self.cur.preparing(ev["name"], ev.get("chars", 0), ev["ts"])
        elif t == "reading":                        # solo en directo: cuánto lleva leído el motor
            if self.cur is not None and ev["ts"] > time.time() - 8:
                self.cur.reading(ev.get("done", 0), ev.get("total", 0), ev.get("tps", 0), ev["ts"])
        elif t == "quiet":                          # solo en directo: escribe sin que llegue nada visible
            if self.cur is not None and ev["ts"] > time.time() - 8:
                self.cur.quiet(ev.get("tokens", 0), ev.get("secs", 0), ev["ts"], api=bool(ev.get("api")))
        elif t == "stats":
            if ev.get("ctx_used") and ev.get("ctx_max"):       # memoria de la conversación: en el anillo junto al cuadro de texto
                self.ctx_ring.set_value(int(ev["ctx_used"]) + int(ev.get("gen_n") or 0), int(ev["ctx_max"]))
            if ev.get("tok_in") or ev.get("tok_out"):   # modelo por API: lo que gastó este paso se suma al turno
                sp = getattr(self, "turn_spent", None) or {"n": 0, "i": 0, "o": 0, "usd": 0.0, "sin_precio": 0, "estimado": False}
                sp["n"] += 1
                sp["i"] += int(ev.get("tok_in") or 0)
                sp["o"] += int(ev.get("tok_out") or 0)
                if ev.get("usd") is None:
                    sp["sin_precio"] += 1
                else:
                    sp["usd"] += float(ev["usd"])
                    sp["estimado"] = sp["estimado"] or ev.get("usd_src") != "servicio"
                self.turn_spent = sp
                if self.cur is not None and not ev.get("gen_n"):
                    from .providers import tok_short, money
                    cost = (" · " + ("≈ " if ev.get("usd_src") != "servicio" else "") + money(float(ev["usd"]))) if ev.get("usd") is not None else ""
                    full = tr("%s tokens leídos · %s escritos") % (tok_short(ev.get("tok_in")), tok_short(ev.get("tok_out"))) + cost
                    if ev.get("think_tok"):                  # razonó sin mostrarlo: al menos se ve cuánto
                        full += tr(" · pensó %s sin mostrarlo") % tok_short(ev["think_tok"])
                    self.cur.set_stats([full, (cost[3:] or full), cost[3:] or "%s tok" % tok_short(ev.get("tok_out"))],
                                       tr("Tokens que el servicio cobró por este paso (lo que leyó y lo que escribió) y su coste "
                                          "aproximado. El detalle por servicio está en «Modelos por API…»."))
            if self.cur is not None and ev.get("think_summary"):
                self.cur.mark_summary()
            if self.cur is not None and ev.get("gen_n"):
                tok = "%s tok" % ev["gen_n"]
                tps = (" · %s tok/s" % i18n.number(ev["tps"])) if ev.get("tps") else ""
                cut = tr(" · cortado por límite") if ev.get("finish") == "length" else ""
                self.cur.set_stats([tok + tps + cut, (tps[3:] or tok) + cut, cut[3:] or tok],
                                   tr("Tokens que escribió el modelo en este paso y a qué velocidad."))
        elif t == "ctx":                                # tras recortar o resumir: lo que ocupa ahora
            self.ctx_ring.set_value(int(ev.get("used") or 0), int(ev.get("max") or 0))
        elif t in ("trimmed", "compact_end"):
            pass
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
                    self.cur.on_regen = self.regenerate
                    if not self.cur.thought_only():   # solo pensó: su «Pensó 4 s ›» irá dentro de las acciones que siguen
                        self._end_steps()
                self.cur = None
        elif t == "tool_call" and ev["name"] in ("update_plan", "use_tools"):     # plan: en su panel; activar herramientas: interno
            pass                                        # se muestra en el panel del plan (evento «plan»)
        elif t == "plan":
            self._plan_items = list(ev.get("items") or [])
            if self._loading is not None:      # al abrir una conversación solo cuenta el último plan: se pinta al final
                self._plan_late = ev.get("items") or []
            else:
                self.plan_panel.set_items(ev.get("items") or [], live=getattr(self, "_live", False))
        elif t == "question":
            card = QuestionCard(ev, self.answer, live=getattr(self, "_live", False) or self.busy)
            self.questions[ev["id"]] = card
            self.add(card)
            self._end_steps()
            if card.inputs.isVisible():
                self.waiting += 1
                self.sync()
                self._show_waiting(card)
                self.main.notify_pending(tr("tiene una pregunta: %s") % ev["question"], ev["ts"], self.sid)
        elif t == "answer":
            q = self.questions.get(ev["id"])
            if q:
                if q.inputs.isVisible():
                    self.waiting = max(0, self.waiting - 1)
                    self._follow_again()
                q.answered(ev.get("text", ""))
                self.sync()
        elif t == "undo":
            for cid in ev.get("ids") or []:
                if cid in self.rows:
                    self.rows[cid].undone()
            for c in getattr(self, "change_cards", []):
                try:
                    c.mark_undone(ev.get("files") or [])
                except RuntimeError:
                    pass
            if ev.get("by") != "agent":              # si lo deshizo el agente, ya lo dice su propia acción («Deshizo sus cambios»)
                self.add(note(tr("Cambios deshechos: %s") % ", ".join(os.path.basename(f) for f in ev.get("files") or [])))
                self._end_steps()
        elif t == "compacted":
            w = self.add(note(tr("Resumí la parte antigua de la conversación para que el modelo no la olvide ni se quede sin memoria.")))
            if ev.get("text"):                          # qué recuerda ahora el modelo de aquello: se puede leer
                full = TextView(ev["text"], "plain", color=C["mut"], size="9pt")
                full.hide()
                b = QPushButton(tr("Ver el resumen"))
                b.setProperty("kind", "flat")
                b.clicked.connect(lambda _=False, f=full, b=b: (f.setVisible(not f.isVisible()),
                                                                 b.setText(tr("Ocultar el resumen") if f.isVisible() else tr("Ver el resumen"))))
                w.layout().addWidget(b, 0, Qt.AlignTop)
                box = QVBoxLayout()
                text_w = w.layout().itemAt(1).widget()
                w.layout().removeWidget(text_w)
                box.addWidget(text_w)
                box.addWidget(full)
                w.layout().insertLayout(1, box, 1)
            self._end_steps()
        elif t == "recovered":                      # la volvió a escribir como texto: Jayth la convirtió en una acción real
            self.add(note(tr("El modelo volvió a escribir la acción «%s» como texto; Jayth la convirtió en una acción real, con los "
                             "permisos de siempre.") % T.TOOL_LABELS.get(ev["name"], ev["name"])))
            self._end_steps()
        elif t == "nudge":                          # el modelo anunció una acción y no la hizo: Jayth se lo recordó
            if ev.get("quiet") and ev.get("api"):   # el servicio por API dejó la petición colgada
                self.add(note(tr("El servicio estuvo varios minutos sin enviar nada; Jayth cortó la petición y le pidió al modelo que continúe.")))
            elif ev.get("quiet"):                   # escribía sin producir nada visible: se cortó
                self.add(note(tr("El modelo se quedó escribiendo sin producir texto ni acción; Jayth lo interrumpió y le pidió que continúe.")))
            elif ev.get("empty"):                   # respondió vacío a mitad de la tarea
                self.add(note(tr("El modelo dejó la respuesta vacía; Jayth le pidió que siga con la tarea.")))
            elif ev.get("offer"):                   # te propuso como comando una acción suya: no dijo haberla hecho
                self.add(note(tr("El modelo te propuso usar «%s», que es una acción suya y no un comando que puedas "
                                 "ejecutar; Jayth se lo indicó.") % T.TOOL_LABELS.get(ev["written"], ev["written"])))
            elif ev.get("written"):                 # la escribió como texto: lo que diga de su resultado no es verdad
                self.add(note(tr("Atención: el modelo escribió la acción «%s» como texto en vez de hacerla, así que no se hizo "
                                 "(aunque diga lo contrario). Jayth se lo indicó.") % T.TOOL_LABELS.get(ev["written"], ev["written"]), True))
            else:
                self.add(note(tr("El modelo anunció una acción sin hacerla; Jayth se lo recordó para que la haga o termine.")))
            self._end_steps()
            self.last_tool = "__nudge__"
        elif t == "plan_ready":
            if getattr(self, "_live", False):
                self._plan_cards = [c for c in getattr(self, "_plan_cards", []) if c.parent() is not None] + [self.add(self._plan_ready_card())]
                self._end_steps()
        elif t == "tool_call":
            self.last_tool = ev["name"]
            row = StepRow(ev, self.decide)
            if ev.get("sub"):                           # lo hizo un ayudante: sangrado bajo el encargo del agente principal
                row.setContentsMargins(18, 0, 0, 0)
                row.setToolTip((tr("Acción del ayudante «%s»") % ev["sub"]) if isinstance(ev["sub"], str) else tr("Acción de un ayudante"))
            self.rows[ev["id"]] = row
            self.turn_rows = getattr(self, "turn_rows", []) + [row]
            th = self._last_visible()                   # lo que pensó justo antes: dentro del grupo, no suelto en el chat
            thought = th if isinstance(th, AssistantBlock) and th.thought_only() else None
            if thought is not None:
                self.cl.removeWidget(thought)
            if self.steps is None or self._last_visible() is not self.steps:
                self._end_steps()
                self.steps = self.add(StepsBox())
                self.boxes = [b for b in getattr(self, "boxes", []) if b.parent() is not None] + [self.steps]
            if thought is not None:
                self.steps.add_thought(thought)
            self.steps.add(row)
            row.box = self.steps
            if row.pending:
                self.waiting += 1
                self.sync()
                self._show_waiting(row)
                self.main.notify_pending(describe(ev["name"], ev.get("args"), "pending"), ev["ts"], self.sid)
        elif t == "approval":
            r = self.rows.get(ev["id"])
            if r:
                if r.pending:
                    self.waiting = max(0, self.waiting - 1)
                    self._follow_again()
                r.resolved(ev["decision"])
                r.box.refresh()
                self.sync()
        elif t == "tool_result":
            # Lo que el agente CREÓ en esta respuesta (imágenes, gráficos) se repite bajo la respuesta final. Las capturas
            # que hizo para mirar algo (pantalla, navegador, una imagen del disco) no: se quedan en su acción, porque al
            # final salían sin venir a cuento (p. ej. una captura de prueba de la propia ventana).
            made = self.rows.get(ev["id"])
            made = made is not None and (made.ev.get("name") in ("run_python", "generate_image") or str(made.ev.get("name")).startswith("mcp__"))
            if ev.get("ok") and made:
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
                if ev.get("connect_service") and r.box is not None and getattr(r, "svc_tile", None) is None:
                    from .conectores_ui import ServiceTile         # el agente propone conectar un servicio: tú decides
                    r.svc_tile = r.box.add_widget(ServiceTile(ev["connect_service"], on_continue=self._service_ready,
                                                              reason=ev.get("reason") or ""))
                if ev.get("image_setup") and r.box is not None and getattr(r, "setup_box", None) is None:
                    from .imagen_ui import ImageInstallBox      # falta el generador de imágenes: se instala desde aquí
                    r.needs_setup()
                    r.setup_box = r.box.add_widget(ImageInstallBox(ev["image_setup"], on_continue=self._images_ready, intro=True))
                if ev["ok"] and ev.get("generated") and r.box is not None:
                    copy = os.path.join(paths.IMG_DIR, ev["image"]) if ev.get("image") else None
                    if copy:
                        GENERATED[copy] = ev["generated"]        # la copia del chat remite al archivo real
                    r.box.add_image(ev["generated"], r, copy, live=ev["ts"] > time.time() - 5)
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
        elif t in ("info", "error") and ev.get("hidden"):
            pass                                       # aviso que el usuario quitó
        elif t == "spend_alert":                       # se superó el gasto que pusiste como aviso
            self.add(note(ev["text"], False))
            if ev.get("ts", 0) > time.time() - 10:
                self.main.toast(ev["text"], tr("Ajustes"), lambda: self.main.settings("Modelos"), icon_name="est_aviso", color=C["warn"])
        elif t in ("info", "error"):
            w = self.add(note(tr("Detenido por ti.") if (t == "info" and ev["text"] == "Detenido.") else ev["text"],
                              t == "error" or bool(ev.get("warn"))))      # warn: un aviso que no debe pasar desapercibido
            if t == "error" and "i" in ev:
                # un error se puede reintentar o quitar (p. ej. «no puedo conectar con el modelo» una vez encendido)
                h = w.layout()
                h.addWidget(tbtn("acc_refrescar", tr("Reintentar"), self.regenerate, size=13), 0, Qt.AlignTop)
                h.addWidget(tbtn("ui_cerrar", tr("Quitar este aviso"), lambda _=False, w=w, i=ev["i"]: self._hide_note(w, i), size=11),
                            0, Qt.AlignTop)
            self._end_steps()
        elif t == "turn_end":
            if self.cur is not None:
                self.cur.halt_prep()
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
            anchor = self._final_anchor(tb[-1] if tb else None)
            if tb:
                tb[-1].final = anchor is not None or not (tb[-1].text or "").strip()
            self._turn_summary(ev, anchor)
            # cómo quedó: las últimas capturas, bajo la respuesta (no dentro de un grupo de acciones plegado)
            home = anchor if anchor is not None else (tb[-1] if tb and self.cl.indexOf(tb[-1]) >= 0 else None)
            if home is not None:
                imgs = getattr(self, "turn_images", None) or []
                near = self._just_above(home)            # las que ya se ven justo encima no se repiten
                imgs = [p for p in imgs if p not in (getattr(near, "images", None) or [])]
                if imgs:
                    home.add_gallery(imgs[-4:])
                    for bx in getattr(self, "boxes", []):    # lo creado ya se ve bajo la respuesta: su tarjeta se pliega
                        try:
                            bx.fold_images(set(imgs[-4:]))
                        except RuntimeError:
                            pass
            self.turn_blocks = []
            self.turn_images = []
            for b in self.blocks:
                # sin texto (el turno acabó en un error tras una acción) no hay nada que copiar ni escuchar: sin la fila,
                # que si no quedaba en medio, antes de esa acción
                b.set_actions(getattr(b, "final", True) and bool((b.text or "").strip()))
            if self.blocks and self.blocks[-1].has("actions"):
                self.blocks[-1].b_regen.show()      # solo la ultima respuesta se puede regenerar
                if self.turn_undo and not getattr(self, "_turn_card", None):   # (con tarjeta de cambios, va en ella)
                    last = self.blocks[-1]
                    last.b_undo_all.show()
                    if not getattr(last, "_undo_wired", False):
                        last._undo_wired = True
                        last.b_undo_all.clicked.connect(self.undo_turn)
            self.turn_undo = False
            for q in self.questions.values():
                if q.inputs.isVisible():
                    q.answered("")
            QTimer.singleShot(0, self.main.sync)          # el estado de arriba vuelve a «Listo»

    def _final_anchor(self, b):
        """La respuesta final del turno si tiene texto y queda después de todas sus acciones (ahí van «Trabajó durante»,
        los cambios y los botones); None si no la hay."""
        if b is None or not (b.text or "").strip():
            return None
        i = self.cl.indexOf(b)
        if i < 0:
            return None
        last = -1
        for x in getattr(self, "boxes", []):
            try:
                if x.parent() is not None:
                    last = max(last, self.cl.indexOf(x))
            except RuntimeError:
                pass
        return b if i > last else None

    def _follow_again(self):
        """Ya no se espera nada del usuario: el chat vuelve a seguir lo que va llegando."""
        if not self.waiting:
            self.stick = True
            sb = self.scroll.verticalScrollBar()
            QTimer.singleShot(0, lambda: sb.setValue(sb.maximum()))

    def _show_waiting(self, w):
        """Lo que espera al usuario (un permiso, una pregunta) se lleva a la vista una vez y ahí se queda."""
        def show():
            try:
                if self.waiting and w.isVisible():
                    self.scroll.ensureWidgetVisible(w, 0, 60)
            except RuntimeError:
                pass
        QTimer.singleShot(140, show)

    def _turn_summary(self, ev, anchor):
        """Al terminar un turno con acciones: «Trabajó durante 3 min 12 s» antes de la respuesta y, bajo ella, los archivos
        que cambió (para abrirlos o deshacerlos)."""
        rows = []
        for r in getattr(self, "turn_rows", []):
            try:
                if r.parent() is not None:
                    rows.append(r)
            except RuntimeError:
                pass
        self.turn_rows = []
        self._turn_card = None
        if not rows:
            return
        files = self._turn_changes(rows)
        if files:
            card = ChangesCard(files, self._open_changed, self._undo_files)
            self.change_cards = [c for c in getattr(self, "change_cards", []) if c.parent() is not None] + [card]
            self._turn_card = card
            if anchor is not None:
                anchor.add_extra(card)
            else:
                self.add(card)
        t0 = getattr(self, "turn_t0", None)
        if t0 and ev["ts"] - t0 >= 1:                # cierra el turno: va debajo de todo, también de la respuesta final
            self._worked = self.add(worked_line(ev["ts"] - t0, getattr(self, "turn_spent", None)))

    def _abs(self, p):
        p = str(p or "")
        return os.path.normpath(p if os.path.isabs(p) else os.path.join(self.workspace(), p))

    def _turn_changes(self, rows):
        """Archivos que cambiaron en este turno, en orden: {path, paths, add, rem, note, can_undo, undone, cids}."""
        from . import harness
        files, order = {}, []
        for r in rows:
            name, a = r.ev["name"], r.ev.get("args") or {}
            if name not in CHANGE_TOOLS or r.phase != "ok" or getattr(r, "is_undone", False):
                continue
            snap = harness.snapshot_files(self.sid, r.id)
            if snap:
                ps = [(e["path"], e.get("existed", True), bool(e.get("copy")) or not e.get("existed", True)) for e in snap]
            else:
                raw = [a.get("source"), a.get("dest")] if name == "move_path" else [a.get("path")]
                ps = [(self._abs(x), True, False) for x in raw if x]
            if not ps or (name == "replace_in_files" and not snap):       # (una vista previa no cambia nada)
                continue
            if name == "replace_in_files":           # un solo reemplazo toca varios archivos: cada uno, su fila
                for path, existed, can in ps:
                    key = os.path.normcase(os.path.normpath(path))
                    f = files.get(key)
                    if f is None:
                        f = files[key] = {"path": path, "paths": [path], "add": 0, "rem": 0, "note": "", "undone": False, "cids": [],
                                          "can_undo": can, "new": False}
                        order.append(key)
                    f["cids"].append(r.id)
                    f["note"] = f["note"] or tr("reemplazo")
                continue
            ad, de = diff_badge(name, a)
            ad, de = int(ad[1:] or 0), int(de[1:] or 0)
            path, existed, can = ps[0]
            key = os.path.normcase(os.path.normpath(path))
            f = files.get(key)
            if f is None:
                f = files[key] = {"path": path, "paths": [path], "add": 0, "rem": 0, "note": "", "undone": False, "cids": [],
                                  "can_undo": bool(snap) and can, "new": not existed}
                order.append(key)
            f["add"] += ad
            f["rem"] += de
            f["cids"].append(r.id)
            if name == "delete_path":
                f["note"] = tr("a la papelera")
            elif name == "move_path" and len(ps) > 1:
                f["note"] = tr("movido a %s") % os.path.basename(ps[1][0])
                if ps[1][0] not in f["paths"]:
                    f["paths"].append(ps[1][0])
            elif f["new"] and not f["note"]:
                f["note"] = tr("nuevo")
        return [files[k] for k in order]

    def _open_changed(self, path):
        if os.path.isfile(path):
            if self.can_edit(path):
                self.open_in_editor(path)
            else:
                osys.open_path(path)
        elif os.path.isdir(path):
            reveal(path)
        else:
            self.main.toast(tr("«%s» ya no existe.") % os.path.basename(path), icon_name="est_info")

    def _undo_files(self, fs):
        """Devuelve esos archivos (de la tarjeta de cambios) a como estaban antes de la respuesta."""
        s = self.session()
        if not s:
            return
        if s.run is not None:
            return self.main.toast(tr("Espera a que el agente termine para deshacer."), icon_name="est_aviso", color=C["warn"])
        done = []
        for f in fs:
            if f["undone"] or not f["can_undo"]:
                continue
            for p in f["paths"]:
                done += s.undo_file(p, f["cids"]) or []
        if done:
            self.main.toast(tr("Restaurado: %s") % ", ".join(os.path.basename(x) for x in done), icon_name="acc_refrescar", color=C["ok"])
            for x in done:
                self.file_written.emit(x)
        else:
            self.main.toast(tr("No queda nada que deshacer en esos archivos."), icon_name="est_info")

    # ---- mensajes escritos mientras trabaja
    def _render_queue(self, force=False):
        s = self.session()
        items = s.run.queued() if (s is not None and s.run is not None) else []
        sig = tuple(i["id"] for i in items)
        if not force and sig == getattr(self, "_queue_sig", ()):
            return
        self._queue_sig = sig
        lay = self.queue_box.layout()
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        for i in items:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)
            h.addWidget(pix_label("lista_subir", C["faint"], 13))
            t = ElidedLabel(i["text"].replace("\n", " "))
            t.setToolTip(i["text"])
            h.addWidget(t, 1)
            w = QLabel(tr("lo verá en su próximo paso"))
            w.setObjectName("faint")
            h.addWidget(w)
            h.addWidget(tbtn("ui_cerrar", tr("Quitar de la cola (vuelve al cuadro de texto)"),
                             lambda _=False, i=i: self._unqueue(i), size=11))
            lay.addWidget(row)
        self.queue_box.setVisible(bool(items))

    def _unqueue(self, item):
        s = self.session()
        if s is not None and s.unsteer(item["id"]):
            cur = self.input.toPlainText().strip()
            self.input.setPlainText("\n\n".join([x for x in (cur, item["text"]) if x]))
            self.input.moveCursor(QTextCursor.End)
        self._render_queue(force=True)

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
        self.session().send(tr("Adelante: ejecuta el plan aprobado paso a paso, actualizando la lista de tareas."), marker="plan")
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
            if b.has("b_undo_all"):
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

    def compact_now(self):
        """«Resumir ahora» desde el anillo de memoria: el modelo resume lo antiguo de la conversación."""
        s = self.session()
        if s is None or self.busy:
            return
        if not core.SET.ready():
            return self.main.fix_not_ready()
        if core.SET.snapshot()["llm_mode"] == "local" and self.main.llm.get("state") != "ready":
            return self.main.toast(tr("Enciende el modelo para poder resumir la conversación."), icon_name="est_aviso", color=C["warn"])
        err = s.compact()
        if err:
            return QMessageBox.information(self, APP_NAME, err)
        self.busy = True
        self.stick = True
        self.sync()
        self.changed.emit()

    def reload_quiet(self, at=None):
        """La conversación se recortó a partir del evento «at» (regenerar, reintentar, editar, volver a un mensaje): se
        quita del chat solo lo que vino desde ahí y lo demás se queda en su sitio, sin rehacerlo. Si no se puede (no se
        sabe dónde, o aún se estaba montando), se vuelve a montar entera sin que se vea a medias."""
        if at is not None and self._cut_at(at):
            return
        self.open_session(self.sid)

    def _mark(self, i):
        """Justo antes de pintar tu mensaje número i: lo necesario para volver a este punto sin rehacer el chat."""
        self._marks[i] = {"first": None, "plan": list(self._plan_items or []), "ctx": (self.ctx_ring.used, self.ctx_ring.max),
                          "waiting": self.waiting}
        self._mark_next = i

    def _cut_at(self, at):
        """Quita del chat lo que vino desde el evento «at» (un mensaje tuyo) y deja el chat como estaba justo antes."""
        import shiboken6
        s, m = self.session(), (getattr(self, "_marks", None) or {}).get(at)
        if s is None or m is None or self._loading is not None:
            return False
        try:
            first = m["first"]
            k = self.cl.indexOf(first) if first is not None else -1
            if k < 0:
                return False                             # no se sabe dónde empieza: mejor rehacerla
            gone = []
            while self.cl.count() - 1 > k:
                w = self.cl.takeAt(k).widget()
                if w is not None:
                    gone.append(w)
            dead = {shiboken6.getCppPointer(w)[0] for w in gone}

            def kept(x):
                try:
                    p = x
                    while p is not None:
                        if shiboken6.getCppPointer(p)[0] in dead:
                            return False
                        p = p.parentWidget()
                    return shiboken6.isValid(x)
                except RuntimeError:
                    return False
            self.blocks = [b for b in self.blocks if kept(b)]
            self.boxes = [b for b in self.boxes if kept(b)]
            self.change_cards = [c for c in self.change_cards if kept(c)]
            self._plan_cards = [c for c in self._plan_cards if kept(c)]
            self.rows = {cid: r for cid, r in self.rows.items() if kept(r)}
            self.questions = {qid: q for qid, q in self.questions.items() if kept(q)}
            if self.empty is not None and not kept(self.empty):
                self.empty = None
            for w in gone:
                w.hide()
                w.deleteLater()
        except RuntimeError:
            return False
        self.cur = self.steps = self._turn_card = self.turn_spent = self.last_tool = None
        self.turn_blocks, self.turn_images, self.turn_rows = [], [], []
        self.turn_undo = False
        self.waiting = m["waiting"]
        self._marks = {i: v for i, v in self._marks.items() if i < at}
        self.ev_i = at
        self._plan_items = m["plan"]
        self.plan_panel.set_items(m["plan"], live=False)
        self.ctx_ring.set_value(*m["ctx"])
        with s.cond:
            left = len(s.events)
        if not left and self.empty is None:              # volviste al primer mensaje y no queda nada
            self.empty = self.add(self._empty_state())
        if self.blocks and self.blocks[-1].has("actions") and s.run is None:
            self.blocks[-1].b_regen.show()               # la respuesta que queda al final se puede regenerar
        self.stick = True
        self.scroll.setUpdatesEnabled(True)
        sb = self.scroll.verticalScrollBar()
        QTimer.singleShot(0, lambda: sb.setValue(sb.maximum()))
        self.sync()
        self.changed.emit()
        return True

    def regenerate(self):
        s = self.session()
        if s:
            last = s.last_user()
            at = last["i"] if last else None
            err = s.regenerate()
            if err:
                QMessageBox.information(self, APP_NAME, err)
            self.reload_quiet(at)

    # ---- tus mensajes: editar y reenviar, reintentar, volver a un punto, conversación nueva desde aquí
    def can_rewind(self):
        s = self.session()
        if s is None:
            return None
        if s.run is not None or self.busy:
            self.main.toast(tr("Espera a que el agente termine (o detenlo) para volver a un mensaje anterior."),
                            icon_name="est_aviso", color=C["warn"])
            return None
        return s

    def _ask_files(self, s, i, question):
        """Confirma volver a un mensaje. Si el agente cambió archivos desde entonces, pregunta si deshacerlos.
        Devuelve True (deshacer), False (mantener) o None (cancelado)."""
        n = len(s.changes_since(i))
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setIcon(QMessageBox.Question)
        if not n:
            box.setText(question)
            ok = box.addButton(tr("Continuar"), QMessageBox.AcceptRole)
            box.addButton(tr("Cancelar"), QMessageBox.RejectRole)
            box.setDefaultButton(ok)
            box.exec()
            return False if box.clickedButton() is ok else None
        box.setText(question + "\n\n" + tr("Después de ese mensaje el agente cambió archivos (%d acciones). ¿Los devuelvo a como estaban?") % n)
        b_undo = box.addButton(tr("Deshacer esos cambios"), QMessageBox.AcceptRole)
        b_keep = box.addButton(tr("Mantener los archivos"), QMessageBox.NoRole)
        box.addButton(tr("Cancelar"), QMessageBox.RejectRole)
        box.setDefaultButton(b_undo)
        box.exec()
        c = box.clickedButton()
        return True if c is b_undo else False if c is b_keep else None

    def _restored(self, files):
        if files:
            for f in files:
                self.file_written.emit(f)
            self.main.toast((tr("Restaurado %d archivo.") if len(files) == 1 else tr("Restaurados %d archivos.")) % len(files),
                            icon_name="acc_refrescar", color=C["ok"])

    def _resend(self, i, text):
        s = self.can_rewind()
        if s is None:
            return
        if not core.SET.ready():
            return self.main.fix_not_ready()
        q = tr("Se quitarán las respuestas a partir de este mensaje y se volverá a enviar.") if text is None else \
            tr("Se quitará lo que vino después de este mensaje y se enviará la versión editada.")
        undo = self._ask_files(s, i, q)
        if undo is None:
            return
        try:
            err, files = s.resend(i, text, undo)
        except ValueError as e:
            return QMessageBox.information(self, APP_NAME, str(e))
        self.reload_quiet(i)
        self._restored(files)
        if err:
            return QMessageBox.information(self, APP_NAME, err)
        self.busy = True
        self.stick = True
        self.sync()
        self.changed.emit()

    def retry_from(self, i):
        self._resend(i, None)

    def edit_from(self, i, text):
        self._resend(i, text)

    def rewind_to(self, i):
        s = self.can_rewind()
        if s is None:
            return
        undo = self._ask_files(s, i, tr("Se quitarán este mensaje y todo lo que vino después. Tu mensaje volverá al cuadro de "
                                         "texto para que lo cambies o lo envíes de nuevo."))
        if undo is None:
            return
        try:
            old, files = s.rewind(i, undo)
        except ValueError as e:
            return QMessageBox.information(self, APP_NAME, str(e))
        self.reload_quiet(i)
        self._restored(files)
        self.input.setPlainText(old["text"])
        self.pending_imgs = [n for n in old["images"] if os.path.isfile(os.path.join(paths.IMG_DIR, n))]
        self._render_thumbs()
        if old["files"]:
            self.main.toast(tr("Los documentos adjuntos de ese mensaje no se recuperan: vuelve a añadirlos si los necesitas."),
                            icon_name="est_info", ms=8000)
        self.input.setFocus()
        self.input.moveCursor(QTextCursor.End)
        self.changed.emit()

    def fork_from(self, i):
        s = self.session()
        if s is None:
            return
        try:
            ns, text = s.fork(i)
        except ValueError as e:
            return QMessageBox.information(self, APP_NAME, str(e))
        self.open_session(ns.id)
        self.input.setPlainText(text)
        self.input.setFocus()
        self.input.moveCursor(QTextCursor.End)
        self.changed.emit()
        self.main.toast(tr("Nueva conversación desde ese punto; la original sigue igual."), icon_name="acc_nuevo", ms=5000)

    def _dismiss_banner(self):
        self._ban_dismissed = self._ban_key
        self._ban_want = False
        self._ban_timer.stop()
        self.banner.hide()

    def _hide_note(self, w, i):
        s = self.session()
        if s is not None:
            s.hide_event(i)
        w.hide()
        w.deleteLater()

    def send(self):
        text = self.input.toPlainText().strip()
        files = list(getattr(self, "pending_files", []))
        if self.busy:                        # trabajando: lo que escribes lo verá en su próximo paso (sin pararlo)
            s = self.session()
            if text and s is not None and s.steer(text):
                self.input.clear()
                self.stick = True
                self._render_queue(force=True)
            return
        if not text and not self.pending_imgs and not files:
            return
        if not core.SET.ready():
            return self.main.fix_not_ready()
        if self.main.llm.get("state") == "checking":          # recién abierto: en un momento se sabe si está encendido
            return QTimer.singleShot(300, self.send)
        if core.SET.snapshot()["llm_mode"] == "local" and self.main.llm.get("state", "off") in ("off", "loading"):
            # modelo apagado o encendiéndose: se enciende y el mensaje sale solo cuando esté listo (sin error rojo)
            if self.main.llm.get("state", "off") == "off":
                self.main.toggle_llm()
            self._queued = True
            self.main.toast(tr("Enciendo el modelo; tu mensaje se enviará en cuanto esté listo."), icon_name="est_cargando", ms=6000)
            return
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

    def _service_ready(self, name):
        """Botón «Continuar» de la ficha de un servicio recién conectado: avisa al agente."""
        if self.busy:
            return self.main.toast(tr("El agente sigue trabajando; díselo cuando termine."), icon_name="est_info")
        self.input.setPlainText(tr("Ya conecté %s: continúa.") % name)
        self.send()

    def _images_ready(self):
        """Botón «Continuar» de la tarjeta del generador de imágenes: avisa al agente de que ya puede crearlas."""
        if self.busy:
            return self.main.toast(tr("El agente sigue trabajando; díselo cuando termine."), icon_name="est_info")
        self.input.setPlainText(tr("Ya está instalado el generador de imágenes: continúa y crea la imagen."))
        self.send()

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
        state = win.windowState()                    # maximizada, a pantalla completa…: vuelve tal cual estaba
        win.hide()

        def grab():
            try:
                self._add_image(qimage=QImage.fromData(T.capture(1600)[0]))
            finally:
                if state & Qt.WindowFullScreen:
                    win.showFullScreen()
                elif state & Qt.WindowMaximized:
                    win.showMaximized()
                else:
                    win.showNormal()         # antes siempre así: una ventana maximizada volvía más pequeña
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
        self.queue_btn.setVisible(self.busy and bool(self.input.toPlainText().strip()))
        self.send_btn.setEnabled(self.busy or has)
        self.send_btn.setIcon(icon("trans_detener" if self.busy else "lista_subir", C["on_send"] if (self.busy or has) else C["faint"], 14 if self.busy else 16))
        self.send_btn.setToolTip(tr("Detener") if self.busy else tr("Enviar (Enter)"))

    def sync(self):
        cfg = core.SET.snapshot()
        if self.hint is not None:                   # el pie dice lo que hace el modo elegido (no siempre pregunta)
            self.hint.setText(HINT.get(cfg.get("mode"), HINT["ask"]) + " · " + tr("ratón a la esquina superior izquierda = detener el control"))
        llm = self.main.llm
        st = llm.get("state", "off")
        ext = cfg["llm_mode"] == "external"
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
        # el aviso se puede ocultar con la ×; vuelve a salir solo si cambia lo que dice
        self._ban_key = (st, why, self.ban_txt.text())
        if self._ban_dismissed is not None and self._ban_dismissed != self._ban_key:
            self._ban_dismissed = None
        self._ban_want = st not in ("ready", "checking") and self._ban_dismissed is None
        if not self._ban_want:
            self._ban_timer.stop()
            self.banner.hide()
        elif self.banner.isHidden() and not self._ban_timer.isActive():
            self._ban_timer.start()
        # mensaje en espera: se envía en cuanto el modelo está listo; si no llega a encenderse, se avisa
        if self._queued and st == "ready":
            self._queued = False
            QTimer.singleShot(0, self.send)
        elif self._queued and st == "off":
            self._queued = False
            self.main.toast(tr("El modelo no se pudo encender; tu mensaje sigue en el cuadro de texto."), icon_name="est_aviso", color=C["warn"])
        self.mode_chip.setText(MODE_LABEL.get(cfg["mode"], cfg["mode"]))
        self.mode_chip.setToolTip(A.MODES.get(cfg["mode"], ""))
        if getattr(self, "_chip_mode", None) != cfg["mode"]:      # un icono por modo; Automático, en color de aviso
            self._chip_mode = cfg["mode"]
            auto = cfg["mode"] == "auto"
            self.mode_chip.setIcon(icon(MODE_ICON.get(cfg["mode"], "est_bloqueado"), C["warn"] if auto else C["mut"], 13))
            self.mode_chip.setStyleSheet("QToolButton#chip { color:%s; border-color:%s; }" % (C["warn"], C["warn"]) if auto else "")
            if self.empty is not None and getattr(self.empty, "by_mode", False):
                self.empty.sub.setText(self._mode_subtitle(cfg["mode"]))
        if cfg["mode"] not in ("plan", "readonly"):
            self.exec_mode = cfg["mode"]          # al aprobar un plan se vuelve a este modo
        if cfg["mode"] in self.mode_actions:
            self.mode_actions[cfg["mode"]].setChecked(True)
            for k, a in self.mode_actions.items():      # con icono no se ve la marca: el modo actual, en negrita
                f = a.font()
                if f.bold() != (k == cfg["mode"]):
                    f.setBold(k == cfg["mode"])
                    a.setFont(f)
        eff = core.effort_of(cfg)
        label, desc = next((l, d) for k, l, d in core.EFFORTS if k == eff)
        ext = cfg["llm_mode"] == "external"
        m = core.active_model(cfg)
        name = ((cfg["external_model"] or tr("servidor externo")).split("/")[-1]) if ext else (core.model_title(m) if m else tr("Elegir modelo"))
        self._chip_name, self._chip_label = name, EFFORT_CHIP.get(eff, label)     # «· esfuerzo alto» (antes, solo «Alto»)
        self._fit_model_chip()                                          # modelo · esfuerzo (se cambian en el mismo menú)
        why = core.effort_support(cfg)[1]
        self.model_chip.setToolTip(tr("%s\nEsfuerzo %s: %s\nPulsa para cambiar de modelo o de esfuerzo.") % (
            ("%s · %s" % (core.model_title(m), core.model_quant(m))) if (m and not ext) else name, label.lower(), desc)
            + (("\n" + why) if why else ""))
        if not self.rec_bar.isVisible():         # mientras se dicta, la caja dice «Escuchando…» / «Pasando tu voz a texto…»
            self.input.setPlaceholderText(tr("Escribe para corregirle o añadir algo; lo verá en su próximo paso") if self.busy else
                                          tr("Pide algo sobre el proyecto…") if self.project_id else tr("Escribe un mensaje…"))
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
        ev.setSpacing(18)                    # el mismo aire que la bienvenida del Chat
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
        self._squeezed = False          # los paneles laterales miden menos de lo que quiere el usuario porque no caben
        self._fitting = False

    # ---- distribucion de paneles
    PANELS = (("left", "tree", "w_tree"), ("chat", "agent", "w_agent"))

    def _term_key(self):
        return "w_term" if self.lay["term_pos"] == "right" else "h_term"

    def _size_of(self, split, w, key):
        if w.isHidden() or not self._sized:
            return int(w.property("last_size") or self.lay[key])
        return split.sizes()[split.indexOf(w)] or int(self.lay[key])

    def layout_state(self, actual=False):
        """Estado actual para guardarlo en los ajustes. Si los paneles están encogidos porque no caben (el navegador o el
        lienzo ocupan media ventana), se guarda el ancho que el usuario les dio, no el encogido; actual=True: lo que miden
        ahora mismo (el usuario acaba de mover un divisor)."""
        st = dict(self.lay)
        for attr, k, wk in self.PANELS:
            w = getattr(self, attr)
            st[k] = not w.isHidden()
            st[wk] = int(self.lay[wk]) if (self._squeezed and not actual and not w.isHidden()) else self._size_of(self.split, w, wk)
        st["term"] = not self.term.isHidden()
        st[self._term_key()] = self._size_of(self.center, self.term, self._term_key())
        return st

    def _refit(self):
        """Al cambiar el ancho del espacio de trabajo (se abre o se cierra el navegador o el lienzo, o cambia la ventana), el
        explorador y el agente vuelven al ancho que les dio el usuario y el resto va al editor. Si no caben, se encogen en
        proporción solo mientras falte sitio: antes se quedaban encogidos para siempre al cerrar el navegador."""
        if not getattr(self, "_sized", False) or self.stack.currentIndex() != 1 or self._fitting:
            return
        tot = self.split.width() - self.split.handleWidth() * (self.split.count() - 1)
        if tot < 300:
            return
        # sin sitio para el editor: el explorador se pliega solo (y vuelve cuando lo hay, si el usuario no lo cerró él)
        # (solo si ni encogiendo el explorador y el agente a su mínimo cabe el editor; si cabe, se encogen en proporción)
        agent_w = self.AGENT_MIN if not self.chat.isHidden() else 0
        tree_w = self.TREE_MIN
        if not self.left.isHidden() and tot - agent_w - tree_w < self.EDITOR_MIN:
            self.left.hide()
            self._tree_auto = True
            self.main.sync()
        elif getattr(self, "_tree_auto", False) and self.left.isHidden() and self.lay.get("tree") \
                and tot - agent_w - tree_w >= self.EDITOR_MIN + 80:
            self.left.show()
            self._tree_auto = False
            self.main.sync()
        sides = [(getattr(self, attr), int(self.lay[wk])) for attr, k, wk in self.PANELS if not getattr(self, attr).isHidden()]
        room = tot - max(260, self.center.minimumSizeHint().width())
        want = sum(s for w, s in sides)
        self._squeezed = bool(sides) and want > room
        if self._squeezed:
            sides = [(w, max(w.minimumWidth(), int(s * max(room, 0) / float(want)))) for w, s in sides]
        given = dict(sides)
        sizes = [given.get(self.split.widget(i), 0) for i in range(self.split.count())]
        sizes[self.split.indexOf(self.center)] = max(1, tot - sum(sizes))
        if sizes != self.split.sizes():
            self._fitting = True
            try:
                self.split.setSizes(sizes)
            finally:
                self._fitting = False

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._refit()

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
        QTimer.singleShot(0, self._refit)          # sin sitio para el editor desde el principio: el explorador se pliega

    def showEvent(self, e):
        super().showEvent(e)
        if not self._sized:
            QTimer.singleShot(0, self._apply_sizes)

    def _moved(self):
        if self._sized:
            self.lay.update(self.layout_state(actual=True))    # el usuario movió un divisor: ese es el ancho que quiere
            self._squeezed = False
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

    EDITOR_MIN, TREE_MIN, AGENT_MIN = 380, 160, 300      # anchos mínimos: si no caben, el explorador se pliega solo (_refit)

    def toggle_tree(self, on=None):
        self._tree_auto = False                       # lo decide el usuario: ya no se abre ni se cierra solo
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
    engine = Signal(object)       # comprobación del motor (oferta de aceleración) o el fin de su instalación


# ---------------------------------------------------------------- ventana principal
class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_icon())
        self.resize(1320, 840)
        self.setMinimumSize(960, 600)
        self.llm = {"state": "checking"}      # hasta la primera consulta: sin avisos de «apagado» que parpadean al abrir
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
        from .canvas import CanvasBridge         # el lienzo devuelve al agente una captura de lo que muestra
        self.canvas_bridge = CanvasBridge(self)
        T.CANVAS = self.canvas_bridge
        from .browser import HiddenSearch, _view_class
        if _view_class():                       # búsquedas sin clave con el motor del navegador (si este equipo lo tiene)
            self.searcher = HiddenSearch()
            T.SEARCHER = self.searcher
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
        self.sig.engine.connect(self._engine_event)
        QTimer.singleShot(12000, self.check_engine)                                # ¿una gráfica que el motor no aprovecha?
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
        self.sec_convs.extra.addWidget(tbtn("acc_anadir", tr("Nueva conversación del proyecto (Ctrl+N)"), self.new_conversation, size=13))
        kl.addWidget(self.sec_convs)
        self.csearch = QLineEdit()                     # buscar en las conversaciones del proyecto (antes no había)
        self.csearch.setObjectName("search")
        self.csearch.setPlaceholderText(tr("Buscar en las conversaciones del proyecto"))
        self.csearch.setClearButtonEnabled(True)
        self.csearch.textChanged.connect(lambda: (setattr(self, "_sig_code", None), self.refresh_lists()))
        kl.addWidget(self.csearch)
        self.sec_projects.toggled.connect(lambda on: self._fold_section(self.plist, on))
        self.sec_convs.toggled.connect(lambda on: (self._fold_section(self.clist, on), self.csearch.setVisible(on)))
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
        self.status_lbl.setTextFormat(Qt.RichText)
        self.status_lbl.linkActivated.connect(lambda sid: self.go_to_session(sid))   # «Trabajando en …»: ir a esa conversación
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
            b.setObjectName("paneBtn")                # visible = marcado y con fondo (no solo el color del icono)
            b.setCheckable(True)
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
        self.tray.messageClicked.connect(self._tray_message_clicked)
        self.tray.show()
        self._running, self._was_busy, self._notify_sid = {}, False, None
        self.runs_t = QTimer(self, interval=1000, timeout=self._watch_runs)
        self.runs_t.start()

    def _show(self):
        if self.isMinimized() or not self.isVisible():
            self.showMaximized()
        self.raise_()
        self.activateWindow()
        if osys.WIN:                          # Windows no deja que una ventana de fondo se ponga delante sola: parpadea
            QApplication.alert(self, 2000)

    def _check_settings_saved(self):
        """Si un guardado de ajustes falló (archivo bloqueado por otro programa), se reintenta y se avisa una vez:
        los cambios siguen en memoria, no se pierden en silencio como antes."""
        err = core.SET.save_error
        if err and not core.SET.retry_save():
            if not getattr(self, "_save_err_told", False):
                self._save_err_told = True
                self.toast(tr("No pude guardar tus ajustes (%s). Tus cambios siguen aquí y lo vuelvo a intentar solo.") % core.SET.save_error,
                           ms=15000, icon_name="est_aviso", color=C["warn"])
        elif err and getattr(self, "_save_err_told", False):
            self._save_err_told = False
            self.toast(tr("Ajustes guardados."), ms=3000)

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

    def offer_crash_report(self, d, previous=False):
        """Aviso discreto tras un error inesperado: «Enviar informe» abre el diálogo con el error ya escrito (se revisa antes)."""
        from . import feedback as FB
        if not d:
            return
        FB.mark_offered()
        text = tr("La última vez %s tuvo un error inesperado. Si nos envías el informe, podremos corregirlo.") % APP_NAME if previous else \
            tr("%s tuvo un error inesperado. Si nos envías el informe, podremos corregirlo.") % APP_NAME
        self.toast(text, tr("Enviar informe…"), lambda: FeedbackDialog(self, "cierre", FB.crash_text(d), title=FB.crash_title(d)).exec(),
                   ms=20000, icon_name="est_aviso", color=C["warn"])

    def notify_pending(self, text, ts, sid=None):
        if core.SET.snapshot().get("notifications", True) and not self.isActiveWindow() and ts > time.time() - 10:
            self._notify_sid = sid
            self.tray.showMessage(APP_NAME, tr("El agente espera tu aprobación: %s") % text, QSystemTrayIcon.Information, 6000)
            QApplication.alert(self, 0)             # el icono de la barra de tareas parpadea hasta que vuelvas

    def _watch_runs(self):
        """Cada segundo: el tiempo que lleva trabajando (arriba) y, si una conversación termina mientras miras otra cosa,
        un aviso (en la bandeja y en la barra de tareas si la ventana no está delante)."""
        active = {sid: getattr(s.run, "t0", time.time()) for sid, s in list(core.SESSIONS.items()) if s.run is not None}
        for sid, t0 in list(self._running.items()):
            if sid not in active:
                self._running.pop(sid)
                self._finished(sid, time.time() - t0)
        for sid, t0 in active.items():
            self._running.setdefault(sid, t0)
        if active or self._was_busy:
            self._sync_status()
        self._was_busy = bool(active)

    def _finished(self, sid, dur):
        s = core.SESSIONS.get(sid)
        if s is None or s.data.get("task") or dur < 15 or not core.SET.snapshot().get("notifications", True):
            return                                   # las tareas programadas avisan por su cuenta
        here = self.current_panel().sid == sid
        if self.isActiveWindow() and here:
            return
        title = s.title if s.events else APP_NAME
        if not self.isActiveWindow():
            self._notify_sid = sid
            self.tray.showMessage(APP_NAME, tr("Terminó «%s» (trabajó %s).") % (title, CV.fmt_secs(dur)), QSystemTrayIcon.Information, 8000)
            QApplication.alert(self, 0)
        elif not s.data.get("project"):
            self.toast(tr("Terminó «%s».") % title, tr("Ver"), lambda sid=sid: self.open_task_result(sid), ms=9000,
                       icon_name="ui_check", color=C["ok"])

    def _tray_message_clicked(self):
        sid, self._notify_sid = getattr(self, "_notify_sid", None), None
        s = core.SESSIONS.get(sid) if sid else None
        if s is not None and not s.data.get("project") and self.current_panel().sid != sid:
            self.open_task_result(sid)
        else:
            self._show()

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
        veil = self._side_veil()                         # un velo sobre lo de detrás: se ve que la barra flota encima
        veil.setGeometry(self._veil_geometry())
        veil.show()
        veil.raise_()
        self.side.show()
        self.side.raise_()
        self._peek_away = 0.0
        self._peek_t.start()

    def _side_veil(self):
        v = getattr(self, "_sveil", None)
        if v is None:
            v = self._sveil = Veil(self.centralWidget(), 110 if QColor(C["bg"]).lightness() < 128 else 50)
            v.clicked.connect(self._peek_close)          # un clic fuera de la barra la cierra
            v.hide()
        return v

    def _veil_geometry(self):
        g = self.hsplit.geometry()
        top = self.head.height() + 1
        return QRect(g.x(), g.y() + top, g.width(), g.height() - top)

    def _peek_check(self):
        if not self._peek:
            return self._peek_t.stop()
        self.side.setGeometry(self._peek_geometry())    # sigue a la ventana si cambia de tamaño
        if getattr(self, "_sveil", None) is not None:
            self._sveil.setGeometry(self._veil_geometry())
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
        if getattr(self, "_sveil", None) is not None:
            self._sveil.hide()
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
        return Toast(self.centralWidget(), text, action, on_action, ms, icon_name, color, above=self._composer_top)

    def _composer_top(self):
        """Altura, dentro de la ventana, donde empieza el cuadro de mensaje del panel a la vista (None si no se ve)."""
        box = getattr(self.current_panel(), "input", None)
        if box is None or not box.isVisible():
            return None
        frame = box.parentWidget() or box
        return frame.mapTo(self.centralWidget(), QPoint(0, 0)).y()

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
        try:                                         # ¿cómo acabó la última actualización «solo con los cambios»?
            last = updater.patch_result()
        except Exception:
            last = None
        if last and last.get("state") != "ok":
            # no se aplicó (la versión anterior sigue intacta): esta vez se descargará el paquete completo
            self.toast(tr("La actualización rápida no se pudo aplicar; %s sigue como estaba y descargará la versión completa.") % APP_NAME,
                       ms=12000, icon_name="est_aviso", color=C["warn"])
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
        if not self.side_pinned():           # con el teclado la barra se fija (al asomarse se cerraria sin el raton)
            self.set_sidebar(True)
        if self.mode == "code" and self.code.project:  # en Code: las conversaciones del proyecto
            self.sec_convs.set_open(True, emit=True)
            self.csearch.show()
            self.csearch.setFocus()
            self.csearch.selectAll()
            return
        if self.mode != "chat":
            self.set_mode("chat")
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
        cq = self.csearch.text().strip().lower()
        cs = [s for s in core.sessions_for(pid) if not cq or cq in s.search_text()] if pid else []
        sig = ([(p["id"], p["name"]) for p in cfg["projects"]], pid, [(s.id, s.title, s.run is not None) for s in cs], self.code.chat.sid, cq)
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
            fill_history(self.clist, cs, self.code.chat.sid, cq, folded=self.folded)     # corto: cabe en la barra (como «Aún no hay proyectos»)

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
        kind, why = core.effort_support(cfg)
        if why:                                          # qué hace de verdad el esfuerzo con este modelo
            note = QWidgetAction(em)
            nl = QLabel(why)
            nl.setWordWrap(True)
            nl.setFixedWidth(300)
            nl.setObjectName("faint")
            nl.setContentsMargins(12, 6, 12, 6)
            note.setDefaultWidget(nl)
            em.addAction(note)
            em.addSeparator()
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
        self._check_settings_saved()
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

    def check_engine(self):
        """¿Tiene este equipo una gráfica que el motor instalado no aprovecha? Se mira en segundo plano y, si la hay, se
        ofrece instalar el motor acelerado (una vez por recomendación; Ajustes › Rendimiento permite que no se ofrezca)."""
        def work():
            try:
                self.sig.engine.emit(("offer", core.engine_offer()))
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def _engine_event(self, ev):
        kind, data = ev
        if kind == "offer" and data:
            core.SET.update({"engine_offer_seen": data["key"]})
            name = core.ENGINE_NAMES.get(data["backend"], data["backend"])
            self.toast(tr("Tu equipo tiene %s: con el motor de %s el modelo irá mucho más rápido.") % (data.get("gpu") or tr("una gráfica"), name),
                       tr("Instalar"), lambda d=data: self.install_engine(d["backend"], d.get("cuda") or ""), ms=30000, icon_name="prof_cpu")
        elif kind == "done":
            backend, err = data
            if err:
                self.toast(tr("No se pudo instalar el motor acelerado: %s") % err, ms=12000, icon_name="est_aviso", color=C["warn"])
                return
            if core.LLM_MGR.mine():
                self.toast(tr("Motor de %s instalado. Se usará al volver a encender el modelo.") % core.ENGINE_NAMES.get(backend, backend),
                           tr("Reiniciar ahora"), self._restart_model, ms=20000, icon_name="ui_check", color=C["ok"])
            else:
                self.toast(tr("Motor de %s instalado: se usará al encender el modelo.") % core.ENGINE_NAMES.get(backend, backend),
                           ms=9000, icon_name="ui_check", color=C["ok"])

    def install_engine(self, backend, cuda=""):
        """Descarga e instala en segundo plano el motor para esta gráfica; el que funciona sigue hasta que el nuevo está listo."""
        if getattr(self, "_engine_job", False):
            return
        self._engine_job = True
        self.toast(tr("Descargando el motor de %s… Puedes seguir usando Jayth.") % core.ENGINE_NAMES.get(backend, backend), ms=8000, icon_name="acc_descargar")

        def work():
            err = ""
            try:
                from . import provision as P
                exe, tag = P.install_llama(backend, cuda)
                core.SET.update({"backend_auto": True})
                core.engine_installed(exe, tag, backend, cuda)
            except Exception as e:
                err = str(e)
            self._engine_job = False
            self.sig.engine.emit(("done", (backend, err)))
        threading.Thread(target=work, daemon=True).start()

    def _restart_model(self):
        if any(s.run for s in core.SESSIONS.values()):
            return self.toast(tr("Espera a que el agente termine para reiniciar el modelo."), icon_name="est_aviso", color=C["warn"])
        core.LLM_MGR.stop()
        err = core.LLM_MGR.start()
        if err:
            self.toast(err, icon_name="est_aviso", color=C["warn"])
        self.poll()

    def _got_status(self, st):
        self._polling = False
        self.llm = st
        while core.LLM_MGR.gpu_events:                   # la gráfica falló al cargar el modelo: sigue en el procesador
            kind, note = core.LLM_MGR.gpu_events.pop(0)
            if kind == "cpu":
                self.toast(tr("La gráfica no pudo cargar el modelo (%s). Lo enciendo en el procesador: irá más lento, pero funciona.") % (note or "?"),
                           ms=15000, icon_name="est_aviso", color=C["warn"])
        cfg = core.SET.snapshot()
        mine = core.LLM_MGR.mine()
        # precalentamiento: en cuanto el modelo propio esta listo, procesar instrucciones y herramientas en segundo plano
        if st.get("state") == "ready" and mine and cfg["warmup"] and not core.LLM_MGR.warm and cfg["llm_mode"] == "local" \
                and not any(s.run for s in core.SESSIONS.values()):      # si ya hay una tarea en marcha, ella misma lo deja leído
            try:                                   # con las instrucciones y herramientas de la conversación abierta
                open_s = core.SESSIONS.get(getattr(self.current_panel(), "sid", None))
            except Exception:
                open_s = None
            threading.Thread(target=core.LLM_MGR.warmup, args=(open_s,), daemon=True).start()
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
        self._sync_status()
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
            b.setChecked(not w.isHidden())
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

    @staticmethod
    def _engine_label(cfg):
        """Con qué trabaja el agente, en palabras del usuario: el servicio o el modelo (antes, «externo» o «local»)."""
        if cfg["llm_mode"] == "external":
            pv = next((p for p in cfg.get("providers") or [] if p.get("id") == cfg.get("external_provider")), None)
            name = (pv or {}).get("name") or (cfg.get("external_model") or "").split("/")[-1] or tr("servicio por API")
        else:
            m = core.active_model(cfg)
            name = core.model_title(m) if m else tr("modelo de este equipo")
        return name if len(name) <= 26 else name[:25].rstrip() + "…"

    def _sync_status(self):
        """El punto de estado de arriba: listo, cargando… o «Trabajando · Claude · 1:12» (con lo que lleva). Si la tarea en
        marcha es de otra conversación, dice cuál, y un clic lleva a ella."""
        import html as _h
        cfg = core.SET.snapshot()
        st = self.llm.get("state", "off")
        label = _h.escape(self._engine_label(cfg))
        col, txt = {"ready": (C["ok"], tr("Listo · %s") % label), "loading": (C["warn"], tr("Cargando…")),
                    "checking": (C["faint"], tr("Comprobando…"))}.get(st, (C["faint"], tr("Apagado")))
        busy = [s for s in list(core.SESSIONS.values()) if s.run is not None]
        tip = ""
        if st == "ready" and self.llm.get("warm") == "warming":
            col, txt = C["warn"], tr("Preparando el agente…")
        elif st == "ready" and busy:                     # no «Listo» mientras trabaja: cuánto lleva
            mine = self.current_panel().session()
            s = mine if (mine is not None and mine.run is not None) else busy[0]
            sec = int(max(0, time.time() - getattr(s.run, "t0", time.time())))
            clock = ("%d:%02d" % divmod(sec, 60)) if sec < 3600 else ("%d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60))
            if s is mine:
                txt, tip = "%s · %s" % (tr("Trabajando · %s") % label, clock), tr("Tiempo que lleva trabajando en esta tarea")
            else:                                        # trabaja en otra conversación (p. ej. una de Code): cuál, y clic para ir
                t = s.title if len(s.title) <= 28 else s.title[:27].rstrip() + "…"
                txt = "<a href='%s' style='color:%s;text-decoration:none'>%s</a> · %s" % (
                    s.id, C["tx"], tr("Trabajando en «%s»") % _h.escape(t), clock)
                tip = tr("El agente trabaja en otra conversación. Pulsa para ir a ella.")
            col = C["acc"]
        self.status_lbl.setText("<span style='color:%s'>●</span> <span style='color:%s'>%s</span>" % (col, C["mut"], txt))
        self.status_lbl.setToolTip(tip)

    def go_to_session(self, sid):
        """Lleva a una conversación esté donde esté: en Chat o en su proyecto de Code."""
        s = core.SESSIONS.get(sid)
        if s is None:
            return
        pid = s.data.get("project")
        if not pid:
            return self.open_task_result(sid)
        p = core.project(core.SET.snapshot(), pid)
        if not p:
            return
        self._show()
        if self.mode != "code":
            self.set_mode("code")
        if not self.code.project or self.code.project["id"] != pid:
            self.code.set_project(p)
        self.code.chat.open_session(sid)
        self.sync()

    def toggle_llm(self):
        if not core.SET.ready():
            return self.fix_not_ready()
        if self.llm.get("state") == "checking":
            return                              # aún no se sabe si está encendido (es un instante al abrir)
        if self.llm.get("state", "off") == "off":
            cfg = core.SET.snapshot()
            plan = core.memory_plan(cfg) if cfg.get("llm_mode") != "external" else None      # antes de cargar: la libre real
            err = core.LLM_MGR.start()
            if err:
                return QMessageBox.warning(self, APP_NAME, err)
            self.llm = {"state": "loading"}
            QTimer.singleShot(1500, lambda: self.memory_warning(plan))
        else:
            core.LLM_MGR.stop()
            self.llm = {"state": "off"}
        self.sync()
        QTimer.singleShot(800, self.poll)

    def memory_warning(self, plan=None):
        """Si el modelo activo no cabe bien en la memoria, lo dice y propone qué hacer: si no cabe en el equipo, una vez por
        modelo; si cabe pero ahora otros programas ocupan la memoria, cada vez que pase."""
        cfg = core.SET.snapshot()
        m = core.active_model(cfg)
        if not m or cfg.get("llm_mode") == "external":
            return
        plan = plan or core.memory_plan(cfg, m)
        key = "%s|%s" % (m.get("id"), plan["level"])
        if plan["level"] == "ok" or (plan["level"] != "busy" and key in (cfg.get("memory_warned") or [])):
            return
        if plan["level"] != "busy":
            core.SET.update({"memory_warned": (cfg.get("memory_warned") or [])[-20:] + [key]})
        gb = lambda n: "%s %s" % (i18n.number(n / (1 << 30)), i18n.unit("GB"))
        if plan["level"] == "busy":
            return self.toast(tr("«%s» necesita unos %s y ahora mismo hay %s libres: cierra programas pesados (navegador con muchas "
                                 "pestañas, juegos…) para que no lea del disco y vaya lento.") % (
                core.model_title(m) or m.get("name"), gb(plan["need"]), gb(plan["free"])), icon_name="est_aviso", ms=12000)
        if plan["level"] == "no":
            txt = tr("«%s» necesita unos %s y tu equipo tiene %s: no cabe en la memoria y escribirá muy despacio. Elige una "
                     "variante más pequeña o un modelo con menos parámetros.") % (core.model_title(m) or m.get("name"), gb(plan["need"]), gb(plan["room"]))
        else:
            txt = tr("«%s» necesita unos %s de los %s de tu equipo: cierra otros programas pesados para que no vaya lento, o elige "
                     "una variante más pequeña.") % (core.model_title(m) or m.get("name"), gb(plan["need"]), gb(plan["room"]))
        self.toast(txt, tr("Ver modelos"), self.models, icon_name="est_aviso", ms=15000)

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
        self.code.tabs.autosave_all()               # con el autoguardado activo, los cambios se guardan sin preguntar
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
        self.hide()                                  # guardar lo leído puede tardar unos segundos: sin ventana a la vista
        core.shutdown()
        self.tray.hide()
        e.accept()
        close_single_instance()                      # un Jayth que se abra ahora (reinicio, actualización) ya no le pregunta a este
        reopen = getattr(self, "_restart", False)
        try:
            upd = updater.ready() if updater.can_update_in_background() else None
        except Exception:
            upd = None
        try:
            if upd and (reopen or core.SET.snapshot().get("auto_install_updates", True)):
                # la versión descargada se instala ahora que Jayth se cierra: en silencio al salir, o con una ventanita
                # «Actualizando…» y volviendo a abrirlo si se pidió reiniciar
                if updater.install_when_closed(upd, reopen=reopen) is not False:
                    reopen = False                   # (False: no había nada válido que instalar; si se pidió reiniciar, se reabre tal cual)
        except Exception:
            pass
        if reopen:                                   # reinicio sin actualización (p. ej. cambio de idioma)
            from PySide6.QtCore import QProcess
            argv = osys.launch_argv()
            QProcess.startDetached(argv[0], argv[1:])
        QApplication.quit()


# ---------------------------------------------------------------- una sola ventana de Jayth
_INSTANCE = {"server": None, "window": None}


def _instance_name():
    """Nombre del canal local: uno por usuario y carpeta de datos (las pruebas con otro JAYTH_HOME no chocan)."""
    import hashlib, getpass
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    key = "%s|%s" % (user, os.path.normcase(os.path.abspath(paths.HOME)))
    return "jayth-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def single_instance(show=True, wait=4000):
    """¿Ya hay un Jayth abierto con estos datos? Entonces le pide que se muestre y devuelve False: este debe cerrarse.
    Si no, se queda escuchando para los siguientes y devuelve True.

    Antes cada clic en el icono abría otra copia completa. Cada una llevaba sus propios ajustes en memoria y la última
    en guardar borraba lo que hubieran cambiado las demás (así desaparecieron proyectos y modelos de un usuario).
    Si el Jayth abierto no contesta (colgado o cerrándose), este arranca igualmente: los ajustes ya se mezclan al guardar."""
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    name = _instance_name()
    s = QLocalSocket()
    s.connectToServer(name)
    if s.waitForConnected(700):
        s.write(b"show\n" if show else b"ping\n")
        s.flush()
        s.waitForBytesWritten(700)
        reply = b""
        end = time.time() + wait / 1000.0
        while time.time() < end and b"\n" not in reply:
            if s.waitForReadyRead(200):
                reply += bytes(s.readAll())
            elif s.state() != QLocalSocket.ConnectedState:
                break
        s.disconnectFromServer()
        if reply.startswith((b"ok", b"wait")):      # «wait»: el otro todavía está arrancando y se mostrará solo
            return False
    srv = QLocalServer()
    srv.setSocketOptions(QLocalServer.UserAccessOption)
    if not srv.listen(name):
        QLocalServer.removeServer(name)          # restos de un cierre brusco (Linux/macOS dejan el archivo del canal)
        if not srv.listen(name):
            return True                          # sin canal: Jayth funciona igual, solo que sin esta protección

    def on_conn():
        while srv.hasPendingConnections():
            c = srv.nextPendingConnection()

            def answer(c=c):
                msg = bytes(c.readAll())
                w = _INSTANCE["window"]
                if b"show" in msg and w is not None:
                    w._show()
                c.write(b"ok\n" if w is not None or b"ping" in msg else b"wait\n")
                c.flush()
                c.disconnectFromServer()
            c.readyRead.connect(answer)
    srv.newConnection.connect(on_conn)
    _INSTANCE["server"] = srv
    return True


def close_single_instance():
    srv = _INSTANCE["server"]
    _INSTANCE["server"] = None
    _INSTANCE["window"] = None
    if srv is not None:
        try:
            srv.close()
        except Exception:
            pass


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
    name = {"pt": "qtbase_pt_BR", "zh": "qtbase_zh_CN"}.get(i18n.LANG, "qtbase_" + i18n.LANG)     # portugués de Brasil, chino simplificado
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
    # la guía que consulta el agente sobre la propia app (jayth_guide), en el idioma de la interfaz
    ok("guide", lambda: (len(importlib.import_module("jayth.guide").sections()) >= 20 and "jayth_guide" in T.TOOLS) or "falta la guía de Jayth")
    # generador de imágenes: catálogo y la parte de la interfaz (sin descargar nada)
    def images():
        IG = importlib.import_module("jayth.imagegen")
        importlib.import_module("jayth.imagen_ui")
        bad = [f["file"] for m in IG.MODELS for f in m["files"] if not f["size"] or len(f["sha256"]) != 64]
        return ("faltan datos de " + ", ".join(bad)) if bad else ("generate_image" in T.TOOLS or "falta la herramienta generate_image")
    ok("images", images)

    def connectors():                       # catálogo de servicios, inicio de sesión y bóveda cifrada (sin conectarse a nada)
        CN = importlib.import_module("jayth.conectores")
        importlib.import_module("jayth.conectores_ui")
        importlib.import_module("jayth.oauth")
        bad = [c["id"] for c in CN.CATALOG if not c["url"].startswith("https://")]
        if bad or len({c["id"] for c in CN.CATALOG}) != len(CN.CATALOG):
            return "catálogo de servicios incorrecto: " + ", ".join(bad)
        BV = importlib.import_module("jayth.boveda")
        BV.put("autodiagnostico", {"ok": 1})
        good = BV.get("autodiagnostico") == {"ok": 1}
        BV.delete("autodiagnostico")
        return ("connect_service" in T.TOOLS and good) or "la bóveda de credenciales no funciona"
    ok("connectors", connectors)

    def knowledge():                        # conocimiento local (SQLite) y ajuste medido del motor
        import sqlite3
        KN = importlib.import_module("jayth.conocimiento")
        importlib.import_module("jayth.ajuste")
        sqlite3.connect(":memory:").execute("SELECT 1")
        return (len(KN.chunks_of("línea de prueba\n" * 400)) > 1 and "search_knowledge" in T.TOOLS) or "falta el conocimiento local"
    ok("knowledge", knowledge)
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

    def instance_channel():                   # el canal que evita abrir dos copias de Jayth (QtNetwork en el paquete)
        from PySide6.QtNetwork import QLocalServer
        return _instance_name().startswith("jayth-") and QLocalServer is not None or "sin canal"
    ok("single_instance", instance_channel)

    def update_parts():                       # actualizaciones con solo los cambios: el módulo va en el paquete y la
        from . import parches                 # comprobación que usa el intercambio de carpetas contesta bien
        code = updater.verify_install(__version__)
        return (code == 0 and updater.verify_install("0.0.0") == 3 and callable(parches.stage)) or "verify_install = %s" % code
    ok("update_parts", update_parts)

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
    if "--selftest" not in sys.argv and "--allow-multiple" not in sys.argv:
        if not single_instance(show="--minimized" not in sys.argv):
            sys.exit(0)                    # ya estaba abierto: se trajo esa ventana al frente
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
    from . import feedback as FB                # errores inesperados: se guardan y se ofrece enviarlos (nunca solos)
    FB.install_crash_capture(app, lambda d: QTimer.singleShot(0, lambda: getattr(app, "_main", None) and app._main.offer_crash_report(d)))
    try:
        recovered = core.recover_projects()      # proyectos que faltaban en la lista pero tienen conversaciones
    except Exception:
        recovered = []
    w = Main()
    app._main = w
    _INSTANCE["window"] = w
    if recovered:
        QTimer.singleShot(2500, lambda: w.toast(tr("Recuperé estos proyectos que faltaban en la lista: %s.") % ", ".join(recovered), ms=10000))
    if FB.pending_crash():                       # el arranque anterior acabó con un error: se ofrece una vez
        QTimer.singleShot(4000, lambda: w.offer_crash_report(FB.pending_crash(), previous=True))
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
        QTimer.singleShot(3000, w.memory_warning)
    if cfg.get("knowledge_auto", True) and cfg.get("knowledge_folders"):      # conocimiento: lee solo lo que cambió
        def _knowledge():
            from . import conocimiento as KN
            if KN.installed() and KN.folders():
                KN.start_index()
        QTimer.singleShot(20000, _knowledge)
    sys.exit(app.exec())
