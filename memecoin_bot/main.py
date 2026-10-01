#!/usr/bin/env python3
"""
Bot quant memecoins Solana -> exécution sur le wallet Phantom via Jupiter.

  python -m memecoin_bot.main            boucle continue (VPS / PC)
  python -m memecoin_bot.main --once     un seul cycle
  python -m memecoin_bot.main --status   positions + PnL
  python -m memecoin_bot.main --sell-all vend toutes les positions (bouton panique)

Fichier STOP dans le dossier courant -> plus aucune nouvelle entrée (les sorties continuent).
"""
import os
import sys
import time

from . import dexscreener, safety, strategy
from .config import Config
from .jupiter import Jupiter
from .notifier import Notifier
from .solana_rpc import SolanaRPC
from .state import State
from .trader import Trader


def build():
    cfg = Config()
    rpc, jup = SolanaRPC(cfg.rpc_url), Jupiter(cfg)
    state = State(cfg.state_file, cfg.paper_balance_sol)
    wallet = None
    if not cfg.dry_run:
        from .wallet import PhantomWallet
        wallet = PhantomWallet(cfg.phantom_private_key)
    return cfg, rpc, jup, state, Trader(cfg, rpc, jup, state, wallet), Notifier(cfg.telegram_token, cfg.telegram_chat_id)


def manage_exits(cfg, trader, notify, force_reason=None):
    for mint, pos in list(trader.state.positions.items()):
        try:
            value = trader.value_sol(pos)
            if value is None and not force_reason:
                print(f"  {pos['symbol']}: pas de cotation, on réessaie au prochain cycle")
                continue
            sell, why = (True, force_reason) if force_reason else strategy.exit_signal(pos, value, cfg)
            if not sell:
                print(f"  {pos['symbol']}: {why} ({value:.4f} SOL)")
                continue
            proceeds, pnl, sig = trader.sell(pos, why)
            notify.send(f"{'🟢' if pnl >= 0 else '🔴'} <b>VENTE {pos['symbol']}</b> — {why}\n"
                        f"Reçu {proceeds:.4f} SOL · PnL {pnl:+.4f} SOL\n{_tx(sig)}")
        except Exception as ex:
            notify.send(f"⚠️ Vente {pos['symbol']} échouée : {ex}")
    trader.state.save()


def find_entries(cfg, trader, rpc, jup, notify):
    st = trader.state
    if os.path.exists("STOP"):
        print("  fichier STOP présent : pas de nouvelles entrées")
        return
    if st.daily_pnl() <= -cfg.daily_loss_limit_sol:
        print(f"  limite de perte journalière atteinte ({st.daily_pnl():+.4f} SOL)")
        return
    slots = cfg.max_positions - len(st.positions)
    if slots <= 0:
        return

    pairs = dexscreener.best_pairs(dexscreener.candidate_mints())
    ranked = []
    for mint, pair in pairs.items():
        if mint in st.positions or st.in_cooldown(mint, cfg.token_cooldown_hours):
            continue
        ok, why, s = strategy.entry_signal(strategy.features(pair), cfg)
        if ok:
            ranked.append((s, mint, pair))
    ranked.sort(reverse=True, key=lambda x: x[0])
    print(f"  {len(pairs)} tokens scannés, {len(ranked)} signaux")

    for s, mint, pair in ranked:
        if slots <= 0:
            break
        if trader.sol_available() - cfg.position_sol < cfg.sol_reserve:
            print("  solde SOL insuffisant")
            return
        sym = (pair.get("baseToken") or {}).get("symbol", mint[:6])
        ok, why, quote = safety.check_token(mint, cfg, rpc, jup)
        if not ok:
            print(f"  ✗ {sym}: {why}")
            st.set_cooldown(mint)
            continue
        try:
            pos = trader.buy(mint, sym, quote, s)
        except Exception as ex:
            notify.send(f"⚠️ Achat {sym} échoué : {ex}")
            st.set_cooldown(mint)
            continue
        slots -= 1
        f = strategy.features(pair)
        notify.send(f"🛒 <b>ACHAT {sym}</b> {'(papier)' if cfg.dry_run else ''}\n"
                    f"{pos['cost_sol']:.4f} SOL · score {s:.2f} · {why}\n"
                    f"Liq ${f['liq']:,.0f} · MC ${f['mcap']:,.0f} · 5m {f['chg_m5']:+.1f}% · 1h {f['chg_h1']:+.1f}%\n"
                    f"https://dexscreener.com/solana/{mint}\n{_tx(pos['buy_sig'])}")
    st.save()


def _tx(sig):
    return "" if sig == "papier" else f"https://solscan.io/tx/{sig}"


def status(cfg, trader):
    st = trader.state
    print(f"Mode : {'PAPIER' if cfg.dry_run else 'RÉEL'} · SOL dispo : {trader.sol_available():.4f}")
    print(f"PnL du jour : {st.daily_pnl():+.4f} SOL · trades clos : {len(st.d['history'])}")
    for p in st.positions.values():
        v = trader.value_sol(p)
        print(f"  {p['symbol']:<10} coût {p['cost_sol']:.4f} · valeur {v if v is None else round(v, 4)}")


def cycle(cfg, rpc, jup, trader, notify):
    manage_exits(cfg, trader, notify)
    find_entries(cfg, trader, rpc, jup, notify)


def main():
    cfg, rpc, jup, state, trader, notify = build()
    if "--status" in sys.argv:
        return status(cfg, trader)
    if "--sell-all" in sys.argv:
        return manage_exits(cfg, trader, notify, force_reason="vente manuelle (--sell-all)")
    if "--once" in sys.argv:
        return cycle(cfg, rpc, jup, trader, notify)
    who = "papier" if cfg.dry_run else trader.wallet.pubkey
    notify.send(f"🤖 Bot memecoins démarré ({who}) · {cfg.position_sol} SOL/trade · max {cfg.max_positions} positions")
    while True:
        try:
            cycle(cfg, rpc, jup, trader, notify)
        except Exception as ex:
            print("Erreur cycle:", ex)
        time.sleep(cfg.scan_interval)


if __name__ == "__main__":
    main()
