# Quick Start Guide

This guide will help you get the Locutus Territory Defense Scheduler up and running quickly.

## Prerequisites

- Python 3.13 or higher
- A Discord bot account
- Discord OAuth2 credentials (for web UI)

## Step 1: Clone and Install

```bash
git clone https://github.com/ComputerEndProgram/locutus.git
cd locutus
python3.13 -m pip install -r requirements.txt
```

## Step 2: Configure Discord Bot

1. Create a Discord application at https://discord.com/developers/applications
2. Create a bot and copy the token
3. Enable these intents:
   - SERVER MEMBERS INTENT
   - MESSAGE CONTENT INTENT
4. Generate an invite URL with these permissions:
   - Read Messages/View Channels
   - Send Messages
   - Send Messages in Thread
   - Mention Everyone (for role mentions)

## Step 3: Configure OAuth (for Web UI)

1. In your Discord application, go to OAuth2 → General
2. Add redirect URL: `http://localhost:8000/oauth/callback`
3. Copy your Client ID and Client Secret

## Step 4: Create Configuration

Copy the example environment file and edit it:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```dotenv
# Bot Configuration (Required)
TOKEN=your_bot_token_here
PREFIX=!
SYNC_SLASH_COMMANDS=on
DEFAULT_TIMEZONE=America/New_York

# Web UI Configuration (Optional but recommended)
LOCUTUS_BASE_URL=http://localhost:8000
DISCORD_CLIENT_ID=your_client_id_here
DISCORD_CLIENT_SECRET=your_client_secret_here
DISCORD_OAUTH_REDIRECT_URI=http://localhost:8000/oauth/callback
SESSION_SECRET=generate_random_string_here
WEB_UI_PORT=8000
```

**Generate a strong session secret:**
```bash
openssl rand -hex 32
```

## Step 5: Start the Bot

```bash
python3.13 start.py
```

The bot will:
- Connect to Discord
- Load the scheduler
- Start the web scheduler (if configured)

## Step 6: Start the Web UI (Optional)

In a separate terminal:

```bash
python3.13 start_web.py
```

Then open your browser to http://localhost:8000

## Step 7: Configure Territory Defense Reminders

1. Login to the web UI with Discord OAuth
2. Select a guild where you have "Manage Server" permission
3. Configure guild settings:
   - Set the timezone (e.g., `Europe/Berlin`)
   - Set the role ID for mentions
   - Choose a default channel
4. Go to "Create Reminder" tab:
   - Choose a template
   - Enter system name (e.g., "Sol System")
   - Select weekday and time
   - Set advance minutes if desired (e.g., 10 minutes before)
5. Save the reminder

## Testing the Setup

### Test the Bot

Use Discord slash commands:
```
/schedule create
```

### Test the Web UI

1. Visit http://localhost:8000
2. Login with Discord
3. Try creating a test reminder

### Run Tests

```bash
python3.13 -m unittest discover tests -v
```

## Troubleshooting

### Bot won't start
- Check that TOKEN is set correctly in `.env`
- Verify Python version is 3.13+
- Check Discord intents are enabled

### Web UI shows "OAuth credentials not set"
- Verify DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET are set
- Check that redirect URI matches in Discord app settings

### Reminders not posting
- Verify bot has permission to send messages in the channel
- Check channel ID is correct
- Verify role ID exists in the guild
- Check bot logs for errors

### Timezone issues
- Use IANA timezone names (e.g., `America/New_York`, not `EST`)
- Test with: `python3 -c "from zoneinfo import ZoneInfo; print(ZoneInfo('YOUR_TIMEZONE'))"`

## Production Deployment

For production:

1. Use a reverse proxy (Caddy or Nginx) with SSL
2. Update LOCUTUS_BASE_URL to your domain
3. Update DISCORD_OAUTH_REDIRECT_URI to match
4. Use a strong SESSION_SECRET
5. Consider using PostgreSQL instead of SQLite
6. Run both bot and web UI as services (systemd, supervisor, etc.)

See [CONFIGURATION.md](CONFIGURATION.md) for detailed configuration options.

## Next Steps

- Customize templates in the web UI
- Set up multiple guilds
- Configure different timezones per guild
- Use advance notifications for early warnings

## Getting Help

- Check the [README](../README.md) for detailed documentation
- Review [CONFIGURATION.md](CONFIGURATION.md) for all options
- Report issues on GitHub

Enjoy your automated territory defense reminders! 🛸
