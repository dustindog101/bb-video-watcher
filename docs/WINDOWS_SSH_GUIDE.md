# Windows & SSH Remote Deployment Guide

This guide walks through deploying and running **bb-video-watcher** remotely on a Windows machine over SSH (e.g., Windows OpenSSH Server, Git Bash, PowerShell, or WSL).

---

## 1. Prerequisites on Windows

1. **Python 3.10+**:
   - Ensure Python is installed and added to your system `PATH`.
   - Verify in terminal:
     ```powershell
     python --version
     ```
2. **Git for Windows**:
   - Ensure `git` is available.
3. **Browser Engine**:
   - **Microsoft Edge** or **Google Chrome** is already pre-installed on Windows. Playwright can use system Edge or Chrome directly (`channel="msedge"` or `channel="chrome"`).
   - Alternatively, install Playwright's bundled Chromium:
     ```powershell
     playwright install chromium
     ```

---

## 2. Clone & Setup Repository

Connect to your Windows machine via SSH:

```bash
ssh username@windows-ip
```

Clone the repository and set up a virtual environment:

### In PowerShell:
```powershell
git clone https://github.com/dustindog101/bb-video-watcher.git
cd bb-video-watcher

# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### In Git Bash / Bash over SSH:
```bash
git clone https://github.com/dustindog101/bb-video-watcher.git
cd bb-video-watcher

# Create virtual environment
python -m venv venv
source venv/Scripts/activate

# Install dependencies
pip install -r requirements.txt
```

---

## 3. Authentication Over SSH

Blackboard requires UMBC SSO + Duo 2FA. On a remote Windows SSH session, you have two quick options:

### Option A: Direct Interactive CLI Login (Recommended)
Run the login command directly in your SSH terminal:
```bash
python cli.py login
```
1. It will prompt for your UMBC username and password (or read them from `.session/config.json`).
2. It launches headless Chrome/Edge in the background and submits the SSO form.
3. Duo triggers an SMS passcode to your mobile phone.
4. The CLI prompts in the SSH terminal:
   ```text
   ↳ Enter 6-digit Duo Passcode from your phone: 
   ```
5. Enter your 6-digit code. The session is saved to `.session/cookies.json` with 30-day device trust enabled!

### Option B: Transfer Session Cookies from Mac
If you already logged in on your Mac, you can simply transfer the active `.session/cookies.json` file over SSH:
```bash
# Run this from your local Mac terminal:
scp "tools/bb-video-watcher/.session/cookies.json" username@windows-ip:"C:/path/to/bb-video-watcher/.session/cookies.json"
```
Once transferred, the Windows machine is immediately authenticated without needing 2FA again.

Verify session health anytime:
```bash
python cli.py status
```

---

## 4. Running Video Watcher Headlessly

Playback runs **100% headlessly** and **hardware-muted** by default. No display, monitor, or X11/GUI forwarding is required over SSH.

### Watch Specific Modules Concurrently:
```bash
python cli.py watch M1 M2 -p -w 2
```

### Watch the Next Required Module:
```bash
python cli.py watch next
```

### Auto-Watch All Pending Lessons:
```bash
python cli.py auto --all -p -w 2
```

---

## 5. Running as a Persistent Background Process on Windows

To disconnect your SSH session and let the watcher run in the background on Windows:

### In PowerShell:
```powershell
Start-Process python -ArgumentList "cli.py watch M1 M2 -p -w 2" -NoNewWindow -RedirectStandardOutput watcher.log -RedirectStandardError watcher.err
```

### In Git Bash:
```bash
nohup python cli.py watch M1 M2 -p -w 2 > watcher.log 2>&1 &
```

Once launched, you can safely log out of your SSH session (`exit`). The background process will continue watching the videos, answering quizzes, flushing beacons, and verifying grades.

---

## 6. Live Progress Monitoring from Another SSH Terminal

Open another SSH connection to your Windows machine at any time to monitor progress cleanly:

### Live In-Place Dashboard:
```bash
python cli.py progress
```
This updates stationary on your screen every second without flooding your terminal:
```text
╔═══════════════════════════════════════════════════════════════════════════════╗
║ 🎥 Video Watcher Live Monitor  | PID: 14820  | Status: 🟢 ACTIVE (Running) ║
╚═══════════════════════════════════════════════════════════════════════════════╝
  Workers Active: 2/2 | Last heartbeat: 0s ago

  [1] ECON122 M1 Online Lesson          48.5% [████████████░░░░░░░░░░░░] 27:42/57:03 | ▶ 2.1x (ETA 13:58)
  [2] ECON122 M2 Online Lesson          49.2% [████████████░░░░░░░░░░░░] 27:26/55:41 | ▶ 2.1x (ETA 13:28)

  (Press Ctrl+C to exit monitor)
```

### Instant Single Snapshot:
```bash
python cli.py progress --once
```

---

## 7. Configuration (`.session/config.json`)

To avoid typing credentials, you can create `.session/config.json`:
```bash
mkdir -p .session
cp config.example.json .session/config.json
```
Edit `.session/config.json`:
```json
{
  "auto_login": {
    "username": "a484",
    "password": "YOUR_PASSWORD"
  },
  "default_course": "ECON122",
  "default_speed": 2.0,
  "max_workers": 2,
  "stealth": true
}
```

---

## 8. Windows Troubleshooting

| Issue | Resolution |
| :--- | :--- |
| **`playwright._impl._errors.Error: Executable doesn't exist`** | Run `playwright install chromium` or ensure Google Chrome / Microsoft Edge is installed in default `Program Files`. The CLI automatically discovers system Edge and Chrome. |
| **Execution Policy Error in PowerShell (`Activate.ps1 cannot be loaded`)** | Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in your PowerShell window before activating venv. |
| **Session shows INACTIVE** | Run `python cli.py login` or copy a fresh `.session/cookies.json` from your Mac. |
| **Terminal cursor / ANSI codes garbled** | Modern Windows Terminal and OpenSSH support ANSI VT100 escapes natively. If using legacy `cmd.exe`, run `python cli.py progress --once` for single-line snapshots. |
