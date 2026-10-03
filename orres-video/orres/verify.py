"""Contrôles automatiques du MP4 final (ffprobe, loudness, synchro sous-titres/voix)."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .audio import measure_lufs, run_ffmpeg
from .subtitles import Group
from .timeline import Timeline


def probe(path: Path) -> dict[str, Any]:
    res = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         capture_output=True, text=True)
    return json.loads(res.stdout)


def speech_onsets(path: Path, threshold_db: int = -35, min_silence: float = 0.12) -> list[float]:
    """Instants où la parole reprend après un silence (silencedetect sur la piste voix)."""
    res = run_ffmpeg(["-i", str(path), "-af", f"silencedetect=n={threshold_db}dB:d={min_silence}",
                      "-f", "null", "-"], "détection de silences")
    return [float(x) for x in re.findall(r"silence_end: ([\d.]+)", res.stderr)]


def verify(mp4: Path, voice_mix_without_music: Path, tl: Timeline, groups: list[Group],
           cfg: dict[str, Any]) -> dict[str, Any]:
    """Renvoie un rapport ; `ok` est faux si un contrôle bloquant échoue."""
    v = cfg["video"]
    info = probe(mp4)
    vs = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])
    checks: dict[str, Any] = {}
    checks["resolution"] = (f"{vs['width']}x{vs['height']}" if vs else None, vs is not None
                            and (vs["width"], vs["height"]) == (v["width"], v["height"]))
    checks["fps"] = (vs["r_frame_rate"] if vs else None, vs is not None and vs["r_frame_rate"] == f"{v['fps']}/1")
    checks["codec_video"] = (vs["codec_name"] if vs else None, vs is not None and vs["codec_name"] == "h264")
    checks["codec_audio"] = (a["codec_name"] if a else None, a is not None and a["codec_name"] == "aac")
    checks["duree_s"] = (round(dur, 2), v["min_total_s"] <= dur <= v["max_total_s"])
    lufs = measure_lufs(mp4)
    checks["loudness_lufs"] = (lufs, abs(lufs - cfg["tts"]["loudness_lufs"]) <= 2.0)

    # Synchro : chaque début de segment de voix (mesuré dans l'audio) doit correspondre
    # au premier mot sous-titré du segment.
    onsets = speech_onsets(voice_mix_without_music)
    firsts = [s.voice_start for s in tl.scenes if s.kind == "photo"]
    sub_firsts = []
    for t in firsts:
        g = min(groups, key=lambda g: abs(g.words[0].start - t))
        sub_firsts.append(g.words[0].start)
    deltas = []
    for t in sub_firsts:
        if onsets:
            nearest = min(onsets, key=lambda o: abs(o - t))
            deltas.append(round(nearest - t, 3))
    worst = max((abs(d) for d in deltas), default=None)
    checks["synchro_debut_segments_s"] = (deltas, worst is not None and worst <= 0.12)

    # Aucune transition pendant un mot : le fondu peut chevaucher la voix, jamais la couper.
    words_in_transition = 0
    for b in tl.boundaries[1:-1]:
        for g in groups:
            for w in g.words:
                if w.start < b < w.end:
                    words_in_transition += 1
    checks["coupe_au_milieu_d_un_mot"] = (words_in_transition, words_in_transition == 0)
    report = {"fichier": str(mp4), "controles": {k: {"valeur": val, "ok": ok} for k, (val, ok) in checks.items()}}
    report["ok"] = all(ok for _, ok in checks.values())
    return report


def format_report(report: dict[str, Any]) -> str:
    lines = [f"Contrôles de {Path(report['fichier']).name} :"]
    for name, c in report["controles"].items():
        lines.append(f"  {'✓' if c['ok'] else '✗'} {name:<28} {c['valeur']}")
    return "\n".join(lines)
