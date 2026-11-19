"""Aplicacion de escritorio (Qt). Usa el mismo nucleo que la interfaz web."""
import os, sys, json, uuid, shutil, threading, ctypes
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QSize, QUrl, QEvent
from PySide6.QtGui import QPixmap, QImage, QKeySequence, QShortcut, QDesktopServices, QAction, QFont, QGuiApplication
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
                               QListWidgetItem, QComboBox, QCheckBox, QScrollArea, QFrame, QPlainTextEdit, QFileDialog, QMessageBox,
                               QMenu, QSystemTrayIcon, QSizePolicy, QToolButton, QInputDialog, QDialog)
from . import APP_NAME, __version__, core, paths, agent as A, tools as T
from .theme import QSS, C, restyle, make_icon, icon, pix, apply as apply_theme
from .wizard import SetupWizard, ModelsDialog, SettingsDialog, run_bg, btn, lbl, set_icon

CAT_ICON = {"read": "acc_examinar", "write": "acc_renombrar", "exec": "cod_terminal", "net": "herr_espacio_mundo", "control": "inp_raton"}


def pix_label(name, color=None, size=16):
    l = QLabel()
    l.setPixmap(pix(name, color, size))
    l.setFixedSize(size + 2, size + 2)
    return l


def note(text, error=False):
    f = QFrame()
    f.setObjectName("errBox" if error else "noteBox")
    h = QHBoxLayout(f)
    h.setContentsMargins(12, 8, 12, 8)
    h.addWidget(pix_label("est_error" if error else "est_info", C["bad"] if error else C["mut"]), 0, Qt.AlignTop)
    t = lbl(text)
    t.setStyleSheet("color:%s" % ("#ffb3b3" if error else C["mut"]))
    h.addWidget(t, 1)
    return f


# ---------------------------------------------------------------- piezas del chat
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


class Collapsible(QWidget):
    def __init__(self, title, content, opened=False):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        self.b = QToolButton()
        self.b.setText(title)
        self.b.setCheckable(True)
        self.b.setChecked(opened)
        self.b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.b.setArrowType(Qt.DownArrow if opened else Qt.RightArrow)
        self.c = content
        content.setVisible(opened)
        self.b.toggled.connect(self._t)
        v.addWidget(self.b)
        v.addWidget(content)

    def _t(self, on):
        self.c.setVisible(on)
        self.b.setArrowType(Qt.DownArrow if on else Qt.RightArrow)


def md_label(text=""):
    l = QLabel()
    l.setTextFormat(Qt.MarkdownText)
    l.setWordWrap(True)
    l.setOpenExternalLinks(True)
    l.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
    l.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    l.setText(text)
    return l


class ImageLabel(QLabel):
    def __init__(self, path, max_w=640, max_h=420):
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


