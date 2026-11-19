"""Control del ordenador en macOS y Linux (en Windows se usa la API nativa desde tools.py).

Captura con mss (X11 y macOS) o con la utilidad del sistema; ratón y teclado con pynput; ventanas con
AppleScript (macOS) o wmctrl/xdotool (Linux).
Permisos: en macOS hay que conceder a Jayth «Grabación de pantalla» y «Accesibilidad» (Ajustes del Sistema >
Privacidad y seguridad). En Linux con Wayland el control global del ratón/teclado está limitado por diseño;
funciona en sesiones X11 (o con XWayland para apps X11)."""
import os, sys, time, shutil, subprocess, tempfile

MAC = sys.platform == "darwin"


class ControlError(Exception):
    pass


def _need(mod, pip_name):
    try:
        return __import__(mod)
    except Exception as e:
        raise ControlError("Falta el módulo «%s» para controlar el equipo (%s). Instálalo con: pip install %s" % (mod, e, pip_name))


def _wayland():
    return not MAC and os.environ.get("XDG_SESSION_TYPE") == "wayland" and not os.environ.get("DISPLAY")


def _hint():
    if MAC:
        return " En macOS concede a Jayth «Grabación de pantalla» y «Accesibilidad» en Ajustes del Sistema > Privacidad y seguridad."
    if _wayland():
        return " En Wayland el control global está limitado: inicia sesión en X11 («Ubuntu on Xorg») para usarlo."
    return ""


# ---------------------------------------------------------------- pantalla
def _monitor():
    mss = _need("mss", "mss")
    with mss.mss() as s:
        m = s.monitors[1] if len(s.monitors) > 1 else s.monitors[0]
        return dict(m)


def screen_size():
    """Tamaño en las coordenadas que usa el ratón (puntos en macOS, píxeles en Linux)."""
    try:
        m = _monitor()
        return m["width"], m["height"]
    except ControlError:
        raise
    except Exception as e:
        raise ControlError("No se pudo leer el tamaño de la pantalla: %s.%s" % (e, _hint()))


def _grab_raw():
    """Devuelve (QImage, ancho_logico, alto_logico)."""
    from PySide6.QtGui import QImage
    try:
        mss = _need("mss", "mss")
        with mss.mss() as s:
            m = s.monitors[1] if len(s.monitors) > 1 else s.monitors[0]
            shot = s.grab(m)
            img = QImage(bytes(shot.bgra), shot.width, shot.height, shot.width * 4, QImage.Format_RGB32).copy()
            return img, m["width"], m["height"]
    except Exception as first:
        # alternativa: utilidades del sistema (Wayland, o mss sin acceso)
        tmp = os.path.join(tempfile.gettempdir(), "jayth_shot_%d.png" % os.getpid())
        cmds = [["screencapture", "-x", "-C", tmp]] if MAC else [
            ["grim", tmp], ["gnome-screenshot", "-f", tmp], ["spectacle", "-b", "-n", "-o", tmp], ["import", "-window", "root", tmp]]
        for c in cmds:
            if shutil.which(c[0]):
                try:
                    subprocess.run(c, capture_output=True, timeout=15)
                    img = QImage(tmp)
                    if not img.isNull():
                        try:
                            os.remove(tmp)
                        except OSError:
                            pass
                        try:
                            w, h = screen_size()
                        except Exception:
                            w, h = img.width(), img.height()
                        return img, w, h
                except Exception:
                    continue
        raise ControlError("No se pudo capturar la pantalla: %s.%s" % (first, _hint()))


