from datetime import date

from django.core.validators import MaxValueValidator, MinLengthValidator
from django.db import models

SUMMER_END_DATE = date(2026, 8, 31)


class Task(models.Model):
    class Category(models.TextChoices):
        EVENT = "イベント", "イベント"
        LEISURE = "レジャー・グルメ", "レジャー・グルメ"
        NATURE = "自然・癒し", "自然・癒し"
        OTHER = "その他", "その他"

    title = models.CharField("タイトル", max_length=100, validators=[MinLengthValidator(1)])
    category = models.CharField("カテゴリ", max_length=20, choices=Category.choices)
    due_date = models.DateField(
        "実行したい日",
        validators=[
            MaxValueValidator(
                SUMMER_END_DATE,
                message="実行したい日は2026年8月31日以前にしてください。",
            )
        ],
    )
    is_completed = models.BooleanField("完了", default=False)
    completed_at = models.DateTimeField("完了日時", null=True, blank=True)
    created_at = models.DateTimeField("登録日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        ordering = ["due_date", "id"]

    def __str__(self):
        return self.title
