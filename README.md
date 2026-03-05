# Argus

AI-powered home security system. Watches IP cameras, detects motion with OpenCV, and sends suspicious frames to an LLM (Claude or local Ollama) for analysis. Fires a Discord alert with a snapshot if something looks wrong — and suppresses repeat alerts for the same ongoing situation.

```
camera stream → motion detection → LLM analysis → Discord alert
                                        ↑
                          Claude (cloud) or Ollama (local)
                                        ↑
                      rolling history DB (change detection)
```

---

## Features

- Multi-camera support via RTSP/HTTP streams
- OpenCV MOG2 background subtraction for fast motion gating
- Pluggable LLM backend: Claude (Anthropic) or any Ollama vision model
- **Multi-camera LLM context** — each analysis includes snapshots from all other cameras
- **Rolling history context** — last 5 min of LLM calls injected into every prompt so the model knows what's already been seen
- **Change detection** — LLM returns a `changed` field; alerts only fire on new events, suppressing spam for the same ongoing situation
- Discord alerts with attached snapshot
- Browser-based live viewer (MJPEG stream) at `http://localhost:5000`
- Live system log panel in the web UI (auto-refreshing)
- Full-screen terminal dashboard with live stats and scrollable log
- Rolling file log with auto-truncation at configurable max size
- Pluggable database backend (SQLite by default; swap via `DB_BACKEND=`)
- Everything configurable via `.env` — no code changes needed

---

## Requirements

