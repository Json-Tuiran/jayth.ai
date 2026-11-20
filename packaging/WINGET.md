# Jayth en winget

[winget](https://learn.microsoft.com/windows/package-manager/) es el gestor de paquetes de Windows. Con la ficha de Jayth
publicada, cualquiera puede instalarlo o actualizarlo con un comando:

```powershell
winget install JeisonTuiran.Jayth
```

La ficha vive en el repositorio comunitario [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs), en
`manifests/j/JeisonTuiran/Jayth/<versión>/`, y la revisan sus moderadores antes de publicarla.

## Primera versión (a mano)

1. Bifurcar `microsoft/winget-pkgs` en la cuenta del autor.
2. Añadir los cuatro manifiestos de la versión (`JeisonTuiran.Jayth.yaml`, `.installer.yaml`, `.locale.en-US.yaml` y
   `.locale.es-ES.yaml`) en `manifests/j/JeisonTuiran/Jayth/<versión>/`.
3. Abrir la petición de cambios (pull request) contra `microsoft/winget-pkgs` y aceptar el acuerdo de colaboración (CLA)
   de Microsoft cuando lo pida su bot.
4. Esperar a que la validen (instalan el paquete en una máquina de prueba) y la aprueben.

Datos del instalador: tipo `inno`, ámbito `user` (no pide permisos de administrador) y código de producto
`{8E5B2C61-4D7A-4F0E-9C3B-6A1D2F7E9B40}_is1` (el `AppId` de `windows/jayth.iss` más `_is1`). No cambiar nunca ese `AppId`:
es lo que permite a winget y a Windows reconocer las versiones instaladas.

## Versiones siguientes (automático)

El trabajo «Actualizar winget» de `.github/workflows/release.yml` abre solo la petición de cambios de cada versión nueva
con [WinGet Releaser](https://github.com/vedantmgoyal9/winget-releaser). Para activarlo:

1. Mantener la bifurcación de `winget-pkgs` en la cuenta del autor.
2. Crear un token clásico de GitHub con el permiso `public_repo` (*Settings → Developer settings → Personal access tokens
   → Tokens (classic)*).
3. Guardarlo en este repositorio como secreto `WINGET_TOKEN` (*Settings → Secrets and variables → Actions*).

Sin ese secreto el paso no hace nada y la publicación sigue igual.
