"""Position sizing and account-level safety gates.

The design intent: every single trade risks a small, fixed percentage of
current equity, and the bot refuses to trade at all once daily losses or
drawdown-from-peak crosses a threshold. None of this can prevent a loss on
any given trade -- CFDs are leveraged and prices move against you -- but it
bounds how much any one bad trade or bad day/stretch can cost.
"""
from __future__ import annotations

from dataclasses import dataclass

from state_store import BotState, StateStore


@dataclass
class SizingResult:
    size: float
    reason: str = ""

    @property
    def tradeable(self) -> bool:
        return self.size > 0


class RiskManager:
    def __init__(
        self,
        risk_per_trade_pct: float,
        daily_loss_limit_pct: float,
        max_drawdown_pct: float,
        max_open_positions: int,
        state_store: StateStore,
    ):
        self.risk_per_trade_pct = risk_per_trade_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_open_positions = max_open_positions
        self.state_store = state_store

    def _refresh_daily_anchor(self, state: BotState, current_equity: float) -> BotState:
        today = StateStore.today()
        if state.daily_start_date != today:
            state.daily_start_date = today
            state.daily_start_equity = current_equity
        if current_equity > state.peak_equity:
            state.peak_equity = current_equity
        if state.peak_equity == 0.0:
            state.peak_equity = current_equity
        return state

    def check_can_trade(self, current_equity: float) -> tuple[bool, str]:
        """Call before every trading decision. Returns (allowed, reason)."""
        state = self.state_store.load()
        state = self._refresh_daily_anchor(state, current_equity)

        if state.halted:
            self.state_store.save(state)
            return False, f"Bot is halted: {state.halt_reason}. Fix and clear state.json to resume."

        if state.daily_start_equity > 0:
            daily_loss_pct = (state.daily_start_equity - current_equity) / state.daily_start_equity * 100
            if daily_loss_pct >= self.daily_loss_limit_pct:
                state.halted = True
                state.halt_reason = (
                    f"Daily loss limit hit: -{daily_loss_pct:.1f}% "
                    f"(limit {self.daily_loss_limit_pct}%)"
                )
                self.state_store.save(state)
                return False, state.halt_reason

        if state.peak_equity > 0:
            drawdown_pct = (state.peak_equity - current_equity) / state.peak_equity * 100
            if drawdown_pct >= self.max_drawdown_pct:
                state.halted = True
                state.halt_reason = (
                    f"Max drawdown from peak hit: -{drawdown_pct:.1f}% "
                    f"(limit {self.max_drawdown_pct}%)"
                )
                self.state_store.save(state)
                return False, state.halt_reason

        self.state_store.save(state)
        return True, ""

    def position_size(
        self,
        equity: float,
        entry_price: float,
        stop_price: float,
        min_deal_size: float,
        deal_size_step: float = 0.01,
    ) -> SizingResult:
        stop_distance = abs(entry_price - stop_price)
        if stop_distance <= 0:
            return SizingResult(0.0, "stop distance is zero, cannot size position")

        risk_amount = equity * (self.risk_per_trade_pct / 100)
        raw_size = risk_amount / stop_distance

        # round down to the broker's allowed size increment
        steps = int(raw_size / deal_size_step)
        size = steps * deal_size_step

        if size < min_deal_size:
            return SizingResult(
                0.0,
                f"computed size {size:.4f} is below broker minimum {min_deal_size} for this "
                f"instrument -- budget is too small for this instrument at this risk level",
            )
        return SizingResult(round(size, 4))
