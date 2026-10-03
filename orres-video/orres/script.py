"""Script de voix off : généré uniquement à partir d'info.yaml, découpé en un segment par plan."""
from __future__ import annotations

import itertools
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .errors import ScriptError
from .loader import Property

WORDS_PER_SECOND = 2.5
_PUNCT_ONLY = re.compile(r"^[\W_]+$", re.UNICODE)

FEMININE = {"résidence", "maison", "villa", "chambre", "suite", "ferme", "cabane", "location", "auberge"}
MASCULINE = {"chalet", "appartement", "studio", "gîte", "hôtel", "duplex", "loft", "refuge", "domaine", "logement"}


@dataclass
class Segment:
    """Une phrase de voix off rattachée à un plan (une photo)."""

    index: int
    role: str      # accroche | point_fort | ambiance | capacite | prix | cta
    plan: str
    image: str
    texte: str
    mots: int = 0

    def __post_init__(self) -> None:
        self.mots = count_words(self.texte)


@dataclass
class Script:
    """Script complet d'un hébergement."""

    hebergement: str
    langue: str
    source: str  # "généré" | "manuel"
    segments: list[Segment]
    valide: bool = False
    avertissements: list[str] = field(default_factory=list)

    @property
    def total_mots(self) -> int:
        return sum(s.mots for s in self.segments)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["total_mots"] = self.total_mots
        d["duree_estimee_s"] = round(self.total_mots / WORDS_PER_SECOND, 1)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Script":
        segs = [Segment(**{k: v for k, v in s.items() if k != "mots"}) for s in d["segments"]]
        return cls(hebergement=d["hebergement"], langue=d["langue"], source=d.get("source", "manuel"),
                   segments=segs, valide=bool(d.get("valide")), avertissements=d.get("avertissements", []))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Script":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def pretty(self) -> str:
        lines = [f"Script « {self.hebergement} » ({self.langue}, {self.source}) — "
                 f"{self.total_mots} mots, ~{self.total_mots / WORDS_PER_SECOND:.0f} s"]
        for s in self.segments:
            lines.append(f"  {s.index}. [{s.plan:<13}] {s.image:<10} ({s.mots:>2} mots) {s.texte}")
        lines += [f"  ⚠ {w}" for w in self.avertissements]
        return "\n".join(lines)


# --------------------------------------------------------------------------- texte

def tokenize(text: str) -> list[str]:
    """Mots du texte ; une ponctuation isolée (« : ») est collée au mot précédent."""
    out: list[str] = []
    for t in text.split():
        if _PUNCT_ONLY.match(t):
            if out:
                out[-1] += t
            continue
        out.append(t)
    return out


def count_words(text: str) -> int:
    return len(tokenize(text))


def normalize(word: str) -> str:
    """Forme comparable d'un mot : minuscules, sans accents ni ponctuation."""
    w = unicodedata.normalize("NFKD", word.lower())
    w = "".join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[^\w€]", "", w)


def speakable(text: str, lang: str = "fr") -> str:
    """Rend un prix prononçable (« 120 €/nuit » → « 120 euros la nuit »)."""
    if lang == "fr":
        text = re.sub(r"\s*€\s*/\s*(nuit|semaine|séjour|personne)", r" euros la \1", text)
        text = re.sub(r"\s*€", " euros", text)
    else:
        text = re.sub(r"\s*€\s*/\s*(night|week|stay|person)", r" euros per \1", text)
        text = re.sub(r"€\s*(\d[\d.,]*)", r"\1 euros", text)
        text = re.sub(r"\s*€", " euros", text)
    return re.sub(r"\s+", " ", text).strip()


def lower_first(s: str) -> str:
    """Minuscule initiale sauf sigle ou nom propre évident (« Serre-Ponçon »)."""
    if len(s) > 1 and s[1].islower():
        return s[0].lower() + s[1:]
    return s


def _first_word(s: str) -> str:
    return s.split()[0].lower() if s.split() else ""


def _starts_vowel(s: str) -> bool:
    return bool(s) and normalize(s[0]) in "aeiouyh"


