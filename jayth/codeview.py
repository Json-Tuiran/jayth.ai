"""Piezas del modo Jayth Code: editor con resaltado, pestañas, arbol de archivos, terminal y dialogo de proyecto."""
import os, re, json, time, uuid
from PySide6.QtCore import Qt, QRect, QSize, Signal, QFileSystemWatcher, QProcess, QDir, QModelIndex, QTimer, QUrl
from PySide6.QtGui import (QColor, QFont, QPainter, QTextFormat, QSyntaxHighlighter, QTextCharFormat, QKeySequence, QShortcut,
                           QPixmap, QGuiApplication, QTextCursor, QDesktopServices, QTextOption)
from PySide6.QtWidgets import (QWidget, QPlainTextEdit, QTextEdit, QTabWidget, QTreeView, QFileSystemModel, QVBoxLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMenu, QMessageBox, QInputDialog, QDialog, QFormLayout, QFileDialog, QHeaderView,
                               QAbstractItemView, QScrollArea, QToolButton, QPushButton, QDialogButtonBox, QRadioButton, QButtonGroup,
                               QStackedWidget, QFrame)
from . import core, paths, osys
from .theme import C, icon, pix
from .wizard import btn, lbl, browse_row

MONO = QFont(osys.mono_font(), 10)
MONO.setStyleHint(QFont.Monospace)
MONO_CSS = "'%s'" % osys.mono_font()
TEXT_EXT = {".py", ".pyw", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".json", ".html", ".htm", ".css", ".scss", ".md", ".txt", ".ps1", ".psm1",
            ".bat", ".cmd", ".sh", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".xml", ".svg", ".csv", ".sql", ".c", ".h", ".cpp", ".hpp", ".cs",
            ".java", ".go", ".rs", ".php", ".rb", ".lua", ".gd", ".env", ".gitignore", ".log", ".vue", ".kt", ".swift", ".r", ".dart"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico"}


# ---------------------------------------------------------------- resaltado de sintaxis
KW = {
    "py": "and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield self match case",
    "js": "async await break case catch class const continue debugger default delete do else export extends false finally for from function if import in instanceof let new null of return static super switch this throw true try typeof undefined var void while with yield interface type enum implements",
    "ps": "begin break catch class continue data do dynamicparam else elseif end exit filter finally for foreach from function if in param process return switch throw trap try until using var while $true $false $null",
    "c": "auto break case char const continue default do double else enum extern float for goto if int long register return short signed sizeof static struct switch typedef union unsigned void volatile while class public private protected namespace using new delete template typename virtual override bool true false nullptr string var func package import fn let mut impl pub use match",
}
LANG = {".py": "py", ".pyw": "py", ".gd": "py", ".js": "js", ".mjs": "js", ".cjs": "js", ".ts": "js", ".tsx": "js", ".jsx": "js", ".vue": "js",
        ".ps1": "ps", ".psm1": "ps", ".c": "c", ".h": "c", ".cpp": "c", ".hpp": "c", ".cs": "c", ".java": "c", ".go": "c", ".rs": "c",
        ".kt": "c", ".swift": "c", ".dart": "c", ".php": "c", ".json": "json", ".html": "html", ".htm": "html", ".xml": "html", ".svg": "html",
        ".css": "css", ".scss": "css", ".md": "md", ".yml": "yaml", ".yaml": "yaml", ".toml": "yaml", ".ini": "yaml", ".cfg": "yaml",
        ".bat": "bat", ".cmd": "bat", ".sh": "ps", ".lua": "js", ".rb": "py", ".sql": "c"}


def _fmt(color, bold=False, italic=False):
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Bold)
    f.setFontItalic(italic)
    return f


