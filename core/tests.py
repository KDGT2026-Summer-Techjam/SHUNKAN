from datetime import datetime
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from core.models import Task


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
        self.assertContains(response, "夏の終わりまで: 11日 11:59:59")
        content = response.content.decode()
        tagline_pos = content.index("夏の瞬間を残すアプリ")
        countdown_pos = content.index("夏の終わりまで")
        self.assertLess(tagline_pos, countdown_pos)

    def test_home_shows_zero_countdown_after_summer_ends(self):
        frozen = timezone.make_aware(datetime(2026, 9, 1, 0, 0, 0))

        with patch("core.views.timezone.localtime", return_value=frozen):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "夏の終わりまで: 00日 00:00:00")
        self.assertContains(response, "夏は終了しました")


class TaskViewTests(TestCase):
    def test_task_page_is_available(self):
        response = self.client.get("/task/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "タスク")
        self.assertContains(response, "まだタスクがありません")

    def test_create_task_and_see_it_in_list(self):
        response = self.client.post(
            "/task/",
            {
                "title": "花火を見る",
                "category": "イベント",
                "due_date": "2026-08-20",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "花火を見る")
        self.assertContains(response, "イベント")
        self.assertContains(response, "2026年8月20日")
        self.assertEqual(Task.objects.count(), 1)

    def test_invalid_due_date_shows_error(self):
        response = self.client.post(
            "/task/",
            {
                "title": "花火を見る",
                "category": "イベント",
                "due_date": "2026-09-01",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "実行したい日は2026年8月31日以前にしてください。")
        self.assertEqual(Task.objects.count(), 0)

    def test_empty_title_shows_error(self):
        response = self.client.post(
            "/task/",
            {
                "title": "",
                "category": "イベント",
                "due_date": "2026-08-20",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "タイトルを入力してください。")
        self.assertEqual(Task.objects.count(), 0)
