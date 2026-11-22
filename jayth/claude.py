"""Claude por su API nativa (/v1/messages) en vez de la capa compatible con OpenAI.

La capa compatible ignora el esfuerzo (`reasoning_effort`), no devuelve el razonamiento y no admite la caché de
contexto: con ella el esfuerzo elegido en Jayth era decoración y cada paso de una tarea larga se cobraba entero. Aquí:
- el esfuerzo va en el ajuste propio de Claude (`output_config.effort`);
- el razonamiento llega resumido (`thinking.display: "summarized"`) y el chat lo muestra como en los modelos locales;
- la conversación se guarda en la caché del servicio (`cache_control`), que cobra a una fracción lo ya leído;
- los bloques de razonamiento se devuelven tal cual en los pasos siguientes, como pide Claude; si Jayth recortó o
  resumió el historial, el servicio descarta los que ya no encajan en vez de rechazar la petición
  (`prefix_mismatch_behavior: "drop_block"`).

Recibe y devuelve lo mismo que agent.llm_stream (formato OpenAI), así el resto de Jayth no cambia. Lo que un modelo no
admite (p. ej. el esfuerzo en los antiguos) se aprende de su error 400 y deja de enviarse."""
import re, json, time, threading, http.client, urllib.parse

HOSTS = ("api.anthropic.com",)
VERSION = "2023-06-01"
BETA_BINDING = "thinking-binding-controls-2026-08-01"
_OFF = {}                       # modelo -> lo que ese modelo rechazó (effort, thinking, display, binding, cache)
_LOCK = threading.Lock()
FINISH = {"end_turn": "stop", "stop_sequence": "stop", "pause_turn": "stop", "tool_use": "tool_calls", "max_tokens": "length",
          "refusal": "refusal", "model_context_window_exceeded": "length"}


def is_claude(base):
    try:
        return (urllib.parse.urlparse(base).hostname or "").lower() in HOSTS
    except ValueError:
        return False


def _text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(p.get("text", "") for p in content or [] if isinstance(p, dict) and p.get("type") == "text")


def _image(url):
    m = re.match(r"data:([^;,]+);base64,(.*)", url or "", re.S)
    if m:
        return {"type": "image", "source": {"type": "base64", "media_type": m.group(1), "data": m.group(2)}}
    return {"type": "image", "source": {"type": "url", "url": url}}


def _parts(content):
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content.strip() else []
    out = []
    for p in content or []:
        if not isinstance(p, dict):
            continue
        if p.get("type") == "text" and (p.get("text") or "").strip():
            out.append({"type": "text", "text": p["text"]})
        elif p.get("type") == "image_url":
            out.append(_image((p.get("image_url") or {}).get("url", "")))
    return out


def _tool_use(tc):
    f = tc.get("function") or {}
    try:
        inp = json.loads(f.get("arguments") or "{}")
    except ValueError:
        inp = {"_raw": f.get("arguments") or ""}
    if not isinstance(inp, dict):
        inp = {"value": inp}
    return {"type": "tool_use", "id": tc.get("id"), "name": f.get("name") or "", "input": inp}


def convert(payload, model):
    """Mensajes, herramientas e instrucciones de formato OpenAI -> (system, messages, tools) de Claude."""
    system, msgs = [], []

    def push(role, blocks):
        if not blocks:
            return
        if msgs and msgs[-1]["role"] == role:          # Claude alterna usuario / asistente: los seguidos se unen
            msgs[-1]["content"].extend(blocks)
        else:
            msgs.append({"role": role, "content": list(blocks)})

    for m in payload.get("messages") or []:
        role = m.get("role")
        if role in ("system", "developer"):
            t = _text_of(m.get("content"))
            if t.strip():
                system.append(t)
        elif role == "tool":
            t = _text_of(m.get("content"))
            blk = {"type": "tool_result", "tool_use_id": m.get("tool_call_id"), "content": t or "(sin salida)"}
            if t.startswith("ERROR: "):
                blk["is_error"] = True
            push("user", [blk])
        elif role == "assistant":
            raw = m.get("_ant")
            if raw and m.get("_ant_model") == model:       # su propia respuesta, tal cual (con su razonamiento)
                blocks = [dict(b) for b in raw]
                have = {b.get("id") for b in blocks if b.get("type") == "tool_use"}
                blocks += [_tool_use(tc) for tc in m.get("tool_calls") or [] if tc.get("id") not in have]
            else:                                           # de otro modelo o de antes: texto y llamadas
                blocks = _parts(m.get("content")) + [_tool_use(tc) for tc in m.get("tool_calls") or []]
            push("assistant", blocks)
        else:
            push("user", _parts(m.get("content")))
    if msgs and msgs[0]["role"] != "user":                  # la conversación tiene que empezar por el usuario
        msgs.insert(0, {"role": "user", "content": [{"type": "text", "text": "(continúa)"}]})
    tools = []
    for t in payload.get("tools") or []:
        f = t.get("function") or t
        if f.get("name"):
            tools.append({"name": f["name"], "description": f.get("description") or "",
                          "input_schema": f.get("parameters") or {"type": "object", "properties": {}}})
    return "\n\n".join(system), msgs, tools


