# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Jayth - aplicacion de escritorio. Desde el codigo: pythonw app.py (Windows) o python3 app.py (macOS/Linux)."""
import os, sys

if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# HTTPS fiable en cualquier equipo: certificados de certifi si el sistema no indica otros
if not os.environ.get("SSL_CERT_FILE"):
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
    except ImportError:
        pass


def _updating():
    """Si ahora mismo se instala una actualización, no se abre a medias: avisa y el instalador abre Jayth al terminar."""
    from jayth import updater
    if not updater.installing():
        return False
    try:
        open(updater.REOPEN, "w").close()
    except OSError:
        pass
    from jayth.i18n import tr
    msg = tr("%s se está actualizando y se abrirá solo en unos segundos.") % "Jayth"
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "Jayth", 0x40)
    else:
        print(msg)
    return True


if __name__ == "__main__":
    if "--verify-install" in sys.argv:
        # lo ejecuta la actualización sobre la versión recién colocada, antes de borrar la anterior: carga el programa
        # entero sin abrir ventanas y contesta con un código (0 = es la versión esperada y arranca)
        from jayth import updater
        i = sys.argv.index("--verify-install")
        sys.exit(updater.verify_install(sys.argv[i + 1] if len(sys.argv) > i + 1 else ""))
    if "--selftest" not in sys.argv and _updating():
        sys.exit(0)
    from jayth.desktop import main
    main()
