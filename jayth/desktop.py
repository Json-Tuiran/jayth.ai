"""Aplicacion de escritorio Jayth (Qt). Dos modos:
- Chat: conversaciones para cualquier tarea.
- Code: proyectos con arbol de archivos, editor, terminal y el agente trabajando dentro de la carpeta del proyecto."""
import os, sys, json, uuid, time, shutil, threading, ctypes, datetime
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QSize, QPoint, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PySide6.QtGui import QPixmap, QImage, QKeySequence, QShortcut, QGuiApplication, QActionGroup, QCursor, QTransform, QFont
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
                               QListWidget, QListWidgetItem, QScrollArea, QFrame, QPlainTextEdit, QFileDialog, QMessageBox, QMenu,
                               QSystemTrayIcon, QSizePolicy, QToolButton, QInputDialog, QLineEdit, QStackedWidget, QSplitter,
                               QGraphicsOpacityEffect, QAbstractButton, QComboBox)
from . import APP_NAME, core, paths, osys, agent as A, tools as T
if osys.WIN:
    from ctypes import wintypes
from . import theme
from .theme import C, restyle, make_icon, icon, pix
from .wizard import SetupWizard, ModelsDialog, btn, lbl, set_icon, run_bg
from .settings_ui import SettingsDialog
from .codeview import EditorTabs, FileTree, Terminal, ProjectDialog
from .feedback import FeedbackDialog
from . import updater

