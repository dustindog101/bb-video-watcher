"""
Autonomous Video Playback and Tracking Engine for YuJa and Blackboard Ultra.
Controls video playback silently, monitors interval progression, handles quizzes,
and flushes heartbeat beacons to ensure full grade credit.
"""

import json
import math
import random
import sys
import time
from dataclasses import dataclass, asdict
from typing import Optional, Callable, Dict, Any

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    sync_playwright = None

from core.session import load_cookies
from core.detector import VideoLesson
from core.quiz_handler import check_and_handle_quiz


@dataclass
class PlaybackResult:
    status: str  # "COMPLETED", "STOPPED", "ERROR", "STALLED"
    lesson: VideoLesson
    duration_seconds: float
    watched_seconds: float
    percentage: float
    effective_speed: float
    quizzes_encountered: int
    elapsed_wall_time: float
    message: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["lesson"] = self.lesson.to_dict()
        return d


def format_time(seconds: float) -> str:
    """Format seconds into MM:SS or HH:MM:SS."""
    s = int(seconds)
    hours = s // 3600
    minutes = (s % 3600) // 60
    secs = s % 60
    if hours > 0:
def find_player_frame(page):
    """
    Find the frame containing the HTML5 video element or YuJa player controls.
    Penetrates cross-origin iframes mounted by Blackboard LTI.
    """
    try:
        if page.evaluate("() => !!document.querySelector('video, #previewPlay, #focusablePlayPauseButton')"):
            return page.main_frame
    except Exception:
        pass

    for frame in page.frames:
        try:
            if frame.evaluate("() => !!document.querySelector('video, #previewPlay, #focusablePlayPauseButton')"):
                return frame
        except Exception:
            continue
    return page.main_frame


