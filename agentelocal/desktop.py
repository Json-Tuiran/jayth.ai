"""Aplicacion de escritorio (Qt). Barra lateral con historial, conversacion centrada con los pasos del
agente y aprobaciones en linea, y compositor redondeado. Usa el mismo nucleo que la interfaz web."""
import os, sys, json, uuid, time, shutil, threading, ctypes, datetime
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QSize, QEvent
from PySide6.QtGui import QPixmap, QImage, QKeySequence, QShortcut, QFont, QGuiApplication, QAction, QActionGroup
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
                               QListWidget, QListWidgetItem, QScrollArea, QFrame, QPlainTextEdit, QFileDialog, QMessageBox, QMenu,
                               QSystemTrayIcon, QSizePolicy, QToolButton, QInputDialog, QLineEdit)
from . import APP_NAME, core, paths, agent as A, tools as T
from . import theme
from .theme import C, restyle, make_icon, icon, pix
from .wizard import SetupWizard, ModelsDialog, SettingsDialog, btn, lbl, set_icon

MODE_LABEL = {k: v.split(":")[0] for k, v in A.MODES.items()}


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
            os.startfile(self.path)


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
}
CAT_ICON = {"read": "acc_examinar", "write": "acc_renombrar", "exec": "cod_terminal", "net": "herr_espacio_mundo", "control": "inp_raton"}


