# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Cómo se ve el trabajo del agente en el chat.

- Actividad animada: un icono con un arco que gira y un texto con un brillo que lo recorre («Pensando…»,
  «Ejecutando python app.py…», «Revisando la salida…»). Las frases cambian según lo que acaba de hacer el agente
  y se van turnando mientras tarda.
- Respuestas (MessageView): el Markdown se parte en trozos. Los bloques de código llevan una barra propia (lenguaje,
  copiar y, si son de terminal, ejecutar) y aire alrededor; los comandos cortos se ven como una fila con botones de
  copiar y ejecutar en vez de una caja negra; las rutas de archivos y carpetas son enlaces (abrir, mostrar en la
  carpeta, copiar) con un botón de copiar al lado.
"""
import os, re, math, time
from PySide6.QtCore import Qt, QTimer, QSize, QRectF, QUrl, QMimeData, Signal
from PySide6.QtGui import (QPainter, QColor, QLinearGradient, QPen, QBrush, QTextCursor, QTextCharFormat, QTextImageFormat,
                           QTextDocument, QGuiApplication, QCursor)
from PySide6.QtWidgets import QWidget, QLabel, QFrame, QHBoxLayout, QVBoxLayout, QToolButton, QMenu, QToolTip, QSizePolicy
from . import core, osys
from .theme import C, pix, icon
from .widgets import TextView, Collapsible
from .i18n import tr


def animations_on():
    try:
        return core.SET.snapshot().get("animations", True)
    except Exception:
        return True


def fmt_secs(s):
    """8 s · 2 min 53 s · 1 h 4 min"""
    s = int(round(max(0, s)))
    if s < 60:
        return "%d s" % s
    m, s = divmod(s, 60)
    if m < 60:
        return "%d min %d s" % (m, s) if s else "%d min" % m
    h, m = divmod(m, 60)
    return "%d h %d min" % (h, m)


# ---------------------------------------------------------------- qué está haciendo
TOOL_ICON = {
    "read_file": "acc_examinar", "read_document": "acc_examinar", "list_dir": "act_carpeta_abierta", "search_files": "acc_buscar",
    "write_file": "acc_nuevo", "create_document": "acc_nuevo", "edit_file": "acc_renombrar", "multi_edit": "acc_renombrar",
    "move_path": "act_carpeta", "delete_path": "acc_eliminar",
    "run_command": "cod_terminal", "command_output": "cod_terminal", "stop_command": "trans_detener", "run_python": "pan_editor_codigo",
    "web_search": "herr_espacio_mundo", "web_fetch": "herr_espacio_mundo", "download_file": "acc_descargar",
    "screenshot": "vista_captura", "view_image": "uij_imagen", "click": "inp_raton", "move_mouse": "inp_raton", "scroll": "inp_raton",
    "type_text": "inp_teclado", "press_keys": "inp_teclado", "list_windows": "app_restaurar", "focus_window": "app_restaurar",
    "open_target": "acc_abrir_externo", "wait": "est_cargando", "remember": "ia_memoria", "forget": "ia_memoria",
    "schedule_task": "lista_subir", "list_tasks": "ui_menu_hamburguesa", "cancel_task": "acc_eliminar", "use_skill": "vfx_magia",
    "show_canvas": "uij_panel", "edit_canvas": "uij_panel", "read_canvas": "uij_panel", "ui_elements": "act_layout_ui", "click_element": "inp_raton", "drag": "inp_raton",
    "window_action": "app_restaurar", "clipboard": "acc_copiar", "jayth_guide": "est_info", "generate_image": "uij_imagen", "connect_service": "hub_conectar", "search_knowledge": "acc_buscar",
    "browser_open": "herr_espacio_mundo", "browser_read": "acc_examinar", "browser_click": "inp_raton", "browser_type": "inp_teclado",
    "browser_nav": "herr_espacio_mundo", "browser_screenshot": "vista_captura",
}


def tool_icon(name):
    return "hub_conectar" if str(name or "").startswith("mcp__") else TOOL_ICON.get(name, "acc_ajustes")


_KIND = {"write_file": "write", "edit_file": "write", "multi_edit": "write", "create_document": "write", "move_path": "write",
         "delete_path": "write", "show_canvas": "write", "edit_canvas": "write", "read_canvas": "read", "generate_image": "write", "search_knowledge": "read",
         "run_command": "run", "run_python": "run", "command_output": "run", "stop_command": "run",
         "read_file": "read", "read_document": "read", "list_dir": "read", "search_files": "read",
         "web_search": "web", "web_fetch": "web", "download_file": "web",
         "screenshot": "look", "view_image": "look", "click": "look", "move_mouse": "look", "scroll": "look", "type_text": "look",
         "press_keys": "look", "list_windows": "look", "focus_window": "look", "ui_elements": "look", "click_element": "look",
         "drag": "look", "window_action": "look", "clipboard": "other", "jayth_guide": "read",
         "browser_open": "web", "browser_read": "web", "browser_click": "web", "browser_type": "web", "browser_nav": "web",
         "browser_screenshot": "web"}


def activity_kind(tool):
    """De qué tipo fue lo último que hizo el agente (para elegir qué decir mientras piensa el siguiente paso)."""
    if not tool:
        return "start"
    if tool == "__nudge__":
        return "nudge"
    return _KIND.get(tool, "other")


# Lo que se ve mientras el agente trabaja tiene que ser cierto: antes de escribir nada, el modelo está leyendo lo nuevo
# (tu mensaje o lo que devolvió la última acción); mientras razona, «Pensando» con su razonamiento real debajo; y si
# está escribiendo los datos de una acción, cuál (desktop.about_to). Sin frases inventadas que vayan rotando.
WAIT = {
    "start": (tr("Leyendo tu mensaje"),),
    "write": (tr("Leyendo el resultado de los cambios"),),
    "run": (tr("Leyendo la salida"),),
    "read": (tr("Leyendo el contenido"),),
    "web": (tr("Leyendo los resultados"),),
    "look": (tr("Leyendo el resultado"),),
    "other": (tr("Leyendo el resultado"),),
    "nudge": (tr("Leyendo el recordatorio de Jayth"),),
}
WAIT_ICON = {"start": "mat_comentario", "write": "pan_editor_codigo", "run": "cod_terminal", "read": "acc_examinar",
             "web": "herr_espacio_mundo", "look": "vista_captura", "other": "ia_controlador", "nudge": "est_info"}
THINK = (tr("Pensando"),)


def think_phrases(kind=None):
    return THINK


def thought_for(seconds):
    """Siempre la misma fórmula (antes, «Pensó durante 1 s» junto a «Pensó un momento»)."""
    return tr("Pensó durante %s") % (fmt_secs(seconds) if seconds >= 1 else tr("menos de 1 s"))


# ---------------------------------------------------------------- piezas animadas
class Shimmer(QWidget):
    """Una línea de texto. Activa, un brillo la recorre de izquierda a derecha (el agente está en ello); quieta, el verbo va
    en gris y lo que se toca («calculadora.py») resaltado. Si no cabe, termina en «…»."""

    def __init__(self, text="", emph=-1, color=None):
        super().__init__()
        self._text, self._emph = text, emph
        self.color = color or C["mut"]
        self.emph_color = C["tx"]
        self.strike = False
        self.active = False
        self.t0 = time.time()
        self.timer = QTimer(self, interval=40, timeout=self.update)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def setText(self, text, emph=-1):
        text = text or ""
        if (text, emph) != (self._text, self._emph):
            self._text, self._emph = text, emph
            self.updateGeometry()
            self.update()

    def text(self):
        return self._text

    def set_color(self, color, emph_color=None):
        self.color = color
        self.emph_color = emph_color or C["tx"]
        self.update()

    def set_strike(self, on):
        self.strike = on
        self.update()

    def set_active(self, on):
        on = bool(on) and animations_on()
        if on == self.active:
            return
        self.active = on
        if on:
            self.t0 = time.time()
            self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self._text) + 6, fm.height() + 4)

    def minimumSizeHint(self):
        return QSize(30, self.fontMetrics().height() + 4)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        f = self.font()
        f.setStrikeOut(self.strike)
        p.setFont(f)
        fm = self.fontMetrics()
        txt = fm.elidedText(self._text, Qt.ElideRight, max(10, self.width() - 2))
        y = (self.height() + fm.ascent() - fm.descent()) // 2
        if self.active:
            tw = max(20, fm.horizontalAdvance(txt))
            band = max(36.0, tw * 0.3)
            cycle = tw + 2 * band + 140                     # recorrido + una pausa antes del siguiente brillo
            pos = ((time.time() - self.t0) * 170) % cycle - band
            g = QLinearGradient(pos - band, 0, pos + band, 0)
            base, hi = QColor(self.color), QColor(C["tx"])
            g.setColorAt(0.0, base)
            g.setColorAt(0.5, hi)
            g.setColorAt(1.0, base)
            p.setPen(QPen(QBrush(g), 1))
            p.drawText(0, y, txt)
        elif 0 < self._emph < len(txt):
            a = txt[:self._emph]
            p.setPen(QColor(self.color))
            p.drawText(0, y, a)
            p.setPen(QColor(self.emph_color))
            p.drawText(fm.horizontalAdvance(a), y, txt[self._emph:])
        else:
            p.setPen(QColor(self.color))
            p.drawText(0, y, txt)
        p.end()


class ActivityIcon(QWidget):
    """Icono de lo que hace el agente. Activo: late suavemente y un arco gira a su alrededor."""

    def __init__(self, name="ia_controlador", color=None, size=14):
        super().__init__()
        self.size_ = size
        self.setFixedSize(size + 10, size + 10)
        self.active = False
        self.t0 = time.time()
        self.timer = QTimer(self, interval=33, timeout=self.update)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.set_icon(name, color)

    def set_icon(self, name, color=None):
        self.name, self.color = name, color or C["mut"]
        self.pm = pix(name, self.color, self.size_)
        self.update()

    def set_active(self, on):
        on = bool(on) and animations_on()
        if on == self.active:
            return
        self.active = on
        if on:
            self.t0 = time.time()
            self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        dpr = self.pm.devicePixelRatio() or 1.0
        pw, ph = self.pm.width() / dpr, self.pm.height() / dpr
        if self.active:
            t = time.time() - self.t0
            ring = QRectF(1.2, 1.2, w - 2.4, h - 2.4)
            p.setPen(QPen(QColor(C["line"]), 1.3))
            p.drawEllipse(ring)
            pen = QPen(QColor(C["acc"]), 1.8)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            start = -(t * 320.0) % 360.0                 # gira en el sentido de las agujas del reloj
            span = 75 + 45 * math.sin(t * 2.4)            # y el arco se estira y se encoge
            p.drawArc(ring, int(start * 16), int(span * 16))
            p.setOpacity(0.6 + 0.4 * (0.5 + 0.5 * math.sin(t * 3.4)))
        p.drawPixmap(QRectF((w - pw) / 2, (h - ph) / 2, pw, ph), self.pm, QRectF(self.pm.rect()))
        p.end()


class ActivityLine(QWidget):
    """«Pensando… 12 s ›»: lo que hace el modelo mientras genera, con icono animado y frases que se turnan. Al terminar
    queda «Pensó durante 12 s ›» y un clic despliega el pensamiento."""
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("stepHead")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_Hover, True)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 1, 8, 1)
        h.setSpacing(6)
        self.ico = ActivityIcon("ia_controlador", C["mut"], 14)
        h.addWidget(self.ico)
        self.txt = Shimmer()
        h.addWidget(self.txt)
        self.time = QLabel()
        self.time.setObjectName("faint")
        h.addWidget(self.time)
        self.chev = QLabel()
        self.chev.hide()
        h.addWidget(self.chev)
        h.addStretch(1)
        self.phrases, self.t_start, self.live, self.expandable = (tr("Pensando"),), time.time(), False, False
        self.extra = ""                      # dato real junto al tiempo (p. ej. cuánto lleva escrito de una acción)
        self.set_open(False)

    def run(self, phrases, t_start, icon_name="ia_controlador", live=True):
        self.phrases, self.t_start, self.live = tuple(phrases) or (tr("Pensando"),), t_start, live
        self.ico.set_icon(icon_name, C["acc"] if live else C["mut"])
        self.ico.set_active(live)
        self.txt.set_color(C["mut"])
        self.txt.set_active(live)
        self.tick(time.time())

    def tick(self, now):
        if not self.live:
            return
        el = max(0.0, now - self.t_start)
        self.txt.setText(self.phrases[int(el // 4) % len(self.phrases)] + "…")
        self.time.setText(" · ".join(x for x in (fmt_secs(el) if el >= 1 else "", self.extra) if x))

    def done(self, text):
        self.live = False
        self.ico.set_active(False)
        self.ico.set_icon(self.ico.name, C["mut"])
        self.txt.set_active(False)
        self.txt.setText(text)
        self.time.setText("")

    def set_expandable(self, on):
        self.expandable = on
        self.chev.setVisible(on)
        self.setCursor(Qt.PointingHandCursor if on else Qt.ArrowCursor)
        self.setToolTip(tr("Clic para ver lo que pensó") if on else "")

    def set_open(self, on):
        self.chev.setPixmap(pix("ui_chevron_abajo" if on else "ui_chevron_derecha", C["faint"], 10))

    def text(self):
        return self.txt.text()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.expandable:
            self.clicked.emit()


class ThinkView(TextView):
    """El pensamiento del modelo: texto tenue con una línea fina a la izquierda."""

    def __init__(self):
        super().__init__("", "plain", color=C["faint"], size="9.5pt")

    def setText(self, text):
        super().setText(text)
        self._indent()

    def _indent(self):
        root = self.document().rootFrame()
        f = root.frameFormat()
        if f.leftMargin() != 14:
            f.setLeftMargin(14)
            root.setFrameFormat(f)
        self._natural = None
        self._fit()

    def append(self, text):
        c = QTextCursor(self.document())
        c.movePosition(QTextCursor.End)
        c.insertText(text)
        self._natural = None
        self._fit()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self.viewport())
        p.fillRect(QRectF(2, 3, 2, max(0, self.viewport().height() - 6)), QColor(C["line"]))
        p.end()


# ---------------------------------------------------------------- respuestas: rutas, comandos y código
def host_of(w):
    """El panel de chat que contiene el widget (sabe la carpeta de trabajo, abrir en el editor y ejecutar en la terminal)."""
    while w is not None:
        if hasattr(w, "run_in_terminal") and hasattr(w, "workspace"):
            return w
        w = w.parentWidget()
    return None


def copy_text(text, msg=tr("Copiado")):
    QGuiApplication.clipboard().setText(text)
    QToolTip.showText(QCursor.pos(), msg)


def path_menu(parent, path):
    """Menú de una ruta de la respuesta: abrir (en el editor si es código y estamos en un proyecto), mostrar o copiar."""
    host = host_of(parent)
    m = QMenu(parent)
    if os.path.isdir(path):
        m.addAction(icon("act_carpeta_abierta"), tr("Abrir la carpeta"), lambda: osys.open_path(path))
    elif os.path.isfile(path):
        if host is not None and getattr(host, "can_edit", None) and host.can_edit(path):
            m.addAction(icon("pan_editor_codigo"), tr("Abrir en el editor"), lambda: host.open_in_editor(path))
        m.addAction(icon("acc_abrir_externo"), tr("Abrir"), lambda: osys.open_path(path))
        m.addAction(icon("act_carpeta_abierta"), tr("Mostrar en la carpeta"), lambda: osys.reveal(path))
    else:
        a = m.addAction(icon("est_info"), tr("Todavía no existe"))
        a.setEnabled(False)
    m.addSeparator()
    m.addAction(icon("acc_copiar"), tr("Copiar la ruta"), lambda: copy_text(path, tr("Ruta copiada")))
    m.exec(QCursor.pos())


_ABS = re.compile(r"(?<![\w/\\])(?:[A-Za-z]:[\\/]|~[\\/]|/(?:Users|home|tmp|var|etc|opt|usr|mnt|media|Volumes|private|srv|root|Applications|Library)/)"
                  r"[^\s<>\"'|*?`]*[^\s<>\"'|*?`.,;:)\]]")
_IMG = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".svg"}
_CODE = {".py", ".pyw", ".js", ".ts", ".tsx", ".jsx", ".json", ".html", ".htm", ".css", ".md", ".txt", ".ps1", ".bat", ".cmd", ".sh", ".yml",
         ".yaml", ".toml", ".ini", ".cfg", ".xml", ".csv", ".sql", ".c", ".h", ".cpp", ".cs", ".java", ".go", ".rs", ".php", ".rb", ".lua",
         ".gd", ".log", ".vue", ".kt", ".swift", ".dart", ".r"}


def _ico_name(path):
    if os.path.isdir(path):
        return "act_carpeta"
    ext = os.path.splitext(path)[1].lower()
    return "uij_imagen" if ext in _IMG else "pan_editor_codigo" if ext in _CODE else "acc_nuevo"


class RichText(TextView):
    """Texto de una respuesta (Markdown). Las rutas de archivos y carpetas se convierten en enlaces con su icono y un
    botón de copiar; un clic en la ruta abre un menú (abrir, mostrar en la carpeta, copiar)."""

    def __init__(self, size="10.5pt"):
        self._links, self._seen = [], {}
        super().__init__("", "md", size=size)
        self.highlighted.connect(self._hover)

    def set_seg(self, seg):
        if seg[2] != getattr(self, "_src", None):
            self._src = seg[2]
            self.setText(seg[2])

    def plain(self):
        return getattr(self, "_src", "") or ""

    def setText(self, text):
        super().setText(text)
        if self.fmt == "md":
            try:
                self._linkify()
            except Exception:
                pass
            self._natural = None
            self._fit()

    def _exists(self, p):
        if p not in self._seen:
            try:
                self._seen[p] = os.path.exists(p)
            except (OSError, ValueError):
                self._seen[p] = False
        return self._seen[p]

    def _code_path(self, s, base):
        """¿Es una ruta lo que hay entre `comillas de código`? Devuelve la ruta completa o None."""
        s = s.strip().strip("\"'")
        if not s or "\n" in s or len(s) > 400 or "://" in s or s.startswith(("-", "$", "%")):
            return None
        if re.match(r"^(?:[A-Za-z]:[\\/]|\\\\[^\\\s]+\\|~[\\/])", s):
            return None if re.search(r'[<>|*?"]', s[2:]) else os.path.expanduser(s)
        if s.startswith("/"):              # /home/… sí; «/v1/users» (una ruta de API) solo si existe en el disco
            return s if (_ABS.fullmatch(s) or (s.count("/") >= 2 and self._exists(s))) and not re.search(r'[<>|*?"]', s) else None
        if base and " " not in s and re.search(r"[./\\]", s) and not re.search(r'[<>|*?"(){}=]', s):
            p = os.path.normpath(os.path.join(base, s))
            if self._exists(p):
                return p
        return None

    def _linkify(self):
        doc = self.document()
        self._links = []
        host = host_of(self)
        base = None
        if host is not None:
            try:
                base = host.workspace()
            except Exception:
                base = None
        spans = []
        b = doc.begin()
        while b.isValid():
            if b.blockFormat().background().style() == Qt.NoBrush:          # no dentro de bloques de código
                it = b.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    if frag.isValid() and not frag.charFormat().isAnchor():
                        t, pos = frag.text(), frag.position()
                        if frag.charFormat().fontFixedPitch():
                            p = self._code_path(t, base)
                            if p:
                                lead = len(t) - len(t.lstrip())
                                spans.append((pos + lead, pos + len(t.rstrip()), p))
                        else:
                            for m in _ABS.finditer(t):
                                p = os.path.expanduser(m.group(0))
                                if self._exists(p) or self._exists(os.path.dirname(p)):
                                    spans.append((pos + m.start(), pos + m.end(), p))
                    it += 1
            b = b.next()
        if not spans:
            return
        for name in ("acc_copiar", "act_carpeta", "uij_imagen", "pan_editor_codigo", "acc_nuevo"):
            col = C["faint"] if name == "acc_copiar" else C["acc"]
            doc.addResource(QTextDocument.ImageResource, QUrl("jico:" + name), pix(name, col, 26).toImage())
        plain = QTextCharFormat()
        for start, end, p in reversed(spans):          # de atrás hacia delante: las posiciones anteriores no se mueven
            i = len(self._links)
            self._links.append(p)
            c = QTextCursor(doc)
            c.setPosition(start)
            c.setPosition(end, QTextCursor.KeepAnchor)
            f = QTextCharFormat()
            f.setAnchor(True)
            f.setAnchorHref("jpath:%d" % i)
            f.setForeground(QColor(C["acc"]))
            f.setFontUnderline(False)
            f.setToolTip(p)
            c.mergeCharFormat(f)
            c = QTextCursor(doc)                        # botón de copiar justo detrás
            c.setPosition(end)
            c.insertText("\u2009", plain)
            c.insertImage(self._img("acc_copiar", "jcopy:%d" % i, tr("Copiar la ruta")))
            if self._exists(p):                         # y su icono delante
                c = QTextCursor(doc)
                c.setPosition(start)
                c.insertImage(self._img(_ico_name(p), "jpath:%d" % i, p))
                c.insertText("\u2009", plain)

    @staticmethod
    def _img(name, href, tip):
        f = QTextImageFormat()
        f.setName("jico:" + name)
        f.setWidth(13)
        f.setHeight(13)
        f.setVerticalAlignment(QTextCharFormat.AlignMiddle)
        f.setAnchor(True)
        f.setAnchorHref(href)
        f.setToolTip(tip)
        return f

    def _link_path(self, s):
        try:
            return self._links[int(s.split(":", 1)[1])]
        except (ValueError, IndexError):
            return None

    def _open_link(self, url):
        s = url.toString()
        if s.startswith(("jpath:", "jcopy:")):
            p = self._link_path(s)
            if p:
                copy_text(p, tr("Ruta copiada")) if s.startswith("jcopy:") else path_menu(self, p)
            return
        super()._open_link(url)

    def _hover(self, url):
        s = url.toString() if url is not None else ""
        if s.startswith("jcopy:"):
            QToolTip.showText(QCursor.pos(), tr("Copiar la ruta"), self)
        elif s.startswith("jpath:"):
            p = self._link_path(s)
            if p:
                QToolTip.showText(QCursor.pos(), tr("%s\nClic: abrir, mostrar en la carpeta o copiar") % p, self)

    def createMimeDataFromSelection(self):
        """Al copiar texto seleccionado, sin los iconos ni los espacios finos de las rutas."""
        src = super().createMimeDataFromSelection()
        md = QMimeData()
        md.setText(src.text().replace("\ufffc", "").replace("\u2009", ""))
        return md


SHELL_LANGS = {"bash", "sh", "shell", "zsh", "fish", "console", "terminal", "shellsession", "powershell", "ps", "ps1", "pwsh", "posh",
               "cmd", "bat", "batch", "dos"}
_CMD_START = re.compile(r"^\s*(?:\$\s+|>\s+|PS(?: [^>]*)?>\s*)?(?:cd|python3?|py|pip3?|npm|npx|node|yarn|pnpm|bun|deno|git|ls|dir|mkdir|md|"
                        r"start|code|cargo|rustc|go|java|javac|dotnet|uv|conda|curl|wget|docker|make|cmake|gcc|g\+\+|explorer|open|"
                        r"xdg-open|Set-Location|Get-ChildItem|Get-Content|New-Item|Invoke-WebRequest|winget|choco|brew|chmod|cat|type|"
                        r"echo|copy|cp|mv|move|\.[\\/]\S+)(?:\s|$)", re.I)
_PROMPT = re.compile(r"^\s*(?:\$|>|PS(?: [^>]*)?>)\s+")
LANG_EXT = {"python": ".py", "py": ".py", "python3": ".py", "javascript": ".js", "js": ".js", "node": ".js", "typescript": ".ts", "ts": ".ts",
            "jsx": ".jsx", "tsx": ".tsx", "json": ".json", "html": ".html", "xml": ".xml", "svg": ".svg", "css": ".css", "scss": ".scss",
            "powershell": ".ps1", "ps1": ".ps1", "ps": ".ps1", "pwsh": ".ps1", "posh": ".ps1", "bash": ".sh", "sh": ".sh", "shell": ".sh",
            "zsh": ".sh", "console": ".sh", "bat": ".bat", "batch": ".bat", "cmd": ".bat", "c": ".c", "cpp": ".cpp", "c++": ".cpp",
            "cs": ".cs", "csharp": ".cs", "java": ".java", "go": ".go", "rust": ".rs", "rs": ".rs", "php": ".php", "ruby": ".rb",
            "rb": ".rb", "lua": ".lua", "sql": ".sql", "yaml": ".yaml", "yml": ".yaml", "toml": ".toml", "ini": ".ini", "md": ".md",
            "markdown": ".md", "kotlin": ".kt", "swift": ".swift", "dart": ".dart", "gdscript": ".gd", "vue": ".vue"}
LANG_NAME = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".jsx": "JSX", ".tsx": "TSX", ".json": "JSON", ".html": "HTML",
             ".xml": "XML", ".svg": "SVG", ".css": "CSS", ".scss": "SCSS", ".ps1": "PowerShell", ".sh": "Terminal", ".bat": "CMD",
             ".c": "C", ".cpp": "C++", ".cs": "C#", ".java": "Java", ".go": "Go", ".rs": "Rust", ".php": "PHP", ".rb": "Ruby",
             ".lua": "Lua", ".sql": "SQL", ".yaml": "YAML", ".toml": "TOML", ".ini": "INI", ".md": "Markdown", ".kt": "Kotlin",
             ".swift": "Swift", ".dart": "Dart", ".gd": "GDScript", ".vue": "Vue"}


def clean_cmd(code):
    """Quita los «$ » o «PS C:\\> » que algunos modelos ponen delante de cada comando."""
    return "\n".join(_PROMPT.sub("", l).rstrip() for l in code.split("\n") if l.strip())


def tool_call_text(code):
    """¿Es una herramienta del agente escrita como texto («open_target "x"», «run_python{…}»)? No es un comando de la
    terminal: «Ejecutar» solo daría un error."""
    m = re.match(r"\s*(?:call:)?([A-Za-z]+_\w+)(?=[\s({]|$)", code or "")
    if not m:
        return False
    from . import tools as T
    return m.group(1) in T.TOOLS


def _kind(lang, code):
    lines = [l for l in code.split("\n") if l.strip()]
    shell = (lang in SHELL_LANGS or (not lang and lines and all(_CMD_START.match(l) for l in lines))) and not tool_call_text(code)
    if shell and 0 < len(lines) <= 4 and all(len(l) <= 240 for l in lines):
        return "cmd"
    return "code"


_FENCE = re.compile(r"^(?P<ind>[ \t]{0,8})(?P<f>`{3,}|~{3,})[ \t]*(?P<lang>[^\s`]*)[^`]*$")


def split_md(text):
    """Parte una respuesta en trozos: ("md", "", texto, 0), ("cmd", lenguaje, comando, sangría) y ("code", lenguaje, código, sangría).
    Un bloque que se está escribiendo (sin cerrar) también cuenta como bloque."""
    out, md = [], []
    lines = (text or "").split("\n")
    i = 0
    while i < len(lines):
        m = _FENCE.match(lines[i])
        if not m:
            md.append(lines[i])
            i += 1
            continue
        ind = len(m.group("ind").expandtabs(4))
        fch, flen = m.group("f")[0], len(m.group("f"))
        lang = m.group("lang").lower().strip("{}.")
        body = []
        i += 1
        while i < len(lines):
            s = lines[i].strip()
            if len(s) >= flen and set(s) == {fch}:
                i += 1
                break
            l = lines[i]
            body.append(l[ind:] if l[:ind].strip() == "" else l.lstrip())
            i += 1
        if "".join(md).strip():
            out.append(("md", "", "\n".join(md), 0))
        md = []
        code = "\n".join(body).rstrip("\n")
        out.append((_kind(lang, code), lang, code, ind))
    if "".join(md).strip():
        out.append(("md", "", "\n".join(md), 0))
    return out


def _small_btn(ico, text, tip, cb):
    b = QToolButton()
    b.setObjectName("codeBtn")
    b.setIcon(icon(ico, C["mut"], 13))
    if text:
        b.setText(text)
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    b.clicked.connect(cb)
    return b


def _flash(b, text, ico="ui_check"):
    """El botón confirma lo que hizo («Copiado») y vuelve a su estado."""
    old_t, old_i = b.text(), b.icon()
    b.setIcon(icon(ico, C["ok"], 13))
    if old_t:
        b.setText(text)

    def back():
        try:
            b.setIcon(old_i)
            if old_t:
                b.setText(old_t)
        except RuntimeError:
            pass
    QTimer.singleShot(1300, back)


def _run(widget, cmd):
    host = host_of(widget)
    if host is not None and cmd.strip():
        return host.run_in_terminal(cmd)
    return False


class CodeBlock(QFrame):
    """Bloque de código de una respuesta: barra con el lenguaje y botones (copiar y, si es de terminal, ejecutar) y el
    código con colores y aire alrededor, también abajo. Los muy largos se pliegan."""

    def __init__(self):
        super().__init__()
        self.setObjectName("codeBlock")
        self.lang, self.code, self.ext, self.hl = None, None, None, None
        v = QVBoxLayout(self)
        v.setContentsMargins(1, 1, 1, 1)
        v.setSpacing(0)
        head = QWidget()
        head.setObjectName("codeHead")
        head.setAttribute(Qt.WA_StyledBackground, True)
        hh = QHBoxLayout(head)
        hh.setContentsMargins(12, 3, 4, 3)
        hh.setSpacing(2)
        self.lang_lbl = QLabel()
        self.lang_lbl.setObjectName("codeLang")
        hh.addWidget(self.lang_lbl)
        hh.addStretch(1)
        self.b_run = _small_btn("cod_terminal", tr("Ejecutar"), tr("Ejecutar en una terminal"), self._run)
        self.b_copy = _small_btn("acc_copiar", tr("Copiar"), tr("Copiar el código"), self._copy)
        hh.addWidget(self.b_run)
        hh.addWidget(self.b_copy)
        v.addWidget(head)
        self.view = TextView("", "plain")
        self.view.document().setDocumentMargin(12)          # aire alrededor del código (también abajo)
        self.view.setStyleSheet("QTextBrowser#textView { background: transparent; border: none; padding: 0; margin: 0; "
                                "font-family: '%s'; font-size: 9.5pt; }" % osys.mono_font())
        self.fold = Collapsible(self.view, limit=420, fade=C["code"], slack=90)
        v.addWidget(self.fold)

    def set_seg(self, seg):
        _, lang, code, _ind = seg
        ext = LANG_EXT.get(lang, "")
        if lang != self.lang:
            self.lang = lang
            self.lang_lbl.setText(LANG_NAME.get(ext) or (lang if lang else tr("Código")))
        self.b_run.setVisible(lang in SHELL_LANGS and not tool_call_text(code))
        if ext != self.ext:
            self.ext = ext
            from .codeview import Highlighter
            if self.hl is not None:
                self.hl.setDocument(None)
            self.hl = Highlighter(self.view.document(), ext) if ext else None
        if code != self.code:
            self.code = code
            self.view.setText(code)

    def plain(self):
        return "```%s\n%s\n```" % (self.lang or "", self.code or "")

    def _copy(self):
        copy_text(self.code or "", tr("Código copiado"))
        _flash(self.b_copy, tr("Copiado"))

    def _run(self):
        if _run(self, clean_cmd(self.code or "")):
            _flash(self.b_run, tr("Enviado"))


class CommandRow(QFrame):
    """Comando de terminal sugerido en una respuesta: se lee como una línea (no una caja negra), con botones para copiarlo
    o ejecutarlo en la terminal."""

    def __init__(self):
        super().__init__()
        self.setObjectName("cmdRow")
        self.setAttribute(Qt.WA_Hover, True)
        self.cmd = None
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 4, 4, 4)
        h.setSpacing(8)
        g = QLabel()
        g.setPixmap(pix("cod_terminal", C["acc"], 14))
        h.addWidget(g, 0, Qt.AlignVCenter)
        self.view = TextView("", "plain")
        self.view.setStyleSheet("QTextBrowser#textView { background: transparent; border: none; padding: 0; margin: 0; "
                                "font-family: '%s'; font-size: 9.5pt; color: %s; }" % (osys.mono_font(), C["tx"]))
        h.addWidget(self.view, 1, Qt.AlignVCenter)
        self.b_copy = _small_btn("acc_copiar", "", tr("Copiar el comando"), self._copy)
        self.b_run = _small_btn("hub_lanzar", tr("Ejecutar"), tr("Ejecutar en una terminal"), self._run)
        h.addWidget(self.b_copy, 0, Qt.AlignVCenter)
        h.addWidget(self.b_run, 0, Qt.AlignVCenter)

    def set_seg(self, seg):
        cmd = clean_cmd(seg[2])
        if cmd != self.cmd:
            self.cmd = cmd
            self.view.setText(cmd)

    def plain(self):
        return "```\n%s\n```" % (self.cmd or "")

    def _copy(self):
        copy_text(self.cmd or "", tr("Comando copiado"))
        _flash(self.b_copy, "")

    def _run(self):
        if _run(self, self.cmd or ""):
            _flash(self.b_run, tr("Enviado"))


class MessageView(QWidget):
    """Respuesta del agente: Markdown con bloques de código, comandos y rutas interactivos. Se actualiza mientras llega
    el texto sin rehacer lo que no cambió (solo el último trozo crece)."""

    def __init__(self, size="10.5pt"):
        super().__init__()
        self.size = size
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.v.setSpacing(8)
        self.parts = []           # (clave, contenedor, pieza)
        self._text = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def setText(self, text):
        text = text or ""
        if text == self._text:
            return
        self._text = text
        segs = split_md(text)
        for i, seg in enumerate(segs):
            key = (seg[0], 22 if seg[3] >= 2 else 0)
            if i < len(self.parts) and self.parts[i][0] == key:
                self.parts[i][2].set_seg(seg)
                continue
            self._drop(i)
            piece = RichText(self.size) if seg[0] == "md" else CommandRow() if seg[0] == "cmd" else CodeBlock()
            box = QWidget()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(key[1], 0, 0, 0)          # bloque dentro de una lista: con la sangría de la lista
            bl.addWidget(piece)
            self.v.addWidget(box)
            self.parts.append((key, box, piece))
            piece.set_seg(seg)
        self._drop(len(segs))

    def _drop(self, i):
        for _, box, _p in self.parts[i:]:
            self.v.removeWidget(box)
            box.hide()
            box.deleteLater()
        del self.parts[i:]

    def text(self):
        return self._text or ""

    def toPlainText(self):
        return "\n\n".join(p.plain() for _, _, p in self.parts)
