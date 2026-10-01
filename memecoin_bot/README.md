# Bot quant memecoins Solana (wallet Phantom)

Scanne les memecoins Solana tendance, filtre les arnaques, achète ceux qui ont le meilleur
signal momentum/flux, puis gère la sortie automatiquement (take-profit, stop-loss, trailing stop,
durée max). Les swaps passent par **Jupiter** et sont signés avec la clé de ton **wallet Phantom**.
Notifications Telegram (mêmes secrets que le bot de news).

> ⚠️ Les memecoins sont extrêmement risqués : la plupart vont à zéro. Le bot démarre en
> **mode papier** (`DRY_RUN=1`, aucune transaction). Ne mets que ce que tu acceptes de perdre,
> sur un wallet dédié. Ce code n'est pas un conseil financier.

## Fonctionnement
| Étape | Détail |
|---|---|
| 1. Univers | Tokens Solana boostés / profilés récemment sur DexScreener, paire la plus liquide |
| 2. Filtres | liquidité, market cap, âge de la paire, nb de transactions 1 h, pas déjà « pompé » |
| 3. Score (0-1) | momentum 5 min / 1 h · ratio acheteurs/vendeurs · accélération du volume · rotation volume/liquidité |
| 4. Anti-rug | mint & freeze authority révoquées · RugCheck sans risque « danger » · impact de prix · **test aller-retour Jupiter** (détecte honeypots et taxes) |
| 5. Exécution | quote Jupiter → transaction signée avec la clé Phantom → envoi RPC → confirmation, coût réel mesuré |
| 6. Sorties | TP +60 %, SL −20 %, trailing −15 % depuis le pic (activé à +25 %), 4 h max |
| 7. Risque | 0,05 SOL/trade, 3 positions max, réserve SOL pour les frais, limite de perte journalière, cooldown par token |

## Démarrage rapide (3 étapes)

**1. Prépare Phantom** (2 min)
- Phantom → icône du compte → **Ajouter / connecter un compte → Créer un nouveau compte** (wallet dédié au bot).
- Envoie-lui le SOL que tu acceptes de risquer (ex. 0,3 SOL).
- **Paramètres → Gérer les comptes → [ce compte] → Afficher la clé privée** → copie-la.
  (Jamais la phrase de récupération : le bot la refuse.)

**2. Télécharge le bot** : *Code → Download ZIP* sur GitHub (branche du bot), puis dézippe.
Il faut [Python 3.10+](https://www.python.org/downloads/) (sous Windows, coche « Add Python to PATH »).

**3. Lance-le**
- **Windows** : double-clique `start.bat`
- **Mac / Linux** : `./start.sh` dans un terminal

Au premier lancement, tout s'installe tout seul puis l'assistant te demande la clé privée
(saisie masquée), affiche l'adresse du wallet pour que tu vérifies qu'elle correspond à Phantom,
puis la mise, le mode (papier / réel) et Telegram. Il écrit un fichier `.env` local
(permissions 600, ignoré par git). Ensuite le bot vérifie tout (`--check`) et démarre.
Ses achats/ventes apparaissent directement dans Phantom.

| Commande (Windows : `start.bat …`) | Effet |
|---|---|
| `./start.sh` | vérifie puis lance le bot (Ctrl+C pour l'arrêter, les positions restent suivies) |
| `./start.sh --check` | teste clé, solde, RPC, Jupiter, DexScreener sans trader |
| `./start.sh --status` | positions ouvertes + PnL du jour |
| `./start.sh --sell-all` | vend toutes les positions (bouton panique) |
| `./start.sh --connect` | reconfigure (changer de wallet, de mise, passer en réel…) |

Un fichier `STOP` dans le dossier bloque toute nouvelle entrée (les sorties continuent).

Sans les lanceurs : `pip install -r requirements-memecoin.txt`, `python -m memecoin_bot.connect`,
puis `python -m memecoin_bot.main` (le `.env` est chargé automatiquement).

## Passer en réel
1. Laisse tourner en papier au moins quelques jours et regarde `--status` / l'historique dans `memecoin_state.json`.
2. Prends un RPC privé gratuit (helius.dev, quicknode.com) : le RPC public limite et rate des transactions.
3. `./start.sh --connect` → réponds « o » au mode réel et tape `REEL`. Garde une petite mise.

Sécurité : la clé ne quitte jamais ta machine (elle sert seulement à signer localement les swaps Jupiter).
Ne mets jamais `.env` sur GitHub ni dans un message ; si tu penses qu'elle a fuité, vide ce compte Phantom.

Hébergement : un VPS ou un PC allumé 24/7. **Pas GitHub Actions** — les cycles de 5 min sont trop lents
pour gérer les stops, et une clé privée n'a rien à faire sur un runner partagé.

## Tests
```bash
python -m pytest tests
```
