"""Validate detection against known insiders + normal wallet control group.

Run: uv run python validate.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.config import KNOWN_INSIDERS, NORMAL_WALLETS
from src.db import Repository
from src.detection.detector import Detector
from src.models import RiskLevel, Side

console = Console()

# Labels for known wallets
INSIDER_LABELS = {
    "0xee50a31c3f5a7c77824b12a941a54388a2827ed6": "AlphaRaccoon (Google d4vd)",
    "0x6baf05d193692bb208d616709e27442c910a94c5": "SBet365 (Maduro)",
    "0xc51eedc01790252d571648cb4abd8e9876de5202": "hogriddahhhh (Spotify scraper)",
    "0x31a56e9e690c621ed21de08cb559e9524cdb8ed9": "unnamed (Maduro)",
    "0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2": "ricosuave (Israel/Iran)",
    "0x7f1329ade2ec162c6f8791dad99125e0dc49801c": "gj1 (Trump pardon CZ)",
    "0x976685b6e867a0400085b1273309e84cd0fc627c": "fromagi (MicroStrategy)",
    "0x55ea982cebff271722419595e0659ef297b48d7c": "flaccidwillie (DraftKings)",
}


def print_wallet_analysis(wallet: str, label: str, repo: Repository, detector: Detector) -> float:
    """Print detailed analysis for a single wallet. Returns composite score."""
    report = detector.analyze_wallet(wallet)
    trades = repo.get_wallet_trades(wallet)
    deposits = repo.get_wallet_deposits(wallet)

    risk_colors = {
        RiskLevel.CRITICAL: "bold red",
        RiskLevel.HIGH: "red",
        RiskLevel.MEDIUM: "yellow",
        RiskLevel.LOW: "green",
    }
    risk_style = risk_colors.get(report.risk_level, "white")

    # Header
    console.print(Panel(
        f"[bold]{label}[/bold]\n{wallet}",
        title=f"[{risk_style}]{report.risk_level.value}[/{risk_style}] - Score: {report.composite_score:.3f}",
        border_style=risk_style.split()[-1],
    ))

    # Raw activity log (last 10 events)
    console.print("  [dim]Raw Activity Log (most recent trades):[/dim]")
    buy_trades = [t for t in trades if t.side == Side.BUY]
    recent = sorted(buy_trades, key=lambda t: t.timestamp, reverse=True)[:8]
    for t in recent:
        market = repo.get_market_by_token(t.token_id)
        q = market.question[:55] if market else f"token:{t.token_id[:20]}..."
        console.print(
            f"    {t.timestamp.strftime('%Y-%m-%d %H:%M')}  "
            f"[cyan]{t.side.value:4s}[/cyan]  "
            f"${t.amount_usdc:>10,.2f}  "
            f"@{t.price:.4f}  "
            f"{q}"
        )

    # Deposit/redemption log
    if deposits:
        console.print("  [dim]Deposits & Redemptions:[/dim]")
        for d in sorted(deposits, key=lambda x: x.timestamp)[:5]:
            src = d.from_address
            if src == "market_redemption":
                label_d = "[green]REDEEM[/green]"
            elif src == "external":
                label_d = "[blue]DEPOSIT[/blue]"
            else:
                label_d = f"[dim]{src[:10]}...[/dim]"
            console.print(
                f"    {d.timestamp.strftime('%Y-%m-%d %H:%M')}  "
                f"{label_d:>30s}  "
                f"${d.amount_usdc:>10,.2f}"
            )

    # Signal breakdown table
    sig_table = Table(show_header=True, show_lines=False, padding=(0, 1))
    sig_table.add_column("Signal", style="white", min_width=18)
    sig_table.add_column("Score", justify="right", min_width=5)
    sig_table.add_column("Wt", justify="right", min_width=4)
    sig_table.add_column("Wtd", justify="right", min_width=5)
    sig_table.add_column("Key Details", max_width=65)

    for s in report.signals:
        sc = "green" if s.score >= 0.7 else "yellow" if s.score >= 0.4 else "red"
        # Build compact details string
        parts = []
        for k, v in s.details.items():
            if k in ("positions",):
                continue
            if isinstance(v, float):
                parts.append(f"{k}={v:.2f}")
            elif isinstance(v, bool):
                parts.append(f"{k}={'Y' if v else 'N'}")
            else:
                parts.append(f"{k}={v}")
        detail_str = ", ".join(parts)

        sig_table.add_row(
            s.name,
            f"[{sc}]{s.score:.2f}[/{sc}]",
            f"{s.weight:.2f}",
            f"{s.weighted_score:.3f}",
            detail_str[:65],
        )

    console.print(sig_table)
    console.print(
        f"  [bold]Composite: {report.composite_score:.3f}[/bold]  "
        f"Volume: ${report.volume:,.0f}  "
        f"Trades: {report.trade_count}  "
        f"Markets: {report.market_count}\n"
    )

    return report.composite_score


def main() -> None:
    repo = Repository()
    detector = Detector(repo)

    all_indexed = set(repo.get_all_wallets())

    # ---- Insider Analysis ----
    console.print("\n[bold underline]KNOWN INSIDER WALLETS[/bold underline]\n")

    insider_scores: dict[str, float] = {}
    indexed_insiders = [w for w in KNOWN_INSIDERS if w in all_indexed]
    missing_insiders = [w for w in KNOWN_INSIDERS if w not in all_indexed]

    if missing_insiders:
        console.print(f"[yellow]Not indexed ({len(missing_insiders)}):[/yellow]")
        for w in missing_insiders:
            lbl = INSIDER_LABELS.get(w, w[:14] + "...")
            console.print(f"  {lbl}: {w}")
        console.print()

    for w in indexed_insiders:
        label = INSIDER_LABELS.get(w, w[:14] + "...")
        score = print_wallet_analysis(w, label, repo, detector)
        insider_scores[w] = score

    # ---- Normal Wallet Analysis ----
    indexed_normals = [w for w in NORMAL_WALLETS if w in all_indexed]
    normal_scores: dict[str, float] = {}

    if indexed_normals:
        console.print("\n[bold underline]NORMAL WALLETS (Control Group)[/bold underline]\n")

        for w in indexed_normals:
            label = f"Normal: {w[:10]}..."
            score = print_wallet_analysis(w, label, repo, detector)
            normal_scores[w] = score

    # ---- Summary Table ----
    console.print("\n[bold underline]SUMMARY[/bold underline]\n")

    summary = Table(title="All Wallets Ranked by Score", show_lines=True)
    summary.add_column("Type", min_width=8)
    summary.add_column("Label", min_width=25)
    summary.add_column("Score", justify="right")
    summary.add_column("Risk", justify="center")

    all_results = []
    for w, sc in insider_scores.items():
        report = detector.analyze_wallet(w)
        all_results.append(("INSIDER", INSIDER_LABELS.get(w, w[:14]), sc, report.risk_level))
    for w, sc in normal_scores.items():
        report = detector.analyze_wallet(w)
        all_results.append(("NORMAL", w[:14] + "...", sc, report.risk_level))

    all_results.sort(key=lambda x: x[2], reverse=True)

    risk_colors = {
        RiskLevel.CRITICAL: "bold red",
        RiskLevel.HIGH: "red",
        RiskLevel.MEDIUM: "yellow",
        RiskLevel.LOW: "green",
    }

    for typ, label, sc, risk in all_results:
        style = risk_colors.get(risk, "white")
        type_style = "red" if typ == "INSIDER" else "cyan"
        summary.add_row(
            f"[{type_style}]{typ}[/{type_style}]",
            label,
            f"{sc:.3f}",
            f"[{style}]{risk.value}[/{style}]",
        )

    console.print(summary)

    # Stats
    insider_high = sum(1 for s in insider_scores.values() if s >= 0.7)
    normal_high = sum(1 for s in normal_scores.values() if s >= 0.7)
    insider_avg = sum(insider_scores.values()) / len(insider_scores) if insider_scores else 0
    normal_avg = sum(normal_scores.values()) / len(normal_scores) if normal_scores else 0

    stats = Table(show_header=True)
    stats.add_column("Metric", style="bold")
    stats.add_column("Insiders", justify="right")
    stats.add_column("Normals", justify="right")

    stats.add_row("Indexed", str(len(indexed_insiders)), str(len(indexed_normals)))
    stats.add_row("Avg Score", f"{insider_avg:.3f}", f"{normal_avg:.3f}")
    stats.add_row("HIGH+ count", f"{insider_high}", f"{normal_high}")
    stats.add_row(
        "Separation",
        f"[{'green' if insider_avg > normal_avg + 0.1 else 'yellow'}]"
        f"{insider_avg - normal_avg:+.3f}[/]",
        "",
    )

    console.print(stats)

    if insider_avg > normal_avg + 0.1:
        console.print(f"\n[bold green]Algorithm separates insiders from normals by {insider_avg - normal_avg:.3f} points[/bold green]\n")
    else:
        console.print(f"\n[bold yellow]Separation is narrow ({insider_avg - normal_avg:.3f}) — may need tuning[/bold yellow]\n")

    repo.close()


if __name__ == "__main__":
    main()