class AssistantBlock(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        self.r_text = QPlainTextEdit()
        self.r_text.setObjectName("mono")
        self.r_text.setReadOnly(True)
        self.r_text.setFixedHeight(150)
        self.reason = Collapsible("Razonamiento", self.r_text)
        self.reason.hide()
        self.body = md_label()
        self.body.hide()
        self.stats = lbl("", "stats")
        self.stats.hide()
        v.addWidget(self.reason)
        v.addWidget(self.body)
        v.addWidget(self.stats)
        self.text = ""

    def add_reason(self, t):
        self.reason.show()
        self.r_text.moveCursor(self.r_text.textCursor().MoveOperation.End)
        self.r_text.insertPlainText(t)
        self.r_text.ensureCursorVisible()

    def add_text(self, t):
        self.text += t
        self.body.show()
        self.body.setText(self.text)

    def finish(self, text):
        if text:
            self.text = text
            self.body.setText(text)
            self.body.show()
        else:
            self.body.hide()

    def empty(self):
        return self.body.isHidden() and self.reason.isHidden()


class ToolCard(QFrame):
    def __init__(self, ev, on_decide, categories):
        super().__init__()
        self.setObjectName("card")
        self.id = ev["id"]
        self.pending = ev["approval"] == "pending"
        if self.pending:
            self.setProperty("state", "pending")
        elif ev.get("danger"):
            self.setProperty("state", "danger")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head = QWidget()
        head.setObjectName("cardHead")
        h = QHBoxLayout(head)
        h.setContentsMargins(12, 6, 12, 6)
        h.addWidget(pix_label(CAT_ICON.get(ev["category"], "acc_ajustes"), C["acc"]))
        nm = QLabel(ev["name"])
        nm.setFont(QFont("Consolas", 10, QFont.Bold))
        h.addWidget(nm)
        b = QLabel(categories.get(ev["category"], ev["category"]))
        b.setObjectName("badge")
        h.addWidget(b)
        if ev.get("danger"):
            h.addWidget(pix_label("est_aviso", C["bad"], 14))
            d = QLabel("acción delicada")
            d.setObjectName("badgeWarn")
            h.addWidget(d)
        h.addStretch(1)
        self.status = QLabel()
        self.status.setObjectName("status")
        h.addWidget(self.status)
        v.addWidget(head)
        self.body = QWidget()
        self.bl = QVBoxLayout(self.body)
        self.bl.setContentsMargins(12, 8, 12, 10)
        self.bl.setSpacing(6)
        self._args(ev["name"], ev.get("args") or {})
        v.addWidget(self.body)
        self.actions = None
        if self.pending:
            self.set_status("esperando tu aprobación", "run")
            self.actions = QWidget()
            a = QHBoxLayout(self.actions)
            a.setContentsMargins(12, 0, 12, 10)
            cat = categories.get(ev["category"], ev["category"])
            for text, kind, dec, ico in (("Permitir", "ok", "allow", "ui_check"), ("Permitir siempre «%s» aquí" % cat, None, "allow_category", "est_bloqueado"),
                                         ("Denegar", "danger", "deny", "ui_cerrar")):
                bt = btn(text, kind, ico=ico)
                bt.clicked.connect(lambda _=False, d=dec: self._decide(d, on_decide))
                a.addWidget(bt)
            a.addStretch(1)
            v.addWidget(self.actions)
        elif ev["approval"] == "blocked":
            self.set_status("bloqueada (solo lectura)", "bad")
        else:
            self.set_status("ejecutando…", "run")

    def _args(self, name, a):
        kv = lambda k, val: lbl("<span style='color:%s'>%s:</span> %s" % (C["mut"], k, str(val).replace("<", "&lt;")), wrap=True)
        if name == "run_command":
            self.bl.addWidget(mono(a.get("command", "")))
            if a.get("cwd"):
                self.bl.addWidget(kv("carpeta", a["cwd"]))
        elif name == "write_file":
            c = str(a.get("content", ""))
            self.bl.addWidget(kv("archivo", a.get("path", "")))
            self.bl.addWidget(Collapsible("Contenido (%d caracteres)" % len(c), mono(c[:20000], "add")))
        elif name == "edit_file":
            self.bl.addWidget(kv("archivo", a.get("path", "")))
            self.bl.addWidget(mono(str(a.get("old", "")), "del", 160))
            self.bl.addWidget(mono(str(a.get("new", "")), "add", 160))
        else:
            for k, val in a.items():
                self.bl.addWidget(kv(k, val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)) if k != "_raw" else mono(str(val)))

    def _decide(self, d, cb):
        for b in self.actions.findChildren(QPushButton):
            b.setEnabled(False)
        cb(self.id, d)

    def set_status(self, text, kind):
        self.status.setText(text)
        self.status.setProperty("kind", kind)
        restyle(self.status)

    def resolved(self, decision):
        self.pending = False
        self.setProperty("state", "")
        restyle(self)
        if self.actions:
            self.actions.hide()
        if decision in ("allow", "allow_category"):
            self.set_status("aprobada · ejecutando…", "run")
        else:
            self.set_status("cancelada" if decision == "cancel" else "denegada", "bad")

    def result(self, ok, text, image):
        self.set_status("hecho" if ok else "error", "ok" if ok else "bad")
        if text:
            if len(text) > 400 or text.count("\n") > 8:
                self.bl.addWidget(Collapsible("Resultado (%d caracteres)" % len(text), mono(text, max_h=320), opened=not ok))
            else:
                self.bl.addWidget(mono(text))
        if image:
            self.bl.addWidget(ImageLabel(os.path.join(paths.IMG_DIR, image)))


# ---------------------------------------------------------------- composer
class Composer(QPlainTextEdit):
    submit = Signal()
    pasted_image = Signal(QImage)

    def __init__(self):
        super().__init__()
        self.setPlaceholderText("Pídeme algo…  (Enter envía · Shift+Enter nueva línea · Ctrl+V pega imágenes)")
        self.setFixedHeight(64)

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


class _Sig(QObject):
    status = Signal(object)


