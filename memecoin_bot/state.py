"""Persistance JSON : positions ouvertes, historique, PnL du jour, cooldowns."""
import json
import os
import time
from datetime import datetime, timezone


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class State:
    def __init__(self, path, paper_balance):
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                self.d = json.load(f)
        except Exception:
            self.d = {}
        self.d.setdefault("positions", {})
        self.d.setdefault("history", [])
        self.d.setdefault("cooldown", {})
        self.d.setdefault("daily", {})
        self.d.setdefault("paper_sol", paper_balance)

    @property
    def positions(self):
        return self.d["positions"]

    def daily_pnl(self):
        return self.d["daily"].get(today(), 0.0)

    def add_pnl(self, sol):
        self.d["daily"][today()] = self.daily_pnl() + sol

    def in_cooldown(self, mint, hours):
        return time.time() - self.d["cooldown"].get(mint, 0) < hours * 3600

    def set_cooldown(self, mint):
        self.d["cooldown"][mint] = time.time()

    def save(self):
        self.d["history"] = self.d["history"][-500:]
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)
