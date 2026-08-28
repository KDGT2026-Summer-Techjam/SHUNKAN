from datetime import timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .models import MomentLog, Photo, Room


class PhotoMediaCleanupTests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()

        self.user = get_user_model().objects.create_user(
            username="media-cleanup-user",
            password="password",
        )
        now = timezone.now()
        self.room = Room.objects.create(
            owner=self.user,
            name="写真削除テスト",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=1),
        )
        self.moment_log = MomentLog.objects.create(
            room=self.room,
            body="写真付きの記録",
            occurred_at=now,
        )

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()
        super().tearDown()

    def create_photo(self, moment_log=None):
        return Photo.objects.create(
            moment_log=moment_log or self.moment_log,
            image=SimpleUploadedFile(
                "memory.jpg",
                b"photo contents",
                content_type="image/jpeg",
            ),
        )

    def assert_image_exists(self, photo):
        self.assertTrue(photo.image.storage.exists(photo.image.name))

    def assert_image_deleted(self, storage, name):
        self.assertFalse(storage.exists(name))

    def test_direct_photo_deletion_removes_image_after_commit(self):
        photo = self.create_photo()
        storage = photo.image.storage
        name = photo.image.name
        self.assert_image_exists(photo)

        photo.delete()

        self.assert_image_deleted(storage, name)

    def test_moment_log_cascade_removes_photo_image_after_commit(self):
        photo = self.create_photo()
        storage = photo.image.storage
        name = photo.image.name
        self.assert_image_exists(photo)

        self.moment_log.delete()

        self.assert_image_deleted(storage, name)

    def test_room_cascade_removes_photo_image_after_commit(self):
        photo = self.create_photo()
        storage = photo.image.storage
        name = photo.image.name
        self.assert_image_exists(photo)

        self.room.delete()

        self.assert_image_deleted(storage, name)

    def test_rollback_keeps_photo_row_and_image_file(self):
        photo = self.create_photo()
        photo_id = photo.pk
        storage = photo.image.storage
        name = photo.image.name
        self.assert_image_exists(photo)

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                photo.delete()
                self.assertTrue(storage.exists(name))
                raise RuntimeError("roll back deletion")

        self.assertTrue(Photo.objects.filter(pk=photo_id).exists())
        self.assertTrue(storage.exists(name))


@override_settings(ALLOW_PHOTO_UPLOADS=True)
class RoomMomentMediaCompensationTests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()

        self.user = get_user_model().objects.create_user(
            username="moment-media-user",
            password="password",
        )
        now = timezone.now()
        self.room = Room.objects.create(
            owner=self.user,
            name="投稿時の写真テスト",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=1),
        )
        self.client.force_login(self.user)
        self.url = reverse("room_moments_new", args=[self.room.pk])

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()
        super().tearDown()

    def uploaded_image(self, name):
        contents = BytesIO()
        Image.new("RGB", (2, 2), color="orange").save(contents, format="JPEG")
        return SimpleUploadedFile(
            name,
            contents.getvalue(),
            content_type="image/jpeg",
        )

    def media_files(self):
        return [path for path in Path(self.media_directory.name).rglob("*") if path.is_file()]

    def test_second_photo_failure_after_file_write_removes_all_new_files(self):
        original_save = Photo.save
        photo_save_count = 0

        def fail_after_second_save(photo, *args, **kwargs):
            nonlocal photo_save_count
            original_save(photo, *args, **kwargs)
            photo_save_count += 1
            if photo_save_count == 2:
                raise IntegrityError("forced failure after second photo write")

        with patch.object(Photo, "save", autospec=True, side_effect=fail_after_second_save):
            response = self.client.post(
                self.url,
                {
                    "body": "保存に失敗する記録",
                    "entry_type": MomentLog.EntryType.MOMENT,
                    "images": [
                        self.uploaded_image("first.jpg"),
                        self.uploaded_image("second.jpg"),
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertFalse(MomentLog.objects.exists())
        self.assertFalse(Photo.objects.exists())
        self.assertEqual(self.media_files(), [])

    def test_successful_multi_photo_post_keeps_files(self):
        response = self.client.post(
            self.url,
            {
                "body": "保存に成功する記録",
                "entry_type": MomentLog.EntryType.MOMENT,
                "images": [
                    self.uploaded_image("first.jpg"),
                    self.uploaded_image("second.jpg"),
                ],
            },
        )

        self.assertRedirects(
            response,
            reverse("room_album", args=[self.room.pk]),
        )
        self.assertEqual(MomentLog.objects.count(), 1)
        self.assertEqual(Photo.objects.count(), 2)
        self.assertEqual(len(self.media_files()), 2)
        for photo in Photo.objects.all():
            self.assertTrue(photo.image.storage.exists(photo.image.name))
