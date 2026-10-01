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

## Installation
```bash
pip install -r requirements-memecoin.txt
cp .env.example .env        # puis édite les valeurs
set -a; source .env; set +a
python -m memecoin_bot.main            # boucle continue
```
Commandes : `--once` (un cycle), `--status` (positions + PnL), `--sell-all` (vend tout).
Créer un fichier `STOP` dans le dossier courant bloque toute nouvelle entrée (les sorties continuent).

## Brancher Phantom
1. Dans Phantom : **Ajouter / connecter un compte → Créer un nouveau compte** (wallet dédié au bot).
2. Envoie-lui un petit montant de SOL.
3. **Paramètres → Gérer les comptes → [ce compte] → Afficher la clé privée** → copie-la.
4. Mets-la dans `PHANTOM_PRIVATE_KEY` du fichier `.env` (jamais dans le code, jamais sur GitHub).
5. Les achats/ventes du bot apparaissent directement dans Phantom.

## Passer en réel
1. Laisse tourner en papier au moins quelques jours et regarde `--status` / l'historique dans `memecoin_state.json`.
2. Prends un RPC privé (Helius, QuickNode… le RPC public limite et rate des transactions).
3. `DRY_RUN=0`, garde `POSITION_SOL` petit.

Hébergement : un VPS ou un PC allumé 24/7. **Pas GitHub Actions** — les cycles de 5 min sont trop lents
pour gérer les stops, et une clé privée n'a rien à faire sur un runner partagé.

## Tests
```bash
python -m pytest tests
```
