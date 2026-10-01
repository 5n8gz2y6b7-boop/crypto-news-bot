#!/usr/bin/env python3
"""
Assistant de connexion du wallet Phantom au bot :  python -m memecoin_bot.connect

Demande la clé privée (saisie masquée), affiche l'adresse pour vérification, choisit le mode
(papier / réel) et écrit le fichier .env (permissions 600). Rien n'est envoyé nulle part.
"""
import getpass
import os
import re

from .config import ENV_FILE, LAMPORTS, ROOT
from .wallet import parse_private_key

TEMPLATE = os.path.join(ROOT, ".env.example")
PUBLIC_RPC = "https://api.mainnet-beta.solana.com"


def read_env(path):
    vals = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.split(" #", 1)[0].strip()
    return vals


def write_env(values, path=ENV_FILE, template=TEMPLATE):
    """Recopie le modèle .env.example en remplaçant les valeurs données ; écrit avec permissions 600."""
    with open(template, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    done = set()
    out = []
    for line in lines:
        m = re.match(r"^([A-Z0-9_]+)=", line)
        if m and m.group(1) in values:
            out.append(f"{m.group(1)}={values[m.group(1)]}")
            done.add(m.group(1))
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in values.items() if k not in done]
    fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    os.replace(path + ".tmp", path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def ask(prompt, default=""):
    ans = input(f"{prompt}{f' [{default}]' if default else ''} : ").strip()
    return ans or default


def ask_num(prompt, default, cast=float):
    while True:
        ans = ask(prompt, default).replace(",", ".")
        try:
            if cast(ans) > 0:
                return ans
        except ValueError:
            pass
        print("  ✗ nombre positif attendu")


def yes(prompt, default=False):
    ans = input(f"{prompt} ({'O/n' if default else 'o/N'}) : ").strip().lower()
    return default if not ans else ans in ("o", "oui", "y", "yes")


def balance(rpc_url, pubkey):
    try:
        from .solana_rpc import SolanaRPC
        return SolanaRPC(rpc_url).sol_balance(pubkey) / LAMPORTS
    except Exception as ex:
        print(f"  (solde illisible pour l'instant : {ex})")
        return None


def main():
    cur = read_env(ENV_FILE)
    print("=== Connexion de ton wallet Phantom au bot ===\n")
    print("Utilise un compte Phantom DÉDIÉ au bot, avec seulement ce que tu acceptes de perdre.")
    print("Phantom → icône du compte → Ajouter/connecter un compte → Créer un nouveau compte,")
    print("puis Paramètres → Gérer les comptes → [ce compte] → Afficher la clé privée → Copier.\n")

    while True:
        hint = " (Entrée = garder la clé actuelle)" if cur.get("PHANTOM_PRIVATE_KEY") else ""
        raw = getpass.getpass(f"Colle la clé privée Phantom (saisie masquée){hint} : ").strip()
        raw = raw or cur.get("PHANTOM_PRIVATE_KEY", "")
        try:
            kp = parse_private_key(raw)
        except ValueError as ex:
            print(f"  ✗ {ex}\n")
            continue
        pub = str(kp.pubkey())
        print(f"\n  Adresse du wallet : {pub}")
        if yes("  C'est bien l'adresse affichée dans Phantom pour ce compte ?", True):
            break

    print("\nRPC Solana : le public marche pour tester, mais un RPC privé gratuit (helius.dev, quicknode.com)")
    print("est fortement conseillé en réel (le public limite et rate des transactions).")
    rpc = ask("URL du RPC", cur.get("SOLANA_RPC_URL") or PUBLIC_RPC)

    sol = balance(rpc, pub)
    if sol is not None:
        print(f"  Solde : {sol:.4f} SOL")

    size = ask_num("\nMise par trade en SOL", cur.get("POSITION_SOL") or "0.05")
    max_pos = ask_num("Nombre max de positions simultanées", cur.get("MAX_POSITIONS") or "3", int)
    loss = ask_num("Perte max par jour en SOL (le bot arrête d'acheter au-delà)", cur.get("DAILY_LOSS_LIMIT_SOL") or "0.15")

    print("\nMode PAPIER : le bot simule avec les vrais prix, aucune transaction (recommandé pour commencer).")
    print("Mode RÉEL   : le bot achète et vend avec le SOL de ce wallet.")
    dry = "1"
    if yes("Activer le mode RÉEL maintenant ?", False):
        need = float(size) + 0.03
        if sol is not None and sol < need:
            print(f"  ⚠️ Solde {sol:.4f} SOL < {need:.3f} SOL nécessaires (mise + réserve frais). Envoie du SOL sur {pub}.")
        if input("  Tape REEL pour confirmer : ").strip().upper() in ("REEL", "RÉEL"):
            dry = "0"
        else:
            print("  → reste en mode papier.")

    tg_token = cur.get("TELEGRAM_TOKEN", "")
    tg_chat = cur.get("TELEGRAM_CHAT_ID", "")
    if yes("\nRecevoir les alertes sur Telegram ?", bool(tg_token)):
        tg_token = ask("  Token du bot Telegram (@BotFather)", tg_token)
        tg_chat = ask("  Chat ID", tg_chat)

    values = {**cur, "PHANTOM_PRIVATE_KEY": raw, "SOLANA_RPC_URL": rpc, "DRY_RUN": dry,
              "POSITION_SOL": size, "MAX_POSITIONS": max_pos, "DAILY_LOSS_LIMIT_SOL": loss,
              "TELEGRAM_TOKEN": tg_token, "TELEGRAM_CHAT_ID": tg_chat}
    write_env(values)
    print(f"\n✅ Configuration enregistrée dans {ENV_FILE} (lisible par toi seul, ignoré par git).")
    print(f"   Wallet {pub} · mode {'PAPIER' if dry == '1' else 'RÉEL'} · {size} SOL/trade")
    print("\nÉtapes suivantes :")
    print("  python -m memecoin_bot.main --check   # vérifie wallet, RPC, Jupiter, DexScreener")
    print("  python -m memecoin_bot.main           # lance le bot")


if __name__ == "__main__":
    main()
