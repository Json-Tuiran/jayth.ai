"""Nucleo compartido por la app de escritorio y la interfaz web: ajustes, conversaciones y el proceso del modelo."""
import os, re, json, time, uuid, threading, subprocess, http.client
from . import paths, osys
from . import agent as A

paths.ensure()

NO_WINDOW = osys.NO_WINDOW

DEFAULTS = {
    "setup_done": False,
    # proveedor del modelo: "local" (llama-server gestionado por la app) o "external" (cualquier API compatible con OpenAI)
    "llm_mode": "local",
    "external_url": "http://127.0.0.1:11434/v1",
    "external_key": "",
    "external_model": "",
    "providers": [],             # servicios por API guardados: {id, name, url, key, models}
    "external_provider": "",     # id del proveedor al que pertenece el modelo externo activo
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
    "gpu_layers": -1,            # -1 = automatico (--fit); 0 = solo CPU; N = capas en la GPU
    "batch_size": 512,
    "flash_attn": "auto",        # auto | on | off
    "cache_type": "f16",         # f16 | q8_0 | q4_0 (contexto comprimido: menos memoria)
    "mmap": True,
    "mlock": False,
    "warmup": True,              # precalentar instrucciones y herramientas al encender el modelo
    "autostart_llm": False,
    "idle_unload": 0,            # minutos sin uso para apagar el modelo (0 = nunca)
    # generacion
    "min_p": 0.0,
    "repeat_penalty": 1.0,
    "seed": -1,
    "sampling": "auto",          # auto = valores recomendados para la familia del modelo | custom = los de abajo
    # conectores MCP: [{name, command, args:[...], env:{}, enabled}]
    "mcp_servers": [],
    # proyectos del modo Code
    "projects": [],
    "active_project": "",
    "app_mode": "chat",          # chat | code (ultimo modo usado)
    "layout": {},                # distribucion de paneles: anchos, plegados, lados (la guarda la ventana sola)
    # interfaz
    "theme": "system",           # system | dark | light
    "font_scale": 100,
    "user_name": "",
    "start_with_windows": False,
    "close_to_tray": False,
    "notifications": True,
    "quick_hotkey": "Ctrl+Alt+J",       # atajo global de la ventana rápida (vacío = desactivado). Ctrl+Alt+Espacio lo usa
                                        # la app de Claude y Alt+Espacio la de ChatGPT: se evita chocar con ellas
    "custom_titlebar": True,     # barra de titulo integrada en la ventana (como las apps de escritorio modernas)
    "animations": True,
    # novedades
    "auto_update_check": True,   # avisar cuando haya una version nueva de Jayth
    "model_news": True,          # avisar cuando se publiquen versiones nuevas de tus modelos
    "model_news_seen": [],
    # personalizacion
    "assistants": [],            # asistentes propios: {id, name, instructions, files}
    "skills_disabled": [],       # habilidades apagadas (por su id de carpeta)
    "tasks": [],                 # tareas programadas (ver schedule.py)
    "memory_enabled": True,      # usar y guardar la memoria entre conversaciones
    "about_me": "",
    "response_style": "",
    "response_language": "auto",
    # agente
    "workspace": paths.WORKSPACE_DEFAULT,
    "mode": "auto",              # readonly | plan | ask | edits | auto (por defecto el agente decide solo)
    "thinking": False,           # se deriva del esfuerzo (se conserva por compatibilidad)
    "effort": "",                # low | medium | high: cuanto razona el modelo antes de responder ("" = segun 'thinking')
    "max_tokens": 4096,
    "max_steps": 30,
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 20,
    "vision": True,
    "keep_images": 1,
    "max_tool_output": 8000,
    "command_timeout": 60,
    "auto_allow_commands": [],   # prefijos de comandos que se permiten sin preguntar (p. ej. "git status")
    "tools_disabled": [],
    "web_access": True,
    "computer_control": True,
    "search_provider": "auto",   # auto (DuckDuckGo + Wikipedia) | brave | searxng
    "brave_key": "",
    "searxng_url": "",
    "custom_instructions": "",
}

# Ajustes que solo se aplican al reiniciar el motor
RESTART_KEYS = {"threads", "n_ctx", "gpu_layers", "batch_size", "flash_attn", "cache_type", "mmap", "mlock", "llm_port", "vision", "backend", "llama_exe"}
LAST_USE = [time.time()]   # ultima actividad del agente (para apagar el modelo por inactividad)


