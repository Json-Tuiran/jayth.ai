"""Nucleo compartido por la app de escritorio y la interfaz web: ajustes, conversaciones y el proceso del modelo."""
import os, re, json, time, uuid, threading, subprocess, http.client
from . import paths
from . import agent as A

paths.ensure()

NO_WINDOW = 0x08000000 if os.name == "nt" else 0

DEFAULTS = {
    "setup_done": False,
    # proveedor del modelo: "local" (llama-server gestionado por la app) o "external" (cualquier API compatible con OpenAI)
    "llm_mode": "local",
    "external_url": "http://127.0.0.1:11434/v1",
    "external_key": "",
    "external_model": "",
    # modelos locales (GGUF). Cada uno: {id, name, path, mmproj, repo, file, size, sha256, mmproj_file, mmproj_size, mmproj_sha256}
    "models": [],
    "active_model": "",
    "models_dir": paths.MODELS_DEFAULT,
    "llama_exe": "",
    "llama_tag": "",
    "backend": "cpu",            # cpu | cuda | vulkan
    "threads": max(1, (os.cpu_count() or 2) // 2),
    "llm_port": 8080,
    "n_ctx": 16384,
    # proyectos del modo Code
    "projects": [],
    "active_project": "",
    "app_mode": "chat",          # chat | code (ultimo modo usado)
    # interfaz
    "theme": "system",           # system | dark | light
    "user_name": "",
    # agente
    "workspace": paths.WORKSPACE_DEFAULT,
    "mode": "ask",               # readonly | ask | edits | auto
    "thinking": False,
    "max_tokens": 4096,
    "max_steps": 30,
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 20,
    "vision": True,
    "keep_images": 1,
    "max_tool_output": 8000,
    "brave_key": "",
    "custom_instructions": "",
}


# ---------------------------------------------------------------- ajustes
class Settings:
    def __init__(self):
        self.path = os.path.join(paths.DATA, "settings.json")
        self.lock = threading.Lock()
        self.v = dict(DEFAULTS)
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.v.update({k: x for k, x in json.load(f).items() if k in DEFAULTS})
        except Exception:
            pass
        if os.path.normcase(self.v["workspace"]).endswith(os.path.normcase(os.path.join("Documents", "AgenteLocal"))):
            self.v["workspace"] = paths.WORKSPACE_DEFAULT   # carpeta del nombre provisional anterior

    def update(self, new):
        with self.lock:
            for k, x in new.items():
                if k not in DEFAULTS:
                    continue
                dv = DEFAULTS[k]
                try:
                    if isinstance(dv, list):
                        x = list(x)
                    elif isinstance(dv, bool):
                        x = x if isinstance(x, bool) else str(x).lower() in ("1", "true", "on", "yes", "si", "sí")
                    elif isinstance(dv, int):
                        x = int(float(x))
                    elif isinstance(dv, float):
                        x = float(x)
                    else:
                        x = str(x)
                except (TypeError, ValueError):
                    continue
                if k == "mode" and x not in A.MODES:
                    continue
                self.v[k] = x
            self._save()

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.v, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    def snapshot(self):
        with self.lock:
            v = dict(self.v)
        os.makedirs(v["workspace"], exist_ok=True)
        return v

    def ready(self):
        """True si hay un proveedor de modelo utilizable."""
        v = self.snapshot()
        if not v["setup_done"]:
            return False
        if v["llm_mode"] == "external":
            return bool(v["external_url"])
        m = active_model(v)
        return bool(m and os.path.isfile(m.get("path", "")) and os.path.isfile(v["llama_exe"]))

    # --- registro de modelos
    def add_model(self, m, activate=True):
        with self.lock:
            ms = [x for x in self.v["models"] if x.get("id") != m["id"]]
            ms.append(m)
            self.v["models"] = ms
            if activate or not self.v["active_model"]:
                self.v["active_model"] = m["id"]
            self._save()

    # --- proyectos (modo Code): {id, name, path, instructions, created}
    def add_project(self, name, path, instructions=""):
        p = {"id": uuid.uuid4().hex[:10], "name": name.strip() or os.path.basename(path), "path": os.path.normpath(path),
             "instructions": instructions, "created": time.time()}
        os.makedirs(p["path"], exist_ok=True)
        with self.lock:
            self.v["projects"] = self.v["projects"] + [p]
            self.v["active_project"] = p["id"]
            self._save()
        return p

    def update_project(self, pid, **kw):
        with self.lock:
            self.v["projects"] = [dict(p, **kw) if p["id"] == pid else p for p in self.v["projects"]]
            self._save()

    def remove_project(self, pid):
        """Quita el proyecto de la lista (no borra su carpeta)."""
        with self.lock:
            self.v["projects"] = [p for p in self.v["projects"] if p["id"] != pid]
            if self.v["active_project"] == pid:
                self.v["active_project"] = self.v["projects"][0]["id"] if self.v["projects"] else ""
            self._save()

    def remove_model(self, mid):
        with self.lock:
            self.v["models"] = [x for x in self.v["models"] if x.get("id") != mid]
            if self.v["active_model"] == mid:
                self.v["active_model"] = self.v["models"][0]["id"] if self.v["models"] else ""
            self._save()


def active_model(cfg):
    for m in cfg.get("models", []):
        if m.get("id") == cfg.get("active_model"):
            return m
    return None


def llm_base(cfg):
    """URL base /v1 del proveedor activo."""
    if cfg["llm_mode"] == "external":
        return cfg["external_url"].rstrip("/")
    return "http://127.0.0.1:%d/v1" % int(cfg["llm_port"])


SET = Settings()


# ---------------------------------------------------------------- conversaciones
DEFAULT_TITLE = "Nueva conversación"


class Session:
    def __init__(self, sid, title=DEFAULT_TITLE, created=None, data=None):
        self.id, self.title, self.created = sid, title, created or time.time()
        self.data = data or {"messages": [], "allowed": []}
        self.events = []
        self.cond = threading.Condition()
        self.run = None
        self.updated = self.created
        self.jpath = os.path.join(paths.SESS_DIR, sid + ".json")
        self.epath = os.path.join(paths.SESS_DIR, sid + ".events.jsonl")

    def meta(self):
        return {"id": self.id, "title": self.title, "created": self.created, "updated": self.updated, "busy": self.run is not None}

    def add_event(self, ev):
        with self.cond:
            ev["i"] = len(self.events)
            ev["ts"] = round(time.time(), 2)
            self.events.append(ev)
            try:
                with open(self.epath, "a", encoding="utf-8") as f:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            except Exception:
                pass
            self.updated = time.time()
            self.cond.notify_all()
        if ev["t"] in ("assistant_end", "tool_result", "turn_end", "user"):
            self.save()

    def save(self):
        try:
            tmp = self.jpath + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"id": self.id, "title": self.title, "created": self.created, "updated": self.updated, "data": self.data}, f, ensure_ascii=False)
            os.replace(tmp, self.jpath)
        except Exception:
            pass

    def send(self, text, images=()):
        """Lanza el agente en un hilo. Devuelve None o un mensaje de error."""
        if self.run is not None:
            return "El agente sigue trabajando en esta conversación."
        cfg = SET.snapshot()
        proj = project(cfg, self.data.get("project"))
        if proj:   # en un proyecto el agente trabaja dentro de su carpeta y sigue sus instrucciones
            cfg["workspace"] = proj["path"]
            extra = "Trabajas en el proyecto «%s» (carpeta %s). Las rutas relativas son relativas a esa carpeta." % (proj["name"], proj["path"])
            if proj.get("instructions"):
                extra += "\nInstrucciones del proyecto:\n" + proj["instructions"]
            cfg["custom_instructions"] = (cfg["custom_instructions"] + "\n\n" + extra).strip()
            os.makedirs(proj["path"], exist_ok=True)
        run = A.Run(self.data, cfg, self.add_event, paths.IMG_DIR)
        self.run = run
        if self.title == DEFAULT_TITLE:
            self.title = (text or "Imagen")[:48]

        def go():
            try:
                run.run(text or "(imagen adjunta)", list(images))
            finally:
                self.run = None
                self.save()
        threading.Thread(target=go, daemon=True).start()
        return None

    def last_user(self):
        """Ultimo mensaje escrito por el usuario (evento 'user'), o None."""
        for ev in reversed(self.events):
            if ev["t"] == "user":
                return ev
        return None

    def regenerate(self):
        """Descarta la ultima respuesta y vuelve a enviar el ultimo mensaje del usuario."""
        if self.run is not None:
            return "El agente sigue trabajando en esta conversación."
        ev = self.last_user()
        if not ev:
            return "No hay ningún mensaje que regenerar."
        msgs = self.data["messages"]
        idx = max((i for i, m in enumerate(msgs) if m["role"] == "user" and not m.get("_auto")), default=None)
        if idx is not None:
            del msgs[idx:]
        with self.cond:
            del self.events[ev["i"]:]
            try:
                with open(self.epath, "w", encoding="utf-8") as f:
                    for e in self.events:
                        f.write(json.dumps(e, ensure_ascii=False) + "\n")
            except Exception:
                pass
        return self.send(ev["text"], ev.get("images") or [])

    def search_text(self):
        """Texto de la conversacion para el buscador (titulo + mensajes)."""
        parts = [self.title]
        for e in self.events:
            if e["t"] in ("user", "assistant_end"):
                parts.append(e.get("text") or "")
        return "\n".join(parts).lower()

    def delete(self):
        if self.run:
            self.run.request_stop()
        SESSIONS.pop(self.id, None)
        for fp in (self.jpath, self.epath):
            try:
                os.remove(fp)
            except OSError:
                pass


