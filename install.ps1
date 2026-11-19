<#
  Instalador de Jayth (Windows 10/11, 64 bits).

  Desde GitHub (una sola linea en PowerShell):
      irm https://raw.githubusercontent.com/Json-Tuiran/agentes-en-local/main/install.ps1 | iex

  Desde una copia local (git clone o zip descomprimido):
      doble clic en install.bat   (o: powershell -ExecutionPolicy Bypass -File install.ps1)

  Que hace:
    1. Obtiene el codigo (carpeta local o zip de GitHub).
    2. Busca Python 3.10+ de 64 bits; si no hay, lo instala para el usuario (winget o python.org).
    3. Crea un entorno aislado (.venv) e instala las dependencias (requirements.txt).
    4. Crea accesos directos en el Escritorio y en el menu Inicio.
    5. Abre la app: su asistente descarga el motor (llama.cpp) y el modelo que elijas.
  No necesita permisos de administrador.
#>
param(
    [string]$Repo = $(if ($env:JAYTH_REPO) { $env:JAYTH_REPO } else { "Json-Tuiran/agentes-en-local" }),
    [string]$Branch = "main",
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\Jayth",
    [switch]$NoShortcut,
    [switch]$NoLaunch
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$AppName = "Jayth"
$PyVersion = "3.12.10"

function Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Ok($m) { Write-Host "    $m" -ForegroundColor Green }
function Fail($m) { Write-Host "`nERROR: $m" -ForegroundColor Red; exit 1 }

# ------------------------------------------------------------------ 1. codigo
Step "Obteniendo $AppName"
$local = $null
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot "app.py"))) { $local = $PSScriptRoot }
if ($local) {
    $AppDir = $local
    Ok "Usando la carpeta local: $AppDir"
} else {
    if ($Repo -like "TU_USUARIO/*") { Fail "Este instalador aun no apunta a un repositorio. Define JAYTH_REPO=usuario/repositorio o edita la variable `$Repo." }
    $tmp = Join-Path $env:TEMP ("jayth_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force $tmp | Out-Null
    $zip = Join-Path $tmp "src.zip"
    Invoke-WebRequest "https://codeload.github.com/$Repo/zip/refs/heads/$Branch" -OutFile $zip -UseBasicParsing
    Expand-Archive $zip -DestinationPath $tmp -Force
    $inner = Get-ChildItem $tmp -Directory | Select-Object -First 1
    New-Item -ItemType Directory -Force $InstallDir | Out-Null
    # actualiza el codigo conservando el entorno (.venv) y los datos portatiles
    Get-ChildItem $InstallDir -Force | Where-Object { $_.Name -notin ".venv", "userdata", "portable.txt" } | Remove-Item -Recurse -Force
    Copy-Item (Join-Path $inner.FullName "*") $InstallDir -Recurse -Force
    Remove-Item $tmp -Recurse -Force
    $AppDir = $InstallDir
    Ok "Instalado en: $AppDir"
}

# ------------------------------------------------------------------ 2. Python
Step "Buscando Python 3.10+ (64 bits)"
function Test-Py($exe, $pre) {
    try {
        $out = & $exe @pre -c "import sys,struct;print(int(sys.version_info[:2]>=(3,10) and struct.calcsize('P')==8))" 2>$null
        return ($LASTEXITCODE -eq 0 -and "$out".Trim() -eq "1")
    } catch { return $false }
}
function Find-Py {
    foreach ($v in "3.13", "3.12", "3.11", "3.10") {
        if ((Get-Command py -ErrorAction SilentlyContinue) -and (Test-Py "py" @("-$v"))) { return @("py", "-$v") }
    }
    foreach ($c in @("python") + (Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe", "$env:ProgramFiles\Python3*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object FullName)) {
        if ((Get-Command $c -ErrorAction SilentlyContinue) -and (Test-Py $c @())) { return @($c) }
    }
    return $null
}
$py = Find-Py
if (-not $py) {
    Step "Instalando Python $PyVersion para tu usuario"
    $done = $false
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        try {
            winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
            $done = $true
        } catch { $done = $false }
    }
    $py = Find-Py
    if (-not $py) {
        $exe = Join-Path $env:TEMP "python-$PyVersion-amd64.exe"
        Invoke-WebRequest "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-amd64.exe" -OutFile $exe -UseBasicParsing
        Start-Process $exe -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0" -Wait
        Remove-Item $exe -Force -ErrorAction SilentlyContinue
        $py = Find-Py
    }
    if (-not $py) { Fail "No se pudo instalar Python. Instálalo desde https://www.python.org y vuelve a ejecutar este instalador." }
}
$pyExe = $py[0]; $pyArgs = @($py | Select-Object -Skip 1)
Ok ("Python: " + (& $pyExe @pyArgs --version))

# ------------------------------------------------------------------ 3. entorno y dependencias
Step "Preparando el entorno aislado (.venv) e instalando dependencias"
$venv = Join-Path $AppDir ".venv"
if (-not (Test-Path "$venv\Scripts\python.exe")) { & $pyExe @pyArgs -m venv $venv; if ($LASTEXITCODE) { Fail "No se pudo crear el entorno virtual." } }
$vpy = "$venv\Scripts\python.exe"
& $vpy -m pip install --upgrade pip --quiet --disable-pip-version-check
& $vpy -m pip install -r (Join-Path $AppDir "requirements.txt") --quiet --disable-pip-version-check
if ($LASTEXITCODE) { Fail "Falló la instalación de dependencias (¿sin internet?)." }
& $vpy -c "import PySide6.QtWidgets" ; if ($LASTEXITCODE) { Fail "PySide6 no quedó instalado correctamente." }
Ok "Dependencias listas"

# ------------------------------------------------------------------ 4. accesos directos
if (-not $NoShortcut) {
    Step "Creando accesos directos"
    $ws = New-Object -ComObject WScript.Shell
    $targets = @([Environment]::GetFolderPath("Desktop"), (Join-Path ([Environment]::GetFolderPath("Programs")) $AppName))
    foreach ($dir in $targets) {
        New-Item -ItemType Directory -Force $dir | Out-Null
        $lnk = $ws.CreateShortcut((Join-Path $dir "$AppName.lnk"))
        $lnk.TargetPath = "$venv\Scripts\pythonw.exe"
        $lnk.Arguments = "`"$AppDir\app.py`""
        $lnk.WorkingDirectory = $AppDir
        $lnk.IconLocation = "$AppDir\assets\icon.ico"
        $lnk.Description = "Agente de IA local"
        $lnk.Save()
    }
    Ok "Escritorio y menú Inicio"
}

Step "$AppName está instalado"
Write-Host "    Código:  $AppDir"
Write-Host "    Datos:   $env:LOCALAPPDATA\Jayth  (ajustes, conversaciones, modelos)"
Write-Host "    Al abrirlo por primera vez, el asistente descargará el motor y el modelo que elijas."
if (-not $NoLaunch) { Start-Process "$venv\Scripts\pythonw.exe" -ArgumentList "`"$AppDir\app.py`"" -WorkingDirectory $AppDir }
