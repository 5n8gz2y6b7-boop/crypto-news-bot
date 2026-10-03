"""Préparation des jobs Kling (images, durées, prompts, budget).

Les appels Kling eux-mêmes passent par le connecteur MCP de Claude (who_am_i, file_upload,
image_to_video, query_tasks) : un script Python ne peut pas utiliser ce connecteur. Ce module
produit kling_jobs.json et tient cache/manifest.json via kling_cache.py.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from .errors import InputError
from .manifest import Manifest, file_sha256, job_key
from .script import Script
from .timeline import Timeline, kling_duration


@dataclass
class KlingJob:
    key: str
    segment: int
    plan: str
    source_image: str
    prepared_image: str
    image_sha256: str
    voice_s: float          # durée de la phrase
    need_s: float           # durée à l'écran (fondus compris)
    requested_s: float      # durée demandée à Kling
    prompt: str
    model: str | None
    aspect_ratio: str
    status: str
    clip_path: str | None


def prepare_image(src: Path, dst_dir: Path, cfg: dict[str, Any]) -> Path:
    """Image conforme Kling : JPG/PNG < 4K, ≤ 30 Mo, ratio ≤ 1:2, recadrée en 9:16."""
    kc = cfg["kling"]
    dst_dir.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
    except OSError as exc:
        raise InputError(f"Image illisible : {src} ({exc})") from exc
    w, h = im.size
    target = 9 / 16
    if w / h > target:  # trop large : recadrage centré
        nw = int(h * target)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    elif w / h < target:
        nh = int(w / target)
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    w, h = im.size
    scale = min(1.0, kc["max_image_side"] / max(w, h))
    if scale < 1:
        im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    if max(im.size) / min(im.size) > kc["max_aspect"]:
        raise InputError(f"Ratio trop extrême après recadrage : {src}")
    out = dst_dir / f"{src.stem}_9x16.jpg"
    quality = 92
    im.save(out, "JPEG", quality=quality, optimize=True)
    while out.stat().st_size > kc["max_bytes"] and quality > 60:
        quality -= 8
        im.save(out, "JPEG", quality=quality, optimize=True)
    return out


def motion_prompt(plan: str, cfg: dict[str, Any]) -> str:
    kc = cfg["kling"]
    base = kc["motion_prompts"].get(plan, kc["motion_prompts"]["default"])
    return f"{base}, {kc['prompt_suffix']}"


def build_jobs(script: Script, prop_folder: Path, tl: Timeline, cfg: dict[str, Any], manifest: Manifest,
               prepared_dir: Path) -> list[KlingJob]:
    """Un job par plan photo ; réutilise le manifest pour ne jamais repayer un clip existant."""
    kc = cfg["kling"]
    jobs = []
    for seg, scene in zip(script.segments, [s for s in tl.scenes if s.kind == "photo"]):
        src = prop_folder / seg.image
        prepared = prepare_image(src, prepared_dir, cfg)
        sha = file_sha256(prepared)
        voice_s = scene.voice_end - scene.voice_start
        need = scene.duration
        # Règle demandée : durée de la voix arrondie au supérieur, parmi les durées autorisées ;
        # on vérifie aussi que le clip couvre les fondus (sinon ralenti/zoom figé au montage).
        requested = kling_duration(max(math.ceil(voice_s), need), kc["allowed_durations"])
        prompt = motion_prompt(seg.plan, cfg)
        key = job_key(sha, requested, kc.get("model"), prompt)
        item = manifest.get(key) or manifest.upsert(
            key, status="prepared", source_image=str(src), prepared_image=str(prepared), image_sha256=sha,
            requested_s=requested, prompt=prompt, model=kc.get("model"),
            upload_url=manifest.upload_url_for_sha(sha))
        clip = manifest.clip_for(key)
        jobs.append(KlingJob(key, seg.index, seg.plan, str(src), str(prepared), sha, round(voice_s, 2),
                             round(need, 2), requested, prompt, kc.get("model"), kc["aspect_ratio_value"],
                             "downloaded" if clip else item.get("status", "prepared"),
                             str(clip) if clip else None))
    return jobs


def budget(jobs: list[KlingJob], cfg: dict[str, Any]) -> dict[str, Any]:
    """Récapitulatif avant soumission (clips déjà en cache exclus)."""
    todo = {j.key: j for j in jobs if j.status != "downloaded"}.values()  # images répétées = 1 seul job
    per = cfg["kling"].get("credits_per_clip") or {}
    unknown = [j for j in todo if str(int(j.requested_s)) not in per]
    credits = None if unknown else sum(per[str(int(j.requested_s))] for j in todo)
    return {
        "clips_a_generer": len(list(todo)),
        "clips_en_cache": sum(1 for j in jobs if j.status == "downloaded"),
        "modele": cfg["kling"].get("model") or "À CHOISIR après who_am_i",
        "durees_s": [j.requested_s for j in todo],
        "credits_estimes": credits if credits is not None else "inconnu (à confirmer via who_am_i)",
    }


def write_jobs(path: Path, jobs: list[KlingJob], recap: dict[str, Any]) -> None:
    path.write_text(json.dumps({"budget": recap, "jobs": [asdict(j) for j in jobs]}, ensure_ascii=False,
                               indent=2), encoding="utf-8")


def format_budget(recap: dict[str, Any]) -> str:
    return (f"Kling : {recap['clips_a_generer']} clip(s) à générer ({recap['clips_en_cache']} en cache) — "
            f"modèle {recap['modele']} — durées {recap['durees_s']} s — crédits estimés : "
            f"{recap['credits_estimes']}")
