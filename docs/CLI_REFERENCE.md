# CLI Reference: bb-video-watcher

## Command Syntax Overview

```bash
bb-video-watcher <command> [options]
```

### Commands

| Command | Description |
| :--- | :--- |
| `detect` | Scan Blackboard Ultra course outline & gradebook to find required weekly video lessons. |
| `watch <target>` | Watch a specific lesson by content ID (e.g. `_8915975_1`), module name (`M1`), or `next`. |
| `auto` | Find the next pending unwatched video lesson and watch it automatically. |
| `status` | Print Blackboard session status and course overview. |

---

## Command Options & Examples

### 1. `detect`
```bash
# Scan ECON 122 video requirements
bb-video-watcher detect

# Scan AGNG 100 or another course
bb-video-watcher detect -c AGNG100

# Output structured JSON
bb-video-watcher detect --json
```

### 2. `watch`
```bash
# Watch the earliest pending weekly lesson at 2.0x speed
bb-video-watcher watch next

# Watch Module 1 video lesson
bb-video-watcher watch M1

# Watch by exact Blackboard content ID at 3.0x speed with stealth micro-jitter
bb-video-watcher watch _8915975_1 --speed 3.0 --stealth

# Watch with a visible browser window (headed mode)
bb-video-watcher watch M2 --headful
```

### 3. `auto`
```bash
# Automatically watch the next pending video lesson for ECON 122
bb-video-watcher auto

# Watch ALL pending video lessons sequentially
bb-video-watcher auto --all --speed 2.5
```

### 4. `status`
```bash
# View session health, student info, and points breakdown
bb-video-watcher status
```