MODE_LABEL = {k: v.split(":")[0] for k, v in A.MODES.items()}
CODE_NAME = APP_NAME + " Code"
SHOW_IN = "Mostrar en el Explorador" if osys.WIN else ("Mostrar en el Finder" if osys.MAC else "Abrir la carpeta")


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
    w = QPlainTextEdit()
    w.setObjectName("mono")
    w.setReadOnly(True)
    w.setPlainText(text)
    if kind:
        w.setProperty("kind", kind)
    lines = min(text.count("\n") + 1 + len(text) // 110, 60)
    w.setFixedHeight(min(max_h, 18 * lines + 16))
    return w


def md_label(text=""):
    l = QLabel()
    l.setTextFormat(Qt.MarkdownText)
    l.setWordWrap(True)
    l.setOpenExternalLinks(True)
    l.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
    l.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    l.setStyleSheet("font-size: 10.5pt;")
    l.setText(text)
    return l


class Clickable(QWidget):
    clicked = Signal()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()


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
        h.addWidget(tbtn("ui_cerrar", "Cerrar", self.close_, size=11), 0, Qt.AlignTop)
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
    def __init__(self, path, max_w=600, max_h=380):
        super().__init__()
        self.path = path
        pm = QPixmap(path)
        if not pm.isNull():
            self.setPixmap(pm.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Clic para abrir a tamaño completo")

    def mousePressEvent(self, e):
        if os.path.isfile(self.path):
            osys.open_path(self.path)


def note(text, error=False):
    f = QFrame()
    f.setObjectName("errBox" if error else "noteBox")
    h = QHBoxLayout(f)
    h.setContentsMargins(12, 8, 12, 8)
    h.addWidget(pix_label("est_error" if error else "est_info", C["bad"] if error else C["mut"]), 0, Qt.AlignTop)
    t = lbl(text)
    t.setStyleSheet("color:%s" % (C["bad"] if error else C["mut"]))
    h.addWidget(t, 1)
    return f


def fill_history(lst, sessions, current, query="", empty_text="Tus conversaciones aparecerán aquí"):
    """Rellena una lista con conversaciones agrupadas por fecha (Hoy, Ayer, …)."""
    lst.blockSignals(True)
    lst.clear()
    today = datetime.date.today()
    last = None
    for s in sessions:
        d = (today - datetime.date.fromtimestamp(s.updated)).days
        grp = "Hoy" if d <= 0 else "Ayer" if d == 1 else "Últimos 7 días" if d < 7 else "Últimos 30 días" if d < 30 else "Anteriores"
        if grp != last:
            h = QListWidgetItem(grp)
            h.setFlags(Qt.NoItemFlags)
            h.setForeground(QGuiApplication.palette().placeholderText())
            f = h.font()
            f.setPointSizeF(8.5)
            h.setFont(f)
            lst.addItem(h)
            last = grp
        it = QListWidgetItem(s.title)
        if s.run is not None:
            it.setIcon(icon("est_cargando", C["warn"], 14))
        it.setData(Qt.UserRole, s.id)
        it.setToolTip(s.title)
        lst.addItem(it)
        if s.id == current:
            it.setSelected(True)
            lst.setCurrentItem(it)
    if not sessions:
        e = QListWidgetItem("Sin resultados" if query else empty_text)
        e.setFlags(Qt.NoItemFlags)
        e.setForeground(QGuiApplication.palette().placeholderText())
        lst.addItem(e)
    lst.blockSignals(False)


# ---------------------------------------------------------------- descripcion legible de cada accion
def _b(p):
    p = str(p or "").rstrip("\\/")
    return os.path.basename(p) or p


def _q(s, n=56):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


STEP = {  # herramienta: (infinitivo, pasado, objeto)
    "read_file": ("leer", "Leyó", lambda a: _b(a.get("path"))),
    "write_file": ("escribir", "Escribió", lambda a: _b(a.get("path"))),
    "edit_file": ("editar", "Editó", lambda a: _b(a.get("path"))),
    "list_dir": ("listar", "Listó", lambda a: _b(a.get("path")) or "la carpeta de trabajo"),
    "search_files": ("buscar", "Buscó", lambda a: "«%s»" % _q(a.get("pattern") or a.get("glob") or "*", 40)),
    "run_command": ("ejecutar", "Ejecutó", lambda a: _q(a.get("command", "").splitlines()[0] if a.get("command") else "")),
    "open_target": ("abrir", "Abrió", lambda a: _b(a.get("target"))),
    "wait": ("esperar", "Esperó", lambda a: "%s s" % a.get("seconds")),
    "web_fetch": ("leer", "Leyó", lambda a: _q(str(a.get("url", "")).split("//")[-1], 48)),
    "web_search": ("buscar en la web", "Buscó en la web", lambda a: "«%s»" % _q(a.get("query"), 44)),
    "download_file": ("descargar", "Descargó", lambda a: _b(str(a.get("url", "")).split("?")[0])),
    "screenshot": ("capturar la pantalla", "Capturó la pantalla", lambda a: ""),
    "click": ("hacer clic", "Hizo clic", lambda a: "en (%s, %s)" % (a.get("x"), a.get("y"))),
    "move_mouse": ("mover el ratón", "Movió el ratón", lambda a: "a (%s, %s)" % (a.get("x"), a.get("y"))),
    "scroll": ("desplazar", "Desplazó", lambda a: str(a.get("amount"))),
    "type_text": ("escribir", "Escribió", lambda a: "«%s»" % _q(a.get("text"), 40)),
    "press_keys": ("pulsar", "Pulsó", lambda a: str(a.get("keys", ""))),
    "list_windows": ("listar las ventanas", "Listó las ventanas", lambda a: ""),
    "focus_window": ("activar la ventana", "Activó la ventana", lambda a: "«%s»" % _q(a.get("title"), 40)),
    "multi_edit": ("editar", "Editó", lambda a: "%s (%d cambios)" % (_b(a.get("path")), len(a.get("edits") or []))),
    "move_path": ("mover", "Movió", lambda a: "%s → %s" % (_b(a.get("source")), _b(a.get("dest")))),
    "delete_path": ("enviar a la papelera", "Envió a la papelera", lambda a: _b(a.get("path"))),
    "command_output": ("revisar la salida de", "Revisó la salida de", lambda a: str(a.get("id"))),
    "stop_command": ("detener", "Detuvo", lambda a: str(a.get("id"))),
    "read_document": ("leer el documento", "Leyó el documento", lambda a: _b(a.get("path"))),
    "view_image": ("ver la imagen", "Vio la imagen", lambda a: _b(a.get("path"))),
    "remember": ("recordar", "Recordó", lambda a: "«%s»" % _q(a.get("fact"), 50)),
}


def describe(name, args, phase):
    if name.startswith("mcp__"):           # herramienta de un conector MCP: «Usó servidor › herramienta»
        parts = name.split("__")
        srv, tool = (parts[1].replace("_", " "), parts[2].replace("_", " ")) if len(parts) > 2 else (name, "")
        return {"pending": "Quiere usar %s › %s" % (srv, tool), "run": "Usando %s › %s…" % (srv, tool)}.get(phase, "Usó %s › %s" % (srv, tool))
    if name == "run_command" and (args or {}).get("background") and phase != "pending":
        return ("Inició en segundo plano %s" if phase != "run" else "Iniciando en segundo plano %s…") % _q((args or {}).get("command", ""))
    inf, past, obj = STEP.get(name, (name, name, lambda a: ""))
    try:
        o = obj(args or {})
    except Exception:
        o = ""
    if phase == "pending":
        return ("Quiere %s %s" % (inf, o)).strip()
    if phase == "run":
        return ("%s %s…" % (inf[:1].upper() + inf[1:], o)).strip()
    return ("%s %s" % (past, o)).strip()


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
    """Una accion del agente en una linea; se despliega para ver detalles y muestra la aprobacion en linea."""

    def __init__(self, ev, on_decide):
        super().__init__()
        self.ev = ev
        self.id = ev["id"]
        self.pending = ev["approval"] == "pending"
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head = Clickable()
        head.setCursor(Qt.PointingHandCursor)
        h = QHBoxLayout(head)
        h.setContentsMargins(10, 6, 8, 6)
        h.setSpacing(8)
        self.st_icon = Spinner(size=14)
        h.addWidget(self.st_icon)
        self.title = QLabel()
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        h.addWidget(self.title, 1)
        add, rem = diff_badge(ev["name"], ev.get("args") or {})
        for txt, col in ((add, C["ok"]), (rem, C["bad"])):
            if txt:
                l = QLabel(txt)
                l.setStyleSheet("color:%s; font-size:9pt" % col)
                h.addWidget(l)
        if ev.get("danger"):
            h.addWidget(pix_label("est_aviso", C["warn"], 14))
        tn = QLabel(ev["name"] if not ev["name"].startswith("mcp__") else "MCP")
        tn.setObjectName("faint")
        h.addWidget(tn)
        self.b_undo = tbtn("acc_refrescar", "Deshacer este cambio (restaura los archivos)", size=13)
        self.b_undo.hide()
        h.addWidget(self.b_undo)
        self.chev = QLabel("›")
        self.chev.setStyleSheet("color:%s; font-size:12pt" % C["faint"])
        h.addWidget(self.chev)
        head.clicked.connect(self.toggle)
        v.addWidget(head)
        self.details = QWidget()
        self.dl = QVBoxLayout(self.details)
        self.dl.setContentsMargins(36, 0, 12, 8)
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
                w = QLabel("Acción delicada: revisa bien el detalle antes de permitirla.")
                w.setObjectName("badgeWarn")
                av.addWidget(w)
            row = QHBoxLayout()
            cat = T.CATEGORIES.get(ev["category"], ev["category"])
            for text, kind, dec in (("Permitir", "primary", "allow"), ("Siempre «%s» aquí" % cat.lower(), None, "allow_category"),
                                    ("Denegar", "danger", "deny")):
                b = btn(text, kind)
                b.clicked.connect(lambda _=False, d=dec: self._decide(d, on_decide))
                row.addWidget(b)
            row.addStretch(1)
            av.addLayout(row)
            wrap = QWidget()
            wl = QVBoxLayout(wrap)
            wl.setContentsMargins(10, 0, 10, 10)
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
        kv = lambda k, val: lbl("<span style='color:%s'>%s:</span> %s" % (C["faint"], k, str(val).replace("<", "&lt;")))
        if name == "run_command":
            self.dl.addWidget(mono(a.get("command", "")))
            if a.get("cwd"):
                self.dl.addWidget(kv("carpeta", a["cwd"]))
        elif name == "write_file":
            self.dl.addWidget(kv("archivo", a.get("path", "")))
            self.dl.addWidget(mono(str(a.get("content", ""))[:20000], "add", 300))
        elif name == "edit_file":
            self.dl.addWidget(kv("archivo", a.get("path", "")))
            self.dl.addWidget(mono(str(a.get("old", "")), "del", 160))
            self.dl.addWidget(mono(str(a.get("new", "")), "add", 160))
        else:
            for k, val in a.items():
                self.dl.addWidget(mono(str(val)) if k == "_raw" else kv(k, val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)))

    def _set(self, phase):
        ico, col = {"pending": ("est_aviso", C["acc"]), "run": ("est_cargando", C["warn"]), "ok": ("ui_check", C["ok"]),
                    "err": ("ui_cerrar", C["bad"]), "denied": ("est_bloqueado", C["bad"]), "blocked": ("est_bloqueado", C["faint"])}[phase]
        if phase == "run" and self.ev.get("ts", 0) > time.time() - 30:
            self.st_icon.start(ico, col)          # gira mientras se ejecuta
        else:
            self.st_icon.stop(pix(ico, col, 14))
        text = describe(self.ev["name"], self.ev.get("args"), {"pending": "pending", "run": "run"}.get(phase, "done"))
        if phase == "denied":
            text = describe(self.ev["name"], self.ev.get("args"), "pending").replace("Quiere", "No se permitió", 1)
        if phase == "blocked":
            text += " (bloqueado: solo lectura)"
        self.title.setText(text)
        self.title.setToolTip(text)
        self.title.setStyleSheet("color:%s" % (C["tx"] if phase in ("pending", "run") else C["mut"]))

    def toggle(self):
        self.details.setVisible(not self.details.isVisible())
        self.chev.setText("⌄" if self.details.isVisible() else "›")

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

    def undone(self):
        self.b_undo.hide()
        self.title.setText(self.title.text() + "  · deshecho")
        self.title.setStyleSheet("color:%s; text-decoration: line-through" % C["faint"])

    def result(self, ok, text, image):
        self._set("ok" if ok else "err")
        if text:
            self.dl.addWidget(mono(text, max_h=300))
        if image:
            self.dl.addWidget(ImageLabel(os.path.join(paths.IMG_DIR, image)))
            self.details.show()
        if not ok:
            self.details.show()
        self.chev.setText("⌄" if self.details.isVisible() else "›")


class StepsBox(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("stepsBox")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 2, 0, 2)
        self.v.setSpacing(0)
        self.rows = []

    def add(self, row):
        if self.rows:
            self.v.addWidget(hline())
        self.rows.append(row)
        self.v.addWidget(row)
        self.refresh()

    def refresh(self):
        self.setProperty("pending", any(r.pending for r in self.rows))
        restyle(self)


# ---------------------------------------------------------------- mensajes
class AssistantBlock(QWidget):
    def __init__(self, started):
        super().__init__()
        self.started = started
        self.r_start = self.r_end = None
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        self.status = QWidget()
        sh = QHBoxLayout(self.status)
        sh.setContentsMargins(0, 0, 0, 0)
        self.spin = Spinner(size=14)
        sh.addWidget(self.spin)
        if started > time.time() - 5:
            self.spin.start()
        self.status_lbl = QLabel("Leyendo tu mensaje…")
        self.status_lbl.setObjectName("muted")
        sh.addWidget(self.status_lbl)
        sh.addStretch(1)
        v.addWidget(self.status)
        self.think_btn = QToolButton()
        self.think_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.think_btn.setIcon(icon("ia_memoria", C["mut"], 15))
        self.think_btn.setCheckable(True)
        self.think_btn.hide()
        self.think_txt = QPlainTextEdit()
        self.think_txt.setObjectName("mono")
        self.think_txt.setReadOnly(True)
        self.think_txt.setFixedHeight(160)
        self.think_txt.hide()
        self.think_btn.toggled.connect(self.think_txt.setVisible)
        v.addWidget(self.think_btn, 0, Qt.AlignLeft)
        v.addWidget(self.think_txt)
        self.body = md_label()
        self.body.hide()
        v.addWidget(self.body)
        self.actions = QWidget()
        ah = QHBoxLayout(self.actions)
        ah.setContentsMargins(0, 0, 0, 0)
        ah.setSpacing(2)
        self.b_copy = tbtn("acc_copiar", "Copiar respuesta", self.copy, size=15)
        self.b_regen = tbtn("acc_refrescar", "Regenerar respuesta", size=15)
        self.b_report = tbtn("est_aviso", "Informar de un problema con esta respuesta", self.report, size=15)
        self.b_undo_all = QPushButton("Deshacer cambios")
        self.b_undo_all.setProperty("kind", "flat")
        self.b_undo_all.setIcon(icon("acc_refrescar", C["mut"], 13))
        self.b_undo_all.setToolTip("Restaura todos los archivos que el agente cambió en esta respuesta")
        self.b_undo_all.hide()
        ah.addWidget(self.b_copy)
        ah.addWidget(self.b_regen)
        ah.addWidget(self.b_report)
        ah.addWidget(self.b_undo_all)
        ah.addStretch(1)
        self.stats = QLabel()
        self.stats.setObjectName("stats")
        ah.addWidget(self.stats)
        self.actions.hide()
        v.addWidget(self.actions)
        self.text = ""

    def tick(self, now):
        if self.status.isVisible():
            self.status_lbl.setText("Leyendo tu mensaje… %d s" % max(0, now - self.started))
        if self.r_start and not self.r_end:
            self.think_btn.setText("Pensando… %d s" % (now - self.r_start))

    def delta(self, kind, text, ts):
        if self.status.isVisible():
            self.spin.stop()
            self.status.hide()
        if kind == "reasoning":
            if self.r_start is None:
                self.r_start = ts
                self.think_btn.show()
            self.think_txt.moveCursor(self.think_txt.textCursor().MoveOperation.End)
            self.think_txt.insertPlainText(text)
            self.tick(ts)
        else:
            self._end_think(ts)
            self.text += text
            self.body.setText(self.text)
            self.body.show()

    def _end_think(self, ts):
        if self.r_start and not self.r_end:
            self.r_end = ts
            self.think_btn.setText("Pensó durante %d s" % max(1, round(self.r_end - self.r_start)))

    def finish(self, text, ts):
        self.spin.stop()
        self.status.hide()
        self._end_think(ts)
        if text:
            self.text = text
            self.body.setText(text)
            self.body.show()

    def empty(self):
        return not self.text and self.r_start is None

    def copy(self):
        QGuiApplication.clipboard().setText(self.text)
        self.b_copy.setIcon(icon("ui_check", C["ok"], 15))
        QTimer.singleShot(1200, lambda: self.b_copy.setIcon(icon("acc_copiar", C["mut"], 15)))

    def report(self):
        excerpt = self.text if len(self.text) < 1500 else self.text[:1500] + "…"
        FeedbackDialog(self.window(), "error", "Respuesta con problemas:\n\n> " + excerpt.replace("\n", "\n> ") + "\n\nQué esperaba: ").exec()


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
        fl.addWidget(pix_label("acc_nuevo", C["acc"], 14))
        fl.addWidget(lbl(fname, "muted"), 1)
        v.addLayout(fl)
    t = lbl(ev["text"])
    t.setStyleSheet("font-size:10.5pt")
    v.addWidget(t)
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
        self.title.setText("Plan · %d de %d" % (done, len(items)))
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
            t = lbl(i.get("content", ""))
            t.setStyleSheet("color:%s;%s" % (C["faint"] if st == "completed" else C["tx"], " text-decoration: line-through;" if st == "completed" else
                                              " font-weight:600;" if st == "in_progress" else ""))
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
        q = lbl(ev["question"])
        q.setStyleSheet("font-weight:600; font-size:10.5pt")
        hh.addWidget(q, 1)
        v.addLayout(hh)
        self.inputs = QWidget()
        il = QVBoxLayout(self.inputs)
        il.setContentsMargins(24, 0, 0, 0)
        row = QHBoxLayout()
        for o in ev.get("options") or []:
            b = btn(o)
            b.clicked.connect(lambda _=False, o=o: self._send(o, on_answer))
            row.addWidget(b)
        row.addStretch(1)
        il.addLayout(row)
        r2 = QHBoxLayout()
        self.free = QLineEdit()
        self.free.setPlaceholderText("Otra respuesta…")
        self.free.returnPressed.connect(lambda: self.free.text().strip() and self._send(self.free.text().strip(), on_answer))
        r2.addWidget(self.free, 1)
        r2.addWidget(btn("Responder", "primary", lambda: self.free.text().strip() and self._send(self.free.text().strip(), on_answer)))
        il.addLayout(r2)
        v.addWidget(self.inputs)
        self.answer_lbl = lbl("", "muted")
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
        self.answer_lbl.setText(("Tu respuesta: " + text) if text else "Sin respuesta")
        self.answer_lbl.show()


CHAT_SUGGESTIONS = [("acc_examinar", "Ordena mi carpeta de Descargas por tipo de archivo"),
                    ("cod_terminal", "Crea un script de Python que renombre mis fotos por fecha"),
                    ("vista_captura", "Haz una captura de pantalla y dime qué ves"),
                    ("herr_espacio_mundo", "Busca en la web las novedades de llama.cpp y resúmelas")]
CODE_SUGGESTIONS = [("acc_examinar", "Explícame la estructura de este proyecto"),
                    ("acc_nuevo", "Crea un README.md que describa este proyecto"),
                    ("acc_buscar", "Revisa el código, busca errores y propón arreglos"),
                    ("cod_terminal", "Crea una página web sencilla con HTML, CSS y JavaScript")]


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
            b = QPushButton(text)
            b.setObjectName("suggestion")
            b.setIcon(icon(ico, C["acc"], 16))
            b.setIconSize(QSize(16, 16))
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(42 if compact else 48)
            b.clicked.connect(lambda _=False, t=text: on_pick(t))
            grid.addWidget(b, i // cols, i % cols)
        v.addLayout(grid)


# ---------------------------------------------------------------- compositor
class ComposerEdit(QPlainTextEdit):
    submit = Signal()
    pasted_image = Signal(QImage)
    focus = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("composerEdit")
        self.setPlaceholderText("Escribe un mensaje…")
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
        if src.hasImage():
            img = src.imageData()
            if isinstance(img, QImage) and not img.isNull():
                self.pasted_image.emit(img)
                return
        super().insertFromMimeData(src)

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
        holder = QWidget()
        holder.setObjectName("chatHolder")
        self.scroll.viewport().setObjectName("chatHolder")
        hl = QHBoxLayout(holder)
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
        self.ban_btn = btn("Encender modelo", "primary", self.main.toggle_llm)
        bl.addWidget(self.ban_btn)
        iv.addWidget(self.banner)
        self.plan_panel = PlanPanel()
        iv.addWidget(self.plan_panel)
        self.box = QFrame()
        self.box.setObjectName("composerBox")
        bv = QVBoxLayout(self.box)
        bv.setContentsMargins(12, 10, 10, 8)
        bv.setSpacing(6)
        self.thumbs = QHBoxLayout()
        self.thumbs.addStretch(1)
        bv.addLayout(self.thumbs)
        self.input = ComposerEdit()
        self.input.submit.connect(self.send)
        self.input.pasted_image.connect(lambda img: self._add_image(qimage=img))
        self.input.focus.connect(lambda f: (self.box.setProperty("focus", f), restyle(self.box)))
        self.input.textChanged.connect(self._sync_send)
        bv.addWidget(self.input)
        row = QHBoxLayout()
        row.setSpacing(6)
        plus = tbtn("acc_anadir", "Adjuntar", size=14, name="round")
        plus.setFixedSize(28, 28)
        plus.setPopupMode(QToolButton.InstantPopup)
        pm = QMenu(self)
        pm.addAction(icon("acc_nuevo"), "Adjuntar archivos o documentos…", self.attach_files)
        pm.addAction(icon("uij_imagen"), "Adjuntar imagen…", self.attach)
        pm.addAction(icon("vista_captura"), "Adjuntar captura de pantalla", self.attach_screenshot)
        plus.setMenu(pm)
        plus.setToolTip("Adjuntar archivos, documentos, imágenes o una captura")
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
        row.addWidget(self.mode_chip)
        self.think_chip = QToolButton()
        self.think_chip.setObjectName("chip")
        self.think_chip.setText("Pensar")
        self.think_chip.setIcon(icon("ia_memoria", C["mut"], 13))
        self.think_chip.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.think_chip.setCheckable(True)
        self.think_chip.setToolTip("Razonar antes de responder: mejores resultados, pero más lento")
        self.think_chip.toggled.connect(lambda on: (core.SET.update({"thinking": on}), self.main.sync()))
        row.addWidget(self.think_chip)
        row.addStretch(1)
        self.send_btn = QToolButton()
        self.send_btn.setObjectName("sendBtn")
        self.send_btn.setFixedSize(32, 32)
        self.send_btn.setIconSize(QSize(16, 16))
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(lambda: self.stop() if self.busy else self.send())
        row.addWidget(self.send_btn)
        bv.addLayout(row)
        iv.addWidget(self.box)
        if not self.compact:
            hint = QLabel("Se ejecuta en tu equipo. Revisa cada acción antes de permitirla · ratón a la esquina superior izquierda = detener el control")
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

    def clear(self):
        while self.cl.count() > 1:
            it = self.cl.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()

    def add(self, w):
        self.cl.insertWidget(self.cl.count() - 1, w)
        if getattr(self, "_live", False):
            fade_in(w)                    # solo lo que llega en vivo, no al reabrir una conversacion
        return w

    def open_session(self, sid):
        self.sid = sid
        self.ev_i = 0
        self.cur = None
        self.steps = None
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
            return EmptyState("¿Qué construimos en «%s»?" % (p["name"] if p else "tu proyecto"),
                              "Trabajo dentro de la carpeta del proyecto. Verás cada archivo que cree o cambie.",
                              CODE_SUGGESTIONS, self._pick, self.compact)
        name = core.SET.snapshot().get("user_name", "").strip()
        return EmptyState("¿En qué te ayudo%s?" % (", " + name if name else " hoy"),
                          "Puedo trabajar con tus archivos, programas y la web. Cada acción la ves y la apruebas tú.",
                          CHAT_SUGGESTIONS, self._pick, self.compact)

    def _pick(self, text):
        self.input.setPlainText(text)
        self.input.setFocus()
        self.input.moveCursor(self.input.textCursor().MoveOperation.End)

    def _last_visible(self):
        for i in range(self.cl.count() - 2, -1, -1):
            w = self.cl.itemAt(i).widget()
            if w is not None and not w.isHidden():
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
            self.steps = None
            self.cur = None
            self.add(user_bubble(ev, self.compact))
        elif t == "turn_start":
            self.cur = self.add(AssistantBlock(ev["ts"]))
            if ev["ts"] < time.time() - 5:
                self.cur.status.hide()     # reconstruyendo una conversacion guardada
        elif t == "delta":
            if self.cur is None:
                self.cur = self.add(AssistantBlock(ev["ts"]))
            self.cur.delta(ev["kind"], ev["text"], ev["ts"])
        elif t == "stats":
            if self.cur is not None and ev.get("gen_n"):
                s = "%s tok" % ev["gen_n"]
                if ev.get("tps"):
                    s += " · %.1f tok/s" % ev["tps"]
                if ev.get("finish") == "length":
                    s += " · cortado por límite"
                if ev.get("ctx_used") and ev.get("ctx_max"):
                    s += " · contexto %.1fk de %dk" % (ev["ctx_used"] / 1000.0, ev["ctx_max"] // 1000)
                self.cur.stats.setText(s)
                self.cur.stats.setToolTip("Memoria de la conversación usada por el modelo. Al acercarse al límite, Jayth resume lo antiguo.")
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
                    self.cur.b_regen.clicked.connect(self.regenerate)
                    self.steps = None
                self.cur = None
        elif t == "tool_call" and ev["name"] == "update_plan":
            pass                                        # se muestra en el panel del plan (evento «plan»)
        elif t == "plan":
            self.plan_panel.set_items(ev.get("items") or [], live=getattr(self, "_live", False))
        elif t == "question":
            card = QuestionCard(ev, self.answer, live=getattr(self, "_live", False) or self.busy)
            self.questions[ev["id"]] = card
            self.add(card)
            self.steps = None
            if card.inputs.isVisible():
                self.waiting += 1
                self.sync()
                self.main.notify_pending("tiene una pregunta: " + ev["question"], ev["ts"])
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
            self.add(note("Cambios deshechos: %s" % ", ".join(os.path.basename(f) for f in ev.get("files") or [])))
            self.steps = None
        elif t == "compacted":
            self.add(note("Resumí la parte antigua de la conversación para que el modelo no la olvide ni se quede sin memoria."))
            self.steps = None
        elif t == "plan_ready":
            if getattr(self, "_live", False):
                self.add(self._plan_ready_card())
                self.steps = None
        elif t == "tool_call":
            row = StepRow(ev, self.decide)
            self.rows[ev["id"]] = row
            if self.steps is None or self._last_visible() is not self.steps:
                self.steps = self.add(StepsBox())
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
            r = self.rows.get(ev["id"])
            if r:
                r.result(ev["ok"], ev.get("text") or "", ev.get("image"))
                if ev.get("undo") and ev["ok"]:
                    from . import harness
                    if harness.has_snapshot(self.sid, ev["id"]):
                        r.b_undo.show()
                        if not getattr(r, "_undo_wired", False):
                            r._undo_wired = True
                            r.b_undo.clicked.connect(lambda _=False, cid=ev["id"]: self.undo(cid))
                        self.turn_undo = True
                if ev["ok"] and r.ev["name"] in ("write_file", "edit_file", "multi_edit") and ev["ts"] > time.time() - 10:
                    p = str((r.ev.get("args") or {}).get("path", ""))
                    if p:
                        self.file_written.emit(os.path.normpath(p if os.path.isabs(p) else os.path.join(self.workspace(), p)))
        elif t in ("info", "error"):
            self.add(note("Detenido por ti." if (t == "info" and ev["text"] == "Detenido.") else ev["text"], t == "error"))
            self.steps = None
        elif t == "turn_end":
            if self.cur is not None and self.cur.empty():
                self.cur.hide()
                self.cur.deleteLater()
            self.cur = None
            self._stale()
            for b in self.blocks:
                b.actions.show()
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

    # ---- plan, preguntas y deshacer
    def _plan_ready_card(self):
        f = QFrame()
        f.setObjectName("noteBox")
        h = QHBoxLayout(f)
        h.setContentsMargins(14, 10, 10, 10)
        h.addWidget(pix_label("ui_check", C["acc"], 16))
        h.addWidget(lbl("Plan listo. Revísalo y, si te convence, ejecútalo."), 1)
        h.addWidget(btn("Seguir ajustando", cb=lambda: self.input.setFocus()))
        h.addWidget(btn("Ejecutar el plan", "primary", lambda: self.execute_plan(f), "hub_lanzar"))
        return f

    def execute_plan(self, card=None):
        if self.busy or not self.session():
            return
        mode = getattr(self, "exec_mode", "ask")
        core.SET.update({"mode": mode})
        self.main.sync()
        if card is not None:
            card.hide()
        self.session().send("Adelante: ejecuta el plan aprobado paso a paso, actualizando la lista de tareas.")
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
                self.main.toast("Restaurado: %s" % ", ".join(os.path.basename(f) for f in files), icon_name="acc_refrescar", color=C["ok"])
                for f in files:
                    self.file_written.emit(f)
        elif s:
            self.main.toast("Espera a que el agente termine para deshacer.", icon_name="est_aviso", color=C["warn"])

    def undo_turn(self):
        s = self.session()
        if not s or s.run is not None:
            return
        files = s.undo_turn()
        if files:
            self.main.toast("Deshechos %d cambios de archivos." % len(files), icon_name="acc_refrescar", color=C["ok"])
            for f in files:
                self.file_written.emit(f)

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
            return self.main.setup()
        if not self.session():
            self.open_session(core.new_session(self.project_id).id)
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
        files, _ = QFileDialog.getOpenFileNames(self, "Adjuntar imágenes", os.path.expanduser("~"), "Imágenes (*.png *.jpg *.jpeg *.webp *.gif)")
        for f in files:
            self._add_image(src=f)

    def attach_files(self):
        """Documentos y archivos de texto o código: su contenido se incluye en el mensaje."""
        files, _ = QFileDialog.getOpenFileNames(self, "Adjuntar archivos", self.workspace(),
                                                "Documentos y texto (*.txt *.md *.py *.js *.ts *.json *.csv *.html *.css *.xml *.yml *.yaml *.log "
                                                "*.docx *.xlsx *.pptx *.pdf *.ps1 *.bat *.ini *.toml *.sql *.c *.cpp *.h *.cs *.java *.go *.rs);;Todos (*.*)")
        imgs = [f for f in files if os.path.splitext(f)[1].lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif")]
        for f in imgs:
            self._add_image(src=f)
        self.pending_files = list(getattr(self, "pending_files", [])) + [os.path.normpath(f) for f in files if f not in imgs]
        self._render_thumbs()

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
        while self.thumbs.count() > 1:
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
            h.addWidget(tbtn("ui_cerrar", "Quitar", lambda _=False, n=n: (self.pending_imgs.remove(n), self._render_thumbs()), size=12), 0, Qt.AlignTop)
            self.thumbs.insertWidget(self.thumbs.count() - 1, w)
        for f in getattr(self, "pending_files", []):
            w = QFrame()
            w.setObjectName("noteBox")
            h = QHBoxLayout(w)
            h.setContentsMargins(8, 4, 2, 4)
            h.setSpacing(4)
            h.addWidget(pix_label("acc_nuevo", C["acc"], 13))
            h.addWidget(QLabel(os.path.basename(f)))
            h.addWidget(tbtn("ui_cerrar", "Quitar", lambda _=False, f=f: (self.pending_files.remove(f), self._render_thumbs()), size=11))
            w.setToolTip(f)
            self.thumbs.insertWidget(self.thumbs.count() - 1, w)
        self._sync_send()

    def _sync_send(self):
        has = bool(self.input.toPlainText().strip() or self.pending_imgs or getattr(self, "pending_files", []))
        self.send_btn.setEnabled(self.busy or has)
        self.send_btn.setIcon(icon("trans_detener" if self.busy else "lista_subir", C["on_send"] if (self.busy or has) else C["faint"], 14 if self.busy else 16))
        self.send_btn.setToolTip("Detener" if self.busy else "Enviar (Enter)")

    def sync(self):
        cfg = core.SET.snapshot()
        llm = self.main.llm
        st = llm.get("state", "off")
        ext = cfg["llm_mode"] == "external"
        self.banner.setVisible(st != "ready")
        if not core.SET.ready():
            self.ban_txt.setText("Aún no hay un modelo configurado.")
            self.ban_btn.setText("Configurar")
            self.ban_btn.show()
        elif st == "loading":
            self.ban_txt.setText("Cargando el modelo en memoria. En equipos sin GPU puede tardar unos minutos.")
            self.ban_btn.hide()
        else:
            self.ban_txt.setText("El servidor externo no responde." if ext else (llm.get("error") or "El modelo está apagado."))
            self.ban_btn.setText("Encender modelo")
            self.ban_btn.setVisible(not ext)
        self.mode_chip.setText(MODE_LABEL.get(cfg["mode"], cfg["mode"]))
        self.mode_chip.setToolTip(A.MODES.get(cfg["mode"], ""))
        if cfg["mode"] not in ("plan", "readonly"):
            self.exec_mode = cfg["mode"]          # al aprobar un plan se vuelve a este modo
        if cfg["mode"] in self.mode_actions:
            self.mode_actions[cfg["mode"]].setChecked(True)
        self.think_chip.blockSignals(True)
        self.think_chip.setChecked(cfg["thinking"])
        self.think_chip.blockSignals(False)
        self.input.setPlaceholderText("Pide algo sobre el proyecto…" if self.project_id else "Escribe un mensaje…")
        self._sync_send()


# ---------------------------------------------------------------- pagina del modo Code
class CodePage(QWidget):
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
        s = QLabel("Crea un proyecto o abre una carpeta. El agente trabajará dentro de ella:\ncrea y edita archivos, ejecuta comandos y te muestra cada cambio en el editor.")
        s.setObjectName("muted")
        s.setAlignment(Qt.AlignCenter)
        ev.addWidget(s)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn("Nuevo proyecto", "primary", main.new_project, "acc_anadir"))
        row.addWidget(btn("Abrir carpeta…", cb=main.open_folder_project, ico="act_carpeta_abierta"))
        row.addStretch(1)
        ev.addLayout(row)
        ev.addStretch(2)
        self.stack.addWidget(e)
        # espacio de trabajo
        ws = QWidget()
        wl = QHBoxLayout(ws)
        wl.setContentsMargins(0, 0, 0, 0)
        self.split = QSplitter(Qt.Horizontal)
        self.split.setHandleWidth(1)
        self.split.setStyleSheet("QSplitter::handle { background: %s; }" % C["line"])
        left = QWidget()
        left.setObjectName("sidebar")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(6, 6, 0, 6)
        lv.setSpacing(4)
        th = QHBoxLayout()
        self.proj_lbl = QLabel()
        self.proj_lbl.setStyleSheet("font-weight:600; padding-left:4px")
        th.addWidget(self.proj_lbl, 1)
        th.addWidget(tbtn("acc_nuevo", "Nuevo archivo", self._new_file, size=14))
        th.addWidget(tbtn("act_carpeta_abierta", SHOW_IN, lambda: self.project and osys.open_path(self.project["path"]), size=14))
        lv.addLayout(th)
        self.tree = FileTree()
        self.tree.open_file.connect(lambda p: self.tabs.open(p))
        lv.addWidget(self.tree, 1)
        self.split.addWidget(left)
        center = QSplitter(Qt.Vertical)
        center.setHandleWidth(1)
        self.tabs = EditorTabs()
        center.addWidget(self.tabs)
        self.term = Terminal()
        center.addWidget(self.term)
        center.setSizes([520, 220])
        self.center = center
        self.split.addWidget(center)
        self.chat = ChatPanel(main, compact=True)
        self.chat.changed.connect(main.on_chat_changed)
        self.chat.file_written.connect(self.tabs.refresh)
        self.chat.setMinimumWidth(340)
        self.split.addWidget(self.chat)
        self.split.setSizes([230, 600, 420])
        self.split.setCollapsible(1, False)
        wl.addWidget(self.split)
        self.stack.addWidget(ws)

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
        self.proj_lbl.setText(p["name"])
        self.proj_lbl.setToolTip(p["path"])
        self.tree.set_root(p["path"])
        self.term.root = p["path"]
        self.term.start(p["path"])
        self.chat.project_id = p["id"]
        ss = core.sessions_for(p["id"])
        self.chat.open_session(ss[0].id if ss else None)

    def _new_file(self):
        if not self.project:
            return
        n, ok = QInputDialog.getText(self, "Nuevo archivo", "Nombre (puede incluir carpetas, p. ej. src/main.py):")
        if ok and n.strip():
            fp = os.path.join(self.project["path"], n.strip())
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            if not os.path.exists(fp):
                open(fp, "w", encoding="utf-8").close()
            self.tabs.open(fp)

    def toggle_terminal(self):
        self.term.setVisible(not self.term.isVisible())
        if self.term.isVisible():
            self.term.inp.setFocus()


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
        self._build()
        self._tray()
        self.chat.open_session(None)
        self.code.set_project(core.project(cfg, cfg["active_project"]))
        self.set_mode(cfg.get("app_mode") or "chat", save=False)
        self.poll_t = QTimer(self, interval=2500, timeout=self.poll)
        self.poll_t.start()
        self.poll()
        QTimer.singleShot(9000, self.check_news)                                   # novedades al poco de abrir…
        self.news_t = QTimer(self, interval=6 * 3600 * 1000, timeout=self.check_news)   # …y cada 6 horas
        self.news_t.start()
        QTimer.singleShot(1500, self.sync_mcp)

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
                self.toast("No se pudo conectar: %s" % "; ".join("%s (%s)" % (n, e[:80]) for n, e in bad.items()), icon_name="est_aviso", color=C["warn"])
        run_bg(lambda: harness.mcp_sync(servers), done)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_conversation)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.focus_search)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, activated=self.toggle_sidebar)
        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self.set_mode("chat"))
        QShortcut(QKeySequence("Ctrl+2"), self, activated=lambda: self.set_mode("code"))
        QShortcut(QKeySequence("Ctrl+`"), self, activated=lambda: self.mode == "code" and self.code.toggle_terminal())
        QShortcut(QKeySequence("Escape"), self, activated=self._escape)

    # ---- construccion
    def _build(self):
        central = QWidget()
        central.setObjectName("central")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)
        root.addWidget(self._sidebar())
        main = QWidget()
        main.setObjectName("main")
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
        mv.addWidget(self.pages, 1)
        root.addWidget(main, 1)

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
        self.side.setFixedWidth(264)
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
        top.addWidget(tbtn("ui_menu_hamburguesa", "Ocultar barra lateral  ·  Ctrl+Shift+S", self.toggle_sidebar, size=16))
        sv.addWidget(self.side_top)
        sv.addSpacing(4)
        seg = QFrame()
        seg.setObjectName("segment")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(3, 3, 3, 3)
        sl.setSpacing(3)
        self.seg_chat = QPushButton("Chat")
        self.seg_code = QPushButton("Code")
        for b, m, tip in ((self.seg_chat, "chat", "Conversaciones (Ctrl+1)"), (self.seg_code, "code", "Proyectos de código (Ctrl+2)")):
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
        self._nav(cl, "acc_renombrar", "Nueva conversación", self.new_conversation, "Ctrl+N")
        self._nav(cl, "acc_buscar", "Buscar", self.focus_search, "Ctrl+K")
        self._nav(cl, "ia_controlador", "Modelos", self.models)
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Buscar en tus conversaciones")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda: (setattr(self, "_sig_chat", None), self.refresh_lists()))
        self.search.hide()
        cl.addWidget(self.search)
        cl.addSpacing(6)
        self.list = QListWidget()
        self.list.setObjectName("history")
        self.list.itemClicked.connect(lambda it: it.data(Qt.UserRole) and self.chat.open_session(it.data(Qt.UserRole)))
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(lambda pos: self._session_menu(self.list, pos, self.chat))
        cl.addWidget(self.list, 1)
        self.side_stack.addWidget(cw)
        # -- lateral del modo Code
        kw = QWidget()
        kl = QVBoxLayout(kw)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.setSpacing(2)
        self._nav(kl, "acc_anadir", "Nuevo proyecto", self.new_project)
        self._nav(kl, "act_carpeta_abierta", "Abrir carpeta…", self.open_folder_project)
        sec = QLabel("Proyectos")
        sec.setObjectName("section")
        kl.addWidget(sec)
        self.plist = QListWidget()
        self.plist.setObjectName("history")
        self.plist.setMaximumHeight(170)
        self.plist.itemClicked.connect(lambda it: it.data(Qt.UserRole) and self.select_project(it.data(Qt.UserRole)))
        self.plist.setContextMenuPolicy(Qt.CustomContextMenu)
        self.plist.customContextMenuRequested.connect(self._project_menu)
        kl.addWidget(self.plist)
        sec2 = QHBoxLayout()
        s2 = QLabel("Conversaciones del proyecto")
        s2.setObjectName("section")
        sec2.addWidget(s2, 1)
        sec2.addWidget(tbtn("acc_renombrar", "Nueva conversación del proyecto (Ctrl+N)", self.new_conversation, size=14))
        kl.addLayout(sec2)
        self.clist = QListWidget()
        self.clist.setObjectName("history")
        self.clist.itemClicked.connect(lambda it: it.data(Qt.UserRole) and self.code.chat.open_session(it.data(Qt.UserRole)))
        self.clist.setContextMenuPolicy(Qt.CustomContextMenu)
        self.clist.customContextMenuRequested.connect(lambda pos: self._session_menu(self.clist, pos, self.code.chat))
        kl.addWidget(self.clist, 1)
        self.side_stack.addWidget(kw)
        sv.addWidget(self.side_stack, 1)
        self.update_btn = QPushButton("  Actualización disponible")
        self.update_btn.setObjectName("updateBtn")
        self.update_btn.setIcon(icon("acc_descargar", C["acc"], 15))
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.clicked.connect(self.install_update)
        self.update_btn.hide()
        sv.addWidget(self.update_btn)
        sv.addSpacing(4)
        sv.addWidget(hline())
        # perfil: generico (sin datos de nadie) y con un menu util, como en las apps de escritorio habituales
        foot = QPushButton()
        foot.setObjectName("nav")
        foot.setCursor(Qt.PointingHandCursor)
        foot.setToolTip("Tu perfil y ajustes")
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
        pm.addAction(icon("acc_ajustes"), "Ajustes", lambda: self.settings("General"))
        pm.addAction(icon("mat_comentario"), "Personalización", lambda: self.settings("Personalización"))
        pm.addAction(icon("ia_controlador"), "Modelos", self.models)
        pm.addSeparator()
        pm.addAction(icon("inp_teclado"), "Atajos de teclado", lambda: self.settings("Atajos de teclado"))
        pm.addAction(icon("mat_comentario"), "Enviar comentarios…", lambda: FeedbackDialog(self, "idea").exec())
        pm.addAction(icon("est_error"), "Informar de un error…", lambda: FeedbackDialog(self, "error").exec())
        pm.addAction(icon("acc_refrescar"), "Buscar actualizaciones", lambda: self.check_news(manual=True))
        pm.addAction(icon("est_info"), "Acerca de %s" % APP_NAME, lambda: self.settings("Acerca de"))
        pm.addSeparator()
        pm.addAction(icon("ui_cerrar"), "Salir", self.quit_app)
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
        self.b_expand = tbtn("ui_menu_hamburguesa", "Mostrar barra lateral  ·  Ctrl+Shift+S", self.toggle_sidebar, size=16)
        self.b_expand.hide()
        h.addWidget(self.b_expand)
        self.model_btn = QToolButton()
        self.model_btn.setObjectName("modelBtn")
        self.model_btn.setPopupMode(QToolButton.InstantPopup)
        self.model_menu = QMenu(self)
        self.model_menu.aboutToShow.connect(self._fill_model_menu)
        self.model_btn.setMenu(self.model_menu)
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
        self.b_term = tbtn("pan_consola", "Mostrar u ocultar la terminal (Ctrl+`)", lambda: self.code.toggle_terminal())
        h.addWidget(self.b_term)
        self.b_folder = tbtn("act_carpeta_abierta", "", lambda: osys.open_path(self.current_panel().workspace()))
        h.addWidget(self.b_folder)
        more = tbtn("ui_menu_horizontal", "Más opciones")
        more.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(self)
        m.addAction(icon("acc_renombrar"), "Renombrar conversación", lambda: self._rename(self.current_panel().session()))
        m.addAction(icon("act_carpeta_abierta"), "Abrir carpeta de trabajo", lambda: osys.open_path(self.current_panel().workspace()))
        m.addSeparator()
        m.addAction(icon("acc_eliminar", C["bad"]), "Borrar conversación", lambda: self._delete(self.current_panel().session(), self.current_panel()))
        more.setMenu(m)
        h.addWidget(more)
        if self.frameless:
            h.addSpacing(8)
            # botones de ventana con la fuente de iconos de Windows (Segoe Fluent / MDL2)
            self.b_min = self._winbtn("", "Minimizar", self.showMinimized)
            self.b_max = self._winbtn("", "Maximizar", self.toggle_max)
            self.b_close = self._winbtn("", "Cerrar", self.close, close=True)
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
            self.b_max.setToolTip("Restaurar" if self.isMaximized() else "Maximizar")

    # ---- barra de titulo integrada (Windows): se quita la nativa y se indica a Windows que zonas son "titulo" y "borde"
    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, "frameless", False) and not getattr(self, "_frame_done", False):
            self._frame_done = True
            hwnd = int(self.winId())
            try:
                u = ctypes.windll.user32
                # estilos de ventana normal: ajuste a los bordes (Aero Snap), animaciones de minimizar/maximizar y redimensionado
                style = u.GetWindowLongW(hwnd, -16)
                u.SetWindowLongW(hwnd, -16, style | 0x00040000 | 0x00C00000 | 0x00010000 | 0x00020000)   # THICKFRAME|CAPTION|MAXIMIZEBOX|MINIMIZEBOX

                class MARGINS(ctypes.Structure):
                    _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int), ("t", ctypes.c_int), ("b", ctypes.c_int)]
                ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(MARGINS(1, 1, 1, 1)))   # mantiene la sombra
                u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0020 | 0x0002 | 0x0001 | 0x0004)                         # FRAMECHANGED|NOMOVE|NOSIZE|NOZORDER
                theme.rounded(self)
            except Exception:
                pass

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

    def _tray(self):
        self.tray = QSystemTrayIcon(make_icon(), self)
        self.tray.setToolTip(APP_NAME)
        m = QMenu()
        m.addAction(icon("acc_abrir_externo"), "Mostrar", self._show)
        m.addAction(icon("trans_detener"), "Detener agente", lambda: (self.chat.stop(), self.code.chat.stop()))
        m.addSeparator()
        m.addAction(icon("ui_cerrar"), "Salir", self.quit_app)
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

    def notify_pending(self, text, ts):
        if core.SET.snapshot().get("notifications", True) and not self.isActiveWindow() and ts > time.time() - 10:
            self.tray.showMessage(APP_NAME, "El agente espera tu aprobación: " + text, QSystemTrayIcon.Information, 6000)

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

    def toggle_sidebar(self):
        show = not self.side.isVisible() or self.side.maximumWidth() == 0
        self.b_expand.setVisible(not show)
        if not animations_on():
            self.side.setFixedWidth(264)
            self.side.setVisible(show)
            return
        if show:
            self.side.setFixedWidth(0)
            self.side.show()
        grp = QParallelAnimationGroup(self)
        for prop in (b"minimumWidth", b"maximumWidth"):
            a = QPropertyAnimation(self.side, prop)
            a.setDuration(190)
            a.setStartValue(self.side.width())
            a.setEndValue(264 if show else 0)
            a.setEasingCurve(QEasingCurve.OutCubic)
            grp.addAnimation(a)
        if not show:
            grp.finished.connect(lambda: (self.side.hide(), self.side.setFixedWidth(264)))
        grp.start(QPropertyAnimation.DeleteWhenStopped)

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
                self.toast("No pude consultar si hay actualizaciones (¿sin internet?).", icon_name="est_aviso", color=C["warn"])
            return
        self.update_info = r
        self.update_btn.setVisible(bool(r))
        if r:
            self.update_btn.setToolTip("Versión del %s: %s" % (r["date"], r["message"]))
            self.toast("Hay una versión nueva de %s (%s): «%s»." % (APP_NAME, r["date"], r["message"]), "Actualizar", self.install_update,
                       12000, "acc_descargar")
        elif manual:
            self.toast("Tienes la última versión de %s." % APP_NAME, icon_name="ui_check", color=C["ok"])

    def _got_model_news(self, news):
        if isinstance(news, Exception) or not news:
            return
        self.model_news = news
        seen = list(core.SET.snapshot().get("model_news_seen") or [])
        for n in news:
            self.toast("Nuevo modelo disponible: %s (más reciente que tu %s)." % (n["title"], n["for"]), "Ver",
                       lambda r=n["repo"]: self.setup("model", r), 15000, "ia_controlador")
            seen.append(n["repo"])
        core.SET.update({"model_news_seen": seen[-50:]})

    def install_update(self):
        info = self.update_info
        if not info:
            return
        if any(s.run for s in core.SESSIONS.values()):
            return QMessageBox.information(self, APP_NAME, "Espera a que el agente termine antes de actualizar.")
        if QMessageBox.question(self, "Actualizar %s" % APP_NAME, "Versión del %s:\n«%s»\n\n%s se cerrará, se actualizará y volverá a abrirse. "
                                "Tus conversaciones, ajustes y modelos se conservan. ¿Actualizar ahora?" % (info["date"], info["message"], APP_NAME)) \
                != QMessageBox.StandardButton.Yes:
            return
        def done(r):
            if isinstance(r, Exception):
                return QMessageBox.warning(self, APP_NAME, "No se pudo actualizar: %s" % r)
            ok, how = r
            if not ok:
                return QMessageBox.warning(self, APP_NAME, how)
            if how == "restart":
                updater.restart()
            self.quit_app()
        if updater.installed()["kind"] == "frozen":          # hay que descargar el paquete: en segundo plano
            self.update_btn.setEnabled(False)
            self.update_btn.setText("  Descargando actualización…")
            self.toast("Descargando la versión nueva. %s se reiniciará al terminar." % APP_NAME, ms=6000, icon_name="acc_descargar")
            run_bg(lambda: updater.apply_update(info), done)
        else:
            done(updater.apply_update(info))

    def focus_search(self):
        if self.mode != "chat":
            self.set_mode("chat")
        if not self.side.isVisible():
            self.toggle_sidebar()
        self.search.show()
        self.search.setFocus()
        self.search.selectAll()

    def _escape(self):
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
        path = QFileDialog.getExistingDirectory(self, "Abrir carpeta como proyecto", os.path.expanduser("~"))
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
        a_edit = m.addAction(icon("acc_renombrar"), "Editar proyecto…")
        a_os = m.addAction(icon("act_carpeta_abierta"), SHOW_IN)
        m.addSeparator()
        a_rm = m.addAction(icon("ui_cerrar", C["bad"]), "Quitar de la lista")
        a = m.exec(self.plist.mapToGlobal(pos))
        if a == a_edit:
            d = ProjectDialog(self, p)
            if d.exec() and self.code.project and self.code.project["id"] == p["id"]:
                self.code.project = None
                self.code.set_project(d.result_project)
        elif a == a_os:
            osys.open_path(p["path"])
        elif a == a_rm:
            if QMessageBox.question(self, "Quitar proyecto", "¿Quitar «%s» de la lista? La carpeta y sus archivos no se borran." % p["name"]) == QMessageBox.StandardButton.Yes:
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
            fill_history(self.list, ss, self.chat.sid, q)
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
                e = QListWidgetItem("Aún no hay proyectos")
                e.setFlags(Qt.NoItemFlags)
                e.setForeground(QGuiApplication.palette().placeholderText())
                self.plist.addItem(e)
            fill_history(self.clist, cs, self.code.chat.sid, empty_text="Las conversaciones del proyecto aparecerán aquí")

    def _session_menu(self, lst, pos, panel):
        it = lst.itemAt(pos)
        if not it or not it.data(Qt.UserRole):
            return
        s = core.SESSIONS.get(it.data(Qt.UserRole))
        m = QMenu(self)
        a_ren = m.addAction(icon("acc_renombrar"), "Renombrar")
        a_del = m.addAction(icon("acc_eliminar", C["bad"]), "Borrar")
        a = m.exec(lst.mapToGlobal(pos))
        if a == a_ren:
            self._rename(s)
        elif a == a_del:
            self._delete(s, panel)

    def _rename(self, s):
        if not s:
            return
        t, ok = QInputDialog.getText(self, "Renombrar", "Nuevo nombre:", text=s.title)
        if ok and t.strip():
            s.title = t.strip()[:80]
            s.save()
            self.on_chat_changed()

    def _delete(self, s, panel):
        if not s:
            return
        if QMessageBox.question(self, "Borrar conversación", "¿Borrar «%s»? No se puede deshacer." % s.title) == QMessageBox.StandardButton.Yes:
            s.delete()
            if panel.sid == s.id:
                panel.open_session(None)
            self.on_chat_changed()

    # ---- modelo y estado
    def _fill_model_menu(self):
        m = self.model_menu
        m.clear()
        cfg = core.SET.snapshot()
        ext = cfg["llm_mode"] == "external"
        grp = QActionGroup(m)
        if cfg["models"]:
            hdr = m.addAction("Modelos locales")
            hdr.setEnabled(False)
        for md in cfg["models"]:
            a = m.addAction(core.model_title(md) + ("   " + core.model_quant(md) if core.model_quant(md) else ""))
            a.setCheckable(True)
            a.setChecked(not ext and md["id"] == cfg["active_model"])
            grp.addAction(a)
            a.triggered.connect(lambda _=False, i=md["id"]: self._use_model(i))
        if ext or cfg["external_model"]:
            a = m.addAction("Servidor externo · %s" % (cfg["external_model"] or cfg["external_url"]))
            a.setCheckable(True)
            a.setChecked(ext)
            grp.addAction(a)
            a.triggered.connect(lambda: (core.LLM_MGR.stop(), core.SET.update({"llm_mode": "external"}), self.poll()))
        m.addSeparator()
        st = self.llm.get("state", "off")
        if not ext:
            if st == "off":
                m.addAction(icon("hub_lanzar"), "Encender modelo", self.toggle_llm)
            elif not self.llm.get("external"):
                m.addAction(icon("trans_detener"), "Apagar modelo", self.toggle_llm)
        m.addAction(icon("acc_anadir"), "Añadir modelo…", lambda: self.setup("model"))
        m.addAction(icon("ia_controlador"), "Gestionar modelos…", self.models)

    def _use_model(self, mid):
        cfg = core.SET.snapshot()
        if cfg["active_model"] == mid and cfg["llm_mode"] == "local":
            return
        core.LLM_MGR.stop()
        core.SET.update({"active_model": mid, "llm_mode": "local"})
        self.llm = {"state": "off"}
        self.sync()
        if QMessageBox.question(self, APP_NAME, "¿Encender el nuevo modelo ahora?") == QMessageBox.StandardButton.Yes:
            self.toggle_llm()

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
                self.tray.showMessage(APP_NAME, "Apagué el modelo tras %d minutos sin uso para liberar memoria." % idle, QSystemTrayIcon.Information, 5000)
        self.sync()

    def sync(self):
        cfg = core.SET.snapshot()
        st = self.llm.get("state", "off")
        ext = cfg["llm_mode"] == "external"
        m = core.active_model(cfg)
        name = ("Externo · " + (cfg["external_model"] or cfg["external_url"])) if ext else (core.model_title(m) if m else "Sin modelo")
        self.model_btn.setText(name + "  ⌄")
        self.model_btn.setToolTip(("%s · %s · %s" % (core.model_title(m), core.model_quant(m), m.get("path", ""))) if (m and not ext) else "Elegir modelo")
        col, txt = {"ready": (C["ok"], "Listo" + (" · externo" if ext else " · local")), "loading": (C["warn"], "Cargando…")}.get(st, (C["faint"], "Apagado"))
        if st == "ready" and self.llm.get("warm") == "warming":
            col, txt = C["warn"], "Preparando el agente…"
        self.status_lbl.setText("<span style='color:%s'>●</span> <span style='color:%s'>%s</span>" % (col, C["mut"], txt))
        panel = self.current_panel()
        s = panel.session()
        if self.mode == "code" and self.code.project:
            self.title.setText(self.code.project["name"] + (" · " + s.title if s and s.events else ""))
        else:
            self.title.setText(s.title if s and s.events else ("" if self.mode == "chat" else CODE_NAME))
        self.b_folder.setToolTip("Carpeta de trabajo: %s" % panel.workspace())
        self.b_term.setVisible(self.mode == "code" and self.code.project is not None)
        un = (cfg.get("user_name") or "").strip()     # nunca se usa el usuario de Windows: el perfil es generico
        self.user_lbl.setText(un or "Tu perfil")
        if un:
            self.avatar.setPixmap(QPixmap())
            self.avatar.setText("".join(p[0] for p in un.split()[:2]).upper())
        else:
            self.avatar.setText("")
            self.avatar.setPixmap(pix("ia_controlador", C["acc"], 15))
        waiting = self.chat.waiting + self.code.chat.waiting
        self.setWindowTitle(("● Esperando tu aprobación · " if waiting else "") + (CODE_NAME if self.mode == "code" else APP_NAME))
        for p in (self.chat, self.code.chat):
            p.sync()

    def toggle_llm(self):
        if not core.SET.ready():
            return self.setup()
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
                self.tray.showMessage(APP_NAME, "%s sigue funcionando aquí. Para cerrarlo, usa «Salir»." % APP_NAME, QSystemTrayIcon.Information, 4000)
            return e.ignore()
        if self.code.tabs.has_dirty():
            r = QMessageBox.question(self, "Cambios sin guardar", "Hay archivos con cambios sin guardar. ¿Guardarlos antes de salir?",
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel:
                return e.ignore()
            if r == QMessageBox.StandardButton.Save:
                for t in self.code.tabs.tabs():
                    if t.dirty:
                        t.save()
        busy = [s for s in core.SESSIONS.values() if s.run]
        if busy and QMessageBox.question(self, "Salir", "El agente está trabajando. ¿Detenerlo y salir?") != QMessageBox.StandardButton.Yes:
            return e.ignore()
        self.code.term.stop()
        core.shutdown()
        self.tray.hide()
        e.accept()
        QApplication.quit()


def _dark_titlebar(w):
    """Con la barra nativa (si se desactiva la integrada) al menos se pinta con los colores del tema."""
    if not getattr(w, "frameless", False):
        theme.titlebar_colors(w)


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
    ok("hardware", lambda: HW.summary(HW.detect()) and None)
    ok("engine", lambda: bool(P.LLAMA_PATTERNS) or "sin motores")
    ok("tools", lambda: len(T.TOOLS) >= 25 or "faltan herramientas")
    ok("shell", lambda: "JAYTH_OK" in __import__("subprocess").run(osys.shell_argv("echo JAYTH_OK"), capture_output=True, text=True,
                                                                     timeout=60, **osys.popen_kwargs()).stdout or "la terminal no responde")
    def window():
        w = Main()
        w.tray.hide()
        w.poll_t.stop()
        w.news_t.stop()
    ok("window", window)
    report = {"version": __version__, "os": osys.os_label(), "arch": _pf.machine(), "frozen": osys.FROZEN, "checks": checks}
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
        w.tray.showMessage(APP_NAME, "%s está listo en la bandeja del sistema." % APP_NAME, QSystemTrayIcon.Information, 3000)
    else:
        w.showMaximized()                  # siempre a pantalla completa
    if core.SET.load_error:
        QTimer.singleShot(500, lambda: QMessageBox.warning(w, APP_NAME, core.SET.load_error))
    if not core.SET.ready() and "--no-wizard" not in sys.argv:
        QTimer.singleShot(300, w.setup)
    elif (cfg["autostart_llm"] or "--start-llm" in sys.argv) and cfg["llm_mode"] == "local":
        core.LLM_MGR.start()
        w.llm = {"state": "loading"}
        w.sync()
    sys.exit(app.exec())