def with_article(nom: str, prep: bool) -> str:
    """« au Chalet X » / « à la Résidence Y » (prep=True) ou « le Chalet X » (prep=False)."""
    low = nom.lower()
    for art, rest_prep in (("le ", "au "), ("la ", "à la "), ("les ", "aux "), ("l'", "à l'")):
        if low.startswith(art):
            rest = nom[len(art):]
            return (rest_prep + rest) if prep else nom[0].lower() + nom[1:]
    fw = _first_word(nom)
    if fw in FEMININE:
        return ("à la " if prep else "la ") + nom
    if fw in MASCULINE and not _starts_vowel(fw):
        return ("au " if prep else "le ") + nom
    if fw in MASCULINE or fw in FEMININE or fw.startswith(("hôtel", "hotel", "appart")):
        return ("à l'" if prep else "l'") + nom
    return ("à " if prep else "") + nom


def demonstrative(type_: str) -> str:
    """« ce chalet », « cette résidence », « cet appartement »."""
    t = lower_first(type_)
    fw = _first_word(t)
    if fw in FEMININE:
        return f"cette {t}"
    if _starts_vowel(fw):
        return f"cet {t}"
    return f"ce {t}"


def locative(secteur: str) -> str:
    """« Les Orres 1650 » → « aux Orres 1650 »."""
    if secteur.lower().startswith("les "):
        return "aux " + secteur[4:]
    if "orres" not in secteur.lower():
        return f"aux Orres, secteur {secteur}"
    return "à " + secteur


# --------------------------------------------------------------------------- modèles

