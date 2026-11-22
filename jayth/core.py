# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Nucleo compartido por la app de escritorio y la interfaz web: ajustes, conversaciones y el proceso del modelo."""
import os, re, json, time, uuid, threading, subprocess, http.client
from . import paths, osys
from . import agent as A
from . import i18n
from .i18n import tr

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
    "models_ignored": [],        # archivos que el usuario quitó de la lista: no se vuelven a añadir solos
    "models_scan_init": False,   # ya se hizo la primera revisión de la carpeta de modelos
    "llama_exe": "",
    "llama_tag": "",
    "backend": "cpu",            # cpu | cuda | vulkan
    "threads": max(1, (os.cpu_count() or 2) // 2),
    "threads_batch": 0,          # hilos al leer (procesar el prompt); 0 = automático (con solo procesador, todos los lógicos)
    "llm_port": 8080,
    "n_ctx": 0,                  # 0 = automatico: el maximo que admite el modelo, ajustado a la memoria (ver effective_ctx)
    "ctx_auto_migrated": False,  # el antiguo valor fijo por defecto (16384) ya se paso a automatico
    "gpu_layers": -1,            # -1 = automatico (--fit); 0 = solo CPU; N = capas en la GPU
    "batch_size": 512,
    "flash_attn": "auto",        # auto | on | off
    "cache_type": "f16",         # f16 | q8_0 | q4_0 (contexto comprimido: menos memoria)
    "mmap": True,
    "mlock": False,
    "spec_type": "auto",         # decodificación especulativa: auto (lo que eligió el ajuste medido) | none | draft-mtp | ngram-mod | …
    "tuning": {},                # último ajuste medido (ajuste.py): hilos, flash attention, velocidades y aceleración elegida
    "engine_caps": {},           # qué admite el llama-server instalado (se lee de su ayuda una vez por versión)
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
    "projects_removed": [],      # ids quitados de la lista a propósito: recover_projects() no los devuelve
    "active_project": "",
    "app_mode": "chat",          # chat | code (ultimo modo usado)
    "layout": {},                # distribucion de paneles: anchos, plegados, lados (la guarda la ventana sola)
    "editor_wrap": False,        # editor de Jayth Code: ajustar las lineas largas al ancho (Alt+Z)
    "editor_autosave": "delay",  # guardado automatico: delay (tras 1 s sin escribir) | focus (al cambiar de pestaña o ventana) | off
    "preview_modes": {},         # por extension: "preview" o "code" (Markdown y CSV se abren formateados)
    # interfaz
    "ui_language": "auto",       # auto (el del sistema) | es | en | pt  (ver i18n.py; se aplica al reiniciar)
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
    "auto_install_updates": True,   # bajarla en segundo plano e instalarla al cerrar Jayth (o al pulsar «Reiniciar para actualizar»)
    "model_news": True,          # avisar cuando se publiquen versiones nuevas de tus modelos
    "model_news_seen": [],
    # personalizacion
    "assistants": [],            # asistentes propios: {id, name, instructions, files}
    "skills_disabled": [],       # habilidades apagadas (por su id de carpeta)
    "voice_model": "base",       # modelo de dictado: tiny, base o small
    "voice_lang": "",            # idioma del dictado ("" = detectar)
    "voice_rate": 0.0,           # velocidad de lectura en voz alta (-1 a 1)
    "download_connections": 6,   # conexiones simultáneas al descargar modelos (1 = una sola, como antes)
    "tasks": [],             # tareas programadas (ver schedule.py)
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
    "tools_mode": "auto",        # auto: herramientas básicas + grupos a demanda (agent.GROUPS) | all: todas siempre
    "web_access": True,
    "computer_control": True,
    "search_provider": "auto",   # auto (DuckDuckGo + Wikipedia) | brave | searxng
    "brave_key": "",
    "searxng_url": "",
    "custom_instructions": "",
    # imágenes (imagegen.py: stable-diffusion.cpp en el propio equipo)
    "image_gen": True,           # ofrecer al agente la herramienta generate_image
    "image_model": "auto",        # auto: rápido (Segmind Vega RT) sin tarjeta gráfica y FLUX.2 [klein] con ella
    "image_size": "auto",        # auto (512 sin tarjeta gráfica, 1024 con ella) | 512 | 768 | 1024
    "image_dir": "",             # carpeta donde se guardan ("" = «imagenes» dentro de la carpeta de trabajo)
    # conocimiento local (conocimiento.py): carpetas donde el agente busca por significado
    "knowledge_folders": [],
    "knowledge_auto": True,      # actualizar el índice al abrir Jayth (solo lee lo que cambió)
    "knowledge_indexed": "",
}

# Ajustes que solo se aplican al reiniciar el motor
RESTART_KEYS = {"threads", "threads_batch", "n_ctx", "gpu_layers", "batch_size", "flash_attn", "cache_type", "mmap", "mlock", "llm_port", "vision", "backend", "llama_exe",
                "spec_type", "tuning"}
LAST_USE = [time.time()]   # ultima actividad del agente (para apagar el modelo por inactividad)


# ---------------------------------------------------------------- ajustes
def _plain(x):
    """Copia independiente y comparable (como queda en el JSON): tuplas -> listas, sin referencias compartidas."""
    return json.loads(json.dumps(x, ensure_ascii=False))


def _id_list(x):
    return isinstance(x, list) and all(isinstance(i, dict) and "id" in i for i in x)


