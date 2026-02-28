"""CLI entrypoint: index on-chain data and run insider detection."""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.table import Table

from src.config import KNOWN_INSIDERS
from src.db import Repository
from src.detection.detector import Detector
from src.indexers.deposits import index_deposits
from src.indexers.markets import index_markets
from src.indexers.trades import index_trades
from src.models import RiskLevel

console = Console()


def cmd_index(args: argparse.Namespace) -> None:
    """Index trades, deposits, and market metadata for given wallets."""
    wallets = [w.strip().lower() for w in args.wallets.split(",")]

    console.print(f"\n[bold]Indexing {len(wallets)} wallet(s)...[/bold]\n")

    repo = Repository()

    # 1. Index trades
    console.print("[bold cyan]Step 1/3:[/bold cyan] Indexing trades...")
    trades = index_trades(wallets)
    inserted = repo.insert_trades(trades)
    console.print(f"  Found {len(trades)} trades, inserted {inserted} new\n")

    # 2. Index deposits / withdrawals
    console.print("[bold cyan]Step 2/3:[/bold cyan] Indexing deposits & withdrawals...")
    deposits = index_deposits(wallets)
    inserted = repo.insert_deposits(deposits)
    console.print(f"  Found {len(deposits)} transfers, inserted {inserted} new\n")

    # 3. Fetch market metadata for all unique token_ids
    console.print("[bold cyan]Step 3/3:[/bold cyan] Fetching market metadata...")
    token_ids = repo.get_unique_token_ids()
    already_mapped = repo.get_mapped_token_ids()
    markets = index_markets(token_ids, already_mapped)
    for market in markets:
        repo.upsert_market(market)
        for tid in market.clob_token_ids:
            repo.insert_token_market_mapping(tid, market.condition_id)
    console.print(f"  Fetched {len(markets)} new market(s)\n")

    repo.close()
    console.print("[bold green]Indexing complete.[/bold green]\n")


def cmd_detect(args: argparse.Namespace) -> None:
    """Run detection on all indexed wallets (or specified ones)."""
    repo = Repository()
    detector = Detector(repo)

    if args.wallets:
        wallets = [w.strip().lower() for w in args.wallets.split(",")]
    elif args.all:
        wallets = repo.get_all_wallets()
    else:
        console.print("[red]Specify --wallets or --all[/red]")
        sys.exit(1)

    if not wallets:
        console.print("[yellow]No wallets found in database. Run 'index' first.[/yellow]")
        sys.exit(1)

    console.print(f"\n[bold]Analyzing {len(wallets)} wallet(s)...[/bold]\n")

    reports = [detector.analyze_wallet(w) for w in wallets]

    # Sort by composite score descending
    reports.sort(key=lambda r: r.composite_score, reverse=True)

    # Summary table
    table = Table(title="Insider Detection Results", show_lines=True)
    table.add_column("Wallet", style="cyan", max_width=14)
    table.add_column("Score", justify="right")
    table.add_column("Risk", justify="center")
    table.add_column("Volume", justify="right")
    table.add_column("Trades", justify="right")
    table.add_column("Markets", justify="right")
    table.add_column("Fresh", justify="right")
    table.add_column("Cert", justify="right")
    table.add_column("Timing", justify="right")
    table.add_column("Focus", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("Surg", justify="right")

    risk_colors = {
        RiskLevel.CRITICAL: "bold red",
        RiskLevel.HIGH: "red",
        RiskLevel.MEDIUM: "yellow",
        RiskLevel.LOW: "green",
    }

    for r in reports:
        risk_style = risk_colors.get(r.risk_level, "white")
        signal_scores = {s.name: s.score for s in r.signals}

        table.add_row(
            r.wallet[:6] + "..." + r.wallet[-4:],
            f"{r.composite_score:.3f}",
            f"[{risk_style}]{r.risk_level.value}[/{risk_style}]",
            f"${r.volume:,.0f}",
            str(r.trade_count),
            str(r.market_count),
            f"{signal_scores.get('WalletFreshness', 0):.2f}",
            f"{signal_scores.get('OutcomeCertainty', 0):.2f}",
            f"{signal_scores.get('EntryTiming', 0):.2f}",
            f"{signal_scores.get('MarketFocus', 0):.2f}",
            f"{signal_scores.get('PositionSize', 0):.2f}",
            f"{signal_scores.get('SurgicalBehavior', 0):.2f}",
        )

    console.print(table)
    console.print()

    repo.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="insider-detect",
        description="Polymarket insider trading detection",
    )
    sub = parser.add_subparsers(dest="command")

    # index subcommand
    idx = sub.add_parser("index", help="Index trades, deposits, and markets via Polymarket API")
    idx.add_argument("--wallets", required=True, help="Comma-separated wallet addresses")

    # detect subcommand
    det = sub.add_parser("detect", help="Run insider detection on indexed wallets")
    det.add_argument("--wallets", help="Comma-separated wallets (or use --all)")
    det.add_argument("--all", action="store_true", help="Analyze all indexed wallets")

    args = parser.parse_args()

    if args.command == "index":
        cmd_index(args)
    elif args.command == "detect":
        cmd_detect(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
