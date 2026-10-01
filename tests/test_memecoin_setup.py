import json
import os
import stat

import pytest
from solders.keypair import Keypair

from memecoin_bot import connect, main
from memecoin_bot.config import Config, load_env
from memecoin_bot.wallet import PhantomWallet, parse_private_key


def test_parse_private_key_formats():
    kp = Keypair()
    assert parse_private_key(str(kp)).pubkey() == kp.pubkey()                       # base58 Phantom
    assert parse_private_key(f'  "{kp}" \n').pubkey() == kp.pubkey()                 # copié avec guillemets
    assert parse_private_key(json.dumps(list(bytes(kp)))).pubkey() == kp.pubkey()    # Solana CLI
    with pytest.raises(ValueError, match="phrase de récupération"):
        parse_private_key(" ".join(["abandon"] * 12))
    with pytest.raises(ValueError, match="invalide"):
        parse_private_key(str(kp.pubkey()))                                         # adresse publique
    with pytest.raises(ValueError, match="manquante"):
        PhantomWallet("")


def test_write_env_then_load(tmp_path, monkeypatch):
    kp = Keypair()
    env = tmp_path / ".env"
    connect.write_env({"PHANTOM_PRIVATE_KEY": str(kp), "DRY_RUN": "0", "POSITION_SOL": "0.1",
                       "SOLANA_RPC_URL": "https://rpc.example/?api-key=x"}, path=str(env))
    text = env.read_text()
    assert f"PHANTOM_PRIVATE_KEY={kp}\n" in text and "MAX_POSITIONS=3" in text   # modèle conservé
    if os.name == "posix":
        assert stat.S_IMODE(env.stat().st_mode) == 0o600
    for k in ("PHANTOM_PRIVATE_KEY", "DRY_RUN", "POSITION_SOL", "SOLANA_RPC_URL", "MAX_POSITIONS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MAX_POSITIONS", "5")                                      # l'environnement prime
    assert load_env(str(env))
    c = Config()
    assert not c.dry_run and c.position_sol == 0.1 and c.max_positions == 5
    assert c.rpc_url == "https://rpc.example/?api-key=x"
    assert PhantomWallet(c.phantom_private_key).pubkey == str(kp.pubkey())
    assert connect.read_env(str(env))["DRY_RUN"] == "0"


def test_example_env_inline_comment(tmp_path, monkeypatch):
    monkeypatch.delenv("SOLANA_RPC_URL", raising=False)
    load_env(connect.TEMPLATE)
    assert os.environ["SOLANA_RPC_URL"] == "https://api.mainnet-beta.solana.com"


class OkRPC:
    def __init__(self, lamports):
        self.lamports = lamports

    def call(self, method, params=None):
        return 123

    def sol_balance(self, pub):
        return self.lamports


class OkJup:
    def quote(self, *a, **k):
        return {"outAmount": "7500000"}


@pytest.mark.parametrize("dry,lamports,expected", [("1", 0, True), ("0", 10**9, True), ("0", 10**6, False)])
def test_check(monkeypatch, tmp_path, capsys, dry, lamports, expected):
    monkeypatch.setattr(main, "ENV_FILE", str(tmp_path / ".env"))
    (tmp_path / ".env").write_text("")
    monkeypatch.setattr(main.dexscreener, "candidate_mints", lambda: ["a", "b"])
    monkeypatch.setenv("DRY_RUN", dry)
    monkeypatch.setenv("PHANTOM_PRIVATE_KEY", str(Keypair()))
    assert main.check(Config(), OkRPC(lamports), OkJup()) is expected
    assert ("❌" in capsys.readouterr().out) is (not expected)
