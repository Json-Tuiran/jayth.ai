#!/usr/bin/env bash
# Deja una Release de Jayth lista para descargar directamente, por sistema:
#  - sube una copia de cada paquete SIN el número de versión, con enlaces fijos que siempre bajan la última versión:
#      https://github.com/<repo>/releases/latest/download/Jayth-Setup-x64.exe   (y los demás nombres)
#    (la app se actualiza buscando los nombres CON versión, así que estas copias no le afectan);
#  - escribe las notas de la Release con un enlace directo por sistema.
# Uso (en GitHub Actions, con GH_TOKEN): bash packaging/enlaces_release.sh v0.4.7 carpeta_con_los_paquetes
set -euo pipefail
TAG="$1"
DIR="$2"
V="${TAG#v}"
REPO="${GITHUB_REPOSITORY:?falta GITHUB_REPOSITORY}"

ALIAS="$(mktemp -d)"
for f in "$DIR"/*; do
  b="$(basename "$f")"
  case "$b" in *.manifest.json|Jayth-parche-*) continue ;; esac   # las huellas y los paquetes de cambios son de una versión concreta
  n="${b/-$V/}"                        # Jayth-Setup-0.4.7-x64.exe -> Jayth-Setup-x64.exe
  if [ "$n" != "$b" ]; then cp "$f" "$ALIAS/$n"; fi
done
ls -lh "$ALIAS"
gh release upload "$TAG" "$ALIAS"/* --repo "$REPO" --clobber

U="https://github.com/$REPO/releases/download/$TAG"
L="https://github.com/$REPO/releases/latest/download"
link() { if [ -f "$DIR/$1" ]; then printf '[%s](%s/%s)' "$2" "$U" "$1"; fi; }
join() { local out="" x; for x in "$@"; do if [ -n "$x" ]; then out="${out:+$out · }$x"; fi; done; printf '%s' "$out"; }
row() { local links; links="$(join "${@:2}")"; if [ -n "$links" ]; then printf '| %s | %s |\n' "$1" "$links"; fi; }

{
  # novedades de la versión, si se escribieron en packaging/novedades/<etiqueta>.md
  if [ -f "packaging/novedades/$TAG.md" ]; then cat "packaging/novedades/$TAG.md"; echo; fi
  echo "## Descargar Jayth $V"
  echo
  echo "| Sistema | Descarga directa |"
  echo "|---|---|"
  row "**Windows 10/11** (64 bits)" "$(link "Jayth-Setup-$V-x64.exe" "Instalador (.exe)")" "$(link "Jayth-$V-windows-x64-portable.zip" "Versión portátil (.zip)")"
  row "**macOS** con chip Apple (M1–M4)" "$(link "Jayth-$V-macos-arm64.dmg" "Jayth para Apple Silicon (.dmg)")"
  row "**macOS** con Intel" "$(link "Jayth-$V-macos-x64.dmg" "Jayth para Intel (.dmg)")"
  row "**Linux** (x86_64)" "$(link "Jayth-$V-linux-x86_64.AppImage" "AppImage")" "$(link "Jayth-$V-linux-x86_64.tar.gz" "Comprimido (.tar.gz)")"
  echo
  echo "No hace falta instalar Python ni nada más. Al abrirlo por primera vez, el asistente detecta tu equipo y descarga el motor y el modelo."
  echo
  echo "**Enlaces que siempre descargan la última versión** (para compartir o guardar):"
  echo "[Windows](${L}/Jayth-Setup-x64.exe) · [Windows portátil](${L}/Jayth-windows-x64-portable.zip) ·"\
       "[macOS Apple Silicon](${L}/Jayth-macos-arm64.dmg) · [macOS Intel](${L}/Jayth-macos-x64.dmg) ·"\
       "[Linux AppImage](${L}/Jayth-linux-x86_64.AppImage)"
  echo
  echo "### Antes de abrirlo"
  echo
  echo "Los paquetes todavía no están firmados:"
  echo "- **Windows:** si aparece «Windows protegió su PC», pulsa *Más información → Ejecutar de todas formas*."
  echo "- **macOS:** la primera vez, clic derecho sobre Jayth → *Abrir* (o *Ajustes del Sistema → Privacidad y seguridad → Abrir igualmente*)."
  echo "- **Linux:** haz ejecutable el AppImage (\`chmod +x Jayth-*.AppImage\`) y ábrelo."
  echo
  echo "Los archivos sin número de versión de la lista de abajo son copias de los mismos paquetes (para los enlaces fijos)."
  echo
  echo "[Ver los cambios de esta versión](https://github.com/$REPO/commits/$TAG)"
} > notes.md
cat notes.md
gh release edit "$TAG" --repo "$REPO" --notes-file notes.md
