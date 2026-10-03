#!/usr/bin/env python3
"""Outil de suivi des jobs Kling dans cache/manifest.json.

Les appels Kling passent par le connecteur MCP de Claude ; cet outil enregistre chaque étape
pour pouvoir reprendre (--resume) sans jamais repayer un clip :

    python kling_cache.py status  output/<slug>/kling_jobs.json
    python kling_cache.py upload  <KEY> --upload-url URL --ticket TICKET   # POST multipart ticket + file
    python kling_cache.py set     <KEY> generation_id=XXX status=submitted
    python kling_cache.py download <KEY> <URL_DU_CLIP>                   # à faire tout de suite (URL 24 h)
    python kling_cache.py fail    <KEY> "message d'erreur"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

from orres.manifest import Manifest


def _find_url(payload: object) -> str | None:
    """Cherche l'URL du fichier dans la réponse d'upload (structure non documentée)."""
    if isinstance(payload, str) and payload.startswith("http"):
        return payload
    if isinstance(payload, dict):
        for k in ("url", "fileUrl", "file_url", "resourceUrl"):
            if isinstance(payload.get(k), str):
                return payload[k]
        for v in payload.values():
            found = _find_url(v)
            if found:
                return found
    if isinstance(payload, list):
        for v in payload:
            found = _find_url(v)
            if found:
                return found
    return None


def cmd_status(m: Manifest, jobs_file: Path | None) -> None:
    keys = None
    if jobs_file:
        data = json.loads(jobs_file.read_text(encoding="utf-8"))
        print(json.dumps(data["budget"], ensure_ascii=False, indent=2))
        keys = [j["key"] for j in data["jobs"]]
    for key, it in m.items.items():
        if keys is None or key in keys:
            print(f"{it.get('status', '?'):<11} {key}  gen={it.get('generation_id', '-')}  "
                  f"img={Path(it.get('prepared_image', '')).name}  clip={it.get('clip_path', '-')}")


def cmd_upload(m: Manifest, key: str, upload_url: str, ticket: str) -> None:
    it = m.get(key) or sys.exit(f"Clé inconnue : {key}")
    img = Path(it["prepared_image"])
    mime = "image/png" if img.suffix.lower() == ".png" else "image/jpeg"
    with open(img, "rb") as fh:
        r = requests.post(upload_url, data={"ticket": ticket}, files={"file": (img.name, fh, mime)}, timeout=120)
    if r.status_code >= 400:
        sys.exit(f"Upload refusé ({r.status_code}) : {r.text[:400]}")
    try:
        payload = r.json()
    except ValueError:
        payload = r.text
    url = _find_url(payload)
    if not url:
        sys.exit(f"URL introuvable dans la réponse : {str(payload)[:400]}")
    m.upsert(key, status="uploaded", upload_url=url)
    print(url)


def cmd_set(m: Manifest, key: str, pairs: list[str]) -> None:
    fields = dict(p.split("=", 1) for p in pairs)
    m.upsert(key, **fields)
    print(json.dumps(m.get(key), ensure_ascii=False, indent=2))


def cmd_download(m: Manifest, key: str, url: str) -> None:
    if not m.get(key):
        sys.exit(f"Clé inconnue : {key}")
    dst = m.path.parent / "clips" / f"{key}.mp4"
    dst.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=300) as r:
        if r.status_code >= 400:
            sys.exit(f"Téléchargement refusé ({r.status_code}) — l'URL a peut-être expiré (24 h).")
        tmp = dst.with_suffix(".part")
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
        tmp.replace(dst)
    m.upsert(key, status="downloaded", clip_path=str(dst.relative_to(m.path.parent)), clip_url=url)
    print(dst)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", type=Path, default=Path("cache"))
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("jobs", type=Path, nargs="?")
    u = sub.add_parser("upload")
    u.add_argument("key")
    u.add_argument("--upload-url", required=True)
    u.add_argument("--ticket", required=True)
    st = sub.add_parser("set")
    st.add_argument("key")
    st.add_argument("pairs", nargs="+")
    d = sub.add_parser("download")
    d.add_argument("key")
    d.add_argument("url")
    f = sub.add_parser("fail")
    f.add_argument("key")
    f.add_argument("message")
    a = p.parse_args()
    m = Manifest(a.cache / "manifest.json")
    if a.cmd == "status":
        cmd_status(m, a.jobs)
    elif a.cmd == "upload":
        cmd_upload(m, a.key, a.upload_url, a.ticket)
    elif a.cmd == "set":
        cmd_set(m, a.key, a.pairs)
    elif a.cmd == "download":
        cmd_download(m, a.key, a.url)
    elif a.cmd == "fail":
        m.upsert(a.key, status="failed", error=a.message)


if __name__ == "__main__":
    main()
