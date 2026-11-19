"""Rutas de la aplicacion. Nada depende de una unidad o carpeta concreta de un equipo.

- Codigo: la carpeta donde este instalado el programa (APP_DIR). Empaquetado, es la carpeta del ejecutable
  y los recursos (iconos, logo) viven en RES_DIR.
- Datos de usuario (ajustes, conversaciones, modelos, llama.cpp):
    Windows  %LOCALAPPDATA%\\Jayth
    macOS    ~/Library/Application Support/Jayth
    Linux    $XDG_DATA_HOME/jayth  (~/.local/share/jayth)
  * Modo portatil: si existe portable.txt junto al programa, todo se guarda en userdata/ (util para un USB).
  * JAYTH_HOME permite forzar otra carpeta (se usa en pruebas).
- Carpeta de trabajo del agente por defecto: Documentos/Jayth
"""
import os, sys
from . import osys

if osys.FROZEN:
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
    if osys.MAC and APP_DIR.endswith("/Contents/MacOS"):          # Jayth.app/Contents/MacOS -> el propio Jayth.app
        APP_DIR = os.path.dirname(os.path.dirname(APP_DIR))
    elif os.environ.get("APPIMAGE"):                              # AppImage: la carpeta donde esta el .AppImage
        APP_DIR = os.path.dirname(os.environ["APPIMAGE"])
    RES_DIR = getattr(sys, "_MEIPASS", APP_DIR)
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RES_DIR = APP_DIR


def _home():
    if os.environ.get("JAYTH_HOME"):
        return os.environ["JAYTH_HOME"]
    if os.path.exists(os.path.join(APP_DIR, "portable.txt")):
        return os.path.join(APP_DIR, "userdata")
    home = osys.data_home("Jayth")
    if osys.WIN:
        old = os.path.join(os.path.dirname(home), "AgenteLocal")   # nombre provisional anterior: migrar una sola vez
        if not os.path.exists(home) and os.path.isdir(old):
            try:
                os.rename(old, home)
            except OSError:
                return old                                          # en uso (p. ej. el motor encendido): seguir con la antigua
    return home


HOME = _home()
DATA = os.path.join(HOME, "data")
SESS_DIR = os.path.join(DATA, "sessions")
IMG_DIR = os.path.join(DATA, "images")
RUNTIME_DIR = os.path.join(HOME, "runtime")      # llama.cpp descargado
MODELS_DEFAULT = os.path.join(HOME, "models")
WORKSPACE_DEFAULT = os.path.join(osys.documents_dir(), "Jayth")
ASSETS = os.path.join(RES_DIR, "assets")
ICON = os.path.join(ASSETS, "icon.ico" if osys.WIN else "icon.png")
WEB_DIR = os.path.join(RES_DIR, "web")


def ensure():
    for d in (DATA, SESS_DIR, IMG_DIR, RUNTIME_DIR):
        os.makedirs(d, exist_ok=True)
