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

from jayth.desktop import main

if __name__ == "__main__":
    main()