def _merge_ids(base, mine, disk):
    """Mezcla una lista de elementos con «id» (proyectos, modelos…): lo que este proceso añadió, cambió o quitó desde
    la última vez que leyó el archivo, aplicado encima de lo que hay ahora en el disco (lo que añadió otro se respeta)."""
    b = {i["id"]: i for i in base}
    m = {i["id"]: i for i in mine}
    out = [i for i in disk if not (i["id"] in b and i["id"] not in m)]      # lo que se quitó aquí
    pos = {i["id"]: n for n, i in enumerate(out)}
    for i in mine:
        k = i["id"]
        if k not in b:                         # añadido aquí
            if k in pos:
                out[pos[k]] = i
            else:
                pos[k] = len(out)
                out.append(i)
        elif i != b[k] and k in pos:           # cambiado aquí (si otro lo quitó mientras tanto, se respeta)
            out[pos[k]] = i
    return out


class _FileLock:
    """Cerrojo entre procesos (otro Jayth, la ventana rápida, una tarea programada) para leer-mezclar-escribir los
    ajustes de una vez. Si no se consigue en unos segundos se sigue sin él: mejor guardar que perder el cambio."""

    def __init__(self, path, timeout=3.0):
        self.path, self.timeout, self.f, self.held = path, timeout, None, False

    def __enter__(self):
        try:
            self.f = open(self.path, "a+")
        except OSError:
            return self
        end = time.time() + self.timeout
        while True:
            try:
                if osys.WIN:
                    import msvcrt
                    self.f.seek(0)
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.held = True
                return self
            except OSError:
                if time.time() > end:
                    return self
                time.sleep(0.05)

    def __exit__(self, *a):
        if self.f:
            try:
                if self.held:
                    if osys.WIN:
                        import msvcrt
                        self.f.seek(0)
                        msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            self.f.close()
        return False


BACKUPS_KEPT = 10        # copias diarias de los ajustes en data/respaldos


class Settings:
    """Ajustes en data/settings.json.

    Varios procesos pueden tenerlos abiertos a la vez (dos ventanas de Jayth, la ventana rápida, una tarea programada).
    Antes cada uno escribía su copia entera en memoria y el último en guardar borraba lo que hubieran cambiado los demás
    (proyectos y modelos incluidos). Ahora cada guardado relee el archivo y aplica encima solo lo que cambió este proceso,
    y si otro proceso lo cambió, snapshot() lo recoge. Además se guarda una copia por día en data/respaldos."""

    def __init__(self):
        self.path = os.path.join(paths.DATA, "settings.json")
        self.lock = threading.Lock()
        self.v = dict(DEFAULTS)
        self.load_error = ""
        self.save_error = ""                   # último guardado fallido (la ventana lo avisa y se reintenta)
        self._extra = {}                       # claves de una versión más nueva de Jayth: se conservan al guardar
        self._base = _plain(self.v)            # lo que había en el disco la última vez que se leyó o se escribió
        self._sig = None
        self._checked = 0.0
        if os.path.isfile(self.path):
            for attempt in range(3):          # otro proceso podria estar escribiendolo en ese instante
                try:
                    with open(self.path, "r", encoding="utf-8-sig") as f:
                        disk = json.load(f)
                    self.v.update({k: x for k, x in disk.items() if k in DEFAULTS})
                    self._extra = {k: x for k, x in disk.items() if k not in DEFAULTS}
                    self._base = _plain(self.v)
                    self._sig = self._stat()
                    break
                except Exception as e:
                    if attempt == 2:
                        # no empezar de cero en silencio: conservar una copia del archivo danado
                        bak = self.path + ".danado-%d.json" % int(time.time())
                        try:
                            os.replace(self.path, bak)
                        except OSError:
                            pass
                        self.load_error = tr("No se pudieron leer tus ajustes (%s). Se guardó una copia en %s.") % (e, bak)
                    time.sleep(0.3)
        if not self.v.get("ctx_auto_migrated"):
            # antes el contexto era 16 000 fijo por defecto: pasa a automático (el máximo del modelo que quepa en memoria)
            if int(self.v.get("n_ctx") or 0) == 16384:
                self.v["n_ctx"] = 0
            self.v["ctx_auto_migrated"] = True
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

    # --- disco
    def _stat(self):
        try:
            st = os.stat(self.path)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _read_disk(self):
        try:
            with open(self.path, "r", encoding="utf-8-sig") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else None
        except (OSError, ValueError):
            return None

    def _mine(self):
        """Claves que este proceso cambió desde la última lectura/escritura del archivo."""
        return {k for k, x in self.v.items() if _plain(x) != self._base.get(k, object())}

    def _refresh(self):
        """Si otro proceso guardó los ajustes, recoger lo suyo (sin perder lo que este aún no guardó). Bajo self.lock."""
        now = time.monotonic()
        if now - self._checked < 1.0:
            return
        self._checked = now
        sig = self._stat()
        if sig is None or sig == self._sig:
            return
        disk = self._read_disk()
        if disk is None:
            return
        mine = self._mine()
        for k, x in disk.items():
            if k in DEFAULTS:
                if k not in mine:
                    self.v[k] = x
                    self._base[k] = _plain(x)
            else:
                self._extra[k] = x
        self._sig = sig

    def _backup(self):
        """Una copia por día del archivo tal como estaba antes de cambiarlo (data/respaldos/settings-AAAAMMDD.json)."""
        try:
            d = os.path.join(paths.DATA, "respaldos")
            dst = os.path.join(d, "settings-%s.json" % time.strftime("%Y%m%d"))
            if os.path.exists(dst) or not os.path.isfile(self.path):
                return
            os.makedirs(d, exist_ok=True)
            import shutil
            shutil.copy2(self.path, dst)
            old = sorted(f for f in os.listdir(d) if f.startswith("settings-") and f.endswith(".json"))
            for f in old[:-BACKUPS_KEPT]:
                os.remove(os.path.join(d, f))
        except OSError:
            pass

    def _write(self, data):
        text = json.dumps(data, indent=2, ensure_ascii=False)
        tmp = "%s.%d.tmp" % (self.path, os.getpid())      # uno por proceso: dos Jayth no escriben el mismo temporal
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        wait = 0.02
        for attempt in range(15):              # algo más de 2 s en total (se guarda desde la ventana: que no se congele)
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:
                # Windows: el antivirus, el indexador u otro programa pueden tener el archivo abierto un momento
                time.sleep(wait)
                wait = min(wait * 1.5, 0.2)
        try:                                   # último recurso: escribir encima (no es atómico, pero no se pierde el cambio)
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(text)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def _save(self):
        """Guarda bajo self.lock: relee el archivo, aplica encima lo que cambió este proceso y escribe el resultado.
        Nunca lanza la excepción a quien llamó (antes, en Windows, un archivo bloqueado hacía que el cambio se quedara
        solo en memoria sin avisar): si falla, queda en save_error, la ventana lo muestra y se reintenta solo."""
        try:
            with _FileLock(self.path + ".lock"):
                disk = self._read_disk() if os.path.isfile(self.path) else None
                cur = _plain(self.v)
                if disk is None:
                    merged = dict(self._extra, **cur)
                else:
                    merged = dict(disk)
                    for k, x in cur.items():
                        b = self._base.get(k, object())
                        if x == b and k in merged:
                            continue                       # no lo tocó este proceso: vale lo que haya en el disco
                        if _id_list(x) and _id_list(b) and _id_list(merged.get(k)):
                            merged[k] = _merge_ids(b, x, merged[k])
                        else:
                            merged[k] = x
                self._backup()
                self._write(merged)
                self.v.update({k: x for k, x in merged.items() if k in DEFAULTS})
                self._extra = {k: x for k, x in merged.items() if k not in DEFAULTS}
                self._base = _plain(self.v)
                self._sig = self._stat()
                self.save_error = ""
        except Exception as e:
            self.save_error = "%s: %s" % (type(e).__name__, e)
            try:
                with open(os.path.join(paths.DATA, "ajustes_errores.log"), "a", encoding="utf-8") as f:
                    f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), self.save_error))
            except OSError:
                pass

    def retry_save(self):
        """Vuelve a intentar un guardado que falló. Devuelve True si ya no queda nada pendiente."""
        with self.lock:
            if self.save_error:
                self._save()
            return not self.save_error

    def snapshot(self):
        with self.lock:
            self._refresh()
            v = dict(self.v)
        os.makedirs(v["workspace"], exist_ok=True)
        return v

    def ready(self):
        """True si hay un proveedor de modelo utilizable."""
        return not_ready(self.snapshot()) == ""

    def update_model(self, mid, **kw):
        """Cambia unos campos de un modelo de la lista (sin pisar lo que otro hilo haya cambiado en los demás)."""
        with self.lock:
            self.v["models"] = [dict(x, **kw) if x.get("id") == mid else x for x in self.v["models"]]
            self._save()

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
            self.v["projects_removed"] = (self.v.get("projects_removed") or [])[-200:] + [pid]
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


