"""
test_scheduler.py

Tests for the web scheduler functionality.
"""

import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


class TestNextRunCalculation(unittest.TestCase):
    """Test next run time calculation with DST handling."""

    def test_next_run_same_week(self):
        """Test next run calculation when target day is later this week."""
        # Monday at 10:00 AM, schedule for Friday
        now = datetime(2024, 1, 1, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))  # Monday
        target_weekday = 4  # Friday
        target_hour = 14
        target_minute = 30

        days_ahead = target_weekday - now.weekday()
        self.assertEqual(days_ahead, 4)

        next_run = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0) + timedelta(
            days=days_ahead
        )

        # Should be Friday at 2:30 PM
        self.assertEqual(next_run.weekday(), 4)
        self.assertEqual(next_run.hour, 14)
        self.assertEqual(next_run.minute, 30)

    def test_next_run_next_week(self):
        """Test next run calculation when target day has passed this week."""
        # Friday at 10:00 AM, schedule for Monday
        now = datetime(2024, 1, 5, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))  # Friday
        target_weekday = 0  # Monday
        target_hour = 9
        target_minute = 0

        days_ahead = target_weekday - now.weekday()
        if days_ahead < 0:
            days_ahead += 7

        self.assertEqual(days_ahead, 3)

        next_run = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0) + timedelta(
            days=days_ahead
        )

        # Should be next Monday at 9:00 AM
        self.assertEqual(next_run.weekday(), 0)
        self.assertEqual(next_run.hour, 9)
        self.assertEqual(next_run.minute, 0)

    def test_next_run_with_advance_minutes(self):
        """Test next run calculation with advance notification."""
        # Monday at 10:00 AM, schedule for Friday at 3:00 PM with 10 min advance
        now = datetime(2024, 1, 1, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        target_weekday = 4  # Friday
        target_hour = 15
        target_minute = 0
        advance_minutes = 10

        days_ahead = target_weekday - now.weekday()
        next_run = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0) + timedelta(
            days=days_ahead
        )

        # Apply advance
        next_run = next_run - timedelta(minutes=advance_minutes)

        # Should be Friday at 2:50 PM
        self.assertEqual(next_run.weekday(), 4)
        self.assertEqual(next_run.hour, 14)
        self.assertEqual(next_run.minute, 50)

    def test_dst_transition(self):
        """Test that DST transitions are handled correctly."""
        # Test scheduling across DST boundary
        # In 2024, DST starts on March 10 in America/New_York
        # 2:00 AM becomes 3:00 AM

        # Schedule for Monday at 2:30 AM during DST
        pre_dst = datetime(2024, 3, 4, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))  # Monday before DST
        target_weekday = 0  # Monday
        target_hour = 2
        target_minute = 30

        days_ahead = 7  # Next Monday
        next_run = pre_dst.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0) + timedelta(
            days=days_ahead
        )

        # Next Monday is after DST switch
        next_run_utc = next_run.astimezone(ZoneInfo("UTC"))

        # Verify the UTC time accounts for DST
        # Before DST: EST is UTC-5
        # After DST: EDT is UTC-4
        # So 2:30 AM EDT = 6:30 AM UTC (not 7:30 AM UTC)
        self.assertEqual(next_run_utc.hour, 6)
        self.assertEqual(next_run_utc.minute, 30)


class TestPermissionFiltering(unittest.TestCase):
    """Test guild permission filtering."""

    def test_filter_manageable_guilds(self):
        """Test filtering guilds by Manage Guild permission."""
        MANAGE_GUILD = 0x00000020

        guilds = [
            {"id": "123", "name": "Guild 1", "permissions": str(MANAGE_GUILD)},
            {"id": "456", "name": "Guild 2", "permissions": "0"},
            {"id": "789", "name": "Guild 3", "permissions": str(MANAGE_GUILD | 0x00000008)},
        ]

        manageable = [guild for guild in guilds if int(guild.get("permissions", 0)) & MANAGE_GUILD]

        self.assertEqual(len(manageable), 2)
        self.assertEqual(manageable[0]["id"], "123")
        self.assertEqual(manageable[1]["id"], "789")


class TestTemplateRendering(unittest.TestCase):
    """Test template rendering with placeholders."""

    def test_render_with_all_placeholders(self):
        """Test rendering with both system_name and role_id."""
        template = "Territory defense in {system_name} scheduled! <@&{role_id}>"
        system_name = "Sol System"
        role_id = "123456789012345678"

        rendered = template.replace("{system_name}", system_name)
        rendered = rendered.replace("{role_id}", role_id)

        self.assertEqual(rendered, "Territory defense in Sol System scheduled! <@&123456789012345678>")

    def test_render_without_role_id(self):
        """Test rendering without role_id."""
        template = "Territory defense in {system_name} scheduled! <@&{role_id}>"
        system_name = "Sol System"
        role_id = None

        rendered = template.replace("{system_name}", system_name)
        if role_id:
            rendered = rendered.replace("{role_id}", role_id)
        else:
            rendered = rendered.replace("<@&{role_id}>", "")
            rendered = rendered.replace("{role_id}", "")

        self.assertEqual(rendered, "Territory defense in Sol System scheduled! ")

    def test_validate_role_id_numeric(self):
        """Test role_id validation."""
        valid_role_id = "123456789012345678"
        invalid_role_id = "not_a_number"

        self.assertTrue(valid_role_id.isdigit())
        self.assertFalse(invalid_role_id.isdigit())


if __name__ == "__main__":
    unittest.main()