# ---------------------------------------------------------------- ajustes
class Settings:
    def __init__(self):
        self.path = os.path.join(paths.DATA, "settings.json")
        self.lock = threading.Lock()
        self.v = dict(DEFAULTS)
        self.load_error = ""
        if os.path.isfile(self.path):
            for attempt in range(3):          # otro proceso podria estar escribiendolo en ese instante
                try:
                    with open(self.path, "r", encoding="utf-8-sig") as f:
                        self.v.update({k: x for k, x in json.load(f).items() if k in DEFAULTS})
                    break
                except Exception as e:
                    if attempt == 2:
                        # no empezar de cero en silencio: conservar una copia del archivo danado
                        bak = self.path + ".danado-%d.json" % int(time.time())
                        try:
                            os.replace(self.path, bak)
                        except OSError:
                            pass
                        self.load_error = "No se pudieron leer tus ajustes (%s). Se guardó una copia en %s." % (e, bak)
                    time.sleep(0.3)
        old_ws = os.path.join(os.path.dirname(paths.WORKSPACE_DEFAULT), "AgenteLocal")
        if os.path.normcase(os.path.normpath(self.v["workspace"])) == os.path.normcase(old_ws):
            self.v["workspace"] = paths.WORKSPACE_DEFAULT   # carpeta del nombre provisional anterior (Documentos\AgenteLocal)

    def update(self, new):
        with self.lock:
            for k, x in new.items():
                if k not in DEFAULTS:
                    continue
                dv = DEFAULTS[k]
                try:
                    if isinstance(dv, list):
                        x = list(x)
                    elif isinstance(dv, dict):
                        x = dict(x)
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


def model_title(m):
    """Nombre limpio para mostrar (familia, versión, tamaño y variante; sin cuantización)."""
    from .provision import pretty_name
    return pretty_name(m.get("repo") or m.get("file") or m.get("name") or "") if m else ""


def model_quant(m):
    """Variante del modelo (Q4_K_M…): la guardada al instalarlo; si no consta, la que indique el nombre del archivo."""
    from .provision import quant_label
    if m and m.get("quant"):
        return str(m["quant"])
    f = os.path.basename(m.get("file") or m.get("path") or "") if m else ""
    q = quant_label(f) if f else ""
    return "" if q == f else q


EFFORTS = [("low", "Bajo", "Responde directo, sin razonar antes. Lo más rápido."),
           ("medium", "Medio", "Razona antes de responder. Mejor en tareas con varios pasos."),
           ("high", "Alto", "Razona a fondo y con más margen de respuesta. Para lo difícil; es lo más lento.")]


def effort_of(cfg):
    """Esfuerzo efectivo: el elegido o, si no hay, el que corresponde al antiguo ajuste 'Pensar'."""
    e = cfg.get("effort") or ""
    return e if e in ("low", "medium", "high") else ("medium" if cfg.get("thinking") else "low")


