"""Main trading loop.

Runs against Capital.com's DEMO environment by default. Going live requires
ALL of: CAPITAL_ENV=live in .env, the --live flag, and --confirm with the
exact phrase below -- three independent steps, on purpose, so live trading
never happens by accident.

Usage:
    python bot.py                          # demo, runs forever, polling
    python bot.py --once                   # demo, single check then exit
    python bot.py --live --confirm "I UNDERSTAND THE RISK"
"""
from __future__ import annotations

import argparse
import logging
import time

from capital_client import CapitalApiError, CapitalClient
from config import load_config
from indicators import average_true_range, parse_bars
from risk_manager import RiskManager
from state_store import StateStore
from strategy import SmaCrossoverStrategy

CONFIRM_PHRASE = "I UNDERSTAND THE RISK"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("bot.log")],
)
log = logging.getLogger("bot")


def run_once(client: CapitalClient, cfg, strategy: SmaCrossoverStrategy, risk: RiskManager) -> None:
    account = client.get_primary_account()
    equity = CapitalClient.get_equity(account)
    currency = account.get("currency", "?")
    log.info("Equity: %.2f %s", equity, currency)

    can_trade, reason = risk.check_can_trade(equity)
    if not can_trade:
        log.warning("Not trading: %s", reason)
        halted_positions = [p for p in client.get_open_positions() if p.epic == cfg.epic]
        for p in halted_positions:
            log.warning("Force-closing %s position %s due to halt", p.direction, p.deal_id)
            try:
                client.close_position(p.deal_id)
            except CapitalApiError as e:
                log.error("Failed to force-close %s: %s", p.deal_id, e)
        return

    market = client.get_market(cfg.epic)
    min_deal_size = market.get("dealingRules", {}).get("minDealSize", {}).get("value", 0)

    raw_prices = client.get_prices(cfg.epic, resolution="HOUR", max_points=strategy.min_bars_required() + 5)
    bars = parse_bars(raw_prices)
    if len(bars) < strategy.min_bars_required():
        log.warning("Not enough price history yet (%d bars) -- skipping this check", len(bars))
        return

    signal = strategy.generate_signal(bars)
    log.info("Signal: %s", signal)

    open_positions = [p for p in client.get_open_positions() if p.epic == cfg.epic]

    if open_positions:
        position = open_positions[0]
        opposite = (position.direction == "BUY" and signal == "SELL") or (
            position.direction == "SELL" and signal == "BUY"
        )
        if opposite:
            log.info("Closing %s position %s on opposite signal", position.direction, position.deal_id)
            client.close_position(position.deal_id)
        else:
            log.info("Holding existing %s position", position.direction)
        return

    if signal == "HOLD":
        return

    if len(open_positions) >= risk.max_open_positions:
        log.info("Max open positions reached, skipping new entry")
        return

    atr = average_true_range(bars)
    entry_price = bars[-1]["close"]
    stop_distance = atr * 1.5 if atr else entry_price * 0.02
    stop_level = entry_price - stop_distance if signal == "BUY" else entry_price + stop_distance
    profit_level = entry_price + 2 * stop_distance if signal == "BUY" else entry_price - 2 * stop_distance

    sizing = risk.position_size(equity, entry_price, stop_level, min_deal_size)
    if not sizing.tradeable:
        log.warning("Skipping trade: %s", sizing.reason)
        return

    log.info(
        "Opening %s %s size=%s stop=%.4f target=%.4f",
        signal, cfg.epic, sizing.size, stop_level, profit_level,
    )
    try:
        deal_ref = client.open_position(cfg.epic, signal, sizing.size, stop_level, profit_level)
        log.info("Order placed: %s", deal_ref)
    except CapitalApiError as e:
        log.error("Failed to place order: %s", e)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="allow live trading (also requires CAPITAL_ENV=live and --confirm)")
    parser.add_argument("--confirm", type=str, default="", help=f'must exactly equal "{CONFIRM_PHRASE}" to trade live')
    parser.add_argument("--once", action="store_true", help="run a single check instead of looping forever")
    args = parser.parse_args()

    cfg = load_config()
    cfg.validate()

    if cfg.env == "live" and not (args.live and args.confirm == CONFIRM_PHRASE):
        raise SystemExit(
            "CAPITAL_ENV=live but live trading was not explicitly confirmed.\n"
            f'Re-run with: --live --confirm "{CONFIRM_PHRASE}"'
        )
    if args.live and cfg.env != "live":
        raise SystemExit("--live was passed but CAPITAL_ENV in .env is not 'live'. Refusing to proceed.")

    if not cfg.epic:
        raise SystemExit("EPIC is not set in .env. Run screen_instruments.py to find a tradeable instrument first.")

    log.info("Starting bot in %s mode, epic=%s", cfg.env.upper(), cfg.epic)
    if cfg.env == "live":
        log.warning("LIVE TRADING IS ACTIVE. Real money is at risk.")

    client = CapitalClient(cfg.base_url, cfg.identifier, cfg.api_key, cfg.api_password)
    strategy = SmaCrossoverStrategy(
        cfg.sma_short, cfg.sma_long, min_separation_atr_multiplier=cfg.min_separation_atr_multiplier
    )
    risk = RiskManager(
        cfg.risk_per_trade_pct, cfg.daily_loss_limit_pct, cfg.max_drawdown_pct,
        cfg.max_open_positions, StateStore(),
    )

    while True:
        try:
            run_once(client, cfg, strategy, risk)
        except CapitalApiError as e:
            log.error("API error: %s", e)
        except Exception:
            log.exception("Unexpected error in trading loop")

        if args.once:
            break
        time.sleep(cfg.poll_interval_minutes * 60)


if __name__ == "__main__":
    main()
