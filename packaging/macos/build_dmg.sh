#!/bin/bash
# Compila Jayth para macOS: dist/Jayth.app y Jayth-<version>-macos-<arch>.dmg (arrastrar a Aplicaciones).
# Requisitos: python3 con `pip install -r requirements.txt pyinstaller`. Se compila en un Mac de la misma arquitectura.
set -euo pipefail
cd "$(dirname "$0")/../.."
VERSION=$(python3 -c "import jayth; print(jayth.__version__)")
ARCH=$(uname -m); [ "$ARCH" = "x86_64" ] && ARCH=x64
echo "Jayth $VERSION ($ARCH)"

python3 -m PyInstaller --noconfirm --clean packaging/jayth.spec
codesign --force --deep --sign - dist/Jayth.app       # firma ad hoc de todo el paquete

# Comprobacion del paquete (sin ventana)
TMP=$(mktemp -d)
JAYTH_HOME="$TMP" QT_QPA_PLATFORM=offscreen dist/Jayth.app/Contents/MacOS/Jayth --selftest || { cat "$TMP/selftest.json" 2>/dev/null; echo "::error title=Autocomprobacion macOS::$(tr -d '\n' < "$TMP/selftest.json" 2>/dev/null || echo sin informe)"; exit 1; }

rm -rf build/dmg && mkdir -p build/dmg
cp -R dist/Jayth.app build/dmg/
ln -s /Applications build/dmg/Applications
hdiutil create -volname "Jayth" -srcfolder build/dmg -ov -format UDZO "dist/Jayth-$VERSION-macos-$ARCH.dmg"
ls -lh dist/*.dmg