def set_effort(e):
    SET.update({"effort": e, "thinking": e != "low"})


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
        self.temp = False            # chat temporal: no se guarda en disco, no usa ni escribe la memoria
        self.jpath = os.path.join(paths.SESS_DIR, sid + ".json")
        self.epath = os.path.join(paths.SESS_DIR, sid + ".events.jsonl")

    def meta(self):
        return {"id": self.id, "title": self.title, "created": self.created, "updated": self.updated, "busy": self.run is not None}

    def add_event(self, ev):
        LAST_USE[0] = time.time()
        with self.cond:
            ev["i"] = len(self.events)
            ev["ts"] = round(time.time(), 2)
            self.events.append(ev)
            try:
                if not self.temp:                    # el chat temporal vive solo en memoria
                    with open(self.epath, "a", encoding="utf-8") as f:
                        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            except Exception:
                pass
            self.updated = time.time()
            self.cond.notify_all()
        if ev["t"] in ("assistant_end", "tool_result", "turn_end", "user"):
            self.save()

    def save(self):
        if self.temp:
            return
        try:
            tmp = self.jpath + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"id": self.id, "title": self.title, "created": self.created, "updated": self.updated, "data": self.data}, f, ensure_ascii=False)
            os.replace(tmp, self.jpath)
        except Exception:
            pass

    def send(self, text, images=(), files=(), mode=None):
        """Lanza el agente en un hilo. files: rutas de documentos adjuntos (su texto se incluye en el mensaje).
        Devuelve None o un mensaje de error."""
        if self.run is not None:
            return "El agente sigue trabajando en esta conversación."
        cfg = SET.snapshot()
        if mode:
            cfg["mode"] = mode
        proj = project(cfg, self.data.get("project"))
        if proj:   # en un proyecto el agente trabaja dentro de su carpeta y sigue sus instrucciones
            cfg["workspace"] = proj["path"]
            cfg["_project"] = True
            extra = "Trabajas en el proyecto «%s» (carpeta %s). Las rutas relativas son relativas a esa carpeta." % (proj["name"], proj["path"])
            if proj.get("instructions"):
                extra += "\nInstrucciones del proyecto:\n" + proj["instructions"]
            cfg["custom_instructions"] = (cfg["custom_instructions"] + "\n\n" + extra).strip()
            os.makedirs(proj["path"], exist_ok=True)
        if self.data.get("assistant"):       # la conversación usa un asistente: sus instrucciones y archivos de referencia
            from . import assistants as AS
            a = AS.get(self.data["assistant"], cfg)
            if a:
                cfg["custom_instructions"] = (cfg["custom_instructions"] + "\n\n" + AS.instructions_for(a)).strip()
        cfg["_sid"] = self.id
        cfg["_temp"] = self.temp
        cfg["_model_title"] = model_title(active_model(cfg)) if cfg["llm_mode"] == "local" else (cfg.get("external_model") or "")
        attach = attachments_text(files)
        if cfg["mode"] == "plan":
            self.data["plan"] = []
        run = A.Run(self.data, cfg, self.add_event, paths.IMG_DIR)
        self.run = run
        if self.title == DEFAULT_TITLE:
            # titulo provisional; al terminar la primera respuesta el propio modelo propone uno breve
            self.title = re.sub(r"\s+", " ", text or "Archivo adjunto").strip()[:48]
            self.data["title_auto"] = 2          # intentos que quedan

        def go():
            try:
                run.run(text or "(adjuntos)", list(images), attach)
            finally:
                self.run = None
                self.save()
            self._auto_title(cfg)
        threading.Thread(target=go, daemon=True).start()
        return None

    def _auto_title(self, cfg):
        """El modelo elegido pone nombre a la conversacion (una vez; si falla, se reintenta en la siguiente respuesta)."""
        left = self.data.get("title_auto") or 0
        if not left or self.run is not None or self.temp:
            return
        self.data["title_auto"] = left - 1
        t = A.make_title(cfg, self.data["messages"])
        if t and self.data.get("title_auto") is not None:   # None: el usuario la renombro mientras tanto
            self.title = t
            self.data["title_auto"] = 0
        self.save()

    def rename(self, title):
        self.title = title.strip()[:80]
        self.data["title_auto"] = None
        self.save()

    def answer(self, cid, text):
        """Respuesta del usuario a una pregunta del agente (ask_user)."""
        return bool(self.run and self.run.resolve(cid, "answer:" + text))

    def _note(self, text):
        """Deja constancia para el modelo (sin mostrarlo como mensaje del usuario)."""
        self.data["messages"].append({"role": "user", "_auto": True, "content": "(Nota del sistema: %s)" % text})
        self.data["messages"].append({"role": "assistant", "content": "Entendido."})

    def undo(self, cid):
        """Deshace los cambios de archivos de una accion del agente."""
        from . import harness
        if self.run is not None:
            return None
        files = harness.undo(self.id, cid)
        if files:
            self.add_event({"t": "undo", "ids": [cid], "files": files})
            self._note("el usuario deshizo tus cambios en: %s" % ", ".join(files))
            self.save()
        return files

    def undo_turn(self):
        """Deshace todos los cambios de archivos de la ultima respuesta (desde el ultimo mensaje del usuario)."""
        from . import harness
        if self.run is not None:
            return None
        last = self.last_user()
        ids = [e["id"] for e in self.events[last["i"]:] if e["t"] == "tool_result" and e.get("undo") and harness.has_snapshot(self.id, e["id"])] if last else []
        files = []
        for cid in reversed(ids):
            files += harness.undo(self.id, cid)
        if files:
            self.add_event({"t": "undo", "ids": ids, "files": sorted(set(files))})
            self._note("el usuario deshizo todos tus cambios de la última respuesta en: %s" % ", ".join(sorted(set(files))))
            self.save()
        return files

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