SESSIONS = {}


def load_sessions():
    for fn in os.listdir(paths.SESS_DIR):
        if fn.endswith(".json"):
            try:
                with open(os.path.join(paths.SESS_DIR, fn), "r", encoding="utf-8") as f:
                    j = json.load(f)
                s = Session(j["id"], j["title"], j["created"], j["data"])
                s.updated = j.get("updated", s.created)
                if os.path.isfile(s.epath):
                    with open(s.epath, "r", encoding="utf-8") as f:
                        s.events = [json.loads(l) for l in f if l.strip()]
                SESSIONS[s.id] = s
            except Exception:
                continue


def new_session(project_id=None):
    s = Session(uuid.uuid4().hex[:10])
    if project_id:
        s.data["project"] = project_id
    SESSIONS[s.id] = s
    s.save()
    return s


def project(cfg, pid):
    for p in cfg.get("projects", []):
        if pid and p["id"] == pid:
            return p
    return None


def sessions_for(project_id=None):
    """Conversaciones del modo Chat (project_id=None) o de un proyecto."""
    return [s for s in sorted_sessions() if (s.data.get("project") or None) == (project_id or None)]


def sorted_sessions():
    return sorted(SESSIONS.values(), key=lambda s: -s.updated)


# ---------------------------------------------------------------- proceso del modelo (llama-server)
class LLM:
    def __init__(self):
        self.proc = None
        self.log = os.path.join(paths.DATA, "llama.log")

    def _health(self, port):
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=1.5)
            c.request("GET", "/health")
            r = c.getresponse()
            r.read()
            c.close()
            return r.status
        except Exception:
            return None

    def status(self):
        cfg = SET.snapshot()
        if cfg["llm_mode"] == "external":
            return self._external_status(cfg)
        h = self._health(int(cfg["llm_port"]))
        mine = self.proc is not None and self.proc.poll() is None
        if h == 200:
            return {"state": "ready", "external": not mine}
        if h == 503 or (mine and h is None):
            return {"state": "loading"}
        if self.proc is not None and self.proc.poll() not in (None, 0):
            return {"state": "off", "error": "El modelo se cerró (código %s). Revisa el registro." % self.proc.poll()}
        return {"state": "off"}

    def _external_status(self, cfg):
        import urllib.request
        try:
            req = urllib.request.Request(cfg["external_url"].rstrip("/") + "/models",
                                         headers={"Authorization": "Bearer " + (cfg["external_key"] or "local")})
            urllib.request.urlopen(req, timeout=2).read(200)
            return {"state": "ready", "external": True}
        except Exception as e:
            return {"state": "off", "external": True, "error": "Servidor externo no disponible"}

    def command(self, cfg=None):
        cfg = cfg or SET.snapshot()
        m = active_model(cfg) or {}
        cmd = [cfg["llama_exe"], "-m", m.get("path", ""), "--host", "127.0.0.1", "--port", str(cfg["llm_port"]),
               "-t", str(cfg["threads"]), "-c", str(cfg["n_ctx"]), "--jinja", "--no-warmup"]
        if cfg["backend"] in ("cuda", "vulkan"):
            cmd += ["--fit", "on"]          # reparte capas entre GPU y RAM segun la memoria disponible
        if cfg["vision"] and m.get("mmproj") and os.path.isfile(m["mmproj"]):
            cmd += ["--mmproj", m["mmproj"]]
        return cmd

    def start(self):
        cfg = SET.snapshot()
        if cfg["llm_mode"] == "external":
            return "Estás usando un servidor externo; enciéndelo desde ese programa."
        if self.status()["state"] != "off":
            return None
        m = active_model(cfg)
        if not m:
            return "No hay ningún modelo elegido. Añade uno en «Modelos»."
        for path, label in ((cfg["llama_exe"], "llama-server"), (m.get("path"), "el modelo «%s»" % m.get("name"))):
            if not path or not os.path.isfile(path):
                return "No encuentro %s (%s). Abre el asistente de configuración." % (label, path or "sin configurar")
        have = os.path.getsize(m["path"])
        if m.get("size") and have < int(m["size"]) and not re.search(r"-\d{5}-of-\d{5}\.gguf$", m["path"]):
            return "El archivo del modelo aún está incompleto (%.1f de %.1f GB). Espera a que termine la descarga." % (have / 1024 ** 3, int(m["size"]) / 1024 ** 3)
        lf = open(self.log, "wb")
        self.proc = subprocess.Popen(self.command(cfg), stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     cwd=os.path.dirname(cfg["llama_exe"]), creationflags=NO_WINDOW)
        return None

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True, creationflags=NO_WINDOW)
        self.proc = None

    def tail(self, n=60):
        try:
            with open(self.log, "rb") as f:
                return b"\n".join(f.read()[-12000:].splitlines()[-n:]).decode("utf-8", "replace")
        except Exception:
            return ""


LLM_MGR = LLM()


def shutdown():
    for s in SESSIONS.values():
        if s.run:
            s.run.request_stop()
    LLM_MGR.stop()
