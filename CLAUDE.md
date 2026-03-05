# Home Security System

A home security system with an OpenCV frontend for IP cameras that detects motion, analyzes suspicious behavior with an LLM, and sends alerts via Telegram.

## Architecture

```
main.py        # Entry point — asyncio orchestration, one task per camera
config.py      # Loads .env, exposes all settings
monitor.py     # Stats singleton + rich live terminal dashboard
cameras/       # CameraStream: threaded cv2.VideoCapture, exposes get_frame()
detectors/     # MotionDetector: MOG2 background subtraction, returns (score, mask)
analyzers/     # LLMAnalyzer (Claude) or OllamaAnalyzer (local) — returns {suspicious, reason}
alerters/      # TelegramAlerter: async httpx sendPhoto/sendMessage
storage/       # save_frame(): timestamped JPEGs under storage/<camera_id>/
web/           # Flask MJPEG server — browser viewer at http://localhost:5000
```

## Pipeline

1. **Capture** — `CameraStream` reads frames in a background thread via `cv2.VideoCapture` (RTSP/HTTP)
2. **Detect** — `MotionDetector` runs MOG2 on each frame; returns pixel-change count
3. **Analyze** — If score > `MOTION_THRESHOLD`, the active analyzer sends the frame to the LLM with a 30s cooldown per camera. Backend selected by `LLM_BACKEND` env var: `claude` → `LLMAnalyzer` (claude-sonnet-4-6), `ollama` → `OllamaAnalyzer` (default: qwen2.5vl:32b)
4. **Alert** — If the LLM flags suspicious activity: frame saved to `storage/`, Telegram alert sent with snapshot
5. **Monitor** — `monitor.py` `Stats` singleton collects live data from all components; `rich` live dashboard updates in terminal

## Tech Stack

- **OpenCV** (`cv2`) — video capture, motion detection, frame processing
- **LLM (switchable)** — `claude-sonnet-4-6` via Anthropic API, or local Ollama (`qwen2.5vl:32b` default); set `LLM_BACKEND=claude|ollama`
- **Telegram Bot API** — alerting via direct `httpx` HTTP calls
- **Flask** — MJPEG stream server for browser-based live view
- **rich** — terminal dashboard (`monitor.py`)
- **asyncio** — concurrent per-camera monitoring; OpenCV (sync) bridged via `run_in_executor`
- **Python** — primary language

## Key Conventions

- `monitor.stats` is a module-level singleton; import `monitor` and mutate `monitor.stats.*` from any component
- Camera threads write to `monitor.stats.camera(id)` (FPS, status, motion score, events)
- LLM writes to `monitor.stats.llm` (call count, suspicious hits, last call timestamp, cooldown)
- Alerter calls `monitor.stats.record_alert(camera_id, reason)` — kept as a rolling log of last 10
- Secrets live in `.env` and are never committed — use `.env.example` as template

## Environment Variables

```
LLM_BACKEND=claude        # "claude" or "ollama"

# Claude backend
ANTHROPIC_API_KEY=

# Ollama backend
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5vl:32b

# Alerts
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Cameras & detection
CAMERA_URLS=              # Comma-separated RTSP/HTTP stream URLs
MOTION_THRESHOLD=5000     # Pixel-change threshold to trigger LLM
LLM_COOLDOWN_SECONDS=30   # Min seconds between LLM calls per camera
FLASK_PORT=5000
```

## Development Notes

- Camera threads are daemon threads — they die when main exits
- Flask runs in a daemon thread; dashboard runs in a separate daemon thread
- `MotionDetector` is not thread-safe — one instance per camera task
- MOG2 needs ~30 frames to build a stable background model on startup (initial false positives expected)
- LLM cooldown is per-`LLMAnalyzer` instance (one per camera in current setup)
- Saved frames go to `storage/<camera_id>/YYYYMMDD_HHMMSS_<us>.jpg`
