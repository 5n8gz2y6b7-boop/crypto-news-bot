"""Lecture et validation d'un dossier d'hébergement (info.yaml + photos)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, UnidentifiedImageError

from .errors import InputError

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
REQUIRED = ["nom", "type", "station_secteur", "points_forts", "capacite", "prix_indicatif", "cta", "saison"]
SEASONS = {"hiver": "hiver", "winter": "hiver", "été": "ete", "ete": "ete", "summer": "ete"}
TONES = {"chaleureux", "dynamique", "premium"}


@dataclass
class Property:
    """Un hébergement prêt à être traité."""

    slug: str
    folder: Path
    nom: str
    type: str
    station_secteur: str
    points_forts: list[str]
    capacite: str
    prix_indicatif: str
    cta: str
    saison: str  # "hiver" | "ete"
    langue: str = "fr"
    ton: str = "chaleureux"
    voix: str | None = None
    script_manuel: str = ""
    plans: list[str] = field(default_factory=list)
    images: list[Path] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)  # champs *_en, etc.

    def facts_text(self) -> str:
        """Tout le texte factuel du yaml, pour le contrôle de véracité."""
        parts = [self.nom, self.type, self.station_secteur, self.capacite, self.prix_indicatif,
                 self.cta, *self.points_forts]
        parts += [str(v) for v in self.extra.values() if isinstance(v, (str, int, float))]
        parts += [str(x) for v in self.extra.values() if isinstance(v, list) for x in v]
        return " ".join(parts)


def parse_info(data: Any, source: str = "info.yaml") -> dict[str, Any]:
    """Valide le contenu brut d'info.yaml et renvoie un dict normalisé."""
    if not isinstance(data, dict):
        raise InputError(f"{source} : le fichier doit contenir des paires clé: valeur.")
    missing = [k for k in REQUIRED if not data.get(k)]
    if missing:
        raise InputError(f"{source} : champ(s) obligatoire(s) manquant(s) ou vide(s) : {', '.join(missing)}")
    pf = data["points_forts"]
    if isinstance(pf, str):
        pf = [pf]
    if not isinstance(pf, list) or not all(isinstance(x, str) and x.strip() for x in pf):
        raise InputError(f"{source} : 'points_forts' doit être une liste de textes.")
    saison = SEASONS.get(str(data["saison"]).strip().lower())
    if not saison:
        raise InputError(f"{source} : saison '{data['saison']}' inconnue (hiver ou été).")
    ton = str(data.get("ton") or "chaleureux").strip().lower()
    if ton not in TONES:
        raise InputError(f"{source} : ton '{ton}' inconnu ({' / '.join(sorted(TONES))}).")
    langue = str(data.get("langue") or "fr").strip().lower()
    if langue not in {"fr", "en"}:
        raise InputError(f"{source} : langue '{langue}' non gérée (fr ou en).")
    plans = data.get("plans") or []
    if not isinstance(plans, list):
        raise InputError(f"{source} : 'plans' doit être une liste (ex. [extérieur, séjour]).")
    known = set(REQUIRED) | {"langue", "ton", "voix", "script_manuel", "plans"}
    return {
        "nom": str(data["nom"]).strip(),
        "type": str(data["type"]).strip(),
        "station_secteur": str(data["station_secteur"]).strip(),
        "points_forts": [x.strip() for x in pf],
        "capacite": str(data["capacite"]).strip(),
        "prix_indicatif": str(data["prix_indicatif"]).strip(),
        "cta": str(data["cta"]).strip(),
        "saison": saison,
        "langue": langue,
        "ton": ton,
        "voix": (str(data["voix"]).strip() or None) if data.get("voix") else None,
        "script_manuel": str(data.get("script_manuel") or "").strip(),
        "plans": [str(p).strip().lower() for p in plans],
        "extra": {k: v for k, v in data.items() if k not in known},
    }


def check_image(path: Path) -> tuple[int, int]:
    """Vérifie qu'une image s'ouvre ; renvoie (largeur, hauteur)."""
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            return im.size
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise InputError(f"Image invalide ou corrompue : {path} ({exc})") from exc


def load_property(folder: Path) -> Property:
    """Charge un dossier input/<slug>/."""
    info = folder / "info.yaml"
    if not info.exists():
        raise InputError(f"{folder.name} : info.yaml manquant.")
    try:
        data = yaml.safe_load(info.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise InputError(f"{info} : YAML invalide — {exc}") from exc
    fields = parse_info(data, str(info))
    images = sorted((p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS), key=lambda p: p.name)
    if not images:
        raise InputError(f"{folder.name} : aucune image (.jpg/.png/.webp) trouvée.")
    for img in images:
        w, h = check_image(img)
        if min(w, h) < 480:
            raise InputError(f"Image trop petite ({w}x{h}) : {img} — minimum 480 px sur le petit côté.")
    return Property(slug=folder.name, folder=folder, images=images, **fields)


def discover(input_dir: Path, only: str | None = None) -> list[Path]:
    """Liste les dossiers d'hébergements à traiter."""
    if not input_dir.is_dir():
        raise InputError(f"Dossier d'entrée introuvable : {input_dir}")
    folders = sorted(p for p in input_dir.iterdir() if p.is_dir() and not p.name.startswith("."))
    if only:
        folders = [p for p in folders if p.name == only]
        if not folders:
            raise InputError(f"--only {only} : dossier introuvable dans {input_dir}")
    if not folders:
        raise InputError(f"Aucun hébergement dans {input_dir}")
    return folders
