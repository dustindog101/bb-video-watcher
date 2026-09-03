#!/usr/bin/env python3
"""
bb-video-watcher: Autonomous Video Lesson Detection & Playback CLI for Blackboard Ultra & YuJa.
"""

import argparse
import json
import sys
from typing import Optional

from core.session import verify_session, find_cookie_file
from core.detector import detect_course_video_lessons, KNOWN_COURSES
from core.resolver import resolve_target
from core.engine import play_video_lesson, format_time
from core.verifier import verify_lesson_grade


def print_banner():
    banner = """
╔═══════════════════════════════════════════════════════════════════════╗
║   bb-video-watcher: Autonomous YuJa & Blackboard Video Engine         ║
╚═══════════════════════════════════════════════════════════════════════╝
"""
    print(banner.strip())


def cmd_detect(args):
    """Detect required weekly video lessons and their current grade status."""
    course = args.course.upper()
    print(f"\n🔍 Scanning Blackboard Ultra outline & Gradebook for '{course}'...")

    lessons = detect_course_video_lessons(course_code=course)
    if not lessons:
        print(f"❌ No video lessons detected for course '{course}'.")
        return 1

    if args.json:
        print(json.dumps([l.to_dict() for l in lessons], indent=2))
        return 0

    pending_count = sum(1 for l in lessons if l.status == "PENDING")
    completed_count = sum(1 for l in lessons if l.status == "COMPLETED")
    total_points = sum(l.points_possible for l in lessons)
    earned_points = sum(l.current_score or 0.0 for l in lessons)

    print(f"\n📚 Detected {len(lessons)} Weekly Video Lessons for {course}:")
    print(f"   Status: {completed_count}/{len(lessons)} Completed | {earned_points:.1f}/{total_points:.1f} Points Earned\n")

    print(f"{'#':<3} {'Title':<28} {'Content ID':<13} {'Score':<11} {'Status':<10} {'Provider'}")
    print("─" * 78)

    for i, l in enumerate(lessons, start=1):
        score_str = f"{l.current_score:.1f}/{l.points_possible:.1f}" if l.current_score is not None else f"--/{l.points_possible:.1f}"
        status_icon = "✅ COMPLETED" if l.status == "COMPLETED" else "⏳ PENDING"
        print(f"{i:<3} {l.title:<28} {l.content_id:<13} {score_str:<11} {status_icon:<10} {l.provider}")

    print("\n💡 Tip: Run 'bb-video-watcher watch next' or 'bb-video-watcher watch M1' to play.")
    return 0


def cmd_watch(args):
    """Watch a specific video lesson by ID, name, or 'next'."""
    course = args.course.upper()
    target_query = args.target

    print(f"\n🎯 Resolving video target '{target_query}' for course '{course}'...")
    lesson = resolve_target(query=target_query, course_code=course)

    if not lesson:
        print(f"❌ Target '{target_query}' not found in course '{course}'.")
        return 1

    print(f"✅ Resolved: {lesson.title} [{lesson.content_id}]")
    print(f"   Module: {lesson.module_name or 'N/A'}")
    print(f"   Current Score: {lesson.current_score}/{lesson.points_possible} ({lesson.status})")
    print(f"   Playback Speed: {args.speed:.1f}x | Stealth: {args.stealth} | Headless: {not args.headful}\n")

    if lesson.status == "COMPLETED" and not args.force:
        print("ℹ️ Lesson is already marked as COMPLETED with full credit. Use --force to re-watch.")
        return 0

    result = play_video_lesson(
        lesson=lesson,
        speed=args.speed,
        headless=not args.headful,
        stealth=args.stealth,
        auto_quiz="auto"
    )

    if result.status == "COMPLETED":
        print(f"\n🎉 Finished watching {lesson.title} in {format_time(result.elapsed_wall_time)} wall time!")

        if args.verify:
            print("\n🔍 Verifying grade in Blackboard Gradebook REST Fast-Path...")
            ver_res = verify_lesson_grade(lesson)
            print(f"   {ver_res.get('message')}")

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))

    return 0 if result.status == "COMPLETED" else 1


