"""
test_web_app.py

Tests for web application caching, rate limiting, and guild filtering.
"""

import asyncio
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Set minimal env before importing
os.environ["TOKEN"] = "test_token"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from src.web_app import (
    get_user_guilds,
    filter_manageable_guilds,
    filter_bot_guilds,
    get_manageable_guilds_with_cache,
    GUILD_CACHE_TTL,
)


class TestGuildCaching(unittest.TestCase):
    """Test guild caching functionality."""

    def test_filter_manageable_guilds(self):
        """Test filtering guilds by Manage Guild permission."""
        MANAGE_GUILD = 0x00000020

        guilds = [
            {"id": "123", "name": "Guild 1", "permissions": str(MANAGE_GUILD)},
            {"id": "456", "name": "Guild 2", "permissions": "0"},
            {"id": "789", "name": "Guild 3", "permissions": str(MANAGE_GUILD | 0x00000008)},
            {"id": "999", "name": "Guild 4", "permissions": str(0x00000008)},
        ]

        manageable = filter_manageable_guilds(guilds)

        self.assertEqual(len(manageable), 2)
        self.assertEqual(manageable[0]["id"], "123")
        self.assertEqual(manageable[1]["id"], "789")

    def test_filter_bot_guilds(self):
        """Test filtering guilds by bot presence."""
        guilds = [
            {"id": "123", "name": "Guild 1"},
            {"id": "456", "name": "Guild 2"},
            {"id": "789", "name": "Guild 3"},
        ]

        bot_guild_ids = {"123", "789"}
        filtered = filter_bot_guilds(guilds, bot_guild_ids)

        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0]["id"], "123")
        self.assertEqual(filtered[1]["id"], "789")

    def test_filter_bot_guilds_no_bot_data(self):
        """Test filtering when bot guild data is unavailable (degraded mode)."""
        guilds = [
            {"id": "123", "name": "Guild 1"},
            {"id": "456", "name": "Guild 2"},
        ]

        # When no bot data available, should return all guilds
        filtered = filter_bot_guilds(guilds, set())

        self.assertEqual(len(filtered), 2)

    def test_cache_ttl_validation(self):
        """Test cache TTL expiration logic."""
        now = datetime.now(timezone.utc).timestamp()

        # Fresh cache (5 seconds old)
        cache_timestamp = now - 5
        cache_age = now - cache_timestamp
        self.assertTrue(cache_age < GUILD_CACHE_TTL)

        # Stale cache (60 seconds old, TTL is 30)
        cache_timestamp = now - 60
        cache_age = now - cache_timestamp
        self.assertFalse(cache_age < GUILD_CACHE_TTL)


class TestRateLimitHandling(unittest.TestCase):
    """Test Discord API rate limit handling."""

    def test_get_user_guilds_success(self):
        """Test successful guild fetch."""

        async def run_test():
            mock_guilds = [{"id": "123", "name": "Test Guild"}]

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_response = AsyncMock()
                mock_response.status_code = 200
                mock_response.json = MagicMock(return_value=mock_guilds)
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value.__aenter__.return_value = mock_client

                guilds = await get_user_guilds("test_token")

                self.assertEqual(guilds, mock_guilds)

        asyncio.run(run_test())

    def test_get_user_guilds_rate_limit_with_retry(self):
        """Test rate limit handling with successful retry."""

        async def run_test():
            mock_guilds = [{"id": "123", "name": "Test Guild"}]

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()

                # First response: rate limited
                mock_response_429 = AsyncMock()
                mock_response_429.status_code = 429
                mock_response_429.json = MagicMock(return_value={"retry_after": 0.1})

                # Second response: success
                mock_response_200 = AsyncMock()
                mock_response_200.status_code = 200
                mock_response_200.json = MagicMock(return_value=mock_guilds)

                mock_client.get = AsyncMock(side_effect=[mock_response_429, mock_response_200])
                mock_client_class.return_value.__aenter__.return_value = mock_client

                guilds = await get_user_guilds("test_token")

                self.assertEqual(guilds, mock_guilds)
                self.assertEqual(mock_client.get.call_count, 2)

        asyncio.run(run_test())

    def test_get_user_guilds_rate_limit_fallback_to_cache(self):
        """Test rate limit with cache fallback when retry also fails."""

        async def run_test():
            cached_guilds = [{"id": "999", "name": "Cached Guild"}]

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()

                # Both responses: rate limited
                mock_response_429 = AsyncMock()
                mock_response_429.status_code = 429
                mock_response_429.json = MagicMock(return_value={"retry_after": 0.1})

                mock_client.get = AsyncMock(return_value=mock_response_429)
                mock_client_class.return_value.__aenter__.return_value = mock_client

                guilds = await get_user_guilds("test_token", cached_guilds)

                # Should return cached guilds
                self.assertEqual(guilds, cached_guilds)
                self.assertEqual(mock_client.get.call_count, 2)

        asyncio.run(run_test())

    def test_get_user_guilds_auth_failure(self):
        """Test authentication failure returns empty list."""

        async def run_test():
            cached_guilds = [{"id": "999", "name": "Cached Guild"}]

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_response = AsyncMock()
                mock_response.status_code = 401
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value.__aenter__.return_value = mock_client

                guilds = await get_user_guilds("test_token", cached_guilds)

                # Auth failure should return empty, not cached
                self.assertEqual(guilds, [])

        asyncio.run(run_test())

    def test_get_user_guilds_rate_limit_no_cache(self):
        """Test rate limit without cache returns empty."""

        async def run_test():
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()

                # Both responses: rate limited
                mock_response_429 = AsyncMock()
                mock_response_429.status_code = 429
                mock_response_429.json = MagicMock(return_value={"retry_after": 0.1})

                mock_client.get = AsyncMock(return_value=mock_response_429)
                mock_client_class.return_value.__aenter__.return_value = mock_client

                guilds = await get_user_guilds("test_token")

                # No cache available, should return empty
                self.assertEqual(guilds, [])

        asyncio.run(run_test())


