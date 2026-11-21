# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Guía de Jayth para el propio agente (herramienta jayth_guide).

- assets/guia/<idioma>.md: qué hace cada parte de la app, dónde está cada botón, menú y ajuste, y cómo se hace cada
  cosa; una por idioma de la interfaz, para que el agente nombre los botones como los ve el usuario. Va dentro de cada
  versión, así que siempre describe la instalada (tools_i18n/revisar_guia.py comprueba que no se quede atrás).
- Datos en vivo de esta instalación, sacados del código y de los ajustes al consultar: versión, carpetas, modelo activo,
  atajos de teclado, modos de permiso y herramientas.
"""
import os, re, unicodedata
from . import paths, osys, i18n, __version__, APP_NAME
from .i18n import tr

MAX_CHARS = 7000
_STOP = set("""a al algo como con cual cuando de del donde dónde el en es esta este esto hay la las lo los me mi mis no o
para por que qué se si sin su sus te tu tus un una uno y ya the a an and are can do does for from how i in is it my of on
or the to what where with you your o os um uma uns com como da das de do dos e em é na nas no nos ou para por que se
sua seu jayth""".split())


def _norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _words(s):
    return [w for w in re.findall(r"[a-z0-9+]{3,}", _norm(s)) if w not in _STOP]


def guide_path(lang=None):
    for l in (lang or i18n.LANG, "es"):
        p = os.path.join(paths.ASSETS, "guia", l + ".md")
        if os.path.isfile(p):
            return p
    return None


def sections(lang=None):
    """[(título, texto)] de la guía, partida por los encabezados «## »."""
    p = guide_path(lang)
    if not p:
        return []
    with open(p, encoding="utf-8") as f:
        text = f.read()
    out = []
    for block in re.split(r"(?m)^## ", text)[1:]:
        title, _, body = block.partition("\n")
        out.append((title.strip(), body.strip()))
    return out


def search(topic, lang=None, top=3):
    """Las secciones que más se parecen al tema (título y texto; las del título pesan más)."""
    q = set(_words(topic))
    if not q:
        return []
    scored = []
    for title, body in sections(lang):
        tw, bw = _words(title), _words(body)
        score = 4 * sum(1 for w in q if any(t.startswith(w[:5]) for t in tw)) + sum(
            min(3, sum(1 for b in bw if b.startswith(w[:5]))) for w in q)
        if score:
            scored.append((score, title, body))
    scored.sort(key=lambda x: -x[0])
    return [(t, b) for s, t, b in scored[:top] if s >= scored[0][0] * 0.35]


def _images_line(cfg, yes, no):
    """«Imágenes: activadas · FLUX.2 [klein] 4B instalado · 512 px» (o lo que falte)."""
    try:
        from . import imagegen as IG
        if not IG.available():
            return tr("Imágenes: no disponibles en este sistema")
        m, st = IG.model(cfg), IG.status(cfg)
        return tr("Imágenes: permitidas %s · modelo %s (%s) · tamaño %d px · carpeta %s") % (
            yes if cfg.get("image_gen", True) else no, m["name"], tr("instalado") if st["ready"] else tr("sin instalar"),
            IG.base_side(cfg), cfg.get("image_dir") or tr("«%s» en la carpeta de trabajo") % tr("imagenes"))
    except Exception:
        return tr("Imágenes: —")


