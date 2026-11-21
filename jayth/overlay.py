# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Señales visibles de que el agente está actuando.

- ControlOverlay: mientras el agente usa el ratón y el teclado, un brillo animado recorre los bordes de la pantalla,
  el puntero lleva un halo con la etiqueta «Jayth» que se desliza hasta donde va a actuar (y deja una onda al hacer
  clic) y arriba aparece un aviso de cómo detenerlo. Al capturar la pantalla, los bordes destellan un instante.
  Todo deja pasar los clics menos el aviso (con «Pausar» y «Parar»), que se aparta si el agente va a pulsar donde está;
  en Windows nada de esto sale en las capturas que hace el propio agente.
- glow(widget): el mismo brillo, un momento, alrededor de una zona de la ventana donde el agente acaba de trabajar
  (el lienzo, el editor).

Las herramientas avisan desde el hilo del agente con notify(); la señal de Qt lo lleva al hilo de la interfaz.
"""
import math, time, ctypes
from PySide6.QtCore import Qt, QObject, Signal, QTimer, QPointF, QRectF, QRect
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient, QRadialGradient, QGuiApplication, QPainterPath
from PySide6.QtWidgets import QWidget
from . import core, osys
from .theme import C
from .i18n import tr

FLAGS = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput | Qt.NoDropShadowWindowHint
         | Qt.WindowDoesNotAcceptFocus)
EDGE = 26           # grosor del brillo de los bordes (px lógicos)
HOLD = 2.6          # segundos que sigue encendido tras la última acción con el ratón o el teclado


def animations_on():
    try:
        return core.SET.snapshot().get("animations", True)
    except Exception:
        return True


def _float(w):
    w.setWindowFlags(FLAGS)
    w.setAttribute(Qt.WA_TranslucentBackground, True)
    w.setAttribute(Qt.WA_ShowWithoutActivating, True)
    w.setAttribute(Qt.WA_TransparentForMouseEvents, True)


def _hide_from_capture(w):
    """Windows 10 (2004) o posterior: la ventana no aparece en las capturas (el agente no se ve a sí mismo)."""
    if osys.WIN:
        try:
            ctypes.windll.user32.SetWindowDisplayAffinity(ctypes.c_void_p(int(w.winId())), 0x11)
        except Exception:
            pass


def _acc(alpha):
    c = QColor(C["acc"])
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


class _Edge(QWidget):
    """Un borde de la pantalla: degradado del color de acento hacia dentro, con dos destellos que recorren el contorno."""

    def __init__(self, side, ov):
        super().__init__(None)
        _float(self)
        self.side, self.ov = side, ov

    def paintEvent(self, e):
        a = self.ov.level()
        if a <= 0.005:
            return
        p = QPainter(self)
        w, h = self.width(), self.height()
        side = self.side
        g = {"top": QLinearGradient(0, 0, 0, h), "bottom": QLinearGradient(0, h, 0, 0),
             "left": QLinearGradient(0, 0, w, 0), "right": QLinearGradient(w, 0, 0, 0)}[side]
        g.setColorAt(0.0, _acc(0.95 * a))
        g.setColorAt(0.14, _acc(0.50 * a))
        g.setColorAt(0.5, _acc(0.14 * a))
        g.setColorAt(1.0, _acc(0.0))
        p.fillRect(self.rect(), g)
        # destellos que dan la vuelta a la pantalla (posición a lo largo del contorno)
        W, H = self.ov.size
        P = 2 * (W + H)
        for s in self.ov.spots():
            s %= P
            if side == "top" and s < W:
                c = s - self.x() + self.ov.origin[0]
            elif side == "right" and W <= s < W + H:
                c = s - W
            elif side == "bottom" and W + H <= s < 2 * W + H:
                c = W - (s - W - H)
            elif side == "left" and s >= 2 * W + H:
                c = H - (s - 2 * W - H)
            else:
                continue
            L = 220.0
            horiz = side in ("top", "bottom")
            sg = QLinearGradient(c - L, 0, c + L, 0) if horiz else QLinearGradient(0, c - L, 0, c + L)
            hi = QColor(C["acc_hi"])
            for pos, al in ((0.0, 0.0), (0.5, 0.9 * a), (1.0, 0.0)):
                k = QColor(hi)
                k.setAlphaF(al)
                sg.setColorAt(pos, k)
            depth = QRectF(0, 0, w, h * 0.42) if side == "top" else QRectF(0, h * 0.58, w, h * 0.42) if side == "bottom" else \
                QRectF(0, 0, w * 0.42, h) if side == "left" else QRectF(w * 0.58, 0, w * 0.42, h)
            p.fillRect(depth, sg)
        p.end()


class _Pointer(QWidget):
    """Halo del puntero del agente con la etiqueta «Jayth»; se desliza hasta su destino y deja una onda en cada clic."""
    HX, HY = 26, 24                                      # dónde cae la punta del puntero dentro de la ventana

    def __init__(self, ov):
        super().__init__(None)
        _float(self)
        self.ov = ov
        self.resize(150, 76)
        self.cur = None                                   # posición actual (lógica, de pantalla)
        self.anim = None                                  # (desde, hasta, inicio, duración)
        self.ripples = []
        self.label = "Jayth"

    def glide(self, x, y):
        to = QPointF(x, y)
        if self.cur is None or not self.isVisible() or not animations_on():
            self.cur, self.anim = to, None
        else:
            self.anim = (QPointF(self.cur), to, time.time(), 0.26)
        self._place()

    def click(self):
        self.ripples.append(time.time())

    def step(self):
        if self.anim:
            a, b, t0, d = self.anim
            t = min(1.0, (time.time() - t0) / d)
            e = 1 - (1 - t) ** 3
            self.cur = QPointF(a.x() + (b.x() - a.x()) * e, a.y() + (b.y() - a.y()) * e)
            if t >= 1:
                self.anim = None
            self._place()
        now = time.time()
        self.ripples = [r for r in self.ripples if now - r < 0.6]
        self.update()

    def _place(self):
        if self.cur is not None:
            self.move(int(round(self.cur.x())) - self.HX, int(round(self.cur.y())) - self.HY)

    def paintEvent(self, e):
        lv = self.ov.level(pulse=False)
        if lv <= 0.005:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.HX, self.HY)
        rg = QRadialGradient(c, 22)                       # halo suave alrededor de la punta
        rg.setColorAt(0.0, _acc(0.45 * lv))
        rg.setColorAt(0.55, _acc(0.18 * lv))
        rg.setColorAt(1.0, _acc(0.0))
        p.setPen(Qt.NoPen)
        p.setBrush(rg)
        p.drawEllipse(c, 22, 22)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_acc(0.95 * lv), 1.6))
        p.drawEllipse(c, 9, 9)
        now = time.time()
        for r in self.ripples:                            # ondas de los clics
            t = (now - r) / 0.6
            pen = QPen(_acc((1 - t) * 0.9 * lv), 2.0)
            p.setPen(pen)
            p.drawEllipse(c, 6 + 20 * t, 6 + 20 * t)
        # etiqueta «Jayth» abajo a la derecha del puntero
        f = p.font()
        f.setPointSizeF(8.5)
        f.setBold(True)
        p.setFont(f)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(self.label)
        box = QRectF(self.HX + 14, self.HY + 16, tw + 16, fm.height() + 6)
        path = QPainterPath()
        path.addRoundedRect(box, box.height() / 2, box.height() / 2)
        p.setPen(Qt.NoPen)
        p.setBrush(_acc(0.95 * lv))
        p.drawPath(path)
        txt = QColor(C["on_acc"])
        txt.setAlphaF(lv)
        p.setPen(txt)
        p.drawText(box, Qt.AlignCenter, self.label)
        p.end()


class _Notice(QWidget):
    """Aviso arriba en el centro: el agente tiene el control, con «Pausar» (para usar tú el ratón un momento) y «Parar».
    Es la única pieza que recibe clics; no se lleva el foco de la ventana en la que trabaja el agente."""
    TEXT = tr("Jayth está usando el ratón y el teclado")
    PAUSED = tr("En pausa: puedes usar el ratón y el teclado")

    def __init__(self, ov):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint
                            | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.ov = ov
        self.hover = None
        self.btns = {}
        self.fit()

    def _labels(self):
        from . import tools as T
        return (tr("Seguir") if T.PAUSED.is_set() else tr("Pausar")), tr("Parar")

    def fit(self):
        from . import tools as T
        self.ensurePolished()                         # la fuente que pone la hoja de estilos de la app
        fm = self.fontMetrics()
        text = self.PAUSED if T.PAUSED.is_set() else self.TEXT
        a, b = self._labels()
        bw = [fm.horizontalAdvance(t) + 22 for t in (a, b)]
        h = fm.height() + 18
        self.resize(28 + fm.horizontalAdvance(text) + 14 + bw[0] + 6 + bw[1] + 6, h)
        x = self.width() - 6 - bw[1]
        bh = h - 10
        self.btns = {"stop": QRect(x, 5, bw[1], bh), "pause": QRect(x - 6 - bw[0], 5, bw[0], bh)}

    def mouseMoveEvent(self, e):
        k = next((k for k, r in self.btns.items() if r.contains(e.position().toPoint())), None)
        if k != self.hover:
            self.hover = k
            self.setCursor(Qt.PointingHandCursor if k else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def mousePressEvent(self, e):
        k = next((k for k, r in self.btns.items() if r.contains(e.position().toPoint())), None)
        if k:
            self.ov.press(k)

    def paintEvent(self, e):
        from . import tools as T
        lv = self.ov.level(pulse=False)
        if lv <= 0.005:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        bg = QColor(C["panel2"])
        bg.setAlphaF(0.96 * lv)
        p.setBrush(bg)
        paused = T.PAUSED.is_set()
        p.setPen(QPen(QColor(C["warn"]) if paused else _acc(0.9 * lv), 1.2))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setPen(Qt.NoPen)
        dot = QColor(C["warn"]) if paused else _acc(lv * (0.6 + 0.4 * math.sin(time.time() * 4)))   # punto que late
        p.setBrush(dot)
        p.drawEllipse(QPointF(16, r.center().y()), 4, 4)
        t = QColor(C["tx"])
        t.setAlphaF(lv)
        p.setPen(t)
        p.setFont(self.font())
        left = self.btns["pause"].left() - 8
        p.drawText(QRectF(28, 0, left - 28, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.PAUSED if paused else self.TEXT)
        a, b = self._labels()
        for k, label in (("pause", a), ("stop", b)):
            br = QRectF(self.btns[k]).adjusted(0.5, 0.5, -0.5, -0.5)
            col = QColor(C["bad"] if k == "stop" else C["tx"])
            fill = QColor(col)
            fill.setAlphaF((0.22 if self.hover == k else 0.10) * lv)
            p.setBrush(fill)
            edge = QColor(col)
            edge.setAlphaF(0.55 * lv)
            p.setPen(QPen(edge, 1))
            p.drawRoundedRect(br, br.height() / 2, br.height() / 2)
            col.setAlphaF(lv)
            p.setPen(col)
            p.drawText(br, Qt.AlignCenter, label)
        p.end()


class ControlOverlay(QObject):
    """Brillo en los bordes + puntero del agente + aviso, mientras el agente controla el equipo."""
    sig = Signal(str, float, float)

    def __init__(self):
        super().__init__()
        self.sig.connect(self._on, Qt.QueuedConnection)
        self.parts = None
        self.until = 0.0          # encendido hasta…
        self.flash = 0.0          # destello de una captura hasta…
        self.fade = 0.0
        self.t0 = time.time()
        self.size, self.origin, self.dpr = (1, 1), (0, 0), 1.0
        self.bottom = False       # el aviso se apartó abajo (el agente iba a hacer clic donde estaba)
        self.timer = QTimer(self, interval=33, timeout=self._frame)

    # --- desde cualquier hilo
    def notify(self, kind, x=-1.0, y=-1.0):
        """kind: move / click / scroll / key / focus (control), look (captura), hide / show (alrededor de una captura
        en macOS y Linux), end. x, y en píxeles reales de la pantalla principal."""
        try:
            self.sig.emit(kind, float(x), float(y))
        except RuntimeError:
            pass

    # --- en el hilo de la interfaz
    def _build(self):
        scr = QGuiApplication.primaryScreen()
        g = scr.geometry()
        self.size, self.origin, self.dpr = (g.width(), g.height()), (g.x(), g.y()), scr.devicePixelRatio() or 1.0
        if self.parts is None:
            self.parts = {s: _Edge(s, self) for s in ("top", "bottom", "left", "right")}
            self.pointer = _Pointer(self)
            self.notice = _Notice(self)
        e = self.parts
        e["top"].setGeometry(g.x(), g.y(), g.width(), EDGE)
        e["bottom"].setGeometry(g.x(), g.y() + g.height() - EDGE, g.width(), EDGE)
        e["left"].setGeometry(g.x(), g.y(), EDGE, g.height())
        e["right"].setGeometry(g.x() + g.width() - EDGE, g.y(), EDGE, g.height())
        self._place_notice()

    def _place_notice(self):
        from . import tools as T
        g = QGuiApplication.primaryScreen().geometry()
        n = self.notice
        n.fit()
        x = g.x() + (g.width() - n.width()) // 2
        y = g.y() + (g.height() - n.height() - 54 if self.bottom else 10)
        n.move(x, y)
        d = self.dpr
        T.NOTICE_RECT = (int((x - g.x()) * d), int((y - g.y()) * d), int((x - g.x() + n.width()) * d), int((y - g.y() + n.height()) * d))

    def press(self, k):
        """Botones del aviso: «Pausar» / «Seguir» y «Parar»."""
        from . import tools as T
        if k == "pause":
            if T.PAUSED.is_set():
                T.PAUSED.clear()
            else:
                T.PAUSED.set()
                self.pointer.hide()
                self.pointer.cur = None
        else:
            T.PAUSED.clear()
            run = T.CONTROL_RUN
            if run is not None:
                run.request_stop()
            self.until = time.time()
        self._place_notice()
        self.notice.update()

    def _windows(self):
        return list(self.parts.values()) + [self.pointer, self.notice] if self.parts else []

    def _show(self, w):
        if not w.isVisible():
            w.show()
            _hide_from_capture(w)
            w.raise_()

    def _on(self, kind, x, y):
        self._build()
        now = time.time()
        if kind == "hide":
            for w in self._windows():
                w.hide()
            return
        if kind == "end":
            self.until = min(self.until, now)
        elif kind == "dodge":                          # el agente va a hacer clic donde está el aviso: al otro extremo
            self.bottom = not self.bottom
            self._place_notice()
        elif kind == "paused":
            self.until = now + HOLD
            self._show(self.notice)
            for w in self.parts.values():
                self._show(w)
        elif kind == "look":
            self.flash = now + 0.7
            for w in self.parts.values():
                self._show(w)
        elif kind == "show":
            pass
        else:                                          # el agente mueve el ratón o escribe
            self.until = now + HOLD
            for w in list(self.parts.values()) + [self.notice]:
                self._show(w)
            if x >= 0 and y >= 0:
                self.pointer.glide(self.origin[0] + x / self.dpr, self.origin[1] + y / self.dpr)
                self._show(self.pointer)
            if kind == "click":
                self.pointer.click()
        if kind == "show" and self.fade > 0.01:
            for w in self._windows():
                if w is not self.pointer or self.pointer.cur is not None:
                    self._show(w)
        self.timer.start()

    def spots(self):
        P = 2 * (self.size[0] + self.size[1])
        s = (time.time() - self.t0) * 900 if animations_on() else 0
        return (s, s + P / 2)

    def level(self, pulse=True):
        if not pulse or not animations_on():
            return self.fade
        return self.fade * (0.78 + 0.22 * math.sin((time.time() - self.t0) * 2.6))

    def _frame(self):
        from . import tools as T
        now = time.time()
        if T.PAUSED.is_set():                           # en pausa el aviso sigue a la vista hasta «Seguir» o «Parar»
            self.until = max(self.until, now + HOLD)
        target = 1.0 if now < self.until else (0.85 if now < self.flash else 0.0)
        speed = 0.18 if target > self.fade else 0.08
        self.fade += (target - self.fade) * (speed if animations_on() else 1.0)
        if target == 0.0 and self.fade < 0.02:
            self.fade = 0.0
            for w in self._windows():
                w.hide()
            self.pointer.cur = None
            self.timer.stop()
            T.NOTICE_RECT = None
            self.bottom = False
            return
        if now >= self.until:                           # una captura sola: solo los bordes
            self.notice.hide()
            self.pointer.hide()
        for w in self.parts.values():
            w.update()
        self.pointer.step()
        self.notice.update()


class _GlowFrame(QWidget):
    """Brillo animado alrededor de una zona de la ventana (el agente acaba de trabajar ahí); se apaga solo."""

    def __init__(self, target, seconds):
        super().__init__(target)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.t0, self.seconds = time.time(), seconds
        self.setGeometry(target.rect())
        self.timer = QTimer(self, interval=33, timeout=self._tick)
        self.timer.start()
        self.show()
        self.raise_()

    def _tick(self):
        if time.time() - self.t0 > self.seconds:
            self.timer.stop()
            self.hide()
            self.deleteLater()
            return
        if self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())
        self.update()

    def paintEvent(self, e):
        t = time.time() - self.t0
        k = min(1.0, t / 0.25) * min(1.0, max(0.0, (self.seconds - t) / 0.6))      # aparece y se desvanece
        if k <= 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        for i in range(10):                                  # resplandor hacia dentro
            p.setPen(QPen(_acc(k * 0.55 * (1 - i / 10.0) ** 2), 1.0))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(0.5 + i, 0.5 + i, -0.5 - i, -0.5 - i), 10, 10)
        # un destello que recorre el contorno
        W, H = r.width(), r.height()
        P = 2 * (W + H)
        s = (t * 700) % P
        x, y = (s, 0) if s < W else (W, s - W) if s < W + H else (W - (s - W - H), H) if s < 2 * W + H else (0, H - (s - 2 * W - H))
        rg = QRadialGradient(QPointF(x, y), 90)
        hi = QColor(C["acc_hi"])
        hi.setAlphaF(0.7 * k)
        rg.setColorAt(0, hi)
        rg.setColorAt(1, _acc(0))
        p.setPen(QPen(QBrush(rg), 3))
        p.drawRoundedRect(r.adjusted(1.5, 1.5, -1.5, -1.5), 10, 10)
        p.end()


def glow(widget, seconds=1.8):
    """Destaca un momento la zona donde el agente acaba de trabajar (sin animaciones: no hace nada)."""
    if widget is None or not widget.isVisible() or not animations_on():
        return None
    for old in widget.findChildren(_GlowFrame):
        old.t0 = time.time()                              # ya brillaba: se alarga
        return old
    return _GlowFrame(widget, seconds)
