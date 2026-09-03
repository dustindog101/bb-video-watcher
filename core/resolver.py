"""
Target Resolver for bb-video-watcher.
Translates user queries (content IDs, module names like 'M1', or 'next') into resolved VideoLesson targets.
"""

import re
from typing import Optional, List
from core.detector import VideoLesson, detect_course_video_lessons


def resolve_target(query: str, course_code: str = "ECON122", cookie_header: Optional[str] = None) -> Optional[VideoLesson]:
    """
    Resolves a query to a specific VideoLesson target.
    
    Supported queries:
      - 'next' or 'pending': Resolves the earliest incomplete/pending lesson
      - Content ID: e.g. '_8915975_1'
      - Module tag: e.g. 'M1', 'm2', 'M1 Online Lesson'
      - Fuzzy title substring: e.g. 'Intro to Managerial', 'Job Order'
    """
    lessons = detect_course_video_lessons(course_code=course_code, cookie_header=cookie_header)
    if not lessons:
        return None

    q = query.strip().lower()

    # 1. 'next' or 'pending'
    if q in ("next", "pending", "auto", "first"):
        for l in lessons:
            if l.status == "PENDING":
                return l
        return lessons[0] if lessons else None

    # 2. Exact content ID match
    for l in lessons:
        if l.content_id == query.strip():
            return l

    # 3. Module tag match (e.g. 'm1', 'm2')
    m_match = re.match(r'^[Mm](\d+)$', q)
    if m_match:
        mod_num = m_match.group(1)
        for l in lessons:
            target_pattern = rf'\b[Mm]{mod_num}\b'
            if re.search(target_pattern, l.title):
                return l

    # 4. Title contains query
    for l in lessons:
        if q in l.title.lower():
            return l

    return None
