# -*- mode: python ; coding: utf-8 -*-
# Empaquetado de Jayth con PyInstaller (Windows, macOS y Linux). Desde la raiz del repositorio:
#   python -m PyInstaller --noconfirm --clean packaging/jayth.spec
# Resultado: dist/Jayth/ (carpeta con el ejecutable) y, en macOS, dist/Jayth.app
import os, sys
from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, ROOT)
from jayth import __version__ as VERSION

WIN, MAC = sys.platform == "win32", sys.platform == "darwin"
ASSETS = os.path.join(ROOT, "assets")

hidden = ["PySide6.QtSvg", "certifi", "pypdf"]
if MAC:
    # pynput elige su motor al importarse: se nombran explicitamente (el compilador no tiene pantalla)
    hidden += ["mss", "mss.darwin", "pynput", "pynput.keyboard._darwin", "pynput.mouse._darwin", "pynput._util.darwin",
               "pynput._util.darwin_vks"]
elif not WIN:
    hidden += ["mss", "mss.linux", "pynput", "pynput.keyboard._xorg", "pynput.mouse._xorg", "pynput.keyboard._uinput",
               "pynput._util.xorg", "pynput._util.xorg_keysyms", "pynput._util.uinput"] + collect_submodules("Xlib")

# Ficha de version del .exe (Propiedades > Detalles)
version_file = None
if WIN:
    from PyInstaller.utils.win32.versioninfo import (VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct,
                                                     VarFileInfo, VarStruct)
    nums = tuple(int(x) for x in (VERSION.split(".") + ["0"] * 4)[:4])
    vi = VSVersionInfo(
        ffi=FixedFileInfo(filevers=nums, prodvers=nums),
        kids=[StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "Jayth"), StringStruct("FileDescription", "Jayth"),
            StringStruct("FileVersion", VERSION), StringStruct("InternalName", "Jayth"),
            StringStruct("OriginalFilename", "Jayth.exe"), StringStruct("ProductName", "Jayth"),
            StringStruct("ProductVersion", VERSION)])]),
              VarFileInfo([VarStruct("Translation", [1033, 1200])])])
    version_file = os.path.join(workpath, "version_info.txt")
    os.makedirs(workpath, exist_ok=True)
    with open(version_file, "w", encoding="utf-8") as f:
        f.write(str(vi))

a = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    datas=[(ASSETS, "assets")],
    hiddenimports=hidden,
    # dependencias opcionales que pypdf/mss/Qt arrastran si estan instaladas y Jayth no usa
    excludes=["tkinter", "unittest", "test", "pydoc_data", "lib2to3", "numpy", "PIL", "cryptography", "scipy", "matplotlib",
              "pandas", "IPython", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtPdf", "PySide6.QtWebEngineCore"],
    noarchive=False,
)
# Partes de Qt que una app de widgets no necesita: QML/Quick, PDF, teclado virtual y OpenGL por software (~40 MB)
_DROP = ("qt6quick", "qt6qml", "qt6pdf", "qt6virtualkeyboard", "virtualkeyboard", "opengl32sw", "qpdf")
a.binaries = [b for b in a.binaries if not any(d in os.path.basename(b[0]).lower() for d in _DROP)]
a.datas = [d for d in a.datas if not any(x in d[0].lower().replace("\\", "/") for x in ("/qml/", "qtvirtualkeyboard"))]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Jayth",
    console=False,                       # app de ventana: sin consola
    upx=False,                           # UPX dispara falsos positivos de antivirus y rompe Qt
    icon=os.path.join(ASSETS, "icon.ico" if WIN else "icon.icns") if (WIN or MAC) else None,
    version=version_file,
    target_arch=None,
    codesign_identity=None,              # macOS: firma ad hoc
    entitlements_file=None,
)

coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="Jayth")

if MAC:
    app = BUNDLE(
        coll,
        name="Jayth.app",
        icon=os.path.join(ASSETS, "icon.icns"),
        bundle_identifier="ai.jayth.app",
        version=VERSION,
        info_plist={
            "CFBundleName": "Jayth",
            "CFBundleDisplayName": "Jayth",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.developer-tools",
            # control de otras apps y ventanas (osascript / System Events)
            "NSAppleEventsUsageDescription": "Jayth controla otras aplicaciones cuando se lo pides (con tu aprobación).",
        },
    )
