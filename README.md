# bb-video-watcher 🎥

**Autonomous Video Lesson Detection, Multi-Threaded Playback, and Gradebook Verification Engine for Blackboard Ultra & YuJa.**

`bb-video-watcher` is a standalone, lightweight CLI engine built for Blackboard Ultra and YuJa Lumina. It automatically scans course outlines, launches LTI 1.3 Advantage video player instances in parallel, executes silent background playback at accelerated velocities, answers in-video check-for-understanding quizzes, clicks end-card completion triggers, and verifies that full credit is awarded in Blackboard Gradebook.

Designed for local macOS execution or remote **Windows / Linux headless execution over SSH**.

---

## 🚀 Key Capabilities

- **Automated Requirement Detection**: Scans Blackboard Ultra outlines, maps video lessons to Gradebook columns, and flags items as `PENDING` or `COMPLETED`.
- **Multi-Worker Concurrent Playback**: Runs multiple video lessons (e.g. `M1` and `M2`) concurrently in isolated browser contexts with configurable worker pools (`-w 2`).
- **Headless & Hardware-Muted**: Runs 100% headlessly with `--mute-audio` and DOM muting. Zero desktop disruption or unexpected audio during background runs.
- **Velocity Control & Stealth Jitter**: Configurable playback speed (`1.0x – 4.0x`, default `2.0x`) with periodic micro-jitter ($\pm 0.15\text{x}$) to mimic natural human learning rhythms.
- **In-Video Quiz Interceptor**: Automatically detects and solves check-for-understanding quiz prompts with human-paced reading and submission delays.
- **Cross-Terminal Live Dashboard**: Run `bb-video-watcher progress` from any separate terminal or SSH session for a stationary, in-place progress monitor with visual progress bars, playback rates, and countdown ETAs without terminal spam.
- **Post-Watch Grade Verification**: Queries Blackboard's Gradebook REST Fast-Path API to verify that the score (e.g. `10.0 / 10.0 pts`) was successfully registered.
- **Standalone Authentication**: Built-in UMBC SSO and Duo 2FA handler with automatic macOS SMS passcode extraction and SSH interactive terminal fallback.

---

## 📦 Quick Installation

### macOS / Linux
```bash
git clone https://github.com/dustindog101/bb-video-watcher.git
cd bb-video-watcher

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Optional: symlink to /usr/local/bin
./install-cli.sh
```

### Windows (Local or Remote SSH)
See the full **[Windows & SSH Deployment Guide](docs/WINDOWS_SSH_GUIDE.md)**.
```powershell
git clone https://github.com/dustindog101/bb-video-watcher.git
cd bb-video-watcher

python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 🔐 Authentication & Session Setup

`bb-video-watcher` manages its own session cookies in `.session/cookies.json`.

### 1. Interactive CLI Login (SSO + Duo 2FA)
```bash
python cli.py login
```
- Prompts for your UMBC credentials (or reads `.session/config.json`).
- Automatically extracts the Duo 2FA SMS code from macOS Messages (on Mac) or prompts in the terminal (on Windows/SSH).
- Enables 30-day trusted device session persistence.

### 2. Check Session Health & Course Lessons
```bash
python cli.py status
```

---

## 🎯 Usage & Commands

### 1. Detect Required Video Lessons
```bash
python cli.py detect -c ECON122
```

### 2. Watch Lessons Concurrently
```bash
# Watch M1 and M2 in parallel (2 workers, 2.0x speed)
python cli.py watch M1 M2 -p -w 2

# Watch at custom speed with stealth jitter
python cli.py watch M1 --speed 2.5 --stealth

# Force re-watch even if already completed
python cli.py watch M1 --force
```

### 3. Auto-Watch All Pending Lessons
```bash
# Automatically finds unwatched lessons and plays them concurrently
python cli.py auto --all -p -w 2
```

### 4. Monitor Live Playback (from Another Terminal or SSH Session)
```bash
# Stationary live monitor (refreshes in-place every second)
python cli.py progress

# Quick one-shot snapshot
python cli.py progress --once
```

---

## 🖥️ Remote Windows / SSH Quick Reference

When running remotely on a Windows host over SSH:

1. **Launch in background:**
   ```powershell
   # PowerShell:
   Start-Process python -ArgumentList "cli.py watch M1 M2 -p -w 2" -NoNewWindow -RedirectStandardOutput watcher.log -RedirectStandardError watcher.err
   ```
   ```bash
   # Git Bash / OpenSSH:
   nohup python cli.py watch M1 M2 -p -w 2 > watcher.log 2>&1 &
   ```
2. **Disconnect SSH session freely:**
   The background process continues running independently.
3. **Reconnect & Monitor:**
   ```bash
   python cli.py progress
   ```

For full details on Windows service setup, cookie transfer, and troubleshooting, read **[docs/WINDOWS_SSH_GUIDE.md](docs/WINDOWS_SSH_GUIDE.md)**.

---

## 📁 Repository Structure

```
bb-video-watcher/
├── cli.py                  # Main CLI executable entrypoint
├── requirements.txt        # Python package dependencies
├── config.example.json     # Configuration template
├── core/
│   ├── login.py            # Standalone UMBC SSO & Duo 2FA authentication
│   ├── session.py          # Session validation & cookie store
│   ├── detector.py         # Blackboard outline & gradebook scanner
│   ├── resolver.py         # Query target resolver (M1, next, URLs)
│   ├── engine.py           # Playwright YuJa playback engine & micro-jitter
│   ├── multi_runner.py     # Multi-worker thread pool & live progress monitor
│   ├── quiz_handler.py     # In-video quiz solver & human decision delays
│   └── verifier.py         # Blackboard Gradebook REST Fast-Path verification
├── docs/
│   ├── WINDOWS_SSH_GUIDE.md # Windows OpenSSH & remote deployment guide
│   ├── CLI_REFERENCE.md    # Full command flag reference
│   ├── DECISIONS_AND_REASONING.md
│   └── RESEARCH_FINDINGS.md
├── tests/
│   └── test_watcher.py     # Test suite
└── install-cli.sh          # Global symlink installer for macOS/Linux
```

---

## 🔒 Security & Privacy

- **No credentials committed:** All passwords, usernames, and session tokens are strictly saved in `.session/` which is ignored by `.gitignore`.
- **Zero modification to school LMS:** The engine interacts with Blackboard and YuJa strictly as a legitimate browser client over HTTPS.
