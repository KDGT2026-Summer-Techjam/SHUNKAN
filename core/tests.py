from datetime import datetime
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone


class HomeViewTests(TestCase):
    def test_home_page_is_available(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SHUNKAN")

    def test_home_path_shows_remaining_time_in_countdown_card(self):
        frozen = timezone.make_aware(datetime(2026, 8, 20, 12, 0, 0))

        with patch("core.views.timezone.localtime", return_value=frozen):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "旬間")
        self.assertContains(response, "この夏を、")
        self.assertContains(response, "夏の終わりまで")
        self.assertContains(response, "11日 11時間 59分 59秒")
        content = response.content.decode()
        tagline_pos = content.index("この夏を、")
        countdown_pos = content.index("夏の終わりまで")
        self.assertLess(tagline_pos, countdown_pos)


class UiShellRouteTests(TestCase):
    def test_v8_ui_pages_are_available(self):
        for path in ("/moments/new/", "/tasks/", "/album/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_moments_page_uses_the_imported_visual_assets(self):
        response = self.client.get("/moments/new/")
        self.assertContains(response, "今を残す")
        self.assertContains(response, "fireworks.jpg")

    def test_home_shows_zero_countdown_after_summer_ends(self):
        frozen = timezone.make_aware(datetime(2026, 9, 1, 0, 0, 0))

        with patch("core.views.timezone.localtime", return_value=frozen):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "00日 00:00:00")
        self.assertContains(response, "夏は終了しました")
