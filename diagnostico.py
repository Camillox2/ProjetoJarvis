"""
Diagnóstico completo do ambiente Keilinks.
Roda antes de iniciar pra garantir que tudo está certo.
"""

import sys
import subprocess
import importlib

OK   = "[  OK  ]"
FAIL = "[ ERRO ]"
WARN = "[ AVISO]"

def check(label: str, ok: bool, detail: str = "", warn: bool = False):
    icon = OK if ok else (WARN if warn else FAIL)
    line = f"  {icon}  {label}"
    if detail:
        line += f"  →  {detail}"
    print(line)
    return ok


def section(title: str):
    print(f"\n{'─' * 55}")
    print(f"  {title}")
    print('─' * 55)


# ─── Python ──────────────────────────────────────────────────────────────────
section("Python")
py_ver = sys.version_info
check(
    "Versão do Python",
    py_ver >= (3, 10),
    f"{py_ver.major}.{py_ver.minor}.{py_ver.micro}",
    warn=py_ver < (3, 10),
)


# ─── CUDA e GPU ──────────────────────────────────────────────────────────────
section("NVIDIA / CUDA")

try:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
        capture_output=True, text=True, timeout=5
    )
    gpu_info = result.stdout.strip()
    check("nvidia-smi", bool(gpu_info), gpu_info)
except Exception as e:
    check("nvidia-smi", False, str(e))

try:
    result = subprocess.run(["nvcc", "--version"], capture_output=True, text=True, timeout=5)
    lines = result.stdout.strip().splitlines()
    cuda_line = next((l for l in lines if "release" in l.lower()), "")
    check("CUDA Toolkit", bool(cuda_line), cuda_line.strip())
except Exception as e:
    check("CUDA Toolkit", False, str(e))

try:
    import torch
    cuda_ok = torch.cuda.is_available()
    check("PyTorch CUDA", cuda_ok, f"torch {torch.__version__} | CUDA disponível: {cuda_ok}")
    if cuda_ok:
        gpu_name = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        check("GPU detectada", True, f"{gpu_name} | {vram:.1f} GB VRAM")
except ImportError:
    check("PyTorch", False, "não instalado — rode instalar.bat")


# ─── Pacotes Python ──────────────────────────────────────────────────────────
section("Pacotes")

packages = {
    "faster_whisper": "faster-whisper",
    "edge_tts":       "edge-tts",
    "sounddevice":    "sounddevice",
    "soundfile":      "soundfile",
    "numpy":          "numpy",
    "pygame":         "pygame",
    "cv2":            "opencv-python",
    "httpx":          "httpx",
}

for module, pkg in packages.items():
    try:
        m = importlib.import_module(module)
        ver = getattr(m, "__version__", "?")
        check(pkg, True, f"v{ver}")
    except ImportError:
        check(pkg, False, "não instalado")


# ─── Ollama ───────────────────────────────────────────────────────────────────
section("Ollama")

try:
    import httpx
    r = httpx.get("http://localhost:11434/api/tags", timeout=3)
    data = r.json()
    models = [m["name"] for m in data.get("models", [])]
    check("Ollama rodando", True, f"http://localhost:11434")

    target = "qwen3-vl:8b"
    found = any(target in m for m in models)
    check(
        f"Modelo {target}",
        found,
        "baixado e pronto" if found else f"NÃO encontrado — rode: ollama pull {target}",
        warn=not found,
    )
    if models:
        print(f"           Modelos disponíveis: {', '.join(models)}")
except Exception as e:
    check("Ollama rodando", False, f"não responde — rode 'ollama serve' | {e}")


# ─── Microfone ───────────────────────────────────────────────────────────────
section("Áudio")

try:
    import sounddevice as sd
    devices = sd.query_devices()
    input_devices = [(i, d) for i, d in enumerate(devices) if d["max_input_channels"] > 0]

    check("sounddevice", True, f"{len(input_devices)} dispositivo(s) de entrada encontrado(s)")

    print("\n  Dispositivos de entrada disponíveis:")
    for i, d in input_devices:
        marker = "  ←  PADRÃO" if i == sd.default.device[0] else ""
        print(f"      [{i:2d}] {d['name']}{marker}")

    default_in = sd.default.device[0]
    check("Microfone padrão", default_in is not None, f"índice {default_in}")
except Exception as e:
    check("sounddevice", False, str(e))


# ─── Câmera ───────────────────────────────────────────────────────────────────
section("Câmera")

try:
    import cv2
    cap = cv2.VideoCapture(0)
    ok = cap.isOpened()
    if ok:
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        check("Câmera (índice 0)", True, f"{w}x{h}")
    else:
        check("Câmera (índice 0)", False, "não encontrada")
    cap.release()
except Exception as e:
    check("Câmera", False, str(e))


# ─── Internet (edge-tts) ──────────────────────────────────────────────────────
section("Conectividade")

try:
    import httpx
    r = httpx.get("https://www.msedge.net", timeout=5)
    check("Internet (edge-tts)", r.status_code < 400, "Microsoft TTS acessível")
except Exception:
    check("Internet (edge-tts)", False, "sem conexão — TTS não vai funcionar", warn=True)


# ─── Resumo ───────────────────────────────────────────────────────────────────
print(f"\n{'═' * 55}")
print("  Diagnóstico concluído.")
print("  Se tudo está OK, rode: iniciar.bat")
print('═' * 55)
