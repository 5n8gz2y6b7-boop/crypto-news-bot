#!/usr/bin/env python3
"""Crée un hébergement d'exemple avec des images synthétiques (et une musique de test) pour tester
le pipeline sans aucun crédit Kling :

    python examples/make_example.py
    python generate.py --input examples/input --output output --music-dir examples/music \
        --dry-run --fallback-kenburns --approve-script
"""
from __future__ import annotations

import random
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
FONT = HERE.parent / "assets" / "fonts" / "Montserrat-Bold.ttf"

INFO = """\
nom: "Chalet Exemple des Orres"
type: "Chalet"
station_secteur: "Les Orres 1650"
points_forts: ["Skis aux pieds", "Vue sur le lac de Serre-Ponçon", "Sauna privatif"]
capacite: "6 personnes"
prix_indicatif: "à partir de 120 €/nuit"
cta: "Réservez sur Booking"
saison: "hiver"
langue: "fr"
ton: "chaleureux"
voix: ""
script_manuel: ""
# Type de plan de chaque photo, dans l'ordre (optionnel)
plans: ["extérieur", "séjour", "vue", "chambre", "cuisine", "salle de bain", "extérieur"]
# Champs pour --lang en (traduction fidèle, rien d'inventé)
type_en: "Chalet"
points_forts_en: ["Ski-in ski-out", "View over Lake Serre-Ponçon", "Private sauna"]
capacite_en: "6 guests"
prix_indicatif_en: "from €120 per night"
cta_en: "Book on Booking.com"
"""


