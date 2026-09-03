# bb-video-watcher 🎥

**Autonomous Video Lesson Detection, Playback, and Gradebook Sync Engine for Blackboard Ultra & YuJa.**

`bb-video-watcher` is a standalone CLI tool that automatically discovers mandatory weekly video lecture requirements, resolves LTI 1.3 Advantage launch handshakes, executes silent background playback at optimized speeds, intercepts in-video check-for-understanding quizzes, and verifies that completion grades are reflected in Blackboard.

---

## Key Features

- **Automated Detection**: Scans course outlines and maps them to Blackboard Gradebook columns to determine which weekly modules are unwatched (`PENDING`) or completed (`COMPLETED`).
- **Silent & Headless Playback**: Hardware-mutes audio via Chromium flags and DOM controls so background watching never interrupts your work or plays sound in public.
- **Velocity Control & Stealth Jitter**: Configurable playback rate (default `2.0x`, safe bounds `1.0x – 4.0x`) with optional `--stealth` micro-jitter ($\pm 0.15\text{x}$) to mimic natural human study habits in Caliper analytics.
- **In-Video Quiz Interceptor**: Automatically detects and answers check-for-understanding pause points and submits final end-cards.
- **Post-Watch Grade Verification**: Directly queries Blackboard's Gradebook REST Fast-Path to verify that full points (e.g. 10.0 / 10.0) were recorded.
- **Zero Configuration**: Leverages existing authenticated UMBC session cookies from `blackboard-scraper` (`.session/cookies.json`).

---

## Installation & Setup

```bash
cd "/Users/king/Desktop/school files/tools/bb-video-watcher"
./install-cli.sh
```

Ensure Playwright is installed:
```bash
pip install playwright
```

---

## Quick Usage

```bash
# 1. Check video requirements and grade status
bb-video-watcher status

# 2. Watch the next pending weekly lesson (e.g. M1)
bb-video-watcher watch next

# 3. Watch specific module at 2.5x speed
bb-video-watcher watch M1 --speed 2.5 --stealth

# 4. Watch all pending lessons sequentially
bb-video-watcher auto --all
```

---

## Project Structure

```
bb-video-watcher/
├── cli.py                  # CLI executable entrypoint
├── core/
│   ├── session.py          # Session cookie loader and validator
│   ├── detector.py         # Blackboard outline & gradebook scanner
│   ├── resolver.py         # Target query resolver (M1, next, content ID)
│   ├── engine.py           # Playwright-driven autonomous playback engine
│   ├── quiz_handler.py     # In-video quiz detector & solver
│   └── verifier.py         # Gradebook REST verification
├── docs/
│   ├── RESEARCH_FINDINGS.md
│   ├── DECISIONS_AND_REASONING.md
│   └── CLI_REFERENCE.md
├── tests/
│   └── test_watcher.py
├── install-cli.sh
└── README.md
```
