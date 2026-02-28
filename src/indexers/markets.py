"""Gamma API market metadata fetcher."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from src.config import GAMMA_API_URL
from src.models import Market


def _parse_market(data: dict) -> Market:
    """Parse a single market dict from the Gamma API response."""
    # Parse end date
    end_date = None
    if data.get("endDate"):
        try:
            end_date = datetime.fromisoformat(
                data["endDate"].replace("Z", "+00:00")
            )
        except (ValueError, TypeError):
            pass

    # Parse outcome prices
    outcome_prices: list[float] = []
    if data.get("outcomePrices"):
        try:
            if isinstance(data["outcomePrices"], str):
                import json
                outcome_prices = [float(p) for p in json.loads(data["outcomePrices"])]
            elif isinstance(data["outcomePrices"], list):
                outcome_prices = [float(p) for p in data["outcomePrices"]]
        except (ValueError, TypeError):
            pass

    # Parse outcomes
    outcomes: list[str] = []
    if data.get("outcomes"):
        if isinstance(data["outcomes"], str):
            import json
            try:
                outcomes = json.loads(data["outcomes"])
            except (ValueError, TypeError):
                outcomes = [data["outcomes"]]
        elif isinstance(data["outcomes"], list):
            outcomes = [str(o) for o in data["outcomes"]]

    # Parse CLOB token IDs
    clob_token_ids: list[str] = []
    if data.get("clobTokenIds"):
        if isinstance(data["clobTokenIds"], str):
            import json
            try:
                clob_token_ids = json.loads(data["clobTokenIds"])
            except (ValueError, TypeError):
                clob_token_ids = [data["clobTokenIds"]]
        elif isinstance(data["clobTokenIds"], list):
            clob_token_ids = [str(t) for t in data["clobTokenIds"]]

    # Parse start date (use startDate, then createdAt as fallback)
    start_date = None
    for field in ("startDate", "createdAt"):
        if data.get(field):
            try:
                start_date = datetime.fromisoformat(
                    data[field].replace("Z", "+00:00")
                )
                break
            except (ValueError, TypeError):
                pass

    # Parse closedTime (actual resolution time, often before endDate)
    closed_time = None
    if data.get("closedTime"):
        try:
            ct = data["closedTime"].replace("Z", "+00:00")
            # Handle postgres-style timestamps: "2026-01-03 12:14:07+00"
            if "T" not in ct:
                ct = ct.replace(" ", "T")
            closed_time = datetime.fromisoformat(ct)
        except (ValueError, TypeError):
            pass

    return Market(
        condition_id=data.get("conditionId", data.get("condition_id", "")),
        question=data.get("question", ""),
        slug=data.get("slug", ""),
        outcomes=outcomes,
        outcome_prices=outcome_prices,
        start_date=start_date,
        end_date=end_date,
        closed_time=closed_time,
        closed=bool(data.get("closed", False)),
        volume=float(data.get("volume", 0) or 0),
        clob_token_ids=clob_token_ids,
        category=data.get("category", "") or "",
        resolution=data.get("resolution", "") or "",
    )


def fetch_market_by_token(token_id: str) -> Market | None:
    """Fetch market data from Gamma API for a given CLOB token ID."""
    url = f"{GAMMA_API_URL}/markets"
    try:
        resp = httpx.get(url, params={"clob_token_ids": token_id}, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if not data:
            return None

        # API returns a list; take the first matching market
        market_data = data[0] if isinstance(data, list) else data
        return _parse_market(market_data)

    except (httpx.HTTPError, KeyError, IndexError):
        return None


def index_markets(token_ids: list[str], already_mapped: set[str] | None = None) -> list[Market]:
    """Fetch market metadata for all token IDs not yet mapped."""
    skip = already_mapped or set()
    to_fetch = [t for t in token_ids if t not in skip]

    if not to_fetch:
        return []

    markets: list[Market] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    ) as progress:
        task = progress.add_task("Fetching markets...", total=len(to_fetch))

        for token_id in to_fetch:
            market = fetch_market_by_token(token_id)
            if market:
                markets.append(market)
            progress.update(task, advance=1)

    return markets
