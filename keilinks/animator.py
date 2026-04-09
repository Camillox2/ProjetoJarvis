"""
Animação visual da Keilinks — cérebro neural com estados.
Roda em thread separada, não bloqueia o loop principal.

Estados:
  idle      → neurônios orbitam devagar em azul, core pulsando
  listening → verde, neurônios reagem ao volume do microfone
  thinking  → laranja, órbita acelerada, partículas caóticas
  speaking  → roxo, ondas expansivas do centro + partículas emitidas
"""

import math
import random
import threading
import numpy as np
import pygame
from dataclasses import dataclass, field
from typing import Literal

WIDTH, HEIGHT = 480, 480
FPS           = 60
CX, CY       = WIDTH // 2, HEIGHT // 2
BG_COLOR      = (6, 6, 14)

# Paleta com cor secundária para gradientes
STATE_COLORS = {
    "idle":      ((30, 70, 220),  (60, 130, 255)),
    "listening": ((30, 200, 80),  (80, 255, 140)),
    "thinking":  ((230, 150, 20), (255, 200, 80)),
    "speaking":  ((170, 40, 230), (220, 100, 255)),
}

NUM_NEURONS      = 36
MAX_CONNECTIONS  = 3
NUM_PARTICLES    = 50

State = Literal["idle", "listening", "thinking", "speaking"]


def _lerp_color(c1: tuple, c2: tuple, t: float) -> tuple:
    """Interpola linearly entre duas cores RGB."""
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


@dataclass
class Neuron:
    # Posição em coordenadas polares relativas ao centro
    angle: float        # radianos — posição orbital
    dist: float         # distância base do centro
    radius: float       # raio visual base
    phase: float        # fase de pulsação individual
    speed: float        # velocidade de pulsação
    orbit_speed: float  # velocidade orbital (rad/frame)
    layer: int          # 0 = inner, 1 = mid, 2 = outer
    connections: list[int] = field(default_factory=list)

    @property
    def x(self) -> float:
        return CX + self.dist * math.cos(self.angle) * 1.1

    @property
    def y(self) -> float:
        return CY + self.dist * math.sin(self.angle) * 0.88


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float      # 0.0 → 1.0 (1.0 = acabou)
    max_life: float
    size: float


