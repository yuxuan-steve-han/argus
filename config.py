import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM backend ────────────────────────────────────────────────────────────────
LLM_BACKEND          = os.getenv("LLM_BACKEND", "claude").lower()  # "claude" or "ollama"
LLM_COOLDOWN_SECONDS = int(os.getenv("LLM_COOLDOWN_SECONDS", "30"))

# Claude
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
CLAUDE_MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "256"))

# Ollama
OLLAMA_URL     = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "qwen2.5vl:32b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "60"))

# ── Motion detection ────────────────────────────────────────────────────────────
MOTION_THRESHOLD  = int(os.getenv("MOTION_THRESHOLD", "5000"))
MOG2_HISTORY      = int(os.getenv("MOG2_HISTORY", "500"))
MOG2_VAR_THRESHOLD = int(os.getenv("MOG2_VAR_THRESHOLD", "50"))

# ── Image quality (1–100) ───────────────────────────────────────────────────────
JPEG_QUALITY_ANALYSIS = int(os.getenv("JPEG_QUALITY_ANALYSIS", "80"))  # sent to LLM
JPEG_QUALITY_ALERT    = int(os.getenv("JPEG_QUALITY_ALERT", "85"))     # sent via Discord
JPEG_QUALITY_STREAM   = int(os.getenv("JPEG_QUALITY_STREAM", "70"))    # web MJPEG stream
JPEG_QUALITY_STORAGE  = int(os.getenv("JPEG_QUALITY_STORAGE", "90"))   # saved to disk

# ── Alerts ──────────────────────────────────────────────────────────────────────
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_TIMEOUT     = int(os.getenv("DISCORD_TIMEOUT", "15"))

# ── Cameras & server ────────────────────────────────────────────────────────────
CAMERA_URLS          = [url.strip() for url in os.getenv("CAMERA_URLS", "").split(",") if url.strip()]
FLASK_PORT           = int(os.getenv("FLASK_PORT", "5000"))
MONITOR_LOOP_INTERVAL = float(os.getenv("MONITOR_LOOP_INTERVAL", "0.1"))
DASHBOARD_REFRESH_RATE = float(os.getenv("DASHBOARD_REFRESH_RATE", "2.0"))
