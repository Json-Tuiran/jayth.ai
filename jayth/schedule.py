# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Tareas programadas: encargos que Jayth ejecuta solo a su hora («cada mañana resúmeme las noticias», «el viernes
revisa esta carpeta») y avisa al terminar. Funcionan mientras Jayth esté abierto (también en la bandeja del sistema);
si a la hora prevista estaba cerrado, la tarea se ejecuta al abrirlo.
"""
import time, uuid, datetime
from . import core

KINDS = [("once", "Una vez"), ("daily", "Cada día"), ("weekdays", "De lunes a viernes"), ("weekly", "Cada semana"), ("interval", "Cada cierto tiempo")]
DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
CATCH_UP = 24 * 3600          # una tarea que tocaba con Jayth cerrado se recupera si no han pasado más de 24 h


def all_tasks(cfg=None):
    return [dict(t) for t in (cfg or core.SET.snapshot()).get("tasks") or []]


def save_tasks(tasks):
    core.SET.update({"tasks": tasks})


def _hm(t):
    try:
        h, m = str(t.get("time") or "09:00").split(":")[:2]
        return max(0, min(23, int(h))), max(0, min(59, int(m)))
    except ValueError:
        return 9, 0


def next_run(t, after=None):
    """Próxima ejecución (marca de tiempo) estrictamente posterior a `after`, o None si ya no toca más."""
    now = datetime.datetime.fromtimestamp(after if after is not None else time.time())
    h, m = _hm(t)
    kind = t.get("kind", "daily")
    if kind == "interval":
        every = max(5, int(t.get("every_min") or 60)) * 60
        base = t.get("last_run") or t.get("created") or now.timestamp()
        nxt = base + every
        while nxt <= now.timestamp():
            nxt += every
        return nxt
    if kind == "once":
        try:
            d = datetime.date.fromisoformat(str(t.get("date")))
        except ValueError:
            d = now.date()
        at = datetime.datetime.combine(d, datetime.time(h, m))
        return at.timestamp() if at > now and not t.get("last_run") else None
    days = {"daily": set(range(7)), "weekdays": {0, 1, 2, 3, 4}}.get(kind) or set(int(x) for x in (t.get("days") or [now.weekday()]))
    for add in range(0, 8):
        d = now.date() + datetime.timedelta(days=add)
        at = datetime.datetime.combine(d, datetime.time(h, m))
        if d.weekday() in days and at > now:
            return at.timestamp()
    return None


def describe(t):
    h, m = _hm(t)
    hm = "%02d:%02d" % (h, m)
    kind = t.get("kind", "daily")
    if kind == "once":
        return "Una vez, el %s a las %s" % (t.get("date", ""), hm)
    if kind == "daily":
        return "Cada día a las %s" % hm
    if kind == "weekdays":
        return "De lunes a viernes a las %s" % hm
    if kind == "weekly":
        ds = [DAYS[int(x)] for x in (t.get("days") or [])] or ["?"]
        return "Cada %s a las %s" % (", ".join(ds[:-1]) + (" y " if len(ds) > 1 else "") + ds[-1], hm)
    n = max(5, int(t.get("every_min") or 60))
    return "Cada %s" % ("%d minutos" % n if n < 60 or n % 60 else ("hora" if n == 60 else "%d horas" % (n // 60)))


def when_text(ts):
    if not ts:
        return "—"
    d = datetime.datetime.fromtimestamp(ts)
    today = datetime.date.today()
    day = "hoy" if d.date() == today else "mañana" if d.date() == today + datetime.timedelta(days=1) else \
        "ayer" if d.date() == today - datetime.timedelta(days=1) else "%s %d/%d" % (DAYS[d.weekday()], d.day, d.month)
    return "%s a las %02d:%02d" % (day, d.hour, d.minute)


def new_task(name, prompt, kind="daily", time_="09:00", date="", days=(), every_min=60, mode="auto"):
    t = {"id": uuid.uuid4().hex[:8], "name": name.strip()[:80] or "Tarea", "prompt": prompt.strip(), "kind": kind, "time": time_,
         "date": date, "days": [int(x) for x in days], "every_min": int(every_min or 60), "mode": mode, "enabled": True,
         "created": time.time(), "last_run": 0, "last_session": ""}
    t["next"] = next_run(t)
    return t


def add(t):
    tasks = all_tasks()
    tasks.append(t)
    save_tasks(tasks)
    return t


def update(tid, **changes):
    tasks = all_tasks()
    for t in tasks:
        if t["id"] == tid:
            t.update(changes)
            if any(k in changes for k in ("kind", "time", "date", "days", "every_min", "enabled")):
                t["next"] = next_run(t) if t.get("enabled", True) else None
    save_tasks(tasks)


def remove(tid):
    save_tasks([t for t in all_tasks() if t["id"] != tid])


def due(now=None):
    """Tareas que toca ejecutar ahora (activas, con hora cumplida; las muy atrasadas se saltan a su próxima vez)."""
    now = now or time.time()
    out, tasks, changed = [], all_tasks(), False
    for t in tasks:
        if not t.get("enabled", True):
            continue
        if not t.get("next"):
            n = next_run(t, now - 1)
            if n != t.get("next"):
                t["next"], changed = n, True
            continue
        if t["next"] <= now:
            if now - t["next"] <= CATCH_UP or t.get("kind") == "once":
                out.append(t)
            else:
                t["next"], changed = next_run(t, now), True
    if changed:
        save_tasks(tasks)
    return out


def start(t):
    """Lanza la tarea en una conversación propia. Devuelve (sesión, error)."""
    s = core.new_session()
    s.title = "⏱ " + t["name"]
    s.data["task"] = t["id"]
    s.data["title_auto"] = None
    note = ("\n\n(Tarea programada «%s», %s. Puede que yo no esté delante: trabaja por tu cuenta, no hagas preguntas "
            "salvo que sea imprescindible y termina con un resumen claro del resultado.)" % (t["name"], describe(t).lower()))
    err = s.send(t["prompt"] + note, mode=t.get("mode") or None)
    if err:
        s.delete()
        return None, err
    now = time.time()
    done_once = t.get("kind") == "once"
    update(t["id"], last_run=now, last_session=s.id, **({"enabled": False} if done_once else {}))
    tasks = all_tasks()
    for x in tasks:                           # la siguiente vez se calcula a partir de ahora
        if x["id"] == t["id"]:
            x["next"] = None if done_once else next_run(x, now)
    save_tasks(tasks)
    return s, None
