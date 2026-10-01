import base64
import pytest
from solders.hash import Hash
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.signature import Signature
from solders.transaction import VersionedTransaction

from memecoin_bot import safety, strategy
from memecoin_bot.config import LAMPORTS, Config
from memecoin_bot.state import State
from memecoin_bot.trader import Trader
from memecoin_bot.wallet import PhantomWallet

NOW = 1_800_000_000


def pair(**kw):
    p = {
        "liquidity": {"usd": 80_000}, "marketCap": 900_000,
        "pairCreatedAt": (NOW - 3 * 3600) * 1000,
        "priceChange": {"m5": 6, "h1": 40, "h6": 80},
        "txns": {"m5": {"buys": 70, "sells": 30}, "h1": {"buys": 600, "sells": 400}},
        "volume": {"m5": 30_000, "h1": 200_000},
    }
    p.update(kw)
    return p


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.state_file = str(tmp_path / "s.json")
    c.dry_run = True
    return c


def test_strong_momentum_triggers_entry(cfg):
    ok, why, s = strategy.entry_signal(strategy.features(pair(), NOW), cfg)
    assert ok, why
    assert s >= cfg.min_score


@pytest.mark.parametrize("kw,reason", [
    ({"liquidity": {"usd": 5_000}}, "liquidité"),
    ({"pairCreatedAt": (NOW - 60) * 1000}, "récent"),
    ({"priceChange": {"m5": 5, "h1": 900}}, "pompé"),
    ({"priceChange": {"m5": -3, "h1": 20}}, "momentum"),
    ({"txns": {"m5": {"buys": 20, "sells": 80}, "h1": {"buys": 300, "sells": 300}}}, "acheteurs"),
])
def test_rejections(cfg, kw, reason):
    ok, why, _ = strategy.entry_signal(strategy.features(pair(**kw), NOW), cfg)
    assert not ok and reason in why


def test_exit_rules(cfg):
    base = lambda: {"cost_sol": 1.0, "peak_sol": 1.0, "opened_at": NOW}
    assert strategy.exit_signal(base(), 0.79, cfg, NOW)[0]                      # stop-loss
    assert strategy.exit_signal(base(), 1.61, cfg, NOW)[0]                      # take-profit
    assert not strategy.exit_signal(base(), 1.10, cfg, NOW)[0]
    p = base(); strategy.exit_signal(p, 1.40, cfg, NOW)                         # pic +40 %
    sell, why = strategy.exit_signal(p, 1.15, cfg, NOW)                         # -18 % depuis le pic
    assert sell and "trailing" in why
    assert strategy.exit_signal(base(), 1.0, cfg, NOW + cfg.max_hold_minutes * 60)[0]


class FakeJup:
    def __init__(self, rate=1000, sell_rate=None, impact="0.001"):
        self.rate, self.sell_rate, self.impact = rate, sell_rate or rate, impact

    def quote(self, i, o, amount, slippage_bps=None):
        if i.startswith("So111"):
            return {"outAmount": str(amount * self.rate), "priceImpactPct": self.impact}
        return {"outAmount": str(int(amount / self.sell_rate)), "priceImpactPct": self.impact}


class FakeRPC:
    def __init__(self, mint_auth=None, freeze=None):
        self.info = {"mintAuthority": mint_auth, "freezeAuthority": freeze}

    def mint_info(self, mint):
        return self.info


@pytest.fixture(autouse=True)
def no_rugcheck(monkeypatch):
    monkeypatch.setattr(safety, "rugcheck", lambda m: {"score": 100, "risks": []})


def test_safety(cfg):
    assert safety.check_token("M", cfg, FakeRPC(), FakeJup())[0]
    assert "mint authority" in safety.check_token("M", cfg, FakeRPC(mint_auth="X"), FakeJup())[1]
    assert "freeze" in safety.check_token("M", cfg, FakeRPC(freeze="X"), FakeJup())[1]
    assert "aller-retour" in safety.check_token("M", cfg, FakeRPC(), FakeJup(1000, 1200))[1]  # taxe ~17 %
    assert "impact" in safety.check_token("M", cfg, FakeRPC(), FakeJup(impact="0.08"))[1]


def test_paper_round_trip(cfg):
    st = State(cfg.state_file, 1.0)
    jup = FakeJup()
    tr = Trader(cfg, None, jup, st)
    q = jup.quote("So111", "M", int(cfg.position_sol * LAMPORTS))
    tr.buy("M", "MEME", q, 0.8)
    assert "M" in st.positions and st.d["paper_sol"] == pytest.approx(1 - cfg.position_sol)
    jup.sell_rate = 500  # le token a doublé
    proceeds, pnl, _ = tr.sell(st.positions["M"], "tp")
    assert pnl == pytest.approx(cfg.position_sol, rel=1e-6)
    assert st.d["paper_sol"] == pytest.approx(1 + cfg.position_sol, rel=1e-6)
    assert not st.positions and st.daily_pnl() == pytest.approx(pnl)
    assert State(cfg.state_file, 1.0).d["history"][0]["reason"] == "tp"  # persisté


def test_phantom_wallet_signs_jupiter_tx():
    kp = Keypair()
    w = PhantomWallet(str(kp))
    msg = MessageV0.try_compile(kp.pubkey(), [], [], Hash.default())
    unsigned = VersionedTransaction.populate(msg, [Signature.default()])  # comme renvoyé par Jupiter
    signed = VersionedTransaction.from_bytes(base64.b64decode(w.sign_b64(base64.b64encode(bytes(unsigned)).decode())))
    assert w.pubkey == str(kp.pubkey())
    assert signed.verify_with_results() == [True]
