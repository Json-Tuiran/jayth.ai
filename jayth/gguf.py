# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Lectura de los metadatos de un archivo GGUF (solo la cabecera: no carga el modelo).

Se usa para saber qué sabe hacer un modelo ya instalado sin internet: su plantilla de conversación
(tokenizer.chat_template) dice si admite herramientas y si tiene modo de pensar.
"""
import struct

_FIXED = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}       # tamaño de los tipos numéricos
_FMT = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}
STRING, ARRAY = 8, 9
# siempre se guardan: el contexto de fábrica y lo necesario para saber cuánta memoria ocupa cada token de contexto
_ALWAYS = (".context_length", ".block_count", ".embedding_length", ".attention.head_count", ".attention.head_count_kv",
           ".attention.key_length", ".attention.value_length", ".full_attention_interval", ".nextn_predict_layers")


class NotGGUF(ValueError):
    pass


def read_meta(path, want=None, max_bytes=256 << 20):
    """Metadatos clave -> valor. Con `want` (conjunto de claves) se detiene en cuanto las tiene todas.
    Las listas largas (el vocabulario) se saltan sin guardarlas."""
    out = {}
    with open(path, "rb") as f:
        def rd(n):
            b = f.read(n)
            if len(b) != n:
                raise NotGGUF("archivo GGUF incompleto")
            if f.tell() > max_bytes:
                raise NotGGUF("cabecera GGUF demasiado grande")
            return b

        def u32():
            return struct.unpack("<I", rd(4))[0]

        def u64():
            return struct.unpack("<Q", rd(8))[0]

        def string():
            return rd(u64()).decode("utf-8", "replace")

        def value(t, keep=True):
            if t in _FIXED:
                b = rd(_FIXED[t])
                return struct.unpack(_FMT[t], b)[0] if keep else None
            if t == STRING:
                if keep:
                    return string()
                f.seek(u64(), 1)
                return None
            if t == ARRAY:
                et, n = u32(), u64()
                if et in _FIXED:
                    if keep and n <= 64:
                        return [struct.unpack(_FMT[et], rd(_FIXED[et]))[0] for _ in range(n)]
                    f.seek(_FIXED[et] * n, 1)
                    return None
                small = keep and n <= 64
                items = []
                for _ in range(n):
                    v = value(et, small)
                    if small:
                        items.append(v)
                return items if small else None
            raise NotGGUF("tipo de dato GGUF desconocido: %d" % t)

        if rd(4) != b"GGUF":
            raise NotGGUF("no es un archivo GGUF")
        ver = u32()
        if ver < 2:
            raise NotGGUF("versión de GGUF demasiado antigua (%d)" % ver)
        u64()                                   # número de tensores
        for _ in range(u64()):
            key = string()
            t = u32()
            keep = want is None or key in want or key.endswith(_ALWAYS)
            v = value(t, keep)
            if keep:
                out[key] = v
            if want and all(k in out for k in want):
                break
    return out
