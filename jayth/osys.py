# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Todo lo que cambia entre Windows, macOS y Linux, en un solo sitio: carpetas, terminal, abrir archivos,
papelera, procesos, inicio con el sistema y fuentes."""
import os, sys, shlex, shutil, signal, subprocess, platform

WIN = sys.platform == "win32"
MAC = sys.platform == "darwin"
LINUX = sys.platform.startswith("linux")
NO_WINDOW = 0x08000000 if WIN else 0
FROZEN = getattr(sys, "frozen", False)          # empaquetado (PyInstaller)


def os_label():
    if WIN:
        return "Windows %s" % platform.release()
    if MAC:
        return "macOS %s" % (platform.mac_ver()[0] or "")
    try:
        info = dict(l.strip().split("=", 1) for l in open("/etc/os-release") if "=" in l)
        return "Linux (%s)" % info.get("PRETTY_NAME", "").strip('"')
    except OSError:
        return "Linux"


# ---------------------------------------------------------------- terminal
def shell_name():
    return "PowerShell" if WIN else ("zsh" if MAC and os.path.exists("/bin/zsh") else "bash")


def shell_label():
    """La terminal tal como hay que decírsela al modelo: en Windows es la 5.1 de siempre, que no entiende lo de la 7."""
    return "Windows PowerShell 5.1" if WIN else shell_name()


EXIT_MARK = "__jayth_ultimo_codigo__="        # run_command: con qué código terminó el último programa (lo dice la propia terminal)


def shell_argv(command, report_exit=False):
    """Argumentos para ejecutar un comando en la terminal del sistema. report_exit (Windows): la última línea de la salida
    será EXIT_MARK + el código del último programa ejecutado, que PowerShell no devuelve como código propio."""
    if WIN:
        import base64
        # el prefijo, en su propia línea: así los errores de PowerShell señalan la columna real de la orden del modelo
        prefix = "[Console]::OutputEncoding=[Text.Encoding]::UTF8;$OutputEncoding=[Text.Encoding]::UTF8;$ProgressPreference='SilentlyContinue'\n"
        if report_exit:                  # …y la terminal acaba con el mismo código con el que habría acabado sin esta línea
            command += ("\n;$__jy=$?;$__jl=$LASTEXITCODE;Write-Output ('%s' + $__jl);"
                        "if(-not $__jy){if($__jl -is [int]){exit $__jl}else{exit 1}}" % EXIT_MARK)
        enc = base64.b64encode((prefix + command).encode("utf-16-le")).decode()
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc]
    sh = "/bin/zsh" if MAC and os.path.exists("/bin/zsh") else ("/bin/bash" if os.path.exists("/bin/bash") else "/bin/sh")
    return [sh, "-lc", command]      # -l: carga el PATH del usuario (en macOS las apps graficas arrancan con un PATH minimo)


def interactive_shell_argv():
    """Terminal persistente que lee comandos por stdin (para el panel de terminal del modo Code)."""
    if WIN:
        return ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "-"]
    sh = "/bin/zsh" if MAC and os.path.exists("/bin/zsh") else ("/bin/bash" if os.path.exists("/bin/bash") else "/bin/sh")
    return [sh, "-l", "-s"]


def popen_kwargs():
    """Sin ventana de consola en Windows; grupo de procesos propio en macOS/Linux (para poder cerrarlo entero)."""
    return {"creationflags": NO_WINDOW} if WIN else {"start_new_session": True}


_SYNC_NAMES = (("onedrive", "OneDrive"), ("dropbox", "Dropbox"), ("google drive", "Google Drive"), ("googledrive", "Google Drive"),
               ("mi unidad", "Google Drive"), ("my drive", "Google Drive"), ("icloud", "iCloud"), ("mobile documents", "iCloud"),
               ("pcloud", "pCloud"), ("nextcloud", "Nextcloud"), ("megasync", "MEGA"))


def synced_service(path):
    """Nombre del servicio que sincroniza esa carpeta con la nube (OneDrive, Dropbox, iCloud…) o '' si no está en ninguna.
    En muchos equipos con Windows la carpeta Documentos está dentro de OneDrive sin que el usuario lo haya decidido."""
    p = os.path.normcase(os.path.abspath(str(path or "")))
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        root = os.environ.get(var)
        if root and (p + os.sep).startswith(os.path.normcase(os.path.abspath(root)) + os.sep):
            return "OneDrive"
    parts = [x.lower() for x in p.replace("\\", "/").split("/") if x]
    for part in parts:
        for key, name in _SYNC_NAMES:
            if part == key or part.startswith(key + " ") or part.startswith(key + "-"):
                return name
    return ""


def interrupt_tree(pid):
    """Pide a un proceso en segundo plano (y a los que abrió) que termine con orden, como Ctrl+C en una terminal: así un
    servidor cierra sus archivos y conexiones. No espera ni garantiza nada: quien llama espera unos segundos y, si sigue
    vivo, usa kill_tree. Devuelve True si se pudo enviar la señal."""
    try:
        if WIN:
            # los procesos se lanzan sin ventana pero con consola propia (oculta); un ayudante se engancha a ella y manda
            # Ctrl+C (Jayth no tiene consola y no puede hacerlo él mismo sin tocar la suya): app.py --interrupt PID
            r = subprocess.run(launch_argv() + ["--interrupt", str(int(pid))], capture_output=True, timeout=8, creationflags=NO_WINDOW)
            return r.returncode == 0
        try:
            os.killpg(os.getpgid(pid), signal.SIGINT)
        except (ProcessLookupError, PermissionError):
            os.kill(pid, signal.SIGINT)
        return True
    except Exception:
        return False


def kill_tree(pid):
    try:
        if WIN:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, creationflags=NO_WINDOW)
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                os.kill(pid, signal.SIGTERM)
    except Exception:
        pass


# ---------------------------------------------------------------- archivos
def open_path(target):
    """Abre un archivo, carpeta o URL con la aplicacion predeterminada del sistema."""
    if WIN:
        os.startfile(target)
    elif MAC:
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def reveal(path):
    """Muestra el archivo seleccionado en el Explorador / Finder (o abre su carpeta)."""
    try:
        if WIN:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif MAC:
            subprocess.Popen(["open", "-R", path])
        else:
            open_path(os.path.dirname(path))
    except Exception:
        open_path(os.path.dirname(path))


def open_terminal(command, cwd=None):
    """Abre una ventana de terminal del sistema que ejecuta el comando y se queda abierta (para que el usuario vea
    la salida y siga escribiendo). Devuelve False si no encuentra ninguna terminal."""
    cwd = cwd if cwd and os.path.isdir(cwd) else os.path.expanduser("~")
    if WIN:
        import base64
        enc = base64.b64encode(command.encode("utf-16-le")).decode()
        subprocess.Popen(["powershell.exe", "-NoExit", "-NoLogo", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc],
                         cwd=cwd, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10))
        return True
    if MAC:
        script = "cd %s && %s" % (shlex.quote(cwd), command)
        esc = script.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.Popen(["osascript", "-e", 'tell application "Terminal" to do script "%s"' % esc, "-e", 'tell application "Terminal" to activate'])
        return True
    sh = 'cd %s && %s; exec "${SHELL:-bash}"' % (shlex.quote(cwd), command)
    for term, args in (("x-terminal-emulator", ["-e"]), ("gnome-terminal", ["--"]), ("konsole", ["-e"]), ("xfce4-terminal", ["-x"]),
                       ("kitty", []), ("alacritty", ["-e"]), ("xterm", ["-e"])):
        if shutil.which(term):
            subprocess.Popen([term] + args + ["bash", "-c", sh], start_new_session=True)
            return True
    return False


def run_program(target, args=""):
    """Lanza un programa con argumentos sin esperar a que termine."""
    if WIN:
        subprocess.Popen('start "" "%s" %s' % (target, args), shell=True)
    elif MAC and target.endswith(".app"):
        subprocess.Popen(["open", "-a", target, "--args"] + shlex.split(args))
    else:
        subprocess.Popen([target] + shlex.split(args), start_new_session=True)


def trash(path):
    """Envia a la papelera del sistema (recuperable). Devuelve True si lo consiguio."""
    path = os.path.abspath(path)
    if WIN:
        ps = "Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.FileIO.FileSystem]::%s('%s','OnlyErrorDialogs','SendToRecycleBin')" % (
            "DeleteDirectory" if os.path.isdir(path) else "DeleteFile", path.replace("'", "''"))
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, creationflags=NO_WINDOW)
    elif MAC:
        subprocess.run(["osascript", "-e", 'tell application "Finder" to delete POSIX file "%s"' % path.replace('"', '\\"')], capture_output=True)
    else:
        if shutil.which("gio"):
            subprocess.run(["gio", "trash", path], capture_output=True)
        if os.path.exists(path):                      # especificacion freedesktop de la papelera
            import datetime, urllib.parse
            base = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "Trash")
            os.makedirs(os.path.join(base, "files"), exist_ok=True)
            os.makedirs(os.path.join(base, "info"), exist_ok=True)
            name, i = os.path.basename(path), 1
            while os.path.exists(os.path.join(base, "files", name)):
                i += 1
                name = "%s.%d" % (os.path.basename(path), i)
            with open(os.path.join(base, "info", name + ".trashinfo"), "w") as f:
                f.write("[Trash Info]\nPath=%s\nDeletionDate=%s\n" % (urllib.parse.quote(path), datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")))
            shutil.move(path, os.path.join(base, "files", name))
    return not os.path.exists(path)


def exe(name):
    return name + ".exe" if WIN else name


# ---------------------------------------------------------------- carpetas del usuario
def data_home(app="Jayth"):
    if WIN:
        return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local"), app)
    if MAC:
        return os.path.expanduser("~/Library/Application Support/%s" % app)
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), app.lower())


def documents_dir():
    if WIN:
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:
                return buf.value
        except Exception:
            pass
    elif LINUX and shutil.which("xdg-user-dir"):
        try:
            d = subprocess.run(["xdg-user-dir", "DOCUMENTS"], capture_output=True, text=True, timeout=3).stdout.strip()
            if d and os.path.isdir(d):
                return d
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def protected_paths():
    """Rutas del sistema: escribir ahi siempre pide confirmacion."""
    if WIN:
        return ["c:\\windows", "c:\\program files", "c:\\program files (x86)", "c:\\programdata",
                os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu").lower()]
    if MAC:
        return ["/system", "/library", "/usr", "/bin", "/sbin", "/etc", "/private", "/applications", os.path.expanduser("~/library/launchagents").lower()]
    return ["/usr", "/bin", "/sbin", "/etc", "/boot", "/lib", "/lib64", "/opt", "/var", "/sys", "/proc", os.path.expanduser("~/.config/autostart").lower()]


# ---------------------------------------------------------------- inicio con el sistema
def launch_argv():
    """Como se vuelve a lanzar Jayth (empaquetado o desde el codigo)."""
    if FROZEN:
        # AppImage: sys.executable vive en un montaje temporal; hay que relanzar el propio .AppImage
        return [os.environ["APPIMAGE"]] if os.environ.get("APPIMAGE") else [sys.executable]
    exe_ = sys.executable.replace("python.exe", "pythonw.exe") if WIN else sys.executable
    from . import paths
    return [exe_, os.path.join(paths.APP_DIR, "app.py")]


def set_autostart(on, app="Jayth"):
    argv = launch_argv() + ["--minimized"]
    if WIN:
        link = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup", app + ".lnk")
        if not on:
            if os.path.exists(link):
                os.remove(link)
            return
        from . import paths
        target, args = argv[0], " ".join('"%s"' % a if " " in a else a for a in argv[1:])
        icon = target if FROZEN else paths.ICON
        ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');$s.TargetPath='%s';$s.Arguments='%s';"
              "$s.WorkingDirectory='%s';$s.IconLocation='%s';$s.Save()" %
              (link, target, args.replace("'", "''"), paths.APP_DIR, icon))
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, creationflags=NO_WINDOW)
    elif MAC:
        plist = os.path.expanduser("~/Library/LaunchAgents/ai.jayth.app.plist")
        if not on:
            if os.path.exists(plist):
                os.remove(plist)
            return
        os.makedirs(os.path.dirname(plist), exist_ok=True)
        items = "".join("<string>%s</string>" % a for a in argv)
        with open(plist, "w") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0"><dict><key>Label</key><string>ai.jayth.app</string><key>ProgramArguments</key><array>%s</array>'
                    '<key>RunAtLoad</key><true/></dict></plist>\n' % items)
    else:
        desk = os.path.expanduser("~/.config/autostart/jayth.desktop")
        if not on:
            if os.path.exists(desk):
                os.remove(desk)
            return
        os.makedirs(os.path.dirname(desk), exist_ok=True)
        with open(desk, "w") as f:
            f.write("[Desktop Entry]\nType=Application\nName=%s\nExec=%s\nX-GNOME-Autostart-enabled=true\n" % (app, " ".join(shlex.quote(a) for a in argv)))


# ---------------------------------------------------------------- fuentes
def ui_font():
    if WIN:
        return "'Segoe UI'"
    if MAC:
        return "'.AppleSystemUIFont', 'Helvetica Neue'"
    return "'Inter', 'Noto Sans', 'Ubuntu', 'Cantarell', 'DejaVu Sans'"


def mono_font():
    if WIN:
        return "Consolas"
    if MAC:
        return "Menlo"
    return "DejaVu Sans Mono"