TEMPLATES: dict[str, dict[str, dict[str, list[str]]]] = {
    "fr": {
        "chaleureux": {
            "accroche": ["Bienvenue {au_nom}, {loc}.", "Bienvenue {au_nom}, votre {type_l} {loc}.",
                         "Bienvenue {au_nom}, {loc}, dans les Hautes-Alpes."],
            "pf0": ["Premier atout de {ce_type} : {pf}.", "Premier coup de cœur : {pf}.",
                    "Ici, premier atout et non des moindres : {pf}."],
            "pf1": ["Autre point fort : {pf}.", "Vous allez aussi adorer : {pf}.",
                    "Autre atout à ne pas manquer : {pf}."],
            "pf2": ["Et ce n'est pas tout : {pf}.", "Sans oublier un vrai plus : {pf}.",
                    "Et pour compléter le tableau : {pf}."],
            "pf3": ["Enfin : {pf}.", "Enfin, dernier atout : {pf}.", "Enfin, dernier atout et non des moindres : {pf}."],
            "ambiance": ["Un séjour {saison_de} à vivre aux Orres.",
                         "Tout est prêt pour un beau séjour {saison_de} aux Orres."],
            "capacite": ["Capacité : {cap}, pour partager de beaux moments.",
                         "{Ce_type} accueille {cap}, idéal pour partager vos vacances.",
                         "{Ce_type} peut accueillir {cap}, en famille ou entre amis."],
            "prix": ["Tarif indicatif : {prix}.", "Côté tarif, c'est {prix}, à titre indicatif.",
                     "Pour le budget, comptez {prix}, à titre indicatif."],
            "cta": ["{cta} dès maintenant !", "{cta}, et à très bientôt aux Orres !",
                    "{cta} dès maintenant, et à très bientôt aux Orres !"],
        },
        "dynamique": {
            "accroche": ["Direction {le_nom}, {loc} !", "Cap sur {le_nom}, {loc}, c'est parti !",
                         "Cap sur {le_nom}, {loc}, dans les Hautes-Alpes !"],
            "pf0": ["Atout numéro un : {pf} !", "On commence fort : {pf} !", "On commence très fort ici : {pf} !"],
            "pf1": ["Atout numéro deux : {pf} !", "Et ensuite : {pf} !", "On enchaîne avec un autre atout : {pf} !"],
            "pf2": ["Et en bonus : {pf} !", "Atout numéro trois : {pf} !", "Et en prime, un vrai bonus : {pf} !"],
            "pf3": ["Et enfin : {pf} !", "Dernier atout, et pas des moindres : {pf} !"],
            "ambiance": ["Ton séjour {saison_de} aux Orres commence ici !"],
            "capacite": ["Toute la tribu est la bienvenue : {cap} !", "{Ce_type} accueille {cap}, parfait pour la bande !",
                         "{Ce_type} accueille {cap}, parfait pour toute la bande !"],
            "prix": ["Prix indicatif : {prix} !", "Le tout {prix}, à titre indicatif !",
                     "Et le meilleur : {prix}, à titre indicatif !"],
            "cta": ["{cta} vite !", "{cta}, on se voit aux Orres !", "{cta} vite, et on se voit aux Orres !"],
        },
        "premium": {
            "accroche": ["Découvrez {le_nom}, {loc}.", "Bienvenue {au_nom}, une adresse {loc}.",
                         "Découvrez {le_nom}, {loc}, au cœur des Hautes-Alpes."],
            "pf0": ["Un privilège : {pf}.", "Premier privilège de {ce_type} : {pf}.",
                    "Premier privilège de cette adresse : {pf}."],
            "pf1": ["Le raffinement se poursuit : {pf}.", "Autre privilège : {pf}.",
                    "Le raffinement se poursuit avec ceci : {pf}."],
            "pf2": ["Pour votre bien-être : {pf}.", "Un dernier raffinement : {pf}.",
                    "Et pour parfaire l'expérience : {pf}."],
            "pf3": ["Enfin : {pf}.", "Enfin, ultime privilège : {pf}."],
            "ambiance": ["Un séjour {saison_de} d'exception aux Orres."],
            "capacite": ["{Ce_type} accueille {cap}.", "{Ce_type} accueille {cap}, en toute intimité.",
                         "{Ce_type} accueille {cap}, pour un séjour en toute intimité."],
            "prix": ["Tarif indicatif : {prix}.", "Le tarif indicatif : {prix}.",
                     "Le séjour est proposé {prix}, à titre indicatif."],
            "cta": ["{cta}.", "{cta} dès aujourd'hui.", "{cta} dès aujourd'hui, et à bientôt aux Orres."],
        },
    },
    "en": {
        "chaleureux": {
            "accroche": ["Welcome to {nom}, in {secteur}.", "Welcome to {nom}, your {type_l} in {secteur}.",
                         "Welcome to {nom}, in {secteur}, in the French Alps."],
            "pf0": ["First highlight of this {type_l}: {pf}.", "First thing you'll love: {pf}.",
                    "Here is the very first highlight of this place: {pf}."],
            "pf1": ["Another highlight: {pf}.", "You will also love this: {pf}.",
                    "Another highlight not to be missed: {pf}."],
            "pf2": ["And that's not all: {pf}.", "And a real bonus: {pf}.", "And to complete the picture: {pf}."],
            "pf3": ["Finally: {pf}.", "Finally, one last highlight: {pf}."],
            "ambiance": ["A {saison_adj} stay to enjoy in Les Orres."],
            "capacite": ["It sleeps {cap}, perfect for sharing.", "This {type_l} sleeps {cap}, perfect for sharing.",
                         "This {type_l} sleeps {cap}, for family or friends."],
            "prix": ["Indicative price: {prix}.", "Prices start {prix}, as a guide.",
                     "As a guide, the price is {prix}."],
            "cta": ["{cta} now!", "{cta}, see you soon in Les Orres!", "{cta} now, and see you soon in Les Orres!"],
        },
    },
}


