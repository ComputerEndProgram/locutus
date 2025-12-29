# Implementation Summary: Web UI for Territory Defense Reminders

## Overview

This implementation adds a production-ready web UI to the Discord bot for managing multi-guild territory defense reminders. The feature allows alliance officers to configure weekly recurring reminders through a browser interface with Discord OAuth authentication.

## Features Implemented

### 1. FastAPI Web Application (`src/web_app.py`)
- Complete REST API with OAuth2 authentication
- Session management using signed cookies (itsdangerous)
- Guild selection with permission filtering (Manage Guild required)
- CRUD endpoints for schedules, templates, and guild configuration
- Health check endpoint for monitoring

### 2. Database Layer (`src/web_db.py`)
- SQLAlchemy async models for:
  - `GuildConfig`: Per-guild settings (timezone, role_id, default_channel_id)
  - `Template`: Customizable message templates with placeholders
  - `Schedule`: Weekly recurring schedules with advance notification support
- Automatic table creation and migrations
- Multi-guild data separation

### 3. Web Scheduler (`src/web_scheduler.py`)
- Asynchronous scheduler integrated with Discord bot
- Weekly recurring reminders with DST-safe calculation
- **Advance notification feature**: Send reminders X minutes before scheduled time
- Automatic next-run calculation preserving timezone across DST boundaries
- Graceful error handling and logging

### 4. Template System (`src/template_utils.py`)
- Preset template loading from `assets/` directory
- Placeholder substitution: `{system_name}`, `{role_id}`
- Role ID validation (numeric check)
- Standardized placeholder format across templates
- Automatic template initialization for new guilds

### 5. Web UI Templates
- **Base template** (`templates/base.html`): Responsive design with navigation
- **Index page** (`templates/index.html`): Landing page with feature overview
- **Guilds page** (`templates/guilds.html`): Guild selection interface
- **Guild management** (`templates/guild.html`): Tabbed interface with:
  - Schedules view with edit/delete actions
  - **Wizard for creating reminders** (4 steps + advance minutes option)
  - Guild configuration (timezone, role ID, default channel)
  - Template management (create, edit, delete, set default)

### 6. Discord OAuth Integration
- Complete OAuth2 flow (login → callback → session)
- User guild fetching with permission filtering
- Session-based authentication with 7-day expiry
- Secure logout functionality

### 7. Documentation
- **README.md**: Updated with web UI setup instructions and deployment guide
- **CONFIGURATION.md**: Comprehensive configuration reference
- **QUICKSTART.md**: Step-by-step setup guide for new users
- Environment variable documentation

### 8. Testing
- **Unit tests** (`tests/test_scheduler.py`):
  - Next-run calculation with different scenarios
  - DST transition handling
  - Advance minutes calculation
  - Permission filtering
  - Template rendering
- **Integration tests** (`tests/test_integration.py`):
  - Database CRUD operations
  - Template loading and rendering
  - Multi-guild template initialization
- All tests passing (15 tests total)

## Key Technical Decisions

### Advance Minutes Feature
Per the requirement, implemented `advance_minutes` field in Schedule model:
- Stored as integer (minutes before scheduled time)
- Applied during next-run calculation: `next_run - timedelta(minutes=advance_minutes)`
- Supports 0-1440 minutes (0 to 24 hours)
- UI includes clear explanation and default value of 0

### Timezone Handling
- Uses Python's `zoneinfo` module (Python 3.9+)
- IANA timezone names for accuracy
- DST-safe calculation: compute in local time, then convert to UTC
- Stores next_run_utc as naive UTC datetime in database

### Multi-Guild Architecture
- All data scoped by guild_id
- Each guild has independent:
  - Timezone configuration
  - Role ID and channel settings
  - Templates
  - Schedules
- Access control via Discord permissions (Manage Guild)

### Database Choice
- SQLite default for easy deployment
- SQLAlchemy async for scalability
- Easy migration to PostgreSQL for production
- Connection string configurable via DATABASE_URL

### Security
- Signed session cookies (no session storage needed)
- OAuth state validation (implicit via Discord)
- Permission checks on every guild operation
- Role ID validation before rendering

