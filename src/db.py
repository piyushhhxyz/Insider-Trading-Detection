"""SQLite schema and Repository class for persisting indexed data."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.config import DB_PATH
from src.models import Deposit, Market, Trade, Side


SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    tx_hash       TEXT NOT NULL,
    block_number  INTEGER NOT NULL,
    timestamp     TEXT NOT NULL,
    wallet        TEXT NOT NULL,
    token_id      TEXT NOT NULL,
    side          TEXT NOT NULL,
    amount_usdc   REAL NOT NULL,
    amount_tokens REAL NOT NULL,
    price         REAL NOT NULL,
    fee           REAL NOT NULL,
    exchange      TEXT NOT NULL,
    PRIMARY KEY (tx_hash, wallet, token_id, side)
);

CREATE INDEX IF NOT EXISTS idx_trades_wallet ON trades(wallet);
CREATE INDEX IF NOT EXISTS idx_trades_token  ON trades(token_id);

CREATE TABLE IF NOT EXISTS deposits (
    tx_hash       TEXT NOT NULL,
    block_number  INTEGER NOT NULL,
    timestamp     TEXT NOT NULL,
    to_address    TEXT NOT NULL,
    from_address  TEXT NOT NULL,
    amount_usdc   REAL NOT NULL,
    PRIMARY KEY (tx_hash, to_address, from_address)
);

CREATE INDEX IF NOT EXISTS idx_deposits_to   ON deposits(to_address);
CREATE INDEX IF NOT EXISTS idx_deposits_from ON deposits(from_address);

CREATE TABLE IF NOT EXISTS markets (
    condition_id    TEXT PRIMARY KEY,
    question        TEXT NOT NULL,
    slug            TEXT NOT NULL DEFAULT '',
    outcomes        TEXT NOT NULL DEFAULT '[]',
    outcome_prices  TEXT NOT NULL DEFAULT '[]',
    start_date      TEXT,
    end_date        TEXT,
    closed_time     TEXT,
    closed          INTEGER NOT NULL DEFAULT 0,
    volume          REAL NOT NULL DEFAULT 0,
    clob_token_ids  TEXT NOT NULL DEFAULT '[]',
    category        TEXT NOT NULL DEFAULT '',
    resolution      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS token_market_map (
    token_id      TEXT PRIMARY KEY,
    condition_id  TEXT NOT NULL,
    FOREIGN KEY (condition_id) REFERENCES markets(condition_id)
);
"""


