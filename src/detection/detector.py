"""Orchestrator — runs all signals on a wallet and produces a WalletReport."""

from __future__ import annotations

from src.db import Repository
from src.detection.scorer import classify_risk, composite_score
from src.detection.signals import ALL_SIGNALS
from src.models import Side, WalletReport


class Detector:
    """Run all detection signals on wallets and produce risk reports."""

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def analyze_wallet(self, wallet: str) -> WalletReport:
        trades = self.repo.get_wallet_trades(wallet)

        # Compute summary stats
        volume = sum(t.amount_usdc for t in trades if t.side == Side.BUY)
        trade_count = len(trades)

        # Count unique markets
        unique_markets: set[str] = set()
        for t in trades:
            market = self.repo.get_market_by_token(t.token_id)
            if market:
                unique_markets.add(market.condition_id)
        market_count = len(unique_markets) or len({t.token_id for t in trades})

        # Run all signals
        signals = [s.evaluate(wallet, self.repo) for s in ALL_SIGNALS]

        score = composite_score(signals)
        risk = classify_risk(score)

        return WalletReport(
            wallet=wallet,
            volume=round(volume, 2),
            trade_count=trade_count,
            market_count=market_count,
            signals=signals,
            composite_score=score,
            risk_level=risk,
        )

    def analyze_all(self) -> list[WalletReport]:
        """Analyze every wallet in the database."""
        wallets = self.repo.get_all_wallets()
        return [self.analyze_wallet(w) for w in wallets]
