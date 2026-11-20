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
from . import APP_NAME, core, paths, osys, agent as A, tools as T
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
    """Codigo o salida de un comando: caja monoespaciada que se parte al ancho; si es larga se muestra plegada
    (difuminado abajo y flecha para verla entera) en vez de una barra de desplazamiento dentro del chat."""
    return Collapsible(TextView(text, "plain", mono=True, kind=kind), limit=max_h, fade=C["bg"], slack=40)


def md_label(text=""):
    """Respuesta del agente en Markdown. Nunca ensancha el panel: parte código, rutas y URL largas."""
    return TextView(text, "md", size="10.5pt")


class Clickable(QWidget):
    clicked = Signal()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()


_HOTKEY = None

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
        self.setToolTip("Clic para abrir a tamaño completo")

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


def fill_history(lst, sessions, current, query="", empty_text="Tus conversaciones aparecerán aquí", folded=()):
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
        h = QListWidgetItem(("▸  %s  ·  %d" % (grp, len(items))) if shut else ("▾  " + grp))
        h.setFlags(Qt.ItemIsEnabled)
        h.setData(GROUP_ROLE, grp)
        h.setToolTip("Clic para desplegar" if shut else "Clic para plegar")
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
        e = QListWidgetItem("Sin resultados" if query else empty_text)
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
    "read_file": ("leer", "Leyó", lambda a: _b(a.get("path"))),
    "write_file": ("escribir", "Escribió", lambda a: _b(a.get("path"))),
    "create_document": ("crear el documento", "Creó el documento", lambda a: _b(a.get("path"))),
    "run_python": ("analizar con Python", "Analizó con Python", lambda a: ""),
    "show_canvas": ("mostrar en el lienzo", "Mostró en el lienzo", lambda a: "«%s»" % _q(a.get("title"), 50)),
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
    "multi_edit": ("editar", "Editó", lambda a: "%s (%s)" % (_b(a.get("path")), _n(len(a.get("edits") or []), "cambio", "cambios"))),
    "move_path": ("mover", "Movió", lambda a: "%s → %s" % (_b(a.get("source")), _b(a.get("dest")))),
    "delete_path": ("enviar a la papelera", "Envió a la papelera", lambda a: _b(a.get("path"))),
    "command_output": ("revisar la salida de", "Revisó la salida de", lambda a: str(a.get("id"))),
    "stop_command": ("detener", "Detuvo", lambda a: str(a.get("id"))),
    "read_document": ("leer el documento", "Leyó el documento", lambda a: _b(a.get("path"))),
    "view_image": ("ver la imagen", "Vio la imagen", lambda a: _b(a.get("path"))),
    "remember": ("recordar", "Recordó", lambda a: "«%s»" % _q(a.get("fact"), 50)),
    "forget": ("olvidar", "Olvidó", lambda a: "«%s»" % _q(a.get("text"), 50)),
    "use_skill": ("usar la habilidad", "Usó la habilidad", lambda a: "«%s»" % _q(a.get("name"), 50)),
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
        self.title = ElidedLabel()            # una linea; si no cabe termina en «…» (completo en el tooltip)
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
                av.addWidget(TextView("Acción delicada: revisa bien el detalle antes de permitirla.", "plain", color=C["warn"], size="9pt"))
            bw = QWidget()
            row = FlowLayout(bw)
            cat = T.CATEGORIES.get(ev["category"], ev["category"])
            for text, kind, dec in (("Permitir", "primary", "allow"), ("Siempre «%s» aquí" % cat.lower(), None, "allow_category"),
                                    ("Denegar", "danger", "deny")):
                b = btn(text, kind)
                b.clicked.connect(lambda _=False, d=dec: self._decide(d, on_decide))
                row.addWidget(b)
            av.addWidget(bw)
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
        kv = lambda k, val: TextView("<span style='color:%s'>%s:</span> %s" % (C["faint"], k, str(val).replace("&", "&amp;").replace("<", "&lt;")), "html")
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

    def result(self, ok, text, image):
        self._set("ok" if ok else "err")
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
        self.chev.setText("⌄" if self.details.isVisible() else "›")

    def undone(self):
        self.b_undo.hide()
        self.is_undone = True
        card = getattr(self, "doc_card", None)
        if card is not None and not os.path.isfile(card.path):      # el documento ya no existe: fuera su tarjeta
            card.hide()
            if self.box is not None:
                self.box.extras.setVisible(any(not self.box.ev_.itemAt(i).widget().isHidden() for i in range(self.box.ev_.count())))
        self.title.setText(self.title.text() + "  · deshecho")
        self.title.setStyleSheet("color:%s; text-decoration: line-through" % C["faint"])


