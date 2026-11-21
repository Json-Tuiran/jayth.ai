// Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
// SPDX-License-Identifier: GPL-3.0-only
//
// Puente de comentarios de Jayth (Cloudflare Worker).
// Jayth envía aquí lo que el usuario escribió y revisó (sin cuenta de GitHub); el puente lo convierte en una incidencia
// del repositorio PRIVADO de reportes, donde el dueño lo ve todo. La clave de GitHub vive solo aquí, como secreto
// (GITHUB_TOKEN): nunca va dentro de Jayth, donde cualquiera podría sacarla.
//
//   POST /reporte  {kind, title, body, version, os, lang}  ->  {ok: true, number}
//   GET  /         ->  {ok: true, servicio: "jayth-reportes"}   (para comprobar que está en marcha)
//
// Variables: REPO (p. ej. "Json-Tuiran/jayth-reportes"). Secreto: GITHUB_TOKEN (fine-grained, solo ese repositorio,
// permiso «Issues: Read and write»).

const KINDS = {
  error: { label: "bug", prefix: "Error" },
  idea: { label: "enhancement", prefix: "Idea" },
  pregunta: { label: "question", prefix: "Pregunta" },
  cierre: { label: "bug", prefix: "Cierre inesperado", extra: "cierre inesperado" },
};
const MAX_BYTES = 64 * 1024;
const PER_IP = 5;              // envíos por dirección…
const PER_IP_WINDOW = 600e3;   // …cada 10 minutos (por instancia del puente: es un freno, no una garantía)
const PER_HOUR = 60;           // y como mucho 60 por hora en total por instancia
const seen = new Map();
let hour = { start: 0, n: 0 };

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json; charset=utf-8" } });
}

function clean(s, max) {
  return String(s ?? "")
    .replace(/\u0000/g, "")
    .replace(/@(?=[A-Za-z0-9-])/g, "@​")       // sin menciones: nadie recibe avisos por un texto pegado
    .slice(0, max);
}

function throttled(ip, now) {
  if (now - hour.start > 3600e3) hour = { start: now, n: 0 };
  if (hour.n >= PER_HOUR) return true;
  const times = (seen.get(ip) || []).filter((t) => now - t < PER_IP_WINDOW);
  if (times.length >= PER_IP) {
    seen.set(ip, times);
    return true;
  }
  times.push(now);
  seen.set(ip, times);
  hour.n += 1;
  if (seen.size > 5000) seen.clear();
  return false;
}

export function issueFor(r, now = new Date()) {
  const k = KINDS[r.kind];
  const title = `[${k.prefix}] ${clean(r.title, 140).trim()}`;
  const meta = [
    "| | |", "|---|---|",
    `| Tipo | ${k.prefix} |`,
    `| Versión | ${clean(r.version, 20) || "—"} |`,
    `| Sistema | ${clean(r.os, 80) || "—"} |`,
    `| Idioma | ${clean(r.lang, 10) || "—"} |`,
    `| Recibido | ${now.toISOString().replace("T", " ").slice(0, 16)} UTC |`,
  ].join("\n");
  const body = `${meta}\n\n${clean(r.body, 20000)}\n\n---\n*Enviado desde Jayth a través del puente de comentarios.*`;
  const labels = [k.label, "desde Jayth"].concat(k.extra ? [k.extra] : []);
  return { title, body, labels };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/") return json({ ok: true, servicio: "jayth-reportes" });
    if (request.method !== "POST" || url.pathname !== "/reporte") return json({ ok: false, error: "no encontrado" }, 404);
    if (request.headers.get("x-jayth") !== "1") return json({ ok: false, error: "cliente no válido" }, 400);
    const len = Number(request.headers.get("content-length") || 0);
    if (len > MAX_BYTES) return json({ ok: false, error: "demasiado grande" }, 413);
    let text;
    try {
      text = await request.text();
    } catch {
      return json({ ok: false, error: "no se pudo leer" }, 400);
    }
    if (text.length > MAX_BYTES) return json({ ok: false, error: "demasiado grande" }, 413);
    let r;
    try {
      r = JSON.parse(text);
    } catch {
      return json({ ok: false, error: "JSON no válido" }, 400);
    }
    if (!r || typeof r !== "object" || !KINDS[r.kind]) return json({ ok: false, error: "tipo no válido" }, 400);
    if (r.website) return json({ ok: true, number: 0 });           // trampa para robots: se acepta y no se publica
    const title = String(r.title ?? "").trim();
    const body = String(r.body ?? "").trim();
    if (title.length < 3 || body.length < 1) return json({ ok: false, error: "falta el resumen o la descripción" }, 400);
    const ip = request.headers.get("cf-connecting-ip") || "?";
    if (throttled(ip, Date.now())) return json({ ok: false, error: "demasiados envíos seguidos; inténtalo más tarde" }, 429);
    if (!env.GITHUB_TOKEN || !env.REPO) return json({ ok: false, error: "el puente no está configurado" }, 503);
    const res = await fetch(`https://api.github.com/repos/${env.REPO}/issues`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${env.GITHUB_TOKEN}`,
        accept: "application/vnd.github+json",
        "x-github-api-version": "2022-11-28",
        "user-agent": "jayth-reportes",
        "content-type": "application/json",
      },
      body: JSON.stringify(issueFor(r)),
    });
    if (!res.ok) {
      console.log("GitHub respondió", res.status, (await res.text()).slice(0, 300));
      return json({ ok: false, error: "no se pudo guardar el informe" }, 502);
    }
    const issue = await res.json();
    return json({ ok: true, number: issue.number });
  },
};
