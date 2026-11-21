# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Bóveda de credenciales: guarda los permisos (tokens) de los servicios que el usuario conecta.

- Windows: cifrados con DPAPI (CryptProtectData), atados a la cuenta del usuario en este equipo: otra cuenta u otro
  equipo no pueden descifrarlos, aunque copien el archivo.
- macOS y Linux: en un archivo que solo puede leer el usuario (permisos 600).
Nunca se guardan contraseñas: solo los permisos que el propio servicio entrega tras iniciar sesión."""
import os, json, hashlib, ctypes
from . import paths, osys

DIR = os.path.join(paths.DATA, "credenciales")


def _file(key):
    return os.path.join(DIR, hashlib.sha256(key.encode("utf-8")).hexdigest()[:32] + ".bin")


if osys.WIN:
    from ctypes import wintypes

    class _BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _dpapi(data, protect):
        crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
        buf = ctypes.create_string_buffer(data, len(data))
        src, out = _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), _BLOB()
        fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
        ok = fn(ctypes.byref(src), "Jayth" if protect else None, None, None, None, 0x1, ctypes.byref(out))   # 0x1: sin ventanas
        if not ok:
            raise OSError("DPAPI %d" % ctypes.GetLastError())
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            kernel32.LocalFree(out.pbData)

    def _seal(raw):
        return b"DPAPI1" + _dpapi(raw, True)

    def _open(data):
        if not data.startswith(b"DPAPI1"):
            raise ValueError("formato desconocido")
        return _dpapi(data[6:], False)
else:
    def _seal(raw):
        return b"PLAIN1" + raw

    def _open(data):
        if not data.startswith(b"PLAIN1"):
            raise ValueError("formato desconocido")
        return data[6:]


def put(key, value):
    """Guarda un diccionario (se sustituye el anterior)."""
    os.makedirs(DIR, exist_ok=True)
    p = _file(key)
    tmp = p + ".tmp"
    with open(tmp, "wb") as f:
        f.write(_seal(json.dumps({"key": key, "value": value}).encode("utf-8")))
    if not osys.WIN:
        os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def get(key):
    """El diccionario guardado o None (si no hay, o si no se puede descifrar: p. ej. copiado de otro equipo)."""
    try:
        with open(_file(key), "rb") as f:
            d = json.loads(_open(f.read()).decode("utf-8"))
        return d["value"] if d.get("key") == key else None
    except (OSError, ValueError, KeyError):
        return None


def delete(key):
    try:
        os.remove(_file(key))
        return True
    except OSError:
        return False
