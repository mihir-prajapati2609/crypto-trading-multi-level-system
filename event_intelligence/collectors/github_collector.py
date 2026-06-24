"""
Event Intelligence — GitHub Collector

Monitors GitHub repos of major crypto projects for releases,
unusual commit activity, and protocol upgrades.
"""

import logging
import time
from typing import Optional

import aiohttp

from event_intelligence.collectors.base import BaseCollector
from event_intelligence.models import NewsEvent, EventCategory

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubCollector(BaseCollector):
    """Monitors GitHub activity for major crypto project repos."""

    def __init__(self, repos: list[str], token: str = "", poll_interval: int = 300):
        super().__init__(
            source_name="github",
            poll_interval=poll_interval,
        )
        self.repos = repos
        self.token = token
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            headers = {
                "User-Agent": "CryptoEventBot/1.0",
                "Accept": "application/vnd.github+json",
            }
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers=headers,
            )

    async def _fetch_repo_releases(self, repo: str) -> list[NewsEvent]:
        """Fetch recent releases for a repo."""
        events = []
        try:
            await self._ensure_session()
            url = f"{GITHUB_API}/repos/{repo}/releases?per_page=5"
            async with self._session.get(url) as resp:
                if resp.status != 200:
                    return events
                releases = await resp.json()

            for release in releases[:3]:
                tag = release.get("tag_name", "")
                name = release.get("name", tag)
                body = release.get("body", "")[:300]
                published_at = release.get("published_at", "")
                html_url = release.get("html_url", "")
                prerelease = release.get("prerelease", False)

                # Parse timestamp
                ts = time.time()
                if published_at:
                    from datetime import datetime
                    try:
                        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                        ts = dt.timestamp()
                    except Exception:
                        pass

                # Extract project name from repo
                project = repo.split("/")[-1].upper()
                # Map common repos to coins
                repo_coin_map = {
                    "BITCOIN": "BTC", "GO-ETHEREUM": "ETH", "SOLANA": "SOL",
                    "CARDANO-NODE": "ADA", "POLKADOT": "DOT",
                }
                coin = repo_coin_map.get(project, project)

                release_type = "pre-release" if prerelease else "release"
                title = f"🔧 {repo}: New {release_type} {tag} — {name}"

                event = NewsEvent(
                    source="github_releases",
                    title=title,
                    body=body,
                    url=html_url,
                    raw_data={"repo": repo, "tag": tag, "prerelease": prerelease},
                    timestamp=ts,
                    category=EventCategory.PROTOCOL_UPGRADE,
                    affected_coins=[coin],
                )
                event.content_hash = self._compute_hash(f"{repo}_{tag}")
                events.append(event)

        except Exception as e:
            logger.debug(f"Error fetching GitHub releases for {repo}: {e}")

        return events

    async def _fetch_events(self) -> list[NewsEvent]:
        """Fetch events from all monitored repos."""
        all_events = []
        for repo in self.repos:
            events = await self._fetch_repo_releases(repo)
            all_events.extend(events)
        return all_events

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