class Highlighter(QSyntaxHighlighter):
    def __init__(self, doc, ext):
        super().__init__(doc)
        dark = C["bg"] < "#8"
        col = ({"kw": "#c792ea", "str": "#c3e88d", "num": "#f78c6c", "com": "#6c7385", "fn": "#82aaff", "tag": "#f07178", "attr": "#ffcb6b"} if dark else
               {"kw": "#7c3aed", "str": "#15803d", "num": "#c2410c", "com": "#8b92a2", "fn": "#2563eb", "tag": "#be123c", "attr": "#a16207"})
        lang = LANG.get(ext, "")
        self.rules = []
        self.ml = None   # comentario multilinea (inicio, fin)
        if lang in KW:
            words = [re.escape(w) for w in KW[lang].split()]
            self.rules.append((re.compile(r"(?<![\w$])(%s)(?![\w])" % "|".join(words), re.I if lang == "ps" else 0), _fmt(col["kw"], True)))
            self.rules.append((re.compile(r"\b([A-Za-z_]\w*)(?=\s*\()"), _fmt(col["fn"])))
            if lang == "ps":
                self.rules.append((re.compile(r"\$[\w:]+"), _fmt(col["attr"])))
        if lang in ("py", "js", "ps", "c", "json", "yaml", "css", "bat"):
            self.rules.append((re.compile(r"\b\d+(\.\d+)?\b"), _fmt(col["num"])))
        if lang in ("py", "js", "ps", "c", "json", "yaml", "css", "html"):
            self.rules.append((re.compile(r"\"([^\"\\\n]|\\.)*\"|'([^'\\\n]|\\.)*'|`[^`\n]*`"), _fmt(col["str"])))
        if lang == "json":
            self.rules.append((re.compile(r"\"[^\"\n]*\"(?=\s*:)"), _fmt(col["fn"])))
        if lang == "html":
            self.rules.append((re.compile(r"</?[\w:-]+|/?>"), _fmt(col["tag"])))
            self.rules.append((re.compile(r"\b[\w:-]+(?==)"), _fmt(col["attr"])))
            self.ml = ("<!--", "-->")
        if lang == "css":
            self.rules.append((re.compile(r"[\w-]+(?=\s*:)"), _fmt(col["fn"])))
        if lang == "md":
            self.rules.append((re.compile(r"^#{1,6} .*"), _fmt(col["fn"], True)))
            self.rules.append((re.compile(r"`[^`\n]+`"), _fmt(col["str"])))
            self.rules.append((re.compile(r"\*\*[^*\n]+\*\*"), _fmt(C["tx"], True)))
        if lang in ("py", "ps", "yaml", "sh"):
            self.rules.append((re.compile(r"#.*$"), _fmt(col["com"], italic=True)))
        if lang in ("js", "c", "css"):
            self.rules.append((re.compile(r"//.*$"), _fmt(col["com"], italic=True)))
            self.ml = ("/*", "*/")
        if lang == "bat":
            self.rules.append((re.compile(r"^\s*(rem|::).*$", re.I), _fmt(col["com"], italic=True)))
        if lang == "ps":
            self.ml = ("<#", "#>")
        self.com_fmt = _fmt(col["com"], italic=True)

    def highlightBlock(self, text):
        for rx, f in self.rules:
            for m in rx.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), f)
        if not self.ml:
            return
        a, b = self.ml
        self.setCurrentBlockState(0)
        start = 0 if self.previousBlockState() == 1 else text.find(a)
        while start >= 0:
            end = text.find(b, start + (0 if self.previousBlockState() == 1 and start == 0 else len(a)))
            if end < 0:
                self.setCurrentBlockState(1)
                self.setFormat(start, len(text) - start, self.com_fmt)
                break
            self.setFormat(start, end - start + len(b), self.com_fmt)
            start = text.find(a, end + len(b))


# ---------------------------------------------------------------- editor
class _Gutter(QWidget):
    def __init__(self, ed):
        super().__init__(ed)
        self.ed = ed

    def sizeHint(self):
        return QSize(self.ed.gutter_width(), 0)

    def paintEvent(self, e):
        self.ed.paint_gutter(e)