# Resumen de varias acciones seguidas en una frase («Editó 2 archivos, buscó en los archivos y ejecutó un comando»)
GROUP = {
    "read_file": ("leyó un archivo", "leyó %d archivos"), "write_file": ("creó un archivo", "creó %d archivos"),
    "edit_file": ("editó un archivo", "editó %d archivos"), "list_dir": ("exploró una carpeta", "exploró %d carpetas"),
    "search_files": ("buscó en los archivos", "hizo %d búsquedas"), "run_command": ("ejecutó un comando", "ejecutó %d comandos"),
    "command_output": ("revisó un proceso", "revisó %d procesos"), "stop_command": ("detuvo un proceso", "detuvo %d procesos"),
    "web_search": ("buscó en internet", "hizo %d búsquedas en internet"), "web_fetch": ("leyó una página web", "leyó %d páginas web"),
    "download_file": ("descargó un archivo", "descargó %d archivos"), "read_document": ("leyó un documento", "leyó %d documentos"),
    "create_document": ("creó un documento", "creó %d documentos"), "view_image": ("vio una imagen", "vio %d imágenes"),
    "screenshot": ("hizo una captura de pantalla", "hizo %d capturas de pantalla"), "move_path": ("movió un archivo", "movió %d archivos"),
    "delete_path": ("envió un archivo a la papelera", "envió %d archivos a la papelera"), "remember": ("guardó una preferencia", "guardó %d preferencias"),
    "control": ("usó el ratón y el teclado", "usó el ratón y el teclado"), "open_target": ("abrió un programa o archivo", "abrió %d programas o archivos"),
    "wait": ("esperó un momento", "esperó %d veces"),
    "run_python": ("analizó los datos con Python", "hizo %d análisis con Python"), "show_canvas": ("mostró algo en el lienzo", "actualizó el lienzo %d veces"),
}
_GROUP_ALIAS = {"multi_edit": "edit_file", "click": "control", "move_mouse": "control", "scroll": "control", "type_text": "control",
                "press_keys": "control", "list_windows": "control", "focus_window": "control"}


def summarize_steps(rows):
    order, seen = [], {}
    for r in rows:
        name, a = r.ev["name"], r.ev.get("args") or {}
        if name.startswith("mcp__"):
            key = ("mcp", name.split("__")[1].replace("_", " ") if name.count("__") >= 2 else "un conector")
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
            parts.append("usó %s" % key[1] + ("" if n == 1 else " (%d veces)" % n))
        elif key in GROUP:
            one, many = GROUP[key]
            parts.append(one if n == 1 else (many % n if "%d" in many else many))
        else:
            parts.append("hizo %d %s" % (n, "acción más" if n == 1 else "acciones más"))
    if not parts:
        return ""
    text = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " y " + parts[-1]
    return text[:1].upper() + text[1:]


DOC_KIND = {".docx": ("W", "2B579A", "Documento de Word"), ".xlsx": ("X", "217346", "Hoja de Excel"),
            ".pptx": ("P", "C43E1C", "Presentación de PowerPoint"), ".pdf": ("PDF", "B3261E", "Documento PDF")}


class DocCard(QFrame):
    """Tarjeta de un documento creado por el agente: tipo, nombre, tamaño y botones para abrirlo."""

    def __init__(self, path):
        super().__init__()
        self.setObjectName("docCard")
        self.path = path
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 8, 8, 8)
        h.setSpacing(10)
        tag, col, kind = DOC_KIND.get(os.path.splitext(path)[1].lower(), ("DOC", "607068", "Documento"))
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
        h.addWidget(btn("Abrir", "primary", lambda: os.path.isfile(self.path) and osys.open_path(self.path)))
        h.addWidget(tbtn("act_carpeta_abierta", "Mostrar en la carpeta", lambda: reveal(self.path), size=15))
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
        kind = {"html": "Página web", "markdown": "Documento", "svg": "Dibujo", "code": "Código"}.get(item.get("kind"), "Lienzo")
        sub = ElidedLabel("%s · versión %s" % (kind, item.get("version", 1)))
        sub.setObjectName("faint")
        info.addWidget(sub)
        h.addLayout(info, 1)
        h.addWidget(btn("Ver en el lienzo", "primary", lambda: self.on_open(self.item)))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.on_open(self.item)


