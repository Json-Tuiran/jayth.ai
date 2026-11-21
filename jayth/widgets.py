# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Piezas de interfaz que se adaptan a cualquier ancho (el panel del agente puede ser muy estrecho).

- TextView: texto (Markdown, HTML o plano) que se parte donde haga falta, tambien codigo, rutas y URL sin espacios;
  su alto se ajusta solo al contenido y se puede seleccionar y copiar tal cual (sin caracteres invisibles).
- FlowLayout: coloca botones en fila y baja a la siguiente linea los que no caben.
- OptionRow: opcion clicable de ancho completo con texto que se ajusta (preguntas del agente, sugerencias).
"""
import math
from PySide6.QtCore import Qt, QSize, QRect, QPoint, Signal, QTimer
from PySide6.QtGui import (QTextOption, QTextCursor, QColor, QTextFormat, QDesktopServices, QPainter, QLinearGradient, QTextCharFormat,
                           QTextFrameFormat)
from PySide6.QtWidgets import (QTextBrowser, QFrame, QLayout, QSizePolicy, QHBoxLayout, QLabel, QWidget, QAbstractScrollArea, QApplication,
                               QToolButton, QPushButton, QStyledItemDelegate, QScrollArea, QDialog)
from PySide6.QtCore import QObject, QEvent, QRectF, QVariantAnimation
from PySide6.QtWidgets import QCheckBox, QComboBox
from .theme import C, pix
from .i18n import tr


# ---------------------------------------------------------------- ventanas que caben en la pantalla
def _screen_of(win, parent=None):
    from PySide6.QtGui import QGuiApplication, QCursor
    ref = parent if parent is not None else win.parentWidget()
    scr = ref.screen() if ref is not None else None
    return scr or QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()


def fit_to_screen(win, w, h, parent=None):
    """Tamaño deseado, pero nunca mayor que la pantalla (en portátiles de 768 px de alto las ventanas se salían)."""
    g = _screen_of(win, parent).availableGeometry()
    win.resize(min(w, g.width() - 24), min(h, g.height() - 48))


def scrollable(widget):
    """Envuelve una zona para que se desplace en vertical si no cabe (sin marco y sin barra horizontal)."""
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.setObjectName("pageScroll")
    sa.viewport().setAutoFillBackground(False)
    widget.setAutoFillBackground(False)
    sa.setWidget(widget)
    return sa


class ScreenFit(QObject):
    """Para toda la aplicación: al mostrarse un diálogo más grande que la pantalla, se encoge y se centra."""

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Show and isinstance(obj, QDialog) and obj.isWindow():
            g = _screen_of(obj).availableGeometry()
            fr = obj.frameGeometry()
            extra_h, extra_w = fr.height() - obj.height(), fr.width() - obj.width()
            w = min(obj.width(), g.width() - extra_w - 8)
            h = min(obj.height(), g.height() - extra_h - 8)
            if (w, h) != (obj.width(), obj.height()):
                obj.resize(max(w, 200), max(h, 150))
                fr = obj.frameGeometry()
            if not g.contains(fr):           # que no quede ningún borde fuera (el título tampoco)
                x = min(max(fr.x(), g.x()), g.right() - fr.width() + 1)
                y = min(max(fr.y(), g.y()), g.bottom() - fr.height() + 1)
                obj.move(max(x, g.x()), max(y, g.y()))
        return False


_FIT = []


def install_screen_fit(app):
    if not _FIT:
        _FIT.append(ScreenFit(app))
        app.installEventFilter(_FIT[0])


class ElideDelegate(QStyledItemDelegate):
    """Listas de una linea (historial): cada fila mide como mucho el ancho visible y el texto que no cabe
    termina en «…» (el tema oculta las barras horizontales, asi que sin esto el texto se cortaba en el borde)."""

    def sizeHint(self, opt, idx):
        s = super().sizeHint(opt, idx)
        view = self.parent()
        if view is not None:
            s.setWidth(min(s.width(), max(40, view.viewport().width() - 2)))
        return s


def elide_list(lst):
    lst.setItemDelegate(ElideDelegate(lst))
    lst.setTextElideMode(Qt.ElideRight)
    lst.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    lst.setUniformItemSizes(False)
    _orig = lst.resizeEvent

    def resized(e):           # al cambiar el ancho del panel, recalcula las filas
        _orig(e)
        lst.doItemsLayout()
    lst.resizeEvent = resized

_CODE_FENCE = int(getattr(getattr(QTextFormat, "Property", QTextFormat), "BlockCodeFence", 0x1060))   # bloque ``` del Markdown


class TextView(QTextBrowser):
    """Texto de solo lectura que nunca ensancha a su contenedor: se ajusta al ancho disponible y crece en alto."""

    def __init__(self, text="", fmt="plain", color=None, size=None, bold=False, selectable=True, mono=False, kind=None):
        super().__init__()
        self.setObjectName("textView")
        self.fmt = fmt
        self.mono = mono
        self.setReadOnly(True)
        self.setOpenLinks(False)                 # nunca navegar dentro del mensaje (lo dejaria en blanco)
        self.anchorClicked.connect(self._open_link)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizeAdjustPolicy(QAbstractScrollArea.AdjustIgnored)
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)    # parte palabras larguisimas si no hay otra
        self.setLineWrapMode(QTextBrowser.WidgetWidth)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.NoFocus)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.setTextInteractionFlags((Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse) if selectable else Qt.LinksAccessibleByMouse)
        self.viewport().setAutoFillBackground(False)
        extra = ((" color: %s;" % color) if color else "") + ((" font-size: %s;" % size) if size else "") + (" font-weight: 600;" if bold else "")
        if mono:            # salida de comandos y codigo: caja con fondo propio, fuente monoespaciada y borde segun el tipo
            from .osys import mono_font
            self.document().setDocumentMargin(8)
            left = {"add": C["ok"], "del": C["bad"]}.get(kind)
            css = ("QTextBrowser#textView { background: %s; border: 1px solid %s; %s border-radius: 8px; padding: 0; margin: 0; "
                   "font-family: '%s'; font-size: 9.5pt;%s }" % (C["code"], C["line"], ("border-left: 3px solid %s;" % left) if left else "",
                                                                 mono_font(), extra))
        else:
            self.document().setDocumentMargin(0)
            css = "QTextBrowser#textView { background: transparent; border: none; padding: 0; margin: 0;%s }" % extra
        self.setStyleSheet(css)
        self._natural = None
        self.setText(text)

    def setText(self, text):
        text = text or ""
        if self.fmt == "md":
            self.setMarkdown(text)
            self._wrap_code_blocks()
            self._style_tables()
        elif self.fmt == "html":
            self.setHtml(text)
        else:
            self.setPlainText(text)
        self._natural = None
        self._fit()

    def text(self):
        return self.toPlainText()

    def _wrap_code_blocks(self):
        """Bloques de codigo del Markdown: se permite partirlos (no desbordan) y llevan fondo propio para leerse mejor."""
        doc = self.document()
        b = doc.begin()
        bg = QColor(C["code"])
        from .osys import mono_font
        mono = QTextCharFormat()
        mono.setFontFamilies([mono_font()])          # el Markdown usa la monoespaciada del sistema (Courier); la de la app se lee mejor
        while b.isValid():
            f = b.blockFormat()
            if f.nonBreakableLines() or f.hasProperty(_CODE_FENCE):
                f.setNonBreakableLines(False)
                f.setBackground(bg)
                f.setLeftMargin(2)
                c = QTextCursor(b)
                c.setBlockFormat(f)
            it = b.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and frag.charFormat().fontFixedPitch():
                    c = QTextCursor(doc)
                    c.setPosition(frag.position())
                    c.setPosition(frag.position() + frag.length(), QTextCursor.KeepAnchor)
                    c.mergeCharFormat(mono)
                it += 1
            b = b.next()

    def _style_tables(self):
        """Tablas del Markdown con aspecto de la app: borde fino y discreto, celdas con aire y cabecera con fondo."""
        doc = self.document()
        seen = set()
        b = doc.begin()
        while b.isValid():
            c = QTextCursor(b)
            t = c.currentTable()
            if t is not None and id(t) not in seen and t.firstPosition() not in seen:
                seen.add(t.firstPosition())
                f = t.format()
                f.setBorder(1)
                f.setBorderBrush(QColor(C["line"]))
                f.setBorderStyle(QTextFrameFormat.BorderStyle_Solid)
                f.setBorderCollapse(True)
                f.setCellPadding(6)
                f.setCellSpacing(0)
                f.setTopMargin(4)
                f.setBottomMargin(4)
                t.setFormat(f)
                head = QColor(C["panel2"])
                for col in range(t.columns()):
                    cell = t.cellAt(0, col)
                    cf = cell.format()
                    cf.setBackground(head)
                    cell.setFormat(cf)
            b = b.next()

    def _open_link(self, url):
        """Enlaces de una respuesta: web y correo en el navegador; rutas de archivo existentes con su programa."""
        from . import osys
        import os
        s = url.toString()
        if url.scheme() in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)
        elif url.isLocalFile() and os.path.exists(url.toLocalFile()):
            osys.open_path(url.toLocalFile())
        elif os.path.exists(s):
            osys.open_path(s)

    def natural_width(self):
        """Ancho que ocuparia el texto sin partir lineas (para burbujas que se ajustan a su contenido)."""
        if self._natural is None:
            doc = self.document().clone()
            doc.setTextWidth(-1)
            self._natural = int(math.ceil(doc.idealWidth())) + 2
        return self._natural

    def _fit(self):
        w = max(20, self.viewport().width())
        doc = self.document()
        doc.setTextWidth(w)
        h = int(math.ceil(doc.size().height())) + 1 + 2 * self.frameWidth()
        if h != self.height():
            self.setFixedHeight(h)
            self.updateGeometry()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def sizeHint(self):
        return QSize(min(self.natural_width(), 4000), self.height())

    def minimumSizeHint(self):
        return QSize(24, self.height())

    def wheelEvent(self, e):
        """La rueda desplaza la conversacion que contiene este texto (el texto nunca tiene barra propia)."""
        area = self.parentWidget()
        while area is not None and not isinstance(area, QAbstractScrollArea):
            area = area.parentWidget()
        if area is not None:
            QApplication.sendEvent(area.viewport(), e)
            e.accept()
        else:
            e.ignore()


class _Fade(QWidget):
    """Degradado de transparente al color de fondo: indica que hay mas contenido debajo."""

    def __init__(self, parent, color):
        super().__init__(parent)
        self.color = QColor(color)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def paintEvent(self, e):
        p = QPainter(self)
        g = QLinearGradient(0, 0, 0, self.height())
        c0 = QColor(self.color)
        c0.setAlpha(0)
        g.setColorAt(0.0, c0)
        g.setColorAt(0.75, self.color)
        g.setColorAt(1.0, self.color)
        p.fillRect(self.rect(), g)
        p.end()


class Collapsible(QWidget):
    """Muestra solo el principio de un contenido largo (mensaje, salida de un comando…) con un difuminado abajo y una
    flecha para desplegarlo; desplegado, la flecha lo vuelve a plegar. Si el contenido es corto no cambia nada."""
    toggled = Signal(bool)

    def __init__(self, child, limit=220, fade=None, slack=60):
        super().__init__()
        self.child, self.limit, self.slack, self.expanded = child, limit, slack, False
        child.setParent(self)
        child.installEventFilter(self)
        self.fade = _Fade(self, fade or C["bg"])
        self.btn = QToolButton(self)
        self.btn.setObjectName("expandBtn")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setFixedSize(26, 26)
        self.btn.setIconSize(QSize(12, 12))
        self.btn.clicked.connect(self.toggle)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._busy = False
        self._relayout()

    def foldable(self):
        return self._full() > self.limit + self.slack

    def _full(self):
        w = max(40, self.width())
        if self.child.hasHeightForWidth():
            return self.child.heightForWidth(w)
        if isinstance(self.child, TextView):
            return self.child.height()
        return self.child.sizeHint().height()

    def toggle(self):
        self.expanded = not self.expanded
        self._relayout()
        self.toggled.emit(self.expanded)

    def eventFilter(self, obj, e):
        if obj is self.child and e.type() in (e.Type.Resize, e.Type.LayoutRequest) and not self._busy:
            QTimer.singleShot(0, self._relayout)
        return False

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    def _relayout(self):
        if self._busy:
            return
        self._busy = True
        try:
            w = max(40, self.width())
            if not isinstance(self.child, TextView):
                self.child.resize(w, self._full())
            else:
                self.child.setGeometry(0, 0, w, self.child.height())
            full = self._full()
            fold = full > self.limit + self.slack
            if not fold:
                self.fade.hide()
                self.btn.hide()
                h = full
            elif self.expanded:
                self.fade.hide()
                h = full + 30                       # sitio para la flecha de plegar
            else:
                h = self.limit
                self.fade.setGeometry(0, h - 70, w, 70)
                self.fade.show()
                self.fade.raise_()
            if fold:
                self.btn.setIcon(_icon("ui_chevron_abajo" if not self.expanded else "ui_chevron_arriba", C["tx"], 12))
                self.btn.setToolTip(tr("Mostrar todo") if not self.expanded else tr("Mostrar menos"))
                self.btn.move((w - self.btn.width()) // 2, h - self.btn.height() - 2)
                self.btn.show()
                self.btn.raise_()
            if self.height() != h:
                self.setFixedHeight(h)
        finally:
            self._busy = False

    def sizeHint(self):
        return QSize(self.child.sizeHint().width(), self.height())

    def minimumSizeHint(self):
        return QSize(40, self.height())


def _icon(name, color, size):
    from .theme import icon
    ic = icon(name, color, size)
    if ic.isNull() and name == "ui_chevron_arriba":            # si falta el icono, el de abajo girado
        from PySide6.QtGui import QTransform, QIcon
        return QIcon(pix("ui_chevron_abajo", color, size).transformed(QTransform().rotate(180)))
    return ic


class FitLabel(QLabel):
    """Una línea que elige, de varias versiones del texto (de la más larga a la más corta), la que cabe.
    Así las estadísticas no se parten en cuatro líneas en un panel estrecho; la completa queda en el tooltip."""

    def __init__(self):
        super().__init__()
        self.options, self.tip = [], ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(20)

    def set_options(self, options, tip=""):
        self.options = [o for o in options if o]
        self.tip = tip
        self._fit()

    def _fit(self):
        if not self.options:
            return super().setText("")
        w = max(10, self.width())
        fm = self.fontMetrics()
        pick = next((o for o in self.options if fm.horizontalAdvance(o) <= w), None)
        super().setText(pick if pick is not None else fm.elidedText(self.options[-1], Qt.ElideRight, w))
        full = self.options[0]
        self.setToolTip(full + ("\n" + self.tip if self.tip else "") if pick != full else self.tip)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def sizeHint(self):
        s = super().sizeHint()
        return QSize(self.fontMetrics().horizontalAdvance(self.options[-1]) if self.options else 0, s.height())

    def minimumSizeHint(self):
        return QSize(20, super().minimumSizeHint().height())


class ElidedLabel(QLabel):
    """Una línea que se recorta con «…» cuando no cabe (el texto completo queda en el tooltip)."""

    def __init__(self, text=""):
        super().__init__()
        self.full = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(30)
        self.setText(text)

    def setText(self, text):
        self.full = text or ""
        self._elide()

    def text(self):
        return self.full

    def _elide(self):
        w = max(10, self.width())
        super().setText(self.fontMetrics().elidedText(self.full, Qt.ElideRight, w))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def sizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance(self.full) + 4, super().sizeHint().height())


class FlowLayout(QLayout):
    """Como un QHBoxLayout pero baja a la siguiente fila lo que no cabe (botones de aprobacion, etiquetas…)."""

    def __init__(self, parent=None, spacing=6):
        super().__init__(parent)
        self._items = []
        self._sp = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do(self, rect, test):
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = r.x(), r.y(), 0
        for it in self._items:
            if it.widget() is not None and it.widget().isHidden():
                continue
            sh = it.sizeHint()
            w = min(sh.width(), r.width())
            nx = x + w + self._sp
            if nx - self._sp > r.right() + 1 and line_h > 0:
                x, y = r.x(), y + line_h + self._sp
                nx, line_h = x + w + self._sp, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), QSize(w, sh.height())))
            x, line_h = nx, max(line_h, sh.height())
        return y + line_h - rect.y() + m.bottom()


class OptionRow(QPushButton):
    """Opcion a todo el ancho (boton de verdad: teclado, foco y lector de pantalla), con icono opcional y texto que
    se ajusta en varias lineas."""

    def __init__(self, text, ico=None, name="optionRow", color=None):
        super().__init__()
        self.setObjectName(name)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(text)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 9, 12, 9)
        h.setSpacing(10)
        if ico:
            il = QLabel()
            il.setPixmap(pix(ico, color or C["acc"], 16))
            il.setFixedSize(18, 18)
            h.addWidget(il, 0, Qt.AlignTop)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)     # nunca impone su ancho
        self.label.setMinimumWidth(40)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        h.addWidget(self.label, 1)
        self.text_value = text

    # el tamaño lo decide el contenido (icono + texto ajustable), no el texto del boton
    def sizeHint(self):
        return self.layout().sizeHint()

    def minimumSizeHint(self):
        m = self.layout().contentsMargins()
        return QSize(60, self.label.minimumSizeHint().height() + m.top() + m.bottom())

    def heightForWidth(self, w):
        return self.layout().heightForWidth(w)

    def hasHeightForWidth(self):
        return True


class Switch(QCheckBox):
    """Interruptor de encendido/apagado con el estilo de Jayth. Es un QCheckBox (toggled, isChecked, text) que se
    dibuja como un interruptor: el texto no se pinta, va en la etiqueta de su fila."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(text)
        self._pos = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.valueChanged.connect(self._moved)
        self.toggled.connect(self._go)

    def sizeHint(self):
        return QSize(40, 22)

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def _moved(self, v):
        self._pos = float(v)
        self.update()

    def _go(self, on):
        if not self.isVisible():
            self._pos = 1.0 if on else 0.0
            return self.update()
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def showEvent(self, e):
        self._pos = 1.0 if self.isChecked() else 0.0
        super().showEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = 40, 22
        y = (self.height() - h) / 2.0
        k = self._pos
        off, on = QColor(C["panel2"]), QColor(C["acc"])
        track = QColor(int(off.red() + (on.red() - off.red()) * k), int(off.green() + (on.green() - off.green()) * k),
                       int(off.blue() + (on.blue() - off.blue()) * k))
        if not self.isEnabled():
            track.setAlpha(110)
        p.setPen(QColor(C["line"]) if k < 0.5 else Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(0.5, y + 0.5, w - 1, h - 1, h / 2.0, h / 2.0)
        d = h - 6
        x = 3 + (w - 6 - d) * k
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#FFFFFF") if k >= 0.5 else QColor(C["mut"]))
        p.drawEllipse(QRectF(x, y + 3, d, d))
        if self.hasFocus():
            p.setPen(QColor(C["acc"]))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(-0.5, y - 0.5, w + 1, h + 1), h / 2.0 + 1, h / 2.0 + 1)
        p.end()


class ElideCombo(QComboBox):
    """Lista desplegable de ancho fijo: si la opción elegida no cabe, termina en «…» (completa en el tooltip y en la
    lista desplegada, que se abre con el ancho de la opción más larga)."""

    def paintEvent(self, e):
        from PySide6.QtWidgets import QStylePainter, QStyleOptionComboBox, QStyle
        p = QStylePainter(self)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        room = self.style().subControlRect(QStyle.CC_ComboBox, opt, QStyle.SC_ComboBoxEditField, self).width()
        full = opt.currentText
        opt.currentText = self.fontMetrics().elidedText(full, Qt.ElideRight, max(20, room - 4))
        self.setToolTip(full if opt.currentText != full else "")
        p.drawComplexControl(QStyle.CC_ComboBox, opt)
        p.drawControl(QStyle.CE_ComboBoxLabel, opt)

    def showPopup(self):
        fm = self.fontMetrics()
        widest = max((fm.horizontalAdvance(self.itemText(i)) for i in range(self.count())), default=0)
        self.view().setMinimumWidth(min(620, max(self.width(), widest + 48)))
        super().showPopup()
