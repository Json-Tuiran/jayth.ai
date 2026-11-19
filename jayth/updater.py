"""Novedades: versiones nuevas de Jayth (GitHub) y de los modelos instalados (Hugging Face)."""
import os, re, sys, json, time, subprocess, urllib.request
from . import paths, APP_NAME
from .provision import pretty_name, get_json

REPO = "Json-Tuiran/jayth.ai"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


# ---------------------------------------------------------------- Jayth
def installed():
    """Version instalada: commit de git (copia clonada) o installed.json (instalada con el instalador)."""
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


def check_app():
    """Devuelve la version nueva si la hay (dict) o None."""
    cur, new = installed(), latest()
    if cur.get("sha") and cur["sha"] != new["sha"]:
        if cur["kind"] == "git":
            # solo avisar si el commit remoto no esta ya en la copia local (p. ej. trabajo local sin subir)
            r = subprocess.run(["git", "-C", paths.APP_DIR, "cat-file", "-e", new["sha"] + "^{commit}"], capture_output=True, creationflags=NO_WINDOW)
            if r.returncode == 0:
                return None
        return new
    return None


def apply_update():
    """Instala la version nueva. Devuelve (ok, mensaje). Tras ok hay que reiniciar Jayth."""
    cur = installed()
    py = sys.executable
    if cur["kind"] == "git":
        r = subprocess.run(["git", "-C", paths.APP_DIR, "pull", "--ff-only"], capture_output=True, text=True, creationflags=NO_WINDOW)
        if r.returncode != 0:
            return False, "No se pudo actualizar con git:\n" + (r.stderr or r.stdout)[-800:]
        subprocess.run([py.replace("pythonw.exe", "python.exe"), "-m", "pip", "install", "-q", "-r", os.path.join(paths.APP_DIR, "requirements.txt")],
                       capture_output=True, creationflags=NO_WINDOW)
        return True, "restart"
    # instalada con el instalador: se vuelve a ejecutar (descarga el codigo nuevo, conserva .venv y datos) y abre Jayth al terminar
    cmd = "$env:JAYTH_REPO='%s'; irm https://raw.githubusercontent.com/%s/main/install.ps1 | iex" % (REPO, REPO)
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd], creationflags=0x00000008 | NO_WINDOW)  # DETACHED
    return True, "installer"


def restart():
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    subprocess.Popen([exe, os.path.join(paths.APP_DIR, "app.py")], cwd=paths.APP_DIR, creationflags=0x00000008)


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
