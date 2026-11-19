"""Piezas del modo Jayth Code: editor con resaltado, pestañas, arbol de archivos, terminal y dialogo de proyecto."""
import os, re, json, time, uuid
from PySide6.QtCore import Qt, QRect, QSize, Signal, QFileSystemWatcher, QProcess, QDir, QModelIndex, QTimer
from PySide6.QtGui import (QColor, QFont, QPainter, QTextFormat, QSyntaxHighlighter, QTextCharFormat, QKeySequence, QShortcut,
                           QPixmap, QGuiApplication, QTextCursor, QDesktopServices)
from PySide6.QtWidgets import (QWidget, QPlainTextEdit, QTextEdit, QTabWidget, QTreeView, QFileSystemModel, QVBoxLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMenu, QMessageBox, QInputDialog, QDialog, QFormLayout, QFileDialog, QHeaderView,
                               QAbstractItemView, QScrollArea, QToolButton, QPushButton, QDialogButtonBox, QRadioButton, QButtonGroup)
from . import core, paths
from .theme import C, icon, pix
from .wizard import btn, lbl, browse_row

MONO = QFont("Consolas", 10)
MONO.setStyleHint(QFont.Monospace)
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
    def __init__(self):
        super().__init__()
        self.setFont(MONO)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setStyleSheet("QPlainTextEdit { background: %s; border: none; border-radius: 0; padding: 0; font-family: Consolas; font-size: 10pt; }" % C["bg"])
        self.gutter = _Gutter(self)
        self.gutter.setFont(MONO)
        self.blockCountChanged.connect(lambda _: self.setViewportMargins(self.gutter_width(), 0, 0, 0))
        self.updateRequest.connect(self._upd)
        self.cursorPositionChanged.connect(self._hl_line)
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)
        self._hl_line()

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
    changed = Signal()

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.dirty = False
        self._loading = False
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        ext = os.path.splitext(path)[1].lower()
        self.editor = None
        if ext in IMG_EXT:
            sc = QScrollArea()
            im = QLabel()
            im.setAlignment(Qt.AlignCenter)
            im.setPixmap(QPixmap(path))
            sc.setWidget(im)
            sc.setWidgetResizable(True)
            v.addWidget(sc)
            return
        size = os.path.getsize(path) if os.path.isfile(path) else 0
        with open(path, "rb") as f:
            head = f.read(4096)
        if b"\0" in head or size > 3_000_000:
            l = lbl("No se muestra: %s (%s)." % ("archivo binario" if b"\0" in head else "archivo demasiado grande", _human(size)), "muted")
            l.setAlignment(Qt.AlignCenter)
            v.addWidget(l)
            return
        self.editor = CodeEditor()
        self.hl = Highlighter(self.editor.document(), ext if ext in LANG else os.path.basename(path).lower())
        v.addWidget(self.editor)
        self.reload()
        self.editor.textChanged.connect(self._edited)

    def reload(self):
        if not self.editor:
            return
        with open(self.path, "r", encoding="utf-8", errors="replace", newline="") as f:
            text = f.read()
        self._loading = True
        pos = self.editor.textCursor().position()
        sb = self.editor.verticalScrollBar().value()
        self.editor.setPlainText(text)
        c = self.editor.textCursor()
        c.setPosition(min(pos, len(text)))
        self.editor.setTextCursor(c)
        self.editor.verticalScrollBar().setValue(sb)
        self._loading = False
        self.dirty = False
        self.changed.emit()

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
class FileTree(QTreeView):
    open_file = Signal(str)

    def __init__(self):
        super().__init__()
        self.model_ = QFileSystemModel(self)
        self.model_.setReadOnly(False)
        self.model_.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot | QDir.Hidden)
        self.setModel(self.model_)
        for c in (1, 2, 3):
            self.hideColumn(c)
        self.setHeaderHidden(True)
        self.setAnimated(True)
        self.setIndentation(14)
        self.setEditTriggers(QAbstractItemView.EditKeyPressed)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.doubleClicked.connect(self._dbl)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.setStyleSheet("QTreeView { background: %s; border: none; } QTreeView::item { padding: 3px 2px; border-radius: 5px; }"
                           "QTreeView::item:selected { background: %s; color: %s; } QTreeView::item:hover:!selected { background: %s; }"
                           % (C["side"], C["panel2"], C["tx"], C["hover"]))
        self.root = ""

    def set_root(self, path):
        self.root = path
        idx = self.model_.setRootPath(path)
        self.setRootIndex(idx)

    def _path(self, idx):
        return self.model_.filePath(idx) if idx.isValid() else self.root

    def _dbl(self, idx):
        p = self._path(idx)
        if os.path.isfile(p):
            self.open_file.emit(p)

    def _menu(self, pos):
        idx = self.indexAt(pos)
        p = self._path(idx)
        folder = p if os.path.isdir(p) else os.path.dirname(p)
        m = QMenu(self)
        a_file = m.addAction(icon("acc_nuevo"), "Nuevo archivo…")
        a_dir = m.addAction(icon("act_carpeta"), "Nueva carpeta…")
        m.addSeparator()
        a_ren = m.addAction(icon("acc_renombrar"), "Renombrar") if idx.isValid() else None
        a_copy = m.addAction(icon("acc_copiar"), "Copiar ruta")
        a_os = m.addAction(icon("act_carpeta_abierta"), "Mostrar en el Explorador")
        m.addSeparator()
        a_del = m.addAction(icon("acc_eliminar", C["bad"]), "Mover a la papelera") if idx.isValid() else None
        a = m.exec(self.viewport().mapToGlobal(pos))
        if a is None:
            return
        if a == a_file:
            n, ok = QInputDialog.getText(self, "Nuevo archivo", "Nombre:")
            if ok and n.strip():
                fp = os.path.join(folder, n.strip())
                if not os.path.exists(fp):
                    os.makedirs(os.path.dirname(fp), exist_ok=True)
                    open(fp, "w", encoding="utf-8").close()
                self.open_file.emit(fp)
        elif a == a_dir:
            n, ok = QInputDialog.getText(self, "Nueva carpeta", "Nombre:")
            if ok and n.strip():
                os.makedirs(os.path.join(folder, n.strip()), exist_ok=True)
        elif a == a_ren:
            self.edit(idx)
        elif a == a_copy:
            QGuiApplication.clipboard().setText(p)
        elif a == a_os:
            os.startfile(folder)
        elif a == a_del:
            if QMessageBox.question(self, "Mover a la papelera", "¿Mover «%s» a la papelera de reciclaje?" % os.path.basename(p)) == QMessageBox.StandardButton.Yes:
                from PySide6.QtCore import QFile
                if not QFile.moveToTrash(p):
                    QMessageBox.warning(self, "No se pudo", "No se pudo mover a la papelera.")


