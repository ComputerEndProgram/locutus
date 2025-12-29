"""
web_scheduler.py

Scheduler for territory defense reminders from web UI.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.web_db import Schedule, Template, GuildConfig, get_session_maker, get_engine
from src.template_utils import render_template

if TYPE_CHECKING:
    from src.bot import Bot

logger = logging.getLogger(__name__)


class WebScheduler:
    """Handles scheduling and posting of territory defense reminders."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.engine = get_engine()
        self.SessionLocal = get_session_maker(self.engine)
        self.running = False

    async def start(self):
        """Start the scheduler loop."""
        self.running = True
        logger.info("Web scheduler started")
        asyncio.create_task(self.scheduler_loop())

    async def stop(self):
        """Stop the scheduler loop."""
        self.running = False
        logger.info("Web scheduler stopped")

    async def scheduler_loop(self):
        """Main scheduler loop - checks every minute."""
        await self.bot.wait_until_ready()

        while self.running and not self.bot.is_closed():
            try:
                await self.process_due_schedules()
            except Exception as e:
                logger.error("Error in web scheduler loop", exc_info=e)

            # Sleep for 60 seconds
            await asyncio.sleep(60)

    async def process_due_schedules(self):
        """Process schedules that are due to be sent."""
        now_utc = datetime.utcnow()

        async with self.SessionLocal() as db:
            # Find all enabled schedules that are due
            result = await db.execute(
                select(Schedule)
                .where(Schedule.enabled == True, Schedule.next_run_utc <= now_utc)
                .order_by(Schedule.next_run_utc)
            )
            schedules = result.scalars().all()

            for schedule in schedules:
                try:
                    await self.post_reminder(schedule, db)
                    await self.update_next_run(schedule, db)
                except Exception as e:
                    logger.error(f"Error posting reminder for schedule {schedule.id}", exc_info=e)

    async def post_reminder(self, schedule: Schedule, db: AsyncSession):
        """Post a territory defense reminder."""
        # Get guild
        guild = self.bot.get_guild(int(schedule.guild_id))
        if not guild:
            logger.warning(f"Guild {schedule.guild_id} not found for schedule {schedule.id}")
            schedule.enabled = False
            await db.commit()
            return

        # Get channel
        if not schedule.channel_id:
            logger.warning(f"No channel configured for schedule {schedule.id}")
            schedule.enabled = False
            await db.commit()
            return

        channel = guild.get_channel(int(schedule.channel_id))
        if not channel:
            logger.warning(f"Channel {schedule.channel_id} not found for schedule {schedule.id}")
            schedule.enabled = False
            await db.commit()
            return

        # Get template
        result = await db.execute(select(Template).where(Template.id == schedule.template_id))
        template = result.scalar_one_or_none()
        if not template:
            logger.warning(f"Template {schedule.template_id} not found for schedule {schedule.id}")
            schedule.enabled = False
            await db.commit()
            return

        # Get guild config for role_id
        result = await db.execute(select(GuildConfig).where(GuildConfig.guild_id == schedule.guild_id))
        guild_config = result.scalar_one_or_none()
        role_id = guild_config.role_id if guild_config else None

        # Render template
        message_content = render_template(template.content, schedule.system_name, role_id)

        # Send message
        try:
            await channel.send(message_content)
            logger.info(f"Posted reminder for schedule {schedule.id} in guild {schedule.guild_id}")
        except Exception as e:
            logger.error(f"Failed to send message for schedule {schedule.id}", exc_info=e)
            raise

    async def update_next_run(self, schedule: Schedule, db: AsyncSession):
        """Update the next run time for a recurring schedule."""
        # Get timezone
        timezone = ZoneInfo(schedule.timezone)

        # Parse the time
        hour, minute = map(int, schedule.time_local.split(":"))

        # Get current time in the schedule's timezone
        now = datetime.now(timezone)

        # Calculate next week's occurrence
        days_ahead = 7  # Always go to next week since we just ran

        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)

        # Apply advance minutes
        next_run = next_run - timedelta(minutes=schedule.advance_minutes)

        # Convert to UTC
        next_run_utc = next_run.astimezone(ZoneInfo("UTC"))

        # Update schedule
        schedule.next_run_utc = next_run_utc.replace(tzinfo=None)  # Store as naive UTC
        await db.commit()

        logger.info(
            f"Updated next run for schedule {schedule.id} to {schedule.next_run_utc} UTC "
            f"({schedule.time_local} {schedule.timezone})"
        )


async def setup_web_scheduler(bot: Bot) -> WebScheduler:
    """Set up and start the web scheduler."""
    scheduler = WebScheduler(bot)
    await scheduler.start()
    return scheduler