def not_ready(cfg):
    """Por qué no se puede usar todavía el modelo: "" (todo bien), "setup" (sin configurar), "no_model" (no hay
    ninguno elegido), "model_file" (su archivo no está donde se guardó) o "engine" (falta llama-server)."""
    if not cfg["setup_done"]:
        return "setup"
    if cfg["llm_mode"] == "external":
        return "" if cfg["external_url"] else "setup"
    m = active_model(cfg)
    if not m:
        return "no_model"
    from .relocate import files_ok
    if not files_ok(m):
        return "model_file"
    return "" if os.path.isfile(cfg["llama_exe"]) else "engine"


def models_dir(cfg=None):
    """Carpeta para las descargas nuevas: la elegida o, si su disco no está conectado, la predeterminada."""
    d = (cfg or SET.snapshot()).get("models_dir") or paths.MODELS_DEFAULT
    anchor = os.path.splitdrive(os.path.abspath(d))[0] or ""
    if osys.WIN and anchor and not os.path.isdir(anchor + "\\"):
        return paths.MODELS_DEFAULT
    from .relocate import _drive_of
    drv = "" if osys.WIN else _drive_of(d)
    return paths.MODELS_DEFAULT if drv and not os.path.isdir(drv) else d


def threads_batch(cfg):
    """Hilos para leer (procesar lo que le llega al modelo). Automático: con solo procesador, todos los hilos lógicos.
    Medido en un i5-8250U (4 núcleos, 8 hilos) con llama-bench: leer fue un 37-46 % más rápido con 8 hilos que con 4 en
    Gemma 4 E4B, gpt-oss-20b y Qwen 27B, mientras que escribir (que depende de la memoria) iba mejor con los 4 núcleos."""
    tb = int(cfg.get("threads_batch") or 0)
    if tb > 0:
        return tb
    t = int(cfg["threads"])
    if cfg.get("backend", "cpu") != "cpu":
        return t                                # con gráfica, leer lo hace ella
    return max(t, os.cpu_count() or t)


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


# ---------------------------------------------------------------- qué sabe hacer un modelo instalado
def _file_sig(path):
    try:
        st = os.stat(path)
        return "%d-%d" % (st.st_size, int(st.st_mtime))
    except OSError:
        return ""