def body_for(payload):
    """Petición de Claude (cuerpo y cabeceras extra) a partir de una de formato OpenAI."""
    model = payload.get("model") or ""
    off = _OFF.get(model, set())
    system, msgs, tools = convert(payload, model)
    body = {"model": model, "stream": True, "messages": msgs,
            "max_tokens": int(payload.get("max_tokens") or payload.get("max_completion_tokens") or 16000)}
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools
    if "thinking" not in off:
        th = {"type": "adaptive"}
        if "display" not in off:
            th["display"] = "summarized"                 # el razonamiento llega resumido y el chat lo muestra
        if "binding" not in off:
            th["block_binding"] = {"prefix_mismatch_behavior": "drop_block"}
        body["thinking"] = th
    effort = payload.get("reasoning_effort")
    if effort and "effort" not in off:
        body["output_config"] = {"effort": effort}
    if "cache" not in off:
        body["cache_control"] = {"type": "ephemeral"}    # lo ya leído se cobra a una fracción en el paso siguiente
    extra = {"anthropic-beta": BETA_BINDING} if "thinking" not in off and "binding" not in off else {}
    return body, extra


def learn(model, error):
    """Un 400 de Claude por algo que ese modelo no admite: se deja de enviar. True si se aprendió algo."""
    e = (error or "").lower()
    if not e.startswith("http 400"):
        return False
    off = _OFF.setdefault(model, set())
    for key, words in (("binding", ("block_binding", "prefix_mismatch", "thinking-binding", "anthropic-beta")),
                       ("display", ("display",)), ("effort", ("effort", "output_config")),
                       ("cache", ("cache_control",)), ("thinking", ("thinking", "adaptive"))):
        if key not in off and any(w in e for w in words):
            with _LOCK:
                off.add(key)
                if key == "thinking":
                    off.update(("display", "binding"))
            return True
    return False