def live():
    """Datos de esta instalación, en el idioma de la interfaz (sacados de los ajustes y del código al consultar)."""
    from . import core, agent as A, tools as T
    cfg = core.SET.snapshot()
    yes, no = tr("sí"), tr("no")
    m = core.active_model(cfg)
    ext = cfg.get("llm_mode") == "external"
    model = (cfg.get("external_model") or cfg.get("external_url") or "—") if ext else (core.model_title(m) if m else tr("ninguno"))
    eff = core.effort_of(cfg)
    eff_label = next((l for k, l, d in core.EFFORTS if k == eff), eff)
    mode_label = A.MODES.get(cfg.get("mode"), cfg.get("mode") or "").split(":")[0]
    autosave = {"delay": tr("al hacer una pausa al escribir"), "focus": tr("al cambiar de pestaña o de ventana"),
                "off": tr("desactivado")}.get(cfg.get("editor_autosave", "delay"), "")
    models = [core.model_title(x) or x.get("name") for x in cfg.get("models") or []]
    mcp = [s.get("name") for s in cfg.get("mcp_servers") or [] if s.get("enabled", True)]
    lines = [
        "## " + tr("Datos de esta instalación (en vivo)"),
        "- " + tr("Versión de %s: %s · sistema: %s · idioma de la interfaz: %s") % (APP_NAME, __version__, osys.os_label(),
                                                                                  i18n.NAMES.get(i18n.LANG, i18n.LANG)),
        "- " + tr("Carpeta de datos (ajustes, conversaciones, motor): %s") % paths.HOME,
        "- " + tr("Carpeta de modelos: %s") % cfg.get("models_dir", ""),
        "- " + tr("Carpeta de trabajo del modo Chat: %s") % cfg.get("workspace", ""),
        "- " + tr("Modelo activo: %s (%s) · esfuerzo: %s") % (model, tr("servidor externo") if ext else tr("local"), eff_label),
        "- " + tr("Motor: llama.cpp %s · %s") % (cfg.get("llama_tag") or "—", cfg.get("backend") or "cpu"),
        "- " + tr("Memoria de la conversación (contexto): %d tokens (%s)") % (
            core.effective_ctx(cfg), tr("automático: lo que admite el modelo, ajustado a la memoria") if not int(cfg.get("n_ctx") or 0)
            else tr("fijado en Ajustes")),
        "- " + tr("Modelos instalados (%d): %s") % (len(models), ", ".join(models[:8]) or tr("ninguno")),
        "- " + tr("Permisos por defecto: %s · memoria: %s · internet: %s · control del ordenador: %s") % (
            mode_label, yes if cfg.get("memory_enabled", True) else no, yes if cfg.get("web_access", True) else no,
            yes if cfg.get("computer_control", True) else no),
        "- " + tr("Conectores MCP: %s") % (", ".join(mcp) or tr("ninguno")),
        "- " + _images_line(cfg, yes, no),
        "- " + tr("Actualizaciones: avisar %s · instalar al cerrar %s · autoguardado del editor: %s") % (
            yes if cfg.get("auto_update_check", True) else no, yes if cfg.get("auto_install_updates", True) else no, autosave),
    ]
    return "\n".join(lines)


def extras():
    """Listas que salen del propio código: atajos, modos de permiso y herramientas (siempre al día)."""
    from . import agent as A, tools as T
    out = []
    try:
        from .settings_ui import SHORTCUTS
        out.append("## " + tr("Atajos de teclado"))
        out += ["- %s: %s" % (k, d) for k, d in SHORTCUTS]
    except Exception:
        pass
    out.append("## " + tr("Modos de permiso"))
    out += ["- %s" % v for v in A.MODES.values()]
    out.append("## " + tr("Herramientas del agente"))
    out.append(", ".join(T.TOOL_LABELS[k] for k in T.TOOL_LABELS))
    return "\n".join(out)


def answer(topic=""):
    """Respuesta de la herramienta: secciones de la guía sobre el tema (o el índice) y los datos de esta instalación."""
    secs = sections()
    if not secs:
        return tr("No encuentro la guía de %s en esta instalación.") % APP_NAME + "\n\n" + live()
    topic = (topic or "").strip()
    found = search(topic) if topic else []
    parts = []
    if found:
        parts += ["## %s\n%s" % (t, b) for t, b in found]
    else:
        if topic:
            parts.append(tr("No hay una sección sobre «%s». Temas de la guía:") % topic)
        else:
            parts.append(tr("Temas de la guía de %s (pide uno con topic):") % APP_NAME)
        parts.append("\n".join("- " + t for t, _ in secs))
    parts.append(live())
    nt = _norm(topic)
    if not topic or any(w in nt for w in ("atajo", "teclado", "shortcut", "keyboard", "tecla", "permis", "modo", "mode",
                                          "herramient", "tool", "ferrament", "puede hacer", "can you do", "pode fazer")):
        parts.append(extras())
    text = "\n\n".join(parts)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n…"
    return text
