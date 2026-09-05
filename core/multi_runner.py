"""
Multi-Worker Concurrent Video Playback Engine for bb-video-watcher.
Enables parallel execution of multiple video lessons (e.g. M1 and M2)
using isolated browser contexts and thread-safe multi-line status tracking.
"""

import os
import json
import sys
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from core.detector import VideoLesson
from core.engine import play_video_lesson, format_time, PlaybackResult
from core.verifier import verify_lesson_grade

STATE_FILE = Path(__file__).resolve().parent.parent / ".session" / "watcher_state.json"


@dataclass
class WorkerProgress:
    lesson: VideoLesson
    percentage: float = 0.0
    current_time: float = 0.0
    duration: float = 0.0
    speed: float = 2.0
    eta_seconds: float = 0.0
    elapsed_wall: float = 0.0
    status: str = "INITIALIZING"
    quizzes: int = 0
    message: str = ""


class MultiProgressRenderer:
    """Thread-safe terminal renderer for concurrent video watching tasks."""

    def __init__(self, lessons: List[VideoLesson]):
        self.lock = threading.Lock()
        self.workers: Dict[str, WorkerProgress] = {
            l.content_id: WorkerProgress(lesson=l) for l in lessons
        }
        self.lesson_order = [l.content_id for l in lessons]
        self._stop_event = threading.Event()
        self._render_thread: Optional[threading.Thread] = None

    def update(self, content_id: str, **kwargs):
        with self.lock:
            if content_id in self.workers:
                wp = self.workers[content_id]
                for k, v in kwargs.items():
                    if hasattr(wp, k):
                        setattr(wp, k, v)

    def start(self):
        self._render_thread = threading.Thread(target=self._render_loop, daemon=True)
        self._render_thread.start()

    def stop(self):
        self._stop_event.set()
        if self._render_thread:
            self._render_thread.join(timeout=2.0)
        self._render_final()

    def _render_loop(self):
        # Print initial blank lines so cursor moves don't overwrite terminal history
        print("\n" * (len(self.lesson_order) + 2))
        while not self._stop_event.is_set():
            self._render_tick()
            time.sleep(1.0)

    def _save_state(self):
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            active_count = sum(1 for wp in self.workers.values() if wp.status in ("INITIALIZING", "WATCHING"))
            data = {
                "pid": os.getpid(),
                "updated_at": time.time(),
                "active_count": active_count,
                "total_count": len(self.lesson_order),
                "workers": [
                    {
                        "content_id": cid,
                        "course_code": wp.lesson.course_code,
                        "title": wp.lesson.title,
                        "percentage": round(wp.percentage, 1),
                        "current_time": round(wp.current_time, 1),
                        "duration": round(wp.duration, 1),
                        "speed": round(wp.speed, 1),
                        "eta_seconds": round(wp.eta_seconds, 1),
                        "status": wp.status,
                        "quizzes": wp.quizzes,
                        "message": wp.message,
                    }
                    for cid, wp in self.workers.items()
                ]
            }
            tmp_file = STATE_FILE.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp_file.replace(STATE_FILE)
        except Exception:
            pass

    def _render_tick(self):
        with self.lock:
            self._save_state()
            lines = []
            active_count = sum(1 for wp in self.workers.values() if wp.status in ("INITIALIZING", "WATCHING"))
            lines.append(
                f"🎥 bb-video-watcher: Multi-Worker Concurrent Playback "
                f"({active_count}/{len(self.lesson_order)} active workers) "
                f"[Time: {time.strftime('%H:%M:%S')}]"
            )
            lines.append("─" * 90)

            for idx, cid in enumerate(self.lesson_order, start=1):
                wp = self.workers[cid]
                bar_len = 20
                pct = max(0.0, min(100.0, wp.percentage))
                filled = int(bar_len * (pct / 100.0))
                bar = "█" * filled + "░" * (bar_len - filled)

                eta_str = format_time(wp.eta_seconds) if wp.eta_seconds > 0 else "--:--"
                curr_str = format_time(wp.current_time)
                dur_str = format_time(wp.duration) if wp.duration > 0 else "--:--"

                if wp.status == "COMPLETED":
                    status_badge = "✅ COMPLETED"
                elif wp.status == "ERROR":
                    status_badge = "❌ FAILED"
                elif wp.status == "INITIALIZING":
                    status_badge = "⏳ STARTING"
                else:
                    status_badge = f"▶ {wp.speed:.1f}x (ETA {eta_str})"

                title_trunc = (wp.lesson.title[:26] + "..") if len(wp.lesson.title) > 28 else wp.lesson.title
                lines.append(
                    f"[{idx}/{len(self.lesson_order)}] [{wp.lesson.course_code}] {title_trunc:<28} "
                    f"{pct:5.1f}% [{bar}] {curr_str}/{dur_str} | {status_badge}"
                )

            if sys.stdout.isatty():
                total_lines = len(lines)
                up_code = f"\033[{total_lines}A\r"
                output = up_code + "\n".join(lines) + "\n"
                sys.stdout.write(output)
                sys.stdout.flush()
            else:
                now = time.time()
                if not hasattr(self, "_last_log_time"):
                    self._last_log_time = 0.0
                    self._last_logged_p = {}
                should_log = (now - self._last_log_time >= 30.0)
                for cid in self.lesson_order:
                    curr_p = int(self.workers[cid].percentage)
                    last_p = self._last_logged_p.get(cid, -1)
                    if curr_p >= last_p + 5 or self.workers[cid].status in ("COMPLETED", "ERROR"):
                        should_log = True
                        self._last_logged_p[cid] = curr_p
                if should_log:
                    sys.stdout.write("\n".join(lines) + "\n")
                    sys.stdout.flush()
                    self._last_log_time = now

    def _render_final(self):
        with self.lock:
            self._save_state()
            print("\n" + "=" * 90)
            print("📋 MULTI-WORKER PLAYBACK COMPLETED")
            print("=" * 90)
            for idx, cid in enumerate(self.lesson_order, start=1):
                wp = self.workers[cid]
                icon = "✅" if wp.status == "COMPLETED" else "❌"
                score_str = f"Score: {wp.lesson.current_score}/{wp.lesson.points_possible} pts" if wp.lesson.current_score is not None else ""
                print(f"{icon} [{idx}/{len(self.lesson_order)}] {wp.lesson.course_code} - {wp.lesson.title}: {wp.status} ({wp.message}) {score_str}")
            print("=" * 90 + "\n")


