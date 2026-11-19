"""Deteccion del hardware y recomendacion de cuantizacion / motor en Windows, macOS y Linux."""
import os, re, shutil, ctypes, platform, subprocess
from . import osys

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
        return m.group(1).strip() if m else (platform.processor() or "CPU desconocida")
    except Exception:
        return "CPU desconocida"


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


def nvidia_gpus():
    exe = shutil.which("nvidia-smi") or (r"C:\Windows\System32\nvidia-smi.exe" if osys.WIN else "")
    if not exe or not os.path.isfile(exe):
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
    gpus = all_gpus()
    return {"cpu": cpu_name(), "cores": physical_cores(), "logical": os.cpu_count() or 1, "avx2": has_avx2(),
            "ram": total, "ram_free": avail, "nvidia": nv, "gpus": gpus, "unified": APPLE_SILICON,
            "vram": max((g["vram"] for g in nv), default=0), "os": osys.os_label(), "arch": platform.machine().lower()}


def recommend_backend(hw):
    """Motor de llama.cpp: metal (Apple Silicon), cuda (NVIDIA), vulkan (AMD/Intel Arc) o cpu."""
    if osys.MAC:
        return "metal" if APPLE_SILICON else "cpu"
    if platform.machine().lower() in ("arm64", "aarch64"):
        return "cpu"
    if hw["nvidia"]:
        return "cuda"
    discrete = [g for g in hw["gpus"] if re.search(r"radeon rx|arc a|arc b|radeon pro|navi|vega", g, re.I)]
    return "vulkan" if discrete else "cpu"


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
    if hw.get("unified"):
        g += " · memoria unificada"
    return "%s · %d núcleos · RAM %s · GPU: %s" % (hw["cpu"], hw["cores"], human(hw["ram"]), g)
