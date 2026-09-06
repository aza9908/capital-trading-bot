"""Find instruments whose *minimum* position size actually fits a small budget.

With ~20,000 KZT (roughly $35-40), most share CFDs require more margin than
that just to open the smallest allowed size. This script checks real
instrument data from the API instead of guessing, so you pick an EPIC that
is actually tradeable at your budget before wiring up the bot.

Usage:
    python screen_instruments.py [--budget 35] [--terms "Apple,Gold,US 500"]

Note: Capital.com's exact field names in /api/v1/markets/{epic} have
shifted between API versions in the past. If the fields referenced below
(marginFactor, minDealSize, snapshot.bid/offer) come back missing, print
the raw response and check https://open-api.capital.com/ for the current
shape rather than assuming this script is right.
"""
from __future__ import annotations

import argparse

from capital_client import CapitalApiError, CapitalClient
from config import load_config

DEFAULT_TERMS = [
    "US 500",
    "Germany 40",
    "Gold",
    "EUR/USD",
    "Apple",
    "Vodafone",
]


def estimate_margin_for_min_size(market: dict) -> dict | None:
    instrument = market.get("instrument", {})
    dealing_rules = market.get("dealingRules", {})
    snapshot = market.get("snapshot", {})

    margin_factor = instrument.get("marginFactor")
    min_deal_size = dealing_rules.get("minDealSize", {}).get("value")
    bid = snapshot.get("bid")
    offer = snapshot.get("offer")

    if None in (margin_factor, min_deal_size, bid, offer):
        return None

    mid_price = (bid + offer) / 2
    notional = mid_price * min_deal_size
    margin_required = notional * (margin_factor / 100)

    return {
        "epic": instrument.get("epic"),
        "name": instrument.get("name"),
        "type": instrument.get("type"),
        "mid_price": mid_price,
        "min_deal_size": min_deal_size,
        "margin_factor_pct": margin_factor,
        "margin_required": margin_required,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=float, default=35.0, help="budget in account currency")
    parser.add_argument("--terms", type=str, default=",".join(DEFAULT_TERMS))
    args = parser.parse_args()

    cfg = load_config()
    cfg.validate()
    client = CapitalClient(cfg.base_url, cfg.identifier, cfg.api_key, cfg.api_password)

    account = client.get_primary_account()
    print(f"Account currency: {account.get('currency')}  Balance: {CapitalClient.get_equity(account):.2f}\n")

    print(f"{'EPIC':<15} {'Name':<25} {'Type':<10} {'MinSize':>8} {'Margin/min':>12} {'Fits budget?':>12}")
    print("-" * 90)

    for term in [t.strip() for t in args.terms.split(",") if t.strip()]:
        try:
            markets = client.search_markets(term)
        except CapitalApiError as e:
            print(f"[{term}] search failed: {e}")
            continue

        for m in markets[:3]:
            epic = m["epic"]
            try:
                detail = client.get_market(epic)
            except CapitalApiError as e:
                print(f"[{epic}] detail failed: {e}")
                continue

            est = estimate_margin_for_min_size(detail)
            if est is None:
                print(f"{epic:<15} (could not parse margin fields, inspect manually)")
                continue

            fits = "YES" if est["margin_required"] <= args.budget else "no"
            print(
                f"{est['epic']:<15} {est['name'][:25]:<25} {est['type']:<10} "
                f"{est['min_deal_size']:>8} {est['margin_required']:>12.2f} {fits:>12}"
            )


if __name__ == "__main__":
    main()
