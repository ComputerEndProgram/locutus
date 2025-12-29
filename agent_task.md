# Agent Task
Add web UI (Discord OAuth) wizard to manage multi-guild territory defense reminders

## Goal
Add a production-friendly Web UI to the Python bot so alliance officers can configure territory defense reminder schedules per Discord guild via a browser:
- URL example: https://locutus.example.com/login
- Auth: Discord OAuth2 login
- Authorization: user must be (a) in the guild and (b) have “Manage Server” (Manage Guild) permission in that guild to edit
- Must remain multi-guild compatible (per-guild configs/schedules)

## User-facing requirements
1) Login
- GET /login: start Discord OAuth
- GET /oauth/callback: complete OAuth, create session
- GET /logout: clear session

2) Guild selection
- After login, show list of guilds the user can manage (Manage Guild permission).
- Selecting a guild opens: /guild/<guild_id>

3) Wizard to create a territory defense reminder schedule
Wizard steps (server-rendered HTML is OK; minimal JS is fine):
- Step 1: Choose template (initially loaded from existing preset templates in assets/preset*.txt, but allow per-guild copies)
- Step 2: Enter/select system name (free text is OK; optionally a saved list per guild)
- Step 3: Choose weekday + time (weekly recurring). Must support guild timezone.
- Step 4: Confirm: show preview of rendered message (with placeholders substituted) + next run time.
- Save schedule.

4) Config tab per guild
- Set Role ID (used for <@&ROLE_ID> mention) per guild
- Select timezone per guild (IANA timezone string, e.g. Europe/Berlin)
- Manage templates per guild: list, edit, create, delete, set default
- Optional but recommended: choose announcement channel_id per schedule or per guild default

## Template rendering
- Templates may include placeholders: {system_name}, {role_id}
- The post should mention the role using Discord role mention format: <@&{role_id}>
- Fix any inconsistency between presets (ensure placeholder style is consistent)
- Validate role_id is numeric.

## Scheduling requirements
- Schedules are weekly recurring at the chosen weekday/time in the configured guild timezone.
- The bot must reliably post at the correct time even after restarts.
- Store schedules persistently (DB).
- Implement a scheduler loop or integrate with existing scheduling mechanism in the repo.
- On startup: load schedules and compute next occurrences.

## Storage
- Use SQLite (default) via SQLAlchemy (preferred) or sqlite3 if repo is simple.
- Proposed tables:
  - guild_config(guild_id TEXT PK, timezone TEXT, role_id TEXT, default_channel_id TEXT, updated_at)
  - template(id INTEGER PK, guild_id TEXT, name TEXT, content TEXT, is_default BOOL)
  - schedule(id INTEGER PK, guild_id TEXT, template_id INT, system_name TEXT, weekday INT 0-6, time_local TEXT "HH:MM", timezone TEXT, channel_id TEXT, enabled BOOL, created_by_user_id TEXT, next_run_utc TEXT)
- Migrations: lightweight (Alembic if SQLAlchemy; otherwise create tables at startup).

## Tech stack (Python)
- Web framework: FastAPI + Jinja2 templates (recommended) OR Flask (if already used).
- Sessions: signed cookie or server-side session store.
- OAuth: use a well-known Discord OAuth client library or implement via requests + itsdangerous.
- Environment variables:
  - LOCUTUS_BASE_URL (e.g. https://locutus.example.com)
  - DISCORD_CLIENT_ID
  - DISCORD_CLIENT_SECRET
  - DISCORD_OAUTH_REDIRECT_URI
  - SESSION_SECRET
  - DATABASE_URL (default sqlite:///locutus.db)

## Discord integration / permissions
- After OAuth, fetch user guilds and filter by permissions bit for Manage Guild.
- Confirm guild membership with OAuth guild list; optionally cross-check with bot’s cached guilds.
- Only allow configuration for guilds where:
  - user has Manage Guild
  - bot is present in that guild (otherwise show “invite bot” message)

## Bot integration
- Ensure the scheduler uses the same DB.
- When a schedule is created/updated via web UI, it should take effect without restart if possible (reload schedules or notify scheduler).
- Posting:
  - Render template content with {system_name}, {role_id}
  - Send to configured channel_id
  - After send, compute and persist next_run_utc (+7 days in local time, accounting for DST via timezone-aware arithmetic)

## Deliverables
- Web UI endpoints + templates
- DB layer
- Scheduler integration
- Documentation:
  - README section describing setup, env vars, and deployment behind reverse proxy (nginx/traefik)
- Basic tests for:
  - next-run calculation (DST-safe)
  - permission filtering (Manage Guild)
  - template rendering substitution

## Acceptance criteria
- A logged-in user with Manage Server can create a weekly reminder for a chosen guild in the wizard.
- Reminder posts the correct message at the correct time weekly.
- Role ID and templates can be edited per guild.
- Multi-guild separation is preserved (configs/schedules do not leak across guilds).

## Notes / hints
- Use IANA timezones and zoneinfo (Python 3.9+).
- Be careful with DST when adding “7 days”: do it in local timezone then convert to UTC for storage.
- Provide a minimal, clean UI; correctness > fancy styling.
- The web ui will be poxied via caddy revrse proxy, so ensure it is compatible.
