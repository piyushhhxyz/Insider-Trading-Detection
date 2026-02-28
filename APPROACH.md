# Approach: Polymarket Insider Trading Detection

## Problem Statement

Detect insider trading on Polymarket by analyzing on-chain behavior of wallets trading on Polygon. Validate against 7 known insider wallets that have been publicly identified.

## Methodology

### Data Collection

We index three categories of on-chain data:

1. **Trades**: `OrderFilled` events from both the CTF Exchange (`0x4bFb...982E`) and NegRisk CTF Exchange (`0xC5d5...f80a`). Each event gives us maker, taker, asset IDs, amounts, and fees.

2. **Deposits/Withdrawals**: `Transfer` events on the USDC.e contract (`0x2791...4174`) to/from target wallets. This captures the funding and exit patterns.

3. **Market Metadata**: Fetched from the Gamma API (`gamma-api.polymarket.com`), linking CLOB token IDs to human-readable market questions, resolution status, end dates, and outcomes.

### Signal Design

We score each wallet on 6 independent behavioral signals, each producing a 0-1 score:

#### 1. Wallet Freshness (weight: 0.15)
**Hypothesis**: Insiders use burner wallets — fresh addresses that receive funding and immediately start trading.

Measures the gap between the first USDC.e deposit and the first trade. A gap of < 2 hours scores 1.0 (critical), < 24 hours scores 0.7, < 7 days scores 0.4.

#### 2. Outcome Certainty (weight: 0.25)
**Hypothesis**: Insiders buy outcome tokens at low prices (high odds against) with conviction, because they know the resolution.

Evaluates whether the wallet bought tokens at prices below $0.50 (implying < 50% market probability), with a payout ratio >= 2x, and whether the outcome actually resolved in their favor. This is the strongest signal — a wallet that repeatedly buys unlikely outcomes and wins is highly suspicious.

#### 3. Entry Timing (weight: 0.20)
**Hypothesis**: Insiders trade in the final days/hours before market resolution, after they've acquired non-public information about the outcome.

Measures where in the market's lifecycle the wallet first traded. Trading in the final 5% of a market's duration scores 1.0, final 15% scores 0.7.

#### 4. Market Focus (weight: 0.15)
**Hypothesis**: Insiders target specific markets where they have information, rather than trading broadly.

A wallet active in only 1 market scores 1.0, 2 markets scores 0.7, 3 markets scores 0.4. Regular traders typically participate in many markets.

#### 5. Position Size (weight: 0.10)
**Hypothesis**: Insiders bet large amounts because they're confident in the outcome.

The max USDC volume on any single market is evaluated. >= $10K scores 1.0, >= $5K scores 0.7, >= $1K scores 0.4.

#### 6. Surgical Behavior (weight: 0.15)
**Hypothesis**: Insiders follow a fund → bet → win → withdraw → disappear pattern. They don't stick around.

Checks for the chronological pattern: deposits arrive, trades happen, withdrawals follow. If >= 80% of the balance is withdrawn after trading, the full pattern scores 1.0.

### Composite Scoring

The composite score is a weighted sum of all 6 signals:

```
composite = Σ (signal_score × signal_weight) for all signals
```

Risk classification:
- **CRITICAL**: >= 0.85
- **HIGH**: >= 0.70
- **MEDIUM**: >= 0.50
- **LOW**: < 0.50

### Weight Rationale

Outcome Certainty receives the highest weight (0.25) because buying cheap tokens on unlikely outcomes and winning is the most direct evidence of foreknowledge. Entry Timing (0.20) is next because trading right before resolution strongly correlates with information leakage. The remaining signals (Freshness, Focus, Surgical, Size) provide supporting behavioral evidence at 0.10-0.15 each.

## Known Insiders (Validation Set)

Seven wallets publicly identified as insider traders on Polymarket:

1. `0xee50a31c3e7a2a4b323adbf78e1a29f843a29b3c`
2. `0x6baf05d1894cde30c5a0afe0b494b5c1e89f4f03`
3. `0x31a56e9e0c0c72138a83e4a1577e1f2db01a44e3`
4. `0x0afc7ce50e61bf63fd839e957adc204d3a614289`
5. `0x7f1329ad79c9868ce0c1a632fbe9d52b301a43f1`
6. `0x976685b62369b48ebd8aa0da5e89e3645dfab98b`
7. `0x55ea982c3ab01e05c73fee51e53d20a37e8c27f6`

The validation target is that all 7 should score >= 0.70 (HIGH risk).

## Limitations

1. **RPC dependency**: Indexing requires a Polygon RPC endpoint. Public RPCs may rate-limit or return incomplete data for large block ranges.

2. **Market start approximation**: We don't have exact market creation timestamps, so entry timing uses the earliest known trade as a proxy for market start.

3. **Resolution data**: The Gamma API may not always return resolution status for all markets, which affects the Outcome Certainty signal's ability to confirm wins.

4. **Single-chain**: Only tracks USDC.e on Polygon. Insiders could fund via bridging or other tokens not captured by our Transfer event indexing.

5. **Static thresholds**: The scoring parameters are manually tuned. A larger dataset could enable data-driven threshold optimization.

6. **No social/off-chain signals**: This is purely on-chain behavioral analysis. Combining with off-chain data (social media, market maker relationships) could improve accuracy.

## Future Improvements

- **Batch RPC calls** via `eth_getLogs` with multiple address filters to reduce RPC calls
- **Incremental indexing** — track last indexed block and resume from there
- **Graph analysis** — trace funding sources across multiple hops to link related wallets
- **ML scoring** — train a classifier on the feature set using known insiders as positive labels
- **Real-time monitoring** — stream new blocks and flag suspicious wallets as they trade
