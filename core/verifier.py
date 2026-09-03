"""
Blackboard Gradebook REST Fast-Path Verifier.
Polls Blackboard Gradebook API to confirm that the YuJa LTI 1.3 Advantage AGS
telemetry passback successfully credited the student's score.
"""

import json
import time
import urllib.request
from typing import Dict, Any, Optional
from core.session import get_cookie_header, BLACKBOARD_HOST
from core.detector import VideoLesson, _api_get


def verify_lesson_grade(
    lesson: VideoLesson,
    cookie_header: Optional[str] = None,
    max_retries: int = 4,
    retry_delay_seconds: int = 5
) -> Dict[str, Any]:
    """
    Poll Blackboard Gradebook for the lesson's updated score.
    Returns status dictionary with verification results.
    """
    if cookie_header is None:
        cookie_header = get_cookie_header()

    course_id = lesson.course_id
    lesson_title = lesson.title.lower().strip()

    for attempt in range(1, max_retries + 1):
        # 1. Fetch Gradebook columns
        grade_cols = _api_get(f"/learn/api/public/v2/courses/{course_id}/gradebook/columns", cookie_header)
        if not grade_cols or "results" not in grade_cols:
            time.sleep(retry_delay_seconds)
            continue

        target_col_id = None
        target_possible = lesson.points_possible

        for col in grade_cols["results"]:
            cid = col.get("id")
            cname = col.get("name", "").lower().strip()
            content_ref = col.get("contentId")

            if cname == lesson_title or content_ref == lesson.content_id or lesson_title in cname:
                target_col_id = cid
                target_possible = col.get("score", {}).get("possible", lesson.points_possible)
                break

        if not target_col_id:
            # Retry after delay
            time.sleep(retry_delay_seconds)
            continue

        # 2. Fetch user's score for this column
        user_grades = _api_get(f"/learn/api/public/v2/courses/{course_id}/gradebook/columns/{target_col_id}/users", cookie_header)
        if user_grades and "results" in user_grades and len(user_grades["results"]) > 0:
            ug = user_grades["results"][0]
            display_grade = ug.get("displayGrade", {})
            score = display_grade.get("score")
            status = ug.get("status", "")

            if score is not None and score >= target_possible:
                return {
                    "verified": True,
                    "attempt": attempt,
                    "score": score,
                    "possible": target_possible,
                    "status": status,
                    "column_id": target_col_id,
                    "message": f"Successfully verified grade {score}/{target_possible} ({status})"
                }
            elif score is not None:
                # Recorded score exists (partial or pending sync)
                if attempt == max_retries:
                    return {
                        "verified": False,
                        "attempt": attempt,
                        "score": score,
                        "possible": target_possible,
                        "status": status,
                        "column_id": target_col_id,
                        "message": f"Current score is {score}/{target_possible} (may update asynchronously)"
                    }

        time.sleep(retry_delay_seconds)

    return {
        "verified": False,
        "attempt": max_retries,
        "score": lesson.current_score,
        "possible": lesson.points_possible,
        "status": "PENDING_SYNC",
        "column_id": None,
        "message": "Grade passback submitted; YuJa backend cron syncs to Blackboard in 15-30 minutes."
    }