# ---------------------------------------------------------------- ventana principal
class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_icon())
        self.resize(1240, 820)
        self.sid = None
        self.ev_i = 0
        self.cur = None
        self.cards = {}
        self.last_asst = None
        self.waiting = 0
        self.busy = False
        self.pending_imgs = []
        self.llm = {"state": "off"}
        self.sig = _Sig()
        self.sig.status.connect(self._got_status)
        self._polling = False
        self._list_sig = None
        self._build()
        self._tray()
        core.load_sessions()
        self.refresh_sessions()
        first = core.sorted_sessions()
        self.open_session(first[0].id if first else None)
        self.pump_t = QTimer(self, interval=60, timeout=self.pump)
        self.pump_t.start()
        self.poll_t = QTimer(self, interval=2500, timeout=self.poll)
        self.poll_t.start()
        self.poll()
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_session)

    # ---- construccion
    def _build(self):
        central = QWidget()
        central.setObjectName("central")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)
        # barra lateral
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(280)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(12, 14, 12, 12)
        sv.setSpacing(8)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(make_icon().pixmap(26, 26))
        brand.addWidget(logo)
        brand.addWidget(lbl(APP_NAME, "h1", False), 1)
        sv.addLayout(brand)
        sv.addWidget(btn("Nueva conversación", "primary", self.new_session, "acc_anadir"))
        self.list = QListWidget()
        self.list.itemClicked.connect(lambda it: self.open_session(it.data(Qt.UserRole)))
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        sv.addWidget(self.list, 1)
        sv.addWidget(lbl("MODELO", "section"))
        self.m_name = lbl("—")
        sv.addWidget(self.m_name)
        r = QHBoxLayout()
        self.lamp = QLabel("●")
        r.addWidget(self.lamp)
        self.m_state = lbl("…")
        r.addWidget(self.m_state, 1)
        sv.addLayout(r)
        r = QHBoxLayout()
        self.b_llm = btn("Encender", cb=self.toggle_llm, ico="hub_lanzar")
        r.addWidget(self.b_llm)
        r.addWidget(btn("Modelos…", cb=self.models, ico="ia_controlador"))
        sv.addLayout(r)
        sv.addWidget(lbl("PERMISOS", "section"))
        self.mode = QComboBox()
        for k, v in A.MODES.items():
            self.mode.addItem(v.split(":")[0], k)
            self.mode.setItemData(self.mode.count() - 1, v, Qt.ToolTipRole)
        self.mode.currentIndexChanged.connect(lambda: (core.SET.update({"mode": self.mode.currentData()}), self._mode_hint()))
        sv.addWidget(self.mode)
        self.mode_hint = lbl("", "muted")
        sv.addWidget(self.mode_hint)
        self.think = QCheckBox("Pensar a fondo (más lento)")
        self.think.toggled.connect(lambda on: core.SET.update({"thinking": on}))
        sv.addWidget(self.think)
        sv.addWidget(btn("Ajustes", cb=self.settings, ico="acc_ajustes"))
        root.addWidget(side)
        # zona principal
        main = QWidget()
        mv = QVBoxLayout(main)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(0)
        head = QWidget()
        head.setObjectName("header")
        hh = QHBoxLayout(head)
        hh.setContentsMargins(18, 10, 18, 10)
        self.title = lbl(APP_NAME, wrap=False)
        self.title.setStyleSheet("font-weight:600")
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        hh.addWidget(self.title, 1)
        self.ws = QPushButton()
        self.ws.setProperty("kind", "flat")
        self.ws.setMaximumWidth(380)
        self.ws.setIcon(icon("act_carpeta_abierta", C["mut"], 16))
        self.ws.setToolTip("Abrir la carpeta de trabajo")
        self.ws.clicked.connect(lambda: os.startfile(core.SET.snapshot()["workspace"]))
        hh.addWidget(self.ws)
        self.chip = QLabel("Inactivo")
        self.chip.setObjectName("chip")
        hh.addWidget(self.chip)
        mv.addWidget(head)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        holder = QWidget()
        holder.setObjectName("chatHolder")
        self.scroll.viewport().setObjectName("chatHolder")
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(18, 18, 18, 18)
        self.col = QWidget()
        self.col.setMaximumWidth(920)
        self.cl = QVBoxLayout(self.col)
        self.cl.setContentsMargins(0, 0, 0, 0)
        self.cl.setSpacing(12)
        self.cl.addStretch(1)
        hl.addStretch(0)
        hl.addWidget(self.col, 1)
        hl.addStretch(0)
        self.scroll.setWidget(holder)
        self.stick = True
        sb = self.scroll.verticalScrollBar()
        sb.rangeChanged.connect(lambda lo, hi: self.stick and sb.setValue(hi))
        sb.valueChanged.connect(lambda v: setattr(self, "stick", v >= sb.maximum() - 60))
        mv.addWidget(self.scroll, 1)
        comp = QWidget()
        comp.setObjectName("composer")
        cv = QVBoxLayout(comp)
        cv.setContentsMargins(18, 10, 18, 10)
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(12, 6, 12, 6)
        self.ban_txt = QLabel()
        bl.addWidget(self.ban_txt, 1)
        bl.insertWidget(0, pix_label("est_aviso", C["warn"]))
        self.ban_btn = btn("Encender modelo", "primary", self.toggle_llm, "hub_lanzar")
        bl.addWidget(self.ban_btn)
        cv.addWidget(self.banner)
        self.thumbs = QHBoxLayout()
        self.thumbs.addStretch(1)
        cv.addLayout(self.thumbs)
        row = QHBoxLayout()
        b_att = btn("", cb=self.attach, ico="uij_imagen")
        b_att.setToolTip("Adjuntar imagen (también puedes pegarla con Ctrl+V)")
        b_att.setFixedSize(42, 40)
        row.addWidget(b_att)
        self.input = Composer()
        self.input.submit.connect(self.send)
        self.input.pasted_image.connect(self._paste_img)
        row.addWidget(self.input, 1)
        self.b_send = btn("Enviar", "primary", self.send, "lista_subir")
        self.b_stop = btn("Detener", "danger", self.stop, "trans_detener")
        self.b_stop.hide()
        row.addWidget(self.b_send)
        row.addWidget(self.b_stop)
        cv.addLayout(row)
        cv.addWidget(lbl("Para abortar el control del ratón al instante, lleva el cursor a la esquina superior izquierda de la pantalla.", "muted"))
        mv.addWidget(comp)
        root.addWidget(main, 1)
        self._sync_controls()

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

    # ---- conversaciones
    def refresh_sessions(self):
        ss = core.sorted_sessions()
        sig = [(s.id, s.title, s.run is not None) for s in ss]
        if sig == self._list_sig:
            return
        self._list_sig = sig
        self.list.blockSignals(True)
        self.list.clear()
        for s in ss:
            it = QListWidgetItem(icon("est_cargando", C["warn"], 16) if s.run else icon("mat_comentario", C["mut"], 16), s.title)
            it.setData(Qt.UserRole, s.id)
            it.setToolTip(s.title)
            self.list.addItem(it)
            if s.id == self.sid:
                it.setSelected(True)
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)

    def _list_menu(self, pos):
        it = self.list.itemAt(pos)
        if not it:
            return
        s = core.SESSIONS.get(it.data(Qt.UserRole))
        m = QMenu(self)
        a_ren = m.addAction("Renombrar…")
        a_del = m.addAction("Borrar conversación")
        a = m.exec(self.list.mapToGlobal(pos))
        if a == a_ren:
            t, ok = QInputDialog.getText(self, "Renombrar", "Nuevo nombre:", text=s.title)
            if ok and t.strip():
                s.title = t.strip()[:80]
                s.save()
        elif a == a_del:
            if QMessageBox.question(self, "Borrar", "¿Borrar «%s»? No se puede deshacer." % s.title) == QMessageBox.StandardButton.Yes:
                s.delete()
                if self.sid == s.id:
                    first = core.sorted_sessions()
                    self.open_session(first[0].id if first else None)
        self._list_sig = None
        self.refresh_sessions()

    def new_session(self):
        s = core.new_session()
        self._list_sig = None
        self.refresh_sessions()
        self.open_session(s.id)
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
        self.cards = {}
        self.last_asst = None
        self.waiting = 0
        self.busy = False
        self.stick = True
        self.clear_chat()
        s = core.SESSIONS.get(sid) if sid else None
        self.title.setText(s.title if s else APP_NAME)
        if not s:
            e = lbl("<h2>¿En qué te ayudo?</h2>Puedo leer y crear archivos, ejecutar comandos y programas, programar, "
                    "usar la web y manejar el ordenador.<br>Cada acción aparece aquí y tú decides qué permitir.", "muted")
            e.setTextFormat(Qt.RichText)
            e.setAlignment(Qt.AlignCenter)
            self.add(e)
        self._list_sig = None
        self.refresh_sessions()
        self._sync_controls()

    # ---- eventos del agente
    def pump(self):
        s = core.SESSIONS.get(self.sid) if self.sid else None
        if not s:
            return
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
            self.cur = None
            box = QFrame()
            box.setObjectName("userBubble")
            v = QVBoxLayout(box)
            v.setContentsMargins(14, 10, 14, 10)
            l = lbl(ev["text"])
            v.addWidget(l)
            for n in ev.get("images") or []:
                v.addWidget(ImageLabel(os.path.join(paths.IMG_DIR, n), 260, 180))
            wrap = QWidget()
            h = QHBoxLayout(wrap)
            h.setContentsMargins(80, 0, 0, 0)
            h.addWidget(box)
            self.add(wrap)
        elif t == "turn_start":
            self.cur = None
        elif t == "delta":
            if self.cur is None:
                self.cur = self.add(AssistantBlock())
            (self.cur.add_reason if ev["kind"] == "reasoning" else self.cur.add_text)(ev["text"])
        elif t == "assistant_end":
            if self.cur is None and ev["text"]:
                self.cur = self.add(AssistantBlock())
            if self.cur is not None:
                self.cur.finish(ev["text"])
                if self.cur.empty():
                    self.cur.hide()
                    self.cur.deleteLater()
                else:
                    self.last_asst = self.cur
                self.cur = None
        elif t == "stats":
            if self.last_asst is not None and ev.get("gen_n"):
                s = ("entrada %s tok · " % ev["prompt_n"] if ev.get("prompt_n") is not None else "") + "salida %s tok" % ev["gen_n"]
                if ev.get("tps"):
                    s += " · %.1f tok/s" % ev["tps"]
                if ev.get("finish") == "length":
                    s += " · cortado por límite"
                self.last_asst.stats.setText(s)
                self.last_asst.stats.show()
        elif t == "tool_call":
            c = ToolCard(ev, self.decide, T.CATEGORIES)
            self.cards[ev["id"]] = c
            self.add(c)
            if c.pending:
                self.waiting += 1
                self._sync_controls()
                if not self.isActiveWindow() and self.ev_i > 0:
                    self.tray.showMessage(APP_NAME, "El agente espera tu aprobación: %s" % ev["name"], QSystemTrayIcon.Information, 6000)
        elif t == "approval":
            c = self.cards.get(ev["id"])
            if c:
                if c.pending:
                    self.waiting = max(0, self.waiting - 1)
                c.resolved(ev["decision"])
                self._sync_controls()
        elif t == "tool_result":
            c = self.cards.get(ev["id"])
            if c:
                c.result(ev["ok"], ev.get("text") or "", ev.get("image"))
        elif t in ("info", "error"):
            self.add(note(ev["text"], t == "error"))
        elif t == "turn_end":
            self.cur = None
            self._stale()

    def _stale(self):
        for c in self.cards.values():
            if c.pending:
                c.resolved("cancel")
                c.set_status("interrumpida", "bad")
        self.waiting = 0
        self._sync_controls()

    def decide(self, cid, decision):
        s = core.SESSIONS.get(self.sid)
        if s and s.run:
            s.run.resolve(cid, decision)

    # ---- envio
    def send(self):
        text = self.input.toPlainText().strip()
        if self.busy or (not text and not self.pending_imgs):
            return
        if not self.sid:
            self.new_session()
        s = core.SESSIONS[self.sid]
        imgs = list(self.pending_imgs)
        err = s.send(text, imgs)
        if err:
            return QMessageBox.information(self, APP_NAME, err)
        self.input.clear()
        self.pending_imgs = []
        self._render_thumbs()
        self.busy = True
        self.stick = True
        self._sync_controls()

    def stop(self):
        s = core.SESSIONS.get(self.sid) if self.sid else None
        if s and s.run:
            s.run.request_stop()

    def attach(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Adjuntar imágenes", os.path.expanduser("~"), "Imágenes (*.png *.jpg *.jpeg *.webp *.gif)")
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            name = uuid.uuid4().hex[:12] + (ext if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif") else ".png")
            shutil.copyfile(f, os.path.join(paths.IMG_DIR, name))
            self.pending_imgs.append(name)
        self._render_thumbs()

    def _paste_img(self, img):
        name = uuid.uuid4().hex[:12] + ".png"
        img.save(os.path.join(paths.IMG_DIR, name), "PNG")
        self.pending_imgs.append(name)
        self._render_thumbs()

    def _render_thumbs(self):
        while self.thumbs.count() > 1:
            it = self.thumbs.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for n in self.pending_imgs:
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            im = QLabel()
            im.setPixmap(QPixmap(os.path.join(paths.IMG_DIR, n)).scaled(80, 54, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            h.addWidget(im)
            x = QPushButton("✕")
            x.setProperty("kind", "flat")
            x.clicked.connect(lambda _=False, n=n: (self.pending_imgs.remove(n), self._render_thumbs()))
            h.addWidget(x)
            self.thumbs.insertWidget(self.thumbs.count() - 1, w)

    # ---- estado del modelo y controles
    def poll(self):
        self.refresh_sessions()
        s = core.SESSIONS.get(self.sid) if self.sid else None
        if s and self.title.text() != s.title:
            self.title.setText(s.title)
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

    def _sync_controls(self):
        cfg = core.SET.snapshot()
        st = self.llm.get("state", "off")
        ext = cfg["llm_mode"] == "external"
        m = core.active_model(cfg)
        self.m_name.setText(("Externo: %s" % (cfg["external_model"] or cfg["external_url"])) if ext else (m["name"] if m else "Ningún modelo configurado"))
        self.lamp.setStyleSheet("color:%s" % {"ready": C["ok"], "loading": C["warn"]}.get(st, C["bad"]))
        self.m_state.setText({"ready": "Encendido" + (" (externo)" if self.llm.get("external") and not ext else ""),
                              "loading": "Cargando… puede tardar unos minutos"}.get(st, self.llm.get("error") or "Apagado"))
        self.b_llm.setText("Apagar" if st != "off" else "Encender")
        set_icon(self.b_llm, "trans_detener" if st != "off" else "hub_lanzar")
        self.b_llm.setEnabled(not ext and not (st == "ready" and self.llm.get("external")))
        ready = st == "ready"
        self.banner.setVisible(not ready)
        if not core.SET.ready():
            self.ban_txt.setText("Aún no hay un modelo configurado.")
            self.ban_btn.setText("Configurar")
            self.ban_btn.show()
        elif st == "loading":
            self.ban_txt.setText("El modelo se está cargando en memoria…")
            self.ban_btn.hide()
        else:
            self.ban_txt.setText("El servidor externo no responde." if ext else "El modelo está apagado. Enciéndelo para poder chatear.")
            self.ban_btn.setText("Encender modelo")
            self.ban_btn.setVisible(not ext)
        if self.mode.currentData() != cfg["mode"]:
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(max(0, self.mode.findData(cfg["mode"])))
            self.mode.blockSignals(False)
        self._mode_hint()
        self.think.blockSignals(True)
        self.think.setChecked(cfg["thinking"])
        self.think.blockSignals(False)
        ws = cfg["workspace"]
        self.ws.setText(ws if len(ws) <= 48 else "…" + ws[-46:])
        self.ws.setToolTip("Carpeta de trabajo: %s (clic para abrir)" % ws)
        self.b_send.setVisible(not self.busy)
        self.b_stop.setVisible(self.busy)
        kind, text = ("wait", "Esperando tu aprobación") if self.waiting else (("busy", "Trabajando…") if self.busy else ("", "Inactivo"))
        self.chip.setText(text)
        self.chip.setProperty("kind", kind)
        restyle(self.chip)

    def _mode_hint(self):
        self.mode_hint.setText(A.MODES.get(self.mode.currentData(), ""))

    def toggle_llm(self):
        if not core.SET.ready():
            return self.setup()
        if self.llm.get("state", "off") == "off":
            err = core.LLM_MGR.start()
            if err:
                QMessageBox.warning(self, APP_NAME, err)
        else:
            core.LLM_MGR.stop()
        self.llm = {"state": "loading"} if self.llm.get("state") == "off" else {"state": "off"}
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
        d = ModelsDialog(self)
        d.exec()
        self.poll()
        self._sync_controls()

    def settings(self):
        d = SettingsDialog(self)
        d.exec()
        self.poll()
        self._sync_controls()

    def closeEvent(self, e):
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
        v = ctypes.c_int(1)
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
    apply_theme(app)
    app.setWindowIcon(make_icon())
    app.setQuitOnLastWindowClosed(False)
    w = Main()
    _dark_titlebar(w)
    w.show()
    if not core.SET.ready() and "--no-wizard" not in sys.argv:
        QTimer.singleShot(300, w.setup)
    elif "--start-llm" in sys.argv:
        core.LLM_MGR.start()
    sys.exit(app.exec())
