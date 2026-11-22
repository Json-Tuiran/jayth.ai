# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Deteccion del hardware y recomendacion de cuantizacion / motor en Windows, macOS y Linux."""
import os, re, shutil, ctypes, platform, subprocess
from . import osys
from .i18n import tr

GB = 1024 ** 3
NO_WINDOW = osys.NO_WINDOW
APPLE_SILICON = osys.MAC and platform.machine() == "arm64"


def _run(cmd, timeout=10):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW).stdout
    except Exception:
        return ""


def _sysctl(name):
    return _run(["sysctl", "-n", name]).strip()


class _MEM(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def _meminfo():
    info = {}
    try:
        for l in open("/proc/meminfo"):
            k, v = l.split(":", 1)
            info[k] = int(v.split()[0]) * 1024
    except Exception:
        pass
    return info


def ram():
    """(total, disponible) en bytes."""
    if osys.WIN:
        m = _MEM()
        m.dwLength = ctypes.sizeof(_MEM)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullTotalPhys, m.ullAvailPhys
    if osys.MAC:
        total = int(_sysctl("hw.memsize") or 0)
        out = _run(["vm_stat"])
        ps = re.search(r"page size of (\d+)", out)
        page = int(ps.group(1)) if ps else 4096
        free = 0
        for key in ("Pages free", "Pages inactive", "Pages speculative", "Pages purgeable"):
            m = re.search(key + r":\s+(\d+)", out)
            if m:
                free += int(m.group(1)) * page
        return total, (min(free, total) if total else free)
    mi = _meminfo()
    return mi.get("MemTotal", 0), mi.get("MemAvailable", mi.get("MemFree", 0))


def _cpuinfo():
    try:
        return open("/proc/cpuinfo", encoding="utf-8", errors="replace").read()
    except Exception:
        return ""


def cpu_name():
    try:
        if osys.WIN:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
        if osys.MAC:
            return _sysctl("machdep.cpu.brand_string") or "Apple " + platform.machine()
        m = re.search(r"^(model name|Hardware|cpu model)\s*:\s*(.+)$", _cpuinfo(), re.M)
        if m:
            return m.group(2).strip()
        m = re.search(r"Model name:\s*(.+)", _run(["lscpu"]))
        return m.group(1).strip() if m else (platform.processor() or tr("CPU desconocida"))
    except Exception:
        return tr("CPU desconocida")


def physical_cores():
    """Nucleos fisicos (en Apple Silicon, los de rendimiento: llama.cpp va mejor sin los de eficiencia)."""
    try:
        if osys.WIN:
            k32 = ctypes.windll.kernel32
            size = ctypes.c_ulong(0)
            k32.GetLogicalProcessorInformationEx(0, None, ctypes.byref(size))   # RelationProcessorCore = 0
            buf = ctypes.create_string_buffer(size.value)
            if k32.GetLogicalProcessorInformationEx(0, buf, ctypes.byref(size)):
                n, off = 0, 0
                while off < size.value:
                    rel, sz = ctypes.c_uint.from_buffer(buf, off).value, ctypes.c_uint.from_buffer(buf, off + 4).value
                    if rel == 0:
                        n += 1
                    off += sz
                if n:
                    return n
        elif osys.MAC:
            n = int(_sysctl("hw.perflevel0.physicalcpu") or _sysctl("hw.physicalcpu") or 0)
            if n:
                return n
        else:
            pairs, phys = set(), None
            for l in _cpuinfo().splitlines():
                if l.startswith("physical id"):
                    phys = l.split(":")[1].strip()
                elif l.startswith("core id"):
                    pairs.add((phys, l.split(":")[1].strip()))
            if pairs:
                return len(pairs)
            m = re.search(r"Core\(s\) per socket:\s*(\d+)[\s\S]*?Socket\(s\):\s*(\d+)", _run(["lscpu"]))
            if m:
                return int(m.group(1)) * int(m.group(2))
            return os.cpu_count() or 1        # ARM sin SMT: logicos = fisicos
    except Exception:
        pass
    return max(1, (os.cpu_count() or 2) // 2)


def has_avx2():
    try:
        if osys.WIN:
            return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(40))   # PF_AVX2_INSTRUCTIONS_AVAILABLE
        if platform.machine().lower() in ("arm64", "aarch64"):
            return True                                                          # no aplica (NEON)
        if osys.MAC:
            return "AVX2" in _sysctl("machdep.cpu.leaf7_features").upper()
        return " avx2" in _cpuinfo()
    except Exception:
        return True


def _nvidia_smi():
    exe = shutil.which("nvidia-smi") or (r"C:\Windows\System32\nvidia-smi.exe" if osys.WIN else "")
    return exe if exe and os.path.isfile(exe) else ""


def nvidia_gpus():
    """GPU NVIDIA: nombre, VRAM, versión del controlador y generación (compute capability, p. ej. 8.9)."""
    exe = _nvidia_smi()
    if not exe:
        return []
    res = []
    for fields in ("name,memory.total,driver_version,compute_cap", "name,memory.total,driver_version", "name,memory.total"):
        out = _run([exe, "--query-gpu=" + fields, "--format=csv,noheader,nounits"], 8)
        if not out.strip() or "not a valid field" in out.lower() or "invalid" in out.lower():
            continue
        for line in out.strip().splitlines():
            parts = [x.strip() for x in line.split(",")]
            try:
                g = {"name": parts[0], "vram": int(float(parts[1])) * 1024 * 1024, "vendor": "nvidia", "dedicated": True}
            except (IndexError, ValueError):
                continue
            if len(parts) > 2:
                g["driver"] = parts[2]
            if len(parts) > 3:
                try:
                    g["cc"] = float(parts[3])
                except ValueError:
                    pass
            res.append(g)
        break
    return res


def nvidia_cuda():
    """Versión de CUDA más alta que admite el controlador NVIDIA instalado («13.0»), o '' si no se sabe."""
    exe = _nvidia_smi()
    m = re.search(r"CUDA Version:\s*([\d.]+)", _run([exe], 8)) if exe else None
    return m.group(1) if m else ""


VENDORS = {"10DE": "nvidia", "1002": "amd", "1022": "amd", "8086": "intel", "106B": "apple"}
_VIRTUAL = re.compile(r"basic display|basic render|virtual|remote|parsec|rustdesk|indirect display|idd|citrix|vmware|hyper-v|"
                      r"displaylink|spacedesk|meta virtual", re.I)


def _vendor_of(name):
    n = (name or "").lower()
    return "nvidia" if re.search(r"nvidia|geforce|quadro|tesla|rtx", n) else "amd" if re.search(r"amd|radeon|ati ", n) else \
        "intel" if "intel" in n else "apple" if "apple" in n else ""


def _dedicated(g):
    """¿Gráfica dedicada que merece la pena? Las integradas no ayudan: medido en un i5-8250U con Intel UHD 620 (Vulkan,
    llama.cpp b12549), leer fue un 20-80 % más lento y escribir hasta 7 veces más lento que con el procesador."""
    n, v = (g.get("name") or "").lower(), int(g.get("vram") or 0)
    if g.get("vendor") == "nvidia":
        return True
    if g.get("vendor") == "amd":
        return v >= 2 * GB or bool(re.search(r"radeon (rx|pro)|instinct|firepro|radeon vii", n))
    if g.get("vendor") == "intel":
        return v >= 2 * GB and bool(re.search(r"arc(\(tm\))?\s*(pro\s*)?[ab]\d", n))
    return False


def _win_adapters():
    """Gráficas de Windows con su memoria de vídeo real (del registro del controlador: WMI se queda en 4 GB)."""
    import winreg
    present = [x.lower() for x in all_gpus()]          # (el registro guarda también las de antes: solo las que están)
    out = []
    base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    try:
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
    except OSError:
        return out
    i = 0
    while True:
        try:
            sub = winreg.EnumKey(k, i)
        except OSError:
            break
        i += 1
        if not sub.isdigit():
            continue
        try:
            sk = winreg.OpenKey(k, sub)
        except OSError:
            continue

        def val(name):
            try:
                return winreg.QueryValueEx(sk, name)[0]
            except OSError:
                return None
        name = str(val("DriverDesc") or "").strip()
        if not name or _VIRTUAL.search(name) or (present and name.lower() not in present):
            continue
        mem = val("HardwareInformation.qwMemorySize")
        if mem is None:
            mem = val("HardwareInformation.MemorySize")
        if isinstance(mem, (bytes, bytearray)):
            mem = int.from_bytes(bytes(mem[:8]), "little")
        ven = re.search(r"VEN_([0-9A-F]{4})", str(val("MatchingDeviceId") or "").upper())
        g = {"name": name, "vram": int(mem or 0), "vendor": VENDORS.get(ven.group(1), "") if ven else _vendor_of(name)}
        if not any(x["name"] == g["name"] for x in out):
            out.append(g)
    return out


def _linux_adapters():
    out = []
    import glob
    for d in sorted(glob.glob("/sys/class/drm/card[0-9]*/device")):
        try:
            ven = open(os.path.join(d, "vendor")).read().strip().upper().replace("0X", "")
        except OSError:
            continue
        vram = 0
        try:
            vram = int(open(os.path.join(d, "mem_info_vram_total")).read().strip())
        except (OSError, ValueError):
            pass
        out.append({"name": "", "vram": vram, "vendor": VENDORS.get(ven, "")})
    names = all_gpus()
    for g, n in zip(out, [n for n in names if _vendor_of(n)]):
        g["name"] = n
    return out


def gpu_list(nv=None):
    """Todas las gráficas: [{name, vendor, vram, dedicated, (driver, cc en NVIDIA)}]."""
    nv = nvidia_gpus() if nv is None else nv
    try:
        if osys.WIN:
            others = _win_adapters()
        elif osys.MAC:
            others = [{"name": n, "vram": 0, "vendor": _vendor_of(n) or ("apple" if APPLE_SILICON else "")} for n in all_gpus()]
        else:
            others = _linux_adapters()
    except Exception:
        others = []
    res = list(nv)
    for g in others:
        if g.get("vendor") == "nvidia" and nv:
            continue                                   # (las NVIDIA ya vienen con sus datos de nvidia-smi)
        g["dedicated"] = _dedicated(g)
        res.append(g)
    return res


def all_gpus():
    try:
        if osys.WIN:
            out = _run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name"], 15)
            return [l.strip() for l in out.splitlines() if l.strip()]
        if osys.MAC:
            out = _run(["system_profiler", "SPDisplaysDataType"], 20)
            return [m.strip() for m in re.findall(r"Chipset Model:\s*(.+)", out)] or (["Apple GPU"] if APPLE_SILICON else [])
        pat = r"VGA compatible controller|3D controller|Display controller"
        return [re.sub(r"^.*?(%s):\s*" % pat, "", l).strip() for l in _run(["lspci"]).splitlines() if re.search(pat, l)]
    except Exception:
        return []


def disk_free(path):
    p = os.path.abspath(path)
    while not os.path.exists(p):
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    try:
        return shutil.disk_usage(p).free
    except Exception:
        return 0


def detect():
    total, avail = ram()
    nv = nvidia_gpus()
    gl = gpu_list(nv)
    hw = {"cpu": cpu_name(), "cores": physical_cores(), "logical": os.cpu_count() or 1, "avx2": has_avx2(),
          "ram": total, "ram_free": avail, "nvidia": nv, "gpus": [g["name"] for g in gl] or all_gpus(), "gpu_list": gl,
          "cuda": nvidia_cuda() if nv else "", "unified": APPLE_SILICON, "os": osys.os_label(), "arch": platform.machine().lower()}
    eng = recommend_engine(hw)
    hw["vram"] = eng["vram"]                           # la memoria de vídeo que usaría el motor recomendado
    hw["engine"] = eng
    return hw


MIN_VRAM = 3 * GB          # con menos, repartir el modelo entre la gráfica y la RAM apenas gana nada


def recommend_engine(hw):
    """El motor de llama.cpp adecuado a este equipo: {'backend': metal | cuda | vulkan | cpu, 'cuda': '13' | '12' | '',
    'gpu': nombre, 'vram': bytes que usaría, 'why': motivo}. CUDA 13 si el controlador lo admite y la gráfica es de 2018 o
    posterior (CUDA 13 dejó fuera las anteriores); si no, CUDA 12; con un controlador muy antiguo, Vulkan."""
    arm = (hw.get("arch") or platform.machine().lower()) in ("arm64", "aarch64")
    if osys.MAC:
        if APPLE_SILICON:
            return {"backend": "metal", "cuda": "", "gpu": "Apple", "vram": 0, "why": tr("Mac con Apple Silicon: Metal usa la memoria unificada.")}
        return {"backend": "cpu", "cuda": "", "gpu": "", "vram": 0, "why": tr("En los Mac con Intel llama.cpp no acelera con la gráfica.")}
    gl = hw.get("gpu_list") or [dict(g, vendor="nvidia", dedicated=True) for g in hw.get("nvidia") or []]
    nv = [g for g in gl if g.get("vendor") == "nvidia" and int(g.get("vram") or 0) >= MIN_VRAM]
    if nv:
        best = max(nv, key=lambda g: g["vram"])
        try:
            major = int(float((hw.get("cuda") or "0").split(".")[0]))
        except ValueError:
            major = 0
        cc = float(best.get("cc") or 0)
        vram = sum(g["vram"] for g in nv)
        if major >= 13 and (cc >= 7.5 or not cc):
            return {"backend": "cuda", "cuda": "13", "gpu": best["name"], "vram": vram, "why": tr("Gráfica NVIDIA: CUDA 13.")}
        if major >= 12 and not arm:
            return {"backend": "cuda", "cuda": "12", "gpu": best["name"], "vram": vram,
                    "why": tr("Gráfica NVIDIA: CUDA 12 (por su controlador o su generación).")}
        return {"backend": "vulkan", "cuda": "", "gpu": best["name"], "vram": vram,
                "why": tr("Gráfica NVIDIA con un controlador antiguo: Vulkan (actualizar el controlador permitiría CUDA, más rápido).")}
    ded = [g for g in gl if g.get("dedicated") and g.get("vendor") in ("amd", "intel") and int(g.get("vram") or 0) >= MIN_VRAM]
    if ded:
        best = max(ded, key=lambda g: g["vram"])
        return {"backend": "vulkan", "cuda": "", "gpu": best["name"], "vram": sum(g["vram"] for g in ded),
                "why": tr("Gráfica AMD o Intel dedicada: Vulkan.")}
    small = [g for g in gl if g.get("dedicated")]
    why = tr("La gráfica tiene poca memoria de vídeo: el procesador va igual o mejor.") if small else \
        tr("Sin gráfica dedicada: el procesador (las integradas van más lentas que él).")
    return {"backend": "cpu", "cuda": "", "gpu": "", "vram": 0, "why": why}


def recommend_backend(hw):
    """Motor de llama.cpp: metal (Apple Silicon), cuda (NVIDIA), vulkan (AMD/Intel dedicadas) o cpu."""
    return (hw.get("engine") or recommend_engine(hw))["backend"]


def memory_budget(hw, vision=True):
    """Bytes disponibles para los pesos del modelo dejando margen al sistema, al contexto y a la vision."""
    reserve = 4.5 * GB + 1.0 * GB + (0.9 * GB if vision else 0)
    if hw.get("unified"):
        reserve = max(reserve, hw["ram"] * 0.25)          # Metal solo deja usar ~75 % de la memoria unificada
    budget = hw["ram"] - reserve
    if hw["vram"]:
        budget += hw["vram"] - 1.0 * GB
    return max(0, budget)


def classify(size, hw, vision=True):
    """'ok' cabe con margen, 'tight' cabe justo, 'no' no cabe."""
    b = memory_budget(hw, vision)
    if size <= b:
        return "ok"
    if size <= b + 2.5 * GB:
        return "tight"
    return "no"


def bits_per_weight(label):
    """Bits por peso aproximados de una cuantizacion (para comparar variantes)."""
    s = (label or "").upper()
    for pat, b in ((r"F32", 32), (r"BF16|F16|FP16", 16), (r"Q8", 8.5), (r"Q6", 6.6), (r"Q5", 5.5), (r"MXFP4", 4.3), (r"IQ4|Q4", 4.8),
                   (r"Q3", 3.9), (r"IQ3", 3.4), (r"Q2", 3.0), (r"IQ2", 2.5), (r"IQ1|Q1", 1.8)):
        if re.search(pat, s):
            return b
    return 6.0


def fast_memory(hw, size):
    """True si el modelo entero cabe en memoria rapida (VRAM de NVIDIA o memoria unificada de Apple)."""
    return bool(hw.get("unified")) or (hw.get("vram", 0) and size <= hw["vram"] - 1.0 * GB)


def recommend_quant(quants, hw, vision=True):
    """Variante recomendada: la de mas calidad que cabe con margen, pero nunca 16/32 bits (no mejoran a Q8 y son
    mucho mas lentas) y, si el modelo corre en CPU, de la familia Q4 (la velocidad depende del tamaño)."""
    quants = [q for q in quants if not q.get("aux")] or quants
    if not quants:
        return None
    lab = lambda q: q.get("label") or q.get("file") or ""
    base = [q for q in quants if bits_per_weight(lab(q)) < 16] or quants
    fit = [q for q in base if classify(q["size"], hw, vision) == "ok"]
    good = [q for q in fit if bits_per_weight(lab(q)) >= 3.4]          # evitar 1-2 bits si hay otra
    pool = good or fit
    if not pool:
        return min(quants, key=lambda q: q["size"])
    gpu = fast_memory(hw, max(q["size"] for q in pool))
    cap = 8.5 if gpu else 5.0
    capped = [q for q in pool if bits_per_weight(lab(q)) <= cap] or pool
    pref = [q for q in capped if re.search(r"(?i)(UD-)?Q4_K_(M|XL)$", lab(q).split()[0])]
    if not gpu and pref:
        return max(pref, key=lambda q: q["size"])
    return max(capped, key=lambda q: q["size"])


# ---------------------------------------------------------------- modelos del catalogo en este equipo
Q4_BYTES = 0.61            # bytes por parametro de una Q4_K_M (~4.85 bits)


def model_size(params):
    """Tamaño aproximado de la descarga recomendada (Q4) de un modelo de 'params' parametros."""
    return params * Q4_BYTES + 0.25 * GB


def est_speed(entry, hw):
    """Tokens por segundo aproximados al generar: la memoria se lee entera por cada palabra (solo los expertos activos
    en los MoE). CPU de portatil ~14 GB/s utiles; GPU NVIDIA ~250 GB/s; memoria unificada de Apple ~90 GB/s."""
    size = model_size(entry["params"])
    bw = 250e9 if (hw.get("vram") and size <= hw["vram"] - 1.0 * GB) else (90e9 if hw.get("unified") else 14e9)
    per_token = entry.get("active", entry["params"]) * Q4_BYTES
    return 0.6 * bw / max(per_token, 1)


def capability(entry):
    """Capacidad aproximada para ordenar: en los MoE cuenta la media geometrica entre activos y totales."""
    import math
    return math.sqrt(entry["params"] * entry.get("active", entry["params"]))


def rate_models(entries, hw, vision=False):
    """Añade a cada modelo del catalogo: size (descarga Q4), fit (ok/tight/no) y speed (tok/s aprox.)."""
    out = []
    for e in entries:
        e = dict(e)
        e["size"] = model_size(e["params"])
        e["fit"] = classify(e["size"], hw, vision and e.get("vision"))
        e["speed"] = est_speed(e, hw)
        out.append(e)
    return out


def recommend_model(rated, min_speed=3.0):
    """El modelo mas capaz que cabe con margen y va a una velocidad comoda (>= ~3 tok/s, necesaria para un agente);
    si ninguno llega, el mas rapido de los que caben."""
    ok = [e for e in rated if e["fit"] == "ok"]
    if not ok:
        return None
    # el agente de Jayth trabaja con herramientas: entre los que caben se prefieren los que saben usarlas
    agents = [e for e in ok if e.get("tools")]
    ok = agents or ok
    fast = [e for e in ok if e["speed"] >= min_speed]
    if fast:
        return max(fast, key=lambda e: (capability(e), e.get("downloads", 0)))
    return max(ok, key=lambda e: e["speed"])


def human(n):
    from .i18n import size
    return size(n)


def summary(hw):
    ded = [x for x in hw.get("gpu_list") or [] if x.get("dedicated")]
    g = ", ".join("%s (%s)" % (x["name"], human(x["vram"])) for x in ded or hw["nvidia"]) or \
        (", ".join(hw["gpus"]) + (" · " + tr("integrada") if hw["gpus"] else "") if hw["gpus"] else tr("sin GPU dedicada"))
    if hw.get("unified"):
        g += " · " + tr("memoria unificada")
    return tr("%s · %d núcleos · RAM %s · GPU: %s") % (hw["cpu"], hw["cores"], human(hw["ram"]), g)
