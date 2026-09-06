"""Tiny JSON-file state store so the bot survives restarts without
re-triggering daily-loss/drawdown logic or losing track of what day it is.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


@dataclass
class BotState:
    daily_start_date: str = ""  # ISO date, UTC
    daily_start_equity: float = 0.0
    peak_equity: float = 0.0
    halted: bool = False
    halt_reason: str = ""


class StateStore:
    def __init__(self, path: str = "state.json"):
        self.path = path

    def load(self) -> BotState:
        if not os.path.exists(self.path):
            return BotState()
        with open(self.path) as f:
            return BotState(**json.load(f))

    def save(self, state: BotState) -> None:
        with open(self.path, "w") as f:
            json.dump(asdict(state), f, indent=2)

    @staticmethod
    def today() -> str:
        return datetime.now(timezone.utc).date().isoformat()
