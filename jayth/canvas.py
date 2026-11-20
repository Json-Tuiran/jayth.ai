# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Lienzo: panel junto a la conversación donde el agente muestra lo que crea (páginas web, documentos, dibujos, código).

- Vista previa en vivo y vista del código, con historial de versiones (cada corrección del agente es una versión).
- Las páginas web se muestran con el navegador integrado (Qt WebEngine) si está disponible; si no, se abren en el
  navegador del sistema con un clic.
"""
import os, re, glob, shutil
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QGuiApplication, QFont, QTransform
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget, QPlainTextEdit, QScrollArea, QFileDialog, QFrame, QPushButton
from . import osys
from .theme import C, icon
from .widgets import TextView, ElidedLabel
from .i18n import tr

KIND_LABEL = {"html": tr("Página web"), "markdown": tr("Documento"), "svg": tr("Dibujo"), "code": tr("Código")}
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


class CanvasPanel(QWidget):
    closed = Signal()

    def __init__(self, main=None):
        super().__init__()
        self.main = main
        self.setObjectName("canvas")
        self.setMinimumWidth(320)
        self.setProperty("foldable", True)
        self.item, self.paths, self.idx, self.web = None, [], 0, None
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head = QWidget()
        head.setObjectName("canvasHead")
        h = QHBoxLayout(head)
        h.setContentsMargins(14, 6, 8, 6)
        h.setSpacing(4)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = ElidedLabel()
        self.title.setStyleSheet("font-weight:600")
        col.addWidget(self.title)
        self.sub = ElidedLabel()
        self.sub.setObjectName("faint")
        col.addWidget(self.sub)
        h.addLayout(col, 1)
        self.b_prev = _tb("ui_chevron_derecha", tr("Versión anterior"), lambda: self.go(self.idx - 1), 13)
        self.b_prev.setIcon(icon("ui_chevron_derecha", C["mut"], 13).pixmap(13, 13).transformed(QTransform().rotate(180)))
        self.b_next = _tb("ui_chevron_derecha", tr("Versión siguiente"), lambda: self.go(self.idx + 1), 13)
        self.ver = QLabel()
        self.ver.setObjectName("faint")
        for w in (self.b_prev, self.ver, self.b_next):
            h.addWidget(w)
        self.b_view = QPushButton(tr("Código"))
        self.b_view.setProperty("kind", "flat")
        self.b_view.setCheckable(True)
        self.b_view.setToolTip(tr("Cambiar entre la vista previa y el código"))
        self.b_view.toggled.connect(self._toggle_source)
        h.addWidget(self.b_view)
        h.addWidget(_tb("acc_copiar", tr("Copiar el contenido"), self.copy))
        h.addWidget(_tb("acc_descargar", tr("Guardar como…"), self.save_as))
        self.b_browser = _tb("acc_abrir_externo", tr("Abrir en el navegador"), self.open_external)
        h.addWidget(self.b_browser)
        h.addWidget(_tb("ui_cerrar", tr("Cerrar el lienzo"), self.close_panel, 13))
        v.addWidget(head)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("hline")
        v.addWidget(line)
        self.stack = QStackedWidget()
        v.addWidget(self.stack, 1)
        # 0: vista previa (se rellena segun el tipo)   1: codigo
        self.preview_host = QWidget()
        self.pv = QVBoxLayout(self.preview_host)
        self.pv.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.preview_host)
        self.source = QPlainTextEdit()
        self.source.setObjectName("mono")
        self.source.setReadOnly(True)
        self.source.setLineWrapMode(QPlainTextEdit.NoWrap)
        f = QFont(osys.mono_font())
        f.setPointSizeF(10)
        self.source.setFont(f)
        self.stack.addWidget(self.source)

    # ---- carga
    def load(self, item):
        self.item = dict(item)
        self.paths = versions_of(item)
        want = os.path.normcase(item["path"])
        self.idx = next((i for i, p in enumerate(self.paths) if os.path.normcase(p) == want), len(self.paths) - 1)
        self._render()

    def go(self, i):
        if 0 <= i < len(self.paths):
            self.idx = i
            self._render()

    def text(self):
        try:
            with open(self.paths[self.idx], encoding="utf-8", errors="replace") as f:
                return f.read()
        except (OSError, IndexError):
            return ""

    def _clear_preview(self):
        while self.pv.count():
            w = self.pv.takeAt(0).widget()
            if w is not None and w is not self.web:
                w.deleteLater()
            elif w is self.web:
                w.setParent(None)

    def _render(self):
        kind, text = self.item["kind"], self.text()
        n = len(self.paths)
        self.title.setText(self.item["title"])
        self.sub.setText(KIND_LABEL.get(kind, kind) + (" · %s" % self.item["language"] if self.item.get("language") else ""))
        self.ver.setText(tr("v%d de %d") % (self.idx + 1, n))
        for w in (self.b_prev, self.b_next, self.ver):
            w.setVisible(n > 1)
        self.b_prev.setEnabled(self.idx > 0)
        self.b_next.setEnabled(self.idx < n - 1)
        self.b_browser.setVisible(kind in ("html", "svg"))
        self.b_view.setVisible(kind != "code")
        self.source.setPlainText(text)
        self._clear_preview()
        if kind == "code":
            self.stack.setCurrentIndex(1)
            return
        if kind == "markdown":
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.NoFrame)
            inner = QWidget()
            iv = QVBoxLayout(inner)
            iv.setContentsMargins(22, 16, 22, 22)
            iv.addWidget(TextView(text, "md", size="10.5pt"))
            iv.addStretch(1)
            sa.setWidget(inner)
            self.pv.addWidget(sa)
        elif kind in ("html", "svg") and web_view_class():
            if self.web is None:
                self.web = web_view_class()()
            page = text if kind == "html" else ("<!doctype html><html><body style='margin:0;display:grid;place-items:center;min-height:100vh;"
                                                "background:#fff'>%s</body></html>" % text)
            self.web.setHtml(page, QUrl("https://lienzo.jayth.local/"))
            self.pv.addWidget(self.web)
        elif kind == "svg":
            from PySide6.QtSvgWidgets import QSvgWidget
            w = QSvgWidget()
            w.load(text.encode("utf-8"))
            w.renderer().setAspectRatioMode(Qt.KeepAspectRatio)
            w.setStyleSheet("background:white")
            self.pv.addWidget(w)
        else:                                   # pagina web sin navegador integrado
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
            self.pv.addWidget(box)
        self.b_view.blockSignals(True)
        self.b_view.setChecked(False)
        self.b_view.blockSignals(False)
        self.stack.setCurrentIndex(0)

    def _toggle_source(self, on):
        self.stack.setCurrentIndex(1 if on else 0)

    # ---- acciones
    def copy(self):
        QGuiApplication.clipboard().setText(self.text())
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

    def close_panel(self):
        self.closed.emit()
