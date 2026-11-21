# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Servicios externos que el usuario puede conectar con su propia cuenta (conectores MCP remotos oficiales).

Todo es opcional: Jayth funciona en local y sin internet; un servicio solo se conecta si el usuario pulsa «Conectar» e
inicia sesión él mismo en la página del servicio (oauth.py). Las acciones que cambian algo en su cuenta (publicar,
enviar, gastar créditos) siempre piden su aprobación (agent.Run._needs_approval)."""
import threading
from . import core, boveda, oauth
from .i18n import tr

GOOGLE_GUIDE = "https://developers.google.com/workspace/guides/configure-mcp-servers"
GOOGLE_CLIENT = "google-oauth-client"           # clave en la bóveda del cliente OAuth que el usuario crea en Google Cloud
_G = "https://www.googleapis.com/auth/"

CATALOG = [
    {"id": "higgsfield", "name": "Higgsfield", "url": "https://mcp.higgsfield.ai/mcp", "color": "#D7F25C", "spends": True,
     "desc": tr("Imágenes y vídeo con IA en la nube, con tu cuenta y tus créditos de Higgsfield.")},
    {"id": "notion", "name": "Notion", "url": "https://mcp.notion.com/mcp", "color": "#EDEDED",
     "desc": tr("Busca, lee y edita tus páginas y bases de datos de Notion.")},
    {"id": "canva", "name": "Canva", "url": "https://mcp.canva.com/mcp", "color": "#7D2AE8",
     "desc": tr("Crea y edita diseños en tu cuenta de Canva.")},
    {"id": "gmail", "name": "Gmail", "url": "https://gmailmcp.googleapis.com/mcp/v1", "color": "#EA4335", "google": True,
     "scopes": _G + "gmail.readonly " + _G + "gmail.compose",
     "desc": tr("Lee, busca y redacta correos de tu Gmail; enviar uno siempre te lo pregunta.")},
    {"id": "drive", "name": "Google Drive", "url": "https://drivemcp.googleapis.com/mcp/v1", "color": "#1FA463", "google": True,
     "scopes": _G + "drive.readonly " + _G + "drive.file",
     "desc": tr("Busca y lee tus archivos de Drive y guarda en él los que cree el agente.")},
    {"id": "calendar", "name": "Google Calendar", "url": "https://calendarmcp.googleapis.com/mcp/v1", "color": "#4285F4", "google": True,
     "scopes": _G + "calendar.events " + _G + "calendar.calendarlist.readonly",
     "desc": tr("Consulta tu agenda y crea o cambia eventos.")},
    {"id": "linear", "name": "Linear", "url": "https://mcp.linear.app/mcp", "color": "#5E6AD2",
     "desc": tr("Consulta y gestiona incidencias y proyectos de Linear.")},
    {"id": "atlassian", "name": "Jira y Confluence", "url": "https://mcp.atlassian.com/v1/mcp", "color": "#2684FF",
     "desc": tr("Incidencias de Jira y páginas de Confluence de tu cuenta de Atlassian.")},
    {"id": "huggingface", "name": "Hugging Face", "url": "https://huggingface.co/mcp", "color": "#FFD21E", "login": False,
     "desc": tr("Busca modelos, conjuntos de datos, artículos y demos de Hugging Face (sin cuenta).")},
]


def find(cid):
    return next((c for c in CATALOG if c["id"] == cid), None)


def server_of(cid, cfg=None):
    """Ajustes del conector de ese servicio si ya está añadido."""
    c = find(cid)
    for s in (cfg or core.SET.snapshot()).get("mcp_servers") or []:
        if s.get("catalog") == cid or (c and oauth.canonical(s.get("url") or "") == oauth.canonical(c["url"])):
            return s
    return None


def connected(cid, cfg=None):
    """¿Está añadido, activo y (si pide cuenta) con la sesión iniciada?"""
    c, s = find(cid), server_of(cid, cfg)
    if not c or not s or not s.get("enabled", True):
        return False
    return not c.get("login", True) or oauth.signed_in(c["url"])


def google_client():
    return boveda.get(GOOGLE_CLIENT)


def set_google_client(client_id, client_secret):
    boveda.put(GOOGLE_CLIENT, {"client_id": client_id.strip(), "client_secret": client_secret.strip()})


def needs_setup(cid):
    """Lo que falta antes de poder conectar: 'google' (crear el cliente en Google Cloud) o ''."""
    c = find(cid)
    return "google" if c and c.get("google") and not google_client() else ""


def offered(cfg):
    """Servicios del catálogo que aún no están conectados (para que el agente los proponga si hacen falta)."""
    return [c for c in CATALOG if not connected(c["id"], cfg)]


def _add(c, cfg=None):
    servers = [dict(s) for s in (cfg or core.SET.snapshot()).get("mcp_servers") or [] if s.get("catalog") != c["id"]
               and oauth.canonical(s.get("url") or "") != oauth.canonical(c["url"])]
    entry = {"name": c["name"], "url": c["url"], "enabled": True, "catalog": c["id"]}
    if c.get("login", True):
        entry["auth"] = "oauth"
    servers.append(entry)
    core.SET.update({"mcp_servers": servers})
    return servers


JOBS = {}           # id del servicio -> {'state': 'navegador'|'conectando'|'listo'|'error', 'error': …, 'stop': Event}


def busy(cid):
    j = JOBS.get(cid)
    return bool(j and j["state"] in ("navegador", "conectando"))


def connect(cid, open_url=None, done=None):
    """Conecta el servicio en segundo plano: inicia sesión en el navegador del usuario (si pide cuenta), lo añade a los
    conectores y lo arranca. done(error o '') se llama al terminar (desde otro hilo)."""
    from . import harness
    c = find(cid)
    if busy(cid):
        return JOBS[cid]
    job = {"state": "navegador" if c.get("login", True) else "conectando", "error": "", "stop": threading.Event()}
    JOBS[cid] = job

    def run():
        try:
            if c.get("login", True):
                client = google_client() if c.get("google") else None
                if c.get("google") and not client:
                    raise oauth.OAuthError(tr("Primero configura tu cliente de Google (botón «Configurar Google…»)."))
                oauth.login(c["url"], client=client, open_url=open_url, stop=job["stop"], scopes=c.get("scopes"),
                            www_auth="" if c.get("google") else None)
            job["state"] = "conectando"
            servers = _add(c)
            st = harness.mcp_sync(servers)
            err = st.get(c["name"], "")
            job.update(state="error" if err else "listo", error=err)
        except oauth.Cancelled:
            job.update(state="error", error=tr("Cancelado."))
        except Exception as e:
            job.update(state="error", error=str(e) or type(e).__name__)
        if done:
            done(job["error"])
    threading.Thread(target=run, daemon=True).start()
    return job


def cancel(cid):
    j = JOBS.get(cid)
    if j:
        j["stop"].set()


def disconnect(cid):
    """Cierra la sesión en este equipo y quita el conector."""
    from . import harness
    c = find(cid)
    if c:
        oauth.logout(c["url"])
    servers = [dict(s) for s in core.SET.snapshot().get("mcp_servers") or [] if s.get("catalog") != cid and not
               (c and oauth.canonical(s.get("url") or "") == oauth.canonical(c["url"]))]
    core.SET.update({"mcp_servers": servers})
    JOBS.pop(cid, None)
    threading.Thread(target=lambda: harness.mcp_sync(servers), daemon=True).start()
