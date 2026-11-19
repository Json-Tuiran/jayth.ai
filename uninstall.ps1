<#
  Desinstala Agente Local: quita los accesos directos y el entorno .venv.
  Si se instalo desde GitHub (en %LOCALAPPDATA%\Programs\AgenteLocal) tambien borra el codigo.
  Tus datos (conversaciones, ajustes y modelos descargados) solo se borran si lo confirmas.
#>
$ErrorActionPreference = "Stop"
$AppName = "Agente Local"
$AppDir = $PSScriptRoot
$Data = "$env:LOCALAPPDATA\AgenteLocal"

foreach ($dir in @([Environment]::GetFolderPath("Desktop"), (Join-Path ([Environment]::GetFolderPath("Programs")) $AppName))) {
    $l = Join-Path $dir "$AppName.lnk"
    if (Test-Path $l) { Remove-Item $l -Force; Write-Host "Quitado: $l" }
}
$startDir = Join-Path ([Environment]::GetFolderPath("Programs")) $AppName
if ((Test-Path $startDir) -and -not (Get-ChildItem $startDir)) { Remove-Item $startDir -Force }
if (Test-Path "$AppDir\.venv") { Remove-Item "$AppDir\.venv" -Recurse -Force; Write-Host "Quitado el entorno .venv" }

if (Test-Path $Data) {
    $size = [math]::Round(((Get-ChildItem $Data -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum) / 1GB, 2)
    $ans = Read-Host "¿Borrar también tus datos en $Data ($size GB: conversaciones, ajustes y modelos descargados)? Esto no se puede deshacer. [s/N]"
    if ($ans -match '^(s|si|sí|y|yes)$') { Remove-Item $Data -Recurse -Force; Write-Host "Datos borrados." } else { Write-Host "Datos conservados." }
}
if ($AppDir -like "$env:LOCALAPPDATA\Programs\AgenteLocal*") {
    Set-Location $env:TEMP
    Remove-Item $AppDir -Recurse -Force
    Write-Host "Código borrado: $AppDir"
}
Write-Host "$AppName desinstalado."
