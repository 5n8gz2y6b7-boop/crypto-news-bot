"""Mesures et traitements audio : durées, piste voix normalisée, mixage musique + ducking."""
from __future__ import annotations

import json
import logging
import random
import re
import subprocess
import wave
from pathlib import Path
from typing import Any

from .config import resolve
from .errors import ToolError

log = logging.getLogger(__name__)
SAMPLE_RATE = 48000
MUSIC_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


def run_ffmpeg(args: list[str], what: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Lance FFmpeg et transforme un échec en message lisible."""
    res = subprocess.run(["ffmpeg", "-y", "-hide_banner", *args], capture_output=True, text=True, cwd=cwd)
    if res.returncode != 0:
        tail = "\n".join(res.stderr.strip().splitlines()[-8:])
        raise ToolError(f"FFmpeg a échoué ({what}) :\n{tail}")
    return res


def probe_duration(path: Path) -> float:
    """Durée réelle d'un fichier média via ffprobe."""
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True)
    try:
        return float(json.loads(res.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise ToolError(f"ffprobe ne peut pas lire la durée de {path} : {res.stderr.strip()}") from exc


def concat_with_gaps(parts: list[Path], gap_s: float, out: Path) -> list[tuple[float, float]]:
    """Concatène des WAV mono 48 kHz avec un silence entre chaque ; renvoie (début, fin) de chaque partie."""
    spans, t = [], 0.0
    gap_frames = int(round(gap_s * SAMPLE_RATE))
    with wave.open(str(out), "wb") as dst:
        dst.setnchannels(1)
        dst.setsampwidth(2)
        dst.setframerate(SAMPLE_RATE)
        for i, p in enumerate(parts):
            with wave.open(str(p), "rb") as src:
                if (src.getnchannels(), src.getsampwidth(), src.getframerate()) != (1, 2, SAMPLE_RATE):
                    raise ToolError(f"Format inattendu pour {p.name} (attendu WAV mono 16 bits 48 kHz).")
                n = src.getnframes()
                dst.writeframes(src.readframes(n))
            spans.append((t, t + n / SAMPLE_RATE))
            t += n / SAMPLE_RATE
            if i < len(parts) - 1:
                dst.writeframes(b"\x00\x00" * gap_frames)
                t += gap_frames / SAMPLE_RATE
    return spans


def loudnorm(src: Path, dst: Path, lufs: float, tp: float) -> dict[str, float]:
    """Normalisation EBU R128 en deux passes (mode linéaire : la synchro est préservée)."""
    res = run_ffmpeg(["-i", str(src), "-af", f"loudnorm=I={lufs}:TP={tp}:LRA=11:print_format=json",
                      "-f", "null", "-"], "mesure loudness")
    m = json.loads(re.findall(r"\{[^{}]*\}", res.stderr, re.S)[-1])
    af = (f"loudnorm=I={lufs}:TP={tp}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
          f"linear=true,aresample={SAMPLE_RATE}")
    run_ffmpeg(["-i", str(src), "-af", af, "-ac", "1", "-c:a", "pcm_s16le", str(dst)], "normalisation voix")
    return {k: float(v) for k, v in m.items() if k.startswith("input_")}


def measure_lufs(path: Path) -> float:
    """Loudness intégrée (LUFS) d'un fichier."""
    res = run_ffmpeg(["-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128", "-f", "null", "-"],
                     "mesure ebur128")
    found = re.findall(r"I:\s+(-?[\d.]+) LUFS", res.stderr)
    if not found:
        raise ToolError(f"Impossible de mesurer la loudness de {path}")
    return float(found[-1])


def pick_music(cfg: dict[str, Any], season: str, seed: str) -> Path | None:
    """Musique libre de droits choisie selon la saison ; None si le dossier est vide."""
    base = resolve(cfg, cfg["music"]["dir"])
    candidates = sorted(p for p in (base / season).glob("*") if p.suffix.lower() in MUSIC_EXTS)
    if not candidates:
        candidates = sorted(p for p in base.glob("*") if p.is_file() and p.suffix.lower() in MUSIC_EXTS
                            and (season in p.stem.lower() or not any(s in p.stem.lower() for s in ("hiver", "ete"))))
    if not candidates:
        return None
    return random.Random(seed).choice(candidates)  # stable pour un même hébergement


def mix(voice: Path, music: Path | None, lead_in: float, total: float, out: Path, cfg: dict[str, Any]) -> None:
    """Voix décalée de lead_in + musique à -26 LUFS avec ducking (sidechaincompress) et fondus."""
    mc = cfg["music"]
    ms = int(round(lead_in * 1000))
    # pan à 0.7071 (-3 dB) : une voix mono copiée sur deux canaux garde la même loudness.
    voice_chain = (f"[0:a]aformat=sample_rates={SAMPLE_RATE}:channel_layouts=mono,adelay={ms}:all=1,"
                   f"apad=whole_dur={total:.3f},atrim=0:{total:.3f},pan=stereo|c0=0.7071*c0|c1=0.7071*c0")
    if music is None:
        fc = voice_chain + "[out]"
        inputs = ["-i", str(voice)]
    else:
        fo = mc["fade_out_s"]
        fc = (voice_chain + ",asplit=2[v][sc];"
              f"[1:a]aformat=sample_rates={SAMPLE_RATE}:channel_layouts=stereo,"
              f"loudnorm=I={mc['level_lufs']}:TP=-6:LRA=11,aresample={SAMPLE_RATE},atrim=0:{total:.3f},"
              f"afade=t=in:d={mc['fade_in_s']},afade=t=out:st={max(total - fo, 0):.3f}:d={fo}[m];"
              f"[m][sc]sidechaincompress=threshold={mc['duck_threshold']}:ratio={mc['duck_ratio']}:"
              f"attack={mc['duck_attack_ms']}:release={mc['duck_release_ms']}[md];"
              "[v][md]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.89:level=false[out]")
        inputs = ["-i", str(voice), "-stream_loop", "-1", "-i", str(music)]
    run_ffmpeg([*inputs, "-filter_complex", fc, "-map", "[out]", "-t", f"{total:.3f}",
                "-c:a", "pcm_s16le", "-ar", str(SAMPLE_RATE), str(out)], "mixage audio")