def _context(prop: Property, lang: str) -> dict[str, str]:
    if lang == "fr":
        ce = demonstrative(prop.type)
        return {
            "nom": prop.nom, "au_nom": with_article(prop.nom, True), "le_nom": with_article(prop.nom, False),
            "loc": locative(prop.station_secteur), "secteur": prop.station_secteur,
            "type_l": lower_first(prop.type), "ce_type": ce, "Ce_type": ce[0].upper() + ce[1:],
            "cap": prop.capacite, "prix": speakable(prop.prix_indicatif, "fr"), "cta": prop.cta,
            "saison_de": "d'hiver" if prop.saison == "hiver" else "d'été",
        }
    ex = prop.extra
    missing = [k for k in ("type_en", "points_forts_en", "capacite_en", "prix_indicatif_en", "cta_en")
               if not ex.get(k)]
    if missing:
        raise ScriptError(
            "--lang en : pour une traduction fidèle sans rien inventer, ajoutez dans info.yaml : "
            + ", ".join(missing) + " (ou 'script_manuel_en'). Je peux traduire le script validé pour vous.")
    return {
        "nom": prop.nom, "secteur": prop.station_secteur, "type_l": lower_first(str(ex["type_en"])),
        "cap": str(ex["capacite_en"]), "prix": speakable(str(ex["prix_indicatif_en"]), "en"),
        "cta": str(ex["cta_en"]), "saison_adj": "winter" if prop.saison == "hiver" else "summer",
    }


def _slots(n_pf: int, cfg_script: dict[str, Any]) -> list[str]:
    slots = ["accroche"] + [f"pf{i}" for i in range(n_pf)]
    base = len(slots) + 3
    if base < cfg_script["min_segments"]:
        slots += ["ambiance"] * (cfg_script["min_segments"] - base)
    return slots + ["capacite", "prix", "cta"]


def _role(slot: str) -> str:
    return "point_fort" if slot.startswith("pf") else slot


def generate_script(prop: Property, cfg: dict[str, Any], lang: str | None = None) -> Script:
    """Construit le script. Les seules données utilisées sont celles d'info.yaml."""
    sc = cfg["script"]
    lang = lang or prop.langue
    manual = prop.script_manuel if lang == "fr" else str(prop.extra.get("script_manuel_en") or "")
    if manual:
        return _manual_script(prop, cfg, manual, lang)

    ctx = _context(prop, lang)
    pfs_src = prop.points_forts if lang == "fr" else list(prop.extra["points_forts_en"])
    warnings: list[str] = []
    if len(pfs_src) > sc["max_points_forts"]:
        warnings.append(f"{len(pfs_src)} points forts : seuls les {sc['max_points_forts']} premiers sont narrés.")
        pfs_src = pfs_src[: sc["max_points_forts"]]
    pfs = [lower_first(speakable(p, lang)) for p in pfs_src]
    slots = _slots(len(pfs), sc)
    tones = TEMPLATES[lang]
    tone = tones.get(prop.ton, tones["chaleureux"])

    options: list[list[str]] = []
    for slot in slots:
        variants = tone.get(slot) or tones["chaleureux"][slot]
        pf = pfs[int(slot[2:])] if slot.startswith("pf") else ""
        texts = [v.format(pf=pf, **ctx) for v in variants]
        texts = [t[0].upper() + t[1:] for t in texts]
        ok = [t for t in texts if sc["segment_min_words"] <= count_words(t) <= sc["segment_max_words"]]
        if not ok:
            raise ScriptError(
                f"Impossible de formuler le segment « {slot} » en {sc['segment_min_words']}-"
                f"{sc['segment_max_words']} mots (ex. : « {texts[0]} »). Raccourcissez ce champ "
                "d'info.yaml ou utilisez 'script_manuel'.")
        options.append(ok)

    target = (sc["min_words"] + sc["max_words"]) / 2
    best: tuple[float, tuple[str, ...]] | None = None
    for combo in itertools.product(*options):
        total = sum(count_words(t) for t in combo)
        if not sc["min_words"] <= total <= sc["max_words"]:
            continue
        # Préfère un total proche du milieu, puis les premières variantes (plus naturelles).
        score = abs(total - target) + 0.01 * sum(o.index(t) for o, t in zip(options, combo))
        if best is None or score < best[0]:
            best = (score, combo)
    if best is None:
        totals = sum(count_words(o[0]) for o in options), sum(count_words(o[-1]) for o in options)
        raise ScriptError(
            f"Impossible d'atteindre {sc['min_words']}-{sc['max_words']} mots (entre {min(totals)} et "
            f"{max(totals)} possibles). Ajoutez/retirez un point fort ou utilisez 'script_manuel'.")

    segments = [_segment(i, slot, text, prop, cfg) for i, (slot, text) in enumerate(zip(slots, best[1]))]
    script = Script(prop.slug, lang, "généré", segments, avertissements=warnings)
    script.avertissements += validate_script(script, prop, cfg)
    return script


