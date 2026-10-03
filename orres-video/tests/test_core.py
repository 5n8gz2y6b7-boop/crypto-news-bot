"""Tests unitaires sans coût (aucun appel réseau, aucun crédit Kling)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orres.align import map_timings, proportional  # noqa: E402
from orres.config import load_config  # noqa: E402
from orres.errors import InputError, ScriptError  # noqa: E402
from orres.loader import Property, parse_info  # noqa: E402
from orres.manifest import Manifest, job_key  # noqa: E402
from orres.script import (Script, count_words, generate_script, keywords, locative, speakable,  # noqa: E402
                          tokenize, truth_check, with_article)
from orres.subtitles import ass_color, ass_time, build_groups, group_words, split_lines, srt_time  # noqa: E402
from orres.timeline import build_timeline, fit_plan, kling_duration  # noqa: E402
from orres.tts import WordTiming  # noqa: E402

CFG = load_config()
BASE = dict(nom="Chalet Le Pic de Bure", type="Chalet", station_secteur="Les Orres 1650",
            points_forts=["Skis aux pieds", "Vue sur le lac de Serre-Ponçon", "Sauna privatif"],
            capacite="6 personnes", prix_indicatif="à partir de 120 €/nuit", cta="Réservez sur Booking",
            saison="hiver", langue="fr", ton="chaleureux")


def make_prop(**over) -> Property:
    fields = parse_info({**BASE, **over})
    return Property(slug="pic", folder=Path("."), images=[Path(f"{i:02d}.jpg") for i in range(1, 9)], **fields)


# --------------------------------------------------------------------- yaml

def test_parse_info_ok():
    d = parse_info({**BASE, "saison": "Été", "voix": ""})
    assert d["saison"] == "ete" and d["voix"] is None and d["points_forts"][0] == "Skis aux pieds"


@pytest.mark.parametrize("bad, msg", [
    ({"nom": ""}, "nom"),
    ({"saison": "automne"}, "saison"),
    ({"ton": "sérieux"}, "ton"),
    ({"points_forts": [1, 2]}, "points_forts"),
    ({"langue": "de"}, "langue"),
])
def test_parse_info_errors(bad, msg):
    with pytest.raises(InputError, match=msg):
        parse_info({**BASE, **bad})


def test_parse_info_not_a_mapping():
    with pytest.raises(InputError):
        parse_info(["pas", "un", "dict"])


# --------------------------------------------------------------------- script

@pytest.mark.parametrize("ton", ["chaleureux", "dynamique", "premium"])
def test_script_rules(ton):
    s = generate_script(make_prop(ton=ton), CFG)
    sc = CFG["script"]
    assert sc["min_segments"] <= len(s.segments) <= sc["max_segments"]
    assert sc["min_words"] <= s.total_mots <= sc["max_words"]
    assert all(sc["segment_min_words"] <= seg.mots <= sc["segment_max_words"] for seg in s.segments)
    assert s.segments[0].role == "accroche" and "Orres" in s.segments[0].texte and "Pic de Bure" in s.segments[0].texte
    assert [seg.role for seg in s.segments][-3:] == ["capacite", "prix", "cta"]
    assert not [w for w in s.avertissements if w.startswith("Véracité")]


def test_script_uses_only_yaml_facts():
    s = generate_script(make_prop(points_forts=["Skis aux pieds", "Cheminée"]), CFG)
    text = " ".join(seg.texte for seg in s.segments).lower()
    for invented in ("piscine", "spa", "wifi", "parking", "lac", "sauna", "minutes", "km"):
        assert invented not in text


def test_script_pads_with_ambiance_when_few_points():
    s = generate_script(make_prop(points_forts=["Skis aux pieds"]), CFG)
    assert len(s.segments) >= CFG["script"]["min_segments"]
    assert any(seg.role == "ambiance" for seg in s.segments)


def test_script_too_many_points_truncated():
    s = generate_script(make_prop(points_forts=["Skis aux pieds", "Sauna privatif", "Cheminée", "Balcon", "Garage"]), CFG)
    assert len(s.segments) <= CFG["script"]["max_segments"]
    assert any("premiers" in w for w in s.avertissements)


def test_manual_script_split():
    txt = ("Bienvenue au Chalet Le Pic de Bure aux Orres. Skis aux pieds pour profiter de chaque jour. "
           "Un sauna privatif pour se détendre après le ski. Vue sur le lac de Serre-Ponçon depuis le chalet. "
           "Le chalet accueille six personnes en toute simplicité. À partir de 120 euros la nuit. "
           "Réservez sur Booking dès maintenant.")
    s = generate_script(make_prop(script_manuel=txt), CFG)
    assert s.source == "manuel" and len(s.segments) == 7
    assert s.segments[0].image == "01.jpg" and s.segments[-1].role == "cta"


def test_truth_check_flags_inventions():
    p = make_prop()
    probs = truth_check("Profitez de la piscine à 5 minutes des pistes.", p, CFG)
    assert any("piscine" in x for x in probs)
    assert any("5" in x for x in probs)
    assert truth_check("Sauna privatif et vue sur le lac.", p, CFG) == []


def test_english_requires_translated_fields():
    with pytest.raises(ScriptError, match="points_forts_en"):
        generate_script(make_prop(), CFG, "en")
    p = make_prop(type_en="Chalet", points_forts_en=["Ski-in ski-out", "Lake view", "Private sauna"],
                  capacite_en="6 guests", prix_indicatif_en="from €120 per night", cta_en="Book on Booking.com")
    s = generate_script(p, CFG, "en")
    assert s.langue == "en" and "120 euros" in " ".join(x.texte for x in s.segments)


def test_french_helpers():
    assert with_article("Chalet Le Pic", True) == "au Chalet Le Pic"
    assert with_article("Résidence Pra Long", True) == "à la Résidence Pra Long"
    assert with_article("Hôtel du Lac", True) == "à l'Hôtel du Lac"
    assert with_article("Le Grand Chalet", True) == "au Grand Chalet"
    assert locative("Les Orres 1800") == "aux Orres 1800"
    assert speakable("à partir de 120 €/nuit") == "à partir de 120 euros la nuit"
    assert speakable("from €120 per night", "en") == "from 120 euros per night"


def test_tokenize_and_count():
    assert tokenize("Autre point fort : skis aux pieds.") == ["Autre", "point", "fort:", "skis", "aux", "pieds."]
    assert count_words("Premier coup de cœur : skis aux pieds !") == 7


def test_script_json_roundtrip(tmp_path):
    s = generate_script(make_prop(), CFG)
    s.save(tmp_path / "script.json")
    d = json.loads((tmp_path / "script.json").read_text())
    assert d["total_mots"] == s.total_mots and d["valide"] is False
    assert Script.load(tmp_path / "script.json").segments[2].texte == s.segments[2].texte


def test_keywords():
    kw = keywords(make_prop())
    assert {"skis", "pieds", "120", "bure"} <= kw and "de" not in kw


# --------------------------------------------------------------------- durées / timeline

def test_timeline_scenes_cover_voice():
    spans = [(0.0, 3.0), (3.15, 6.0), (6.15, 9.2)]
    tl = build_timeline(spans, CFG)
    lead, f = CFG["video"]["lead_in_s"], CFG["video"]["xfade_s"]
    photos = [s for s in tl.scenes if s.kind == "photo"]
    assert len(photos) == 3 and tl.scenes[-1].kind == "outro"
    for sc, (a, b) in zip(photos, spans):
        assert sc.start <= a + lead and sc.end >= b + lead  # le plan couvre toute sa phrase
    # le centre de chaque fondu est dans le silence entre deux phrases
    for b, ((_, e), (s, _)) in zip(tl.boundaries[1:], zip(spans, spans[1:])):
        assert e + lead < b < s + lead
    assert tl.xfade_offsets[0] == pytest.approx(tl.boundaries[1] - f / 2)
    assert tl.total == pytest.approx(9.2 + lead + max(f / 2 + 0.15, 0.35) + CFG["video"]["outro_s"])


def test_kling_duration_and_fit():
    assert kling_duration(3.2, [5, 10]) == 5
    assert kling_duration(5.0, [5, 10]) == 5
    assert kling_duration(6.1, [5, 10]) == 10
    assert kling_duration(12, [5, 10]) == 10
    assert fit_plan(5.0, 4.0, 0.8)["mode"] == "trim"
    slow = fit_plan(5.0, 6.0, 0.8)
    assert slow["mode"] == "slow" and slow["speed"] == pytest.approx(5 / 6)
    frz = fit_plan(5.0, 8.0, 0.8)
    assert frz["mode"] == "freeze" and frz["speed"] == 0.8 and frz["freeze"] == pytest.approx(8 - 5 / 0.8)


def test_alignment_maps_and_interpolates():
    script = ["Tarif", "indicatif:", "120", "euros", "la", "nuit."]
    rec = [WordTiming("Tarif", 0.0, 0.4), WordTiming("indicatif", 0.4, 1.0), WordTiming("cent", 1.1, 1.3),
           WordTiming("vingt", 1.3, 1.6), WordTiming("euros", 1.6, 2.0), WordTiming("la", 2.0, 2.1),
           WordTiming("nuit", 2.1, 2.5)]
    out = map_timings(script, rec, 2.6)
    assert [w.word for w in out] == script
    assert out[0].start == 0.0 and out[3].start == pytest.approx(1.6)
    assert 1.0 <= out[2].start < out[3].start  # « 120 » interpolé dans le trou
    assert all(a.start <= b.start for a, b in zip(out, out[1:]))
    prop = proportional(["a", "bbbb"], 1.0, 2.0)
    assert prop[0].start == 1.0 and prop[-1].end == pytest.approx(2.0)


# --------------------------------------------------------------------- sous-titres ASS

def _words(text: str, t0: float = 0.0, step: float = 0.4) -> list[WordTiming]:
    return [WordTiming(w, t0 + i * step, t0 + (i + 1) * step - 0.05) for i, w in enumerate(text.split())]


def test_groups_2_to_4_words_and_break_on_punctuation():
    sc = CFG["subtitles"]
    groups = group_words(_words("Autre point fort: vue sur le lac de Serre-Ponçon."), sc)
    assert all(2 <= len(g) <= 4 for g in groups)
    assert groups[0][-1].word == "fort:"


def test_groups_no_orphan_word():
    sc = CFG["subtitles"]
    groups = group_words(_words("Réservez sur Booking dès maintenant !"), sc)
    assert all(len(g) >= 2 for g in groups)


def test_split_lines_max_two():
    assert split_lines(["Bienvenue", "au"], 22) == [[0, 1]]
    lines = split_lines(["Serre-Ponçon", "lac", "magnifique", "superbe"], 16)
    assert len(lines) == 2


def test_ass_helpers():
    assert ass_color("#38BDF8") == "&H00F8BD38"
    assert ass_time(65.256) == "0:01:05.26"
    assert srt_time(3661.5) == "01:01:01,500"


def test_ass_file_contents(tmp_path):
    from orres.subtitles import write_ass, write_srt
    prop = make_prop()
    words = [_words("Bienvenue au Chalet Le Pic de Bure.", 0.5), _words("Skis aux pieds garantis.", 4.0)]
    groups = build_groups(words, CFG["subtitles"])
    tl = build_timeline([(0.0, 2.8), (3.5, 5.0)], CFG)
    kw = keywords(prop)
    write_ass(tmp_path / "s.ass", prop, groups, tl, CFG, "fr", kw)
    txt = (tmp_path / "s.ass").read_text(encoding="utf-8-sig")
    assert "PlayResX: 1080" in txt and "Montserrat ExtraBold" in txt
    dialogues = [l for l in txt.splitlines() if l.startswith("Dialogue: 1,")]
    assert len(dialogues) == sum(len(g.words) for g in groups)  # un événement par mot prononcé
    assert "\\t(0,120,\\fscx115\\fscy115)" in txt and "\\fad(80,0)" in txt
    assert "\\c" + ass_color(CFG["palettes"]["hiver"]["keyword"]) in txt  # mots clés en couleur
    assert "à partir de 120 €/nuit" in txt and "Réservez sur Booking" in txt  # carte de fin
    # sous-titres jamais sur plus de 2 lignes, jamais simultanés
    assert all(l.count("\\N") <= 1 for l in dialogues)
    write_ass(tmp_path / "n.ass", prop, groups, tl, CFG, "fr", kw, with_subs=False)
    assert "Dialogue: 1," not in (tmp_path / "n.ass").read_text(encoding="utf-8-sig")
    write_srt(tmp_path / "s.srt", groups)
    srt = (tmp_path / "s.srt").read_text()
    assert srt.startswith("1\n00:00:00,450 --> ") and "Bienvenue au" in srt


def test_groups_do_not_overlap():
    words = [_words("Bienvenue au Chalet Le Pic de Bure.", 0.5), _words("Skis aux pieds garantis.", 3.5)]
    groups = build_groups(words, CFG["subtitles"])
    for a, b in zip(groups, groups[1:]):
        assert a.end <= b.start + 1e-6


# --------------------------------------------------------------------- manifest

def test_manifest_resume(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    key = job_key("a" * 64, 5, "kling-x", "slow dolly forward")
    assert key == job_key("a" * 64, 5, "kling-x", "slow dolly forward")
    assert key != job_key("a" * 64, 10, "kling-x", "slow dolly forward")
    m.upsert(key, status="uploaded", image_sha256="a" * 64, upload_url="https://u/1")
    m.upsert(key, status="submitted", generation_id="gen-1")
    assert m.clip_for(key) is None
    clip = tmp_path / "clips" / "c.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"x")
    m.upsert(key, status="downloaded", clip_path="clips/c.mp4")
    m2 = Manifest(tmp_path / "manifest.json")  # rechargé depuis le disque
    assert m2.get(key)["generation_id"] == "gen-1"
    assert m2.clip_for(key) == clip
    assert m2.upload_url_for_sha("a" * 64) == "https://u/1"
    with pytest.raises(ValueError):
        m2.upsert(key, status="bidon")
