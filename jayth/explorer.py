# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Explorador de archivos de Jayth Code.

- Iconos por tipo de archivo (etiquetas de color: PY, JS, TS, {}, M↓, <>, W, X, P, PDF…), carpetas que se abren al
  desplegarlas y carpetas pesadas o internas (node_modules, .git, build…) atenuadas.
- Guías de sangría y flechas propias; filas con aire y selección redondeada.
- «Ir a un archivo…» (Ctrl+P): escribe parte del nombre y salta a él.
- Lo que el agente acaba de cambiar lleva un punto verde (también la carpeta que lo contiene).
- El archivo abierto en el editor se resalta en el árbol.
"""
import os, time
from PySide6.QtCore import Qt, Signal, QDir, QRect, QRectF, QSize, QStringListModel, QTimer
from PySide6.QtGui import QPainter, QColor, QPixmap, QFont, QPen, QPainterPath, QIcon, QPalette, QGuiApplication
from PySide6.QtWidgets import (QTreeView, QFileSystemModel, QStyledItemDelegate, QAbstractItemView, QMenu, QInputDialog, QMessageBox,
                               QLineEdit, QCompleter, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QStyle)
from . import osys
from .theme import C, icon, pix
from .i18n import tr

DIM_DIRS = {"node_modules", ".git", "__pycache__", "dist", "build", ".venv", "venv", "env", ".idea", ".vscode", ".next", ".cache",
            ".pytest_cache", ".mypy_cache", "target", "bin", "obj", ".gradle", "coverage", ".parcel-cache", ".turbo"}
SKIP_SCAN = DIM_DIRS - {"dist", "build", "bin"}          # «Ir a un archivo» no entra en estas

# etiqueta y color de cada tipo de archivo
BADGE = {
    ".py": ("PY", "#3776AB"), ".pyw": ("PY", "#3776AB"), ".ipynb": ("NB", "#F37626"),
    ".js": ("JS", "#C9A400"), ".mjs": ("JS", "#C9A400"), ".cjs": ("JS", "#C9A400"), ".jsx": ("JSX", "#149ECA"),
    ".ts": ("TS", "#3178C6"), ".tsx": ("TSX", "#3178C6"), ".vue": ("V", "#41B883"), ".svelte": ("S", "#FF3E00"),
    ".json": ("{}", "#C69026"), ".md": ("M↓", "#4A90D9"), ".markdown": ("M↓", "#4A90D9"),
    ".html": ("<>", "#E44D26"), ".htm": ("<>", "#E44D26"), ".xml": ("<>", "#8A8F98"), ".svg": ("◇", "#E8A33D"),
    ".css": ("#", "#2965F1"), ".scss": ("#", "#C6538C"), ".less": ("#", "#1D365D"),
    ".sh": (">_", "#4EAA25"), ".bash": (">_", "#4EAA25"), ".zsh": (">_", "#4EAA25"), ".ps1": (">_", "#2671BE"),
    ".bat": (">_", "#7A7A7A"), ".cmd": (">_", "#7A7A7A"),
    ".yml": ("YML", "#CB171E"), ".yaml": ("YML", "#CB171E"), ".toml": ("⚙", "#9C4221"), ".ini": ("⚙", "#8A8F98"),
    ".cfg": ("⚙", "#8A8F98"), ".env": ("⚙", "#ECD53F"), ".lock": ("🔒", "#8A8F98"),
    ".txt": ("≡", "#8A8F98"), ".log": ("≡", "#8A8F98"), ".csv": ("▦", "#2E8F62"), ".sql": ("SQL", "#E38C00"),
    ".docx": ("W", "#2B579A"), ".docm": ("W", "#2B579A"), ".xlsx": ("X", "#217346"), ".xlsm": ("X", "#217346"),
    ".pptx": ("P", "#C43E1C"), ".pdf": ("PDF", "#B3261E"),
    ".c": ("C", "#5C6BC0"), ".h": ("H", "#7E57C2"), ".cpp": ("C++", "#00599C"), ".hpp": ("H++", "#00599C"), ".cs": ("C#", "#68217A"),
    ".java": ("J", "#E76F00"), ".kt": ("KT", "#7F52FF"), ".go": ("GO", "#00ADD8"), ".rs": ("RS", "#CE422B"), ".php": ("PHP", "#777BB4"),
    ".rb": ("RB", "#CC342D"), ".lua": ("LUA", "#2C2D72"), ".gd": ("GD", "#478CBF"), ".swift": ("SW", "#F05138"), ".dart": ("DT", "#0175C2"),
    ".r": ("R", "#276DC3"), ".zip": ("ZIP", "#8A8F98"), ".7z": ("7Z", "#8A8F98"), ".rar": ("RAR", "#8A8F98"), ".exe": ("EXE", "#607068"),
    ".msi": ("MSI", "#607068"), ".gguf": (tr("IA"), "#52B788"), ".ttf": ("Aa", "#8A8F98"), ".otf": ("Aa", "#8A8F98"), ".woff2": ("Aa", "#8A8F98"),
    ".mp3": ("♪", "#8E44AD"), ".wav": ("♪", "#8E44AD"), ".mp4": ("▶", "#C0392B"), ".mov": ("▶", "#C0392B"),
}
NAMES = {".gitignore": ("GIT", "#F05032"), ".gitattributes": ("GIT", "#F05032"), "package.json": ("npm", "#CB3837"),
         "package-lock.json": ("npm", "#8A8F98"), "dockerfile": ("DK", "#2496ED"), "license": ("©", "#C69026"), "license.md": ("©", "#C69026"),
         "requirements.txt": ("PY", "#3776AB"), "makefile": ("MK", "#6D8086"), "readme.md": ("i", "#4A90D9"), "jayth.md": ("J", "#52B788"),
         "vite.config.ts": ("⚡", "#9E6CFF"), "vite.config.js": ("⚡", "#9E6CFF"), "tsconfig.json": ("TS", "#3178C6")}
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico"}

_CACHE = {}


def _dpr():
    s = QGuiApplication.primaryScreen()
    return max(1.0, s.devicePixelRatio() if s else 1.0)


def _badge(text, color, size=16):
    key = ("b", text, color, size)
    if key in _CACHE:
        return _CACHE[key]
    dpr = _dpr()
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(0.5, 1.5, size - 1, size - 3), 3.2, 3.2)
    f = QFont()
    f.setBold(True)
    f.setPixelSize({1: 10, 2: 8}.get(len(text), 6))
    p.setFont(f)
    light = QColor(color).lightnessF() > 0.62
    p.setPen(QColor("#1B1F1D") if light else QColor("#FFFFFF"))
    p.drawText(QRectF(0, 1, size, size - 2), Qt.AlignCenter, text)
    p.end()
    ic = QIcon(pm)
    _CACHE[key] = ic
    return ic


def _page(size=16):
    """Archivo sin tipo conocido: una hoja con la esquina doblada."""
    key = ("page", C["mut"], size)
    if key in _CACHE:
        return _CACHE[key]
    dpr = _dpr()
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(C["mut"]), 1.2))
    path = QPainterPath()
    path.moveTo(3.5, 1.5)
    path.lineTo(9.5, 1.5)
    path.lineTo(13, 5)
    path.lineTo(13, 14.5)
    path.lineTo(3.5, 14.5)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(9.5, 1.8, 9.5, 5)
    p.drawLine(9.5, 5, 12.7, 5)
    p.end()
    ic = QIcon(pm)
    _CACHE[key] = ic
    return ic


def file_icon(name):
    low = name.lower()
    ext = os.path.splitext(low)[1]
    if low in NAMES:
        return _badge(*NAMES[low])
    if low.startswith(".env"):
        return _badge(*BADGE[".env"])
    if ext in IMAGES:
        key = ("img", C["acc"])
        if key not in _CACHE:
            _CACHE[key] = QIcon(pix("uij_imagen", "#26A69A", 16))
        return _CACHE[key]
    if ext in BADGE:
        return _badge(*BADGE[ext])
    return _page()


def folder_icon(opened, dim=False):
    col = C["faint"] if dim else ("#D9A441" if C["bg"] < "#8" else "#B7862B")
    key = ("dir", opened, col)
    if key not in _CACHE:
        _CACHE[key] = QIcon(pix("act_carpeta_abierta" if opened else "act_carpeta", col, 16))
    return _CACHE[key]


class _Delegate(QStyledItemDelegate):
    def __init__(self, tree):
        super().__init__(tree)
        self.tree = tree

    def sizeHint(self, opt, idx):
        s = super().sizeHint(opt, idx)
        s.setHeight(max(s.height(), 25))
        return s

    def initStyleOption(self, opt, idx):
        super().initStyleOption(opt, idx)
        m = self.tree.model_
        name = m.fileName(idx)
        dim = m.isDir(idx) and (name in DIM_DIRS or name.startswith("."))     # carpetas pesadas o internas, más tenues
        if m.isDir(idx):
            opt.icon = folder_icon(self.tree.isExpanded(idx), dim)
        else:
            opt.icon = file_icon(name)
        opt.decorationSize = QSize(16, 16)
        changed = self.tree.is_changed(m.filePath(idx))
        if changed:
            opt.palette.setColor(QPalette.Text, QColor(C["acc"]))
        elif dim:
            opt.palette.setColor(QPalette.Text, QColor(C["faint"]))

    def paint(self, p, opt, idx):
        super().paint(p, opt, idx)
        if self.tree.is_changed(self.tree.model_.filePath(idx)):      # punto verde: lo cambió el agente hace poco
            p.save()
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C["acc"]))
            r = opt.rect
            p.drawEllipse(QRectF(r.right() - 12, r.center().y() - 3, 6, 6))
            p.restore()


class FileTree(QTreeView):
    open_file = Signal(str)
    RECENT = 15 * 60          # segundos que un archivo cambiado por el agente se queda marcado

    def __init__(self):
        super().__init__()
        self.setObjectName("fileTree")
        self.model_ = QFileSystemModel(self)
        self.model_.setReadOnly(False)
        self.model_.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot | QDir.Hidden)
        self.model_.setOption(QFileSystemModel.DontUseCustomDirectoryIcons, True)
        self.setModel(self.model_)
        for c in (1, 2, 3):
            self.hideColumn(c)
        self.setHeaderHidden(True)
        self.setAnimated(True)
        self.setIndentation(14)
        self.setIconSize(QSize(16, 16))
        self.setUniformRowHeights(True)
        self.setEditTriggers(QAbstractItemView.EditKeyPressed)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setItemDelegate(_Delegate(self))
        self.setExpandsOnDoubleClick(False)              # las carpetas se abren con un clic (ver _click)
        self.setMouseTracking(True)
        self._on_arrow = False
        self.doubleClicked.connect(self._dbl)
        self.clicked.connect(self._click)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.setStyleSheet(
            "QTreeView#fileTree { background: %(side)s; border: none; outline: 0; }"
            "QTreeView#fileTree::item { padding: 2px 4px; border-radius: 6px; margin: 0 4px 0 0; }"
            "QTreeView#fileTree::item:selected { background: %(acc_bg)s; color: %(tx)s; }"
            "QTreeView#fileTree::item:hover:!selected { background: %(hover)s; }"
            "QTreeView#fileTree::branch { background: transparent; image: none; border-image: none; }" % C)
        self.root = ""
        self.changed = {}
        self._chev = {o: pix("ui_chevron_abajo" if o else "ui_chevron_derecha", C["faint"], 9) for o in (True, False)}

    # ---- raíz y marcas
    def set_root(self, path):
        self.root = path
        idx = self.model_.setRootPath(path)
        self.setRootIndex(idx)

    def mark_changed(self, path):
        """El agente cambió este archivo: queda marcado un rato (y la carpeta que lo contiene)."""
        self.changed[os.path.normcase(os.path.abspath(path))] = time.time()
        self.viewport().update()

    def is_changed(self, path):
        if not self.changed or not path:
            return False
        now = time.time()
        p = os.path.normcase(os.path.abspath(path))
        t = self.changed.get(p)
        if t is not None:
            return now - t < self.RECENT
        pre = p.rstrip("\\/") + os.sep
        return any(k.startswith(pre) and now - v < self.RECENT for k, v in self.changed.items())

    def reveal(self, path):
        """Resalta en el árbol el archivo abierto en el editor."""
        idx = self.model_.index(path)
        if idx.isValid():
            self.setCurrentIndex(idx)
            self.scrollTo(idx)

    # ---- dibujo: guías de sangría y flechas propias
    def drawBranches(self, p, rect, idx):
        ind = self.indentation()
        depth, par = 0, idx.parent()
        while par.isValid() and par != self.rootIndex():
            depth += 1
            par = par.parent()
        p.save()
        guide = QColor(C["line"])
        for d in range(depth):
            x = rect.left() + d * ind + ind // 2 + 2
            p.fillRect(QRect(x, rect.top(), 1, rect.height()), guide)
        if self.model_.isDir(idx):
            pm = self._chev[self.isExpanded(idx)]
            w = pm.width() / (pm.devicePixelRatio() or 1)
            x = rect.left() + depth * ind + (ind - w) / 2 + 2
            p.drawPixmap(int(x), int(rect.center().y() - w / 2 + 1), pm)
        p.restore()

    # ---- acciones
    def _path(self, idx):
        return self.model_.filePath(idx) if idx.isValid() else self.root

    def mousePressEvent(self, e):
        idx = self.indexAt(e.position().toPoint())
        # en la flecha la abre o cierra Qt; en el nombre, _click (así no se cambia dos veces)
        self._on_arrow = idx.isValid() and e.position().x() < self.visualRect(idx).left()
        super().mousePressEvent(e)

    def _click(self, idx):
        if self.model_.isDir(idx) and not self._on_arrow:   # un clic en una carpeta la abre o la cierra
            self.setExpanded(idx, not self.isExpanded(idx))

    def _dbl(self, idx):
        p = self._path(idx)
        if os.path.isfile(p):
            self.open_file.emit(p)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and self.currentIndex().isValid():
            p = self._path(self.currentIndex())
            if os.path.isfile(p):
                self.open_file.emit(p)
                return
        super().keyPressEvent(e)

    def _target_dir(self):
        idx = self.currentIndex()
        p = self._path(idx) if idx.isValid() else self.root
        return p if os.path.isdir(p) else os.path.dirname(p)

    def new_file(self, folder=None):
        folder = folder or self._target_dir() or self.root
        n, ok = QInputDialog.getText(self, tr("Nuevo archivo"), tr("Nombre (puede incluir carpetas, p. ej. src/main.py):"))
        if ok and n.strip():
            fp = os.path.join(folder, n.strip())
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            if not os.path.exists(fp):
                open(fp, "w", encoding="utf-8").close()
            self.open_file.emit(fp)

    def new_folder(self, folder=None):
        folder = folder or self._target_dir() or self.root
        n, ok = QInputDialog.getText(self, tr("Nueva carpeta"), tr("Nombre:"))
        if ok and n.strip():
            os.makedirs(os.path.join(folder, n.strip()), exist_ok=True)
            idx = self.model_.index(folder)
            if idx.isValid():
                self.setExpanded(idx, True)

    def _menu(self, pos):
        idx = self.indexAt(pos)
        p = self._path(idx)
        folder = p if os.path.isdir(p) else os.path.dirname(p)
        m = QMenu(self)
        a_open = m.addAction(icon("pan_editor_codigo"), tr("Abrir")) if idx.isValid() and os.path.isfile(p) else None
        a_ext = m.addAction(icon("acc_abrir_externo"), tr("Abrir con su programa")) if idx.isValid() and os.path.isfile(p) else None
        if a_open:
            m.addSeparator()
        a_file = m.addAction(icon("acc_nuevo"), tr("Nuevo archivo…"))
        a_dir = m.addAction(icon("act_carpeta"), tr("Nueva carpeta…"))
        m.addSeparator()
        a_ren = m.addAction(icon("acc_renombrar"), tr("Renombrar")) if idx.isValid() else None
        a_copy = m.addAction(icon("acc_copiar"), tr("Copiar ruta"))
        a_rel = m.addAction(icon("acc_copiar"), tr("Copiar ruta relativa")) if idx.isValid() else None
        a_os = m.addAction(icon("act_carpeta_abierta"), tr("Mostrar en el Explorador") if osys.WIN else (tr("Mostrar en el Finder") if osys.MAC else tr("Abrir la carpeta")))
        m.addSeparator()
        a_del = m.addAction(icon("acc_eliminar", C["bad"]), tr("Mover a la papelera")) if idx.isValid() else None
        a = m.exec(self.viewport().mapToGlobal(pos))
        if a is None:
            return
        if a == a_open:
            self.open_file.emit(p)
        elif a == a_ext:
            osys.open_path(p)
        elif a == a_file:
            self.new_file(folder)
        elif a == a_dir:
            self.new_folder(folder)
        elif a == a_ren:
            self.edit(idx)
        elif a == a_copy:
            QGuiApplication.clipboard().setText(p)
        elif a == a_rel:
            QGuiApplication.clipboard().setText(os.path.relpath(p, self.root) if self.root else p)
        elif a == a_os:
            osys.reveal(p) if idx.isValid() else osys.open_path(folder)
        elif a == a_del:
            if QMessageBox.question(self, tr("Mover a la papelera"), tr("¿Mover «%s» a la papelera?") % os.path.basename(p)) == QMessageBox.StandardButton.Yes:
                from PySide6.QtCore import QFile
                if not QFile.moveToTrash(p):
                    QMessageBox.warning(self, tr("No se pudo"), tr("No se pudo mover a la papelera."))


class FileFinder(QLineEdit):
    """«Ir a un archivo…»: escribe parte del nombre o de la ruta y elige; abre el archivo."""
    picked = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("fileFinder")
        self.setPlaceholderText(tr("Ir a un archivo…  (Ctrl+P)"))
        self.setClearButtonEnabled(True)
        self.addAction(icon("acc_buscar", C["faint"], 13), QLineEdit.LeadingPosition)
        self.root, self._at, self._files = "", 0.0, []
        self.list = QStringListModel(self)
        self.comp = QCompleter(self.list, self)
        self.comp.setFilterMode(Qt.MatchContains)
        self.comp.setCaseSensitivity(Qt.CaseInsensitive)
        self.comp.setMaxVisibleItems(14)
        self.comp.activated.connect(self._pick)
        self.setCompleter(self.comp)
        self.returnPressed.connect(self._enter)

    def set_root(self, path):
        self.root, self._at = path, 0.0

    def scan(self, limit=20000):
        """Lista de archivos del proyecto (sin entrar en carpetas pesadas como node_modules o .git)."""
        out = []
        for d, dirs, files in os.walk(self.root):
            dirs[:] = sorted(x for x in dirs if x not in SKIP_SCAN)
            rel = os.path.relpath(d, self.root)
            for f in sorted(files):
                out.append(f if rel == "." else os.path.join(rel, f))
                if len(out) >= limit:
                    break
            if len(out) >= limit:
                break
        self._files, self._at = out, time.time()
        self.list.setStringList(out)

    def focusInEvent(self, e):
        if self.root and time.time() - self._at > 5:
            self.scan()
        super().focusInEvent(e)

    def _pick(self, rel):
        p = os.path.join(self.root, rel)
        if os.path.isfile(p):
            self.picked.emit(os.path.normpath(p))
            QTimer.singleShot(0, self.clear)

    def _enter(self):
        t = self.text().strip()
        if not t:
            return
        if os.path.isfile(os.path.join(self.root, t)):
            return self._pick(t)
        low = t.lower()
        hit = next((f for f in self._files if os.path.basename(f).lower() == low), None) or \
            next((f for f in self._files if low in f.lower()), None)
        if hit:
            self._pick(hit)


class ExplorerPanel(QWidget):
    """Barra lateral del proyecto: nombre y botones, «Ir a un archivo…» y el árbol."""
    open_file = Signal(str)

    def __init__(self, tbtn):
        super().__init__()
        self.setObjectName("sidebar")
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 8, 0, 6)
        v.setSpacing(6)
        head = QHBoxLayout()
        head.setContentsMargins(4, 0, 2, 0)
        head.setSpacing(2)
        self.ico = QLabel()
        self.ico.setPixmap(pix("act_carpeta_abierta", C["acc"], 15))
        head.addWidget(self.ico)
        from .widgets import ElidedLabel
        self.name = ElidedLabel()
        self.name.setStyleSheet("font-weight:600; padding-left:4px")
        head.addWidget(self.name, 1)
        self.tree = FileTree()
        head.addWidget(tbtn("acc_nuevo", tr("Nuevo archivo"), lambda: self.tree.new_file(), size=14))
        head.addWidget(tbtn("act_carpeta", tr("Nueva carpeta"), lambda: self.tree.new_folder(), size=14))
        head.addWidget(tbtn("ui_chevron_arriba", tr("Contraer todas las carpetas"), self.tree.collapseAll, size=13))
        more = tbtn("ui_menu_horizontal", tr("Más"), size=14)
        more.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(self)
        m.addAction(icon("act_carpeta_abierta"), tr("Mostrar en el Explorador") if osys.WIN else (tr("Mostrar en el Finder") if osys.MAC else tr("Abrir la carpeta")),
                    lambda: self.tree.root and osys.open_path(self.tree.root))
        m.addAction(icon("acc_copiar"), tr("Copiar la ruta del proyecto"), lambda: QGuiApplication.clipboard().setText(self.tree.root))
        more.setMenu(m)
        head.addWidget(more)
        v.addLayout(head)
        self.finder = FileFinder()
        wrap = QHBoxLayout()
        wrap.setContentsMargins(0, 0, 6, 0)
        wrap.addWidget(self.finder)
        v.addLayout(wrap)
        v.addWidget(self.tree, 1)
        self.tree.open_file.connect(self.open_file.emit)
        self.finder.picked.connect(self._picked)

    def set_project(self, name, path):
        self.name.setText(name)
        self.name.setToolTip(path)
        self.tree.set_root(path)
        self.finder.set_root(path)

    def _picked(self, p):
        self.open_file.emit(p)
        self.tree.reveal(p)

    def focus_finder(self):
        self.finder.setFocus()
        self.finder.selectAll()
