"""
Wallet Phantom : on utilise la clé privée exportée depuis Phantom
(Paramètres → Gérer les comptes → [compte] → Afficher la clé privée, format base58).
Utilise un wallet DÉDIÉ au bot, jamais ton wallet principal.
"""
import base64
import json

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction


def parse_private_key(raw):
    """Clé Phantom (base58) ou tableau JSON de 64 octets (format Solana CLI) -> Keypair."""
    raw = (raw or "").strip().strip('"').strip("'")
    if not raw:
        raise ValueError("PHANTOM_PRIVATE_KEY manquante (lance : python -m memecoin_bot.connect)")
    if not raw.startswith("[") and len(raw.split()) >= 12:
        raise ValueError("ceci ressemble à une phrase de récupération : ne la donne jamais au bot. "
                         "Utilise « Afficher la clé privée » dans Phantom.")
    try:
        if raw.startswith("["):
            return Keypair.from_bytes(bytes(json.loads(raw)))
        return Keypair.from_base58_string(raw)
    except Exception:
        raise ValueError("clé privée invalide : copie la clé privée exportée depuis Phantom "
                         "(pas l'adresse publique, pas la phrase de récupération)") from None


class PhantomWallet:
    def __init__(self, private_key_b58):
        self.keypair = parse_private_key(private_key_b58)

    @property
    def pubkey(self):
        return str(self.keypair.pubkey())

    def sign_b64(self, tx_b64):
        """Signe une transaction versionnée (base64, renvoyée par Jupiter) et la renvoie en base64."""
        tx = VersionedTransaction.from_bytes(base64.b64decode(tx_b64))
        signed = VersionedTransaction(tx.message, [self.keypair])
        return base64.b64encode(bytes(signed)).decode()
