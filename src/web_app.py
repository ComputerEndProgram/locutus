"""
web_app.py

FastAPI web application for territory defense reminder management.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.env import (
    DISCORD_CLIENT_ID,
    DISCORD_CLIENT_SECRET,
    DISCORD_OAUTH_REDIRECT_URI,
    SESSION_SECRET,
    LOCUTUS_BASE_URL,
)
from src.web_db import GuildConfig, Template, Schedule, get_session_maker, init_db, get_engine
from src.template_utils import ensure_guild_has_templates
from src.bot_state import read_bot_guild_ids

logger = logging.getLogger(__name__)

# Guild cache TTL in seconds (30 seconds to avoid hitting Discord rate limits)
GUILD_CACHE_TTL = 30

# FastAPI app
app = FastAPI(title="Locutus Territory Defense Scheduler")

# Templates
templates = Jinja2Templates(directory="templates")

# Session serializer
serializer = URLSafeTimedSerializer(SESSION_SECRET)

# Database
engine = get_engine()
SessionLocal = get_session_maker(engine)


# Dependency to get DB session
async def get_db():
    """Get database session."""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Session management
def get_session_data(request: Request) -> dict[str, Any] | None:
    """Get session data from cookie."""
    session_cookie = request.cookies.get("session")
    if not session_cookie:
        return None
    try:
        return serializer.loads(session_cookie, max_age=86400 * 7)  # 7 days
    except BadSignature:
        return None


def create_session_cookie(data: dict[str, Any]) -> str:
    """Create a signed session cookie."""
    return serializer.dumps(data)


async def require_auth(request: Request) -> dict[str, Any]:
    """Require authentication, raise 401 if not authenticated."""
    session_data = get_session_data(request)
    if not session_data:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session_data


async def get_user_guilds(access_token: str, cached_guilds: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """
    Fetch user's guilds from Discord API with rate limit handling.
    
    Args:
        access_token: Discord OAuth access token
        cached_guilds: Previously cached guild list to fall back to on rate limit
        
    Returns:
        List of guild dictionaries, or empty list only on auth failure
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://discord.com/api/v10/users/@me/guilds",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        
        # Success case
        if response.status_code == 200:
            return response.json()
        
        # Rate limit case
        if response.status_code == 429:
            try:
                retry_data = response.json()
                retry_after = retry_data.get("retry_after", 1.0)
                logger.warning(f"Discord rate limit hit, retry after {retry_after}s")
                
                # Wait and retry once
                await asyncio.sleep(retry_after)
                retry_response = await client.get(
                    "https://discord.com/api/v10/users/@me/guilds",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                
                if retry_response.status_code == 200:
                    return retry_response.json()
                
                # Still rate limited after retry, fall back to cache
                if retry_response.status_code == 429:
                    logger.warning("Still rate limited after retry, using cached guilds")
                    if cached_guilds is not None:
                        return cached_guilds
                    logger.error("No cached guilds available during rate limit")
                    return []
                    
            except Exception as e:
                logger.error(f"Error handling rate limit: {e}")
                if cached_guilds is not None:
                    return cached_guilds
                return []
        
        # Auth failure cases (401, 403) - return empty
        if response.status_code in (401, 403):
            logger.error(f"Authentication failed: {response.status_code}")
            return []
        
        # Other errors - log and try to use cache
        logger.error(f"Failed to fetch guilds: {response.status_code} - {response.text}")
        if cached_guilds is not None:
            logger.info("Using cached guilds due to API error")
            return cached_guilds
        return []


def filter_manageable_guilds(guilds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter guilds where user has Manage Guild permission."""
    MANAGE_GUILD = 0x00000020
    return [guild for guild in guilds if int(guild.get("permissions", 0)) & MANAGE_GUILD]


def get_bot_guild_ids() -> set[str]:
    """
    Get the set of guild IDs where the bot is currently present.
    Reads from shared state file written by bot process.
    
    Returns:
        Set of guild ID strings, or empty set if unavailable
    """
    # First check if callback is available (for testing or advanced integration)
    if hasattr(app.state, "get_bot_guild_ids"):
        try:
            return app.state.get_bot_guild_ids()
        except Exception as e:
            logger.warning(f"Failed to get bot guild IDs from callback: {e}")
    
    # Fall back to reading from state file
    return read_bot_guild_ids()


def filter_bot_guilds(guilds: list[dict[str, Any]], bot_guild_ids: set[str] | None = None) -> list[dict[str, Any]]:
    """
    Filter guilds to only those where the bot is present.
    
    Args:
        guilds: List of guild dictionaries
        bot_guild_ids: Set of guild IDs where bot is present (if None, fetches from state)
        
    Returns:
        Filtered list of guilds
    """
    if bot_guild_ids is None:
        bot_guild_ids = get_bot_guild_ids()
    
    # If no bot guild data available, return all (degraded mode)
    if not bot_guild_ids:
        logger.warning("Bot guild IDs not available, showing all manageable guilds")
        return guilds
    
    return [guild for guild in guilds if guild.get("id") in bot_guild_ids]


async def verify_guild_access(guild_id: str, session_data: dict[str, Any]) -> None:
    """
    Verify that the user has access to the specified guild.
    Raises HTTPException(403) if access is denied.
    
    Args:
        guild_id: Guild ID to check access for
        session_data: Current session data with access token
    """
    manageable_guilds, _ = await get_manageable_guilds_with_cache(
        session_data, use_cache=True, filter_by_bot=True
    )
    if not any(g["id"] == guild_id for g in manageable_guilds):
        raise HTTPException(status_code=403, detail="Access denied")


async def get_manageable_guilds_with_cache(
    session_data: dict[str, Any],
    use_cache: bool = True,
    filter_by_bot: bool = True
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Get manageable guilds with caching support.
    
    Args:
        session_data: Current session data
        use_cache: Whether to use cached data if available and fresh
        filter_by_bot: Whether to filter by bot presence
        
    Returns:
        Tuple of (guilds list, updated session data)
    """
    cached_guilds = session_data.get("cached_guilds")
    cache_timestamp = session_data.get("guild_cache_timestamp")
    
    # Check if cache is still valid
    cache_valid = False
    if use_cache and cached_guilds is not None and cache_timestamp is not None:
        try:
            cache_age = datetime.now(timezone.utc).timestamp() - cache_timestamp
            cache_valid = cache_age < GUILD_CACHE_TTL
        except (TypeError, ValueError):
            pass
    
    # Use cache if valid
    if cache_valid:
        guilds = cached_guilds
    else:
        # Fetch fresh data from Discord
        access_token = session_data["access_token"]
        all_guilds = await get_user_guilds(access_token, cached_guilds)
        guilds = filter_manageable_guilds(all_guilds)
        
        # Update cache in session
        session_data["cached_guilds"] = guilds
        session_data["guild_cache_timestamp"] = datetime.now(timezone.utc).timestamp()
    
    # Filter by bot presence if requested
    if filter_by_bot:
        guilds = filter_bot_guilds(guilds)
    
    return guilds, session_data


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    await init_db(engine)
    logger.info("Web application started")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Home page."""
    session_data = get_session_data(request)
    return templates.TemplateResponse("index.html", {"request": request, "logged_in": session_data is not None})


@app.get("/login")
async def login():
    """Start Discord OAuth flow."""
    oauth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={DISCORD_OAUTH_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify+guilds"
    )
    return RedirectResponse(oauth_url)


@app.get("/oauth/callback")
async def oauth_callback(code: str, request: Request):
    """Handle OAuth callback."""
    async with httpx.AsyncClient() as client:
        # Exchange code for access token
        token_response = await client.post(
            "https://discord.com/api/v10/oauth2/token",
            data={
                "client_id": DISCORD_CLIENT_ID,
                "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": DISCORD_OAUTH_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if token_response.status_code != 200:
            logger.error("OAuth token exchange failed: %s", token_response.text)
            raise HTTPException(status_code=400, detail="OAuth failed")

        token_data = token_response.json()
        access_token = token_data["access_token"]

        # Fetch user info
        user_response = await client.get(
            "https://discord.com/api/v10/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if user_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch user info")

        user_data = user_response.json()

    # Create session
    session_data = {
        "user_id": user_data["id"],
        "username": user_data["username"],
        "access_token": access_token,
    }

    response = RedirectResponse(url="/guilds", status_code=303)
    response.set_cookie(
        key="session",
        value=create_session_cookie(session_data),
        httponly=True,
        max_age=86400 * 7,  # 7 days
        samesite="lax",
    )
    return response


@app.get("/logout")
async def logout():
    """Logout and clear session."""
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key="session")
    return response


@app.get("/guilds", response_class=HTMLResponse)
async def list_guilds(request: Request, session_data: dict = Depends(require_auth)):
    """List guilds the user can manage (filtered to guilds where bot is present)."""
    manageable_guilds, updated_session = await get_manageable_guilds_with_cache(
        session_data, use_cache=True, filter_by_bot=True
    )
    
    # Update session cookie if cache was updated
    response = templates.TemplateResponse(
        "guilds.html",
        {
            "request": request,
            "guilds": manageable_guilds,
            "username": session_data["username"],
        },
    )
    
    # Only update cookie if session data changed
    if updated_session != session_data:
        response.set_cookie(
            key="session",
            value=create_session_cookie(updated_session),
            httponly=True,
            max_age=86400 * 7,  # 7 days
            samesite="lax",
        )
    
    return response


@app.get("/guild/{guild_id}", response_class=HTMLResponse)
async def guild_page(
    request: Request,
    guild_id: str,
    session_data: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Guild management page."""
    # Verify user has access to this guild
    manageable_guilds, updated_session = await get_manageable_guilds_with_cache(
        session_data, use_cache=True, filter_by_bot=True
    )

    guild = next((g for g in manageable_guilds if g["id"] == guild_id), None)
    if not guild:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get or create guild config
    result = await db.execute(select(GuildConfig).where(GuildConfig.guild_id == guild_id))
    guild_config = result.scalar_one_or_none()

    if not guild_config:
        guild_config = GuildConfig(guild_id=guild_id)
        db.add(guild_config)
        await db.commit()
        await db.refresh(guild_config)

    # Ensure guild has templates
    await ensure_guild_has_templates(db, guild_id)

    # Get templates
    result = await db.execute(select(Template).where(Template.guild_id == guild_id))
    templates_list = result.scalars().all()

    # Get schedules
    result = await db.execute(select(Schedule).where(Schedule.guild_id == guild_id))
    schedules = result.scalars().all()

    response = templates.TemplateResponse(
        "guild.html",
        {
            "request": request,
            "guild": guild,
            "guild_config": guild_config,
            "templates": templates_list,
            "schedules": schedules,
            "username": session_data["username"],
        },
    )
    
    # Update session cookie if cache was updated
    if updated_session != session_data:
        response.set_cookie(
            key="session",
            value=create_session_cookie(updated_session),
            httponly=True,
            max_age=86400 * 7,
            samesite="lax",
        )
    
    return response


@app.post("/guild/{guild_id}/config/update")
async def update_guild_config(
    request: Request,
    guild_id: str,
    session_data: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Update guild configuration."""
    # Verify access
    await verify_guild_access(guild_id, session_data)

    form_data = await request.form()
    
    # Get or create guild config
    result = await db.execute(select(GuildConfig).where(GuildConfig.guild_id == guild_id))
    guild_config = result.scalar_one_or_none()

    if not guild_config:
        guild_config = GuildConfig(guild_id=guild_id)
        db.add(guild_config)

    # Update fields
    guild_config.timezone = form_data.get("timezone", "UTC")
    guild_config.role_id = form_data.get("role_id") or None
    guild_config.default_channel_id = form_data.get("default_channel_id") or None

    await db.commit()
    return RedirectResponse(url=f"/guild/{guild_id}", status_code=303)


@app.post("/guild/{guild_id}/template/create")
async def create_template(
    request: Request,
    guild_id: str,
    session_data: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Create a new template."""
    # Verify access
    await verify_guild_access(guild_id, session_data)

    form_data = await request.form()

    # If setting as default, unset other defaults
    is_default = form_data.get("is_default") == "1"
    if is_default:
        result = await db.execute(select(Template).where(Template.guild_id == guild_id))
        for template in result.scalars():
            template.is_default = False

    # Create new template
    template = Template(
        guild_id=guild_id,
        name=form_data["name"],
        content=form_data["content"],
        is_default=is_default,
    )
    db.add(template)
    await db.commit()

    return RedirectResponse(url=f"/guild/{guild_id}", status_code=303)


@app.post("/guild/{guild_id}/schedule/create")
async def create_schedule(
    request: Request,
    guild_id: str,
    session_data: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Create a new schedule."""
    # Verify access
    await verify_guild_access(guild_id, session_data)

    form_data = await request.form()

    # Get guild config for timezone
    result = await db.execute(select(GuildConfig).where(GuildConfig.guild_id == guild_id))
    guild_config = result.scalar_one_or_none()
    if not guild_config:
        raise HTTPException(status_code=400, detail="Guild config not found")

    # Parse form data
    template_id = int(form_data["template_id"])
    system_name = form_data["system_name"]
    weekday = int(form_data["weekday"])
    time_local = form_data["time_local"]  # HH:MM format
    advance_minutes = int(form_data.get("advance_minutes", 0))
    channel_id = form_data.get("channel_id") or guild_config.default_channel_id

    # Calculate next run time
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    timezone = ZoneInfo(guild_config.timezone)
    now = datetime.now(timezone)
    
    # Parse time
    hour, minute = map(int, time_local.split(":"))
    
    # Find next occurrence of the weekday
    days_ahead = weekday - now.weekday()
    if days_ahead < 0:  # Target day already happened this week
        days_ahead += 7
    elif days_ahead == 0:  # Today
        # Check if the time has already passed
        target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now >= target_time:
            days_ahead = 7
    
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
    
    # Apply advance minutes (subtract from the scheduled time)
    next_run = next_run - timedelta(minutes=advance_minutes)
    
    # Convert to UTC
    next_run_utc = next_run.astimezone(ZoneInfo("UTC"))

    # Create schedule
    schedule = Schedule(
        guild_id=guild_id,
        template_id=template_id,
        system_name=system_name,
        weekday=weekday,
        time_local=time_local,
        timezone=guild_config.timezone,
        channel_id=channel_id,
        enabled=True,
        created_by_user_id=session_data["user_id"],
        next_run_utc=next_run_utc.replace(tzinfo=None),  # Store as naive UTC
        advance_minutes=advance_minutes,
    )
    db.add(schedule)
    await db.commit()

    return RedirectResponse(url=f"/guild/{guild_id}", status_code=303)


@app.post("/guild/{guild_id}/schedule/{schedule_id}/delete")
async def delete_schedule(
    guild_id: str,
    schedule_id: int,
    session_data: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Delete a schedule."""
    # Verify access
    await verify_guild_access(guild_id, session_data)

    result = await db.execute(select(Schedule).where(Schedule.id == schedule_id, Schedule.guild_id == guild_id))
    schedule = result.scalar_one_or_none()
    
    if schedule:
        await db.delete(schedule)
        await db.commit()

    return {"status": "ok"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
