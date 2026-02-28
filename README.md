# Polymarket Insider Trade Detection

On-chain behavioral analysis to detect insider trading on Polymarket prediction markets.

## Setup

```bash
# Install uv (if not already)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Configure RPC endpoint
cp .env.example .env
# Edit .env with your Polygon RPC URL (Alchemy/Infura recommended)
```

## Usage

### 1. Index on-chain data

```bash
uv run python -m src.main index \
  --wallets 0xee50a31c3e7a2a4b323adbf78e1a29f843a29b3c,0x6baf05d1894cde30c5a0afe0b494b5c1e89f4f03 \
  --from-block 55000000 \
  --to-block 67000000
```

This queries Polygon for:
- **OrderFilled** events from both CTF Exchange and NegRisk CTF Exchange
- **USDC.e Transfer** events (deposits and withdrawals)
- **Market metadata** from the Gamma API

All data is stored in a local SQLite database (`insider_trades.db`).

### 2. Run detection

```bash
# Analyze specific wallets
uv run python -m src.main detect --wallets 0xee50a31c...

# Analyze all indexed wallets
uv run python -m src.main detect --all
```

### 3. Validate against known insiders

```bash
uv run python validate.py
```

Runs all 7 known insider wallets through the detection pipeline and checks each scores >= 0.7 (HIGH risk).

## Detection Signals

| # | Signal | Weight | What It Detects |
|---|--------|--------|-----------------|
| 1 | WalletFreshness | 0.15 | Deposit-to-trade gap < hours = burner wallet |
| 2 | OutcomeCertainty | 0.25 | Bought at low odds, bet big, won = had info |
| 3 | EntryTiming | 0.20 | Traded in final % of market lifecycle |
| 4 | MarketFocus | 0.15 | Only 1-2 markets = targeted knowledge |
| 5 | PositionSize | 0.10 | Large USDC volume on few markets |
| 6 | SurgicalBehavior | 0.15 | Fund -> bet -> win -> withdraw -> disappear |

Composite score = weighted sum of all signals. Risk levels: LOW (< 0.5), MEDIUM (0.5-0.7), HIGH (0.7-0.85), CRITICAL (>= 0.85).

## Architecture

```
src/
├── config.py              # Constants, ABIs, ScoringConfig
├── models.py              # Pydantic v2 models
├── db.py                  # SQLite repository
├── indexers/
│   ├── trades.py          # OrderFilled event indexer
│   ├── deposits.py        # USDC.e Transfer indexer
│   └── markets.py         # Gamma API market fetcher
├── detection/
│   ├── signals.py         # 6 behavioral signals
│   ├── scorer.py          # Weighted composite scorer
│   └── detector.py        # Orchestrator
└── main.py                # CLI entrypoint
```

## Configuration

All scoring weights and thresholds are in `src/config.py` via the `ScoringConfig` model. Adjust weights, tier boundaries, and signal parameters in one place.
