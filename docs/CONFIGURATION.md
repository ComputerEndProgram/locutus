# Locutus Configuration Guide

This document explains the configuration options for the Locutus Territory Defense Scheduler.

## Environment Variables

All configuration is done through environment variables in the `.env` file.

### Required Variables (Bot)

- `TOKEN`: Your Discord bot token (required)
- `PREFIX`: Command prefix for text commands (default: `=`)
- `SYNC_SLASH_COMMANDS`: Whether to sync slash commands on startup (`on` or `off`)
- `DEFAULT_TIMEZONE`: Default timezone for parsing times (default: `America/Vancouver`)

### Optional Variables (Web UI)

These are required if you want to use the web-based territory defense scheduler:

- `LOCUTUS_BASE_URL`: Base URL for your web server (e.g., `https://locutus.example.com`)
- `DISCORD_CLIENT_ID`: Discord OAuth2 client ID
- `DISCORD_CLIENT_SECRET`: Discord OAuth2 client secret
- `DISCORD_OAUTH_REDIRECT_URI`: OAuth redirect URI (must match Discord app settings)
- `SESSION_SECRET`: Secret key for signing session cookies (generate a random string)
- `DATABASE_URL`: Database connection URL (default: `sqlite:///./locutus.db`)
- `WEB_UI_PORT`: Port for the web server (default: `8000`)

## Discord OAuth Setup

To enable the web UI:

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your bot application
3. Navigate to **OAuth2** → **General**
4. Add a redirect URL matching your `DISCORD_OAUTH_REDIRECT_URI`
   - For local development: `http://localhost:8000/oauth/callback`
   - For production: `https://yourdomain.com/oauth/callback`
5. Copy your Client ID and Client Secret to `.env`

## Territory Defense Reminder Features

### Templates

Templates support the following placeholders:

- `{system_name}`: The name of the system for the defense
- `{role_id}`: The Discord role ID to mention (e.g., `<@&{role_id}>`)

Example template:
```
**🛸 Territory Defense Notification: {system_name}**

<@&{role_id}>

A Territory Defense is scheduled in **{system_name}**.

— Transmission complete.
```

### Advance Notifications

You can configure reminders to be sent before the scheduled time:

- Set `advance_minutes` to `10` to send the reminder 10 minutes before
- Set to `0` for exact time
- Maximum: 1440 minutes (24 hours)

### Timezone Support

All schedules use IANA timezone names for accurate DST handling:

- `America/New_York` (Eastern Time)
- `America/Los_Angeles` (Pacific Time)
- `Europe/London` (UK Time)
- `Europe/Berlin` (Central European Time)
- `Asia/Tokyo` (Japan Time)

Full list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones

### Multi-Guild Support

Each guild has separate:

- Configuration (timezone, role ID, default channel)
- Templates
- Schedules

Users must have "Manage Server" permission to configure reminders for a guild.

## Database

By default, the bot uses SQLite for storage:

- Bot schedules: `data/schedule.db`
- Web UI data: `locutus.db`

For production, you can use a different database by setting `DATABASE_URL`:

```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/locutus
```

## Security Considerations

1. **Never commit `.env` to version control** - it contains secrets
2. **Generate a strong SESSION_SECRET** - use `openssl rand -hex 32`
3. **Use HTTPS in production** - set up a reverse proxy with SSL
4. **Restrict database access** - use appropriate file permissions or database auth
5. **Keep dependencies updated** - regularly update packages for security fixes

## Reverse Proxy Setup

For production deployment behind a reverse proxy:

### Caddy (Recommended)

```
locutus.example.com {
    reverse_proxy localhost:8000
}
```

### Nginx

```nginx
server {
    listen 80;
    server_name locutus.example.com;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Don't forget to update `LOCUTUS_BASE_URL` and `DISCORD_OAUTH_REDIRECT_URI` to match your domain!
