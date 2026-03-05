"""
Set environment variables before any project module is imported.
This prevents monitor.py from creating log files and keeps tests hermetic.
"""
import os

os.environ.setdefault("LOG_FILE", "")               # disable file logging
os.environ.setdefault("DISCORD_WEBHOOK_URL", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("CAMERA_URLS", "")
os.environ.setdefault("LLM_BACKEND", "claude")