def gradient(w: int, h: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    return im


def mountains(im: Image.Image, rng: random.Random, base: int, color: tuple[int, int, int], snow: bool) -> None:
    d = ImageDraw.Draw(im)
    w, h = im.size
    x = -100
    while x < w + 100:
        peak = base - rng.randint(150, 380)
        width = rng.randint(300, 600)
        d.polygon([(x, base), (x + width / 2, peak), (x + width, base)], fill=color)
        if snow:
            s = (base - peak) * 0.3
            d.polygon([(x + width / 2 - s * 0.9, peak + s), (x + width / 2, peak), (x + width / 2 + s * 0.9, peak + s)],
                      fill=(245, 248, 255))
        x += width * 0.6
    d.rectangle([0, base, w, h], fill=(236, 242, 250) if snow else (90, 130, 70))


def chalet(im: Image.Image, cx: int, base: int, s: float) -> None:
    d = ImageDraw.Draw(im)
    w, h = int(420 * s), int(260 * s)
    d.rectangle([cx - w // 2, base - h, cx + w // 2, base], fill=(120, 72, 40))
    d.polygon([(cx - w // 2 - 50 * s, base - h), (cx, base - h - 200 * s), (cx + w // 2 + 50 * s, base - h)],
              fill=(70, 45, 30))
    d.polygon([(cx - w // 2 - 50 * s, base - h), (cx, base - h - 200 * s), (cx + w // 2 + 50 * s, base - h),
               (cx + w // 2 + 30 * s, base - h + 18 * s), (cx, base - h - 170 * s), (cx - w // 2 - 30 * s, base - h + 18 * s)],
              fill=(250, 252, 255))
    for i in range(3):
        x0 = cx - w // 2 + int((40 + i * 130) * s)
        d.rectangle([x0, base - int(200 * s), x0 + int(90 * s), base - int(90 * s)], fill=(255, 214, 140))


def interior(w: int, h: int, rng: random.Random, kind: str) -> Image.Image:
    im = gradient(w, h, (232, 220, 200), (190, 170, 140))
    d = ImageDraw.Draw(im)
    d.rectangle([0, int(h * 0.72), w, h], fill=(150, 110, 75))  # parquet
    for x in range(0, w, 90):
        d.line([(x, int(h * 0.72)), (x - 60, h)], fill=(130, 95, 65), width=3)
    d.rectangle([int(w * 0.62), int(h * 0.15), int(w * 0.92), int(h * 0.55)], fill=(170, 210, 240))  # fenêtre
    mountains_win = gradient(int(w * 0.3), int(h * 0.4), (150, 200, 240), (220, 235, 250))
    im.paste(mountains_win, (int(w * 0.62), int(h * 0.15)))
    if kind == "séjour":
        d.rounded_rectangle([int(w * 0.08), int(h * 0.52), int(w * 0.52), int(h * 0.75)], 30, fill=(90, 100, 120))
        d.rounded_rectangle([int(w * 0.1), int(h * 0.45), int(w * 0.5), int(h * 0.58)], 30, fill=(110, 120, 140))
    elif kind == "chambre":
        d.rounded_rectangle([int(w * 0.1), int(h * 0.5), int(w * 0.6), int(h * 0.78)], 20, fill=(245, 245, 240))
        d.rectangle([int(w * 0.1), int(h * 0.38), int(w * 0.14), int(h * 0.78)], fill=(110, 75, 50))
    elif kind == "cuisine":
        d.rectangle([int(w * 0.05), int(h * 0.5), int(w * 0.58), int(h * 0.72)], fill=(240, 240, 235))
        d.rectangle([int(w * 0.05), int(h * 0.47), int(w * 0.58), int(h * 0.5)], fill=(60, 60, 60))
        d.rectangle([int(w * 0.05), int(h * 0.12), int(w * 0.58), int(h * 0.3)], fill=(225, 222, 215))
    elif kind == "salle de bain":
        d.rectangle([0, 0, w, int(h * 0.72)], fill=(215, 228, 232))
        d.rounded_rectangle([int(w * 0.1), int(h * 0.48), int(w * 0.55), int(h * 0.7)], 60, fill=(250, 250, 250))
    return im


def label(im: Image.Image, text: str) -> None:
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(str(FONT), max(28, im.width // 40))
    d.rounded_rectangle([20, 20, 40 + d.textlength(text, font=font), 30 + font.size * 1.3], 12, fill=(0, 0, 0, 160))
    d.text((30, 25), text, font=font, fill=(255, 255, 255))


def make_images(dst: Path) -> None:
    rng = random.Random(1650)
    W, H = 1800, 1200
    specs = ["extérieur", "séjour", "vue", "chambre", "cuisine", "salle de bain", "extérieur nuit"]
    for i, kind in enumerate(specs, 1):
        if kind.startswith("extérieur"):
            night = "nuit" in kind
            im = gradient(W, H, (30, 40, 90) if night else (90, 160, 230), (240, 170, 120) if night else (210, 232, 250))
            mountains(im, rng, int(H * 0.68), (95, 110, 140), snow=True)
            chalet(im, W // 2, int(H * 0.86), 1.4)
        elif kind == "vue":
            im = gradient(W, H, (110, 170, 230), (225, 238, 250))
            mountains(im, rng, int(H * 0.55), (100, 115, 150), snow=True)
            ImageDraw.Draw(im).ellipse([W * 0.2, H * 0.6, W * 0.85, H * 0.82], fill=(70, 140, 180))  # lac
        else:
            im = interior(W, H, rng, kind)
        im = im.filter(ImageFilter.GaussianBlur(0.6))
        label(im, f"IMAGE SYNTHÉTIQUE {i:02d} — {kind}")
        im.save(dst / f"{i:02d}.jpg", quality=90)


def make_music(dst: Path, seconds: int = 40) -> None:
    """Nappe d'accords synthétique (aucun droit), pour tester le ducking."""
    dst.mkdir(parents=True, exist_ok=True)
    chords = [(220.0, 277.18, 329.63), (196.0, 246.94, 293.66), (174.61, 220.0, 261.63), (196.0, 246.94, 329.63)]
    expr = []
    seg = seconds / len(chords) / 2
    for k in range(len(chords) * 2):
        f = chords[k % len(chords)]
        tone = "+".join(f"sin(2*PI*{x}*t)" for x in f)
        expr.append(f"between(t,{k * seg},{(k + 1) * seg})*({tone})")
    e = "0.12*(" + "+".join(expr) + ")*(0.6+0.4*sin(2*PI*0.25*t))"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"aevalsrc='{e}':s=48000:d={seconds}",
                    "-af", "aecho=0.8:0.7:120|240:0.35|0.25,lowpass=f=2500", "-ac", "2",
                    str(dst / "nappe-synthetique-hiver.wav")], check=True)


if __name__ == "__main__":
    folder = HERE / "input" / "chalet-exemple"
    folder.mkdir(parents=True, exist_ok=True)
    make_images(folder)
    (folder / "info.yaml").write_text(INFO, encoding="utf-8")
    make_music(HERE / "music" / "hiver")
    print(f"Exemple créé : {folder} (+ musique de test dans examples/music/hiver)")
