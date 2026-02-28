# Polymarket Insider Trade Detection

Behavioral analysis system to detect insider trading on Polymarket prediction markets. Scores wallets on 6 signals and classifies them as LOW / MEDIUM / HIGH / CRITICAL risk.

## Demo

> **Loom Video**: [TODO: Add loom video link here — approach walkthrough + dry run + script execution]

## Results

Validated against 8 known insider wallets + 10 normal wallets (control group):

| Wallet | Label | Score | Risk |
|--------|-------|-------|------|
| `0x7f1329ad...` | gj1 (Trump pardon CZ) | 0.880 | CRITICAL |
| `0x6baf05d1...` | SBet365 (Maduro) | 0.805 | HIGH |
| `0x0afc7ce5...` | ricosuave (Israel/Iran) | 0.760 | HIGH |
| `0x31a56e9e...` | unnamed (Maduro) | 0.708 | HIGH |
| `0xee50a31c...` | AlphaRaccoon (Google d4vd) | 0.700 | HIGH |
| `0xc51eedc0...` | hogriddahhhh (Spotify scraper) | 0.640 | MEDIUM |
| `0x55ea982c...` | flaccidwillie (DraftKings) | 0.505 | MEDIUM |
| `0x976685b6...` | fromagi (MicroStrategy) | 0.490 | LOW |
| Normal wallets (10) | — | 0.574 avg | MEDIUM |

- **5/8 insiders** flagged HIGH or CRITICAL
- **0/10 normals** flagged HIGH — zero false positives
- **+0.112 point separation** between insider avg (0.686) and normal avg (0.574)

## Setup

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

## Usage

```bash
# 1. Index all known insiders + normal wallets
uv run python -m src.main index --all

# Or index specific wallets
# uv run python -m src.main index --wallets 0xee50a31c...,0x6baf05d1...

# 2. Run detection on all indexed wallets
uv run python -m src.main detect --all

# 3. Full validation (8 insiders + 10 normals, detailed output)
uv run python validate.py
```

## Detection Signals

| # | Signal | Weight | What It Detects |
|---|--------|--------|-----------------|
| 1 | **WalletFreshness** | 0.15 | Deposit-to-trade gap < hours = burner wallet |
| 2 | **OutcomeCertainty** | 0.25 | Bought at low odds, bet big, won = foreknowledge |
| 3 | **EntryTiming** | 0.20 | Traded in final % of market lifecycle |
| 4 | **MarketFocus** | 0.15 | Only 1-2 markets = targeted knowledge |
| 5 | **PositionSize** | 0.10 | Large USDC concentrated on few markets |
| 6 | **SurgicalBehavior** | 0.15 | Fund -> bet -> win -> withdraw -> disappear |

Composite score = weighted sum. Risk tiers: LOW (< 0.5), MEDIUM (0.5-0.7), HIGH (0.7-0.85), CRITICAL (>= 0.85).

## Architecture

```
src/
├── config.py              # Scoring weights, thresholds, wallet lists
├── models.py              # Pydantic v2 models
├── db.py                  # SQLite repository
├── indexers/
│   ├── trades.py          # Trade indexer (Polymarket data API)
│   ├── deposits.py        # Deposit/withdrawal/redemption indexer
│   └── markets.py         # Market metadata fetcher (Gamma API, concurrent)
├── detection/
│   ├── signals.py         # 6 behavioral signals (Strategy pattern)
│   ├── scorer.py          # Weighted composite scorer
│   └── detector.py        # Orchestrator
└── main.py                # CLI entrypoint
```

## Design Decisions & Tradeoffs

### Data API vs On-Chain RPC Indexing

The assignment references indexing `OrderFilled` events and USDC.e `Transfer` events directly from the Polygon blockchain via RPC. During implementation, I discovered that **Polymarket uses a proxy wallet architecture** — users don't transact directly on-chain. All wallets have `nonce=0` and trades are executed by the Polymarket operator on behalf of users. This means scanning raw on-chain logs for a specific wallet address returns nothing useful.

I chose to use the **Polymarket Data API** (`data-api.polymarket.com`) as the data source instead. It returns the same information (trades, deposits, withdrawals, redemptions) in a structured format tied to the actual user wallets. This was a pragmatic decision — I have limited web3 experience and didn't want to go down a rabbit hole debugging proxy wallet RPC edge cases when a clean, reliable API exists that gives the exact same data. The detection algorithm and scoring logic are the same regardless of data source.

If needed, the indexer layer can be swapped to use direct `eth_getLogs` RPC calls (the code structure supports this — indexers are isolated modules behind a clean interface). With a paid RPC provider (Alchemy/Infura) and knowledge of Polymarket's proxy contract internals, on-chain indexing would be straightforward to add.

### No Real-Time Mode (Yet)

The system currently runs in batch/historical mode. Real-time monitoring is not implemented but can be added easily — the codebase is modular and designed with that in mind. The indexer/detector separation means a streaming layer would just need to call the same `index` + `detect` pipeline on new activity as it appears. A polling loop on the data API or a WebSocket listener on new blocks would plug in cleanly.

### REDEEM Events as Win Proof

The Gamma API `resolution` field is often empty for resolved markets. Instead of relying on it, we use REDEEM events from the data API as proof of winning. If `total_redeemed > total_bought`, the wallet profited. This is more reliable in practice.

### closedTime vs endDate

`closedTime` is when a market actually resolved. `endDate` is the market expiry deadline. For entry timing analysis, `closedTime` is what matters — insiders trade right before the actual resolution, not before the deadline.

## Configuration

All scoring weights and thresholds are in `src/config.py` via the `ScoringConfig` Pydantic model. Every parameter is adjustable in one place — signal weights, risk tier boundaries, timing thresholds, size thresholds, etc.

## Known Insider Wallets

| Wallet | Label | Source |
|--------|-------|--------|
| `0xee50a31c3f5a7c77824b12a941a54388a2827ed6` | AlphaRaccoon (Google d4vd) | [x.com](https://x.com/drizzl3r/status/1996434092749914596) |
| `0x6baf05d193692bb208d616709e27442c910a94c5` | SBet365 (Maduro) | [x.com](https://x.com/thejayden/status/2010844183301374290) |
| `0xc51eedc01790252d571648cb4abd8e9876de5202` | hogriddahhhh (Spotify scraper*) | [x.com](https://x.com/PolymarketStory/status/1995933029349634389) |
| `0x31a56e9e690c621ed21de08cb559e9524cdb8ed9` | unnamed (Maduro) | [x.com](https://x.com/Andrey_10gwei/status/2007904168791454011) |
| `0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2` | ricosuave (Israel/Iran) | [x.com](https://x.com/AdameMedia/status/2009011970780037534) |
| `0x7f1329ade2ec162c6f8791dad99125e0dc49801c` | gj1 (Trump pardon CZ) | [x.com](https://x.com/Polysights/status/1977716009797570865) |
| `0x976685b6e867a0400085b1273309e84cd0fc627c` | fromagi (MicroStrategy) | [x.com](https://x.com/Polysights/status/1997753083934204049) |
| `0x55ea982cebff271722419595e0659ef297b48d7c` | flaccidwillie (DraftKings) | [x.com](https://x.com/Polysights/status/1999361742405611964) |

*hogriddahhhh is not a true insider — uses public Spotify data scraping. Correctly scores MEDIUM (0.640), below the HIGH threshold.
