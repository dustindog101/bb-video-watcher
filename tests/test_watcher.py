"""
Unit tests for bb-video-watcher core modules.
"""

import unittest
from unittest.mock import patch, MagicMock
from core.session import find_cookie_file, get_cookie_header
from core.detector import VideoLesson, _build_lesson_record
from core.resolver import resolve_target


class TestSession(unittest.TestCase):
    def test_find_cookie_file(self):
        cookie_file = find_cookie_file()
        self.assertIsNotNone(cookie_file)
        self.assertTrue(cookie_file.exists())

    def test_cookie_header_generation(self):
        mock_cookies = [
            {"name": "test_cookie", "value": "12345"},
            {"name": "session_id", "value": "abcde"}
        ]
        hdr = get_cookie_header(mock_cookies)
        self.assertEqual(hdr, "test_cookie=12345; session_id=abcde")


class TestDetector(unittest.TestCase):
    def test_build_lesson_record(self):
        item_data = {
            "id": "_8915975_1",
            "title": "M1 Online Lesson",
            "contentHandler": {
                "id": "resource/x-bb-blti-link",
                "customParameters": {
                    "redirectURL": "https://umbc.video.yuja.com/V/Video?v=14866522&a=115592142"
                }
            }
        }
        col_map = {
            "m1 online lesson": {
                "column_id": "_2073196_1",
                "name": "M1 Online Lesson",
                "possible": 10.0,
                "content_id": "_8915975_1"
            }
        }
        col_scores = {"_2073196_1": 10.0}

        lesson = _build_lesson_record(
            course_code="ECON122",
            course_id="_107884_1",
            course_name="ECON 122 FA2026",
            item_data=item_data,
            module_id="_8915945_1",
            module_name="Chapter 1",
            column_map=col_map,
            col_scores=col_scores
        )

        self.assertEqual(lesson.content_id, "_8915975_1")
        self.assertEqual(lesson.provider, "yuja")
        self.assertEqual(lesson.current_score, 10.0)
        self.assertEqual(lesson.status, "COMPLETED")


class TestResolver(unittest.TestCase):
    @patch("core.resolver.detect_course_video_lessons")
    def test_resolve_m1(self, mock_detect):
        l1 = VideoLesson(
            course_code="ECON122", course_id="_107884_1", course_name="ECON 122",
            content_id="_8915975_1", title="M1 Online Lesson", module_id="_1",
            module_name="Ch1", provider="yuja", launch_url="http://launch",
            direct_video_url="http://yuja", points_possible=10.0, current_score=0.0,
            status="PENDING"
        )
        l2 = VideoLesson(
            course_code="ECON122", course_id="_107884_1", course_name="ECON 122",
            content_id="_8915981_1", title="M2 Online Lesson", module_id="_2",
            module_name="Ch2", provider="yuja", launch_url="http://launch",
            direct_video_url="http://yuja", points_possible=10.0, current_score=None,
            status="PENDING"
        )
        mock_detect.return_value = [l1, l2]

        resolved_m1 = resolve_target("M1", "ECON122")
        self.assertEqual(resolved_m1.content_id, "_8915975_1")

        resolved_next = resolve_target("next", "ECON122")
        self.assertEqual(resolved_next.content_id, "_8915975_1")

        resolved_id = resolve_target("_8915981_1", "ECON122")
        self.assertEqual(resolved_id.content_id, "_8915981_1")


if __name__ == "__main__":
    unittest.main()
