"""Client JSON-RPC Solana minimal (pas de dépendance solana-py)."""
import time

import requests


class SolanaRPC:
    def __init__(self, url):
        self.url = url

    def call(self, method, params=None):
        r = requests.post(self.url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []},
                          timeout=20)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"RPC {method}: {data['error']}")
        return data["result"]

    def sol_balance(self, pubkey):
        return self.call("getBalance", [pubkey, {"commitment": "confirmed"}])["value"]

    def token_balance(self, owner, mint):
        """Solde brut (unités minimales) du token pour ce wallet, SPL et Token-2022."""
        total = 0
        for program in ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"):
            res = self.call("getTokenAccountsByOwner",
                            [owner, {"programId": program}, {"encoding": "jsonParsed", "commitment": "confirmed"}])
            for acc in res["value"]:
                info = acc["account"]["data"]["parsed"]["info"]
                if info["mint"] == mint:
                    total += int(info["tokenAmount"]["amount"])
        return total

    def mint_info(self, mint):
        res = self.call("getAccountInfo", [mint, {"encoding": "jsonParsed"}])["value"]
        if not res:
            return None
        return res["data"]["parsed"]["info"]

    def send_raw(self, tx_b64):
        return self.call("sendTransaction", [tx_b64, {"encoding": "base64", "skipPreflight": True, "maxRetries": 3}])

    def confirm(self, sig, timeout=60):
        """Attend la confirmation. Lève une erreur si la transaction a échoué on-chain."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = self.call("getSignatureStatuses", [[sig], {"searchTransactionHistory": False}])["value"][0]
            if st:
                if st.get("err"):
                    raise RuntimeError(f"transaction {sig} échouée: {st['err']}")
                if st.get("confirmationStatus") in ("confirmed", "finalized"):
                    return True
            time.sleep(2)
        raise TimeoutError(f"transaction {sig} non confirmée après {timeout}s")
