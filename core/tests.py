from datetime import datetime, timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from django.core.files.uploadedfile import SimpleUploadedFile

from .image_processing import (
    MAX_IMAGE_DIMENSION,
    MAX_SOURCE_PIXELS,
    MAX_UPLOAD_SIZE,
    process_uploaded_image,
)
from .models import Room, Category, Task, MomentLog, Photo


class ImageProcessingTests(TestCase):
    def make_image(self, image_format, size=(2400, 1200)):
        output = BytesIO()
        mode = "RGBA" if image_format == "PNG" else "RGB"
        Image.new(mode, size, "coral").save(output, format=image_format)
        return SimpleUploadedFile(
            f"photo.{image_format.lower()}",
            output.getvalue(),
            content_type=f"image/{image_format.lower()}",
        )

    def test_large_image_is_resized_and_optimized(self):
        processed = process_uploaded_image(self.make_image("JPEG"))

        with Image.open(processed) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertLessEqual(max(image.size), MAX_IMAGE_DIMENSION)

    def test_animated_gif_keeps_its_frames(self):
        output = BytesIO()
        frames = [
            Image.new("RGB", (2400, 1200), "coral"),
            Image.new("RGB", (2400, 1200), "navy"),
        ]
        frames[0].save(
            output,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=[100, 120],
            loop=0,
        )
        upload = SimpleUploadedFile("animated.gif", output.getvalue(), content_type="image/gif")

        processed = process_uploaded_image(upload)

        with Image.open(processed) as image:
            self.assertTrue(getattr(image, "is_animated", False))
            self.assertEqual(getattr(image, "n_frames", 1), 2)
            self.assertLessEqual(max(image.size), MAX_IMAGE_DIMENSION)

    def test_image_larger_than_ten_megabytes_is_rejected(self):
        upload = SimpleUploadedFile(
            "large.jpg",
            b"x" * (MAX_UPLOAD_SIZE + 1),
            content_type="image/jpeg",
        )

        with self.assertRaisesMessage(ValidationError, "写真は1枚10MB以下にしてください。"):
            process_uploaded_image(upload)

    def test_non_image_file_is_rejected(self):
        upload = SimpleUploadedFile("fake.jpg", b"not-an-image", content_type="image/jpeg")

        with self.assertRaisesMessage(ValidationError, "画像ファイルを読み取れませんでした。"):
            process_uploaded_image(upload)

    @patch("core.image_processing.Image.open")
    def test_image_with_too_many_pixels_is_rejected(self, image_open):
        image_open.return_value = Mock(
            format="JPEG",
            width=MAX_SOURCE_PIXELS + 1,
            height=1,
        )
        upload = SimpleUploadedFile("huge.jpg", b"jpeg-header", content_type="image/jpeg")

        with self.assertRaisesMessage(ValidationError, "画像の縦横サイズが大きすぎます。"):
            process_uploaded_image(upload)


