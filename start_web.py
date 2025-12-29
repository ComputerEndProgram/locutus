"""
start_web.py

Entrypoint for the web UI server.
Run this separately from the bot or together using a process manager.
"""

from __future__ import annotations

import logging

import uvicorn

from src.env import WEB_UI_PORT

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info(f"Starting web UI on port {WEB_UI_PORT}")
    uvicorn.run(
        "src.web_app:app",
        host="0.0.0.0",
        port=WEB_UI_PORT,
        log_level="info",
        access_log=True,
    )
