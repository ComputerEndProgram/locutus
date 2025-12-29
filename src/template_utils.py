"""
template_utils.py

Utilities for loading and managing templates.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.web_db import Template

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent.parent / "assets"


def load_preset_templates() -> dict[str, str]:
    """Load preset templates from assets directory."""
    templates = {}
    
    # Load preset1.txt (English)
    preset1_path = ASSETS_DIR / "preset1.txt"
    if preset1_path.exists():
        with open(preset1_path, "r", encoding="utf-8") as f:
            content = f.read()
            # Standardize placeholders
            content = content.replace("{system_name}", "{system_name}")
            content = content.replace("role_id", "{role_id}")
            content = content.replace("<@&role_id>", "<@&{role_id}>")
            templates["English Default"] = content

    # Load preset2.txt (German)
    preset2_path = ASSETS_DIR / "preset2.txt"
    if preset2_path.exists():
        with open(preset2_path, "r", encoding="utf-8") as f:
            content = f.read()
            # Standardize placeholders
            content = content.replace("{system_name}", "{system_name}")
            content = content.replace("{role_id}", "{role_id}")
            content = content.replace("<@&{role_id}>", "<@&{role_id}>")
            templates["German Default"] = content

    return templates


async def ensure_guild_has_templates(db: AsyncSession, guild_id: str) -> None:
    """Ensure a guild has at least the default templates."""
    # Check if guild already has templates
    result = await db.execute(select(Template).where(Template.guild_id == guild_id))
    existing_templates = result.scalars().all()

    if existing_templates:
        return  # Guild already has templates

    # Load preset templates
    presets = load_preset_templates()

    # Create templates for the guild
    is_first = True
    for name, content in presets.items():
        template = Template(
            guild_id=guild_id,
            name=name,
            content=content,
            is_default=is_first,  # First template is default
        )
        db.add(template)
        is_first = False

    await db.commit()
    logger.info(f"Initialized {len(presets)} templates for guild {guild_id}")


def render_template(content: str, system_name: str, role_id: str | None) -> str:
    """Render a template with placeholders substituted."""
    rendered = content.replace("{system_name}", system_name)
    
    if role_id:
        # Validate role_id is numeric
        if not role_id.isdigit():
            logger.warning(f"Invalid role_id: {role_id}, using placeholder")
            rendered = rendered.replace("{role_id}", "INVALID_ROLE_ID")
        else:
            rendered = rendered.replace("{role_id}", role_id)
    else:
        # If no role_id, remove the mention line
        rendered = rendered.replace("<@&{role_id}>", "")
        rendered = rendered.replace("{role_id}", "")

    return rendered
