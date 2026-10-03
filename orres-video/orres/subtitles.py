"""Sous-titres ASS karaoké (mot prononcé en couleur + pop), titres graphiques intro/outro, export SRT."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .loader import Property
from .script import normalize
from .timeline import Timeline
from .tts import WordTiming

_TRAIL = re.compile(r"[.,;:!?…]+$")


@dataclass
class Group:
    """2 à 4 mots affichés ensemble."""

    words: list[WordTiming]
    start: float
    end: float
    lines: list[list[int]]  # indices des mots par ligne (1 ou 2 lignes)


def ass_color(hex_color: str, alpha: int = 0) -> str:
    """#RRGGBB → &HAABBGGRR (format ASS)."""
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ass_time(t: float) -> str:
    t = max(t, 0.0)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def srt_time(t: float) -> str:
    ms = int(round(max(t, 0.0) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def display(word: str) -> str:
    """Mot affiché : sans ponctuation finale, accolades neutralisées pour ASS."""
    return _TRAIL.sub("", word).replace("{", "(").replace("}", ")") or word


def split_lines(words: list[str], max_chars: int) -> list[list[int]]:
    """Répartit les mots sur 1 ou 2 lignes équilibrées."""
    text_len = len(" ".join(words))
    if text_len <= max_chars or len(words) == 1:
        return [list(range(len(words)))]
    best_k, best = 1, None
    for k in range(1, len(words)):
        a, b = len(" ".join(words[:k])), len(" ".join(words[k:]))
        score = max(a, b)
        if best is None or score < best:
            best_k, best = k, score
    return [list(range(best_k)), list(range(best_k, len(words)))]


def group_words(words: list[WordTiming], sc: dict[str, Any]) -> list[list[WordTiming]]:
    """Découpe un segment en groupes de 2 à 4 mots, en coupant de préférence après une ponctuation."""
    mn, mx = sc["min_words_per_group"], sc["max_words_per_group"]
    max_chars = sc["max_chars_per_line"] * sc["max_lines"]
    groups: list[list[WordTiming]] = []
    cur: list[WordTiming] = []
    for w in words:
        candidate = cur + [w]
        too_long = len(" ".join(display(x.word) for x in candidate)) > max_chars
        if cur and (len(candidate) > mx or too_long):
            groups.append(cur)
            cur = [w]
        else:
            cur = candidate
        if len(cur) >= mn and _TRAIL.search(w.word):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    # Évite un mot isolé : on le rattache au groupe voisin ou on rééquilibre.
    fixed: list[list[WordTiming]] = []
    for g in groups:
        if len(g) < mn and fixed:
            prev = fixed[-1]
            if len(prev) + len(g) <= mx:
                prev.extend(g)
                continue
            if len(prev) > mn:
                g.insert(0, prev.pop())
        fixed.append(g)
    if len(fixed) > 1 and len(fixed[0]) < mn and len(fixed[0]) + len(fixed[1]) <= mx:
        fixed[1] = fixed[0] + fixed[1]
        fixed.pop(0)
    return fixed


def build_groups(segments_words: list[list[WordTiming]], sc: dict[str, Any]) -> list[Group]:
    """Groupes horodatés pour toute la vidéo (temps globaux)."""
    raw: list[list[WordTiming]] = []
    seg_end: list[float] = []
    for words in segments_words:
        for g in group_words(words, sc):
            raw.append(g)
            seg_end.append(words[-1].end)
    out: list[Group] = []
    for i, g in enumerate(raw):
        start = max(g[0].start - 0.05, out[-1].end if out else 0.0)
        end = g[-1].end + sc["linger_s"]
        end = min(end, seg_end[i] + sc["linger_s"])
        if i + 1 < len(raw):
            end = min(end, raw[i + 1][0].start - 0.05)
        end = max(end, g[-1].end)
        lines = split_lines([display(w.word) for w in g], sc["max_chars_per_line"])
        out.append(Group(g, start, end, lines))
    return out


def _header(cfg: dict[str, Any], pal: dict[str, str]) -> str:
    v, sc = cfg["video"], cfg["subtitles"]
    W, H = v["width"], v["height"]
    text, outline = ass_color(pal["text"]), ass_color(pal["outline"])
    shadow = ass_color(pal["outline"], 0x60)
    card_text, accent = ass_color(pal["card_text"]), ass_color(pal["accent"])
    mv = H - sc["position_y"]
    ml = sc["margin_side"]
    f, ft, fb = sc["font_name"], sc["title_font_name"], sc["body_font_name"]
    fmt = ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
           "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
           "Alignment, MarginL, MarginR, MarginV, Encoding")
    styles = [
        f"Style: Sub,{f},{sc['font_size']},{text},{accent},{outline},{shadow},0,0,0,0,100,100,0,0,1,"
        f"{sc['outline']},{sc['shadow']},2,{ml},{ml},{mv},1",
        f"Style: Title,{ft},100,{text},{accent},{outline},{shadow},0,0,0,0,100,100,0,0,1,6,4,5,{ml},{ml},0,1",
        f"Style: Kicker,{fb},46,{accent},{accent},{outline},{shadow},0,0,0,0,100,100,5,0,1,3,2,5,{ml},{ml},0,1",
        f"Style: Card,{fb},62,{card_text},{accent},{outline},{shadow},0,0,0,0,100,100,0,0,1,3,2,5,{ml},{ml},0,1",
        f"Style: Price,{ft},78,{ass_color(pal['keyword'])},{accent},{outline},{shadow},0,0,0,0,100,100,0,0,1,"
        f"4,3,5,{ml},{ml},0,1",
        f"Style: CTA,{ft},60,{ass_color(pal['card_bg'])},{accent},{accent},{accent},0,0,0,0,100,100,1,0,3,"
        f"22,0,5,{ml},{ml},0,1",
        f"Style: Shape,{fb},10,{accent},{accent},{accent},{accent},0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
    ]
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2",
        "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "", "[V4+ Styles]", fmt, *styles, "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ])


