from datetime import timedelta
from html.parser import HTMLParser
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.test import TestCase
from django.urls import resolve, reverse
from django.utils import timezone

from .models import Room


class CaptureFormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.form_stack = []
        self.has_nested_capture_form = False

    def handle_starttag(self, tag, attrs):
        if tag != "form":
            return

        attributes = dict(attrs)
        if any(self.form_stack):
            self.has_nested_capture_form = True
        self.form_stack.append("data-capture-form" in attributes)

    def handle_endtag(self, tag):
        if tag == "form" and self.form_stack:
            self.form_stack.pop()


class PasswordPolicyTests(TestCase):
    def test_only_the_five_character_minimum_validator_is_enabled(self):
        self.assertEqual(
            settings.AUTH_PASSWORD_VALIDATORS,
            [
                {
                    "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
                    "OPTIONS": {"min_length": 5},
                }
            ],
        )

    def test_passwords_shorter_than_five_characters_are_rejected(self):
        user = get_user_model()(username="policy-user")

        with self.assertRaises(ValidationError):
            validate_password("1234", user=user)

    def test_any_five_character_password_is_accepted(self):
        user = get_user_model()(username="policy-user")

        validate_password("12345", user=user)
        validate_password("aaaaa", user=user)
        validate_password("policy-user", user=user)

    def test_signup_displays_the_five_character_minimum(self):
        response = self.client.get(reverse("signup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "5")
        self.assertNotContains(response, "よく使われるパスワード")


class HealthCheckTests(TestCase):
    def test_anonymous_get_checks_database_and_returns_only_ok_status(self):
        response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response.content, b'{"status": "ok"}')

    def test_non_get_method_is_not_allowed(self):
        with patch("core.views.connection.cursor") as cursor:
            response = self.client.post(reverse("healthz"))

        self.assertEqual(response.status_code, 405)
        cursor.assert_not_called()

    def test_database_failure_returns_service_unavailable_without_body(self):
        with patch(
            "core.views.connection.cursor",
            side_effect=DatabaseError("database unavailable"),
        ):
            response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.content, b"")


class CaptureFormRenderingTests(TestCase):
    def test_quick_create_forms_are_standalone_and_controls_are_associated(self):
        user = get_user_model().objects.create_user(
            username="capture-owner",
            password="CapturePass123!",
        )
        now = timezone.now()
        room = Room.objects.create(
            owner=user,
            name="夏のRoom",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=1),
        )
        self.client.force_login(user)

        response = self.client.get(reverse("room_moments_new", args=[room.pk]))
        content = response.content.decode()
        parser = CaptureFormParser()
        parser.feed(content)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(parser.has_nested_capture_form)
        self.assertContains(
            response,
            f'id="quick-task-form" data-quick-create-form action="{reverse("task_quick_create", args=[room.pk])}"',
        )
        self.assertContains(
            response,
            f'id="quick-category-form" data-quick-create-form action="{reverse("category_quick_create", args=[room.pk])}"',
        )
        self.assertContains(
            response,
            'data-quick-create="task" data-quick-create-form="quick-task-form"',
        )
        self.assertContains(
            response,
            'data-quick-create="category" data-quick-create-form="quick-category-form"',
        )
        self.assertContains(response, 'name="title" maxlength="100" placeholder="例：花火を見る" form="quick-task-form"')
        self.assertContains(response, 'name="due_date" type="date" form="quick-task-form"')
        self.assertContains(response, 'name="name" maxlength="30" placeholder="例：花火" form="quick-category-form"')
        self.assertContains(response, 'type="submit" form="quick-task-form"')
        self.assertContains(response, 'type="submit" form="quick-category-form"')


class RouteCleanupTests(TestCase):
    def test_task_list_name_is_compatible_with_canonical_room_tasks_route(self):
        task_list_url = reverse("task_list", args=[1])
        room_tasks_url = reverse("room_tasks", args=[1])

        self.assertEqual(task_list_url, room_tasks_url)
        self.assertEqual(room_tasks_url, "/rooms/1/tasks/")

        task_list_match = resolve(task_list_url)
        room_tasks_match = resolve(room_tasks_url)
        self.assertEqual(task_list_match.func, room_tasks_match.func)
        self.assertEqual(task_list_match.kwargs, room_tasks_match.kwargs)
        self.assertEqual(task_list_match.url_name, "room_tasks")
        self.assertEqual(room_tasks_match.url_name, "room_tasks")