def _parse_dt(s: str) -> datetime:
    """Parse an ISO-format timestamp string to a timezone-aware datetime."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class Repository:
    """Thin wrapper around raw sqlite3 for typed reads/writes."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = str(db_path or DB_PATH)
        self._conn = sqlite3.connect(self._path)
        self._conn.executescript(SCHEMA)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    # ---- writes ----

    def insert_trades(self, trades: list[Trade]) -> int:
        """Insert trades, ignoring duplicates. Returns count inserted."""
        cur = self._conn.executemany(
            """INSERT OR IGNORE INTO trades
               (tx_hash, block_number, timestamp, wallet, token_id,
                side, amount_usdc, amount_tokens, price, fee, exchange)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    t.tx_hash,
                    t.block_number,
                    t.timestamp.isoformat(),
                    t.wallet.lower(),
                    t.token_id,
                    t.side.value,
                    t.amount_usdc,
                    t.amount_tokens,
                    t.price,
                    t.fee,
                    t.exchange,
                )
                for t in trades
            ],
        )
        self._conn.commit()
        return cur.rowcount

    def insert_deposits(self, deposits: list[Deposit]) -> int:
        cur = self._conn.executemany(
            """INSERT OR IGNORE INTO deposits
               (tx_hash, block_number, timestamp, to_address, from_address, amount_usdc)
               VALUES (?,?,?,?,?,?)""",
            [
                (
                    d.tx_hash,
                    d.block_number,
                    d.timestamp.isoformat(),
                    d.to_address.lower(),
                    d.from_address.lower(),
                    d.amount_usdc,
                )
                for d in deposits
            ],
        )
        self._conn.commit()
        return cur.rowcount

    def upsert_market(self, market: Market) -> None:
        import json

        self._conn.execute(
            """INSERT INTO markets
               (condition_id, question, slug, outcomes, outcome_prices,
                start_date, end_date, closed_time, closed, volume,
                clob_token_ids, category, resolution)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(condition_id) DO UPDATE SET
                 question=excluded.question, slug=excluded.slug,
                 outcomes=excluded.outcomes, outcome_prices=excluded.outcome_prices,
                 start_date=excluded.start_date, end_date=excluded.end_date,
                 closed_time=excluded.closed_time, closed=excluded.closed,
                 volume=excluded.volume, clob_token_ids=excluded.clob_token_ids,
                 category=excluded.category, resolution=excluded.resolution""",
            (
                market.condition_id,
                market.question,
                market.slug,
                json.dumps(market.outcomes),
                json.dumps(market.outcome_prices),
                market.start_date.isoformat() if market.start_date else None,
                market.end_date.isoformat() if market.end_date else None,
                market.closed_time.isoformat() if market.closed_time else None,
                int(market.closed),
                market.volume,
                json.dumps(market.clob_token_ids),
                market.category,
                market.resolution,
            ),
        )
        self._conn.commit()

    def insert_token_market_mapping(self, token_id: str, condition_id: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO token_market_map (token_id, condition_id) VALUES (?,?)",
            (token_id, condition_id),
        )
        self._conn.commit()

    # ---- reads ----

    def get_wallet_trades(self, wallet: str) -> list[Trade]:
        rows = self._conn.execute(
            "SELECT * FROM trades WHERE wallet = ? ORDER BY timestamp",
            (wallet.lower(),),
        ).fetchall()
        return [self._row_to_trade(r) for r in rows]

    def get_wallet_deposits(self, wallet: str) -> list[Deposit]:
        """Get all USDC.e transfers TO this wallet (inbound deposits)."""
        rows = self._conn.execute(
            "SELECT * FROM deposits WHERE to_address = ? ORDER BY timestamp",
            (wallet.lower(),),
        ).fetchall()
        return [self._row_to_deposit(r) for r in rows]

    def get_wallet_withdrawals(self, wallet: str) -> list[Deposit]:
        """Get all USDC.e transfers FROM this wallet (outbound withdrawals)."""
        rows = self._conn.execute(
            "SELECT * FROM deposits WHERE from_address = ? ORDER BY timestamp",
            (wallet.lower(),),
        ).fetchall()
        return [self._row_to_deposit(r) for r in rows]

    def get_market_by_token(self, token_id: str) -> Market | None:
        row = self._conn.execute(
            """SELECT m.* FROM markets m
               JOIN token_market_map tm ON m.condition_id = tm.condition_id
               WHERE tm.token_id = ?""",
            (token_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_market(row)

    def get_all_wallets(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT wallet FROM trades ORDER BY wallet"
        ).fetchall()
        return [r[0] for r in rows]

    def get_unique_token_ids(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT token_id FROM trades"
        ).fetchall()
        return [r[0] for r in rows]

    def get_mapped_token_ids(self) -> set[str]:
        rows = self._conn.execute(
            "SELECT token_id FROM token_market_map"
        ).fetchall()
        return {r[0] for r in rows}

    # ---- helpers ----

    @staticmethod
    def _row_to_trade(r: tuple) -> Trade:
        return Trade(
            tx_hash=r[0],
            block_number=r[1],
            timestamp=_parse_dt(r[2]),
            wallet=r[3],
            token_id=r[4],
            side=Side(r[5]),
            amount_usdc=r[6],
            amount_tokens=r[7],
            price=r[8],
            fee=r[9],
            exchange=r[10],
        )

    @staticmethod
    def _row_to_deposit(r: tuple) -> Deposit:
        return Deposit(
            tx_hash=r[0],
            block_number=r[1],
            timestamp=_parse_dt(r[2]),
            to_address=r[3],
            from_address=r[4],
            amount_usdc=r[5],
        )

    @staticmethod
    def _row_to_market(r: tuple) -> Market:
        import json

        return Market(
            condition_id=r[0],
            question=r[1],
            slug=r[2],
            outcomes=json.loads(r[3]),
            outcome_prices=json.loads(r[4]),
            start_date=_parse_dt(r[5]) if r[5] else None,
            end_date=_parse_dt(r[6]) if r[6] else None,
            closed_time=_parse_dt(r[7]) if r[7] else None,
            closed=bool(r[8]),
            volume=r[9],
            clob_token_ids=json.loads(r[10]),
            category=r[11],
            resolution=r[12],
        )

    def close(self) -> None:
        self._conn.close()