def karaoke_events(groups: list[Group], kw: set[str], cfg: dict[str, Any], pal: dict[str, str]) -> list[str]:
    """Un événement par mot prononcé : le groupe reste affiché, seul le mot actif change."""
    sc = cfg["subtitles"]
    accent, kwc, base = ass_color(pal["accent"]), ass_color(pal["keyword"]), ass_color(pal["text"])
    pop, ps = sc["pop_ms"], sc["pop_scale"]
    events = []
    for g in groups:
        for k, w in enumerate(g.words):
            t0 = g.start if k == 0 else w.start
            t1 = g.end if k == len(g.words) - 1 else g.words[k + 1].start
            if t1 - t0 < 0.01:
                continue
            parts = []
            for line in g.lines:
                tokens = []
                for idx in line:
                    word = display(g.words[idx].word)
                    if idx == k:
                        tokens.append(f"{{\\c{accent}\\fscx100\\fscy100\\t(0,{pop},\\fscx{ps}\\fscy{ps})}}"
                                      f"{word}{{\\c{base}\\fscx100\\fscy100}}")
                    elif normalize(word) in kw:
                        tokens.append(f"{{\\c{kwc}}}{word}{{\\c{base}}}")
                    else:
                        tokens.append(word)
                parts.append(" ".join(tokens))
            fade = f"{{\\fad({sc['fade_in_ms']},0)}}" if k == 0 else ""
            events.append(f"Dialogue: 1,{ass_time(t0)},{ass_time(t1)},Sub,,0,0,0,,{fade}" + "\\N".join(parts))
    return events


def balance_title(text: str, max_chars: int = 15) -> str:
    """Coupe un titre long en deux lignes équilibrées."""
    words = text.split()
    lines = split_lines(words, max_chars)
    return "\\N".join(" ".join(words[i] for i in line) for line in lines)


def title_events(prop: Property, tl: Timeline, cfg: dict[str, Any], lang: str) -> list[str]:
    """Titres animés (slide + fondu) : nom à l'intro ; type, capacité, prix, CTA sur la carte de fin."""
    W = cfg["video"]["width"]
    cx = W // 2
    ev = []

    def slide(t0: float, t1: float, style: str, y: int, text: str, delay_ms: int = 0, dy: int = 50,
              layer: int = 2) -> None:
        a = t0 + delay_ms / 1000
        ev.append(f"Dialogue: {layer},{ass_time(a)},{ass_time(t1)},{style},,0,0,0,,"
                  f"{{\\move({cx},{y + dy},{cx},{y},0,380)\\fad(260,220)}}{text}")

    # Intro : pendant l'accroche, en haut (hors zone des sous-titres)
    intro_end = min(tl.scenes[0].voice_end + 0.1, tl.lead_in + 3.2)
    slide(0.15, intro_end, "Kicker", 330, prop.station_secteur.upper())
    slide(0.15, intro_end, "Title", 450, balance_title(prop.nom), delay_ms=120)
    bar_w = 160
    ev.append(f"Dialogue: 2,{ass_time(0.45)},{ass_time(intro_end)},Shape,,0,0,0,,"
              f"{{\\move({cx - bar_w // 2 - 120},560,{cx - bar_w // 2},560,0,420)\\fad(200,220)\\p1}}"
              f"m 0 0 l {bar_w} 0 {bar_w} 8 0 8{{\\p0}}")

    # Outro : carte graphique
    outro = tl.scenes[-1]
    t0, t1 = tl.boundaries[-2] - tl.xfade / 2 + 0.1, tl.total
    if lang == "fr":
        typ, cap, prix, cta = prop.type, prop.capacite, prop.prix_indicatif, prop.cta
    else:
        ex = prop.extra
        typ, cap = str(ex.get("type_en", prop.type)), str(ex.get("capacite_en", prop.capacite))
        prix, cta = str(ex.get("prix_indicatif_en", prop.prix_indicatif)), str(ex.get("cta_en", prop.cta))
    assert outro.kind == "outro"
    slide(t0, t1, "Kicker", 640, typ.upper())
    slide(t0, t1, "Title", 760, balance_title(prop.nom), delay_ms=100)
    slide(t0, t1, "Card", 950, cap, delay_ms=220)
    slide(t0, t1, "Price", 1070, prix, delay_ms=340)
    slide(t0, t1, "CTA", 1250, cta, delay_ms=480)
    return ev


def write_ass(path: Path, prop: Property, groups: list[Group], tl: Timeline, cfg: dict[str, Any],
              lang: str, kw: set[str], with_subs: bool = True) -> None:
    pal = cfg["palettes"][prop.saison]
    events = title_events(prop, tl, cfg, lang)
    if with_subs:
        events += karaoke_events(groups, kw, cfg, pal)
    path.write_text(_header(cfg, pal) + "\n" + "\n".join(events) + "\n", encoding="utf-8-sig")


def write_srt(path: Path, groups: list[Group]) -> None:
    blocks = []
    for i, g in enumerate(groups, 1):
        text = "\n".join(" ".join(display(g.words[idx].word) for idx in line) for line in g.lines)
        blocks.append(f"{i}\n{srt_time(g.start)} --> {srt_time(g.end)}\n{text}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")
