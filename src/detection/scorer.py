"""Weighted composite scorer — turns signal scores into a risk classification."""

from __future__ import annotations

from src.config import SCORING
from src.models import RiskLevel, SignalScore


def composite_score(signals: list[SignalScore]) -> float:
    """Weighted sum of all signal scores, clamped to [0, 1]."""
    total = sum(s.weighted_score for s in signals)
    return round(min(1.0, max(0.0, total)), 4)


def classify_risk(score: float) -> RiskLevel:
    if score >= SCORING.critical_threshold:
        return RiskLevel.CRITICAL
    elif score >= SCORING.high_threshold:
        return RiskLevel.HIGH
    elif score >= SCORING.medium_threshold:
        return RiskLevel.MEDIUM
    else:
        return RiskLevel.LOW