def capture(max_w=1024):
    """PNG reducido + tamaños: (png, ancho_img, alto_img, ancho_pantalla, alto_pantalla)."""
    from PySide6.QtCore import Qt, QBuffer, QByteArray, QIODevice
    img, W, H = _grab_raw()
    tw = min(W, max_w)
    th = max(1, round(H * tw / W))
    small = img.scaled(tw, th, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    small.save(buf, "PNG")
    buf.close()
    return bytes(ba.data()), tw, th, W, H


# ---------------------------------------------------------------- ratón y teclado
_mouse = _kbd = None


def _ctl():
    global _mouse, _kbd
    if _mouse is None:
        try:
            from pynput import mouse, keyboard
        except Exception as e:
            raise ControlError("No se puede controlar el ratón/teclado: %s.%s" % (e, _hint()))
        _mouse, _kbd = mouse.Controller(), keyboard.Controller()
    return _mouse, _kbd


def cursor():
    m, _ = _ctl()
    x, y = m.position
    return int(x), int(y)


def set_cursor(x, y):
    m, _ = _ctl()
    m.position = (x, y)


def click(button="left", double=False):
    from pynput.mouse import Button
    m, _ = _ctl()
    b = {"right": Button.right, "middle": Button.middle}.get(button, Button.left)
    m.click(b, 2 if double else 1)


def wheel(amount):
    m, _ = _ctl()
    m.scroll(0, int(amount))


def type_text(txt, stop=None):
    _, k = _ctl()
    from pynput.keyboard import Key
    for ch in txt:
        if stop is not None and stop.is_set():
            break
        if ch == "\n":
            k.press(Key.enter)
            k.release(Key.enter)
        elif ch == "\t":
            k.press(Key.tab)
            k.release(Key.tab)
        elif ch != "\r":
            k.type(ch)
        time.sleep(0.01)


def _key_names():
    from pynput.keyboard import Key
    n = {"ctrl": Key.ctrl, "control": Key.ctrl, "alt": Key.alt, "option": Key.alt, "shift": Key.shift,
         "win": Key.cmd, "windows": Key.cmd, "super": Key.cmd, "cmd": Key.cmd, "command": Key.cmd, "meta": Key.cmd,
         "enter": Key.enter, "return": Key.enter, "tab": Key.tab, "esc": Key.esc, "escape": Key.esc, "space": Key.space,
         "backspace": Key.backspace, "delete": Key.delete, "del": Key.delete, "home": Key.home, "end": Key.end,
         "pageup": Key.page_up, "pagedown": Key.page_down, "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
         "capslock": Key.caps_lock}
    for opt in ("insert", "print_screen"):
        if hasattr(Key, opt):
            n[opt.replace("_", "")] = getattr(Key, opt)
    for i in range(1, 13):
        n["f%d" % i] = getattr(Key, "f%d" % i)
    return n


def press_combo(parts):
    _, k = _ctl()
    names = _key_names()
    keys = []
    for p in parts:
        if p in names:
            keys.append(names[p])
        elif len(p) == 1:
            keys.append(p)
        else:
            raise ControlError("Tecla desconocida: " + p)
    for x in keys:
        k.press(x)
    for x in reversed(keys):
        k.release(x)


# ---------------------------------------------------------------- ventanas
_AS_LIST = '''
set out to ""
tell application "System Events"
  repeat with p in (every process whose background only is false)
    set pn to name of p
    try
      set ws to name of every window of p
      if (count of ws) is 0 then
        set out to out & pn & linefeed
      else
        repeat with w in ws
          set out to out & pn & " — " & w & linefeed
        end repeat
      end if
    on error
      set out to out & pn & linefeed
    end try
  end repeat
end tell
return out
'''


def windows():
    """Lista de (id, titulo)."""
    if MAC:
        r = subprocess.run(["osascript", "-e", _AS_LIST], capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            raise ControlError("No se pudieron listar las ventanas: %s.%s" % (r.stderr.strip(), _hint()))
        return [(l.split(" — ")[0], l) for l in r.stdout.splitlines() if l.strip()]
    if shutil.which("wmctrl"):
        r = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=10)
        out = []
        for l in r.stdout.splitlines():
            parts = l.split(None, 3)
            if len(parts) == 4:
                out.append((parts[0], parts[3]))
        return out
    if shutil.which("xdotool"):
        r = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", "."], capture_output=True, text=True, timeout=10)
        out = []
        for wid in r.stdout.split():
            t = subprocess.run(["xdotool", "getwindowname", wid], capture_output=True, text=True, timeout=5).stdout.strip()
            if t:
                out.append((wid, t))
        return out
    raise ControlError("Para listar ventanas en Linux instala wmctrl o xdotool (p. ej. sudo apt install wmctrl).")


def focus(wid, title):
    if MAC:
        app = wid.replace('"', '\\"')
        win = title.split(" — ", 1)[1].replace('"', '\\"') if " — " in title else ""
        script = 'tell application "System Events" to set frontmost of process "%s" to true' % app
        if win:
            script += '\ntell application "System Events" to tell process "%s" to perform action "AXRaise" of (first window whose name is "%s")' % (app, win)
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
    elif shutil.which("wmctrl"):
        subprocess.run(["wmctrl", "-i", "-a", wid], capture_output=True, timeout=10)
    else:
        subprocess.run(["xdotool", "windowactivate", wid], capture_output=True, timeout=10)
