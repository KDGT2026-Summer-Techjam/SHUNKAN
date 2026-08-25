from datetime import datetime, timedelta


from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from django.core.files.uploadedfile import SimpleUploadedFile

from .models import Room, Category, Task, MomentLog, Photo


class AuthenticationViewTests(TestCase):
    def setUp(self):
        self.password = "test-password-123"
        self.user = get_user_model().objects.create_user(
            username="demo-user",
            password=self.password,
        )

    def test_home_redirects_to_login(self):
        response = self.client.get("/")

        self.assertRedirects(response, reverse("login"))

    def test_login_page_is_available(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ログイン")
        self.assertContains(response, 'href="/accounts/signup/"')
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_signup_creates_a_user_and_logs_in(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "new-user",
                "password1": "safe-test-password-123",
                "password2": "safe-test-password-123",
            },
        )

        self.assertRedirects(response, reverse("rooms"))
        user = get_user_model().objects.get(username="new-user")
        self.assertTrue(user.check_password("safe-test-password-123"))
        self.assertEqual(self.client.session.get("_auth_user_id"), str(user.pk))

    def test_signup_shows_errors_without_creating_a_user(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": self.user.username,
                "password1": "safe-test-password-123",
                "password2": "safe-test-password-123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["username"])
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_authenticated_user_is_redirected_from_signup_to_rooms(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("signup"))

        self.assertRedirects(response, reverse("rooms"))

    def test_authenticated_user_is_redirected_from_login_to_rooms(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("login"))

        self.assertRedirects(response, reverse("rooms"))

    def test_login_redirects_to_rooms(self):
        response = self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": self.password},
            follow=True,
        )

        self.assertRedirects(response, reverse("rooms"))
        self.assertContains(response, "ルーム一覧")

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("rooms"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('rooms')}")

    def test_logout_prevents_reopening_protected_pages(self):
        room = Room.objects.create(
            owner=self.user,
            name="ログアウト確認用Room",
            starts_at=timezone.make_aware(datetime(2026, 8, 20, 12, 0, 0)),
            ends_at=timezone.make_aware(datetime(2026, 8, 30, 12, 0, 0)),
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse("logout"), follow=True)

        self.assertRedirects(response, reverse("login"))
        for url in (reverse("rooms"), reverse("room_detail", args=[room.pk])):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(response, f"{reverse('login')}?next={url}")


class RoomViewTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="room-owner",
            password="test-password-123",
        )
        self.other_user = get_user_model().objects.create_user(
            username="other-user",
            password="test-password-123",
        )
        self.owner_room = Room.objects.create(
            owner=self.owner,
            name="自分のRoom",
            starts_at=timezone.make_aware(datetime(2026, 8, 20, 12, 0, 0)),
            ends_at=timezone.make_aware(datetime(2026, 8, 30, 12, 0, 0)),
        )
        self.other_room = Room.objects.create(
            owner=self.other_user,
            name="他人のRoom",
            starts_at=timezone.make_aware(datetime(2026, 8, 20, 12, 0, 0)),
            ends_at=timezone.make_aware(datetime(2026, 8, 30, 12, 0, 0)),
        )
        self.client.force_login(self.owner)

    def test_room_list_shows_only_rooms_owned_by_the_current_user(self):
        response = self.client.get(reverse("rooms"))

        self.assertContains(response, "自分のRoom")
        self.assertNotContains(response, "他人のRoom")

    def test_room_creation_assigns_the_current_user_as_owner(self):
        response = self.client.post(
            reverse("rooms"),
            {
                "name": "新しいRoom",
                "starts_at": "2026-08-20T12:00",
                "ends_at": "2026-08-30T12:00",
            },
        )

        self.assertRedirects(response, reverse("rooms"))
        room = Room.objects.get(name="新しいRoom")
        self.assertEqual(room.owner, self.owner)

    def test_room_detail_rejects_another_users_room(self):
        response = self.client.get(reverse("room_detail", args=[self.other_room.pk]))

        self.assertEqual(response.status_code, 404)


class SeedDemoCommandTests(TestCase):
    @override_settings(DEBUG=True)
    def test_seed_demo_uses_public_credentials_when_debug_is_enabled(self):
        call_command("seed_demo")

        user = get_user_model().objects.get(username="demo")
        self.assertTrue(user.check_password("demo"))


class UiShellRouteTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="ui-user",
            password="test-password-123",
        )
        self.client.force_login(self.user)

    def test_template_preview_pages_are_available(self):
        for path in (
            "/rooms/",
            "/rooms/active/",
            "/rooms/ended/",
            "/moments/new/",
            "/tasks/",
            "/album/",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "ログアウト")

    def test_album_page_uses_django_static_assets(self):
        response = self.client.get("/album/")

        self.assertContains(response, "/static/core/images/fireworks.jpg")
        self.assertContains(response, "/static/core/css/v8-ui.css")

    def test_post_forms_include_csrf_tokens(self):
        for path in ("/rooms/", "/tasks/", "/moments/new/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertContains(response, "csrfmiddlewaretoken")

class RoomModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="testuser",
            password="testpass123",
        )

        self.starts_at = timezone.make_aware(
            datetime(2026, 8, 20, 12, 0, 0)
        )
        self.ends_at = self.starts_at + timedelta(days=10)

    def test_room_can_be_created(self):
        room = Room(
            owner=self.user,
            name="2026 夏",
            starts_at=self.starts_at,
            ends_at=self.ends_at,
        )

        room.full_clean()
        room.save()

        self.assertEqual(Room.objects.count(), 1)
        self.assertEqual(room.owner, self.user)
        self.assertEqual(room.name, "2026 夏")
        self.assertFalse(room.is_archived)

    def test_ends_at_must_be_after_starts_at(self):
        room = Room(
            owner=self.user,
            name="不正なルーム",
            starts_at=self.starts_at,
            ends_at=self.starts_at,
        )

        with self.assertRaises(ValidationError):
            room.full_clean()

    def test_owner_delete_also_deletes_room(self):
        room = Room.objects.create(
            owner=self.user,
            name="2026 夏",
            starts_at=self.starts_at,
            ends_at=self.ends_at,
        )

        self.user.delete()

        self.assertFalse(Room.objects.filter(pk=room.pk).exists())

    def test_reflection_deadline_is_optional(self):
        room = Room(
            owner=self.user,
            name="2026 夏",
            starts_at=self.starts_at,
            ends_at=self.ends_at,
        )

        room.full_clean()
        room.save()

        self.assertIsNone(room.reflection_deadline_at)

class CategoryModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="category_user",
            password="testpass123",
        )

        self.starts_at = timezone.make_aware(
            datetime(2026, 8, 20, 12, 0, 0)
        )
        self.ends_at = self.starts_at + timedelta(days=10)

        self.room = Room.objects.create(
            owner=self.user,
            name="2026 夏",
            starts_at=self.starts_at,
            ends_at=self.ends_at,
        )

    def test_category_can_be_created(self):
        category = Category.objects.create(
            room=self.room,
            name="花火",
        )

        self.assertEqual(category.room, self.room)
        self.assertEqual(category.name, "花火")
        self.assertEqual(category.sort_order, 0)
        self.assertEqual(category.color, "")

    def test_category_name_must_be_unique_within_same_room(self):
        Category.objects.create(
            room=self.room,
            name="花火",
        )

        with self.assertRaises(Exception):
            Category.objects.create(
                room=self.room,
                name="花火",
            )

    def test_same_category_name_can_exist_in_different_rooms(self):
        another_room = Room.objects.create(
            owner=self.user,
            name="TechJam 2026",
            starts_at=self.starts_at,
            ends_at=self.ends_at,
        )

        Category.objects.create(
            room=self.room,
            name="花火",
        )

        category = Category.objects.create(
            room=another_room,
            name="花火",
        )

        self.assertEqual(category.name, "花火")
        self.assertEqual(category.room, another_room)

class TaskModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="testuser",
            password="password",
        )

        self.room = Room.objects.create(
            owner=self.user,
            name="2026 夏",
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(days=7),
        )

        self.other_room = Room.objects.create(
            owner=self.user,
            name="TechJam 2026",
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(days=7),
        )

        self.category = Category.objects.create(
            room=self.room,
            name="花火",
        )

        self.other_category = Category.objects.create(
            room=self.other_room,
            name="準備",
        )

    def test_task_can_be_created(self):
        task = Task(
            room=self.room,
            category=self.category,
            title="花火を見る",
        )

        task.full_clean()
        task.save()

        self.assertEqual(task.room, self.room)
        self.assertEqual(task.category, self.category)

    def test_category_from_another_room_is_invalid(self):
        task = Task(
            room=self.room,
            category=self.other_category,
            title="不正なタスク",
        )

        with self.assertRaises(ValidationError):
            task.full_clean()

    def test_completed_at_must_match_completion_status(self):
        task = Task(
            room=self.room,
            title="テストタスク",
            is_completed=False,
            completed_at=timezone.now(),
        )

        with self.assertRaises(ValidationError):
            task.full_clean()

class MomentLogModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="moment-user",
            password="password",
        )

        now = timezone.now()

        self.room = Room.objects.create(
            owner=self.user,
            name="2026 夏",
            starts_at=now,
            ends_at=now + timedelta(days=7),
        )

        self.other_room = Room.objects.create(
            owner=self.user,
            name="TechJam 2026",
            starts_at=now,
            ends_at=now + timedelta(days=7),
        )

        self.category = Category.objects.create(
            room=self.room,
            name="花火",
        )

        self.other_category = Category.objects.create(
            room=self.other_room,
            name="準備",
        )

        self.task = Task.objects.create(
            room=self.room,
            title="花火を見る",
        )

        self.other_task = Task.objects.create(
            room=self.other_room,
            title="発表準備",
        )

    def test_moment_log_can_be_created(self):
        occurred_at = self.room.starts_at + timedelta(days=1)

        log = MomentLog(
            room=self.room,
            task=self.task,
            category=self.category,
            body="花火がきれいだった",
            occurred_at=occurred_at,
        )

        log.full_clean()
        log.save()

        self.assertEqual(log.entry_type, MomentLog.EntryType.MOMENT)
        self.assertEqual(log.occurred_at, occurred_at)

    def test_task_from_another_room_is_invalid(self):
        log = MomentLog(
            room=self.room,
            task=self.other_task,
            body="別RoomのTask",
            occurred_at=self.room.starts_at,
        )

        with self.assertRaises(ValidationError):
            log.full_clean()

    def test_category_from_another_room_is_invalid(self):
        log = MomentLog(
            room=self.room,
            category=self.other_category,
            body="別RoomのCategory",
            occurred_at=self.room.starts_at,
        )

        with self.assertRaises(ValidationError):
            log.full_clean()

    def test_occurred_at_can_be_edited(self):
        original = self.room.starts_at + timedelta(days=1)

        log = MomentLog.objects.create(
            room=self.room,
            body="最初の記録",
            occurred_at=original,
        )

        edited = self.room.starts_at + timedelta(days=2)
        log.occurred_at = edited
        log.full_clean()
        log.save()

        log.refresh_from_db()
        self.assertEqual(log.occurred_at, edited)

class PhotoModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="photo-user",
            password="password",
        )

        now = timezone.now()

        self.room = Room.objects.create(
            owner=self.user,
            name="2026 夏",
            starts_at=now,
            ends_at=now + timedelta(days=7),
        )

        self.moment_log = MomentLog.objects.create(
            room=self.room,
            body="花火がきれいだった",
            occurred_at=now,
        )

    def test_photo_can_be_created(self):
        image = SimpleUploadedFile(
            "fireworks.jpg",
            b"fake-image-data",
            content_type="image/jpeg",
        )

        photo = Photo.objects.create(
            moment_log=self.moment_log,
            image=image,
            caption="夏の花火",
            sort_order=0,
        )

        self.assertEqual(photo.moment_log, self.moment_log)
        self.assertEqual(photo.caption, "夏の花火")
        self.assertEqual(photo.sort_order, 0)

    def test_photo_belongs_to_room_through_moment_log(self):
        image = SimpleUploadedFile(
            "summer.jpg",
            b"fake-image-data",
            content_type="image/jpeg",
        )

        photo = Photo.objects.create(
            moment_log=self.moment_log,
            image=image,
        )

        self.assertEqual(photo.moment_log.room, self.room)
