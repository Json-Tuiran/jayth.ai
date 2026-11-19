"""Rutas de la aplicacion. Nada depende de una unidad o carpeta concreta de un equipo.

- Codigo: la carpeta donde este instalado el programa (APP_DIR).
- Datos de usuario (ajustes, conversaciones, modelos, llama.cpp): %LOCALAPPDATA%\\AgenteLocal
  * Modo portatil: si existe APP_DIR\\portable.txt, todo se guarda en APP_DIR\\userdata (util para un USB).
  * AGENTELOCAL_HOME permite forzar otra carpeta (se usa en pruebas).
- Carpeta de trabajo del agente por defecto: Documentos\\AgenteLocal
"""
import os

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _home():
    if os.environ.get("AGENTELOCAL_HOME"):
        return os.environ["AGENTELOCAL_HOME"]
    if os.path.exists(os.path.join(APP_DIR, "portable.txt")):
        return os.path.join(APP_DIR, "userdata")
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "AgenteLocal")


def _documents():
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:   # CSIDL_PERSONAL
                return buf.value
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


HOME = _home()
DATA = os.path.join(HOME, "data")
SESS_DIR = os.path.join(DATA, "sessions")
IMG_DIR = os.path.join(DATA, "images")
RUNTIME_DIR = os.path.join(HOME, "runtime")      # llama.cpp descargado
MODELS_DEFAULT = os.path.join(HOME, "models")
WORKSPACE_DEFAULT = os.path.join(_documents(), "AgenteLocal")
ICON = os.path.join(APP_DIR, "assets", "icon.ico")
WEB_DIR = os.path.join(APP_DIR, "web")


def ensure():
    for d in (DATA, SESS_DIR, IMG_DIR, RUNTIME_DIR):
        os.makedirs(d, exist_ok=True)
