"""
web_app.py

FastAPI web application for territory defense reminder management.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
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

logger = logging.getLogger(__name__)

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


async def get_user_guilds(access_token: str) -> list[dict[str, Any]]:
    """Fetch user's guilds from Discord API."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://discord.com/api/v10/users/@me/guilds",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code != 200:
            logger.error("Failed to fetch guilds: %s", response.text)
            return []
        return response.json()


def filter_manageable_guilds(guilds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter guilds where user has Manage Guild permission."""
    MANAGE_GUILD = 0x00000020
    return [guild for guild in guilds if int(guild.get("permissions", 0)) & MANAGE_GUILD]


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
    """List guilds the user can manage."""
    guilds = await get_user_guilds(session_data["access_token"])
    manageable_guilds = filter_manageable_guilds(guilds)

    return templates.TemplateResponse(
        "guilds.html",
        {
            "request": request,
            "guilds": manageable_guilds,
            "username": session_data["username"],
        },
    )


@app.get("/guild/{guild_id}", response_class=HTMLResponse)
async def guild_page(
    request: Request,
    guild_id: str,
    session_data: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Guild management page."""
    # Verify user has access to this guild
    guilds = await get_user_guilds(session_data["access_token"])
    manageable_guilds = filter_manageable_guilds(guilds)

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

    return templates.TemplateResponse(
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


@app.post("/guild/{guild_id}/config/update")
async def update_guild_config(
    request: Request,
    guild_id: str,
    session_data: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Update guild configuration."""
    # Verify access
    guilds = await get_user_guilds(session_data["access_token"])
    manageable_guilds = filter_manageable_guilds(guilds)
    if not any(g["id"] == guild_id for g in manageable_guilds):
        raise HTTPException(status_code=403, detail="Access denied")

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
    guilds = await get_user_guilds(session_data["access_token"])
    manageable_guilds = filter_manageable_guilds(guilds)
    if not any(g["id"] == guild_id for g in manageable_guilds):
        raise HTTPException(status_code=403, detail="Access denied")

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
    guilds = await get_user_guilds(session_data["access_token"])
    manageable_guilds = filter_manageable_guilds(guilds)
    if not any(g["id"] == guild_id for g in manageable_guilds):
        raise HTTPException(status_code=403, detail="Access denied")

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
    guilds = await get_user_guilds(session_data["access_token"])
    manageable_guilds = filter_manageable_guilds(guilds)
    if not any(g["id"] == guild_id for g in manageable_guilds):
        raise HTTPException(status_code=403, detail="Access denied")

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
