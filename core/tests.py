from datetime import datetime, timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from typing import cast
from unittest.mock import Mock, patch

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .image_processing import (
    MAX_IMAGE_DIMENSION,
    MAX_SOURCE_PIXELS,
    MAX_UPLOAD_SIZE,
    process_uploaded_image,
    read_captured_at,
)
from .forms import MomentLogForm, RoomForm, TaskForm
from .models import Room, Category, Task, MomentLog, Photo
from .room_state import log_post_permission


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

    def make_exif_jpeg(self, dt_string):
        output = BytesIO()
        exif = Image.Exif()
        # 36867: DateTimeOriginal、36868: DateTimeDigitized
        exif[36867] = dt_string
        Image.new("RGB", (1200, 800), "coral").save(
            output,
            format="JPEG",
            exif=exif,
        )
        return SimpleUploadedFile("exif.jpg", output.getvalue(), content_type="image/jpeg")

    def test_read_captured_at_reads_exif_datetime(self):
        captured = read_captured_at(self.make_exif_jpeg("2026:08:20 15:30:00"))

        self.assertIsNotNone(captured)
        self.assertEqual(captured.year, 2026)
        self.assertEqual(captured.month, 8)
        self.assertEqual(captured.day, 20)
        self.assertEqual(captured.hour, 15)
        self.assertEqual(captured.minute, 30)
        self.assertTrue(timezone.is_aware(captured))

    def test_read_captured_at_returns_none_without_exif(self):
        output = BytesIO()
        Image.new("RGB", (1200, 800), "coral").save(output, format="JPEG")
        upload = SimpleUploadedFile("plain.jpg", output.getvalue(), content_type="image/jpeg")

        self.assertIsNone(read_captured_at(upload))

    def test_read_captured_at_returns_none_for_non_jpeg(self):
        output = BytesIO()
        Image.new("RGB", (1200, 800), "coral").save(output, format="PNG")
        upload = SimpleUploadedFile("plain.png", output.getvalue(), content_type="image/png")

        self.assertIsNone(read_captured_at(upload))

    @patch("core.image_processing.Image.open")
    def test_image_with_too_many_pixels_is_rejected(self, image_open):
        image_open.return_value.__enter__.return_value = Mock(
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

    def make_exif_jpeg(self, dt_string="2026:08:20 15:30:00"):
        output = BytesIO()
        exif = Image.Exif()
        exif[36867] = dt_string
        Image.new("RGB", (1200, 800), "coral").save(
            output,
            format="JPEG",
            exif=exif,
        )
        return SimpleUploadedFile("exif.jpg", output.getvalue(), content_type="image/jpeg")

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
        self.assertLess(abs((moment.occurred_at - timezone.now()).total_seconds()), 60)
        with Image.open(photo.image) as image:
            self.assertLessEqual(max(image.size), MAX_IMAGE_DIMENSION)

    def test_photo_can_complete_the_selected_task(self):
        task = Task.objects.create(room=self.room, title="写真で完了するタスク")

        response = self.client.post(
            reverse("room_moments_new", args=[self.room.pk]),
            {
                "body": "写真と一緒に完了",
                "task": task.pk,
                "complete_task": "1",
                "images": self.make_jpeg(),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
            response.context["form"].errors.as_json() if response.context else "",
        )
        self.assertRedirects(response, reverse("room_album", args=[self.room.pk]))
        task.refresh_from_db()
        self.assertTrue(task.is_completed)
        self.assertIsNotNone(task.completed_at)
        moment = MomentLog.objects.get(task=task)
        self.assertEqual(moment.occurred_at, task.completed_at)
        self.assertEqual(moment.photos.count(), 1)

    def test_completed_task_photo_flow_preserves_completion_and_creates_nothing(self):
        completed_at = timezone.now() - timedelta(minutes=10)
        task = Task.objects.create(
            room=self.room,
            title="完了済みタスク",
            is_completed=True,
            completed_at=completed_at,
        )

        response = self.client.post(
            reverse("room_moments_new", args=[self.room.pk]),
            {
                "body": "重複して完了しない",
                "task": task.pk,
                "complete_task": "1",
                "images": self.make_jpeg(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "このタスクはすでに完了しています。")
        task.refresh_from_db()
        self.assertEqual(task.completed_at, completed_at)
        self.assertFalse(MomentLog.objects.filter(task=task).exists())
        self.assertFalse(Photo.objects.filter(moment_log__task=task).exists())

    def test_task_completion_requires_a_photo(self):
        task = Task.objects.create(room=self.room, title="写真が必要なタスク")

        response = self.client.post(
            reverse("room_moments_new", args=[self.room.pk]),
            {
                "body": "写真なしでは完了しない",
                "task": task.pk,
                "complete_task": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "写真を1枚以上追加してください。")
        task.refresh_from_db()
        self.assertFalse(task.is_completed)
        self.assertFalse(MomentLog.objects.filter(task=task).exists())

    def test_photo_saves_exif_candidate_as_captured_at_source(self):
        response = self.client.post(
            reverse("room_moments_new", args=[self.room.pk]),
            {
                "body": "EXIFの写真",
                "images": self.make_exif_jpeg(),
                "captured_at": ["2026-08-20T15:30"],
                "captured_at_source": ["exif"],
            },
        )

        self.assertRedirects(response, reverse("room_album", args=[self.room.pk]))
        photo = Photo.objects.get(moment_log__room=self.room)
        self.assertEqual(photo.captured_at_source, Photo.CapturedAtSource.EXIF)
        self.assertIsNotNone(photo.captured_at)
        self.assertEqual(photo.captured_at.year, 2026)

    def test_photo_saves_manual_captured_at_when_user_provides_value(self):
        response = self.client.post(
            reverse("room_moments_new", args=[self.room.pk]),
            {
                "body": "手入力の写真",
                "images": self.make_jpeg(),
                "captured_at": ["2026-08-21T09:15"],
                "captured_at_source": ["manual"],
            },
        )

        self.assertRedirects(response, reverse("room_album", args=[self.room.pk]))
        photo = Photo.objects.get(moment_log__room=self.room)
        self.assertEqual(photo.captured_at_source, Photo.CapturedAtSource.MANUAL)
        local_captured = timezone.localtime(photo.captured_at)
        self.assertEqual(local_captured.hour, 9)
        self.assertEqual(local_captured.minute, 15)

    def test_photo_saves_unknown_when_exif_candidate_is_removed(self):
        response = self.client.post(
            reverse("room_moments_new", args=[self.room.pk]),
            {
                "body": "EXIF候補を削除した写真",
                "images": self.make_exif_jpeg(),
                "captured_at": [""],
                "captured_at_source": ["unknown"],
            },
        )

        self.assertRedirects(response, reverse("room_album", args=[self.room.pk]))
        photo = Photo.objects.get(moment_log__room=self.room)
        self.assertEqual(photo.captured_at_source, Photo.CapturedAtSource.UNKNOWN)
        self.assertIsNone(photo.captured_at)

    def test_invalid_captured_at_is_shown_as_form_error(self):
        response = self.client.post(
            reverse("room_moments_new", args=[self.room.pk]),
            {
                "body": "不正日時の写真",
                "images": self.make_jpeg(),
                "captured_at": ["not-a-date"],
                "captured_at_source": ["manual"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "撮影日時を確認してください。")
        self.assertFalse(Photo.objects.filter(moment_log__room=self.room).exists())

    def test_photo_saves_unknown_when_no_datetime_is_given(self):
        response = self.client.post(
            reverse("room_moments_new", args=[self.room.pk]),
            {
                "body": "日時不明の写真",
                "images": self.make_jpeg(),
            },
        )

        self.assertRedirects(response, reverse("room_album", args=[self.room.pk]))
        photo = Photo.objects.get(moment_log__room=self.room)
        self.assertEqual(photo.captured_at_source, Photo.CapturedAtSource.UNKNOWN)
        self.assertIsNone(photo.captured_at)

    @override_settings(ALLOW_PHOTO_UPLOADS=False)
    def test_photo_upload_is_rejected_when_storage_is_disabled(self):
        response = self.client.post(
            reverse("room_moments_new", args=[self.room.pk]),
            {"body": "保存しない写真", "images": self.make_jpeg()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "写真アップロードを一時停止しています")
        self.assertFalse(MomentLog.objects.filter(room=self.room).exists())
        self.assertFalse(Photo.objects.exists())

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
        self.category = Category.objects.create(room=self.room, name="表示確認カテゴリ")
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
            reverse("room_categories", args=[self.room.pk]),
            reverse("category_update", args=[self.room.pk, self.category.pk]),
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


class CategoryViewTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="category-owner",
            password="test-password-123",
        )
        self.other = get_user_model().objects.create_user(
            username="category-other",
            password="test-password-123",
        )
        now = timezone.now()
        self.owned_room = Room.objects.create(
            owner=self.owner,
            name="自分のRoom",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=7),
        )
        self.other_room = Room.objects.create(
            owner=self.other,
            name="他人のRoom",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=7),
        )
        self.category = Category.objects.create(room=self.owned_room, name="花火")
        self.other_category = Category.objects.create(room=self.other_room, name="準備")
        self.client.force_login(self.owner)

    def test_list_shows_only_own_categories(self):
        response = self.client.get(reverse("room_categories", args=[self.owned_room.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "花火")
        self.assertNotContains(response, "準備")

    def test_other_users_category_list_returns_404(self):
        response = self.client.get(reverse("room_categories", args=[self.other_room.pk]))

        self.assertEqual(response.status_code, 404)

    def test_owner_can_create_category(self):
        response = self.client.post(
            reverse("room_categories", args=[self.owned_room.pk]),
            {"name": "グルメ", "color": "#FB8500"},
        )

        self.assertRedirects(response, reverse("room_categories", args=[self.owned_room.pk]))
        category = Category.objects.get(room=self.owned_room, name="グルメ")
        self.assertEqual(category.color, "#FB8500")
        self.assertEqual(category.sort_order, 1)

    def test_owner_can_update_category(self):
        response = self.client.post(
            reverse("category_update", args=[self.owned_room.pk, self.category.pk]),
            {"name": "夏祭り", "color": ""},
        )

        self.assertRedirects(response, reverse("room_categories", args=[self.owned_room.pk]))
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, "夏祭り")

    def test_cannot_update_another_users_category(self):
        response = self.client.post(
            reverse("category_update", args=[self.owned_room.pk, self.other_category.pk]),
            {"name": "書き換え", "color": ""},
        )

        self.assertEqual(response.status_code, 404)
        self.other_category.refresh_from_db()
        self.assertEqual(self.other_category.name, "準備")

    def test_owner_can_delete_category(self):
        response = self.client.post(
            reverse("category_delete", args=[self.owned_room.pk, self.category.pk])
        )

        self.assertRedirects(response, reverse("room_categories", args=[self.owned_room.pk]))
        self.assertFalse(Category.objects.filter(pk=self.category.pk).exists())

    def test_cannot_delete_another_users_category(self):
        response = self.client.post(
            reverse("category_delete", args=[self.owned_room.pk, self.other_category.pk])
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Category.objects.filter(pk=self.other_category.pk).exists())

    def test_category_posts_are_rejected_outside_active_room(self):
        ended_room = Room.objects.create(
            owner=self.owner,
            name="終了したRoom",
            starts_at=timezone.now() - timedelta(days=7),
            ends_at=timezone.now() - timedelta(days=1),
        )

        response = self.client.post(
            reverse("room_categories", args=[ended_room.pk]),
            {"name": "追加", "color": ""},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Category.objects.filter(room=ended_room).exists())

    def test_quick_create_adds_category_to_owned_room(self):
        response = self.client.post(
            reverse("category_quick_create", args=[self.owned_room.pk]),
            {"name": "即席カテゴリ", "color": ""},
        )

        self.assertEqual(response.status_code, 200)
        category = Category.objects.get(room=self.owned_room, name="即席カテゴリ")
        data = response.json()
        self.assertEqual(data["id"], category.pk)
        self.assertEqual(data["label"], "即席カテゴリ")

    def test_quick_create_rejects_duplicate_category_name(self):
        response = self.client.post(
            reverse("category_quick_create", args=[self.owned_room.pk]),
            {"name": "花火", "color": ""},
        )

        self.assertEqual(response.status_code, 400)

    def test_quick_create_rejects_another_users_room(self):
        response = self.client.post(
            reverse("category_quick_create", args=[self.other_room.pk]),
            {"name": "他人のRoomに追加", "color": ""},
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Category.objects.filter(name="他人のRoomに追加").exists())


class MomentLogFormTests(TestCase):
    def test_task_choices_show_title_and_due_date(self):
        user = get_user_model().objects.create_user(
            username="form-user",
            password="test-password-123",
        )
        now = timezone.now()
        room = Room.objects.create(
            owner=user,
            name="フォーム確認Room",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=7),
        )
        task = Task.objects.create(
            room=room,
            title="花火を見る",
            due_date=(now + timedelta(days=2)).date(),
        )

        form = MomentLogForm(room=room)
        task_field = cast(forms.ModelChoiceField, form.fields["task"])
        label = task_field.label_from_instance(task)

        self.assertIn("花火を見る", label)
        self.assertIn("まで", label)


class RoomReflectionDeadlineFormTests(TestCase):
    def test_room_form_sets_reflection_deadline_to_seven_days_after_end(self):
        starts_at = timezone.now() + timedelta(days=1)
        ends_at = starts_at + timedelta(days=2)
        form = RoomForm(
            {
                "name": "振り返り期限確認Room",
                "starts_at": starts_at,
                "ends_at": ends_at,
            }
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        room = form.save(commit=False)
        self.assertEqual(room.reflection_deadline_at, ends_at + timedelta(days=7))

    def test_room_form_recalculates_deadline_when_end_is_updated(self):
        user = get_user_model().objects.create_user(username="room-form-user")
        starts_at = timezone.now() - timedelta(hours=1)
        room = Room.objects.create(
            owner=user,
            name="更新前Room",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=1),
            reflection_deadline_at=starts_at + timedelta(days=8),
        )
        new_ends_at = starts_at + timedelta(days=2)
        form = RoomForm(
            {
                "name": room.name,
                "starts_at": starts_at,
                "ends_at": new_ends_at,
            },
            instance=room,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        updated_room = form.save()
        self.assertEqual(
            updated_room.reflection_deadline_at,
            new_ends_at + timedelta(days=7),
        )


class LogPostPermissionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="permission-user",
            password="test-password-123",
        )
        self.starts_at = timezone.make_aware(datetime(2026, 8, 1, 9, 0, 0))
        self.ends_at = timezone.make_aware(datetime(2026, 8, 31, 23, 59, 59))
        self.reflection_deadline_at = timezone.make_aware(
            datetime(2026, 9, 7, 23, 59, 59)
        )
        self.tick = timedelta(microseconds=1)

    def make_room(self, *, reflection_deadline_at=None, is_archived=False):
        return Room.objects.create(
            owner=self.user,
            name="判定確認Room",
            starts_at=self.starts_at,
            ends_at=self.ends_at,
            reflection_deadline_at=reflection_deadline_at,
            is_archived=is_archived,
        )

    def test_moment_is_allowed_from_start_until_just_before_end(self):
        room = self.make_room(reflection_deadline_at=self.reflection_deadline_at)

        for label, now in (
            ("開始時刻", self.starts_at),
            ("終了直前", self.ends_at - self.tick),
        ):
            with self.subTest(boundary=label):
                permission = log_post_permission(
                    room, MomentLog.EntryType.MOMENT, now=now
                )
                self.assertTrue(permission.allowed)
                self.assertEqual(permission.reason, "moment_open")

    def test_moment_is_rejected_before_start_and_from_end(self):
        room = self.make_room(reflection_deadline_at=self.reflection_deadline_at)

        for label, now, reason in (
            ("開始直前", self.starts_at - self.tick, "room_not_started"),
            ("終了時刻", self.ends_at, "room_ended"),
            ("終了後", self.ends_at + timedelta(days=1), "room_ended"),
        ):
            with self.subTest(boundary=label):
                permission = log_post_permission(
                    room, MomentLog.EntryType.MOMENT, now=now
                )
                self.assertFalse(permission.allowed)
                self.assertEqual(permission.reason, reason)

    def test_reflection_is_allowed_from_end_until_deadline(self):
        room = self.make_room(reflection_deadline_at=self.reflection_deadline_at)

        for label, now in (
            ("終了時刻", self.ends_at),
            ("期限直前", self.reflection_deadline_at - self.tick),
            ("期限時刻", self.reflection_deadline_at),
        ):
            with self.subTest(boundary=label):
                permission = log_post_permission(
                    room, MomentLog.EntryType.REFLECTION, now=now
                )
                self.assertTrue(permission.allowed)
                self.assertEqual(permission.reason, "reflection_open")

    def test_reflection_is_rejected_before_end_and_after_deadline(self):
        room = self.make_room(reflection_deadline_at=self.reflection_deadline_at)

        for label, now, reason in (
            ("終了直前", self.ends_at - self.tick, "room_not_ended"),
            ("期限直後", self.reflection_deadline_at + self.tick, "reflection_closed"),
        ):
            with self.subTest(boundary=label):
                permission = log_post_permission(
                    room, MomentLog.EntryType.REFLECTION, now=now
                )
                self.assertFalse(permission.allowed)
                self.assertEqual(permission.reason, reason)

    def test_reflection_is_rejected_when_deadline_is_unset(self):
        room = self.make_room()

        permission = log_post_permission(
            room, MomentLog.EntryType.REFLECTION, now=self.ends_at
        )

        self.assertFalse(permission.allowed)
        self.assertEqual(permission.reason, "reflection_deadline_unset")

    def test_archived_room_rejects_every_entry_type(self):
        room = self.make_room(
            reflection_deadline_at=self.reflection_deadline_at,
            is_archived=True,
        )

        for entry_type, now in (
            (MomentLog.EntryType.MOMENT, self.starts_at),
            (MomentLog.EntryType.REFLECTION, self.ends_at),
        ):
            with self.subTest(entry_type=entry_type):
                permission = log_post_permission(room, entry_type, now=now)
                self.assertFalse(permission.allowed)
                self.assertEqual(permission.reason, "archived")

    def test_form_rejects_post_outside_the_allowed_window(self):
        room = self.make_room(reflection_deadline_at=self.reflection_deadline_at)

        form = MomentLogForm(
            {"body": "終了後の通常ログ", "entry_type": MomentLog.EntryType.MOMENT},
            room=room,
            now=self.ends_at,
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "Roomが終了したため、通常のSHUNKAN-logは投稿できません。",
            form.non_field_errors(),
        )


class ReflectionPostViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="reflection-user",
            password="test-password-123",
        )
        self.client.force_login(self.user)
        self.now = timezone.now()

    def make_room(self, *, starts_at, ends_at, reflection_deadline_at=None):
        return Room.objects.create(
            owner=self.user,
            name="振り返りRoom",
            starts_at=starts_at,
            ends_at=ends_at,
            reflection_deadline_at=reflection_deadline_at,
        )

    def post_log(self, room, entry_type):
        return self.client.post(
            reverse("room_moments_new", args=[room.pk]),
            {"body": "投稿本文", "entry_type": entry_type},
        )

    def test_reflection_is_saved_inside_the_reflection_period(self):
        room = self.make_room(
            starts_at=self.now - timedelta(days=3),
            ends_at=self.now - timedelta(days=1),
            reflection_deadline_at=self.now + timedelta(days=1),
        )

        response = self.post_log(room, MomentLog.EntryType.REFLECTION)

        self.assertRedirects(response, reverse("room_album", args=[room.pk]))
        log = MomentLog.objects.get(room=room)
        self.assertEqual(log.entry_type, MomentLog.EntryType.REFLECTION)
        self.assertLess(abs((log.occurred_at - timezone.now()).total_seconds()), 5)
        self.assertIsNone(log.task)
        self.assertIsNone(log.category)
        self.assertFalse(log.photos.exists())

    def test_moment_is_rejected_inside_the_reflection_period(self):
        room = self.make_room(
            starts_at=self.now - timedelta(days=3),
            ends_at=self.now - timedelta(days=1),
            reflection_deadline_at=self.now + timedelta(days=1),
        )

        response = self.post_log(room, MomentLog.EntryType.MOMENT)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(MomentLog.objects.filter(room=room).exists())

    def test_reflection_is_rejected_while_the_room_is_open(self):
        room = self.make_room(
            starts_at=self.now - timedelta(hours=1),
            ends_at=self.now + timedelta(hours=1),
            reflection_deadline_at=self.now + timedelta(days=7),
        )

        response = self.post_log(room, MomentLog.EntryType.REFLECTION)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(MomentLog.objects.filter(room=room).exists())

    def test_reflection_is_rejected_when_the_deadline_is_unset(self):
        room = self.make_room(
            starts_at=self.now - timedelta(days=3),
            ends_at=self.now - timedelta(days=1),
        )

        response = self.post_log(room, MomentLog.EntryType.REFLECTION)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(MomentLog.objects.filter(room=room).exists())

    def test_reflection_is_rejected_after_the_deadline(self):
        room = self.make_room(
            starts_at=self.now - timedelta(days=5),
            ends_at=self.now - timedelta(days=3),
            reflection_deadline_at=self.now - timedelta(days=1),
        )

        response = self.post_log(room, MomentLog.EntryType.REFLECTION)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(MomentLog.objects.filter(room=room).exists())

    def test_moment_is_saved_while_the_room_is_open(self):
        room = self.make_room(
            starts_at=self.now - timedelta(hours=1),
            ends_at=self.now + timedelta(hours=1),
            reflection_deadline_at=self.now + timedelta(days=7),
        )

        response = self.post_log(room, MomentLog.EntryType.MOMENT)

        self.assertRedirects(response, reverse("room_album", args=[room.pk]))
        log = MomentLog.objects.get(room=room)
        self.assertEqual(log.entry_type, MomentLog.EntryType.MOMENT)

    def test_unknown_entry_type_is_not_saved(self):
        room = self.make_room(
            starts_at=self.now - timedelta(hours=1),
            ends_at=self.now + timedelta(hours=1),
            reflection_deadline_at=self.now + timedelta(days=7),
        )

        response = self.post_log(room, "hacked")

        self.assertEqual(response.status_code, 200)
        self.assertIn("entry_type", response.context["form"].errors)
        self.assertFalse(MomentLog.objects.filter(room=room).exists())

    def test_reflection_page_shows_body_only_and_reflection_navigation(self):
        room = self.make_room(
            starts_at=self.now - timedelta(days=3),
            ends_at=self.now - timedelta(days=1),
            reflection_deadline_at=self.now + timedelta(days=6),
        )

        response = self.client.get(reverse("room_moments_new", args=[room.pk]))
        content = response.content.decode()

        self.assertContains(response, "振り返りを残す")
        self.assertContains(response, 'name="entry_type" value="reflection"')
        self.assertContains(response, "振り返りを保存する")
        self.assertNotContains(response, 'name="images"')
        self.assertNotContains(response, "関連Task")
        self.assertNotContains(response, "カテゴリ")
        self.assertIn("振り返り", content)

    def test_room_detail_shows_reflection_cta_and_deadline(self):
        room = self.make_room(
            starts_at=self.now - timedelta(days=3),
            ends_at=self.now - timedelta(days=1),
            reflection_deadline_at=self.now + timedelta(days=6),
        )

        response = self.client.get(reverse("room_detail", args=[room.pk]))

        self.assertContains(response, "振り返りを残す")
        self.assertContains(response, "まで投稿できます")
        self.assertNotContains(response, "期間・名前を編集")

    def test_forged_reflection_relations_and_completion_are_rejected(self):
        room = self.make_room(
            starts_at=self.now - timedelta(days=3),
            ends_at=self.now - timedelta(days=1),
            reflection_deadline_at=self.now + timedelta(days=6),
        )
        category = Category.objects.create(room=room, name="不正カテゴリ")
        task = Task.objects.create(room=room, title="不正Task")

        response = self.client.post(
            reverse("room_moments_new", args=[room.pk]),
            {
                "body": "関連付けを偽装",
                "entry_type": MomentLog.EntryType.REFLECTION,
                "task": task.pk,
                "category": category.pk,
                "complete_task": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Task・カテゴリを関連付けできません")
        self.assertContains(response, "Taskを完了できません")
        self.assertFalse(MomentLog.objects.filter(room=room).exists())
        task.refresh_from_db()
        self.assertFalse(task.is_completed)

    def test_forged_reflection_photo_is_rejected(self):
        room = self.make_room(
            starts_at=self.now - timedelta(days=3),
            ends_at=self.now - timedelta(days=1),
            reflection_deadline_at=self.now + timedelta(days=6),
        )
        output = BytesIO()
        Image.new("RGB", (20, 20), "navy").save(output, format="JPEG")
        image = SimpleUploadedFile(
            "reflection.jpg",
            output.getvalue(),
            content_type="image/jpeg",
        )

        response = self.client.post(
            reverse("room_moments_new", args=[room.pk]),
            {
                "body": "写真を偽装",
                "entry_type": MomentLog.EntryType.REFLECTION,
                "images": image,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "振り返りログには写真を追加できません")
        self.assertFalse(MomentLog.objects.filter(room=room).exists())
        self.assertFalse(Photo.objects.exists())

    def test_page_returns_the_reason_when_posting_is_closed(self):
        room = self.make_room(
            starts_at=self.now - timedelta(days=3),
            ends_at=self.now - timedelta(days=1),
            reflection_deadline_at=self.now + timedelta(days=1),
        )

        response = self.client.get(reverse("room_moments_new", args=[room.pk]))

        self.assertFalse(response.context["can_post_moment"])
        self.assertTrue(response.context["can_post_reflection"])
        self.assertEqual(response.context["moment_permission"].reason, "room_ended")
        self.assertEqual(
            response.context["moment_permission"].message,
            "Roomが終了したため、通常のSHUNKAN-logは投稿できません。",
        )


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
        self.assertNotContains(response, "demo / demo")

    def test_login_page_shows_the_shunkan_logo(self):
        response = self.client.get(reverse("login"))

        self.assertContains(response, "shunkan-logo.png")
        self.assertContains(response, 'alt="旬間 (SHUNKAN)"')

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
        self.assertEqual(
            self.client.session.get("_auth_user_id"),
            str(user.pk),
        )

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
            {
                "username": self.user.username,
                "password": self.password,
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("rooms"))
        self.assertContains(
            response,
            '<h1 id="rooms-title">Roomを切り替える</h1>',
            html=True,
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("rooms"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('rooms')}",
        )

    def test_logout_prevents_reopening_protected_pages(self):
        room = Room.objects.create(
            owner=self.user,
            name="ログアウト確認用Room",
            starts_at=timezone.make_aware(
                datetime(2026, 8, 20, 12, 0, 0)
            ),
            ends_at=timezone.make_aware(
                datetime(2026, 8, 30, 12, 0, 0)
            ),
        )

        self.client.force_login(self.user)

        response = self.client.post(
            reverse("logout"),
            follow=True,
        )

        self.assertRedirects(response, reverse("login"))

        for url in (
            reverse("rooms"),
            reverse("room_detail", args=[room.pk]),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertRedirects(
                    response,
                    f"{reverse('login')}?next={url}",
                )


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
            starts_at=timezone.make_aware(
                datetime(2026, 8, 20, 12, 0, 0)
            ),
            ends_at=timezone.make_aware(
                datetime(2026, 8, 30, 12, 0, 0)
            ),
        )

        self.other_room = Room.objects.create(
            owner=self.other_user,
            name="他人のRoom",
            starts_at=timezone.make_aware(
                datetime(2026, 8, 20, 12, 0, 0)
            ),
            ends_at=timezone.make_aware(
                datetime(2026, 8, 30, 12, 0, 0)
            ),
        )

        self.client.force_login(self.owner)

    def test_room_list_shows_only_rooms_owned_by_the_current_user(self):
        response = self.client.get(reverse("rooms"))

        self.assertContains(response, "自分のRoom")
        self.assertNotContains(response, "他人のRoom")

    def test_room_switcher_groups_rooms_by_status(self):
        now = timezone.now()
        Room.objects.create(
            owner=self.owner,
            name="開催中のRoom",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
        )
        Room.objects.create(
            owner=self.owner,
            name="これからのRoom",
            starts_at=now + timedelta(days=2),
            ends_at=now + timedelta(days=3),
        )
        Room.objects.create(
            owner=self.owner,
            name="終了したRoom",
            starts_at=now - timedelta(days=3),
            ends_at=now - timedelta(days=2),
        )

        response = self.client.get(reverse("rooms"))

        self.assertContains(response, "いま開催中")
        self.assertContains(response, "これから始まる")
        self.assertContains(response, "終了したRoom")
        self.assertContains(response, "新しいRoomを作る")

    def test_room_switcher_prompts_before_room_specific_navigation(self):
        response = self.client.get(reverse("rooms"))

        self.assertContains(response, 'data-room-required="タスク"')
        self.assertContains(response, 'data-room-required="撮影"')
        self.assertContains(response, 'data-room-required="アルバム"')
        self.assertContains(response, "先にRoomを選びましょう")

    def test_room_navigation_returns_to_the_room_switcher(self):
        response = self.client.get(reverse("room_detail", args=[self.owner_room.pk]))

        self.assertContains(response, f'href="{reverse("rooms")}"')

    def test_room_creation_assigns_the_current_user_as_owner(self):
        response = self.client.post(
            reverse("rooms"),
            {
                "name": "新しいRoom",
                "starts_at": "2026-08-20T12:00",
                "ends_at": "2026-08-30T12:00",
            },
        )

        room = Room.objects.get(name="新しいRoom")

        self.assertRedirects(
            response,
            reverse("room_detail", args=[room.pk]),
        )

        self.assertEqual(room.owner, self.owner)

    def test_room_creation_rejects_end_before_start(self):
        response = self.client.post(
            reverse("rooms"),
            {
                "name": "不正なRoom",
                "starts_at": "2026-08-30T12:00",
                "ends_at": "2026-08-20T12:00",
            },
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "終了日時は開始日時より後である必要があります。",
        )

        self.assertFalse(
            Room.objects.filter(name="不正なRoom").exists()
        )

    def test_room_creation_rejects_same_start_and_end(self):
        response = self.client.post(
            reverse("rooms"),
            {
                "name": "同日時のRoom",
                "starts_at": "2026-08-20T12:00",
                "ends_at": "2026-08-20T12:00",
            },
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "終了日時は開始日時より後である必要があります。",
        )

        self.assertFalse(
            Room.objects.filter(name="同日時のRoom").exists()
        )

    def test_room_detail_rejects_another_users_room(self):
        response = self.client.get(
            reverse(
                "room_detail",
                args=[self.other_room.pk],
            )
        )

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

    @patch("core.views.RoomForm.save", side_effect=IntegrityError)
    def test_room_update_conflict_returns_form_errors(self, _save):
        response = self.client.post(
            reverse("room_update", args=[self.owner_room.pk]),
            {
                "name": "競合したRoom",
                "starts_at": "2026-08-20T12:00",
                "ends_at": "2026-08-30T12:00",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "関連データが更新されたためRoomを更新できませんでした。もう一度確認してください。",
            response.context["form"].non_field_errors(),
        )
        self.owner_room.refresh_from_db()
        self.assertEqual(self.owner_room.name, "自分のRoom")

    def test_cusers_room(self):
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

    def test_quick_create_adds_task_to_owned_room(self):
        response = self.client.post(
            reverse("task_quick_create", args=[self.owned_room.pk]),
            {"title": "即席タスク", "due_date": ""},
        )

        self.assertEqual(response.status_code, 200)
        task = Task.objects.get(room=self.owned_room, title="即席タスク")
        data = response.json()
        self.assertEqual(data["id"], task.pk)
        self.assertIn("即席タスク", data["label"])

    def test_quick_create_rejects_due_date_outside_room_period(self):
        response = self.client.post(
            reverse("task_quick_create", args=[self.owned_room.pk]),
            {
                "title": "期間外タスク",
                "due_date": (self.owned_room.ends_at + timedelta(days=1)).date().isoformat(),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Task.objects.filter(room=self.owned_room, title="期間外タスク").exists())

    def test_quick_create_rejects_another_users_room(self):
        response = self.client.post(
            reverse("task_quick_create", args=[self.other_room.pk]),
            {"title": "他人のRoomに追加", "due_date": ""},
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Task.objects.filter(title="他人のRoomに追加").exists())

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

    def test_owner_can_complete_task_with_json_response(self):
        response = self.client.post(
            reverse("task_complete", args=[self.owned_room.pk, self.owned_task.pk]),
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task"]["id"], self.owned_task.pk)
        self.assertEqual(response.json()["task"]["title"], "自分のタスク")
        self.owned_task.refresh_from_db()
        self.assertTrue(self.owned_task.is_completed)
        self.assertIsNotNone(self.owned_task.completed_at)

    def test_complete_task_falls_back_to_task_list_without_javascript(self):
        response = self.client.post(
            reverse("task_complete", args=[self.owned_room.pk, self.owned_task.pk])
        )

        self.assertRedirects(response, reverse("task_list", args=[self.owned_room.pk]))
        self.owned_task.refresh_from_db()
        self.assertTrue(self.owned_task.is_completed)

    def test_cannot_complete_another_users_task(self):
        response = self.client.post(
            reverse("task_complete", args=[self.other_room.pk, self.other_task.pk]),
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.other_task.refresh_from_db()
        self.assertFalse(self.other_task.is_completed)

    def test_cannot_complete_task_twice(self):
        self.owned_task.is_completed = True
        self.owned_task.completed_at = timezone.now()
        self.owned_task.save()

        response = self.client.post(
            reverse("task_complete", args=[self.owned_room.pk, self.owned_task.pk]),
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "このタスクはすでに完了しています。")

    def test_cannot_complete_task_in_ended_room(self):
        now = timezone.now()
        self.owned_room.starts_at = now - timedelta(days=2)
        self.owned_room.ends_at = now - timedelta(seconds=1)
        self.owned_room.save(update_fields=["starts_at", "ends_at"])

        response = self.client.post(
            reverse("task_complete", args=[self.owned_room.pk, self.owned_task.pk]),
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.owned_task.refresh_from_db()
        self.assertFalse(self.owned_task.is_completed)


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


class TaskToggleViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="toggle-user",
            password="test-password-123",
        )
        now = timezone.now()
        self.room = Room.objects.create(
            owner=self.user,
            name="開催中Room",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=1),
        )
        self.task = Task.objects.create(room=self.room, title="切り替えるTask")
        self.client.force_login(self.user)

    def test_task_can_toggle_completion_and_timestamp(self):
        url = reverse("task_toggle", args=[self.room.pk, self.task.pk])

        response = self.client.post(url)

        self.assertRedirects(response, reverse("task_list", args=[self.room.pk]))
        self.task.refresh_from_db()
        self.assertTrue(self.task.is_completed)
        self.assertIsNotNone(self.task.completed_at)

        response = self.client.post(url)

        self.assertRedirects(response, reverse("task_list", args=[self.room.pk]))
        self.task.refresh_from_db()
        self.assertFalse(self.task.is_completed)
        self.assertIsNone(self.task.completed_at)


class RelationalIntegrityRegressionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="integrity-user")
        self.now = timezone.now()
        self.room = Room.objects.create(
            owner=self.user,
            name="整合性Room",
            starts_at=self.now - timedelta(hours=1),
            ends_at=self.now + timedelta(hours=1),
            reflection_deadline_at=self.now + timedelta(days=7),
        )
        self.task = Task.objects.create(room=self.room, title="関連Task")
        self.category = Category.objects.create(room=self.room, name="関連Category")
        self.client.force_login(self.user)

    def test_reflection_model_rejects_task_and_category(self):
        reflection = MomentLog(
            room=self.room,
            task=self.task,
            category=self.category,
            body="不正な振り返り",
            occurred_at=self.room.ends_at,
            entry_type=MomentLog.EntryType.REFLECTION,
        )

        with self.assertRaises(ValidationError) as raised:
            reflection.full_clean()

        self.assertIn("task", raised.exception.message_dict)
        self.assertIn("category", raised.exception.message_dict)

    def test_photo_model_rejects_reflection_parent(self):
        reflection = MomentLog.objects.create(
            room=self.room,
            body="振り返り",
            occurred_at=self.room.ends_at,
            entry_type=MomentLog.EntryType.REFLECTION,
        )
        photo = Photo(moment_log=reflection, image="moment_photos/reflection.jpg")

        with self.assertRaisesMessage(ValidationError, "写真を追加できません"):
            photo.full_clean()

    def test_room_form_rejects_period_excluding_existing_children(self):
        Task.objects.filter(pk=self.task.pk).update(due_date=self.room.ends_at.date())
        MomentLog.objects.create(
            room=self.room,
            body="既存ログ",
            occurred_at=self.now,
        )
        form = RoomForm(
            {
                "name": self.room.name,
                "starts_at": self.now + timedelta(days=1),
                "ends_at": self.now + timedelta(days=1, minutes=10),
            },
            instance=self.room,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("ends_at", form.errors)

    def test_upload_caption_over_140_characters_is_rejected_before_writes(self):
        output = BytesIO()
        Image.new("RGB", (20, 20), "coral").save(output, format="JPEG")
        response = self.client.post(
            reverse("room_moments_new", args=[self.room.pk]),
            {
                "body": "長いキャプション",
                "images": SimpleUploadedFile(
                    "caption.jpg", output.getvalue(), content_type="image/jpeg"
                ),
                "captions": "あ" * 141,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "140文字以内")
        self.assertFalse(MomentLog.objects.filter(room=self.room).exists())
        self.assertFalse(Photo.objects.exists())


class RoomMutationStateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="readonly-user",
            password="test-password-123",
        )
        now = timezone.now()
        self.room = Room.objects.create(
            owner=self.user,
            name="終了済みRoom",
            starts_at=now - timedelta(days=2),
            ends_at=now - timedelta(days=1),
        )
        self.category = Category.objects.create(room=self.room, name="記録")
        self.task = Task.objects.create(room=self.room, title="完了したこと")
        self.moment = MomentLog.objects.create(
            room=self.room,
            body="残した記録",
            occurred_at=self.room.ends_at - timedelta(hours=1),
        )
        self.photo = Photo.objects.create(
            moment_log=self.moment,
            image=SimpleUploadedFile(
                "ended.jpg", b"fake-image-data", content_type="image/jpeg"
            ),
            caption="変更前",
        )
        self.client.force_login(self.user)

    def test_ended_room_update_pages_are_read_only(self):
        paths = (
            reverse("room_update", args=[self.room.pk]),
            reverse("task_update", args=[self.room.pk, self.task.pk]),
            reverse("moment_update", args=[self.room.pk, self.moment.pk]),
            reverse("photo_update", args=[self.room.pk, self.photo.pk]),
            reverse("category_update", args=[self.room.pk, self.category.pk]),
        )

        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

    def test_ended_room_cannot_delete_room(self):
        response = self.client.post(reverse("room_delete", args=[self.room.pk]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Room.objects.filter(pk=self.room.pk).exists())

    def test_ended_room_cannot_delete_task(self):
        response = self.client.post(
            reverse("task_delete", args=[self.room.pk, self.task.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Task.objects.filter(pk=self.task.pk).exists())

    def test_ended_room_cannot_toggle_task(self):
        response = self.client.post(
            reverse("task_toggle", args=[self.room.pk, self.task.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.task.refresh_from_db()
        self.assertFalse(self.task.is_completed)

    def test_ended_room_cannot_delete_moment(self):
        response = self.client.post(
            reverse("moment_delete", args=[self.room.pk, self.moment.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(MomentLog.objects.filter(pk=self.moment.pk).exists())

    def test_ended_room_cannot_delete_photo(self):
        response = self.client.post(
            reverse("photo_delete", args=[self.room.pk, self.photo.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Photo.objects.filter(pk=self.photo.pk).exists())

    def test_ended_room_cannot_delete_category(self):
        response = self.client.post(
            reverse("category_delete", args=[self.room.pk, self.category.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())


class PostgreSQLIntegrityTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="postgres-integrity-user",
            password="test-password-123",
        )
        now = timezone.now()
        self.room = Room.objects.create(
            owner=self.user,
            name="制約確認Room",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
            reflection_deadline_at=now + timedelta(days=8),
        )
        self.other_room = Room.objects.create(
            owner=self.user,
            name="別Room",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
        )
        self.category = Category.objects.create(room=self.room, name="自分")
        self.other_category = Category.objects.create(
            room=self.other_room, name="別Room"
        )
        self.task = Task.objects.create(room=self.room, title="自分のTask")
        self.other_task = Task.objects.create(
            room=self.other_room, title="別RoomのTask"
        )

    def make_photo(self, name):
        return SimpleUploadedFile(name, b"fake-image-data", content_type="image/jpeg")

    def test_room_period_constraint_rejects_invalid_period(self):
        with self.assertRaises(IntegrityError):
            Room.objects.create(
                owner=self.user,
                name="終了が先のRoom",
                starts_at=self.room.starts_at,
                ends_at=self.room.starts_at,
            )

    def test_room_reflection_deadline_constraint_rejects_deadline_before_end(self):
        with self.assertRaises(IntegrityError):
            Room.objects.create(
                owner=self.user,
                name="期限が早いRoom",
                starts_at=self.room.starts_at,
                ends_at=self.room.ends_at,
                reflection_deadline_at=self.room.starts_at,
            )

    def test_task_completion_constraint_rejects_missing_timestamp(self):
        with self.assertRaises(IntegrityError):
            Task.objects.create(
                room=self.room,
                title="時刻なし完了Task",
                is_completed=True,
            )

    def test_task_room_boundary_trigger_rejects_other_room_category(self):
        with self.assertRaises(IntegrityError):
            Task.objects.create(
                room=self.room,
                category=self.other_category,
                title="別RoomカテゴリのTask",
            )

    def test_task_due_date_trigger_rejects_date_outside_room(self):
        with self.assertRaises(IntegrityError):
            Task.objects.create(
                room=self.room,
                title="期間外期限のTask",
                due_date=(self.room.ends_at + timedelta(days=1)).date(),
            )

    def test_moment_room_boundary_trigger_rejects_other_room_task(self):
        with self.assertRaises(IntegrityError):
            MomentLog.objects.create(
                room=self.room,
                task=self.other_task,
                body="別RoomのTaskを指定",
                occurred_at=timezone.now(),
            )

    def test_moment_time_trigger_rejects_log_outside_room(self):
        with self.assertRaises(IntegrityError):
            MomentLog.objects.create(
                room=self.room,
                body="期間外の通常ログ",
                occurred_at=self.room.starts_at - timedelta(seconds=1),
            )

    def test_photo_limit_trigger_rejects_fourth_photo(self):
        moment = MomentLog.objects.create(
            room=self.room,
            body="写真上限確認",
            occurred_at=timezone.now(),
        )
        for index in range(3):
            Photo.objects.create(
                moment_log=moment,
                image=self.make_photo(f"photo-{index}.jpg"),
            )

        with self.assertRaises(IntegrityError):
            Photo.objects.create(
                moment_log=moment,
                image=self.make_photo("photo-4.jpg"),
            )


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

                self.assertContains(
                    response,
                    "csrfmiddlewaretoken",
                )


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

        self.assertFalse(
            Room.objects.filter(pk=room.pk).exists()
        )

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

    def test_form_validates_due_date_inside_the_room_period(self):
        form = TaskForm(
            {
                "title": "期間内タスク",
                "due_date": (timezone.now() + timedelta(days=2)).date(),
                "category": "",
            },
            room=self.room,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())

    def test_form_rejects_due_date_outside_the_room_period(self):
        form = TaskForm(
            {
                "title": "期間外タスク",
                "due_date": (self.room.ends_at + timedelta(days=1)).date(),
                "category": "",
            },
            room=self.room,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("期限はRoom期間内で設定してください。", str(form.errors))


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

        self.assertEqual(
            log.entry_type,
            MomentLog.EntryType.MOMENT,
        )

        self.assertEqual(
            log.occurred_at,
            occurred_at,
        )

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

        self.assertEqual(
            log.occurred_at,
            edited,
        )


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

        self.assertEqual(
            photo.moment_log,
            self.moment_log,
        )

        self.assertEqual(
            photo.caption,
            "夏の花火",
        )

        self.assertEqual(
            photo.sort_order,
            0,
        )

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

        self.assertEqual(
            photo.moment_log.room,
            self.room,
        )
