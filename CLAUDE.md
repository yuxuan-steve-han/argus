# Home Security System

A home security system with an OpenCV frontend for IP cameras that detects motion, analyzes suspicious behavior with an LLM, and sends alerts via Discord.

## Architecture

```
main.py        # Entry point — asyncio orchestration, one task per camera
config.py      # Loads .env, exposes all settings
monitor.py     # Stats singleton + rich live terminal dashboard + rotating file logger
cameras/       # CameraStream: threaded cv2.VideoCapture, exposes get_frame()
detectors/     # MotionDetector: MOG2 background subtraction, returns (score, mask)
analyzers/     # LLMAnalyzer (Claude) or OllamaAnalyzer (local) — returns {suspicious, changed, reason}
alerters/      # DiscordAlerter + HomeAssistantAlerter — dispatched via MultiAlerter in main.py
storage/       # save_frame(): timestamped JPEGs under storage/<camera_id>/
db/            # DBBackend ABC + SQLiteBackend — records every LLM call for history context
web/           # Flask MJPEG server + /api/{logs,alerts,status} — tabbed dashboard at http://localhost:5000
```

## Pipeline

1. **Capture** — `CameraStream` reads frames in a background thread via `cv2.VideoCapture` (RTSP/HTTP)
2. **Detect** — `MotionDetector` runs MOG2 on each frame; returns pixel-change count
3. **Pre-filter (optional)** — If `YOLO_ENABLED=true`, YOLOv8 runs on the frame to check for target object classes (person, car, etc.). Frames with only irrelevant motion (wind, shadows) are dropped before reaching the LLM. Disable with `YOLO_ENABLED=false`
4. **Analyze** — If score > `MOTION_THRESHOLD` (and YOLO passes, if enabled), the active analyzer sends the frame to the LLM with a cooldown per camera. Backend selected by `LLM_BACKEND` env var: `claude` → `LLMAnalyzer` (claude-haiku-4-5), `ollama` → `OllamaAnalyzer` (default: qwen3-vl:8b). Each call includes:
   - The trigger frame (full quality)
   - Snapshots from up to `LLM_CONTEXT_CAMERAS` other cameras (reduced quality)
   - Last `LLM_HISTORY_WINDOW` seconds of LLM call history from the DB as a text log
5. **Record** — Every LLM result (suspicious or not) is written to the DB with `suspicious`, `changed`, and `reason`
6. **Alert** — Only if `suspicious=true AND changed=true`: frame saved to `storage/`, alerts sent via `MultiAlerter` (Discord + Home Assistant). Repeated detections of the same situation are suppressed (`changed=false`)
7. **Monitor** — `monitor.py` `Stats` singleton collects live data from all components; `rich` live dashboard updates in terminal; log also written to a rolling file

## Tech Stack

- **OpenCV** (`cv2`) — video capture, motion detection, frame processing
- **LLM (switchable)** — `claude-haiku-4-5` via Anthropic API, or local Ollama (`qwen3-vl:8b` default); set `LLM_BACKEND=claude|ollama`
- **Discord Webhooks** — alerting via direct `httpx` POST with image attachment
- **Home Assistant** — optional HA integration: fires `argus_security_alert` events + webhook triggers; `/api/status` endpoint for HA REST sensor
- **SQLite** — rolling LLM call history for context and change detection (swappable via `DB_BACKEND`)
- **Flask** — MJPEG stream server + JSON APIs (`/api/logs`, `/api/alerts`, `/api/status`) + tabbed browser dashboard (Live Feeds / Alert History)
- **rich** — terminal dashboard (`monitor.py`)
- **asyncio** — concurrent per-camera monitoring; OpenCV (sync) bridged via `run_in_executor`
- **Python** — primary language

## Key Conventions

- `monitor.stats` is a module-level singleton; import `monitor` and mutate `monitor.stats.*` from any component
- Camera threads write to `monitor.stats.camera(id)` (FPS, status, motion score, events)
- LLM writes to `monitor.stats.llm` (call count, suspicious hits, last call timestamp, cooldown)
- Alerter calls `monitor.stats.record_alert(camera_id, reason)` — kept as a rolling log of last 10
- `_latest_frames` dict in `main.py` holds the most recent frame per camera for cross-camera context
- DB records are keyed by unix timestamp; `db.get_recent(window)` and `db.format_history()` provide the context text injected into LLM prompts
- Secrets live in `.env` and are never committed — use `.env.example` as template

## Environment Variables

```
LLM_BACKEND=claude        # "claude" or "ollama"

# Claude backend
ANTHROPIC_API_KEY=

# Ollama backend
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen3-vl:8b

# Alerts
DISCORD_WEBHOOK_URL=      # Discord channel webhook URL

# Home Assistant (optional)
HASS_URL=                 # e.g. http://homeassistant.local:8123
HASS_TOKEN=               # Long-lived access token
HASS_WEBHOOK_ID=          # Webhook automation trigger ID (optional)

# Cameras & detection
CAMERA_URLS=              # Comma-separated RTSP/HTTP stream URLs
MOTION_THRESHOLD=5000     # Pixel-change threshold to trigger LLM
YOLO_ENABLED=true         # Enable YOLO pre-filter (set false to skip)
YOLO_MODEL=yolov8n.pt     # YOLOv8 model (n/s/m/l/x); auto-downloaded on first run
YOLO_CONFIDENCE=0.4       # Min confidence to count a detection
YOLO_CLASSES=person,car,truck,bus,motorcycle,bicycle,dog,cat  # Object classes to pass through
LLM_COOLDOWN_SECONDS=30   # Min seconds between LLM calls per camera
LLM_CONTEXT_CAMERAS=3     # Max other-camera snapshots sent per LLM call
LLM_HISTORY_WINDOW=300    # Seconds of past LLM calls sent as context (5 min)
FLASK_PORT=5000

# Database
DB_BACKEND=sqlite         # Registered backend name in db/__init__.py
DB_PATH=logs/security.db

# Logging
LOG_FILE=logs/security.log
LOG_MAX_BYTES=5242880     # Truncate and restart at 5 MB
```

## Development Notes

- Camera threads are daemon threads — they die when main exits
- Flask runs in a daemon thread; dashboard runs in a separate daemon thread
- `MotionDetector` is not thread-safe — one instance per camera task
- MOG2 needs ~30 frames to build a stable background model on startup (initial false positives expected)
- LLM cooldown is per-`LLMAnalyzer` instance (one per camera in current setup)
- Saved frames go to `storage/<camera_id>/YYYYMMDD_HHMMSS_<us>.jpg`
- To add a new DB backend: subclass `db.base.DBBackend`, add it to `db/_BACKENDS`, set `DB_BACKEND=` in `.env`
- The `changed` field suppresses alert spam — the LLM is instructed to return `changed=false` for ongoing situations already present in the history log
- Web dashboard has two tabs: **Live Feeds** (camera streams + system log) and **Alert History** (DB-backed table + status cards)
- `MultiAlerter` in `main.py` fans out alerts to all configured backends (Discord, Home Assistant); adding a new backend just requires another alerter with a `send()` method
- Home Assistant receives alerts two ways: (1) webhook trigger (if `HASS_WEBHOOK_ID` set) and (2) `argus_security_alert` event on the HA event bus. The `/api/status` endpoint can be used as a HA REST sensor for dashboard integration
