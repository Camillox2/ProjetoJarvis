"""
Monitoramento de hardware em tempo real.
CPU, RAM, GPU, disco, temperatura, bateria.
Alertas proativos quando algo está no limite.
"""

import threading
import time
import psutil
from typing import Callable


class SystemStats:
    def __init__(self, on_alert: Callable[[str], None] | None = None):
        self._on_alert  = on_alert
        self._watching  = False
        self._thread: threading.Thread | None = None

        # Thresholds para alertas proativos
        self.ALERT_CPU_PERCENT  = 95.0   # elevado: LLM consome CPU facilmente
        self.ALERT_RAM_PERCENT  = 92.0
        self.ALERT_GPU_PERCENT  = 99.0   # elevado: LLM sempre usa ~97% — não é alarme
        self.ALERT_TEMP_C       = 88.0
        self.ALERT_BATTERY_PCT  = 15.0
        self._last_alerts: dict[str, float] = {}   # evita spam (cooldown 60s)
        self._suppress: bool = False  # True durante inferência do LLM

    # ─── Leitura instantânea ──────────────────────────────────────────────────
    def get_cpu(self) -> dict:
        return {
            "percent": psutil.cpu_percent(interval=0.5),
            "cores":   psutil.cpu_count(logical=False),
            "threads": psutil.cpu_count(logical=True),
            "freq_mhz": round(psutil.cpu_freq().current) if psutil.cpu_freq() else 0,
        }

    def get_ram(self) -> dict:
        m = psutil.virtual_memory()
        return {
            "total_gb":  round(m.total / 1e9, 1),
            "used_gb":   round(m.used  / 1e9, 1),
            "percent":   m.percent,
        }

    def get_disk(self, path: str = "C:/") -> dict:
        d = psutil.disk_usage(path)
        return {
            "total_gb": round(d.total / 1e9, 1),
            "used_gb":  round(d.used  / 1e9, 1),
            "free_gb":  round(d.free  / 1e9, 1),
            "percent":  d.percent,
        }

    def get_gpu(self) -> dict | None:
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if not gpus:
                return None
            g = gpus[0]
            return {
                "name":       g.name,
                "load_pct":   round(g.load * 100, 1),
                "vram_used_mb": round(g.memoryUsed),
                "vram_total_mb": round(g.memoryTotal),
                "vram_pct":   round(g.memoryUsed / g.memoryTotal * 100, 1),
                "temp_c":     g.temperature,
            }
        except ImportError:
            return None
        except Exception:
            return None

    def get_temps(self) -> dict:
        try:
            temps = psutil.sensors_temperatures()
            result = {}
            for name, entries in temps.items():
                if entries:
                    result[name] = round(entries[0].current, 1)
            return result
        except Exception:
            return {}

    def get_battery(self) -> dict | None:
        b = psutil.sensors_battery()
        if not b:
            return None
        return {
            "percent":   round(b.percent, 1),
            "plugged":   b.power_plugged,
            "secs_left": b.secsleft if b.secsleft != psutil.POWER_TIME_UNLIMITED else None,
        }

    def get_top_processes(self, n: int = 5) -> list[dict]:
        procs = []
        for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except Exception:
                pass
        return sorted(procs, key=lambda x: x.get("cpu_percent", 0), reverse=True)[:n]

    def summary_text(self) -> str:
        """Resumo em texto para a Keilinks falar."""
        cpu  = self.get_cpu()
        ram  = self.get_ram()
        gpu  = self.get_gpu()
        bat  = self.get_battery()

        lines = [
            f"CPU: {cpu['percent']}% a {cpu['freq_mhz']}MHz",
            f"RAM: {ram['used_gb']}GB de {ram['total_gb']}GB ({ram['percent']}%)",
        ]
        if gpu:
            lines.append(
                f"GPU {gpu['name']}: {gpu['load_pct']}% | "
                f"VRAM {gpu['vram_used_mb']}MB/{gpu['vram_total_mb']}MB | "
                f"{gpu['temp_c']}°C"
            )
        if bat:
            plug = "carregando" if bat["plugged"] else "na bateria"
            lines.append(f"Bateria: {bat['percent']}% ({plug})")

        return " | ".join(lines)

    # ─── Monitoramento proativo ───────────────────────────────────────────────
    def start_monitoring(self, interval: float = 30.0):
        """Monitora em background e chama on_alert se algo estiver no limite."""
        if self._watching or not self._on_alert:
            return
        self._watching = True
        self._thread = threading.Thread(
            target=self._monitor_loop, args=(interval,), daemon=True
        )
        self._thread.start()

    def stop_monitoring(self):
        self._watching = False

    def _can_alert(self, key: str, cooldown: float = 60.0) -> bool:
        now = time.time()
        last = self._last_alerts.get(key, 0)
        if now - last > cooldown:
            self._last_alerts[key] = now
            return True
        return False

    def set_suppress(self, value: bool):
        """Suprime alertas durante inferência do LLM para não interromper respostas."""
        self._suppress = value

    def _monitor_loop(self, interval: float):
        while self._watching:
            time.sleep(interval)

            if self._suppress:
                continue  # LLM está pensando — ignora alertas agora

            cpu = self.get_cpu()
            if cpu["percent"] > self.ALERT_CPU_PERCENT and self._can_alert("cpu"):
                self._on_alert(f"CPU está em {cpu['percent']}%. Tá pesado aí.")

            ram = self.get_ram()
            if ram["percent"] > self.ALERT_RAM_PERCENT and self._can_alert("ram"):
                self._on_alert(f"RAM em {ram['percent']}% — {ram['used_gb']}GB usados.")

            gpu = self.get_gpu()
            if gpu:
                if gpu["load_pct"] > self.ALERT_GPU_PERCENT and self._can_alert("gpu_load"):
                    self._on_alert(f"GPU em {gpu['load_pct']}% de carga.")
                if gpu["temp_c"] and gpu["temp_c"] > self.ALERT_TEMP_C and self._can_alert("gpu_temp"):
                    self._on_alert(f"GPU está a {gpu['temp_c']}°C. Cuidado com o aquecimento.")

            bat = self.get_battery()
            if bat and not bat["plugged"] and bat["percent"] < self.ALERT_BATTERY_PCT:
                if self._can_alert("battery", cooldown=300):
                    self._on_alert(f"Bateria em {bat['percent']}%. Conecta o carregador.")
