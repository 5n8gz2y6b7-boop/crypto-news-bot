#!/usr/bin/env python3
"""Génère des vidéos courtes (Reels/TikTok/Shorts) pour les hébergements des Orres.

Exemple : python generate.py --input input/ --output output/ --only chalet-le-pic --dry-run
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from orres.config import load_config
from orres.errors import KlingPending, OrresError
from orres.loader import discover
from orres.pipeline import Options, process


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Vidéos courtes d'hébergements des Orres (voix off + sous-titres).")
    p.add_argument("--input", type=Path, default=Path("input"), help="dossier des hébergements")
    p.add_argument("--output", type=Path, default=Path("output"), help="dossier de sortie")
    p.add_argument("--cache", type=Path, default=Path("cache"), help="cache Kling (manifest.json, clips)")
    p.add_argument("--config", type=Path, default=None, help="config.yaml à utiliser")
    p.add_argument("--music-dir", type=Path, help="dossier de musiques (défaut : config.yaml, assets/music)")
    p.add_argument("--only", help="ne traiter que ce dossier")
    p.add_argument("--lang", choices=["fr", "en"], help="langue du script et de la voix")
    p.add_argument("--voice", help="voix TTS (ex. fr-FR-HenriNeural)")
    p.add_argument("--engine", choices=["edge", "piper", "espeak"], help="moteur TTS (défaut : config.yaml)")
    p.add_argument("--script-only", action="store_true", help="génère et affiche uniquement le script")
    p.add_argument("--approve-script", action="store_true", help="valide le script affiché et continue")
    p.add_argument("--regen-script", action="store_true", help="régénère script.json (écrase vos corrections)")
    p.add_argument("--dry-run", action="store_true", help="aucun appel Kling : montage avec plans fixes")
    p.add_argument("--fallback-kenburns", action="store_true", help="Ken Burns local à la place des clips manquants")
    p.add_argument("--resume", action="store_true", help="reprend avec la voix et les clips déjà en cache")
    p.add_argument("--no-subs", action="store_true", help="sans sous-titres karaoké (titres conservés)")
    p.add_argument("--no-music", action="store_true", help="voix seule")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)-7s %(message)s")
    log = logging.getLogger("orres")
    try:
        cfg = load_config(args.config)
        if args.music_dir:
            cfg["music"]["dir"] = str(args.music_dir.resolve())
        opts = Options(output=args.output, cache=args.cache, lang=args.lang, voice=args.voice, engine=args.engine,
                       script_only=args.script_only, approve_script=args.approve_script,
                       regen_script=args.regen_script, dry_run=args.dry_run,
                       fallback_kenburns=args.fallback_kenburns, resume=args.resume, no_subs=args.no_subs,
                       no_music=args.no_music)
        folders = discover(args.input, args.only)
    except OrresError as exc:
        log.error("✗ %s", exc)
        return 2
    status = 0
    for folder in folders:
        try:
            process(folder, cfg, opts)
        except KlingPending as exc:
            log.warning("⏸ %s", exc)
            status = max(status, 3)
        except OrresError as exc:
            log.error("✗ %s : %s", folder.name, exc)
            status = 2
        except KeyboardInterrupt:
            log.error("Interrompu.")
            return 130
    return status


if __name__ == "__main__":
    sys.exit(main())
