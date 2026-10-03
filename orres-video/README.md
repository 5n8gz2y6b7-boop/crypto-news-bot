# Vidéos courtes — hébergements des Orres

Outil en ligne de commande qui produit des vidéos verticales (Instagram Reels, TikTok, YouTube Shorts) de
présentation d'hôtels et de locations des Orres (Hautes-Alpes). Il assemble :

- une **voix off** à partir d'un script généré **uniquement** avec les données d'`info.yaml` ;
- des **sous-titres animés** façon karaoké (le mot prononcé est coloré, avec un léger zoom) ;
- les **photos animées** par Kling AI, ou un effet Ken Burns local si besoin ;
- des **titres graphiques** à l'intro et à l'outro, de la **musique** atténuée automatiquement sous la voix
  (ducking) et un export MP4 1080×1920 (H.264 + AAC), avec un fichier `.srt` à côté.

## 1. Installation

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**FFmpeg avec libass** (indispensable pour les sous-titres) :

```bash
ffmpeg -hide_banner -filters | grep -E " (ass|xfade|loudnorm|sidechaincompress) "
```

Les quatre filtres doivent apparaître. Sinon : `sudo apt install ffmpeg` (Debian/Ubuntu),
`brew install ffmpeg` (macOS) ou une version « full » sur Windows (gyan.dev). L'outil vérifie lui-même la présence
de libass et affiche une erreur claire si elle manque.

La police **Montserrat** (licence OFL) est embarquée dans `assets/fonts/` : rien à installer.

## 2. Préparer un hébergement

```
input/
  chalet-le-pic-de-bure/
    01.jpg, 02.jpg, …    # ordre alphabétique = ordre dans la vidéo
    info.yaml
```

```yaml
nom: "Chalet Le Pic de Bure"
type: "Chalet"
station_secteur: "Les Orres 1650"
points_forts: ["Skis aux pieds", "Vue sur le lac de Serre-Ponçon", "Sauna privatif"]
capacite: "6 personnes"
prix_indicatif: "à partir de 120 €/nuit"
cta: "Réservez sur Booking"
saison: "hiver"            # hiver / été
langue: "fr"
ton: "chaleureux"          # chaleureux / dynamique / premium
voix: "fr-FR-DeniseNeural" # optionnel
script_manuel: ""          # optionnel : remplace le script généré (une phrase = un plan)
plans: ["extérieur", "séjour", "vue", "chambre", "cuisine", "salle de bain", "extérieur"]  # optionnel
# Pour --lang en (traduction fidèle, rien d'inventé) :
type_en: "Chalet"
points_forts_en: ["Ski-in ski-out", "View over Lake Serre-Ponçon", "Private sauna"]
capacite_en: "6 guests"
prix_indicatif_en: "from €120 per night"
cta_en: "Book on Booking.com"
```

`plans` indique le type de chaque photo, dans l'ordre. Il sert au mouvement de caméra demandé à Kling et à
l'affichage du script. Les photos doivent être dans l'ordre de la narration : accroche (extérieur), un point fort
par photo, capacité, prix, appel à l'action. Il faut donc idéalement 6 à 8 photos ; s'il en manque, elles sont
réutilisées.

## 3. Utilisation

```bash
# 1. Script seul, à relire (output/<slug>/script.json)
python generate.py --input input/ --output output/ --only chalet-le-pic-de-bure --script-only

# 2. Corrigez script.json si besoin, puis validez et testez sans Kling (plans fixes)
python generate.py --only chalet-le-pic-de-bure --approve-script --dry-run

# 3. Test complet sans crédit avec effet Ken Burns
python generate.py --only chalet-le-pic-de-bure --dry-run --fallback-kenburns

# 4. Vraie génération : prépare kling_jobs.json et affiche le budget, puis s'arrête
python generate.py --only chalet-le-pic-de-bure
#    → Claude génère les clips via le MCP Kling après votre « ok », puis :
python generate.py --only chalet-le-pic-de-bure --resume
```

| Option | Effet |
|---|---|
| `--only NOM` | traite un seul dossier |
| `--lang fr\|en` | langue du script et de la voix |
| `--voice NOM` | voix TTS (prioritaire sur info.yaml et config.yaml) |
| `--engine edge\|piper\|espeak` | moteur TTS (défaut : `config.yaml`) |
| `--script-only` | génère et affiche le script, sans rien d'autre |
| `--approve-script` | valide le script et continue (sinon une question est posée) |
| `--regen-script` | régénère `script.json` (écrase vos corrections) |
| `--dry-run` | aucun appel Kling : voix, sous-titres et montage avec plans fixes |
| `--fallback-kenburns` | Ken Burns local pour les clips Kling manquants ou en échec |
| `--resume` | reprend avec la voix et les clips déjà en cache |
| `--no-subs` | sans sous-titres karaoké (titres intro/outro conservés) |
| `--no-music` | voix seule |
| `--music-dir DOSSIER` | autre dossier de musiques |

Sorties, dans `output/<slug>/` :

| Fichier | Contenu |
|---|---|
| `<slug>_fr.mp4` | la vidéo |
| `<slug>_fr.srt` | sous-titres pour les plateformes |
| `script.json` | le script |
| `kling_jobs.json` | les jobs Kling et le budget |
| `<slug>_fr_controle.json` | rapport de contrôle |
| `work/` | fichiers intermédiaires (voix, `timings.json`, `subs.ass`) |

Codes de sortie :

| Code | Signification |
|---|---|
| 0 | OK |
| 2 | erreur |
| 3 | des clips Kling restent à générer |

## 4. Voix off

