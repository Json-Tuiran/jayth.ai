# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Ventana de Ajustes con secciones (los cambios se guardan al instante)."""
import os, re, sys, json, subprocess, threading, webbrowser, urllib.request, datetime
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QListWidget, QListWidgetItem,
                               QStackedWidget, QScrollArea, QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit, QPlainTextEdit,
                               QFrame, QFileDialog, QMessageBox, QGridLayout, QApplication)
from . import APP_NAME, __version__, core, paths, osys, i18n, hardware as HW, agent as A, tools as T
from .i18n import tr
from .theme import C, icon, pix
from .wizard import SetupWizard, ModelsDialog, btn, lbl, browse_row, run_bg
from .widgets import Switch, ElideCombo, Columns
import shutil
from html import escape as html_escape


def short_paths(text):
    """C:\\Users\\…\\carpeta\\archivo.py -> …\\archivo.py (los errores se leen mejor; la ruta completa va en el tooltip)."""
    return re.sub(r"[A-Za-z]:\\[^\s'\"]+", lambda m: "…\\" + m.group(0).replace("\\\\", "\\").rstrip("\\").split("\\")[-1], text or "")

# Conectores MCP conocidos: rellenan el formulario (el usuario revisa y pulsa «Añadir y probar»)
MCP_TEMPLATES = [
    {"label": tr("Archivos de una carpeta"), "name": tr("Archivos"), "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "{carpeta}"],
     "note": tr("Da acceso a la carpeta indicada (puedes cambiarla en los argumentos). Necesita Node.js.")},
    {"label": tr("Memoria (grafo de conocimiento)"), "name": tr("Memoria"), "command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"],
     "note": tr("El agente guarda y consulta datos entre conversaciones. Necesita Node.js.")},
    {"label": tr("Navegador web (Playwright)"), "name": tr("Navegador"), "command": "npx", "args": ["-y", "@playwright/mcp@latest"],
     "note": tr("El agente abre y maneja un navegador real. Necesita Node.js.")},
    {"label": tr("Pensamiento paso a paso"), "name": tr("Pensamiento"), "command": "npx", "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
     "note": tr("Ayuda a los modelos pequeños a razonar problemas largos. Necesita Node.js.")},
    {"label": tr("Git (historial de un repositorio)"), "name": "Git", "command": "uvx", "args": ["mcp-server-git", "--repository", "{carpeta}"],
     "note": tr("Consulta el historial y los cambios de un repositorio. Necesita uv.")},
    {"label": tr("Leer páginas web (Fetch)"), "name": "Fetch", "command": "uvx", "args": ["mcp-server-fetch"],
     "note": tr("Descarga páginas web convertidas a texto. Necesita uv.")},
    {"label": tr("GitHub (remoto)"), "name": "GitHub", "url": "https://api.githubcopilot.com/mcp/",
     "note": tr("Pega abajo un token personal de GitHub (github.com/settings/tokens).")},
]

REPO = "Json-Tuiran/jayth.ai"
NO_WINDOW = osys.NO_WINDOW
SYSTEM = "Windows" if osys.WIN else ("macOS" if osys.MAC else "Linux")
FILE_MANAGER = tr("el Explorador") if osys.WIN else (tr("el Finder") if osys.MAC else tr("el gestor de archivos"))

LANGS = [(tr("Automático (el idioma de tu mensaje)"), "auto"), ("Español", "es"), ("English", "en"), ("Português", "pt"), ("Français", "fr"),
         ("Deutsch", "de"), ("Italiano", "it"), ("日本語", "ja"), ("中文", "zh")]
SHORTCUTS = [("Ctrl+N", tr("Nueva conversación")), ("Ctrl+K", tr("Buscar en tus conversaciones")), ("Ctrl+1 / Ctrl+2", tr("Cambiar entre Chat y Code")),
             ("Ctrl+Shift+S", tr("Mostrar u ocultar la barra lateral")), ("Enter / Shift+Enter", tr("Enviar / nueva línea")),
             ("Ctrl+V", tr("Pegar una imagen en el mensaje")), ("Ctrl+S", tr("Guardar el archivo (Code)")), ("Ctrl+W", tr("Cerrar la pestaña (Code)")),
             ("Ctrl+`", tr("Mostrar u ocultar la terminal (Code)")), ("Ctrl+B", tr("Mostrar u ocultar el explorador de archivos (Code)")),
             ("Ctrl+L", tr("Mostrar u ocultar el panel del agente (Code)")), ("Ctrl+Shift+M", tr("Modo enfoque: solo el editor (Code)")),
             (tr("Doble clic en un divisor"), tr("Plegar o recuperar el panel de al lado")), ("Esc", tr("Cerrar el buscador")),
             (tr("Ratón a la esquina superior izquierda"), tr("Detener al instante el control del ratón"))]


# nombres de las teclas en los atajos, como los escribe cada idioma en Windows y Linux (en macOS los pone Qt: ⌘ ⇧ ⏎)
KEY_NAMES = {"de": {"Ctrl": "Strg", "Shift": "Umschalt", "Enter": "Eingabe"},
             "fr": {"Shift": "Maj", "Enter": "Entrée", "Esc": "Échap"},
             "it": {"Shift": "Maiusc", "Enter": "Invio"}}


def keys_text(k):
    """«Ctrl+Shift+S» como se escribe en el idioma de la interfaz (Strg+Umschalt+S en alemán; ⌘⇧S en macOS).
    Lo que no es un atajo («Doble clic en un divisor») se deja tal cual."""
    out = []
    for part in k.split(" / "):
        if osys.MAC:
            from PySide6.QtGui import QKeySequence
            s = QKeySequence(part, QKeySequence.PortableText)
            if not s.isEmpty() and s.toString(QKeySequence.PortableText) == part:
                part = s.toString(QKeySequence.NativeText)
        else:
            names = KEY_NAMES.get(i18n.LANG, {})
            part = "+".join(names.get(x, x) for x in part.split("+"))
        out.append(part)
    return " / ".join(out)


# ---------------------------------------------------------------- acciones del sistema
def set_autostart(on):
    """Inicio con el sistema: carpeta Inicio (Windows), LaunchAgent (macOS) o ~/.config/autostart (Linux)."""
    osys.set_autostart(on, APP_NAME)


def export_conversations(folder):
    n = 0
    for s in core.sorted_sessions():
        lines = ["# " + s.title, "", "_%s_" % datetime.datetime.fromtimestamp(s.created).strftime("%Y-%m-%d %H:%M"), ""]
        for e in s.events:
            if e["t"] == "user":
                lines += [tr("## Tú"), "", e.get("text", ""), ""]
            elif e["t"] == "assistant_end" and e.get("text"):
                lines += ["## " + APP_NAME, "", e["text"], ""]
            elif e["t"] == "tool_call":
                lines += [tr("> Acción: `%s` %s") % (e["name"], json.dumps(e.get("args", {}), ensure_ascii=False)[:300]), ""]
        name = re.sub(r'[<>:"/\\|?*]+', "_", s.title)[:60] or s.id
        with open(os.path.join(folder, "%s - %s.md" % (datetime.datetime.fromtimestamp(s.created).strftime("%Y%m%d"), name)), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        n += 1
    return n


def unused_images():
    used = set()
    for s in core.SESSIONS.values():
        for e in s.events:
            used.update(e.get("images") or [])
            if e.get("image"):
                used.add(e["image"])
    return [os.path.join(paths.IMG_DIR, f) for f in os.listdir(paths.IMG_DIR) if f not in used]


def local_commit():
    head = os.path.join(paths.APP_DIR, ".git", "HEAD")
    try:
        ref = open(head).read().strip()
        if ref.startswith("ref:"):
            return open(os.path.join(paths.APP_DIR, ".git", ref[5:].strip())).read().strip()
        return ref
    except OSError:
        return ""


# ---------------------------------------------------------------- dialogo
# una frase bajo el título de cada página (por su nombre interno)
SUBTITLES = {
    "General": tr("Idioma, aspecto de la ventana y cómo se abre %s.") % APP_NAME,
    "Personalización": tr("Cómo te llama, cómo responde, la voz y lo que recuerda de ti."),
    "Modelos": tr("El modelo que usa el agente y de dónde lo obtiene."),
    "Generación": tr("Cómo escribe el modelo: cuánto piensa, cuánta creatividad y qué longitud."),
    "Rendimiento": tr("Velocidad y memoria del motor en este equipo."),
    "Agente y permisos": tr("Qué puede hacer el agente sin preguntarte y hasta dónde llega."),
    "Herramientas": tr("Internet, control del ordenador, búsqueda web y conectores con otros servicios."),
    "Imágenes": tr("Imágenes creadas en tu propio equipo, sin internet."),
    "Conocimiento": tr("Carpetas en las que el agente busca por significado: tus notas, documentos y proyectos."),
    "Datos y privacidad": tr("Dónde se guarda todo y cómo exportarlo o borrarlo."),
    "Registro del modelo": tr("Lo que escribe el motor al trabajar, para diagnosticar problemas."),
    "Atajos de teclado": tr("Combinaciones de teclas de %s.") % APP_NAME,
    "Acerca de": tr("Versión, licencia, actualizaciones y comentarios."),
}


class Page:
    """Contenido de una página de Ajustes. Ofrece lo que usan las páginas de un QVBoxLayout (addWidget, addLayout,
    addSpacing, addStretch), pero lo agrupa: lo que se añade va a la tarjeta de la sección en curso, con una línea fina
    entre filas; section() cierra la tarjeta y pone el título de la siguiente."""

    def __init__(self, layout):
        self.root = layout
        self.card, self.n = None, 0

    def section(self, text):
        self.card, self.n = None, 0
        t = QLabel(text)
        t.setObjectName("setSection")
        self.root.addSpacing(12)
        self.root.addWidget(t)
        self.root.addSpacing(2)

    def _next(self):
        if self.card is None:
            fr = QFrame()
            fr.setObjectName("setCard")
            self.card = QVBoxLayout(fr)
            self.card.setContentsMargins(16, 4, 16, 4)
            self.card.setSpacing(0)
            self.root.addWidget(fr)
            self.n = 0
        elif self.n:
            sep = QFrame()
            sep.setObjectName("setSep")
            self.card.addWidget(sep)
        self.n += 1
        return self.card

    def addWidget(self, w, *a):
        if w.objectName() == "noteBox" and not self.n:          # un recuadro propio al empezar: él es la tarjeta
            w.setObjectName("setCard")
            self.root.addWidget(w, *a)
            self.card, self.n = None, 0
            return
        if w.property("setRow"):
            return self._next().addWidget(w, *a)
        holder = QWidget()                                       # el resto, con el mismo aire que una fila
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 10, 0, 10)
        hl.addWidget(w, *a)
        self._next().addWidget(holder)

    def addLayout(self, lay, *a):
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 10, 0, 10)
        hl.addLayout(lay, *a)
        self._next().addWidget(holder)

    def addSpacing(self, n):
        (self.card or self.root).addSpacing(n)

    def addStretch(self, n=0):
        self.root.addStretch(n)