# ---------------------------------------------------------------- terminal
MARK = "__JAYTH_CWD__"


class Terminal(QWidget):
    """Terminal de PowerShell persistente (el cd y las variables se conservan entre comandos).
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
        self.out.setStyleSheet("QPlainTextEdit { background: %s; border: none; border-radius: 0; padding: 6px 10px; font-family: Consolas; font-size: 9.5pt; }" % C["code"])
        v.addWidget(self.out, 1)
        row = QHBoxLayout()
        row.setContentsMargins(10, 4, 10, 6)
        self.prompt = QLabel("PS>")
        self.prompt.setFont(MONO)
        self.prompt.setStyleSheet("color:%s; font-family: Consolas; font-size: 9.5pt;" % C["acc"])
        row.addWidget(self.prompt)
        self.inp = QLineEdit()
        self.inp.setFont(MONO)
        self.inp.setPlaceholderText("Escribe un comando y pulsa Enter (↑ ↓ historial)")
        self.inp.setStyleSheet("QLineEdit { background: transparent; border: none; font-family: Consolas; font-size: 9.5pt; }")
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
        self.proc.start("powershell.exe", ["-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "-"])
        self.proc.waitForStarted(3000)
        self._send("[Console]::OutputEncoding=[Text.Encoding]::UTF8; $OutputEncoding=[Text.Encoding]::UTF8; $ProgressPreference='SilentlyContinue'")
        self._send("Write-Output \"%s$($PWD.Path)\"" % MARK)
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
        # ". { }" ejecuta en el ambito actual: las variables y el cd se conservan; Out-String vuelca la salida antes de la marca
        self._send(". { %s } 2>&1 | Out-String -Width 200" % cmd)
        self._send("Write-Output \"%s$($PWD.Path)\"" % MARK)

    def _read(self):
        self._buf += bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        lines = self._buf.split("\n")
        self._buf = lines.pop()
        for l in lines:
            l = l.rstrip("\r")
            if l.startswith(MARK):
                self.cwd = l[len(MARK):].strip() or self.cwd
                self._update_prompt()
            else:
                self.out.appendPlainText(l)
        self.out.verticalScrollBar().setValue(self.out.verticalScrollBar().maximum())

    def _short(self):
        """Ruta corta para el prompt: relativa a la raiz del proyecto si esta dentro."""
        root = getattr(self, "root", "") or ""
        if root and os.path.normcase(self.cwd).startswith(os.path.normcase(root)):
            rel = os.path.relpath(self.cwd, root)
            return os.path.basename(root) + ("" if rel == "." else "\\" + rel)
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