- **edge-tts** (par défaut) : gratuit, sans clé, voix neurales, horodatage exact de chaque mot. Il faut une
  connexion Internet. Liste des voix : `edge-tts --list-voices | grep fr-FR`. Voix françaises conseillées :
  `fr-FR-DeniseNeural` (chaleureuse), `fr-FR-HenriNeural` (masculine), `fr-FR-VivienneMultilingualNeural`.
  La vitesse se règle avec `tts.rate` (ex. `"-5%"`).
- **Piper** (100 % hors ligne) : `pip install piper-tts`. Téléchargez un modèle (par exemple
  `fr_FR-siwis-medium.onnx` et son `.json`) depuis https://huggingface.co/rhasspy/piper-voices dans
  `models/piper/`, puis réglez `tts.engine: piper`.
- **espeak-ng** : voix robotique, uniquement pour tester le rythme et la synchronisation.

Si le moteur ne fournit pas l'horodatage des mots (Piper, espeak), l'outil aligne avec **faster-whisper**
(`pip install faster-whisper`, modèle `small`, local). Sans lui, il estime les temps à partir de la longueur des
mots et affiche un avertissement.

La voix est normalisée à -16 LUFS, avec 0,15 s de silence entre les phrases. Aucun clonage de voix.

## 5. Kling AI (connecteur MCP)

Le connecteur MCP Kling est relié à **Claude**, pas à Python : `generate.py` prépare tout, et c'est Claude qui
appelle Kling. Déroulé :

1. `generate.py` prépare les images : recadrage en 9:16, moins de 4K, 30 Mo maximum (`cache/prepared/`). Il calcule
   la durée de chaque clip (durée de la phrase arrondie au supérieur, parmi les durées autorisées), écrit
   `kling_jobs.json` et affiche le **budget**.
2. Claude appelle `who_am_i` et `query_membership_and_credits` pour vérifier les modèles, les paramètres et les
   crédits. Il renseigne ensuite `kling.model`, `allowed_durations` et `credits_per_clip` dans `config.yaml` :
   rien n'est inventé.
3. **Après votre « ok »** sur le budget, Claude enchaîne :
   1. `file_upload`, puis `python kling_cache.py upload KEY --upload-url … --ticket …` ;
   2. `image_to_video` ;
   3. `query_tasks` toutes les 10 à 15 s ;
   4. `python kling_cache.py download KEY URL` dès qu'un clip est prêt (les URL expirent au bout de 24 h).
4. `python generate.py --only … --resume` fait le montage avec les clips en cache.

Pour connecter le MCP Kling : dans Claude (claude.ai ou Claude Code), Paramètres → Connecteurs → Kling, puis
connectez votre compte Kling (OAuth). Si l'outil `who_am_i` ne répond pas, le connecteur n'est pas connecté.

### Gestion des crédits

- Rien n'est soumis sans récapitulatif (nombre de clips, modèle, durées, crédits estimés) et sans votre « ok ».
- Aucun job d'essai, aucun retry automatique : en cas d'échec, l'erreur est expliquée et la décision vous revient
  (relancer, changer de paramètre ou utiliser `--fallback-kenburns`).
- `cache/manifest.json` associe chaque image à son `generationId` et à son clip local. La clé combine l'empreinte
  de l'image, la durée, le modèle et le prompt : un clip déjà payé n'est jamais regénéré.
- `python kling_cache.py status output/<slug>/kling_jobs.json` affiche l'état.

Ajustement d'un clip à sa place dans la vidéo :

- clip trop long : il est coupé ;
- clip un peu court : il est ralenti, jusqu'à x0,8 au maximum ;
- clip encore plus court : la dernière image est figée avec un zoom lent.

## 6. Montage et style

- Chaque photo reste à l'écran pendant sa phrase. Les fondus enchaînés de 0,4 s sont centrés sur les silences
  entre les phrases. La voix est une piste continue : aucune transition ne la coupe, ce que le rapport de
  contrôle vérifie.
- Intro : nom de l'hébergement et secteur, qui glissent avec un fondu. Outro : carte avec le type, le nom, la
  capacité, le prix indicatif et le bouton d'appel à l'action.
- Sous-titres :
  - 2 à 4 mots à la fois, au maximum 2 lignes, dans le tiers inférieur ;
  - marges de sécurité de 150 px en haut et 250 px en bas ;
  - Montserrat ExtraBold 76 px, avec contour et ombre ;
  - fondu d'apparition de 80 ms et zoom de 100 à 115 % en 120 ms sur le mot prononcé ;
  - mots clés (nom, points forts, prix) en couleur d'accent.
- Palette par saison (hiver : blancs et bleus glacier ; été : verts et ocres), modifiable dans `config.yaml`.
- Musique : déposez des fichiers libres de droits dans `assets/music/hiver/` et `assets/music/ete/`. Elle est
  ramenée à -26 LUFS, atténuée sous la voix (`sidechaincompress`) et ouverte et fermée par un fondu. Sans
  musique : voix seule.

Tous les réglages se trouvent dans `config.yaml` : voix, vitesse, styles, couleurs, marges, durées, loudness,
timeouts et prompts de mouvement.

## 7. Exemple sans crédit

```bash
python examples/make_example.py      # images synthétiques + nappe musicale de test
python generate.py --input examples/input --output output --music-dir examples/music \
    --dry-run --fallback-kenburns --approve-script
```

## 8. Tests

```bash
python -m pytest -q
```

Tous les tests tournent sans réseau ni crédit. Ils couvrent la lecture du yaml, le découpage et la véracité du
script, le calcul des durées et de la ligne de temps, l'alignement, la génération ASS et SRT, et le manifest.

## Véracité

Le script n'utilise que les champs d'`info.yaml`. Un contrôle automatique signale tout équipement (piscine, vue,
parking, etc.) ou chiffre (distance, minutes) présent dans le script mais absent du yaml, y compris dans un
`script_manuel`.
