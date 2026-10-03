"""Calcul de la ligne de temps : voix, plans, fondus enchaînés, intro et outro."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Scene:
    """Un plan vidéo : visible de `start` à `end` (fondus inclus de part et d'autre)."""

    index: int
    kind: str          # "photo" | "outro"
    start: float       # début du clip (fondu d'entrée compris)
    end: float         # fin du clip (fondu de sortie compris)
    voice_start: float = 0.0
    voice_end: float = 0.0

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Timeline:
    scenes: list[Scene]
    boundaries: list[float]   # instants de changement de plan (centre des fondus)
    total: float
    lead_in: float
    xfade: float

    @property
    def xfade_offsets(self) -> list[float]:
        """Offsets FFmpeg xfade (temps global du début de chaque fondu)."""
        return [b - self.xfade / 2 for b in self.boundaries[1:-1]]


def build_timeline(voice_spans: list[tuple[float, float]], cfg: dict[str, Any]) -> Timeline:
    """voice_spans : (début, fin) de chaque segment dans la piste voix (sans lead-in).

    Chaque photo couvre exactement son segment de voix ; les changements de plan sont placés au
    milieu des silences, donc la voix n'est jamais interrompue par une coupe.
    """
    v = cfg["video"]
    lead, f = v["lead_in_s"], v["xfade_s"]
    spans = [(s + lead, e + lead) for s, e in voice_spans]
    tail = max(f / 2 + 0.15, 0.35)  # le dernier mot finit avant le fondu vers la carte de fin
    bounds = [0.0]
    for (_, e_prev), (s_next, _) in zip(spans, spans[1:]):
        bounds.append((e_prev + s_next) / 2)
    bounds.append(spans[-1][1] + tail)
    total = bounds[-1] + v["outro_s"]
    bounds.append(total)

    scenes = []
    n = len(bounds) - 1
    for k in range(n):
        start = 0.0 if k == 0 else bounds[k] - f / 2
        end = total if k == n - 1 else bounds[k + 1] + f / 2
        if k < len(spans):
            scenes.append(Scene(k, "photo", start, end, spans[k][0], spans[k][1]))
        else:
            scenes.append(Scene(k, "outro", start, end))
    return Timeline(scenes, bounds, total, lead, f)


def kling_duration(need_s: float, allowed: list[int | float]) -> float:
    """Plus petite durée autorisée par Kling couvrant le besoin ; sinon la plus longue."""
    ok = sorted(a for a in allowed if a >= need_s - 1e-6)
    return ok[0] if ok else max(allowed)


def fit_plan(clip_s: float, need_s: float, max_slowdown: float) -> dict[str, float]:
    """Comment adapter un clip à sa place : coupe, ralenti (≥ x0.8) ou image figée en zoom lent."""
    if clip_s >= need_s:
        return {"mode": "trim", "speed": 1.0, "freeze": 0.0}
    speed = clip_s / need_s
    if speed >= max_slowdown:
        return {"mode": "slow", "speed": speed, "freeze": 0.0}
    return {"mode": "freeze", "speed": max_slowdown, "freeze": need_s - clip_s / max_slowdown}