def read_caps(m):
    """Lee del propio GGUF (sin internet) si el modelo usa herramientas y si razona; la visión depende de que tenga
    instalado su proyector (mmproj). Tarda ~1-2 s por el vocabulario: el resultado se guarda en el modelo."""
    from . import gguf, provision as P
    path = m.get("path", "")
    caps = {"sig": _file_sig(path), "v": CAPS_V, "vision": bool(m.get("mmproj") and os.path.isfile(m["mmproj"]))}
    try:
        meta = gguf.read_meta(path)      # completo: los datos de capas compartidas o por ventana pueden ir tras la plantilla
        tpl = str(meta.get("tokenizer.chat_template") or "")
        caps.update(tools=bool(P._TOOLS_TPL.search(tpl)) if tpl else bool(P._TOOLS_NAME.search(m.get("repo") or path)),
                    think=bool(P._THINK_TPL.search(tpl)) if tpl else False, arch=str(meta.get("general.architecture") or ""),
                    ctx=next((int(v) for k, v in meta.items() if k.endswith(".context_length") and isinstance(v, int)), 0),
                    kv=_kv_elems(meta), source="gguf")
    except (OSError, ValueError):
        name = m.get("repo") or path                      # archivo ilegible o ausente: se deduce del nombre
        caps.update(tools=bool(P._TOOLS_NAME.search(name)), think=False, arch="", ctx=0, kv=0, source="nombre")
    return caps


# capas con atención por ventana cuando el GGUF no trae el patrón: 1 de cada N tiene atención completa
_SWA_EVERY = {"gemma2": 2, "gemma3": 6, "gpt-oss": 2, "cohere2": 4}


def _swa_layers(meta, layers):
    """[True si la capa usa atención por ventana] (esas capas guardan solo la ventana: no crecen con el contexto)."""
    def g(suffix):
        return next((v for k, v in meta.items() if k.endswith(suffix)), None)
    win, pat = g(".attention.sliding_window"), g(".attention.sliding_window_pattern")
    if not isinstance(win, int) or win <= 0:
        return None
    if isinstance(pat, list) and pat:
        return [bool(x) for x in pat]
    every = pat if isinstance(pat, int) and pat > 1 else _SWA_EVERY.get(str(meta.get("general.architecture") or ""))
    return [(i + 1) % every != 0 for i in range(layers)] if every else None