class _Row(QWidget):
    """Fila de una opción: nombre y explicación a la izquierda, el control a la derecha. Un clic en la fila de un
    interruptor lo cambia (no hace falta acertar en él)."""
    switch = None

    def mouseReleaseEvent(self, e):
        if self.switch is not None and e.button() == Qt.LeftButton and self.switch.isEnabled():
            self.switch.toggle()
        super().mouseReleaseEvent(e)


class SettingsDialog(QDialog):
    def __init__(self, parent=None, page="General"):
        super().__init__(parent)
        self.setWindowTitle(tr("Ajustes"))
        self.setObjectName("settings")
        self.resize(1000, 700)
        self.before = core.SET.snapshot()
        self.timers = {}
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        side = QWidget()
        side.setObjectName("setSide")
        side.setAttribute(Qt.WA_StyledBackground, True)
        side.setFixedWidth(224)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(12, 18, 12, 12)
        t = QLabel(tr("Ajustes"))
        t.setObjectName("h1")
        t.setContentsMargins(8, 0, 0, 0)
        sv.addWidget(t)
        sv.addSpacing(10)
        self.nav = QListWidget()
        self.nav.setObjectName("setNav")
        self.nav.setIconSize(QSize(17, 17))
        sv.addWidget(self.nav, 1)
        root.addWidget(side)
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(12, 6, 8, 6)
        bl.addWidget(QLabel(tr("Algunos cambios se aplican al reiniciar el modelo.")), 1)
        bl.addWidget(btn(tr("Reiniciar modelo"), "primary", self._restart_llm))
        self.banner.hide()
        bw = QWidget()
        bwl = QHBoxLayout(bw)
        bwl.setContentsMargins(32, 12, 32, 0)
        bwl.addWidget(self.banner)
        rv.addWidget(bw)
        self.pages = QStackedWidget()
        rv.addWidget(self.pages, 1)
        fw = QWidget()
        fw.setObjectName("setFoot")
        fw.setAttribute(Qt.WA_StyledBackground, True)
        foot = QHBoxLayout(fw)
        foot.setContentsMargins(32, 10, 20, 12)
        self.saved = QLabel(tr("Los cambios se guardan automáticamente."))
        self.saved.setObjectName("faint")
        foot.addWidget(self.saved, 1)
        foot.addWidget(btn(tr("Cerrar"), "primary", self.accept))
        rv.addWidget(fw)
        root.addWidget(right, 1)
        # key: nombre interno de la página (lo usan SettingsDialog(page=…) y _reload); label: el texto que se muestra
        for key, label, ico, build in (("General", tr("General"), "acc_ajustes", self.p_general),
                                       ("Personalización", tr("Personalización"), "mat_comentario", self.p_personal),
                                       ("Modelos", tr("Modelos"), "ia_controlador", self.p_models),
                                       ("Generación", tr("Generación"), "vfx_magia", self.p_generation),
                                       ("Rendimiento", tr("Rendimiento"), "prof_cpu", self.p_performance),
                                       ("Agente y permisos", tr("Agente y permisos"), "est_bloqueado", self.p_agent),
                                       ("Herramientas", tr("Herramientas"), "cod_terminal", self.p_tools),
                                       ("Imágenes", tr("Imágenes"), "uij_imagen", self.p_images),
                                       ("Conocimiento", tr("Conocimiento"), "acc_examinar", self.p_knowledge),
                                       ("Datos y privacidad", tr("Datos y privacidad"), "prof_disco", self.p_data),
                                       ("Registro del modelo", tr("Registro del modelo"), "pan_consola", self.p_log),
                                       ("Atajos de teclado", tr("Atajos de teclado"), "inp_teclado", self.p_keys),
                                       ("Acerca de", tr("Acerca de"), "est_info", self.p_about)):
            it = QListWidgetItem(icon(ico, C["mut"], 17), label)
            it.setData(Qt.UserRole, key)
            self.nav.addItem(it)
            self.pages.addWidget(self._scroll(label, build, SUBTITLES.get(key, "")))
        # la barra lateral se ensancha si en este idioma algún nombre no cabe (la página elegida va en negrita)
        self.nav.ensurePolished()                     # con la fuente del tema ya aplicada
        bold = QFont(self.nav.font())
        bold.setWeight(QFont.DemiBold)
        need = max(QFontMetrics(bold).horizontalAdvance(self.nav.item(i).text()) for i in range(self.nav.count()))
        side.setFixedWidth(max(224, need + 17 + 8 + 20 + 12 + 24))      # icono, separación, relleno, holgura y márgenes
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        keys = [self.nav.item(i).data(Qt.UserRole) for i in range(self.nav.count())]
        labels = [self.nav.item(i).text() for i in range(self.nav.count())]
        self.nav.setCurrentRow(keys.index(page) if page in keys else labels.index(page) if page in labels else 0)

    # ---- infraestructura
    def _scroll(self, title, build, sub=""):
        """Página con su título, una frase que explica para qué sirve y las opciones agrupadas en tarjetas."""
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        w = QWidget()
        w.setObjectName("chatHolder")
        sc.viewport().setObjectName("chatHolder")
        outer = QHBoxLayout(w)
        outer.setContentsMargins(32, 22, 24, 24)
        col = QWidget()
        col.setMaximumWidth(780)                    # en ventanas anchas no se estira de lado a lado
        outer.addWidget(col, 1)
        outer.addStretch(0)
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        h = QLabel(title)
        h.setObjectName("setTitle")
        v.addWidget(h)
        if sub:
            s = QLabel(sub)
            s.setObjectName("setSub")
            s.setWordWrap(True)
            v.addWidget(s)
        v.addSpacing(8)
        page = Page(v)
        build(page)
        v.addStretch(1)
        sc.setWidget(w)
        return sc

    def _section(self, v, text):
        if isinstance(v, Page):
            return v.section(text)
        l = QLabel(text)
        l.setObjectName("setSection")
        v.addSpacing(12)
        v.addWidget(l)

    def _save(self, key, value):
        core.SET.update({key: value})
        self.saved.setText(tr("Guardado ✓"))
        QTimer.singleShot(1500, lambda: self.saved.setText(tr("Los cambios se guardan automáticamente.")))
        if key in core.RESTART_KEYS and core.LLM_MGR.mine():
            self.banner.show()
        if key == "start_with_windows":
            set_autostart(bool(value))
        if key == "ui_language":
            QTimer.singleShot(0, self._ask_restart_language)
        if key in ("image_model", "image_size", "models_dir", "backend") and getattr(self, "img_box", None) is not None:
            self.img_box.refresh()

    def _ask_restart_language(self):
        """El idioma se elige al arrancar: ofrece reiniciar Jayth para verlo ya."""
        want = core.SET.snapshot().get("ui_language", "auto")
        now = i18n.LANG
        new = want if want in i18n.LANGS else i18n.system_lang()
        if new == now:
            return
        r = QMessageBox.question(self, tr("Idioma de la interfaz"),
                                 tr("El nuevo idioma se verá al reiniciar %s. ¿Reiniciar ahora?") % APP_NAME,
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        main = getattr(QApplication.instance(), "_main", None)
        if r == QMessageBox.StandardButton.Yes and main is not None:
            self.close()
            main.restart_app()

    def _debounced(self, key, getter, ms=600):
        t = self.timers.get(key)
        if t is None:
            t = QTimer(self, singleShot=True, interval=ms)
            t.timeout.connect(lambda: self._save(key, getter()))
            self.timers[key] = t
        t.start()

    def field(self, v, key, label, kind, help="", **kw):
        """Crea una fila enlazada a un ajuste y lo guarda al cambiar: nombre y explicación a la izquierda y el control a
        la derecha (interruptor, lista o número); los textos y carpetas, a todo el ancho debajo del nombre."""
        val = core.SET.snapshot()[key]
        box = _Row()
        box.setProperty("setRow", True)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 11, 0, 11)
        bl.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(18)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        name = QLabel(label)
        name.setObjectName("setLabel")
        name.setWordWrap(True)
        texts.addWidget(name)
        if help:
            h = QLabel(help)
            h.setObjectName("setHelp")
            h.setWordWrap(True)
            texts.addWidget(h)
        top.addLayout(texts, 1)
        bl.addLayout(top)
        side = None                                    # control a la derecha
        if kind == "bool":
            w = Switch(label)
            w.setChecked(bool(val))
            w.toggled.connect(lambda on: self._save(key, on))
            box.switch = side = w
            box.setCursor(Qt.PointingHandCursor)
        elif kind == "int":
            w = QSpinBox()
            w.setRange(kw.get("min", 0), kw.get("max", 1_000_000))
            w.setValue(int(val))
            if kw.get("suffix"):
                w.setSuffix(kw["suffix"])
            if kw.get("special"):
                w.setSpecialValueText(kw["special"])
            w.valueChanged.connect(lambda x: self._debounced(key, w.value, 400))
            w.setFixedWidth(150)
            side = w
        elif kind == "float":
            w = QDoubleSpinBox()
            w.setRange(kw.get("min", 0.0), kw.get("max", 2.0))
            w.setSingleStep(kw.get("step", 0.05))
            w.setDecimals(kw.get("decimals", 2))
            w.setValue(float(val))
            w.valueChanged.connect(lambda x: self._debounced(key, w.value, 400))
            w.setFixedWidth(150)
            side = w
        elif kind == "choice":
            w = ElideCombo()                          # todas del mismo ancho; si no cabe, «…» (entera al desplegarla)
            for t, d in kw["choices"]:
                w.addItem(t, d)
            i = w.findData(val)
            if i < 0:
                w.addItem(str(val), val)
                i = w.count() - 1
            w.setCurrentIndex(i)
            w.currentIndexChanged.connect(lambda _: self._save(key, w.currentData()))
            w.setFixedWidth(300)
            side = w
        elif kind in ("text", "secret"):
            w = QLineEdit(str(val))
            if kind == "secret":
                w.setEchoMode(QLineEdit.Password)
            if kw.get("placeholder"):
                w.setPlaceholderText(kw["placeholder"])
            w.textChanged.connect(lambda _: self._debounced(key, w.text))
            bl.addWidget(w)
        elif kind in ("area", "list"):
            w = QPlainTextEdit("\n".join(val) if kind == "list" else str(val))
            w.setFixedHeight(kw.get("height", 96))
            if kw.get("placeholder"):
                w.setPlaceholderText(kw["placeholder"])
            getter = (lambda: [l.strip() for l in w.toPlainText().splitlines() if l.strip()]) if kind == "list" else w.toPlainText
            w.textChanged.connect(lambda: self._debounced(key, getter))
            bl.addWidget(w)
        elif kind == "dir":
            w = QLineEdit(str(val))
            w.textChanged.connect(lambda _: self._debounced(key, w.text, 900))
            row = browse_row(w, folder=True, parent=self)
            wr = QWidget()
            wr.setLayout(row)
            row.setContentsMargins(0, 0, 0, 0)
            bl.addWidget(wr)
        if side is not None:
            top.addWidget(side, 0, Qt.AlignVCenter | Qt.AlignRight)
        v.addWidget(box)
        return box

    # ---- paginas
    def p_general(self, v):
        self.field(v, "ui_language", tr("Idioma de la interfaz"), "choice",
                   choices=[(tr("Automático (el idioma del sistema)"), "auto")] + [(n, c) for c, n in i18n.NAMES.items()],
                   help=tr("Menús, botones y mensajes de %s. Se aplica al reiniciar.") % APP_NAME)
        self.field(v, "theme",tr("Tema"), "choice", choices=[(tr("Según el sistema"), "system"), (tr("Oscuro"), "dark"), (tr("Claro"), "light")])
        self.field(v, "font_scale", tr("Tamaño del texto"), "choice", choices=[(tr("Pequeño"), 90), (tr("Normal"), 100), (tr("Grande"), 115), (tr("Muy grande"), 130)],
                   help=tr("El tema y el tamaño se aplican al cerrar esta ventana."))
        self.field(v, "animations", tr("Animaciones (aparición de mensajes, barra lateral, avisos)"), "bool")
        if osys.WIN:      # en macOS y Linux se usa siempre la barra del sistema (semáforos de macOS, decoraciones del escritorio)
            self.field(v, "custom_titlebar", tr("Barra de título integrada en la ventana"), "bool",
                       help=tr("Como en las apps de escritorio modernas. Si la desactivas se usa la barra de Windows (al reiniciar %s).") % APP_NAME)
        self._section(v, tr("Editor de %s Code") % APP_NAME)
        self.field(v, "editor_autosave", tr("Guardado automático de los archivos"), "choice",
                   choices=[(tr("Al hacer una pausa al escribir (1 segundo)"), "delay"),
                            (tr("Al cambiar de pestaña o de ventana"), "focus"),
                            (tr("Desactivado: guardar con Ctrl+S"), "off")],
                   help=tr("Con el guardado desactivado, las pestañas con cambios sin guardar llevan un punto (●) y %s pregunta antes de "
                           "cerrarlas.") % APP_NAME)
        self._section(v, tr("Inicio y ventana"))
        self.field(v, "start_with_windows", tr("Abrir %s al iniciar %s (minimizado en la bandeja)") % (APP_NAME, SYSTEM), "bool")
        self.field(v, "autostart_llm", tr("Encender el modelo al abrir %s") % APP_NAME, "bool",
                   help=tr("Así está listo cuando lo necesites. Usa la memoria del modelo mientras la app esté abierta."))
        self.field(v, "close_to_tray", tr("Al cerrar la ventana, seguir funcionando en la bandeja del sistema"), "bool")
        self.field(v, "notifications", tr("Avisarme cuando el agente necesite mi aprobación"), "bool")
        self.field(v, "quick_hotkey", tr("Atajo de la ventana rápida"), "text", placeholder="Ctrl+Alt+J",
                   help=tr("Abre una barrita para preguntar a %s desde cualquier programa, con opción de adjuntar una captura de la pantalla. "
                        "Funciona mientras %s esté abierto (también en la bandeja). Déjalo vacío para desactivarlo.") % (APP_NAME, APP_NAME))

    def p_personal(self, v):
        self.field(v, "user_name", tr("¿Cómo quieres que te llame?"), "text", placeholder=tr("Tu nombre (opcional)"),
                   help=tr("Se usa en el saludo y para que el agente sepa cómo dirigirse a ti."))
        self.field(v, "about_me", tr("¿Qué debería saber %s de ti?") % APP_NAME, "area",
                   placeholder=tr("Ej.: Soy diseñador, trabajo con Python y Figma, uso %s y guardo mis proyectos en %s.") % (SYSTEM, "D:\\Trabajo" if osys.WIN else "~/Trabajo"))
        self.field(v, "response_style", tr("¿Cómo quieres que responda?"), "area",
                   placeholder=tr("Ej.: Respuestas breves y directas, con ejemplos de código y sin relleno."))
        self.field(v, "response_language", tr("Idioma de las respuestas"), "choice", choices=LANGS)
        self.field(v, "custom_instructions", tr("Instrucciones adicionales para el agente"), "area",
                   placeholder=tr("Ej.: Antes de borrar o mover archivos, explícame qué vas a hacer."))
        self._section(v, tr("Voz"))
        from . import voice as _voice
        self.field(v, "voice_model", tr("Precisión del dictado"), "choice", choices=[("%s: %s" % (k.capitalize(), d), k) for k, d in _voice.MODELS.items()],
                   help=tr("El dictado funciona en tu equipo. El modelo elegido se descarga la primera vez que lo uses."))
        self.field(v, "voice_lang", tr("Idioma del dictado"), "choice",
                   choices=[(tr("Detectar automáticamente"), ""), (tr("Español"), "es"), (tr("Inglés"), "en"), (tr("Portugués"), "pt"), (tr("Francés"), "fr"), (tr("Alemán"), "de"), (tr("Italiano"), "it"),
                            (tr("Japonés"), "ja"), (tr("Chino"), "zh")])
        self._section(v, tr("Memoria"))
        v.addWidget(lbl(tr("Lo que %s recuerda de ti entre conversaciones (lo guarda cuando le dices algo duradero, como «uso pnpm»). "
                        "Puedes editarlo o borrarlo.") % APP_NAME, "faint"))
        self.field(v, "memory_enabled", tr("Usar la memoria (recordar cosas entre conversaciones)"), "bool",
                   help=tr("Apagada, %s no lee ni guarda recuerdos. Para una sola conversación sin memoria usa el chat temporal.") % APP_NAME)
        self.mem_box = QVBoxLayout()
        self.mem_box.setSpacing(4)
        v.addLayout(self.mem_box)
        r = QHBoxLayout()
        self.mem_new = QLineEdit()
        self.mem_new.setPlaceholderText(tr("Añadir un recuerdo, p. ej.: Prefiero respuestas cortas"))
        self.mem_new.returnPressed.connect(self._mem_add)
        r.addWidget(self.mem_new, 1)
        r.addWidget(btn(tr("Añadir"), None, self._mem_add, "acc_anadir"))
        self.mem_clear = btn(tr("Borrar toda la memoria"), "danger", self._mem_clear)
        r.addWidget(self.mem_clear)
        v.addLayout(r)
        self._mem_render()
        v.addWidget(lbl(tr("En los proyectos, %s también lee AGENTS.md, JAYTH.md o CLAUDE.md de la carpeta: escribe ahí las normas del proyecto.") % APP_NAME, "faint"))

    # ---- memoria: un recuerdo por fila, cada uno se puede corregir o borrar
    def _mem_render(self):
        from . import harness
        while self.mem_box.count():
            w = self.mem_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        items = harness.memory_items()
        self.mem_clear.setVisible(bool(items))
        if not items:
            self.mem_box.addWidget(lbl(tr("Todavía no hay recuerdos guardados."), "faint"))
        for i, (text, date) in enumerate(items):
            row = QFrame()
            row.setObjectName("noteBox")
            h = QHBoxLayout(row)
            h.setContentsMargins(10, 4, 4, 4)
            e = QLineEdit(text)
            e.setFrame(False)
            e.setStyleSheet("background: transparent")
            e.setToolTip(tr("Edita el recuerdo y pulsa Enter para guardarlo"))
            e.editingFinished.connect(lambda i=i, e=e: self._mem_edit(i, e.text()))
            h.addWidget(e, 1)
            if date:
                h.addWidget(lbl(date, "faint", wrap=False))
            b = btn(tr("Olvidar"), None, lambda _=False, i=i: self._mem_edit(i, ""))
            b.setProperty("kind", "flat")
            h.addWidget(b)
            self.mem_box.addWidget(row)

    def _mem_edit(self, i, text):
        from . import harness
        items = harness.memory_items()
        if i >= len(items) or items[i][0] == text.strip():
            return
        if text.strip():
            items[i] = (text.strip(), items[i][1])
        else:
            del items[i]
        harness.memory_save(items)
        self.saved.setText(tr("Memoria actualizada."))
        if not text.strip():
            QTimer.singleShot(0, self._mem_render)

    def _mem_add(self):
        from . import harness
        t = self.mem_new.text().strip()
        if t:
            harness.remember(t)
            self.mem_new.clear()
            self._mem_render()

    def _mem_clear(self):
        from . import harness
        if QMessageBox.question(self, tr("Borrar la memoria"), tr("¿Borrar todos los recuerdos? No se puede deshacer.")) == QMessageBox.StandardButton.Yes:
            harness.memory_save([])
            self._mem_render()

    def p_models(self, v):
        cfg = core.SET.snapshot()
        m = core.active_model(cfg)
        card = QFrame()
        card.setObjectName("noteBox")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.addWidget(lbl(tr("<b>Modelo activo:</b> %s") % ((core.model_title(m) if m else tr("ninguno")) if cfg["llm_mode"] == "local" else tr("servidor externo"))))
        if m and cfg["llm_mode"] == "local":
            cl.addWidget(lbl("%s · %s · %s" % (core.model_quant(m) or "GGUF", HW.human(m.get("size", 0)), m.get("path", "")), "faint"))
        row = QHBoxLayout()
        row.addWidget(btn(tr("Gestionar modelos…"), cb=lambda: ModelsDialog(self).exec(), ico="ia_controlador"))
        row.addWidget(btn(tr("Añadir modelo…"), cb=lambda: SetupWizard(self, start="model").exec(), ico="acc_anadir"))
        row.addWidget(btn(tr("Asistente de configuración…"), cb=lambda: SetupWizard(self).exec(), ico="vfx_magia"))
        row.addStretch(1)
        cl.addLayout(row)
        v.addWidget(card)
        self.field(v, "models_dir", tr("Carpeta donde se descargan los modelos"), "dir")
        self._section(v, tr("Proveedor"))
        self.field(v, "llm_mode", tr("¿Qué motor usa el agente?"), "choice",
                   choices=[(tr("Local: llama.cpp en este equipo"), "local"), (tr("Servidor externo compatible con OpenAI"), "external")])
        self.field(v, "external_url", tr("URL del servidor externo (termina en /v1)"), "text", placeholder="http://127.0.0.1:11434/v1",
                   help=tr("Ollama: http://127.0.0.1:11434/v1 · LM Studio: http://127.0.0.1:1234/v1 · otro PC de tu red: http://IP:puerto/v1"))
        self.field(v, "external_model", tr("Nombre del modelo en ese servidor"), "text", placeholder="qwen3:8b")
        self.field(v, "external_key", tr("Clave de API (si el servidor la pide)"), "secret")
        res = lbl("", "faint")
        b = btn(tr("Probar conexión"), cb=lambda: self._test_ext(res), ico="hub_conectar")
        r = QHBoxLayout()
        r.addWidget(b)
        r.addWidget(res, 1)
        v.addLayout(r)

    def _test_ext(self, out):
        cfg = core.SET.snapshot()
        out.setText(tr("Probando…"))

        def probe():
            req = urllib.request.Request(cfg["external_url"].rstrip("/") + "/models", headers={"Authorization": "Bearer " + (cfg["external_key"] or "local")})
            return [m.get("id") for m in json.loads(urllib.request.urlopen(req, timeout=5).read().decode("utf-8")).get("data", [])]
        run_bg(probe, lambda r: out.setText((tr("✗ No responde: %s") % r) if isinstance(r, Exception) else tr("✓ Conectado · %s") % (", ".join(r[:6]) or tr("sin modelos listados"))))

    def p_generation(self, v):
        self.field(v, "thinking", tr("Pensar a fondo por defecto (mejores respuestas, más lento)"), "bool")
        self.field(v, "sampling", tr("Parámetros de muestreo"), "choice",
                   choices=[(tr("Recomendados para el modelo activo (automático)"), "auto"), (tr("Personalizados (los de abajo)"), "custom")],
                   help=tr("Automático usa los valores que publica cada laboratorio (Qwen, Gemma, Llama, Mistral, DeepSeek…) según si piensa o no."))
        self.field(v, "temperature", tr("Temperatura"), "float", min=0, max=2, help=tr("Más alta = más creativa y variada; más baja = más precisa y estable."))
        self.field(v, "max_tokens", tr("Longitud máxima de cada respuesta (tokens)"), "int", min=64, max=65536)
        self._section(v, tr("Muestreo avanzado"))
        self.field(v, "top_p", "Top-p", "float", min=0, max=1)
        self.field(v, "top_k", "Top-k", "int", min=0, max=500, special=tr("sin límite"))
        self.field(v, "min_p", "Min-p", "float", min=0, max=1)
        self.field(v, "repeat_penalty", tr("Penalización por repetición"), "float", min=1, max=2, help=tr("1,00 = desactivada."))
        self.field(v, "seed", tr("Semilla"), "int", min=-1, max=2_000_000_000, special=tr("aleatoria"), help=tr("Fija un número para obtener siempre la misma respuesta."))
        r = QHBoxLayout()
        r.addWidget(btn(tr("Restablecer valores recomendados"), cb=self._reset_generation))
        r.addStretch(1)
        v.addLayout(r)

    def _reset_generation(self):
        core.SET.update({k: core.DEFAULTS[k] for k in ("temperature", "top_p", "top_k", "min_p", "repeat_penalty", "seed", "max_tokens")})
        self._reload("Generación")

    def _reload(self, page):
        p = self.parent()
        self.done(0)
        d = SettingsDialog(p, page)
        d.exec()

    def p_performance(self, v):
        cfg = core.SET.snapshot()
        card = QFrame()
        card.setObjectName("noteBox")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        hw = lbl(tr("Detectando tu equipo…"))
        cl.addWidget(hw)
        cl.addWidget(lbl(tr("Motor: llama.cpp %s · %s") % (cfg["llama_tag"] or "", {"cpu": "CPU", "cuda": tr("GPU NVIDIA (CUDA)"), "vulkan": "GPU (Vulkan)"}.get(cfg["backend"], cfg["backend"])), "faint"))
        r = QHBoxLayout()
        r.addWidget(btn(tr("Cambiar o actualizar el motor…"), cb=lambda: SetupWizard(self).exec(), ico="acc_refrescar"))
        self.tune_btn = btn(tr("Optimizar para este equipo"), "primary", self._tune, "prof_cpu")
        self.tune_btn.setToolTip(tr("Prueba de verdad varias configuraciones del motor con tu modelo (unos minutos) y deja la más rápida."))
        r.addWidget(self.tune_btn)
        self.tune_cancel = btn(tr("Cancelar"), None, self._tune_cancel)
        self.tune_cancel.hide()
        r.addWidget(self.tune_cancel)
        r.addStretch(1)
        cl.addLayout(r)
        self.tune_lbl = lbl("", "faint")
        cl.addWidget(self.tune_lbl)
        self._tune_show()
        v.addWidget(card)
        run_bg(HW.detect, lambda h: hw.setText(HW.summary(h) if not isinstance(h, Exception) else tr("No se pudo detectar el hardware.")))
        self.field(v, "warmup", tr("Precalentar al encender el modelo"), "bool",
                   help=tr("Procesa una vez las instrucciones y herramientas del agente: el primer mensaje responde muchísimo antes."))
        cfg = core.SET.snapshot()
        auto = dict(cfg, n_ctx=0)
        try:
            now = core.effective_ctx(auto)
            caps = core.model_caps(core.active_model(cfg), compute=False) or {}
            native = int(caps.get("ctx") or 0)
            ctx_help = tr("Automático usa todo el contexto que admite el modelo de fábrica, reducido si no cabe en la memoria de "
                          "tu equipo. Con el modelo activo serían %s tokens%s.") % (
                "{:,}".format(now).replace(",", " "), (tr(" (máximo del modelo: %s)") % "{:,}".format(native).replace(",", " ")) if native else "")
        except Exception:
            ctx_help = tr("Automático usa todo el contexto que admite el modelo de fábrica, reducido si no cabe en la memoria de tu equipo.")
        self.field(v, "n_ctx", tr("Memoria de la conversación (contexto)"), "choice",
                   choices=[(tr("Automático: lo que admita el modelo (recomendado)"), 0), (tr("4 000 tokens"), 4096), (tr("8 000 tokens"), 8192),
                            (tr("16 000 tokens"), 16384), (tr("32 000 tokens"), 32768), (tr("64 000 tokens"), 65536), (tr("128 000 tokens"), 131072),
                            (tr("256 000 tokens"), 262144)],
                   help=ctx_help + " " + tr("Más contexto permite tareas más largas, pero usa más memoria."))
        self.field(v, "idle_unload", tr("Apagar el modelo si no se usa durante"), "choice",
                   choices=[(tr("Nunca"), 0), (tr("5 minutos"), 5), (tr("15 minutos"), 15), (tr("30 minutos"), 30), (tr("1 hora"), 60)], help=tr("Libera memoria cuando no lo estás usando."))
        self._section(v, tr("Ajustes del motor"))
        self.field(v, "threads", tr("Hilos de CPU"), "int", min=1, max=256, help=tr("Lo ideal suele ser el número de núcleos físicos."))
        self.field(v, "gpu_layers", tr("Capas en la GPU"), "int", min=-1, max=999, special=tr("automático"), help=tr("Solo con GPU. Automático reparte el modelo entre GPU y RAM."))
        self.field(v, "batch_size", tr("Tamaño de lote"), "choice", choices=[(str(x), x) for x in (128, 256, 512, 1024, 2048)],
                   help=tr("Más grande procesa más rápido los textos largos, con algo más de memoria."))
        self.field(v, "cache_type", tr("Contexto comprimido"), "choice",
                   choices=[(tr("No (máxima calidad)"), "f16"), (tr("8 bits (la mitad de memoria, casi sin pérdida)"), "q8_0"), (tr("4 bits (un cuarto de memoria)"), "q4_0")])
        self.field(v, "flash_attn", "Flash attention", "choice", choices=[(tr("Automático"), "auto"), (tr("Activado"), "on"), (tr("Desactivado"), "off")])
        self.field(v, "spec_type", tr("Aceleración al escribir"), "choice",
                   choices=[(tr("Automática (la que elija «Optimizar»)"), "auto"), (tr("Desactivada"), "none"),
                            (tr("MTP (capas de predicción del modelo)"), "draft-mtp"), (tr("Repetición de texto (n-gramas)"), "ngram-mod"),
                            (tr("MTP y n-gramas"), "draft-mtp,ngram-mod")],
                   help=tr("Decodificación especulativa: el modelo adelanta varias palabras y las comprueba de una vez. MTP usa capas "
                           "que traen algunos modelos (p. ej. Qwen 3.5 y 3.8); los n-gramas aceleran al reescribir código o texto. "
                           "Solo se usa si tu motor y tu modelo lo admiten."))
        self.field(v, "mmap", tr("Cargar el modelo con mmap (arranque más rápido)"), "bool")
        self.field(v, "mlock", tr("Bloquear el modelo en la RAM (evita que el sistema lo mueva al disco)"), "bool",
                   help=tr("Útil si tienes RAM de sobra; si no, puede ralentizar el equipo."))
        self.field(v, "llm_port", tr("Puerto local del motor"), "int", min=1024, max=65535)
        self._section(v, tr("Descargas"))
        self.field(v, "download_connections", tr("Conexiones simultáneas al descargar modelos"), "int", min=1, max=16,
                   help=tr("Varias conexiones aprovechan mejor tu internet (como un gestor de descargas). Pon 1 si tu red "
                        "o tu router van mal con muchas conexiones a la vez."))

    # ---- ajuste medido del motor (ajuste.py)
    def _tune_show(self):
        from . import ajuste
        job = ajuste.JOB
        busy = bool(job and job["running"])
        self.tune_btn.setVisible(not busy)
        self.tune_cancel.setVisible(busy)
        if busy:
            self.tune_lbl.setText(tr("Optimizando: %s") % job["text"])
        elif job and job.get("error"):
            self.tune_lbl.setText(tr("No se pudo optimizar: %s") % job["error"])
        else:
            rep = core.SET.snapshot().get("tuning") or {}
            self.tune_lbl.setText(tr("Última optimización (%s, %s): %s") % (rep["date"], rep.get("model", ""), ajuste.summary(rep)) if rep
                                  else tr("Aún sin optimizar: %s usa valores calculados. «Optimizar» mide tu equipo de verdad.") % APP_NAME)

    def _tune(self):
        from . import ajuste
        if core.SET.snapshot().get("llm_mode") == "external":
            return QMessageBox.information(self, APP_NAME, tr("La optimización es para modelos locales."))
        was = core.LLM_MGR.mine()
        if was:
            r = QMessageBox.question(self, tr("Optimizar para este equipo"),
                                     tr("Para medir bien, %s apaga el modelo unos minutos y lo vuelve a encender al terminar. ¿Seguir?") % APP_NAME,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes:
                return
            core.LLM_MGR.stop()

        def done(job):
            if was:
                core.LLM_MGR.start()
        ajuste.start(done=done)
        self._tune_timer = QTimer(self, interval=500, timeout=self._tune_tick)
        self._tune_timer.start()
        self._tune_show()

    def _tune_tick(self):
        from . import ajuste
        self._tune_show()
        if ajuste.JOB and not ajuste.JOB["running"]:
            self._tune_timer.stop()
            if ajuste.JOB.get("report"):
                QTimer.singleShot(0, lambda: self._reload("Rendimiento"))     # se ven los valores nuevos (hilos, flash attention…)

    def _tune_cancel(self):
        from . import ajuste
        if ajuste.JOB:
            ajuste.JOB["stop"].set()

    def p_agent(self, v):
        self.field(v, "mode", tr("Permisos por defecto"), "choice", choices=[(d, k) for k, d in A.MODES.items()])
        self.field(v, "workspace", tr("Carpeta de trabajo del modo Chat"), "dir")
        self.field(v, "auto_allow_commands", tr("Comandos que se permiten sin preguntar"), "list", height=90,
                   placeholder="git status\nnpm test\npython -m pytest",
                   help=tr("Uno por línea. Se aplica si el comando empieza así y no encadena otros (; | &). Las acciones delicadas siempre preguntan."))
        self._section(v, tr("Límites"))
        self.field(v, "max_steps", tr("Máximo de pasos por tarea"), "int", min=1, max=500)
        self.field(v, "command_timeout", tr("Tiempo máximo de cada comando"), "int", min=5, max=900, suffix=" s")
        self.field(v, "max_tool_output", tr("Máximo de texto que recibe el modelo de cada acción"), "int", min=1000, max=200000, suffix=tr(" caracteres"))
        self.field(v, "vision", tr("Enviar capturas e imágenes al modelo (si tiene visión)"), "bool")
        self.field(v, "keep_images", tr("Imágenes recientes que recuerda"), "int", min=0, max=10)

    def p_tools(self, v):
        self.field(v, "web_access", tr("Permitir el acceso a internet (buscar, leer páginas y descargar)"), "bool")
        self.field(v, "computer_control", tr("Permitir el control del ordenador (ratón, teclado, capturas)"), "bool")
        self.field(v, "tools_mode", tr("Herramientas que se cargan"), "choice",
                   choices=[(tr("Solo las que necesita cada tarea (recomendado)"), "auto"), (tr("Todas siempre"), "all")],
                   help=tr("Con solo las necesarias, el modelo tiene más memoria para la conversación, responde antes y se equivoca "
                           "menos; el agente activa las demás en cuanto las necesita. «Todas siempre» gasta unas 6000 palabras más "
                           "de contexto en cada conversación."))
        self._section(v, tr("Herramientas disponibles"))
        off = set(core.SET.snapshot()["tools_disabled"])
        cats = {}
        for name, t in T.TOOLS.items():
            cats.setdefault(t["category"], []).append(name)
        blocks = []
        for cat, names in cats.items():
            bw = QWidget()
            box = QVBoxLayout(bw)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(5)
            h = QLabel(T.CATEGORIES.get(cat, cat))
            h.setStyleSheet("font-weight:600")
            box.addWidget(h)
            for n in names:
                cb = QCheckBox(T.TOOL_LABELS.get(n, n))      # nombre comprensible; el interno, en el tooltip
                cb.setChecked(n not in off)
                cb.setToolTip("%s\n(%s)" % (T.TOOLS[n]["description"], n))
                cb.toggled.connect(lambda on, n=n: self._toggle_tool(n, on))
                box.addWidget(cb)
            box.addStretch(1)
            blocks.append(bw)
        v.addWidget(Columns(blocks))                         # dos columnas; una sola si los nombres no caben enteros
        self._section(v, tr("Búsqueda web"))
        self.field(v, "search_provider", tr("Buscador"), "choice",
                   choices=[(tr("Automático (DuckDuckGo; si lo bloquea, Wikipedia)"), "auto"), (tr("Brave Search (necesita clave)"), "brave"), (tr("SearXNG (tu propio buscador)"), "searxng")])
        self.field(v, "brave_key", tr("Clave de Brave Search"), "secret", help=tr("Gratis en api.search.brave.com para uso personal."))
        self.field(v, "searxng_url", tr("URL de SearXNG"), "text", placeholder="http://127.0.0.1:8888")
        self._section(v, tr("Servicios con tu cuenta"))
        from .conectores_ui import services_grid
        v.addWidget(lbl(tr("Opcional: conecta servicios en línea para que el agente trabaje con ellos (Gmail, Drive, Notion, "
                           "Higgsfield…). Inicias sesión tú en la página de cada servicio; %s no ve tu contraseña y guarda el permiso "
                           "cifrado en este equipo. Lo que cambie algo en tu cuenta (enviar, publicar, gastar créditos) siempre te lo "
                           "pregunta.") % APP_NAME, "faint"))
        self.svc_grid = services_grid(lambda: QTimer.singleShot(0, self._mcp_render))
        v.addWidget(self.svc_grid)
        self._section(v, tr("Conectores MCP"))
        v.addWidget(lbl(tr("Amplían lo que puede hacer el agente con herramientas externas (archivos, GitHub, bases de datos, navegador, "
                        "Notion…) mediante el estándar Model Context Protocol. Pueden ser un programa de tu equipo o un servicio "
                        "remoto con su dirección; si pide iniciar sesión, se abre su página."), "faint"))
        self.mcp_box = QVBoxLayout()
        self.mcp_box.setSpacing(6)
        v.addLayout(self.mcp_box)
        self._mcp_render()
        f = QFrame()
        f.setObjectName("noteBox")
        g = QGridLayout(f)
        g.setContentsMargins(12, 10, 12, 10)
        g.setVerticalSpacing(6)
        title = QLabel(tr("Añadir conector"))
        title.setStyleSheet("font-weight:600")
        g.addWidget(title, 0, 0)
        self.mcp_tpl = QComboBox()
        self.mcp_tpl.addItem(tr("Plantillas…"), None)
        for t in MCP_TEMPLATES:
            self.mcp_tpl.addItem(t["label"], t)
        self.mcp_tpl.activated.connect(self._mcp_template)
        g.addWidget(self.mcp_tpl, 0, 1)
        self.mcp_kind = QComboBox()
        self.mcp_kind.addItem(tr("Programa de este equipo"), "local")
        self.mcp_kind.addItem(tr("Servicio remoto (dirección web)"), "remote")
        self.mcp_kind.currentIndexChanged.connect(self._mcp_kind_changed)
        self.mcp_name = QLineEdit()
        self.mcp_name.setPlaceholderText(tr("Nombre (p. ej. Archivos)"))
        g.addWidget(self.mcp_name, 1, 0)
        g.addWidget(self.mcp_kind, 1, 1)
        self.mcp_cmd = QLineEdit()
        self.mcp_cmd.setPlaceholderText(tr("Comando (p. ej. npx, uvx o python)"))
        self.mcp_args = QLineEdit()
        self.mcp_args.setPlaceholderText(tr("Argumentos (p. ej. -y @modelcontextprotocol/server-filesystem C:\\Users\\tú\\Documents)"))
        self.mcp_env = QLineEdit()
        self.mcp_env.setPlaceholderText(tr("Variables (opcional): CLAVE=valor; OTRA=valor"))
        self.mcp_url = QLineEdit()
        self.mcp_url.setPlaceholderText(tr("Dirección del servicio (p. ej. https://servicio.com/mcp)"))
        self.mcp_hdr = QLineEdit()
        self.mcp_hdr.setPlaceholderText(tr("Clave o token (opcional): se envía como «Authorization: Bearer …»"))
        self.mcp_hdr.setEchoMode(QLineEdit.Password)
        g.addWidget(self.mcp_cmd, 2, 0, 1, 2)
        g.addWidget(self.mcp_args, 3, 0, 1, 2)
        g.addWidget(self.mcp_env, 4, 0, 1, 2)
        g.addWidget(self.mcp_url, 5, 0, 1, 2)
        g.addWidget(self.mcp_hdr, 6, 0, 1, 2)
        self.mcp_res = lbl("", "faint")
        g.addWidget(self.mcp_res, 7, 0)
        g.addWidget(btn(tr("Añadir y probar"), "primary", self._mcp_add, "acc_anadir"), 7, 1, Qt.AlignRight)
        v.addWidget(f)
        self._mcp_kind_changed()

    def _mcp_kind_changed(self, *_):
        remote = self.mcp_kind.currentData() == "remote"
        for w in (self.mcp_cmd, self.mcp_args, self.mcp_env):
            w.setVisible(not remote)
        for w in (self.mcp_url, self.mcp_hdr):
            w.setVisible(remote)

    def _mcp_template(self, i):
        t = self.mcp_tpl.itemData(i)
        if not t:
            return
        self.mcp_name.setText(t["name"])
        self.mcp_kind.setCurrentIndex(1 if t.get("url") else 0)
        ws = core.SET.snapshot().get("workspace") or os.path.expanduser("~")
        if t.get("url"):
            self.mcp_url.setText(t["url"])
            self.mcp_hdr.clear()
        else:
            self.mcp_cmd.setText(t["command"])
            self.mcp_args.setText(" ".join(('"%s"' % a if " " in a else a) for a in [x.replace("{carpeta}", ws) for x in t["args"]]))
            self.mcp_env.setText(t.get("env", ""))
        self.mcp_res.setText(t.get("note", ""))
        self.mcp_tpl.setCurrentIndex(0)

    def _mcp_render(self):
        from . import harness
        while self.mcp_box.count():
            it = self.mcp_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        servers = [s for s in core.SET.snapshot().get("mcp_servers") or [] if not s.get("catalog")]   # los del catálogo, en sus fichas
        if not servers:
            self.mcp_box.addWidget(lbl(tr("Aún no hay conectores. Elige una plantilla abajo o añade el tuyo."), "faint"))
        for s in servers:
            row = QFrame()
            row.setObjectName("noteBox")
            h = QHBoxLayout(row)
            h.setContentsMargins(12, 6, 6, 6)
            srv = harness.MCP.get(s["name"])
            err = harness.MCP_STATUS.get(s["name"])
            if not s.get("enabled", True):
                state, col = tr("○ desactivado"), C["faint"]
            elif srv:
                state, col = tr("● conectado · %d herramientas") % len(srv.tools), C["ok"]
            elif err:
                state, col = tr("✗ no conecta"), C["bad"]
            else:
                state, col = tr("○ sin conectar"), C["faint"]
            full = s.get("url") or ("%s %s" % (s.get("command", ""), " ".join(s.get("args") or [])))
            short = lambda a: ("…" + os.sep + os.path.basename(a.rstrip("\\/"))) if os.path.isabs(a) and len(a) > 32 else a
            where = s.get("url") or " ".join([os.path.basename(s.get("command", ""))] + [short(a) for a in s.get("args") or []])
            info = lbl("<b>%s</b>  <span style='color:%s'>%s</span><br><span style='color:%s'>%s</span>%s" % (
                html_escape(s["name"]), col, state, C["faint"], html_escape(where[:140]),
                ("<br><span style='color:%s'>%s</span>" % (C["bad"], html_escape(short_paths(err)[:220])))
                if err and not srv and s.get("enabled", True) else ""))
            tip = full
            if srv and srv.tools:
                tip += "\n\n" + tr("Herramientas:\n%s") % "\n".join("• %s — %s" % (t["name"], (t.get("description") or "")[:80]) for t in srv.tools[:40])
            info.setToolTip(tip)
            h.addWidget(info, 1)
            if s.get("auth") == "oauth":
                from . import oauth
                if oauth.signed_in(s["url"]):
                    h.addWidget(btn(tr("Cerrar sesión"), None, lambda _=False, s=s: (oauth.logout(s["url"]), self._mcp_update(s["name"], reconnect=True))))
                else:
                    h.addWidget(btn(tr("Iniciar sesión"), "primary", lambda _=False, s=s: self._mcp_login(s), "hub_conectar"))
            cb = QCheckBox(tr("Activo"))
            cb.setChecked(s.get("enabled", True))
            cb.toggled.connect(lambda on, n=s["name"]: self._mcp_update(n, enabled=on))
            h.addWidget(cb)
            h.addWidget(btn(tr("Reconectar"), None, lambda _=False, n=s["name"]: self._mcp_update(n, reconnect=True), "acc_refrescar"))
            h.addWidget(btn(tr("Quitar"), "danger", lambda _=False, n=s["name"]: self._mcp_update(n, remove=True)))
            self.mcp_box.addWidget(row)

    def _mcp_update(self, name, enabled=None, remove=False, reconnect=False):
        from . import harness
        servers = [dict(s) for s in core.SET.snapshot().get("mcp_servers") or [] if not (remove and s["name"] == name)]
        for s in servers:
            if s["name"] == name and enabled is not None:
                s["enabled"] = enabled
        core.SET.update({"mcp_servers": servers})
        if reconnect and name in harness.MCP:
            harness.MCP.pop(name).stop()
        run_bg(lambda: harness.mcp_sync(servers), lambda r: self._mcp_render())

    def _mcp_add(self):
        import shlex
        from . import harness
        name = self.mcp_name.text().strip()
        remote = self.mcp_kind.currentData() == "remote"
        if remote:
            url = self.mcp_url.text().strip()
            if not name or not re.match(r"(?i)https?://", url):
                return self.mcp_res.setText(tr("Escribe un nombre y una dirección que empiece por https://"))
            entry = {"name": name, "url": url, "enabled": True}
            tok = self.mcp_hdr.text().strip()
            if tok:
                entry["headers"] = {"Authorization": tok if " " in tok else "Bearer " + tok}
        else:
            cmd = self.mcp_cmd.text().strip()
            if not name or not cmd:
                return self.mcp_res.setText(tr("Escribe un nombre y un comando."))
            if cmd in ("npx", "node") and not shutil.which("npx"):
                return self.mcp_res.setText(tr("Este conector necesita Node.js. Instálalo desde nodejs.org y vuelve a intentarlo."))
            if cmd == "uvx" and not shutil.which("uvx"):
                return self.mcp_res.setText(tr("Este conector necesita uv (docs.astral.sh/uv). Instálalo y vuelve a intentarlo."))
            try:
                args = [a.strip('"') for a in shlex.split(self.mcp_args.text(), posix=False)]
            except ValueError:
                args = self.mcp_args.text().split()
            env = {}
            for part in re.split(r"[;\n]", self.mcp_env.text()):
                if "=" in part:
                    k, val = part.split("=", 1)
                    env[k.strip()] = val.strip()
            entry = {"name": name, "command": cmd, "args": args, "enabled": True}
            if env:
                entry["env"] = env
        servers = [s for s in core.SET.snapshot().get("mcp_servers") or [] if s["name"] != name] + [entry]
        core.SET.update({"mcp_servers": servers})
        self.mcp_res.setText(tr("Conectando… (la primera vez npx o uvx pueden tardar en descargar el conector)") if not remote else
                             tr("Conectando… si el servicio pide iniciar sesión, se abrirá su página en tu navegador."))

        def work():
            if remote and not entry.get("headers"):        # ¿pide iniciar sesión con una cuenta? (OAuth del estándar MCP)
                from . import oauth
                wa = oauth.probe(entry["url"])
                if wa is not None:
                    entry["auth"] = "oauth"
                    core.SET.update({"mcp_servers": servers})
                    oauth.login(entry["url"], www_auth=wa)
            return harness.mcp_sync(servers)

        def done(st):
            if isinstance(st, Exception):
                self.mcp_res.setText("✗ %s" % st)
            elif st.get(name):
                self.mcp_res.setText(tr("✗ No se pudo conectar: %s") % st[name][:220])
            else:
                n = len(harness.MCP[name].tools) if name in harness.MCP else 0
                self.mcp_res.setText(tr("✓ Conectado: %d herramientas disponibles para el agente.") % n)
                for w in (self.mcp_name, self.mcp_cmd, self.mcp_args, self.mcp_env, self.mcp_url, self.mcp_hdr):
                    w.clear()
            self._mcp_render()
        run_bg(work, done)

    def _mcp_login(self, s):
        """Iniciar sesión en un conector remoto añadido a mano que pide cuenta."""
        from . import harness, oauth
        self.mcp_res.setText(tr("Inicia sesión en la ventana del navegador que se abrió…"))
        run_bg(lambda: (oauth.login(s["url"]), harness.MCP.pop(s["name"], None), harness.mcp_sync(core.SET.snapshot().get("mcp_servers") or []))[2],
               lambda r: (self.mcp_res.setText(("✗ %s" % r) if isinstance(r, Exception) else tr("✓ Sesión iniciada en %s.") % s["name"]),
                          self._mcp_render()))

    def _toggle_tool(self, name, on):
        off = set(core.SET.snapshot()["tools_disabled"])
        off.discard(name) if on else off.add(name)
        self._save("tools_disabled", sorted(off))

    def p_images(self, v):
        from . import imagegen as IG, provision as P
        from .imagen_ui import ImageInstallBox
        v.addWidget(lbl(tr("El agente puede crear imágenes (fotos, ilustraciones, logotipos, iconos…) en tu propio equipo, sin "
                           "internet ni servicios externos, con stable-diffusion.cpp y un modelo de imagen de licencia libre. Solo "
                           "se usa cuando el modelo de texto activo no crea imágenes por sí mismo."), "faint"))
        self.field(v, "image_gen", tr("Permitir que el agente cree imágenes"), "bool",
                   help=tr("Las crea cuando se lo pides o cuando una tarea las necesita (una web, una presentación…). Cada una "
                           "se aprueba como el resto de acciones de escritura y aparece en el chat."))
        self._section(v, tr("Modelo de imagen"))
        self.field(v, "image_model", tr("Modelo elegido"), "choice",
                   choices=[(tr("Automático (según tu equipo)"), "auto")] +
                           [("%s · %s · %s" % (m["name"], P.fmt_bytes(IG.total_size(m)), m["license"]), m["id"]) for m in IG.MODELS],
                   help=tr("En automático: Segmind Vega RT (rápido) sin tarjeta gráfica y FLUX.2 [klein] con ella. FLUX.2 y Z-Image "
                           "comparten el lector de la descripción: si instalas los dos, descarga menos."))
        self.img_box = ImageInstallBox(removable=True)
        v.addWidget(self.img_box)
        self._section(v, tr("Imágenes creadas"))
        self.field(v, "image_size", tr("Tamaño de las imágenes"), "choice",
                   choices=[(tr("Automático (según tu equipo)"), "auto"), (tr("512 px (más rápido)"), "512"), ("768 px", "768"),
                            (tr("1024 px (más detalle)"), "1024")],
                   help=tr("El lado de una imagen cuadrada; las horizontales y verticales tienen los mismos píxeles. En automático, "
                           "512 px sin tarjeta gráfica y 1024 px con ella."))
        self.field(v, "image_dir", tr("Carpeta donde se guardan"), "dir",
                   help=tr("Vacío: la carpeta «%s» dentro de la carpeta de trabajo o del proyecto.") % tr("imagenes"))
        v.addWidget(lbl(tr("Licencias: stable-diffusion.cpp y TAESDXL son MIT; FLUX.2 [klein] 4B, Z-Image Turbo, Qwen3 4B y Segmind Vega "
                           "son Apache-2.0. Ambas permiten también el uso comercial. Registro de la última imagen: %s") % IG.LOG, "faint"))

    # ---- conocimiento local (conocimiento.py)
    def p_knowledge(self, v):
        from . import conocimiento as KN, provision as P
        v.addWidget(lbl(tr("Elige carpetas (notas, documentos, proyectos) y el agente buscará en ellas por significado, sin tener "
                           "que leerlas enteras: ideal con modelos locales, que tienen poca memoria de conversación. Todo se queda "
                           "en tu equipo."), "faint"))
        self._section(v, tr("Buscador por significado"))
        self.kn_model = lbl("")
        row = QHBoxLayout()
        self.kn_install = btn(tr("Instalar (%s)") % P.fmt_bytes(KN.EMB["size"]), "primary", self._kn_install, "acc_descargar")
        row.addWidget(self.kn_install)
        row.addStretch(1)
        box = QVBoxLayout()
        box.setSpacing(8)
        box.addWidget(self.kn_model)
        box.addLayout(row)
        v.addLayout(box)
        self._section(v, tr("Carpetas de conocimiento"))
        self.kn_list = QVBoxLayout()
        self.kn_list.setSpacing(6)
        v.addLayout(self.kn_list)
        r = QHBoxLayout()
        r.addWidget(btn(tr("Añadir carpeta…"), None, self._kn_add, "acc_anadir"))
        r.addStretch(1)
        v.addLayout(r)
        self._section(v, tr("Índice"))
        self.kn_stats = lbl("")
        r = QHBoxLayout()
        self.kn_btn = btn(tr("Actualizar el índice"), None, self._kn_index, "acc_refrescar")
        self.kn_cancel = btn(tr("Cancelar"), None, self._kn_stop)
        r.addWidget(self.kn_btn)
        r.addWidget(self.kn_cancel)
        r.addStretch(1)
        box = QVBoxLayout()
        box.setSpacing(8)
        box.addWidget(self.kn_stats)
        box.addLayout(r)
        v.addLayout(box)
        self.field(v, "knowledge_auto", tr("Actualizar el índice al abrir %s") % APP_NAME, "bool",
                   help=tr("Solo vuelve a leer los archivos nuevos o cambiados."))
        self._kn_timer = QTimer(self, interval=500, timeout=self._kn_refresh)
        self._kn_render()
        self._kn_refresh()

    def _kn_render(self):
        from . import conocimiento as KN
        while self.kn_list.count():
            w = self.kn_list.takeAt(0).widget()
            if w:
                w.deleteLater()
        fs = KN.folders()
        if not fs:
            self.kn_list.addWidget(lbl(tr("Aún no hay carpetas. Añade las que quieras que el agente pueda consultar."), "faint"))
        for f in fs:
            row = QFrame()
            row.setObjectName("noteBox")
            h = QHBoxLayout(row)
            h.setContentsMargins(10, 4, 4, 4)
            h.addWidget(lbl(f), 1)
            h.addWidget(btn(tr("Quitar"), "danger", lambda _=False, f=f: self._kn_remove(f)))
            self.kn_list.addWidget(row)

    def _kn_add(self):
        from . import conocimiento as KN
        d = QFileDialog.getExistingDirectory(self, tr("Carpeta de conocimiento"), os.path.expanduser("~"))
        if not d:
            return
        d = os.path.normpath(d)
        fs = KN.folders()
        if d not in fs:
            core.SET.update({"knowledge_folders": fs + [d]})
        self._kn_render()
        if KN.installed():
            self._kn_index()

    def _kn_remove(self, f):
        from . import conocimiento as KN
        core.SET.update({"knowledge_folders": [x for x in KN.folders() if x != f]})
        self._kn_render()
        if KN.installed():
            self._kn_index()                   # olvida lo que ya no está en ninguna carpeta

    def _kn_install(self):
        from . import conocimiento as KN
        KN.install()
        self._kn_timer.start()
        self._kn_refresh()

    def _kn_index(self):
        from . import conocimiento as KN
        if not KN.installed():
            return self._kn_refresh()
        KN.start_index()
        self._kn_timer.start()
        self._kn_refresh()

    def _kn_stop(self):
        from . import conocimiento as KN
        if KN.INDEX_JOB and KN.INDEX_JOB.get("running"):
            KN.INDEX_JOB["stop"].set()
        elif KN.JOB is not None and not KN.JOB.finished:
            KN.JOB.cancel()

    def _kn_refresh(self):
        from . import conocimiento as KN, provision as P
        job, ij = KN.JOB, KN.INDEX_JOB
        downloading = job is not None and not job.finished
        indexing = bool(ij and ij.get("running"))
        if KN.installed():
            self.kn_model.setText(tr("✓ Instalado: Qwen3-Embedding 0.6B (Apache-2.0), en tu equipo."))
        elif downloading:
            self.kn_model.setText(tr("Instalando: %s") % P.describe_overall(job.overall()))
        elif job is not None and job.error:
            self.kn_model.setText(tr("No se pudo instalar: %s") % job.error)
        else:
            self.kn_model.setText(tr("Hace falta descargarlo una vez (%s). Entiende español, inglés, portugués y muchos más idiomas.")
                                  % P.fmt_bytes(KN.EMB["size"]))
        self.kn_install.setVisible(not KN.installed() and not downloading)
        st = KN.stats()
        if indexing:
            txt = tr("Actualizando: %s") % ij["text"]
        elif ij and ij.get("error"):
            txt = tr("No se pudo actualizar: %s") % ij["error"]
        elif st["chunks"]:
            txt = tr("%d archivos · %d fragmentos · actualizado %s") % (st["files"], st["chunks"], core.SET.snapshot().get("knowledge_indexed") or "—")
        else:
            txt = tr("Vacío.") if KN.installed() else tr("Se crea al instalar el buscador y elegir carpetas.")
        self.kn_stats.setText(txt)
        self.kn_btn.setVisible(KN.installed() and bool(KN.folders()) and not indexing)
        self.kn_cancel.setVisible(indexing or downloading)
        if not indexing and not downloading and self._kn_timer.isActive():
            self._kn_timer.stop()
            if KN.installed() and KN.folders() and job is not None and job.finished and not job.error and not st["chunks"]:
                self._kn_index()               # recién instalado: primer índice

    def p_data(self, v):
        v.addWidget(lbl(tr("Todo se guarda solo en este equipo. %s no envía tus conversaciones ni archivos a ningún servidor. "
                        "Solo se conecta a internet para descargar modelos y para las herramientas web que tú permitas.") % APP_NAME, "muted"))
        r = QHBoxLayout()
        r.addWidget(lbl(tr("Datos: %s") % paths.HOME, "faint"), 1)
        r.addWidget(btn(tr("Abrir carpeta"), cb=lambda: osys.open_path(paths.HOME), ico="act_carpeta_abierta"))
        v.addLayout(r)
        self._section(v, tr("Conversaciones"))
        n = len(core.SESSIONS)
        r = QHBoxLayout()
        r.addWidget(btn(tr("Exportar conversaciones (Markdown)…"), cb=self._export, ico="acc_descargar"))
        r.addStretch(1)
        v.addLayout(r)
        imgs = unused_images()
        size = sum(os.path.getsize(f) for f in imgs if os.path.isfile(f))
        r = QHBoxLayout()
        b = btn(tr("Liberar espacio: borrar %d imágenes sin usar (%s)") % (len(imgs), HW.human(size)), cb=self._clean_images, ico="acc_eliminar")
        b.setEnabled(bool(imgs))
        r.addWidget(b)
        r.addStretch(1)
        v.addLayout(r)
        r = QHBoxLayout()
        r.addWidget(btn(tr("Borrar todas las conversaciones (%d)…") % n, "danger", self._delete_all))
        r.addStretch(1)
        v.addLayout(r)

    def _export(self):
        d = QFileDialog.getExistingDirectory(self, tr("Exportar conversaciones a…"), os.path.expanduser("~"))
        if d:
            QMessageBox.information(self, tr("Exportado"), tr("%d conversaciones exportadas a %s") % (export_conversations(d), d))

    def _clean_images(self):
        for f in unused_images():
            try:
                os.remove(f)
            except OSError:
                pass
        self._reload("Datos y privacidad")

    def _delete_all(self):
        n = len(core.SESSIONS)
        if QMessageBox.question(self, tr("Borrar todo"), tr("Se borrarán permanentemente %d conversaciones (las de Chat y las de tus proyectos). "
                                "No se puede deshacer. ¿Continuar?") % n) != QMessageBox.StandardButton.Yes:
            return
        for s in list(core.SESSIONS.values()):
            s.delete()
        self._reload("Datos y privacidad")

    def p_log(self, v):
        self.log = QPlainTextEdit(core.LLM_MGR.tail(300) or tr("(vacío)"))
        self.log.setObjectName("mono")
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(380)
        v.addWidget(self.log)
        v.addWidget(lbl(tr("Comando: %s") % " ".join(core.LLM_MGR.command()), "faint"))
        r = QHBoxLayout()
        r.addWidget(btn(tr("Actualizar"), cb=lambda: self.log.setPlainText(core.LLM_MGR.tail(300) or tr("(vacío)")), ico="acc_refrescar"))
        r.addStretch(1)
        v.addLayout(r)

    def p_keys(self, v):
        g = QGridLayout()
        g.setHorizontalSpacing(24)
        for i, (k, d) in enumerate(SHORTCUTS):
            kl = QLabel(keys_text(k))
            kl.setStyleSheet("font-family: '%s'; color:%s" % (osys.mono_font(), C["acc"]))
            g.addWidget(kl, i, 0)
            g.addWidget(QLabel(d), i, 1)
        g.setColumnStretch(1, 1)
        v.addLayout(g)

    def p_about(self, v):
        cfg = core.SET.snapshot()
        from .theme import make_icon
        head = QHBoxLayout()
        lg = QLabel()
        from .theme import logo
        lg.setPixmap(logo(64))
        head.addWidget(lg)
        tl = QVBoxLayout()
        n = QLabel(APP_NAME)
        n.setStyleSheet("font-size:18pt; font-weight:700")
        tl.addWidget(n)
        tl.addWidget(lbl(tr("Agente de IA local para tu escritorio · versión %s") % __version__, "muted"))
        tl.addWidget(lbl(tr("Creado por Ing. Jeison Tuiran"), "muted"))
        head.addLayout(tl, 1)
        v.addLayout(head)
        lic = lbl(tr("Software libre con licencia GNU GPL-3.0 · Copyright (C) 2026 Ing. Jeison Tuiran.\nEl nombre «Jayth» y su logotipo son la marca "
                  "del proyecto: las versiones modificadas deben llevar otro nombre."), "faint")
        lic.setWordWrap(True)
        v.addWidget(lic)
        r = QHBoxLayout()
        r.addWidget(btn(tr("Ver la licencia"), cb=lambda: webbrowser.open("https://github.com/%s/blob/main/LICENSE" % REPO), ico="est_info"))
        r.addWidget(btn(tr("Política de marca"), cb=lambda: webbrowser.open("https://github.com/%s/blob/main/MARCA.md" % REPO), ico="est_info"))
        r.addStretch(1)
        v.addLayout(r)
        commit = local_commit()
        v.addWidget(lbl(tr("Código: %s%s\nMotor: llama.cpp %s\nDatos: %s") % (paths.APP_DIR, (" · " + commit[:7]) if commit else "", cfg["llama_tag"] or "—", paths.HOME), "faint"))
        self.upd = lbl("", "muted")
        self.upd.hide()
        r = QHBoxLayout()
        r.addWidget(btn(tr("Buscar actualizaciones"), cb=self._check_updates, ico="acc_refrescar"))
        r.addWidget(btn(tr("Abrir en GitHub"), cb=lambda: webbrowser.open("https://github.com/" + REPO), ico="acc_abrir_externo"))
        r.addStretch(1)
        box = QVBoxLayout()                    # el resultado de la búsqueda aparece bajo los botones (sin banda vacía antes)
        box.setSpacing(8)
        box.addLayout(r)
        box.addWidget(self.upd)
        v.addLayout(box)
        self._section(v, tr("Novedades"))
        self.field(v, "auto_update_check", tr("Avisarme cuando haya una versión nueva de %s") % APP_NAME, "bool")
        self.field(v, "auto_install_updates", tr("Descargar las actualizaciones en segundo plano e instalarlas al cerrar %s") % APP_NAME, "bool",
                   help=tr("No interrumpe lo que estés haciendo. Si quieres tenerla antes, pulsa «Reiniciar para actualizar» en la "
                           "barra lateral cuando te venga bien."))
        self.field(v, "model_news", tr("Avisarme cuando se publique una versión nueva de mis modelos"), "bool",
                   help=tr("Busca en Hugging Face versiones más recientes de la misma familia, tamaño y variante (p. ej. de Gemma 3 12B a Gemma 4 12B)."))
        self._section(v, tr("Comentarios"))
        v.addWidget(lbl(tr("¿Encontraste un error o tienes una idea? Tu comentario ayuda a mejorar %s.") % APP_NAME, "muted"))
        r = QHBoxLayout()
        from .feedback import FeedbackDialog
        r.addWidget(btn(tr("Informar de un error…"), cb=lambda: FeedbackDialog(self, "error").exec(), ico="est_error"))
        r.addWidget(btn(tr("Sugerir una mejora…"), cb=lambda: FeedbackDialog(self, "idea").exec(), ico="vfx_magia"))
        r.addStretch(1)
        v.addLayout(r)

    def _check_updates(self):
        self.upd.show()
        self.upd.setText(tr("Consultando GitHub…"))

        from . import updater

        def done(r):
            if isinstance(r, Exception):
                return self.upd.setText(tr("No se pudo consultar GitHub (¿sin internet?)."))
            if not r:
                return self.upd.setText(tr("✓ Tienes la última versión de %s.") % APP_NAME)
            self.upd.setText(tr("Hay una versión nueva (%s): «%s».\nSe descarga en segundo plano; cuando esté lista, pulsa «Reiniciar para "
                                "actualizar» en la barra lateral o se instalará al cerrar %s.") % (r.get("date") or r.get("version"), r["message"], APP_NAME))
            win = self.parent()
            if hasattr(win, "_got_app_news"):
                win._got_app_news(r, False)
        run_bg(updater.check_app, done)

    def _restart_llm(self):
        core.LLM_MGR.stop()
        err = core.LLM_MGR.start()
        if err:
            QMessageBox.warning(self, APP_NAME, err)
        self.banner.hide()
