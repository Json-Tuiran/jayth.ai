# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Paquete MSIX de Jayth para la Microsoft Store.

La tienda firma el paquete al publicarlo, así que se crea sin firmar y no va a las Releases de GitHub (sin firma no se
puede instalar fuera de la tienda). Dentro del paquete, Jayth no se actualiza solo: lo hace la tienda (osys.store_package).

Uso (Windows, con el SDK de Windows instalado):
  python packaging/tienda/crear_msix.py dist/Jayth --version 0.9.7 --nombre <Identity Name> \\
      --editor "CN=…" --editor-nombre "Ing. Jeison Tuiran" -o dist-tienda

Los tres datos de identidad salen de Partner Center (Gestión de productos › Identidad del producto); ver
packaging/TIENDA.md.
"""
import os, re, sys, glob, shutil, argparse, subprocess
from xml.sax.saxutils import escape

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
IDIOMAS = ("es-ES", "en-US", "pt-BR", "fr-FR", "de-DE", "it-IT", "ja-JP", "zh-CN")
LOGOS = {"StoreLogo.png": (50, 50), "Square44x44Logo.png": (44, 44), "Square44x44Logo.targetsize-256_altform-unplated.png": (256, 256),
         "Square150x150Logo.png": (150, 150), "Wide310x150Logo.png": (310, 150)}


def version_msix(v):
    """0.9.7 → 0.9.7.0 (la tienda pide cuatro números y el último a 0)."""
    partes = [int(x) for x in re.findall(r"\d+", v)][:3]
    while len(partes) < 3:
        partes.append(0)
    return ".".join(str(x) for x in partes + [0])


def logos(dst):
    """Logotipos de la tienda a partir del icono de la app (centrado, con margen y fondo transparente)."""
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtCore import Qt
    icono = QImage(os.path.join(RAIZ, "assets", "icon.png"))
    if icono.isNull():
        raise SystemExit("No encuentro assets/icon.png")
    os.makedirs(dst, exist_ok=True)
    for nombre, (w, h) in LOGOS.items():
        im = QImage(w, h, QImage.Format_ARGB32)
        im.fill(Qt.transparent)
        lado = int(min(w, h) * (0.84 if min(w, h) < 100 else 0.72))
        ic = icono.scaled(lado, lado, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        p = QPainter(im)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage((w - ic.width()) // 2, (h - ic.height()) // 2, ic)
        p.end()
        im.save(os.path.join(dst, nombre))


def manifiesto(nombre, editor, editor_nombre, version):
    plantilla = open(os.path.join(AQUI, "AppxManifest.plantilla.xml"), encoding="utf-8").read()
    recursos = "\n".join('    <Resource Language="%s"/>' % l for l in IDIOMAS)
    return (plantilla.replace("{NOMBRE}", escape(nombre, {'"': "&quot;"})).replace("{EDITOR}", escape(editor, {'"': "&quot;"}))
            .replace("{EDITOR_NOMBRE}", escape(editor_nombre)).replace("{VERSION}", version).replace("{RECURSOS}", recursos))


def makeappx():
    """El makeappx.exe más nuevo del SDK de Windows."""
    raiz = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Windows Kits", "10", "bin")
    hallados = sorted(glob.glob(os.path.join(raiz, "10.*", "x64", "makeappx.exe")),
                      key=lambda p: [int(x) for x in re.findall(r"\d+", os.path.basename(os.path.dirname(os.path.dirname(p))))])
    if not hallados:
        raise SystemExit("No encuentro makeappx.exe (instala el SDK de Windows).")
    return hallados[-1]


def main():
    ap = argparse.ArgumentParser(description="Crea el paquete MSIX de Jayth para la Microsoft Store.")
    ap.add_argument("app", help="Carpeta de la app compilada (dist/Jayth)")
    ap.add_argument("--version", required=True)
    ap.add_argument("--nombre", required=True, help="Identity Name de Partner Center")
    ap.add_argument("--editor", required=True, help="Publisher de Partner Center (CN=…)")
    ap.add_argument("--editor-nombre", required=True, help="Publisher display name de Partner Center")
    ap.add_argument("-o", "--salida", default="dist-tienda")
    a = ap.parse_args()
    if not os.path.isfile(os.path.join(a.app, "Jayth.exe")):
        raise SystemExit("En %s no está Jayth.exe" % a.app)
    v = version_msix(a.version)
    base = os.path.join(a.salida, "paquete")
    shutil.rmtree(base, ignore_errors=True)
    shutil.copytree(a.app, base)
    for sobra in ("portable.txt", "userdata"):              # dentro de la tienda nunca es la versión portátil
        ruta = os.path.join(base, sobra)
        shutil.rmtree(ruta, ignore_errors=True) if os.path.isdir(ruta) else (os.path.exists(ruta) and os.remove(ruta))
    logos(os.path.join(base, "Assets"))
    with open(os.path.join(base, "AppxManifest.xml"), "w", encoding="utf-8") as f:
        f.write(manifiesto(a.nombre, a.editor, a.editor_nombre, v))
    salida = os.path.join(a.salida, "Jayth-%s-x64.msix" % a.version)
    r = subprocess.run([makeappx(), "pack", "/d", base, "/p", salida, "/o"], capture_output=True, text=True)
    print(r.stdout[-3000:])
    if r.returncode:
        print(r.stderr[-3000:], file=sys.stderr)
        raise SystemExit("makeappx falló (%d)" % r.returncode)
    shutil.rmtree(base, ignore_errors=True)
    print("Paquete: %s (%.0f MB), versión %s" % (salida, os.path.getsize(salida) / 1e6, v))


if __name__ == "__main__":
    main()