def _kv_elems(meta):
    """Valores de la caché de atención por cada token de contexto: capas × cabezas KV × (dim. de clave + de valor).
    Solo cuentan las capas cuya caché crece con el contexto: las que reutilizan la caché de otras (Gemma 3n/4) no
    guardan nada propio, y las de atención por ventana (Gemma, gpt-oss…) guardan solo su ventana. Medido con Gemma 4
    E4B: 42 capas, pero solo 4 crecen con el contexto (~1 GB a 64k, no 11). Lo que no se sabe se calcula por lo alto."""
    def g(suffix):
        return next((v for k, v in meta.items() if k.endswith(suffix)), None)
    layers, heads, embd = g(".block_count"), g(".attention.head_count"), g(".embedding_length")
    kvh = g(".attention.head_count_kv")
    if not isinstance(layers, int) or not layers:
        return 0
    extra = g(".nextn_predict_layers")              # capas de predicción múltiple (MTP): el motor no les reserva caché
    if isinstance(extra, int) and 0 < extra < layers:
        layers -= extra
    shared = g(".attention.shared_kv_layers")       # las últimas capas reutilizan la caché de las anteriores
    own = layers - shared if isinstance(shared, int) and 0 < shared < layers else layers
    if isinstance(heads, list):
        heads = max(heads) if heads else 0
    head_dim = (embd // heads) if isinstance(embd, int) and isinstance(heads, int) and heads else 128
    k, v = g(".attention.key_length") or head_dim, g(".attention.value_length") or head_dim
    if isinstance(kvh, list):                         # cabezas por capa (las capas sin atención llevan 0)
        per_layer = [int(x) for x in kvh[:own]]
    else:
        # modelos híbridos (p. ej. Qwen3.5/Qwen3-Next): solo 1 de cada N capas tiene atención; las demás guardan un
        # estado fijo que no crece con el contexto
        every = g(".full_attention_interval")
        if isinstance(every, int) and every > 1:
            return int(-(-own // every) * int(kvh or heads or 8) * (int(k) + int(v)))
        per_layer = [int(kvh or heads or 8)] * own
    swa = _swa_layers(meta, layers)
    if swa and not all(swa[:own]):                    # con al menos una capa completa, las de ventana no cuentan
        per_layer = [h for i, h in enumerate(per_layer) if not (i < len(swa) and swa[i])]
    return int(sum(per_layer) * (int(k) + int(v)))


CAPS_V = 3                      # sube al cambiar cómo se calcula «kv»: las capacidades guardadas se vuelven a leer


CTX_FLOOR = 16384               # lo que se usaba antes por defecto: el automático nunca baja de aquí (si el modelo llega)
_KV_BYTES = {"f16": 2.0, "q8_0": 34 / 32, "q4_0": 18 / 32}
_HW = []


def _hardware():
    if not _HW:
        from . import hardware as HW
        try:
            _HW.append(HW.detect())
        except Exception:
            _HW.append({"ram": 8 << 30, "vram": 0})
    return _HW[0]


def effective_ctx(cfg, m=None):
    """Contexto con el que se enciende el modelo. Con n_ctx > 0 es ese número; con 0 (automático) es el máximo que admite
    el modelo de fábrica, reducido si su caché no cabe en la memoria del equipo (nunca por debajo de CTX_FLOOR)."""
    n = int(cfg.get("n_ctx") or 0)
    if n > 0:
        return n
    if cfg.get("llm_mode") == "external":
        return CTX_FLOOR                                 # el servidor externo decide su propio contexto
    m = m or active_model(cfg)
    c = model_caps(m) if m else None
    native = int((c or {}).get("ctx") or 0) or 32768
    kv = int((c or {}).get("kv") or 0) * _KV_BYTES.get(cfg.get("cache_type", "f16"), 2.0)
    if not kv:
        return min(native, CTX_FLOOR * 2)
    # medido con llama.cpp (Qwen3.5 27B en CPU): la caché crece exactamente kv bytes por token, el búfer de cálculo unos
    # 2 KB más por token y hay ~0,5 GB fijos (cálculo y estado de las capas recurrentes)
    per_token = kv + 2048
    hw = _hardware()
    GB = 1 << 30
    used = GB // 2
    for p in ((m or {}).get("path"), (m or {}).get("mmproj") if cfg.get("vision", True) else None):
        try:
            used += os.path.getsize(p) if p else 0
        except OSError:
            pass
    ram = hw.get("ram", 0)
    reserve = max(4 * GB, ram * 0.2)                 # para el sistema y los demás programas abiertos
    free = ram + max(0, hw.get("vram", 0) - GB) - used - reserve
    fits = int(free / per_token) if free > 0 else 0
    ctx = min(native, max(min(native, CTX_FLOOR), fits))
    return max(2048, ctx // 1024 * 1024)


def memory_plan(cfg, m=None):
    """Memoria del modelo activo en este equipo: {'need', 'room', 'level', 'cache_mib'}.
    need: pesos (+ proyector de visión) + caché del contexto + ~0,5 GB. level: 'ok'; 'tight' (cabe cerrando otros
    programas) o 'no' (no cabe: lee del disco y escribe muy despacio). cache_mib: RAM que puede usar llama-server para
    recordar conversaciones anteriores (--cache-ram, 8 GB por defecto) sin quitársela al propio modelo."""
    m = m or active_model(cfg)
    if not m or cfg.get("llm_mode") == "external":
        return {"level": "ok", "cache_mib": None, "need": 0, "room": 0}
    GB = 1 << 30
    c = model_caps(m, compute=False) or {}
    kv = int(c.get("kv") or 0) * _KV_BYTES.get(cfg.get("cache_type", "f16"), 2.0)
    need = GB // 2 + (kv + 2048) * effective_ctx(cfg, m) if kv else GB
    for p in (m.get("path"), m.get("mmproj") if cfg.get("vision", True) else None):
        try:
            need += os.path.getsize(p) if p else 0
        except OSError:
            pass
    hw = _hardware()
    ram = hw.get("ram", 0)
    gpu = max(0, hw.get("vram", 0) - GB) if cfg.get("backend") in ("cuda", "vulkan", "metal") else 0
    room = ram + gpu
    reserve = max(4 * GB, ram * 0.2)
    level = "ok" if need <= room - reserve else "tight" if need <= room - 1.5 * GB else "no"
    try:                                            # memoria libre ahora mismo (con el modelo aún apagado)
        from . import hardware as HW
        free = HW.ram()[1] + gpu
    except Exception:
        free = 0
    if level == "ok" and free and not LLM_MGR.mine() and need > free + GB // 2:
        level = "busy"                              # cabe en el equipo, pero ahora otros programas ocupan la memoria
    spare = (room - reserve - need) / (1 << 20)
    return {"need": int(need), "room": int(room), "free": int(free), "level": level,
            # nunca 0: con modelos de atención por ventana (Gemma, gpt-oss) llama.cpp no reutiliza la caché entre pasos sin
            # ella y relee toda la conversación cada vez. Es un tope, no una reserva: solo se usa si hace falta.
            "cache_mib": int(min(8192, max(512, spare)))}


def model_caps(m, compute=True):
    """Capacidades guardadas del modelo; si faltan o el archivo cambió, se leen (compute=False: solo lo guardado)."""
    if not m:
        return None
    c = m.get("caps")
    if c and c.get("sig") == _file_sig(m.get("path", "")) and c.get("v") == CAPS_V and ("kv" in c or not compute):
        c = dict(c)
        c["vision"] = bool(m.get("mmproj") and os.path.isfile(m["mmproj"]))     # el proyector se puede añadir o quitar luego
        return c
    if not compute:
        return None
    c = read_caps(m)
    SET.update_model(m.get("id"), caps=c)
    return c


def caps_text(c, short=False):
    """«Agente · Visión · Razona» (o «Solo conversación» si no usa herramientas)."""
    if not c:
        return ""
    parts = ([tr("Agente")] if c.get("tools") else []) + ([tr("Visión")] if c.get("vision") else []) + ([tr("Razona")] if c.get("think") else [])
    if not c.get("tools"):
        parts.insert(0, tr("Solo conversación") if not short else tr("Sin herramientas"))
    return " · ".join(parts)


EFFORTS = [("low", tr("Bajo"), tr("Responde directo, sin razonar antes. Lo más rápido.")),
           ("medium", tr("Medio"), tr("Razona antes de responder. Mejor en tareas con varios pasos.")),
           ("high", tr("Alto"), tr("Razona a fondo y con más margen de respuesta. Para lo difícil; es lo más lento."))]


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
DEFAULT_TITLE = tr("Nueva conversación")
# el título se guarda en disco: una conversación aún vacía pudo crearse con la interfaz en otro idioma
DEFAULT_TITLES = {DEFAULT_TITLE, "Nueva conversación", "New conversation", "Nova conversa"}


class Session:
    def __init__(self, sid, title=DEFAULT_TITLE, created=None, data=None):
        self.id, self.title, self.created = sid, title, created or time.time()
        self.data = data or {"messages": [], "allowed": []}
        self.events = []
        self.cond = threading.Condition()
        self.run = None
        self.updated = self.created
        self.temp = False            # chat temporal: no se guarda en disco, no usa ni escribe la memoria
        self.leftover = []           # mensajes en cola que el agente no llegó a ver
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
                # el chat temporal vive solo en memoria; los avisos de avance en directo tampoco se guardan
                if not self.temp and ev["t"] not in ("reading", "quiet"):
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

    def send(self, text, images=(), files=(), mode=None, attach_text=None, marker=None):
        """Lanza el agente en un hilo. files: rutas de documentos adjuntos (su texto se incluye en el mensaje);
        attach_text: el texto de los adjuntos ya preparado (al reenviar un mensaje anterior). Devuelve None o un mensaje de error."""
        if self.run is not None:
            return tr("El agente sigue trabajando en esta conversación.")
        cfg = self._run_cfg(mode)
        attach = attach_text if attach_text is not None else attachments_text(files)
        if cfg["mode"] == "plan":
            self.data["plan"] = []
        run = A.Run(self.data, cfg, self.add_event, paths.IMG_DIR)
        self.run = run
        if self.title in DEFAULT_TITLES:
            # titulo provisional; al terminar la primera respuesta el propio modelo propone uno breve
            t = re.sub(r"\s+", " ", text or tr("Archivo adjunto")).strip()
            if len(t) > 48:                      # cortado en una palabra entera y con «…» (no «…de la carpeta de trab»)
                cut = t[:48].rsplit(" ", 1)[0] if " " in t[:48] else t[:47]
                t = cut.rstrip(" ,.;:") + "…"
            self.title = t
            self.data["title_auto"] = 2          # intentos que quedan

        def go():
            try:
                run.run(text or "(adjuntos)", list(images), attach, marker)
            finally:
                # lo que escribiste mientras trabajaba y no llegó a ver (lo detuviste, hubo un error): vuelve al cuadro de texto
                self.leftover = [i["text"] for i in run.queued()]
                self.run = None
                self.save()
            self._auto_title(cfg)
        threading.Thread(target=go, daemon=True).start()
        return None

    def compact(self):
        """«Resumir ahora»: el modelo resume lo antiguo de la conversación para liberar memoria. None o un error."""
        if self.run is not None:
            return tr("El agente sigue trabajando en esta conversación.")
        run = A.Run(self.data, self._run_cfg(), self.add_event, paths.IMG_DIR)
        self.run = run

        def go():
            try:
                run.compact_now()
            finally:
                self.run = None
                self.save()
        threading.Thread(target=go, daemon=True).start()
        return None

    def _run_cfg(self, mode=None):
        """Ajustes con los que trabaja el agente en esta conversación (proyecto, asistente, contexto real…)."""
        cfg = SET.snapshot()
        if mode:
            cfg["mode"] = mode
        proj = project(cfg, self.data.get("project"))
        if proj:   # en un proyecto el agente trabaja dentro de su carpeta y sigue sus instrucciones
            self.data["project_info"] = _project_info(proj)     # para recuperarlo si se pierde de la lista
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
        cfg["n_ctx"] = effective_ctx(cfg)        # el agente mide la conversación con el contexto real (también en automático)
        cfg["_before_llm"] = LLM_MGR.yield_warm  # un mensaje real no espera detrás del precalentamiento
        cfg["_model_title"] = model_title(active_model(cfg)) if cfg["llm_mode"] == "local" else (cfg.get("external_model") or "")
        return cfg

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

    def steer(self, text):
        """Mensaje escrito mientras el agente trabaja: lo verá en su próximo paso. Devuelve su id (o None si ya terminó)."""
        run = self.run
        return run.queue(text) if run is not None else None

    def unsteer(self, qid):
        run = self.run
        return bool(run and run.unqueue(qid))

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

    def undo_file(self, path, cids):
        """Devuelve un archivo a como estaba antes de las acciones cids (las de una respuesta). Devuelve las rutas restauradas."""
        from . import harness
        if self.run is not None:
            return None
        done, emptied = harness.undo_file(self.id, cids, path)
        if done:
            self.add_event({"t": "undo", "ids": emptied, "files": [done]})
            self._note("el usuario deshizo tus cambios en: %s" % done)
            self.save()
        return [done] if done else []

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
            return tr("El agente sigue trabajando en esta conversación.")
        ev = self.last_user()
        if not ev:
            return tr("No hay ningún mensaje que regenerar.")
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
        return self.send(ev["text"], ev.get("images") or [], marker=ev.get("marker"))

    # ---- volver a un mensaje anterior (editar, reintentar, rebobinar, ramificar)
    def _rewrite_events(self):
        try:
            if not self.temp:
                with open(self.epath, "w", encoding="utf-8") as f:
                    for e in self.events:
                        f.write(json.dumps(e, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _user_event(self, ev_i):
        if not (0 <= ev_i < len(self.events)) or self.events[ev_i]["t"] != "user":
            raise ValueError(tr("Ese mensaje ya no está en la conversación."))
        return self.events[ev_i]

    def _user_msg_index(self, ev_i):
        """Posición en data['messages'] del mensaje del usuario del evento ev_i, contando desde el final (los mensajes
        antiguos pueden estar resumidos). None si ese mensaje ya forma parte del resumen."""
        k = sum(1 for e in self.events[ev_i:] if e["t"] == "user")
        msgs, n = self.data["messages"], 0
        for idx in range(len(msgs) - 1, -1, -1):
            if msgs[idx]["role"] == "user" and not msgs[idx].get("_auto"):
                n += 1
                if n == k:
                    return idx
        return None

    def changes_since(self, ev_i):
        """Acciones del agente desde el evento ev_i cuyos cambios de archivos aún se pueden deshacer."""
        from . import harness
        return [e["id"] for e in self.events[ev_i:] if e["t"] == "tool_result" and e.get("undo") and harness.has_snapshot(self.id, e["id"])]

    def rewind(self, ev_i, undo_files=True):
        """Vuelve al momento justo antes del mensaje del usuario ev_i: lo quita junto con todo lo que vino después y, si
        undo_files, deshace los cambios de archivos que hizo el agente desde entonces.
        Devuelve (mensaje, archivos restaurados); mensaje = {text, images, files, attach}. Lanza ValueError si no se puede."""
        if self.run is not None:
            raise ValueError(tr("El agente sigue trabajando en esta conversación."))
        ev = self._user_event(ev_i)
        idx = self._user_msg_index(ev_i)
        if idx is None:
            raise ValueError(tr("Ese mensaje ya forma parte del resumen de la conversación: no puedo volver a ese punto."))
        files = []
        if undo_files:
            from . import harness
            for cid in reversed(self.changes_since(ev_i)):
                files += harness.undo(self.id, cid)
        content = self.data["messages"][idx].get("content")
        body = content if isinstance(content, str) else next((c.get("text", "") for c in content or [] if c.get("type") == "text"), "")
        text = ev.get("text") or ""
        attach = body[len(text):].lstrip("\n") if body.startswith(text) else ""
        del self.data["messages"][idx:]
        with self.cond:
            del self.events[ev_i:]
            self._rewrite_events()
        self.updated = time.time()
        self.save()
        return {"text": text, "images": list(ev.get("images") or []), "files": list(ev.get("files") or []), "attach": attach}, sorted(set(files))

    def resend(self, ev_i, text=None, undo_files=True):
        """Reintentar (text=None) o editar y reenviar un mensaje anterior: vuelve a ese punto y lo envía otra vez,
        con sus imágenes y adjuntos. Devuelve (error o None, archivos restaurados)."""
        old, files = self.rewind(ev_i, undo_files)
        new = old["text"] if text is None else text
        return self.send(new, old["images"], attach_text=old["attach"]), files

    def fork(self, ev_i):
        """Conversación nueva con todo lo anterior al mensaje ev_i (para probar otro camino sin perder este).
        Devuelve (sesión nueva, texto de ese mensaje)."""
        import copy
        ev = self._user_event(ev_i)
        idx = self._user_msg_index(ev_i)
        if idx is None:
            raise ValueError(tr("Ese mensaje ya forma parte del resumen de la conversación: no puedo volver a ese punto."))
        ns = new_session(self.data.get("project"), temp=self.temp)
        for k in ("assistant", "allowed"):
            if k in self.data:
                ns.data[k] = copy.deepcopy(self.data[k])
        ns.data["messages"] = copy.deepcopy(self.data["messages"][:idx])
        ns.title = (tr("%s (rama)") % self.title)[:80]
        ns.data["title_auto"] = None
        with ns.cond:
            ns.events = [dict(e) for e in self.events[:ev_i]]
            ns._rewrite_events()
        ns.save()
        return ns, ev.get("text") or ""

    def hide_event(self, ev_i):
        """Quita de la vista un aviso (p. ej. un error ya resuelto); queda marcado como oculto en el historial."""
        with self.cond:
            if 0 <= ev_i < len(self.events):
                self.events[ev_i]["hidden"] = True
                self._rewrite_events()

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
        p = project(SET.snapshot(), project_id)
        if p:
            s.data["project_info"] = _project_info(p)
    SESSIONS[s.id] = s
    s.save()
    return s


def project(cfg, pid):
    for p in cfg.get("projects", []):
        if pid and p["id"] == pid:
            return p
    return None


def _project_info(p):
    return {"name": p.get("name", ""), "path": p.get("path", ""), "instructions": p.get("instructions", ""),
            "created": p.get("created") or 0}


def recover_projects():
    """Proyectos que tienen conversaciones pero ya no están en la lista (p. ej. ajustes pisados por otra copia de Jayth
    abierta a la vez): vuelven solos con su mismo id si su carpeta sigue existiendo. Los que el usuario quitó a propósito
    no. Devuelve los nombres recuperados."""
    cfg = SET.snapshot()
    projs = {p["id"]: p for p in cfg["projects"]}
    for s in list(SESSIONS.values()):        # conversaciones de antes de esto: se les anota su proyecto una vez
        p = projs.get(s.data.get("project"))
        if p and not s.temp and s.data.get("project_info") != _project_info(p):
            s.data["project_info"] = _project_info(p)
            s.save()
    have = set(projs) | set(cfg.get("projects_removed") or [])
    found = {}
    for s in sorted(SESSIONS.values(), key=lambda s: s.created):
        pid, info = s.data.get("project"), s.data.get("project_info") or {}
        if not pid or pid in have or pid in found or s.temp:
            continue
        path = info.get("path") or ""
        if path and os.path.isdir(path):
            found[pid] = {"id": pid, "name": info.get("name") or os.path.basename(path), "path": os.path.normpath(path),
                          "instructions": info.get("instructions", ""), "created": info.get("created") or s.created}
    if found:
        with SET.lock:
            SET.v["projects"] = SET.v["projects"] + [p for k, p in found.items() if k not in {x["id"] for x in SET.v["projects"]}]
            SET._save()
        for s in list(SESSIONS.values()):    # las demás conversaciones de esos proyectos también quedan anotadas
            p = found.get(s.data.get("project"))
            if p and not s.temp and s.data.get("project_info") != _project_info(p):
                s.data["project_info"] = _project_info(p)
                s.save()
    return [p["name"] for p in found.values()]


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
            return {"state": "off", "error": tr("El modelo se cerró (código %s). Revisa el registro.") % self.proc.poll()}
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
                return {"state": "off", "external": True, "error": tr("El servicio rechazó la clave de API (HTTP %d).") % e.code}
            return {"state": "ready", "external": True}      # contesta, aunque no ofrezca la lista de modelos
        except Exception as e:
            return {"state": "off", "external": True, "error": tr("Servidor externo no disponible")}

    def command(self, cfg=None):
        cfg = cfg or SET.snapshot()
        m = active_model(cfg) or {}
        cmd = [cfg["llama_exe"], "-m", m.get("path", ""), "--host", "127.0.0.1", "--port", str(cfg["llm_port"]),
               "-t", str(cfg["threads"]), "-c", str(effective_ctx(cfg, m)), "--jinja", "--no-warmup",
               "-np", "1",                       # una sola ranura: todo el contexto disponible y la cache de prompt siempre se reutiliza
               "-b", str(cfg["batch_size"])]
        tb = threads_batch(cfg)
        if tb != int(cfg["threads"]):
            cmd += ["-tb", str(tb)]             # leer (cálculo) aprovecha todos los hilos; escribir (memoria), los núcleos físicos
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
        try:                                    # decodificación especulativa (MTP, n-gramas) si el ajuste medido la eligió
            from . import ajuste
            sp = ajuste.spec_for(cfg, m)
            if sp:
                cmd += ["--spec-type", sp]
            # la caché de conversaciones anteriores (8 GB por defecto) no debe quitarle memoria al propio modelo
            if ajuste.engine_caps(cfg["llama_exe"]).get("cram"):
                cram = memory_plan(cfg, m).get("cache_mib")
                if cram is not None:
                    cmd += ["--cache-ram", str(cram)]
        except Exception:
            pass
        return cmd

    # --- precalentamiento: procesa una vez las instrucciones y herramientas fijas para que el primer mensaje sea rapido
    warm = ""          # "" | "warming" | "warm"

    _warm_sock = None

    def warmup(self, session=None):
        """Lee por adelantado las instrucciones y herramientas. Con `session` (la conversación abierta) usa las suyas:
        en un proyecto las instrucciones empiezan por su carpeta, y precalentar las generales no servía de nada (el
        motor volvía a leerlo todo, minutos en un equipo sin gráfica)."""
        if self.warm:
            return
        self.warm = "warming"
        try:
            cfg = session._run_cfg() if session is not None else SET.snapshot()
            groups = list((session.data.get("tool_groups") or []) if session is not None else [])
            payload = {"model": "local", "stream": False, "max_tokens": 1, "cache_prompt": True, "temperature": 0,
                       "messages": [{"role": "system", "content": A.system_prompt(cfg)}, {"role": "user", "content": "hola"}],
                       "tools": A.tool_schemas(cfg, groups), "chat_template_kwargs": {"enable_thinking": effort_of(cfg) != "low",
                                                                                       "reasoning_effort": effort_of(cfg)}}
            c = http.client.HTTPConnection("127.0.0.1", int(cfg["llm_port"]), timeout=10)
            c.connect()
            c.sock.settimeout(None)
            self._warm_sock = c.sock
            c.request("POST", "/v1/chat/completions", json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json"})
            # la respuesta llega cuando el motor termina de leer. Se espera a trozos cortos para poder ceder el paso:
            # cerrar el enchufe desde otro hilo no despierta en Windows una lectura bloqueada
            import socket
            c.sock.settimeout(0.5)
            while not self._warm_yielded:
                try:
                    c.sock.recv(65536)           # cualquier dato (o el cierre) = el motor ya contestó
                    break
                except socket.timeout:
                    continue
            c.close()                            # si se cedió el paso, al cerrar el motor abandona la lectura
            self.warm = "warm"
        except Exception:
            # falló o se le cedió el paso a un mensaje real (yield_warm): ese mensaje ya deja leído lo suyo
            self.warm = "warm" if self._warm_yielded else ""
        finally:
            self._warm_sock = None

    _warm_yielded = False

    def yield_warm(self):
        """Llega un mensaje de verdad mientras se precalienta: se corta el precalentamiento para que el mensaje no espere
        detrás (el motor atiende una petición cada vez) y el chat muestre su avance desde el primer momento. Lo que el
        motor ya había leído sigue en su memoria y se reutiliza si coincide."""
        if self.warm == "warming" and self._warm_sock is not None:
            self._warm_yielded = True            # el hilo del precalentamiento lo ve enseguida y cierra su conexión
            for _ in range(40):                  # se le da un momento (hasta 2 s) para que el motor quede libre
                if self.warm != "warming":
                    break
                time.sleep(0.05)
            return True
        return False

    def start(self):
        cfg = SET.snapshot()
        if cfg["llm_mode"] == "external":
            return tr("Estás usando un servidor externo; enciéndelo desde ese programa.")
        if self.status()["state"] != "off":
            return None
        m = active_model(cfg)
        if not m:
            return tr("No hay ningún modelo elegido. Añade uno en «Modelos».")
        from . import relocate
        if not relocate.files_ok(m) or (m.get("mmproj") and not os.path.isfile(m["mmproj"])):
            relocate.run("guess")                   # ¿se movió? primero los sitios evidentes (es instantáneo)
            cfg = SET.snapshot()
            m = active_model(cfg)
        if not relocate.files_ok(m):
            return (tr("No encuentro el archivo del modelo «%s» (%s). Si lo moviste de carpeta o de disco, Jayth lo busca solo; "
                    "también puedes indicarle dónde está en Modelos → Localizar…") % (model_title(m) or m.get("name"), m.get("path") or tr("sin ruta")))
        if not cfg["llama_exe"] or not os.path.isfile(cfg["llama_exe"]):
            return tr("No encuentro llama-server (%s). Abre el asistente de configuración.") % (cfg["llama_exe"] or tr("sin configurar"))
        have = os.path.getsize(m["path"])
        if m.get("size") and have < int(m["size"]) and not re.search(r"-\d{5}-of-\d{5}\.gguf$", m["path"]):
            return tr("El archivo del modelo aún está incompleto (%s de %s). Espera a que termine la descarga.") % (i18n.size(have), i18n.size(int(m["size"])))
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
