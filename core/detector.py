"""
Video Requirement and Weekly Lesson Detector.
Inspects Blackboard Ultra course outlines, LTI content handlers, and Gradebook columns
to discover mandatory weekly video lessons and their current viewing/grade status.
"""

import json
import re
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from core.session import get_cookie_header, BLACKBOARD_HOST

# Known courses with weekly online lesson video requirements
KNOWN_COURSES = {
    "ECON122": {
        "id": "_107884_1",
        "name": "ECON 122 Principles of Accounting II FA2026",
        "points_per_lesson": 10.0,
        "total_lessons": 11,
    },
    "AGNG100": {
        "id": "_112155_1",
        "name": "AGNG 100 Longevity Economy FA2026",
        "points_per_lesson": 0.0,
        "total_lessons": 0,
    }
}


@dataclass
class VideoLesson:
    course_code: str
    course_id: str
    course_name: str
    content_id: str
    title: str
    module_id: Optional[str]
    module_name: Optional[str]
    provider: str  # "yuja", "lti", "embedded"
    launch_url: str
    direct_video_url: Optional[str]
    points_possible: float
    current_score: Optional[float]
    status: str  # "PENDING" (needs watching), "COMPLETED" (full score), "UNGRADED"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _api_get(path: str, cookie_header: str) -> Optional[Dict[str, Any]]:
    """Execute authenticated GET against Blackboard REST API."""
    url = f"https://{BLACKBOARD_HOST}{path}"
    req = urllib.request.Request(url)
    req.add_header("Cookie", cookie_header)
    req.add_header("User-Agent", "Mozilla/5.0 (bb-video-watcher autonomous agent)")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return None


def detect_course_video_lessons(course_code: str = "ECON122", cookie_header: Optional[str] = None) -> List[VideoLesson]:
    """
    Detect all required video lessons for the specified course.
    Correlates course contents with gradebook column scores.
    """
    if cookie_header is None:
        cookie_header = get_cookie_header()

    info = KNOWN_COURSES.get(course_code.upper(), {
        "id": course_code if course_code.startswith("_") else "_107884_1",
        "name": course_code,
        "points_per_lesson": 10.0
    })
    course_id = info["id"]
    course_name = info.get("name", course_code)

    # 1. Fetch Gradebook columns to correlate lesson scores
    grade_cols = _api_get(f"/learn/api/public/v2/courses/{course_id}/gradebook/columns", cookie_header)
    column_map = {}
    col_scores = {}

    if grade_cols and "results" in grade_cols:
        for col in grade_cols["results"]:
            cid = col.get("id")
            cname = col.get("name", "")
            possible = col.get("score", {}).get("possible", 0.0)
            content_ref = col.get("contentId")
            column_map[cname.lower().strip()] = {
                "column_id": cid,
                "name": cname,
                "possible": possible,
                "content_id": content_ref
            }

            # Fetch student score for this column
            user_grades = _api_get(f"/learn/api/public/v2/courses/{course_id}/gradebook/columns/{cid}/users", cookie_header)
            if user_grades and "results" in user_grades and len(user_grades["results"]) > 0:
                ug = user_grades["results"][0]
                display_grade = ug.get("displayGrade", {})
                score = display_grade.get("score")
                col_scores[cid] = score

    # 2. Fetch top-level course outline items
    contents_data = _api_get(f"/learn/api/public/v1/courses/{course_id}/contents", cookie_header)
    items = contents_data.get("results", []) if contents_data else []

    detected_lessons: List[VideoLesson] = []

    for item in items:
        item_id = item.get("id")
        title = item.get("title", "")
        handler = item.get("contentHandler", {})
        handler_id = handler.get("id", "")

        # Check if this item is a container (folder, lesson module, learning module)
        if item.get("hasChildren") or "folder" in handler_id or "module" in handler_id or "lesson" in handler_id:
            sub_data = _api_get(f"/learn/api/public/v1/courses/{course_id}/contents/{item_id}/children", cookie_header)
            sub_items = sub_data.get("results", []) if sub_data else []
            for sub in sub_items:
                sub_title = sub.get("title", "")
                sub_handler = sub.get("contentHandler", {})
                sub_hid = sub_handler.get("id", "")

                # Check for Online Lesson or LTI video (exclude static office documents/files)
                is_file = "file" in sub_hid or sub_title.lower().endswith(('.docx', '.pptx', '.pdf', '.xlsx'))
                is_ignored = any(k in sub_title.lower() for k in ("textbook", "library reserve", "research guide", "syllabus", "support"))
                is_video_handler = ("blti" in sub_hid or "yuja" in sub_hid or "video" in sub_hid) and not is_ignored
                is_video_title = any(k in sub_title.lower() for k in ("online lesson", "lesson", "video lecture")) and not is_ignored

                if not is_file and (is_video_handler or is_video_title):
                    lesson = _build_lesson_record(
                        course_code=course_code,
                        course_id=course_id,
                        course_name=course_name,
                        item_data=sub,
                        module_id=item_id,
                        module_name=title,
                        column_map=column_map,
                        col_scores=col_scores
                    )
                    detected_lessons.append(lesson)
        else:
            # Top-level lesson item
            is_file = "file" in handler_id or title.lower().endswith(('.docx', '.pptx', '.pdf', '.xlsx'))
            is_video_handler = "blti" in handler_id or "yuja" in handler_id or "video" in handler_id
            is_video_title = any(k in title.lower() for k in ("online lesson", "lesson", "video lecture"))

            if not is_file and (is_video_handler or is_video_title):
                # Also ignore general university library/textbook LTI links
                if not any(ignore in title.lower() for ignore in ("textbooks", "library reserves", "research guide")):
                    lesson = _build_lesson_record(
                        course_code=course_code,
                        course_id=course_id,
                        course_name=course_name,
                        item_data=item,
                        module_id=None,
                        module_name=None,
                        column_map=column_map,
                        col_scores=col_scores
                    )
                    detected_lessons.append(lesson)

    # Sort lessons naturally by title (M1, M2, ... M11)
    def natural_sort_key(l: VideoLesson):
        m = re.search(r'M(\d+)', l.title)
        return int(m.group(1)) if m else 999

    detected_lessons.sort(key=natural_sort_key)
    return detected_lessons


