"""
Event Intelligence — Entity Extractor

Extracts structured data from event text:
- Coin/token symbols
- Exchange names
- Dollar amounts
- Percentage values
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Known crypto symbols (top 200+)
KNOWN_SYMBOLS = {
    "BTC", "ETH", "BNB", "XRP", "ADA", "DOGE", "SOL", "DOT", "MATIC",
    "AVAX", "LINK", "UNI", "ATOM", "LTC", "ETC", "XLM", "ALGO", "VET",
    "FIL", "ICP", "NEAR", "APE", "SAND", "MANA", "AXS", "AAVE", "GRT",
    "CRV", "MKR", "SNX", "COMP", "YFI", "SUSHI", "FTM", "ONE", "HBAR",
    "EGLD", "XTZ", "THETA", "ENJ", "CHZ", "BAT", "ZIL", "IOTA", "WAVES",
    "DASH", "ZEC", "NEO", "QTUM", "ICX", "ONT", "ZRX", "REN", "ANKR",
    "CRO", "KAVA", "CELO", "RSR", "BAND", "STORJ", "OGN", "NKN", "LOOM",
    "PEPE", "SHIB", "FLOKI", "WIF", "BONK", "MEME", "DEGEN",
    "OP", "ARB", "SUI", "SEI", "TIA", "JUP", "W", "STRK", "ZK",
    "TON", "NOT", "DOGS", "HMSTR",
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP",
    "WBTC", "WETH", "STETH",
}

# Common names to symbol mapping
NAME_TO_SYMBOL = {
    "bitcoin": "BTC", "ethereum": "ETH", "binance coin": "BNB",
    "bnb": "BNB", "ripple": "XRP", "cardano": "ADA", "dogecoin": "DOGE",
    "solana": "SOL", "polkadot": "DOT", "polygon": "MATIC",
    "avalanche": "AVAX", "chainlink": "LINK", "uniswap": "UNI",
    "cosmos": "ATOM", "litecoin": "LTC", "ethereum classic": "ETC",
    "stellar": "XLM", "algorand": "ALGO", "vechain": "VET",
    "filecoin": "FIL", "near protocol": "NEAR", "near": "NEAR",
    "apecoin": "APE", "sandbox": "SAND", "decentraland": "MANA",
    "axie": "AXS", "aave": "AAVE", "the graph": "GRT",
    "curve": "CRV", "maker": "MKR", "synthetix": "SNX",
    "compound": "COMP", "sushi": "SUSHI", "fantom": "FTM",
    "hedera": "HBAR", "tezos": "XTZ", "theta": "THETA",
    "enjin": "ENJ", "chiliz": "CHZ", "pepe": "PEPE",
    "shiba": "SHIB", "shiba inu": "SHIB", "floki": "FLOKI",
    "arbitrum": "ARB", "optimism": "OP", "sui": "SUI",
    "sei": "SEI", "celestia": "TIA", "jupiter": "JUP",
    "toncoin": "TON", "ton": "TON",
}

# Known exchanges
KNOWN_EXCHANGES = {
    "binance", "coinbase", "kraken", "okx", "bybit", "kucoin",
    "bitfinex", "gate.io", "gate", "huobi", "htx", "gemini",
    "bitstamp", "upbit", "bithumb", "crypto.com", "mexc",
}


class EntityExtractor:
    """Extracts structured entities from crypto news text."""

    def extract_coins(self, text: str) -> list[str]:
        """
        Extract mentioned cryptocurrency symbols from text.
        Returns list of uppercase symbols like ["BTC", "ETH"].
        """
        coins = set()
        text_lower = text.lower()

        # Method 1: Direct symbol matches (look for $SYMBOL or standalone symbols)
        # Match $BTC, $ETH style
        dollar_symbols = re.findall(r'\$([A-Z]{2,10})', text)
        for sym in dollar_symbols:
            if sym in KNOWN_SYMBOLS:
                coins.add(sym)

        # Match standalone uppercase symbols (surrounded by non-alpha)
        word_symbols = re.findall(r'\b([A-Z]{2,10})\b', text)
        for sym in word_symbols:
            if sym in KNOWN_SYMBOLS:
                # Avoid false positives for common abbreviations
                if sym not in {"AI", "US", "UK", "EU", "CEO", "CTO", "SEC", "ETF",
                               "USD", "API", "NFT", "TVL", "APR", "APY"}:
                    coins.add(sym)

        # Method 2: Name-to-symbol mapping
        for name, symbol in NAME_TO_SYMBOL.items():
            if name in text_lower:
                coins.add(symbol)

        # Remove stablecoins from results (they're not tradeable events)
        stables = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP"}
        coins -= stables

        return sorted(list(coins))

    def extract_exchanges(self, text: str) -> list[str]:
        """Extract mentioned exchange names."""
        exchanges = []
        text_lower = text.lower()
        for exchange in KNOWN_EXCHANGES:
            if exchange in text_lower:
                exchanges.append(exchange)
        return exchanges

    def extract_dollar_amounts(self, text: str) -> list[float]:
        """Extract dollar amounts mentioned in text."""
        amounts = []

        # Match patterns like $100M, $2.5B, $500K, $1,000
        patterns = [
            r'\$(\d+(?:\.\d+)?)\s*[bB](?:illion)?',    # $X billion
            r'\$(\d+(?:\.\d+)?)\s*[mM](?:illion)?',    # $X million
            r'\$(\d+(?:\.\d+)?)\s*[kK]',               # $X thousand
            r'\$(\d{1,3}(?:,\d{3})+(?:\.\d+)?)',        # $1,000,000
            r'\$(\d+(?:\.\d+)?)',                        # $X
        ]

        multipliers = [1e9, 1e6, 1e3, 1, 1]

        for pattern, mult in zip(patterns, multipliers):
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    value = float(match.replace(",", "")) * mult
                    amounts.append(value)
                except ValueError:
                    pass

        return amounts

    def extract_percentages(self, text: str) -> list[float]:
        """Extract percentage values from text."""
        percentages = []
        matches = re.findall(r'([+-]?\d+(?:\.\d+)?)\s*%', text)
        for match in matches:
            try:
                percentages.append(float(match))
            except ValueError:
                pass
        return percentages

    def extract_all(self, text: str) -> dict:
        """Extract all entities from text and return structured data."""
        return {
            "coins": self.extract_coins(text),
            "exchanges": self.extract_exchanges(text),
            "dollar_amounts": self.extract_dollar_amounts(text),
            "percentages": self.extract_percentages(text),
        }
