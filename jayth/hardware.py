"""Deteccion del hardware y recomendacion de cuantizacion / motor. Funciona en cualquier PC con Windows."""
import os, re, shutil, ctypes, subprocess

GB = 1024 ** 3
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class _MEM(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def ram():
    m = _MEM()
    m.dwLength = ctypes.sizeof(_MEM)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullTotalPhys, m.ullAvailPhys


def cpu_name():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
    except Exception:
        return "CPU desconocida"


def physical_cores():
    """Nucleos fisicos via GetLogicalProcessorInformationEx; si falla, la mitad de los logicos."""
    try:
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
    except Exception:
        pass
    return max(1, (os.cpu_count() or 2) // 2)


def has_avx2():
    try:
        return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(40))   # PF_AVX2_INSTRUCTIONS_AVAILABLE
    except Exception:
        return True


def nvidia_gpus():
    exe = shutil.which("nvidia-smi") or r"C:\Windows\System32\nvidia-smi.exe"
    if not os.path.isfile(exe):
        return []
    try:
        out = subprocess.run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], capture_output=True,
                             text=True, timeout=8, creationflags=NO_WINDOW).stdout
        res = []
        for line in out.strip().splitlines():
            name, mem = [x.strip() for x in line.rsplit(",", 1)]
            res.append({"name": name, "vram": int(float(mem)) * 1024 * 1024})
        return res
    except Exception:
        return []


def all_gpus():
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name"],
                             capture_output=True, text=True, timeout=15, creationflags=NO_WINDOW).stdout
        return [l.strip() for l in out.splitlines() if l.strip()]
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
    gpus = all_gpus()
    return {"cpu": cpu_name(), "cores": physical_cores(), "logical": os.cpu_count() or 1, "avx2": has_avx2(),
            "ram": total, "ram_free": avail, "nvidia": nv, "gpus": gpus,
            "vram": max((g["vram"] for g in nv), default=0)}


def recommend_backend(hw):
    if hw["nvidia"]:
        return "cuda"
    discrete = [g for g in hw["gpus"] if re.search(r"radeon rx|arc a|arc b|radeon pro", g, re.I)]
    return "vulkan" if discrete else "cpu"


def memory_budget(hw, vision=True):
    """Bytes disponibles para los pesos del modelo dejando margen al sistema, al contexto y a la vision."""
    reserve = 4.5 * GB + 1.0 * GB + (0.9 * GB if vision else 0)
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


def recommend_quant(quants, hw, vision=True):
    """De una lista de {file,size} elige la mas grande que cabe con margen (evitando las de 1-2 bits si hay otra)."""
    quants = [q for q in quants if not q.get("aux")] or quants
    fit = [q for q in quants if classify(q["size"], hw, vision) == "ok"]
    good = [q for q in fit if not re.search(r"IQ1|IQ2|Q2_", q["file"], re.I)]
    pool = good or fit
    if not pool:
        return min(quants, key=lambda q: q["size"]) if quants else None
    pool = [q for q in pool if q["size"] < 30 * GB] or pool    # mas alla de Q8 no aporta
    return max(pool, key=lambda q: q["size"])


def human(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return ("%.0f %s" if u in ("B", "KB") else "%.1f %s") % (n, u)
        n /= 1024


def summary(hw):
    g = ", ".join("%s (%s)" % (x["name"], human(x["vram"])) for x in hw["nvidia"]) or (", ".join(hw["gpus"]) or "sin GPU dedicada")
    return "%s · %d núcleos · RAM %s · GPU: %s" % (hw["cpu"], hw["cores"], human(hw["ram"]), g)