def _segment(i: int, slot: str, text: str, prop: Property, cfg: dict[str, Any]) -> Segment:
    plans = prop.plans or cfg["script"]["default_plans"]
    plan = plans[i] if i < len(plans) else plans[i % len(plans)]
    image = prop.images[i % len(prop.images)].name
    return Segment(index=i + 1, role=_role(slot), plan=plan, image=image, texte=text)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _manual_script(prop: Property, cfg: dict[str, Any], text: str, lang: str) -> Script:
    sentences = split_sentences(text)
    n = len(sentences)
    roles = ["accroche"] + ["point_fort"] * max(n - 4, 0) + ["capacite", "prix", "cta"]
    roles = roles[:n] if n >= 4 else ["libre"] * n
    segs = [Segment(index=i + 1, role=roles[i], plan="", image="", texte=s) for i, s in enumerate(sentences)]
    for s, base in zip(segs, [_segment(i, "x", "x", prop, cfg) for i in range(n)]):
        s.plan, s.image = base.plan, base.image
    script = Script(prop.slug, lang, "manuel", segs)
    script.avertissements = validate_script(script, prop, cfg)
    return script


def validate_script(script: Script, prop: Property, cfg: dict[str, Any]) -> list[str]:
    """Contrôle longueurs et véracité ; renvoie la liste des avertissements."""
    sc = cfg["script"]
    out: list[str] = []
    n = len(script.segments)
    if not sc["min_segments"] <= n <= sc["max_segments"]:
        out.append(f"{n} segments (attendu {sc['min_segments']}-{sc['max_segments']}).")
    if not sc["min_words"] <= script.total_mots <= sc["max_words"]:
        out.append(f"{script.total_mots} mots (attendu {sc['min_words']}-{sc['max_words']}).")
    for s in script.segments:
        if not sc["segment_min_words"] <= s.mots <= sc["segment_max_words"]:
            out.append(f"Segment {s.index} : {s.mots} mots (attendu {sc['segment_min_words']}-"
                       f"{sc['segment_max_words']}).")
    out += truth_check(" ".join(s.texte for s in script.segments), prop, cfg, script.langue)
    return out


def truth_check(text: str, prop: Property, cfg: dict[str, Any], lang: str = "fr") -> list[str]:
    """Signale équipements ou chiffres présents dans le script mais absents d'info.yaml."""
    facts = " ".join(normalize(w) for w in prop.facts_text().split())
    said = " ".join(normalize(w) for w in text.split())
    problems = []
    for term in cfg["script"].get(f"risky_terms_{lang}", []):
        t = " ".join(normalize(w) for w in term.split())
        if re.search(rf"\b{re.escape(t)}\b", said) and not re.search(rf"\b{re.escape(t)}\b", facts):
            problems.append(f"Véracité : « {term} » n'apparaît pas dans info.yaml.")
    fact_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", prop.facts_text()))
    for num in sorted(set(re.findall(r"\d+(?:[.,]\d+)?", text))):
        if num not in fact_numbers:
            problems.append(f"Véracité : le chiffre « {num} » n'apparaît pas dans info.yaml.")
    return problems


def keywords(prop: Property, lang: str = "fr") -> set[str]:
    """Mots à colorer dans les sous-titres : nom, points forts, prix."""
    src = [prop.nom, speakable(prop.prix_indicatif, lang)]
    src += prop.points_forts if lang == "fr" else list(prop.extra.get("points_forts_en") or [])
    stop = {"le", "la", "les", "de", "du", "des", "sur", "aux", "au", "a", "à", "et", "the", "of", "on", "in",
            "partir", "from", "un", "une", "l", "d"}
    out = set()
    for phrase in src:
        for w in speakable(phrase, lang).split():
            n = normalize(w)
            if n and n not in stop:
                out.add(n)
    return out
