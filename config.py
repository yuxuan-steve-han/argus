import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM backend ────────────────────────────────────────────────────────────────
LLM_BACKEND          = os.getenv("LLM_BACKEND", "claude").lower()  # "claude" or "ollama"
LLM_DEBOUNCE_SECONDS = float(os.getenv("LLM_DEBOUNCE_SECONDS", "1.0"))  # gather window before firing LLM call

# Claude
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
CLAUDE_MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "256"))

# Ollama
OLLAMA_URL     = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "qwen3-vl:8b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "60"))

# ── Motion detection ────────────────────────────────────────────────────────────
MOTION_THRESHOLD  = int(os.getenv("MOTION_THRESHOLD", "5000"))
MOG2_HISTORY      = int(os.getenv("MOG2_HISTORY", "500"))
MOG2_VAR_THRESHOLD = int(os.getenv("MOG2_VAR_THRESHOLD", "50"))

# ── YOLO pre-filter ────────────────────────────────────────────────────────────
YOLO_ENABLED    = os.getenv("YOLO_ENABLED", "true").lower() in ("1", "true", "yes")
YOLO_MODEL      = os.getenv("YOLO_MODEL", "yolov8n.pt")  # nano model; fast on CPU
YOLO_CONFIDENCE = float(os.getenv("YOLO_CONFIDENCE", "0.4"))
YOLO_CLASSES    = os.getenv("YOLO_CLASSES", "person,car,truck,bus,motorcycle,bicycle,dog,cat").split(",")

# ── Image quality (1–100) ───────────────────────────────────────────────────────
JPEG_QUALITY_ANALYSIS = int(os.getenv("JPEG_QUALITY_ANALYSIS", "80"))  # trigger frame sent to LLM
JPEG_QUALITY_CONTEXT  = int(os.getenv("JPEG_QUALITY_CONTEXT",  "55"))  # context frames from other cameras
JPEG_QUALITY_ALERT    = int(os.getenv("JPEG_QUALITY_ALERT", "85"))     # sent via Discord
JPEG_QUALITY_STREAM   = int(os.getenv("JPEG_QUALITY_STREAM", "70"))    # web MJPEG stream
JPEG_QUALITY_STORAGE  = int(os.getenv("JPEG_QUALITY_STORAGE", "90"))   # saved to disk

LLM_CONTEXT_CAMERAS = int(os.getenv("LLM_CONTEXT_CAMERAS", "3"))  # max other-camera snapshots sent as context

# ── Alerts ──────────────────────────────────────────────────────────────────────
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_TIMEOUT     = int(os.getenv("DISCORD_TIMEOUT", "15"))

# ── Discord bot ────────────────────────────────────────────────────────────────
DISCORD_BOT_TOKEN   = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_BOT_MAX_TOKENS = int(os.getenv("DISCORD_BOT_MAX_TOKENS", "1024"))

# ── Home Assistant ─────────────────────────────────────────────────────────────
HASS_URL        = os.getenv("HASS_URL", "").rstrip("/")          # e.g. http://homeassistant.local:8123
HASS_TOKEN      = os.getenv("HASS_TOKEN", "")                    # Long-lived access token
HASS_WEBHOOK_ID = os.getenv("HASS_WEBHOOK_ID", "")               # Webhook trigger ID (optional, alternative to REST)
HASS_TIMEOUT    = int(os.getenv("HASS_TIMEOUT", "10"))

# ── Database ─────────────────────────────────────────────────────────────────────
DB_BACKEND          = os.getenv("DB_BACKEND", "sqlite")             # registered backend name in db.py
DB_PATH             = os.getenv("DB_PATH", "logs/security.db")
LLM_HISTORY_WINDOW  = int(os.getenv("LLM_HISTORY_WINDOW", "300"))  # seconds of history sent as context

# ── Logging ─────────────────────────────────────────────────────────────────────
LOG_FILE      = os.getenv("LOG_FILE", "logs/security.log")          # empty string to disable
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(5 * 1024 * 1024)))  # 5 MB; file is truncated on rollover

# ── Cameras & server ────────────────────────────────────────────────────────────
CAMERA_URLS          = [url.strip() for url in os.getenv("CAMERA_URLS", "").split(",") if url.strip()]
FLASK_PORT           = int(os.getenv("FLASK_PORT", "5000"))
MONITOR_LOOP_INTERVAL = float(os.getenv("MONITOR_LOOP_INTERVAL", "0.1"))
DASHBOARD_REFRESH_RATE = float(os.getenv("DASHBOARD_REFRESH_RATE", "2.0"))
