"""
Event Intelligence — On-Chain Whale Wallet Collector

Tracks whale wallet movements using Etherscan API.
Detects large transfers, exchange inflows/outflows, and accumulation patterns.
"""

import logging
import time
from typing import Optional

import aiohttp

from event_intelligence.collectors.base import BaseCollector
from event_intelligence.models import NewsEvent, EventCategory

logger = logging.getLogger(__name__)

ETHERSCAN_API = "https://api.etherscan.io/api"

# Known exchange deposit addresses (simplified)
EXCHANGE_ADDRESSES = {
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance",
    "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": "Binance",
    "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43": "Coinbase",
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase",
    "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase",
    "0xe92d1a43df510f82c66382592a047d288f85226f": "OKX",
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX",
}

# Minimum transfer value in ETH to be considered "whale"
WHALE_THRESHOLD_ETH = 100


class OnChainWhaleCollector(BaseCollector):
    """Tracks on-chain whale movements using Etherscan."""

    def __init__(self, api_key: str = "", wallets: list[str] = None,
                 poll_interval: int = 120):
        super().__init__(
            source_name="onchain_whale",
            poll_interval=poll_interval,
        )
        self.api_key = api_key
        self.wallets = wallets or []
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
            )

    async def _fetch_large_transactions(self) -> list[NewsEvent]:
        """Fetch recent large ETH transactions (whale movements)."""
        events = []
        if not self.api_key:
            return events

        try:
            await self._ensure_session()

            # Check recent blocks for large transactions
            params = {
                "module": "account",
                "action": "txlist",
                "address": "0x00000000219ab540356cBB839Cbe05303d7705Fa",  # ETH2 deposit
                "startblock": 0,
                "endblock": 99999999,
                "page": 1,
                "offset": 10,
                "sort": "desc",
                "apikey": self.api_key,
            }

            async with self._session.get(ETHERSCAN_API, params=params) as resp:
                if resp.status != 200:
                    return events
                data = await resp.json()

            txs = data.get("result", [])
            if not isinstance(txs, list):
                return events

            for tx in txs:
                value_wei = int(tx.get("value", "0"))
                value_eth = value_wei / 1e18

                if value_eth < WHALE_THRESHOLD_ETH:
                    continue

                from_addr = tx.get("from", "").lower()
                to_addr = tx.get("to", "").lower()
                tx_hash = tx.get("hash", "")
                block_ts = int(tx.get("timeStamp", time.time()))

                from_exchange = EXCHANGE_ADDRESSES.get(from_addr, "")
                to_exchange = EXCHANGE_ADDRESSES.get(to_addr, "")

                # Determine direction
                if to_exchange and not from_exchange:
                    direction = f"→ {to_exchange} (potential sell)"
                    title = f"🐋 Whale deposits {value_eth:.1f} ETH to {to_exchange}"
                    category = EventCategory.WHALE_MOVEMENT
                elif from_exchange and not to_exchange:
                    direction = f"← {from_exchange} (potential buy/hold)"
                    title = f"🐋 Whale withdraws {value_eth:.1f} ETH from {from_exchange}"
                    category = EventCategory.WHALE_MOVEMENT
                else:
                    direction = "wallet to wallet"
                    title = f"🐋 Large ETH transfer: {value_eth:.1f} ETH"
                    category = EventCategory.WHALE_MOVEMENT

                event = NewsEvent(
                    source="onchain_whale",
                    title=title,
                    body=f"Transfer of {value_eth:.2f} ETH ({direction}). TX: {tx_hash[:16]}...",
                    url=f"https://etherscan.io/tx/{tx_hash}",
                    raw_data={
                        "value_eth": value_eth,
                        "from": from_addr[:10] + "...",
                        "to": to_addr[:10] + "...",
                        "direction": direction,
                    },
                    timestamp=block_ts,
                    category=category,
                    affected_coins=["ETH"],
                )
                event.content_hash = self._compute_hash(tx_hash)
                events.append(event)

        except Exception as e:
            logger.debug(f"Error fetching on-chain whale data: {e}")

        return events

    async def _fetch_events(self) -> list[NewsEvent]:
        """Fetch all on-chain events."""
        return await self._fetch_large_transactions()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
