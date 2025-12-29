"""
bot_state.py

Shared state between bot and web app processes.
Uses a simple JSON file for IPC.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import discord

logger = logging.getLogger(__name__)

# State file path in data directory
STATE_FILE = Path(__file__).parent.parent / "data" / "bot_state.json"


def write_bot_guild_ids(guild_ids: set[str]) -> None:
    """
    Write bot's current guild IDs to shared state file.
    
    Args:
        guild_ids: Set of guild ID strings where bot is present
    """
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        state = {
            "guild_ids": list(guild_ids),
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        # Write atomically by writing to temp file then renaming
        temp_file = STATE_FILE.with_suffix(".tmp")
        with open(temp_file, "w") as f:
            json.dump(state, f)
        temp_file.replace(STATE_FILE)
        
    except Exception as e:
        logger.error(f"Failed to write bot state: {e}")


def read_bot_guild_ids(max_age_seconds: int = 300) -> set[str]:
    """
    Read bot's guild IDs from shared state file.
    
    Args:
        max_age_seconds: Maximum age of state file in seconds (default 5 minutes)
        
    Returns:
        Set of guild ID strings, or empty set if unavailable/stale
    """
    try:
        if not STATE_FILE.exists():
            return set()
        
        # Check file age
        file_age = datetime.utcnow().timestamp() - STATE_FILE.stat().st_mtime
        if file_age > max_age_seconds:
            logger.warning(f"Bot state file is stale ({file_age:.0f}s old)")
            return set()
        
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        
        return set(state.get("guild_ids", []))
        
    except Exception as e:
        logger.error(f"Failed to read bot state: {e}")
        return set()


def get_bot_guilds_from_bot(bot: discord.Client) -> set[str]:
    """
    Get guild IDs directly from bot instance.
    
    Args:
        bot: Discord bot client
        
    Returns:
        Set of guild ID strings
    """
    return {str(guild.id) for guild in bot.guilds}