class CodeEditor(QPlainTextEdit):
    """Editor de código. Las líneas largas se leen con la barra de abajo o Mayús + rueda, o se ajustan al ancho con
    «Ajustar líneas» (Alt+Z)."""
    BOTTOM = 14

    def __init__(self):
        super().__init__()
        self.setObjectName("codeEditor")             # el tema le deja ver su barra horizontal (en el resto de la app no hay)
        self.setFont(MONO)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setStyleSheet("QPlainTextEdit { background: %s; border: none; border-radius: 0; padding: 0; font-family: %s; font-size: 10pt; }" % (C["bg"], MONO_CSS))
        self.gutter = _Gutter(self)
        self.gutter.setFont(MONO)
        # un poco de aire bajo la última línea: el código no queda pegado al borde de abajo
        self.blockCountChanged.connect(lambda _: self.setViewportMargins(self.gutter_width(), 0, 0, self.BOTTOM))
        self.updateRequest.connect(self._upd)
        self.cursorPositionChanged.connect(self._hl_line)
        self.setViewportMargins(self.gutter_width(), 0, 0, self.BOTTOM)
        self._hl_line()

    def set_wrap(self, on):
        """Ajustar las líneas largas al ancho (sin desplazarse de lado) o dejarlas enteras."""
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth if on else QPlainTextEdit.NoWrap)
        self.gutter.update()

    def wheelEvent(self, e):
        """Mayús + rueda: desplaza de lado (para leer el final de las líneas largas)."""
        if e.modifiers() & Qt.ShiftModifier and self.lineWrapMode() == QPlainTextEdit.NoWrap:
            hsb = self.horizontalScrollBar()
            d = e.angleDelta().y() or e.angleDelta().x()
            hsb.setValue(hsb.value() - d)
            e.accept()
            return
        super().wheelEvent(e)

    def gutter_width(self):
        return 18 + self.fontMetrics().horizontalAdvance("9") * max(3, len(str(self.blockCount())))

    def _upd(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def paint_gutter(self, e):
        p = QPainter(self.gutter)
        p.fillRect(e.rect(), QColor(C["bg"]))
        block = self.firstVisibleBlock()
        n = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        cur = self.textCursor().blockNumber()
        while block.isValid() and top <= e.rect().bottom():
            if block.isVisible() and bottom >= e.rect().top():
                p.setPen(QColor(C["tx"] if n == cur else C["faint"]))
                p.drawText(0, top, self.gutter.width() - 10, self.fontMetrics().height(), Qt.AlignRight, str(n + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            n += 1

    def _hl_line(self):
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(QColor(C["panel"]))
        sel.format.setProperty(QTextFormat.FullWidthSelection, True)
        sel.cursor = self.textCursor()
        sel.cursor.clearSelection()
        self.setExtraSelections([sel])
        self.gutter.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Tab and not self.textCursor().hasSelection():
            self.insertPlainText("    ")
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):      # mantener la sangria
            line = self.textCursor().block().text()
            ind = re.match(r"\s*", line).group(0)
            if line.rstrip().endswith((":", "{", "(", "[")):
                ind += "    "
            super().keyPressEvent(e)
            self.insertPlainText(ind)
            return
        super().keyPressEvent(e)


class FileTab(QWidget):
    """Una pestaña del editor. Elige cómo mostrar cada archivo: código con colores; Markdown formateado (y «Código» para
    editarlo); HTML, SVG y CSV con vista previa; Word, Excel, PowerPoint y PDF en modo lectura; imágenes con zoom."""
    changed = Signal()
    open_file = Signal(str)        # un enlace de la vista previa lleva a otro archivo del proyecto

    def __init__(self, path):
        super().__init__()
        from . import docview as DV
        self.DV = DV
        self.path = path
        self.dirty = False
        self._loading = False
        self.editor = self.preview = self.stack = None
        self.mode, self._stale = "code", True
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.v = v
        ext = os.path.splitext(path)[1].lower()
        self.ext = ext
        size = os.path.getsize(path) if os.path.isfile(path) else 0
        if ext in IMG_EXT:                                   # imagen: ajustada a la ventana, con zoom
            self.kind = "image"
            self.preview = DV.ImageView()
            self.preview.layout().itemAt(0).widget().layout().addWidget(self._open_btn())
            v.addWidget(self.preview)
            self.reload()
            return
        if ext in DV.DOCS:                                   # documento de Office o PDF: solo lectura
            self.kind = "doc"
            v.addWidget(self._bar("%s · solo lectura" % DV.DOC_KIND.get(ext, "Documento"), toggle=False))
            if size > DV.MAX_DOC:
                v.addWidget(self._note("Es muy grande para verlo aquí (%s). Ábrelo con su programa." % _human(size)), 1)
                return
            self.preview = DV.web_preview() if ext == ".pdf" else None
            if self.preview is not None:                 # si el visor de PDF no puede con él, se muestra su texto
                self.preview.loadFinished.connect(lambda ok_: ok_ or self._pdf_as_text())
            else:
                self.preview = DV.Reader(os.path.dirname(path))
                self.preview.open_file.connect(self.open_file.emit)
            v.addWidget(self.preview, 1)
            self.reload()
            return
        with open(path, "rb") as f:
            head = f.read(4096)
        if b"\0" in head or size > 3_000_000:
            self.kind = "none"
            v.addWidget(self._note("No se muestra: %s (%s)." % ("archivo binario" if b"\0" in head else "archivo demasiado grande", _human(size))), 1)
            return
        self.editor = CodeEditor()
        self.hl = Highlighter(self.editor.document(), ext if ext in LANG else os.path.basename(path).lower())
        if ext in DV.TEXT_PREVIEW:                           # texto con vista previa: Markdown, HTML, SVG, CSV
            self.kind = "text"
            if ext in (".md", ".markdown"):
                self.preview = DV.Reader(os.path.dirname(path))
                self.preview.open_file.connect(self.open_file.emit)
            elif ext in (".html", ".htm"):
                self.preview = DV.web_preview() or DV.Reader(os.path.dirname(path))
            elif ext == ".svg":
                self.preview = DV.ImageView()
            else:
                self.preview = DV.CsvView()
            v.addWidget(self._bar(DV.DOC_KIND.get(ext, ""), toggle=True))
            self.stack = QStackedWidget()
            self.stack.addWidget(self.preview)
            self.stack.addWidget(self.editor)
            v.addWidget(self.stack, 1)
            modes = core.SET.snapshot().get("preview_modes") or {}
            self.mode = modes.get(ext) or ("preview" if ext in (".md", ".markdown", ".csv") else "code")
        else:
            self.kind = "code"
            v.addWidget(self.editor)
        self.reload()
        self.editor.textChanged.connect(self._edited)
        if self.stack is not None:
            self.set_mode(self.mode, save=False)

    def _pdf_as_text(self):
        if isinstance(self.preview, self.DV.Reader):
            return
        old = self.preview
        self.preview = self.DV.Reader(os.path.dirname(self.path))
        self.v.replaceWidget(old, self.preview)
        old.hide()
        old.deleteLater()
        self.render_preview()

    # ---- barra de arriba y modos
    def _open_btn(self):
        b = QToolButton()
        b.setObjectName("chip")
        b.setIcon(icon("acc_abrir_externo", C["mut"], 13))
        b.setText("Abrir con su programa")
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip("Abrirlo con el programa del sistema (Word, Excel, el visor de imágenes…)")
        b.clicked.connect(lambda: osys.open_path(self.path))
        return b

    def _note(self, text):
        l = lbl(text, "muted")
        l.setAlignment(Qt.AlignCenter)
        l.setWordWrap(True)
        return l

    def _bar(self, label, toggle):
        bar = QWidget()
        bar.setObjectName("fileBar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        h = QHBoxLayout(bar)
        h.setContentsMargins(12, 4, 8, 4)
        h.setSpacing(6)
        k = QLabel(label)
        k.setObjectName("faint")
        h.addWidget(k)
        h.addStretch(1)
        if toggle:
            seg = QFrame()
            seg.setObjectName("segment")
            sh = QHBoxLayout(seg)
            sh.setContentsMargins(3, 3, 3, 3)
            sh.setSpacing(2)
            self.b_prev, self.b_code = QPushButton("Vista previa"), QPushButton("Código")
            for b, m in ((self.b_prev, "preview"), (self.b_code, "code")):
                b.setObjectName("segBtn")
                b.setCheckable(True)
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, m=m: self.set_mode(m))
                sh.addWidget(b)
            self.b_prev.setToolTip("Ver el archivo ya formateado")
            self.b_code.setToolTip("Ver y editar el texto del archivo")
            h.addWidget(seg)
        h.addWidget(self._open_btn())
        return bar

    def set_mode(self, mode, save=True):
        """«Vista previa» o «Código» (se recuerda para ese tipo de archivo)."""
        if self.stack is None:
            return
        self.mode = mode
        self.b_prev.setChecked(mode == "preview")
        self.b_code.setChecked(mode == "code")
        self.stack.setCurrentWidget(self.preview if mode == "preview" else self.editor)
        if mode == "preview":
            self.render_preview()
        else:
            self.editor.setFocus()
        if save:
            modes = dict(core.SET.snapshot().get("preview_modes") or {})
            modes[self.ext] = mode
            core.SET.update({"preview_modes": modes})

    def render_preview(self):
        """Dibuja la vista previa con lo último (el texto del editor, aunque no esté guardado, o el archivo)."""
        DV, p, ext = self.DV, self.preview, self.ext
        if p is None:
            return
        try:
            if self.kind == "image":
                pm = QPixmap(self.path)
                try:
                    size = _human(os.path.getsize(self.path))
                except OSError:
                    size = ""
                p.set_pixmap(pm, "%d × %d · %s" % (pm.width(), pm.height(), size) if not pm.isNull() else "")
            elif self.kind == "doc":
                if isinstance(p, DV.Reader):
                    p.show_html(DV.document_html(self.path))
                elif p.url().isEmpty() or p.url().toLocalFile() != self.path:
                    p.load(QUrl.fromLocalFile(self.path))
                else:
                    p.reload()
            else:
                text = self.editor.toPlainText()
                if ext in (".md", ".markdown"):
                    p.show_markdown(text)
                elif ext in (".html", ".htm"):
                    if isinstance(p, DV.Reader):
                        p.show_html(text)
                    else:
                        p.setHtml(text, QUrl.fromLocalFile(os.path.dirname(self.path).rstrip("\\/") + "/"))
                elif ext == ".svg":
                    p.set_svg(text.encode("utf-8"))
                else:
                    p.show_text(text)
            self._stale = False
        except Exception as e:                                # documento dañado o formato raro: se dice, no se rompe
            msg = "No pude mostrar la vista previa: %s" % e
            if isinstance(p, DV.Reader):
                p.show_html("<p><i>%s</i></p>" % DV.esc(msg))
            elif hasattr(p, "info"):
                p.info.setText(msg)

    def reload(self):
        if not self.editor:
            if self.preview is not None:
                self.render_preview()
            return
        with open(self.path, "r", encoding="utf-8", errors="replace", newline="") as f:
            text = f.read()
        self._loading = True
        pos = self.editor.textCursor().position()
        sb = self.editor.verticalScrollBar().value()
        hb = self.editor.horizontalScrollBar().value()
        self.editor.setPlainText(text)
        c = self.editor.textCursor()
        c.setPosition(min(pos, len(text)))
        self.editor.setTextCursor(c)
        self.editor.verticalScrollBar().setValue(sb)
        self.editor.horizontalScrollBar().setValue(hb)      # al recargar (cambios del agente) no se pierde la posición
        self._loading = False
        self.dirty = False
        self.changed.emit()
        if self.stack is not None and self.mode == "preview":   # el agente cambió el archivo: la vista previa también
            self.render_preview()

    def _edited(self):
        if not self._loading and not self.dirty:
            self.dirty = True
            self.changed.emit()

    def save(self):
        if not self.editor:
            return True
        with open(self.path, "w", encoding="utf-8", newline="") as f:
            f.write(self.editor.toPlainText())
        self.dirty = False
        self.changed.emit()
        return True


def _human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return ("%d %s" if u == "B" else "%.1f %s") % (n, u)
        n /= 1024


class EditorTabs(QTabWidget):
    def __init__(self):
        super().__init__()
        self.setMovable(True)
        self.setDocumentMode(True)
        self.watch = QFileSystemWatcher(self)
        self.watch.fileChanged.connect(self._external)
        self.welcome = lbl("Abre un archivo del árbol o pide al agente que cree uno.\nLos cambios del agente aparecen aquí al instante.", "muted")
        self.welcome.setAlignment(Qt.AlignCenter)
        self.addTab(self.welcome, "Inicio")
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_current)
        QShortcut(QKeySequence("Ctrl+W"), self, activated=lambda: self.close_tab(self.currentIndex()))
        # ajustar las líneas largas al ancho (se recuerda); Alt+Z como en otros editores
        self.wrap = bool(core.SET.snapshot().get("editor_wrap", False))
        self.b_wrap = QToolButton()
        self.b_wrap.setCheckable(True)
        self.b_wrap.setChecked(self.wrap)
        self.b_wrap.setIcon(icon("uij_alinear_izq", C["mut"], 14))
        self.b_wrap.setText("Ajustar líneas")
        self.b_wrap.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.b_wrap.setObjectName("chip")
        self.b_wrap.setCursor(Qt.PointingHandCursor)
        self.b_wrap.setToolTip("Ajustar las líneas largas al ancho del editor, sin desplazarse de lado  ·  Alt+Z\n"
                               "(sin ajustar: barra de abajo o Mayús + rueda para ver el final de cada línea)")
        self.b_wrap.toggled.connect(self.set_wrap)
        self.setCornerWidget(self.b_wrap, Qt.TopRightCorner)
        QShortcut(QKeySequence("Alt+Z"), self, activated=self.b_wrap.toggle)

    def set_wrap(self, on):
        self.wrap = bool(on)
        if self.b_wrap.isChecked() != self.wrap:
            self.b_wrap.setChecked(self.wrap)
        for t in self.tabs():
            if t.editor is not None:
                t.editor.set_wrap(self.wrap)
        core.SET.update({"editor_wrap": self.wrap})

    def tabs(self):
        return [self.widget(i) for i in range(self.count()) if isinstance(self.widget(i), FileTab)]

    def open(self, path, focus=True):
        path = os.path.normpath(path)
        if not os.path.isfile(path):
            return
        for t in self.tabs():
            if os.path.normcase(t.path) == os.path.normcase(path):
                if focus:
                    self.setCurrentWidget(t)
                return t
        try:
            t = FileTab(path)
        except OSError as e:
            QMessageBox.warning(self, "No se pudo abrir", str(e))
            return
        if self.indexOf(self.welcome) >= 0:
            self.removeTab(self.indexOf(self.welcome))
        if t.editor is not None:
            t.editor.set_wrap(self.wrap)
        t.open_file.connect(lambda p: self.open(p))           # enlaces de la vista previa a otros archivos
        i = self.addTab(t, os.path.basename(path))
        self.setTabToolTip(i, path)
        x = QToolButton()
        x.setIcon(icon("ui_cerrar", C["faint"], 9))
        x.setFixedSize(18, 18)
        x.setToolTip("Cerrar (Ctrl+W)")
        x.clicked.connect(lambda _=False, t=t: self.close_tab(self.indexOf(t)))
        self.tabBar().setTabButton(i, self.tabBar().ButtonPosition.RightSide, x)
        t.changed.connect(lambda t=t: self._title(t))
        self.watch.addPath(path)
        if focus:
            self.setCurrentIndex(i)
        return t

    def _title(self, t):
        i = self.indexOf(t)
        if i >= 0:
            self.setTabText(i, ("● " if t.dirty else "") + os.path.basename(t.path))

    def _external(self, path):
        for t in self.tabs():
            if os.path.normcase(t.path) == os.path.normcase(path):
                if not os.path.exists(path):
                    continue
                if t.dirty:
                    if QMessageBox.question(self, "Archivo modificado", "«%s» cambió fuera del editor (¿el agente?). ¿Recargarlo y perder tus cambios sin guardar?"
                                            % os.path.basename(path)) != QMessageBox.StandardButton.Yes:
                        continue
                t.reload()
        if os.path.exists(path) and path not in self.watch.files():
            self.watch.addPath(path)     # algunos editores reemplazan el archivo: volver a vigilarlo

    def refresh(self, path):
        """El agente escribio o edito este archivo: abrirlo o recargarlo."""
        t = self.open(path, focus=True)
        if t:
            QTimer.singleShot(150, t.reload)

    def save_current(self):
        w = self.currentWidget()
        if isinstance(w, FileTab):
            w.save()

    def close_tab(self, i):
        w = self.widget(i)
        if not isinstance(w, FileTab):
            return
        if w.dirty:
            r = QMessageBox.question(self, "Cambios sin guardar", "¿Guardar «%s» antes de cerrarlo?" % os.path.basename(w.path),
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel:
                return
            if r == QMessageBox.StandardButton.Save:
                w.save()
        self.watch.removePath(w.path)
        self.removeTab(i)
        w.deleteLater()
        if not self.tabs():
            self.addTab(self.welcome, "Inicio")

    def close_all(self):
        for t in self.tabs():
            if t.dirty:
                t.save()
        while self.tabs():
            self.close_tab(self.indexOf(self.tabs()[0]))

    def has_dirty(self):
        return any(t.dirty for t in self.tabs())


# ---------------------------------------------------------------- arbol de archivos
from .explorer import FileTree   # el explorador vive en explorer.py (iconos, guías, «Ir a un archivo»)


# ---------------------------------------------------------------- terminal
MARK = "__JAYTH_CWD__"


class Terminal(QWidget):
    """Terminal persistente del sistema (PowerShell en Windows, zsh/bash en macOS y Linux) (el cd y las variables se conservan entre comandos).
    Pensada para comandos; los programas interactivos que esperan teclado no funcionan aqui."""

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(10, 4, 6, 4)
        t = QLabel("TERMINAL")
        t.setObjectName("faint")
        bar.addWidget(t)
        bar.addStretch(1)
        for ico, tip, cb in (("trans_detener", "Detener el comando (reinicia la sesión)", self.restart), ("acc_eliminar", "Limpiar", lambda: self.out.clear())):
            b = QToolButton()
            b.setIcon(icon(ico, C["mut"], 14))
            b.setToolTip(tip)
            b.clicked.connect(cb)
            bar.addWidget(b)
        v.addLayout(bar)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setFont(MONO)
        self.out.setMaximumBlockCount(5000)
        self.out.setStyleSheet("QPlainTextEdit { background: %s; border: none; border-radius: 0; padding: 6px 10px; font-family: %s; font-size: 9.5pt; }" % (C["code"], MONO_CSS))
        v.addWidget(self.out, 1)
        row = QHBoxLayout()
        row.setContentsMargins(10, 4, 10, 6)
        self.prompt = QLabel(">")
        self.prompt.setFont(MONO)
        self.prompt.setStyleSheet("color:%s; font-family: %s; font-size: 9.5pt;" % (C["acc"], MONO_CSS))
        row.addWidget(self.prompt)
        self.inp = QLineEdit()
        self.inp.setFont(MONO)
        self.inp.setPlaceholderText("Escribe un comando y pulsa Enter (↑ ↓ historial)")
        self.inp.setStyleSheet("QLineEdit { background: transparent; border: none; font-family: %s; font-size: 9.5pt; }" % MONO_CSS)
        self.inp.returnPressed.connect(self.run_input)
        self.inp.installEventFilter(self)
        row.addWidget(self.inp, 1)
        v.addLayout(row)
        self.hist, self.hi = [], 0
        self.cwd = os.path.expanduser("~")
        self.proc = None
        self._buf = ""

    def eventFilter(self, obj, e):
        from PySide6.QtCore import QEvent
        if obj is self.inp and e.type() == QEvent.KeyPress and self.hist:
            if e.key() == Qt.Key_Up:
                self.hi = max(0, self.hi - 1)
                self.inp.setText(self.hist[self.hi])
                return True
            if e.key() == Qt.Key_Down:
                self.hi = min(len(self.hist), self.hi + 1)
                self.inp.setText(self.hist[self.hi] if self.hi < len(self.hist) else "")
                return True
        return super().eventFilter(obj, e)

    def start(self, cwd):
        self.stop()
        self.cwd = cwd
        if not getattr(self, "root", None) or not os.path.normcase(cwd).startswith(os.path.normcase(self.root)):
            self.root = cwd
        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(cwd)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        from PySide6.QtCore import QProcessEnvironment
        env = QProcessEnvironment.systemEnvironment()
        env.insert("TERM", "dumb")                     # sin colores ANSI ni paginadores
        env.insert("PAGER", "cat")
        env.insert("GIT_PAGER", "cat")
        self.proc.setProcessEnvironment(env)
        argv = osys.interactive_shell_argv()
        self.proc.start(argv[0], argv[1:])
        self.proc.waitForStarted(3000)
        if osys.WIN:
            self._send("[Console]::OutputEncoding=[Text.Encoding]::UTF8; $OutputEncoding=[Text.Encoding]::UTF8; $ProgressPreference='SilentlyContinue'")
        self._send(self._mark_cmd())
        self._update_prompt()

    def stop(self):
        if self.proc is not None:
            self.proc.kill()
            self.proc.waitForFinished(1500)
            self.proc = None

    def restart(self):
        self.out.appendPlainText("^C  (sesión reiniciada)")
        self.start(self.cwd)

    def _send(self, line):
        if self.proc is not None:
            self.proc.write((line + "\n").encode("utf-8"))

    def run_input(self):
        cmd = self.inp.text()
        self.inp.clear()
        self.run(cmd)

    def run(self, cmd):
        if not cmd.strip():
            return
        if self.proc is None or self.proc.state() != QProcess.Running:
            self.start(self.cwd)
        self.hist.append(cmd)
        self.hi = len(self.hist)
        self.out.appendHtml("<span style='color:%s'>%s&gt;</span> %s" % (C["acc"], self._short().replace("<", "&lt;"), cmd.replace("<", "&lt;")))
        if cmd.strip().lower() in ("cls", "clear"):
            self.out.clear()
            return
        if osys.WIN:
            # ". { }" ejecuta en el ambito actual: las variables y el cd se conservan; Out-String vuelca la salida antes de la marca
            self._send(". { %s } 2>&1 | Out-String -Width 200" % cmd)
        else:
            self._send("{ %s\n} 2>&1 </dev/null" % cmd)
        self._send(self._mark_cmd())

    @staticmethod
    def _mark_cmd():
        return ("Write-Output \"%s$($PWD.Path)\"" if osys.WIN else "printf '%s%%s\\n' \"$PWD\"") % MARK

    def _read(self):
        self._buf += bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        lines = self._buf.split("\n")
        self._buf = lines.pop()
        for l in lines:
            l = l.rstrip("\r")
            if MARK in l:                                  # la marca puede quedar pegada a una salida sin salto final
                before, _, after = l.partition(MARK)
                if before:
                    self.out.appendPlainText(before)
                self.cwd = after.strip() or self.cwd
                self._update_prompt()
            else:
                self.out.appendPlainText(l)
        self.out.verticalScrollBar().setValue(self.out.verticalScrollBar().maximum())

    def _short(self):
        """Ruta corta para el prompt: relativa a la raiz del proyecto si esta dentro."""
        root = getattr(self, "root", "") or ""
        if root and os.path.normcase(self.cwd).startswith(os.path.normcase(root)):
            rel = os.path.relpath(self.cwd, root)
            return os.path.basename(root) + ("" if rel == "." else os.sep + rel)
        return self.cwd if len(self.cwd) < 40 else "…" + self.cwd[-38:]

    def _update_prompt(self):
        self.prompt.setText("%s>" % self._short())


# ---------------------------------------------------------------- dialogo de proyecto
class ProjectDialog(QDialog):
    def __init__(self, parent=None, proj=None):
        super().__init__(parent)
        self.setWindowTitle("Editar proyecto" if proj else "Nuevo proyecto")
        self.resize(560, 360)
        self.proj = proj
        v = QVBoxLayout(self)
        v.addWidget(lbl("Editar proyecto" if proj else "Nuevo proyecto", "h1"))
        v.addWidget(lbl("El agente trabajará dentro de la carpeta del proyecto y seguirá sus instrucciones.", "muted"))
        f = QFormLayout()
        self.name = QLineEdit(proj["name"] if proj else "")
        self.name.setPlaceholderText("Mi app de notas")
        f.addRow("Nombre:", self.name)
        self.r_new = QRadioButton("Crear una carpeta nueva en Documentos\\Jayth\\Proyectos")
        self.r_old = QRadioButton("Usar una carpeta existente")
        g = QButtonGroup(self)
        g.addButton(self.r_new)
        g.addButton(self.r_old)
        self.path = QLineEdit(proj["path"] if proj else "")
        if proj:
            self.r_old.setChecked(True)
            self.r_new.setEnabled(False)
        else:
            self.r_new.setChecked(True)
        f.addRow(self.r_new)
        f.addRow(self.r_old)
        f.addRow("Carpeta:", browse_row(self.path, folder=True, parent=self))
        self.instr = QPlainTextEdit(proj.get("instructions", "") if proj else "")
        self.instr.setPlaceholderText("Ej.: Es una app web en React con TypeScript. Usa pnpm. Escribe pruebas para cada función nueva.")
        self.instr.setFixedHeight(90)
        f.addRow("Instrucciones:", self.instr)
        v.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Guardar" if proj else "Crear proyecto")
        bb.button(QDialogButtonBox.Ok).setProperty("kind", "primary")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.r_new.toggled.connect(lambda on: self.path.setEnabled(not on))
        self.path.setEnabled(not self.r_new.isChecked())
        self.result_project = None

    def _ok(self):
        name = self.name.text().strip()
        if self.r_new.isChecked():
            if not name:
                return QMessageBox.warning(self, "Falta el nombre", "Escribe un nombre para el proyecto.")
            path = os.path.join(paths.WORKSPACE_DEFAULT, "Proyectos", re.sub(r'[<>:"/\\|?*]+', "_", name))
        else:
            path = self.path.text().strip()
            if not path:
                return QMessageBox.warning(self, "Falta la carpeta", "Elige la carpeta del proyecto.")
            name = name or os.path.basename(os.path.normpath(path))
        if self.proj:
            core.SET.update_project(self.proj["id"], name=name, path=os.path.normpath(path), instructions=self.instr.toPlainText())
            self.result_project = core.project(core.SET.snapshot(), self.proj["id"])
        else:
            self.result_project = core.SET.add_project(name, path, self.instr.toPlainText())
        self.accept()
