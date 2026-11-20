"""Ventana de Ajustes con secciones (los cambios se guardan al instante)."""
import os, re, sys, json, subprocess, threading, webbrowser, urllib.request, datetime
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QListWidget, QListWidgetItem,
                               QStackedWidget, QScrollArea, QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit, QPlainTextEdit,
                               QFrame, QFileDialog, QMessageBox, QGridLayout)
from . import APP_NAME, __version__, core, paths, osys, hardware as HW, agent as A, tools as T
from .theme import C, icon, pix
from .wizard import SetupWizard, ModelsDialog, btn, lbl, browse_row, run_bg
import shutil
from html import escape as html_escape


def short_paths(text):
    """C:\\Users\\…\\carpeta\\archivo.py -> …\\archivo.py (los errores se leen mejor; la ruta completa va en el tooltip)."""
    return re.sub(r"[A-Za-z]:\\[^\s'\"]+", lambda m: "…\\" + m.group(0).replace("\\\\", "\\").rstrip("\\").split("\\")[-1], text or "")

# Conectores MCP conocidos: rellenan el formulario (el usuario revisa y pulsa «Añadir y probar»)
MCP_TEMPLATES = [
    {"label": "Archivos de una carpeta", "name": "Archivos", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "{carpeta}"],
     "note": "Da acceso a la carpeta indicada (puedes cambiarla en los argumentos). Necesita Node.js."},
    {"label": "Memoria (grafo de conocimiento)", "name": "Memoria", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"],
     "note": "El agente guarda y consulta datos entre conversaciones. Necesita Node.js."},
    {"label": "Navegador web (Playwright)", "name": "Navegador", "command": "npx", "args": ["-y", "@playwright/mcp@latest"],
     "note": "El agente abre y maneja un navegador real. Necesita Node.js."},
    {"label": "Pensamiento paso a paso", "name": "Pensamiento", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
     "note": "Ayuda a los modelos pequeños a razonar problemas largos. Necesita Node.js."},
    {"label": "Git (historial de un repositorio)", "name": "Git", "command": "uvx", "args": ["mcp-server-git", "--repository", "{carpeta}"],
     "note": "Consulta el historial y los cambios de un repositorio. Necesita uv."},
    {"label": "Leer páginas web (Fetch)", "name": "Fetch", "command": "uvx", "args": ["mcp-server-fetch"],
     "note": "Descarga páginas web convertidas a texto. Necesita uv."},
    {"label": "GitHub (remoto)", "name": "GitHub", "url": "https://api.githubcopilot.com/mcp/",
     "note": "Pega abajo un token personal de GitHub (github.com/settings/tokens)."},
]

REPO = "Json-Tuiran/jayth.ai"
NO_WINDOW = osys.NO_WINDOW
SYSTEM = "Windows" if osys.WIN else ("macOS" if osys.MAC else "Linux")
FILE_MANAGER = "el Explorador" if osys.WIN else ("el Finder" if osys.MAC else "el gestor de archivos")

LANGS = [("Automático (el idioma de tu mensaje)", "auto"), ("Español", "es"), ("English", "en"), ("Português", "pt"), ("Français", "fr"),
         ("Deutsch", "de"), ("Italiano", "it")]
