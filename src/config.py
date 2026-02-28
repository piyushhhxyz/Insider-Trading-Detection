"""Constants, RPC URLs, contract addresses, ABIs, and scoring configuration."""

import os
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

# --- RPC ---
POLYGON_RPC_URL = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
POLYGON_CHAIN_ID = 137

# --- Contract Addresses ---
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEG_RISK_CTF_EXCHANGE = "0xC5d563A36AE78145C45a50134d48A1215220f80a"
USDC_E_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

# --- APIs ---
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"

# --- Database ---
DB_PATH = os.getenv("DB_PATH", "insider_trades.db")

# --- Indexer Defaults ---
DEFAULT_BATCH_SIZE = 10_000  # blocks per RPC batch
USDC_E_DECIMALS = 6

# --- Event ABIs ---
ORDER_FILLED_ABI = {
    "anonymous": False,
    "inputs": [
        {"indexed": True, "name": "orderHash", "type": "bytes32"},
        {"indexed": True, "name": "maker", "type": "address"},
        {"indexed": True, "name": "taker", "type": "address"},
        {"indexed": False, "name": "makerAssetId", "type": "uint256"},
        {"indexed": False, "name": "takerAssetId", "type": "uint256"},
        {"indexed": False, "name": "makerAmountFilled", "type": "uint256"},
        {"indexed": False, "name": "takerAmountFilled", "type": "uint256"},
        {"indexed": False, "name": "fee", "type": "uint256"},
    ],
    "name": "OrderFilled",
    "type": "event",
}

TRANSFER_ABI = {
    "anonymous": False,
    "inputs": [
        {"indexed": True, "name": "from", "type": "address"},
        {"indexed": True, "name": "to", "type": "address"},
        {"indexed": False, "name": "value", "type": "uint256"},
    ],
    "name": "Transfer",
    "type": "event",
}

# Minimal contract ABIs (only the events we need)
CTF_EXCHANGE_ABI = [ORDER_FILLED_ABI]
USDC_E_ABI = [TRANSFER_ABI]

# --- Known Insider Wallets (for validation) ---
KNOWN_INSIDERS = [
    # Google d4vd / AlphaRaccoon
    "0xee50a31c3f5a7c77824b12a941a54388a2827ed6",
    # Maduro out / SBet365
    "0x6baf05d193692bb208d616709e27442c910a94c5",
    # Spotify hogriddahhhh (not insider - smart scraper)
    "0xc51eedc01790252d571648cb4abd8e9876de5202",
    # Maduro out / unnamed wallet
    "0x31a56e9e690c621ed21de08cb559e9524cdb8ed9",
    # Israel iran / ricosuave
    "0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2",
    # Trump pardon CZ / gj1
    "0x7f1329ade2ec162c6f8791dad99125e0dc49801c",
    # MicroStrategy / fromagi
    "0x976685b6e867a0400085b1273309e84cd0fc627c",
    # DraftKings / flaccidwillie
    "0x55ea982cebff271722419595e0659ef297b48d7c",
]

# --- Normal Wallets (control group for validation) ---
NORMAL_WALLETS = [
    "0xfcdaf37b9ecbcae92ed1869efbdc59a1cab9c70a",
    "0xb863fc4f93b747e668b7f1b0cf6a12eae9aaa3a0",
    "0xe5e1c17f6319ec40240050b400aa45b0c79698a8",
    "0xdc241fb1db81a2f08e4e0ff42554019ad32a4ab5",
    "0x2eb5714ff6f20f5f9f7662c556dbef5e1c9bf4d4",
    "0x272b9a72ff25d164a4f265e2ac78f73904bfddc3",
    "0xed87bc130e09d11550653a5bc377ebe6b8e8572d",
    "0x1e3cb16886d605430a8c5581eddd08e068c08a62",
    "0xd1922f466b05b55dbf9d93f4aff67899d57494eb",
    "0x16652fd6bc0e3765281ea5251bc141fce29c7902",
]


# --- Scoring Configuration ---
class ScoringConfig(BaseModel):
    """All detection weights, thresholds, and parameters in one place."""

    # Signal weights (must sum to 1.0)
    wallet_freshness_weight: float = 0.15
    outcome_certainty_weight: float = 0.25
    entry_timing_weight: float = 0.20
    market_focus_weight: float = 0.15
    position_size_weight: float = 0.10
    surgical_behavior_weight: float = 0.15

    # Risk tier thresholds
    critical_threshold: float = 0.85
    high_threshold: float = 0.70
    medium_threshold: float = 0.50

    # WalletFreshness parameters
    freshness_hours_critical: float = 2.0    # deposit-to-trade < 2h → score 1.0
    freshness_hours_suspicious: float = 24.0  # < 24h → score 0.7
    freshness_hours_moderate: float = 168.0   # < 7 days → score 0.4

    # OutcomeCertainty parameters
    certainty_min_price: float = 0.05   # min entry price to consider (5c)
    certainty_max_price: float = 0.50   # max entry price (bought cheap)
    certainty_min_payout_ratio: float = 2.0  # min payout multiplier

    # EntryTiming parameters
    timing_final_pct_critical: float = 0.05   # last 5% of market → score 1.0
    timing_final_pct_suspicious: float = 0.15  # last 15% → score 0.7
    timing_final_pct_moderate: float = 0.30    # last 30% → score 0.4

    # MarketFocus parameters
    focus_single_market_score: float = 1.0    # only 1 market → score 1.0
    focus_two_markets_score: float = 0.7
    focus_three_markets_score: float = 0.4

    # PositionSize parameters
    size_large_usd: float = 10_000.0    # >= $10K on single market → score 1.0
    size_medium_usd: float = 5_000.0    # >= $5K → score 0.7
    size_small_usd: float = 1_000.0     # >= $1K → score 0.4

    # SurgicalBehavior parameters
    surgical_full_pattern_score: float = 1.0   # fund→bet→win→withdraw→gone
    surgical_partial_pattern_score: float = 0.6  # fund→bet→win (no withdrawal tracked)
    surgical_withdraw_pct_threshold: float = 0.80  # withdrew ≥80% of balance


SCORING = ScoringConfig()