def _stream_once(base, key, payload, holder, on_delta, err):
    u = urllib.parse.urlparse(base)
    from .agent import tls_context
    if u.scheme == "https":
        conn = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=10, context=tls_context())
    else:                                       # (un intermediario local o las pruebas)
        conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=10)
    holder["conn"] = conn
    body, extra = body_for(payload)
    try:
        conn.connect()
        conn.sock.settimeout(None)
        holder["sock"] = conn.sock
        heads = dict({"Content-Type": "application/json", "x-api-key": key or "", "anthropic-version": VERSION,
                      "Accept": "text/event-stream"}, **extra)
        conn.request("POST", "/v1/messages", json.dumps(body).encode("utf-8"), heads)
        resp = conn.getresponse()
        if resp.status != 200:
            body = resp.read(4000).decode("utf-8", "replace")
            try:
                raise err("HTTP %d: %s" % (resp.status, body[:2000]), resp.status, body, resp.getheader("retry-after"))
            except TypeError:                         # un tipo de error que no admite esos datos
                raise err("HTTP %d: %s" % (resp.status, body[:2000]))
        rl = {k.lower(): v for k, v in resp.getheaders() if "ratelimit" in k.lower() or k.lower() == "retry-after"}
        blocks, content, reasoning = {}, [], []
        usage, out_tok, finish = {}, 0, None
        holder["rx"], holder["rx_n"], holder["t_gen"] = time.time(), 0, None

        def seen():
            holder["rx"], holder["rx_n"] = time.time(), holder.get("rx_n", 0) + 1
            if holder.get("t_gen") is None:
                holder["t_gen"] = holder["rx"]
        while True:
            try:
                line = resp.readline()
            except Exception:
                if holder.get("cut"):
                    finish = "cut"
                    break
                raise
            if not line:
                if holder.get("cut"):
                    finish = "cut"
                break
            line = line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except ValueError:
                continue
            t = ev.get("type")
            if t == "message_start":
                usage = dict((ev.get("message") or {}).get("usage") or {})
            elif t == "content_block_start":
                b = dict(ev.get("content_block") or {})
                if b.get("type") == "tool_use":
                    b["_json"] = ""
                    b["input"] = {}
                blocks[ev.get("index", len(blocks))] = b
            elif t == "content_block_delta":
                b = blocks.setdefault(ev.get("index", 0), {"type": "text", "text": ""})
                d = ev.get("delta") or {}
                dt = d.get("type")
                if dt == "text_delta":
                    b["text"] = b.get("text", "") + d.get("text", "")
                    content.append(d.get("text", ""))
                    on_delta("content", d.get("text", ""))
                    seen()
                elif dt == "thinking_delta":
                    b["thinking"] = b.get("thinking", "") + d.get("thinking", "")
                    if d.get("thinking"):
                        reasoning.append(d["thinking"])
                        on_delta("reasoning", d["thinking"])
                        seen()
                elif dt == "signature_delta":
                    b["signature"] = b.get("signature", "") + d.get("signature", "")
                elif dt == "input_json_delta":
                    b["_json"] = b.get("_json", "") + d.get("partial_json", "")
                    on_delta("tool", "%s\t%d" % (b.get("name", ""), len(b["_json"])))
                    seen()
            elif t == "content_block_stop":
                b = blocks.get(ev.get("index"))
                if b is not None and b.get("type") == "tool_use":
                    try:
                        b["input"] = json.loads(b.get("_json") or "{}")
                    except ValueError:
                        b["input"] = {"_raw": b.get("_json") or ""}
            elif t == "message_delta":
                finish = FINISH.get((ev.get("delta") or {}).get("stop_reason"), (ev.get("delta") or {}).get("stop_reason")) or finish
                out_tok = int((ev.get("usage") or {}).get("output_tokens") or out_tok)
            elif t == "error":
                e = ev.get("error") or {}
                over = e.get("type") == "overloaded_error"         # saturado a mitad: se trata como un 529
                try:
                    raise err("%s: %s" % (e.get("type", "error"), e.get("message", "")), 529 if over else None, json.dumps(ev))
                except TypeError:
                    raise err("%s: %s" % (e.get("type", "error"), e.get("message", "")))
            elif t == "message_stop":
                break
        raw = []
        calls = []
        for k in sorted(blocks):
            b = {x: y for x, y in blocks[k].items() if x != "_json"}
            raw.append(b)
            if b.get("type") == "tool_use":
                calls.append({"id": b.get("id", ""), "name": b.get("name", ""), "args": json.dumps(b.get("input") or {}, ensure_ascii=False)})
        read = int(usage.get("input_tokens") or 0) + int(usage.get("cache_read_input_tokens") or 0) + int(usage.get("cache_creation_input_tokens") or 0)
        use = {"prompt_tokens": read, "completion_tokens": out_tok, "cache_read_input_tokens": int(usage.get("cache_read_input_tokens") or 0),
               "cache_creation_input_tokens": int(usage.get("cache_creation_input_tokens") or 0)}
        return {"content": "".join(content), "reasoning": "".join(reasoning), "tool_calls": calls, "finish": finish,
                "timings": None, "usage": use, "headers": rl, "blocks": raw, "keep_ids": True}
    finally:
        try:
            conn.close()
        except Exception:
            pass
        holder["conn"] = None
        holder["sock"] = None


def stream(base, key, payload, holder, on_delta, err):
    """Una petición a Claude. Si rechaza algo que ese modelo no admite, se quita y se repite (como apis.learn)."""
    for _ in range(6):
        try:
            return _stream_once(base, key, payload, holder, on_delta, err)
        except err as e:
            if not learn(payload.get("model") or "", str(e)):
                raise
    return _stream_once(base, key, payload, holder, on_delta, err)