class MomentImageUploadTests(TestCase):
    def setUp(self):
        self.media_root = TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media_root.name)
        self.override.enable()
        self.user = get_user_model().objects.create_user(
            username="image-uploader",
            password="test-password-123",
        )
        now = timezone.now()
        self.room = Room.objects.create(
            owner=self.user,
            name="写真テストRoom",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
        )
        self.occurred_at = timezone.localtime(now).strftime("%Y-%m-%dT%H:%M")
        self.client.force_login(self.user)

    def tearDown(self):
        self.override.disable()
        self.media_root.cleanup()

    def make_jpeg(self):
        output = BytesIO()
        Image.new("RGB", (2400, 1200), "coral").save(output, format="JPEG")
        return SimpleUploadedFile("moment.jpg", output.getvalue(), content_type="image/jpeg")

    def test_valid_image_post_creates_resized_photo(self):
        response = self.client.post(
            reverse("room_moments_new", args=[self.room.pk]),
            {
                "body": "写真を残した瞬間",
                "occurred_at": self.occurred_at,
                "images": self.make_jpeg(),
                "captions": "夕暮れ",
            },
        )

        self.assertRedirects(response, reverse("room_album", args=[self.room.pk]))
        moment = MomentLog.objects.get(room=self.room)
        photo = Photo.objects.get(moment_log=moment)
        self.assertEqual(photo.caption, "夕暮れ")
        with Image.open(photo.image) as image:
            self.assertLessEqual(max(image.size), MAX_IMAGE_DIMENSION)

    def test_invalid_image_post_does_not_create_moment_or_photo(self):
        invalid = SimpleUploadedFile("broken.gif", b"not-a-gif", content_type="image/gif")

        response = self.client.post(
            reverse("room_moments_new", args=[self.room.pk]),
            {
                "body": "保存されない瞬間",
                "occurred_at": self.occurred_at,
                "images": invalid,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "画像ファイルを読み取れませんでした。")
        self.assertFalse(MomentLog.objects.filter(room=self.room).exists())
        self.assertFalse(Photo.objects.exists())


class PageRenderingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="page-reviewer",
            password="test-password-123",
        )
        now = timezone.now()
        self.room = Room.objects.create(
            owner=self.user,
            name="全ページ確認Room",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
        )
        self.task = Task.objects.create(room=self.room, title="表示確認タスク")
        self.moment = MomentLog.objects.create(
            room=self.room,
            task=self.task,
            body="表示確認SHUNKAN-log",
            occurred_at=now,
        )
        self.photo = Photo.objects.create(
            moment_log=self.moment,
            image="moment_photos/page-test.jpg",
            caption="表示確認写真",
        )
        self.client.force_login(self.user)

    def test_all_authenticated_pages_render_with_the_shared_layout(self):
        urls = [
            reverse("profile"),
            reverse("rooms"),
            reverse("room_detail", args=[self.room.pk]),
            reverse("room_update", args=[self.room.pk]),
            reverse("room_tasks", args=[self.room.pk]),
            reverse("task_update", args=[self.room.pk, self.task.pk]),
            reverse("moment_list", args=[self.room.pk]),
            reverse("room_moments_new", args=[self.room.pk]),
            reverse("moment_update", args=[self.room.pk, self.moment.pk]),
            reverse("photo_list", args=[self.room.pk]),
            reverse("photo_update", args=[self.room.pk, self.photo.pk]),
            reverse("room_album", args=[self.room.pk]),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "旬間 (SHUNKAN)")
                self.assertContains(response, 'id="main-content"')

    def test_bottom_navigation_uses_the_expected_order_and_labels(self):
        response = self.client.get(reverse("room_detail", args=[self.room.pk]))
        content = response.content.decode()

        positions = [
            content.index(">Room</span>"),
            content.index(">タスク</span>"),
            content.index(">撮影</span>"),
            content.index(">アルバム</span>"),
            content.index(">アカウント</span>"),
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertContains(response, "bottom-nav__icon", count=4)


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
        self.assertContains(response, '<h1 id="rooms-title">Room</h1>', html=True)

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

    def test_owner_can_update_own_room(self):
        response = self.client.post(
            reverse("room_update", args=[self.owner_room.pk]),
            {
                "name": "更新したRoom",
                "starts_at": "2026-08-20T12:00",
                "ends_at": "2026-08-30T12:00",
            },
        )

        self.assertRedirects(
            response, reverse("room_detail", args=[self.owner_room.pk])
        )
        self.owner_room.refresh_from_db()
        self.assertEqual(self.owner_room.name, "更新したRoom")

    def test_cannot_update_another_users_room(self):
        response = self.client.post(
            reverse("room_update", args=[self.other_room.pk]),
            {
                "name": "書き換え",
                "starts_at": "2026-08-20T12:00",
                "ends_at": "2026-08-30T12:00",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.other_room.refresh_from_db()
        self.assertEqual(self.other_room.name, "他人のRoom")

    def test_owner_can_delete_own_room(self):
        response = self.client.post(reverse("room_delete", args=[self.owner_room.pk]))

        self.assertRedirects(response, reverse("rooms"))
        self.assertFalse(Room.objects.filter(pk=self.owner_room.pk).exists())

    def test_cannot_delete_another_users_room(self):
        response = self.client.post(reverse("room_delete", args=[self.other_room.pk]))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Room.objects.filter(pk=self.other_room.pk).exists())


class TaskOwnerAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="task-owner", password="pass123")
        self.other = User.objects.create_user(username="task-other", password="pass123")
        now = timezone.now()
        self.owned_room = Room.objects.create(
            owner=self.owner,
            name="自分のRoom",
            starts_at=now,
            ends_at=now + timedelta(days=7),
        )
        self.other_room = Room.objects.create(
            owner=self.other,
            name="他人のRoom",
            starts_at=now,
            ends_at=now + timedelta(days=7),
        )
        self.owned_task = Task.objects.create(room=self.owned_room, title="自分のタスク")
        self.other_task = Task.objects.create(room=self.other_room, title="他人のタスク")
        self.client.force_login(self.owner)

    def test_list_shows_only_tasks_in_owned_room(self):
        response = self.client.get(reverse("task_list", args=[self.owned_room.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "自分のタスク")
        self.assertNotContains(response, "他人のタスク")

    def test_other_users_task_list_returns_404(self):
        response = self.client.get(reverse("task_list", args=[self.other_room.pk]))

        self.assertEqual(response.status_code, 404)

    def test_owner_can_update_own_task(self):
        response = self.client.post(
            reverse("task_update", args=[self.owned_room.pk, self.owned_task.pk]),
            {"title": "更新したタスク", "due_date": ""},
        )

        self.assertRedirects(response, reverse("task_list", args=[self.owned_room.pk]))
        self.owned_task.refresh_from_db()
        self.assertEqual(self.owned_task.title, "更新したタスク")

    def test_cannot_update_another_users_task(self):
        response = self.client.post(
            reverse("task_update", args=[self.other_room.pk, self.other_task.pk]),
            {"title": "書き換え", "due_date": ""},
        )

        self.assertEqual(response.status_code, 404)
        self.other_task.refresh_from_db()
        self.assertEqual(self.other_task.title, "他人のタスク")

    def test_cannot_update_another_users_task_via_owned_room_url(self):
        response = self.client.post(
            reverse("task_update", args=[self.owned_room.pk, self.other_task.pk]),
            {"title": "書き換え", "due_date": ""},
        )

        self.assertEqual(response.status_code, 404)
        self.other_task.refresh_from_db()
        self.assertEqual(self.other_task.title, "他人のタスク")

    def test_owner_can_delete_own_task(self):
        response = self.client.post(
            reverse("task_delete", args=[self.owned_room.pk, self.owned_task.pk])
        )

        self.assertRedirects(response, reverse("task_list", args=[self.owned_room.pk]))
        self.assertFalse(Task.objects.filter(pk=self.owned_task.pk).exists())

    def test_cannot_delete_another_users_task(self):
        response = self.client.post(
            reverse("task_delete", args=[self.other_room.pk, self.other_task.pk])
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Task.objects.filter(pk=self.other_task.pk).exists())


class MomentLogOwnerAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="moment-owner", password="pass123")
        self.other = User.objects.create_user(username="moment-other", password="pass123")
        now = timezone.now()
        self.owned_room = Room.objects.create(
            owner=self.owner,
            name="自分のRoom",
            starts_at=now,
            ends_at=now + timedelta(days=7),
        )
        self.other_room = Room.objects.create(
            owner=self.other,
            name="他人のRoom",
            starts_at=now,
            ends_at=now + timedelta(days=7),
        )
        self.owned_moment = MomentLog.objects.create(
            room=self.owned_room,
            body="自分の記録",
            occurred_at=now,
        )
        self.other_moment = MomentLog.objects.create(
            room=self.other_room,
            body="他人の記録",
            occurred_at=now,
        )
        self.client.force_login(self.owner)

    def test_list_shows_only_moment_logs_in_owned_room(self):
        response = self.client.get(reverse("moment_list", args=[self.owned_room.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "自分の記録")
        self.assertNotContains(response, "他人の記録")

    def test_other_users_moment_list_returns_404(self):
        response = self.client.get(reverse("moment_list", args=[self.other_room.pk]))

        self.assertEqual(response.status_code, 404)

    def test_owner_can_update_own_moment_log(self):
        response = self.client.post(
            reverse("moment_update", args=[self.owned_room.pk, self.owned_moment.pk]),
            {"body": "更新した記録"},
        )

        self.assertRedirects(response, reverse("moment_list", args=[self.owned_room.pk]))
        self.owned_moment.refresh_from_db()
        self.assertEqual(self.owned_moment.body, "更新した記録")

    def test_cannot_update_another_users_moment_log(self):
        response = self.client.post(
            reverse("moment_update", args=[self.other_room.pk, self.other_moment.pk]),
            {"body": "書き換え"},
        )

        self.assertEqual(response.status_code, 404)
        self.other_moment.refresh_from_db()
        self.assertEqual(self.other_moment.body, "他人の記録")

    def test_owner_can_delete_own_moment_log(self):
        response = self.client.post(
            reverse("moment_delete", args=[self.owned_room.pk, self.owned_moment.pk])
        )

        self.assertRedirects(response, reverse("moment_list", args=[self.owned_room.pk]))
        self.assertFalse(MomentLog.objects.filter(pk=self.owned_moment.pk).exists())

    def test_cannot_delete_another_users_moment_log(self):
        response = self.client.post(
            reverse("moment_delete", args=[self.other_room.pk, self.other_moment.pk])
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(MomentLog.objects.filter(pk=self.other_moment.pk).exists())


class PhotoOwnerAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="photo-owner", password="pass123")
        self.other = User.objects.create_user(username="photo-other", password="pass123")
        now = timezone.now()
        self.owned_room = Room.objects.create(
            owner=self.owner,
            name="自分のRoom",
            starts_at=now,
            ends_at=now + timedelta(days=7),
        )
        self.other_room = Room.objects.create(
            owner=self.other,
            name="他人のRoom",
            starts_at=now,
            ends_at=now + timedelta(days=7),
        )
        self.owned_moment = MomentLog.objects.create(
            room=self.owned_room,
            body="自分の記録",
            occurred_at=now,
        )
        self.other_moment = MomentLog.objects.create(
            room=self.other_room,
            body="他人の記録",
            occurred_at=now,
        )
        self.owned_photo = Photo.objects.create(
            moment_log=self.owned_moment,
            image=SimpleUploadedFile("mine.jpg", b"fake-image-data", content_type="image/jpeg"),
            caption="自分の写真",
        )
        self.other_photo = Photo.objects.create(
            moment_log=self.other_moment,
            image=SimpleUploadedFile("theirs.jpg", b"fake-image-data", content_type="image/jpeg"),
            caption="他人の写真",
        )
        self.client.force_login(self.owner)

    def test_list_shows_only_photos_in_owned_room(self):
        response = self.client.get(reverse("photo_list", args=[self.owned_room.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "自分の写真")
        self.assertNotContains(response, "他人の写真")

    def test_other_users_photo_list_returns_404(self):
        response = self.client.get(reverse("photo_list", args=[self.other_room.pk]))

        self.assertEqual(response.status_code, 404)

    def test_owner_can_update_own_photo(self):
        response = self.client.post(
            reverse("photo_update", args=[self.owned_room.pk, self.owned_photo.pk]),
            {"caption": "更新した写真"},
        )

        self.assertRedirects(response, reverse("photo_list", args=[self.owned_room.pk]))
        self.owned_photo.refresh_from_db()
        self.assertEqual(self.owned_photo.caption, "更新した写真")

    def test_cannot_update_another_users_photo(self):
        response = self.client.post(
            reverse("photo_update", args=[self.other_room.pk, self.other_photo.pk]),
            {"caption": "書き換え"},
        )

        self.assertEqual(response.status_code, 404)
        self.other_photo.refresh_from_db()
        self.assertEqual(self.other_photo.caption, "他人の写真")

    def test_cannot_update_another_users_photo_via_owned_room_url(self):
        response = self.client.post(
            reverse("photo_update", args=[self.owned_room.pk, self.other_photo.pk]),
            {"caption": "書き換え"},
        )

        self.assertEqual(response.status_code, 404)
        self.other_photo.refresh_from_db()
        self.assertEqual(self.other_photo.caption, "他人の写真")

    def test_owner_can_delete_own_photo(self):
        response = self.client.post(
            reverse("photo_delete", args=[self.owned_room.pk, self.owned_photo.pk])
        )

        self.assertRedirects(response, reverse("photo_list", args=[self.owned_room.pk]))
        self.assertFalse(Photo.objects.filter(pk=self.owned_photo.pk).exists())

    def test_cannot_delete_another_users_photo(self):
        response = self.client.post(
            reverse("photo_delete", args=[self.other_room.pk, self.other_photo.pk])
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Photo.objects.filter(pk=self.other_photo.pk).exists())

    def test_task_and_moment_posts_are_rejected_outside_active_room(self):
        now = timezone.now()
        rooms = (
            Room.objects.create(owner=self.owner, name="開催前", starts_at=now + timedelta(days=1), ends_at=now + timedelta(days=2)),
            Room.objects.create(owner=self.owner, name="終了済み", starts_at=now - timedelta(days=2), ends_at=now - timedelta(days=1)),
            Room.objects.create(owner=self.owner, name="アーカイブ", starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=1), is_archived=True),
        )

        for room in rooms:
            with self.subTest(room=room.name, endpoint="tasks"):
                response = self.client.post(reverse("room_tasks", args=[room.pk]), {"title": "追加不可"})
                self.assertEqual(response.status_code, 403)
                self.assertFalse(room.tasks.exists())
            with self.subTest(room=room.name, endpoint="moments"):
                response = self.client.post(reverse("room_moments_new", args=[room.pk]), {})
                self.assertEqual(response.status_code, 403)
                self.assertFalse(room.moment_logs.exists())


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
        self.room = Room.objects.create(
            owner=self.user,
            name="UI確認Room",
            starts_at=timezone.make_aware(datetime(2026, 8, 20, 12, 0, 0)),
            ends_at=timezone.make_aware(datetime(2026, 8, 30, 12, 0, 0)),
        )
        self.client.force_login(self.user)

    def test_template_preview_pages_are_available(self):
        for path in (
            "/rooms/",
            f"/rooms/{self.room.pk}/",
            f"/rooms/{self.room.pk}/tasks/",
            f"/rooms/{self.room.pk}/moments/new/",
            f"/rooms/{self.room.pk}/album/",
            "/profile/",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)


    def test_album_page_uses_shared_app_shell(self):
        response = self.client.get(f"/rooms/{self.room.pk}/album/")

        self.assertContains(response, "/static/core/css/app.css")
        self.assertContains(response, "アルバム")
        self.assertContains(response, 'aria-current="page"')

    def test_post_forms_include_csrf_tokens(self):
        for path in ("/rooms/", f"/rooms/{self.room.pk}/tasks/", f"/rooms/{self.room.pk}/moments/new/"):
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
