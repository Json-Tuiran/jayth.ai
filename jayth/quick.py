# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Ventana rápida: un atajo global abre una barrita flotante para preguntar a Jayth desde cualquier programa,
con la opción de adjuntar una captura de lo que había en pantalla en ese momento."""
import sys, threading, ctypes
from PySide6.QtCore import Qt, QObject, Signal, QSize, QTimer, QEvent
from PySide6.QtGui import QPixmap, QGuiApplication, QKeySequence
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QToolButton
from . import APP_NAME, theme
from .theme import C, icon
from .i18n import tr

WIN = sys.platform == "win32"
DEFAULT_HOTKEY = "Ctrl+Alt+J"
_VK = {"SPACE": 0x20, "ESPACIO": 0x20, "ENTER": 0x0D, "TAB": 0x09, "ESC": 0x1B, "INSERT": 0x2D, "HOME": 0x24, "END": 0x23}
_VK.update({"F%d" % i: 0x6F + i for i in range(1, 13)})


def parse_hotkey(combo):
    """'Ctrl+Alt+Space' -> (modificadores de Windows, tecla virtual) o None si no es válido."""
    mods, vk = 0, None
    for part in [p.strip().upper() for p in str(combo or "").replace(" ", "").split("+") if p.strip()]:
        if part in ("CTRL", "CONTROL"):
            mods |= 0x0002
        elif part in ("ALT", "OPTION"):
            mods |= 0x0001
        elif part in ("SHIFT", "MAYÚS", "MAYUS"):
            mods |= 0x0004
        elif part in ("WIN", "CMD", "META", "SUPER"):
            mods |= 0x0008
        elif part in _VK:
            vk = _VK[part]
        elif len(part) == 1 and (part.isalpha() or part.isdigit()):
            vk = ord(part)
        else:
            return None
    return (mods, vk) if mods and vk else None        # sin modificador no vale: secuestraría una tecla normal


def _pynput_combo(combo):
    names = {"CTRL": "<ctrl>", "CONTROL": "<ctrl>", "ALT": "<alt>", "OPTION": "<alt>", "SHIFT": "<shift>", "WIN": "<cmd>", "CMD": "<cmd>",
             "META": "<cmd>", "SUPER": "<cmd>", "SPACE": "<space>", "ESPACIO": "<space>", "ENTER": "<enter>", "TAB": "<tab>"}
    out = []
    for p in [x.strip().upper() for x in combo.split("+") if x.strip()]:
        out.append(names.get(p) or ("<%s>" % p.lower() if p.startswith("F") and p[1:].isdigit() else p.lower()))
    return "+".join(out)


class GlobalHotkey(QObject):
    """Atajo de teclado que funciona aunque Jayth no tenga el foco."""
    pressed = Signal()

    def __init__(self):
        super().__init__()
        self.combo, self.error = "", ""
        self._tid, self._listener = None, None

    def start(self, combo):
        """Registra el atajo. Devuelve True si quedó activo (self.error explica por qué no)."""
        self.stop()
        self.combo, self.error = (combo or "").strip(), ""
        if not self.combo:
            return False
        parsed = parse_hotkey(self.combo)
        if not parsed:
            self.error = tr("Atajo no válido: usa una combinación como Ctrl+Alt+Space.")
            return False
        if WIN:
            ready, res = threading.Event(), {}

            def loop():
                from ctypes import wintypes
                u = ctypes.windll.user32
                self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
                res["ok"] = bool(u.RegisterHotKey(None, 1, parsed[0] | 0x4000, parsed[1]))      # 0x4000: sin repetición al mantener
                ready.set()
                if not res["ok"]:
                    return
                msg = wintypes.MSG()
                while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                    if msg.message == 0x0312:                 # WM_HOTKEY
                        self.pressed.emit()
                u.UnregisterHotKey(None, 1)
            threading.Thread(target=loop, daemon=True).start()
            ready.wait(3)
            if not res.get("ok"):
                self._tid = None
                self.error = tr("El atajo %s ya lo usa otro programa. Elige otro en Ajustes.") % self.combo
                return False
            return True
        try:
            from pynput import keyboard
            self._listener = keyboard.GlobalHotKeys({_pynput_combo(self.combo): self.pressed.emit})
            self._listener.start()
            return True
        except Exception as e:
            self.error = tr("No se pudo activar el atajo global: %s") % e
            return False

    def active(self):
        return bool(self._tid) or self._listener is not None

    def stop(self):
        if self._tid:
            ctypes.windll.user32.PostThreadMessageW(self._tid, 0x0012, 0, 0)      # WM_QUIT
            self._tid = None
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None


class QuickWindow(QWidget):
    submit = Signal(str, object)        # texto, captura PNG (bytes) o None

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle(tr("%s · pregunta rápida") % APP_NAME)
        self.shot = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        box = QFrame()
        box.setObjectName("quickBox")
        outer.addWidget(box)
        v = QVBoxLayout(box)
        v.setContentsMargins(14, 12, 12, 10)
        v.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(theme.logo(26))
        row.addWidget(logo)
        self.edit = QLineEdit()
        self.edit.setObjectName("quickEdit")
        self.edit.setPlaceholderText(tr("Pregunta a %s…") % APP_NAME)
        self.edit.setFrame(False)
        self.edit.returnPressed.connect(self._send)
        self.edit.installEventFilter(self)
        row.addWidget(self.edit, 1)
        self.b_shot = QToolButton()
        self.b_shot.setObjectName("chip")
        self.b_shot.setCheckable(True)
        self.b_shot.setIcon(icon("vista_captura", C["mut"], 15))
        self.b_shot.setIconSize(QSize(15, 15))
        self.b_shot.setText(tr("Con captura"))
        self.b_shot.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.b_shot.setToolTip(tr("Adjunta una imagen de lo que había en tu pantalla al abrir esta ventana (Ctrl+S)"))
        self.b_shot.setAccessibleName(tr("Con captura"))
        self.b_shot.toggled.connect(self._sync)
        row.addWidget(self.b_shot)
        v.addLayout(row)
        self.thumb = QLabel()
        self.thumb.setObjectName("preview")
        self.thumb.hide()
        v.addWidget(self.thumb, 0, Qt.AlignLeft)
        self.hint = QLabel(tr("Enter para enviar · Esc para cerrar"))
        self.hint.setObjectName("faint")
        v.addWidget(self.hint)
        self.setFixedWidth(680)

    def popup(self, shot=None):
        """Abre la ventana centrada en la pantalla del ratón. shot: captura PNG tomada justo antes."""
        self.shot = shot
        self._was_active = False
        self.b_shot.setEnabled(bool(shot))
        self.b_shot.setChecked(False)
        self.edit.clear()
        self._sync()
        from PySide6.QtGui import QCursor
        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        g = scr.availableGeometry()
        self.adjustSize()
        self.move(g.x() + (g.width() - self.width()) // 2, g.y() + int(g.height() * 0.24))
        self.show()
        self.raise_()
        self.activateWindow()
        self._force_front()
        self.edit.setFocus()

    def _force_front(self):
        """Windows no deja robar el foco a una app en segundo plano: tras un atajo global sí está permitido,
        pero hay que pedirlo explícitamente."""
        if not WIN:
            return
        try:
            u = ctypes.windll.user32
            hwnd = int(self.winId())
            fg = u.GetWindowThreadProcessId(u.GetForegroundWindow(), None)
            me = ctypes.windll.kernel32.GetCurrentThreadId()
            u.AttachThreadInput(fg, me, True)
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
            u.SetFocus(hwnd)
            u.AttachThreadInput(fg, me, False)
            if u.GetForegroundWindow() != hwnd:      # último recurso: una pulsación de Alt desbloquea el cambio de ventana
                u.keybd_event(0x12, 0, 0, 0)
                u.keybd_event(0x12, 0, 2, 0)
                u.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _sync(self, *_):
        on = self.b_shot.isChecked() and bool(self.shot)
        if on:
            pm = QPixmap()
            pm.loadFromData(self.shot)
            self.thumb.setPixmap(pm.scaledToHeight(96, Qt.SmoothTransformation))
        self.thumb.setVisible(on)
        self.b_shot.setIcon(icon("vista_captura", C["acc"] if on else C["mut"], 15))
        QTimer.singleShot(0, self.adjustSize)

    def _send(self):
        text = self.edit.text().strip()
        shot = self.shot if self.b_shot.isChecked() else None
        if not text and not shot:
            return
        self.hide()
        self.submit.emit(text or tr("¿Qué ves en esta captura de mi pantalla?"), shot)

    def eventFilter(self, obj, ev):
        if obj is self.edit and ev.type() == QEvent.KeyPress:
            if ev.key() == Qt.Key_Escape:
                self.hide()
                return True
            if ev.key() == Qt.Key_S and ev.modifiers() & Qt.ControlModifier and self.b_shot.isEnabled():
                self.b_shot.toggle()
                return True
        return super().eventFilter(obj, ev)

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() != QEvent.ActivationChange:
            return
        if self.isActiveWindow():
            self._was_active = True
        elif self.isVisible() and getattr(self, "_was_active", False):
            # clic fuera: se cierra. Solo si llegó a tener el foco: si Windows no se lo dio al abrirse, se queda
            # a la vista (siempre encima) en vez de desaparecer al instante.
            QTimer.singleShot(120, lambda: (not self.isActiveWindow()) and self.hide())
