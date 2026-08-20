from datetime import datetime
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone


class HomeViewTests(TestCase):
    def test_home_page_is_available(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SHUNKAN")

    def test_home_path_shows_remaining_time_below_tagline(self):
        frozen = timezone.make_aware(datetime(2026, 8, 20, 12, 0, 0))

        with patch("core.views.timezone.localtime", return_value=frozen):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "旬間")
        self.assertContains(response, "夏の瞬間を残すアプリ")
        self.assertNotContains(response, "現在時刻")
        self.assertContains(response, "夏の終わりまで: 11日 11時間 59分 59秒")
        content = response.content.decode()
        tagline_pos = content.index("夏の瞬間を残すアプリ")
        countdown_pos = content.index("夏の終わりまで")
        self.assertLess(tagline_pos, countdown_pos)
