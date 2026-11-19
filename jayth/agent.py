"""Bucle del agente: habla con llama-server (API OpenAI), ejecuta herramientas y pide aprobacion."""
import os, re, json, time, uuid, base64, socket, threading, datetime, http.client, urllib.parse
from . import tools as T

MODES = {
    "readonly": "Solo lectura: no puede escribir, ejecutar ni usar la red.",
    "ask": "Preguntar: lee solo; todo lo demás pide tu aprobación.",
    "edits": "Editar archivos: escribe libremente; ejecutar, red y control piden aprobación.",
    "auto": "Automático: hace todo sin preguntar (salvo acciones peligrosas).",
}


class LLMError(Exception):
    pass


def system_prompt(settings):
    p = """Eres un agente que trabaja en el ordenador local del usuario (Windows 11, PowerShell). Hoy es %s.
Carpeta de trabajo: %s
Reglas:
- Usa las herramientas para actuar; nunca inventes resultados ni rutas. Da pasos cortos y comprueba cada resultado.
- Lee un archivo antes de editarlo; para cambios pequeños usa edit_file.
- run_command ejecuta PowerShell. Python está disponible como `python`.
- Para programas con interfaz: screenshot -> actuar (click, type_text, press_keys) -> screenshot para verificar. Las coordenadas son píxeles de la última captura.
- web_search y web_fetch solo funcionan con internet; si fallan, dilo y continúa sin ellos.
- Si el usuario deniega una acción, no insistas: propón otra vía o pregunta.
- Responde en el idioma del usuario, de forma breve. Al terminar, resume qué hiciste y dónde quedaron los archivos.""" % (
        datetime.date.today().isoformat(), settings["workspace"])
    if settings.get("custom_instructions"):
        p += "\n\nInstrucciones del usuario:\n" + settings["custom_instructions"]
    return p


def coerce(args, schema):
    props = (schema or {}).get("properties", {})
    out = {}
    for k, v in args.items():
        t = props.get(k, {}).get("type")
        try:
            if t == "integer" and not isinstance(v, bool):
                v = int(float(v))
            elif t == "boolean" and isinstance(v, str):
                v = v.strip().lower() in ("true", "1", "yes", "si", "sí")
        except (TypeError, ValueError):
            pass
        out[k] = v
    return out


