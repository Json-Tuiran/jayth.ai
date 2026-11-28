# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Jayth: espacio local para usar un modelo de lenguaje con herramientas, en tu propio equipo."""
__version__ = "0.9.6"
APP_NAME = "Jayth"
SITE = "https://json-tuiran.github.io/jayth.ai/"


def support_url(lang="es"):
    """Página con las formas de apoyar el proyecto (aportaciones, estrella, difundirlo), en español o en inglés."""
    return SITE + ("apoyar.html" if lang == "es" else "en/support.html")
