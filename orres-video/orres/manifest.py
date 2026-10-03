"""cache/manifest.json : image → generationId → clip local, pour reprendre sans repayer."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

STATUSES = ("prepared", "uploaded", "submitted", "succeeded", "downloaded", "failed")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def job_key(image_sha: str, duration: float, model: str | None, prompt: str) -> str:
    """Clé stable : même image + durée + modèle + prompt = même clip (pas de double paiement)."""
    p = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8]
    return f"{image_sha[:16]}_{duration:g}s_{model or 'model-tbd'}_{p}"


class Manifest:
    """Fichier JSON lisible, réécrit de façon atomique à chaque modification."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = {"version": 1, "items": {}}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))
            self.data.setdefault("items", {})

    @property
    def items(self) -> dict[str, dict[str, Any]]:
        return self.data["items"]

    def get(self, key: str) -> dict[str, Any] | None:
        return self.items.get(key)

    def upsert(self, key: str, **fields: Any) -> dict[str, Any]:
        if "status" in fields and fields["status"] not in STATUSES:
            raise ValueError(f"statut inconnu : {fields['status']}")
        item = self.items.setdefault(key, {"created": _now()})
        item.update({k: v for k, v in fields.items() if v is not None})
        item["updated"] = _now()
        self.save()
        return item

    def clip_for(self, key: str) -> Path | None:
        """Clip local déjà téléchargé et présent sur disque, sinon None."""
        item = self.get(key)
        if item and item.get("status") == "downloaded" and item.get("clip_path"):
            p = Path(item["clip_path"])
            if not p.is_absolute():
                p = self.path.parent / p
            if p.exists() and p.stat().st_size > 0:
                return p
        return None

    def upload_url_for_sha(self, sha: str) -> str | None:
        """URL Kling déjà obtenue pour une image identique (évite un ré-upload)."""
        for item in self.items.values():
            if item.get("image_sha256") == sha and item.get("upload_url"):
                return item["upload_url"]
        return None

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
