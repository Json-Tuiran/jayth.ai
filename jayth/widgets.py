"""Piezas de interfaz que se adaptan a cualquier ancho (el panel del agente puede ser muy estrecho).

- TextView: texto (Markdown, HTML o plano) que se parte donde haga falta, tambien codigo, rutas y URL sin espacios;
  su alto se ajusta solo al contenido y se puede seleccionar y copiar tal cual (sin caracteres invisibles).
- FlowLayout: coloca botones en fila y baja a la siguiente linea los que no caben.
- OptionRow: opcion clicable de ancho completo con texto que se ajusta (preguntas del agente, sugerencias).
"""
import math
from PySide6.QtCore import Qt, QSize, QRect, QPoint, Signal, QTimer
from PySide6.QtGui import QTextOption, QTextCursor, QColor, QTextFormat, QDesktopServices
from PySide6.QtWidgets import (QTextBrowser, QFrame, QLayout, QSizePolicy, QHBoxLayout, QLabel, QWidget, QAbstractScrollArea, QApplication)
from .theme import C, pix

_CODE_FENCE = int(getattr(getattr(QTextFormat, "Property", QTextFormat), "BlockCodeFence", 0x1060))   # bloque ``` del Markdown


class TextView(QTextBrowser):
    """Texto de solo lectura que nunca ensancha a su contenedor: se ajusta al ancho disponible y crece en alto."""

    def __init__(self, text="", fmt="plain", color=None, size=None, bold=False, selectable=True):
        super().__init__()
        self.setObjectName("textView")
        self.fmt = fmt
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
        self.document().setDocumentMargin(0)
        self.viewport().setAutoFillBackground(False)
        css = "QTextBrowser#textView { background: transparent; border: none; padding: 0; margin: 0;%s%s%s }" % (
            (" color: %s;" % color) if color else "", (" font-size: %s;" % size) if size else "", " font-weight: 600;" if bold else "")
        self.setStyleSheet(css)
        self._natural = None
        self.setText(text)

    def setText(self, text):
        text = text or ""
        if self.fmt == "md":
            self.setMarkdown(text)
            self._wrap_code_blocks()
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
        while b.isValid():
            f = b.blockFormat()
            if f.nonBreakableLines() or f.hasProperty(_CODE_FENCE):
                f.setNonBreakableLines(False)
                f.setBackground(bg)
                f.setLeftMargin(2)
                c = QTextCursor(b)
                c.setBlockFormat(f)
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
        h = int(math.ceil(doc.size().height())) + 1
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


class OptionRow(QFrame):
    """Opcion clicable a todo el ancho, con icono opcional y texto que se ajusta en varias lineas."""
    clicked = Signal()

    def __init__(self, text, ico=None, name="optionRow", color=None):
        super().__init__()
        self.setObjectName(name)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_Hover, True)
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

    def heightForWidth(self, w):
        return self.layout().heightForWidth(w)

    def hasHeightForWidth(self):
        return True

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled() and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(e)