def play_video_lesson(
    lesson: VideoLesson,
    speed: float = 2.0,
    headless: bool = True,
    stealth: bool = False,
    auto_quiz: str = "auto",
    max_duration_seconds: Optional[float] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    silent_display: bool = False
) -> PlaybackResult:
    """
    Executes automated, silent background playback of the target video lesson.
    """
    if sync_playwright is None:
        raise RuntimeError("Playwright is not installed! Run 'pip install playwright'.")

    # Safety clamps: cap speed between 1.0x and 4.0x
    safe_speed = max(1.0, min(4.0, speed))

    cookies = load_cookies(for_playwright=True)
    wall_start_time = time.time()
    quizzes_count = 0

    with sync_playwright() as pw:
        # Launch using Google Chrome channel (preferred on macOS) with fallbacks
        browser = None
        for channel in ["chrome", "msedge", "chromium", None]:
            try:
                launch_kwargs = {
                    "headless": headless,
                    "args": [
                        "--mute-audio",
                        "--disable-blink-features=AutomationControlled",
                        "--use-fake-ui-for-media-stream",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ]
                }
                if channel:
                    launch_kwargs["channel"] = channel
                browser = pw.chromium.launch(**launch_kwargs)
                break
            except Exception:
                continue

        if not browser:
            raise RuntimeError("Failed to launch any system Chromium or Chrome browser.")

        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        # Inject anti-bot evasion script
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
            const origQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (p) => (
                p.name === 'notifications' ? Promise.resolve({ state: Notification.permission }) : origQuery(p)
            );
        """)
        context.add_cookies(cookies)

        page = context.new_page()

        try:
            if not silent_display:
                print(f"🔗 Launching LTI entry for '{lesson.title}'...")
            page.goto(lesson.launch_url, timeout=45000, wait_until="load")
            page.wait_for_timeout(4000)

            # Wait for YuJa player DOM elements
            if not silent_display:
                print("⏳ Waiting for YuJa video player to mount...")
            try:
                page.wait_for_selector("video, #previewPlay, #focusablePlayPauseButton, iframe", timeout=25000)
            except PlaywrightTimeout:
                pass

            target_frame = find_player_frame(page)

            # Start playback
            target_frame.evaluate('''() => {
                const playBtn = document.querySelector('#previewPlay') || document.querySelector('#focusablePlayPauseButton');
                if (playBtn) playBtn.click();
                const v = document.querySelector('video');
                if (v) {
                    v.muted = true;
                    v.play().catch(() => {});
                }
            }''')

            target_frame = find_player_frame(page)

            # Set initial playback rate and mute
            target_frame.evaluate('''(s) => {
                const v = document.querySelector('video');
                if (v) {
                    v.muted = true;
                    v.playbackRate = s;
                }
            }''', safe_speed)

            # Polling loop
            last_jitter_time = time.time()
            current_effective_speed = safe_speed

            while True:
                time.sleep(2.0)
                elapsed_wall = time.time() - wall_start_time

                # Check max duration safety
                if max_duration_seconds and elapsed_wall >= max_duration_seconds:
                    print(f"\n⚠️ Max duration reached ({max_duration_seconds}s). Stopping playback.")
                    break

                active_frame = find_player_frame(page)

                # Query video status
                status = active_frame.evaluate('''() => {
                    const v = document.querySelector('video');
                    if (!v) return { found: false };
                    return {
                        found: true,
                        duration: v.duration || 0,
                        currentTime: v.currentTime || 0,
                        paused: v.paused,
                        playbackRate: v.playbackRate || 1.0,
                        ended: v.ended || false,
                        bufferedEnd: v.buffered.length > 0 ? v.buffered.end(v.buffered.length - 1) : 0
                    };
                }''')

                if not status.get("found"):
                    time.sleep(1.0)
                    continue

                duration = status.get("duration", 0)
                current_time = status.get("currentTime", 0)
                paused = status.get("paused", False)
                ended = status.get("ended", False)

                if duration > 0:
                    pct = min(100.0, (current_time / duration) * 100.0)
                else:
                    pct = 0.0

                # Check if paused for quiz
                if paused and not ended:
                    quiz_res = check_and_handle_quiz(active_frame, mode=auto_quiz)
                    if quiz_res:
                        quizzes_count += 1
                        print(f"\n📝 Handled in-video quiz at {format_time(current_time)}: {quiz_res.get('question')[:50]}...")
                        # Resume playback
                        active_frame.evaluate('''() => {
                            const v = document.querySelector('video');
                            if (v) v.play().catch(() => {});
                        }''')
                        time.sleep(1.5)
                    else:
                        # Resume ordinary pause
                        active_frame.evaluate('''() => {
                            const v = document.querySelector('video');
                            if (v) v.play().catch(() => {});
                        }''')

                # Stealth mode micro-jitter
                if stealth and time.time() - last_jitter_time > 35:
                    jitter = random.uniform(-0.15, 0.15)
                    current_effective_speed = max(1.5, min(3.0, safe_speed + jitter))
                    active_frame.evaluate('''(s) => {
                        const v = document.querySelector('video');
                        if (v) v.playbackRate = s;
                    }''', current_effective_speed)
                    last_jitter_time = time.time()

                # Calculate ETA
                if duration > current_time and current_effective_speed > 0:
                    remaining_wall_sec = (duration - current_time) / current_effective_speed
                    eta_str = format_time(remaining_wall_sec)
                else:
                    eta_str = "00:00"

                # Progress display
                if not silent_display:
                    bar_len = 24
                    filled = int(bar_len * (pct / 100.0))
                    bar = "█" * filled + "░" * (bar_len - filled)
                    sys.stdout.write(
                        f"\r[{lesson.course_code}] {lesson.title} | {pct:5.1f}% [{bar}] "
                        f"{format_time(current_time)} / {format_time(duration)} "
                        f"({current_effective_speed:.1f}x) | ETA: {eta_str} "
                    )
                    sys.stdout.flush()

                if progress_callback:
                    progress_callback({
                        "percentage": pct,
                        "current_time": current_time,
                        "duration": duration,
                        "speed": current_effective_speed,
                        "elapsed_wall": elapsed_wall,
                        "eta_seconds": (duration - current_time) / current_effective_speed if duration > current_time else 0
                    })

                # Check completion condition (video ended or within last 2 seconds)
                if ended or (duration > 10 and current_time >= duration - 2.5):
                    print(f"\n✅ Video playback completed 100%! ({format_time(duration)} watched)")
                    # Look for end-card Submit Quiz / Finish button
                    active_frame.evaluate('''() => {
                        const endBtns = Array.from(document.querySelectorAll('button, div[role="button"]'));
                        const submitBtn = endBtns.find(b => {
                            const t = (b.innerText || '').toLowerCase();
                            return t.includes('submit') || t.includes('finish') || t.includes('done');
                        });
                        if (submitBtn) submitBtn.click();
                    }''')

                    print("📡 Flushing final telemetry and heartbeat beacons to YuJa server...")
                    page.wait_for_timeout(6000)
                    break

            elapsed_wall_total = time.time() - wall_start_time
            final_status = active_frame.evaluate('''() => {
                const v = document.querySelector('video');
                return v ? { duration: v.duration, currentTime: v.currentTime } : { duration: 0, currentTime: 0 };
            }''')
            final_dur = final_status.get("duration", 0)
            final_curr = final_status.get("currentTime", 0)
            final_pct = min(100.0, (final_curr / final_dur) * 100.0) if final_dur > 0 else 100.0

            browser.close()

            return PlaybackResult(
                status="COMPLETED" if final_pct >= 95.0 else "STOPPED",
                lesson=lesson,
                duration_seconds=final_dur,
                watched_seconds=final_curr,
                percentage=final_pct,
                effective_speed=safe_speed,
                quizzes_encountered=quizzes_count,
                elapsed_wall_time=elapsed_wall_total,
                message=f"Watched {format_time(final_curr)} of {format_time(final_dur)} ({final_pct:.1f}%)"
            )

        except Exception as e:
            try:
                browser.close()
            except Exception:
                pass
            return PlaybackResult(
                status="ERROR",
                lesson=lesson,
                duration_seconds=0,
                watched_seconds=0,
                percentage=0,
                effective_speed=safe_speed,
                quizzes_encountered=quizzes_count,
                elapsed_wall_time=time.time() - wall_start_time,
                message=f"Playback failed: {str(e)}"
            )