class BrainAnimator:
    def __init__(self):
        self._state: State   = "idle"
        self._volume: float  = 0.0
        self._running        = False
        self._thread: threading.Thread | None = None
        self._lock           = threading.Lock()
        self._wave_rings: list[dict] = []
        self.neurons: list[Neuron] = []
        self._particles: list[Particle] = []
        self._time: float = 0.0  # tempo acumulado para efeitos

        # Transição suave de cor
        self._current_color: tuple = STATE_COLORS["idle"][0]
        self._current_color2: tuple = STATE_COLORS["idle"][1]

    # ─── API pública (thread-safe) ────────────────────────────────────────────
    def set_state(self, state: State):
        with self._lock:
            self._state = state
            if state == "speaking":
                self._wave_rings.append({"r": 0, "alpha": 255})

    def set_volume(self, volume: float):
        with self._lock:
            self._volume = min(1.0, max(0.0, volume))

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    # ─── Geração do grafo neural ──────────────────────────────────────────────
    def _build_neurons(self):
        neurons = []
        layers = [
            (8,   40,   80),   # inner: 8 neurônios, dist 40–80
            (14,  90,  140),   # mid:   14 neurônios, dist 90–140
            (14, 150,  195),   # outer: 14 neurônios, dist 150–195
        ]
        for layer_idx, (count, d_min, d_max) in enumerate(layers):
            for i in range(count):
                base_angle = (2 * math.pi / count) * i + random.uniform(-0.3, 0.3)
                neurons.append(Neuron(
                    angle=base_angle,
                    dist=random.uniform(d_min, d_max),
                    radius=random.uniform(3.0, 7.0) if layer_idx > 0 else random.uniform(5.0, 10.0),
                    phase=random.uniform(0, 2 * math.pi),
                    speed=random.uniform(0.015, 0.045),
                    orbit_speed=random.uniform(0.001, 0.004) * (1.0 + layer_idx * 0.4),
                    layer=layer_idx,
                ))

        # Conexões: liga aos mais próximos (usando posição atual)
        for i, n in enumerate(neurons):
            dists = sorted(
                [(j, math.hypot(n.x - m.x, n.y - m.y))
                 for j, m in enumerate(neurons) if j != i],
                key=lambda t: t[1],
            )
            n.connections = [j for j, _ in dists[:MAX_CONNECTIONS]]
        self.neurons = neurons

    def _spawn_particle(self, x: float, y: float, spread: float = 2.0):
        """Cria uma partícula com velocidade aleatória."""
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(0.3, spread)
        self._particles.append(Particle(
            x=x, y=y,
            vx=math.cos(angle) * speed,
            vy=math.sin(angle) * speed,
            life=0.0,
            max_life=random.uniform(40, 90),
            size=random.uniform(1.0, 2.5),
        ))
        # Limita quantidade total
        if len(self._particles) > NUM_PARTICLES:
            self._particles = self._particles[-NUM_PARTICLES:]

    # ─── Loop de renderização ─────────────────────────────────────────────────
    def _run(self):
        try:
            self._render_loop()
        finally:
            try:
                pygame.display.quit()
                pygame.font.quit()
            except Exception:
                pass

    def _render_loop(self):
        pygame.display.init()
        pygame.font.init()

        screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Keilinks")
        clock  = pygame.time.Clock()

        icon_surf = pygame.Surface((32, 32), pygame.SRCALPHA)
        pygame.draw.circle(icon_surf, (170, 40, 230), (16, 16), 14)
        pygame.display.set_icon(icon_surf)

        font = pygame.font.SysFont("consolas", 13)
        self._build_neurons()

        labels = {
            "idle":      "em espera...",
            "listening": "ouvindo...",
            "thinking":  "pensando...",
            "speaking":  "falando...",
        }
        speed_mults = {"idle": 1.0, "listening": 1.5, "thinking": 3.5, "speaking": 2.0}
        orbit_mults = {"idle": 1.0, "listening": 0.8, "thinking": 4.0, "speaking": 1.5}

        while self._running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False

            with self._lock:
                state  = self._state
                volume = self._volume
                rings  = [r.copy() for r in self._wave_rings]

            self._time += 1.0 / FPS
            target_c1, target_c2 = STATE_COLORS[state]

            # Transição suave de cor (lerp 5% por frame)
            self._current_color  = _lerp_color(self._current_color, target_c1, 0.05)
            self._current_color2 = _lerp_color(self._current_color2, target_c2, 0.05)
            base_color = self._current_color
            hi_color   = self._current_color2

            speed_mult = speed_mults[state]
            orbit_mult = orbit_mults[state]

            screen.fill(BG_COLOR)

            # ── Core central pulsante ─────────────────────────────────────────
            core_pulse = (math.sin(self._time * 2.0) + 1) / 2
            if state == "listening":
                core_pulse = max(core_pulse, volume)
            core_r = int(18 + core_pulse * 10)
            core_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

            # Glow externo do core (3 camadas)
            for i, (mult, alpha_base) in enumerate([(5.0, 15), (3.0, 25), (1.8, 40)]):
                glow_r = int(core_r * mult)
                alpha  = int(alpha_base + core_pulse * 20)
                pygame.draw.circle(core_surf, (*base_color, alpha), (CX, CY), glow_r)
            # Core sólido
            pygame.draw.circle(core_surf, hi_color, (CX, CY), core_r)
            # Highlight interno
            pygame.draw.circle(core_surf, (255, 255, 255, int(80 + core_pulse * 60)),
                               (CX - core_r // 4, CY - core_r // 4), core_r // 3)
            screen.blit(core_surf, (0, 0))

            # ── Atualiza órbitas dos neurônios ────────────────────────────────
            for n in self.neurons:
                n.phase += n.speed * speed_mult
                n.angle += n.orbit_speed * orbit_mult
                if state == "thinking":
                    n.angle += random.uniform(-0.005, 0.005)  # jitter

            # ── Conexões (linhas entre neurônios) ─────────────────────────────
            conn_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            for n in self.neurons:
                pulse = (math.sin(n.phase) + 1) / 2
                if state == "thinking":
                    pulse = (math.sin(n.phase * 2 + random.uniform(-0.2, 0.2)) + 1) / 2

                alpha = int(20 + pulse * 80)
                nx, ny = int(n.x), int(n.y)
                for j in n.connections:
                    m = self.neurons[j]
                    mx, my = int(m.x), int(m.y)
                    dist = math.hypot(nx - mx, ny - my)
                    # Conexões mais próximas são mais visíveis
                    dist_factor = max(0.2, 1.0 - dist / 300)
                    line_alpha = int(alpha * dist_factor)
                    col = _lerp_color(base_color, hi_color, pulse)
                    pygame.draw.line(conn_surf, (*col, line_alpha),
                                     (nx, ny), (mx, my), 1)

                    # Pulso viajando pela conexão (thinking/speaking)
                    if state in ("thinking", "speaking") and pulse > 0.7:
                        mid_t = (math.sin(self._time * 3 + n.phase) + 1) / 2
                        px = int(nx + (mx - nx) * mid_t)
                        py = int(ny + (my - ny) * mid_t)
                        pygame.draw.circle(conn_surf, (*hi_color, int(100 * pulse)),
                                           (px, py), 2)
            screen.blit(conn_surf, (0, 0))

            # ── Neurônios (glow + corpo) ──────────────────────────────────────
            glow_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            for n in self.neurons:
                pulse = (math.sin(n.phase) + 1) / 2

                if state == "listening":
                    radius = n.radius * (0.7 + pulse * 0.4 + volume * 0.8)
                elif state == "thinking":
                    radius = n.radius * (0.6 + pulse * 0.8)
                elif state == "speaking":
                    radius = n.radius * (0.8 + pulse * 0.4 + volume * 0.3)
                else:
                    radius = n.radius * (0.85 + pulse * 0.25)

                # Cor com variação por camada
                layer_t = n.layer / 2.0  # 0.0 → 1.0
                col = _lerp_color(hi_color, base_color, layer_t)
                brightness = 0.5 + pulse * 0.5
                r = int(min(255, col[0] * brightness + 40))
                g = int(min(255, col[1] * brightness + 40))
                b = int(min(255, col[2] * brightness + 40))

                nx, ny = int(n.x), int(n.y)

                # Glow duplo
                glow_a1 = int(pulse * 35)
                glow_a2 = int(pulse * 60)
                pygame.draw.circle(glow_surf, (r, g, b, glow_a1),
                                   (nx, ny), int(radius * 3.5))
                pygame.draw.circle(glow_surf, (r, g, b, glow_a2),
                                   (nx, ny), int(radius * 2.0))

                # Corpo do neurônio
                pygame.draw.circle(screen, (r, g, b), (nx, ny), max(1, int(radius)))

                # Highlight especular no neurônio
                if radius > 3:
                    spec_alpha = int(40 + pulse * 60)
                    pygame.draw.circle(glow_surf, (255, 255, 255, spec_alpha),
                                       (nx - 1, ny - 1), max(1, int(radius * 0.4)))

            screen.blit(glow_surf, (0, 0))

            # ── Partículas ────────────────────────────────────────────────────
            if state == "thinking" and random.random() < 0.3:
                # Partículas surgem de neurônios aleatórios
                n = random.choice(self.neurons)
                self._spawn_particle(n.x, n.y, spread=1.5)
            elif state == "speaking" and random.random() < 0.15:
                # Partículas emitidas do core
                angle = random.uniform(0, 2 * math.pi)
                self._spawn_particle(CX + math.cos(angle) * 15,
                                     CY + math.sin(angle) * 15,
                                     spread=2.0)
            elif state == "listening" and volume > 0.3 and random.random() < 0.2:
                n = random.choice(self.neurons)
                self._spawn_particle(n.x, n.y, spread=1.0)

            part_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            alive = []
            for p in self._particles:
                p.x += p.vx
                p.y += p.vy
                p.vx *= 0.98  # drag
                p.vy *= 0.98
                p.life += 1

                if p.life >= p.max_life:
                    continue

                t = p.life / p.max_life  # 0 → 1
                alpha = int(180 * (1.0 - t))
                sz = p.size * (1.0 - t * 0.5)
                col = _lerp_color(hi_color, base_color, t)
                pygame.draw.circle(part_surf, (*col, alpha),
                                   (int(p.x), int(p.y)), max(1, int(sz)))
                alive.append(p)
            self._particles = alive
            screen.blit(part_surf, (0, 0))

            # ── Ondas de fala ─────────────────────────────────────────────────
            if state == "speaking":
                wave_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                new_rings = []
                for ring in rings:
                    ring["r"]     += 2.5
                    ring["alpha"]  = max(0, ring["alpha"] - 2)
                    if ring["alpha"] > 0:
                        # Onda com espessura variável
                        thickness = max(1, int(3 * ring["alpha"] / 255))
                        pygame.draw.circle(wave_surf, (*base_color, ring["alpha"]),
                                           (CX, CY), int(ring["r"]), thickness)
                        # Segunda onda sutil
                        if ring["alpha"] > 50:
                            pygame.draw.circle(wave_surf,
                                               (*hi_color, ring["alpha"] // 3),
                                               (CX, CY), int(ring["r"] * 0.85), 1)
                        new_rings.append(ring)
                screen.blit(wave_surf, (0, 0))

                if random.random() < 0.06 + volume * 0.1:
                    new_rings.append({"r": 0, "alpha": 255})

                with self._lock:
                    self._wave_rings = new_rings

            # ── Anel orbital decorativo ───────────────────────────────────────
            ring_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            orbit_alpha = int(20 + core_pulse * 15)
            pygame.draw.ellipse(ring_surf, (*base_color, orbit_alpha),
                                (CX - 100, CY - 30, 200, 60), 1)
            screen.blit(ring_surf, (0, 0))

            # ── Label com sombra ──────────────────────────────────────────────
            label_text = labels[state]
            shadow = font.render(label_text, True, (0, 0, 0))
            label  = font.render(label_text, True, hi_color)
            lx = WIDTH // 2 - label.get_width() // 2
            screen.blit(shadow, (lx + 1, HEIGHT - 27))
            screen.blit(label,  (lx, HEIGHT - 28))

            pygame.display.flip()
            clock.tick(FPS)
