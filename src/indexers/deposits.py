"""USDC.e Transfer indexer — uses Polymarket data API for deposit/withdrawal activity."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from src.models import Deposit


DATA_API = "https://data-api.polymarket.com"
PAGE_SIZE = 100


def index_deposits(
    wallets: list[str],
    from_block: int = 0,
    to_block: int = 0,
    batch_size: int = 10_000,
) -> list[Deposit]:
    """Index deposit/withdrawal activity from the Polymarket data API.

    Block params kept for CLI compatibility but unused (API-based).
    """
    all_deposits: list[Deposit] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    ) as progress:
        task = progress.add_task("Indexing deposits...", total=len(wallets))

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
                    if not isinstance(item, dict):
                        continue
                    typ = item.get("type", "")
                    if typ not in ("DEPOSIT", "WITHDRAWAL", "REDEEM", "REWARD"):
                        continue

                    ts = item.get("timestamp", 0)
                    tx_hash = item.get("transactionHash", "")
                    amount = float(item.get("usdcSize", 0) or 0)

                    if typ in ("DEPOSIT", "REWARD"):
                        # Inbound funds
                        all_deposits.append(
                            Deposit(
                                tx_hash=tx_hash,
                                block_number=0,
                                timestamp=datetime.fromtimestamp(ts, tz=timezone.utc),
                                to_address=wallet.lower(),
                                from_address="external",
                                amount_usdc=round(amount, 6),
                            )
                        )
                    elif typ in ("WITHDRAWAL",):
                        # Outbound funds
                        all_deposits.append(
                            Deposit(
                                tx_hash=tx_hash,
                                block_number=0,
                                timestamp=datetime.fromtimestamp(ts, tz=timezone.utc),
                                to_address="external",
                                from_address=wallet.lower(),
                                amount_usdc=round(amount, 6),
                            )
                        )
                    elif typ == "REDEEM":
                        # Winning payout — treated as inbound
                        all_deposits.append(
                            Deposit(
                                tx_hash=tx_hash,
                                block_number=0,
                                timestamp=datetime.fromtimestamp(ts, tz=timezone.utc),
                                to_address=wallet.lower(),
                                from_address="market_redemption",
                                amount_usdc=round(amount, 6),
                            )
                        )

                if len(items) < PAGE_SIZE:
                    break
                offset += PAGE_SIZE

            progress.update(task, advance=1)

    # Deduplicate
    seen: set[tuple[str, str, str]] = set()
    unique: list[Deposit] = []
    for d in all_deposits:
        key = (d.tx_hash, d.to_address, d.from_address)
        if key not in seen:
            seen.add(key)
            unique.append(d)

    return unique
