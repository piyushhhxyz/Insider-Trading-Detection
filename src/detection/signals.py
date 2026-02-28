"""Six behavioral signals for insider trading detection (Strategy pattern)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import timedelta

from src.config import SCORING
from src.db import Repository
from src.models import Side, SignalScore


class Signal(ABC):
    """Base class — each signal evaluates a wallet and returns a SignalScore."""

    @abstractmethod
    def evaluate(self, wallet: str, repo: Repository) -> SignalScore: ...


class WalletFreshness(Signal):
    """Deposit-to-trade gap. Burner wallets fund and trade within hours."""

    def evaluate(self, wallet: str, repo: Repository) -> SignalScore:
        deposits = repo.get_wallet_deposits(wallet)
        trades = repo.get_wallet_trades(wallet)

        if not deposits or not trades:
            return SignalScore(
                name="WalletFreshness",
                score=0.0,
                weight=SCORING.wallet_freshness_weight,
                details={"reason": "no deposits or trades found"},
            )

        # Only consider external deposits (not market redemptions)
        external_deposits = [
            d for d in deposits if d.from_address != "market_redemption"
        ]

        if not external_deposits:
            # No external deposits but has trades → funded via bridge/other token
            # This is suspicious (score high)
            return SignalScore(
                name="WalletFreshness",
                score=0.7,
                weight=SCORING.wallet_freshness_weight,
                details={"reason": "no external deposits found, likely bridge-funded"},
            )

        first_deposit = min(d.timestamp for d in external_deposits)
        first_trade = min(t.timestamp for t in trades)
        gap_hours = (first_trade - first_deposit).total_seconds() / 3600

        if gap_hours < 0:
            # Trade before deposit — funded via a different mechanism
            gap_hours = 0

        if gap_hours <= SCORING.freshness_hours_critical:
            score = 1.0
        elif gap_hours <= SCORING.freshness_hours_suspicious:
            score = 0.7
        elif gap_hours <= SCORING.freshness_hours_moderate:
            score = 0.4
        else:
            score = 0.1

        return SignalScore(
            name="WalletFreshness",
            score=score,
            weight=SCORING.wallet_freshness_weight,
            details={
                "first_deposit": first_deposit.isoformat(),
                "first_trade": first_trade.isoformat(),
                "gap_hours": round(gap_hours, 2),
            },
        )


class OutcomeCertainty(Signal):
    """Bought at low odds, bet big, and won. Suggests foreknowledge.

    Uses REDEEM events as proof of winning (since Gamma API doesn't expose resolution).
    """

    def evaluate(self, wallet: str, repo: Repository) -> SignalScore:
        trades = repo.get_wallet_trades(wallet)
        deposits = repo.get_wallet_deposits(wallet)
        if not trades:
            return SignalScore(
                name="OutcomeCertainty",
                score=0.0,
                weight=SCORING.outcome_certainty_weight,
                details={"reason": "no trades"},
            )

        # REDEEM events prove the wallet won on that market
        # Redemption amounts > buy amounts = profitable win
        redemptions = [d for d in deposits if d.from_address == "market_redemption"]
        total_redeemed = sum(r.amount_usdc for r in redemptions)

        # Group BUY trades by token_id
        buys_by_token: dict[str, list] = defaultdict(list)
        for t in trades:
            if t.side == Side.BUY:
                buys_by_token[t.token_id].append(t)

        if not buys_by_token:
            return SignalScore(
                name="OutcomeCertainty",
                score=0.0,
                weight=SCORING.outcome_certainty_weight,
                details={"reason": "no buy trades"},
            )

        certainty_scores: list[float] = []
        details_list: list[dict] = []

        total_bought = sum(t.amount_usdc for t in trades if t.side == Side.BUY)
        # If total redeemed > total bought, the wallet profited overall
        has_profitable_redemptions = total_redeemed > total_bought

        for token_id, buy_trades in buys_by_token.items():
            avg_price = sum(t.price for t in buy_trades) / len(buy_trades)
            total_usdc = sum(t.amount_usdc for t in buy_trades)

            bought_cheap = (
                SCORING.certainty_min_price <= avg_price <= SCORING.certainty_max_price
            )
            potential_payout_ratio = (1.0 / avg_price) if avg_price > 0 else 0.0

            # If we have redemptions and the wallet was profitable, treat as "won"
            won = has_profitable_redemptions

            if won and bought_cheap and potential_payout_ratio >= SCORING.certainty_min_payout_ratio:
                certainty_scores.append(1.0)
            elif bought_cheap and potential_payout_ratio >= SCORING.certainty_min_payout_ratio:
                certainty_scores.append(0.7)
            elif bought_cheap:
                certainty_scores.append(0.4)
            else:
                certainty_scores.append(0.1)

            details_list.append({
                "token_id": token_id[:16] + "...",
                "avg_price": round(avg_price, 4),
                "total_usdc": round(total_usdc, 2),
                "won": won,
                "payout_ratio": round(potential_payout_ratio, 2),
            })

        final_score = max(certainty_scores) if certainty_scores else 0.0

        return SignalScore(
            name="OutcomeCertainty",
            score=final_score,
            weight=SCORING.outcome_certainty_weight,
            details={
                "total_bought": round(total_bought, 2),
                "total_redeemed": round(total_redeemed, 2),
                "profitable": has_profitable_redemptions,
                "positions_count": len(details_list),
            },
        )


class EntryTiming(Signal):
    """Traded in the final percentage of market lifecycle. Waited for info.

    Uses market start_date and end_date from Gamma API.
    Falls back to 30 days before end_date if start_date unavailable.
    """

    def evaluate(self, wallet: str, repo: Repository) -> SignalScore:
        trades = repo.get_wallet_trades(wallet)
        if not trades:
            return SignalScore(
                name="EntryTiming",
                score=0.0,
                weight=SCORING.entry_timing_weight,
                details={"reason": "no trades"},
            )

        timing_scores: list[float] = []

        # Check timing per unique market
        token_ids = {t.token_id for t in trades}
        for token_id in token_ids:
            market = repo.get_market_by_token(token_id)
            if not market or not market.end_date:
                continue

            token_trades = [t for t in trades if t.token_id == token_id and t.side == Side.BUY]
            if not token_trades:
                continue

            first_trade_dt = min(t.timestamp for t in token_trades)

            # Use real start_date from Gamma API, fall back to 30d estimate
            if market.start_date:
                market_start = market.start_date
            else:
                market_start = market.end_date - timedelta(days=30)

            # Use closed_time (actual resolution) if available, else end_date
            resolution_time = market.closed_time or market.end_date

            market_duration = (resolution_time - market_start).total_seconds()
            time_before_end = (resolution_time - first_trade_dt).total_seconds()

            if market_duration <= 0 or time_before_end < 0:
                continue

            pct_remaining = time_before_end / market_duration

            if pct_remaining <= SCORING.timing_final_pct_critical:
                timing_scores.append(1.0)
            elif pct_remaining <= SCORING.timing_final_pct_suspicious:
                timing_scores.append(0.7)
            elif pct_remaining <= SCORING.timing_final_pct_moderate:
                timing_scores.append(0.4)
            else:
                timing_scores.append(0.1)

        final_score = max(timing_scores) if timing_scores else 0.0

        return SignalScore(
            name="EntryTiming",
            score=final_score,
            weight=SCORING.entry_timing_weight,
            details={"markets_evaluated": len(timing_scores)},
        )


class MarketFocus(Signal):
    """Only traded in 1-2 markets. Targeted insider knowledge."""

    def evaluate(self, wallet: str, repo: Repository) -> SignalScore:
        trades = repo.get_wallet_trades(wallet)
        if not trades:
            return SignalScore(
                name="MarketFocus",
                score=0.0,
                weight=SCORING.market_focus_weight,
                details={"reason": "no trades"},
            )

        # Count unique markets (condition_ids) via token→market mapping
        unique_markets: set[str] = set()
        unmapped_tokens: set[str] = set()
        for token_id in {t.token_id for t in trades}:
            market = repo.get_market_by_token(token_id)
            if market:
                unique_markets.add(market.condition_id)
            else:
                unmapped_tokens.add(token_id)

        # If we can't map tokens, count unique token_ids as proxy
        n_markets = len(unique_markets) or len(unmapped_tokens)

        if n_markets <= 1:
            score = SCORING.focus_single_market_score
        elif n_markets == 2:
            score = SCORING.focus_two_markets_score
        elif n_markets == 3:
            score = SCORING.focus_three_markets_score
        else:
            score = max(0.1, 1.0 - (n_markets - 1) * 0.15)

        return SignalScore(
            name="MarketFocus",
            score=score,
            weight=SCORING.market_focus_weight,
            details={"unique_markets": n_markets},
        )


class PositionSize(Signal):
    """Large USDC volume concentrated on few markets."""

    def evaluate(self, wallet: str, repo: Repository) -> SignalScore:
        trades = repo.get_wallet_trades(wallet)
        if not trades:
            return SignalScore(
                name="PositionSize",
                score=0.0,
                weight=SCORING.position_size_weight,
                details={"reason": "no trades"},
            )

        # Total USDC volume across BUY trades
        buy_trades = [t for t in trades if t.side == Side.BUY]
        total_volume = sum(t.amount_usdc for t in buy_trades)

        # Max volume per market
        volume_by_token: dict[str, float] = defaultdict(float)
        for t in buy_trades:
            volume_by_token[t.token_id] += t.amount_usdc
        max_market_volume = max(volume_by_token.values()) if volume_by_token else 0

        if max_market_volume >= SCORING.size_large_usd:
            score = 1.0
        elif max_market_volume >= SCORING.size_medium_usd:
            score = 0.7
        elif max_market_volume >= SCORING.size_small_usd:
            score = 0.4
        else:
            score = 0.1

        return SignalScore(
            name="PositionSize",
            score=score,
            weight=SCORING.position_size_weight,
            details={
                "total_buy_volume": round(total_volume, 2),
                "max_single_market_volume": round(max_market_volume, 2),
            },
        )


class SurgicalBehavior(Signal):
    """Fund -> bet -> win -> withdraw -> disappear. Classic insider pattern.

    Separates external deposits from market redemptions to check the real pattern.
    """

    def evaluate(self, wallet: str, repo: Repository) -> SignalScore:
        deposits = repo.get_wallet_deposits(wallet)
        withdrawals = repo.get_wallet_withdrawals(wallet)
        trades = repo.get_wallet_trades(wallet)

        if not trades:
            return SignalScore(
                name="SurgicalBehavior",
                score=0.0,
                weight=SCORING.surgical_behavior_weight,
                details={"reason": "no trades"},
            )

        # Separate external deposits from redemptions
        external_deposits = [d for d in deposits if d.from_address not in ("market_redemption",)]
        redemptions = [d for d in deposits if d.from_address == "market_redemption"]

        has_funding = len(external_deposits) > 0
        has_trades = len(trades) > 0
        has_redemptions = len(redemptions) > 0
        has_withdrawals = len(withdrawals) > 0

        total_funded = sum(d.amount_usdc for d in external_deposits)
        total_redeemed = sum(r.amount_usdc for r in redemptions)
        total_withdrawn = sum(w.amount_usdc for w in withdrawals)
        total_bought = sum(t.amount_usdc for t in trades if t.side == Side.BUY)

        # Check chronological pattern: fund → trade → redeem
        chronological = False
        if has_trades:
            first_trade = min(t.timestamp for t in trades)
            last_trade = max(t.timestamp for t in trades)

            if has_funding:
                first_fund = min(d.timestamp for d in external_deposits)
                # Funding should come before or around the same time as trading
                chronological = first_fund <= first_trade + timedelta(hours=24)
            else:
                # No explicit deposit tracked but trades exist — still counts
                chronological = True

            if chronological and has_redemptions:
                first_redeem = min(r.timestamp for r in redemptions)
                # Redemptions should come after trading
                chronological = first_redeem >= last_trade

        # Profitability: redeemed more than spent
        profitable = total_redeemed > total_bought if total_bought > 0 else False
        profit_ratio = total_redeemed / total_bought if total_bought > 0 else 0

        # The full surgical pattern: fund → bet → win big → cash out
        if has_trades and has_redemptions and chronological and profitable and profit_ratio >= 1.5:
            score = SCORING.surgical_full_pattern_score
        elif has_trades and has_redemptions and profitable:
            score = SCORING.surgical_partial_pattern_score
        elif has_trades and has_redemptions:
            score = 0.4
        elif has_trades:
            score = 0.3
        else:
            score = 0.0

        return SignalScore(
            name="SurgicalBehavior",
            score=score,
            weight=SCORING.surgical_behavior_weight,
            details={
                "has_funding": has_funding,
                "has_redemptions": has_redemptions,
                "has_withdrawals": has_withdrawals,
                "chronological": chronological,
                "total_funded": round(total_funded, 2),
                "total_bought": round(total_bought, 2),
                "total_redeemed": round(total_redeemed, 2),
                "profit_ratio": round(profit_ratio, 2),
            },
        )


# All signals in evaluation order
ALL_SIGNALS: list[Signal] = [
    WalletFreshness(),
    OutcomeCertainty(),
    EntryTiming(),
    MarketFocus(),
    PositionSize(),
    SurgicalBehavior(),
]
