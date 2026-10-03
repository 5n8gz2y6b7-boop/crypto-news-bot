"""Rendu des plans (Ken Burns, plan fixe, clip Kling ajusté, carte de fin) et assemblage final."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from .audio import probe_duration, run_ffmpeg
from .config import resolve
from .errors import ToolError
from .timeline import Timeline, fit_plan


def check_ffmpeg() -> None:
    """FFmpeg, ffprobe et libass (filtre ass) sont indispensables."""
    for exe in ("ffmpeg", "ffprobe"):
        if not shutil.which(exe):
            raise ToolError(f"{exe} introuvable. Installez FFmpeg (avec libass) — voir README.")
    res = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
    names = {line.split()[1] for line in res.stdout.splitlines() if len(line.split()) > 2}
    missing = [f for f in ("ass", "xfade", "loudnorm", "sidechaincompress", "zoompan") if f not in names]
    if missing:
        raise ToolError(f"FFmpeg sans les filtres {', '.join(missing)}. 'ass' nécessite FFmpeg compilé avec "
                        "libass (--enable-libass) — voir README.")


def _encode_args(cfg: dict[str, Any], preset: str = "veryfast") -> list[str]:
    return ["-an", "-c:v", "libx264", "-preset", preset, "-crf", "16", "-pix_fmt", "yuv420p",
            "-r", str(cfg["video"]["fps"])]


def prepare_still(src: Path, dst: Path, cfg: dict[str, Any], ss: int) -> tuple[int, int]:
    """Image redimensionnée pour couvrir la hauteur 1920×ss (largeur ≥ 1080×ss)."""
    W, H = cfg["video"]["width"] * ss, cfg["video"]["height"] * ss
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        scale = max(W / im.width, H / im.height)
        im = im.resize((max(W, round(im.width * scale)), max(H, round(im.height * scale))), Image.LANCZOS)
        im.save(dst, "PNG", compress_level=1)
        return im.size


def render_kenburns(src: Path, out: Path, duration: float, idx: int, cfg: dict[str, Any], work: Path,
                    animate: bool = True) -> None:
    """Ken Burns local : panoramique doux si la photo est large, sinon zoom avant/arrière.

    animate=False donne un plan fixe (mode --dry-run).
    """
    v = cfg["video"]
    W, H, fps = v["width"], v["height"], v["fps"]
    ss = v["kenburns"]["supersample"] if animate else 1
    still = work / f"still_{idx:02d}_{ss}.png"
    iw, ih = prepare_still(src, still, cfg, ss)
    cw, ch = W * ss, H * ss
    if not animate:
        vf = f"crop={cw}:{ch}:(iw-{cw})/2:(ih-{ch})/2,scale={W}:{H},setsar=1"
    else:
        D = max(duration, 0.1)
        p = f"(1-cos(PI*min(t/{D:.3f},1)))/2"           # easing sinusoïdal
        zm = v["kenburns"]["zoom_max"]
        n = max(int(round(duration * fps)), 1)
        pz = f"(1-cos(PI*min(on/{n},1)))/2"
        span = iw - cw
        if span > cw * 0.08:  # photo plus large que 9:16 → panoramique
            amp = min(span, cw * 0.30)
            x0 = (span - amp) / 2
            direction = p if idx % 2 == 0 else f"(1-{p})"
            crop = f"crop={cw}:{ch}:'{x0:.1f}+{amp:.1f}*{direction}':(ih-{ch})/2"
            z = f"1+{(zm - 1) * 0.5:.4f}*{pz}"
        else:
            crop = f"crop={cw}:{ch}:(iw-{cw})/2:(ih-{ch})/2"
            z = f"1+{zm - 1:.4f}*{pz}" if idx % 2 == 0 else f"{zm:.4f}-{zm - 1:.4f}*{pz}"
        vf = (f"{crop},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps},"
              "setsar=1")
    run_ffmpeg(["-loop", "1", "-framerate", str(fps), "-i", str(still), "-t", f"{duration:.3f}", "-vf", vf,
                *_encode_args(cfg), str(out)], f"plan {idx + 1}")


def render_kling_clip(clip: Path, out: Path, duration: float, idx: int, cfg: dict[str, Any]) -> dict[str, Any]:
    """Recadre en 1080×1920 et ajuste la durée : coupe, ralenti (≥ x0.8) ou image figée en zoom lent."""
    v = cfg["video"]
    W, H, fps = v["width"], v["height"], v["fps"]
    plan = fit_plan(probe_duration(clip), duration, v["max_slowdown"])
    chain = [f"scale={W}:{H}:force_original_aspect_ratio=increase", f"crop={W}:{H}", "setsar=1"]
    if plan["mode"] != "trim":
        chain.append(f"setpts=PTS/{plan['speed']:.4f}")
    chain.append(f"fps={fps}")
    if plan["mode"] == "freeze":
        frz = int(round((duration - plan["freeze"]) * fps))
        chain += [f"tpad=stop_mode=clone:stop_duration={plan['freeze'] + 0.1:.3f}",
                  f"zoompan=z='if(gte(on,{frz}),1+0.0015*(on-{frz}),1)':x='iw/2-(iw/zoom/2)':"
                  f"y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}"]
    chain.append(f"trim=0:{duration:.3f},setpts=PTS-STARTPTS")
    run_ffmpeg(["-i", str(clip), "-vf", ",".join(chain), *_encode_args(cfg), "-t", f"{duration:.3f}", str(out)],
               f"clip Kling {idx + 1}")
    return plan


def render_outro(src: Path, out: Path, duration: float, cfg: dict[str, Any], palette: dict[str, str],
                 work: Path) -> None:
    """Fond de la carte de fin : dernière photo floutée, assombrie et teintée aux couleurs de la saison."""
    v = cfg["video"]
    W, H, fps = v["width"], v["height"], v["fps"]
    still = work / "outro_bg.png"
    prepare_still(src, still, cfg, 1)
    tint = palette["card_bg"].lstrip("#")
    n = max(int(round(duration * fps)), 1)
    vf = (f"crop={W}:{H}:(iw-{W})/2:(ih-{H})/2,gblur=sigma=28,eq=brightness=-0.08:saturation=0.8,"
          f"drawbox=x=0:y=0:w=iw:h=ih:color=0x{tint}@0.62:t=fill,"
          f"zoompan=z='1+0.04*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps},setsar=1")
    run_ffmpeg(["-loop", "1", "-framerate", str(fps), "-i", str(still), "-t", f"{duration:.3f}", "-vf", vf,
                *_encode_args(cfg), str(out)], "carte de fin")


def _esc(path: Path) -> str:
    """Échappement d'un chemin pour un argument de filtre FFmpeg."""
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def assemble(scenes: list[Path], tl: Timeline, audio: Path, ass: Path, out: Path, cfg: dict[str, Any]) -> None:
    """Fondus enchaînés de 0,4 s, incrustation ASS (libass), H.264 + AAC, 1080×1920 à 30 i/s."""
    v = cfg["video"]
    if len(scenes) != len(tl.scenes):
        raise ToolError("Nombre de plans incohérent avec la ligne de temps.")
    inputs: list[str] = []
    for s in scenes:
        inputs += ["-i", str(s)]
    inputs += ["-i", str(audio)]
    parts, last = [], "[0:v]"
    for k, off in enumerate(tl.xfade_offsets, start=1):
        label = f"[x{k}]"
        parts.append(f"{last}[{k}:v]xfade=transition=fade:duration={tl.xfade}:offset={off:.3f}{label}")
        last = label
    fonts = resolve(cfg, cfg["subtitles"]["fonts_dir"])
    parts.append(f"{last}ass=filename='{_esc(ass)}':fontsdir='{_esc(fonts)}',format=yuv420p[v]")
    run_ffmpeg([*inputs, "-filter_complex", ";".join(parts), "-map", "[v]", "-map", f"{len(scenes)}:a",
                "-t", f"{tl.total:.3f}", "-c:v", "libx264", "-preset", v["preset"], "-crf", str(v["crf"]),
                "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(v["fps"]), "-c:a", "aac", "-b:a", "192k",
                "-ar", "48000", "-movflags", "+faststart", str(out)], "assemblage final")
