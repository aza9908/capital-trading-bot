import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


@dataclass(frozen=True)
class Config:
    identifier: str
    api_key: str
    api_password: str
    env: str
    epic: str
    sma_short: int
    sma_long: int
    min_separation_atr_multiplier: float
    risk_per_trade_pct: float
    daily_loss_limit_pct: float
    max_drawdown_pct: float
    max_open_positions: int
    poll_interval_minutes: int
    starting_equity_kzt: float

    @property
    def base_url(self) -> str:
        if self.env == "live":
            return "https://api-capital.backend-capital.com"
        return "https://demo-api-capital.backend-capital.com"

    def validate(self) -> None:
        missing = [
            name
            for name, value in [
                ("CAPITAL_IDENTIFIER", self.identifier),
                ("CAPITAL_API_KEY", self.api_key),
                ("CAPITAL_API_PASSWORD", self.api_password),
            ]
            if not value
        ]
        if missing:
            raise SystemExit(
                f"Missing required .env values: {', '.join(missing)}. "
                f"Copy .env.example to .env and fill them in."
            )
        if self.env not in ("demo", "live"):
            raise SystemExit(f"CAPITAL_ENV must be 'demo' or 'live', got {self.env!r}")


def load_config() -> Config:
    return Config(
        identifier=os.getenv("CAPITAL_IDENTIFIER", ""),
        api_key=os.getenv("CAPITAL_API_KEY", ""),
        api_password=os.getenv("CAPITAL_API_PASSWORD", ""),
        env=os.getenv("CAPITAL_ENV", "demo"),
        epic=os.getenv("EPIC", ""),
        sma_short=_int("SMA_SHORT", 20),
        sma_long=_int("SMA_LONG", 50),
        min_separation_atr_multiplier=_float("MIN_SEPARATION_ATR_MULTIPLIER", 0.02),
        risk_per_trade_pct=_float("RISK_PER_TRADE_PCT", 1.0),
        daily_loss_limit_pct=_float("DAILY_LOSS_LIMIT_PCT", 5.0),
        max_drawdown_pct=_float("MAX_DRAWDOWN_PCT", 15.0),
        max_open_positions=_int("MAX_OPEN_POSITIONS", 1),
        poll_interval_minutes=_int("POLL_INTERVAL_MINUTES", 15),
        starting_equity_kzt=_float("STARTING_EQUITY_KZT", 20000),
    )