def parse_time_str(ts: str) -> float:
    try:
        parts = [int(p) for p in ts.split(":")]
        if len(parts) == 2:
            return float(parts[0] * 60 + parts[1])
        elif len(parts) == 3:
            return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    except Exception:
        pass
    return 0.0


def load_current_state() -> Optional[Dict[str, Any]]:
    """Loads state from STATE_FILE, or synthesizes from active background task log if needed."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            updated_at = state.get("updated_at", 0)
            if (time.time() - updated_at < 30.0) or not state.get("workers"):
                return state
        except Exception:
            pass

    # Fallback: scan for active task log
    import glob, re
    pattern = re.compile(r'\[(\d+)/\d+\]\s+\[(.*?)\]\s+(.*?)\s+(\d+\.\d+)%\s+\[.*?\]\s+(\d+:\d+)/(\d+:\d+)\s+\|\s+(.*)')
    log_pattern = os.path.expanduser("~/.gemini/antigravity/brain/*/.system_generated/tasks/task-*.log")
    logs = glob.glob(log_pattern)
    if not logs:
        return None

    logs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    latest_log = logs[0]
    mtime = os.path.getmtime(latest_log)
    if time.time() - mtime > 180.0:
        return None

    try:
        with open(latest_log, "r", errors="ignore") as f:
            lines = f.readlines()[-30:]

        matches = {}
        for line in lines:
            m = pattern.search(line)
            if m:
                idx, course, title, pct, curr, dur, badge = m.groups()
                eta_val = 0.0
                if "ETA" in badge:
                    eta_part = badge.split("ETA")[-1].strip().rstrip(")")
                    eta_val = parse_time_str(eta_part)
                matches[idx] = {
                    "content_id": f"worker_{idx}",
                    "course_code": course.strip(),
                    "title": title.strip(),
                    "percentage": float(pct),
                    "current_time": parse_time_str(curr),
                    "duration": parse_time_str(dur),
                    "speed": 2.1,
                    "eta_seconds": eta_val,
                    "status": "COMPLETED" if "COMPLETED" in badge else "WATCHING",
                    "quizzes": 0,
                    "message": badge.strip()
                }

        if matches:
            workers = [matches[k] for k in sorted(matches.keys())]
            state = {
                "updated_at": mtime,
                "pid": "active",
                "active_count": sum(1 for w in workers if w["status"] == "WATCHING"),
                "total_count": len(workers),
                "workers": workers
            }
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            return state
    except Exception:
        pass

    return None


def render_external_progress(watch: bool = False, json_output: bool = False) -> int:
    """
    Read watcher state from another terminal and display progress cleanly.
    If watch is True, refresh in-place every second without scrolling or spitting lines.
    """
    try:
        while True:
            state = load_current_state()
            if not state:
                print("ℹ️  No active video watcher session found.")
                print("   Start a session with: bb-video-watcher watch M1 M2 -p")
                return 1

            if json_output:
                print(json.dumps(state, indent=2))
                return 0

            updated_at = state.get("updated_at", 0)
            age = time.time() - updated_at
            is_stale = age > 30.0

            workers = state.get("workers", [])
            active = state.get("active_count", 0)
            total = state.get("total_count", len(workers))
            pid = state.get("pid", "?")

            status_str = "🟢 ACTIVE (Running)" if not is_stale and active > 0 else ("⏳ FINISHED / IDLE" if not is_stale else "⚠️ STALE")

            lines = []
            lines.append("╔═══════════════════════════════════════════════════════════════════════════════╗")
            lines.append(f"║ 🎥 Video Watcher Live Monitor  | PID: {str(pid):<6} | Status: {status_str:<18} ║")
            lines.append("╚═══════════════════════════════════════════════════════════════════════════════╝")
            lines.append(f"  Workers Active: {active}/{total} | Last heartbeat: {int(age)}s ago\n")

            for idx, w in enumerate(workers, 1):
                pct = w.get("percentage", 0.0)
                bar_len = 24
                filled = int(bar_len * (pct / 100.0))
                bar = "█" * filled + "░" * (bar_len - filled)
                curr = format_time(w.get("current_time", 0))
                dur = format_time(w.get("duration", 0))
                spd = w.get("speed", 2.0)
                eta = format_time(w.get("eta_seconds", 0))
                status = w.get("status", "WATCHING")

                if status == "COMPLETED":
                    badge = "✅ COMPLETED"
                elif status == "ERROR":
                    badge = "❌ ERROR"
                else:
                    badge = f"▶ {spd:.1f}x (ETA {eta})"

                title = w.get("title", "Lesson")
                if len(title) > 24:
                    title = title[:22] + ".."

                lines.append(f"  [{idx}] {w.get('course_code', '')} {title:<24} {pct:5.1f}% [{bar}] {curr}/{dur} | {badge}")

            lines.append("\n  (Press Ctrl+C to exit monitor)")

            out_text = "\n".join(lines)

            if watch:
                sys.stdout.write("\033[H\033[J" + out_text + "\n")
                sys.stdout.flush()
                time.sleep(1.0)
            else:
                print(out_text)
                return 0

    except KeyboardInterrupt:
        print("\n👋 Monitor closed.")
        return 0


def play_lessons_concurrently(
    lessons: List[VideoLesson],
    speed: float = 2.0,
    max_workers: int = 2,
    headless: bool = True,
    stealth: bool = True,
    auto_quiz: str = "auto",
    verify: bool = True,
) -> List[PlaybackResult]:
    """
    Executes multiple video lessons concurrently using a ThreadPoolExecutor.
    Each worker runs inside its own isolated Playwright browser context.
    """
    if not lessons:
        return []

    print(f"\n🚀 Launching {len(lessons)} video lessons concurrently with {min(len(lessons), max_workers)} workers...")
    for idx, l in enumerate(lessons, 1):
        print(f"   [{idx}] {l.course_code}: {l.title} ({l.content_id}) -> {l.points_possible} pts")
    print(f"   Settings: Speed={speed:.1f}x | Stealth={stealth} | Headless={headless} | Auto-Quiz={auto_quiz}\n")

    renderer = MultiProgressRenderer(lessons)
    renderer.start()

    results: List[PlaybackResult] = []

    def _worker_task(lesson: VideoLesson) -> PlaybackResult:
        cid = lesson.content_id
        renderer.update(cid, status="INITIALIZING")

        def _progress_cb(data: Dict[str, Any]):
            renderer.update(
                cid,
                status="WATCHING",
                percentage=data.get("percentage", 0.0),
                current_time=data.get("current_time", 0.0),
                duration=data.get("duration", 0.0),
                speed=data.get("speed", speed),
                elapsed_wall=data.get("elapsed_wall", 0.0),
                eta_seconds=data.get("eta_seconds", 0.0)
            )

        try:
            res = play_video_lesson(
                lesson=lesson,
                speed=speed,
                headless=headless,
                stealth=stealth,
                auto_quiz=auto_quiz,
                progress_callback=_progress_cb,
                silent_display=True
            )

            # Verification step if requested
            if res.status == "COMPLETED" and verify:
                renderer.update(cid, message="Verifying Gradebook...")
                ver_res = verify_lesson_grade(lesson)
                if ver_res.get("verified"):
                    lesson.current_score = ver_res.get("score")
                    lesson.status = "COMPLETED"
                    res.message += f" [Grade verified: {lesson.current_score}/{lesson.points_possible} pts]"
                else:
                    res.message += f" [{ver_res.get('message', 'Grade pending')}]"

            renderer.update(
                cid,
                status=res.status,
                percentage=100.0 if res.status == "COMPLETED" else res.percentage,
                message=res.message
            )
            return res

        except Exception as e:
            renderer.update(cid, status="ERROR", message=str(e))
            return PlaybackResult(
                status="ERROR",
                lesson=lesson,
                duration_seconds=0.0,
                watched_seconds=0.0,
                percentage=0.0,
                effective_speed=speed,
                quizzes_encountered=0,
                elapsed_wall_time=0.0,
                message=str(e)
            )

    worker_pool_size = min(len(lessons), max(1, max_workers))
    with ThreadPoolExecutor(max_workers=worker_pool_size) as executor:
        future_map = {executor.submit(_worker_task, l): l for l in lessons}
        for future in as_completed(future_map):
            try:
                res = future.result()
                results.append(res)
            except Exception as e:
                l = future_map[future]
                results.append(PlaybackResult(
                    status="ERROR",
                    lesson=l,
                    duration_seconds=0.0,
                    watched_seconds=0.0,
                    percentage=0.0,
                    effective_speed=speed,
                    quizzes_encountered=0,
                    elapsed_wall_time=0.0,
                    message=str(e)
                ))

    renderer.stop()
    return results