def cmd_auto(args):
    """Automatically find and watch unwatched lessons."""
    course = args.course.upper()
    print(f"\n🤖 Auto-mode: Finding pending video lessons for '{course}'...")

    lessons = detect_course_video_lessons(course_code=course)
    pending = [l for l in lessons if l.status == "PENDING"]

    if not pending:
        print(f"✅ All {len(lessons)} video lessons for '{course}' are already completed!")
        return 0

    print(f"📋 Found {len(pending)} pending video lessons.")
    to_watch = pending if args.all else [pending[0]]

    for idx, lesson in enumerate(to_watch, start=1):
        print(f"\n[{idx}/{len(to_watch)}] Starting: {lesson.title} ({lesson.content_id})")
        res = play_video_lesson(
            lesson=lesson,
            speed=args.speed,
            headless=not args.headful,
            stealth=args.stealth
        )

        if res.status != "COMPLETED":
            print(f"❌ Playback stopped for {lesson.title}: {res.message}")
            if not args.continue_on_error:
                return 1

        if args.verify:
            print("🔍 Verifying gradebook sync...")
            ver_res = verify_lesson_grade(lesson)
            print(f"   {ver_res.get('message')}")

    print("\n🎉 Auto-watch sequence finished!")
    return 0


def cmd_status(args):
    """Check Blackboard session health and general video watching status."""
    print_banner()
    cookie_file = find_cookie_file()
    print(f"📁 Session Cookie File: {cookie_file or 'NOT FOUND'}")

    is_active, user_meta = verify_session()
    if is_active:
        user_name = user_meta.get("userName", "Unknown")
        student_id = user_meta.get("studentId", "Unknown")
        print(f"✅ Blackboard Session: ACTIVE (User: {user_name} / Student ID: {student_id})")
    else:
        print(f"❌ Blackboard Session: INACTIVE ({user_meta.get('error')})")
        print("   Please run 'bb --login' in blackboard-scraper to refresh your session.")
        return 1

    cmd_detect(args)
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="bb-video-watcher",
        description="Autonomous Video Lesson Detection & Playback CLI for Blackboard Ultra & YuJa."
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # detect
    p_detect = subparsers.add_parser("detect", help="Detect required weekly video lessons and grade status")
    p_detect.add_argument("-c", "--course", default="ECON122", help="Course code (default: ECON122)")
    p_detect.add_argument("--json", action="store_true", help="Output standardized JSON")

    # watch
    p_watch = subparsers.add_parser("watch", help="Watch a specific video lesson")
    p_watch.add_argument("target", help="Content ID, module tag (e.g. M1, M2), or 'next'")
    p_watch.add_argument("-c", "--course", default="ECON122", help="Course code (default: ECON122)")
    p_watch.add_argument("--speed", type=float, default=2.0, help="Playback speed (1.0 - 4.0, default: 2.0)")
    p_watch.add_argument("--headful", action="store_true", help="Show visible browser window")
    p_watch.add_argument("--stealth", action="store_true", help="Enable human-mimicking micro-jitter")
    p_watch.add_argument("--force", action="store_true", help="Watch even if already completed")
    p_watch.add_argument("--verify", action="store_true", default=True, help="Verify grade passback after watch")
    p_watch.add_argument("--json", action="store_true", help="Output standardized JSON")

    # auto
    p_auto = subparsers.add_parser("auto", help="Automatically watch pending video lessons")
    p_auto.add_argument("-c", "--course", default="ECON122", help="Course code (default: ECON122)")
    p_auto.add_argument("--all", action="store_true", help="Watch all pending lessons sequentially")
    p_auto.add_argument("--speed", type=float, default=2.0, help="Playback speed (default: 2.0)")
    p_auto.add_argument("--headful", action="store_true", help="Show visible browser window")
    p_auto.add_argument("--stealth", action="store_true", help="Enable micro-jitter and pauses")
    p_auto.add_argument("--continue-on-error", action="store_true", help="Continue if a lesson fails")
    p_auto.add_argument("--verify", action="store_true", default=True, help="Verify grade passback")

    # status
    p_status = subparsers.add_parser("status", help="Check session health and course overview")
    p_status.add_argument("-c", "--course", default="ECON122", help="Course code (default: ECON122)")
    p_status.add_argument("--json", action="store_true", help="Output standardized JSON")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "detect":
        sys.exit(cmd_detect(args))
    elif args.command == "watch":
        sys.exit(cmd_watch(args))
    elif args.command == "auto":
        sys.exit(cmd_auto(args))
    elif args.command == "status":
        sys.exit(cmd_status(args))


if __name__ == "__main__":
    main()
