# Approach: Polymarket Insider Trading Detection

## Problem

Detect insider trading on Polymarket by analyzing wallet behavior. An insider typically: creates a new wallet, drops large amounts on 1-2 markets close to resolution, wins, withdraws, and disappears.

## Data Collection

Polymarket uses proxy wallets — users don't transact directly on-chain (all wallets have `nonce=0`, trades are executed by the Polymarket operator). Direct RPC log scanning for `OrderFilled` events by wallet address returns nothing useful.

I chose to use the **Polymarket Data API** as the data source. It returns the same information (trades, deposits, withdrawals, redemptions) tied to actual user wallets. I have limited web3 experience and prioritized building a working detection system over debugging proxy wallet RPC edge cases. The indexer layer is isolated — it can be swapped to on-chain `eth_getLogs` calls without touching the detection logic.

**Two APIs used:**

1. **Polymarket Data API** (`data-api.polymarket.com/activity?user=WALLET`) — paginated trade history: TRADE, DEPOSIT, WITHDRAWAL, REDEEM events with timestamps, amounts, token IDs.

2. **Gamma API** (`gamma-api.polymarket.com/markets?clob_token_ids=TOKEN`) — market metadata: question, `startDate`, `endDate`, `closedTime` (actual resolution), outcomes, volume. Note: `resolution` field is often empty, so we use REDEEM events as proof of winning instead.

## Signal Design

Six independent behavioral signals, each scoring 0-1:

### 1. Wallet Freshness (0.15)
Gap between first deposit and first trade. < 2h = 1.0, < 24h = 0.7, < 7d = 0.4.

### 2. Outcome Certainty (0.25)
Bought tokens at $0.05-$0.50 (unlikely outcomes), payout ratio >= 2x, and profited (total redeemed > total bought). Strongest signal — buying cheap and winning = foreknowledge.

### 3. Entry Timing (0.20)
Where in the market lifecycle the wallet first traded, using `closedTime` (actual resolution, not `endDate` deadline). Final 5% = 1.0, 15% = 0.7, 30% = 0.4.

### 4. Market Focus (0.15)
Number of unique markets traded. 1 = 1.0, 2 = 0.7, 3 = 0.4. Insiders target specific markets.

### 5. Position Size (0.10)
Max USDC on any single market. >= $10K = 1.0, >= $5K = 0.7, >= $1K = 0.4.

### 6. Surgical Behavior (0.15)
Fund -> bet -> win -> withdraw pattern. Checks chronological ordering, separates external deposits from market redemptions. Full pattern with profit ratio >= 1.5x = 1.0.

## Scoring

```
composite = sum(signal_score * signal_weight)
```

CRITICAL >= 0.85, HIGH >= 0.70, MEDIUM >= 0.50, LOW < 0.50.

Outcome Certainty gets the highest weight (0.25) — buying unlikely outcomes and winning is the most direct evidence of insider knowledge.

## Results

| Type | Wallet | Score | Risk |
|------|--------|-------|------|
| INSIDER | gj1 (Trump pardon CZ) | 0.880 | CRITICAL |
| INSIDER | SBet365 (Maduro) | 0.805 | HIGH |
| INSIDER | ricosuave (Israel/Iran) | 0.760 | HIGH |
| INSIDER | unnamed (Maduro) | 0.708 | HIGH |
| INSIDER | AlphaRaccoon (Google d4vd) | 0.700 | HIGH |
| INSIDER | hogriddahhhh (Spotify scraper) | 0.640 | MEDIUM |
| NORMAL | 10 control wallets | 0.574 avg | MEDIUM |
| INSIDER | flaccidwillie (DraftKings) | 0.505 | MEDIUM |
| INSIDER | fromagi (MicroStrategy) | 0.490 | LOW |

**5/8 insiders HIGH+, 0/10 normals HIGH, +0.112 separation.**

Key differentiators: insiders trade 1-3 markets (MarketFocus 0.7-1.0) vs normals at 50-700+ (0.10). Insiders concentrate $5K-$50K+ per market vs normals spreading thin. Insiders show clear fund->bet->win->redeem chronological patterns.

The Spotify scraper correctly scores MEDIUM — it uses public data, not insider info. `fromagi` and `flaccidwillie` score lower, likely due to different trading patterns or incomplete API data.

## Limitations

- **No real-time mode**: Batch/historical only. The modular architecture (isolated indexers, separate detector) is designed so a streaming layer can be added on top — a polling loop or WebSocket listener would plug into the same pipeline.
- **API vs RPC**: Uses Polymarket data API, not direct on-chain event indexing. Pragmatic tradeoff given proxy wallet architecture.
- **Static thresholds**: Manually tuned. A larger labeled dataset could enable ML-based optimization.
- **No graph analysis**: Wallets analyzed independently. Cross-wallet funding analysis could catch coordinated rings.
- **No market manipulability signal**: We don't assess whether a market's outcome could be influenced by few people.
