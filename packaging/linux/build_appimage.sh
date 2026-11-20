#!/bin/bash
# Compila Jayth para Linux: Jayth-<version>-linux-<arch>.AppImage (un solo archivo ejecutable) y un .tar.gz.
# Requisitos: python3 con `pip install -r requirements.txt pyinstaller`, curl y las bibliotecas xcb de Qt
# (en Ubuntu: sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1 libfontconfig1).
# Conviene compilar en la distribucion mas antigua que se quiera soportar (glibc): p. ej. Ubuntu 22.04.
set -euo pipefail
cd "$(dirname "$0")/../.."
VERSION=$(python3 -c "import jayth; print(jayth.__version__)")
ARCH=$(uname -m)
echo "Jayth $VERSION ($ARCH)"

python3 -m PyInstaller --noconfirm --clean packaging/jayth.spec

# Comprobacion del paquete (sin ventana)
TMP=$(mktemp -d)
JAYTH_HOME="$TMP" QT_QPA_PLATFORM=offscreen dist/Jayth/Jayth --selftest || { cat "$TMP/selftest.json" 2>/dev/null; echo "::error title=Autocomprobacion Linux::$(tr -d '\n' < "$TMP/selftest.json" 2>/dev/null || echo sin informe)"; exit 1; }

APPDIR=build/Jayth.AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/512x512/apps"
cp -a dist/Jayth "$APPDIR/usr/bin/jayth"
cp assets/icon.png "$APPDIR/jayth.png"
cp assets/icon.png "$APPDIR/usr/share/icons/hicolor/512x512/apps/jayth.png"
cp packaging/linux/jayth.desktop "$APPDIR/jayth.desktop"
cp packaging/linux/jayth.desktop "$APPDIR/usr/share/applications/jayth.desktop"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/jayth/Jayth" "$@"
EOF
chmod +x "$APPDIR/AppRun"

TOOL="build/appimagetool-$ARCH.AppImage"
[ -f "$TOOL" ] || curl -fsSL -o "$TOOL" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
chmod +x "$TOOL"
ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" "dist/Jayth-$VERSION-linux-$ARCH.AppImage"

tar -C dist -czf "dist/Jayth-$VERSION-linux-$ARCH.tar.gz" Jayth
ls -lh dist/*.AppImage dist/*.tar.gz
