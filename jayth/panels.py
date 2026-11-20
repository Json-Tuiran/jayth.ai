# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Paneles que se pueden redimensionar, plegar, mover y recordar.

- Splitter: divisor con zona de agarre comoda (6 px) que pinta solo una linea fina; se resalta al pasar el raton.
  Doble clic en el divisor pliega o recupera el panel plegable de al lado.
- set_visible / animate: mostrar u ocultar un panel recordando su tamaño, con animacion opcional.
- Section: cabecera plegable (▾ / ▸) para listas de la barra lateral.
"""
from PySide6.QtCore import Qt, Signal, QTimer, QVariantAnimation, QEasingCurve, QRect
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QSplitter, QSplitterHandle, QWidget, QPushButton, QHBoxLayout, QSizePolicy
from .theme import C, icon


class _Handle(QSplitterHandle):
    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)
        self._hover = False

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        col = QColor(C["acc"] if self._hover else C["line"])
        w = 2 if self._hover else 1
        if self.orientation() == Qt.Horizontal:
            p.fillRect(QRect((self.width() - w) // 2, 0, w, self.height()), col)
        else:
            p.fillRect(QRect(0, (self.height() - w) // 2, self.width(), w), col)
        p.end()

    def mouseDoubleClickEvent(self, e):
        self.splitter().toggle_near(self)


class Splitter(QSplitter):
    """QSplitter con divisor comodo, plegado por doble clic y aviso (con retardo) cuando cambian los tamaños."""
    changed = Signal()

    def __init__(self, orientation, name=""):
        super().__init__(orientation)
        self.setObjectName(name or "splitter")
        self.setHandleWidth(6)
        self.setChildrenCollapsible(False)
        self._save_t = QTimer(self, singleShot=True, interval=400, timeout=self.changed.emit)
        self.splitterMoved.connect(lambda *_: self._save_t.start())

    def createHandle(self):
        return _Handle(self.orientation(), self)

    def toggle_near(self, handle):
        """Pliega o recupera el panel plegable a un lado del divisor (el lateral, no el central)."""
        i = self.indexOf(handle)
        for idx in (i - 1, i) if i > 0 else ():
            w = self.widget(idx)
            if w is not None and w.property("foldable"):
                set_visible(self, w, not w.isVisible(), animated=True)
                self._save_t.start()
                return


def _sizes_with(split, w, size):
    """Tamaños del splitter dando 'size' a w y quitando (o devolviendo) la diferencia al panel principal."""
    sizes = split.sizes()
    i = split.indexOf(w)
    main = next((k for k in range(split.count()) if split.widget(k).property("main")), None)
    if main is None:
        main = max(range(split.count()), key=lambda k: sizes[k] if k != i else -1)
    delta = size - sizes[i]
    sizes[i] = size
    sizes[main] = max(80, sizes[main] - delta)
    return sizes


def animate(split, sizes, ms=180, done=None):
    start = split.sizes()
    a = QVariantAnimation(split)
    a.setDuration(ms)
    a.setStartValue(0.0)
    a.setEndValue(1.0)
    a.setEasingCurve(QEasingCurve.OutCubic)
    a.valueChanged.connect(lambda t: split.setSizes([int(s0 + (s1 - s0) * t) for s0, s1 in zip(start, sizes)]))
    if done:
        a.finished.connect(done)
    a.start(QVariantAnimation.DeleteWhenStopped)
    return a


def set_visible(split, w, on, animated=False, size=None):
    """Muestra u oculta un panel de un Splitter recordando su ultimo tamaño."""
    i = split.indexOf(w)
    if i < 0:
        w.setVisible(on)
        return
    vertical = split.orientation() == Qt.Vertical
    if not on:
        if not w.isVisible():
            return
        cur = split.sizes()[i]
        if cur > 0:
            w.setProperty("last_size", cur)
        if animated:
            mn = w.minimumHeight() if vertical else w.minimumWidth()
            w.setProperty("_min", mn)
            w.setMinimumHeight(0) if vertical else w.setMinimumWidth(0)

            def fin():
                w.hide()
                w.setMinimumHeight(mn) if vertical else w.setMinimumWidth(mn)
            animate(split, _sizes_with(split, w, 0), done=fin)
        else:
            w.hide()
        return
    if w.isVisible():
        return
    target = size or w.property("last_size") or (w.sizeHint().height() if vertical else w.sizeHint().width()) or 240
    if animated:
        mn = w.minimumHeight() if vertical else w.minimumWidth()
        w.setMinimumHeight(0) if vertical else w.setMinimumWidth(0)
        sizes = split.sizes()
        sizes[i] = 0
        w.show()
        split.setSizes(sizes)
        animate(split, _sizes_with(split, w, int(target)), done=lambda: w.setMinimumHeight(mn) if vertical else w.setMinimumWidth(mn))
    else:
        w.show()
        split.setSizes(_sizes_with(split, w, int(target)))


class Section(QWidget):
    """Cabecera de seccion plegable: «▾ Proyectos». toggled(abierta) al pulsar."""
    toggled = Signal(bool)

    def __init__(self, text, opened=True):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 6, 0, 0)
        h.setSpacing(0)
        self.btn = QPushButton(text)
        self.btn.setObjectName("sectionBtn")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.btn.clicked.connect(lambda: self.set_open(not self.opened, emit=True))
        h.addWidget(self.btn, 1)
        self.extra = QHBoxLayout()
        self.extra.setSpacing(0)
        h.addLayout(self.extra)
        self.opened = opened
        self._paint()

    def _paint(self):
        self.btn.setIcon(icon("ui_chevron_abajo" if self.opened else "ui_chevron_derecha", C["faint"], 11))
        self.btn.setToolTip("Plegar" if self.opened else "Desplegar")

    def set_open(self, on, emit=False):
        self.opened = bool(on)
        self._paint()
        if emit:
            self.toggled.emit(self.opened)