def _build_lesson_record(
    course_code: str,
    course_id: str,
    course_name: str,
    item_data: Dict[str, Any],
    module_id: Optional[str],
    module_name: Optional[str],
    column_map: Dict[str, Dict[str, Any]],
    col_scores: Dict[str, Optional[float]]
) -> VideoLesson:
    """Build a normalized VideoLesson dataclass from Blackboard API item metadata."""
    item_id = item_data.get("id")
    title = item_data.get("title", "")
    handler = item_data.get("contentHandler", {})
    custom = handler.get("customParameters", {})
    direct_url = custom.get("redirectURL")

    provider = "yuja" if (direct_url and "yuja.com" in direct_url) else "lti"
    launch_url = f"https://{BLACKBOARD_HOST}/webapps/blackboard/execute/blti/launchLink?course_id={course_id}&content_id={item_id}&from_ultra=true"

    # Match Gradebook column by exact title or content ID
    matched_col = None
    title_key = title.lower().strip()
    if title_key in column_map:
        matched_col = column_map[title_key]
    else:
        for cname, cinfo in column_map.items():
            if cinfo.get("content_id") == item_id or title_key in cname or cname in title_key:
                matched_col = cinfo
                break

    possible = matched_col.get("possible", 10.0) if matched_col else 10.0
    col_id = matched_col.get("column_id") if matched_col else None
    current_score = col_scores.get(col_id) if col_id else None

    # Determine status
    if current_score is not None:
        if current_score >= possible and possible > 0:
            status = "COMPLETED"
        else:
            status = "PENDING"
    else:
        status = "PENDING"

    return VideoLesson(
        course_code=course_code,
        course_id=course_id,
        course_name=course_name,
        content_id=item_id,
        title=title,
        module_id=module_id,
        module_name=module_name,
        provider=provider,
        launch_url=launch_url,
        direct_video_url=direct_url,
        points_possible=possible,
        current_score=current_score,
        status=status
    )
