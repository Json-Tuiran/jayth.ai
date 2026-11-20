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

hidden = ["PySide6.QtSvg", "PySide6.QtSvgWidgets", "certifi", "pypdf",
          # navegador integrado del lienzo (se importa solo cuando hace falta, por eso se nombra aqui)
          "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel", "PySide6.QtNetwork", "PySide6.QtPrintSupport",
          # voz: leer en voz alta (voces del sistema) y grabar del micrófono para el dictado
          "PySide6.QtTextToSpeech", "PySide6.QtMultimedia"]
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
            StringStruct("CompanyName", "Ing. Jeison Tuiran"), StringStruct("FileDescription", "Jayth"),
            StringStruct("LegalCopyright", "Copyright (C) 2026 Ing. Jeison Tuiran · GPL-3.0"),
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
    datas=[(ASSETS, "assets"),
           # la GPL-3.0 exige entregar la licencia con el programa; la marca y la firma, para que se sepan sus condiciones
           (os.path.join(ROOT, "LICENSE"), "."), (os.path.join(ROOT, "MARCA.md"), ".")],
    hiddenimports=hidden,
    # dependencias opcionales que pypdf/mss/Qt arrastran si estan instaladas y Jayth no usa
    excludes=["tkinter", "unittest", "test", "pydoc_data", "lib2to3", "numpy", "PIL", "cryptography", "scipy", "matplotlib",
              "pandas", "IPython", "PySide6.QtPdf", "PySide6.QtWebEngineQuick", "PySide6.Qt3DCore", "PySide6.QtCharts",
              "PySide6.QtMultimediaWidgets", "PySide6.QtDataVisualization", "PySide6.QtBluetooth", "PySide6.QtSensors"],
    noarchive=False,
)
# Partes de Qt que Jayth no necesita: PDF y teclado virtual. (Qt Quick/QML se quedan: el navegador integrado los usa.)
_DROP = ("qt6pdf", "qt6virtualkeyboard", "virtualkeyboard", "qpdf", "qt6quick3d", "qt6charts", "qt6multimediawidgets", "qt6multimediaquick", "qt6datavis",
         # el micrófono usa el sistema de sonido nativo: no hace falta FFmpeg (~60 MB)
         "avcodec", "avformat", "avutil", "swresample", "swscale", "ffmpegmediaplugin",
         "opengl32sw", "qt6quickcontrols2", "qt6quickdialogs2", "qt6quicktemplates2", "qt6quicklayouts", "qt6quickeffects",
         "qt6quickparticles", "qt6quickshapes", "qt6quicktest", "qt6quicktimeline", "qt6webenginequick", "qt6labs")
a.binaries = [b for b in a.binaries if not any(d in os.path.basename(b[0]).lower() for d in _DROP)]
a.datas = [d for d in a.datas if not any(x in d[0].lower().replace("\\", "/") for x in ("/qml/", "qtvirtualkeyboard"))]
# del navegador solo hacen falta los idiomas de la interfaz en español e inglés (el resto son ~25 MB)
a.datas = [d for d in a.datas if "devtools_resources" not in d[0].lower()]        # inspector del navegador: 83 MB que no se usan
a.binaries = [b for b in a.binaries if "devtools_resources" not in b[0].lower()]
a.datas = [d for d in a.datas if "qtwebengine_locales" not in d[0].lower().replace("\\", "/")
           or os.path.basename(d[0]).lower() in ("es.pak", "es-419.pak", "en-us.pak")]
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
            "NSHumanReadableCopyright": "Copyright (C) 2026 Ing. Jeison Tuiran · GPL-3.0",
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.developer-tools",
            # control de otras apps y ventanas (osascript / System Events)
            "NSAppleEventsUsageDescription": "Jayth controla otras aplicaciones cuando se lo pides (con tu aprobación).",
        },
    )
