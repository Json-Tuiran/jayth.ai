# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Actualizaciones que solo descargan lo que cambió.

Casi todo el programa instalado (Qt, Python, bibliotecas: unos 380 MB) es idéntico de una versión a otra; lo que cambia
es nuestro código y poco más (unos pocos MB). En vez de bajar el instalador entero:

  Al publicar   se guarda el «manifiesto» de la versión (tamaño y huella SHA-256 de cada archivo) y, comparándolo con
                el de las versiones anteriores, un «paquete de cambios» por cada una: un zip con solo los archivos
                distintos y el manifiesto completo de la versión nueva.
  En el equipo  1. se descarga el paquete de cambios (se comprueba su huella);
                2. se monta la versión nueva COMPLETA en una carpeta aparte, junto a la instalada: los archivos que no
                   cambian se enlazan (sin ocupar disco ni copiar) y los que cambian salen del paquete;
                3. se comprueba la huella de TODOS los archivos de esa carpeta contra el manifiesto: o es exactamente
                   la versión nueva, o no se usa;
                4. al cerrar Jayth se intercambian las dos carpetas (dos cambios de nombre), se arranca la versión
                   nueva en modo comprobación y solo si responde bien se borra la anterior. Si algo falla, se vuelve a
                   poner la carpeta anterior tal cual estaba.

Nunca se toca un archivo de la instalación en uso: la versión instalada sigue entera hasta el intercambio, y después
se conserva hasta que la nueva ha demostrado que arranca. Ante cualquier duda (no hay paquete para tu versión, un
archivo local no coincide, falta disco, el intercambio falla, la versión nueva no arranca) se usa el instalador completo
de siempre.

Este módulo no depende de Qt ni del resto de Jayth: también lo usa la publicación (python -m jayth.parches …).
"""
import os, re, sys, json, time, shutil, hashlib, zipfile

FORMAT = 1
SKIP_TOP = ("unins", "portable.txt", "userdata")     # del instalador o datos del modo portátil: no son del programa
MAX_RATIO = 0.6            # un paquete de cambios mayor que esta parte del programa entero no compensa


class PatchError(Exception):
    """El paquete de cambios no se puede usar: se sigue con el instalador completo."""


# ---------------------------------------------------------------- manifiesto
def _skip(rel):
    top = rel.split("/", 1)[0].lower()
    return any(top == s or (s == "unins" and top.startswith("unins")) for s in SKIP_TOP)


def sha256(path, stop=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            if stop is not None and stop.is_set():
                raise PatchError("cancelado")
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def scan(root, stop=None):
    """{ruta relativa (con /): [tamaño, sha256]} de todos los archivos del programa en `root`."""
    out = {}
    root = os.path.abspath(root)
    for dp, dn, fn in os.walk(root):
        for f in fn:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root).replace("\\", "/")
            if _skip(rel) or os.path.islink(p):
                continue
            out[rel] = [os.path.getsize(p), sha256(p, stop)]
    return out


def manifest(root, version, platform):
    return {"v": FORMAT, "version": version, "plataforma": platform, "archivos": scan(root)}


def _safe(rel):
    """Rutas del paquete: relativas, sin subir de carpeta ni unidades (un zip malicioso no escribe fuera)."""
    if not rel or rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel) or "\\" in rel:
        return False
    return all(part not in ("", ".", "..") for part in rel.split("/"))


# ---------------------------------------------------------------- al publicar: el paquete de cambios
def make_patch(root, new, old, out):
    """Crea en `out` el paquete para pasar de la versión del manifiesto `old` a la de `new` (cuyos archivos están en
    `root`). Devuelve {cambian, sobran, bytes} o None si no compensa (casi todo cambió)."""
    if new.get("plataforma") != old.get("plataforma"):
        raise PatchError("los manifiestos son de plataformas distintas")
    a, b = old["archivos"], new["archivos"]
    changed = sorted(k for k, v in b.items() if a.get(k) != v)
    gone = sorted(k for k in a if k not in b)
    info = {"v": FORMAT, "plataforma": new["plataforma"], "de": old["version"], "a": new["version"],
            "archivos": b, "cambian": changed, "sobran": gone}
    tmp = out + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("parche.json", json.dumps(info, ensure_ascii=False, separators=(",", ":")))
        for rel in changed:
            z.write(os.path.join(root, rel.replace("/", os.sep)), "archivos/" + rel)
    size = os.path.getsize(tmp)
    whole = sum(v[0] for v in b.values())
    if whole and size > whole * 0.42 * MAX_RATIO:      # el programa entero comprimido ronda el 42 % de su tamaño
        os.remove(tmp)
        return None
    os.replace(tmp, out)
    return {"cambian": len(changed), "sobran": len(gone), "bytes": size}


# ---------------------------------------------------------------- en el equipo: montar y comprobar la versión nueva
def read_patch(zip_path):
    """El contenido del paquete (parche.json), validado. Lanza PatchError si no es un paquete de cambios correcto."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            info = json.loads(z.read("parche.json").decode("utf-8"))
            names = set(z.namelist())
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as e:
        raise PatchError("paquete ilegible: %s" % e)
    if info.get("v") != FORMAT or not isinstance(info.get("archivos"), dict):
        raise PatchError("formato de paquete desconocido")
    for rel in list(info["archivos"]) + list(info.get("cambian") or []) + list(info.get("sobran") or []):
        if not _safe(rel) or _skip(rel):
            raise PatchError("ruta no permitida en el paquete: %r" % rel)
    for rel in info.get("cambian") or []:
        if rel not in info["archivos"] or ("archivos/" + rel) not in names:
            raise PatchError("al paquete le falta %s" % rel)
    return info


