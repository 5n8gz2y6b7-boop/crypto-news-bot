"""
Configuration par variables d'environnement (voir .env.example).
Tout est en SOL sauf mention contraire. DRY_RUN=1 par défaut : aucune transaction réelle.
"""
import os
from dataclasses import dataclass, field

SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
LAMPORTS = 1_000_000_000
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.environ.get("MEMECOIN_ENV_FILE", os.path.join(ROOT, ".env"))


def load_env(path=ENV_FILE):
    """Charge le fichier .env (sans dépendance). Les variables déjà définies dans l'environnement priment."""
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            val = val.split(" #", 1)[0].split("\t#", 1)[0].strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), val)
    return True


def _f(name, default):
    return float(os.environ.get(name, default))


def _i(name, default):
    return int(os.environ.get(name, default))


def _b(name, default):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    # --- Wallet / réseau
    phantom_private_key: str = field(default_factory=lambda: os.environ.get("PHANTOM_PRIVATE_KEY", ""))
    rpc_url: str = field(default_factory=lambda: os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"))
    jup_base: str = field(default_factory=lambda: os.environ.get("JUPITER_API", "https://lite-api.jup.ag/swap/v1"))
    jup_api_key: str = field(default_factory=lambda: os.environ.get("JUPITER_API_KEY", ""))
    dry_run: bool = field(default_factory=lambda: _b("DRY_RUN", "1"))
    priority_fee_lamports: int = field(default_factory=lambda: _i("PRIORITY_FEE_LAMPORTS", "200000"))
    slippage_bps: int = field(default_factory=lambda: _i("SLIPPAGE_BPS", "300"))

    # --- Taille / risque
    position_sol: float = field(default_factory=lambda: _f("POSITION_SOL", "0.05"))
    max_positions: int = field(default_factory=lambda: _i("MAX_POSITIONS", "3"))
    sol_reserve: float = field(default_factory=lambda: _f("SOL_RESERVE", "0.03"))
    daily_loss_limit_sol: float = field(default_factory=lambda: _f("DAILY_LOSS_LIMIT_SOL", "0.15"))
    paper_balance_sol: float = field(default_factory=lambda: _f("PAPER_BALANCE_SOL", "1.0"))

    # --- Sorties
    take_profit_pct: float = field(default_factory=lambda: _f("TAKE_PROFIT_PCT", "60"))
    stop_loss_pct: float = field(default_factory=lambda: _f("STOP_LOSS_PCT", "20"))
    trailing_activate_pct: float = field(default_factory=lambda: _f("TRAILING_ACTIVATE_PCT", "25"))
    trailing_stop_pct: float = field(default_factory=lambda: _f("TRAILING_STOP_PCT", "15"))
    max_hold_minutes: int = field(default_factory=lambda: _i("MAX_HOLD_MINUTES", "240"))

    # --- Filtres d'univers
    min_liquidity_usd: float = field(default_factory=lambda: _f("MIN_LIQUIDITY_USD", "25000"))
    min_mcap_usd: float = field(default_factory=lambda: _f("MIN_MCAP_USD", "50000"))
    max_mcap_usd: float = field(default_factory=lambda: _f("MAX_MCAP_USD", "20000000"))
    min_age_minutes: int = field(default_factory=lambda: _i("MIN_AGE_MINUTES", "15"))
    max_age_hours: int = field(default_factory=lambda: _i("MAX_AGE_HOURS", "72"))
    min_txns_h1: int = field(default_factory=lambda: _i("MIN_TXNS_H1", "150"))
    max_h1_change_pct: float = field(default_factory=lambda: _f("MAX_H1_CHANGE_PCT", "250"))
    min_score: float = field(default_factory=lambda: _f("MIN_SCORE", "0.6"))

    # --- Sécurité token
    max_roundtrip_loss_pct: float = field(default_factory=lambda: _f("MAX_ROUNDTRIP_LOSS_PCT", "8"))
    max_rugcheck_score: int = field(default_factory=lambda: _i("MAX_RUGCHECK_SCORE", "1000"))
    max_price_impact_pct: float = field(default_factory=lambda: _f("MAX_PRICE_IMPACT_PCT", "3"))
    token_cooldown_hours: float = field(default_factory=lambda: _f("TOKEN_COOLDOWN_HOURS", "12"))

    # --- Boucle / notifications
    scan_interval: int = field(default_factory=lambda: _i("SCAN_INTERVAL", "30"))
    telegram_token: str = field(default_factory=lambda: os.environ.get("TELEGRAM_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.environ.get("TELEGRAM_CHAT_ID", ""))
    state_file: str = field(default_factory=lambda: os.environ.get(
        "MEMECOIN_STATE_FILE", os.path.join(ROOT, "memecoin_state.json")))
