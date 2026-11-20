# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Novedades: versiones nuevas de Jayth (GitHub) y de los modelos instalados (Hugging Face).

Tres formas de instalacion:
- "frozen": la app empaquetada (instalador .exe, .dmg o AppImage). Se actualiza desde GitHub Releases.
- "git": una copia clonada del repositorio. Se actualiza con git pull.
- "zip": instalada desde el codigo con install.ps1. Se vuelve a ejecutar el instalador.
"""
import os, re, sys, json, time, shlex, platform, tempfile, subprocess, urllib.request
from . import paths, osys, APP_NAME, __version__
from .provision import pretty_name, get_json, download
from .i18n import tr

REPO = "Json-Tuiran/jayth.ai"
NO_WINDOW = osys.NO_WINDOW
DETACHED = 0x00000008 if osys.WIN else 0


# ---------------------------------------------------------------- Jayth
def installed():
    """Version instalada: empaquetada, commit de git (copia clonada) o installed.json (instalador desde el codigo)."""
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


def latest_release():
    rel = get_json("https://api.github.com/repos/%s/releases/latest" % REPO, timeout=12)
    asset = next((a for a in rel.get("assets", []) if re.match(asset_pattern(), a["name"])), None)
    dig = (asset or {}).get("digest") or ""
    return {"version": rel.get("tag_name", "").lstrip("v"), "date": (rel.get("published_at") or "")[:10],
            "message": (rel.get("name") or rel.get("tag_name") or "").strip(), "notes": rel.get("body") or "",
            "url": rel.get("html_url"),
            "asset": {"name": asset["name"], "url": asset["browser_download_url"], "size": asset["size"],
                      "sha256": dig.split(":", 1)[1] if dig.startswith("sha256:") else ""} if asset else None}


def check_app():
    """Devuelve la version nueva si la hay (dict con date y message) o None."""
    cur = installed()
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
    for f in os.listdir(UPD_DIR):
        p = os.path.join(UPD_DIR, f)
        if p != LOCK and os.path.isfile(p):
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
    dest = os.path.join(UPD_DIR, a["name"])
    download(a["url"], dest, a["size"], a["sha256"], progress, stop)
    d = {"version": info["version"], "path": dest, "date": info.get("date", ""), "message": info.get("message", ""),
         "notes": info.get("notes", ""), "url": info.get("url", "")}
    tmp = READY + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, READY)
    return d


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
    if osys.WIN:
        app_exe = sys.executable
        title = tr("Actualizando %s a la versión %s…") % (APP_NAME, d["version"])
        sub = tr("Se abrirá solo en unos segundos. Tus conversaciones, ajustes y modelos se conservan.")
        args = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"] + (["/RELAUNCH=1"] if reopen else [])
        # ventanita propia con los colores de Jayth en lugar del asistente del instalador (solo si se reabre)
        win = """
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
""" % (_ps(title), _ps(sub)) if reopen else "$f = $null\n"
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