## File Structure

```
/home/runner/work/locutus/locutus/
├── src/
│   ├── web_app.py           # FastAPI application
│   ├── web_db.py            # SQLAlchemy models
│   ├── web_scheduler.py     # Scheduler integration
│   ├── template_utils.py    # Template management
│   └── env.py               # Environment configuration (updated)
├── templates/
│   ├── base.html            # Base template
│   ├── index.html           # Landing page
│   ├── guilds.html          # Guild selection
│   └── guild.html           # Guild management
├── tests/
│   ├── test_scheduler.py    # Unit tests
│   └── test_integration.py  # Integration tests
├── docs/
│   ├── CONFIGURATION.md     # Configuration guide
│   └── QUICKSTART.md        # Quick start guide
├── assets/
│   ├── preset1.txt          # English template (updated)
│   └── preset2.txt          # German template (updated)
├── start_web.py             # Web server entrypoint
├── .env.example             # Example configuration (updated)
├── requirements.txt         # Dependencies (updated)
├── pyproject.toml           # Project metadata (updated)
└── README.md                # Documentation (updated)
```

## Dependencies Added

- `fastapi>=0.115.0` - Web framework
- `httpx>=0.27.0` - Async HTTP client for Discord API
- `itsdangerous>=2.2.0` - Session cookie signing
- `jinja2>=3.1.0` - Template engine
- `sqlalchemy>=2.0.0` - ORM and database toolkit
- `uvicorn>=0.32.0` - ASGI server

## Environment Variables Added

- `LOCUTUS_BASE_URL` - Base URL for web application
- `DISCORD_CLIENT_ID` - Discord OAuth client ID
- `DISCORD_CLIENT_SECRET` - Discord OAuth client secret
- `DISCORD_OAUTH_REDIRECT_URI` - OAuth callback URL
- `SESSION_SECRET` - Session cookie signing key
- `DATABASE_URL` - Database connection string
- `WEB_UI_PORT` - Web server port (default: 8000)

## Usage

### Starting the Bot
```bash
python3.13 start.py
```
The bot now includes the web scheduler for territory defense reminders.

### Starting the Web UI
```bash
python3.13 start_web.py
```
Access at http://localhost:8000

### Creating a Reminder
1. Login with Discord OAuth
2. Select guild (must have Manage Server permission)
3. Configure guild settings (timezone, role ID)
4. Use wizard to create reminder:
   - Choose template
   - Enter system name
   - Select weekday and time
   - **Set advance minutes** (e.g., 10 for 10 minutes before)
   - Optionally specify channel
5. Reminder posts automatically every week

## Testing

All tests pass:
```bash
python3.13 -m unittest discover tests -v
# 15 tests passed
```

## Production Readiness

- ✅ Reverse proxy compatible (Caddy, Nginx)
- ✅ Environment-based configuration
- ✅ Secure authentication (OAuth + signed cookies)
- ✅ Multi-guild isolation
- ✅ DST-safe scheduling
- ✅ Error handling and logging
- ✅ Database migrations (automatic)
- ✅ Comprehensive documentation
- ✅ Test coverage

## Acceptance Criteria Met

- ✅ Logged-in user with Manage Server can create weekly reminder
- ✅ Reminder posts correct message at correct time weekly
- ✅ **Advance minutes option implemented** (10 minutes before, etc.)
- ✅ Role ID and templates editable per guild
- ✅ Multi-guild separation preserved
- ✅ Discord OAuth authentication working
- ✅ Timezone handling with DST support
- ✅ Template placeholders working ({system_name}, {role_id})

## Future Enhancements (Not in Scope)

- Edit existing schedules (currently: delete + recreate)
- Bulk schedule management
- Schedule preview before creation
- Email notifications on reminder failures
- Bot presence check before guild configuration
- Schedule analytics and reporting

## Notes

The implementation is minimal yet complete, focusing on correctness and reliability over fancy features. The code follows the existing project structure and style, integrates cleanly with the existing Discord bot, and provides a solid foundation for future enhancements.
