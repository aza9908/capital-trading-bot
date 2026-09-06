# Capital.com CFD Trading Bot

A small, rule-based (not AI-driven) automated trading bot for
[Capital.com](https://capital.com), built around an SMA-crossover strategy
with strict risk limits. Runs against the **demo** environment by default.

## Read this first: what this bot can and cannot do

**It cannot turn 20,000 tenge into 1,000,000 tenge in two weeks.** That is a
50x return in 14 days. No legitimate trading strategy does this reliably —
if it could, everyone using it would already be a billionaire. Any system
claiming otherwise is either gambling with your capital (expected outcome:
losing it) or lying. This bot does not attempt that goal.

**Capital.com trades CFDs (Contracts for Difference), not real shares.**
CFDs are leveraged derivatives:
- Leverage amplifies losses exactly as much as gains.
- You don't own the underlying stock — you have a contract with Capital.com.
- Overnight positions typically incur financing fees.
- Depending on your account's jurisdiction/regulator, you may or may not
  have negative-balance protection. **Check your actual account terms** —
  this bot does not verify that for you.

**A realistic target** for a small, risk-managed account over two weeks is
a few percent, or a loss — trading is not guaranteed income, and a strategy
that looks good in a backtest can still lose money going forward. If you
are not comfortable potentially losing the full 20,000 tenge, don't fund
the account with money you need.

## What it actually does

- Strategy: SMA crossover (configurable short/long windows) computed on
  closed price bars only — a deterministic, backtestable rule, not an LLM
  guessing at market timing.
- Risk management, enforced on every trade and every loop iteration:
  - Fixed % of equity risked per trade, sized off an ATR-based stop-loss.
  - Every position has a stop-loss and take-profit from the moment it opens.
  - Daily loss limit — bot halts itself for the day if hit.
  - Max drawdown-from-peak kill switch — halts until you manually clear
    `state.json`, forcing you to actually notice before it resumes.
  - Max open positions cap.
- Backtester against real historical prices from the API, so you see
  simulated performance before ever running it live.
- Instrument screener, because most CFDs need more margin than 20,000
  tenge covers just to open the *minimum* size — this checks real
  numbers instead of guessing.
- Defaults to Capital.com's demo environment. Going live requires three
  independent, explicit steps (see below) — never accidental.

## Setup

1. Create/log into your Capital.com account, enable 2FA, then create an
   API key under Settings > API integrations.
2. `cd capital-trading-bot`
3. `python3 -m venv .venv && source .venv/bin/activate`
4. `pip install -r requirements.txt`
5. `cp .env.example .env` and fill in `CAPITAL_IDENTIFIER`,
   `CAPITAL_API_KEY`, `CAPITAL_API_PASSWORD`. Leave `CAPITAL_ENV=demo`.

## Step 1 — find an instrument your budget can actually trade

```
python screen_instruments.py --budget 35
```

This prints, for a handful of common instruments, the margin required to
open the *minimum* allowed position size. Pick one where "Fits budget?"
says YES, and put its EPIC into `.env` as `EPIC=...`.
(Edit `DEFAULT_TERMS` in `screen_instruments.py` to check other instruments.)

## Step 2 — backtest before trusting it with anything

```
python backtester.py --epic <EPIC> --resolution HOUR --bars 1000
```

Read the printed stats and the caveat at the bottom. If the strategy shows
a large drawdown or a poor win rate on this instrument, do not proceed —
try a different instrument, or accept that SMA crossover may not suit this
market right now.

## Step 3 — run it on demo

```
python bot.py --once     # single check, good for a first test
python bot.py            # loops forever, polling every POLL_INTERVAL_MINUTES
```

Watch `bot.log` and your Capital.com demo dashboard. Let it run for the
full two weeks on demo before ever considering live money — that's the
only way to know how it behaves in conditions you haven't backtested.

## Step 4 — going live (optional, your call, real money at risk)

Three independent things must all be true, on purpose:

1. `CAPITAL_ENV=live` in `.env`
2. `--live` on the command line
3. `--confirm "I UNDERSTAND THE RISK"` (exact phrase) on the command line

```
python bot.py --live --confirm "I UNDERSTAND THE RISK"
```

## Files

| File | Purpose |
|---|---|
| `capital_client.py` | REST API wrapper (auth, market data, positions) |
| `strategy.py` | SMA crossover signal logic |
| `indicators.py` | SMA / ATR helpers |
| `risk_manager.py` | Position sizing + daily loss/drawdown gates |
| `state_store.py` | Persists halt state / daily equity anchor to `state.json` |
| `backtester.py` | Historical simulation + stats |
| `screen_instruments.py` | Finds instruments affordable at your budget |
| `bot.py` | Main loop tying it all together |

## Known limitations, honestly

- Backtests use whatever history the API returns for a given resolution
  (up to ~1000 bars); that's a limited window, not a long-term edge proof.
- No slippage/commission modeling beyond the bid/ask mid-price bars.
- Only one open position at a time, one instrument at a time.
- API field names (margin factor, min deal size, etc.) were implemented
  against Capital.com's public docs at https://open-api.capital.com/ as of
  writing — if requests start failing, check that page for changes before
  assuming the bot's logic is wrong.
- This has not been run against a live account by me. Test thoroughly on
  demo first.