def describe(name, args, phase):
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
        self.st_icon = QLabel()
        self.st_icon.setFixedSize(18, 18)
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
        tn = QLabel(ev["name"])
        tn.setObjectName("faint")
        h.addWidget(tn)
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
            for text, kind, dec in (("Permitir", "primary", "allow"), ("Permitir siempre «%s» en esta conversación" % cat.lower(), None, "allow_category"),
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
        self.st_icon.setPixmap(pix(ico, col, 14))
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
        if image:
            img = ImageLabel(os.path.join(paths.IMG_DIR, image))
            self.dl.addWidget(img)
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
            sep = QFrame()
            sep.setFixedHeight(1)
            sep.setStyleSheet("background:%s" % C["line"])
            self.v.addWidget(sep)
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
        sh.addWidget(pix_label("est_cargando", C["acc"], 14))
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
        ah.addWidget(self.b_copy)
        ah.addWidget(self.b_regen)
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


def user_bubble(ev):
    wrap = QWidget()
    h = QHBoxLayout(wrap)
    h.setContentsMargins(0, 6, 0, 2)
    h.addStretch(1)
    box = QFrame()
    box.setObjectName("userBubble")
    box.setMaximumWidth(560)
    v = QVBoxLayout(box)
    v.setContentsMargins(14, 9, 14, 9)
    for n in ev.get("images") or []:
        v.addWidget(ImageLabel(os.path.join(paths.IMG_DIR, n), 240, 160))
    t = lbl(ev["text"])
    t.setStyleSheet("font-size:10.5pt")
    v.addWidget(t)
    h.addWidget(box)
    return wrap


SUGGESTIONS = [("acc_examinar", "Ordena mi carpeta de Descargas por tipo de archivo"),
               ("cod_terminal", "Crea un script de Python que renombre mis fotos por fecha"),
               ("vista_captura", "Haz una captura de pantalla y dime qué ves"),
               ("herr_espacio_mundo", "Busca en la web las novedades de llama.cpp y resúmelas")]


class EmptyState(QWidget):
    def __init__(self, name, on_pick):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 70, 0, 0)
        v.setSpacing(18)
        logo = QLabel()
        logo.setPixmap(make_icon().pixmap(52, 52))
        logo.setAlignment(Qt.AlignCenter)
        v.addWidget(logo)
        g = QLabel("¿En qué te ayudo%s?" % (", " + name if name else " hoy"))
        g.setObjectName("greeting")
        g.setAlignment(Qt.AlignCenter)
        v.addWidget(g)
        s = QLabel("Puedo trabajar con tus archivos, programas y la web. Cada acción la ves y la apruebas tú.")
        s.setObjectName("muted")
        s.setAlignment(Qt.AlignCenter)
        s.setWordWrap(True)
        v.addWidget(s)
        grid = QGridLayout()
        grid.setSpacing(10)
        for i, (ico, text) in enumerate(SUGGESTIONS):
            b = QPushButton(text)
            b.setObjectName("suggestion")
            b.setIcon(icon(ico, C["acc"], 16))
            b.setIconSize(QSize(16, 16))
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(48)
            b.clicked.connect(lambda _=False, t=text: on_pick(t))
            grid.addWidget(b, i // 2, i % 2)
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
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
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


class _Sig(QObject):
    status = Signal(object)


# ---------------------------------------------------------------- ventana principal
class Main(QMainWindow):
    def __init__(self, sid=None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_icon())
        self.resize(1240, 820)
        self.setMinimumSize(880, 560)
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
        self.llm = {"state": "off"}
        self.sig = _Sig()
        self.sig.status.connect(self._got_status)
        self._polling = False
        self._list_sig = None
        self._swapping = False
        self._build()
        self._tray()
        if not core.SESSIONS:
            core.load_sessions()
        first = core.sorted_sessions()
        self.open_session(sid if sid in core.SESSIONS else None)
        self.pump_t = QTimer(self, interval=60, timeout=self.pump)
        self.pump_t.start()
        self.poll_t = QTimer(self, interval=2500, timeout=self.poll)
        self.poll_t.start()
        self.tick_t = QTimer(self, interval=1000, timeout=lambda: self.cur and self.cur.tick(time.time()))
        self.tick_t.start()
        self.poll()
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_session)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.focus_search)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, activated=self.toggle_sidebar)
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
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        holder = QWidget()
        holder.setObjectName("chatHolder")
        self.scroll.viewport().setObjectName("chatHolder")
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(24, 12, 24, 24)
        self.col = QWidget()
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
        sb.valueChanged.connect(lambda v: setattr(self, "stick", v >= sb.maximum() - 60))
        mv.addWidget(self.scroll, 1)
        mv.addWidget(self._composer())
        root.addWidget(main, 1)
        self._sync_controls()

    def _sidebar(self):
        self.side = QWidget()
        self.side.setObjectName("sidebar")
        self.side.setFixedWidth(264)
        sv = QVBoxLayout(self.side)
        sv.setContentsMargins(10, 12, 10, 10)
        sv.setSpacing(2)
        top = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(make_icon().pixmap(24, 24))
        top.addWidget(logo)
        name = QLabel(APP_NAME)
        name.setStyleSheet("font-weight:600; font-size:11pt")
        top.addWidget(name, 1)
        top.addWidget(tbtn("ui_menu_hamburguesa", "Ocultar barra lateral (Ctrl+Shift+S)", self.toggle_sidebar, size=16))
        sv.addLayout(top)
        sv.addSpacing(8)

        def nav(ico, text, cb, tip=""):
            b = QPushButton(text)
            b.setObjectName("nav")
            b.setIcon(icon(ico, C["tx"], 16))
            b.setIconSize(QSize(16, 16))
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(tip)
            b.clicked.connect(cb)
            sv.addWidget(b)
            return b
        nav("acc_renombrar", "Nueva conversación", self.new_session, "Ctrl+N")
        nav("acc_buscar", "Buscar", self.focus_search, "Ctrl+K")
        nav("ia_controlador", "Modelos", self.models)
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Buscar en tus conversaciones")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda: (setattr(self, "_list_sig", None), self.refresh_sessions()))
        self.search.hide()
        sv.addWidget(self.search)
        sv.addSpacing(6)
        self.list = QListWidget()
        self.list.setObjectName("history")
        self.list.itemClicked.connect(lambda it: it.data(Qt.UserRole) and self.open_session(it.data(Qt.UserRole)))
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        sv.addWidget(self.list, 1)
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background:%s" % C["line"])
        sv.addWidget(sep)
        foot = Clickable()
        foot.setCursor(Qt.PointingHandCursor)
        foot.setToolTip("Ajustes")
        foot.clicked.connect(self.settings)
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(4, 8, 4, 2)
        self.avatar = QLabel()
        self.avatar.setObjectName("avatar")
        self.avatar.setFixedSize(26, 26)
        self.avatar.setAlignment(Qt.AlignCenter)
        fh.addWidget(self.avatar)
        self.user_lbl = QLabel()
        fh.addWidget(self.user_lbl, 1)
        fh.addWidget(pix_label("acc_ajustes", C["mut"], 16))
        sv.addWidget(foot)
        return self.side

    def _header(self):
        head = QWidget()
        h = QHBoxLayout(head)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(6)
        self.b_expand = tbtn("ui_menu_hamburguesa", "Mostrar barra lateral (Ctrl+Shift+S)", self.toggle_sidebar, size=16)
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
        self.b_folder = tbtn("act_carpeta_abierta", "", lambda: os.startfile(core.SET.snapshot()["workspace"]))
        h.addWidget(self.b_folder)
        more = tbtn("ui_menu_horizontal", "Más opciones")
        more.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(self)
        m.addAction(icon("acc_renombrar"), "Renombrar conversación", self.rename_current)
        m.addAction(icon("act_carpeta_abierta"), "Abrir carpeta de trabajo", lambda: os.startfile(core.SET.snapshot()["workspace"]))
        m.addSeparator()
        m.addAction(icon("acc_eliminar", C["bad"]), "Borrar conversación", self.delete_current)
        more.setMenu(m)
        h.addWidget(more)
        return head

    def _composer(self):
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(24, 0, 24, 10)
        v.setSpacing(6)
        inner = QWidget()
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
        bl.addWidget(self.ban_txt, 1)
        self.ban_btn = btn("Encender modelo", "primary", self.toggle_llm)
        bl.addWidget(self.ban_btn)
        iv.addWidget(self.banner)
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
        self.input.pasted_image.connect(self._paste_img)
        self.input.focus.connect(lambda f: (self.box.setProperty("focus", f), restyle(self.box)))
        self.input.textChanged.connect(self._sync_send)
        bv.addWidget(self.input)
        row = QHBoxLayout()
        row.setSpacing(6)
        plus = tbtn("acc_anadir", "Adjuntar", size=14, name="round")
        plus.setFixedSize(28, 28)
        plus.setPopupMode(QToolButton.InstantPopup)
        pm = QMenu(self)
        pm.addAction(icon("uij_imagen"), "Adjuntar imagen…", self.attach)
        pm.addAction(icon("vista_captura"), "Adjuntar captura de pantalla", self.attach_screenshot)
        plus.setMenu(pm)
        row.addWidget(plus)
        self.mode_chip = QToolButton()
        self.mode_chip.setObjectName("chip")
        self.mode_chip.setIcon(icon("est_bloqueado", C["mut"], 13))
        self.mode_chip.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.mode_chip.setPopupMode(QToolButton.InstantPopup)
        self.mode_chip.setToolTip("Permisos del agente")
        mm = QMenu(self)
        grp = QActionGroup(self)
        self.mode_actions = {}
        for k, desc in A.MODES.items():
            a = mm.addAction(MODE_LABEL[k])
            a.setCheckable(True)
            a.setToolTip(desc)
            a.setStatusTip(desc)
            grp.addAction(a)
            a.triggered.connect(lambda _=False, k=k: (core.SET.update({"mode": k}), self._sync_controls()))
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
        self.think_chip.toggled.connect(lambda on: core.SET.update({"thinking": on}))
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
        hint = QLabel("Se ejecuta en tu equipo. Revisa cada acción antes de permitirla · ratón a la esquina superior izquierda = detener el control")
        hint.setObjectName("faint")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        iv.addWidget(hint)
        outer = QHBoxLayout()
        outer.addWidget(inner)
        v.addLayout(outer)
        return wrap

    def _tray(self):
        self.tray = QSystemTrayIcon(make_icon(), self)
        self.tray.setToolTip(APP_NAME)
        m = QMenu()
        m.addAction(icon("acc_abrir_externo"), "Mostrar", self._show)
        m.addAction(icon("trans_detener"), "Detener agente", self.stop)
        m.addSeparator()
        m.addAction(icon("ui_cerrar"), "Salir", self.close)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(lambda r: r == QSystemTrayIcon.Trigger and self._show())
        self.tray.show()

    def _show(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ---- barra lateral
    def toggle_sidebar(self):
        vis = not self.side.isVisible()
        self.side.setVisible(vis)
        self.b_expand.setVisible(not vis)

    def focus_search(self):
        if not self.side.isVisible():
            self.toggle_sidebar()
        self.search.show()
        self.search.setFocus()
        self.search.selectAll()

    def _escape(self):
        if self.search.isVisible() and (self.search.hasFocus() or self.search.text()):
            self.search.clear()
            self.search.hide()

    def refresh_sessions(self):
        q = self.search.text().strip().lower() if self.search.isVisible() else ""
        ss = [s for s in core.sorted_sessions() if not q or q in s.search_text()]
        sig = (q, [(s.id, s.title, s.run is not None) for s in ss], self.sid)
        if sig == self._list_sig:
            return
        self._list_sig = sig
        self.list.blockSignals(True)
        self.list.clear()
        today = datetime.date.today()
        last = None
        for s in ss:
            d = (today - datetime.date.fromtimestamp(s.updated)).days
            grp = "Hoy" if d <= 0 else "Ayer" if d == 1 else "Últimos 7 días" if d < 7 else "Últimos 30 días" if d < 30 else "Anteriores"
            if grp != last:
                h = QListWidgetItem(grp)
                h.setFlags(Qt.NoItemFlags)
                h.setForeground(QGuiApplication.palette().placeholderText())
                f = h.font()
                f.setPointSizeF(8.5)
                h.setFont(f)
                self.list.addItem(h)
                last = grp
            it = QListWidgetItem(s.title)
            if s.run is not None:
                it.setIcon(icon("est_cargando", C["warn"], 14))
            it.setData(Qt.UserRole, s.id)
            it.setToolTip(s.title)
            self.list.addItem(it)
            if s.id == self.sid:
                it.setSelected(True)
                self.list.setCurrentItem(it)
        if not ss:
            e = QListWidgetItem("Sin resultados" if q else "Tus conversaciones aparecerán aquí")
            e.setFlags(Qt.NoItemFlags)
            self.list.addItem(e)
        self.list.blockSignals(False)

    def _list_menu(self, pos):
        it = self.list.itemAt(pos)
        if not it or not it.data(Qt.UserRole):
            return
        s = core.SESSIONS.get(it.data(Qt.UserRole))
        m = QMenu(self)
        a_ren = m.addAction(icon("acc_renombrar"), "Renombrar")
        a_del = m.addAction(icon("acc_eliminar", C["bad"]), "Borrar")
        a = m.exec(self.list.mapToGlobal(pos))
        if a == a_ren:
            self._rename(s)
        elif a == a_del:
            self._delete(s)

    def _rename(self, s):
        t, ok = QInputDialog.getText(self, "Renombrar", "Nuevo nombre:", text=s.title)
        if ok and t.strip():
            s.title = t.strip()[:80]
            s.save()
            self._list_sig = None
            self.refresh_sessions()
            self._sync_controls()

    def _delete(self, s):
        if QMessageBox.question(self, "Borrar conversación", "¿Borrar «%s»? No se puede deshacer." % s.title) == QMessageBox.StandardButton.Yes:
            s.delete()
            if self.sid == s.id:
                self.open_session(None)
            self._list_sig = None
            self.refresh_sessions()

    def rename_current(self):
        s = core.SESSIONS.get(self.sid) if self.sid else None
        if s:
            self._rename(s)

    def delete_current(self):
        s = core.SESSIONS.get(self.sid) if self.sid else None
        if s:
            self._delete(s)

    # ---- conversacion
    def new_session(self):
        self.open_session(None)
        self.input.setFocus()

    def clear_chat(self):
        while self.cl.count() > 1:
            it = self.cl.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()

    def add(self, w):
        self.cl.insertWidget(self.cl.count() - 1, w)
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
        self.clear_chat()
        s = core.SESSIONS.get(sid) if sid else None
        self.empty = None
        if not s or not s.events:
            self.empty = self.add(EmptyState(self._user_name(), self._pick_suggestion))
        self._list_sig = None
        self.refresh_sessions()
        self._sync_controls()

    def _pick_suggestion(self, text):
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
        s = core.SESSIONS.get(self.sid) if self.sid else None
        if not s:
            return
        if self.ev_i > len(s.events):          # la conversacion se recorto (regenerar): reconstruir
            return self.open_session(self.sid)
        with s.cond:
            new = s.events[self.ev_i:self.ev_i + 400]
        for ev in new:
            try:
                self.handle(ev)
            except Exception as e:
                print("evento", ev.get("t"), e, file=sys.stderr)
        self.ev_i += len(new)
        busy = s.run is not None
        if busy != self.busy:
            self.busy = busy
            if not busy:
                self._stale()
            self._sync_controls()
            self._list_sig = None
            self.refresh_sessions()

    def handle(self, ev):
        t = ev["t"]
        if t == "user":
            if self.empty is not None:
                self.empty.hide()
                self.empty.deleteLater()
                self.empty = None
            self.steps = None
            self.cur = None
            self.add(user_bubble(ev))
        elif t == "turn_start":
            self.cur = self.add(AssistantBlock(ev["ts"]))
            if ev["ts"] < time.time() - 5:
                self.cur.status.hide()     # reconstruyendo una conversacion guardada: sin indicador de espera
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
                self.cur.stats.setText(s)
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
        elif t == "tool_call":
            row = StepRow(ev, self.decide)
            self.rows[ev["id"]] = row
            if self.steps is None or self._last_visible() is not self.steps:
                self.steps = self.add(StepsBox())
            self.steps.add(row)
            row.box = self.steps
            if row.pending:
                self.waiting += 1
                self._sync_controls()
                if not self.isActiveWindow() and ev["ts"] > time.time() - 10:
                    self.tray.showMessage(APP_NAME, "El agente espera tu aprobación: %s" % describe(ev["name"], ev.get("args"), "pending"),
                                          QSystemTrayIcon.Information, 6000)
        elif t == "approval":
            r = self.rows.get(ev["id"])
            if r:
                if r.pending:
                    self.waiting = max(0, self.waiting - 1)
                r.resolved(ev["decision"])
                r.box.refresh()
                self._sync_controls()
        elif t == "tool_result":
            r = self.rows.get(ev["id"])
            if r:
                r.result(ev["ok"], ev.get("text") or "", ev.get("image"))
        elif t in ("info", "error"):
            if t == "info" and ev["text"] == "Detenido.":
                self.add(note("Detenido por ti."))
            else:
                self.add(note(ev["text"], t == "error"))
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
            if self.blocks:
                self.blocks[-1].b_regen.show()      # solo la ultima respuesta se puede regenerar

    def _stale(self):
        for r in self.rows.values():
            if r.pending:
                r.resolved("cancel")
                r.box.refresh()
        self.waiting = 0
        self._sync_controls()

    def decide(self, cid, decision):
        s = core.SESSIONS.get(self.sid)
        if s and s.run:
            s.run.resolve(cid, decision)

    def regenerate(self):
        s = core.SESSIONS.get(self.sid) if self.sid else None
        if s:
            err = s.regenerate()
            if err:
                QMessageBox.information(self, APP_NAME, err)
            self.open_session(self.sid)

    # ---- envio
    def send(self):
        text = self.input.toPlainText().strip()
        if self.busy or (not text and not self.pending_imgs):
            return
        if not core.SET.ready():
            return self.setup()
        if not self.sid:
            s = core.new_session()
            self.open_session(s.id)
        s = core.SESSIONS[self.sid]
        err = s.send(text, list(self.pending_imgs))
        if err:
            return QMessageBox.information(self, APP_NAME, err)
        self.input.clear()
        self.pending_imgs = []
        self._render_thumbs()
        self.busy = True
        self.stick = True
        self._list_sig = None
        self.refresh_sessions()
        self._sync_controls()

    def stop(self):
        s = core.SESSIONS.get(self.sid) if self.sid else None
        if s and s.run:
            s.run.request_stop()

    def _add_image_file(self, src=None, qimage=None):
        name = uuid.uuid4().hex[:12] + ".png"
        dst = os.path.join(paths.IMG_DIR, name)
        if qimage is not None:
            qimage.save(dst, "PNG")
        else:
            ext = os.path.splitext(src)[1].lower()
            if ext in (".jpg", ".jpeg", ".webp", ".gif"):
                name = name[:-4] + ext
                dst = os.path.join(paths.IMG_DIR, name)
            shutil.copyfile(src, dst)
        self.pending_imgs.append(name)
        self._render_thumbs()

    def attach(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Adjuntar imágenes", os.path.expanduser("~"), "Imágenes (*.png *.jpg *.jpeg *.webp *.gif)")
        for f in files:
            self._add_image_file(src=f)

    def attach_screenshot(self):
        self.hide()
        QTimer.singleShot(350, self._grab_screen)

    def _grab_screen(self):
        try:
            png = T.capture(1600)[0]
            img = QImage.fromData(png)
            self._add_image_file(qimage=img)
        finally:
            self._show()

    def _paste_img(self, img):
        self._add_image_file(qimage=img)

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
            x = tbtn("ui_cerrar", "Quitar", lambda _=False, n=n: (self.pending_imgs.remove(n), self._render_thumbs()), size=12)
            h.addWidget(x, 0, Qt.AlignTop)
            self.thumbs.insertWidget(self.thumbs.count() - 1, w)
        self._sync_send()

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
            a = m.addAction(md["name"])
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
        self._sync_controls()
        if QMessageBox.question(self, APP_NAME, "¿Encender el nuevo modelo ahora?") == QMessageBox.StandardButton.Yes:
            self.toggle_llm()

    def poll(self):
        self.refresh_sessions()
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
        self._sync_controls()

    def _user_name(self):
        return core.SET.snapshot().get("user_name", "").strip()

    def _sync_send(self):
        has = bool(self.input.toPlainText().strip() or self.pending_imgs)
        self.send_btn.setEnabled(self.busy or has)
        self.send_btn.setIcon(icon("trans_detener" if self.busy else "lista_subir", C["on_send"] if (self.busy or has) else C["faint"], 14 if self.busy else 16))
        self.send_btn.setToolTip("Detener" if self.busy else "Enviar (Enter)")

    def _sync_controls(self):
        cfg = core.SET.snapshot()
        st = self.llm.get("state", "off")
        ext = cfg["llm_mode"] == "external"
        m = core.active_model(cfg)
        name = ("Externo · " + (cfg["external_model"] or cfg["external_url"])) if ext else (m["name"] if m else "Sin modelo")
        self.model_btn.setText(name + "  ⌄")
        col, txt = {"ready": (C["ok"], "Listo" + (" · externo" if ext else " · local")), "loading": (C["warn"], "Cargando…")}.get(st, (C["faint"], "Apagado"))
        self.status_lbl.setText("<span style='color:%s'>●</span> <span style='color:%s'>%s</span>" % (col, C["mut"], txt))
        ready = st == "ready"
        self.banner.setVisible(not ready)
        if not core.SET.ready():
            self.ban_txt.setText("Aún no hay un modelo configurado.")
            self.ban_btn.setText("Configurar")
            self.ban_btn.show()
        elif st == "loading":
            self.ban_txt.setText("Cargando el modelo en memoria. En equipos sin GPU puede tardar unos minutos.")
            self.ban_btn.hide()
        else:
            self.ban_txt.setText("El servidor externo no responde." if ext else (self.llm.get("error") or "El modelo está apagado."))
            self.ban_btn.setText("Encender modelo")
            self.ban_btn.setVisible(not ext)
        self.mode_chip.setText(MODE_LABEL.get(cfg["mode"], cfg["mode"]))
        self.mode_chip.setToolTip(A.MODES.get(cfg["mode"], ""))
        if cfg["mode"] in self.mode_actions:
            self.mode_actions[cfg["mode"]].setChecked(True)
        self.think_chip.blockSignals(True)
        self.think_chip.setChecked(cfg["thinking"])
        self.think_chip.blockSignals(False)
        self.b_folder.setToolTip("Carpeta de trabajo: %s" % cfg["workspace"])
        s = core.SESSIONS.get(self.sid) if self.sid else None
        self.title.setText(s.title if s and s.events else "")
        un = cfg.get("user_name", "").strip() or os.environ.get("USERNAME", "Tú")
        self.user_lbl.setText(un)
        self.avatar.setText("".join(p[0] for p in un.split()[:2]).upper() or "?")
        if self.waiting:
            self.setWindowTitle("● Esperando tu aprobación · " + APP_NAME)
        else:
            self.setWindowTitle(APP_NAME)
        self._sync_send()

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
        self._sync_controls()
        QTimer.singleShot(800, self.poll)

    def setup(self, start="welcome"):
        w = SetupWizard(self, start=start)
        if w.exec() and w.start_llm:
            core.LLM_MGR.stop()
            core.LLM_MGR.start()
        self.poll()
        self._sync_controls()

    def models(self):
        ModelsDialog(self).exec()
        self.poll()
        self._sync_controls()

    def settings(self):
        before = core.SET.snapshot()["theme"]
        SettingsDialog(self).exec()
        if core.SET.snapshot()["theme"] != before:
            return self._swap_window()
        self.poll()
        self._sync_controls()
        if self.empty is not None:
            self.open_session(self.sid)

    def _swap_window(self):
        """Aplica un tema nuevo recreando la ventana (los iconos se tiñen al crearse)."""
        theme.apply(QApplication.instance(), core.SET.snapshot()["theme"])
        w = Main(self.sid)
        w.setGeometry(self.geometry())
        if self.isMaximized():
            w.showMaximized()
        else:
            w.show()
        _dark_titlebar(w)
        QApplication.instance()._main = w
        self._swapping = True
        self.tray.hide()
        self.close()

    def closeEvent(self, e):
        if self._swapping:
            self.pump_t.stop()
            self.poll_t.stop()
            return e.accept()
        busy = [s for s in core.SESSIONS.values() if s.run]
        if busy and QMessageBox.question(self, "Salir", "El agente está trabajando. ¿Detenerlo y salir?") != QMessageBox.StandardButton.Yes:
            return e.ignore()
        core.shutdown()
        self.tray.hide()
        e.accept()
        QApplication.quit()


def _dark_titlebar(w):
    try:
        hwnd = int(w.winId())
        v = ctypes.c_int(1 if theme.MODE == "dark" else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:
        pass


def main():
    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AgenteLocal.App")   # icono propio en la barra de tareas
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    theme.apply(app, core.SET.snapshot()["theme"])
    app.setWindowIcon(make_icon())
    app.setQuitOnLastWindowClosed(False)
    core.load_sessions()
    w = Main()
    app._main = w
    _dark_titlebar(w)
    w.show()
    if not core.SET.ready() and "--no-wizard" not in sys.argv:
        QTimer.singleShot(300, w.setup)
    elif "--start-llm" in sys.argv:
        core.LLM_MGR.start()
    sys.exit(app.exec())
