"""Enchaînement des étapes pour un hébergement."""
from __future__ import annotations

import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tqdm import tqdm

from . import audio, kling, montage, subtitles, verify
from .align import align_segment
from .errors import KlingPending, ScriptError
from .loader import Property, load_property
from .manifest import Manifest
from .script import Script, generate_script, keywords, validate_script
from .timeline import build_timeline
from .tts import WordTiming, default_voice, make_engine

log = logging.getLogger("orres")


@dataclass
class Options:
    output: Path
    cache: Path
    lang: str | None = None
    voice: str | None = None
    engine: str | None = None
    script_only: bool = False
    approve_script: bool = False
    regen_script: bool = False
    dry_run: bool = False
    fallback_kenburns: bool = False
    resume: bool = False
    no_subs: bool = False
    no_music: bool = False


def step_script(prop: Property, out_dir: Path, lang: str, opts: Options, cfg: dict[str, Any]) -> Script | None:
    """Étape 1 : script (repris s'il existe déjà, pour respecter vos corrections)."""
    path = out_dir / ("script.json" if lang == "fr" else f"script_{lang}.json")
    if path.exists() and not opts.regen_script:
        script = Script.load(path)
        script.avertissements = validate_script(script, prop, cfg)
        _check_images(script, prop)
    else:
        script = generate_script(prop, cfg, lang)
        script.save(path)
    if opts.approve_script and not script.valide:
        script.valide = True
        script.save(path)
        log.info("Script validé : %s", path)
    print("\n" + script.pretty() + "\n")
    if opts.script_only:
        log.info("Script écrit dans %s", path)
        return None
    if not script.valide:
        if sys.stdin.isatty() and input("Valider ce script ? [o/N] ").strip().lower() in {"o", "oui", "y", "ok"}:
            script.valide = True
            script.save(path)
        else:
            log.warning("Script non validé. Corrigez %s si besoin puis relancez avec --approve-script.", path)
            return None
    return script


def _check_images(script: Script, prop: Property) -> None:
    names = {p.name for p in prop.images}
    for s in script.segments:
        if s.image not in names:
            raise ScriptError(f"script.json, segment {s.index} : image « {s.image} » absente du dossier.")


def step_voice(script: Script, prop: Property, work: Path, opts: Options,
               cfg: dict[str, Any]) -> tuple[Path, list[tuple[float, float]], list[list[WordTiming]], str]:
    """Étape 2 : un fichier par segment, durée ffprobe, timestamps par mot, piste normalisée."""
    engine = make_engine(cfg, opts.engine)
    voice = default_voice(cfg, engine.name, script.langue, opts.voice or prop.voix)
    vdir = work / "voice"
    vdir.mkdir(parents=True, exist_ok=True)
    meta_path = vdir / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    parts, words_local, methods = [], [], set()
    for seg in tqdm(script.segments, desc="Voix off", unit="seg", leave=False):
        key = hashlib.sha1(json.dumps([engine.name, voice, seg.texte, cfg["tts"].get("rate"),
                                       cfg["tts"].get("pitch")]).encode()).hexdigest()[:12]
        wav = vdir / f"seg_{seg.index:02d}_{key}.wav"
        cached = meta.get(wav.name)
        if cached and wav.exists():
            words = [WordTiming(**w) for w in cached["words"]]
            methods.add(cached["method"])
        else:
            res = engine.synthesize(seg.texte, voice, wav)
            dur = audio.probe_duration(wav)
            words, method = align_segment(seg.texte, wav, dur, res.words, script.langue, cfg)
            methods.add(method)
            meta[wav.name] = {"duration": dur, "method": method, "words": [w.__dict__ for w in words]}
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
        parts.append(wav)
        words_local.append(words)
    if "estimation" in methods:
        log.warning("Timestamps estimés (ni le moteur ni faster-whisper n'en fournissent) : synchro mot à mot "
                    "approximative. Installez faster-whisper pour un alignement précis.")
    raw = work / "voice_raw.wav"
    spans = audio.concat_with_gaps(parts, cfg["tts"]["gap_s"], raw)
    norm = work / "voice.wav"
    audio.loudnorm(raw, norm, cfg["tts"]["loudness_lufs"], cfg["tts"]["true_peak_db"])
    lead = cfg["video"]["lead_in_s"]
    words_global = [[WordTiming(w.word, w.start + s + lead, w.end + s + lead) for w in ws]
                    for ws, (s, _) in zip(words_local, spans)]
    (work / "timings.json").write_text(json.dumps(
        {"voix": voice, "moteur": engine.name, "alignement": sorted(methods),
         "segments": [{"debut": round(s + lead, 3), "fin": round(e + lead, 3),
                       "mots": [w.__dict__ for w in ws]} for (s, e), ws in zip(spans, words_global)]},
        ensure_ascii=False, indent=1))
    return norm, spans, words_global, f"{engine.name}:{voice}"


