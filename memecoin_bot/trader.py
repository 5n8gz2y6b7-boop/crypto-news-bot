"""Exécution des ordres : mode papier (DRY_RUN, simulé avec les vraies cotations Jupiter) ou réel (Phantom)."""
import time

from .config import LAMPORTS, SOL_MINT


class Trader:
    def __init__(self, cfg, rpc, jup, state, wallet=None):
        self.cfg, self.rpc, self.jup, self.state, self.wallet = cfg, rpc, jup, state, wallet
        if not cfg.dry_run and wallet is None:
            raise ValueError("wallet requis en mode réel")

    # ------------------------------------------------------------ soldes
    def sol_available(self):
        if self.cfg.dry_run:
            return self.state.d["paper_sol"]
        return self.rpc.sol_balance(self.wallet.pubkey) / LAMPORTS

    def value_sol(self, pos):
        q = self.jup.quote(pos["mint"], SOL_MINT, pos["tokens"])
        return int(q["outAmount"]) / LAMPORTS if q else None

    # ------------------------------------------------------------ swap réel
    def _execute(self, quote):
        before = self.rpc.sol_balance(self.wallet.pubkey)
        tx = self.wallet.sign_b64(self.jup.swap_tx(quote, self.wallet.pubkey))
        sig = self.rpc.send_raw(tx)
        self.rpc.confirm(sig)
        after = self.rpc.sol_balance(self.wallet.pubkey)
        return sig, (after - before) / LAMPORTS  # variation SOL réelle, frais inclus

    # ------------------------------------------------------------ ordres
    def buy(self, mint, symbol, quote, score):
        lamports = int(self.cfg.position_sol * LAMPORTS)
        if self.cfg.dry_run:
            tokens, cost, sig = int(quote["outAmount"]), self.cfg.position_sol, "papier"
            self.state.d["paper_sol"] -= cost
        else:
            quote = self.jup.quote(SOL_MINT, mint, lamports) or quote  # cotation fraîche
            sig, delta = self._execute(quote)
            cost = -delta
            tokens = self.rpc.token_balance(self.wallet.pubkey, mint)
            if tokens <= 0:
                raise RuntimeError("achat confirmé mais solde token nul")
        pos = {"mint": mint, "symbol": symbol, "tokens": tokens, "cost_sol": cost,
               "peak_sol": cost, "opened_at": time.time(), "score": score, "buy_sig": sig}
        self.state.positions[mint] = pos
        self.state.set_cooldown(mint)
        self.state.save()
        return pos

    def sell(self, pos, reason):
        slippage = min(self.cfg.slippage_bps * 3, 1500)  # sortie prioritaire : on tolère plus de glissement
        if self.cfg.dry_run:
            q = self.jup.quote(pos["mint"], SOL_MINT, pos["tokens"], slippage)
            if not q:
                raise RuntimeError("aucune route de vente")
            proceeds, sig = int(q["outAmount"]) / LAMPORTS, "papier"
            self.state.d["paper_sol"] += proceeds
        else:
            amount = self.rpc.token_balance(self.wallet.pubkey, pos["mint"]) or pos["tokens"]
            q = self.jup.quote(pos["mint"], SOL_MINT, amount, slippage)
            if not q:
                raise RuntimeError("aucune route de vente")
            sig, proceeds = self._execute(q)
        pnl = proceeds - pos["cost_sol"]
        self.state.add_pnl(pnl)
        self.state.d["history"].append({**pos, "closed_at": time.time(), "proceeds_sol": proceeds,
                                        "pnl_sol": pnl, "reason": reason, "sell_sig": sig})
        del self.state.positions[pos["mint"]]
        self.state.save()
        return proceeds, pnl, sig
