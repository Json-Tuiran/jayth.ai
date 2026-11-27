# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Control del ordenador en macOS y Linux (en Windows se usa la API nativa desde tools.py).

Captura con mss (X11 y macOS) o con la utilidad del sistema; ratón y teclado con pynput; ventanas con
AppleScript (macOS) o wmctrl/xdotool (Linux).
Permisos: en macOS hay que conceder a Jayth «Grabación de pantalla» y «Accesibilidad» (Ajustes del Sistema >
Privacidad y seguridad).
Linux con Wayland: la captura usa la utilidad del escritorio (grim, gnome-screenshot o spectacle); el ratón y el teclado,
dotool o ydotool (escriben como un teclado y un ratón del sistema, así que valen en GNOME, KDE y Sway; necesitan permiso
sobre /dev/uinput y, ydotool, su servicio ydotoold); las ventanas, swaymsg, hyprctl o kdotool según el escritorio. Leer y
pulsar botones por accesibilidad (ui_elements, click_element) funciona igual que en X11."""
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
    """¿Sesión Wayland? (también con XWayland, que define DISPLAY: antes se tomaba por X11 y la captura salía negra)"""
    return not MAC and (os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY")))


def _desktop():
    return (os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "").lower()


def _hint():
    if MAC:
        return " En macOS concede a Jayth «Grabación de pantalla» y «Accesibilidad» en Ajustes del Sistema > Privacidad y seguridad."
    if _wayland():
        return (" En Wayland: para la captura instala grim (Sway, Hyprland), gnome-screenshot (GNOME) o spectacle (KDE); para el "
                "ratón y el teclado, dotool o ydotool (con su servicio ydotoold y permiso sobre /dev/uinput). Para pulsar botones "
                "sin coordenadas usa ui_elements y click_element, que funcionan en Wayland. Otra opción: iniciar sesión en X11.")
    return ""


# ---------------------------------------------------------------- ratón y teclado en Wayland (dotool / ydotool)
# códigos de tecla de Linux (input-event-codes.h) para ydotool, que no entiende nombres
_KEYCODES = {"esc": 1, "escape": 1, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10, "0": 11, "-": 12,
             "=": 13, "backspace": 14, "tab": 15, "q": 16, "w": 17, "e": 18, "r": 19, "t": 20, "y": 21, "u": 22, "i": 23, "o": 24,
             "p": 25, "[": 26, "]": 27, "enter": 28, "return": 28, "ctrl": 29, "control": 29, "a": 30, "s": 31, "d": 32, "f": 33,
             "g": 34, "h": 35, "j": 36, "k": 37, "l": 38, ";": 39, "'": 40, "`": 41, "shift": 42, "\\": 43, "z": 44, "x": 45,
             "c": 46, "v": 47, "b": 48, "n": 49, "m": 50, ",": 51, ".": 52, "/": 53, "alt": 56, "option": 56, "space": 57,
             "capslock": 58, "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64, "f7": 65, "f8": 66, "f9": 67, "f10": 68,
             "f11": 87, "f12": 88, "home": 102, "up": 103, "pageup": 104, "left": 105, "right": 106, "end": 107, "down": 108,
             "pagedown": 109, "insert": 110, "delete": 111, "del": 111, "win": 125, "windows": 125, "super": 125, "cmd": 125,
             "command": 125, "meta": 125, "printscreen": 99}
# nombres para dotool (los de XKB)
_DOTOOL_NAMES = {"control": "ctrl", "return": "enter", "escape": "esc", "del": "delete", "win": "super", "windows": "super",
                 "cmd": "super", "command": "super", "meta": "super", "option": "alt", "printscreen": "print"}
_wl_pos = [-1, -1]               # Wayland no deja leer la posición del ratón: la última que puso Jayth (-1: ninguna)


def _wl_tool():
    """dotool o ydotool en una sesión Wayland (None fuera de Wayland: allí sirve pynput)."""
    if not _wayland():
        return None
    for t in ("dotool", "ydotool"):
        if shutil.which(t):
            return t
    raise ControlError("En Wayland el ratón y el teclado no se pueden controlar sin ayuda del sistema." + _hint())


def _wl(cmds):
    """Órdenes para dotool (por su entrada) o ydotool (una por llamada)."""
    t = _wl_tool()
    if t == "dotool":
        r = subprocess.run(["dotool"], input="\n".join(cmds) + "\n", capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise ControlError("dotool no pudo: %s.%s" % (r.stderr.strip()[:200], _hint()))
        return
    for c in cmds:
        r = subprocess.run(["ydotool"] + c.split(" ") if not c.startswith("type ") else ["ydotool", "type", "--", c[5:]],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise ControlError("ydotool no pudo: %s.%s" % (r.stderr.strip()[:200], _hint()))


def _wl_btn(button):
    return {"right": "right", "middle": "middle"}.get(button, "left")


def _wl_key(name, down=None):
    """Una tecla para dotool («ctrl») o ydotool («29:1»)."""
    if _wl_tool() == "dotool":
        return _DOTOOL_NAMES.get(name, name)
    code = _KEYCODES.get(name.lower())
    if code is None:
        raise ControlError("Tecla desconocida para ydotool: " + name)
    return "%d:%d" % (code, 1 if down else 0)


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
        if _wayland():                       # mss solo ve las ventanas de XWayland (lo demás sale negro)
            raise ControlError("Wayland")
        mss = _need("mss", "mss")
        with mss.mss() as s:
            m = s.monitors[1] if len(s.monitors) > 1 else s.monitors[0]
            shot = s.grab(m)
            img = QImage(bytes(shot.bgra), shot.width, shot.height, shot.width * 4, QImage.Format_RGB32).copy()
            return img, m["width"], m["height"]
    except Exception as first:
        # alternativa: utilidades del sistema (Wayland, o mss sin acceso)
        tmp = os.path.join(tempfile.gettempdir(), "jayth_shot_%d.png" % os.getpid())
        desk = _desktop()
        cmds = [["screencapture", "-x", "-C", tmp]] if MAC else [
            ["grim", tmp], ["gnome-screenshot", "-f", tmp], ["spectacle", "-b", "-n", "-o", tmp], ["import", "-window", "root", tmp]]
        if "kde" in desk:                    # la del propio escritorio primero
            cmds.insert(0, cmds.pop(2))
        elif "gnome" in desk:
            cmds.insert(0, cmds.pop(1))
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
                            w, h = (img.width(), img.height()) if _wayland() else screen_size()
                        except Exception:
                            w, h = img.width(), img.height()
                        return img, w, h
                except Exception:
                    continue
        raise ControlError("No se pudo capturar la pantalla: %s.%s" % (first, _hint()))


def window_rect(wid, title):
    """(x, y, ancho, alto) de una ventana (AppleScript en macOS; xdotool o wmctrl en Linux); None si no se sabe."""
    if MAC:
        app, win = _mac_names(wid, title)
        sel = '(first window whose name is "%s")' % win if win else "window 1"
        r = subprocess.run(["osascript", "-e", 'tell application "System Events" to tell process "%s" to get {position, size} of %s' % (app, sel)],
                           capture_output=True, text=True, timeout=10)
        try:
            x, y, w, h = [int(float(v)) for v in r.stdout.replace("{", "").replace("}", "").split(",")]
            return x, y, w, h
        except ValueError:
            return None
    try:
        n = int(str(wid), 0)
        if shutil.which("xdotool"):
            r = subprocess.run(["xdotool", "getwindowgeometry", "--shell", str(n)], capture_output=True, text=True, timeout=10)
            d = dict(l.split("=", 1) for l in r.stdout.split() if "=" in l)
            if {"X", "Y", "WIDTH", "HEIGHT"} <= set(d):
                return int(d["X"]), int(d["Y"]), int(d["WIDTH"]), int(d["HEIGHT"])
        if shutil.which("wmctrl"):
            r = subprocess.run(["wmctrl", "-lG"], capture_output=True, text=True, timeout=10)
            for line in r.stdout.splitlines():
                p = line.split(None, 6)
                if len(p) >= 6 and int(p[0], 16) == n:
                    return int(p[2]), int(p[3]), int(p[4]), int(p[5])
    except Exception:
        pass
    return None


def capture(max_w=1024, rect=None, zoom=False):
    """PNG reducido + tamaños: (png, ancho_img, alto_img, ancho_real, alto_real). rect = zona (x, y, ancho, alto);
    zoom: una zona pequeña se amplía (hasta el doble)."""
    from PySide6.QtCore import Qt, QBuffer, QByteArray, QIODevice
    img, W, H = _grab_raw()
    if rect:
        k = img.width() / float(W or img.width())          # la imagen puede venir a otra escala (pantallas Retina)
        x, y, w, h = rect
        x, y = max(0, x), max(0, y)
        w, h = min(w, W - x), min(h, H - y)
        if w > 20 and h > 20:
            img = img.copy(int(x * k), int(y * k), int(w * k), int(h * k))
            W, H = w, h
    tw = min(max_w, W * 2 if zoom else W)
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
    if _wayland():                           # no se puede leer: la última posición que puso Jayth
        return tuple(_wl_pos)
    m, _ = _ctl()
    x, y = m.position
    return int(x), int(y)


def set_cursor(x, y):
    t = _wl_tool()
    if t:
        _wl_pos[:] = [int(x), int(y)]
        if t == "dotool":                    # dotool mueve en fracciones de la pantalla
            img_w, img_h = _wl_screen()
            _wl(["mouseto %.5f %.5f" % (x / float(img_w), y / float(img_h))])
        else:
            _wl(["mousemove --absolute -x %d -y %d" % (x, y)])
        return
    m, _ = _ctl()
    m.position = (x, y)


def _wl_screen():
    """Tamaño de la pantalla en Wayland (el de la captura; si no, el que dice Qt)."""
    try:
        from PySide6.QtGui import QGuiApplication
        s = QGuiApplication.primaryScreen()
        if s is not None:
            g = s.geometry()
            return max(1, g.width()), max(1, g.height())
    except Exception:
        pass
    return 1920, 1080


def click(button="left", double=False):
    t = _wl_tool()
    if t == "dotool":
        return _wl(["click " + _wl_btn(button)] * (2 if double else 1))
    if t == "ydotool":
        code = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}[_wl_btn(button)]
        return _wl(["click --repeat %d %s" % (2 if double else 1, code)])
    from pynput.mouse import Button
    m, _ = _ctl()
    b = {"right": Button.right, "middle": Button.middle}.get(button, Button.left)
    m.click(b, 2 if double else 1)


def mouse_button(button="left", down=True):
    """Pulsar o soltar un botón (para arrastrar)."""
    t = _wl_tool()
    if t == "dotool":
        return _wl(["button%s %s" % ("down" if down else "up", _wl_btn(button))])
    if t == "ydotool":
        base = {"left": 0, "right": 1, "middle": 2}[_wl_btn(button)]
        return _wl(["click 0x%02X" % ((0x40 if down else 0x80) + base)])
    from pynput.mouse import Button
    m, _ = _ctl()
    b = {"right": Button.right, "middle": Button.middle}.get(button, Button.left)
    (m.press if down else m.release)(b)


def hold(parts, down=True):
    """Mantener pulsadas (o soltar) teclas como shift o ctrl mientras se hace clic."""
    t = _wl_tool()
    if t == "dotool":
        return _wl(["key%s %s" % ("down" if down else "up", _wl_key(p)) for p in (parts if down else list(reversed(parts)))])
    if t == "ydotool":
        return _wl(["key " + " ".join(_wl_key(p, down) for p in (parts if down else list(reversed(parts))))])
    _, k = _ctl()
    names = _key_names()
    for p in (parts if down else reversed(parts)):
        key = names.get(p, p if len(p) == 1 else None)
        if key is None:
            raise ControlError("Tecla desconocida: " + p)
        (k.press if down else k.release)(key)


def wheel(amount):
    t = _wl_tool()
    if t == "dotool":
        return _wl(["wheel %d" % int(amount)])
    if t == "ydotool":
        return _wl(["mousemove --wheel -x 0 -y %d" % int(amount)])
    m, _ = _ctl()
    m.scroll(0, int(amount))


def type_text(txt, stop=None):
    if _wl_tool():                           # por líneas: Intro entre ellas
        for i, line in enumerate(str(txt).replace("\r", "").split("\n")):
            if stop is not None and stop.is_set():
                break
            if i:
                press_combo(["enter"])
            if line:
                _wl(["type " + line])
        return
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
    t = _wl_tool()
    if t == "dotool":
        return _wl(["key " + "+".join(_wl_key(p) for p in parts)])
    if t == "ydotool":
        return _wl(["key " + " ".join([_wl_key(p, True) for p in parts] + [_wl_key(p, False) for p in reversed(parts)])])
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


def _wl_windows():
    """Ventanas de un escritorio Wayland que lo permite: Sway (swaymsg), Hyprland (hyprctl) o KDE (kdotool). None si no."""
    import json as _json
    if shutil.which("hyprctl") and os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        r = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=10)
        try:
            return [("hypr:" + c["address"], c.get("title") or c.get("class") or "") for c in _json.loads(r.stdout or "[]") if c.get("mapped", True)]
        except ValueError:
            return None
    if shutil.which("swaymsg") and os.environ.get("SWAYSOCK"):
        r = subprocess.run(["swaymsg", "-t", "get_tree", "-r"], capture_output=True, text=True, timeout=10)
        out = []

        def walk(n):
            if n.get("pid") and n.get("name"):
                out.append(("sway:%d" % n["id"], n["name"]))
            for c in n.get("nodes", []) + n.get("floating_nodes", []):
                walk(c)
        try:
            walk(_json.loads(r.stdout or "{}"))
            return out
        except ValueError:
            return None
    if shutil.which("kdotool"):
        r = subprocess.run(["kdotool", "search", "--name", "."], capture_output=True, text=True, timeout=10)
        out = []
        for wid in r.stdout.split():
            t = subprocess.run(["kdotool", "getwindowname", wid], capture_output=True, text=True, timeout=5).stdout.strip()
            if t:
                out.append(("kde:" + wid, t))
        return out
    return None


def windows():
    """Lista de (id, titulo)."""
    if not MAC and _wayland():
        w = _wl_windows()
        if w is not None:
            return w
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
    w = str(wid)
    if w.startswith("hypr:"):
        return subprocess.run(["hyprctl", "dispatch", "focuswindow", "address:" + w[5:]], capture_output=True, timeout=10)
    if w.startswith("sway:"):
        return subprocess.run(["swaymsg", "[con_id=%s] focus" % w[5:]], capture_output=True, timeout=10)
    if w.startswith("kde:"):
        return subprocess.run(["kdotool", "windowactivate", w[4:]], capture_output=True, timeout=10)
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


def _mac_names(wid, title):
    """(proceso, ventana) para AppleScript, con las comillas escapadas."""
    app = str(wid).replace('"', '\\"')
    win = title.split(" — ", 1)[1].replace('"', '\\"') if " — " in title else ""
    return app, win


def _osa(script, timeout=15):
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise ControlError("macOS no lo permitió: %s.%s" % (r.stderr.strip()[:300], _hint()))
    return r.stdout.strip()


def window_action(wid, title, action, x=None, y=None, w=None, h=None):
    """Maximizar, minimizar, restaurar, cerrar, mover o cambiar el tamaño de una ventana."""
    if MAC:
        app, win = _mac_names(wid, title)
        sel = '(first window whose name is "%s")' % win if win else "window 1"
        tell = 'tell application "System Events" to tell process "%s" to ' % app
        if action == "minimize":
            _osa(tell + 'set value of attribute "AXMinimized" of %s to true' % sel)
        elif action == "restore":
            _osa(tell + 'set value of attribute "AXMinimized" of %s to false' % sel)
        elif action == "close":
            _osa(tell + 'click (first button of %s whose subrole is "AXCloseButton")' % sel)
        elif action == "maximize":
            sw, sh = screen_size()
            _osa(tell + "set position of %s to {0, 25}\n" % sel + tell + "set size of %s to {%d, %d}" % (sel, sw, sh - 25))
        else:                                             # mover / cambiar el tamaño
            if x is not None and y is not None:
                _osa(tell + "set position of %s to {%d, %d}" % (sel, x, y))
            if w is not None and h is not None:
                _osa(tell + "set size of %s to {%d, %d}" % (sel, w, h))
        return
    s = str(wid)
    if s.startswith(("hypr:", "sway:", "kde:")):
        return _wl_window_action(s, action, x, y, w, h)
    if not shutil.which("wmctrl") and not shutil.which("xdotool"):
        raise ControlError("Para manejar ventanas en Linux instala wmctrl o xdotool (p. ej. sudo apt install wmctrl xdotool)." + _hint())
    run = lambda *c: subprocess.run(list(c), capture_output=True, timeout=10)
    if action == "minimize":
        run("xdotool", "windowminimize", str(int(str(wid), 0))) if shutil.which("xdotool") else run("wmctrl", "-i", "-r", wid, "-b", "add,hidden")
    elif action == "restore":
        run("wmctrl", "-i", "-r", wid, "-b", "remove,maximized_vert,maximized_horz,hidden")
        run("wmctrl", "-i", "-a", wid)
    elif action == "maximize":
        run("wmctrl", "-i", "-r", wid, "-b", "add,maximized_vert,maximized_horz")
    elif action == "close":
        run("wmctrl", "-i", "-c", wid) if shutil.which("wmctrl") else run("xdotool", "windowclose", str(int(str(wid), 0)))
    else:
        run("wmctrl", "-i", "-r", wid, "-b", "remove,maximized_vert,maximized_horz")
        run("wmctrl", "-i", "-r", wid, "-e", "0,%d,%d,%d,%d" % (x if x is not None else -1, y if y is not None else -1,
                                                              w if w is not None else -1, h if h is not None else -1))


def _wl_window_action(wid, action, x=None, y=None, w=None, h=None):
    """Lo mismo en Sway, Hyprland y KDE (cada uno con su orden)."""
    run = lambda *c: subprocess.run(list(c), capture_output=True, timeout=10)
    kind, ident = wid.split(":", 1)
    if kind == "hypr":
        a = "address:" + ident
        if action == "close":
            return run("hyprctl", "dispatch", "closewindow", a)
        if action in ("maximize", "restore"):
            run("hyprctl", "dispatch", "focuswindow", a)
            return run("hyprctl", "dispatch", "fullscreen", "1")
        if action == "minimize":
            return run("hyprctl", "dispatch", "movetoworkspacesilent", "special," + a)
        if x is not None and y is not None:
            run("hyprctl", "dispatch", "movewindowpixel", "exact %d %d,%s" % (x, y, a))
        if w is not None and h is not None:
            run("hyprctl", "dispatch", "resizewindowpixel", "exact %d %d,%s" % (w, h, a))
        return
    if kind == "sway":
        sel = "[con_id=%s] " % ident
        cmd = {"close": "kill", "maximize": "fullscreen enable", "restore": "fullscreen disable", "minimize": "move scratchpad"}.get(action)
        if cmd:
            return run("swaymsg", sel + cmd)
        if x is not None and y is not None:
            run("swaymsg", sel + "floating enable, move position %d %d" % (x, y))
        if w is not None and h is not None:
            run("swaymsg", sel + "floating enable, resize set %d %d" % (w, h))
        return
    sub = {"close": ["windowclose"], "minimize": ["windowminimize"], "maximize": ["windowstate", "--add", "MAXIMIZED"],
           "restore": ["windowstate", "--remove", "MAXIMIZED"]}.get(action)
    if sub:
        return run("kdotool", *sub[:1], ident, *sub[1:]) if sub[0] != "windowstate" else run("kdotool", "windowstate", sub[1], sub[2], ident)
    if x is not None and y is not None:
        run("kdotool", "windowmove", ident, str(x), str(y))
    if w is not None and h is not None:
        run("kdotool", "windowsize", ident, str(w), str(h))


# ---------------------------------------------------------------- portapapeles
def clipboard_get():
    cmds = [["pbpaste"]] if MAC else [["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"], ["xsel", "--clipboard", "--output"]]
    for c in cmds:
        if shutil.which(c[0]):
            r = subprocess.run(c, capture_output=True, timeout=10)
            return r.stdout.decode("utf-8", "replace")
    raise ControlError("Para usar el portapapeles en Linux instala wl-clipboard, xclip o xsel.")


def clipboard_set(text):
    cmds = [["pbcopy"]] if MAC else [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
    for c in cmds:
        if shutil.which(c[0]):
            subprocess.run(c, input=text.encode("utf-8"), timeout=10)
            return
    raise ControlError("Para usar el portapapeles en Linux instala wl-clipboard, xclip o xsel.")


# ---------------------------------------------------------------- interfaz por accesibilidad
_MAC_ROLES = {"AXButton": "Button", "AXTextField": "Edit", "AXTextArea": "Edit", "AXSearchField": "Edit", "AXStaticText": "Text",
              "AXCheckBox": "CheckBox", "AXRadioButton": "RadioButton", "AXPopUpButton": "ComboBox", "AXComboBox": "ComboBox",
              "AXMenuItem": "MenuItem", "AXMenuBarItem": "MenuItem", "AXMenuButton": "Button", "AXLink": "Hyperlink",
              "AXTab": "TabItem", "AXCell": "DataItem", "AXRow": "ListItem", "AXSlider": "Slider", "AXIncrementor": "Spinner",
              "AXDisclosureTriangle": "Button"}
_JXA = r"""
function run(argv) {
  var se = Application('System Events');
  var p = se.processes.byName(argv[0]);
  var w = argv[1] ? p.windows.byName(argv[1]) : p.windows[0];
  var keep = argv[3].split(','), limit = parseInt(argv[2]), out = [];
  var els = w.entireContents();
  for (var i = 0; i < els.length && out.length < limit; i++) {
    var e = els[i];
    try {
      var r = e.role();
      if (keep.indexOf(r) < 0) continue;
      var pos = e.position(), sz = e.size(), n = '', v = '', en = true;
      try { n = e.name() || e.description() || e.title() || ''; } catch (x) {}
      try { v = String(e.value() || ''); } catch (x) {}
      try { en = e.enabled(); } catch (x) {}
      out.push({t: r, n: String(n), v: v, x: pos[0], y: pos[1], w: sz[0], h: sz[1], e: en});
    } catch (x) {}
  }
  return JSON.stringify(out);
}
"""
_ATSPI_ROLES = {"push button": "Button", "toggle button": "Button", "text": "Edit", "entry": "Edit", "password text": "Edit",
                "label": "Text", "check box": "CheckBox", "radio button": "RadioButton", "combo box": "ComboBox", "menu item": "MenuItem",
                "menu": "MenuItem", "link": "Hyperlink", "page tab": "TabItem", "list item": "ListItem", "table cell": "DataItem",
                "tree item": "TreeItem", "slider": "Slider", "spin button": "Spinner", "check menu item": "MenuItem",
                "radio menu item": "MenuItem"}


def ui_elements(wid, title, limit=150):
    """Elementos de la interfaz de una ventana: [{t: tipo, n: nombre, v: valor, x, y, w, h, e: activo}] (coordenadas de pantalla)."""
    import json
    if MAC:
        app, win = _mac_names(wid, title)
        r = subprocess.run(["osascript", "-l", "JavaScript", "-e", _JXA, app.replace('\\"', '"'), win.replace('\\"', '"'), str(limit),
                            ",".join(_MAC_ROLES)], capture_output=True, text=True, timeout=40)
        if r.returncode != 0:
            raise ControlError("No pude leer la interfaz: %s.%s" % (r.stderr.strip()[:300], _hint()))
        items = json.loads(r.stdout or "[]")
        for it in items:
            it["t"] = _MAC_ROLES.get(it["t"], it["t"])
        return items
    try:
        import gi
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
    except Exception:
        raise ControlError("Para leer la interfaz de los programas en Linux hace falta AT-SPI (paquetes python3-gi y gir1.2-atspi-2.0). "
                           "Mientras tanto, usa screenshot y click con coordenadas.")
    q = (title or "").lower()
    target = None
    desk = Atspi.get_desktop(0)
    for i in range(desk.get_child_count()):
        app = desk.get_child_at_index(i)
        for j in range(app.get_child_count() if app else 0):
            w = app.get_child_at_index(j)
            if w is not None and q and q in (w.get_name() or "").lower():
                target = w
                break
        if target is not None:
            break
    if target is None:
        raise ControlError("La ventana «%s» no expone su interfaz (accesibilidad). Usa screenshot y click con coordenadas." % title)
    out, stack = [], [target]
    while stack and len(out) < limit:
        e = stack.pop(0)
        try:
            n = e.get_child_count()
            stack.extend(e.get_child_at_index(k) for k in range(min(n, 400)))
            role = _ATSPI_ROLES.get(e.get_role_name())
            if not role:
                continue
            st = e.get_state_set()
            if not st.contains(Atspi.StateType.SHOWING):
                continue
            ext = e.get_extents(Atspi.CoordType.SCREEN)
            val = ""
            try:
                ti = e.get_text_iface()
                if ti is not None:
                    val = ti.get_text(0, min(ti.get_character_count(), 300))
            except Exception:
                pass
            out.append({"t": role, "n": e.get_name() or "", "v": val, "x": ext.x, "y": ext.y, "w": ext.width, "h": ext.height,
                        "e": st.contains(Atspi.StateType.ENABLED)})
        except Exception:
            continue
    return out
