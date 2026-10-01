"""
Wallet Phantom : on utilise la clé privée exportée depuis Phantom
(Paramètres → Gérer les comptes → [compte] → Afficher la clé privée, format base58).
Utilise un wallet DÉDIÉ au bot, jamais ton wallet principal.
"""
import base64

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction


class PhantomWallet:
    def __init__(self, private_key_b58):
        if not private_key_b58:
            raise ValueError("PHANTOM_PRIVATE_KEY manquante")
        self.keypair = Keypair.from_base58_string(private_key_b58.strip())

    @property
    def pubkey(self):
        return str(self.keypair.pubkey())

    def sign_b64(self, tx_b64):
        """Signe une transaction versionnée (base64, renvoyée par Jupiter) et la renvoie en base64."""
        tx = VersionedTransaction.from_bytes(base64.b64decode(tx_b64))
        signed = VersionedTransaction(tx.message, [self.keypair])
        return base64.b64encode(bytes(signed)).decode()
