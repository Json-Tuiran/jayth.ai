# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Agradecimientos automáticos a quienes patrocinan Jayth en GitHub Sponsors.

Lo ejecuta .github/workflows/patrocinadores.yml una vez al día. Lee los patrocinios **públicos y activos** de la cuenta
(los privados nunca se publican) y cumple lo que prometen los niveles:
- 10 USD al mes o más → nombre en los agradecimientos de la web (sitio/apoyar.html y sitio/en/support.html);
- 25 USD al mes o más → además, nombre en los README.

Escribe solo entre las marcas <!-- patrocinadores:… --> de cada archivo. Sin cambios no toca nada.

Uso:  SPONSORS_TOKEN=… python tools_web/patrocinadores.py            (token clásico con permiso read:user)
      python tools_web/patrocinadores.py --prueba datos.json          (sin red: lista de prueba)
"""
import os, re, sys, json, html, argparse, urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUENTA = "Json-Tuiran"
WEB_MIN, README_MIN = 10, 25
CONSULTA = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    sponsorshipsAsMaintainer(first: 100, after: $cursor, activeOnly: true, includePrivate: false) {
      pageInfo { hasNextPage endCursor }
      nodes {
        isOneTimePayment
        privacyLevel
        tier { monthlyPriceInDollars isOneTime }
        sponsorEntity {
          ... on User { login name url }
          ... on Organization { login name url }
        }
      }
    }
  }
}"""


def leer(token):
    """Patrocinios públicos y activos: [{"login", "nombre", "url", "usd"}] (usd: lo que aporta al mes)."""
    out, cursor = [], None
    while True:
        body = json.dumps({"query": CONSULTA, "variables": {"login": CUENTA, "cursor": cursor}}).encode()
        req = urllib.request.Request("https://api.github.com/graphql", data=body,
                                     headers={"Authorization": "bearer " + token, "User-Agent": "jayth-patrocinadores"})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        if d.get("errors"):
            raise SystemExit("GitHub respondió con errores: %s" % d["errors"])
        s = d["data"]["user"]["sponsorshipsAsMaintainer"]
        for n in s["nodes"]:
            e, t = n.get("sponsorEntity") or {}, n.get("tier") or {}
            if not e or n.get("privacyLevel") != "PUBLIC" or n.get("isOneTimePayment") or t.get("isOneTime"):
                continue
            out.append({"login": e["login"], "nombre": e.get("name") or e["login"], "url": e.get("url") or
                        "https://github.com/" + e["login"], "usd": int(t.get("monthlyPriceInDollars") or 0)})
        if not s["pageInfo"]["hasNextPage"]:
            return out
        cursor = s["pageInfo"]["endCursor"]


def ordenar(lista, minimo):
    """Los que llegan al mínimo, de mayor a menor aporte y luego por nombre (sin repetir)."""
    vistos, out = set(), []
    for p in sorted(lista, key=lambda p: (-p["usd"], p["nombre"].lower())):
        if p["usd"] >= minimo and p["login"] not in vistos:
            vistos.add(p["login"])
            out.append(p)
    return out


def bloque_readme(pats, es):
    if not pats:
        return ("¿Quieres aparecer aquí? Patrocina Jayth con 25 USD al mes en "
                "[GitHub Sponsors](https://github.com/sponsors/%s)." % CUENTA if es else
                "Want to be listed here? Sponsor Jayth with 25 USD a month on "
                "[GitHub Sponsors](https://github.com/sponsors/%s)." % CUENTA)
    nombres = " · ".join("[%s](%s)" % (p["nombre"].replace("]", ""), p["url"]) for p in pats)
    return ("**Patrocinadores:** " if es else "**Sponsors:** ") + nombres


def bloque_web(pats, es):
    if not pats:
        return ('<p class="note" style="margin:0">%s</p>' % (
            "Todavía no hay nadie en esta lista: con 10 USD al mes o más, tu nombre aparecerá aquí." if es else
            "Nobody here yet: at 10 USD a month or more, your name will show up here."))
    items = "".join('<li><a href="%s" rel="noopener">%s</a></li>' % (html.escape(p["url"], quote=True), html.escape(p["nombre"]))
                    for p in pats)
    return '<ul class="share" style="list-style:none;padding:0;margin:0">%s</ul>' % items


def poner(ruta, contenido):
    """Sustituye lo que hay entre las marcas. Devuelve True si el archivo cambió."""
    s = open(ruta, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in s else "\n"
    m = re.search(r"(<!-- patrocinadores:inicio -->)(.*?)(<!-- patrocinadores:fin -->)", s, re.S)
    if not m:
        raise SystemExit("Faltan las marcas de patrocinadores en %s" % ruta)
    nuevo = s[:m.start(2)] + nl + contenido.replace("\n", nl) + nl + s[m.end(2):]
    if nuevo == s:
        return False
    open(ruta, "w", encoding="utf-8", newline="").write(nuevo)
    return True


def main():
    ap = argparse.ArgumentParser(description="Actualiza los agradecimientos a patrocinadores de Jayth.")
    ap.add_argument("--prueba", help="JSON con una lista de patrocinadores de prueba (no usa la red)")
    ap.add_argument("--raiz", default=RAIZ)
    a = ap.parse_args()
    if a.prueba:
        lista = json.load(open(a.prueba, encoding="utf-8"))
    else:
        token = os.environ.get("SPONSORS_TOKEN", "").strip()
        if not token:
            print("Sin el secreto SPONSORS_TOKEN no se puede leer la lista de patrocinadores: no se cambia nada.")
            return
        lista = leer(token)
    web, readme = ordenar(lista, WEB_MIN), ordenar(lista, README_MIN)
    cambios = []
    for rel, txt in (("README.md", bloque_readme(readme, True)), ("README.en.md", bloque_readme(readme, False)),
                     ("sitio/apoyar.html", bloque_web(web, True)), ("sitio/en/support.html", bloque_web(web, False))):
        if poner(os.path.join(a.raiz, rel), txt):
            cambios.append(rel)
    print("Patrocinios públicos activos: %d · en la web: %d · en el README: %d" % (len(lista), len(web), len(readme)))
    print("Archivos cambiados: %s" % (", ".join(cambios) or "ninguno"))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("cambios=%s\n" % ("si" if cambios else "no"))


if __name__ == "__main__":
    main()
