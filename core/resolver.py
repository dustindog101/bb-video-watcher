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
      - Direct launch URL: e.g. 'https://blackboard.umbc.edu/webapps/blackboard/execute/blti/launchLink?...'
    """
    q = query.strip()
    if not q:
        return None

    # Handle direct launch URL
    if q.startswith("http://") or q.startswith("https://"):
        cid_match = re.search(r'content_id=(_\d+_\d+)', q)
        content_id = cid_match.group(1) if cid_match else f"custom_{abs(hash(q)) % 100000}"
        return VideoLesson(
            content_id=content_id,
            title=f"Direct URL Video ({content_id})",
            course_code=course_code,
            launch_url=q,
            status="PENDING",
            points_possible=10.0,
            provider="LTI / YuJa"
        )

    lessons = detect_course_video_lessons(course_code=course_code, cookie_header=cookie_header)
    if not lessons:
        return None

    q_lower = q.lower()

    # 1. 'next' or 'pending'
    if q_lower in ("next", "pending", "auto", "first"):
        for l in lessons:
            if l.status == "PENDING":
                return l
        return lessons[0] if lessons else None

    # 2. Exact content ID match
    for l in lessons:
        if l.content_id == q:
            return l

    # 3. Module tag match (e.g. 'm1', 'm2')
    m_match = re.match(r'^[Mm](\d+)$', q_lower)
    if m_match:
        mod_num = m_match.group(1)
        for l in lessons:
            target_pattern = rf'\b[Mm]{mod_num}\b'
            if re.search(target_pattern, l.title):
                return l

    # 4. Title contains query
    for l in lessons:
        if q_lower in l.title.lower():
            return l

    return None


def resolve_targets(queries: List[str], course_code: str = "ECON122", cookie_header: Optional[str] = None) -> List[VideoLesson]:
    """
    Resolves a list of queries into deduplicated VideoLesson targets.
    Supports queries like ['M1', 'M2'], ['all'], or comma-separated strings.
    """
    flat_queries: List[str] = []
    for q in queries:
        for part in q.replace(",", " ").split():
            clean = part.strip()
            if clean:
                flat_queries.append(clean)

    if not flat_queries:
        return []

    lessons = detect_course_video_lessons(course_code=course_code, cookie_header=cookie_header)
    if not lessons:
        return []

    # If any query is 'all', return all lessons
    if any(q.lower() in ("all", "--all") for q in flat_queries):
        return lessons

    # If query is 'pending', return all pending lessons
    if any(q.lower() in ("pending", "unwatched") for q in flat_queries):
        pending = [l for l in lessons if l.status == "PENDING"]
        return pending if pending else lessons

    resolved: List[VideoLesson] = []
    seen_ids = set()

    for q in flat_queries:
        target = resolve_target(q, course_code=course_code, cookie_header=cookie_header)
        if target and target.content_id not in seen_ids:
            seen_ids.add(target.content_id)
            resolved.append(target)

    return resolved
