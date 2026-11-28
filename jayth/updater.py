# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Novedades: versiones nuevas de Jayth (GitHub) y de los modelos instalados (Hugging Face).

Tres formas de instalacion:
- "frozen": la app empaquetada (instalador .exe, .dmg o AppImage). Se actualiza desde GitHub Releases.
- "git": una copia clonada del repositorio. Se actualiza con git pull.
- "zip": instalada desde el codigo con install.ps1. Se vuelve a ejecutar el instalador.
"""
import os, re, sys, json, time, shlex, shutil, platform, tempfile, subprocess, urllib.request
from . import paths, osys, APP_NAME, __version__
from .provision import pretty_name, get_json, download, Cancelled
from .i18n import tr

REPO = "Json-Tuiran/jayth.ai"
NO_WINDOW = osys.NO_WINDOW
DETACHED = 0x00000008 if osys.WIN else 0


# ---------------------------------------------------------------- Jayth
def installed():
    """Version instalada: empaquetada, commit de git (copia clonada) o installed.json (instalador desde el codigo)."""
    if osys.FROZEN and osys.store_package():           # Microsoft Store: la tienda la actualiza
        return {"kind": "store", "version": __version__}
    if osys.FROZEN:
        return {"kind": "frozen", "version": __version__}
    git = os.path.join(paths.APP_DIR, ".git")
    if os.path.isdir(git):
        try:
            ref = open(os.path.join(git, "HEAD")).read().strip()
            sha = open(os.path.join(git, ref[5:].strip())).read().strip() if ref.startswith("ref:") else ref
            return {"sha": sha, "kind": "git"}
        except OSError:
            pass
    try:
        with open(os.path.join(paths.APP_DIR, "installed.json"), encoding="utf-8-sig") as f:
            d = json.load(f)
            d["kind"] = "zip"
            return d
    except (OSError, ValueError):
        return {"sha": "", "kind": "zip"}


def latest():
    d = get_json("https://api.github.com/repos/%s/commits/main" % REPO, timeout=12)
    return {"sha": d["sha"], "date": d["commit"]["committer"]["date"][:10], "message": d["commit"]["message"].splitlines()[0]}


def _vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:3])


def asset_pattern():
    """Nombre del paquete de este sistema dentro de una Release."""
    arm = platform.machine().lower() in ("arm64", "aarch64")
    if osys.WIN:
        return r"^Jayth-Setup-[\d.]+-x64\.exe$"
    if osys.MAC:
        return r"^Jayth-[\d.]+-macos-%s\.dmg$" % ("arm64" if arm else "x64")
    return r"^Jayth-[\d.]+-linux-%s\.AppImage$" % ("aarch64" if arm else "x86_64")


def _asset(a):
    dig = (a or {}).get("digest") or ""
    return {"name": a["name"], "url": a["browser_download_url"], "size": a["size"],
            "sha256": dig.split(":", 1)[1] if dig.startswith("sha256:") else ""} if a else None


def patch_name(version):
    """Nombre del paquete de cambios que lleva de la versión instalada a `version` (solo Windows por ahora)."""
    return "Jayth-parche-%s-a-%s-%s.zip" % (__version__, version, PATCH_PLATFORM)


def latest_release():
    rel = get_json("https://api.github.com/repos/%s/releases/latest" % REPO, timeout=12)
    asset = next((a for a in rel.get("assets", []) if re.match(asset_pattern(), a["name"])), None)
    version = rel.get("tag_name", "").lstrip("v")
    small = next((a for a in rel.get("assets", []) if a["name"] == patch_name(version)), None)
    return {"version": version, "date": (rel.get("published_at") or "")[:10],
            "message": (rel.get("name") or rel.get("tag_name") or "").strip(), "notes": rel.get("body") or "",
            "url": rel.get("html_url"), "asset": _asset(asset),
            "patch": _asset(small)}           # solo lo que cambia desde la versión instalada (None si no se publicó)


def check_app():
    """Devuelve la version nueva si la hay (dict con date y message) o None."""
    cur = installed()
    if cur["kind"] == "store":
        return None
    if cur["kind"] == "frozen":
        new = latest_release()
        if new["asset"] and _vtuple(new["version"]) > _vtuple(__version__):
            new["message"] = "%s %s" % (APP_NAME, new["version"]) if not new["message"] else new["message"]
            return new
        return None
    new = latest()
    if cur.get("sha") and cur["sha"] != new["sha"]:
        if cur["kind"] == "git":
            # solo avisar si el commit remoto no esta ya en la copia local (p. ej. trabajo local sin subir)
            r = subprocess.run(["git", "-C", paths.APP_DIR, "cat-file", "-e", new["sha"] + "^{commit}"], capture_output=True, creationflags=NO_WINDOW)
            if r.returncode == 0:
                return None
        return new
    return None


def _spawn_script(lines):
    """Lanza un script de shell desacoplado que espera a que Jayth se cierre (macOS/Linux)."""
    sh = os.path.join(tempfile.gettempdir(), "jayth_update_%d.sh" % os.getpid())
    with open(sh, "w") as f:
        f.write("#!/bin/sh\nwhile kill -0 %d 2>/dev/null; do sleep 0.5; done\n" % os.getpid() + "\n".join(lines) + "\nrm -f \"$0\"\n")
    os.chmod(sh, 0o755)
    subprocess.Popen(["/bin/sh", sh], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------- actualización sin interrupciones (app empaquetada)
# 1) la versión nueva se descarga en segundo plano (se reanuda si se corta y se comprueba con SHA-256);
# 2) queda «lista» (updates/ready.json) y la barra lateral ofrece «Reiniciar para actualizar»;
# 3) se instala cuando el usuario quiera (reinicia Jayth) o, si no, sola al cerrar Jayth, sin volver a abrirlo.
UPD_DIR = os.path.join(paths.HOME, "updates")
READY = os.path.join(UPD_DIR, "ready.json")
LOCK = os.path.join(UPD_DIR, "installing.lock")          # existe mientras el instalador trabaja
REOPEN = os.path.join(UPD_DIR, "reopen.flag")            # alguien abrió Jayth durante la instalación: abrirlo al terminar
LOCK_MAX_AGE = 300                                       # un candado más viejo es de una instalación interrumpida


def can_update_in_background():
    """Solo la app empaquetada se actualiza con un paquete descargado (las copias de git o del instalador de código no)."""
    return installed()["kind"] == "frozen" and (osys.WIN or osys.MAC or bool(os.environ.get("APPIMAGE")))


def _read_ready():
    try:
        with open(READY, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def ready():
    """La actualización ya descargada y comprobada, lista para instalar (dict con version, path, date, message…), o None."""
    d = _read_ready()
    if not d or _vtuple(d.get("version")) <= _vtuple(__version__) or not os.path.isfile(d.get("path") or ""):
        return None
    if d.get("kind") == "patch" and not os.path.isfile(os.path.join(d.get("dir") or "", os.path.basename(sys.executable))):
        return None                           # la versión montada ya no está: se descargará de nuevo
    return d


def just_updated():
    """Si esta es la primera vez que se abre la versión instalada por la actualización, devuelve sus datos (una sola vez)
    y borra el paquete descargado. Si quedó un paquete viejo o ya instalado, también lo limpia."""
    d = _read_ready()
    if not d or _vtuple(d.get("version")) > _vtuple(__version__):
        return None
    clean()
    return d if _vtuple(d.get("version")) == _vtuple(__version__) else None


def clean():
    """Borra los paquetes descargados y el estado (no el candado de una instalación en marcha)."""
    if not os.path.isdir(UPD_DIR):
        return
    d = _read_ready()
    if d and d.get("kind") == "patch" and (d.get("dir") or "").endswith(NEW_SUFFIX):
        shutil.rmtree(d["dir"], ignore_errors=True)        # la versión montada junto a la instalada
    for f in os.listdir(UPD_DIR):
        p = os.path.join(UPD_DIR, f)
        if p not in (LOCK, NO_PATCH, RESULT) and f != "rescate.ps1" and os.path.isfile(p):     # (el estado de los paquetes de cambios se conserva)
            try:
                os.remove(p)
            except OSError:
                pass


def download_update(info, progress=None, stop=None):
    """Descarga el paquete de la versión nueva en segundo plano y la deja lista. Devuelve el dict de ready()."""
    a = info.get("asset")
    if not a:
        raise RuntimeError(tr("No hay un paquete de %s para este sistema en la última versión.") % APP_NAME)
    old = _read_ready()
    if old and old.get("version") != info["version"]:     # había otra versión a medias: fuera
        clean()
    d = None
    if info.get("patch") and patch_allowed(info["version"]):
        try:                                   # primero, solo lo que cambia (unos MB en vez del instalador entero)
            d = _prepare_patch(info, progress, stop)
        except Cancelled:
            raise
        except Exception as e:                 # cualquier duda: el instalador completo de siempre
            _note_patch("failed", info["version"], "%s: %s" % (type(e).__name__, e))
            shutil.rmtree(paths.APP_DIR + NEW_SUFFIX, ignore_errors=True)
            d = None
    if d is None:
        dest = os.path.join(UPD_DIR, a["name"])
        download(a["url"], dest, a["size"], a["sha256"], progress, stop)
        d = {"version": info["version"], "path": dest, "date": info.get("date", ""), "message": info.get("message", ""),
             "notes": info.get("notes", ""), "url": info.get("url", "")}
    tmp = READY + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, READY)
    return d


# ventanita propia con los colores de Jayth mientras se actualiza (solo si después se reabre)
_UPDATING_WINDOW = """
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$f = New-Object System.Windows.Forms.Form
$f.FormBorderStyle = 'None'; $f.StartPosition = 'CenterScreen'; $f.Size = New-Object System.Drawing.Size(460, 132)
$f.BackColor = [System.Drawing.Color]::FromArgb(20, 23, 22); $f.TopMost = $true; $f.ShowInTaskbar = $true; $f.Text = 'Jayth'
$t = New-Object System.Windows.Forms.Label; $t.Text = %s; $t.ForeColor = [System.Drawing.Color]::FromArgb(235, 242, 240)
$t.Font = New-Object System.Drawing.Font('Segoe UI', 12, [System.Drawing.FontStyle]::Bold); $t.AutoSize = $false
$t.SetBounds(24, 20, 412, 28); $f.Controls.Add($t)
$s = New-Object System.Windows.Forms.Label; $s.Text = %s; $s.ForeColor = [System.Drawing.Color]::FromArgb(151, 166, 158)
$s.Font = New-Object System.Drawing.Font('Segoe UI', 9); $s.AutoSize = $false; $s.SetBounds(24, 50, 412, 36); $f.Controls.Add($s)
$b = New-Object System.Windows.Forms.ProgressBar; $b.Style = 'Marquee'; $b.MarqueeAnimationSpeed = 25; $b.SetBounds(24, 96, 412, 8)
$f.Controls.Add($b)
$f.Show(); [System.Windows.Forms.Application]::DoEvents()
"""


# ---------------------------------------------------------------- actualización con solo los cambios (jayth/parches.py)
PATCH_PLATFORM = "windows-x64"
NEW_SUFFIX, OLD_SUFFIX, BAD_SUFFIX = ".nuevo", ".anterior", ".fallida"       # carpetas junto a la instalada
RESULT = os.path.join(UPD_DIR, "parche_resultado.json")      # cómo acabó el último intercambio de carpetas
NO_PATCH = os.path.join(UPD_DIR, "sin_parche.json")          # versiones para las que ya falló: instalador completo
UNINSTALL_KEY = r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{8E5B2C61-4D7A-4F0E-9C3B-6A1D2F7E9B40}_is1"


def patch_supported():
    """¿Esta instalación puede actualizarse con un paquete de cambios? (Windows instalado; el portátil, macOS y Linux
    siguen con el paquete completo.)"""
    if not (osys.FROZEN and osys.WIN):
        return False
    app = paths.APP_DIR
    if os.path.exists(os.path.join(app, "portable.txt")) or os.path.isdir(os.path.join(app, "userdata")):
        return False
    return os.access(os.path.dirname(app), os.W_OK)


def _no_patch():
    try:
        with open(NO_PATCH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _note_patch(state, version, why=""):
    """Anota que el paquete de cambios de `version` no sirvió aquí: la próxima vez, el instalador completo."""
    try:
        os.makedirs(UPD_DIR, exist_ok=True)
        d = _no_patch()
        d[str(version)] = {"state": state, "why": str(why)[:300], "time": time.time()}
        with open(NO_PATCH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def patch_allowed(version):
    return patch_supported() and str(version) not in _no_patch()


def _prepare_patch(info, progress=None, stop=None):
    """Descarga el paquete de cambios y monta la versión nueva, completa y comprobada, junto a la instalada."""
    from . import parches
    p = info["patch"]
    if not p.get("sha256"):
        raise parches.PatchError("el paquete no trae huella con la que comprobarlo")
    dest = os.path.join(UPD_DIR, p["name"])
    download(p["url"], dest, p["size"], p["sha256"], progress, stop)
    new_dir = paths.APP_DIR + NEW_SUFFIX
    parches.stage(paths.APP_DIR, dest, new_dir, __version__, progress, stop)
    if not os.path.isfile(os.path.join(new_dir, os.path.basename(sys.executable))):
        raise parches.PatchError("la versión montada no tiene el programa")
    return {"version": info["version"], "path": dest, "dir": new_dir, "kind": "patch", "date": info.get("date", ""),
            "message": info.get("message", ""), "notes": info.get("notes", ""), "url": info.get("url", "")}


def patch_result():
    """Cómo acabó el último intercambio de carpetas (una sola vez): None, o {state: ok|locked|failed|bad, version, why}.
    Si no salió bien, deja anotado que esa versión se instale con el paquete completo. También recoge carpetas sobrantes."""
    try:
        with open(RESULT, encoding="utf-8-sig") as f:
            r = json.load(f)
    except (OSError, ValueError):
        r = None
    try:
        os.remove(RESULT)
    except OSError:
        pass
    if r and r.get("state") != "ok":
        _note_patch(r.get("state") or "failed", r.get("version"), r.get("why") or "")
        if os.path.isfile(READY):
            try:
                os.remove(READY)                    # lo preparado no llegó a instalarse: se descargará el completo
            except OSError:
                pass
    if osys.FROZEN and osys.WIN:
        keep = (_read_ready() or {}).get("dir")
        for suffix in (OLD_SUFFIX, BAD_SUFFIX, NEW_SUFFIX):
            d = paths.APP_DIR + suffix
            if os.path.isdir(d) and d != keep:
                shutil.rmtree(d, ignore_errors=True)
    return r


def verify_install(expected):
    """«Jayth --verify-install X»: lo ejecuta el intercambio de carpetas sobre la versión recién colocada, antes de
    borrar la anterior. Carga el programa entero sin abrir ventanas; código 0 solo si es la versión esperada y carga."""
    try:
        if expected and str(expected) != __version__:
            return 3
        import importlib
        for m in ("PySide6.QtWidgets", "PySide6.QtNetwork", "jayth.core", "jayth.agent", "jayth.tools", "jayth.desktop"):
            importlib.import_module(m)
        from . import i18n
        for f in (paths.ICON, os.path.join(paths.ASSETS, "i18n", "en.json")):
            if not os.path.isfile(f):
                return 4
        return 0
    except BaseException:
        return 5


def _swap_when_closed(d, reopen):
    """Windows: al cerrarse Jayth, intercambia la carpeta instalada por la versión nueva ya montada y comprobada.
    Dos cambios de nombre; la anterior se conserva hasta que la nueva demuestra que arranca; si no, vuelve la anterior."""
    pid = os.getpid()
    os.makedirs(UPD_DIR, exist_ok=True)
    app, new = paths.APP_DIR, d["dir"]
    exe = os.path.basename(sys.executable)
    # última comprobación, justo antes de instalar: la carpeta montada sigue siendo exactamente la versión nueva
    # (desde que se montó pudo pasar tiempo) y se anota qué programa hay instalado ahora, para no cambiar otro distinto
    from . import parches
    try:
        diff = parches.verify_dir(new, parches.read_patch(d["path"])["archivos"])
        stamp = parches.sha256(os.path.join(app, exe))
    except Exception as e:
        diff, stamp = "%s: %s" % (type(e).__name__, e), ""
    if diff:
        _note_patch("failed", d["version"], "al instalar: " + diff)
        shutil.rmtree(new, ignore_errors=True)
        try:
            os.remove(READY)
        except OSError:
            pass
        return False
    title = tr("Actualizando %s a la versión %s…") % (APP_NAME, d["version"])
    sub = tr("Se abrirá solo en unos segundos. Tus conversaciones, ajustes y modelos se conservan.")
    rescue = os.path.join(UPD_DIR, "rescate.ps1")
    with open(rescue, "w", encoding="utf-8-sig") as f:      # si el equipo se apaga justo entre los dos cambios de nombre
        f.write("""$app = %(app)s; $old = %(old)s