class Preview(QLabel):
    """Vista previa de una imagen que el agente ha visto o creado; un clic la abre en grande."""

    def __init__(self, path, max_w=520, max_h=300):
        super().__init__()
        self.path = path
        pm = QPixmap(path)
        if not pm.isNull():
            self.setPixmap(pm.scaled(min(max_w, pm.width()), min(max_h, pm.height()), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Abrir la imagen")
        self.setObjectName("preview")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and os.path.isfile(self.path):
            osys.open_path(self.path)


def reveal(path):
    """Muestra el archivo seleccionado en el Explorador / Finder (o abre su carpeta)."""
    try:
        if osys.WIN:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif osys.MAC:
            subprocess.Popen(["open", "-R", path])
        else:
            osys.open_path(os.path.dirname(path))
    except Exception:
        osys.open_path(os.path.dirname(path))


class StepsBox(QFrame):
    """Acciones seguidas del agente. Mientras trabaja se ven una a una; al terminar, si son varias, se resumen en una
    línea («Editó 2 archivos y ejecutó un comando  +12 −3 ›») que se despliega con un clic. Las imágenes que ve y los
    documentos que crea quedan siempre a la vista debajo."""

    def __init__(self):
        super().__init__()
        self.setObjectName("stepsBox")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 2, 0, 2)
        self.v.setSpacing(0)
        self.rows = []
        self.closed = False
        self.head = Clickable()
        self.head.setCursor(Qt.PointingHandCursor)
        hh = QHBoxLayout(self.head)
        hh.setContentsMargins(10, 6, 8, 6)
        hh.setSpacing(8)
        self.h_icon = QLabel()
        hh.addWidget(self.h_icon)
        self.h_text = ElidedLabel()
        self.h_text.setStyleSheet("color:%s" % C["mut"])
        hh.addWidget(self.h_text, 1)
        self.h_add, self.h_rem, self.h_fail = QLabel(), QLabel(), QLabel()
        for l, col in ((self.h_add, C["ok"]), (self.h_rem, C["bad"]), (self.h_fail, C["bad"])):
            l.setStyleSheet("color:%s; font-size:9pt" % col)
            hh.addWidget(l)
        self.h_chev = QLabel("›")
        self.h_chev.setStyleSheet("color:%s; font-size:12pt" % C["faint"])
        hh.addWidget(self.h_chev)
        self.head.clicked.connect(self.toggle)
        self.head.hide()
        self.v.addWidget(self.head)
        self.body = QWidget()
        self.bv = QVBoxLayout(self.body)
        self.bv.setContentsMargins(0, 0, 0, 0)
        self.bv.setSpacing(0)
        self.v.addWidget(self.body)
        self.extras = QWidget()
        self.ev_ = QVBoxLayout(self.extras)
        self.ev_.setContentsMargins(10, 4, 10, 8)
        self.ev_.setSpacing(6)
        self.extras.hide()
        self.v.addWidget(self.extras)

    def add(self, row):
        if self.rows:
            self.bv.addWidget(hline())
        self.rows.append(row)
        self.bv.addWidget(row)
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
            self.ev_.addWidget(Preview(path), 0, Qt.AlignLeft)
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
        self.h_fail.setText(("%d ha fallado" if fails == 1 else "%d han fallado") % fails if fails else "")
        ico, col = ("est_aviso", C["warn"]) if fails else ("ui_check", C["ok"])
        self.h_icon.setPixmap(pix(ico, col, 14))
        self.head.show()
        self.body.hide()
        self.h_chev.setText("›")

    def toggle(self):
        self.body.setVisible(not self.body.isVisible())
        self.h_chev.setText("⌄" if self.body.isVisible() else "›")


# ---------------------------------------------------------------- mensajes
class AssistantBlock(QWidget):
    def __init__(self, started, step=1):
        super().__init__()
        self.started = started
        # primer paso: el modelo lee el mensaje; despues, lo que devolvieron las herramientas
        self.wait_text = "Leyendo tu mensaje…" if (step or 1) <= 1 else "Revisando los resultados…"
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
        self.status_lbl = QLabel(self.wait_text)
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
        self.stats = FitLabel()              # una sola linea: si no cabe, una version mas corta
        self.stats.setObjectName("stats")
        self.stats.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        ah.addWidget(self.stats, 1)
        self.actions.hide()
        v.addWidget(self.actions)
        self.text = ""

    def tick(self, now):
        if self.status.isVisible():
            self.status_lbl.setText("%s %d s" % (self.wait_text, max(0, now - self.started)))
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
            self.body.show()
            # el Markdown se vuelve a dibujar como mucho cada 90 ms: con modelos rapidos llegan decenas de trozos por segundo
            if not getattr(self, "_render_t", None):
                self._render_t = QTimer(self, singleShot=True, interval=90, timeout=lambda: self.body.setText(self.text))
            if not self._render_t.isActive():
                self._render_t.start()

    def _end_think(self, ts):
        if self.r_start and not self.r_end:
            self.r_end = ts
            self.think_btn.setText("Pensó durante %d s" % max(1, round(self.r_end - self.r_start)))

    def finish(self, text, ts):
        self.spin.stop()
        self.status.hide()
        self._end_think(ts)
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
        self.free.setPlaceholderText("Otra respuesta…")
        self.free.returnPressed.connect(lambda: self.free.text().strip() and self._send(self.free.text().strip(), on_answer))
        r2.addWidget(self.free, 1)
        r2.addWidget(btn("Responder", "primary", lambda: self.free.text().strip() and self._send(self.free.text().strip(), on_answer)))
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
        pm.addSeparator()
        self.assist_menu = pm.addMenu(icon("ia_controlador"), "Usar un asistente")
        self.assist_menu.aboutToShow.connect(self._fill_assist_menu)
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
            return EmptyState("¿Qué construimos en «%s»?" % (p["name"] if p else "tu proyecto"),
                              "Trabajo dentro de la carpeta del proyecto. Verás cada archivo que cree o cambie.",
                              CODE_SUGGESTIONS, self._pick, self.compact)
        if getattr(self, "temp_next", False):
            return EmptyState("Chat temporal", "Esta conversación no se guardará en el historial y no usa ni cambia la memoria. "
                              "Al empezar otra conversación, desaparece.", [], self._pick, self.compact)
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
            self.add(user_bubble(ev, self.compact))
        elif t == "turn_start":
            self.cur = self.add(AssistantBlock(ev["ts"], ev.get("step", 1)))
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
                cut = " · cortado por límite" if ev.get("finish") == "length" else ""
                ctx = ctx_s = ""
                if ev.get("ctx_used") and ev.get("ctx_max"):
                    ctx = " · contexto %.1fk de %dk" % (ev["ctx_used"] / 1000.0, ev["ctx_max"] // 1000)
                    ctx_s = " · %.1fk/%dk" % (ev["ctx_used"] / 1000.0, ev["ctx_max"] // 1000)
                self.cur.stats.set_options([tok + tps + cut + ctx, tok + tps + cut + ctx_s, (tps[3:] or tok) + cut + ctx_s,
                                            (cut[3:] or (ctx_s[3:] or tok))],
                                           "Memoria de la conversación usada por el modelo. Al acercarse al límite, Jayth resume lo antiguo.")
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
            self._end_steps()
        elif t == "compacted":
            self.add(note("Resumí la parte antigua de la conversación para que el modelo no la olvide ni se quede sin memoria."))
            self._end_steps()
        elif t == "plan_ready":
            if getattr(self, "_live", False):
                self.add(self._plan_ready_card())
                self._end_steps()
        elif t == "tool_call":
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
            r = self.rows.get(ev["id"])
            if r:
                r.result(ev["ok"], ev.get("text") or "", ev.get("image"))
                if ev["ok"] and r.ev["name"] in ("remember", "forget") and ev["ts"] > time.time() - 10:
                    fact = str((r.ev.get("args") or {}).get("fact") or (r.ev.get("args") or {}).get("text") or "")
                    self.main.toast(("Guardado en la memoria: «%s»" if r.ev["name"] == "remember" else "Olvidado: «%s»") % fact[:90],
                                    "Ver memoria", lambda: self.main.settings("Personalización"), icon_name="ia_memoria")
                if ev["ok"] and r.box is not None:
                    for n in (ev.get("images") or [])[1:]:           # el resto de gráficos de un análisis
                        r.box.add_preview(os.path.join(paths.IMG_DIR, n))
                    if ev.get("canvas"):
                        r.box.add_canvas(ev["canvas"], self.main.open_canvas)
                        if ev["ts"] > time.time() - 10:               # en directo se abre solo; al reabrir la conversación, no
                            self.main.open_canvas(ev["canvas"])
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
            self.turn_blocks = []
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
        for b in self.blocks:                # ya no queda nada que deshacer en esta respuesta
            b.b_undo_all.hide()
        if files:
            self.main.toast("Deshecho%s %s." % ("" if len(files) == 1 else "s", _n(len(files), "cambio de archivo", "cambios de archivos")),
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
            return self.main.setup()
        if not self.session():
            temp = bool(getattr(self, "temp_next", False))
            aid = getattr(self, "assistant_next", None)
            ns = core.new_session(self.project_id, temp=temp)
            if aid:
                ns.data["assistant"] = aid
            self.open_session(ns.id)
            if temp:
                self.add(note("Chat temporal: esta conversación no se guarda en el historial y no usa ni cambia la memoria."))
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
            self.mode_chip.setToolTip(("Modo: %s. " % self.mode_chip.text() if compact_mode else "") + "Cómo actúa el agente: pregunta, automático, solo lectura o plan.")
        free -= 34 if compact_mode else mode_full
        room = free - pad - fm.horizontalAdvance(" · " + label)
        room = min(room, 120 if self.compact else 220)
        text = "%s · %s" % (fm.elidedText(name, Qt.ElideRight, max(48, room)), label)
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
            na = m.addAction("Aún no tienes asistentes")
            na.setEnabled(False)
        m.addSeparator()
        m.addAction("Crear o editar asistentes…", lambda: self.main.assistants())
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
            self.input.setPlainText((cur + ("\n" if cur and not cur.endswith("\n") else "")) + "\n".join("Carpeta: %s" % d for d in dirs))
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
            self._drop = QLabel("Suelta aquí para adjuntar\nimágenes, documentos o archivos", self)
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
            h.addWidget(tbtn("ui_cerrar", "Quitar", lambda _=False, n=n: (self.pending_imgs.remove(n), self._render_thumbs()), size=12), 0, Qt.AlignTop)
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
            h.addWidget(QLabel("Asistente: " + a["name"]))
            if not (self.session() and self.session().events):
                h.addWidget(tbtn("ui_cerrar", "Quitar el asistente", lambda _=False: self.set_assistant(None), size=11))
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
            h.addWidget(tbtn("ui_cerrar", "Quitar", lambda _=False, f=f: (self.pending_files.remove(f), self._render_thumbs()), size=11))
            w.setToolTip(f)
            self.thumbs.addWidget(w)
        self.thumbs_w.setVisible(bool(self.pending_imgs or getattr(self, "pending_files", []) or a))
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
        eff = core.effort_of(cfg)
        label, desc = next((l, d) for k, l, d in core.EFFORTS if k == eff)
        ext = cfg["llm_mode"] == "external"
        m = core.active_model(cfg)
        name = ((cfg["external_model"] or "servidor externo").split("/")[-1]) if ext else (core.model_title(m) if m else "Elegir modelo")
        self._chip_name, self._chip_label = name, label
        self._fit_model_chip()                                          # modelo · esfuerzo (se cambian en el mismo menú)
        self.model_chip.setToolTip("%s\nEsfuerzo %s: %s\nPulsa para cambiar de modelo o de esfuerzo." % (
            ("%s · %s" % (core.model_title(m), core.model_quant(m))) if (m and not ext) else name, label.lower(), desc))
        self.input.setPlaceholderText("Pide algo sobre el proyecto…" if self.project_id else "Escribe un mensaje…")
        self._sync_send()


# ---------------------------------------------------------------- pagina del modo Code
CODE_LAYOUT = {"tree": True, "term": True, "agent": True, "agent_side": "right", "term_pos": "bottom",
               "w_tree": 230, "w_agent": 420, "h_term": 220, "w_term": 420, "focus": None}
CHAT_WIDTHS = [("Estrecha", 660), ("Normal", 780), ("Ancha", 1040), ("Todo el ancho", 0)]


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
        # espacio de trabajo: explorador | editor (+ terminal) | agente. Todo se redimensiona, se pliega y se recuerda;
        # el agente puede ir a la izquierda o a la derecha y la terminal abajo o a la derecha del editor.
        ws = QWidget()
        wl = QHBoxLayout(ws)
        wl.setContentsMargins(0, 0, 0, 0)
        self.split = panels.Splitter(Qt.Horizontal, "codeSplit")
        left = QWidget()
        self.left = left
        left.setProperty("foldable", True)
        left.setMinimumWidth(160)
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
            self.main.toast("Modo enfoque: solo el editor. Pulsa Ctrl+Shift+M para volver.", ms=3500, icon_name="app_pantalla_completa")
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
        self.toast("Distribución de paneles restablecida.", ms=2500, icon_name="act_layout_ui")

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
        check("Barra lateral fija", self.side_pinned(), self.toggle_sidebar, "ui_barra_lateral", "Ctrl+Shift+S")
        if self.mode == "code" and self.code.project:
            c = self.code
            check("Explorador de archivos", not c.left.isHidden(), c.toggle_tree, "pan_explorador", "Ctrl+B")
            check("Terminal", not c.term.isHidden(), c.toggle_terminal, "pan_consola", "Ctrl+`")
            check("Panel del agente", not c.chat.isHidden(), c.toggle_agent, "mat_comentario", "Ctrl+L")
            m.addSeparator()
            g1 = QActionGroup(m)
            for side, text in (("left", "Agente a la izquierda"), ("right", "Agente a la derecha")):
                a = check(text, c.lay["agent_side"] == side, lambda s=side: c.set_agent_side(s), "uij_alinear_izq" if side == "left" else "uij_alinear_der")
                g1.addAction(a)
            g2 = QActionGroup(m)
            for pos, text, ico in (("bottom", "Terminal debajo del editor", "ui_dividir_v"), ("right", "Terminal a la derecha del editor", "ui_dividir_h")):
                a = check(text, c.lay["term_pos"] == pos, lambda p=pos: c.set_term_pos(p), ico)
                g2.addAction(a)
            m.addSeparator()
            check("Modo enfoque (solo el editor)", c.lay.get("focus"), c.toggle_focus, "app_pantalla_completa", "Ctrl+Shift+M")
        else:
            m.addSeparator()
            sub = m.addMenu(icon("uij_layout_horizontal"), "Ancho de la conversación")
            g = QActionGroup(sub)
            for text, px in CHAT_WIDTHS:
                a = sub.addAction(text, lambda *_, px=px: self.set_chat_width(px))
                a.setCheckable(True)
                a.setChecked((self.chat_width or 0) == px)
                g.addAction(a)
        m.addSeparator()
        m.addAction(icon("acc_refrescar"), "Restablecer la distribución", self.reset_layout)

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
        b_hide = tbtn("ui_menu_hamburguesa", "Ocultar barra lateral  ·  Ctrl+Shift+S", self.toggle_sidebar, size=16)
        b_hide.setAccessibleName("Ocultar barra lateral")
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
        self._nav(kl, "acc_anadir", "Nuevo proyecto", self.new_project)
        self._nav(kl, "act_carpeta_abierta", "Abrir carpeta…", self.open_folder_project)
        # secciones plegables: Proyectos y Conversaciones del proyecto
        self.sec_projects = panels.Section("Proyectos")
        kl.addWidget(self.sec_projects)
        self.plist = QListWidget()
        self.plist.setObjectName("history")
        elide_list(self.plist)
        self.plist.setMaximumHeight(170)
        self.plist.itemClicked.connect(lambda it: it.data(Qt.UserRole) and self.select_project(it.data(Qt.UserRole)))
        self.plist.setContextMenuPolicy(Qt.CustomContextMenu)
        self.plist.customContextMenuRequested.connect(self._project_menu)
        kl.addWidget(self.plist)
        self.sec_convs = panels.Section("Conversaciones del proyecto")
        self.sec_convs.extra.addWidget(tbtn("acc_renombrar", "Nueva conversación del proyecto (Ctrl+N)", self.new_conversation, size=14))
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
        pm.addAction(icon("ia_memoria"), "Memoria", lambda: self.settings("Personalización"))
        pm.addAction(icon("ia_controlador"), "Asistentes y habilidades", self.assistants)
        pm.addAction(icon("ia_controlador"), "Modelos", self.models)
        pm.addAction(icon("hub_conectar"), "Modelos por API…", self.providers)
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
        self.b_expand = tbtn("ui_menu_hamburguesa", "Barra lateral: pasa el ratón para verla, clic para dejarla fija  ·  Ctrl+Shift+S",
                             self.toggle_sidebar, size=16)
        self.b_expand.setAccessibleName("Barra lateral")
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
        self.b_tree = tbtn("pan_explorador", "Explorador de archivos  ·  Ctrl+B", lambda: self.code.toggle_tree())
        self.b_term = tbtn("pan_consola", "Terminal  ·  Ctrl+`", lambda: self.code.toggle_terminal())
        self.b_agent = tbtn("mat_comentario", "Panel del agente  ·  Ctrl+L", lambda: self.code.toggle_agent())
        for b in (self.b_tree, self.b_term, self.b_agent):
            h.addWidget(b)
        self.b_temp = QToolButton()
        self.b_temp.setObjectName("chip")
        self.b_temp.setText("Temporal")
        self.b_temp.setCheckable(True)
        self.b_temp.setCursor(Qt.PointingHandCursor)
        self.b_temp.setAccessibleName("Chat temporal")
        self.b_temp.setToolTip("Chat temporal: una conversación que no se guarda en el historial y no usa ni cambia la memoria")
        self.b_temp.clicked.connect(lambda on: self.toggle_temp(on))
        h.addWidget(self.b_temp)
        self.b_layout = tbtn("act_layout_ui", "Distribución de paneles")
        self.b_layout.setPopupMode(QToolButton.InstantPopup)
        self.layout_menu = QMenu(self)
        self.layout_menu.aboutToShow.connect(self._fill_layout_menu)
        self.b_layout.setMenu(self.layout_menu)
        h.addWidget(self.b_layout)
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
            self.toast("Ventana rápida: pulsa %s desde cualquier programa." % combo, icon_name="ui_check", color=C["ok"])

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
            return self.toast("El agente sigue trabajando; espera a que termine o detenlo.", icon_name="est_aviso", color=C["warn"])
        p.open_session(None)
        if shot:
            p._add_image(qimage=QImage.fromData(shot))
        p.input.setPlainText(text)
        p.send()

    # ---- lienzo
    def open_canvas(self, item):
        """Muestra en el lienzo un contenido creado por el agente ({title, kind, path, version, slug})."""
        if not item or not os.path.isfile(item.get("path", "")):
            return self.toast("Ese contenido del lienzo ya no existe.", icon_name="est_aviso", color=C["warn"])
        self.canvas.load(item)
        self.set_canvas(True)

    def set_canvas(self, on):
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
        m.addAction(icon("acc_abrir_externo"), "Mostrar", self._show)
        m.addAction(icon("mat_comentario"), "Pregunta rápida", lambda: QTimer.singleShot(250, self.quick_open))
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
                e = QListWidgetItem("Aún no hay proyectos")
                e.setFlags(Qt.NoItemFlags)
                e.setForeground(QGuiApplication.palette().placeholderText())
                self.plist.addItem(e)
            fill_history(self.clist, cs, self.code.chat.sid, empty_text="Las conversaciones del proyecto aparecerán aquí", folded=self.folded)

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
            s.rename(t)          # a partir de aqui el modelo ya no cambia el nombre
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
    def _fill_model_menu(self, m=None):
        """Menu del modelo: tus modelos (variante a la derecha), Esfuerzo ›, Más modelos › y el interruptor del motor."""
        m = m if m is not None else self.model_menu
        m.clear()
        m.setToolTipsVisible(True)
        cfg = core.SET.snapshot()
        ext = cfg["llm_mode"] == "external"
        grp = QActionGroup(m)
        for md in cfg["models"]:
            a = m.addAction(core.model_title(md) + ("\t" + core.model_quant(md) if core.model_quant(md) else ""))
            a.setCheckable(True)
            a.setChecked(not ext and md["id"] == cfg["active_model"])
            a.setToolTip(md.get("path", ""))
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
            a = m.addAction("%s\tservidor externo" % (cfg["external_model"] or cfg["external_url"]))
            a.setCheckable(True)
            a.setChecked(ext)
            grp.addAction(a)
            a.triggered.connect(lambda: (core.LLM_MGR.stop(), core.SET.update({"llm_mode": "external"}), self.poll()))
        if not cfg["models"] and not (ext or cfg["external_model"]) and not provs:
            na = m.addAction("Aún no tienes modelos")
            na.setEnabled(False)
        m.addSeparator()
        # esfuerzo: cuanto razona el modelo antes de responder
        eff = core.effort_of(cfg)
        label = next(l for k, l, d in core.EFFORTS if k == eff)
        em = m.addMenu(icon("ia_memoria"), "Esfuerzo\t%s" % label)
        em.setToolTipsVisible(True)
        eg = QActionGroup(em)
        hints = {"low": "más rápido", "medium": "equilibrado", "high": "más preciso"}
        for k, l, d in core.EFFORTS:
            a = em.addAction("%s\t%s" % (l, hints[k]))
            a.setCheckable(True)
            a.setChecked(k == eff)
            a.setToolTip(d)
            eg.addAction(a)
            a.triggered.connect(lambda _=False, k=k: (core.set_effort(k), self.sync()))
        more = m.addMenu(icon("acc_anadir"), "Más modelos")
        more.addAction(icon("acc_descargar"), "Descargar o añadir un modelo…", lambda: self.setup("model"))
        more.addAction(icon("ia_controlador"), "Gestionar modelos…", self.models)
        more.addAction(icon("hub_conectar"), "Modelos por API (OpenAI, Claude, Gemini, Ollama…)…", self.providers)
        if not ext:
            m.addSeparator()
            sec = m.addAction("Motor")
            sec.setEnabled(False)
            st = self.llm.get("state", "off")
            on = m.addAction("Modelo encendido" if st != "loading" else "Cargando el modelo…")
            on.setCheckable(True)
            on.setChecked(st in ("ready", "loading"))
            on.setToolTip("Encendido, el modelo ocupa memoria y responde al momento; apagado, libera la memoria.")
            on.triggered.connect(lambda _=False: self.toggle_llm())

    def toggle_temp(self, on):
        """Empieza (o abandona) un chat temporal en el modo Chat."""
        p = self.chat
        if p.busy:
            self.b_temp.setChecked(not on)
            return self.toast("Espera a que el agente termine.", icon_name="est_aviso", color=C["warn"])
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
            self.title.setText(("Chat temporal" if s.temp else s.title) if s and s.events else ("" if self.mode == "chat" else CODE_NAME))
        temp_on = self.mode == "chat" and (bool(getattr(self.chat, "temp_next", False)) or bool(self.chat.session() and self.chat.session().temp))
        self.b_temp.setVisible(self.mode == "chat")
        self.b_temp.setChecked(temp_on)
        self.b_folder.setToolTip("Carpeta de trabajo: %s" % panel.workspace())
        in_code = self.mode == "code" and self.code.project is not None
        for b, w, ico in ((self.b_tree, self.code.left, "pan_explorador"), (self.b_term, self.code.term, "pan_consola"),
                          (self.b_agent, self.code.chat, "mat_comentario")):
            b.setVisible(in_code)
            b.setIcon(icon(ico, C["acc"] if not w.isHidden() else C["faint"], 18))
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
        if a.get("quick_hotkey") != b.get("quick_hotkey"):
            self._apply_hotkey(tell=True)
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


def install_spanish(app):
    """Textos propios de Qt en español: menús contextuales (Copiar, Seleccionar todo…) y botones estándar (Sí/No)."""
    from PySide6.QtCore import QTranslator, QLibraryInfo
    folders = [QLibraryInfo.path(QLibraryInfo.TranslationsPath)]
    if osys.FROZEN:
        folders.append(os.path.join(getattr(sys, "_MEIPASS", paths.APP_DIR), "PySide6", "translations"))
    for d in folders:
        tr = QTranslator(app)
        if tr.load("qtbase_es", d):
            app.installTranslator(tr)
            app._tr_es = tr
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
    ok("hardware", lambda: HW.summary(HW.detect()) and None)
    ok("engine", lambda: bool(P.LLAMA_PATTERNS) or "sin motores")
    ok("spanish", lambda: install_spanish(app) or "sin traducción de Qt al español")
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
    report = {"version": __version__, "os": osys.os_label(), "arch": _pf.machine(), "frozen": osys.FROZEN, "web_canvas": web, "checks": checks}
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
    install_spanish(app)
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