def _link_or_copy(src, dst):
    try:
        os.link(src, dst)                 # mismo disco: no ocupa ni copia nada
    except OSError:
        shutil.copy2(src, dst)            # disco sin enlaces (FAT/exFAT) o no permitido: copia normal


def free_needed(app_dir, info):
    """Bytes que hacen falta para montar la versión nueva (lo que cambia; todo, si el disco no admite enlaces)."""
    changed = sum(info["archivos"][r][0] for r in info.get("cambian") or [])
    probe = os.path.join(os.path.dirname(app_dir), ".jayth_enlace_%d" % os.getpid())
    some = next((os.path.join(dp, f) for dp, dn, fn in os.walk(app_dir) for f in fn), None)
    links = False
    if some:
        try:
            os.link(some, probe)
            links = True
        except OSError:
            pass
        finally:
            try:
                os.remove(probe)
            except OSError:
                pass
    return changed + (0 if links else sum(v[0] for v in info["archivos"].values())) + (64 << 20)


def stage(app_dir, zip_path, new_dir, version_from, progress=None, stop=None):
    """Monta en `new_dir` la versión nueva completa a partir de la instalada en `app_dir` y del paquete, y comprueba
    la huella de todos sus archivos. Si termina, `new_dir` es exactamente la versión nueva. Si no, lanza PatchError y
    no deja nada a medias. No modifica `app_dir`."""
    app_dir, new_dir = os.path.abspath(app_dir), os.path.abspath(new_dir)
    info = read_patch(zip_path)
    if info.get("de") != version_from:
        raise PatchError("el paquete es para la versión %s, no para la %s" % (info.get("de"), version_from))
    files, changed, gone = info["archivos"], set(info.get("cambian") or []), set(info.get("sobran") or [])
    if os.path.dirname(app_dir) != os.path.dirname(new_dir):
        raise PatchError("la carpeta nueva debe estar junto a la instalada")
    try:
        if shutil.disk_usage(os.path.dirname(app_dir)).free < free_needed(app_dir, info):
            raise PatchError("no hay espacio en disco suficiente")
        shutil.rmtree(new_dir, ignore_errors=True)
        if os.path.exists(new_dir):
            raise PatchError("no se pudo limpiar %s" % new_dir)
        os.makedirs(new_dir)
        total = sum(v[0] for v in files.values()) or 1
        done = 0
        with zipfile.ZipFile(zip_path) as z:
            for rel in sorted(files):
                if stop is not None and stop.is_set():
                    raise PatchError("cancelado")
                dst = os.path.join(new_dir, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if rel in changed:
                    with z.open("archivos/" + rel) as src, open(dst, "wb") as out:
                        shutil.copyfileobj(src, out, 1 << 20)
                else:
                    src = os.path.join(app_dir, rel.replace("/", os.sep))
                    if not os.path.isfile(src):
                        raise PatchError("falta en la instalación: %s" % rel)
                    _link_or_copy(src, dst)
        # lo que hay en la instalación y no es del programa (el desinstalador): pasa tal cual
        for dp, dn, fn in os.walk(app_dir):
            for f in fn:
                src = os.path.join(dp, f)
                rel = os.path.relpath(src, app_dir).replace("\\", "/")
                if rel in files or rel in gone:
                    continue
                top = rel.split("/", 1)[0].lower()
                if top in ("portable.txt", "userdata"):
                    raise PatchError("instalación portátil: se actualiza con el paquete completo")
                if _skip(rel):
                    dst = os.path.join(new_dir, rel.replace("/", os.sep))
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    _link_or_copy(src, dst)
                # cualquier otro archivo suelto no es de Jayth ni de su instalador: no se lleva a la versión nueva
        # la comprobación que da la garantía: TODOS los archivos, contra el manifiesto de la versión nueva
        for rel, (size, digest) in sorted(files.items()):
            p = os.path.join(new_dir, rel.replace("/", os.sep))
            if not os.path.isfile(p) or os.path.getsize(p) != size:
                raise PatchError("tamaño distinto del esperado: %s" % rel)
            if sha256(p, stop) != digest:
                raise PatchError("contenido distinto del esperado: %s" % rel)
            done += size
            if progress:
                progress(done, total, "verificando")
        extra = [r for r in scan_names(new_dir) if r not in files and not _skip(r)]
        if extra:
            raise PatchError("archivos de más en la versión montada: %s" % ", ".join(extra[:3]))
        return info
    except PatchError:
        shutil.rmtree(new_dir, ignore_errors=True)
        raise
    except Exception as e:                     # disco, permisos, zip dañado…: nada a medias y se usa el instalador completo
        shutil.rmtree(new_dir, ignore_errors=True)
        raise PatchError("%s: %s" % (type(e).__name__, e))


def scan_names(root):
    root = os.path.abspath(root)
    return [os.path.relpath(os.path.join(dp, f), root).replace("\\", "/") for dp, dn, fn in os.walk(root) for f in fn]


def verify_dir(root, files, stop=None):
    """¿Es `root` exactamente la versión descrita por `files`? Devuelve la primera diferencia o ''."""
    for rel, (size, digest) in sorted(files.items()):
        p = os.path.join(root, rel.replace("/", os.sep))
        if not os.path.isfile(p):
            return "falta " + rel
        if os.path.getsize(p) != size or sha256(p, stop) != digest:
            return "distinto " + rel
    return ""


# ---------------------------------------------------------------- uso desde la publicación
def _main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="python -m jayth.parches", description="Manifiestos y paquetes de cambios de Jayth")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifiesto", help="huella de cada archivo de una compilación")
    m.add_argument("carpeta")
    m.add_argument("--version", required=True)
    m.add_argument("--plataforma", required=True)
    m.add_argument("-o", "--salida", required=True)
    p = sub.add_parser("parche", help="paquete con lo que cambia entre dos versiones")
    p.add_argument("carpeta", help="la compilación nueva")
    p.add_argument("--nuevo", required=True, help="manifiesto de la versión nueva")
    p.add_argument("--anterior", required=True, help="manifiesto de la versión de partida")
    p.add_argument("-o", "--salida", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "manifiesto":
        d = manifest(a.carpeta, a.version, a.plataforma)
        with open(a.salida, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
        print("manifiesto %s %s: %d archivos, %.1f MB" % (a.plataforma, a.version, len(d["archivos"]),
                                                          sum(v[0] for v in d["archivos"].values()) / 1e6))
        return 0
    new = json.load(open(a.nuevo, encoding="utf-8"))
    old = json.load(open(a.anterior, encoding="utf-8"))
    r = make_patch(a.carpeta, new, old, a.salida)
    if r is None:
        print("de %s a %s cambia casi todo: no se publica paquete de cambios (se usará el instalador completo)" % (old["version"], new["version"]))
        return 0
    print("paquete %s -> %s: %d archivos cambian, %d sobran, %.1f MB" % (old["version"], new["version"], r["cambian"], r["sobran"], r["bytes"] / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
