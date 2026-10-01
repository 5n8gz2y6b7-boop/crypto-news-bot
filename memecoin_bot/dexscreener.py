"""Scanner de marché : tokens Solana tendance via l'API publique DexScreener."""
import requests

BASE = "https://api.dexscreener.com"
UA = {"User-Agent": "Mozilla/5.0 (MemecoinQuantBot)"}


def _get(path):
    r = requests.get(BASE + path, headers=UA, timeout=15)
    r.raise_for_status()
    return r.json()


def candidate_mints():
    """Mints Solana récemment boostés / profilés (là où l'attention arrive)."""
    mints = []
    for path in ("/token-boosts/latest/v1", "/token-boosts/top/v1", "/token-profiles/latest/v1"):
        try:
            data = _get(path)
        except Exception as ex:
            print(f"! DexScreener {path}: {ex}")
            continue
        for t in data if isinstance(data, list) else []:
            if t.get("chainId") == "solana" and t.get("tokenAddress") and t["tokenAddress"] not in mints:
                mints.append(t["tokenAddress"])
    return mints


def best_pairs(mints):
    """Pour chaque mint, la paire SOL/USDC la plus liquide. Retourne {mint: pair}."""
    out = {}
    for i in range(0, len(mints), 30):
        chunk = ",".join(mints[i:i + 30])
        try:
            pairs = _get(f"/tokens/v1/solana/{chunk}")
        except Exception as ex:
            print(f"! DexScreener pairs: {ex}")
            continue
        for p in pairs if isinstance(pairs, list) else []:
            mint = (p.get("baseToken") or {}).get("address")
            if not mint or mint not in mints:
                continue
            liq = (p.get("liquidity") or {}).get("usd") or 0
            if mint not in out or liq > ((out[mint].get("liquidity") or {}).get("usd") or 0):
                out[mint] = p
    return out