def process(folder: Path, cfg: dict[str, Any], opts: Options) -> Path | None:
    """Traite un hébergement ; renvoie le MP4 produit (ou None si arrêt volontaire)."""
    prop = load_property(folder)
    lang = opts.lang or prop.langue
    out_dir = opts.output / prop.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "work"
    work.mkdir(exist_ok=True)
    log.info("━━ %s (%s, %s, %d photos)", prop.nom, prop.saison, lang, len(prop.images))

    script = step_script(prop, out_dir, lang, opts, cfg)
    if script is None:
        return None
    montage.check_ffmpeg()

    voice_path, spans, words, voice_desc = step_voice(script, prop, work, opts, cfg)
    tl = build_timeline(spans, cfg)
    log.info("Voix %s : %.1f s de parole, vidéo %.1f s", voice_desc, spans[-1][1], tl.total)
    if not cfg["video"]["min_total_s"] <= tl.total <= cfg["video"]["max_total_s"]:
        log.warning("Durée %.1f s hors de la plage %s–%s s : ajustez le script ou tts.rate.", tl.total,
                    cfg["video"]["min_total_s"], cfg["video"]["max_total_s"])

    # Sous-titres
    groups = subtitles.build_groups(words, cfg["subtitles"])
    kw = keywords(prop, lang)
    ass = work / "subs.ass"
    subtitles.write_ass(ass, prop, groups, tl, cfg, lang, kw, with_subs=not opts.no_subs)
    base = f"{prop.slug}_{lang}"
    subtitles.write_srt(out_dir / f"{base}.srt", groups)

    # Clips : Kling (cache) ou Ken Burns / plans fixes
    photo_scenes = [s for s in tl.scenes if s.kind == "photo"]
    clips: list[Path | None] = [None] * len(photo_scenes)
    if not opts.dry_run:
        manifest = Manifest(opts.cache / "manifest.json")
        jobs = kling.build_jobs(script, folder, tl, cfg, manifest, opts.cache / "prepared")
        recap = kling.budget(jobs, cfg)
        kling.write_jobs(out_dir / "kling_jobs.json", jobs, recap)
        clips = [Path(j.clip_path) if j.clip_path else None for j in jobs]
        missing = [j for j in jobs if not j.clip_path]
        if missing and not opts.fallback_kenburns:
            raise KlingPending(
                f"{len(missing)} clip(s) Kling manquant(s) pour {prop.slug}.\n  {kling.format_budget(recap)}\n"
                f"  Jobs : {out_dir / 'kling_jobs.json'}\n  → Demandez à Claude de lancer la génération via le "
                "MCP Kling (après votre « ok » sur le budget), puis relancez avec --resume.\n"
                "  → Ou ajoutez --fallback-kenburns pour remplacer les clips manquants par un Ken Burns local.")
        if missing:
            log.warning("%d clip(s) Kling absent(s) : remplacés par un Ken Burns local.", len(missing))

    scene_files: list[Path] = []
    animate = opts.fallback_kenburns or not opts.dry_run
    pal = cfg["palettes"][prop.saison]
    for scene in tqdm(tl.scenes, desc="Plans", unit="plan", leave=False):
        out = work / f"scene_{scene.index:02d}.mp4"
        if scene.kind == "outro":
            last_img = folder / script.segments[-1].image
            montage.render_outro(last_img, out, scene.duration, cfg, pal, work)
        elif clips[scene.index] is not None:
            plan = montage.render_kling_clip(clips[scene.index], out, scene.duration, scene.index, cfg)
            log.debug("Plan %d : %s", scene.index + 1, plan)
        else:
            img = folder / script.segments[scene.index].image
            montage.render_kenburns(img, out, scene.duration, scene.index, cfg, work, animate=animate)
        scene_files.append(out)

    # Audio
    music = None if opts.no_music else audio.pick_music(cfg, prop.saison, prop.slug)
    log.info("Musique : %s", music.name if music else "aucune (voix seule)")
    mixed = work / "mix.wav"
    audio.mix(voice_path, music, tl.lead_in, tl.total, mixed, cfg)
    voice_only = work / "voice_timeline.wav"
    audio.mix(voice_path, None, tl.lead_in, tl.total, voice_only, cfg)

    mp4 = out_dir / f"{base}.mp4"
    log.info("Assemblage final…")
    montage.assemble(scene_files, tl, mixed, ass, mp4, cfg)

    report = verify.verify(mp4, voice_only, tl, groups, cfg)
    report["voix"] = voice_desc
    report["musique"] = music.name if music else None
    report["clips"] = ["kling" if c else ("kenburns" if animate else "fixe") for c in clips]
    (out_dir / f"{base}_controle.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(verify.format_report(report))
    log.info("✓ %s", mp4)
    return mp4