def new_session(project_id=None, temp=False):
    s = Session(uuid.uuid4().hex[:10])
    s.temp = temp
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
    return [s for s in sorted_sessions() if (s.data.get("project") or None) == (project_id or None) and not s.temp]


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
            return {"state": "ready", "external": not mine, "warm": self.warm}
        if h == 503 or (mine and h is None):
            return {"state": "loading"}
        if self.proc is not None and self.proc.poll() not in (None, 0):
            return {"state": "off", "error": "El modelo se cerró (código %s). Revisa el registro." % self.proc.poll()}
        return {"state": "off"}

    def _external_status(self, cfg):
        import urllib.request, urllib.error
        try:
            req = urllib.request.Request(cfg["external_url"].rstrip("/") + "/models",
                                         headers={"Authorization": "Bearer " + (cfg["external_key"] or "local")})
            urllib.request.urlopen(req, timeout=4).read(200)
            return {"state": "ready", "external": True}
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return {"state": "off", "external": True, "error": "El servicio rechazó la clave de API (HTTP %d)." % e.code}
            return {"state": "ready", "external": True}      # contesta, aunque no ofrezca la lista de modelos
        except Exception as e:
            return {"state": "off", "external": True, "error": "Servidor externo no disponible"}

    def command(self, cfg=None):
        cfg = cfg or SET.snapshot()
        m = active_model(cfg) or {}
        cmd = [cfg["llama_exe"], "-m", m.get("path", ""), "--host", "127.0.0.1", "--port", str(cfg["llm_port"]),
               "-t", str(cfg["threads"]), "-c", str(cfg["n_ctx"]), "--jinja", "--no-warmup",
               "-np", "1",                       # una sola ranura: todo el contexto disponible y la cache de prompt siempre se reutiliza
               "-b", str(cfg["batch_size"])]
        if cfg["backend"] in ("cuda", "vulkan", "metal"):
            if int(cfg["gpu_layers"]) >= 0:
                cmd += ["-ngl", str(cfg["gpu_layers"])]
            else:
                cmd += ["--fit", "on"]          # reparte capas entre GPU y RAM segun la memoria disponible
        fa = cfg["flash_attn"]
        if cfg["cache_type"] != "f16":
            cmd += ["-ctk", cfg["cache_type"], "-ctv", cfg["cache_type"]]
            fa = "on"                           # la cache V comprimida requiere flash attention
        if fa in ("on", "off"):
            cmd += ["-fa", fa]
        if not cfg["mmap"]:
            cmd += ["--no-mmap"]
        if cfg["mlock"]:
            cmd += ["--mlock"]
        if cfg["vision"] and m.get("mmproj") and os.path.isfile(m["mmproj"]):
            cmd += ["--mmproj", m["mmproj"]]
        return cmd

    # --- precalentamiento: procesa una vez las instrucciones y herramientas fijas para que el primer mensaje sea rapido
    warm = ""          # "" | "warming" | "warm"

    def warmup(self):
        if self.warm:
            return
        self.warm = "warming"
        try:
            cfg = SET.snapshot()
            payload = {"model": "local", "stream": False, "max_tokens": 1, "cache_prompt": True, "temperature": 0,
                       "messages": [{"role": "system", "content": A.system_prompt(cfg)}, {"role": "user", "content": "hola"}],
                       "tools": A.tool_schemas(cfg), "chat_template_kwargs": {"enable_thinking": effort_of(cfg) != "low",
                                                                               "reasoning_effort": effort_of(cfg)}}
            c = http.client.HTTPConnection("127.0.0.1", int(cfg["llm_port"]), timeout=10)
            c.connect()
            c.sock.settimeout(None)
            c.request("POST", "/v1/chat/completions", json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json"})
            c.getresponse().read()
            c.close()
            self.warm = "warm"
        except Exception:
            self.warm = ""

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
        bindir = os.path.dirname(cfg["llama_exe"])
        env = dict(os.environ)
        if osys.LINUX:      # las bibliotecas (.so) de llama.cpp vienen junto al ejecutable
            env["LD_LIBRARY_PATH"] = bindir + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        elif osys.MAC:
            env["DYLD_LIBRARY_PATH"] = bindir + os.pathsep + env.get("DYLD_LIBRARY_PATH", "")
        self.proc = subprocess.Popen(self.command(cfg), stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     cwd=bindir, env=env, **osys.popen_kwargs())
        return None

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            osys.kill_tree(self.proc.pid)
            try:
                self.proc.wait(5)
            except Exception:
                pass
        self.proc = None
        self.warm = ""

    def mine(self):
        return self.proc is not None and self.proc.poll() is None

    def tail(self, n=60):
        try:
            with open(self.log, "rb") as f:
                return b"\n".join(f.read()[-12000:].splitlines()[-n:]).decode("utf-8", "replace")
        except Exception:
            return ""


LLM_MGR = LLM()


def shutdown():
    from . import harness
    for s in SESSIONS.values():
        if s.run:
            s.run.request_stop()
    LLM_MGR.stop()
    harness.bg_stop_all()
    harness.mcp_stop_all()


TEXT_LIMIT = 40000


def attachments_text(files):
    """Texto de los documentos adjuntos para incluirlo en el mensaje (con su nombre como encabezado)."""
    from . import harness
    out = []
    for p in files or []:
        name = os.path.basename(p)
        try:
            if os.path.splitext(p)[1].lower() in (".docx", ".docm", ".pptx", ".xlsx", ".xlsm", ".pdf"):
                txt = harness.read_document(p, TEXT_LIMIT)
            else:
                with open(p, "rb") as f:
                    raw = f.read(TEXT_LIMIT * 2)
                if b"\0" in raw[:4096]:
                    txt = "(archivo binario: no se puede leer como texto; ruta %s)" % p
                else:
                    txt = raw.decode("utf-8", "replace")[:TEXT_LIMIT]
        except Exception as e:
            txt = "(no se pudo leer: %s)" % e
        out.append("### %s\nRuta: %s\n```\n%s\n```" % (name, p, txt))
    return "\n\n".join(out)
