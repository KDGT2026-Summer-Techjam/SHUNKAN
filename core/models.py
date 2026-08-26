from typing import ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


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

    def clean(self):
        super().clean()

        if self.ends_at <= self.starts_at:
            raise ValidationError(
                {"ends_at": "終了日時は開始日時より後である必要があります。"}
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

class Photo(models.Model):
    objects = models.Manager()

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
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["sort_order", "created_at"]