"""Rattache des timestamps à chaque mot du script (moteur TTS, faster-whisper ou estimation)."""
from __future__ import annotations

import difflib
import logging
from pathlib import Path
from typing import Any

from .script import normalize, tokenize
from .tts import WordTiming

log = logging.getLogger(__name__)
_whisper_model = None


def map_timings(script_words: list[str], recognized: list[WordTiming], duration: float) -> list[WordTiming]:
    """Projette des mots reconnus (edge/whisper) sur les mots du script.

    Les mots appariés gardent leurs bornes ; les autres sont interpolés entre voisins.
    """
    if not recognized:
        return proportional(script_words, 0.0, duration)
    a = [normalize(w) for w in script_words]
    b = [normalize(w.word) for w in recognized]
    starts: list[float | None] = [None] * len(a)
    ends: list[float | None] = [None] * len(a)
    for blk in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            starts[blk.a + k] = recognized[blk.b + k].start
            ends[blk.a + k] = recognized[blk.b + k].end
    # Mots non appariés (ex. « 120 » lu « cent vingt ») : on répartit le trou entre voisins connus.
    i = 0
    first = recognized[0].start
    last = recognized[-1].end
    while i < len(a):
        if starts[i] is not None:
            i += 1
            continue
        j = i
        while j < len(a) and starts[j] is None:
            j += 1
        t0 = ends[i - 1] if i > 0 else first
        t1 = starts[j] if j < len(a) else last
        assert t0 is not None and t1 is not None
        span = proportional(script_words[i:j], t0, max(t1, t0 + 0.05 * (j - i)))
        for k, wt in enumerate(span):
            starts[i + k], ends[i + k] = wt.start, wt.end
        i = j
    out = []
    for w, s, e in zip(script_words, starts, ends):
        assert s is not None and e is not None
        out.append(WordTiming(w, s, max(e, s + 0.05)))
    return _monotonic(out)


def proportional(words: list[str], t0: float, t1: float) -> list[WordTiming]:
    """Estimation : durée de chaque mot proportionnelle à sa longueur (+ une base fixe)."""
    if not words:
        return []
    weights = [len(normalize(w)) + 2 for w in words]
    total = sum(weights)
    out, t = [], t0
    for w, wt in zip(words, weights):
        d = (t1 - t0) * wt / total
        out.append(WordTiming(w, t, t + d))
        t += d
    return out


def _monotonic(words: list[WordTiming]) -> list[WordTiming]:
    for prev, cur in zip(words, words[1:]):
        if cur.start < prev.start:
            cur.start = prev.start
        if prev.end > cur.start:
            prev.end = max(prev.start + 0.02, cur.start)
        cur.end = max(cur.end, cur.start + 0.02)
    return words


def speech_bounds(audio: Path, duration: float) -> tuple[float, float]:
    """Début/fin de la parole (silencedetect), pour caler l'estimation proportionnelle."""
    import re
    import subprocess

    res = subprocess.run(["ffmpeg", "-v", "info", "-i", str(audio), "-af", "silencedetect=n=-40dB:d=0.08",
                          "-f", "null", "-"], capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", res.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", res.stderr)]
    t0 = ends[0] if starts and starts[0] < 0.02 and ends else 0.0
    t1 = starts[-1] if starts and (not ends or starts[-1] > ends[-1]) else duration
    return t0, max(t1, t0 + 0.1)


def whisper_words(audio: Path, lang: str, cfg: dict[str, Any]) -> list[WordTiming] | None:
    """Reconnaissance locale avec faster-whisper (modèle small) ; None si indisponible."""
    global _whisper_model
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    al = cfg["alignment"]
    try:
        if _whisper_model is None:
            _whisper_model = WhisperModel(al["whisper_model"], device=al["device"], compute_type=al["compute_type"])
        segments, _ = _whisper_model.transcribe(str(audio), language=lang, word_timestamps=True)
        return [WordTiming(w.word.strip(), w.start, w.end) for seg in segments for w in (seg.words or [])]
    except Exception as exc:  # modèle non téléchargeable, etc.
        log.warning("faster-whisper indisponible (%s)", exc)
        return None


def align_segment(text: str, audio: Path, duration: float, engine_words: list[WordTiming] | None,
                  lang: str, cfg: dict[str, Any]) -> tuple[list[WordTiming], str]:
    """Renvoie les timestamps des mots du segment et la méthode utilisée."""
    words = tokenize(text)
    if engine_words:
        return map_timings(words, engine_words, duration), "moteur"
    rec = whisper_words(audio, lang, cfg)
    if rec:
        return map_timings(words, rec, duration), "faster-whisper"
    if not cfg["alignment"].get("allow_proportional_fallback", True):
        from .errors import ToolError
        raise ToolError("Pas de timestamps par mot : installez faster-whisper (pip install faster-whisper).")
    t0, t1 = speech_bounds(audio, duration)
    return proportional(words, t0, t1), "estimation"
