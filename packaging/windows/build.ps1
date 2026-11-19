# Compila Jayth para Windows: carpeta dist\Jayth, instalador Jayth-Setup-<version>-x64.exe y zip portatil.
# Requisitos: Python 3.10+ con `pip install -r requirements.txt pyinstaller` e Inno Setup 6 (se instala con choco si falta).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")
$version = (python -c "import jayth; print(jayth.__version__)").Trim()
Write-Host "Jayth $version"

python -m PyInstaller --noconfirm --clean packaging\jayth.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fallo" }

# Comprobacion del paquete: abre la app sin ventana, revisa recursos, terminal y ventana principal, y cierra
$tmp = Join-Path $env:TEMP ("jayth_selftest_" + [guid]::NewGuid().ToString("N"))
$env:JAYTH_HOME = $tmp
$env:QT_QPA_PLATFORM = "offscreen"
$p = Start-Process -FilePath "dist\Jayth\Jayth.exe" -ArgumentList "--selftest" -Wait -PassThru
Get-Content (Join-Path $tmp "selftest.json") -ErrorAction SilentlyContinue | Write-Host
Remove-Item Env:JAYTH_HOME, Env:QT_QPA_PLATFORM
if ($p.ExitCode -ne 0) { throw "La comprobacion del paquete fallo (codigo $($p.ExitCode))" }

# Zip portatil: con portable.txt los datos se guardan junto al programa (para llevarlo en un USB)
$stage = "build\portable\Jayth"
Remove-Item "build\portable" -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force (Split-Path $stage) | Out-Null
Copy-Item "dist\Jayth" $stage -Recurse
Set-Content -Path (Join-Path $stage "portable.txt") -Value "Modo portatil: los datos se guardan en la carpeta userdata." -Encoding ascii
Compress-Archive -Path $stage -DestinationPath "dist\Jayth-$version-windows-x64-portable.zip" -Force

# Instalador
$iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $iscc)) {
    choco install innosetup -y --no-progress | Out-Null
    $iscc = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
}
& $iscc "/DMyAppVersion=$version" "packaging\windows\jayth.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup fallo" }
Get-ChildItem dist -File | Format-Table Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
