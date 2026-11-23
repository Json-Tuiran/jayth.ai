# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Lienzo: panel junto a la conversación donde el agente muestra lo que crea (páginas web, documentos, dibujos, código).

- Vista previa en vivo y vista del código, con historial de versiones (cada corrección del agente es una versión) y los
  cambios entre una versión y la anterior.
- El usuario puede editarlo (con vista previa mientras escribe) y guardar su versión; el agente se entera en el siguiente
  mensaje. «Pedir un cambio» lleva al chat lo que tenga seleccionado.
- Las páginas web se muestran con el navegador integrado (Qt WebEngine) si está disponible; si no, se abren en el
  navegador del sistema con un clic.
"""
import os, re, glob, time, shutil, difflib, threading
from PySide6.QtCore import Qt, QUrl, Signal, QObject, QTimer, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QGuiApplication, QFont, QTransform, QShortcut, QKeySequence
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget, QPlainTextEdit, QScrollArea, QFileDialog,
                               QFrame, QPushButton, QToolButton, QMenu, QSplitter, QTextBrowser)
from . import osys
from .theme import C, icon
from .widgets import TextView, ElidedLabel
from .i18n import tr

KIND_LABEL = {"html": tr("Página web"), "markdown": tr("Documento"), "svg": tr("Dibujo"), "code": tr("Código"), "file": tr("Archivo")}


def can_show(path):
    """¿El lienzo sabe mostrar este archivo del disco? (documentos, imágenes, tablas y cualquier texto)"""
    from .codeview import TEXT_EXT, IMG_EXT
    from .docview import DOCS
    return os.path.isfile(path) and os.path.splitext(path)[1].lower() in (DOCS | IMG_EXT | TEXT_EXT)


def file_item(path):
    from .tools import canvas_file_item
    return canvas_file_item(path)
_WEB = [None]          # None = sin probar, False = no disponible, o la clase QWebEngineView


def web_view_class():
    if _WEB[0] is None:
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            _WEB[0] = QWebEngineView
        except Exception:
            _WEB[0] = False
    return _WEB[0]


def versions_of(item):
    """Rutas de todas las versiones de un contenido del lienzo, en orden."""
    d, slug = os.path.dirname(item["path"]), item.get("slug") or ""
    ext = os.path.splitext(item["path"])[1]
    found = []
    for p in glob.glob(os.path.join(glob.escape(d), glob.escape(slug) + "_v*" + ext)):
        m = re.search(r"_v(\d+)%s$" % re.escape(ext), p)
        if m:
            found.append((int(m.group(1)), p))
    return [p for _, p in sorted(found)] or [item["path"]]


def _tb(ico, tip, cb, size=15):
    from PySide6.QtWidgets import QToolButton
    from PySide6.QtCore import QSize
    b = QToolButton()
    b.setIcon(icon(ico, C["mut"], size))
    b.setIconSize(QSize(size, size))
    b.setToolTip(tip)
    b.setAccessibleName(tip)
    b.setCursor(Qt.PointingHandCursor)
    b.setAutoRaise(True)
    b.clicked.connect(lambda *_: cb())
    return b


# ---- vista web: tamaños de dispositivo, zoom y consola
DEVICES = {"auto": (tr("Adaptable"), 0, 0), "phone": (tr("Móvil"), 390, 844), "tablet": (tr("Tableta"), 820, 1180),
           "desktop": (tr("Escritorio"), 1280, 800)}
ZOOMS = (0.5, 0.67, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0)
_CPAGE = [None]

# ---- exportar: formato → (nombre, extensión); qué formatos tiene sentido ofrecer según el tipo de contenido
EXPORTS = {"pdf": (tr("PDF"), ".pdf"), "png": (tr("Imagen PNG"), ".png"), "docx": (tr("Word (DOCX)"), ".docx"),
           "html": (tr("Página HTML"), ".html")}
EXPORT_KINDS = {"markdown": ("pdf", "docx", "html", "png"), "html": ("pdf", "png"), "svg": ("png", "pdf", "html"), "code": ("pdf", "html")}


def _page_html(title, inner, style=""):
    import html as _h
    return ('<!doctype html>\n<html><head><meta charset="utf-8"><title>%s</title><style>body{margin:0;%s}</style></head>\n'
            "<body>\n%s\n</body></html>\n" % (_h.escape(title), style, inner))


def console_page_class():
    """Página que avisa de lo que escribe en su consola (errores de JavaScript incluidos)."""
    if _CPAGE[0] is None:
        from PySide6.QtWebEngineCore import QWebEnginePage

        class ConsolePage(QWebEnginePage):
            console = Signal(str, str, int)          # nivel (error, warning, info), mensaje, línea

            def javaScriptConsoleMessage(self, level, msg, line, source):
                L = QWebEnginePage.JavaScriptConsoleMessageLevel
                kind = "error" if level == L.ErrorMessageLevel else "warning" if level == L.WarningMessageLevel else "info"
                self.console.emit(kind, str(msg), int(line or 0))
        _CPAGE[0] = ConsolePage
    return _CPAGE[0]


def console_note(log, limit=5):
    """Resumen de la consola para el modelo (vacío si no hubo errores ni avisos)."""
    errs = [(m, l) for k, m, l in log or [] if k == "error"]
    warns = [(m, l) for k, m, l in log or [] if k == "warning"]
    if not errs and not warns:
        return ""
    show = (errs or warns)[:limit]
    items = "; ".join("«%s%s»" % (("línea %d: " % l) if l else "", (m if len(m) <= 240 else m[:240] + "…")) for m, l in show)
    if errs:
        return " La consola de la página dio %d error%s: %s%s. Corrígelo%s con edit_canvas." % (
            len(errs), "es" if len(errs) > 1 else "", items, (" (y %d aviso%s)" % (len(warns), "s" if len(warns) > 1 else "")) if warns else "",
            "s" if len(errs) > 1 else "")
    return " La consola de la página dio %d aviso%s: %s." % (len(warns), "s" if len(warns) > 1 else "", items)


class WebStage(QWidget):
    """Contiene la vista web y simula el ancho de un móvil, una tableta o un escritorio (encogiéndola si no cabe)."""

    def __init__(self, view):
        super().__init__()
        self.view = view
        view.setParent(self)
        self.device, self.zoom, self.fit = "auto", 1.0, 1.0
        view.loadFinished.connect(lambda *_: self._apply_zoom())

    def set_device(self, d):
        self.device = d if d in DEVICES else "auto"
        self._place()
        self.update()

    def set_zoom(self, z):
        self.zoom = max(ZOOMS[0], min(ZOOMS[-1], z))
        self._apply_zoom()

    def _apply_zoom(self):
        z = max(0.25, min(5.0, self.fit * self.zoom))
        if abs(self.view.zoomFactor() - z) > 1e-3:
            self.view.setZoomFactor(z)

    def _place(self):
        w, h = self.width(), self.height()
        _, W, H = DEVICES[self.device]
        if not W:
            self.fit = 1.0
            self.view.setGeometry(0, 0, w, h)
        else:
            m = 12
            aw, ah = max(60, w - 2 * m), max(60, h - 2 * m)
            self.fit = min(1.0, aw / float(W))
            vw, vh = int(W * self.fit), int(min(H * self.fit, ah))
            self.view.setGeometry((w - vw) // 2, m, vw, vh)
        self._apply_zoom()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()

    def paintEvent(self, e):
        if self.device == "auto":
            return
        from PySide6.QtGui import QPainter, QColor
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C["panel2"]))
        p.setPen(QColor(C["line"]))
        p.drawRect(self.view.geometry().adjusted(-1, -1, 0, 0))
        p.end()


class CanvasBridge(QObject):
    """Puente entre el hilo del agente y el lienzo: muestra un contenido y devuelve una captura de cómo queda, para que el
    modelo pueda comprobar lo que el usuario ve (antes lo mostraba a ciegas)."""
    sig = Signal(object)

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.sig.connect(self._run, Qt.QueuedConnection)

    def capture(self, item, stop=None, timeout=20):
        """Desde cualquier hilo: abre `item` en el lienzo y devuelve {"image": PNG o None, "console": [(nivel, texto, línea)]}."""
        job = {"item": dict(item), "ev": threading.Event(), "res": None, "console": []}
        self.sig.emit(job)
        end = time.time() + timeout
        while not job["ev"].wait(0.2):
            if (stop is not None and stop.is_set()) or time.time() > end:
                return {"image": None, "console": list(job["console"])}
        return {"image": job["res"], "console": list(job["console"])}

    def shot(self, item, stop=None, timeout=20):
        return self.capture(item, stop, timeout)["image"]

    def console_for(self, path):
        """Lo último que escribió en la consola la página de ese archivo del lienzo ([] si no se ha mostrado)."""
        try:
            return list(self.main.canvas.console_by_path.get(os.path.normcase(path)) or [])
        except Exception:
            return []

    def _run(self, job):
        try:
            self.main.open_canvas(job["item"])
            panel = self.main.canvas
        except Exception:
            job["ev"].set()
            return
        done = []

        def grab():
            if done:
                return
            done.append(1)
            try:
                w = panel.stack.currentWidget()
                img = w.grab().toImage()
                if img.width() > 1024:
                    img = img.scaledToWidth(1024, Qt.SmoothTransformation)
                ba = QByteArray()
                buf = QBuffer(ba)
                buf.open(QIODevice.WriteOnly)
                img.save(buf, "PNG")
                buf.close()
                if img.width() > 40 and img.height() > 40:
                    job["res"] = bytes(ba.data())
            except Exception:
                pass
            finally:
                job["console"] = list(getattr(panel, "console_log", []) or [])
                job["ev"].set()
        web = panel.web if job["item"].get("kind") in ("html", "svg") else None
        if web is not None:                          # una página: cuando termine de cargar, y un momento más para que pinte
            def loaded(_ok=True):
                try:
                    web.loadFinished.disconnect(loaded)
                except Exception:
                    pass
                QTimer.singleShot(700, grab)
            web.loadFinished.connect(loaded)
            QTimer.singleShot(6000, grab)            # por si la página nunca dice que terminó
        else:                                        # texto: lo que tarda el panel en abrirse y colocarse
            QTimer.singleShot(1800 if job["item"].get("kind") == "file" else 650, grab)


class CanvasPanel(QWidget):
    closed = Signal()
    user_saved = Signal(object)          # el usuario guardó una versión suya (item nuevo)
    expand_changed = Signal(bool)        # el lienzo ocupa toda la ventana (o vuelve junto al chat)

    PREVIEW, SOURCE, DIFF, EDIT = range(4)

    def __init__(self, main=None):
        super().__init__()
        self.main = main
        self.setObjectName("canvas")
        self.setMinimumWidth(320)
        self.setProperty("foldable", True)
        self.item, self.paths, self.idx, self.web = None, [], 0, None
        self.user_versions = []
        self.editing, self._base, self._drafts, self._hl = False, "", {}, []
        self._md_view = None
        self.stage, self.console_log, self.console_by_path, self.expanded = None, [], {}, False
        self._filetab = None
        from PySide6.QtCore import QFileSystemWatcher
        self._watch = QFileSystemWatcher(self)        # un archivo del disco: se vuelve a mostrar si cambia
        self._watch.fileChanged.connect(lambda p: self._file_timer.start())
        self._file_timer = QTimer(self, singleShot=True, interval=500, timeout=self._file_changed)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head = QWidget()
        head.setObjectName("canvasHead")
        h = QHBoxLayout(head)
        h.setContentsMargins(14, 6, 8, 6)
        h.setSpacing(2)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = ElidedLabel()
        self.title.setStyleSheet("font-weight:600")
        col.addWidget(self.title)
        self.sub = ElidedLabel()
        self.sub.setObjectName("faint")
        col.addWidget(self.sub)
        h.addLayout(col, 1)
        self.b_items = _tb("ui_chevron_abajo", tr("Contenidos del lienzo en esta conversación"), lambda: None, 13)
        self.b_items.setPopupMode(QToolButton.InstantPopup)
        self.items_menu = QMenu(self)
        self.items_menu.aboutToShow.connect(self._fill_items)
        self.b_items.setMenu(self.items_menu)
        h.addWidget(self.b_items)
        self.b_prev = _tb("ui_chevron_derecha", tr("Versión anterior"), lambda: self.go(self.idx - 1), 13)
        self.b_prev.setIcon(icon("ui_chevron_derecha", C["mut"], 13).pixmap(13, 13).transformed(QTransform().rotate(180)))
        self.b_next = _tb("ui_chevron_derecha", tr("Versión siguiente"), lambda: self.go(self.idx + 1), 13)
        self.ver = QLabel()
        self.ver.setObjectName("faint")
        for w in (self.b_prev, self.ver, self.b_next):
            h.addWidget(w)
        self.b_edit = _tb("acc_renombrar", tr("Editar: cambia el contenido tú mismo y guárdalo como una versión nueva"), self.start_edit)
        h.addWidget(self.b_edit)
        self.b_ask = _tb("mat_comentario", tr("Pedir un cambio al agente (sobre lo que tengas seleccionado)"), self.ask_change)
        h.addWidget(self.b_ask)
        self.b_view = QPushButton(tr("Código"))
        self.b_view.setProperty("kind", "flat")
        self.b_view.setCheckable(True)
        self.b_view.setToolTip(tr("Cambiar entre la vista previa y el código"))
        self.b_view.toggled.connect(self._toggle_source)
        h.addWidget(self.b_view)
        self.b_more = _tb("ui_menu_horizontal", tr("Más opciones del lienzo"), lambda: None)
        self.b_more.setPopupMode(QToolButton.InstantPopup)
        self.more_menu = QMenu(self)
        self.more_menu.aboutToShow.connect(self._fill_more)
        self.b_more.setMenu(self.more_menu)
        h.addWidget(self.b_more)
        self.b_expand = _tb("app_pantalla_completa", tr("Ampliar el lienzo a toda la ventana"), self.toggle_expand)
        h.addWidget(self.b_expand)
        h.addWidget(_tb("ui_cerrar", tr("Cerrar el lienzo"), self.close_panel, 13))
        v.addWidget(head)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("hline")
        v.addWidget(line)
        # barra de edición: solo mientras el usuario edita
        self.edit_bar = QWidget()
        eb = QHBoxLayout(self.edit_bar)
        eb.setContentsMargins(14, 5, 8, 5)
        eb.setSpacing(6)
        self.edit_lbl = ElidedLabel()
        self.edit_lbl.setObjectName("muted")
        eb.addWidget(self.edit_lbl, 1)
        self.b_live = QPushButton(tr("Vista previa"))
        self.b_live.setProperty("kind", "flat")
        self.b_live.setCheckable(True)
        self.b_live.setChecked(True)
        self.b_live.setToolTip(tr("Ver cómo queda mientras escribes"))
        self.b_live.toggled.connect(self._toggle_live)
        eb.addWidget(self.b_live)
        b = QPushButton(tr("Descartar"))
        b.setProperty("kind", "flat")
        b.clicked.connect(lambda *_: self.discard_edit())
        eb.addWidget(b)
        self.b_save = QPushButton(tr("Guardar versión"))
        self.b_save.setProperty("kind", "primary")
        self.b_save.setToolTip(tr("Guardar como una versión nueva (Ctrl+S); el agente sabrá que la cambiaste"))
        self.b_save.clicked.connect(lambda *_: self.save_edit())
        eb.addWidget(self.b_save)
        self.edit_bar.hide()
        v.addWidget(self.edit_bar)
        self.edit_line = QFrame()
        self.edit_line.setFrameShape(QFrame.HLine)
        self.edit_line.setObjectName("hline")
        self.edit_line.hide()
        v.addWidget(self.edit_line)
        mono = QFont(osys.mono_font())
        mono.setPointSizeF(10)
        self._web_bar(v)
        self.stack = QStackedWidget()
        v.addWidget(self.stack, 1)
        self._console_box(v, mono)
        # 0: vista previa (se rellena según el tipo)
        self.preview_host = QWidget()
        self.pv = QVBoxLayout(self.preview_host)
        self.pv.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.preview_host)
        # 1: código
        self.source = QPlainTextEdit()
        self.source.setObjectName("mono")
        self.source.setReadOnly(True)
        self.source.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.source.setFont(mono)
        self.stack.addWidget(self.source)
        # 2: cambios respecto a la versión anterior
        dp = QWidget()
        dv = QVBoxLayout(dp)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(0)
        dbar = QHBoxLayout()
        dbar.setContentsMargins(14, 5, 8, 5)
        self.diff_lbl = ElidedLabel()
        self.diff_lbl.setObjectName("muted")
        dbar.addWidget(self.diff_lbl, 1)
        b = QPushButton(tr("Volver"))
        b.setProperty("kind", "flat")
        b.clicked.connect(lambda *_: self._show_page(self.SOURCE if self.b_view.isChecked() or self.item["kind"] == "code" else self.PREVIEW))
        dbar.addWidget(b)
        dv.addLayout(dbar)
        self.diff = QTextBrowser()
        self.diff.setObjectName("mono")
        self.diff.setFont(mono)
        self.diff.setLineWrapMode(QTextBrowser.NoWrap)
        self.diff.setOpenLinks(False)
        dv.addWidget(self.diff, 1)
        self.stack.addWidget(dp)
        # 3: edición (el texto arriba y, si se quiere, cómo queda debajo)
        self.edit_split = QSplitter(Qt.Vertical)
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("mono")
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.editor.setFont(mono)
        self.editor.setTabStopDistance(4 * self.editor.fontMetrics().horizontalAdvance(" "))
        self.editor.textChanged.connect(self._edited)
        self.edit_split.addWidget(self.editor)
        self.live_host = QWidget()
        self.lv = QVBoxLayout(self.live_host)
        self.lv.setContentsMargins(0, 0, 0, 0)
        self.edit_split.addWidget(self.live_host)
        self.edit_split.setChildrenCollapsible(False)
        self.stack.addWidget(self.edit_split)
        self._live_timer = QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(600)
        self._live_timer.timeout.connect(self._render_live)
        QShortcut(QKeySequence.Save, self.editor, activated=self.save_edit)
        esc = QShortcut(QKeySequence(Qt.Key_Escape), self, activated=lambda: self.expanded and self.toggle_expand())
        esc.setContext(Qt.WidgetWithChildrenShortcut)

    def _web_bar(self, v):
        """Barra de la vista web: tamaño de dispositivo, zoom, recargar y consola."""
        self.webbar = QWidget()
        b = QHBoxLayout(self.webbar)
        b.setContentsMargins(10, 3, 8, 3)
        b.setSpacing(2)
        self.b_device = QToolButton()
        self.b_device.setProperty("kind", "flat")
        self.b_device.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.b_device.setLayoutDirection(Qt.RightToLeft)         # la flecha, a la derecha del texto
        self.b_device.setIcon(icon("ui_chevron_abajo", C["mut"], 11))
        self.b_device.setStyleSheet("QToolButton::menu-indicator{image:none;width:0}")
        self.b_device.setCursor(Qt.PointingHandCursor)
        self.b_device.setToolTip(tr("Ver la página con el ancho de un móvil, una tableta o un escritorio"))
        self.b_device.setPopupMode(QToolButton.InstantPopup)
        dm = QMenu(self)
        for key, (label, W, H) in DEVICES.items():
            a = dm.addAction(label + (("  ·  %d × %d" % (W, H)) if W else ""))
            a.triggered.connect(lambda *_, k=key: self.set_device(k))
        self.b_device.setMenu(dm)
        b.addWidget(self.b_device)
        b.addSpacing(6)
        self.b_zoom_out = self._text_btn("−", tr("Alejar"), lambda: self.step_zoom(-1))
        self.b_zoom = QToolButton()
        self.b_zoom.setAutoRaise(True)
        self.b_zoom.setCursor(Qt.PointingHandCursor)
        self.b_zoom.setToolTip(tr("Zoom (clic: volver al 100 %)"))
        self.b_zoom.clicked.connect(lambda *_: self.set_zoom(1.0))
        self.b_zoom_in = self._text_btn("+", tr("Acercar"), lambda: self.step_zoom(1))
        for w in (self.b_zoom_out, self.b_zoom, self.b_zoom_in):
            b.addWidget(w)
        b.addWidget(_tb("acc_refrescar", tr("Recargar la página"), self.reload, 14))
        b.addStretch(1)
        self.b_console = QToolButton()
        self.b_console.setAutoRaise(True)
        self.b_console.setCheckable(True)
        self.b_console.setCursor(Qt.PointingHandCursor)
        self.b_console.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.b_console.setToolTip(tr("Consola de la página: errores y mensajes de su JavaScript"))
        self.b_console.toggled.connect(lambda on: self.console_wrap.setVisible(on))
        b.addWidget(self.b_console)
        self.webbar.hide()
        v.addWidget(self.webbar)
        self.web_line = QFrame()
        self.web_line.setFrameShape(QFrame.HLine)
        self.web_line.setObjectName("hline")
        self.web_line.hide()
        v.addWidget(self.web_line)
        self.device, self.zoom = "auto", 1.0
        self._sync_webbar()

    def _text_btn(self, text, tip, cb):
        b = QToolButton()
        b.setText(text)
        b.setAutoRaise(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(tip)
        b.setAccessibleName(tip)
        b.setFixedWidth(26)
        b.clicked.connect(lambda *_: cb())
        return b

    def _console_box(self, v, mono):
        self.console_wrap = QWidget()
        cv = QVBoxLayout(self.console_wrap)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("hline")
        cv.addWidget(line)
        top = QHBoxLayout()
        top.setContentsMargins(12, 4, 8, 4)
        lbl = QLabel(tr("Consola"))
        lbl.setObjectName("muted")
        top.addWidget(lbl)
        top.addStretch(1)
        self.b_fix = QPushButton(tr("Pedir que lo arregle"))
        self.b_fix.setProperty("kind", "flat")
        self.b_fix.setToolTip(tr("Lleva los errores de la consola al chat"))
        self.b_fix.clicked.connect(lambda *_: self.ask_fix())
        top.addWidget(self.b_fix)
        cv.addLayout(top)
        self.console = QPlainTextEdit()
        self.console.setObjectName("mono")
        self.console.setReadOnly(True)
        self.console.setFont(mono)
        self.console.setMaximumBlockCount(500)
        self.console.setFixedHeight(130)
        cv.addWidget(self.console)
        self.console_wrap.hide()
        v.addWidget(self.console_wrap)

    # ---- carga
    def load(self, item):
        if self.editing:                     # llega otro contenido (o el agente cambió este) mientras el usuario edita
            self._stash_draft()
        self.item = dict(item)
        if self._watch.files():
            self._watch.removePaths(self._watch.files())
        if item.get("kind") == "file":
            self.paths, self.idx, self.user_versions = [item["path"]], 0, []
            self._watch.addPath(item["path"])
            self._render()
            return
        self.paths = versions_of(item)
        want = os.path.normcase(item["path"])
        self.idx = next((i for i, p in enumerate(self.paths) if os.path.normcase(p) == want), len(self.paths) - 1)
        self._read_meta()
        self._render()

    def _read_meta(self):
        try:
            from . import tools as T
            it = next((x for x in T.canvas_items(d=os.path.dirname(self.item["path"])) if x["slug"] == self.item.get("slug")), None)
            self.user_versions = list((it or {}).get("user") or self.item.get("user") or [])
        except Exception:
            self.user_versions = list(self.item.get("user") or [])

    def go(self, i):
        if self.editing:
            return
        if 0 <= i < len(self.paths):
            self.idx = i
            self._render()

    def _vnum(self, i=None):
        p = self.paths[self.idx if i is None else i] if self.paths else ""
        m = re.search(r"_v(\d+)\.\w+$", p)
        return int(m.group(1)) if m else (self.idx + 1)

    def text(self, i=None):
        try:
            with open(self.paths[self.idx if i is None else i], encoding="utf-8", errors="replace", newline="") as f:
                return f.read()
        except (OSError, IndexError):
            return ""

    def _ext(self):
        return os.path.splitext(self.item["path"])[1].lower() if self.item else ""

    def _highlight(self, edit):
        """Colores de sintaxis según la extensión (sin colores en textos enormes, como el editor de código)."""
        from .codeview import Highlighter, HL_MAX_BYTES
        doc = (self.editor if edit else self.source).document()
        self._hl = [h for h in self._hl if h.document() is not doc or h.setDocument(None)]
        if len(doc.toPlainText()) <= HL_MAX_BYTES:
            self._hl.append(Highlighter(doc, self._ext()))

    def _clear(self, lay):
        while lay.count():
            w = lay.takeAt(0).widget()
            if w is self.stage:
                w.setParent(None)
            elif w is self._filetab:
                self._filetab = None
                w.deleteLater()
            elif w is not None:
                w.deleteLater()

    def _ensure_web(self):
        if self.web is None:
            self.web = web_view_class()()
            page = console_page_class()(self.web)
            page.console.connect(self._on_console)
            self.web.setPage(page)
            self.stage = WebStage(self.web)
            self.stage.set_device(self.device)
            self.stage.set_zoom(self.zoom)
        return self.web

    def _render_into(self, lay, kind, text, key=None):
        """Pinta `text` en `lay` como se verá (documento, página o dibujo). `key`: de qué archivo es la consola."""
        self._clear(lay)
        self.console_log = []                   # la consola es de lo que se ve ahora (no de una página anterior)
        self._md_view = None
        if kind == "markdown":
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.NoFrame)
            inner = QWidget()
            iv = QVBoxLayout(inner)
            iv.setContentsMargins(22, 16, 22, 22)
            self._md_view = TextView(text, "md", size="10.5pt")
            iv.addWidget(self._md_view)
            iv.addStretch(1)
            sa.setWidget(inner)
            lay.addWidget(sa)
        elif kind in ("html", "svg") and web_view_class():
            self._ensure_web()
            self.stage.set_device(self.device if kind == "html" else "auto")
            if key:
                self.console_by_path[os.path.normcase(key)] = self.console_log
            self._sync_console()
            page = text if kind == "html" else ("<!doctype html><html><body style='margin:0;display:grid;place-items:center;min-height:100vh;"
                                                "background:#fff'>%s</body></html>" % text)
            self.web.setHtml(page, QUrl("https://lienzo.jayth.local/"))
            lay.addWidget(self.stage)
        elif kind == "svg":
            from PySide6.QtSvgWidgets import QSvgWidget
            w = QSvgWidget()
            w.load(text.encode("utf-8"))
            w.renderer().setAspectRatioMode(Qt.KeepAspectRatio)
            w.setStyleSheet("background:white")
            lay.addWidget(w)
        else:                                   # página web sin navegador integrado
            box = QWidget()
            bv = QVBoxLayout(box)
            bv.setAlignment(Qt.AlignCenter)
            msg = QLabel(tr("La vista previa de páginas web se abre en tu navegador."))
            msg.setObjectName("muted")
            msg.setAlignment(Qt.AlignCenter)
            msg.setWordWrap(True)
            bv.addWidget(msg)
            b = QPushButton(tr("Abrir en el navegador"))
            b.setProperty("kind", "primary")
            b.clicked.connect(lambda *_: self.open_external())
            bv.addWidget(b, 0, Qt.AlignCenter)
            lay.addWidget(box)

    def _render(self):
        if self.item.get("kind") == "file":
            return self._render_file()
        self.b_edit.setVisible(True)
        self.title.setToolTip("")
        kind, text = self.item["kind"], self.text()
        n = len(self.paths)
        self.title.setText(self.item["title"])
        self.sub.setText(KIND_LABEL.get(kind, kind) + (" · %s" % self.item["language"] if self.item.get("language") else ""))
        mine = self._vnum() in self.user_versions
        self.ver.setText((tr("v%d de %d · tuya") if mine else tr("v%d de %d")) % (self.idx + 1, n))
        self.ver.setToolTip(tr("Esta versión la guardaste tú") if mine else "")
        for w in (self.b_prev, self.b_next, self.ver):
            w.setVisible(n > 1)
        self.b_prev.setEnabled(self.idx > 0)
        self.b_next.setEnabled(self.idx < n - 1)
        self.b_items.setVisible(self._count_items() > 1)
        self.b_view.setVisible(kind != "code")
        self.source.setPlainText(text)
        self._highlight(False)
        if kind == "code":
            self._clear(self.pv)
            self._show_page(self.SOURCE)
            return
        self._render_into(self.pv, kind, text, self.paths[self.idx] if self.paths else None)
        self.b_view.blockSignals(True)
        self.b_view.setChecked(False)
        self.b_view.blockSignals(False)
        self._show_page(self.PREVIEW)

    def _render_file(self):
        """Un archivo del disco con el mismo visor que el editor: Word, Excel, PowerPoint y PDF en modo lectura,
        imágenes con zoom, tablas CSV, Markdown y HTML con vista previa, código con colores."""
        from .codeview import FileTab
        from .docview import DOC_KIND
        path = self.item["path"]
        ext = os.path.splitext(path)[1].lower()
        self.title.setText(os.path.basename(path))
        self.title.setToolTip(path)
        self.sub.setText(DOC_KIND.get(ext) or KIND_LABEL["file"])
        for w in (self.b_prev, self.b_next, self.ver, self.b_items, self.b_edit, self.b_view):
            w.setVisible(False)
        self._clear(self.pv)
        self.console_log = []
        if not os.path.isfile(path):
            msg = QLabel(tr("«%s» ya no existe.") % os.path.basename(path))
            msg.setObjectName("muted")
            msg.setAlignment(Qt.AlignCenter)
            self.pv.addWidget(msg)
        else:
            self._filetab = FileTab(path, self.preview_host)
            if hasattr(self._filetab, "open_file"):        # un enlace del documento a otro archivo: también aquí
                self._filetab.open_file.connect(lambda p: os.path.isfile(p) and self._open_item(file_item(p)))
            self.pv.addWidget(self._filetab)
        self._show_page(self.PREVIEW)

    def _download(self, p):
        try:
            from .desktop import download_copy
        except Exception:
            return self.save_as()
        download_copy(self, p)

    def _file_changed(self):
        """El archivo cambió en el disco (el agente lo volvió a crear, o se guardó desde su programa)."""
        if not self.item or self.item.get("kind") != "file":
            return
        p = self.item["path"]
        if os.path.isfile(p) and p not in self._watch.files():
            self._watch.addPath(p)                    # muchos programas lo reemplazan: hay que volver a vigilarlo
        ft = self._filetab
        if ft is not None and os.path.isfile(p) and not getattr(ft, "dirty", False):
            try:
                ft.reload()
                return
            except Exception:
                pass
        self._render_file()

    def _count_items(self):
        try:
            from . import tools as T
            return len(T.canvas_items(d=os.path.dirname(self.item["path"])))
        except Exception:
            return 1

    def _show_page(self, i):
        self.stack.setCurrentIndex(i)
        self._sync_webbar()
        editing = i == self.EDIT
        for w in (self.b_prev, self.b_next, self.b_items, self.b_edit, self.b_view):
            w.setEnabled(not editing and (w is not self.b_prev or self.idx > 0) and (w is not self.b_next or self.idx < len(self.paths) - 1))

    def _toggle_source(self, on):
        if not self.editing:
            self._show_page(self.SOURCE if on else self.PREVIEW)

    # ---- contenidos de la conversación y más opciones
    def _fill_items(self):
        self.items_menu.clear()
        try:
            from . import tools as T
            items = T.canvas_items(d=os.path.dirname(self.item["path"])) if self.item else []
        except Exception:
            items = []
        for it in items:
            a = self.items_menu.addAction("%s  ·  %s · v%d" % (it["title"], KIND_LABEL.get(it["kind"], it["kind"]), it["version"]))
            a.setCheckable(True)
            a.setChecked(it["slug"] == (self.item or {}).get("slug"))
            a.triggered.connect(lambda *_, it=it: self._open_item(it))

    def _open_item(self, it):
        if self.main is not None and hasattr(self.main, "open_canvas"):
            self.main.open_canvas(it)
        else:
            self.load(it)

    def _fill_more(self):
        m = self.more_menu
        m.clear()
        if self.item and self.item.get("kind") == "file":
            p = self.item["path"]
            m.addAction(icon("acc_abrir_externo", C["mut"], 15), tr("Abrir con su programa"), lambda: osys.open_path(p))
            m.addAction(icon("act_carpeta_abierta", C["mut"], 15), tr("Mostrar en la carpeta"), lambda: osys.reveal(p))
            m.addAction(icon("acc_copiar", C["mut"], 15), tr("Copiar la ruta"), lambda: QGuiApplication.clipboard().setText(p))
            m.addAction(icon("acc_descargar", C["mut"], 15), tr("Descargar una copia…"), lambda: self._download(p))
            return
        a = m.addAction(icon("ui_dividir_h", C["mut"], 15), tr("Ver cambios respecto a la versión anterior"), self.show_diff)
        a.setEnabled(self.idx > 0 and not self.editing)
        m.addSeparator()
        m.addAction(icon("acc_copiar", C["mut"], 15), tr("Copiar el contenido"), self.copy)
        m.addAction(icon("acc_descargar", C["mut"], 15), tr("Guardar como…"), self.save_as)
        a = m.addAction(icon("act_carpeta", C["mut"], 15), tr("Guardar en el proyecto"), self.save_to_project)
        a.setToolTip(tr("Copia esta versión en la carpeta de trabajo con el nombre del contenido"))
        kinds = EXPORT_KINDS.get(self.item["kind"], ()) if self.item else ()
        if kinds:
            ex = m.addMenu(icon("acc_abrir_externo", C["mut"], 15), tr("Exportar como"))
            ex.setEnabled(not self.editing)
            for fmt in kinds:
                ex.addAction(EXPORTS[fmt][0], lambda f=fmt: self.export(f))
        if self.item and self.item["kind"] in ("html", "svg"):
            m.addAction(icon("acc_abrir_externo", C["mut"], 15), tr("Abrir en el navegador"), self.open_external)

    # ---- cambios entre versiones
    def diff_html(self, old, new):
        """Diferencias línea a línea en HTML (verde lo añadido, rojo lo quitado) y cuántas líneas cambian (+, −)."""
        import html as _h
        rows, add, rem = [], 0, 0
        for ln in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=3):
            if ln.startswith(("---", "+++")):
                continue
            t = _h.escape(ln) or "&nbsp;"
            if ln.startswith("@@"):
                rows.append("<div style='color:%s;padding:6px 0 2px 0'>%s</div>" % (C["info"], t))
            elif ln.startswith("+"):
                add += 1
                rows.append("<div style='background:%s;color:%s'>%s</div>" % (C["acc_bg"], C["ok"], t))
            elif ln.startswith("-"):
                rem += 1
                rows.append("<div style='background:%s;color:%s'>%s</div>" % (C["bad_bg"], C["bad"], t))
            else:
                rows.append("<div style='color:%s'>%s</div>" % (C["mut"], t))
        body = "".join(rows) or "<div style='color:%s'>%s</div>" % (C["mut"], _h.escape(tr("Las dos versiones son iguales.")))
        return "<div style=\"white-space:pre;font-family:'%s',monospace\">%s</div>" % (osys.mono_font(), body), add, rem

    def show_diff(self):
        if self.idx <= 0:
            return
        page, add, rem = self.diff_html(self.text(self.idx - 1), self.text())
        self.diff.setHtml(page)
        self.diff_lbl.setText(tr("Cambios de la v%d a la v%d  ·  +%d  −%d líneas") % (self.idx, self.idx + 1, add, rem))
        self._show_page(self.DIFF)

    # ---- edición del usuario
    def _draft_key(self):
        return os.path.normcase(os.path.join(os.path.dirname(self.item["path"]), self.item.get("slug") or ""))

    def start_edit(self):
        if not self.item or self.editing:
            return
        self._base = self.text()
        draft = self._drafts.pop(self._draft_key(), None)
        self.editing = True
        self.editor.blockSignals(True)
        self.editor.setPlainText(draft if draft is not None else self._base)
        self.editor.blockSignals(False)
        self._highlight(True)
        self.edit_lbl.setText(tr("Recuperé tu borrador sin guardar") if draft is not None else
                              (tr("Editando a partir de la v%d") % (self.idx + 1)))
        live = self.item["kind"] != "code"
        self.b_live.setVisible(live)
        self.live_host.setVisible(live and self.b_live.isChecked())
        if live and self.b_live.isChecked():
            self._render_live()
            self.edit_split.setSizes([1, 1])
        self.edit_bar.show()
        self.edit_line.show()
        self._show_page(self.EDIT)
        self.editor.setFocus()

    def dirty(self):
        return self.editing and self.editor.toPlainText() != self._base

    def _edited(self):
        if self.editing and self.live_host.isVisible():
            self._live_timer.start()

    def _toggle_live(self, on):
        if not self.editing:
            return
        self.live_host.setVisible(on)
        if on:
            self._render_live()
            self.edit_split.setSizes([1, 1])
        self._sync_webbar()

    def _render_live(self):
        if self.editing and self.item["kind"] != "code":
            self._render_into(self.lv, self.item["kind"], self.editor.toPlainText())

    def _end_edit(self):
        self.editing = False
        self._live_timer.stop()
        self.edit_bar.hide()
        self.edit_line.hide()
        self._clear(self.lv)

    def discard_edit(self):
        if not self.editing:
            return
        self._end_edit()
        self._render()

    def _stash_draft(self):
        if self.dirty():
            self._drafts[self._draft_key()] = self.editor.toPlainText()
            if self.main is not None:
                self.main.toast(tr("El lienzo cambió mientras editabas. Guardé tu borrador: pulsa Editar para recuperarlo."),
                                icon_name="est_info", ms=9000)
        self._end_edit()

    def save_edit(self):
        if not self.editing:
            return
        text = self.editor.toPlainText()
        if text == self._base:
            self._end_edit()
            self._render()
            if self.main is not None:
                self.main.toast(tr("Sin cambios: no hay nada que guardar."), ms=2500)
            return
        from . import tools as T
        try:
            it = T.canvas_save(None, self.item["title"], self.item["kind"], text, self.item.get("language") or "", by_user=True,
                               d=os.path.dirname(self.item["path"]))
        except Exception as e:
            if self.main is not None:
                self.main.toast(tr("No se pudo guardar: %s") % e, icon_name="est_error", color=C["bad"])
            return
        self._end_edit()
        self.load(it)
        self.user_saved.emit(it)
        if self.main is not None:
            self.main.toast(tr("Guardado como versión %d. El agente lo sabrá en tu próximo mensaje.") % it["version"],
                            icon_name="ui_check", color=C["ok"])

    # ---- pedir un cambio al agente
    def selection(self):
        """Lo que el usuario tiene seleccionado en el lienzo (texto, código o página)."""
        page = self.stack.currentIndex()
        if page == self.EDIT:
            s = self.editor.textCursor().selectedText()
        elif page == self.SOURCE:
            s = self.source.textCursor().selectedText()
        elif page == self.PREVIEW and self.item and self.item["kind"] in ("html", "svg") and self.web is not None:
            s = self.web.selectedText()
        elif page == self.PREVIEW and self._md_view is not None:
            s = self._md_view.textCursor().selectedText()
        elif page == self.PREVIEW and self._filetab is not None:
            s = ""
            for w in (getattr(self._filetab, "editor", None), getattr(self._filetab, "preview", None)):
                if w is not None and w.isVisible():
                    if hasattr(w, "textCursor"):
                        s = w.textCursor().selectedText()
                    elif hasattr(w, "selectedText"):
                        s = w.selectedText()
                    if s:
                        break
        else:
            s = ""
        return s.replace(" ", "\n").replace(" ", "\n").strip()

    def ask_text(self):
        sel = self.selection()
        t = self.item["title"] if self.item else ""
        if self.item and self.item.get("kind") == "file":     # el agente necesita la ruta para encontrarlo
            if not sel:
                return tr("Sobre «%s» (%s): ") % (t, self.item["path"])
            if len(sel) > 600:
                sel = sel[:600].rstrip() + "…"
            return tr("En «%s» (%s), cambia esta parte:\n«%s»\n\n") % (t, self.item["path"], sel)
        if not sel:
            return tr("En el lienzo «%s»: ") % t
        if len(sel) > 600:
            sel = sel[:600].rstrip() + "…"
        return tr("En el lienzo «%s», cambia esta parte:\n«%s»\n\n") % (t, sel)

    def ask_change(self):
        if not self.item:
            return
        text = self.ask_text()
        if self.expanded:
            self.toggle_expand()
        panel = self.main.current_panel() if self.main is not None else None
        if panel is not None and hasattr(panel, "_pick"):
            panel._pick(text)

    # ---- acciones
    def copy(self):
        QGuiApplication.clipboard().setText(self.editor.toPlainText() if self.editing else self.text())
        if self.main is not None:
            self.main.toast(tr("Copiado."), ms=1800, icon_name="ui_check", color=C["ok"])

    def save_as(self):
        if not self.paths:
            return
        src = self.paths[self.idx]
        ext = os.path.splitext(src)[1]
        base = self.main.current_panel().workspace() if self.main is not None else os.path.expanduser("~")
        name = re.sub(r'[\\/:*?"<>|]+', " ", self.item["title"]).strip() or "lienzo"
        dst, _ = QFileDialog.getSaveFileName(self, tr("Guardar como"), os.path.join(base, name + ext), tr("Archivo (*%s);;Todos (*.*)") % ext)
        if dst:
            shutil.copyfile(src, dst)
            if self.main is not None:
                self.main.toast(tr("Guardado en %s") % dst, icon_name="ui_check", color=C["ok"])

    def open_external(self):
        if self.paths:
            osys.open_path(self.paths[self.idx])

    # ---- exportar y guardar en el proyecto
    def _workspace(self):
        try:
            return self.main.current_panel().workspace()
        except Exception:
            return os.path.expanduser("~")

    def _file_name(self, ext):
        return (re.sub(r'[\\/:*?"<>|]+', " ", self.item["title"]).strip() or "lienzo") + ext

    def save_to_project(self):
        """Copia la versión que se ve en la carpeta de trabajo (sin pisar nada: «nombre (2)» si ya existe)."""
        if not self.paths:
            return None
        folder = self._workspace()
        base, ext = os.path.splitext(self._file_name(self._ext()))
        dst, n = os.path.join(folder, base + ext), 2
        while os.path.exists(dst):
            dst, n = os.path.join(folder, "%s (%d)%s" % (base, n, ext)), n + 1
        try:
            os.makedirs(folder, exist_ok=True)
            shutil.copyfile(self.paths[self.idx], dst)
        except OSError as e:
            self._done(False, str(e))
            return None
        if self.main is not None:
            self.main.toast(tr("Guardado en el proyecto: %s") % os.path.basename(dst), action=tr("Mostrar"),
                            on_action=lambda: osys.reveal(dst), icon_name="ui_check", color=C["ok"])
        return dst

    def export(self, fmt):
        if not self.item or fmt not in EXPORTS:
            return
        ext = EXPORTS[fmt][1]
        dst, _ = QFileDialog.getSaveFileName(self, tr("Exportar como %s") % EXPORTS[fmt][0], os.path.join(self._workspace(), self._file_name(ext)),
                                             "%s (*%s)" % (EXPORTS[fmt][0], ext))
        if dst:
            self.export_to(fmt, dst)

    def _done(self, ok, msg):
        if self.main is None:
            return
        if ok:
            self.main.toast(tr("Exportado: %s") % os.path.basename(msg), action=tr("Mostrar"), on_action=lambda: osys.reveal(msg),
                            icon_name="ui_check", color=C["ok"])
        else:
            self.main.toast(tr("No se pudo exportar: %s") % msg, icon_name="est_error", color=C["bad"])

    def export_to(self, fmt, dst, done=None):
        """Exporta la versión que se ve a `dst`. Llama a done(ok, ruta o error) al terminar: el PDF y la imagen de una
        página web llegan un momento después (los hace el navegador integrado)."""
        done = done or self._done
        kind, text, title = self.item["kind"], self.text(), self.item["title"]
        from . import office
        try:
            if kind == "html" and fmt in ("pdf", "png"):
                return self._export_web(fmt, dst, done)
            if fmt in ("pdf", "docx"):
                if kind == "svg":
                    self._svg_pdf(text, dst)
                else:
                    md = text if kind == "markdown" else "```\n%s\n```" % text
                    (office.write_pdf if fmt == "pdf" else office.write_docx)(dst, md, title)
            elif fmt == "html":
                import html as _h
                page = (office.md_html(text, title) if kind == "markdown" else
                        _page_html(title, text, "display:grid;place-items:center;min-height:100vh;background:#fff") if kind == "svg" else
                        _page_html(title, "<pre>%s</pre>" % _h.escape(text), "padding:24px;font:13px Consolas,Menlo,monospace"))
                with open(dst, "w", encoding="utf-8", newline="\n") as f:
                    f.write(page)
            elif fmt == "png":
                img = self._svg_image(text) if kind == "svg" else self._doc_image(text)
                if img is None or img.isNull() or not img.save(dst, "PNG"):
                    raise RuntimeError(tr("no se pudo crear la imagen"))
            else:
                raise RuntimeError(tr("formato no disponible para este contenido"))
        except Exception as e:
            done(False, str(e))
            return
        done(True, dst)

    def _svg_renderer(self, text):
        from PySide6.QtSvg import QSvgRenderer
        r = QSvgRenderer(QByteArray(text.encode("utf-8")))
        if not r.isValid():
            raise RuntimeError(tr("el dibujo SVG no es válido"))
        return r

    def _svg_image(self, text):
        from PySide6.QtGui import QImage, QPainter
        r = self._svg_renderer(text)
        s = r.defaultSize()
        w, h = max(1, s.width()), max(1, s.height())
        k = max(1.0, min(4.0, 1600.0 / max(w, h)))          # nítido aunque el dibujo sea pequeño
        img = QImage(int(w * k), int(h * k), QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        r.render(p)
        p.end()
        return img

    def _svg_pdf(self, text, dst):
        from PySide6.QtGui import QPdfWriter, QPainter, QPageSize, QPageLayout
        from PySide6.QtCore import QRectF, QMarginsF
        r = self._svg_renderer(text)
        s = r.defaultSize()
        wr = QPdfWriter(dst)
        wr.setPageSize(QPageSize(QPageSize.A4))
        wr.setPageOrientation(QPageLayout.Landscape if s.width() > s.height() else QPageLayout.Portrait)
        wr.setPageMargins(QMarginsF(12, 12, 12, 12))
        wr.setTitle(self.item["title"])
        p = QPainter(wr)
        page = QRectF(0, 0, wr.width(), wr.height())
        k = min(page.width() / max(1, s.width()), page.height() / max(1, s.height()))
        w, h = s.width() * k, s.height() * k
        r.render(p, QRectF((page.width() - w) / 2, (page.height() - h) / 2, w, h))
        p.end()

    def _doc_image(self, text):
        """Un documento Markdown entero como imagen (fondo blanco, ancho de lectura)."""
        from PySide6.QtGui import QImage, QPainter, QTextDocument, QColor, QPalette, QAbstractTextDocumentLayout
        doc = QTextDocument()
        f = QFont(self.font())
        f.setPointSizeF(11)
        doc.setDefaultFont(f)
        doc.setDocumentMargin(36)
        doc.setMarkdown(text)
        doc.setTextWidth(860)
        w, h = 860, int(doc.size().height()) + 1
        k = 2
        img = QImage(w * k, h * k, QImage.Format_ARGB32_Premultiplied)
        img.fill(QColor("white"))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(k, k)
        ctx = QAbstractTextDocumentLayout.PaintContext()     # colores de documento, no los del tema de Jayth
        for role, col in ((QPalette.Text, "#1b1f1d"), (QPalette.WindowText, "#1b1f1d"), (QPalette.Link, "#1d6fb8")):
            ctx.palette.setColor(role, QColor(col))
        doc.documentLayout().draw(p, ctx)
        p.end()
        return img

    def _export_web(self, fmt, dst, done):
        """PDF o imagen de la página que se ve (la vista previa debe estar delante para poder capturarla)."""
        if not web_view_class() or self.web is None:
            return done(False, tr("hace falta el navegador integrado"))
        if self.stack.currentIndex() != self.PREVIEW:
            self.b_view.setChecked(False)
            self._show_page(self.PREVIEW)
        page = self.web.page()
        if fmt == "pdf":
            def fin(path, ok):
                try:
                    page.pdfPrintingFinished.disconnect(fin)
                except Exception:
                    pass
                done(bool(ok), path if ok else tr("el navegador no pudo crear el PDF"))
            page.pdfPrintingFinished.connect(fin)
            page.printToPdf(dst)
            return

        def grab():
            img = self.web.grab().toImage()
            if img.isNull() or img.width() < 20 or not img.save(dst, "PNG"):
                return done(False, tr("no se pudo crear la imagen"))
            done(True, dst)
        QTimer.singleShot(350, grab)

    def close_panel(self):
        if self.editing:
            self._stash_draft()
            self._render()
        if self.expanded:
            self.toggle_expand()
        self.closed.emit()

    # ---- vista web: dispositivo, zoom, recargar, consola y ampliar
    def web_shown(self):
        page = self.stack.currentIndex()
        return bool(self.item and self.item["kind"] in ("html", "svg") and web_view_class() and
                    (page == self.PREVIEW or (page == self.EDIT and self.editing and self.live_host.isVisible())))

    def _sync_webbar(self):
        on = self.web_shown() if hasattr(self, "stack") else False
        self.webbar.setVisible(on)
        self.web_line.setVisible(on)
        if not on:
            self.b_console.setChecked(False)
        self.b_device.setVisible(bool(self.item and self.item["kind"] == "html"))
        label, W, H = DEVICES[self.device]
        self.b_device.setText(label)
        self.b_zoom.setText("%d %%" % round(self.zoom * 100))
        self.b_zoom_out.setEnabled(self.zoom > ZOOMS[0] + 1e-6)
        self.b_zoom_in.setEnabled(self.zoom < ZOOMS[-1] - 1e-6)

    def set_device(self, d):
        self.device = d if d in DEVICES else "auto"
        if self.stage is not None and self.item and self.item["kind"] == "html":
            self.stage.set_device(self.device)
        self._sync_webbar()

    def set_zoom(self, z):
        self.zoom = max(ZOOMS[0], min(ZOOMS[-1], z))
        if self.stage is not None:
            self.stage.set_zoom(self.zoom)
        self._sync_webbar()

    def step_zoom(self, d):
        i = min(range(len(ZOOMS)), key=lambda k: abs(ZOOMS[k] - self.zoom))
        self.set_zoom(ZOOMS[max(0, min(len(ZOOMS) - 1, i + d))])

    def reload(self):
        if not self.item:
            return
        if self.editing:
            self._render_live()
        elif self.stack.currentIndex() == self.PREVIEW:
            self._render_into(self.pv, self.item["kind"], self.text(), self.paths[self.idx] if self.paths else None)

    def _on_console(self, kind, msg, line):
        self.console_log.append((kind, msg, line))
        mark = {"error": "×", "warning": "!"}.get(kind, "·")        # (la fuente monoespaciada no siempre tiene ✕ ni ⚠)
        self.console.appendPlainText("%s %s%s" % (mark, (tr("línea %d: ") % line) if line else "", msg))
        self._sync_console(kind == "error")

    def _sync_console(self, new_error=False):
        if not self.console_log:
            self.console.clear()
        errs = sum(1 for k, m, l in self.console_log if k == "error")
        warns = sum(1 for k, m, l in self.console_log if k == "warning")
        txt = tr("Consola")
        if errs:
            txt += "  ·  " + (tr("%d errores") % errs if errs > 1 else tr("1 error"))
        elif warns:
            txt += "  ·  " + (tr("%d avisos") % warns if warns > 1 else tr("1 aviso"))
        self.b_console.setText(txt)
        self.b_console.setIcon(icon("est_error" if errs else "est_aviso" if warns else "pan_consola",
                                    C["bad"] if errs else C["warn"] if warns else C["mut"], 14))
        self.b_fix.setVisible(bool(errs or warns))

    def ask_fix(self):
        bad = [(k, m, l) for k, m, l in self.console_log if k in ("error", "warning")][:8]
        if not bad or not self.item:
            return
        lines = "\n".join("- %s%s" % ((tr("línea %d: ") % l) if l else "", m[:300]) for k, m, l in bad)
        text = tr("En el lienzo «%s», la consola de la página muestra estos errores; arréglalos:\n%s\n") % (self.item["title"], lines)
        if self.expanded:
            self.toggle_expand()
        panel = self.main.current_panel() if self.main is not None else None
        if panel is not None and hasattr(panel, "_pick"):
            panel._pick(text)

    def toggle_expand(self):
        self.expanded = not self.expanded
        self.b_expand.setIcon(icon("app_restaurar" if self.expanded else "app_pantalla_completa", C["mut"], 15))
        tip = tr("Volver junto al chat (Esc)") if self.expanded else tr("Ampliar el lienzo a toda la ventana")
        self.b_expand.setToolTip(tip)
        self.b_expand.setAccessibleName(tip)
        self.expand_changed.emit(self.expanded)
