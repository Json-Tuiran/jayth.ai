"""Análisis de datos: ejecutar Python con pandas y matplotlib y recoger los gráficos que produzca.

El agente escribe un script; Jayth lo ejecuta en la carpeta de trabajo con un Python que tenga pandas y matplotlib:
  1) el entorno propio de Jayth (runtime/analysis), si ya está preparado;
  2) el Python del sistema, si ya trae esas bibliotecas;
  3) si no, prepara una sola vez un Python aislado con uv (no toca el sistema; ~250 MB).
Las figuras que el script deja abiertas (o muestra con plt.show()) se guardan como PNG y vuelven a la conversación.
"""
import os, sys, json, time, shutil, subprocess, tempfile, threading
from . import paths, osys

HOME = os.path.join(paths.RUNTIME_DIR, "analysis")
PACKAGES = ["pandas", "matplotlib", "openpyxl", "numpy"]
_PROBE = "import pandas, matplotlib, numpy"
_cache = {}

RUNNER = r'''
import os, sys, runpy
out = sys.argv[2]
os.environ.setdefault("MPLBACKEND", "Agg")
_n = [0]
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.figsize": (8, 4.5), "figure.dpi": 110, "axes.grid": True, "grid.alpha": 0.25,
                         "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
                         "axes.prop_cycle": matplotlib.cycler(color=["#2E8F62", "#3B82F6", "#F2A541", "#E05A3A", "#8B5CF6", "#14B8A6"])})

    def _guardar(*a, **k):
        for num in plt.get_fignums():
            fig = plt.figure(num)
            if not fig.get_axes():
                continue
            _n[0] += 1
            fig.savefig(os.path.join(out, "figura_%02d.png" % _n[0]), dpi=110, bbox_inches="tight", facecolor="white")
        plt.close("all")
    plt.show = _guardar
except ImportError:
    _guardar = lambda *a, **k: None
try:
    import pandas as pd
    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.max_rows", 60)
except ImportError:
    pass
try:
    sys.argv = [sys.argv[1]]
    runpy.run_path(sys.argv[0], run_name="__main__")
finally:
    _guardar()
'''


def env_python():
    return os.path.join(HOME, "env", "Scripts", "python.exe") if osys.WIN else os.path.join(HOME, "env", "bin", "python")


def _has_libs(py):
    if py not in _cache:
        try:
            r = subprocess.run([py, "-c", _PROBE], capture_output=True, timeout=60, **osys.popen_kwargs())
            _cache[py] = r.returncode == 0
        except Exception:
            _cache[py] = False
    return _cache[py]


def find_python():
    """Python con pandas y matplotlib ya disponible, o None."""
    if os.path.isfile(env_python()):
        return env_python()
    cands = []
    if not getattr(sys, "frozen", False):
        cands.append(sys.executable)
    for name in ("python", "python3", "py"):
        p = shutil.which(name)
        if p and "WindowsApps" not in p:        # el «python» de la Tienda de Windows es solo un acceso que abre la tienda
            cands.append(p)
    for py in cands:
        if _has_libs(py):
            return py
    return None


def ensure_env(progress=None, stop=None):
    """Prepara (una vez) el Python aislado de análisis con uv. Devuelve su ruta."""
    py = make_env(HOME, PACKAGES, progress, stop)
    _cache.pop(py, None)
    return py


