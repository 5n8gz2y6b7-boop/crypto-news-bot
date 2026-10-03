"""Chargement de config.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import InputError

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Lit config.yaml et ajoute la clé interne `_root`."""
    path = path or ROOT / "config.yaml"
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InputError(f"config.yaml introuvable : {path}") from exc
    except yaml.YAMLError as exc:
        raise InputError(f"config.yaml invalide : {exc}") from exc
    cfg["_root"] = path.resolve().parent
    return cfg


def resolve(cfg: dict[str, Any], rel: str | Path) -> Path:
    """Résout un chemin relatif au dossier de config.yaml."""
    p = Path(rel)
    return p if p.is_absolute() else cfg["_root"] / p
