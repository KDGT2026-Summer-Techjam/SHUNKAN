from typing import ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Room(models.Model):
    objects = models.Manager()

    task_count: int
    completed_count: int
    progress_percent: int
    ui_status: str

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rooms",
    )
    name = models.CharField(max_length=50)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reflection_deadline_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")),
                name="room_ends_after_starts",
            ),
            models.CheckConstraint(
                condition=(
                    Q(reflection_deadline_at__isnull=True)
                    | Q(reflection_deadline_at__gte=F("ends_at"))
                ),
                name="room_reflection_deadline_after_end",
            ),
        ]

    def clean(self):
        super().clean()

        if self.ends_at <= self.starts_at:
            raise ValidationError(
                {"ends_at": "終了日時は開始日時より後である必要があります。"}
            )
        if (
            self.reflection_deadline_at is not None
            and self.reflection_deadline_at < self.ends_at
        ):
            raise ValidationError(
                {
                    "reflection_deadline_at": (
                        "振り返り期限はRoom終了日時以後に設定してください。"
                    )
                }
            )

    def __str__(self):
        return self.name

class Category(models.Model):
    objects = models.Manager()

    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="categories",
    )
    name = models.CharField(max_length=30)
    color = models.CharField(max_length=20, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["room", "name"],
                name="unique_category_name_per_room",
            ),
        ]
        ordering: ClassVar[list[str]] = ["sort_order", "id"]

    def __str__(self):
        return self.name

class Task(models.Model):
    objects = models.Manager()

    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    title = models.CharField(max_length=100)
    due_date = models.DateField(
        null=True,
        blank=True,
    )
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()

        if self.category is not None and self.category.room_id != self.room_id:
            raise ValidationError(
                {"category": "Category must belong to the same Room."}
            )

        if self.is_completed and self.completed_at is None:
            raise ValidationError(
                {"completed_at": "completed_at is required when the task is completed."}
            )

        if not self.is_completed and self.completed_at is not None:
            raise ValidationError(
                {"completed_at": "completed_at must be empty when the task is not completed."}
            )

        if self.due_date is not None:
            starts_on = timezone.localtime(self.room.starts_at).date()
            ends_on = timezone.localtime(self.room.ends_at).date()
            if not starts_on <= self.due_date <= ends_on:
                raise ValidationError(
                    {"due_date": "期限はRoom期間内で設定してください。"}
                )

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=(
                    Q(is_completed=True, completed_at__isnull=False)
                    | Q(is_completed=False, completed_at__isnull=True)
                ),
                name="task_completion_timestamp_matches_status",
            ),
        ]

class MomentLog(models.Model):
    objects = models.Manager()

    class EntryType(models.TextChoices):
        MOMENT = "moment", "moment"
        REFLECTION = "reflection", "reflection"

    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="moment_logs",
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moment_logs",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moment_logs",
    )
    body = models.CharField(max_length=280)
    occurred_at = models.DateTimeField()
    entry_type = models.CharField(
        max_length=20,
        choices=EntryType.choices,
        default=EntryType.MOMENT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=Q(entry_type__in=["moment", "reflection"]),
                name="moment_log_entry_type_is_valid",
            ),
        ]

    def clean(self):
        super().clean()

        if self.task is not None and self.task.room_id != self.room_id:
            raise ValidationError(
                {"task": "Task must belong to the same Room."}
            )

        if self.category is not None and self.category.room_id != self.room_id:
            raise ValidationError(
                {"category": "Category must belong to the same Room."}
            )

        if self.room_id and self.occurred_at:
            room = self.room
            if self.entry_type == self.EntryType.MOMENT:
                if not room.starts_at <= self.occurred_at < room.ends_at:
                    raise ValidationError(
                        {"occurred_at": "通常のSHUNKAN-logはRoom期間内に設定してください。"}
                    )
            elif self.entry_type == self.EntryType.REFLECTION:
                if (
                    room.reflection_deadline_at is None
                    or not room.ends_at
                    <= self.occurred_at
                    <= room.reflection_deadline_at
                ):
                    raise ValidationError(
                        {
                            "occurred_at": (
                                "振り返りはRoom終了後から振り返り期限までに設定してください。"
                            )
                        }
                    )

class Photo(models.Model):
    objects = models.Manager()

    class CapturedAtSource(models.TextChoices):
        EXIF = "exif", "exif"
        MANUAL = "manual", "manual"
        UNKNOWN = "unknown", "unknown"

    moment_log = models.ForeignKey(
        MomentLog,
        on_delete=models.CASCADE,
        related_name="photos",
    )
    image = models.ImageField(
        upload_to="moment_photos/",
    )
    caption = models.CharField(
        max_length=140,
        blank=True,
    )
    captured_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="EXIFまたは利用者が指定した撮影日時",
    )
    captured_at_source = models.CharField(
        max_length=10,
        choices=CapturedAtSource.choices,
        default=CapturedAtSource.UNKNOWN,
    )
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["sort_order", "created_at"]

    def clean(self):
        super().clean()
        if self.moment_log_id and self._state.adding:
            if self.moment_log.photos.count() >= 3:
                raise ValidationError(
                    {"moment_log": "1件のSHUNKAN-logに保存できる写真は3枚までです。"}
                )
