"""Backtest the SMA crossover strategy against real historical prices.

This is intentionally simple: no slippage or commission modeling beyond
what the spread already implies via mid-price bars, and only one open
position at a time. Read the printed caveats -- a good backtest here is
evidence the strategy isn't obviously broken, not a promise about the
future. Two weeks of real market data is not enough to trust any
strategy; treat short backtests as a sanity check, not proof.

Usage:
    python backtester.py --epic <EPIC> [--resolution HOUR] [--bars 1000]
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

from capital_client import CapitalClient
from config import load_config
from indicators import average_true_range, parse_bars
from strategy import SmaCrossoverStrategy


@dataclass
class OpenTrade:
    direction: str
    entry: float
    stop: float
    size: float
    entry_index: int


@dataclass
class ClosedTrade:
    direction: str
    entry: float
    exit: float
    size: float
    pnl: float
    reason: str


def run_backtest(
    bars: list[dict],
    strategy: SmaCrossoverStrategy,
    starting_equity: float,
    risk_per_trade_pct: float,
    min_deal_size: float,
    margin_factor_pct: float,
    atr_multiplier: float = 1.5,
) -> dict:
    equity = starting_equity
    peak_equity = starting_equity
    max_drawdown_pct = 0.0
    equity_curve = [equity]

    position: OpenTrade | None = None
    trades: list[ClosedTrade] = []
    skipped_insufficient_margin = 0

    for i in range(strategy.min_bars_required(), len(bars)):
        bar = bars[i]
        bars_so_far = bars[: i + 1]

        if position is not None:
            hit_stop = (
                position.direction == "BUY" and bar["low"] <= position.stop
            ) or (position.direction == "SELL" and bar["high"] >= position.stop)

            signal = strategy.generate_signal(bars_so_far)
            opposite_signal = (position.direction == "BUY" and signal == "SELL") or (
                position.direction == "SELL" and signal == "BUY"
            )

            if hit_stop or opposite_signal:
                exit_price = position.stop if hit_stop else bar["close"]
                direction_sign = 1 if position.direction == "BUY" else -1
                pnl = (exit_price - position.entry) * direction_sign * position.size
                equity += pnl
                trades.append(
                    ClosedTrade(
                        position.direction, position.entry, exit_price, position.size, pnl,
                        "stop" if hit_stop else "signal",
                    )
                )
                position = None

        if position is None:
            signal = strategy.generate_signal(bars_so_far)
            if signal in ("BUY", "SELL"):
                atr = average_true_range(bars[: i + 1])
                stop_distance = atr * atr_multiplier if atr else bar["close"] * 0.02
                entry = bar["close"]
                stop = entry - stop_distance if signal == "BUY" else entry + stop_distance

                risk_amount = equity * (risk_per_trade_pct / 100)
                size = risk_amount / stop_distance if stop_distance > 0 else 0

                margin_required = entry * size * (margin_factor_pct / 100)
                if size < min_deal_size or margin_required > equity:
                    skipped_insufficient_margin += 1
                else:
                    position = OpenTrade(signal, entry, stop, size, i)

        peak_equity = max(peak_equity, equity)
        drawdown_pct = (peak_equity - equity) / peak_equity * 100 if peak_equity > 0 else 0
        max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)
        equity_curve.append(equity)

    if position is not None:
        last_close = bars[-1]["close"]
        direction_sign = 1 if position.direction == "BUY" else -1
        pnl = (last_close - position.entry) * direction_sign * position.size
        equity += pnl
        trades.append(ClosedTrade(position.direction, position.entry, last_close, position.size, pnl, "mark-to-market close"))

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]

    return {
        "starting_equity": starting_equity,
        "final_equity": equity,
        "total_return_pct": (equity - starting_equity) / starting_equity * 100,
        "num_trades": len(trades),
        "win_rate_pct": (len(wins) / len(trades) * 100) if trades else 0,
        "avg_win": sum(t.pnl for t in wins) / len(wins) if wins else 0,
        "avg_loss": sum(t.pnl for t in losses) / len(losses) if losses else 0,
        "max_drawdown_pct": max_drawdown_pct,
        "skipped_insufficient_margin": skipped_insufficient_margin,
        "trades": trades,
        "equity_curve": equity_curve,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epic", required=True)
    parser.add_argument("--resolution", default="HOUR")
    parser.add_argument("--bars", type=int, default=1000)
    parser.add_argument("--equity", type=float, default=None, help="override starting equity (account currency)")
    args = parser.parse_args()

    cfg = load_config()
    cfg.validate()
    client = CapitalClient(cfg.base_url, cfg.identifier, cfg.api_key, cfg.api_password)

    account = client.get_primary_account()
    starting_equity = args.equity if args.equity is not None else CapitalClient.get_equity(account)

    market = client.get_market(args.epic)
    min_deal_size = market.get("dealingRules", {}).get("minDealSize", {}).get("value", 0)
    margin_factor_pct = market.get("instrument", {}).get("marginFactor", 100)

    raw_prices = client.get_prices(args.epic, resolution=args.resolution, max_points=args.bars)
    bars = parse_bars(raw_prices)
    if len(bars) < 60:
        raise SystemExit(f"Only got {len(bars)} bars back -- not enough history for a meaningful backtest.")

    strategy = SmaCrossoverStrategy(
        cfg.sma_short, cfg.sma_long, min_separation_atr_multiplier=cfg.min_separation_atr_multiplier
    )
    result = run_backtest(
        bars, strategy, starting_equity, cfg.risk_per_trade_pct, min_deal_size, margin_factor_pct
    )

    print(f"\nBacktest: {args.epic}  ({len(bars)} {args.resolution} bars)")
    print(f"Strategy: SMA({cfg.sma_short}/{cfg.sma_long}), risk/trade {cfg.risk_per_trade_pct}%\n")
    print(f"Starting equity:  {result['starting_equity']:.2f}")
    print(f"Final equity:     {result['final_equity']:.2f}")
    print(f"Total return:     {result['total_return_pct']:+.2f}%")
    print(f"Trades:           {result['num_trades']}  (win rate {result['win_rate_pct']:.1f}%)")
    print(f"Avg win / loss:   {result['avg_win']:+.2f} / {result['avg_loss']:+.2f}")
    print(f"Max drawdown:     {result['max_drawdown_pct']:.1f}%")
    print(f"Skipped (margin): {result['skipped_insufficient_margin']} signals had insufficient margin/size")
    print(
        "\nThis is a backtest over a limited, past window on one instrument. It is not a "
        "forecast. A positive result here does not make a specific 2-week real-money target "
        "achievable -- markets that produced this result will not necessarily repeat it."
    )


if __name__ == "__main__":
    main()
