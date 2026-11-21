# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Iniciar sesión en servicios externos (conectores MCP remotos) con OAuth 2.1, como define el estándar MCP.

1. El conector responde 401 con «WWW-Authenticate: Bearer resource_metadata=…» (o se consulta
   /.well-known/oauth-protected-resource): así se sabe qué servidor de autorización usa y qué permisos pide.
2. Se leen los metadatos de ese servidor (RFC 8414 u OpenID) y Jayth se presenta como cliente: con el cliente que haya
   dado el usuario (p. ej. Google), con un documento de cliente publicado (CIMD) o por registro dinámico (RFC 7591).
3. Se abre el navegador del usuario en la página del propio servicio (PKCE S256, state y resource). El usuario inicia
   sesión allí y autoriza; el servicio vuelve a http://127.0.0.1:<puerto>/callback, donde Jayth escucha un momento.
4. Se canjea el código por los permisos (tokens), que se guardan cifrados en la bóveda y se renuevan solos.
Jayth nunca ve la contraseña del usuario."""
import os, re, json, time, base64, hashlib, secrets, threading, webbrowser
import urllib.request, urllib.parse, urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from . import APP_NAME, __version__, boveda
from .i18n import tr

UA = {"User-Agent": "%s/%s" % (APP_NAME, __version__), "Accept": "application/json"}
# documento de cliente (CIMD) de Jayth: se usará cuando esté publicado en una dirección https propia del proyecto
CLIENT_METADATA_URL = ""
REDIRECT_PATH = "/callback"


class OAuthError(RuntimeError):
    pass


class Cancelled(OAuthError):
    pass


def _key(url):
    return "mcp-oauth:" + canonical(url)


def canonical(url):
    """Dirección del recurso (RFC 8707): esquema y servidor en minúsculas, sin fragmento ni barra final."""
    u = urllib.parse.urlsplit(url.strip())
    path = u.path.rstrip("/") if u.path not in ("", "/") else ""
    return urllib.parse.urlunsplit((u.scheme.lower(), u.netloc.lower(), path, u.query, ""))


def _get_json(url, timeout=15):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(url, data, json_body=False, headers=None, timeout=20):
    h = dict(UA, **(headers or {}))
    if json_body:
        body = json.dumps(data).encode("utf-8")
        h["Content-Type"] = "application/json"
    else:
        body = urllib.parse.urlencode(data).encode("utf-8")
        h["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=h, method="POST"), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        txt = e.read(800).decode("utf-8", "replace")
        try:
            j = json.loads(txt)
            msg = j.get("error_description") or j.get("error") or txt
        except ValueError:
            msg = txt
        raise OAuthError("HTTP %d: %s" % (e.code, str(msg)[:300]))


def parse_www_authenticate(h):
    """{'resource_metadata': …, 'scope': …, 'error': …} de una cabecera «Bearer a="b", c="d"»."""
    out = {}
    for k, v1, v2 in re.findall(r'(\w+)\s*=\s*(?:"([^"]*)"|([^\s,]+))', h or ""):
        out[k.lower()] = v1 or v2
    return out


def probe(url, timeout=15):
    """Pregunta al conector sin permiso: devuelve la cabecera WWW-Authenticate si pide iniciar sesión (401), o None."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": APP_NAME, "version": __version__}}})
    req = urllib.request.Request(url, data=body.encode("utf-8"), method="POST",
                                 headers=dict(UA, **{"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(200)
        return None
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return e.headers.get("WWW-Authenticate") or "Bearer"
        return None


def _well_known(base, name, path=""):
    u = urllib.parse.urlsplit(base)
    return urllib.parse.urlunsplit((u.scheme, u.netloc, "/.well-known/%s%s" % (name, path), "", ""))


def discover(url, www_auth=None):
    """Datos para iniciar sesión en el conector: {'resource', 'issuer', 'meta' (del servidor de autorización), 'scopes'}."""
    url = url.strip()
    wa = parse_www_authenticate(www_auth if www_auth is not None else (probe(url) or ""))
    path = urllib.parse.urlsplit(url).path.rstrip("/")
    prm = None
    for cand in ([wa["resource_metadata"]] if wa.get("resource_metadata") else []) + \
            [_well_known(url, "oauth-protected-resource", path), _well_known(url, "oauth-protected-resource")]:
        try:
            prm = _get_json(cand)
            if prm.get("authorization_servers"):
                break
        except Exception:
            prm = None
    issuer = ((prm or {}).get("authorization_servers") or [None])[0]
    if not issuer:                                    # conectores antiguos: el propio servidor autoriza
        u = urllib.parse.urlsplit(url)
        issuer = "%s://%s" % (u.scheme, u.netloc)
    ipath = urllib.parse.urlsplit(issuer).path.rstrip("/")
    cands = [_well_known(issuer, "oauth-authorization-server", ipath), _well_known(issuer, "openid-configuration", ipath)]
    if ipath:
        cands.append(issuer.rstrip("/") + "/.well-known/openid-configuration")
    meta = None
    for c in cands:
        try:
            meta = _get_json(c)
            if meta.get("authorization_endpoint") and meta.get("token_endpoint"):
                break
            meta = None
        except Exception:
            meta = None
    if not meta:
        raise OAuthError(tr("El servicio no publica cómo iniciar sesión (no encontré su servidor de autorización)."))
    scopes = (wa.get("scope") or " ".join((prm or {}).get("scopes_supported") or [])).strip()
    return {"resource": canonical((prm or {}).get("resource") or url), "issuer": issuer, "meta": meta, "scopes": scopes}


# ---------------------------------------------------------------- registro del cliente
def _register(meta, redirect_uri):
    """Registro dinámico (RFC 7591): el servicio da a Jayth un identificador de cliente para este equipo."""
    reg = meta.get("registration_endpoint")
    if not reg:
        return None
    r = _post(reg, {"client_name": APP_NAME, "redirect_uris": [redirect_uri], "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"], "token_endpoint_auth_method": "none", "application_type": "native",
                    "client_uri": "https://github.com/Json-Tuiran/jayth.ai"}, json_body=True)
    if not r.get("client_id"):
        raise OAuthError(tr("El servicio no aceptó el registro de %s.") % APP_NAME)
    return {"client_id": r["client_id"], "client_secret": r.get("client_secret") or "", "redirect_uri": redirect_uri,
            "auth_method": r.get("token_endpoint_auth_method") or ("client_secret_post" if r.get("client_secret") else "none"), "dynamic": True}


def _client_auth(client, data, headers):
    if client.get("client_secret") and client.get("auth_method") == "client_secret_basic":
        tok = base64.b64encode(("%s:%s" % (urllib.parse.quote(client["client_id"], safe=""),
                                           urllib.parse.quote(client["client_secret"], safe=""))).encode()).decode()
        headers["Authorization"] = "Basic " + tok
    elif client.get("client_secret"):
        data["client_secret"] = client["client_secret"]


# ---------------------------------------------------------------- servidor de vuelta (127.0.0.1)
_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>%(app)s</title><style>
body{font-family:Segoe UI,system-ui,sans-serif;background:#141716;color:#EBF2F0;display:flex;align-items:center;justify-content:center;
height:100vh;margin:0}div{background:#1A1F1D;border:1px solid #27302C;border-radius:14px;padding:28px 34px;max-width:420px;text-align:center}
h1{font-size:18px;margin:0 0 8px;color:%(color)s}p{color:#97A69E;margin:0}</style></head><body><div><h1>%(title)s</h1><p>%(text)s</p></div></body></html>"""


class _Catcher(HTTPServer):
    result = None


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        if u.path != REDIRECT_PATH:
            self.send_response(404)
            self.end_headers()
            return
        q = dict(urllib.parse.parse_qsl(u.query))
        self.server.result = q
        ok = "code" in q
        page = _PAGE % {"app": APP_NAME, "color": "#6CC99C" if ok else "#F07A7A",
                        "title": tr("Listo: %s ya está conectado") % APP_NAME if ok else tr("No se pudo conectar"),
                        "text": tr("Ya puedes cerrar esta pestaña y volver a %s.") % APP_NAME if ok else
                        (q.get("error_description") or q.get("error") or tr("El servicio no dio permiso."))}
        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def _catcher(port=0):
    srv = _Catcher(("127.0.0.1", port), _Handler)
    srv.timeout = 0.3
    return srv


# ---------------------------------------------------------------- iniciar sesión, renovar, cerrar sesión
def _pkce():
    v = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    c = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
    return v, c


def login(url, client=None, open_url=None, stop=None, timeout=300, www_auth=None, scopes=None, extra=None):
    """Inicia sesión en el conector de url con el navegador del usuario. client: {'client_id', 'client_secret'} si el
    servicio no permite registrarse solo (p. ej. Google). Devuelve los permisos guardados. Lanza OAuthError o Cancelled."""
    info = discover(url, www_auth)
    meta = info["meta"]
    old = boveda.get(_key(url)) or {}
    cl = dict(client) if client else (old.get("client") if old.get("issuer") == info["issuer"] else None)
    srv = None
    if cl and cl.get("redirect_uri"):                    # un registro anterior: mismo puerto si está libre
        try:
            srv = _catcher(int(urllib.parse.urlsplit(cl["redirect_uri"]).port or 0))
        except OSError:
            cl = None if cl.get("dynamic") else cl
    if srv is None:
        srv = _catcher(0)
    redirect = "http://127.0.0.1:%d%s" % (srv.server_address[1], REDIRECT_PATH)
    try:
        if cl and not cl.get("dynamic"):
            cl["redirect_uri"] = redirect                # cliente del usuario (aplicación de escritorio): puerto libre
            cl.setdefault("auth_method", "client_secret_post" if cl.get("client_secret") else "none")
        elif not cl or cl.get("redirect_uri") != redirect:
            if CLIENT_METADATA_URL and meta.get("client_id_metadata_document_supported"):
                cl = {"client_id": CLIENT_METADATA_URL, "redirect_uri": redirect, "auth_method": "none", "dynamic": False}
            else:
                cl = _register(meta, redirect)
            if not cl:
                raise OAuthError(tr("Este servicio no permite que %s se registre solo: hace falta un identificador de cliente "
                                    "(lo da el propio servicio en su panel de desarrolladores).") % APP_NAME)
        verifier, challenge = _pkce()
        state = secrets.token_urlsafe(24)
        q = {"response_type": "code", "client_id": cl["client_id"], "redirect_uri": redirect, "code_challenge": challenge,
             "code_challenge_method": "S256", "state": state, "resource": info["resource"]}
        sc = scopes or info["scopes"]
        if sc:
            q["scope"] = sc
        if "accounts.google.com" in info["issuer"]:       # Google solo da el permiso para renovar con estos dos
            q.update(access_type="offline", prompt="consent")
        q.update(extra or {})
        auth = meta["authorization_endpoint"]
        full = auth + ("&" if "?" in auth else "?") + urllib.parse.urlencode(q)
        (open_url or webbrowser.open)(full)
        end = time.time() + timeout
        while srv.result is None:
            if stop is not None and stop.is_set():
                raise Cancelled(tr("Cancelado."))
            if time.time() > end:
                raise OAuthError(tr("No llegó la autorización a tiempo (5 minutos). Vuelve a intentarlo."))
            srv.handle_request()
        res = srv.result
    finally:
        srv.server_close()
    if res.get("state") != state:
        raise OAuthError(tr("La respuesta del servicio no corresponde a esta solicitud (state). Por seguridad, se descartó."))
    if "code" not in res:
        raise OAuthError(tr("El servicio no dio permiso: %s") % (res.get("error_description") or res.get("error") or "?"))
    data = {"grant_type": "authorization_code", "code": res["code"], "redirect_uri": redirect, "client_id": cl["client_id"],
            "code_verifier": verifier, "resource": info["resource"]}
    headers = {}
    _client_auth(cl, data, headers)
    tok = _post(meta["token_endpoint"], data, headers=headers)
    if not tok.get("access_token"):
        raise OAuthError(tr("El servicio no entregó el permiso de acceso."))
    rec = {"issuer": info["issuer"], "token_endpoint": meta["token_endpoint"], "resource": info["resource"], "client": cl,
           "access_token": tok["access_token"], "refresh_token": tok.get("refresh_token") or "",
           "expires_at": time.time() + float(tok.get("expires_in") or 3600), "scope": tok.get("scope") or sc or "", "since": time.time()}
    boveda.put(_key(url), rec)
    return rec


_LOCK = threading.Lock()


def token(url, force_refresh=False):
    """Permiso de acceso válido para el conector (renovado si hace falta) o None si hay que iniciar sesión."""
    with _LOCK:
        rec = boveda.get(_key(url))
        if not rec or not rec.get("access_token"):
            return None
        if not force_refresh and rec.get("expires_at", 0) - 60 > time.time():
            return rec["access_token"]
        if not rec.get("refresh_token"):
            return None if force_refresh or rec.get("expires_at", 0) < time.time() else rec["access_token"]
        cl = rec.get("client") or {}
        data = {"grant_type": "refresh_token", "refresh_token": rec["refresh_token"], "client_id": cl.get("client_id", ""),
                "resource": rec.get("resource") or canonical(url)}
        headers = {}
        _client_auth(cl, data, headers)
        try:
            tok = _post(rec["token_endpoint"], data, headers=headers)
        except Exception:
            return None
        if not tok.get("access_token"):
            return None
        rec.update(access_token=tok["access_token"], refresh_token=tok.get("refresh_token") or rec["refresh_token"],
                   expires_at=time.time() + float(tok.get("expires_in") or 3600))
        boveda.put(_key(url), rec)
        return rec["access_token"]


def signed_in(url):
    rec = boveda.get(_key(url))
    return bool(rec and rec.get("access_token"))


def logout(url):
    """Olvida los permisos de ese conector en este equipo (el servicio puede seguir listándolo en su cuenta)."""
    return boveda.delete(_key(url))
