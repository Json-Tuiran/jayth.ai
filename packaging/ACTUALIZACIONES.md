# Actualizaciones de Jayth

Jayth empaquetado se actualiza solo desde GitHub Releases (`jayth/updater.py`). Hay dos caminos; el segundo es la red
de seguridad del primero.

## 1. Solo lo que cambia (Windows instalado)

Casi todo el programa instalado (Qt, Python y bibliotecas: unos 380 MB) es idéntico de una versión a otra. Lo que cambia
es nuestro código y poco más: unos pocos MB.

**Al publicar** (`release.yml`, trabajo de Windows, con `python -m jayth.parches`):

- `Jayth-<versión>-windows-x64.manifest.json`: tamaño y huella SHA-256 de cada archivo de `dist\Jayth`.
- `Jayth-parche-<anterior>-a-<versión>-windows-x64.zip`, uno por cada una de las últimas 3 versiones que publicaron su
  manifiesto: los archivos distintos y el manifiesto completo de la versión nueva. Si cambia casi todo (por ejemplo, al
  subir de versión de Qt), no se publica y esa actualización va con el instalador completo.

**En el equipo** (`jayth/parches.py`):

1. Se descarga el paquete de cambios y se comprueba con la huella que da GitHub.
2. Se monta la versión nueva **completa** en `…\Programs\Jayth.nuevo`, junto a la instalada: lo que no cambia se enlaza
   (enlaces duros: ni copia ni ocupa disco) y lo que cambia sale del paquete.
3. Se comprueba la huella de **todos** los archivos de esa carpeta contra el manifiesto. O es exactamente la versión
   nueva, o no se usa.
4. Al cerrar Jayth (o al pulsar «Reiniciar para actualizar») un script intercambia las carpetas con dos cambios de
   nombre (`Jayth` → `Jayth.anterior`, `Jayth.nuevo` → `Jayth`), arranca la versión nueva con `--verify-install` y solo
   si contesta bien borra la anterior. Si no contesta, o tarda más de 2 minutos, vuelve a poner la anterior.

Nunca se modifica un archivo de la instalación en uso.

**Cuándo NO se usa** (y se sigue con el camino 2, sin que el usuario tenga que hacer nada):

| Caso | Qué pasa |
|---|---|
| No hay paquete para tu versión (te saltaste más de 3 versiones) | instalador completo |
| El paquete no trae huella, no coincide o está dañado | instalador completo |
| Un archivo de tu instalación no coincide con el esperado (dañado o modificado) | instalador completo, que además lo repara |
| No hay disco suficiente o no se puede escribir junto a la instalación | instalador completo |
| Otro programa tiene abierta la carpeta de Jayth al intercambiar | no se cambia nada; la próxima vez, instalador completo |
| La versión nueva no arranca o se cuelga en la comprobación | vuelve la anterior; la próxima vez, instalador completo |
| El equipo se apaga justo entre los dos cambios de nombre | al iniciar sesión, un rescate (RunOnce) devuelve la carpeta anterior |
| Instalación portátil, macOS, Linux | paquete completo (como siempre) |

Lo que falló queda anotado en `updates\sin_parche.json` para no reintentarlo con esa versión.

**Firma de código:** con SignPath activo no se generan manifiestos ni paquetes de cambios, porque los archivos que
instala el instalador firmado ya no serían los de `dist\Jayth`. Para activarlos con firma hay que generar el manifiesto
a partir de los archivos ya firmados.

## 2. Paquete completo (todas las plataformas)

El instalador (`Jayth-Setup-<versión>-x64.exe`), el `.dmg` o el AppImage se descargan en segundo plano, se comprueban
con SHA-256 y se instalan al cerrar Jayth. Es el camino de siempre y el respaldo del anterior.

## Pruebas

`test_parches.py` (en la carpeta de pruebas de la sesión de desarrollo) monta instalaciones de prueba y ejecuta el
intercambio real con PowerShell: actualización correcta, versión que no arranca, versión colgada, carpeta en uso,
rescate tras un apagón, paquete dañado, archivo local alterado y paquete que intenta escribir fuera de su carpeta.
