# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Ajuste medido del motor: en vez de estimar, prueba configuraciones reales en este equipo y deja la más rápida.

1. llama-bench (viene junto a llama-server): hilos y flash attention -> velocidad al leer (pp) y al escribir (tg).
2. llama-server en un puerto aparte: decodificación especulativa -> velocidad al escribir con cada tipo:
   - draft-mtp: las capas de predicción múltiple que traen algunos modelos (p. ej. Qwen 3.5 y 3.8);
   - ngram-mod: adelanta texto que ya apareció (muy útil al reescribir código o documentos).
Se elige lo que menos tarda en una tarea típica de agente: leer ~2000 tokens y escribir ~200."""
import os, re, json, time, socket, subprocess, threading, urllib.request
from . import osys, core, hardware as HW
from . import i18n
from .i18n import tr

READ_TOK, WRITE_TOK = 2000, 200
_CAPS = {}


def _sig(path):
    try:
        st = os.stat(path)
        return "%s|%d|%d" % (path, st.st_size, int(st.st_mtime))
    except OSError:
        return ""


def engine_caps(exe):
    """Qué admite este llama-server (por su ayuda): {'spec': [tipos de --spec-type], 'fit': bool}. Se guarda por versión."""
    sig = _sig(exe)
    if not sig:
        return {"spec": [], "fit": False}
    if sig in _CAPS:
        return _CAPS[sig]
    saved = core.SET.snapshot().get("engine_caps") or {}
    if saved.get("sig") == sig:
        _CAPS[sig] = saved["caps"]
        return saved["caps"]
    try:
        out = subprocess.run([exe, "--help"], capture_output=True, text=True, timeout=20, cwd=os.path.dirname(exe),
                             **osys.popen_kwargs()).stdout
    except Exception:
        out = ""
    m = re.search(r"--spec-type\s+([\w,.-]+)", out)
    caps = {"spec": m.group(1).split(",") if m else [], "fit": "--fit" in out, "cram": "--cache-ram" in out}
    _CAPS[sig] = caps
    core.SET.update({"engine_caps": {"sig": sig, "caps": caps}})
    return caps


def has_mtp(m):
    """¿El modelo trae capas de predicción múltiple (MTP) en su GGUF?"""
    try:
        from . import gguf
        meta = gguf.read_meta(m.get("path", ""), set())
        return any(k.endswith(".nextn_predict_layers") and int(v or 0) > 0 for k, v in meta.items())
    except Exception:
        return False


def spec_for(cfg, m):
    """Tipo de decodificación especulativa que hay que pasar a llama-server ('' = ninguna)."""
    want = str(cfg.get("spec_type") or "auto")
    caps = engine_caps(cfg.get("llama_exe") or "")
    if want == "auto":
        t = (cfg.get("tuning") or {})
        # sin medir: n-gramas, que solo adelanta lo que ya apareció (no cuesta nada si no acierta). Medido con Qwen3.8 27B
        # en un portátil sin gráfica: texto 0,70 -> 0,69 tok/s y reescribir código 0,64 -> 0,96 (+50 %); MTP, en cambio,
        # bajó el texto a 0,49: solo se usa si la medición de este equipo lo elige.
        want = t.get("spec", "") if t.get("model_sig") == _sig((m or {}).get("path", "")) else "ngram-mod"
    if want in ("", "none"):
        return ""
    ok = [x for x in want.split(",") if x in caps["spec"] and (x != "draft-mtp" or has_mtp(m or {}))]
    return ",".join(ok)


def score(pp, tg):
    """Segundos para una tarea típica de agente (leer y escribir); menos es mejor."""
    return (READ_TOK / pp if pp else 1e9) + (WRITE_TOK / tg if tg else 1e9)


def bench_exe(cfg):
    exe = cfg.get("llama_exe") or ""
    b = os.path.join(os.path.dirname(exe), osys.exe("llama-bench"))
    return b if os.path.isfile(b) else ""


def thread_options(hw):
    phys, logi = int(hw.get("cores") or 1), int(hw.get("logical") or 1)
    return sorted({max(1, phys), max(1, logi)} | ({phys - 1} if phys >= 6 else set()))


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Cancelled(Exception):
    pass


def run_bench(cfg, m, threads, fas, progress=None, stop=None):
    """llama-bench con todas las combinaciones: [{'threads', 'fa', 'pp', 'tg'}]."""
    exe = bench_exe(cfg)
    if not exe:
        raise RuntimeError(tr("Este motor no trae llama-bench: actualízalo en Ajustes › Rendimiento."))
    cmd = [exe, "-m", m["path"], "-t", ",".join(map(str, threads)), "-fa", ",".join(fas), "-p", "256", "-n", "32", "-r", "1",
           "-b", str(cfg.get("batch_size") or 512), "-o", "json"]
    if cfg.get("backend") in ("cuda", "vulkan", "metal") and int(cfg.get("gpu_layers", -1)) >= 0:
        cmd += ["-ngl", str(cfg["gpu_layers"])]
    import tempfile
    # la salida va a archivos: con tuberías sin leer, llama-bench se bloquea al llenarse (en Windows, a los pocos KB)
    fo, fe = tempfile.TemporaryFile(), tempfile.TemporaryFile()
    p = subprocess.Popen(cmd, stdout=fo, stderr=fe, stdin=subprocess.DEVNULL, cwd=os.path.dirname(exe), **osys.popen_kwargs())
    t0, total = time.time(), len(threads) * len(fas)
    while p.poll() is None:
        if stop is not None and stop.is_set():
            osys.kill_tree(p.pid)
            raise Cancelled()
        if progress:
            progress(tr("Midiendo lectura y escritura (%d combinaciones)… %d s") % (total, time.time() - t0))
        time.sleep(0.5)
    fo.seek(0)
    fe.seek(0)
    out, err = fo.read(), fe.read()
    fo.close()
    fe.close()
    try:
        rows = json.loads(out.decode("utf-8", "replace") or "[]")
    except ValueError:
        raise RuntimeError(tr("llama-bench no dio resultados: %s") % err.decode("utf-8", "replace")[-300:])
    res = {}
    for r in rows:
        k = (int(r.get("n_threads") or 0), "on" if str(r.get("flash_attn")).lower() in ("1", "true", "on") else "off")
        d = res.setdefault(k, {"threads": k[0], "fa": k[1], "pp": 0.0, "tg": 0.0})
        if int(r.get("n_prompt") or 0) > 0 and not int(r.get("n_gen") or 0):
            d["pp"] = float(r.get("avg_ts") or 0)
        elif int(r.get("n_gen") or 0) > 0:
            d["tg"] = float(r.get("avg_ts") or 0)
    return list(res.values())


PROBE = [{"role": "user", "content": "Reescribe esta función cambiando el nombre «items» por «elementos» y explica el cambio en una frase.\n\n"
                                     "```python\ndef total(items):\n    suma = 0\n    for item in items:\n        if item['activo']:\n"
                                     "            suma += item['precio'] * item['cantidad']\n    return round(suma, 2)\n```"}]


def run_spec(cfg, m, spec, threads, fa, progress=None, stop=None):
    """Velocidad al escribir (tok/s) con un tipo de decodificación especulativa ('' = ninguna), con llama-server aparte."""
    port = _free_port()
    c = dict(cfg, threads=threads, flash_attn=fa, llm_port=port, n_ctx=4096, spec_type=spec or "none")
    cmd = core.LLM_MGR.command(c)                  # la misma orden que usará Jayth (con --spec-type si toca)
    exe = cfg["llama_exe"]
    env = dict(os.environ)
    if osys.LINUX:
        env["LD_LIBRARY_PATH"] = os.path.dirname(exe) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                         cwd=os.path.dirname(exe), env=env, **osys.popen_kwargs())
    t0 = time.time()
    try:
        while True:
            if stop is not None and stop.is_set():
                raise Cancelled()
            if p.poll() is not None:
                return 0.0
            try:
                with urllib.request.urlopen("http://127.0.0.1:%d/health" % port, timeout=3) as r:
                    if json.loads(r.read().decode()).get("status") == "ok":
                        break
            except Exception:
                pass
            if time.time() - t0 > 900:
                return 0.0
            if progress:
                progress(tr("Cargando el modelo para probar «%s»… %d s") % (spec or tr("sin aceleración"), time.time() - t0))
            time.sleep(1)
        if progress:
            progress(tr("Escribiendo con «%s»…") % (spec or tr("sin aceleración")))
        body = json.dumps({"messages": PROBE, "max_tokens": 64, "temperature": 0, "cache_prompt": False,
                           "chat_template_kwargs": {"enable_thinking": False}}).encode()
        req = urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % port, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=1800) as r:
            tm = json.loads(r.read().decode()).get("timings") or {}
        return float(tm.get("predicted_per_second") or 0)
    finally:
        osys.kill_tree(p.pid)
        try:
            p.wait(15)
        except Exception:
            pass


def tune(cfg=None, progress=None, stop=None, specs=True):
    """Mide y aplica la mejor configuración para el modelo activo. Devuelve el informe (también queda en cfg['tuning'])."""
    cfg = cfg or core.SET.snapshot()
    m = core.active_model(cfg)
    if not m or not os.path.isfile(m.get("path", "")):
        raise RuntimeError(tr("No hay un modelo local activo para medir."))
    hw = HW.detect()
    threads = thread_options(hw)
    fas = ["off", "on"]
    rows = run_bench(cfg, m, threads, fas, progress, stop)
    rows = [r for r in rows if r["pp"] and r["tg"]]
    if not rows:
        raise RuntimeError(tr("La medición no dio resultados."))
    best = min(rows, key=lambda r: score(r["pp"], r["tg"]))
    report = {"model_sig": _sig(m["path"]), "model": core.model_title(m) or m.get("name"), "date": time.strftime("%Y-%m-%d %H:%M"),
              "rows": rows, "threads": best["threads"], "fa": best["fa"], "pp": best["pp"], "tg": best["tg"], "spec": "", "spec_rows": {}}
    caps = engine_caps(cfg.get("llama_exe") or "")
    tries = []
    if specs and cfg.get("llm_mode", "local") == "local":
        if "draft-mtp" in caps["spec"] and has_mtp(m):
            tries.append("draft-mtp")
        if "ngram-mod" in caps["spec"]:
            tries.append("ngram-mod")
    if tries:
        base = run_spec(cfg, m, "", best["threads"], best["fa"], progress, stop)
        report["spec_rows"][""] = base
        for s in tries:
            report["spec_rows"][s] = run_spec(cfg, m, s, best["threads"], best["fa"], progress, stop)
        good = [s for s in tries if base and report["spec_rows"][s] >= base * 1.08]       # al menos un 8 % más rápido
        if len(good) == 2:
            both = run_spec(cfg, m, ",".join(good), best["threads"], best["fa"], progress, stop)
            report["spec_rows"][",".join(good)] = both
            if both >= max(report["spec_rows"][s] for s in good):
                good = [",".join(good)]
        if good:
            report["spec"] = max(good, key=lambda s: report["spec_rows"][s])
            report["tg_spec"] = report["spec_rows"][report["spec"]]
    core.SET.update({"threads": best["threads"], "flash_attn": best["fa"], "tuning": report})
    return report


def summary(rep):
    """Una línea para Ajustes: «4 hilos · flash attention sí · lee 31 tok/s · escribe 2,1 tok/s (2,9 con MTP)»."""
    if not rep:
        return ""
    s = tr("%d hilos · flash attention %s · lee %s tok/s · escribe %s tok/s") % (
        rep["threads"], tr("sí") if rep["fa"] == "on" else tr("no"), i18n.number(rep["pp"], 0), i18n.number(rep["tg"]))
    if rep.get("spec"):
        s += tr(" (%s con %s)") % (i18n.number(rep.get("tg_spec") or 0), {"draft-mtp": "MTP", "ngram-mod": tr("n-gramas")}.get(rep["spec"], rep["spec"]))
    return s


JOB = None


def start(cfg=None, done=None):
    """Lanza la medición en segundo plano; JOB guarda el estado para la interfaz."""
    global JOB
    if JOB is not None and JOB.get("running"):
        return JOB
    job = {"running": True, "text": tr("Preparando…"), "error": "", "report": None, "stop": threading.Event(), "t0": time.time()}
    JOB = job

    def prog(t):
        job["text"] = t

    def run():
        try:
            job["report"] = tune(cfg, prog, job["stop"])
        except Cancelled:
            job["error"] = tr("Cancelado.")
        except Exception as e:
            job["error"] = str(e) or type(e).__name__
        job["running"] = False
        if done:
            done(job)
    threading.Thread(target=run, daemon=True).start()
    return job
