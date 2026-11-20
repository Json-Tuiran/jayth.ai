# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Voz: dictar el mensaje con el micrófono y escuchar las respuestas en voz alta. Todo en este equipo.

- Escuchar: voces del sistema (Qt TextToSpeech: SAPI/WinRT en Windows, AVSpeech en macOS, speech-dispatcher en Linux).
- Dictar: se graba con el micrófono (Qt Multimedia) y se transcribe con Whisper (faster-whisper) en un Python aislado
  que Jayth prepara una sola vez con uv, igual que el entorno de análisis. El modelo de voz se descarga la primera vez.
"""
import os, re, sys, json, wave, struct, subprocess, tempfile
from . import paths, osys

HOME = os.path.join(paths.RUNTIME_DIR, "voice")
MODELS = {"tiny": "Muy rápido, menos preciso (75 MB)", "base": "Equilibrado (145 MB)", "small": "Más preciso, más lento (480 MB)"}

TRANSCRIBE = r'''
import sys, json, wave
import numpy as np
from faster_whisper import WhisperModel
wav, size, root, lang = sys.argv[1], sys.argv[2], sys.argv[3], (sys.argv[4] if len(sys.argv) > 4 else "")
# el WAV (PCM de 16 bits) se lee aquí mismo y se pasa a 16 kHz mono: así no depende del decodificador de audio
with wave.open(wav, "rb") as w:
    ch, rate, n = w.getnchannels(), w.getframerate(), w.getnframes()
    audio = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
if ch > 1:
    audio = audio.reshape(-1, ch).mean(axis=1)
if rate != 16000 and len(audio):
    audio = np.interp(np.linspace(0, len(audio) - 1, int(len(audio) * 16000 / rate)), np.arange(len(audio)), audio).astype(np.float32)
from faster_whisper.utils import download_model
path = download_model(size, cache_dir=root, local_files_only=True)     # ya descargado al preparar el dictado
model = WhisperModel(path, device="cpu", compute_type="int8")
segments, info = model.transcribe(audio, language=lang or None, vad_filter=True, beam_size=3, initial_prompt="Jayth.")
text = " ".join(s.text.strip() for s in segments).strip()
print("JAYTH_JSON " + json.dumps({"text": text, "language": info.language}, ensure_ascii=False))
'''

DOWNLOAD = r'''
import sys
from faster_whisper.utils import download_model
print("JAYTH_PATH " + download_model(sys.argv[1], cache_dir=sys.argv[2]))
'''


def _env():
    """Entorno del Python de voz: sin la configuración de certificados de Jayth (usa la suya), con la caché de
    Hugging Face dentro de la carpeta de voz y sin el componente Xet (descargas normales: falló en un equipo con
    «entity not found (os error 2)»)."""
    env = {k: v for k, v in os.environ.items() if k not in ("SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
                                                             "PYTHONHOME", "PYTHONPATH")}
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", HF_HOME=os.path.join(HOME, "hf"), HF_HUB_DISABLE_XET="1",
               HF_HUB_DISABLE_SYMLINKS_WARNING="1", HF_HUB_DISABLE_TELEMETRY="1", HF_HUB_DISABLE_PROGRESS_BARS="1",
               HF_HUB_ETAG_TIMEOUT="30", HF_HUB_DOWNLOAD_TIMEOUT="60")
    return env


def _explain(stderr, what):
    """Mensaje entendible a partir del error; el detalle completo queda en runtime/voice/ultimo_error.txt."""
    text = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else str(stderr)
    try:
        with open(os.path.join(HOME, "ultimo_error.txt"), "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith(("warnings.warn", "File ", "^"))]
    key = next((l for l in reversed(lines) if re.search(r"(?i)error|exception|refused|timed? ?out|not found|denied", l)), lines[-1] if lines else "")
    if re.search(r"(?i)connection|resolve|timed? ?out|getaddrinfo|ssl|certificate|offline|LocalEntryNotFound|internet", text):
        return "%s: no se pudo descargar el modelo de voz (¿sin internet?). Inténtalo de nuevo con conexión." % what
    if re.search(r"RIFF|wave\.Error|EOFError|unpack requires", text):
        return "%s: la grabación está vacía o dañada. Vuelve a intentarlo." % what
    if re.search(r"(?i)MemoryError|bad allocation|out of memory", text):
        return "%s: no hay memoria suficiente; prueba la precisión «Tiny» en Ajustes › Personalización › Voz." % what
    return "%s: %s" % (what, key[:240] or "error desconocido")


def model_ready(model="base"):
    root = os.path.join(HOME, "models", "models--Systran--faster-whisper-%s" % model)
    return os.path.isdir(os.path.join(root, "snapshots")) and any(
        os.path.isfile(os.path.join(root, "snapshots", d, "model.bin")) for d in os.listdir(os.path.join(root, "snapshots")))


def ensure_model(model="base", tries=3):
    """Descarga (una vez) el modelo de voz elegido, con reintentos."""
    if model_ready(model):
        return
    script = os.path.join(HOME, "descargar_modelo.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(DOWNLOAD)
    err = b""
    for _ in range(tries):
        r = subprocess.run([env_python(), script, model, os.path.join(HOME, "models")], capture_output=True, timeout=1800,
                           env=_env(), **osys.popen_kwargs())
        if r.returncode == 0 and model_ready(model):
            return
        err = r.stderr or r.stdout
    raise RuntimeError(_explain(err, "No se pudo preparar el dictado"))


# ---------------------------------------------------------------- dictado (voz a texto)
def env_python():
    return os.path.join(HOME, "env", "Scripts", "python.exe") if osys.WIN else os.path.join(HOME, "env", "bin", "python")


def stt_ready():
    return os.path.isfile(env_python()) and os.path.isfile(os.path.join(HOME, "ready.json"))


def ensure_stt(progress=None, stop=None, model="base"):
    """Prepara (una vez) el Python aislado con faster-whisper y descarga el modelo de voz."""
    from . import analysis
    if not os.path.isfile(env_python()) or not os.path.isfile(os.path.join(HOME, "ready.json")):
        analysis.make_env(HOME, ["faster-whisper"], progress, stop)
        with open(os.path.join(HOME, "ready.json"), "w") as f:
            json.dump({"ok": True}, f)
    ensure_model(model if model in MODELS else "base")
    return env_python()


def transcribe(wav_path, model="base", lang="", timeout=600):
    """Texto de una grabación (si falta el modelo elegido, lo descarga antes)."""
    if not stt_ready():
        raise RuntimeError("El dictado aún no está preparado.")
    model = model if model in MODELS else "base"
    ensure_model(model)
    script = os.path.join(HOME, "transcribir.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(TRANSCRIBE)
    r = subprocess.run([env_python(), script, wav_path, model, os.path.join(HOME, "models"), lang or ""],
                       capture_output=True, timeout=timeout, env=_env(), **osys.popen_kwargs())
    out = r.stdout.decode("utf-8", "replace")
    for line in out.splitlines():
        if line.startswith("JAYTH_JSON "):
            return json.loads(line[11:])["text"]
    raise RuntimeError(_explain(r.stderr or r.stdout, "No se pudo transcribir"))


class Recorder:
    """Graba del micrófono predeterminado a un WAV de 16 bits."""

    def __init__(self):
        self.src, self.buf, self.fmt = None, None, None

    @staticmethod
    def available():
        try:
            from PySide6.QtMultimedia import QMediaDevices
            return bool(QMediaDevices.audioInputs())
        except Exception:
            return False

    def start(self):
        from PySide6.QtMultimedia import QMediaDevices, QAudioSource, QAudioFormat
        from PySide6.QtCore import QBuffer, QIODevice
        dev = QMediaDevices.defaultAudioInput()
        if dev.isNull():
            raise RuntimeError("No encuentro ningún micrófono.")
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.Int16)
        if not dev.isFormatSupported(fmt):
            fmt = dev.preferredFormat()
        self.fmt = fmt
        self.buf = QBuffer()
        self.buf.open(QIODevice.ReadWrite)
        self.src = QAudioSource(dev, fmt)
        self.src.start(self.buf)

    def recording(self):
        return self.src is not None

    def level(self):
        """Volumen de los últimos 60 ms (0 a 1), para dibujar la onda mientras se graba."""
        if self.src is None or self.buf is None:
            return 0.0
        from PySide6.QtMultimedia import QAudioFormat
        fmt = self.fmt
        sf = fmt.sampleFormat()
        width = {QAudioFormat.Float: 4, QAudioFormat.Int32: 4, QAudioFormat.UInt8: 1}.get(sf, 2)
        n = max(1, int(fmt.sampleRate() * fmt.channelCount() * 0.06)) * width
        raw = bytes(self.buf.buffer().right(n))
        cnt = len(raw) // width
        if not cnt:
            return 0.0
        raw = raw[:cnt * width]
        if sf == QAudioFormat.Float:
            vals = struct.unpack("<%df" % cnt, raw)
        elif sf == QAudioFormat.Int32:
            vals = [v / 2147483648.0 for v in struct.unpack("<%di" % cnt, raw)]
        elif sf == QAudioFormat.UInt8:
            vals = [(b - 128) / 128.0 for b in raw]
        else:
            vals = [v / 32768.0 for v in struct.unpack("<%dh" % cnt, raw)]
        rms = (sum(v * v for v in vals) / cnt) ** 0.5
        return min(1.0, (rms / 0.2) ** 0.6)            # la voz normal llena media barra; un grito, la barra entera

    def cancel(self):
        if self.src is not None:
            self.src.stop()
        self.src, self.buf = None, None

    def stop(self, path=None):
        """Detiene la grabación y devuelve la ruta del WAV (o None si no se grabó nada)."""
        from PySide6.QtMultimedia import QAudioFormat
        if self.src is None:
            return None
        self.src.stop()
        raw = bytes(self.buf.data())
        fmt, self.src, self.buf = self.fmt, None, None
        ch, rate, sf = fmt.channelCount(), fmt.sampleRate(), fmt.sampleFormat()
        if sf == QAudioFormat.Float:
            n = len(raw) // 4
            vals = struct.unpack("<%df" % n, raw[:n * 4])
            pcm = struct.pack("<%dh" % n, *(max(-32768, min(32767, int(v * 32767))) for v in vals))
        elif sf == QAudioFormat.Int32:
            n = len(raw) // 4
            pcm = struct.pack("<%dh" % n, *(v >> 16 for v in struct.unpack("<%di" % n, raw[:n * 4])))
        elif sf == QAudioFormat.UInt8:
            pcm = struct.pack("<%dh" % len(raw), *((b - 128) << 8 for b in raw))
        else:
            pcm = raw
        if len(pcm) < rate * ch * 2 * 0.3:           # menos de 0,3 s: nada que transcribir
            return None
        path = path or os.path.join(tempfile.gettempdir(), "jayth_dictado.wav")
        with wave.open(path, "wb") as w:
            w.setnchannels(ch)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(pcm)
        return path


# ---------------------------------------------------------------- lectura (texto a voz)
def speakable(md):
    """Texto de una respuesta sin marcas de formato, código ni enlaces, para leerlo en voz alta."""
    t = re.sub(r"```.*?```", " (bloque de código) ", md or "", flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", " enlace ", t)
    t = re.sub(r"^\s*\|?[\s:|-]{3,}\|?\s*$", " ", t, flags=re.M)        # separadores de tablas
    t = t.replace("|", ", ")
    t = re.sub(r"^\s{0,3}(#{1,6}|[-*+]|\d+[.)])\s+", "", t, flags=re.M)
    t = re.sub(r"[*_~>#]+", "", t)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{2,}", ". ", t)).replace("\n", " ").strip()


class Speaker:
    """Lee texto con una voz del sistema, prefiriendo una en el idioma del texto."""

    def __init__(self):
        self.tts = None

    def _engine(self):
        if self.tts is None:
            from PySide6.QtTextToSpeech import QTextToSpeech
            from PySide6.QtCore import QCoreApplication
            import time
            self.tts = QTextToSpeech()
            end = time.time() + 3             # el motor del sistema se inicia en segundo plano: hasta que no está
            while self.tts.state() != QTextToSpeech.Ready and time.time() < end:    # listo, ignora lo que se le pida leer
                QCoreApplication.processEvents()
                time.sleep(0.02)
        return self.tts

    @staticmethod
    def available():
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
            return any(e != "mock" for e in QTextToSpeech.availableEngines())
        except Exception:
            return False

    def speaking(self):
        from PySide6.QtTextToSpeech import QTextToSpeech
        return self.tts is not None and self.tts.state() in (QTextToSpeech.Speaking, QTextToSpeech.Synthesizing)

    def speak(self, text, rate=0.0):
        t = self._engine()
        t.stop()
        txt = speakable(text)
        if not txt:
            return False
        spanish = len(re.findall(r"\b(el|la|los|las|que|de|y|en|es|para|con|una?|por|no|se)\b", txt.lower())) >= max(2, len(txt.split()) // 14)
        want = "es" if spanish else "en"
        voices = [v for v in t.availableVoices() if v.locale().name().lower().startswith(want)]
        if voices:
            t.setVoice(voices[0])
        t.setRate(max(-1.0, min(1.0, float(rate))))
        t.say(txt[:6000])
        return True

    def stop(self):
        if self.tts is not None:
            self.tts.stop()
