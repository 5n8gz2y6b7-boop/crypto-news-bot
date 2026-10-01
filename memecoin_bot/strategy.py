"""
Logique quant pure (sans réseau) : filtres, score momentum/flux, décisions d'entrée et de sortie.
Testable unitairement (tests/test_strategy.py).
"""
import math
import time


def _n(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def features(pair, now=None):
    now = now or time.time()
    tx = pair.get("txns") or {}
    vol = pair.get("volume") or {}
    chg = pair.get("priceChange") or {}
    b5, s5 = _n((tx.get("m5") or {}).get("buys")), _n((tx.get("m5") or {}).get("sells"))
    b1, s1 = _n((tx.get("h1") or {}).get("buys")), _n((tx.get("h1") or {}).get("sells"))
    created = _n(pair.get("pairCreatedAt")) / 1000
    return {
        "liq": _n((pair.get("liquidity") or {}).get("usd")),
        "mcap": _n(pair.get("marketCap") or pair.get("fdv")),
        "age_min": (now - created) / 60 if created else 0,
        "chg_m5": _n(chg.get("m5")),
        "chg_h1": _n(chg.get("h1")),
        "chg_h6": _n(chg.get("h6")),
        "txns_h1": b1 + s1,
        "buy_ratio_m5": b5 / (b5 + s5) if b5 + s5 else 0.5,
        "buy_ratio_h1": b1 / (b1 + s1) if b1 + s1 else 0.5,
        # volume des 5 dernières min annualisé à l'heure / volume 1 h : >1 = accélération
        "vol_accel": (_n(vol.get("m5")) * 12) / _n(vol.get("h1")) if _n(vol.get("h1")) else 0,
        "vol_liq": _n(vol.get("h1")) / _n((pair.get("liquidity") or {}).get("usd")) if _n((pair.get("liquidity") or {}).get("usd")) else 0,
    }


def passes_filters(f, cfg):
    """Retourne (ok, raison)."""
    if f["liq"] < cfg.min_liquidity_usd:
        return False, "liquidité faible"
    if not (cfg.min_mcap_usd <= f["mcap"] <= cfg.max_mcap_usd):
        return False, "mcap hors plage"
    if f["age_min"] < cfg.min_age_minutes:
        return False, "trop récent"
    if f["age_min"] > cfg.max_age_hours * 60:
        return False, "trop ancien"
    if f["txns_h1"] < cfg.min_txns_h1:
        return False, "peu de transactions"
    if f["chg_h1"] > cfg.max_h1_change_pct:
        return False, "déjà trop pompé"
    return True, ""


def _sig(x):
    return 1 / (1 + math.exp(-x))


def score(f):
    """Score 0..1 combinant momentum, pression acheteuse, accélération de volume et rotation."""
    momentum = _sig(f["chg_m5"] / 5) * 0.6 + _sig(f["chg_h1"] / 30) * 0.4
    pressure = _sig((f["buy_ratio_m5"] - 0.5) * 12) * 0.6 + _sig((f["buy_ratio_h1"] - 0.5) * 12) * 0.4
    accel = _sig((f["vol_accel"] - 1) * 2)
    turnover = _sig((f["vol_liq"] - 0.5) * 2)
    return round(0.35 * momentum + 0.30 * pressure + 0.20 * accel + 0.15 * turnover, 4)


def entry_signal(f, cfg):
    ok, why = passes_filters(f, cfg)
    if not ok:
        return False, why, 0.0
    s = score(f)
    if f["chg_m5"] <= 0:
        return False, "momentum 5 min négatif", s
    if f["buy_ratio_m5"] < 0.55:
        return False, "pas assez d'acheteurs", s
    if s < cfg.min_score:
        return False, f"score {s:.2f} < {cfg.min_score}", s
    return True, f"score {s:.2f}", s


def exit_signal(pos, value_sol, cfg, now=None):
    """
    pos : dict avec cost_sol, peak_sol, opened_at. Met à jour peak_sol.
    Retourne (vendre?, raison).
    """
    now = now or time.time()
    pos["peak_sol"] = max(pos.get("peak_sol", pos["cost_sol"]), value_sol)
    pnl = (value_sol / pos["cost_sol"] - 1) * 100
    peak_pnl = (pos["peak_sol"] / pos["cost_sol"] - 1) * 100
    drawdown = (1 - value_sol / pos["peak_sol"]) * 100 if pos["peak_sol"] else 0
    if pnl <= -cfg.stop_loss_pct:
        return True, f"stop-loss {pnl:+.1f}%"
    if pnl >= cfg.take_profit_pct:
        return True, f"take-profit {pnl:+.1f}%"
    if peak_pnl >= cfg.trailing_activate_pct and drawdown >= cfg.trailing_stop_pct:
        return True, f"trailing stop (pic {peak_pnl:+.1f}%, actuel {pnl:+.1f}%)"
    if (now - pos["opened_at"]) / 60 >= cfg.max_hold_minutes:
        return True, f"durée max atteinte ({pnl:+.1f}%)"
    return False, f"{pnl:+.1f}%"