def parse_text_tool_calls(text):
    """Respaldo: algunos modelos escriben la llamada como texto <tool_call>...</tool_call>."""
    calls = []
    for m in re.finditer(r"<tool_call>(.*?)</tool_call>", text, re.S):
        body = m.group(1).strip()
        name, args = None, {}
        try:
            j = json.loads(body)
            name, args = j.get("name"), j.get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args)
        except Exception:
            fm = re.search(r"<function=([^>\s]+)>(.*?)</function>", body, re.S)
            if fm:
                name = fm.group(1)
                for pm in re.finditer(r"<parameter=([^>\s]+)>\n?(.*?)\n?</parameter>", fm.group(2), re.S):
                    args[pm.group(1)] = pm.group(2)
        if name:
            calls.append({"id": "call_" + uuid.uuid4().hex[:8], "type": "function", "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}})
    cleaned = re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.S).strip()
    return calls, cleaned


def llm_stream(base_url, api_key, payload, holder, on_delta):
    """Llama a una API compatible con OpenAI (base_url termina en /v1) con streaming.
    holder['conn'] permite cortar la conexion desde otro hilo."""
    u = urllib.parse.urlparse(base_url)
    cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
    conn = cls(u.hostname, u.port or (443 if u.scheme == "https" else 80), timeout=10)
    holder["conn"] = conn
    try:
        conn.connect()
        conn.sock.settimeout(None)
        conn.request("POST", u.path.rstrip("/") + "/chat/completions", json.dumps(payload).encode("utf-8"),
                     {"Content-Type": "application/json", "Authorization": "Bearer " + (api_key or "local"), "Accept": "text/event-stream"})
        resp = conn.getresponse()
        if resp.status != 200:
            raise LLMError("HTTP %d: %s" % (resp.status, resp.read(2000).decode("utf-8", "replace")))
        content, reasoning, tcs, finish, timings, usage = [], [], {}, None, None, None
        while True:
            line = resp.readline()
            if not line:
                break
            line = line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                ch = json.loads(data)
            except ValueError:
                continue
            if ch.get("timings"):
                timings = ch["timings"]
            if ch.get("usage"):
                usage = ch["usage"]
            for c in ch.get("choices") or []:
                d = c.get("delta") or {}
                if d.get("reasoning_content"):
                    reasoning.append(d["reasoning_content"])
                    on_delta("reasoning", d["reasoning_content"])
                if d.get("content"):
                    content.append(d["content"])
                    on_delta("content", d["content"])
                for tc in d.get("tool_calls") or []:
                    slot = tcs.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    f = tc.get("function") or {}
                    if f.get("name"):
                        slot["name"] += f["name"]
                    if f.get("arguments"):
                        slot["args"] += f["arguments"]
                if c.get("finish_reason"):
                    finish = c["finish_reason"]
        return {"content": "".join(content), "reasoning": "".join(reasoning), "tool_calls": [tcs[k] for k in sorted(tcs)],
                "finish": finish, "timings": timings, "usage": usage}
    finally:
        try:
            conn.close()
        except Exception:
            pass
        holder["conn"] = None


class Run:
    def __init__(self, session, settings, emit, images_dir):
        self.s = session            # dict con 'messages' y 'allowed'
        self.cfg = settings
        self.emit = emit
        self.images_dir = images_dir
        self.stop = threading.Event()
        self.pending = {}           # tool_call_id -> {event, decision}
        self.holder = {}
        self.ctx = T.Ctx(settings["workspace"], self.stop, images_dir, int(settings["max_tool_output"]), {"brave_key": settings.get("brave_key")})
        self._buf, self._last = {"kind": None, "text": ""}, 0.0

    # ---- control externo
    def request_stop(self):
        self.stop.set()
        c = self.holder.get("conn")
        if c is not None:
            try:
                c.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                c.close()
            except Exception:
                pass
        for p in self.pending.values():
            p["event"].set()

    def resolve(self, call_id, decision):
        p = self.pending.get(call_id)
        if p:
            p["decision"] = decision
            p["event"].set()
            return True
        return False

    # ---- salida de texto con agrupacion de deltas
    def _delta(self, kind, text):
        b = self._buf
        if b["kind"] not in (None, kind):
            self._flush()
        b["kind"] = kind
        b["text"] += text
        if time.time() - self._last > 0.12:
            self._flush()

    def _flush(self):
        b = self._buf
        if b["text"]:
            self.emit({"t": "delta", "kind": b["kind"], "text": b["text"]})
        b["kind"], b["text"], self._last = None, "", time.time()

    # ---- contexto
    def _estimate(self, msgs):
        n = 0
        for m in msgs:
            c = m.get("content")
            if isinstance(c, list):
                for p in c:
                    n += 700 if p.get("type") == "image_url" else len(p.get("text", "")) / 3
            else:
                n += len(c or "") / 3
            if m.get("tool_calls"):
                n += len(json.dumps(m["tool_calls"], ensure_ascii=False)) / 3
            n += 6
        return n

    def _to_llm(self):
        msgs = self.s["messages"]
        refs = [(i, j) for i, m in enumerate(msgs) if isinstance(m.get("content"), list)
                for j, p in enumerate(m["content"]) if p.get("type") == "image_ref"]
        keep = set(refs[-int(self.cfg["keep_images"]):]) if self.cfg.get("vision") and self.cfg["keep_images"] else set()
        out = []
        for i, m in enumerate(msgs):
            c = m.get("content")
            if isinstance(c, list):
                parts = []
                for j, p in enumerate(c):
                    if p.get("type") != "image_ref":
                        parts.append(p)
                    elif (i, j) in keep and os.path.isfile(os.path.join(self.images_dir, p["name"])):
                        with open(os.path.join(self.images_dir, p["name"]), "rb") as f:
                            b64 = base64.b64encode(f.read()).decode()
                        ext = os.path.splitext(p["name"])[1].lower()
                        mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "image/png")
                        parts.append({"type": "image_url", "image_url": {"url": "data:%s;base64,%s" % (mime, b64)}})
                    else:
                        parts.append({"type": "text", "text": "[imagen anterior omitida para ahorrar contexto]"})
                m = dict(m, content=parts)
            out.append({k: v for k, v in m.items() if not k.startswith("_")})   # claves internas (_auto) no van al modelo
        return out

    def _fit(self, msgs):
        budget = int(self.cfg["n_ctx"]) - int(self.cfg["max_tokens"]) - 1500   # margen para el sistema y herramientas
        if self._estimate(msgs) <= budget:
            return msgs
        msgs = [dict(m) for m in msgs]
        for m in msgs:                                    # 1) recortar salidas antiguas de herramientas
            if m["role"] == "tool" and len(m.get("content") or "") > 400:
                m["content"] = m["content"][:300] + "\n...[recortado para ahorrar contexto]"
                if self._estimate(msgs) <= budget:
                    return msgs
        while self._estimate(msgs) > budget and len(msgs) > 2:   # 2) descartar lo mas antiguo
            msgs.pop(0)
            while msgs and msgs[0]["role"] != "user":
                msgs.pop(0)
        return msgs

    # ---- herramientas
    def _needs_approval(self, tool, name, args):
        mode, cat = self.cfg["mode"], tool["category"]
        if mode == "readonly" and cat != "read":
            return "blocked"
        if T.is_dangerous(name, args, self.ctx):
            return "pending"
        if cat == "read" or cat in self.s.setdefault("allowed", []) or mode == "auto" or (mode == "edits" and cat == "write"):
            return "auto"
        return "pending"

    def _exec(self, call):
        f = call["function"]
        name, raw = f["name"], f.get("arguments") or "{}"
        cid = call["id"]
        tool = T.TOOLS.get(name)
        try:
            args = json.loads(raw) if isinstance(raw, str) else dict(raw)
            if not isinstance(args, dict):
                raise ValueError("los argumentos deben ser un objeto JSON")
        except ValueError as e:
            self.emit({"t": "tool_call", "id": cid, "name": name, "args": {"_raw": str(raw)[:500]}, "category": "read", "approval": "auto"})
            return False, "Argumentos JSON inválidos: %s" % e, None
        if tool is None:
            self.emit({"t": "tool_call", "id": cid, "name": name, "args": args, "category": "read", "approval": "auto"})
            return False, "Herramienta desconocida: %s. Disponibles: %s" % (name, ", ".join(T.TOOLS)), None
        args = coerce(args, tool["parameters"])
        approval = self._needs_approval(tool, name, args)
        self.emit({"t": "tool_call", "id": cid, "name": name, "args": args, "category": tool["category"], "approval": approval,
                   "danger": T.is_dangerous(name, args, self.ctx)})
        if approval == "blocked":
            return False, "Bloqueado: el modo actual es solo lectura.", None
        if approval == "pending":
            ev = {"event": threading.Event(), "decision": None}
            self.pending[cid] = ev
            while not ev["event"].wait(0.3):
                if self.stop.is_set():
                    break
            self.pending.pop(cid, None)
            d = ev["decision"]
            if self.stop.is_set() and d is None:
                self.emit({"t": "approval", "id": cid, "decision": "cancel"})
                return False, "Cancelado por el usuario.", None
            self.emit({"t": "approval", "id": cid, "decision": d})
            if d == "allow_category":
                self.s.setdefault("allowed", []).append(tool["category"])
            elif d != "allow":
                return False, "El usuario denegó esta acción.%s" % (" Motivo: " + d[5:] if d and d.startswith("deny:") and len(d) > 5 else ""), None
        try:
            r = tool["fn"](args, self.ctx)
            if isinstance(r, dict):
                return True, T.clip(r["text"], self.ctx.max_out), r.get("image")
            return True, T.clip(str(r), self.ctx.max_out), None
        except T.Abort:
            raise
        except T.ToolError as e:
            return False, str(e), None
        except Exception as e:
            return False, "%s: %s" % (type(e).__name__, e), None

    def _repair(self):
        """Si se corto a mitad, toda llamada a herramienta debe tener su respuesta para que el historial sea valido."""
        msgs = self.s["messages"]
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i]["role"] == "assistant":
                if msgs[i].get("tool_calls"):
                    done = {m.get("tool_call_id") for m in msgs[i + 1:] if m["role"] == "tool"}
                    for c in msgs[i]["tool_calls"]:
                        if c["id"] not in done:
                            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": "Interrumpido."})
                break

    # ---- bucle principal
    def run(self, text, image_names=()):
        msgs = self.s["messages"]
        content = text if not image_names else [{"type": "text", "text": text}] + [{"type": "image_ref", "name": n} for n in image_names]
        msgs.append({"role": "user", "content": content})
        self.emit({"t": "user", "text": text, "images": list(image_names)})
        try:
            for step in range(int(self.cfg["max_steps"])):
                if self.stop.is_set():
                    break
                self.emit({"t": "turn_start", "step": step + 1})
                external = self.cfg.get("llm_mode") == "external"
                base = self.cfg["external_url"].rstrip("/") if external else "http://127.0.0.1:%d/v1" % int(self.cfg["llm_port"])
                payload = {"model": (self.cfg.get("external_model") or "local") if external else "local", "stream": True,
                           "messages": [{"role": "system", "content": system_prompt(self.cfg)}] + self._fit(self._to_llm()),
                           "temperature": float(self.cfg["temperature"]), "top_p": float(self.cfg["top_p"]), "max_tokens": int(self.cfg["max_tokens"])}
                if not external:   # parametros propios de llama.cpp (una API estricta podria rechazarlos)
                    payload.update({"top_k": int(self.cfg["top_k"]), "cache_prompt": True,
                                    "chat_template_kwargs": {"enable_thinking": bool(self.cfg["thinking"])}})
                allowed = None if self.cfg["mode"] != "readonly" else {"read"}
                payload["tools"] = T.schemas(allowed)
                try:
                    res = llm_stream(base, self.cfg.get("external_key") if external else "", payload, self.holder, self._delta)
                except (ConnectionRefusedError, socket.timeout, OSError) as e:
                    self._flush()
                    if self.stop.is_set():
                        break
                    self.emit({"t": "error", "text": "No puedo conectar con el modelo en %s (%s). %s" % (
                        base, e, "Comprueba que ese servidor esté encendido." if external else "Enciéndelo con el botón «Encender modelo».")})
                    break
                except LLMError as e:
                    self._flush()
                    self.emit({"t": "error", "text": "Error del modelo: %s" % e})
                    break
                except Exception as e:
                    self._flush()
                    if self.stop.is_set():
                        break
                    self.emit({"t": "error", "text": "Conexión con el modelo interrumpida: %s: %s" % (type(e).__name__, e)})
                    break
                self._flush()
                if self.stop.is_set():
                    break
                # ids propios y unicos: algunos servidores repiten ids (p. ej. "call_0") entre turnos
                calls = [{"id": "call_" + uuid.uuid4().hex[:12], "type": "function",
                          "function": {"name": c["name"], "arguments": c["args"] or "{}"}} for c in res["tool_calls"] if c["name"]]
                text_out = res["content"]
                if not calls and "<tool_call>" in text_out:
                    calls, text_out = parse_text_tool_calls(text_out)
                tm = res.get("timings") or {}
                self.emit({"t": "stats", "prompt_n": tm.get("prompt_n"), "prompt_ms": tm.get("prompt_ms"), "gen_n": tm.get("predicted_n"),
                           "tps": tm.get("predicted_per_second"), "finish": res["finish"]})
                am = {"role": "assistant", "content": text_out}
                if calls:
                    am["tool_calls"] = calls
                msgs.append(am)
                self.emit({"t": "assistant_end", "text": text_out})
                if not calls:
                    if not text_out.strip():
                        self.emit({"t": "info", "text": "El modelo no escribió respuesta" + (" (se alcanzó el límite de tokens; sube «máx. tokens» o desactiva el pensamiento)." if res["finish"] == "length" else ".")})
                    break
                images = []
                for i, call in enumerate(calls):
                    if self.stop.is_set():
                        msgs.append({"role": "tool", "tool_call_id": call["id"], "content": "Cancelado por el usuario."})
                        continue
                    ok, out, img = self._exec(call)
                    name = None
                    if img:
                        name = uuid.uuid4().hex[:12] + ".png"
                        with open(os.path.join(self.images_dir, name), "wb") as f:
                            f.write(img)
                        images.append(name)
                    self.emit({"t": "tool_result", "id": call["id"], "ok": ok, "text": out, "image": name})
                    msgs.append({"role": "tool", "tool_call_id": call["id"], "content": out if ok else "ERROR: " + out})
                if images:
                    msgs.append({"role": "user", "_auto": True,
                                 "content": [{"type": "text", "text": "Captura de pantalla resultante:"}] + [{"type": "image_ref", "name": n} for n in images]})
                if self.stop.is_set():
                    break
            else:
                self.emit({"t": "info", "text": "Se alcanzó el máximo de %s pasos. Escribe «continúa» si quieres seguir." % self.cfg["max_steps"]})
        except T.Abort as e:
            self.emit({"t": "error", "text": str(e)})
            self.stop.set()
        except Exception as e:
            self.emit({"t": "error", "text": "Error interno: %s: %s" % (type(e).__name__, e)})
        finally:
            self._flush()
            self._repair()
            if self.stop.is_set():
                self.emit({"t": "info", "text": "Detenido."})
            self.emit({"t": "turn_end"})