class TestCacheIntegration(unittest.TestCase):
    """Test cache integration with session management."""

    def test_get_manageable_guilds_with_cache_fresh(self):
        """Test using fresh cache."""

        async def run_test():
            cached_guilds = [{"id": "123", "name": "Cached", "permissions": "32"}]
            session_data = {
                "access_token": "test_token",
                "cached_guilds": cached_guilds,
                "guild_cache_timestamp": datetime.now(timezone.utc).timestamp(),
            }

            # Mock bot guild IDs to avoid warnings
            with patch("src.web_app.get_bot_guild_ids", return_value={"123"}):
                guilds, updated_session = await get_manageable_guilds_with_cache(
                    session_data, use_cache=True, filter_by_bot=True
                )

            # Should use cached data
            self.assertEqual(guilds, cached_guilds)
            # Session should not be updated (cache was fresh)
            self.assertEqual(session_data["cached_guilds"], updated_session["cached_guilds"])

        asyncio.run(run_test())

    def test_get_manageable_guilds_with_cache_stale(self):
        """Test refreshing stale cache."""

        async def run_test():
            old_guilds = [{"id": "999", "name": "Old", "permissions": "32"}]
            new_guilds = [{"id": "123", "name": "New", "permissions": "32"}]

            session_data = {
                "access_token": "test_token",
                "cached_guilds": old_guilds,
                "guild_cache_timestamp": datetime.now(timezone.utc).timestamp() - 100,  # Stale
            }

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_response = AsyncMock()
                mock_response.status_code = 200
                mock_response.json = MagicMock(return_value=new_guilds)
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value.__aenter__.return_value = mock_client

                # Mock bot guild IDs
                with patch("src.web_app.get_bot_guild_ids", return_value={"123"}):
                    guilds, updated_session = await get_manageable_guilds_with_cache(
                        session_data, use_cache=True, filter_by_bot=True
                    )

            # Should fetch fresh data
            self.assertEqual(guilds, new_guilds)
            # Session should be updated
            self.assertEqual(updated_session["cached_guilds"], new_guilds)
            self.assertIsNotNone(updated_session["guild_cache_timestamp"])

        asyncio.run(run_test())

    def test_get_manageable_guilds_rate_limit_preserves_access(self):
        """Test that rate limit with cache preserves user access."""

        async def run_test():
            cached_guilds = [{"id": "123", "name": "Cached", "permissions": "32"}]
            session_data = {
                "access_token": "test_token",
                "cached_guilds": cached_guilds,
                "guild_cache_timestamp": datetime.now(timezone.utc).timestamp() - 100,  # Stale
            }

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()

                # Rate limited responses
                mock_response_429 = AsyncMock()
                mock_response_429.status_code = 429
                mock_response_429.json = MagicMock(return_value={"retry_after": 0.1})

                mock_client.get = AsyncMock(return_value=mock_response_429)
                mock_client_class.return_value.__aenter__.return_value = mock_client

                # Mock bot guild IDs
                with patch("src.web_app.get_bot_guild_ids", return_value={"123"}):
                    guilds, updated_session = await get_manageable_guilds_with_cache(
                        session_data, use_cache=True, filter_by_bot=True
                    )

            # Should fall back to cached guilds
            self.assertEqual(guilds, cached_guilds)
            # User should still have access
            self.assertGreater(len(guilds), 0)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
