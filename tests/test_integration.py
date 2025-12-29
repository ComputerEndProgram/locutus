"""
test_integration.py

Integration tests for database and template functionality.
"""

import asyncio
import os
import tempfile
import unittest
from datetime import datetime

from sqlalchemy import select

# Set minimal env before importing
os.environ["TOKEN"] = "test_token"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from src.web_db import (
    GuildConfig,
    Template,
    Schedule,
    get_engine,
    get_session_maker,
    init_db,
)
from src.template_utils import render_template, load_preset_templates, ensure_guild_has_templates


class TestDatabaseModels(unittest.TestCase):
    """Test database models and operations."""

    def setUp(self):
        """Set up test database."""
        self.engine = get_engine("sqlite+aiosqlite:///:memory:")
        self.SessionLocal = get_session_maker(self.engine)

    def test_create_guild_config(self):
        """Test creating guild configuration."""

        async def run_test():
            await init_db(self.engine)

            async with self.SessionLocal() as db:
                guild_config = GuildConfig(
                    guild_id="123456789",
                    timezone="America/New_York",
                    role_id="987654321",
                    default_channel_id="555555555",
                )
                db.add(guild_config)
                await db.commit()

                # Fetch it back
                result = await db.execute(select(GuildConfig).where(GuildConfig.guild_id == "123456789"))
                fetched = result.scalar_one_or_none()

                self.assertIsNotNone(fetched)
                self.assertEqual(fetched.guild_id, "123456789")
                self.assertEqual(fetched.timezone, "America/New_York")
                self.assertEqual(fetched.role_id, "987654321")

        asyncio.run(run_test())

    def test_create_template(self):
        """Test creating message template."""

        async def run_test():
            await init_db(self.engine)

            async with self.SessionLocal() as db:
                # Create guild first
                guild_config = GuildConfig(guild_id="123456789")
                db.add(guild_config)
                await db.commit()

                # Create template
                template = Template(
                    guild_id="123456789",
                    name="Test Template",
                    content="Territory defense in {system_name}! <@&{role_id}>",
                    is_default=True,
                )
                db.add(template)
                await db.commit()

                # Fetch it back
                result = await db.execute(select(Template).where(Template.guild_id == "123456789"))
                fetched = result.scalar_one_or_none()

                self.assertIsNotNone(fetched)
                self.assertEqual(fetched.name, "Test Template")
                self.assertTrue(fetched.is_default)

        asyncio.run(run_test())

    def test_create_schedule(self):
        """Test creating schedule."""

        async def run_test():
            await init_db(self.engine)

            async with self.SessionLocal() as db:
                # Create guild and template first
                guild_config = GuildConfig(guild_id="123456789")
                db.add(guild_config)
                await db.commit()

                template = Template(
                    guild_id="123456789",
                    name="Test Template",
                    content="Test content",
                    is_default=True,
                )
                db.add(template)
                await db.commit()
                await db.refresh(template)

                # Create schedule
                schedule = Schedule(
                    guild_id="123456789",
                    template_id=template.id,
                    system_name="Test System",
                    weekday=0,  # Monday
                    time_local="14:30",
                    timezone="America/New_York",
                    channel_id="111111111",
                    enabled=True,
                    created_by_user_id="999999999",
                    next_run_utc=datetime.utcnow(),
                    advance_minutes=10,
                )
                db.add(schedule)
                await db.commit()

                # Fetch it back
                result = await db.execute(select(Schedule).where(Schedule.guild_id == "123456789"))
                fetched = result.scalar_one_or_none()

                self.assertIsNotNone(fetched)
                self.assertEqual(fetched.system_name, "Test System")
                self.assertEqual(fetched.weekday, 0)
                self.assertEqual(fetched.advance_minutes, 10)

        asyncio.run(run_test())


class TestTemplateUtils(unittest.TestCase):
    """Test template utility functions."""

    def test_load_preset_templates(self):
        """Test loading preset templates."""
        templates = load_preset_templates()

        self.assertIsInstance(templates, dict)
        # Should have at least one template
        self.assertGreater(len(templates), 0)

        # Check that templates contain placeholders
        for name, content in templates.items():
            self.assertIn("{system_name}", content)
            self.assertIn("{role_id}", content)

    def test_render_template_with_placeholders(self):
        """Test template rendering."""
        template = "Territory defense in {system_name}! <@&{role_id}>"
        system_name = "Sol System"
        role_id = "123456789"

        rendered = render_template(template, system_name, role_id)

        self.assertIn("Sol System", rendered)
        self.assertIn("123456789", rendered)
        self.assertNotIn("{system_name}", rendered)
        self.assertNotIn("{role_id}", rendered)

    def test_render_template_without_role_id(self):
        """Test template rendering without role_id."""
        template = "Territory defense in {system_name}! <@&{role_id}>"
        system_name = "Sol System"
        role_id = None

        rendered = render_template(template, system_name, role_id)

        self.assertIn("Sol System", rendered)
        self.assertNotIn("<@&", rendered)

    def test_ensure_guild_has_templates(self):
        """Test ensuring guild has templates."""

        async def run_test():
            engine = get_engine("sqlite+aiosqlite:///:memory:")
            SessionLocal = get_session_maker(engine)
            await init_db(engine)

            async with SessionLocal() as db:
                # Create guild
                guild_config = GuildConfig(guild_id="123456789")
                db.add(guild_config)
                await db.commit()

                # Ensure templates
                await ensure_guild_has_templates(db, "123456789")

                # Check that templates were created
                result = await db.execute(select(Template).where(Template.guild_id == "123456789"))
                templates = result.scalars().all()

                self.assertGreater(len(templates), 0)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
