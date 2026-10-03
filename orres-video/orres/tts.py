"""Moteurs de synthèse vocale derrière une interface commune (edge-tts, Piper, espeak-ng)."""
from __future__ import annotations

import asyncio
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .config import resolve
from .errors import ToolError


@dataclass
class WordTiming:
    """Un mot et ses bornes en secondes, relatives au début du fichier audio."""

    word: str
    start: float
    end: float


@dataclass
class TTSResult:
    audio_path: Path
    words: list[WordTiming] | None  # None = le moteur ne fournit pas de timestamps


class TTSEngine(Protocol):
    name: str

    def synthesize(self, text: str, voice: str, out_path: Path) -> TTSResult: ...


class EdgeTTS:
    """edge-tts : gratuit, sans clé, voix neurales, timestamps par mot (WordBoundary)."""

    name = "edge"

    def __init__(self, cfg: dict[str, Any]):
        try:
            import edge_tts  # noqa: F401
        except ImportError as exc:
            raise ToolError("edge-tts n'est pas installé : pip install edge-tts") from exc
        self.cfg = cfg["tts"]

    def synthesize(self, text: str, voice: str, out_path: Path) -> TTSResult:
        try:
            return asyncio.run(self._run(text, voice, out_path))
        except ToolError:
            raise
        except Exception as exc:  # aiohttp, websockets, NoAudioReceived...
            raise ToolError(
                f"edge-tts injoignable ou en erreur ({type(exc).__name__}: {exc}). Vérifiez la connexion "
                "Internet, le nom de la voix, ou passez tts.engine à 'piper' dans config.yaml.") from exc

    async def _run(self, text: str, voice: str, out_path: Path) -> TTSResult:
        import edge_tts

        comm = edge_tts.Communicate(
            text, voice, rate=self.cfg.get("rate", "+0%"), pitch=self.cfg.get("pitch", "+0Hz"),
            boundary="WordBoundary", connect_timeout=self.cfg.get("connect_timeout_s", 10),
            receive_timeout=self.cfg.get("receive_timeout_s", 60))
        words: list[WordTiming] = []
        mp3 = out_path.with_suffix(".mp3")
        with open(mp3, "wb") as fh:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    fh.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / 1e7  # unités de 100 ns
                    words.append(WordTiming(chunk["text"], start, start + chunk["duration"] / 1e7))
        if mp3.stat().st_size == 0:
            raise ToolError(f"edge-tts n'a renvoyé aucun audio pour la voix « {voice} ».")
        to_wav(mp3, out_path)
        mp3.unlink(missing_ok=True)
        return TTSResult(out_path, words or None)


class PiperTTS:
    """Piper : 100 % hors ligne, pas de timestamps (alignement faster-whisper ensuite)."""

    name = "piper"

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.exe = cfg["tts"]["piper"].get("executable", "piper")
        if not shutil.which(self.exe):
            raise ToolError("Piper introuvable : pip install piper-tts (puis téléchargez un modèle .onnx).")

    def synthesize(self, text: str, voice: str, out_path: Path) -> TTSResult:
        model = Path(voice) if voice.endswith(".onnx") else None
        if model is None:
            lang = "en" if voice.lower().startswith("en") else "fr"
            model = resolve(self.cfg, self.cfg["tts"]["piper"]["models"][lang])
        if not model.exists():
            raise ToolError(f"Modèle Piper introuvable : {model} (voir README, section Piper).")
        raw = out_path.with_suffix(".raw.wav")
        cmd = [self.exe, "--model", str(model), "--output_file", str(raw),
               "--length_scale", str(self.cfg["tts"]["piper"].get("length_scale", 1.0))]
        res = subprocess.run(cmd, input=text, text=True, capture_output=True)
        if res.returncode != 0 or not raw.exists():
            raise ToolError(f"Piper a échoué : {res.stderr.strip()[-400:]}")
        to_wav(raw, out_path)
        raw.unlink(missing_ok=True)
        return TTSResult(out_path, None)


class EspeakTTS:
    """espeak-ng : hors ligne, voix robotique. Uniquement pour tester rythme et synchro."""

    name = "espeak"

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg["tts"]["espeak"]
        self.exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if not self.exe:
            raise ToolError("espeak-ng introuvable (apt install espeak-ng).")

    def synthesize(self, text: str, voice: str, out_path: Path) -> TTSResult:
        raw = out_path.with_suffix(".raw.wav")
        cmd = [self.exe, "-v", voice, "-s", str(self.cfg.get("speed_wpm", 150)), "-w", str(raw), text]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise ToolError(f"espeak-ng a échoué : {res.stderr.strip()}")
        to_wav(raw, out_path)
        raw.unlink(missing_ok=True)
        return TTSResult(out_path, None)


ENGINES = {"edge": EdgeTTS, "piper": PiperTTS, "espeak": EspeakTTS}


def make_engine(cfg: dict[str, Any], name: str | None = None) -> TTSEngine:
    name = name or cfg["tts"]["engine"]
    if name not in ENGINES:
        raise ToolError(f"Moteur TTS inconnu : {name} ({', '.join(ENGINES)}).")
    return ENGINES[name](cfg)


def default_voice(cfg: dict[str, Any], engine: str, lang: str, override: str | None) -> str:
    """Voix effective : option --voice / info.yaml, sinon config.yaml."""
    if override:
        return override
    if engine == "espeak":
        return cfg["tts"]["espeak"]["voices"][lang]
    if engine == "piper":
        return lang
    return cfg["tts"]["voices"][lang]


def to_wav(src: Path, dst: Path) -> None:
    """Convertit en WAV mono 48 kHz (format de travail)."""
    res = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ac", "1", "-ar", "48000",
                          "-c:a", "pcm_s16le", str(dst)], capture_output=True, text=True)
    if res.returncode != 0:
        raise ToolError(f"FFmpeg n'a pas pu convertir {src.name} : {res.stderr.strip()}")
