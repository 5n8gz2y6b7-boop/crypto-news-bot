"""
Contrôles anti-rug avant tout achat :
 1. Mint authority / freeze authority révoquées (sinon le dev peut imprimer ou geler tes tokens)
 2. Rapport RugCheck (risques "danger", score)
 3. Test aller-retour Jupiter : achat puis revente simulés -> détecte honeypots et taxes cachées
 4. Impact de prix acceptable pour la taille de position
"""
import requests

from .config import LAMPORTS, SOL_MINT


def rugcheck(mint):
    try:
        r = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary", timeout=15)
        return r.json() if r.ok else None
    except Exception:
        return None


def check_token(mint, cfg, rpc, jup):
    """Retourne (ok, raison, quote_achat)."""
    try:
        info = rpc.mint_info(mint)
    except Exception as ex:
        return False, f"mint illisible ({ex})", None
    if not info:
        return False, "mint introuvable", None
    if info.get("mintAuthority"):
        return False, "mint authority active", None
    if info.get("freezeAuthority"):
        return False, "freeze authority active", None

    rc = rugcheck(mint)
    if rc:
        dangers = [x.get("name") for x in rc.get("risks", []) if x.get("level") == "danger"]
        if dangers:
            return False, "RugCheck: " + ", ".join(dangers[:3]), None
        if (rc.get("score") or 0) > cfg.max_rugcheck_score:
            return False, f"RugCheck score {rc.get('score')}", None

    lamports = int(cfg.position_sol * LAMPORTS)
    buy = jup.quote(SOL_MINT, mint, lamports)
    if not buy:
        return False, "aucune route d'achat", None
    impact = float(buy.get("priceImpactPct") or 0) * 100
    if impact > cfg.max_price_impact_pct:
        return False, f"impact prix {impact:.1f}%", None
    sell = jup.quote(mint, SOL_MINT, int(buy["outAmount"]))
    if not sell:
        return False, "impossible de revendre (honeypot ?)", None
    loss = (1 - int(sell["outAmount"]) / lamports) * 100
    if loss > cfg.max_roundtrip_loss_pct:
        return False, f"perte aller-retour {loss:.1f}% (taxe/liquidité)", None
    return True, f"ok (aller-retour -{loss:.1f}%)", buy