def make_env(HOME, PACKAGES, progress=None, stop=None):
    """Crea en la carpeta HOME un Python aislado (uv) con los paquetes indicados. Lo usan el análisis y la voz."""
    from . import convert
    from .provision import download, extract_archive
    pr = progress or (lambda *a: None)
    os.makedirs(HOME, exist_ok=True)
    uv = os.path.join(HOME, osys.exe("uv"))
    shared = os.path.join(convert.TOOLS, osys.exe("uv"))
    if not os.path.isfile(uv) and os.path.isfile(shared):
        shutil.copy2(shared, uv)                 # el convertidor de modelos ya lo descargó
    if not os.path.isfile(uv):
        asset = convert._uv_asset()
        dl = os.path.join(HOME, "downloads", asset)
        download("https://github.com/astral-sh/uv/releases/latest/download/" + asset, dl, 0, "", lambda d, t, ph: pr(d, t, "uv: " + ph), stop)
        tmp = os.path.join(HOME, "uv_tmp")
        extract_archive(dl, tmp)
        found = next((os.path.join(r, f) for r, _, fs in os.walk(tmp) for f in fs if f == osys.exe("uv")), None)
        if not found:
            raise RuntimeError("El paquete de uv no contiene %s" % osys.exe("uv"))
        shutil.move(found, uv)
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(os.path.join(HOME, "downloads"), ignore_errors=True)
        if not osys.WIN:
            os.chmod(uv, 0o755)
    env = dict(os.environ, UV_PYTHON_INSTALL_DIR=os.path.join(HOME, "python"), UV_CACHE_DIR=os.path.join(HOME, "cache"), UV_NO_CONFIG="1")

    def run(cmd, label):
        r = subprocess.run(cmd, capture_output=True, env=env, **osys.popen_kwargs())
        if r.returncode != 0:
            raise RuntimeError("%s falló: %s" % (label, (r.stdout + r.stderr).decode("utf-8", "replace")[-600:]))
    py = os.path.join(HOME, "env", "Scripts", "python.exe") if osys.WIN else os.path.join(HOME, "env", "bin", "python")
    if not os.path.isfile(py):
        venv = [uv, "venv", "--python", "3.12", os.path.join(HOME, "env")]
        try:
            run(venv, "Preparar Python")
        except RuntimeError:                     # mismo tropiezo de uv en Windows que en el convertidor: el segundo intento funciona
            shutil.rmtree(os.path.join(HOME, "env"), ignore_errors=True)
            run(venv, "Preparar Python")
    pr(0, 0, "instalando " + ", ".join(PACKAGES))
    run([uv, "pip", "install", "--python", py] + list(PACKAGES), "Instalar " + ", ".join(PACKAGES))
    try:
        run([uv, "cache", "clean"], "limpiar")
    except RuntimeError:
        pass
    return py


def run_code(code, workdir, stop=None, timeout=120):
    """Ejecuta el script. Devuelve (salida, [png bytes], nota)."""
    note = ""
    py = find_python()
    if py is None:
        py = ensure_env(stop=stop)
        note = "[Se preparó el entorno de análisis de Jayth (pandas, matplotlib); las próximas veces será inmediato.]\n"
    tmp = tempfile.mkdtemp(prefix="jayth_an_")
    try:
        script, runner = os.path.join(tmp, "analisis.py"), os.path.join(tmp, "_ejecutar.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(code)
        with open(runner, "w", encoding="utf-8") as f:
            f.write(RUNNER)
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", MPLBACKEND="Agg", NO_COLOR="1")
        p = subprocess.Popen([py, runner, script, tmp], cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             env=env, **osys.popen_kwargs())
        chunks = []
        th = threading.Thread(target=lambda: chunks.append(p.stdout.read()), daemon=True)
        th.start()
        t0, why = time.time(), None
        while p.poll() is None:
            if stop is not None and stop.is_set():
                why = "cancelado por el usuario"
                break
            if time.time() - t0 > timeout:
                why = "tiempo agotado (%d s)" % timeout
                break
            time.sleep(0.1)
        if why:
            osys.kill_tree(p.pid)
        th.join(3)
        out = b"".join(c for c in chunks if c).decode("utf-8", "replace")
        out = out.replace(script, "analisis.py").replace(tmp + os.sep, "")
        # del error solo interesa la parte del script, no las líneas internas del lanzador
        if "Traceback (most recent call last)" in out:
            lines = out.splitlines()
            i = next((k for k, l in enumerate(lines) if l.startswith("Traceback")), 0)
            j = next((k for k in range(i, len(lines)) if 'File "analisis.py"' in lines[k]), None)
            if j is not None:
                out = "\n".join(lines[:i + 1] + lines[j:])
        figs = []
        for fn in sorted(os.listdir(tmp)):
            if fn.startswith("figura_") and fn.endswith(".png"):
                with open(os.path.join(tmp, fn), "rb") as f:
                    figs.append(f.read())
        status = "[Proceso terminado: %s]" % why if why else ("" if p.returncode == 0 else "[terminó con error, código %d]" % p.returncode)
        return out.strip(), figs, note, status, (p.returncode == 0 and not why)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
