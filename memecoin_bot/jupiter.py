"""Exécution des swaps via l'agrégateur Jupiter (meilleur prix sur Raydium, Orca, Meteora, Pump.fun…)."""
import requests


class Jupiter:
    def __init__(self, cfg):
        self.base = cfg.jup_base.rstrip("/")
        self.cfg = cfg
        self.headers = {"x-api-key": cfg.jup_api_key} if cfg.jup_api_key else {}

    def quote(self, input_mint, output_mint, amount, slippage_bps=None):
        r = requests.get(f"{self.base}/quote", headers=self.headers, timeout=15, params={
            "inputMint": input_mint, "outputMint": output_mint, "amount": int(amount),
            "slippageBps": slippage_bps or self.cfg.slippage_bps, "restrictIntermediateTokens": "true"})
        if r.status_code == 400:
            return None  # pas de route (token non échangeable)
        r.raise_for_status()
        q = r.json()
        return q if q.get("outAmount") else None

    def swap_tx(self, quote, user_pubkey):
        r = requests.post(f"{self.base}/swap", headers=self.headers, timeout=20, json={
            "quoteResponse": quote,
            "userPublicKey": user_pubkey,
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True,
            "dynamicSlippage": True,
            "prioritizationFeeLamports": {"priorityLevelWithMaxLamports": {
                "maxLamports": self.cfg.priority_fee_lamports, "priorityLevel": "veryHigh"}},
        })
        r.raise_for_status()
        return r.json()["swapTransaction"]