SHORTCUTS = [("Ctrl+N", "Nueva conversación"), ("Ctrl+K", "Buscar en tus conversaciones"), ("Ctrl+1 / Ctrl+2", "Cambiar entre Chat y Code"),
             ("Ctrl+Shift+S", "Mostrar u ocultar la barra lateral"), ("Enter / Shift+Enter", "Enviar / nueva línea"),
             ("Ctrl+V", "Pegar una imagen en el mensaje"), ("Ctrl+S", "Guardar el archivo (Code)"), ("Ctrl+W", "Cerrar la pestaña (Code)"),
             ("Ctrl+`", "Mostrar u ocultar la terminal (Code)"), ("Ctrl+B", "Mostrar u ocultar el explorador de archivos (Code)"),
             ("Ctrl+L", "Mostrar u ocultar el panel del agente (Code)"), ("Ctrl+Shift+M", "Modo enfoque: solo el editor (Code)"),
             ("Doble clic en un divisor", "Plegar o recuperar el panel de al lado"), ("Esc", "Cerrar el buscador"),
             ("Ratón a la esquina superior izquierda", "Detener al instante el control del ratón")]


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
                lines += ["## Tú", "", e.get("text", ""), ""]
            elif e["t"] == "assistant_end" and e.get("text"):
                lines += ["## " + APP_NAME, "", e["text"], ""]
            elif e["t"] == "tool_call":
                lines += ["> Acción: `%s` %s" % (e["name"], json.dumps(e.get("args", {}), ensure_ascii=False)[:300]), ""]
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
class SettingsDialog(QDialog):
    def __init__(self, parent=None, page="General"):
        super().__init__(parent)
        self.setWindowTitle("Ajustes")
        self.resize(980, 680)
        self.before = core.SET.snapshot()
        self.timers = {}
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(230)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(10, 16, 10, 10)
        t = QLabel("Ajustes")
        t.setObjectName("h1")
        sv.addWidget(t)
        sv.addSpacing(6)
        self.nav = QListWidget()
        self.nav.setObjectName("history")
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
        bl.addWidget(QLabel("Algunos cambios se aplican al reiniciar el modelo."), 1)
        bl.addWidget(btn("Reiniciar modelo", "primary", self._restart_llm))
        self.banner.hide()
        bw = QWidget()
        bwl = QHBoxLayout(bw)
        bwl.setContentsMargins(24, 12, 24, 0)
        bwl.addWidget(self.banner)
        rv.addWidget(bw)
        self.pages = QStackedWidget()
        rv.addWidget(self.pages, 1)
        foot = QHBoxLayout()
        foot.setContentsMargins(24, 8, 24, 14)
        self.saved = QLabel("Los cambios se guardan automáticamente.")
        self.saved.setObjectName("faint")
        foot.addWidget(self.saved, 1)
        foot.addWidget(btn("Cerrar", "primary", self.accept))
        rv.addLayout(foot)
        root.addWidget(right, 1)
        for name, ico, build in (("General", "acc_ajustes", self.p_general), ("Personalización", "mat_comentario", self.p_personal),
                                 ("Modelos", "ia_controlador", self.p_models), ("Generación", "vfx_magia", self.p_generation),
                                 ("Rendimiento", "prof_cpu", self.p_performance), ("Agente y permisos", "est_bloqueado", self.p_agent),
                                 ("Herramientas", "cod_terminal", self.p_tools), ("Datos y privacidad", "prof_disco", self.p_data),
                                 ("Registro del modelo", "pan_consola", self.p_log), ("Atajos de teclado", "inp_teclado", self.p_keys),
                                 ("Acerca de", "est_info", self.p_about)):
            it = QListWidgetItem(icon(ico, C["mut"], 16), name)
            self.nav.addItem(it)
            self.pages.addWidget(self._scroll(name, build))
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        names = [self.nav.item(i).text() for i in range(self.nav.count())]
        self.nav.setCurrentRow(names.index(page) if page in names else 0)

    # ---- infraestructura
    def _scroll(self, title, build):
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        w = QWidget()
        w.setObjectName("chatHolder")
        sc.viewport().setObjectName("chatHolder")
        v = QVBoxLayout(w)
        v.setContentsMargins(28, 18, 28, 18)
        v.setSpacing(10)
        h = QLabel(title)
        h.setObjectName("h1")
        v.addWidget(h)
        build(v)
        v.addStretch(1)
        sc.setWidget(w)
        return sc

    def _section(self, v, text):
        l = QLabel(text.upper())
        l.setObjectName("section")
        v.addSpacing(6)
        v.addWidget(l)

    def _save(self, key, value):
        core.SET.update({key: value})
        self.saved.setText("Guardado ✓")
        QTimer.singleShot(1500, lambda: self.saved.setText("Los cambios se guardan automáticamente."))
        if key in core.RESTART_KEYS and core.LLM_MGR.mine():
            self.banner.show()
        if key == "start_with_windows":
            set_autostart(bool(value))

    def _debounced(self, key, getter, ms=600):
        t = self.timers.get(key)
        if t is None:
            t = QTimer(self, singleShot=True, interval=ms)
            t.timeout.connect(lambda: self._save(key, getter()))
            self.timers[key] = t
        t.start()

    def field(self, v, key, label, kind, help="", **kw):
        """Crea un control enlazado a un ajuste y lo guarda al cambiar."""
        val = core.SET.snapshot()[key]
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 2, 0, 2)
        bl.setSpacing(3)
        if kind == "bool":
            w = QCheckBox(label)
            w.setChecked(bool(val))
            w.toggled.connect(lambda on: self._save(key, on))
            bl.addWidget(w)
        else:
            bl.addWidget(QLabel(label))
            if kind == "int":
                w = QSpinBox()
                w.setRange(kw.get("min", 0), kw.get("max", 1_000_000))
                w.setValue(int(val))
                if kw.get("suffix"):
                    w.setSuffix(kw["suffix"])
                if kw.get("special"):
                    w.setSpecialValueText(kw["special"])
                w.valueChanged.connect(lambda x: self._debounced(key, w.value, 400))
                w.setMaximumWidth(220)
            elif kind == "float":
                w = QDoubleSpinBox()
                w.setRange(kw.get("min", 0.0), kw.get("max", 2.0))
                w.setSingleStep(kw.get("step", 0.05))
                w.setDecimals(kw.get("decimals", 2))
                w.setValue(float(val))
                w.valueChanged.connect(lambda x: self._debounced(key, w.value, 400))
                w.setMaximumWidth(220)
            elif kind == "choice":
                w = QComboBox()
                for t, d in kw["choices"]:
                    w.addItem(t, d)
                i = w.findData(val)
                if i < 0:
                    w.addItem(str(val), val)
                    i = w.count() - 1
                w.setCurrentIndex(i)
                w.currentIndexChanged.connect(lambda _: self._save(key, w.currentData()))
                w.setMaximumWidth(420)
            elif kind in ("text", "secret"):
                w = QLineEdit(str(val))
                if kind == "secret":
                    w.setEchoMode(QLineEdit.Password)
                if kw.get("placeholder"):
                    w.setPlaceholderText(kw["placeholder"])
                w.textChanged.connect(lambda _: self._debounced(key, w.text))
            elif kind in ("area", "list"):
                w = QPlainTextEdit("\n".join(val) if kind == "list" else str(val))
                w.setFixedHeight(kw.get("height", 96))
                if kw.get("placeholder"):
                    w.setPlaceholderText(kw["placeholder"])
                getter = (lambda: [l.strip() for l in w.toPlainText().splitlines() if l.strip()]) if kind == "list" else w.toPlainText
                w.textChanged.connect(lambda: self._debounced(key, getter))
            elif kind == "dir":
                w = QLineEdit(str(val))
                w.textChanged.connect(lambda _: self._debounced(key, w.text, 900))
                row = browse_row(w, folder=True, parent=self)
                wr = QWidget()
                wr.setLayout(row)
                row.setContentsMargins(0, 0, 0, 0)
                bl.addWidget(wr)
                w = None
            if w is not None:
                bl.addWidget(w)
        if help:
            h = QLabel(help)
            h.setObjectName("faint")
            h.setWordWrap(True)
            bl.addWidget(h)
        v.addWidget(box)
        return box

    # ---- paginas
    def p_general(self, v):
        self.field(v, "theme", "Tema", "choice", choices=[("Según el sistema", "system"), ("Oscuro", "dark"), ("Claro", "light")])
        self.field(v, "font_scale", "Tamaño del texto", "choice", choices=[("Pequeño", 90), ("Normal", 100), ("Grande", 115), ("Muy grande", 130)],
                   help="El tema y el tamaño se aplican al cerrar esta ventana.")
        self.field(v, "animations", "Animaciones (aparición de mensajes, barra lateral, avisos)", "bool")
        if osys.WIN:      # en macOS y Linux se usa siempre la barra del sistema (semáforos de macOS, decoraciones del escritorio)
            self.field(v, "custom_titlebar", "Barra de título integrada en la ventana", "bool",
                       help="Como en las apps de escritorio modernas. Si la desactivas se usa la barra de Windows (al reiniciar %s)." % APP_NAME)
        self._section(v, "Inicio y ventana")
        self.field(v, "start_with_windows", "Abrir %s al iniciar %s (minimizado en la bandeja)" % (APP_NAME, SYSTEM), "bool")
        self.field(v, "autostart_llm", "Encender el modelo al abrir %s" % APP_NAME, "bool",
                   help="Así está listo cuando lo necesites. Usa la memoria del modelo mientras la app esté abierta.")
        self.field(v, "close_to_tray", "Al cerrar la ventana, seguir funcionando en la bandeja del sistema", "bool")
        self.field(v, "notifications", "Avisarme cuando el agente necesite mi aprobación", "bool")
        self.field(v, "quick_hotkey", "Atajo de la ventana rápida", "text", placeholder="Ctrl+Alt+J",
                   help="Abre una barrita para preguntar a %s desde cualquier programa, con opción de adjuntar una captura de la pantalla. "
                        "Funciona mientras %s esté abierto (también en la bandeja). Déjalo vacío para desactivarlo." % (APP_NAME, APP_NAME))

    def p_personal(self, v):
        self.field(v, "user_name", "¿Cómo quieres que te llame?", "text", placeholder="Tu nombre (opcional)",
                   help="Se usa en el saludo y para que el agente sepa cómo dirigirse a ti.")
        self.field(v, "about_me", "¿Qué debería saber %s de ti?" % APP_NAME, "area",
                   placeholder="Ej.: Soy diseñador, trabajo con Python y Figma, uso %s y guardo mis proyectos en %s." % (SYSTEM, "D:\\Trabajo" if osys.WIN else "~/Trabajo"))
        self.field(v, "response_style", "¿Cómo quieres que responda?", "area",
                   placeholder="Ej.: Respuestas breves y directas, con ejemplos de código y sin relleno.")
        self.field(v, "response_language", "Idioma de las respuestas", "choice", choices=LANGS)
        self.field(v, "custom_instructions", "Instrucciones adicionales para el agente", "area",
                   placeholder="Ej.: Antes de borrar o mover archivos, explícame qué vas a hacer.")
        self._section(v, "Memoria")
        v.addWidget(lbl("Lo que %s recuerda de ti entre conversaciones (lo guarda cuando le dices algo duradero, como «uso pnpm»). "
                        "Puedes editarlo o borrarlo." % APP_NAME, "faint"))
        from . import harness
        self.mem = QPlainTextEdit(harness.memory_text(20000))
        self.mem.setPlaceholderText("- Prefiero respuestas cortas\n- Mis proyectos están en D:\\Trabajo")
        self.mem.setFixedHeight(120)
        self.mem.textChanged.connect(lambda: self._debounced("__memory__", lambda: self._save_memory(self.mem.toPlainText())))
        v.addWidget(self.mem)
        r = QHBoxLayout()
        r.addWidget(btn("Borrar la memoria", "danger", lambda: self.mem.setPlainText("")))
        r.addStretch(1)
        v.addLayout(r)
        v.addWidget(lbl("En los proyectos, %s también lee AGENTS.md, JAYTH.md o CLAUDE.md de la carpeta: escribe ahí las normas del proyecto." % APP_NAME, "faint"))

    def _save_memory(self, text):
        from . import harness
        os.makedirs(os.path.dirname(harness.MEMORY), exist_ok=True)
        with open(harness.MEMORY, "w", encoding="utf-8") as f:
            f.write(text.strip() + ("\n" if text.strip() else ""))
        return None

    def p_models(self, v):
        cfg = core.SET.snapshot()
        m = core.active_model(cfg)
        card = QFrame()
        card.setObjectName("noteBox")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.addWidget(lbl("<b>Modelo activo:</b> %s" % ((core.model_title(m) if m else "ninguno") if cfg["llm_mode"] == "local" else "servidor externo")))
        if m and cfg["llm_mode"] == "local":
            cl.addWidget(lbl("%s · %s · %s" % (core.model_quant(m) or "GGUF", HW.human(m.get("size", 0)), m.get("path", "")), "faint"))
        row = QHBoxLayout()
        row.addWidget(btn("Gestionar modelos…", cb=lambda: ModelsDialog(self).exec(), ico="ia_controlador"))
        row.addWidget(btn("Añadir modelo…", cb=lambda: SetupWizard(self, start="model").exec(), ico="acc_anadir"))
        row.addWidget(btn("Asistente de configuración…", cb=lambda: SetupWizard(self).exec(), ico="vfx_magia"))
        row.addStretch(1)
        cl.addLayout(row)
        v.addWidget(card)
        self.field(v, "models_dir", "Carpeta donde se descargan los modelos", "dir")
        self._section(v, "Proveedor")
        self.field(v, "llm_mode", "¿Qué motor usa el agente?", "choice",
                   choices=[("Local: llama.cpp en este equipo", "local"), ("Servidor externo compatible con OpenAI", "external")])
        self.field(v, "external_url", "URL del servidor externo (termina en /v1)", "text", placeholder="http://127.0.0.1:11434/v1",
                   help="Ollama: http://127.0.0.1:11434/v1 · LM Studio: http://127.0.0.1:1234/v1 · otro PC de tu red: http://IP:puerto/v1")
        self.field(v, "external_model", "Nombre del modelo en ese servidor", "text", placeholder="qwen3:8b")
        self.field(v, "external_key", "Clave de API (si el servidor la pide)", "secret")
        res = lbl("", "faint")
        b = btn("Probar conexión", cb=lambda: self._test_ext(res), ico="hub_conectar")
        r = QHBoxLayout()
        r.addWidget(b)
        r.addWidget(res, 1)
        v.addLayout(r)

    def _test_ext(self, out):
        cfg = core.SET.snapshot()
        out.setText("Probando…")

        def probe():
            req = urllib.request.Request(cfg["external_url"].rstrip("/") + "/models", headers={"Authorization": "Bearer " + (cfg["external_key"] or "local")})
            return [m.get("id") for m in json.loads(urllib.request.urlopen(req, timeout=5).read().decode("utf-8")).get("data", [])]
        run_bg(probe, lambda r: out.setText(("✗ No responde: %s" % r) if isinstance(r, Exception) else "✓ Conectado · " + (", ".join(r[:6]) or "sin modelos listados")))

    def p_generation(self, v):
        self.field(v, "thinking", "Pensar a fondo por defecto (mejores respuestas, más lento)", "bool")
        self.field(v, "sampling", "Parámetros de muestreo", "choice",
                   choices=[("Recomendados para el modelo activo (automático)", "auto"), ("Personalizados (los de abajo)", "custom")],
                   help="Automático usa los valores que publica cada laboratorio (Qwen, Gemma, Llama, Mistral, DeepSeek…) según si piensa o no.")
        self.field(v, "temperature", "Temperatura", "float", min=0, max=2, help="Más alta = más creativa y variada; más baja = más precisa y estable.")
        self.field(v, "max_tokens", "Longitud máxima de cada respuesta (tokens)", "int", min=64, max=65536)
        self._section(v, "Muestreo avanzado")
        self.field(v, "top_p", "Top-p", "float", min=0, max=1)
        self.field(v, "top_k", "Top-k", "int", min=0, max=500, special="sin límite")
        self.field(v, "min_p", "Min-p", "float", min=0, max=1)
        self.field(v, "repeat_penalty", "Penalización por repetición", "float", min=1, max=2, help="1,00 = desactivada.")
        self.field(v, "seed", "Semilla", "int", min=-1, max=2_000_000_000, special="aleatoria", help="Fija un número para obtener siempre la misma respuesta.")
        r = QHBoxLayout()
        r.addWidget(btn("Restablecer valores recomendados", cb=self._reset_generation))
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
        hw = lbl("Detectando tu equipo…")
        cl.addWidget(hw)
        cl.addWidget(lbl("Motor: llama.cpp %s · %s" % (cfg["llama_tag"] or "", {"cpu": "CPU", "cuda": "GPU NVIDIA (CUDA)", "vulkan": "GPU (Vulkan)"}.get(cfg["backend"], cfg["backend"])), "faint"))
        r = QHBoxLayout()
        r.addWidget(btn("Cambiar o actualizar el motor…", cb=lambda: SetupWizard(self).exec(), ico="acc_refrescar"))
        r.addStretch(1)
        cl.addLayout(r)
        v.addWidget(card)
        run_bg(HW.detect, lambda h: hw.setText(HW.summary(h) if not isinstance(h, Exception) else "No se pudo detectar el hardware."))
        self.field(v, "warmup", "Precalentar al encender el modelo", "bool",
                   help="Procesa una vez las instrucciones y herramientas del agente: el primer mensaje responde muchísimo antes.")
        self.field(v, "n_ctx", "Memoria de la conversación (contexto)", "choice",
                   choices=[("4 000 tokens", 4096), ("8 000 tokens", 8192), ("16 000 tokens (recomendado)", 16384), ("32 000 tokens", 32768),
                            ("64 000 tokens", 65536), ("128 000 tokens", 131072)], help="Más contexto permite tareas más largas, pero usa más memoria.")
        self.field(v, "idle_unload", "Apagar el modelo si no se usa durante", "choice",
                   choices=[("Nunca", 0), ("5 minutos", 5), ("15 minutos", 15), ("30 minutos", 30), ("1 hora", 60)], help="Libera memoria cuando no lo estás usando.")
        self._section(v, "Ajustes del motor")
        self.field(v, "threads", "Hilos de CPU", "int", min=1, max=256, help="Lo ideal suele ser el número de núcleos físicos.")
        self.field(v, "gpu_layers", "Capas en la GPU", "int", min=-1, max=999, special="automático", help="Solo con GPU. Automático reparte el modelo entre GPU y RAM.")
        self.field(v, "batch_size", "Tamaño de lote", "choice", choices=[(str(x), x) for x in (128, 256, 512, 1024, 2048)],
                   help="Más grande procesa más rápido los textos largos, con algo más de memoria.")
        self.field(v, "cache_type", "Contexto comprimido", "choice",
                   choices=[("No (máxima calidad)", "f16"), ("8 bits (la mitad de memoria, casi sin pérdida)", "q8_0"), ("4 bits (un cuarto de memoria)", "q4_0")])
        self.field(v, "flash_attn", "Flash attention", "choice", choices=[("Automático", "auto"), ("Activado", "on"), ("Desactivado", "off")])
        self.field(v, "mmap", "Cargar el modelo con mmap (arranque más rápido)", "bool")
        self.field(v, "mlock", "Bloquear el modelo en la RAM (evita que el sistema lo mueva al disco)", "bool",
                   help="Útil si tienes RAM de sobra; si no, puede ralentizar el equipo.")
        self.field(v, "llm_port", "Puerto local del motor", "int", min=1024, max=65535)

    def p_agent(self, v):
        self.field(v, "mode", "Permisos por defecto", "choice", choices=[(d, k) for k, d in A.MODES.items()])
        self.field(v, "workspace", "Carpeta de trabajo del modo Chat", "dir")
        self.field(v, "auto_allow_commands", "Comandos que se permiten sin preguntar", "list", height=90,
                   placeholder="git status\nnpm test\npython -m pytest",
                   help="Uno por línea. Se aplica si el comando empieza así y no encadena otros (; | &). Las acciones delicadas siempre preguntan.")
        self._section(v, "Límites")
        self.field(v, "max_steps", "Máximo de pasos por tarea", "int", min=1, max=500)
        self.field(v, "command_timeout", "Tiempo máximo de cada comando", "int", min=5, max=900, suffix=" s")
        self.field(v, "max_tool_output", "Máximo de texto que recibe el modelo de cada acción", "int", min=1000, max=200000, suffix=" caracteres")
        self.field(v, "vision", "Enviar capturas e imágenes al modelo (si tiene visión)", "bool")
        self.field(v, "keep_images", "Imágenes recientes que recuerda", "int", min=0, max=10)

    def p_tools(self, v):
        self.field(v, "web_access", "Permitir el acceso a internet (buscar, leer páginas y descargar)", "bool")
        self.field(v, "computer_control", "Permitir el control del ordenador (ratón, teclado, capturas)", "bool")
        self._section(v, "Herramientas disponibles")
        off = set(core.SET.snapshot()["tools_disabled"])
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        cats = {}
        for name, t in T.TOOLS.items():
            cats.setdefault(t["category"], []).append(name)
        col = 0
        for cat, names in cats.items():
            box = QVBoxLayout()
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
            grid.addLayout(box, col // 3, col % 3)
            col += 1
        v.addLayout(grid)
        self._section(v, "Búsqueda web")
        self.field(v, "search_provider", "Buscador", "choice",
                   choices=[("Automático (DuckDuckGo; si lo bloquea, Wikipedia)", "auto"), ("Brave Search (necesita clave)", "brave"), ("SearXNG (tu propio buscador)", "searxng")])
        self.field(v, "brave_key", "Clave de Brave Search", "secret", help="Gratis en api.search.brave.com para uso personal.")
        self.field(v, "searxng_url", "URL de SearXNG", "text", placeholder="http://127.0.0.1:8888")
        self._section(v, "Conectores MCP")
        v.addWidget(lbl("Amplían lo que puede hacer el agente con herramientas externas (archivos, GitHub, bases de datos, navegador, "
                        "Notion…) mediante el estándar Model Context Protocol. Pueden ser un programa de tu equipo o un servicio "
                        "remoto con su dirección y clave.", "faint"))
        self.mcp_box = QVBoxLayout()
        self.mcp_box.setSpacing(6)
        v.addLayout(self.mcp_box)
        self._mcp_render()
        f = QFrame()
        f.setObjectName("noteBox")
        g = QGridLayout(f)
        g.setContentsMargins(12, 10, 12, 10)
        g.setVerticalSpacing(6)
        title = QLabel("Añadir conector")
        title.setStyleSheet("font-weight:600")
        g.addWidget(title, 0, 0)
        self.mcp_tpl = QComboBox()
        self.mcp_tpl.addItem("Plantillas…", None)
        for t in MCP_TEMPLATES:
            self.mcp_tpl.addItem(t["label"], t)
        self.mcp_tpl.activated.connect(self._mcp_template)
        g.addWidget(self.mcp_tpl, 0, 1)
        self.mcp_kind = QComboBox()
        self.mcp_kind.addItem("Programa de este equipo", "local")
        self.mcp_kind.addItem("Servicio remoto (dirección web)", "remote")
        self.mcp_kind.currentIndexChanged.connect(self._mcp_kind_changed)
        self.mcp_name = QLineEdit()
        self.mcp_name.setPlaceholderText("Nombre (p. ej. Archivos)")
        g.addWidget(self.mcp_name, 1, 0)
        g.addWidget(self.mcp_kind, 1, 1)
        self.mcp_cmd = QLineEdit()
        self.mcp_cmd.setPlaceholderText("Comando (p. ej. npx, uvx o python)")
        self.mcp_args = QLineEdit()
        self.mcp_args.setPlaceholderText("Argumentos (p. ej. -y @modelcontextprotocol/server-filesystem C:\\Users\\tú\\Documents)")
        self.mcp_env = QLineEdit()
        self.mcp_env.setPlaceholderText("Variables (opcional): CLAVE=valor; OTRA=valor")
        self.mcp_url = QLineEdit()
        self.mcp_url.setPlaceholderText("Dirección del servicio (p. ej. https://servicio.com/mcp)")
        self.mcp_hdr = QLineEdit()
        self.mcp_hdr.setPlaceholderText("Clave o token (opcional): se envía como «Authorization: Bearer …»")
        self.mcp_hdr.setEchoMode(QLineEdit.Password)
        g.addWidget(self.mcp_cmd, 2, 0, 1, 2)
        g.addWidget(self.mcp_args, 3, 0, 1, 2)
        g.addWidget(self.mcp_env, 4, 0, 1, 2)
        g.addWidget(self.mcp_url, 5, 0, 1, 2)
        g.addWidget(self.mcp_hdr, 6, 0, 1, 2)
        self.mcp_res = lbl("", "faint")
        g.addWidget(self.mcp_res, 7, 0)
        g.addWidget(btn("Añadir y probar", "primary", self._mcp_add, "acc_anadir"), 7, 1, Qt.AlignRight)
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
        servers = core.SET.snapshot().get("mcp_servers") or []
        if not servers:
            self.mcp_box.addWidget(lbl("Aún no hay conectores. Elige una plantilla abajo o añade el tuyo.", "faint"))
        for s in servers:
            row = QFrame()
            row.setObjectName("noteBox")
            h = QHBoxLayout(row)
            h.setContentsMargins(12, 6, 6, 6)
            srv = harness.MCP.get(s["name"])
            err = harness.MCP_STATUS.get(s["name"])
            if not s.get("enabled", True):
                state, col = "○ desactivado", C["faint"]
            elif srv:
                state, col = "● conectado · %d herramientas" % len(srv.tools), C["ok"]
            elif err:
                state, col = "✗ no conecta", C["bad"]
            else:
                state, col = "○ sin conectar", C["faint"]
            full = s.get("url") or ("%s %s" % (s.get("command", ""), " ".join(s.get("args") or [])))
            short = lambda a: ("…" + os.sep + os.path.basename(a.rstrip("\\/"))) if os.path.isabs(a) and len(a) > 32 else a
            where = s.get("url") or " ".join([os.path.basename(s.get("command", ""))] + [short(a) for a in s.get("args") or []])
            info = lbl("<b>%s</b>  <span style='color:%s'>%s</span><br><span style='color:%s'>%s</span>%s" % (
                html_escape(s["name"]), col, state, C["faint"], html_escape(where[:140]),
                ("<br><span style='color:%s'>%s</span>" % (C["bad"], html_escape(short_paths(err)[:220])))
                if err and not srv and s.get("enabled", True) else ""))
            tip = full
            if srv and srv.tools:
                tip += "\n\nHerramientas:\n" + "\n".join("• %s — %s" % (t["name"], (t.get("description") or "")[:80]) for t in srv.tools[:40])
            info.setToolTip(tip)
            h.addWidget(info, 1)
            cb = QCheckBox("Activo")
            cb.setChecked(s.get("enabled", True))
            cb.toggled.connect(lambda on, n=s["name"]: self._mcp_update(n, enabled=on))
            h.addWidget(cb)
            h.addWidget(btn("Reconectar", None, lambda _=False, n=s["name"]: self._mcp_update(n, reconnect=True), "acc_refrescar"))
            h.addWidget(btn("Quitar", "danger", lambda _=False, n=s["name"]: self._mcp_update(n, remove=True)))
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
                return self.mcp_res.setText("Escribe un nombre y una dirección que empiece por https://")
            entry = {"name": name, "url": url, "enabled": True}
            tok = self.mcp_hdr.text().strip()
            if tok:
                entry["headers"] = {"Authorization": tok if " " in tok else "Bearer " + tok}
        else:
            cmd = self.mcp_cmd.text().strip()
            if not name or not cmd:
                return self.mcp_res.setText("Escribe un nombre y un comando.")
            if cmd in ("npx", "node") and not shutil.which("npx"):
                return self.mcp_res.setText("Este conector necesita Node.js. Instálalo desde nodejs.org y vuelve a intentarlo.")
            if cmd == "uvx" and not shutil.which("uvx"):
                return self.mcp_res.setText("Este conector necesita uv (docs.astral.sh/uv). Instálalo y vuelve a intentarlo.")
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
        self.mcp_res.setText("Conectando… (la primera vez npx o uvx pueden tardar en descargar el conector)")

        def done(st):
            if isinstance(st, Exception):
                self.mcp_res.setText("✗ %s" % st)
            elif st.get(name):
                self.mcp_res.setText("✗ No se pudo conectar: %s" % st[name][:220])
            else:
                n = len(harness.MCP[name].tools) if name in harness.MCP else 0
                self.mcp_res.setText("✓ Conectado: %d herramientas disponibles para el agente." % n)
                for w in (self.mcp_name, self.mcp_cmd, self.mcp_args, self.mcp_env, self.mcp_url, self.mcp_hdr):
                    w.clear()
            self._mcp_render()
        run_bg(lambda: harness.mcp_sync(servers), done)

    def _toggle_tool(self, name, on):
        off = set(core.SET.snapshot()["tools_disabled"])
        off.discard(name) if on else off.add(name)
        self._save("tools_disabled", sorted(off))

    def p_data(self, v):
        v.addWidget(lbl("Todo se guarda solo en este equipo. %s no envía tus conversaciones ni archivos a ningún servidor. "
                        "Solo se conecta a internet para descargar modelos y para las herramientas web que tú permitas." % APP_NAME, "muted"))
        r = QHBoxLayout()
        r.addWidget(lbl("Datos: " + paths.HOME, "faint"), 1)
        r.addWidget(btn("Abrir carpeta", cb=lambda: osys.open_path(paths.HOME), ico="act_carpeta_abierta"))
        v.addLayout(r)
        self._section(v, "Conversaciones")
        n = len(core.SESSIONS)
        r = QHBoxLayout()
        r.addWidget(btn("Exportar conversaciones (Markdown)…", cb=self._export, ico="acc_descargar"))
        r.addStretch(1)
        v.addLayout(r)
        imgs = unused_images()
        size = sum(os.path.getsize(f) for f in imgs if os.path.isfile(f))
        r = QHBoxLayout()
        b = btn("Liberar espacio: borrar %d imágenes sin usar (%s)" % (len(imgs), HW.human(size)), cb=self._clean_images, ico="acc_eliminar")
        b.setEnabled(bool(imgs))
        r.addWidget(b)
        r.addStretch(1)
        v.addLayout(r)
        r = QHBoxLayout()
        r.addWidget(btn("Borrar todas las conversaciones (%d)…" % n, "danger", self._delete_all))
        r.addStretch(1)
        v.addLayout(r)

    def _export(self):
        d = QFileDialog.getExistingDirectory(self, "Exportar conversaciones a…", os.path.expanduser("~"))
        if d:
            QMessageBox.information(self, "Exportado", "%d conversaciones exportadas a %s" % (export_conversations(d), d))

    def _clean_images(self):
        for f in unused_images():
            try:
                os.remove(f)
            except OSError:
                pass
        self._reload("Datos y privacidad")

    def _delete_all(self):
        n = len(core.SESSIONS)
        if QMessageBox.question(self, "Borrar todo", "Se borrarán permanentemente %d conversaciones (las de Chat y las de tus proyectos). "
                                "No se puede deshacer. ¿Continuar?" % n) != QMessageBox.StandardButton.Yes:
            return
        for s in list(core.SESSIONS.values()):
            s.delete()
        self._reload("Datos y privacidad")

    def p_log(self, v):
        self.log = QPlainTextEdit(core.LLM_MGR.tail(300) or "(vacío)")
        self.log.setObjectName("mono")
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(380)
        v.addWidget(self.log)
        v.addWidget(lbl("Comando: " + " ".join(core.LLM_MGR.command()), "faint"))
        r = QHBoxLayout()
        r.addWidget(btn("Actualizar", cb=lambda: self.log.setPlainText(core.LLM_MGR.tail(300) or "(vacío)"), ico="acc_refrescar"))
        r.addStretch(1)
        v.addLayout(r)

    def p_keys(self, v):
        g = QGridLayout()
        g.setHorizontalSpacing(24)
        for i, (k, d) in enumerate(SHORTCUTS):
            kl = QLabel(k.replace("Ctrl+", "⌘ ") if osys.MAC else k)      # en macOS Qt asigna Ctrl a la tecla Comando
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
        tl.addWidget(lbl("Agente de IA local para tu escritorio · versión %s" % __version__, "muted"))
        head.addLayout(tl, 1)
        v.addLayout(head)
        commit = local_commit()
        v.addWidget(lbl("Código: %s%s\nMotor: llama.cpp %s\nDatos: %s" % (paths.APP_DIR, (" · " + commit[:7]) if commit else "", cfg["llama_tag"] or "—", paths.HOME), "faint"))
        self.upd = lbl("", "muted")
        r = QHBoxLayout()
        r.addWidget(btn("Buscar actualizaciones", cb=self._check_updates, ico="acc_refrescar"))
        r.addWidget(btn("Abrir en GitHub", cb=lambda: webbrowser.open("https://github.com/" + REPO), ico="acc_abrir_externo"))
        r.addStretch(1)
        v.addLayout(r)
        v.addWidget(self.upd)
        self._section(v, "Novedades")
        self.field(v, "auto_update_check", "Avisarme cuando haya una versión nueva de %s" % APP_NAME, "bool")
        self.field(v, "model_news", "Avisarme cuando se publique una versión nueva de mis modelos", "bool",
                   help="Busca en Hugging Face versiones más recientes de la misma familia, tamaño y variante (p. ej. de Gemma 3 12B a Gemma 4 12B).")
        self._section(v, "Comentarios")
        v.addWidget(lbl("¿Encontraste un error o tienes una idea? Tu comentario ayuda a mejorar %s." % APP_NAME, "muted"))
        r = QHBoxLayout()
        from .feedback import FeedbackDialog
        r.addWidget(btn("Informar de un error…", cb=lambda: FeedbackDialog(self, "error").exec(), ico="est_error"))
        r.addWidget(btn("Sugerir una mejora…", cb=lambda: FeedbackDialog(self, "idea").exec(), ico="vfx_magia"))
        r.addStretch(1)
        v.addLayout(r)

    def _check_updates(self):
        self.upd.setText("Consultando GitHub…")

        from . import updater

        def done(r):
            if isinstance(r, Exception):
                return self.upd.setText("No se pudo consultar GitHub (¿sin internet?).")
            if not r:
                return self.upd.setText("✓ Tienes la última versión de %s." % APP_NAME)
            self.upd.setText("Hay una versión nueva (%s): «%s».\nUsa el botón «Actualizar» de la barra lateral; %s se reiniciará solo." % (
                r.get("date") or r.get("version"), r["message"], APP_NAME))
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