if (-not (Test-Path (Join-Path $app %(exe)s)) -and (Test-Path (Join-Path $old %(exe)s))) {
  if (Test-Path $app) { Rename-Item -Force $app ((Split-Path $app -Leaf) + '.rota') }
  [System.IO.Directory]::Move($old, $app)
}
""" % {"app": _ps(app), "old": _ps(app + OLD_SUFFIX), "exe": _ps(exe)})
    win = _UPDATING_WINDOW % (_ps(title), _ps(sub)) if reopen else "$f = $null\n"
    script = """$ErrorActionPreference = 'SilentlyContinue'
Wait-Process -Id %(pid)d -Timeout 120
New-Item -ItemType File -Force -Path %(lock)s | Out-Null
%(win)s
$app = %(app)s; $new = %(new)s; $old = %(old)s; $bad = %(bad)s; $exe = %(exe)s; $ver = %(ver)s; $res = %(res)s
function Touch { if ($f) { [System.Windows.Forms.Application]::DoEvents() }; (Get-Item %(lock)s).LastWriteTime = Get-Date }
function Result($state, $why) {
  @{ state = $state; version = $ver; why = $why } | ConvertTo-Json | Set-Content -Encoding UTF8 -Path $res
}
function Move-Dir($from, $to, $tries) {
  for ($i = 0; $i -lt $tries; $i++) {
    try { [System.IO.Directory]::Move($from, $to); return $true } catch { Start-Sleep -Milliseconds 250; Touch }
  }
  return $false
}
$now = (Get-FileHash -Algorithm SHA256 -Path (Join-Path $app $exe)).Hash
if (-not (Test-Path (Join-Path $new $exe))) { Result 'failed' 'no esta la version nueva montada' }
elseif ($now -ne %(stamp)s) { Result 'changed' 'la instalacion cambio mientras tanto (otro instalador)'; Remove-Item -Recurse -Force $new }
else {
  Remove-Item -Recurse -Force $old, $bad
  $run = 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce'
  Set-ItemProperty -Path $run -Name 'JaythRescate' -Value ('powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + %(rescue)s + '"')
  if (-not (Move-Dir $app $old 60)) {
    Result 'locked' 'otro programa tiene abierta la carpeta de Jayth'
    Remove-Item -Recurse -Force $new
  } elseif (-not (Move-Dir $new $app 20)) {
    [void](Move-Dir $old $app 40)
    Result 'failed' 'no se pudo colocar la version nueva'
    Remove-Item -Recurse -Force $new
  } else {
    # la version nueva tiene que arrancar antes de dar el cambio por bueno
    $code = -1
    try {
      $psi = New-Object System.Diagnostics.ProcessStartInfo
      $psi.FileName = (Join-Path $app $exe); $psi.Arguments = %(check)s; $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
      $p = [System.Diagnostics.Process]::Start($psi)
      $t0 = Get-Date
      while (-not $p.WaitForExit(150)) { Touch; if (((Get-Date) - $t0).TotalSeconds -gt %(wait)d) { $p.Kill(); break } }
      if ($p.HasExited) { $code = $p.ExitCode }
    } catch { $code = -2 }
    if ($code -ne 0) {
      Start-Sleep -Milliseconds 400
      if ((Move-Dir $app $bad 40) -and (Move-Dir $old $app 40)) { Remove-Item -Recurse -Force $bad }
      Result 'bad' ('la version nueva no arranco (codigo ' + $code + ')')
    } else {
      Set-ItemProperty -Path %(reg)s -Name 'DisplayVersion' -Value $ver
      Set-ItemProperty -Path %(reg)s -Name 'DisplayName' -Value (%(name)s + ' ' + $ver)
      Remove-Item -Recurse -Force $old
      Result 'ok' ''
    }
  }
  if (Test-Path (Join-Path $app $exe)) { Remove-ItemProperty -Path $run -Name 'JaythRescate' }
}
if ($f) { $f.Close() }
Remove-Item -Force %(lock)s
$open = %(reopened)s
if (Test-Path %(reopen)s) { Remove-Item -Force %(reopen)s; $open = $true }
if ($open) { Start-Process -FilePath (Join-Path $app $exe) }
Remove-Item -Force $MyInvocation.MyCommand.Path
""" % {"pid": pid, "lock": _ps(LOCK), "win": win, "app": _ps(app), "new": _ps(new), "old": _ps(app + OLD_SUFFIX),
       "bad": _ps(app + BAD_SUFFIX), "exe": _ps(exe), "ver": _ps(d["version"]), "res": _ps(RESULT), "rescue": _ps(rescue), "stamp": _ps(stamp.upper()),
       "check": _ps(" ".join(CHECK_ARGS) + " " + d["version"]), "wait": CHECK_WAIT, "reg": _ps(UNINSTALL_KEY), "name": _ps(APP_NAME),
       "reopen": _ps(REOPEN), "reopened": "$true" if reopen else "$false"}
    ps1 = os.path.join(UPD_DIR, "intercambiar_%d.ps1" % pid)
    with open(ps1, "w", encoding="utf-8-sig") as f:
        f.write(script)
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", ps1],
                     creationflags=NO_WINDOW | 0x00000200, close_fds=True, cwd=UPD_DIR)
    return ps1


CHECK_ARGS = ["--verify-install"]        # (las pruebas lo cambian para simular una versión que no arranca)
CHECK_WAIT = 120                         # segundos que se le dan a la versión nueva para responder


def installing():
    """¿Hay una instalación de una actualización en marcha ahora mismo?"""
    try:
        return time.time() - os.path.getmtime(LOCK) < LOCK_MAX_AGE
    except OSError:
        return False


def _ps(s):
    return "'" + str(s).replace("'", "''") + "'"


def install_when_closed(d, reopen):
    """Prepara la instalación de la versión «d»: empieza en cuanto este proceso se cierre.
    reopen=True: el usuario pidió actualizar ahora (se ve una ventanita «Actualizando…» y Jayth se vuelve a abrir).
    reopen=False: actualización al cerrar Jayth, en silencio; solo se reabre si alguien lo abre mientras tanto."""
    pid, pkg = os.getpid(), d["path"]
    os.makedirs(UPD_DIR, exist_ok=True)
    if osys.WIN and d.get("kind") == "patch":
        return _swap_when_closed(d, reopen)      # False: la versión montada ya no era válida y no se instala nada ahora
    if osys.WIN:
        app_exe = sys.executable
        title = tr("Actualizando %s a la versión %s…") % (APP_NAME, d["version"])
        sub = tr("Se abrirá solo en unos segundos. Tus conversaciones, ajustes y modelos se conservan.")
        args = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"] + (["/RELAUNCH=1"] if reopen else [])
        # ventanita propia con los colores de Jayth en lugar del asistente del instalador (solo si se reabre)
        win = _UPDATING_WINDOW % (_ps(title), _ps(sub)) if reopen else "$f = $null\n"
        script = """$ErrorActionPreference = 'SilentlyContinue'
Wait-Process -Id %(pid)d -Timeout 120
New-Item -ItemType File -Force -Path %(lock)s | Out-Null
%(win)s
$p = Start-Process -FilePath %(pkg)s -ArgumentList %(args)s -PassThru
while (-not $p.HasExited) {
  if ($f) { [System.Windows.Forms.Application]::DoEvents() }
  (Get-Item %(lock)s).LastWriteTime = Get-Date
  Start-Sleep -Milliseconds 100
}
if ($f) { $f.Close() }
Remove-Item -Force %(lock)s
if (Test-Path %(reopen)s) { Remove-Item -Force %(reopen)s; if (-not %(reopened)s) { Start-Process -FilePath %(app)s } }
Remove-Item -Force $MyInvocation.MyCommand.Path
""" % {"pid": pid, "lock": _ps(LOCK), "win": win, "pkg": _ps(pkg), "args": ",".join(_ps(a) for a in args),
       "reopen": _ps(REOPEN), "reopened": "$true" if reopen else "$false", "app": _ps(app_exe)}
        ps1 = os.path.join(UPD_DIR, "instalar_%d.ps1" % pid)
        with open(ps1, "w", encoding="utf-8-sig") as f:          # con BOM: PowerShell 5 lee bien los acentos
            f.write(script)
        # sin consola y en su propio grupo de procesos: sigue vivo cuando Jayth se cierra (con DETACHED_PROCESS PowerShell no arranca)
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", ps1],
                         creationflags=NO_WINDOW | 0x00000200, close_fds=True)
        return
    q = shlex.quote
    if osys.MAC:
        app = paths.APP_DIR if paths.APP_DIR.endswith(".app") else "/Applications/Jayth.app"
        mnt = os.path.join(tempfile.gettempdir(), "jayth_update_mnt")
        steps = ["hdiutil attach -nobrowse -quiet -mountpoint %s %s || exit 1" % (q(mnt), q(pkg)),
                 "rm -rf %s.old; mv %s %s.old && ditto %s/Jayth.app %s && rm -rf %s.old || mv %s.old %s" % (
                     q(app), q(app), q(app), q(mnt), q(app), q(app), q(app), q(app)),
                 "hdiutil detach -quiet %s" % q(mnt)]
        start = "open %s" % q(app)
    else:
        appimage = os.environ.get("APPIMAGE")
        os.chmod(pkg, 0o755)
        steps = ["cp -f %s %s.new && mv -f %s.new %s" % (q(pkg), q(appimage), q(appimage), q(appimage)), "chmod +x %s" % q(appimage)]
        start = "nohup %s >/dev/null 2>&1 &" % q(appimage)
    lines = ["mkdir -p %s; touch %s" % (q(UPD_DIR), q(LOCK))] + steps + ["rm -f %s" % q(LOCK)]
    lines.append(start if reopen else "[ -f %s ] && { rm -f %s; %s; }" % (q(REOPEN), q(REOPEN), start))
    _spawn_script(lines)


def apply_update(info=None, progress=None, stop=None):
    """Instala la version nueva. Devuelve (ok, como): como = "restart" (hay que relanzar), "installer" (el instalador
    reabre Jayth al cerrarlo) o el mensaje de error. Para la app empaquetada descarga el paquete si aún no lo está."""
    cur = installed()
    if cur["kind"] == "frozen":
        info = info or check_app()
        if not info or not info.get("asset"):
            return False, tr("No hay un paquete de %s para este sistema en la última versión.") % APP_NAME
        if not can_update_in_background():
            a = info["asset"]
            dest = os.path.join(UPD_DIR, a["name"])
            download(a["url"], dest, a["size"], a["sha256"], progress, stop)
            return False, tr("Descargado en %s. Sustituye tu AppImage por este archivo.") % dest
        d = ready() or download_update(info, progress, stop)
        install_when_closed(d, reopen=True)
        return True, "installer"
    if cur["kind"] == "git":
        r = subprocess.run(["git", "-C", paths.APP_DIR, "pull", "--ff-only"], capture_output=True, text=True, creationflags=NO_WINDOW)
        if r.returncode != 0:
            return False, tr("No se pudo actualizar con git:\n%s") % (r.stderr or r.stdout)[-800:]
        py = sys.executable.replace("pythonw.exe", "python.exe")
        subprocess.run([py, "-m", "pip", "install", "-q", "-r", os.path.join(paths.APP_DIR, "requirements.txt")],
                       capture_output=True, creationflags=NO_WINDOW)
        return True, "restart"
    if not osys.WIN:
        return False, tr("Descarga la última versión desde https://github.com/%s/releases") % REPO
    # instalada con el instalador: se vuelve a ejecutar (descarga el codigo nuevo, conserva .venv y datos) y abre Jayth al terminar
    cmd = "$env:JAYTH_REPO='%s'; irm https://raw.githubusercontent.com/%s/main/install.ps1 | iex" % (REPO, REPO)
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd], creationflags=NO_WINDOW | 0x00000200)
    return True, "installer"


def restart():
    argv = osys.launch_argv()
    subprocess.Popen(argv, cwd=paths.APP_DIR, **({"creationflags": DETACHED} if osys.WIN else {"start_new_session": True}))


# ---------------------------------------------------------------- modelos
_VER = re.compile(r"^([A-Za-z]+)\s?(\d+(?:\.\d+)*)")
_SIZE = re.compile(r"\b(\d+(?:\.\d+)?[BM])\b")


def parse(title):
    """'Qwen3.8 27B Coder' -> ('qwen', (3, 8), '27B', 'coder')."""
    m = _VER.match(title)
    if not m:
        return None
    fam, ver = m.group(1).lower(), tuple(int(x) for x in m.group(2).split("."))
    rest = title[m.end():]
    size = _SIZE.search(rest)
    variant = " ".join(w.lower() for w in _SIZE.sub("", rest).split() if not re.fullmatch(r"\d{4}", w))   # sin fechas tipo 2507
    return fam, ver, size.group(1) if size else "", variant


def check_models(models, seen=()):
    """Busca en Hugging Face versiones mas nuevas de la misma familia, tamaño y variante que tus modelos.
    Devuelve [{repo, title, for}] sin repetir avisos ya vistos."""
    news, done = [], set()
    for m in models:
        repo = m.get("repo") or ""
        if "/" not in repo:
            continue
        mine = parse(pretty_name(repo))
        if not mine:
            continue
        author = repo.split("/")[0]
        key = (author, mine[0])
        if key in done:
            continue
        done.add(key)
        try:
            found = get_json("https://huggingface.co/api/models?author=%s&search=%s&sort=createdAt&direction=-1&limit=60" % (author, mine[0]), timeout=15)
        except Exception:
            continue
        for it in found:
            rid = it.get("id") or it.get("modelId") or ""
            if not rid.lower().endswith("-gguf") or rid in seen:
                continue
            other = parse(pretty_name(rid))
            if other and other[0] == mine[0] and other[1] > mine[1] and other[2] == mine[2] and other[3] == mine[3]:
                news.append({"repo": rid, "title": pretty_name(rid), "for": pretty_name(repo)})
    news.sort(key=lambda n: parse(n["title"])[1], reverse=True)
    return news[:3]