- Python 3.11+
- An IP camera with an RTSP or HTTP stream
- A Discord webhook URL
- Either an Anthropic API key (Claude) or a local [Ollama](https://ollama.com) install

---

## Setup

```bash
git clone <repo>
cd argus

pip install -r requirements.txt

cp .env.example .env
# edit .env with your keys and camera URLs
```

### Get a Discord webhook

1. Open your Discord server → channel settings → **Integrations** → **Webhooks**
2. Click **New Webhook**, give it a name, copy the URL
3. Paste into `DISCORD_WEBHOOK_URL` in `.env`

---

## Running

```bash
python main.py
```

The terminal dashboard launches automatically. Open `http://localhost:5000` in a browser to watch live feeds and the system log.

### Run persistently over SSH (recommended)

```bash
# On the server
tmux new -s argus
python main.py

# Detach — process keeps running
Ctrl+B, then D

# Re-attach from any SSH session
tmux attach -t argus
```

---

## Configuration

Copy `.env.example` to `.env` and fill in values. Every setting has a sensible default.

### LLM backend

```env
LLM_BACKEND=claude        # "claude" or "ollama"
```

**Claude** (cloud, best reasoning):
```env
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-6
CLAUDE_MAX_TOKENS=256
```

**Ollama** (local, private, no API cost):
```env
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5vl:32b   # needs a vision-capable model
OLLAMA_TIMEOUT=60
```

Pull the model first:
```bash
ollama pull qwen2.5vl:32b
```

### Cameras

```env
CAMERA_URLS=rtsp://user:pass@192.168.1.100/stream1,rtsp://192.168.1.101/stream2
```

Comma-separated. Each camera gets its own motion detector and asyncio task.

### Motion detection tuning

| Variable | Default | Effect |
|---|---|---|
| `MOTION_THRESHOLD` | `5000` | Changed pixels needed to trigger LLM |
| `MOG2_HISTORY` | `500` | Frames used to build background model |
| `MOG2_VAR_THRESHOLD` | `50` | Sensitivity — lower catches more, but noisier |
| `LLM_COOLDOWN_SECONDS` | `30` | Min gap between LLM calls per camera |

### Multi-camera & history context

| Variable | Default | Effect |
|---|---|---|
| `LLM_CONTEXT_CAMERAS` | `3` | Max snapshots from other cameras included per LLM call |
| `LLM_HISTORY_WINDOW` | `300` | Seconds of past LLM results sent as context (5 min) |

### Image quality

| Variable | Default | Used for |
|---|---|---|
| `JPEG_QUALITY_ANALYSIS` | `80` | Trigger frame sent to LLM |
| `JPEG_QUALITY_CONTEXT` | `55` | Other-camera context frames |
| `JPEG_QUALITY_ALERT` | `85` | Discord snapshot |
| `JPEG_QUALITY_STREAM` | `70` | Web MJPEG stream |
| `JPEG_QUALITY_STORAGE` | `90` | Frames saved to disk |

### Database

| Variable | Default | Effect |
|---|---|---|
| `DB_BACKEND` | `sqlite` | Backend name (registered in `db/__init__.py`) |
| `DB_PATH` | `logs/security.db` | Path passed to the backend |

### File logging

| Variable | Default | Effect |
|---|---|---|
| `LOG_FILE` | `logs/security.log` | Path to rolling log file (empty to disable) |
| `LOG_MAX_BYTES` | `5242880` | Truncate and restart at 5 MB |

---

## Terminal dashboard

```
┌─ Home Security Monitor │ uptime 00:12:34 │ http://localhost:5000 ─┐
│ Cameras                    │ LLM Analyzer                          │
│ cam0  ● connected  24fps   │ Model   claude-sonnet-4-6             │
│ cam1  ● connected  30fps   │ Calls   5   Suspicious  2             │
│                            │ Last call   28s ago                   │
├────────────────────────────┴───────────────────────────────────────┤
│ Alerts — 2 sent                                                    │
│ 14:23:01  cam0  Person lurking near front door                     │
├────────────────────────────────────────────────────────────────────┤
│ Logs                                          (live)               │
│ 14:23:05 [ALERT]  cam0: alert sent — person lurking               │
│ 14:23:04 [LLM]    LLM call #5 — cam0 + 1 context cam(s), 3 history│
│ 14:23:03 [MOTION] cam0: motion 8,432 px — sending to LLM          │
└── ↑↓ scroll logs  •  Ctrl+C quit ─────────────────────────────────┘
```

Arrow keys `↑↓` scroll the log panel.

---

## Project structure

```
main.py                  Entry point — asyncio orchestration
config.py                Loads .env, exposes all settings
monitor.py               Stats singleton + rich live dashboard + file logger
cameras/stream.py        Threaded OpenCV capture per camera
detectors/motion.py      MOG2 motion detection
analyzers/
  llm.py                 Claude vision analyzer (multi-image + history)
  ollama_local.py        Ollama vision analyzer (multi-image + history)
alerters/discord.py      Discord webhook alerter
db/
  __init__.py            Public API + backend registry
  base.py                DBBackend abstract base class
  sqlite.py              SQLite implementation
storage/                 Timestamped JPEG archive of flagged frames
web/
  server.py              Flask MJPEG stream server + /api/logs endpoint
  templates/index.html   Web UI with live feeds and log panel
```

---

## Tips

- **Too many false alerts?** Raise `MOTION_THRESHOLD` or `MOG2_VAR_THRESHOLD`. MOG2 needs ~30 frames at startup to build its background model, so expect a few false positives on first launch. The `changed` field also naturally suppresses repeat alerts.
- **Alerts too slow?** Lower `LLM_COOLDOWN_SECONDS`. With Claude you pay per call; with Ollama it's free but limited by local hardware.
- **Low bandwidth?** Lower `JPEG_QUALITY_STREAM` (web viewer), `JPEG_QUALITY_ANALYSIS` (LLM trigger frame), and `JPEG_QUALITY_CONTEXT` (other-camera snapshots).
- **Running headless?** Set `DASHBOARD_REFRESH_RATE=0.5` to reduce CPU from the terminal renderer.
- **Adding a new DB backend?** Subclass `db.base.DBBackend`, implement `init`, `record`, `get_recent`, register it in `db/_BACKENDS`, and set `DB_BACKEND=<name>` in `.env`.
