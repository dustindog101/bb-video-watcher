"""
Multi-Worker Concurrent Video Playback Engine for bb-video-watcher.
Enables parallel execution of multiple video lessons (e.g. M1 and M2)
using isolated browser contexts and thread-safe multi-line status tracking.
"""

import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from core.detector import VideoLesson
from core.engine import play_video_lesson, format_time, PlaybackResult
from core.verifier import verify_lesson_grade


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

    def _render_tick(self):
        with self.lock:
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

            # Move cursor up and render
            total_lines = len(lines)
            up_code = f"\033[{total_lines}A\r"
            output = up_code + "\n".join(lines) + "\n"
            sys.stdout.write(output)
            sys.stdout.flush()

    def _render_final(self):
        with self.lock:
            print("\n" + "=" * 90)
            print("📋 MULTI-WORKER PLAYBACK COMPLETED")
            print("=" * 90)
            for idx, cid in enumerate(self.lesson_order, start=1):
                wp = self.workers[cid]
                icon = "✅" if wp.status == "COMPLETED" else "❌"
                score_str = f"Score: {wp.lesson.current_score}/{wp.lesson.points_possible} pts" if wp.lesson.current_score is not None else ""
                print(f"{icon} [{idx}/{len(self.lesson_order)}] {wp.lesson.course_code} - {wp.lesson.title}: {wp.status} ({wp.message}) {score_str}")
            print("=" * 90 + "\n")


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
