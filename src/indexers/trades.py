"""Trade indexer using Polymarket data API (primary) with RPC fallback."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from src.models import Side, Trade


DATA_API = "https://data-api.polymarket.com"
PAGE_SIZE = 100  # max per request


def _parse_api_trade(item: dict, wallet: str) -> Trade | None:
    """Parse a single trade record from the Polymarket data API."""
    if item.get("type") != "TRADE":
        return None

    side_str = item.get("side", "").upper()
    if side_str not in ("BUY", "SELL"):
        return None

    ts = item.get("timestamp", 0)
    return Trade(
        tx_hash=item.get("transactionHash", ""),
        block_number=0,  # API doesn't return block numbers
        timestamp=datetime.fromtimestamp(ts, tz=timezone.utc),
        wallet=wallet.lower(),
        token_id=str(item.get("asset", "")),
        side=Side(side_str),
        amount_usdc=round(float(item.get("usdcSize", 0)), 6),
        amount_tokens=round(float(item.get("size", 0)), 6),
        price=round(float(item.get("price", 0)), 6),
        fee=0.0,  # API doesn't break out fees
        exchange="polymarket",
    )


def index_trades_api(wallets: list[str]) -> list[Trade]:
    """Index all trades for wallets via the Polymarket data API."""
    all_trades: list[Trade] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    ) as progress:
        task = progress.add_task("Indexing trades...", total=len(wallets))

        for wallet in wallets:
            offset = 0
            while True:
                try:
                    resp = httpx.get(
                        f"{DATA_API}/activity",
                        params={"user": wallet, "limit": PAGE_SIZE, "offset": offset},
                        timeout=30,
                    )
                    resp.raise_for_status()
                    items = resp.json()
                except (httpx.HTTPError, ValueError):
                    break

                if not items or not isinstance(items, list):
                    break

                for item in items:
                    if isinstance(item, dict):
                        trade = _parse_api_trade(item, wallet)
                        if trade:
                            all_trades.append(trade)

                if len(items) < PAGE_SIZE:
                    break
                offset += PAGE_SIZE

            progress.update(task, advance=1)

    # Deduplicate by tx_hash + wallet + token_id + side
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[Trade] = []
    for t in all_trades:
        key = (t.tx_hash, t.wallet, t.token_id, t.side.value)
        if key not in seen:
            seen.add(key)
            unique.append(t)

    return unique


# Keep the RPC-based indexer available as fallback
def index_trades(
    wallets: list[str],
    from_block: int = 0,
    to_block: int = 0,
    batch_size: int = 10_000,
) -> list[Trade]:
    """Index trades. Uses data API (fast). Block params ignored but kept for CLI compat."""
    return index_trades_api(wallets)
