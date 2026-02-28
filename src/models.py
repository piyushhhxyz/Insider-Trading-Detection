"""Pydantic v2 models for trades, deposits, markets, and detection results."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, computed_field


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Trade(BaseModel):
    tx_hash: str
    block_number: int
    timestamp: datetime
    wallet: str
    token_id: str
    side: Side
    amount_usdc: float
    amount_tokens: float
    price: float
    fee: float
    exchange: str


class Deposit(BaseModel):
    tx_hash: str
    block_number: int
    timestamp: datetime
    to_address: str
    from_address: str
    amount_usdc: float


class Market(BaseModel):
    condition_id: str
    question: str
    slug: str
    outcomes: list[str]
    outcome_prices: list[float]
    start_date: datetime | None = None
    end_date: datetime | None = None
    closed_time: datetime | None = None
    closed: bool = False
    volume: float = 0.0
    clob_token_ids: list[str] = []
    category: str = ""
    resolution: str = ""


class SignalScore(BaseModel):
    name: str
    score: float  # 0.0 - 1.0
    weight: float
    details: dict[str, object] = {}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def weighted_score(self) -> float:
        return round(self.score * self.weight, 4)


class WalletReport(BaseModel):
    wallet: str
    volume: float
    trade_count: int
    market_count: int
    signals: list[SignalScore]
    composite_score: float
    risk_level: RiskLevel
